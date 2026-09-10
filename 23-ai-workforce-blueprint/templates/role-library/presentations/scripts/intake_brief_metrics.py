#!/usr/bin/env python3
"""PRES-056 -- brief metrics: turn-count + time-to-valid-brief vs baseline.

MEASURES, NEVER GATES. The 23-turn bank is the ceiling (Trevor ruling);
a required SOP/QC obligation is never dropped to hit a target, so every
function here reports and returns -- nothing refuses, nothing skips, nothing
invents offer/pricing/research facts.

BASELINE (fixture-designed, mirrored from the bank's
session_budget.ux_targets -- the bank is the single source: 23 merged turns,
48 physical rows, 20 required fields among the merged turns):
  * new client: valid brief in at most 11 interactions
  * repeat client: at most 6
  * preference reuse: 100% (every locked creative pref a repeat client
    brings is copied with provenance "preference-reuse")

VALID BRIEF (what "time-to-valid-brief" means): every required downstream
brief field is real, approved-derived, or explicit pending -- never null,
never invented:
  * real: provenance "client-answered" (the driver records
    "deck-intake-driver" -- same meaning, led by the only writer) or
    "plan-lock" (the ask-once lock resolving resource_plan in place);
  * approved-derived: "preference-reuse", a "derived" record (slide_count
    from duration math, access_free from event price, deliverable_set from
    the toggles, target_wpm from pace), or a validated entry carrying a
    bank-documented default (default / none_value / conservative_value /
    no_note);
  * explicit pending: a skipped entry WITH a skip_reason (pitchless rows,
    conditional rows whose condition is unmet and which carry no documented
    default).
Omitted vs declined stays distinct: a waiver toggle answered "no" must carry
a validated non-empty declined-reason record; silence is routed to pending,
never to a reason.

GOOD SOURCES (single read each): the bank's ux_targets header, the driver's
measure_progress / review_summary / _answer_view and the completed intake's
ledger entries. Values reported come ONLY from those -- this module holds no
fixture data of its own.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

METRICS_VERSION = 1

BASELINE_TURNS = 23
BANK_PHYSICAL_ROWS = 48
BANK_REQUIRED_FIELDS = 20
NEW_CLIENT_TARGET = 11
REPEAT_CLIENT_TARGET = 6

REQUIRED_BRIEF_FIELDS: Tuple[str, ...] = (
    "GOAL", "CTA_ACTION", "TARGET_FEELING", "TONE", "AUDIENCE",
    "TRANSFORMATION_PROMISE", "TIME_TO_RESULT", "NAMED_METHODOLOGY",
    "OFFER_NAME", "OFFER_STACK", "FINAL_PRICE", "PRICE_MODE",
    "DURATION_MIN", "DEADLINE", "PROOF_ASSETS", "STYLE_PREFS",
    "BRAND_PRIMARY", "VISUAL_MIX", "DELIVERY_DESTINATIONS",
    "PRESENTATION_TYPE",
)

WAIVER_TOGGLES: Tuple[str, ...] = (
    "want_teleprompter", "want_speech_script", "want_ghl_upload",
    "want_audio_deliverable", "want_sales_checkout", "want_vsl_page",
)

_DECLINE_REASON = {
    "want_teleprompter": "teleprompter_declined_reason",
    "want_speech_script": "speech_script_declined_reason",
    "want_ghl_upload": "ghl_upload_declined_reason",
    "want_audio_deliverable": "audio_declined_reason",
    "want_sales_checkout": "sales_checkout_declined_reason",
    "want_vsl_page": "vsl_page_declined_reason",
}

_REAL_SOURCES = ("client-answered", "deck-intake-driver", "plan-lock")
_APPROVED_DERIVED_SOURCES = ("preference-reuse",)

_DRIVER_MOD: Any = None


def _driver() -> Any:
    """Import deck-intake-driver.py beside this module. Cached."""
    global _DRIVER_MOD
    if _DRIVER_MOD is None:
        path = Path(__file__).resolve().parent / "deck-intake-driver.py"
        spec = importlib.util.spec_from_file_location(
            "deck_intake_driver_pres056_metrics", str(path))
        assert spec is not None and spec.loader is not None, (
            f"cannot load driver at {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _DRIVER_MOD = mod
    return _DRIVER_MOD


def bank_path() -> Path:
    """Canonical bank beside the driver's department root."""
    return (Path(__file__).resolve().parent.parent
            / "intake" / "deck-intake-questions.json")


