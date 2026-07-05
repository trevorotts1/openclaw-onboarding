#!/usr/bin/env python3
"""
test_ad_preflight.py — NEGATIVE-TEST SUITE for the Facebook & Instagram Ad gates.

================================================================================
For EVERY autofail in AD-PIPELINE-MANIFEST.json whose enforced_by == "ad_director",
this suite builds a deliberately-failing run dir, calls the enforcing checker, and
asserts it TRIGGERS (returns a fatal string carrying the AF code). It ALSO builds a
GOOD run dir and asserts the checker PASSES. It then emits working/af-coverage.json
listing every AF code a failing fixture actually tripped — the file Guard A
(ad_gate_integrity_check.py) consumes to prove "declared == enforced == tested".

It also directly probes the two non-checker gates: AF-FBAD-KIE-BALANCE (the Phase-0
balance preflight, via an unreachable endpoint) and AF-FBAD-DEP-SKIPPED (the
dependency-map driver gate, via dispatching a phase with no dependency attested).

Mirrors the Movie Producer test_video_preflight.py / af-coverage contract.

EXIT CODES:
    0 — every gate fixture behaved (negative tripped, positive passed); af-coverage emitted.
    1 — a gate did not trip on its failing fixture, or rejected its passing fixture.
"""

import copy
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ad_build_check as abc  # noqa: E402
import ad_director as ad      # noqa: E402

AF_COVERAGE = HERE / "working" / "af-coverage.json"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------
def _mk_run(tmp: Path) -> Path:
    rd = Path(tempfile.mkdtemp(dir=tmp))
    (rd / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "qc").mkdir(parents=True, exist_ok=True)
    return rd


def _write(rd: Path, rel: str, obj) -> None:
    p = rd / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, (dict, list)):
        p.write_text(json.dumps(obj, indent=2))
    else:
        p.write_text(str(obj))


_PAD = " padding to clear the 256-byte deliverable size floor for the bundle check;"


def _good_qc(maker: str, grader: str, session_id: str = "sess-default") -> dict:
    return {
        "categories": {"rules": 9.0, "mission": 9.0, "craft": 8.5, "clarity": 9.0,
                       "variety": 8.5},
        "average": 8.8,  # == the average computed from the categories above (44/5)
        "pass": True,
        "maker": maker,
        "grader": grader,
        "grader_session_id": session_id,
        "independent": True,
    }


# The registered QC/reviewer role slugs (AD-PIPELINE-MANIFEST roles[].id) a grade may
# name; the ledger's qc_sessions[] ties each scorecard back to a real grading session.
_QC_ROLE = "qc-role--paid-advertisement"
_DEVILS = "devils-advocate--paid-advertisement"
_QC_SESSIONS = [
    {"gate": "copy", "grader": _QC_ROLE, "session_id": "sess-copy-01"},
    {"gate": "prompt", "grader": _QC_ROLE, "session_id": "sess-prompt-01"},
    {"gate": "image", "grader": _QC_ROLE, "session_id": "sess-image-01"},
    {"gate": "targeting", "grader": _QC_ROLE, "session_id": "sess-targeting-01"},
    {"gate": "package", "grader": _DEVILS, "session_id": "sess-package-01"},
]


