#!/usr/bin/env python3
"""
phase_verifiers.py — Per-phase SUBSTANCE verifier registry (FIX 5d).

REQUIRED PUBLIC API (run_signature_deck.py imports this module and calls these):

    PHASE_VERIFIERS : dict[str, callable]
        Maps manifest phase id (verbatim from PIPELINE-MANIFEST.json) to a callable:
            callable(run_dir: Path) -> (ok: bool, reasons: list[str])

    verify(phase_id: str, run_dir: Path) -> (ok: bool, reasons: list[str])
        Entry point. Unknown phase ids return (False, ["no verifier — pass"]) so the
        runner blocks unmapped phases (fail-closed per U013 step 9).

DESIGN RULES
  * These verifiers are PRIMARY gates — they are THE enforcement surface for every
    phase. They supersede, never supplement, the attestation chain.
  * FAIL-HARD for file-not-found: if a produces_artifact is absent, the verifier
    returns (False, ["<pattern>: file not found — phase artifact missing"]).
    Verifiers must check artifact existence AND substance AND format validity.
    A missing artifact is FAIL. A present-but-empty artifact is FAIL. A
    present-but-wrong artifact (wrong magic bytes, wrong MIME type) is FAIL.
    A present-and-valid artifact is PASS.
  * SIMULATED is not a valid phase result. The verify() entry point now
    mechanically scans the run's process_manifest.json for SIMULATED entries
    BEFORE dispatching to any per-phase verifier (WI-14c).  Any phase whose
    attestation record contains "SIMULATED" or {"execution": "SIMULATED"}
    is FAIL unless the PIPELINE-MANIFEST declares allowed_simulated:true
    AND the reason cites the specific missing credential (e.g. KIE_API_KEY).
    This check is in verify() itself — no verifier can bypass it.
  * All engine-checker imports are defensive (try/except ImportError) so CI/test
    contexts that lack sibling modules still parse without error.
  * A genuinely unavailable checker records a NOTE reason but does NOT crash and does
    NOT silently pass a real substance failure — it only degrades when the module is
    missing.
  * NO network calls, NO side effects. Pure filesystem reads + engine checks.
  * FAIL-with-reason is mechanically enforced. After each verifier returns,
    verify() validates that every (False, reasons) tuple has non-empty reasons.
    A bare (False, []) is a VERIFIER BUG and is escalated to the operator.

EXIT CODES (when run as __main__ with --selftest)
    0 — all self-tests passed
    1 — a self-test failed
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple

# SINGLE SOURCE OF TRUTH (U05) — the deliverable whitelist and its key set live
# in presentation_job/deliverables.py; fix_bundle_complete.py, curate.py, and
# self_audit.py all derive their runtime maps from the same constant. This
# import is NOT defensive/optional: the P9-DELIVER verifier's whitelist must
# never fall back to a local, driftable copy (see _DELIVERY_DELIVERABLES below).
try:
    from presentation_job.deliverables import DELIVERABLE_AUDIT_SPEC as _DELIVERABLE_AUDIT_SPEC
except ImportError:
    _SCRIPTS_DIR = Path(__file__).resolve().parent
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    from presentation_job.deliverables import DELIVERABLE_AUDIT_SPEC as _DELIVERABLE_AUDIT_SPEC

# ---------------------------------------------------------------------------
# Defensive engine-checker imports (all optional)
# ---------------------------------------------------------------------------

try:
    import build_deck as _bd
except ImportError:
    _bd = None  # type: ignore[assignment]

try:
    import canonical_render_guard as _crg
except ImportError:
    _crg = None  # type: ignore[assignment]

try:
    import intelligence_engines_check as _iec
except ImportError:
    _iec = None  # type: ignore[assignment]

try:
    import pitch_engines_check as _pec
except ImportError:
    _pec = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Internal filesystem helpers
# ---------------------------------------------------------------------------

def _resolve_glob(run_dir: Path, pattern: str) -> Optional[Path]:
    """Resolve a glob pattern relative to run_dir; return the first match or None."""
    if not pattern:
        return None
    if "*" in pattern or "?" in pattern:
        hits = sorted(run_dir.glob(pattern))
        return hits[0] if hits else None
    p = run_dir / pattern
    return p if p.exists() else None


def _read_json(path: Path):
    """Read a JSON file, returning None on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return None


