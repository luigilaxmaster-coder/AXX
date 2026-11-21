"""Unit and integration tests for Phase 8 (PR-11 & PR-12 / Gate G8): Agent Profiles, 24/9 Catalog, and Chat Bindings."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.agents.bindings import (
    ConversationBindingService,
    CrossChatAccessDeniedError,
)
from backend.agents.policy import (
    PermissionDeniedError,
    attenuate_delegated_grants,
    resolve_effective_permissions,
)
from backend.agents.profiles import (
    AgentProfileValidationError,
    AvatarFormAdapter,
    export_agent_package,
    import_agent_package,
)
from backend.agents.registry import (
    AgentRegistry,
    StaleAgentRevisionError,
)
from backend.chat_store import ChatStore


class AgentProfilesAndChatBindingsTests(unittest.TestCase):
    def _sample_profile(self, agent_id: str = 'axx-dev-001', **overrides) -> dict:
        base = {
            'schema_version': '1.0',
            'agent_id': agent_id,
            'revision': 1,
            'name': 'AXX Ingeniero',
            'role': 'software_engineer',
            'description': 'Especialista en código y pruebas',
            'instructions': 'Usa worktrees aislados y verifica cada diff.',
            'enabled': True,
            'appearance': {
                'form_id': 17,
                'palette_id': 0,
                'catalog_version': 'axx-avatar-24x9-v1',
                'material_preset': 'obsidian',
                'scale': 1.0,
            },
            'intelligence': {
                'route': 'manual',
                'provider_profile_ref': 'codex-sub',
                'model_id': 'gpt-5',
                'fallback': 'ask',
                'max_parallel_turns': 1,
            },
            'voice': {
                'tts_profile_id': 'axxmorcito',
                'language': 'es-DO',
                'auto_speak': True,
                'speed': 1.0,
            },
            'workspace': {
                'runtime': 'api',
                'foreground_policy': 'ask',
                'project_ref': 'axx-repo',
                'allowed_roots': ['project://axx'],
            },
            'permissions': {
                'tool_grant_refs': ['grant.read.project', 'grant.write.worktree'],
                'delegation_enabled': True,
                'max_delegate_depth': 2,
            },
            'limits': {
                'max_concurrent_jobs': 2,
                'max_retries': 1,
                'max_cost_usd': 2.5,
            },
            'memory_scope': 'agent',
        }
        base.update(overrides)
        return base

    def test_agent_02_canonical_24_forms_9_palettes_and_thumbnail_cache(self):
        adapter = AvatarFormAdapter()
        cat = adapter.catalog()
        self.assertEqual(cat['form_count'], 24)
        self.assertEqual(cat['palette_count'], 9)

        # Verify all 24 x 9 combinations produce valid non-WebGL thumbnails
        for fid in range(24):
            for pid in range(9):
                thumb = adapter.get_thumbnail(fid, pid, material_preset='obsidian')
                self.assertEqual(thumb['form_id'], fid)
                self.assertEqual(thumb['palette_id'], pid)
                self.assertFalse(thumb['webgl_loop_active'])
                self.assertIn('<svg', thumb['svg'])

        # Out-of-range form or palette rejected
        with self.assertRaises(AgentProfileValidationError):
            adapter.get_thumbnail(24, 0)
        with self.assertRaises(AgentProfileValidationError):
            adapter.get_thumbnail(0, 9)

    def test_agent_01_04_05_and_e2e_02_crud_cas_provider_switch_and_clean_export_import(self):
        reg = AgentRegistry(':memory:')
        self.addCleanup(reg.close)

        # Reject raw API key leak in instructions or profile
        with self.assertRaises(AgentProfileValidationError):
            reg.create_profile(self._sample_profile(instructions='My key is sk-1234567890abcdefghijklmnop'))

        created = reg.create_profile(self._sample_profile('agent-1'))
        self.assertEqual(created['revision'], 1)
        self.assertEqual(created['appearance']['form_name'], 'Helix')
        self.assertEqual(created['appearance']['palette_name'], 'Obsidian')

        # E2E-02: Full customization update increments revision to 2
        updated = reg.update_profile(
            'agent-1',
            {
                'appearance': {'form_id': 3, 'palette_id': 5},
                'voice': {'speed': 1.15},
                'limits': {'max_cost_usd': 5.0},
            },
            expected_revision=1,
        )
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(updated['appearance']['form_name'], 'Torus')
        self.assertEqual(updated['appearance']['palette_name'], 'Emerald')

        # Concurrent stale revision=1 update fails with StaleAgentRevisionError (409 stale_revision)
        with self.assertRaises(StaleAgentRevisionError):
            reg.update_profile('agent-1', {'name': 'Colisión'}, expected_revision=1)

        # AGENT-04: Switch provider revokes session tokens and preserves permissions
        switched = reg.switch_provider(
            'agent-1',
            expected_revision=2,
            new_provider_ref='claude-auth',
            new_model_id='claude-4-sonnet',
            prior_session_tokens={'session_a': 'tok-123'},
        )
        self.assertEqual(switched['profile']['revision'], 3)
        self.assertEqual(switched['transferred_session_tokens'], {})
        self.assertEqual(switched['revoked_session_count'], 1)
        self.assertTrue(switched['permissions_unchanged'])

        # AGENT-05 & E2E-15: Export strips grants/roots and pauses routines; import enforces disabled state even for 'admin' role
        pkg = export_agent_package(
            switched['profile'],
            routines=[{'routine_id': 'r-monday', 'schedule': {'cron': '0 9 * * 1'}, 'work_spec': {}, 'enabled': True}],
        )
        self.assertEqual(pkg['profile']['permissions']['tool_grant_refs'], [])
        self.assertEqual(pkg['profile']['workspace']['allowed_roots'], [])
        self.assertFalse(pkg['routines'][0]['enabled'])

        # Tamper with package role to 'admin' and request grants; import must strip grants and keep disabled
        pkg['profile']['role'] = 'admin'
        pkg['profile']['enabled'] = True
        pkg['profile']['permissions']['tool_grant_refs'] = ['grant.host.admin']
        imported = import_agent_package(pkg)
        self.assertFalse(imported['profile']['enabled'])
        self.assertEqual(imported['profile']['permissions']['tool_grant_refs'], [])
        self.assertFalse(imported['import_report']['admin_role_privilege_escalation'])
        self.assertFalse(imported['routines'][0]['enabled'])

        # T-AG-008: Disabling agent revokes active grants
        reg.grant_permission(
            grant_id='g-1',
            agent_id='agent-1',
            tool_id='axx.file.sha256',
            resource_pattern='project://axx/*',
            operation_kinds=['read_scoped'],
        )
        self.assertEqual(len(reg.list_permissions('agent-1')), 1)
        disabled = reg.disable_profile('agent-1', revoke_grants=True)
        self.assertFalse(disabled['enabled'])
        self.assertTrue(disabled['draining'])
        self.assertEqual(reg.list_permissions('agent-1'), [])

    def test_chat_01_02_03_and_e2e_01_lossless_chat_conversion_privacy_and_forget_scrub(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'chat_agents.db'
            chat_store = ChatStore(db_path)
            reg = AgentRegistry(db_path)
            bindings = ConversationBindingService(reg, chat_store=chat_store)
            try:
                # Create two conversations in ChatStore with messages and drafts
                c1_res = chat_store.mutate('create', {'title': 'Proyecto Principal', 'draft': 'borrador intacto'})
                cid1 = c1_res['id']
                c1_before = chat_store.get(cid1)
                chat_store.mutate(
                    'save',
                    {
                        'id': cid1,
                        'draft': 'borrador intacto',
                        'memory_scope': c1_before['memory_scope'],
                        'memory_context_id': c1_before['context_id'],
                        'messages': [{'id': 'm1', 'role': 'user', 'status': 'complete', 'text': 'Mensaje privado del hilo 1', 'at': chat_store.clock()}],
                    },
                )
                c1_saved = chat_store.get(cid1)

                c2_res = chat_store.mutate('create', {'title': 'Hilo Privado 2'})
                cid2 = c2_res['id']
                c2_before = chat_store.get(cid2)
                chat_store.mutate(
                    'save',
                    {
                        'id': cid2,
                        'memory_scope': c2_before['memory_scope'],
                        'memory_context_id': c2_before['context_id'],
                        'messages': [{'id': 'm2', 'role': 'user', 'status': 'complete', 'text': 'Secreto en hilo 2', 'at': chat_store.clock()}],
                    },
                )

                # Create agent and bind it to both cid1 and cid2
                reg.create_profile(self._sample_profile('agent-shared'))
                b1 = bindings.bind_agent_to_conversation(cid1, 'agent-shared', membership_role='lead')
                self.assertTrue(b1['chat_preserved'])
                bindings.bind_agent_to_conversation(cid2, 'agent-shared', membership_role='lead')

                # CHAT-01 / E2E-01: Verify cid1 ID, messages, draft, and connect_id are 100% preserved
                c1_after = chat_store.get(cid1)
                self.assertEqual(c1_after['id'], cid1)
                self.assertEqual(c1_after['draft'], 'borrador intacto')
                self.assertEqual(len(c1_after['messages']), 1)
                self.assertEqual(c1_after['messages'][0]['text'], 'Mensaje privado del hilo 1')
                self.assertEqual(c1_after['connect_id'], c1_saved['connect_id'])

                # CHAT-02: Agent in cid1 attempting to read cid2 without explicit chat_link must be denied!
                with self.assertRaises(CrossChatAccessDeniedError):
                    bindings.resolve_authorized_conversation_context(
                        agent_id='agent-shared',
                        active_conversation_id=cid1,
                        requested_conversation_id=cid2,
                    )

                # Reading its own active conversation cid1 succeeds
                ctx1 = bindings.resolve_authorized_conversation_context(
                    agent_id='agent-shared',
                    active_conversation_id=cid1,
                    requested_conversation_id=cid1,
                )
                self.assertEqual(len(ctx1['messages']), 1)

                # Reversible unbind on cid2 keeps cid2 intact
                bindings.unbind_agent_from_conversation(cid2, 'agent-shared')
                self.assertEqual(bindings.list_conversation_members(cid2), [])
                self.assertEqual(len(chat_store.get(cid2)['messages']), 1)

                # CHAT-03: Forgetting cid1 in ChatStore automatically scrubs its agent_conversation_links
                chat_store.mutate('forget', {'id': cid1})
                self.assertEqual(bindings.list_conversation_members(cid1), [])
            finally:
                reg.close()
                chat_store.close()

    def test_sec_02_permission_intersection_and_delegation_attenuation(self):
        eff = resolve_effective_permissions(
            user_grants={'tool.read', 'tool.write', 'tool.admin'},
            conversation_mode='ask',
            agent_grants={'tool.read', 'tool.write'},
            project_allowed_tools={'tool.read'},
        )
        self.assertEqual(eff['effective_tools'], frozenset({'tool.read'}))
        self.assertFalse(eff['provider_bypass_permissions'])

        # Sub-agent requesting 'tool.write' when parent only has 'tool.read' must fail (SEC-02)
        with self.assertRaises(PermissionDeniedError):
            attenuate_delegated_grants(
                parent_effective_tools=eff['effective_tools'],
                requested_delegate_tools=['tool.read', 'tool.write'],
                parent_delegate_depth=0,
                max_delegate_depth=2,
            )


if __name__ == '__main__':
    unittest.main()
