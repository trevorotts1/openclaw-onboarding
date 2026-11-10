from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import form_notifications as n
from recipe_cli import compile_recipe
from skill6_playwright import Stop, validate_job


CONTEXT = {'location_id':'fixture','location_name':'Fixture',
           'start_url':'https://app.convertandflow.com/v2/location/fixture/form-builder-v2/form1'}
CONFIG = {'enabled':True, 'subject':'Authored subject', 'reply_to':'reply@example.com',
          'sender_name':'Fixture sender', 'attach_pdf':True,
          'recipients':['one@example.com','two@example.com'], 'expected_recipients':['old@example.com']}


class Control:
    def __init__(self, card=None, field=None, *, label='', count=1, click=None, outer=False):
        self.card, self.field, self.label, self.n, self.on_click, self.outer = card, field, label, count, click, outer
    def count(self): return self.n
    def is_visible(self): return self.n == 1
    def is_enabled(self): return True
    def click(self):
        if self.on_click: self.on_click()
    def fill(self, value): self.card.data[self.field] = value
    def input_value(self): return self.card.data[self.field]
    def get_attribute(self, name):
        if self.field == 'name' and name == 'contenteditable':return None
        return str(self.card.data['enabled']).lower()
    def evaluate(self, script): return self.outer if 'closest' in script else self.label
    def locator(self, value): return Control(count=0)
    def set_checked(self, value): self.card.data[self.field] = value
    def is_checked(self): return self.card.data[self.field]
    def press(self, key):
        if key != 'Enter': raise AssertionError(key)
        self.card.data['recipients'].append(self.card.data.pop('pending_email'))


class Fields:
    def __init__(self, card): self.card = card
    def count(self): return 2
    def nth(self, index):
        field, label = [('reply_to','Reply-to-email'),('sender_name','Sender name')][index]
        return Control(self.card,field,label=label)


class Chips:
    def __init__(self, card): self.card = card
    def count(self): return len(self.card.data['recipients'])
    @property
    def first(self): return Control(click=lambda:self.card.data['recipients'].pop(0))
    def evaluate_all(self, script):
        return list(self.card.data['recipients']) if 'parentElement' in script else ['']*self.count()


class Card:
    def __init__(self, native, key): self.native, self.key = native, key
    @property
    def data(self): return self.native.current[self.key]
    def count(self): return 1
    def get_by_role(self, role, name=None, exact=True):
        if role == 'switch':
            return Control(self,click=lambda:self.data.update(enabled=not self.data['enabled']))
        if role == 'checkbox': return Control(self,'attach_pdf')
        if role == 'button' and name == 'Save':
            return Control(click=lambda:self.native.actions.append('inner:'+self.key))
        raise AssertionError((role,name))
    def get_by_placeholder(self, value, exact=True):
        if value != n.CARDS[self.key][1]: raise AssertionError(value)
        return Control(self,'subject')
    def locator(self, value):
        if value == '.n-input__input input': return Fields(self)
        if value == 'button[id="remove-email"]': return Chips(self)
        if value == 'input#email-to-input': return Control(self,'pending_email')
        raise AssertionError(value)


class Cards:
    def __init__(self, native): self.native = native
    def count(self): return 2
    def filter(self, *, has):
        key = next(key for key,(title,_) in n.CARDS.items() if title == has.label)
        return Card(self.native,key)


class Saves:
    def __init__(self, native): self.native = native
    def all(self):
        def save():
            self.native.actions.append('outer')
            if self.native.persist: self.native.saved = deepcopy(self.native.current)
        return [Control(outer=True,click=save),Control(outer=False),Control(outer=False)]


class Frame:
    def __init__(self, native): self.native = native
    def get_by_role(self, role, name=None, exact=True):
        if role == 'textbox':
            card = type('Name',(),{'data':{'name':'Fixture form'}})()
            return Control(card,'name')
        if role == 'dialog':
            return type('Dialog',(),{'get_by_role':lambda *a,**k:Control(count=0)})()
        if role == 'button' and name == 'Save': return Saves(self.native)
        if role == 'tab': return Control(click=lambda:self.native.actions.append('tab:'+name))
        raise AssertionError((role,name))
    def get_by_text(self, text, exact=True): return Control(label=text)
    def locator(self, value):
        if value == '.hl-card-content': return Cards(self.native)
        raise AssertionError(value)


