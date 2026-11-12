"""Completed replay binds community access mode and the selected calendar staff."""
from copy import deepcopy
import hashlib
import unittest

import editor_replay as replay
import meeting_dynamic
from skill6_playwright import Stop
from test_meeting_dynamic import inputs as meeting_inputs


def community(inactive=True):
    step={'id':'community','action':'community','name':'Fixture Group','slug':'fixture-group'}
    if inactive is not None:step['inactive']=inactive
    selected=step.get('inactive',True)
    digest=hashlib.sha256(step['slug'].encode()).hexdigest()
    value={'status':'GROUP_REUSED_IDENTITY_CONFIRMED','name':step['name'],'slug':step['slug'],
        'portal_url':'https://portal.example.invalid/communities/groups/fixture-group/home',
        'group_status':'Inactive' if selected else 'Active','discovery':False,'deleted':False,
        'requested_slug_sha256':digest,'observed_slug_sha256':digest,
        'identity_source':'native_app_card_login_popup','slug_identity_verified':True,
        'portal_identity_verified':True,'native_name_seen_after_reload':True,
        'description_verified':False,'discovery_verified':False,'independent_readback':'VERIFIED',
        'functional_verified':False,'group_activation_attempted':False,'reused':True}
    return step,value


class ReceiptProfileTests(unittest.TestCase):
    def test_active_and_inactive_reuse_retain_exact_access_mode(self):
        for inactive in (True,False,None):
            step,value=community(inactive)
            with self.subTest(inactive=inactive):
                result=replay._result(step,value,{'location_id':'loc'})
                self.assertEqual(result['group_status'],value['group_status'])
                self.assertEqual(result['portal_url'],value['portal_url'])
                self.assertFalse(result['group_activation_attempted'])

    def test_community_route_status_slug_and_evidence_mismatches_fail(self):
        mutations=(
            lambda v:v.update(group_status='Active'),
            lambda v:v.update(portal_url=v['portal_url'].replace('/home','/inactive-group')),
            lambda v:v.update(portal_url=v['portal_url'].replace('/fixture-group/','/foreign/')),
            lambda v:v.update(group_activation_attempted=True),
            lambda v:v.update(portal_identity_verified=False),
            lambda v:v.update(requested_slug_sha256='0'*64),
        )
        for index,mutate in enumerate(mutations):
            step,value=community();mutate(value)
            with self.subTest(index=index),self.assertRaises(Stop):
                replay._result(step,value,{'location_id':'loc'})
        for invalid in ('true',1,0,None):
            step,value=community();step['inactive']=invalid
            with self.subTest(invalid=invalid),self.assertRaises(Stop):
                replay._result(step,value,{'location_id':'loc'})

    def meeting(self,*,target_room,first_room):
        data=meeting_inputs()
        data['expected_staff_locations'][0].update(location_kind='Meeting Room' if target_room else 'Custom',
            location_value='' if target_room else 'https://example.invalid/target')
        data['expected_staff_locations'].insert(0,{'staff_id':'other','staff_name':'Other Staff',
            'location_kind':'Meeting Room' if first_room else 'Custom',
            'location_value':'' if first_room else 'https://example.invalid/other'})
        data['staff_dependency']['users'].append({'id':'other','name':'Other Staff',
            'roles':{'locationIds':['loc']}})
        data['staff_dependency']['total_count']=2
        job={key:data[key] for key in ('location_id','location_name','start_url')}
        step={'id':'meeting','action':'native_dynamic_meeting_location','payload':data}
        value={'status':'DYNAMIC_MEETING_LOCATION_REUSED_AND_REOPENED' if target_room else
                'DYNAMIC_MEETING_LOCATION_SAVED_AND_REOPENED',
            'location_id':'loc','calendar_id':data['calendar_id'],'staff_id':data['staff_id'],
            'configuration_sha256':meeting_dynamic.configuration_hash(data),
            'independent_readback':'VERIFIED','native_location_kind':'Meeting Room',
            'appointment_created':False,'meeting_started':False,
            'dynamic_room_generation_verified':False,'functional_verified':False}
        return job,step,value

    def test_nonfirst_target_change_is_saved_even_when_first_staff_already_uses_room(self):
        job,step,value=self.meeting(target_room=False,first_room=True)
        result=replay._result(step,value,job)
        self.assertEqual(result['status'],'DYNAMIC_MEETING_LOCATION_SAVED_AND_REOPENED')

    def test_nonfirst_target_reuse_is_reused_even_when_first_staff_uses_custom(self):
        job,step,value=self.meeting(target_room=True,first_room=False)
        result=replay._result(step,value,job)
        self.assertEqual(result['status'],'DYNAMIC_MEETING_LOCATION_REUSED_AND_REOPENED')

    def test_wrong_target_status_and_cross_staff_receipts_are_rejected(self):
        job,step,base=self.meeting(target_room=False,first_room=True)
        for change in ({'status':'DYNAMIC_MEETING_LOCATION_REUSED_AND_REOPENED'},
                       {'staff_id':'other'},{'calendar_id':'other'},
                       {'configuration_sha256':'0'*64},{'functional_verified':True}):
            value={**deepcopy(base),**change}
            with self.subTest(change=change),self.assertRaises(Stop):replay._result(step,value,job)


if __name__=='__main__':unittest.main()
