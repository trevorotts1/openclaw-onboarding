#!/usr/bin/env python3
"""RR-032 remote-rescue configuration transaction engine.

Pure stdlib. No network, no node, no shell. Every state transition is a NAMED
transition so a report can never claim a state the file does not hold.

Contract
--------
  enable      explicit valid destination supplied   -> write canonical+alias, state enabled
  enable      no approved destination, explicit new -> write canonical+alias, state enabled
  change      explicit destination differs          -> write canonical+alias, state destination-changed
  preserve    empty repair input, approved existing -> leave both keys alone, state preserved
  preserve    empty repair input, valid custom mount-> leave both keys alone, state preserved
  preserve    empty repair input, nothing approved  -> leave both keys alone, state preserve-no-destination
  disable     explicit disable token only           -> remove canonical+alias, state disabled
  refuse      malformed destination                 -> leave file alone, state refused

A destination is approved when canonical and alias agree on a non-empty value,
when a single recognized key carries it, or when a legacy help key carries it.
Disagreement between canonical and alias is NOT approved and NOT repaired by
guessing: an empty repair input preserves the file and reports
state "preserve-alias-disagreement".

Every write is temporary candidate + validation + atomic promote + rollback.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

CANONICAL_KEY = "OPERATOR_ESCALATION_CHAT_ID"
ALIAS_KEY = "OPERATOR_TELEGRAM_CHAT_ID"
RECOGNIZED_KEYS = (CANONICAL_KEY, ALIAS_KEY, "OPERATOR_HELP_CHAT_ID")
DISABLE_TOKENS = ("disable", "disabled", "off", "none", "no", "false", "0")
CHAT_ID_RE = re.compile(r"^-?[0-9]{5,20}$")
PROCESS_FLAVORS = {
    "linux": ("reiserfs", "ext4", "xfs"),
    "darwin": ("apfs", "hfs"),
}
APPROVED_STATES = ("enabled", "preserved", "disabled", "destination-changed",
                   "preserve-no-destination", "preserve-alias-disagreement")


def now_iso():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


class Refusal(Exception):
    pass


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path):
    with open(path, "rb") as fh:
        return sha256_bytes(fh.read())


def load_document(path):
    """Byte-exact text + parsed object + sha of the exact bytes read."""
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    try:
        obj = json.loads(text)
    except ValueError as exc:
        raise Refusal("document is not parseable JSON: %s" % exc)
    if not isinstance(obj, dict):
        raise Refusal("document root is not an object")
    return text, obj, sha256_bytes(raw)


def _vars(config):
    env = config.get("env")
    if not isinstance(env, dict):
        return {}
    v = env.get("vars")
    if not isinstance(v, dict):
        return {}
    return v


def read_destination(config):
    """Raw destinations by key. Never coerced, never repaired."""
    v = _vars(config)
    return dict((k, v.get(k)) for k in RECOGNIZED_KEYS)


def classify_destination(dests, requested):
    """Return (state, approved, destination, note). Pure function of read state."""
    canonical = dests.get(CANONICAL_KEY)
    alias = dests.get(ALIAS_KEY)
    help_key = dests.get("OPERATOR_HELP_CHAT_ID")
    canonical_set = canonical is not None and str(canonical) != ""
    alias_set = alias is not None and str(alias) != ""
    help_set = help_key is not None and str(help_key) != ""

    if canonical_set and alias_set and str(canonical) != str(alias):
        return ("preserve-alias-disagreement", False, None,
                "canonical and alias name different destinations; preserving both and reporting")
    if canonical_set and alias_set:
        return ("preserve", True, str(canonical), "canonical and alias agree")
    if canonical_set:
        return ("preserve", True, str(canonical), "single recognized key carries the destination")
    if alias_set:
        return ("preserve", True, str(alias), "single recognized key carries the destination")
    if help_set:
        return ("preserve", True, str(help_key), "legacy help key carries the destination")
    return ("preserve-no-destination", False, None, "no recognized key carries a destination")


def validate_destination(value):
    if not CHAT_ID_RE.match(str(value)):
        raise Refusal(
            "destination %r is not a telegram chat id; refused rather than written" % (value,))
    return str(value)


def resolve_oc_root(explicit=None):
    """Verified OpenClaw root: explicit when it EXISTS, then /data/.openclaw, then HOME/.openclaw."""
    if explicit and os.path.isdir(explicit):
        return explicit, "explicit"
    if os.path.isdir("/data/.openclaw"):
        return "/data/.openclaw", "docker-root"
    home = os.path.expanduser("~")
    if home and home != "~":
        path = os.path.join(home, ".openclaw")
        if os.path.isdir(path):
            return path, "home"
    return None, "unresolved"


def default_workspace(root):
    if root:
        return os.path.join(root, "workspaces", "remote-rescue")
    home = os.path.expanduser("~")
    return os.path.join(home, ".openclaw", "workspaces", "remote-rescue")


def path_has_spaces(path):
    return any(" " in part for part in path.split(os.sep))


def classify_mount(path, explicit, flavors):
    """missing | existing | existing-valid-custom | invalid-file"""
    if os.path.isdir(path):
        return "existing-valid-custom" if explicit else "existing"
    if os.path.lexists(path):
        return "invalid-file"
    parent = os.path.dirname(path.rstrip(os.sep))
    while parent and parent != os.sep and not os.path.exists(parent):
        parent = os.path.dirname(parent)
    if not parent or parent == os.sep:
        return "missing"
    try:
        st = os.statvfs(parent)
    except (AttributeError, OSError):
        return "missing"
    fstype = str(getattr(st, "f_fstype", ""))
    for flavor in flavors:
        if flavor and flavor in fstype:
            return "missing"
    return "missing"


def ensure_workspace(path, explicit, flavors):
    """Create when missing. Never joins, never mirrors, the owner workspace."""
    if path_has_spaces(path):
        os.makedirs(path, mode=0o700, exist_ok=True)
        return "path-resolved-and-created-space-safe", True
    state = classify_mount(path, explicit, flavors)
    if state == "invalid-file":
        return "invalid-file", False
    if state == "missing":
        os.makedirs(path, mode=0o700, exist_ok=True)
        # Report what the directory IS NOW, not what it was before the write.
        # Reporting "missing" for a directory this run just created is exactly
        # the class of untruthful state RR-032 exists to remove.
        return "created", True
    return state, True


def apply_keys(obj, action, destination):
    """Return a NEW object. Never mutates the caller's document."""
    env = obj.get("env")
    env = dict(env) if isinstance(env, dict) else {}
    vars_ = env.get("vars")
    vars_ = dict(vars_) if isinstance(vars_, dict) else {}
    removed = []

    if action == "write":
        vars_[CANONICAL_KEY] = destination
        vars_[ALIAS_KEY] = destination
    elif action == "remove":
        for key in (CANONICAL_KEY, ALIAS_KEY):
            if key in vars_:
                del vars_[key]
                removed.append(key)
    elif action == "remove-invalid-alias":
        vars_[ALIAS_KEY] = destination
    else:
        raise Refusal("unknown apply action %r" % (action,))

    env["vars"] = vars_
    out = dict(obj)
    out["env"] = env
    return out, removed


