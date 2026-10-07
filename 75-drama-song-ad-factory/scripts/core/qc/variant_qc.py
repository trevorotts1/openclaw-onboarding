#!/usr/bin/env python3
"""variant_qc.py: per-variant QC gate, Plan 9.3 "separate verdicts for each
length and shape" + Plan 9.4 media rule. stdlib only.

One gate call per variant. The variant key is length x shape; the variant's
QC records are bound to a variant-unique stage string, so a record written
for 60s 9:16 can never satisfy the 90s 9:16 gate (STALE_BINDING comes back
from core.qc_gate). Each variant reports its own gate, its own failure
codes, its own repair scope: one variant's PASS never covers another's.

Composition per variant:
- record verdicts via core.qc_gate.evaluate (independent reviewer, schema,
  UNAVAILABLE never PASS, critical defects never averaged away);
- media gate (9.4): a media stage cannot pass without the real file, right
  duration and format, and an inspection receipt;
- creative-fidelity gate (9.3): style in every visual prompt, twelve-beat
  arc, product reveal after the mentor;
- lyric sign-off (9.3): a recorded human decision on the exact lyrics
  before song generation.

Overall gate: PASS only when every sub-gate passes. BLOCKED when the
record gate is structurally broken (same records cannot ever pass).
"""
from __future__ import annotations

try:
    import qc_gate
except ImportError as _e:  # imported as core.qc.variant_qc
    if "qc_gate" not in str(_e):
        raise
    from .. import qc_gate

from .creative_fidelity import check_creative
from .lyric_signoff import check_signoff, lyrics_digest
from .media_gate import check_media

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"

#: Plan 6.1 base lengths + the plan 6.13 / D23 ten-minute long version.
#: Kept equal to core.length_engine.long LENGTHS_S so a variant the length
#: engine offers is never rejected here with UNKNOWN_LENGTH.
LENGTHS = (60, 90, 180, 300, 600)
#: Shapes the delivery/export layer knows (campaign-schema aspects).
SHAPES = ("16:9", "9:16", "1:1")

#: Stages that produce media: no media file, no pass (Plan 9.4).
MEDIA_STAGES = {
    "song": "audio",
    "image": "image",
    "video": "video",
    "assembly": "video",
    "final_edit": "video",
}
#: Stages where creative fidelity (9.3) is required.
CREATIVE_STAGES = frozenset(
    ("storyboard", "image", "video", "assembly", "final_edit"))
#: The song stage is the one that needs the lyric sign-off (9.3): the
#: approval must exist before the song is generated.
SIGNOFF_STAGES = frozenset(("song",))

#: Plan 9.2 checks per stage, fed to core.qc_gate as the required set.
REQUIRED_CHECKS = {
    "storyboard": ("storyboard", "creative"),
    "image": ("creative", "continuity"),
    "song": ("song", "lyrics", "audio"),
    "video": ("video", "creative"),
    "assembly": ("timeline", "audio"),
    "final_edit": ("final_edit", "export", "timeline", "text_product"),
}

CRITICAL_CHECKS = frozenset({"lyrics", "text_product"})


class VariantQCError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def variant_key(length_s, shape):
    """Canonical variant key, e.g. '60s@9:16'. Validates both parts."""
    if isinstance(length_s, bool) or not isinstance(length_s, int) \
            or length_s not in LENGTHS:
        raise VariantQCError(
            "UNKNOWN_LENGTH",
            "length_s %r not in %s" % (length_s, list(LENGTHS)))
    if shape not in SHAPES:
        raise VariantQCError("UNKNOWN_SHAPE",
                             "shape %r not in %s" % (shape, list(SHAPES)))
    return "%ds@%s" % (length_s, shape)


def stage_for(stage, key):
    """Variant-unique stage binding: 'video@60s@9:16'.

    qc_gate rejects a record whose stage differs (STALE_BINDING), which is
    what keeps one variant's verdicts out of another variant's gate.
    """
    if not isinstance(stage, str) or not stage.strip():
        raise VariantQCError("BAD_STAGE", "stage must be a non-empty string")
    return "%s@%s" % (stage, key)


def _split_codes(reason_code):
    return [c for c in (reason_code or "").split("+") if c]


