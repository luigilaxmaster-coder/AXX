/* Approved phones can rotate and move the native desktop avatar. */
(function(Axx){
  'use strict';
  if(!Axx?.isNative())return;
  let sequence=0,boot='',lockOwned=false,lockUntil=0;
  const request=()=>Axx.backendRequest('GET','/axx-api/mobile/avatar/events?wait=1&since='+sequence);
  function releaseLock(){
    if(lockOwned&&Axx.companion){Axx.companion.interactionLock=false;lockOwned=false;}
  }
  function apply(event){
    const c=Axx.companion,r=Axx.app?.renderer;
    if(!c||!r)return;
    if(event.kind==='end'){releaseLock();return;}
    if(event.kind==='rotate')r.rotate(event.dx*.012,event.dy*.012);
    else if(event.kind==='move'){
      const first=!lockOwned;
      if(!c.interactionLock){c.interactionLock=true;lockOwned=true;}
      if(c.pointer)c.pointer.known=false;
      c.follower.go((first?c.follower.x:c.follower.tx)+event.dx*2.5,(first?c.follower.y:c.follower.ty)+event.dy*2.5,innerWidth,innerHeight,c.size*.3);
      lockUntil=performance.now()+700;
    }
  }
  async function poll(){
    for(;;){try{
      const result=await request();
      if(boot!==result.boot_id){releaseLock();sequence=0;boot=result.boot_id;}
      for(const event of result.events||[]){if(event.sequence>sequence){apply(event);sequence=event.sequence;}}
      if(result.sequence>sequence)sequence=result.sequence;
    }catch{await new Promise(resolve=>setTimeout(resolve,1000));}
    finally{if(lockOwned&&performance.now()>lockUntil)releaseLock();}}
  }
  // Long polling avoids delayed gestures when the desktop WebView loses focus.
  void poll();
  window.addEventListener('blur',releaseLock);
})(window.Axx);
