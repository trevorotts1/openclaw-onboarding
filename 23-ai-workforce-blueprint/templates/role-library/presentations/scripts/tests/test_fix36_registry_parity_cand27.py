"""FIX 36(4) — ENFORCEMENT REGISTRY PARITY (the standing registry parity test).

The FIX SPEC (FIX 36, item 4): "bring the runtime enforcement registry into
exact parity with every documented enforced checker, including FIX 15/18, and
make missing entries fail the registry parity test."

This file pins BOTH DIRECTIONS of every documented enforcement registry:

  A. phase_verifiers.PHASE_VERIFIERS  <->  PIPELINE-MANIFEST.phases
     (every manifest phase has a registered substance verifier; every
     registered verifier maps to a real manifest phase — the runner blocks an
     unregistered phase fail-closed, so a phase/registry mismatch is either a
     phase that can never attest or a dead verifier entry).

  B. slide_craft.CHECK_RULE_CODES  <->  manifest.autofails
     (FIX 15's ten deterministic craft codes: each check's named code is a
     registered manifest autofail, and enforced on the real gate).

  C. craft_judgement ENFORCED/WARNING/HUMAN  <->  manifest.autofails
     (FIX 18's 13-codes-in-3-buckets disposition: all 13 unique codes are
     registered manifest autofails, buckets are disjoint, and the enforced
     bucket is wired into the blocking gate _chk_slide_craft while the human
     bucket is wired into run_signature_deck's attest_phase).

  D. build_deck._chk_slide_craft (the FIX 15+18 enforcement call path) is a
     member of PREFLIGHT_REQUIRED — the enforcement registry entry the FIX 15
     spec required ("wire into build_deck.py PREFLIGHT_REQUIRED or a phase
     verifier") actually executes.

  E. run_signature_deck imports craft_judgement and gates attestations on
     attestation_blocker + warning_hold_blocker (the FIX 18 warning/human
     enforcement call path).

A missing entry anywhere here FAILS the parity test (fail-closed, loud),
exactly per spec. No client names, English only.

Run:  python3 -m pytest tests/test_fix36_enforcement_registry_parity.py -q
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

# ---------------------------------------------------------------------------
# Canonical sources (same resolution order sync_check/tests use)
# ---------------------------------------------------------------------------
CLUSTER_MANIFEST = (
    SCRIPTS.parent.parent.parent.parent.parent
    / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
)

import phase_verifiers as pv  # noqa: E402


def _manifest() -> dict:
    assert CLUSTER_MANIFEST.exists(), f"manifest not found at {CLUSTER_MANIFEST}"
    return json.loads(CLUSTER_MANIFEST.read_text())


# ---------------------------------------------------------------------------
# A. PHASE_VERIFIERS <-> manifest.phases, BOTH directions
# ---------------------------------------------------------------------------

def test_every_manifest_phase_has_a_registered_verifier():
    m = _manifest()
    registered = set(pv.PHASE_VERIFIERS.keys())
    missing = [p["id"] for p in m["phases"] if p["id"] not in registered]
    assert not missing, (
        "FIX 36(4) registry parity FAILURE: manifest phases with NO "
        f"phase_verifiers.PHASE_VERIFIERS entry: {missing} — the runner blocks "
        "an unregistered phase (no verifier — pass), so these phases can never "
        "attest. Add the verifier (or retire the phase from the manifest).")


def test_every_registered_verifier_maps_to_a_manifest_phase():
    m = _manifest()
    manifest_ids = {p["id"] for p in m["phases"]}
    orphan = sorted(set(pv.PHASE_VERIFIERS.keys()) - manifest_ids)
    assert not orphan, (
        "FIX 36(4) registry parity FAILURE: PHASE_VERIFIERS entries that are "
        f"NOT manifest phases: {orphan} — dead enforcement entries (a verifier "
        "that can never be selected). Retire them or restore the phase.")


def test_registry_keys_are_unique_dict_literals():
    """A duplicate key in the dict literal silently shadows the first entry —
    the parity test must see exactly the effective registry."""
    src = (SCRIPTS / "phase_verifiers.py").read_text()
    m = re.search(r"PHASE_VERIFIERS:\s*dict\[str,\s*Callable\]\s*=\s*\{", src)
    assert m, "PHASE_VERIFIERS dict literal not found"
    start = m.end() - 1
    depth = 0
    for i, ch in enumerate(src[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                block = src[start:i + 1]
                break
    else:
        pytest.fail("unbalanced braces in PHASE_VERIFIERS literal")
    keys = re.findall(r'"(P[A-Z0-9.\-]+)"\s*:', block)
    dups = sorted({k for k in keys if keys.count(k) > 1})
    assert not dups, f"duplicate PHASE_VERIFIERS keys (silent shadowing): {dups}"


# ---------------------------------------------------------------------------
# B. FIX 15 — slide_craft ten deterministic codes <-> manifest.autofails
# ---------------------------------------------------------------------------

def test_fix15_ten_codes_registered_in_manifest_autofails():
    import slide_craft
    m = _manifest()
    mf_codes = {a["code"] for a in m["autofails"]}
    check_codes = set(slide_craft.CHECK_RULE_CODES.values())
    assert len(check_codes) == 10, (
        f"FIX 15 declares ten deterministic checks; slide_craft.CHECK_RULE_CODES "
        f"holds {len(check_codes)}: {sorted(check_codes)}")
    missing = sorted(check_codes - mf_codes)
    assert not missing, (
        "FIX 36(4) registry parity FAILURE: slide_craft's enforced codes absent "
        f"from PIPELINE-MANIFEST.autofails: {missing} — an enforced checker whose "
        "code is not a registered autofail (the exact FIX 36(4) defect class).")


def test_fix15_enforcement_gate_is_wired_into_preflight_required():
    """The FIX 15 spec's wiring requirement: slide_craft checks must run from
    build_deck.py PREFLIGHT_REQUIRED (or a phase verifier) — here the shared
    _chk_slide_craft gate entry must be a live member of PREFLIGHT_REQUIRED."""
    src = (SCRIPTS / "build_deck.py").read_text()
    tree = ast.parse(src)
    found = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "PREFLIGHT_REQUIRED" for t in node.targets):
            found = node.value
            break
    assert found is not None, "PREFLIGHT_REQUIRED not found in build_deck.py"
    names = {n.id for n in ast.walk(found) if isinstance(n, ast.Name)}
    assert "_chk_slide_craft" in names, (
        "FIX 36(4) registry parity FAILURE: _chk_slide_craft (the FIX 15+18 "
        "craft gate) is not a member of build_deck.PREFLIGHT_REQUIRED — the "
        "deterministic craft checks would run nowhere (the FIX 15 dead-code "
        "defect regressed).")


def test_fix15_check_functions_exist_and_are_registered():
    import slide_craft
    for fn_name, code in slide_craft.CHECK_RULE_CODES.items():
        fn = getattr(slide_craft, fn_name, None)
        assert callable(fn), (
            f"FIX 36(4) registry parity FAILURE: slide_craft.{fn_name} (named for "
            f"{code} in CHECK_RULE_CODES) does not exist — a documented enforced "
            "checker with no implementation.")


# ---------------------------------------------------------------------------
# C. FIX 18 — craft_judgement 13 codes in 3 buckets <-> manifest.autofails
# ---------------------------------------------------------------------------

def test_fix18_all_13_codes_registered_in_manifest_autofails():
    import craft_judgement as cj
    m = _manifest()
    mf_codes = {a["code"] for a in m["autofails"]}
    all13 = cj.ENFORCED_CODES | cj.WARNING_CODES | cj.HUMAN_CODES
    assert len(all13) == 13, (
        f"FIX 18 pins exactly 13 unique codes; craft_judgement holds {len(all13)}")
    missing = sorted(all13 - mf_codes)
    assert not missing, (
        "FIX 36(4) registry parity FAILURE: FIX 18 disposition codes absent from "
        f"PIPELINE-MANIFEST.autofails: {missing}")


def test_fix18_buckets_disjoint_and_complete():
    import craft_judgement as cj
    assert not (cj.ENFORCED_CODES & cj.WARNING_CODES)
    assert not (cj.ENFORCED_CODES & cj.HUMAN_CODES)
    assert not (cj.WARNING_CODES & cj.HUMAN_CODES)
    assert sorted(cj.ENFORCED_CODES) == [
        "AF-DEN-3", "AF-DEN-6", "AF-HOOK-2", "AF-HOOK-7", "AF-OBI-6"]
    assert sorted(cj.WARNING_CODES) == [
        "AF-AUD-1", "AF-AUD-2", "AF-AUD-3", "AF-DEN-8", "AF-OBI-3", "AF-OBI-5"]
    assert sorted(cj.HUMAN_CODES) == ["AF-OBI", "AF-OBI-4"]


def test_fix18_enforced_bucket_runs_in_the_blocking_gate():
    """The ENFORCED bucket must be executed by _chk_slide_craft's
    craft_judgement.run_all_checks call — a registry entry with no call path
    is the FIX 15 dead-code defect class again."""
    src = (SCRIPTS / "build_deck.py").read_text()
    fn_start = src.index("def _chk_slide_craft(")
    fn_src = src[fn_start:src.index("\ndef ", fn_start + 10)]
    assert "import craft_judgement" in fn_src
    assert "craft_judgement.run_all_checks" in fn_src, (
        "FIX 36(4) registry parity FAILURE: craft_judgement's ENFORCED bucket "
        "is not called from build_deck._chk_slide_craft — the enforced codes "
        "(AF-HOOK-2/7, AF-OBI-6, AF-DEN-3/6) would run nowhere.")


def test_fix18_human_and_warning_buckets_gate_attestation():
    """The HUMAN + WARNING buckets hold the QC phase at ATTESTATION time via
    run_signature_deck's attestation_blocker / warning_hold_blocker calls."""
    src = (SCRIPTS / "run_signature_deck.py").read_text()
    assert "craft_judgement.attestation_blocker" in src, (
        "FIX 36(4) registry parity FAILURE: the HUMAN bucket's attestation hold "
        "is not wired in run_signature_deck (attestation_blocker missing).")
    assert "craft_judgement.warning_hold_blocker" in src, (
        "FIX 36(4) registry parity FAILURE: the WARNING bucket's disposition "
        "hold is not wired in run_signature_deck (warning_hold_blocker missing).")