def evaluate_variant(run_id, stage, length_s, shape, case):
    """Run every gate for ONE variant. case is a dict of QC inputs:
    records, makers, required_checks?, media?, creative?, signoff?,
    lyrics_digest?, song_started_at?, produces_media?, requires_creative?,
    requires_signoff?, checker/profile version expectations.
    """
    if not isinstance(case, dict):
        raise VariantQCError("BAD_CASE", "case must be an object")
    key = variant_key(length_s, shape)
    bound_stage = stage_for(stage, key)
    failures = []          # {code, detail, critical}
    sub = {}

    def fail(code, detail, critical=False):
        failures.append({"code": code, "detail": detail,
                         "critical": bool(critical)})

    # --- 1. record verdicts, bound to this variant's stage -------------
    required = case.get("required_checks")
    if required is None:
        required = REQUIRED_CHECKS.get(stage)
    if not required:
        raise VariantQCError(
            "NO_REQUIRED_CHECKS",
            "no required checks for stage %r; pass required_checks" % stage)
    records = case.get("records")
    if records is None:
        records = []
    makers = case.get("makers")
    if makers is None:
        makers = {}
    rec_res = qc_gate.evaluate(
        run_id, bound_stage, records, makers, list(required),
        critical=case.get("critical", CRITICAL_CHECKS),
        profile_version=case.get("profile_version"),
        expected_profile_version=case.get("expected_profile_version"),
        expected_checker_version=case.get("expected_checker_version"))
    sub["records"] = rec_res
    for f in rec_res["failures"]:
        fail(f["code"], f["detail"], f.get("critical", False))

    # --- 2. media file (Plan 9.4) --------------------------------------
    produces_media = case.get("produces_media")
    if produces_media is None:
        produces_media = stage in MEDIA_STAGES
    if produces_media:
        spec = case.get("media")
        if not isinstance(spec, dict):
            fail("MEDIA_REQUIRED",
                 "stage %r produces media; no media file recorded (9.4)"
                 % stage)
            sub["media"] = {"verdict": FAIL, "code": "MEDIA_REQUIRED",
                            "failures": []}
        else:
            hint = MEDIA_STAGES.get(stage)
            res = check_media(spec, kind_hint=hint)
            sub["media"] = res
            for f in res["failures"]:
                fail(f["code"], f["detail"])
    elif case.get("media") is not None:
        fail("MEDIA_NOT_EXPECTED",
             "stage %r does not produce media, a media spec was passed"
             % stage)

    # --- 3. creative fidelity (Plan 9.3) --------------------------------
    requires_creative = case.get("requires_creative")
    if requires_creative is None:
        requires_creative = stage in CREATIVE_STAGES
    if requires_creative:
        payload = case.get("creative")
        if not isinstance(payload, dict):
            fail("CREATIVE_REQUIRED",
                 "stage %r requires the creative-fidelity gate; no payload"
                 % stage)
            sub["creative"] = {"verdict": FAIL, "code": "CREATIVE_REQUIRED",
                               "failures": []}
        else:
            res = check_creative(payload)
            sub["creative"] = res
            for f in res["failures"]:
                fail(f["code"], f["detail"])

    # --- 4. human lyric sign-off (Plan 9.3) -----------------------------
    requires_signoff = case.get("requires_signoff")
    if requires_signoff is None:
        requires_signoff = stage in SIGNOFF_STAGES
    if requires_signoff:
        expected = case.get("lyrics_digest")
        if expected is None:
            lines = case.get("approved_lyrics")
            if lines is not None:
                expected = lyrics_digest(lines)
        res = check_signoff(case.get("signoff"),
                            expected_digest=expected,
                            song_started_at=case.get("song_started_at"),
                            maker=case.get("lyrics_maker"))
        sub["signoff"] = res
        for f in res["failures"]:
            fail(f["code"], f["detail"])

    # --- aggregate -------------------------------------------------------
    if rec_res["gate"] == BLOCKED:
        gate = BLOCKED
    elif failures:
        gate = FAIL
    else:
        gate = PASS
    codes = sorted({f["code"] for f in failures})
    repair = sorted({cid for cid in rec_res.get("repair_scope", [])})
    return {
        "variant": key,
        "length_s": length_s,
        "shape": shape,
        "stage": bound_stage,
        "gate": gate,
        "reason_codes": codes,
        "failures": failures,
        "repair_scope": repair,
        "critical_failures": sorted({f["check_id"] for f in rec_res
                                     .get("critical_failures", [])}),
        "sub_gates": sub,
    }


def evaluate_variants(run_id, stage, cases, required_variants=None):
    """Per-variant gates for a whole run + the aggregate decision.

    cases: {variant_key: case}. required_variants: iterable of
    (length_s, shape) pairs; defaults to every key present in cases. A
    required variant with no case is FAIL MISSING_VARIANT_QC -- a run
    never passes because someone forgot to QC a variant.
    """
    if not isinstance(cases, dict):
        raise VariantQCError("BAD_CASES", "cases must be a dict by variant key")
    if required_variants is None:
        keys = sorted(cases)
    else:
        keys = []
        for pair in required_variants:
            if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
                raise VariantQCError("BAD_REQUIRED_VARIANT",
                                     "required variant must be (length, shape)")
            keys.append(variant_key(pair[0], pair[1]))
        keys = sorted(set(keys))
    if not keys:
        raise VariantQCError("NO_VARIANTS", "no variants required")

    results = {}
    all_failures = []
    blocked = False
    for key in keys:
        case = cases.get(key)
        if case is None:
            res = {"variant": key, "gate": FAIL,
                   "reason_codes": ["MISSING_VARIANT_QC"],
                   "failures": [{"code": "MISSING_VARIANT_QC",
                                 "detail": "no QC case for required variant %s"
                                           % key, "critical": False}],
                   "repair_scope": [], "critical_failures": [],
                   "sub_gates": {}}
        else:
            length_s, shape = key.split("@", 1)[0].rstrip("s"), \
                key.split("@", 1)[1]
            res = evaluate_variant(run_id, stage, int(length_s), shape, case)
        if res["gate"] == BLOCKED:
            blocked = True
        results[key] = res
        all_failures.extend(res["failures"])

    if blocked:
        gate = BLOCKED
    elif any(r["gate"] != PASS for r in results.values()):
        gate = FAIL
    else:
        gate = PASS
    codes = sorted({f["code"] for f in all_failures})
    return {
        "stage": stage,
        "run_id": run_id,
        "gate": gate,
        "reason_codes": codes,
        "variants": results,
        "passing_variants": sorted(k for k, r in results.items()
                                   if r["gate"] == PASS),
        "failing_variants": sorted(k for k, r in results.items()
                                   if r["gate"] != PASS),
    }
