"use strict";
importScripts("shared.js");
const HOST = "com.opera_music_downloader";
let port = null;
let snapshot = {settings:{folderMode:"ask", defaultFolder:"", lastFolder:"", openFolder:false}, jobs:[], tools:{}};
let connection = {connected:false, error:"Aplicativo auxiliar desconectado.", lastSeen:null};
const pending = new Map();
const completed = new Set();
let restored = false;
const restore = chrome.storage.local.get(["snapshot", "notified"]).then(data => {
  if (data.snapshot) snapshot = data.snapshot;
  for (const id of data.notified || []) completed.add(id);
  restored = true;
});
function sendView() {
  chrome.runtime.sendMessage({event:"state", data:{...snapshot, connection}}).catch(() => {});
}
function disconnected(message) {
  port = null;
  connection = {connected:false,error:message || "A conexão com o aplicativo auxiliar foi encerrada. Abra a extensão para reconectar.",lastSeen:connection.lastSeen};
  for (const {reject,timer} of pending.values()) { clearTimeout(timer); reject(new Error(connection.error)); }
  pending.clear();
  sendView();
}
async function acceptState(state) {
  await restore;
  if (!state || !Array.isArray(state.jobs) || !state.settings) return;
  snapshot = state;
  connection = {connected:true,error:"",lastSeen:Date.now()};
  for (const job of state.jobs) {
    if (!["completed","error"].includes(job.status) || completed.has(job.id)) continue;
    completed.add(job.id);
    chrome.notifications.create(`omd-${job.id}`, {type:"basic",iconUrl:"icons/128.png",title:job.status === "completed" ? "Mídia salva com sucesso!" : "Falha no download",message: String(job.status === "completed" ? job.title || "Seu arquivo está pronto." : job.error || "Abra a extensão para tentar novamente.").slice(0,400)}, () => { void chrome.runtime.lastError; });
  }
  if (completed.size > 300) { const keep = [...completed].slice(-200); completed.clear(); for (const id of keep) completed.add(id); }
  chrome.storage.local.set({snapshot,notified:[...completed]}).catch(() => {});
  sendView();
}
function connect() {
  if (port) return port;
  try {
    const next = chrome.runtime.connectNative(HOST);
    port = next;
    next.onMessage.addListener(msg => {
      connection = {connected:true,error:"",lastSeen:Date.now()};
      if (msg?.event === "state") { acceptState(msg.data); return; }
      const item = pending.get(msg?.id);
      if (!item) return;
      clearTimeout(item.timer); pending.delete(msg.id);
      if (msg.ok) item.resolve(msg.result); else item.reject(new Error(msg.error || "O aplicativo não conseguiu atender ao pedido."));
    });
    next.onDisconnect.addListener(() => {
      const detail = chrome.runtime.lastError?.message || "";
      if (detail) console.warn("Opera Music Downloader: conexão nativa encerrada:", detail);
      if (port === next) disconnected("Aplicativo auxiliar indisponível. Instale ou repare o Opera Music Downloader e reinicie o Opera GX.");
    });
    return next;
  } catch { throw new Error("Não foi possível iniciar o aplicativo auxiliar. Confira a instalação."); }
}
function native(type, payload = {}) {
  const current = connect();
  return new Promise((resolve,reject) => {
    const id = crypto.randomUUID();
    // A native folder dialog may stay open until the user decides.
    const timer = setTimeout(() => {pending.delete(id); reject(new Error("O aplicativo demorou para responder. Feche a janela de escolha de pasta e tente novamente."));}, ["download","pick_folder"].includes(type) ? 30 * 60 * 1000 : 20000);
    pending.set(id,{resolve,reject,timer});
    try { current.postMessage({id,type,payload}); } catch { clearTimeout(timer); pending.delete(id); reject(new Error("A conexão com o aplicativo auxiliar foi encerrada.")); }
  });
}
function trustedPage(sender) {
  if (sender.id !== chrome.runtime.id) return false;
  const base = chrome.runtime.getURL("");
  return typeof sender.url === "string" && ["popup.html","options.html"].some(page => sender.url === base + page);
}
chrome.runtime.onMessage.addListener((message,sender,respond) => {
  if (!message?.type) return false;
  const isPage = trustedPage(sender);
  const isContent = sender.id === chrome.runtime.id && Number.isInteger(sender.tab?.id) && OMD.pageUrl(sender.url);
  const allowed = isPage ? ["ping","get_state","download","cancel","pick_folder","settings","open_folder","clear_history"] : isContent ? ["ping","get_state","download"] : [];
  if (!allowed.includes(message.type)) { respond({ok:false,error:"Pedido não autorizado."}); return false; }
  (async () => {
    await restore;
    const type = message.type;
    const payload = type === "download" ? OMD.downloadPayload(message.payload) : message.payload || {};
    if (type === "get_state") {
      try { await acceptState(await native(type,payload)); } catch (error) { connection = {...connection,connected:false,error:error.message}; }
      return isContent ? {settings:{folderMode:snapshot.settings.folderMode},connection} : {...snapshot,connection};
    }
    const result = await native(type,payload);
    if (["settings","clear_history","cancel","download","pick_folder"].includes(type)) await acceptState(await native("get_state"));
    return result;
  })().then(result => respond({ok:true,result}), error => respond({ok:false,error:error.message || "Não foi possível concluir o pedido."}));
  return true;
});
chrome.runtime.onInstalled.addListener(() => { if (restored) sendView(); });
chrome.notifications.onClicked.addListener(() => chrome.runtime.openOptionsPage());
