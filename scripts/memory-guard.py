#!/usr/bin/env python3
"""memory-guard.py - nightly, zero-model guard for OpenClaw memory search.

Two jobs, both deterministic (no model turn, no tokens):

  key   - Tests the box's memory-search embedding key with OpenClaw's own probe
          (`openclaw memory status --deep --json` -> embeddingProbe). When the
          provider memory search is using is unusable - DEAD (key rejected, out of
          credit, out of quota; confirmed by a second probe 90 s later) or
          UNCONFIGURED (no key, unknown provider) - the guard walks a fixed backup
          chain and uses the first option whose probe passes:
            1. the box's original provider/model (whatever it had before the
               guard first touched it; on a Mac, the Skill 76 local Ollama model)
            2. OpenRouter nvidia/nemotron-3.5-embed-1b:free, expressed purely
               inside memory.search (see NEMOTRON below; nothing under models.*)
            3. Gemini gemini-embedding-2
          One `config patch` switches provider + model (+ the endpoint that goes
          with it). If none is usable, memory search goes OFF for the whole box (so
          it stops retrying a dead key in a loop) and the box's own Telegram bot
          tells the client to add funds (retried nightly until a send succeeds).
          Every night the guard also tries to climb back UP the chain, and turns
          memory search back on when something works again. A transient failure
          (network, timeout, 5xx, local Ollama down) changes nothing.
          OpenClaw allows only one `memory.search.fallback` string with no model
          choice, which is why the chain lives here; that key is never edited.

  idle  - Lets the box's own job history decide which workers keep memory
          search. The main agent and the master orchestrator always keep it.
          Every other worker that ran a job or had a conversation in the last
          30 days keeps it; a worker with nothing in 30 days has it turned off
          (agents.entries.<id>.memory.search.enabled=false). When that worker
          runs a job again, the next nightly pass turns it back on. A worker
          younger than 30 days is never turned off.

Ownership rule: the guard only ever undoes what the guard itself did (recorded in
its state file). A switch somebody else set to false is left alone, so is any
agent with its own memory.search provider, and if someone changes the provider
by hand the guard forgets its record and treats the new setting as the original.

Writes go through `openclaw config patch --stdin` (one validated write per pass)
as the box user; the script refuses to run as root. Needs the current config
shape (top-level memory.search, agents.entries) and OpenClaw 2026.10.5 or newer
(the first build that applies a memory.search provider, model or enabled change
without restarting the Gateway; none of the commands used here takes the SQLite
maintenance lock on any build tested, 2026.9.1 to 2026.10.8); otherwise it reports
SKIPPED and changes nothing.

Usage:
  memory-guard.py run   [--dry-run] [--days N]   # key, then idle (what the cron runs)
  memory-guard.py key   [--dry-run]
  memory-guard.py idle  [--dry-run] [--days N]
  memory-guard.py status
  memory-guard.py --self-test

Exit: 0 done / nothing to do / skipped; 1 unexpected error; 2 usage or refused.
"""
import argparse
import contextlib
import copy
import glob
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

IDLE_DAYS_DEFAULT = 30
CONFIRM_DELAY_S = 90
# Time budget. The cron command times out at 600 s; the whole run (version check, key
# check, idle check) stops itself at TOTAL_BUDGET_S and every CLI call is clamped to
# what is left, so a run always ends first. A dead verdict is only re-confirmed when
# the confirmation (sleep + re-probes) and the write after it still fit.
TOTAL_BUDGET_S = 540
PROBE_TIMEOUT_S = 60
VERSION_TIMEOUT_S = 30
PATCH_TIMEOUT_S = 60
MESSAGE_TIMEOUT_S = 45
WRITE_RESERVE_S = PATCH_TIMEOUT_S + MESSAGE_TIMEOUT_S
# 2026.10.4 and older restart the serving Gateway on any memory.search provider/model/enabled change; 2026.10.5+ hot-reload it.
MIN_OPENCLAW = (2026, 10, 5)
ALWAYS_ON_IDS = {"main"}
ALWAYS_ON_PATTERNS = ("master-orchestrator",)
# Canonical list: shared-utils/resolve-owner-chat.sh (OPERATOR_CHAT_IDS_SH). Every reader in
# the repo keeps its own copy (install.sh, ensure-pipeline-crons.sh, ...); tests/unit/memory-guard.test.sh
# fails if this copy drifts from the canonical one.
OPERATOR_CHAT_IDS = {"5252140759", "6663821679", "6771245262"}

VERSION_RE = re.compile(r"\b(20\d\d)\.(\d{1,2})\.(\d{1,2})\b")

# The backup chain after the box's own (original) provider/model, in the owner-approved order.
#
# OpenRouter: OpenClaw only knows "openrouter" as a memory provider when models.providers.openrouter
# exists, and that is chat-model config the guard never touches. So the slot is expressed purely
# inside memory.search: the OpenAI-compatible provider pointed at OpenRouter's embeddings endpoint,
# with the key as an env SecretRef to the box's own OPENROUTER_API_KEY (never a literal key).
# Verified with `openclaw memory status --deep --json` on 2026.10.8 against a temp config copy that
# had neither models.providers.openrouter nor models.providers.openai: embeddingProbe ok:true; the
# same shape with a missing variable, an unreachable baseUrl, or an unknown model all fail.
# A box with no OPENROUTER_API_KEY simply gets an "unconfigured" verdict for this slot.
NEMOTRON = {"name": "openrouter", "provider": "openai", "model": "nvidia/nemotron-3.5-embed-1b:free",
            "remote": {"baseUrl": "https://openrouter.ai/api/v1",
                       "apiKey": {"source": "env", "provider": "default", "id": "OPENROUTER_API_KEY"}}}
# Gemini needs nothing but provider + model: OpenClaw finds the key itself (models.providers.google
# or GEMINI_API_KEY / GOOGLE_API_KEY). No key = "unconfigured".
GEMINI = {"name": "gemini", "provider": "gemini", "model": "gemini-embedding-2"}
# memory.search keys that move with the provider; OWNED[2:] (endpoint+credential override,
# provider-specific vector size) belong to the original provider and are dropped on a
# switch, restored on return. (`dimensions` is not a memory.search key on 2026.10.8.)
OWNED = ("provider", "model", "remote", "outputDimensionality")
SECRET_KEYS = ("remote", "apiKey", "headers")  # never written to a log or to `status` output

# A probe error that means the key itself is unusable (rejected, unpaid, out of
# quota). Anything else is treated as transient and never flips a switch.
DEAD_KEY_RE = re.compile(
    r"\b(401|402|403)\b|unauthori[sz]ed|invalid[ _-]?api[ _-]?key|incorrect api key|"
    r"api key not valid|api_key_invalid|permission[ _-]denied|no credits|"
    r"insufficient[ _](credits|quota|balance|funds)|exceeded your current quota|"
    r"resource_exhausted|billing|payment required|token status is unavailable|"
    r"account (is )?(suspended|disabled|deactivated)",
    re.IGNORECASE,
)
# A probe error that means the MODEL or its endpoint is gone for good (retired, "no endpoints
# found", 404 on the model, 400 invalid model): retrying tomorrow will not help, so the slot is
# unusable, exactly like a dead key. Real texts: `... (400): Model X does not exist` (2026.10.8),
# OpenRouter `No endpoints found for X`, Gemini `models/X is not found for API version v1beta`.
# A network failure, timeout, 5xx or 429 rate limit is never "gone", whatever else the text says
# (TRANSIENT_RE wins): OpenRouter free models also answer 404/503 for a while when busy, which is
# why a "gone" verdict is confirmed by a second probe 90 s later, like a dead key.
MODEL_GONE_RE = re.compile(
    r"no endpoints found|model[_ -]?not[_ -]?found|invalid[ _-]model|unknown model|no such model|"
    r"\bmodel\b[^\n]{0,100}\b(does not exist|is not found|not found|is not supported|no longer (available|supported)|"
    r"has been (deprecated|retired|removed|discontinued|decommissioned))|"
    r"\bmodels/\S+ is not found|\b404\b[^\n]{0,200}\bmodel\b|\bmodel\b[^\n]{0,200}\b404\b",
    re.IGNORECASE,
)
TRANSIENT_RE = re.compile(
    r"\b(429|5\d\d)\b|rate[ _-]?limit|too many requests|time[ds]?[ -]?out|ETIMEDOUT|ECONN\w*|ENOTFOUND|EAI_AGAIN|"
    r"fetch failed|socket|network|overloaded|temporar|unavailable",
    re.IGNORECASE,
)
# A provider that cannot be used on this box at all: no key, an env variable that is not set, or a
# provider OpenClaw does not know. Real CLI texts (2026.10.8): `No API key found for provider "google"`,
# `Unknown memory embedding provider: openrouter`, `openai embedding credentials are not configured
# for <url>`, `Environment variable "X" is missing or empty`. Deterministic, so no second probe.
UNCONFIGURED_RE = re.compile(
    r"No API key found for provider|Unknown memory embedding provider|"
    r"embedding credentials are not configured|Environment variable \"[A-Z0-9_]+\" is missing or empty",
)
UNUSABLE = ("dead", "gone", "unconfigured")
# Anything key-shaped in provider error text (vendor-prefixed, masked "sk-ab***yz", long tokens).
KEYLIKE_RE = re.compile(
    r"\b(?:sk|rk|pk|nvapi|ghp|xox[abp])[-_][A-Za-z0-9_\-\*\.]{6,}"
    r"|\bAIza[0-9A-Za-z_\-]{10,}"
    r"|\b[A-Za-z0-9]{2,}\*{3,}[A-Za-z0-9]{2,}"
    r"|\b[A-Za-z0-9_\-]{32,}\b"
)

BILLING_HINT = {
    "gemini": "Google AI Studio (https://aistudio.google.com)",
    "google": "Google AI Studio (https://aistudio.google.com)",
    "openai": "the OpenAI billing page (https://platform.openai.com/settings/organization/billing)",
    "openrouter": "the OpenRouter credits page (https://openrouter.ai/settings/credits)",
    "voyage": "the Voyage AI dashboard (https://dashboard.voyageai.com)",
    "mistral": "the Mistral console (https://console.mistral.ai)",
}
PROVIDER_NAME = {"gemini": "Gemini", "google": "Gemini", "openai": "OpenAI",
                 "openrouter": "OpenRouter", "voyage": "Voyage", "mistral": "Mistral"}


