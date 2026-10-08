#!/usr/bin/env python3
"""LSP001 tests: one class per numbered point of the approved lip-sync process.
Stdlib only, $0, no network. Run: python3 core/lip_sync/lip_gate/test_lip_process.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, CORE):
    if p not in sys.path:
        sys.path.insert(0, p)

import lip_process as P                                # noqa: E402
import load_governor as LG                             # noqa: E402
import lipsync_clips as LC                             # noqa: E402

TAKES = {"a.mp4": {"verdict": "NOT_SYNCED", "corr": 0.50},
         "b.mp4": {"verdict": "WEAK", "corr": 0.30},
         "c.mp4": {"verdict": "WEAK", "corr": 0.41},
         "d.mp4": {"verdict": "SYNCED", "corr": 0.20},
         "e.mp4": {"verdict": "SYNCED", "corr": 0.60}}


def meas(path):
    return TAKES[path]


def take(name, **kw):
    return dict({"path": name}, **kw)


class T1ReuseFirst(unittest.TestCase):
    def test_rank_synced_then_weak_then_not_then_corr(self):
        c = P.pick_kept([take(n) for n in TAKES], meas, sung=False)
        self.assertEqual(c["take"], "e.mp4")                  # SYNCED, higher corr
        c = P.pick_kept([take("a.mp4"), take("b.mp4"), take("c.mp4")], meas, False)
        self.assertEqual(c["take"], "c.mp4")                  # WEAK beats NOT_SYNCED 0.50
        c = P.pick_kept([take("a.mp4")], meas, False)
        self.assertEqual(c["take"], "a.mp4")

    def test_defect_flag_drops_the_take(self):
        c = P.pick_kept([take("e.mp4", defect="garbled chest text"), take("d.mp4")],
                        meas, False)
        self.assertEqual(c["take"], "d.mp4")
        self.assertIsNone(P.pick_kept([take("e.mp4", defect=True)], meas, False))

    def test_every_take_is_remeasured(self):
        seen = []
        P.pick_kept([take(n) for n in TAKES], lambda p: seen.append(p) or TAKES[p], True)
        self.assertEqual(sorted(seen), sorted(TAKES))

    def test_no_new_job_where_a_usable_take_exists(self):
        ok, why = P.retry_allowed(usable_take=True, person_verdict=None, jobs=1,
                                  input_fingerprint="new")
        self.assertFalse(ok)
        self.assertEqual(why, P.REUSE_FIRST)

    def test_unmeasurable_take_is_kept_not_dropped(self):
        def boom(_):
            raise RuntimeError("no face")
        c = P.pick_kept([take("a.mp4")], boom, True)
        self.assertEqual(c["take"], "a.mp4")
        self.assertEqual(c["tag"], P.TAG_SUNG)


class T2KeptBest(unittest.TestCase):
    def test_sung_not_confirmed(self):
        c = P.pick_kept([take("a.mp4")], meas, sung=True)
        self.assertEqual(c["tag"], "KEPT_BEST (UNDETERMINED, sung)")
        self.assertTrue(c["needs_strip"])

    def test_borderline_spoken_kept_flagged(self):
        c = P.pick_kept([take("a.mp4")], meas, sung=False)
        self.assertEqual(c["tag"], P.TAG_SPOKEN)
        self.assertTrue(c["flag"])

    def test_synced_is_clean_weak_is_flagged(self):
        self.assertIsNone(P.pick_kept([take("e.mp4")], meas, True)["flag"])
        self.assertEqual(P.pick_kept([take("c.mp4")], meas, True)["flag"], "WEAK")


class T3MouthStrips(unittest.TestCase):
    def test_path(self):
        self.assertEqual(P.strip_path("/d", "Perm_5-v2"), "/d/mouth-strips/Perm_5-v2.png")

    def test_argv_is_bounded_eight_frame_tile(self):
        a = P.mouth_strip_argv("c.mp4", "o.png", 4.0)
        self.assertEqual(a[:3], ["nice", "-n", "10"])
        self.assertIn("tile=8x1", " ".join(a))
        self.assertIn("fps=2.000000", " ".join(a))
        self.assertLessEqual(int(a[a.index("-threads") + 1]), 4)

    @unittest.skipUnless(shutil.which("ffmpeg"), "no ffmpeg")
    def test_real_strip_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            clip = os.path.join(d, "c.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc=size=320x240:rate=30:duration=2", clip], check=True)
            out = P.strip_path(d, "seg1")
            os.makedirs(os.path.dirname(out))
            r = LG.run_ffmpeg(P.mouth_strip_argv(clip, out, 2.0), "strip-test")
            self.assertEqual(r.returncode, 0)
            self.assertGreater(os.path.getsize(out), 500)


class T4Retry(unittest.TestCase):
    def go(self, **kw):
        base = dict(usable_take=False, person_verdict="DEFECT", jobs=1,
                    input_fingerprint="cut2", prior_fingerprints=["cut1"])
        base.update(kw)
        return P.retry_allowed(**base)

    def test_person_defect_with_changed_input_allowed(self):
        self.assertEqual(self.go(), (True, None))

    def test_no_retry_on_a_checker_verdict(self):
        for pv in (None, "", "NOT_SYNCED", "WEAK", "UNDETERMINED"):
            self.assertEqual(self.go(person_verdict=pv)[0], False, pv)

    def test_two_jobs_is_the_limit(self):
        self.assertEqual(self.go(jobs=2), (False, P.JOB_LIMIT))

    def test_same_input_refused(self):
        self.assertEqual(self.go(input_fingerprint="cut1"), (False, P.SAME_INPUT))

    def test_name_variants_all_count(self):
        keys = ["lip-ad-perm5", "lip-ad-perm5-b", "x/lip-ad-perm5_retry", "lip-ad-perm4", "lip-ad-perm50"]
        self.assertEqual(LC.count_jobs(keys, "perm5"), 3)
        self.assertEqual(LC.count_jobs(keys, "perm4"), 1)
        self.assertEqual(self.go(jobs=LC.count_jobs(keys, "perm5"))[0], False)

    def test_first_job_is_not_a_retry(self):
        self.assertEqual(P.retry_allowed(usable_take=False, person_verdict=None,
                                         jobs=0, input_fingerprint="x"), (True, None))


class T5Edit(unittest.TestCase):
    def plan(self, **kw):
        a = dict(clip="k.mp4", out="o.mp4", audio_len_s=4.2, word_start=10.0,
                 lead_s=0.35, stem_offset_s=0.066, cut_corrected=False)
        a.update(kw)
        return P.edit_plan(**a)

    def test_trim_to_audio_length(self):
        a = self.plan()["argv"]
        self.assertEqual(a[a.index("-t") + 1], "4.200")

    def test_place_at_suno_time_corrected_for_stem_lateness(self):
        self.assertAlmostEqual(self.plan()["place_at"], 10.0 - 0.35 - 0.066, 4)
        self.assertAlmostEqual(self.plan(cut_corrected=True)["place_at"], 9.65, 4)

    def test_lanczos_upscale(self):
        self.assertIn("scale=1080:1920:flags=lanczos", self.plan()["vf"])

    def test_fps_drops_never_invents(self):
        self.assertEqual(P.fps_filter(60, 30), "fps=30")
        self.assertEqual(P.fps_filter(30, 30), "")
        self.assertEqual(P.fps_filter(24, 30), "")
        for src in (24, 30, 60):
            self.assertNotIn("minterpolate", self.plan(src_fps=src)["vf"])
        self.assertIn("fps=30", self.plan(src_fps=60)["vf"])

    def test_through_load_governor(self):
        a = self.plan()["argv"]
        self.assertEqual(a[:3], ["nice", "-n", "10"])
        self.assertLessEqual(int(a[a.index("-threads") + 1]), 4)
        with open(os.path.join(HERE, "lip_process.py")) as f:
            src = f.read()
        self.assertNotIn("subprocess", src)


class T6QC(unittest.TestCase):
    def row(self, take_name, sung, strip="/d/mouth-strips/s.png"):
        c = P.pick_kept([take(take_name)], meas, sung)
        return P.receipt_row("S 1", c, 2, strip if c["needs_strip"] else None)

    def test_kept_best_with_strip_passes(self):
        r = self.row("a.mp4", True)
        self.assertEqual(r["jobs_used"], "2 of 2")
        self.assertEqual(r["tag"], P.TAG_SUNG)
        q = P.qc_rows([r])
        self.assertTrue(q["pass"], q)
        self.assertEqual(q["strips"], ["/d/mouth-strips/s.png"])

    def test_flagged_without_strip_fails(self):
        r = self.row("a.mp4", True)
        r["mouth_strip"] = None
        self.assertEqual(P.qc_rows([r])["failed"], [("S_1", P.NO_STRIP)])

    def test_clean_synced_needs_no_strip(self):
        self.assertTrue(P.qc_rows([self.row("e.mp4", False)])["pass"])

    def test_row_lists_take_numbers_flag_strip(self):
        r = self.row("c.mp4", False)
        for k in ("kept_take", "jobs_used", "verdict", "numbers", "flag", "mouth_strip"):
            self.assertIn(k, r)
        self.assertEqual(r["numbers"], {"corr": 0.41})


class T7Docs(unittest.TestCase):
    """The four docs describe exactly this process and nothing contradicts it."""
    ROOT = os.path.dirname(os.path.dirname(CORE))

    def read(self, rel):
        with open(os.path.join(self.ROOT, rel)) as f:
            return f.read()

    def test_docs_carry_the_process(self):
        for rel in ("SKILL.md", "INSTRUCTIONS.md", "QC.md",
                    "references/QC-CHECKLIST-BEFORE-DELIVERY.md"):
            s = self.read(rel)
            for needle in ("KEPT_BEST", "mouth-strips", "person"):
                self.assertIn(needle, s, (rel, needle))
        s = self.read("SKILL.md")
        for needle in ("Reuse first", "UNDETERMINED, sung", "lanczos",
                       "stem_offset", "load_governor", "DROPPING frames"):
            self.assertIn(needle, s, needle)

    def test_no_contradicting_text(self):
        for rel in ("SKILL.md", "INSTRUCTIONS.md", "QC.md",
                    "references/QC-CHECKLIST-BEFORE-DELIVERY.md"):
            s = " ".join(self.read(rel).split())
            self.assertNotIn("second only on a hard defect", s, rel)
            self.assertNotIn("try 2 only on a hard defect", s, rel)
            self.assertNotIn("Try 2 runs only on a hard defect", s, rel)


if __name__ == "__main__":
    unittest.main(verbosity=1)
