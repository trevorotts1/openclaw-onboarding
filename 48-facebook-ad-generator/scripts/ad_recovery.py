#!/usr/bin/env python3
"""
ad_recovery.py — SELF-CORRECT + DURABLE PARK-AND-RESUME ENGINE (Skill 48, net-new).

================================================================================
The Facebook & Instagram ad foreman (ad_director.py) used to HARD-ABORT on the
first failed check and the whole job died, throwing away every paid/attested step.
This engine replaces "die" with two durable behaviours, WITHOUT ever bypassing a
gate or fabricating a pass:

  (A) RECOVERABLE failures (recovery:"auto") — the foreman redoes ONLY the failing
      artifact using the gate's own feedback, up to a bounded budget, re-runs the
      REAL check, and CONTINUES. Only after the budget is spent does it escalate
      to a durable park.
  (B) NON-RECOVERABLE conditions (recovery:"park" — over the money ceiling, out of
      balance, a fabrication/tampering check, a skipped/awaited HUMAN approval) —
      the foreman writes a DURABLE save-point (PARKED.json + a box-level pointer
      under OC_ROOT/workspace/.park/fbad/) and PAUSES. Nothing is discarded. When
      the blocker clears, a resume re-enters at the exact last-incomplete phase,
      idempotent on the run-id ledger (never re-charges, never re-uploads).

This module is the SINGLE place the recovery POLICY lives at runtime. It reads the
policy from AD-PIPELINE-MANIFEST.json (each autofail carries `recovery` +
`max_fix_attempts`; a top-level `recovery_policy` block carries the defaults +
env-override names). It hardcodes NO `AF-FBAD-*` strings, so ad_sync_check.py's
orphan-AF check (B2) stays clean and the dangerous-gate set is enforced in the
manifest + ad_sync_check (R4), not here.

Stdlib only (hashlib / json / os / re / time / pathlib). All writes are ATOMIC
(write-to-temp-then-os.replace), mirroring ad_run_ledger.py, so a crash or reboot
mid-park never leaves a half-written checkpoint.

DURABILITY (mirrors the v14.1.5 stuck-build park pattern, scripts/unpark-build.sh):
  OC_ROOT = /data/.openclaw (VPS) else $HOME/.openclaw (Mac); overridable for tests
  via FBAD_OC_ROOT. The durable runs root is OC_ROOT/workspace/fbad-runs/<run_id>/;
  the box-level park pointer dir is OC_ROOT/workspace/.park/fbad/. A paid run pinned
  to a reboot-wiped tmp dir is REFUSED (unless --allow-ephemeral) so a checkpoint can
  never evaporate.
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
AF_RE = re.compile(r"AF-FBAD-[A-Z0-9]+(?:-[A-Z0-9]+)*")


# ---------------------------------------------------------------------------
# Manifest resolution (own loader so the engine is importable with no side
# effects by ad_director, ad_sync_check, ad_gate_integrity_check, and the tests)
# ---------------------------------------------------------------------------
def _find_repo_root(start: Path):
    cur = start
    for _ in range(12):
        if (cur / "universal-sops").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def load_manifest() -> dict:
    repo = _find_repo_root(HERE)
    candidates = []
    if repo:
        candidates.append(repo / "universal-sops" / "fb-ad-craft"
                          / "AD-PIPELINE-MANIFEST.json")
    candidates += [
        HERE.parent / "sops" / "AD-PIPELINE-MANIFEST.json",
        HERE.parent / "AD-PIPELINE-MANIFEST.json",
        HERE / "AD-PIPELINE-MANIFEST.json",
    ]
    for c in candidates:
        if c.exists():
            return json.loads(c.read_text())
    raise FileNotFoundError("AD-PIPELINE-MANIFEST.json not found for ad_recovery.")


# ---------------------------------------------------------------------------
# Recovery policy — read from the manifest (the single source of truth)
# ---------------------------------------------------------------------------
def load_policy(manifest=None) -> dict:
    m = manifest if manifest is not None else load_manifest()
    by_code = {}
    for a in m.get("autofails", []):
        code = a.get("code")
        if not code:
            continue
        rec = a.get("recovery")
        mx = a.get("max_fix_attempts", 0)
        by_code[code] = {
            "recovery": rec,
            "max_fix_attempts": int(mx) if isinstance(mx, (int, float)) else 0,
        }
    return {"by_code": by_code, "policy": m.get("recovery_policy", {}) or {}}


def _policy_int(rp: dict, key: str, env_key: str, default: int) -> int:
    env = os.environ.get(rp.get(env_key, ""), "")
    if str(env).strip().lstrip("-").isdigit():
        return int(str(env).strip())
    v = rp.get(key, default)
    return int(v) if isinstance(v, (int, float)) else default


def policy(af_code: str, manifest=None):
    """Return (recovery:str, max_fix_attempts:int) for an AF code.

    Unknown codes default to ("park", 0) — the engine NEVER auto-fixes something it
    cannot find a policy for. The per-gate `max_fix_attempts` from the manifest wins;
    FBAD_MAX_FIX_ATTEMPTS (if set to an int) overrides every `auto` gate's budget."""
    pol = load_policy(manifest)
    rp = pol["policy"]
    entry = pol["by_code"].get(af_code)
    if entry is None:
        return ("park", 0)
    recovery = entry["recovery"] or "park"
    if recovery != "auto":
        return ("park", 0)
    env = os.environ.get(rp.get("env_override", "FBAD_MAX_FIX_ATTEMPTS"), "")
    if str(env).strip().isdigit():
        return ("auto", max(1, int(str(env).strip())))
    mx = entry["max_fix_attempts"]
    if mx <= 0:
        mx = int(rp.get("default_max_fix_attempts", 3) or 3)
    return ("auto", max(1, mx))


