"""S44-08 timing-contract comparator (DESIGN-S44-08-v1.md).

The timing contract lives per workflow (never in a mutable
contact-wide field): mode, anchor, signed offset, timezone, past-due
behavior, and re-entry isolation. This module compares a contract
against the native export read-back and reports expected vs observed,
field by field — the receipt evidence for timing, not a claim.

Honesty rules:
- duration waits are the only waits the API adapter expresses; an
  EVENT-ANCHORED wait in a contract is not degraded into a duration —
  it is reported as requiring the governed browser lane, and any export
  step claiming to implement it via the API is a mismatch;
- a wait step observed in the export with no contract entry (or the
  reverse) is a mismatch, never silently aligned;
- past-due behavior and timezone are contract fields the native export
  may not echo; where the export cannot express them, the comparison
  reports UNVERIFIABLE for that field rather than ok — absence of
  evidence is not agreement.
"""
from __future__ import annotations


def compare_timing(contract: dict, export: dict) -> dict:
    """contract: {"slug", "allow_multiple": bool,
                   "waits": [{"step": name, "mode": "duration"|
                              "event_anchored", "offset_seconds": int,
                              "timezone": str, "past_due": str}]}
    export: the native workflow export (steps carry names; duration
    waits appear as steps of type "wait" with "duration_seconds").
    Returns {"slug", "fields": [...], "verdict": ...}."""
    fields = []

    def add(name, expected, observed, ok):
        fields.append({"field": name, "expected": expected,
                       "observed": observed, "ok": ok})

    # re-entry isolation is directly observable in the export
    exp_am = contract.get("allow_multiple", False)
    obs_am = export.get("allowMultiple")
    add("allow_multiple", exp_am, obs_am, obs_am == exp_am)

    export_waits = {}
    for step in export.get("steps", []):
        if step.get("type") == "wait":
            export_waits[step.get("name")] = step
    contract_waits = {w["step"]: w for w in contract.get("waits", [])}

    for name, w in contract_waits.items():
        if w["mode"] == "event_anchored":
            # never degradable: the API lane cannot express this wait
            add(f"wait:{name}:lane", "governed_browser_lane",
                "api_export_present" if name in export_waits
                else "not_in_api_export", name not in export_waits)
            continue
        obs = export_waits.get(name)
        if obs is None:
            add(f"wait:{name}", w["offset_seconds"], None, False)
            continue
        add(f"wait:{name}:offset_seconds", w["offset_seconds"],
            obs.get("duration_seconds"),
            obs.get("duration_seconds") == w["offset_seconds"])
        # timezone / past-due: only ok when the export actually echoes
        for sub in ("timezone", "past_due"):
            echoed = obs.get(sub)
            add(f"wait:{name}:{sub}", w.get(sub), echoed,
                echoed == w.get(sub) if echoed is not None
                else "UNVERIFIABLE")
    for name in export_waits:
        if name not in contract_waits:
            add(f"wait:{name}", None,
                export_waits[name].get("duration_seconds"), False)

    def _ok(f):
        return f["ok"] is True

    verdict = "MATCH" if all(_ok(f) for f in fields) else "MISMATCH"
    if any(f["ok"] == "UNVERIFIABLE" for f in fields) and \
            all(f["ok"] in (True, "UNVERIFIABLE") for f in fields):
        verdict = "MATCH_WITH_UNVERIFIABLE_FIELDS"
    return {"slug": contract.get("slug"), "fields": fields,
            "verdict": verdict}
