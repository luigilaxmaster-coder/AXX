import tempfile,time,unittest,threading
from pathlib import Path
from backend.mobile.gateway import MobileGateway

class MobileCommandFlow(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.calls=[];self.operations={};self.kind='axx.system.telemetry'
  def backend(method,path,body):
   self.calls.append(path)
   if path.endswith('/resolve'):return {'match':'exact','command_id':self.kind,'inputs':{'script':'Get-Date'} if 'shell' in self.kind else {}}
   if path.endswith('/prepare'):
    self.operations[body['operation_id']]={**body,'state':'awaiting_approval'};return self.operations[body['operation_id']]
   if path.endswith('/execute'):
    row=self.operations[body['operation_id']];row.update(state='succeeded',postconditions_passed=True,output={'stdout':'ok'});return row
   if '/operations?' in path:return {'operation':self.operations[path.split('=')[-1]]}
   raise AssertionError(path)
  self.gateway=MobileGateway(Path(self.tmp.name)/'state.db',self.tmp.name,backend)
  self.device=self.gateway.store.consume_pairing(self.gateway.store.create_pairing(),'Phone')['device_id']
  self.body={'operation':'chat','command_id':'test-command','text':'estado del sistema','conversation_id':'main'}
 def settled(self):
  for _ in range(200):
   result=self.gateway.store.command(self.device,self.body['command_id'])
   if result['state'] in ('completed','failed') or result.get('result'):return result
   time.sleep(.01)
  self.fail('command did not settle')
 def test_chat_executes_registered_command_without_model_once(self):
  self.gateway.store.set_tool_permission(self.device,True)
  first=self.gateway.admit_chat(self.device,self.body)
  self.gateway.admit_chat(self.device,self.body)
  result=self.settled();self.assertEqual(result['state'],'completed')
  self.assertEqual(self.calls.count('/axx-api/commands/execute'),1)
  self.assertEqual(result['result']['operation']['operation_id'],first['task_id'])
 def test_query_only_cannot_execute(self):
  self.gateway.admit_chat(self.device,self.body)
  self.assertEqual(self.settled()['state'],'failed')
  self.assertNotIn('/axx-api/commands/prepare',self.calls)
 def test_shell_waits_for_pc_then_phone_recovers_result_without_replay(self):
  self.kind='axx.shell.powershell';self.gateway.store.set_tool_permission(self.device,True)
  self.gateway.admit_chat(self.device,self.body)
  result=self.settled();self.assertEqual(result['state'],'running')
  self.assertNotIn('/axx-api/commands/execute',self.calls)
  self.gateway.approve_work({'operation_id':result['task_id'],'approved':True})
  result=self.gateway.command_status(self.device,self.body['command_id'])
  self.assertEqual(result['state'],'completed');self.assertIn('ok',result['result']['message'])
  self.gateway.command_status(self.device,self.body['command_id'])
  self.assertEqual(self.calls.count('/axx-api/commands/execute'),1)
 def test_avatar_wait_wakes_on_event_and_restart_has_new_identity(self):
  result=[];thread=threading.Thread(target=lambda:result.append(self.gateway.avatar_events(0,True)))
  thread.start();time.sleep(.03)
  self.gateway.avatar_gesture(self.device,{'kind':'rotate','dx':5,'dy':1});thread.join(1)
  self.assertFalse(thread.is_alive());self.assertEqual(result[0]['events'][0]['dx'],5)
  other=MobileGateway(Path(self.tmp.name)/'other.db',self.tmp.name,lambda *a:{})
  self.assertNotEqual(result[0]['boot_id'],other.avatar_events(0)['boot_id'])
