import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import psutil
from backend.actions import windows_automation as uia
from backend.actions.executor import ActionExecutor
from backend.magic_pen import MagicPenService, monitors


@unittest.skipUnless(os.environ.get('AXX_TEST_DESKTOP_OCR_NATIVE')=='1','Opt-in visible owned OCR fixture')
class DesktopOcrNativeTests(unittest.TestCase):
    def test_observed_window_capture_to_local_ocr(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            script=root/'window.py'
            script.write_text("import tkinter as tk\nr=tk.Tk();r.title('Axx OCR native fixture');r.geometry('1050x260+40+40');r.configure(bg='white');r.attributes('-topmost',True)\ntk.Label(r,text='Año 2026 - revisión técnica\\nÁrea 12,50 m² - longitud 3,25 m\\nNO borrar plano_ñ.ifc',font=('Arial',26),bg='white',fg='black',justify='left').pack(padx=24,pady=30)\nr.mainloop()\n",encoding='utf-8')
            process=subprocess.Popen([sys.executable,str(script)],creationflags=subprocess.CREATE_NO_WINDOW)
            service=MagicPenService(root)
            try:
                window=None
                for _ in range(80):
                    owned={process.pid,*[p.pid for p in psutil.Process(process.pid).children(recursive=True)]}
                    window=next((w for w in uia.list_windows() if w['pid'] in owned and w['title']=='Axx OCR native fixture'),None)
                    if window: break
                    time.sleep(.1)
                self.assertIsNotNone(window)
                time.sleep(.5)
                with ActionExecutor(root/'state.db',root) as executor:
                    executor.capture_service=service
                    observed=executor.execute_action('computer_observe',{'window_id':window['window_id'],'pid':window['pid'],'monitor_id':monitors()[0]['id']})
                    self.assertEqual(observed['state'],'succeeded',observed)
                    result=executor.execute_action('computer_ocr',{'window_id':window['window_id'],'pid':window['pid'],'observation_id':observed['output']['observation_id']})
                    self.assertEqual(result['state'],'succeeded',result)
                    self.assertIn('NO borrar plano_ñ.ifc',' '.join(result['output']['text'].split()))
                    self.assertIn('12,50',result['output']['text'])
                    self.assertEqual(result['output']['transform']['scale_x'],1)
                report=Path(__file__).resolve().parents[2]/'evidence/mcp-expansion-20261026/desktop-ocr.json'
                report.write_text(json.dumps({'source_only':True,'fixture_only':True,'text':result['output']['text'],'transform':result['output']['transform'],'postconditions_passed':result['postconditions_passed']},ensure_ascii=False,indent=2),encoding='utf-8')
            finally:
                for child in psutil.Process(process.pid).children(recursive=True): child.terminate()
                process.terminate(); process.wait(timeout=5)
                service.close()
