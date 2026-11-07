"use strict";
const $=id=>document.getElementById(id);
let defaultFolder="";
let connected=false;
function message(text,failed=false){$("message").textContent=text;$("message").style.color=failed?"#ff9aae":"#6ae0ac";}
async function request(type,payload={}){const r=await chrome.runtime.sendMessage({type,payload});if(!r?.ok)throw new Error(r?.error || "Não foi possível atender ao pedido.");return r.result;}
function connection(state){connected=!!state.connection?.connected;$("connection").className=connected?"connected":"disconnected";$("connection").textContent=connected?"● Aplicativo auxiliar conectado. Tudo pronto.":state.connection?.error || "Aplicativo desconectado. Confira a instalação.";$("save").disabled=!connected;$("pick-folder").disabled=!connected;}
function populate(settings){const mode=[...document.querySelectorAll("input[name=folderMode]")].find(el=>el.value===settings.folderMode);if(mode)mode.checked=true;defaultFolder=settings.defaultFolder || "";$("default-folder").textContent=defaultFolder || "Nenhuma pasta padrão selecionada";$("last-folder").textContent=settings.lastFolder || "A primeira vez abrirá a seleção de pasta.";$("open-folder").checked=!!settings.openFolder;}
async function refresh(){message("");try{const state=await request("get_state");connection(state);populate(state.settings || {});}catch(e){message(e.message,true);}}
$("pick-folder").onclick=async()=>{message("Escolha uma pasta na janela do Windows.");$("pick-folder").disabled=true;try{const result=await request("pick_folder");if(result.cancelled){message("Seleção cancelada.");return;}defaultFolder=result.path;$("default-folder").textContent=defaultFolder;document.querySelector("input[value=default]").checked=true;message("Pasta selecionada. Salve as preferências para aplicar.");}catch(e){message(e.message,true);}finally{$("pick-folder").disabled=!connected;}};
$("preferences").onsubmit=async event=>{event.preventDefault();const folderMode=document.querySelector("input[name=folderMode]:checked").value;if(folderMode==="default"&&!defaultFolder){message("Escolha uma pasta padrão antes de salvar.",true);return;}$("save").disabled=true;try{const settings=await request("settings",{folderMode,defaultFolder,openFolder:$("open-folder").checked});populate(settings);message("Preferências salvas.");}catch(e){message(e.message,true);}finally{$("save").disabled=!connected;}};
$("reconnect").onclick=refresh;
chrome.runtime.onMessage.addListener(message=>{if(message?.event==="state")connection(message.data);});
refresh();
