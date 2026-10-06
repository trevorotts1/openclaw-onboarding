#!/usr/bin/env python3
"""Crash-after-done regression for the poller's actual cache replay path."""
import json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; POLL=ROOT/'65-rescue-receiver/rescue-poll.sh'
def extract(name):
 s=POLL.read_text(); a=s.index(name+'() {'); b=s.find('\n# ---------------------------------------------------------------------------',a)
 if name in ('_rr_notification_tick','_rr_notification_enqueue'): b=s.index('\n}\n',a)+3
 return s[a:b]+'\n'
class Recovery(unittest.TestCase):
 def test_final_intent_replays_without_turn_or_duplicate_send(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t); f=d/'f.sh'; log=d/'log'; done=d/'done'; done.mkdir(); shutil.copy(ROOT/'65-rescue-receiver/rescue-notification.py',d/'rescue-notification.py')
   cli=d/'openclaw'; cli.write_text('#!/bin/sh\necho send >> "$LOG"\necho \'{"action":"send","channel":"telegram","dryRun":false,"messageId":"m","payload":{"accountId":"acct","chatId":"chat"}}\'\n');cli.chmod(0o755)
   f.write_text('''_json_str(){ printf %s "$1"; }
_rr_hash(){ shasum -a 256 | cut -d' ' -f1; }
_now_iso(){ echo now; }; _op_id_for(){ echo op; }; _log(){ :; }
_json_field(){ python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(d.get(sys.argv[2],""))' "$1" "$2"; }
_ack(){ :; }; _post(){ return 1; }
'''+extract('_write_done')+extract('_reack_cached')+extract('_rr_notification_tick')+extract('_rr_notification_enqueue')+'''\n_DONE="$DONE"; _TMP="$TMP"; _STATE="$STATE"; _OC_BIN="$CLI"; mkdir -p "$_TMP"
IDEMPOTENCY_KEY=key; RR_CACHE_KEY=key; INCIDENT_ID=inc; INSTRUCTION_ID=inst; TICKET_ID=ticket; ATTEMPT_ID=attempt; ATTEMPT_GENERATION=1; RR_NOTIFICATION_ORIGIN='{"authorized":true,"channel":"telegram","account":"acct","target":"chat"}'; RR_NOTIFICATION_FINAL_BODY=$(printf 'Recovery is not verified.\nRemaining blocker: blocked')
_write_done delivered 0 1 '' 1 ''
# Crash point: no enqueue occurred before this cached replay.
_reack_cached key; _reack_cached key
''')
   r=subprocess.run(['bash',str(f)],env={**os.environ,'DONE':str(done),'TMP':str(d/'tmp'),'STATE':str(d/'state'),'CLI':str(cli),'LOG':str(log)},text=True,capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr)
   lines=log.read_text().splitlines(); self.assertEqual(lines,['send'])
   ops=list((d/'state'/'notifications'/'operations').glob('*.json')); self.assertEqual(len(ops),1)
   job=json.loads(ops[0].read_text()); self.assertEqual(job['stage'],'final'); self.assertEqual(job['body'],'Recovery is not verified.\nRemaining blocker: blocked')
   record=json.loads(next(done.iterdir()).read_text()); self.assertEqual(record['notification_final']['origin']['target'],'chat')
 def test_missing_intent_never_invents_a_final_route(self):
  self.assertIn('if [ -n "$_rc_notify" ]',POLL.read_text())
if __name__=='__main__': unittest.main()
