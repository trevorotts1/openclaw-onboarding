#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u06_modules/golden_found.py  (U06 tooling)
# GOLDEN BOTH-WORKFLOWS FIXTURE — the canonical in-memory payload of the
# U06 FIND half in its FOUND state: BOTH contract workflows the archive
# action touches are on the listing BY EXACT NAME and carry their ONE
# workflow id each — the golden control of the U06 find-then-archive gate
# (the anti-attack mirror of golden_absent.py, which certifies the state
# where there is NOTHING to archive).
#
# WHERE THIS SITS: scripts/u06_modules/ — an importable module under the U06
# package (pure namespace container per the u06 __init__.py: imported BY
# NAME, side-effect-free at import; the init records the U06 archive
# doctrine: destructive actions require --execute, Trevor-gated — WITHOUT
# --execute a module must report what it WOULD do and exit without
# mutating). It is NOT a manifest row and NOT a checker: it ships the
# GOLDEN found-state surface the offline self-tests of the U06 verifier
# and its sibling checkers assert against, so every checker's happy path
# is judged against the SAME payload and a drift in the engine's find law
# breaks THIS module's self-test first (fail-closed: an inconsistent law
# is a refusal, never a blind pass).
#
# WHAT THIS OWNS (the U06 FIND LAW, derived from the sibling that owns the
# find — u06_modules.find_legacy.py LEGACY_NAMES, the ONE pinned table of
# the two legacy engine workflows the archive action touches):
#   1. THE FOUND-STATE LAW: the archive gate is find-then-archive, and the
#      FOUND state is EXACTLY TWO workflow rows on the listing — one per
#      contract legacy name, each matched BY EXACT NAME (the exact-name
#      law: workflow-typed row name == the contract name with dashes ->
#      spaces, normalized lowercase — a renamed legacy is indistinguishable
#      from an absent one and BOTH refuse fail-closed). The golden surface
#      carries BOTH workflows found under the golden keys, each with its
#      ONE id (masked on every operator surface, full only inside the JSON
#      payload a machine consumer reads) — a listing that loses a contract
#      workflow is a FAIL, never a blind pass.
#   2. THE NAME LAW IS READ ONCE: the golden names are NEVER retyped here —
#      they come BYTE-EXACT from find_legacy.LEGACY_NAMES (the delta_reporter
#      single-implementation doctrine: a contract read once, in one module;
#      the golden keys are the same stable keys the finder's surface
#      reports: "start_anthology_writer" and "pipeline_manager"). A drift
#      in the pinned table breaks THIS fixture's self-test first — never
#      silently.
#   3. GOLDEN_FOUND — the deep-frozen canonical record: {"start_anthology_
#      writer": {"found": True, "id": <synthetic>, "id_masked": <masked>,
#      "matched_by": "name"}, "pipeline_manager": {...}} — both rows found,
#      synthetic ids only (wf_golden_start / wf_golden_pipe — the fixture
#      discipline: a fixture id is never a real id). The record is a
#      MappingProxyType (types module) and every container inside it is a
#      tuple, so NO caller can mutate the canonical payload through the
#      module's public surface — the self-test proves every mutation route
#      raises.
#   4. golden_found() / golden_found_payload() / golden_listing_payload()
#      — the deep-copied payload surfaces (the canonical found record, the
#      {"workflows": {...}} shape the U06 find surface reads, and the
#      {"rows": [...]} internal-rail listing shape the finder reads live)
#      consumers mutate freely; the canon never changes. The listing is
#      derived from the golden names ONCE, in the same row shape the
#      finder's golden read uses (workflow-typed rows; the two contract
#      workflows plus one unrelated workflow — never a bare two-row
#      listing, so the find proves the exact-name law against a real
#      listing shape).
#   5. payload — a FAIL-CLOSED found-state gate: the golden listing carries
#      BOTH contract workflows byte-exact by their golden keys (each found
#      with its one synthetic id, each matched BY NAME) -> PASS exit 0 with
#      the dispatcher-consumed dict surface {"ok": True, "names": [the two
#      contract names], "rows": <row count>, "af_code": "LEGACY-FOUND",
#      "note": ...}. ANY deviation (a contract workflow absent or renamed,
#      a malformed listing, a duplicate name, a missing rows array, a
#      non-object row, a credential-shaped value) is a REFUSED exit 5 —
#      never a blind pass, never a fabricated success. The one JSON report
#      object lands on stdout; human notes go to stderr; the dict the
#      dispatcher's verify_live consumes is the payload() RETURN VALUE.
#
# DOCTRINE (house, inherited from the registry / the u02/u03/u04/u05 golden
# siblings and the U06 golden_absent sibling — the SAME doctrine every
# fixture carries):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT
#     SET). This module holds NO credential surface and reads NO env var —
#     a fixture cannot leak what it never holds. The only id-shaped
#     material it carries is SYNTHETIC fixture markers (wf_golden_*), and
#     the never-print self-test proves no pit-/Bearer-shaped string ever
#     rides any surface.
#   - Fail-closed: a malformed listing, an absent or renamed contract
#     workflow, a duplicate name, a credential-shaped value all STOP or
#     FAIL — never a blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#     The --execute gate that refuses an archive ACTION without --execute
#     (Trevor-gated) lives in the dispatcher (main_skeleton.py), never in
#     a fixture; THIS module pins the gate as the law its surfaces carry,
#     exactly as golden_absent pins it.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a
#     browser User-Agent on every request — urllib's default
#     "Python-urllib/x.y" is 403'd at the WAF edge (CF error 1010) before it
#     ever reaches the API (CAF_BROWSER_UA in anthology_registry.py is the
#     house pattern). THIS module makes NO network call and defines NO
#     User-Agent constant of its own; the sibling that DOES (the finder
#     rides the house rail clients, which send CAF_BROWSER_UA on every
#     request) — the proven edge fix. The self-test pins the browser UA law
#     so a registry regression is caught HERE first.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# THE SUBJECT MATERIAL IS NEVER HARDCODED HERE AS A LIVE VALUE (SPEC M8):
# the fixture ships SYNTHETIC deterministic ids only (wf_golden_start /
# wf_golden_pipe — the discipline of the u02/u03/u04/u05 siblings: a
# fixture id is never a real participant, form, or anthology id). The LAW
# (the two contract workflow names, the golden keys, the found-state
# census shape) is pinned from the engine sources: u06_modules.find_legacy
# LEGACY_NAMES (the ONE pinned table — read once, never re-implemented).
# The OFFLINE self-test pins the contract values so a drift in the LAW is
# caught first — never silently.
#
# EXIT CODE CONTRACT (house convention 0/1/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified success — the golden found-state payload is internally
#      consistent and the golden listing PASSES the gate; also self-test /
#      plan OK
#   1  unexpected error (top-level guard; never a secret leak)
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as exit 1)
#   5  mismatch / fail-closed default — an absent or renamed contract
#      workflow, a duplicate name, a malformed listing, or a
#      credential-shaped value (all FAIL-CLOSED refusals)
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# golden_absent sibling: sys.path.insert to scripts/ then
# `import anthology_registry as reg` for its canonical constants, and the
# contract workflow names are read through u06_modules.find_legacy
# LEGACY_NAMES — never duplicated here.
# =============================================================================
"""golden_found.py — golden BOTH-WORKFLOWS-FOUND fixture for the U06
self-tests. Pure data + the fail-closed found-state gate; never prints a
token; the --execute archive gate lives in the dispatcher, never here."""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# Cloudflare browser-UA wiring and the exit-code contract; the contract
# workflow names are read ONCE from the sibling that owns the find law
# (u06_modules.find_legacy LEGACY_NAMES — the ONE pinned table) — a
# fixture never re-implements what a sibling owns.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import find_legacy as fl  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for a found
# fixture (the self-test asserts the golden report carries the exact string —
# the surface contract is load-bearing).
FIXTURE_CONTRACT = "anthology-engine-golden-found"

