"use strict";
const $ = id => document.getElementById(id);
let current = null;
let pendingSettings = {};
let writes = Promise.resolve();
function request(type,payload = {}) {
  return chrome.runtime.sendMessage({type,payload}).then(response => {if (!response?.ok) throw new Error(response?.error || "O pedido falhou."); return response.result;});
}
function error(message) {$("error").hidden=!message; $("error").textContent=message || "";}
function node(tag,className,text) {const el=document.createElement(tag); if(className)el.className=className; if(text)el.textContent=text; return el;}
function speed(value) {if(!Number.isFinite(value)||value<=0)return ""; return value>1048576 ? `${(value/1048576).toFixed(1)} MB/s` : `${(value/1024).toFixed(0)} KB/s`;}
function jobCard(job) {
  const card=node("article",`job ${job.status}`); card.dataset.jobId=job.id;
  const top=node("div","job-top");const info=node("div","job-info");info.append(node("p","job-title",job.title || "Vídeo do YouTube"),node("p","job-subtitle",[job.channel,(job.format || "mp3").toUpperCase(),job.format === "mp4" ? (job.status === "completed" && Number.isInteger(job.actualHeight) ? `${job.actualHeight}p` : `até ${job.quality}p`) : job.format === "mp3" ? `${job.quality} kbps` : ""].filter(Boolean).join(" · ")));top.append(info);card.append(top);
  if(OMD.active.has(job.status)) {
    const cancel=node("button","cancel","×");cancel.title="Cancelar download";cancel.setAttribute("aria-label","Cancelar download");cancel.onclick=()=>action("cancel",{jobId:job.id});top.append(cancel);
    const status=node("div","job-status");const amount=Number.isFinite(job.progress)?Math.max(0,Math.min(100,job.progress)):null;
    status.append(node("span","",OMD.status[job.status] || job.status),node("span","",[speed(job.speed),amount===null?"":`${Math.floor(amount)}%`].filter(Boolean).join(" · ")));
    const track=node("div","progress");track.setAttribute("role","progressbar");track.setAttribute("aria-label","Progresso do download");track.setAttribute("aria-valuemin","0");track.setAttribute("aria-valuemax","100");if(amount!==null)track.setAttribute("aria-valuenow",String(amount));const fill=node("span","progress-fill");fill.style.width=`${amount || 0}%`;track.append(fill);card.append(status,track);
  } else {
    card.append(node("p","job-subtitle",OMD.status[job.status] || job.status));
    if(job.error)card.append(node("p","job-error",job.error));
    if(job.resultNote)card.append(node("p","job-result-note",job.resultNote));
    const actions=node("div","job-actions");
    if(job.status==="completed") {const open=node("button","text-button","Abrir pasta ↗");open.onclick=()=>action("open_folder",{jobId:job.id});actions.append(open);}
    if(["error","cancelled"].includes(job.status)) {const retry=node("button","text-button","Tentar novamente");retry.onclick=()=>action("download",{url:job.url,title:job.title,channel:job.channel,thumbnail:job.thumbnail});actions.append(retry);}
    card.append(actions);
  }
  return card;
}
function renderSettings(settings) {
  const format=settings.defaultFormat === "mp4"?"mp4":"mp3";
  $("default-folder").textContent=settings.defaultFolder || "Configure uma pasta de destino na extensão.";
  $("default-format").value=format;
  const quality=$("default-quality");
  const values=format === "mp4"?[360,720,1080]:[128,192,320];
  if(quality.dataset.format !== format){quality.replaceChildren(...values.map(value=>{const option=node("option","",format === "mp4"?`Até ${value}p`:`${value} kbps`);option.value=value;return option;}));quality.dataset.format=format;}
  const configured=format === "mp4"?settings.mp4Quality:settings.mp3Quality;
  quality.value=String(values.includes(configured)?configured:format === "mp4"?720:320);
  $("authorized-downloads").checked=settings.authorizedDownloads === true;
  $("open-folder").checked=settings.openFolder === true;
  $("quality-note").textContent=format === "mp4"?"Usa a melhor resolução disponível até o limite escolhido. O resultado informa ajustes de resolução.":"Converter para 320 kbps não melhora a qualidade do áudio original.";
  $("download-label").textContent=`Baixar ${format.toUpperCase()}`;
  $("empty-title").textContent=current?.connection?.compatible && settings.defaultFolder && settings.authorizedDownloads === true?"Tudo pronto para o próximo download":"Configure e comece a baixar";
}
function render(state) {
  current=state;
  const connected=!!state.connection?.connected;
  const compatible=connected && !!state.connection?.compatible;
  $("connection").className=`connection ${compatible?"connected":"disconnected"}`;
  $("connection-label").textContent=compatible?"Aplicativo auxiliar conectado":connected?"Atualize o aplicativo auxiliar":"Aplicativo auxiliar desconectado";
  $("connection").title=state.connection?.error || "";
  $("reconnect").hidden=compatible;
  if(state.connection?.error)error(state.connection.error);else error("");
  for(const id of ["default-format","default-quality","authorized-downloads","open-folder","pick-folder"])$(id).disabled=!compatible;
  renderSettings({...state.settings,...pendingSettings});
  const jobs=state.jobs || [];
  const active=jobs.filter(job=>OMD.active.has(job.status));
  const history=jobs.filter(job=>!OMD.active.has(job.status)).slice().reverse().slice(0,20);
  $("queue-count").textContent=`${active.length} na fila`;
  $("queue").replaceChildren(...active.map(jobCard));$("empty").hidden=active.length>0;
  $("history").replaceChildren(...history.map(jobCard));$("history-section").hidden=history.length===0;
}
function savePatch(patch) {
  pendingSettings={...pendingSettings,...patch};renderSettings({...current?.settings,...pendingSettings});
  $("save-status").textContent="Salvando preferências…";
  writes=writes.catch(()=>{}).then(()=>request("settings",patch)).then(settings=>{
    for(const [key,value]of Object.entries(patch))if(pendingSettings[key]===value)delete pendingSettings[key];
    if(current)current={...current,settings};renderSettings({...settings,...pendingSettings});
    $("save-status").textContent=Object.keys(pendingSettings).length?"Salvando preferências…":"Preferências salvas. Os próximos downloads usarão estas opções.";
  }).catch(e=>{for(const [key,value]of Object.entries(patch))if(pendingSettings[key]===value)delete pendingSettings[key];if(current)renderSettings({...current.settings,...pendingSettings});$("save-status").textContent="Não foi possível salvar as preferências.";error(e.message);});
  return writes;
}
async function action(type,payload) {error("");try {await request(type,payload);await refresh();}catch(e){error(e.message);}}
async function refresh() {try {render(await request("get_state"));}catch(e){error(e.message);}}
chrome.runtime.onMessage.addListener(message=>{if(message?.event==="state")render(message.data);});
$("reconnect").onclick=refresh;$("clear-history").onclick=()=>action("clear_history");
$("default-format").addEventListener("change",event=>savePatch({defaultFormat:event.target.value}));
$("default-quality").addEventListener("change",event=>savePatch({[$("default-format").value === "mp4"?"mp4Quality":"mp3Quality"]:Number(event.target.value)}));
$("authorized-downloads").addEventListener("change",event=>{if(event.isTrusted)savePatch({authorizedDownloads:event.target.checked});});
$("open-folder").addEventListener("change",event=>{if(event.isTrusted)savePatch({openFolder:event.target.checked});});
$("pick-folder").addEventListener("click",async event=>{
  if(!event.isTrusted)return;
  $("pick-folder").disabled=true;$("save-status").textContent="Escolha a pasta na janela do Windows.";
  try{const result=await request("pick_folder");$("save-status").textContent=result.cancelled?"Seleção cancelada. Sua pasta anterior foi mantida.":"Pasta de destino salva.";await refresh();}
  catch(e){error(e.message);}finally{$("pick-folder").disabled=!current?.connection?.compatible;}
});
// Native storage is authoritative. A fresh native response loads preferences on every opening.
refresh();
