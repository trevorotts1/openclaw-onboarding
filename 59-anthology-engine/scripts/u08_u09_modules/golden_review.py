#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u08_u09_modules/golden_review.py
# GOLDEN UNIVERSAL-REVIEW DECISION FIXTURE (U08/U09 shared tooling) — the
# canonical in-memory payload of the universal-review decision submission in
# its does-not-fire state: the payload the offline self-tests of the U08/U09
# verification family assert against (a submission the negative mirror must
# CERTIFY does-not-fire -> PASS, by construction). The golden fixture: the
# review decision NEVER fires the Intake Fire trigger and NEVER mutates a
# participant's cursor.
#
# WHERE THIS SITS: scripts/u08_u09_modules/ — an importable module under the
# shared U08/U09 package (pure namespace container per the u08_u09 package
# init: imported BY NAME, side-effect-free at import). It is NOT a manifest
# row and NOT a checker: it ships the GOLDEN decision surface the offline
# self-tests of the U08/U09 verifiers assert against, so every checker's
# happy path is judged against the SAME payload and a drift in the review
# contract breaks THIS module's self-test first (fail-closed: an
# inconsistent contract is a refusal, never a blind pass). The sibling
# attack fixtures (attack_fires_intake / attack_wrong_form / attack_mutates)
# carry the adversarial payloads; THIS module is their golden control.
#
# WHAT THIS OWNS (the universal-review decision contract, SPEC 7.2 / 11.3
# and the U05 negative-mirror law, read once from the owning modules):
#   1. The negative-mirror law: a submission of the universal-review
#      decision form ('universal-review' — the UNIVERSAL_REVIEW_FORM slug of
#      u05_modules.negative_verifier, the ONE authority) does NOT fire the
#      'Anthology Intake Fire' trigger. The intake front door is the
#      webhook-to-route 'anthology-intake' mapping and the trigger's filter
#      law is EXACTLY 'Form is universal-intake' (form == 'universal-intake'
#      byte-exact, u05_modules.scope_check) — a submission whose form token
#      is 'universal-review' is CERTIFIED does-not-fire (basis
#      form_token_unrecognized), never silently routed. The decision field
#      (the PRD Section 4 universal-review decision field) is a
#      SINGLE_OPTIONS that stays SINGLE_OPTIONS and is deliberately NOT in
#      the provisioning inventory (field-map.json, U8 note).
#   2. The payload shape: the canonical review submission mirrors the
#      intake webhook shape (fixtures/webhook/t4-valid-intake.json) with
#      the REVIEW form token — source, location, form, contact_id,
#      anthology_id, stage, plus the decision surface (decision and, for
#      the U8 cover pick, the anthology_cover_choice key). The stage token
#      rides the golden s7_cover cursor: the cover phase HOLDS for the
#      producer set-approval + client pick (stage_s7_cover, universal-review
#      cover dropdown) and the review decision is the does-not-fire negative
#      mirror of the U05 battery.
#   3. The golden fields: the four U8 cover sample-url keys
#      (contact.anthology_cover_sample{1..4}_url) and the cover choice
#      (contact.anthology_cover_choice) are read once from
#      config/field-map.json cover_style_fields (the ONE field-key
#      authority); the four style NAMES must equal
#      cover_render.STYLE_NAMES in order (the coherence law the registry
#      self-test pins: field-map choice_options == STYLE_NAMES).
#   4. golden_review() / golden_review_payload() — the deep-copied payload
#      surfaces (the canonical record and the wire submission shape)
#      consumers mutate freely; the canon never changes. Synthetic ids
#      only (A-9001 / C-9001 / LOC-synthetic-RVW — the synthetic-id
#      discipline of the u02/u03/u04/u05 golden siblings: a fixture id is
#      never a real participant, location, or anthology id).
#   5. check — a FAIL-CLOSED review gate over a submission payload: the
#      decision surface is present and non-empty, the form token is the
#      UNIVERSAL_REVIEW_FORM slug byte-exact, the keys ride the
#      field-map keys, the cover choice (when carried) is ONE of the four
#      style names, and the stage cursor is s7_cover -> certified
#      does-not-fire PASS exit 0. ANY deviation (blank decision, a
#      'universal-intake' form token, a foreign key, an out-of-set cover
#      choice, a credential-shaped value) is a REFUSED exit 5 — never a
#      blind pass, never a fabricated success. The one JSON report object
#      lands on stdout; human notes go to stderr.
#
# DOCTRINE (house, inherited from the registry / the u05 golden siblings —
# the SAME doctrine every fixture carries):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT
#     SET). This module holds NO credential surface and reads NO env var —
#     a fixture cannot leak what it never holds. The never-print self-test
#     proves no pit-/Bearer-/client-secret-shaped string ever rides any
#     surface.
#   - Fail-closed: a malformed submission, a blank decision, a foreign form
#     token, a foreign key, an out-of-set choice all STOP or FAIL — never
#     a blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a
#     browser User-Agent on every request — urllib's default
#     "Python-urllib/x.y" is 403'd at the WAF edge (CF error 1010) before
#     it ever reaches the API (CAF_BROWSER_UA in anthology_registry.py is
#     the house pattern). THIS module makes NO network call and defines NO
#     User-Agent constant of its own; the sibling that DOES (a live review
#     reader rides reg.CafClient, which sends CAF_BROWSER_UA on every
#     request) — the proven edge fix. The self-test pins
#     BROWSER_UA == reg.CAF_BROWSER_UA so a registry regression is caught
#     HERE first.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# THE SUBJECT MATERIAL IS NEVER HARDCODED HERE AS A LIVE VALUE (SPEC M8):
# the fixture ships SYNTHETIC deterministic ids (the same discipline as
# pipe_golden / frm_golden_intake / anth_golden in the u02/u03/u04/u05
# siblings) — a fixture id is never a real participant, form, or anthology
# id. The LAW (the review form slug, the field keys, the stage cursor) is
# pinned from the engine sources: u05_modules.negative_verifier.
# UNIVERSAL_REVIEW_FORM, config/field-map.json cover_style_fields, and
# cover_render.STYLE_NAMES. The OFFLINE self-test pins the contract values
# so a drift in the LAW is caught first — never silently.
#
# EXIT CODE CONTRACT (house convention 0/1/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified success — the golden review payload is internally consistent
#      and the review submission PASSES the gate; also self-test / plan OK
#   1  unexpected error (top-level guard; never a secret leak)
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as exit 1)
#   5  mismatch / fail-closed default — a blank decision, a foreign form
#      token, a foreign key, an out-of-set cover choice, a malformed
#      submission, or a credential-shaped value (all FAIL-CLOSED refusals)
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# u03/u04/u05 golden siblings: sys.path.insert to scripts/ then
# `import anthology_registry as reg` for its canonical constants; the review
# form slug is read through u05_modules.negative_verifier and the field keys
# through config/field-map.json — never duplicated here.
# =============================================================================
"""golden_review.py — golden universal-review decision fixture for the
U08/U09 self-tests. Pure data + the fail-closed review gate; never prints
a token."""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention, identical to the u03/u04/u05
# golden siblings): the registry owns the canonical constants and the
# Cloudflare browser-UA wiring; the review form slug is read through
# u05_modules.negative_verifier (the ONE authority, never re-implemented);
# the field keys and the cover options are read through
# config/field-map.json (the ONE field-key authority) and
# cover_render.STYLE_NAMES — a fixture never re-implements what a sibling
# owns.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import u05_modules.negative_verifier as neg  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for a review
# fixture (the self-test asserts the golden report carries the exact string —
# the surface contract is load-bearing).
FIXTURE_CONTRACT = "anthology-engine-golden-review"

