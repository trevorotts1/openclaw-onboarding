#!/usr/bin/env python3
# =============================================================================
# 58-PODCAST-PRODUCTION-ENGINE :: GUARD-ACTIVATION-HEALTH (act-6 fleet-safety net)
# -----------------------------------------------------------------------------
# DETERMINISTIC, NO-AI, FAIL-CLOSED. This guard exists because of one real
# incident: intake and publish both worked, but queued TaskFlows never ran --
# the activation layer (hook registration script, department installer, the
# deterministic intake handler) was missing from the build and from the box,
# and nothing ever said so. This gate makes that whole class of gap FAIL
# LOUDLY.
#
# THE NO-DAEMON DESIGN (the contract this guard enforces). There is NO
# controller daemon and NO poller scheduler (webhook-design.md Section 7;
# act-2, which would have built a controller daemon, was EXCLUDED as a design
# violation). The bound department agent advances each flow in its OWN turn:
# the intake route's controllerId runbook opens with ONE deterministic step,
# scripts/webhook/intake_handler.py --mode in-flow, and continues the 18-step
# pipeline in the same session. The runbook's mechanism for Steps 2-18 is the
# DETERMINISTIC STEP DRIVER, scripts/podcast_step_driver.py: the agent calls
# `podcast_step_driver.py next --job-id <id>` in its OWN turn, runs the emitted
# command, and records the advance through podcast_state.py. The step driver is
# a TOOL the agent calls, not a resident process. A bounded single invocation
# is NOT a daemon; a CRON line that calls the driver repeatedly WOULD be a
# poller and is FAILED below (B5 no-poller). The ONLY recurring podcast cron in
# the design is the daily smoke test (podcast-smoke-test.py via openclaw cron);
# no second cron, no queue poller, ever.
#
# WHAT IT CHECKS
#
#   REPO PRESENCE (always runs; the --repo-only surface for CI/merge gates):
#     R1. scripts/register-podcast-hook.sh      intake hook registration
#     R2. scripts/webhook/intake_handler.py     the deterministic first step of
#                                               the controllerId runbook; it
#                                               maps, claims, persists, and
#                                               advances each accepted intake
#     R3. scripts/install-podcast-department.sh department agent installer for
#                                               the box
#     R4. scripts/podcast_step_driver.py        the deterministic step driver
#                                               (the runbook mechanism for
#                                               Steps 2-18; `next --job-id`)
#     A missing file means the pipeline can never activate on ANY box. Any miss
#     FAILS (exit 2). Paths are overridable for relocation tests but never
#     exemptable.
#
#   ON-BOX ACTIVATION (default mode; skipped by --repo-only):
#     B1. the four activation scripts are installed on this box (the installed
#         skill copy under $SKILLS_DIR_DEFAULT, resolved exactly like
#         qc-podcast.sh does it)
#     B6. the deterministic step driver is callable: a bounded `--help` probe
#         under the box python exits 0 (no daemon armed; a cron line naming the
#         driver is still a poller and is flagged in B5)
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
#     B4. the intake route BINDING SHAPE: for every client slug in
#         --client-slug / $PODCAST_CLIENT_SLUGS, the box openclaw.json carries
#         plugins.entries.webhooks.config.routes["podcast-intake-<slug>"] with
#         sessionKey "podcast:intake:<slug>" and a controllerId of the form
#         "webhooks/podcast-intake-<slug>" (the controllerId runbook whose
#         first step is the deterministic intake handler; the shape per
#         scripts/webhook/route-template.json5). The scan tolerates JSON5
#         comments and only ever extracts route ids and two key values; a
#         secret value is never parsed, stored, or printed. With no configured
#         slugs this is a SKIP, not a failure.
#     B5. the intake env secrets are PRESENT in this process environment, and
#         NOTHING is polling. PODCAST_INTAKE_HOOK_SECRET is the route secret
#         (referenced by env SecretRef in openclaw.json; the gateway resolves
#         process.env[id] on every request) and PODCAST_INTAKE_INBOUND_SECRET
#         is the handler HMAC secret. The handler FAILS CLOSED when the HMAC
#         secret is set, so a provisioned box without it cannot verify inbound
#         signatures; only NOT-SET is ever printed, never a value. The
#         no-poller half of B5: no crontab entry names a controller or
#         scheduler daemon; a cron line naming such a daemon FAILS (the design
#         has none).
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
# (default $HOME/Library/LaunchAgents; kept for B5's no-poller scan);
# $OPENCLAW_CONFIG overrides the box config file path; and
# $PODCAST_STEP_DRIVER_PY overrides the python used for the step-driver --help
# probe (default: the python running this guard).
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