class Native:
    def __init__(self, persist=True):
        common = {'enabled':False,'subject':'Old','reply_to':'oldreply@example.com',
                  'sender_name':'Old sender','attach_pdf':False}
        self.current = {'email_notification':{**common,'recipients':['old@example.com']},'auto_responder':dict(common)}
        self.saved, self.actions, self.persist = deepcopy(self.current), [], persist
        self.url = CONTEXT['start_url']
        self.frame = Frame(self)
    def reopen(self,*args):
        self.actions.append('reopen')
        self.current = deepcopy(self.saved)


class NotificationTests(unittest.TestCase):
    def plan(self): return {'id':'notification1','action':'form_notifications','_context':CONTEXT,'email_notification':deepcopy(CONFIG),'auto_responder':{'enabled':False}}
    def run_native(self, native, plan):
        def immediate(fn,*args,**kw):
            if not fn(): raise Stop('Fixture expectation failed')
        with patch.object(n,'assert_tenant'), patch.object(n,'form_builder',return_value=native.frame), \
             patch.object(n,'click',side_effect=lambda control:control.click()), \
             patch.object(n,'fill',side_effect=lambda control,value:control.fill(value)), \
             patch.object(n,'wait_until',side_effect=immediate), \
             patch.object(n,'reopen_editor',side_effect=native.reopen):
            return n.configure_notifications(native,plan)

    def test_authored_schema_compiles_with_canonical_context(self):
        job = validate_job(compile_recipe('forms.notifications',{**CONTEXT,'notifications':{'email_notification':deepcopy(CONFIG)}}),Path('.'))
        self.assertEqual(job['steps'][0]['_context'],CONTEXT)
        self.assertEqual(job['steps'][0]['action'],'form_notifications')

    def test_invalid_email_duplicate_unknown_body_and_false_strings_refused(self):
        changes = [{'reply_to':'not-an-email'},{'recipients':['one@example.com','one@example.com']},
                   {'body':'silently ignored?'},{'enabled':'false'},{'attach_pdf':'true'},
                   {'subject':'Injected\nHeader'}]
        for change in changes:
            plan = self.plan(); plan['email_notification'].update(change)
            with self.subTest(change=change), self.assertRaises(Stop): n.validate_notifications(plan)

    def test_disabled_card_cannot_silently_ignore_other_requested_settings(self):
        with self.assertRaises(Stop): n.validate_notifications({'auto_responder':{'enabled':False,'subject':'Ignored'}})

    def test_every_card_is_validated_before_any_browser_activity(self):
        plan = self.plan(); plan['auto_responder']={'enabled':True}
        native = Native()
        with self.assertRaises(Stop): self.run_native(native,plan)
        self.assertEqual(native.actions,[])

    def test_recipient_mismatch_stops_before_replacement_or_save(self):
        native, plan = Native(), self.plan()
        plan['email_notification']['expected_recipients']=['different@example.com']
        with self.assertRaises(Stop): self.run_native(native,plan)
        self.assertEqual(native.current['email_notification']['recipients'],['old@example.com'])
        self.assertFalse(any(x.startswith('inner:') or x=='outer' for x in native.actions))

    def test_full_settings_save_reopen_and_safe_receipt_without_sending(self):
        native, plan = Native(), self.plan()
        result = self.run_native(native,plan)
        self.assertEqual(native.saved['email_notification']['recipients'],CONFIG['recipients'])
        self.assertLess(native.actions.index('inner:email_notification'),native.actions.index('outer'))
        self.assertLess(native.actions.index('outer'),native.actions.index('reopen'))
        self.assertEqual(result['behavior_verification'],'REQUIRED')
        self.assertEqual(result['email_delivery'],'NOT_TESTED')
        self.assertFalse(result['form_submitted'])
        self.assertFalse(result['notifications_sent'])
        for raw in (*CONFIG['recipients'],CONFIG['reply_to'],CONFIG['subject'],CONFIG['sender_name']):
            self.assertNotIn(raw,str(result))

    def test_successful_save_click_without_persisted_change_fails(self):
        with self.assertRaises(Stop): self.run_native(Native(persist=False),self.plan())

    def test_auto_responder_has_authored_fields_but_no_recipient_replacement(self):
        native = Native()
        config = {k:v for k,v in CONFIG.items() if k not in ('recipients','expected_recipients')}
        result = self.run_native(native,{'_context':CONTEXT,'auto_responder':config})
        self.assertTrue(native.saved['auto_responder']['enabled'])
        self.assertEqual(native.saved['email_notification']['recipients'],['old@example.com'])
        self.assertEqual(result['recipient_count'],0)


if __name__ == '__main__': unittest.main()