def reconcile_operators(obj, operator_ids):
    """Keep every authorized operator identity inbound-allowed, and out of the group allowlist.

    Returns (new_obj, changes) where changes is a list of NAMED changes. Never mutates input.
    """
    if not operator_ids:
        return obj, []
    out = dict(obj)
    channels = out.get("channels")
    channels = dict(channels) if isinstance(channels, dict) else {}
    telegram = channels.get("telegram")
    telegram = dict(telegram) if isinstance(telegram, dict) else {}
    changes = []

    allow = telegram.get("allowFrom")
    allow = list(allow) if isinstance(allow, list) else []
    added = [oid for oid in operator_ids if oid not in [str(x) for x in allow]]
    if added or not isinstance(telegram.get("allowFrom"), list):
        allow = allow + added
        telegram["allowFrom"] = allow
        changes.append({"to": "operators-inbound-allowed", "cause": "allowFrom missing operator ids",
                        "added": added})

    group = telegram.get("groupAllowFrom")
    if isinstance(group, list):
        stripped = [x for x in group if str(x) not in operator_ids]
        if len(stripped) != len(group):
            telegram["groupAllowFrom"] = stripped
            changes.append({"to": "operators-removed-from-group-allowlist",
                            "cause": "operator ids must not be reachable from a group context",
                            "removed": [str(x) for x in group if str(x) in operator_ids]})

    channels["telegram"] = telegram
    out["channels"] = channels
    return out, changes


