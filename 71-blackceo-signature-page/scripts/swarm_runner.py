#!/usr/bin/env python3
"""Skill 71 swarm runner (fix plan Item 21; spec: references/swarm-plan.md).

Schedules a run's items as a DAG across worker sessions, bounded by a runner
profile (references/runner-profiles.json), and closes items and stages only
through scripts/stage_gate.py, only from OBSERVED results: validator exit
codes, output files on disk, review files stamped by scripts/write_review.py
from the reviewing worker's own session. Worker self-report is never a
receipt; workers write artifacts and notes, the runner and the gate record
everything else.

Non-goal, stated plainly: the runner makes no creative decisions and writes
no creative content. It schedules, validates, retries by failure class, and
records.

Key mechanics:
- Item DAG from references/stage-contract.json. Itemized stages (Item 20)
  get one work node and one review node per inventory item; a generation
  item depends only on ITS prompt item's review node, never on the prompt
  stage closing (the weld cut). Stage-close nodes are the fan-in.
- KIE token bucket: 20 createTask starts per 10 seconds per KIE account,
  shared by every runner on the box through a persisted state file guarded
  by a lockfile. The runner never calls KIE itself; Skill 74 transports.
  Generation attempts (first tries and retries alike) take a token before
  the worker starts.
- Failure classes are decided BEFORE an item's single retry is spent:
  validation returns to the author lane with the validator output attached;
  transport first reads the item's Skill 74 receipts (a success receipt
  with the image on disk completes the item with no resubmission; a
  submitted task is polled, never resubmitted); timeout retries once in the
  retry lane. After the retry, the item is blocked through the gate with a
  named reason and a recorded escalation; all other items continue.
- Capability-aware readiness (Amendment 6): an item whose capability
  (render, transport) is absent under the active profile waits; the runner
  declares the sequential fallback in the run record instead of failing it.
- Reviewer assignment is matched to the item's review criteria class and
  recorded per item in private/runner-state.json.

Usage:
  swarm_runner.py <run_dir> [--stages a,b] [--profile NAME]
                  [--profile-file PATH] [--runtime NAME] [--worker-cmd TPL]
                  [--max-items N] [--kie-limiter PATH]
                  [--timeout-work S] [--timeout-review S]
                  [--timeout-generation S]

Exit codes: 0 = every in-scope stage closed, no blocked items;
1 = run finished with blocked items or unclosed stages (all named);
2 = usage or configuration error (for example a runtime with no documented
spawn contract in references/runtime-adapters.md).
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
GATE = SKILL_ROOT / "scripts" / "stage_gate.py"
WRITE_REVIEW = SKILL_ROOT / "scripts" / "write_review.py"
PROFILES_FILE = SKILL_ROOT / "references" / "runner-profiles.json"
BRIEFS_DIR = SKILL_ROOT / "references" / "swarm-briefs"
DEFAULT_CONTRACT = SKILL_ROOT / "references" / "stage-contract.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser_sessions  # Item 33 session registry (scripts/browser_sessions.py)

# Item 33: for browser-using stages (contract flag "uses_browser": true)
# the runner is the launching wrapper: it registers one session per work
# node at spawn and closes it when the worker exits, on every exit path
# (see teardown_browser_sessions and the signal handlers in main). Engine
# and binding names are DRAFT-PENDING-LANDING (Amendment 5B; Skill 6
# draft PR #1990, not merged): the OpenClaw binding's primary engine is
# the OpenClaw Chrome extension, the Claude Code bindings ride the
# agent-browser CLI. The names are registry data; when Skill 6's text
# lands, only this table changes.
BROWSER_BINDINGS = {
    "openclaw": ("openclaw-chrome-extension", "openclaw"),
    "claude-code": ("agent-browser", "claude-code"),
    "claude-nine": ("agent-browser", "claude-code"),
    "generic-shell": ("agent-browser", "generic-shell"),
    "sequential": ("agent-browser", "sequential"),
}

ITEMIZED_STAGES = ("image-inventory-prompts", "image-generation-qc")
ITEM_FEEDS = {"image-generation-qc": "image-inventory-prompts"}
RENDER_STAGES = {"desktop-wireframe", "mobile-tablet", "visual-mockup",
                 "final-mockups"}
TRANSPORT_STAGES = {"image-generation-qc"}

# Spawn templates per runtime (references/runtime-adapters.md, "Swarm spawn
# contract"). A runtime with no entry here has no documented spawn contract
# and the runner refuses it. Placeholders: {brief} {note} {item} {stage}
# {kind} {run_dir}. The worker prints "SESSION: <id>" on stdout.
RUNTIME_TEMPLATES = {
    "generic-shell": None,  # requires --worker-cmd / SKILL71_WORKER_CMD
    "openclaw": "openclaw agent --local --session-id swarm-{stage}-{item} "
                "--message-file {brief}",
    "claude-nine": "claude --print --session-id swarm-{stage}-{item} "
                   "$(cat {brief})",
    "claude-code": "claude --print --session-id swarm-{stage}-{item} "
                   "$(cat {brief})",
    "sequential": None,  # same template machinery at concurrency 1
}

# Plan timeouts (seconds): prompt write 15m, prompt review 10m, image review
# 10m, wireframe part render 20m. Generation is bounded by Skill 74's own
# wait unless --timeout-generation is given.
TIMEOUTS = {
    ("image-inventory-prompts", "work"): 15 * 60,
    ("image-inventory-prompts", "review"): 10 * 60,
    ("image-generation-qc", "review"): 10 * 60,
}
RENDER_TIMEOUT = 20 * 60
DEFAULT_WORK_TIMEOUT = 15 * 60
DEFAULT_REVIEW_TIMEOUT = 10 * 60

CRITERIA_CLASS = {
    "image-inventory-prompts": "image-fidelity",
    "image-generation-qc": "image-fidelity",
    "copy": "copy",
    "desktop-wireframe": "layout",
    "mobile-tablet": "layout",
    "visual-mockup": "layout",
    "final-mockups": "layout",
    "responsive-html": "layout",
}
REVIEW_BRIEFS = {
    ("image-inventory-prompts", "image-fidelity"): "prompt-reviewer.md",
    ("image-generation-qc", "image-fidelity"): "image-reviewer.md",
}
WORK_BRIEFS = {
    "image-inventory-prompts": "prompt-author.md",
    "image-generation-qc": "generation-operator.md",
    "desktop-wireframe": "wireframe-renderer.md",
    "mobile-tablet": "wireframe-renderer.md",
    "visual-mockup": "wireframe-renderer.md",
    "final-mockups": "wireframe-renderer.md",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def item_number(item_id):
    m = re.search(r"(\d+)\s*$", str(item_id))
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------
# Clocks (the token bucket's pacing is testable with a simulated clock)

class SystemClock:
    def now(self):
        return time.time()

    def sleep(self, seconds):
        time.sleep(seconds)


class FakeClock:
    """Simulated clock for tests: sleep() advances instantly."""

    def __init__(self, start=1000.0):
        self.t = float(start)

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += max(0.0, seconds)


# --------------------------------------------------------------------------
# KIE token bucket: 20 starts per 10 seconds per account, persisted, shared.

class TokenBucket:
    LIMIT = 20
    WINDOW = 10.0

    def __init__(self, state_path, clock=None):
        self.path = Path(state_path)
        self.clock = clock or SystemClock()

    def _lock(self):
        lock = self.path.with_suffix(self.path.suffix + ".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        deadline = self.clock.now() + 120.0
        while True:
            try:
                fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return lock
            except FileExistsError:
                if self.clock.now() > deadline:
                    raise TimeoutError(f"kie limiter lock held >120s: {lock}")
                self.clock.sleep(0.05)

    def _unlock(self, lock):
        try:
            lock.unlink()
        except FileNotFoundError:
            pass

    def _grants(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [float(x) for x in data.get("grants", [])]
        except Exception:
            return []

    def _prune(self, grants, now):
        return [g for g in grants if now - g < self.WINDOW]

    def try_acquire(self):
        lock = self._lock()
        try:
            now = self.clock.now()
            grants = self._prune(self._grants(), now)
            if len(grants) >= self.LIMIT:
                return False
            grants.append(now)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"grants": grants}), encoding="utf-8")
            return True
        finally:
            self._unlock(lock)

    def consume(self):
        """Block (on the injected clock) until a start slot is granted."""
        while not self.try_acquire():
            lock = self._lock()
            try:
                grants = self._prune(self._grants(), self.clock.now())
                wait_s = (grants[0] + self.WINDOW - self.clock.now()) if grants else self.WINDOW
            finally:
                self._unlock(lock)
            self.clock.sleep(max(0.01, wait_s))


# --------------------------------------------------------------------------
# Runner profiles: detection, per-host override, clamps (Amendment 1).

def probe_host(env):
    cgroup = ""
    try:
        cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    container = Path("/.dockerenv").exists() or any(
        marker in cgroup for marker in ("docker", "containerd", "kubepods"))
    mem_limit = None
    try:
        raw = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        if raw != "max":
            mem_limit = int(raw)
    except (OSError, ValueError):
        pass
    cpu_limit = None
    try:
        raw = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if raw and raw[0] != "max":
            cpu_limit = int(raw[0]) / int(raw[1])  # quota / period = cores
    except (OSError, ValueError, IndexError):
        pass
    return {"container": container,
            "os": sys.platform,
            "fleet_shape": env.get("FLEET_SHAPE", ""),
            "cgroup_mem_bytes": mem_limit,
            "cgroup_cpu_cores": cpu_limit,
            "os_cpus": os.cpu_count() or 1,
            "os_mem_bytes": None}


def resolve_profile(env=None, probe=None, profiles_data=None, cli_name=None):
    """Returns (profile_dict, evidence_dict). Resolution: explicit name, then
    the per-host override file (<openclaw-data>/skill71-runner-profile.json),
    then deterministic detection, then checked-in defaults. Unknown
    containers default to fleet-contabo and log the assumption loudly."""
    env = env or os.environ
    probe = probe or probe_host(env)
    data = profiles_data or json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
    profiles = data["profiles"]
    defaults = data.get("defaults", {})
    evidence = {"probe": {k: v for k, v in probe.items()}, "clamps": [],
                "assumptions": []}
    openclaw_data = Path(env.get("OPENCLAW_DATA_DIR", str(Path.home() / ".openclaw")))
    override = {}
    override_path = openclaw_data / "skill71-runner-profile.json"
    if override_path.exists():
        try:
            override = json.loads(override_path.read_text(encoding="utf-8"))
        except Exception:
            override = {}
        evidence["override_file"] = str(override_path)
    name = cli_name or env.get("SKILL71_RUNNER_PROFILE") or override.get("profile")
    if name and Path(str(name)).exists():
        loaded = json.loads(Path(str(name)).read_text(encoding="utf-8"))
        if "profiles" in loaded:  # a full profiles file: keep its first entry
            data = loaded
            profiles = loaded["profiles"]
            name = sorted(profiles)[0]
        else:
            override = {**override, **loaded}
            name = override.get("profile")
    if not name:
        if probe["container"]:
            shape = probe.get("fleet_shape") or ""
            if shape in profiles:
                name = shape
            else:
                name = "fleet-contabo"
                evidence["assumptions"].append(
                    "container detected without a recognized FLEET_SHAPE; "
                    "defaulting to the fleet-contabo profile (Amendment 1)")
        elif probe["os"] == "darwin":
            name = "fleet-mac"
        else:
            name = "fleet-hostinger"
    if name not in profiles:
        raise ValueError(f"unknown runner profile {name!r}; "
                         f"known: {sorted(profiles)}")
    merged = json.loads(json.dumps(profiles[name]))  # deep copy
    merged["capabilities"] = {**defaults.get("capabilities", {}),
                              **merged.get("capabilities", {})}
    merged.setdefault("disk_soft_cap_bytes",
                      defaults.get("disk_soft_cap_bytes", 5 * 1024 ** 3))
    over_settings = {k: v for k, v in override.items() if k != "profile"}
    for key, value in over_settings.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    for cap, val in list(env.items()):
        if cap.startswith("SKILL71_CAPABILITY_"):
            merged["capabilities"][cap[len("SKILL71_CAPABILITY_"):].lower()] = (
                val.strip().lower() not in ("absent", "false", "0", "no"))
    # Clamps (Amendment 1 numbers only).
    mem = probe.get("cgroup_mem_bytes")
    if mem:
        if mem < 6 * 1024 ** 3 and merged["max_workers"] > 4:
            merged["max_workers"] = 4
            evidence["clamps"].append("cgroup memory < 6 GiB: max_workers <= 4")
        if mem < 4 * 1024 ** 3:
            if merged["max_workers"] > 2:
                merged["max_workers"] = 2
            if merged["reviewers"] > 1:
                merged["reviewers"] = 1
            merged["image_qc_sequential"] = True
            evidence["clamps"].append(
                "cgroup memory < 4 GiB: max_workers <= 2, reviewers <= 1, "
                "image QC sequential")
        merged["playwright_instances"] = 1
    cpus = probe.get("cgroup_cpu_cores") or probe.get("os_cpus") or 1
    pw_cap = max(1, int(cpus) // 4)
    if merged.get("playwright_instances", 1) > pw_cap:
        merged["playwright_instances"] = pw_cap
        evidence["clamps"].append(
            f"playwright_instances capped at floor(cpus/4) = {pw_cap}")
    if probe.get("cgroup_cpu_cores"):
        # The 80 percent Contabo CPU planning ceiling, operationalized: when
        # a finite container CPU limit exists, plan workers against 80
        # percent of it.
        plan = max(1, int(0.8 * probe["cgroup_cpu_cores"]))
        merged["cpu_plan_cores"] = plan
        if merged["max_workers"] > plan:
            merged["max_workers"] = plan
            evidence["clamps"].append(
                f"80 percent CPU planning ceiling: max_workers <= {plan} "
                f"of {probe['cgroup_cpu_cores']:g} limited cores")
    merged["name"] = name
    evidence["resolved_profile"] = name
    return merged, evidence


def limiter_path_for(profile, env, cli_path=None):
    if cli_path:
        return Path(cli_path)
    if env.get("KIE_ACCOUNT_LOCK"):
        return Path(env["KIE_ACCOUNT_LOCK"])
    openclaw_data = env.get("OPENCLAW_DATA_DIR", str(Path.home() / ".openclaw"))
    tpl = profile.get("kie_limiter_path", "{openclaw_data}/locks/kie-account.json")
    return Path(tpl.replace("{openclaw_data}", openclaw_data)
                   .replace("{shared}", "/skill71-shared")
                   .replace("{run_dir}", "."))


# --------------------------------------------------------------------------
# Graph

def load_contract(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def item_universe(run_dir, contract, stage):
    spec = contract["stages"][stage]
    rel = spec.get("count_of")
    if not rel:
        return []
    path = run_dir / rel
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    entries = data if isinstance(data, list) else []
    if isinstance(data, dict):
        for key in ("images", "inventory", "entries", "slots"):
            if isinstance(data.get(key), list):
                entries = data[key]
                break
    ids = []
    for e in entries:
        if isinstance(e, dict) and e.get("id"):
            ids.append(str(e["id"]))
        elif isinstance(e, str):
            ids.append(e)
    return ids


def expected_item_artifact(contract, stage, item_id):
    spec = contract["stages"][stage]
    pattern = spec.get("per_file_glob") or ""
    num = item_number(item_id)
    if num is None:
        return None
    base = Path(pattern).name
    prefix, _, suffix = base.partition("*")
    stem = item_id if item_id.startswith(prefix) else f"{prefix}{num:03d}"
    return str(Path(pattern).parent / f"{stem}{suffix}")


def expected_stage_outputs(contract, stage):
    outs = []
    for art in contract["stages"][stage].get("artifacts", []):
        glob = art["glob"]
        if "*" in glob:
            for i in range(1, art.get("min_count", 1) + 1):
                outs.append(glob.replace("*", f"{i:02d}"))
        else:
            outs.append(glob)
    return outs


def criteria_class(stage):
    return CRITERIA_CLASS.get(stage, "generic")


def review_brief_for(stage):
    cls = criteria_class(stage)
    return REVIEW_BRIEFS.get((stage, cls), "generic-reviewer.md")


def build_graph(run_dir, contract, stages):
    """Nodes: id -> dict(kind, stage, item, deps, capability)."""
    order = contract["stage_order"]
    scope = [s for s in order if s in stages]
    nodes = {}

    def nid(stage, kind, item):
        return f"{stage}:{kind}:{item}"

    for stage in scope:
        spec = contract["stages"][stage]
        dep_closes = [nid(d, "stageclose", "stage")
                      for d in spec.get("depends_on", []) if d in scope]
        if stage in ITEMIZED_STAGES:
            items = item_universe(run_dir, contract, stage)
            review_nodes = []
            for item in items:
                work_deps = list(dep_closes)
                if stage in ITEM_FEEDS:
                    upstream = ITEM_FEEDS[stage]
                    work_deps = [nid(upstream, "review", item)] if upstream in scope else []
                    cap = "transport"
                else:
                    cap = None
                nodes[nid(stage, "work", item)] = {
                    "kind": "work", "stage": stage, "item": item,
                    "deps": work_deps, "capability": cap}
                if spec.get("review_required") or spec.get("min_scores"):
                    nodes[nid(stage, "review", item)] = {
                        "kind": "review", "stage": stage, "item": item,
                        "deps": [nid(stage, "work", item)], "capability": None}
                    review_nodes.append(nid(stage, "review", item))
                else:
                    review_nodes.append(nid(stage, "work", item))
            nodes[nid(stage, "stageclose", "stage")] = {
                "kind": "stageclose", "stage": stage, "item": "stage",
                "deps": review_nodes + dep_closes, "capability": None}
        else:
            cap = "render" if stage in RENDER_STAGES else None
            nodes[nid(stage, "work", "stage")] = {
                "kind": "work", "stage": stage, "item": "stage",
                "deps": dep_closes, "capability": cap}
            last = nid(stage, "work", "stage")
            if spec.get("review_required") or spec.get("min_scores"):
                nodes[nid(stage, "review", "stage")] = {
                    "kind": "review", "stage": stage, "item": "stage",
                    "deps": [last], "capability": None}
                last = nid(stage, "review", "stage")
            nodes[nid(stage, "stageclose", "stage")] = {
                "kind": "stageclose", "stage": stage, "item": "stage",
                "deps": [last] + dep_closes, "capability": None}
    return nodes


# --------------------------------------------------------------------------
# The runner

class Runner:
    def __init__(self, run_dir, contract_path, profile, evidence, runtime,
                 worker_cmd, stages=None, clock=None, limiter_path=None,
                 timeout_overrides=None, max_items=None):
        self.run_dir = Path(run_dir)
        self.contract_path = Path(contract_path)
        self.contract = load_contract(contract_path)
        self.profile = profile
        self.evidence = evidence
        self.runtime = runtime
        self.worker_cmd = worker_cmd
        self.clock = clock or SystemClock()
        self.bucket = TokenBucket(limiter_path, self.clock) if limiter_path else None
        self.timeouts = dict(timeout_overrides or {})
        self.max_items = max_items
        order = self.contract["stage_order"]
        self.stages = stages or list(order)
        self.nodes = build_graph(self.run_dir, self.contract, set(self.stages))
        self.state_path = self.run_dir / "private" / "runner-state.json"
        self.log_path = self.run_dir / "private" / "runner-log.jsonl"
        self.state = self._load_state()
        self.fallback_declared = self.state.get("fallback", {}).get("declared", False)
        self._browser_open = set()  # Item 33: sessions this runner opened

    # -- state -------------------------------------------------------------
    def _load_state(self):
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state["updated_at"] = now_iso()
        self.state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def log(self, event, **kw):
        rec = {"event": event, "at": now_iso(), **kw}
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")

    def node_state(self, nid):
        return self.state.setdefault("nodes", {}).setdefault(
            nid, {"status": "pending", "attempts": []})

    # -- gate --------------------------------------------------------------
    def gate(self, *args):
        env = {**os.environ, "STAGE_GATE_CONTRACT": str(self.contract_path)}
        proc = subprocess.run([sys.executable, str(GATE), *[str(a) for a in args]],
                              text=True, capture_output=True, env=env)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")

    def gate_state(self):
        path = self.run_dir / "private" / "state.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def item_closed_in_gate(self, stage, item):
        if item == "stage":
            return self.gate_state().get("stages", {}).get(stage, {}).get("status") == "closed"
        return (self.gate_state().get("items", {}).get(stage, {})
                .get(item, {}).get("status") == "closed")

    # -- browser sessions (Item 33) --------------------------------------
    def stage_uses_browser(self, stage):
        return bool(self.contract["stages"].get(stage, {}).get("uses_browser"))

    def _is_gate_owned_output(self, stage, rel):
        # Item 33: the hygiene receipt is written by the gate's reaper
        # pass at close, never by the worker, so it is not a worker
        # output. The stage close still requires it as a contract
        # artifact; the pass is what satisfies it.
        return (self.stage_uses_browser(stage)
                and rel == f"{stage}/{browser_sessions.RECEIPT_NAME}")

    def _client_slug(self):
        intake = self.run_dir / "intake.json"
        try:
            data = json.loads(intake.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        slug = data.get("client_slug") or data.get("brand_owner") or "client"
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(slug)).strip("-") or "client"

    def _run_ref(self):
        run_id = self.gate_state().get("run_id")
        return str(run_id) if run_id else self.run_dir.name

    def browser_session_open(self, node):
        """Register the work node's session (launching-wrapper duty,
        Item 33 HOW 1). The session name carries client slug, run ref,
        and stage, per the Browser Engine Contract."""
        engine, binding = BROWSER_BINDINGS.get(
            self.runtime, ("agent-browser", self.runtime))
        name = f"{self._client_slug()}-{self._run_ref()}-{node['stage']}"
        if node["item"] != "stage":
            name += f"-{node['item']}"
        name = re.sub(r"[^A-Za-z0-9_.-]+", "-", name)
        browser_sessions.register_open(
            self.run_dir, session_name=name, stage=node["stage"],
            engine=engine, binding=binding, unit="session",
            client_slug=self._client_slug(), run_id=self._run_ref(),
            via="swarm-runner")
        self._browser_open.add(name)
        self.log("browser_session_opened", session=name, stage=node["stage"],
                 item=node["item"])
        return name

    def browser_session_close(self, name, via="runner-node-exit"):
        if name not in self._browser_open:
            return
        browser_sessions.register_close(self.run_dir, name,
                                        closed_by="normal", via=via)
        self._browser_open.discard(name)
        self.log("browser_session_closed", session=name, via=via)

    def teardown_browser_sessions(self, via="runner-shutdown"):
        """Teardown on every exit path the runner controls: run end,
        SIGTERM, SIGINT (handlers in main). A runner killed with SIGKILL
        cannot run this; its registry opens stay open and the gate's
        reaper pass accounts for them at the next check or close
        (Item 33 HOW 2)."""
        for name in sorted(self._browser_open):
            self.browser_session_close(name, via=via)

    # -- briefs ------------------------------------------------------------
    def render_brief(self, node, attempt=1, lane=None, extra_context=""):
        stage, kind, item = node["stage"], node["kind"], node["item"]
        spec = self.contract["stages"][stage]
        if kind == "review":
            template_name = review_brief_for(stage)
        elif lane == "transport-poll":
            template_name = "generation-poll.md"
        else:
            template_name = WORK_BRIEFS.get(stage, "generic-worker.md")
        template = (BRIEFS_DIR / template_name).read_text(encoding="utf-8")
        note_file = self.run_dir / "private" / "notes" / f"{stage}-{item}-{kind}.md"
        note_file.parent.mkdir(parents=True, exist_ok=True)
        if kind == "review":
            inputs = []
            art = (expected_item_artifact(self.contract, stage, item)
                   if item != "stage" else None)
            if art:
                inputs.append(f"- Artifact under review: {art}")
            inputs.append(f"- Scores file to write: {note_file}.scores.json")
            outputs = [f"{note_file}.scores.json"]
            validators = ["scripts/write_review.py (executed by the runner "
                          "with your session id)"]
            done = ["Scores JSON written with a verdict and an evidence note "
                    "of at least 40 characters per criterion."]
        else:
            if item != "stage":
                outputs = [expected_item_artifact(self.contract, stage, item)]
            else:
                outputs = expected_stage_outputs(self.contract, stage)
            inputs = [f"- Run folder: {self.run_dir}"]
            if self.stage_uses_browser(stage):
                inputs.append(
                    "- Browser work (Item 33): the runner has registered a "
                    "named session for this node in "
                    "private/browser-sessions.jsonl; do the browser work in "
                    "that session. Any session you launch yourself must be "
                    "registered at open via scripts/browser_sessions.py and "
                    "closed at teardown. A headed launch is a contract "
                    "violation recorded in the hygiene receipt.")
            if stage in ITEM_FEEDS and item != "stage":
                inputs.append("- Closed prompt: "
                              + str(expected_item_artifact(
                                  self.contract, ITEM_FEEDS[stage], item)))
            validators = list(spec.get("validators", [])) or ["gate:noop"]
            done = ["Every expected output exists on disk.",
                    "The stage validators pass against the outputs."]
        reads = [f"- {r}" for r in spec.get("reads", [])] or ["- (none declared)"]
        objective = (f"Stage {stage}, item {item}: "
                     f"{'review' if kind == 'review' else 'produce the expected outputs'} "
                     f"(attempt {attempt}).")
        text = (template
                .replace("{{objective}}", objective)
                .replace("{{inputs}}", "\n".join(inputs))
                .replace("{{reads}}", "\n".join(reads))
                .replace("{{outputs}}", "\n".join(f"- {o}" for o in outputs))
                .replace("{{validators}}", "\n".join(f"- {v}" for v in validators))
                .replace("{{done_criteria}}", "\n".join(f"- {d}" for d in done))
                .replace("{{note_file}}", str(note_file))
                .replace("{{item}}", str(item))
                .replace("{{stage}}", stage))
        if extra_context:
            text += "\n" + extra_context
        brief_path = (self.run_dir / "private" / "briefs" /
                      f"{stage}-{item}-{kind}-attempt{attempt}.md")
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(text, encoding="utf-8")
        return brief_path, note_file

    # -- workers -----------------------------------------------------------
    def spawn_worker(self, node, brief_path, note_file, timeout_s):
        cmd = self.worker_cmd
        values = {"brief": str(brief_path), "note": str(note_file),
                  "item": str(node["item"]), "stage": node["stage"],
                  "kind": node["kind"], "run_dir": str(self.run_dir)}
        for key, val in values.items():
            cmd = cmd.replace("{" + key + "}", val)
        argv = shlex.split(cmd)
        started = self.clock.now()
        try:
            proc = subprocess.run(argv, text=True, capture_output=True,
                                  timeout=timeout_s, cwd=str(self.run_dir))
            out = proc.stdout or ""
            session = None
            for line in out.splitlines():
                if line.startswith("SESSION:"):
                    session = line.split(":", 1)[1].strip()
            if not session:
                session = f"shell-{proc.pid}-{uuid.uuid4().hex[:8]}"
            return {"exit": proc.returncode, "session": session,
                    "stdout": out, "stderr": proc.stderr or "",
                    "timed_out": False, "started": started,
                    "finished": self.clock.now()}
        except subprocess.TimeoutExpired as exc:
            return {"exit": None, "session": f"shell-timeout-{uuid.uuid4().hex[:8]}",
                    "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
                    "stderr": "", "timed_out": True, "started": started,
                    "finished": self.clock.now()}

    def timeout_for(self, node):
        key = f"{node['stage']}:{node['kind']}"
        if key in self.timeouts:
            return self.timeouts[key]
        if node["stage"] in TRANSPORT_STAGES and node["kind"] == "work":
            return self.timeouts.get("generation")  # None = Skill 74 bounds it
        base = TIMEOUTS.get((node["stage"], node["kind"]))
        if base is None:
            base = (RENDER_TIMEOUT if node["stage"] in RENDER_STAGES
                    and node["kind"] == "work"
                    else DEFAULT_WORK_TIMEOUT if node["kind"] == "work"
                    else DEFAULT_REVIEW_TIMEOUT)
        mult = (self.profile.get("timeout_multipliers") or {}).get("render", 1.0)
        if node["stage"] in RENDER_STAGES:
            base = int(base * mult)
        return base

    # -- validators (observed results only) --------------------------------
    def run_validators_for(self, stage, artifact_rel):
        spec = self.contract["stages"][stage]
        failures = []
        for raw in spec.get("validators", []):
            if raw.strip() == "gate:noop":
                continue
            cmd = raw.replace("{run_dir}", str(self.run_dir)) \
                     .replace("{file}", str(self.run_dir / artifact_rel)) \
                     .replace("{brand}", str(self.run_dir / "private" / "brand.json")) \
                     .replace("{sauce}", "")
            argv = shlex.split(cmd)
            argv = [sys.executable if a == "python3" else a for a in argv]
            proc = subprocess.run(argv, text=True, capture_output=True,
                                  cwd=str(SKILL_ROOT))
            if proc.returncode != 0:
                failures.append(f"validator {raw!r} exited {proc.returncode}: "
                                f"{(proc.stdout + proc.stderr).strip()[:400]}")
        return failures

    # -- receipts ----------------------------------------------------------
    def ensure_stage_receipt(self, stage, session, started_iso, finished_iso,
                             artifacts):
        path = self.run_dir / "private" / "receipts" / f"{stage}.json"
        if path.exists():
            return
        receipt = {"stage": stage, "status": "pass",
                   "author_agent": "swarm-runner",
                   "author_session": session,
                   "started_at": started_iso, "finished_at": finished_iso,
                   "artifacts": artifacts}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    def kie74_receipt_for(self, artifact_rel):
        """The item's Skill 74 task receipt, found via saved_paths."""
        kdir = self.run_dir / "receipts" / "kie74"
        if not kdir.exists():
            return None
        for f in sorted(kdir.glob("*.json")):
            try:
                obj = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if artifact_rel in (obj.get("saved_paths") or []):
                return obj
        return None

    # -- capability / fallback ---------------------------------------------
    def capability_absent(self, node):
        cap = node.get("capability")
        if not cap:
            return None
        caps = self.profile.get("capabilities", {})
        if cap == "render" and not caps.get("render", True):
            return "render"
        if cap == "transport" and caps.get("image_transport", "active") != "active":
            return "transport"
        return None

    def declare_fallback(self, capability, node_ids, reason):
        if self.fallback_declared:
            return
        self.fallback_declared = True
        decl = {"declared": True, "runtime": self.runtime, "reason": reason,
                "items": node_ids, "capability": capability, "at": now_iso(),
                "mode": "sequential-fallback"}
        self.state["fallback"] = decl
        path = self.run_dir / "private" / "runner-fallback.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(decl, indent=2), encoding="utf-8")
        self.state["swarm_mode"] = "sequential-fallback"
        self.log("fallback_declared", capability=capability, items=node_ids)
        self.save_state()

    def disk_over_cap(self):
        cap = self.profile.get("disk_soft_cap_bytes")
        if not cap:
            return None
        total = 0
        for root, _dirs, files in os.walk(self.run_dir):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    pass
        return total if total > cap else None

    # -- node execution ------------------------------------------------------
    def block_node(self, nid, node, reason, escalation):
        ns = self.node_state(nid)
        ns["status"] = "blocked"
        ns["blocked_reason"] = reason
        ns["escalation"] = escalation
        if node["item"] != "stage" and node["stage"] in ITEMIZED_STAGES:
            self.gate("block-item", self.run_dir, node["stage"], node["item"],
                      "--reason", reason)
        self.log("item_blocked", node=nid, reason=reason, escalation=escalation)
        self.save_state()

    def classify_and_maybe_complete(self, node, result, artifact_rel):
        """Decide the failure class BEFORE any retry is spent. Returns 'done'
        (observed results complete the item), 'poll' (transport retry lane:
        a submitted Skill 74 task exists and must be polled, never
        resubmitted), or 'retry_or_block' (with ns['next_lane'] and
        ns['retry_context'] set; the caller blocks when the retry is spent)."""
        nid = f"{node['stage']}:{node['kind']}:{node['item']}"
        ns = self.node_state(nid)
        if result["timed_out"]:
            partial = artifact_rel and (self.run_dir / artifact_rel).exists()
            if partial and not self.run_validators_for(node["stage"], artifact_rel):
                ns["completed_from"] = "observed partial outputs after timeout"
                return "done"
            ns["next_lane"] = "timeout"
            ns["retry_context"] = (
                "\n## Retry context (failure class: timeout)\n\n"
                "The previous attempt timed out with no valid partial outputs. "
                "Retry once in the retry lane.\n")
            return "retry_or_block"
        if result["exit"] == 2:
            receipt = self.kie74_receipt_for(artifact_rel) if artifact_rel else None
            if receipt and receipt.get("state") == "success" \
                    and artifact_rel and (self.run_dir / artifact_rel).exists():
                ns["completed_from"] = "observed Skill 74 success receipt"
                return "done"
            if receipt and receipt.get("state") in ("submitted", "pending",
                                                     "processing", "running"):
                ns["next_lane"] = "transport-poll"
                ns["retry_context"] = (
                    f"\n## Retry context (failure class: transport)\n\n"
                    f"A Skill 74 task for this item already exists: task_id "
                    f"{receipt.get('task_id')!r}, state {receipt.get('state')!r}. "
                    f"Poll that task. Never submit a new createTask.\n")
                return "poll"
            ns["next_lane"] = "transport"
            ns["retry_context"] = (
                "\n## Retry context (failure class: transport)\n\n"
                "The previous attempt reported a transport failure (exit 2) "
                "and no usable Skill 74 receipt exists for this item, so a "
                "fresh dispatch is permitted. Check the Skill 74 receipt "
                "state first if one appears.\n")
            return "retry_or_block"
        if result["exit"] == 0:
            if artifact_rel is None:
                return "done"  # stage-level outputs are checked by the caller
            failures = self.run_validators_for(node["stage"], artifact_rel)
            if not failures:
                return "done"
            ns["next_lane"] = "validation"
            ns["validator_failures"] = failures
            ns["retry_context"] = (
                "\n## Retry context (failure class: validation)\n\n"
                "The gate's validators rejected the previous attempt. Their "
                "output, verbatim:\n\n"
                + "\n".join(f"- {f}" for f in failures) + "\n")
            return "retry_or_block"
        ns["next_lane"] = "validation"
        ns["retry_context"] = (
            f"\n## Retry context (failure class: validation)\n\n"
            f"The previous attempt exited {result['exit']}. Stderr tail:\n\n"
            f"{result['stderr'][-800:]}\n")
        return "retry_or_block"

    def execute_work(self, nid, node):
        ns = self.node_state(nid)
        stage, item = node["stage"], node["item"]
        if self.item_closed_in_gate(stage, item):
            ns["status"] = "done"
            ns["completed_from"] = "gate state: already closed"
            self.save_state()
            return
        if node["stage"] in TRANSPORT_STAGES:
            over = self.disk_over_cap()
            if over is not None:
                self.block_node(nid, node,
                                f"disk soft cap exceeded: run dir is {over} bytes, "
                                f"cap is {self.profile['disk_soft_cap_bytes']} "
                                f"(references/runner-profiles.json); free space "
                                f"or raise the cap in the per-host override",
                                "operator: disk soft cap")
                return
        if item != "stage":
            rc, out = self.gate("check-item", self.run_dir, stage, item)
            if rc != 0:
                waits = ns.get("wait_count", 0) + 1
                ns["wait_count"] = waits
                last = out.strip().splitlines()[-1] if out.strip() else "gate check-item"
                if waits >= 5:
                    self.block_node(
                        nid, node,
                        f"gate check-item kept refusing this item: {last}",
                        f"escalation: item dependencies never satisfied for {nid}")
                    return
                ns["status"] = "waiting"
                ns["waiting_on"] = "gate check-item: " + last
                self.save_state()
                return
        artifact_rel = (expected_item_artifact(self.contract, stage, item)
                        if item != "stage" else None)
        attempt = len(ns["attempts"]) + 1
        lane = ns.pop("next_lane", None)
        extra = ns.pop("retry_context", "")
        if node["stage"] in TRANSPORT_STAGES and self.bucket is not None:
            self.bucket.consume()  # first attempts and retries alike
            self.log("kie_token_granted", node=nid, attempt=attempt)
        browser_name = None
        if self.stage_uses_browser(stage):
            browser_name = self.browser_session_open(node)
        brief_path, note_file = self.render_brief(
            node, attempt=attempt, lane=lane, extra_context=extra)
        ns["status"] = "running"
        self.save_state()
        try:
            result = self.spawn_worker(node, brief_path, note_file,
                                       self.timeout_for(node))
        finally:
            # The worker has exited on every path spawn_worker can take
            # (exit, timeout, exception): its browser work is over, so
            # the runner tears the session down here (Item 33 HOW 2).
            if browser_name:
                self.browser_session_close(browser_name,
                                           via="runner-node-exit")
        record = {"attempt": attempt, "lane": lane, "session": result["session"],
                  "exit": result["exit"], "timed_out": result["timed_out"],
                  "started_at": now_iso()}
        ns["attempts"].append(record)
        ns["session_id"] = result["session"]
        outcome = self.classify_and_maybe_complete(node, result, artifact_rel) \
            if node["kind"] == "work" else "done"
        if outcome == "retry_or_block":
            if attempt >= 2:
                lane_name = ns.get("next_lane", "validation")
                self.block_node(
                    nid, node,
                    f"{lane_name} failure after 1 retry (attempt {attempt})",
                    f"escalation: {lane_name} lane exhausted for {nid}; a human "
                    f"or the stage lead reviews the recorded attempts")
                return
            ns["status"] = "pending"  # retry, with next_lane/retry_context set
            self.save_state()
            return
        if outcome == "poll":  # transport lane: the retry polls, never resubmits
            if attempt >= 2:
                self.block_node(nid, node,
                                "transport failure after 1 retry: the submitted "
                                "Skill 74 task never completed",
                                f"escalation: transport lane exhausted for {nid}")
                return
            ns["status"] = "pending"
            self.save_state()
            return
        # done: observed outputs verified (validators ran inside classify for
        # exit-0; transport completions verified against receipts and disk).
        if artifact_rel is None:
            missing = [o for o in expected_stage_outputs(self.contract, stage)
                       if not (self.run_dir / o).exists()
                       and not self._is_gate_owned_output(stage, o)]
            if missing and result["exit"] == 0:
                ns["status"] = "pending"
                ns["next_lane"] = "validation"
                ns["retry_context"] = ("\n## Retry context (failure class: "
                                        "validation)\n\nExpected outputs missing: "
                                        + ", ".join(missing) + "\n")
                if attempt >= 2:
                    self.block_node(nid, node,
                                    "validation failure after 1 retry: outputs "
                                    "missing: " + ", ".join(missing),
                                    f"escalation: validation lane exhausted for {nid}")
                self.save_state()
                return
        ns["status"] = "done"
        if stage == "image-inventory-prompts" and item != "stage":
            self.refresh_prompt_manifest()
        self.ensure_stage_receipt(stage, result["session"], record["started_at"],
                                  now_iso(),
                                  [artifact_rel] if artifact_rel else
                                  expected_stage_outputs(self.contract, stage))
        self.log("work_done", node=nid, attempt=attempt, session=result["session"])
        self.save_state()

    def refresh_prompt_manifest(self):
        files = sorted((self.run_dir / "image-inventory-prompts").glob("IMG-*.txt"))
        import hashlib
        entries = []
        for f in files:
            entries.append({"id": f.stem, "file": f"image-inventory-prompts/{f.name}",
                            "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
        path = self.run_dir / "image-inventory-prompts" / "prompt-manifest.json"
        path.write_text(json.dumps({"prompts": entries}, indent=2), encoding="utf-8")

    def execute_review(self, nid, node):
        ns = self.node_state(nid)
        stage, item = node["stage"], node["item"]
        cls = criteria_class(stage)
        ns["assignment"] = {"criteria_class": cls,
                            "brief": review_brief_for(stage)}
        if self.item_closed_in_gate(stage, item) and item != "stage":
            ns["status"] = "done"
            ns["assignment"]["session_id"] = ns.get("session_id")
            self.save_state()
            return
        attempt = len(ns["attempts"]) + 1
        brief_path, note_file = self.render_brief(node, attempt=attempt)
        ns["status"] = "running"
        self.save_state()
        result = self.spawn_worker(node, brief_path, note_file,
                                   self.timeout_for(node))
        ns["attempts"].append({"attempt": attempt, "session": result["session"],
                               "exit": result["exit"],
                               "timed_out": result["timed_out"],
                               "started_at": now_iso()})
        ns["session_id"] = result["session"]
        ns["assignment"]["session_id"] = result["session"]
        scores_path = Path(str(note_file) + ".scores.json")
        if result["exit"] != 0 or not scores_path.exists():
            if attempt >= 2:
                self.block_node(nid, node,
                                "review worker produced no scores after 1 retry",
                                f"escalation: review lane exhausted for {nid}")
            else:
                ns["status"] = "pending"
                self.save_state()
            return
        try:
            scores = json.loads(scores_path.read_text(encoding="utf-8"))
        except Exception:
            self.block_node(nid, node, "review scores file is not valid JSON",
                            f"escalation: review lane for {nid}")
            return
        criteria = scores.get("criteria") or {}
        verdict = scores.get("verdict")
        artifact_rel = (expected_item_artifact(self.contract, stage, item)
                        if item != "stage" else None)
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENCLAW_SESSION_ID", "CLAUDE_CODE_SESSION_ID",
                            "CLAUDE_SESSION_ID")}
        env["OPENCLAW_SESSION_ID"] = result["session"]
        env["STAGE_GATE_CONTRACT"] = str(self.contract_path)
        cmd = [sys.executable, str(WRITE_REVIEW), str(self.run_dir), stage,
               (Path(artifact_rel).stem if artifact_rel else "stage"),
               "--scores", json.dumps(criteria), "--verdict", verdict or "fail",
               "--performed-check",
               "Reviewed the artifact on disk against the stage rubric and "
               "recorded per-criterion scores with evidence notes.",
               "--next-current-artifact", artifact_rel or stage]
        if verdict == "fail":
            cmd += ["--specific-defects",
                    scores.get("defects") or "review verdict fail; see scores file"]
        proc = subprocess.run(cmd, text=True, capture_output=True, env=env)
        if proc.returncode != 0:
            self.block_node(nid, node,
                            "write_review.py refused the review: "
                            + (proc.stdout + proc.stderr).strip()[:300],
                            f"escalation: review stamping failed for {nid}")
            return
        if verdict != "pass":
            work_nid = f"{stage}:work:{item}"
            wns = self.node_state(work_nid)
            returns = wns.get("review_returns", 0)
            if returns >= 1:
                self.block_node(work_nid, self.nodes[work_nid],
                                "review failed after the item's one return: "
                                + (scores.get("defects") or "see review file"),
                                f"escalation: review fail for {work_nid}")
                ns["status"] = "done"
                self.save_state()
                return
            wns["review_returns"] = returns + 1
            wns["status"] = "pending"
            # The return IS the work item's one retry: its attempt history is
            # kept, so the redone attempt counts against the same budget.
            wns["next_lane"] = "validation"
            wns["retry_context"] = (
                "\n## Retry context (failure class: validation, review return)\n\n"
                "The reviewer failed this item. Defects:\n"
                + (scores.get("defects") or "(see the review file)") + "\n")
            # This review node must run again against the redone artifact;
            # its own attempt budget is per review round.
            ns["status"] = "pending"
            ns["attempts"] = []
            self.log("review_return", node=work_nid)
            self.save_state()
            return
        ns["status"] = "done"
        if item != "stage" and stage in ITEMIZED_STAGES:
            rc, out = self.gate("close-item", self.run_dir, stage, item)
            if rc != 0:
                self.block_node(nid, node,
                                "gate close-item refused after a passing review: "
                                + out.strip().splitlines()[-1] if out.strip() else
                                "gate close-item refused",
                                f"escalation: gate refusal for {nid}")
                return
            self.log("item_closed", node=nid)
        self.save_state()

    def execute_stageclose(self, nid, node):
        ns = self.node_state(nid)
        rc, out = self.gate("close", self.run_dir, node["stage"])
        if rc == 0:
            ns["status"] = "done"
            self.log("stage_closed", node=nid)
        else:
            ns["status"] = "blocked"
            ns["blocked_reason"] = out.strip()[-4000:]
            ns["escalation"] = (f"escalation: stage {node['stage']} fan-in "
                                f"failed; the gate output above names the items")
            self.log("stage_close_failed", node=nid)
        self.save_state()

    def execute(self, nid):
        node = self.nodes[nid]
        if node["kind"] == "work":
            self.execute_work(nid, node)
        elif node["kind"] == "review":
            self.execute_review(nid, node)
        else:
            self.execute_stageclose(nid, node)

    # -- scheduling ----------------------------------------------------------
    def run(self):
        self.state.setdefault("run", {"started_at": now_iso(),
                                      "runtime": self.runtime,
                                      "swarm_mode": "swarm"})
        self.state["profile"] = self.profile
        self.state["profile_evidence"] = self.evidence
        self.state["kie_limiter"] = str(self.bucket.path) if self.bucket else None
        self.save_state()
        workers = max(1, int(self.profile.get("max_workers", 4)))
        reviewers_cap = max(1, int(self.profile.get("reviewers", 2)))
        render_cap = max(1, int(self.profile.get("playwright_instances", 1)))
        sequential = self.runtime == "sequential" or workers == 1
        if self.runtime == "sequential":
            self.state["swarm_mode"] = "sequential-fallback"
            self.save_state()
        main_pool = ThreadPoolExecutor(max_workers=1 if sequential else workers)
        seq_pool = ThreadPoolExecutor(max_workers=1)
        futures = {}
        running_review = 0
        running_render = 0

        def status(nid):
            return self.node_state(nid)["status"]

        while True:
            # Resume semantics: a node whose gate state already shows its
            # item closed is done without re-running.
            progressed = False
            for nid, node in self.nodes.items():
                if status(nid) in ("pending", "waiting") \
                        and node["kind"] in ("work", "review") \
                        and self.item_closed_in_gate(node["stage"], node["item"]) \
                        and node["item"] != "stage":
                    self.node_state(nid)["status"] = "done"
                    progressed = True
                if status(nid) in ("pending", "waiting") \
                        and node["kind"] == "stageclose" \
                        and self.item_closed_in_gate(node["stage"], "stage"):
                    self.node_state(nid)["status"] = "done"
                    progressed = True
            # Skip propagation: a node whose dependency blocked can never run.
            # Stage-close nodes are exempt: they still run, so the gate's
            # fan-in names the blocked items in its own output.
            for nid, node in self.nodes.items():
                if node["kind"] == "stageclose":
                    continue
                if status(nid) in ("pending", "waiting"):
                    blocked_deps = [d for d in node["deps"]
                                    if status(d) == "blocked"]
                    if blocked_deps:
                        self.node_state(nid)["status"] = "blocked"
                        self.node_state(nid)["blocked_reason"] = (
                            "dependency blocked: " + ", ".join(blocked_deps))
                        progressed = True
            if progressed:
                self.save_state()
            ready = []
            for nid, node in self.nodes.items():
                if status(nid) not in ("pending", "waiting"):
                    continue
                if node["kind"] == "stageclose":
                    satisfied = all(status(d) in ("done", "blocked")
                                    for d in node["deps"])
                else:
                    satisfied = all(status(d) == "done" for d in node["deps"])
                if satisfied:
                    ready.append(nid)
            submitted = False
            in_flight = set(futures.values())
            for nid in ready:
                node = self.nodes[nid]
                if nid in in_flight:
                    continue
                absent = self.capability_absent(node)
                pool = main_pool
                if absent == "transport":
                    self.declare_fallback(
                        "transport", [nid],
                        f"profile capabilities.image_transport is "
                        f"{self.profile.get('capabilities', {}).get('image_transport')!r}, "
                        f"not 'active'; a sequential fallback cannot dispatch "
                        f"paid generation in a non-active transport mode")
                    ns = self.node_state(nid)
                    ns["waiting_on"] = "transport"
                    self.block_node(nid, node,
                                    "capability absent: transport (image_transport "
                                    "is not 'active' under the active profile); "
                                    "sequential fallback declared in the run record",
                                    "escalation: provision an active Skill 74 "
                                    "transport or run this stage sequentially by hand")
                    submitted = True
                    continue
                if absent == "render":
                    ns = self.node_state(nid)
                    ns["waiting_on"] = "render"
                    ns["waited_on_capability"] = "render"
                    self.declare_fallback(
                        "render", [n for n in ready
                                   if self.capability_absent(self.nodes[n]) == "render"],
                        "profile capabilities.render is false; render items "
                        "run sequentially through the same brief and validator "
                        "machinery")
                    pool = seq_pool
                if node["kind"] == "review" and running_review >= reviewers_cap:
                    continue
                if node.get("capability") == "render" and absent is None \
                        and running_render >= render_cap:
                    continue
                fut = pool.submit(self.execute, nid)
                futures[fut] = nid
                if node["kind"] == "review":
                    running_review += 1
                if node.get("capability") == "render":
                    running_render += 1
                submitted = True
            if futures:
                done_futs, _ = wait(list(futures), return_when=FIRST_COMPLETED)
                for fut in done_futs:
                    nid = futures.pop(fut)
                    node = self.nodes[nid]
                    if node["kind"] == "review":
                        running_review -= 1
                    if node.get("capability") == "render":
                        running_render -= 1
                    exc = fut.exception()
                    if exc is not None:
                        self.block_node(nid, node, f"runner error: {exc}",
                                        f"escalation: runner error at {nid}")
                continue
            if submitted:
                continue
            remaining = [n for n in self.nodes
                         if status(n) in ("pending", "waiting", "running")]
            if not remaining:
                break
            # Deadlock guard: nothing ready, nothing running.
            for nid in remaining:
                node = self.nodes[nid]
                unmet = [d for d in node["deps"] if status(d) != "done"]
                self.block_node(nid, node,
                                "dependencies never satisfied: "
                                + ", ".join(unmet or ["gate check-item"]),
                                f"escalation: deadlock at {nid}")
            break
        main_pool.shutdown(wait=True)
        seq_pool.shutdown(wait=True)
        self.teardown_browser_sessions(via="runner-run-end")
        blocked = [n for n in self.nodes if status(n) == "blocked"]
        unclosed = [n for n in self.nodes
                    if self.nodes[n]["kind"] == "stageclose" and status(n) != "done"]
        summary = {"blocked_items": sorted(
                       n for n in blocked if self.nodes[n]["kind"] != "stageclose"),
                   "blocked_nodes": sorted(blocked),
                   "unclosed_stages": sorted(
                       self.nodes[n]["stage"] for n in unclosed),
                   "swarm_mode": self.state.get("swarm_mode", "swarm"),
                   "fallback_declared": self.fallback_declared}
        self.state["summary"] = summary
        self.save_state()
        self.log("run_finished", **summary)
        return 0 if not blocked and not unclosed else 1


# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Skill 71 swarm runner (Item 21)")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--stages", help="comma-separated stage subset")
    ap.add_argument("--profile")
    ap.add_argument("--profile-file", type=Path,
                    help="a profiles JSON file or a single profile object")
    ap.add_argument("--runtime", default=os.environ.get("SKILL71_RUNTIME", "openclaw"))
    ap.add_argument("--worker-cmd", default=os.environ.get("SKILL71_WORKER_CMD"))
    ap.add_argument("--contract", type=Path,
                    default=Path(os.environ.get("STAGE_GATE_CONTRACT",
                                                str(DEFAULT_CONTRACT))))
    ap.add_argument("--kie-limiter", type=Path)
    ap.add_argument("--timeout-work", type=int)
    ap.add_argument("--timeout-review", type=int)
    ap.add_argument("--timeout-generation", type=int)
    args = ap.parse_args(argv)

    if args.runtime not in RUNTIME_TEMPLATES:
        print(f"FAIL: runtime {args.runtime!r} has no documented spawn contract "
              f"in references/runtime-adapters.md (known: "
              f"{sorted(RUNTIME_TEMPLATES)}); refusing to spawn", file=sys.stderr)
        return 2
    worker_cmd = args.worker_cmd or RUNTIME_TEMPLATES[args.runtime]
    if not worker_cmd:
        print("FAIL: runtime generic-shell/sequential needs --worker-cmd or "
              "SKILL71_WORKER_CMD (see references/runtime-adapters.md)",
              file=sys.stderr)
        return 2
    profiles_data = None
    cli_name = args.profile
    if args.profile_file:
        loaded = json.loads(args.profile_file.read_text(encoding="utf-8"))
        if "profiles" in loaded:
            profiles_data = loaded
        else:
            profiles_data = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
            base = dict(profiles_data["profiles"]["fleet-contabo"])
            base.update(loaded)
            profiles_data["profiles"] = {"custom": base}
            cli_name = "custom"
    try:
        profile, evidence = resolve_profile(cli_name=cli_name,
                                            profiles_data=profiles_data)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    overrides = {}
    if args.timeout_work is not None:
        overrides["image-inventory-prompts:work"] = args.timeout_work
    if args.timeout_review is not None:
        overrides["image-generation-qc:review"] = args.timeout_review
        overrides["image-inventory-prompts:review"] = args.timeout_review
    if args.timeout_generation is not None:
        overrides["generation"] = args.timeout_generation
    stages = args.stages.split(",") if args.stages else None
    runner = Runner(args.run_dir, args.contract, profile, evidence,
                    args.runtime, worker_cmd, stages=stages,
                    limiter_path=limiter_path_for(profile, os.environ,
                                                  args.kie_limiter),
                    timeout_overrides=overrides)
    # Item 33 HOW 2: teardown on the runner's signal paths too. SIGKILL
    # cannot be handled by anyone; sessions it strands stay open in the
    # registry and the gate's reaper pass accounts for them.
    import signal as _signal

    def _shutdown(signum, _frame):
        runner.teardown_browser_sessions(via=f"runner-signal-{signum}")
        raise SystemExit(128 + signum)

    _signal.signal(_signal.SIGTERM, _shutdown)
    _signal.signal(_signal.SIGINT, _shutdown)
    rc = runner.run()
    summary = runner.state.get("summary", {})
    if rc != 0:
        print("RUN INCOMPLETE")
        for nid in summary.get("blocked_nodes", []):
            reason = runner.node_state(nid).get("blocked_reason", "")
            print(f"- blocked: {nid}: {str(reason)[:300]}")
        for stage in summary.get("unclosed_stages", []):
            print(f"- stage not closed: {stage}")
    else:
        print("RUN COMPLETE: all in-scope stages closed")
    return rc


if __name__ == "__main__":
    sys.exit(main())
