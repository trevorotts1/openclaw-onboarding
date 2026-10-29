#!/usr/bin/env python3
"""memory-guard.py - nightly, zero-model guard for OpenClaw memory search.

Two jobs, both deterministic (no model turn, no tokens):

  key   - Tests the box's memory-search embedding key with OpenClaw's own probe
          (`openclaw memory status --deep --json` -> embeddingProbe). When the
          provider memory search is using is DEAD (key rejected, out of credit,
          out of quota; confirmed by a second probe 90 s later) the guard walks a
          fixed backup chain and uses the first option whose probe passes:
            1. the box's original provider/model (whatever it had before the
               guard first touched it; on a Mac, the Skill 76 local Ollama model)
            2. OpenRouter nvidia/nemotron-3.5-embed-1b:free
            3. Gemini gemini-embedding-2
          One `config patch` switches provider + model. If all of them are dead,
          memory search goes OFF for the whole box (so it stops retrying a dead
          key in a loop) and the box's own Telegram bot tells the client to add
          funds. Every night the guard also tries to climb back UP the chain, and
          turns memory search back on when something works again. A transient
          failure (network, timeout, 5xx, local Ollama down) changes nothing.
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
import copy
import glob
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
PROBE_TIMEOUT_S = 180
# 2026.10.4 and older restart the serving Gateway on any memory.search provider/model/enabled change; 2026.10.5+ hot-reload it.
MIN_OPENCLAW = (2026, 10, 5)
ALWAYS_ON_IDS = {"main"}
ALWAYS_ON_PATTERNS = ("master-orchestrator",)
OPERATOR_CHAT_IDS = {"5252140759", "6663821679", "6771245262"}

VERSION_RE = re.compile(r"\b(20\d\d)\.(\d{1,2})\.(\d{1,2})\b")

# The backup chain after the box's own (original) provider/model, in the owner-approved order.
NEMOTRON = {"provider": "openrouter", "model": "nvidia/nemotron-3.5-embed-1b:free"}
GEMINI = {"provider": "gemini", "model": "gemini-embedding-2"}
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


def scrub(o):
    if isinstance(o, dict):
        return {k: ("<redacted>" if k in SECRET_KEYS and v is not None else scrub(v)) for k, v in o.items()}
    return [scrub(x) for x in o] if isinstance(o, list) else o


class Box:
    def __init__(self, root, cli="openclaw", now=None, dry_run=False, log=None):
        self.root = root
        self.cfg_path = os.environ.get("OPENCLAW_CONFIG_PATH") or os.path.join(root, "openclaw.json")
        self.state_dir = os.path.join(root, "memory-guard")
        self.state_path = os.path.join(self.state_dir, "state.json")
        self.log_path = os.path.join(root, "logs", "memory-guard.log")
        self.cli = cli
        self.now = now or time.time()
        self.dry_run = dry_run
        self._log = log

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
        e = dict(os.environ)
        if env:
            e.update(env)
        try:
            p = subprocess.run([self.cli] + args, input=stdin, capture_output=True,
                               text=True, timeout=timeout, env=e)
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return 124, "", "timeout after %ss" % timeout
        except OSError as exc:
            return 127, "", str(exc)

    def patch(self, obj, why):
        """One validated config write. Returns True on success (or dry run)."""
        body = json.dumps(obj)
        shown = json.dumps(scrub(obj))
        if self.dry_run:
            self.log("DRY-RUN would patch config (%s): %s" % (why, shown))
            return True
        rc, out, err = self.run_cli(["config", "patch", "--stdin"], stdin=body, timeout=120)
        if rc != 0:
            self.log("FAIL config patch (%s) rc=%s: %s" % (why, rc, (err or out).strip()[:300]))
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


def default_agent_id(cfg):
    ents = entries(cfg)
    for aid, e in ents.items():
        if isinstance(e, dict) and e.get("default") is True:
            return aid
    if "main" in ents or not ents:
        return "main"
    return next(iter(ents))


# ---------------------------------------------------------------- key guard
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


def snapshot(ms):
    return {k: copy.deepcopy(ms[k]) for k in OWNED if k in ms}


def chain_of(orig):
    """Backup chain, best first: the box's original, then the two backups. A backup that
    is the same provider+model as an earlier slot is dropped."""
    out = []
    for c in ({"provider": orig.get("provider"), "model": orig.get("model")}, NEMOTRON, GEMINI):
        if all((c["provider"], c["model"]) != (o["provider"], o["model"]) for o in out):
            out.append(dict(c))
    return out


def label(c):
    return "%s/%s" % (c["provider"] or "auto", c["model"] or "default")


def mm_flags(cfg):
    """Where multimodal is switched on and inherited: "" is the top level, else an agent id."""
    out = [""] if (top_search(cfg).get("multimodal") or {}).get("enabled") is True else []
    for aid, e in sorted(entries(cfg).items()):
        s = agent_search(e)
        if (s.get("multimodal") or {}).get("enabled") is True and not (s.get("provider") or s.get("model")):
            out.append(aid)
    return out


def slot_patch(cfg, orig, chain, i, cur, mm_off):
    """The one config patch that makes chain slot i the memory-search provider ({} if it
    already is). Returns (patch, multimodal switches the guard now holds off).

    Why more than provider+model:
      * remote / outputDimensionality are the ORIGINAL provider's endpoint, credential
        and vector size. Left in place they would send that endpoint (a local
        Ollama URL) or credential to a different vendor, so they are removed whenever
        the provider changes and put back verbatim on the way home to the original.
      * multimodal indexing needs the Gemini adapter; on a text-only provider every
        agent that has it on fails to re-index, so it is held off there and put back
        when the box is on Gemini again."""
    ms, slot, p = top_search(cfg), chain[i], {}
    if i != cur:
        if i == 0:
            p = {k: orig.get(k) for k in OWNED}
        else:
            p = {"provider": slot["provider"], "model": slot["model"]}
            if slot["provider"] != orig.get("provider"):
                p.update({k: None for k in OWNED[2:] if k in ms})
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
    forced on, and no fallback (so the probe measures that one provider, not its fallback)."""
    c = merge_patch(copy.deepcopy(cfg), patch)
    c.setdefault("memory", {}).setdefault("search", {}).update({"enabled": True, "fallback": "none"})
    ent = entries(c).get(agent_id)
    if isinstance(ent, dict) and agent_search(ent).get("enabled") is False:
        ent["memory"]["search"]["enabled"] = True
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

    Returns (state, detail); state: ok | dead | transient | none (no probe to read)."""
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
    env = {"OPENCLAW_CONFIG_PATH": tmp, "OPENCLAW_CONFIG_READONLY": "1", "OPENCLAW_STATE_DIR": box.root}
    try:
        rc, out, err = box.run_cli(["memory", "status", "--deep", "--agent", agent_id, "--json"], env=env)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    data = parse_json(out)
    if data is None:
        return "transient", "no JSON from memory status (rc=%s): %s" % (rc, (err or out).strip()[:200])
    rows = data if isinstance(data, list) else [data]
    pr = ((rows[0] if rows else None) or {}).get("embeddingProbe")
    if not isinstance(pr, dict):
        return "none", "no embedding probe in status output"
    if pr.get("ok") is True:
        return "ok", ""
    detail = str(pr.get("error") or "probe failed")
    return ("dead" if DEAD_KEY_RE.search(detail) else "transient"), detail


def survey(box, cfg, orig, chain, cur, mm_off, agent, sleep):
    """Probe the chain top-down, stopping at the first slot that works. Dead verdicts are
    re-checked once, CONFIRM_DELAY_S later, but only when something could act on them
    (a dead slot at or below the current one)."""
    def one(i):
        patch, _ = slot_patch(cfg, orig, chain, i, cur, mm_off)
        return probe(box, agent, probe_cfg(cfg, patch, agent))

    res = []
    for i in range(len(chain)):
        res.append(one(i))
        if res[-1][0] == "ok":
            break
    dead = [i for i, r in enumerate(res) if r[0] == "dead"]
    if dead and dead[-1] >= cur:
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


def tell_client(box, cfg, chain, st):
    chat = owner_chat(cfg)
    provs = []
    for c in chain:
        if c["provider"] in BILLING_HINT and c["provider"] not in provs:
            provs.append(c["provider"])
    names = [PROVIDER_NAME[p] for p in provs]
    msg = ("Heads up from your AI team: the keys your agents use for memory search (%s) have all "
           "stopped working. It looks like the accounts are out of money or were switched off. "
           "To keep your box running smoothly, memory search is paused for now. Your agents keep "
           "doing their jobs; they just can't search their notes until a key works again. Please "
           "add funds or check the keys at: %s. Memory search turns back on by itself once a key "
           "works." % (", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names),
                       "; ".join(BILLING_HINT[p] for p in provs)))
    if not chat:
        box.log("NOTICE no client Telegram chat found; client message not sent")
        st["key"]["notified"] = "no-chat"
        return
    if box.dry_run:
        box.log("DRY-RUN would message the client's Telegram chat: %s" % msg)
        return
    rc, out, err = box.run_cli(["message", "send", "--channel", "telegram", "--target", chat,
                                "--message", msg], timeout=60)
    if rc == 0:
        box.log("OK told the client (Telegram) that the memory keys are dead")
        st["key"]["notified"] = int(box.now)
    else:
        box.log("FAIL client message rc=%s: %s" % (rc, (err or out).strip()[:200]))


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
    agent = default_agent_id(cfg)
    own = agent_search(entries(cfg).get(agent))
    if not enabled and not kst.get("disabled_by_guard"):
        box.log("SKIPPED key check: memory search was switched off by someone else; leaving it alone")
        return 0
    if own.get("provider") or own.get("model"):
        box.log("SKIPPED key check: the default agent (%s) has its own memory.search provider" % agent)
        return 0

    orig = kst.get("original") or snapshot(ms)
    chain = chain_of(orig)
    cur = next((i for i, c in enumerate(chain) if (c["provider"], c["model"]) == (ms.get("provider"), ms.get("model"))), None)
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
        {"slot": label(chain[i]), "state": r[0], "detail": r[1][:200]} for i, r in enumerate(res)]}
    best = next((i for i, s in enumerate(states) if s == "ok"), None)

    if best is None and all(s == "dead" for s in states):
        if enabled:
            box.log("every memory option is dead (%s): turning memory search OFF"
                    % ", ".join(label(c) for c in chain))
            if box.patch({"memory": {"search": {"enabled": False}}}, "all memory keys dead"):
                kst.update({"disabled_by_guard": True, "since": int(box.now)})
                tell_client(box, cfg, chain, st)
        else:
            box.log("key check: still dead, memory search stays off")
    elif best is not None and (best <= cur or states[cur] == "dead" or not enabled):
        patch, mm = slot_patch(cfg, orig, chain, best, cur, mm_off)
        if not enabled:
            patch.setdefault("memory", {}).setdefault("search", {})["enabled"] = True
        if merge_patch(copy.deepcopy(cfg), patch) == cfg:
            box.log("key check: %s works - no change" % label(chain[cur]))
        else:
            box.log("%s %s -> %s" % ("moving up:" if best < cur else "backup chain:", label(chain[cur]), label(chain[best])))
            if box.patch(patch, "memory search -> %s" % label(chain[best])):
                if best != cur:
                    box.log("provider changed: every agent re-indexes once on its next memory use")
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
    else:
        box.log("key check: %s - no change (memory search %s)"
                % (", ".join("%s %s" % (label(chain[i]), s) for i, s in enumerate(states)), "on" if enabled else "off"))
    box.save_state(st)
    return 0


# ---------------------------------------------------------------- idle guard
def _ro(path):
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=10)


def activity(box, aid):
    """(last_activity_epoch, first_seen_epoch) for one agent, from the box's own
    records: transcripts, task runs, cron runs, legacy session files."""
    last, first = 0.0, 0.0
    adb = os.path.join(box.root, "agents", aid, "agent", "openclaw-agent.sqlite")
    if os.path.exists(adb):
        try:
            with _ro(adb) as c:
                row = c.execute("select max(created_at), min(created_at) from transcript_events").fetchone()
            if row and row[0]:
                last = max(last, row[0] / 1000.0)
                first = row[1] / 1000.0
        except sqlite3.Error:
            pass
    sdb = os.path.join(box.root, "state", "openclaw.sqlite")
    if os.path.exists(sdb):
        try:
            with _ro(sdb) as c:
                for sql in ("select max(created_at) from task_runs where agent_id=?",
                            "select max(started_at_ms) from cron_run_receipts where agent_id=?"):
                    try:
                        v = c.execute(sql, (aid,)).fetchone()[0]
                        if v:
                            last = max(last, v / 1000.0)
                    except sqlite3.Error:
                        pass
        except sqlite3.Error:
            pass
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


def always_on(aid, cfg):
    return aid in ALWAYS_ON_IDS or aid == default_agent_id(cfg) or any(p in aid for p in ALWAYS_ON_PATTERNS)


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
    off, on, kept, report = {}, {}, 0, []

    for aid, ent in sorted(entries(cfg).items()):
        if not isinstance(ent, dict):
            continue
        ms = agent_search(ent)
        cur = ms.get("enabled")
        if aid in owned and cur is not False:
            owned.pop(aid)  # someone else turned it back on; it is theirs now
            continue
        if always_on(aid, cfg):
            continue
        if aid not in owned and (cur is False or ms.get("provider") or ms.get("model")):
            continue  # someone else's choice: leave it alone
        last, first = activity(box, aid)
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
        box.log("idle check: no change (%d workers checked)" % kept)
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
        for r in report:
            box.log("idle check: " + r)
    box.save_state(st)
    return 0


def openclaw_ok(box):
    """True when the installed OpenClaw is MIN_OPENCLAW or newer (logs why not)."""
    rc, out, err = box.run_cli(["--version"], timeout=60)
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
import json, os, sys
d = os.environ["MG_FAKE_DIR"]
args = sys.argv[1:]
open(os.path.join(d, "calls.log"), "a").write(json.dumps(args) + "\n")
if args[:1] == ["--version"]:
    print("OpenClaw " + open(os.path.join(d, "version")).read().strip() + " (test)"); sys.exit(0)
if args[:2] == ["memory", "status"]:
    cfgp = os.environ.get("OPENCLAW_CONFIG_PATH") or os.path.join(d, "root", "openclaw.json")
    ms = (json.load(open(cfgp)).get("memory") or {}).get("search", {})
    open(os.path.join(d, "seen.log"), "a").write(json.dumps(ms) + "\n")
    if os.path.exists(os.path.join(d, "banner")):
        print("[plugins] 3 loaded"); print("Config warnings: one plugin is disabled")
    if ms.get("enabled") is False:
        print("[]"); sys.exit(0)
    f = os.path.join(d, "probe-" + str(ms.get("provider")))
    mode = open(f if os.path.exists(f) else os.path.join(d, "probe")).read().strip()
    pr = {"ok": True} if mode == "ok" else {"ok": False, "error": mode}
    print(json.dumps([{"agentId": "main", "embeddingProbe": pr}])); sys.exit(0)
if args[:2] == ["config", "patch"]:
    p = os.path.join(d, "root", "openclaw.json")
    cfg = json.load(open(p))
    def merge(a, b):
        for k, v in b.items():
            if v is None: a.pop(k, None)
            elif isinstance(v, dict):
                if not isinstance(a.get(k), dict): a[k] = {}
                merge(a[k], v)
            else: a[k] = v
    merge(cfg, json.loads(sys.stdin.read()))
    json.dump(cfg, open(p, "w")); sys.exit(0)
if args[:2] == ["message", "send"]:
    sys.exit(0)
sys.exit(3)
'''

DEAD = "gemini embeddings failed (429): You exceeded your current quota [code=RESOURCE_EXHAUSTED]"
BLIP = "fetch failed: connect ECONNREFUSED 127.0.0.1:11434"
OPENAI_MS = {"provider": "openai", "model": "text-embedding-3-small", "outputDimensionality": 1536,
             "remote": {"baseUrl": "https://example.invalid/v1", "apiKey": "SECRET-REMOTE-KEY"},
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
            for n in ("calls.log", "seen.log"):
                if os.path.exists(os.path.join(d, n)):
                    os.remove(os.path.join(d, n))
            if os.path.exists(os.path.join(d, "banner")):
                os.remove(os.path.join(d, "banner"))
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
              [("ollama", "embeddinggemma-2:740m"), ("openrouter", NEMOTRON["model"]), ("gemini", "gemini-embedding-2")])
        check("an original that is already gemini-embedding-2 is not tried twice",
              names({"provider": "gemini", "model": "gemini-embedding-2"}) ==
              [("gemini", "gemini-embedding-2"), ("openrouter", NEMOTRON["model"])])
        check("an original that is already the nemotron option is not tried twice",
              names({"provider": "openrouter", "model": NEMOTRON["model"]}) ==
              [("openrouter", NEMOTRON["model"]), ("gemini", "gemini-embedding-2")])

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
        check("original dead -> nemotron chosen", (m["provider"], m["model"]) == ("openrouter", NEMOTRON["model"]))
        check("switch is ONE config patch and no client message",
              len(kinds(cs, "config", "patch")) == 1 and not kinds(cs, "message", "send"))
        check("the old provider's endpoint, credential and vector size are removed",
              all(k not in m for k in ("remote", "outputDimensionality")))
        check("memory.search.fallback is never edited", m.get("fallback") == "gemini")
        check("memory search stays on", on())
        check("the original is remembered, extras included",
              box().state()["key"]["original"] == {k: OPENAI_MS[k] for k in ("provider", "model", "remote", "outputDimensionality")})
        seen = [json.loads(l) for l in open(os.path.join(d, "seen.log"))]
        check("the nemotron probe ran with no stale remote and no fallback",
              any(s.get("provider") == "openrouter" and "remote" not in s and s.get("fallback") == "none" for s in seen))
        check("the provider switch is logged as a one-time re-index", any("re-indexes once" in l for l in LOG))

        cs = run_key()
        check("settled on the backup: no write, no wait", not kinds(cs, "config", "patch") and not slept)
        check("settled on the backup: original is re-tried each night, backup stays",
              len(kinds(cs, "memory", "status")) == 2 and ms_now()["provider"] == "openrouter")

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
        check("nemotron recovers -> moved up from gemini", ms_now()["provider"] == "openrouter")

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
        check("banner lines before the JSON do not hide the verdict", ms_now()["provider"] == "openrouter")

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
    box = Box(root, cli=os.environ.get("OPENCLAW_BIN", "openclaw"), dry_run=a.dry_run)
    try:
        if a.cmd == "status":
            return status(box)
        if not openclaw_ok(box):
            return 0
        rc = 0
        if a.cmd in ("run", "key"):
            rc |= key_pass(box)
        if a.cmd in ("run", "idle"):
            box = Box(root, cli=box.cli, dry_run=a.dry_run)  # re-read config after any key write
            rc |= idle_pass(box, a.days)
        return rc
    except Exception as exc:  # report, never crash silently
        box.log("ERROR %s: %s" % (type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
