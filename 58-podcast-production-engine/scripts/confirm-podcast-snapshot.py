#!/usr/bin/env python3
"""confirm-podcast-snapshot.py — GK-05/U67: podcast golden snapshot v2 +
`PODCAST_SNAPSHOT_ID` confirmation (no-409 dry run).

Implements the repo-side half of GK-05's BINARY acceptance:
  (a) the current snapshot id is RECORDED in this repo
      (config/podcast-snapshot-registry.json);
  (b) n8n's Snapshot Provisioner workflow (`ol9YLeCpvYdNsbsg`) `PODCAST_SNAPSHOT_ID`
      value is compared against the recorded id (byte-for-byte);
  (c) ONE dry-run provisioning request against the live provision-snapshot webhook
      is proven to NOT 409.

STRUCTURAL DEPENDENCY (spec Deps: GK-01). This gate refuses to treat a version as
confirmable while its `snapshot_id` is still null in the registry -- the v2 golden
snapshot must not be cut until GK-01/U63 (the publish-path fix) lands, or it bakes a
known-broken state as golden. As of this build U63 is operator-gated/deferred (see
LEDGER U63) so `current` stays pinned at v1 and v2.snapshot_id stays null. A
registry that reports BLOCKED is the correct, expected pre-GK-01 state -- exit 0.

WHAT THIS SCRIPT DELIBERATELY DOES NOT DO (and why):
  - It never cuts a GHL snapshot. There is no public create-snapshot API (confirmed
    in PODCAST-SNAPSHOT-BUILD-MANIFEST.md Section I -- snapshotting is a hand-built
    GHL UI action). That is Trevor's live step, same pattern as GK-04/U66.
  - It never auto-fetches PODCAST_SNAPSHOT_ID from n8n. n8n exposes no REST endpoint
    for reading an arbitrary OS-level `$env.*` value set on the deployment (that is
    exactly the surface `N8N_BLOCK_ENV_ACCESS_IN_NODE` gates, per
    59-anthology-engine/config/n8n/README.md) -- the value must be read back by
    whatever channel the operator already uses (e.g. a container-level env read on
    the n8n host) and passed in via --confirm-n8n-value. This script does the
    COMPARISON, not a fabricated fetch.
  - --dry-run-provision fires a REAL live POST at the production provision-snapshot
    webhook (reusing the already-proven shared-utils/fire-provision-snapshot.sh).
    That is a genuine live side effect and is opt-in only; this build does not
    invoke it.

Exit 0 = registry well-formed and (if requested) confirmed; exit 1 = malformed
registry, a value mismatch, or a proven 409 / provisioning failure. A structurally
BLOCKED (pre-GK-01) state is exit 0 -- it is not a failure of this gate.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve()
_ENGINE_ROOT = _HERE.parent.parent  # .../58-podcast-production-engine
_REPO_ROOT = _ENGINE_ROOT.parent
DEFAULT_REGISTRY = _ENGINE_ROOT / "config" / "podcast-snapshot-registry.json"
FIRE_SCRIPT = _REPO_ROOT / "shared-utils" / "fire-provision-snapshot.sh"

REQUIRED_TOP_KEYS = {
    "engine", "template_location_id", "n8n_workflow_id",
    "n8n_workflow_name", "n8n_env_var", "current", "snapshots",
}
REQUIRED_SNAPSHOT_KEYS = {"snapshot_id", "status"}


class RegistryError(ValueError):
    """Raised when the snapshot registry file is missing or malformed."""


def _validate_registry_shape(data: dict, source: Path) -> None:
    """Raise RegistryError on any structural problem in an already-parsed registry."""
    if not isinstance(data, dict):
        raise RegistryError(f"registry root must be an object ({source})")
    missing = REQUIRED_TOP_KEYS - set(data.keys())
    if missing:
        raise RegistryError(f"registry missing top-level key(s): {sorted(missing)}")
    if data["engine"] != "podcast":
        raise RegistryError(f"registry engine must be 'podcast', got {data['engine']!r}")
    snapshots = data["snapshots"]
    if not isinstance(snapshots, dict) or not snapshots:
        raise RegistryError("registry['snapshots'] must be a non-empty object")
    current = data["current"]
    if current not in snapshots:
        raise RegistryError(f"current={current!r} not present in snapshots {sorted(snapshots)}")
    for ver, row in snapshots.items():
        if not isinstance(row, dict):
            raise RegistryError(f"snapshots[{ver!r}] must be an object")
        missing_s = REQUIRED_SNAPSHOT_KEYS - set(row.keys())
        if missing_s:
            raise RegistryError(f"snapshots[{ver!r}] missing key(s): {sorted(missing_s)}")


def load_registry(path: Optional[str] = None) -> dict:
    """Load + shape-validate the snapshot registry. Raises RegistryError on any
    structural problem so callers never silently proceed on a malformed file."""
    p = Path(path) if path else DEFAULT_REGISTRY
    if not p.is_file():
        raise RegistryError(f"registry not found: {p}")
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        raise RegistryError(f"registry is not valid JSON ({p}): {e}") from e
    _validate_registry_shape(data, p)
    return data


def registry_state(data: dict) -> dict:
    """Pure function: derive the confirmable state from an already-loaded registry.

    Returns {current_version, current_snapshot_id (may be None), ready, reason}.
    """
    current = data["current"]
    row = data["snapshots"][current]
    sid = row.get("snapshot_id")
    if not sid:
        deps = row.get("blocked_on") or []
        dep_txt = f" (blocked_on={deps})" if deps else ""
        return {
            "current_version": current,
            "current_snapshot_id": None,
            "ready": False,
            "reason": f"snapshots[{current!r}].snapshot_id is not recorded yet{dep_txt} — nothing to confirm",
        }
    return {
        "current_version": current,
        "current_snapshot_id": sid,
        "ready": True,
        "reason": "",
    }


def compare_n8n_value(expected_id: str, observed_value: str) -> bool:
    """PODCAST_SNAPSHOT_ID read back from n8n must equal the registry's recorded id,
    byte-for-byte (whitespace-trimmed only)."""
    if not isinstance(observed_value, str):
        return False
    return observed_value.strip() == expected_id.strip()


def parse_fire_provision_log(log_text: str) -> dict:
    """Classify the stderr log emitted by shared-utils/fire-provision-snapshot.sh into
    a verdict for the GK-05 'one dry-run provisioning request does not 409' proof.

    Pure string classification over ALREADY-CAPTURED output (never shells back out to
    grep) so it is independently unit-testable against canned log fixtures. Any
    non-2xx outcome (409 specifically, or any other manual-fallback trigger) is
    treated as FAIL -- the acceptance criterion's "does not 409" names the KNOWN
    failure mode (PODCAST_SNAPSHOT_ID unset/stale), not a license to accept a
    different live error instead.
    """
    text = log_text or ""
    if "webhook accepted (HTTP 2" in text:
        return {"verdict": "PASS", "code_class": "2xx", "detail": "provisioning webhook accepted (non-409)"}
    if "webhook returned 409" in text:
        return {
            "verdict": "FAIL", "code_class": "409",
            "detail": "PODCAST_SNAPSHOT_ID not set/stale in n8n — hard-409 (fail-closed by design)",
        }
    if "MANUAL FALLBACK" in text:
        return {"verdict": "FAIL", "code_class": "manual-fallback", "detail": "webhook unreachable/unconfigured/errored — could not prove no-409"}
    return {"verdict": "FAIL", "code_class": "unknown", "detail": "could not classify fire-provision-snapshot.sh output"}


def run_dry_run_provision(*, location_id: str, client_slug: str = "gk05-scratch-confirm",
                           extra_env: Optional[dict] = None, timeout: int = 45) -> dict:
    """Fire ONE real provisioning request at a clearly-labeled SCRATCH client via the
    existing, already-proven shared-utils/fire-provision-snapshot.sh, then classify
    its output. LIVE network call -- callers gate this behind an explicit flag."""
    if not FIRE_SCRIPT.is_file():
        return {"verdict": "FAIL", "code_class": "missing-script", "detail": f"{FIRE_SCRIPT} not found"}
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        ["bash", str(FIRE_SCRIPT),
         "--engine", "podcast",
         "--location-id", location_id,
         "--client-slug", client_slug,
         "--client-name", "GK-05 Scratch Confirm (delete-safe, no real client)",
         "--client-email", "gk05-scratch-confirm@example.invalid",
         "--requested-by", "confirm-podcast-snapshot.py"],
        capture_output=True, text=True, env=env, timeout=timeout,
    )
    return parse_fire_provision_log(proc.stderr)


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write `data` to `path` via a same-directory temp file + rename, so a crash or
    concurrent read never observes a half-written registry."""
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".podcast-snapshot-registry-", suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def record_snapshot(path: Optional[str], version: str, snapshot_id: str) -> dict:
    """Write a newly-cut snapshot id back into the registry (repo bookkeeping only --
    no live side effect). Clears blocked_on and sets status='cut-pending-n8n-confirm'.
    Never flips 'current' -- that is a separate, deliberate operator decision made only
    after the n8n PODCAST_SNAPSHOT_ID + dry-run proofs both pass."""
    p = Path(path) if path else DEFAULT_REGISTRY
    data = load_registry(str(p))
    if version not in data["snapshots"]:
        raise RegistryError(f"unknown version {version!r}; known={sorted(data['snapshots'])}")
    if not snapshot_id or not snapshot_id.strip():
        raise RegistryError("snapshot_id must be a non-empty string")
    row = data["snapshots"][version]
    row["snapshot_id"] = snapshot_id.strip()
    row["status"] = "cut-pending-n8n-confirm"
    row["blocked_on"] = []
    _atomic_write_json(p, data)
    return data


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry", default=None, help="path to the snapshot registry JSON (default: repo canonical path)")
    ap.add_argument("--confirm-n8n-value", default=None,
                     help="the PODCAST_SNAPSHOT_ID value already read back from n8n by the operator's own "
                          "channel; compared byte-for-byte against the registry's recorded current-version id")
    ap.add_argument("--dry-run-provision", action="store_true",
                     help="also fire ONE live provisioning request at a SCRATCH client and assert it does not "
                          "409 (requires --confirm-n8n-value to have matched first; LIVE side effect)")
    ap.add_argument("--record-snapshot", nargs=2, metavar=("VERSION", "SNAPSHOT_ID"), default=None,
                     help="record a newly-cut snapshot id into the registry (repo-only write, no live call), "
                          "e.g. --record-snapshot v2 AbCdEfGhIjKlMnOp")
    return ap


