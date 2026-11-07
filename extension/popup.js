"use strict";
const $ = id => document.getElementById(id);
let current = null;
function request(type,payload = {}) {
  return chrome.runtime.sendMessage({type,payload}).then(response => {if (!response?.ok) throw new Error(response?.error || "O pedido falhou."); return response.result;});
}
function error(message) {$("error").hidden=!message; $("error").textContent=message || "";}
function node(tag,className,text) {const el=document.createElement(tag); if(className)el.className=className; if(text)el.textContent=text; return el;}
function speed(value) {if(!Number.isFinite(value)||value<=0)return ""; return value>1048576 ? `${(value/1048576).toFixed(1)} MB/s` : `${(value/1024).toFixed(0)} KB/s`;}
function jobCard(job) {
  const card=node("article",`job ${job.status}`); card.dataset.jobId=job.id;
  const top=node("div","job-top");const info=node("div","job-info");info.append(node("p","job-title",job.title || "Vídeo do YouTube"),node("p","job-subtitle",[job.channel,(job.format || "mp3").toUpperCase(),job.format === "mp4" ? `até ${job.quality}p` : job.format === "mp3" ? `${job.quality} kbps` : ""].filter(Boolean).join(" · ")));top.append(info);card.append(top);
  if(OMD.active.has(job.status)) {
    const cancel=node("button","cancel","×");cancel.title="Cancelar download";cancel.setAttribute("aria-label","Cancelar download");cancel.onclick=()=>action("cancel",{jobId:job.id});top.append(cancel);
    const status=node("div","job-status");const amount=Number.isFinite(job.progress)?Math.max(0,Math.min(100,job.progress)):null;
    status.append(node("span","",OMD.status[job.status] || job.status),node("span","",[speed(job.speed),amount===null?"":`${Math.floor(amount)}%`].filter(Boolean).join(" · ")));
    const track=node("div","progress");track.setAttribute("role","progressbar");track.setAttribute("aria-label","Progresso do download");track.setAttribute("aria-valuemin","0");track.setAttribute("aria-valuemax","100");if(amount!==null)track.setAttribute("aria-valuenow",String(amount));const fill=node("span","progress-fill");fill.style.width=`${amount || 0}%`;track.append(fill);card.append(status,track);
  } else {
    card.append(node("p","job-subtitle",OMD.status[job.status] || job.status));
    if(job.error)card.append(node("p","job-error",job.error));
    const actions=node("div","job-actions");
    if(job.status==="completed") {const open=node("button","text-button","Abrir pasta ↗");open.onclick=()=>action("open_folder",{jobId:job.id});actions.append(open);}
    if(["error","cancelled"].includes(job.status)) {const retry=node("button","text-button","Tentar novamente");retry.onclick=()=>{if(confirm("Você continua tendo autorização para baixar e salvar este conteúdo?"))action("download",{url:job.url,title:job.title,channel:job.channel,thumbnail:job.thumbnail,format:job.format,quality:job.quality,authorized:true});};actions.append(retry);}
    card.append(actions);
  }
  return card;
}
function render(state) {
  current=state;
  const connected=!!state.connection?.connected;
  $("connection").className=`connection ${connected?"connected":"disconnected"}`;
  $("connection-label").textContent=connected?"Aplicativo auxiliar conectado":"Aplicativo auxiliar desconectado";
  $("connection").title=state.connection?.error || "";
  $("reconnect").hidden=connected;
  if(!connected && state.connection?.error)error(state.connection.error);else error("");
  const jobs=state.jobs || [];
  const active=jobs.filter(job=>OMD.active.has(job.status));
  const history=jobs.filter(job=>!OMD.active.has(job.status)).slice().reverse().slice(0,20);
  $("queue-count").textContent=`${active.length} ${active.length===1?"na fila":"na fila"}`;
  $("queue").replaceChildren(...active.map(jobCard));$("empty").hidden=active.length>0;
  $("history").replaceChildren(...history.map(jobCard));$("history-section").hidden=history.length===0;
  const settings=state.settings || {};
  $("folder").textContent=settings.folderMode==="ask"?"Sempre perguntar onde salvar":settings.folderMode==="default"?settings.defaultFolder || "Defina uma pasta nas configurações":settings.lastFolder || "A pasta será escolhida no próximo download";
}
async function action(type,payload) {error("");try {const result=await request(type,payload);if(result?.cancelled)error("Seleção de pasta cancelada.");await refresh();}catch(e){error(e.message);}}
async function refresh() {try {render(await request("get_state"));}catch(e){error(e.message);}}
chrome.runtime.onMessage.addListener(message=>{if(message?.event==="state")render(message.data);});
$("settings").onclick=()=>chrome.runtime.openOptionsPage();$("reconnect").onclick=refresh;
$("clear-history").onclick=()=>action("clear_history");
// Cached values only populate labels. A fresh native response decides connection status.
chrome.storage.local.get("snapshot").then(data=>{if(!current && data.snapshot)render({...data.snapshot,connection:{connected:false,error:""}});});
refresh();
