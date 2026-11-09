"""Independent corruption and special-content boundaries for existing outlines."""
import json
from pathlib import Path
import tempfile
import unittest

import course_outline as outline
import test_course_outline as fixtures
from skill6_playwright import Stop


class CourseOutlineQcTests(unittest.TestCase):
    def test_replay_requires_complete_ordered_target_ledger_and_pending_functional_proof(self):
        corruptions = [
            lambda state: state.update(completed=[]),
            lambda state: state['completed'].pop(),
            lambda state: state['completed'].reverse(),
            lambda state: state['completed'].append(state['completed'][0]),
            lambda state: state['completed'][0].update(id='FOREIGN'),
            lambda state: state.update(functional_verified=True),
            lambda state: state.pop('functional_verified'),
        ]
        for index, corrupt in enumerate(corruptions):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as root:
                api = fixtures.Api(root)
                outline.run_outline(fixtures.plan(), root, capability=fixtures.capability(), transport=api)
                path = Path(root, 'delivery-state.json')
                state = json.loads(path.read_text())
                corrupt(state)
                damaged = json.dumps(state)
                path.write_text(damaged)
                before = len(api.calls)
                with self.assertRaises(Stop):
                    outline.run_outline(fixtures.plan(), root, capability=fixtures.capability(), transport=api)
                self.assertEqual(len(api.calls), before)
                self.assertEqual(path.read_text(), damaged)

    def test_existing_special_content_cannot_become_a_video_with_the_old_special_content_id(self):
        for special in ('quiz', 'assignment'):
            with self.subTest(special=special), tempfile.TemporaryDirectory() as root:
                data = fixtures.plan()
                data['lesson_changes'][0]['changes'] = {'contentType': 'video'}
                api = fixtures.Api(root)
                current = api.rows['/courses/products/P/lessons/L2']
                current.update(contentType=special, contentId='SPECIAL_CONTENT_ID')
                with self.assertRaises(Stop):
                    outline.run_outline(data, root, capability=fixtures.capability(), transport=api)
                self.assertFalse(any(method == 'PUT' for method, _, _ in api.calls))
                self.assertFalse(Path(root, 'delivery-state.json').exists())


if __name__ == '__main__':
    unittest.main()