# ---------------------------------------------------------------- paths / io
def oc_root():
    for var in ("OPENCLAW_STATE_DIR", "OPENCLAW_ROOT", "OC_ROOT"):
        v = os.environ.get(var, "").strip()
        if v and os.path.isdir(v):
            return v
    if os.path.isdir("/data/.openclaw"):
        return "/data/.openclaw"
    return os.path.expanduser("~/.openclaw")


def redact(text):
    """Provider error text can echo a (masked) key; nothing key-shaped is stored or printed."""
    return KEYLIKE_RE.sub("<redacted>", str(text))


def scrub(o):
    if isinstance(o, dict):
        return {k: ("<redacted>" if k in SECRET_KEYS and v is not None else scrub(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [scrub(x) for x in o]
    return redact(o) if isinstance(o, str) else o


def merge_patch(doc, patch):
    """Apply a patch the way `openclaw config patch` does: objects merge, null deletes, the rest replaces."""
    for k, v in patch.items():
        if v is None:
            doc.pop(k, None)
        elif isinstance(v, dict):
            if not isinstance(doc.get(k), dict):
                doc[k] = {}
            merge_patch(doc[k], v)
        else:
            doc[k] = v
    return doc


def unlanded(doc, patch, path=""):
    """Paths in `patch` whose value is not what the config file (`doc`) holds now."""
    bad = []
    for k, v in patch.items():
        here = "%s.%s" % (path, k) if path else k
        have = doc.get(k) if isinstance(doc, dict) else None
        if v is None:
            if isinstance(doc, dict) and k in doc:
                bad.append(here)
        elif isinstance(v, dict):
            bad += unlanded(have if isinstance(have, dict) else {}, v, here)
        elif have != v:
            bad.append(here)
    return bad


class Box:
    def __init__(self, root, cli="openclaw", now=None, dry_run=False, log=None, deadline=None):
        self.root = root
        self.cfg_path = os.environ.get("OPENCLAW_CONFIG_PATH") or os.path.join(root, "openclaw.json")
        self.state_dir = os.path.join(root, "memory-guard")
        self.state_path = os.path.join(self.state_dir, "state.json")
        self.log_path = os.path.join(root, "logs", "memory-guard.log")
        self.cli = cli
        self.now = now or time.time()
        self.dry_run = dry_run
        self._log = log
        self.deadline = deadline or time.time() + TOTAL_BUDGET_S

    def remaining(self):
        return max(0.0, self.deadline - time.time())

    def log(self, msg):
        line = "%s [memory-guard] %s" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), msg)
        if self._log is not None:  # self-test capture
            self._log.append(line)
            return
        print(line)
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "a") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def config(self):
        with open(self.cfg_path) as f:
            return json.load(f)

    def state(self):
        try:
            with open(self.state_path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_state(self, st):
        if self.dry_run:
            return
        os.makedirs(self.state_dir, mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.state_dir, prefix=".state-")
        with os.fdopen(fd, "w") as f:
            json.dump(st, f, indent=2, sort_keys=True)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.state_path)

    def run_cli(self, args, env=None, stdin=None, timeout=PROBE_TIMEOUT_S):
        """Every call names the box's state dir and config file explicitly (so a stray
        environment can never make the CLI create or edit a different one) and is clamped
        to the time budget that is left."""
        left = self.remaining()
        if left < 3:
            return 124, "", "time budget exhausted"
        e = dict(os.environ, OPENCLAW_STATE_DIR=self.root, OPENCLAW_CONFIG_PATH=self.cfg_path)
        if env:
            e.update(env)
        timeout = min(timeout, left)
        try:
            p = subprocess.run([self.cli] + args, input=stdin, capture_output=True,
                               text=True, timeout=timeout, env=e)
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return 124, "", "timeout after %ds" % timeout
        except OSError as exc:
            return 127, "", str(exc)

    def patch(self, obj, why):
        """One validated config write. True only if the CLI succeeded AND the value is in the
        real config file afterwards (a CLI pointed at the wrong place exits 0 and writes
        nothing here). A dry run reports success."""
        body = json.dumps(obj)
        shown = json.dumps(scrub(obj))
        if self.dry_run:
            self.log("DRY-RUN would patch config (%s): %s" % (why, shown))
            return True
        rc, out, err = self.run_cli(["config", "patch", "--stdin"], stdin=body, timeout=PATCH_TIMEOUT_S)
        if rc != 0:
            self.log("FAIL config patch (%s) rc=%s: %s" % (why, rc, redact((err or out).strip()[:300])))
            return False
        try:
            missing = unlanded(self.config(), obj)
        except (OSError, ValueError) as exc:
            self.log("FAIL config patch (%s): cannot re-read %s to verify it: %s" % (why, self.cfg_path, exc))
            return False
        if missing:
            self.log("FAIL config patch (%s): the CLI said OK but %s did not change in %s; nothing recorded"
                     % (why, ", ".join(missing[:4]), self.cfg_path))
            return False
        self.log("OK config patch (%s): %s" % (why, shown))
        return True


def schema_ok(cfg):
    """Current shape only: top-level memory.search + agents.entries."""
    agents = cfg.get("agents") or {}
    if isinstance(agents.get("list"), list):
        return False, "agents.list (older config shape)"
    if (agents.get("defaults") or {}).get("memorySearch") and not (cfg.get("memory") or {}).get("search"):
        return False, "agents.defaults.memorySearch (older config shape)"
    return True, ""


def top_search(cfg):
    return (cfg.get("memory") or {}).get("search") or {}


def entries(cfg):
    e = (cfg.get("agents") or {}).get("entries") or {}
    return e if isinstance(e, dict) else {}


def agent_search(entry):
    return ((entry or {}).get("memory") or {}).get("search") or {}


def system_agent_key(cfg):
    """The roster key named by agents.defaults.systemAgent.agentId (case-insensitive), else None."""
    ents = entries(cfg)
    sysid = str((((cfg.get("agents") or {}).get("defaults") or {}).get("systemAgent") or {}).get("agentId") or "").strip().lower()
    return next((k for k in ents if k.lower() == sysid), None) if sysid else None


def protected_ids(cfg):
    """Agents the idle check never touches, however quiet: main, anything marked
    `default: true`, the configured system agent, the resolved default, any master orchestrator.
    Several of these can exist at once and the default can be unknowable, so none of them
    depends on default_agent_id() succeeding."""
    out = set(ALWAYS_ON_IDS)
    out |= {a for a, e in entries(cfg).items() if isinstance(e, dict) and e.get("default") is True}
    out |= {k for k in (system_agent_key(cfg), default_agent_id(cfg)) if k}
    out |= {a for a in entries(cfg) if any(p in a for p in ALWAYS_ON_PATTERNS)}
    return out


def default_agent_id(cfg):
    """The agent OpenClaw itself treats as the default (2026.10.x resolveAmbientOwnerAgentId):
    agents.defaults.systemAgent.agentId, else the single `default: true` marker (not under
    explicit ownership), else the only agent. Beyond that, `main` if it exists. None when it
    cannot be told (several agents, no marker, no main): callers then leave the box alone."""
    ents, agents = entries(cfg), cfg.get("agents") or {}
    if system_agent_key(cfg):
        return system_agent_key(cfg)
    if agents.get("ownership") != "explicit":
        marked = [a for a, e in ents.items() if isinstance(e, dict) and e.get("default") is True]
        if len(marked) == 1:
            return marked[0]
    if len(ents) == 1:
        return next(iter(ents))
    if not ents or "main" in ents:
        return "main"
    return None


# ---------------------------------------------------------------- key guard
def snapshot(ms):
    return {k: copy.deepcopy(ms[k]) for k in OWNED if k in ms}


def ident(c):
    """What makes two memory-search setups the same slot: provider, model, endpoint."""
    return (c.get("provider"), c.get("model"), (c.get("remote") or {}).get("baseUrl"))


def chain_of(orig):
    """Backup chain, best first: the box's original, then the two backups. A backup that
    is the same setup as an earlier slot is dropped."""
    first = {"provider": orig.get("provider"), "model": orig.get("model")}
    if orig.get("remote"):
        first["remote"] = orig["remote"]
    out = []
    for c in (first, NEMOTRON, GEMINI):
        if all(ident(c) != ident(o) for o in out):
            out.append(c)
    return out


def label(c):
    return "%s/%s" % (c.get("name") or c.get("provider") or "auto", c.get("model") or "default")


def mm_flags(cfg):
    """Where multimodal is switched on and inherited: "" is the top level, else an agent id."""
    out = [""] if (top_search(cfg).get("multimodal") or {}).get("enabled") is True else []
    for aid, e in sorted(entries(cfg).items()):
        s = agent_search(e)
        if (s.get("multimodal") or {}).get("enabled") is True and not (s.get("provider") or s.get("model")):
            out.append(aid)
    return out


def remote_patch(cur, new):
    """Patch fragment that turns memory.search.remote into exactly `new`. A merge patch only
    adds and overwrites, so every key of the current object that `new` lacks is nulled; a
    stale header or key of the previous provider must not survive."""
    cur, new = cur if isinstance(cur, dict) else {}, new or {}
    if not cur and not new:
        return {}
    if not new:
        return {"remote": None}
    return {"remote": dict({k: None for k in cur if k not in new}, **new)}


def slot_patch(cfg, orig, chain, i, cur, mm_off):
    """The one config patch that makes chain slot i the memory-search setup ({} if it already
    is). Returns (patch, multimodal switches the guard now holds off).

    Why more than provider+model:
      * remote / outputDimensionality are the ORIGINAL provider's endpoint, credential
        and vector size. Left in place they would send that endpoint (a local Ollama URL)
        or credential to a different vendor, so a slot REPLACES them (the OpenRouter slot
        brings its own remote; Gemini brings none) and the original gets its own back
        verbatim on the way home.
      * multimodal indexing needs the Gemini adapter; on a text-only provider every
        agent that has it on fails to re-index, so it is held off there and put back
        when the box is on Gemini again."""
    ms, slot, p = top_search(cfg), chain[i], {}
    if i != cur:
        src = orig if i == 0 else slot
        p = {"provider": src.get("provider"), "model": src.get("model"),
             "outputDimensionality": src.get("outputDimensionality")}
        p.update(remote_patch(ms.get("remote"), src.get("remote")))
        if p["outputDimensionality"] is None and "outputDimensionality" not in ms:
            del p["outputDimensionality"]
    out = {"memory": {"search": p}} if p else {}
    gemini = slot["provider"] == "gemini"
    ids = mm_off if gemini else (mm_flags(cfg) if i != cur else [])
    for who in ids:
        node = out.setdefault("memory", {}).setdefault("search", {}) if who == "" else \
            out.setdefault("agents", {}).setdefault("entries", {}).setdefault(who, {}).setdefault("memory", {}).setdefault("search", {})
        node["multimodal"] = {"enabled": gemini}
    return out, ([] if gemini else sorted(set(mm_off) | set(ids)))


