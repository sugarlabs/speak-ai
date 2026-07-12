"""
Disk-backed LRU cache for synthesized TTS audio.

Stores float32 waveforms as .npy files with a JSON index for fast lookup.
Evicts least-recently-used entries when entry count or disk quota is exceeded.
"""

import json
import os
import time
import hashlib
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger('speak')

DEFAULT_CACHE_DIR = Path(__file__).parent / ".tts_cache"
MAX_ENTRIES = 500
MAX_DISK_BYTES = 200 * 1024 * 1024
_REQUIRED_KEYS = ('path', 'atime', 'size', 'sample_rate')


class TTSCache:
    """Thread-safe, disk-backed LRU cache for TTS waveforms.

    Keys are SHA-256 hashes of (text, voice, lang, speed). Values are
    numpy float32 arrays stored as .npy files. A JSON index tracks
    access times, file sizes, and sample rates.
    """

    def __init__(
        self,
        cache_dir: Optional[Union[Path, str]] = None,
        max_entries: int = MAX_ENTRIES,
        max_disk_bytes: int = MAX_DISK_BYTES,
    ):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.max_entries = max_entries
        self.max_disk_bytes = max_disk_bytes
        self._index_path = self.cache_dir / "index.json"
        self._index: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._dirty = False
        self._load_index()

    def __repr__(self) -> str:
        n = len(self._index)
        mb = sum(e.get('size', 0) for e in self._index.values()) / (1024 * 1024)
        return f"TTSCache(entries={n}, disk={mb:.1f}MB)"

    def __len__(self) -> int:
        with self._lock:
            return len(self._index)

    @staticmethod
    def _compute_hash(text: str, voice: str, lang_code: str, speed: float) -> str:
        payload = json.dumps(
            [text, voice, lang_code, speed],
            ensure_ascii=False,
            separators=(',', ':'),
        )
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def _load_index(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if not self._index_path.is_file():
            return
        try:
            with self._index_path.open('r', encoding='utf-8') as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Cache index corrupted, resetting: {e}")
            self._index = {}
            return

        self._index = {}
        for key, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            if not all(k in entry for k in _REQUIRED_KEYS):
                continue
            if not isinstance(entry.get('size'), (int, float)):
                continue
            self._index[key] = entry

    def _save_index(self) -> None:
        tmp = self._index_path.with_suffix('.tmp')
        try:
            with tmp.open('w', encoding='utf-8') as f:
                json.dump(self._index, f)
            os.replace(str(tmp), str(self._index_path))
            self._dirty = False
        except OSError as e:
            logger.error(f"Failed to write cache index: {e}")

    def _evict(self) -> None:
        current_size = sum(e.get('size', 0) for e in self._index.values())
        if len(self._index) <= self.max_entries and current_size <= self.max_disk_bytes:
            return

        sorted_entries = sorted(
            self._index.items(),
            key=lambda x: x[1].get('atime', 0.0),
        )

        for key, entry in sorted_entries:
            if len(self._index) <= self.max_entries and current_size <= self.max_disk_bytes:
                break
            target_file = self.cache_dir / entry['path']
            if target_file.is_file():
                try:
                    target_file.unlink()
                    logger.debug(f"Evicted: {key[:12]}")
                except OSError as e:
                    logger.error(f"Failed to delete {target_file.name}: {e}")
            current_size -= entry.get('size', 0)
            self._index.pop(key, None)

    def get(self, text: str, voice: str, lang_code: str = 'a',
            speed: float = 1.0) -> Tuple[Optional[np.ndarray], Optional[int]]:
        key = self._compute_hash(text, voice, lang_code, speed)
        with self._lock:
            entry = self._index.get(key)
            if not entry:
                return None, None

            payload_path = self.cache_dir / entry['path']
            if not payload_path.is_file():
                self._index.pop(key, None)
                self._dirty = True
                return None, None

            entry['atime'] = time.time()
            self._dirty = True

        try:
            waveform = np.load(payload_path)
            return waveform, entry.get('sample_rate', 24000)
        except Exception as e:
            logger.error(f"Corrupt cache file {payload_path.name}: {e}")
            with self._lock:
                self._index.pop(key, None)
                self._dirty = True
            return None, None

    def put(self, text: str, voice: str, lang_code: str, speed: float,
            audio_array: np.ndarray, sample_rate: int = 24000) -> None:
        if audio_array is None or not isinstance(audio_array, np.ndarray):
            logger.warning("put() called with invalid audio_array, skipping")
            return
        if audio_array.size == 0:
            logger.warning("put() called with empty audio_array, skipping")
            return

        key = self._compute_hash(text, voice, lang_code, speed)
        filename = f"{key[:16]}.npy"
        payload_path = self.cache_dir / filename

        try:
            np.save(payload_path, audio_array)
            file_size = payload_path.stat().st_size
            with self._lock:
                self._index[key] = {
                    'path': filename,
                    'atime': time.time(),
                    'size': file_size,
                    'sample_rate': sample_rate,
                }
                self._evict()
                self._dirty = True
                self._flush_if_dirty()
        except OSError as e:
            logger.error(f"Failed to write cache file {filename}: {e}")

    def _flush_if_dirty(self) -> None:
        if self._dirty:
            self._save_index()

    def flush(self) -> None:
        with self._lock:
            self._flush_if_dirty()

    def clear(self) -> None:
        with self._lock:
            for entry in self._index.values():
                payload_path = self.cache_dir / entry['path']
                if payload_path.is_file():
                    try:
                        payload_path.unlink()
                    except OSError:
                        pass
            self._index.clear()
            self._save_index()

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total_size = sum(e.get('size', 0) for e in self._index.values())
            return {
                'entries': len(self._index),
                'disk_mb': round(total_size / (1024 * 1024), 2),
                'disk_bytes': total_size,
            }
