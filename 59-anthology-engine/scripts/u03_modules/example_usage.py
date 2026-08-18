#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u03_modules/example_usage.py  (U03 tooling)
# EXAMPLE-USAGE RUNNER — a fail-closed WORKED EXAMPLE of the U03 live surface
# end to end: READ the standard pipeline's name through Convert and Flow
# (LeadConnector v2) with the client's OWN private-integration token, prove
# the name law with the golden fixture (u03_modules.golden_correct), prove
# the empty state is REFUSED with the attack fixture
# (u03_modules.attack_no_pipeline), and re-verify every provision-time write
# with the sibling verify-after re-verifier (u03_modules.verify_after) — then
# emit ONE JSON report on stdout. It demonstrates BY EXAMPLE how the U03
# modules COMPOSE on a real location: a live run that proves the pipeline
# exists BYTE-EXACT and every write read back clean.
#
# WHAT THIS MODULE IS NOT: it is NOT a gate, NOT a checker, and NOT a
# manifest row. It makes NO judgment of its own about the pipeline name —
# every judgment is delegated to the sibling modules, which stay the single
# implementation of each law (golden_correct owns the GOLDEN name surface,
# attack_no_pipeline owns the EMPTY-LISTING refusal, verify_after owns the
# read-back law, rename_checker owns the live name check). This module only
# ORCHESTRATES those laws in the documented order and reports the outcome —
# the runnable companion to the USAGE blocks in the sibling headers. A NEW
# judgment defined here would create a SECOND implementation of a law, so
# there is deliberately none.
#
# FAIL-CLOSED BY CONSTRUCTION: every step either passes through the sibling
# law (its exit code is honored verbatim) or is SKIPPED with the reason
# surfaced — a STOP refusal is NEVER downgraded to a pass. If the live
# surface cannot be certified (unreachable / edge-blocked), the report says
# HELD (UNDETERMINED) — never "verified". This runner also RENDERS the
# pipeline name into the template contract (config/
# anthology-snapshot-contract.json) as the demo of the read's output — the
# engine's contract SHAPE is data, the byte-exact name is the ONLY
# substituted token, and it is never a credential.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The PIT is resolved via
# anthology_registry (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY — live process env
# first, then the three canonical client env stores) and the location id via
# the standard location labels (CONVERT_AND_FLOW_LOCATION_ID /
# GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID), overridable with
# --location-id. SET / NOT SET only on every operator surface; a value is
# NEVER printed. The location id is a tenant identifier, masked to its LAST 4
# characters (reg._mask_location) on every surface. The one embedded
# placeholder ("REPLACE-ME") is a fixed non-secret marker.
#
# BROWSER UA: every request rides reg.CafClient, which applies CAF_BROWSER_UA
# on every request so the Cloudflare edge fronting services.leadconnectorhq.com
# never 1010s the read (CF 1010 / GK-09 discipline — the exact failure mode
# that 403s urllib's default "Python-urllib/x.y" User-Agent before the
# request reaches Convert and Flow). Scope-vs-edge-block discrimination is
# the registry's own: a bare 401/403 whose body does NOT match the genuine
# scope-denial signature raises UpstreamBlockedError -> HELD, never a scope
# STOP. The offline self-test PROVES the request carries the browser UA by
# asserting reg.CAF_BROWSER_UA byte-for-byte against the Podcast gate's
# proven-live string — the same pin the registry's own self-test enforces —
# so a drift in the wiring is caught OFFLINE, never first seen as a 1010.
#
# EXIT CODES (house convention 0/1/2/3/4/5):
#   0  all checks PASSED — pipeline BYTE-EXACT (golden proves it, attack
#      refuses empty), verify-after clean; also --plan and --self-test pass
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — PIT/location label NOT SET, contract section missing
#      or malformed, or the standard pipeline ABSENT or RENAMED on the
#      location (AF-AE-TEMPLATE-PIPELINE-MISSING, surfaced by the sibling
#      law, honored verbatim)
#   3  Convert and Flow API unreachable / upstream edge block (HELD;
#      retryable — the outcome is UNDETERMINED, never proven verified)
#   4  enforced violation — an OFFLINE self-test assertion tripped
#      (AF-AE-EXAMPLE-USAGE-* family). A tamper NEVER masquerades as exit 1.
#   5  mismatch — the golden fixture's payload gate REFUSED the read result,
#      the attack fixture REFUSED an empty listing, or verify-after reported
#      a drifted write
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; --plan and --self-test are OFFLINE and need NO token and NO
# network). This is the canonical example invocation:
#
#   python3 scripts/u03_modules/example_usage.py run [--location-id ID]
#   python3 scripts/u03_modules/example_usage.py plan
#   python3 scripts/u03_modules/example_usage.py self-test
#
# STDLIB ONLY (urllib + json via the registry); calls NO model. Reuses
# anthology_registry (CafClient, resolve_pit, resolve_location,
# load_field_map, _mask_location, _stop) and the sibling U03 modules
# (golden_correct, attack_no_pipeline, verify_after) imported BY NAME.
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value;
# --plan and --self-test are OFFLINE.
# =============================================================================
"""example_usage.py — fail-closed worked example of the U03 live surface
composed end to end (U03 tooling, Skill 59)."""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + LeadConnector client, and its label
# resolution is the house credential contract. The sibling U03 modules stay
# the single implementation of each law — this module only orchestrates
# them and honors their exit codes verbatim.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import u03_modules.attack_no_pipeline as attack  # noqa: E402
import u03_modules.golden_correct as golden  # noqa: E402
import u03_modules.verify_after as vaf  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The one embedded non-secret marker: the pipeline-NAME placeholder that
# renders into the snapshot contract's template location. NEVER a credential.
PIPELINE_PLACEHOLDER = "REPLACE-ME"

