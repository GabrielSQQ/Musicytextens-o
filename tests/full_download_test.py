"""Real one-click flow: popup preferences -> YouTube fixture -> native host -> media.

The test host injects ONLY a local authorized media source and a logged picker.
Production URL validation, queue, persistence, yt-dlp and FFmpeg remain real.
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
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]


class QuietHTTP(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def wait_until(condition, message, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = condition()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Este harness usa um registro Native Messaging Linux isolado.")
    from playwright.sync_api import sync_playwright
    extension = ROOT / "extension"
    extension_id = (extension / "extension-id.txt").read_text().strip()
    with tempfile.TemporaryDirectory(prefix="omd-oneclick-") as temporary:
        base = Path(temporary)
        media = base / "Músicas do João & testes [2026]"
        media.mkdir()
        source = base / "source"
        source.mkdir()
        for filename, frequency in (("Canção autorizada.wav", 440), ("Segundo tom.wav", 660)):
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=1.3", "-c:a", "pcm_s16le", str(source / filename)], check=True, timeout=30)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0xff3158:s=640x360:r=12:d=1.3", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.3", "-c:v", "libx264", "-threads", "2", "-preset", "ultrafast", "-c:a", "aac", "-shortest", "-f", "hls", "-hls_time", "1", "-hls_list_size", "0", str(source / "rendition.m3u8")], check=True, timeout=30)
        (source / "master.m3u8").write_text('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=720000,RESOLUTION=640x360,CODECS="avc1.42c01e,mp4a.40.2"\nrendition.m3u8\n')
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHTTP, directory=str(source)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}/"
        source_map = {"abcdefghijk": origin + quote("Canção autorizada.wav"), "ZYXWVUTSRQP": origin + quote("Segundo tom.wav"), "12345678901": origin + "master.m3u8"}
        picker_log = base / "picker.json"
        state_path = base / "state" / "state.json"
        shim = base / "test_host.py"
        shim.write_text("\n".join([
            "import sys, json, time", "from pathlib import Path", f"sys.path.insert(0, {str(ROOT / 'native-app')!r})",
            "import main", "from app import Application", "from downloader import Runner", "from urllib.parse import parse_qs, urlsplit",
            f"sources = {source_map!r}", f"picker_log = Path({str(picker_log)!r})",
            "def picker(_):", "    previous = json.loads(picker_log.read_text()) if picker_log.exists() else {'calls': 0}",
            "    picker_log.write_text(json.dumps({'calls': previous['calls'] + 1}))", "    time.sleep(0.5)", f"    return {str(media)!r}",
            "def test_application(folder, emit):",
            "    return Application(folder, emit=emit, picker=picker, runner_factory=lambda tools, callback, cancelled: Runner(tools, callback, cancelled, source_resolver=lambda url: sources[parse_qs(urlsplit(url).query)['v'][0]]))",
            "main.Application = test_application", "raise SystemExit(main.main())", "",
        ]), encoding="utf-8")
        wrapper = base / "native-host"
        wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " " + shlex.quote(str(shim)) + ' "$@" --state-dir ' + shlex.quote(str(base / "state")) + "\n")
        wrapper.chmod(0o700)
        manifests = base / "profile" / "NativeMessagingHosts"
        manifests.mkdir(parents=True)
        (manifests / "com.opera_music_downloader.json").write_text(json.dumps({"name": "com.opera_music_downloader", "description": "Isolated one-click test host", "path": str(wrapper), "type": "stdio", "allowed_origins": [f"chrome-extension://{extension_id}/"]}))

        def state():
            try:
                return json.loads(state_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, ValueError):
                return {"jobs": [], "settings": {}}

        def completed(count):
            jobs = state()["jobs"]
            return jobs if len(jobs) == count and all(j["status"] == "completed" for j in jobs) else None

        def select_value(page, selector, value):
            # Native keyboard input yields trusted change events even on extension pages.
            field = page.locator(selector)
            values = field.locator("option").evaluate_all("options => options.map(o=>o.value)")
            field.focus()
            field.press("Home")
            for _ in range(values.index(str(value))):
                field.press("ArrowDown")
            field.press("Enter")

        records = []
        try:
            with sync_playwright() as playwright:
                def launch():
                    return playwright.chromium.launch_persistent_context(str(base / "profile"), executable_path=str(args.browser), headless=True, args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}", "--no-sandbox"])

                context = launch()
                popup = context.new_page()
                popup.goto(f"chrome-extension://{extension_id}/popup.html")
                popup.get_by_text("Aplicativo auxiliar conectado", exact=True).wait_for(timeout=15000)
                assert popup.locator("#default-format").input_value() == "mp3"
                assert popup.locator("#default-quality").input_value() == "320"
                popup.locator("#pick-folder").click()
                wait_until(picker_log.exists, "O pedido explícito de seleção não chegou ao host.")
                popup.close()  # Real native dialogs commonly close the browser action popup.
                wait_until(lambda: state()["settings"].get("defaultFolder") == str(media), "A pasta não foi salva depois de fechar o popup.")
                popup = context.new_page()
                popup.goto(f"chrome-extension://{extension_id}/popup.html")
                popup.get_by_text("Aplicativo auxiliar conectado", exact=True).wait_for(timeout=15000)
                popup.locator("#authorized-downloads").check()
                wait_until(lambda: state()["settings"].get("authorizedDownloads") is True, "A autorização única não foi salva.")
                popup.close()
                page = context.new_page()
                cards = [("a", "abcdefghijk"), ("b", "ZYXWVUTSRQP"), ("c", "12345678901")]
                fixture = '<!doctype html><html lang="pt-BR"><body>' + ''.join(f'<ytd-video-renderer id="card-{name}"><div id="meta"><a id="video-title" href="/watch?v={video}">Mídia autorizada {name}</a><ytd-channel-name>Canal de teste</ytd-channel-name></div></ytd-video-renderer>' for name, video in cards) + '</body></html>'
                context.route("https://**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=fixture) if route.request.url.startswith("https://www.youtube.com/results") else route.abort())
                page.goto("https://www.youtube.com/results?search_query=fixture")

                def download(card, expected_count, expected_format, expected_quality):
                    button = page.locator(f"#card-{card} button.omd-download-button")
                    button.get_by_text(f"Baixar {expected_format.upper()}", exact=True).wait_for(timeout=10000)
                    button.click()  # The only click needed for this download.
                    assert page.locator("#omd-dialog-host,[role=dialog]").count() == 0
                    jobs = wait_until(lambda: completed(expected_count), "O fluxo real de download não terminou.", timeout=45)
                    job = jobs[-1]
                    assert job["format"] == expected_format and job["quality"] == expected_quality, job
                    output = Path(job["path"])
                    assert output.parent == media and output.is_file(), job
                    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,codec_type,bit_rate,height:format=duration,size", "-of", "json", str(output)], check=True, capture_output=True, text=True)
                    result = json.loads(probe.stdout)
                    audio = next(stream for stream in result["streams"] if stream["codec_type"] == "audio")
                    if expected_format == "mp3":
                        assert audio["codec_name"] == "mp3" and int(audio["bit_rate"]) == expected_quality * 1000
                    else:
                        assert audio["codec_name"] == "aac"
                        assert next(stream for stream in result["streams"] if stream["codec_type"] == "video")["height"] == 360
                        assert job.get("actualHeight") == 360 and "360" in job.get("resultNote", ""), job
                    assert json.loads(picker_log.read_text())["calls"] == 1
                    records.append({"filename": output.name, "format": job["format"], "requestedQuality": job["quality"], "actualHeight": job.get("actualHeight"), "resultNote": job.get("resultNote", ""), "probe": result})

                download("a", 1, "mp3", 320)
                popup = context.new_page()
                popup.goto(f"chrome-extension://{extension_id}/popup.html")
                popup.get_by_text("Aplicativo auxiliar conectado", exact=True).wait_for(timeout=15000)
                select_value(popup, "#default-format", "mp4")
                wait_until(lambda: state()["settings"].get("defaultFormat") == "mp4", "Formato MP4 não foi salvo.")
                assert popup.locator("#default-quality").input_value() == "720"
                popup.close()
                download("c", 2, "mp4", 720)
                popup = context.new_page()
                popup.goto(f"chrome-extension://{extension_id}/popup.html")
                popup.get_by_text("Aplicativo auxiliar conectado", exact=True).wait_for(timeout=15000)
                select_value(popup, "#default-format", "mp3")
                wait_until(lambda: state()["settings"].get("defaultFormat") == "mp3", "Formato MP3 não foi salvo.")
                select_value(popup, "#default-quality", "192")
                wait_until(lambda: state()["settings"].get("mp3Quality") == 192, "Nova qualidade não foi salva.")
                popup.close()
                download("b", 3, "mp3", 192)
                context.close()

                context = launch()
                popup = context.new_page()
                popup.goto(f"chrome-extension://{extension_id}/popup.html")
                popup.get_by_text("Aplicativo auxiliar conectado", exact=True).wait_for(timeout=15000)
                response = popup.evaluate("() => chrome.runtime.sendMessage({type:'get_state'})")
                settings = response["result"]["settings"]
                assert settings["defaultFolder"] == str(media) and settings["authorizedDownloads"] is True
                assert settings["defaultFormat"] == "mp3" and settings["mp3Quality"] == 192 and settings["mp4Quality"] == 720
                assert len(response["result"]["jobs"]) == 3
                assert json.loads(picker_log.read_text())["calls"] == 1
                context.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    report = {"ok": True, "version": json.loads((extension / "manifest.json").read_text())["version"], "realExtension": True, "realNativeMessaging": True, "realYtDlpFfmpegAndFfprobe": True, "singleTrustedClickPerDownload": True, "noYouTubeModal": True, "pickerCallsOnlyInExplicitSettings": 1, "folderSavedAfterPopupCloses": True, "standingAuthorizationSavedOnce": True, "sequentialDownloads": 3, "popupClosedDuringDownloads": True, "liveFormatChangeWithoutPageReload": True, "unicodeAndSpaceDestination": True, "settingsAndHistoryPersistAfterBrowserRestart": True, "localSyntheticSourceInjectedOnlyInTestHost": True, "nativeWindowsFolderDialogTested": False, "liveYouTubeTested": False, "outputs": records}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
