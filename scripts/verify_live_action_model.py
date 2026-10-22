"""One bounded live-model check; only executes the expected disposable file write."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.action_learning import ActionLearning
from backend.inference.adapter import InferenceAdapter
from backend.inference.provider_settings import load_credentials


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=Path)
    parser.add_argument('provider')
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    chosen = next(p for p in config['providers'] if p['name'] == args.provider)
    config['providers'] = [chosen]
    config['max_attempts'] = 1
    load_credentials(args.config)
    with tempfile.TemporaryDirectory(prefix='axx-live-learning-') as temp:
        root = Path(temp)
        adapter = InferenceAdapter(config, root / 'state.db')
        executor = ActionExecutor(root / 'state.db', root / 'artifacts')
        commands = CommandService(executor)
        learning = ActionLearning(commands, adapter)
        report = {'provider': args.provider, 'model': chosen['model'], 'real_model': True}
        try:
            plan = learning.propose('Crea un archivo de texto nuevo llamado prueba-modelo.txt dentro de artifacts con exactamente este contenido: AXX LIVE OK. No abras aplicaciones ni hagas otros cambios.',
                                    model=chosen['model'], provider_name=args.provider)
            report['proposal_state'] = plan['state']
            expected = [{'command_id': 'axx.artifact.write', 'inputs': {'path': 'prueba-modelo.txt', 'content': 'AXX LIVE OK'}}]
            if plan['state'] == 'awaiting_approval' and plan['steps'] == expected:
                result = learning.execute(plan['operation_id'], True)
                report.update(execution_state=result['state'], file_verified=(root / 'artifacts/prueba-modelo.txt').read_text() == 'AXX LIVE OK',
                              learned=len(learning.list_actions()) == 1)
            else:
                report['message'] = plan.get('message', 'Model proposal differed from the narrow test request; no effect executed.')
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(report, ensure_ascii=True))
        finally:
            learning.close(); commands.close(); executor.close(); adapter.close()


if __name__ == '__main__': main()
