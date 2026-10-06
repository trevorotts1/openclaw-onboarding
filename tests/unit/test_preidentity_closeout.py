#!/usr/bin/env python3
"""Real helper regressions for the 685-byte pre-onboarding resume stub."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
SCRIPTS=ROOT/'23-ai-workforce-blueprint/scripts'
sys.path.insert(0,str(SCRIPTS))
import workforce_completion as completion
from workforce_state import atomic_write, read
spec=importlib.util.spec_from_file_location('stub_launch',ROOT/'32-command-center-setup/scripts/interview-launch.py')
launch=importlib.util.module_from_spec(spec);spec.loader.exec_module(launch)


def old_pending_stub():
    build_id='00000000-0000-4000-8000-000000000001'
    return {'buildId':build_id,'completionVerification':{
        'version':1,'buildId':build_id,'companyId':None,'status':'pending',
        'checkedAt':'2026-09-05T18:45:00.000000+00:00',
        'unmetRequirements':completion.evaluate({}),
        'inputDigest':completion.input_digest({}),'artifactDigest':None},'stateRevision':1}


class PreidentityCloseout(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.state=self.root/'state.json'

    def test_no_verifier_creates_state_before_identity(self):
        for function in (completion.finalize,completion.refresh,completion.finalize_closeout):
            with self.subTest(function=function.__name__), patch.object(completion.subprocess,'run',side_effect=AssertionError('No external checks before identity')):
                self.assertFalse(function(self.state));self.assertFalse(self.state.exists())

    def test_unowned_failure_answers_and_old_stub_remain_byte_exact(self):
        for state in ({'commandCenterStatus':'failed'}, {'answers':{'Q1':'Keep this answer'}}, old_pending_stub()):
            atomic_write(self.state,state);before=self.state.read_bytes()
            for function in (completion.finalize,completion.refresh,completion.finalize_closeout):
                self.assertFalse(function(self.state));self.assertEqual(self.state.read_bytes(),before)

    def test_existing_legacy_slug_build_still_gets_pending_checks(self):
        atomic_write(self.state,{'companySlug':'fixture-legacy','answers':{'Q1':'Saved'}})
        self.assertFalse(completion.finalize(self.state))
        state=read(self.state);self.assertEqual(state['answers'],{'Q1':'Saved'})
        self.assertEqual(state['completionVerification']['status'],'pending')

    def test_exact_historical_stub_recovers_without_deleting_build_id(self):
        original=old_pending_stub();atomic_write(self.state,original)
        self.assertEqual(self.state.stat().st_size,685)
        self.assertTrue(launch.is_uninitialized(read(self.state)))
        launch.initialize(self.state,'fixture-company','Fixture Company','owner@example.test',{'OPENCLAW_OWNER_NAME':'Fixture Owner'})
        state=read(self.state)
        self.assertEqual(state['buildId'],original['buildId'])
        self.assertEqual(state['completionVerification'],original['completionVerification'])
        self.assertTrue(state['companyId']);self.assertTrue(state['tenantId']);self.assertTrue(state['installationId'])
        self.assertEqual(state['buildType'],'standard-first');self.assertFalse(state['interviewComplete'])

    def test_failure_metadata_can_coexist_with_exact_pending_stub(self):
        state=old_pending_stub();state.update(commandCenterStatus='failed',commandCenterFailureReason='Previous failure',stateRevision=9)
        self.assertTrue(launch.is_uninitialized(state))

    def test_unknown_answers_identity_and_build_evidence_never_count_as_fresh(self):
        for key,value in {'companyId':None,'companySlug':'existing','tenantId':'existing','installationId':'existing',
                          'answers':{},'interviewAnswers':{'Q1':'Saved'},'departments':[],
                          'buildCompletedAt':'previous','buildChecks':{},'unexpected':True}.items():
            state=old_pending_stub();state[key]=value
            with self.subTest(key=key):self.assertFalse(launch.is_uninitialized(state))

    def test_altered_receipt_never_unlocks_identity_allocation(self):
        variants={'status':'verified','companyId':'other-client','artifactDigest':'evidence',
                  'inputDigest':'different-inputs','unmetRequirements':[], 'buildId':'another-build',
                  'version':True,'checkedAt':'not-a-time','unexpected':'field'}
        for key,value in variants.items():
            state=old_pending_stub();state['completionVerification'][key]=value
            with self.subTest(key=key):self.assertFalse(launch.is_uninitialized(state))
        for key in ('buildId','completionVerification'):
            state=old_pending_stub();state.pop(key);self.assertFalse(launch.is_uninitialized(state))

    def test_answer_bearing_stub_initialization_refuses_without_changing_file(self):
        state=old_pending_stub();state['answers']={'Q1':'Preserve forever'}
        atomic_write(self.state,state);before=self.state.read_bytes()
        with self.assertRaises(ValueError):
            launch.initialize(self.state,'fixture','Fixture Company','owner@example.test',{})
        self.assertEqual(self.state.read_bytes(),before)

    def gate(self,relative):
        source=(ROOT/relative).read_text()
        start=source.index('if ! "$WORKFORCE_PYTHON" "$COMPLETION_SCRIPT" "$STATE_FILE" --has-identity')
        return source[start:source.index('\nfi',start)+3]

    def run_gate(self,relative):
        marker=self.root/'past-gate'
        values={'WORKFORCE_PYTHON':sys.executable,'COMPLETION_SCRIPT':str(SCRIPTS/'workforce_completion.py'),
                'STATE_FILE':str(self.state),'LOG_FILE':str(self.root/'log')}
        script='\n'.join(key+'='+shlex.quote(value) for key,value in values.items())+'\nlog() { :; }\n'
        script+=self.gate(relative)+'\nprintf reached > '+shlex.quote(str(marker))
        result=subprocess.run(['/bin/bash','-c',script],capture_output=True,text=True)
        return result,marker

    def test_actual_resume_guard_precedes_normalizer_and_leaves_stub_unchanged(self):
        relative='23-ai-workforce-blueprint/scripts/resume-workforce-build.sh'
        source=(ROOT/relative).read_text()
        self.assertLess(source.index('--has-identity'),source.index('\nnormalize_status_vocabulary\n'))
        for state in (None,old_pending_stub()):
            if state is not None:atomic_write(self.state,state)
            before=self.state.read_bytes() if self.state.exists() else None
            result,marker=self.run_gate(relative)
            self.assertEqual(result.returncode,0,result.stderr);self.assertFalse(marker.exists())
            self.assertEqual(self.state.read_bytes() if self.state.exists() else None,before)

    def test_actual_closeout_guard_refuses_unowned_state_before_failure_writes(self):
        atomic_write(self.state,old_pending_stub());before=self.state.read_bytes()
        result,marker=self.run_gate('37-zhc-closeout/scripts/run-closeout.sh')
        self.assertEqual(result.returncode,1,result.stderr);self.assertFalse(marker.exists())
        self.assertEqual(self.state.read_bytes(),before)


if __name__=='__main__':unittest.main()