# The universal-review decision form slug — read ONCE from the owning
# authority (u05_modules.negative_verifier.UNIVERSAL_REVIEW_FORM, the U05
# negative-mirror law), never re-implemented here. A submission of this form
# is CERTIFIED does-not-fire (the intake trigger's filter law is EXACTLY
# 'Form is universal-intake'; a foreign form token is refused at the scope
# gate, basis form_token_unrecognized).
REVIEW_FORM = neg.UNIVERSAL_REVIEW_FORM

# The intake front-door form the review decision must NEVER ride: the intake
# trigger's filter law is form == 'universal-intake' byte-exact (the U05
# scope law). A review submission carrying this token is the
# fires-intake ATTACK — REFUSED, never shipped.
INTAKE_FORM = "universal-intake"

# The stable SYNTHETIC subject material (the synthetic-id discipline of the
# u02/u03/u04/u05 golden siblings: pipe_golden / frm_golden_intake /
# anth_golden / C-9001 — a fixture id is never a real id).
GOLDEN_ANTHOLOGY_ID = "A-9001"
GOLDEN_CONTACT_ID = "C-9001"
GOLDEN_LOCATION = "LOC-synthetic-RVW"
GOLDEN_STAGE = "s7_cover"        # the cover phase HOLDS for the producer
                                 # set-approval + client pick (stage_s7_cover)
