"""Recovery data survives while redundant runtime caches are not recopied."""
import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class BackupTests(unittest.TestCase):
    def test_settings_database_models_and_previous_installation_are_verified(self):
        script=Path(__file__).with_name('backup-mobile-upgrade.py')
        with tempfile.TemporaryDirectory() as temp:
            local=Path(temp)
            kept=['Axx/providers.json','Axx/credentials/profile.dpapi','Axx/speech/custom/profile.json',
                  'Axx/models/custom/model.bin','com.axx.desktop/profile/preferences.json','Programs/Axx/resources/settings.json']
            skipped=['Axx/gateways/local/node_modules/dependency/index.js','Axx/backups/old/state.json',
                     'Axx/chatgpt/.tmp/temporary.json','Axx/speech/__pycache__/worker.pyc']
            for name in kept+skipped:
                path=local/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(name)
            with closing(sqlite3.connect(local/'Axx/state.db')) as db:
                db.execute('CREATE TABLE preferences(value TEXT)')
                db.execute("INSERT INTO preferences VALUES('preserved')")
                db.commit()
            result=subprocess.run([sys.executable,str(script)],env=dict(os.environ,LOCALAPPDATA=str(local)),capture_output=True,text=True,check=True)
            receipt=json.loads(result.stdout);backup=Path(receipt['backup'])
            for name in kept:
                label='data' if name.startswith('Axx/') else 'webview' if name.startswith('com.axx.desktop/') else 'installation'
                relative='/'.join(name.split('/')[1:] if label!='installation' else name.split('/')[2:])
                self.assertEqual((backup/label/relative).read_text(),name)
            self.assertFalse((backup/'data/gateways/local/node_modules').exists())
            self.assertFalse((backup/'data/backups').exists())
            self.assertEqual(receipt['excluded_rebuildable_directories'],4)
            with closing(sqlite3.connect(backup/'data/state.db')) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(db.execute('SELECT value FROM preferences').fetchone()[0],'preserved')
            manifest=json.loads((backup/'manifest.json').read_text())
            self.assertEqual(len(manifest),len(kept)+1)


if __name__=='__main__':unittest.main()
