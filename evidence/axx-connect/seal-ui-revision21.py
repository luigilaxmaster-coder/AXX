"""Seal only the reviewed frontend delta after immutable source V2."""
from datetime import datetime, timezone
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'evidence/axx-connect'
BASE=EVIDENCE/'overlay-revision2'
OUT=EVIDENCE/'overlay-revision21-ui'
FILES=('1.AXX/scripts/axx-connect.js','1.AXX/scripts/test-axx-connect.cjs')
SHA=lambda data:hashlib.sha256(data).hexdigest()


def main():
    if OUT.exists():
        raise FileExistsError('The frontend delta is immutable; use a new revision.')
    log=EVIDENCE/'ui-connect-tests-revision21.log'
    tests=json.loads(log.read_text(encoding='utf-8-sig'))
    assert tests['passed']>=33 and tests['uncaught_errors']==[]
    manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    # All previously frozen product/docs/plugin files except this explicit delta
    # must still match. The separate prepared isolation harness is not in V2.
    for item in manifest['files']:
        if item['path'] not in FILES:
            assert SHA((ROOT/item['path']).read_bytes())==item['sha256'],item['path']
    records,patches=[],[]
    for relative in FILES:
        before=(BASE/'sources'/relative).read_bytes();after=(ROOT/relative).read_bytes()
        records.append({'path':relative,'base_sha256':SHA(before),'sha256':SHA(after),'bytes':len(after)})
        patches.append(''.join(difflib.unified_diff(before.decode('utf-8-sig').splitlines(keepends=True),
            after.decode('utf-8-sig').splitlines(keepends=True),fromfile='a/'+relative,tofile='b/'+relative)))
    patch=''.join(patches)
    spec=importlib.util.spec_from_file_location('freeze_helper',EVIDENCE/'prepare-revision2.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    for item in records:
        reconstructed=helper.reconstruct((BASE/'sources'/item['path']).read_bytes(),helper.sections(patch)[item['path']])
        assert SHA(reconstructed)==item['sha256'],item['path']
    OUT.mkdir()
    (OUT/'ui-v2-v21.patch').write_text(patch,encoding='utf-8',newline='\n')
    receipts=[]
    for name in ('ui-connect-tests-revision21.log','ui-connect-settings-controlled-revision21.json',
                 'ui-connect-settings-controlled-revision21.png'):
        data=(EVIDENCE/name).read_bytes();(OUT/name).write_bytes(data)
        receipts.append({'path':name,'sha256':SHA(data),'bytes':len(data)})
    for relative in FILES:
        destination=OUT/'sources'/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes((ROOT/relative).read_bytes())
    result={'revision':'V2.1 frontend only','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'baseline':'overlay-revision2 / immutable ZIP 50a801e89eb319fc1b6ac43080c19a026f345d4b2060dc24567802ca6971e964',
        'files':records,'receipts':receipts,'incremental_reconstruction_verified':True,
        'all_other_v2_source_files_unchanged':True,
        'controlled_ui_checks_passed':tests['passed'],'uncaught_errors':[],
        'changes':['Monotonic deadline and validation after asynchronous replies',
            'Abort does not await a hung cancellation acknowledgement',
            'Obsolete engine/history responses adopt the newest refresh result',
            'Only explicit authenticated:true proves session authentication'],
        'native_gui_tested':False,'inference_executed':False,'builtin_inventory_complete':False,
        'activation_gate':'OPEN; no change to native C3 ownership or runtime-isolation acceptance.'}
    (OUT/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (OUT/'README.md').write_text('''# Delta UI V2.1

Aplicar después del snapshot V2. Cambia únicamente axx-connect.js y su prueba de navegador.
El parche se reconstruyó contra las fuentes V2 y sus hashes coinciden. No sustituir HTML,
CSS, Rust, backend, voz ni documentos del integrador. Los otros 45 archivos V2
conservan sus hashes. Revisar por hunks si el stage tiene cambios propios.

Los resultados son de navegador/IPC controlado. Este delta no ejecuta inferencia ni
demuestra el funcionamiento de la aplicación Windows instalada. El ZIP V2 original
permanece inmutable; el ensayo de aislamiento es un addendum separado aún sin ejecutar.
''',encoding='utf-8')
    archive=EVIDENCE/'axx-connect-ui-review-v21.zip'
    if archive.exists():
        raise FileExistsError('Review ZIP already exists.')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(OUT.rglob('*')):
            if path.is_file():output.write(path,path.relative_to(OUT).as_posix())
    print(json.dumps({'files':len(records),'ui_checks_passed':tests['passed'],
                      'archive':str(archive),'sha256':SHA(archive.read_bytes())},indent=2))


if __name__=='__main__':
    main()
