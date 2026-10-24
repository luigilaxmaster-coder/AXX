"""Windows rectangular capture to disk using the already bundled PyAV runtime."""
from __future__ import annotations
import ctypes
import hashlib
import os
from pathlib import Path
import threading
import time
import uuid
from .magic_pen import physical_dpi_context

ACTIVE = {'requesting', 'countdown', 'running', 'paused', 'stopping'}

def desktop_bounds():
    if os.name != 'nt':
        raise ValueError('La grabación de área requiere Windows.')
    with physical_dpi_context() as user:
        user.GetSystemMetrics.argtypes = [ctypes.c_int]
        user.GetSystemMetrics.restype = ctypes.c_int
        return tuple(user.GetSystemMetrics(i) for i in (76, 77, 78, 79))

def validate_region(raw, bounds=None):
    if not isinstance(raw, dict) or set(raw) != {'x','y','width','height'}:
        raise ValueError('Selecciona un rectángulo de pantalla válido.')
    if any(type(v) is not int for v in raw.values()):
        raise ValueError('El área debe usar coordenadas enteras.')
    x,y,w,h = (raw[k] for k in ('x','y','width','height'))
    bx,by,bw,bh = bounds or desktop_bounds()
    if w < 16 or h < 16 or w > 7680 or h > 4320 or x < bx or y < by or x+w > bx+bw or y+h > by+bh:
        raise ValueError('El área está fuera del escritorio o es demasiado pequeña/grande.')
    return {'x':x,'y':y,'width':w-w%2,'height':h-h%2}