def _read_text(path: Path) -> Optional[str]:
    """Read a text file, returning None on any error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Engine-checker helpers
# ---------------------------------------------------------------------------

def _bd_fn(name: str):
    """Return a build_deck attribute by name, or None if unavailable."""
    if _bd is None:
        return None
    return getattr(_bd, name, None)


def _checker_pass(result) -> bool:
    """Normalise a checker result to bool.

    build_deck preflights return '' / None on PASS (preflight convention).
    Checkers may also return dict({pass:bool}) or a list ([] == pass).
    Returns True when the result indicates PASS."""
    if result is None or result == "" or result == []:
        return True
    if isinstance(result, dict):
        return bool(result.get("pass", True))
    if isinstance(result, (list, tuple)):
        return len(result) == 0
    if isinstance(result, str):
        return result.strip() == ""
    return bool(result)


def _pitch_included(run_dir: Path) -> bool:
    """True unless intake.json explicitly records pitch_included:false."""
    intake = run_dir / "working" / "copy" / "intake.json"
    try:
        obj = json.loads(intake.read_text())
        if isinstance(obj, dict) and obj.get("pitch_included") is False:
            return False
    except Exception:  # noqa: BLE001
        pass
    return True


# ---------------------------------------------------------------------------
# Generic artifact checks (filesystem-only, no engine required)
# ---------------------------------------------------------------------------

def _check_json_nonempty(run_dir: Path, pattern: str,
                          required_keys: tuple = ()) -> Tuple[bool, List[str]]:
    """Check that a JSON artifact is non-empty and has required_keys.
    FAIL-HARD when the file is absent — the verifier is a PRIMARY gate, not secondary."""
    p = _resolve_glob(run_dir, pattern)
    if p is None:
        return False, [f"{pattern}: file not found — phase artifact missing"]
    if p.stat().st_size == 0:
        return False, [f"{pattern}: file is zero bytes"]
    obj = _read_json(p)
    if obj is None:
        return False, [f"{pattern}: not valid JSON (parse error)"]
    if isinstance(obj, dict):
        for k in required_keys:
            if k not in obj:
                return False, [f"{pattern}: required key {k!r} absent"]
    elif isinstance(obj, list) and len(obj) == 0:
        return False, [f"{pattern}: JSON array is empty"]
    return True, []


def _check_text_nonempty(run_dir: Path, pattern: str,
                          min_bytes: int = 20) -> Tuple[bool, List[str]]:
    """Check that a text artifact has at least min_bytes of non-whitespace content.
    FAIL-HARD when the file is absent — the verifier is a PRIMARY gate, not secondary."""
    p = _resolve_glob(run_dir, pattern)
    if p is None:
        return False, [f"{pattern}: file not found — phase artifact missing"]
    txt = _read_text(p)
    if txt is None:
        return False, [f"{pattern}: unreadable"]
    if len(txt.strip()) < min_bytes:
        return False, [f"{pattern}: suspiciously short ({len(txt.strip())} chars < {min_bytes})"]
    return True, []


def _merge(results: List[Tuple[bool, List[str]]]) -> Tuple[bool, List[str]]:
    """Merge multiple (ok, reasons) tuples: ok=True only if ALL are True."""
    all_ok = all(r[0] for r in results)
    all_reasons: List[str] = []
    for _, reasons in results:
        all_reasons.extend(reasons)
    return all_ok, all_reasons


# ---------------------------------------------------------------------------
# Per-phase substance verifiers
# Each returns (ok: bool, reasons: list[str]).
# ---------------------------------------------------------------------------

def _verify_research(run_dir: Path) -> Tuple[bool, List[str]]:
    """P-0.5-RESEARCH: brief exists + cited URLs >= floor + no uncited claims.

    Wires the three preflights declared in PIPELINE-MANIFEST.json for this phase:
    _chk_research_brief, _chk_research_cited, _chk_claims_without_citation.
    Falls back to filesystem check when build_deck is unavailable."""
    reasons: List[str] = []

    fn_brief = _bd_fn("_chk_research_brief")
    fn_cited = _bd_fn("_chk_research_cited")
    fn_claims = _bd_fn("_chk_claims_without_citation")

    if fn_brief is None and fn_cited is None and fn_claims is None:
        # No engine available — fall back to filesystem existence check.
        ok, r = _check_text_nonempty(run_dir, "working/research/brief-*.md", 100)
        if not ok:
            return False, r
        return True, ["NOTE: build_deck not importable — research engine checks degraded (pass)"]

    # FIX-E2E: _chk_research_brief / _chk_research_cited take a FILE path (they
    # call path.read_text()), but this verifier passed run_dir (a directory) —
    # an IsADirectoryError that failed every P-0.5-RESEARCH attestation at
    # substance-verify time even when the brief was valid. build_deck's own
    # preflight resolves the glob to a file first; mirror that here. The
    # globbed brief file (if any) is the target for both file-path checkers;
    # _chk_claims_without_citation takes run_dir, which stays unchanged.
    brief_files = sorted((run_dir / "working" / "research").glob("brief-*.md")) \
        if (run_dir / "working" / "research").is_dir() else []
    brief_path = brief_files[0] if brief_files else None

    if fn_brief is not None:
        result = fn_brief(brief_path)
        if not _checker_pass(result):
            reasons.append(f"AF-RESEARCH-GATE: research brief check failed: {result}")
    else:
        reasons.append("NOTE: _chk_research_brief unavailable — skipped")

    if fn_cited is not None:
        result = fn_cited(brief_path)
        if not _checker_pass(result):
            reasons.append(f"AF-RESEARCH-UNCITED: cited-URL check failed: {result}")
    else:
        reasons.append("NOTE: _chk_research_cited unavailable — skipped")

    if fn_claims is not None:
        result = fn_claims(run_dir)
        if not _checker_pass(result):
            reasons.append(f"AF-RESEARCH-UNCITED: claims-without-citation check failed: {result}")
    else:
        reasons.append("NOTE: _chk_claims_without_citation unavailable — skipped")

    hard = [r for r in reasons if not r.startswith("NOTE")]
    return (len(hard) == 0), reasons


def _verify_copy(run_dir: Path) -> Tuple[bool, List[str]]:
    """P4-COPY / P1Q-COPY-QC: writing-engine (intelligence_engines_check.check_copy)
    + pricing-engine (pitch_engines_check.check_copy)."""
    reasons: List[str] = []
    problems: list = []

    if _iec is None and _pec is None:
        # Fall back to filesystem check.
        ok, r = _check_text_nonempty(run_dir, "working/copy/slides_copy.md", 50)
        if not ok:
            return False, r
        return True, ["NOTE: engine checkers not importable — copy verifier degraded (pass)"]

    working = run_dir / "working"

    if _iec is not None and hasattr(_iec, "check_copy"):
        try:
            _iec.check_copy(working, problems)
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"NOTE: intelligence_engines_check.check_copy raised {exc!r} — skipped")
    else:
        reasons.append("NOTE: intelligence_engines_check.check_copy unavailable — skipped")

    if _pec is not None and hasattr(_pec, "check_copy") and _pitch_included(run_dir):
        try:
            _pec.check_copy(working, problems)
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"NOTE: pitch_engines_check.check_copy raised {exc!r} — skipped")
    else:
        if _pec is None:
            reasons.append("NOTE: pitch_engines_check unavailable — skipped")

    for p in problems:
        code = p.get("code", "AF-COPY") if isinstance(p, dict) else "AF-COPY"
        detail = p.get("detail", str(p)) if isinstance(p, dict) else str(p)
        reasons.append(f"{code}: {detail}")

    hard = [r for r in reasons if not r.startswith("NOTE")]
    return (len(hard) == 0), reasons


def _verify_prompt(run_dir: Path) -> Tuple[bool, List[str]]:
    """P4-PROMPT / P-PROMPT-QC: build_deck.check_prompt_qc_deterministic
    (length >= 9,000 AND every engine AND harmony AND excellence)."""
    reasons: List[str] = []

    fn = _bd_fn("check_prompt_qc_deterministic")
    if fn is None:
        ok, r = _check_text_nonempty(run_dir, "working/prompts/slide-*.txt", 100)
        if not ok:
            return False, r
        return True, ["NOTE: build_deck.check_prompt_qc_deterministic unavailable — prompt verifier degraded (pass)"]

    try:
        verdict = fn(run_dir)
    except Exception as exc:  # noqa: BLE001
        return True, [f"NOTE: check_prompt_qc_deterministic raised {exc!r} — degraded (pass)"]

    if isinstance(verdict, dict):
        if verdict.get("pass"):
            return True, []
        for sid, sd in (verdict.get("slides") or {}).items():
            if not isinstance(sd, dict):
                continue
            for d in (sd.get("deficiencies") or []):
                if not isinstance(d, dict):
                    continue
                if str(d.get("severity", "")).lower() == "ok":
                    continue
                reasons.append(
                    f"AF-PROMPT-FLOOR slide-{sid}: {d.get('code', '?')} — {d.get('detail', '')}"
                )
        if not reasons:
            reasons.append("AF-PROMPT-FLOOR: check_prompt_qc_deterministic returned pass:false")
        return False, reasons

    if not _checker_pass(verdict):
        return False, [f"AF-PROMPT-FLOOR: {verdict}"]
    return True, []


def _verify_render(run_dir: Path) -> Tuple[bool, List[str]]:
    """P4-RENDER / P-IMAGE-QC: canonical_render_guard image-QC (AF-IMAGE-QC-VISION).
    Falls back to filesystem PNG existence check when the guard is unavailable."""
    if _crg is not None:
        fn = getattr(_crg, "check_image_qc", None) or getattr(_crg, "check_rendered_images", None)
        if fn is not None:
            try:
                result = fn(run_dir)
                if not _checker_pass(result):
                    return False, [f"AF-IMAGE-QC-VISION: {result}"]
                return True, []
            except Exception as exc:  # noqa: BLE001
                pass  # fall through to filesystem check below

    # Filesystem fallback: at least one render PNG must exist.
    hits = list(run_dir.glob("renders/slide-*.png"))
    if not hits:
        return False, ["AF-IMAGE-QC-VISION: no render PNGs found at renders/slide-*.png"]
    return True, ["NOTE: canonical_render_guard image-QC unavailable — filesystem-only check (pass)"]


def _verify_assemble(run_dir: Path) -> Tuple[bool, List[str]]:
    """P8-ASSEMBLE: build_deck.check_deck_harmony (arc + visual consistency).
    Falls back to filesystem PPTX existence + size check when unavailable.

    check_deck_harmony only proves cross-slide cohesion (recurring character,
    palette, archetype rhythm) from the RENDERED PNGs / prompts — it never opens
    the assembled PPTX itself. Delegating straight to it let a decoy file (e.g. a
    40-byte text file renamed 'deck.pptx') pass this phase outright, because a
    harmony PASS was returned before anything checked the artifact was a real
    PPTX. Mirror the same magic-bytes idiom _DELIVERY_DELIVERABLES already uses
    (PK\\x03\\x04 header) on every passing harmony result, so a decoy cannot ride
    a harmony pass through assembly."""
    fn = _bd_fn("check_deck_harmony")
    if fn is not None:
        try:
            result = fn(run_dir)
            if not _checker_pass(result):
                detail = result if isinstance(result, str) else json.dumps(result)
                return False, [f"AF-HARMONY: deck harmony check failed: {detail}"]
            # Harmony passed — but harmony never inspects the assembled PPTX
            # itself. Prove each candidate PPTX is a real one before letting the
            # delegated pass stand.
            hits = [p for p in run_dir.glob("**/*.pptx") if not p.name.startswith("~$")]
            if not hits:
                return False, ["AF-HARMONY: deck harmony check passed but no .pptx "
                               "found in run dir (assembly not complete)"]
            pptx_reasons: List[str] = []
            for p in hits:
                size = p.stat().st_size
                if size < 1000:
                    pptx_reasons.append(
                        f"AF-HARMONY: {p.name} is suspiciously small ({size} bytes) "
                        f"— not a real assembled PPTX")
                    continue
                try:
                    with open(p, "rb") as fh:
                        head = fh.read(4)
                except OSError as exc:  # noqa: BLE001
                    pptx_reasons.append(f"AF-HARMONY: cannot read {p.name} for "
                                        f"magic-bytes check: {exc!r}")
                    continue
                if head != b"PK\x03\x04":
                    pptx_reasons.append(
                        f"AF-HARMONY: {p.name} is not a valid ZIP/PPTX container "
                        f"(expected b'PK\\x03\\x04' at offset 0, got {head!r}) — "
                        f"a renamed non-PPTX file cannot pass assembly")
            if pptx_reasons:
                return False, pptx_reasons
            return True, []
        except Exception as exc:  # noqa: BLE001
            pass  # fall through to filesystem check

    # Filesystem fallback: a non-trivially-sized PPTX must exist.
    hits = [p for p in run_dir.glob("**/*.pptx") if not p.name.startswith("~$")]
    if not hits:
        return False, ["AF-HARMONY: no .pptx found in run dir (assembly not complete)"]
    biggest = max(hits, key=lambda p: p.stat().st_size)
    if biggest.stat().st_size < 1000:
        return False, [f"AF-HARMONY: {biggest.name} is suspiciously small ({biggest.stat().st_size} bytes)"]
    return True, ["NOTE: build_deck.check_deck_harmony unavailable — filesystem-only check (pass)"]


def _verify_notes_sync(run_dir: Path) -> Tuple[bool, List[str]]:
    """P9.5-NOTES-SYNC: notes_sync.json must record a 'synced' pass (notes actually
    injected from the QC-passed speech), AND the delivered PPTX must have no empty
    notes panes (via build_deck._chk_notes_pane / AF-EMPTY-NOTES-PANE) when a bundle
    dir can be located. 'no_speech' status is a HARD FAIL here — by the time this
    phase's precondition gate runs, P9-SPEECH + P-SPEECH-QC are already attested, so
    the speech MUST exist; a notes_sync.json still reporting no_speech means the
    reorder did not do its job and the deck would still ship with empty notes."""
    reasons: List[str] = []
    ok_json, r = _check_json_nonempty(run_dir, "working/checkpoints/notes_sync.json")
    if not ok_json:
        return False, r
    obj = _read_json(run_dir / "working" / "checkpoints" / "notes_sync.json")
    if isinstance(obj, dict):
        status = obj.get("status")
        if status == "error":
            reasons.append(f"AF-EMPTY-NOTES-PANE: notes_sync.json status=error: "
                           f"{obj.get('reason', '')}")
        elif status == "no_speech":
            reasons.append("AF-EMPTY-NOTES-PANE: notes_sync.json status=no_speech — "
                           "P9-SPEECH/P-SPEECH-QC are attested (this phase's own "
                           "precondition) but no speech was found at re-sync time; "
                           "the notes pane would still ship empty.")
        elif status != "synced":
            reasons.append(f"AF-EMPTY-NOTES-PANE: notes_sync.json has unexpected "
                           f"status={status!r}")
    fn = _bd_fn("_chk_notes_pane")
    if fn is not None:
        bundle_pptx = obj.get("bundle_pptx") if isinstance(obj, dict) else None
        if bundle_pptx:
            bundle_dir = Path(bundle_pptx).parent
            result = fn(bundle_dir, run_dir=run_dir, slides_path=None)
            if not _checker_pass(result):
                reasons.append(str(result))
    hard = [r for r in reasons if not r.startswith("NOTE")]
    return (len(hard) == 0), reasons


# -- canonical deliverable whitelist (U05: SINGLE SOURCE OF TRUTH — derived from
#    presentation_job.deliverables.DELIVERABLE_AUDIT_SPEC, the same constant
#    fix_bundle_complete.py, curate.py, and self_audit.py all import). The key
#    set, min_bytes floor, and magic bytes/description come from the canonical
#    spec; `pattern` (the pre-curation working/ dir glob) and `content_check`
#    (the substance-verifier tag) are phase_verifiers-local metadata layered on
#    top, because this verifier runs BEFORE curate.py assembles the flat
#    deliverables/ bundle the other consumers check. --

# Pre-curation search pattern (glob, relative to run_dir) per canonical key.
_DELIVERY_PATTERN_BY_KEY = {
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

# Substance content-check tag for deliverables whose magic_bytes is None (a
# presence-only check would let a renamed text file pass) — see
# _deliverable_content_check() below.
_DELIVERY_CONTENT_CHECK_BY_KEY = {
    "speech_fish_md":    "fish_tags",
    "teleprompter_html": "teleprompter",
    "webinar_mp4":       "mp4_ftyp",
}

_DELIVERY_DELIVERABLES = [
    {
        "key": s["key"],
        "pattern": _DELIVERY_PATTERN_BY_KEY[s["key"]],
        "min_bytes": s["min_bytes"],
        "magic": s["magic_bytes"],
        "magic_desc": s["magic_desc"],
        **({"content_check": _DELIVERY_CONTENT_CHECK_BY_KEY[s["key"]]}
           if s["key"] in _DELIVERY_CONTENT_CHECK_BY_KEY else {}),
    }
    for s in _DELIVERABLE_AUDIT_SPEC
]


def _load_manifest_json(run_dir: Path) -> Optional[dict]:
    """Load the run's process_manifest.json or deliverable manifest."""
    for path in [
        run_dir / "working" / "checkpoints" / "process_manifest.json",
        run_dir / "process_manifest.json",
    ]:
        try:
            return json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            continue
    return None


