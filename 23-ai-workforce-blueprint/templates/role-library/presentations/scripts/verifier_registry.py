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
                               run_dir=run_dir)
        except Exception:  # noqa: BLE001 — shadow compare never breaks a gate
            pass
        if _rf.enforcing():
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
    """Build the standard QC-report verifier for one of the six QC_REPORTS keys
    (copy / prompt / image / typography / speech / priority_shift). Seals the
    report's fact (existence, sha256, gate label, average, pass, autofails,
    independence, substance) and verifies it with runfacts.verify_qc — the
    SAME rubric build_deck._qc_report_gate enforces. This is the machinery the
    T1 slice (copy/typography/speech re-measure teeth) wires per report."""
    if qc_key not in QC_REPORTS:
        raise KeyError(f"{qc_key!r} is not a sealed QC report key")

    def _v(artifact_paths: Tuple[str, ...], run_dir: Path,
           config: Optional[dict]) -> Tuple[RunFacts, bool]:
        facts = _rf.seal(Path(run_dir), nonce_bound=False, force=True)
        had = facts.qc.get(qc_key) is not None and \
            facts.qc[qc_key].state is not Epistemic.ABSENT
        return facts, bool(had)

    def _verdict(facts: RunFacts) -> Tuple[Verdict, str]:
        return _rf.verify_qc(facts, qc_key)

    return VerifierSpec(
        gate=f"qc:{qc_key}",
        verifier=_v,
        verdict=_verdict,
        artifacts=(QC_REPORTS[qc_key]["path"],),
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
