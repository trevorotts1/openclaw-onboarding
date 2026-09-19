#!/usr/bin/env python3
"""Crash-after-done regression for the poller's actual cache replay path."""
import json, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; POLL=ROOT/'65-rescue-receiver/rescue-poll.sh'
def extract(name):
 s=POLL.read_text(); a=s.index(name+'() {'); b=s.find('\n# ---------------------------------------------------------------------------',a)
 return s[a:b]+'\n'
class Recovery(unittest.TestCase):
 def test_final_intent_replays_without_turn_or_duplicate_send(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t); f=d/'f.sh'; log=d/'log'; done=d/'done'; done.mkdir()
   f.write_text('''_json_str(){ printf %s "$1"; }
_rr_hash(){ shasum -a 256 | cut -d' ' -f1; }
_now_iso(){ echo now; }; _op_id_for(){ echo op; }; _log(){ :; }
_json_field(){ python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(d.get(sys.argv[2],""))' "$1" "$2"; }
_ack(){ :; }; _rr_notification_enqueue(){ printf '%s|%s|%s|%s|%s\n' "$1" "$2" "$INCIDENT_ID" "$ATTEMPT_ID" "$ATTEMPT_GENERATION" >> "$LOG"; }
'''+extract('_write_done')+extract('_reack_cached')+'''\n_DONE="$DONE"; _TMP="$TMP"; mkdir -p "$_TMP"
IDEMPOTENCY_KEY=key; RR_CACHE_KEY=key; INCIDENT_ID=inc; INSTRUCTION_ID=inst; TICKET_ID=ticket; ATTEMPT_ID=attempt; ATTEMPT_GENERATION=1; RR_NOTIFICATION_ORIGIN='{"authorized":true,"channel":"telegram","account":"acct","target":"chat"}'; RR_NOTIFICATION_FINAL_BODY='Recovery is not verified. Remaining blocker: blocked'
_write_done delivered 0 1 '' 1 ''
# Crash point: no enqueue occurred before this cached replay.
_reack_cached key; _reack_cached key
''')
   r=subprocess.run(['bash',str(f)],env={'DONE':str(done),'TMP':str(d/'tmp'),'LOG':str(log)},text=True,capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr)
   lines=log.read_text().splitlines(); self.assertEqual(len(lines),2)
   self.assertTrue(all(x.startswith('final|Recovery is not verified. Remaining blocker: blocked|inc|attempt|1') for x in lines))
   record=json.loads(next(done.iterdir()).read_text()); self.assertEqual(record['notification_final']['origin']['target'],'chat')
 def test_missing_intent_never_invents_a_final_route(self):
  self.assertIn('if [ -n "$_rc_notify" ]',POLL.read_text())
if __name__=='__main__': unittest.main()
