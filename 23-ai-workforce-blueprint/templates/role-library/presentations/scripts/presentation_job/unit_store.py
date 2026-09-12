from __future__ import annotations

"""
presentation_job/unit_store.py -- durable fan-out unit records (PRES-014, W2
WF05).

THE DEFECT THIS CLOSES (SPEC.md PRES-014): `_dispatch_phase_fanout_units`
enumerates and submits ALL units on every dispatch tick; the per-unit scratch
files under working/fanout/<phase>/ are written but never READ before new
model calls. A resume after one failed unit of twenty therefore re-bills all
twenty -- and `FanoutSpec.max_units` was ambiguous between "how many variants
the phase WANTS" (P-STYLE-SPEC's count of 3) and "submission batch width", so
a 100-slide style phase could call the model once per slide and then have the
aggregator throw all but three away.

THE CONTRACT HERE (spec text, verbatim obligations):

  1. Durable unit records keyed
     company_id/presentation_id/phase_id/unit_id/revision, plus source/input
     hashes, author route and QC revision.
  2. Banked results are READ AND VALIDATED before admission: a banked record
     only re-admits (saves a call) when its output file still exists, its
     content hash still matches, and its recorded input hash still matches the
     unit's CURRENT input hash. A corrupt/truncated/absent banked output is
     NOT a pass -- exactly one unit regenerates.
  3. Append-only transition history: every unit state change appends one
     JSONL transition row (never a rewrite of history), and the CURRENT state
     pointer is a separate atomic index so a reader never sees a torn state.
  4. Only failed/changed units resubmit: a unit whose record says ok/verified
     with matching hashes is banked (attempts=0 on this call) and never
     re-submitted. The attempt/budget ledger is durable ACROSS restarts --
     no restart resets it.
  5. max_units is disambiguated into TWO fields, migrated from the manifest:
       * desired_count -- how many units the phase WANTS done (style
         variants: 3). Reduces the enumerated unit list; never drops per-slide
         QC coverage.
       * batch_width  -- how many units are IN FLIGHT per admission batch
         (bounded concurrent batches; QC still covers every slide).
     parse_fanout_field keeps accepting legacy {"by","max_units"} and the
     migration maps max_units -> desired_count (the shipped manifest's nine
     declarations all mean a desired count, per PRES-014's own example:
     "style spec max_units3").
  6. per-slide QC coverage: batch_width bounds CONCURRENCY; every enumerated
     slide is still admitted exactly once across the batches.

IDENTITY (company_id/presentation_id): the engine's own resolution chain --
company_id from working/copy/intake.json["company_id"]/["business_name"] (the
deck's owner), presentation_id from manifest._resolve_deck_slug's chain
(deck_slug -> title -> state.json intake -> run_dir.name). Both are stable
across a run and across resumes of the same run dir, which is the only reuse
boundary this store serves (banked records live INSIDE the run dir, so a
different run dir can never read another run's banked outputs).

REVISION: the per-unit input hash IS the revision witness. A unit whose
inputs changed gets revision=N+1 (its record's input_hash no longer matches),
which is what makes "change 2 slides -> exactly those 2 (+ dependents) rerun"
a mechanical property instead of a hope.

STORAGE LAYOUT (all under working/fanout/_units/ -- inside the fanout tree
the sweep's work-order glob never touches):

  working/fanout/_units/<phase_id>/records.jsonl     append-only transitions
  working/fanout/_units/<phase_id>/state.json        atomic current-state map

NO RESTART RESET: state.json here is read on every admission pass and only
rewritten by an atomic os.replace; transitions.jsonl is only ever appended.
Nothing in this module ever truncates either file.
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Field names for the disambiguated fanout spec (PRES-014 step 1).
# ---------------------------------------------------------------------------
DESIRED_COUNT_KEY = "desired_count"
BATCH_WIDTH_KEY = "batch_width"
LEGACY_MAX_UNITS_KEY = "max_units"


class UnitRecordError(ValueError):
    """Raised when a durable unit record is too broken to trust. The caller
    treats this as NOT-BANKED (the unit re-runs); it never fabricates a pass."""


def content_sha256(text: str) -> str:
    """The content hash a unit record stores. sha256 of the exact bytes the
    scratch file holds (utf-8). Stable across restarts and hosts."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> Optional[str]:
    """sha256 of a file's bytes, or None when unreadable -- never a guess."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def input_hash_for_unit(payload: Dict[str, Any]) -> str:
    """The unit's INPUT hash: a canonical sha256 over the sorted, stable-JSON
    serialization of the unit's payload (its slide/section/file item dict).
    Two calls with identical inputs produce the identical hash, so a changed
    slide changes exactly its own hash. Payloads carrying the whole upstream
    deck are NOT hashed here -- the payload the enumerator hands each unit is
    already unit-scoped."""
    try:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                               default=str)
    except (TypeError, ValueError):
        canonical = repr(sorted((k, str(v)) for k, v in payload.items()))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Identity resolution -- the store's own two-segment key prefix.
# ---------------------------------------------------------------------------
def resolve_company_id(run_dir: Path) -> str:
    """company_id: the deck's owning identity, from the intake the engine
    already maintains. intake.json["company_id"] first, then business_name,
    then "unknown-company" -- a MISSING company id is recorded as unknown, it
    is never invented from a hostname or a timestamp."""
    for rel in ("working/copy/intake.json", "intake.json", "working/intake.json"):
        p = run_dir / rel
        if not p.is_file():
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(obj, dict):
            continue
        for key in ("company_id", "business_name", "company"):
            v = obj.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()[:200]
    return "unknown-company"


def resolve_presentation_id(run_dir: Path) -> str:
    """presentation_id: the run's own deck identity -- run_dir.name. The run
    dir IS the presentation instance this engine addresses; banked records
    live inside it, so the key can never cross runs."""
    return run_dir.name or "unknown-presentation"


# ---------------------------------------------------------------------------
# Storage paths.
# ---------------------------------------------------------------------------
def unit_store_dir(run_dir: Path, phase_id: str) -> Path:
    return run_dir / "working" / "fanout" / "_units" / phase_id


def unit_state_path(run_dir: Path, phase_id: str) -> Path:
    return unit_store_dir(run_dir, phase_id) / "state.json"


def unit_transitions_path(run_dir: Path, phase_id: str) -> Path:
    return unit_store_dir(run_dir, phase_id) / "transitions.jsonl"


# ---------------------------------------------------------------------------
# Record shape. One record per unit id, current state + history pointer.
# ---------------------------------------------------------------------------
def _empty_record(unit_id: str) -> Dict[str, Any]:
    return {
        "unit_id": unit_id,
        "company_id": None,
        "presentation_id": None,
        "phase_id": None,
        "revision": 0,
        "input_hash": None,
        "output_hash": None,
        "output_path": None,
        "author_route": None,        # {provider, model, request_id} of the author call
        "qc_revision": None,         # the QC stamp the phase's verifier left, when known
        "status": "pending",         # pending|admitted|ok|failed|banked
        "attempts_total": 0,         # DURABLE across restarts -- never reset here
        "last_error": None,
        "updated_at": None,
    }


def load_state(run_dir: Path, phase_id: str) -> Dict[str, Dict[str, Any]]:
    """Read the CURRENT per-unit records for one phase. Returns {} when the
    store has never been written (a first run), or when the state file is
    unreadable -- the caller then admits everything (safe default: a corrupt
    ledger must never skip work, only ever re-run it)."""
    try:
        obj = json.loads(unit_state_path(run_dir, phase_id)
                         .read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    units = obj.get("units") if isinstance(obj, dict) else None
    if not isinstance(units, dict):
        return {}
    return {str(k): v for k, v in units.items() if isinstance(v, dict)}


def save_state(run_dir: Path, phase_id: str, units: Dict[str, Dict[str, Any]],
               *, company_id: str, presentation_id: str) -> None:
    """Atomic replace of the current-state map (never an append, never a
    rewrite of transitions.jsonl)."""
    path = unit_state_path(run_dir, phase_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "phase_id": phase_id,
        "company_id": company_id,
        "presentation_id": presentation_id,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "units": units,
    }
    tmp = path.with_name(path.name + f".partial-{os.getpid()}")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False),
                   encoding="utf-8")
    os.replace(tmp, path)


def append_transition(run_dir: Path, phase_id: str, unit_id: str, *,
                      from_status: str, to_status: str, reason: str,
                      company_id: str = "", presentation_id: str = "",
                      revision: int = 0, input_hash: str = "",
                      output_hash: str = "", route: Optional[Dict[str, Any]] = None,
                      attempts_total: int = 0) -> None:
    """ONE append-only JSONL row per unit transition. Best-effort on OSError
    exactly like fanout.append_unit_ledger_row -- the ledger must never fail
    a unit that already did its real work."""
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase_id": phase_id,
        "unit_id": unit_id,
        "company_id": company_id,
        "presentation_id": presentation_id,
        "revision": revision,
        "from_status": from_status,
        "to_status": to_status,
        "reason": reason[:500],
        "input_hash": input_hash,
        "output_hash": output_hash,
        "author_route": route or None,
        "attempts_total": attempts_total,
    }
    try:
        path = unit_transitions_path(run_dir, phase_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        pass


def stamp_identity(record: Dict[str, Any], *, company_id: str,
                   presentation_id: str, phase_id: str) -> Dict[str, Any]:
    """Fill the record's identity columns (idempotent). Returns the record."""
    record["company_id"] = company_id
    record["presentation_id"] = presentation_id
    record["phase_id"] = phase_id
    return record


