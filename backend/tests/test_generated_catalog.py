"""The reviewed registry preserves revocation and exact conversational selection."""
import unittest

from backend.tests import test_generated_commands as fixtures


class GeneratedCatalogTests(unittest.TestCase):
    setUp = fixtures.GeneratedWorkshopTests.setUp
    tearDown = fixtures.GeneratedWorkshopTests.tearDown
    ref = staticmethod(fixtures.GeneratedWorkshopTests.ref)
    active = fixtures.GeneratedWorkshopTests.active

    def test_unchanged_registration_preserves_admitted_tool_identity(self):
        item = self.active()
        tool = self.executor.dynamic_tools[item['command_id']]
        self.commands.refresh_generated_catalog(self.workshop.active_generated_records())
        self.assertIs(self.executor.dynamic_tools[item['command_id']], tool)

    def test_exact_named_command_and_retired_revision(self):
        item = self.active()
        title = item['definition']['title']
        resolved = self.commands.resolve('ejecuta el comando ' + title)
        self.assertEqual(resolved['command_id'], item['command_id'])
        self.assertEqual(resolved['inputs'], {})
        self.assertEqual(self.commands.resolve('¿cómo funciona el comando ' + title + '?')['match'], 'none')
        self.assertEqual(self.commands.resolve('ejecuta comando inexistente')['match'], 'none')
        pending = self.commands.prepare(item['command_id'], {'text': ' AXX '})
        self.workshop.revoke(*self.ref(item))
        self.assertEqual(self.commands.resolve('ejecuta comando ' + title)['match'], 'none')
        result = self.commands.execute(pending['operation_id'])
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['error']['code'], 'PRECONDITION_CHANGED')


if __name__ == '__main__': unittest.main()
