import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const source=fs.readFileSync(path.join(root,'extension/shared.js'),'utf8');
const ctx=vm.createContext({URL});vm.runInContext(source,ctx);const OMD=ctx.OMD;
test('only canonical supported YouTube video URLs are accepted',()=>{
  for(const value of ['https://www.youtube.com/watch?v=abcdefghijk&list=x','https://music.youtube.com/watch?v=abcdefghijk','https://youtu.be/abcdefghijk','https://youtube.com/shorts/abcdefghijk'])assert.equal(OMD.videoUrl(value),'https://www.youtube.com/watch?v=abcdefghijk');
  for(const value of ['http://www.youtube.com/watch?v=abcdefghijk','file:///etc/passwd','https://www.youtube.com.evil.test/watch?v=abcdefghijk','https://www.youtube.com@evil.test/watch?v=abcdefghijk','https://user:pass@www.youtube.com/watch?v=abcdefghijk','https://www.youtube.com:444/watch?v=abcdefghijk','https://www.youtube.com/playlist?list=abcdefghijk','https://www.youtube.com/watch?v=abcdefghijk;ls','https://youtu.be/abcdefghijk/extra','javascript:alert(1)'])assert.equal(OMD.videoUrl(value),null,value);
});
test('download payload requires explicit authorization and validates format',()=>{
  const base={url:'https://youtube.com/watch?v=abcdefghijk',authorized:true,format:'mp3',quality:192};
  assert.equal(OMD.downloadPayload(base).quality,192);
  assert.throws(()=>OMD.downloadPayload({...base,authorized:false}));
  assert.throws(()=>OMD.downloadPayload({...base,authorized:'true'}));
  assert.throws(()=>OMD.downloadPayload({...base,format:'exe'}));
  assert.throws(()=>OMD.downloadPayload({...base,quality:'192; calc.exe'}));
  assert.throws(()=>OMD.downloadPayload({...base,format:'mp4',quality:192}));
  const clean=OMD.downloadPayload({...base,title:'a'.repeat(600),thumbnail:'https://evil.test/x.png',path:'C:\\Windows',cookies:'secret'});
  assert.equal(clean.title.length,500);assert.equal(clean.thumbnail,'');assert.equal('path' in clean,false);assert.equal('cookies' in clean,false);
});
test('thumbnail and sender URL checks restrict unrelated origins',()=>{
  assert.equal(OMD.thumbnail('https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg'),'https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg');
  assert.equal(OMD.thumbnail('https://i.ytimg.com.evil.test/track'),'');
  assert.equal(OMD.pageUrl('https://www.youtube.com/results?search_query=music'),true);
  assert.equal(OMD.pageUrl('https://youtu.be/abcdefghijk'),false);
  assert.equal(OMD.pageUrl('http://www.youtube.com/'),false);
});
function backgroundHarness(){
  let listener;const requests=[];const listeners={};
  const state={settings:{folderMode:'last',lastFolder:'C:\\Private',defaultFolder:'C:\\Secret'},jobs:[{id:'old',status:'cancelled',path:'C:\\Private\\song.mp3',title:'Private history'}],tools:{}};
  const port={onMessage:{addListener(fn){listeners.message=fn;}},onDisconnect:{addListener(fn){listeners.disconnect=fn;}},postMessage(msg){requests.push(msg);queueMicrotask(()=>listeners.message({id:msg.id,ok:true,result:msg.type==='get_state'?state:msg.type==='download'?{jobId:'new'}:{version:'1.0.0'}}));}};
  const chrome={runtime:{id:'abcdefghijklmnopabcdefghijklmnop',getURL:x=>'chrome-extension://abcdefghijklmnopabcdefghijklmnop/'+x,sendMessage:()=>Promise.resolve(),connectNative:()=>port,onMessage:{addListener(fn){listener=fn;}},onInstalled:{addListener(){}},openOptionsPage(){}},storage:{local:{get:()=>Promise.resolve({}),set:()=>Promise.resolve()}},notifications:{create:()=>Promise.resolve(),onClicked:{addListener(){}}}};
  const context=vm.createContext({chrome,URL,setTimeout,clearTimeout,crypto:{randomUUID:()=>String(Math.random())},console,queueMicrotask});
  context.importScripts=()=>vm.runInContext(source,context);
  vm.runInContext(fs.readFileSync(path.join(root,'extension/background.js'),'utf8'),context);
  return {requests,send:(message,sender)=>new Promise(resolve=>listener(message,sender,resolve)),state};
}
const contentSender={id:'abcdefghijklmnopabcdefghijklmnop',url:'https://www.youtube.com/watch?v=abcdefghijk',tab:{id:1}};
test('service worker prevents content configuration and filesystem commands',async()=>{
  const h=backgroundHarness();
  for(const type of ['settings','pick_folder','cancel','open_folder','clear_history']){const r=await h.send({type,payload:{}},contentSender);assert.equal(r.ok,false);}
  assert.equal(h.requests.length,0);
  const foreign=await h.send({type:'download',payload:{}},{...contentSender,id:'foreign'});assert.equal(foreign.ok,false);
  const hostile=await h.send({type:'get_state'},{...contentSender,url:'https://evil.test/'});assert.equal(hostile.ok,false);
});
test('content state never reveals local paths or other download history',async()=>{
  const h=backgroundHarness();const r=await h.send({type:'get_state'},contentSender);
  assert.equal(r.ok,true);assert.equal(r.result.connection.connected,true);assert.equal(r.result.settings.folderMode,'last');assert.equal('jobs' in r.result,false);assert.equal('defaultFolder' in r.result.settings,false);assert.equal('lastFolder' in r.result.settings,false);
  const serialized=JSON.stringify(r);assert.equal(serialized.includes('Private'),false);assert.equal(serialized.includes('Secret'),false);
});
test('trusted extension pages receive settings and can select native folders',async()=>{
  const h=backgroundHarness();const sender={id:contentSender.id,url:'chrome-extension://abcdefghijklmnopabcdefghijklmnop/options.html'};
  const r=await h.send({type:'get_state'},sender);assert.equal(r.result.settings.lastFolder,'C:\\Private');
  const denied=await h.send({type:'pick_folder'},{...sender,url:sender.url+'?evil=1'});assert.equal(denied.ok,false);
});