# ---------------------------------------------------------------------------
# SIMULATED rejection — mechanical enforcement that no phase can be "SIMULATED"
# without a verifier pass.  This is the ANTI-DRIFT CORE (WORK-ITEM-14c):
# every phase result flows through verify(), and verify() checks this BEFORE
# delegating to the individual verifier so the check cannot be bypassed.
# ---------------------------------------------------------------------------

def _simulated_phase_ids(run_dir: Path) -> set[str]:
    """Return the set of phase ids whose process_manifest attestation record
    contains 'SIMULATED' in any execution/status/result field.

    An attestation entry looks like:
        {"phase_id": "P8-ASSEMBLE", "execution": "SIMULATED", "status": "complete"}

    Any entry with the literal string "SIMULATED" in the execution field, the
    status field, or any field value is suspect.  This scanner is deliberately
    broad — a genuine PASS never contains the word "SIMULATED"."""
    obj = _load_manifest_json(run_dir)
    if not isinstance(obj, dict):
        return set()
    simulated: set[str] = set()
    # Scan the top-level phases list (the common shape).
    for entry in (obj.get("phases") or []):
        if not isinstance(entry, dict):
            continue
        pid = entry.get("phase_id") or entry.get("id") or ""
        # Check every string value in the entry for the literal "SIMULATED"
        for _k, v in entry.items():
            if isinstance(v, str) and "SIMULATED" in v:
                simulated.add(str(pid))
                break
    # Also scan a flat key-value manifest where keys are phase ids.
    for k, v in obj.items():
        if isinstance(v, dict):
            for _kk, vv in v.items():
                if isinstance(vv, str) and "SIMULATED" in vv:
                    simulated.add(str(k))
                    break
        elif isinstance(v, str) and "SIMULATED" in v:
            simulated.add(str(k))
    return simulated


def _load_pipeline_manifest() -> dict:
    """Load the PIPELINE-MANIFEST.json (the canonical phase definition, not the
    per-run process manifest).  Returns empty dict when unresolvable."""
    # Resolve the manifest the same way the engine does.
    here = Path(__file__).resolve().parent
    sops_dir = here.parent / "sops"
    manifest_path = sops_dir / "PIPELINE-MANIFEST.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8", errors="replace"))
        if isinstance(data, dict):
            return data
    except Exception:  # noqa: BLE001
        pass
    return {}


def _phase_allows_simulated(phase_id: str) -> Tuple[bool, str]:
    """Check whether the PIPELINE-MANIFEST declares allowed_simulated:true for
    this phase.  Returns (allowed: bool, required_credential: str).

    allowed_simulated is only valid when the phase cites a SPECIFIC missing
    credential (e.g. KIE_API_KEY, FISH_API_KEY).  A blanket allowed_simulated
    without a named credential is NOT honoured."""
    manifest = _load_pipeline_manifest()
    phases = manifest.get("phases") or manifest.get("work_items") or []
    if not isinstance(phases, list):
        return False, ""
    for ph in phases:
        if not isinstance(ph, dict):
            continue
        pid = ph.get("id") or ph.get("phase_id") or ""
        if str(pid) != phase_id:
            continue
        if ph.get("allowed_simulated") is not True:
            return False, ""
        cred = ph.get("simulated_requires_credential") or ph.get("simulated_credential") or ""
        return True, str(cred)
    return False, ""


def _check_simulated_rejection(phase_id: str, run_dir: Path) -> Tuple[bool, List[str]]:
    """Before dispatching to the per-phase verifier, check whether the run's
    attestation record claims this phase was SIMULATED.

    DESIGN RULE: SIMULATED is not a valid phase result.  The ONLY exception is
    phases whose PIPELINE-MANIFEST declares allowed_simulated: true WITH a
    specific missing credential cited — and even then the SIMULATED reason
    must name that credential."""
    simulated_ids = _simulated_phase_ids(run_dir)
    if phase_id not in simulated_ids:
        return True, []  # not simulated — proceed to normal verification

    allowed, required_cred = _phase_allows_simulated(phase_id)

    if not allowed:
        return False, [
            f"SIMULATED is not a valid phase result for {phase_id!r}. "
            f"The attestation record marks this phase as SIMULATED but the "
            f"PIPELINE-MANIFEST does not declare allowed_simulated:true for it. "
            f"A phase cannot be skipped by agent declaration."
        ]

    # allowed_simulated is true — verify the reason cites the required credential.
    obj = _load_manifest_json(run_dir)
    if isinstance(obj, dict):
        for entry in (obj.get("phases") or []):
            if not isinstance(entry, dict):
                continue
            pid = entry.get("phase_id") or entry.get("id") or ""
            if str(pid) != phase_id:
                continue
            reason = entry.get("reason") or entry.get("simulated_reason") or ""
            if required_cred and required_cred not in reason:
                return False, [
                    f"SIMULATED requires a specific missing credential for {phase_id!r}. "
                    f"PIPELINE-MANIFEST requires credential {required_cred!r} but the "
                    f"SIMULATED reason did not cite it (got: {repr(reason) if reason else '<empty>'} )."
                ]
            # Credential cited — allow the SIMULATED result.
            return True, [
                f"NOTE: {phase_id} — allowed_simulated: credential {required_cred!r} "
                f"cited in reason — proceeding with degraded check"
            ]

    # Manifest unreadable but phase claims SIMULATED with allowed_simulated.
    # Treat as unverifiable.
    return False, [
        f"SIMULATED attestation for {phase_id!r} cannot be verified: "
        f"allowed_simulated is declared but the process_manifest is unreadable"
    ]


# ---------------------------------------------------------------------------
# WORK-ITEM-14 (R3 U03 / R3 U03-R2): owner_skip_approval token check —
# mechanical gate that a FAILING substance verifier can only be stepped over
# with an AUTHENTIC OWNER-AUTHORIZED token.  Shared with the engine
# (presentation_job.phases.Engine.run_phase), so the token contract lives in
# exactly one place.
#
# R3 U03-R2 (QC FAIL 8.00, adversarial F1): a token found ONLY in
# working/checkpoints/process_manifest.json is SELF-MINTED — the engine writes
# that file itself, so a token that lives only there proves nothing about an
# owner.  The judge's exploit: {"owner_approved":true, "phase_id":"P8-ASSEMBLE"}
# inside process_manifest.json authorized its own skip with zero authenticity.
# From this fix, process_manifest.json is structurally INCAPABLE of issuing an
# owner skip — the ONLY authentic source is the operator-signed waiver ledger:
#
#   waivers.json  (run_dir root) — the engine's existing waiver ledger, signed
#     by the operator at capture time with the client's own recorded words.
#     presentation_job.waivers.validate_waiver() mechanically proves the
#     client_request_quote is a real substring of the client's intake field
#     (or transcript) — a token cannot self-mint those words, because the
#     intake.json value the quote is checked against is written by the intake
#     driver from the client's own answers, not by the job engine.  Waivers
#     additionally require captured_at and carry the operator identity in
#     captured_from.
#
# A waiver covers exactly the phase(s) its rule keys — the phase id -> waiver
# rule mapping below.  A waiver for rule=qc may NEVER step over a substance
# verifier (QC is structurally unskippable, canonical_render_guard.
# UNSKIPPABLE_QC_PHASES); the QA gates in Gates.close() consume waivers.json
# themselves and are untouched here.
#
# Rejection reasons are appended to the caller's fail_reasons list (in place)
# so the engine's block message names the missing authenticity field.
# ---------------------------------------------------------------------------
_AF_CODE_RE = re.compile(r"\b(AF-[A-Z0-9][A-Z0-9_.-]*)\b")

# Phase id -> waiver rule.  A skip token (validated waiver) may step over
# phase_id ONLY when its rule is the mapped one.  Kept deliberately small and
# non-waivable: the P8 assembly / P8.1-PDF / P8.2-GUIDE / P8.4-FISH-TAG
# substance verifiers are keyed to the SCRIPT deliverable (a client-written
# waiver for rule=script), the P9-SPEECH verifier to the same, and the
# P9.2-GHL-UPLOAD verifier to rule=ghl_upload.  No phase maps to rule=qc or
# rule=prompt_floor: a substance verifier can never be stepped over by a QC
# or prompt-floor waiver.
_PHASE_TO_WAIVER_RULE: dict = {
    "P8-ASSEMBLE": "script",
    "P8.1-PDF-EXPORT": "script",
    "P8.2-GUIDE": "script",
    "P8.4-FISH-TAG": "script",
    "P9-SPEECH": "script",
    "P9.2-GHL-UPLOAD": "ghl_upload",
}


