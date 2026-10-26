import sqlite3
import threading
import unittest
from backend.memory.skill_memory import SkillMemory


class SkillSearchTests(unittest.TestCase):
    def test_accents_project_scope_version_and_queries_are_data(self):
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE learned_actions(id,trigger,title,steps,environment,verified_at)')
            memory = SkillMemory(db, threading.RLock())
            def add(key, project, title, version=1):
                memory.insert({'id':key,'version':version,'project_id':project,'title':title,'trigger':title,
                    'examples':[],'templates':[],'checks':[],'schema':{},'executable':False,'environment':'fixture'})
            add('shared', '', 'Revisión de planos')
            add('private', 'another-project', 'Revisión privada')
            self.assertEqual([s['id'] for s in memory.search('revision', 'current-project')], ['shared'])
            self.assertEqual(memory.search('" OR * : -', ''), [])
            add('shared', '', 'Presupuesto actualizado', 2)
            self.assertEqual(memory.search('revision', ''), [])
            self.assertEqual(memory.search('presupuesto', '')[0]['version'], 2)
            self.assertFalse(memory.search('presupuesto', '')[0]['effect_verified'])
