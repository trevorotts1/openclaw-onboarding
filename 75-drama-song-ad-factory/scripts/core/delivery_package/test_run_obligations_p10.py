#!/usr/bin/env python3
"""P10 (bbdb4a28): what a run OWES comes from its own recorded answers.

The delivery package used to demand the same twelve files from every run: a
60-second ad was asked for two clips it never had, a campaign's trailers were
copied over the clip names and its ad clips dropped, and a packaging call
accepted a folder with no intake, purpose record or saved length at all.

Every check here runs the REAL intake writer, the REAL stage store, the REAL
method record, the REAL derivative planner and the REAL delivery-clip adapter.
Only two external boundaries are faked: the ffmpeg process (no frame is ever
encoded) and the audio probe (no codec is measured). The ten package items
this repair does not change are produced by contract-valid fixture writers --
their own deliver paths have their own suites -- exactly so the subject here
stays the obligation contract, not someone else's renderer.

Run: python3 delivery_package/test_run_obligations_p10.py
"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import delivery_audio                              # noqa: E402
import delivery_package.contract as C              # noqa: E402
import delivery_package.packaging as P             # noqa: E402
from choice_card.intake_card import intake_session as session  # noqa: E402
from delivery_clips import delivery_clips as dc    # noqa: E402
from delivery_package import run_inputs as RI      # noqa: E402
from sung_hook import sung_hook as SH              # noqa: E402
from test_production_process import run_hashes     # noqa: E402

PDF = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\n%%EOF\n"
SRT_OK = "1\n00:00:00,000 --> 00:00:01,000\nline\n"
MEDIA = b"media-bytes" * 8
PNG = b"\x89PNG\r\n\x1a\nimage" * 2
NOTE = b"# note\n"

#: the campaign blueprint's six beat ranges, in story order. Every range
#: carries the music cue that gives it a structural role; the end card and the
#: offer never ride a trailer's source ranges (method 8.3).
CAMPAIGN_BEATS = (
    ("b-open", "BASELINE", 0.0, 12.0, "the morning routine that matters"),
    ("b-erm", "ERM_DROP", 12.0, 36.0, None),
    ("b-pain", "PAIN_BUILD", 36.0, 64.0, "the cost of never taking the time"),
    ("b-hero", "HERO_SHIFT", 64.0, 88.0, "the small ritual that turns the day"),
    ("b-break", "BREAKTHROUGH", 88.0, 116.0,
     "she starts the day on her own terms"),
    ("b-hook", "SOLUTION_HOOK", 116.0, 140.0, None),
)
EPISODE_LINK = "https://example.test/episode"
OFFER_LINK = "https://example.test/buy"


# --------------------------------------------------------------- run inputs ---
def _replies(length, purpose):
    """One real client reply per card question the run will ask."""
    out = {"offer": "New Chapter Coaching",
           "link": "https://example.com/coaching",
           "audience": "successful founders 45-60",
           "character": "Christine, a lawyer",
           "photos": "Generate the photos",
           "models": "deepseek-chain builds, opus-chain checks",
           "spend": "$25", "script": "1", "song": "1", "storyboard": "1"}
    out["purpose" if purpose is not None else "length"] = (
        str(purpose) if purpose is not None else length)
    if purpose is not None:
        out["episode_length" if purpose == 1 else "length"] = length
    return out


def build_run(run, *, length="3 minutes", purpose=None):
    """A REAL confirmed intake: full card, session writer, stage store.

    purpose None is a legacy (no purpose card) run; 1 is the campaign purpose;
    3 is a lesson. The reply set is what the fixture client actually typed.
    """
    run = Path(run)
    flow = purpose is not None
    replies = _replies(length, purpose)
    turn = session.process([], run_dir=run, purpose_flow=flow,
                           runtime="claude-nine")
    for _ in range(40):
        if turn.get("done"):
            return turn["run_id"]
        qid = turn.get("question_id")
        raw = "yes" if qid == "recap" else replies.get(qid, "1")
        turn = session.process([raw], run_dir=run, purpose_flow=flow,
                               runtime="claude-nine", question_id=qid,
                               question_digest=turn.get("question_digest"),
                               source="client", source_ref="p10:" + str(qid))
        if turn.get("outcome") == "error":
            raise AssertionError(turn)
    raise AssertionError("intake did not reach its confirmation: %r" % turn)


def _lines(total, beat_of):
    hooks = SH.hook_times(total)
    out = []
    for i in range(int(total // 4)):
        start = i * 4.0
        out.append({"line_id": "L%d" % i, "start_s": start,
                    "end_s": start + 3.8, "beat": beat_of(start),
                    "hook": any(start <= h < start + 4.0 for h in hooks)})
    return out


def plain_timeline(total=150.0):
    """An ordinary (non-method) timeline: whole lines, hooks where they belong."""
    return {"schema_version": "blackceo.timeline/v1",
            "lines": _lines(total, lambda s: "beat%d" % (int(s) // 16))}


def method_timeline(purpose, total=150.0):
    """The same lines plus the method block the card wrote (no campaign data)."""
    doc = plain_timeline(total)
    doc["method"] = {"purpose": purpose}
    return doc


def campaign_timeline(total=150.0):
    """A campaign timeline: method block, blueprint, show and offer records."""
    def beat_of(start):
        for beat_id, _cue, begin, end, _why in CAMPAIGN_BEATS:
            if begin <= start < end:
                return beat_id
        return "b-extra"
    lines = _lines(total, beat_of)
    lines[4]["first_sung"] = True                    # inside the ERM range
    return {"schema_version": "blackceo.timeline/v1", "lines": lines,
            "method": {"purpose": "campaign"},
            "blueprint": {
                "story_beats": [
                    {"story_beat_id": beat_id, "music_cue_ids": [cue],
                     "start_s": begin, "end_s": end,
                     **({"trailer_value": why} if why else {})}
                    for beat_id, cue, begin, end, why in CAMPAIGN_BEATS],
                "music_cues": [{"music_cue_id": "ERM_DROP", "start_s": 16.0,
                                "vocal_status": "sung"}]},
            "show": {"name": "The Show", "episode": "Ep 12",
                     "channel": "@the-show", "destination": EPISODE_LINK},
            "offer": {"link": OFFER_LINK, "cta": "Start today",
                      "name": "The Offer"}}


def write_run_files(run, timeline):
    """The real run inputs the clip producer reads, as real files on disk."""
    run = Path(run)
    (run / "edit").mkdir(parents=True, exist_ok=True)
    (run / "edit" / "timeline.json").write_text(json.dumps(timeline),
                                                encoding="utf-8")
    (run / "edit" / "ad.mp4").write_bytes(b"master-bytes-not-encoded")
    return run


def cli_check(delivery, run):
    """Run the ACTUAL command line in --check mode; (exit code, parsed JSON)."""
    out = io.StringIO()
    with redirect_stdout(out):
        code = dc.main(["--delivery", str(delivery), "--check",
                        "--run", str(run)])
    return code, json.loads(out.getvalue())


# ---------------------------------------------------------- boundary fakes ---
def _fake_runner(calls):
    """The ffmpeg PROCESS, faked: records argv and touches the output file."""
    def run(argv, **_kw):
        calls.append(argv)
        Path(argv[-1]).write_bytes(b"rendered")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return run


class MediaBoundary(unittest.TestCase):
    """Every run here encodes no frame and measures no codec."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p10-obligations-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.renders = []
        real_run_clips = dc.run_clips

        def run_clips(master, plans, out_dir, **kw):
            # the real planner/staging/rename/gate logic; only the process
            # spawn inside it is replaced
            kw["runner"] = _fake_runner(self.renders)
            return real_run_clips(master, plans, out_dir, **kw)

        runner = patch.object(dc, "run_clips", run_clips)
        runner.start()
        self.addCleanup(runner.stop)
        gate = patch.object(
            delivery_audio, "check_delivery_audio",
            lambda *a, **k: {"ok": True, "reason_code": "DELIVERY_AUDIO_OK",
                             "reason": "faked at the external probe"})
        gate.start()
        self.addCleanup(gate.stop)


