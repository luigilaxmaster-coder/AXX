// Backend-validated diagrams and annotations. Model strings are always text, never markup.
const NS='http://www.w3.org/2000/svg';let sequence=0;
const svg=(name,attrs={},text)=>{const n=document.createElementNS(NS,name);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;};

export function renderDiagram(host,diagram,stepId,onStep=()=>{}){
    host.replaceChildren();const root=svg('svg',{viewBox:'0 0 1000 600',role:'group','aria-label':'Diagrama de la explicación'}),markerId='axx-diagram-arrow-'+(++sequence);
    const defs=svg('defs'),marker=svg('marker',{id:markerId,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto-start-reverse'});
    marker.append(svg('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'currentColor'}));defs.append(marker);root.append(defs);
    root.style.color='var(--mp-ink)';const nodes=new Map(diagram.nodes.map(n=>[n.id,n]));
    for(const edge of diagram.edges){
        const a=nodes.get(edge.from).bounds,b=nodes.get(edge.to).bounds,x1=(a[0]+a[2]/2)*1000,y1=(a[1]+a[3]/2)*600,x2=(b[0]+b[2]/2)*1000,y2=(b[1]+b[3]/2)*600;
        const labelX=(x1+x2)/2,labelY=(y1+y2)/2-18,labelWidth=Math.min(300,Math.max(120,edge.label.length*18+28));
        root.append(svg('line',{x1,y1,x2,y2,stroke:'currentColor','stroke-opacity':'.55','stroke-width':4,'marker-end':'url(#'+markerId+')'}),
            svg('rect',{x:labelX-labelWidth/2,y:labelY-24,width:labelWidth,height:38,rx:19,fill:'var(--surface, #222b3c)',stroke:'var(--line, #ffffff25)','stroke-width':2}),
            svg('text',{x:labelX,y:labelY,'text-anchor':'middle','dominant-baseline':'middle','font-size':26,'font-weight':550,fill:'currentColor'},edge.label));
    }
    for(const node of diagram.nodes){
        const [a,b,c,d]=node.bounds,x=a*1000,y=b*600,w=c*1000,h=d*600,active=node.step_id===stepId;
        const g=svg('g',{role:'button',tabindex:0,'aria-label':node.label,'aria-current':active?'step':'false',class:'mp-diagram-node'});
        g.append(svg('rect',{x,y,width:w,height:h,rx:18,fill:active?'color-mix(in srgb, var(--mp-accent, #9274ff) 12%, var(--surface, #222b3c))':'var(--surface, #222b3c)',stroke:active?'var(--mp-accent, #9274ff)':'currentColor','stroke-opacity':active?'1':'.6','stroke-width':active?5:2}));
        const words=node.label.split(/\s+/),lines=[];let line='';
        for(const word of words){if(line.length+word.length>Math.max(7,Math.floor(w/20))){lines.push(line);line='';}line+=(line?' ':'')+word;}if(line)lines.push(line);
        lines.slice(0,4).forEach((text,i)=>g.append(svg('text',{x:x+w/2,y:y+h/2+(i-(Math.min(lines.length,4)-1)/2)*36,'text-anchor':'middle','dominant-baseline':'middle','font-size':32,'font-weight':550,fill:'currentColor'},text)));
        g.addEventListener('click',()=>onStep(node.step_id,node));g.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();onStep(node.step_id,node);}});root.append(g);
    }
    host.append(root);
}

function lines(ctx,text,x,y,width,height,font){
    const words=text.split(/\s+/);let row='',at=y+font;
    for(const word of words){const next=row+(row?' ':'')+word;if(ctx.measureText(next).width>width&&row){ctx.fillText(row,x,at);at+=font*1.3;row=word;if(at>y+height)return;}else row=next;}
    if(row&&at<=y+height)ctx.fillText(row,x,at);
}

export function paintOverlays(ctx,overlays,stepId,selection,image,accent='#9274ff'){
    if(!selection)return;const [left,top,right,bottom]=selection.bounds,width=right-left,height=bottom-top;
    ctx.save();ctx.beginPath();
    if(selection.shape==='lasso'&&selection.points?.length>=3){selection.points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();}
    else ctx.rect(left,top,width,height);
    ctx.clip();ctx.setLineDash([]);ctx.lineWidth=Math.max(2,Math.min(width,height)/160);ctx.strokeStyle=accent;
    for(const item of overlays.filter(o=>o.step_id===stepId)){
        const x=left+item.start[0]*width,y=top+item.start[1]*height,ex=left+item.end[0]*width,ey=top+item.end[1]*height,w=ex-x,h=ey-y;
        if(item.kind==='arrow'){
            const angle=Math.atan2(ey-y,ex-x),head=Math.min(22,Math.hypot(w,h)*.25);ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(ex,ey);
            ctx.moveTo(ex-head*Math.cos(angle-.5),ey-head*Math.sin(angle-.5));ctx.lineTo(ex,ey);ctx.lineTo(ex-head*Math.cos(angle+.5),ey-head*Math.sin(angle+.5));ctx.stroke();
        }else if(item.kind==='box'){
            ctx.fillStyle='rgba(133,185,255,.16)';ctx.fillRect(x,y,w,h);
            ctx.strokeStyle='#85c4ff';ctx.lineWidth=Math.max(2,Math.min(width,height)/160);ctx.strokeRect(x,y,w,h);
            const clen=Math.max(8,Math.min(22,Math.min(w,h)*.26));
            ctx.strokeStyle='#ffffff';ctx.lineWidth=Math.max(3,Math.min(width,height)/120);
            ctx.beginPath();
            ctx.moveTo(x,y+clen);ctx.lineTo(x,y);ctx.lineTo(x+clen,y);
            ctx.moveTo(ex-clen,y);ctx.lineTo(ex,y);ctx.lineTo(ex,y+clen);
            ctx.moveTo(x,ey-clen);ctx.lineTo(x,ey);ctx.lineTo(x+clen,ey);
            ctx.moveTo(ex-clen,ey);ctx.lineTo(ex,ey);ctx.lineTo(ex,ey-clen);
            ctx.stroke();
            if(item.text){
                const label='📍 '+item.text,font=Math.max(11,Math.min(16,width/42));
                ctx.font='600 '+font+'px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif';
                const bw=ctx.measureText(label).width+18,bh=font*1.85;let bx=x+4,by=y-bh-6;
                if(by<top+4)by=y+6;if(bx+bw>right-4)bx=Math.max(left+4,right-bw-4);
                ctx.save();ctx.fillStyle='rgba(16,22,34,.94)';ctx.strokeStyle='#85c4ff';ctx.lineWidth=1.5;
                ctx.beginPath();
                if(ctx.roundRect)ctx.roundRect(bx,by,bw,bh,bh/2);else ctx.rect(bx,by,bw,bh);
                ctx.fill();ctx.stroke();
                ctx.fillStyle='#ffffff';ctx.fillText(label,bx+9,by+font*1.28);
                ctx.restore();
            }
        }
        else{
            ctx.fillStyle='rgba(20,25,36,.93)';ctx.fillRect(x,y,w,h);ctx.strokeRect(x,y,w,h);
            let textY=y+8,textH=h-16;
            if(item.kind==='card'&&item.photo&&image){
                const photoH=Math.max(0,h*.55),px=x+4,py=y+4,pw=Math.max(1,w-8),ph=Math.max(1,photoH-8);
                ctx.save();ctx.beginPath();
                if(selection.shape==='lasso'&&selection.points?.length>=3)selection.points.forEach(([sx,sy],i)=>{const tx=px+(sx-left)/width*pw,ty=py+(sy-top)/height*ph;i?ctx.lineTo(tx,ty):ctx.moveTo(tx,ty);});
                else ctx.rect(px,py,pw,ph);
                ctx.closePath();ctx.clip();ctx.drawImage(image,left,top,width,height,px,py,pw,ph);ctx.restore();
                textY=y+photoH;textH=h-photoH-4;
            }
            const font=Math.max(12,Math.min(22,w/14));ctx.font=font+'px Segoe UI, sans-serif';ctx.fillStyle='#fff';lines(ctx,item.text,x+8,textY,w-16,textH,font);
        }
    }
    ctx.restore();
}
