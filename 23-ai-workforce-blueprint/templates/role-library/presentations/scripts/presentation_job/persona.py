"""U024 — blended-persona governance, called once per pipeline phase.

Skill 51 SKILL.md:146-160 binds the deck's WRITTEN VOICE to the blended persona
directive: "never advisory, no exemptions." blend_voice_governance.py implements
that and had ZERO runtime callers. This module is the caller.

Skill-51 PHASES are the FOUR narrative phases, not the 26 pipeline phases. The
mapping below is the only place the two vocabularies meet.
"""
from __future__ import annotations

import importlib.util
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

BLEND_TIMEOUT_S = 90          # REVISED 2026-09-01 (SMOKE-1 F18): 30s blocked a legitimate cold call
                               # (shared-utils/persona_for_job.py:425, "timeout: int = 60"; neither
                               # persona-selector-v2.py's 20s/120s subprocess timeouts nor
                               # persona_for_job.py carry a 30s value anywhere — checked, re-checked
                               # 2026-07-27, and there is none. So this wall is NOT a mirror of an
                               # upstream number; it is this unit's own, deliberately tighter, choice:
                               # fail fast and BLOCK the phase well before the seam's own 60s budget
                               # is spent, accepting that a legitimately slow 30-59s call is treated
                               # the same as a hung one — consistent with "block, do not degrade"
                               # above. Do not raise it to 60 "to match": that would let one slow
                               # persona resolution silently eat the whole per-phase critical path.)
BLEND_PHASE_FOR = {           # pipeline phase id -> Skill-51 narrative phase
    "P-SP-STRUCTURE":  "avatar-section",
    "P4-COPY":         "signature-story",
    "P-SP-P3-HYGIENE": "transformational-teaching",
    "P4-PROMPT":       "purpose-pitch",
}


# ---------------------------------------------------------------------------
# Module loader — _sp_prover-style, cached, never registers in sys.modules
# ---------------------------------------------------------------------------
_MODULE_CACHE: Dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()


def _resolve_module_path() -> Optional[Path]:
    """Find blend_voice_governance.py, preferring <dept>/scripts/ then
    Skill-51 fallback. Mirrors build_deck._sp_prover (build_deck.py:6661-6698)."""
    here = Path(__file__).resolve().parent       # presentation_job/
    scripts_dir = here.parent                     # …/presentations/scripts/

    # Candidate 1: deployed department scripts dir (this unit installs it there)
    cands = [scripts_dir / "blend_voice_governance.py"]

    # Candidate 2: repo/worktree layout — sibling 51-signature-presentation
    cands += [anc / "51-signature-presentation" / "scripts" / "blend_voice_governance.py"
              for anc in here.parents]

    # Candidate 3: installed skills tree under an ancestor
    cands += [anc / "skills" / "51-signature-presentation" / "scripts" / "blend_voice_governance.py"
              for anc in here.parents]

    # Candidate 4: canonical installed roots
    for _base in ("/data/.openclaw/skills",
                  str(Path.home() / ".openclaw" / "skills")):
        cands.append(Path(_base) / "51-signature-presentation" / "scripts"
                     / "blend_voice_governance.py")

    for cand in cands:
        if cand.is_file():
            return cand
    return None