# ------------------------------------------------------------ the contract ---
class Obligations(unittest.TestCase):
    """What a run owes, derived from its saved length and purpose alone."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p10-contract-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_short_lengths_owe_no_clip_files(self):
        for length in (60, 90, 120):
            with self.subTest(length=length):
                for campaign in (False, True):
                    items = C.required_items(length, campaign_run=campaign)
                    keys = [item.key for item in items]
                    self.assertNotIn("clips", keys)
                    self.assertNotIn("ad_clips", keys)
                    self.assertEqual(len(items), 11)
        self.assertEqual(len(C.PACKAGE_ITEMS), 12)      # display slots unchanged

    def test_ordinary_180_owes_the_contracts_two_clips(self):
        items = C.required_items(180)
        clips = next(item for item in items if item.key == "clips")
        self.assertEqual(clips.files, C.ITEMS_BY_KEY["clips"].files)
        self.assertFalse(any(item.key == "ad_clips" for item in items))

    def test_campaign_180_owes_two_trailers_and_two_ads(self):
        items = C.required_items(180, campaign_run=True)
        clips = next(item for item in items if item.key == "clips")
        ads = next(item for item in items if item.key == "ad_clips")
        self.assertEqual(clips.files, C.METHOD_ITEM_FILES[6])
        self.assertEqual(ads.files, C.AD_CLIPS_ITEM.files)

    def test_campaign_folder_cannot_open_base_clip_names(self):
        folder = self.tmp / "campaign-with-clip-names"
        for item in C.required_items(180, campaign_run=True):
            C.produce_item(item, folder)
        for name in C.METHOD_ITEM_FILES[6]:
            (folder / name).unlink()
        for name in C.ITEMS_BY_KEY["clips"].files:
            (folder / name).write_bytes(MEDIA)
        report = C.verify_folder(folder, chosen_length_s=180, campaign_run=True)
        self.assertEqual(report["authority"], "resolved-run")
        self.assertIn("clips", report["missing"])
        self.assertIn("06 - Clip 60s.mp4", report["not_clean"])
        self.assertFalse(report["ok"])

    def test_short_folder_does_not_demand_or_accept_clip_files(self):
        folder = C.write_reference_package(self.tmp / "short")
        report = C.verify_folder(folder, chosen_length_s=60)
        self.assertIn("clips", report["not_applicable"])
        self.assertNotIn("clips", report["missing"])
        self.assertIn("06 - Clip 60s.mp4", report["not_clean"])
        self.assertEqual(report["expected"], 11)

    def test_context_free_check_stays_structural(self):
        folder = C.write_reference_package(self.tmp / "structural")
        report = C.verify_folder(folder)
        self.assertEqual(report["authority"], "structural-only")
        self.assertEqual(report["expected"], 12)
        self.assertTrue(report["ok"], report)


# ------------------------------------------------------------- run context ---
class RunContext(MediaBoundary):
    """The run's own recorded answers, never the brief or the folder."""

    def test_legacy_short_run_reads_its_saved_length(self):
        for length, seconds in (("60 seconds", 60), ("90 seconds", 90)):
            with self.subTest(length=length):
                run = self.tmp / ("legacy-" + str(seconds))
                build_run(run, length=length)
                ctx = RI.delivery_context(run)
                self.assertEqual(ctx["chosen_length_s"], seconds)
                self.assertFalse(ctx["campaign"])
                self.assertFalse(ctx["method_run"])
                self.assertIsNone(ctx["purpose"])
                self.assertEqual(ctx["not_applicable"], ("clips",))

    def test_legacy_180_reads_the_two_clip_obligation(self):
        run = self.tmp / "legacy-180"
        build_run(run, length="3 minutes + 60s and 90s clips")
        ctx = RI.delivery_context(run)
        self.assertEqual(ctx["chosen_length_s"], 180)
        clips = next(i for i in ctx["items"] if i.key == "clips")
        self.assertEqual(clips.files, C.ITEMS_BY_KEY["clips"].files)
        self.assertEqual(ctx["not_applicable"], ())

    def test_campaign_180_reads_the_trailer_and_ad_obligation(self):
        run = self.tmp / "campaign-180"
        build_run(run, length="3 minutes", purpose=1)
        ctx = RI.delivery_context(run)
        self.assertEqual(ctx["purpose"], "campaign")
        self.assertTrue(ctx["campaign"])
        self.assertTrue(ctx["method_run"])
        self.assertEqual(ctx["chosen_length_s"], 180)
        self.assertEqual(len(ctx["items"]), 13)

    def test_campaign_short_run_owes_no_derivatives(self):
        run = self.tmp / "campaign-60"
        build_run(run, length="60 seconds", purpose=1)
        ctx = RI.delivery_context(run)
        self.assertTrue(ctx["campaign"])
        self.assertEqual(ctx["chosen_length_s"], 60)
        self.assertEqual(ctx["not_applicable"], ("clips",))
        self.assertEqual(len(ctx["items"]), 11)

    def test_lesson_method_reads_ordinary_clips(self):
        run = self.tmp / "lesson-180"
        build_run(run, length="3 minutes + 60s and 90s clips", purpose=3)
        ctx = RI.delivery_context(run)
        self.assertEqual(ctx["purpose"], "lesson")
        self.assertFalse(ctx["campaign"])
        clips = next(i for i in ctx["items"] if i.key == "clips")
        self.assertEqual(clips.files, C.ITEMS_BY_KEY["clips"].files)

    def test_unproven_run_metadata_is_refused_not_inferred(self):
        run = self.tmp / "refusals"
        build_run(run, length="3 minutes", purpose=1)
        ledger = run / "control" / "intake-session.json"
        method = run / "control" / "method.json"
        original_ledger = ledger.read_text(encoding="utf-8")
        original_method = method.read_text(encoding="utf-8")

        cases = []

        def wrong_run():
            return RI.delivery_context(run, run_id="another-run")

        def no_session():
            ledger.unlink()
            return RI.delivery_context(run)

        def no_method():
            ledger.write_text(original_ledger, encoding="utf-8")
            method.unlink()
            return RI.delivery_context(run)

        def broken_method():
            method.write_text("{broken", encoding="utf-8")
            return RI.delivery_context(run)

        def conflicting_length():
            doc = json.loads(original_method)
            doc["chosen_length_s"] = 300
            method.write_text(json.dumps(doc), encoding="utf-8")
            return RI.delivery_context(run)

        def conflicting_purpose():
            doc = json.loads(original_method)
            doc["purpose"] = "lesson"
            method.write_text(json.dumps(doc), encoding="utf-8")
            return RI.delivery_context(run)

        cases = [("wrong run", wrong_run), ("no session", no_session),
                 ("no method record", no_method),
                 ("broken method record", broken_method),
                 ("conflicting length", conflicting_length),
                 ("conflicting purpose", conflicting_purpose)]
        for label, call in cases:
            with self.subTest(case=label):
                method.write_text(original_method, encoding="utf-8")
                with self.assertRaises(RI.RunInputError):
                    call()
        ledger.write_text(original_ledger, encoding="utf-8")
        method.write_text(original_method, encoding="utf-8")
        self.assertTrue(RI.delivery_context(run)["campaign"])


