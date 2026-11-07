"""Browser checks against synthetic YouTube DOM, with the real unpacked extension.

No YouTube media is downloaded by this suite. Page requests are fulfilled from
tests/fixtures; all other HTTPS requests are blocked. The optional injected mode
checks content-script DOM behavior with a clearly labelled runtime test double.
It does not count as extension or Native Messaging integration coverage.

Usage:
    python tests/browser_test.py --executable /path/to/chrome
    python tests/browser_test.py --mode injected --executable /usr/bin/chromium

Requires Python Playwright and a browser supporting unpacked MV3 extensions.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"
FIXTURES = ROOT / "tests" / "fixtures"
CONFIG: argparse.Namespace
RESULTS: list[dict] = []

# This double is used ONLY with --mode injected. Product files are not modified.
RUNTIME_DOUBLE = r"""
globalThis.__omdTestMessages = [];
globalThis.chrome = {runtime: {
  lastError: null,
  getURL: p => 'chrome-extension://test-only/' + p,
  onMessage: {addListener() {}, removeListener() {}},
  async sendMessage(message) {
    globalThis.__omdTestMessages.push(JSON.parse(JSON.stringify(message)));
    if (message.type === 'get_state') return {ok:true,result:{settings:{folderMode:'ask',defaultFolder:'',lastFolder:'',openFolder:false},jobs:[],tools:{},connection:{connected:true,error:''}}};
    if (message.type === 'ping') return {ok:true,result:{version:'1.0.0'}};
    if (message.type === 'download') return {ok:true,result:{jobId:'TEST-ONLY-NO-FILE'}};
    return {ok:false,error:'Comando indisponível neste teste isolado.'};
  }
}};
"""


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required = ["manifest.json", "shared.js", "content.js", "popup.html", "options.html"]
        missing = [name for name in required if not (EXTENSION / name).is_file()]
        if missing:
            raise RuntimeError(f"Arquivos da extensão ausentes: {missing}")
        cls.playwright = sync_playwright().start()
        cls.profile = tempfile.TemporaryDirectory(prefix="omd-browser-")
        args = ["--no-sandbox"]
        if CONFIG.mode == "extension":
            args.extend([f"--disable-extensions-except={EXTENSION}", f"--load-extension={EXTENSION}"])
        launch = dict(user_data_dir=cls.profile.name, headless=not CONFIG.headed, args=args)
        if CONFIG.executable:
            launch["executable_path"] = CONFIG.executable
        else:
            launch["channel"] = "chromium"
        cls.context = cls.playwright.chromium.launch_persistent_context(**launch)
        cls.context.route("https://**/*", cls.serve_fixture)
        cls.worker = None
        if CONFIG.mode == "extension":
            cls.worker = cls.context.service_workers[0] if cls.context.service_workers else cls.context.wait_for_event("serviceworker", timeout=10000)
            cls.extension_id = cls.worker.url.split("/")[2]
            expected_id = (EXTENSION / "extension-id.txt").read_text().strip()
            if cls.extension_id != expected_id:
                raise AssertionError(f"ID instável: {cls.extension_id}, esperado {expected_id}")
        cls.browser_version = cls.context.browser.version

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "context"):
            cls.context.close()
        if hasattr(cls, "profile"):
            cls.profile.cleanup()
        if hasattr(cls, "playwright"):
            cls.playwright.stop()

    @staticmethod
    def serve_fixture(route):
        u = urlparse(route.request.url)
        if route.request.resource_type == "document" and u.hostname in {"www.youtube.com", "music.youtube.com"}:
            name = "music" if u.hostname == "music.youtube.com" else "watch" if u.path == "/watch" else "search"
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=(FIXTURES / f"{name}.html").read_text())
        else:
            # Keep the browser entirely on local fixture content.
            route.abort()

    def setUp(self):
        self.start = time.monotonic()
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))

    def tearDown(self):
        outcome = getattr(self, "_outcome", None)
        skipped = bool(outcome and any(test is self for test, _ in outcome.result.skipped))
        success = bool(outcome and outcome.success and not skipped)
        if CONFIG.screenshot_dir and not success:
            destination = Path(CONFIG.screenshot_dir)
            destination.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(destination / f"{CONFIG.mode}-{self._testMethodName}.png"), full_page=True)
        RESULTS.append({"test": self._testMethodName, "mode": CONFIG.mode, "passed": success, "skipped": skipped, "seconds": round(time.monotonic() - self.start, 3), "page_errors": self.errors})
        self.page.close()

    def save_screenshot(self, name):
        if CONFIG.screenshot_dir:
            destination = Path(CONFIG.screenshot_dir)
            destination.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(destination / f"{CONFIG.mode}-{name}.png"), full_page=True)

    def open_fixture(self, url):
        self.page.goto(url, wait_until="domcontentloaded")
        if CONFIG.mode == "injected":
            self.page.evaluate(RUNTIME_DOUBLE)
            for filename in ["shared.js", "content.js"]:
                self.page.evaluate((EXTENSION / filename).read_text())
        self.page.locator("button.omd-download-button").first.wait_for(timeout=8000)

    def test_search_only_compatible_individual_videos(self):
        self.open_fixture("https://www.youtube.com/results?search_query=fixture")
        self.assertEqual(self.page.locator("button.omd-download-button").count(), 2)
        self.assertEqual(self.page.locator("#invalid-url button.omd-download-button").count(), 0)
        self.assertEqual(self.page.locator("ytd-playlist-renderer button.omd-download-button").count(), 0)
        self.assertEqual(self.page.locator("#result-a button.omd-download-button").inner_text().strip(), "Baixar MP3")
        self.assertEqual(self.errors, [])

    def test_dynamic_scroll_mutations_do_not_duplicate_buttons(self):
        self.open_fixture("https://www.youtube.com/results?search_query=fixture")
        self.page.evaluate("""() => {
          const source = document.querySelector('#result-a');
          for(let i=0;i<18;i++) {
            const row=source.cloneNode(true); row.id='new-'+i;
            row.querySelectorAll('button.omd-download-button').forEach(button=>button.remove());
            row.querySelector('#video-title').href='/watch?v=' + String(i).padStart(11,'0');
            document.querySelector('#contents').append(row);
          }
          for(let i=0;i<100;i++) source.setAttribute('data-progress',String(i));
        }""")
        self.page.wait_for_function("document.querySelectorAll('button.omd-download-button').length===20")
        self.page.evaluate("document.dispatchEvent(new Event('yt-navigate-finish'))")
        self.page.wait_for_timeout(700)
        self.assertEqual(self.page.locator("button.omd-download-button").count(), 20)
        self.assertEqual(self.page.locator("#result-a button.omd-download-button").count(), 1)
        self.assertEqual(self.errors, [])

    def test_recycled_renderer_reads_current_video(self):
        self.open_fixture("https://www.youtube.com/results?search_query=fixture")
        self.page.evaluate("""() => {
          const link=document.querySelector('#result-a #video-title');
          link.href='/watch?v=ZYXWVUTSRQP';link.textContent='Novo título após reciclagem';
          link.setAttribute('title','Novo título após reciclagem');
          document.dispatchEvent(new Event('yt-navigate-finish'));
        }""")
        self.page.wait_for_timeout(500)
        self.page.locator("#result-a button.omd-download-button").click()
        dialog = self.page.locator("#omd-dialog-host").get_by_role("dialog")
        dialog.wait_for()
        self.assertIn("Novo título após reciclagem", dialog.inner_text())
        self.assertEqual(self.page.locator("#result-a button.omd-download-button").count(), 1)
        self.assertEqual(self.errors, [])

    def test_modal_formats_authorization_and_safe_title(self):
        self.open_fixture("https://www.youtube.com/results?search_query=fixture")
        self.page.locator("#result-b button.omd-download-button").click()
        host = self.page.locator("#omd-dialog-host")
        dialog = host.get_by_role("dialog")
        dialog.wait_for()
        self.assertIn("<img src=x onerror=alert(1)>", dialog.inner_text())
        self.assertEqual(host.locator("img[onerror]").count(), 0)
        self.assertEqual(host.locator("#omd-format").input_value(), "mp3")
        self.assertEqual(host.locator("#omd-quality option").evaluate_all("nodes=>nodes.map(n=>n.value)"), ["128", "192", "320"])
        self.assertFalse(host.locator("#omd-authorized").is_checked())
        start = host.locator("#omd-start")
        if start.is_enabled():
            start.click()
            self.assertTrue(dialog.is_visible())
        host.locator("#omd-format").select_option("mp4")
        self.assertEqual(host.locator("#omd-quality option").evaluate_all("nodes=>nodes.map(n=>n.value)"), ["360", "720", "1080"])
        host.locator("#omd-format").select_option("mp3")
        host.locator("#omd-quality").select_option("320")
        host.locator("#omd-authorized").check()
        self.save_screenshot("download-dialog")
        if CONFIG.mode == "injected":
            start.click()
            self.page.wait_for_function("globalThis.__omdTestMessages.some(m=>m.type==='download')")
            requests = self.page.evaluate("globalThis.__omdTestMessages.filter(m=>m.type==='download')")
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]["payload"]["url"], "https://www.youtube.com/watch?v=lmnopqrstuv")
            self.assertEqual(requests[0]["payload"]["quality"], 320)
            self.assertIs(requests[0]["payload"]["authorized"], True)
        else:
            # A real download is intentionally not triggered from a fake video.
            self.page.keyboard.press("Escape")
        self.assertEqual(self.errors, [])

    def test_synthetic_page_click_cannot_authorize_download(self):
        self.open_fixture("https://www.youtube.com/results?search_query=fixture")
        self.page.evaluate("document.querySelector('#result-a button.omd-download-button').click()")
        self.page.wait_for_timeout(250)
        self.assertEqual(self.page.locator("#omd-dialog-host").count(), 0, "O JavaScript da página não deve abrir a interface de autorização.")
        self.page.locator("#result-a button.omd-download-button").click()
        host = self.page.locator("#omd-dialog-host")
        host.get_by_role("dialog").wait_for()
        self.save_screenshot("download-dialog-normal-title")
        self.page.evaluate("""() => {
          const shadow=document.querySelector('#omd-dialog-host').shadowRoot;
          const checkbox=shadow.querySelector('#omd-authorized');
          checkbox.checked=true;
          checkbox.dispatchEvent(new Event('change',{bubbles:true}));
          const start=shadow.querySelector('#omd-start');
          start.disabled=false;
          start.click();
        }""")
        self.page.wait_for_timeout(150)
        self.assertTrue(host.get_by_role("dialog").is_visible())
        if CONFIG.mode == "injected":
            self.assertEqual(self.page.evaluate("globalThis.__omdTestMessages.filter(m=>m.type==='download').length"), 0)
            # A trusted submit still needs a trusted authorization change.
            host.locator("#omd-start").click()
            self.assertEqual(self.page.evaluate("globalThis.__omdTestMessages.filter(m=>m.type==='download').length"), 0)
            host.locator("#omd-authorized").uncheck()
            host.locator("#omd-authorized").check()
            host.locator("#omd-start").click()
            self.page.wait_for_function("globalThis.__omdTestMessages.filter(m=>m.type==='download').length===1")
        self.assertEqual(self.errors, [])

    def test_watch_and_spa_navigation_update_video(self):
        self.open_fixture("https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(self.page.locator("button.omd-download-button[data-omd-context=watch]").count(), 1)
        self.page.evaluate("""() => {
          history.pushState({},'', '/watch?v=ZYXWVUTSRQP');
          document.querySelector('h1').textContent='Segundo vídeo por navegação dinâmica';
          document.querySelector('ytd-watch-flexy').setAttribute('video-id','ZYXWVUTSRQP');
          document.dispatchEvent(new Event('yt-navigate-finish'));
        }""")
        self.page.wait_for_timeout(600)
        self.page.locator("button.omd-download-button[data-omd-context=watch]").click()
        dialog = self.page.locator("#omd-dialog-host").get_by_role("dialog")
        dialog.wait_for()
        self.assertIn("Segundo vídeo por navegação dinâmica", dialog.inner_text())
        self.assertEqual(self.page.locator("button.omd-download-button[data-omd-context=watch]").count(), 1)
        self.assertEqual(self.errors, [])

    def test_music_list_injects_supported_track(self):
        self.open_fixture("https://music.youtube.com/search?q=fixture")
        self.assertEqual(self.page.locator("#music-a button.omd-download-button").count(), 1)
        self.assertEqual(self.page.locator("#music-invalid button.omd-download-button").count(), 0)
        self.page.locator("#music-a button.omd-download-button").click()
        dialog = self.page.locator("#omd-dialog-host").get_by_role("dialog")
        dialog.wait_for()
        self.assertIn("Faixa sintética de teste", dialog.inner_text())
        self.assertEqual(self.errors, [])

    def test_extension_pages_load_and_offline_state_is_clear(self):
        if CONFIG.mode != "extension":
            self.skipTest("Requer carregamento real da extensão.")
        self.page.set_viewport_size({"width": 400, "height": 650})
        self.page.goto(f"chrome-extension://{self.extension_id}/popup.html")
        self.page.locator("body").wait_for()
        result = self.page.evaluate("chrome.runtime.sendMessage({type:'get_state'})")
        self.assertTrue(result["ok"])
        self.assertIn("connection", result["result"])
        if not result["result"]["connection"]["connected"]:
            self.assertTrue(result["result"]["connection"]["error"])
        self.save_screenshot("popup-offline")
        self.page.goto(f"chrome-extension://{self.extension_id}/options.html")
        self.page.locator("body").wait_for()
        self.assertIn("pasta", self.page.locator("body").inner_text().lower())
        self.assertEqual(self.errors, [])


def main():
    global CONFIG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", default=os.environ.get("OMD_TEST_BROWSER"))
    parser.add_argument("--mode", choices=["extension", "injected"], default="extension")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--report")
    parser.add_argument("--screenshot-dir")
    CONFIG = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BrowserTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"mode": CONFIG.mode, "browser": getattr(BrowserTests, "browser_version", None), "extension_id": getattr(BrowserTests, "extension_id", None), "synthetic_pages": True, "live_youtube_tested": False, "opera_gx_tested": False, "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped), "tests": RESULTS}
    if CONFIG.report:
        destination = Path(CONFIG.report)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
