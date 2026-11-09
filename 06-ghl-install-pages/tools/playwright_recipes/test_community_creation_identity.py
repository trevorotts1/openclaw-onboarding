"""Native create redirect binds authored name/slug without trusting list names."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

import community_creation as creation
from skill6_playwright import Stop


def step():
    return {'action':'community', '_context':{'location_id':'LOC','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/memberships/communities/community-groups'},
        'name':'ZHC Test & Group','slug':'zhc-test-group','description':'Authored description',
        'allow_creation':True,'inactive':False,'discovery':False}


class CommunityCreationIdentityTests(unittest.TestCase):
    def setUp(self):
        self.data=step();self.context=self.data['_context'];self.base=self.context['start_url']
        self.patch=patch.object(creation,'assert_tenant');self.guard=self.patch.start();self.addCleanup(self.patch.stop)

    def read(self,query):
        return creation._created_identity(SimpleNamespace(url=self.base+'?'+query),self.context,self.data)

    def test_encoded_native_name_and_exact_slug_are_bound_after_create(self):
        result=self.read(urlencode({'groupCreated':self.data['name'],'groupSlug':self.data['slug']}))
        self.assertEqual(result,{'name':self.data['name'],'slug':self.data['slug']})
        self.guard.assert_called_once()

    def test_wrong_name_slug_duplicate_or_missing_identity_never_passes(self):
        variants=[{'groupCreated':'Different','groupSlug':self.data['slug']},
                  {'groupCreated':self.data['name'],'groupSlug':'different'},
                  {'groupCreated':self.data['name']},
                  {'groupCreated':self.data['name'],'groupSlug':self.data['slug'],'extra':'unexpected'}]
        for query in [urlencode(value) for value in variants]+[
                'groupCreated=A&groupCreated=A', 'groupCreated&groupSlug=zhc-test-group']:
            with self.subTest(query=query),self.assertRaises(Stop):self.read(query)
        self.guard.assert_not_called()

    def test_foreign_app_location_origin_or_fragment_refuses(self):
        query=urlencode({'groupCreated':self.data['name'],'groupSlug':self.data['slug']})
        for url in (self.base.replace('/LOC/','/OTHER/')+'?'+query,
                    self.base.replace('app.convertandflow.com','foreign.example.com')+'?'+query,
                    self.base+'?'+query+'#unexpected'):
            with self.subTest(url=url),self.assertRaises(Stop):
                creation._created_identity(SimpleNamespace(url=url),self.context,self.data)

    def test_unsettled_create_or_empty_list_url_is_not_false_identity(self):
        create=self.base.rsplit('/',1)[0]+'/create-group'
        for url in (create,self.base):
            self.assertIsNone(creation._created_identity(SimpleNamespace(url=url),self.context,self.data))
        self.guard.assert_not_called()

    def test_intake_does_not_accept_creation_identity_query_as_reuse_proof(self):
        data=deepcopy(self.data);data['_context']['start_url']+='?groupCreated=ZHC+Test&groupSlug=other'
        with self.assertRaises(Stop):creation.validate(data)

    def test_native_name_limit_is_thirty_not_one_hundred(self):
        data=deepcopy(self.data);data['name']='x'*30
        self.assertEqual(creation.validate(data)['name'],data['name'])
        data['name']='x'*31
        with self.assertRaises(Stop):creation.validate(data)


if __name__=='__main__':unittest.main()
