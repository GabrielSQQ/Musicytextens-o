"""Portable checks for dependency integrity and safe installer staging."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fetch_dependencies", ROOT / "scripts" / "fetch_dependencies.py")
FETCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FETCH)
BUILD_SPEC = importlib.util.spec_from_file_location("build_windows", ROOT / "scripts" / "build_windows.py")
BUILD = importlib.util.module_from_spec(BUILD_SPEC)
BUILD_SPEC.loader.exec_module(BUILD)


class DependencyBuildTests(unittest.TestCase):
    def test_extension_id_matches_manifest_public_key(self):
        manifest = json.loads((ROOT / "extension" / "manifest.json").read_text())
        self.assertEqual(BUILD.stable_extension_id(manifest["key"]), (ROOT / "extension" / "extension-id.txt").read_text().strip())

    def test_lock_uses_immutable_version_urls_and_hashes(self):
        lock = json.loads((ROOT / "installer" / "dependencies.lock.json").read_text())
        self.assertEqual(lock["platform"], "windows-x86_64")
        for item in lock["artifacts"]:
            self.assertRegex(item["sha256"], r"^[a-f0-9]{64}$")
            self.assertNotIn("/latest/", item["url"])
            self.assertTrue(item["url"].startswith("https://"))

    def test_cached_hash_must_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            data = b"verified test executable fixture"
            artifact = dict(name="fixture", url="https://github.com/yt-dlp/yt-dlp/releases/download/2026.10.26/yt-dlp.exe", sha256=hashlib.sha256(data).hexdigest(), filename="fixture.exe", kind="file")
            target = folder / "fixture.exe"
            target.write_bytes(data)
            with patch.object(FETCH.urllib.request, "urlopen", side_effect=AssertionError("network must not be used for matching cache")):
                self.assertEqual(FETCH.download(artifact, folder), target)
            target.write_bytes(b"corrupted")
            with patch.object(FETCH.urllib.request, "urlopen", side_effect=OSError("no test network")):
                with self.assertRaises(OSError):
                    FETCH.download(artifact, folder)
            self.assertFalse(target.exists())

    def test_url_source_restricted(self):
        artifact = dict(name="fixture", url="https://untrusted.invalid/tools.exe", sha256="0" * 64, filename="fixture.exe", kind="file")
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                FETCH.download(artifact, Path(temporary))

    def test_extracts_only_known_tools_and_license(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            archive = folder / "fixture.zip"
            tools = folder / "tools"
            licenses = folder / "licenses"
            tools.mkdir()
            licenses.mkdir()
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("release/bin/ffmpeg.exe", b"fixture ffmpeg")
                zipped.writestr("release/bin/evil.exe", b"do not extract")
                zipped.writestr("release/licenses/LICENSE.txt", b"license fixture")
            FETCH.extract_tool(archive, dict(name="ffmpeg", kind="zip", members={"bin/ffmpeg.exe": "ffmpeg.exe"}), tools, licenses)
            self.assertEqual((tools / "ffmpeg.exe").read_bytes(), b"fixture ffmpeg")
            self.assertFalse((tools / "evil.exe").exists())
            self.assertEqual((licenses / "ffmpeg/release/licenses/LICENSE.txt").read_bytes(), b"license fixture")

    def test_zip_traversal_is_rejected(self):
        for bad_path in ("../LICENSE.txt", "..\\LICENSE.txt", "C:/outside/LICENSE.txt", "C:\\outside\\LICENSE.txt", "\\\\server\\share\\LICENSE.txt"):
            with self.subTest(bad_path=bad_path), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                archive = folder / "fixture.zip"
                tools = folder / "tools"
                licenses = folder / "licenses"
                tools.mkdir()
                licenses.mkdir()
                with zipfile.ZipFile(archive, "w") as zipped:
                    zipped.writestr(bad_path, "must not escape")
                with self.assertRaises(ValueError):
                    FETCH.extract_tool(archive, dict(name="fixture", kind="zip", members={}), tools, licenses)
                self.assertFalse((folder.parent / "LICENSE.txt").exists())

    def test_uninstaller_does_not_recursively_delete_preferences_folder(self):
        script = (ROOT / "installer" / "OperaMusicDownloader.iss").read_text()
        section = script.split("[UninstallDelete]", 1)[1].split("[Code]", 1)[0]
        self.assertNotIn("filesandordirs", section.lower())
        self.assertIn('Type: dirifempty; Name: "{localappdata}\\OperaMusicDownloader"', section)
        self.assertIn("state-corrompido.json", section)
        self.assertIn("host.lock", section)


if __name__ == "__main__":
    unittest.main()
