#!/usr/bin/env python3
"""
qc_aggregate.py -- FINAL QC AGGREGATION (manifest phase P-QC-AGGREGATE, order 8.65).

================================================================================
THE GAP THIS CLOSES. gates.py's `_qc_gate` (fixed fail-closed in the same change
that adds this phase) blocks close() unless working/qc/final_qc_report.json exists,
parses, and carries a numeric average >= QC_PASS_THRESHOLD (8.5). Nothing wrote that
file: the manifest's six QC-domain phases each write their OWN report --

    P1Q-COPY-QC   -> working/qc/copy_qc_report.json
    P-TYPO-QC     -> working/qc/typography_qc_report.json
    P-PROMPT-QC   -> working/qc/prompt_qc_report.json
    P-IMAGE-QC    -> working/qc/image_qc_report.json
    P-SHIFT-QC    -> working/qc/priority_shift_report.json
    P-SPEECH-QC   -> working/qc/speech_qc_report.json

-- and nothing combined them. That made the fail-closed `qc` gate a universal
brick: it blocked every job, including a flawless one, because its input never
existed. This script IS that input's producer.

WHAT IT DOES
    1. Resolves each of the six domain-report paths from the manifest's own
       `produces_artifact` field (manifest_source.resolve_manifest + a
       find_repo_root walk-up; falls back to the known-good literal paths above
       only when no manifest can be resolved at all -- e.g. an isolated test
       fixture -- and says so).
    2. Reads each report. A report that is absent, unreadable, carries no numeric
       average, scores below 8.5, or fails independent-reviewer provenance
       (build_deck._qc_independence_reason -- the SAME check the legacy
       per-domain gates already use; not reinvented here) is a BLOCKING finding
       naming that exact domain.
    3. Runs qc_generator_guard.guard_qc_generators(run_dir) -- the EXISTING,
       already-shipped provenance guard (AF-QC-GENERATOR-UNGOVERNED /
       AF-QC-RUBRIC-CORRUPT / AF-QC-REPORT-UNTRUSTED) -- across the whole run
       dir. Any un-waived finding is a BLOCKING finding, whole-run-wide.
    4. Computes the combined score as the mean of the five numeric domain
       averages (copy/typography/prompt/image/speech) PLUS the priority-shift
       ship gate's own pass/fail (P-SHIFT-QC is a 14-item checklist, not a
       0-10 rubric, so it gates rather than averages).
    5. Writes working/qc/final_qc_report.json. The gate-facing `average` field
       is populated ONLY when every one of the six domains is present, trusted,
       and passing (independence + generator-guard clean + priority-shift
       pass) -- i.e. only on a genuine, full pass. On ANY blocking finding,
       `average` is null (NEVER a fabricated/partial number that could slip
       past gates.py's `score >= 8.5` check) and `blocking_reasons` names every
       finding, keyed to the domain and/or AF code. `computed_average` is a
       separate, diagnostic-only field: the honest five-domain mean, populated
       whenever all five numbers are readable, regardless of pass/fail -- for
       humans, never read by the gate.

WHAT IT DELIBERATELY DOES NOT DO
    It does not re-run build_deck.py's deep per-domain substance teeth (the
    prompt-file re-measure behind _chk_prompt_qc, the pixel/vision cross-check
    behind _chk_image_qc). Those already gate their OWN phases via build_deck's
    preflight framework and phase_verifiers.py's warn-mode substance checks;
    re-running them here would be a third parallel path duplicating, not
    reusing, existing logic, and would require fabricating deep image/prompt
    fixtures to demonstrate. This script's job is PROVENANCE + AGGREGATION, not
    re-grading -- and it uses the two existing mechanisms that job actually
    calls for: qc_generator_guard.py (corrupt-generator/corrupt-rubric/
    untrusted-report) and build_deck._qc_independence_reason (self-graded
    reports). It does NOT invent a third trust mechanism.

EXIT CODES
    Default (no --phase-mode): mirrors qc_generator_guard.py's own convention.
        0 -- genuine, full pass (average populated, no blocking findings).
        5 -- BLOCKED (missing/untrusted/sub-threshold/independence/priority-shift
             finding). Message names every blocking domain/code.
        2 -- usage/IO error (bad --run-dir, cannot write the report).
    --phase-mode (used by the manifest's script executor): exits 0 whenever the
        report was MECHANICALLY written, regardless of the verdict inside it --
        pass/fail enforcement is gates.py's `_qc_gate` at close() time, a single
        enforcement point, exactly like ocr_readback and every other close()-time
        gate. Still exits 2 on a genuine usage/IO error (the report was never
        written at all -- that legitimately blocks the phase itself, via the
        engine's own produces_artifact presence check).

USAGE
    python3 qc_aggregate.py --run-dir <RUN_DIR> [--manifest PATH] [--phase-mode]
    python3 qc_aggregate.py --run-dir <RUN_DIR> --json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent

QC_PASS_THRESHOLD = 8.5
FINAL_REPORT_REL = "working/qc/final_qc_report.json"

# Known-good literal paths -- the FALLBACK used only when no manifest can be
# resolved at all (e.g. an isolated unit-test fixture with no PIPELINE-MANIFEST.json
# on disk anywhere). When a manifest IS resolvable, its own produces_artifact
# value for each phase id below is used instead (requirement: "reads the six
# domain QC reports from their manifest-declared produces_artifact paths").
DEFAULT_DOMAIN_PATHS = {
    "P1Q-COPY-QC": "working/qc/copy_qc_report.json",
    "P-TYPO-QC": "working/qc/typography_qc_report.json",
    "P-PROMPT-QC": "working/qc/prompt_qc_report.json",
    "P-IMAGE-QC": "working/qc/image_qc_report.json",
    "P-SPEECH-QC": "working/qc/speech_qc_report.json",
}
DEFAULT_PRIORITY_SHIFT_PATH = "working/qc/priority_shift_report.json"

# domain key -> (phase id, human label)
AVERAGED_DOMAINS = [
    ("copy", "P1Q-COPY-QC", "Copy QC"),
    ("typography", "P-TYPO-QC", "Typography QC"),
    ("prompt", "P-PROMPT-QC", "Prompt QC"),
    ("image", "P-IMAGE-QC", "Image QC"),
    ("speech", "P-SPEECH-QC", "Speech QC"),
]
PRIORITY_SHIFT_PHASE_ID = "P-SHIFT-QC"


# ---------------------------------------------------------------------------
# Defensive, existing-mechanism reuse. Both imports are the SAME modules the
# legacy per-domain gates and the anti-bypass surface already use -- nothing
# here is a new trust mechanism.
# ---------------------------------------------------------------------------
try:
    sys.path.insert(0, str(HERE))
    import build_deck as _bd
except Exception:  # noqa: BLE001 -- import failure is handled per-domain below
    _bd = None

try:
    import qc_generator_guard as _qgg
except Exception as exc:  # noqa: BLE001 -- this module is stdlib-only; a failure here is fatal
    print(f"FATAL: qc_generator_guard.py is not importable ({exc!r}) -- the ONE "
          "provenance guard this aggregator relies on is unavailable. Refusing to "
          "aggregate without it (fail-closed).", file=sys.stderr)
    raise


def _independence_reason(obj: dict) -> str:
    """Delegates to build_deck._qc_independence_reason -- the existing
    independent-reviewer-provenance check every legacy per-domain gate already
    uses. If build_deck.py cannot be imported at all, this FAILS CLOSED (a
    blocking reason saying so) rather than inventing a substitute check."""
    if _bd is None or not hasattr(_bd, "_qc_independence_reason"):
        return ("AF-QC-INDEPENDENCE: cannot verify independent-reviewer provenance "
                "-- build_deck.py (the module that owns this check) is not "
                "importable in this environment. Treating provenance as unproven "
                "(fail-closed).")
    try:
        return _bd._qc_independence_reason(obj) or ""
    except Exception as exc:  # noqa: BLE001
        return f"AF-QC-INDEPENDENCE: independence check raised {exc!r} -- treating as unproven."


# ---------------------------------------------------------------------------
# Manifest-declared path resolution (requirement: read the six reports from
# their manifest-declared produces_artifact paths, not a second hardcoded copy).
# ---------------------------------------------------------------------------
def _resolve_domain_paths(explicit_manifest: Optional[str]) -> Tuple[Dict[str, str], str]:
    """Returns ({phase_id: produces_artifact}, provenance_note).

    Tries, in order:
      1. --manifest, if given.
      2. manifest_source.find_repo_root() walk-up to
         universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json (the
         canonical resolver every other lockstep tool in this scripts dir uses
         -- sync_check.py, test_producers.py).
      3. <scripts_dir>/../sops/PIPELINE-MANIFEST.json (deployed-department layout).
    Falls back to DEFAULT_DOMAIN_PATHS/DEFAULT_PRIORITY_SHIFT_PATH (with a NOTE,
    never silently) only when no manifest is found at all.
    """
    candidates: List[Path] = []
    if explicit_manifest:
        candidates.append(Path(explicit_manifest).expanduser().resolve())
    try:
        from manifest_source import find_repo_root
        root = find_repo_root(HERE)
        if root is not None:
            candidates.append(root / "universal-sops" / "presentation-slide-craft"
                               / "PIPELINE-MANIFEST.json")
    except Exception:  # noqa: BLE001
        pass
    candidates.append(HERE.parent / "sops" / "PIPELINE-MANIFEST.json")

    for cand in candidates:
        if cand.is_file():
            try:
                obj = json.loads(cand.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            paths: Dict[str, str] = {}
            for p in obj.get("phases", []):
                pa = p.get("produces_artifact")
                if isinstance(pa, list):
                    pa = pa[0] if pa else None
                if isinstance(pa, str) and p.get("id"):
                    paths[p["id"]] = pa
            wanted = set(DEFAULT_DOMAIN_PATHS) | {PRIORITY_SHIFT_PHASE_ID}
            if wanted.issubset(paths):
                return paths, f"manifest: {cand}"
            # A manifest was found but is missing one of the six phases -- do not
            # silently fall back to defaults for a manifest that is genuinely
            # stale; that is a louder problem than "no manifest at all".
            missing = sorted(wanted - set(paths))
            print(f"NOTE: manifest at {cand} is missing produces_artifact for "
                  f"{missing} -- falling back to known-good default paths for those.",
                  file=sys.stderr)
            merged = dict(DEFAULT_DOMAIN_PATHS)
            merged[PRIORITY_SHIFT_PHASE_ID] = DEFAULT_PRIORITY_SHIFT_PATH
            merged.update(paths)
            return merged, f"manifest (partial): {cand}"

    print("NOTE: no PIPELINE-MANIFEST.json could be resolved -- using the known-good "
          "default domain-report paths.", file=sys.stderr)
    merged = dict(DEFAULT_DOMAIN_PATHS)
    merged[PRIORITY_SHIFT_PHASE_ID] = DEFAULT_PRIORITY_SHIFT_PATH
    return merged, "defaults (no manifest resolved)"


# ---------------------------------------------------------------------------
# Aggregation.
# ---------------------------------------------------------------------------
def aggregate(run_dir: Path, explicit_manifest: Optional[str] = None) -> Dict[str, Any]:
    domain_paths, provenance = _resolve_domain_paths(explicit_manifest)
    domains: Dict[str, Any] = {}
    blocking_reasons: List[str] = []
    missing_domains: List[str] = []
    numeric_averages: List[float] = []

    for key, phase_id, label in AVERAGED_DOMAINS:
        rel = domain_paths[phase_id]
        p = run_dir / rel
        entry: Dict[str, Any] = {"phase": phase_id, "file": rel, "present": p.is_file(),
                                  "average": None, "reasons": []}
        if not p.is_file():
            missing_domains.append(key)
            reason = f"{label} ({phase_id}): missing domain report at {rel}"
            entry["reasons"].append(reason)
            blocking_reasons.append(reason)
            domains[key] = entry
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            reason = f"{label} ({phase_id}): report at {rel} is unreadable ({exc})"
            entry["reasons"].append(reason)
            blocking_reasons.append(reason)
            domains[key] = entry
            continue
        if not isinstance(obj, dict):
            reason = f"{label} ({phase_id}): report at {rel} is not a JSON object"
            entry["reasons"].append(reason)
            blocking_reasons.append(reason)
            domains[key] = entry
            continue

        avg = obj.get("average", obj.get("average_score"))
        avg_ok = isinstance(avg, (int, float))
        entry["average"] = avg if avg_ok else None
        if not avg_ok:
            reason = f"{label} ({phase_id}): report carries no numeric average (got {avg!r})"
            entry["reasons"].append(reason)
            blocking_reasons.append(reason)
        else:
            # Recorded for computed_average REGARDLESS of threshold -- that field is an
            # honest, diagnostic-only mean of whatever numbers exist, never the
            # gate-facing verdict. The threshold check below is what actually blocks.
            numeric_averages.append(float(avg))
            if avg < QC_PASS_THRESHOLD:
                reason = (f"{label} ({phase_id}): average {avg} is below the "
                          f"{QC_PASS_THRESHOLD} threshold")
                entry["reasons"].append(reason)
                blocking_reasons.append(reason)

        triggered = obj.get("triggered_autofails") or obj.get("autofails_triggered") or []
        if triggered:
            reason = f"{label} ({phase_id}): triggered autofails present: {triggered}"
            entry["reasons"].append(reason)
            blocking_reasons.append(reason)

        indep = _independence_reason(obj)
        if indep:
            reason = f"{label} ({phase_id}): {indep}"
            entry["reasons"].append(reason)
            blocking_reasons.append(reason)

        domains[key] = entry

    # Priority-shift ship gate: a 14-item pass/fail checklist, not a 0-10 rubric.
    ps_rel = domain_paths[PRIORITY_SHIFT_PHASE_ID]
    ps_p = run_dir / ps_rel
    ps_entry: Dict[str, Any] = {"phase": PRIORITY_SHIFT_PHASE_ID, "file": ps_rel,
                                "present": ps_p.is_file(), "pass": None,
                                "failed_items": [], "reasons": []}
    if not ps_p.is_file():
        missing_domains.append("priority_shift")
        reason = f"Priority-Shift Ship Gate ({PRIORITY_SHIFT_PHASE_ID}): missing report at {ps_rel}"
        ps_entry["reasons"].append(reason)
        blocking_reasons.append(reason)
    else:
        try:
            ps_obj = json.loads(ps_p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            reason = f"Priority-Shift Ship Gate ({PRIORITY_SHIFT_PHASE_ID}): report unreadable ({exc})"
            ps_entry["reasons"].append(reason)
            blocking_reasons.append(reason)
            ps_obj = None
        if isinstance(ps_obj, dict):
            ps_pass = ps_obj.get("pass") is True
            ps_entry["pass"] = ps_pass
            if not ps_pass:
                failed = [r.get("item") for r in (ps_obj.get("items") or [])
                          if isinstance(r, dict) and not r.get("pass")]
                ps_entry["failed_items"] = failed
                reason = (f"Priority-Shift Ship Gate ({PRIORITY_SHIFT_PHASE_ID}): "
                          f"failed on {', '.join(str(f) for f in failed) or 'unspecified item(s)'} "
                          f"(AF-PRIORITY-SHIFT)")
                ps_entry["reasons"].append(reason)
                blocking_reasons.append(reason)
        elif ps_obj is not None:
            reason = f"Priority-Shift Ship Gate ({PRIORITY_SHIFT_PHASE_ID}): report is not a JSON object"
            ps_entry["reasons"].append(reason)
            blocking_reasons.append(reason)
    domains["priority_shift"] = ps_entry

    # Whole-run-dir provenance guard -- the EXISTING mechanism (AF-QC-GENERATOR-UNGOVERNED /
    # AF-QC-RUBRIC-CORRUPT / AF-QC-REPORT-UNTRUSTED). Not reinvented here.
    findings = _qgg.scan_run_dir(run_dir)
    owner_skips = _qgg.load_owner_skip_approvals(run_dir)
    guard_blocking, guard_waived = _qgg._format_findings(findings, owner_skips)
    generator_guard = {
        "clean": not guard_blocking,
        "blocking": guard_blocking,
        "waived": guard_waived,
    }
    if guard_blocking:
        for f in guard_blocking:
            blocking_reasons.append(
                f"[{f['af_code']}] {f['file']}:{f['line']} -- {f['reason']}")
    raw_average = (sum(numeric_averages) / len(numeric_averages)
                   if len(numeric_averages) == len(AVERAGED_DOMAINS) else None)
    # F20 — round DOWN to 4dp for display, compare the RAW value against the
    # threshold. round() uses banker's rounding and rounds 8.49996 UP to 8.5,
    # letting a below-threshold deck pass on a rounding artifact. floor at the
    # display precision means displayed >= threshold implies raw >= threshold.
    computed_average = (math.floor(raw_average * 10 ** 4) / 10 ** 4
                        if raw_average is not None else None)

    overall_pass = (not blocking_reasons) and computed_average is not None \
        and computed_average >= QC_PASS_THRESHOLD

    report: Dict[str, Any] = {
        "schema": "final_qc_report/v1",
        "generator": "scripts/qc_aggregate.py",
        "manifest_provenance": provenance,
        "threshold": QC_PASS_THRESHOLD,
        "pass": overall_pass,
        "average": computed_average if overall_pass else None,
        "computed_average": computed_average,
        "domains": domains,
        "missing_domains": missing_domains,
        "generator_guard": generator_guard,
        "blocking_reasons": blocking_reasons,
    }
    if overall_pass:
        report["per_dimension"] = {
            key: domains[key]["average"] for key, _pid, _label in AVERAGED_DOMAINS
        }
        report["per_dimension"]["priority_shift_pass"] = domains["priority_shift"]["pass"]
    return report


def _print_summary(report: Dict[str, Any]) -> None:
    print("=== qc_aggregate: FINAL QC AGGREGATION ===")
    print(f"manifest provenance: {report['manifest_provenance']}")
    for key, _pid, label in AVERAGED_DOMAINS:
        d = report["domains"][key]
        status = "OK" if d["present"] and not d["reasons"] else "BLOCKED"
        print(f"  [{status}] {label}: present={d['present']} average={d['average']}")
    ps = report["domains"]["priority_shift"]
    ps_status = "OK" if ps["present"] and not ps["reasons"] else "BLOCKED"
    print(f"  [{ps_status}] Priority-Shift Ship Gate: present={ps['present']} pass={ps['pass']}")
    gg = report["generator_guard"]
    print(f"  generator_guard: clean={gg['clean']} blocking={len(gg['blocking'])} "
          f"waived={len(gg['waived'])}")
    print(f"computed_average: {report['computed_average']}")
    if report["pass"]:
        print(f"PASS -- average {report['average']} >= {report['threshold']}")
    else:
        print(f"BLOCKED -- {len(report['blocking_reasons'])} finding(s):")
        for r in report["blocking_reasons"]:
            print(f"    - {r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--phase-mode", action="store_true",
                    help="always exit 0 once the report is mechanically written; "
                         "pass/fail enforcement is left to gates.py's close()-time "
                         "qc gate (used by the manifest's script executor).")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        print(f"FATAL: --run-dir not found: {run_dir}", file=sys.stderr)
        return 2

    try:
        report = aggregate(run_dir, args.manifest)
    except Exception as exc:  # noqa: BLE001 -- a genuine mechanism failure
        print(f"FATAL: qc_aggregate could not compute a report: {exc!r}", file=sys.stderr)
        return 2

    out_path = run_dir / FINAL_REPORT_REL
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from presentation_job.checkpoint import atomic_write_text
            atomic_write_text(out_path, json.dumps(report, indent=2))
        except ImportError:
            out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"FATAL: could not write {out_path}: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        _print_summary(report)
        print(f"\nwrote {out_path}")

    if args.phase_mode:
        return 0
    return 0 if report["pass"] else 5


if __name__ == "__main__":
    sys.exit(main())
