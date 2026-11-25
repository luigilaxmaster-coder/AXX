import base64
import json
from pathlib import Path
import struct
import tempfile
import unittest

from backend.spatial.mesh_export import export_renderer_glb
from backend.spatial.offline_glb import validate_offline_glb
from backend.spatial.asset_registry import AssetGateError, AssetSecurityError
from backend.spatial.scene_document import import_presentation_plan_v1
from backend.tests.test_acts_inference import _Server


def triangle():
    scene=import_presentation_plan_v1({'scene':{'objects':[
        {'id':'part','shape':'box','size':[1,1,1],'position':[0,0,0],'color':'#ff0000'}]}},document_id='scene',source_id='file')
    raw,_=export_renderer_glb(scene,[{'object_id':'part','positions_b64':base64.b64encode(struct.pack('<9f',0,0,0,1,0,0,0,1,0)).decode(),
        'indices_b64':base64.b64encode(struct.pack('<3I',0,1,2)).decode(),
        'material':{'color':[1,0,0],'roughness':.4,'metalness':.5,'opacity':1}}])
    return scene,raw


def rewrite(raw,change):
    length=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+length]);change(doc)
    payload=json.dumps(doc).encode();payload+=b' '*(-len(payload)%4)
    tail=raw[20+length:]
    return struct.pack('<III',0x46546C67,2,20+len(payload)+len(tail))+struct.pack('<II',len(payload),0x4E4F534A)+payload+tail


class OfflineGlbTests(unittest.TestCase):
    def test_real_mesh_admission_rejects_uri_overrun_cycles_and_invented_budgets(self):
        _,raw=triangle()
        self.assertEqual(validate_offline_glb(raw)['triangle_count'],1)
        with self.assertRaises(AssetSecurityError):
            validate_offline_glb(rewrite(raw,lambda d:d['buffers'][0].update(uri='texture.bin')))
        with self.assertRaises(AssetGateError):
            validate_offline_glb(rewrite(raw,lambda d:d['accessors'][0].update(count=750001)))
        with self.assertRaises(AssetGateError):
            validate_offline_glb(rewrite(raw,lambda d:d['nodes'][0].update(children=[0])))

    def test_register_uses_actual_mesh_budget_and_cache_load_rechecks_immutable_hash(self):
        scene,raw=triangle()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            srv=_Server(Path(tmp),[])
            try:
                for flag in ('magic_scene_v2','asset_gate_mcp_v1'):srv.rt.flags.set_flag(flag,True,reason='GLB test')
                srv.rt.scenes.create_document(scene)
                code,result=srv.api.request('POST','/axx-api/spatial/v2/assets/register',{
                    'filename':'triangle.glb','content_b64':base64.b64encode(raw).decode(),'license_id':'internal','triangle_count':0})
                self.assertEqual(code,200,result)
                self.assertEqual(result['asset']['triangle_count'],1)
                aid=result['asset']['asset_id']
                body={'asset_id':aid,'document_id':'scene','base_revision':1,'operation_id':'insert'}
                code,added=srv.api.request('POST','/axx-api/spatial/v2/assets/insert-glb',body)
                self.assertEqual(code,200,added)
                self.assertEqual(len(added['document']['objects']),2)
                self.assertEqual(srv.api.request('POST','/axx-api/spatial/v2/assets/insert-glb',body),(200,added))
                Path(result['asset']['storage_path']).write_bytes(raw[:-1]+b'!')
                self.assertNotEqual(srv.api.request('POST','/axx-api/spatial/v2/assets/load',{'asset_id':aid})[0],200)
            finally:srv.close()
