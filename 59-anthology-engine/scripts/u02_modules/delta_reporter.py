#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules/delta_reporter.py
# JSON DELTA REPORTER — diffs live vs expected, names every delta, never a
# secret (U02 tooling, extension module).
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u02_modules/ — an importable module under the U02
# template-verify tooling, reached by the SAME sys.path.insert bootstrap the
# other sibling imports use (imported BY NAME as u02_modules.delta_reporter,
# per the u02_modules package contract in __init__.py: pure namespace
# container). It is NOT a manifest row: it ships as a sibling helper, exactly
# the way delivery_report.py ships as the sibling helper of caf_delivery.py
# (ENGINE-MANIFEST row 12 pattern) — the U02 verifier stays the single
# manifest row while this module owns the delta/report surface.
#
# WHAT THIS OWNS
#   1. THE DELTA REPORT CONTRACT. The U02 verifier (ENGINE-MANIFEST.json
#      row 54) and its check modules record per-item (status, detail,
#      expected, live) tuples; the REPORT is the machine deliverable: ONE
#      JSON object on stdout with a per-item checks map, a `delta` list that
#      NAMES EVERY mismatch (item + expected + live + detail — never a bare
#      "something failed"), the fail-closed aggregate verdict, and the
#      fail_closed block (any_fail / deferred / allow_deferred). This module
#      is the single implementation of that contract so the verifier, the
#      skeleton dispatcher, and the live check modules can never drift apart.
#   2. DELTA COMPUTATION, CONTRACT-DRIVEN AND FAIL-CLOSED:
#        - missing    : an item in the expected set is absent from live
#        - extra      : an item in the live set was never expected
#        - value      : an item present in both, but its value differs
#      Every deviation is NAMED with its contract path. A caller that passes
#      a malformed input (non-list expected/live, a row without its key) is
#      REFUSED (DeltaReporterError) — a report that cannot name its own
#      expectations must not run (never a blind pass, never a fabricated
#      success).
#   3. SECRET HYGIENE. The report carries KEYS, NAMES, and DERIVED BOOLEANS
#      only. A credential-shaped string (a `pit-` token value) is never
#      accepted into a report; the sanitizer REFUSES the whole delta rather
#      than emit a redacted guess. Custom-value payloads are rendered as
#      "REPLACE-ME" when placeholder-marked and "(real — refused)" otherwise
#      — the VALUE itself is never surfaced (never-a-real-token doctrine).
#   4. LIVE SURFACE (optional, house client only). When handed an already
#      built reg.CafClient / reg.InternalRailClient (the registry's clients
#      apply the CAF_BROWSER_UA on EVERY request so the Cloudflare edge
#      fronting services.leadconnectorhq.com never 1010s the report — CF
#      error 1010 / GK-09 discipline), the module can fetch the live
#      pipeline / custom-field / custom-value / workflow-row surfaces and
#      produce the delta report. Scope-vs-edge-block discrimination is the
#      registry's own (a bare 401/403 is HELD, never mislabeled as a scope
#      problem). The module itself has ZERO credential surface: it never
#      resolves a token — the caller owns that (SET / NOT SET only).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE, everywhere this module is used.
# A token value is never printed, echoed, or reflected in any surface.
#
# FAIL-CLOSED (the whole point): a malformed input, an unreadable contract,
# a live read that cannot be completed, or a credential-shaped value in a
# record is a REFUSAL (raise) or a recorded FAIL — never a silent pass,
# never a fabricated success. A DEFERRED live read (internal-rail credential
# NOT SET) is reported with the deferral named, never invented.
#
# RETURN CONTRACT (the machine surface this module owns):
#   diff_expected_live(expected, live, *, kind="items") -> list
#       every deviation as {"item", "expected", "live", "detail"} — [] when
#       the sets agree exactly. Raises DeltaReporterError on malformed input.
#   build_report(checks, *, allow_deferred=False, location_marker="",
#                contract="anthology-engine-u02-delta-report") -> dict
#       the ONE JSON report object (checks / verdict / delta / fail_closed).
#   emit_report(report, out=sys.stdout) -> None
#       print ONE JSON object (indent 2, sort_keys) — the house surface.
#   The CLI (main) additionally offers verify / plan / self-test against the
#   template location, mirroring the U02 check modules' house shape; it
#   resolves the PIT BY LABEL through anthology_registry and constructs
#   reg.CafClient (browser UA on every request).
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation):
#   0  all checks PASS (also plan / self-test / dry-run)
#   1  unexpected error
#   2  STOP refusal — label NOT SET / non-pit- value / usage / contract
#      section missing
#   3  Convert and Flow API unreachable / internal rail unavailable (HELD;
#      retryable, never mislabeled as scope)
#   4  self-test FAILED (AF-AE-TEMPLATE-ATTACK family — a tamper NEVER
#      masquerades as exit 1)
#   5  data or read-back mismatch (any FAIL or a DEFERRED live read without
#      --allow-deferred — fail-closed default)
#
# STDLIB ONLY (urllib + json via the registry); calls NO model. Reuses
# anthology_registry (CafClient, InternalRailClient, resolve_pit,
# resolve_location, load_field_map, _stop, _mask_location). DOCTRINE: move
# in silence; NOTHING Anthropic in any runtime file; Convert and Flow naming
# in every client surface; never print a secret value; --plan and --self-test
# are OFFLINE.
# =============================================================================
"""delta_reporter.py — JSON delta report: diffs live vs expected, names every
delta, never a secret (U02 tooling, Skill 59)."""

from __future__ import annotations

import argparse
import copy
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the LeadConnector client + label resolution,
# and its exit-code constants are the house contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The report pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# The never-a-real-token markers a template custom value must carry. A value
# that is neither empty nor marker-labeled is REAL and REFUSED — and its
# payload is never surfaced (the same marker set live_verify_template.py and
# u02_modules/custom_values_check.py use for the same template gate).
PLACEHOLDER_MARKERS = ("REPLACE-ME", "replace-me", "<PUBLIC_HOSTNAME>")

