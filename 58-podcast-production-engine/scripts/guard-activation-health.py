#!/usr/bin/env python3
# =============================================================================
# 58-PODCAST-PRODUCTION-ENGINE :: GUARD-ACTIVATION-HEALTH (act-6 fleet-safety net)
# -----------------------------------------------------------------------------
# DETERMINISTIC, NO-AI, FAIL-CLOSED. This guard exists because of one real
# incident: intake and publish both worked, but the PRODUCTION PROCESSOR never
# activated -- queued TaskFlows sat forever because the activation layer (hook
# registration script, controller processor, department installer) was missing
# from the build and from the box, and nothing ever said so. This gate makes
# that whole class of gap FAIL LOUDLY.
#
# WHAT IT CHECKS
#
#   REPO PRESENCE (always runs; the --repo-only surface for CI/merge gates):
#     R1. scripts/register-podcast-hook.sh      intake hook registration
#     R2. scripts/podcast_controller.py         the production processor that
#                                               drains queued TaskFlows through
#                                               the 18 pipeline steps
#     R3. scripts/install-podcast-department.sh department agent + scheduler
#                                               installer for the box
#     A missing file means the pipeline can never activate on ANY box. Any miss
#     FAILS (exit 2). Paths are overridable for relocation tests but never
#     exemptable.
#
#   ON-BOX ACTIVATION (default mode; skipped by --repo-only):
#     B1. the three activation scripts are installed on this box (the installed
#         skill copy under $SKILLS_DIR_DEFAULT, resolved exactly like
#         qc-podcast.sh does it)
#     B2. the podcast department agent directory is registered and NON-EMPTY
#         (<root>/agents/dept-podcast, root candidates: repo root, the skills
#         dir parent, $HOME/.openclaw; override with --agents-root). An empty
#         directory is a FAIL: an agent dir with no agent file routes intake to
#         the wrong session.
#     B3. the loopback TaskFlow gateway is reachable: a bounded HTTP HEAD on
#         --gateway-url (default http://127.0.0.1:18789, the webhook plugin's
#         action API per flow_client.py). Any HTTP answer counts as reachable;
#         only a connection failure or timeout FAILS. No credential ever leaves
#         this probe.
#     B4. an intake webhook route podcast-intake-<slug> is registered for every
#         client slug in --client-slug / $PODCAST_CLIENT_SLUGS, read from the
#         box openclaw.json at plugins.entries.webhooks.config.routes (the map
#         keyed by routeId per scripts/webhook/route-template.json5; the scan
#         tolerates JSON5 comments, never touches or prints a secret). With no
#         configured slugs this is a SKIP, not a failure.
#     B5. the controller is RUNNABLE (--help exits 0, bounded) and SCHEDULED.
#         The engine is NO-DAEMON by design: the controller is a per-fire
#         processor, so the proof of life is the scheduled heartbeat (a crontab
#         entry or a launchd plist naming the controller or the installer), not
#         a running process.
#
# SEVERITY MODEL. Repo misses are ALWAYS fatal -- the build is broken
# regardless of any box. On-box findings are FATAL when --strict is passed or
# when the box declares itself provisioned ($PODCAST_ACTIVATION_PROVISIONED=1,
# or any client slug configured); otherwise they are non-fatal WARNs so a dev
# checkout or a not-yet-provisioned box does not fail its install QC. A
# provisioned box with a dead activation layer is exactly the incident this
# guard was written to catch, and it must fail.
#
# No secret is ever printed: presence, behavior, and SET/NOT-SET only.
#
# EXIT: 0 PASS / 2 AUTOFAIL / 3 USAGE-IO.
# USAGE:
#   python3 guard-activation-health.py --repo-only [--repo-root DIR] [--json]
#   python3 guard-activation-health.py [--strict] [--repo-root DIR]
#                 [--agents-root DIR] [--gateway-url URL]
#                 [--client-slug SLUG ...] [--timeout SECS] [--json]
#   python3 guard-activation-health.py --self-test
# Test seams: $PODCAST_CRONTAB_BIN overrides the crontab binary (default
# "crontab"); $PODCAST_LAUNCHD_DIR overrides the launchd plist directory
# (default $HOME/Library/LaunchAgents); $OPENCLAW_CONFIG overrides the box
# config file path.
# =============================================================================
"""Fail-loud activation-layer health gate for the Podcast Production Engine."""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_REPO = "AF-PPE-ACTIVATION-REPO"
AF_BOX = "AF-PPE-ACTIVATION-BOX"