# ---------------------------------------------------------------- packaging ---
def fixture_producers(record):
    """Contract-valid sources for the items this repair does not own."""
    out = {}

    def build(item, root):
        src_dir = Path(root) / ("src-" + item.key)
        src_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i, (name, kind) in enumerate(zip(item.files, item.kinds), 1):
            if kind.startswith("images"):
                d = src_dir / name
                d.mkdir(parents=True, exist_ok=True)
                (d / ("%02d.png" % i)).write_bytes(PNG)
                paths.append(d)
                continue
            p = src_dir / name
            if kind == "pdf":
                p.write_bytes(PDF)
            elif kind == "srt":
                p.write_text(SRT_OK, encoding="utf-8")
            elif kind == "text":
                p.write_bytes(NOTE)
            else:
                p.write_bytes(MEDIA)
            paths.append(p)
        return paths

    for item in C.PACKAGE_ITEMS + (C.AD_CLIPS_ITEM,):
        def make(_run, target, _item=item, _root=record["root"]):
            record["called"].append(_item.key)
            return build(_item, _root)
        out[item.key] = make

    def clips(run_dir, item):
        record["called"].append(item.key)
        return dc.produce_delivery(run_dir, item)
    out["clips"] = clips
    return out


class Packaging(MediaBoundary):
    """package_run against the run's own obligations, with real clip planning."""

    def _setup(self, name, timeline, *, length, purpose=None):
        run = self.tmp / name
        build_run(run, length=length, purpose=purpose)
        write_run_files(run, timeline)
        record = {"root": self.tmp / (name + "-items"), "called": []}
        record["root"].mkdir(parents=True, exist_ok=True)
        return run, record

    def test_short_run_packages_without_a_clip_slot(self):
        run, record = self._setup("pack-60", plain_timeline(), length="60 seconds")
        out = run / "delivery"
        res = P.package_run(run, out, producers=fixture_producers(record))
        self.assertEqual(len(res["items"]), 11)
        self.assertEqual(res["not_applicable"], ["clips"])
        self.assertNotIn("clips", record["called"])
        self.assertEqual(self.renders, [])
        self.assertEqual(list(out.glob("06 - *.mp4")), [])
        self.assertEqual(len(C.PACKAGE_ITEMS), 12)
        report = C.verify_folder(out, chosen_length_s=60)
        self.assertTrue(report["ok"], report)

    def test_ordinary_180_packages_the_two_clips(self):
        run, record = self._setup("pack-180", plain_timeline(),
                                  length="3 minutes + 60s and 90s clips")
        out = run / "delivery"
        res = P.package_run(run, out, producers=fixture_producers(record))
        self.assertEqual(len(res["items"]), 12)
        self.assertEqual(res["not_applicable"], [])
        self.assertEqual(len(self.renders), 2)
        for name in ("06 - Clip 60s.mp4", "06 - Clip 90s.mp4"):
            self.assertTrue((out / name).is_file(), name)
        self.assertEqual(dc.check_clips(out, run_dir=run)[0], "PASS")

    def test_campaign_180_renders_four_derivatives_once(self):
        run, record = self._setup("pack-campaign", campaign_timeline(),
                                  length="3 minutes", purpose=1)
        out = run / "delivery"
        res = P.package_run(run, out, producers=fixture_producers(record))
        self.assertTrue(res["campaign"])
        self.assertEqual(len(res["items"]), 13)
        self.assertEqual(record["called"].count("clips"), 1)
        self.assertNotIn("ad_clips", record["called"])     # no second render
        self.assertEqual(len(self.renders), 4)
        for name in ("06 - Trailer 60s.mp4", "06 - Trailer 90s.mp4",
                     "13 - Ad 60s.mp4", "13 - Ad 90s.mp4"):
            self.assertTrue((out / name).is_file(), name)
        self.assertFalse((out / "06 - Clip 60s.mp4").exists())
        verdict, detail = dc.check_clips(out, run_dir=run)
        self.assertEqual(verdict, "PASS", detail)

    def test_missing_promised_derivative_fails_with_its_receipt_row_gone(self):
        run, record = self._setup("pack-missing", campaign_timeline(),
                                  length="3 minutes", purpose=1)
        out = run / "delivery"
        P.package_run(run, out, producers=fixture_producers(record))
        victim = "06 - Trailer 90s.mp4"
        (out / victim).unlink()
        receipt = json.loads((out / "delivery-receipt.json").read_text())
        receipt["delivery_clips"] = [r for r in receipt["delivery_clips"]
                                     if r.get("file") != victim]
        (out / "delivery-receipt.json").write_text(json.dumps(receipt))
        verdict, detail = dc.check_clips(out, run_dir=run)
        self.assertEqual(verdict, "FAIL")
        self.assertIn(victim, detail)
        self.assertIn("clips", C.verify_folder(
            out, chosen_length_s=180, campaign_run=True)["missing"])

    def test_separate_export_keeps_the_merged_receipt_and_readme(self):
        run, record = self._setup("pack-export", plain_timeline(),
                                  length="3 minutes + 60s and 90s clips")
        out = self.tmp / "export"
        res = P.package_run(run, out, producers=fixture_producers(record))
        self.assertEqual(res["folder"], str(out))
        self.assertTrue((out / "delivery-receipt.json").is_file())
        self.assertTrue((out / "README.md").is_file())
        self.assertIn("delivery_clips",
                      json.loads((out / "delivery-receipt.json").read_text()))

    def test_internal_cost_report_never_ships_in_the_client_folder(self):
        run, record = self._setup("pack-cost", plain_timeline(),
                                  length="3 minutes + 60s and 90s clips")
        out = run / "delivery"
        out.mkdir(parents=True, exist_ok=True)
        (out / "cost-report.json").write_text('{"internal": "cost"}')
        with self.assertRaises(P.PackageError) as ctx:
            P.package_run(run, out, producers=fixture_producers(record))
        self.assertEqual(ctx.exception.code, "PACKAGE_INCOMPLETE")
        self.assertIn(C.DELIVERY_FOLDER_NOT_CLEAN, str(ctx.exception))
        self.assertIn("cost-report.json", str(ctx.exception))
        self.assertTrue((out / "cost-report.json").is_file())   # never deleted

    def test_a_stale_caller_context_is_refused_before_producers(self):
        run, record = self._setup("pack-changed", campaign_timeline(),
                                  length="3 minutes", purpose=1)
        stale = dict(RI.delivery_context(run))           # the caller's reading
        stale["chosen_length_s"] = 300                   # moved under the call
        out = self.tmp / "changed-export"
        with self.assertRaises(P.PackageError) as ctx:
            P.package_run(run, out, producers=fixture_producers(record),
                          context=stale)
        self.assertEqual(ctx.exception.code, "RUN_CONTEXT_MISMATCH")
        self.assertIn("chosen_length_s", str(ctx.exception))
        self.assertEqual(record["called"], [])
        self.assertFalse(out.exists(), "nothing may reach the client folder")
        self.assertFalse((run / "delivery").exists(),
                         "no producer may run on a mismatched context")

    def test_a_foreign_context_cannot_choose_items_or_skip_producers(self):
        run, record = self._setup("pack-foreign", campaign_timeline(),
                                  length="3 minutes", purpose=1)
        actual = RI.delivery_context(run)
        foreign = dict(actual)
        foreign["run_id"] = "another-run"                # same length/campaign
        foreign["items"] = ()                            # way to owe nothing
        out = self.tmp / "foreign-export"
        with self.assertRaises(P.PackageError) as ctx:
            P.package_run(run, out, producers=fixture_producers(record),
                          context=foreign)
        self.assertEqual(ctx.exception.code, "RUN_CONTEXT_MISMATCH")
        self.assertIn("run_id", str(ctx.exception))
        self.assertIn("items", str(ctx.exception))
        self.assertEqual(record["called"], [])
        self.assertFalse(out.exists())
        self.assertFalse((run / "delivery").exists())

    def test_a_matching_caller_context_is_accepted_but_never_chooses_items(self):
        run, record = self._setup("pack-agree", plain_timeline(),
                                  length="3 minutes + 60s and 90s clips")
        supplied = RI.delivery_context(run)
        out = run / "delivery"
        res = P.package_run(run, out, producers=fixture_producers(record),
                            context=supplied)
        self.assertEqual(len(res["items"]), 12)
        self.assertEqual([r["file"] for r in json.loads(
            (out / "delivery-receipt.json").read_text())["delivery_clips"]],
            ["06 - Clip 60s.mp4", "06 - Clip 90s.mp4"])

    def test_source_map_with_no_source_keys_is_refused(self):
        run, record = self._setup("pack-nokeys", campaign_timeline(),
                                  length="3 minutes", purpose=1)
        out = run / "delivery"
        P.package_run(run, out, producers=fixture_producers(record))
        receipt_path = out / "delivery-receipt.json"
        receipt = json.loads(receipt_path.read_text())
        for row in receipt["delivery_clips"]:
            row["source_map"] = [{"trailer_in": 0.0,
                                  "trailer_out": float(row["clip_length_s"])}]
        receipt_path.write_text(json.dumps(receipt))
        verdict, detail = dc.check_clips(out, run_dir=run)
        self.assertEqual(verdict, "FAIL", detail)
        self.assertIn("source_in key", detail)
        code, payload = cli_check(out, run)
        self.assertEqual(code, 5)
        self.assertEqual(payload["verdict"], "FAIL")
        self.assertIn("source_in key", payload["detail"])

    def test_source_map_of_only_null_end_cards_is_refused(self):
        run, record = self._setup("pack-allnull", campaign_timeline(),
                                  length="3 minutes", purpose=1)
        out = run / "delivery"
        P.package_run(run, out, producers=fixture_producers(record))
        receipt_path = out / "delivery-receipt.json"
        receipt = json.loads(receipt_path.read_text())
        for row in receipt["delivery_clips"]:
            row["source_map"] = [{"source_in": None, "source_out": None,
                                  "trailer_in": 0.0,
                                  "trailer_out": float(row["clip_length_s"])}]
        receipt_path.write_text(json.dumps(receipt))
        verdict, detail = dc.check_clips(out, run_dir=run)
        self.assertEqual(verdict, "FAIL", detail)
        self.assertIn("no source window", detail)

    def test_an_explicit_null_end_card_beside_a_real_window_is_allowed(self):
        run, record = self._setup("pack-endcard", campaign_timeline(),
                                  length="3 minutes", purpose=1)
        out = run / "delivery"
        P.package_run(run, out, producers=fixture_producers(record))
        receipt_path = out / "delivery-receipt.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["delivery_clips"][0]["source_map"] = [
            {"source_in": 2.0, "source_out": 12.0,
             "trailer_in": 0.0, "trailer_out": 10.0},
            {"source_in": None, "source_out": None,
             "trailer_in": 10.0, "trailer_out": 13.0}]
        receipt_path.write_text(json.dumps(receipt))
        verdict, detail = dc.check_clips(out, run_dir=run)
        self.assertEqual(verdict, "PASS", detail)

    def test_source_map_builder_requires_keys_and_a_real_window(self):
        with self.assertRaises(dc.DeliveryClipsError) as ctx:
            dc.source_map({"name": "trailer-60s", "pieces": [
                {"source_in": 0.0, "trailer_in": 0.0, "trailer_out": 1.0}]})
        self.assertIn("TRAILER_SOURCE_MAP_INCOMPLETE", str(ctx.exception))
        with self.assertRaises(dc.DeliveryClipsError) as ctx:
            dc.source_map({"name": "trailer-60s", "pieces": [
                {"source_in": None, "source_out": None,
                 "trailer_in": 0.0, "trailer_out": 3.0}]})
        self.assertIn("TRAILER_NO_SOURCE_WINDOW", str(ctx.exception))

    def test_refusal_leaves_the_produced_sources_untouched(self):
        run, record = self._setup("pack-hash", campaign_timeline(),
                                  length="3 minutes", purpose=1)
        before = run_hashes(run)
        with self.assertRaises(P.PackageError) as ctx:
            P.package_run(run, run / "delivery",
                          producers=fixture_producers(record), run_id="another-run")
        self.assertEqual(ctx.exception.code, "RUN_CONTEXT_UNVERIFIED")
        self.assertEqual(run_hashes(run), before)
        self.assertFalse((run / "delivery").exists())