# The one fixed report contract. Every report this module emits carries it,
# so a machine consumer can never mistake another JSON object for a delta
# report (and the self-test asserts the golden report carries the exact
# string — the report contract is load-bearing).
REPORT_CONTRACT = "anthology-engine-u02-delta-report"

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (e.g. "pit-abc123"). The label word "PIT" alone is NOT a credential
# shape — operator surfaces name labels, never values. The self-test proves
# the pattern discriminates both ways.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


class DeltaReporterError(Exception):
    """A fail-closed report refusal (STOP or mismatch family): malformed
    input, an unreadable contract, or a credential-shaped value in a
    record. A report that cannot name its own expectations must not run."""


# ---------------------------------------------------------------------------
# Secret hygiene — the report surface NEVER carries a credential value.
# ---------------------------------------------------------------------------
def _is_placeholder(value: str) -> bool:
    """True when a custom-value payload is a clearly-labeled placeholder:
    empty or carrying a PLACEHOLDER_MARKERS marker. A real-looking value
    (e.g. https://... or Bearer ...) is NOT a placeholder. Only the fixed
    marker substrings are matched — the value itself is never printed."""
    v = (value or "").strip()
    if not v:
        return True
    return any(marker in v for marker in PLACEHOLDER_MARKERS)


def _safe_text(value) -> str:
    """Coerce any scalar to a STRING for a report field without ever
    surfacing a credential value: a pit- token shape REFUSES (the whole
    report fails closed), everything else renders plainly. The value is
    never reflected verbatim past this gate."""
    if value is None:
        return ""
    text = str(value)
    if _CREDENTIAL_SHAPE.search(text):
        raise DeltaReporterError(
            "a record carries a credential-shaped value; the report surface "
            "never prints a token — fix the source, not the report")
    return text


def _render_value(value) -> str:
    """Render one custom-value payload for a report field: 'REPLACE-ME' when
    it is a placeholder, '(real — refused)' when it is not. The VALUE itself
    is never surfaced (never-a-real-token; live_verify_template doctrine)."""
    if isinstance(value, (dict, list)):
        return "(structured — not rendered)"
    return "REPLACE-ME" if _is_placeholder(_safe_text(value)) else "(real — refused)"


def _value_of(item) -> str:
    """The single compare key of one expected/live row: 'key' when the row
    carries one (custom values — a real-looking VALUE is never a compare
    key: the never-a-real-token gate keys by the contract KEY), else 'name'
    (pipelines / stages / fields). Missing in both is a refusal — a report
    cannot diff an unnameable row. Missing in ONE side is a plain
    difference (value vs empty), never a refusal: an absent live row is
    exactly the delta being reported."""
    if isinstance(item, dict):
        if "key" in item:
            return "key"
        if "name" in item:
            return "name"
        if "value" in item:
            return "value"
    raise DeltaReporterError(
        "an expected/live row carries neither 'name' nor 'key' nor 'value' "
        "— the delta report cannot name it")


def _item_key(item, key_field: str) -> str:
    """The identity string of one row under its key field. A missing key is
    a refusal (fail-closed: unnameable rows are never diffed, never passed)."""
    if not isinstance(item, dict):
        raise DeltaReporterError(
            "an expected/live row is not an object (%s) — the delta report "
            "cannot name it" % type(item).__name__)
    raw = item.get(key_field)
    text = _safe_text(raw)
    if not text:
        raise DeltaReporterError(
            "an expected/live row carries an empty %r — the delta report "
            "cannot name it" % key_field)
    return text


def _live_payload(item: dict, key_field: str) -> str:
    """The payload rendered for the 'live' column of a delta row: the
    sanitized value for custom-value rows (keyed BY KEY — see _value_of),
    the plain name otherwise. Never a raw payload."""
    if key_field == "value":
        return _render_value(item.get("value"))
    return _safe_text(item.get(key_field))


def _expected_payload(item: dict, key_field: str) -> str:
    """The payload rendered for the 'expected' column of a delta row. For
    custom values the EXPECTED is the placeholder marker set itself (the
    contract, not a guess at a value); for everything else the plain name."""
    if key_field == "value":
        return "placeholder (%s)" % " / ".join(PLACEHOLDER_MARKERS)
    return _safe_text(item.get(key_field))