# Skill-root-relative canonical paths for the activation layer (no-daemon
# design: no controller daemon, no poller scheduler; the bound department
# agent advances each flow in its own turn). The deterministic step driver
# (podcast_step_driver.py) is the runbook's mechanism for Steps 2-18: the
# controllerId runbook calls `podcast_step_driver.py next --job-id <id>` in
# the agent's OWN tool-bearing turn. A bounded single invocation is NOT a
# resident daemon: the no-poller rule below forbids a CRON line naming it
# (that would be a poller), never the agent's own in-turn call.
DEFAULT_HOOK_SCRIPT = "scripts/register-podcast-hook.sh"
DEFAULT_HANDLER_SCRIPT = "scripts/webhook/intake_handler.py"
DEFAULT_INSTALLER_SCRIPT = "scripts/install-podcast-department.sh"
DEFAULT_DRIVER_SCRIPT = "scripts/podcast_step_driver.py"

DEPT_AGENT_DIRNAME = "dept-podcast"
ROUTE_ID_PREFIX = "podcast-intake-"
CONTROLLER_ID_PREFIX = "webhooks/podcast-intake-"
SESSION_KEY_PREFIX = "podcast:intake:"
PROVISIONED_ENV = "PODCAST_ACTIVATION_PROVISIONED"
SLUGS_ENV = "PODCAST_CLIENT_SLUGS"

# Intake env secrets checked for PRESENCE only (never printed; SET/NOT-SET).
INTAKE_SECRETS = (
    ("PODCAST_INTAKE_HOOK_SECRET",
     "route secret (env SecretRef in openclaw.json; the gateway resolves it "
     "per request)"),
    ("PODCAST_INTAKE_INBOUND_SECRET",
     "HMAC secret verified by webhook/intake_handler.py"),
)