def probe_cfg(cfg, patch, agent_id):
    """What the probe runs against: the config as the patch would leave it, memory search
    forced on, no fallback (so the probe measures that one provider, not its fallback), and
    no per-agent off switches. Those are irrelevant to whether a provider and key work, and
    they break the probe: when ANY agent has memory search (or the agent itself) switched
    off, OpenClaw's command-side secret analysis (2026.10.8) treats a SecretRef shared at
    memory.search.remote.apiKey as inactive and the OpenRouter slot reads as unresolvable.
    (The running Gateway is not affected: with the same SecretRef in its own config and idle
    workers switched off, `memory status` resolves it and the probe passes, verified in a
    sandbox Gateway.)"""
    c = merge_patch(copy.deepcopy(cfg), patch)
    c.setdefault("memory", {}).setdefault("search", {}).update({"enabled": True, "fallback": "none"})
    for ent in entries(c).values():
        if isinstance(ent, dict):
            if ent.get("enabled") is False:
                ent.pop("enabled")
            if agent_search(ent).get("enabled") is False:
                ent["memory"]["search"].pop("enabled")
    return c


def parse_json(text):
    """The first JSON value that starts a line; a banner or warning line before it is skipped."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"^[\[{]", text, re.M):
        try:
            return dec.raw_decode(text[m.start():])[0]
        except ValueError:
            continue
    return None


def probe(box, agent_id, cfg):
    """Run OpenClaw's own embedding probe against a read-only temp copy of cfg.

    Returns (state, detail); state: ok | dead | gone | unconfigured | transient | none."""
    os.makedirs(box.state_dir, mode=0o700, exist_ok=True)
    for old in glob.glob(os.path.join(box.state_dir, ".probe-*.json")):  # left by a killed run
        try:
            if os.path.getmtime(old) < box.now - 3600:
                os.remove(old)
        except OSError:
            pass
    fd, tmp = tempfile.mkstemp(dir=box.state_dir, prefix=".probe-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f)
    os.chmod(tmp, 0o600)
    env = {"OPENCLAW_CONFIG_PATH": tmp, "OPENCLAW_CONFIG_READONLY": "1"}
    try:
        rc, out, err = box.run_cli(["memory", "status", "--deep", "--agent", agent_id, "--json"],
                                   env=env, timeout=PROBE_TIMEOUT_S)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    data = parse_json(out)
    row = (data[0] if isinstance(data, list) and data else data) if data is not None else None
    row = row if isinstance(row, dict) else {}
    pr = row.get("embeddingProbe")
    if isinstance(pr, dict):
        if pr.get("ok") is True:
            return "ok", ""
        raw = str(pr.get("error") or "probe failed")
        if DEAD_KEY_RE.search(raw):
            verdict = "dead"
        elif MODEL_GONE_RE.search(raw) and not TRANSIENT_RE.search(raw):
            verdict = "gone"
        else:
            verdict = "transient"
        return verdict, redact(raw)[:200]
    e = row.get("error")
    msg = str(e.get("message") if isinstance(e, dict) else e or "")
    if UNCONFIGURED_RE.search(msg + "\n" + err):
        return "unconfigured", redact(msg or err.strip())[:200]
    if not row:
        return "transient", "no JSON from memory status (rc=%s): %s" % (rc, redact((err or out).strip())[:200])
    return "none", redact(msg)[:200] if msg else "no embedding probe in status output"


def survey(box, cfg, orig, chain, cur, mm_off, agent, sleep):
    """Probe the chain top-down, stopping at the first slot that works. A dead (or model-gone)
    verdict is re-checked once, CONFIRM_DELAY_S later, but only when something could act on it (a
    dead slot at or below the current one) and only if the wait, the re-probes and the
    write after them still fit in the time budget; otherwise it stays unconfirmed and
    nothing changes this run. Unconfigured slots are deterministic: no re-check."""
    def one(i):
        patch, _ = slot_patch(cfg, orig, chain, i, cur, mm_off)
        return probe(box, agent, probe_cfg(cfg, patch, agent))

    res = []
    for i in range(len(chain)):
        res.append(one(i))
        if res[-1][0] == "ok":
            break
    dead = [i for i, r in enumerate(res) if r[0] in ("dead", "gone")]
    if dead and dead[-1] >= cur:
        if box.remaining() < CONFIRM_DELAY_S + len(dead) * PROBE_TIMEOUT_S + WRITE_RESERVE_S:
            box.log("dead verdict on %s but too little of the time budget is left to confirm it; changing nothing"
                    % ", ".join(label(chain[i]) for i in dead))
            for i in dead:
                res[i] = ("transient", "dead verdict unconfirmed (time budget)")
            return res
        box.log("dead verdict on %s; confirming in %ss" % (", ".join(label(chain[i]) for i in dead), CONFIRM_DELAY_S))
        sleep(CONFIRM_DELAY_S)
        for i in dead:
            res[i] = one(i)
    return res


def owner_chat(cfg):
    """Non-operator owner Telegram chat (mirrors ensure-pipeline-crons.sh
    _resolve_owner_chat: env override, allowFrom, then ownerAllowFrom)."""
    def tg_token(cfg, acct="default"):
        tg = (cfg.get("channels") or {}).get("telegram") or {}
        acc = (tg.get("accounts") or {}).get(acct) or {}
        for src in (acc, tg):
            f = src.get("tokenFile")
            if isinstance(f, str) and f.strip():
                try:
                    t = open(os.path.expanduser(f.strip())).read().strip()
                    if t:
                        return t
                except OSError:
                    pass
            t = src.get("botToken")
            if isinstance(t, str) and t.strip():
                return t.strip()
        return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() if acct == "default" else ""

    bt = tg_token(cfg)
    bot_id = bt.split(":")[0] if ":" in bt else ""

    def valid(v):
        if not isinstance(v, (str, int)):
            return ""
        s = str(v).strip().replace("telegram:", "").replace("tg:", "")
        digits = s.lstrip("-")
        if not (digits.isdigit() and 6 <= len(digits) <= 20):
            return ""
        if (bot_id and s == bot_id) or s in OPERATOR_CHAT_IDS:
            return ""
        return s

    cands = [os.environ.get("OPENCLAW_OWNER_CHAT_ID", "")]
    tg = (cfg.get("channels") or {}).get("telegram") or {}
    cands += list(tg.get("allowFrom") or [])
    cands += list(((tg.get("accounts") or {}).get("default") or {}).get("allowFrom") or [])
    cands += list((cfg.get("commands") or {}).get("ownerAllowFrom") or [])
    for c in cands:
        cid = valid(c)
        if cid:
            return cid
    return ""


def tell_client(box, cfg, chain, res, st):
    """ONE plain-English notice to the client's own Telegram chat per dead-key episode: a send
    that fails (or no chat to send to) is retried on later nights until one succeeds.
    Returns True once a message has gone out."""
    chat = owner_chat(cfg)
    bills = lambda cs: [x for x in dict.fromkeys(c.get("name") or c["provider"] for c in cs) if x in BILLING_HINT]
    provs = bills([c for c, r in zip(chain, res) if r[0] == "dead"]) or bills(chain)
    names = [PROVIDER_NAME[p] for p in provs]
    msg = ("Heads up from your AI team: memory search has no working key right now (%s). It looks like "
           "the accounts are out of money, were switched off, have no key set up, or the model is no longer offered. To keep your box "
           "running smoothly, memory search is paused for now. Your agents keep doing their jobs; they "
           "just can't search their notes until a key works again. Please add funds or check the keys "
           "at: %s. Memory search turns back on by itself once a key works."
           % (", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names),
              "; ".join(BILLING_HINT[p] for p in provs)))
    if not chat:
        box.log("NOTICE no client Telegram chat found; client message not sent (retried next night)")
        return False
    if box.dry_run:
        box.log("DRY-RUN would message the client's Telegram chat: %s" % msg)
        return False
    rc, out, err = box.run_cli(["message", "send", "--channel", "telegram", "--target", chat,
                                "--message", msg], timeout=MESSAGE_TIMEOUT_S)
    if rc != 0:
        box.log("FAIL client message rc=%s: %s (retried next night)" % (rc, redact((err or out).strip())[:200]))
        return False
    st["key"]["notified"] = int(box.now)
    box.save_state(st)
    box.log("OK told the client (Telegram) that the memory keys are not working")
    return True


def key_pass(box, sleep=time.sleep):
    cfg = box.config()
    ok, why = schema_ok(cfg)
    if not ok:
        box.log("SKIPPED key check: %s" % why)
        return 0
    st = box.state()
    kst = st.setdefault("key", {})
    ms = top_search(cfg)
    enabled = ms.get("enabled", True) is not False
    if not enabled and not kst.get("disabled_by_guard"):
        box.log("SKIPPED key check: memory search was switched off by someone else; leaving it alone")
        return 0
    agent = default_agent_id(cfg)
    if agent is None:
        box.log("SKIPPED key check: cannot tell which agent is the default (several agents, no default marker, no main)")
        return 0
    own = agent_search(entries(cfg).get(agent))
    if own.get("provider") or own.get("model"):
        box.log("SKIPPED key check: the default agent (%s) has its own memory.search provider" % agent)
        return 0

    orig = kst.get("original") or snapshot(ms)
    chain = chain_of(orig)
    me = ident({"provider": ms.get("provider"), "model": ms.get("model"), "remote": ms.get("remote")})
    cur = next((i for i, c in enumerate(chain) if ident(c) == me), None)
    if cur is None:  # somebody changed the provider by hand since the guard recorded the original
        box.log("memory.search provider changed by someone else; treating %s as the original"
                % label({"provider": ms.get("provider"), "model": ms.get("model")}))
        kst.pop("mm_off", None)
        orig = snapshot(ms)
        chain, cur = chain_of(orig), 0
    if cur == 0:  # on the original: nothing to remember
        kst.pop("original", None)
        orig = snapshot(ms)
    mm_off = kst.get("mm_off", [])

    res = survey(box, cfg, orig, chain, cur, mm_off, agent, sleep)
    states = [r[0] for r in res]
    kst["last_probe"] = {"at": int(box.now), "slots": [
        {"slot": label(chain[i]), "state": r[0], "detail": r[1]} for i, r in enumerate(res)]}
    unusable = [s in UNUSABLE for s in states]
    best = next((i for i, s in enumerate(states) if s == "ok"), None)

    if best is None and all(unusable):
        if enabled:
            box.log("no memory option is usable (%s): turning memory search OFF"
                    % ", ".join("%s %s" % (label(c), s) for c, s in zip(chain, states)))
            if box.patch({"memory": {"search": {"enabled": False}}}, "no usable memory key"):
                kst.update({"disabled_by_guard": True, "since": int(box.now)})
                box.save_state(st)
        else:
            box.log("key check: still nothing usable, memory search stays off")
        if kst.get("disabled_by_guard") and not kst.get("notified"):
            tell_client(box, cfg, chain, res, st)
    elif best is not None and (best <= cur or unusable[cur] or not enabled):
        patch, mm = slot_patch(cfg, orig, chain, best, cur, mm_off)
        if not enabled:
            patch.setdefault("memory", {}).setdefault("search", {})["enabled"] = True
        if merge_patch(copy.deepcopy(cfg), patch) == cfg:
            box.log("key check: %s works - no change" % label(chain[cur]))
        else:
            box.log("%s %s -> %s" % ("moving up:" if best < cur else "backup chain:", label(chain[cur]), label(chain[best])))
            if box.patch(patch, "memory search -> %s" % label(chain[best])):
                if best != cur:
                    if best == 0:
                        kst.pop("original", None)
                    else:
                        kst["original"] = orig
                if mm:
                    kst["mm_off"] = mm
                else:
                    kst.pop("mm_off", None)
                for k in ("disabled_by_guard", "since", "notified"):
                    kst.pop(k, None)
                box.save_state(st)  # recorded the moment the write has landed
                if best != cur:
                    box.log("provider changed: every agent re-indexes once on its next memory use")
    else:
        box.log("key check: %s - no change (memory search %s)"
                % (", ".join("%s %s" % (label(chain[i]), s) for i, s in enumerate(states)), "on" if enabled else "off"))
    box.save_state(st)
    return 0


# ---------------------------------------------------------------- idle guard
class Unreadable(Exception):
    """A worker's activity records could not be read; its switch must not be touched."""


