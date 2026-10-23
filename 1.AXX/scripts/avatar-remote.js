/* Approved phones can rotate and move the native desktop avatar. */
(function(Axx){
  'use strict';
  if(!Axx?.isNative())return;
  let sequence=0,busy=false,lockOwned=false,lockUntil=0;
  const request=()=>Axx.backendRequest('GET','/axx-api/mobile/avatar/events?since='+sequence);
  function releaseLock(){
    if(lockOwned&&Axx.companion){Axx.companion.interactionLock=false;lockOwned=false;}
  }
  function apply(event){
    const c=Axx.companion,r=Axx.app?.renderer;
    if(!c||!r)return;
    if(event.kind==='end'){releaseLock();return;}
    if(event.kind==='rotate')r.rotate(event.dx*.012,event.dy*.012);
    else if(event.kind==='move'){
      if(!c.interactionLock){c.interactionLock=true;lockOwned=true;}
      c.follower.go(c.follower.x+event.dx*2.5,c.follower.y+event.dy*2.5,innerWidth,innerHeight,c.size*.3);
      lockUntil=performance.now()+700;
    }
  }
  async function poll(){
    if(busy||document.hidden)return;
    busy=true;
    try{
      const result=await request();
      for(const event of result.events||[]){if(event.sequence>sequence){apply(event);sequence=event.sequence;}}
      if(result.sequence>sequence)sequence=result.sequence;
    }catch{ /* Gateway can be off; retry after the next poll. */ }
    finally{busy=false;if(lockOwned&&performance.now()>lockUntil)releaseLock();}
  }
  setInterval(()=>void poll(),65);
  window.addEventListener('blur',releaseLock);
})(window.Axx);
