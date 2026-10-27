// Real installed MOSS model and WebAudio playback; no microphone/acoustic claim.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const b=await chromium.connectOverCDP('http://127.0.0.1:9224'),p=b.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));
 const receipt={kind:'INSTALLED_SPEECH_PLAYBACK',samples:[],limitations:['Acoustic output and subjective naturalness require listening; WebAudio events only are measured here.']};
 let saved;
 try{
  const voices=await p.evaluate(()=>Axx.nativeVoice.refreshVoices());
  saved=await p.evaluate(()=>{const r=Axx.symbiosis.reader;return {voiceURI:r.voiceURI,lang:r.lang,rate:r.rate,text:r.text};});
  const selected=voices.some(v=>v.name==='moss:axx-sam')?'moss:axx-sam':'moss:axx-valeria';
  for(const name of [selected,selected]){
   assert(voices.some(v=>v.name===name),'Missing local sample: '+name);
   await p.evaluate(name=>{const r=Axx.symbiosis.reader;r.stop();r.voiceURI=name;r.lang='es';r.rate=1;r.setText('Hola, Señor. Estoy lista para ayudar con sus proyectos.','Aceptación de voz');Axx.nativeVoice.playback=null;r.play();},name);
   await p.waitForFunction(()=>['ended','error'].includes(Axx.symbiosis.reader.state),{},{timeout:180000});
   const result=await p.evaluate(()=>({state:Axx.symbiosis.reader.state,evidence:Axx.nativeVoice.playback}));
   receipt.samples.push({voice:name,...result});console.log(JSON.stringify(receipt.samples.at(-1)));
   assert.equal(result.state,'ended');assert(result.evidence.playing_event&&result.evidence.ended_event);assert.equal(result.evidence.underruns,0);assert.equal(result.evidence.buffering,'adaptive');
  }
  assert(receipt.samples[1].evidence.cached_phrases>0,'Repeated speech must reuse the local audio cache');
  receipt.result='PASS';
 }catch(e){receipt.result='FAIL';receipt.error=e.stack;throw e;}
 finally{
  if(saved)await p.evaluate(s=>{const r=Axx.symbiosis.reader;r.stop();r.voiceURI=s.voiceURI;r.lang=s.lang;r.rate=s.rate;r.setText(s.text||'','');},saved);
  const dir=path.resolve('build/chat-'+require('../package.json').version);fs.mkdirSync(dir,{recursive:true});fs.writeFileSync(path.join(dir,'installed-speech.json'),JSON.stringify(receipt,null,2));await b.close();
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
