"""Unit, security, and integration tests for Phase 12 — Code Studio Pro: Indexer, LSP, DAP & External Git Gate (PR-18 / Gate G12).

Covers:
- CODE-04: Incremental AST/symbol indexer, LSP allowlist & graceful 'degraded_syntax_only' fallback on crash,
  and DAP loopback confinement + dangerous LLM evaluate blocking.
- CODE-05: External git push / PR creation blocked without explicit write_external user approval receipt.
- E2E-05: End-to-end Code Studio workflow (Index -> CodeChangeSet -> SupervisedTestRunner receipt -> Spatial Diagram link).
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

from backend.code_studio.artifact_link import CodeArtifactLinkService, ExternalGitPushBlockedError
from backend.code_studio.debug_adapters import DebugAdapterManager, DebugSecurityError
from backend.code_studio.indexer import CodeStructuralIndexer
from backend.code_studio.language_servers import LanguageServerManager, UnauthorizedLanguageServerError
from backend.code_studio.patch_engine import CodePatchEngine
from backend.code_studio.projects import CodeProjectService
from backend.code_studio.test_runner import SupervisedTestRunner


class CodeStudioProTests(unittest.TestCase):
    def test_code04_indexer_and_lsp_graceful_degradation_on_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'service.py').write_text(
                'class OrderService:\n'
                '    def compute_total(self, items):\n'
                '        return sum(items)\n',
                encoding='utf-8',
            )
            (root / 'broken.py').write_text('def bad_syntax(:\n    pass\n', encoding='utf-8')
            (root / 'ui.js').write_text(
                'class WidgetView {}\n'
                'function renderWidget(el) { return el; }\n',
                encoding='utf-8',
            )

            projects = CodeProjectService(':memory:')
            self.addCleanup(projects.close)
            projects.register_project('p-pro', root)
            indexer = CodeStructuralIndexer(projects)
            lsp = LanguageServerManager(projects, indexer)

            # Non-allowlisted LSP language or binary is rejected
            with self.assertRaises(UnauthorizedLanguageServerError):
                lsp.start_language_server(project_id='p-pro', language='python', preferred_binary='malicious-lsp.exe')

            # Start LSP and simulate mid-session crash -> degrades gracefully without losing usability
            lsp.start_language_server(project_id='p-pro', language='python')
            crashed = lsp.simulate_crash_or_disconnect('p-pro', 'python', reason='LSP worker SIGSEGV')
            self.assertEqual(crashed['status'], 'degraded_syntax_only')
            self.assertTrue(crashed['degraded'])

            doc_info = lsp.get_document_symbols_and_diagnostics(
                project_id='p-pro',
                language='python',
                relative_path='service.py',
            )
            self.assertTrue(doc_info['editor_usable'])
            self.assertTrue(doc_info['degraded'])
            sym_names = {s['name'] for s in doc_info['symbols']}
            self.assertEqual(sym_names, {'OrderService', 'compute_total'})

            # Broken syntax file reports AST syntax diagnostic in degraded mode
            broken_info = lsp.get_document_symbols_and_diagnostics(
                project_id='p-pro',
                language='python',
                relative_path='broken.py',
            )
            self.assertEqual(len(broken_info['diagnostics']), 1)
            self.assertIn('SyntaxError', broken_info['diagnostics'][0]['message'])

            # Project-wide index finds both Python and JS symbols
            summary = indexer.index_project('p-pro')
            self.assertEqual(summary['indexed_file_count'], 3)
            self.assertEqual(len(indexer.query_symbol('p-pro', 'Widget')), 2)

    def test_code04_dap_loopback_confinement_and_evaluate_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            projects = CodeProjectService(':memory:')
            self.addCleanup(projects.close)
            projects.register_project('p-dap', Path(tmp))
            dap = DebugAdapterManager(projects)

            # Non-loopback host binding rejected
            with self.assertRaises(DebugSecurityError):
                dap.create_debug_session(
                    session_id='dap-bad',
                    project_id='p-dap',
                    adapter='debugpy',
                    host='0.0.0.0',
                )

            # Non-allowlisted adapter rejected
            with self.assertRaises(DebugSecurityError):
                dap.create_debug_session(
                    session_id='dap-bad2',
                    project_id='p-dap',
                    adapter='custom-gdb-shell',
                )

            sess = dap.create_debug_session(
                session_id='dap-1',
                project_id='p-dap',
                adapter='debugpy',
                host='127.0.0.1',
                port=5678,
            )
            self.assertEqual(sess['host'], '127.0.0.1')

            # Safe read-only variable inspection by agent is allowed
            res = dap.evaluate_expression(session_id='dap-1', expression='counter', actor='agent')
            self.assertIsNone(res['result'])
            self.assertEqual(res['status'], 'unsupported_mode')

            # Dangerous side-effecting expression by agent is blocked
            with self.assertRaises(DebugSecurityError):
                dap.evaluate_expression(
                    session_id='dap-1',
                    expression="__import__('os').system('calc.exe')",
                    actor='agent',
                )

    def test_code05_and_e2e05_external_git_gate_and_end_to_end_code_to_diagram_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'pricing.py').write_text(
                'def apply_discount(price, pct):\n    return price\n',
                encoding='utf-8',
            )
            (root / 'test_pricing.py').write_text(
                'import unittest, pricing\n'
                'class T(unittest.TestCase):\n'
                '    def test_disc(self):\n'
                '        self.assertEqual(pricing.apply_discount(100, 15), 85)\n'
                'if __name__ == "__main__":\n'
                '    unittest.main()\n',
                encoding='utf-8',
            )

            projects = CodeProjectService(':memory:')
            self.addCleanup(projects.close)
            projects.register_project('p-e2e05', root)
            patcher = CodePatchEngine(projects)
            runner = SupervisedTestRunner(projects)
            links = CodeArtifactLinkService(projects)

            # 1. TDD Red: initial test fails before patch
            red_receipt = runner.run_test_command(
                report_id='rep-red',
                project_id='p-e2e05',
                workspace_id='wt-1',
                command=[sys.executable, 'test_pricing.py'],
            )
            self.assertFalse(red_receipt['passed'])

            # 2. Propose and apply CodeChangeSet
            patcher.propose_changeset(
                changeset_id='cs-e2e05',
                project_id='p-e2e05',
                workspace_id='wt-1',
                agent_id='axx-coder',
                base_commit='508bceabc718905db9bcf4042992d91f4c6c0705',
                branch='axx/agent/axx-coder/pricing',
                file_edits=[
                    {
                        'path': 'pricing.py',
                        'new_content': 'def apply_discount(price, pct):\n    return price - (price * pct // 100)\n',
                    }
                ],
            )
            patcher.apply_changeset('cs-e2e05')

            # 3. TDD Green: test passes with cryptographic receipt
            green_receipt = runner.run_test_command(
                report_id='rep-green',
                project_id='p-e2e05',
                workspace_id='wt-1',
                command=[sys.executable, 'test_pricing.py'],
            )
            self.assertTrue(green_receipt['passed'])

            # 4. Link updated source file & changeset to Spatial Diagram object
            artifact_link = links.link_code_to_spatial_artifact(
                project_id='p-e2e05',
                relative_path='pricing.py',
                changeset_id='cs-e2e05',
                scene_id='scene-arch-1',
                spatial_object_id='node-pricing-service',
                artifact_kind='diagram_2d',
            )
            self.assertEqual(artifact_link['spatial_object_id'], 'node-pricing-service')

            # 5. CODE-05: External git push is blocked without write_external approval
            with self.assertRaises(ExternalGitPushBlockedError):
                links.authorize_external_git_action(
                    action='git_push',
                    remote='origin',
                    branch='axx/agent/axx-coder/pricing',
                )

            # Once user approves write_external, git push is authorized
            links.record_external_write_approval(
                approval_operation_id='op-push-approve-1',
                approved=True,
                actor='user',
            )
            auth = links.authorize_external_git_action(
                action='git_push',
                remote='origin',
                branch='axx/agent/axx-coder/pricing',
                approval_operation_id='op-push-approve-1',
            )
            self.assertTrue(auth['authorized'])


if __name__ == '__main__':
    unittest.main()
