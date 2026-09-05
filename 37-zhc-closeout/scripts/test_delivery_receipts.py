import importlib.util
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).parent))
from verify_delivery_receipts import verify
from workforce_state import atomic_write,read,update

class DurableReceipts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.state=self.root/'state.json';self.registry=self.root/'registry.json'
        atomic_write(self.state,{'buildId':'build-a','ownerChat':'chat-a','commandCenterUrl':'https://a.example','messagesDelivered':[{'n':n,'messageId':str(n),'chatId':'chat-a','status':'sent'} for n in (1,6,7)]})
    def tearDown(self):self.tmp.cleanup()
    def prove(self):
        atomic_write(self.registry,{'chat-a':{str(n):1700000000000 for n in (1,6,7)}})
        self.assertEqual(verify(self.state,self.registry,{1,6,7}),0)
    def test_registry_rotation_keeps_only_previously_observed_receipts(self):
        self.prove();self.registry.unlink()
        self.assertEqual(verify(self.state,self.registry,{1,6,7}),0)
        self.assertTrue(all(r['verdict']=='pass-verified-receipt' for r in read(self.state)['telegramDeliveryVerification']['results']))
    def test_empty_rotated_registry_uses_retained_receipt(self):
        self.prove();atomic_write(self.registry,{})
        self.assertEqual(verify(self.state,self.registry,{1,6,7}),0)
    def test_changed_build_artifact_chat_or_message_cannot_reuse_proof(self):
        original=dict(read(self.state))
        for key,value in [('buildId','build-b'),('commandCenterUrl','https://b.example'),('ownerChat','chat-b')]:
            with self.subTest(field=key):
                atomic_write(self.state,copy.deepcopy(original));self.prove();self.registry.unlink()
                update(self.state,lambda s:s.update({key:value}))
                self.assertNotEqual(verify(self.state,self.registry,{1,6,7}),0)
    def test_retained_receipt_requires_finite_non_boolean_timestamp(self):
        self.prove();self.registry.unlink()
        original=read(self.state)
        for stamp in (True,float('inf'),float('nan')):
            with self.subTest(timestamp=stamp):
                tampered=copy.deepcopy(original)
                for receipt in tampered['telegramDeliveryReceipts'].values():receipt['registryTimestamp']=stamp
                atomic_write(self.state,tampered)
                self.assertNotEqual(verify(self.state,self.registry,{1,6,7}),0)
    def test_bare_old_pass_is_not_a_receipt(self):
        update(self.state,lambda s:s.update(telegramDeliveryVerification={'status':'pass'}))
        self.assertEqual(verify(self.state,self.registry,{1,6,7}),7)
        self.assertEqual(read(self.state)['telegramDeliveryVerification']['status'],'pending')
    def test_failed_send_cannot_borrow_a_live_registry_entry(self):
        self.prove();update(self.state,lambda s:s['messagesDelivered'][0].update(status='send-failed'))
        self.assertNotEqual(verify(self.state,self.registry,{1,6,7}),0)

if __name__=='__main__':unittest.main()