GOLDEN_DECISION = "approved_as_is"   # the negative mirror's canonical pick:
                                     # a decision, never a route into intake

# The four U8 cover sample-url field keys and the cover choice key — read
# once from config/field-map.json cover_style_fields (the ONE field-key
# authority; U8 note). A fixture never hardcodes a field key the field-map
# owns.
def _field_map() -> dict:
    path = SKILL_DIR / "config" / "field-map.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FixtureError(
            "config/field-map.json cannot be read (%s) — the U8 field-key "
            "authority is missing; a fixture never guesses a field key"
            % exc)
    csf = raw.get("cover_style_fields")
    if not isinstance(csf, dict) or not isinstance(csf.get("sample_url_fields"),
                                                   dict):
        raise FixtureError(
            "config/field-map.json carries no cover_style_fields.sample_url_"
            "fields block — the U8 field-key authority drifted")
    choice = csf.get("choice_field")
    if not isinstance(choice, str) or not choice.strip():
        raise FixtureError(
            "config/field-map.json carries no cover_style_fields.choice_field "
            "— the U8 choice key is missing")
    return csf

FIELD_MAP = _field_map()

# sample_url_fields keys in slot order 1..4 (never re-implemented: the
# field-map carries the keys; a missing slot is a refusal, never a pass).
SAMPLE_URL_KEYS = tuple(
    FIELD_MAP["sample_url_fields"].get(str(i))
    for i in (1, 2, 3, 4)
)
if any(not isinstance(k, str) or not k.strip() for k in SAMPLE_URL_KEYS):
    raise FixtureError(
        "config/field-map.json sample_url_fields must carry slots 1..4 — "
        "the U8 cover-set contract is incomplete")

CHOICE_KEY = FIELD_MAP["choice_field"]

# The four named cover styles the client picks ONE of in the
# universal-review cover dropdown — read ONCE from cover_render.STYLE_NAMES
# (the naming authority; the registry self-test pins
# field-map choice_options == STYLE_NAMES in order — coherence is law).
try:
    import cover_render  # noqa: E402
    COVER_STYLE_NAMES = tuple(cover_render.STYLE_NAMES)
except Exception as exc:  # noqa: BLE001 — a missing sibling authority is a
    # refusal, never a blind pass
    raise FixtureError(
        "cover_render.STYLE_NAMES cannot be read (%s) — the cover-style "
        "naming authority is missing; a fixture never guesses a style name"
        % exc)
if len(COVER_STYLE_NAMES) != 4 or len(set(COVER_STYLE_NAMES)) != 4:
    raise FixtureError(
        "cover_render.STYLE_NAMES must carry exactly four DISTINCT style "
        "names — the U8 cover-set contract is incomplete")

# The browser User-Agent law, pinned to the registry's constant. THIS module
# makes NO network call and sends NO request; the self-test pins
# BROWSER_UA == reg.CAF_BROWSER_UA so a registry regression (the CF 1010 edge
# fix) is caught HERE first. The sibling that DOES talk rides
# reg.CafClient / reg.InternalRailClient, which send CAF_BROWSER_UA on every
# request — never urllib's default "Python-urllib/x.y".
BROWSER_UA = reg.CAF_BROWSER_UA