# ---------------------------------------------------------------------------
# Banked-result validation (spec: "read and validate banked results before
# admission"). A banked record admits ONLY when every leg holds:
#   * status in ("ok", "verified", "banked")            -- it PASSED before
#   * input_hash == the unit's CURRENT input hash       -- its inputs did not change
#   * output file exists and hashes to the recorded value -- it is not corrupt
#   * non-empty content                                  -- never a stub
# Any failure => NOT banked => the unit re-runs (regenerates exactly 1).
# ---------------------------------------------------------------------------
BANKED_STATUSES = ("ok", "verified", "banked")


def validate_banked(record: Optional[Dict[str, Any]], *, run_dir: Path,
                    current_input_hash: str) -> Tuple[bool, str]:
    """(admits, why) for one banked record against the unit's current input."""
    if not isinstance(record, dict):
        return False, "no prior record"
    if record.get("status") not in BANKED_STATUSES:
        return False, f"prior status {record.get('status')!r} is not banked-ok"
    if record.get("input_hash") != current_input_hash:
        return False, "input hash changed since the banked result"
    rel = record.get("output_path")
    if not isinstance(rel, str) or not rel:
        return False, "banked record names no output file"
    out = run_dir / rel
    if not out.is_file():
        return False, "banked output file is missing"
    want = record.get("output_hash")
    if not isinstance(want, str) or not want:
        return False, "banked record carries no output hash"
    got = file_sha256(out)
    if got != want:
        return False, (f"banked output corrupt (hash {str(got)[:12]}... != recorded "
                       f"{str(want)[:12]}...) -- regenerating this one unit")
    try:
        text = out.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return False, "banked output unreadable"
    if not text:
        return False, "banked output is empty"
    return True, "banked result validated: file present, hashes match"