def _ro(path):
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)


def activity(box, aid):
    """(last_activity_epoch, first_seen_epoch) for one agent, from the box's own
    records: transcripts, task runs, cron runs, legacy session files.

    Raises Unreadable on any read error. An error must never look like "no activity":
    that would switch off a worker that is busy."""
    last, first = 0.0, 0.0
    adb = os.path.join(box.root, "agents", aid, "agent", "openclaw-agent.sqlite")
    if os.path.exists(adb):
        try:
            with contextlib.closing(_ro(adb)) as c:
                row = c.execute("select max(created_at), min(created_at) from transcript_events").fetchone()
        except sqlite3.Error as exc:
            raise Unreadable("agent database: %s" % exc)
        if row and row[0]:
            last = max(last, row[0] / 1000.0)
            first = row[1] / 1000.0
    sdb = os.path.join(box.root, "state", "openclaw.sqlite")
    if os.path.exists(sdb):
        try:
            with contextlib.closing(_ro(sdb)) as c:
                for sql in ("select max(created_at) from task_runs where agent_id=?",
                            "select max(started_at_ms) from cron_run_receipts where agent_id=?"):
                    v = c.execute(sql, (aid,)).fetchone()[0]
                    if v:
                        last = max(last, v / 1000.0)
        except sqlite3.Error as exc:
            raise Unreadable("state database: %s" % exc)
    for f in glob.glob(os.path.join(box.root, "agents", aid, "sessions", "*.jsonl")):
        try:
            last = max(last, os.path.getmtime(f))
        except OSError:
            pass
    if not first:
        try:
            first = os.path.getmtime(os.path.join(box.root, "agents", aid))
        except OSError:
            first = box.now
    return last, first


def idle_pass(box, days=IDLE_DAYS_DEFAULT):
    cfg = box.config()
    ok, why = schema_ok(cfg)
    if not ok:
        box.log("SKIPPED idle check: %s" % why)
        return 0
    st = box.state()
    ist = st.setdefault("idle", {})
    owned = ist.setdefault("disabled", {})
    cutoff = box.now - days * 86400
    keep_on = protected_ids(cfg)
    off, on, kept, report, unread = {}, {}, 0, [], []

    for aid, ent in sorted(entries(cfg).items()):
        if not isinstance(ent, dict):
            continue
        ms = agent_search(ent)
        cur = ms.get("enabled")
        if aid in owned and cur is not False:
            owned.pop(aid)  # someone else turned it back on; it is theirs now
            continue
        if aid in keep_on:
            continue
        if aid not in owned and (cur is False or ms.get("provider") or ms.get("model")):
            continue  # someone else's choice: leave it alone
        if box.remaining() < WRITE_RESERVE_S:
            box.log("idle check: time budget nearly used up; the remaining workers are left unchanged this run")
            break
        try:
            last, first = activity(box, aid)
        except Unreadable as exc:
            unread.append(aid)
            box.log("idle check: %s left unchanged this run, cannot read its activity (%s)" % (aid, exc))
            continue
        busy = last >= cutoff or first >= cutoff
        if busy and aid in owned:
            on[aid] = owned[aid].get("before")
            report.append("%s on (active %s)" % (aid, time.strftime("%Y-%m-%d", time.localtime(last or first))))
        elif not busy and aid not in owned:
            off[aid] = cur
            report.append("%s off (last activity %s)" % (aid, time.strftime("%Y-%m-%d", time.localtime(last)) if last else "never"))
        else:
            kept += 1

    if not off and not on:
        box.log("idle check: no change (%d workers checked, %d unreadable)" % (kept, len(unread)))
        box.save_state(st)
        return 0

    patch = {"agents": {"entries": {}}}
    for aid in off:
        patch["agents"]["entries"][aid] = {"memory": {"search": {"enabled": False}}}
    for aid, before in on.items():
        patch["agents"]["entries"][aid] = {"memory": {"search": {"enabled": True if before is True else None}}}
    if box.patch(patch, "idle workers: %d off, %d on" % (len(off), len(on))):
        for aid, before in off.items():
            owned[aid] = {"at": int(box.now), "before": before}
        for aid in on:
            owned.pop(aid, None)
        box.save_state(st)  # recorded the moment the write has landed
        for r in report:
            box.log("idle check: " + r)
    box.save_state(st)
    return 0


def openclaw_ok(box):
    """True when the installed OpenClaw is MIN_OPENCLAW or newer (logs why not)."""
    rc, out, err = box.run_cli(["--version"], timeout=VERSION_TIMEOUT_S)
    m = VERSION_RE.search(out) or VERSION_RE.search(err)
    if not m:
        box.log("SKIPPED: cannot read the OpenClaw version (rc=%s)" % rc)
        return False
    if tuple(int(x) for x in m.groups()) < MIN_OPENCLAW:
        box.log("SKIPPED: OpenClaw %s is older than %s" % (m.group(0), ".".join(map(str, MIN_OPENCLAW))))
        return False
    return True


