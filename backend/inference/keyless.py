"""One bounded background setup job; command execution never depends on this worker."""
from __future__ import annotations

import copy
import logging
import threading
import time


class KeylessSetup:
    TASKS = ('chat', 'plan', 'parameters', 'repair', 'code', 'writing', 'translation', 'vision')

    def __init__(self, candidates):
        self.candidates = candidates
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.worker = None
        self.timer = None
        self.value = {'state': 'idle', 'task': '', 'tasks': {}, 'message': '', 'updated_at': 0}

    def status(self):
        with self.lock:
            return copy.deepcopy(self.value)

    def _update(self, **values):
        with self.lock:
            self.value.update(values, updated_at=time.time())

    def start(self, *, refresh=False):
        if type(refresh) is not bool:
            raise ValueError('refresh must be boolean')
        with self.lock:
            if self.stopping.is_set() or (self.worker and self.worker.is_alive()):
                return self.status()
            cooldown = 21600 if all(self.value['tasks'].get(task, {}).get('applied') for task in self.TASKS) else 300
            if not refresh and time.time() - self.value['updated_at'] < cooldown:
                return self.status()
            if self.timer:
                self.timer.cancel()
            self._update(state='preparing', task='', message='')
            self.worker = threading.Thread(target=self._run, args=(refresh,), name='axx-keyless-setup', daemon=True)
            self.worker.start()
            return self.status()

    def _run(self, refresh):
        try:
            if self.stopping.is_set():
                return
            setup = self.candidates.prepare_keyless(force=refresh)
            if self.stopping.is_set():
                return
            if not setup.get('providers'):
                self._update(state='waiting', task='', message=setup.get('message', 'Sin rutas anónimas disponibles.'))
                return
            for task in self.TASKS:
                if self.stopping.is_set():
                    return
                previous = self.value['tasks'].get(task, {})
                if not refresh and previous.get('applied') and time.time() - previous.get('checked_at', 0) < 21600:
                    continue
                self._update(state='evaluating', task=task)
                result = self.candidates.bootstrap(task, force=refresh)
                with self.lock:
                    self.value['tasks'][task] = dict(result, checked_at=time.time())
            ready = any(value.get('applied') for value in self.value['tasks'].values())
            self._update(state='ready' if ready else 'waiting', task='',
                         message='Las tareas sin modelo apto quedan pendientes hasta disponer de una ruta comprobada.')
        except Exception:
            logging.getLogger('axx.keyless').exception('Anonymous model setup failed')
            self._update(state='error', task='', message='No se pudo completar la preparación. Puedes volver a comprobar los modelos.')
        finally:
            with self.lock:
                if self.stopping.is_set():
                    self._update(state='stopped', task='')
                else:
                    delay = 21601 if all(self.value['tasks'].get(task, {}).get('applied') for task in self.TASKS) else 301
                    self.timer = threading.Timer(delay, self.start)
                    self.timer.daemon = True
                    self.timer.start()

    def close(self):
        self.stopping.set()
        with self.lock:
            if self.timer:
                self.timer.cancel()
        if getattr(self.candidates, 'gateway', None):
            self.candidates.gateway.cancel_bootstrap()
        self.candidates.cancel_active()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join()
