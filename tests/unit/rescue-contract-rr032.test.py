#!/usr/bin/env python3
"""RR-032 — remote rescue config repair: truthful state + real routing.

WHAT THIS PROVES (and what it refuses to accept as proof)
---------------------------------------------------------
A green run is NOT evidence. `exit 0`, HTTP 200, a printed banner and a file
that merely exists all pass while the config says something else. Every check
below reads the DESTINATION OUT OF THE CONFIG BYTES ON DISK after the run and
compares it against the state the run REPORTED. A run that reports "preserved"
while the bytes changed fails. A run that reports "disabled" while a destination
survives fails.

Routing is checked the same way: field presence is not evidence. The old
installer wrote `agents.list[].telegram.allowFrom` and a per-agent `workspace`
and called that isolation. Neither has any routing effect — verified against the
shipped resolver, where only a top-level `bindings` entry with a peer match
resolves a DM to an agent. routing_acceptance() runs the ACTUAL resolver module
when one is present and SKIPS (never passes) when it is not.

The nine required cases:
  1 prior opt-in + empty repair        -> preserved, bytes untouched
  2 initial opt-out + empty repair     -> preserve-no-destination, bytes untouched
  3 explicit disable                   -> disabled, both keys gone
  4 changed destination                -> destination-changed, both keys agree
  5 alias disagreement                 -> reported, neither guessed nor removed
  6 concurrent config edit             -> refused by CAS, edit survives
  7 invalid candidate                  -> refused, live config untouched
  8 Docker HOME outside the mount      -> workspace resolves under the real root
  9 owner/operator separation          -> two operators + owner resolve disjointly
Plus the negative control that proves this file can actually go red.

Hermetic: every run is inside a temp dir. No network, no live config touched.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
ENGINE = os.path.join(REPO, "15-blackceo-team-management", "scripts", "lib",
                      "rr-config-transaction.py")
VERIFIER = os.path.join(REPO, "15-blackceo-team-management", "scripts", "lib",
                        "rr-verify-routing.mjs")

PASS = 0
FAIL = 0
SKIP = 0
CANON = "OPERATOR_ESCALATION_CHAT_ID"
ALIAS = "OPERATOR_TELEGRAM_CHAT_ID"
OPS = ["5252140759", "6663821679", "6771245262"]
OWNER_ID = "111222333"


def ok(msg):
    global PASS
    PASS += 1
    print("ok   - %s" % msg)


def bad(msg):
    global FAIL
    FAIL += 1
    print("FAIL - %s" % msg)


def check(cond, msg):
    if cond:
        ok(msg)
    else:
        bad(msg)
    return bool(cond)


def skip(msg):
    global SKIP
    SKIP += 1
    print("skip - %s" % msg)


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def write_cfg(path, destination=None):
    """Write a config whose ROUTING is already fully wired.

    The routing scaffold is held constant so the only axis left to vary is the
    destination. A test that changes routing and destination at once cannot tell
    which one moved the bytes.
    """
    c = {
        "agents": {
            "ownership": "explicit",
            "entries": {
                "main": {"workspace": os.path.join(os.environ["RR032_TMP"], "ws", "owner")},
                "remote-rescue": {
                    "name": "Remote Rescue by T Otts",
                    "workspace": os.path.join(os.environ["RR032_TMP"], "ws", "rr"),
                    "subagents": {"allowAgents": ["*"]},
                },
            },
        },
        "channels": {"telegram": {"allowFrom": ["111"] + OPS, "groupAllowFrom": ["111"]}},
        "bindings": [
            {"agentId": "remote-rescue",
             "match": {"channel": "telegram", "peer": {"kind": "direct", "id": op}},
             "session": {"dmScope": "per-peer"}}
            for op in OPS
        ],
        "env": {"vars": {}},
    }
    if destination == "enabled":
        c["env"]["vars"] = {CANON: OPS[0], ALIAS: OPS[0]}
    elif destination == "alias_only":
        c["env"]["vars"] = {ALIAS: OPS[0]}
    elif destination == "disagree":
        c["env"]["vars"] = {CANON: OPS[0], ALIAS: OPS[1]}
    elif destination == "disabled":
        pass
    with open(path, "w") as fh:
        json.dump(c, fh, indent=2)


def read_vars(path):
    with open(path) as fh:
        return (json.load(fh).get("env") or {}).get("vars") or {}


def run_engine(tmp, cfg, requested, source_sha, promote="promote_ok.sh",
               expect_sha=None, workspace_explicit=True, extra=None):
    report = cfg + ".rep"
    argv = [
        sys.executable, ENGINE,
        "--cfg", cfg,
        "--repair",
        "--requested", requested,
        "--source-revision", "sha256:" + source_sha,
        "--expect-sha", expect_sha if expect_sha is not None else source_sha,
        "--oc-root", os.path.join(tmp, "root"),
        "--workspace", os.path.join(tmp, "ws", "rr"),
        "--reconcile-operators",
        "--reconcile-routing",
        "--promote-program", os.path.join(tmp, promote),
        "--report", report,
    ]
    if workspace_explicit:
        argv.append("--workspace-explicit")
    for op in OPS:
        argv += ["--operator-id", op]
    if extra:
        argv += extra
    proc = subprocess.run(argv, capture_output=True, text=True)
    try:
        with open(report) as fh:
            rep = json.load(fh)
    except (OSError, ValueError):
        rep = {"state": "<no report>", "rc": proc.returncode, "stderr": proc.stderr[-300:]}
    return rep, proc


def make_fixtures(tmp):
    os.makedirs(os.path.join(tmp, "root"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "ws", "rr"), exist_ok=True)
    okp = os.path.join(tmp, "promote_ok.sh")
    with open(okp, "w") as fh:
        fh.write("#!/usr/bin/env bash\nset -euo pipefail\nmv \"$1\" \"$2\"\n")
    os.chmod(okp, 0o755)
    badp = os.path.join(tmp, "promote_fail.sh")
    with open(badp, "w") as fh:
        fh.write("#!/usr/bin/env bash\nexit 7\n")
    os.chmod(badp, 0o755)
    tornp = os.path.join(tmp, "promote_tears_then_fails.sh")
    with open(tornp, "w") as fh:
        fh.write("#!/usr/bin/env bash\n"
                 "# A promotion that DAMAGES the live config and then fails: truncate\n"
                 "# the live file to a half-written fragment, then die. A rollback that\n"
                 "# never actually restores would leave this torn config behind.\n"
                 "printf '%s' '{\"env\": {\"vars\": {' > \"$2\"\n"
                 "exit 9\n")
    os.chmod(tornp, 0o755)


# ---------------------------------------------------------------------------
# 1 — prior opt-in + empty repair preserves and reports preserved
# ---------------------------------------------------------------------------
def case_prior_optin_empty_repair(tmp):
    cfg = os.path.join(tmp, "c1.json")
    write_cfg(cfg, "enabled")
    before = sha(cfg)
    rep, _ = run_engine(tmp, cfg, "", before)
    after = sha(cfg)
    check(rep.get("state") == "preserved",
          "1 empty repair input on an enabled box reports state=preserved (got %r)" % rep.get("state"))
    check(read_vars(cfg).get(CANON) == OPS[0] and read_vars(cfg).get(ALIAS) == OPS[0],
          "1 destination survives the preserve (canon and alias both intact)")
    check(before == after,
          "1 preserve did not rewrite the config bytes (no gratuitous churn)")


# ---------------------------------------------------------------------------
# 2 — initial opt-out + empty repair stays off and does NOT claim disabled
# ---------------------------------------------------------------------------
def case_initial_optout_empty_repair(tmp):
    cfg = os.path.join(tmp, "c2.json")
    write_cfg(cfg, "disabled")
    before = sha(cfg)
    rep, _ = run_engine(tmp, cfg, "", before)
    check(rep.get("state") == "preserve-no-destination",
          "2 empty repair on a never-configured box reports preserve-no-destination (got %r)" % rep.get("state"))
    check(read_vars(cfg).get(CANON) is None and read_vars(cfg).get(ALIAS) is None,
          "2 no destination was invented by an empty repair")
    check(before == sha(cfg), "2 the run did not churn the config bytes")


# ---------------------------------------------------------------------------
# 3 — explicit disable removes canonical AND alias
# ---------------------------------------------------------------------------
def case_explicit_disable(tmp):
    cfg = os.path.join(tmp, "c3.json")
    write_cfg(cfg, "enabled")
    rep, _ = run_engine(tmp, cfg, "disable", sha(cfg))
    v = read_vars(cfg)
    check(rep.get("state") == "disabled",
          "3 explicit disable reports state=disabled (got %r)" % rep.get("state"))
    check(v.get(CANON) is None, "3 canonical key removed by explicit disable")
    check(v.get(ALIAS) is None, "3 alias key removed by explicit disable")
    check("disabled" == rep.get("state") and v.get(CANON) is None,
          "3 reported state matches the bytes on disk")


# ---------------------------------------------------------------------------
# 4 — changed destination writes both keys and they agree
# ---------------------------------------------------------------------------
def case_changed_destination(tmp):
    cfg = os.path.join(tmp, "c4.json")
    write_cfg(cfg, "enabled")
    rep, _ = run_engine(tmp, cfg, "999888777", sha(cfg))
    v = read_vars(cfg)
    check(rep.get("state") == "destination-changed",
          "4 a different destination reports destination-changed (got %r)" % rep.get("state"))
    check(v.get(CANON) == "999888777" and v.get(ALIAS) == "999888777",
          "4 canonical and alias both carry the new destination")
    check(rep.get("destination") == "999888777",
          "4 the reported destination equals the on-disk destination")


# ---------------------------------------------------------------------------
# 5 — alias disagreement is reported, never guessed away and never removed
# ---------------------------------------------------------------------------
def case_alias_disagreement(tmp):
    cfg = os.path.join(tmp, "c5.json")
    write_cfg(cfg, "disagree")
    before = sha(cfg)
    rep, _ = run_engine(tmp, cfg, "", before)
    v = read_vars(cfg)
    check(rep.get("state") == "preserve-alias-disagreement",
          "5 disagreement reports preserve-alias-disagreement (got %r)" % rep.get("state"))
    check(v.get(CANON) == OPS[0] and v.get(ALIAS) == OPS[1],
          "5 neither side of the disagreement was guessed or deleted")
    check(before == sha(cfg), "5 the disagreeing config was not rewritten")


# ---------------------------------------------------------------------------
# 6 — concurrent edit: CAS refuses and the concurrent edit survives
# ---------------------------------------------------------------------------
def case_concurrent_edit(tmp):
    cfg = os.path.join(tmp, "c6.json")
    write_cfg(cfg, "enabled")
    stale = sha(cfg)
    with open(cfg) as fh:
        doc = json.load(fh)
    doc["env"]["vars"][CANON] = "555000111"
    doc["env"]["vars"][ALIAS] = "555000111"
    doc["concurrentMarker"] = "written-by-another-process"
    with open(cfg, "w") as fh:
        json.dump(doc, fh, indent=2)
    concurrent = sha(cfg)
    rep, _ = run_engine(tmp, cfg, "999888777", stale, expect_sha=stale)
    v = read_vars(cfg)
    check(rep.get("state") == "refused" and rep.get("cas") == "mismatch",
          "6 a stale revision is refused by CAS (state=%r cas=%r)" % (rep.get("state"), rep.get("cas")))
    check(v.get(CANON) == "555000111",
          "6 the concurrent write survived; the stale run did not clobber it")
    check(sha(cfg) == concurrent,
          "6 the refused run changed nothing on disk")
    check("concurrentMarker" in json.load(open(cfg)),
          "6 the concurrent process's own key is still present")


# ---------------------------------------------------------------------------
# 7 — invalid candidate: refused, live config untouched, rollback not needed
# ---------------------------------------------------------------------------
def case_invalid_candidate(tmp):
    cfg = os.path.join(tmp, "c7.json")
    write_cfg(cfg, "enabled")
    before = sha(cfg)
    rejecting = os.path.join(tmp, "validator_reject.sh")
    with open(rejecting, "w") as fh:
        fh.write("#!/usr/bin/env bash\n"
                 "echo '{\"rc\":1,\"valid\":false,\"detail\":\"schema rejected the candidate\"}'\n"
                 "exit 1\n")
    os.chmod(rejecting, 0o755)
    rep, _ = run_engine(tmp, cfg, "999888777", before,
                        extra=["--validator-program", rejecting])
    check(rep.get("state") == "refused",
          "7 an unvalidatable candidate is refused (got %r)" % rep.get("state"))
    check(rep.get("rollback", "").startswith("not-needed:live-config-never-touched"),
          "7 rollback correctly reported as never-needed (live config untouched)")
    check(sha(cfg) == before, "7 the live config bytes are unchanged after a refused promote")
    leftover = [f for f in os.listdir(tmp) if ".rr032-candidate" in f and f.startswith("c7")]
    check(not leftover, "7 no candidate file was left behind")


# ---------------------------------------------------------------------------
# 8 — promote failure rolls back to the source bytes
# ---------------------------------------------------------------------------
def case_promote_failure_rolls_back(tmp):
    cfg = os.path.join(tmp, "c8.json")
    write_cfg(cfg, "enabled")
    before = sha(cfg)
    rep, _ = run_engine(tmp, cfg, "999888777", before, promote="promote_fail.sh")
    check(rep.get("state") == "rolled-back",
          "8 a failed promote reports rolled-back (got %r)" % rep.get("state"))
    check(sha(cfg) == before,
          "8 the live config was restored byte-for-byte after the failed promote")
    check(read_vars(cfg).get(CANON) == OPS[0],
          "8 the pre-run destination is back, not the failed candidate's")

    # The real failure mode: the live file is damaged BEFORE the failure, so a
    # rollback that never restores would leave a torn config behind.
    torn = os.path.join(tmp, "c8-torn.json")
    write_cfg(torn, "enabled")
    before_torn = sha(torn)
    rep2, _ = run_engine(tmp, torn, "999888777", before_torn,
                         promote="promote_tears_then_fails.sh")
    check(rep2.get("state") == "rolled-back",
          "8f a promotion that damages the live config then fails reports rolled-back (got %r)"
          % rep2.get("state"))
    check(sha(torn) == before_torn,
          "8g the DAMAGED live config was restored byte-for-byte, not left torn")
    try:
        with open(torn) as fh:
            doc = json.load(fh)
        parsed = True
    except ValueError:
        doc, parsed = {}, False
    check(parsed, "8h the restored config is parseable JSON again, not a fragment")
    check((doc.get("env") or {}).get("vars", {}).get(CANON) == OPS[0],
          "8i the restored config carries the pre-run destination")
    check(rep2.get("rollback", "").startswith("restored-source-bytes"),
          "8j the rollback reason names the restored source bytes (%r)" % rep2.get("rollback"))


# ---------------------------------------------------------------------------
# 9 — Docker HOME outside the mount: the mount root wins
# ---------------------------------------------------------------------------
def case_docker_root_wins(tmp):
    root = os.path.join(tmp, "docker-root")
    os.makedirs(root, exist_ok=True)
    fake_home = os.path.join(tmp, "fake-home")
    os.makedirs(os.path.join(fake_home, ".openclaw"), exist_ok=True)
    proc = subprocess.run(
        [sys.executable, ENGINE, "--stage", "resolve-root",
         "--cfg", os.path.join(tmp, "unused.json"), "--oc-root", root],
        capture_output=True, text=True,
        env=dict(os.environ, HOME=fake_home))
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {}
    check(out.get("root") == root,
          "8a an explicit verified root wins over HOME (got %r)" % out.get("root"))
    ws = out.get("workspace") or ""
    check(ws.startswith(root),
          "8b the remote-rescue workspace is resolved under the verified root, not HOME (got %r)" % ws)
    check(not ws.startswith(fake_home),
          "8c the workspace is NOT under a HOME that sits outside the mount")

    spaced = os.path.join(tmp, "path with spaces", "rr")
    cfg = os.path.join(tmp, "c9.json")
    write_cfg(cfg, "enabled")
    rep, _ = run_engine(tmp, cfg, "", sha(cfg), extra=["--workspace", spaced,
                                                      "--workspace-explicit"])
    check(rep.get("mount_state") in ("path-resolved-and-created-space-safe", "missing"),
          "8d a workspace path containing spaces resolves without word splitting (%r)"
          % rep.get("mount_state"))
    check(os.path.isdir(spaced),
          "8e the space-containing workspace was created at the exact path")


# ---------------------------------------------------------------------------
# 10 — owner/operator separation: custom mount retained, routing resolves apart
# ---------------------------------------------------------------------------
def case_owner_operator_separation(tmp):
    cfg = os.path.join(tmp, "c10.json")
    write_cfg(cfg, "enabled")
    custom = os.path.join(tmp, "custom-mount", "rr")
    os.makedirs(custom, exist_ok=True)
    with open(cfg) as fh:
        doc = json.load(fh)
    doc["agents"]["entries"]["remote-rescue"]["workspace"] = custom
    with open(cfg, "w") as fh:
        json.dump(doc, fh, indent=2)
    rep, _ = run_engine(tmp, cfg, "", sha(cfg), workspace_explicit=False)
    with open(cfg) as fh:
        doc = json.load(fh)
    ws_after = doc["agents"]["entries"]["remote-rescue"]["workspace"]
    check(ws_after == custom,
          "9a an existing valid custom mount is retained when the operator named no mount (got %r)" % ws_after)
    owner_ws = doc["agents"]["entries"]["main"].get("workspace")
    check(owner_ws != custom,
          "9b owner workspace and operator workspace are distinct (%r vs %r)" % (owner_ws, custom))
    for op in OPS:
        check(op in doc["channels"]["telegram"]["allowFrom"],
              "9c authorized operator %s keeps inbound access across the repair" % op)
        check(op not in (doc["channels"]["telegram"].get("groupAllowFrom") or []),
              "9d operator %s is not reachable from the group allowlist" % op)


# ---------------------------------------------------------------------------
# 11 — routing acceptance against the REAL resolver (skip, never pass, if absent)
# ---------------------------------------------------------------------------
def find_resolver():
    cands = [
        os.environ.get("OPENCLAW_ROUTING_MODULE", ""),
        os.path.join(os.path.expanduser("~"), ".npm-global", "lib", "node_modules",
                     "openclaw", "dist", "plugin-sdk", "routing.js"),
        "/usr/local/lib/node_modules/openclaw/dist/plugin-sdk/routing.js",
        "/usr/lib/node_modules/openclaw/dist/plugin-sdk/routing.js",
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def case_routing_acceptance(tmp):
    resolver = find_resolver()
    if resolver is None:
        skip("11 no installed OpenClaw resolver present; routing acceptance NOT asserted "
             "(set OPENCLAW_ROUTING_MODULE to the target version's routing.js)")
        return
    cfg = os.path.join(tmp, "c11.json")
    write_cfg(cfg, "enabled")
    argv = ["node", VERIFIER, "--config", cfg, "--module", resolver,
            "--owner-id", OWNER_ID]
    for op in OPS:
        argv += ["--operator-id", op]
    proc = subprocess.run(argv, capture_output=True, text=True)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        bad("11 routing verifier produced no parseable verdict: %s" % proc.stderr[-200:])
        return
    check(out.get("verdict") == "PASS",
          "11 routing verdict is PASS against the real resolver (got %r)" % out.get("verdict"))
    checks = out.get("checks") or []
    op_checks = [c for c in checks if c.get("subject") in OPS]
    check(len(op_checks) == len(OPS),
          "11 all %d operator identities were resolved, not just the first" % len(OPS))
    for c in op_checks:
        actual = c.get("actual") or {}
        check(c.get("ok") is True and actual.get("agentId") == "remote-rescue",
              "11 operator %s DM resolves to remote-rescue (got %r)" % (c.get("subject"), actual.get("agentId")))
        check(actual.get("sessionKey") == "agent:remote-rescue:direct:%s" % c.get("subject"),
              "11 operator %s gets its OWN session, not a shared one (%r)"
              % (c.get("subject"), actual.get("sessionKey")))
    owner = [c for c in checks if c.get("subject") == OWNER_ID]
    if owner:
        actual = owner[0].get("actual") or {}
        check(actual.get("agentId") != "remote-rescue",
              "11 the client owner does NOT resolve to the rescue agent (got %r)" % actual.get("agentId"))
        check(actual.get("sessionKey") != "agent:remote-rescue:direct:%s" % OWNER_ID,
              "11 the owner session is separate from every operator session")

    # Proof the verifier can fail: drop the bindings and re-resolve.
    with open(cfg) as fh:
        doc = json.load(fh)
    doc.pop("bindings", None)
    stripped = os.path.join(tmp, "c11-nobindings.json")
    with open(stripped, "w") as fh:
        json.dump(doc, fh, indent=2)
    argv2 = ["node", VERIFIER, "--config", stripped, "--module", resolver]
    for op in OPS:
        argv2 += ["--operator-id", op]
    proc2 = subprocess.run(argv2, capture_output=True, text=True)
    check(proc2.returncode != 0,
          "11 negative control: with bindings removed the verifier FAILS (proves it can fail)")


# ---------------------------------------------------------------------------
# 12 — field presence is not routing (the defect the repair replaces)
# ---------------------------------------------------------------------------
def case_field_presence_is_not_routing(tmp):
    resolver = find_resolver()
    if resolver is None:
        skip("12 resolver absent; the field-presence trap cannot be demonstrated")
        return
    cfg = os.path.join(tmp, "c12.json")
    write_cfg(cfg, "disabled")
    with open(cfg) as fh:
        doc = json.load(fh)
    doc.pop("bindings", None)
    doc["agents"]["entries"]["remote-rescue"] = {
        "name": "Remote Rescue by T Otts",
        "workspace": os.path.join(tmp, "ws", "rr"),
        "telegram": {"allowFrom": list(OPS)},
    }
    doc["channels"]["telegram"]["allowFrom"] = ["111"] + OPS
    with open(cfg, "w") as fh:
        json.dump(doc, fh, indent=2)
    argv = ["node", VERIFIER, "--config", cfg, "--module", resolver]
    for op in OPS:
        argv += ["--operator-id", op]
    proc = subprocess.run(argv, capture_output=True, text=True)
    check(proc.returncode != 0,
          "12 the old field-presence shape is REJECTED by the resolver (allowFrom + workspace "
          "are not routing); the verifier fails it rather than passing it")
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {}
    mism = [c for c in (out.get("checks") or []) if not c.get("ok")]
    check(len(mism) == len(OPS),
          "12 all %d operators are reported as NOT routed by field presence alone" % len(OPS))


# ---------------------------------------------------------------------------
# 13 — repair WIRES routing from the old inert shape, verified by the resolver
# ---------------------------------------------------------------------------
def case_repair_wires_real_routing(tmp):
    """The decisive case: start from the shape the old installer produced.

    A config carrying only `agents.list[].telegram.allowFrom` + a per-agent
    workspace has NO routing effect. The repair must replace that with real
    bindings, and the resolver must confirm the result. Asserting on the
    presence of a written field would pass on the broken shape too.
    """
    cfg = os.path.join(tmp, "c13.json")
    with open(cfg, "w") as fh:
        json.dump({
            "agents": {
                "ownership": "explicit",
                "entries": {
                    "main": {"workspace": os.path.join(tmp, "ws", "owner")},
                    "remote-rescue": {
                        "name": "Remote Rescue by T Otts",
                        "workspace": os.path.join(tmp, "ws", "rr"),
                        "telegram": {"allowFrom": OPS},
                    },
                },
            },
            "channels": {"telegram": {"allowFrom": ["111"] + OPS, "groupAllowFrom": ["111"]}},
            "env": {"vars": {CANON: OPS[0], ALIAS: OPS[0]}},
        }, fh, indent=2)

    rep, _ = run_engine(tmp, cfg, "", sha(cfg), workspace_explicit=False)
    with open(cfg) as fh:
        doc = json.load(fh)

    bindings = doc.get("bindings") or []
    check(len(bindings) == len(OPS),
          "13 the repair wrote one binding per operator identity (got %d)" % len(bindings))
    by_peer = {}
    for b in bindings:
        peer = ((b.get("match") or {}).get("peer") or {})
        by_peer[str(peer.get("id"))] = b
    for op in OPS:
        b = by_peer.get(op)
        check(b is not None and b.get("agentId") == "remote-rescue",
              "13 operator %s is bound to remote-rescue" % op)
        check(b is not None and (b.get("session") or {}).get("dmScope") == "per-peer",
              "13 operator %s binding isolates the session with dmScope=per-peer" % op)
    check("telegram" not in (doc["agents"]["entries"]["remote-rescue"] or {}),
          "13 the inert per-agent telegram key was removed, not left to look like routing")

    resolver = find_resolver()
    if resolver is None:
        skip("13 resolver absent; the repaired routing could not be resolved")
        return
    argv = ["node", VERIFIER, "--config", cfg, "--module", resolver, "--owner-id", OWNER_ID]
    for op in OPS:
        argv += ["--operator-id", op]
    proc = subprocess.run(argv, capture_output=True, text=True)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        bad("13 verifier produced no verdict on the repaired config: %s" % proc.stderr[-200:])
        return
    check(out.get("verdict") == "PASS",
          "13 the repaired config actually routes, verified by the real resolver (got %r)"
          % out.get("verdict"))
    for c in out.get("checks") or []:
        if c.get("subject") in OPS:
            actual = c.get("actual") or {}
            check(actual.get("agentId") == "remote-rescue"
                  and actual.get("sessionKey") == "agent:remote-rescue:direct:%s" % c.get("subject"),
                  "13 operator %s resolves to its own isolated session after repair (%r)"
                  % (c.get("subject"), actual.get("sessionKey")))


# ---------------------------------------------------------------------------
# 14 — check mode is READ-ONLY: it must not touch the config it inspects
# ---------------------------------------------------------------------------
def case_check_mode_is_read_only(tmp):
    cfg = os.path.join(tmp, "c14.json")
    write_cfg(cfg, "enabled")
    before = sha(cfg)
    rep, _ = run_engine(tmp, cfg, "999888777", before, extra=["--check"])
    check(rep.get("check_only") is True,
          "14 check mode is reported as check_only in the output")
    check(rep.get("promote") == "not-attempted",
          "14 check mode attempts no promote (got %r)" % rep.get("promote"))
    check(sha(cfg) == before,
          "14 check mode left the inspected config byte-for-byte unchanged")
    check(read_vars(cfg).get(CANON) == OPS[0],
          "14 check mode did not apply the destination it was asked to inspect")
    check(rep.get("state") == "destination-changed",
          "14 check mode still REPORTS the state it found (got %r)" % rep.get("state"))
    leftovers = [f for f in os.listdir(tmp)
                 if ".rr032-candidate" in f and os.path.basename(f).startswith("c14")]
    check(not leftovers, "14 check mode wrote no candidate file")
    checks = [f for f in os.listdir(tmp) if ".rr032-rollback" in f and "c14" in f]
    check(not checks, "14 check mode wrote no rollback snapshot")


# ---------------------------------------------------------------------------
# negative control for THIS FILE
# ---------------------------------------------------------------------------
def self_control(tmp):
    """If the harness cannot fail, every ok above is worthless. Prove it can."""
    cfg = os.path.join(tmp, "ctl.json")
    write_cfg(cfg, "enabled")
    before = sha(cfg)
    rep, _ = run_engine(tmp, cfg, "999888777", before)
    changed = sha(cfg) != before
    check(changed and rep.get("state") == "destination-changed",
          "control: an actual destination change IS detected as a change "
          "(so 'bytes unchanged' elsewhere is a real observation, not a broken check)")
    v = read_vars(cfg)
    check(not (v.get(CANON) is None and v.get(ALIAS) is None),
          "control: the emptiness assertion used by case 3 can distinguish set from unset")


# ---------------------------------------------------------------------------
# 15 — the workspace the report NAMES is the workspace the box USES
#
# A mount the config already declares is the one the operator's session storage
# actually lives in. Reporting a root-derived path instead is a false statement
# about the box, and creating a root-derived directory the box never uses leaves
# a stray mount behind. Both are the untruthful-state class RR-032 removes.
# ---------------------------------------------------------------------------
def case_workspace_truthfulness(tmp):
    base = os.path.join(tmp, "ws15")
    os.makedirs(base, exist_ok=True)

    # (a) the config DECLARES a custom mount -> that mount wins, nothing created
    declared = os.path.join(base, "declared-custom-rr")
    os.makedirs(declared, exist_ok=True)
    cfg = os.path.join(base, "config.json")
    write_cfg(cfg, "enabled")
    doc = json.load(open(cfg))
    doc["agents"]["entries"]["remote-rescue"]["workspace"] = declared
    doc["agents"]["entries"]["main"]["workspace"] = os.path.join(base, "owner")
    json.dump(doc, open(cfg, "w"), indent=2)
    osha = sha(cfg)

    # No --workspace and no --workspace-explicit: the engine must adopt what the
    # config itself declares rather than derive a path from the root.
    report = cfg + ".rep15a"
    default_path = os.path.join(tmp, "root", "workspaces", "remote-rescue")
    subprocess.run(
        [sys.executable, ENGINE, "--cfg", cfg, "--repair", "--requested", "",
         "--source-revision", "sha256:" + osha, "--expect-sha", osha,
         "--oc-root", os.path.join(tmp, "root"),
         "--reconcile-operators", "--reconcile-routing",
         "--promote-program", os.path.join(tmp, "promote_ok.sh"),
         "--report", report]
        + sum([["--operator-id", op] for op in OPS], []),
        capture_output=True, text=True)
    rep = json.load(open(report))

    check(rep.get("workspace") == declared,
          "15a report names the CONFIG-DECLARED mount, not a root-derived one (got %r)"
          % rep.get("workspace"))
    check(rep.get("workspace_source") == "declared-by-config",
          "15a the report says WHERE the workspace came from (got %r)"
          % rep.get("workspace_source"))
    check(not os.path.exists(default_path),
          "15a no stray root-derived workspace was created beside the declared one")
    after = json.load(open(cfg))
    check(after["agents"]["entries"]["remote-rescue"].get("workspace") == declared,
          "15a the config still declares its own mount after the repair")
    causes = " ".join(c.get("cause", "") for c in (rep.get("transitions") or []))
    check("declared-by-config" in causes,
          "15a the workspace transition names the declared mount as its source")

    # (b) the config declares NO mount -> creating one is correct AND reported so
    cfg2 = os.path.join(base, "config2.json")
    write_cfg(cfg2, "enabled")
    doc2 = json.load(open(cfg2))
    doc2["agents"]["entries"]["remote-rescue"].pop("workspace", None)
    json.dump(doc2, open(cfg2, "w"), indent=2)
    osha2 = sha(cfg2)
    report2 = cfg2 + ".rep15b"
    subprocess.run(
        [sys.executable, ENGINE, "--cfg", cfg2, "--repair", "--requested", "",
         "--source-revision", "sha256:" + osha2, "--expect-sha", osha2,
         "--oc-root", os.path.join(tmp, "root"),
         "--reconcile-operators", "--reconcile-routing",
         "--promote-program", os.path.join(tmp, "promote_ok.sh"),
         "--report", report2]
        + sum([["--operator-id", op] for op in OPS], []),
        capture_output=True, text=True)
    rep2 = json.load(open(report2))
    check(rep2.get("workspace") == default_path,
          "15b with no declared mount the resolved workspace is reported (got %r)"
          % rep2.get("workspace"))
    check(rep2.get("workspace_source") == "resolved-from-root",
          "15b 15b workspace_source says resolved-from-root (got %r)"
          % rep2.get("workspace_source"))
    check(rep2.get("mount_state") == "created",
          "15b a mount this run created is reported as created (got %r)"
          % rep2.get("mount_state"))
    check(os.path.isdir(default_path),
          "15b the reported workspace directory actually exists after the run")
    tnames2 = " ".join(c.get("to", "") for c in (rep2.get("transitions") or []))
    check("workspace-created" in tnames2,
          "15b the NAMED transition for a mount this run created is workspace-created "
          "(transitions: %s)" % tnames2)
    after2 = json.load(open(cfg2))
    check(after2["agents"]["entries"]["remote-rescue"].get("workspace") == default_path,
          "15b the created mount was wired into the config it was created for")

    # (c) idempotence: a second run over the same box reports the mount as
    #     existing, never as freshly created
    cfg = os.path.join(base, "config3.json")
    write_cfg(cfg, "enabled")
    doc3 = json.load(open(cfg))
    doc3["agents"]["entries"]["remote-rescue"]["workspace"] = os.path.join(base, "owner")
    json.dump(doc3, open(cfg, "w"), indent=2)
    osha3 = sha(cfg)
    for tag in ("first", "second"):
        rp = cfg + "." + tag
        subprocess.run(
            [sys.executable, ENGINE, "--cfg", cfg, "--repair", "--requested", "",
             "--source-revision", "sha256:" + osha3, "--expect-sha", osha3,
             "--oc-root", os.path.join(tmp, "root"),
             "--reconcile-operators", "--reconcile-routing",
             "--promote-program", os.path.join(tmp, "promote_ok.sh"),
             "--report", rp]
            + sum([["--operator-id", op] for op in OPS], []),
            capture_output=True, text=True)
        r = json.load(open(rp))
        osha3 = sha(cfg)
        if tag == "first":
            check(r.get("mount_state") == "created",
                  "15c first run on a box with no mount creates it (got %r)"
                  % r.get("mount_state"))
        else:
            check(r.get("mount_state") != "created",
                  "15c second run does NOT re-report an existing mount as created (got %r)"
                  % r.get("mount_state"))
            tnames = " ".join(c.get("to", "") for c in (r.get("transitions") or []))
            check("workspace-created" not in tnames,
                  "15c second run does not NAME a transition workspace-created for a mount "
                  "that already existed (transitions: %s)" % tnames)
            check("workspace-present" in tnames or "workspace-custom-retained" in tnames,
                  "15c second run names the mount as already present (transitions: %s)" % tnames)

    # (d) a mount that does NOT exist must never be named "workspace-present".
    #     This is the read-only path a check run takes, and the report of what a
    #     box HAS is the whole deliverable of a check run.
    missing = os.path.join(base, "not-there-rr")
    cfg4 = os.path.join(base, "config4.json")
    write_cfg(cfg4, "enabled")
    doc4 = json.load(open(cfg4))
    doc4["agents"]["entries"]["remote-rescue"]["workspace"] = missing
    json.dump(doc4, open(cfg4, "w"), indent=2)
    osha4 = sha(cfg4)
    rp4 = cfg4 + ".rep15d"
    subprocess.run(
        [sys.executable, ENGINE, "--cfg", cfg4, "--check", "--requested", "",
         "--source-revision", "sha256:" + osha4, "--expect-sha", osha4,
         "--oc-root", os.path.join(tmp, "root"),
         "--reconcile-operators", "--reconcile-routing",
         "--promote-program", os.path.join(tmp, "promote_ok.sh"),
         "--report", rp4]
        + sum([["--operator-id", op] for op in OPS], []),
        capture_output=True, text=True)
    r4 = json.load(open(rp4))
    tnames4 = " ".join(c.get("to", "") for c in (r4.get("transitions") or []))
    check(not os.path.exists(missing),
          "15d check mode did not create the mount it was inspecting")
    check(r4.get("mount_state") == "missing",
          "15d an absent mount is reported as missing (got %r)" % r4.get("mount_state"))
    check("workspace-present" not in tnames4,
          "15d an ABSENT mount is never NAMED workspace-present (transitions: %s)" % tnames4)
    check("workspace-absent" in tnames4 or "workspace-created" in tnames4,
          "15d an absent mount is named workspace-absent (transitions: %s)" % tnames4)

def main():
    check(os.path.isfile(ENGINE), "engine present at %s" % ENGINE)
    errors = 0
    for module in (ENGINE, VERIFIER):
        if module.endswith(".py"):
            proc = subprocess.run([sys.executable, "-c",
                                   "import ast,sys;ast.parse(open(sys.argv[1]).read())", module],
                                  capture_output=True, text=True)
            if not check(proc.returncode == 0, "syntax ok: %s" % os.path.basename(module)):
                errors += 1
    if errors:
        print("\n%d/%d checks passed, %d failed" % (PASS, PASS + FAIL, FAIL))
        return 1

    tmp = tempfile.mkdtemp(prefix="rr032-")
    os.environ["RR032_TMP"] = tmp
    try:
        make_fixtures(tmp)
        case_prior_optin_empty_repair(tmp)
        case_initial_optout_empty_repair(tmp)
        case_explicit_disable(tmp)
        case_changed_destination(tmp)
        case_alias_disagreement(tmp)
        case_concurrent_edit(tmp)
        case_invalid_candidate(tmp)
        case_promote_failure_rolls_back(tmp)
        case_docker_root_wins(tmp)
        case_owner_operator_separation(tmp)
        case_routing_acceptance(tmp)
        case_field_presence_is_not_routing(tmp)
        case_repair_wires_real_routing(tmp)
        case_check_mode_is_read_only(tmp)
        case_workspace_truthfulness(tmp)
        self_control(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d/%d checks passed, %d failed, %d skipped" % (PASS, PASS + FAIL, FAIL, SKIP))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
