(() => {
  "use strict";
  if (globalThis.__omdContentInstalled) return;
  globalThis.__omdContentInstalled = true;
  const CARD = "ytd-video-renderer,ytd-grid-video-renderer,ytd-rich-item-renderer,yt-lockup-view-model,ytmusic-responsive-list-item-renderer,ytmusic-two-row-item-renderer";
  const DISCONNECTED = "Aplicativo auxiliar desconectado. Abra a extensão para verificar.";
  let scheduled = false;
  let preferences = {defaultFormat:"mp3",mp3Quality:320,mp4Quality:720};
  const records = new Map();
  const downloads = new Map();
  const seenJobs = new Map();
  const style = document.createElement("style");
  style.id = "omd-page-style";
  style.textContent = `.omd-download-control{display:inline-flex!important;flex-wrap:wrap;align-items:center;max-width:100%;gap:0 8px;vertical-align:middle}.omd-download-button{display:inline-flex!important;align-items:center;gap:6px;background:#24242c!important;border:1px solid #ff315866!important;color:#fff!important;border-radius:20px;padding:8px 13px!important;font:600 12px/1.2 Arial,sans-serif!important;cursor:pointer!important;margin:7px 6px 7px 0!important;white-space:nowrap;transition:background .15s;position:relative;z-index:1}.omd-download-button:hover:not(:disabled){background:#e72d51!important}.omd-download-button:disabled{cursor:wait!important;opacity:.75}.omd-download-button:focus-visible{outline:2px solid #ff3158;outline-offset:3px}.omd-download-button svg{width:15px;height:15px;flex:none;pointer-events:none}.omd-download-feedback{font:11px/1.4 Arial,sans-serif!important;color:#b9b9c6!important;max-width:300px;overflow-wrap:anywhere}.omd-download-feedback.error{color:#ff6987!important}.omd-download-feedback.completed{color:#52c99d!important}.omd-download-button[data-state=pending] svg{animation:omd-pulse 1s infinite}@keyframes omd-pulse{50%{opacity:.3}}@media(prefers-reduced-motion:reduce){.omd-download-button svg{animation:none!important}}`;
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
  function request(type,payload={}) {
    return chrome.runtime.sendMessage({type,payload}).then(response=>{if(!response?.ok)throw new Error(response?.error || DISCONNECTED);return response.result;});
  }
  function paint(button,record) {
    const info=record.dataGetter();
    const state=info?downloads.get(info.url):null;
    const phase=state?.status || "idle";
    const busy=phase === "pending" || OMD.active.has(phase);
    const labels={pending:"Preparando…",queued:"Na fila…",preparing:"Preparando…",downloading:Number.isFinite(state?.progress)?`Baixando ${Math.floor(state.progress)}%` : "Baixando…",converting:"Convertendo…",completed:"Salvo ✓",error:"Tentar novamente",cancelled:"Cancelado"};
    const label=labels[phase] || `Baixar ${preferences.defaultFormat === "mp4"?"MP4":"MP3"}`;
    const span=button.querySelector(".omd-button-label");if(span.textContent!==label)span.textContent=label;
    button.disabled=busy;button.dataset.state=phase;button.setAttribute("aria-busy",String(busy));button.setAttribute("aria-label",label+" com Opera Music Downloader");
    const feedback=phase === "error"?state.error:phase === "completed"?(state.resultNote || "Arquivo salvo com sucesso!"):phase === "cancelled"?"Download cancelado.":"";
    if(record.feedback.textContent!==feedback)record.feedback.textContent=feedback;
    record.feedback.className=`omd-download-feedback ${phase}`;
  }
  function paintAll() {
    for(const [button,record]of records){if(!button.isConnected){records.delete(button);continue;}paint(button,record);}
  }
  function terminal(url,state) {
    if(state.resetTimer)clearTimeout(state.resetTimer);
    state.resetTimer=setTimeout(()=>{if(downloads.get(url)===state){downloads.delete(url);paintAll();}},5000);
  }
  function update(data) {
    if(data?.preferences){preferences={...preferences,...data.preferences};}
    if(data?.connection?.connected === false) {
      for(const [url,state]of downloads)if(state.status === "pending" || OMD.active.has(state.status)) {
        if(state.resetTimer)clearTimeout(state.resetTimer);
        const failed={status:"error",error:DISCONNECTED};downloads.set(url,failed);terminal(url,failed);
      }
      seenJobs.clear();paintAll();return;
    }
    for(const job of data?.jobs || []) {
      if(!job.url)continue;
      const fingerprint=JSON.stringify([job.status,job.progress,job.error,job.resultNote]);
      if(seenJobs.get(job.id)===fingerprint)continue;
      seenJobs.set(job.id,fingerprint);
      const existing=downloads.get(job.url);
      if(existing?.resetTimer)clearTimeout(existing.resetTimer);
      const state={status:job.status,progress:job.progress,jobId:job.id,error:job.error,resultNote:job.resultNote};
      downloads.set(job.url,state);
      if(!OMD.active.has(job.status))terminal(job.url,state);
    }
    if(seenJobs.size>300){const keep=[...seenJobs].slice(-200);seenJobs.clear();for(const [key,value]of keep)seenJobs.set(key,value);}
    paintAll();
  }
  function button(dataGetter,context) {
    const wrap=document.createElement("span");wrap.className="omd-download-control";
    const b=document.createElement("button");b.type="button";b.className="omd-download-button";b.dataset.omdContext=context;
    b.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5"/></svg><span class="omd-button-label"></span>';
    const feedback=document.createElement("span");feedback.className="omd-download-feedback";feedback.setAttribute("role","status");feedback.setAttribute("aria-live","polite");
    const record={dataGetter,feedback};records.set(b,record);wrap.append(b,feedback);paint(b,record);
    b.addEventListener("click",async event=>{
      event.preventDefault();event.stopPropagation();
      if(!event.isTrusted)return;
      const info=dataGetter();if(!info)return;
      const previous=downloads.get(info.url);if(previous?.status === "pending" || OMD.active.has(previous?.status))return;
      if(previous?.resetTimer)clearTimeout(previous.resetTimer);
      const state={status:"pending"};downloads.set(info.url,state);paintAll();
      try {
        const result=await request("download",info);
        // A very short job may already have completed via a live event before its acknowledgement.
        const current=downloads.get(info.url);
        if(current===state){state.status="queued";state.jobId=result.jobId;paintAll();}
      }catch(error){
        const failed={status:"error",error:error.message || DISCONNECTED};downloads.set(info.url,failed);terminal(info.url,failed);paintAll();
      }
    });
    return wrap;
  }
  function scan() {
    scheduled=false;
    for(const card of document.querySelectorAll(CARD)) {
      if(card.parentElement?.closest(CARD))continue;
      const existing=card.querySelector("button.omd-download-button");
      if(!cardData(card)){existing?.closest(".omd-download-control")?.remove();continue;}
      if(existing)continue;
      const music=card.tagName.toLowerCase().startsWith("ytmusic");
      const target=card.querySelector("#meta,#metadata,#details,.yt-lockup-metadata-view-model__text-container,.flex-columns,.details") || card;
      target.append(button(()=>cardData(card),music?"music":"result"));
    }
    const valid=OMD.videoUrl(location.href);
    const existing=document.querySelector("button.omd-download-button[data-omd-context='watch']");
    if(!valid)existing?.closest(".omd-download-control")?.remove();
    else if(!existing){const target=document.querySelector("ytd-watch-metadata #top-level-buttons-computed,ytd-watch-metadata #actions,#menu-container #top-level-buttons-computed,ytmusic-player-bar .middle-controls,ytmusic-player-bar .content-info-wrapper");if(target)target.append(button(watchData,"watch"));}
    paintAll();
  }
  function schedule(){if(!scheduled){scheduled=true;setTimeout(scan,180);}}
  const observer=new MutationObserver(changes=>{
    if(changes.some(change=>{const node=change.target.nodeType===Node.ELEMENT_NODE?change.target:change.target.parentElement;return !node?.closest?.(".omd-download-control,#omd-page-style");}))schedule();
  });
  observer.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:["href"]});
  for(const event of ["yt-navigate-finish","yt-page-data-updated","ytmusic-navigate-finish","popstate"])window.addEventListener(event,schedule);
  chrome.runtime.onMessage.addListener(message=>{if(message?.event === "content_state")update(message.data);});
  scan();
  request("get_state").then(update).catch(()=>{});
})();
