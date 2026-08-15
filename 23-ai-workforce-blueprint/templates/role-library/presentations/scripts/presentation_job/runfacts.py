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
import re
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
    # P-QC-AGGREGATE (order 8.65) — the FINAL aggregate produced by
    # qc_aggregate.py (scripts/qc_aggregate.py), consumed by gates.py's
    # fail-closed _qc_gate. Slice-2 conversion adds it to the sealed set so
    # the aggregate verifier re-measures it from the seal. Deliberately NOT
    # added to WIRED_QC_KEYS: the aggregate's shape is not a 0-10 rubric
    # report (no independence block, `average` null on any blocking finding),
    # so RunFacts.findings()'s WIRED rubric must not shout about it before
    # the aggregate verifier exists to judge it properly.
    "final":          {"path": "working/qc/final_qc_report.json",       "gate_label": None},
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
    schema: str                 # the report's declared "schema" ("" when absent)
    items: tuple = ()           # raw ledger rows for ledger-shaped reports (priority_shift / final)


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

    schema = str(obj.get("schema", "") or "").strip()
    raw_items = obj.get("items")
    items = tuple(raw_items) if isinstance(raw_items, list) else ()

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
        schema=schema,
        items=items,
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
    # --- SLICE 3 (composite / multi-artifact gates) ---
    deliverables: Fact                    # Fact[Tuple[DeliverableInfo, ...]] — P9-DELIVER bundle (10 keys)
    media_library: Fact                  # Fact[MediaLibraryInfo] — P9.2-GHL-UPLOAD ledger
    workbook: Fact                       # Fact[WorkbookInfo] — P8.25-WORKBOOK dual-PDF
    webinar_video: Fact                  # Fact[WebinarVideoInfo] — P9.6-WEBINAR-VIDEO video+timing
    notes_sync: Fact                     # Fact[NotesSyncInfo] — P9.5-NOTES-SYNC record+pptx
    fish_tag: Fact                       # Fact[FishTagInfo] — P8.4-FISH-TAG dual-file strip-equals

    def to_json(self) -> dict:
        return {
            "run_dir": self.run_dir,
            "sealed_at": self.sealed_at,
            "schema_version": self.schema_version,
            "nonce_bound": self.nonce_bound,
            "process_manifest": self.process_manifest.to_json(),
            "owner_skip_records": self.owner_skip_records.to_json(),
            "qc": {k: f.to_json() for k, f in self.qc.items()},
            "deliverables": self.deliverables.to_json(),
            "media_library": self.media_library.to_json(),
            "workbook": self.workbook.to_json(),
            "webinar_video": self.webinar_video.to_json(),
            "notes_sync": self.notes_sync.to_json(),
            "fish_tag": self.fish_tag.to_json(),
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
            deliverables=_deliverables_fact(run_dir),
            media_library=_media_library_fact(run_dir),
            workbook=_workbook_fact(run_dir),
            webinar_video=_webinar_video_fact(run_dir),
            notes_sync=_notes_sync_fact(run_dir),
            fish_tag=_fish_tag_fact(run_dir),
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


def verify_priority_shift(facts: RunFacts) -> Tuple[Verdict, str]:
    """PURE. SLICE-2: P-SHIFT-QC (order 7.5). Re-derives the priority-shift ship
    gate's decided value from the SEALED ledger fact instead of a fresh read —
    the ledger (working/qc/priority_shift_report.json, written by
    build_deck._chk_priority_shift_ledger from its own 14-item + per-slide
    measurements) is the REAL artifact; the legacy phase verifier only proved
    the file existed. The verdict re-derives the exact contract the ledger's
    writer enforces: schema matches, pass is literal True, and every ledger
    item row is structurally pass:true. A ledger whose rows contradict its
    pass flag is a rubber stamp and is REJECTED naming the failing rows."""
    fact = facts.qc["priority_shift"]
    if fact.state is Epistemic.ABSENT:
        return Verdict.FAIL, f"qc[priority_shift] ABSENT ({fact.detail})"
    if fact.state is Epistemic.UNPARSEABLE:
        return Verdict.FAIL, f"qc[priority_shift] UNPARSEABLE ({fact.detail})"
    info: QcReportInfo = fact.value
    problems = []
    if info.schema != "priority_shift_report/v1":
        problems.append(f"schema={info.schema!r}, expected 'priority_shift_report/v1'")
    if info.pass_declared is not True:
        problems.append(f"report does not affirmatively mark pass:true (got {info.pass_declared!r})")
    if not info.items:
        problems.append("ledger carries no item rows — the 14-item ship checklist is empty")
    else:
        failed = [str(r.get("item") or r.get("id") or f"row#{i}")
                  for i, r in enumerate(info.items)
                  if isinstance(r, dict) and r.get("pass") is not True]
        if failed:
            problems.append("ledger items failing (contradict the pass flag): "
                            + ", ".join(failed[:5]))
    if problems:
        return Verdict.FAIL, "; ".join(problems)
    return Verdict.PASS, ("qc[priority_shift] ledger declares pass with all "
                          f"{len(info.items)} item rows passing")


def verify_final_qc(facts: RunFacts) -> Tuple[Verdict, str]:
    """PURE. SLICE-2: P-QC-AGGREGATE (order 8.65). Re-derives the FINAL aggregate
    verdict from the SEALED six-domain facts + the sealed aggregate report —
    the same six sources qc_aggregate.py (the real producer) reads, exactly
    once, at seal time. This is the re-measure the task demands: the verifier
    never trusts the aggregate's headline alone; it independently confirms
    every one of the six domain facts it claims to aggregate is KNOWN and
    passing under the SAME rubric the per-domain gates enforce (verify_qc).
    The aggregate's own `average` must be a numeric >= 8.5 (a blocked
    aggregate writes average:null on purpose — that is a FAIL naming it)."""
    agg_fact = facts.qc["final"]
    if agg_fact.state is Epistemic.ABSENT:
        return Verdict.FAIL, f"qc[final] ABSENT ({agg_fact.detail})"
    if agg_fact.state is Epistemic.UNPARSEABLE:
        return Verdict.FAIL, f"qc[final] UNPARSEABLE ({agg_fact.detail})"
    info: QcReportInfo = agg_fact.value
    problems = []
    if info.schema != "final_qc_report/v1":
        problems.append(f"schema={info.schema!r}, expected 'final_qc_report/v1'")
    if info.pass_declared is not True:
        problems.append(f"report does not affirmatively mark pass:true (got {info.pass_declared!r})")
    if info.average is None:
        problems.append("average is null — the aggregate carries no numeric score "
                        "(qc_aggregate writes average:null on ANY blocking finding)")
    elif info.average < 8.5:
        problems.append(f"average={info.average!r} below the 8.5 pass threshold")
    if info.triggered_autofails:
        problems.append(f"triggered autofails present: {list(info.triggered_autofails)}")
    for key in ("copy", "prompt", "image", "typography", "speech"):
        dverdict, ddetail = verify_qc(facts, key)
        if dverdict is not Verdict.PASS:
            problems.append(f"domain qc[{key}] does not pass: {ddetail}")
    ps = facts.qc["priority_shift"]
    if ps.state is not Epistemic.KNOWN:
        problems.append("domain qc[priority_shift] absent/unreadable — the ship gate "
                        "must be present and passing for the aggregate to pass")
    else:
        pverdict, pdetail = verify_priority_shift(facts)
        if pverdict is not Verdict.PASS:
            problems.append(f"domain qc[priority_shift] does not pass: {pdetail}")
    if problems:
        return Verdict.FAIL, "; ".join(problems)
    return Verdict.PASS, ("qc[final] aggregate declares pass, average "
                          f"{info.average}, all six domain facts independently passing")
# ---------------------------------------------------------------------------
# SLICE 3 — composite / multi-artifact / deferred-when-None gates. Each of
# these gates judges MORE than one artifact (a 10-key deliverable bundle, a
# JSON ledger, a dual-PDF pair, a video + its timing track, a sync record +
# the PPTX it mutated). The fact layer seals every artifact the gate must
# re-measure — each read exactly once at seal time, stored with its epistemic
# state — and the verdict functions below are PURE: they open nothing, they
# decide only over what the seal recorded. Absence of any required artifact is
# FAIL, never UNDETERMINED and never a pass (D10: "a check that defers because
# its input is missing is a fail-open wearing a fail-closed label").
#
# Everything the legacy phase verifiers (phase_verifiers.py) did at call time —
# globbing delivery dirs, opening PDFs with pypdf, probing mp4 ftyp boxes,
# python-pptx notes panes — happens here exactly once, at seal() time. The
# verdict functions mirror the legacy rubric decision-for-decision.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeliverableInfo:
    """One deliverable key's sealed measurement (P9-DELIVER bundle check).

    Mirrors the legacy _verify_delivery rubric (phase_verifiers._DELIVERY_DELIVERABLES,
    sourced from presentation_job.deliverables.DELIVERABLE_AUDIT_SPEC):
    existence, size, min_bytes floor, magic-bytes signature at the canonical
    offset, and the content-substance probe for the keys that have no magic
    (speech_fish_md -> fish-tag count, teleprompter_html -> HTML structure,
    webinar_mp4 -> ftyp/moov)."""

    key: str
    found: bool                     # a file matching the key's pattern existed
    path: str                       # resolved candidate path ("" if not found)
    size: int
    min_bytes: int
    magic_ok: Optional[bool]        # None = no magic check for this key
    magic_problem: str              # "" = magic OK / not checked
    content_problem: str            # "" = content probe OK / not checked


@dataclass(frozen=True)
class MediaLibraryInfo:
    """Sealed P9.2-GHL-UPLOAD local ledger (working/checkpoints/media_library.json).

    The ledger is the artifact this gate re-measures. The READ-ONLY GHL list-back
    is a network call and deliberately stays in the legacy verifier (NOTE-degrades
    when the LOCATION PIT / env does not resolve) — it cannot be a sealed fact
    because seal() never touches the network; the ledger's recorded ids are what
    the list-back proves against, so sealing them is exactly what the verdict
    needs."""

    folder_id: str
    pptx_media_id: str              # pptx_ghl_media_id or pptx_ghl_url fallback
    pptx_remote_name: str
    slide_uploads_complete: int
    slide_uploads_total: int


@dataclass(frozen=True)
class WorkbookInfo:
    """Sealed P8.25-WORKBOOK dual-PDF measurement (AF-WORKBOOK-BOTH).

    The regular workbook must be image-only (zero AcroForm fields), the fillable
    must carry fields + /NeedAppearances, both must exist with >= 2048 bytes and
    at least one page. pypdf absence NOTE-degrades exactly like the legacy
    verifier (existence+size only, pass with a note)."""

    regular_found: bool
    regular_path: str
    fillable_found: bool
    fillable_path: str
    regular_pages: int              # -1 when pypdf could not read it
    regular_fields: int
    fillable_pages: int
    fillable_fields: int
    fillable_need_appearances: bool
    pypdf_available: bool           # False -> verdict must degrade, never false-fail
    too_small: tuple                 # tuple[str] — names of workbook PDFs under 2048 bytes


@dataclass(frozen=True)
class WebinarVideoInfo:
    """Sealed P9.6-WEBINAR-VIDEO measurement (video + timing track)."""

    video_found: bool
    video_path: str
    video_size: int
    ftyp_ok: bool                    # 'ftyp' box present at offset 4
    moov_ok: bool                    # 'moov' atom in first 256 KiB (when size >= 8192)
    timing_parseable: bool
    timing_count: int
    timing_contiguous: bool          # slides 1..N in order
    timing_durations_ok: bool        # every duration is a number > 0
    timing_problem: str              # "" when the track is fully OK


@dataclass(frozen=True)
class FishTagInfo:
    """Sealed P8.4-FISH-TAG dual-file measurement (AF-FISH-TAG).

    The tagged speech must be the source speech with [fish] expression tags
    (and parens) inserted — the strip-equals prover removes every bracket/paren
    span and whitespace from BOTH files and requires the stripped texts to be
    identical. Both texts are sealed raw; the verdict does the pure strip
    comparison (mirrors phase_verifiers._verify_fish_tag's rubric)."""

    tagged_found: bool
    source_found: bool
    tagged_path: str
    source_path: str
    tagged_size: int
    source_size: int
    tagged_text: str                 # "" when unreadable
    source_text: str                 # "" when unreadable


@dataclass(frozen=True)
class NotesSyncInfo:
    """Sealed P9.5-NOTES-SYNC measurement (notes_sync.json + the PPTX it mutated).

    The bundle PPTX's empty-notes-pane scan runs through build_deck._chk_notes_pane
    at seal time (the single source of the AF-EMPTY-NOTES-PANE rubric) — same call
    the legacy verifier makes, one time, on the sealed snapshot instead of at
    every gate invocation."""

    status: str                      # "synced" | "no_speech" | "error" | "" (absent)
    reason: str
    slides_total: int
    slides_with_notes: int
    speech_source: str
    bundle_pptx: str                 # recorded bundle_pptx path ("" if absent)
    notes_pane_result: str           # "" = no empty notes panes; else AF-EMPTY-NOTES-PANE finding


@dataclass(frozen=True)
class FishTagInfo:
    """Sealed P8.4-FISH-TAG dual-file measurement (AF-FISH-TAG).

    The tagged speech must be the source speech with [fish] expression tags
    (and parens) inserted — the strip-equals prover removes every bracket/paren
    span and whitespace from BOTH files and requires the stripped texts to be
    identical. Both texts are sealed raw; the verdict does the pure strip
    comparison (mirrors phase_verifiers._verify_fish_tag's rubric)."""

    tagged_found: bool
    source_found: bool
    tagged_path: str
    source_path: str
    tagged_size: int
    source_size: int
    tagged_text: str                 # "" when unreadable
    source_text: str                 # "" when unreadable


# ---------------------------------------------------------------------------
# Seal-time readers for the slice-3 facts. Each reads its source EXACTLY ONCE
# per seal. None of these may ever raise into seal().
# ---------------------------------------------------------------------------

def _deliverables_fact(run_dir: Path) -> Fact:
    """Seal the P9-DELIVER bundle: every DELIVERABLE_AUDIT_SPEC key, measured.
    Uses the canonical spec's min_bytes / magic_bytes / magic_offset, and the
    same per-key pre-curation globs the legacy phase verifier uses
    (phase_verifiers._DELIVERY_PATTERN_BY_KEY / _DELIVERY_CONTENT_CHECK_BY_KEY).
    The content-substance probes mirror _deliverable_content_check: fish tags
    for speech_fish_md, HTML structure for teleprompter_html, ftyp/moov for
    webinar_mp4."""
    try:
        from presentation_job.deliverables import DELIVERABLE_AUDIT_SPEC as _DAS
    except Exception:  # noqa: BLE001 — the spec module must exist (U05); degrade loudly
        return Fact.untrusted(
            "presentation_job.deliverables.DELIVERABLE_AUDIT_SPEC could not be "
            "imported — the P9-DELIVER bundle cannot be measured. This is a "
            "module-level packaging break, not a run-dir state.")

    # Pre-curation glob per key — mirrors phase_verifiers._DELIVERY_PATTERN_BY_KEY.
    _pattern = {
        "deck_pptx":         "working/delivery/*-FINAL.pptx",
        "deck_pdf":          "working/delivery/*-FINAL.pdf",
        "guide_pdf":         "working/deliverables/PRESENTER-GUIDE.pdf",
        "speech_md":         "working/deliverables/PRESENTERS-SPEECH.md",
        "speech_pdf":        "working/deliverables/PRESENTERS-SPEECH.pdf",
        "speech_fish_md":    "working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md",
        "audio_mp3":         "working/delivery/PRESENTER-AUDIO.mp3",
        "infographic_png":   "working/delivery/infographic.png",
        "teleprompter_html": "working/deliverables/presenter-teleprompter.html",
        "webinar_mp4":       "working/delivery/*-WEBINAR.mp4",
    }

    infos = []
    for spec in _DAS:
        key = spec["key"]
        pattern = _pattern.get(key) or spec.get("filename_template")
        hits = sorted(run_dir.glob(pattern)) if pattern else []
        if not hits:
            infos.append(DeliverableInfo(
                key=key, found=False, path="", size=0,
                min_bytes=int(spec["min_bytes"]), magic_ok=None,
                magic_problem="", content_problem=""))
            continue
        p = hits[0]
        try:
            size = p.stat().st_size
        except OSError as exc:  # noqa: BLE001
            infos.append(DeliverableInfo(
                key=key, found=False, path="", size=0,
                min_bytes=int(spec["min_bytes"]), magic_ok=None,
                magic_problem="", content_problem=f"unreadable: {exc!r}"))
            continue

        magic_ok: Optional[bool] = None
        magic_problem = ""
        magic = spec.get("magic_bytes")
        if magic is not None:
            try:
                with open(p, "rb") as fh:
                    fh.seek(int(spec.get("magic_offset") or 0))
                    head = fh.read(len(magic))
                magic_ok = head == magic
                if not magic_ok:
                    magic_problem = (f"expected {spec.get('magic_desc') or 'magic bytes'} "
                                     f"at offset {spec.get('magic_offset') or 0}, got {head!r}")
            except OSError as exc:  # noqa: BLE001
                magic_ok = False
                magic_problem = f"cannot read for magic check: {exc!r}"

        content_problem = ""
        if key == "speech_fish_md":
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                n = len(re.findall(r"\[fish\b[^\]]*\]", text, re.IGNORECASE))
                if n < 3:
                    content_problem = (f"only {n} [fish] tags (min 3 expected) — a renamed "
                                       f"plain text file is not a fish-tagged speech")
            except Exception as exc:  # noqa: BLE001
                content_problem = f"cannot read for fish-tag check: {exc!r}"
        elif key == "teleprompter_html":
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                if not re.search(r"<\s*html", text, re.IGNORECASE):
                    content_problem = "not HTML (no <html> tag found)"
                elif (not re.search(r"<\s*(?:div|section|article)", text, re.IGNORECASE)
                        and "slide" not in text.lower()):
                    content_problem = ("lacks slide structure (no <div>/<section> "
                                       "elements, no 'slide' text)")
            except Exception as exc:  # noqa: BLE001
                content_problem = f"cannot read for HTML check: {exc!r}"
        elif key == "webinar_mp4":
            try:
                with open(p, "rb") as fh:
                    head = fh.read(8)
                if len(head) < 8 or head[4:8] != b"ftyp":
                    content_problem = (f"not a valid MP4 (no 'ftyp' box at offset 4, "
                                       f"got {head[4:8]!r})")
                elif size >= 8192:
                    with open(p, "rb") as fh:
                        chunk = fh.read(262144)
                    if b"moov" not in chunk:
                        content_problem = ("has ftyp but no 'moov' atom in first "
                                           "256 KiB — a header-only stub is not a "
                                           "rendered video")
            except Exception as exc:  # noqa: BLE001
                content_problem = f"cannot read for video check: {exc!r}"

        infos.append(DeliverableInfo(
            key=key, found=True, path=str(p), size=size,
            min_bytes=int(spec["min_bytes"]), magic_ok=magic_ok,
            magic_problem=magic_problem, content_problem=content_problem))

    return Fact.known(tuple(infos),
                      detail=f"{len(infos)} deliverable keys sealed from DELIVERABLE_AUDIT_SPEC")


def _media_library_fact(run_dir: Path) -> Fact:
    """Seal the P9.2-GHL-UPLOAD local ledger (working/checkpoints/media_library.json)."""
    p = run_dir / "working" / "checkpoints" / "media_library.json"
    if not p.is_file():
        return Fact.absent("working/checkpoints/media_library.json: file not found")
    obj, digest, err = _load_json_bytes(p)
    if obj is None:
        return Fact.unparseable(f"working/checkpoints/media_library.json: {err}")
    slides = [e for e in (obj.get("slides") or []) if isinstance(e, dict)]
    complete = [e for e in slides
                if (e.get("ghl_media_id") or e.get("file_id"))
                and str(e.get("ghl_upload_status") or "").lower() == "complete"]
    info = MediaLibraryInfo(
        folder_id=str(obj.get("ghl_folder_id") or "").strip(),
        pptx_media_id=str(obj.get("pptx_ghl_media_id") or obj.get("pptx_ghl_url") or "").strip(),
        pptx_remote_name=str(obj.get("pptx_ghl_remote_name") or "").strip(),
        slide_uploads_complete=len(complete),
        slide_uploads_total=len(slides),
    )
    return Fact.known(info, detail=f"media_library.json sealed sha256={digest[:12]}")


def _workbook_fact(run_dir: Path) -> Fact:
    """Seal the P8.25-WORKBOOK dual-PDF measurement. pypdf is opened lazily and
    defensively — a box without pypdf records pypdf_available=False and the
    verdict degrades to existence+size, exactly like the legacy verifier."""
    dl = run_dir / "working" / "deliverables"
    regulars = sorted(dl.glob("*-WORKBOOK.pdf")) if dl.is_dir() else []
    fillables = sorted(dl.glob("*-WORKBOOK-FILLABLE.pdf")) if dl.is_dir() else []
    if not regulars and not fillables:
        return Fact.absent("no *-WORKBOOK.pdf / *-WORKBOOK-FILLABLE.pdf in working/deliverables")

    too_small = tuple(p.name for p in regulars + fillables
                      if p.stat().st_size < 2048)

    def _empty_workbook_info() -> WorkbookInfo:
        return WorkbookInfo(
            regular_found=False, regular_path="",
            fillable_found=False, fillable_path="",
            regular_pages=0, regular_fields=0,
            fillable_pages=0, fillable_fields=0,
            fillable_need_appearances=False,
            pypdf_available=False, too_small=too_small)

    info = WorkbookInfo(
        regular_found=bool(regulars),
        regular_path=str(regulars[0]) if regulars else "",
        fillable_found=bool(fillables),
        fillable_path=str(fillables[0]) if fillables else "",
        regular_pages=0, regular_fields=0,
        fillable_pages=0, fillable_fields=0,
        fillable_need_appearances=False,
        pypdf_available=False, too_small=too_small)
    if not regulars or not fillables:
        return Fact.known(info, detail="workbook dual-PDF: at least one side absent")

    try:
        from pypdf import PdfReader

        def _read(pdf: Path):
            r = PdfReader(str(pdf))
            fields = r.get_fields() or {}
            need_app = False
            try:
                need_app = bool(r.trailer["/Root"]["/AcroForm"]["/NeedAppearances"])
            except Exception:  # noqa: BLE001
                need_app = False
            return (len(r.pages), len(fields), need_app)

        reg_pages, reg_fields, _ = _read(regulars[0])
        fill_pages, fill_fields, need_app = _read(fillables[0])
        info = WorkbookInfo(
            regular_found=True, regular_path=str(regulars[0]),
            fillable_found=True, fillable_path=str(fillables[0]),
            regular_pages=reg_pages, regular_fields=reg_fields,
            fillable_pages=fill_pages, fillable_fields=fill_fields,
            fillable_need_appearances=need_app,
            pypdf_available=True, too_small=too_small)
        return Fact.known(info, detail="workbook dual-PDF sealed via pypdf")
    except ImportError:
        return Fact.known(info, detail="pypdf not importable — workbook fact degraded (existence+size only)")
    except Exception as exc:  # noqa: BLE001 — never let pypdf blow up the seal
        return Fact.known(info, detail=f"pypdf read failed ({exc!r}) — workbook fact degraded")


def _webinar_video_fact(run_dir: Path) -> Fact:
    """Seal the P9.6-WEBINAR-VIDEO measurement: the mp4 + its timing track."""
    delivery = run_dir / "working" / "delivery"
    candidates = sorted(delivery.glob("*-WEBINAR.mp4")) if delivery.is_dir() else []
    if not candidates:
        video_found, video_path, video_size, ftyp_ok, moov_ok = False, "", 0, False, False
    else:
        video_found, video_path = True, str(candidates[0])
        try:
            video_size = candidates[0].stat().st_size
        except OSError:
            video_size = 0
        ftyp_ok = False
        moov_ok = False
        try:
            with open(candidates[0], "rb") as fh:
                head = fh.read(8)
            ftyp_ok = len(head) >= 8 and head[4:8] == b"ftyp"
            if video_size >= 8192:
                with open(candidates[0], "rb") as fh:
                    chunk = fh.read(262144)
                moov_ok = b"moov" in chunk
        except Exception:  # noqa: BLE001
            ftyp_ok, moov_ok = False, False

    timing_parseable, timing_count, timing_contiguous = False, 0, False
    timing_durations_ok, timing_problem = False, ""
    timing_p = run_dir / "working" / "checkpoints" / "webinar_timing.json"
    obj, _, _ = _load_json_bytes(timing_p)
    timing = obj.get("timing") if isinstance(obj, dict) else None
    if not isinstance(timing, list) or not timing:
        timing_problem = "absent or has no timing[] entries"
    else:
        timing_parseable = True
        timing_count = len(timing)
        expected = 1
        contiguous = True
        durations_ok = True
        for i, entry in enumerate(timing):
            if not isinstance(entry, dict):
                timing_problem = f"timing[{i}] is not an object"
                contiguous = durations_ok = False
                break
            if entry.get("slide") != expected:
                timing_problem = (f"slides must be contiguous 1..N; got slide "
                                  f"{entry.get('slide')!r} at index {i} (expected {expected})")
                contiguous = False
                break
            dur = entry.get("duration")
            if not isinstance(dur, (int, float)) or dur <= 0:
                timing_problem = f"timing[{i}] duration must be > 0, got {dur!r}"
                durations_ok = False
                break
            expected += 1
        timing_contiguous, timing_durations_ok = contiguous, durations_ok

    info = WebinarVideoInfo(
        video_found=video_found, video_path=video_path, video_size=video_size,
        ftyp_ok=ftyp_ok, moov_ok=moov_ok,
        timing_parseable=timing_parseable, timing_count=timing_count,
        timing_contiguous=timing_contiguous,
        timing_durations_ok=timing_durations_ok, timing_problem=timing_problem)
    if not video_found and not timing_parseable:
        return Fact.absent("no *-WEBINAR.mp4 in working/delivery and no webinar_timing.json")
    return Fact.known(info, detail="webinar video + timing track sealed")


def _notes_sync_fact(run_dir: Path) -> Fact:
    """Seal the P9.5-NOTES-SYNC measurement: the sync record + the empty-notes-pane
    scan of the bundle PPTX it names (via build_deck._chk_notes_pane — the single
    source of the AF-EMPTY-NOTES-PANE rubric; same call the legacy verifier makes,
    made once at seal time)."""
    p = run_dir / "working" / "checkpoints" / "notes_sync.json"
    if not p.is_file():
        return Fact.absent("working/checkpoints/notes_sync.json: file not found")
    obj, digest, err = _load_json_bytes(p)
    if obj is None:
        return Fact.unparseable(f"working/checkpoints/notes_sync.json: {err}")
    status = str(obj.get("status") or "").strip()
    bundle_pptx = str(obj.get("bundle_pptx") or "").strip()
    notes_pane_result = ""
    if bundle_pptx:
        try:
            _bd = _import_build_deck()
            if _bd is not None and _bd._chk_notes_pane is not None:
                notes_pane_result = _bd._chk_notes_pane(
                    Path(bundle_pptx).parent, run_dir=run_dir, slides_path=None) or ""
            else:
                notes_pane_result = ""
        except Exception as exc:  # noqa: BLE001 — degrade, never crash the seal
            notes_pane_result = ""
    info = NotesSyncInfo(
        status=status,
        reason=str(obj.get("reason") or "").strip(),
        slides_total=int(obj.get("slides_total") or 0),
        slides_with_notes=int(obj.get("slides_with_notes") or 0),
        speech_source=str(obj.get("speech_source") or "").strip(),
        bundle_pptx=bundle_pptx,
        notes_pane_result=notes_pane_result)
    return Fact.known(info, detail=f"notes_sync.json sealed sha256={digest[:12]}")


def _fish_tag_fact(run_dir: Path) -> Fact:
    """Seal the P8.4-FISH-TAG dual-file measurement: both speech files' raw
    text, sizes, existence. The strip-equals comparison happens in the pure
    verdict; the seal only captures what both files actually contain."""
    tagged_p = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH-FISH-TAGGED.md"
    source_p = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH.md"
    if not tagged_p.exists() and not source_p.exists():
        return Fact.absent("PRESENTERS-SPEECH-FISH-TAGGED.md and PRESENTERS-SPEECH.md "
                           "not found in working/deliverables")
    tagged_found = tagged_p.exists()
    source_found = source_p.exists()
    tagged_text = ""
    source_text = ""
    if tagged_found:
        try:
            tagged_text = tagged_p.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            tagged_text = ""
    if source_found:
        try:
            source_text = source_p.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            source_text = ""
    info = FishTagInfo(
        tagged_found=tagged_found, source_found=source_found,
        tagged_path=str(tagged_p), source_path=str(source_p),
        tagged_size=tagged_p.stat().st_size if tagged_found else 0,
        source_size=source_p.stat().st_size if source_found else 0,
        tagged_text=tagged_text, source_text=source_text)
    return Fact.known(info, detail="fish-tag dual speech files sealed")


# ---------------------------------------------------------------------------
# SLICE 3 — pure verdict functions: (RunFacts, ...) -> (Verdict, str).
# Each mirrors the legacy phase-verifier rubric decision-for-decision, sourced
# from the sealed facts. None opens a file (see gate_integrity_check --purity).
# ---------------------------------------------------------------------------
def verify_deliverables(facts: RunFacts) -> Tuple[Verdict, str]:
    """PURE. P9-DELIVER verdict over the sealed 10-key bundle. Mirrors
    phase_verifiers._verify_delivery: every key must exist, meet its min_bytes
    floor, pass magic bytes (where the spec defines them) and the content probe
    (fish tags / HTML structure / ftyp+moov). A missing artifact is FAIL (D10),
    and every FAIL reason names the exact discrepancy."""
    fact = facts.deliverables
    if fact.state is not Epistemic.KNOWN:
        return Verdict.FAIL, f"deliverables {fact.state.value} ({fact.detail})"
    problems = []
    for d in fact.value:
        if not d.found:
            problems.append(f"{d.key}: no matching file found (min {d.min_bytes} bytes)")
            continue
        if d.size == 0:
            problems.append(f"{d.key}: {d.path} is zero bytes")
            continue
        if d.size < d.min_bytes:
            problems.append(f"{d.key}: {d.path} is {d.size} bytes (minimum {d.min_bytes} bytes)")
            continue
        if d.magic_ok is False:
            problems.append(f"{d.key}: {d.path} is not a valid file ({d.magic_problem})")
            continue
        if d.content_problem:
            problems.append(f"{d.key}: {d.content_problem}")
    if problems:
        return Verdict.FAIL, "; ".join(problems)
    return Verdict.PASS, f"all {len(fact.value)} deliverables verified (existence, size, magic, substance)"


def verify_media_library(facts: RunFacts) -> Tuple[Verdict, str]:
    """PURE. P9.2-GHL-UPLOAD verdict over the sealed local ledger. Mirrors the
    local half of phase_verifiers._verify_ghl_upload (the ledger checks BEFORE
    the network list-back). The list-back itself stays in the legacy verifier
    (network, NOTE-degrades) — this verdict re-measures the ledger: folder id
    resolved, every slide upload complete, pptx recorded in the library."""
    fact = facts.media_library
    if fact.state is Epistemic.ABSENT:
        # Legacy NOTE-degrades here (returns True + NOTE). D10: an absent input
        # does not pass; but this gate's whole point is the ledger — absent
        # means the upload phase did not run, which a fail-closed gate blocks.
        return Verdict.FAIL, f"media_library ABSENT ({fact.detail})"
    if fact.state is not Epistemic.KNOWN:
        return Verdict.FAIL, f"media_library {fact.state.value} ({fact.detail})"
    info: MediaLibraryInfo = fact.value
    problems = []
    if not info.folder_id:
        problems.append("ghl_folder_id is null or empty — the per-deck media folder was never resolved")
    if info.slide_uploads_complete == 0:
        problems.append("no per-slide upload carries a real ghl_media_id with status 'complete'")
    elif info.slide_uploads_complete != info.slide_uploads_total:
        problems.append(f"{info.slide_uploads_total - info.slide_uploads_complete} "
                        f"of {info.slide_uploads_total} slide uploads are incomplete")
    if not info.pptx_media_id:
        problems.append("pptx_ghl_media_id is absent — the assembled deck is not in the media library")
    if problems:
        return Verdict.FAIL, "; ".join(problems)
    return Verdict.PASS, (f"ledger clean: folder_id={info.folder_id[:24]}…, "
                          f"{info.slide_uploads_complete}/{info.slide_uploads_total} "
                          f"slide uploads complete, pptx_ghl_media_id recorded")


def verify_workbook(facts: RunFacts) -> Tuple[Verdict, str]:
    """PURE. P8.25-WORKBOOK verdict (AF-WORKBOOK-BOTH). Mirrors
    phase_verifiers._verify_workbook: both PDFs exist and exceed 2048 bytes,
    the regular is image-only (zero AcroForm fields), the fillable carries
    fields and /NeedAppearances. pypdf absence NOTE-degrades to existence+size
    (never a false fail on a genuine box)."""
    fact = facts.workbook
    if fact.state is not Epistemic.KNOWN:
        return Verdict.FAIL, f"workbook {fact.state.value} ({fact.detail})"
    info: WorkbookInfo = fact.value
    problems = []
    if info.too_small:
        problems.extend(f"workbook PDF {n} is only < 2048 bytes — too small" for n in info.too_small)
    if not info.regular_found:
        problems.append("regular workbook PDF (*-WORKBOOK.pdf) not found in working/deliverables")
    if not info.fillable_found:
        problems.append("fillable workbook PDF (*-WORKBOOK-FILLABLE.pdf) not found — "
                        "AF-WORKBOOK-BOTH requires BOTH deliverables")
    if problems:
        return Verdict.FAIL, "; ".join(problems)
    if not info.pypdf_available:
        return Verdict.PASS, "NOTE: pypdf not importable — workbook verdict degraded to existence+size check (pass)"
    if info.regular_pages < 1:
        problems.append(f"regular workbook {info.regular_path}: pypdf read {info.regular_pages} pages")
    if info.regular_fields != 0:
        problems.append(f"regular workbook {info.regular_path}: pypdf read {info.regular_fields} "
                        "AcroForm fields — the regular PDF must be image-only (no overlay)")
    if info.fillable_pages < 1:
        problems.append(f"fillable workbook {info.fillable_path}: pypdf read {info.fillable_pages} pages")
    if info.fillable_fields < 1:
        problems.append(f"fillable workbook {info.fillable_path}: pypdf read ZERO AcroForm "
                        "fields — the fillable form did not survive")
    if not info.fillable_need_appearances:
        problems.append(f"fillable workbook {info.fillable_path}: /NeedAppearances not set — "
                        "fields will not render in viewers")
    if problems:
        return Verdict.FAIL, "; ".join(problems)
    return Verdict.PASS, ("both workbook PDFs verified: regular image-only "
                          f"({info.regular_pages} pages), fillable with "
                          f"{info.fillable_fields} fields + /NeedAppearances")


def verify_webinar_video(facts: RunFacts) -> Tuple[Verdict, str]:
    """PURE. P9.6-WEBINAR-VIDEO verdict. Mirrors phase_verifiers._verify_webinar_video:
    mp4 exists, >= 4096 bytes, real ftyp box, timing track parseable and
    contiguous 1..N with positive durations. Absent video or absent timing
    track is FAIL (D10) — a phase attestation cannot pass without the video."""
    fact = facts.webinar_video
    if fact.state is not Epistemic.KNOWN:
        return Verdict.FAIL, f"webinar video {fact.state.value} ({fact.detail})"
    info: WebinarVideoInfo = fact.value
    problems = []
    if not info.video_found:
        problems.append("webinar video (*-WEBINAR.mp4) not found in working/delivery")
    elif info.video_size < 4096:
        problems.append(f"webinar video {info.video_path} is only {info.video_size} bytes — "
                        "too small for a real rendered mp4 (no slide content)")
    elif not info.ftyp_ok:
        problems.append(f"webinar video {info.video_path} is not a real MP4 (no 'ftyp' "
                        "box at offset 4) — a decoy/stub is not a video")
    if not info.timing_parseable:
        problems.append("webinar timing track (working/checkpoints/webinar_timing.json) is "
                        f"absent or has no timing[] entries ({info.timing_problem})")
    elif info.timing_problem:
        problems.append(f"webinar timing track: {info.timing_problem}")
    if problems:
        return Verdict.FAIL, "; ".join(problems)
    return Verdict.PASS, (f"video {info.video_path} verified (ftyp + {info.video_size} bytes) "
                          f"with contiguous timing track ({info.timing_count} slides)")


def verify_notes_sync(facts: RunFacts) -> Tuple[Verdict, str]:
    """PURE. P9.5-NOTES-SYNC verdict. Mirrors phase_verifiers._verify_notes_sync:
    notes_sync.json must record status='synced' — 'no_speech' is a HARD FAIL (by
    this phase's precondition, P9-SPEECH/P-SPEECH-QC are attested, so a speech
    MUST exist) — and the bundle PPTX it names must have no empty notes panes
    (AF-EMPTY-NOTES-PANE, scanned at seal time)."""
    fact = facts.notes_sync
    if fact.state is not Epistemic.KNOWN:
        return Verdict.FAIL, f"notes_sync {fact.state.value} ({fact.detail})"
    info: NotesSyncInfo = fact.value
    problems = []
    if info.status == "error":
        problems.append(f"notes_sync.json status=error: {info.reason}")
    elif info.status == "no_speech":
        problems.append("notes_sync.json status=no_speech — P9-SPEECH/P-SPEECH-QC are "
                        "attested (this phase's own precondition) but no speech was found "
                        "at re-sync time; the notes pane would still ship empty.")
    elif info.status != "synced":
        problems.append(f"notes_sync.json has unexpected status={info.status!r}")
    if info.notes_pane_result:
        problems.append(info.notes_pane_result)
    if problems:
        return Verdict.FAIL, "; ".join(problems)
    return Verdict.PASS, (f"notes synced ({info.slides_with_notes}/{info.slides_total} "
                          f"slides with notes), no empty notes panes")


def verify_fish_tag(facts: RunFacts) -> Tuple[Verdict, str]:
    """PURE. P8.4-FISH-TAG verdict (AF-FISH-TAG). Mirrors
    phase_verifiers._verify_fish_tag: the tagged speech must exist, exceed the
    2048-byte floor, and its [fish]-tag-stripped text must equal the source
    speech's stripped text (strip-equals prover)."""
    fact = facts.fish_tag
    if fact.state is not Epistemic.KNOWN:
        return Verdict.FAIL, f"fish tag {fact.state.value} ({fact.detail})"
    info: FishTagInfo = fact.value
    problems = []
    if not info.tagged_found:
        problems.append("AF-BUNDLE-INCOMPLETE: PRESENTERS-SPEECH-FISH-TAGGED.md not found")
    if not info.source_found:
        problems.append("AF-BUNDLE-INCOMPLETE: PRESENTERS-SPEECH.md (source) not found")
    if not info.tagged_found or not info.source_found:
        return Verdict.FAIL, "; ".join(problems)
    if info.tagged_size < 2048:
        problems.append(f"PRESENTERS-SPEECH-FISH-TAGGED.md: {info.tagged_size} bytes < 2048")
    if not info.tagged_text or not info.source_text:
        problems.append("AF-FISH-TAG: cannot read tagged or source speech file")
        return Verdict.FAIL, "; ".join(problems)

    def _strip(t: str) -> str:
        t = re.sub(r"\[.*?\]", " ", t)
        t = re.sub(r"\(.*?\)", " ", t)
        return re.sub(r"\s+", " ", t).strip()

    if _strip(info.tagged_text) != _strip(info.source_text):
        problems.append("AF-FISH-TAG: strip-equals prover failed — the tagged speech's "
                        "stripped text does not match the source speech (removing every "
                        "[tag] and (paren) span must reproduce the source exactly)")
    if problems:
        return Verdict.FAIL, "; ".join(problems)
    return Verdict.PASS, "fish-tag strip-equals prover passed (tagged speech is the source plus tags)"


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
