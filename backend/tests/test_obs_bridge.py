import os
import threading
import unittest
from unittest.mock import patch

from backend.actions import obs_bridge as obs


class ObsContracts(unittest.TestCase):
    def setUp(self):
        self.before = dict(obs_session='a'*64, profile='Fixture', collection='Fixture', scene='Desktop',
                           scenes=['Desktop', 'Other'], recording=False, paused=False)
        self.inputs = {key:self.before[key] for key in ('obs_session', 'profile', 'collection', 'scene')} | {'action':'start'}

    def test_configuration_rejects_remote_and_unauthenticated(self):
        for url,password in [('ws://example.com:4455','x'), ('ws://127.0.0.1:4455',''), ('ws://u:p@127.0.0.1:4455','x')]:
            with patch.dict(os.environ, {'AXX_OBS_URL':url, 'AXX_OBS_PASSWORD':password}), self.assertRaises(ValueError):
                obs.configuration()

    def test_target_changed_never_mutates(self):
        with patch.object(obs,'Connection') as connection, patch.object(obs,'observe',return_value=self.before | {'scene':'Other'}):
            result = obs.ObsTool('control').execute(self.inputs)
            self.assertFalse(result.success); self.assertFalse(result.evidence['effect_uncertain'])
            connection.return_value.call.assert_not_called()

    def test_start_requires_readback_and_does_not_toggle(self):
        for active in (False, True):
            with patch.object(obs,'Connection') as connection, patch.object(obs,'observe',side_effect=[self.before, self.before | {'recording':active}]):
                result = obs.ObsTool('control').execute(self.inputs)
                self.assertEqual(result.success, active)
                connection.return_value.call.assert_called_once_with('StartRecord', None)
                if not active: self.assertTrue(result.evidence['effect_uncertain'])

    def test_already_recording_is_readback_without_start(self):
        with patch.object(obs,'Connection') as connection, patch.object(obs,'observe',return_value=self.before | {'recording':True}):
            result = obs.ObsTool('control').execute(self.inputs)
            self.assertTrue(result.success); self.assertFalse(result.evidence['recording_file_verified'])
            connection.return_value.call.assert_not_called()

    def test_stop_requires_file_and_no_retry_on_timeout(self):
        with patch.object(obs,'Connection') as connection, patch.object(obs,'observe',return_value=self.before | {'recording':True}):
            connection.return_value.call.side_effect = TimeoutError('lost response')
            result = obs.ObsTool('control').execute(self.inputs | {'action':'stop'})
            self.assertFalse(result.success); self.assertTrue(result.evidence['effect_uncertain'])
            connection.return_value.call.assert_called_once_with('StopRecord', None)
        with patch.object(obs,'Connection') as connection, patch.object(obs,'observe',side_effect=[self.before | {'recording':True}, self.before]), patch.object(obs,'run_inspector',side_effect=ValueError('missing file')):
            connection.return_value.call.return_value = {'outputPath':'C:/missing.mkv'}
            result = obs.ObsTool('control').execute(self.inputs | {'action':'stop'})
            self.assertFalse(result.success); self.assertTrue(result.evidence['effect_uncertain'])

    def test_cancelled_no_connection_and_extra_fields_rejected(self):
        event=threading.Event(); event.set()
        with patch.object(obs,'Connection') as connection:
            result=obs.ObsTool('control').execute_cancellable(self.inputs,None,event)
            self.assertFalse(result.success); connection.assert_not_called()
        with self.assertRaises(ValueError): obs.validate('control', self.inputs | {'script':'x'})


if __name__ == '__main__': unittest.main()
