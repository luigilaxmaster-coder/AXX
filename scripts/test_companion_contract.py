"""Negative release tests: appearance drift, stale builds/evidence and missing checks."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import companion_contract as contract
import release

class CompanionContractTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        names=set(contract.read(contract.ROOT/'mobile/design-baseline.json')['protected'])
        names={name.split('#')[0] for name in names}|{'package.json','backend/mobile/gateway.py','mobile/companion-contract.json','mobile/design-baseline.json','mobile/package.json','mobile/package-lock.json','mobile/android/app/build.gradle','scripts/companion_contract.py','scripts/validate_companion.py','scripts/test_companion_contract.py','scripts/release.py','requirements-mobile.txt','requirements-companion-tests.txt'}
        for name in names:
            target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(contract.ROOT/name,target)

    def receipt(self):
        path=self.root/'receipt.json'
        value={'result':'PASS','versions':contract.versions(self.root),'inputs':contract.input_hashes(self.root),'steps':[{'id':key,'exit_code':0} for key in sorted(contract.CHECKS)]}
        path.write_text(json.dumps(value),encoding='utf-8')
        return path,value

    def test_current_contract_and_portable_text_hash(self):
        self.assertEqual(contract.check_contract(self.root),contract.versions(self.root))
        self.assertEqual(contract.sha('a\r\nb'),contract.sha('a\nb'))

    def test_design_change_stops_delivery(self):
        path=self.root/'mobile/css/live-client.css';path.write_text(path.read_text(encoding='utf-8')+'\nbody{color:red}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Approved design changed'):contract.check_contract(self.root)

    def test_route_removal_is_a_breaking_change(self):
        path=self.root/'backend/mobile/gateway.py';path.write_text(path.read_text(encoding='utf-8').replace('/v1/snapshot','/v2/snapshot'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'routes removed'):contract.check_contract(self.root)

    def test_android_versions_cannot_drift(self):
        path=self.root/'mobile/package.json';value=contract.read(path);value['version']='99.0.0';path.write_text(json.dumps(value),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Android manifests disagree'):contract.check_contract(self.root)

    def test_android_code_cannot_downgrade_the_approved_phone_build(self):
        path=self.root/'mobile/android/app/build.gradle'
        text=path.read_text(encoding='utf-8');current=contract.versions(self.root)['android_code']
        path.write_text(text.replace(f'versionCode {current}','versionCode 1'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'versionCode'):contract.check_contract(self.root)

    def test_failed_incomplete_or_boolean_checks_are_rejected(self):
        path,value=self.receipt();self.assertEqual(contract.validate_receipt(self.root,path)['result'],'PASS')
        for steps in (value['steps'][:-1],[{**row,'exit_code':1} for row in value['steps']],[{**row,'exit_code':False} for row in value['steps']]):
            path.write_text(json.dumps({**value,'steps':steps}),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'incomplete or failed'):contract.validate_receipt(self.root,path)

    def test_new_mobile_source_invalidates_old_evidence(self):
        path,_=self.receipt();(self.root/'mobile/js/future.js').write_text('/* added after validation */',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'evidence is stale'):contract.validate_receipt(self.root,path)

    def test_generated_capacitor_assets_do_not_break_clean_checkout_receipts(self):
        before=contract.input_hashes(self.root)
        path=self.root/'mobile/android/app/src/main/assets/public/copied.js';path.parent.mkdir(parents=True);path.write_text('generated',encoding='utf-8')
        path=self.root/'mobile/android/app/src/main/res/xml/config.xml';path.parent.mkdir(parents=True);path.write_text('<widget/>',encoding='utf-8')
        self.assertEqual(contract.input_hashes(self.root),before)

    def test_missing_receipt_blocks_publication_before_github(self):
        args=SimpleNamespace(build_result=self.root/'build.json',install_result=self.root/'install.json',companion_result=self.root/'missing.json',dry_run=True)
        with patch.object(release,'ROOT',self.root),patch.object(release,'check',return_value='0.22.26'),patch.object(release,'validate_receipts',return_value=self.root/'installer.exe'),patch.object(release,'run') as external:
            with self.assertRaisesRegex(ValueError,'Missing companion receipt'):release.publish(args)
            external.assert_not_called()

    def test_stale_generated_geometry_is_rejected(self):
        path=self.root/'mobile/www/js/desktop-avatar.js';path.parent.mkdir(parents=True);path.write_text('stale',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'renderer is stale'):contract.check_contract(self.root,built=True)
