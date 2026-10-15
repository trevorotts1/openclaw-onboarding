#!/usr/bin/env python3
"""Method trailers and ad clips in the delivery folder (W1-method-trailer-U2).

Covers what SPEC C5 / F11 / F19 ask of THIS module and nothing else:
  * a method run names its files ``06 - Trailer 60s.mp4`` /
    ``06 - Trailer 90s.mp4`` and ``13 - Ad 60s.mp4`` / ``13 - Ad 90s.mp4``
    (slot 7 is the Ready-to-Post Kit, so the ad clip takes 13);
  * each trailer/ad row writes its own ``destination`` (trailers ->
    episode/channel, ads -> the offer) and its ``source_map`` into
    ``delivery-receipt.json`` (merge, never clobber) and the README;
  * a trailer without a destination, an ad without an offer link and a plan
    with no source map all fail closed BEFORE anything is cut or listed;
  * the delivery audio gate still guards every delivered file;
  * a non-method run keeps ``06 - Clip 60s.mp4`` and today's rows untouched.

No media, no network: the ffmpeg runner and the audio gate are injected.
The trailer/ad PLANS come from ``clip_cutdown.plan_clips`` once
W1-method-trailer-U1 lands (its ``trailer.plan_trailers`` /
``ad_clip.plan_ad_clips`` dispatch); this test injects those plans directly so
the delivery half is provable on its own, exactly as the unit's Prove line
asks.

Run: python3 delivery_clips/test_trailer_delivery.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

import delivery_audio  # noqa: E402
from clip_cutdown import clips_for  # noqa: E402
from delivery_clips import delivery_clips as dc  # noqa: E402
from delivery_clips.delivery_clips import (  # noqa: E402
    AD_ITEM,
    CLIP_ITEM,
    DeliveryClipsError,
    check_clips,
    clip_file_name,
    deliver_clips,
    plan_kind,
    source_map,
)
from clip_cutdown.trailer import end_card_lines, end_card_s  # noqa: E402

EPISODE_DEST = "Watch the full episode on @the-show"
OFFER_DEST = "https://example.test/buy"

#: The card copy ``trailer.plan`` would build from the show/offer records, so
#: the fixture's end card is shaped exactly like the shipped one.
_FIELDS = {"trailer": {"name": "The Show", "episode": "Ep 12",
                       "channel": "@the-show", "destination": EPISODE_DEST},
           "ad": {"cta": "Learn more", "name": "The Offer",
                  "link": OFFER_DEST}}


def trailer_plan(length=60, pieces=True, destination=EPISODE_DEST, kind="trailer"):
    """One trailer plan shaped the way W1-method-trailer-U1 hands them over.

    The end card and the per-piece ``piece``/``duration_s`` keys are part of
    that contract: ``clip_cutdown.trailer.render`` reads ``end_card`` for the
    card text and each non-card piece's ``duration_s`` to size the joined
    ranges, so a plan without them cannot be cut. ``delivery_clips.source_map``
    keeps reporting only the four window keys, so the receipt rows below are
    unchanged.
    """
    dur = float(length - 5)
    plan = {"name": "%s-%ds" % (kind, length), "kind": kind,
            "clip_length_s": length, "start_s": 0.0, "end_s": dur,
            "duration_s": dur, "hooks": 2, "beats": 3,
            "captions_offset_s": 0.0,
            "end_card": {"kind": kind, "duration_s": end_card_s(),
                         "lines": end_card_lines(kind, _FIELDS[kind]),
                         "source_in": 52.0}}
    if destination is not None:
        plan["destination"] = destination
    if pieces:
        plan["pieces"] = [
            {"piece": "scene-1", "source_in": 12.0, "source_out": 24.0,
             "trailer_in": 0.0, "trailer_out": 12.0, "duration_s": 12.0},
            {"piece": "scene-2", "source_in": 40.0, "source_out": 52.0,
             "trailer_in": 12.0, "trailer_out": 24.0, "duration_s": 12.0},
        ]
    return plan


def ad_plan(length=60, pieces=True, destination=OFFER_DEST):
    return trailer_plan(length=length, pieces=pieces, destination=destination,
                        kind="ad")


def method_plans(pieces=True):
    """The four files a method run ships: two trailers, two ad clips."""
    return [trailer_plan(60, pieces), trailer_plan(90, pieces),
            ad_plan(60, pieces), ad_plan(90, pieces)]


def plain_timeline(total=178.0):
    """A non-method timeline: a line every 5 s, hooks where they belong."""
    lines = []
    for i in range(int(total // 5)):
        s = i * 5.0
        lines.append({"line_id": "L%d" % i, "start_s": s, "end_s": s + 4.5,
                      "beat": "beat%d" % (i // 3),
                      "hook": i in (4, 9, 14, 19, 24)})
    return {"schema_version": "blackceo.timeline/v1", "lines": lines}


def fake_runner(calls, fail_on=None):
    """A runner that records argv and touches the output file (no ffmpeg)."""

    def run(argv, **kw):
        calls.append(argv)
        if fail_on and fail_on in argv[-1]:
            class R:
                returncode = 1
            return R()
        Path(argv[-1]).write_bytes(b"fake mp4")

        class R:
            returncode = 0
        return R()
    return run


def ok_gate(_path):
    return {"ok": True, "reason_code": "DELIVERY_AUDIO_OK", "reason": "ok"}


class Base(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp(prefix="trailer-delivery-"))
        self.delivery = self.t / "delivery"
        self.calls = []
        patcher = unittest.mock.patch.object(
            delivery_audio, "check_delivery_audio",
            lambda *a, **k: dict(ok=True,
                                 reason_code="DELIVERY_AUDIO_OK",
                                 reason="aac-lc 48 kHz faststart, ok"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def build(self, plans, tl=None, length=180, audio_gate=ok_gate,
              runner=None):
        """deliver_clips with ``plans`` standing in for plan_clips."""
        patcher = unittest.mock.patch.object(
            dc, "plan_clips", lambda _tl, _l: [dict(p) for p in plans])
        patcher.start()
        self.addCleanup(patcher.stop)
        return deliver_clips(tl if tl is not None else plain_timeline(),
                             length, str(self.t / "master.mp4"),
                             str(self.delivery),
                             runner=runner or fake_runner(self.calls),
                             audio_gate=audio_gate)

    def receipt(self):
        return json.loads(
            (self.delivery / "delivery-receipt.json").read_text())

    def readme(self):
        return (self.delivery / "README.md").read_text()


class Names(Base):
    def test_trailer_and_ad_file_names(self):
        self.assertEqual(clip_file_name(60, "trailer"),
                         "06 - Trailer 60s.mp4")
        self.assertEqual(clip_file_name(90, "trailer"),
                         "06 - Trailer 90s.mp4")
        self.assertEqual(clip_file_name(60, "ad"), "13 - Ad 60s.mp4")
        self.assertEqual(clip_file_name(90, "ad"), "13 - Ad 90s.mp4")
        # slot 07 belongs to the Ready-to-Post Kit, never to an ad clip
        self.assertEqual(CLIP_ITEM, 6)
        self.assertEqual(AD_ITEM, 13)

    def test_a_run_without_method_keeps_the_contract_names(self):
        self.assertEqual(clip_file_name(60), "06 - Clip 60s.mp4")
        self.assertEqual(clip_file_name(90), "06 - Clip 90s.mp4")
        self.assertEqual(clip_file_name(60, "clip"), "06 - Clip 60s.mp4")

    def test_unknown_kind_and_length_are_refusals(self):
        with self.assertRaises(DeliveryClipsError):
            clip_file_name(60, "teaser")
        with self.assertRaises(DeliveryClipsError):
            clip_file_name(120, "trailer")
        with self.assertRaises(DeliveryClipsError):
            clip_file_name(120)

    def test_plan_kind_reads_the_kind_then_the_plan_name(self):
        self.assertEqual(plan_kind({"kind": "ad", "name": "x"}), "ad")
        self.assertEqual(plan_kind({"name": "trailer-90s"}), "trailer")
        self.assertEqual(plan_kind({"name": "ad-60s"}), "ad")
        self.assertEqual(plan_kind({"name": "clip-60s"}), "clip")
        self.assertEqual(plan_kind({}), "clip")


class MethodDelivery(Base):
    def test_four_files_land_with_trailer_and_ad_names(self):
        rows = self.build(method_plans())
        self.assertEqual([r["file"] for r in rows], [
            "06 - Trailer 60s.mp4",
            "06 - Trailer 90s.mp4",
            "13 - Ad 60s.mp4",
            "13 - Ad 90s.mp4"])
        for r in rows:
            p = self.delivery / r["file"]
            self.assertTrue(p.is_file() and p.stat().st_size > 0, p)
        # the raw plan names never reach the client folder
        self.assertFalse((self.delivery / "trailer-60s.mp4").exists())
        self.assertFalse((self.delivery / "ad-90s.mp4").exists())

    def test_each_row_records_its_destination_and_source_map(self):
        rows = self.build(method_plans())
        by_name = {r["file"]: r for r in rows}
        for name in ("06 - Trailer 60s.mp4", "06 - Trailer 90s.mp4"):
            self.assertEqual(by_name[name]["destination"], EPISODE_DEST)
            self.assertEqual(by_name[name]["source_map"], [
                {"source_in": 12.0, "source_out": 24.0,
                 "trailer_in": 0.0, "trailer_out": 12.0},
                {"source_in": 40.0, "source_out": 52.0,
                 "trailer_in": 12.0, "trailer_out": 24.0}])
        for name in ("13 - Ad 60s.mp4", "13 - Ad 90s.mp4"):
            self.assertEqual(by_name[name]["destination"], OFFER_DEST)
        # trailers point at the episode, ads at the offer -- never swapped
        self.assertNotEqual(by_name["06 - Trailer 60s.mp4"]["destination"],
                            by_name["13 - Ad 60s.mp4"]["destination"])

    def test_receipt_carries_the_rows_and_keeps_other_keys(self):
        self.delivery.mkdir(parents=True, exist_ok=True)
        (self.delivery / "delivery-receipt.json").write_text(
            json.dumps({"keep": 1, "song_files": [{"file": "a.mp3"}]}))
        rows = self.build(method_plans())
        receipt = self.receipt()
        self.assertEqual(receipt["keep"], 1)
        self.assertEqual(receipt["song_files"], [{"file": "a.mp3"}])
        self.assertEqual(receipt["delivery_clips"], rows)
        for r in rows:
            self.assertIn("destination", r)
            self.assertIn("source_map", r)

    def test_readme_states_the_destination_per_file(self):
        self.build(method_plans())
        text = self.readme()
        for name in ("06 - Trailer 60s.mp4", "06 - Trailer 90s.mp4",
                     "13 - Ad 60s.mp4", "13 - Ad 90s.mp4"):
            self.assertIn(name, text)
        self.assertIn(EPISODE_DEST, text)
        self.assertIn(OFFER_DEST, text)

    def test_a_plan_without_pieces_records_its_window_as_the_map(self):
        # A trailer/ad plan always carries pieces (trailer._record writes them)
        # and ``trailer.render`` cannot cut a piece-less one -- it needs at
        # least two source ranges -- so this state never reaches a receipt row.
        # The whole-window fallback is asserted on the function that owns it.
        plan = {"name": "trailer-60s", "kind": "trailer",
                "start_s": 0.0, "end_s": 55.0, "duration_s": 55.0}
        self.assertEqual(source_map(plan), [{
            "source_in": 0.0, "source_out": 55.0,
            "trailer_in": 0.0, "trailer_out": 55.0}])

    def test_the_audio_gate_still_watches_every_method_file(self):
        seen = []

        def watching_gate(path):
            seen.append(os.path.basename(path))
            return ok_gate(path)
        self.build(method_plans(), audio_gate=watching_gate)
        for name in ("06 - Trailer 60s.mp4", "06 - Trailer 90s.mp4",
                     "13 - Ad 60s.mp4", "13 - Ad 90s.mp4"):
            self.assertIn(name, seen)

    def test_a_refused_trailer_is_deleted_and_never_listed(self):

        def bad_gate(_path):
            return {"ok": False, "reason_code": delivery_audio.BAD_CODEC,
                    "reason": "audio codec is 'mp3', must be aac"}
        # ValueError, not ClipCutdownError: clip_cutdown.run_clips imports
        # clip_cutdown.trailer LAZILY, and scripts/conftest.py drops skill-tree
        # modules between collectors, so that import can build a second module
        # copy with a second ClipCutdownError class. The refusal CODE below is
        # the stable contract and is what pins the failure to this path.
        with self.assertRaises(ValueError) as cm:
            self.build(method_plans(), audio_gate=bad_gate)
        self.assertIn("CLIP_AUDIO_REFUSED", str(cm.exception))
        self.assertEqual(list(self.delivery.glob("*.mp4")), [])
        rp = self.delivery / "delivery-receipt.json"
        self.assertFalse(
            rp.exists() and
            (json.loads(rp.read_text()).get("delivery_clips")))


class FailClosed(Base):
    def test_trailer_without_a_destination_is_never_cut(self):
        plans = [trailer_plan(60, destination=None), trailer_plan(90)]
        with self.assertRaises(DeliveryClipsError) as cm:
            self.build(plans)
        self.assertIn("TRAILER_NO_DESTINATION", str(cm.exception))
        # refused before ffmpeg ran: nothing half-delivered is left behind
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.delivery.glob("*.mp4")), [])

    def test_ad_without_an_offer_link_is_refused(self):
        plans = [ad_plan(60, destination=""), ad_plan(90)]
        with self.assertRaises(DeliveryClipsError) as cm:
            self.build(plans)
        self.assertIn("AD_NO_OFFER_DESTINATION", str(cm.exception))
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.delivery.glob("*.mp4")), [])

    def test_a_plan_with_no_source_map_is_refused(self):
        plans = [trailer_plan(60, pieces=False)]
        del plans[0]["start_s"]
        del plans[0]["end_s"]
        with self.assertRaises(DeliveryClipsError) as cm:
            self.build(plans)
        self.assertIn("TRAILER_NO_SOURCE_MAP", str(cm.exception))
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.delivery.glob("*.mp4")), [])

    def test_an_ffmpeg_failure_leaves_no_method_file(self):
        # A method derivative is cut by clip_cutdown.trailer.render (one joined
        # render per plan), so its ffmpeg refusal carries that module's code.
        # ValueError rather than ClipCutdownError for the same module-copy
        # reason as the audio-gate refusal above.
        runner = fake_runner(self.calls, fail_on="ad-90s")
        with self.assertRaises(ValueError) as cm:
            self.build(method_plans(), runner=runner)
        self.assertIn("TRAILER_FFMPEG_FAILED", str(cm.exception))
        self.assertEqual(list(self.delivery.glob("*.mp4")), [])


class NonMethod(Base):
    def test_a_run_without_method_is_untouched(self):
        rows = deliver_clips(plain_timeline(), 180,
                             str(self.t / "master.mp4"),
                             str(self.delivery),
                             runner=fake_runner(self.calls),
                             audio_gate=ok_gate)
        self.assertEqual([r["file"] for r in rows],
                         ["06 - Clip 60s.mp4", "06 - Clip 90s.mp4"])
        for r in rows:
            self.assertEqual(r["kind"], "clip")
            self.assertNotIn("destination", r)
            self.assertNotIn("source_map", r)
            for key in ("start_s", "end_s", "duration_s", "hooks", "beats"):
                self.assertIn(key, r)
        readme = self.readme()
        self.assertIn("06 - Clip 60s.mp4", readme)
        self.assertNotIn("Trailer", readme)
        self.assertNotIn("destination:", readme)

    def test_the_clip_check_is_unchanged(self):
        deliver_clips(plain_timeline(), 180, str(self.t / "master.mp4"),
                      str(self.delivery), runner=fake_runner(self.calls),
                      audio_gate=ok_gate)
        verdict, detail = check_clips(str(self.delivery), 180)
        self.assertEqual(verdict, "PASS", detail)
        self.assertEqual(detail,
                         "both clips present, listed and AAC-LC 48 kHz "
                         "faststart")
        (self.delivery / clip_file_name(90)).unlink()
        self.assertEqual(check_clips(str(self.delivery), 180)[0], "FAIL")


class Check(Base):
    def test_a_complete_method_delivery_passes(self):
        self.build(method_plans())
        verdict, detail = check_clips(str(self.delivery), 180)
        self.assertEqual(verdict, "PASS", detail)
        self.assertIn("4 trailer/ad file(s)", detail)

    def test_a_missing_trailer_fails_naming_the_file(self):
        self.build(method_plans())
        (self.delivery / "06 - Trailer 90s.mp4").unlink()
        verdict, detail = check_clips(str(self.delivery), 180)
        self.assertEqual(verdict, "FAIL")
        self.assertIn("06 - Trailer 90s.mp4", detail)

    def test_a_missing_ad_clip_fails_naming_the_file(self):
        self.build(method_plans())
        (self.delivery / "13 - Ad 60s.mp4").unlink()
        verdict, detail = check_clips(str(self.delivery), 180)
        self.assertEqual(verdict, "FAIL")
        self.assertIn("13 - Ad 60s.mp4", detail)

    def test_an_unlisted_trailer_fails(self):
        self.build(method_plans())
        (self.delivery / "delivery-receipt.json").write_text("{}")
        self.assertEqual(check_clips(str(self.delivery), 180)[0], "FAIL")

    def test_a_trailer_failing_the_audio_gate_fails_the_delivery(self):
        self.build(method_plans())
        (self.delivery / "13 - Ad 90s.mp4").write_bytes(b"broken")

        def one_bad(path, *a, **k):
            if os.path.basename(path) == "13 - Ad 90s.mp4":
                return dict(ok=False, reason_code=delivery_audio.BAD_CODEC,
                            reason="codec is 'mp3'")
            return dict(ok=True, reason_code="DELIVERY_AUDIO_OK",
                        reason="aac-lc 48 kHz faststart, ok")
        patcher = unittest.mock.patch.object(
            delivery_audio, "check_delivery_audio", one_bad)
        patcher.start()
        self.addCleanup(patcher.stop)
        verdict, detail = check_clips(str(self.delivery), 180)
        self.assertEqual(verdict, "FAIL")
        self.assertIn("13 - Ad 90s.mp4", detail)

    def test_sixty_second_ads_owe_nothing(self):
        for length in (60, 90):
            self.assertEqual(clips_for(length), ())
            self.assertEqual(check_clips(str(self.delivery), length)[0],
                             "PASS")


if __name__ == "__main__":
    unittest.main()