class CommandLine(MediaBoundary):
    """The ACTUAL command line must own a run, never judge a folder alone."""

    def _setup(self, name, timeline, *, length, purpose=None):
        run = self.tmp / name
        build_run(run, length=length, purpose=purpose)
        write_run_files(run, timeline)
        record = {"root": self.tmp / (name + "-items"), "called": []}
        record["root"].mkdir(parents=True, exist_ok=True)
        return run, record

    def test_check_refuses_a_context_free_invocation(self):
        run, record = self._setup("cli-norun", campaign_timeline(),
                                  length="3 minutes", purpose=1)
        out = run / "delivery"
        P.package_run(run, out, producers=fixture_producers(record))
        with self.assertRaises(SystemExit) as ctx:
            with redirect_stderr(io.StringIO()):
                dc.main(["--delivery", str(out), "--check"])
        self.assertEqual(ctx.exception.code, 2)

    def test_check_refuses_an_unverified_run(self):
        bare = self.tmp / "bare-run"
        bare.mkdir()
        code, payload = cli_check(self.tmp / "no-delivery", bare)
        self.assertEqual(code, 5)
        self.assertEqual(payload["verdict"], "FAIL")
        self.assertIn("CLIPS_RUN_AUTHORITY_UNVERIFIED", payload["detail"])

    def test_check_fails_when_both_trailers_and_rows_are_gone_ads_remain(self):
        run, record = self._setup("cli-missing", campaign_timeline(),
                                  length="3 minutes", purpose=1)
        out = run / "delivery"
        P.package_run(run, out, producers=fixture_producers(record))
        gone = ("06 - Trailer 60s.mp4", "06 - Trailer 90s.mp4")
        for name in gone:
            (out / name).unlink()
        rp = out / "delivery-receipt.json"
        receipt = json.loads(rp.read_text())
        receipt["delivery_clips"] = [r for r in receipt["delivery_clips"]
                                     if r.get("file") not in gone]
        rp.write_text(json.dumps(receipt))
        for name in ("13 - Ad 60s.mp4", "13 - Ad 90s.mp4"):
            self.assertTrue((out / name).is_file(), name)
        code, payload = cli_check(out, run)
        self.assertEqual(code, 5)
        self.assertEqual(payload["verdict"], "FAIL")
        self.assertIn(gone[0], payload["detail"])

    def test_valid_short_long_and_campaign_neighbours_pass(self):
        cases = (("cli-60", plain_timeline(), "60 seconds", None),
                 ("cli-180", plain_timeline(),
                  "3 minutes + 60s and 90s clips", None),
                 ("cli-campaign", campaign_timeline(), "3 minutes", 1))
        for name, timeline, length, purpose in cases:
            with self.subTest(run=name):
                run, record = self._setup(name, timeline, length=length,
                                          purpose=purpose)
                out = run / "delivery"
                P.package_run(run, out, producers=fixture_producers(record))
                code, payload = cli_check(out, run)
                self.assertEqual(code, 0, payload)
                self.assertEqual(payload["verdict"], "PASS")


