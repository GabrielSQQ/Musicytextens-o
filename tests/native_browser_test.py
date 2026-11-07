"""Real Chromium extension -> real Python host stdio integration, isolated config.

Linux developer test; does not register a host in the user's normal browser.
Requires Playwright, a Chromium supporting --load-extension, and Python 3.12.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, required=True)
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright
    if sys.platform != "linux":
        parser.error("Este teste isolado usa o registro Linux; valide o instalador no Windows separadamente.")
    extension = ROOT / "extension"
    extension_id = (extension / "extension-id.txt").read_text().strip()
    with tempfile.TemporaryDirectory(prefix="omd-native-browser-") as temporary:
        base = Path(temporary)
        config = base / "config"
        data = base / "state"
        media = base / "media"
        media.mkdir()
        wrapper = base / "native-host"
        wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " " + shlex.quote(str(ROOT / "native-app/main.py")) + ' "$@" --state-dir ' + shlex.quote(str(data)) + "\n", encoding="utf-8")
        wrapper.chmod(0o700)
        host_manifest = {"name": "com.opera_music_downloader", "description": "OMD isolated integration test", "path": str(wrapper), "type": "stdio", "allowed_origins": [f"chrome-extension://{extension_id}/"]}
        for folder in (base / "profile" / "NativeMessagingHosts",):
            folder.mkdir(parents=True)
            (folder / "com.opera_music_downloader.json").write_text(json.dumps(host_manifest), encoding="utf-8")
        env = dict(os.environ, XDG_CONFIG_HOME=str(config))
        with sync_playwright() as playwright:
            def launch():
                return playwright.chromium.launch_persistent_context(str(base / "profile"), executable_path=str(args.browser), headless=True, env=env, args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}", "--no-sandbox"])

            context = launch()
            page = context.new_page()
            page.goto(f"chrome-extension://{extension_id}/popup.html")
            try:
                page.get_by_text("Aplicativo auxiliar conectado", exact=True).wait_for(timeout=5000)
            except Exception:
                print(page.locator("#error").inner_text(), file=sys.stderr)
                raise

            def request(command, payload=None):
                response = page.evaluate("m => chrome.runtime.sendMessage(m)", {"type": command, "payload": payload or {}})
                assert response["ok"], response
                return response["result"]

            assert request("ping")["version"] == "1.0.0"
            state = request("get_state")
            assert state["connection"]["connected"]
            assert state["jobs"] == []
            request("settings", {"folderMode": "default", "defaultFolder": str(media), "openFolder": False})
            assert request("get_state")["settings"]["defaultFolder"] == str(media)
            bad = page.evaluate("m => chrome.runtime.sendMessage(m)", {"type": "download", "payload": {"url": "http://127.0.0.1/private.wav", "format": "mp3", "quality": 192, "authorized": True}})
            assert not bad["ok"]
            assert request("get_state")["jobs"] == []
            request("clear_history")
            context.close()

            # Native process exits on EOF. The saved settings survive new browser/host.
            context = launch()
            page = context.new_page()
            page.goto(f"chrome-extension://{extension_id}/popup.html")
            try:
                page.get_by_text("Aplicativo auxiliar conectado", exact=True).wait_for(timeout=5000)
            except Exception:
                print(page.locator("#error").inner_text(), file=sys.stderr)
                raise
            state = request("get_state")
            assert state["settings"]["folderMode"] == "default"
            assert state["settings"]["defaultFolder"] == str(media)
            context.close()
        print(json.dumps({"ok": True, "realNativeMessaging": True, "fixedExtensionId": extension_id, "settingsPersistedAcrossBrowserRestart": True, "nonYouTubeUrlRejected": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
