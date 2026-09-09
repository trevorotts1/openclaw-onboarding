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

BLEND_TIMEOUT_S = 90          # (Fix 28, 2026-09-02) raised from 30 s: the 30 s wall
                               # blocked legitimately slow copy-phase persona
                               # resolutions (P4-COPY et al.) and the SMOKE-1
                               # ledger shows copy phases dying on it. The seam's
                               # own subprocess budget is 60 s
                               # (shared-utils/persona_for_job.py:425,
                               # "timeout: int = 60"); 90 s gives one full seam
                               # budget plus headroom, and the retry below gives
                               # one second attempt before the phase blocks.
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
                       avatar_context: str = "",
                       persona_context: Optional[Dict[str, Any]] = None
                       ) -> Optional[Dict[str, Any]]:
    """Resolve the blended-persona governance bundle for one pipeline phase.

    Returns None immediately for any phase_id not in BLEND_PHASE_FOR (22 of
    26 phases — keep the critical path clean). On match: imports
    blend_voice_governance, calls governed_phase_voice under a hard timeout.

    PRES-031: the caller (Engine._run_phase) builds the canonical scoped
    persona context (presentation_job.persona_context.build_persona_context:
    client/company/presentation IDs, audience, topic, offer, approved owner
    voice, sales framework) and passes it as `persona_context`. The
    avatar_context string is DERIVED from that context when the caller does
    not supply one explicitly -- the seam never receives generic phase text
    alone. The COMPLETE bundle caches by scoped input/context hash
    (persona_context cache key: client+presentation+context -- never shared
    across runs); the dual-persona algorithm itself is untouched.

    Failure modes:
    - LegacyIntakeVoiceRequired -> continue, record persona_governance marker
    - RuntimeError / timeout -> BLOCK
    """
    narrative = BLEND_PHASE_FOR.get(phase_id)
    if narrative is None:
        return None

    from presentation_job import persona_context as _pc
    if persona_context is None:
        try:
            persona_context = _pc.build_persona_context(run_dir, phase_id)
        except Exception:  # noqa: BLE001 -- context build never blocks
            persona_context = None
    cached_bundle = None
    if persona_context is not None:
        cached_bundle = _pc.lookup_bundle(run_dir, persona_context)
        if cached_bundle is not None:
            _try_record_bundle(run_dir, phase_id, narrative, cached_bundle)
            return cached_bundle
        if not avatar_context:
            avatar_context = _avatar_text_from_context(persona_context)

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

    # Normal path: call governed_phase_voice under a hard timeout.
    # (Fix 28, 2026-09-02) One retry: a single timed-out attempt no longer
    # blocks the phase immediately. Attempt 1 gets BLEND_TIMEOUT_S; if it
    # times out, exactly one fresh attempt (a new executor thread, so a wedged
    # first call cannot poison the retry) gets the same wall; only a second
    # timeout raises TimeoutError and blocks the phase.
    import concurrent.futures
    bundle = None
    attempts = 2
    for attempt in range(1, attempts + 1):
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            fut = ex.submit(
                mod.governed_phase_voice,
                narrative, avatar_context,
                department="presentations", record=True)
            try:
                bundle = fut.result(timeout=BLEND_TIMEOUT_S)
                break
            except concurrent.futures.TimeoutError:
                if attempt >= attempts:
                    raise TimeoutError(
                        f"blend_voice_governance.governed_phase_voice('{narrative}') "
                        f"timed out after {BLEND_TIMEOUT_S}s on attempt {attempt} "
                        f"of {attempts} for phase {phase_id}. The persona "
                        "resolution seam (persona_for_job.py) did not respond "
                        "within the governance wall; one retry was spent.") from None
                import time as _time
                _time.sleep(1.0)
        finally:
            ex.shutdown(wait=False)

    # Write the bundle to state.json and record the event.
    _try_record_bundle(run_dir, phase_id, narrative, bundle)
    # PRES-031: cache the COMPLETE bundle under the scoped key (no-op when
    # no context was built). The owner-selected voice is asserted intact
    # before caching: a bundle that dropped it is a seam fault, not a cache
    # entry.
    if persona_context is not None and isinstance(bundle, dict):
        try:
            from presentation_job import persona_context as _pc2
            _assert_owner_voice_intact(persona_context, bundle)
            _pc2.store_bundle(run_dir, persona_context, bundle)
        except Exception:  # noqa: BLE001 -- cache/voice-assert never blocks
            pass
    return bundle


def _avatar_text_from_context(
        persona_context: Dict[str, Any]) -> str:
    """Derive the seam's avatar_context string from the scoped context
    (PRES-031 step 1). Audience + topic + offer + owner voice + framework --
    never generic phase text alone."""
    parts = []
    for label, section in (("audience", (persona_context.get("audience")
                                        or {}).get("value")),
                           ("topic", (persona_context.get("topic")
                                      or {}).get("value")),
                           ("offer", (persona_context.get("offer")
                                      or {}).get("value")),
                           ("owner voice", (persona_context.get("owner_voice")
                                            or {}).get("value")),
                           ("frame", (persona_context.get("signature_frame")
                                      or {}).get("value"))):
        if section:
            parts.append(f"{label}: {section}")
    framework = persona_context.get("framework")
    if framework:
        parts.append(f"framework: {framework}")
    return "; ".join(parts)


def _assert_owner_voice_intact(persona_context: Dict[str, Any],
                               bundle: Dict[str, Any]) -> None:
    """PRES-031 QC3: the owner-named voice survives into the bundle.

    The bundle carries execution persona and audience voice as separate
    fields with recorded IDs/hashes (persona_context); the seam's bundle
    must not silently replace an owner-selected voice with a default. When
    the context names an owner voice, the bundle text must reference it
    (case-insensitive substring of the voice's leading significant words)
    or carry it in a dedicated owner_voice field -- else ValueError.
    """
    voice = str((persona_context.get("owner_voice") or {}).get("value")
                or "").strip()
    if not voice:
        return
    blob = json.dumps(bundle, ensure_ascii=False).lower()
    import re as _re
    words = [w for w in _re.findall(r"[a-z]{4,}", voice.lower())][:6]
    if words and not any(w in blob for w in words):
        if "owner_voice" not in blob:
            raise ValueError(
                "owner-selected voice dropped by the persona seam: "
                f"{voice[:80]!r} has no trace in the resolved bundle")


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
