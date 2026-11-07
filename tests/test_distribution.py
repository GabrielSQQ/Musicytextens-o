"""Checks integration properties which would otherwise break native messaging."""
import base64
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.extension = ROOT / "extension"
        self.manifest = json.loads((self.extension / "manifest.json").read_text(encoding="utf-8"))

    def test_extension_identity_is_fixed(self):
        digest = hashlib.sha256(base64.b64decode(self.manifest["key"], validate=True)).hexdigest()[:32]
        extension_id = "".join(chr(97 + int(c, 16)) for c in digest)
        self.assertEqual(extension_id, (self.extension / "extension-id.txt").read_text().strip())

    def test_every_declared_resource_exists(self):
        paths = [self.manifest["background"]["service_worker"], self.manifest["action"]["default_popup"]]
        paths.extend(self.manifest.get("icons", {}).values())
        paths.append(self.manifest["options_ui"]["page"])
        for content in self.manifest["content_scripts"]:
            paths.extend(content.get("js", []))
            paths.extend(content.get("css", []))
        for name in paths:
            with self.subTest(name=name):
                self.assertTrue((self.extension / name).is_file(), name)

    def test_browser_privileges_stay_scoped(self):
        self.assertEqual(self.manifest["manifest_version"], 3)
        self.assertEqual(set(self.manifest["permissions"]), {"storage", "nativeMessaging", "notifications"})
        self.assertNotIn("externally_connectable", self.manifest)
        self.assertNotIn("<all_urls>", self.manifest.get("host_permissions", []))
        for content in self.manifest["content_scripts"]:
            for match in content["matches"]:
                self.assertTrue(match.startswith("https://"))
                self.assertIn(match, {"https://www.youtube.com/*", "https://youtube.com/*", "https://music.youtube.com/*", "https://m.youtube.com/*"})

    def test_dependency_lock_requires_pinned_https_hashes(self):
        lock = json.loads((ROOT / "installer/dependencies.lock.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(lock["artifacts"]), 3)
        for item in lock["artifacts"]:
            with self.subTest(name=item["name"]):
                self.assertTrue(item["url"].startswith("https://"))
                self.assertNotIn("/latest/", item["url"])
                self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
                self.assertTrue(item["version"])

    def test_extension_helper_and_installer_versions_match(self):
        native = (ROOT / "native-app/downloader.py").read_text(encoding="utf-8")
        installer = (ROOT / "installer/OperaMusicDownloader.iss").read_text(encoding="utf-8")
        native_version = re.search(r'^VERSION = "([^"]+)"', native, re.M).group(1)
        installer_version = re.search(r'^AppVersion=([^\r\n]+)', installer, re.M).group(1)
        self.assertEqual(self.manifest["version"], native_version)
        self.assertEqual(self.manifest["version"], installer_version)


if __name__ == "__main__":
    unittest.main()
