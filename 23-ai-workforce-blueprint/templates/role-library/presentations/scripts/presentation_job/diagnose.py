from __future__ import annotations

from typing import Dict, List


def describe_park(state: dict, run_dir=None) -> list[str]:
    """Return the operator-facing lines explaining why this job is parked.
    Reads BOTH park shapes: state['blocked'] (phase failure) and state['gates'] (gate failure).
    Never mutates state. Returns [] when the job is not parked."""
    lines: list[str] = []

    terminal = state.get("terminal")
    if terminal is None:
        lines.append("terminal : in progress")
        return lines
    lines.append(f"terminal : {terminal}")

    # -- Phase park -----------------------------------------------------------
    blocked = state.get("blocked")
    if blocked is not None:
        phase_id = blocked.get("phase", "?")
        reason = blocked.get("reason", "no reason recorded")
        lines.append("")
        lines.append(f"parked at phase   : {phase_id}")
        lines.append(f"reason             : {reason}")
    else:
        for ps in state.get("phases", []) or []:
            if ps.get("status") == "blocked":
                lines.append("")
                lines.append(f"parked at phase   : {ps['id']}")
                lines.append(f"reason             : {ps.get('blocked_reason', 'no reason recorded')}")
                break

    # -- Gates ----------------------------------------------------------------
    gates = state.get("gates") or {}
    if gates:
        failed = [(k, g.get("reason", "failed")) for k, g in sorted(gates.items()) if g.get("state") == "fail"]
        waived = [(k, g.get("reason", "waived")) for k, g in sorted(gates.items()) if g.get("state") == "waived"]
        warn = [k for k, g in sorted(gates.items()) if g.get("warn_only")]
        if failed:
            lines.append("")
            lines.append("failing gates:")
            for k, r in failed:
                lines.append(f"  {k}: {r}")
        if waived:
            lines.append("")
            lines.append("waived gates:")
            for k, r in waived:
                lines.append(f"  {k}: {r}")
        if warn:
            lines.append("")
            lines.append(f"warn-only gates: {', '.join(warn)}")

    # -- Artifact inventory with denominator ----------------------------------
    phases = state.get("phases") or []
    total_phases = len(phases)
    done_phases = [p for p in phases if p.get("status") == "done"]
    n_done = len(done_phases)
    banked = [a for p in done_phases for a in (p.get("artifacts") or [])]
    n_banked = len(banked)
    lines.append("")
    lines.append(f"phases  : {n_done} of {total_phases} done, {n_banked} artifact(s) banked")

    # -- Resume re-validation count -------------------------------------------
    # state["resume_revalidation"] is a dict as of U017: {"checked": N, "failed": M}.
    # Before U017 it was written as a bare int, and any run dir resumed under the
    # old code still carries that shape on disk (StateStore.load() does no shape
    # migration). Treat any non-dict value (legacy int, corrupt string, etc.) the
    # same as absent -- degrade to "unknown", never crash and never guess a cause.
    rr = state.get("resume_revalidation")
    if isinstance(rr, dict):
        checked = rr.get("checked", 0)
        failed_rev = rr.get("failed", 0)
        lines.append(f"banked artifact re-validation: {checked} checked, {failed_rev} of {checked} failed")
    else:
        lines.append("banked artifact re-validation: unknown \u2014 no re-validation record on this run dir")

    # -- Heal history ---------------------------------------------------------
    heal_by_rung: Dict[int, int] = {}
    for ps in phases:
        for he in ps.get("heal_events") or []:
            rung = he.get("rung", 0)
            heal_by_rung[rung] = heal_by_rung.get(rung, 0) + 1
    if heal_by_rung:
        lines.append("")
        lines.append("heal events by rung:")
        for rung in sorted(heal_by_rung):
            lines.append(f"  rung {rung}: {heal_by_rung[rung]} event(s)")

    # -- Undeliverable count --------------------------------------------------
    undeliverable = state.get("undeliverable") or []
    if undeliverable:
        total_events = len(state.get("events") or [])
        lines.append("")
        lines.append(f"undeliverable messages: {len(undeliverable)} of {total_events} total events "
                      "\u2014 the requester was NOT told about these; retried automatically on backoff")

    # -- Parked (poisoned) messages --------------------------------------------
    # These stopped retrying because the SAME content kept failing while the
    # transport was independently confirmed working for other messages -- see
    # report.flush_undeliverable()'s docstring. Content is preserved, never
    # discarded, and never re-attempted automatically.
    parked = state.get("parked") or []
    if parked:
        lines.append("")
        lines.append(f"parked (poisoned) messages: {len(parked)} \u2014 retries stopped, "
                      "content preserved, the requester was NOT told about these")
        for m in parked:
            lines.append(f"  [{m.get('kind','?')}] {m.get('message','')[:100]!r} "
                         f"\u2014 {m.get('parked_reason','no reason recorded')}")

    return lines
