"""Ephemeral visual evidence; the existing Windows owner remains the only input path."""
import base64
import hashlib
import io
import time
import uuid

from PIL import Image, ImageDraw, ImageGrab
from .actions import windows_automation as uia
from .actions.desktop_input import _interactive_session
from .magic_pen import physical_dpi_context

TARGETED_WINDOW_OBSERVATION = True


def region(shot, box):
    if (not isinstance(box,list) or len(box)!=4 or any(type(n) is not int for n in box)
            or not 0<=box[0]<box[2]<=shot['width'] or not 0<=box[1]<box[3]<=shot['height']):
        raise ValueError('La región de comprobación debe ser [izquierda, arriba, derecha, abajo] dentro de la imagen.')
    with Image.open(io.BytesIO(shot['jpeg'])) as im:return im.crop(tuple(box)).tobytes()


def same_target(old, new, x, y):
    if (old['width'],old['height'],old.get('image_bounds'))!=(new['width'],new['height'],new.get('image_bounds')):return False
    if type(x) is not int or type(y) is not int or not 0<=x<old['width'] or not 0<=y<old['height']:
        raise ValueError('Punto fuera de la imagen autorizada.')
    box=[max(0,x-8),max(0,y-8),min(old['width'],x+9),min(old['height'],y+9)]
    return region(old,box)==region(new,box)


def capture(grant, identity, event, *, overview=False, hidden=()):
    if event.is_set():raise ValueError('Captura cancelada.')
    user,kernel=uia._windows_api();_interactive_session(user,kernel,grant['pid'])
    bounds=identity['window_bounds']
    if overview:
        screens=identity['monitors']
        if not screens:raise ValueError('No hay pantallas observables.')
        x,y=min(m['x'] for m in screens),min(m['y'] for m in screens)
        right=max(m['x']+m['width'] for m in screens);bottom=max(m['y']+m['height'] for m in screens)
        bounds={'x':x,'y':y,'width':right-x,'height':bottom-y}
        if bounds['width']*bounds['height']>34000000:raise ValueError('El escritorio supera el tamaño de captura permitido; enfoca una aplicación.')
        masks=[uia.observe_geometry(w['window_id'])['window_bounds'] for w in hidden]
        with physical_dpi_context():im=ImageGrab.grab(bbox=(x,y,right,bottom),all_screens=True)
        if im.size!=(bounds['width'],bounds['height']):raise ValueError('Cambió el tamaño del escritorio durante la captura.')
        for w,box in zip(hidden,masks):
            if uia.observe_geometry(w['window_id'])['window_bounds']!=box:raise ValueError('Cambió una superficie protegida durante la captura.')
            ImageDraw.Draw(im).rectangle((box['x']-x,box['y']-y,box['x']+box['width']-x,box['y']+box['height']-y),fill='black')
        im.thumbnail((1280,1280),Image.Resampling.LANCZOS);buffer=io.BytesIO();im.convert('RGB').save(buffer,format='JPEG',quality=80);jpeg=buffer.getvalue()
    else:
        captured=uia.capture_window(grant['window_id'],grant['pid'],grant['birth'],cancelled=event)
        if captured['window_bounds']!=bounds:raise ValueError('La geometría cambió durante la captura; observa de nuevo.')
        jpeg=base64.b64decode(captured['jpeg'],validate=True)
    after=uia.observe_geometry(grant['window_id'])
    if (any(after[k]!=identity[k] for k in ('window_bounds','monitors')) or event.is_set()
            or uia.process_started(grant['pid'])!=grant['birth']):
        raise ValueError('La geometría o el proceso cambió durante la captura; observa de nuevo.')
    with Image.open(io.BytesIO(jpeg)) as frame:
        frame.load();width,height=frame.size
        if frame.convert('L').getextrema()==(0,0):raise ValueError('La captura está negra; no se enviará como una pantalla observable.')
    if len(jpeg)>350000 or max(width,height)>1280:raise ValueError('La captura excede el límite de envío; enfoca una aplicación.')
    return {'jpeg':jpeg,'width':width,'height':height,'image_bounds':bounds,'hash':hashlib.sha256(jpeg).hexdigest(),'at':time.monotonic()}


def observe(grant,event,*,overview=False,hidden=(),on_observation=None):
    if on_observation is not None and not callable(on_observation):raise ValueError('Registro de observación inválido.')
    rows=[w for w in uia.list_windows(include_untitled=True,include_titles=False) if w['window_id']==grant['window_id'] and w['pid']==grant['pid']]
    if len(rows)!=1:raise ValueError('La ventana observada ya no existe.')
    geometry=uia.observe_geometry(grant['window_id'])
    if geometry.get('minimized') or uia.process_started(grant['pid'])!=grant['birth']:raise ValueError('La ventana no está disponible para observar.')
    title=uia.read_window_title(grant['window_id'],grant['pid'],grant['birth'],cancelled=event)
    warning=None
    try:
        if title:observed=uia.read_window_content(grant['window_id'],grant['pid'],title,cancelled=event,full_window=True,timeout=5)
        else:observed=uia._uia({'operation':'inspect','window_id':grant['window_id'],'pid':grant['pid']},cancelled=event,timeout=5)
    except ValueError as exc:
        if 'UI Automation excedió el límite' not in str(exc) or event.is_set():raise
        warning='Accesibilidad lenta: se conserva la imagen real; no se inventan controles.'
        observed={'window_title':title,'controls':[],'truncated':True,'focused_control_id':None,'observation':{
            **geometry,'window_id':grant['window_id'],'pid':grant['pid'],'process_started':grant['birth'],
            'observation_id':uuid.uuid4().hex,'session_id':uia.OBSERVATION_SESSION_ID,'completed_monotonic':time.monotonic(),'source':'windows_visual'}}
        uia._remember_observation(observed)
    if on_observation is not None:on_observation(observed)
    identity=observed['observation']
    if any(identity[k]!=geometry[k] for k in ('window_bounds','monitors')):raise ValueError('La geometría cambió durante la observación.')
    shot=capture(grant,identity,event,overview=overview,hidden=hidden)
    shot.update(id=identity['observation_id'],observed=observed,overview=overview)
    output={'observation_id':shot['id'],'window_id':grant['window_id'],'pid':grant['pid'],'title':observed['window_title'],
        'image_width':shot['width'],'image_height':shot['height'],'image_bounds':shot['image_bounds'],'image_scope':'desktop' if overview else 'window',
        'window_bounds':identity['window_bounds'],'truncated':bool(observed.get('truncated')),'focused_control_id':observed.get('focused_control_id'),
        'controls':[{k:r.get(k) for k in ('control_id','name','value','text','control_type','bounds','enabled','offscreen','patterns','state','read_only')} for r in observed['controls']],
        'image_sha256':shot['hash'],'accessibility_warning':warning}
    return shot,output
