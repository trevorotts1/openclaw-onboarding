"""Private native association identity, no-retry and collateral-state boundaries."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import community_courses as courses
import community_portal as portal
from skill6_playwright import Stop
from test_community_portal import Page, inputs as portal_inputs, read_identity

_native_inventory=courses._inventory


def inputs():
    data=portal_inputs();data.pop('channels')
    data['course_associations']={'course_id':'COURSE','course_title':'Exact course',
        'expected_group_id':'GROUP','visibility':'Private','expected_courses':[]}
    data['api_capability']={'location_id':data['location_id'],'version':'v3','status':'PASS',
        'source':'fixture','scopes':['courses.readonly'],'checked_at':datetime.now(timezone.utc).isoformat()}
    return data


class Api:
    def __init__(self):
        self.calls=[];self.pages=[{'products':[{'id':'COURSE','title':'Exact course'}],'nextCursor':None}]
        self.current={'id':'COURSE','title':'Exact course'}
    def request(self,method,path,*,location_id,query=None):
        self.calls.append((method,path,location_id,deepcopy(query)))
        if path=='/courses/products':
            return deepcopy(self.pages[0 if not query.get('cursor') else 1])
        return deepcopy(self.current)


class LearningPage(Page):
    def __init__(self,data):
        super().__init__(data);self.identity['group_id']='GROUP';self.cards=[];self.lose_save=False
    def goto(self,url,**kwargs):self.url=url
    def locator(self,selector):
        if selector.startswith('a[href="/communities/groups/'):
            ready=Mock();ready.count.return_value=1;ready.is_visible.return_value=True
            return ready
        raise AssertionError('Unexpected fixture selector '+selector)
    def wait_for_load_state(self,*args,**kwargs):pass
    def reload(self,**kwargs):
        super().reload(**kwargs)
        if self.lose_save:self.cards=[]


class CommunityCourseTests(unittest.TestCase):
    def setUp(self):
        self.data=inputs();self.page=LearningPage(self.data);self.api=Api()
        self.context=portal.capture_context(self.page,self.data,identity_reader=read_identity,clock=lambda:10)
        self.root=tempfile.TemporaryDirectory();self.addCleanup(self.root.cleanup)
        self.inventory=patch.object(courses,'_inventory',side_effect=lambda page,plan,facts:deepcopy(page.cards))
        self.inventory.start();self.addCleanup(self.inventory.stop)
        def add(page,plan,context,clock):
            journal=json.loads(Path(self.root.name,'community-details-state.json').read_text())
            self.assertEqual(journal['status'],'INTENT_RECORDED')
            # Native Default ordering is observed, not assumed to append last.
            page.cards.insert(0,{'course_id':'COURSE','title':'Exact course','visibility':'Private'})
            return True
        self.add_patch=patch.object(courses,'_add',side_effect=add)
        self.add=self.add_patch.start();self.addCleanup(self.add_patch.stop)

    def run_courses(self):
        return courses.run_courses(self.page,self.data,self.root.name,portal_context=self.context,
            transport=self.api,clock=lambda:11)

    def test_private_add_binds_native_ids_and_replays_without_api_or_add(self):
        result=self.run_courses()
        self.assertEqual(result['status'],'NEEDS_VERIFICATION')
        self.assertEqual(result['course_id'],'COURSE');self.assertEqual(result['group_id'],'GROUP')
        self.assertTrue(result['share_post_skipped']);self.assertFalse(result['communication_attempted'])
        self.assertFalse(result['functional_verified'])
        calls=len(self.api.calls)
        self.assertTrue(self.run_courses()['replayed'])
        self.assertEqual(len(self.api.calls),calls);self.assertEqual(self.add.call_count,1)

    def test_unique_native_option_is_bound_against_all_api_pages(self):
        self.api.pages=[{'products':[{'id':'OTHER','title':'Other course'}],'nextCursor':'next'},
            {'products':[{'id':'COURSE','title':'Exact course'}],'nextCursor':None}]
        self.run_courses()
        self.assertTrue(any(call[3] and call[3].get('cursor')=='next' for call in self.api.calls))

    def test_duplicate_title_foreign_course_or_location_refuses_before_add(self):
        variants=[{'products':[{'id':'COURSE','title':'Exact course'},{'id':'OTHER','title':'exact COURSE'}]},
                  {'products':[{'id':'OTHER','title':'Exact course'}]},
                  {'products':[{'id':'COURSE','title':'Exact course','locationId':'OTHER'}]}]
        for value in variants:
            with self.subTest(value=value):
                self.api.pages=[value]
                with self.assertRaises(Stop):self.run_courses()
                self.add.assert_not_called()

    def test_existing_exact_private_association_is_reused_without_add(self):
        card={'course_id':'COURSE','title':'Exact course','visibility':'Private'}
        self.page.cards=[card];self.data['course_associations']['expected_courses']=[deepcopy(card)]
        result=self.run_courses()
        self.assertTrue(result['reused']);self.assertFalse(result['share_post_skipped'])
        self.add.assert_not_called()

    def test_stale_native_inventory_or_existing_different_access_refuses(self):
        card={'course_id':'COURSE','title':'Exact course','visibility':None}
        self.page.cards=[card]
        with self.assertRaisesRegex(Stop,'inventory changed'):self.run_courses()
        self.data['course_associations']['expected_courses']=[deepcopy(card)]
        with self.assertRaisesRegex(Stop,'different title/access'):self.run_courses()
        self.add.assert_not_called()

    def test_lost_persisted_card_leaves_uncertain_journal_and_never_retries(self):
        self.page.lose_save=True
        with self.assertRaisesRegex(Stop,'readback'):self.run_courses()
        journal=Path(self.root.name,'community-details-state.json')
        self.assertEqual(json.loads(journal.read_text())['status'],'RECONCILIATION_REQUIRED')
        calls=len(self.api.calls)
        with self.assertRaisesRegex(Stop,'uncertain or unbound'):self.run_courses()
        self.assertEqual(self.add.call_count,1);self.assertEqual(len(self.api.calls),calls)

    def test_group_or_user_change_refuses_before_native_add(self):
        for key,value in (('group_id','OTHER'),('user_id','OTHER')):
            original=self.page.identity[key];self.page.identity[key]=value
            with self.subTest(key=key),self.assertRaises(Stop):self.run_courses()
            self.add.assert_not_called();self.page.identity[key]=original

    def test_journal_proof_tampering_and_foreign_writers_refuse(self):
        self.run_courses();journal=Path(self.root.name,'community-details-state.json')
        state=json.loads(journal.read_text());state['outcome']['functional_verified']=True
        journal.write_text(json.dumps(state))
        with self.assertRaisesRegex(Stop,'saved proof'):self.run_courses()
        self.assertEqual(self.add.call_count,1)

    def test_collateral_sibling_change_cannot_be_saved_as_success(self):
        sibling={'course_id':'KEEP','title':'Keep course','visibility':None}
        self.page.cards=[deepcopy(sibling)];self.data['course_associations']['expected_courses']=[deepcopy(sibling)]
        def corrupt(page,plan,context,clock):
            page.cards=[{'course_id':'COURSE','title':'Exact course','visibility':'Private'}]
            return True
        self.add.side_effect=corrupt
        with self.assertRaisesRegex(Stop,'sibling cards'):self.run_courses()

    def test_nonprivate_write_modes_and_json_context_cannot_authorize(self):
        for visibility in ('All members','Buy Now','Time Unlock','Level Unlock'):
            data=deepcopy(self.data);data['course_associations']['visibility']=visibility
            with self.subTest(visibility=visibility),self.assertRaises(Stop):courses.validate_inputs(data)
        self.page.url=courses._learning_url(self.data)
        with self.assertRaises(Stop):courses._check(self.page,self.data,{'authenticated':True},clock=lambda:11)

    def test_empty_native_cards_are_unproven_even_with_authenticated_group_id(self):
        ready=Mock();ready.count.return_value=1;ready.is_visible.return_value=True
        absent=Mock();absent.count.return_value=0
        page=Mock();page.get_by_text.return_value=ready
        page.get_by_role.side_effect=lambda role,**kwargs:absent if not isinstance(kwargs.get('name'),str) else ready
        grid=Mock();grid.count.return_value=1;grid.is_visible.return_value=True;grid.locator.return_value=absent
        page.locator.side_effect=lambda selector:grid if selector=='div.courses-grid' else absent
        for facts in ({},{'group_id':'GROUP'}):
            with self.subTest(facts=facts),self.assertRaisesRegex(Stop,'NATIVE_EMPTY_COURSE_INVENTORY_UNPROVEN'):
                _native_inventory(page,self.data,facts)

    def test_native_course_card_requires_matching_product_group_and_dom_ids(self):
        ready=Mock();ready.count.return_value=1;ready.is_visible.return_value=True
        absent=Mock();absent.count.return_value=0
        page=Mock();page.get_by_text.return_value=ready
        page.get_by_role.side_effect=lambda role,**kwargs:absent if not isinstance(kwargs.get('name'),str) else ready
        card=Mock();collection=Mock();collection.count.return_value=1;collection.nth.return_value=card
        grid=Mock();grid.count.return_value=1;grid.is_visible.return_value=True;grid.locator.return_value=collection
        page.locator.side_effect=lambda selector:grid if selector=='div.courses-grid' else collection
        analytics={'event':'community_course_opened_event','productId':'COURSE','groupId':'GROUP'}
        card.get_attribute.side_effect=lambda key:json.dumps(analytics) if key=='data-analytics' else 'course-card-COURSE-'
        title=Mock();title.count.return_value=1;title.is_visible.return_value=True;title.inner_text.return_value='Exact course'
        badge=Mock();badge.count.return_value=1;badge.inner_text.return_value='Private'
        card.locator.side_effect=lambda selector:title if selector.startswith('h2') else badge if 'lock-text-badge' in selector else ready
        self.assertEqual(_native_inventory(page,self.data,{}),[{'course_id':'COURSE','title':'Exact course','visibility':'Private'}])
        analytics['groupId']='FOREIGN'
        with self.assertRaisesRegex(Stop,'another group'):_native_inventory(page,self.data,{})


if __name__=='__main__':unittest.main()
