"""SLICE 1 GATE CONVERSION — the 18 highest-risk gates moved to the verifier pattern.

TRUST BOUNDARY, INCREMENT 2 (gate-conversion slice 1). Every gate in SLICE_1_GATES
is the CONVERSION of one build_deck._chk_* preflight gate. A converted gate:

  * RE-MEASURES the REAL artifact — the verifier re-derives the exact rubric the
    legacy gate enforced (never trusts a self-written report, never trusts a flag
    the producer wrote for itself);
  * records a SEALED RunFacts record (via presentation_job.runfacts.seal);
  * returns pass/fail naming the EXACT discrepancy on failure;
  * preserves the legacy defer semantics VERBATIM — a gate DEFERS (report-only
    PASS, exactly what the legacy `return ""` meant) ONLY when its input
    genuinely does not exist yet (D10: pre-phase ordering, or an upstream gate
    owns the absence), never when the input exists but is wrong;
  * shadow-compares against the legacy _chk_* function in report-only mode —
    PRES_TRUST_BOUNDARY_ENFORCE=1 makes the sealed verdict authoritative;
  * NEVER weakens a waiver path (owner_skip_approval for AF-DECK-TYPE-UNSET /
    AF-MODE-UNSET / AF-STYLE-UNPICKED / AF-STYLE-DOUBLECHARGE / AF-PRIORITY-SHIFT)
    and NEVER weakens the fail-closed paths (SP intake-trace ABSENT transcript).

WHY the verifier reads the SAME files the legacy gate reads: the seal() front
door (process_manifest.json + the six QC reports) does not carry these gates'
inputs (slides_copy.md, arc_allocation.json, renders/*.png, sp_intake.json,
intake_transcript.json, source_brief.md, ...), so the verifier seals the generic
RunFacts AND captures the gate's own inputs into a snapshot dict carried on the
RunFacts subclass. The verdict functions are then PURE over that snapshot —
they contain no I/O and are unit-testable without touching disk. Every verdict
re-derives the exact legacy rubric from the captured raw values (lowercased
copy, arc token blob, figure claims, style-preview choice, per-slide PNG
vividness proxy, SP intake/ledger/transcript shapes, priority-shift ledger rows).

GATE NAMES (registered with the verifier_registry, runnable via run_gate):
  slice1:deck_type            AF-DECK-TYPE-UNSET
  slice1:mode                 AF-MODE-UNSET
  slice1:priority_shift       AF-NO-SHIFT
  slice1:priority_stack       AF-NO-PRIORITY-STACK
  slice1:rerank               AF-NO-RERANK
  slice1:trigger              AF-NO-TRIGGER
  slice1:proclamation_hedge   AF-PROCLAMATION-HEDGE
  slice1:peak_end             AF-PEAK-END
  slice1:salience_apex        AF-NO-SALIENCE-APEX
  slice1:converter_no_invent  AF-CONVERTER-NO-INVENT
  slice1:persuasion_beats     AF-NO-PROBLEM/... (persuasion taxonomy)
  slice1:style_preview        AF-STYLE-UNPICKED / AF-STYLE-DOUBLECHARGE
  slice1:priority_shift_ledger AF-PRIORITY-SHIFT (14-item ship gate + report write)
  slice1:sp_intake            P-SP-INTAKE (prove_sp_intake)
  slice1:sp_structure         P-SP-STRUCTURE (prove_sp_structure)
  slice1:sp_no_pitch          P-SP-P3-HYGIENE (prove_sp_no_pitch)
  slice1:sp_intake_trace      P-SP-INTAKE-TRACE (intake_trace_check)
  slice1:sp_claim             P-SP-CLAIM (prove_sp_routing)

Stdlib only. No third-party imports. This module is additive: build_deck.py,
runfacts.py and verifier_registry.py are NOT modified.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from presentation_job import runfacts as _rf

# ---------------------------------------------------------------------------
# Re-exports — slices import ONE module for the machinery
# ---------------------------------------------------------------------------
RunFacts = _rf.RunFacts
Fact = _rf.Fact
Epistemic = _rf.Epistemic
Verdict = _rf.Verdict
RunFactsError = _rf.RunFactsError
seal = _rf.seal
reset_cache_for_tests = _rf.reset_cache_for_tests
shadow_compare = _rf.shadow_compare
enforcing = _rf.enforcing

from verifier_registry import (  # noqa: E402
    VerifierSpec,
    register_verifier,
    get_verifier,
    known_gates,
    run_gate,
    both_directions,
    write_fixture,
    _resolve_first,
)

# ---------------------------------------------------------------------------
# Import the legacy gate engine + constants (read-only; nothing here writes to
# build_deck, and no build_deck module-level side effect runs on import).
# ---------------------------------------------------------------------------
import build_deck as _bd  # noqa: E402

# ---------------------------------------------------------------------------
# The slice-1 sealed facts record: RunFacts + the gates' own captured inputs.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SliceFacts(RunFacts):
    """RunFacts plus the raw snapshot the slice-1 verdict functions read.

    The base RunFacts is what presentation_job.runfacts.seal() returns (a frozen
    dataclass); this subclass carries the gate inputs as an opaque Fact[dict].
    The verdict functions are pure over this snapshot — they never touch disk.

    snapshot keys (all lowercased text / parsed objects / measured values):
      intake_obj       parsed working/copy/intake.json dict (or None)
      priority_spec    parsed working/copy/priority_shift_spec.json dict (or None)
      slides_copy_lc   lowercased slides_copy.md text (or None)
      arc_blob         lowercased arc-allocation token blob (or None)
      apex_ordinal     OFFER/PROMISE-APEX slide ordinal (or None)
      render_pngs      sorted [(ordinal, rel_path)] for rendered slide PNGs (or [])
      flatfill         {rel_path: (dominant_fraction, rgb)} for the render PNGs
      style_manifest   parsed style_samples_manifest.json (or None)
      style_choice     parsed style_preview_choice.json (or None)
      source_brief     text of the first source brief found (or None)
      source_text      concatenated raw source text (or None)
      sp_intake        parsed working/copy/sp_intake.json (or None)
      sp_structure     parsed working/copy/sp_structure.json (or None)
      sp_transcript    raw text of working/interview/intake_transcript.json (or None)
      sp_transcript_path_abs  absolute path of the transcript (or None)
      af_skip          {af_code: legacy-owner-skip-approved bool} — evaluated the
                       SAME way build_deck._owner_skip_approved evaluates (the
                       sealed RunFacts.owner_skip_records is the authoritative
                       shadow); used only by the verdict functions that waive.
      png_provider     "measure" when _png_flatfill_fraction ran, else "unavailable"
    """

    snapshot: Fact = field(default_factory=lambda: Fact.absent("slice1 snapshot unset"))


# ---------------------------------------------------------------------------
# File-read helpers (the verifier front door — the ONLY place slice 1 reads
# disk; the verdicts are pure over the snapshot).
# ---------------------------------------------------------------------------
def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 — unparseable == absent for the rubric
        return None


def _first_existing(run_dir: Path, rels: Tuple[str, ...]) -> Optional[Path]:
    for rel in rels:
        p = run_dir / rel
        if p.exists():
            return p
    return None


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def _first_marker_offset(text_lc: str, markers: Tuple[str, ...]) -> Optional[int]:
    best = None
    for m in markers:
        idx = text_lc.find(m.lower())
        if idx >= 0 and (best is None or idx < best):
            best = idx
    return best


def _png_ordinal(path: Path) -> Optional[int]:
    m = re.search(r"(\d+)", path.stem)
    return int(m.group(1)) if m else None


def _capture_owner_skip(run_dir: Path, af_codes: Tuple[str, ...]) -> Dict[str, bool]:
    """Legacy owner-skip evaluation for the waivable slice-1 codes. Mirrors
    build_deck._owner_skip_approved (the sealed verify_owner_skip is the
    authoritative shadow; this is the report-only value the verdicts use)."""
    out: Dict[str, bool] = {}
    for code in af_codes:
        try:
            out[code] = bool(_bd._owner_skip_approved(run_dir, code))
        except Exception:  # noqa: BLE001
            out[code] = False
    return out


_ARC_RELS = ("working/copy/arc_allocation.json", "arc_allocation.json",
             "working/arc_allocation.json")
_INTK_RELS = ("working/copy/intake.json", "intake.json", "working/intake.json")
_SPEC_RELS = ("working/copy/priority_shift_spec.json", "priority_shift_spec.json",
              "working/priority_shift_spec.json")
_COPY_RELS = ("working/copy/slides_copy.md", "slides_copy.md",
              "working/slides_copy.md")
_BRIEF_RELS = ("working/copy/source_brief.md", "working/copy/source_brief.json",
               "working/converter/source_brief.md", "working/copy/source_brief.txt")
_SRC_RELS = ("working/source/transcript.txt", "working/converter/source.txt",
             "working/copy/source_raw.txt")

_STYLE_MANIFEST_REL = "working/style-preview/style_samples_manifest.json"
_STYLE_CHOICE_REL = "working/copy/style_preview_choice.json"
_SP_INTK_REL = "working/copy/sp_intake.json"
_SP_STRUCT_REL = "working/copy/sp_structure.json"
_SP_TRANSCRIPT_REL = "working/interview/intake_transcript.json"
_SHIFT_REPORT_REL = "working/qc/priority_shift_report.json"


def _build_snapshot(run_dir: Path) -> dict:
    """Capture every slice-1 gate input from disk (the verifier front door)."""
    rd = Path(run_dir)
    snap: Dict[str, Any] = {}

    intk_p = _first_existing(rd, _INTK_RELS)
    snap["intake_obj"] = _read_json(intk_p) if intk_p else None

    spec_p = _first_existing(rd, _SPEC_RELS)
    snap["priority_spec"] = _read_json(spec_p) if spec_p else None

    copy_p = _first_existing(rd, _COPY_RELS)
    snap["slides_copy_lc"] = copy_p.read_text(errors="replace").lower() if copy_p else None

    arc_p = _first_existing(rd, _ARC_RELS)
    snap["arc_blob"] = None
    if arc_p:
        arc_obj = _read_json(arc_p)
        if isinstance(arc_obj, list) or (isinstance(arc_obj, dict)
                                         and "__parse_error__" not in arc_obj):
            slots = (arc_obj if isinstance(arc_obj, list) else
                     (arc_obj.get("slots") or arc_obj.get("allocation")
                      or arc_obj.get("slides") or []))
            tokens: List[str] = []
            for s in slots if isinstance(slots, list) else []:
                if isinstance(s, dict):
                    for k in ("arc_section", "section", "beat", "tag", "type", "role"):
                        v = s.get(k)
                        if isinstance(v, str):
                            tokens.append(v.lower())
                    tags = s.get("tags")
                    if isinstance(tags, list):
                        tokens += [str(t).lower() for t in tags]
                elif isinstance(s, str):
                    tokens.append(s.lower())
            snap["arc_blob"] = " ".join(tokens)
        elif isinstance(arc_obj, dict) and "__parse_error__" in arc_obj:
            snap["arc_blob"] = "__parse_error__"

    snap["apex_ordinal"] = _bd._apex_slide_ordinal(rd)

    pngs: List[Tuple[Optional[int], str]] = []
    flatfill: Dict[str, Tuple[Optional[float], Any]] = {}
    for p in _bd._gather_rendered_pngs(rd):
        ordn = _png_ordinal(p)
        pngs.append((ordn, str(p)))
        if ordn is None:
            continue
        frac, rgb = _bd._png_flatfill_fraction(p)
        flatfill[str(p)] = (frac, rgb)
    snap["render_pngs"] = pngs
    snap["flatfill"] = flatfill
    snap["png_provider"] = ("measure" if flatfill else "unavailable")

    sm_p = rd / _STYLE_MANIFEST_REL
    snap["style_manifest"] = _read_json(sm_p) if sm_p.exists() else None
    sc_p = rd / _STYLE_CHOICE_REL
    snap["style_choice"] = _read_json(sc_p) if sc_p.exists() else None

    brief_p = _first_existing(rd, _BRIEF_RELS)
    snap["source_brief"] = brief_p.read_text(errors="replace") if brief_p else None

    source_parts: List[str] = []
    for rel in _SRC_RELS:
        p = rd / rel
        if p.exists():
            source_parts.append(p.read_text(errors="replace"))
    src_dir = rd / "working" / "source"
    if src_dir.is_dir():
        for pattern in ("*.txt", "*.md"):
            for p in sorted(src_dir.glob(pattern)):
                if p.exists():
                    source_parts.append(p.read_text(errors="replace"))
    snap["source_text"] = "\n".join(source_parts) if source_parts else None

    sp_intk_p = rd / _SP_INTK_REL
    snap["sp_intake"] = _read_json(sp_intk_p) if sp_intk_p.exists() else None
    sp_struct_p = rd / _SP_STRUCT_REL
    snap["sp_structure"] = _read_json(sp_struct_p) if sp_struct_p.exists() else None
    sp_tr_p = rd / _SP_TRANSCRIPT_REL
    snap["sp_transcript"] = (sp_tr_p.read_text(encoding="utf-8", errors="replace")
                             if sp_tr_p.is_file() else None)
    snap["sp_transcript_path_abs"] = str(sp_tr_p) if sp_tr_p.is_file() else None

    snap["af_skip"] = _capture_owner_skip(rd, (
        "AF-DECK-TYPE-UNSET", "AF-MODE-UNSET", "AF-STYLE-UNPICKED",
        "AF-STYLE-DOUBLECHARGE", "AF-PRIORITY-SHIFT"))

    snap["_run_dir"] = str(rd)
    return snap


_SNAPSHOT_REQUIRED = (
    "intake_obj", "priority_spec", "slides_copy_lc", "arc_blob", "apex_ordinal",
    "render_pngs", "flatfill", "style_manifest", "style_choice", "source_brief",
    "source_text", "sp_intake", "sp_structure", "sp_transcript", "af_skip",
)


# ---------------------------------------------------------------------------
# Verifier factory: seal RunFacts + capture the snapshot in one transaction.
# ---------------------------------------------------------------------------
def _legacy_str_ok(legacy: Callable) -> Callable:
    """Adapt a legacy build_deck _chk_* function (run_dir) -> str to the
    (run_dir) -> (ok, reasons) contract VerifierSpec.run_verifier expects for
    shadow-compare. '' is PASS; any non-empty str is a FAIL with that reason."""
    def _adapted(run_dir: Path):
        reason = legacy(Path(run_dir))
        if not reason:
            return True, []
        return False, [reason]
    return _adapted


def _slice_verifier(gate: str, artifacts: Tuple[str, ...],
                    verdict_fn: Callable[[SliceFacts], Tuple[Verdict, str]],
                    legacy: Optional[Callable] = None) -> VerifierSpec:
    """Build a VerifierSpec for a slice-1 gate. The verifier seals the generic
    RunFacts (process_manifest + QC reports + owner_skip_records — the shared
    front door) and attaches the gate-input snapshot. had_input is True when at
    least one declared artifact path exists (a wholly-absent artifact set is
    fail-closed by the base run_verifier, exactly like the QC-report gates).
    `legacy` is a build_deck _chk_* str-returning function; it is adapted to
    the (ok, reasons) shape for the report-only shadow compare."""

    def _v(artifact_paths: Tuple[str, ...], run_dir: Path,
           config: Optional[dict]) -> Tuple[SliceFacts, bool]:
        facts = seal(Path(run_dir), nonce_bound=False, force=True)
        snap = _build_snapshot(Path(run_dir))
        # The slice-1 verdicts decide ABSENCE semantics per gate (defer / pass /
        # fail-closed) from the captured snapshot — they never delegate absence to
        # the base run_verifier's hard fail-closed, which is too coarse for gates
        # whose input is genuinely optional (e.g. P-SP-CLAIM runs for EVERY deck
        # and passes a no-signal deck; P-SP-INTAKE-TRACE fails an absent
        # transcript). had_input is therefore always True here: the verdict owns
        # the outcome, exactly as the legacy _chk_* functions did.
        snapshot_fact = Fact.known("slice1 gate snapshot", snap)
        slice_facts = SliceFacts(
            run_dir=facts.run_dir,
            sealed_at=facts.sealed_at,
            schema_version=facts.schema_version,
            nonce_bound=facts.nonce_bound,
            process_manifest=facts.process_manifest,
            owner_skip_records=facts.owner_skip_records,
            qc=facts.qc,
            snapshot=snapshot_fact,
        )
        return slice_facts, True

    return VerifierSpec(
        gate=gate,
        verifier=_v,
        verdict=verdict_fn,
        artifacts=artifacts,
        legacy=_legacy_str_ok(legacy) if legacy is not None else None,
        config=None,
    )


def _snap(facts: SliceFacts) -> dict:
    """The snapshot dict, or {} when the seal did not attach one (defensive)."""
    if facts.snapshot.state is Epistemic.KNOWN and isinstance(facts.snapshot.value, dict):
        return facts.snapshot.value
    return {}


def _waived(snap: dict, code: str) -> bool:
    return bool((snap.get("af_skip") or {}).get(code))


# ---------------------------------------------------------------------------
# Warn-window machinery (U021 / U022): report-only deferral inside the dated
# migration window, kept byte-identical to the legacy gates' semantics.
# ---------------------------------------------------------------------------
def _warn_mode_deck_type(snap: dict, reason: str) -> Tuple[Verdict, str]:
    if _bd.DECK_TYPE_GATE_STAGE != "enforce":
        overdue = "" if date.today() <= _bd.MIGRATION_WINDOW_UNTIL else \
            " [WINDOW CLOSED -- the enforce unit is overdue]"
        print("  WARN  " + reason + " [warn-mode until "
              + _bd.MIGRATION_WINDOW_UNTIL.isoformat() + "]" + overdue,
              file=sys.stderr)
        return Verdict.PASS, ""
    return Verdict.FAIL, reason


def _warn_mode_mode(snap: dict, reason: str) -> Tuple[Verdict, str]:
    if date.today() <= _bd.MIGRATION_WINDOW_UNTIL:
        print("  WARN  AF-MODE-UNSET: intake.json.creation_mode is unset and no "
              "priority_shift_spec.json is present. This deck is exempt only until "
              + _bd.MIGRATION_WINDOW_UNTIL.isoformat() + "; after that an unset mode "
              "blocks the build (SOP-MODE-00, P118).", file=sys.stderr)
        return Verdict.PASS, ""
    return Verdict.FAIL, reason


# ---------------------------------------------------------------------------
# Verdict functions — PURE over the snapshot. Each re-derives the EXACT rubric
# of the legacy gate, naming the exact discrepancy on failure.
# ---------------------------------------------------------------------------
def v_deck_type(facts: SliceFacts) -> Tuple[Verdict, str]:
    """AF-DECK-TYPE-UNSET — intake.json.deck_type must be one of DECK_TYPES."""
    snap = _snap(facts)
    intake = snap.get("intake_obj")
    if not isinstance(intake, dict):
        return Verdict.PASS, ""  # absence is _chk_intake's, fail-closed there.
    declared = str(intake.get("deck_type") or "").strip()
    if declared in _bd.DECK_TYPES:
        return Verdict.PASS, ""
    reason = (f"AF-DECK-TYPE-UNSET: intake.json.deck_type is "
              f"{declared or 'unset'!r}; it must be one of {', '.join(_bd.DECK_TYPES)}. "
              f"deck_type is written by deck-intake-driver.py's "
              f"derive_legacy_fields() from the ONE presentation_type answer -- it is "
              f"never hand-typed. An unset deck_type makes _sp_active defer, so every "
              f"signature-presentation gate silently no-ops (SOP-MODE-00 / P-SP-CLAIM).")
    if _waived(snap, "AF-DECK-TYPE-UNSET"):
        return Verdict.PASS, ""
    return _warn_mode_deck_type(snap, reason)


def v_mode(facts: SliceFacts) -> Tuple[Verdict, str]:
    """AF-MODE-UNSET — creation_mode in CREATION_MODES; content modes need
    extracted_substance/source provenance."""
    snap = _snap(facts)
    intake = snap.get("intake_obj")
    if not isinstance(intake, dict):
        return Verdict.PASS, ""  # no intake — upstream gates own absence.
    mode = str(intake.get("creation_mode") or "").strip().lower()
    if not mode and snap.get("priority_spec") is None:
        if _waived(snap, "AF-MODE-UNSET"):
            return Verdict.PASS, ""
        if date.today() <= _bd.MIGRATION_WINDOW_UNTIL:
            print("  WARN  AF-MODE-UNSET: intake.json.creation_mode is unset and no "
                  "priority_shift_spec.json is present. This deck is exempt only until "
                  + _bd.MIGRATION_WINDOW_UNTIL.isoformat() + "; after that an unset mode "
                  "blocks the build (SOP-MODE-00, P118).", file=sys.stderr)
            return Verdict.PASS, ""
        # fall through — the CREATION_MODES check now blocks.
    if mode not in _bd.CREATION_MODES:
        return Verdict.FAIL, (f"AF-MODE-UNSET: intake.json.creation_mode is "
                              f"{mode or 'unset'!r}; it must be one of "
                              f"{', '.join(_bd.CREATION_MODES)}. Step Zero of every deck "
                              f"is to identify the creation mode before any content is "
                              f"built (SOP-MODE-00, P118).")
    if mode in ("content_personal", "content_general"):
        substance = intake.get("extracted_substance") or intake.get("source_brief_origin")
        if not substance:
            return Verdict.FAIL, (f"AF-MODE-UNSET: creation_mode {mode!r} is a content "
                                  f"mode but no extracted_substance / source provenance "
                                  f"is recorded -- a content-mode deck must diagnose and "
                                  f"extract the source first (SOP-MODE-00, P22-P29).")
    return Verdict.PASS, ""


def v_priority_shift(facts: SliceFacts) -> Tuple[Verdict, str]:
    """AF-NO-SHIFT — the priority-shift SPINE gate: spec true_goal + named
    priority_stack[] + >=5/8 build-move tags monotonic in slides_copy.md."""
    snap = _snap(facts)
    if snap.get("priority_spec") is None:
        return Verdict.PASS, ""  # doctrine inactive — defer.
    spec = snap["priority_spec"] or {}
    problems: List[str] = []
    if not str(spec.get("true_goal") or "").strip():
        problems.append("priority_shift_spec.json has no true_goal (the destination shift)")
    stack = spec.get("priority_stack")
    if not (isinstance(stack, list) and len(stack) >= 1):
        problems.append("priority_shift_spec.json has an empty priority_stack[] "
                        "(the audience's current ranking must be surfaced)")
    text = snap.get("slides_copy_lc")
    if text:
        present = [(tag, text.find(tag.lower())) for tag in _bd.EIGHT_MOVE_TAGS
                   if text.find(tag.lower()) >= 0]
        if len(present) < 5:
            problems.append(f"only {len(present)}/8 build-move beat tags are present in "
                            f"slides_copy.md (need >=5 of {', '.join(_bd.EIGHT_MOVE_TAGS)})")
        else:
            offs = [o for _, o in present]
            if offs != sorted(offs):
                problems.append("the build-move beat tags are out of canonical order -- "
                                "the eight moves must run monotonically (P141-P150)")
    if problems:
        return Verdict.FAIL, ("AF-NO-SHIFT: the deck does not engineer a deliberate "
                              "priority shift -- " + "; ".join(problems) + ". Re-rank the "
                              "owner's offer/idea to the top of the audience's priority "
                              "stack (SOP-NORTHSTAR-00 / SOP-PRIORITY-02).")
    return Verdict.PASS, ""


def v_priority_stack(facts: SliceFacts) -> Tuple[Verdict, str]:
    """AF-NO-PRIORITY-STACK — stack named before the first ladder beat."""
    snap = _snap(facts)
    if snap.get("priority_spec") is None:
        return Verdict.PASS, ""
    text = snap.get("slides_copy_lc")
    if not text:
        return Verdict.PASS, ""
    ladder = _first_marker_offset(text, _bd.LADDER_BEAT_MARKERS)
    if ladder is None:
        return Verdict.PASS, ""  # no ladder beat yet — nothing to order against.
    stack = _first_marker_offset(text, _bd.PRIORITY_STACK_MARKERS)
    if stack is None or stack > ladder:
        return Verdict.FAIL, ("AF-NO-PRIORITY-STACK: Move 1 is missing -- the deck must "
                              "surface the audience's current priority stack BEFORE the "
                              "first value/price ladder beat (P142, SOP-PRIORITY-02).")
    return Verdict.PASS, ""


def v_rerank(facts: SliceFacts) -> Tuple[Verdict, str]:
    """AF-NO-RERANK — after PRICE, the deck demands the re-rank out loud."""
    snap = _snap(facts)
    if snap.get("priority_spec") is None:
        return Verdict.PASS, ""
    intake = snap.get("intake_obj")
    pitch = intake.get("pitch_included") if isinstance(intake, dict) else None
    if pitch is not True:
        return Verdict.PASS, ""
    text = snap.get("slides_copy_lc")
    if not text:
        return Verdict.PASS, ""
    price = text.find("price")
    if price < 0:
        return Verdict.PASS, ""
    rerank = _first_marker_offset(text, _bd.RERANK_MARKERS)
    if rerank is None or rerank <= price:
        return Verdict.FAIL, ("AF-NO-RERANK: Move 7 is missing -- after the PRICE the "
                              "deck must demand the re-rank out loud (make the owner's "
                              "thing the audience's new #1) (P148).")
    return Verdict.PASS, ""


def v_trigger(facts: SliceFacts) -> Tuple[Verdict, str]:
    """AF-NO-TRIGGER — the CTA fires a time-bound trigger."""
    snap = _snap(facts)
    if snap.get("priority_spec") is None:
        return Verdict.PASS, ""
    intake = snap.get("intake_obj")
    pitch = intake.get("pitch_included") if isinstance(intake, dict) else None
    if pitch is not True:
        return Verdict.PASS, ""
    text = snap.get("slides_copy_lc")
    if not text:
        return Verdict.PASS, ""
    if _first_marker_offset(text, _bd.TRIGGER_MARKERS) is not None:
        return Verdict.PASS, ""
    return Verdict.FAIL, ("AF-NO-TRIGGER: Move 8 is missing -- the CTA carries no "
                          "time-bound trigger (deadline / scarcity window / act-now). "
                          "A priority that is not acted on now is not yet a priority "
                          "(P149).")


def v_proclamation_hedge(facts: SliceFacts) -> Tuple[Verdict, str]:
    """AF-PROCLAMATION-HEDGE — proclamations plain, bold, hedge-free."""
    snap = _snap(facts)
    if snap.get("priority_spec") is None:
        return Verdict.PASS, ""
    text = snap.get("slides_copy_lc")
    if not text:
        return Verdict.PASS, ""
    hits = [t for t in _bd.PROCLAMATION_HEDGE_TOKENS if t in text]
    if hits:
        return Verdict.FAIL, ("AF-PROCLAMATION-HEDGE: the copy hedges its declarations "
                              "with " + ", ".join(repr(h) for h in hits[:5]) + ". A "
                              "proclamation is a plain, bold claim of truth that dares to "
                              "challenge the norm -- strip the hedge "
                              "(SOP-PROCLAMATION-01, P109).")
    return Verdict.PASS, ""


def v_peak_end(facts: SliceFacts) -> Tuple[Verdict, str]:
    """AF-PEAK-END — the arc declares a PEAK beat AND an ENDING beat."""
    snap = _snap(facts)
    if snap.get("priority_spec") is None:
        return Verdict.PASS, ""
    blob = snap.get("arc_blob")
    if blob is None:
        return Verdict.PASS, ""  # no arc yet — _chk_arc owns absence.
    if blob == "__parse_error__":
        return Verdict.FAIL, ("AF-PEAK-END: arc_allocation.json is not valid JSON, so "
                              "the engineered PEAK + ending cannot be proven (P49).")
    missing: List[str] = []
    if not any(t in blob for t in _bd.PEAK_TAGS):
        missing.append("no PEAK/APEX/WOW beat")
    if not any(t in blob for t in _bd.ENDING_TAGS):
        missing.append("no deliberate ending/recap/CTA beat")
    if missing:
        return Verdict.FAIL, ("AF-PEAK-END: the arc fails the peak-end rule -- "
                              + "; ".join(missing) + ". Engineer a deliberate peak and "
                              "a deliberate ending; a flat ending is remembered as flat "
                              "(P49, SOP-NORTHSTAR-00).")
    return Verdict.PASS, ""


def v_salience_apex(facts: SliceFacts) -> Tuple[Verdict, str]:
    """AF-NO-SALIENCE-APEX — the OFFER/PROMISE-APEX slide is the single most vivid
    (von Restorff). Vividness proxy = 1 - dominant-colour fraction, reusing the
    AF-VISUAL-VARIETY pixel data."""
    snap = _snap(facts)
    if snap.get("priority_spec") is None:
        return Verdict.PASS, ""
    pngs = snap.get("render_pngs") or []
    if not pngs:
        return Verdict.PASS, ""  # pre-render — defer.
    apex = snap.get("apex_ordinal")
    if apex is None:
        return Verdict.PASS, ""  # apex undeterminable — AF-PEAK-END owns that absence.
    scores: Dict[int, float] = {}
    for ordn, rel in pngs:
        if ordn is None:
            continue
        frac, _rgb = (snap.get("flatfill") or {}).get(rel, (None, None))
        if frac is None:
            continue
        scores[ordn] = 1.0 - float(frac)
    if apex not in scores or len(scores) < 3:
        return Verdict.PASS, ""  # apex not rendered yet, or too few measurable slides.
    deck_max = max(scores.values())
    if deck_max <= 0:
        return Verdict.PASS, ""
    if scores[apex] < 0.85 * deck_max:
        return Verdict.FAIL, (f"AF-NO-SALIENCE-APEX: the OFFER/PROMISE-APEX slide "
                              f"(slide {apex}) is not the most vivid element in the deck "
                              f"(vividness {scores[apex]:.2f} vs deck peak "
                              f"{deck_max:.2f}). The owner's thing must be the single "
                              f"most vivid thing in the room by the end "
                              f"(von Restorff, P48/P155).")
    return Verdict.PASS, ""


def v_converter_no_invent(facts: SliceFacts) -> Tuple[Verdict, str]:
    """AF-CONVERTER-NO-INVENT — every figure in the source brief traces to the raw
    source (digit-only match)."""
    snap = _snap(facts)
    brief_text = snap.get("source_brief")
    if brief_text is None:
        return Verdict.PASS, ""  # no converter brief — defer.
    source_text = snap.get("source_text")
    if not source_text:
        return Verdict.PASS, ""  # raw source not on disk to compare against — defer.
    source_norm = _norm_ws(source_text.lower())
    claim_re = re.compile(r"\b\d[\d,\.]*\s?%|\$\s?\d[\d,\.]*|\b\d{2,}[\d,\.]*\b")
    invented: List[str] = []
    for m in claim_re.findall(brief_text):
        tok = _norm_ws(str(m).lower()).replace(" ", "")
        digits = re.sub(r"[^\d]", "", tok)
        if not digits:
            continue
        if digits not in re.sub(r"[^\d]", "", source_norm):
            invented.append(str(m).strip())
    invented = sorted(set(invented))[:6]
    if invented:
        return Verdict.FAIL, ("AF-CONVERTER-NO-INVENT: the source brief carries "
                              "figure(s) absent from the raw source: "
                              + ", ".join(invented) + ". Extract, never invent -- a "
                              "converter deck may only use claims the source actually "
                              "makes (P167d).")
    return Verdict.PASS, ""


def v_persuasion_beats(facts: SliceFacts) -> Tuple[Verdict, str]:
    """HOLE C — a doctrine-active pitch deck carries every named persuasion beat."""
    snap = _snap(facts)
    if snap.get("priority_spec") is None:
        return Verdict.PASS, ""
    intake = snap.get("intake_obj")
    pitch = intake.get("pitch_included") if isinstance(intake, dict) else None
    if pitch is not True:
        return Verdict.PASS, ""
    text = snap.get("slides_copy_lc")
    if not text:
        return Verdict.PASS, ""
    missing = []
    for code, markers in _bd.PERSUASION_BEAT_MARKERS.items():
        if _first_marker_offset(text, markers) is None:
            missing.append(code)
    if missing:
        return Verdict.FAIL, ("the deck is missing the named persuasion beat(s) "
                              + ", ".join(missing) + " -- every converting deck must "
                              "name the problem, present a choice/fork, draw a "
                              "comparison, cite a measurable result, carry expert "
                              "proof, and show a before/after (SOP-PITCH-06 / "
                              "SOP-ENGINE-00 persuasion-beat taxonomy).")
    return Verdict.PASS, ""


def v_style_preview(facts: SliceFacts) -> Tuple[Verdict, str]:
    """AF-STYLE-UNPICKED + AF-STYLE-DOUBLECHARGE — the approved 3-style-preview
    gate (P-STYLE-PREVIEW, order 4.85)."""
    snap = _snap(facts)
    sm = snap.get("style_manifest")
    if sm is None:
        return Verdict.PASS, ""  # style-preview phase not run — defer.
    choice = snap.get("style_choice")
    valid_pick = (isinstance(choice, dict)
                  and choice.get("owner_approved") is True
                  and str(choice.get("chosen_variant") or "").strip())
    if not valid_pick:
        if _waived(snap, "AF-STYLE-UNPICKED"):
            return Verdict.PASS, ""
        return Verdict.FAIL, ("AF-STYLE-UNPICKED: 9 style samples were rendered but the "
                              "owner has not picked a winning variant "
                              "(working/copy/style_preview_choice.json must carry "
                              "owner_approved:true + chosen_variant). The full deck must "
                              "NOT render until the owner chooses A/B/C via their OWN "
                              "gateway -- never the operator chat.")
    if _waived(snap, "AF-STYLE-DOUBLECHARGE"):
        return Verdict.PASS, ""
    locked = choice.get("locked_renders")
    if not (isinstance(locked, list) and len(locked) >= 1):
        return Verdict.FAIL, ("AF-STYLE-DOUBLECHARGE: the winning variant "
                              + repr(choice.get("chosen_variant"))
                              + " records no locked_renders -- its 3 representative "
                              "slides must be carried forward and REUSED, never "
                              "re-rendered. kie must never double-charge for the "
                              "already-approved samples (P-STYLE-PREVIEW, order 4.85).")
    for ref in locked:
        rp = Path(snap.get("_run_dir", ".")) / str(ref) if not str(ref).startswith("/") \
            else Path(str(ref))
        if not rp.exists():
            return Verdict.FAIL, ("AF-STYLE-DOUBLECHARGE: locked sample render "
                                  + repr(str(ref))
                                  + " (the approved variant's representative slide) is "
                                  "missing -- it must be reused, not re-charged. kie must "
                                  "never double-charge the approved samples.")
    return Verdict.PASS, ""


def v_priority_shift_ledger(facts: SliceFacts) -> Tuple[Verdict, str]:
    """AF-PRIORITY-SHIFT — the 14-item pre-output ship gate. Re-derives all 14
    sub-assertions from the captured inputs (copy, spec, renders, pitch flag) and
    writes the per-item ledger to working/qc/priority_shift_report.json — the
    SAME report the legacy gate wrote (the P-SHIFT-QC phase verifier reads it).
    Refuses ship until all 14 PASS. Waivable only by a logged owner skip."""
    snap = _snap(facts)
    if snap.get("priority_spec") is None:
        return Verdict.PASS, ""
    pngs = snap.get("render_pngs") or []
    if not pngs:
        return Verdict.PASS, ""  # the 14-item gate needs the rendered images.
    spec = snap.get("priority_spec") or {}
    text = snap.get("slides_copy_lc") or ""
    intake = snap.get("intake_obj")
    pitch = (intake.get("pitch_included") is True) if isinstance(intake, dict) else False

    def ok_flag(verdict_pair: Tuple[Verdict, str]) -> bool:
        return verdict_pair[0] is Verdict.PASS

    rows: List[Dict[str, Any]] = []

    def add(item: str, passed: bool, evidence: str) -> None:
        rows.append({"item": item, "pass": bool(passed), "evidence": str(evidence)[:240]})

    add("0_attention_is_the_no1_job",
        bool(str(spec.get("true_goal") or "").strip()),
        "priority_shift_spec.true_goal declares the destination shift")
    add("1_creation_mode_identified", ok_flag(v_mode(facts)), "AF-MODE-UNSET")
    add("2_priority_stack_named", ok_flag(v_priority_stack(facts)),
        "AF-NO-PRIORITY-STACK")
    add("3_priority_shift_engineered", ok_flag(v_priority_shift(facts)), "AF-NO-SHIFT")
    add("4_present_cost_exposed",
        _first_marker_offset(text, _bd.COST_OF_INACTION_MARKERS) is not None,
        "cost-of-inaction beat present (Move 2)")
    add("5_higher_priority_lever",
        bool(str(spec.get("higher_priority_hook") or "").strip()),
        "priority_shift_spec.higher_priority_hook (Move 3)")
    add("6_value_anchored_high",
        _first_marker_offset(text, ("anchor", "value-stack", "value_stack",
                                    "value add")) is not None,
        "value anchor beat present (Move 4)")
    add("7_urgency_scarcity",
        (not pitch) or _first_marker_offset(text, _bd.URGENCY_SCARCITY_MARKERS) is not None,
        "urgency/scarcity present (Move 5; n/a for pitchless)")
    add("8_ability_unblocked",
        (not pitch) or _first_marker_offset(text, _bd.ABILITY_UNBLOCK_MARKERS) is not None,
        "ability-blocker removed (Move 6; n/a for pitchless)")
    add("9_rerank_demanded", ok_flag(v_rerank(facts)), "AF-NO-RERANK (Move 7)")
    add("10_trigger_fired", ok_flag(v_trigger(facts)), "AF-NO-TRIGGER (Move 8)")
    add("11_proclamation_hedge_free", ok_flag(v_proclamation_hedge(facts)),
        "AF-PROCLAMATION-HEDGE")
    add("12_peak_and_ending", ok_flag(v_peak_end(facts)), "AF-PEAK-END")
    add("13_most_vivid_by_the_end", ok_flag(v_salience_apex(facts)),
        "AF-NO-SALIENCE-APEX")
    add("14_one_promise_one_wow_one_demonstration",
        all(str(spec.get(k) or "").strip()
            for k in ("the_one_promise", "the_one_wow", "the_one_demonstration")),
        "spec carries the single promise + wow + demonstration anchors")

    passed = all(r["pass"] for r in rows)
    per_slide: List[Dict[str, Any]] = []
    for ordn, rel in sorted(pngs):
        if ordn is None:
            continue
        is_file = Path(rel).is_file()
        per_slide.append({
            "slide": ordn,
            "pass": is_file,
            "verdict": "pass" if is_file else "fail",
            "evidence": "rendered slide present in run dir (ship-gate per-slide pass)",
        })
    report = {
        "schema": "priority_shift_report/v1",
        "gate": "AF-PRIORITY-SHIFT",
        "phase": "P-SHIFT-QC (order 7.5)",
        "generated_at": _bd.time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pass": passed,
        "items": rows,
        "slides": per_slide,
    }
    try:
        out = Path(snap.get("_run_dir", ".")) / _SHIFT_REPORT_REL
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2))
    except Exception:  # noqa: BLE001 — never let report-write mask the verdict
        pass
    if not passed:
        if _waived(snap, "AF-PRIORITY-SHIFT"):
            return Verdict.PASS, ""
        failed = [r["item"] for r in rows if not r["pass"]]
        return Verdict.FAIL, ("AF-PRIORITY-SHIFT: the 14-item priority-shift ship gate "
                              "failed on " + ", ".join(failed)
                              + " (see working/qc/priority_shift_report.json). P-SHIFT-QC "
                              "(order 7.5) blocks ship until all 14 items PASS -- item 0 "
                              "is the North Star: the #1 job is to hold attention "
                              "(P161/P155, SOP-INTEGRATION-00).")
    return Verdict.PASS, ""


def _sp_active_from_snap(snap: dict) -> bool:
    intake = snap.get("intake_obj")
    return isinstance(intake, dict) and intake.get("deck_type") == "signature_presentation"


def v_sp_intake(facts: SliceFacts) -> Tuple[Verdict, str]:
    """P-SP-INTAKE — the 8-Questions atomic-RECORD gate, delegated to the
    Skill-51 prover (prove_sp_intake). DEFERS unless signature_presentation."""
    snap = _snap(facts)
    if not _sp_active_from_snap(snap):
        return Verdict.PASS, ""
    spi = _bd._sp_prover("prove_sp_intake")
    if spi is None:
        return Verdict.FAIL, ("signature_presentation deck but the Skill-51 intake "
                              "prover could not be imported (install the "
                              "51-signature-presentation scripts next to build_deck.py). "
                              "Fail-closed -- the sacred gate cannot be skipped.")
    intake = snap.get("sp_intake")
    if not isinstance(intake, dict):
        return Verdict.FAIL, ("AF-SP-8Q-MISSING: working/copy/sp_intake.json is missing "
                              "or unreadable.")
    fails = spi.evaluate(intake)
    if fails:
        return Verdict.FAIL, "; ".join(str(c) + ": " + str(m) for c, m in fails)
    return Verdict.PASS, ""


def v_sp_structure(facts: SliceFacts) -> Tuple[Verdict, str]:
    """P-SP-STRUCTURE — the SACRED 4-phase structure contract (prove_sp_structure).
    DEFERS unless signature_presentation."""
    snap = _snap(facts)
    if not _sp_active_from_snap(snap):
        return Verdict.PASS, ""
    sps = _bd._sp_prover("prove_sp_structure")
    if sps is None:
        return Verdict.FAIL, ("signature_presentation deck but the Skill-51 structure "
                              "prover could not be imported (install the "
                              "51-signature-presentation scripts next to build_deck.py). "
                              "Fail-closed -- the sacred gate cannot be skipped.")
    deck = snap.get("sp_structure")
    if not isinstance(deck, dict):
        return Verdict.FAIL, ("AF-SP-PHASE-ORDER: working/copy/sp_structure.json is "
                              "missing or unreadable.")
    violations, _notes = sps.verify(sps._load_structure(None), deck)
    if violations:
        return Verdict.FAIL, "; ".join(str(c) + ": " + str(m) for c, m in violations)
    return Verdict.PASS, ""


def v_sp_no_pitch(facts: SliceFacts) -> Tuple[Verdict, str]:
    """P-SP-P3-HYGIENE — Phase-3 teaching no-pitch hygiene (prove_sp_no_pitch).
    DEFERS unless signature_presentation."""
    snap = _snap(facts)
    if not _sp_active_from_snap(snap):
        return Verdict.PASS, ""
    spn = _bd._sp_prover("prove_sp_no_pitch")
    if spn is None:
        return Verdict.FAIL, ("signature_presentation deck but the Skill-51 no-pitch "
                              "prover could not be imported (install the "
                              "51-signature-presentation scripts next to build_deck.py). "
                              "Fail-closed -- the sacred gate cannot be skipped.")
    rd = Path(snap.get("_run_dir", "."))
    code, msgs = spn.evaluate_paths(rd / _SP_INTK_REL, rd / _SP_STRUCT_REL, None)
    if code != 0:
        return Verdict.FAIL, "AF-SP-P3-PITCH: " + " | ".join(str(m) for m in msgs)
    return Verdict.PASS, ""


def v_sp_intake_trace(facts: SliceFacts) -> Tuple[Verdict, str]:
    """P-SP-INTAKE-TRACE — the intake CONVERSATION gate (AF-INTAKE-BATCH).
    Fail-closed: an ABSENT transcript fails (the cheapest way past a conversation
    gate is to record no conversation); a bare hand-written list fails (FIX-3);
    the signed driver envelope is required. DEFERS unless signature_presentation."""
    snap = _snap(facts)
    if not _sp_active_from_snap(snap):
        return Verdict.PASS, ""
    mod = _bd._sp_prover("intake_trace_check")
    if mod is None:
        return Verdict.FAIL, ("AF-INTAKE-BATCH: 51-signature-presentation/scripts/"
                              "intake_trace_check.py is not co-located with build_deck.py "
                              "-- the intake-conversation gate cannot run for a signature "
                              "deck (fail-closed; install skill 51 next to the engine).")
    tpath = snap.get("sp_transcript_path_abs")
    raw = snap.get("sp_transcript")
    if not raw or not tpath:
        return Verdict.FAIL, ("AF-INTAKE-BATCH: no intake transcript at "
                              + str(_SP_TRANSCRIPT_REL) + " -- a signature-presentation "
                              "intake must be CONDUCTED choice-first and one question per "
                              "turn, and the turn-gate records that conversation "
                              "mechanically. An absent transcript is not proof of a "
                              "compliant intake (fail-closed). Run the intake through "
                              "deck-intake-driver.py --signature, which writes a signed "
                              "driver envelope at that path (a hand-written "
                              "intake_ledger.json with no transcript is NOT an "
                              "interview).")
    try:
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError:
            envelope = raw
        prov_fails = mod.check_driver_provenance(envelope)
        turns = mod.parse_transcript(raw)
        if not turns:
            return Verdict.FAIL, ("AF-INTAKE-BATCH: the intake transcript at "
                                  + str(_SP_TRANSCRIPT_REL) + " parsed to zero turns "
                                  "(unreadable format) -- fail-closed.")
        result = mod.scan_transcript(turns, mod.load_bank_questions())
        prov_violations = [{"code": mod.AF_CODE, "reason": code, "turn_index": None,
                            "detail": msg} for code, msg in prov_fails]
        result["violations"] = prov_violations + result.get("violations", [])
        result["pass"] = len(result["violations"]) == 0
    except Exception as exc:  # noqa: BLE001 — fail-closed, never crash
        return Verdict.FAIL, ("AF-INTAKE-BATCH: the intake-conversation scanner raised "
                              + repr(exc) + " -- fail-closed (the conversation gate "
                              "cannot be skipped).")
    if result.get("pass"):
        return Verdict.PASS, ""
    reasons = "; ".join(
        str(v.get("reason", "?")) + " @turn " + str(v.get("turn_index", "?"))
        + ": " + str(v.get("detail", ""))
        for v in result.get("violations", []))
    return Verdict.FAIL, "AF-INTAKE-BATCH: " + reasons


def v_sp_claim(facts: SliceFacts) -> Tuple[Verdict, str]:
    """P-SP-CLAIM — the routing/claim gate. Runs for EVERY deck (does NOT defer):
    SP signals present but deck_type not declared -> fail-closed
    AF-SP-TYPE-UNDECLARED. A non-signature deck with no SP signal passes."""
    snap = _snap(facts)
    mod = _bd._sp_prover("prove_sp_routing")
    if mod is None:
        intake = snap.get("intake_obj")
        declared = isinstance(intake, dict) and \
            intake.get("deck_type") == "signature_presentation"
        sp_present = snap.get("sp_intake") is not None
        if sp_present and not declared:
            return Verdict.FAIL, ("AF-SP-TYPE-UNDECLARED: working/copy/sp_intake.json "
                                  "is present but intake.json does not declare "
                                  "deck_type == signature_presentation (install "
                                  "51-signature-presentation/scripts/prove_sp_routing.py "
                                  "next to build_deck.py for the full signal set). "
                                  "Fail-closed.")
        return Verdict.PASS, ""
    try:
        fails = mod.evaluate_run_dir(Path(snap.get("_run_dir", ".")))
        if fails:
            return Verdict.FAIL, "; ".join(str(c) + ": " + str(m) for c, m in fails)
        return Verdict.PASS, ""
    except Exception as exc:  # noqa: BLE001 — fail-closed, never crash
        return Verdict.FAIL, ("signature-presentation claim gate raised " + repr(exc)
                              + " -- fail-closed (a signature deck cannot skip the "
                              "claim gate).")


# ---------------------------------------------------------------------------
# Registration — one VerifierSpec per converted gate. legacy= the _chk_* function
# (report-only shadow-compare); a NULL legacy means the slice owns the gate and
# the RunFacts verdict is authoritative.
# ---------------------------------------------------------------------------
SLICE1_GATES = (
    # (gate name, artifacts glob(s) the verifier needs, verdict fn, legacy fn)
    ("slice1:deck_type", _INTK_RELS, v_deck_type, _bd._chk_deck_type),
    ("slice1:mode", _INTK_RELS, v_mode, _bd._chk_mode),
    ("slice1:priority_shift", _SPEC_RELS, v_priority_shift, _bd._chk_priority_shift),
    ("slice1:priority_stack", _SPEC_RELS, v_priority_stack, _bd._chk_priority_stack),
    ("slice1:rerank", _SPEC_RELS, v_rerank, _bd._chk_rerank),
    ("slice1:trigger", _SPEC_RELS, v_trigger, _bd._chk_trigger),
    ("slice1:proclamation_hedge", _SPEC_RELS, v_proclamation_hedge,
     _bd._chk_proclamation_hedge),
    ("slice1:peak_end", _SPEC_RELS, v_peak_end, _bd._chk_peak_end),
    ("slice1:salience_apex", _SPEC_RELS, v_salience_apex, _bd._chk_salience_apex),
    ("slice1:converter_no_invent", _BRIEF_RELS, v_converter_no_invent,
     _bd._chk_converter_no_invent),
    ("slice1:persuasion_beats", _SPEC_RELS, v_persuasion_beats,
     _bd._chk_persuasion_beats),
    ("slice1:style_preview", (_STYLE_MANIFEST_REL,), v_style_preview,
     _bd._chk_style_preview),
    ("slice1:priority_shift_ledger", _SPEC_RELS, v_priority_shift_ledger,
     _bd._chk_priority_shift_ledger),
    ("slice1:sp_intake", (_SP_INTK_REL,), v_sp_intake, _bd._chk_sp_intake),
    ("slice1:sp_structure", (_SP_STRUCT_REL,), v_sp_structure, _bd._chk_sp_structure),
    ("slice1:sp_no_pitch", (_SP_INTK_REL, _SP_STRUCT_REL), v_sp_no_pitch,
     _bd._chk_sp_no_pitch),
    ("slice1:sp_intake_trace", (_SP_TRANSCRIPT_REL,), v_sp_intake_trace,
     _bd._chk_sp_intake_trace),
    ("slice1:sp_claim", (_SP_INTK_REL,), v_sp_claim, _bd._chk_sp_claim),
)


def register_slice1() -> None:
    """Register every slice-1 gate. Idempotent (last registration wins)."""
    for gate, artifacts, verdict_fn, legacy in SLICE1_GATES:
        register_verifier(_slice_verifier(gate, artifacts, verdict_fn, legacy))


register_slice1()
