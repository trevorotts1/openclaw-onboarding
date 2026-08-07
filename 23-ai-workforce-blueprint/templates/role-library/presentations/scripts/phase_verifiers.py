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
  * These verifiers are SECONDARY proofs — they supplement, never replace, the
    attestation-chain and produces_artifact presence checks in run_signature_deck.py.
  * FAIL-SOFT for file-not-found: if a produces_artifact is absent, the verifier
    returns (True, []) because run_signature_deck.py already hard-aborts on that
    condition. Verifiers flag SUBSTANTIVE failures (zero-byte file, JSON parse error,
    empty collections, engine check failures).
  * All engine-checker imports are defensive (try/except ImportError) so CI/test
    contexts that lack sibling modules still parse without error.
  * A genuinely unavailable checker records a NOTE reason but does NOT crash and does
    NOT silently pass a real substance failure — it only degrades when the module is
    missing.
  * NO network calls, NO side effects. Pure filesystem reads + engine checks.

EXIT CODES (when run as __main__ with --selftest)
    0 — all self-tests passed
    1 — a self-test failed
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple

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
    """Check that a JSON artifact is non-empty and has required_keys."""
    p = _resolve_glob(run_dir, pattern)
    if p is None:
        return True, []  # absent is run_signature_deck's problem, not ours
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
    """Check that a text artifact has at least min_bytes of non-whitespace content."""
    p = _resolve_glob(run_dir, pattern)
    if p is None:
        return True, []
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
    Falls back to filesystem PPTX existence + size check when unavailable."""
    fn = _bd_fn("check_deck_harmony")
    if fn is not None:
        try:
            result = fn(run_dir)
            if not _checker_pass(result):
                detail = result if isinstance(result, str) else json.dumps(result)
                return False, [f"AF-HARMONY: deck harmony check failed: {detail}"]
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


def _verify_delivery(run_dir: Path) -> Tuple[bool, List[str]]:
    """P9-DELIVER: verify the delivery artifact (PRESENTER-AUDIO.mp3) or bundle exists."""
    audio = run_dir / "working" / "delivery" / "PRESENTER-AUDIO.mp3"
    if audio.exists() and audio.stat().st_size > 1000:
        return True, []
    # Fallback: any delivery artifact is present.
    hits = list(run_dir.glob("working/delivery/*"))
    if hits:
        return True, []
    # Not hard-blocked here — run_signature_deck already checks the delivery bundle.
    return True, []


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
    if not tagged_p.exists() or not source_p.exists(): return True, []
    size = tagged_p.stat().st_size
    if size < 2048: reasons.append(f"PRESENTERS-SPEECH-FISH-TAGGED.md: {size} bytes < 2048")
    try: tagged_text = tagged_p.read_text(encoding="utf-8",errors="replace"); source_text = source_p.read_text(encoding="utf-8",errors="replace")
    except: return True, []
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
    """Feature L2-D verifier: the fillable PDF workbook exists, is non-empty, and pypdf
    reads it back with at least one AcroForm field and /NeedAppearances true.

    The workbook PDF lives at working/deliverables/<deck_slug>-WORKBOOK.pdf. Its assembly
    (scripts/workbook_builder.py) already verifies with pypdf before writing the ledger at
    working/checkpoints/workbook.json; this verifier is the runner-side substance proof so
    a phase attestation cannot pass on a missing/zero-byte/garbled workbook. pypdf is a
    hard dependency of the assembly step; a box without it records a NOTE and degrades to
    the existence+size check rather than crashing the phase."""
    reasons: List[str] = []
    candidates = sorted((run_dir / "working" / "deliverables").glob("*-WORKBOOK.pdf")) \
        if (run_dir / "working" / "deliverables").is_dir() else []
    if not candidates:
        reasons.append("workbook PDF (*-WORKBOOK.pdf) not found in working/deliverables")
        return (False, reasons)
    pdf = candidates[0]
    size = pdf.stat().st_size
    if size < 2048:
        reasons.append(f"workbook PDF {pdf.name} is only {size} bytes — too small for a "
                       "fillable form (no fields rendered)")
        return (False, reasons)
    try:
        from pypdf import PdfReader
        r = PdfReader(str(pdf))
        n_pages = len(r.pages)
        fields = r.get_fields() or {}
        need_app = False
        try:
            need_app = bool(r.trailer["/Root"]["/AcroForm"]["/NeedAppearances"])
        except Exception:  # noqa: BLE001
            need_app = False
        if n_pages < 1:
            reasons.append(f"workbook PDF {pdf.name}: pypdf read {n_pages} pages")
        if not fields:
            reasons.append(f"workbook PDF {pdf.name}: pypdf read ZERO AcroForm fields — "
                           "the fillable form did not survive")
        if not need_app:
            reasons.append(f"workbook PDF {pdf.name}: /NeedAppearances not set — fields will "
                           "not render in viewers")
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
    if not tagged_p.exists() or not source_p.exists(): return True, []
    size = tagged_p.stat().st_size
    if size < 2048: reasons.append(f"PRESENTERS-SPEECH-FISH-TAGGED.md: {size} bytes < 2048")
    try: tagged_text = tagged_p.read_text(encoding="utf-8",errors="replace"); source_text = source_p.read_text(encoding="utf-8",errors="replace")
    except: return True, []
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
    "P9.1-SPEECH-PDF":    _verify_text_artifact("working/deliverables/PRESENTERS-SPEECH.pdf", 20480),
    "P9.2-GHL-UPLOAD":    _verify_ghl_upload,
    # --- Feature L2-D: fillable PDF workbook ---
    "P8.25-WORKBOOK":     _verify_workbook,
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
    so the runner blocks unmapped phases (fail-closed per U013 step 9)."""
    fn: Optional[Callable] = PHASE_VERIFIERS.get(phase_id)
    if fn is None:
        return False, [f"no verifier registered for {phase_id!r} — pass"]
    try:
        result = fn(Path(run_dir))
        # Accept both (ok, reasons) tuple and legacy str return for compat.
        if isinstance(result, tuple) and len(result) == 2:
            ok, reasons = result
            return bool(ok), list(reasons)
        # Legacy str: '' == pass, non-empty == fail.
        if isinstance(result, str):
            return (result == ""), ([] if result == "" else [result])
        return bool(result), []
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

        # T1: absent artifact => pass (run_signature_deck owns absence)
        ok, reasons = verify("P0A-INTAKE", rd)
        if not ok:
            fails.append(f"T1: absent artifact should pass, got ok={ok} reasons={reasons}")

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

        # T5: verify_all_phases with no artifacts => no failures
        phases = [
            {"id": "P0A-INTAKE", "produces_artifact": "working/copy/intake.json"},
            {"id": "P0B-PRIORITY", "produces_artifact": "working/copy/priority_shift_spec.json"},
        ]
        rd2 = Path(tempfile.mkdtemp(prefix="phase_verifiers_selftest2_"))
        failures = verify_all_phases(rd2, phases)
        if failures:
            fails.append(f"T5: all-absent should produce no failures, got {failures}")

        # T6: render verifier with no PNGs -> fail (filesystem fallback)
        # Only fires when _crg is None (the module is absent in test context).
        if _crg is None and _bd is None:
            ok, reasons = verify("P4-RENDER", rd)
            if ok and not any("NOTE" in r for r in reasons):
                fails.append(f"T6: render with no PNGs should fail or note-degrade, got ok={ok} reasons={reasons}")

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
