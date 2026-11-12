"""Bounded native conditional-message markup and editor behavior."""
import unittest
from unittest.mock import Mock, call, patch
import condition_message_markup as markup
from skill6_playwright import Stop

class ParseTests(unittest.TestCase):
    def test_paragraphs_and_nested_marks(self):
        self.assertEqual(markup.parse('<p>One <strong>bold <em>both</em></strong></p><p>Two &amp; three</p>'),
            [[('One ', ()), ('bold ', ('strong',)), ('both', ('strong', 'em'))], [('Two & three', ())]])

    def test_captured_empty_style_is_preserved(self):
        self.assertEqual(markup.parse('<p style=""><strong>One</strong></p><p style=""><strong>Two</strong></p>'),
                         [[('One', ('strong',))], [('Two', ('strong',))]])

    def test_only_empty_paragraph_style_compares_equivalent(self):
        self.assertEqual(markup.comparable('<p style=""><strong>x</strong></p>'),
                         markup.comparable('<p><strong>x</strong></p>'))
        self.assertNotEqual(markup.comparable('<p><strong>x</strong></p>'),
                            markup.comparable('<p>x</p>'))
        with self.assertRaises(Stop):markup.comparable('<p style="color:red">x</p>')

    def test_captured_https_link_and_attribute_safety(self):
        link='<p><a target="_blank" rel="noopener noreferrer nofollow" href="https://example.com">Link</a></p>'
        self.assertEqual(markup.parse(link,with_links=True),[[('Link',(), 'https://example.com')]])
        for bad in (link.replace('https://example.com','javascript:alert(1)'),
                    link.replace('https://example.com','https://user:pw@example.com'),
                    link.replace('_blank','_self'),link.replace('nofollow','noreferrer')):
            with self.subTest(bad=bad),self.assertRaises(Stop):markup.parse(bad)

    def test_unsupported_or_unreproducible_shapes_stop(self):
        for html in ('<p><strong></strong>text</p>', '<p></p>', '<p x="1">x</p>', '<p style="color:red">x</p>', '<strong style="">x</strong>', '<p>x<br>y</p>',
                     '<p>x\ny</p>', '<p><strong>x</p></strong>', '<p><!-- hidden -->x</p>', '<p>&#65;</p>'):
            with self.subTest(html=html), self.assertRaises(Stop): markup.parse(html)

class WriteTests(unittest.TestCase):
    def test_native_toolbar_and_keyboard_for_two_paragraphs(self):
        modal, control = Mock(), Mock()
        buttons = {}
        for tag, (suffix, label) in markup.MARKS.items():
            button = Mock()
            button.count.return_value = 1
            button.is_visible.return_value = button.is_enabled.return_value = True
            button.get_attribute.side_effect = {'type':'button', 'aria-label':label, 'class':'toolbar_button'}.get
            buttons['#richTextEditor #toolbar_button--' + suffix] = button
        modal.locator.side_effect = buttons.__getitem__
        expected='<p>Hello <strong>bold</strong></p><p>Next</p>'
        control.inner_html.return_value = expected.replace('<p>', '<p style="">')
        with patch.object(markup, 'fill') as fill, patch.object(markup, 'click') as click:
            markup.write(modal, control, expected, lambda: None)
        fill.assert_called_once_with(control, '')
        self.assertEqual(control.press_sequentially.call_args_list, [call('Hello '), call('bold'), call('Next')])
        control.press.assert_called_once_with('Enter')
        self.assertEqual(click.call_args_list, [call(buttons['#richTextEditor #toolbar_button--bold'])]*2)

    def test_link_uses_native_selection_dialog_and_new_window(self):
        import form_conditions
        modal,control,frame=Mock(),Mock(),Mock();buttons={}
        for tag,(suffix,label) in markup.MARKS.items():
            node=Mock();node.count.return_value=1;node.is_visible.return_value=node.is_enabled.return_value=True
            node.get_attribute.side_effect={'type':'button','aria-label':label,'class':'toolbar_button'}.get
            buttons['#richTextEditor #toolbar_button--'+suffix]=node
        rte,linkbutton,dialog,form,href,save=[Mock() for _ in range(6)]
        linkbutton.count.return_value=dialog.count.return_value=form.count.return_value=href.count.return_value=save.count.return_value=1
        linkbutton.is_visible.return_value=linkbutton.is_enabled.return_value=True
        dialog.is_visible.side_effect=[True,False]
        form.is_visible.return_value=save.is_visible.return_value=save.is_enabled.return_value=True
        href.get_attribute.return_value='text';rte.get_by_role.return_value=linkbutton
        buttons['#richTextEditor']=rte;modal.locator.side_effect=buttons.__getitem__
        modal.get_by_role.return_value=dialog
        dialog.locator.side_effect={'#link-embed_form':form,'#editor_link-embed-href':href,
                                    '#editor__link-embed-footer-btn-positive-action':save}.__getitem__
        html='<p><a target="_blank" rel="noopener noreferrer nofollow" href="https://example.com">Link</a></p>'
        control.inner_html.return_value=html
        with patch.object(markup,'fill') as fill,patch.object(markup,'click') as click,patch.object(form_conditions,'_choose') as choose:
            markup.write(modal,control,html,lambda:None,frame=frame)
        self.assertEqual(control.press.call_args_list,[call('Shift+ArrowLeft')]*4+[call('ArrowRight')])
        self.assertIn(call(href,'https://example.com'),fill.call_args_list)
        choose.assert_called_once_with(frame,'#editor_link-embed-target','New window')
        self.assertEqual(click.call_args_list,[call(linkbutton),call(save)])

    def test_unknown_toolbar_stops_before_edit(self):
        modal, control = Mock(), Mock()
        modal.locator.return_value.count.return_value = 0
        with patch.object(markup, 'fill') as fill, self.assertRaises(Stop):
            markup.write(modal, control, '<p>text</p>', lambda: None)
        fill.assert_not_called()
