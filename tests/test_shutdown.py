"""A browser closing during explicit folder configuration must not save afterward."""
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "native-app"))
from app import Application


class NoToolsNeeded:
    def require(self):
        pass

    def snapshot(self):
        return {}


class ShutdownTests(unittest.TestCase):
    def test_browser_closes_before_native_picker_returns(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            entered, released = threading.Event(), threading.Event()
            errors = []

            def picker(_):
                entered.set()
                released.wait(timeout=3)
                return str(folder)

            app = Application(folder / "state", tools=NoToolsNeeded(), picker=picker, music_folder=lambda: "")

            def request():
                try:
                    app.dispatch("pick_folder", {})
                except Exception as exc:
                    errors.append(exc)

            thread = threading.Thread(target=request)
            thread.start()
            self.assertTrue(entered.wait(timeout=2))
            app.close()
            released.set()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(app.snapshot()["jobs"], [])
            self.assertEqual(app.snapshot()["settings"]["defaultFolder"], "")
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], ValueError)
            self.assertEqual(list(folder.glob("*.mp3")), [])
            with self.assertRaises(ValueError):
                app.enqueue({"url": "https://youtu.be/abcdefghijk"})
