import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from backend.actions.blender_scene import BlenderSceneTool, checked_inputs
from backend.actions.cli_blender import find_blender
from backend.actions.executor import ActionExecutor
from backend.actions.process_runner import run_process


class BlenderSceneTests(unittest.TestCase):
    def test_invalid_position_and_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.blend'; source.write_bytes(b'fixture')
            inputs={'source':str(source),'destination':'result','scene':'Scene','camera':'Camera','object':'Cube','position':[0,0,0],'width':128,'height':128}
            checked_inputs(inputs)
            for patch in ({'position':[float('nan'),0,0]},{'destination':'../outside'},{'width':True},{'position':[True,0,0]}):
                with self.assertRaises(ValueError): checked_inputs(inputs|patch)

    @unittest.skipUnless(os.environ.get('AXX_TEST_BLENDER_NATIVE')=='1','Opt-in installed Blender')
    def test_real_copy_transform_render_and_original_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source.blend'; script=root/'fixture.py'
            script.write_text('import bpy\nbpy.ops.wm.save_as_mainfile(filepath='+repr(str(source))+')\n',encoding='utf-8')
            fixture=run_process({'executable':str(find_blender()),'args':['--background','--factory-startup','--disable-autoexec','--python-exit-code','9','--python',str(script)],'cwd':str(root),'timeout_s':60},root)
            self.assertTrue(fixture['success'],fixture)
            inputs={'source':str(source),'destination':'result','scene':'Scene','camera':'Camera','object':'Cube','position':[.25,0,0],'width':128,'height':128}
            before=source.read_bytes()
            with ActionExecutor(root/'state.db',root) as executor:
                result=executor.execute_action('blender_scene_render',inputs)
                self.assertEqual(result['state'],'succeeded',result)
                self.assertEqual(source.read_bytes(),before)
                replay=executor.execute_action('blender_scene_render',inputs)
                self.assertEqual(replay['state'],'failed')
            report=Path(__file__).resolve().parents[2]/'evidence/mcp-expansion-20261026/blender-scene.json'
            report.write_text(json.dumps({'source_only':True,'receipt':result},ensure_ascii=False,indent=2),encoding='utf-8')
