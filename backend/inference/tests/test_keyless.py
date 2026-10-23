import threading
import unittest

from backend.inference.keyless import KeylessSetup


class Candidates:
    def __init__(self):
        self.entered, self.release = threading.Event(), threading.Event()
        self.calls = []
        self.available = True

    def prepare_keyless(self, *, force=False):
        self.calls.append(('prepare', force))
        self.entered.set()
        self.release.wait(3)
        return {'providers': ['anonymous'] if self.available else [], 'message': 'No capacity'}

    def bootstrap(self, task, *, force=False):
        self.calls.append((task, force))
        return {'applied': [{'task': task}] if task == 'plan' else [], 'evaluations': []}

    def cancel_active(self):
        self.release.set()


class KeylessSetupTests(unittest.TestCase):
    def test_setup_is_nonblocking_deduplicated_and_only_verified_tasks_are_ready(self):
        candidates = Candidates(); setup = KeylessSetup(candidates)
        self.addCleanup(setup.close)
        self.assertEqual(setup.start()['state'], 'preparing')
        self.assertTrue(candidates.entered.wait(1))
        setup.start(refresh=True)
        self.assertEqual(candidates.calls, [('prepare', False)])
        candidates.release.set(); setup.worker.join(2)
        status = setup.status()
        self.assertEqual(status['state'], 'ready')
        self.assertTrue(status['tasks']['plan']['applied'])
        self.assertFalse(status['tasks']['vision']['applied'])
        self.assertEqual(setup.timer.interval, 301)
        before = list(candidates.calls); setup.start()
        self.assertEqual(candidates.calls, before)
        status['tasks'].clear()
        self.assertTrue(setup.status()['tasks'])

    def test_no_routes_waits_without_inference_and_close_prevents_work(self):
        candidates = Candidates(); candidates.available = False; candidates.release.set()
        setup = KeylessSetup(candidates)
        setup.start(); setup.worker.join(2)
        self.assertEqual(setup.status()['state'], 'waiting')
        self.assertEqual(candidates.calls, [('prepare', False)])
        setup.close(); setup.start(refresh=True)
        self.assertEqual(candidates.calls, [('prepare', False)])
        with self.assertRaises(ValueError): setup.start(refresh='yes')

    def test_shutdown_cancels_setup_before_probes(self):
        candidates = Candidates(); setup = KeylessSetup(candidates)
        setup.start(); self.assertTrue(candidates.entered.wait(1)); setup.close()
        self.assertEqual(setup.status()['state'], 'stopped')
        self.assertEqual(candidates.calls, [('prepare', False)])

    def test_delayed_worker_does_not_start_setup_after_close(self):
        candidates = Candidates(); setup = KeylessSetup(candidates)
        setup.close()
        setup._run(False)
        self.assertEqual(candidates.calls, [])
        self.assertEqual(setup.status()['state'], 'stopped')


if __name__ == '__main__':
    unittest.main()
