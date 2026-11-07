"""Unit and process integration tests. No YouTube requests or copyrighted media."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import queue

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "native-app"))

from app import Application
from downloader import Cancelled, Runner, Tools, media_title, safe_filename, validate_url
from messaging import MAX_MESSAGE, ProtocolError, Writer, read_message
import main as host_main

VIDEO = "https://www.youtube.com/watch?v=abcdefghijk"


class StubTools:
    paths = {}

    def require(self):
        return None

    def snapshot(self):
        return {}


class FramingTests(unittest.TestCase):
    def test_multibyte_frame_byte_length_and_roundtrip(self):
        stream = io.BytesIO()
        Writer(stream).send({"id": "áç😀", "ok": True})
        raw = stream.getvalue()
        self.assertEqual(struct.unpack("<I", raw[:4])[0], len(raw) - 4)
        stream.seek(0)
        self.assertEqual(read_message(stream), {"id": "áç😀", "ok": True})
        self.assertIsNone(read_message(stream))

    def test_truncated_oversized_and_nonobject_messages(self):
        bad = [b"\x01", struct.pack("<I", MAX_MESSAGE + 1), struct.pack("<I", 5) + b"{}", struct.pack("<I", 2) + b"[]", struct.pack("<I", 0)]
        for data in bad:
            with self.subTest(data=data[:4]), self.assertRaises(ProtocolError):
                read_message(io.BytesIO(data))

    def test_concurrent_events_do_not_interleave(self):
        stream = io.BytesIO()
        writer = Writer(stream)
        threads = [threading.Thread(target=lambda n=n: [writer.send({"n": n, "i": i}) for i in range(40)]) for n in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        stream.seek(0)
        messages = []
        while (message := read_message(stream)) is not None:
            messages.append(message)
        self.assertEqual(len(messages), 160)
        self.assertEqual(len({(m["n"], m["i"]) for m in messages}), 160)


class ValidationTests(unittest.TestCase):
    def test_only_canonical_video_urls(self):
        for url in [VIDEO, "https://youtu.be/abcdefghijk?t=3", "https://music.youtube.com/watch?v=abcdefghijk&list=LL", "https://www.youtube.com/shorts/abcdefghijk"]:
            self.assertEqual(validate_url(url), VIDEO)
        for url in ["http://www.youtube.com/watch?v=abcdefghijk", "https://youtube.com.evil.test/watch?v=abcdefghijk", "https://www.youtube.com@127.0.0.1/watch?v=abcdefghijk", "https://user:pass@www.youtube.com/watch?v=abcdefghijk", "https://www.youtube.com:443/watch?v=abcdefghijk", "file:///tmp/video.mp4", "https://localhost/video.mp4", "https://www.youtube.com/playlist?list=LL", "https://www.youtube.com/watch?v=bad", VIDEO + "&v=12345678901", VIDEO + "\n"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_safe_unicode_reserved_and_long_filenames(self):
        self.assertEqual(safe_filename('João: Canção / ao vivo?'), "João Canção ao vivo")
        self.assertEqual(safe_filename("CON.txt"), "_CON.txt")
        self.assertEqual(safe_filename("nul"), "_nul")
        self.assertLessEqual(len(safe_filename("🎵" * 300).encode("utf-16-le")) // 2, 130)
        self.assertEqual(media_title({"title": "Vídeo", "channel": "Canal"}), "Vídeo")
        self.assertEqual(media_title({"title": "Vídeo", "artist": "Artista", "track": "Canção"}), "Artista - Canção")


class PublicationTests(unittest.TestCase):
    def test_collision_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "stage"
            source.write_bytes(b"new")
            (root / "Canção.mp3").write_bytes(b"keep")
            runner = Runner(StubTools(), lambda _: None, threading.Event())
            result = runner.publish(source, root, "Canção", "mp3")
            self.assertEqual(result.name, "Canção (2).mp3")
            self.assertEqual((root / "Canção.mp3").read_bytes(), b"keep")
            self.assertEqual(result.read_bytes(), b"new")

    def test_copy_fallback_cancellation_removes_owned_partial(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "stage"
            source.write_bytes(b"a" * 2_000_000)
            runner = Runner(StubTools(), lambda _: None, threading.Event())
            calls = 0

            def check():
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise Cancelled()

            with patch("downloader.os.link", side_effect=OSError("no hardlinks")), patch.object(runner, "check_cancelled", side_effect=check):
                with self.assertRaises(Cancelled):
                    runner.publish(source, root, "Parcial", "mp3")
            self.assertFalse((root / "Parcial.mp3").exists())
            self.assertEqual(source.stat().st_size, 2_000_000)

    def test_real_subprocess_cancellation(self):
        started = threading.Event()
        result = []
        runner = Runner(StubTools(), lambda _: None, threading.Event())

        def run():
            try:
                runner.run([sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(30)"], on_line=lambda _: started.set())
            except Exception as exc:
                result.append(exc)

        thread = threading.Thread(target=run)
        thread.start()
        self.assertTrue(started.wait(3), "process did not start")
        runner.cancel()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(result[0], Cancelled)
        self.assertIsNone(runner.process)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / "músicas"
        self.folder.mkdir()
        self.started = threading.Event()
        self.release = threading.Event()
        self.instances = []
        parent = self

        class ControlledRunner:
            def __init__(self, tools, emit, cancelled):
                self.emit, self.cancelled = emit, cancelled
                parent.instances.append(self)

            def cancel(self):
                self.cancelled.set()
                parent.release.set()

            def download(self, job, folder):
                parent.started.set()
                parent.release.wait(5)
                if self.cancelled.is_set():
                    raise Cancelled()
                path = folder / (job["id"] + ".mp3")
                path.write_bytes(b"queue fixture (not a media test)")
                return path

        self.app = Application(self.root / "data", tools=StubTools(), picker=lambda _: str(self.folder), runner_factory=ControlledRunner, folder_opener=lambda _: None)

    def tearDown(self):
        self.release.set()
        self.app.close()
        self.temp.cleanup()

    def payload(self, video=VIDEO):
        return {"url": video, "title": "Canção", "format": "mp3", "quality": 192, "authorized": True}

    def wait_status(self, job_id, expected):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            job = next(j for j in self.app.snapshot()["jobs"] if j["id"] == job_id)
            if job["status"] == expected:
                return job
            time.sleep(0.01)
        self.fail(f"job did not reach {expected}: {self.app.snapshot()}")

    def test_authorization_duplicate_active_cancel_retry_and_complete(self):
        bad = self.payload()
        bad["authorized"] = False
        with self.assertRaises(ValueError):
            self.app.dispatch("download", bad)
        job = self.app.dispatch("download", self.payload())["jobId"]
        self.assertTrue(self.started.wait(2))
        with self.assertRaisesRegex(ValueError, "já está na fila"):
            self.app.dispatch("download", self.payload())
        self.app.dispatch("cancel", {"jobId": job})
        self.wait_status(job, "cancelled")
        retry = self.app.dispatch("download", self.payload())["jobId"]
        done = self.wait_status(retry, "completed")
        self.assertTrue(Path(done["path"]).is_file())
        self.assertNotIn("_folder", done)

    def test_queued_cancel_does_not_start_or_remove_completed_files(self):
        first = self.app.enqueue(self.payload())["jobId"]
        self.assertTrue(self.started.wait(2))
        second = self.app.enqueue(self.payload("https://youtu.be/12345678901"))["jobId"]
        self.app.cancel(second)
        self.release.set()
        done = self.wait_status(first, "completed")
        self.wait_status(second, "cancelled")
        self.assertEqual(len(self.instances), 1)
        self.app.dispatch("clear_history", {})
        self.assertEqual(self.app.snapshot()["jobs"], [])
        self.assertTrue(Path(done["path"]).is_file())

    def test_settings_persist_and_invalid_path_is_rejected(self):
        with self.assertRaises(ValueError):
            self.app.dispatch("settings", {"folderMode": "default"})
        with self.assertRaises(ValueError):
            self.app.dispatch("settings", {"defaultFolder": "../relative"})
        self.app.dispatch("settings", {"folderMode": "default", "defaultFolder": str(self.folder), "openFolder": True})
        self.app.close()
        self.app = Application(self.root / "data", tools=StubTools(), picker=lambda _: self.fail("default folder should avoid picker"))
        self.assertEqual(self.app.choose_folder(), self.folder)
        self.assertTrue(self.app.snapshot()["settings"]["openFolder"])

    def test_interrupted_jobs_become_retryable_errors_on_restart(self):
        job = self.app.enqueue(self.payload())["jobId"]
        self.assertTrue(self.started.wait(2))
        # Simulate previous state before abrupt exit in an independent data dir.
        other = self.root / "restart"
        other.mkdir()
        (other / "state.json").write_text(json.dumps({"jobs": [{"id": "interrupted", "status": "converting"}], "settings": {}}))
        restored = Application(other, tools=StubTools())
        try:
            state = restored.snapshot()["jobs"][0]
            self.assertEqual(state["status"], "error")
            self.assertIn("tentar novamente", state["error"])
        finally:
            restored.close()


class HostProcessTests(unittest.TestCase):
    def test_ping_and_cancel_respond_while_folder_picker_is_blocked(self):
        extension_id = (ROOT / "extension" / "extension-id.txt").read_text().strip()
        in_read, in_write = os.pipe()
        out_read, out_write = os.pipe()
        stdin = os.fdopen(in_read, "rb", buffering=0)
        request_stream = os.fdopen(in_write, "wb", buffering=0)
        response_stream = os.fdopen(out_read, "rb", buffering=0)
        stdout = os.fdopen(out_write, "wb", buffering=0)
        picker_started, release_picker = threading.Event(), threading.Event()
        responses = queue.Queue()

        def picker(_):
            picker_started.set()
            release_picker.wait(4)
            return None

        def create_app(folder, emit):
            return Application(folder, emit=emit, tools=StubTools(), picker=picker)

        def read_responses():
            while (response := read_message(response_stream)) is not None:
                responses.put(response)

        reader = threading.Thread(target=read_responses, daemon=True)
        reader.start()
        result = []
        with tempfile.TemporaryDirectory() as temp, patch.object(host_main, "Application", side_effect=create_app), patch.object(host_main.sys, "stdin", SimpleNamespace(buffer=stdin)), patch.object(host_main.sys, "stdout", SimpleNamespace(buffer=stdout)):
            thread = threading.Thread(target=lambda: result.append(host_main.main([f"chrome-extension://{extension_id}/", "--state-dir", temp])))
            thread.start()
            writer = Writer(request_stream)
            try:
                writer.send({"id": "choose", "type": "download", "payload": {"url": VIDEO, "format": "mp3", "quality": 192, "authorized": True}})
                self.assertTrue(picker_started.wait(2))
                writer.send({"id": "ping", "type": "ping", "payload": {}})
                writer.send({"id": "cancel", "type": "cancel", "payload": {"jobId": "absent"}})
                self.assertEqual(responses.get(timeout=2)["id"], "ping")
                self.assertEqual(responses.get(timeout=2)["id"], "cancel")
                release_picker.set()
                response = responses.get(timeout=2)
                self.assertEqual(response["id"], "choose")
                self.assertTrue(response["result"]["cancelled"])
            finally:
                release_picker.set()
                request_stream.close()
                thread.join(5)
                stdout.close()
                reader.join(2)
                stdin.close()
                response_stream.close()
            self.assertFalse(thread.is_alive())
            self.assertEqual(result, [0])

    def test_real_host_native_framed_ping_and_origin_rejection(self):
        extension_id = (ROOT / "extension" / "extension-id.txt").read_text().strip()
        stream = io.BytesIO()
        writer = Writer(stream)
        writer.send({"id": "ping-1", "type": "ping", "payload": {}})
        writer.send({"id": "bad-1", "type": "settings", "payload": {"unexpected": True}})
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run([sys.executable, str(ROOT / "native-app" / "main.py"), f"chrome-extension://{extension_id}/", "--state-dir", temp], input=stream.getvalue(), capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            output = io.BytesIO(result.stdout)
            ping, bad = read_message(output), read_message(output)
            self.assertEqual(ping["id"], "ping-1")
            self.assertEqual(ping["result"]["version"], "1.0.0")
            self.assertFalse(bad["ok"])
            self.assertIsNone(read_message(output))
            denied = subprocess.run([sys.executable, str(ROOT / "native-app" / "main.py"), "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/", "--state-dir", temp], input=b"", capture_output=True, timeout=10)
            self.assertNotEqual(denied.returncode, 0)
            self.assertEqual(denied.stdout, b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
