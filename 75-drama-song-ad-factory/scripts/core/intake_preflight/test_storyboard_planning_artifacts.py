"""Planning artifacts unlock keyframes; actual whole-package approval unlocks video.

Real intake, planner validation, Store transitions and approval handlers. All
assets are bounded synthetic temp bytes; no model, provider or media render.
"""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

CORE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORE))
from intake_preflight import factory
import production_process
from shot_planner import shot_planner as planner
from storyboard_director import approval_runner
from test_production_process import (confirmed_run, complete_stage, approve_script,
                                    write_json, run_hashes)


class StoryboardPlanningArtifacts(unittest.TestCase):
    def test_planning_without_approval_gate_admits_keyframes_and_keeps_video_paused(self):
        with tempfile.TemporaryDirectory(prefix="storyboard-planning-artifacts-") as tmp:
            run = Path(tmp) / "run"
            confirmed_run(run, song=False)
            for stage in ("research", "creative-strategy", "script-lyrics"):
                complete_stage(run, stage)
            approve_script(run)
            for stage in ("music", "continuity-bible"):
                complete_stage(run, stage)
            actions = ("Christine reads an unanswered invitation", "Christine turns her phone facedown",
                       "Christine opens her New Chapter workbook", "Christine circles a goal in her workbook",
                       "Christine calls her friend", "Christine walks into the class",
                       "Christine laughs with her new group", "Christine marks the next date in her calendar")
            shots, contracts, lines = [], {}, {}
            for n, action in enumerate(actions, 1):
                sid, lid = "s%d" % n, "l%d" % n
                start, end = (n - 1) * 14.75, n * 14.75
                shots.append({"shot_id": sid, "song_start": start, "song_end": end,
                              "lyric_line_ids": [lid], "story_stage": "new-chapter-%d" % n,
                              "visual_objective": action, "character_ids": ["christine"],
                              "wardrobe_ids": ["suit"], "location_id": "office" if n < 5 else "classroom",
                              "product_visibility": "featured" if n == 3 else "none",
                              "camera_direction": ("close hands", "profile face", "wide action")[(n - 1) % 3],
                              "reference_assets": [], "image_model_capability_request": {"capabilities": ["image"]},
                              "video_model_capability_request": {"capabilities": ["video"]},
                              "continuity_constraints": [], "negative_constraints": [], "cost_estimate": 0,
                              "qc_requirements": ["speaker-visibility"], "status": "planned"})
                contracts[sid] = {"lyric_text": "I choose my next step %d" % n,
                                  "viewer_understanding": action, "character_action": action,
                                  "visible_emotion": "hope", "change_from_prior": "she takes her next step",
                                  "treatment": "literal-repeat", "necessity": "shows the next choice she makes"}
                lines[lid] = {"start": start, "end": end, "text": contracts[sid]["lyric_text"]}
            bound = planner.bind_plan(shots, {"duration_seconds": 118, "lines": lines},
                                      contracts, chosen_length_s=120)
            self.assertEqual(bound["outcome"], "ok", bound)
            write_json(run / "storyboard" / "shot-list.json", {"shots": shots})
            write_json(run / "storyboard" / "contracts.json", contracts)
            self.assertEqual(factory.validate_registry(), [])
            self.assertEqual(factory.STAGE_REGISTRY["storyboard"]["required_artifacts"],
                             ["storyboard/shot-list.json", "storyboard/contracts.json"])
            self.assertEqual(factory.STAGE_REGISTRY["image-keyframes"]["prerequisites"], ["storyboard"])
            self.assertEqual(factory.STAGE_REGISTRY["video-generation"]["prerequisites"], ["image-keyframes"])
            complete_stage(run, "storyboard")
            for name in ("gate.json", "approval.json", "stills.json"):
                self.assertFalse((run / "storyboard" / name).exists(), name)
            before = run_hashes(run)
            admitted = production_process.admit_production(run, "image-keyframes")
            self.assertTrue(admitted["ok"], admitted)
            self.assertEqual(run_hashes(run), before)
            output = io.StringIO()
            with redirect_stdout(output):
                code = factory.main(["next", "--run-dir", str(run)])
            next_images = json.loads(output.getvalue())
            self.assertEqual(code, 0, next_images)
            self.assertEqual(next_images["data"]["stage"], "image-keyframes")
            self.assertTrue(next_images["data"]["production_admitted"])
            complete_stage(run, "image-keyframes")
            output = io.StringIO()
            with redirect_stdout(output):
                code = factory.main(["next", "--run-dir", str(run)])
            paused = json.loads(output.getvalue())
            self.assertEqual(code, 2, paused)
            self.assertEqual(paused["reason_code"], "storyboard-approval-required")
            self.assertNotIn("command", paused["data"])
            self.assertFalse((run / "storyboard" / "gate.json").exists())
            stills = {}
            for shot in shots:
                path = run / "storyboard" / (shot["shot_id"] + ".png")
                path.write_bytes(("synthetic local still " + shot["shot_id"]).encode())
                stills[shot["shot_id"]] = str(path)
            write_json(run / "storyboard" / "stills.json", stills)
            sent = []
            pending = approval_runner.run(str(run), lambda text, images: sent.append((text, images)))
            self.assertEqual(pending["action"], "waiting", pending)
            self.assertTrue(sent)
            self.assertFalse((run / "storyboard" / "gate.json").exists())
            held = production_process.admit_production(run, "video-generation")
            self.assertFalse(held["ok"], held)
            self.assertEqual(held["reason_code"], "PRODUCTION_STAGE_NOT_RUNNABLE")
            approved = approval_runner.run(str(run), lambda text, images: None, reply="GO")
            self.assertEqual(approved["action"], "approved", approved)
            video = production_process.admit_production(run, "video-generation")
            self.assertTrue(video["ok"], video)
            self.assertEqual(set(video["approved_storyboard"]["shot_ids"]), set(stills))


if __name__ == "__main__":
    unittest.main()
