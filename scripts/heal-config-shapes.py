#!/usr/bin/env python3
"""heal-config-shapes.py (v16.1.4) — idempotent self-heal for the three
schema-invalid openclaw.json shapes the onboarding updater historically
injected. Repairs an already-broken config IN PLACE so re-rolling v16.1.4 fixes
boxes corrupted by earlier versions. Running twice never re-breaks (idempotent).

All three shapes were proven against the LIVE `openclaw config schema` on
gateway 2026.5.28 AND 2026.6.8 (identical in both):

  1. plugins.entries.<id> is additionalProperties:false — it allows ONLY
     {enabled, hooks, subagent, llm, config}. Earlier installs wrote
     active-memory's option keys (agents, allowedChatTypes, queryMode,
     promptStyle, timeoutMs, maxSummaryChars) as TOP-LEVEL siblings of
     `enabled`. active-memory IS a real plugin (dist/extensions/active-memory/
     openclaw.plugin.json, activation.onStartup) whose options are plugin
     CONFIG, so they belong UNDER `config`.
       validator: "plugins.entries.active-memory: Invalid input"
       FIX: move every non-{enabled,hooks,subagent,llm,config} key under
            `config`, keep `enabled` at the top level. NEVER delete (deleting
            drops Layer-8 Active Memory).

  2. channels.telegram.accounts.<id> is additionalProperties:false; `helpChatId`
     is NOT a valid account key, and a chat id stuffed there co-mingles
     operators with clients. Escalation is driven by the env var
     OPERATOR_ESCALATION_CHAT_ID, never this key.
       validator: 'channels.telegram.accounts.operator: invalid config: must
                   not have additional properties: "helpChatId"'
       FIX: strip helpChatId from every telegram account and the top-level
            telegram object.

  3. `bindings` is a TOP-LEVEL config key (sibling of `agents`) whose entries are
     {agentId, match:{channel, accountId, ...}}. Earlier installs wrote it UNDER
     `channels` (the gateway reads `bindings` as an unknown channel id) and/or
     with the legacy flat {channel, accountId, agentId} shape.
       validator: "channels.bindings: unknown channel id: bindings"
                  / "bindings.0: Invalid input" (flat shape at the top level)
       FIX: relocate channels.bindings to the top-level `bindings`, convert any
            flat entry to {agentId, match:{...}}, drop an inert token-less
            operator route, dedupe, and remove channels.bindings.

Usage:
  heal-config-shapes.py <openclaw.json>            # heal in place (idempotent)
  heal-config-shapes.py --check <openclaw.json>    # exit 3 if any bad shape (no write)
  heal-config-shapes.py --dry-run <openclaw.json>  # report what WOULD change (no write)

Exit codes: 0 = healed or already clean (or --check clean); 3 = --check found a
bad shape; 2 = usage / IO / parse error. Stdlib only.
"""
import json
import sys

ENTRY_TOP_KEYS = {"enabled", "hooks", "subagent", "llm", "config"}
# Fields a binding `match` object may carry (schema: match.additionalProperties=false).
MATCH_KEYS = ("channel", "accountId", "peer", "guildId", "teamId", "roles")
# Top-level binding fields the route/acp variants allow.
BINDING_PASSTHROUGH = ("type", "comment", "session", "acp")


def heal_plugin_entries(cfg, notes):
    """Move any schema-invalid top-level option keys on every plugins.entries.<id>
    down into that entry's `config` payload. Never deletes an entry."""
    entries = (cfg.get("plugins") or {}).get("entries")
    if not isinstance(entries, dict):
        return
    for pid, entry in list(entries.items()):
        if not isinstance(entry, dict):
            continue
        stray = [k for k in list(entry) if k not in ENTRY_TOP_KEYS]
        if not stray:
            continue
        block = entry.get("config")
        if not isinstance(block, dict):
            block = {}
        for k in stray:
            # preserve an existing config value; otherwise adopt the flat value
            block.setdefault(k, entry.pop(k))
        entry["config"] = block
        notes.append(
            "plugins.entries.%s: nested %d stray option key(s) under config (%s)"
            % (pid, len(stray), ", ".join(stray))
        )


def heal_help_chat_id(cfg, notes):
    """Strip the invalid `helpChatId` key from every telegram account and the
    top-level telegram object. Escalation lives in env OPERATOR_ESCALATION_CHAT_ID."""
    tg = (cfg.get("channels") or {}).get("telegram")
    if not isinstance(tg, dict):
        return
    if tg.pop("helpChatId", None) is not None:
        notes.append("channels.telegram: removed invalid helpChatId")
    accounts = tg.get("accounts")
    if isinstance(accounts, dict):
        for aid, acct in accounts.items():
            if isinstance(acct, dict) and acct.pop("helpChatId", None) is not None:
                notes.append(
                    "channels.telegram.accounts.%s: removed invalid helpChatId" % aid
                )


def _to_route(b):
    """Normalize a binding entry to the valid {agentId, match:{...}} shape.
    Accepts both the legacy flat {channel, accountId, agentId} shape and the
    already-correct {agentId, match} shape. Returns None if unusable."""
    if not isinstance(b, dict):
        return None
    out = {}
    for k in BINDING_PASSTHROUGH:
        if k in b:
            out[k] = b[k]
    out["agentId"] = b.get("agentId") or "main"
    match = b.get("match")
    if isinstance(match, dict):
        match = {k: v for k, v in match.items() if k in MATCH_KEYS}
    else:
        # legacy flat shape: lift channel/accountId/etc. into match
        match = {k: b[k] for k in MATCH_KEYS if k in b}
    if not match.get("channel"):
        return None  # match.channel is required; an entry without it is unusable
    out["match"] = match
    return out