_SELF = Path(__file__).resolve()
_SKILL_ROOT = _SELF.parent.parent          # 58-podcast-production-engine/
_REPO_ROOT = _SKILL_ROOT.parent

DEFAULT_GATEWAY_URL = "http://127.0.0.1:18789"

# Skill-root-relative canonical paths for the activation layer.
DEFAULT_HOOK_SCRIPT = "scripts/register-podcast-hook.sh"
DEFAULT_CONTROLLER_SCRIPT = "scripts/podcast_controller.py"
DEFAULT_INSTALLER_SCRIPT = "scripts/install-podcast-department.sh"

DEPT_AGENT_DIRNAME = "dept-podcast"
ROUTE_ID_PREFIX = "podcast-intake-"
PROVISIONED_ENV = "PODCAST_ACTIVATION_PROVISIONED"
SLUGS_ENV = "PODCAST_CLIENT_SLUGS"

# Statuses a check line can carry.
PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
SKIP = "SKIP"


def _result(check_id, title, status, detail):
    return {"id": check_id, "title": title, "status": status, "detail": detail}


# --------------------------------------------------------------------------- #
# Repo presence checks (always run)
# --------------------------------------------------------------------------- #
def repo_checks(skill_root, hook_rel, controller_rel, installer_rel):
    """R1-R3: the activation layer files must exist in the build."""
    out = []
    for check_id, rel, what in (
        ("R1", hook_rel, "intake hook registration script"),
        ("R2", controller_rel, "production processor (controller)"),
        ("R3", installer_rel, "department + scheduler installer"),
    ):
        path = skill_root / rel
        if path.is_file():
            out.append(_result(check_id, what, PASS, "present: %s" % path))
        else:
            out.append(_result(
                check_id, what, FAIL,
                "MISSING: %s (queued flows can never run the pipeline)" % path))
    return out


# --------------------------------------------------------------------------- #
# On-box checks
# --------------------------------------------------------------------------- #
def box_checks(skill_root, agents_root_override, gateway_url, slugs, timeout,
               hook_rel, controller_rel, installer_rel):
    """B1-B5: the activation layer must be live on this box."""
    out = []

    # B1: installed activation scripts ----------------------------------------
    missing = []
    for rel in (hook_rel, controller_rel, installer_rel):
        if not (skill_root / rel).is_file():
            missing.append(rel)
    if missing:
        out.append(_result("B1", "activation scripts installed on this box", FAIL,
                           "missing under %s: %s" % (skill_root, ", ".join(missing))))
    else:
        out.append(_result("B1", "activation scripts installed on this box", PASS,
                           "all three present under %s" % skill_root))

    # B2: department agent directory registered and non-empty ------------------
    agent_dir, candidates = _resolve_agent_dir(skill_root, agents_root_override)
    if agent_dir is not None and _dir_non_empty(agent_dir):
        out.append(_result("B2", "podcast department agent registered", PASS,
                           "non-empty agent dir: %s" % agent_dir))
    elif agent_dir is not None:
        out.append(_result("B2", "podcast department agent registered", FAIL,
                           "agent dir exists but is EMPTY: %s" % agent_dir))
    else:
        out.append(_result("B2", "podcast department agent registered", FAIL,
                           "no %s dir under any candidate: %s"
                           % (DEPT_AGENT_DIRNAME, ", ".join(str(c) for c in candidates))))

    # B3: loopback TaskFlow gateway reachable ----------------------------------
    reachable, why = _gateway_reachable(gateway_url, timeout)
    if reachable:
        out.append(_result("B3", "TaskFlow gateway reachable", PASS,
                           "%s answered within %ss" % (gateway_url, timeout)))
    else:
        out.append(_result("B3", "TaskFlow gateway reachable", FAIL,
                           "%s not reachable within %ss (%s)" % (gateway_url, timeout, why)))

    # B4: intake route registered for every configured client ------------------
    if not slugs:
        out.append(_result("B4", "intake webhook routes registered", SKIP,
                           "no client slugs configured (--client-slug or $%s); "
                           "nothing to assert" % SLUGS_ENV))
    else:
        config_path = _resolve_box_config()
        if config_path is None:
            out.append(_result("B4", "intake webhook routes registered", FAIL,
                               "configured slugs %s but no openclaw.json found "
                               "(set $OPENCLAW_CONFIG)" % sorted(slugs)))
        else:
            try:
                text = config_path.read_text(encoding="utf-8")
            except OSError as exc:
                out.append(_result("B4", "intake webhook routes registered", FAIL,
                                   "cannot read %s: %s" % (config_path, type(exc).__name__)))
            else:
                route_ids = scan_route_ids(text)
                missing_routes = [s for s in slugs
                                  if (ROUTE_ID_PREFIX + s) not in route_ids]
                if missing_routes:
                    out.append(_result(
                        "B4", "intake webhook routes registered", FAIL,
                        "no route podcast-intake-<slug> for: %s (config %s; "
                        "registered podcast routes: %s)"
                        % (", ".join(sorted(missing_routes)), config_path,
                           ", ".join(sorted(route_ids)) or "none")))
                else:
                    out.append(_result(
                        "B4", "intake webhook routes registered", PASS,
                        "route podcast-intake-<slug> registered for every "
                        "configured slug: %s (config %s)"
                        % (", ".join(sorted(slugs)), config_path)))

    # B5: controller runnable and scheduled (no-daemon proof of life) ----------
    controller_path = skill_root / controller_rel
    runnable, run_detail = _controller_runnable(controller_path, timeout)
    scheduled, sched_detail = _controller_scheduled(controller_rel, installer_rel)
    if runnable and scheduled:
        out.append(_result("B5", "controller runnable and scheduled", PASS,
                           "%s; %s" % (run_detail, sched_detail)))
    else:
        parts = []
        if not runnable:
            parts.append(run_detail)
        if not scheduled:
            parts.append(sched_detail)
        out.append(_result("B5", "controller runnable and scheduled", FAIL,
                           "; ".join(parts)))

    return out


