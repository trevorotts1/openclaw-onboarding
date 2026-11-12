"""Captured Standard/Bubble Single Choice styling preserves routing and scores."""
from copy import deepcopy
import unittest
from unittest.mock import MagicMock,patch
from playwright_recipes import quiz_answer_jumps as jumps
from test_quiz_answer_jumps import config,snapshot
from skill6_playwright import Stop


def presentation():
    value=config()
    question=value['questions'][0]
    question['presentation']={'expected_style':'Standard','style':'Bubble'}
    for option in question['options']:option['destination']=option['expected_destination']
    return value


class ChoicePresentationTests(unittest.TestCase):
    def test_exact_captured_style_request_and_foreign_styles_refuse(self):
        value=presentation();self.assertEqual(jumps.validate(value),value)
        for style in ('bubble','Rounded','',None,True):
            changed=deepcopy(value);changed['questions'][0]['presentation']['style']=style
            with self.subTest(style=style),self.assertRaises(Stop):jumps.validate(changed)
        before=snapshot();before['style']='Standard'
        after=jumps.desired(value,[before])[0]
        self.assertEqual(after['style'],'Bubble')
        self.assertEqual(after['options'],before['options']);self.assertEqual(after['spread_to_columns'],before['spread_to_columns'])

    def test_exact_two_style_card_owners_and_one_active_are_required(self):
        panel=MagicMock();panel.locator.return_value.count.return_value=2
        images={};cards={}
        for name in ('Standard','Bubble'):
            image,card=MagicMock(),MagicMock()
            image.count.return_value=card.count.return_value=1
            image.is_visible.return_value=card.is_visible.return_value=True
            image.locator.return_value=card
            card.get_attribute.return_value='style-option'+(' style-option-active' if name=='Standard' else '')
            images[name+' radio style']=image;cards[name]=card
        panel.get_by_role.side_effect=lambda role,name,exact:images[name]
        observed,current=jumps._style_controls(panel,{})
        self.assertEqual(current,'Standard');self.assertEqual(observed,cards)
        cards['Bubble'].get_attribute.return_value='style-option style-option-active'
        with self.assertRaisesRegex(Stop,'ambiguous'):jumps._style_controls(panel,{})

    def test_owned_style_write_changes_only_style_and_protected_drift_stops(self):
        for drift in (False,True):
            value=presentation();state=snapshot();state['style']='Standard';before=deepcopy(state)
            frame,panel,row=MagicMock(),MagicMock(),MagicMock();cards={name:MagicMock() for name in ('Standard','Bubble')}
            for card in cards.values():card.is_enabled.return_value=True
            def select():
                state['style']='Bubble'
                if drift:state['options'][0]['score']='99'
            cards['Bubble'].click.side_effect=select
            switches=[]
            for index in range(2):
                switch=MagicMock();switch.get_attribute.side_effect=lambda key,index=index:'true' if state['options'][index]['destination'] is not None else 'false';switches.append(switch)
            with patch.object(jumps,'read',side_effect=lambda *args:[deepcopy(state)]), \
                    patch.object(jumps,'_open',return_value=panel), \
                    patch.object(jumps,'_selected',side_effect=lambda *args:deepcopy(state)), \
                    patch.object(jumps,'_style_controls',side_effect=lambda *args:(cards,state['style'])), \
                    patch.object(jumps,'_row',side_effect=lambda panel,index,question:(row,switches[index])), \
                    patch.object(jumps,'click',side_effect=lambda node:node.click()), \
                    patch.object(jumps,'wait_until',side_effect=lambda predicate,message:predicate() or (_ for _ in ()).throw(Stop(message))), \
                    patch.object(jumps.native,'_close_properties'):
                if drift:
                    with self.assertRaisesRegex(Stop,'protected answer state'):jumps.write(frame,value,[before])
                else:
                    jumps.write(frame,value,[before]);self.assertEqual(state,jumps.desired(value,[before])[0])
                cards['Bubble'].click.assert_called_once()

    def test_incorrect_prior_style_refuses_and_saved_style_drift_is_not_completion(self):
        before=snapshot();before['style']='Bubble'
        with patch.object(jumps,'read',return_value=[before]),self.assertRaisesRegex(Stop,'prior presentation'):
            jumps.preflight(MagicMock(),presentation())
        before['style']='Standard';before['spread_to_columns']=True
        with patch.object(jumps,'read',return_value=[before]),self.assertRaisesRegex(Stop,'captured column inventory'):
            jumps.preflight(MagicMock(),presentation())
        before['spread_to_columns']=False
        with patch.object(jumps,'read',return_value=[before]),self.assertRaisesRegex(Stop,'did not persist'):
            jumps.verify(MagicMock(),presentation(),[before])


if __name__=='__main__':unittest.main()
