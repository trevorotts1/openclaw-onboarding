#!/usr/bin/env python3
"""test_preflight_shadow_scoped.py — proves the SCOPED attestation-explained-
divergence mechanism in presentation_job/preflight_shadow.py (rebuild of
fix/trust-falsepos after the rejected version was found, on review, to explain
divergences via an UNSCOPED global pool of every attested hash in the whole
run — a laundering hole where a hash legitimately attested for one artifact's
phase could wrongly explain a real tamper on a completely different artifact).

Reuses the REAL fixture-building helper (`make_workdir`) from test_preflight.py
and the REAL `run_signature_deck.attest_phase` / `_compute_artifact_sha`
functions — this file authors no fixture and no attestation mechanism of its
own; every retry/attestation here is driven through the actual harness the
pipeline uses on a legitimate QC send-back retry or `--phase` re-dispatch.

Three cases:

  CASE D — a REAL legitimate retry (rewrite + genuine attest_phase()
    corroboration under the artifact's OWN owning phase_id, e.g. P0A-INTAKE
    re-attesting working/copy/intake.json) through the REAL
    build_deck.run_preflight() loop no longer false-flags: toctou_divergence
    stays true (nothing is hidden from the ledger) but
    explained_by_attestation is true, the gate is dropped from
    would_have_blocked, and no WOULD-BLOCK line is printed. This is the
    original FALSEPOS defect, reproduced then closed.

  CASE E — the SAME real attestation from CASE D does NOT explain a
    divergence on a DIFFERENT, untouched artifact (working/copy/slides_copy.md,
    owned by P4-COPY — a phase P0A-INTAKE never touches and never attests)
    even when that different artifact is hand-edited to contain the EXACT
    SAME bytes P0A-INTAKE legitimately attested for intake.json. This is the
    laundering hole the verifier found in the rejected fix's unscoped global
    hash pool; CASE E proves it is closed on the real dispatch loop.

  CASE F — mechanism-level, direct proof: the rejected fix's own unscoped
    lookup logic (transcribed verbatim from commit a403cc7b, not reinvented)
    is exercised against the SAME real process_manifest.json CASE E produces,
    side by side with the fixed module's `_attested_artifact_shas_for`. The
    rejected logic explains the hash for ANY artifact_spec (proving the
    laundering channel is structural in that code); the fixed, scoped lookup
    explains it ONLY for the artifact_spec(s) PIPELINE-MANIFEST.json actually
    names P0A-INTAKE as producing.

Run:  python3 test_preflight_shadow_scoped.py
Exit: 0 = all assertions passed; 1 = a case failed.
"""
import contextlib
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_deck  # noqa: E402
import run_signature_deck as rsd  # noqa: E402
from presentation_job import preflight_shadow  # noqa: E402
from test_preflight import make_workdir  # noqa: E402 — REUSE the real fixture, author none here

LEDGER_REL = Path("working") / "checkpoints" / "preflight-shadow.jsonl"


def _read_ledger(root: Path):
    p = root / LEDGER_REL
    if not p.is_file():
        return []
    lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def _run_preflight_captured(root: Path):
    out, err = io.StringIO(), io.StringIO()
    exited_3 = False
    slides_path = root / "slides.json"
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            build_deck.run_preflight(root, slides_path=slides_path)
        except SystemExit as e:
            exited_3 = (e.code == 3)
    return exited_3, out.getvalue(), err.getvalue()


def _entry_index(rel_value):
    for i, entry in enumerate(build_deck.PREFLIGHT_REQUIRED):
        if entry[0] == rel_value:
            return i
    raise AssertionError(f"could not find the {rel_value!r} PREFLIGHT_REQUIRED entry")