def _resolve_agent_dir(skill_root, agents_root_override):
    """Return (agent_dir_or_None, candidates_tried)."""
    candidates = []
    if agents_root_override:
        candidates.append(Path(agents_root_override) / DEPT_AGENT_DIRNAME)
    else:
        seen = set()
        for root in (_REPO_ROOT, _REPO_ROOT.parent, Path.home() / ".openclaw"):
            cand = root / "agents" / DEPT_AGENT_DIRNAME
            if str(cand) not in seen:
                seen.add(str(cand))
                candidates.append(cand)
    for cand in candidates:
        if cand.is_dir():
            return cand, candidates
    # Report a candidate that exists but is not a directory (a stray file in
    # the agent slot is still a registration failure worth naming).
    for cand in candidates:
        if cand.exists():
            return cand, candidates
    return None, candidates


def _dir_non_empty(path):
    try:
        return any(path.iterdir())
    except OSError:
        return False


def _gateway_reachable(url, timeout):
    """Bounded HTTP HEAD. Any HTTP answer means reachable."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(1)
        return True, "http answer"
    except urllib.error.HTTPError:
        # An HTTP error status still proves the gateway is up and answering.
        return True, "http error status (still reachable)"
    except urllib.error.URLError as exc:
        return False, "url error: %s" % getattr(exc, "reason", exc)
    except (OSError, ValueError) as exc:
        return False, type(exc).__name__


def _resolve_box_config():
    """Locate the box openclaw.json without ever reading a secret value."""
    override = os.environ.get("OPENCLAW_CONFIG")
    if override:
        p = Path(override)
        return p if p.is_file() else None
    for cand in (Path.home() / ".openclaw" / "openclaw.json",
                 Path("/data/.openclaw/openclaw.json")):
        if cand.is_file():
            return cand
    return None


# Route ids live in a MAP keyed by routeId (route-template.json5). The box
# config may carry JSON5 comments, so a strict json.loads is tried first and a
# tolerant quoted-key scan is the fallback. Only route IDs are extracted; the
# route objects (which embed secret references) are never parsed or printed.
_ROUTE_KEY_RE = re.compile(r'"(podcast-intake-[A-Za-z0-9][A-Za-z0-9._-]*)"\s*:')


def scan_route_ids(text):
    """Return the set of podcast-intake-<slug> route ids declared in text."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        data = None
    if isinstance(data, dict):
        routes = (data.get("plugins", {}).get("entries", {})
                      .get("webhooks", {}).get("config", {}).get("routes"))
        if isinstance(routes, dict):
            return {k for k in routes if isinstance(k, str)
                    and k.startswith(ROUTE_ID_PREFIX)}
    return set(m.group(1) for m in _ROUTE_KEY_RE.finditer(text))


