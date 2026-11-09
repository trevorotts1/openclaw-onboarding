"""Live inventory aliases must not become duplicate native query/label anchors."""
import unittest
from unittest.mock import patch

import field_placement
import skill6_playwright as runner
import test_extended_field_properties as fixtures


class FieldPropertyIdentityTests(unittest.TestCase):
    def test_ignored_authored_text_writes_refuse_before_save(self):
        edits = [
            {'field': 'Website', 'label': 'Caller label'},
            {'field': 'Website', 'placeholder': 'Caller placeholder'},
            {'field': 'Website', 'short_label': 'Caller short label'},
            {'field': 'Website', 'width_pct': 50},
            {'field': 'Website', 'hidden': True, 'hidden_value': 'Caller default'},
        ]
        def ignored_fill(node, value):
            # A native framework may accept fill() then retain its old model.
            node.frame.writes.append(('ignored', node.index, value))
        for edit in edits:
            frame = fixtures.Frame([fixtures.field('Website')])
            with self.subTest(edit=edit), patch.object(fixtures.Node, 'fill', ignored_fill):
                with self.assertRaises(runner.Stop):
                    fixtures.ExtendedFieldProperties().run_fields(frame, [edit])
                self.assertEqual((frame.saves, frame.reopens), (0, 0))

    def test_new_query_cannot_take_an_unrequested_fields_renamed_query(self):
        other=fixtures.field('Organization')
        other['values'][3]='shared_query'
        frame=fixtures.Frame([fixtures.field('Website'),other])
        # The native reader is tested separately against the captured wrappers.
        # Supply its actual full inventory to isolate the property edit planner.
        with patch.object(field_placement,'_inventory',return_value={
                'website':'text','shared_query':'text'}):
            with self.assertRaises(runner.Stop):
                fixtures.ExtendedFieldProperties().run_fields(frame,[{
                    'field':'Website','query_key':'shared_query'}])
        self.assertEqual((frame.writes,frame.saves),([],0))

    def test_new_placeholder_cannot_take_an_unrequested_fields_renamed_placeholder(self):
        other=fixtures.field('Organization')
        other['values'][1]='Existing client URL'
        frame=fixtures.Frame([fixtures.field('Website'),other])
        with self.assertRaises(runner.Stop):
            fixtures.ExtendedFieldProperties().run_fields(frame,[{
                'field':'Website','placeholder':'Existing client URL'}])
        self.assertEqual((frame.writes,frame.saves),([],0))


if __name__ == '__main__':unittest.main()
