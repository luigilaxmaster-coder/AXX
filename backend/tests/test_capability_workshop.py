"""Workshop contracts and real local executor evidence; no model/network mocks of success."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.capability_workshop import CapabilityWorkshop
from backend.commands import ApprovalRequired, CommandService


def definition(command='axx.system.telemetry', inputs=None):
    return {'kind': 'workflow', 'title': 'Diagnóstico revisado', 'objective': 'Consultar el estado local',
            'schema': {'type': 'object', 'properties': {}, 'required': []},
            'templates': [{'command_id': command, 'inputs': inputs or {}}], 'sample_inputs': {}}


class Model:
    config = {'allow_paid': False}

    def __init__(self): self.calls = []; self.answer = definition()
    def route(self, request):
        self.calls.append(request)
        return {'ok': True, 'message': {'content': json.dumps(self.answer)},
                'route': {'model': 'test-local', 'provider_name': 'offline-fixture', 'api_key': 'must-not-persist'}}


class CapabilityWorkshopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.model = Model()
        self.learning = ActionLearning(self.commands, self.model)
        self.commands.learning = self.learning
        self.workshop = CapabilityWorkshop(self.learning)

    def tearDown(self):
        self.workshop.close(); self.learning.close(); self.commands.close(); self.executor.close(); self.temp.cleanup()

    @staticmethod
    def ref(item): return item['id'], item['revision'], item['digest']

    def reviewed(self, value=None):
        item = self.workshop.create(value or definition())
        return self.workshop.approve(*self.ref(item), confirmed=True)

    def validated(self, value=None):
        item = self.reviewed(value)
        plan = self.workshop.prepare_validation(*self.ref(item), conversation_id='chat-validation')
        done = self.learning.execute(plan['operation_id'], approved=True)
        self.assertEqual(done['state'], 'succeeded', done)
        return self.workshop.get(item['id']), done

    def active(self, value=None):
        item, _ = self.validated(value)
        return self.workshop.activate(*self.ref(item))

    def test_draft_static_validation_does_not_execute_or_register(self):
        item = self.workshop.create(definition())
        self.assertEqual(item['state'], 'draft')
        self.assertEqual(item['validation']['status'], 'static_validated')
        self.assertFalse(item['validation']['runtime_verified'])
        self.assertEqual(self.commands.operations(), [])
        self.assertEqual(self.learning.skills.list(), [])
        self.assertEqual(self.workshop.list()[0]['id'], item['id'])

    def test_catalog_excludes_shell_ephemeral_selectors_and_model_policy(self):
        catalog = self.workshop.catalog()
        ids = [entry['command_id'] for entry in catalog['commands']]
        self.assertNotIn('axx.shell.powershell', ids)
        self.assertNotIn('axx.desktop.window.set_value', ids)
        self.assertNotIn('axx.desktop.cli_anything.scan', ids)
        self.assertTrue(catalog['policy']['runtime_evidence_required'])

    def test_unknown_model_fields_and_permission_escalation_are_rejected(self):
        for field, value in [('approved', True), ('risk', 'read'), ('permissions', ['*']), ('execute', True), ('allow_paid', True)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.workshop.create(definition() | {field: value})
        for command in ['execute_any', 'axx.shell.cmd', 'axx.shell.powershell', 'axx.desktop.window.focus']:
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.workshop.create(definition(command, {'script': 'echo surprise'}))
        self.assertEqual(self.commands.operations(), [])

    def test_parameter_types_and_references_are_strict(self):
        value = definition('axx.process.inspect', {'pid': '{{pid}}'})
        value['schema'] = {'type': 'object', 'properties': {'pid': {'type': 'string'}}, 'required': ['pid']}
        value['sample_inputs'] = {'pid': '123'}
        with self.assertRaises(ValueError): self.workshop.create(value)
        value['schema']['properties']['pid']['type'] = 'integer'; value['sample_inputs']['pid'] = True
        with self.assertRaises(ValueError): self.workshop.create(value)
        value['sample_inputs']['pid'] = 123
        self.assertEqual(self.workshop.create(value)['validation']['steps'][0]['inputs'], {'pid': 123})
        value['templates'][0]['inputs']['pid'] = '{{missing}}'
        with self.assertRaises(ValueError): self.workshop.create(value)

    def test_approval_binds_digest_and_revision_without_executing(self):
        item = self.workshop.create(definition())
        with self.assertRaises(ValueError): self.workshop.approve(*self.ref(item))
        with self.assertRaises(ValueError): self.workshop.approve(item['id'], 1, '0' * 64, True)
        with self.assertRaises(ValueError): self.workshop.prepare_validation(*self.ref(item))
        reviewed = self.workshop.approve(*self.ref(item), confirmed=True)
        self.assertEqual(reviewed['approval']['digest'], item['digest'])
        self.assertEqual(self.commands.operations(), [])

    def test_validation_is_linked_durable_and_requires_execution_approval(self):
        item = self.reviewed()
        plan = self.workshop.prepare_validation(*self.ref(item), conversation_id='chat-validation')
        self.assertEqual(plan['state'], 'awaiting_approval')
        self.assertEqual(plan['conversation_id'], 'chat-validation')
        self.assertEqual(plan['workshop_validation']['digest'], item['digest'])
        self.assertEqual(self.workshop.prepare_validation(*self.ref(item), conversation_id='chat-validation')['operation_id'], plan['operation_id'])
        with self.assertRaises(ValueError): self.workshop.prepare_validation(*self.ref(item), conversation_id='chat-other')
        with self.assertRaises(ApprovalRequired): self.learning.execute(plan['operation_id'])
        with self.assertRaises(ValueError): self.workshop.activate(*self.ref(item))
        done = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(done['state'], 'succeeded')
        self.assertEqual(self.learning.skills.list(), [], 'validation must not bypass activation by auto-learning')
        self.assertEqual(self.commands.get(done['step_records'][0]['operation_id'])['conversation_id'], 'chat-validation')

    def test_real_receipts_gate_activation_and_reuse_uses_existing_executor(self):
        item, plan = self.validated()
        active = self.workshop.activate(*self.ref(item))
        self.assertEqual(active['state'], 'active')
        self.assertEqual(active['active_revision'], 1)
        skill = self.learning.skills.get(active['skill_id'])
        self.assertTrue(skill['effect_verified']); self.assertTrue(skill['executable'])
        self.assertEqual(skill['provenance']['workshop_digest'], item['digest'])
        replay = self.learning.propose(active['skill_id'])
        self.assertEqual(replay['model_calls_used'], 0)
        self.assertEqual(self.learning.execute(replay['operation_id'], True)['state'], 'succeeded')
        self.assertEqual(self.workshop.activate(*self.ref(item))['published_skill_version'], 1)

    def test_missing_command_or_executor_evidence_cannot_activate(self):
        item, plan = self.validated()
        operation_id = plan['step_records'][0]['operation_id']
        receipt = self.commands.get(operation_id)
        with patch.object(self.commands, 'get', return_value=receipt | {'evidence': {}}):
            with self.assertRaises(ValueError): self.workshop.activate(*self.ref(item))
        with patch.object(self.executor, 'get_operation', return_value=None):
            with self.assertRaises(ValueError): self.workshop.activate(*self.ref(item))
        self.assertEqual(self.workshop.get(item['id'])['state'], 'reviewed')
        self.assertEqual(self.learning.skills.list(), [])

    def test_wrong_receipt_inputs_unknown_result_and_tampered_plan_rejected(self):
        item, plan = self.validated()
        operation_id = plan['step_records'][0]['operation_id']
        receipt = self.commands.get(operation_id)
        for altered in [receipt | {'inputs': {'injected': 'value'}}, receipt | {'state': 'unknown'}]:
            with patch.object(self.commands, 'get', return_value=altered), self.assertRaises(ValueError):
                self.workshop.activate(*self.ref(item))
        plan['steps'][0]['command_id'] = 'axx.desktop.list_apps'
        self.learning._save(plan)
        with self.assertRaises(ValueError): self.workshop.activate(*self.ref(item))

    def test_stale_revision_approval_and_pending_validation_are_invalidated(self):
        item = self.reviewed()
        plan = self.workshop.prepare_validation(*self.ref(item))
        newer = self.workshop.revise(*self.ref(item), definition() | {'title': 'Revisión dos'})
        self.assertEqual(newer['revision'], 2); self.assertIsNone(newer['approval'])
        self.assertEqual(self.learning.get(plan['operation_id'])['state'], 'cancelled')
        for method in [self.workshop.validate, self.workshop.prepare_validation, self.workshop.activate]:
            with self.assertRaises(ValueError): method(*self.ref(item))
        with self.assertRaises(ValueError): self.workshop.approve(*self.ref(item), confirmed=True)

    def test_durable_review_and_activation_after_restart(self):
        item, _ = self.validated()
        self.workshop.close(); self.learning.close()
        self.learning = ActionLearning(self.commands, self.model)
        self.commands.learning = self.learning
        self.workshop = CapabilityWorkshop(self.learning)
        recovered = self.workshop.get(item['id'])
        self.assertEqual(recovered['approval'], item['approval'])
        self.assertEqual(recovered['validation_operation_id'], item['validation_operation_id'])
        self.assertEqual(self.workshop.activate(*self.ref(recovered))['state'], 'active')

    def test_revoke_blocks_old_versions_and_prepared_plans(self):
        item = self.active()
        skill = self.learning.skills.get(item['skill_id'])
        pending = self.learning.propose(item['skill_id'])
        revoked = self.workshop.revoke(*self.ref(item))
        self.assertEqual(revoked['state'], 'revoked'); self.assertIsNone(revoked['active_revision'])
        self.assertFalse(self.learning.skills.get(item['skill_id'])['executable'])
        with self.assertRaises(ValueError): self.workshop.assert_skill_available(skill)
        self.assertEqual(self.learning.execute(pending['operation_id'], True)['state'], 'cancelled')
        composed = self.learning.compose('Intento de versión anterior', [{'id': item['skill_id'], 'version': 1}])
        self.assertEqual(composed['state'], 'failed', composed)
        with self.assertRaises(ValueError): self.workshop.approve(*self.ref(revoked), confirmed=True)

    def test_rollback_creates_unapproved_revision_preserving_current_active(self):
        item = self.active()
        second = self.workshop.revise(*self.ref(item), definition() | {'title': 'Segundo diseño'})
        restored = self.workshop.rollback(*self.ref(second), target_revision=1)
        self.assertEqual(restored['revision'], 3)
        self.assertEqual(restored['active_revision'], 1)
        self.assertEqual(restored['definition']['title'], item['definition']['title'])
        self.assertIsNone(restored['approval']); self.assertIsNone(restored['validation_operation_id'])
        self.assertFalse(restored['validation']['runtime_verified'])
        with self.assertRaises(ValueError): self.workshop.activate(*self.ref(restored))

    def test_new_active_revision_disables_historical_skill_binding(self):
        item = self.active()
        old_skill = self.learning.skills.get(item['skill_id'])
        newer = self.workshop.revise(*self.ref(item), definition() | {'title': 'Segundo diagnóstico'})
        newer = self.workshop.approve(*self.ref(newer), confirmed=True)
        plan = self.workshop.prepare_validation(*self.ref(newer))
        self.assertEqual(self.learning.execute(plan['operation_id'], True)['state'], 'succeeded')
        self.workshop.activate(*self.ref(newer))
        with self.assertRaises(ValueError): self.workshop.assert_skill_available(old_skill)
        self.workshop.assert_skill_available(self.learning.skills.get(item['skill_id']))

    def test_generic_configuration_and_repair_cannot_bypass_workshop(self):
        item = self.active()
        with self.assertRaises(ValueError): self.learning.configure(item['skill_id'], {'title': 'bypass'})
        plan = self.learning.propose(item['skill_id'])
        with self.assertRaises(ValueError): self.learning.repair(plan['operation_id'], 'cambia los pasos')

    def test_generation_uses_selected_provider_and_preserves_no_secrets_or_permissions(self):
        item = self.workshop.generate('Consulta estado local', model='selected-model', provider_name='selected-provider', conversation_id='chat-context')
        request = self.model.calls[0]
        self.assertEqual(request['model'], 'selected-model'); self.assertEqual(request['provider_name'], 'selected-provider')
        self.assertFalse(request['allow_paid']); self.assertEqual(request['conversation_id'], 'chat-context')
        self.assertEqual(item['state'], 'draft'); self.assertIsNone(item['approval'])
        self.assertNotIn('api_key', json.dumps(item))
        self.assertEqual(self.commands.operations(), [])

    def test_malformed_model_output_never_becomes_executable(self):
        invalid = ['not json', '[]', '{"kind":"workflow","kind":"source_proposal"}', '{"approved":true}', '{"kind":NaN}']
        for raw in invalid:
            with self.subTest(raw=raw), patch.object(self.model, 'route', return_value={'ok': True, 'message': {'content': raw}}):
                with self.assertRaises(ValueError): self.workshop.generate('prueba')
        self.assertEqual(self.workshop.list(), []); self.assertEqual(self.commands.operations(), [])

    def test_invalid_proposal_is_corrected_once_with_same_route_and_shared_deadline(self):
        answers = [{'ok': True, 'message': {'content': '{bad json'}},
                   {'ok': True, 'message': {'content': json.dumps(definition())}}]
        with patch.object(self.model, 'route', side_effect=answers) as route:
            item = self.workshop.generate('Consulta estado', model='chosen', provider_name='local')
        first, second = [call.args[0] for call in route.call_args_list]
        self.assertNotEqual(first['request_id'], second['request_id'])
        self.assertLessEqual(second['deadline_ms'], first['deadline_ms'])
        self.assertEqual(second['model'], 'chosen'); self.assertEqual(second['provider_name'], 'local')
        self.assertEqual(second['conversation_id'], first['conversation_id'])
        self.assertFalse(second['allow_paid'])
        feedback = json.loads(second['messages'][1]['content'])
        self.assertEqual(feedback['invalid_proposal'], '{bad json'); self.assertTrue(feedback['validation_error'])
        self.assertEqual(item['provenance']['generation_attempts'], 2)
        self.assertEqual(item['provenance']['generation_request_id'], second['request_id'])
        self.assertEqual(item['state'], 'draft'); self.assertIsNone(item['approval'])
        self.assertEqual(len(self.workshop.list()), 1); self.assertEqual(self.commands.operations(), [])
        self.assertEqual(self.workshop.requests, set())

    def test_codex_correction_uses_unique_request_without_adapter_fallback(self):
        from unittest.mock import Mock
        provider = Mock()
        provider.generate_capability.side_effect = [
            {'ok': True, 'message': {'content': 'invalid'}},
            {'ok': True, 'message': {'content': json.dumps(definition())}}]
        self.workshop.provider = provider
        item = self.workshop.generate('Consulta estado', model='chosen', provider_name='@codex')
        calls = [call.args[0] for call in provider.generate_capability.call_args_list]
        self.assertEqual(len(calls), 2); self.assertNotEqual(calls[0]['request_id'], calls[1]['request_id'])
        self.assertTrue(all(call['model'] == 'chosen' and call['provider_name'] == '@codex' for call in calls))
        self.assertEqual(self.model.calls, []); self.assertIsNone(item['approval'])

    def test_generation_does_not_retry_errors_clarifications_or_single_attempt_budget(self):
        for response, options in [
            ({'ok': False, 'error': {'code': 'CANCELLED'}}, {}),
            ({'ok': True, 'message': {'content': '{"needs_input":"Indica el archivo"}'}}, {}),
            ({'ok': True, 'message': {'content': '{"unavailable":"No hay contrato"}'}}, {}),
            ({'ok': True, 'message': {'content': 'invalid'}}, {'max_attempts': 1}),
        ]:
            with self.subTest(response=response), patch.object(self.model, 'route', return_value=response) as route:
                with self.assertRaises(ValueError): self.workshop.generate('Consulta estado', **options)
                self.assertEqual(route.call_count, 1)
        self.assertEqual(self.workshop.list(), [])

    def test_generation_discards_response_after_shared_deadline(self):
        with patch('backend.capability_workshop.time.monotonic', return_value=1) as clock:
            def late(request):
                clock.return_value = 72
                return {'ok': True, 'message': {'content': json.dumps(definition())}}
            with patch.object(self.model, 'route', side_effect=late):
                with self.assertRaisesRegex(ValueError, 'agotó su plazo'): self.workshop.generate('Consulta estado')
        self.assertEqual(self.workshop.list(), [])

    def test_exact_shape_wrapper_normalizes_then_preserves_strict_definition_gates(self):
        self.model.answer = {'shape': definition()}
        item = self.workshop.generate('Consulta el estado local')
        self.assertEqual(item['definition']['kind'], 'workflow')
        self.assertEqual(item['definition']['templates'], definition()['templates'])
        self.assertEqual(item['state'], 'draft'); self.assertIsNone(item['approval'])
        self.assertEqual(self.commands.operations(), []); self.assertEqual(self.learning.skills.list(), [])
        prompt = self.model.calls[0]['messages'][0]['content']
        self.assertIn('objeto JSON de definición en la raíz', prompt)
        self.assertNotIn('"shape":', prompt)

    def test_wrapped_model_output_cannot_hide_permissions_metadata_or_wrong_kind(self):
        invalid = [
            {'shape': definition(), 'approved': True},
            {'shape': definition(), 'metadata': {'risk': 'read'}},
            {'shape': definition() | {'permissions': ['*']}},
            {'shape': definition() | {'kind': 'source_proposal'}},
            {'shape': definition('axx.shell.powershell', {'script': 'echo must-not-run'})},
            {'shape': {'shape': definition()}},
            {'shape': [definition()]},
            {'shape': None},
        ]
        for answer in invalid:
            with self.subTest(answer=answer):
                self.model.answer = answer
                with self.assertRaises(ValueError): self.workshop.generate('Consulta el estado local')
        self.assertEqual(self.workshop.list(), []); self.assertEqual(self.commands.operations(), [])

    def test_generation_stale_revision_and_paid_config_rejected(self):
        item = self.workshop.create(definition())
        def concurrent(request):
            self.workshop.revise(*self.ref(item), definition() | {'title': 'Edición concurrente'})
            return {'ok': True, 'message': {'content': json.dumps(definition())}}
        with patch.object(self.model, 'route', side_effect=concurrent), self.assertRaises(ValueError):
            self.workshop.generate('Mejorar', capability_id=item['id'], revision=1, digest=item['digest'])
        self.assertEqual(self.workshop.get(item['id'])['definition']['title'], 'Edición concurrente')
        with patch.object(self.model, 'config', {'allow_paid': True}), self.assertRaises(ValueError):
            self.workshop.generate('prueba')

    def test_source_proposal_is_text_export_never_a_runtime_tool(self):
        d = {'kind': 'source_proposal', 'title': 'Extensión propuesta', 'objective': 'Planificar una extensión',
             'language': 'python', 'source': 'raise RuntimeError("must never run")', 'readme': 'Revisar contratos y pruebas.'}
        item = self.workshop.create(d)
        reviewed = self.workshop.approve(*self.ref(item), confirmed=True)
        self.assertEqual(reviewed['validation']['status'], 'review_required')
        with self.assertRaises(ValueError): self.workshop.prepare_validation(*self.ref(item))
        with self.assertRaises(ValueError): self.workshop.activate(*self.ref(item))
        exported = self.workshop.export(item['id'])
        self.assertEqual(exported['mime_type'], 'text/markdown')
        self.assertIn('    raise RuntimeError', exported['content'])
        self.assertEqual(self.learning.skills.list(), [])

    def test_pending_command_prevents_second_validation(self):
        item = self.reviewed()
        self.commands.prepare('axx.system.telemetry', {}, command_mode='ask')
        with self.assertRaises(ValueError): self.workshop.prepare_validation(*self.ref(item))

    def test_unknown_validation_is_not_retried_by_new_identity(self):
        item = self.reviewed()
        plan = self.workshop.prepare_validation(*self.ref(item))
        plan['state'] = 'unknown'; self.learning._save(plan)
        self.assertEqual(self.workshop.prepare_validation(*self.ref(item))['operation_id'], plan['operation_id'])
        with self.assertRaises(ValueError): self.workshop.revise(*self.ref(item), definition())
        with self.assertRaises(ValueError): self.workshop.activate(*self.ref(item))

    def test_shutdown_discards_late_generation_and_blocks_activation(self):
        entered, release = threading.Event(), threading.Event()
        errors = []
        def route(request):
            entered.set(); release.wait(5)
            return {'ok': True, 'message': {'content': json.dumps(definition())}}
        def generate():
            try: self.workshop.generate('prueba')
            except ValueError as exc: errors.append(str(exc))
        with patch.object(self.model, 'route', side_effect=route):
            thread = threading.Thread(target=generate); thread.start(); self.assertTrue(entered.wait(5))
            self.workshop.closing = True; release.set(); thread.join(5)
        self.assertTrue(errors)
        self.assertEqual(self.learning.db.execute('SELECT COUNT(*) FROM capability_heads').fetchone()[0], 0)


if __name__ == '__main__': unittest.main()