def _load_owner_skip_records(run_dir: Path) -> List[dict]:
    """Collect every raw owner_skip_approval record from process_manifest.json.
    R3 U03-R2: every one of these is a SELF-MINT — the run's own attestation
    ledger cannot issue an owner skip, so the authorizer rejects them all
    (reason names the missing authenticity fields)."""
    obj = _load_manifest_json(run_dir)
    if not isinstance(obj, dict):
        return []
    raw = obj.get("owner_skip_approval", obj.get("owner_skip_approvals", []))
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [r for r in raw if isinstance(r, dict)]


def _waiver_covers_phase(w: dict, phase_id: str) -> bool:
    """True when validated waiver `w` names the rule that maps to phase_id."""
    return _PHASE_TO_WAIVER_RULE.get(phase_id) == str(w.get("rule") or "").strip()


def owner_skip_approval_authorizes(phase_id: str, fail_reasons: List[str],
                                   run_dir: Path) -> Optional[dict]:
    """Return the skip token that authorizes stepping a FAILED verifier over,
    or None when no AUTHENTIC token covers phase_id.

    R3 U03-R2 authenticity contract (QC FAIL 8.00 — adversarial F1: a
    self-minted process_manifest token {owner_approved:true,
    phase_id:'P8-ASSEMBLE'} previously authorized its own skip with zero
    authenticity).  A token authorizes ONLY when ALL hold:

      1. SOURCE — it is an entry of waivers.json (run_dir root), the
         operator-signed ledger.  A record found in process_manifest.json is
         the run's OWN self-mint (the engine writes that file itself) and is
         REJECTED unconditionally; the rejection reason names the missing
         authenticity field(s) (client_request_quote / issuer / captured_at).
      2. ISSUANCE PROOF — validate_waiver() proves the client_request_quote
         is a genuine substring of the client's own recorded words in
         intake.json (or the transcript), and that captured_at is present.
         The engine cannot forge those: the intake value is written by the
         intake driver from the client's own answers.
      3. COVERAGE — the waiver's rule maps to phase_id (see
         _PHASE_TO_WAIVER_RULE).  A waiver never covers a phase outside its
         rule, and a rule=qc / rule=prompt_floor waiver covers nothing here.

    Rejection reasons are appended to fail_reasons in place (when it is a
    list) so the engine's block message names the missing field.  Malformed
    or unverifiable records authorize nothing (fail-closed)."""
    reasons = fail_reasons if isinstance(fail_reasons, list) else []

    # 1. The run's own manifest can never issue an owner skip (self-mint).
    for tok in _load_owner_skip_records(run_dir):
        gate = tok.get("gate") or tok.get("af_code") or tok.get("phase_id") or "?"
        missing = [f for f in ("client_request_quote", "issuer", "captured_at")
                   if not str(tok.get(f) or "").strip()]
        if missing:
            reasons.append(
                f"AF-FORGED-APPROVAL: owner_skip_approval token for {gate!r} "
                f"is SELF-MINTED — found only in process_manifest.json (the "
                f"run's own attestation ledger) and missing authenticity "
                f"field(s): {', '.join(missing)}.  Authentic skips are "
                f"recorded in waivers.json.")
        else:
            reasons.append(
                f"AF-FORGED-APPROVAL: owner_skip_approval token for {gate!r} "
                f"is SELF-MINTED — process_manifest.json is the run's own "
                f"attestation ledger and cannot issue an owner skip, even "
                f"with quote/issuer/captured_at fields.  Authentic skips are "
                f"recorded in waivers.json.")

    # 2+3. Only the operator-signed, client-verified waiver ledger authorizes.
    try:
        try:
            from .waivers import load_waivers, WaiverError, validate_waiver
        except ImportError:
            # Bare-module context (legacy callers, engine's `import phase_verifiers`):
            # relative import has no package to anchor to — use the absolute form.
            from presentation_job.waivers import (  # type: ignore[no-redef]
                load_waivers, WaiverError, validate_waiver)
        try:
            waivers = list(load_waivers(run_dir))
        except WaiverError as exc:
            reasons.append(f"AF-FORGED-APPROVAL: waivers.json is unreadable "
                           f"— {exc}")
            waivers = []
    except ImportError:
        reasons.append("AF-FORGED-APPROVAL: waivers module unavailable — no "
                       "skip can be authenticated")
        waivers = []

    for w in waivers:
        if not isinstance(w, dict):
            continue
        try:
            validate_waiver(w, Path(run_dir))
        except WaiverError as exc:
            reasons.append(
                f"AF-FORGED-APPROVAL: waivers.json record for {w.get('rule')!r} "
                f"is not authentic — {exc}")
            continue
        if not _waiver_covers_phase(w, phase_id):
            continue
        return w
    return None


def _deliverable_content_check(key: str, path: Path, reasons: list) -> None:
    """Run a substance content check on a deliverable that has content_check configured.

    Three deliverable types had magic:None — presence-only checks that a renamed
    text file would pass.  Each gets a dedicated substance verifier:"""

    chk = None
    for item in _DELIVERY_DELIVERABLES:
        if item["key"] == key:
            chk = item.get("content_check")
            break

    if chk == "fish_tags":
        # Must contain actual Fish Audio [fish] tags — a plain text file renamed
        # as FISH-TAGGED.md would have no bracket tags at all.
        import re
        fish_pattern = re.compile(r'\[fish\b[^\]]*\]', re.IGNORECASE)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            matches = fish_pattern.findall(text)
            if len(matches) < 3:
                reasons.append(
                    f"AF-BUNDLE-INCOMPLETE: {key} — {path.name} has only "
                    f"{len(matches)} [fish] tags (min 3 expected).  A renamed "
                    f"plain text file is not a fish-tagged speech."
                )
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"AF-BUNDLE-INCOMPLETE: {key} — cannot read {path.name} "
                           f"for fish-tag verification: {exc!r}")

    elif chk == "teleprompter":
        # Must be a real HTML document with teleprompter structure — not a
        # renamed plaintext file or empty <html><head></head><body></body></html>.
        import re
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            if not re.search(r'<\s*html', text, re.IGNORECASE):
                reasons.append(
                    f"AF-BUNDLE-INCOMPLETE: {key} — {path.name} is not HTML "
                    f"(no <html> tag found).  A renamed text file is not a teleprompter."
                )
                return
            # Teleprompter must have presenter-view structure: slide containers
            # or cue markers.  At minimum, <div>, <section>, or .slide CSS.
            if not re.search(r'<\s*(?:div|section|article)', text, re.IGNORECASE) \
               and 'slide' not in text.lower():
                reasons.append(
                    f"AF-BUNDLE-INCOMPLETE: {key} — {path.name} lacks slide "
                    f"structure (no <div>/<section> elements, no 'slide' text).  "
                    f"An empty HTML skeleton is not a teleprompter."
                )
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"AF-BUNDLE-INCOMPLETE: {key} — cannot read {path.name} "
                           f"for HTML verification: {exc!r}")

    elif chk == "mp4_ftyp":
        # Video-specific ftyp-box check (magic at offset 4).  Also validate
        # that the file has a moov atom — a container with ftyp but no moov
        # is a header-only stub.
        try:
            with open(path, "rb") as fh:
                head = fh.read(8)
            if len(head) < 8 or head[4:8] != b"ftyp":
                reasons.append(
                    f"AF-BUNDLE-INCOMPLETE: {key} — {path.name} is not a valid "
                    f"MP4 (no 'ftyp' box at offset 4, got {head[4:8]!r}).  "
                    f"A renamed non-MP4 file is not a video."
                )
            # Quick moov signature scan: a real MP4 container has a moov atom.
            # Scan the first 256 KiB for 'moov'; a stub without media data
            # often has ftyp but no moov.
            if path.stat().st_size >= 8192:
                with open(path, "rb") as fh:
                    chunk = fh.read(262144)
                if b"moov" not in chunk:
                    reasons.append(
                        f"AF-BUNDLE-INCOMPLETE: {key} — {path.name} has ftyp "
                        f"but no 'moov' atom in first 256 KiB.  A header-only "
                        f"stub is not a rendered video."
                    )
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"AF-BUNDLE-INCOMPLETE: {key} — cannot read {path.name} "
                           f"for video verification: {exc!r}")


def _verify_delivery(run_dir: Path) -> Tuple[bool, List[str]]:
    """P9-DELIVER: hard-fail on ANY missing or substance-less whitelist deliverable.

    Checks ALL 10 deliverables in _DELIVERY_DELIVERABLES.  Each is verified for
    existence, non-empty, min bytes, magic-byte signature (where applicable),
    AND content substance (where content_check is configured).  A missing or
    substance-less deliverable produces FAIL with the specific deficiency —
    never (True, []).

    NO escape hatches remain.  The owner_skip_approval bypass has been removed
    and the helper function deleted.  Every single deliverable on the whitelist
    is mechanically verified for both presence AND substance.

    The prior design (return (True, []) unconditionally) is DELETED."""
    reasons: List[str] = []

    for item in _DELIVERY_DELIVERABLES:
        key = item["key"]
        pattern = item["pattern"]
        min_bytes = item["min_bytes"]
        magic = item.get("magic")
        magic_desc = item.get("magic_desc", "")

        hits = sorted(run_dir.glob(pattern))
        if not hits:
            reasons.append(
                f"AF-BUNDLE-INCOMPLETE: {key} — no file matching '{pattern}' found "
                f"in run_dir. Expected: {magic_desc or 'any real file'} "
                f"(min {min_bytes} bytes)."
            )
            continue

        candidate = hits[0]
        size = candidate.stat().st_size
        if size == 0:
            reasons.append(f"AF-BUNDLE-INCOMPLETE: {key} — {candidate.name} is zero bytes")
            continue
        if size < min_bytes:
            reasons.append(
                f"AF-BUNDLE-INCOMPLETE: {key} — {candidate.name} is {size} bytes "
                f"(minimum {min_bytes} bytes)"
            )
            continue

        # Magic-byte check when applicable
        if magic is not None:
            try:
                with open(candidate, "rb") as fh:
                    head = fh.read(len(magic))
                if len(head) < len(magic):
                    reasons.append(
                        f"AF-BUNDLE-INCOMPLETE: {key} — {candidate.name} is too short "
                        f"({size} bytes) for magic-byte check ({magic_desc})"
                    )
                    continue
                if head != magic:
                    reasons.append(
                        f"AF-BUNDLE-INCOMPLETE: {key} — {candidate.name} is not a valid "
                        f"{magic_desc} (expected {magic!r} at offset 0, got {head!r})"
                    )
                    continue
            except OSError as exc:  # noqa: BLE001
                reasons.append(
                    f"AF-BUNDLE-INCOMPLETE: {key} — cannot read {candidate.name} "
                    f"for magic-bytes check: {exc!r}"
                )
                continue

        # Content-substance check for deliverables that had magic:None.
        # These three are the former presence-only checks — a renamed text
        # file would pass size+absence-of-magic alone.
        _deliverable_content_check(key, candidate, reasons)

    hard = [r for r in reasons if not r.startswith("NOTE")]
    return (len(hard) == 0), reasons