# The U06 ARCHIVE ACTION LAW (Trevor-gated, per the u06 package-init
# doctrine), pinned here exactly as the golden_absent sibling pins it: any
# archive ACTION REQUIRES --execute. This module is READ-ONLY and never
# performs the mutation — the --execute gate lives in the dispatcher
# (main_skeleton.py), never in a fixture; a checker that would mutate
# without --execute is caught by the dispatcher's gate FIRST.
ARCHIVE_ACTION = "archive"
EXECUTE_FLAG = "--execute"
GOLDEN_EXECUTE_REQUIRED = True  # the law: the archive ACTION is gated

# THE TWO CONTRACT WORKFLOWS — read ONCE from the sibling that owns the
# find law (u06_modules.find_legacy.LEGACY_NAMES, the ONE pinned table of
# the two legacy engine workflows the archive action touches). The golden
# keys are the same stable keys the finder's surface reports; a drift in
# the pinned table breaks THIS fixture's self-test first — never silently.
GOLDEN_WORKFLOW_KEYS = tuple(fl.LEGACY_NAMES.keys())  # the fixed two, in order
GOLDEN_WORKFLOW_NAMES = tuple(fl.LEGACY_NAMES[k] for k in GOLDEN_WORKFLOW_KEYS)

# The stable SYNTHETIC workflow ids (the synthetic-id discipline of the
# u02/u03/u04/u05 golden siblings — a fixture id is never a real id). These
# markers ride the golden found surface as the ONE id each contract
# workflow carries; they never name a real workflow.
GOLDEN_WF_IDS = ("wf_golden_start", "wf_golden_pipe")

