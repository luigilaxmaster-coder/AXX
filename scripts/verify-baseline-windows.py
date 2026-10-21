"""Run unchanged baseline assertions, explicitly closing SQLite before teardown.

The original suite never closes its Router instances and fails WinError 32 on
Windows. This harness repairs test resource ownership without editing baseline
files or changing any assertion. Raw original failure remains in baseline.log.
"""
from pathlib import Path
import sys
import unittest

baseline = Path(__file__).resolve().parents[1] / '2.analisis e integracion profunda' / 'baseline' / 'axx-api-router'
sys.path.insert(0, str(baseline))
sys.path.insert(0, str(baseline / 'tests'))
import test_router

original_make = test_router.RouterTests.make
original_teardown = test_router.RouterTests.tearDown

def tracked_make(self, **overrides):
    router = original_make(self, **overrides)
    if not hasattr(self, '_owned_routers'):
        self._owned_routers = []
    self._owned_routers.append(router)
    return router

def close_before_teardown(self):
    for router in getattr(self, '_owned_routers', []):
        router.close()
    original_teardown(self)

test_router.RouterTests.make = tracked_make
test_router.RouterTests.tearDown = close_before_teardown
suite = unittest.defaultTestLoader.loadTestsFromTestCase(test_router.RouterTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
