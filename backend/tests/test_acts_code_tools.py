"""Acts on Code Studio (CODE-04..10): own grant per step, own worktree, model-written patch, diff, tests, integration.

Everything runs on the real AXX handler, a real Git repository, the real patch engine and the supervised test
runner (real subprocesses). The controlled responder returns a fixed file; the Ollama test lets a real local model
write the fix and is skipped, never passed, when Ollama is not reachable.
"""
from __future__ import annotations

import hashlib
import http.server
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request

from backend.tests.test_acts_inference import _EchoModel, _Server, _ollama_models, act_spec, provider

BUGGY = 'def add(a, b):\n    return a - b\n'
FIXED = 'def add(a, b):\n    return a + b\n'
TEST = 'import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n'
TESTS = [sys.executable, '-m', 'unittest', 'discover', '-v']


class _CoderModel(_EchoModel):
    """Controlled OpenAI-compatible responder: answers code tasks with one complete file."""

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).seen.append(body)
        reply = json.dumps({'id': 'x', 'model': body['model'], 'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {
            'role': 'assistant', 'content': '```python\n' + FIXED + '```'}}]}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)


def git_repo(root: Path) -> Path:
    repo = root / 'proj'
    repo.mkdir()
    (repo / 'calc.py').write_text(BUGGY, encoding='utf-8', newline='\n')
    (repo / 'test_calc.py').write_text(TEST, encoding='utf-8', newline='\n')
    # Local to this temporary repo: keeps worktree checkouts byte-identical to the LF files written above.
    for args in (['init', '-q'], ['config', 'core.autocrlf', 'false'], ['add', '.'],
                 ['-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'base']):
        subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True)
    return repo


def ask_act_for_file(srv, act_id, path, content, request_id):
    """The same turn Code Studio sends: the Act's own model rewrites the whole file, AXX keeps the last fenced block."""
    code, body = srv.api.request('POST', '/axx-api/chat', {
        'messages': [{'role': 'user', 'content': f'Tarea de código sobre {path}. Instrucción: corrige add para que sume.\n'
                      'Devuelve el contenido COMPLETO del archivo modificado en un único bloque ```python y nada fuera del bloque.'
                      f'\n\nContenido actual:\n```python\n{content}```'}],
        'request_id': request_id, 'conversation_id': 'conv-code', 'act_id': act_id, 'max_tokens': 400})
    assert code == 200, body
    assert body['axx_act']['model_verified'], body['axx_act']
    blocks = re.findall(r'```[^\n]*\n([\s\S]*?)```', body['choices'][0]['message']['content'])
    assert blocks, body['choices'][0]['message']['content']
    return blocks[-1], body['axx_act']


class ActCodeToolsTests(unittest.TestCase):
    def setUp(self):
        _CoderModel.seen = []
        self.model = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _CoderModel)
        threading.Thread(target=self.model.serve_forever, daemon=True).start()
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.repo = git_repo(root)
        self.srv = _Server(root, [provider('loop-a', f'http://127.0.0.1:{self.model.server_port}/v1', 'model-alpha')])
        for flag in ('agent_profiles_v1', 'code_studio_v1', 'code_execution_v1'):
            self.srv.rt.flags.set_flag(flag, True, reason='act code test')
        api = self.srv.api
        for spec in (act_spec('act-dev', 'Dev', 'Helix', 'loop-a', 'model-alpha'),
                     act_spec('act-qa', 'QA', 'Core', 'loop-a', 'model-alpha', role='QA')):
            self.assertEqual(api.request('POST', '/axx-api/agents/v1/profiles', spec)[0], 200)
        self.assertEqual(api.request('POST', '/axx-api/code/v1/projects/register',
                                     {'project_id': 'proj', 'project_root': str(self.repo)})[0], 200)

    def tearDown(self):
        self.srv.close()
        self.model.shutdown()
        self.model.server_close()
        self.tmp.cleanup()

    def post(self, path, body):
        return self.srv.api.request('POST', '/axx-api/code/v1/' + path, body)

    def grant(self, ops, act='act-dev'):
        code, body = self.srv.api.request('POST', '/axx-api/agents/v1/profiles/permissions/grant', {
            'agent_id': act, 'grant_id': f'g-code-{act}', 'tool_id': 'axx.code', 'operation_kinds': ops, 'approval_mode': 'ask'})
        self.assertEqual(code, 200, body)

    def test_act_works_only_in_its_worktree_under_its_grant_and_integrates_after_tests(self):  # CODE-04..10 (controlled)
        primary = self.repo / 'calc.py'
        wt_body = {'act_id': 'act-dev', 'agent_id': 'act-dev', 'project_id': 'proj', 'workspace_id': 'act-w1',
                   'task_slug': 'fix-add', 'conversation_id': 'conv-code'}
        code, denied = self.post('worktrees/create', wt_body)
        self.assertEqual((code, denied['error']['code']), (403, 'FORBIDDEN'))  # no axx.code grant yet
        # A registered Act's name is not a free label: naming it without act_id still needs its grant.
        self.assertEqual(self.post('worktrees/create', {**wt_body, 'act_id': None, 'agent_id': 'act-qa', 'workspace_id': 'qa-w'})[0], 403)
        self.grant(['worktree', 'patch', 'test'])

        # CODE-04: isolated worktree on the Act's own branch.
        code, wt = self.post('worktrees/create', wt_body)
        self.assertEqual(code, 200, wt)
        self.assertEqual(wt['worktree']['branch_name'], 'axx/agent/act-dev/fix-add')
        wt_root = Path(wt['worktree']['worktree_path'])

        # CODE-07 (failing first): the bug is real; this receipt can never unlock integration.
        code, before = self.post('tests/run', {'act_id': 'act-dev', 'project_id': 'proj', 'workspace_id': 'act-w1',
                                               'report_id': 'r-before', 'command': TESTS})
        self.assertEqual(code, 200, before)
        self.assertFalse(before['receipt']['passed'])

        # CODE-05: the Act's own model writes the file; AXX applies it only inside the worktree.
        content, receipt = ask_act_for_file(self.srv, 'act-dev', 'calc.py', BUGGY, 'code-turn-1')
        self.assertEqual(receipt['served_model'], 'model-alpha')
        self.assertIn('return a - b', json.dumps(_CoderModel.seen[-1]['messages']))  # the model saw the real file
        code, cs = self.post('worktrees/propose-apply', {'act_id': 'act-dev', 'changeset_id': 'cs-1', 'workspace_id': 'act-w1',
                                                         'file_edits': [{'path': 'calc.py', 'new_content': content}]})
        self.assertEqual(code, 200, cs)
        self.assertEqual((wt_root / 'calc.py').read_text(encoding='utf-8'), FIXED)
        self.assertEqual(primary.read_text(encoding='utf-8'), BUGGY)  # the user's copy is untouched

        # CODE-06: diff is readable from the stored changeset.
        code, view = self.srv.api.request('GET', '/axx-api/code/v1/changesets?changeset_id=cs-1')
        self.assertEqual(code, 200, view)
        diff = view['diffs']['files'][0]['diff_text']
        self.assertIn('-    return a - b', diff)
        self.assertIn('+    return a + b', diff)

        # No cross-access and no direct writes to the primary copy.
        self.grant(['worktree', 'patch', 'test', 'integrate'], act='act-qa')
        code, cross = self.post('worktrees/propose-apply', {'act_id': 'act-qa', 'changeset_id': 'cs-qa', 'workspace_id': 'act-w1',
                                                            'file_edits': [{'path': 'calc.py', 'new_content': BUGGY}]})
        self.assertEqual(code, 403, cross)
        self.assertEqual(self.post('tests/run', {'act_id': 'act-qa', 'project_id': 'proj', 'workspace_id': 'act-w1',
                                                 'report_id': 'r-qa', 'command': TESTS})[0], 403)
        self.assertEqual(self.post('changesets/propose', {
            'act_id': 'act-dev', 'changeset_id': 'cs-p', 'project_id': 'proj', 'workspace_id': 'proj', 'agent_id': 'act-dev',
            'base_commit': wt['worktree']['base_commit'], 'branch': 'main', 'file_edits': []})[0], 403)

        # CODE-07: tests in the Act's worktree produce a verifiable receipt.
        code, after = self.post('tests/run', {'act_id': 'act-dev', 'project_id': 'proj', 'workspace_id': 'act-w1',
                                              'report_id': 'r-after', 'command': TESTS})
        self.assertEqual(code, 200, after)
        self.assertTrue(after['receipt']['passed'], after['receipt']['stderr_preview'])

        # CODE-08/09: integration needs the integrate grant and a passing receipt for this change.
        integrate = {'act_id': 'act-dev', 'changeset_id': 'cs-1', 'test_report_ids': ['r-after']}
        self.assertEqual(self.post('worktrees/integrate', integrate)[0], 403)  # no integrate grant
        self.grant(['worktree', 'patch', 'test', 'integrate'])
        self.assertEqual(self.post('worktrees/integrate', {**integrate, 'test_report_ids': []})[0], 403)
        self.assertEqual(self.post('worktrees/integrate', {**integrate, 'test_report_ids': ['r-before']})[0], 403)
        self.assertEqual(primary.read_text(encoding='utf-8'), BUGGY)
        code, done = self.post('worktrees/integrate', integrate)
        self.assertEqual(code, 200, done)
        self.assertEqual(done['changeset']['status'], 'integrated')
        self.assertEqual(hashlib.sha256(primary.read_bytes()).hexdigest(), cs['changeset']['files'][0]['proposed_sha256'])

        # CODE-10: revocation blocks the next step; the owner's own Code Studio actions are unchanged.
        self.srv.api.request('POST', '/axx-api/agents/v1/profiles/permissions/revoke', {'agent_id': 'act-dev', 'grant_id': 'g-code-act-dev'})
        self.assertEqual(self.post('tests/run', {'act_id': 'act-dev', 'project_id': 'proj', 'workspace_id': 'act-w1',
                                                 'report_id': 'r-revoked', 'command': TESTS})[0], 403)
        self.assertEqual(self.post('worktrees/create', {'project_id': 'proj', 'workspace_id': 'user-w', 'agent_id': 'user',
                                                        'task_slug': 'mine'})[0], 200)
        # Rollback: an Act may not undo on the primary copy; the owner always can.
        self.assertEqual(self.post('changesets/rollback', {'act_id': 'act-dev', 'changeset_id': 'cs-1'})[0], 403)
        code, rolled = self.post('changesets/rollback', {'changeset_id': 'cs-1'})
        self.assertEqual(code, 200, rolled)
        self.assertEqual(primary.read_text(encoding='utf-8'), BUGGY)
        events = self.srv.api.request('GET', '/axx-api/agents/v1/events/sse?conversation_id=conv-code')[1]['events']
        self.assertIn(('act-dev', 'tool.dispatched', 'worktree'),
                      [(e['agent_id'], e['type'], e['payload'].get('operation')) for e in events])