def read_bank_targets(bank_file: Optional[Path] = None) -> Dict[str, Any]:
    """Read the bank's single-source UX header. Keys: baseline, new_target,
    repeat_target, max_turns, merged_turns, physical_rows, required_fields."""
    bank = json.loads(Path(bank_file or bank_path()).read_text(
        encoding="utf-8"))
    targets = (bank.get("session_budget") or {}).get("ux_targets") or {}
    merged = [q for q in bank.get("questions", [])
              if q.get("kind") == "merged" and not q.get("alias")]
    return {"baseline": targets.get("baseline_turns", BASELINE_TURNS),
            "new_target": targets.get(
                "new_client_valid_brief_max_interactions", NEW_CLIENT_TARGET),
            "repeat_target": targets.get(
                "repeat_client_valid_brief_max_interactions",
                REPEAT_CLIENT_TARGET),
            "max_turns": (bank.get("session_budget") or {}).get("max_turns"),
            "merged_turns": len(merged),
            "physical_rows": len(bank.get("questions", [])),
            "required_fields": sum(1 for q in merged if q.get("required"))}


def verify_bank_shape(bank_file: Optional[Path] = None) -> Dict[str, Any]:
    """Confirm the bank the targets were designed against is still the bank:
    23 merged turns, 48 physical rows, 20 required, ceiling 23. Reports
    mismatches -- never raises, never gates (callers decide)."""
    got = read_bank_targets(bank_file)
    expect = {"merged_turns": BASELINE_TURNS,
              "physical_rows": BANK_PHYSICAL_ROWS,
              "required_fields": BANK_REQUIRED_FIELDS, "max_turns": 23}
    mismatches = {k: {"expected": v, "got": got.get(k)}
                  for k, v in expect.items() if got.get(k) != v}
    return {"ok": not mismatches, "mismatches": mismatches, "measured": got}


def count_interactions(run_dir: Path) -> int:
    """Interactions this presentation actually spent: the snapshot's asked
    order, falling back to half the raw turn log (assistant + owner per
    answer). 0 when neither exists -- absence is absence."""
    drv = _driver()
    rd = Path(run_dir).expanduser().resolve()
    snap = drv.read_autosave(rd)
    order = (snap.get("asked_order") or []) if isinstance(snap, dict) else []
    if order:
        return len(order)
    return len(drv.read_intake_transcript_raw(rd)) // 2


def _entry_state(key: str, entry: Any) -> Tuple[str, str]:
    """Classify one ledger record for the valid-brief contract.

    Returns (state, detail) with state one of: real, approved-derived,
    pending, bad. Bad covers: null values, unknown provenance, declined
    toggles without a validated reason, and non-record shapes."""
    if key.startswith("_"):
        return "real", "meta"
    if not isinstance(entry, dict):
        return "bad", "not-a-record"
    if entry.get("skipped"):
        if entry.get("skip_reason"):
            return "pending", "skipped-with-reason"
        return "bad", "skip-without-reason"
    val = entry.get("value")
    if val is None:
        return "bad", "null-value"
    if isinstance(val, str) and not val.strip() and not entry.get("validated"):
        return "bad", "empty-unvalidated"
    src = entry.get("source")
    if src in _REAL_SOURCES:
        return "real", f"source-{src}"
    if src in _APPROVED_DERIVED_SOURCES:
        return "approved-derived", f"source-{src}"
    return "bad", f"unknown-source-{src!r}"


