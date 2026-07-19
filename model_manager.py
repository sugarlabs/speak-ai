"""Offline-first model management for Speak-AI.

Sugar runs in classrooms that are frequently offline and frequently old. A
1 GB XO laptop cannot hold Kokoro (measured ~1.3 GB RSS once loaded), and a
school connection cannot be relied on to fetch a 60-145 MB voice pack in the
middle of a lesson. Both of those are facts about the deployment, not edge
cases, so this module treats them as the normal path.

Three jobs:

1. Decide what this machine can actually run, before anything heavy loads.
   Under-provisioned devices get espeak-ng and never attempt a neural model,
   because an OOM kill mid-lesson is worse than a robotic voice.

2. Fetch models safely when there IS a connection. Downloads land on a .tmp
   path, get checksummed against MANIFEST.json, and are only then renamed into
   place. rename() is atomic on POSIX, so a model file either exists complete
   and verified or does not exist at all. There is no half-written state for
   the activity to trip over.

3. Never let the child press Speak and hear nothing. Every failure path in
   here ends at espeak-ng, not at an exception.

Nothing in this module is allowed to raise into the UI thread. Callers get a
truthful return value and a log line; the activity keeps talking.
"""

import hashlib
import json
import logging
import os
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is optional at runtime
    psutil = None
    logger.warning("psutil unavailable; RAM detection will assume a capable device")

MANIFEST_PATH = Path(__file__).parent / "MANIFEST.json"
DEFAULT_MODEL_DIR = Path(
    os.environ.get("SPEAK_AI_MODEL_DIR", Path.home() / ".local/share/speak-ai/models")
)
ERROR_LOG = Path.home() / ".local/share/speak-ai/download_errors.log"

# Below this, loading Kokoro or MMS reliably OOMs on the hardware Sugar targets.
# Derived from measured peak RSS during synthesis (~1.29 GB on x86_64) plus
# headroom for the GStreamer pipeline and the rest of the desktop.
MIN_RAM_FOR_NEURAL_MB = 1536

# Read in 1 MiB blocks: large enough that syscall overhead disappears, small
# enough that a progress callback still feels responsive on a slow link.
_CHUNK = 1024 * 1024


class ModelUnavailable(Exception):
    """Raised internally when a model cannot be produced. Never escapes get()."""