def _binding_key(route):
    m = route.get("match", {})
    return (
        route.get("agentId"),
        m.get("channel"),
        m.get("accountId"),
        json.dumps(m.get("peer"), sort_keys=True) if m.get("peer") else None,
    )


def heal_bindings(cfg, notes):
    """Relocate channels.bindings to the top level, normalize every entry to the
    {agentId, match:{...}} shape, drop an inert token-less operator route, and
    dedupe. Removes channels.bindings."""
    channels = cfg.get("channels")
    misplaced = None
    if isinstance(channels, dict) and "bindings" in channels:
        misplaced = channels.pop("bindings")
        notes.append("channels.bindings: relocated to top-level `bindings`")

    had_top = "bindings" in cfg
    existing = cfg.get("bindings")
    raw = []
    if isinstance(existing, list):
        raw.extend(existing)
    if isinstance(misplaced, list):
        raw.extend(misplaced)
    elif misplaced is not None:
        notes.append("channels.bindings: dropped (not a list)")

    if not raw and misplaced is None:
        return  # nothing to do

    # Does the operator telegram account have a real bot token? A binding that
    # references a token-less account is inert and poisons config load, so drop it.
    op_acct = (
        ((cfg.get("channels") or {}).get("telegram") or {}).get("accounts") or {}
    ).get("operator") or {}
    operator_has_token = bool(op_acct.get("botToken"))

    normalized, seen, dropped_inert, reshaped = [], set(), 0, 0
    for b in raw:
        route = _to_route(b)
        if route is None:
            continue
        m = route["match"]
        is_operator_tg = m.get("channel") == "telegram" and m.get("accountId") == "operator"
        if is_operator_tg and not operator_has_token:
            dropped_inert += 1
            continue
        key = _binding_key(route)
        if key in seen:
            continue
        seen.add(key)
        # was the source flat (no proper match)? count a reshape for reporting
        if not isinstance(b, dict) or not isinstance(b.get("match"), dict):
            reshaped += 1
        normalized.append(route)

    if dropped_inert:
        notes.append(
            "bindings: dropped %d inert token-less operator route(s)" % dropped_inert
        )
    if reshaped:
        notes.append("bindings: reshaped %d legacy flat entry(ies) to match-shape" % reshaped)

    if normalized:
        cfg["bindings"] = normalized
    elif had_top:
        cfg["bindings"] = []  # one existed; leave a clean empty array
    # else: never existed at the top level and nothing to keep — leave it unset


def is_bad_shape(cfg):
    """True if the config still carries any of the three invalid shapes."""
    entries = (cfg.get("plugins") or {}).get("entries")
    if isinstance(entries, dict):
        for entry in entries.values():
            if isinstance(entry, dict) and any(
                k not in ENTRY_TOP_KEYS for k in entry
            ):
                return True
    tg = (cfg.get("channels") or {}).get("telegram")
    if isinstance(tg, dict):
        if "helpChatId" in tg:
            return True
        for acct in (tg.get("accounts") or {}).values():
            if isinstance(acct, dict) and "helpChatId" in acct:
                return True
    if isinstance(cfg.get("channels"), dict) and "bindings" in cfg["channels"]:
        return True
    top = cfg.get("bindings")
    if isinstance(top, list):
        for b in top:
            if isinstance(b, dict) and not isinstance(b.get("match"), dict):
                return True  # flat / shapeless entry
    return False


def main(argv):
    mode = "heal"
    args = [a for a in argv[1:]]
    if args and args[0] in ("--check", "--dry-run"):
        mode = "check" if args[0] == "--check" else "dry-run"
        args = args[1:]
    if len(args) != 1:
        sys.stderr.write(
            "usage: heal-config-shapes.py [--check|--dry-run] <openclaw.json>\n"
        )
        return 2
    path = args[0]
    try:
        with open(path) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        sys.stderr.write("heal-config-shapes: config not found: %s\n" % path)
        return 2
    except (ValueError, OSError) as e:
        sys.stderr.write("heal-config-shapes: cannot read %s: %s\n" % (path, e))
        return 2

    if mode == "check":
        bad = is_bad_shape(cfg)
        if bad:
            sys.stderr.write("heal-config-shapes: BAD SHAPE present in %s\n" % path)
            return 3
        print("heal-config-shapes: clean (%s)" % path)
        return 0

    before = json.dumps(cfg, sort_keys=True)
    notes = []
    heal_plugin_entries(cfg, notes)
    heal_help_chat_id(cfg, notes)
    heal_bindings(cfg, notes)
    after = json.dumps(cfg, sort_keys=True)

    if before == after:
        print("heal-config-shapes: no change (%s)" % path)
        return 0

    if mode == "dry-run":
        print("heal-config-shapes: WOULD heal %s" % path)
        for n in notes:
            print("  - " + n)
        return 0

    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    print("heal-config-shapes: healed %s" % path)
    for n in notes:
        print("  - " + n)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
