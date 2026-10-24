// Pixel coverage/performance probes of the installed production tube renderer.
// These complement native pointer/attachment captures; they do not simulate user input.
const fs=require('fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const b=await chromium.connectOverCDP('http://127.0.0.1:9224');
 const p=b.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));
 try{
  const report=await p.evaluate(()=>{
   const tube=new Axx.OrganicTendrils();tube.canvas.hidden=true;tube.width=1920;tube.height=1080;
   const renderer=Axx.app.renderer,lut=tube.material(renderer.materialTable(),renderer.lutKey),rows=[];
   try{
    for(const dpr of [1,1.5,2])for(const length of [24,60,180,800,2000])for(const angle of [0,Math.PI/4,Math.PI/2,Math.PI]){
     tube.dpr=dpr;
     const link={id:'quality',a:{x:80,y:100},b:{x:80+Math.cos(angle)*length,y:100+Math.sin(angle)*length},progress:1,rootRadius:Math.min(24,length*.16)};
     const start=performance.now();tube.tube(link,0,lut,0);const ms=performance.now()-start;
     const raster=tube.buffers.get('quality').raster,columns=new Uint32Array(raster.width);let partial=0,clipped=0;
     for(let y=0;y<raster.height;y++)for(let x=0;x<raster.width;x++){
      const alpha=raster.pixels[(y*raster.width+x)*4+3];if(alpha){columns[x]++;if(alpha<255)partial++;if(y===0||y===raster.height-1)clipped++;}
     }
     const first=columns.findIndex(v=>v>0);let last=columns.length-1;while(last>0&&!columns[last])last--;
     const gaps=Array.from(columns.slice(first,last+1)).filter(v=>!v).length;
     rows.push({dpr,length,angle,ms,first,last,gaps,partial,clipped,pixels:raster.width*raster.height});
    }
    return {kind:'INSTALLED_ANALYTIC_TUBE_COVERAGE',rows,renderer:tube.snapshot().kind};
   }finally{tube.canvas.remove();tube.buffers.clear();}
  });
  for(const row of report.rows){assert(row.first>=0);assert.equal(row.gaps,0);assert(row.partial>0);assert.equal(row.clipped,0);assert(row.pixels<4000000);}
  report.result='PASS';fs.writeFileSync('build/chat-0.21.4/tentacles/quality.json',JSON.stringify(report,null,2));
  const times=report.rows.map(r=>r.ms).sort((a,b)=>a-b);
  console.log(JSON.stringify({result:report.result,cases:report.rows.length,median_ms:times[Math.floor(times.length*.5)],p95_ms:times[Math.floor(times.length*.95)],renderer:report.renderer},null,2));
 }finally{await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
