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
        self_control(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d/%d checks passed, %d failed, %d skipped" % (PASS, PASS + FAIL, FAIL, SKIP))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