def _controller_runnable(controller_path, timeout):
    if not controller_path.is_file():
        return False, "controller script missing: %s" % controller_path
    try:
        proc = subprocess.run(
            [sys.executable, str(controller_path), "--help"],
            capture_output=True, text=True, timeout=max(5, int(timeout * 3)))
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "controller --help errored: %s" % type(exc).__name__
    if proc.returncode == 0:
        return True, "controller --help exits 0"
    return False, "controller --help exits %s" % proc.returncode


def _controller_scheduled(controller_rel, installer_rel):
    """No-daemon proof of life: a crontab entry or launchd plist names the
    controller or the installer."""
    needles = (Path(controller_rel).name, Path(installer_rel).name)
    # crontab listing (bounded; absent crontab is an empty listing, not an error)
    crontab_bin = os.environ.get("PODCAST_CRONTAB_BIN", "crontab")
    try:
        proc = subprocess.run([crontab_bin, "-l"], capture_output=True,
                              text=True, timeout=15)
        lines = proc.stdout.splitlines() if proc.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if any(n in stripped for n in needles):
            return True, "scheduled: crontab entry references %s" % _first_hit(stripped, needles)
    # launchd plists (Mac fleet)
    launchd_dir = Path(os.environ.get("PODCAST_LAUNCHD_DIR",
                                      str(Path.home() / "Library" / "LaunchAgents")))
    if launchd_dir.is_dir():
        try:
            plists = sorted(launchd_dir.glob("*.plist"))
        except OSError:
            plists = []
        for plist in plists:
            try:
                body = plist.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if any(n in body for n in needles):
                return True, "scheduled: launchd plist %s references the activation layer" % plist.name
    return False, ("not scheduled: no crontab entry or launchd plist names "
                   "%s or %s (the heartbeat that wakes the processor is missing)"
                   % needles)


def _first_hit(line, needles):
    for n in needles:
        if n in line:
            return n
    return "activation layer"


# --------------------------------------------------------------------------- #
# Severity model
# --------------------------------------------------------------------------- #
def is_provisioned(slugs):
    return os.environ.get(PROVISIONED_ENV) == "1" or bool(slugs)