class ModelManager:
    """Resolves a backend's model file, downloading it only if it has to.

    Typical use from speech.py:

        mm = ModelManager()
        if not mm.neural_allowed:
            use_espeak()
        else:
            path = mm.get('piper_ar')      # None means "fall back to espeak"
    """

    def __init__(self, model_dir=None, manifest_path=None):
        self.model_dir = Path(model_dir or DEFAULT_MODEL_DIR)
        self.manifest_path = Path(manifest_path or MANIFEST_PATH)
        self._manifest = None
        self._lock = threading.Lock()
        self._loading = {}          # name -> threading.Thread, for async prefetch
        self.available_ram_mb = self._detect_ram_mb()
        self.neural_allowed = self.available_ram_mb >= MIN_RAM_FOR_NEURAL_MB

        if not self.neural_allowed:
            logger.warning(
                "Detected %d MB RAM (< %d MB): neural TTS disabled, using espeak-ng",
                self.available_ram_mb, MIN_RAM_FOR_NEURAL_MB,
            )

    # ------------------------------------------------------------------
    # capability detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_ram_mb():
        """Total system RAM in MB.

        Total rather than available on purpose: available fluctuates with page
        cache and would make the same laptop eligible one launch and ineligible
        the next, which is worse than being consistently wrong.
        """
        if psutil is not None:
            return int(psutil.virtual_memory().total / (1024 ** 2))
        try:
            # Fallback for images that ship without psutil.
            pages = os.sysconf('SC_PHYS_PAGES')
            page_size = os.sysconf('SC_PAGE_SIZE')
            return int(pages * page_size / (1024 ** 2))
        except (ValueError, OSError, AttributeError):
            logger.warning("Cannot determine system RAM; assuming device is capable")
            return MIN_RAM_FOR_NEURAL_MB

    # ------------------------------------------------------------------
    # manifest
    # ------------------------------------------------------------------

    @property
    def manifest(self) -> Dict:
        """MANIFEST.json, loaded once.

        A missing or malformed manifest is not fatal — it just means nothing is
        downloadable and every lookup falls through to espeak.
        """
        if self._manifest is None:
            try:
                with open(self.manifest_path, 'r', encoding='utf-8') as f:
                    self._manifest = json.load(f).get('models', {})
            except FileNotFoundError:
                logger.error("MANIFEST.json not found at %s", self.manifest_path)
                self._manifest = {}
            except json.JSONDecodeError as e:
                logger.error("MANIFEST.json is malformed: %s", e)
                self._manifest = {}
        return self._manifest

    def local_path(self, name: str) -> Optional[Path]:
        """Where a model would live on disk, or None if it isn't in the manifest."""
        entry = self.manifest.get(name)
        if entry is None:
            return None
        return self.model_dir / entry['filename']

    def is_cached(self, name: str) -> bool:
        path = self.local_path(name)
        return path is not None and path.is_file()

    # ------------------------------------------------------------------
    # retrieval
    # ------------------------------------------------------------------

    def get(self, name: str, allow_download=True, progress_cb=None) -> Optional[Path]:
        """Return a verified local path for `name`, or None to use espeak.

        None is a normal, expected answer. Callers must handle it; they must not
        treat it as an error state.
        """
        if not self.neural_allowed:
            logger.info("Neural backends disabled on this device; skipping %s", name)
            return None

        entry = self.manifest.get(name)
        if entry is None:
            logger.error("No manifest entry for model '%s'", name)
            return None

        path = self.model_dir / entry['filename']

        if path.is_file():
            # Trust the cache. Re-hashing 60-145 MB on every launch would add
            # seconds to startup on the SD-card storage these machines use, and
            # the file was already verified at download time.
            return path

        if not allow_download:
            return None

        try:
            self._download_verified(entry, path, progress_cb=progress_cb)
            return path
        except ModelUnavailable as e:
            self._record_failure(name, e)
            return None

    def _download_verified(self, entry, dest: Path, progress_cb=None):
        """Download to .tmp, checksum it, then atomically rename into place."""
        url = entry['url']
        expected = (entry.get('sha256') or '').lower()

        # Refuse to install anything we cannot verify. An unpinned model is how
        # a school ends up silently running a different voice than the one that
        # was reviewed, so an empty or malformed hash is a hard stop, not a
        # warning we skip past.
        if len(expected) != 64 or not all(c in '0123456789abcdef' for c in expected):
            raise ModelUnavailable(
                "manifest entry has no valid sha256; refusing to install unverified model"
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + '.tmp')

        logger.info("Downloading %s -> %s", url, dest)
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                total = int(resp.headers.get('Content-Length') or 0)
                seen = 0
                with open(tmp, 'wb') as out:
                    while True:
                        chunk = resp.read(_CHUNK)
                        if not chunk:
                            break
                        out.write(chunk)
                        digest.update(chunk)
                        seen += len(chunk)
                        if progress_cb and total:
                            progress_cb(seen / total)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            tmp.unlink(missing_ok=True)
            raise ModelUnavailable(f"download failed: {e}") from e

        actual = digest.hexdigest()
        if actual != expected:
            # A wrong hash means a corrupted transfer or a changed upstream
            # artefact. Either way we refuse it — a silently different model is
            # exactly the thing MANIFEST.json exists to prevent.
            tmp.unlink(missing_ok=True)
            raise ModelUnavailable(
                f"checksum mismatch: expected {expected[:12]}..., got {actual[:12]}..."
            )

        # Atomic on POSIX: readers see either no file or the complete verified one.
        tmp.replace(dest)
        logger.info("Verified and installed %s (%.1f MiB)",
                    dest.name, dest.stat().st_size / 1024 ** 2)

    # ------------------------------------------------------------------
    # async prefetch
    # ------------------------------------------------------------------

    def prefetch(self, name: str, on_done: Optional[Callable] = None):
        """Fetch a model on a background thread.

        Cold-loading Kokoro takes tens of seconds on SD-card storage. Blocking
        the GTK main loop for that long looks like a crash to a child, so the
        activity speaks with espeak immediately and swaps to the neural voice
        once this lands.
        """
        with self._lock:
            existing = self._loading.get(name)
            if existing is not None and existing.is_alive():
                return existing

            def _work():
                path = self.get(name)
                if on_done is not None:
                    try:
                        on_done(name, path)
                    except Exception:
                        logger.exception("prefetch callback for %s failed", name)

            t = threading.Thread(target=_work, name=f"prefetch-{name}", daemon=True)
            self._loading[name] = t
            t.start()
            return t

    def is_loading(self, name: str) -> bool:
        t = self._loading.get(name)
        return t is not None and t.is_alive()

    # ------------------------------------------------------------------
    # housekeeping
    # ------------------------------------------------------------------

    @staticmethod
    def _record_failure(name, exc):
        """Append to the download error log. Never raises."""
        try:
            ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(ERROR_LOG, 'a', encoding='utf-8') as f:
                f.write(f"{name}\t{exc}\n")
        except OSError:
            logger.exception("Could not write %s", ERROR_LOG)
        logger.warning("Model '%s' unavailable (%s); falling back to espeak-ng", name, exc)

    def disk_usage_mb(self) -> float:
        """How much disk the cached models currently occupy."""
        if not self.model_dir.is_dir():
            return 0.0
        total = sum(p.stat().st_size for p in self.model_dir.rglob('*') if p.is_file())
        return total / (1024 ** 2)

    def free_disk_mb(self) -> float:
        target = self.model_dir if self.model_dir.is_dir() else self.model_dir.parent
        while not target.exists() and target != target.parent:
            target = target.parent
        return shutil.disk_usage(target).free / (1024 ** 2)

    def summary(self) -> Dict:
        """Diagnostic snapshot, for logs and the about box."""
        return {
            'ram_mb': self.available_ram_mb,
            'neural_allowed': self.neural_allowed,
            'model_dir': str(self.model_dir),
            'cached_models': sorted(n for n in self.manifest if self.is_cached(n)),
            'disk_used_mb': round(self.disk_usage_mb(), 2),
            'disk_free_mb': round(self.free_disk_mb(), 2),
        }
