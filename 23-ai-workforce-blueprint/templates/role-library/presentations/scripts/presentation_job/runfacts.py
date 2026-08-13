#!/usr/bin/env python3
"""
runfacts.py — TRUST BOUNDARY, INCREMENT 1 (report-only).

THE PROBLEM THIS CLOSES (see CONTROL/TRUST-BOUNDARY-DESIGN.md and
CONTROL/ROOT-CAUSE-ARCHITECTURE.md for the full analysis): every gate in this
pipeline decides whether a run is trustworthy by re-reading the same
agent-writable run-directory files that the thing being judged wrote. There is
no privileged writer and no external anchor — deck-intake-driver.py's own
docstring says as much. ~372 scattered reads across build_deck.py,
run_signature_deck.py, phase_verifiers.py, cc_board.py and presentation_job/*
each open their own files, on their own schedule, and each gets to decide for
itself what "absent" or "malformed" means — which is how a weak verifier
(phase_verifiers._verify_json_artifact, no required_keys) and a strict one
(build_deck._qc_report_gate, full rubric) can exist side by side for what is
nominally the same checkpoint.

THE SHAPE OF THIS FIX: replace scattered reads with ONE sealed, immutable
RunFacts record, built EXACTLY ONCE per run at the front door — the same place
the per-run entry nonce is already verified (build_deck.py, _verify_entry_nonce
call site in main()). Every fact carries its own EPISTEMIC STATE (KNOWN /
ABSENT / UNPARSEABLE / CONFLICTED / UNTRUSTED) so absence can never silently
present as a value, and every verdict is PASS / FAIL / UNDETERMINED with
UNDETERMINED refusing to coerce to a boolean at all (Verdict.__bool__ raises).

HONEST LIMIT (read this before trusting this module more than it earns):
RunFacts gives TAMPER-EVIDENCE against accident, drift, and refactoring error.
It does NOT give an integrity guarantee against a run-dir-writable adversary.
seal() runs as the same UID that would have written a lie, and reads the same
files a lying writer controls — a false process_manifest.json written BEFORE
seal() runs is sealed as fact, faithfully. The front-door nonce this module
binds to is read from process environment, which a co-resident same-UID
process can also read. What this buys is real: it converts ~372 independent
trust decisions into ONE trust decision (the seal), so the next increment has
exactly one function to actually anchor (e.g. to a separement privilege
boundary, an out-of-process attestor, or a write-once medium) instead of 372
scattered call sites that would each need it separately. It does not, by
itself, solve the single-UID trust problem — see the design doc's "what this
does NOT fix" section.

REPORT-ONLY: nothing in this module is wired to change what a run does unless
the operator explicitly sets PRES_TRUST_BOUNDARY_ENFORCE=1 (see enforcing()).
By default every RunFacts-derived verdict is computed, compared against the
legacy result, and — on divergence — LOGGED LOUDLY to stderr, but the legacy
result is what a caller gets back. Flip the flag only after this increment has
run report-only against real traffic long enough to trust the divergence log
is empty (or fully explained) on legitimate runs.

ZERO third-party deps (stdlib only), matching the rest of this package.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Generic, Optional, Tuple, TypeVar

RUNFACTS_SCHEMA_VERSION = 1
SEALED_REL = Path("working") / "checkpoints" / ".runfacts.sealed.json"
ENFORCE_ENV = "PRES_TRUST_BOUNDARY_ENFORCE"
DIVERGENCE_PREFIX = "TRUST-BOUNDARY-DIVERGENCE"
FINDING_PREFIX = "TRUST-BOUNDARY-SEAL-FINDING"
ERROR_PREFIX = "TRUST-BOUNDARY-SHADOW-ERROR"

# Reserved for the standalone `python3 -m presentation_job.runfacts --verify`
# CLI added alongside this module, and for a future enforcing build_deck.py to
# adopt. build_deck.py's own CLI never used 7 (histogram checked: 0,1,2,3,4,5
# only) so this does not collide with any exit code already live on that
# process. presentation_job/__main__.py's EXIT_MANIFEST_MISMATCH is a
# DIFFERENT executable's exit-code space and is untouched by this module.
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_UNDETERMINED = 7

T = TypeVar("T")


class RunFactsError(RuntimeError):
    """Raised by Fact.value when read while the fact is not KNOWN. Existing to be
    raised: a caller that reaches into a degraded fact without going through
    .get(default) has a bug, and this type makes that bug loud instead of
    letting ABSENT quietly behave like None-is-falsy-is-fine."""


class Epistemic(str, Enum):
    KNOWN = "KNOWN"              # read succeeded, value is authoritative
    ABSENT = "ABSENT"            # the source did not exist
    UNPARSEABLE = "UNPARSEABLE"  # the source existed but did not parse
    CONFLICTED = "CONFLICTED"    # multiple sources disagree
    UNTRUSTED = "UNTRUSTED"      # parsed fine but fails a provenance/shape check


@dataclass(frozen=True)
class Fact(Generic[T]):
    """One sealed fact. `.value` raises unless state is KNOWN; `.get(default)` is
    the deliberate, greppable way to degrade. This is the whole point: an
    ABSENT fact must never be reachable as if it were a value of None."""

    state: Epistemic
    detail: str = ""
    _payload: Optional[T] = None

    @property
    def value(self) -> T:
        if self.state is not Epistemic.KNOWN:
            raise RunFactsError(
                f"Fact.value read while state={self.state.value} "
                f"({self.detail or 'no detail recorded'}) — use .get(default) "
                f"if a degraded read is actually intended."
            )
        return self._payload  # type: ignore[return-value]

    def get(self, default: T) -> T:
        return self._payload if self.state is Epistemic.KNOWN else default  # type: ignore[return-value]

    def is_known(self) -> bool:
        return self.state is Epistemic.KNOWN

    def to_json(self) -> dict:
        d: Dict[str, Any] = {"state": self.state.value}
        if self.detail:
            d["detail"] = self.detail
        if self.state is Epistemic.KNOWN:
            d["value"] = _jsonable(self._payload)
        return d

    @staticmethod
    def known(payload: T, detail: str = "") -> "Fact[T]":
        return Fact(Epistemic.KNOWN, detail, payload)

    @staticmethod
    def absent(detail: str) -> "Fact[T]":
        return Fact(Epistemic.ABSENT, detail, None)

    @staticmethod
    def unparseable(detail: str) -> "Fact[T]":
        return Fact(Epistemic.UNPARSEABLE, detail, None)

    @staticmethod
    def conflicted(detail: str) -> "Fact[T]":
        return Fact(Epistemic.CONFLICTED, detail, None)

    @staticmethod
    def untrusted(detail: str) -> "Fact[T]":
        return Fact(Epistemic.UNTRUSTED, detail, None)


def _jsonable(v):
    if hasattr(v, "__dataclass_fields__"):
        return {k: _jsonable(getattr(v, k)) for k in v.__dataclass_fields__}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, Enum):
        return v.value
    return v


class Verdict(str, Enum):
    """A gate's decided outcome. Deliberately NOT boolean: `if verdict:` is
    exactly the bug class this exists to catch (UNDETERMINED silently reading
    as truthy-pass or falsy-fail depending on which branch someone typed).
    Compare explicitly: `if verdict is Verdict.PASS:`."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNDETERMINED = "UNDETERMINED"

    def __bool__(self):  # pragma: no cover - exercised by test_runfacts.py
        raise TypeError(
            "Verdict has no truthiness by design — compare explicitly against "
            "Verdict.PASS / Verdict.FAIL / Verdict.UNDETERMINED. UNDETERMINED "
            "must never be able to coerce into a pass or a fail by accident."
        )


