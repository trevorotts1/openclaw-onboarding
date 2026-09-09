#!/usr/bin/env python3
"""sp_doctor.py (PRES-051): classify files-present, registered, event-observed,
engine-gate-tested separately on each actual host.

Usage:
  sp_doctor.py --skill-dir DIR [--host NAME] [--json] [--handshake]
  sp_doctor.py --check-registration --settings PATH   # owned-entries check
  sp_doctor.py --install --settings PATH --backup-dir DIR
  sp_doctor.py --uninstall --settings PATH

Install/uninstall preserve unrelated settings/hooks: --install records owned
registrations + a backup; --uninstall removes only owned entries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sp_hook_common import (  # noqa: E402
    HOOK_VERSION,
    SCHEMA_VERSION,
    engine_entry,
    engine_scripts_dir,
    utcnow,
)

OWNED_MARKER = "signature-presentation"
HANDLERS = {
    "SessionStart": "sp_session_start.py",
    "PreToolUse": "sp_pre_tool_use.py",
    "PostToolUse": "sp_post_tool_use.py",
    "Stop": "sp_stop.py",
}


def sha16(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return "missing"


def files_present(skill_dir: Path) -> dict:
    hooks_json = skill_dir / "hooks" / "hooks.json"
    plugin_json = skill_dir / ".claude-plugin" / "plugin.json"
    out = {
        "hooks_json": hooks_json.is_file(),
        "plugin_json": plugin_json.is_file(),
        "handlers": {k: (skill_dir / "scripts" / "hooks" / v).is_file() for k, v in HANDLERS.items()},
        "dispatcher": (skill_dir / "scripts" / "hooks" / "sp-hook.sh").is_file(),
        "common": (skill_dir / "scripts" / "hooks" / "sp_hook_common.py").is_file(),
    }
    out["all"] = bool(
        out["hooks_json"] and out["plugin_json"] and all(out["handlers"].values())
        and out["dispatcher"] and out["common"]
    )
    return out


def _settings_events(settings: dict) -> dict:
    return settings.get("hooks", {}) if isinstance(settings, dict) else {}


def owned_entries(settings: dict) -> list:
    """Hook entry commands that belong to this plugin (command text match)."""
    owned = []
    for event, groups in _settings_events(settings).items():
        if not isinstance(groups, list):
            continue
        for gi, group in enumerate(groups):
            for hi, hook in enumerate((group or {}).get("hooks", []) or []):
                cmd = (hook or {}).get("command", "")
                if "51-signature-presentation/scripts/hooks/sp-hook.sh" in cmd or (
                    "sp-hook.sh" in cmd and OWNED_MARKER in cmd
                ):
                    owned.append({"event": event, "group": gi, "index": hi, "command": cmd})
    return owned


def check_registration(settings_path: Path) -> dict:
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "reason": f"settings unreadable: {type(exc).__name__}"}
    owned = owned_entries(settings)
    by_event = sorted({o["event"] for o in owned})
    return {
        "ok": True,
        "owned_count": len(owned),
        "events": by_event,
        "owned": owned,
        "registered": len(owned) > 0,
    }


def cmd_install(args) -> int:
    skill_dir = Path(args.skill_dir).resolve()
    hooks_json = skill_dir / "hooks" / "hooks.json"
    if not hooks_json.is_file():
        print(f"doctor: hooks.json missing at {hooks_json}", file=sys.stderr)
        return 2
    try:
        wanted = json.loads(hooks_json.read_text(encoding="utf-8"))["hooks"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"doctor: hooks.json unreadable: {exc}", file=sys.stderr)
        return 2
    settings_path = Path(args.settings).expanduser()
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
    except json.JSONDecodeError as exc:
        print(f"doctor: settings unparseable, refusing to touch: {exc}", file=sys.stderr)
        return 2
    if not isinstance(settings, dict):
        print("doctor: settings root is not an object; refusing to touch", file=sys.stderr)
        return 2
    backup_dir = Path(args.backup_dir).expanduser()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"settings-{utcnow().replace(':', '')}.bak.json"
    if settings_path.is_file():
        shutil.copy2(settings_path, backup)
        print(f"doctor: backup -> {backup}")
    else:
        backup.write_text("{}\n", encoding="utf-8")
        print(f"doctor: no settings file; backup of empty object -> {backup}")
    hooks = settings.setdefault("hooks", {})
    installed = []
    for event, groups in wanted.items():
        dest = hooks.setdefault(event, [])
        for group in groups if isinstance(groups, list) else []:
            for hook in (group or {}).get("hooks", []) or []:
                cmd = (hook or {}).get("command", "")
                if "sp-hook.sh" not in cmd:
                    continue
                resolved = cmd.replace("${CLAUDE_PLUGIN_ROOT}", str(skill_dir))
                # Deduplicate: skip when an owned command for this event+script exists.
                exists = any(
                    (h or {}).get("command", "") in (cmd, resolved)
                    or "sp-hook.sh" in (h or {}).get("command", "")
                    and OWNED_MARKER in (h or {}).get("command", "")
                    for g in dest
                    for h in (g or {}).get("hooks", []) or []
                )
                if exists:
                    continue
                new_hook = dict(hook)
                new_hook["command"] = resolved
                matcher = (group or {}).get("matcher")
                entry = {"hooks": [new_hook]}
                if matcher:
                    entry["matcher"] = matcher
                dest.append(entry)
                installed.append(f"{event}:{resolved}")
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    record = {
        "schema": "sp-doctor-install-v1",
        "at": utcnow(),
        "skill_dir": str(skill_dir),
        "settings": str(settings_path),
        "backup": str(backup),
        "installed": installed,
    }
    (backup_dir / "sp-owned-install.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"doctor: installed {len(installed)} owned hook(s); record -> {backup_dir}/sp-owned-install.json")
    for line in installed:
        print(f"  + {line}")
    return 0


def cmd_uninstall(args) -> int:
    settings_path = Path(args.settings).expanduser()
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"doctor: settings unreadable: {exc}", file=sys.stderr)
        return 2
    removed = []
    hooks = settings.get("hooks")
    if isinstance(hooks, dict):
        for event, groups in list(hooks.items()):
            if not isinstance(groups, list):
                continue
            new_groups = []
            for group in groups if isinstance(groups, list) else []:
                kept = []
                for hook in (group or {}).get("hooks", []) or []:
                    cmd = (hook or {}).get("command", "")
                    if "sp-hook.sh" in cmd and OWNED_MARKER in cmd:
                        removed.append(f"{event}:{cmd}")
                    else:
                        kept.append(hook)
                if kept:
                    group["hooks"] = kept
                    new_groups.append(group)
            # prune groups/events left with zero hooks only when they carried no
            # unrelated entries (kept == [] for every group in this event)
            if new_groups:
                hooks[event] = new_groups
            else:
                hooks.pop(event, None)
        if not hooks:
            settings.pop("hooks", None)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    print(f"doctor: removed {len(removed)} owned hook(s); unrelated entries preserved")
    for line in removed:
        print(f"  - {line}")
    return 0


def run_handshake_matrix(skill_dir: Path, host: str) -> dict:
    """Feed malformed input, timeout-shaped input, duplicate/reentrant events
    and an unrelated session through each handler; deterministic bounded result,
    no duplicate work, no secrets in stdout."""
    hook_sh = skill_dir / "scripts" / "hooks" / "sp-hook.sh"
    py = sys.executable or "python3"
    handlers = {
        "sp_session_start.py": "session-start",
        "sp_pre_tool_use.py": "pre-tool-use",
        "sp_post_tool_use.py": "post-tool-use",
        "sp_stop.py": "stop",
    }
    base = {
        "session-start": {"session_id": "sp-doc-sess", "hook_event_name": "SessionStart",
                          "cwd": "/tmp/sp-unrelated", "source": "startup"},
        "pre-tool-use": {"session_id": "sp-doc-sess", "hook_event_name": "PreToolUse",
                         "cwd": "/tmp/sp-unrelated", "tool_name": "Bash",
                         "tool_input": {"command": "echo hi"}},
        "post-tool-use": {"session_id": "sp-doc-sess", "hook_event_name": "PostToolUse",
                          "cwd": "/tmp/sp-unrelated", "tool_name": "Bash",
                          "tool_input": {"command": "echo hi"},
                          "tool_response": {"exit": 0}, "tool_use_id": "tu_1"},
        "stop": {"session_id": "sp-doc-sess", "hook_event_name": "Stop",
                 "cwd": "/tmp/sp-unrelated", "stop_hook_active": False,
                 "last_assistant_message": "still working"},
    }
    cases = {
        "malformed": ("{not json",),
        "empty": ("",),
        "wrong-event": (json.dumps({"session_id": "x", "hook_event_name": "Nope", "cwd": "/tmp"}),),
        "missing-fields": (json.dumps({"session_id": "x", "hook_event_name": "SessionStart"}),),
        "foreign-session": None,  # base payload, unbound cwd
        "duplicate": None,  # base payload twice
        "stop-active": (json.dumps({"session_id": "sp-doc-sess", "hook_event_name": "Stop",
                                    "cwd": "/tmp/sp-unrelated", "stop_hook_active": True,
                                    "last_assistant_message": "done, all complete"}),),
    }
    results: dict = {}
    env = {k: v for k, v in os.environ.items()
           if not any(s in k for s in ("TOKEN", "SECRET", "KEY", "PASSWORD", "AUTH"))}
    for fname, sub in handlers.items():
        per: dict = {}
        payload = json.dumps(base[sub])
        for case, override in cases.items():
            if sub == "stop" and case == "stop-active":
                inputs = [override[0]]
            elif override is not None:
                inputs = [override[0]]
            elif case == "duplicate":
                inputs = [payload, payload]
            else:
                inputs = [payload]
            outs = []
            ok = True
            for doc in inputs:
                try:
                    proc = subprocess.run(
                        [str(hook_sh), sub], input=doc, capture_output=True,
                        text=True, timeout=25, env=env,
                        cwd="/tmp",
                    )
                    blob = proc.stdout + proc.stderr
                    secret_hit = any(
                        s in blob for s in ("sk-ant-", "sk-", "xoxb-", "ghp_") if len(s) > 3
                    )
                    outs.append({"rc": proc.returncode, "secret_hit": secret_hit,
                                 "bytes": len(blob)})
                    if proc.returncode not in (0,):
                        ok = False
                except subprocess.TimeoutExpired:
                    outs.append({"rc": "TIMEOUT", "secret_hit": False, "bytes": 0})
                    ok = False
            per[case] = {"ok": ok, "runs": outs}
        results[fname] = per
    results["host"] = host
    return results


def main() -> int:
    ap = argparse.ArgumentParser(prog="sp_doctor.py")
    ap.add_argument("--skill-dir", default=str(Path(__file__).resolve().parent.parent.parent))
    ap.add_argument("--host", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--handshake", action="store_true")
    ap.add_argument("--check-registration", action="store_true")
    ap.add_argument("--settings", default="")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--backup-dir", default="")
    args = ap.parse_args()

    if args.install:
        if not args.settings or not args.backup_dir:
            print("doctor: --install needs --settings and --backup-dir", file=sys.stderr)
            return 2
        return cmd_install(args)
    if args.uninstall:
        if not args.settings:
            print("doctor: --uninstall needs --settings", file=sys.stderr)
            return 2
        return cmd_uninstall(args)
    if args.check_registration:
        if not args.settings:
            print("doctor: --check-registration needs --settings", file=sys.stderr)
            return 2
        print(json.dumps(check_registration(Path(args.settings).expanduser()), indent=2))
        return 0

    skill_dir = Path(args.skill_dir).resolve()
    host = args.host or platform.node()
    files = files_present(skill_dir)
    hooks_json_ok = False
    hooks_events: list = []
    if (skill_dir / "hooks" / "hooks.json").is_file():
        try:
            hooks_json_ok = True
            hooks_events = sorted(
                json.loads((skill_dir / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"].keys()
            )
        except (json.JSONDecodeError, KeyError):
            pass
    scripts = engine_scripts_dir()
    entry = engine_entry(scripts) if scripts else None
    report = {
        "schema": SCHEMA_VERSION + "-doctor-v1",
        "hook_version": HOOK_VERSION,
        "host": host,
        "at": utcnow(),
        "files_present": files,
        "hooks_json_parseable": hooks_json_ok,
        "hooks_events": hooks_events,
        "engine_scripts_dir": str(scripts) if scripts else None,
        "engine_entry": str(entry) if entry else None,
        "handlers_digest": {k: sha16(skill_dir / "scripts" / "hooks" / v) for k, v in HANDLERS.items()},
    }
    if args.handshake:
        report["handshake"] = run_handshake_matrix(skill_dir, host)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"sp_doctor v{HOOK_VERSION} host={host}")
        print(f"  files_present : {files['all']}")
        print(f"  hooks_events  : {hooks_events}")
        print(f"  engine_entry  : {entry or 'NOT FOUND'}")
    ok = bool(files["all"] and hooks_json_ok and entry)
    if args.handshake:
        bad = [f"{h}/{c}" for h, per in report["handshake"].items() if isinstance(per, dict)
               for c, r in per.items() if isinstance(r, dict) and not r.get("ok")]
        if bad:
            print(f"handshake failures: {bad}", file=sys.stderr)
            return 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
