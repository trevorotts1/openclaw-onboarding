#!/usr/bin/env python3
"""PRES-056 -- progressive intake store: autosave + continuity after renewal.

Thin stable API over deck-intake-driver.py's OWN persistence surface. This
module holds NO interview logic, NO defaults, NO facts: every read and write
delegates to the driver's functions (autosave_state / read_autosave /
save_preferences / load_preferences / record_preference_reuse /
read_intake_ledger / write_intake_ledger), so the driver and this store can
never disagree about what a snapshot, a ledger entry, or a preference IS.

SCOPING (per company / presentation):
  * One PRESENTATION (one deck) = one run_dir. The ledger and the
    progressive snapshot both live under run_dir/working/interview/, so two
    simultaneous decks never share state -- isolation is by directory.
  * One COMPANY = one shared profile/config dir (the
    PRESENTATION_RESOURCE_PROFILE_DIR the operator already controls). Locked
    creative prefs and plan-tier locks live there; --reuse-preferences copies
    them into each new deck's ledger with provenance "preference-reuse".

CONTINUITY AFTER TOKEN RENEWAL: a renewal is a fresh process with the SAME
dirs. resume_context() re-reads the LEDGER (the authority -- every answer
with its provenance) plus the snapshot (the progress meter -- asked order),
so --next after a restart surfaces the identical next turn with nothing
re-asked. An absent/unreadable snapshot is absence, never evidence: the
interview restarts at turn 1 with the ledger's answers intact (negative-
result contract).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional

STORE_VERSION = 1
SNAPSHOT_FILENAME = "progressive_state.json"
LEDGER_REL = Path("working") / "interview" / "intake_ledger.json"
SNAPSHOT_REL = Path("working") / "interview" / SNAPSHOT_FILENAME

_DRIVER_MOD: Any = None


def _driver() -> Any:
    """Import deck-intake-driver.py beside this module (filename has a dash,
    so importlib, not a plain import). Cached; the driver is import-safe
    (constants + defs only, main-guarded)."""
    global _DRIVER_MOD
    if _DRIVER_MOD is None:
        path = Path(__file__).resolve().parent / "deck-intake-driver.py"
        spec = importlib.util.spec_from_file_location(
            "deck_intake_driver_pres056_store", str(path))
        assert spec is not None and spec.loader is not None, (
            f"cannot load driver at {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _DRIVER_MOD = mod
    return _DRIVER_MOD


def snapshot_path(run_dir: Path) -> Path:
    """Where this presentation's progressive snapshot lives."""
    return Path(run_dir).expanduser().resolve() / SNAPSHOT_REL


def ledger_path(run_dir: Path) -> Path:
    """Where this presentation's intake ledger lives."""
    return Path(run_dir).expanduser().resolve() / LEDGER_REL


def save_progress(run_dir: Path, answers: Optional[Dict[str, Any]] = None,
                  asked_order: Optional[List[str]] = None,
                  preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Atomically persist this presentation's progressive snapshot (the
    driver's own autosave_state: tmp + os.replace, crash-safe). The normal
    path needs no direct call -- --next / --answer already autosave -- this
    exists for agents driving the ledger by other means."""
    drv = _driver()
    rd = Path(run_dir).expanduser().resolve()
    if answers is None or asked_order is None:
        entries = drv.read_intake_ledger(rd).get("entries", {})
        if answers is None:
            answers = drv._answer_view(entries)
        if asked_order is None:
            asked_order = (drv.read_autosave(rd).get("asked_order") or [])
    return drv.autosave_state(rd, answers, asked_order, preferences)


def load_progress(run_dir: Path) -> Dict[str, Any]:
    """Read this presentation's snapshot. {} when absent/unreadable, or when
    the content is not a snapshot (asked_order must be a list) -- an absent
    snapshot proves nothing about the interview."""
    drv = _driver()
    snap = drv.read_autosave(Path(run_dir).expanduser().resolve())
    if not isinstance(snap, dict):
        return {}
    if not isinstance(snap.get("asked_order"), list):
        return {}
    return snap


def read_ledger(run_dir: Path) -> Dict[str, Any]:
    """Read this presentation's intake ledger ({} when absent)."""
    return _driver().read_intake_ledger(Path(run_dir).expanduser().resolve())


def resume_context(run_dir: Path,
                   config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Rebuild everything a fresh process needs after a token renewal: the
    ledger entries (authority), the flattened answers view, the snapshot's
    asked order, and the company's locked preferences.

    Keys: entries, answers, asked_order, snapshot, preferences,
    returning_client. Never raises on missing state -- empty maps, never an
    error, so a renewal with nothing saved yet just starts at turn 1."""
    drv = _driver()
    rd = Path(run_dir).expanduser().resolve()
    ledger = drv.read_intake_ledger(rd)
    entries = ledger.get("entries", {})
    if not isinstance(entries, dict):
        entries = {}
    snap = load_progress(rd)
    try:
        preferences = drv.load_preferences(config_dir)
    except Exception:
        preferences = {}
    if not isinstance(preferences, dict):
        preferences = {}
    return {"entries": entries,
            "answers": drv._answer_view(entries),
            "asked_order": snap.get("asked_order", []),
            "snapshot": snap,
            "preferences": preferences,
            "returning_client": bool(preferences)}


def load_locked_preferences(
        config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Read-only view of the company's locked preferences (model-plan slots,
    creative prefs, plan-tier lock marker). {} for a new client -- never an
    error, never invented values."""
    drv = _driver()
    try:
        prefs = drv.load_preferences(config_dir)
    except Exception:
        return {}
    return prefs if isinstance(prefs, dict) else {}


def persist_confirmed_preferences(
        entries: Dict[str, Any],
        config_dir: Optional[Path] = None) -> List[str]:
    """Autosave direction ledger -> profile: persist newly CONFIRMED
    preference-bearing ledger values to the company profile's creative_prefs.
    Only validated, non-empty values move; returns the keys saved. Never
    raises -- a store failure keeps the answer in the ledger."""
    return _driver().save_preferences(entries, config_dir)


def copy_preferences_into_ledger(
        entries: Dict[str, Any],
        preferences: Dict[str, Any]) -> List[str]:
    """Copy locked company preferences into this run's ledger with provenance
    "preference-reuse" (never "client-answered"). Returns the keys copied.
    Model-plan slots and the plan-tier lock are NOT copied -- the router and
    the ask gate consult those on the profile in place."""
    return _driver().record_preference_reuse(entries, preferences)
