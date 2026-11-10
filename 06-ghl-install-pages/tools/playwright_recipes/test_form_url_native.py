"""Captured URL domain control behavior through the shared widget action."""
from copy import deepcopy
from unittest import TestCase

import recipe_cli
from test_form_widget_families import inputs, properties
from playwright_recipes import form_widget_families as native
from playwright_recipes.skill6_playwright import Stop


class Node:
    def __init__(self,panel,kind,value=None):self.panel=panel;self.kind=kind;self.value=value
    def count(self):
        if self.kind=='chips':return len(self.panel.domains) if self.panel.mode!='allow_all' else 0
        if self.kind in ('editor','chip','remove') and self.panel.mode=='allow_all':return 0
        if self.kind in ('chip','remove'):return int(self.value<len(self.panel.domains))
        return 1
    def wait_for(self,**kw):
        if not self.is_visible():raise AssertionError("unavailable captured owner")
    def is_visible(self):return bool(self.count())
    def get_attribute(self,key):
        if key=='type' and self.kind=='radio':return 'radio'
        if key=='aria-label' and self.kind=='remove':return 'Remove '+self.panel.domains[self.value]
    def is_checked(self):return self.panel.mode==self.value
    def input_value(self):return self.panel.draft
    def inner_text(self):return self.panel.domains[self.value]
    def fill(self,value,**kw):self.panel.draft=value
    def press(self,key,**kw):
        if key=='Enter':self.panel.domains.append(self.panel.draft);self.panel.draft=''
    def click(self,**kw):
        self.panel.clicks.append((self.kind,self.value))
        if self.kind=='owner':self.panel.mode=self.value
        elif self.kind=='remove':self.panel.domains.pop(self.value)
    def locator(self,selector):
        if self.kind=='owner':
            expected='input[name="url-domain-mode"][value="'+self.value+'"]'
            if selector!=expected:raise AssertionError(selector)
            return Node(self.panel,'radio',self.value)
        if self.kind=='chip':
            if selector!='button#url-domain-remove-'+str(self.value):raise AssertionError(selector)
            return Node(self.panel,'remove',self.value)
        raise AssertionError((self.kind,selector))


class Panel(Node):
    def __init__(self,mode='allow_all',domains=None):
        self.panel=self;self.kind='panel';self.mode=mode;self.domains=list(domains or []);self.draft='';self.clicks=[]
    def locator(self,selector):
        if selector=='#form_custom_sidebar':return self
        if selector.startswith('label[data-testid="url-mode-'):return Node(self,'owner',selector[len('label[data-testid="url-mode-'):-2])
        if selector=='[data-testid^="url-domain-chip-"]':return Node(self,'chips')
        if selector.startswith('[data-testid="url-domain-chip-'):return Node(self,'chip',int(selector[len('[data-testid="url-domain-chip-'):-2]))
        if selector=='input#url-domain-input':return Node(self,'editor')
        raise AssertionError(selector)


class FormURL(TestCase):
    def test_url_compiles_and_existing_global_identity_is_immutable(self):
        source=inputs('url');spec=recipe_cli.compile_recipe('forms.configure',source)['steps'][0]
        self.assertEqual(spec['action'],native.ACTION)
        desired=properties('url');desired.update(domain_mode='allow_only',domains=['example.com'])
        native._properties('url',desired)
        source['widget_fields']['expected_fields']=[{'kind':'url','index':1,'properties':deepcopy(desired)}]
        source['widget_fields']['fields']=[{'kind':'url','index':1,'desired':deepcopy(desired)}]
        for key,value in [('unique_key','contact.other'),('custom_field_name','Other')]:
            bad=deepcopy(source);bad['widget_fields']['fields'][0]['desired'][key]=value
            with self.assertRaises(Stop):recipe_cli.compile_recipe('forms.configure',bad)

    def test_url_unmeasured_hidden_and_invalid_domain_contracts_refuse(self):
        for change in [dict(hidden=True,hidden_value='unmeasured'),dict(domain_mode='allow_only'),
                       dict(domain_mode='block',domains=['https://example.com']),
                       dict(domain_mode='block',domains=['example.com','example.com']),
                       dict(domains=['example.com'])]:
            value=properties('url');value.update(change)
            with self.subTest(change=change),self.assertRaises(Stop):native._properties('url',value)

    def test_domain_replacement_clicks_visible_owners_and_preserves_exact_order(self):
        panel=Panel('allow_only',['old.example.com']);before={'domain_mode':'allow_only','domains':['old.example.com']}
        desired={'domain_mode':'block','domains':['example.com','second.example.com']}
        native._write_url_options(panel,before,desired)
        self.assertEqual(native._url_options(panel),desired)
        self.assertEqual(panel.clicks,[('owner','block'),('remove',0)])
        native._write_url_options(panel,desired,{'domain_mode':'allow_all','domains':[]})
        self.assertEqual(native._url_options(panel),{'domain_mode':'allow_all','domains':[]})
        self.assertEqual(panel.clicks[-1],('owner','allow_all'))

    def test_changed_domain_preflight_and_draft_stop_before_mutation(self):
        panel=Panel('block',['example.com'])
        with self.assertRaises(Stop):native._write_url_options(panel,{'domain_mode':'block','domains':['stale.com']},
                                                             {'domain_mode':'allow_all','domains':[]})
        self.assertEqual(panel.clicks,[])
        panel.draft='uncommitted.com'
        with self.assertRaises(Stop):native._url_options(panel)

    def test_url_read_is_saved_in_shared_receipt(self):
        from test_form_widget_families import receipt
        spec=recipe_cli.compile_recipe('forms.configure',inputs('url'))['steps'][0]
        self.assertEqual(native.validate_receipt(receipt(spec),spec)['fields'][0]['kind'],'url')