def _cmd_record_snapshot(registry_path: Optional[str], version: str, snapshot_id: str) -> int:
    try:
        record_snapshot(registry_path, version, snapshot_id)
    except RegistryError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    target = Path(registry_path) if registry_path else DEFAULT_REGISTRY
    print(f"[OK] recorded snapshots[{version!r}].snapshot_id={snapshot_id!r} in {target}")
    return 0


def _cmd_confirm_n8n_value(sid: str, confirm_n8n_value: str) -> int:
    if not compare_n8n_value(sid, confirm_n8n_value):
        print(f"[FAIL] n8n PODCAST_SNAPSHOT_ID={confirm_n8n_value!r} != registry {sid!r}")
        return 1
    print(f"[PASS] n8n PODCAST_SNAPSHOT_ID matches registry ({sid})")
    return 0


def _cmd_confirm(args) -> int:
    try:
        data = load_registry(args.registry)
    except RegistryError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    state = registry_state(data)
    print(f"== GK-05/U67 podcast snapshot confirmation — current={state['current_version']!r} ==")
    if not state["ready"]:
        print(f"[BLOCKED] {state['reason']}")
        print("RESULT: BLOCKED (expected pre-GK-01/U63 state — not a failure of this gate)")
        return 0
    print(f"[OK] registry records current snapshot_id={state['current_snapshot_id']}")

    if args.confirm_n8n_value is None:
        print("[SKIP] --confirm-n8n-value not supplied; registry-only check complete")
        return 0
    rc = _cmd_confirm_n8n_value(state["current_snapshot_id"], args.confirm_n8n_value)
    if rc != 0 or not args.dry_run_provision:
        return rc

    result = run_dry_run_provision(location_id=data["template_location_id"])
    print(f"[{result['verdict']}] dry-run provisioning request — {result['detail']}")
    return 0 if result["verdict"] == "PASS" else 1


def main(argv=None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if args.record_snapshot is not None:
        version, snapshot_id = args.record_snapshot
        return _cmd_record_snapshot(args.registry, version, snapshot_id)
    return _cmd_confirm(args)


if __name__ == "__main__":
    sys.exit(main())