def _verify_json_artifact(pattern: str, required_keys: tuple = ()):
    """Factory returning a verifier that checks a JSON artifact."""
    def _v(run_dir: Path) -> Tuple[bool, List[str]]:
        return _check_json_nonempty(run_dir, pattern, required_keys)
    return _v


def _verify_text_artifact(pattern: str, min_bytes: int = 50,
                          scale_by_slides: bool = False):
    """Factory returning a verifier that checks a text artifact. When
    scale_by_slides is True, min_bytes is scaled by the deck's slide count
    (MIN_BYTES was tuned for a ~34-slide reference deck; a fully-populated
    smaller deck legitimately renders smaller — E2E finding)."""
    def _v(run_dir: Path) -> Tuple[bool, List[str]]:
        if not scale_by_slides:
            return _check_text_nonempty(run_dir, pattern, min_bytes)
        try:
            _n = 0
            for _cand in sorted((run_dir / "working/copy").glob("slides*.json")):
                import json as _json
                _data = _json.load(open(_cand))
                if isinstance(_data, list):
                    _n = len(_data)
                elif isinstance(_data, dict) and _data.get("slides"):
                    _n = len(_data["slides"])
                if _n:
                    break
            _n = _n or 1
            _scaled = max(int(min_bytes * _n // 34), 8192)
        except Exception:  # noqa: BLE001 — fall back to the fixed floor
            _scaled = min_bytes
        return _check_text_nonempty(run_dir, pattern, _scaled)
    return _v


# ---------------------------------------------------------------------------
# Signature Presentation (Skill 51) substance verifiers. Each DELEGATES to the
# build_deck _chk_sp_* wrapper (single source of truth), which itself DEFERS
# (returns "") for any non-signature deck — so these pass for non-signature decks
# exactly as before. Falls back to a filesystem check when build_deck is unavailable.
# ---------------------------------------------------------------------------
def _verify_sp_intake(run_dir: Path) -> Tuple[bool, List[str]]:
    """P-SP-INTAKE: the 8-Questions-in-ONE-block intake gate (via _chk_sp_intake)."""
    fn = _bd_fn("_chk_sp_intake")
    if fn is None:
        return _check_json_nonempty(run_dir, "working/copy/sp_intake.json")
    result = fn(run_dir)
    return (True, []) if _checker_pass(result) else (False, [str(result)])


def _verify_sp_structure(run_dir: Path) -> Tuple[bool, List[str]]:
    """P-SP-STRUCTURE: the SACRED 4-phase structure contract (via _chk_sp_structure)."""
    fn = _bd_fn("_chk_sp_structure")
    if fn is None:
        return _check_json_nonempty(run_dir, "working/copy/sp_structure.json", ("slides",))
    result = fn(run_dir)
    return (True, []) if _checker_pass(result) else (False, [str(result)])


def _verify_sp_no_pitch(run_dir: Path) -> Tuple[bool, List[str]]:
    """P-SP-P3-HYGIENE: Phase-3 (teaching) no-pitch hygiene (via _chk_sp_no_pitch)."""
    fn = _bd_fn("_chk_sp_no_pitch")
    if fn is None:
        return _check_json_nonempty(run_dir, "working/copy/sp_structure.json", ("slides",))
    result = fn(run_dir)
    return (True, []) if _checker_pass(result) else (False, [str(result)])


# ---------------------------------------------------------------------------
# PHASE_VERIFIERS registry — keyed by manifest phase id (PIPELINE-MANIFEST.json version read at runtime from the resolved manifest; canonical at time of writing: 25)
# ---------------------------------------------------------------------------

def _verify_fish_tag(run_dir: Path) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    tagged_p = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH-FISH-TAGGED.md"
    source_p = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH.md"
    if not tagged_p.exists():
        reasons.append("AF-BUNDLE-INCOMPLETE: PRESENTERS-SPEECH-FISH-TAGGED.md not found")
        return False, reasons
    if not source_p.exists():
        reasons.append("AF-BUNDLE-INCOMPLETE: PRESENTERS-SPEECH.md (source) not found")
        return False, reasons
    size = tagged_p.stat().st_size
    if size < 2048: reasons.append(f"PRESENTERS-SPEECH-FISH-TAGGED.md: {size} bytes < 2048")
    try: tagged_text = tagged_p.read_text(encoding="utf-8",errors="replace"); source_text = source_p.read_text(encoding="utf-8",errors="replace")
    except:
        reasons.append("AF-FISH-TAG: cannot read tagged or source speech file")
        return False, reasons
    import re
    def strip_tags(t):
        t = re.sub(r'\[.*?\]', ' ', t); t = re.sub(r'\(.*?\)', ' ', t)
        return re.sub(r'\s+', ' ', t).strip()
    if strip_tags(tagged_text) != strip_tags(source_text):
        reasons.append("AF-FISH-TAG: strip-equals prover failed")
    return (len(reasons) == 0), reasons


def _verify_ghl_upload(run_dir: Path) -> Tuple[bool, List[str]]:
    """FIX-11 verifier: the local GHL ledger AND — when the LOCATION PIT resolves —
    a READ-ONLY media-library list-back proving the deck is genuinely in the GHL
    library (the QC gate: "the deck appears in the listing").

    The local ledger (working/checkpoints/media_library.json) is the fast first
    check. When `pptx_ghl_media_id` + the canonical GHL env names resolve, this
    verifier additionally calls the read-only GET /medias/files list-back (via the
    shared ghl_media.list_media) and confirms the deck entry is present by name or
    fileId. The list-back is deliberately FAIL-SOFT (NOTE on any transport/scope
    issue): a box with no GHL env, or whose LOCATION PIT lacks medias.read, must
    not block the run — but on a box where the PIT DOES resolve, a missing deck in
    the listing is a real AF-BUNDLE-COMPLETE finding, not a silent pass. It NEVER
    mutates the media library (read-only GET only)."""
    ledger_p = run_dir / "working" / "checkpoints" / "media_library.json"
    if not ledger_p.exists(): return True, ["NOTE: media_library.json not found"]
    try: obj = json.loads(ledger_p.read_text(encoding="utf-8",errors="replace"))
    except: return True, ["NOTE: media_library.json unreadable"]
    reasons: List[str] = []
    if not isinstance(obj, dict): return True, reasons
    if "ghl_folder_id" not in obj: reasons.append("NOTE: ghl_folder_id absent")
    pptx_id = str(obj.get("pptx_ghl_media_id") or obj.get("pptx_ghl_url") or "").strip()
    pptx_name = str(obj.get("pptx_ghl_remote_name") or "").strip()
    if not pptx_id:
        reasons.append("AF-BUNDLE-COMPLETE: media_library.json has no pptx_ghl_media_id "
                       "— the final assembled deck was never recorded as uploaded to GHL.")
        return (len(reasons) == 0), reasons
    # READ-ONLY LIST-BACK (FIX-11 QC gate). Lazy + fail-soft: only when the shared
    # module AND the canonical LOCATION PIT resolve. Never blocks on absence.
    try:
        import ghl_media
        pit = ghl_media.resolve_location_pit()
        loc = ghl_media.resolve_location_id()
    except Exception as exc:  # noqa: BLE001
        return True, reasons + [f"NOTE: GHL list-back skipped (env/import: {exc})"]
    if not pit or not loc:
        return True, reasons + ["NOTE: GHL list-back skipped (no LOCATION PIT/location id)"]
    try:
        listing = ghl_media.list_media(loc, pit, media_type="file", limit=200)
    except Exception as exc:  # noqa: BLE001 — read-only transport issue -> NOTE, never block
        return True, reasons + [f"NOTE: GHL read-only list-back failed ({exc})"]
    entries = listing.get("data") or []
    found = [
        e for e in entries if isinstance(e, dict)
        and (str(e.get("fileId") or e.get("_id") or "") == pptx_id
             or (pptx_name and str(e.get("name") or "") == pptx_name))
    ]
    if not found:
        reasons.append(
            "AF-BUNDLE-COMPLETE: the final deck is NOT present in the GHL media "
            "library listing (read-only GET /medias/files) — the local ledger claims "
            f"pptx_ghl_media_id={pptx_id[:24]}… but the library has no matching entry. "
            "An upload record that does not survive a real list-back is not an upload.")
    return (len(reasons) == 0), reasons
def _verify_workbook(run_dir: Path) -> Tuple[bool, List[str]]:
    """WORKBOOK REDESIGN verifier (AF-WORKBOOK-BOTH): BOTH deliverables must exist and
    verify — the regular (*-WORKBOOK.pdf) AND the fillable (*-WORKBOOK-FILLABLE.pdf).

    The dual contract is the anti-wireframe substance proof: the regular PDF carries the
    designed content-baked pages, the fillable adds the AcroForm overlay. Either side
    missing / zero-byte / garbled fails the phase attestation. pypdf is a hard dependency
    of the assembly step; a box without it records a NOTE and degrades to the
    existence+size check rather than crashing the phase."""
    reasons: List[str] = []
    dl = run_dir / "working" / "deliverables"
    regulars = sorted(dl.glob("*-WORKBOOK.pdf")) if dl.is_dir() else []
    fillables = sorted(dl.glob("*-WORKBOOK-FILLABLE.pdf")) if dl.is_dir() else []
    if not regulars:
        reasons.append("regular workbook PDF (*-WORKBOOK.pdf) not found in working/deliverables")
    if not fillables:
        reasons.append("fillable workbook PDF (*-WORKBOOK-FILLABLE.pdf) not found — "
                       "AF-WORKBOOK-BOTH requires BOTH deliverables")
    if not regulars or not fillables:
        return (False, reasons)

    def _read(pdf: Path) -> Tuple[int, int, bool]:
        from pypdf import PdfReader
        r = PdfReader(str(pdf))
        fields = r.get_fields() or {}
        need_app = False
        try:
            need_app = bool(r.trailer["/Root"]["/AcroForm"]["/NeedAppearances"])
        except Exception:  # noqa: BLE001
            need_app = False
        return (len(r.pages), len(fields), need_app)

    for pdf in regulars + fillables:
        size = pdf.stat().st_size
        if size < 2048:
            reasons.append(f"workbook PDF {pdf.name} is only {size} bytes — too small")
    if reasons:
        return (False, reasons)
    try:
        reg_pages, reg_fields, _ = _read(regulars[0])
        if reg_pages < 1:
            reasons.append(f"regular workbook {regulars[0].name}: pypdf read {reg_pages} pages")
        if reg_fields != 0:
            reasons.append(f"regular workbook {regulars[0].name}: pypdf read {reg_fields} "
                           "AcroForm fields — the regular PDF must be image-only (no overlay)")
        fill_pages, fill_fields, need_app = _read(fillables[0])
        if fill_pages < 1:
            reasons.append(f"fillable workbook {fillables[0].name}: pypdf read {fill_pages} pages")
        if fill_fields < 1:
            reasons.append(f"fillable workbook {fillables[0].name}: pypdf read ZERO AcroForm "
                           "fields — the fillable form did not survive")
        if not need_app:
            reasons.append(f"fillable workbook {fillables[0].name}: /NeedAppearances not set — "
                           "fields will not render in viewers")
        if reasons:
            return (False, reasons)
        return (True, [])
    except ImportError:
        return (True, ["NOTE: pypdf not importable — workbook verifier degraded to "
                       "existence+size check (pass)"])
    except Exception as exc:  # noqa: BLE001
        return (False, [f"workbook verifier raised {exc!r}"])




def _verify_sp_claim(run_dir: Path) -> Tuple[bool, List[str]]:
    fn = _bd_fn("_chk_sp_claim")
    if fn is None: return _check_json_nonempty(run_dir, "working/copy/sp_claims.json")
    result = fn(run_dir)
    return (True, []) if _checker_pass(result) else (False, [str(result)])


def _verify_sp_intake_trace(run_dir: Path) -> Tuple[bool, List[str]]:
    fn = _bd_fn("_chk_sp_intake_trace")
    if fn is None: return _check_json_nonempty(run_dir, "working/interview/intake_transcript.json")
    result = fn(run_dir)
    return (True, []) if _checker_pass(result) else (False, [str(result)])



def _verify_fish_tag(run_dir: Path) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    tagged_p = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH-FISH-TAGGED.md"
    source_p = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH.md"
    if not tagged_p.exists():
        reasons.append("AF-BUNDLE-INCOMPLETE: PRESENTERS-SPEECH-FISH-TAGGED.md not found")
        return False, reasons
    if not source_p.exists():
        reasons.append("AF-BUNDLE-INCOMPLETE: PRESENTERS-SPEECH.md (source) not found")
        return False, reasons
    size = tagged_p.stat().st_size
    if size < 2048: reasons.append(f"PRESENTERS-SPEECH-FISH-TAGGED.md: {size} bytes < 2048")
    try: tagged_text = tagged_p.read_text(encoding="utf-8",errors="replace"); source_text = source_p.read_text(encoding="utf-8",errors="replace")
    except:
        reasons.append("AF-FISH-TAG: cannot read tagged or source speech file")
        return False, reasons
    import re
    def strip_tags(t):
        t = re.sub(r'\[.*?\]', ' ', t); t = re.sub(r'\(.*?\)', ' ', t)
        return re.sub(r'\s+', ' ', t).strip()
    if strip_tags(tagged_text) != strip_tags(source_text):
        reasons.append("AF-FISH-TAG: strip-equals prover failed")
    return (len(reasons) == 0), reasons


def _verify_ghl_upload(run_dir: Path) -> Tuple[bool, List[str]]:
    """FIX-11 verifier: the local GHL ledger AND — when the LOCATION PIT resolves —
    a READ-ONLY media-library list-back proving the deck is genuinely in the GHL
    library (the QC gate: "the deck appears in the listing").

    The local ledger (working/checkpoints/media_library.json) is the fast first
    check. When `pptx_ghl_media_id` + the canonical GHL env names resolve, this
    verifier additionally calls the read-only GET /medias/files list-back (via the
    shared ghl_media.list_media) and confirms the deck entry is present by name or
    fileId. The list-back is deliberately FAIL-SOFT (NOTE on any transport/scope
    issue): a box with no GHL env, or whose LOCATION PIT lacks medias.read, must
    not block the run — but on a box where the PIT DOES resolve, a missing deck in
    the listing is a real AF-BUNDLE-COMPLETE finding, not a silent pass. It NEVER
    mutates the media library (read-only GET only)."""
    ledger_p = run_dir / "working" / "checkpoints" / "media_library.json"
    if not ledger_p.exists(): return True, ["NOTE: media_library.json not found"]
    try: obj = json.loads(ledger_p.read_text(encoding="utf-8",errors="replace"))
    except: return True, ["NOTE: media_library.json unreadable"]
    reasons: List[str] = []
    if not isinstance(obj, dict): return True, reasons
    if "ghl_folder_id" not in obj: reasons.append("NOTE: ghl_folder_id absent")
    pptx_id = str(obj.get("pptx_ghl_media_id") or obj.get("pptx_ghl_url") or "").strip()
    pptx_name = str(obj.get("pptx_ghl_remote_name") or "").strip()
    if not pptx_id:
        reasons.append("AF-BUNDLE-COMPLETE: media_library.json has no pptx_ghl_media_id "
                       "— the final assembled deck was never recorded as uploaded to GHL.")
        return (len(reasons) == 0), reasons
    # READ-ONLY LIST-BACK (FIX-11 QC gate). Lazy + fail-soft: only when the shared
    # module AND the canonical LOCATION PIT resolve. Never blocks on absence.
    try:
        import ghl_media
        pit = ghl_media.resolve_location_pit()
        loc = ghl_media.resolve_location_id()
    except Exception as exc:  # noqa: BLE001
        return True, reasons + [f"NOTE: GHL list-back skipped (env/import: {exc})"]
    if not pit or not loc:
        return True, reasons + ["NOTE: GHL list-back skipped (no LOCATION PIT/location id)"]
    try:
        listing = ghl_media.list_media(loc, pit, media_type="file", limit=200)
    except Exception as exc:  # noqa: BLE001 — read-only transport issue -> NOTE, never block
        return True, reasons + [f"NOTE: GHL read-only list-back failed ({exc})"]
    entries = listing.get("data") or []
    found = [
        e for e in entries if isinstance(e, dict)
        and (str(e.get("fileId") or e.get("_id") or "") == pptx_id
             or (pptx_name and str(e.get("name") or "") == pptx_name))
    ]
    if not found:
        reasons.append(
            "AF-BUNDLE-COMPLETE: the final deck is NOT present in the GHL media "
            "library listing (read-only GET /medias/files) — the local ledger claims "
            f"pptx_ghl_media_id={pptx_id[:24]}… but the library has no matching entry. "
            "An upload record that does not survive a real list-back is not an upload.")
    return (len(reasons) == 0), reasons


def _verify_sp_claim(run_dir: Path) -> Tuple[bool, List[str]]:
    fn = _bd_fn("_chk_sp_claim")
    if fn is None: return _check_json_nonempty(run_dir, "working/copy/sp_claims.json")
    result = fn(run_dir)
    return (True, []) if _checker_pass(result) else (False, [str(result)])


def _verify_sp_intake_trace(run_dir: Path) -> Tuple[bool, List[str]]:
    fn = _bd_fn("_chk_sp_intake_trace")
    if fn is None: return _check_json_nonempty(run_dir, "working/interview/intake_transcript.json")
    result = fn(run_dir)
    return (True, []) if _checker_pass(result) else (False, [str(result)])


def _verify_webinar_video(run_dir: Path) -> Tuple[bool, List[str]]:
    """Feature L2-G verifier (P9.6-WEBINAR-VIDEO): the webinar mp4 exists, is non-empty,
    is a real MP4 (ftyp box), and the timing track records a sane per-slide mapping.

    The video lives at working/delivery/<deck_slug>-WEBINAR.mp4 and its timing track at
    working/checkpoints/webinar_timing.json. The build_webinar_video.py executor already
    runs the AF-WEBINAR-SIZE gate + ffprobe verification; this verifier is the
    runner-side substance proof so a phase attestation cannot pass on a missing /
    zero-byte / non-MP4 video or an empty timing track."""
    reasons: List[str] = []

    candidates = sorted((run_dir / "working" / "delivery").glob("*-WEBINAR.mp4")) \
        if (run_dir / "working" / "delivery").is_dir() else []
    if not candidates:
        reasons.append("webinar video (*-WEBINAR.mp4) not found in working/delivery")
        return (False, reasons)
    video = candidates[0]
    size = video.stat().st_size
    if size < 4096:
        reasons.append(f"webinar video {video.name} is only {size} bytes — too small for a "
                       "real rendered mp4 (no slide content)")
        return (False, reasons)
    # MP4 ftyp-box magic (mirrors ghl_media.verify_video).
    try:
        with open(video, "rb") as fh:
            head = fh.read(8)
        if len(head) < 8 or head[4:8] != b"ftyp":
            reasons.append(f"webinar video {video.name} is not a real MP4 (no 'ftyp' box "
                           "at offset 4) — a decoy/stub is not a video")
            return (False, reasons)
    except OSError as exc:  # noqa: BLE001
        reasons.append(f"webinar video {video.name} unreadable: {exc!r}")
        return (False, reasons)

    # Timing track: present, parseable, contiguous 1..N with non-empty durations.
    timing_p = run_dir / "working" / "checkpoints" / "webinar_timing.json"
    obj = _read_json(timing_p)
    timing = obj.get("timing") if isinstance(obj, dict) else None
    if not isinstance(timing, list) or not timing:
        reasons.append("webinar timing track (working/checkpoints/webinar_timing.json) is "
                       "absent or has no timing[] entries")
        return (False, reasons)
    expected = 1
    for i, entry in enumerate(timing):
        if not isinstance(entry, dict):
            reasons.append(f"timing[{i}] is not an object")
            return (False, reasons)
        if entry.get("slide") != expected:
            reasons.append(f"timing slides must be contiguous 1..N; got slide "
                           f"{entry.get('slide')!r} at index {i} (expected {expected})")
            return (False, reasons)
        dur = entry.get("duration")
        if not isinstance(dur, (int, float)) or dur <= 0:
            reasons.append(f"timing[{i}] duration must be > 0, got {dur!r}")
            return (False, reasons)
        expected += 1
    return (len(reasons) == 0), reasons


def _verify_webinarized_speech(run_dir: Path) -> Tuple[bool, List[str]]:
    """Feature L2-H verifier (P9-SPEECH-WEBINAR-INTRO): the webinarized speech audio
    exists, is a valid MP3, AND the host framing (welcome / chat Q&A / crescendo close)
    is structurally proven.

    The audio lives at working/delivery/PRESENTER-AUDIO-WEBINAR.mp3, produced by
    synthesize_full_speech.py --webinar-intro-outro (the P9-SPEECH-WEBINAR-INTRO
    executor). The executor injects the framing in-memory (the on-disk UNTAGGED
    PRESENTERS-SPEECH.md is never modified), so the MP3 duration gate already counts
    the framing words; this verifier adds the runner-side substance proof:

      1. the webinarized audio exists, is non-empty, and passes the shared MP3
         validity probe (synthesize_full_speech.verify_mp3) — a plain deck-only
         audio renamed as the webinar audio is a defect;
      2. the framing layer is the wired one: webinar_intro_outro.build_framing_markdown()
         must carry the three `## Section ... (WEBINAR FRAMING)` headers (WELCOME /
         QNA / CLOSE) and every section must hit its word budget within tolerance.

    Defensive: a missing sibling module (synthesize_full_speech / webinar_intro_outro)
    degrades to a NOTE, never a crash and never a silent pass on a real substance
    failure."""
    reasons: List[str] = []

    candidates = sorted((run_dir / "working" / "delivery").glob("PRESENTER-AUDIO-WEBINAR.mp3")) \
        if (run_dir / "working" / "delivery").is_dir() else []
    if not candidates:
        reasons.append("webinarized speech audio (working/delivery/PRESENTER-AUDIO-WEBINAR.mp3) "
                       "not found — the webinar host framing was never synthesized")
        return (False, reasons)
    audio = candidates[0]
    size = audio.stat().st_size
    if size < 10000:
        reasons.append(f"webinarized speech audio {audio.name} is only {size} bytes — too "
                       "small for a full webinarized render (framing + deck)")
        return (False, reasons)

    # MP3 validity via the shared probe (the same probe the synthesis executor runs on
    # every chunk and the final deliverable). Defensive import: a missing module is a
    # NOTE-degrade, never a crash and never a silent pass on a bad file.
    try:
        import synthesize_full_speech as _syn
        probe_reason = _syn.verify_mp3(str(audio))
        if probe_reason:
            reasons.append(f"webinarized speech audio {audio.name} is not a valid MP3: "
                           f"{probe_reason} — a plain deck-only audio renamed as the "
                           "webinar audio is a defect")
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"NOTE: synthesize_full_speech.verify_mp3 unavailable ({exc!r}) — "
                       "webinarized-audio probe degraded (size check only)")

    # Framing structure proof: the framing layer must be the wired one (welcome before
    # the deck, chat Q&A + crescendo close after), with in-band word budgets. This is
    # the substance half that makes a plain audio un-skippable as the webinar audio.
    try:
        import webinar_intro_outro as _w
        framing = _w.build_framing_markdown()
        for label in ("WELCOME", "QNA", "CLOSE"):
            if f"## Section {label}" not in framing:
                reasons.append(f"AF-WEBINAR-INTRO: framing layer is missing the {label} "
                               "section — the webinar host framing is not the wired "
                               "generator")
        report = _w.verify_sections()
        for name, r in report.items():
            if not r["within_band"]:
                reasons.append(f"AF-WEBINAR-INTRO: {name} framing section is {r['words']} "
                               f"words, outside the +/-{_w.TOLERANCE:.0%} band of target "
                               f"{r['target']}")
            if r["n_distinct_tags"] < 2:
                reasons.append(f"AF-WEBINAR-INTRO: {name} framing section has flat reader "
                               "tags (fewer than 2 distinct) — the host delivery would "
                               "read monotonically")
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"NOTE: webinar_intro_outro unavailable ({exc!r}) — framing "
                       "structure check degraded (audio existence + MP3 probe only)")

    hard = [r for r in reasons if not r.startswith("NOTE")]
    return (len(hard) == 0), reasons


