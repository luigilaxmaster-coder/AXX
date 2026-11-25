"""Seed synthetic evidence only, inside a caller-supplied private QA profile."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PIL import Image
from backend.magic_pen import MagicPenService,write_json

out=Path(sys.argv[1]).resolve()
if not out.is_relative_to(ROOT/'build/three-pillars'):
    raise SystemExit('Fixture output must remain inside build/three-pillars')
data=out/'native-profile/local/Axx'
pen=MagicPenService(data/'artifacts',None)
capture=pen.acquire(Image.new('RGB',(400,300),'white'),{'id':'synthetic-native-fixture'})
plan={'schema_version':'1.0','kind':'presentation','title':'Mecanismo de prueba','summary':'Tres piezas sintéticas',
      'fidelity':'conceptual','steps':[{'id':'s1','title':'Piezas','body':'Tres piezas de una prueba sintética.',
          'basis':'inferred','narration':'Tres piezas.','focus':['a']}],
      'scene':{'fidelity':'conceptual','objects':[
          {'id':name,'label':name.upper(),'shape':shape,'size':[1,1,1],'position':[i*2,0,0],
           'color':'#438ee8','material':'plastic'} for i,(name,shape) in enumerate([('a','box'),('b','sphere'),('c','cylinder')])],
          'arrows':[]}}
capture['queries']=[{'id':'a'*32,'source_id':capture['id'],'revision':1,'state':'completed','format':'presentation','presentation':plan}]
write_json(pen.directory(capture['id'])/'document.json',capture)
pen.close()
repo=out/'project';repo.mkdir(parents=True,exist_ok=True)
(repo/'human.py').write_bytes(b'\xef\xbb\xbfVALUE = 1\r\n')
(repo/'calc.py').write_text('def add(a, b):\n    return a - b\n',encoding='utf-8')
(repo/'test_calc.py').write_text('import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n    def test_sum(self): self.assertEqual(add(2,3),5)\n',encoding='utf-8')
(repo/'helpers.py').write_text('def helper():\n    return 42\n',encoding='utf-8')
(repo/'lsp_case.py').write_text('from helpers import helper\nanswer = helper()\nprint(missing_name)\n',encoding='utf-8')
(repo/'debug_case.py').write_text('value = 40\nanswer = value + 2\nprint(answer)\n',encoding='utf-8')
for args in (['init','-q'],['config','core.autocrlf','false'],['add','.'],['commit','-qm','Native acceptance fixture']):
    identity=[]
    if args[0]=='commit':
        for field in ('user.name','user.email'):
            value=subprocess.check_output(['git','config','--get',field],cwd=ROOT,text=True).strip()
            identity.extend(['-c',field+'='+value])
    result=subprocess.run(['git',*identity,*args],cwd=repo,capture_output=True)
    if result.returncode:raise RuntimeError(result.stderr.decode('utf-8',errors='replace'))
print(json.dumps({'capture_id':capture['id'],'data_directory':str(data),'project':str(repo)}))