# A cron line naming any of these names a controller/scheduler daemon, which
# the no-daemon design forbids (no poller, no per-job watcher, nothing
# sub-daily; the sole recurring podcast cron is the daily smoke test).
# podcast_step_driver is listed because a CRON line calling it repeatedly
# WOULD be a poller (a bounded in-turn `next --job-id <id>` is not).
DAEMON_NAME_NEEDLES = ("podcast_controller", "podcast_scheduler",
                       "podcast_step_driver")

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
def repo_checks(skill_root, hook_rel, handler_rel, installer_rel, driver_rel):
    """R1-R4: the activation layer files must exist in the build."""
    out = []
    for check_id, rel, what in (
        ("R1", hook_rel, "intake hook registration script"),
        ("R2", handler_rel, "deterministic intake handler "
                            "(first step of the controllerId runbook)"),
        ("R3", installer_rel, "department agent installer"),
        ("R4", driver_rel, "deterministic step driver "
                           "(the runbook mechanism for Steps 2-18)"),
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
               hook_rel, handler_rel, installer_rel, driver_rel,
               step_driver_python=None):
    """B1-B6: the activation layer must be live on this box."""
    out = []

    # B1: installed activation scripts ----------------------------------------
    missing = []
    for rel in (hook_rel, handler_rel, installer_rel, driver_rel):
        if not (skill_root / rel).is_file():
            missing.append(rel)
    if missing:
        out.append(_result("B1", "activation scripts installed on this box", FAIL,
                           "missing under %s: %s" % (skill_root, ", ".join(missing))))
    else:
        out.append(_result("B1", "activation scripts installed on this box", PASS,
                           "all four present under %s" % skill_root))

    # B6: the deterministic step driver is callable (no-daemon, bounded) ------
    driver_path = skill_root / driver_rel
    if not driver_path.is_file():
        out.append(_result("B6", "step driver callable on this box", FAIL,
                           "missing: %s" % driver_path))
    else:
        # A bounded single invocation (--help) proves the driver runs under the
        # box python without ever arming a daemon or poller. A cron line that
        # names the driver repeatedly is still a poller (flagged in B5); a
        # one-shot in-turn call is not.
        py = step_driver_python or _python_bin()
        try:
            proc = subprocess.run(
                [py, str(driver_path), "--help"],
                capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            out.append(_result("B6", "step driver callable on this box", FAIL,
                               "%s could not run: %s" % (driver_path, exc)))
        else:
            if proc.returncode == 0:
                out.append(_result(
                    "B6", "step driver callable on this box", PASS,
                    "%s --help exited 0 under %s" % (driver_path, py)))
            else:
                out.append(_result(
                    "B6", "step driver callable on this box", FAIL,
                    "%s --help exited %s under %s (stderr: %s)"
                    % (driver_path, proc.returncode, py,
                       proc.stderr.strip()[:200] or "empty")))

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

    # B4: intake route BINDING SHAPE for every configured client ---------------
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
                shapes = scan_route_shapes(text)
                problems = []
                for slug in slugs:
                    route_id = ROUTE_ID_PREFIX + slug
                    shape = shapes.get(route_id)
                    if shape is None:
                        problems.append(
                            "no route %s" % route_id)
                        continue
                    if shape["sessionKey"] != SESSION_KEY_PREFIX + slug:
                        problems.append(
                            "%s sessionKey is %s, want %s"
                            % (route_id, shape["sessionKey"] or "missing",
                               SESSION_KEY_PREFIX + slug))
                    if shape["controllerId"] != CONTROLLER_ID_PREFIX + slug:
                        problems.append(
                            "%s controllerId is %s, want %s (the controllerId "
                            "runbook whose first step is the deterministic "
                            "intake handler)"
                            % (route_id, shape["controllerId"] or "missing",
                               CONTROLLER_ID_PREFIX + slug))
                if problems:
                    out.append(_result(
                        "B4", "intake webhook routes registered", FAIL,
                        "route binding shape wrong (config %s; registered "
                        "podcast routes: %s): %s"
                        % (config_path,
                           ", ".join(sorted(shapes)) or "none",
                           "; ".join(problems))))
                else:
                    out.append(_result(
                        "B4", "intake webhook routes registered", PASS,
                        "route podcast-intake-<slug> registered with "
                        "sessionKey podcast:intake:<slug> and controllerId "
                        "webhooks/podcast-intake-<slug> for every configured "
                        "slug: %s (config %s)"
                        % (", ".join(sorted(slugs)), config_path)))

    # B5: intake env secrets present AND no poller daemon (no-daemon design) ---
    parts = []
    for name, why in INTAKE_SECRETS:
        if os.environ.get(name):
            parts.append("%s SET (%s)" % (name, why))
        else:
            parts.append("%s NOT-SET (%s)" % (name, why))
    set_count = sum(1 for name, _why in INTAKE_SECRETS
                    if os.environ.get(name))
    secrets_ok = set_count == len(INTAKE_SECRETS)
    daemon_line = _cron_daemon_line()
    if daemon_line is not None:
        parts.append("POLLER FOUND: a crontab entry names a controller or "
                     "scheduler daemon (%s); the design is no-daemon, the "
                     "sole recurring podcast cron is the daily smoke test"
                     % daemon_line)
        no_poller = False
    else:
        parts.append("no-poller OK: no crontab entry names a controller or "
                     "scheduler daemon")
        no_poller = True
    if secrets_ok and no_poller:
        out.append(_result("B5", "intake env secrets present and no poller",
                           PASS, "; ".join(parts)))
    else:
        out.append(_result("B5", "intake env secrets present and no poller",
                           FAIL, "; ".join(parts)))

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


# Route objects live in a MAP keyed by routeId (route-template.json5). The box
# config may carry JSON5 comments, so a strict json.loads is tried first and a
# tolerant scan is the fallback. Only route ids, sessionKey, and controllerId
# are ever extracted; secret values are never parsed, stored, or printed.
_ROUTE_KEY_RE = re.compile(
    r'"(podcast-intake-[A-Za-z0-9][A-Za-z0-9._-]*)"\s*:\s*\{')
# JSON5 allows bare keys; strict JSON quotes them. Values are always quoted.
_FIELD_RE = r'["\']?%s["\']?\s*:\s*"([^"]*)"'


def scan_route_shapes(text):
    """Return {route_id: {"sessionKey": str_or_None, "controllerId":
    str_or_None}} for every podcast-intake-<slug> route declared in text."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        data = None
    if isinstance(data, dict):
        routes = (data.get("plugins", {}).get("entries", {})
                      .get("webhooks", {}).get("config", {}).get("routes"))
        if isinstance(routes, dict):
            shapes = {}
            for rid, obj in routes.items():
                if not (isinstance(rid, str)
                        and rid.startswith(ROUTE_ID_PREFIX)):
                    continue
                if not isinstance(obj, dict):
                    obj = {}
                shapes[rid] = {
                    "sessionKey": obj.get("sessionKey"),
                    "controllerId": obj.get("controllerId"),
                }
            return shapes
    # JSON5 fallback: for each route id, scan the window from the route's
    # opening brace to the next podcast route key (or end of text). Nested
    # objects (the secret SecretRef) ride inside the window; only the two
    # field names above are ever matched.
    shapes = {}
    matches = list(_ROUTE_KEY_RE.finditer(text))
    for i, m in enumerate(matches):
        rid = m.group(1)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        window = text[m.end():end]
        shape = {}
        for field in ("sessionKey", "controllerId"):
            fm = re.search(_FIELD_RE % field, window)
            shape[field] = fm.group(1) if fm else None
        shapes[rid] = shape
    return shapes


def _python_bin():
    """Python used to probe the step driver (--help). Mirrors the skill's
    `#!/usr/bin/env python3` shebang resolution; overridable for tests via
    $PODCAST_STEP_DRIVER_PY (e.g. a venv python)."""
    return os.environ.get("PODCAST_STEP_DRIVER_PY") or sys.executable


def _crontab_lines():
    """crontab listing, bounded. An absent crontab yields an empty listing,
    never an error (the $PODCAST_CRONTAB_BIN seam points tests at a stub)."""
    crontab_bin = os.environ.get("PODCAST_CRONTAB_BIN", "crontab")
    try:
        proc = subprocess.run([crontab_bin, "-l"], capture_output=True,
                              text=True, timeout=15)
        return proc.stdout.splitlines() if proc.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        return []


def _cron_daemon_line():
    """No-daemon doctrine: the design has NO controller daemon and NO poller
    scheduler, so no crontab entry may name one. Returns the offending line
    (comments excluded) or None when clean."""
    for line in _crontab_lines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if any(n in stripped for n in DAEMON_NAME_NEEDLES):
            return stripped
    return None


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
    ap.add_argument("--handler-script", default=DEFAULT_HANDLER_SCRIPT)
    ap.add_argument("--installer-script", default=DEFAULT_INSTALLER_SCRIPT)
    ap.add_argument("--driver-script", default=DEFAULT_DRIVER_SCRIPT,
                    help="skill-root-relative path to the deterministic step "
                         "driver (default: scripts/podcast_step_driver.py)")
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
                               args.handler_script, args.installer_script,
                               args.driver_script)
    if args.repo_only:
        fatal, warn, skip = classify(repo_results, [], False, False)
        return emit(repo_results, fatal, warn, skip, "repo-only",
                    args.json, repo_root)

    box_results = box_checks(skill_root, args.agents_root, args.gateway_url,
                             slugs, args.timeout, args.hook_script,
                             args.handler_script, args.installer_script,
                             args.driver_script)
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
        (scripts / "webhook").mkdir(parents=True, exist_ok=True)
        if with_files:
            (scripts / "register-podcast-hook.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
            (scripts / "webhook" / "intake_handler.py").write_text(
                "#!/usr/bin/env python3\n# deterministic first step of the "
                "controllerId runbook\n")
            (scripts / "install-podcast-department.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
            (scripts / "podcast_step_driver.py").write_text(
                "#!/usr/bin/env python3\nimport sys\n"
                "print('podcast_step_driver stub')\nsys.exit(0)\n")
        return root / "58-podcast-production-engine"

    print("== self-test: repo presence ==")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        skill = make_skill(root, with_files=True)
        res = repo_checks(skill, DEFAULT_HOOK_SCRIPT, DEFAULT_HANDLER_SCRIPT,
                          DEFAULT_INSTALLER_SCRIPT, DEFAULT_DRIVER_SCRIPT)
        check("all-present-passes", all(r["status"] == PASS for r in res))
        (skill / DEFAULT_HANDLER_SCRIPT).unlink()
        res = repo_checks(skill, DEFAULT_HOOK_SCRIPT, DEFAULT_HANDLER_SCRIPT,
                          DEFAULT_INSTALLER_SCRIPT, DEFAULT_DRIVER_SCRIPT)
        check("missing-handler-fails",
              any(r["status"] == FAIL for r in res))
        check("fail-detail-names-the-file",
              any("intake_handler.py" in r["detail"] for r in res if r["status"] == FAIL))
        check("driver-present-pass", any(
            r["id"] == "R4" and r["status"] == PASS for r in res))
        (skill / DEFAULT_DRIVER_SCRIPT).unlink()
        res = repo_checks(skill, DEFAULT_HOOK_SCRIPT, DEFAULT_HANDLER_SCRIPT,
                          DEFAULT_INSTALLER_SCRIPT, DEFAULT_DRIVER_SCRIPT)
        check("missing-driver-fails",
              any(r["id"] == "R4" and r["status"] == FAIL for r in res))

    print("== self-test: route-shape scan (JSON5 tolerant, no secrets) ==")
    json5 = """
    {
      // a comment
      plugins: {
        entries: {
          webhooks: {
            config: {
              routes: {
                "podcast-intake-acme-media": {
                  enabled: true,
                  sessionKey: "podcast:intake:acme-media",
                  controllerId: "webhooks/podcast-intake-acme-media",
                  secret: { source: "env", id: "PODCAST_INTAKE_HOOK_SECRET" }
                },
                "other-skill-route": { enabled: true }
              }
            }
          }
        }
      }
    }
    """
    shapes = scan_route_shapes(json5)
    check("json5-route-found", "podcast-intake-acme-media" in shapes)
    check("json5-session-key", shapes.get("podcast-intake-acme-media", {})
          .get("sessionKey") == "podcast:intake:acme-media")
    check("json5-controller-id", shapes.get("podcast-intake-acme-media", {})
          .get("controllerId") == "webhooks/podcast-intake-acme-media")
    check("foreign-route-ignored", "other-skill-route" not in shapes)
    strict_json = json.dumps({"plugins": {"entries": {"webhooks": {"config": {
        "routes": {"podcast-intake-zeta": {
            "sessionKey": "podcast:intake:zeta",
            "controllerId": "webhooks/podcast-intake-zeta"}}}}}}})
    zshapes = scan_route_shapes(strict_json)
    check("strict-json-route-found",
          zshapes.get("podcast-intake-zeta", {}).get("controllerId")
          == "webhooks/podcast-intake-zeta")
    check("garbage-scans-empty", scan_route_shapes("nothing here") == {})

    print("== self-test: no-poller crontab scan ==")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cronbin = root / "fake-crontab.sh"
        cronbin.write_text("#!/usr/bin/env bash\n"
                           "echo '*/5 * * * * python3 .../podcast_controller.py run-once'\n")
        os.chmod(cronbin, 0o755)
        os.environ["PODCAST_CRONTAB_BIN"] = str(cronbin)
        try:
            check("daemon-cron-line-flagged",
                  _cron_daemon_line() is not None)
        finally:
            os.environ.pop("PODCAST_CRONTAB_BIN", None)
        with tempfile.TemporaryDirectory() as td2:
            root2 = Path(td2)
            cronbin2 = root2 / "fake-crontab.sh"
            cronbin2.write_text("#!/usr/bin/env bash\n"
                                "echo '# podcast_controller.py is dead by design'\n"
                                "echo '0 6 * * * openclaw cron ... podcast-smoke-test.py'\n")
            os.chmod(cronbin2, 0o755)
            os.environ["PODCAST_CRONTAB_BIN"] = str(cronbin2)
            try:
                check("clean-crontab-passes", _cron_daemon_line() is None)
            finally:
                os.environ.pop("PODCAST_CRONTAB_BIN", None)

    print("== self-test: on-box checks on a fake tree ==")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        skill = make_skill(root, with_files=True)
        agents = root / "agents" / DEPT_AGENT_DIRNAME
        agents.mkdir(parents=True)
        (agents / "agent.md").write_text("podcast department agent\n")
        # fake crontab seam: a clean listing (smoke cron only, no poller)
        cronbin = root / "fake-crontab.sh"
        cronbin.write_text("#!/usr/bin/env bash\n"
                           "echo '0 6 * * * openclaw cron fire podcast-smoke-test.py'\n")
        os.chmod(cronbin, 0o755)
        os.environ["PODCAST_CRONTAB_BIN"] = str(cronbin)
        os.environ["PODCAST_LAUNCHD_DIR"] = str(root / "no-such-dir")
        # Pin the box config away from any real machine state (hermetic).
        os.environ["OPENCLAW_CONFIG"] = str(root / "no-such-openclaw.json")
        try:
            res = box_checks(skill, str(root / "agents"), "http://127.0.0.1:1",
                             ["acme-media"], 1, DEFAULT_HOOK_SCRIPT,
                             DEFAULT_HANDLER_SCRIPT, DEFAULT_INSTALLER_SCRIPT,
                             DEFAULT_DRIVER_SCRIPT)
            by_id = {r["id"]: r for r in res}
            check("B1-installed-passes", by_id["B1"]["status"] == PASS)
            check("B2-agent-dir-passes", by_id["B2"]["status"] == PASS)
            check("B3-unreachable-gateway-fails", by_id["B3"]["status"] == FAIL)
            check("B4-missing-config-fails-with-slugs", by_id["B4"]["status"] == FAIL)
            check("B5-missing-secrets-fails", by_id["B5"]["status"] == FAIL)
            check("B5-detail-names-the-secret",
                  "PODCAST_INTAKE_HOOK_SECRET NOT-SET" in by_id["B5"]["detail"])
            check("B5-no-poller-ok-in-detail",
                  "no-poller OK" in by_id["B5"]["detail"])
            check("B6-driver-callable-passes", by_id["B6"]["status"] == PASS)
            # secrets both set: B5 flips to PASS
            os.environ["PODCAST_INTAKE_HOOK_SECRET"] = "sandbox-not-a-real-secret"
            os.environ["PODCAST_INTAKE_INBOUND_SECRET"] = "sandbox-not-a-real-secret"
            try:
                res2 = box_checks(skill, str(root / "agents"),
                                  "http://127.0.0.1:1", ["acme-media"], 1,
                                  DEFAULT_HOOK_SCRIPT, DEFAULT_HANDLER_SCRIPT,
                                  DEFAULT_INSTALLER_SCRIPT, DEFAULT_DRIVER_SCRIPT)
                by_id2 = {r["id"]: r for r in res2}
                check("B5-secrets-present-passes", by_id2["B5"]["status"] == PASS)
            finally:
                os.environ.pop("PODCAST_INTAKE_HOOK_SECRET", None)
                os.environ.pop("PODCAST_INTAKE_INBOUND_SECRET", None)
        finally:
            os.environ.pop("PODCAST_CRONTAB_BIN", None)
            os.environ.pop("PODCAST_LAUNCHD_DIR", None)
            os.environ.pop("OPENCLAW_CONFIG", None)

    print("== self-test: B4 route binding shape ==")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        skill = make_skill(root, with_files=True)
        config = root / "openclaw.json"
        config.write_text(json.dumps({
            "plugins": {"entries": {"webhooks": {"config": {"routes": {
                "podcast-intake-acme-media": {
                    "sessionKey": "podcast:intake:acme-media",
                    "controllerId": "webhooks/podcast-intake-acme-media"},
                "podcast-intake-zeta-corp": {
                    "sessionKey": "podcast:intake:WRONG",
                    "controllerId": "webhooks/podcast-intake-zeta-corp"}}}}}}}))
        cronbin = root / "fake-crontab.sh"
        cronbin.write_text("#!/usr/bin/env bash\nexit 0\n")
        os.chmod(cronbin, 0o755)
        os.environ["PODCAST_CRONTAB_BIN"] = str(cronbin)
        os.environ["OPENCLAW_CONFIG"] = str(config)
        os.environ["PODCAST_INTAKE_HOOK_SECRET"] = "sandbox-not-a-real-secret"
        os.environ["PODCAST_INTAKE_INBOUND_SECRET"] = "sandbox-not-a-real-secret"
        try:
            res = box_checks(skill, str(root / "agents"),
                             "http://127.0.0.1:1", ["acme-media"], 1,
                             DEFAULT_HOOK_SCRIPT, DEFAULT_HANDLER_SCRIPT,
                             DEFAULT_INSTALLER_SCRIPT, DEFAULT_DRIVER_SCRIPT)
            by_id = {r["id"]: r for r in res}
            check("B4-correct-shape-passes", by_id["B4"]["status"] == PASS)
            res = box_checks(skill, str(root / "agents"),
                             "http://127.0.0.1:1", ["zeta-corp"], 1,
                             DEFAULT_HOOK_SCRIPT, DEFAULT_HANDLER_SCRIPT,
                             DEFAULT_INSTALLER_SCRIPT, DEFAULT_DRIVER_SCRIPT)
            by_id = {r["id"]: r for r in res}
            check("B4-wrong-session-key-fails", by_id["B4"]["status"] == FAIL)
            check("B4-detail-names-the-route",
                  "podcast-intake-zeta-corp" in by_id["B4"]["detail"])
        finally:
            os.environ.pop("PODCAST_CRONTAB_BIN", None)
            os.environ.pop("OPENCLAW_CONFIG", None)
            os.environ.pop("PODCAST_INTAKE_HOOK_SECRET", None)
            os.environ.pop("PODCAST_INTAKE_INBOUND_SECRET", None)

    print("== self-test: severity model ==")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        skill = make_skill(root, with_files=True)
        repo_res = repo_checks(skill, DEFAULT_HOOK_SCRIPT,
                               DEFAULT_HANDLER_SCRIPT, DEFAULT_INSTALLER_SCRIPT,
                               DEFAULT_DRIVER_SCRIPT)
        box_fail = [_result("B3", "gateway", FAIL, "unreachable")]
        fatal, warn, _skip = classify(repo_res, box_fail, strict=False, provisioned=False)
        check("unprovisioned-box-finding-is-warn", fatal == [] and len(warn) == 1)
        fatal, warn, _skip = classify(repo_res, box_fail, strict=True, provisioned=False)
        check("strict-makes-box-finding-fatal", len(fatal) == 1)
        fatal, warn, _skip = classify(repo_res, box_fail, strict=False, provisioned=True)
        check("provisioned-makes-box-finding-fatal", len(fatal) == 1)
        (skill / DEFAULT_HOOK_SCRIPT).unlink()
        repo_res = repo_checks(skill, DEFAULT_HOOK_SCRIPT,
                               DEFAULT_HANDLER_SCRIPT, DEFAULT_INSTALLER_SCRIPT,
                               DEFAULT_DRIVER_SCRIPT)
        fatal, warn, _skip = classify(repo_res, [], strict=False, provisioned=False)
        check("repo-missing-always-fatal", len(fatal) == 1)

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