PHASE_VERIFIERS: dict[str, Callable] = {
    # Phase -1    Content-to-Presentation Conversion
    "P-CONVERTER":        _verify_json_artifact("working/copy/intake.json", ("slides",)),
    # Phase -0.5  Deep Research
    "P-0.5-RESEARCH":     _verify_research,
    # Phase 0.1   Intake / Interview Confirm
    "P0A-INTAKE":         _verify_json_artifact("working/copy/intake.json"),
    # Phase 0.2   Priority-Shift Spec
    "P0B-PRIORITY":       _verify_json_artifact("working/copy/priority_shift_spec.json"),
    # Phase 3     Converting Arc Allocation
    "P3-ARC":             _verify_json_artifact("working/copy/arc_allocation.json"),
    # Phase 3.5   Research-to-Slide Mapping
    "P-3.5-RESEARCH-MAP": _verify_json_artifact("working/research/research_map.json"),
    # Phase 4     Slide Copy
    "P4-COPY":            _verify_copy,
    # Phase 4.2   Copy QC — uses the same engine as P4-COPY
    "P1Q-COPY-QC":        _verify_copy,
    # Phase 4.5   Typography / Design Brief
    "PF-DESIGN":          _verify_text_artifact("working/research/design-brief-*.md", 50),
    # Phase 4.6   Typography QC
    "P-TYPO-QC":          _verify_json_artifact("working/qc/typography_qc_report.json"),
    # Phase 4.7   Prompt Authoring
    "P4-PROMPT":          _verify_prompt,
    # Phase 4.8   Prompt QC
    "P-PROMPT-QC":        _verify_prompt,
    # Phase 4.85  Style Preview
    "P-STYLE-PREVIEW":    _verify_json_artifact("working/style-preview/style_samples_manifest.json"),
    # Phase 4.9   Deterministic Render
    "P4-RENDER":          _verify_render,
    # Phase 4.95  Image QC
    "P-IMAGE-QC":         _verify_render,
    # Phase 7.5   Priority-Shift Ship Gate
    "P-SHIFT-QC":         _verify_json_artifact("working/qc/priority_shift_report.json"),
    # Phase 8     PPTX Assembly
    "P8-ASSEMBLE":        _verify_assemble,
    # Phase 8.5   Presenter Speech
    "P9-SPEECH":          _verify_text_artifact("working/presenter-speech/PRESENTERS-SPEECH.md", 200),
    # Phase 8.6   Speech QC
    "P-SPEECH-QC":        _verify_json_artifact("working/qc/speech_qc_report.json"),
    # Phase 8.65  Final QC Aggregation (combines the six domain QC reports)
    "P-QC-AGGREGATE":     _verify_json_artifact("working/qc/final_qc_report.json", ("schema", "pass")),
    # Phase 8.7   Notes-Pane Sync (reorder — AF-EMPTY-NOTES-PANE)
    "P9.5-NOTES-SYNC":    _verify_notes_sync,
    # Phase 9     Delivery
    "P9-DELIVER":         _verify_delivery,
    # Phase 0.15  Signature-Presentation Intake Gate (Skill 51)
    "P-SP-INTAKE":        _verify_sp_intake,
    # Phase 4.1   Signature-Presentation SACRED Structure (Skill 51)
    "P-SP-STRUCTURE":     _verify_sp_structure,
    # Phase 4.15  Signature-Presentation Phase-3 No-Pitch Hygiene (Skill 51)
    "P-SP-P3-HYGIENE":    _verify_sp_no_pitch,
    # --- U012 new phases ---
    "P7-TELEPROMPTER":    _verify_text_artifact("working/deliverables/presenter-teleprompter.html", 10240),
    "P8.1-PDF-EXPORT":    _verify_text_artifact("working/deliverables/*-FINAL.pdf", 51200),
    "P8.2-GUIDE":         _verify_text_artifact("working/deliverables/PRESENTER-GUIDE.pdf", 51200, scale_by_slides=True),
    "P8.4-FISH-TAG":      _verify_fish_tag,
    # --- Feature L2-H: webinarized speech audio (welcome + Q&A + crescendo close) ---
    "P9-SPEECH-WEBINAR-INTRO": _verify_webinarized_speech,
    "P9.1-SPEECH-PDF":    _verify_text_artifact("working/deliverables/PRESENTERS-SPEECH.pdf", 20480),
    "P9.2-GHL-UPLOAD":    _verify_ghl_upload,
    # --- Feature L2-D: fillable PDF workbook ---
    "P8.25-WORKBOOK":     _verify_workbook,
    # --- Feature L2-G: webinar video ---
    "P9.6-WEBINAR-VIDEO": _verify_webinar_video,
    # --- U012 SP registry gaps ---
    "P-SP-CLAIM":         _verify_sp_claim,
    "P-SP-INTAKE-TRACE":  _verify_sp_intake_trace,
}


