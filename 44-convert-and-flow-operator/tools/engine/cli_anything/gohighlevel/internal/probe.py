"""probe.py — ContractProbe: doctor internal-probe + Sunday contract check.

ONE code path, three callers (adapter-design §8.3):
  1. `caf doctor` (acceptance criterion C1: "internal probe passes")
  2. Sunday 3 AM cron contract check
  3. CI (mock transport, replay golden fixture — acceptance criterion C19)

`run_contract_probe(adapter, *, allow_write_probe=False) -> ProbeResult`

Probe is READ-ONLY by default:
  - Checks token health (Firebase exchange succeeds)
  - Runs READ-ONLY shape assertions against contract.schema.json
  - Writes result to data_dir()/probe/last-probe.json

On contract failure (shape drift, not merely dead token):
  - Calls degrade.disable_writes(scope="local", reason=..., probe_result)
  - The fleet-wide disable is the Sunday cron's job (it calls disable_writes
    on every box).  This module calls it locally; the cron wiring (unit 13)
    does the fleet propagation.

PRD constraint: NEVER raises mid-probe.  All failures are caught and returned
as ProbeResult(ok=False, ...).  Only the CLI top-level may sys.exit().
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from cli_anything.gohighlevel.internal.adapter_types import AdapterError, ProbeResult

if TYPE_CHECKING:
    from cli_anything.gohighlevel.internal.adapter import InternalAdapter


# ── Paths ─────────────────────────────────────────────────────────────────────

def _probe_result_path() -> Path:
    from cli_anything.gohighlevel.internal.guards import data_dir
    d = data_dir() / "probe"
    d.mkdir(parents=True, exist_ok=True)
    return d / "last-probe.json"


def _schema_path() -> Path:
    return Path(__file__).parent / "fixtures" / "contract.schema.json"


def _golden_path() -> Path:
    return Path(__file__).parent / "fixtures" / "contract.golden.json"


# ── Public entry point ────────────────────────────────────────────────────────

def run_contract_probe(
    adapter: "InternalAdapter",
    *,
    allow_write_probe: bool = False,
) -> ProbeResult:
    """Run the contract probe against the adapter.

    Steps:
      1. Token health check (Firebase exchange).
      2. READ-ONLY shape assertions from contract.schema.json.
      3. Write result to last-probe.json.
      4. On contract failure, call degrade.disable_writes().

    allow_write_probe=True is reserved for build-time fixture capture; the
    Sunday/doctor probe is always read-only.

    Returns ProbeResult — never raises.
    """
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Step 1: Token health
    try:
        adapter.transport.get_token()
    except AdapterError as e:
        result = ProbeResult(
            ok=False,
            reason=e.code,
            failed_assertion="token_health",
            checked_at=checked_at,
            scope="token",
        )
        _save_probe_result(result)
        # Dead token is NOT a contract break — no degrade, just nudge
        return result
    except Exception as e:
        result = ProbeResult(
            ok=False,
            reason=f"TOKEN_ERROR: {e}",
            failed_assertion="token_health",
            checked_at=checked_at,
            scope="token",
        )
        _save_probe_result(result)
        return result

    # Step 2: Contract shape assertions (read-only)
    schema = _load_schema()
    if schema is None:
        result = ProbeResult(
            ok=False,
            reason="SCHEMA_MISSING: contract.schema.json not found",
            failed_assertion="schema_load",
            checked_at=checked_at,
            scope="contract",
        )
        _save_probe_result(result)
        return result

    # Run assertions defined in the schema
    failed = _run_shape_assertions(adapter, schema, checked_at)
    if failed:
        result = ProbeResult(
            ok=False,
            reason=f"CONTRACT_DRIFT: {failed['assertion']}",
            failed_assertion=failed["assertion"],
            checked_at=checked_at,
            scope="contract",
        )
        _save_probe_result(result)
        from cli_anything.gohighlevel.internal import degrade
        degrade.disable_writes(scope="local", reason=result.reason, probe_result=result)
        return result

    # Warn if the golden fixture is synthetic (built from source, not a real account)
    reason = ""
    if schema.get("_synthetic_check") == "warn_if_synthetic":
        golden = _load_golden()
        if golden and golden.get("_synthetic"):
            reason = (
                "SYNTHETIC_FIXTURE: golden fixture was built from source-code shapes "
                "and has NOT been validated against a live GHL backend. "
                "Run the capture procedure in internal/fixtures/README.md with a real "
                "canonical account credential before first production deploy. "
                "Probe ok=True; writes are not blocked by a synthetic fixture alone."
            )
            import sys
            print(f"[probe] WARNING: {reason}", file=sys.stderr)

    result = ProbeResult(ok=True, reason=reason, checked_at=checked_at, scope="contract")
    _save_probe_result(result)
    return result


# ── Schema loader ─────────────────────────────────────────────────────────────

def _load_schema() -> dict | None:
    path = _schema_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── Shape assertions ──────────────────────────────────────────────────────────

def _run_shape_assertions(
    adapter: "InternalAdapter",
    schema: dict,
    checked_at: str,
) -> dict | None:
    """Run each assertion in the schema against the adapter (read-only GETs only).

    Returns None if all pass, or {"assertion": name, "detail": msg} on first failure.

    Assertion types supported in contract.schema.json:
      - "workflow_get_shape": GET a workflow and check required keys are present.
      - "strip_keys_present": verify STRIP_KEYS are actually present on a GET response.
      - "verified_actions_snapshot": compare VERIFIED_ACTIONS snapshot in golden.

    The probe uses a known workflow_id from the schema's "probe_fixture" section
    if provided (allows a static read-only fixture for CI with a mock transport).
    CI feeds the golden fixture via a mock — no live CRM call.
    """
    probe_fixture = schema.get("probe_fixture", {})

    # Assert 1: workflow GET shape
    wf_shape = schema.get("workflow_get_shape", {})
    if wf_shape:
        wf_id = probe_fixture.get("workflow_id", "")
        if wf_id:
            result = adapter.get_workflow(wf_id)
            if not result.ok or result.data is None:
                return {
                    "assertion": "workflow_get_shape",
                    "detail": f"GET /workflow/{{loc}}/{wf_id} failed: {result.error}",
                }
            data = result.data
            for required_key in wf_shape.get("required_keys", []):
                if required_key not in data:
                    return {
                        "assertion": "workflow_get_shape",
                        "detail": f"required key '{required_key}' missing from GET response",
                    }
            # Check workflowData.templates is present if required
            if wf_shape.get("requires_workflow_data_templates"):
                if "workflowData" not in data or "templates" not in data.get("workflowData", {}):
                    return {
                        "assertion": "workflow_get_shape",
                        "detail": "workflowData.templates missing from GET response",
                    }
            # Check version field
            if wf_shape.get("requires_version") and "version" not in data:
                return {
                    "assertion": "workflow_get_shape",
                    "detail": "'version' missing from GET response",
                }

    # Assert 2: STRIP_KEYS present on live GET response
    strip_assertions = schema.get("strip_keys_assertions", {})
    if strip_assertions and probe_fixture.get("workflow_id"):
        wf_id = probe_fixture["workflow_id"]
        result = adapter.get_workflow(wf_id)
        if result.ok and result.data:
            from cli_anything.gohighlevel.internal.contract import STRIP_KEYS
            required_stripable = strip_assertions.get("must_be_present_for_strip", [])
            for key in required_stripable:
                if key not in result.data:
                    return {
                        "assertion": "strip_keys_present",
                        "detail": (
                            f"STRIP_KEY '{key}' marked stripable:true in schema "
                            "but not present in live GET response — contract drift"
                        ),
                    }

    # Assert 3: VERIFIED_ACTIONS snapshot check against golden
    if schema.get("check_verified_actions"):
        golden = _load_golden()
        if golden:
            golden_actions = set(golden.get("verified_actions_snapshot", []))
            from cli_anything.gohighlevel.utils.workflow_builder import VERIFIED_ACTIONS
            if golden_actions and not golden_actions.issubset(VERIFIED_ACTIONS):
                missing = golden_actions - VERIFIED_ACTIONS
                return {
                    "assertion": "verified_actions_snapshot",
                    "detail": (
                        f"Actions in golden fixture are missing from VERIFIED_ACTIONS: "
                        f"{sorted(missing)}"
                    ),
                }

    return None  # all assertions passed


def _load_golden() -> dict | None:
    path = _golden_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── Persist probe result ──────────────────────────────────────────────────────

def _save_probe_result(result: ProbeResult) -> None:
    """Write last-probe.json — never raises (transparency is logged to stderr)."""
    try:
        data = {
            "ok": result.ok,
            "reason": result.reason,
            "failed_assertion": result.failed_assertion,
            "checked_at": result.checked_at,
            "scope": result.scope,
        }
        _probe_result_path().write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
    except Exception as e:
        import sys
        print(f"[probe] WARNING: could not write probe result: {e}", file=sys.stderr)


def last_probe_result() -> dict | None:
    """Return the most recent probe result dict, or None if never run."""
    path = _probe_result_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