# ---------------------------------------------------------------------------
# The diff — names EVERY delta. Fail-closed: malformed input REFUSES.
# ---------------------------------------------------------------------------
def diff_expected_live(expected, live, *, kind: str = "items",
                       order_bearing: bool = False) -> list:
    """Diff two row sets and name every deviation as a delta.

    Returns a list of {"item", "expected", "live", "detail"} — EMPTY when the
    sets agree exactly (same keys, same names, same values — the golden
    report). Every deviation is named with its contract path:

      missing: an expected key absent from live      (strict subset -> STOP
               family upstream, recorded here verbatim)
      extra  : a live key never expected             (drift, never ignored)
      value  : a key present in both, but the value differs (custom values)
      order  : with `order_bearing=True` (the STAGE surface — the contract
               is BY NAME IN ORDER), a permutation of the same names is a
               named order delta at the first drifted position. Field keys
               are NOT order-bearing (live key lists are sorted sets); the
               stage surface opts in explicitly.

    Fail-closed: `expected` / `live` must be lists of dicts whose rows carry
    a 'key' / 'name' / 'value' identity (custom-value rows are keyed BY KEY,
    with the placeholder contract asserted separately; everything else by
    name). A credential-shaped string anywhere REFUSES the whole diff
    (DeltaReporterError) — never a redacted guess, never a partial report.
    """
    if not isinstance(expected, list) or not isinstance(live, list):
        raise DeltaReporterError(
            "expected and live must both be lists for %r — got %s and %s"
            % (kind, type(expected).__name__, type(live).__name__))
    if not expected:
        raise DeltaReporterError(
            "empty expected set for %r — a diff that cannot name its own "
            "expectations must not run (a report over nothing would be a "
            "fabricated success)" % (kind,))

    want = {_item_key(item, _value_of(item)): (item, _value_of(item))
            for item in expected}
    got = {_item_key(item, _value_of(item)): (item, _value_of(item))
            for item in live}
    want_keys, got_keys = set(want), set(got)

    delta = []
    for key in sorted(want_keys - got_keys):
        item, key_field = want[key]
        delta.append({
            "item": key,
            "expected": _expected_payload(item, key_field),
            "live": "(absent)",
            "detail": "%s missing: %r is in the expected set but not in live"
                      % (kind, key),
        })
    for key in sorted(got_keys - want_keys):
        item, key_field = got[key]
        delta.append({
            "item": key,
            "expected": "(not expected)",
            "live": _live_payload(item, key_field),
            "detail": "%s extra: %r is in live but was never expected"
                      % (kind, key),
        })
    # LIST-ORDER LAW: for ORDER-BEARING surfaces the ORDER of the rows is
    # load-bearing (the U02 stage contract is BY NAME IN ORDER with
    # contiguous positions; a UI reorder that renumbers positions must be
    # caught). The union of a set-diff over keyed rows is order-blind, so a
    # permutation of the same names would diff to an empty delta — exactly
    # the reorder attack. The caller opts in per surface with
    # `order_bearing=True` (the stage surface — a sorted live key list is
    # NOT a claimed live order, so the field surface never opts in). When
    # every expected name is present, no extra name exists, and the caller
    # claims the surface order-bearing, compare the live names against the
    # expected names IN LIST ORDER; the first position where they differ is
    # a named value delta (the item whose slot moved, both sides named).
    if order_bearing and not delta and not got_keys - want_keys \
            and got_keys == want_keys \
            and all(_value_of(i) == "name" for i in expected):
        want_order = [_item_key(i, "name") for i in expected]
        live_order = [_item_key(i, "name") for i in live]
        for pos, (w_name, l_name) in enumerate(zip(want_order, live_order)):
            if w_name != l_name:
                delta.append({
                    "item": l_name,
                    "expected": w_name,
                    "live": l_name,
                    "detail": "%s order drift at position %d: expected %r, "
                              "live %r (the stage law is BY NAME IN ORDER)"
                              % (kind, pos, w_name, l_name),
                })
                break

    # CUSTOM-VALUE LAW: a custom-value row is keyed BY KEY, never by value —
    # a real-looking value on the live side is the exact attack this gate
    # exists for, and keying on the value would turn it into an "extra" key.
    # The key-set diff above already compared the KEY identity; here the
    # placeholder contract is asserted for every key present in both sets:
    # a live payload that is not a placeholder is a named value delta with
    # the contract KEY as the item, the placeholder contract as expected,
    # and the marker string as live — the payload itself is never surfaced
    # (never-a-real-token). Note the value-keyed rows are detected by the
    # FIELD the row declares (any row carrying a 'value' key is value-keyed
    # and keyed BY KEY for identity), not by the chosen compare field.
    for key in sorted(want_keys & got_keys):
        want_item, key_field = want[key]
        got_item, _ = got[key]
        value_keyed = isinstance(want_item, dict) and "value" in want_item
        if not value_keyed:
            want_v = (want_item.get(key_field) or "")
            got_v = (got_item.get(key_field) or "")
            if _safe_text(want_v) != _safe_text(got_v):
                delta.append({
                    "item": key,
                    "expected": _safe_text(want_v),
                    "live": _safe_text(got_v),
                    "detail": "%s value drift: expected %r, live %r"
                              % (kind, _safe_text(want_v), _safe_text(got_v)),
                })
            continue
        want_v = (want_item.get("value") or "")
        got_v = (got_item.get("value") or "")
        if _is_placeholder(want_v) != _is_placeholder(got_v):
            live_marker = _render_value(got_item.get("value"))
            delta.append({
                "item": key,
                "expected": "placeholder (%s)" % " / ".join(PLACEHOLDER_MARKERS),
                "live": live_marker,
                "detail": "%s value drift: expected a placeholder, live "
                          "carries %s (never-a-real-token)" % (
                              kind, live_marker),
            })
    return delta


