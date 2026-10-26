"""Render a selected scene/camera from a copied blend file with a literal object position."""
import json
import math
from pathlib import Path
import shutil
import tempfile
import threading

from .file_inspection import validate_path, hash_file
from .process_runner import _artifact_path, run_process
from .cli_blender import find_blender


# Fixed code; user values are read from JSON, never interpolated into Python.
SCRIPT = '''
import bpy,json,sys
from pathlib import Path
p=Path(sys.argv[sys.argv.index('--')+1]); d=json.loads(p.read_text(encoding='utf-8'))
bpy.ops.wm.open_mainfile(filepath=d['source'],load_ui=False,use_scripts=False)
if bpy.data.libraries: raise ValueError('Linked libraries are not supported')
if any(image.source=='FILE' and image.filepath and not image.packed_file for image in bpy.data.images): raise ValueError('Pack external textures before rendering a private copy')
scene=bpy.data.scenes.get(d['scene'])
if scene is None: raise ValueError('Exact scene not found')
camera=scene.objects.get(d['camera']); obj=scene.objects.get(d['object'])
if camera is None or camera.type!='CAMERA' or obj is None: raise ValueError('Exact camera/object not found')
if obj.animation_data or obj.constraints or obj.parent: raise ValueError('Animated/constrained/parented targets require a specialized adapter')
obj.location=d['position']; scene.camera=camera
scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=8
scene.render.resolution_x=d['width']; scene.render.resolution_y=d['height']; scene.render.resolution_percentage=100
scene.render.use_compositing=False; scene.render.use_sequencer=False
scene.render.image_settings.file_format='PNG'
scene.render.filepath=str(p.parent/'render.png')
bpy.ops.wm.save_as_mainfile(filepath=str(p.parent/'scene.blend'),copy=True)
bpy.ops.render.render(write_still=True,scene=scene.name)
(p.parent/'readback.json').write_text(json.dumps({'scene':scene.name,'camera':scene.camera.name,'object':obj.name,'position':list(obj.location),'width':scene.render.resolution_x,'height':scene.render.resolution_y}),encoding='utf-8')
'''


def checked_inputs(inputs):
    if not isinstance(inputs,dict) or set(inputs) != {'source','destination','scene','camera','object','position','width','height'}:
        raise ValueError('Indica archivo, destino, escena, cámara, objeto, posición y dimensiones exactos')
    source=validate_path(inputs['source'])
    if source.suffix.lower()!='.blend' or source.stat().st_size>100*1024*1024: raise ValueError('Selecciona un blend local de hasta 100 MiB')
    for key in ('scene','camera','object'):
        if not isinstance(inputs[key],str) or not 1<=len(inputs[key])<=200 or '\0' in inputs[key]: raise ValueError('Nombre Blender inválido')
    position=inputs['position']
    if not isinstance(position,list) or len(position)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>100000 for v in position):
        raise ValueError('Posición debe contener tres números finitos acotados')
    for key in ('width','height'):
        if type(inputs[key]) is not int or not 64<=inputs[key]<=2048: raise ValueError('Dimensión fuera de 64–2048 píxeles')
    target=inputs['destination']
    if not isinstance(target,str) or not target or Path(target).is_absolute() or Path(target).drive or '..' in Path(target).parts:
        raise ValueError('Indica una carpeta nueva relativa al workspace')
    return hash_file(str(source),threading.Event())


class BlenderSceneTool:
    name,version='blender_scene_render','1.0.0'
    description='Render exact scene/camera and static object position on a private Blender copy'

    def verify_preconditions(self,inputs):
        try:
            checked_inputs(inputs); find_blender()
            return True,'Archivo y parámetros Blender comprobados'
        except Exception as exc: return False,str(exc)[:600]

    def execute_cancellable(self,inputs,workspace_root,cancelled):
        from .tools import ToolResult
        from PIL import Image
        created=[]
        try:
            before=checked_inputs(inputs); target=_artifact_path(inputs['destination'],workspace_root)
            if target.exists(): raise ValueError('El destino ya existe')
            with tempfile.TemporaryDirectory(prefix='axx-blender-') as folder:
                staging=Path(folder); source=staging/'input.blend'; shutil.copyfile(inputs['source'],source)
                if hash_file(str(source),cancelled)['sha256']!=before['sha256']: raise ValueError('El origen cambió al copiarlo')
                request=staging/'request.json'; request.write_text(json.dumps(inputs|{'source':str(source)}),encoding='utf-8')
                script=staging/'render.py'; script.write_text(SCRIPT,encoding='utf-8')
                process=run_process({'executable':str(find_blender()),'args':['--background','--factory-startup','--disable-autoexec','--threads','2','--python-exit-code','9','--python',str(script),'--',str(request)],'cwd':str(staging),'timeout_s':120},staging,cancelled)
                if not process['success']: raise ValueError(process['error'])
                observed=json.loads((staging/'readback.json').read_text())
                if any(observed[k]!=inputs[k] for k in ('scene','camera','object','width','height')) or any(not math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-6) for a,b in zip(observed['position'],inputs['position'])):
                    raise ValueError('La escena renderizada no coincide con la solicitud')
                with Image.open(staging/'render.png') as image:
                    if image.format!='PNG' or image.size!=(inputs['width'],inputs['height']): raise ValueError('PNG de dimensiones incorrectas')
                    image.load()
                if hash_file(inputs['source'],cancelled)!=before: raise ValueError('El archivo original cambió')
                if cancelled.is_set(): raise ValueError('Cancelado antes de publicar')
                target.mkdir(parents=True,exist_ok=False); created.append(str(target))
                files=[]
                for name in ('scene.blend','render.png'):
                    output=_artifact_path(str(target/name),workspace_root)
                    with (staging/name).open('rb') as reader, output.open('xb') as writer:
                        created.append(str(output))
                        while chunk:=reader.read(1024*1024):
                            if cancelled.is_set(): raise ValueError('Cancelado publicando; se conservan archivos parciales')
                            writer.write(chunk)
                    files.append(hash_file(str(output),cancelled))
            return ToolResult(True,output={'files':files,'scene':observed,'source_sha256':before['sha256'],'visual_quality_verified':False},evidence={'verification':'blender_scene_and_decoded_png'})
        except Exception as exc:
            return ToolResult(False,error=str(exc)[:600],evidence={'created_paths':created,'effect_uncertain':bool(created),'cancelled':cancelled.is_set()})

    def verify_postconditions(self,inputs,result):
        try:
            return bool(result.success and hash_file(inputs['source'],threading.Event())['sha256']==result.output['source_sha256'] and all(hash_file(row['path'],threading.Event())['sha256']==row['sha256'] for row in result.output['files'])), 'Escena, PNG y origen comprobados'
        except Exception: return False,'No se pudo comprobar el resultado'