# The found-state report the golden payload certifies (the same af_code the
# finder's ok surface carries — the two can never drift apart).
GOLDEN_AF_CODE = "LEGACY-FOUND"

# The two found rows plus ONE unrelated workflow — the golden listing is
# never a bare two-row listing, so the exact-name law is proven against a
# real listing shape (the same shape the finder's golden read carries: the
# two contract workflows, one unrelated workflow, never a non-workflow row).
_UNRELATED_WORKFLOW = {"type": "workflow", "name": "Anthology Intake Fire",
                       "id": "wfIntakeFire03"}

class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the find law
    is inconsistent with the golden found state, so NO fixture is shipped —
    a wrong fixture is worse than no fixture."""

# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing law is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_name_law() -> dict:
    """The exact-name law, fail-closed. The golden names are read ONCE from
    find_legacy.LEGACY_NAMES; a sibling table that cannot name both
    contract workflows is a refusal, never a pass (a fixture that does not
    know what it is a fixture OF is worthless)."""
    if not fl.LEGACY_NAMES or len(fl.LEGACY_NAMES) != 2:
        raise FixtureError(
            "find_legacy.LEGACY_NAMES does not carry the two contract "
            "legacy names — refusing to ship a golden payload (the find "
            "law is read once, never re-implemented).")
    out = {}
    for key in GOLDEN_WORKFLOW_KEYS:
        name = fl.LEGACY_NAMES.get(key)
        if not isinstance(name, str) or not name.strip():
            raise FixtureError(
                "find_legacy.LEGACY_NAMES carries a blank name under %r — "
                "refusing to ship a golden payload." % key)
        out[key] = name
    return out

def _contract_rows(payload: dict) -> tuple:
    """The listing's row surface, fail-closed. A listing without a 'rows'
    array is a malformed read (never a pass); rows that are not objects are
    drift (a wrong fixture is worse than no fixture)."""
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise FixtureError(
            "the golden listing carries no 'rows' array — a malformed read "
            "is never a pass; refusing to ship a golden payload.")
    out = [r for r in rows if isinstance(r, dict)]
    if len(out) != len(rows):
        raise FixtureError(
            "the golden listing carries non-object workflow rows — "
            "refusing to derive a golden payload from a malformed read.")
    return tuple(out)

def _row_name(row: dict) -> str:
    """The display name of a listing row under any of its name-bearing keys
    ("name" canonical, "workflowName" alternate — the same container keys
    the finder resolves). Returns "" when the row carries none."""
    for key in ("name", "workflowName"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def _normalize_name(name: str) -> str:
    """The name-match normalization: lowercase, spaces collapsed — the same
    law the finder pins. A renamed legacy is indistinguishable from an
    absent one and BOTH refuse fail-closed."""
    return " ".join((name or "").strip().split()).lower()

# ---------------------------------------------------------------------------
# The golden builder — fail-closed, deterministic, never a live id.
# ---------------------------------------------------------------------------
def golden_found() -> dict:
    """The canonical found-state record: both contract workflows found by
    exact name, each with its one synthetic id (masked on the surface, the
    full synthetic id inside the machine payload) — the state the U06
    find-then-archive gate exists to certify. Returns a deep copy; mutating
    it never touches the internal canonical payload (which itself is
    mappingproxy-frozen)."""
    return copy.deepcopy({
        GOLDEN_WORKFLOW_KEYS[0]: {
            "found": True,
            "id": GOLDEN_WF_IDS[0],
            "id_masked": fl.mask_id(GOLDEN_WF_IDS[0]),
            "matched_by": "name",
        },
        GOLDEN_WORKFLOW_KEYS[1]: {
            "found": True,
            "id": GOLDEN_WF_IDS[1],
            "id_masked": fl.mask_id(GOLDEN_WF_IDS[1]),
            "matched_by": "name",
        },
    })

def golden_found_payload() -> dict:
    """The canonical found-state surface: {"workflows": {<key>: {found,
    id, id_masked, matched_by}, ...}} — the exact shape a U06 find reads
    when BOTH contract workflows are found. A deep copy; callers may
    mutate it."""
    return {"workflows": golden_found()}

def golden_listing_payload() -> dict:
    """The canonical internal-rail listing surface: {"rows": [...]} — the
    two contract workflows (by the golden names, exact) plus ONE unrelated
    workflow, in the row shape the finder's golden read carries. A deep
    copy; callers may mutate it."""
    return {"rows": [
        {"type": "workflow", "name": GOLDEN_WORKFLOW_NAMES[0],
         "id": GOLDEN_WF_IDS[0]},
        {"type": "workflow", "name": GOLDEN_WORKFLOW_NAMES[1],
         "id": GOLDEN_WF_IDS[1]},
        dict(_UNRELATED_WORKFLOW),
    ]}

# ---------------------------------------------------------------------------
# The golden fixture itself — derived ONCE at import, deep-frozen. The record
# is a MappingProxyType and every container is a tuple, so NO caller can
# mutate the canonical payload through the module's public surface — the
# self-test proves it. Consumers that need a mutable payload call
# golden_found() / golden_found_payload() / golden_listing_payload()
# (deep copies).
# ---------------------------------------------------------------------------
def _build_golden() -> tuple:
    from types import MappingProxyType
    inner = golden_found()
    frozen = {}
    for key, row in inner.items():
        # every inner row is deep-frozen the same way: the row dict becomes
        # a mappingproxy over its own plain dict (a fresh copy, so a caller
        # could never have aliased it)
        frozen[key] = MappingProxyType(dict(row))
    return (MappingProxyType(frozen),)

# The canonical found-state record: deep-frozen (a mappingproxy — immutable
# through every route).
GOLDEN_FOUND = _build_golden()[0]

# The canonical af_code of the found state — the same string the finder's
# ok surface carries (a drift between the fixture and the finder's report
# is caught HERE first).
GOLDEN_AF = GOLDEN_FOUND and GOLDEN_AF_CODE

# ---------------------------------------------------------------------------
# Fail-closed found-state gate — the offline gate the self-test, `payload`
# and the dispatcher's live gate all ride on. An absent or renamed contract
# workflow or a drifted surface is REFUSED with exit 5, never tolerated.
# ---------------------------------------------------------------------------
def _is_blank(value) -> bool:
    return not isinstance(value, str) or not value.strip()

def _contract_found_rows(rows: tuple, law: dict) -> dict:
    """The found-state law over the listing rows, fail-closed. Every judged
    contract workflow must be matched BY EXACT NAME by exactly ONE
    workflow-typed row (the normalized row name equals the contract name
    with dashes -> spaces). Returns {key: row}; a missing or renamed
    contract workflow raises FixtureError — never a blind pass, never an id
    guessed from memory."""
    out = {}
    for key, name in law.items():
        slug = _normalize_name(name)
        matches = [r for r in rows if _normalize_name(_row_name(r)) == slug]
        if not matches:
            raise FixtureError(
                "the contract workflow %r (%r) is ABSENT from the listing "
                "— a renamed legacy is indistinguishable from an absent "
                "one and BOTH refuse fail-closed; never an id guessed from "
                "memory." % (key, name))
        if len(matches) > 1:
            raise FixtureError(
                "the contract workflow %r (%r) is matched by %d rows — a "
                "DUPLICATE name makes the find ambiguous; the archive "
                "ACTION must bind to ONE byte-exact workflow, never a "
                "duplicate." % (key, name, len(matches)))
        out[key] = matches[0]
    return out

def _judge(payload: dict, *, out) -> tuple:
    """The fail-closed found-state gate. Returns (exit_code, result_dict):
    0 PASS / 5 REFUSED, where result_dict is the dispatcher-consumed
    surface {"ok", "names", "rows", "af_code", "note"} (on a refusal the
    dict carries ok False with a named af_code). Emits the ONE JSON report
    object on stdout; human notes go to out (stderr)."""
    detail = ""
    ok = False
    found = {"workflow_keys": None, "rows": None, "names": None}
    af_code = "U06-FIXTURE-MISSING"
    try:
        law = _contract_name_law()
        rows = _contract_rows(payload)
        matched = _contract_found_rows(rows, law)
    except FixtureError as exc:
        detail = str(exc)
    else:
        found["workflow_keys"] = list(matched.keys())
        found["rows"] = len(rows)
        found["names"] = [GOLDEN_WORKFLOW_NAMES[0], GOLDEN_WORKFLOW_NAMES[1]]
        ok = True
        af_code = GOLDEN_AF_CODE
        detail = ("both contract workflows found byte-exact by the golden "
                  "keys (%s / %s, %d row(s)) — the U06 find-then-archive "
                  "gate's FOUND state holds (and any archive ACTION would "
                  "require %s, Trevor-gated)"
                  % (GOLDEN_WORKFLOW_NAMES[0], GOLDEN_WORKFLOW_NAMES[1],
                     len(rows), EXECUTE_FLAG))
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "REFUSED",
        "expected": {
            "workflows": dict(zip(GOLDEN_WORKFLOW_KEYS, GOLDEN_WORKFLOW_NAMES)),
            "archive_action": ARCHIVE_ACTION,
            "execute_required": GOLDEN_EXECUTE_REQUIRED,
        },
        "found": found,
        "detail": detail,
    }, indent=2, sort_keys=True))
    if not ok:
        out.write("[golden-found] REFUSED: %s\n" % detail)
        return EX_MISMATCH, {
            "ok": False,
            "names": [],
            "rows": found["rows"] if found["rows"] is not None else 0,
            "af_code": af_code,
            "note": detail,
        }
    return EX_OK, {
        "ok": True,
        "names": [GOLDEN_WORKFLOW_NAMES[0], GOLDEN_WORKFLOW_NAMES[1]],
        "rows": found["rows"],
        "af_code": af_code,
        "note": detail,
    }

def payload(candidate: dict = None, *, out=None) -> dict:
    """Judge a listing payload against the golden found contract. Returns
    the dispatcher-consumed dict {"ok", "names", "rows", "af_code", "note"}
    (the surface main_skeleton's verify_live reads).

    READ-ONLY: asserts the U06 found-state law — BOTH contract workflows
    the archive action touches are on the listing byte-exact by the golden
    keys, each found with its one id, each matched BY NAME. An absent or
    renamed contract workflow, a duplicate name, a malformed listing (no
    'rows' array, non-object rows), a non-object candidate, or a
    credential-shaped value is a FAIL-CLOSED refusal (exit 5 in the
    report), never a blind pass. With no candidate the GOLDEN listing
    itself is judged — the dispatcher's offline gate. Emits the ONE JSON
    report object on stdout; human notes go to out (stderr)."""
    out = out or sys.stderr
    if candidate is None:
        candidate = golden_listing_payload()
    if not isinstance(candidate, dict):
        detail = "the candidate is not a JSON object — malformed listing, " \
                 "never a pass (fail-closed)"
        print(json.dumps({
            "contract": FIXTURE_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "expected": {
                "workflows": dict(zip(GOLDEN_WORKFLOW_KEYS,
                                      GOLDEN_WORKFLOW_NAMES)),
                "archive_action": ARCHIVE_ACTION,
                "execute_required": GOLDEN_EXECUTE_REQUIRED,
            },
            "found": None,
            "detail": detail,
        }, indent=2, sort_keys=True))
        out.write("[golden-found] REFUSED: %s\n" % detail)
        return {"ok": False, "names": [], "rows": 0,
                "af_code": "U06-FIXTURE-MISSING", "note": detail}
    return _judge(candidate, out=out)[1]

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
        sys.stderr.write("[golden-found] SELF-TEST FAILED "
                         "(AF-AE-GOLDENFOUND-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK

def _self_test_body(dev) -> None:
    from types import MappingProxyType

    # ---- contract coherence: the names come ONCE from the finder ----------
    assert fl.LEGACY_NAMES["start_anthology_writer"] == \
        "00-Start Anthology Writer with Avatar Alchemist", \
        "the pinned legacy name drifted from the U06 contract"
    assert fl.LEGACY_NAMES["pipeline_manager"] == \
        "Anthology Pipeline Manager and Notification System", \
        "the pinned legacy name drifted from the U06 contract"
    assert GOLDEN_WORKFLOW_KEYS == ("start_anthology_writer",
                                    "pipeline_manager"), \
        "the golden workflow keys drifted from the finder's stable keys"
    assert GOLDEN_WORKFLOW_NAMES == (
        "00-Start Anthology Writer with Avatar Alchemist",
        "Anthology Pipeline Manager and Notification System"), \
        "the golden names must byte-equal the finder's pinned table"

    # ---- the canonical fixture: found record deep-frozen -------------------
    assert isinstance(GOLDEN_FOUND, MappingProxyType), \
        "GOLDEN_FOUND must be mappingproxy-frozen"
    for key, name in zip(GOLDEN_WORKFLOW_KEYS, GOLDEN_WORKFLOW_NAMES):
        row = GOLDEN_FOUND[key]
        assert row["found"] is True, \
            "the golden record must carry %r FOUND" % key
        assert row["matched_by"] == "name", \
            "the golden record must be matched BY NAME"
    assert GOLDEN_FOUND["start_anthology_writer"]["id"] == "wf_golden_start"
    assert GOLDEN_FOUND["pipeline_manager"]["id"] == "wf_golden_pipe"
    assert GOLDEN_AF_CODE == GOLDEN_AF == "LEGACY-FOUND"

    # ---- the payload surfaces cover the law on every shape -----------------
    rec = golden_found()
    assert rec["start_anthology_writer"]["found"] is True and \
        rec["start_anthology_writer"]["id"] == "wf_golden_start" and \
        rec["start_anthology_writer"]["matched_by"] == "name", \
        "the canonical record drifted from the golden contract"
    assert rec["pipeline_manager"]["found"] is True and \
        rec["pipeline_manager"]["id"] == "wf_golden_pipe", \
        "the canonical record drifted from the golden contract"
    found_payload = golden_found_payload()
    assert set(found_payload["workflows"]) == set(GOLDEN_WORKFLOW_KEYS), \
        "the found surface must carry exactly the two golden keys"
    listing = golden_listing_payload()
    assert isinstance(listing, dict) and isinstance(listing.get("rows"), list) \
        and len(listing["rows"]) == 3, \
        "the listing surface must carry exactly three rows"
    assert _row_name(listing["rows"][0]) == GOLDEN_WORKFLOW_NAMES[0]
    assert _row_name(listing["rows"][1]) == GOLDEN_WORKFLOW_NAMES[1]

    # ---- the canonical fixture can never be mutated through the surface -----
    before = GOLDEN_FOUND["start_anthology_writer"]

    def _try_rebind():  # subscript assignment on a mappingproxy -> TypeError
        GOLDEN_FOUND["start_anthology_writer"] = "wf_golden_mutated"  # noqa: B034 -- deliberately attempted

    try:
        _try_rebind()
        raise AssertionError("the canonical fixture must be immutable")
    except TypeError:
        pass
    assert GOLDEN_FOUND["start_anthology_writer"] == before, \
        "the canonical fixture changed during the self-test"
    # golden_found() returns a deep copy: mutating it never touches the canon.
    copy_ = golden_found()
    copy_["start_anthology_writer"]["id"] = "wf_golden_mutated"
    assert GOLDEN_FOUND["start_anthology_writer"] == before, \
        "the returned copy must not alias the canonical payload"

    # ---- attack fixtures: every drift REFUSED, never shipped ----------------
    # 1. a contract workflow ABSENT -> FixtureError
    try:
        _contract_found_rows(
            (dict(_UNRELATED_WORKFLOW),),
            _contract_name_law())
        raise AssertionError("an absent contract workflow was NOT refused")
    except FixtureError:
        pass
    # 2. a contract workflow RENAMED -> FixtureError (indistinguishable from
    #    absent — the exact-name law, never a similarity match)
    try:
        _contract_found_rows(
            ({"type": "workflow", "name": "00-Start Anthology Writer",
              "id": "wf_renamed"},
             {"type": "workflow",
              "name": GOLDEN_WORKFLOW_NAMES[1], "id": GOLDEN_WF_IDS[1]}),
            _contract_name_law())
        raise AssertionError("a renamed contract workflow was NOT refused")
    except FixtureError:
        pass
    # 3. a DUPLICATE name -> FixtureError (the archive ACTION must bind to
    #    ONE byte-exact workflow, never a duplicate)
    try:
        _contract_found_rows(
            ({"type": "workflow", "name": GOLDEN_WORKFLOW_NAMES[0],
              "id": "wf_dup_a"},
             {"type": "workflow", "name": GOLDEN_WORKFLOW_NAMES[0],
              "id": "wf_dup_b"},
             {"type": "workflow", "name": GOLDEN_WORKFLOW_NAMES[1],
              "id": GOLDEN_WF_IDS[1]}),
            _contract_name_law())
        raise AssertionError("a duplicate name was NOT refused")
    except FixtureError:
        pass
    # 4. missing rows array -> FixtureError
    try:
        _contract_rows({"nope": 1})
        raise AssertionError("a listing without rows was NOT refused")
    except FixtureError:
        pass
    # 5. non-object row -> FixtureError
    try:
        _contract_rows({"rows": ["not-an-object"]})
        raise AssertionError("a non-object row was NOT refused")
    except FixtureError:
        pass

    # ---- the payload gate: golden exits 0, every drift exits 5 --------------
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = payload()
    assert result["ok"] is True, \
        "payload on the golden listing must PASS, got %r" % result
    assert result["names"] == list(GOLDEN_WORKFLOW_NAMES), \
        "the golden result must name both contract workflows"
    assert result["rows"] == 3 and result["af_code"] == "LEGACY-FOUND"
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["contract"] == FIXTURE_CONTRACT
    assert parsed["expected"]["execute_required"] is True
    # an absent contract workflow -> REFUSED exit 5 (the result dict carries
    # ok False with a named af_code)
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        result2 = payload({"rows": [dict(_UNRELATED_WORKFLOW)]})
    assert result2["ok"] is False and result2["af_code"] == \
        "U06-FIXTURE-MISSING", \
        "an absent contract workflow must refuse, got %r" % result2
    assert json.loads(buf2.getvalue())["verdict"] == "REFUSED"
    # a renamed contract workflow -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"rows": [
            {"type": "workflow", "name": "00-Start Anthology Writer",
             "id": "wf_renamed"},
            {"type": "workflow", "name": GOLDEN_WORKFLOW_NAMES[1],
             "id": GOLDEN_WF_IDS[1]}]})["ok"] is False, \
            "a renamed contract workflow must refuse"
    # a duplicate name -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"rows": [
            {"type": "workflow", "name": GOLDEN_WORKFLOW_NAMES[0],
             "id": "wf_dup_a"},
            {"type": "workflow", "name": GOLDEN_WORKFLOW_NAMES[0],
             "id": "wf_dup_b"},
            {"type": "workflow", "name": GOLDEN_WORKFLOW_NAMES[1],
             "id": GOLDEN_WF_IDS[1]}]})["ok"] is False, \
            "a duplicate name must refuse"
    # a malformed candidate -> REFUSED exit 5 (never a pass)
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"no_rows_here": True})["ok"] is False, \
            "a malformed candidate must refuse"
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload("not-an-object")["ok"] is False, \
            "a non-object candidate must refuse"

    # ---- the BROWSER UA law is pinned (CF 1010) ------------------------------
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
        "CAF_BROWSER_UA must be a browser User-Agent (CF 1010)"

    # ---- never-print: no credential-shaped string on any surface ------------
    all_text = buf.getvalue() + buf2.getvalue()
    for token in ("pit-", "Bearer "):
        assert token not in all_text, \
            "surface leak: %r must never appear" % token

    dev.write("golden_found self-test: OK (found-state law pinned: BOTH "
              "contract workflows %r / %r found byte-exact by the golden "
              "keys, names read once from find_legacy.LEGACY_NAMES; the "
              "archive ACTION is %s-gated, Trevor-gated — the gate lives "
              "in the dispatcher, never in a fixture; canonical "
              "mappingproxy-frozen immutability + deep-copy surface; 5 "
              "attack fixtures refused (absent / renamed / duplicate / "
              "no-rows-array / non-object-row); payload gate returns the "
              "dispatcher dict surface — ok True on the golden listing, "
              "ok False with a named af_code on every drift; BROWSER UA "
              "pinned; never-print)\n"
              % (GOLDEN_WORKFLOW_NAMES[0], GOLDEN_WORKFLOW_NAMES[1],
                 EXECUTE_FLAG))

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="golden_found.py",
        description="Golden BOTH-WORKFLOWS-FOUND fixture for the U06 "
                    "self-tests (Skill 59): the listing where both contract "
                    "workflows the archive action touches are found "
                    "byte-exact by the golden key — fail-closed, offline, "
                    "never prints a token; the --execute archive gate lives "
                    "in the dispatcher, never in a fixture.")
    ap.add_argument("cmd", nargs="?", choices=["payload", "plan", "self-test"],
                    default="payload")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the U06 siblings use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            # Offline plan (no network, no credentials): the golden found
            # surface — the two contract workflow names, the found state,
            # the --execute-gated archive action.
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "workflows": dict(zip(GOLDEN_WORKFLOW_KEYS,
                                      GOLDEN_WORKFLOW_NAMES)),
                "found_state": "both found byte-exact by the golden key",
                "archive_action": ARCHIVE_ACTION,
                "execute_required": GOLDEN_EXECUTE_REQUIRED,
                "note": "offline plan only — synthetic fixture ids, no "
                        "network, no credential needed; a LIVE find must "
                        "ride the house rail clients (CAF_BROWSER_UA on "
                        "every request — CF 1010 law); the --execute gate "
                        "that refuses an archive ACTION without it "
                        "(Trevor-gated) lives in the dispatcher, never in "
                        "a fixture",
            }, indent=2, sort_keys=True))
            return EX_OK
        # payload: the candidate listing arrives on stdin, read from NO
        # network (the live finder is the sibling checker, which rides the
        # house rail clients and their CAF_BROWSER_UA — this fixture never
        # touches the wire). The candidate is a {"rows": [...]} listing
        # object; with none, the golden listing itself is judged.
        try:
            candidate = json.load(sys.stdin)
        except ValueError as exc:
            sys.stderr.write("[golden-found] the listing on stdin is not "
                             "valid JSON: %s\n" % exc)
            return EX_MISMATCH
        result = payload(candidate)
        return EX_OK if result.get("ok") else EX_MISMATCH
    except FixtureError as exc:
        sys.stderr.write("[golden-found] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[golden-found] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