# ---------------------------------------------------------------------------
# The report — ONE JSON object, fail-closed aggregate.
# ---------------------------------------------------------------------------
def build_report(checks: dict, *, allow_deferred: bool = False,
                 location_marker: str = "",
                 contract: str = REPORT_CONTRACT) -> dict:
    """Assemble the ONE delta report object from a per-item checks map.

    checks maps item name -> {"status": PASS|FAIL|DEFERRED, "detail": str,
    "expected": ..., "live": ...} (the exact record shape the U02 verifier's
    check_* primitives and the skeleton dispatcher already emit). Every item
    whose status is not PASS is NAMED in `delta` with its expected/live
    record and its detail — a report never says "something failed".

    Fail-closed: a check row with an unknown status or a missing detail is a
    refusal (DeltaReporterError); a DEFERRED live read (internal-rail
    credential NOT SET) is a FAIL unless --allow-deferred (the operator's
    explicit opt-in), and the report says so in its own fail_closed block.
    """
    if not isinstance(checks, dict) or not checks:
        raise DeltaReporterError(
            "build_report needs a non-empty checks map — a report over "
            "nothing would be a fabricated success")

    normalized = {}
    for name, rec in checks.items():
        if not isinstance(rec, dict):
            raise DeltaReporterError(
                "check %r record is not an object (%s)"
                % (name, type(rec).__name__))
        status = rec.get("status")
        if status not in ("PASS", "FAIL", "DEFERRED"):
            raise DeltaReporterError(
                "check %r carries unknown status %r (PASS / FAIL / DEFERRED)"
                % (name, status))
        detail = rec.get("detail")
        if not isinstance(detail, str) or not detail:
            raise DeltaReporterError(
                "check %r carries no detail — every non-PASS check is named "
                "with its detail, never a bare status" % name)
        normalized[name] = {
            "status": status,
            "detail": detail,
            "expected": rec.get("expected"),
            "live": rec.get("live"),
        }

    failures = sorted(n for n, r in normalized.items() if r["status"] == "FAIL")
    deferred = sorted(n for n, r in normalized.items() if r["status"] == "DEFERRED")
    delta = [{"item": n, "expected": r["expected"], "live": r["live"],
              "detail": r["detail"]}
             for n, r in normalized.items() if r["status"] != "PASS"]

    pass_all = (not failures and (allow_deferred or not deferred))
    report = {
        "contract": contract,
        "schema_version": 1,
        "location": location_marker,
        "verdict": "PASS" if pass_all else "FAIL",
        "checks": normalized,
        "delta": delta,
        "fail_closed": {
            "any_fail": bool(failures),
            "deferred": deferred,
            "allow_deferred": allow_deferred,
            "note": "a DEFERRED live read (internal-rail credential NOT SET) "
                    "counts as FAIL unless --allow-deferred — the report "
                    "never fabricates an unread surface.",
        },
    }
    return report