def _old_rejected_unscoped_attested_shas(run_dir: Path) -> frozenset:
    """Transcribed VERBATIM (logic-for-logic, not reinvented) from the REJECTED
    commit a403cc7b's `_attested_artifact_shas()`: a global pool of every
    attested artifact_sha in the whole run, with ZERO scoping to which
    artifact or phase attested it. Kept here ONLY to prove, side by side with
    the fixed module, that the laundering channel that logic created is
    closed by the scoped replacement — never reinstated as live code."""
    try:
        pm_path = run_dir / "working" / "checkpoints" / "process_manifest.json"
        if not pm_path.is_file():
            return frozenset()
        obj = json.loads(pm_path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(obj, dict):
            return frozenset()
        shas = set()
        for att in obj.get("phase_attestations", []) or []:
            if isinstance(att, dict):
                sha = att.get("artifact_sha")
                if isinstance(sha, str) and sha and sha != "no-artifact-spec":
                    shas.add(sha)
        return frozenset(shas)
    except Exception:  # noqa: BLE001
        return frozenset()


def case_d_legitimate_retry_no_longer_falseflags():
    fails = []
    root = make_workdir(with_artifacts=True)
    idx = _entry_index("working/copy/intake.json")
    rel, label, phase, real_check = build_deck.PREFLIGHT_REQUIRED[idx]

    def _legit_retry_then_check(path):
        # REAL legitimate retry: rewrite the artifact, then REALLY attest it
        # via the REAL run_signature_deck harness under its OWN owning
        # phase_id (P0A-INTAKE) — the same two calls
        # run_copy_qc_loop/run_prompt_qc_loop and the --phase dispatch path
        # make on every legitimate completion, first pass or retry.
        p = Path(path)
        obj = json.loads(p.read_text())
        obj["_retry_pass"] = 2
        p.write_text(json.dumps(obj))
        sha = rsd._compute_artifact_sha(root, "working/copy/intake.json")
        rsd.attest_phase(root, "P0A-INTAKE", "content-to-presentation-architect",
                          "artifact_present", artifact_sha=sha, substance_verified=True)
        return real_check(path)

    build_deck.PREFLIGHT_REQUIRED[idx] = (rel, label, phase, _legit_retry_then_check)
    try:
        exited_3, out, err = _run_preflight_captured(root)
    finally:
        build_deck.PREFLIGHT_REQUIRED[idx] = (rel, label, phase, real_check)

    if exited_3:
        fails.append("CASE D: legitimate retry wrongly refused (exit 3)")

    ledger = _read_ledger(root)
    matches = [e for e in ledger if e.get("gate_label") == label]
    if len(matches) != 1:
        fails.append(f"CASE D: expected exactly one ledger line for {label!r}, found {len(matches)}")
    else:
        e = matches[0]
        if not e.get("toctou_divergence"):
            fails.append(f"CASE D: expected toctou_divergence=true (nothing hidden from the "
                          f"ledger even when explained) -- got {e.get('toctou_divergence')}")
        if not e.get("explained_by_attestation"):
            fails.append(f"CASE D: the REAL, matching attestation under intake.json's OWN "
                          f"owning phase (P0A-INTAKE) should explain this divergence -- "
                          f"explained_by_attestation={e.get('explained_by_attestation')}")

    if "TRUST-BOUNDARY-PREFLIGHT-WOULD-BLOCK" in err and label in err:
        fails.append("CASE D: a legitimate, attested retry was still reported as "
                      "would-have-blocked (the original FALSEPOS defect is NOT fixed)")

    print(f"CASE D (legitimate retry no longer false-flags) -> {'PASS' if not fails else 'FAIL'}")
    return fails


def case_e_scoping_closes_cross_artifact_laundering():
    fails = []
    root = make_workdir(with_artifacts=True)
    intake_idx = _entry_index("working/copy/intake.json")
    copy_idx = _entry_index("working/copy/slides_copy.md")
    intake_rel, intake_label, intake_phase, intake_check = build_deck.PREFLIGHT_REQUIRED[intake_idx]
    copy_rel, copy_label, copy_phase, copy_check = build_deck.PREFLIGHT_REQUIRED[copy_idx]

    # Byte-identical payload used for BOTH artifacts on purpose: this is the
    # exact shape of the laundering exploit -- a hash legitimately attested
    # for artifact A's phase, replayed onto a completely different artifact B.
    payload = json.dumps({"_shared_payload": "identical-bytes-cross-artifact", "n": 1})

    def _legit_retry_intake(path):
        p = Path(path)
        p.write_text(payload)
        sha = rsd._compute_artifact_sha(root, "working/copy/intake.json")
        rsd.attest_phase(root, "P0A-INTAKE", "content-to-presentation-architect",
                          "artifact_present", artifact_sha=sha, substance_verified=True)
        return intake_check(path)

    def _hand_edit_slides_copy(path):
        # REAL tamper: overwrite slides_copy.md with bytes copied from a
        # totally different artifact's legitimate retry. NO attest_phase call
        # for P4-COPY at all -- no corroboration this phase produced this
        # content.
        p = Path(path)
        p.write_text(payload)
        return copy_check(path)

    build_deck.PREFLIGHT_REQUIRED[intake_idx] = (intake_rel, intake_label, intake_phase, _legit_retry_intake)
    build_deck.PREFLIGHT_REQUIRED[copy_idx] = (copy_rel, copy_label, copy_phase, _hand_edit_slides_copy)
    try:
        exited_3, out, err = _run_preflight_captured(root)
    finally:
        build_deck.PREFLIGHT_REQUIRED[intake_idx] = (intake_rel, intake_label, intake_phase, intake_check)
        build_deck.PREFLIGHT_REQUIRED[copy_idx] = (copy_rel, copy_label, copy_phase, copy_check)

    ledger = _read_ledger(root)
    intake_matches = [e for e in ledger if e.get("gate_label") == intake_label]
    copy_matches = [e for e in ledger if e.get("gate_label") == copy_label]
    if len(intake_matches) != 1 or len(copy_matches) != 1:
        fails.append(f"CASE E: expected one ledger line each for intake/copy gates, "
                      f"got {len(intake_matches)}/{len(copy_matches)}")
        print(f"CASE E (scoping closes cross-artifact laundering) -> FAIL")
        return fails

    intake_entry, copy_entry = intake_matches[0], copy_matches[0]
    if not intake_entry.get("explained_by_attestation"):
        fails.append("CASE E: intake.json's OWN legitimate retry should still be explained "
                      f"-- got explained_by_attestation={intake_entry.get('explained_by_attestation')}")
    if not copy_entry.get("toctou_divergence"):
        fails.append("CASE E: slides_copy.md's real tamper should register a divergence")
    if copy_entry.get("explained_by_attestation"):
        fails.append("CASE E: LAUNDERING REGRESSION -- slides_copy.md's tamper (never "
                      "attested by its own owning phase P4-COPY) was wrongly explained by "
                      "a hash legitimately attested for a DIFFERENT artifact/phase "
                      "(intake.json / P0A-INTAKE)")

    print(f"CASE E (scoping closes cross-artifact laundering) -> {'PASS' if not fails else 'FAIL'}")
    return fails


def case_f_mechanism_level_old_vs_new():
    fails = []
    root = make_workdir(with_artifacts=True)
    intake_path = root / "working" / "copy" / "intake.json"
    obj = json.loads(intake_path.read_text())
    obj["_retry_pass"] = 2
    intake_path.write_text(json.dumps(obj))
    sha = rsd._compute_artifact_sha(root, "working/copy/intake.json")
    rsd.attest_phase(root, "P0A-INTAKE", "content-to-presentation-architect",
                      "artifact_present", artifact_sha=sha, substance_verified=True)

    old_pool = _old_rejected_unscoped_attested_shas(root)
    if sha not in old_pool:
        fails.append("CASE F: sanity check failed -- the rejected unscoped pool should "
                      "contain the attested sha (test setup problem, not the fix)")

    new_for_owner = preflight_shadow._attested_artifact_shas_for(root, "working/copy/intake.json")
    new_for_other = preflight_shadow._attested_artifact_shas_for(root, "working/copy/slides_copy.md")
    new_for_qc = preflight_shadow._attested_artifact_shas_for(root, "working/qc/copy_qc_report.json")

    if sha not in new_for_owner:
        fails.append("CASE F: the scoped lookup should explain the hash for intake.json "
                      "itself (the artifact P0A-INTAKE actually produced)")
    if sha in new_for_other:
        fails.append("CASE F: LAUNDERING REGRESSION -- the scoped lookup explained "
                      "intake.json's attested hash for slides_copy.md, an unrelated "
                      "artifact owned by a different phase")
    if sha in new_for_qc:
        fails.append("CASE F: LAUNDERING REGRESSION -- the scoped lookup explained "
                      "intake.json's attested hash for copy_qc_report.json, an unrelated "
                      "artifact owned by a different phase")

    print(f"CASE F (mechanism-level: old unscoped pool launders, new scoped lookup does not) "
          f"-> {'PASS' if not fails else 'FAIL'}")
    return fails


def main() -> int:
    all_fails = []
    all_fails += case_d_legitimate_retry_no_longer_falseflags()
    all_fails += case_e_scoping_closes_cross_artifact_laundering()
    all_fails += case_f_mechanism_level_old_vs_new()

    print()
    if all_fails:
        print(f"FAIL ({len(all_fails)} failure(s)):")
        for f in all_fails:
            print(f"  - {f}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