# ---------------------------------------------------------------------------
# Public entry point (called by run_signature_deck.py)
# ---------------------------------------------------------------------------

def verify(phase_id: str, run_dir: Path) -> Tuple[bool, List[str]]:
    """Run the substance verifier for phase_id.

    Returns (ok: bool, reasons: list[str]).
      ok=True, reasons=[]          — PASS (substance confirmed)
      ok=True, reasons=[NOTE ...]  — PASS with degraded notes (checker unavailable)
      ok=False, reasons=[...]      — FAIL; reasons lists every finding

    For phase ids not in PHASE_VERIFIERS, returns (False, ["no verifier — pass"])
    so the runner blocks unmapped phases (fail-closed per U013 step 9).

    BEFORE dispatching to the per-phase verifier, this function checks the run's
    attestation record (process_manifest.json) for SIMULATED entries.  A SIMULATED
    result without a valid allowed_simulated declaration FAILS the phase — this
    check runs first so no verifier can silently accept a SIMULATED attestation."""
    fn: Optional[Callable] = PHASE_VERIFIERS.get(phase_id)
    if fn is None:
        return False, [f"no verifier registered for {phase_id!r} — pass"]

    # ---- ANTI-DRIFT CORE (WORK-ITEM-14c): SIMULATED rejection ----
    # Check BEFORE the per-phase verifier so a SIMULATED attestation cannot be
    # bypassed by a verifier that returns (True, []).
    sim_ok, sim_reasons = _check_simulated_rejection(phase_id, run_dir)
    if not sim_ok:
        # SIMULATED without valid allowed_simulated — hard FAIL.
        return False, sim_reasons
    # If sim_ok but sim_reasons is non-empty, the phase was SIMULATED but
    # legitimately (allowed_simulated with credential cited).  Return the
    # NOTE-degraded pass directly — a SIMULATED phase does not get substance-
    # checked because the whole point is the credential is absent.
    if sim_reasons:
        return True, sim_reasons
    # ---- end SIMULATED rejection ----

    try:
        result = fn(Path(run_dir))
        # Accept both (ok, reasons) tuple and legacy str return for compat.
        if isinstance(result, tuple) and len(result) == 2:
            ok, reasons = result
        elif isinstance(result, str):
            # Legacy str: '' == pass, non-empty == fail.
            ok, reasons = (result == ""), ([] if result == "" else [result])
        else:
            ok, reasons = bool(result), []

        # ---- FAIL-with-reason validation (WORK-ITEM-14c) ----
        # A bare FAIL without a reason is a verifier bug — the verifier returned
        # (False, []) with no explanation.  Escalate it.
        if not ok and len(reasons) == 0:
            return False, [
                f"VERIFIER BUG: {phase_id!r} returned FAIL with empty reasons "
                f"— escalated.  The verifier function must cite the specific "
                f"missing file, empty field, or violated gate code."
            ]
        # ---- end FAIL-with-reason validation ----

        return bool(ok), list(reasons)
    except Exception as exc:  # noqa: BLE001
        return False, [f"verifier for {phase_id!r} raised {exc!r} — degraded (pass)"]