def _good(rd: Path) -> None:
    """Lay down a COMPLETE, valid run dir — every receipt + scorecard passes every
    checker. Each BAD case calls this then corrupts exactly one receipt."""
    _write(rd, "working/job-manifest.json", {
        "brief_complete": True,
        "job_id": "fbad-good-001",
        "show_name": "A Real Show",
        "audience_profile_ref": "working/inputs/audience.md",
        "money_ceiling_usd": 5.0,
        "estimated_cost_usd": 0.65,
        "cost_estimate_approved": True,
        "owner": "Owner Name",
        "_pad": _PAD * 4,
    })
    _write(rd, "working/checkpoints/ad_run_ledger.json", {
        "run_id": "fbad-good-001",
        "spent_usd": 0.50,
        "events": [{"kind": "image", "idx": i, "task_id": f"tid{i}", "usd": 0.05}
                   for i in range(10)],
        # the conductor's independent record of each grading session it dispatched
        "qc_sessions": [dict(s) for s in _QC_SESSIONS],
    })
    # S1 overlays
    _write(rd, "working/s1-overlays.md", "# 70 overlays (fixture)\n" + "\n".join(
        f"{i+1}. punchy guest spotlight overlay line {i+1}" for i in range(70)))
    _write(rd, "working/checkpoints/s1-receipt.json", {
        "overlay_count": 70,
        "word_counts": [6] * 70,
        "top_line_present": True,
        "on_mission": True,
        "audience_wording_preserved": True,
    })
    # PICK-10
    _write(rd, "working/s1-selection.json", {
        "selection": list(range(1, 11)),
        "overlay_count": 70,
    })
    # S2 bodies
    _write(rd, "working/s2-primary-text.md", "# 10 bodies (fixture)\n")
    _write(rd, "working/checkpoints/s2-receipt.json", {
        "body_count": 10,
        "bodies": [{"hook_chars": 110, "cta_count": 3, "emoji_count": 3}
                   for _ in range(10)],
    })
    # S3 headlines
    _write(rd, "working/s3-headlines.md", "# 10 headlines (fixture)\n")
    _write(rd, "working/checkpoints/s3-receipt.json", {
        "headline_count": 10,
        "headlines": [{"shape": abc.HEADLINE_SHAPES_LOCKED[i % 4]} for i in range(10)],
    })
    # S4 image prompts
    _write(rd, "working/s4-image-prompts.md", "# 10 image prompts (fixture)\n")
    _write(rd, "working/checkpoints/s4-receipt.json", {
        "prompt_count": 10,
        "prompts": [{"char_count": 6000, "sections": list(abc.PROMPT_BUILD_ORDER),
                     "styleblock_ok": True, "baked_text_present": True}
                    for _ in range(10)],
    })
    # S5 images
    _write(rd, "working/checkpoints/s5-image-receipt.json", {
        "image_count": 10,
        "images": [{"kie_task_id": f"a27542cb60343417e562afc2be65da{i:02d}",
                    "width": 1500, "height": 1500,
                    "model": "gpt-image-2-text-to-image", "would_cross": False}
                   for i in range(10)],
        "_pad": _PAD * 2,
    })
    # S6 targeting
    group = {
        "name": "Core fans",
        "explanation": "People who already follow this kind of show — warmest tier.",
        "layer1": [{"name": "Podcasts", "resolved": True, "meta_id": "6003020834693"}],
        "layer2": [{"name": "Audiobooks", "resolved": True, "meta_id": "6003123299417"}],
        "layer3": [{"name": "Self improvement", "resolved": True, "meta_id": "6002868910910"}],
    }
    _write(rd, "working/checkpoints/s6-targeting.json", {
        "groups": [copy.deepcopy(group) for _ in range(3)],
    })
    _write(rd, "working/checkpoints/s6-targeting-brief.md", "# targeting brief (fixture)\n")
    # S7 deliver
    _write(rd, "working/checkpoints/s7-deliver-receipt.json", {
        "counts": {"selection": 10, "bodies": 10, "headlines": 10,
                   "prompts": 10, "images": 10},
        "delivered": [{"image_url": f"https://storage.googleapis.com/msgsndr/loc/ad{i}.png",
                       "http_status": 200} for i in range(10)],
        "adtext_block_pairs": 10,
        "adtext_matches_copy": True,
        "campaign_id": "fbad-good-001",
        "_pad": _PAD * 2,
    })
    _write(rd, "working/s7-plai-brief.json", {
        "campaign_name": "A Real Show — guest recruit",
        "objective": "OUTCOME_TRAFFIC",
        "image_links": [f"https://storage.googleapis.com/msgsndr/loc/ad{i}.png"
                        for i in range(10)],
        "primary_texts": ["body " + str(i) for i in range(10)],
        "headlines": ["headline " + str(i) for i in range(10)],
        "targeting_groups": [group["name"]],
        "placements": ["facebook_feed", "instagram_feed"],
        "destination_url": "https://example-show.com/apply",
        "_pad": _PAD * 2,
    })
    # PUBLISH
    _write(rd, "working/checkpoints/approval-receipt.json", {
        "approved_by": "Owner Name",
        "approval_received_at": "2026-06-25T18:00:00-0400",
        "owner_confirmed": True,
    })
    # QC scorecards (Gate A..E) — independent (grader != maker), graders are REGISTERED
    # role slugs, and each grader_session_id ties back to the ledger's qc_sessions[].
    _write(rd, "working/qc/copy-qc.json",
           _good_qc("direct-response-ad-copywriter", _QC_ROLE, "sess-copy-01"))
    _write(rd, "working/qc/prompt-qc.json",
           _good_qc("ai-image-generator-specialist", _QC_ROLE, "sess-prompt-01"))
    _write(rd, "working/qc/image-qc.json",
           _good_qc("ai-image-generator-specialist", _QC_ROLE, "sess-image-01"))
    _write(rd, "working/qc/targeting-qc.json",
           _good_qc("audience-research-specialist", _QC_ROLE, "sess-targeting-01"))
    _write(rd, "working/qc/package-qc.json",
           _good_qc("facebook-ads-specialist", _DEVILS, "sess-package-01"))


