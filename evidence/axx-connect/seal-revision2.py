"""Seal a frozen source review package and its existing evidence (no runtime)."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT/'evidence/axx-connect'
FROZEN = EVIDENCE/'overlay-revision2'
SHA = lambda data: hashlib.sha256(data).hexdigest()


def main():
    archive=EVIDENCE/'axx-connect-source-review-v2.zip'
    if archive.exists() or (FROZEN/'freeze.json').exists():
        raise FileExistsError('The V2 review package is already sealed; use a new revision instead of replacing it.')
    spec=importlib.util.spec_from_file_location('freeze_helper',EVIDENCE/'prepare-revision2.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    old=json.loads((EVIDENCE/'overlay-revision1/manifest.json').read_text(encoding='utf-8'))
    with (EVIDENCE/'overlay-revision1/source.patch').open(encoding='utf-8',newline='') as stream:
        hunks=helper.sections(stream.read())
    previous={}
    for item in old['files']:
        relative=item['path'];base=Path(old['baseline'])/relative
        before=base.read_bytes() if base.is_file() else b''
        if relative=='.gitignore':
            before=(FROZEN/'sources'/relative).read_bytes()
            for line in (b'.venv-axx-connect/\n',b'.venv-axx-connect-build/\n',b'**/endpoint.dpapi\n',b'**/endpoint.tmp\n'):
                before=before.replace(line,b'')
        data=helper.reconstruct(before,hunks[relative])
        if SHA(data)!=item['sha256'] and SHA(b'\xef\xbb\xbf'+data)==item['sha256']:
            data=b'\xef\xbb\xbf'+data
        assert SHA(data)==item['sha256'],relative
        previous[relative]=data
    incremental=json.loads((FROZEN/'incremental-manifest.json').read_text(encoding='utf-8'))
    with (FROZEN/'incremental-v1-v2.patch').open(encoding='utf-8',newline='') as stream:
        hunks=helper.sections(stream.read())
    for item in incremental['files']:
        data=helper.reconstruct(previous.get(item['path'],b''),hunks[item['path']])
        assert SHA(data)==item['sha256'],item['path']
    current=json.loads((FROZEN/'manifest.json').read_text(encoding='utf-8'))
    for item in current['files']:
        assert SHA((FROZEN/'sources'/item['path']).read_bytes())==item['sha256'],item['path']
        assert SHA((ROOT/item['path']).read_bytes())==item['sha256'],item['path']
    receipts=[
        'provider-revision-e-tests.txt','provider-revision-e-result.json',
        'core-revision2-final.log','core-revision2-final-result.json',
        'http-revision2-final.log','mcp-revision2-final.log','frontend-revision2-final.log',
        'ui-connect-tests-revision2-final.log','ui-connect-settings-controlled-revision2.json',
        'ui-connect-settings-controlled-revision2.png','provider-readonly-v2-result.json',
        'runtime-inventory-readonly-result.json','runtime-inventory-readonly-hardened-result.json',
        'runtime-inventory-readonly-extended-result.json','runtime-inventory-schema-audit.json',
        'runtime-inventory-investigation.md',
    ]
    receipt_dir=FROZEN/'evidence';receipt_dir.mkdir(exist_ok=True)
    records=[]
    for name in receipts:
        data=(EVIDENCE/name).read_bytes();(receipt_dir/name).write_bytes(data)
        records.append({'path':'evidence/'+name,'sha256':SHA(data),'bytes':len(data)})
    report={
        'revision':'Connect V2 / provider E',
        'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_files':len(current['files']),'incremental_files':len(incremental['files']),
        'patch_verified_against_v1':True,
        'source_files_match_frozen_bytes':True,
        'files':current['files'],'receipts':records,
        'checks_passed':{'provider_offline':66,'service':21,'http':2,'mcp_transport':1,
                         'ui_controlled':28,'frontend_controlled':18},
        'checks_total_passed':136,'live_opt_in_skipped':1,
        'real_final_provider_status':{'authenticated':True,'inference_verified':False,
                                      'turn_start_sent':False,'native_gui_tested':False},
        'historical_live_proof':'Earlier inference/tool/interrupt/plugin-host evidence predates final provider E; do not certify this frozen source from those earlier runs.',
        'builtin_inventory_complete':False,'isolation_gate':'OPEN',
        'native_combined_gate':'OPEN; C3 integrator owns Rust/event split, GUI/build/install and physical acceptance.',
        'chatgpt_web_gate':'OPEN; no verified tunnel/runtime credential/workspace association.',
        'native_stage_modified_by_this_chat':False,
        'scope':'Only the manifest-listed files are frozen. A separately prepared isolation harness is an addendum; it is not part of this snapshot.',
        'full_patch_sha256':SHA((FROZEN/'source.patch').read_bytes()),
        'incremental_patch_sha256':SHA((FROZEN/'incremental-v1-v2.patch').read_bytes()),
    }
    encoded=json.dumps(report,indent=2,ensure_ascii=False)
    (FROZEN/'freeze.json').write_text(encoded,encoding='utf-8')
    (EVIDENCE/'source-frozen-revision2.json').write_text(encoded,encoding='utf-8')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as target:
        for path in sorted(FROZEN.rglob('*')):
            if path.is_file():
                target.write(path,path.relative_to(FROZEN).as_posix())
    print(json.dumps({'source_files':len(current['files']),'incremental_files':len(incremental['files']),
                      'checks_passed':136,'archive':str(archive),'sha256':SHA(archive.read_bytes())},indent=2))


if __name__=='__main__':
    main()