def total_budget(manifest=None) -> int:
    rp = load_policy(manifest)["policy"]
    return _policy_int(rp, "total_budget_default", "total_budget_env", 30)


def no_progress_cap(manifest=None) -> int:
    rp = load_policy(manifest)["policy"]
    return _policy_int(rp, "no_progress_default", "no_progress_env", 2)


# ---------------------------------------------------------------------------
# Durable-root resolution (mirrors unpark-build.sh)
# ---------------------------------------------------------------------------
def resolve_oc_root() -> Path:
    env = os.environ.get("FBAD_OC_ROOT", "").strip()
    if env:
        return Path(env)
    if Path("/data/.openclaw").is_dir():
        return Path("/data/.openclaw")
    home = os.environ.get("HOME", "")
    if home:
        return Path(home) / ".openclaw"
    return Path("/data/.openclaw")


def resolve_runs_root() -> Path:
    return resolve_oc_root() / "workspace" / "fbad-runs"


def box_park_dir() -> Path:
    return resolve_oc_root() / "workspace" / ".park" / "fbad"


_TMP_PREFIXES = ("/tmp", "/private/tmp", "/var/folders", "/private/var/folders",
                 "/var/tmp", "/private/var/tmp")


def is_tmp_path(path) -> bool:
    s = str(Path(path).resolve())
    prefixes = list(_TMP_PREFIXES)
    td = os.environ.get("TMPDIR", "").rstrip("/")
    if td:
        prefixes.append(td)
    for pre in prefixes:
        if pre and (s == pre or s.startswith(pre + "/")):
            return True
    return False


def refuse_paid_tmp(run_dir, paid: bool, allow_ephemeral: bool) -> str:
    """A PAID run must be checkpointed on durable disk, never a reboot-wiped tmp dir.
    Returns a refusal reason (non-empty) when the run must be refused, else ""."""
    if allow_ephemeral or not paid:
        return ""
    if is_tmp_path(run_dir):
        return ("a paid run must be checkpointed under a durable workspace dir "
                f"({resolve_runs_root()}/<run_id>), not a reboot-wiped temp dir "
                f"({run_dir}). A park written to /tmp would not survive a reboot, so the "
                "checkpoint guarantee would be a lie. Re-run the job under the durable "
                "runs root, or pass --allow-ephemeral for a dry/test-only run.")
    return ""


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------
def _atomic_write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Durable attempt / fingerprint ledger — working/checkpoints/ad_recovery_state.json
# ---------------------------------------------------------------------------
def _state_path(run_dir: Path) -> Path:
    return Path(run_dir) / "working" / "checkpoints" / "ad_recovery_state.json"


