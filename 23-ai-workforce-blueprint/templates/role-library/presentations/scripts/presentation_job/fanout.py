from __future__ import annotations

"""
presentation_job/fanout.py -- the per-phase worker pool (PARALLEL-PIPELINE-SPEC,
2026-08-27, Ticket 1).

WHAT THIS MODULE IS: a bounded-concurrency pool that lets a single dispatcher
phase author N independent units (slides, QC checks, media files) concurrently
instead of one at a time, while leaving `phases.py` (the Engine) and its
RunLock invariant completely untouched -- see the spec's S2.1: "phases.py
changes in exactly one respect: nothing." This module has ZERO importers as
of Ticket 1; dispatcher.py wires it in per-phase starting with Ticket 4
(P4-PROMPT).

HARD INVARIANTS (spec S2.6 -- mechanical, not just documented):

  1. A worker is a callable, not a command. `run_units` takes
     `worker_fn: Callable[[Unit], UnitResult]`. There is no code path here by
     which a worker becomes an argv.
  2. A worker is NEVER a `presentation_job.py` / `presentation_job` package /
     `run_signature_deck.py` / `presentation-canonical-entry.sh` re-entry.
     The Engine holds RunLock (state.py:148) for its whole run
     (`__main__.py:229`, `:582`), so any re-entry dies with EXIT_LOCK_HELD
     (state.py:162) -- the exact regression class
     `tests/test_l11_webinar_executor_no_recursion.py` exists to catch.
     `_assert_not_a_second_engine` below is the mechanical guard: any FUTURE
     subprocess-based worker (e.g. the Ticket 7 ffmpeg clip loop) must call it
     on its argv before invoking `subprocess`/`run_with_cleanup`, and it
     raises at SUBMIT time rather than surfacing as an exit-6 mystery N times
     over.
  3. No fail-fast, no cancellation (spec S2.4). By the time unit 7 of 50
     fails, units 8-50 are already in flight and already billed; cancelling
     them saves nothing and throws away completed work. Every SUBMITTED unit
     runs to its own conclusion, including after the phase deadline passes --
     the deadline only stops NEW submissions.
  4. Deterministic output order (spec S2.5). `run_units` returns results in
     the SAME order as the input `units` list, regardless of completion
     order, so an ordered-concatenation caller (P4-COPY's Wave-D harmonize
     input, the TTS phases) never has to re-sort itself.

RETRY DESIGN NOTE (a place the spec's own pseudocode under-specifies, so the
choice made here is written down rather than left implicit): `worker_fn` is
expected to perform ONE authoritative attempt and return a definitive
UnitResult (status "ok" or "failed") -- exactly what an extracted-verbatim
function like the eventual `_author_one_slide` (Ticket 4, which already
contains ITS OWN internal DISPATCH_RETRY_CAP retry loop, dispatcher.py
~1815-1855) does. `run_units`'s own `retry_cap` is therefore a SEPARATE,
outer safety net that only fires when `worker_fn` *raises* (an unexpected
transport/programming fault), never when it returns a normal "failed"
verdict -- so a worker that already owns its retry policy is never
double-retried by the pool, while a simple worker that has no retry policy of
its own (a QC grader, a media upload) still gets the shared
HEAL_CAP_TRANSIENT-based backoff for free. This is the meaning of spec S2.3's
"retries happen inside the worker": whichever side (worker_fn's own loop, or
this fallback) does the retrying, a retrying unit always occupies exactly one
pool slot and never inflates live concurrency above `workers`.

Concurrency primitive: `concurrent.futures.ThreadPoolExecutor` -- the same
import dispatcher.py already uses (dispatcher.py:58). Not multiprocessing,
not asyncio -- see spec S2.3 for why.
"""

import os
import re
import sys
import threading
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path bootstrap -- same pattern as dispatcher.py, so this module imports
# cleanly both as `presentation_job.fanout` and when scripts_dir is the sys.path
# root (e.g. under a GATE-1-style import smoke test).
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_OWN_SCRIPTS_DIR = _THIS_FILE.parent.parent  # presentation_job/ -> scripts/
if str(_OWN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_OWN_SCRIPTS_DIR))

from presentation_job import heal as _heal  # noqa: E402

