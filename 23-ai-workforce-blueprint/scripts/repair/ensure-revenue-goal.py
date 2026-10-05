#!/usr/bin/env python3
"""ensure-revenue-goal.py -- make sure every box's company-config.json carries
the owner's yearly revenue goal, by having the box's OWN agent ask the owner.

WHY
  Department playbooks and the revenue cascade (yearly / quarterly / monthly /
  weekly / daily targets) read `yearlyRevenueGoal` from company-config.json.
  Boxes built before the question existed have no value, so every target stays
  blank. This script closes that gap WITHOUT ever inventing a number.

WHAT IT DOES (idempotent; the same code runs on every box, the operator's
included)
  1. Goal already set (a positive number under yearlyRevenueGoal, or under an
     alias create_role_workspaces.py also reads)  ->  nothing to ask. If a
     question from an earlier run is still queued, it is removed. Never asks
     again once set.
  2. Goal missing  ->  queues ONE question for the box's agent: a marker-fenced
     section in the workspace AGENTS.md (the same agent-facing channel the
     UPDATE PENDING flag uses; the agent reads it at the start of a session).
     The script sends NO message to anyone; the agent asks the owner itself.
  3. Still unanswered a week later  ->  the section is rewritten as a gentle
     reminder (at most one per 7 days). Re-running sooner changes nothing.
  4. Owner answers  ->  the agent runs `ensure-revenue-goal.py --record "<the
     owner's words>"`. That validates the amount, stores it in company-config.json
     under `yearlyRevenueGoal`, removes the question, and the box is settled.

WHY THE SECTION HEADER IS NOT "UPDATE PENDING"
  update-skills.sh strips every "## ... UPDATE PENDING ..." section from
  AGENTS.md on each run and treats any such header that does not name the
  current version as stale. A header with that text would be deleted by the next
  update before the owner could answer. This section uses its own marker pair
  and the header "OWNER QUESTION PENDING", which the updater leaves alone.

SAFETY
  * Never invents a number: the only source of a value is --record.
  * Never reads or writes openclaw.json beyond reading the agent workspace path.
  * company-config.json is rewritten atomically and only by --record; every
    other key is preserved. A config that is not valid JSON is never touched.
  * AGENTS.md is edited in place THROUGH a symlink (agents share one file; a
    rename would silently unshare it). Only the marker-fenced block is touched.
  * No model, no network, no secrets.

USAGE
  ensure-revenue-goal.py [--company-config PATH] [--workspace DIR] [--dry-run]
                         [--record "750000"|"$750,000"|"1.2m"] [--json]

EXIT CODES
  0  settled / queued / waiting / reminded / answered / skipped (no config yet)
  2  error: config or AGENTS.md unreadable or damaged, write failed, no workspace
  4  --record refused: not a positive amount, or a goal is already set
"""
import argparse
import contextlib
import io
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

KEY = "yearlyRevenueGoal"
# Same aliases create_role_workspaces.fill_tokens() reads; any valid one counts as "set".
ALIASES = ("yearly_revenue_goal", "revenueGoal", "yearlyGoal")
BEGIN = "<!-- BEGIN REVENUE_GOAL_ASK_V1 -->"
END = "<!-- END REVENUE_GOAL_ASK_V1 -->"
BLOCK_RE = re.compile(r"\n?" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)
REMIND_AFTER = timedelta(days=7)
STATE_NAME = ".revenue-goal-ask.json"  # lives next to company-config.json
MULT = {"": Decimal(1), "k": Decimal(1_000), "m": Decimal(1_000_000), "b": Decimal(1_000_000_000)}


class Fail(Exception):
    def __init__(self, msg, code=2):
        super().__init__(msg)
        self.code = code