def load_state(run_dir) -> dict:
    p = _state_path(run_dir)
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text())
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_state(run_dir, obj: dict) -> None:
    _atomic_write_json(_state_path(run_dir), obj)


def attempts(run_dir, key: str) -> int:
    return int(load_state(run_dir).get("attempts", {}).get(key, 0))


def total_attempts(run_dir) -> int:
    return int(load_state(run_dir).get("total_attempts", 0))


def bump(run_dir, key: str) -> int:
    """Atomically increment the per-key + global fix-attempt counters. Returns the new
    per-key count. Done BEFORE the engine returns a REDO so the budget can never be
    out-run by a crash mid-attempt."""
    st = load_state(run_dir)
    a = st.setdefault("attempts", {})
    a[key] = int(a.get(key, 0)) + 1
    st["total_attempts"] = int(st.get("total_attempts", 0)) + 1
    _save_state(run_dir, st)
    return a[key]


def fingerprint(run_dir, key: str, artifact_bytes) -> tuple:
    """Record the sha256 of the redo artifact for this key. Returns
    (status:'changed'|'same', no_progress_count). A 'same' result means the agent
    resubmitted a byte-identical artifact — the redo isn't changing anything."""
    if isinstance(artifact_bytes, (bytes, bytearray)):
        raw = bytes(artifact_bytes)
    else:
        raw = str(artifact_bytes).encode("utf-8", errors="replace")
    h = hashlib.sha256(raw).hexdigest()
    st = load_state(run_dir)
    fps = st.setdefault("fingerprints", {})
    nps = st.setdefault("no_progress", {})
    prev = fps.get(key)
    if prev == h:
        nps[key] = int(nps.get(key, 0)) + 1
        status = "same"
    else:
        nps[key] = 0
        status = "changed"
    fps[key] = h
    _save_state(run_dir, st)
    return status, int(nps.get(key, 0))


# ---------------------------------------------------------------------------
# The recovery DECISION — the single source of truth for "redo vs park"
# ---------------------------------------------------------------------------
def af_from_reason(reason: str):
    m = AF_RE.search(reason or "")
    return m.group(0) if m else None


def classify_fail(run_dir, manifest, phase_id: str, af: str, item=None,
                  artifact_bytes=b"") -> dict:
    """Decide what to do about a REAL failing check, given its AF code. Returns a
    decision dict. The durable counters/fingerprint are updated here so the bound is
    enforced in the engine — the agent cannot loop forever, discard work, or
    self-correct past a dangerous gate.

      {"decision":"PARK","reason":"park_gate", ...}            # recovery:"park"
      {"decision":"PARK","reason":"no_progress", ...}          # identical resubmits
      {"decision":"PARK","reason":"budget_exhausted", ...}     # per-key budget spent
      {"decision":"PARK","reason":"total_budget_exhausted",...}# global budget spent
      {"decision":"REDO","attempt":n,"max":N, ...}             # redo ONLY this artifact
    """
    recovery, maxn = policy(af, manifest)
    key = f"{phase_id}:{af}:{item if item is not None else '*'}"
    base = {"recovery": recovery, "af": af, "key": key, "phase": phase_id,
            "item": item}
    if recovery == "park":
        base.update({"decision": "PARK", "reason": "park_gate"})
        return base
    # recovery == "auto"
    status, np = fingerprint(run_dir, key, artifact_bytes)
    if status == "same" and np >= no_progress_cap(manifest):
        base.update({"decision": "PARK", "reason": "no_progress", "no_progress": np})
        return base
    cur = attempts(run_dir, key)
    if cur >= maxn:
        base.update({"decision": "PARK", "reason": "budget_exhausted",
                     "attempt": cur, "max": maxn})
        return base
    if total_attempts(run_dir) >= total_budget(manifest):
        base.update({"decision": "PARK", "reason": "total_budget_exhausted",
                     "max": maxn})
        return base
    n = bump(run_dir, key)
    base.update({"decision": "REDO", "attempt": n, "max": maxn})
    return base


