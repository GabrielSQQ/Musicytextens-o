import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const source=fs.readFileSync(path.join(root,'extension/shared.js'),'utf8');
const ctx=vm.createContext({URL});vm.runInContext(source,ctx);const OMD=ctx.OMD;
const ID='abcdefghijklmnopabcdefghijklmnop';
const contentSender={id:ID,url:'https://www.youtube.com/watch?v=abcdefghijk',tab:{id:1},frameId:0,documentId:'document-one'};
const popupSender={id:ID,url:`chrome-extension://${ID}/popup.html`};
const freshState=()=>({version:'1.1.0',protocolVersion:2,capabilities:{oneClickDownloads:true},settings:{folderMode:'default',lastFolder:'C:\\Private',defaultFolder:'C:\\Secret',defaultFormat:'mp3',mp3Quality:320,mp4Quality:720,authorizedDownloads:true,openFolder:false},jobs:[{id:'old',url:'https://www.youtube.com/watch?v=zzzzzzzzzzz',status:'cancelled',path:'C:\\Private\\song.mp3',title:'Private history'}],tools:{}});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function backgroundHarness({host=freshState(),cached=null,subscriptions={},failure=null,disconnectAfterState=false}={}){
  let listener;const requests=[],tabMessages=[],storageOrder=[],sessionValues={contentSubscriptions:subscriptions};const listeners={};let sequence=0;
  const port={onMessage:{addListener(fn){listeners.message=fn;}},onDisconnect:{addListener(fn){listeners.disconnect=fn;}},postMessage(msg){
    requests.push(msg);
    queueMicrotask(()=>{
      let result;
      if(failure && msg.type === failure.type){listeners.message({id:msg.id,ok:false,error:failure.error});return;}
      if(msg.type==='get_state')result=host;
      else if(msg.type==='download'){
        const id=`new-${++sequence}`;
        host.jobs.push({id,...msg.payload,format:host.settings.defaultFormat,quality:host.settings.mp3Quality,status:'queued',progress:0,path:'C:\\Secret\\never-content.mp3',title:'Own title not needed by content'});
        result={jobId:id};
      }else if(msg.type==='settings'){Object.assign(host.settings,msg.payload);result=host.settings;}
      else if(msg.type==='pick_folder'){host.settings.defaultFolder='C:\\Pasta com acentos ç';result={path:host.settings.defaultFolder};}
      else result={version:host.version,protocolVersion:host.protocolVersion,capabilities:host.capabilities};
      listeners.message({id:msg.id,ok:true,result});
      if(disconnectAfterState && msg.type === 'get_state')listeners.disconnect();
    });
  }};
  const chrome={runtime:{id:ID,getURL:x=>`chrome-extension://${ID}/`+x,sendMessage:()=>Promise.resolve(),connectNative:()=>port,onMessage:{addListener(fn){listener=fn;}},lastError:null},tabs:{sendMessage:(tabId,message,target)=>{tabMessages.push({tabId,message:JSON.parse(JSON.stringify(message)),target});return Promise.resolve();},onRemoved:{addListener(){}},create:()=>Promise.resolve()},storage:{local:{setAccessLevel:async value=>storageOrder.push(['lock',value.accessLevel]),get:async()=>{storageOrder.push(['get']);return cached?{snapshot:cached}:{};},set:async()=>{storageOrder.push(['set']);}},session:{setAccessLevel:async()=>{},get:async()=>sessionValues,set:async patch=>Object.assign(sessionValues,patch)}},notifications:{create:()=>{},onClicked:{addListener(){}}}};
  const context=vm.createContext({chrome,URL,setTimeout,clearTimeout,crypto:{randomUUID:()=>String(Math.random())},console,queueMicrotask});
  context.importScripts=()=>vm.runInContext(source,context);
  vm.runInContext(fs.readFileSync(path.join(root,'extension/background.js'),'utf8'),context);
  return {requests,tabMessages,storageOrder,host,sessionValues,send:(message,sender=contentSender)=>new Promise(resolve=>listener(message,sender,resolve)),emit:async state=>{listeners.message({event:'state',data:state});await tick();},disconnect:async()=>{listeners.disconnect();await tick();}};
}
test('only supported HTTPS YouTube video URLs are accepted',()=>{
  for(const value of ['https://www.youtube.com/watch?v=abcdefghijk&list=x','https://music.youtube.com/watch?v=abcdefghijk','https://youtu.be/abcdefghijk','https://youtube.com/shorts/abcdefghijk'])assert.equal(OMD.videoUrl(value),'https://www.youtube.com/watch?v=abcdefghijk');
  for(const value of ['http://www.youtube.com/watch?v=abcdefghijk','file:///etc/passwd','https://www.youtube.com.evil.test/watch?v=abcdefghijk','https://www.youtube.com@evil.test/watch?v=abcdefghijk','https://user:pass@www.youtube.com/watch?v=abcdefghijk','https://www.youtube.com:444/watch?v=abcdefghijk','https://www.youtube.com/playlist?list=abcdefghijk','https://www.youtube.com/watch?v=abcdefghijk;ls','https://youtu.be/abcdefghijk/extra','javascript:alert(1)'])assert.equal(OMD.videoUrl(value),null,value);
});
test('download requests contain metadata only; caller cannot set prefs or authorization',()=>{
  const clean=OMD.downloadPayload({url:contentSender.url,title:'a'.repeat(600),thumbnail:'https://evil.test/x.png',path:'C:\\Windows',defaultFolder:'C:\\Injected',format:'exe',quality:'192; calc.exe',authorized:true,authorizedDownloads:true,cookies:'secret'});
  assert.equal(clean.title.length,500);assert.equal(clean.thumbnail,'');assert.deepEqual(Object.keys(clean).sort(),['channel','thumbnail','title','url']);
  assert.throws(()=>OMD.downloadPayload({url:'file:///private.mp3'}));
  assert.equal(OMD.thumbnail('https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg'),'https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg');
  assert.equal(OMD.pageUrl('https://youtu.be/abcdefghijk'),false);
});
test('settings validate independent qualities and booleans, ignoring unsupported authority fields',()=>{
  const clean=OMD.settingsPayload({defaultFormat:'mp4',mp3Quality:320,mp4Quality:720,authorizedDownloads:true,defaultFolder:'C:\\Música',lastFolder:'C:\\Injected',shell:'calc'});
  assert.equal(clean.defaultFormat,'mp4');assert.equal(clean.folderMode,'default');assert.equal('lastFolder'in clean,false);assert.equal('shell'in clean,false);
  for(const value of [{defaultFormat:'m4a'},{mp3Quality:720},{mp4Quality:320},{authorizedDownloads:'true'},{openFolder:1}])assert.throws(()=>OMD.settingsPayload(value));
});
test('worker locks full snapshots to trusted storage before reading or writing',async()=>{
  const h=backgroundHarness();await h.send({type:'get_state'});
  assert.deepEqual(h.storageOrder[0],['lock','TRUSTED_CONTEXTS']);assert.equal(h.storageOrder.findIndex(x=>x[0]==='get')>0,true);
});
test('content cannot edit prefs, consent, native directories or arbitrary job IDs',async()=>{
  const h=backgroundHarness();
  for(const type of ['settings','pick_folder','cancel','open_folder','clear_history'])assert.equal((await h.send({type,payload:{authorizedDownloads:true,jobId:'old'}})).ok,false);
  assert.equal(h.requests.length,0);
  assert.equal((await h.send({type:'get_state'},{...contentSender,id:'foreign'})).ok,false);
  assert.equal((await h.send({type:'get_state'},{...contentSender,url:'https://evil.test/'})).ok,false);
});
test('cached v2 state cannot authorize sending downloads or settings to a live old host',async()=>{
  for(const state of [{...freshState(),protocolVersion:1,capabilities:{}},{...freshState(),capabilities:{oneClickDownloads:false}}]){
    const h=backgroundHarness({host:state,cached:freshState()});
    const r=await h.send({type:'download',payload:{url:contentSender.url}});
    assert.equal(r.ok,false);assert.match(r.error,/Atualize o aplicativo auxiliar/);assert.equal(h.requests.some(x=>x.type==='download'),false);
    const s=await h.send({type:'settings',payload:{authorizedDownloads:true}},popupSender);assert.equal(s.ok,false);assert.equal(h.requests.some(x=>x.type==='settings'),false);
  }
});
test('one click passes metadata only to a live compatible host without picker',async()=>{
  const h=backgroundHarness();const r=await h.send({type:'download',payload:{url:contentSender.url,format:'mp4',quality:1080,authorized:true,path:'C:\\Injected'}});
  assert.equal(r.ok,true);const command=h.requests.find(x=>x.type==='download');assert.deepEqual(Object.keys(command.payload).sort(),['channel','thumbnail','title','url']);
  assert.equal(h.requests.some(x=>x.type==='pick_folder'),false);
  const own=(await h.send({type:'get_state'})).result;assert.equal(own.jobs.length,1);assert.equal(own.jobs[0].id,r.result.jobId);assert.equal(own.preferences.defaultFormat,'mp3');
  assert.equal(JSON.stringify(own).includes('C:\\'),false);assert.equal(JSON.stringify(own).includes('Own title'),false);assert.equal(JSON.stringify(own).includes('Private history'),false);
});
test('live tab messages contain only that document owned jobs, sanitized notes/errors and prefs',async()=>{
  const h=backgroundHarness();const one=await h.send({type:'download',payload:{url:contentSender.url}});
  const second={...contentSender,tab:{id:2},documentId:'document-two'};await h.send({type:'get_state'},second);
  const ownJob=h.host.jobs.find(x=>x.id===one.result.jobId);Object.assign(ownJob,{status:'error',error:'OSError writing C:\\Private\\secrets.json',format:'mp4',quality:720,actualHeight:360,resultNote:'C:\\Private\\bad'});
  h.host.settings.defaultFormat='mp4';await h.emit(h.host);
  for(const tabId of [1,2]){
    const message=h.tabMessages.filter(x=>x.tabId===tabId).at(-1);assert.equal(message.message.data.preferences.defaultFormat,'mp4');assert.equal(message.message.data.jobs.length,tabId===1?1:0);
    const serialized=JSON.stringify(message);assert.equal(serialized.includes('Private'),false);assert.equal(serialized.includes('Secret'),false);assert.equal(serialized.includes('C:\\'),false);
    if(tabId===1){assert.match(message.message.data.jobs[0].error,/Abra a extensão/);assert.match(message.message.data.jobs[0].resultNote,/360p/);assert.equal(message.target.documentId,'document-one');}
  }
  const newDocument={...contentSender,documentId:'replacement-document'};assert.equal((await h.send({type:'get_state'},newDocument)).result.jobs.length,0);
});
test('subscription ownership survives service worker restart but remains document-bound',async()=>{
  const state=freshState();state.jobs.push({id:'own-before-restart',url:contentSender.url,status:'downloading',progress:42,path:'C:\\Secret'});
  const records={'1:0':{tabId:1,frameId:0,documentKey:'document-one',documentId:'document-one',jobIds:['own-before-restart']}};
  const h=backgroundHarness({host:state,subscriptions:records});const r=await h.send({type:'get_state'});assert.equal(r.result.jobs[0].progress,42);assert.equal(r.result.jobs.length,1);
});
test('raw native failures never expose paths to content, while folder errors stay actionable',async()=>{
  const h=backgroundHarness({failure:{type:'download',error:'Permission denied: C:\\Private\\state.json'}});const r=await h.send({type:'download',payload:{url:contentSender.url}});assert.equal(r.ok,false);assert.equal(r.error,'Não foi possível concluir o download. Abra a extensão para verificar.');
  const folder=backgroundHarness({failure:{type:'download',error:'Configure uma pasta de destino na extensão.'}});assert.equal((await folder.send({type:'download',payload:{url:contentSender.url}})).error,'Configure uma pasta de destino na extensão.');
});
test('popup settings and explicit picker remain privileged and preserve native state',async()=>{
  const h=backgroundHarness();const r=await h.send({type:'settings',payload:{defaultFormat:'mp4',mp4Quality:720,authorizedDownloads:true}},popupSender);assert.equal(r.ok,true);assert.equal(h.host.settings.defaultFormat,'mp4');
  assert.equal((await h.send({type:'pick_folder'},popupSender)).ok,true);assert.equal(h.host.settings.defaultFolder,'C:\\Pasta com acentos ç');
  assert.equal((await h.send({type:'pick_folder'},{...popupSender,url:popupSender.url+'?evil=1'})).ok,false);
});

test('port loss after live capability response cannot reconnect and forward an unverified download',async()=>{
  const h=backgroundHarness({disconnectAfterState:true});
  const r=await h.send({type:'download',payload:{url:contentSender.url}});
  assert.equal(r.ok,false);assert.equal(r.error,'Aplicativo auxiliar desconectado. Abra a extensão para verificar.');
  assert.equal(h.requests.some(x=>x.type==='download'),false);
});