# ---------------------------------------------------------------------------
# D. manifest gate_codes <-> autofails (declared gate vocabulary is registered)
# ---------------------------------------------------------------------------

def test_manifest_phase_gate_codes_are_registered_autofails():
    m = _manifest()
    mf_codes = {a["code"] for a in m["autofails"]}
    # AF-NO-VISION-QC is the U049-retired code (test_autofail_registry.py pins
    # its retirement); a stale gate_codes mention of it is tolerated as the
    # documented exception, anything else must be registered.
    RETIRED = {"AF-NO-VISION-QC"}
    missing = [
        (ph["id"], c) for ph in m["phases"] for c in ph.get("gate_codes", [])
        if c not in mf_codes and c not in RETIRED
    ]
    assert not missing, (
        "FIX 36(4) registry parity FAILURE: phase gate_codes naming codes that "
        f"are not registered manifest autofails: {missing}")


def test_manifest_autofail_enforced_by_build_deck_symbols_resolve():
    """Every manifest autofail row claiming build_deck enforcement must name a
    py_symbol that actually exists in build_deck.py (sync_check A3's invariant,
    re-proven here against the imported module)."""
    import build_deck  # noqa: E402
    m = _manifest()
    unresolved = []
    for a in m["autofails"]:
        if a.get("enforced_by") != "build_deck":
            continue
        sym = a.get("py_symbol")
        if not sym or not hasattr(build_deck, sym):
            unresolved.append((a["code"], sym))
    assert not unresolved, (
        "FIX 36(4) registry parity FAILURE: manifest autofails declared "
        f"enforced_by:build_deck with a non-resolving py_symbol: {unresolved}")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