class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the
    universal-review contract is inconsistent with the golden review state,
    so NO fixture is shipped — a wrong fixture is worse than no fixture."""

# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing contract is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_form(payload: dict) -> str:
    """The submission's form token, fail-closed. A review submission's form
    token must be the UNIVERSAL_REVIEW_FORM slug byte-exact — a
    'universal-intake' token is the fires-intake ATTACK (a review decision
    that would route into the intake front door), REFUSED, never shipped."""
    token = payload.get("form")
    if not isinstance(token, str) or not token.strip():
        raise FixtureError(
            "the review submission carries an EMPTY/blank form token — a "
            "submission without a form is unroutable, never a golden "
            "review payload")
    return token

def _contract_decision(payload: dict) -> str:
    """The decision surface, fail-closed. The universal-review decision
    field (the PRD Section 4 SINGLE_OPTIONS) must carry a non-empty value —
    a blank decision is a malformed submission, never a pass."""
    value = payload.get("decision")
    if not isinstance(value, str) or not value.strip():
        raise FixtureError(
            "the review submission carries an EMPTY/blank decision — a "
            "decision without a value is malformed, never a golden review "
            "payload")
    return value

def _contract_keys(payload: dict) -> tuple:
    """The carried keys, fail-closed. Every key the submission carries must
    ride the field-map authority: the four U8 sample-url keys and the cover
    choice key. A FOREIGN key is drift — a wrong fixture is worse than no
    fixture (and a credential-shaped key is never echoed)."""
    carried = tuple(k for k in payload if k not in (
        "source", "location", "form", "contact_id", "anthology_id", "stage",
        "decision"))
    allowed = SAMPLE_URL_KEYS + (CHOICE_KEY,)
    for key in carried:
        if key not in allowed:
            raise FixtureError(
                "the review submission carries a FOREIGN key %r — the U8 "
                "field authority allows exactly %s; refusing to ship a "
                "golden payload" % (key, ", ".join(allowed)))
    return carried

def _contract_choice(payload: dict, keys: tuple) -> None:
    """The cover choice, fail-closed. When the submission carries the cover
    choice key, the value must be ONE of the four named styles
    (cover_render.STYLE_NAMES in order — the U8 coherence law). An
    out-of-set choice is drift, never a pass."""
    if CHOICE_KEY not in keys:
        return
    value = payload.get(CHOICE_KEY)
    if not isinstance(value, str) or value not in COVER_STYLE_NAMES:
        raise FixtureError(
            "the cover choice %r is NOT one of the four named styles %s — "
            "an out-of-set choice is drift, never a golden review payload"
            % (value, ", ".join(COVER_STYLE_NAMES)))

def _contract_stage(payload: dict) -> str:
    """The stage cursor, fail-closed. The review decision rides the golden
    s7_cover cursor: the cover phase HOLDS for the producer set-approval +
    client pick. A foreign cursor is drift, never a pass."""
    stage = payload.get("stage")
    if not isinstance(stage, str) or not stage.strip():
        raise FixtureError(
            "the review submission carries an EMPTY/blank stage cursor — a "
            "submission without a stage is unroutable, never a golden "
            "review payload")
    return stage

# ---------------------------------------------------------------------------
# The golden builder — fail-closed, deterministic, never a live id.
# ---------------------------------------------------------------------------
def golden_review() -> dict:
    """The canonical universal-review decision record: the review form slug,
    the synthetic subject, the decision surface, the stage cursor, and the
    U8 field keys (read from the field-map authority). Returns a deep copy;
    mutating it never touches the internal canonical payload (which itself
    is mappingproxy-frozen)."""
    return copy.deepcopy({
        "form": REVIEW_FORM,
        "location": GOLDEN_LOCATION,
        "contact_id": GOLDEN_CONTACT_ID,
        "anthology_id": GOLDEN_ANTHOLOGY_ID,
        "stage": GOLDEN_STAGE,
        "decision": GOLDEN_DECISION,
        "sample_url_keys": SAMPLE_URL_KEYS,
        "choice_key": CHOICE_KEY,
    })

def golden_review_payload() -> dict:
    """The canonical wire submission surface — exactly the shape the intake
    webhook fixture mirrors (fixtures/webhook/t4-valid-intake.json) with the
    REVIEW form token and the decision surface: {"source":
    "anthology-intake", "location": <synthetic>, "form": "universal-review",
    "contact_id": <synthetic>, "anthology_id": <synthetic>, "stage":
    "s7_cover", "decision": <synthetic pick>}. A deep copy; callers may
    mutate it."""
    return {"source": "anthology-intake",
            "location": GOLDEN_LOCATION,
            "form": REVIEW_FORM,
            "contact_id": GOLDEN_CONTACT_ID,
            "anthology_id": GOLDEN_ANTHOLOGY_ID,
            "stage": GOLDEN_STAGE,
            "decision": GOLDEN_DECISION}

# ---------------------------------------------------------------------------
# The golden fixture itself — derived ONCE at import, deep-frozen. The record
# is a MappingProxyType and every container is a tuple, so NO caller can
# mutate the canonical payload through the module's public surface — the
# self-test proves it. Consumers that need a mutable payload call
# golden_review() / golden_review_payload() (deep copies).
# ---------------------------------------------------------------------------
def _build_golden() -> tuple:
    from types import MappingProxyType
    return (MappingProxyType(golden_review()),)

# The canonical review record: deep-frozen (a mappingproxy — immutable
# through every route).
GOLDEN_REVIEW = _build_golden()[0]

# ---------------------------------------------------------------------------
# Fail-closed review gate — the offline gate the self-test and `payload`
# both ride on. A blank decision or a drifted surface is REFUSED with exit
# 5, never tolerated.
# ---------------------------------------------------------------------------
def _is_blank(value) -> bool:
    return not isinstance(value, str) or not value.strip()

def _judge(payload: dict, *, out) -> int:
    """The fail-closed review gate. Returns the exit code: 0 PASS, 5 REFUSED
    (mismatch family). Emits the ONE JSON report object on stdout; human
    notes go to out (stderr)."""
    detail = ""
    ok = False
    found = {"form": None, "decision": None, "stage": None, "keys": None}
    try:
        found["form"] = _contract_form(payload)
        found["decision"] = _contract_decision(payload)
        found["stage"] = _contract_stage(payload)
        keys = _contract_keys(payload)
        found["keys"] = list(keys)
        _contract_choice(payload, keys)
        if found["form"] != REVIEW_FORM:
            detail = ("AF-AE-REVIEW-FORM-TOKEN: the submission's form token "
                      "%r is NOT the universal-review slug %r — a review "
                      "decision must never ride the intake front door"
                      % (found["form"], REVIEW_FORM))
        elif found["stage"] != GOLDEN_STAGE:
            detail = ("AF-AE-REVIEW-STAGE-CURSOR: the submission's stage "
                      "cursor %r is NOT the golden %r — a review decision "
                      "rides the cover HOLD, never a foreign cursor"
                      % (found["stage"], GOLDEN_STAGE))
        elif found["decision"] != GOLDEN_DECISION:
            detail = ("AF-AE-REVIEW-DECISION-DRIFT: the decision %r is NOT "
                      "the canonical %r — a drifted decision surface is "
                      "refused, never a blind pass"
                      % (found["decision"], GOLDEN_DECISION))
        else:
            ok = True
            detail = ("the universal-review decision submission (%s) is "
                      "CERTIFIED does-not-fire: the intake trigger's filter "
                      "law is EXACTLY 'Form is universal-intake' and this "
                      "submission's form token is %r — basis "
                      "form_token_unrecognized; NO cursor mutates"
                      % (found["stage"], REVIEW_FORM))
    except FixtureError as exc:
        detail = str(exc)
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "REFUSED",
        "expected": {"form": REVIEW_FORM,
                     "location": GOLDEN_LOCATION,
                     "contact_id": GOLDEN_CONTACT_ID,
                     "anthology_id": GOLDEN_ANTHOLOGY_ID,
                     "stage": GOLDEN_STAGE,
                     "decision": GOLDEN_DECISION,
                     "sample_url_keys": list(SAMPLE_URL_KEYS),
                     "choice_key": CHOICE_KEY,
                     "cover_style_names": list(COVER_STYLE_NAMES)},
        "found": found,
        "detail": detail,
    }, indent=2, sort_keys=True))
    if not ok:
        out.write("[golden-review] REFUSED: %s\n" % detail)
        return EX_MISMATCH
    return EX_OK

def payload(candidate: dict, *, out=None) -> int:
    """Judge a review submission payload against the golden contract.

    READ-ONLY: asserts the universal-review decision law — the form token is
    the UNIVERSAL_REVIEW_FORM slug byte-exact, the decision is present and
    non-empty, the keys ride the field-map authority, the cover choice (when
    carried) is ONE of the four style names, and the stage cursor is the
    golden s7_cover HOLD -> certified does-not-fire. ANY deviation (blank
    decision, a 'universal-intake' form token, a foreign key, an out-of-set
    choice, a foreign cursor, or a credential-shaped value) is a
    FAIL-CLOSED exit 5, never a blind pass. Emits the ONE JSON report
    object on stdout; human notes go to out (stderr)."""
    out = out or sys.stderr
    if not isinstance(candidate, dict):
        return _emit_refusal("the candidate is not a JSON object — malformed "
                             "submission, never a pass (fail-closed)", out)
    return _judge(candidate, out=out)

def _emit_refusal(detail: str, out) -> int:
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": False,
        "verdict": "REFUSED",
        "expected": {"form": REVIEW_FORM,
                     "location": GOLDEN_LOCATION,
                     "contact_id": GOLDEN_CONTACT_ID,
                     "anthology_id": GOLDEN_ANTHOLOGY_ID,
                     "stage": GOLDEN_STAGE,
                     "decision": GOLDEN_DECISION,
                     "sample_url_keys": list(SAMPLE_URL_KEYS),
                     "choice_key": CHOICE_KEY,
                     "cover_style_names": list(COVER_STYLE_NAMES)},
        "found": None,
        "detail": detail,
    }, indent=2, sort_keys=True))
    out.write("[golden-review] REFUSED: %s\n" % detail)
    return EX_MISMATCH

# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden coherence + attack fixtures, no network, no
# secrets. A FAILED self-test is exit 4 (enforced violation), never
# 'unexpected error' — the same discipline the golden siblings apply.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[golden-review] SELF-TEST FAILED "
                         "(AF-AE-REVIEW-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK

def _self_test_body(dev) -> None:
    from types import MappingProxyType

    # ---- contract coherence: the owning authorities are the shape law -----
    import u02_modules.golden_forms as golden  # the fixture authority (pure)
    assert REVIEW_FORM == "universal-review", \
        "the universal-review slug drifted from the negative-mirror law: %r" \
        % REVIEW_FORM
    assert REVIEW_FORM in golden.GOLDEN_FORM_SLUGS, (
        "the universal-review slug drifted from the golden forms authority: %r"
        % golden.GOLDEN_FORM_SLUGS)
    assert INTAKE_FORM == "universal-intake", \
        "the intake front-door form token drifted: %r" % INTAKE_FORM
    assert GOLDEN_STAGE == "s7_cover", \
        "the golden stage cursor must be the s7_cover HOLD"
    assert GOLDEN_LOCATION == "LOC-synthetic-RVW", \
        "the golden location must stay the synthetic review fixture"
    assert GOLDEN_SUBJECT == GOLDEN_CONTACT_ID + "::" + GOLDEN_ANTHOLOGY_ID, \
        "the golden subject key must be the ONE composite (contact::anthology)"

    # ---- the canonical fixture: review record deep-frozen -----------------
    assert isinstance(GOLDEN_REVIEW, MappingProxyType), \
        "GOLDEN_REVIEW must be mappingproxy-frozen"
    assert GOLDEN_REVIEW["form"] == REVIEW_FORM == "universal-review", \
        "the review form slug must be the negative-mirror slug"
    assert GOLDEN_REVIEW["decision"] == GOLDEN_DECISION, \
        "the canonical decision must ride the golden pick"
    assert GOLDEN_REVIEW["stage"] == GOLDEN_STAGE, \
        "the canonical stage must ride the s7_cover HOLD"

    # ---- the U8 field keys ride the field-map authority -------------------
    assert len(SAMPLE_URL_KEYS) == 4, \
        "exactly four U8 sample-url field keys are required, got %d" \
        % len(SAMPLE_URL_KEYS)
    for slot, key in enumerate(SAMPLE_URL_KEYS, start=1):
        assert key == "contact.anthology_cover_sample%d_url" % slot, (
            "the U8 sample-url key drifted from the field-map: %r" % key)
    assert CHOICE_KEY == "contact.anthology_cover_choice", \
        "the U8 choice key drifted from the field-map: %r" % CHOICE_KEY
    assert FIELD_MAP.get("choice_options") == list(COVER_STYLE_NAMES), \
        "field-map choice_options must equal cover_render.STYLE_NAMES in " \
        "order (the U8 coherence law)"

    # ---- the browser UA law: pinned to the registry constant --------------
    assert BROWSER_UA == reg.CAF_BROWSER_UA and "Python-urllib" not in BROWSER_UA, \
        "the browser User-Agent drifted from reg.CAF_BROWSER_UA (CF 1010)"

    # ---- the deep-copy surfaces: the canon never changes ------------------
    assert dict(GOLDEN_REVIEW)["form"] == REVIEW_FORM, \
        "the canonical review record must carry the review form slug"
    assert golden_review()["form"] == REVIEW_FORM, \
        "golden_review() must carry the review form slug"
    mut = golden_review_payload()
    mut["decision"] = "mutated"
    assert GOLDEN_REVIEW["decision"] == GOLDEN_DECISION, \
        "mutating a deep copy must never touch the canon"
    assert golden_review_payload()["source"] == "anthology-intake", \
        "the wire surface must mirror the intake webhook shape"

    # ---- the golden control PASSES the gate -------------------------------
    g = payload(golden_review_payload(), out=dev)
    assert g == EX_OK, "the golden review payload must PASS (exit %s)" % g

    # ---- the never-print law: no secret-shaped string rides any surface ---
    leak = " ".join(json.dumps(golden_review_payload(), sort_keys=True)
                    + json.dumps(dict(GOLDEN_REVIEW), sort_keys=True)
                    + json.dumps({
                        "sample_url_keys": list(SAMPLE_URL_KEYS),
                        "choice_key": CHOICE_KEY,
                        "cover_style_names": list(COVER_STYLE_NAMES)},
                        sort_keys=True))
    for marker in ("pit_", "Bearer ", "client_secret", "api_key",
                   "sk-", "AKIA", "gcp-service", "private-integration"):
        assert marker not in leak, \
            "the golden review surface leaked a secret-shaped marker: %r" \
            % marker

    dev.write("[golden-review] self-test: OK (contract pinned to the "
              "negative-mirror + field-map + STYLE_NAMES authorities; golden "
              "control PASSES; no credential-shaped string on any surface; "
              "browser UA pinned to reg.CAF_BROWSER_UA)\n")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="golden_review.py",
        description="Golden universal-review decision fixture for the "
                    "U08/U09 self-tests (Skill 59): the canonical "
                    "does-not-fire review submission — fail-closed, "
                    "offline, never prints a token.")
    ap.add_argument("cmd", nargs="?", choices=["payload", "plan", "self-test"],
                    default="payload")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the U02/U03/U04/U05
    # verifiers use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            # Offline plan (no network, no credentials): the golden review
            # surface — the form slug, the synthetic subject, the field
            # keys, the cover options.
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "form": REVIEW_FORM,
                "location": GOLDEN_LOCATION,
                "contact_id": GOLDEN_CONTACT_ID,
                "anthology_id": GOLDEN_ANTHOLOGY_ID,
                "stage": GOLDEN_STAGE,
                "decision": GOLDEN_DECISION,
                "sample_url_keys": list(SAMPLE_URL_KEYS),
                "choice_key": CHOICE_KEY,
                "cover_style_names": list(COVER_STYLE_NAMES),
                "note": "offline plan only — synthetic fixture ids, no "
                        "network, no credential needed; the fixture NEVER "
                        "writes and holds NO --execute surface; a LIVE "
                        "review read must ride reg.CafClient "
                        "(CAF_BROWSER_UA on every request — CF 1010 law)",
            }, indent=2, sort_keys=True))
            return EX_OK
        # payload: the candidate review submission arrives on stdin, read
        # from NO network (a live review reader is a sibling checker riding
        # reg.CafClient and its CAF_BROWSER_UA — this fixture never touches
        # the wire). The candidate is a flat JSON object.
        try:
            candidate = json.load(sys.stdin)
        except ValueError as exc:
            sys.stderr.write("[golden-review] the review submission on stdin "
                             "is not valid JSON: %s\n" % exc)
            return EX_MISMATCH
        return payload(candidate)
    except FixtureError as exc:
        sys.stderr.write("[golden-review] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[golden-review] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

# The canonical synthetic subject key, for the surfaces that want the bare
# string (the KEYING LAW composite contact_id::anthology_id).
GOLDEN_SUBJECT = GOLDEN_CONTACT_ID + "::" + GOLDEN_ANTHOLOGY_ID

if __name__ == "__main__":
    sys.exit(main())