class ScreenRecordingService:
    def __init__(self, root):
        self.root = Path(root).resolve() / 'recordings'
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.data = {'id':'','state':'ready','elapsedMs':0,'bytes':0,'error':'','path':'','region':None}

    def status(self):
        with self.lock:
            return dict(self.data)

    def start(self, body):
        if not isinstance(body,dict) or set(body)-{'region','fps','quality','countdown','maxMinutes'}:
            raise ValueError('Opciones de captura no válidas.')
        region = validate_region(body.get('region'))
        fps = body.get('fps',30)
        countdown = body.get('countdown',3)
        minutes = body.get('maxMinutes',15)
        quality = body.get('quality','balanced')
        if type(fps) is not int or fps not in (15,30,60) or type(countdown) is not int or countdown not in (0,3,5) or type(minutes) is not int or minutes not in (1,5,15,30) or quality not in ('light','balanced','detail'):
            raise ValueError('Calidad, duración o cuenta previa no válida.')
        with self.lock:
            if self.data['state'] in ACTIVE or self.thread and self.thread.is_alive():
                raise ValueError('Ya hay una grabación en curso.')
            self.stop_event.clear()
            self.data = {'id':uuid.uuid4().hex,'state':'requesting','elapsedMs':0,'bytes':0,'error':'','path':'','region':region,'fps':fps,'countdownLeft':countdown,'frames':0}
            self.thread = threading.Thread(target=self._record,args=(region,fps,quality,countdown,minutes),daemon=True)
            self.thread.start()
            return dict(self.data)

    def control(self, recording_id, command):
        with self.lock:
            if not recording_id or recording_id != self.data['id']:
                raise ValueError('La grabación ya no está activa.')
            state=self.data['state']
            if command=='stop':
                if state in ACTIVE:
                    self.data['state']='stopping'
                    self.stop_event.set()
            elif command=='pause' and state=='running':self.data['state']='paused'
            elif command=='resume' and state=='paused':self.data['state']='running'
            else:raise ValueError('Ese control no está disponible en este estado.')
            return dict(self.data)

    def open_result(self, recording_id, folder=False):
        with self.lock:
            if not recording_id or recording_id != self.data['id'] or self.data['state']!='finished':
                raise ValueError('Todavía no hay un vídeo guardado.')
            target=Path(self.data['path']).resolve()
            if target.parent != self.root or not target.is_file() or target.suffix!='.mp4':
                raise ValueError('El vídeo guardado ya no existe.')
        os.startfile(str(target.parent if folder else target))
        return {'opened':True}

    def _record(self, region, fps, quality, countdown, minutes):
        try:
            with physical_dpi_context():
                self._record_physical(region, fps, quality, countdown, minutes)
        except Exception as exc:
            with self.lock:
                self.data.update(state='error', error='No se pudo preparar la captura: ' + str(exc)[:400])

    def _record_physical(self, region, fps, quality, countdown, minutes):
        source=output=None
        partial=None
        frames=0
        try:
            import av
            self.root.mkdir(parents=True,exist_ok=True)
            target=self.root / ('Axx-'+time.strftime('%Y%m%d-%H%M%S')+'-'+self.data['id'][:8]+'.mp4')
            partial=target.with_suffix('.partial.mp4')
            with self.lock:
                if self.stop_event.is_set():self.data['state']='ready';return
                self.data['state']='countdown' if countdown else 'requesting'
            for remaining in range(countdown,0,-1):
                with self.lock:self.data['countdownLeft']=remaining
                if self.stop_event.wait(1):
                    with self.lock:self.data['state']='ready'
                    return
            if self.stop_event.is_set():
                with self.lock:self.data['state']='ready'
                return
            source=av.open('desktop',format='gdigrab',options={'framerate':str(fps),'offset_x':str(region['x']),'offset_y':str(region['y']),'video_size':f"{region['width']}x{region['height']}",'draw_mouse':'1'})
            output=av.open(str(partial),mode='w',format='mp4',options={'movflags':'frag_keyframe+empty_moov+default_base_moof'})
            stream=output.add_stream('libx264',rate=fps)
            stream.width=region['width'];stream.height=region['height'];stream.pix_fmt='yuv420p'
            stream.bit_rate={'light':1800000,'balanced':4500000,'detail':9000000}[quality]
            stream.options={'preset':'veryfast','tune':'zerolatency','g':str(fps*2)}
            active_time=0.0;previous=time.monotonic();last_pts=-1;was_running=True
            with self.lock:
                if not self.stop_event.is_set():self.data.update(state='running',countdownLeft=0)
            for frame in source.decode(video=0):
                now=time.monotonic()
                with self.lock:state=self.data['state']
                if self.stop_event.is_set():break
                if state=='running' and was_running:active_time+=now-previous
                previous=now;was_running=state=='running'
                if state=='paused':continue
                if active_time>=minutes*60:break
                pts=int(active_time*fps)
                if pts<=last_pts:continue
                frame=frame.reformat(width=stream.width,height=stream.height,format='yuv420p')
                from fractions import Fraction
                frame.pts=pts;frame.time_base=Fraction(1,fps)
                for packet in stream.encode(frame):output.mux(packet)
                frames+=1;last_pts=pts
                size=partial.stat().st_size
                with self.lock:self.data.update(elapsedMs=round(active_time*1000),bytes=size,frames=frames)
                if size>=4*1024**3:
                    with self.lock:self.data['error']='Se alcanzó el límite de 4 GB; vídeo finalizado.'
                    break
            with self.lock:self.data['state']='stopping'
            for packet in stream.encode():output.mux(packet)
            output.close();output=None
            source.close();source=None
            if not frames:raise ValueError('La captura terminó sin fotogramas. Selecciona otra área.')
            # Verify a decodable video before publishing the completed file.
            with av.open(str(partial)) as check:
                decoded=next(check.decode(video=0))
                if decoded.width!=region['width'] or decoded.height!=region['height']:raise ValueError('Resolución de vídeo incorrecta.')
            partial.replace(target)
            with target.open('rb') as file:digest=hashlib.file_digest(file,'sha256').hexdigest()
            with self.lock:self.data.update(state='finished',path=str(target),bytes=target.stat().st_size,sha256=digest,verified=True)
        except Exception as exc:
            with self.lock:self.data.update(state='error',error='No se pudo completar la grabación: '+str(exc)[:400])
        finally:
            for handle in (output,source):
                if handle:
                    try:handle.close()
                    except Exception:pass
            if partial and partial.exists():
                # A partial remains recoverable on disk, never reported as a completed video.
                with self.lock:self.data['partialPath']=str(partial)

    def close(self):
        self.stop_event.set()
        if self.thread:self.thread.join(8)
