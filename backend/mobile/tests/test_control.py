import tempfile
import unittest
import uuid
from pathlib import Path
from backend.mobile.control import RemoteControl
from backend.mobile.trust_store import MobileTrustStore

class Native:
    def __init__(self):self.active=False;self.reason='idle';self.sent=[]
    def status(self):return {'active':self.active,'reason':self.reason,'keys':[],'buttons':[]}
    def grant(self,*args):self.active=True
    def renew(self,*args):
        if not self.active:raise ValueError('Local input has priority')
    def cancel(self,reason):self.active=False;self.reason=reason
    def events(self,lease,events):
        if not self.active:raise ValueError('Revoked')
        self.sent.extend(events)

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=MobileTrustStore(Path(self.tmp.name)/'state.db')
        self.device=self.store.consume_pairing(self.store.create_pairing(),'Android')['device_id']
        self.store.set_input_permission(self.device,True)
        self.now=100.;self.native=Native();self.control=RemoteControl(self.store,self.native,lambda:self.now)
        self.request={'request_id':str(uuid.uuid4()),'visible':True}
    def acquire(self):
        s=self.control.acquire(self.device,self.request)
        return {'lease_id':s['lease']['lease_id'],'boot_id':s['boot_id']}
    def test_dedup_hash_order_and_foreign_lease(self):
        b={**self.acquire(),'seq':1,'events':[{'type':'move','x':12,'y':-4}]}
        self.control.events(self.device,b);self.control.events(self.device,b)
        self.assertEqual(len(self.native.sent),1)
        for bad in ({**b,'events':[{'type':'move','x':99,'y':0}]},{**b,'seq':3},{**b,'lease_id':str(uuid.uuid4())}):
            with self.assertRaises(ValueError):self.control.events(self.device,bad)
    def test_expiry_revokes_and_prevents_reacquiring_with_old_request(self):
        b=self.acquire();self.now+=4
        with self.assertRaises(ValueError):self.control.renew(self.device,{**b,'visible':True})
        self.assertFalse(self.native.active)
        with self.assertRaises(ValueError):self.control.acquire(self.device,self.request)
    def test_local_input_has_priority_and_no_automatic_recovery(self):
        b=self.acquire();self.native.cancel('local_input')
        with self.assertRaises(ValueError):self.control.events(self.device,{**b,'seq':1,'events':[{'type':'key','key':'Control','down':True}]})
        self.assertEqual(self.control.status()['lease']['state'],'released')
        self.assertEqual(self.native.sent,[])
    def test_permissions_revocation_visibility_and_second_owner(self):
        with self.assertRaises(ValueError):self.control.acquire(self.device,{**self.request,'visible':False})
        b=self.acquire()
        with self.assertRaises(ValueError):self.control.acquire('other',{'request_id':str(uuid.uuid4()),'visible':True})
        self.store.set_input_permission(self.device,False)
        with self.assertRaises(ValueError):self.control.renew(self.device,{**b,'visible':True})
        self.assertFalse(self.native.active)
    def test_invalid_payload_does_not_inject_or_advance_sequence(self):
        b=self.acquire()
        for event in ({'type':'move','x':True,'y':0},{'type':'text','text':'\x00'},{'type':'key','key':'unknown','down':True}):
            with self.assertRaises(ValueError):self.control.events(self.device,{**b,'seq':1,'events':[event]})
        self.assertEqual(self.control.status()['lease']['last_seq'],0)
        self.control.release(self.device,b)
        self.assertFalse(self.native.active)
