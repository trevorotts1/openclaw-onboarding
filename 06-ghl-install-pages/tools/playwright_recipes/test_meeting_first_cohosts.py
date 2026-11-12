"""First assignment binds positive NEW state, one Create, and native replay."""
from copy import deepcopy
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch
import recipe_cli
import skill6_playwright as runner
first=importlib.import_module('playwright_recipes.meeting_first_cohosts')


def inputs():
    return {'location_id':'loc','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/loc/dashboard',
        'name':'Approved room','slug':'approved-room','waiting_room':True,'guest_users':False,
        'open_room':False,'allow_creation':True,'cohosts':{'expected':[],
            'desired':[{'name':'Fixture Person','email':'person@example.invalid'}],
            'access_change_acknowledged':True}}


def receipt(data):
    return {'status':'COHOSTS_CREATED_AND_REOPENED','location_id':data['location_id'],
        'room_id':'https://rooms.example.invalid/'+data['slug'],
        'configuration_sha256':first.configuration_hash(data),'cohost_count':1,'addition_count':1,
        'removal_count':0,'independent_readback':'VERIFIED','meeting_started':False,
        'functional_verified':False,'notification_behavior_verified':False}


def compiled():
    data=inputs();common={key:data.pop(key) for key in ('location_id','location_name','start_url')}
    return runner.validate_job(recipe_cli.compile_recipe('meetings.setup',{**common,'meeting':data}),Path('.'))


