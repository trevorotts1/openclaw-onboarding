import unittest

from playwright_recipes.recipe_cli import compile_recipe
from playwright_recipes.skill6_playwright import Stop

BASE = {'location_id': 'loc', 'location_name': 'Location', 'start_url': 'https://example.com'}
PLACE = {'section_id': 'section', 'row_id': 'row', 'column_id': 'column'}


class HybridFrontdoorTests(unittest.TestCase):
  def test_layout_boundary_and_refusal(self):
      for count in range(1, 7):
          steps = compile_recipe('pages.layout', {**BASE, 'layout': {'section_id': 'section', 'columns': count}})['steps']
          assert steps[0]['layout']['columns'] == count
      for count in (0, 7, True):
          with self.assertRaises(Stop):
              compile_recipe('pages.layout', {**BASE, 'layout': {'section_id': 'section', 'columns': count}})


  def test_native_order_and_placement_preserved(self):
      index = {'section_id': 'section', 'row_id': 'row', 'column_index': 1, 'expected_columns': 2}
      result = compile_recipe('checkout.wrap_native', {**BASE, 'before_file': 'before.html', 'before_marker': 'before',
          'before_placement': PLACE, 'checkout': {'mode': 'One-step', 'placement': index},
          'after_file': 'after.html', 'after_marker': 'after', 'after_placement': PLACE, 'seo': {}})
      assert [step['action'] for step in result['steps']] == ['html', 'checkout', 'html', 'seo']
      assert [step['placement'] for step in result['steps'][:3]] == [PLACE, index, PLACE]


  def test_placement_refusal_and_policy(self):
      with self.assertRaises(Stop):
          compile_recipe('pages.install_code', {**BASE, 'file': 'x', 'marker': 'x', 'seo': {},
              'placement': {'section_id': 'section', 'row_id': 'row', 'column_index': 1}})
      with self.assertRaises(Stop):
          compile_recipe('checkout.wrap_native', {**BASE, 'before_file': 'x', 'before_marker': 'x',
              'checkout': {'processor': 'external'}, 'seo': {}})
      with self.assertRaises(Stop):
          compile_recipe('pages.install_embed', {**BASE, 'file': 'x', 'marker': 'x', 'seo': {},
              'embed_receipt': {'source': 'install external checkout', 'status': 'PASS', 'location_id': 'loc'}})
