import unittest
from copy import deepcopy
from pathlib import Path

import editor_replay
from receipt_validation import pending_proof
from meeting_oauth_handoff import validate_inputs, configuration_hash
from recipe_cli import compile_recipe
from skill6_playwright import Stop, validate_job


def inputs():
    return {'location_id':'loc','location_name':'Fixture account',
        'start_url':'https://app.convertandflow.com/v2/location/loc/settings/calendars?section=calendars',
        'integration_mode':'provider_oauth_handoff','staff_id':'user-1','staff_name':'Trevor Fixture',
        'provider':'Zoom','staff_dependency':{'status':'VERIFIED','provider':'public_api',
            'location_id':'loc','observed_at':1.0,'operation':'users.search','http_status':200,
            'complete':True,'total_count':1,'users':[{'id':'user-1','name':'Trevor Fixture',
                'roles':{'locationIds':['loc']}}]}}


class ProviderOAuthHandoffTests(unittest.TestCase):
    def test_handoff_compiles_through_recipe_cli_and_replay_stays_pending_without_consent(self):
        data=inputs()
        payload={key:value for key,value in data.items() if key!='integration_mode'}
        validate_inputs(payload,require_fresh=False)
        job=validate_job(compile_recipe('meetings.integrate',data),Path('.'))
        step=job['steps'][0]
        self.assertEqual(step['action'],'native_provider_oauth_handoff')
        receipt={'status':'PENDING_USER_AUTHORIZATION','location_id':'loc','staff_id':'user-1',
            'provider':'Zoom','configuration_sha256':configuration_hash(payload),
            'oauth_popup_opened':True,'authorization_completed':False,'consent_submitted':False,
            'connection_verified':False,'popup_origin_sha256':'a'*64}
        safe=editor_replay._result(step,receipt,job)
        self.assertEqual(safe['status'],'PENDING_USER_AUTHORIZATION')
        self.assertFalse(safe['consent_submitted'])
        self.assertFalse(safe['connection_verified'])
        self.assertTrue(pending_proof(safe))

    def test_handoff_refuses_nonunique_staff_or_unapproved_provider(self):
        data=inputs()
        duplicate=deepcopy(data)
        duplicate['staff_dependency']['users'].append(
            {'id':'user-2','name':'Trevor Fixture','roles':{'locationIds':['loc']}})
        duplicate['staff_dependency']['total_count']=2
        with self.assertRaises(Stop):validate_inputs(duplicate,require_fresh=False)
        bad=deepcopy(data);bad['provider']='Unknown Conference'
        with self.assertRaises(Stop):validate_inputs(bad,require_fresh=False)


if __name__=='__main__':unittest.main()
