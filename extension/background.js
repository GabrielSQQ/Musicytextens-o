"use strict";
importScripts("shared.js");
const HOST = "com.opera_music_downloader";
const DISCONNECTED = "Aplicativo auxiliar desconectado. Abra a extensão para verificar.";
const UPDATE = "Atualize o aplicativo auxiliar para a versão 1.1.0 ou posterior para baixar com um clique.";
const FOLDER = "Configure uma pasta de destino na extensão.";
const AUTH = "Confirme na extensão que você tem autorização para baixar o conteúdo.";
const GENERIC = "Não foi possível concluir o download. Abra a extensão para verificar.";
let port = null;
let snapshot = {protocolVersion:0, capabilities:{}, settings:{defaultFolder:"", lastFolder:"", folderMode:"default", defaultFormat:"mp3", mp3Quality:320, mp4Quality:720, authorizedDownloads:false, openFolder:false}, jobs:[], tools:{}};
let connection = {connected:false, compatible:false, error:DISCONNECTED, lastSeen:null};
const pending = new Map();
const completed = new Set();
const subscriptions = new Map();
const enqueuing = new Map();
const supportsOneClick = state => Number.isInteger(state?.protocolVersion) && state.protocolVersion >= 2 && state.capabilities?.oneClickDownloads === true;
// Full snapshots include local paths. Restrict them before reading or caching any state.
const restore = (async () => {
  await chrome.storage.local.setAccessLevel({accessLevel:"TRUSTED_CONTEXTS"});
  if (chrome.storage.session?.setAccessLevel) await chrome.storage.session.setAccessLevel({accessLevel:"TRUSTED_CONTEXTS"});
  const data = await chrome.storage.local.get(["snapshot","notified"]);
  if (data.snapshot) snapshot = data.snapshot;
  for (const id of data.notified || []) completed.add(id);
  const session = chrome.storage.session ? await chrome.storage.session.get("contentSubscriptions") : {};
  for (const [key,value] of Object.entries(session.contentSubscriptions || {})) {
    if (Number.isInteger(value.tabId) && Number.isInteger(value.frameId) && typeof value.documentKey === "string" && Array.isArray(value.jobIds)) subscriptions.set(key,{...value,jobIds:new Set(value.jobIds.filter(id=>typeof id === "string").slice(-100))});
  }
})();
function persistSubscriptions() {
  if (!chrome.storage.session) return;
  const records = Object.fromEntries([...subscriptions].map(([key,value])=>[key,{...value,jobIds:[...value.jobIds].slice(-100)}]));
  chrome.storage.session.set({contentSubscriptions:records}).catch(()=>{});
}
function subscribe(sender) {
  const frameId = Number.isInteger(sender.frameId) ? sender.frameId : 0;
  const key = `${sender.tab.id}:${frameId}`;
  const documentKey = sender.documentId || sender.url;
  let subscription = subscriptions.get(key);
  if (!subscription || subscription.documentKey !== documentKey) {
    subscription = {tabId:sender.tab.id,frameId,documentKey,documentId:sender.documentId || "",jobIds:new Set()};
    subscriptions.set(key,subscription);
    if (subscriptions.size > 200) subscriptions.delete(subscriptions.keys().next().value);
    persistSubscriptions();
  }
  return subscription;
}
function contentError(value) {return [DISCONNECTED,UPDATE,FOLDER,AUTH].includes(value) ? value : GENERIC;}
function resultNote(job) {
  // Derive a truthful bounded note without forwarding arbitrary host text or paths.
  return job.format === "mp4" && Number.isInteger(job.actualHeight) && job.actualHeight > 0 && job.actualHeight <= 4320 && Number.isInteger(job.quality) && job.actualHeight < job.quality ? `Vídeo salvo em ${job.actualHeight}p; resolução solicitada indisponível.` : "";
}
function contentState(subscription) {
  const settings = snapshot.settings || {};
  return {
    preferences:{defaultFormat:settings.defaultFormat === "mp4" ? "mp4" : "mp3",mp3Quality:[128,192,320].includes(settings.mp3Quality)?settings.mp3Quality:320,mp4Quality:[360,720,1080].includes(settings.mp4Quality)?settings.mp4Quality:720,authorizedDownloads:settings.authorizedDownloads === true,destinationConfigured:!!settings.defaultFolder},
    connection:{connected:connection.connected,compatible:connection.compatible,error:connection.error ? contentError(connection.error) : ""},
    jobs:(snapshot.jobs || []).filter(job=>subscription?.jobIds.has(job.id)).map(job=>({id:job.id,url:OMD.videoUrl(job.url),status:job.status,progress:typeof job.progress === "number" && Number.isFinite(job.progress)?Math.max(0,Math.min(100,job.progress)):null,error:job.error?contentError(job.error):"",actualHeight:Number.isInteger(job.actualHeight)?job.actualHeight:null,resultNote:resultNote(job)}))
  };
}
function sendView() {
  chrome.runtime.sendMessage({event:"state",data:{...snapshot,connection}}).catch(()=>{});
  for (const [key,subscription] of subscriptions) {
    const target = subscription.documentId ? {documentId:subscription.documentId} : {frameId:subscription.frameId};
    chrome.tabs.sendMessage(subscription.tabId,{event:"content_state",data:contentState(subscription)},target).catch(()=>{
      if (subscriptions.get(key) === subscription) {subscriptions.delete(key);persistSubscriptions();}
    });
  }
}
function disconnected() {
  port = null;
  connection = {connected:false,compatible:false,error:DISCONNECTED,lastSeen:connection.lastSeen};
  for (const {reject,timer} of pending.values()) {clearTimeout(timer);reject(new Error(DISCONNECTED));}
  pending.clear();
  sendView();
}
async function acceptState(state) {
  await restore;
  if (!state || !Array.isArray(state.jobs) || !state.settings) throw new Error("Resposta inválida do aplicativo auxiliar.");
  snapshot = state;
  connection = {connected:true,compatible:supportsOneClick(state),error:supportsOneClick(state)?"":UPDATE,lastSeen:Date.now()};
  for (const job of state.jobs) {
    if (!["completed","error"].includes(job.status) || completed.has(job.id)) continue;
    completed.add(job.id);
    const message = job.status === "completed" ? [job.title || "Seu arquivo está pronto.",job.resultNote || resultNote(job)].filter(Boolean).join(" · ") : job.error || GENERIC;
    chrome.notifications.create(`omd-${job.id}`,{type:"basic",iconUrl:"icons/128.png",title:job.status === "completed"?"Mídia salva com sucesso!":"Falha no download",message:String(message).slice(0,400)},()=>{void chrome.runtime.lastError;});
  }
  if (completed.size > 300) {const keep=[...completed].slice(-200);completed.clear();for(const id of keep)completed.add(id);}
  chrome.storage.local.set({snapshot,notified:[...completed]}).catch(()=>{});
  sendView();
}
function connect() {
  if (port) return port;
  try {
    const next=chrome.runtime.connectNative(HOST);port=next;
    next.onMessage.addListener(msg=>{
      if(port!==next)return;
      if (msg?.event === "state") {acceptState(msg.data).catch(()=>{});return;}
      const item=pending.get(msg?.id);if(!item)return;
      clearTimeout(item.timer);pending.delete(msg.id);
      if(msg.ok)item.resolve(msg.result);else item.reject(new Error(typeof msg.error === "string"?msg.error:GENERIC));
    });
    next.onDisconnect.addListener(()=>{void chrome.runtime.lastError;if(port===next)disconnected();});
    return next;
  } catch {throw new Error(DISCONNECTED);}
}
function native(type,payload={},approvedPort=null) {
  if (approvedPort && port !== approvedPort) return Promise.reject(new Error(DISCONNECTED));
  const current=approvedPort || connect();
  return new Promise((resolve,reject)=>{
    const id=crypto.randomUUID();
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error(type === "pick_folder"?"A seleção de pasta demorou para responder. Feche a janela e tente novamente.":DISCONNECTED));},type === "pick_folder"?30*60*1000:20000);
    pending.set(id,{resolve,reject,timer});
    try {current.postMessage({id,type,payload});}catch{clearTimeout(timer);pending.delete(id);reject(new Error(DISCONNECTED));}
  });
}
function trustedPage(sender) {
  if(sender.id!==chrome.runtime.id)return false;
  return ["popup.html","options.html"].some(page=>sender.url === chrome.runtime.getURL(page));
}
async function refresh() {await acceptState(await native("get_state"));}
async function compatiblePort() {
  // Bind the live capability response to the exact connection receiving the command.
  const current=connect();
  const state=await native("get_state",{},current);
  if(port!==current)throw new Error(DISCONNECTED);
  await acceptState(state);
  if(port!==current)throw new Error(DISCONNECTED);
  if(!supportsOneClick(state))throw new Error(UPDATE);
  return current;
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(!message?.type)return false;
  const isPage=trustedPage(sender);
  const isContent=sender.id===chrome.runtime.id && Number.isInteger(sender.tab?.id) && OMD.pageUrl(sender.url);
  const allowed=isPage?["ping","get_state","download","cancel","pick_folder","settings","open_folder","clear_history"]:isContent?["ping","get_state","download"]:[];
  if(!allowed.includes(message.type)){respond({ok:false,error:"Pedido não autorizado."});return false;}
  (async()=>{
    await restore;
    const subscription=isContent?subscribe(sender):null;
    const type=message.type;
    if(type === "get_state") {
      try{await refresh();}catch{connection={...connection,connected:false,compatible:false,error:DISCONNECTED};sendView();}
      return isContent?contentState(subscription):{...snapshot,connection};
    }
    if(type === "download") {
      const payload=OMD.downloadPayload(message.payload);
      const approvedPort=await compatiblePort();
      let operation=enqueuing.get(payload.url);
      if(!operation){operation=native("download",payload,approvedPort);enqueuing.set(payload.url,operation);operation.finally(()=>{if(enqueuing.get(payload.url)===operation)enqueuing.delete(payload.url);}).catch(()=>{});}
      const result=await operation;
      if(subscription && typeof result?.jobId === "string"){subscription.jobIds.add(result.jobId);persistSubscriptions();}
      await refresh();
      return isContent?{jobId:typeof result?.jobId === "string"?result.jobId:""}:result;
    }
    if(type === "settings") {
      const approvedPort=await compatiblePort();
      const result=await native(type,OMD.settingsPayload(message.payload),approvedPort);await refresh();return result;
    }
    const result=await native(type,message.payload || {});
    if(type === "ping" && isContent)return {version:typeof result?.version === "string"?result.version.slice(0,30):"",protocolVersion:Number.isInteger(result?.protocolVersion)?result.protocolVersion:0,capabilities:{oneClickDownloads:result?.capabilities?.oneClickDownloads === true}};
    if(["cancel","pick_folder","clear_history"].includes(type))await refresh();
    return result;
  })().then(result=>respond({ok:true,result}),error=>respond({ok:false,error:isContent?contentError(error.message):error.message || GENERIC}));
  return true;
});
chrome.tabs.onRemoved.addListener(tabId=>{for(const [key,value]of subscriptions)if(value.tabId===tabId)subscriptions.delete(key);persistSubscriptions();});
chrome.notifications.onClicked.addListener(()=>chrome.tabs.create({url:chrome.runtime.getURL("popup.html")}));
