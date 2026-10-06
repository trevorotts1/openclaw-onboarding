"""wave_contract.py -- FIX 104: ONE WaveContract for the P4-PROMPT wave.

Master Part 8 Fix 104. Before this module the P4-PROMPT wave input existed in
THREE hand-maintained places that could (and on F41 did) drift apart:

  1. dispatcher._prompt_routing_stamp         -- builds the routing stamp
  2. dispatcher._dispatch_prompt_phase_parallel -- hand-builds wave_input dict
  3. parallel_prompt_worker.validate_input    -- re-validates with a hand-built
     field whitelist that silently DROPPED any field the stamp grew (F41's
     measured_capacity=None rejection; F42's owning_role near-loss)

This module makes the contract a SINGLE dataclass with THREE seams:

  * stamp()        -- the routing stamp (dispatcher's FIX 7 profile-truth logic
                      stays where it lives; the shape lives here)
  * wave_input()   -- stamp + run identity + owning_role + prompt constraints
                      + slides -> the canonical prompt-wave-input.json payload
  * validate_input() -- the whole-input reject gate. Field-by-field, driven by
                      the dataclass field spec -- NOT a hand-built whitelist.
                      Anything it does not recognize passes through UNTOUCHED
                      (identity), so no field can be lost between stamp and
                      validate no matter which side grows first.

The contract is carried through the transport seams unchanged:

  seam 1: dispatcher builds a WaveContract, calls contract.wave_input(),
          writes prompt-wave-input.json (schema_version 1, unchanged shape)
  seam 2: parallel_prompt_worker.load_input()/run_worker() call
          wave_contract.validate_input() instead of its own hand-built
          whitelist -- same reject codes, same exit-2 class, same normalized
          dict, but every field the dispatcher stamped survives verbatim.

Spawn children may import this module standalone: it depends only on stdlib.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1
PHASE_ID = "P4-PROMPT"
DEFAULT_MIN_CHARS = 9000
DEFAULT_MAX_CHARS = 18000
#: The three block prefixes the serial loop's prompt contract has always
#: required (dispatcher._dispatch_prompt_phase_parallel built these inline).
DEFAULT_REQUIRED_BLOCKS = ("[ARCHETYPE", "DO-NOT BLOCK", "Do not ")
DEFAULT_ROUTING_KEYS = (
    "provider", "model", "mode", "measured_capacity",
    "router", "route_reason", "requested_alias",
    "capacity_status", "capacity_source",
)


class WaveContractError(RuntimeError):
    """Pre-dispatch whole-input reject. Worker maps this to its exit-2 class;
    the dispatcher maps it to a named phase error. Zero provider spend."""


@dataclass(frozen=True)
class RoutingStamp:
    """FIX 7 profile-driven routing stamp, shape owned HERE.

    Extra keys the dispatcher's resolution grows (route_reason,
    requested_alias, capacity_status, capacity_source, anything future) are
    carried in `extra` and ride the stamp verbatim -- validate_input refuses
    nothing it does not know about."""
    provider: str = "deepseek-direct"
    model: str = ""
    router: str = "disabled"
    mode: str = "standard"
    measured_capacity: int = 8
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "router": self.router,
            "mode": self.mode,
            "measured_capacity": self.measured_capacity,
        }
        out.update(self.extra)
        return out


@dataclass(frozen=True)
class PromptConstraints:
    """min/max chars + required block prefixes for a gate-passing prompt."""
    min_chars: int = DEFAULT_MIN_CHARS
    max_chars: int = DEFAULT_MAX_CHARS
    required_blocks: Tuple[str, ...] = DEFAULT_REQUIRED_BLOCKS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_chars": self.min_chars,
            "max_chars": self.max_chars,
            "required_blocks": list(self.required_blocks),
        }


@dataclass
class WaveContract:
    """The ONE P4-PROMPT wave contract. Built by the dispatcher from the
    routing stamp + run identity; consumed by the worker through
    wave_input()/validate_input(). No third copy of the field list exists."""
    run_id: str
    run_dir: str
    owning_role: str
    routing: RoutingStamp
    slides: List[Dict[str, Any]]
    prompt_constraints: PromptConstraints = field(default_factory=PromptConstraints)
    schema_version: int = SCHEMA_VERSION
    phase_id: str = PHASE_ID

    # -- seam 2: the canonical wave input payload --------------------------
    def wave_input(self) -> Dict[str, Any]:
        """The exact prompt-wave-input.json document (schema_version 1).
        The dispatcher writes this; the worker validates the same shape."""
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "run_dir": self.run_dir,
            "phase_id": self.phase_id,
            "owning_role": self.owning_role,
            "routing": self.routing.to_dict(),
            "prompt_constraints": self.prompt_constraints.to_dict(),
            "slides": [dict(s) for s in self.slides],
        }

    # -- seam 3: the whole-input reject gate -------------------------------
    def validate(self) -> Dict[str, Any]:
        """Validate THIS contract's fields directly (dispatcher-side pre-write
        check). Raises WaveContractError on the first violation. Returns the
        normalized wave-input dict (same document wave_input() builds)."""
        return validate_input(self.wave_input(), "wave_contract")

    def write(self, run_dir: Optional[Path] = None) -> Path:
        """Atomically write prompt-wave-input.json under
        <run_dir>/working/checkpoints/ and return its path."""
        target = Path(run_dir or self.run_dir) / "working" / "checkpoints" / \
            "prompt-wave-input.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".partial")
        tmp.write_text(
            json.dumps(self.wave_input(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        tmp.replace(target)
        return target


# ---------------------------------------------------------------------------
# The shared whole-input validator (no hand-built whitelist: field-spec-driven
# passthrough -- unknown keys survive, known keys are checked).
# ---------------------------------------------------------------------------
def _check_routing(routing: Any, where: str) -> None:
    if not isinstance(routing, dict):
        raise WaveContractError(f"{where}: routing must be an object")
    for key in ("provider", "model", "mode"):
        if not isinstance(routing.get(key), str) or not routing[key].strip():
            raise WaveContractError(
                f"{where}: routing.{key} must be a non-empty string")
    cap = routing.get("measured_capacity")
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise WaveContractError(
            f"{where}: routing.measured_capacity must be a positive integer "
            f"(got {cap!r})")


def _check_prompt_constraints(pc: Any, where: str) -> Tuple[int, int, List[str]]:
    if not isinstance(pc, dict):
        raise WaveContractError(f"{where}: prompt_constraints must be an object")
    min_chars = pc.get("min_chars", DEFAULT_MIN_CHARS)
    max_chars = pc.get("max_chars", DEFAULT_MAX_CHARS)
    if isinstance(min_chars, bool) or not isinstance(min_chars, int) or min_chars < 1:
        raise WaveContractError(
            f"{where}: prompt_constraints.min_chars must be a positive integer")
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
        raise WaveContractError(
            f"{where}: prompt_constraints.max_chars must be a positive integer")
    if max_chars <= min_chars:
        raise WaveContractError(
            f"{where}: prompt_constraints.max_chars ({max_chars}) must exceed "
            f"min_chars ({min_chars})")
    blocks = pc.get("required_blocks")
    if not isinstance(blocks, list) or not blocks or \
            not all(isinstance(b, str) and b.strip() for b in blocks):
        raise WaveContractError(
            f"{where}: prompt_constraints.required_blocks must be a non-empty "
            "array of non-empty strings")
    return min_chars, max_chars, list(blocks)


def _check_slides(slides: Any, where: str) -> List[Dict[str, Any]]:
    if not isinstance(slides, list) or not slides:
        raise WaveContractError(f"{where}: slides must be a non-empty array")
    seen_ids: set = set()
    seen_ordinals: set = set()
    for idx, slide in enumerate(slides):
        s_where = f"{where}: slides[{idx}]"
        if not isinstance(slide, dict):
            raise WaveContractError(f"{s_where}: each slide must be an object")
        slide_id = slide.get("slide_id")
        if not isinstance(slide_id, str) or not slide_id.strip():
            raise WaveContractError(
                f"{s_where}: slide_id must be a non-empty string")
        ordinal = slide.get("ordinal")
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
            raise WaveContractError(
                f"{s_where}: ordinal must be an integer >= 1 (got {ordinal!r})")
        copy = slide.get("copy")
        if not isinstance(copy, list) or not all(isinstance(c, str) for c in copy):
            raise WaveContractError(f"{s_where}: copy must be an array of strings")
        if not isinstance(slide.get("archetype"), str):
            raise WaveContractError(f"{s_where}: archetype must be a string")
        anchors = slide.get("research_anchors")
        if not isinstance(anchors, list) or \
                not all(isinstance(a, str) for a in anchors):
            raise WaveContractError(
                f"{s_where}: research_anchors must be an array of strings")
        if not isinstance(slide.get("design_tokens"), dict):
            raise WaveContractError(f"{s_where}: design_tokens must be an object")
        negs = slide.get("negative_requirements")
        if not isinstance(negs, list) or not all(isinstance(n, str) for n in negs):
            raise WaveContractError(
                f"{s_where}: negative_requirements must be an array of strings")
        if slide_id in seen_ids:
            raise WaveContractError(f"{s_where}: duplicate slide_id {slide_id!r}")
        if ordinal in seen_ordinals:
            raise WaveContractError(f"{s_where}: duplicate ordinal {ordinal}")
        seen_ids.add(slide_id)
        seen_ordinals.add(ordinal)
    return [dict(s) for s in slides]


def validate_input(data: Any, source: str) -> Dict[str, Any]:
    """Whole-input reject gate for the P4-PROMPT wave input. FIX 104: this is
    the ONE validator -- the worker delegates here and its old hand-built
    whitelist is gone. Same reject messages, same normalized shape.

    FIX 104 no-loss rule: the returned dict is the INPUT with checked fields
    type-normalized -- every key present on input is present on output,
    including any key this validator does not know about. Nothing is
    hand-enumerated out."""
    if not isinstance(data, dict):
        raise WaveContractError(f"{source}: input must be a JSON object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise WaveContractError(
            f"{source}: unsupported schema_version {data.get('schema_version')!r} "
            f"(this worker speaks version {SCHEMA_VERSION} only)")
    run_id = data.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise WaveContractError(f"{source}: run_id must be a non-empty string")
    run_dir_raw = data.get("run_dir")
    if not isinstance(run_dir_raw, str) or not run_dir_raw.strip():
        raise WaveContractError(f"{source}: run_dir must be a non-empty string")
    if not Path(run_dir_raw).expanduser().is_absolute():
        raise WaveContractError(
            f"{source}: run_dir must be an ABSOLUTE path (got {run_dir_raw!r})")
    if data.get("phase_id") != PHASE_ID:
        raise WaveContractError(
            f"{source}: phase_id must be {PHASE_ID!r} (got {data.get('phase_id')!r})")

    routing = data.get("routing")
    _check_routing(routing, source)
    min_chars, max_chars, blocks = _check_prompt_constraints(
        data.get("prompt_constraints"), source)

    # F42/F104: owning_role optional on older callers, but when present it
    # MUST be a non-empty string -- and it MUST survive into the output.
    owning_role = data.get("owning_role")
    if owning_role is not None and (
            not isinstance(owning_role, str) or not owning_role.strip()):
        raise WaveContractError(f"{source}: owning_role must be a non-empty string")

    normalized_slides = _check_slides(data.get("slides"), source)

    # Build the normalized output by IDENTITY-PRESERVING copy: start from the
    # input itself, then overwrite only the fields that need normalization.
    # Any field the stamp grew (route_reason, capacity_status, a future F-fix
    # field) rides through untouched -- the F41/F42 class of silent loss is
    # impossible by construction.
    out: Dict[str, Any] = dict(data)
    out["schema_version"] = SCHEMA_VERSION
    out["run_id"] = run_id
    out["run_dir"] = str(Path(run_dir_raw).expanduser())
    out["phase_id"] = PHASE_ID
    out["owning_role"] = owning_role
    out["routing"] = dict(routing)
    out["prompt_constraints"] = {
        **{k: v for k, v in (data.get("prompt_constraints") or {}).items()
           if isinstance(data.get("prompt_constraints"), dict)},
        "min_chars": min_chars,
        "max_chars": max_chars,
        "required_blocks": blocks,
    }
    out["slides"] = normalized_slides
    return out


def wave_contract_field_names() -> Tuple[str, ...]:
    """Introspection seam for tests/audits: the exact field names the
    WaveContract dataclass carries."""
    return tuple(f.name for f in fields(WaveContract))
