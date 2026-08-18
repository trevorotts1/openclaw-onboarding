#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules/stages_check.py
# NINE-STAGE PIPELINE CHECK — the U02 "nine stages BY NAME IN ORDER" contract
# (ENGINE-MANIFEST.json row 54; CHANGELOG U02; MASTERDOC floor 11: find-and-bind
# is BY NAME, so the stage set AND its order are load-bearing). Lives in the
# u02_modules package so engine scripts can import it by NAME.
# -----------------------------------------------------------------------------
# WHAT THIS OWNS
#   1. CHECK the STANDARD Anthology pipeline on a Convert and Flow location:
#      the pipeline exists BY NAME byte-exact ('Anthology Engine' per
#      config/field-map.json pipeline.standard_pipeline_name) and carries the
#      NINE contract stages BY NAME IN ORDER with contiguous positions 0..8
#      (Intake, Avatar, Tone, Title, Outline, Chapter, Cover, Delivered,
#      Assembled).
#   2. FAIL-CLOSED every anomaly — never a blind pass, never a silent
#      fallback: absent/renamed pipeline; missing, extra, renamed, reordered,
#      or duplicate stage; non-contiguous or renumbered positions; a
#      malformed source of truth (field-map.json pipeline section). Keying
#      ONLY on the position field would miss a UI reorder that renumbers
#      positions — the reorder attack proves the list-order comparison.
#   3. Return the MACHINE contract {ok, count, names} — exactly three keys,
#      in exactly that shape. Human detail goes to stderr (operator-verbose);
#      stdout carries only the JSON result. The module itself has ZERO
#      credential surface: the caller hands it an already-built client (the
#      CLI resolves the PIT BY LABEL and constructs reg.CafClient).
#   4. READ-ONLY: the ONLY Convert and Flow call is the public v2 pipelines
#      GET (reg.CafClient.list_pipelines). The offline self-test proves zero
#      writes with a mutation log.
#
# WHY IT EXISTS (U02): the template location's pipeline is the find-and-bind
# target for every client provision — stage drift there would silently break
# the per-gate pipeline-stage update (SPEC M8) and the snapshot import (U16).
# live_verify_template.py runs the FULL seven-item U02 verify; this module is
# the narrow, importable single-surface check sibling scripts call by NAME.
#
# SOURCE OF TRUTH: config/field-map.json -> pipeline.standard_pipeline_name +
# pipeline.standard_stages (position, name). A source of truth that is
# missing, not a JSON object, not exactly 9 stages, non-unique, or not
# position-contiguous 0..8 is a CONTRACT error: the check REFUSES (exit 2),
# it never checks "some" stages.
#
# AF CODES (fail-closed operator surfaces; self-test failures are exit 4):
#   AF-AE-STAGES-PIPELINE-MISSING -> the standard pipeline is ABSENT or
#          renamed (byte-exact) on the location. STOP (exit 2) — find-and-
#          bind would fail silently.
#   AF-AE-STAGES-CONTRACT         -> config/field-map.json does not carry the
#          nine-stage contract (malformed / drifted source of truth, or the
#          file cannot be read). exit 2.
#   AF-AE-STAGES-DRIFT            -> a present pipeline carries a missing,
#          extra, renamed, reordered, or duplicate stage, or non-contiguous /
#          renumbered positions. exit 5.
#   AF-AE-STAGES-ATTACK           -> an attack fixture tripped the OFFLINE
#          self-test. exit 4 (never 1).
#   AF-AE-PIT-SCOPE               -> the PIT cannot READ pipelines (a genuine
#          Convert and Flow scope denial). exit 2. A bare 401/403 (Cloudflare/
#          WAF edge block, CF 1010) is HELD (exit 3), never mislabeled scope.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation):
#   0  all checks PASS (also plan / self-test pass)
#   1  unexpected error
#   2  STOP refusal — PIT label NOT SET / invalid, no location label, genuine
#      scope denial, pipeline ABSENT, or the field-map contract is malformed
#   3  Convert and Flow API unreachable incl. a Cloudflare/WAF edge block
#      (HELD; retryable; scope undetermined)
#   4  self-test FAILED (AF-AE-STAGES-ATTACK family)
#   5  stage drift (AF-AE-STAGES-DRIFT)
#
# RETURN CONTRACT (the machine surface this module owns):
#   check_stages(client, location_id, field_map=None, *,
#                field_map_path=FIELD_MAP_PATH, out=None) -> dict
#   EXACTLY {"ok": bool, "count": int, "names": [str]}.
#     ok    True  -> the standard pipeline exists and its 9 stages are present
#                    BY NAME IN ORDER with contiguous positions 0..8.
#           False -> fail-closed: ANY anomaly above (bad input, bad source of
#                    truth, missing pipeline, scope denial, transport error,
#                    drift). Never raises.
#     count the number of stage entries on the FOUND standard pipeline (9 on
#           pass; 0 when the pipeline is absent, the source of truth is
#           malformed, or nothing was readable)
#     names the LIVE stage names in list order (the byte-exact read, never
#           the expected list — on a mismatch names shows what is actually
#           there, in the order it is there)
#   Callers that need the house exit-code classification use verify_exit(...)
#   -> int instead.
#
# DOCTRINE: stdlib only; calls NO model. Every Convert and Flow request rides
# reg.CafClient, which applies CAF_BROWSER_UA so the Cloudflare edge fronting
# services.leadconnectorhq.com never 1010s the check (CF 1010, W0.6/GK-09) —
# this module defines NO own HTTP path and NO own User-Agent. Credentials are
# resolved BY LABEL in the CLI (reg.resolve_pit) and NEVER printed — SET /
# NOT-SET only. Move in silence; nothing Anthropic in any runtime file;
# Convert and Flow naming in every client surface.
# =============================================================================
"""u02_modules/stages_check.py — nine-stage pipeline check (U02 contract)."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tempfile
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the LeadConnector client + label resolution,
# and its exit-code constants are the house contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The U02 contract: EXACTLY nine stages. Never "however many the pipeline
# carries" — the count is part of the contract.
EXPECTED_STAGE_COUNT = 9

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

_LOCATION = "loc-test"  # self-test location marker; never a real location id

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (e.g. "pit-abc123"). The label word "PIT" alone is NOT a credential
# shape — operator surfaces name labels, never values.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


class StagesCheckError(Exception):
    """The source of truth (config/field-map.json pipeline section) does not
    carry the nine-stage contract. A fail-closed refusal, never a blind pass."""


def expected_stages(field_map: dict) -> tuple:
    """Read the nine-stage contract from the source of truth, fail-closed.

    Returns (pipeline_name, [stage names in contract order]). Raises
    StagesCheckError on ANY malformed/drifted contract — a check that cannot
    name its own expectation must not run.
    """
    if not isinstance(field_map, dict):
        raise StagesCheckError("field-map is not a JSON object")
    pconf = field_map.get("pipeline")
    if not isinstance(pconf, dict):
        raise StagesCheckError("field-map pipeline section missing or not an object")
    name = pconf.get("standard_pipeline_name")
    if not isinstance(name, str) or not name.strip():
        raise StagesCheckError(
            "field-map pipeline.standard_pipeline_name missing or empty")
    raw = pconf.get("standard_stages")
    if not isinstance(raw, list):
        raise StagesCheckError(
            "field-map pipeline.standard_stages is not a list (%s)"
            % type(raw).__name__)
    if len(raw) != EXPECTED_STAGE_COUNT:
        raise StagesCheckError(
            "field-map pipeline.standard_stages must carry exactly %d stages, "
            "got %d" % (EXPECTED_STAGE_COUNT, len(raw)))
    names = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise StagesCheckError(
                "field-map stage %d is not an object (%s)"
                % (i, type(entry).__name__))
        nm = entry.get("name")
        if not isinstance(nm, str) or not nm:
            raise StagesCheckError("field-map stage %d name missing or empty" % i)
        if entry.get("position") != i:
            raise StagesCheckError(
                "field-map stage %d position %r != %d — the contract must be "
                "contiguous 0..%d" % (i, entry.get("position"), i,
                                      EXPECTED_STAGE_COUNT - 1))
        names.append(nm)
    if len(set(names)) != len(names):
        raise StagesCheckError(
            "duplicate stage name in the contract: %s"
            % ", ".join(sorted(set(names))))
    return name.strip(), names


def _load_field_map(field_map, field_map_path: Path, out) -> tuple:
    """Resolve the source of truth. Returns (field_map_dict, exit_code);
    exit EX_STOP on an unreadable file. Never silent."""
    if field_map is not None:
        return field_map, EX_OK
    try:
        return reg.load_field_map(field_map_path), EX_OK
    except (OSError, ValueError) as exc:
        out.write("[stages-check] STOP: cannot read the source of truth %s — %s. "
                  "AF-AE-STAGES-CONTRACT.\n" % (field_map_path, exc))
        return {}, EX_STOP


def _verify(client, location_id: str, field_map: dict, *, out) -> tuple:
    """Run the check against the live location. Returns (result_dict, rc).
    Human detail goes to out (stderr); the result dict is the machine surface.

    Fail-closed at every step: a malformed source of truth, an unreadable
    remote, a scope denial, an absent pipeline, or any stage drift is a
    False result with a LOUD operator line — never a silent pass.
    """
    try:
        want_name, want_names = expected_stages(field_map)
    except StagesCheckError as exc:
        out.write("[stages-check] STOP: source of truth malformed — %s. "
                  "AF-AE-STAGES-CONTRACT.\n" % exc)
        return {"ok": False, "count": 0, "names": []}, EX_STOP

    try:
        pipes = client.list_pipelines(location_id)
    except reg.ScopeDenied as exc:
        out.write("[stages-check] STOP: %s (marker %s). AF-AE-PIT-SCOPE — grant "
                  "the PIT the opportunities READ scope.\n"
                  % (exc, reg._mask_location(location_id)))
        return {"ok": False, "count": 0, "names": []}, EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[stages-check] HELD: %s (marker %s). Retryable — the stage "
                  "check never fabricates an unread surface.\n"
                  % (exc, reg._mask_location(location_id)))
        return {"ok": False, "count": 0, "names": []}, EX_HELD

    found = next((p for p in pipes if p.get("name") == want_name), None)
    if found is None:
        names = sorted({p.get("name") for p in pipes if p.get("name")})
        out.write("[stages-check] STOP: standard pipeline %r ABSENT on the "
                  "location (marker %s; found: %s). AF-AE-STAGES-PIPELINE-MISSING "
                  "— find-and-bind would fail silently; restore it in the "
                  "Convert and Flow UI.\n"
                  % (want_name, reg._mask_location(location_id),
                     ", ".join(names) or "(none)"))
        return {"ok": False, "count": 0, "names": []}, EX_STOP

    live_raw = found.get("stages")
    if not isinstance(live_raw, list):
        live_raw = []
    live = [s for s in live_raw if isinstance(s, dict)]
    live_names = [s.get("name") or "" for s in live]
    live_pos = [s.get("position") for s in live]
    # The stage law is BYTE-EXACT in both senses: the LIST ORDER of the stage
    # entries must equal the contract order AND the position field must be the
    # contiguous 0..N index. Keying only on the position field would miss a UI
    # reorder that renumbers positions — the reorder attack proves it.
    ok = (len(live_raw) == EXPECTED_STAGE_COUNT
          and live_names == want_names
          and live_pos == list(range(EXPECTED_STAGE_COUNT)))
    result = {"ok": ok, "count": len(live_raw), "names": list(live_names)}
    if not ok:
        out.write("[stages-check] FAIL: stage drift (marker %s): expected %d "
                  "stages %s in list order with contiguous positions 0..%d; "
                  "live %d stages %s with positions %s. AF-AE-STAGES-DRIFT.\n"
                  % (reg._mask_location(location_id), len(want_names), want_names,
                     EXPECTED_STAGE_COUNT - 1, len(live_raw), live_names, live_pos))
        return result, EX_MISMATCH
    out.write("[stages-check] OK (marker %s): pipeline %r carries all %d stages "
              "by name in order, positions 0..%d.\n"
              % (reg._mask_location(location_id), want_name, EXPECTED_STAGE_COUNT,
                 EXPECTED_STAGE_COUNT - 1))
    return result, EX_OK


def check_stages(client, location_id: str, field_map: dict | None = None, *,
                 field_map_path: Path = FIELD_MAP_PATH, out=None) -> dict:
    """Nine-stage pipeline check (U02). Returns EXACTLY
    {"ok": bool, "count": int, "names": [str]} — never raises, never prints a
    credential, never fabricates an unread surface.

    client     any object exposing list_pipelines(location_id) — house callers
               pass reg.CafClient (CAF_BROWSER_UA on every request, CF 1010);
               self-tests pass an in-memory fake.
    location_id the Convert and Flow location id to check (never printed by
               this module; operator surfaces carry the masked marker).
    field_map  optional pre-loaded field-map dict; default None loads the
               house source of truth from field_map_path.
    out        operator channel (default stderr).
    """
    out = out or sys.stderr
    fm, rc = _load_field_map(field_map, field_map_path, out)
    if rc != EX_OK:
        return {"ok": False, "count": 0, "names": []}
    result, _ = _verify(client, location_id, fm, out=out)
    return result


def verify_exit(client, location_id: str, field_map: dict | None = None, *,
                field_map_path: Path = FIELD_MAP_PATH, out=None) -> int:
    """check_stages plus the house exit-code classification (0/2/3/5), for
    callers that need the CLI's rc without the CLI. Never raises."""
    out = out or sys.stderr
    fm, rc = _load_field_map(field_map, field_map_path, out)
    if rc != EX_OK:
        return rc
    _, rc = _verify(client, location_id, fm, out=out)
    return rc