def load_blend_module():
    """Path-import blend_voice_governance.py, cached. Returns the module
    object or None. Never registers in sys.modules (Skill 58 ships an
    identically-named module and the two would collide)."""
    with _CACHE_LOCK:
        if "mod" in _MODULE_CACHE:
            return _MODULE_CACHE["mod"]

    path = _resolve_module_path()
    if path is None:
        with _CACHE_LOCK:
            _MODULE_CACHE["mod"] = None
        return None

    spec = importlib.util.spec_from_file_location("blend_voice_governance_pj", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with _CACHE_LOCK:
        _MODULE_CACHE["mod"] = mod
    return mod


# ---------------------------------------------------------------------------
# State recording helpers — graceful when state.json is absent
# ---------------------------------------------------------------------------
def _state_store_exists(run_dir: Path) -> bool:
    from .state import STATE_FILENAME
    return (run_dir / STATE_FILENAME).is_file()


def _try_record_legacy(run_dir: Path, phase_id: str) -> None:
    """Record legacy-intake-tone marker if state.json exists."""
    if not _state_store_exists(run_dir):
        return
    from .report import Reporter
    from .state import StateStore, utcnow
    store = StateStore(run_dir)
    state = store.load()
    rep = Reporter(state, store)
    rep.event("persona_resolved",
              f"{phase_id} -> legacy-intake-tone",
              phase_id=phase_id,
              persona_governance="legacy-intake-tone")
    result = {"persona_governance": "legacy-intake-tone",
              "phase_id": phase_id, "at": utcnow()}
    for ps in state.setdefault("phases", []):
        if ps.get("id") == phase_id:
            ps["persona_bundle"] = result
            break
    store.save(state)


def _try_record_bundle(run_dir: Path, phase_id: str,
                        narrative: str, bundle: Dict[str, Any]) -> None:
    """Record the resolved persona bundle if state.json exists."""
    if not _state_store_exists(run_dir):
        return
    from .report import Reporter
    from .state import StateStore
    store = StateStore(run_dir)
    state = store.load()
    for ps in state.setdefault("phases", []):
        if ps.get("id") == phase_id:
            ps["persona_bundle"] = bundle
            break
    rep = Reporter(state, store)
    rep.event("persona_resolved",
              f"{phase_id} -> {narrative} governed by blend directive",
              phase_id=phase_id, narrative_phase=narrative,
              persona_id=bundle.get("persona_id"))
    store.save(state)


# ---------------------------------------------------------------------------
# Resolver — once per pipeline phase
# ---------------------------------------------------------------------------
def resolve_for_phase(run_dir: Path, phase_id: str,
                       avatar_context: str = "") -> Optional[Dict[str, Any]]:
    """Resolve the blended-persona governance bundle for one pipeline phase.

    Returns None immediately for any phase_id not in BLEND_PHASE_FOR (22 of
    26 phases — keep the critical path clean). On match: imports
    blend_voice_governance, calls governed_phase_voice under a hard timeout.

    Failure modes:
    - LegacyIntakeVoiceRequired -> continue, record persona_governance marker
    - RuntimeError / timeout -> BLOCK
    """
    narrative = BLEND_PHASE_FOR.get(phase_id)
    if narrative is None:
        return None

    mod = load_blend_module()
    if mod is None:
        raise RuntimeError(
            f"blend_voice_governance.py not reachable — cannot resolve a governed "
            f"phase voice for {phase_id} (never silently degrade to an ungoverned "
            f"local voice). persona_for_job.py seam must be installed; see "
            f"blend_voice_governance._load_pfj search order.")

    # Flag-off path: SKILL51_BLEND_GOVERNS=0 — continue with legacy marker
    try:
        if not mod.blend_governs():
            _try_record_legacy(run_dir, phase_id)
            return {"persona_governance": "legacy-intake-tone",
                    "phase_id": phase_id}
    except mod.LegacyIntakeVoiceRequired:
        _try_record_legacy(run_dir, phase_id)
        return {"persona_governance": "legacy-intake-tone",
                "phase_id": phase_id}

    # Normal path: call governed_phase_voice under a hard timeout
    import concurrent.futures
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        fut = ex.submit(
            mod.governed_phase_voice,
            narrative, avatar_context,
            department="presentations", record=True)
        try:
            bundle = fut.result(timeout=BLEND_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(
                f"blend_voice_governance.governed_phase_voice('{narrative}') "
                f"timed out after {BLEND_TIMEOUT_S}s for phase {phase_id}. "
                "The persona resolution seam (persona_for_job.py) did not "
                "respond within the governance wall.") from None
    finally:
        ex.shutdown(wait=False)

    # Write the bundle to state.json and record the event.
    _try_record_bundle(run_dir, phase_id, narrative, bundle)
    return bundle


# ---------------------------------------------------------------------------
# Banner — one line an operator can read at engine start
# ---------------------------------------------------------------------------
def governance_banner() -> str:
    """One line an operator can read at engine start: governance ON/OFF, the
    pipeline phase ids that will resolve a bundle, and the resolved import path
    of blend_voice_governance.py. Never raises: an unreachable module reports
    'import: UNREACHABLE', because a banner that crashes the engine is worse
    than a banner that says it cannot see the module."""
    mod = load_blend_module()
    gov_phases = sorted(list(BLEND_PHASE_FOR.keys()))
    if mod is None:
        gov_state = "OFF (module UNREACHABLE)"
        import_path = "import: UNREACHABLE"
    else:
        gov_state = "ON" if mod.blend_governs() else "OFF (SKILL51_BLEND_GOVERNS=0)"
        path = _resolve_module_path()
        import_path = str(path) if path else "import: UNREACHABLE"

    return (f"blended-persona governance: {gov_state}  "
            f"governed_phases={gov_phases}  "
            f"module={import_path}")


# ---------------------------------------------------------------------------
# Structure warn check — engine start-up gate that warns, never blocks
# ---------------------------------------------------------------------------
def _resolve_skill51_root() -> Optional[Path]:
    """Find a Skill-51 root that has the sacred structure files.
    Search order is the REVERSE of load_blend_module's: repository copy first,
    then installed skills tree. The department copy has no sacred files."""
    here = Path(__file__).resolve().parent       # presentation_job/
    scripts_dir = here.parent                     # …/presentations/scripts/

    # Repo / worktree layout: sibling 51-signature-presentation/
    cands = [anc / "51-signature-presentation"
             for anc in scripts_dir.parents]

    # Installed skills
    for _base in (str(Path.home() / ".openclaw" / "skills"),
                  "/data/.openclaw/skills"):
        cands.append(Path(_base) / "51-signature-presentation")

    for cand in cands:
        if cand.is_dir() and (cand / "MASTERDOC.md").is_file():
            return cand
    return None


def structure_warn_check() -> Dict[str, Any]:
    """Warn-mode (Rule 3.5) sacred-structure check for engine start-up.

    Returns {"checked": int, "mismatched": [rel, ...], "pin_file_found": bool}.
    NEVER raises, NEVER exits non-zero, and NEVER records a persona selection:
    it calls structural_fixture_hashes() — a pure read — and compares it to the
    pin file. It does NOT call prove_voice_governance_and_structure(), whose
    voice half resolves four personas with record=True.
    """
    # Find a Skill-51 root with the sacred files.
    skill_root = _resolve_skill51_root()
    if skill_root is None:
        return {"checked": 0, "mismatched": [], "pin_file_found": False}

    pin_path = skill_root / "scripts" / "sacred-structure-hashes.json"
    if not pin_path.is_file():
        return {"checked": 0, "mismatched": [], "pin_file_found": False}

    # Load the pin file
    try:
        pin_data = json.loads(pin_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"checked": 0, "mismatched": [], "pin_file_found": False}

    pinned = {k: v for k, v in pin_data.items() if not k.startswith("_")}

    # Load the module from the Skill-51 root (not the department) so
    # _SKILL_ROOT resolves to the directory with the sacred files.
    bvg_path = skill_root / "scripts" / "blend_voice_governance.py"
    if not bvg_path.is_file():
        return {"checked": 0, "mismatched": [], "pin_file_found": True}

    spec = importlib.util.spec_from_file_location(
        "blend_voice_governance_structure_check", bvg_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    current = mod.structural_fixture_hashes()
    all_keys = set(pinned.keys()) | set(current.keys())
    mismatched = sorted(
        k for k in all_keys
        if pinned.get(k) != current.get(k)
    )

    return {
        "checked": len(pinned),
        "mismatched": mismatched,
        "pin_file_found": True,
    }