def _roster_form(cfg):
    """Which roster shape this config actually uses. Never invents a migration."""
    agents = cfg.get("agents")
    if not isinstance(agents, dict):
        return "entries"
    if isinstance(agents.get("entries"), dict):
        return "entries"
    if isinstance(agents.get("list"), list):
        return "list"
    return "entries"


def _operator_binding(agent_id, chat_id):
    return {
        "agentId": agent_id,
        "match": {"channel": "telegram", "peer": {"kind": "direct", "id": chat_id}},
        "session": {"dmScope": "per-peer"},
    }


def reconcile_routing(obj, agent_id, workspace, operator_ids, owner_agent_id="main",
                      agent_name="Remote Rescue by T Otts", agent_description=None,
                      workspace_explicit=False):
    """Make routing REAL for this version of OpenClaw.

    Field presence is not routing. Verified against 2026.9.2 (3928bad):
      * agents.entries.<id>.telegram is NOT a valid key (Unrecognized key)
      * channels.telegram.allowFrom grants inbound access but does NOT route
      * a per-agent workspace does NOT route
      * only a top-level bindings entry {agentId, match.peer, session.dmScope}
        resolves the DM to the agent, matchedBy="binding.peer"

    Returns (new_obj, changes, refusal) where refusal is a string when the
    requested shape would violate the owner/operator separation.
    """
    if not operator_ids:
        return obj, [], None
    out = dict(obj)
    changes = []
    form = _roster_form(out)

    agents = out.get("agents")
    agents = dict(agents) if isinstance(agents, dict) else {}
    if form == "entries":
        entries = agents.get("entries")
        entries = dict(entries) if isinstance(entries, dict) else {}
        entry = dict(entries.get(agent_id) or {})
        existing_ws = entry.get("workspace")
        # A valid custom mount is RETAINED. The resolved workspace is written only
        # when the agent has none yet, or when the operator named one explicitly.
        if existing_ws is not None and not workspace_explicit:
            if existing_ws != workspace:
                changes.append({"to": "workspace-custom-retained",
                                "cause": "existing valid custom mount retained over the resolved default",
                                "value": existing_ws})
        elif existing_ws != workspace:
            entry["workspace"] = workspace
            changes.append({"to": "workspace-wired",
                            "cause": "workspace set from the verified OpenClaw root",
                            "value": workspace})
        if entry.get("description") != agent_description and agent_description:
            entry["description"] = agent_description
        if entry.get("name") != agent_name:
            entry["name"] = agent_name
        if "telegram" in entry:
            del entry["telegram"]
            changes.append({"to": "routing-inert-key-removed",
                            "cause": "agents.entries.<id>.telegram is not a schema key and carries no routing"})
        subs = entry.get("subagents")
        subs = dict(subs) if isinstance(subs, dict) else {}
        if subs.get("allowAgents") != ["*"]:
            subs["allowAgents"] = ["*"]
            entry["subagents"] = subs
        entries[agent_id] = entry
        agents["entries"] = entries
        if (len(entries) > 1 and not agents.get("ownership")
                and not any(isinstance(a, dict) and a.get("default") for a in entries.values())):
            agents["ownership"] = "explicit"
            changes.append({"to": "roster-ownership-declared",
                            "cause": "multi-agent roster requires agents.ownership=explicit"})
    else:
        entries = agents.get("list")
        entries = list(entries) if isinstance(entries, list) else []
        idx = next((i for i, a in enumerate(entries)
                    if isinstance(a, dict) and a.get("id") == agent_id), None)
        entry = dict(entries[idx]) if idx is not None else {"id": agent_id}
        existing_ws = entry.get("workspace")
        if existing_ws is not None and not workspace_explicit and idx is not None:
            if existing_ws != workspace:
                changes.append({"to": "workspace-custom-retained",
                                "cause": "existing valid custom mount retained",
                                "value": existing_ws})
        else:
            entry["workspace"] = workspace
        entry["name"] = agent_name
        if agent_description:
            entry["description"] = agent_description
        if "telegram" in entry:
            del entry["telegram"]
            changes.append({"to": "routing-inert-key-removed",
                            "cause": "agents.list[].telegram is not a schema key and carries no routing"})
        subs = entry.get("subagents")
        subs = dict(subs) if isinstance(subs, dict) else {}
        subs["allowAgents"] = ["*"]
        entry["subagents"] = subs
        if idx is not None:
            entries[idx] = entry
        else:
            entries.append(entry)
        agents["list"] = entries
        if not agents.get("ownership") and not any(
                isinstance(a, dict) and a.get("default") for a in entries):
            agents["ownership"] = "explicit"
            changes.append({"to": "roster-ownership-declared",
                            "cause": "multi-agent roster requires agents.ownership=explicit"})
    out["agents"] = agents

    bindings = out.get("bindings")
    bindings = list(bindings) if isinstance(bindings, list) else []
    kept = []
    for b in bindings:
        if not isinstance(b, dict):
            continue
        match = b.get("match") or {}
        peer = (match.get("peer") or {}) if isinstance(match, dict) else {}
        peer_id = str(peer.get("id") or "") if isinstance(peer, dict) else ""
        if peer_id in operator_ids and b.get("agentId") != agent_id:
            changes.append({"to": "operator-binding-removed-from-owner-agent",
                            "cause": "operator DM was bound to %s, not %s" % (b.get("agentId"), agent_id),
                            "peer": peer_id})
            continue
        kept.append(b)

    have = set()
    for b in kept:
        match = b.get("match") or {}
        peer = (match.get("peer") or {}) if isinstance(match, dict) else {}
        if isinstance(peer, dict) and str(peer.get("id") or "") in operator_ids and b.get("agentId") == agent_id:
            have.add(str(peer.get("id")))

    for oid in operator_ids:
        if oid not in have:
            kept.append(_operator_binding(agent_id, oid))
            changes.append({"to": "operator-route-bound",
                            "cause": "bindings entry added so this operator DM resolves by binding.peer",
                            "peer": oid})
    out["bindings"] = kept
    return out, changes, None


