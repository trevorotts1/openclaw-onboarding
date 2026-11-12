"""Individual result media binds category, owner and saved proof."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import MagicMock,patch
from playwright_recipes import quiz_individual_media as media, quiz_results
import recipe_cli
import skill6_playwright as runner

def value():
    return {'category':'Leadership','expected':{'type':'image','url':'https://example.com/old.png','placement':'Top'},
            'expected_target':{'type':'video','url':'https://example.com/old.mp4','placement':'Top'},
            'changes':{'type':'video','url':'https://example.com/new.mp4','placement':'Right center'}}

class IndividualMediaTests(unittest.TestCase):
    def test_public_compile_and_bound_schema(self):
        config={'individual_category_media':value()}
        data={'location_id':'LOC','location_name':'Fixture',
              'start_url':'https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ',
              'configuration':{'result_page':config}}
        job=runner.validate_job(recipe_cli.compile_recipe('quizzes.configure',data),Path('.'))
        self.assertEqual(job['steps'][0]['result_page'],config)
        self.assertEqual(len(quiz_results.configuration_hash(job['steps'][0])),64)
        for change in ('target','url','placement','mixed'):
            bad=deepcopy(config)
            if change=='target':bad['individual_category_media'].pop('expected_target')
            elif change=='url':bad['individual_category_media']['changes']['url']='http://example.com/video'
            elif change=='placement':bad['individual_category_media']['changes']['placement']='Invented'
            else:bad['changes']={'business_name':'unexpected'}
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                quiz_results.validate({'result_page':bad})

    def test_type_placement_url_write_preserves_content(self):
        plan=value();state=deepcopy(plan['expected']);markup='<p>Protected</p>'
        panel=MagicMock();kind,card,source=MagicMock(),MagicMock(),MagicMock()
        for node in (kind,card,source):node.count.return_value=1;node.is_visible.return_value=True;node.is_enabled.return_value=True
        source.get_attribute.return_value=None
        panel.locator.side_effect=lambda selector:source if selector.startswith('#bgImage') else kind
        panel.get_by_text.return_value.locator.return_value=card
        def click(node):
            if node is kind:state.update(plan['expected_target'])
            elif node is card:state['placement']=plan['changes']['placement']
        def fill(node,text):state['url']=text
        with patch.object(media,'_read',side_effect=lambda panel:(deepcopy(state),markup)), \
                patch.object(media,'click',side_effect=click),patch.object(media,'fill',side_effect=fill), \
                patch.object(media,'wait_until',side_effect=lambda predicate,message:self.assertTrue(predicate())):
            media._write(panel,plan,plan['expected'],markup)
        self.assertEqual(state,plan['changes'])

if __name__=='__main__':unittest.main()
