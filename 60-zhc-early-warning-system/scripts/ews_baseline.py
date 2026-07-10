#!/usr/bin/env python3
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: ews_baseline.py
# BASELINE: making "changed" a computable fact (spec 4.3)
# -----------------------------------------------------------------------------
# The baseline is AUTHORITATIVE. Reality is diffed against it; reality NEVER
# silently becomes it. This module:
#   pin              read the live config AS INSTALLED-AND-APPROVED and write
#                    baseline.json (values, or sha256 HASHES for sensitive keys),
#                    plus cron inventory, model allowlist, config owner/mode,
#                    platform/user, and the skills manifest hash.
#   diff             report per-monitored-key baseline-vs-live with a computed
#                    DIRECTION (raise/widen/loosen/tighten/change) - the reusable
#                    engine S1/S4/S10 consume.
#   approve-baseline the ONLY path that updates the baseline: it names the key(s),
#                    writes a signed stamp (key path + new value hash + operator +
#                    ts) via the ledger, and folds the new value into baseline.json.
#                    That stamp is exactly what Signal S4 checks for. This is the
#                    entire enforcement of "never silently raise a safety limit".
#   show             print the pinned baseline (audit).
#
# STDLIB ONLY. Zero model, zero network. DOCTRINE: sensitive keys (botToken and
# anything credential-shaped) are baselined by HASH ONLY, never by value; nothing
# here prints a secret. Reads config; writes only STATE (baseline.json + ledger),
# never the live config. Warns (does not hard-refuse) as root since it is not a
# config write.
#
# EXIT CODES: 0 OK, 1 error, 2 usage, 3 not-found (no baseline / unknown key).
# =============================================================================
"""ews_baseline.py - pin / diff / approve-baseline for the ZHC Early Warning System."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import ews_common as C  # noqa: E402
from ews_ledger import Ledger, default_state_dir, detect_platform, now_utc  # noqa: E402

EX_OK, EX_ERR, EX_USAGE, EX_NOTFOUND = 0, 1, 2, 3

# policy-loosening rank: a higher rank is MORE open (an access-cap raise).
_POLICY_RANK = {"closed": 0, "none": 0, "off": 0, "disabled": 0,
                "allowlist": 1, "contacts": 1, "paired": 1, "known": 1,
                "open": 2, "all": 2, "any": 2, "public": 2, "everyone": 2}


def baseline_path(state_dir: Path | None = None) -> Path:
    return (state_dir or default_state_dir()) / "baseline.json"


# --------------------------------------------------------------------------- #
# stored form of a monitored value (value, or hash for sensitive keys)
# --------------------------------------------------------------------------- #
def _stored_form(key_spec: dict, value):
    if value is C.MISSING:
        return {"present": False}
    if key_spec.get("hashed"):
        return {"present": True, "hashed": True, "hash": C.sha256_of_value(value)}
    return {"present": True, "hashed": False, "value": value}


def _read_monitored_keys() -> list:
    return C.load_skill_config("monitored-keys.json").get("keys", [])


# --------------------------------------------------------------------------- #
# skills manifest hash (S9) - reuse scripts/skill-content-hash.sh when present
# --------------------------------------------------------------------------- #
def _skills_manifest():
    """Return {skill_name: digest, '__TREE_SHA__': rollup} using the repo's
    skill-content-hash.sh over the installed skills root, or None if unavailable."""
    skills_root = C.openclaw_root() / "skills"
    if not skills_root.is_dir():
        return None
    # the shared helper lives at the repo root in a dev checkout; on a box it ships
    # under skills/scripts or is absent. Try a few known locations.
    candidates = [
        skills_root / "scripts" / "skill-content-hash.sh",
        C.openclaw_root() / "scripts" / "skill-content-hash.sh",
    ]
    tool = next((c for c in candidates if c.is_file()), None)
    if tool is None:
        return None
    try:
        out = subprocess.run(["bash", str(tool), str(skills_root)],
                             capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    manifest = {}
    for line in out.stdout.splitlines():
        if "|" in line:
            name, digest = line.split("|", 1)
            manifest[name.strip()] = digest.strip()
    return manifest or None


# --------------------------------------------------------------------------- #
# pin
# --------------------------------------------------------------------------- #
def build_baseline(config: dict) -> dict:
    keys = _read_monitored_keys()
    monitored = {}
    for spec in keys:
        path = spec["path"]
        val = C.dotpath_get(config, path)
        monitored[path] = {"class": spec.get("class"), **_stored_form(spec, val)}
    cfg_path = C.default_config_path()
    owner, mode = None, None
    try:
        st = cfg_path.stat()
        import pwd
        try:
            owner = pwd.getpwuid(st.st_uid).pw_name
        except (KeyError, ImportError):
            owner = str(st.st_uid)
        mode = oct(st.st_mode & 0o777)
    except OSError:
        pass
    return {
        "version": 1,
        "pinned_at": now_utc(),
        "platform": detect_platform(),
        "user": os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown",
        "config_path": str(cfg_path),
        "config_owner": owner,
        "config_mode": mode,
        "monitored": monitored,
        "model_allowlist": C.extract_model_ids(config),
        "cron_inventory": C.cron_inventory(config),
        "skills_manifest": _skills_manifest(),
    }


def cmd_pin(args) -> int:
    config = C.read_config(args.config)
    baseline = build_baseline(config)
    bp = baseline_path(Path(args.state_dir) if args.state_dir else None)
    bp.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".baseline.", suffix=".tmp", dir=str(bp.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(baseline, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, bp)
        os.chmod(bp, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    _emit({"ok": True, "action": "pin", "baseline": str(bp),
           "monitored_keys": len(baseline["monitored"]),
           "model_allowlist": len(baseline["model_allowlist"]),
           "cron_entries": len(baseline["cron_inventory"]),
           "config_owner": baseline["config_owner"], "config_mode": baseline["config_mode"]})
    return EX_OK


# --------------------------------------------------------------------------- #
# diff engine (the reusable core S1/S4/S10 consume)
# --------------------------------------------------------------------------- #
def _direction(klass, path, base_stored, live_val):
    """Compute the direction of a change. base_stored is the baseline 'monitored'
    entry; live_val is the live value (or C.MISSING)."""
    base_present = base_stored.get("present", False)
    live_present = live_val is not C.MISSING
    if not base_present and not live_present:
        return "same"
    if base_present != live_present:
        return "added" if live_present else "removed"

    # hashed keys: compare hashes only (never the value)
    if base_stored.get("hashed"):
        changed = base_stored.get("hash") != C.sha256_of_value(live_val)
        return "change" if changed else "same"

    base_val = base_stored.get("value")
    if C.canonical(base_val) == C.canonical(live_val):
        return "same"

    if klass == "cap":
        try:
            if float(live_val) > float(base_val):
                return "raise"
            if float(live_val) < float(base_val):
                return "lower"
        except (TypeError, ValueError):
            return "change"
        return "change"

    if klass == "access":
        # allowFrom list -> widen/narrow; policy string -> loosen/tighten
        if isinstance(base_val, list) or isinstance(live_val, list):
            b = set(base_val or []) if isinstance(base_val, list) else set()
            l = set(live_val or []) if isinstance(live_val, list) else set()
            if b < l or len(l) > len(b):
                return "widen"
            if l < b or len(l) < len(b):
                return "narrow"
            return "change"
        br = _POLICY_RANK.get(str(base_val).lower())
        lr = _POLICY_RANK.get(str(live_val).lower())
        if br is not None and lr is not None:
            if lr > br:
                return "loosen"
            if lr < br:
                return "tighten"
        return "change"

    if klass == "furnace" and path.endswith("heartbeat.every"):
        bb = C.fires_per_day_bound(base_val)
        lb = C.fires_per_day_bound(live_val)
        if bb is not None and lb is not None:
            if lb > bb:
                return "tighten"   # fires MORE per day = tighter cadence = more spend
            if lb < bb:
                return "loosen"
        return "change"

    return "change"


# the dangerous direction per class (used by S4 severity)
_DANGER = {"cap": {"raise"}, "access": {"widen", "loosen"}, "furnace": {"tighten"}}


def compute_diff(baseline: dict, config: dict) -> list:
    """Per monitored key: {path, class, changed, direction, dangerous, baseline_present,
    live_present, hashed}. NEVER includes a raw value for a hashed key. For plain keys
    the values are included so the sentinel can build a value-free alert detail."""
    keys = {k["path"]: k for k in _read_monitored_keys()}
    mon = baseline.get("monitored", {})
    out = []
    for path, spec in keys.items():
        klass = spec.get("class")
        base_stored = mon.get(path, {"present": False})
        live_val = C.dotpath_get(config, path)
        direction = _direction(klass, path, base_stored, live_val)
        changed = direction not in ("same",)
        dangerous = direction in _DANGER.get(klass, set())
        rec = {"path": path, "class": klass, "direction": direction, "changed": changed,
               "dangerous": dangerous, "hashed": bool(base_stored.get("hashed")),
               "baseline_present": base_stored.get("present", False),
               "live_present": live_val is not C.MISSING,
               "spec_severity": spec.get("severity")}
        if not base_stored.get("hashed"):
            # value-free for anything credential-shaped is not needed here (those are
            # marked hashed in the catalog); plain caps/models/policies are safe.
            rec["baseline_value"] = base_stored.get("value")
            rec["live_value"] = None if live_val is C.MISSING else live_val
        out.append(rec)
    return out


def cmd_diff(args) -> int:
    bp = baseline_path(Path(args.state_dir) if args.state_dir else None)
    if not bp.is_file():
        _emit({"ok": False, "error": "no baseline pinned", "baseline": str(bp)})
        return EX_NOTFOUND
    baseline = json.loads(bp.read_text(encoding="utf-8"))
    config = C.read_config(args.config)
    diffs = compute_diff(baseline, config)
    changed = [d for d in diffs if d["changed"]]
    _emit({"ok": True, "action": "diff", "changed_count": len(changed), "diffs": diffs})
    return EX_OK


# --------------------------------------------------------------------------- #
# approve-baseline (the only path that updates the baseline)
# --------------------------------------------------------------------------- #
def cmd_approve(args) -> int:
    key = args.key
    keys = {k["path"]: k for k in _read_monitored_keys()}
    if key not in keys:
        _emit({"ok": False, "error": "unknown monitored key", "key": key})
        return EX_NOTFOUND
    bp = baseline_path(Path(args.state_dir) if args.state_dir else None)
    if not bp.is_file():
        _emit({"ok": False, "error": "no baseline to approve against", "baseline": str(bp)})
        return EX_NOTFOUND
    baseline = json.loads(bp.read_text(encoding="utf-8"))
    config = C.read_config(args.config)
    live_val = C.dotpath_get(config, key)
    if live_val is C.MISSING:
        _emit({"ok": False, "error": "key absent in live config; nothing to approve", "key": key})
        return EX_NOTFOUND
    new_hash = C.sha256_of_value(live_val)
    operator = args.operator or os.environ.get("EWS_OPERATOR") or "operator"

    # 1) write the signed stamp (what S4 checks for)
    state_dir = Path(args.state_dir) if args.state_dir else None
    with Ledger(state_dir) as led:
        stamp_id = led.record_stamp(key, new_hash, operator)
    # 2) fold the new value into the baseline so subsequent diffs are clean
    baseline.setdefault("monitored", {})[key] = {"class": keys[key].get("class"),
                                                 **_stored_form(keys[key], live_val)}
    fd, tmp = tempfile.mkstemp(prefix=".baseline.", suffix=".tmp", dir=str(bp.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(baseline, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, bp)
        os.chmod(bp, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    _emit({"ok": True, "action": "approve-baseline", "key": key, "operator": operator,
           "stamp_id": stamp_id, "new_value_hash": new_hash})
    return EX_OK


def cmd_show(args) -> int:
    bp = baseline_path(Path(args.state_dir) if args.state_dir else None)
    if not bp.is_file():
        _emit({"ok": False, "error": "no baseline pinned", "baseline": str(bp)})
        return EX_NOTFOUND
    _emit(json.loads(bp.read_text(encoding="utf-8")))
    return EX_OK


# --------------------------------------------------------------------------- #
def _emit(obj):
    sys.stdout.write(json.dumps(obj, sort_keys=True) + "\n")


def _warn_root():
    if C.is_root():
        sys.stderr.write("WARN [ews_baseline]: running as root; baseline state should be "
                         "written by the box user.\n")


def _cli(argv=None):
    ap = argparse.ArgumentParser(prog="ews_baseline.py",
                                 description="Pin / diff / approve the EWS baseline.")
    ap.add_argument("--state-dir")
    ap.add_argument("--config", help="live openclaw.json path (default $EWS_CONFIG_PATH or box path)")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=False)
    sub.add_parser("pin")
    sub.add_parser("diff")
    sub.add_parser("show")
    sp = sub.add_parser("approve-baseline")
    sp.add_argument("--key", required=True)
    sp.add_argument("--operator")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.cmd:
        ap.error("a subcommand is required (or use --self-test)")
    _warn_root()
    try:
        if args.cmd == "pin":
            return cmd_pin(args)
        if args.cmd == "diff":
            return cmd_diff(args)
        if args.cmd == "show":
            return cmd_show(args)
        if args.cmd == "approve-baseline":
            return cmd_approve(args)
    except FileNotFoundError as exc:
        _emit({"ok": False, "error": "file not found: %s" % exc})
        return EX_NOTFOUND
    except (ValueError, OSError) as exc:
        _emit({"ok": False, "error": str(exc)})
        return EX_ERR
    return EX_USAGE


# --------------------------------------------------------------------------- #
def self_test():
    import tempfile as _tf
    print("[ews_baseline] self-test: pin, diff directions, approve-stamp, clean-after-approve")
    base_cfg = {
        "agents": {"defaults": {
            "model": {"primary": "glm-5.2", "fallbacks": ["minimax-m3:cloud"]},
            "models": {"openrouter/glm-5.2": {}},
            "maxConcurrent": 16,
            "subagents": {"model": {"primary": "gemini-3.5-flash", "fallbacks": []},
                          "maxConcurrent": 16, "maxChildrenPerAgent": 8, "maxSpawnDepth": 3},
            "compaction": {"mode": "memoryFlush", "memoryFlush": {"softThresholdTokens": 20000}},
            "heartbeat": {"every": "@daily", "model": "minimax-m3"}}},
        "channels": {"telegram": {"accounts": {"default": {
            "allowFrom": ["111"], "dmPolicy": "allowlist", "groupPolicy": "closed",
            "botToken": "not-a-real-token-value-1234567890"}}}},
        "cron": [{"name": "ews-tick", "schedule": "*/15 * * * *", "delivery": "silent"}]}

    with _tf.TemporaryDirectory() as td:
        os.environ["EWS_STATE_DIR"] = str(Path(td) / "ews")
        cfgp = Path(td) / "openclaw.json"
        cfgp.write_text(json.dumps(base_cfg), encoding="utf-8")
        os.environ["EWS_CONFIG_PATH"] = str(cfgp)

        # pin
        baseline = build_baseline(base_cfg)
        bp = baseline_path()
        bp.parent.mkdir(parents=True, exist_ok=True)
        bp.write_text(json.dumps(baseline), encoding="utf-8")
        # botToken must be stored as a HASH, never the value
        tok_entry = baseline["monitored"]["channels.telegram.accounts.default.botToken"]
        assert tok_entry.get("hashed") and "hash" in tok_entry and "value" not in tok_entry
        assert "not-a-real-token-value" not in json.dumps(baseline)
        print("  pin case: PASS (sensitive key hashed, no value in baseline)")

        # unchanged config -> zero changed
        d0 = compute_diff(baseline, base_cfg)
        assert all(not x["changed"] for x in d0), [x for x in d0 if x["changed"]]
        print("  no-drift case: PASS (identical config = 0 changed)")

        # cap RAISE
        raised = json.loads(json.dumps(base_cfg))
        raised["agents"]["defaults"]["subagents"]["maxConcurrent"] = 64
        d1 = {x["path"]: x for x in compute_diff(baseline, raised)}
        r = d1["agents.defaults.subagents.maxConcurrent"]
        assert r["changed"] and r["direction"] == "raise" and r["dangerous"]
        print("  cap-raise case: PASS (direction=raise, dangerous)")

        # access WIDEN + policy LOOSEN
        widened = json.loads(json.dumps(base_cfg))
        widened["channels"]["telegram"]["accounts"]["default"]["allowFrom"] = ["111", "222", "333"]
        widened["channels"]["telegram"]["accounts"]["default"]["dmPolicy"] = "open"
        d2 = {x["path"]: x for x in compute_diff(baseline, widened)}
        assert d2["channels.telegram.accounts.default.allowFrom"]["direction"] == "widen"
        assert d2["channels.telegram.accounts.default.dmPolicy"]["direction"] == "loosen"
        assert d2["channels.telegram.accounts.default.allowFrom"]["dangerous"]
        print("  access case: PASS (widen + loosen both dangerous)")

        # heartbeat TIGHTEN (more fires/day)
        furn = json.loads(json.dumps(base_cfg))
        furn["agents"]["defaults"]["heartbeat"]["every"] = "*/5 * * * *"
        d3 = {x["path"]: x for x in compute_diff(baseline, furn)}
        assert d3["agents.defaults.heartbeat.every"]["direction"] == "tighten"
        print("  furnace case: PASS (heartbeat tightened)")

        # model change (not dangerous, but changed)
        modc = json.loads(json.dumps(base_cfg))
        modc["agents"]["defaults"]["model"]["primary"] = "some-new-model"
        d4 = {x["path"]: x for x in compute_diff(baseline, modc)}
        assert d4["agents.defaults.model.primary"]["changed"]
        assert not d4["agents.defaults.model.primary"]["dangerous"]
        print("  model case: PASS (changed, not a cap so not 'dangerous')")

        # hashed key change is detected WITHOUT exposing the value
        rot = json.loads(json.dumps(base_cfg))
        rot["channels"]["telegram"]["accounts"]["default"]["botToken"] = "different-token-value-0987654321"
        d5 = {x["path"]: x for x in compute_diff(baseline, rot)}
        tk = d5["channels.telegram.accounts.default.botToken"]
        assert tk["changed"] and tk["hashed"] and "live_value" not in tk and "baseline_value" not in tk
        print("  hashed-key case: PASS (rotation detected, value never present in diff)")

        # approve-baseline stamps the raise and clears it
        cfgp.write_text(json.dumps(raised), encoding="utf-8")
        rc = cmd_approve(argparse.Namespace(key="agents.defaults.subagents.maxConcurrent",
                                            operator="operator", state_dir=None, config=str(cfgp)))
        assert rc == EX_OK
        new_baseline = json.loads(baseline_path().read_text(encoding="utf-8"))
        d6 = {x["path"]: x for x in compute_diff(new_baseline, raised)}
        assert not d6["agents.defaults.subagents.maxConcurrent"]["changed"]
        with Ledger() as led:
            assert led.has_stamp("agents.defaults.subagents.maxConcurrent", C.sha256_of_value(64))
        print("  approve case: PASS (stamp written; diff clean after approval)")

        os.environ.pop("EWS_STATE_DIR", None)
        os.environ.pop("EWS_CONFIG_PATH", None)

    print("[ews_baseline] self-test: PASS")
    return EX_OK


if __name__ == "__main__":
    sys.exit(_cli())