def _load(rd: Path, rel: str) -> dict:
    return json.loads((rd / rel).read_text())


# ---- per-case BAD mutators (each starts from a full _good run) -------------
def _bad_brief(rd):
    _good(rd)
    _write(rd, "working/job-manifest.json", {"brief_complete": True, "job_id": "x"})


def _bad_cost(rd):
    _good(rd)
    jm = _load(rd, "working/job-manifest.json")
    jm.update({"estimated_cost_usd": 99.0, "money_ceiling_usd": 5.0,
               "cost_estimate_approved": True})
    _write(rd, "working/job-manifest.json", jm)


def _bad_ledger(rd):
    _good(rd)
    led = _load(rd, "working/checkpoints/ad_run_ledger.json")
    led["run_id"] = "DIFFERENT-RUN-ID"
    _write(rd, "working/checkpoints/ad_run_ledger.json", led)


def _bad_overlay_count(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s1-receipt.json")
    r["overlay_count"] = 50
    _write(rd, "working/checkpoints/s1-receipt.json", r)


def _bad_overlay_wc(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s1-receipt.json")
    r["word_counts"][3] = 40
    _write(rd, "working/checkpoints/s1-receipt.json", r)


def _bad_topline(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s1-receipt.json")
    r["top_line_present"] = False
    _write(rd, "working/checkpoints/s1-receipt.json", r)


def _bad_on_mission(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s1-receipt.json")
    r["on_mission"] = False
    _write(rd, "working/checkpoints/s1-receipt.json", r)


def _bad_audience(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s1-receipt.json")
    r["audience_wording_preserved"] = False
    _write(rd, "working/checkpoints/s1-receipt.json", r)


def _bad_copy_qc(rd):
    _good(rd)
    sc = _good_qc("direct-response-ad-copywriter", "ad-quality-reviewer")
    sc.update({"categories": {"rules": 9.0, "mission": 4.0, "craft": 9.0}, "average": 7.3,
               "pass": False})
    _write(rd, "working/qc/copy-qc.json", sc)


def _bad_selection_count(rd):
    _good(rd)
    _write(rd, "working/s1-selection.json", {"selection": [1, 2, 3, 4, 5], "overlay_count": 70})


def _bad_selection_subset(rd):
    _good(rd)
    _write(rd, "working/s1-selection.json",
           {"selection": [1, 2, 3, 4, 5, 6, 7, 8, 9, 200], "overlay_count": 70})


def _bad_body_hook(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s2-receipt.json")
    r["bodies"][2]["hook_chars"] = 240
    _write(rd, "working/checkpoints/s2-receipt.json", r)


def _bad_body_cta(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s2-receipt.json")
    r["bodies"][2]["cta_count"] = 1
    _write(rd, "working/checkpoints/s2-receipt.json", r)


def _bad_body_emoji(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s2-receipt.json")
    r["bodies"][2]["emoji_count"] = 99
    _write(rd, "working/checkpoints/s2-receipt.json", r)


def _bad_headline(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s3-receipt.json")
    r["headlines"][4]["shape"] = "clickbait-shock"
    _write(rd, "working/checkpoints/s3-receipt.json", r)


def _bad_prompt_order(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s4-receipt.json")
    r["prompts"][1]["sections"] = ["subject", "composition"]
    _write(rd, "working/checkpoints/s4-receipt.json", r)


def _bad_prompt_richness(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s4-receipt.json")
    r["prompts"][1]["char_count"] = 200
    _write(rd, "working/checkpoints/s4-receipt.json", r)


def _bad_prompt_styleblock(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s4-receipt.json")
    r["prompts"][1]["styleblock_ok"] = False
    _write(rd, "working/checkpoints/s4-receipt.json", r)


def _bad_prompt_qc(rd):
    _good(rd)
    sc = _good_qc("ai-image-generator-specialist", "independent-prompt-reviewer")
    sc.update({"average": 7.0, "pass": False})
    _write(rd, "working/qc/prompt-qc.json", sc)


def _bad_image_taskid(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s5-image-receipt.json")
    r["images"][3]["kie_task_id"] = "TASK_ID"
    _write(rd, "working/checkpoints/s5-image-receipt.json", r)


def _bad_image_size(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s5-image-receipt.json")
    r["images"][3]["width"] = 1024
    _write(rd, "working/checkpoints/s5-image-receipt.json", r)


def _bad_image_model(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s5-image-receipt.json")
    r["images"][3]["model"] = "flux-1.1-pro"
    _write(rd, "working/checkpoints/s5-image-receipt.json", r)


def _bad_tally(rd):
    _good(rd)
    led = _load(rd, "working/checkpoints/ad_run_ledger.json")
    led["spent_usd"] = 99.0
    _write(rd, "working/checkpoints/ad_run_ledger.json", led)


def _bad_image_qc(rd):
    _good(rd)
    sc = _good_qc("ai-image-generator-specialist", "independent-vision-reviewer")
    sc.update({"categories": {"legibility": 5.0, "professional": 9.0, "cohesion": 9.0},
               "average": 7.6, "pass": False})
    _write(rd, "working/qc/image-qc.json", sc)


def _bad_targeting_shape(rd):
    _good(rd)
    t = _load(rd, "working/checkpoints/s6-targeting.json")
    t["groups"][0].pop("layer3")
    _write(rd, "working/checkpoints/s6-targeting.json", t)


def _bad_targeting_real(rd):
    _good(rd)
    t = _load(rd, "working/checkpoints/s6-targeting.json")
    t["groups"][0]["layer1"][0] = {"name": "Invented interest", "resolved": False}
    _write(rd, "working/checkpoints/s6-targeting.json", t)


def _bad_targeting_qc(rd):
    _good(rd)
    sc = _good_qc("audience-research-specialist", "independent-targeting-reviewer")
    sc.update({"average": 6.4, "pass": False})
    _write(rd, "working/qc/targeting-qc.json", sc)


def _bad_fanout(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s7-deliver-receipt.json")
    r["counts"]["images"] = 8
    _write(rd, "working/checkpoints/s7-deliver-receipt.json", r)


def _bad_ghl_url(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s7-deliver-receipt.json")
    r["delivered"][5] = {"image_url": "https://placeholder.example.com/x.png",
                         "http_status": 200}
    _write(rd, "working/checkpoints/s7-deliver-receipt.json", r)


def _bad_adtext(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s7-deliver-receipt.json")
    r["adtext_block_pairs"] = 5
    _write(rd, "working/checkpoints/s7-deliver-receipt.json", r)


def _bad_plai(rd):
    _good(rd)
    pb = _load(rd, "working/s7-plai-brief.json")
    pb.pop("destination_url")
    _write(rd, "working/s7-plai-brief.json", pb)


def _bad_board(rd):
    _good(rd)
    r = _load(rd, "working/checkpoints/s7-deliver-receipt.json")
    r["campaign_id"] = ""
    _write(rd, "working/checkpoints/s7-deliver-receipt.json", r)


def _bad_package_qc(rd):
    _good(rd)
    sc = _good_qc("facebook-ads-specialist", "devils-advocate--paid-advertisement")
    sc.update({"average": 8.0, "pass": False})
    _write(rd, "working/qc/package-qc.json", sc)


def _bad_independence(rd):
    _good(rd)
    # self-graded copy scorecard (grader == maker)
    sc = _good_qc("direct-response-ad-copywriter", "direct-response-ad-copywriter")
    _write(rd, "working/qc/copy-qc.json", sc)


def _bad_approve(rd):
    _good(rd)
    _write(rd, "working/checkpoints/approval-receipt.json",
           {"approved_by": "Owner Name", "approval_received_at": "2026-06-25T18:00:00Z",
            "owner_confirmed": False})


def _bad_qc_declared_lie(rd):
    """FIX-XC-03i: a SELF-DECLARED average may never override the computed one. Every
    category is 7.0 (computes to 7.0, all above the 7.0 category floor) but the
    scorecard declares 9.9 — the >0.05 declared-vs-computed disagreement must autofail,
    NOT sail through on the fabricated 9.9."""
    _good(rd)
    sc = _good_qc("direct-response-ad-copywriter", _QC_ROLE, "sess-copy-01")
    sc["categories"] = {"rules": 7.0, "mission": 7.0, "craft": 7.0, "clarity": 7.0}
    sc["average"] = 9.9
    _write(rd, "working/qc/copy-qc.json", sc)


def _bad_overlay_measured(rd):
    """FIX-XC-03i: MEASURE the source file. The receipt keeps every word_count at 6
    (all in-range, so the range check passes), but the real s1-overlays.md has an
    over-long line — the receipt-vs-measured mismatch must trip."""
    _good(rd)
    lines = ["# 70 overlays (fixture)"]
    for i in range(70):
        if i == 3:
            lines.append(f"{i+1}. " + " ".join(["word"] * 25))  # 25 words, receipt says 6
        else:
            lines.append(f"{i+1}. punchy guest spotlight overlay line {i+1}")  # 6 words
    _write(rd, "working/s1-overlays.md", "\n".join(lines) + "\n")


def _bad_qc_unregistered_grader(rd):
    """FIX-S36-45(iii): a grade must name REGISTERED role slugs, not free text."""
    _good(rd)
    sc = _good_qc("direct-response-ad-copywriter", "some-freetext-reviewer", "sess-copy-01")
    _write(rd, "working/qc/copy-qc.json", sc)


def _bad_qc_no_ledger_session(rd):
    """FIX-S36-45(iii): a scorecard whose grading session the run ledger never recorded
    is a self-attested grade — the ledger tie-back must fail closed."""
    _good(rd)
    led = _load(rd, "working/checkpoints/ad_run_ledger.json")
    led["qc_sessions"] = [s for s in led.get("qc_sessions", []) if s.get("gate") != "copy"]
    _write(rd, "working/checkpoints/ad_run_ledger.json", led)


# Each entry: (af_code, checker_name, make_bad, make_good)
CASES = [
    ("AF-FBAD-BRIEF-INCOMPLETE", "_chk_brief_complete", _bad_brief, _good),
    ("AF-FBAD-COST-CEILING", "_chk_cost_ceiling", _bad_cost, _good),
    ("AF-FBAD-RECEIPT-NAMESPACE", "_chk_run_ledger", _bad_ledger, _good),
    ("AF-FBAD-OVERLAY-COUNT", "_chk_overlay_count", _bad_overlay_count, _good),
    ("AF-FBAD-OVERLAY-WORDCOUNT", "_chk_overlay_wordcount", _bad_overlay_wc, _good),
    ("AF-FBAD-OVERLAY-TOPLINE", "_chk_overlay_topline", _bad_topline, _good),
    ("AF-FBAD-ON-MISSION", "_chk_on_mission", _bad_on_mission, _good),
    ("AF-FBAD-AUDIENCE-WORDING", "_chk_audience_wording", _bad_audience, _good),
    ("AF-FBAD-COPY-QC", "_chk_copy_qc", _bad_copy_qc, _good),
    ("AF-FBAD-SELECTION-COUNT", "_chk_selection_count", _bad_selection_count, _good),
    ("AF-FBAD-SELECTION-SUBSET", "_chk_selection_subset", _bad_selection_subset, _good),
    ("AF-FBAD-BODY-HOOK", "_chk_body_hook", _bad_body_hook, _good),
    ("AF-FBAD-BODY-CTA", "_chk_body_cta", _bad_body_cta, _good),
    ("AF-FBAD-BODY-EMOJI", "_chk_body_emoji", _bad_body_emoji, _good),
    ("AF-FBAD-HEADLINE-SHAPE", "_chk_headline_shape", _bad_headline, _good),
    ("AF-FBAD-PROMPT-ORDER", "_chk_prompt_order", _bad_prompt_order, _good),
    ("AF-FBAD-PROMPT-RICHNESS", "_chk_prompt_richness", _bad_prompt_richness, _good),
    ("AF-FBAD-PROMPT-STYLEBLOCK", "_chk_prompt_styleblock", _bad_prompt_styleblock, _good),
    ("AF-FBAD-PROMPT-QC", "_chk_prompt_qc", _bad_prompt_qc, _good),
    ("AF-FBAD-IMAGE-TASKID", "_chk_image_taskid", _bad_image_taskid, _good),
    ("AF-FBAD-IMAGE-SIZE", "_chk_image_size", _bad_image_size, _good),
    ("AF-FBAD-IMAGE-MODEL", "_chk_image_model", _bad_image_model, _good),
    ("AF-FBAD-TALLY-CROSS", "_chk_tally_ceiling", _bad_tally, _good),
    ("AF-FBAD-IMAGE-QC", "_chk_image_qc", _bad_image_qc, _good),
    ("AF-FBAD-TARGETING-SHAPE", "_chk_targeting_shape", _bad_targeting_shape, _good),
    ("AF-FBAD-TARGETING-REAL", "_chk_targeting_real", _bad_targeting_real, _good),
    ("AF-FBAD-TARGETING-QC", "_chk_targeting_qc", _bad_targeting_qc, _good),
    ("AF-FBAD-FANOUT", "_chk_fanout", _bad_fanout, _good),
    ("AF-FBAD-GHL-URL", "_chk_ghl_url", _bad_ghl_url, _good),
    ("AF-FBAD-ADTEXT-DOC", "_chk_adtext_doc", _bad_adtext, _good),
    ("AF-FBAD-PLAI-FIELDS", "_chk_plai_fields", _bad_plai, _good),
    ("AF-FBAD-BOARD", "_chk_board", _bad_board, _good),
    ("AF-FBAD-PACKAGE-QC", "_chk_package_qc", _bad_package_qc, _good),
    ("AF-FBAD-QC-INDEPENDENCE", "_chk_qc_independence", _bad_independence, _good),
    ("AF-FBAD-APPROVE", "_chk_approve", _bad_approve, _good),
    # FIX-XC-03i — computed average wins; MEASURE the artifact.
    ("AF-FBAD-COPY-QC", "_chk_copy_qc", _bad_qc_declared_lie, _good),
    ("AF-FBAD-OVERLAY-WORDCOUNT", "_chk_overlay_wordcount", _bad_overlay_measured, _good),
    # FIX-S36-45(iii) — registered role slugs + run-ledger session tie-back.
    ("AF-FBAD-QC-INDEPENDENCE", "_chk_qc_independence", _bad_qc_unregistered_grader, _good),
    ("AF-FBAD-QC-INDEPENDENCE", "_chk_qc_independence", _bad_qc_no_ledger_session, _good),
]


# ---- direct probes for the two non-checker gates --------------------------
def _probe_kie_balance() -> bool:
    """Trigger AF-FBAD-KIE-BALANCE via an unverifiable balance (unreachable endpoint)."""
    orig = abc.FBAD_KIE_CREDIT_URL
    try:
        abc.FBAD_KIE_CREDIT_URL = "http://127.0.0.1:0/nope"
        with tempfile.TemporaryDirectory() as tmp:
            rd = Path(tmp)
            (rd / "working" / "checkpoints").mkdir(parents=True)
            reason = abc.kie_balance_preflight(rd, estimated_cost_usd=0.65,
                                               api_key="dummy-key-not-real")
        return "AF-FBAD-KIE-BALANCE" in reason
    finally:
        abc.FBAD_KIE_CREDIT_URL = orig


def _probe_dep_skipped() -> bool:
    """Trigger AF-FBAD-DEP-SKIPPED: dispatch S5-IMAGE-GEN with no dependency attested."""
    manifest = ad.load_manifest()
    with tempfile.TemporaryDirectory() as tmp:
        rd = Path(tmp)
        (rd / "working" / "checkpoints").mkdir(parents=True)
        reason = ad.check_dependency_preconditions(rd, manifest["phases"], "S5-IMAGE-GEN")
    return "AF-FBAD-DEP-SKIPPED" in reason


def main():
    triggered = set()
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for code, checker_name, make_bad, make_good in CASES:
            fn = abc.CHECKERS.get(checker_name)
            if fn is None:
                failures.append(f"{code}: checker {checker_name!r} is not defined in "
                                "ad_build_check.CHECKERS.")
                continue
            # NEGATIVE: the failing fixture MUST trip the gate, naming its AF code.
            rd_bad = _mk_run(tmp)
            make_bad(rd_bad)
            reason = fn(rd_bad)
            if not reason:
                failures.append(f"{code}: negative fixture did NOT trip {checker_name} "
                                "(gate is a no-op).")
            elif code not in reason:
                failures.append(f"{code}: {checker_name} tripped but its message does not "
                                f"name {code} (got: {reason[:90]!r}).")
            else:
                triggered.add(code)
            # POSITIVE: the passing fixture MUST pass the gate.
            rd_good = _mk_run(tmp)
            make_good(rd_good)
            ok_reason = fn(rd_good)
            if ok_reason:
                failures.append(f"{code}: POSITIVE fixture was REJECTED by {checker_name} "
                                f"(false positive): {ok_reason[:140]!r}.")

    # The two non-checker gates — probed directly.
    if _probe_kie_balance():
        triggered.add("AF-FBAD-KIE-BALANCE")
    else:
        failures.append("AF-FBAD-KIE-BALANCE: unverifiable-balance fixture did not trip "
                        "kie_balance_preflight.")
    if _probe_dep_skipped():
        triggered.add("AF-FBAD-DEP-SKIPPED")
    else:
        failures.append("AF-FBAD-DEP-SKIPPED: no-dependency fixture did not trip "
                        "check_dependency_preconditions.")

    AF_COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    AF_COVERAGE.write_text(json.dumps({"triggered": sorted(triggered)}, indent=2))

    if failures:
        print("=== test_ad_preflight: FAILURES ===", file=sys.stderr)
        for f in failures:
            print(f"  FAIL: {f}", file=sys.stderr)
        print(f"\n{len(failures)} failure(s). af-coverage emitted with "
              f"{len(triggered)} triggered code(s) at {AF_COVERAGE}.", file=sys.stderr)
        sys.exit(1)

    print("=== test_ad_preflight: ALL GATES BEHAVE (negative tripped, positive passed) ===")
    print(f"triggered AF codes: {len(triggered)}")
    for c in sorted(triggered):
        print(f"  TRIGGERED {c}")
    print(f"af-coverage emitted: {AF_COVERAGE}")
    sys.exit(0)


if __name__ == "__main__":
    main()