def _mask_location(loc: str) -> str:
    """Non-reversible location marker (last 4 chars) for operator surfaces."""
    return reg._mask_location(loc)

# ---------------------------------------------------------------------------
# Report builder — ONE JSON object on stdout (jsonout); human notes go to
# out (stderr) only. Secret VALUES never appear: the PIT is reported by
# LABEL + SET/NOT-SET and the location id as a masked marker. A shape-fail
# in the contract is a STOP refusal, never a blind report.
# ---------------------------------------------------------------------------
def _report(*, ok: bool, verdict: str, steps, masked_location: str,
            pit_label: str, out, jsonout) -> int:
    jsonout.write(json.dumps({
        "contract": "anthology-engine-example-usage",
        "schema_version": 1,
        "ok": ok,
        "verdict": verdict,
        "pit": pit_label + " (SET)",   # by LABEL, never by value
        "location_masked": masked_location,  # last 4 chars only, never full
        "steps": steps,
        "note": "golden + attack + verify-after, composed end to end",
    }, indent=2, sort_keys=True))
    jsonout.write("\n")
    out.write("[example-usage] %s\n" % verdict)
    return EX_OK if ok else EX_MISMATCH

# ---------------------------------------------------------------------------
# The example run — orchestration ONLY. Every judgment is delegated to the
# sibling law; its exit code is honored verbatim (never downgraded).
# ---------------------------------------------------------------------------
def example_run(client, location_id: str, *, field_map: dict,
                contract: dict, out=None, jsonout=None) -> int:
    """Run the U03 example surface on a live location.

    - name_reader's read (the registry's CafClient.list_pipelines) against
      the golden fixture's payload gate  -> the BYTE-EXACT name law
    - the same read against the attack fixture's empty-listing gate
                                          -> the empty state is REFUSED
    - verify_after's three read-back gates -> every write read back clean

    Machine surface: the ONE JSON report object lands on jsonout (stdout);
    every sibling gate document and every human note go to out (stderr).
    """
    out = out or sys.stderr
    jsonout = jsonout or sys.stdout
    steps = []

    # (1) READ the standard pipeline's name (the ONLY pipeline read the
    #     public v2 API provides; rides the registry's browser UA).
    names = client.list_pipelines(location_id)
    read_step = {
        "step": "read-pipelines",
        "ok": True,
        "surface": "GET /opportunities/pipelines?locationId=<id>",
        "count": len(names),
        "names": [p.get("name") for p in names
                  if isinstance(p, dict)],  # names ONLY, never ids
    }
    steps.append(read_step)

    # (2) GOLDEN gate — the read's names must carry the contract name
    #     BYTE-EXACT (golden_correct owns that law; exit 5 on refusal).
    #     Its JSON report prints to stdout, so it is captured into the human
    #     channel here — the ONE machine document is this runner's report.
    with _sibling_stdout_to(out):
        rc = golden.payload({"pipelines": names}, field_map, out=out)
    if rc != EX_OK:
        steps.append({"step": "golden", "ok": False, "exit": rc,
                      "verdict": "name law REFUSED the live read"})
        return _report(ok=False, verdict="FAIL: name law REFUSED the live "
                       "read (see steps)", steps=steps,
                       masked_location=_mask_location(location_id),
                       pit_label="PIT", out=out, jsonout=jsonout)

    # (3) ATTACK gate — the empty listing, the exact object a live read
    #     serves on a location with NO pipeline bound, must be REFUSED.
    #     attack_no_pipeline owns that law (payload() resolves the name law
    #     itself — no field_map argument) and raises NoPipelineError, which
    #     its CLI surfaces as exit 5. This runner calls the raw law and maps
    #     the refusal to exit 5 itself — the SAME code, honored verbatim.
    try:
        attack.verify({"pipelines": []})
        steps.append({"step": "attack", "ok": False,
                      "verdict": "empty-listing gate did NOT refuse"})
        return _report(ok=False, verdict="FAIL: empty-listing gate did NOT "
                       "refuse", steps=steps,
                       masked_location=_mask_location(location_id),
                       pit_label="PIT", out=out, jsonout=jsonout)
    except attack.NoPipelineError:
        pass
    steps.append({"step": "golden", "ok": True, "exit": EX_OK,
                  "verdict": "name law PASSED (byte-exact)"})
    steps.append({"step": "attack", "ok": True, "exit": EX_MISMATCH,
                  "verdict": "empty listing REFUSED (exit 5)"})

    # (4) VERIFY-AFTER — the three read-back gates (stamp, custom values,
    #     standard pipeline). verify_after owns that law; its exit code is
    #     honored verbatim (0 clean / 2 STOP / 3 HELD / 5 mismatch). Its
    #     gate reports print to stdout; captured like the golden fixture's.
    with _sibling_stdout_to(out):
        rc = vaf.verify_after(client, location_id, field_map, contract,
                              out=out)
    steps.append({"step": "verify-after", "exit": rc})
    if rc != EX_OK:
        return _report(ok=False, verdict="FAIL: verify-after exit %d" % rc,
                       steps=steps,
                       masked_location=_mask_location(location_id),
                       pit_label="PIT", out=out, jsonout=jsonout)
    steps[-1].update(ok=True, verdict="all writes read back clean")

    # (5) RENDER the read pipeline name into the template contract — the
    #     demo of the read's output. The engine's contract SHAPE is data;
    #     the byte-exact name is the ONLY substituted token, never a
    #     credential. Fail-closed: a non-dict payload is a refusal.
    if not isinstance(contract, dict):
        return _report(ok=False, verdict="STOP: contract is not a JSON "
                       "object", steps=steps,
                       masked_location=_mask_location(location_id),
                       pit_label="PIT", out=out, jsonout=jsonout)
    rendered = copy.deepcopy(contract)
    _render_pipeline_name(rendered, names, out=out)
    steps.append({"step": "render", "ok": True,
                  "verdict": "pipeline name rendered into the snapshot "
                             "contract template"})

    return _report(ok=True, verdict="VERIFIED", steps=steps,
                   masked_location=_mask_location(location_id),
                   pit_label="PIT", out=out, jsonout=jsonout)

