// Production handler with controlled FileReader/transport; native ASR is separate.
const fs=require('fs'),assert=require('node:assert/strict');
const source=fs.readFileSync('1.AXX/Axx.html','utf8');
const start=source.indexOf("            click('transcript-transcribe-file', async () => {");
const end=source.indexOf("            sx('transcript-media').onchange",start);
assert(start>0&&end>start);
async function trial(options={}) {
 const file={name:'fixture.wav',type:'audio/wav',size:100,...options.file};
 const nodes={'transcript-transcribe-file':{disabled:false},'transcript-file-status':{},'transcript-state':{}};
 const calls=[],reads=[];let handler;
 const owner={mediaFile:file,prefs:{language:'es-DO'},cues:[{text:'preserved'}],renderCues(){},updateCaption(){},notice(){}};
 class Reader {readAsDataURL(value){reads.push(value);if(options.readError)return this.onerror();this.result='data:audio/wav;base64,YXVkaW8=';if(options.changed)owner.mediaFile={};this.onload();}}
 const axx={isNative:()=>true,backendRequest:async(...args)=>{calls.push(args);if(options.apiError)throw Error('ASR unavailable');return {segments:[{start:0,end:1,text:'Fixture'}]};}};
 new Function('click','sx','Axx','FileReader',source.slice(start,end)).call(owner,(_,fn)=>handler=fn,id=>nodes[id],axx,Reader);
 await handler();assert.equal(nodes['transcript-transcribe-file'].disabled,false);
 return {file,owner,nodes,calls,reads};
}
(async()=>{
 let t=await trial();assert.strictEqual(t.reads[0],t.file);assert.equal(t.calls.length,1);assert.equal(t.calls[0][2].language,'es');assert.equal(t.owner.cues[0].text,'Fixture');
 for(const options of [{file:{size:1400*1024+1}},{file:{type:'video/mp4'}},{file:{size:0}},{readError:true},{changed:true}]){
  t=await trial(options);assert.equal(t.calls.length,0);assert.equal(t.owner.cues[0].text,'preserved');
 }
 t=await trial({apiError:true});assert.equal(t.owner.cues[0].text,'preserved');assert.match(t.nodes['transcript-file-status'].textContent,/unavailable/);
 console.log('PASS: whole-file input, language, byte/MIME limits, read errors, changed selection and failed ASR preserve prior cues');
})().catch(e=>{console.error(e);process.exitCode=1;});