def classify(repo_results, box_results, strict, provisioned):
    """Return (fatal, warn, skip) result lists under the severity model."""
    fatal = [r for r in repo_results if r["status"] == FAIL]
    warn, skip = [], []
    box_fatal = strict or provisioned
    for r in box_results:
        if r["status"] == SKIP:
            skip.append(r)
        elif r["status"] == FAIL:
            (fatal if box_fatal else warn).append(r)
    return fatal, warn, skip


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def emit(results, fatal, warn, skip, mode, as_json, repo_root):
    passed = not fatal
    if as_json:
        print(json.dumps({
            "gate": "podcast-guard-activation-health",
            "mode": mode,
            "repo_root": str(repo_root),
            "pass": passed,
            "results": [{"id": r["id"], "status": r["status"], "detail": r["detail"]}
                        for r in results],
            "findings": [{"code": AF_REPO if r["id"].startswith("R") else AF_BOX,
                          "id": r["id"]} for r in fatal],
        }, indent=2))
    else:
        print("== Podcast Production Engine :: guard-activation-health ==")
        print("  mode: %s | repo root: %s" % (mode, repo_root))
        for r in results:
            print("  [%s] %s %s : %s" % (r["status"], r["id"], r["title"], r["detail"]))
        if passed:
            print("RESULT: PASS - the activation layer is present%s."
                  % ("" if mode == "repo-only" else " and healthy where checkable"))
        else:
            print("RESULT: FAIL (fail-closed) - %d fatal finding(s):" % len(fatal))
            for r in fatal:
                print("  [%s] %s : %s" % (AF_REPO if r["id"].startswith("R") else AF_BOX,
                                          r["id"], r["detail"]))
        for r in warn:
            print("  [non-fatal WARN] %s : %s" % (r["id"], r["detail"]))
        for r in skip:
            print("  [SKIP] %s : %s" % (r["id"], r["detail"]))
    return EXIT_PASS if passed else EXIT_AUTOFAIL


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-only", dest="repo_only", action="store_true",
                    help="check only repo file presence (CI/merge gate surface)")
    ap.add_argument("--strict", action="store_true",
                    help="make on-box findings fatal even on an unprovisioned box")
    ap.add_argument("--repo-root", default=None,
                    help="repo (or installed skills dir) root; default: the "
                         "parent of this skill directory")
    ap.add_argument("--agents-root", default=None,
                    help="directory holding agents/dept-podcast (on-box check)")
    ap.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL,
                    help="loopback TaskFlow gateway base URL")
    ap.add_argument("--client-slug", dest="client_slugs", action="append",
                    default=None, help="a provisioned client slug (repeatable)")
    ap.add_argument("--timeout", type=float, default=5.0,
                    help="bounded probe timeout in seconds")
    ap.add_argument("--hook-script", default=DEFAULT_HOOK_SCRIPT)
    ap.add_argument("--controller-script", default=DEFAULT_CONTROLLER_SCRIPT)
    ap.add_argument("--installer-script", default=DEFAULT_INSTALLER_SCRIPT)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    if args.timeout <= 0:
        print("FATAL: --timeout must be positive", file=sys.stderr)
        return EXIT_USAGE

    repo_root = Path(args.repo_root) if args.repo_root else _REPO_ROOT
    if not repo_root.is_dir():
        print("FATAL: repo root not found: %s" % repo_root, file=sys.stderr)
        return EXIT_USAGE
    skill_root = repo_root / _SKILL_ROOT.name

    slugs = list(args.client_slugs or [])
    env_slugs = os.environ.get(SLUGS_ENV, "")
    slugs += [s.strip() for s in env_slugs.split(",") if s.strip()]
    slugs = sorted(set(slugs))

    repo_results = repo_checks(skill_root, args.hook_script,
                               args.controller_script, args.installer_script)
    if args.repo_only:
        fatal, warn, skip = classify(repo_results, [], False, False)
        return emit(repo_results, fatal, warn, skip, "repo-only",
                    args.json, repo_root)

    box_results = box_checks(skill_root, args.agents_root, args.gateway_url,
                             slugs, args.timeout, args.hook_script,
                             args.controller_script, args.installer_script)
    provisioned = is_provisioned(slugs)
    fatal, warn, skip = classify(repo_results, box_results,
                                 args.strict, provisioned)
    mode = "repo + on-box (severity: %s)" % (
        "strict" if args.strict else ("provisioned" if provisioned else "warn"))
    return emit(repo_results + box_results, fatal, warn, skip, mode,
                args.json, repo_root)