# FIX 14 (MASTER Part 8): one per-provider governor for every outbound call.
# Defensive import, same pattern as heal above: a tree that predates the
# governor module (W09 has not landed presentation_job/governor.py yet) keeps
# the old behavior byte-for-byte -- the _run_one gate degrades to a no-op.
try:
    from presentation_job import governor as _governor  # noqa: E402
except ImportError:  # pragma: no cover - pre-FIX-14 trees limit nothing new
    _governor = None  # type: ignore[assignment]

# Reused, never re-invented (spec S2.3): the one retry budget the serial path
# already uses at dispatcher.py:1815 (`for attempt in range(1, DISPATCH_RETRY_CAP + 1)`).
DEFAULT_RETRY_CAP = _heal.HEAL_CAP_TRANSIENT  # = 3


class FanoutContractError(Exception):
    """Raised at SUBMIT time when a worker argv would re-enter the pipeline.
    Never raised for a normal unit failure -- that is a UnitResult with
    status="failed", never an exception."""


# S2.6 point 3: a mechanical guard, not a comment.
_FORBIDDEN_WORKER_TOKENS = (
    "presentation_job.py",
    "presentation_job",
    "run_signature_deck.py",
    "presentation-canonical-entry.sh",
)


def _assert_not_a_second_engine(argv: List[str]) -> None:
    """A worker is a model call or a media subprocess. It is NEVER a pipeline
    re-entry. The Engine holds RunLock (state.py:148) for its whole run, so
    any re-entry dies with EXIT_LOCK_HELD (state.py:162) -- the L11/workbook
    regression class. This raises at SUBMIT time so the failure names the
    cause instead of surfacing as an exit-6 mystery N times over."""
    joined = " ".join(str(a) for a in argv)
    for tok in _FORBIDDEN_WORKER_TOKENS:
        if tok in joined:
            raise FanoutContractError(
                f"worker argv would re-enter the pipeline ({tok!r}); workers are "
                f"model calls or media subprocesses, never second engines: {argv!r}"
            )


@dataclass(frozen=True)
class Unit:
    """One independent piece of fan-out work. `key` must be stable and
    sortable ("slide-07", "chunk-003") -- it is both the merge-ordering key
    and the progress-artifact key. `payload` carries everything the worker
    needs; per spec, no shared mutable state may live here."""
    key: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnitResult:
    key: str
    status: str  # "ok" | "failed" | "skipped"
    attempts: int = 1
    reasons: List[str] = field(default_factory=list)
    target: Optional[str] = None  # path relative to run_dir, when a file was produced
    # FIX 15: optional per-unit stamps {provider, model, request_id, response_id,
    # started_at, ended_at} the worker_fn already holds in hand, forwarded into
    # the unit ledger row below so every unit row carries its own provenance.
    meta: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# S2.2: the Option-B-shaped observability layer bolted onto the Option-A
# direct-HTTP mechanism -- a live progress artifact the dept-presentations
# agent already reads, so a phase "37/50 slides authored, 2 retrying" is
# visible instead of one silent "busy".
# ---------------------------------------------------------------------------
def _progress_path(run_dir: Path, phase_id: str) -> Path:
    return run_dir / "working" / "fanout" / f"{phase_id}-progress.json"


