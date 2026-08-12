# Speak.activity
# This file is part of Speak.activity
#
# Copyright (C) 2026  NSA Raiyyan <f20241312@pilani.bits-pilani.ac.in>
#
#     Speak.activity is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     Speak.activity is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with Speak.activity.  If not, see <http://www.gnu.org/licenses/>.

"""Tests for model_manager.py.

Everything here runs against a throwaway HTTP server on localhost, so the
suite needs no network and no 145 MB download. The point is to prove the
safety properties, not to exercise HuggingFace:

  - a corrupted download never lands in the model directory
  - an unpinned (empty-hash) entry is refused outright
  - a partial download leaves no .tmp litter behind
  - a low-RAM device never even attempts a neural model
  - nothing in the failure paths raises into the caller
"""

import functools
import hashlib
import http.server
import json
import os
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from model_manager import ModelManager, MIN_RAM_FOR_NEURAL_MB  # noqa: E402


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep test output readable


class ServedDirectory:
    """A localhost HTTP server over a temp dir, usable as a context manager."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp())
        handler = functools.partial(_QuietHandler, directory=str(self.root))
        self.httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.root, ignore_errors=True)

    def publish(self, name: str, data: bytes) -> str:
        (self.root / name).write_bytes(data)
        return f"http://127.0.0.1:{self.port}/{name}"


class ModelManagerTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.model_dir = self.tmp / "models"
        self.manifest_path = self.tmp / "MANIFEST.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_manifest(self, models):
        self.manifest_path.write_text(json.dumps({"schema_version": 1, "models": models}))

    def manager(self, force_neural=True):
        mm = ModelManager(model_dir=self.model_dir, manifest_path=self.manifest_path)
        if force_neural:
            # Decouple these tests from whatever RAM the CI runner happens to have.
            mm.neural_allowed = True
        return mm


class TestDownloadIntegrity(ModelManagerTestBase):
    def test_good_download_is_installed(self):
        payload = b"pretend onnx weights" * 5000
        with ServedDirectory() as srv:
            url = srv.publish("voice.onnx", payload)
            self.write_manifest({"v": {
                "filename": "voice.onnx", "url": url, "sha256": sha256_of(payload),
            }})
            path = self.manager().get("v")

        self.assertIsNotNone(path, "a correctly-hashed model should install")
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_bytes(), payload)

    def test_checksum_mismatch_is_rejected(self):
        payload = b"the bytes we actually serve"
        with ServedDirectory() as srv:
            url = srv.publish("voice.onnx", payload)
            self.write_manifest({"v": {
                "filename": "voice.onnx", "url": url,
                "sha256": sha256_of(b"the bytes we expected"),
            }})
            path = self.manager().get("v")

        self.assertIsNone(path, "a hash mismatch must not yield a usable path")
        self.assertFalse((self.model_dir / "voice.onnx").exists(),
                         "corrupt payload must not be left in the model dir")

    def test_no_tmp_file_survives_a_rejected_download(self):
        payload = b"corrupt"
        with ServedDirectory() as srv:
            url = srv.publish("voice.onnx", payload)
            self.write_manifest({"v": {
                "filename": "voice.onnx", "url": url, "sha256": sha256_of(b"different"),
            }})
            self.manager().get("v")

        leftovers = list(self.model_dir.glob("*.tmp")) if self.model_dir.exists() else []
        self.assertEqual(leftovers, [], f"stale .tmp files left behind: {leftovers}")

    def test_unpinned_entry_is_refused(self):
        payload = b"whatever"
        with ServedDirectory() as srv:
            url = srv.publish("voice.onnx", payload)
            self.write_manifest({"v": {"filename": "voice.onnx", "url": url, "sha256": ""}})
            path = self.manager().get("v")

        self.assertIsNone(path, "an empty sha256 must never install")

    def test_malformed_hash_is_refused(self):
        payload = b"whatever"
        with ServedDirectory() as srv:
            url = srv.publish("voice.onnx", payload)
            self.write_manifest({"v": {
                "filename": "voice.onnx", "url": url, "sha256": "not-a-real-hash",
            }})
            self.assertIsNone(self.manager().get("v"))

    def test_unreachable_url_returns_none(self):
        # Port 1 on localhost: reliably refused, no DNS involved.
        self.write_manifest({"v": {
            "filename": "voice.onnx", "url": "http://127.0.0.1:1/nope.onnx",
            "sha256": "a" * 64,
        }})
        self.assertIsNone(self.manager().get("v"), "network failure must degrade, not raise")


class TestCaching(ModelManagerTestBase):
    def test_cached_file_is_reused_without_network(self):
        payload = b"already here"
        self.write_manifest({"v": {
            "filename": "voice.onnx",
            "url": "http://127.0.0.1:1/unreachable.onnx",   # would fail if contacted
            "sha256": sha256_of(payload),
        }})
        (self.model_dir).mkdir(parents=True, exist_ok=True)
        (self.model_dir / "voice.onnx").write_bytes(payload)

        mm = self.manager()
        self.assertTrue(mm.is_cached("v"))
        self.assertEqual(mm.get("v").read_bytes(), payload)

    def test_allow_download_false_does_not_fetch(self):
        payload = b"x" * 100
        with ServedDirectory() as srv:
            url = srv.publish("voice.onnx", payload)
            self.write_manifest({"v": {
                "filename": "voice.onnx", "url": url, "sha256": sha256_of(payload),
            }})
            self.assertIsNone(self.manager().get("v", allow_download=False))

    def test_unknown_model_returns_none(self):
        self.write_manifest({})
        self.assertIsNone(self.manager().get("does_not_exist"))

    def test_missing_manifest_is_survivable(self):
        mm = ModelManager(model_dir=self.model_dir, manifest_path=self.tmp / "absent.json")
        mm.neural_allowed = True
        self.assertEqual(mm.manifest, {})
        self.assertIsNone(mm.get("anything"))

    def test_malformed_manifest_is_survivable(self):
        self.manifest_path.write_text("{ this is not json")
        mm = self.manager()
        self.assertEqual(mm.manifest, {})
        self.assertIsNone(mm.get("anything"))


class TestLowRamGuard(ModelManagerTestBase):
    def test_low_ram_device_never_downloads(self):
        payload = b"y" * 100
        with ServedDirectory() as srv:
            url = srv.publish("voice.onnx", payload)
            self.write_manifest({"v": {
                "filename": "voice.onnx", "url": url, "sha256": sha256_of(payload),
            }})
            mm = self.manager()
            mm.neural_allowed = False          # simulate a 1 GB XO laptop
            self.assertIsNone(mm.get("v"))

        self.assertFalse((self.model_dir / "voice.onnx").exists(),
                         "a low-RAM device must not fetch neural weights at all")

    def test_ram_detection_returns_something_sane(self):
        mm = self.manager(force_neural=False)
        self.assertGreater(mm.available_ram_mb, 0)
        self.assertEqual(mm.neural_allowed, mm.available_ram_mb >= MIN_RAM_FOR_NEURAL_MB)


class TestPrefetch(ModelManagerTestBase):
    def test_prefetch_completes_and_invokes_callback(self):
        payload = b"z" * 20000
        done = threading.Event()
        captured = {}

        with ServedDirectory() as srv:
            url = srv.publish("voice.onnx", payload)
            self.write_manifest({"v": {
                "filename": "voice.onnx", "url": url, "sha256": sha256_of(payload),
            }})

            def on_done(name, path):
                captured['name'], captured['path'] = name, path
                done.set()

            mm = self.manager()
            mm.prefetch("v", on_done=on_done)
            self.assertTrue(done.wait(timeout=30), "prefetch did not finish in time")

        self.assertEqual(captured['name'], "v")
        self.assertIsNotNone(captured['path'])

    def test_prefetch_callback_error_does_not_escape(self):
        payload = b"w" * 100
        with ServedDirectory() as srv:
            url = srv.publish("voice.onnx", payload)
            self.write_manifest({"v": {
                "filename": "voice.onnx", "url": url, "sha256": sha256_of(payload),
            }})
            mm = self.manager()
            t = mm.prefetch("v", on_done=lambda *a: 1 / 0)   # callback raises
            t.join(timeout=30)
            self.assertFalse(t.is_alive(), "prefetch thread should terminate cleanly")


class TestSummary(ModelManagerTestBase):
    def test_summary_reports_cached_models(self):
        payload = b"cached bytes"
        self.write_manifest({"v": {
            "filename": "voice.onnx", "url": "http://127.0.0.1:1/x",
            "sha256": sha256_of(payload),
        }})
        self.model_dir.mkdir(parents=True, exist_ok=True)
        (self.model_dir / "voice.onnx").write_bytes(payload)

        s = self.manager().summary()
        self.assertIn("v", s['cached_models'])
        self.assertGreaterEqual(s['disk_used_mb'], 0)
        self.assertGreater(s['disk_free_mb'], 0)


if __name__ == '__main__':
    unittest.main()