#: the four numbers a method source map records per piece. Every one of them
#: is a boundary the checker compares, so every one of them is tested.
PIECE_COORDINATES = ("source_in", "source_out", "trailer_in", "trailer_out")

#: malformed coordinate values a receipt can actually carry. ``json.dumps``
#: writes the NaN/Infinity literals and ``json.loads`` reads them back, so
#: these reach the checker exactly as an edited receipt would; ``bool`` is an
#: int subclass and must be refused before any arithmetic.
BAD_COORDINATES = (
    ("nan", float("nan")),
    ("positive infinity", float("inf")),
    ("negative infinity", float("-inf")),
    ("negative", -1.0),
    ("bool", True),
)


class SourceMapCoordinates(MediaBoundary):
    """A method source map's four coordinates are real finite boundaries.

    The pre-fix checker compared ``end <= start`` directly, and NaN and both
    infinities compare false against themselves -- a confirmed campaign whose
    receipt carried a NaN source window was handed back PASS by the actual
    command line. Negative coordinates and reversed/zero ranges went through
    the same gate. The valid end card and the valid windows must still pass.
    """

    def _packed_campaign(self, name):
        """A REAL confirmed campaign run packaged through the REAL producer."""
        run = self.tmp / name
        build_run(run, length="3 minutes", purpose=1)
        write_run_files(run, campaign_timeline())
        record = {"root": self.tmp / (name + "-items"), "called": []}
        record["root"].mkdir(parents=True, exist_ok=True)
        out = run / "delivery"
        P.package_run(run, out, producers=fixture_producers(record))
        self.assertEqual(dc.check_clips(out, run_dir=run)[0], "PASS")
        return run, out

    def test_cli_refuses_every_non_finite_and_negative_coordinate(self):
        """Data-driven over all four coordinates: the CLI must say FAIL, not PASS."""
        run, out = self._packed_campaign("coord-cli")
        receipt_path = out / "delivery-receipt.json"
        pristine = receipt_path.read_text(encoding="utf-8")
        for key in PIECE_COORDINATES:
            for label, value in BAD_COORDINATES:
                with self.subTest(coordinate=key, value=label):
                    receipt_path.write_text(pristine, encoding="utf-8")
                    receipt = json.loads(receipt_path.read_text())
                    receipt["delivery_clips"][0]["source_map"][0][key] = value
                    receipt_path.write_text(json.dumps(receipt))
                    code, payload = cli_check(out, run)
                    self.assertEqual(code, 5, payload)
                    self.assertEqual(payload["verdict"], "FAIL")
                    self.assertIn(key, payload["detail"])
        receipt_path.write_text(pristine, encoding="utf-8")
        self.assertEqual(cli_check(out, run)[0], 0)

    def test_cli_refuses_reversed_and_zero_width_ranges(self):
        run, out = self._packed_campaign("coord-range")
        receipt_path = out / "delivery-receipt.json"
        pristine = receipt_path.read_text(encoding="utf-8")
        cases = (
            ("source_in", "source_out", 10.0, 10.0),
            ("source_in", "source_out", 12.0, 10.0),
            ("trailer_in", "trailer_out", 5.0, 5.0),
            ("trailer_in", "trailer_out", 6.0, 5.0),
        )
        for begin_key, end_key, begin_value, end_value in cases:
            with self.subTest(range=(begin_key, end_key, begin_value,
                                     end_value)):
                receipt_path.write_text(pristine, encoding="utf-8")
                receipt = json.loads(receipt_path.read_text())
                piece = receipt["delivery_clips"][0]["source_map"][0]
                piece[begin_key], piece[end_key] = begin_value, end_value
                receipt_path.write_text(json.dumps(receipt))
                code, payload = cli_check(out, run)
                self.assertEqual(code, 5, payload)
                self.assertEqual(payload["verdict"], "FAIL")
        receipt_path.write_text(pristine, encoding="utf-8")
        self.assertEqual(cli_check(out, run)[0], 0)

    def test_valid_zero_start_and_end_card_survive_the_new_bounds(self):
        run, out = self._packed_campaign("coord-valid")
        receipt_path = out / "delivery-receipt.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["delivery_clips"][0]["source_map"] = [
            {"source_in": 0.0, "source_out": 12.0,
             "trailer_in": 0.0, "trailer_out": 10.0},
            {"source_in": None, "source_out": None,
             "trailer_in": 10.0, "trailer_out": 13.0}]
        receipt_path.write_text(json.dumps(receipt))
        code, payload = cli_check(out, run)
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["verdict"], "PASS")

    def test_builder_refuses_bad_coordinates_before_any_render(self):
        base = {"source_in": 2.0, "source_out": 12.0,
                "trailer_in": 0.0, "trailer_out": 10.0}
        for key in PIECE_COORDINATES:
            for label, value in BAD_COORDINATES:
                with self.subTest(coordinate=key, value=label):
                    piece = dict(base)
                    piece[key] = value
                    with self.assertRaises(dc.DeliveryClipsError) as ctx:
                        dc.source_map({"name": "trailer-60s",
                                       "pieces": [piece]})
                    self.assertIn("TRAILER_SOURCE_MAP_INVALID",
                                  str(ctx.exception))
        for label, value in BAD_COORDINATES:
            with self.subTest(single_window=label):
                with self.assertRaises(dc.DeliveryClipsError) as ctx:
                    dc.source_map({"name": "trailer-60s", "start_s": value,
                                   "end_s": 10.0, "trailer_in": 0.0,
                                   "trailer_out": 5.0})
                self.assertIn("TRAILER_SOURCE_MAP_INVALID", str(ctx.exception))

    def test_builder_keeps_valid_zero_start_and_end_card(self):
        pieces = [{"source_in": 0.0, "source_out": 12.0,
                   "trailer_in": 0.0, "trailer_out": 10.0},
                  {"source_in": None, "source_out": None,
                   "trailer_in": 10.0, "trailer_out": 13.0}]
        self.assertEqual(
            dc.source_map({"name": "trailer-60s", "pieces": pieces}),
            pieces)


if __name__ == "__main__":
    unittest.main(verbosity=2)