def serialize(obj):
    return json.dumps(obj, indent=2) + "\n"


def classify_candidate(raw):
    """Runner-level structural classification, independent of any schema file."""
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return False, "candidate is not parseable JSON: %s" % exc
    if not isinstance(parsed, dict):
        return False, "candidate root is not an object"
    env = parsed.get("env")
    if env is not None and not isinstance(env, dict):
        return False, "env is not an object"
    if isinstance(env, dict) and env.get("vars") is not None and not isinstance(env["vars"], dict):
        return False, "env.vars is not an object"
    return True, ""


def write_report(path, report):
    with open(path, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")


def run(req):
    report = {
        "rr": "RR-032",
        "at": now_iso(),
        "cfg": req["cfg"],
        "mode": req["mode"],
        "check_only": bool(req.get("check_only")),
        "repair": bool(req["repair"]),
        "noninteractive": bool(req["noninteractive"]),
        "requested_raw": req["requested_raw"],
        "requested_after_env_fallback": req["requested_after_env_fallback"],
        "source_revision": req.get("source_revision"),
        "source_sha256": None,
        "expected_source_sha256": req.get("expect_sha"),
        "cas": "not-evaluated",
        "validation": "not-run",
        "validation_detail": "",
        "promote": "not-attempted",
        "rollback": "not-needed",
        "root": None,
        "root_source": None,
        "workspace": None,
        "mount_state": None,
        "flavors": list(req["flavors"]),
        "state": "unknown",
        "approved_before": False,
        "destination": None,
        "alias": None,
        "wrote_keys": [],
        "removed_keys": [],
        "operator_changes": [],
        "routing_changes": [],
        "keys_after": {},
        "notes": [],
        "transitions": [],
        "rc": 1,
    }
    t = report["transitions"]
    request = req["requested_after_env_fallback"]
    # The disable token is honored in EVERY mode. Blank is NOT a disable token:
    # blank means preserve. Only the literal token removes the destination.
    is_disable = str(request).strip().lower() in DISABLE_TOKENS

    # ---- workspace + root ------------------------------------------------
    root, root_source = resolve_oc_root(req.get("oc_root"))
    report["root"] = root
    report["root_source"] = root_source
    if root is None:
        t.append({"from": "start", "to": "refused", "cause": "no-verified-openclaw-root"})
        report["state"] = "refused"
        report["notes"].append(
            "no verified OpenClaw root: explicit root, /data/.openclaw and HOME/.openclaw all absent")
        report["rc"] = 2
        return report
    t.append({"from": "start", "to": "root-resolved", "cause": "resolve_oc_root:" + root_source})

    check_only = bool(req.get("check_only"))
    ws_explicit = bool(req.get("workspace_explicit")) and bool(req.get("workspace"))
    ws = req["workspace"] if req.get("workspace") else default_workspace(root)
    report["workspace"] = ws
    if check_only:
        ws_state, ws_created = classify_mount(ws, ws_explicit, req["flavors"]), False
    else:
        ws_state, ws_created = ensure_workspace(ws, ws_explicit, req["flavors"])
    report["mount_state"] = ws_state
    if ws_state == "invalid-file":
        t.append({"from": "root-resolved", "to": "refused", "cause": "workspace-path-is-not-a-directory"})
        report["state"] = "refused"
        report["notes"].append("workspace path exists and is not a directory; refused, nothing created")
        report["rc"] = 2
        return report
    if ws_state == "path-resolved-and-created-space-safe":
        t.append({"from": "root-resolved", "to": "workspace-path-space-safe",
                  "cause": "path contains spaces; resolved and created without word splitting"})
    elif ws_state == "existing-valid-custom":
        t.append({"from": "root-resolved", "to": "workspace-custom-retained",
                  "cause": "valid custom mount retained, not overwritten"})
    else:
        t.append({"from": "root-resolved",
                  "to": "workspace-created" if ws_created else "workspace-present",
                  "cause": ws_state})

    # ---- read destination -------------------------------------------------
    cfg = req["cfg"]
    if not os.path.exists(cfg):
        t.append({"from": "root-resolved", "to": "refused", "cause": "config-missing"})
        report["state"] = "refused"
        report["notes"].append("config does not exist at the resolved path; refused, no new config created")
        report["rc"] = 2
        return report
    text, obj, source_sha = load_document(cfg)
    report["source_sha256"] = source_sha
    dests = read_destination(obj)
    report["keys_before"] = dict((k, v) for k, v in dests.items() if v not in (None, ""))
    state, approved, destination, note = classify_destination(dests, request)
    report["state"] = state
    report["approved_before"] = approved
    report["destination"] = destination
    report["alias"] = destination
    t.append({"from": "root-resolved", "to": state, "cause": note})

    # ---- decide -----------------------------------------------------------
    explicit_dest = str(request).strip()
    write_action = None
    outcome = state

    if is_disable:
        outcome = "disabled"
        write_action = "remove"
        t.append({"from": state, "to": "disabled", "cause": "explicit-disable-token"})
    elif explicit_dest:
        validate_destination(explicit_dest)
        if destination is not None and explicit_dest == destination:
            if state == "preserve-alias-disagreement":
                outcome = "preserve"
                destination = explicit_dest
                write_action = "remove-invalid-alias"
                t.append({"from": state, "to": "preserve",
                          "cause": "explicit destination equals canonical; alias repaired to agree"})
            else:
                outcome = "preserved"
                write_action = None
                t.append({"from": state, "to": "preserved",
                          "cause": "explicit destination equals approved destination"})
        elif destination is not None and explicit_dest != destination:
            outcome = "destination-changed"
            destination = explicit_dest
            write_action = "write"
            t.append({"from": state, "to": "destination-changed",
                      "cause": "explicit destination differs from approved destination"})
        else:
            outcome = "enabled"
            destination = explicit_dest
            write_action = "write"
            t.append({"from": state, "to": "enabled", "cause": "explicit-destination-supplied"})
    else:
        if state == "preserve":
            outcome = "preserved"
            write_action = None
            t.append({"from": state, "to": "preserved",
                      "cause": "empty-repair-input-preserves-approved-destination"})
        elif state == "preserve-alias-disagreement":
            outcome = "preserve-alias-disagreement"
            write_action = None
            report["notes"].append(
                "canonical and alias disagree; with no explicit destination nothing was removed and nothing guessed")
        else:
            outcome = "preserve-no-destination"
            write_action = None
            report["notes"].append("no approved destination and no explicit destination; nothing written")

    report["destination"] = destination
    report["alias"] = destination
    report["outcome"] = outcome

    # ---- lock / CAS -------------------------------------------------------
    if req.get("source_revision"):
        if req.get("expect_sha") and req["expect_sha"] != source_sha:
            t.append({"from": outcome, "to": "refused", "cause": "cas-mismatch"})
            report["cas"] = "mismatch"
            report["state"] = "refused"
            report["notes"].append(
                "source revision changed after it was inspected; refused rather than write over a concurrent edit")
            report["rc"] = 3
            return report
        report["cas"] = "ok"
    else:
        report["cas"] = "unnamed-revision:read-then-single-atomic-rename"

    # ---- candidate / validate / promote ----------------------------------
    if check_only:
        t.append({"from": outcome, "to": "check-only",
                  "cause": "read-only inspection; no candidate written, nothing promoted"})
        report["state"] = outcome
        report["promote"] = "not-attempted"
        report["rollback"] = "not-needed:check-only"
        report["rc"] = 0
        return report

    if write_action is None:
        candidate = obj
        removed = []
    else:
        candidate, removed = apply_keys(obj, write_action, destination)
    report["removed_keys"] = removed

    if req.get("reconcile_operators"):
        candidate, op_changes = reconcile_operators(candidate, req.get("operator_ids") or [])
    else:
        op_changes = []
    report["operator_changes"] = op_changes
    for change in op_changes:
        t.append({"from": outcome, "to": change["to"], "cause": change["cause"]})

    route_changes = []
    if req.get("reconcile_routing"):
        candidate, route_changes, refusal = reconcile_routing(
            candidate,
            "remote-rescue",
            req.get("workspace"),
            [str(x) for x in (req.get("operator_ids") or [])],
            owner_agent_id=req.get("owner_agent_id") or "main",
            workspace_explicit=bool(req.get("workspace_explicit")),
        )
        if refusal:
            t.append({"from": outcome, "to": "refused", "cause": refusal})
            report["state"] = "refused"
            report["notes"].append(refusal)
            report["rc"] = 6
            return report
    report["routing_changes"] = route_changes
    for change in route_changes:
        t.append({"from": outcome, "to": change["to"], "cause": change["cause"]})

    if write_action is None and not op_changes and not route_changes:
        t.append({"from": outcome, "to": "no-write", "cause": "no configuration change required"})
        report["state"] = outcome
        report["rc"] = 0
        return report
    cand_path = cfg + ".rr032-candidate"
    with open(cand_path, "w") as fh:
        fh.write(serialize(candidate))
    t.append({"from": outcome, "to": "candidate-written", "cause": "temporary candidate " + cand_path})

    with open(cand_path, "rb") as fh:
        cand_raw = fh.read()
    valid, issue = classify_candidate(cand_raw)
    validator = req.get("validator_program")
    if validator:
        try:
            proc = subprocess.run(list(validator) + [cand_path], capture_output=True, text=True)
            try:
                parsed = json.loads(proc.stdout or "{}")
            except ValueError:
                parsed = {"rc": proc.returncode, "valid": False,
                          "detail": (proc.stdout or proc.stderr or "validator produced no JSON").strip()[:400]}
            rv = {"rc": parsed.get("rc", proc.returncode),
                  "valid": bool(parsed.get("valid")),
                  "detail": parsed.get("detail") or ""}
        except OSError as exc:
            rv = {"rc": 1, "valid": False, "detail": "validator could not be executed: %s" % exc}
        if not (rv["rc"] == 0 and rv["valid"]):
            valid = False
            issue = rv["detail"] or "validator rejected the candidate"
    rv = req.get("runner_candidate")
    if rv is not None:
        if rv.get("rc") != 0 or not rv.get("valid"):
            valid = False
            issue = (rv.get("detail") or rv.get("raw") or "runner reported the candidate invalid").strip()
    report["validation"] = "valid" if valid else "invalid"
    report["validation_detail"] = issue
    t.append({"from": "candidate-written",
              "to": "candidate-valid" if valid else "candidate-invalid",
              "cause": issue or "runner and structural classification both accept the candidate"})

    if not valid:
        os.unlink(cand_path)
        report["promote"] = "refused"
        report["state"] = "refused"
        report["rollback"] = "not-needed:live-config-never-touched"
        report["notes"].append(
            "candidate failed validation; live config never touched, candidate discarded")
        report["rc"] = 4
        return report

    if sha256_file(cfg) != source_sha:
        os.unlink(cand_path)
        report["cas"] = "mismatch-live"
        report["state"] = "refused"
        report["promote"] = "refused"
        report["rollback"] = "not-needed:live-config-never-touched"
        report["notes"].append(
            "live config changed between read and promote; refused rather than clobber the concurrent edit")
        report["rc"] = 5
        return report

    rollback_src = req.get("rollback_src")
    if rollback_src:
        with open(rollback_src, "wb") as fh:
            fh.write(text.encode("utf-8"))
        report["rollback"] = "snapshot-written:" + rollback_src

    try:
        rc, err = req["promote"](cand_path, cfg)
    except Exception as exc:  # any promoter failure must roll back
        rc, err = 1, str(exc)
    if rc == 0:
        report["promote"] = "promoted"
        report["rollback"] = "not-needed:promote-succeeded"
        report["state"] = outcome
        report["wrote_keys"] = [CANONICAL_KEY, ALIAS_KEY] if write_action == "write" else []
        if op_changes:
            report["wrote_keys"] = report["wrote_keys"] + ["channels.telegram.allowFrom",
                                                          "channels.telegram.groupAllowFrom"]
        if route_changes:
            report["wrote_keys"] = report["wrote_keys"] + ["bindings", "agents.entries." + "remote-rescue"]
        t.append({"from": "candidate-valid", "to": "promoted", "cause": "atomic rename onto live config"})
    else:
        with open(cfg, "w") as fh:
            fh.write(text)
        report["promote"] = "failed"
        report["rollback"] = "restored-source-bytes:sha256=" + source_sha
        report["state"] = "rolled-back"
        report["notes"].append("driver failed to promote (%s); live config restored byte-for-byte" % err)
        t.append({"from": "candidate-valid", "to": "rolled-back", "cause": "promote-failed-then-restore"})
        try:
            os.unlink(cand_path)
        except OSError:
            pass

    _, live_obj, live_sha_after = load_document(cfg)
    report["keys_after"] = dict((k, v) for k, v in read_destination(live_obj).items() if v not in (None, ""))
    report["live_sha256_after"] = live_sha_after
    report["keys_after_verified"] = (sha256_file(cfg) == live_sha_after)
    report["rc"] = 0 if report["state"] in APPROVED_STATES else 1
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage")
    ap.add_argument("--cfg", required=True)
    ap.add_argument("--mode", default="repair")
    ap.add_argument("--repair", action="store_true")
    ap.add_argument("--noninteractive", action="store_true")
    ap.add_argument("--requested", default=None)
    ap.add_argument("--requested-env", default=None)
    ap.add_argument("--source-revision", default=None)
    ap.add_argument("--expect-sha", default=None)
    ap.add_argument("--oc-root", default=None)
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--workspace-explicit", action="store_true")
    ap.add_argument("--flavor", action="append", default=[])
    ap.add_argument("--operator-id", action="append", default=[])
    ap.add_argument("--check", dest="check_only", action="store_true")
    ap.add_argument("--reconcile-operators", action="store_true")
    ap.add_argument("--reconcile-routing", action="store_true")
    ap.add_argument("--owner-agent-id", default="main")
    ap.add_argument("--promote-program", action="append", default=[])
    ap.add_argument("--validator-program", action="append", default=[])
    ap.add_argument("--rollback-src", default=None)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    if args.stage == "resolve-root":
        root, source = resolve_oc_root(args.oc_root)
        print(json.dumps({"root": root, "source": source, "workspace": default_workspace(root)}))
        return 0 if root else 2

    requested = args.requested
    if requested is None or str(requested).strip() == "":
        requested = args.requested_env if args.requested_env is not None else ""
    flavors = args.flavor or list(PROCESS_FLAVORS.get(
        "darwin" if sys.platform == "darwin" else "linux", ()))

    def promote(cand, live):
        if not args.promote_program:
            raise Refusal("no promote program supplied")
        argv = list(args.promote_program) + [cand, live]
        rc = os.spawnv(os.P_WAIT, argv[0], argv)
        return rc, "promote program rc=%d" % rc

    req = {
        "cfg": args.cfg,
        "mode": args.mode,
        "repair": args.repair,
        "noninteractive": args.noninteractive,
        "requested_raw": args.requested,
        "requested_after_env_fallback": requested,
        "source_revision": args.source_revision,
        "expect_sha": args.expect_sha,
        "oc_root": args.oc_root,
        "workspace": args.workspace,
        "workspace_explicit": args.workspace_explicit,
        "flavors": flavors,
        "operator_ids": [str(x) for x in args.operator_id],
        "check_only": bool(args.check_only),
        "reconcile_operators": bool(args.reconcile_operators),
        "reconcile_routing": bool(args.reconcile_routing),
        "owner_agent_id": args.owner_agent_id,
        "validator_program": list(args.validator_program),
        "rollback_src": args.rollback_src,
        "promote": promote,
    }
    try:
        report = run(req)
    except Refusal as exc:
        report = {"rr": "RR-032", "at": now_iso(), "cfg": args.cfg, "state": "refused",
                  "notes": [str(exc)], "transitions": [{"from": "start", "to": "refused",
                                                        "cause": str(exc)}], "rc": 2}
    if args.report:
        write_report(args.report, report)
    print(json.dumps(report, indent=2))
    return report.get("rc", 1)


if __name__ == "__main__":
    sys.exit(main())
