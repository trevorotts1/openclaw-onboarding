"""WF12 / A16: the Skill 74 result envelope feeds the shared course-asset normalizer.

Offline: a temp PNG/MP4 on disk, no network, no key, no adapter dispatch. Proves that the
envelope the adapter already returns is enough to complete a course asset, that a URL is
never persistence, and that no model/price/prompt policy is re-decided here.
"""
import hashlib
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SHARED = os.path.join(REPO, "shared-utils", "ghl")
if SHARED not in sys.path:
    sys.path.insert(0, SHARED)

import course_assets as ca  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
MP4 = b"\x00\x00\x00\x18ftypisom" + b"M" * 64


class CourseSeam(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.addCleanup(self._t.cleanup)

    def _png(self):
        p = os.path.join(self.tmp, "a.png")
        with open(p, "wb") as fh:
            fh.write(PNG)
        return p

    def test_success_with_saved_paths_completes_from_real_bytes(self):
        path = self._png()
        m = ca.new_manifest("c1", "m1", "l1", "lesson_image", model_id="gpt-image", provider_task_id="T1")
        done = ca.completion_from_adapter_result({"state": "success", "saved_paths": [path], "task_id": "T1"}, m)
        self.assertEqual(done["generation_state"], "completed")
        self.assertEqual(done["sha256"], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(done["byte_size"], len(PNG))
        self.assertEqual(done["mime_type"], "image/png")
        self.assertEqual(done["model_id"], "gpt-image")
        self.assertEqual(done["provider_task_id"], "T1")

    def test_result_urls_alone_never_complete(self):
        m = ca.new_manifest("c1", "m1", "l1", "lesson_image")
        with self.assertRaises(ca.AssetError) as e:
            ca.completion_from_adapter_result(
                {"state": "success", "result_urls": ["https://tempfile.aiquickdraw.com/a.png"]}, m)
        self.assertEqual(e.exception.code, "no_persisted_bytes")

    def test_queued_running_and_validated_stay_incomplete(self):
        m = ca.new_manifest("c1", "m1", "l1", "lesson_video")
        for state, expected in (("queued", "running"), ("running", "running"), ("validated", "queued")):
            out = ca.completion_from_adapter_result({"state": state, "task_id": "T"}, m)
            self.assertEqual(out["generation_state"], expected, state)

    def test_skipped_and_fail_are_failures_for_the_course_seam(self):
        m = ca.new_manifest("c1", "m1", "l1", "lesson_image")
        self.assertEqual(ca.completion_from_adapter_result({"state": "skipped"}, m)["generation_state"], "failed")
        self.assertEqual(ca.completion_from_adapter_result({"state": "fail", "error": {"msg": "boom"}}, m)["generation_state"], "failed")

    def test_video_requires_the_callers_duration_and_never_an_invented_one(self):
        path = os.path.join(self.tmp, "a.mp4")
        with open(path, "wb") as fh:
            fh.write(MP4)
        m = ca.new_manifest("c1", "m1", "l1", "lesson_video")
        with self.assertRaises(ca.AssetError):
            ca.completion_from_adapter_result({"state": "success", "saved_paths": [path]}, m)
        done = ca.completion_from_adapter_result({"state": "success", "saved_paths": [path]}, m,
                                                duration_seconds=12.5)
        self.assertEqual(done["duration_seconds"], 12.5)
        self.assertEqual(done["mime_type"], "video/mp4")


if __name__ == "__main__":
    unittest.main()