def status(box):
    print(json.dumps(scrub(box.state()), indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------- self-test
FAKE_CLI = r'''#!/usr/bin/env python3
import json, os, sys, time
d = os.environ["MG_FAKE_DIR"]
args = sys.argv[1:]
def mode_of(name, default=""):
    f = os.path.join(d, name)
    return open(f).read().strip() if os.path.exists(f) else default
open(os.path.join(d, "calls.log"), "a").write(json.dumps(args) + "\n")
open(os.path.join(d, "envs.log"), "a").write(json.dumps({
    "state": os.environ.get("OPENCLAW_STATE_DIR"), "cfg": os.environ.get("OPENCLAW_CONFIG_PATH")}) + "\n")
if args[:1] == ["--version"]:
    print("OpenClaw " + mode_of("version", "2026.10.8") + " (test)"); sys.exit(0)
if args[:2] == ["memory", "status"]:
    if mode_of("hang"):
        time.sleep(float(mode_of("hang")))
    cfgp = os.environ.get("OPENCLAW_CONFIG_PATH") or os.path.join(d, "root", "openclaw.json")
    cfgd = json.load(open(cfgp))
    ms = (cfgd.get("memory") or {}).get("search", {})
    open(os.path.join(d, "seen.log"), "a").write(json.dumps(ms) + "\n")
    ents = (cfgd.get("agents") or {}).get("entries") or {}
    off = sum(1 for e in ents.values() if isinstance(e, dict) and (e.get("enabled") is False or ((e.get("memory") or {}).get("search") or {}).get("enabled") is False))
    open(os.path.join(d, "agentsoff.log"), "a").write(str(off) + "\n")
    if os.path.exists(os.path.join(d, "banner")):
        print("[plugins] 3 loaded"); print("Config warnings: one plugin is disabled")
    if ms.get("enabled") is False:
        print("[]"); sys.exit(0)
    # the OpenRouter slot is provider "openai" + an openrouter.ai endpoint: answer by endpoint
    key = "openrouter" if "openrouter.ai" in str((ms.get("remote") or {}).get("baseUrl")) else str(ms.get("provider"))
    f = os.path.join(d, "probe-" + key)
    mode = open(f if os.path.exists(f) else os.path.join(d, "probe")).read().strip()
    if mode.startswith("UNCONF:"):
        print(json.dumps({"ok": False, "error": {"type": "cli_error", "message": mode[7:]}})); sys.exit(1)
    if mode.startswith("UNCONF-STDERR:"):
        print(json.dumps({"ok": False, "error": {"type": "cli_error", "message": "memory status failed"}}))
        print(mode[14:], file=sys.stderr); sys.exit(1)
    pr = {"ok": True} if mode == "ok" else {"ok": False, "error": mode}
    print(json.dumps([{"agentId": "main", "embeddingProbe": pr}])); sys.exit(0)
if args[:2] == ["config", "patch"]:
    # like the real CLI: with no OPENCLAW_CONFIG_PATH it writes a NEW config somewhere else and exits 0
    target = os.environ.get("OPENCLAW_CONFIG_PATH") or os.path.join(d, "stray", "openclaw.json")
    body = json.loads(sys.stdin.read())
    if mode_of("patchmode") == "swallow":
        sys.exit(0)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    cfg = json.load(open(target)) if os.path.exists(target) else {}
    def merge(a, b):
        for k, v in b.items():
            if v is None: a.pop(k, None)
            elif isinstance(v, dict):
                if not isinstance(a.get(k), dict): a[k] = {}
                merge(a[k], v)
            else: a[k] = v
    merge(cfg, body)
    json.dump(cfg, open(target, "w")); sys.exit(0)
if args[:2] == ["message", "send"]:
    if mode_of("msgmode") == "fail":
        print("telegram: chat not found", file=sys.stderr); sys.exit(1)
    sys.exit(0)
sys.exit(3)
'''

DEAD = "gemini embeddings failed (429): You exceeded your current quota [code=RESOURCE_EXHAUSTED]"
BLIP = "fetch failed: connect ECONNREFUSED 127.0.0.1:11434"
OPENAI_MS = {"provider": "openai", "model": "text-embedding-3-small", "outputDimensionality": 1536,
             "remote": {"baseUrl": "https://example.invalid/v1", "apiKey": "SECRET-REMOTE-KEY",
                        "headers": {"X-Tenant": "stale-header"}},
             "fallback": "gemini"}


def _self_test():
    fails, LOG = [], []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)
            print("\n".join("     log: " + l for l in LOG[-6:]))

    d = tempfile.mkdtemp(prefix="memory-guard-test-")
    try:
        root = os.path.join(d, "root")
        os.makedirs(os.path.join(root, "state"))
        cli = os.path.join(d, "openclaw")
        with open(cli, "w") as f:
            f.write(FAKE_CLI)
        os.chmod(cli, 0o755)
        os.environ["MG_FAKE_DIR"] = d
        os.environ.pop("OPENCLAW_CONFIG_PATH", None)
        now = time.time()
        old, recent = now - 60 * 86400, now - 2 * 86400
        slept = []

        def box(dry=False):
            return Box(root, cli=cli, now=now, dry_run=dry, log=LOG)

        def cfg_now():
            return json.load(open(os.path.join(root, "openclaw.json")))

        def calls():
            p = os.path.join(d, "calls.log")
            return [json.loads(l) for l in open(p)] if os.path.exists(p) else []

        def reset(cfg, default="ok", **probes):
            """Fresh box: this config, no guard state, no call history, these probe answers."""
            json.dump(cfg, open(os.path.join(root, "openclaw.json"), "w"))
            shutil.rmtree(os.path.join(root, "memory-guard"), ignore_errors=True)
            for n in ("calls.log", "seen.log", "agentsoff.log", "envs.log", "banner", "hang", "patchmode", "msgmode", "version"):
                if os.path.exists(os.path.join(d, n)):
                    os.remove(os.path.join(d, n))
            shutil.rmtree(os.path.join(d, "stray"), ignore_errors=True)
            open(os.path.join(d, "probe"), "w").write(default)
            for f in glob.glob(os.path.join(d, "probe-*")):
                os.remove(f)
            for prov, mode in probes.items():
                open(os.path.join(d, "probe-" + prov), "w").write(mode)
            del LOG[:]

        def answer(**probes):
            for prov, mode in probes.items():
                open(os.path.join(d, "probe-" + prov), "w").write(mode)

        def mkcfg(ms, extra=None):
            ents = {"main": {}}
            ents.update(extra or {})
            return {"memory": {"search": copy.deepcopy(ms)},
                    "channels": {"telegram": {"allowFrom": ["5252140759", "123456789"]}},
                    "agents": {"defaults": {}, "entries": ents}}

        def run_key(dry=False):
            n = len(calls())
            del slept[:]
            key_pass(box(dry), sleep=slept.append)
            return calls()[n:]

        def kinds(cs, a, b):
            return [c for c in cs if c[:2] == [a, b]]

        def ms_now():
            return top_search(cfg_now())

        def on(): return ms_now().get("enabled") is not False

        # ---- 1. classifier and chain shape
        check("401 is dead", DEAD_KEY_RE.search("openai embeddings failed (401): Incorrect API key") is not None)
        check("no credits is dead", DEAD_KEY_RE.search("(429): You have no credits remaining") is not None)
        check("timeout is not dead", DEAD_KEY_RE.search("request timed out after 30000ms") is None)
        check("5xx is not dead", DEAD_KEY_RE.search("(503): Service Unavailable") is None)
        names = lambda o: [(c["provider"], c["model"]) for c in chain_of(o)]
        check("chain = original, nemotron, gemini",
              names({"provider": "ollama", "model": "embeddinggemma-2:740m"}) ==
              [("ollama", "embeddinggemma-2:740m"), ("openai", NEMOTRON["model"]), ("gemini", "gemini-embedding-2")])
        check("an original that is already gemini-embedding-2 is not tried twice",
              names({"provider": "gemini", "model": "gemini-embedding-2"}) ==
              [("gemini", "gemini-embedding-2"), ("openai", NEMOTRON["model"])])
        check("an original that is already the nemotron option is not tried twice",
              names({"provider": "openai", "model": NEMOTRON["model"], "remote": NEMOTRON["remote"]}) ==
              [("openai", NEMOTRON["model"]), ("gemini", "gemini-embedding-2")])
        check("the OpenRouter slot lives purely in memory.search: OpenAI-compatible provider, OpenRouter endpoint, env SecretRef",
              NEMOTRON["provider"] == "openai" and NEMOTRON["remote"]["baseUrl"] == "https://openrouter.ai/api/v1"
              and NEMOTRON["remote"]["apiKey"] == {"source": "env", "provider": "default", "id": "OPENROUTER_API_KEY"})

        # ---- 2. two-slot box (original gemini-embedding-2): the simple key story
        gem = {"provider": "gemini", "model": "gemini-embedding-2"}
        reset(mkcfg(gem), default="ok")
        cs = run_key()
        check("healthy key: nothing written", not kinds(cs, "config", "patch") and cfg_now() == mkcfg(gem))
        check("healthy key: settled box probes only the original", len(kinds(cs, "memory", "status")) == 1)

        reset(mkcfg(gem), default=BLIP)
        cs = run_key()
        check("transient failure changes nothing", not kinds(cs, "config", "patch") and on() and not slept)

        reset(mkcfg(gem), default=DEAD)
        run_key(dry=True)
        check("dry run never writes", on() and not kinds(calls(), "config", "patch"))
        cs = run_key()
        sends = kinds(cs, "message", "send")
        check("every option dead: memory search off", ms_now().get("enabled") is False)
        check("every option dead: provider left as it was", (ms_now()["provider"], ms_now()["model"]) == ("gemini", "gemini-embedding-2"))
        check("every option dead: client told exactly once", len(sends) == 1)
        check("message goes to the client chat, never the operator",
              sends and sends[0][sends[0].index("--target") + 1] == "123456789")
        check("message names both providers and where to add funds",
              sends and "Gemini and OpenRouter" in sends[0][-1] and "openrouter.ai/settings/credits" in sends[0][-1])
        check("dead verdicts are confirmed once, 90 s later, with a second probe per option",
              len(kinds(cs, "memory", "status")) == 4 and slept == [CONFIRM_DELAY_S])
        cs = run_key()
        check("still dead: no repeat message", not kinds(cs, "message", "send") and ms_now().get("enabled") is False)
        answer(gemini="ok")
        run_key()
        check("a working key turns memory search back on", ms_now().get("enabled") is True)
        check("guard ownership cleared", not box().state().get("key", {}).get("disabled_by_guard"))

        c = cfg_now(); c["memory"]["search"]["enabled"] = False
        json.dump(c, open(os.path.join(root, "openclaw.json"), "w"))
        run_key()
        check("a switch someone else turned off is never turned back on", ms_now().get("enabled") is False)

        # ---- 3. three-slot box (original openai): the backup chain
        reset(mkcfg(OPENAI_MS), default="ok", openai=DEAD, openrouter="ok")
        cs = run_key()
        m = ms_now()
        check("original dead -> nemotron chosen", (m["provider"], m["model"]) == ("openai", NEMOTRON["model"]))
        check("nemotron slot is exactly the OpenRouter endpoint + env SecretRef, no literal key anywhere",
              m["remote"] == NEMOTRON["remote"] and "SECRET-REMOTE-KEY" not in json.dumps(cfg_now()))
        check("switch is ONE config patch and no client message",
              len(kinds(cs, "config", "patch")) == 1 and not kinds(cs, "message", "send"))
        check("the old provider's credential, headers and vector size do not survive the switch",
              "outputDimensionality" not in m and "headers" not in m["remote"] and "stale-header" not in json.dumps(m))
        check("memory.search.fallback is never edited", m.get("fallback") == "gemini")
        check("memory search stays on", on())
        check("the original is remembered, extras included",
              box().state()["key"]["original"] == {k: OPENAI_MS[k] for k in ("provider", "model", "remote", "outputDimensionality")})
        seen = [json.loads(l) for l in open(os.path.join(d, "seen.log"))]
        check("the nemotron probe ran on the OpenRouter endpoint with no stale remote key and no fallback",
              any(s.get("remote") == NEMOTRON["remote"] and s.get("fallback") == "none" and "outputDimensionality" not in s
                  for s in seen))
        check("the provider switch is logged as a one-time re-index", any("re-indexes once" in l for l in LOG))

        cs = run_key()
        check("settled on the backup: no write, no wait", not kinds(cs, "config", "patch") and not slept)
        check("settled on the backup: original is re-tried each night, backup stays",
              len(kinds(cs, "memory", "status")) == 2 and ms_now()["model"] == NEMOTRON["model"])

        answer(openai="ok")
        cs = run_key()
        m = ms_now()
        check("original recovers -> moved back up, one patch", len(kinds(cs, "config", "patch")) == 1 and m["provider"] == "openai")
        check("original comes back exactly as it was",
              m == OPENAI_MS and "original" not in box().state()["key"])
        check("the restored credential never reaches the log",
              not any("SECRET-REMOTE-KEY" in l for l in LOG) and any("<redacted>" in l for l in LOG))

        reset(mkcfg(OPENAI_MS), default="ok", openai=DEAD, openrouter=DEAD, gemini="ok")
        run_key()
        m = ms_now()
        check("original + nemotron dead -> gemini chosen", (m["provider"], m["model"]) == ("gemini", "gemini-embedding-2"))
        check("gemini gets no stale remote", "remote" not in m and "outputDimensionality" not in m and on())
        answer(openrouter="ok")
        run_key()
        check("nemotron recovers -> moved up from gemini",
              ms_now()["model"] == NEMOTRON["model"] and ms_now()["remote"] == NEMOTRON["remote"])

        reset(mkcfg(OPENAI_MS), default=DEAD)
        cs = run_key()
        sends = kinds(cs, "message", "send")
        check("all three dead -> memory search off, one client message",
              ms_now().get("enabled") is False and len(sends) == 1 and ms_now()["provider"] == "openai")
        check("all three dead: three options probed twice", len(kinds(cs, "memory", "status")) == 6)
        check("message names all three providers", sends and "OpenAI, OpenRouter and Gemini" in sends[0][-1])
        answer(gemini="ok")
        run_key()
        check("any option working turns memory search back on, on that option",
              on() and ms_now()["provider"] == "gemini")

        # ---- 4. transient never switches
        reset(mkcfg(OPENAI_MS), default="ok", openai="(503): Service Unavailable", openrouter="ok", gemini="ok")
        cs = run_key()
        check("original transient (a lower option works): nothing changes",
              not kinds(cs, "config", "patch") and cfg_now() == mkcfg(OPENAI_MS) and not slept)
        reset(mkcfg(OPENAI_MS), default=DEAD, openrouter="request timed out after 30000ms")
        cs = run_key()
        check("one option transient, rest dead: not 'all dead', memory search stays on",
              not kinds(cs, "config", "patch") and on() and not kinds(cs, "message", "send"))
        reset(mkcfg(OPENAI_MS), default="ok", openai="(401): Incorrect API key", openrouter="timed out", gemini="ok")
        run_key()
        check("a transient middle option is skipped, first PASSING option wins", ms_now()["provider"] == "gemini")

        reset(mkcfg(OPENAI_MS), default="ok", openai=DEAD, openrouter="ok")
        open(os.path.join(d, "banner"), "w").write("1")
        run_key()
        check("banner lines before the JSON do not hide the verdict", ms_now()["model"] == NEMOTRON["model"])

        # ---- 5. someone else changes the provider, or the default agent has its own
        reset(mkcfg(OPENAI_MS), default="ok", openai=DEAD, openrouter="ok")
        run_key()
        c = cfg_now(); c["memory"]["search"].update({"provider": "voyage", "model": "voyage-3"})
        json.dump(c, open(os.path.join(root, "openclaw.json"), "w"))
        cs = run_key()
        check("provider changed by hand: record dropped, new setting is the original",
              "original" not in box().state()["key"] and ms_now()["provider"] == "voyage" and not kinds(cs, "config", "patch"))
        reset(mkcfg(OPENAI_MS, {"main": {"memory": {"search": {"provider": "ollama"}}}}), default=DEAD)
        cs = run_key()
        check("default agent with its own provider: key check skipped", not cs and on())

        # ---- 6. multimodal is held off on a text-only backup and put back with gemini
        mm = lambda a: ((a.get("memory") or {}).get("search") or {}).get("multimodal", {}).get("enabled")
        ents = {"dept-a": {"memory": {"search": {"multimodal": {"enabled": True}}}},
                "dept-own": {"memory": {"search": {"provider": "voyage", "multimodal": {"enabled": True}}}}}
        reset(mkcfg(dict(gem, multimodal={"enabled": True}), ents), default="ok", gemini=DEAD, openrouter="ok")
        run_key()
        c = cfg_now()
        check("text-only backup: multimodal off at top level and on inheriting agents",
              mm(c) is False and mm(c["agents"]["entries"]["dept-a"]) is False)
        check("an agent with its own provider keeps its multimodal setting", mm(c["agents"]["entries"]["dept-own"]) is True)
        check("only what the guard held off is recorded", box().state()["key"]["mm_off"] == ["", "dept-a"])
        answer(gemini="ok")
        run_key()
        c = cfg_now()
        check("back on gemini: multimodal put back, record cleared",
              ms_now()["provider"] == "gemini" and ms_now()["multimodal"]["enabled"] is True
              and mm(c["agents"]["entries"]["dept-a"]) is True and "mm_off" not in box().state()["key"])

        # ---- 6b. a backup that cannot be used at all (no key, unknown provider) is unusable, not "no answer"
        reset(mkcfg(OPENAI_MS))
        for text in ('No API key found for provider "google". Auth store: /x/agent.sqlite',
                     "Unknown memory embedding provider: openrouter",
                     "openai embedding credentials are not configured for https://openrouter.ai/api/v1. "
                     "Set memory.search.remote.apiKey or an Authorization header for this destination."):
            answer(openai="UNCONF:" + text)
            check("unconfigured: %s" % text[:46], probe(box(), "main", mkcfg(OPENAI_MS))[0] == "unconfigured")
        answer(openai='UNCONF-STDERR:[secrets] failed to resolve memory.search.remote.apiKey locally '
                      '(Environment variable "OPENROUTER_API_KEY" is missing or empty.)')
        check("unconfigured: env variable missing (stderr only)", probe(box(), "main", mkcfg(OPENAI_MS))[0] == "unconfigured")
        answer(openai="UNCONF:Config invalid: agents.ownership must be explicit")
        check("a CLI error that is not about keys is not 'unconfigured'", probe(box(), "main", mkcfg(OPENAI_MS))[0] == "transient" or probe(box(), "main", mkcfg(OPENAI_MS))[0] == "none")

        NOKEY = ("openai embedding credentials are not configured for https://openrouter.ai/api/v1. "
                 "Set memory.search.remote.apiKey or an Authorization header for this destination.")
        reset(mkcfg(gem), default=DEAD, openrouter="UNCONF:" + NOKEY)
        cs = run_key()
        sends = kinds(cs, "message", "send")
        check("dead primary + unconfigured backup: memory search goes off (it used to keep hammering the dead key)",
              ms_now().get("enabled") is False and len(kinds(cs, "config", "patch")) == 1)
        check("... and the client is told once, naming only the key that is really dead",
              len(sends) == 1 and "(Gemini)" in sends[0][-1] and "OpenRouter" not in sends[0][-1])
        check("an unconfigured option is not re-probed or waited for (3 probes, one 90 s wait)",
              len(kinds(cs, "memory", "status")) == 3 and slept == [CONFIRM_DELAY_S])

        reset(mkcfg(gem), default='UNCONF:No API key found for provider "google".')
        cs = run_key()
        sends = kinds(cs, "message", "send")
        check("no usable key anywhere: off, one notice, no waiting (nothing is 'dead', nothing to confirm)",
              ms_now().get("enabled") is False and len(sends) == 1 and not slept and "no working key" in sends[0][-1])

        reset(mkcfg(OPENAI_MS), default="ok", openai=DEAD, openrouter="UNCONF:" + NOKEY, gemini="ok")
        run_key()
        check("dead primary, unconfigured OpenRouter, working Gemini: Gemini is chosen", ms_now()["provider"] == "gemini")
        reset(mkcfg(OPENAI_MS), default="ok", openai="UNCONF:No API key found for provider \"openai\".", openrouter="ok")
        run_key()
        check("a primary that has no key at all falls through to the backup", ms_now()["model"] == NEMOTRON["model"])
        reset(mkcfg(OPENAI_MS), default="UNCONF:" + NOKEY, openai=BLIP)
        cs = run_key()
        check("a transient outage on the primary is not turned into 'all dead' by unconfigured backups",
              not kinds(cs, "config", "patch") and on() and not kinds(cs, "message", "send"))

        # ---- 6b2. a model or endpoint that is gone for good is unusable too; network trouble never is
        reset(mkcfg(OPENAI_MS))
        for text in ("openai embeddings failed (model: nvidia/x:free, batch size: 1) (400): Model nvidia/x does not exist",
                     "openai embeddings failed (404): No endpoints found for nvidia/nemotron-3.5-embed-1b:free.",
                     "gemini embeddings failed (404): models/gemini-embedding-9 is not found for API version v1beta",
                     "openai embeddings failed (400): invalid model ID",
                     "openai embeddings failed (404): The model `text-embedding-ada-001` has been deprecated",
                     "(404) model_not_found: The model does not exist or you do not have access to it"):
            answer(openai=text)
            check("model gone: %s" % text[:58], probe(box(), "main", mkcfg(OPENAI_MS))[0] == "gone")
        for text in ("fetch failed | bad port", "request timed out after 30000ms", "(503): Service Unavailable",
                     "(429): Rate limit exceeded: free-models-per-day", "(502): model overloaded, retry later",
                     "(500): model not found in cache, retrying", "connect ECONNREFUSED 127.0.0.1:11434",
                     "(404): Not Found", "(400): input is too long"):
            answer(openai=text)
            check("never 'gone': %s" % text[:58], probe(box(), "main", mkcfg(OPENAI_MS))[0] == "transient")

        GONE = "openai embeddings failed (404): No endpoints found for nvidia/nemotron-3.5-embed-1b:free."
        NOGEMINI = "UNCONF:No API key found for provider \"google\"."
        reset(mkcfg(OPENAI_MS), default="ok", openai=DEAD, openrouter=GONE, gemini=NOGEMINI)
        cs = run_key()
        sends = kinds(cs, "message", "send")
        check("dead primary + retired OpenRouter model + unconfigured Gemini: memory search off, one notice (it used to retry forever)",
              ms_now().get("enabled") is False and len(sends) == 1 and len(kinds(cs, "config", "patch")) == 1)
        check("... the notice names the dead key only, not the retired model or the missing key",
              sends and "(OpenAI)" in sends[0][-1] and "OpenRouter" not in sends[0][-1] and "Gemini" not in sends[0][-1])
        check("... a 'gone' verdict is confirmed like a dead key (5 probes, one 90 s wait)",
              len(kinds(cs, "memory", "status")) == 5 and slept == [CONFIRM_DELAY_S])
        reset(mkcfg(OPENAI_MS), default="ok", openai=DEAD, openrouter=GONE, gemini="ok")
        run_key()
        check("dead primary, retired OpenRouter model, working Gemini: Gemini is chosen", ms_now()["provider"] == "gemini")
        reset(mkcfg(OPENAI_MS), default="ok", openai="openai embeddings failed (404): model_not_found", openrouter="ok")
        run_key()
        check("a primary whose model is retired falls through to the backup", ms_now()["model"] == NEMOTRON["model"])
        reset(mkcfg(OPENAI_MS), default="ok", openai=DEAD, openrouter="(429): Rate limit exceeded: free-models-per-day", gemini=NOGEMINI)
        cs = run_key()
        check("a rate-limited backup is transient: nothing is switched off",
              not kinds(cs, "config", "patch") and on() and not kinds(cs, "message", "send"))
        reset(mkcfg(OPENAI_MS), default="ok", openai=DEAD, openrouter="(503): No endpoints found for nvidia/nemotron-3.5-embed-1b:free", gemini=NOGEMINI)
        cs = run_key()
        check("'no endpoints found' behind a 503 is transient: nothing is switched off",
              not kinds(cs, "config", "patch") and on() and not kinds(cs, "message", "send"))

        # ---- 6b3. the probe copy carries no per-agent off switches (they poison the shared SecretRef check)
        off_cfg = mkcfg(OPENAI_MS, {"w-off": {"memory": {"search": {"enabled": False}}}, "w-dead": {"enabled": False}, "w-on": {}})
        pc = probe_cfg(off_cfg, {}, "main")
        check("probe config: no agent keeps an off switch, memory search forced on, no fallback",
              all("enabled" not in agent_search(e) and e.get("enabled") is not False for e in entries(pc).values())
              and pc["memory"]["search"]["enabled"] is True and pc["memory"]["search"]["fallback"] == "none")
        check("... and the real config is not touched by building it",
              agent_search(off_cfg["agents"]["entries"]["w-off"]).get("enabled") is False and off_cfg["agents"]["entries"]["w-dead"]["enabled"] is False)
        reset(off_cfg, default="ok", openai=DEAD, openrouter="ok")
        run_key()
        seen = [json.loads(l) for l in open(os.path.join(d, "seen.log"))]
        offs = [int(l) for l in open(os.path.join(d, "agentsoff.log"))]
        check("every probe actually run was given such a copy (the fake counts the off switches in the file the CLI was handed)",
              seen and offs and set(offs) == {0} and all(sm.get("enabled") is True for sm in seen)
              and ms_now()["model"] == NEMOTRON["model"] and agent_search(entries(cfg_now())["w-off"]).get("enabled") is False)

        # ---- 6c. every CLI call names the box's state dir and config; a write must land
        reset(mkcfg(OPENAI_MS), default="ok", openai=DEAD, openrouter="ok")
        cs = run_key()
        envs = [json.loads(l) for l in open(os.path.join(d, "envs.log"))]
        real_cfg = os.path.join(root, "openclaw.json")
        check("every CLI call carries OPENCLAW_STATE_DIR = the box root", envs and all(e["state"] == root for e in envs))
        check("the write targets the real config; probes a read-only copy",
              all((e["cfg"] == real_cfg) == (c[:2] != ["memory", "status"]) for c, e in zip(cs, envs)))
        check("nothing was created outside the box (the sandbox bug)", not os.path.exists(os.path.join(d, "stray")))
        reset(mkcfg(OPENAI_MS), default="ok", openai=DEAD, openrouter="ok")
        open(os.path.join(d, "patchmode"), "w").write("swallow")
        before = cfg_now()
        run_key()
        check("a patch that exits 0 but changes nothing is a FAIL: config, state and 'original' untouched",
              cfg_now() == before and "original" not in box().state().get("key", {})
              and any("did not change" in l for l in LOG))
        os.remove(os.path.join(d, "patchmode"))
        run_key()
        check("... and the next night's run does the switch", ms_now()["model"] == NEMOTRON["model"])

        # ---- 6d. the client notice is retried until one send succeeds
        reset(mkcfg(gem), default=DEAD)
        open(os.path.join(d, "msgmode"), "w").write("fail")
        cs = run_key()
        check("send failed: memory search is off, notice not recorded",
              ms_now().get("enabled") is False and "notified" not in box().state()["key"] and len(kinds(cs, "message", "send")) == 1)
        cs = run_key()
        check("still failing next night: tried again", len(kinds(cs, "message", "send")) == 1 and "notified" not in box().state()["key"])
        os.remove(os.path.join(d, "msgmode"))
        cs = run_key()
        check("a later night's send succeeds and is recorded", len(kinds(cs, "message", "send")) == 1 and box().state()["key"].get("notified"))
        cs = run_key()
        check("... and then never again for the same episode", not kinds(cs, "message", "send"))
        c = mkcfg(gem); c["channels"] = {"telegram": {"allowFrom": ["5252140759"]}}  # operator chat only = no client chat
        reset(c, default=DEAD)
        cs = run_key()
        check("no client chat: nothing sent, not recorded", not kinds(cs, "message", "send") and "notified" not in box().state()["key"])
        c = cfg_now(); c["channels"] = {"telegram": {"allowFrom": ["123456789"]}}
        json.dump(c, open(os.path.join(root, "openclaw.json"), "w"))
        cs = run_key()
        check("chat appears later: sent exactly once", len(kinds(cs, "message", "send")) == 1 and box().state()["key"].get("notified"))

        # ---- 6e. provider error text never stores or prints key-like strings
        MASK = ("Incorrect API key provided: sk-abcd1234efgh***wxyz1234. AIzaSyA1234567890abcdefghijklmnopqrstuv "
                "is not valid (401)")
        reset(mkcfg(gem), default=MASK)
        run_key()
        stored = open(os.path.join(root, "memory-guard", "state.json")).read()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status(box())
        check("state.json and `status` hold no key-like text",
              all(x not in stored + buf.getvalue() for x in ("sk-abcd", "AIzaSyA", "wxyz1234")))
        check("... but the verdict text is still readable", "Incorrect API key provided" in stored)

        # ---- 6f. the default agent is the one OpenClaw would pick
        mk = lambda ents, **ag: {"agents": dict(ag, entries=ents)}
        check("default: agents.defaults.systemAgent.agentId wins",
              default_agent_id(mk({"a": {}, "ceo": {}}, defaults={"systemAgent": {"agentId": "CEO"}})) == "ceo")
        check("default: the single default:true marker", default_agent_id(mk({"a": {}, "b": {"default": True}})) == "b")
        check("default: explicit ownership ignores markers", default_agent_id(mk({"b": {"default": True}, "main": {}, "c": {}}, ownership="explicit")) == "main")
        check("default: the only agent", default_agent_id(mk({"solo": {}})) == "solo")
        check("default: no entries -> main", default_agent_id(mk({})) == "main")
        check("default: two markers and no main cannot be told", default_agent_id(mk({"a": {"default": True}, "b": {"default": True}})) is None)
        check("default: several agents, no main, no marker cannot be told", default_agent_id(mk({"a": {}, "b": {}})) is None)
        c = mk({"ceo": {"default": True}, "w1": {}}); c["memory"] = {"search": dict(gem)}
        reset(c, default="ok")
        cs = run_key()
        probes_ = kinds(cs, "memory", "status")
        check("probe runs for the configured default agent, not the first entry or main",
              probes_ and probes_[0][probes_[0].index("--agent") + 1] == "ceo")
        c = mk({"a": {}, "b": {}}); c["memory"] = {"search": dict(gem)}
        reset(c, default=DEAD)
        cs = run_key()
        check("default agent cannot be told: key check skipped, no call", not cs and any("cannot tell which agent" in l for l in LOG))

        # ---- 7. idle pass
        idle_cfg = {
            "memory": {"search": {"provider": "gemini", "model": "gemini-embedding-2"}},
            "agents": {"defaults": {}, "entries": {
                "main": {}, "dept-master-orchestrator": {}, "dept-busy": {}, "dept-sleepy": {},
                "dept-new": {}, "dept-manual-off": {"memory": {"search": {"enabled": False}}},
                "dept-own-provider": {"memory": {"search": {"provider": "openai"}}},
            }},
        }
        reset(idle_cfg)
        for aid, created in (("dept-busy", recent), ("dept-sleepy", old), ("dept-manual-off", old),
                             ("dept-own-provider", old), ("dept-master-orchestrator", old), ("main", old)):
            p = os.path.join(root, "agents", aid, "agent")
            os.makedirs(p)
            with sqlite3.connect(os.path.join(p, "openclaw-agent.sqlite")) as c:
                c.execute("create table transcript_events(created_at integer)")
                c.execute("insert into transcript_events values (?)", (int(created * 1000),))
        os.makedirs(os.path.join(root, "agents", "dept-new"))  # brand-new, no records
        idle_pass(box())
        e = entries(cfg_now())
        check("sleeping worker turned off", agent_search(e["dept-sleepy"]).get("enabled") is False)
        check("busy worker kept on", agent_search(e["dept-busy"]).get("enabled") is not False)
        check("main always on", agent_search(e["main"]).get("enabled") is not False)
        check("master orchestrator always on", agent_search(e["dept-master-orchestrator"]).get("enabled") is not False)
        check("worker younger than the window kept on", agent_search(e["dept-new"]).get("enabled") is not False)
        check("agent with its own provider left alone", "enabled" not in agent_search(e["dept-own-provider"]))
        check("manual per-agent off left alone", agent_search(e["dept-manual-off"]).get("enabled") is False)
        check("guard records only what it switched", set(box().state()["idle"]["disabled"]) == {"dept-sleepy"})
        with sqlite3.connect(os.path.join(root, "agents", "dept-sleepy", "agent", "openclaw-agent.sqlite")) as c2:
            c2.execute("insert into transcript_events values (?)", (int((now - 3600) * 1000),))
        idle_pass(box())
        e = entries(cfg_now())
        check("worker back on after new activity", "enabled" not in agent_search(e["dept-sleepy"]))
        check("guard state cleared after re-enable", not box().state()["idle"]["disabled"])

        # ---- 7b. unreadable activity records must never read as "idle"
        def mkdb(aid, created, valid=True, table="transcript_events"):
            p = os.path.join(root, "agents", aid, "agent")
            os.makedirs(p, exist_ok=True)
            dbp = os.path.join(p, "openclaw-agent.sqlite")
            if os.path.exists(dbp):
                os.remove(dbp)
            if valid:
                with sqlite3.connect(dbp) as c:
                    c.execute("create table %s(created_at integer)" % table)
                    c.execute("insert into %s values (?)" % table, (int(created * 1000),))
            else:
                open(dbp, "wb").write(b"this is not a sqlite database" * 20)
            os.utime(os.path.join(root, "agents", aid), (created, created))  # directory looks old too
            os.utime(p, (created, created))

        sick_cfg = {"memory": {"search": {"provider": "gemini", "model": "gemini-embedding-2"}},
                    "agents": {"defaults": {}, "entries": {"main": {}, "dept-corrupt": {}, "dept-notable": {},
                                                          "dept-fine-old": {}, "dept-owned": {}}}}
        reset(sick_cfg)
        mkdb("dept-corrupt", old, valid=False)  # busy, but its records are unreadable and its folder looks old
        mkdb("dept-notable", old, table="something_else")
        mkdb("dept-fine-old", old)
        mkdb("dept-owned", old)
        idle_pass(box())
        e = entries(cfg_now())
        check("corrupt activity database: the worker is left on", agent_search(e["dept-corrupt"]).get("enabled") is not False)
        check("database without the transcript table: the worker is left on", agent_search(e["dept-notable"]).get("enabled") is not False)
        check("a healthy idle worker is still turned off in the same run", agent_search(e["dept-fine-old"]).get("enabled") is False)
        check("each skipped worker is logged", sum("left unchanged this run, cannot read" in l for l in LOG) == 2)
        check("skipped workers are not recorded as guard-disabled", set(box().state()["idle"]["disabled"]) == {"dept-fine-old", "dept-owned"})
        mkdb("dept-owned", old, valid=False)
        idle_pass(box())
        e = entries(cfg_now())
        check("a worker the guard already turned off stays off (and recorded) when its records cannot be read",
              agent_search(e["dept-owned"]).get("enabled") is False and "dept-owned" in box().state()["idle"]["disabled"])
        mkdb("dept-owned", recent)
        idle_pass(box())
        check("... and comes back when its records are readable and show activity",
              "enabled" not in agent_search(entries(cfg_now())["dept-owned"]))

        # the state database: cron runs and task runs count as activity; a read error there is still not "idle"
        sdb = os.path.join(root, "state", "openclaw.sqlite")
        state_cfg = {"memory": {"search": {"provider": "gemini", "model": "gemini-embedding-2"}},
                     "agents": {"defaults": {}, "entries": {"main": {}, "dept-cron": {}, "dept-quiet": {}}}}
        mkdb("dept-cron", old)
        mkdb("dept-quiet", old)
        reset(state_cfg)
        with sqlite3.connect(sdb) as c:
            c.execute("create table task_runs(agent_id text, created_at integer)")
            c.execute("create table cron_run_receipts(agent_id text, started_at_ms integer)")
            c.execute("insert into cron_run_receipts values (?, ?)", ("dept-cron", int((now - 3600) * 1000)))
        idle_pass(box())
        e = entries(cfg_now())
        check("a worker with old transcripts but a recent cron run stays on", agent_search(e["dept-cron"]).get("enabled") is not False)
        check("a worker with nothing anywhere is turned off", agent_search(e["dept-quiet"]).get("enabled") is False)
        os.remove(sdb)
        open(sdb, "wb").write(b"this is not a sqlite database" * 20)
        reset(state_cfg)
        idle_pass(box())
        e = entries(cfg_now())
        check("state database unreadable: no worker is switched off on a guess",
              all(agent_search(e[a]).get("enabled") is not False for a in ("dept-cron", "dept-quiet"))
              and sum("cannot read its activity" in l for l in LOG) == 2)
        os.remove(sdb)

        # agents the idle check must never touch, even when the default cannot be worked out
        prot_cfg = {"memory": {"search": {"provider": "gemini", "model": "gemini-embedding-2"}},
                    "agents": {"defaults": {"systemAgent": {"agentId": "Sys"}},
                               "entries": {"alpha": {"default": True}, "beta": {"default": True}, "sys": {},
                                           "dept-master-orchestrator": {}, "dept-plain": {}}}}
        check("protected: every default marker, the system agent and the orchestrator",
              protected_ids(prot_cfg) == {"main", "alpha", "beta", "sys", "dept-master-orchestrator"})
        marker_cfg = {"memory": prot_cfg["memory"], "agents": {"defaults": {}, "entries": {
            "alpha": {"default": True}, "beta": {"default": True}, "dept-plain": {}}}}
        check("two default markers and no main: default really is unknown", default_agent_id(marker_cfg) is None)
        for aid in ("alpha", "beta", "dept-plain"):
            mkdb(aid, old)
        reset(marker_cfg)
        idle_pass(box())
        e = entries(cfg_now())
        check("idle pass: agents marked default:true stay on when the default cannot be determined",
              all(agent_search(e[a]).get("enabled") is not False for a in ("alpha", "beta")))
        check("... while an ordinary idle worker is still turned off", agent_search(e["dept-plain"]).get("enabled") is False)
        sys_cfg = {"memory": prot_cfg["memory"], "agents": {"defaults": {"systemAgent": {"agentId": "SYS"}},
                   "entries": {"sys": {}, "dept-plain": {}}}}
        mkdb("sys", old)
        reset(sys_cfg)
        idle_pass(box())
        e = entries(cfg_now())
        real_default = default_agent_id
        globals()["default_agent_id"] = lambda cfg: None  # whatever the default resolver says, these stay protected
        try:
            blind = protected_ids(prot_cfg)
        finally:
            globals()["default_agent_id"] = real_default
        check("protection does not depend on the default resolver working: markers, system agent, orchestrator, main",
              blind == {"main", "alpha", "beta", "sys", "dept-master-orchestrator"})
        check("idle pass: the configured system agent stays on",
              agent_search(e["sys"]).get("enabled") is not False and agent_search(e["dept-plain"]).get("enabled") is False)

        class Boom(Box):
            def log(self, msg):
                if "re-indexes once" in msg or " off (last activity" in msg:
                    raise RuntimeError("killed right after the write")
                Box.log(self, msg)

        reset(mkcfg(OPENAI_MS), default="ok", openai=DEAD, openrouter="ok")
        try:
            key_pass(Boom(root, cli=cli, now=now, log=LOG), sleep=slept.append)
        except RuntimeError:
            pass
        check("key check: state is on disk the moment the write lands (a kill right after loses nothing)",
              box().state().get("key", {}).get("original", {}).get("model") == "text-embedding-3-small")
        reset(sick_cfg)
        try:
            idle_pass(Boom(root, cli=cli, now=now, log=LOG))
        except RuntimeError:
            pass
        check("idle check: state is on disk the moment the write lands", "dept-fine-old" in box().state().get("idle", {}).get("disabled", {}))

        # ---- 7c. a run always ends inside the cron's timeout
        check("budget is under the 600 s cron command timeout", TOTAL_BUDGET_S <= 560 and PROBE_TIMEOUT_S * 2 + CONFIRM_DELAY_S < TOTAL_BUDGET_S)
        reset(mkcfg(gem))
        open(os.path.join(d, "hang"), "w").write("30")
        t0 = time.time()
        rc_, _, err_ = Box(root, cli=cli, now=now, log=LOG, deadline=time.time() + 4).run_cli(["memory", "status"], timeout=60)
        check("a CLI call is cut off at the time budget, not at its own timeout", rc_ == 124 and time.time() - t0 < 15)
        os.remove(os.path.join(d, "hang"))
        reset(mkcfg(gem), default=DEAD)
        del slept[:]
        key_pass(Box(root, cli=cli, now=now, log=LOG, deadline=time.time() - 1), sleep=slept.append)
        check("budget used up: nothing changes, no message", not kinds(calls(), "config", "patch") and not kinds(calls(), "message", "send") and on())
        reset(mkcfg(gem), default=DEAD)
        del slept[:]
        key_pass(Box(root, cli=cli, now=now, log=LOG, deadline=time.time() + 120), sleep=slept.append)
        check("a dead verdict is not acted on when its confirmation would not fit the budget",
              not slept and on() and not kinds(calls(), "config", "patch") and any("too little of the time budget" in l for l in LOG))

        # ---- 7d. root is refused
        reset(mkcfg(gem), default=DEAD)
        real_euid, buf = os.geteuid, io.StringIO()
        os.geteuid = lambda: 0
        try:
            with contextlib.redirect_stdout(buf):
                rc_ = main(["run"])
        finally:
            os.geteuid = real_euid
        check("run as root: exit 2, REFUSED, no CLI call at all", rc_ == 2 and "REFUSED" in buf.getvalue() and not calls())

        # ---- 8. older config shape and older OpenClaw: skipped, untouched
        legacy = {"agents": {"list": [{"id": "main"}], "defaults": {"memorySearch": {"enabled": True}}}}
        reset(legacy)
        key_pass(box()); idle_pass(box())
        check("older config shape is skipped without any call", not calls() and cfg_now() == legacy)
        for ver, want in (("2026.10.5", True), ("2026.10.8", True), ("2026.11.2", True), ("2027.1.1", True),
                          ("2026.10.4", False), ("2026.9.30", False), ("garbage", False)):
            open(os.path.join(d, "version"), "w").write(ver)
            check("OpenClaw %s %s" % (ver, "runs" if want else "is skipped"), openclaw_ok(box()) is want)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("self-test: %d failure(s)" % len(fails))
    return 1 if fails else 0


# ---------------------------------------------------------------- main
def main(argv):
    if "--self-test" in argv:
        return _self_test()
    ap = argparse.ArgumentParser(prog="memory-guard.py")
    ap.add_argument("cmd", choices=["run", "key", "idle", "status"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--days", type=int, default=IDLE_DAYS_DEFAULT)
    a = ap.parse_args(argv)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("[memory-guard] REFUSED: run as the box user, never root (a root-owned config freezes the gateway)")
        return 2
    root = oc_root()
    if not os.path.exists(os.path.join(root, "openclaw.json")) and not os.environ.get("OPENCLAW_CONFIG_PATH"):
        print("[memory-guard] SKIPPED: no openclaw.json under %s" % root)
        return 0
    deadline = time.time() + TOTAL_BUDGET_S  # one budget for the whole run, shared by both checks
    box = Box(root, cli=os.environ.get("OPENCLAW_BIN", "openclaw"), dry_run=a.dry_run, deadline=deadline)
    try:
        if a.cmd == "status":
            return status(box)
        if not openclaw_ok(box):
            return 0
        rc = 0
        if a.cmd in ("run", "key"):
            rc |= key_pass(box)
        if a.cmd in ("run", "idle"):
            box = Box(root, cli=box.cli, dry_run=a.dry_run, deadline=deadline)  # re-read config after any key write
            rc |= idle_pass(box, a.days)
        return rc
    except Exception as exc:  # report, never crash silently
        box.log("ERROR %s: %s" % (type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