# ---------------------------------------------------------------------------
# Next-actionable-phase (factored from ad_director.print_plan READY logic)
# ---------------------------------------------------------------------------
def next_actionable_phase(phases, attested_ids):
    """Lowest-order phase that is NOT attested and whose every depends_on IS attested.
    None when every phase is attested (the run is complete)."""
    att = set(attested_ids)
    for ph in sorted(phases, key=lambda p: p.get("order", 0)):
        if ph["id"] in att:
            continue
        if all(d in att for d in (ph.get("depends_on") or [])):
            return ph
    return None


# ---------------------------------------------------------------------------
# Durable park checkpoint — working/checkpoints/PARKED.json + box-level pointer
# ---------------------------------------------------------------------------
def _park_path(run_dir: Path) -> Path:
    return Path(run_dir) / "working" / "checkpoints" / "PARKED.json"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_park(run_dir, *, run_id, parked_by_af, park_class, phase, waiting_for,
               resume_clears_when, feedback, attested_phases, selections=None,
               spent_usd=0.0, ledger_done_keys=None) -> dict:
    """Write the DURABLE save-point. Nothing is ever discarded on a park — every stop
    is a checkpoint. Writes PARKED.json (atomic) AND a box-level pointer so an operator
    / a future cron can enumerate parked runs without knowing the run dir."""
    rd = Path(run_dir).resolve()
    payload = {
        "schema": 1,
        "run_id": run_id or rd.name,
        "parked_at": _now(),
        "parked_by_af": parked_by_af,
        "park_class": park_class,
        "phase": phase,
        "waiting_for": waiting_for,
        "resume_clears_when": resume_clears_when,
        "feedback": feedback,
        "attested_phases": list(attested_phases or []),
        "selections": selections or {},
        "spent_usd": spent_usd,
        "ledger_done_keys": list(ledger_done_keys or []),
        "recovery_state_ref": "working/checkpoints/ad_recovery_state.json",
    }
    _atomic_write_json(_park_path(rd), payload)
    # box-level pointer (best-effort; never blocks the local checkpoint).
    try:
        bp = box_park_dir()
        ptr = bp / f"{payload['run_id']}.parked"
        _atomic_write_json(ptr, {"run_dir": str(rd), "run_id": payload["run_id"],
                                 "parked_by_af": parked_by_af,
                                 "park_class": park_class, "parked_at": payload["parked_at"]})
    except Exception:  # noqa: BLE001
        pass
    return payload


def read_park(run_dir):
    p = _park_path(run_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


def clear_park(run_dir, run_id=None) -> None:
    """Remove PARKED.json + the box pointer. Called only after the blocker's REAL
    checker(s) pass — a park is never auto-cleared without the real check passing."""
    rd = Path(run_dir).resolve()
    p = _park_path(rd)
    rid = run_id
    if rid is None:
        parked = read_park(rd)
        rid = (parked or {}).get("run_id") or rd.name
    if p.exists():
        try:
            p.unlink()
        except Exception:  # noqa: BLE001
            pass
    try:
        ptr = box_park_dir() / f"{rid}.parked"
        if ptr.exists():
            ptr.unlink()
    except Exception:  # noqa: BLE001
        pass


def list_parked():
    """Enumerate parked fbad runs from the box pointer dir (operator/cron helper)."""
    out = []
    bp = box_park_dir()
    if not bp.is_dir():
        return out
    for f in sorted(bp.glob("*.parked")):
        try:
            out.append(json.loads(f.read_text()))
        except Exception:  # noqa: BLE001
            out.append({"pointer": str(f), "unreadable": True})
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "--policy":
        pol = load_policy()
        print(json.dumps({
            "policy": pol["policy"],
            "by_code": pol["by_code"],
            "total_budget": total_budget(),
            "no_progress_cap": no_progress_cap(),
        }, indent=2))
    elif len(sys.argv) >= 2 and sys.argv[1] == "--list-parked":
        print(json.dumps(list_parked(), indent=2))
    else:
        print("usage: ad_recovery.py --policy | --list-parked", file=sys.stderr)
        sys.exit(2)
