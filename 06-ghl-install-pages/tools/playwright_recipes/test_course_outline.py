"""Existing draft course outline edits must preflight and preserve their targets."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import course_outline as outline
from skill6_playwright import Stop


def capability():
    return {'location_id':'LOC', 'version':'v3','status':'PASS','source':'synthetic-probe',
        'scopes':['courses.readonly','courses.write'],'checked_at':datetime.now(timezone.utc).isoformat()}


def plan():
    return {'location_id':'LOC','product_id':'P',
        'category_changes':[{'category_id':'C1','expected_updated_at':'v1',
                             'changes':{'title':'Updated module'}}],
        'lesson_changes':[{'lesson_id':'L2','category_id':'C2','expected_updated_at':'v1',
                           'changes':{'description':'Updated lesson'}}]}


class Api:
    def __init__(self, root):
        self.root = Path(root)
        self.rows = {'/courses/products/P':{'id':'P','title':'Course'}}
        for identity in ('C1','C2'):
            self.rows['/courses/products/P/categories/'+identity] = {
                'id':identity,'productId':'P','title':'Original module','visibility':'draft',
                'updatedAt':'v1','futureColumn':{'keep':True}}
        for identity, parent in (('L1','C1'),('L2','C2')):
            self.rows['/courses/products/P/lessons/'+identity] = {
                'id':identity,'productId':'P','categoryId':parent,'title':'Original lesson',
                'description':'Original','visibility':'draft','updatedAt':'v1','contentType':'video',
                'metaData':{'keep':True},'futureColumn':'preserved'}
        self.calls = []
        self.counts = {}
        self.intents = []
        self.fail_put = False
        self.lose_sibling = False
        self.retain_metadata = False
        self.on_get = None

    def request(self, method, path, *, location_id, body=None):
        assert location_id == 'LOC'
        self.calls.append((method,path,deepcopy(body)))
        if method == 'GET':
            self.counts[path] = self.counts.get(path,0)+1
            value = deepcopy(self.rows[path])
            if self.on_get:self.on_get(path,self.counts[path],value)
            return value
        assert method == 'PUT'
        self.intents.append(json.loads((self.root/'delivery-state.json').read_text()))
        if self.fail_put:raise TimeoutError('synthetic uncertain response')
        old = self.rows[path].get('metaData')
        self.rows[path].update(deepcopy(body))
        self.rows[path]['updatedAt'] = 'v2'
        if self.retain_metadata and 'metaData' in body:self.rows[path]['metaData'] = old
        if self.lose_sibling:self.rows[path].pop('futureColumn',None)
        return deepcopy(self.rows[path])


class DraftOutlineTests(unittest.TestCase):
    def test_all_targets_preflight_before_any_write_and_pending_replay_does_not_write(self):
        with tempfile.TemporaryDirectory() as root:
            api = Api(root)
            result = outline.run_outline(plan(),root,capability=capability(),transport=api)
            self.assertEqual(result['status'],'NEEDS_VERIFICATION')
            self.assertFalse(result['functional_verified'])
            self.assertEqual(result['current_step_status'],'VERIFIED')
            index = next(i for i,call in enumerate(api.calls) if call[0]=='PUT')
            reads = {call[1] for call in api.calls[:index] if call[0]=='GET'}
            self.assertEqual(reads,{'/courses/products/P','/courses/products/P/categories/C1',
                '/courses/products/P/categories/C2','/courses/products/P/lessons/L2'})
            self.assertTrue(all(state['current_step_status']=='INTENT_RECORDED' for state in api.intents))
            self.assertEqual([call[2] for call in api.calls if call[0]=='PUT'],
                [{'title':'Updated module'},{'description':'Updated lesson'}])
            count = len(api.calls)
            replay = outline.run_outline(plan(),root,capability=capability(),transport=api)
            self.assertEqual(replay['status'],'NEEDS_VERIFICATION')
            self.assertEqual(len(api.calls),count)

    def test_later_stale_version_or_wrong_category_blocks_the_entire_batch_before_writes(self):
        for mutation in ('stale','parent','published-parent'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as root:
                api = Api(root)
                if mutation=='stale':api.rows['/courses/products/P/lessons/L2']['updatedAt']='v3'
                elif mutation=='parent':api.rows['/courses/products/P/lessons/L2']['categoryId']='C1'
                else:api.rows['/courses/products/P/categories/C2']['visibility']='published'
                with self.assertRaises(Stop):outline.run_outline(plan(),root,capability=capability(),transport=api)
                self.assertFalse(any(call[0]=='PUT' for call in api.calls))
                self.assertFalse(Path(root,'delivery-state.json').exists())

    def test_foreign_target_claims_never_reach_a_write(self):
        for field, value in (('id','FOREIGN'),('locationId','OTHER'),('productId','OTHER')):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as root:
                api=Api(root);api.rows['/courses/products/P/lessons/L2'][field]=value
                with self.assertRaises(Stop):outline.run_outline(plan(),root,capability=capability(),transport=api)
                self.assertFalse(any(call[0]=='PUT' for call in api.calls))

    def test_target_drift_between_preflight_and_put_stops_without_writing(self):
        with tempfile.TemporaryDirectory() as root:
            api=Api(root)
            def drift(path,count,row):
                if path.endswith('/C1') and count==2:row['title']='Concurrent edit'
            api.on_get=drift
            with self.assertRaisesRegex(Stop,'after the complete preflight'):
                outline.run_outline(plan(),root,capability=capability(),transport=api)
            self.assertFalse(any(call[0]=='PUT' for call in api.calls))

    def test_parent_becoming_published_after_preflight_stops_before_lesson_put(self):
        with tempfile.TemporaryDirectory() as root:
            api=Api(root)
            def drift(path,count,row):
                if path.endswith('/C2') and count==2:row['visibility']='published'
            api.on_get=drift
            with self.assertRaises(Stop):outline.run_outline(plan(),root,capability=capability(),transport=api)
            writes=[call[1] for call in api.calls if call[0]=='PUT']
            self.assertEqual(writes,['/courses/products/P/categories/C1'])
            state=json.loads(Path(root,'delivery-state.json').read_text())
            self.assertEqual(state['status'],'NEEDS_RECONCILIATION')
            self.assertEqual(state['completed'],[{'kind':'category','id':'C1'}])

    def test_uncertain_put_preserves_intent_and_never_retries(self):
        with tempfile.TemporaryDirectory() as root:
            api=Api(root);api.fail_put=True
            with self.assertRaises(TimeoutError):outline.run_outline(plan(),root,capability=capability(),transport=api)
            state=json.loads(Path(root,'delivery-state.json').read_text())
            self.assertEqual((state['status'],state['current_step_status']),('NEEDS_RECONCILIATION','INTENT_RECORDED'))
            calls=len(api.calls)
            with self.assertRaises(Stop):outline.run_outline(plan(),root,capability=capability(),transport=api)
            self.assertEqual(len(api.calls),calls)

    def test_unknown_sibling_loss_and_ignored_metadata_clear_are_not_success(self):
        for mode in ('sibling','metadata'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                api=Api(root)
                data=plan()
                if mode=='sibling':api.lose_sibling=True
                else:
                    api.retain_metadata=True
                    data['category_changes']=[]
                    data['lesson_changes'][0]['changes']={'metaData':{}}
                with self.assertRaisesRegex(Stop,'did not persist'):
                    outline.run_outline(data,root,capability=capability(),transport=api)
                self.assertEqual(json.loads(Path(root,'delivery-state.json').read_text())['status'],'NEEDS_RECONCILIATION')

    def test_replay_must_bind_each_nested_target_not_only_object_counts(self):
        with tempfile.TemporaryDirectory() as root:
            api=Api(root)
            outline.run_outline(plan(),root,capability=capability(),transport=api)
            path=Path(root,'delivery-state.json');state=json.loads(path.read_text())
            next(obj for obj in state['objects'] if obj['kind']=='lesson')['id']='FOREIGN'
            path.write_text(json.dumps(state));calls=len(api.calls)
            with self.assertRaisesRegex(Stop,'identities differ'):
                outline.run_outline(plan(),root,capability=capability(),transport=api)
            self.assertEqual(len(api.calls),calls)

    def test_invalid_or_access_changing_requests_fail_before_network(self):
        bad = []
        for value in ({'visibility':'published'},{'parentCategory':[]},{'lockedBy':{}},
                      {'metadata':{'unknown':'days'}},{'title':''},{'sequenceNo':True}):
            data=plan();data['category_changes'][0]['changes']=value;bad.append(data)
        data=plan();data['publish']=True;bad.append(data)
        data=plan();data['options']={};bad.append(data)
        data=plan();data['lesson_changes'][0].pop('expected_updated_at');bad.append(data)
        data=plan();data['lesson_changes']*=2;bad.append(data)
        for data in bad:
            with self.subTest(data=data), tempfile.TemporaryDirectory() as root:
                api=Api(root)
                with self.assertRaises(Stop):outline.run_outline(data,root,capability=capability(),transport=api)
                self.assertEqual(api.calls,[])

    def test_hierarchy_rotation_detaches_child_before_parent_and_replays_without_calls(self):
        with tempfile.TemporaryDirectory() as root:
            api=Api(root)
            api.rows['/courses/products/P/categories/C1']['parentCategory']=None
            api.rows['/courses/products/P/categories/C2']['parentCategory']='C1'
            data={'location_id':'LOC','product_id':'P','category_changes':[
                {'category_id':'C1','expected_updated_at':'v1','changes':{'parentCategory':'C2'}},
                {'category_id':'C2','expected_updated_at':'v1','changes':{'parentCategory':None}}]}
            request=api.request
            def cycle_guard(method,path,**kwargs):
                if method=='PUT' and 'parentCategory' in kwargs.get('body',{}):
                    parents={key.rsplit('/',1)[1]:row.get('parentCategory') for key,row in api.rows.items()
                             if '/categories/' in key}
                    identity=path.rsplit('/',1)[1]
                    parents[identity]=kwargs['body']['parentCategory']
                    seen=set()
                    while identity is not None:
                        self.assertNotIn(identity,seen,'Native PUT would introduce a transient cycle')
                        seen.add(identity);identity=parents[identity]
                return request(method,path,**kwargs)
            api.request=cycle_guard
            result=outline.run_outline(data,root,capability=capability(),transport=api)
            self.assertEqual([path for method,path,_ in api.calls if method=='PUT'],[
                '/courses/products/P/categories/C2','/courses/products/P/categories/C1'])
            self.assertEqual(result['completed'],[{'kind':'category','id':'C1'},{'kind':'category','id':'C2'}])
            count=len(api.calls)
            outline.run_outline(data,root,capability=capability(),transport=api)
            self.assertEqual(len(api.calls),count)

    def test_invalid_access_dependencies_stop_before_journal_or_put(self):
        for change in ({'parentCategory':'C2'},{'lockedBy':'L1'},{'metadata':{'dripUnit':'days'}}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as root:
                api=Api(root);data=plan();data['category_changes'][0]['changes']=change
                with self.assertRaises(Stop):
                    outline.run_outline(data,root,capability=capability(),transport=api)
                self.assertTrue(api.calls)  # Supported schemas need actual GET inventory.
                self.assertFalse(any(method=='PUT' for method,_,_ in api.calls))
                self.assertFalse(Path(root,'delivery-state.json').exists())

    def test_final_hierarchy_cycle_refuses_before_any_write(self):
        with tempfile.TemporaryDirectory() as root:
            api=Api(root)
            for identity in ('C1','C2'):
                api.rows['/courses/products/P/categories/'+identity]['parentCategory']=None
            data={'location_id':'LOC','product_id':'P','category_changes':[
                {'category_id':'C1','expected_updated_at':'v1','changes':{'parentCategory':'C2'}},
                {'category_id':'C2','expected_updated_at':'v1','changes':{'parentCategory':'C1'}}]}
            with self.assertRaisesRegex(Stop,'hierarchy contains a cycle'):
                outline.run_outline(data,root,capability=capability(),transport=api)
            self.assertFalse(any(method=='PUT' for method,_,_ in api.calls))
            self.assertFalse(Path(root,'delivery-state.json').exists())

    def test_lesson_move_inventories_destination_ancestors_and_keeps_both_parent_receipts(self):
        for cycle in (False, True):
            with self.subTest(cycle=cycle), tempfile.TemporaryDirectory() as root:
                api=Api(root)
                api.rows['/courses/products/P/categories/C1']['parentCategory']='C2' if cycle else None
                api.rows['/courses/products/P/categories/C2']['parentCategory']='C1'
                data={'location_id':'LOC','product_id':'P','lesson_changes':[
                    {'lesson_id':'L1','category_id':'C1','expected_updated_at':'v1',
                     'changes':{'categoryId':'C2'}}]}
                if cycle:
                    with self.assertRaisesRegex(Stop,'hierarchy contains a cycle'):
                        outline.run_outline(data,root,capability=capability(),transport=api)
                    self.assertFalse(any(method=='PUT' for method,_,_ in api.calls))
                else:
                    result=outline.run_outline(data,root,capability=capability(),transport=api)
                    self.assertEqual(api.rows['/courses/products/P/lessons/L1']['categoryId'],'C2')
                    self.assertEqual({obj['id'] for obj in result['objects'] if obj['kind']=='category'}, {'C1','C2'})

    def test_draft_drip_edit_preserves_metadata_and_published_unlock_identity(self):
        with tempfile.TemporaryDirectory() as root:
            api=Api(root)
            api.rows['/courses/products/P/categories/C1']['metadata']={'dripUnit':'days','dripDate':None}
            api.rows['/courses/products/P/categories/C2']['visibility']='published'
            api.rows['/courses/products/P/lessons/L2']['visibility']='published'
            data={'location_id':'LOC','product_id':'P','category_changes':[
                {'category_id':'C1','expected_updated_at':'v1','changes':{
                    'dripDays':3,'metadata':{'dripUnit':'hours'},'lockedBy':'L2'}}]}
            result=outline.run_outline(data,root,capability=capability(),transport=api)
            writes=[body for method,_,body in api.calls if method=='PUT']
            self.assertEqual(writes,[{'dripDays':3,'metadata':{'dripUnit':'hours','dripDate':None},'lockedBy':'L2'}])
            self.assertEqual(result['status'],'NEEDS_VERIFICATION')
            self.assertEqual(api.rows['/courses/products/P/categories/C1']['visibility'],'draft')
            self.assertEqual(api.rows['/courses/products/P/categories/C2']['visibility'],'published')

    def test_quiz_transition_requires_its_real_content_operation(self):
        with tempfile.TemporaryDirectory() as root:
            api=Api(root);data=plan();data['lesson_changes'][0]['changes']={'contentType':'quiz'}
            with self.assertRaisesRegex(Stop,'dedicated content operation'):
                outline.run_outline(data,root,capability=capability(),transport=api)
            self.assertFalse(any(call[0]=='PUT' for call in api.calls))

    def test_check_mode_validates_without_constructing_a_transport(self):
        route={'operation':'courses.lessons','location_id':'LOC','version':'v3','lane':'public_api'}
        data={**plan(),'api_capability':capability()}
        result=outline.validate_api_inputs('courses.lessons',data,route)
        self.assertEqual(result['product_id'],'P')
        for mismatch in ({'version':'v2'},{'operation':'courses.update'},{'location_id':'FOREIGN'}):
            with self.subTest(mismatch=mismatch), self.assertRaises(Stop):
                outline.validate_api_inputs('courses.lessons',data,{**route,**mismatch})


if __name__=='__main__':unittest.main()
