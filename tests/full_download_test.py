"""Trusted YouTube-fixture click -> MV3 -> native stdio -> real MP3.

Only the test host injects a local source resolver. Product URLs remain YouTube
only. Uses a configured destination; native Windows folder UI is not exercised.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


class QuietHTTP(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Este harness registra o host Linux em perfil isolado.")
    from playwright.sync_api import sync_playwright
    extension = ROOT / "extension"
    extension_id = (extension / "extension-id.txt").read_text().strip()
    with tempfile.TemporaryDirectory(prefix="omd-full-download-") as temporary:
        base = Path(temporary)
        media = base / "media"
        media.mkdir()
        source = base / "source"
        source.mkdir()
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "pcm_s16le", str(source / "Fonte autorizada.wav")], check=True, timeout=30)
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHTTP, directory=str(source)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        fixture_url = f"http://127.0.0.1:{server.server_port}/Fonte%20autorizada.wav"
        shim = base / "test_host.py"
        shim.write_text("\n".join([
            "import sys", "from pathlib import Path", f"sys.path.insert(0, {str(ROOT / 'native-app')!r})",
            "import main", "from app import Application", "from downloader import Runner",
            "def test_application(folder, emit):",
            f"    return Application(folder, emit=emit, runner_factory=lambda tools, callback, cancelled: Runner(tools, callback, cancelled, source_resolver=lambda _: {fixture_url!r}))",
            "main.Application = test_application", "raise SystemExit(main.main())", "",
        ]), encoding="utf-8")
        wrapper = base / "native-host"
        wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " " + shlex.quote(str(shim)) + ' "$@" --state-dir ' + shlex.quote(str(base / "state")) + "\n")
        wrapper.chmod(0o700)
        manifests = base / "profile" / "NativeMessagingHosts"
        manifests.mkdir(parents=True)
        (manifests / "com.opera_music_downloader.json").write_text(json.dumps({"name": "com.opera_music_downloader", "description": "Test host with local source only", "path": str(wrapper), "type": "stdio", "allowed_origins": [f"chrome-extension://{extension_id}/"]}))
        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(str(base / "profile"), executable_path=str(args.browser), headless=True, args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}", "--no-sandbox"])
                popup = context.new_page()
                popup.goto(f"chrome-extension://{extension_id}/popup.html")
                popup.get_by_text("Aplicativo auxiliar conectado", exact=True).wait_for(timeout=15000)
                result = popup.evaluate("payload => chrome.runtime.sendMessage({type:'settings',payload})", {"folderMode": "default", "defaultFolder": str(media), "openFolder": False})
                assert result["ok"], result
                popup.close()
                page = context.new_page()
                fixture = '<!doctype html><html lang="pt-BR"><head><title>Fonte autorizada de teste</title></head><body><ytd-video-renderer><div id="meta"><a id="video-title" href="/watch?v=abcdefghijk">Mídia sintética autorizada</a><ytd-channel-name>Canal de teste</ytd-channel-name></div></ytd-video-renderer></body></html>'
                context.route("https://**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=fixture) if route.request.url.startswith("https://www.youtube.com/results") else route.abort())
                page.goto("https://www.youtube.com/results?search_query=fixture")
                page.locator("button.omd-download-button").click()
                page.locator("#omd-dialog-host").locator("#omd-authorized").check()
                page.locator("#omd-dialog-host").locator("#omd-start").click()
                page.locator("#omd-dialog-host").get_by_text("Download adicionado", exact=True).wait_for(timeout=15000)
                # The popup remains closed during all processing.
                page.close()
                deadline = time.monotonic() + 30
                while not list(media.glob("*.mp3")) and time.monotonic() < deadline:
                    time.sleep(0.1)
                assert list(media.glob("*.mp3")), "A mídia não foi publicada enquanto o popup estava fechado."
                popup = context.new_page()
                popup.goto(f"chrome-extension://{extension_id}/popup.html")
                popup.locator("article.job.completed").wait_for(timeout=30000)
                state = popup.evaluate("() => chrome.runtime.sendMessage({type:'get_state'})")["result"]
                assert len(state["jobs"]) == 1, state
                job = state["jobs"][0]
                assert job["status"] == "completed", job
                output = Path(job["path"])
                assert output.parent == media and output.is_file()
                probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,codec_type,bit_rate:format=duration,size", "-of", "json", str(output)], check=True, capture_output=True, text=True)
                data = json.loads(probe.stdout)
                assert data["streams"][0]["codec_name"] == "mp3"
                assert data["streams"][0]["bit_rate"] == "192000"
                report = {"ok": True, "trustedContentButton": True, "realExtension": True, "realNativeMessaging": True, "realYtDlpFfmpegAndFfprobe": True, "popupClosedDuringProcessing": True, "localSyntheticSourceInjectedOnlyInTestHost": True, "nativeWindowsFolderDialogTested": False, "liveYouTubeTested": False, "outputFile": output.name, "probe": data}
                context.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