class FirstRoomCohosts(unittest.TestCase):
    def test_setup_only_compiles_with_explicit_new_room_and_scoped_access(self):
        job=compiled();self.assertEqual(job['steps'][0]['action'],'meeting_cohosts')
        for change in ('expected','identity','ack','desired','allow'):
            value=inputs()
            if change=='expected':value['cohosts']['expected']=deepcopy(value['cohosts']['desired'])
            elif change=='identity':value['expected_room_id']='https://rooms.example.invalid/approved-room'
            elif change=='ack':value['cohosts']['access_change_acknowledged']=False
            elif change=='desired':value['cohosts']['desired']=[]
            else:value['allow_creation']=False
            with self.subTest(change=change),self.assertRaises(runner.Stop):first.validate_inputs(value)
        data=inputs();common={key:data.pop(key) for key in ('location_id','location_name','start_url')}
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('meetings.update',{**common,'meeting':data})

    def test_saved_empty_editor_is_never_accepted_as_positive_new_form(self):
        page=MagicMock();page.url='https://app.convertandflow.com/v2/location/loc/meetings/personal-room/edit'
        with self.assertRaisesRegex(runner.Stop,'positive new-room'):first._editor(page,inputs())
        page.get_by_role.assert_not_called()
        editor=MagicMock();editor.locator.return_value.count.return_value=1
        editor.locator.return_value.locator.return_value.count.return_value=0
        with self.assertRaisesRegex(runner.Stop,'zero rows remain unknown'):first.cohosts.read_roster(editor)

    def test_positive_new_form_accepts_zero_rows_with_exact_card_add_and_create_controls(self):
        page=MagicMock();page.url='https://app.convertandflow.com/v2/location/loc/meetings/personal-room/new'
        editor=MagicMock();page.get_by_role.return_value=editor
        editor.count.return_value=1;editor.is_visible.return_value=True
        fields=editor.get_by_role.return_value;fields.count.return_value=3
        card,submit,rows,add=[MagicMock() for _ in range(4)]
        editor.locator.side_effect=lambda selector:card if selector=='#create-room-members-card' else submit
        card.locator.side_effect=lambda selector:rows if selector=='.pr-members__rows > div' else add
        rows.count.return_value=0
        for node in (card,submit,add):node.count.return_value=1;node.is_visible.return_value=True
        with patch.object(first,'assert_tenant'):
            self.assertEqual(first._roster(page,inputs()),[])
        fields.nth.assert_not_called()

    def exercise(self,*,absent=True,candidate_missing=False,saved_drift=False):
        data=inputs();page=MagicMock();page.url=data['start_url']
        editor,fields,create,submit,candidate,dialog,search=[MagicMock() for _ in range(7)]
        values=[MagicMock(),MagicMock(),MagicMock()];fields.nth.side_effect=lambda i:values[i]
        values[0].input_value.return_value=data['name'];values[1].input_value.return_value=data['slug']
        entry=MagicMock();entry.get_by_role.return_value=create
        dialogs=MagicMock();dialogs.count.return_value=0
        page.get_by_role.side_effect=lambda role,**kwargs:dialogs if role=='dialog' else entry
        editor.locator.return_value=submit
        security={label:MagicMock() for label in first.meetings.SECURITY.values()}
        editor.get_by_role.side_effect=lambda role,name,exact:security[name]
        for key,label in first.meetings.SECURITY.items():security[label].get_attribute.return_value=str(data[key]).lower()
        for node in [editor,create,submit,candidate,*security.values()]:
            node.count.return_value=1;node.is_visible.return_value=True;node.is_enabled.return_value=True
        state={'roster':[],'creates':0}
        def click(node):
            if node is candidate:state['roster']=deepcopy(data['cohosts']['desired'])
            elif node is submit:state['creates']+=1
        observed={'status':'PRESENT','source':'native reader','location_id':'loc','name':data['name'],
            'slug':data['slug'],'room_id':receipt(data)['room_id'],'url':receipt(data)['room_id'],
            **{key:data[key] for key in first.meetings.SECURITY}}
        before={'status':'ABSENT' if absent else 'UNKNOWN','source':'native reader','location_id':'loc'}
        with patch.object(first,'assert_tenant'),patch.object(first,'click',side_effect=click),\
             patch.object(first,'fill'),patch.object(first,'_editor',return_value=(editor,fields)),\
             patch.object(first,'_roster',side_effect=lambda *args:deepcopy(state['roster'])),\
             patch.object(first.meetings,'read_room',side_effect=[before,observed]),\
             patch.object(first.meetings,'_security'),\
             patch.object(first.cohosts,'_open_directory',return_value=(dialog,search)),\
             patch.object(first.cohosts,'_find_candidate',side_effect=runner.Stop('candidate missing') if candidate_missing else None,return_value=candidate),\
             patch.object(first,'_verify_room',side_effect=runner.Stop('saved cohost drift') if saved_drift else None) as verify:
            try:result=first.configure(page,data)
            except runner.Stop as error:result=error
        values[2].input_value.assert_not_called()
        return result,state,verify

    def test_positive_new_stage_creates_once_then_independently_verifies_roster(self):
        result,state,verify=self.exercise()
        self.assertEqual(result['status'],'COHOSTS_CREATED_AND_REOPENED')
        self.assertEqual(state['creates'],1);verify.assert_called_once()
        self.assertFalse(result['notification_behavior_verified'])

    def test_unknown_room_or_missing_candidate_stops_before_create(self):
        for values in ({'absent':False},{'candidate_missing':True}):
            result,state,_=self.exercise(**values)
            self.assertIsInstance(result,runner.Stop);self.assertEqual(state['creates'],0)

    def test_saved_roster_drift_is_not_created_success(self):
        result,state,_=self.exercise(saved_drift=True)
        self.assertIsInstance(result,runner.Stop);self.assertEqual(state['creates'],1)

    def test_actual_runner_replay_verifies_created_roster_without_second_create(self):
        job=compiled();step=job['steps'][0];done=receipt(step['payload']);page=MagicMock()
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'),\
             patch.object(first,'configure',return_value=done) as create:
            result=runner.run_on_page(page,job,root)
            self.assertEqual(result['status'],'NEEDS_VERIFICATION')
            journal=Path(root,'state.json');saved=journal.read_bytes()
            with patch.object(first,'verify_completed',return_value=done) as verify:
                replay=runner.run_on_page(page,job,root)
                self.assertTrue(replay['replayed']);verify.assert_called_once_with(page,step['payload'],done)
                verify.side_effect=runner.Stop('created roster changed')
                with self.assertRaises(runner.Stop):runner.run_on_page(page,job,root)
            create.assert_called_once();self.assertEqual(journal.read_bytes(),saved)


if __name__=='__main__':unittest.main()