# --------------------------------------------------------------------------- #
# Self-test (hermetic: temp trees only, no network, no box state read)
# --------------------------------------------------------------------------- #
def self_test():
    import tempfile

    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "MISS", label))

    def make_skill(root, with_files=True):
        scripts = root / "58-podcast-production-engine" / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        if with_files:
            (scripts / "register-podcast-hook.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
            (scripts / "podcast_controller.py").write_text(
                "import sys\nif '--help' in sys.argv:\n    sys.exit(0)\n")
            (scripts / "install-podcast-department.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
        return root / "58-podcast-production-engine"

    print("== self-test: repo presence ==")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        skill = make_skill(root, with_files=True)
        res = repo_checks(skill, DEFAULT_HOOK_SCRIPT, DEFAULT_CONTROLLER_SCRIPT,
                          DEFAULT_INSTALLER_SCRIPT)
        check("all-present-passes", all(r["status"] == PASS for r in res))
        (skill / DEFAULT_CONTROLLER_SCRIPT).unlink()
        res = repo_checks(skill, DEFAULT_HOOK_SCRIPT, DEFAULT_CONTROLLER_SCRIPT,
                          DEFAULT_INSTALLER_SCRIPT)
        check("missing-controller-fails",
              any(r["status"] == FAIL for r in res))
        check("fail-detail-names-the-file",
              any(DEFAULT_CONTROLLER_SCRIPT in r["detail"] for r in res if r["status"] == FAIL))

    print("== self-test: route-id scan (JSON5 tolerant, ids only) ==")
    json5 = """
    {
      // a comment
      plugins: {
        entries: {
          webhooks: {
            config: {
              routes: {
                "podcast-intake-acme-media": { enabled: true, sessionKey: "podcast:intake:acme-media" },
                "other-skill-route": { enabled: true }
              }
            }
          }
        }
      }
    }
    """
    ids = scan_route_ids(json5)
    check("json5-route-id-found", "podcast-intake-acme-media" in ids)
    check("foreign-route-ignored", "other-skill-route" not in ids)
    strict_json = json.dumps({"plugins": {"entries": {"webhooks": {"config": {
        "routes": {"podcast-intake-zeta": {}}}}}}})
    check("strict-json-route-id-found", "podcast-intake-zeta" in scan_route_ids(strict_json))
    check("garbage-scans-empty", scan_route_ids("nothing here") == set())

    print("== self-test: on-box checks on a fake tree ==")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        skill = make_skill(root, with_files=True)
        agents = root / "agents" / DEPT_AGENT_DIRNAME
        agents.mkdir(parents=True)
        (agents / "agent.md").write_text("podcast department agent\n")
        # fake crontab seam: one heartbeat line naming the controller
        cronbin = root / "fake-crontab.sh"
        cronbin.write_text("#!/usr/bin/env bash\n"
                           "echo '*/5 * * * * python3 .../podcast_controller.py run-once'\n")
        os.chmod(cronbin, 0o755)
        os.environ["PODCAST_CRONTAB_BIN"] = str(cronbin)
        os.environ["PODCAST_LAUNCHD_DIR"] = str(root / "no-such-dir")
        # Pin the box config away from any real machine state (hermetic).
        os.environ["OPENCLAW_CONFIG"] = str(root / "no-such-openclaw.json")
        try:
            res = box_checks(skill, str(root / "agents"), "http://127.0.0.1:1",
                             ["acme-media"], 1, DEFAULT_HOOK_SCRIPT,
                             DEFAULT_CONTROLLER_SCRIPT, DEFAULT_INSTALLER_SCRIPT)
            by_id = {r["id"]: r for r in res}
            check("B1-installed-passes", by_id["B1"]["status"] == PASS)
            check("B2-agent-dir-passes", by_id["B2"]["status"] == PASS)
            check("B3-unreachable-gateway-fails", by_id["B3"]["status"] == FAIL)
            check("B4-missing-config-fails-with-slugs", by_id["B4"]["status"] == FAIL)
            check("B5-runnable-and-scheduled-passes", by_id["B5"]["status"] == PASS)
        finally:
            os.environ.pop("PODCAST_CRONTAB_BIN", None)
            os.environ.pop("PODCAST_LAUNCHD_DIR", None)
            os.environ.pop("OPENCLAW_CONFIG", None)

    print("== self-test: severity model ==")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        skill = make_skill(root, with_files=True)
        repo_res = repo_checks(skill, DEFAULT_HOOK_SCRIPT,
                               DEFAULT_CONTROLLER_SCRIPT, DEFAULT_INSTALLER_SCRIPT)
        box_fail = [_result("B3", "gateway", FAIL, "unreachable")]
        fatal, warn, _skip = classify(repo_res, box_fail, strict=False, provisioned=False)
        check("unprovisioned-box-finding-is-warn", fatal == [] and len(warn) == 1)
        fatal, warn, _skip = classify(repo_res, box_fail, strict=True, provisioned=False)
        check("strict-makes-box-finding-fatal", len(fatal) == 1)
        fatal, warn, _skip = classify(repo_res, box_fail, strict=False, provisioned=True)
        check("provisioned-makes-box-finding-fatal", len(fatal) == 1)
        (skill / DEFAULT_HOOK_SCRIPT).unlink()
        repo_res = repo_checks(skill, DEFAULT_HOOK_SCRIPT,
                               DEFAULT_CONTROLLER_SCRIPT, DEFAULT_INSTALLER_SCRIPT)
        fatal, warn, _skip = classify(repo_res, [], strict=False, provisioned=False)
        check("repo-missing-always-fatal", len(fatal) == 1)

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
