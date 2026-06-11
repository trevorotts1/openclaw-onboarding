"""degrade.py — read-only write-disable flag and owner alert.

Implements adapter-design §8.4:

  On a CONTRACT probe failure (shape drift = GHL changed the backend):
  - LOCAL: write data_dir()/degrade/workflow-write.disabled containing the
    ProbeResult.  adapter._call(is_write=True) checks is_write_disabled()
    and refuses cleanly.
  - FLEET-WIDE: Sunday cron / release agent calls disable_writes() on every
    box + fires the owner alert.
  - RE-ENABLE: clear_write_disable() removes the flag.

Dead token is NOT a degrade event — it nudges the owner instead.

The FLEET-WIDE propagation (cron / release.sh) calls these three functions:
  disable_writes(scope, reason)  -> writes flag + emits alert
  is_write_disabled()            -> returns bool (adapter checks before writing)
  clear_write_disable()          -> removes flag (after probe passes again)

Boundary: this module writes the local flag and emits the alert.  The cron
wiring that calls disable_writes() on every box is unit 13's responsibility.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cli_anything.gohighlevel.internal.adapter_types import ProbeResult


# ── Degrade flag path ─────────────────────────────────────────────────────────

def _degrade_flag_path() -> Path:
    from cli_anything.gohighlevel.internal.guards import data_dir
    d = data_dir() / "degrade"
    d.mkdir(parents=True, exist_ok=True)
    return d / "workflow-write.disabled"


# ── Public API ────────────────────────────────────────────────────────────────

def is_write_disabled() -> bool:
    """Return True if workflow writes are currently disabled (flag file exists)."""
    return _degrade_flag_path().exists()


def disable_writes(scope: str, reason: str, probe_result: Optional["ProbeResult"] = None) -> None:
    """Write the disable flag and emit the owner alert.

    Args:
        scope:        "local" | "fleet" — recorded in the flag for audit.
        reason:       Human-readable reason (e.g. failed assertion name).
        probe_result: If provided, included in the flag file for detail.
    """
    flag = _degrade_flag_path()
    record: dict = {
        "disabled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": scope,
        "reason": reason,
    }
    if probe_result is not None:
        record["probe"] = {
            "ok": probe_result.ok,
            "reason": probe_result.reason,
            "failed_assertion": probe_result.failed_assertion,
            "checked_at": probe_result.checked_at,
            "scope": probe_result.scope,
        }
    flag.write_text(json.dumps(record, indent=2), encoding="utf-8")
    _emit_owner_alert(scope, reason, probe_result)


def clear_write_disable() -> None:
    """Remove the disable flag — re-enables workflow writes.

    Called by the Sunday update after a re-probe passes (PRD §8:
    're-enables Tier 0 writes fleet-wide once the probe passes again').
    """
    flag = _degrade_flag_path()
    try:
        flag.unlink()
    except FileNotFoundError:
        pass


def read_disable_record() -> Optional[dict]:
    """Return the contents of the flag file, or None if not disabled."""
    flag = _degrade_flag_path()
    if not flag.exists():
        return None
    try:
        return json.loads(flag.read_text(encoding="utf-8"))
    except Exception:
        return {"error": "flag file unreadable"}


# ── Owner alert ───────────────────────────────────────────────────────────────

def _emit_owner_alert(
    scope: str,
    reason: str,
    probe_result: Optional["ProbeResult"] = None,
) -> None:
    """Emit a structured owner alert via the OpenClaw notification channel.

    Alert content (PRD §8.5) includes:
    - Which assertion failed
    - Timestamp of when golden fixtures were last captured
    - Box id / hostname
    - One-line remediation instruction

    The actual send uses the OPENCLAW_NOTIFY_CHANNEL env var if set; falls
    back to stderr so the alert is never silent (PRD §3.2 transparency rule).
    Alert is logged; never suppressed.
    """
    import socket
    box_id = socket.gethostname()

    fixture_ts = _read_fixture_capture_date()
    failed = probe_result.failed_assertion if probe_result else reason

    lines = [
        "[SKILL-44 CONTRACT PROBE FAILED]",
        f"  box:              {box_id}",
        f"  scope:            {scope}",
        f"  failed_assertion: {failed}",
        f"  reason:           {reason}",
        f"  fixture_captured: {fixture_ts or 'unknown'}",
        f"  disabled_at:      {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "",
        "  Workflow writes are now DISABLED fleet-wide until the adapter is refreshed.",
        "  REMEDIATION: engineering must re-capture golden fixtures from the canonical",
        "  account, update internal/fixtures/, bump skill 44 version, and ship via",
        "  release.sh.  The Sunday update re-enables Tier 0 writes after probe passes.",
    ]
    alert_text = "\n".join(lines)

    notify_channel = os.environ.get("OPENCLAW_NOTIFY_CHANNEL", "").strip()
    if notify_channel:
        try:
            # Attempt OpenClaw notification (best-effort; stderr fallback always runs)
            _send_to_openclaw(notify_channel, alert_text)
        except Exception:
            pass

    # Always log to stderr — never silent
    import sys
    print(alert_text, file=sys.stderr)


def _send_to_openclaw(channel: str, message: str) -> None:
    """Best-effort send to the OpenClaw notification channel.

    Uses subprocess to call `openclaw message send` if available.
    Failure here is non-fatal — the stderr fallback in _emit_owner_alert
    ensures the alert is always visible.
    """
    import subprocess
    subprocess.run(
        ["openclaw", "message", "send", "--channel", channel, "--text", message],
        timeout=15,
        capture_output=True,
    )


def _read_fixture_capture_date() -> Optional[str]:
    """Read the capture_date field from contract.golden.json.

    This is the authoritative source — README prose may contain code snippets
    that contain the string 'capture_date', which would produce misleading output.
    Falls back to None if the golden file is absent or unparseable.
    """
    try:
        import pathlib
        import json as _json
        golden = pathlib.Path(__file__).parent / "fixtures" / "contract.golden.json"
        if golden.exists():
            data = _json.loads(golden.read_text(encoding="utf-8"))
            return data.get("capture_date")
    except Exception:
        pass
    return None
