"""Native pipe closure must not abort Python or truncate framed messages."""
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "native-app"))
from messaging import Writer, read_message


class ShortWriteStream:
    def __init__(self):
        self.bytes = bytearray()

    def write(self, value):
        count = min(len(value), 3)
        self.bytes.extend(value[:count])
        return count

    def flush(self):
        pass


class BrokenPipeTests(unittest.TestCase):
    def test_partial_writes_produce_one_complete_frame(self):
        stream = ShortWriteStream()
        message = {"id": "áudio", "ok": True, "result": {"title": "Música autorizada"}}
        Writer(stream).send(message)
        framed = io.BytesIO(stream.bytes)
        self.assertEqual(read_message(framed), message)
        self.assertIsNone(read_message(framed))

    def test_zero_or_none_write_closes_writer(self):
        for result in (0, None):
            class StoppedStream:
                def write(self, value):
                    return result

                def flush(self):
                    raise AssertionError("A broken stream must not be flushed")

            with self.subTest(result=result):
                writer = Writer(StoppedStream())
                writer.send({"id": "closed"})
                self.assertTrue(writer.closed)

    def test_broken_stdout_with_open_stdin_exits_cleanly(self):
        # Simulate the browser losing its receiving pipe while an async progress
        # event is emitted and the reader still waits for another request.
        source = r'''
import sys
import threading
import main

class FakeApplication:
    def __init__(self, folder, emit):
        timer = threading.Timer(0.3, lambda: emit({"event": "state", "data": {}}))
        timer.daemon = True
        timer.start()

    def close(self):
        pass

main.Application = FakeApplication
raise SystemExit(main.main(sys.argv[1:]))
'''
        extension_id = (ROOT / "extension/extension-id.txt").read_text().strip()
        with tempfile.TemporaryDirectory() as temporary:
            process = subprocess.Popen(
                [sys.executable, "-c", source, "chrome-extension://" + extension_id + "/", "--state-dir", temporary],
                cwd=ROOT / "native-app",
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                process.stdout.close()
                process.wait(timeout=6)
                errors = process.stderr.read().decode("utf-8", errors="replace")
                self.assertEqual(process.returncode, 0, errors)
                self.assertEqual(errors, "")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=3)
                process.stdin.close()
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
