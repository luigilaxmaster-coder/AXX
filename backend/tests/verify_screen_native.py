"""Real Windows GDI -> PyAV -> MP4 test against an owned solid-color window."""
import ctypes
import json
import tempfile
import time
import tkinter as tk
from pathlib import Path
import av
from backend.screen_recording import ScreenRecordingService

ctypes.windll.user32.SetProcessDPIAware()
root=tk.Tk();root.overrideredirect(True);root.geometry('320x240+80+80');root.configure(background='#22bb66');root.attributes('-topmost',True);root.update()
service=None
try:
    with tempfile.TemporaryDirectory() as directory:
        service=ScreenRecordingService(Path(directory))
        def wait(predicate,seconds=10):
            until=time.monotonic()+seconds
            while time.monotonic()<until:
                root.update();s=service.status()
                if predicate(s):return s
                if s['state']=='error':raise AssertionError(s['error'])
                time.sleep(.02)
            raise AssertionError(service.status())
        s=service.start({'region':{'x':100,'y':100,'width':200,'height':160},'fps':15,'countdown':0,'quality':'balanced','maxMinutes':1})
        rid=s['id'];wait(lambda s:s['frames']>10)
        service.control(rid,'pause');time.sleep(.15);paused=service.status()['frames'];time.sleep(.4)
        assert service.status()['frames']==paused
        service.control(rid,'resume');wait(lambda s:s['frames']>paused+8)
        service.control(rid,'stop');s=wait(lambda s:s['state']=='finished')
        with av.open(s['path']) as video:
            frame=next(video.decode(video=0));pixel=frame.to_ndarray(format='rgb24')[50,50]
            assert frame.width==200 and frame.height==160
            assert abs(int(pixel[0])-34)<15 and abs(int(pixel[1])-187)<15 and abs(int(pixel[2])-102)<15,pixel
        report={'windows_gdi':True,'resolution':[frame.width,frame.height],'pixel':[int(v) for v in pixel],'frames':s['frames'],'bytes':s['bytes'],'verified':s['verified'],'pause_resume':True,'sha256':s['sha256']}
        out=Path('evidence/area-recording-20261021');out.mkdir(parents=True,exist_ok=True);(out/'native.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
finally:
    if service:service.close()
    root.destroy()