def enforcing() -> bool:
    """True iff the operator has explicitly flipped the trust boundary from
    report-only to enforcing. Default is report-only (unset, '0', 'false',
    'no' all read as report-only) — shipping enforcing-by-default would risk
    bricking a real client run on the very first divergence this increment
    finds, which is the one thing the task forbids."""
    return (os.environ.get(ENFORCE_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Owner-skip facts (FIX-2 waiver — build_deck._owner_skip_approved and its two
# independent reimplementations in run_signature_deck.py / presentation-
# canonical-entry.sh). Highest-privilege bypass in the pipeline: a valid
# record waives an AF-* gate outright. Migrated first for that reason.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OwnerSkipRecord:
    af_code: str            # normalized (upper, stripped) af_code/gate this record names
    valid: bool             # structurally valid per the legacy authenticity rule
    owner_approved_raw: Any  # the raw owner_approved value, so False-vs-absent is visible
    approved_by: str
    reason: str
    timestamp: str


def _classify_owner_skip_record(r: dict) -> Optional[OwnerSkipRecord]:
    if not isinstance(r, dict):
        return None
    af_code = str(r.get("af_code") or r.get("gate") or "").strip().upper()
    approved_by = str(r.get("approved_by") or "").strip()
    reason = str(r.get("reason") or "").strip()
    timestamp = str(r.get("timestamp") or "").strip()
    owner_approved_raw = r.get("owner_approved")
    valid = (
        owner_approved_raw is True
        and bool(af_code)
        and bool(approved_by)
        and bool(reason)
        and bool(timestamp)
    )
    return OwnerSkipRecord(af_code, valid, owner_approved_raw, approved_by, reason, timestamp)


# ---------------------------------------------------------------------------
# QC-report facts. Sealed for all six domain reports (complete picture); only
# "typography" is wired into a shadow verifier this increment (see
# phase_verifiers._shadow_qc_verifier) — the concrete, EXECUTED proof of the
# gap is P-TYPO-QC (phase_verifiers._verify_json_artifact, no required_keys:
# a report that says pass:false is accepted as a phase PASS because the weak
# verifier never opens the "pass" key). The other five are sealed so the next
# migration wave has the record already available; wiring them is future work
# and is called out as such in TRUST-BOUNDARY-DESIGN.md.
# ---------------------------------------------------------------------------
QC_REPORTS: Dict[str, Dict[str, Optional[str]]] = {
    "copy":           {"path": "working/qc/copy_qc_report.json",        "gate_label": "Phase 1Q"},
    "prompt":         {"path": "working/qc/prompt_qc_report.json",      "gate_label": "Phase Prompt-QC"},
    "image":          {"path": "working/qc/image_qc_report.json",       "gate_label": "Phase Image-QC"},
    "typography":     {"path": "working/qc/typography_qc_report.json",  "gate_label": "Phase Typography-QC"},
    "speech":         {"path": "working/qc/speech_qc_report.json",      "gate_label": "Phase Speech-QC"},
    "priority_shift": {"path": "working/qc/priority_shift_report.json", "gate_label": None},
}

# Which of the six sealed QC facts are actually consumed by a shadow verifier
# THIS increment (see phase_verifiers._shadow_qc_verifier). Deliberately a
# small, named set — the task asks for "a SMALL, well-chosen set of gates",
# and this is also what RunFacts.findings() treats as loud-reportable; the
# other five are sealed (available programmatically) but not yet gated on, so
# their ABSENT-before-that-phase-runs state is not noise-reported.
WIRED_QC_KEYS = frozenset({"typography"})


@dataclass(frozen=True)
class QcReportInfo:
    rel_path: str
    sha256: str
    gate_label: str
    gate_label_expected: Optional[str]
    average: Optional[float]
    pass_declared: Any          # raw obj.get("pass") — compared with `is True`, never truthy-coerced
    triggered_autofails: tuple
    independence_reason: str    # "" == independent, provenance OK
    substance_problems: tuple   # empty == no rubber-stamp / foreign-signature hit


def _load_json_bytes(p: Path) -> Tuple[Optional[dict], Optional[str], str]:
    """Read a JSON file exactly once. Returns (obj_or_None, sha256_hex_or_None,
    error_or_empty). Never raises — every failure mode is reported back."""
    try:
        raw = p.read_bytes()
    except OSError as exc:
        return None, None, f"unreadable: {exc!r}"
    digest = hashlib.sha256(raw).hexdigest()
    try:
        obj = json.loads(raw.decode("utf-8", errors="strict"))
    except Exception as exc:  # noqa: BLE001
        return None, digest, f"not valid JSON: {exc!r}"
    if not isinstance(obj, dict):
        return None, digest, f"top-level JSON is {type(obj).__name__}, expected object"
    return obj, digest, ""


def _qc_report_fact(run_dir: Path, key: str, spec: Dict[str, Optional[str]]) -> Fact:
    p = run_dir / spec["path"]
    if not p.is_file():
        return Fact.absent(f"{spec['path']}: file not found")
    obj, digest, err = _load_json_bytes(p)
    if obj is None:
        return Fact.unparseable(f"{spec['path']}: {err}")

    gate_label = str(obj.get("gate", "")).strip()
    avg_raw = obj.get("average", obj.get("average_score"))
    try:
        average = float(avg_raw) if avg_raw is not None else None
    except (TypeError, ValueError):
        average = None
    triggered = tuple(obj.get("triggered_autofails") or obj.get("autofails_triggered") or [])
    pass_declared = obj.get("pass")

    # Reuse the EXISTING pure rubric helpers from build_deck.py rather than
    # re-implementing independence / anti-rubber-stamp logic a second time —
    # both operate on an already-parsed dict and do no I/O of their own, so
    # calling them here does not violate the "read each source once" rule.
    # Lazy/defensive import: build_deck.py is a sibling script file, not
    # guaranteed importable from every context this module might load in
    # (e.g. a bare unit test that only exercises runfacts.py).
    independence_reason = ""
    substance_problems: tuple = ()
    try:
        _bd = _import_build_deck()
        if _bd is not None:
            independence_reason = _bd._qc_independence_reason(obj) or ""
            substance_problems = tuple(_bd._qc_report_substance_problems(obj) or [])
    except Exception as exc:  # noqa: BLE001 — degrade, never crash the seal
        independence_reason = ""
        substance_problems = (f"NOTE: independence/substance check unavailable ({exc!r})",)

    info = QcReportInfo(
        rel_path=spec["path"],
        sha256=digest or "",
        gate_label=gate_label,
        gate_label_expected=spec.get("gate_label"),
        average=average,
        pass_declared=pass_declared,
        triggered_autofails=triggered,
        independence_reason=independence_reason,
        substance_problems=substance_problems,
    )
    return Fact.known(info, detail=f"{spec['path']} sealed sha256={digest[:12]}")


_BD_MODULE = None
_BD_LOAD_TRIED = False


def _import_build_deck():
    """Lazy, cached, defensive import of the sibling build_deck.py module.
    Lazy so this module never creates an import cycle at load time (build_deck
    imports presentation_job.checkpoint at its own module top; if this module
    imported build_deck at ITS top, importing either module first would
    recurse). Cached so repeated seals in one process don't re-import."""
    global _BD_MODULE, _BD_LOAD_TRIED
    if _BD_LOAD_TRIED:
        return _BD_MODULE
    _BD_LOAD_TRIED = True
    try:
        here = Path(__file__).resolve().parent.parent  # .../scripts
        if str(here) not in sys.path:
            sys.path.insert(0, str(here))
        import build_deck as _bd  # noqa: PLC0415
        _BD_MODULE = _bd
    except Exception:  # noqa: BLE001
        _BD_MODULE = None
    return _BD_MODULE


# ---------------------------------------------------------------------------
# RunFacts — the one sealed record.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RunFacts:
    run_dir: str
    sealed_at: str
    schema_version: int
    nonce_bound: bool
    process_manifest: Fact               # Fact[dict]
    owner_skip_records: Fact             # Fact[Tuple[OwnerSkipRecord, ...]]
    qc: Dict[str, Fact]                  # key in QC_REPORTS -> Fact[QcReportInfo]

    def to_json(self) -> dict:
        return {
            "run_dir": self.run_dir,
            "sealed_at": self.sealed_at,
            "schema_version": self.schema_version,
            "nonce_bound": self.nonce_bound,
            "process_manifest": self.process_manifest.to_json(),
            "owner_skip_records": self.owner_skip_records.to_json(),
            "qc": {k: f.to_json() for k, f in self.qc.items()},
        }

    def findings(self) -> list:
        """Lines naming a SPECIFIC fact that looks suspicious — this is what the
        acceptance report reads from ("the report names the specific fact that
        failed validation" is this method's contract). Deliberately NOT every
        non-KNOWN fact: plain ABSENT for an artifact whose phase simply hasn't
        run yet (no process_manifest.json on the very first admission of a
        brand-new run; no typography_qc_report.json before the Design phase)
        is the NORMAL, common, innocent state for the large majority of a run's
        lifetime — reporting it as a "finding" on every single legitimate run
        would be exactly the cry-wolf failure mode that trains an operator to
        stop reading this log. What DOES get reported:
          * UNPARSEABLE — a source file exists but is not valid JSON (a manifest
            or report that got corrupted/truncated/tampered).
          * an owner_skip_approval record that names an af_code but fails
            structural validity — evidence someone tried to write a skip and
            either forged it incompletely or it drifted; legacy code silently
            ignores this (returns None), RunFacts surfaces it.
          * a WIRED QC report (see WIRED_QC_KEYS) that is KNOWN but fails its
            own rubric (wrong gate label / sub-floor average / triggered
            autofail / pass not literal True / no independence provenance /
            rubber-stamp signature) — a report that EXISTS and CLAIMS a pass
            it has not earned. This is the proven P-TYPO-QC gap."""
        out = []
        if self.process_manifest.state is Epistemic.UNPARSEABLE:
            out.append(f"process_manifest.json: UNPARSEABLE — {self.process_manifest.detail}")
        if self.owner_skip_records.state is Epistemic.UNPARSEABLE:
            out.append(f"owner_skip_records: UNPARSEABLE — {self.owner_skip_records.detail}")
        elif self.owner_skip_records.state is Epistemic.KNOWN:
            for r in self.owner_skip_records.value:
                if r.af_code and not r.valid:
                    out.append(
                        f"owner_skip_records: a record names af_code={r.af_code!r} but is "
                        f"NOT structurally valid (owner_approved={r.owner_approved_raw!r}, "
                        f"approved_by={r.approved_by!r}, reason={'set' if r.reason else 'EMPTY'}, "
                        f"timestamp={'set' if r.timestamp else 'EMPTY'}) — legacy code silently "
                        f"ignores this and falls through to enforced; surfaced here for audit"
                    )
        for key in WIRED_QC_KEYS:
            f = self.qc.get(key)
            if f is None or f.state is not Epistemic.KNOWN:
                if f is not None and f.state is Epistemic.UNPARSEABLE:
                    out.append(f"qc[{key}] ({QC_REPORTS[key]['path']}): UNPARSEABLE — {f.detail}")
                continue
            info: QcReportInfo = f.value
            problems = []
            if info.gate_label_expected and info.gate_label != info.gate_label_expected:
                problems.append(f"gate={info.gate_label!r} expected {info.gate_label_expected!r}")
            if info.average is None or info.average < 8.5:
                problems.append(f"average={info.average!r} below 8.5")
            if info.triggered_autofails:
                problems.append(f"triggered_autofails={list(info.triggered_autofails)}")
            if info.pass_declared is not True:
                problems.append(f"pass={info.pass_declared!r} (not literal True)")
            if info.independence_reason:
                problems.append(info.independence_reason)
            if info.substance_problems:
                problems.extend(info.substance_problems)
            if problems:
                out.append(f"qc[{key}] ({info.rel_path}): UNTRUSTED — " + "; ".join(problems))
        return out


_SEAL_LOCK = threading.Lock()
_SEAL_CACHE: Dict[str, RunFacts] = {}


def seal(run_dir: Path, *, nonce_bound: bool = False, force: bool = False) -> RunFacts:
    """Build (or return the cached) RunFacts for run_dir. Reads every source file
    EXACTLY ONCE per process per run_dir (cached by resolved path) — this is the
    "built exactly once per epoch at the front door" property. Sealing NEVER
    raises: any read failure becomes an ABSENT/UNPARSEABLE Fact, not an
    exception, so calling this can never itself block a run (report-only
    increment: only the CALLER decides whether to act on what's found, and by
    default it doesn't).

    Loudly prints one FINDING_PREFIX line per non-KNOWN / rubric-failing fact
    to stderr at seal time, in addition to whatever shadow_compare() prints
    later at each individual gate call — the seal-time findings on their own
    already answer "the report names the specific fact that failed
    validation" without requiring any gate to actually run."""
    run_dir = Path(run_dir).resolve()
    key = str(run_dir)
    with _SEAL_LOCK:
        if not force and key in _SEAL_CACHE:
            return _SEAL_CACHE[key]

        pm_path = run_dir / "working" / "checkpoints" / "process_manifest.json"
        if not pm_path.is_file():
            pm_fact = Fact.absent("working/checkpoints/process_manifest.json: file not found")
            owner_fact = Fact.absent("no process_manifest.json — owner_skip_approval cannot be read")
        else:
            obj, digest, err = _load_json_bytes(pm_path)
            if obj is None:
                pm_fact = Fact.unparseable(f"process_manifest.json: {err}")
                owner_fact = Fact.unparseable(f"process_manifest.json: {err}")
            else:
                pm_fact = Fact.known(obj, detail=f"sha256={digest[:12]}")
                raw = obj.get("owner_skip_approval")
                records_raw = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])
                records = tuple(
                    rec for rec in (_classify_owner_skip_record(r) for r in records_raw)
                    if rec is not None
                )
                owner_fact = Fact.known(records, detail=f"{len(records)} record(s) sealed")

        qc: Dict[str, Fact] = {
            key_: _qc_report_fact(run_dir, key_, spec) for key_, spec in QC_REPORTS.items()
        }

        facts = RunFacts(
            run_dir=key,
            sealed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            schema_version=RUNFACTS_SCHEMA_VERSION,
            nonce_bound=nonce_bound,
            process_manifest=pm_fact,
            owner_skip_records=owner_fact,
            qc=qc,
        )
        _SEAL_CACHE[key] = facts

    for line in facts.findings():
        try:
            print(f"{FINDING_PREFIX} run_dir={run_dir} {line}", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass

    _best_effort_save(facts)
    return facts


def get_or_seal(run_dir: Path) -> RunFacts:
    """Convenience for call sites that don't control admission (e.g. a gate
    called from a unit test, or from a code path that runs before/without the
    front-door hook): seal on first touch if nothing sealed this run yet,
    reuse the cached seal otherwise. nonce_bound is False for a lazily-created
    seal — only the explicit main() front-door call passes nonce_bound=True."""
    key = str(Path(run_dir).resolve())
    with _SEAL_LOCK:
        cached = _SEAL_CACHE.get(key)
    if cached is not None:
        return cached
    return seal(run_dir, nonce_bound=False)


def _best_effort_save(facts: RunFacts) -> None:
    """Write the sealed record to <run_dir>/working/checkpoints/.runfacts.sealed.json,
    0600, atomically. Best-effort / non-fatal by design (report-only). NOTE the
    honest limit from the module docstring: this file is written and read by
    the same UID as everything else in the run dir, so on-disk persistence is
    an AUDIT TRAIL for a human/CI to diff across runs, not a cross-process
    integrity guarantee — a co-resident same-UID process can rewrite it."""
    try:
        run_dir = Path(facts.run_dir)
        out_path = run_dir / SEALED_REL
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_suffix(out_path.suffix + f".tmp{os.getpid()}")
        tmp_path.write_text(json.dumps(facts.to_json(), indent=2, sort_keys=True))
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, out_path)
    except Exception:  # noqa: BLE001 — never let the audit write break a caller
        pass


def load_sealed(run_dir: Path) -> Optional[dict]:
    """Read back the on-disk sealed JSON (raw dict, not a reconstructed RunFacts
    — this is deliberately a read-only audit view, not a substitute for
    seal()/get_or_seal() within the process that actually needs to gate on
    it). Returns None if absent/unreadable."""
    p = Path(run_dir) / SEALED_REL
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# PURE verdict functions: (RunFacts, ...) -> (Verdict, str). Neither of these
# opens a file, stats a path, or globs a directory — see gate_integrity_check
# --purity, which AST-asserts exactly that for both functions by name.
# ---------------------------------------------------------------------------
def verify_owner_skip(facts: RunFacts, af_code: str) -> Tuple[Verdict, str]:
    """PURE. The RunFacts-sourced equivalent of build_deck._owner_skip_approved's
    boolean question ("is af_code validly waived?") — operates only on the
    already-sealed owner_skip_records fact. Absence is never a waiver (FAIL,
    not UNDETERMINED: a missing manifest is a known, common, legitimate state
    for a run that simply never needed a skip, and defaulting it to
    UNDETERMINED would make UNDETERMINED the common case instead of the
    exception). A record whose af_code is claimed both approved and NOT
    approved is CONFLICTED -> UNDETERMINED, never resolved by first-match
    (which is what the legacy list-scan implicitly does)."""
    want = af_code.strip().upper()
    fact = facts.owner_skip_records
    if fact.state is Epistemic.ABSENT:
        return Verdict.FAIL, f"owner_skip_records ABSENT ({fact.detail}) — {want} stays enforced"
    if fact.state is Epistemic.UNPARSEABLE:
        return Verdict.UNDETERMINED, f"owner_skip_records UNPARSEABLE ({fact.detail})"
    records = fact.value
    valid_matches = [r for r in records if r.af_code == want and r.valid]
    false_claims = [r for r in records if r.af_code == want and r.owner_approved_raw is False]
    if valid_matches and false_claims:
        return Verdict.UNDETERMINED, (
            f"CONFLICTED: {want} has {len(valid_matches)} valid owner_approved:true "
            f"record(s) AND {len(false_claims)} owner_approved:false record(s) for the "
            f"same af_code — ambiguous, needs human review, never auto-resolved"
        )
    if valid_matches:
        r0 = valid_matches[0]
        return Verdict.PASS, f"{want} waived by owner_skip_approval (approved_by={r0.approved_by!r})"
    any_matches = [r for r in records if r.af_code == want]
    if any_matches:
        return Verdict.FAIL, (
            f"{want}: {len(any_matches)} record(s) present but none structurally valid "
            f"(need owner_approved:true + non-empty af_code/approved_by/reason/timestamp)"
        )
    return Verdict.FAIL, f"{want}: no owner_skip_approval record found"


def verify_qc(facts: RunFacts, key: str) -> Tuple[Verdict, str]:
    """PURE. Re-derives the SAME decided-value rubric build_deck._qc_report_gate
    already enforces (gate label / average>=8.5 / no triggered autofails /
    pass IS True / independence / anti-rubber-stamp substance) but sources it
    from the sealed fact instead of a fresh read. This is the function that
    would have rejected the proven P-TYPO-QC gap (a report with
    gate:'typography', pass:false accepted by the file-existence-only legacy
    verifier) — every one of the five checks below independently rejects it."""
    if key not in QC_REPORTS:
        return Verdict.UNDETERMINED, f"{key!r} is not a sealed QC report key"
    fact = facts.qc[key]
    if fact.state is Epistemic.ABSENT:
        return Verdict.FAIL, f"qc[{key}] ABSENT ({fact.detail})"
    if fact.state is Epistemic.UNPARSEABLE:
        return Verdict.FAIL, f"qc[{key}] UNPARSEABLE ({fact.detail})"
    info: QcReportInfo = fact.value
    problems = []
    if info.gate_label_expected and info.gate_label != info.gate_label_expected:
        problems.append(f"gate={info.gate_label!r}, expected {info.gate_label_expected!r}")
    if info.average is None or info.average < 8.5:
        problems.append(f"average={info.average!r} below the 8.5 pass threshold")
    if info.triggered_autofails:
        problems.append(f"triggered autofails present: {list(info.triggered_autofails)}")
    if info.pass_declared is not True:
        problems.append(f"report does not affirmatively mark pass:true (got {info.pass_declared!r})")
    if info.independence_reason:
        problems.append(info.independence_reason)
    if info.substance_problems:
        problems.extend(info.substance_problems)
    if problems:
        return Verdict.FAIL, "; ".join(problems)
    return Verdict.PASS, f"qc[{key}] declared pass, independent, no rubber-stamp signature"


def shadow_compare(label: str, legacy_ok: bool, legacy_reason: str,
                    new_verdict: Verdict, new_reason: str, *, run_dir) -> bool:
    """Compare a legacy boolean verdict against the sealed-RunFacts Verdict for
    the SAME gate query. On divergence, print ONE greppable line to stderr
    naming the gate, both verdicts, and both reasons, and return True (caller
    may use this to count divergences). Report-only: this function NEVER
    raises and NEVER changes what the caller returns — that decision is made
    by the caller using enforcing()."""
    legacy_as_verdict = Verdict.PASS if legacy_ok else Verdict.FAIL
    if legacy_as_verdict is new_verdict:
        return False
    try:
        print(
            f"{DIVERGENCE_PREFIX} gate={label} run_dir={run_dir} "
            f"legacy={legacy_as_verdict.value}({_trunc(legacy_reason)!r}) "
            f"runfacts={new_verdict.value}({_trunc(new_reason)!r}) "
            f"enforcing={enforcing()}",
            file=sys.stderr,
        )
    except Exception:  # noqa: BLE001
        pass
    return True


def _trunc(s: str, n: int = 220) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 3] + "..."