# ── amount parsing ───────────────────────────────────────────────────────────
def parse_amount(value):
    """Positive Decimal, or None. Accepts 750000, "$750,000", "1.2m", "750k"."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        s = format(Decimal(repr(value)), "f") if isinstance(value, (int, float)) else str(value)
    except InvalidOperation:
        return None
    s = re.sub(r"[,$\s]", "", s)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb]?)", s, re.I)
    if not m:
        return None
    d = Decimal(m.group(1)) * MULT[m.group(2).lower()]
    return d if d > 0 else None


def normalize(d):
    return str(int(d)) if d == d.to_integral_value() else format(d.normalize(), "f")


def goal_is_set(cfg):
    return any(parse_amount(cfg.get(k)) is not None for k in (KEY,) + ALIASES)


# ── locating the box's files ─────────────────────────────────────────────────
def _oc_root():
    for name in ("OPENCLAW_ROOT", "OC_ROOT", "OC_CONFIG"):
        if os.environ.get(name):
            return Path(os.environ[name])
    return Path("/data/.openclaw") if Path("/data/.openclaw").is_dir() else Path.home() / ".openclaw"


def resolve_workspace(explicit):
    """Agent workspace: --workspace, else this box's openclaw.json (READ ONLY),
    in the same order update-skills.sh uses, else <root>/workspace."""
    if explicit:
        return Path(explicit)
    root = _oc_root()
    try:
        agents = json.loads((root / "openclaw.json").read_text(encoding="utf-8")).get("agents") or {}
        ws = ((agents.get("entries") or {}).get("main") or {}).get("workspace")
        for ag in (agents.get("list") or []):
            if not ws and isinstance(ag, dict) and ag.get("id") == "main":
                ws = ag.get("workspace")
        ws = ws or (agents.get("defaults") or {}).get("workspace")
        if ws:
            return Path(os.path.expanduser(ws))
    except (OSError, ValueError, AttributeError):
        pass
    return root / "workspace"


def find_config(explicit, workspace):
    if explicit:
        return Path(explicit)
    if os.environ.get("OPENCLAW_COMPANY_CONFIG", "").strip():
        return Path(os.environ["OPENCLAW_COMPANY_CONFIG"].strip())
    here = Path(__file__).resolve()
    for i in (1, 2, 3):  # repo checkout, installed skill dir, skills root
        sys.path.insert(0, str(here.parents[i] / "shared-utils"))
    try:
        from detect_platform import get_openclaw_paths
        with contextlib.redirect_stderr(io.StringIO()):
            p = Path(get_openclaw_paths()["company_config"])
        if p.is_file():
            return p
    except (Exception, SystemExit):
        pass
    zhc = workspace / "zero-human-company"
    cands = sorted(zhc.glob("*/company-config.json")) + [zhc / "company-config.json",
                                                         workspace / "company-config.json"]
    return next((c for c in cands if c.is_file()), None)


# ── file helpers ─────────────────────────────────────────────────────────────
def load_json(path, what):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Fail(f"cannot read {what} {path}: {exc} -- left untouched")
    if not isinstance(data, dict):
        raise Fail(f"{what} {path} is not a JSON object -- left untouched")
    return data


def atomic_write_json(path, obj):
    real = Path(os.path.realpath(path))
    fd, tmp = tempfile.mkstemp(prefix="." + real.name + ".", dir=str(real.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        with contextlib.suppress(OSError):
            os.chmod(tmp, real.stat().st_mode & 0o7777)
        os.replace(tmp, real)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_state(path):
    try:
        s = json.loads(path.read_text(encoding="utf-8"))
        return s if isinstance(s, dict) else None
    except (OSError, ValueError):
        return None


def read_agents(path):
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError as exc:
        raise Fail(f"cannot read {path}: {exc} -- left untouched")


def write_agents(path, text):
    # ponytail: in-place write (never rename: AGENTS.md is shared via symlinks);
    # no cross-process lock -- add fcntl.flock if two writers ever race.
    try:
        with open(path, "w", encoding="utf-8", errors="surrogateescape") as fh:
            fh.write(text)
        back = path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError as exc:
        raise Fail(f"cannot write {path}: {exc}")
    if back != text:
        raise Fail(f"read-back of {path} differs from what was written")


def check_markers(text):
    if text.count(BEGIN) != text.count(END):
        raise Fail("AGENTS.md has an unmatched REVENUE_GOAL_ASK_V1 marker -- left untouched")


def upsert_block(text, block):
    check_markers(text)
    block = block + "\n"
    if BEGIN not in text:
        return text + ("" if text.endswith("\n") or not text else "\n") + ("\n" if text else "") + block
    seen = []

    def sub(_m):  # first pair becomes the block, any duplicate pair is dropped
        if seen:
            return ""
        seen.append(1)
        return "\n" + block if _m.group(0).startswith("\n") else block
    return BLOCK_RE.sub(sub, text)


def remove_block(text):
    check_markers(text)
    return BLOCK_RE.sub("", text)


def build_block(state, script):
    reminders = int(state.get("reminders") or 0)
    asked = datetime.fromisoformat(state["lastAskedAt"])
    status = "first ask" if reminders == 0 else f"weekly reminder {reminders}, one gentle line"
    return f"""{BEGIN}
