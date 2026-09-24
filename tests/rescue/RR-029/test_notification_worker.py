#!/usr/bin/env python3
import json, os, stat, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; WORKER=ROOT/'65-rescue-receiver/rescue-notification.py'
class Worker(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory(); self.d=Path(self.t.name); self.state=self.d/'state'; self.fake=self.d/'openclaw'; self.log=self.d/'calls'
  self.fake.write_text('#!/bin/sh\necho "$*" >> "$CALLS"\ncase "$MODE" in ok) echo \'{"action":"send","channel":"telegram","dryRun":false,"messageId":"m-7","payload":{"accountId":"trusted","chatId":"42"}}\';; invalid) echo \'{"receipt":{"messageId":"old"}}\';; negative) echo \'{"action":"send","channel":"telegram","dryRun":false,"ok":false,"messageId":"old"}\';; mismatch) echo \'{"action":"send","channel":"telegram","dryRun":false,"messageId":"old","payload":{"accountId":"foreign"}}\';; timeout) sleep 2;; fail) exit 9;; esac\n');self.fake.chmod(0o755)
  self.env={**os.environ,'CALLS':str(self.log),'MODE':'ok'}
 def tearDown(self): self.t.cleanup()
 def call(self,*a,env=None,input=None): return subprocess.run(['python3',str(WORKER),*a],text=True,input=input,capture_output=True,env=env or self.env,check=True)
 def enqueue(self,origin=None):
  o=origin or {'authorized':True,'channel':'telegram','account':'trusted','target':'42'}
  answer=json.loads(self.call('enqueue','--state-dir',str(self.state),'--origin-json',json.dumps(o),'--incident-id','i','--instruction-id','n','--attempt-id','a','--attempt-generation','1','--idempotency-key','k','--stage','initial',input='hello').stdout)
  return answer
 def tick(self,env=None,*extra): return json.loads(self.call('tick','--state-dir',str(self.state),'--openclaw-bin',str(self.fake),'--timeout-seconds','.1',*extra,env=env).stdout)
 def test_success_restart_and_report_confirm_do_not_resend(self):
  op=self.enqueue(); got=self.tick(); self.assertEqual(got['pending_reports'][0]['notification']['message_id'],'m-7'); self.assertEqual(got['pending_reports'][0]['notification']['status'],'confirmed'); self.assertEqual(self.log.read_text().count('\n'),1)
  self.tick(); self.assertEqual(self.log.read_text().count('\n'),1)
  self.call('report-confirm','--state-dir',str(self.state),'--operation-id',op['operation_id']); self.assertEqual(self.tick()['pending_reports'],[]); self.assertEqual(self.log.read_text().count('\n'),1)
  self.assertEqual(stat.S_IMODE((self.state/'operations'/f"{op['operation_id']}.json").stat().st_mode),0o600)
 def test_invalid_receipt_never_proves_delivery(self):
  self.enqueue(); got=self.tick({**self.env,'MODE':'invalid'},'--max-retries','1'); self.assertEqual(got['pending_reports'][0]['notification']['status'],'failed'); self.assertIsNone(got['pending_reports'][0]['notification']['message_id'])
 def test_timeout_is_ambiguous_and_never_retried(self):
  self.enqueue(); got=self.tick({**self.env,'MODE':'timeout'}); self.assertEqual(got['pending_reports'][0]['notification']['status'],'pending'); self.tick({**self.env,'MODE':'ok'}); self.assertEqual(self.log.read_text().count('\n'),1)
 def test_foreign_origin_rejected(self):
  p=subprocess.run(['python3',str(WORKER),'enqueue','--state-dir',str(self.state),'--origin-json','{"channel":"signal","account":"x","target":"y"}','--incident-id','i','--instruction-id','n','--attempt-id','a','--attempt-generation','1','--idempotency-key','k','--stage','initial'],text=True,input='hello',capture_output=True); self.assertNotEqual(p.returncode,0)
 def test_negative_message_id_and_crash_sending_are_unconfirmed_or_failed(self):
  self.enqueue(); got=self.tick({**self.env,'MODE':'negative'},'--max-retries','1'); self.assertEqual(got['pending_reports'][0]['notification']['status'],'failed')
  op=self.enqueue({'authorized':True,'channel':'telegram','account':'trusted','target':'43'}); p=self.state/'operations'/f"{op['operation_id']}.json"; row=json.loads(p.read_text()); row['state']='sending';p.write_text(json.dumps(row)); got=self.tick(); self.assertIn('pending', [x['notification']['status'] for x in got['pending_reports']])
 def test_known_cli_shape_and_route_mismatch(self):
  self.enqueue(); self.assertEqual(self.tick()['pending_reports'][0]['notification']['status'],'confirmed')
  self.enqueue({'authorized':True,'channel':'telegram','account':'trusted','target':'43'}); got=self.tick({**self.env,'MODE':'mismatch'},'--max-retries','1'); self.assertEqual(next(x for x in got['pending_reports'] if x['notification']['target']=='43')['notification']['status'],'failed')
if __name__=='__main__': unittest.main()