@unittest.skipUnless('qwen2.5:7b-instruct' in _ollama_models(), 'Ollama with qwen2.5:7b-instruct not reachable')
class ActCodeRealOllamaTests(unittest.TestCase):
    def test_real_local_model_writes_the_fix_that_passes_tests_and_is_integrated(self):  # CODE-05..09 with real inference
        model = 'qwen2.5:7b-instruct'
        urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:11434/api/generate', method='POST',
                               data=json.dumps({'model': model, 'keep_alive': '10m'}).encode()), timeout=300).read()  # cold load only
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            repo = git_repo(Path(tmp))
            srv = _Server(Path(tmp), [provider('ollama-qwen', 'http://127.0.0.1:11434/v1', model)])
            try:
                for flag in ('agent_profiles_v1', 'code_studio_v1', 'code_execution_v1'):
                    srv.rt.flags.set_flag(flag, True, reason='real act code test')
                api = srv.api
                api.request('POST', '/axx-api/agents/v1/profiles', act_spec('act-dev', 'Dev', 'Helix', 'ollama-qwen', model))
                api.request('POST', '/axx-api/agents/v1/profiles/permissions/grant', {
                    'agent_id': 'act-dev', 'grant_id': 'g-code', 'tool_id': 'axx.code',
                    'operation_kinds': ['worktree', 'patch', 'test', 'integrate'], 'approval_mode': 'ask'})
                api.request('POST', '/axx-api/code/v1/projects/register', {'project_id': 'proj', 'project_root': str(repo)})
                code, wt = api.request('POST', '/axx-api/code/v1/worktrees/create', {
                    'act_id': 'act-dev', 'agent_id': 'act-dev', 'project_id': 'proj', 'workspace_id': 'act-w1', 'task_slug': 'fix-add'})
                self.assertEqual(code, 200, wt)
                content, receipt = ask_act_for_file(srv, 'act-dev', 'calc.py', BUGGY, 'real-code-1')
                self.assertEqual(receipt['responder_model'], model)
                print(f'\n[ACT-CODE-REAL] {model} wrote calc.py:\n{content}')
                code, cs = api.request('POST', '/axx-api/code/v1/worktrees/propose-apply', {
                    'act_id': 'act-dev', 'changeset_id': 'cs-1', 'workspace_id': 'act-w1',
                    'file_edits': [{'path': 'calc.py', 'new_content': content}]})
                self.assertEqual(code, 200, cs)
                code, run = api.request('POST', '/axx-api/code/v1/tests/run', {
                    'act_id': 'act-dev', 'project_id': 'proj', 'workspace_id': 'act-w1', 'report_id': 'r1', 'command': TESTS})
                self.assertEqual(code, 200, run)
                self.assertTrue(run['receipt']['passed'], run['receipt']['stderr_preview'])
                code, done = api.request('POST', '/axx-api/code/v1/worktrees/integrate', {
                    'act_id': 'act-dev', 'changeset_id': 'cs-1', 'test_report_ids': ['r1']})
                self.assertEqual(code, 200, done)
                self.assertIn('a + b', (repo / 'calc.py').read_text(encoding='utf-8'))
            finally:
                srv.close()


if __name__ == '__main__':
    unittest.main()