def _write_progress(run_dir: Path, phase_id: str, state: Dict[str, Any]) -> None:
    """Atomic os.replace, matching every other artifact write in this package
    (dispatcher.py:1866-1869) -- concurrent worker threads call this
    concurrently, so a reader must never see a half-written file."""
    path = _progress_path(run_dir, phase_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".partial-{os.getpid()}-{threading.get_ident()}")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def run_units(
    units: List[Unit],
    worker_fn: Callable[[Unit], UnitResult],
    *,
    workers: int,
    run_dir: Path,
    phase_id: str,
    per_unit_timeout_s: Optional[float] = None,
    retry_cap: int = DEFAULT_RETRY_CAP,
    deadline_s: Optional[float] = None,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> List[UnitResult]:
    """Run `units` through `worker_fn` with at most `workers` concurrent
    callables, and return one UnitResult per unit IN INPUT ORDER (never
    completion order -- see module docstring point 4).

    `per_unit_timeout_s`: informational / for subprocess workers to pass to
    their own transport (`urlopen(timeout=...)`, already the case for every
    model call in this package) or to `run_with_cleanup` (phases.py:644).
    Deliberately NOT enforced here via `future.result(timeout=...)`: a
    ThreadPoolExecutor future timeout abandons the future without stopping
    the thread -- the classic way to leak workers (spec S2.3).

    `deadline_s`: phase-level wall-clock ceiling on the POOL's own lifetime,
    computed by the caller from `phase.budget_minutes` (manifest.py:180).
    When it passes, no NEW units are submitted; every already-submitted unit
    still runs to completion (spec S2.4 point 1 -- no cancellation).

    `retry_cap`: see the module docstring's "RETRY DESIGN NOTE" -- this is an
    outer safety net for a `worker_fn` that raises, not a second retry layer
    on top of a `worker_fn` that already retries internally and returns a
    definitive verdict.
    """
    if not units:
        return []

    workers = max(1, min(int(workers), len(units)))
    deadline_at = (time.monotonic() + deadline_s) if deadline_s else None
    lock = threading.Lock()
    progress: Dict[str, Any] = {
        "phase_id": phase_id,
        "total": len(units),
        "workers": workers,
        "units": {u.key: "pending" for u in units},
    }

    def _counts() -> Dict[str, int]:
        vals = list(progress["units"].values())
        return {
            "dispatched": sum(1 for v in vals if v == "dispatched"),
            "retrying": sum(1 for v in vals if v == "retrying"),
            "verified": sum(1 for v in vals if v == "verified"),
            "failed": sum(1 for v in vals if v == "failed"),
            "skipped": sum(1 for v in vals if v == "skipped"),
            "pending": sum(1 for v in vals if v == "pending"),
        }

    def _emit(unit_key: str, state: str) -> None:
        with lock:
            progress["units"][unit_key] = state
            snapshot = dict(progress, units=dict(progress["units"]), counts=_counts())
        _write_progress(run_dir, phase_id, snapshot)
        if progress_cb:
            progress_cb(snapshot)

    def _run_one(unit: Unit) -> UnitResult:
        _emit(unit.key, "dispatched")
        attempts = 0
        last_exc: Optional[BaseException] = None
        cap = max(1, retry_cap)
        # FIX 14: the unit's provider, when the caller stamps one into
        # unit.payload ({"provider": "kie", ...} for image/TTS units, etc.).
        # Unstamped units gate on "deepseek-direct" only if the payload also
        # carries {"govern": true}; plain local units (QC graders, file
        # assembly) consume no provider budget and stay ungated. The gate is
        # best-effort: a tree without presentation_job/governor.py no-ops.
        _gov_provider = unit.payload.get("provider") or "deepseek-direct"
        _gov_enabled = bool(unit.payload.get("provider")) or \
            bool(unit.payload.get("govern"))
        _gov = _governor if _gov_enabled else None
        while attempts < cap:
            attempts += 1
            _lease = None
            if _gov is not None:
                try:
                    # FIX 14 named call site: fanout acquires one governor
                    # lease per attempt so a 40-unit wave can never exceed the
                    # provider's max_inflight or rps/burst window.
                    _lease = _gov.acquire(_gov_provider)
                except Exception:  # noqa: BLE001 -- gating never kills a unit
                    _lease = None
            try:
                result = worker_fn(unit)
                if _gov is not None:
                    try:
                        _gov.report_ok(_gov_provider)
                    except Exception:  # noqa: BLE001
                        pass
                _emit(unit.key, "verified" if result.status == "ok" else "failed")
                return result
            except Exception as exc:  # noqa: BLE001 -- transient-fault safety net (S2.3)
                last_exc = exc
                text = f"{type(exc).__name__}: {exc}"
                if _gov is not None and ("429" in text or
                                         "rate limit" in text.lower()):
                    try:
                        _gov.report_429(_gov_provider)
                    except Exception:  # noqa: BLE001
                        pass
                if attempts >= cap:
                    break
                _emit(unit.key, "retrying")
                time.sleep(min(30, 5 * attempts))
            finally:
                if _gov is not None and _lease is not None:
                    try:
                        _gov.release(_lease)
                    except Exception:  # noqa: BLE001
                        pass
        _emit(unit.key, "failed")
        return UnitResult(key=unit.key, status="failed", attempts=attempts,
                           reasons=[f"worker raised: {last_exc}"])

    results: Dict[str, UnitResult] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for unit in units:
            if deadline_at is not None and time.monotonic() >= deadline_at:
                results[unit.key] = UnitResult(
                    key=unit.key, status="skipped", attempts=0,
                    reasons=["phase deadline reached before submission"])
                _emit(unit.key, "skipped")
                continue
            futures[pool.submit(_run_one, unit)] = unit
        # S2.4: no fail-fast, no cancellation -- every SUBMITTED unit runs to
        # its own conclusion even after the deadline has passed.
        for fut in as_completed(futures):
            unit = futures[fut]
            results[unit.key] = fut.result()

    return [results[u.key] for u in units]


def resolve_effective_workers(
    phase_workers: int,
    unit_count: int,
    *,
    env_var: Optional[str] = None,
    capacity_available: Any = None,
) -> int:
    """Spec S3.3's resolution order:

        effective = min(
            phase.workers,          # manifest, default 1
            env override if set,    # PRESENTATION_PHASE_WORKERS_<PHASE_ID>
            unit_count,             # never more workers than units
            capacity_ceiling,       # capacity.probe(); UNBOUNDED drops out
        )

    `capacity_available` is expected to be `capacity.probe()['available']` --
    a positive int or the UNBOUNDED sentinel. Reuses capacity.is_unbounded()'s
    own contract (`min(n, UNBOUNDED) == n`, capacity.py:253-259) rather than
    re-deriving it, so a NO_CAP_PROVIDERS account (deepseek-direct,
    openrouter) simply drops this term instead of being special-cased here.
    """
    effective = max(1, int(phase_workers))
    effective = min(effective, max(1, int(unit_count)))
    if env_var:
        raw = os.environ.get(env_var)
        if raw:
            try:
                env_val = int(raw)
                if env_val > 0:
                    effective = min(effective, env_val)
            except ValueError:
                pass
    if capacity_available is not None:
        try:
            from presentation_job import capacity as _capacity
            if _capacity.is_unbounded(capacity_available):
                pass  # UNBOUNDED drops out of the min() per its comparison contract
            elif isinstance(capacity_available, int) and capacity_available > 0:
                effective = min(effective, capacity_available)
        except Exception:  # noqa: BLE001 -- capacity probing is best-effort
            pass
    return max(1, effective)


# ---------------------------------------------------------------------------
# FIX 15b (MASTER Part 8 / W07a-B2): manifest-declared fanout by
# slide/section/file -- one unit per item.
#
# The manifest declares, on a per-phase entry:
#     "fanout": {"by": "slide"|"section"|"file", "max_units": N}
# and the dispatcher runs ONE unit per enumerated item (Prompts: one unit per
# slide. Prompt QC: one judge unit per slide. Image QC: one vision unit per
# slide. Copy: one unit per section. Design PNGs: one unit per page. Speech:
# one unit per slide). This module owns three things for that contract:
#
#   1. parse_fanout_field    -- manifest field -> FanoutSpec, refusing a
#                               malformed declaration at parse time (the same
#                               defect class _parse_workers_field refuses in
#                               manifest.py: silent coercion of a scheduling
#                               number).
#   2. enumerate_fanout_items -- run-dir truth -> the deterministic, ordered
#                               list of units for a spec. NO unit is invented:
#                               slides come from slides.json/arc_allocation
#                               (the same sources _prompt_slide_count trusts),
#                               sections from arc_allocation.json /
#                               slides_copy.md headings, files from the
#                               spec's own list or the phase's
#                               produces_artifact patterns.
#   3. append_unit_ledger_row -- one JSONL ledger row per unit into
#                               working/work-orders/_units/<phase>.units.jsonl
#                               ("each unit has its own ledger row", Part 7).
# ---------------------------------------------------------------------------
FANOUT_BY_VALUES = ("slide", "section", "file")


class FanoutSpecError(ValueError):
    """Raised when a manifest's `fanout` field is malformed. The dispatcher
    converts this into a phase error -- the run never proceeds with a guessed
    unit shape."""


@dataclass(frozen=True)
class FanoutSpec:
    by: str                      # "slide" | "section" | "file"
    max_units: Optional[int] = None   # submission-batch cap; None = all units at once

    def batches(self, units: List["Unit"]) -> List[List["Unit"]]:
        """Split `units` into submission batches of at most `max_units`.
        max_units=None (or <= 0, refused at parse) => one batch."""
        if not self.max_units or self.max_units >= len(units):
            return [units]
        return [units[i:i + self.max_units]
                for i in range(0, len(units), self.max_units)]


def parse_fanout_field(raw: Any) -> Optional[FanoutSpec]:
    """Manifest `fanout` field -> FanoutSpec, or None when absent.

    Absent/None => None (the phase is NOT fan-out enabled; the caller keeps
    its existing path untouched). Anything PRESENT but malformed raises
    FanoutSpecError -- a typo'd "by": "Slide" or a string "max_units": "12"
    must never silently degrade to serial dispatch (same refusal rule as
    manifest.py's _parse_workers_field).
    """
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    if not isinstance(raw, dict):
        raise FanoutSpecError(
            f"fanout must be an object {{by, max_units}}, got {raw!r}")
    by = raw.get("by")
    if not isinstance(by, str) or by.strip().lower() not in FANOUT_BY_VALUES:
        raise FanoutSpecError(
            f"fanout.by must be one of {FANOUT_BY_VALUES}, got {by!r}")
    max_units = raw.get("max_units")
    if max_units is not None:
        if isinstance(max_units, bool) or not isinstance(max_units, int) \
                or max_units < 1:
            raise FanoutSpecError(
                f"fanout.max_units must be a positive int, got {max_units!r}")
    return FanoutSpec(by=by.strip().lower(), max_units=max_units)


def unit_output_dir(run_dir: Path, phase_id: str) -> Path:
    """Per-unit scratch outputs for one phase: working/fanout/<phase_id>/."""
    return run_dir / "working" / "fanout" / phase_id


def unit_output_path(run_dir: Path, phase_id: str, unit_key: str) -> Path:
    """Where one unit's authored text lands before the dispatcher aggregates
    it into the phase's real artifact. Deterministic per unit key so a re-run
    (resume) of the same unit overwrites exactly its own scratch file."""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", unit_key)
    return unit_output_dir(run_dir, phase_id) / f"{safe}.out"


def unit_ledger_path(run_dir: Path, phase_id: str) -> Path:
    return run_dir / "working" / "work-orders" / "_units" / f"{phase_id}.units.jsonl"


def append_unit_ledger_row(run_dir: Path, phase_id: str, row: Dict[str, Any]) -> None:
    """One JSONL row per unit into working/work-orders/_units/<phase>.units.jsonl.

    Append-only, best-effort (an OSError must never fail a unit that already
    did its real work). Rows carry at least: unit, status, attempts; callers
    add the provider/model/request-id stamps they already hold in hand."""
    try:
        path = unit_ledger_path(run_dir, phase_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = dict(row)
        record.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        record.setdefault("phase_id", phase_id)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        pass


def _slides_for_units(run_dir: Path) -> List[Dict[str, Any]]:
    """The slide list for by=slide units, from the SAME sources
    dispatcher._prompt_slide_count trusts (working/copy/slides.json, then
    arc_allocation.json). Ordered by ordinal; entries carry at least
    {"ordinal": int}. Returns [] when neither source is present/readable --
    the caller reports that honestly rather than inventing slides."""
    for rel in ("working/copy/slides.json", "slides.json", "working/slides.json"):
        p = run_dir / rel
        if not p.is_file():
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        raw = obj if isinstance(obj, list) else (
            obj.get("slides") if isinstance(obj, dict) else None)
        if isinstance(raw, list) and raw:
            out = []
            for s in raw:
                if isinstance(s, dict):
                    o = s.get("ordinal") if isinstance(s.get("ordinal"), int) else None
                    if o is None and isinstance(s.get("slide"), int):
                        o = s["slide"]
                    if o is None:
                        o = len(out) + 1  # positional fallback keeps order honest
                    out.append({"ordinal": int(o), **{k: v for k, v in s.items()
                                                      if k not in ("ordinal", "slide")}})
            if out:
                return sorted(out, key=lambda s: s["ordinal"])
    arc = run_dir / "working" / "copy" / "arc_allocation.json"
    if arc.is_file():
        try:
            obj = json.loads(arc.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            obj = None
        slots = None
        if isinstance(obj, dict):
            slots = obj.get("slots") or obj.get("allocation") or obj.get("slides")
        elif isinstance(obj, list):
            slots = obj
        if isinstance(slots, list) and slots:
            return [{"ordinal": i + 1, **(s if isinstance(s, dict) else {"slot": s})}
                    for i, s in enumerate(slots)]
    return []


def _sections_for_units(run_dir: Path) -> List[Dict[str, Any]]:
    """The section list for by=section units (P4-COPY: one unit per section).

    Priority: arc_allocation.json's own "sections" array (its declared shape),
    then the arc grouping of its slots, then the top-level headings of the
    existing slides_copy.md, then ONE whole-file unit. Ordered; entries carry
    {"name": str, "ordinal": int}."""
    arc = run_dir / "working" / "copy" / "arc_allocation.json"
    if arc.is_file():
        try:
            obj = json.loads(arc.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            obj = None
        if isinstance(obj, dict):
            secs = obj.get("sections")
            if isinstance(secs, list) and secs:
                return [{"ordinal": i + 1,
                         "name": str((s.get("name") if isinstance(s, dict) else s)
                                     or f"section-{i + 1:02d}")}
                        for i, s in enumerate(secs)]
            slots = obj.get("slots") or obj.get("allocation") or obj.get("slides")
            if isinstance(slots, list) and slots:
                names: List[str] = []
                for s in slots:
                    if not isinstance(s, dict):
                        continue
                    arc_name = s.get("arc") or s.get("section") or s.get("name")
                    if isinstance(arc_name, str) and arc_name.strip() \
                            and arc_name not in names:
                        names.append(arc_name)
                if names:
                    return [{"ordinal": i + 1, "name": n}
                            for i, n in enumerate(names)]
    copy_md = run_dir / "working" / "copy" / "slides_copy.md"
    if copy_md.is_file():
        try:
            names = []
            for line in copy_md.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("## ") and not line.startswith("### "):
                    n = line[3:].strip()
                    if n and n not in names:
                        names.append(n)
            if names:
                return [{"ordinal": i + 1, "name": n} for i, n in enumerate(names)]
        except OSError:
            pass
    return [{"ordinal": 1, "name": "whole"}]


def enumerate_fanout_items(run_dir: Path, spec: FanoutSpec, *, phase_id: str,
                           produces_artifact: Optional[List[str]] = None,
                           ) -> List[Dict[str, Any]]:
    """Deterministic, ordered unit items for one FanoutSpec against a run dir.

    Returns a list of item dicts, each carrying its stable `key` (the merge
    order for text aggregation) plus whatever the unit worker needs:
      by=slide    -> {"key": "slide-NN", "ordinal": N}
      by=section  -> {"key": "section-NN", "ordinal": N, "name": ...}
      by=file     -> {"key": "file-NN", "path": <rel path>}
    """
    if spec.by == "slide":
        slides = _slides_for_units(run_dir)
        return [{"key": f"slide-{s['ordinal']:02d}", "ordinal": s["ordinal"],
                 "slide": s} for s in slides]
    if spec.by == "section":
        secs = _sections_for_units(run_dir)
        return [{"key": f"section-{s['ordinal']:02d}", "ordinal": s["ordinal"],
                 "name": s["name"]} for s in secs]
    # by=file: the spec's own file list wins; else enumerate the phase's
    # produces_artifact patterns (a '*' pattern globs the run dir).
    rels: List[str] = []
    if isinstance(getattr(spec, "files", None), list):
        rels = [str(r) for r in spec.files if str(r).strip()]  # type: ignore[attr-defined]
    elif produces_artifact:
        for pattern in produces_artifact:
            if "*" in pattern or "?" in pattern:
                base = run_dir / pattern
                for hit in sorted(base.parent.glob(base.name)):
                    if hit.is_file():
                        rels.append(str(hit.relative_to(run_dir)))
            else:
                rels.append(pattern)
    seen: set = set()
    items: List[Dict[str, Any]] = []
    for rel in rels:
        if rel in seen:
            continue
        seen.add(rel)
        items.append({"key": f"file-{len(items) + 1:02d}", "path": rel})
    return items
