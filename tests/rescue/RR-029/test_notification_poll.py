#!/usr/bin/env python3
"""Hermetic integration test for the poller's real notification drain."""
import json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]; POLL=ROOT/'65-rescue-receiver/rescue-poll.sh'; WORKER=ROOT/'65-rescue-receiver/rescue-notification.py'
def tick_function():
 text=POLL.read_text(); start=text.index('_rr_notification_tick() {'); end=text.index('\n_rr_notification_tick\n',start)
 return text[start:end]+'\n'
class NotificationPoll(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory(); self.d=Path(self.t.name); self.state=self.d/'state'; self.calls=self.d/'calls'; self.request=self.d/'request'; self.worker=self.d/'rescue-notification.py';shutil.copy(WORKER,self.worker);self.worker.chmod(0o755)
  self.cli=self.d/'openclaw'; self.cli.write_text('#!/bin/sh\necho x >> "$CALLS"\necho \'{"action":"send","channel":"telegram","dryRun":false,"messageId":"m-1","payload":{"accountId":"acct","chatId":"chat"}}\'\n');self.cli.chmod(0o755)
  self.runner=self.d/'runner.sh'; self.runner.write_text('''set -u
source "$FUNCS"
_STATE="$STATE"; _OC_BIN="$CLI"; RR_BOX_SLUG=box-good
_post() { printf '%s' "$1" > "$REQUEST"; [ "${POST_OK:-yes}" = yes ] || return 1; printf '%s' "$POST_RESPONSE"; }
_rr_notification_tick
''')
  self.enqueue()
 def tearDown(self): self.t.cleanup()
 def enqueue(self):
  args=['python3',str(self.worker),'enqueue','--state-dir',str(self.state/'notifications'),'--origin-json','{"authorized":true,"channel":"telegram","account":"acct","target":"chat"}','--incident-id','inc','--instruction-id','inst','--attempt-id','attempt','--attempt-generation','1','--idempotency-key','key']
  out=subprocess.run(args,input='body',text=True,capture_output=True,check=True).stdout; self.op=json.loads(out)['operation_id']
 def execute(self, response, ok=True):
  env={**os.environ,'FUNCS':str(self.d/'functions.sh'),'STATE':str(self.state),'CLI':str(self.cli),'CALLS':str(self.calls),'REQUEST':str(self.request),'POST_RESPONSE':response,'POST_OK':'yes' if ok else 'no'}
  (self.d/'functions.sh').write_text(tick_function())
  subprocess.run(['bash',str(self.runner)],env=env,text=True,capture_output=True,check=True)
 def pending(self):
  row=json.loads(next((self.state/'notifications'/'operations').glob('*.json')).read_text());return row
 def test_exact_2xx_receipt_settles_and_repeat_does_not_resend(self):
  self.execute(json.dumps({'ok':True,'operation_id':self.op,'receipt':{'revision':1},'notification_state':'confirmed'}))
  self.assertEqual(json.loads(self.request.read_text())['box_slug'],'box-good');self.assertEqual(self.pending()['report_state'],'confirmed');self.assertEqual(self.calls.read_text().count('\n'),1)
  self.execute(json.dumps({'ok':True,'operation_id':self.op,'receipt':{'revision':1},'notification_state':'confirmed'}));self.assertEqual(self.calls.read_text().count('\n'),1)
 def test_wrong_operation_2xx_stays_pending(self):
  self.execute(json.dumps({'ok':True,'operation_id':'other','receipt':{'revision':1},'notification_state':'confirmed'}));self.assertEqual(self.pending()['report_state'],'pending')
 def test_http_error_with_ok_body_stays_pending(self):
  self.execute(json.dumps({'ok':True,'operation_id':self.op,'receipt':{'revision':1},'notification_state':'confirmed'}),ok=False);self.assertEqual(self.pending()['report_state'],'pending')
if __name__=='__main__': unittest.main()
