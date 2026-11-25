"""Act identity, private explicit memory, TTL, import/export and isolation regressions."""
from pathlib import Path
import tempfile
import unittest

from backend.agents.act_inference import ActInferenceService
from backend.agents.registry import AgentRegistry, StaleAgentRevisionError
from backend.agents.profiles import AgentProfileValidationError
from backend.tests.test_acts_inference import act_spec


class ActLifecycleTests(unittest.TestCase):
    def test_unique_identity_private_memory_restart_ttl_and_import_without_grants(self):
        with tempfile.TemporaryDirectory() as temp:
            now=[1000000]
            path=Path(temp)/'state.db'
            registry=AgentRegistry(path,clock=lambda:now[0])
            try:
                dev=registry.create_profile(act_spec('dev','Dev','Helix','local','m',collaboration={'mention':'Dev'},memory_scope='agent'))
                registry.create_profile(act_spec('qa','QA','Core','local','m',memory_scope='agent'))
                with self.assertRaises(AgentProfileValidationError):
                    registry.create_profile(act_spec('other','Otro','Core','local','m',collaboration={'mention':'dev'}))
                memory=registry.save_private_memory('dev',content='Usa pruebas unittest para este proyecto.',ttl_days=1)
                acts=ActInferenceService(registry)
                self.assertIn('pruebas unittest',acts.resolve('dev',transport='router')['persona'])
                self.assertNotIn('pruebas unittest',acts.resolve('qa',transport='router')['persona'])
                self.assertEqual(registry.get_profile('dev')['revision'],dev['revision'])
                with self.assertRaises(StaleAgentRevisionError):
                    registry.save_private_memory('dev',memory_id=memory['memory_id'],content='Otra nota',expected_revision=0)
                with self.assertRaises(PermissionError):
                    registry.save_private_memory('qa',memory_id=memory['memory_id'],content='Otra nota',expected_revision=1)
                package=registry.export_agent_package('dev')
                self.assertNotIn('unittest',str(package))
                registry.grant_permission(agent_id='dev',grant_id='g',tool_id='axx.code',resource_pattern='*',operation_kinds=['patch'])
                copied=registry.import_agent_package(package,new_agent_id='copy')
                self.assertFalse(copied['enabled'])
                self.assertNotEqual(copied['name'],dev['name'])
                self.assertFalse(registry.list_permissions('copy'))
                self.assertFalse(registry.list_private_memories('copy'))
            finally:registry.close()
            registry=AgentRegistry(path,clock=lambda:now[0])
            try:
                self.assertEqual(registry.list_private_memories('dev')[0]['content'],memory['content'])
                now[0]+=86400001
                self.assertFalse(registry.list_private_memories('dev'))
                self.assertNotIn('pruebas unittest',ActInferenceService(registry).resolve('dev',transport='router')['persona'])
            finally:registry.close()