## OWNER QUESTION PENDING -- Yearly Revenue Goal
Status: {status}. Asked {asked.date().isoformat()}; not again before {(asked + REMIND_AFTER).date().isoformat()}.
The company config has no yearly revenue goal, so revenue targets are blank.
1. Ask the owner once, naturally: "What is your revenue goal for this year, in dollars?"
2. Never guess or infer a number. Only the owner's answer counts.
3. On the answer run: python3 "{script}" --record "<owner's answer>"
   That saves it and removes this section.
4. No answer yet: wait for the date above, then at most one gentle reminder a week.
{END}"""


# ── the run ──────────────────────────────────────────────────────────────────
def run(a, now):
    ws = resolve_workspace(a.workspace)
    agents = ws / "AGENTS.md"
    cfg_path = find_config(a.company_config, ws)
    out = {"state": "", "goal": "missing", "config": str(cfg_path) if cfg_path else None,
           "agents_md": str(agents), "dry_run": a.dry_run}
    if not cfg_path or not cfg_path.is_file():
        out["state"] = "skipped-no-company-config"  # nothing to ask about yet; never create one
        return out
    cfg = load_json(cfg_path, "company-config.json")
    state_path = cfg_path.parent / STATE_NAME
    state = load_state(state_path)
    already = goal_is_set(cfg)
    out["goal"] = "set" if already else "missing"
    script = str(Path(__file__).resolve())

    if a.record is not None:
        d = parse_amount(a.record)
        if already:
            raise Fail("a yearly revenue goal is already set; it is never overwritten here", 4)
        if d is None:
            raise Fail(f"{a.record!r} is not a positive dollar amount (examples: 750000, $750,000, 1.2m)", 4)
        value = normalize(d)
        out.update(state="answered", recorded=value, goal="set")
        if not a.dry_run:
            cfg[KEY] = value
            atomic_write_json(cfg_path, cfg)
            st = dict(state or {}, status="answered", answeredAt=now.isoformat(), answer=value)
            atomic_write_json(state_path, st)
            drop_question(agents)
        return out

    if already:
        had_question = agents.exists() and BEGIN in read_agents(agents)
        out["state"] = "settled"
        if not a.dry_run:
            if had_question:
                drop_question(agents)
            if state and state.get("status") != "answered":
                atomic_write_json(state_path, dict(state, status="answered", answeredAt=now.isoformat()))
        return out

    if state and state.get("status") == "answered":
        # Owner answered once and the value has since vanished from the config.
        # Never ask again, never invent: report only (the answer is kept in the state file).
        out["state"] = "answered-config-lost"
        return out

    # Goal missing and not yet answered: first ask, wait, or weekly reminder.
    try:
        last = datetime.fromisoformat(state["lastAskedAt"]) if state else None
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        last = None
    if last is None:
        st = {"status": "pending", "queuedAt": now.isoformat(), "lastAskedAt": now.isoformat(), "reminders": 0}
        out["state"] = "queued"
    elif now - last >= REMIND_AFTER:
        st = dict(state, lastAskedAt=now.isoformat(), reminders=int(state.get("reminders") or 0) + 1)
        out["state"] = "reminded"
    else:
        st = state
        out["state"] = "waiting"
    if not ws.is_dir():
        raise Fail(f"agent workspace {ws} does not exist; cannot queue the question")
    text = read_agents(agents)
    new = upsert_block(text, build_block(st, script))
    if new != text and out["state"] == "waiting":
        out["state"] = "waiting-question-restored"
    out["reminders"] = int(st.get("reminders") or 0)
    if not a.dry_run:
        if new != text:
            write_agents(agents, new)
        if st is not state:
            atomic_write_json(state_path, st)
    return out


def drop_question(agents):
    if agents.exists():
        text = read_agents(agents)
        new = remove_block(text)
        if new != text:
            write_agents(agents, new)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--company-config", help="path to company-config.json (default: this box's)")
    ap.add_argument("--workspace", help="agent workspace dir holding AGENTS.md (default: from openclaw.json)")
    ap.add_argument("--record", metavar="AMOUNT", help="the owner's answer; stores it and clears the question")
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--now", help=argparse.SUPPRESS)  # ISO timestamp, for tests
    a = ap.parse_args(argv)
    now = datetime.fromisoformat(a.now) if a.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    try:
        out = run(a, now)
    except Fail as exc:
        print(f"[ensure-revenue-goal] ERROR: {exc}", file=sys.stderr)
        return exc.code
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print("[ensure-revenue-goal] " + " ".join(f"{k}={v}" for k, v in out.items() if v is not None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