# ---------------------------------------------------------------------------
# Legacy API (retained for prove-deck.py and any callers that use the old shape)
# ---------------------------------------------------------------------------

def verify_phase(run_dir: Path, phase_spec: dict) -> str:
    """Legacy API: returns '' on pass, a reason string on fail.
    Wraps the new verify() entry point."""
    phase_id = phase_spec.get("id", "")
    ok, reasons = verify(phase_id, Path(run_dir))
    hard = [r for r in reasons if not r.startswith("NOTE")]
    if ok or not hard:
        return ""
    return "; ".join(hard)


def verify_all_phases(run_dir: Path, phases: list) -> list:
    """Legacy API: run substance checks for all phases.
    Returns [(phase_id, reason), ...] for hard failures only."""
    failures = []
    for ph in phases:
        reason = verify_phase(run_dir, ph)
        if reason:
            failures.append((ph.get("id", "?"), reason))
    return failures


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _selftest() -> None:
    """Deterministic self-tests. Exits 0 on pass, 1 on failure."""
    import tempfile

    fails = []

    with tempfile.TemporaryDirectory(prefix="phase_verifiers_selftest_") as tmp:
        rd = Path(tmp)

        # T1: absent artifact => FAIL (FAIL-HARD: verifier is PRIMARY gate)
        ok, reasons = verify("P0A-INTAKE", rd)
        if ok:
            fails.append(f"T1: absent artifact should FAIL (FAIL-HARD rule), got ok={ok} reasons={reasons}")
        if not any("file not found" in r for r in reasons):
            fails.append(f"T1: absent artifact reason should say 'file not found', got reasons={reasons}")

        # T2: zero-byte JSON artifact => fail
        zb = rd / "working" / "copy" / "intake.json"
        zb.parent.mkdir(parents=True, exist_ok=True)
        zb.write_bytes(b"")
        ok, reasons = verify("P0A-INTAKE", rd)
        if ok:
            fails.append("T2: zero-byte intake.json should fail")

        # T3: valid JSON artifact => pass
        zb.write_text(json.dumps({"slides": [{"idx": 1}]}))
        ok, reasons = verify("P0A-INTAKE", rd)
        if not ok:
            fails.append(f"T3: valid intake.json should pass, got reasons={reasons}")

        # T4: unknown phase id => fail-closed (U013 step 9)
        ok, reasons = verify("UNKNOWN-PHASE-XYZ", rd)
        if ok:
            fails.append(f"T4: unknown phase should fail-closed, got ok={ok} reasons={reasons}")
        if not any("UNKNOWN-PHASE-XYZ" in r for r in reasons):
            fails.append(f"T4: unknown phase reason should name the phase, got reasons={reasons}")

        # T5: verify_all_phases with no artifacts => failures (FAIL-HARD)
        phases = [
            {"id": "P0A-INTAKE", "produces_artifact": "working/copy/intake.json"},
            {"id": "P0B-PRIORITY", "produces_artifact": "working/copy/priority_shift_spec.json"},
        ]
        rd2 = Path(tempfile.mkdtemp(prefix="phase_verifiers_selftest2_"))
        failures5 = verify_all_phases(rd2, phases)
        if not failures5:
            fails.append(f"T5: all-absent must produce failures (FAIL-HARD rule), got none")
        elif len(failures5) != 2:
            fails.append(f"T5: all-absent should produce 2 failures, got {len(failures5)}: {failures5}")

        # T6: render verifier with no PNGs -> fail (filesystem fallback)
        # Only fires when _crg is None (the module is absent in test context).
        if _crg is None and _bd is None:
            ok, reasons = verify("P4-RENDER", rd)
            if ok and not any("NOTE" in r for r in reasons):
                fails.append(f"T6: render with no PNGs should fail or note-degrade, got ok={ok} reasons={reasons}")

        # T7: _verify_delivery with no deliverables => fail (primary gate)
        ok, reasons = verify("P9-DELIVER", rd)
        if ok:
            fails.append(f"T7: _verify_delivery with no deliverables should FAIL, got ok={ok}")
        if not any("AF-BUNDLE-INCOMPLETE" in r for r in reasons):
            fails.append(f"T7: _verify_delivery missing deliverable should include AF-BUNDLE-INCOMPLETE, got reasons={reasons}")

        # T8: _verify_fish_tag with no files => fail (no more silent return True)
        ok, reasons = verify("P8.4-FISH-TAG", rd)
        if ok:
            fails.append(f"T8: fish-tag verifier with missing files should FAIL, got ok={ok}")
        if not any("not found" in r.lower() for r in reasons):
            fails.append(f"T8: fish-tag missing file should say 'not found', got reasons={reasons}")

    # T9: SIMULATED attestation must be mechanically rejected (WI-14c ANTI-DRIFT CORE)
    with tempfile.TemporaryDirectory(prefix="phase_verifiers_selftest_sim_") as t9tmp:
        t9rd = Path(t9tmp)
        # Create a valid artifact so the verifier itself would pass.
        intake_path = t9rd / "working" / "copy" / "intake.json"
        intake_path.parent.mkdir(parents=True, exist_ok=True)
        intake_path.write_text(json.dumps({"slides": [{"idx": 1}]}))

        # Place a SIMULATED attestation for this phase.
        ckpt = t9rd / "working" / "checkpoints"
        ckpt.mkdir(parents=True, exist_ok=True)
        (ckpt / "process_manifest.json").write_text(json.dumps({
            "phases": [
                {"phase_id": "P0A-INTAKE", "execution": "SIMULATED", "status": "complete"}
            ]
        }))

        ok, reasons = verify("P0A-INTAKE", t9rd)
        if ok:
            fails.append(
                f"T9: SIMULATED attestation must be HARD-FAILED, "
                f"but verify() returned ok={ok}.  Without WI-14c enforcement "
                f"the SIMULATED attestation would silently pass."
            )
        if not any("SIMULATED" in r for r in reasons):
            fails.append(
                f"T9: SIMULATED rejection reason must contain 'SIMULATED', "
                f"got reasons={reasons}"
            )

    if fails:
        for f in fails:
            print(f"[phase_verifiers selftest] FAIL: {f}", file=sys.stderr)
        sys.exit(1)
    print("[phase_verifiers selftest] PASS — all self-tests passed.", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif len(sys.argv) >= 3 and sys.argv[1] in ("--phase", "verify"):
        # Quick smoke: python3 phase_verifiers.py --phase PHASE_ID --run-dir DIR
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--phase", required=True)
        ap.add_argument("--run-dir", required=True)
        a = ap.parse_args()
        ok, reasons = verify(a.phase, Path(a.run_dir))
        for r in reasons:
            print(r)
        print(f"{'PASS' if ok else 'FAIL'} — phase {a.phase!r}")
        sys.exit(0 if ok else 6)
    else:
        print("Usage: phase_verifiers.py --selftest", file=sys.stderr)
        print("       phase_verifiers.py --phase PHASE_ID --run-dir DIR", file=sys.stderr)
        sys.exit(1)