def check_required_fields(entries: Dict[str, Any]) -> Dict[str, Any]:
    """Classify every required brief field: real / approved-derived /
    pending / bad, plus per-field detail. Omitted-vs-declined proof: each
    declined waiver toggle must carry its own validated non-empty reason."""
    fields: Dict[str, Dict[str, str]] = {}
    for key in REQUIRED_BRIEF_FIELDS:
        entry = entries.get(key)
        if entry is None:
            lower = entries.get(key.lower())
            if isinstance(lower, dict):
                entry = lower
        if entry is None:
            fields[key] = {"state": "pending",
                           "detail": "no-record-yet"}
            continue
        state, detail = _entry_state(key, entry)
        fields[key] = {"state": state, "detail": detail}
    reasons: Dict[str, Dict[str, str]] = {}
    for toggle in WAIVER_TOGGLES:
        entry = entries.get(toggle)
        val = entry.get("value") if isinstance(entry, dict) else entry
        declined = (val is False or
                    (isinstance(val, str)
                     and val.strip().lower() in (
                         "no", "false", "n", "0", "none")))
        if not declined:
            continue
        rkey = _DECLINE_REASON[toggle]
        rent = entries.get(rkey) or entries.get(rkey.lower())
        if (isinstance(rent, dict) and rent.get("validated")
                and rent.get("value")
                and str(rent.get("value")).strip()):
            reasons[toggle] = {"state": "real",
                               "detail": f"declined-with-reason:{rkey}"}
        else:
            reasons[toggle] = {"state": "bad",
                               "detail": f"declined-without-reason:{rkey}"}
    return {"fields": fields, "decline_reasons": reasons}


def brief_valid(entries: Dict[str, Any]) -> Dict[str, Any]:
    """True when every required field is real / approved-derived / pending
    AND every declined toggle carries its reason: no nulls, no unknown
    provenance, no unreasoned declines -- and nothing invented. Reports the
    bad list; never raises."""
    checked = check_required_fields(entries)
    bad = ([k for k, r in checked["fields"].items()
            if r["state"] == "bad"]
           + [f"{t}-reason" for t, r in checked["decline_reasons"].items()
              if r["state"] == "bad"])
    pending = [k for k, r in checked["fields"].items()
               if r["state"] == "pending"]
    return {"valid": not bad, "bad": bad, "pending": pending,
            "fields": checked["fields"],
            "decline_reasons": checked["decline_reasons"]}


def measure_run(run_dir: Path,
                returning_client: Optional[bool] = None,
                preferences: Optional[Dict[str, Any]] = None,
                bank_file: Optional[Path] = None) -> Dict[str, Any]:
    """Full measurement for one presentation dir: asked count, saved vs the
    23 baseline, target + meets_target, preference hits + reuse rate for
    repeat clients, brief-valid verdict, and the bank-shape check the targets
    were designed against."""
    drv = _driver()
    rd = Path(run_dir).expanduser().resolve()
    targets = read_bank_targets(bank_file)
    if preferences is None:
        try:
            preferences = drv.load_preferences()
        except Exception:
            preferences = {}
    if not isinstance(preferences, dict):
        preferences = {}
    if returning_client is None:
        returning_client = bool(preferences)
    asked = count_interactions(rd)
    target = (targets["repeat_target"] if returning_client
              else targets["new_target"])
    reuse_keys = [k for k in drv.PREFERENCE_REUSE_KEYS
                  if preferences.get(k) not in (None, "")]
    locked_total = len([k for k in drv.CREATIVE_PREF_KEYS])
    reuse_rate = (len([k for k in reuse_keys if k in drv.CREATIVE_PREF_KEYS])
                  / locked_total) if locked_total else None
    entries = drv.read_intake_ledger(rd).get("entries", {})
    if not isinstance(entries, dict):
        entries = {}
    verdict = brief_valid(entries)
    shape = verify_bank_shape(bank_file)
    return {"asked": asked, "baseline": targets["baseline"],
            "saved": max(0, targets["baseline"] - asked),
            "target": target, "meets_target": asked <= target,
            "returning_client": returning_client,
            "preference_hits": len(reuse_keys),
            "preference_reuse_rate": reuse_rate,
            "brief": verdict, "bank_shape": shape}


def summarize_runs(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate measure_run dicts (pure function, no disk): counts, how
    many meet target, mean asked/saved, how many briefs valid."""
    total = len(runs)
    if not total:
        return {"runs": 0}
    asked = [r.get("asked", 0) for r in runs]
    return {"runs": total,
            "meet_target": sum(1 for r in runs if r.get("meets_target")),
            "briefs_valid": sum(1 for r in runs
                                if (r.get("brief") or {}).get("valid")),
            "mean_asked": sum(asked) / total,
            "mean_saved": sum(r.get("saved", 0) for r in runs) / total,
            "max_asked": max(asked), "min_asked": min(asked)}
