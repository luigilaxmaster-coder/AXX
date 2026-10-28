/* Keep desktop geometry, motion and lighting; rasterize the same mesh on the GPU. */
(()=>{
  'use strict';
  const noop=()=>{};
  class MobileRenderer extends Axx.SoftwareRenderer {
    constructor(canvas,settings){
      super(canvas,settings);
      this.surface=document.createElement('canvas');
      this.gl=this.surface.getContext('webgl',{alpha:true,antialias:true,premultipliedAlpha:false});
      this.accelerated=false;
      if(!this.gl)return;
      this.surface.addEventListener('webglcontextlost',event=>{event.preventDefault();this.accelerated=false;this.lastDrawnSignature='';});
      this.surface.addEventListener('webglcontextrestored',()=>this.initialize());
      this.initialize();
    }
    initialize(){
      const gl=this.gl;
      try{
        const shader=(type,source)=>{
          const value=gl.createShader(type);gl.shaderSource(value,source);gl.compileShader(value);
          if(!gl.getShaderParameter(value,gl.COMPILE_STATUS)){gl.deleteShader(value);throw Error('Shader compilation failed');}
          return value;
        };
        const vertex=shader(gl.VERTEX_SHADER,`attribute vec3 point;attribute vec3 normal;uniform vec2 size;varying vec3 n;
          void main(){float w=1.0/point.z;gl_Position=vec4((point.x/size.x*2.0-1.0)*w,(1.0-point.y/size.y*2.0)*w,-1.0,w);n=normal/point.z;}`);
        const precision=gl.getShaderPrecisionFormat(gl.FRAGMENT_SHADER,gl.HIGH_FLOAT).precision?'highp':'mediump';
        const fragment=shader(gl.FRAGMENT_SHADER,`precision ${precision} float;varying vec3 n;uniform sampler2D lighting;uniform int view;
          void main(){vec3 v=normalize(n);if(v.z<0.0)v=-v;
            if(view==2)gl_FragColor=vec4(v*0.5+0.5,1.0);
            else if(view==1){float l=clamp(0.20+v.y*0.25-v.x*0.14+v.z*0.64,0.08,1.0);gl_FragColor=vec4(vec3(180.0,193.0,210.0)*l/255.0,1.0);}
            else gl_FragColor=texture2D(lighting,((v.xy*0.5+0.5)*511.0+0.5)/512.0);}`);
        this.program=gl.createProgram();gl.attachShader(this.program,vertex);gl.attachShader(this.program,fragment);gl.linkProgram(this.program);
        gl.deleteShader(vertex);gl.deleteShader(fragment);
        if(!gl.getProgramParameter(this.program,gl.LINK_STATUS))throw Error('Shader link failed');
        this.point=gl.getAttribLocation(this.program,'point');this.normal=gl.getAttribLocation(this.program,'normal');
        this.size=gl.getUniformLocation(this.program,'size');this.view=gl.getUniformLocation(this.program,'view');
        this.texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,this.texture);
        for(const parameter of [gl.TEXTURE_MIN_FILTER,gl.TEXTURE_MAG_FILTER])gl.texParameteri(gl.TEXTURE_2D,parameter,gl.LINEAR);
        for(const parameter of [gl.TEXTURE_WRAP_S,gl.TEXTURE_WRAP_T])gl.texParameteri(gl.TEXTURE_2D,parameter,gl.CLAMP_TO_EDGE);
        this.grids=new WeakMap();this.textureKey=null;this.accelerated=true;this.lastDrawnSignature='';
      }catch(error){this.accelerated=false;console.warn('Axx: GPU unavailable, using the desktop-compatible renderer.',error.message);}
    }
    project(grid,rotate=true){
      if(!this.gpuFrame)return super.project(grid,rotate);
      const triangle=this.raster.triangle;
      this.raster.triangle=noop;
      try{super.project(grid,rotate);}finally{this.raster.triangle=triangle;}
      const gl=this.gl;
      let buffers=this.grids.get(grid);
      if(!buffers){
        const indices=new Uint16Array(grid.u*grid.v*6);let at=0;
        for(let y=0;y<grid.v;y++)for(let x=0;x<grid.u;x++){
          const i=y*(grid.u+1)+x,s=grid.u+1;indices.set([i,i+1,i+s,i+1,i+s+1,i+s],at);at+=6;
        }
        buffers={vertices:gl.createBuffer(),indices:gl.createBuffer(),count:indices.length};
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,buffers.indices);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,indices,gl.STATIC_DRAW);
        this.grids.set(grid,buffers);
      }
      gl.bindBuffer(gl.ARRAY_BUFFER,buffers.vertices);gl.bufferData(gl.ARRAY_BUFFER,grid.projected,gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(this.point);gl.vertexAttribPointer(this.point,3,gl.FLOAT,false,24,0);
      gl.enableVertexAttribArray(this.normal);gl.vertexAttribPointer(this.normal,3,gl.FLOAT,false,24,12);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,buffers.indices);gl.drawElements(gl.TRIANGLES,buffers.count,gl.UNSIGNED_SHORT,0);
    }
    draw(time){
      // The desktop's diagnostic wireframe stays on its original rasterizer.
      if(!this.accelerated||this.gl.isContextLost()||this.studio.view===3)return super.draw(time);
      const started=performance.now(),gl=this.gl,r=this.canvas.getBoundingClientRect(),parent=this.canvas.parentElement.getBoundingClientRect();
      this.lastTime=time;
      try{
        if(this.surface.width!==this.raster.width||this.surface.height!==this.raster.height){this.surface.width=this.raster.width;this.surface.height=this.raster.height;}
        this.layout={cx:(parent.left+parent.width/2-r.left)*this.raster.width/Math.max(1,r.width),cy:(parent.top+parent.height/2-r.top)*this.raster.width/Math.max(1,r.width),unit:Math.min(parent.width,parent.height)/3.52*this.settings.scale*this.raster.width/Math.max(1,r.width)};
        this.shadeTable();gl.useProgram(this.program);gl.viewport(0,0,this.surface.width,this.surface.height);
        gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LESS);gl.disable(gl.CULL_FACE);gl.disable(gl.BLEND);
        gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
        gl.uniform2f(this.size,this.surface.width,this.surface.height);gl.uniform1i(this.view,this.studio.view);
        gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,this.texture);
        if(this.textureKey!==this.lutKey){gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,512,512,0,gl.RGBA,gl.UNSIGNED_BYTE,this.lut);this.textureKey=this.lutKey;}
        gl.uniform1i(gl.getUniformLocation(this.program,'lighting'),0);
        this.gpuFrame=true;
        try{this.body();this.orbit();this.droplets();this.tendril();}finally{this.gpuFrame=false;}
        this.ctx.clearRect(0,0,this.canvas.width,this.canvas.height);this.ctx.imageSmoothingEnabled=true;
        this.ctx.drawImage(this.surface,0,0,this.canvas.width,this.canvas.height);
        this.drawMs=performance.now()-started;
      }catch(error){this.gpuFrame=false;this.accelerated=false;console.warn('Axx: compatible rendering restored.',error.message);super.draw(time);}
    }
    hitMask(cols=64,rows=64){
      if(!this.accelerated||this.studio.view===3)return super.hitMask(cols,rows);
      cols=Math.round(Axx.clamp(cols,8,128));rows=Math.round(Axx.clamp(rows,8,128));
      const {width,height}=this.canvas,data=this.ctx.getImageData(0,0,width,height).data,bits=[];
      for(let y=0;y<rows;y++)for(let x=0;x<cols;x++)bits.push(data[(Math.min(height-1,Math.floor((y+.5)*height/rows))*width+Math.min(width-1,Math.floor((x+.5)*width/cols)))*4+3]>16?1:0);
      const r=this.canvas.getBoundingClientRect();return {width:r.width,height:r.height,cols,rows,bits};
    }
    hitTest(x,y){
      if(!this.accelerated||this.studio.view===3)return super.hitTest(x,y);
      const r=this.canvas.getBoundingClientRect(),px=Math.floor((x-r.left)/r.width*this.canvas.width),py=Math.floor((y-r.top)/r.height*this.canvas.height);
      return px>=0&&py>=0&&px<this.canvas.width&&py<this.canvas.height&&this.ctx.getImageData(px,py,1,1).data[3]>16;
    }
    pixelSummary(){const mask=this.hitMask();return {solid:mask.bits.reduce((a,b)=>a+b,0),centerAlpha:this.ctx.getImageData(Math.floor(this.canvas.width/2),Math.floor(this.canvas.height/2),1,1).data[3],width:this.canvas.width,height:this.canvas.height};}
    diagnostics(){return {...super.diagnostics(),renderer:this.accelerated&&this.studio.view!==3?'GPU · geometría y material del PC':'CPU · modo compatible',mode:this.accelerated&&this.studio.view!==3?'gpu':'compatible'};}
  }
  Axx.MobileRenderer=MobileRenderer;
})();
