#!/usr/bin/env python3
"""Exercise the receiver's shipped acceptance verifier, not a copy of it."""
import json, os, re, subprocess, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
POLL=ROOT/'65-rescue-receiver/rescue-poll.sh'

def function(name):
    text=POLL.read_text()
    start=text.index(name+'() {')
    marker='\n\n_rr_run_acceptance_verifier || true' if name == '_rr_run_acceptance_verifier' else '\n# ---------------------------------------------------------------------------'
    end=text.find(marker,start)
    return text[start:end]+'\n'

class AcceptanceProbe(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.bin=self.root/'bin';self.bin.mkdir()
  # Its output is the sole receiver-owned gateway observation.  No network is
  # possible in this harness because PATH resolves curl here first.
  (self.bin/'curl').write_text('#!/bin/sh\nprintf %s "${FAKE_HTTP_CODE:-000}"\n')
  (self.bin/'curl').chmod(0o755)
  self.functions=self.root/'functions.sh';self.functions.write_text(function('_rr_build_result')+function('_rr_hash')+function('_rr_run_acceptance_verifier'))
 def tearDown(self): self.temp.cleanup()
 def exercise(self, code, reply, check='health', kind='gateway_http', url='https://receiver.invalid/health'):
  runner=self.root/'run.sh'
  runner.write_text('''set -eu
source "$FUNCS"
_TMP="$TMP"; mkdir -p "$_TMP"
INCIDENT_ID=inc-1; TICKET_ID=ticket-1; INSTRUCTION_ID=instruction-1
ATTEMPT_ID=attempt-1; ATTEMPT_REF=attempt-1; ATTEMPT_GENERATION=2; RR_RUNTIME_ID=runtime-1; _op_id=op-1
RR_ACCEPTANCE_CHECK_ID="$CHECK"; RR_ACCEPTANCE_KIND="$KIND"; RR_ACCEPTANCE_URL="$URL"
_rr_run_acceptance_verifier || true
_rr_build_result "$REPLY" 0 12 excerpt
cat "$RR_RESULT_JSON"
''')
  env={**os.environ,'PATH':str(self.bin)+os.pathsep+os.environ['PATH'],'FUNCS':str(self.functions),'TMP':str(self.root/'tmp'),'FAKE_HTTP_CODE':code,'CHECK':check,'KIND':kind,'URL':url,'REPLY':reply}
  completed=subprocess.run(['bash',str(runner)],env=env,text=True,capture_output=True)
  if completed.returncode: raise AssertionError(completed.stderr or completed.stdout)
  return json.loads(completed.stdout)
 def repair_claim(self, evidence='agent:invented'):
  return '```json\n'+json.dumps({'repair_status':'repaired','verification_status':'verified','evidence_refs':[evidence],'fix_card':{'card_id':'fix','card_version':'1','scope_authorized':True},'acceptance_check':{'check_id':'health','passed':True,'evidence_ref':evidence}})+'\n```'
 def test_configured_2xx_replaces_agent_evidence_with_receiver_proof(self):
  result=self.exercise('204',self.repair_claim())
  self.assertEqual(result['repair_status'],'repaired'); self.assertTrue(result['acceptance_check']['evidence_ref'].startswith('receiver:gateway_http:inc-1:attempt-1:health:'))
  self.assertNotEqual(result['acceptance_check']['evidence_ref'],'agent:invented')
 def test_no_probe_or_bad_http_cannot_promote_agent_claim(self):
  for code,kind,url in [('500','gateway_http','https://receiver.invalid/x'),('000','gateway_http','https://receiver.invalid/x'),('204','agent_command','https://receiver.invalid/x'),('204','gateway_http','http://foreign.invalid/x')]:
   result=self.exercise(code,self.repair_claim(),kind=kind,url=url)
   self.assertEqual(result['repair_status'],'partial'); self.assertEqual(result['verification_status'],'unverified')
 def test_missing_result_stays_not_repaired_even_when_probe_passes(self):
  result=self.exercise('200','agent says all fixed')
  self.assertEqual(result['repair_status'],'not_repaired'); self.assertEqual(result['remaining_blocker']['reason'],'structured_result_missing')
if __name__=='__main__': unittest.main()