def emit_report(report: dict, out=None) -> None:
    """Print the ONE JSON object (indent 2, sort_keys) — the house machine
    surface. The payload has already passed the secret hygiene gate."""
    (out or sys.stdout).write(json.dumps(report, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Live surfaces (optional; house clients only — CAF_BROWSER_UA on every
# request via reg.CafClient / reg.InternalRailClient, CF 1010 / GK-09).
# ---------------------------------------------------------------------------
def _contract_field_keys(field_map: dict) -> list:
    """The intended field keys, straight from the field-map (the SINGLE
    SOURCE OF TRUTH — never a hardcoded list). A missing section is a
    refusal, never a pass."""
    fields = (field_map.get("provisioning") or {}).get("fields")
    if not isinstance(fields, list) or not fields:
        raise DeltaReporterError(
            "field-map.json has no provisioning.fields inventory — the delta "
            "report has no expected field set to diff against")
    keys = [f.get("intended_key") for f in fields if isinstance(f, dict)]
    if not keys:
        raise DeltaReporterError(
            "field-map provisioning.fields carries no intended_key entries")
    return keys


def _contract_stages(field_map: dict) -> list:
    """The standard stage names in contract order (positions 0..8), from the
    field-map. A malformed pipeline section is a refusal."""
    pconf = field_map.get("pipeline")
    if not isinstance(pconf, dict):
        raise DeltaReporterError(
            "field-map pipeline section missing or not an object")
    raw = pconf.get("standard_stages")
    if not isinstance(raw, list) or not raw:
        raise DeltaReporterError(
            "field-map pipeline.standard_stages is not a non-empty list")
    names = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise DeltaReporterError(
                "field-map stage %d is not an object (%s)"
                % (i, type(entry).__name__))
        nm = entry.get("name")
        if not isinstance(nm, str) or not nm:
            raise DeltaReporterError("field-map stage %d name missing or empty" % i)
        if entry.get("position") != i:
            raise DeltaReporterError(
                "field-map stage %d position %r != %d — the contract must be "
                "contiguous 0..%d" % (i, entry.get("position"), i, len(raw) - 1))
        names.append(nm)
    return names


def _contract_custom_value_keys(contract: dict) -> list:
    """The contract's required location custom-value keys. A missing section
    is a refusal (never a blind pass)."""
    rows = ((contract.get("location_custom_values") or {}).get("required") or [])
    if not isinstance(rows, list) or not rows:
        raise DeltaReporterError(
            "contract location_custom_values.required is missing or empty")
    keys = [cv.get("key") for cv in rows if isinstance(cv, dict) and cv.get("key")]
    if not keys:
        raise DeltaReporterError(
            "contract location_custom_values.required carries no keys")
    return keys


def _custom_values_expected(contract: dict) -> list:
    """The expected custom-value rows: the contract keys, each carrying the
    contract's placeholder as its 'value' — the expected surface is the
    placeholder, never a real token."""
    rows = ((contract.get("location_custom_values") or {}).get("required") or [])
    return [{"key": cv.get("key"), "value": (cv.get("placeholder") or "REPLACE-ME")}
            for cv in rows if isinstance(cv, dict) and cv.get("key")]


def _live_stage_names(pipelines, want_name: str) -> list:
    """The stage names of the standard pipeline, in list order. An absent
    pipeline is an empty list — the missing-pipeline delta is the caller's
    job (STOP upstream)."""
    found = next((p for p in pipelines if p.get("name") == want_name), None)
    if found is None:
        return []
    return [s.get("name") or "" for s in (found.get("stages") or [])
            if isinstance(s, dict)]


def live_delta_report(client, location_id: str, field_map: dict, contract: dict,
                      *, kind: str = "all") -> dict:
    """Build the delta report from the LIVE surfaces through a house client.

    `client` is a reg.CafClient (or an in-memory fake with the same read
    methods): list_pipelines / list_custom_fields / list_custom_values —
    the registry client applies CAF_BROWSER_UA on EVERY request, so the
    Cloudflare edge never 1010s the report (CF 1010 / GK-09). `kind`
    selects the surfaces to diff: "pipeline", "fields", "custom_values", or
    "all" (default). Raises reg.ScopeDenied / reg.CafUnreachable exactly as
    the registry surfaces them (STOP / HELD by the caller), and
    DeltaReporterError for a malformed contract (STOP).

    The report carries KEYS and DERIVED BOOLEANS only — the custom-value
    payloads are rendered as "REPLACE-ME" / "(real — refused)", never
    surfaced (never-a-real-token).
    """
    masked = reg._mask_location(location_id)
    checks = {}

    if kind in ("pipeline", "all"):
        want_name = ((field_map.get("pipeline") or {}).get("standard_pipeline_name")
                     or "Anthology Engine")
        want_stages = _contract_stages(field_map)
        pipes = client.list_pipelines(location_id)
        live_stages = _live_stage_names(pipes, want_name)
        stage_delta = diff_expected_live(
            [{"name": n} for n in want_stages],
            [{"name": n} for n in live_stages],
            kind="stage", order_bearing=True)
        checks["pipeline"] = {
            "status": "PASS" if (live_stages and not stage_delta) else "FAIL",
            "detail": ("standard pipeline %r present with all %d stages in "
                       "order" % (want_name, len(want_stages)))
            if (live_stages and not stage_delta)
            else "stage drift: %d expected vs %d live" % (
                len(want_stages), len(live_stages)),
            "expected": {"name": want_name, "stages": want_stages},
            "live": {"name": want_name if live_stages else "(absent)",
                     "stages": live_stages},
        }

    if kind in ("fields", "all"):
        want_keys = _contract_field_keys(field_map)
        fields = client.list_custom_fields(location_id)
        live_keys = sorted({f.get("fieldKey") for f in fields
                            if isinstance(f, dict) and f.get("fieldKey")})
        field_delta = diff_expected_live(
            [{"name": k} for k in want_keys],
            [{"name": k} for k in live_keys],
            kind="field")
        checks["custom_fields"] = {
            "status": "PASS" if not field_delta else "FAIL",
            "detail": ("all %d contract field keys present live, byte-exact"
                       % len(want_keys)) if not field_delta
            else "%d field key(s) drifted (%d expected vs %d live)"
                 % (len(field_delta), len(want_keys), len(live_keys)),
            "expected": {"count": len(want_keys)},
            "live": {"count": len(live_keys)},
        }

    if kind in ("custom_values", "all"):
        want_values = _custom_values_expected(contract)
        values = client.list_custom_values(location_id)
        live_values = [{"key": cv.get("key") or cv.get("name") or "",
                        "value": (cv.get("value") or "")}
                       for cv in values if isinstance(cv, dict)]
        value_delta = diff_expected_live(want_values, live_values,
                                         kind="custom_value")
        checks["custom_values"] = {
            "status": "PASS" if not value_delta else "FAIL",
            "detail": ("all %d contract custom values present as placeholders"
                       % len(want_values)) if not value_delta
            else "%d custom value(s) drifted (%d expected vs %d live)"
                 % (len(value_delta), len(want_values), len(live_values)),
            "expected": {"count": len(want_values)},
            "live": {"count": len(live_values)},
        }

    if not checks:
        raise DeltaReporterError(
            "live_delta_report: kind %r selects no surface — refusing to "
            "emit an empty report" % (kind,))

    return build_report(checks, location_marker=masked)


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials. ONE JSON object on stdout.
# ---------------------------------------------------------------------------
def plan(field_map: dict, contract: dict, *, location_id: str = "",
          out=None) -> int:
    """Offline plan: what the live delta report will diff, straight from the
    sources of truth (never a hardcoded list). No network, no credential."""
    out = out or sys.stderr
    try:
        stages = _contract_stages(field_map)
        keys = _contract_field_keys(field_map)
        cv_keys = _contract_custom_value_keys(contract)
    except DeltaReporterError as exc:
        out.write("[delta-reporter] plan STOP: %s\n" % exc)
        return EX_STOP
    print(json.dumps({
        "contract": REPORT_CONTRACT + "-plan",
        "schema_version": 1,
        "template_location_id": location_id,
        "pipeline": {
            "name": (field_map.get("pipeline") or {}).get("standard_pipeline_name"),
            "expected_stages": stages,
        },
        "custom_fields": {"expected_count": len(keys)},
        "custom_values": {"expected_keys": cv_keys},
        "note": "offline plan only — no network, no credential needed",
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden + attack fixtures, mutation proof, exit 4 on
# failure (a tamper NEVER masquerades as exit 1).
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow covering exactly the read surfaces the
    report uses (pipelines / custom fields / custom values), with a
    mutation log — self-tests prove the report only READS."""

    def __init__(self, pipelines=None, fields=None, values=None, behavior=None):
        self._pipelines = [dict(p) for p in (pipelines or [])]
        self._fields = [dict(f) for f in (fields or [])]
        self._values = [dict(v) for v in (values or [])]
        self.behavior = behavior  # None | scope | edge | transport
        self.calls = []

    def list_pipelines(self, location_id):
        self.calls.append(("pipelines", location_id))
        self._maybe_raise()
        return [dict(p) for p in self._pipelines]

    def list_custom_fields(self, location_id):
        self.calls.append(("fields", location_id))
        self._maybe_raise()
        return [dict(f) for f in self._fields]

    def list_custom_values(self, location_id):
        self.calls.append(("values", location_id))
        self._maybe_raise()
        return [dict(v) for v in self._values]

    def _maybe_raise(self):
        if self.behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self.behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self.behavior == "transport":
            raise reg.CafUnreachable("Convert and Flow transport error: URLError")


def _fake_field_map():
    return reg.load_field_map(FIELD_MAP_PATH)


def _fake_contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _golden_pipeline(field_map: dict) -> dict:
    pconf = field_map.get("pipeline") or {}
    return {
        "id": "pipe_tmpl",
        "name": pconf.get("standard_pipeline_name") or "",
        "stages": [{"position": s.get("position"), "name": s.get("name"),
                    "id": "stg_%s" % s.get("position")}
                   for s in (pconf.get("standard_stages") or [])
                   if isinstance(s, dict)],
    }


def _golden_fields(field_map: dict) -> list:
    return [{"fieldKey": f.get("intended_key"), "name": f.get("create_name"),
             "dataType": f.get("data_type", "LARGE_TEXT")}
            for f in (field_map.get("provisioning") or {}).get("fields", [])
            if isinstance(f, dict)]


def _golden_values(contract: dict) -> list:
    return [{"key": cv.get("key"), "name": cv.get("key"), "value": "REPLACE-ME"}
            for cv in ((contract.get("location_custom_values") or {}).get("required") or [])
            if isinstance(cv, dict) and cv.get("key")]


def _self_test_body(dev) -> None:
    field_map = _fake_field_map()
    contract = _fake_contract()
    want_keys = _contract_field_keys(field_map)
    want_stages = _contract_stages(field_map)
    cv_keys = _contract_custom_value_keys(contract)

    # ---- contract coherence (the same assertions the U02 verifier runs) ----
    assert len(want_keys) == 28, "field-map must carry exactly 28 keys, got %d" % len(want_keys)
    assert len(want_stages) == 9, "field-map must carry exactly 9 stages, got %d" % len(want_stages)
    assert len(cv_keys) == 4, "contract must carry exactly 4 custom values"
    assert field_map["pipeline"]["standard_pipeline_name"] == "Anthology Engine"

    # ---- the diff primitive: golden -> EMPTY delta ----
    stage_rows_want = [{"name": n} for n in want_stages]
    stage_rows_got = [{"name": n} for n in want_stages]
    assert diff_expected_live(stage_rows_want, stage_rows_got, kind="stage",
                              order_bearing=True) == [], \
        "identical stage sets must diff to an empty delta"

    # ---- attack fixtures: every deviation NAMED, never a bare "failed" ----
    # 1. missing stage -> named delta (strict subset)
    d = diff_expected_live(stage_rows_want, stage_rows_got[:8], kind="stage",
                           order_bearing=True)
    assert len(d) == 1 and d[0]["item"] == want_stages[8], \
        "missing stage must be named: %r" % d
    assert d[0]["live"] == "(absent)"
    # 2. extra stage -> named delta
    d = diff_expected_live(stage_rows_want, stage_rows_got
                           + [{"name": "Extra"}], kind="stage",
                           order_bearing=True)
    assert len(d) == 1 and d[0]["item"] == "Extra" and d[0]["detail"].startswith("stage extra"), \
        "extra stage must be named: %r" % d
    # 3. renamed stage -> TWO named deltas (missing + extra), never a pass:
    #    a renamed key is a missing expected key AND an extra live key; the
    #    reorder attack would be silently missed by a set-diff, but the
    #    list-order comparison above already catches reordering separately.
    drifted = [dict(r) for r in stage_rows_got]
    drifted[1] = {"name": "Avatar RENAMED"}
    d = diff_expected_live(stage_rows_want, drifted, kind="stage",
                           order_bearing=True)
    assert len(d) == 2 \
        and {x["item"] for x in d} == {"Avatar", "Avatar RENAMED"}, \
        "renamed stage must name both the missing and the extra side: %r" % d
    assert any(x["live"] == "(absent)" for x in d), \
        "the missing side must be named (absent): %r" % d
    assert any(x["live"] == "Avatar RENAMED" for x in d), \
        "the extra side must name the live name: %r" % d
    # 4. reordered stages -> ORDER deltas (the stage law is BY NAME IN
    #    ORDER; a UI reorder that renumbers positions must be caught)
    shuffled = [dict(r) for r in stage_rows_got]
    shuffled[4], shuffled[5] = shuffled[5], shuffled[4]
    d = diff_expected_live(stage_rows_want, shuffled, kind="stage",
                           order_bearing=True)
    assert any(x["item"] in ("Outline", "Chapter") for x in d), \
        "reordered stages must be named: %r" % d
    #    (the same swap, as rows WITH positions: the stage law is BYTE-EXACT
    #    in both list order AND the position field — the U02 reorder attack)
    shuffled_pos = [{"name": n, "position": i}
                    for i, n in enumerate([want_stages[0], want_stages[1],
                                           want_stages[2], want_stages[3],
                                           want_stages[5], want_stages[4],
                                           want_stages[6], want_stages[7],
                                           want_stages[8]])]
    d = diff_expected_live(
        [{"name": n, "position": i} for i, n in enumerate(want_stages)],
        shuffled_pos, kind="stage", order_bearing=True)
    assert any(x["item"] in ("Outline", "Chapter") for x in d), \
        "position-carrying reorder must be named: %r" % d
    # 5. missing field key -> named delta
    d = diff_expected_live([{"name": k} for k in want_keys],
                           [{"name": k} for k in want_keys[1:]], kind="field")
    assert d[0]["item"] == want_keys[0] and d[0]["detail"].startswith("field missing")
    # 6. extra field key -> named delta
    d = diff_expected_live([{"name": k} for k in want_keys],
                           [{"name": k} for k in want_keys]
                           + [{"name": "contact.anthology_extra"}], kind="field")
    assert d[0]["item"] == "contact.anthology_extra"
    # 7. custom value holding a REAL value -> named delta, the VALUE never surfaced
    want_cv = [{"key": k, "value": "REPLACE-ME"} for k in cv_keys]
    got_cv = [{"key": k, "value": "REPLACE-ME"} for k in cv_keys]
    got_cv[0] = {"key": cv_keys[0], "value": "https://live.example/hooks/anthology-intake"}
    d = diff_expected_live(want_cv, got_cv, kind="custom_value")
    assert len(d) == 1 and d[0]["item"] == cv_keys[0], "real-value drift must be named: %r" % d
    assert d[0]["live"] == "(real — refused)", "the real value must never be surfaced: %r" % d
    assert "https://" not in json.dumps(d), "a URL must never reach the delta surface"
    # 8. credential-shaped value -> the WHOLE diff refuses
    try:
        diff_expected_live([{"name": "x"}], [{"name": "pit-abc123secret"}], kind="field")
        raise AssertionError("a credential-shaped value was NOT refused")
    except DeltaReporterError:
        pass
    # 9. non-list input -> refusal
    try:
        diff_expected_live({"not": "a list"}, [], kind="stage")
        raise AssertionError("non-list expected was NOT refused")
    except DeltaReporterError:
        pass
    # 10. row without a name/key/value -> refusal
    try:
        diff_expected_live([{"x": 1}], [], kind="stage")
        raise AssertionError("unnameable row was NOT refused")
    except DeltaReporterError:
        pass
    # 11. empty expected -> refusal (a report over nothing is fabricated)
    try:
        diff_expected_live([], [], kind="stage")
        raise AssertionError("empty expected was NOT refused")
    except DeltaReporterError:
        pass
    try:
        diff_expected_live([], [{"name": "Extra"}], kind="stage")
        raise AssertionError("empty expected with live rows was NOT refused")
    except DeltaReporterError:
        pass

    # ---- build_report: golden -> PASS verdict, empty delta ----
    report = build_report({
        "pipeline": {"status": "PASS", "detail": "ok",
                     "expected": want_stages, "live": want_stages},
        "custom_fields": {"status": "PASS", "detail": "ok",
                          "expected": len(want_keys), "live": len(want_keys)},
        "custom_values": {"status": "PASS", "detail": "ok",
                          "expected": len(cv_keys), "live": len(cv_keys)},
    }, location_marker="...c_fx")
    assert report["verdict"] == "PASS" and report["delta"] == [], \
        "golden report must carry verdict PASS and an empty delta"
    assert report["contract"] == REPORT_CONTRACT
    assert report["fail_closed"]["any_fail"] is False

    # ---- build_report: every non-PASS item NAMED in delta ----
    report = build_report({
        "pipeline": {"status": "FAIL", "detail": "stage drift",
                     "expected": want_stages, "live": want_stages[:8]},
        "custom_values": {"status": "DEFERRED",
                          "detail": "rail not set — never fabricated",
                          "expected": len(cv_keys), "live": "not read (no rail)"},
        "custom_fields": {"status": "PASS", "detail": "ok",
                          "expected": len(want_keys), "live": len(want_keys)},
    })
    assert report["verdict"] == "FAIL"
    assert {x["item"] for x in report["delta"]} == {"pipeline", "custom_values"}, \
        "every non-PASS check must be named in delta: %r" % report["delta"]
    assert report["fail_closed"]["deferred"] == ["custom_values"]
    # deferred without --allow-deferred stays FAIL (fail-closed)
    report = build_report({
        "custom_values": {"status": "DEFERRED", "detail": "rail not set",
                          "expected": 4, "live": "not read"},
    }, allow_deferred=True)
    assert report["verdict"] == "PASS", "explicit --allow-deferred accepts the deferral"
    assert report["delta"], "the deferral is still recorded in the report"

    # ---- build_report: malformed records REFUSE ----
    for bad in ({"pipeline": {"status": "MAYBE", "detail": "x"}},
                {"pipeline": {"status": "FAIL", "detail": ""}},
                {"pipeline": {"status": "PASS", "detail": "ok"},
                 "custom_fields": "not-a-dict"},
                {}):
        try:
            build_report(bad)
            raise AssertionError("malformed checks map was NOT refused: %r" % (bad,))
        except DeltaReporterError:
            pass

    # ---- live_delta_report: golden state -> exit 0, PASS, empty delta ----
    golden_caf = _FakeCaf(
        pipelines=[_golden_pipeline(field_map)],
        fields=_golden_fields(field_map),
        values=_golden_values(contract),
    )
    report = live_delta_report(golden_caf, "loc_tmpl", field_map, contract)
    assert report["verdict"] == "PASS" and report["delta"] == [], \
        "golden live report must PASS with an empty delta: %r" % report["delta"]
    assert report["checks"]["pipeline"]["live"]["stages"] == want_stages
    # the report only READS
    assert golden_caf.calls and all(m in ("pipelines", "fields", "values")
                                    for m, _ in golden_caf.calls), \
        "the report performed an unexpected call: %s" % golden_caf.calls

    # ---- live_delta_report: a drifted live state NAMES every delta ----
    drift_caf = _FakeCaf(
        pipelines=[dict(_golden_pipeline(field_map), name="Anthology Engine RENAMED")],
        fields=[dict(_golden_fields(field_map)[0],
                     fieldKey="contact.anthology_avatar_doc_url_MUTATED")]
                + _golden_fields(field_map)[1:],
        values=[{"key": cv_keys[0], "value": "https://live.example/hooks/anthology-intake"}]
                + [dict(v) for v in _golden_values(contract)[1:]],
    )
    report = live_delta_report(drift_caf, "loc_tmpl", field_map, contract)
    assert report["verdict"] == "FAIL"
    # the delta list NAMES the three check families that drifted (the item
    # is the check surface; the fine-grained rows live in the check record's
    # expected/live columns, exactly the house report shape)
    items = {x["item"] for x in report["delta"]}
    assert items == {"pipeline", "custom_fields", "custom_values"}, \
        "every drifted check family must be named: %r" % report["delta"]
    # the renamed pipeline names the drift; the stage set is empty-absent
    assert report["checks"]["pipeline"]["status"] == "FAIL"
    # the real URL never reaches any surface of the report
    assert "https://" not in json.dumps(report), \
        "a real-looking URL must never appear in the report"

    # ---- live_delta_report: scope / edge / transport propagate (never fabricated) ----
    for behavior in ("scope", "edge", "transport"):
        try:
            live_delta_report(_FakeCaf(behavior=behavior), "loc_tmpl",
                              field_map, contract)
            raise AssertionError("%s was NOT refused by live_delta_report" % behavior)
        except reg.ScopeDenied:
            assert behavior == "scope"
        except reg.CafUnreachable:
            assert behavior in ("edge", "transport")

    # ---- live_delta_report: kind selection ----
    report = live_delta_report(_FakeCaf(pipelines=[_golden_pipeline(field_map)]),
                               "loc_tmpl", field_map, contract, kind="pipeline")
    assert report["verdict"] == "PASS" and set(report["checks"]) == {"pipeline"}
    try:
        live_delta_report(_FakeCaf(), "loc_tmpl", field_map, contract, kind="bogus")
        raise AssertionError("unknown kind was NOT refused")
    except DeltaReporterError:
        pass

    # ---- plan: offline, exact contract surfaces ----
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = plan(field_map, contract, location_id="loc_tmpl", out=io.StringIO())
    assert rc == EX_OK, "plan must exit 0"
    p = json.loads(buf.getvalue())
    assert p["custom_fields"]["expected_count"] == 28
    assert p["custom_values"]["expected_keys"] == cv_keys
    assert p["pipeline"]["expected_stages"] == want_stages

    # ---- emit_report: ONE JSON object ----
    buf = io.StringIO()
    emit_report(report, out=buf)
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == report["verdict"]

    dev.write("delta_reporter self-test: OK (contract coherence 28 fields / 9 "
              "stages / 4 custom values; diff primitive names missing / extra / "
              "value drift both sides; credential-shaped value, non-list input, "
              "unnameable row, and empty expected all REFUSED; build_report "
              "golden PASS + empty delta, every non-PASS check named, "
              "deferred fail-closed ladder, malformed records refused; "
              "live_delta_report golden exit 0 PASS with empty delta, drifted "
              "live state names every delta with the real URL never surfaced, "
              "scope/edge/transport propagate, read-only proven; plan offline; "
              "emit_report one JSON object)\n")


def self_test(out=None) -> int:
    """OFFLINE mutation-proof self-test. exit 0 pass; 4 any failure
    (AF-AE-TEMPLATE-ATTACK family — a tamper never masquerades as exit 1)."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[delta-reporter] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


# ---------------------------------------------------------------------------
# CLI — house shape: verify / plan / self-test (the same normalization
# anthology_registry.py and the U02 check modules use).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="delta_reporter.py",
        description="JSON delta report (U02, Skill 59): diff the live "
                    "Anthology Convert and Flow TEMPLATE location against the "
                    "engine's sources of truth (pipeline name + nine stages, "
                    "28 custom field keys, 4 location custom values) and name "
                    "every delta as JSON on stdout — never a secret, never a "
                    "token, fail-closed.")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the contract's "
                         "source_template_location.template_location_id, %s; never "
                         "printed)" % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--allow-deferred", action="store_true",
                    help="accepted for CLI-shape parity with the U02 verifier "
                         "(this report surface has no rail-gated checks; a "
                         "deferred family, if added, stays fail-closed without it)")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (source of truth for the byte-exact gate)")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json")
    ap.add_argument("--kind", default="all", choices=("all", "pipeline", "fields", "custom_values"),
                    help="which live surfaces to diff (default: all)")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "self-test"], default="verify")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        field_map = reg.load_field_map(Path(args.field_map).expanduser())
        contract = _read_json(Path(args.contract).expanduser(),
                              "anthology-snapshot-contract.json")
        location_id = (args.location_id.strip() or
                       (contract.get("source_template_location") or {}).get("template_location_id")
                       or DEFAULT_TEMPLATE_LOCATION)

        if args.cmd == "plan":
            return plan(field_map, contract, location_id=location_id)

        # ---- live verify ----
        pit_label, token = reg.resolve_pit()
        if not token:
            checked = ", ".join(reg.PIT_LABELS)
            reg._stop(sys.stderr, "No Convert and Flow private-integration token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "The report runs against the operator's OWN template "
                       "location %s; set the template PIT (client-standard "
                       "labels first) and re-run." % location_id])
            return EX_STOP
        client = reg.CafClient(token)  # CAF_BROWSER_UA on every request (CF 1010)

        report = live_delta_report(client, location_id, field_map, contract,
                                   kind=args.kind)
        emit_report(report)
        if report["verdict"] == "PASS":
            sys.stderr.write("[delta-reporter] OK (marker %s): all surfaces "
                             "agree with the sources of truth.\n"
                             % report.get("location", reg._mask_location(location_id)))
            return EX_OK
        sys.stderr.write("[delta-reporter] FAIL (marker %s): %d delta(s) named "
                         "in the report — every one documented as JSON on "
                         "stdout.\n"
                         % (report.get("location", reg._mask_location(location_id)),
                            len(report.get("delta") or [])))
        return EX_MISMATCH

    except reg.ScopeDenied as exc:
        sys.stderr.write("[delta-reporter] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[delta-reporter] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[delta-reporter] HELD: %s\n" % exc)
        return EX_HELD
    except DeltaReporterError as exc:
        sys.stderr.write("[delta-reporter] STOP: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[delta-reporter] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


def _read_json(path: Path, what: str) -> dict:
    """Fail-closed contract reader — a missing or malformed file is a STOP,
    never a blind pass."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeltaReporterError("cannot read %s: %s" % (what, exc)) from exc
    except ValueError as exc:
        raise DeltaReporterError("%s is not valid JSON: %s" % (what, exc)) from exc
    if not isinstance(data, dict):
        raise DeltaReporterError("%s does not parse to a JSON object" % what)
    return data


if __name__ == "__main__":
    sys.exit(main())