def plan(*, field_map_path: Path = FIELD_MAP_PATH, out=None) -> int:
    """OFFLINE plan: validate the source of truth and print what the check
    will assert. No network, no credentials. exit 0 contract valid; 2 not."""
    out = out or sys.stderr
    try:
        fm = reg.load_field_map(field_map_path)
    except (OSError, ValueError) as exc:
        out.write("[stages-check] STOP: cannot read the source of truth %s — %s. "
                  "AF-AE-STAGES-CONTRACT.\n" % (field_map_path, exc))
        return EX_STOP
    try:
        name, names = expected_stages(fm)
    except StagesCheckError as exc:
        out.write("[stages-check] STOP: source of truth malformed — %s. "
                  "AF-AE-STAGES-CONTRACT.\n" % exc)
        return EX_STOP
    print(json.dumps({
        "pipeline_name": name,
        "expected_stage_count": len(names),
        "expected_stages": names,
        "positions": list(range(len(names))),
        "note": "offline plan only — no network, no credential needed",
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden + attack fixtures, no network, no secrets.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow covering exactly the check surface: pipeline
    listing with programmable contents, failure behaviors, and a mutation log
    (the self-test proves the check makes ZERO writes)."""

    def __init__(self, pipelines=None, behavior=None):
        self._pipelines = [dict(p) for p in (pipelines or [])]
        self.behavior = behavior  # None | scope | edge | transport
        self.calls = []

    def list_pipelines(self, location_id):
        self.calls.append(("list_pipelines", location_id))
        if self.behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self.behavior == "edge":
            raise reg.UpstreamBlockedError(
                "HTTP 403 did NOT match a scope-denial signature (CF 1010)")
        if self.behavior == "transport":
            raise reg.CafUnreachable("transport error: ConnectionResetError")
        return [dict(p) for p in self._pipelines]


def _pipeline(name: str, stages) -> dict:
    # Tolerate non-dict stage entries (the attack fixtures prove the check
    # filters them the same way the live API surface could present them).
    if stages is None:
        return {"id": "pipe_x", "name": name, "stages": None}
    return {"id": "pipe_x", "name": name,
            "stages": [dict(s) if isinstance(s, dict) else s for s in stages]}


def self_test(*, out=None) -> int:
    """OFFLINE mutation-proof self-test. exit 0 pass; 4 any failure
    (AF-AE-STAGES-ATTACK family — a tamper NEVER masquerades as exit 1)."""
    out = out or sys.stderr
    failures = []

    # ---- the source of truth itself must carry the nine-stage contract ----
    try:
        fm = reg.load_field_map(FIELD_MAP_PATH)
    except (OSError, ValueError) as exc:
        out.write("[stages-check] self-test STOP: cannot read the source of "
                  "truth %s — %s\n" % (FIELD_MAP_PATH, exc))
        return EX_VIOLATION
    try:
        want_name, want_names = expected_stages(fm)
    except StagesCheckError as exc:
        out.write("[stages-check] self-test STOP: source of truth malformed — "
                  "%s\n" % exc)
        return EX_VIOLATION

    def run(name, client, field_map, expect_ok, expect_count=None,
            expect_names=None, field_map_path=FIELD_MAP_PATH):
        captured = io.StringIO()
        result = check_stages(client, _LOCATION, field_map, out=captured,
                              field_map_path=field_map_path)
        if not isinstance(result, dict) or set(result) != {"ok", "count", "names"}:
            failures.append("%s: result shape wrong: %r" % (name, result))
        elif result["ok"] is not expect_ok:
            failures.append("%s: ok=%r expected %r" % (name, result["ok"], expect_ok))
        elif expect_count is not None and result["count"] != expect_count:
            failures.append("%s: count=%r expected %r" % (name, result["count"], expect_count))
        elif expect_names is not None and result["names"] != expect_names:
            failures.append("%s: names=%r expected %r" % (name, result["names"], expect_names))
        # The module must never emit a credential-shaped string (it has zero
        # credential surface, but the guard stays). The label word "PIT" is
        # fine; a pit-<value> shape is not.
        if _CREDENTIAL_SHAPE.search(captured.getvalue()):
            failures.append("%s: operator output carries a credential shape" % name)

    golden = [{"position": i, "name": n} for i, n in enumerate(want_names)]
    rename0 = [dict(s) for s in golden]
    rename0[0]["name"] = "IntakeX"
    shuffled = [{"position": i, "name": n}
                for i, n in enumerate([want_names[1]] + want_names[0:1] + want_names[2:])]
    dup = [dict(s) for s in golden]
    dup[7]["name"] = dup[6]["name"]  # duplicate "Cover"
    non_dict = [dict(s) for s in golden]
    non_dict[3] = "not-a-dict"

    # (name, fake pipelines, field_map, expect_ok, expect_count, expect_names)
    fixtures = [
        ("golden", [_pipeline(want_name, golden)], fm, True, 9, want_names),
        ("pipeline_absent",
         [_pipeline("Some Other Pipeline", golden)], fm, False, 0, []),
        ("pipeline_case_drift",
         [_pipeline(want_name.lower(), golden)], fm, False, 0, []),
        ("stage_renamed",
         [_pipeline(want_name, rename0)], fm, False, 9,
         ["IntakeX"] + want_names[1:]),
        ("stage_missing",
         [_pipeline(want_name, golden[:8])], fm, False, 8),
        ("stage_extra",
         [_pipeline(want_name, golden + [{"position": 9, "name": "Extra"}])],
         fm, False, 10),
        ("stage_reorder_renumbered",  # the reorder attack: positions follow the
         [_pipeline(want_name, shuffled)], fm, False, 9,  # new list order
         [want_names[1], want_names[0]] + want_names[2:]),
        ("positions_not_contiguous",
         [_pipeline(want_name, [dict(s) for s in golden[:2]]
                    + [{"position": 4, "name": n} for n in want_names[2:]])],
         fm, False, 9),
        ("positions_out_of_order",
         [_pipeline(want_name, [{"position": 1, "name": want_names[0]},
                                {"position": 0, "name": want_names[1]}]
                    + [dict(s) for s in golden[2:]])],
         fm, False, 9),
        ("duplicate_stage_name",
         [_pipeline(want_name, dup)], fm, False, 9),
        ("stage_entry_not_dict",
         [_pipeline(want_name, non_dict)], fm, False, 9),
        ("stages_empty",
         [_pipeline(want_name, [])], fm, False, 0, []),
        ("stages_not_list",
         [_pipeline(want_name, None)], fm, False, 0, []),
        ("pipeline_missing_stages_key",
         [{"id": "pipe_x", "name": want_name}], fm, False, 0, []),
        # ---- source-of-truth attacks: the check must refuse, not blind-pass ----
        ("contract_missing_pipeline_section",
         [_pipeline(want_name, golden)], {"$note": "no pipeline section"},
         False, 0, []),
        ("contract_eight_stages",
         [_pipeline(want_name, golden)], dict(fm, pipeline=dict(
             fm["pipeline"], standard_stages=golden[:8])), False, 0, []),
        ("contract_ten_stages",
         [_pipeline(want_name, golden)], dict(fm, pipeline=dict(
             fm["pipeline"],
             standard_stages=golden + [{"position": 9, "name": "Extra"}])),
         False, 0, []),
        ("contract_duplicate_names",
         [_pipeline(want_name, golden)], dict(fm, pipeline=dict(
             fm["pipeline"], standard_stages=dup)), False, 0, []),
        ("contract_noncontiguous_positions",
         [_pipeline(want_name, golden)], dict(fm, pipeline=dict(
             fm["pipeline"],
             standard_stages=[{"position": i, "name": n}
                              for i, n in enumerate(["Intake", "Avatar", "Tone",
                                                     "Title", "Outline", "Chapter",
                                                     "Cover", "Delivered"])]
                              + [{"position": 9, "name": "Assembled"}])),
         False, 0, []),
        ("contract_empty_name",
         [_pipeline(want_name, golden)], dict(fm, pipeline=dict(
             fm["pipeline"], standard_pipeline_name="  ")), False, 0, []),
        ("contract_name_not_string",
         [_pipeline(want_name, golden)], dict(fm, pipeline=dict(
             fm["pipeline"], standard_pipeline_name=123)), False, 0, []),
    ]
    for fixture in fixtures:
        # (name, pipes, field_map, expect_ok, expect_count[, expect_names])
        name, pipes, field_map, eok, ecnt = fixture[:5]
        enames = fixture[5] if len(fixture) > 5 else None
        run(name, _FakeCaf(pipelines=pipes), field_map, eok, ecnt, enames)

    # ---- failure behaviors on the remote surface ----
    run("scope_denied", _FakeCaf(pipelines=[_pipeline(want_name, golden)],
                                 behavior="scope"), fm, False, 0, [])
    run("edge_block", _FakeCaf(pipelines=[_pipeline(want_name, golden)],
                               behavior="edge"), fm, False, 0, [])
    run("transport_error", _FakeCaf(pipelines=[_pipeline(want_name, golden)],
                                    behavior="transport"), fm, False, 0, [])

    # ---- unreadable / invalid source-of-truth FILE (default-path load) ----
    # A path that can never resolve: the load must fail closed.
    run("field_map_file_missing",
        _FakeCaf(pipelines=[_pipeline(want_name, golden)]), None,
        False, 0, [],
        field_map_path=Path("/nonexistent-59-u02-stages-check/field-map.json"))
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        tf.write("{ not json")
        bad_json_path = Path(tf.name)
    run("field_map_file_invalid_json",
        _FakeCaf(pipelines=[_pipeline(want_name, golden)]), None,
        False, 0, [], field_map_path=bad_json_path)
    bad_json_path.unlink(missing_ok=True)

    # ---- exit-code classification via verify_exit ----
    for name, behavior, want_rc in (("rc_ok", None, EX_OK),
                                    ("rc_scope", "scope", EX_STOP),
                                    ("rc_edge", "edge", EX_HELD),
                                    ("rc_transport", "transport", EX_HELD),
                                    ("rc_absent", "absent", EX_STOP),
                                    ("rc_drift", "drift", EX_MISMATCH)):
        if behavior == "absent":
            fake = _FakeCaf(pipelines=[_pipeline("Some Other Pipeline", golden)])
        elif behavior == "drift":
            fake = _FakeCaf(pipelines=[_pipeline(want_name, golden[:7])])
        else:
            fake = _FakeCaf(pipelines=[_pipeline(want_name, golden)],
                            behavior=behavior)
        rc = verify_exit(fake, _LOCATION, fm, out=io.StringIO())
        if rc != want_rc:
            failures.append("verify_exit %s: rc=%d expected %d" % (name, rc, want_rc))

    # ---- READ-ONLY proof: the check only ever lists pipelines ----
    fake = _FakeCaf(pipelines=[_pipeline(want_name, golden)])
    check_stages(fake, _LOCATION, fm, out=io.StringIO())
    if fake.calls != [("list_pipelines", _LOCATION)]:
        failures.append("mutation log: expected only list_pipelines, got %r"
                        % fake.calls)

    if failures:
        out.write("[stages-check] self-test FAILED (%d):\n" % len(failures))
        for f in failures:
            out.write("    - %s\n" % f)
        out.write("AF-AE-STAGES-ATTACK — a tamper never masquerades as an "
                  "unexpected error.\n")
        return EX_VIOLATION
    out.write("[stages-check] self-test OK: golden + %d attack fixtures pass; "
              "read-only proven.\n" % (len(fixtures) + 3))
    return EX_OK


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="stages_check.py",
        description="Nine-stage pipeline check (U02): the standard Anthology "
                    "pipeline exists BY NAME byte-exact and carries the nine "
                    "contract stages BY NAME IN ORDER with contiguous positions "
                    "0..8. Machine result {ok, count, names} on stdout; "
                    "operator detail on stderr (Skill 59).")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow location id (default: "
                         "CONVERT_AND_FLOW_LOCATION_ID / GOHIGHLEVEL_LOCATION_ID "
                         "/ GHL_LOCATION_ID env labels; never printed)")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to config/field-map.json (source of truth for "
                         "the byte-exact gate)")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "self-test"],
                    default="verify")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    if args.cmd == "self-test":
        return self_test()

    field_map_path = Path(args.field_map).expanduser()

    if args.cmd == "plan":
        return plan(field_map_path=field_map_path)

    # ---- live verify ----
    location_id = args.location_id.strip() or (reg.resolve_location()[1] or "")
    if not location_id:
        reg._stop(sys.stderr, "No Convert and Flow location id is SET.",
                  ["Checked (in order): %s — all NOT SET."
                   % ", ".join(reg.LOCATION_LABELS),
                   "Set a location label or pass --location-id and re-run."])
        return EX_STOP

    # Credentials BY LABEL, never by value: resolve_pit returns the label and
    # the token; only the label may name a surface. The token itself is passed
    # straight into the client and never referenced again.
    pit_label, token = reg.resolve_pit()
    if not token:
        if pit_label:
            reg._stop(sys.stderr,
                      "The Convert and Flow private-integration token under %s "
                      "is NOT a valid pit- token." % pit_label,
                      ["The value is never printed. Set a valid PIT under one "
                       "of: %s." % ", ".join(reg.PIT_LABELS)])
        else:
            reg._stop(sys.stderr,
                      "No Convert and Flow private-integration token is SET.",
                      ["Checked (in order): %s — all NOT SET."
                       % ", ".join(reg.PIT_LABELS),
                       "Set the PIT BY LABEL and re-run. The check never runs "
                       "unauthenticated and never prints a token."])
        return EX_STOP
    client = reg.CafClient(token)  # CAF_BROWSER_UA on every request (CF 1010)

    fm, rc = _load_field_map(None, field_map_path, sys.stderr)
    if rc != EX_OK:
        return rc
    result, rc = _verify(client, location_id, fm, out=sys.stderr)
    print(json.dumps(result))
    return rc


if __name__ == "__main__":
    sys.exit(main())