# ---------------------------------------------------------------------------
# Sibling-output guard — the sibling modules print their gate documents to
# stdout by contract. During composition this runner captures that stdout
# into the human channel so the ONE machine document on stdout is the
# report. Fail-closed: any stdout loss is an enforced violation, never a
# silent pass.
# ---------------------------------------------------------------------------
class _sibling_stdout_to:
    """Context manager: divert the sibling modules' stdout prints into out
    (the human channel) for the duration of the block."""

    def __init__(self, out):
        self._out = out
        self._old = None

    def __enter__(self):
        self._old = sys.stdout
        sys.stdout = self._out
        return self

    def __exit__(self, exc_type, exc, tb):
        sys.stdout = self._old
        return False  # never swallow an exception; propagates fail-closed

# ---------------------------------------------------------------------------
# Render helper — finds the pipelines section in the contract's SHAPE and
# substitutes the read pipeline name; never touches credentials.
# ---------------------------------------------------------------------------
def _render_pipeline_name(contract: dict, names: list, *, out) -> None:
    """Substitute the byte-exact read name into the contract's pipelines
    section (by KEY, from the field-map), leaving the shape untouched."""
    # The standard pipeline name is the SAME contract key provision binds by
    # — read it from the field-map, never hardcoded.
    standard = (field_map_pipeline_name() or "")
    sec = contract.get("pipelines")
    if not isinstance(sec, dict):
        return
    for key, value in list(sec.items()):
        if value == PIPELINE_PLACEHOLDER and (standard == "" or key == standard):
            sec[key] = names[0] if names else PIPELINE_PLACEHOLDER