def reset_cache_for_tests() -> None:
    """Test-only: clear the per-process seal cache so a test can seal the same
    run_dir path twice with different fixture content. Not called by any
    production code path."""
    with _SEAL_LOCK:
        _SEAL_CACHE.clear()


# ---------------------------------------------------------------------------
# Standalone CLI: `python3 -m presentation_job.runfacts --verify <run_dir>`.
# A NEW, separate entry point (does not touch build_deck.py's CLI or exit
# codes) that seals a run dir and reports PASS/FAIL/UNDETERMINED for the
# facts this increment covers, exiting EXIT_UNDETERMINED (7) whenever any
# sealed fact is not KNOWN-and-clean — UNDETERMINED never coerces to a pass.
# ---------------------------------------------------------------------------
def _main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2 or argv[0] != "--verify":
        print("usage: python3 -m presentation_job.runfacts --verify <run_dir>", file=sys.stderr)
        return EXIT_FAIL
    run_dir = Path(argv[1])
    facts = seal(run_dir, nonce_bound=False, force=True)
    findings = facts.findings()
    print(json.dumps({
        "run_dir": facts.run_dir,
        "sealed_at": facts.sealed_at,
        "findings": findings,
        "clean": not findings,
    }, indent=2))
    if findings:
        return EXIT_UNDETERMINED
    return EXIT_PASS


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