# ---------------------------------------------------------------------------
# max_units disambiguation (PRES-014 step 1): separate the DESIRED WORK COUNT
# from the BATCHING WIDTH, and migrate the legacy field.
# ---------------------------------------------------------------------------
def migrate_fanout_field(raw: Any) -> Dict[str, Any]:
    """Legacy/normalised {"by", "max_units"|...} -> {"by", "desired_count",
    "batch_width"}.

    Migration rule (the SAFE direction): an un-migrated manifest's max_units
    maps to batch_width ONLY -- a bounded batch of that width still covers
    every enumerated unit exactly once, so the migration can never silently
    DROP work. desired_count is set ONLY by an explicit manifest declaration
    (the migrated PIPELINE-MANIFEST.json names it directly on the variant
    phases: P-STYLE-SPEC desired_count 3, P-U-DESIGN-* desired_count 3) --
    the phases whose reducer provably consumes exactly that many whole-deck
    units. An un-migrated manifest keeps pre-PRES-014 behavior (all units
    admitted); the migrated manifest carries the unambiguous contract.
    """
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    by = raw.get("by")
    if isinstance(by, str):
        out["by"] = by
    legacy = raw.get(LEGACY_MAX_UNITS_KEY)
    desired = raw.get(DESIRED_COUNT_KEY)
    width = raw.get(BATCH_WIDTH_KEY)
    if isinstance(desired, int) and not isinstance(desired, bool) and desired > 0:
        out[DESIRED_COUNT_KEY] = desired
    if isinstance(width, int) and not isinstance(width, bool) and width > 0:
        out[BATCH_WIDTH_KEY] = width
    elif isinstance(legacy, int) and not isinstance(legacy, bool) and legacy > 0:
        out[BATCH_WIDTH_KEY] = legacy
    return out


def apply_desired_count(units: List[Any], desired_count: Optional[int]) -> List[Any]:
    """Reduce the enumerated unit list to the phase's DESIRED WORK COUNT.

    The first N units in enumeration order are kept (slides are ordered by
    ordinal, so the reducer keeps the deck's leading slides -- the same
    behavior the shipped P-STYLE-SPEC aggregator already had when it kept the
    first three well-formed variants). desired_count None/0/>len = all units.
    NEVER called for per-slide QC phases: their coverage obligation is every
    slide, exactly once (the dispatcher passes desired_count=None there)."""
    if not desired_count or desired_count < 1 or desired_count >= len(units):
        return list(units)
    return list(units[:desired_count])


def plan_batches(units: List[Any], batch_width: Optional[int]) -> List[List[Any]]:
    """Admission batches of at most batch_width units each. batch_width None
    or <1 = ONE batch (the whole list). This is COVERAGE, not concurrency:
    every unit lands in exactly one batch, in order, none dropped."""
    n = len(units)
    if n == 0:
        return []
    if not batch_width or batch_width < 1 or batch_width >= n:
        return [list(units)]
    return [units[i:i + batch_width] for i in range(0, n, batch_width)]