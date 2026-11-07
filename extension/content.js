(() => {
  "use strict";
  if (globalThis.__omdContentInstalled) return;
  globalThis.__omdContentInstalled = true;
  const CARD = "ytd-video-renderer,ytd-grid-video-renderer,ytd-rich-item-renderer,yt-lockup-view-model,ytmusic-responsive-list-item-renderer,ytmusic-two-row-item-renderer";
  let scheduled = false;
  let dialogHost = null;
  const style = document.createElement("style");
  style.id = "omd-page-style";
  style.textContent = `.omd-download-button{display:inline-flex!important;align-items:center;gap:6px;background:#24242c!important;border:1px solid #ff315866!important;color:#fff!important;border-radius:20px;padding:8px 13px!important;font:600 12px/1.2 Arial,sans-serif!important;cursor:pointer!important;margin:7px 6px 7px 0!important;white-space:nowrap;transition:background .15s,transform .15s;position:relative;z-index:1}.omd-download-button:hover{background:#e72d51!important;transform:translateY(-1px)}.omd-download-button:focus-visible{outline:2px solid #ff3158;outline-offset:3px}.omd-download-button svg{width:15px;height:15px;flex:none;pointer-events:none}`;
  (document.head || document.documentElement).append(style);
  function text(root,selectors) {
    for (const selector of selectors) { const value = root.querySelector(selector)?.textContent?.trim(); if (value) return value; }
    return "";
  }
  function cardData(card) {
    let link;
    for (const a of card.querySelectorAll("a[href]")) { if (OMD.videoUrl(a.href)) { link = a; if (a.id === "video-title" || a.classList.contains("yt-simple-endpoint")) break; } }
    if (!link) return null;
    const url = OMD.videoUrl(link.href);
    const title = text(card,["#video-title","h3",".yt-lockup-metadata-view-model__title",".title", ".ytmusic-responsive-list-item-renderer.title"]) || link.getAttribute("title") || link.textContent?.trim() || "Vídeo do YouTube";
    const channel = text(card,["#channel-name a","ytd-channel-name",".yt-content-metadata-view-model__metadata-row", ".secondary-flex-columns .yt-formatted-string", ".subtitle"]);
    return {url,title,channel,thumbnail:OMD.thumbnail(card.querySelector("img")?.src)};
  }
  function watchData() {
    const url = OMD.videoUrl(location.href);
    if (!url) return null;
    const title = text(document,["ytd-watch-metadata h1","h1.ytd-watch-metadata","#title h1","ytmusic-player-bar .title", ".ytmusic-player-bar.title"]) || document.title.replace(/ - YouTube(?: Music)?$/, "");
    const channel = text(document,["ytd-watch-metadata ytd-channel-name a","#owner #channel-name a", "ytmusic-player-bar .byline", "ytmusic-player-bar .subtitle"]);
    const videoId = new URL(url).searchParams.get("v");
    return {url,title,channel,thumbnail:`https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`};
  }
  function button(dataGetter,context) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "omd-download-button"; b.dataset.omdContext = context;
    b.setAttribute("aria-label","Baixar MP3 com Opera Music Downloader");
    b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5"/></svg><span>Baixar MP3</span>';
    b.addEventListener("click", e => { e.preventDefault(); e.stopPropagation(); if (!e.isTrusted) return; const info = dataGetter(); if (info) openDialog(info); });
    return b;
  }
  function scan() {
    scheduled = false;
    for (const card of document.querySelectorAll(CARD)) {
      // Rich results may wrap another supported renderer; keep one button per item.
      if (card.parentElement?.closest(CARD)) continue;
      const existing = card.querySelector("button.omd-download-button");
      const info = cardData(card);
      if (!info) { existing?.remove(); continue; }
      if (existing) continue;
      const music = card.tagName.toLowerCase().startsWith("ytmusic");
      const target = card.querySelector("#meta,#metadata,#details,.yt-lockup-metadata-view-model__text-container,.flex-columns,.details") || card;
      target.append(button(() => cardData(card), music ? "music" : "result"));
    }
    const valid = OMD.videoUrl(location.href);
    const existing = document.querySelector("button.omd-download-button[data-omd-context='watch']");
    if (!valid) { existing?.remove(); return; }
    if (existing) return;
    const target = document.querySelector("ytd-watch-metadata #top-level-buttons-computed,ytd-watch-metadata #actions,#menu-container #top-level-buttons-computed,ytmusic-player-bar .middle-controls,ytmusic-player-bar .content-info-wrapper");
    if (target) target.append(button(watchData,"watch"));
  }
  function schedule() { if (!scheduled) { scheduled = true; setTimeout(scan,180); } }
  const observer = new MutationObserver(records => {
    if (records.some(record => {
      const node = record.target.nodeType === Node.ELEMENT_NODE ? record.target : record.target.parentElement;
      return !node?.closest?.(".omd-download-button,#omd-dialog-host,#omd-page-style");
    })) schedule();
  });
  observer.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:["href"]});
  for (const event of ["yt-navigate-finish","yt-page-data-updated","ytmusic-navigate-finish","popstate"]) window.addEventListener(event,schedule);
  scan();
  function request(type,payload = {}) {
    return chrome.runtime.sendMessage({type,payload}).then(response => {
      if (!response?.ok) throw new Error(response?.error || "Não foi possível falar com a extensão. Recarregue esta página.");
      return response.result;
    });
  }
  function openDialog(info) {
    dialogHost?.remove();
    const oldFocus = document.activeElement;
    const host = document.createElement("div"); host.id = "omd-dialog-host";
    dialogHost = host;
    const shadow = host.attachShadow({mode:"open"});
    shadow.innerHTML = `<style>
      :host{all:initial;position:fixed;inset:0;z-index:2147483647;color:#fff;font:14px/1.5 system-ui,sans-serif;color-scheme:dark}*{box-sizing:border-box}.overlay{position:absolute;inset:0;background:#000b;display:flex;align-items:center;justify-content:center;padding:18px;backdrop-filter:blur(5px)}.dialog{width:440px;max-width:100%;max-height:94vh;overflow:auto;background:#121216;border:1px solid #35353e;border-radius:22px;box-shadow:0 25px 100px #000a;padding:25px}header{display:flex;justify-content:space-between;align-items:center;color:#ff3158;font-size:11px;font-weight:800;letter-spacing:1.6px}button,select,input{font:inherit}button{cursor:pointer}#omd-close{background:none;border:0;color:#c2c2cd;font-size:25px;line-height:1}.media{display:flex;gap:15px;margin:24px 0}img{width:112px;height:72px;object-fit:cover;border-radius:10px;background:#1d1d24}.info{min-width:0}h2{font-size:17px;line-height:1.4;margin:0 0 6px;overflow-wrap:anywhere}.muted{color:#aaaab8;font-size:12px;margin:0}.fields{display:grid;grid-template-columns:1fr 1fr;gap:12px}label{display:block;font-size:12px;color:#c4c4d0}select{width:100%;background:#1d1d24;color:#fff;border:1px solid #383843;border-radius:10px;padding:11px;margin:6px 0 12px}.note{font-size:12px;color:#aaaab8;margin:3px 0 17px}.auth{display:flex;align-items:flex-start;gap:9px;background:#1d1d24;border-radius:10px;padding:12px;color:#ddd}.auth input{margin-top:3px;accent-color:#ff3158;flex:none}#omd-start{width:100%;border:0;border-radius:12px;background:#ff3158;color:#fff;padding:14px;font-weight:700;margin-top:18px}#omd-start:disabled{opacity:.4;cursor:default}#omd-message{min-height:22px;font-size:12px;color:#d6d6df;margin:12px 0 0;overflow-wrap:anywhere}#omd-message.error{color:#ff8ba0}button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid #ff7e96;outline-offset:3px}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
      </style><div class="overlay"><section class="dialog" role="dialog" aria-modal="true" aria-labelledby="omd-title"><header><span>OPERA MUSIC DOWNLOADER</span><button id="omd-close" aria-label="Fechar">×</button></header><div class="media"><img id="omd-thumbnail" alt=""><div class="info"><h2 id="omd-title"></h2><p class="muted" id="omd-channel"></p></div></div><div class="fields"><label>Formato<select id="omd-format"><option value="mp3">MP3 · áudio</option><option value="m4a">M4A · áudio</option><option value="opus">OPUS · áudio</option><option value="mp4">MP4 · vídeo</option></select></label><label id="omd-quality-label">Qualidade<select id="omd-quality"></select></label></div><p class="note" id="omd-quality-note">Converter para 320 kbps não melhora a qualidade do áudio original.</p><label class="auth"><input id="omd-authorized" type="checkbox"><span>Tenho autorização para baixar e salvar este conteúdo.</span></label><button id="omd-start" disabled>Escolher pasta e baixar</button><p id="omd-message" aria-live="polite">Verificando aplicativo auxiliar…</p></section></div>`;
    shadow.getElementById("omd-title").textContent = info.title;
    shadow.getElementById("omd-channel").textContent = info.channel || "YouTube";
    const image = shadow.getElementById("omd-thumbnail");
    image.addEventListener("error", () => { image.hidden = true; }, {once:true});
    if (info.thumbnail) image.src = info.thumbnail; else image.hidden = true;
    const format = shadow.getElementById("omd-format");
    const quality = shadow.getElementById("omd-quality");
    const start = shadow.getElementById("omd-start");
    const authorized = shadow.getElementById("omd-authorized");
    const message = shadow.getElementById("omd-message");
    let sending = false;
    let authorizationAccepted = false;
    function qualities() {
      quality.replaceChildren();
      const bestAudio = ["m4a","opus"].includes(format.value);
      for (const value of format.value === "mp4" ? [360,720,1080] : [128,192,320]) {
        if (bestAudio && value !== 192) continue;
        const option = document.createElement("option"); option.value = value; option.textContent = format.value === "mp4" ? `Até ${value}p` : `${value} kbps`;
        if (bestAudio) option.textContent = "Melhor disponível";
        quality.append(option);
      }
      quality.value = format.value === "mp4" ? "720" : "192";
      quality.disabled = bestAudio;
      shadow.getElementById("omd-quality-note").textContent = format.value === "mp4" ? "A resolução depende do vídeo disponível. Áudio e vídeo são mesclados automaticamente." : format.value === "mp3" ? "Converter para 320 kbps não melhora a qualidade do áudio original." : "Usa o melhor áudio disponível; o formato de origem pode exigir conversão.";
    }
    qualities(); format.addEventListener("change",qualities);
    authorized.addEventListener("change",event => {if (!event.isTrusted) return; authorizationAccepted = authorized.checked; start.disabled = !authorizationAccepted || sending;});
    function close() { host.remove(); if (dialogHost === host) dialogHost = null; oldFocus?.focus?.(); document.removeEventListener("keydown",keyHandler,true); }
    function keyHandler(event) {
      if (event.key === "Escape") { event.stopPropagation(); close(); }
      if (event.key === "Tab") {
        const focusable = [...shadow.querySelectorAll("button,select,input")].filter(el => !el.disabled);
        const index = focusable.indexOf(shadow.activeElement);
        if (event.shiftKey && index <= 0) { event.preventDefault(); focusable.at(-1)?.focus(); }
        else if (!event.shiftKey && index === focusable.length - 1) {event.preventDefault(); focusable[0]?.focus();}
      }
    }
    shadow.getElementById("omd-close").addEventListener("click",close);
    shadow.querySelector(".overlay").addEventListener("click",e => { if (e.target.className === "overlay") close(); });
    document.addEventListener("keydown",keyHandler,true);
    start.addEventListener("click",async event => {
      if (!event.isTrusted || !authorizationAccepted || !authorized.checked || sending) return;
      sending = true; start.disabled = true; message.className = ""; message.textContent = "Selecione a pasta na janela do Windows. Ela pode aparecer atrás do navegador.";
      try {
        const result = await request("download",{...info,format:format.value,quality:Number(quality.value),authorized:true});
        message.textContent = result?.cancelled ? "Seleção cancelada. Nenhum download foi iniciado." : "Adicionado à fila! Acompanhe o download no ícone da extensão.";
        if (!result?.cancelled) { start.textContent = "Download adicionado"; return; }
      } catch (error) {message.className="error"; message.textContent=error.message || "Recarregue a página para reconectar a extensão.";}
      finally { sending=false; if (start.textContent !== "Download adicionado") start.disabled=!authorized.checked; }
    });
    document.documentElement.append(host);
    shadow.getElementById("omd-close").focus();
    request("get_state").then(state => {
      if (!host.isConnected || sending) return;
      message.textContent = state.connection?.connected ? "Tudo pronto. O processamento acontece no seu computador." : state.connection?.error || "Aplicativo auxiliar indisponível. Confira a instalação.";
      if (state.settings?.folderMode !== "ask") start.textContent = "Baixar na pasta configurada";
      if (!state.connection?.connected) message.className="error";
    }).catch(error => {if (!sending) {message.className="error";message.textContent=error.message;}});
  }
})();
