"""v1.1 browser tests using synthetic YouTube DOM, never live media.

The extension mode loads the real unpacked MV3 extension with an isolated Linux
native-host configuration (helper offline). The injected mode uses the real UI
scripts and an explicit runtime TEST DOUBLE. It verifies requests/status/UI, not
media processing, Windows, or Opera GX. Separate integration tests cover media.

python tests/browser_test.py --executable /path/to/chrome [--mode injected]
Requires Python Playwright and Chromium with unpacked extension support.
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
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"
FIXTURES = ROOT / "tests" / "fixtures"
CONFIG: argparse.Namespace
RESULTS: list[dict] = []
VIDEO_A = "https://www.youtube.com/watch?v=abcdefghijk"
DISCONNECTED = "Aplicativo auxiliar desconectado. Abra a extensão para verificar."
FOLDER_ERROR = "Configure uma pasta de destino na extensão."
OLD_HOST = "Atualize o aplicativo auxiliar para a versão 1.1.0 ou posterior para baixar com um clique."

# ONLY --mode injected installs this TEST DOUBLE. Product files are unchanged.
RUNTIME_DOUBLE = r"""
(() => {
  const listeners=[];
  globalThis.__omdTestMessages=[];
  globalThis.__omdDownloadError=null;
  let number=0;
  const state={protocolVersion:2,capabilities:{oneClickDownloads:true},
    settings:{folderMode:'default',defaultFolder:['C:','Músicas de teste','Áudio & Vídeo'].join(String.fromCharCode(92)),lastFolder:'',openFolder:false,defaultFormat:'mp3',mp3Quality:320,mp4Quality:720,authorizedDownloads:false},
    jobs:[],tools:{},connection:{connected:true,compatible:true,error:''}};
  const copy=value=>JSON.parse(JSON.stringify(value));
  function contentState() {
    return {preferences:{defaultFormat:state.settings.defaultFormat,mp3Quality:state.settings.mp3Quality,mp4Quality:state.settings.mp4Quality,authorizedDownloads:state.settings.authorizedDownloads,destinationConfigured:!!state.settings.defaultFolder},connection:copy(state.connection),jobs:state.jobs.map(({id,url,status,progress,error,resultNote,actualHeight})=>({id,url,status,progress,error,resultNote,actualHeight}))};
  }
  function emit() {
    const popup=location.hostname==='omd-ui.test';
    for(const listener of listeners)listener({event:popup?'state':'content_state',data:popup?copy(state):contentState()},{id:'test-only'},()=>{});
  }
  globalThis.__omdState=state;
  globalThis.__omdSetPreferences=patch=>{Object.assign(state.settings,patch);emit();};
  globalThis.__omdSetConnection=patch=>{Object.assign(state.connection,patch);emit();};
  globalThis.__omdEmitJobs=jobs=>{state.jobs=copy(jobs);emit();};
  globalThis.chrome={runtime:{lastError:null,getURL:p=>'https://omd-ui.test/'+p,
    getManifest:()=>({version:'1.1.0'}),openOptionsPage:async()=>{},
    onMessage:{addListener:listener=>listeners.push(listener),removeListener:listener=>{const index=listeners.indexOf(listener);if(index>=0)listeners.splice(index,1);}},
    async sendMessage(message) {
      globalThis.__omdTestMessages.push(copy(message));
      const payload=message.payload||{};
      if(message.type==='get_state')return {ok:true,result:location.hostname==='omd-ui.test'?copy(state):contentState()};
      if(message.type==='ping')return {ok:true,result:{version:'1.1.0',protocolVersion:2,capabilities:{oneClickDownloads:true}}};
      if(message.type==='settings'){Object.assign(state.settings,payload);emit();return {ok:true,result:copy(state.settings)};}
      if(message.type==='pick_folder'){state.settings.defaultFolder=['D:','Coleção nova','Áudio & Vídeo'].join(String.fromCharCode(92));emit();return {ok:true,result:{path:state.settings.defaultFolder}};}
      if(message.type==='download') {
        await new Promise(resolve=>setTimeout(resolve,100));
        if(globalThis.__omdDownloadError)return {ok:false,error:globalThis.__omdDownloadError};
        const id='TEST-ONLY-'+(++number);
        state.jobs.push({id,url:payload.url,title:payload.title,channel:payload.channel,format:state.settings.defaultFormat,quality:state.settings.defaultFormat==='mp4'?state.settings.mp4Quality:state.settings.mp3Quality,status:'queued',progress:null,error:null});
        emit();return {ok:true,result:{jobId:id}};
      }
      if(message.type==='cancel'){const job=state.jobs.find(job=>job.id===payload.jobId);if(job)job.status='cancelled';emit();return {ok:true,result:{cancelled:true}};}
      if(message.type==='clear_history'){state.jobs=state.jobs.filter(job=>['queued','preparing','downloading','converting'].includes(job.status));emit();return {ok:true,result:{}};}
      if(message.type==='open_folder')return {ok:true,result:{opened:true}};
      return {ok:false,error:'Comando indisponível no TEST DOUBLE de interface.'};
    }},storage:{local:{get:async()=>({snapshot:copy(state)}),set:async()=>{},setAccessLevel:async()=>{}}}};
})();
"""


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if CONFIG.mode == "extension" and os.name == "nt":
            raise RuntimeError("O modo extension desta suíte usa isolamento de host Linux. No Windows, use injected e os testes nativos separados.")
        for name in ["manifest.json", "shared.js", "content.js", "popup.html", "popup.js"]:
            if not (EXTENSION / name).is_file():
                raise RuntimeError(f"Arquivo da extensão ausente: {name}")
        cls.playwright = sync_playwright().start()
        cls.profile = tempfile.TemporaryDirectory(prefix="omd-browser-")
        args = ["--no-sandbox"]
        if CONFIG.mode == "extension":
            args.extend([f"--disable-extensions-except={EXTENSION}", f"--load-extension={EXTENSION}"])
        launch = dict(user_data_dir=cls.profile.name, headless=not CONFIG.headed, args=args)
        if os.name != "nt":
            launch["env"] = {**os.environ, "XDG_CONFIG_HOME": str(Path(cls.profile.name) / "isolated-native-config")}
        if CONFIG.executable:
            launch["executable_path"] = CONFIG.executable
        else:
            launch["channel"] = "chromium"
        cls.context = cls.playwright.chromium.launch_persistent_context(**launch)
        cls.context.route("https://**/*", cls.serve_fixture)
        if CONFIG.mode == "injected":
            cls.context.add_init_script(RUNTIME_DOUBLE)
        if CONFIG.mode == "extension":
            cls.worker = cls.context.service_workers[0] if cls.context.service_workers else cls.context.wait_for_event("serviceworker", timeout=10000)
            cls.extension_id = cls.worker.url.split("/")[2]
            if cls.extension_id != (EXTENSION / "extension-id.txt").read_text().strip():
                raise AssertionError("A atualização alterou o ID estável da extensão.")
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
        elif CONFIG.mode == "injected" and u.hostname == "omd-ui.test":
            name = Path(u.path).name
            if name not in {"popup.html", "popup.js", "popup.css", "shared.js", "16.png", "32.png", "48.png", "128.png"}:
                route.abort()
                return
            source = EXTENSION / ("icons/" + name if name.endswith(".png") else name)
            mime = "text/html" if name.endswith(".html") else "text/javascript" if name.endswith(".js") else "text/css" if name.endswith(".css") else "image/png"
            route.fulfill(status=200, content_type=mime, body=source.read_bytes())
        else:
            route.abort()

    def setUp(self):
        self.start = time.monotonic()
        self.page = self.context.new_page()
        self.errors, self.dialogs = [], []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("dialog", lambda dialog: (self.dialogs.append(dialog.type), dialog.dismiss()))

    def tearDown(self):
        outcome = self._outcome
        skipped = any(test is self for test, _ in outcome.result.skipped)
        failed = any(test is self for test, _ in outcome.result.failures + outcome.result.errors)
        success = not failed and not skipped
        if not success and not skipped:
            self.save_screenshot(self._testMethodName)
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
            for name in ["shared.js", "content.js"]:
                self.page.evaluate((EXTENSION / name).read_text())
            self.page.evaluate("__omdSetPreferences({authorizedDownloads:true})")
        self.page.locator("button.omd-download-button").first.wait_for(timeout=8000)

    def open_popup(self):
        self.page.set_viewport_size({"width": 400, "height": 540})
        target = f"chrome-extension://{self.extension_id}/popup.html" if CONFIG.mode == "extension" else "https://omd-ui.test/popup.html"
        self.page.goto(target, wait_until="domcontentloaded")
        self.page.locator("#default-format").wait_for()

    def requests(self, kind="download"):
        return self.page.evaluate("kind=>__omdTestMessages.filter(message=>message.type===kind)", kind)

    def assert_no_configuration_flow(self):
        self.assertEqual(self.page.locator("#omd-dialog-host,[role=dialog]").count(), 0)
        self.assertEqual(self.dialogs, [])
        if CONFIG.mode == "injected":
            self.assertEqual(self.requests("pick_folder"), [])

    def require_double(self):
        if CONFIG.mode != "injected":
            self.skipTest("Requer TEST DOUBLE explícito de status/preferências; extension usa host offline.")

    def test_search_only_compatible_individual_videos(self):
        self.open_fixture("https://www.youtube.com/results?search_query=fixture")
        self.assertEqual(self.page.locator("button.omd-download-button").count(), 2)
        self.assertEqual(self.page.locator("#invalid-url button.omd-download-button").count(), 0)
        self.assertEqual(self.page.locator("ytd-playlist-renderer button.omd-download-button").count(), 0)
        expect(self.page.locator("#result-a .omd-button-label")).to_have_text("Baixar MP3")
        self.assertEqual(self.errors, [])

    def test_dynamic_scroll_mutations_do_not_duplicate_buttons(self):
        self.open_fixture("https://www.youtube.com/results?search_query=fixture")
        self.page.evaluate("""() => {
          const source=document.querySelector('#result-a');
          for(let i=0;i<18;i++) {
            const row=source.cloneNode(true);row.id='new-'+i;
            row.querySelectorAll('.omd-download-button,.omd-download-feedback').forEach(node=>node.remove());
            row.querySelector('#video-title').href='/watch?v='+String(i).padStart(11,'0');
            document.querySelector('#contents').append(row);
          }
          for(let i=0;i<100;i++)source.setAttribute('data-progress',String(i));
          window.dispatchEvent(new Event('yt-navigate-finish'));
        }""")
        expect(self.page.locator("button.omd-download-button")).to_have_count(20)
        self.page.wait_for_timeout(450)
        self.assertEqual(self.page.locator("#result-a button.omd-download-button").count(), 1)
        self.assertEqual(self.page.locator("span.omd-download-feedback").count(), 20)
        self.assertEqual(self.errors, [])

    def test_recycled_renderer_reads_current_metadata_without_modal(self):
        self.open_fixture("https://www.youtube.com/results?search_query=fixture")
        self.page.evaluate("""() => {
          const link=document.querySelector('#result-a #video-title');
          link.href='/watch?v=ZYXWVUTSRQP';link.textContent='Novo título após reciclagem';
          link.setAttribute('title','Novo título após reciclagem');
          window.dispatchEvent(new Event('yt-navigate-finish'));
        }""")
        self.page.wait_for_timeout(350)
        self.page.locator("#result-a button.omd-download-button").click()
        self.assert_no_configuration_flow()
        if CONFIG.mode == "injected":
            payload = self.requests()[0]["payload"]
            self.assertEqual(payload["url"], "https://www.youtube.com/watch?v=ZYXWVUTSRQP")
            self.assertEqual(payload["title"], "Novo título após reciclagem")
        else:
            expect(self.page.locator("#result-a .omd-download-feedback")).to_have_text(DISCONNECTED)
        self.assertEqual(self.page.locator("#result-a button.omd-download-button").count(), 1)
        self.assertEqual(self.errors, [])

    def test_trusted_one_click_uses_metadata_only_and_safe_title(self):
        self.open_fixture("https://www.youtube.com/results?search_query=fixture")
        pages_before = len(self.context.pages)
        self.page.locator("#result-b button.omd-download-button").click()
        self.assert_no_configuration_flow()
        if CONFIG.mode == "injected":
            payload = self.requests()[0]["payload"]
            self.assertEqual(set(payload), {"url", "title", "channel", "thumbnail"})
            self.assertIn("<img src=x onerror=alert(1)>", payload["title"])
            self.assertEqual(self.page.locator("img[onerror]").count(), 0)
            self.assertEqual(self.requests("settings"), [])
        else:
            expect(self.page.locator("#result-b .omd-download-feedback")).to_have_text(DISCONNECTED)
        self.assertEqual(len(self.context.pages), pages_before)
        self.save_screenshot("oneclick-feedback")
        self.assertEqual(self.errors, [])

    def test_synthetic_page_click_cannot_start_download(self):
        self.open_fixture("https://www.youtube.com/results?search_query=fixture")
        self.page.evaluate("document.querySelector('#result-a button.omd-download-button').click()")
        self.page.wait_for_timeout(200)
        self.assert_no_configuration_flow()
        expect(self.page.locator("#result-a .omd-button-label")).to_have_text("Baixar MP3")
        self.assertFalse(self.page.locator("#result-a button.omd-download-button").is_disabled())
        if CONFIG.mode == "injected":
            self.assertEqual(self.requests(), [])
        self.assertEqual(self.errors, [])

    def test_watch_and_spa_navigation_update_metadata(self):
        self.open_fixture(VIDEO_A)
        self.assertEqual(self.page.locator("button.omd-download-button[data-omd-context=watch]").count(), 1)
        self.page.evaluate("""() => {
          history.pushState({},'', '/watch?v=ZYXWVUTSRQP');
          document.querySelector('h1').textContent='Segundo vídeo por navegação dinâmica';
          document.querySelector('ytd-watch-flexy').setAttribute('video-id','ZYXWVUTSRQP');
          window.dispatchEvent(new Event('yt-navigate-finish'));
        }""")
        self.page.wait_for_timeout(350)
        self.page.locator("button.omd-download-button[data-omd-context=watch]").click()
        self.assert_no_configuration_flow()
        if CONFIG.mode == "injected":
            payload = self.requests()[0]["payload"]
            self.assertEqual(payload["url"], "https://www.youtube.com/watch?v=ZYXWVUTSRQP")
            self.assertEqual(payload["title"], "Segundo vídeo por navegação dinâmica")
        else:
            expect(self.page.locator(".omd-download-feedback")).to_have_text(DISCONNECTED)
        self.assertEqual(self.page.locator("button.omd-download-button[data-omd-context=watch]").count(), 1)
        self.assertEqual(self.errors, [])

    def test_music_list_one_click_injects_supported_track(self):
        self.open_fixture("https://music.youtube.com/search?q=fixture")
        self.assertEqual(self.page.locator("#music-a button.omd-download-button").count(), 1)
        self.assertEqual(self.page.locator("#music-invalid button.omd-download-button").count(), 0)
        self.page.locator("#music-a button.omd-download-button").click()
        self.assert_no_configuration_flow()
        if CONFIG.mode == "injected":
            self.assertEqual(self.requests()[0]["payload"]["title"], "Faixa sintética de teste")
        else:
            expect(self.page.locator("#music-a .omd-download-feedback")).to_have_text(DISCONNECTED)
        self.assertEqual(self.errors, [])

    def test_popup_central_settings_defaults_and_narrow_layout(self):
        self.open_popup()
        self.assertIn("Configurações de download", self.page.locator("body").inner_text())
        expect(self.page.locator("#default-format")).to_have_value("mp3")
        expect(self.page.locator("#default-quality")).to_have_value("320")
        self.assertEqual(self.page.locator("#default-quality option").evaluate_all("nodes=>nodes.map(node=>node.value)"), ["128", "192", "320"])
        self.assertFalse(self.page.locator("#authorized-downloads").is_checked())
        self.assertEqual(self.page.locator("#pick-folder").inner_text().strip(), "Alterar pasta")
        expect(self.page.locator("#empty-title")).to_have_text("Configure e comece a baixar")
        if CONFIG.mode == "extension":
            result = self.page.evaluate("chrome.runtime.sendMessage({type:'get_state'})")
            self.assertTrue(result["ok"])
            self.assertFalse(result["result"]["connection"]["connected"])
            self.assertIn("desconectado", self.page.locator("body").inner_text().lower())
        dimensions = self.page.evaluate("({viewport:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth})")
        self.assertLessEqual(dimensions["document"], dimensions["viewport"])
        self.assertLessEqual(dimensions["body"], dimensions["viewport"])
        self.page.locator("#authorized-downloads").scroll_into_view_if_needed()
        self.save_screenshot("popup-settings")
        self.assertEqual(self.errors, [])

    def test_live_format_progress_duplicate_and_terminal_reset(self):
        self.require_double()
        self.open_fixture("https://www.youtube.com/results?search_query=fixture")
        self.page.evaluate("__omdSetPreferences({defaultFormat:'mp4',mp4Quality:720})")
        expect(self.page.locator("#result-a .omd-button-label")).to_have_text("Baixar MP4")
        expect(self.page.locator("#result-b .omd-button-label")).to_have_text("Baixar MP4")
        self.page.locator("#result-a button.omd-download-button").dblclick()
        self.page.wait_for_function("__omdState.jobs.length===1")
        self.assertEqual(len(self.requests()), 1)
        self.assertTrue(self.page.locator("#result-a button.omd-download-button").is_disabled())
        self.assertFalse(self.page.locator("#result-b button.omd-download-button").is_disabled())
        self.page.locator("#result-b button.omd-download-button").click()
        self.page.wait_for_function("__omdState.jobs.length===2")
        self.assertEqual(len(self.requests()), 2)
        self.page.evaluate("() => __omdEmitJobs(__omdState.jobs.map((job,index)=>index===0?{...job,status:'downloading',progress:42}:job))")
        expect(self.page.locator("#result-a button.omd-download-button")).to_contain_text("42")
        self.save_screenshot("oneclick-progress")
        self.page.evaluate("() => __omdEmitJobs(__omdState.jobs.map((job,index)=>index===0?{...job,status:'completed',progress:100,resultNote:'Salvo em 360p; resolução disponível.',actualHeight:360}:job))")
        expect(self.page.locator("#result-a .omd-download-feedback")).to_contain_text("360p")
        expect(self.page.locator("#result-a .omd-button-label")).to_have_text("Baixar MP4", timeout=10000)
        self.assertFalse(self.page.locator("#result-a button.omd-download-button").is_disabled())
        self.page.evaluate("__omdSetConnection({connected:false,compatible:false,error:'Aplicativo auxiliar desconectado. Abra a extensão para verificar.'})")
        expect(self.page.locator("#result-b .omd-download-feedback")).to_have_text(DISCONNECTED)
        self.assertFalse(self.page.locator("#result-b button.omd-download-button").is_disabled())
        expect(self.page.locator("#result-b .omd-button-label")).to_have_text("Baixar MP4", timeout=10000)
        self.assertFalse(self.page.locator("#result-b button.omd-download-button").is_disabled())
        self.page.evaluate("""() => {
          __omdState.jobs=__omdState.jobs.map((job,index)=>index===1?{...job,status:'error',error:'Processo interrompido durante reinício.'}:job);
          __omdSetConnection({connected:true,compatible:true,error:''});
        }""")
        expect(self.page.locator("#result-b .omd-download-feedback")).to_have_text("Processo interrompido durante reinício.")
        self.assertFalse(self.page.locator("#result-b button.omd-download-button").is_disabled())
        self.assert_no_configuration_flow()
        self.assertEqual(self.errors, [])

    def test_error_messages_retry_and_old_host_guidance(self):
        self.require_double()
        self.open_fixture("https://www.youtube.com/results?search_query=fixture")
        button = self.page.locator("#result-a button.omd-download-button")
        for message in [FOLDER_ERROR, DISCONNECTED, OLD_HOST]:
            self.page.evaluate("message=>globalThis.__omdDownloadError=message", message)
            button.click()
            expect(self.page.locator("#result-a .omd-download-feedback")).to_have_text(message)
            expect(self.page.locator("#result-a .omd-button-label")).to_have_text("Baixar MP3", timeout=10000)
            self.assertFalse(button.is_disabled())
            self.assert_no_configuration_flow()
        self.page.evaluate("globalThis.__omdDownloadError=null")
        button.click()
        self.page.wait_for_function("__omdState.jobs.length===1")
        self.assertEqual(len(self.requests()), 4)
        self.assertEqual(self.errors, [])

    def test_popup_autosaves_preferences_explicit_picker_and_history_scroll(self):
        self.require_double()
        self.open_popup()
        self.page.locator("#default-format").select_option("mp4")
        expect(self.page.locator("#default-quality")).to_have_value("720")
        self.assertEqual(self.page.locator("#default-quality option").evaluate_all("nodes=>nodes.map(node=>node.value)"), ["360", "720", "1080"])
        self.page.locator("#default-quality").select_option("1080")
        self.page.wait_for_function("__omdState.settings.mp4Quality===1080")
        self.page.locator("#default-format").select_option("mp3")
        expect(self.page.locator("#default-quality")).to_have_value("320")
        self.page.locator("#default-quality").select_option("192")
        self.page.wait_for_function("__omdState.settings.mp3Quality===192")
        self.page.locator("#authorized-downloads").check()
        self.page.wait_for_function("__omdState.settings.authorizedDownloads===true")
        expect(self.page.locator("#empty-title")).to_have_text("Tudo pronto para o próximo download")
        self.page.locator("#pick-folder").click()
        expected_path = r"D:\Coleção nova\Áudio & Vídeo"
        expect(self.page.locator("#default-folder")).to_contain_text(expected_path)
        self.assertEqual(len(self.requests("pick_folder")), 1)
        self.assertEqual(self.page.evaluate("__omdState.settings.defaultFolder"), expected_path)
        self.page.evaluate("() => __omdEmitJobs(Array.from({length:24},(_,index)=>({id:'history-'+index,url:'https://www.youtube.com/watch?v=abcdefghijk',title:'Título muito longo '+('áudio com acentuação & espaços '.repeat(12)),channel:'Canal de teste',format:'mp4',quality:720,status:'completed',progress:100,actualHeight:360,resultNote:'Disponível em 360p.'})))")
        expect(self.page.locator("#history .job")).to_have_count(20)
        self.page.locator("#history .job").last.scroll_into_view_if_needed()
        dimensions = self.page.evaluate("({viewport:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth})")
        self.assertLessEqual(dimensions["document"], dimensions["viewport"])
        self.assertLessEqual(dimensions["body"], dimensions["viewport"])
        self.save_screenshot("popup-history-scroll")
        self.page.evaluate("message=>__omdSetConnection({connected:true,compatible:false,error:message})", OLD_HOST)
        expect(self.page.locator("#error")).to_have_text(OLD_HOST)
        for selector in ["#default-format", "#default-quality", "#authorized-downloads", "#pick-folder"]:
            self.assertTrue(self.page.locator(selector).is_disabled())
        self.page.locator("#connection").scroll_into_view_if_needed()
        self.save_screenshot("popup-old-host")
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
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BrowserTests))
    report = {"mode": CONFIG.mode, "browser": getattr(BrowserTests, "browser_version", None), "extension_id": getattr(BrowserTests, "extension_id", None), "synthetic_pages": True, "media_download_tested": False, "native_host_offline": CONFIG.mode == "extension", "runtime_test_double": CONFIG.mode == "injected", "live_youtube_tested": False, "opera_gx_tested": False, "windows_tested": False, "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped), "tests": RESULTS}
    if CONFIG.report:
        destination = Path(CONFIG.report)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
