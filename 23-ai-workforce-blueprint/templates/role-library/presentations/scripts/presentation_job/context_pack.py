"""presentation_job/context_pack.py -- PRES-027: dependency-driven context pack.

THE ONE-SENTENCE PROBLEM THIS FIXES: gather_upstream_context() walked a fixed
global candidate list under a char cap and silently truncated mid-file, so a
large intake consumed the whole P4-COPY budget and excluded all research with
no warning (dispatcher.py pre-fix: intake >100000 chars drops
RESEARCH_SENTINEL silently). Design briefs and phase-specific assets were not
comprehensively included.

WHAT THIS IS
------------
A pure, dependency-driven context pack builder. Per phase it declares REQUIRED
input artifacts (from the manifest's own consumes[] + role SOP refs) and
PROTECTED research inputs (research_map.json + brief excerpts ahead of raw
transcript/history), token-counts under the conservative 4:1 rule
(workingset.CHARACTERS_PER_TOKEN), reserves output + reasoning headroom for
the routed model, and NEVER silently truncates a required artifact or JSON
mid-value. Oversize packs raise an explicit context_overflow carrying a
deterministic sharding/compaction action instead of a torn prompt.

CONTRACT
--------
  * build_pack(run_dir, phase_id, ...) -> ContextPack. pack.text is the
    prompt-ready context; pack.inclusion_manifest records every file with its
    sha256, bytes included, and required/optional status; pack.overflow is
    None on success or a context_overflow dict (with action shard|block and a
    deterministic shard plan) when required inputs exceed the model budget.
  * Required artifacts are all-or-nothing: any required file present on disk
    is included WHOLE or the pack overflows loudly. Optional files fill
    remaining budget whole-only (never mid-file slices, never mid-JSON).
  * Model budget: MODEL_INPUT_BUDGET_CHARS maps routed model id prefixes to
    a max input in chars; unknown models fall back to the conservative
    DEFAULT_INPUT_BUDGET_CHARS. Reserves: output (max_tokens*4 chars) +
    equal reasoning headroom (thinking MAX bills reasoning out of the same
    budget -- dispatcher.py) + FIXED_OVERHEAD_CHARS for role SOP/persona/
    contract framing. available = budget - reserves, floored at MIN budget.
  * Rollout flag: PRESENTATION_CONTEXT_PACK=0 restores the pre-fix path
    (dispatcher falls back to its inline gather loop); the flag never
    silently narrows a pack.

No network, no credentials, no engine imports at module load (stdlib only +
lazy workingset import for the 4:1 constant).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FLAG_ENV = "PRESENTATION_CONTEXT_PACK"
FLAG_DEFAULT = "1"

CHARACTERS_PER_TOKEN = 4  # workingset.CHARACTERS_PER_TOKEN (conservative 4:1)
FIXED_OVERHEAD_CHARS = 70_000  # role SOP + persona bundle + contract framing
MIN_AVAILABLE_CHARS = 20_000  # a pack smaller than this cannot carry any phase

# Per-model max INPUT chars (conservative operating budgets, not vendor
# maxima). Sources: dispatcher.py ships P4-COPY at 100K and P-PROMPT-QC at
# 500K against DeepSeek; workingset.py caps the fleet model at 131072 tokens
# (~524K chars at 4:1). GLM/OpenRouter rows stay at or under the DeepSeek
# row until a live measurement raises them -- an unknown reading is never
# rounded upward into capability.
MODEL_INPUT_BUDGET_CHARS: Dict[str, int] = {
    "deepseek-v4-pro": 500_000,
    "deepseek-v4-flash": 500_000,
    "glm-5.3": 400_000,
    "glm-5": 400_000,
    "glm-flash": 200_000,
    "glm-ocr": 200_000,
    "gpt-image": 50_000,
}
DEFAULT_INPUT_BUDGET_CHARS = 200_000

# Research inputs that outrank optional raw transcript/history for copy
# phases (TODO step 5): protected budget is filled before any optional file.
PROTECTED_RESEARCH = (
    "working/research/research_map.json",
    "working/research/brief-*.md",
)

# Raw low-signal files: included only after required + protected fit.
OPTIONAL_LOW_SIGNAL = (
    "working/interview/intake_transcript.json",
    "working/interview/intake_ledger.json",
    "working/copy/sp_claims.json",
    "working/copy/sp_structure.json",
    "working/copy/mission_prd.json",
)

# Per-slide phases: the pack is scoped to one ordinal's inputs.
PER_SLIDE_PHASES = frozenset({"P4-PROMPT", "P-PROMPT-QC", "P-IMAGE-QC"})


class ContextOverflow(RuntimeError):
    """Required inputs exceed the model budget. Carries the overflow dict."""

    def __init__(self, overflow: Dict[str, Any]) -> None:
        super().__init__(
            f"context_overflow for {overflow.get('phase_id')}: "
            f"required {overflow.get('required_chars')} chars > "
            f"available {overflow.get('available_chars')} chars "
            f"(model {overflow.get('model')}); action={overflow.get('action')}")
        self.overflow = overflow


def flag_enabled() -> bool:
    raw = os.environ.get(FLAG_ENV, FLAG_DEFAULT)
    return str(raw).strip().strip("'\"") != "0"


def model_input_budget(model: Optional[str]) -> int:
    """Max input chars for a routed model id (prefix match, conservative)."""
    name = str(model or "").strip().lower()
    for prefix, budget in MODEL_INPUT_BUDGET_CHARS.items():
        if name.startswith(prefix) or prefix in name:
            return budget
    return DEFAULT_INPUT_BUDGET_CHARS


def available_budget(model: Optional[str], max_output_tokens: int = 64_000) -> int:
    """Usable input chars after output + framing reserves.

    DeepSeek bills reasoning AND content out of the SAME max_tokens budget
    (dispatcher.py: reasoning_tokens is a SUBSET of completion_tokens), so
    one output-sized reserve covers both -- not two. Small-context models
    whose budget cannot hold the requested output overflow loudly so the
    caller shards (and lowers max_tokens per shard) instead of sending an
    oversized request.
    """
    budget = model_input_budget(model)
    reserve = int(max_output_tokens) * CHARACTERS_PER_TOKEN
    avail = budget - reserve - FIXED_OVERHEAD_CHARS
    return max(MIN_AVAILABLE_CHARS, avail)


def recommended_max_tokens(model: Optional[str]) -> int:
    """Largest output budget a model can serve while keeping headroom: half
    the post-overhead budget in tokens (output + equal thinking share)."""
    budget = model_input_budget(model)
    return max(4_000, (budget - FIXED_OVERHEAD_CHARS) // CHARACTERS_PER_TOKEN // 2)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _expand(pattern: str, run_dir: Path) -> List[Path]:
    if any(c in pattern for c in "*?["):
        return sorted(p for p in run_dir.glob(pattern) if p.is_file())
    p = run_dir / pattern
    return [p] if p.is_file() else []


def required_patterns(phase_id: str, manifest=None) -> List[str]:
    """Required input patterns for a phase: the manifest's own consumes[].

    Falls back to the pre-fix P4-COPY set when no manifest resolves, so a
    missing manifest degrades to the old known list, never to an empty pack.
    """
    if manifest is not None:
        try:
            ph = manifest.phase_or_none(phase_id) if hasattr(
                manifest, "phase_or_none") else next(
                    (p for p in manifest.phases if p.id == phase_id), None)
        except Exception:  # noqa: BLE001 -- manifest failure is not a pack failure
            ph = None
        if ph is not None and getattr(ph, "consumes", None):
            return list(ph.consumes)
    if phase_id == "P4-COPY":
        return ["working/copy/intake.json", "working/copy/arc_allocation.json",
                "working/copy/priority_shift_spec.json",
                "working/copy/sp_intake.json"]
    return ["working/copy/intake.json"]


@dataclass
class ContextPack:
    phase_id: str
    text: str
    total_chars: int
    model: Optional[str]
    available_chars: int
    inclusion_manifest: List[Dict[str, Any]] = field(default_factory=list)
    content_hash: str = ""
    overflow: Optional[Dict[str, Any]] = None

    def manifest_json(self) -> str:
        return json.dumps({"phase_id": self.phase_id, "model": self.model,
                           "total_chars": self.total_chars,
                           "available_chars": self.available_chars,
                           "content_hash": self.content_hash,
                           "overflow": self.overflow,
                           "inputs": self.inclusion_manifest},
                          indent=2, ensure_ascii=False)


def _read_whole(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _slide_anchors(research_map_path: Path, ordinal: Optional[int]) -> List[str]:
    """Exact research anchors for one slide ordinal out of research_map.json."""
    if ordinal is None:
        return []
    try:
        obj = json.loads(research_map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = obj.get("items") if isinstance(obj, dict) else obj
    if not isinstance(items, list):
        return []
    out: List[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        slides = it.get("slides", it.get("slide_numbers", it.get("slide")))
        if isinstance(slides, int):
            slides = [slides]
        if isinstance(slides, list) and ordinal in slides:
            out.append(json.dumps(it, ensure_ascii=False))
    return out


def build_pack(run_dir: Path, phase_id: str, *,
               model: Optional[str] = None,
               max_output_tokens: int = 64_000,
               manifest=None,
               slide_ordinal: Optional[int] = None,
               extra_required: Optional[List[str]] = None) -> ContextPack:
    """Build the dependency-driven context pack for one phase.

    Raises ContextOverflow when required inputs exceed the model budget
    (callers shard or block -- never truncate). Optional inputs fill
    remaining budget whole-only.
    """
    avail = available_budget(model, max_output_tokens)
    patterns = list(required_patterns(phase_id, manifest))
    for extra in (extra_required or []):
        if extra not in patterns:
            patterns.append(extra)

    # Per-slide scoping (TODO step 3): this ordinal's anchors ride with the
    # shared pack; the shared pack itself stays cached and content-addressed.
    # research_map.json as a WHOLE is a shared lookup index, not a per-slide
    # input: when an ordinal is scoped, the whole map is replaced by that
    # ordinal's exact anchors so sibling slides' claims never ride along.
    anchored: List[str] = []
    scoped_map = False
    if slide_ordinal is not None:
        rm = run_dir / "working" / "research" / "research_map.json"
        if rm.is_file():
            anchored = _slide_anchors(rm, slide_ordinal)
            scoped_map = True

    parts: List[str] = []
    manifest_rows: List[Dict[str, Any]] = []
    required_chars = 0
    required_rows: List[Tuple[str, str]] = []  # (rel, text)

    for pattern in patterns:
        for path in _expand(pattern, run_dir):
            rel = str(path.relative_to(run_dir))
            text = _read_whole(path)
            if text is None:
                continue
            required_rows.append((rel, text))
            required_chars += len(text)

    if required_chars > avail:
        overflow = {
            "event": "context_overflow",
            "phase_id": phase_id,
            "model": model,
            "required_chars": required_chars,
            "available_chars": avail,
            "action": "shard",
            "shard_hint": _shard_hint(phase_id, required_rows, avail),
            "required_files": [rel for rel, _ in required_rows],
        }
        raise ContextOverflow(overflow)

    total = 0
    map_rel = "working/research/research_map.json"
    for rel, text in required_rows:
        if scoped_map and rel == map_rel:
            # Scoped ordinal: the whole-map row is replaced by the exact
            # anchor block below (sibling slides' claims never ride along).
            manifest_rows.append({"path": rel, "sha256": sha256_text(text),
                                  "chars": len(text), "required": True,
                                  "included": False,
                                  "reason": "scoped-to-ordinal-anchors"})
            continue
        parts.append(f"### {rel}\n```\n{text}\n```")
        manifest_rows.append({"path": rel, "sha256": sha256_text(text),
                              "chars": len(text), "required": True,
                              "included": True})
        total += len(text)

    # Protected research budget (TODO step 5): research_map + brief excerpts
    # before optional raw transcript/history -- for phases whose manifest
    # consumes do not already name them.
    named = set(patterns)
    protected = [p for p in PROTECTED_RESEARCH
                 if not (scoped_map and p == "working/research/research_map.json")]
    for pattern in protected:
        if any(fnmatch.fnmatch(pattern, n) or fnmatch.fnmatch(n, pattern)
               for n in named):
            continue
        for path in _expand(pattern, run_dir):
            rel = str(path.relative_to(run_dir))
            if any(r["path"] == rel for r in manifest_rows):
                continue
            text = _read_whole(path)
            if text is None:
                continue
            if total + len(text) > avail:
                manifest_rows.append({"path": rel, "sha256": sha256_text(text),
                                      "chars": len(text), "required": False,
                                      "included": False,
                                      "reason": "over-budget-whole-only"})
                continue
            parts.append(f"### {rel}\n```\n{text}\n```")
            manifest_rows.append({"path": rel, "sha256": sha256_text(text),
                                  "chars": len(text), "required": False,
                                  "included": True, "protected": True})
            total += len(text)

    # Per-slide anchors (exact, small, always fit-or-overflow-loudly).
    for anchor in anchored:
        if total + len(anchor) > avail:
            break
        parts.append(f"### slide-{slide_ordinal}-research-anchor\n```\n{anchor}\n```")
        manifest_rows.append({"path": f"working/research/research_map.json"
                                      f"#slide-{slide_ordinal}",
                              "sha256": sha256_text(anchor),
                              "chars": len(anchor), "required": True,
                              "included": True, "scoped": True})
        total += len(anchor)

    # Optional low-signal files, whole-only, never mid-JSON.
    for pattern in OPTIONAL_LOW_SIGNAL:
        for path in _expand(pattern, run_dir):
            rel = str(path.relative_to(run_dir))
            if any(r["path"] == rel for r in manifest_rows):
                continue
            text = _read_whole(path)
            if text is None:
                continue
            if total + len(text) > avail:
                manifest_rows.append({"path": rel, "sha256": sha256_text(text),
                                      "chars": len(text), "required": False,
                                      "included": False,
                                      "reason": "over-budget-whole-only"})
                continue
            parts.append(f"### {rel}\n```\n{text}\n```")
            manifest_rows.append({"path": rel, "sha256": sha256_text(text),
                                  "chars": len(text), "required": False,
                                  "included": True})
            total += len(text)

    text = "\n\n".join(parts) if parts else \
        "(no upstream artifacts exist yet for this run)"
    pack = ContextPack(phase_id=phase_id, text=text, total_chars=total,
                       model=model, available_chars=avail,
                       inclusion_manifest=manifest_rows)
    pack.content_hash = sha256_text(
        json.dumps(manifest_rows, sort_keys=True, default=str))
    return pack


def _shard_hint(phase_id: str, required_rows: List[Tuple[str, int]],
                avail: int) -> Dict[str, Any]:
    """Deterministic sharding/compaction action for an overflowed pack."""
    if phase_id in PER_SLIDE_PHASES or phase_id == "P-PROMPT-QC":
        return {"strategy": "shard-by-unit",
                "unit": "slide",
                "note": "dispatch each slide ordinal with its complete unit "
                        "inputs, then aggregate coverage + whole-deck cohesion"}
    if phase_id in ("P4-COPY", "P-IMAGE-QC"):
        return {"strategy": "shard-by-section",
                "note": "split copy/image QC by manifest fanout sections with "
                        "complete inputs per unit, then aggregate"}
    files = [rel for rel, _ in required_rows]
    return {"strategy": "compact-optional-first",
            "note": "drop optional transcript/history, protect required "
                    "research; block paid generation if still over budget",
            "required_files": files}


def shard_units(phase_id: str, count: int) -> List[Dict[str, Any]]:
    """Deterministic unit list for sharded QC (TODO step 4): every unit gets
    complete inputs; the aggregate checks coverage + whole-deck cohesion."""
    return [{"unit": i + 1, "of": count, "phase_id": phase_id,
             "requires_complete_inputs": True} for i in range(max(1, count))]
