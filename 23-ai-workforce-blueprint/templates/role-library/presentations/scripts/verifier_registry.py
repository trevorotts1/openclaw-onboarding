#!/usr/bin/env python3
"""
verifier_registry.py — TRUST BOUNDARY, INCREMENT 2: the verifier REGISTRY BASE
for the gate-conversion slices (T1 QC-report teeth, T2 CC-registered gate,
future slices). Extends the Increment-1 machinery (presentation_job/runfacts.py:
sealed RunFacts + shadow_compare + enforcing()) with the three things the slices
share:

  1. REGISTERED VERIFIERS — a registry of VerifierSpec entries. A verifier is a
     function (artifact_paths, config) -> sealed RunFacts. The seal is
     transactional: it does NOT mutate the shared per-run seal cache. It returns
     (RunFacts, had_input) where had_input=False means none of the spec's
     artifact paths existed, so a slice can gate on "input absent" the same way
     presentation_job.gates.Gates._qc_gate fails closed on a missing report
     (a check that defers because its input is missing is a fail-open wearing a
     fail-closed label).

  2. shadow_compare + enforcing() — reused as-is from runfacts.py (Increment-1
     pattern, merge 49ca32b6): a slice's RunFacts verdict is COMPUTED and
     compared against the legacy verdict in REPORT-ONLY mode; the legacy result
     is what callers get unless PRES_TRUST_BOUNDARY_ENFORCE=1. A divergence is
     one greppable TRUST-BOUNDARY-DIVERGENCE line per gate.

  3. register_verifier() — the wiring point the slices call to register their
     per-gate verifier functions. Registration is idempotent by gate name;
     re-registering the same name replaces the entry (last registration wins) so
     slices stay independent.

PURITY CONTRACT (enforced by gate_integrity_check.py --purity, GUARD B): every
verdict function registered here MUST be pure — (RunFacts) -> (Verdict, str),
reading ONLY already-sealed fields. Direct file/env I/O inside a verdict
function is a lint violation. The seal itself may touch disk (it is the one
front-door read); the verdict may not.

ZERO third-party deps (stdlib only), matching the rest of this package.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from presentation_job import runfacts as _rf

# ---------------------------------------------------------------------------
# Public names (re-exported so slices import ONE module)
# ---------------------------------------------------------------------------
RunFacts = _rf.RunFacts
Fact = _rf.Fact
Epistemic = _rf.Epistemic
Verdict = _rf.Verdict
RunFactsError = _rf.RunFactsError
seal = _rf.seal
get_or_seal = _rf.get_or_seal
reset_cache_for_tests = _rf.reset_cache_for_tests
shadow_compare = _rf.shadow_compare
enforcing = _rf.enforcing
SEALED_REL = _rf.SEALED_REL
FINDING_PREFIX = _rf.FINDING_PREFIX
DIVERGENCE_PREFIX = _rf.DIVERGENCE_PREFIX

QC_REPORTS: Dict[str, Dict[str, Optional[str]]] = dict(_rf.QC_REPORTS)

# ---------------------------------------------------------------------------
# FIX 33 — QC independence provable; a real vision route (MASTER Part 8).
# "the dispatcher stamps graded_by_provider, graded_by_model, request_id into
# every QC artifact it authors; qc_aggregate AND verifier_registry.
# qc_report_verifier fail a report whose model equals the authoring stamp for
# the same range or lacks a request id."
#
# This module's share: the qc_report_verifier seal (the ONE front-door read the
# purity contract allows) ALSO captures the report's FIX 33 vision-unit stamp
# (graded_by_provider / graded_by_model / request_id + the authoring stamp it
# must differ from), and the verdict fails when
#   * graded_by_model is absent, OR equals the authoring stamp (self-graded
#     vision pass), OR
#   * request_id is absent (the report names no route).
# The captured snapshot is stored in _FIX33_SNAPSHOTS keyed by (qc_key,
# sha256) AT SEAL TIME; the verdict reads only that sealed snapshot — no file
# I/O in the verdict, so the purity contract holds. A qc_key with no captured
# snapshot (artifact absent, or a non-image key whose report carries no
# vision-unit stamp at all) is not FIX-33-judged: the contract is about
# artifacts the dispatcher AUTHORS with a vision-unit stamp, not about
# reports that never claimed one.
#
# Rollback: PRESENTATION_FIX33_REGISTRY_CONTRACT=0 restores the pre-FIX-33
# verifier verdicts exactly. Default is ON.
# ---------------------------------------------------------------------------
FIX33_REGISTRY_ROLLBACK_FLAG = "PRESENTATION_FIX33_REGISTRY_CONTRACT"

FIX33_PROVIDER_KEYS = ("graded_by_provider", "vision_provider", "provider")
FIX33_MODEL_KEYS = ("graded_by_model", "vision_model", "multimodal_model",
                    "ocr_engine", "vision_engine", "reviewer_vision_model")
FIX33_REQUEST_KEYS = ("request_id", "route_request_id", "vision_request_id")
FIX33_AUTHORING_KEYS = ("graded_by", "builder", "built_by", "reviewer",
                        "reviewed_by")
FIX33_AF_CODE = "AF-IMAGE-QC-UNIT"

# (qc_key, sha256) -> {"graded_model": str, "authoring_stamp": str,
#                      "request_id": str, "has_stamp": bool}
# Written ONLY inside the qc_report_verifier seal (front-door read time);
# read ONLY by the pure verdict. Cleared by reset_fix33_snapshots().
_FIX33_SNAPSHOTS: Dict[Tuple[str, str], Dict[str, Any]] = {}


def reset_fix33_snapshots() -> None:
    """Test hook: drop every captured FIX 33 snapshot (call alongside
    reset_cache_for_tests between fixtures)."""
    _FIX33_SNAPSHOTS.clear()


def _fix33_first_str(src: dict, keys) -> str:
    for k in keys:
        v = src.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _fix33_capture(qc_key: str, obj: Optional[dict], sha256: str) -> None:
    """Seal-time capture of a report's FIX 33 vision-unit stamp. Called from
    the qc_report_verifier's front-door read; stores the snapshot the pure
    verdict later consumes. Only reports that carry (or should carry) the
    dispatcher's stamp are captured — a report with none of the FIX 33 keys
    anywhere is snapshotted with has_stamp=False and the verdict treats a
    captured report for the IMAGE range as missing its stamp (fail), while
    other ranges are not FIX-33-judged unless they DO carry a stamp."""
    if obj is None:
        _FIX33_SNAPSHOTS.pop((qc_key, sha256), None)
        return
    graded_model = _fix33_first_str(obj, FIX33_MODEL_KEYS)
    request_id = _fix33_first_str(obj, FIX33_REQUEST_KEYS)
    blk = obj.get("qc_independence")
    blk = blk if isinstance(blk, dict) else {}
    authoring_stamp = ""
    for src in (blk, obj):
        stamp = _fix33_first_str(src, FIX33_AUTHORING_KEYS)
        if stamp:
            authoring_stamp = stamp
            break
    has_stamp = bool(graded_model or request_id
                     or _fix33_first_str(obj, FIX33_PROVIDER_KEYS))
    _FIX33_SNAPSHOTS[(qc_key, sha256)] = {
        "graded_model": graded_model,
        "authoring_stamp": authoring_stamp,
        "request_id": request_id,
        "has_stamp": has_stamp,
    }


def _fix33_registry_enabled() -> bool:
    return os.environ.get(FIX33_REGISTRY_ROLLBACK_FLAG) != "0"


def _fix33_verdict_problems(qc_key: str, fact_value: Any) -> List[str]:
    """PURE. FIX 33 verdict contribution for one sealed QC report fact:
    a report whose graded_by_model equals the authoring stamp for the same
    range, or that lacks a request_id, FAILS. Reads ONLY the snapshot the
    seal captured — never a file, never the environment."""
    if not _fix33_registry_enabled():
        return []
    snap = _FIX33_SNAPSHOTS.get((qc_key, getattr(fact_value, "sha256", "")))
    if snap is None:
        return []
    # Only the IMAGE range is fix-33-judged when the report carries no stamp
    # at all (a report that never claimed a vision unit is judged by the
    # existing independence/rubric checks; a report that DID claim one must
    # prove it).
    problems: List[str] = []
    if not snap["has_stamp"] and qc_key != "image":
        return []
    graded_model = snap["graded_model"]
    if not graded_model:
        problems.append(
            f"{FIX33_AF_CODE}: {getattr(fact_value, 'rel_path', qc_key)} declares "
            "no graded_by_model — FIX 33 requires the dispatcher's vision-unit "
            "stamp (graded_by_provider/graded_by_model/request_id) in every QC "
            "artifact the dispatcher authors.")
    elif (snap["authoring_stamp"]
          and graded_model.strip().lower() == snap["authoring_stamp"].strip().lower()):
        problems.append(
            f"{FIX33_AF_CODE}: graded_by_model {graded_model!r} equals the "
            f"report's authoring stamp {snap['authoring_stamp']!r} for the same "
            "range — the author graded its own work. FIX 33: the vision route "
            "that graded the deck must be a DIFFERENT model from the authoring "
            "stamp (cross-graded, never self-graded).")
    if not snap["request_id"]:
        problems.append(
            f"{FIX33_AF_CODE}: {getattr(fact_value, 'rel_path', qc_key)} carries "
            "no request_id — FIX 33 requires the vision route's request id in "
            "the report so every grade is traceable to the unit call that "
            "produced it.")
    return problems


# ---------------------------------------------------------------------------
# The verifier signature
# ---------------------------------------------------------------------------
# A verifier is:
#     callable(artifact_paths: Tuple[str, ...], run_dir: Path,
#              config: Optional[dict]) -> (RunFacts, had_input: bool)
# artifact_paths are run_dir-relative (glob patterns allowed). config is
# per-spec metadata the verifier may consult (e.g. {"qc_key": "typography"}).
# The verifier MUST call seal() with force=True and MUST NOT mutate the shared
# seal cache (see VerifierSpec.seal_into below). The sealed facts carry every
# fact the verdict function needs; the verdict function is pure.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifierSpec:
    """One registered gate verifier.

    gate      — the gate name (e.g. "qc:typography"). Registered in VERIFIERS.
    verifier  — (artifact_paths, run_dir, config) -> (RunFacts, had_input)
    verdict   — PURE (RunFacts) -> (Verdict, str). Must be in
                gate_integrity_check.PURITY_ASSERTED_FUNCTIONS to be
                AST-linted pure (or assert purity yourself).
    artifacts — run_dir-relative paths/globs the verifier needs present.
    legacy    — optional (run_dir) -> (ok: bool, reasons: list[str]); when set,
                run_verifier() shadow-compares the RunFacts verdict against it.
    config    — optional per-spec dict passed through to verifier().
    """

    gate: str
    verifier: Callable
    verdict: Callable
    artifacts: Tuple[str, ...] = ()
    legacy: Optional[Callable] = None
    config: Optional[dict] = None

    def seal_into(self, run_dir: Path) -> Tuple[RunFacts, bool]:
        """Transactional seal for THIS spec. Runs the verifier against a fresh
        seal (force=True) and restores the shared cache afterwards, so a slice's
        seal can never poison the process-wide Increment-1 cache (which other
        gates still read). Never raises: every read failure is a degraded Fact,
        and a missing artifact set is had_input=False, not an exception."""
        cache_before = dict(_rf._SEAL_CACHE)
        try:
            facts, had = self.verifier(tuple(self.artifacts), Path(run_dir),
                                       self.config)
            return facts, bool(had)
        except Exception as exc:  # noqa: BLE001 — a broken seal must not block a gate
            try:
                print(f"{_rf.ERROR_PREFIX} verifier={self.gate} seal raised {exc!r}",
                      file=sys.stderr)
            except Exception:  # noqa: BLE001
                pass
            return _rf.get_or_seal(run_dir), False
        finally:
            try:
                _rf._SEAL_CACHE.clear()
                _rf._SEAL_CACHE.update(cache_before)
            except Exception:  # noqa: BLE001
                pass

    def verdict_on(self, facts: RunFacts) -> Tuple[Verdict, str]:
        """Pure verdict over an already-sealed RunFacts. Never raises: a broken
        verdict degrades to UNDETERMINED with the exception named (UNDETERMINED
        refuses to coerce to a boolean, so a degraded verdict can never be
        mistaken for a pass)."""
        try:
            v, d = self.verdict(facts)
            return v, str(d)
        except Exception as exc:  # noqa: BLE001
            return Verdict.UNDETERMINED, f"{self.gate} verdict raised {exc!r}"

    def run_verifier(self, run_dir: Path) -> Tuple[bool, List[str]]:
        """Run this verifier end-to-end against run_dir.

        Returns the (ok, reasons) contract the phase verifiers already use.
        REPORT-ONLY by default: when self.legacy is set, the legacy result is
        what is returned unless PRES_TRUST_BOUNDARY_ENFORCE=1 — the RunFacts
        verdict is computed, shadow-compared (one DIVERGENCE line on mismatch),
        and returned only when enforcing. When self.legacy is NOT set, the
        RunFacts verdict is authoritative (the slice took over the gate).

        A missing artifact set is FAIL with a reason naming the exact missing
        path(s) — the Gates._qc_gate fail-closed contract: a check that cannot
        find its input does not get to pass."""
        try:
            facts, had_input = self.seal_into(Path(run_dir))
        except Exception as exc:  # noqa: BLE001
            return False, [f"{self.gate}: seal failed {exc!r}"]
        verdict, detail = self.verdict_on(facts)

        if not had_input:
            missing = "; ".join(self.artifacts) or "no artifact paths declared"
            return False, [
                f"{self.gate}: no input artifact found ({missing}) — a gate "
                f"whose input is absent does not pass"
            ]

        if self.legacy is None:
            if verdict is Verdict.PASS:
                return True, []
            if verdict is Verdict.UNDETERMINED:
                return False, [f"{self.gate}: {detail}"]
            return False, [f"{self.gate}: {detail}"]

        legacy_ok, legacy_reasons = self.legacy(Path(run_dir))
        try:
            _rf.shadow_compare(self.gate, bool(legacy_ok),
                               "; ".join(legacy_reasons), verdict, detail,
                               run_dir=run_dir, facts=facts)
        except Exception:  # noqa: BLE001 — shadow compare never breaks a gate
            pass
        # SEALED mode (facts.enforcing) -- never a live os.environ re-read --
        # so this decision cannot drift mid-run. `facts` here comes from
        # self.seal_into() above, i.e. from a TRANSACTIONAL force=True
        # reseal: presentation_job/runfacts.py resolves the enforcement mode
        # once per run_dir on FIRST touch and reuses it for every later
        # seal() call for that run_dir, forced or not (see
        # _resolve_enforcing_mode()) -- so this is the run's one true sealed
        # mode, not a fresh read for this particular gate check.
        if facts.enforcing:
            if verdict is Verdict.PASS:
                return True, []
            if verdict is Verdict.UNDETERMINED:
                return False, [f"{self.gate}: {detail}"]
            return False, [f"{self.gate}: {detail}"]
        return bool(legacy_ok), list(legacy_reasons)


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------
VERIFIERS: Dict[str, VerifierSpec] = {}


def register_verifier(spec: VerifierSpec) -> VerifierSpec:
    """Register a VerifierSpec under spec.gate. Idempotent by name: a later
    registration with the same gate REPLACES the earlier one (last registration
    wins) so the slices stay independent and re-import safe."""
    VERIFIERS[spec.gate] = spec
    return spec


def get_verifier(gate: str) -> Optional[VerifierSpec]:
    return VERIFIERS.get(gate)


def known_gates() -> Tuple[str, ...]:
    return tuple(sorted(VERIFIERS))


def run_gate(gate: str, run_dir: Path) -> Tuple[bool, List[str]]:
    """Run a registered gate by name against run_dir. Unknown gate is
    fail-closed, matching phase_verifiers.verify() for unmapped phases."""
    spec = VERIFIERS.get(gate)
    if spec is None:
        return False, [f"no verifier registered for gate {gate!r} — fail-closed"]
    return spec.run_verifier(run_dir)


# ---------------------------------------------------------------------------
# Verifier factories for the common shapes
# ---------------------------------------------------------------------------
def qc_report_verifier(qc_key: str) -> VerifierSpec:
    """Build the standard QC-report verifier for one of the sealed QC_REPORTS
    keys (copy / prompt / image / typography / speech — the 0-10 rubric
    reports). Seals the report's fact (existence, sha256, gate label, average,
    pass, autofails, independence, substance) and verifies it with
    runfacts.verify_qc — the SAME rubric build_deck._qc_report_gate enforces.
    This is the machinery the T1 slice (copy/typography/speech re-measure
    teeth) wires per report, and SLICE-2 uses it for P-SPEECH-QC. NOT for
    priority_shift (a ledger, not a 0-10 rubric) or final (the aggregate — see
    priority_shift_verifier / final_qc_verifier)."""
    if qc_key not in QC_REPORTS:
        raise KeyError(f"{qc_key!r} is not a sealed QC report key")

    def _v(artifact_paths: Tuple[str, ...], run_dir: Path,
           config: Optional[dict]) -> Tuple[RunFacts, bool]:
        facts = _rf.seal(Path(run_dir), nonce_bound=False, force=True)
        fact = facts.qc.get(qc_key)
        had = fact is not None and fact.state is not Epistemic.ABSENT
        # FIX 33 — capture the report's vision-unit stamp at the seal's
        # front-door read so the PURE verdict can judge it later without
        # touching the file again. A KNOWN fact carries the parsed report's
        # sha256; re-reading the same bytes here is the one allowed read.
        if had and fact.state is Epistemic.KNOWN:
            info = fact.value
            try:
                p = Path(run_dir) / QC_REPORTS[qc_key]["path"]
                obj = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
                if not isinstance(obj, dict):
                    obj = None
            except Exception:  # noqa: BLE001 — capture must never break a seal
                obj = None
            _fix33_capture(qc_key, obj, getattr(info, "sha256", ""))
        return facts, bool(had)

    def _verdict(facts: RunFacts) -> Tuple[Verdict, str]:
        base_verdict, base_detail = _rf.verify_qc(facts, qc_key)
        fact = facts.qc.get(qc_key)
        # FIX 33 — cross-graded + request-id teeth on top of the existing
        # rubric. Composes: the base rubric problems stay the headline; the
        # FIX 33 findings are appended (a base FAIL keeps its reasons).
        if fact is not None and fact.state is Epistemic.KNOWN:
            fix33 = _fix33_verdict_problems(qc_key, fact.value)
            if fix33:
                if base_verdict is Verdict.FAIL:
                    return Verdict.FAIL, base_detail + " | " + "; ".join(fix33)
                return Verdict.FAIL, "; ".join(fix33)
        return base_verdict, base_detail

    return VerifierSpec(
        gate=f"qc:{qc_key}",
        verifier=_v,
        verdict=_verdict,
        artifacts=(QC_REPORTS[qc_key]["path"],),
        legacy=None,
        config=None,
    )


def priority_shift_verifier() -> VerifierSpec:
    """SLICE-2: P-SHIFT-QC (order 7.5). Verifier for the priority-shift ship
    gate's ledger report (working/qc/priority_shift_report.json). The ledger is
    written by build_deck._chk_priority_shift_ledger from its own 14-item +
    per-slide measurements — the REAL artifact. The verdict re-derives the
    ledger's decided value from the SEALED fact (runfacts.verify_priority_shift)
    instead of trusting the file's existence. Authoritative (legacy=None): this
    slice takes over the gate."""
    if "priority_shift" not in QC_REPORTS:
        raise KeyError("'priority_shift' is not a sealed QC report key")

    def _v(artifact_paths: Tuple[str, ...], run_dir: Path,
           config: Optional[dict]) -> Tuple[RunFacts, bool]:
        facts = _rf.seal(Path(run_dir), nonce_bound=False, force=True)
        had = facts.qc.get("priority_shift") is not None and \
            facts.qc["priority_shift"].state is not Epistemic.ABSENT
        return facts, bool(had)

    return VerifierSpec(
        gate="qc:priority_shift",
        verifier=_v,
        verdict=lambda facts: _rf.verify_priority_shift(facts),
        artifacts=(QC_REPORTS["priority_shift"]["path"],),
        legacy=None,
        config=None,
    )


def final_qc_verifier() -> VerifierSpec:
    """SLICE-2: P-QC-AGGREGATE (order 8.65). Verifier for the FINAL QC aggregate
    report (working/qc/final_qc_report.json, produced by qc_aggregate.py from
    the six domain reports). Re-measures the REAL artifacts: the verdict
    (runfacts.verify_final_qc) independently re-derives every one of the six
    sealed domain facts it claims to aggregate under the SAME per-domain rubric
    (verify_qc), never trusting the aggregate's headline alone. Authoritative
    (legacy=None): this slice takes over the gate."""
    if "final" not in QC_REPORTS:
        raise KeyError("'final' is not a sealed QC report key")

    def _v(artifact_paths: Tuple[str, ...], run_dir: Path,
           config: Optional[dict]) -> Tuple[RunFacts, bool]:
        facts = _rf.seal(Path(run_dir), nonce_bound=False, force=True)
        had = facts.qc.get("final") is not None and \
            facts.qc["final"].state is not Epistemic.ABSENT
        return facts, bool(had)

    return VerifierSpec(
        gate="qc:final",
        verifier=_v,
        verdict=lambda facts: _rf.verify_final_qc(facts),
        artifacts=(QC_REPORTS["final"]["path"],),
        legacy=None,
        config=None,
    )


def artifact_verifier(gate: str, pattern: str,
                      check: Callable[[RunFacts], Tuple[Verdict, str]],
                      legacy: Optional[Callable] = None) -> VerifierSpec:
    """Factory for a single-artifact verifier: seals the file that glob
    `pattern` resolves to (as an opaque Fact carrying sha256 + text/JSON parse
    state), then delegates the verdict to the pure `check` function. `legacy`,
    when given, is the (run_dir) -> (ok, reasons) callable the gate is
    shadow-compared against in report-only mode."""
    def _v(artifact_paths: Tuple[str, ...], run_dir: Path,
           config: Optional[dict]) -> Tuple[RunFacts, bool]:
        facts = _rf.seal(Path(run_dir), nonce_bound=False, force=True)
        had = bool(_resolve_first(Path(run_dir), pattern))
        return facts, had

    return VerifierSpec(
        gate=gate,
        verifier=_v,
        verdict=check,
        artifacts=(pattern,),
        legacy=legacy,
        config=None,
    )


def _resolve_first(run_dir: Path, pattern: str) -> Optional[Path]:
    if not pattern:
        return None
    if "*" in pattern or "?" in pattern:
        hits = sorted(run_dir.glob(pattern))
        return hits[0] if hits else None
    p = run_dir / pattern
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# SLICE 3 — composite / multi-artifact gate verifiers. Each gate re-measures
# MORE than one artifact at seal time (a 10-key deliverable bundle, a JSON
# ledger, a dual-PDF pair, a video + its timing track, a sync record + the
# PPTX it mutated, two speech files under a strip-equals prover). The pure
# verdicts live in runfacts.py (verify_deliverables / verify_media_library /
# verify_workbook / verify_webinar_video / verify_notes_sync /
# verify_fish_tag) and are registered here as VerifierSpecs so the both-
# direction test harness and the phase_verifiers wiring share one source.
# ---------------------------------------------------------------------------
def composite_verifier(gate: str, verdict_fn: Callable[[RunFacts], Tuple[Verdict, str]],
                       artifact_paths: Tuple[str, ...],
                       legacy: Optional[Callable] = None) -> VerifierSpec:
    """Build a slice-3 composite verifier. The seal reads every artifact the
    gate re-measures exactly once; the verdict is the pure runfacts function
    (never opens a file — enforced by gate_integrity_check --purity). had_input
    is True when ANY declared artifact exists — a composite gate may legitimately
    run with some keys absent (that is what its verdict FAILs on, D10)."""
    def _v(artifact_paths_: Tuple[str, ...], run_dir: Path,
           config: Optional[dict]) -> Tuple[RunFacts, bool]:
        facts = _rf.seal(Path(run_dir), nonce_bound=False, force=True)
        had = any(_resolve_first(Path(run_dir), pat) is not None for pat in artifact_paths_)
        return facts, had

    return VerifierSpec(
        gate=gate,
        verifier=_v,
        verdict=verdict_fn,
        artifacts=artifact_paths,
        legacy=legacy,
        config=None,
    )


def slice3_verifiers() -> Tuple[VerifierSpec, ...]:
    """Build (not register) the slice-3 composite-gate VerifierSpecs.

    `legacy` is deliberately None for every one: the phase_verifiers wiring
    (_shadow_*_verifier in phase_verifiers.py) owns the legacy shadow-compare
    at the phase level and passes the legacy fn there — registering it here
    too would double-compare. A slice-3 spec run directly (both_directions,
    run_gate) is therefore authoritative on the RunFacts verdict, exactly like
    the qc_report_verifier specs."""
    _FISH_TAG_ARTIFACTS = (
        "working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md",
        "working/deliverables/PRESENTERS-SPEECH.md",
    )
    return (
        composite_verifier(
            "deliverables:bundle",
            _rf.verify_deliverables,
            (
                "working/delivery/*-FINAL.pptx",
                "working/delivery/*-FINAL.pdf",
                "working/deliverables/PRESENTER-GUIDE.pdf",
                "working/deliverables/PRESENTERS-SPEECH.md",
                "working/deliverables/PRESENTERS-SPEECH.pdf",
                "working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md",
                "working/delivery/PRESENTER-AUDIO.mp3",
                "working/delivery/infographic.png",
                "working/deliverables/presenter-teleprompter.html",
                "working/delivery/*-WEBINAR.mp4",
            ),
        ),
        composite_verifier(
            "ghl_upload:ledger",
            _rf.verify_media_library,
            ("working/checkpoints/media_library.json",),
        ),
        composite_verifier(
            "workbook:both",
            _rf.verify_workbook,
            ("working/deliverables/*-WORKBOOK.pdf",
             "working/deliverables/*-WORKBOOK-FILLABLE.pdf"),
        ),
        composite_verifier(
            "webinar_video:video",
            _rf.verify_webinar_video,
            ("working/delivery/*-WEBINAR.mp4",
             "working/checkpoints/webinar_timing.json"),
        ),
        composite_verifier(
            "notes_sync:sync",
            _rf.verify_notes_sync,
            ("working/checkpoints/notes_sync.json",),
        ),
        composite_verifier(
            "fish_tag:strip_equals",
            _rf.verify_fish_tag,
            _FISH_TAG_ARTIFACTS,
        ),
    )


def register_slice3() -> None:
    """Register all slice-3 composite-gate verifiers. Idempotent: re-registration
    replaces (last wins) per register_verifier. Called from phase_verifiers'
    shadow wiring so the registry is populated wherever the phases run."""
    for spec in slice3_verifiers():
        register_verifier(spec)


# ---------------------------------------------------------------------------
# The both-direction test harness: fabricated artifact REJECTED / genuine PASSES
# ---------------------------------------------------------------------------
# Shared by every slice test so the "fabricated -> reject, genuine -> pass"
# pair is exercised identically. Fabricated means the artifact exists and parses
# but fails the rubric; genuine means it satisfies it.
# ---------------------------------------------------------------------------
def both_directions(spec: VerifierSpec, run_dir: Path, *,
                    fabricate: Callable[[Path], None],
                    genuine: Callable[[Path], None]) -> Dict[str, Any]:
    """Run the both-direction pattern against a fresh run_dir.

      * write_fabricated() must produce a present-but-failing artifact;
        run_verifier() must return ok=False with a reason naming what could not
        be reproduced (assert in the caller).
      * then write_genuine() must produce a passing artifact; run_verifier()
        must return ok=True.

    Returns {"fabricated": (ok, reasons), "genuine": (ok, reasons)}."""
    out: Dict[str, Any] = {}
    try:
        fabricate(Path(run_dir))
        out["fabricated"] = spec.run_verifier(Path(run_dir))
    finally:
        reset_cache_for_tests()
    try:
        genuine(Path(run_dir))
        out["genuine"] = spec.run_verifier(Path(run_dir))
    finally:
        reset_cache_for_tests()
    return out


def write_fixture(run_dir: Path, rel: str, obj_or_text) -> Path:
    """Write a fixture file under run_dir (dirs created), JSON-encoding dicts."""
    p = Path(run_dir) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj_or_text, (dict, list)):
        p.write_text(json.dumps(obj_or_text))
    else:
        p.write_text(str(obj_or_text))
    return p