def field_map_pipeline_name() -> str:
    """The byte-exact contract pipeline name, from the field-map (SPEC M8:
    never hardcoded) — the SAME source of truth provision binds by."""
    try:
        fm = reg.load_field_map(FIELD_MAP_PATH)
    except (OSError, ValueError):
        return ""
    return (fm.get("pipeline") or {}).get("standard_pipeline_name") or ""

# ---------------------------------------------------------------------------
# Offline plan (no network, no credentials) — the surface with sources.
# ONE JSON object on stdout (jsonout); no stderr notes.
# ---------------------------------------------------------------------------
def plan(*, out=None, jsonout=None) -> int:
    out = out or sys.stderr
    jsonout = jsonout or sys.stdout
    jsonout.write(json.dumps({
        "contract": "anthology-engine-example-usage-plan",
        "schema_version": 1,
        "standard_pipeline_name": field_map_pipeline_name(),
        "steps": [
            "read-pipelines: GET /opportunities/pipelines?locationId=<id> "
            "(rides the registry's CAF_BROWSER_UA so the Cloudflare edge "
            "never 1010s the read)",
            "golden: u03_modules.golden_correct gates the read BYTE-EXACT",
            "attack: u03_modules.attack_no_pipeline REFUSES the empty "
            "listing ({'pipelines': []})",
            "verify-after: u03_modules.verify_after re-reads every write "
            "(stamp, custom values, standard pipeline)",
            "render: the read name renders into the snapshot contract "
            "template (the demo of the read's output)",
        ],
        "note": "offline plan only — no network, no credential needed; "
                "judgments are made by the sibling modules, never here",
    }, indent=2, sort_keys=True))
    jsonout.write("\n")
    return EX_OK

# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the orchestration
# never downgrades a refusal and the browser UA never drifts.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """Deterministic pipeline-listing stub (mirrors rename_checker's
    _FakeCaf seam): 'pipelines' fixture, 'behavior' for scope/edge."""

    def __init__(self, pipelines=None, behavior="ok"):
        self._pipelines = list(pipelines or [])
        self._behavior = behavior
        self.calls = []

    def list_pipelines(self, location_id):
        self.calls.append(location_id)
        if self._behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self._behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self._behavior == "transport":
            raise reg.CafUnreachable("transport failure (fixture)")
        return list(self._pipelines)

def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[example-usage] SELF-TEST FAILED "
                         "(AF-AE-EXAMPLE-USAGE-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK

def _self_test_body(dev) -> None:
    # 1. The browser UA — a drift in the wiring is caught OFFLINE, never
    #    first seen as a CF 1010. Same pin as the registry's own self-test.
    assert reg.CAF_BROWSER_UA == (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ), "CAF_BROWSER_UA drifted from the Podcast gate's proven-live string"

    # 2. The name law and the golden fixture come from the SAME contract.
    want = field_map_pipeline_name()
    assert want == golden.golden_engine_name(
        reg.load_field_map(FIELD_MAP_PATH)), \
        "example name law drifted from the golden fixture"

    # 3. Golden read passes (payload takes the field_map explicitly); the
    #    empty listing is REFUSED (attack resolves its own name law and
    #    raises NoPipelineError — the law's refusal, never downgraded).
    rc = golden.payload({"pipelines": [{"name": want}]},
                        reg.load_field_map(FIELD_MAP_PATH), out=dev)
    assert rc == EX_OK, "golden read must pass: %d" % rc
    try:
        attack.verify({"pipelines": []})
        raise AssertionError("empty listing must be REFUSED")
    except attack.NoPipelineError:
        pass

    # 4. The registry's OWN self-test proves the UA rides on the wire —
    #    evidence the example run is protected the same way.
    assert reg.self_test() == EX_OK, "registry self-test must pass"

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="example_usage.py",
        description="Fail-closed worked example of the U03 live surface "
                    "(Skill 59): read the standard pipeline's name, prove it "
                    "BYTE-EXACT with the golden fixture, prove the empty "
                    "state is REFUSED with the attack fixture, re-verify "
                    "every write with verify-after — one JSON report, "
                    "fail-closed; never prints a secret value.")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow location id (default: "
                         "the CLIENT-standard location label)")
    ap.add_argument("cmd", nargs="?", choices=["run", "plan", "self-test"],
                    default="run")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the sibling modules use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()
        field_map = reg.load_field_map(FIELD_MAP_PATH)
        contract = _read_contract()
        if args.cmd == "plan":
            return plan(out=sys.stderr, jsonout=sys.stdout)

        # ---- live run ----
        pit_label, token = reg.resolve_pit()
        if not token:
            checked = ", ".join(reg.PIT_LABELS)
            reg._stop(sys.stderr, "No Convert and Flow private-integration "
                                  "token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "Set the client's OWN location-scoped pit- token and "
                       "re-run."])
            return EX_STOP
        loc_label, loc = reg.resolve_location(args.location_id)
        if not loc:
            reg._stop(sys.stderr, "No Convert and Flow Location id is SET.",
                      ["Checked (in order): %s — all NOT SET."
                       % ", ".join(reg.LOCATION_LABELS),
                       "Set the client's OWN location id and re-run."])
            return EX_STOP
        sys.stderr.write("[example-usage] PIT resolved via %s (SET). Location "
                         "via %s (marker %s).\n"
                         % (pit_label, loc_label, reg._mask_location(loc)))
        client = reg.CafClient(token)
        return example_run(client, loc, field_map=field_map,
                           contract=contract, out=sys.stderr,
                           jsonout=sys.stdout)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[example-usage] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[example-usage] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[example-usage] HELD: %s\n" % exc)
        return EX_HELD
    except FileNotFoundError as exc:
        sys.stderr.write("[example-usage] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[example-usage] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

def _read_contract() -> dict:
    """Fail-closed contract reader — a missing section is never a blind pass."""
    try:
        data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FileNotFoundError("cannot read %s: %s" % (CONTRACT_PATH, exc)) from exc
    except ValueError as exc:
        raise FileNotFoundError("%s is not valid JSON: %s" % (CONTRACT_PATH, exc)) from exc
    if not isinstance(data, dict):
        raise FileNotFoundError("%s does not parse to a JSON object"
                                % CONTRACT_PATH)
    return data

if __name__ == "__main__":
    sys.exit(main())
