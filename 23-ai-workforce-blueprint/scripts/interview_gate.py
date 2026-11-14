#!/usr/bin/env python3
"""
interview_gate.py -- step gate for the AI Workforce Interview.

One program decides, for BOTH the web mini app and the Telegram agent:
  * which question is next            (next)
  * whether an answer is accepted     (answer)
  * whether a question may be skipped (skip / unsure)
  * how far along the owner is        (status, status --write-handoff)
  * whether the interview is finished (complete-check)

What the gate guarantees
  1. NO SKIPPED QUESTIONS. `next` always returns the lowest-order applicable question that has
     no accepted answer and is not a recorded skip. `answer` refuses any question id other than
     the current one, an already-answered one (an edit), or a recorded skip (a circle-back).
  2. NO LOOPS. `next` is idempotent. A too-short answer gets exactly ONE follow-up; the second
     submission is accepted and flagged shortAccepted. Nothing is ever refused twice for length.
  3. EXACT RESUME. All state is on disk: an append-only answers log plus a small state file
     written by temp-file-then-rename. A cold process reads them and lands on the same question.
  4. NO SELF-COMPLETION. `complete-check` exits 0 only when every required, applicable question
     has an accepted answer. Nothing else in this file can say "complete".
  5. NO FABRICATION. The gate stores only text passed in by `answer`. A known value is offered
     by `next` as knownValue and becomes an answer only when the owner submits it.
  6. ONE WRITER AT A TIME. Every command that writes takes a file lock on
     <state-dir>/.interview-gate.lock (10-second wait, then exit 1). Submitting the SAME text
     again for an already-answered question is a no-op (no second log line).
  7. PRIVATE FILES. The answers log and the state file are created with mode 0600.

This program never searches text to decide anything, never shells out, never prints anything it
did not compute from the files it just read, and treats "missing" and "unreadable" as different.

Exit codes (interface contract, 01-BUILD-SPEC.md section 2.5)
  0  ok / accepted / complete
  2  refused (wrong question, required skip, unknown question, bad usage)
  3  not complete yet, or the answer needs one follow-up
  1  tooling error (unreadable registry or state, lock timeout). The caller reports
     "temporarily unavailable", never "not answered".

Usage
  interview_gate.py [--registry R] [--state-dir D] next [--team-name "Marketing"]
  interview_gate.py [--registry R] [--state-dir D] answer --qid company_name --text "Bright Path" [--source web|telegram] [--confirmed-from SRC]
  interview_gate.py [--registry R] [--state-dir D] skip --qid brand_logo
  interview_gate.py [--registry R] [--state-dir D] unsure --qid ideal_customer
  interview_gate.py [--registry R] [--state-dir D] status [--write-handoff]
  interview_gate.py [--registry R] [--state-dir D] complete-check
--registry defaults to <script dir>/../interview/questions.v2.json, then <script dir>/questions.final.json.
--state-dir defaults to <workspace>/company-discovery, where <workspace> comes from the same
resolver platform/common.sh oc_set_platform_paths uses (resolve_workspace below).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

STATE_NAME = "interview-gate-state.json"
LOG_NAME = "interview-answers.jsonl"
KNOWN_NAME = "interview-known.json"
HANDOFF_NAME = "interview-handoff.md"
LOCK_NAME = ".interview-gate.lock"
LOCK_WAIT_SECONDS = 10
BOARD_VALUES = ("keep-all", "edited")


class GateError(Exception):
    """Tooling failure: the caller must report UNDETERMINED, never 'not answered'."""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path, what: str, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise GateError(f"{what} missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GateError(f"{what} unreadable ({exc}): {path}")
    if not isinstance(data, dict):
        raise GateError(f"{what} is not a JSON object: {path}")
    return data


def atomic_write_text(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write(path: Path, data: dict) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", 0o600)


class GateLock:
    """Exclusive lock for every writing command. Times out as a tooling error (exit 1)."""

    def __init__(self, state_dir: Path):
        self.path = state_dir / LOCK_NAME
        self.fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, "a+")
        deadline = time.time() + LOCK_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.time() >= deadline:
                    self.fh.close()
                    raise GateError(f"could not take the gate lock within {LOCK_WAIT_SECONDS} seconds: {self.path}")
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        finally:
            self.fh.close()
        return False


def title_from_id(dept_id: str) -> str:
    return " ".join(w.capitalize() for w in dept_id.replace("_", "-").split("-") if w)


class Gate:
    def __init__(self, registry_path: Path, state_dir: Path):
        self.registry = load_json(registry_path, "question registry")
        qs = self.registry.get("questions")
        if not isinstance(qs, list) or not qs:
            raise GateError("question registry has no questions")
        self.questions = sorted(qs, key=lambda q: q["order"])
        self.by_id = {q["id"]: q for q in self.questions}
        if len(self.by_id) != len(self.questions):
            raise GateError("question registry has duplicate ids")
        self.state_dir = state_dir
        self.state_path = state_dir / STATE_NAME
        self.log_path = state_dir / LOG_NAME
        self.state = load_json(self.state_path, "gate state", default={
            "version": 1, "registryVersion": self.registry.get("version"),
            "answers": {}, "skipped": [], "unsure": [], "attempts": {}, "startedAt": now_iso(),
        })
        for key, kind in (("answers", dict), ("skipped", list), ("unsure", list), ("attempts", dict)):
            if not isinstance(self.state.get(key), kind):
                raise GateError(f"gate state field '{key}' has the wrong shape: {self.state_path}")
        self.known = load_json(state_dir / KNOWN_NAME, "known facts", default={})

    # ---- applicability, order, completion -------------------------------------------------
    def applicable(self, q: dict) -> bool:
        cond = q.get("askIf")
        if not cond:
            return True
        dep = cond.get("answered")
        if dep and dep not in self.state["answers"]:
            return False
        allowed = cond.get("in")
        if dep and allowed is not None:
            return self.state["answers"][dep]["value"] in allowed
        return True

    def pending(self, include_skipped: bool = False) -> list:
        out = []
        for q in self.questions:
            if q["id"] in self.state["answers"]:
                continue
            if not self.applicable(q):
                continue
            if not include_skipped and q["id"] in self.state["skipped"]:
                continue
            out.append(q)
        return out

    def current(self):
        p = self.pending()
        return p[0] if p else None

    def missing_required(self) -> list:
        return [q["id"] for q in self.pending(include_skipped=True) if q.get("required")]

    def counts(self) -> dict:
        # A required question that is not applicable yet still counts in the total, so the
        # number an owner sees ("N of 15") never changes while they answer.
        req = [q for q in self.questions if q.get("required")]
        done = [q for q in req if q["id"] in self.state["answers"]]
        return {"requiredTotal": len(req), "requiredAnswered": len(done),
                "answeredTotal": len(self.state["answers"]),
                "percent": int(round(100 * len(done) / len(req))) if req else 100}

    # ---- wording helpers ------------------------------------------------------------------
    def team_for(self, q: dict, team_name: str | None) -> str:
        if team_name:
            return team_name
        spec = q.get("teamFrom") or {}
        src = self.state["answers"].get(spec.get("question", ""), {}).get("value")
        dept = (spec.get("map") or {}).get(src, spec.get("default", ""))
        return title_from_id(dept) if dept else ""

    def prompt_for(self, q: dict, team_name: str | None = None) -> str:
        prompt = q.get("prompt", "")
        if "{team}" in prompt:
            prompt = prompt.replace("{team}", self.team_for(q, team_name) or "first")
        return prompt

    # ---- validation (every rule comes from the registry) -----------------------------------
    def validate(self, q: dict, text: str):
        t = (text or "").strip()
        if not t:
            return False, "empty", "Please type an answer, or tap I am not sure."
        kind = q.get("kind", "text")
        if kind == "choice":
            ok = t in q.get("choices", []) or (q.get("allowOther") and t.lower().startswith("other:") and len(t) > 7)
            return (True, "", "") if ok else (False, "not-a-choice", "Please pick one of the options.")
        if kind == "multi":
            parts = [p.strip() for p in t.split("|") if p.strip()]
            bad = [p for p in parts if p not in q.get("choices", []) and not (q.get("allowOther") and p.lower().startswith("other:"))]
            return (True, "", "") if parts and not bad else (False, "not-a-choice", "Please tap at least one option.")
        if kind == "url":
            ok = t.lower().startswith(("http://", "https://", "uploaded:"))
            return (True, "", "") if ok else (False, "bad-link", "Paste a link that starts with https, or upload a picture.")
        if kind == "board":
            return (True, "", "") if t in BOARD_VALUES else (False, "not-a-choice", "Please keep all, or change a team, on the team screen.")
        if kind == "color":
            return True, "", ""          # resolved by the caller (the page's color resolver)
        short = len(t) < int(q.get("minChars", 1)) or len(t.split()) < int(q.get("minWords", 1))
        if short:
            ex = q.get("example")
            return False, "too-short", ("Can you add a little more?" + (f" For example: {ex}" if ex else ""))
        return True, "", ""

    # ---- commands -------------------------------------------------------------------------
    def cmd_next(self, team_name: str | None = None) -> tuple:
        q = self.current()
        if q is None:
            miss = self.missing_required()
            return 0, {"done": not miss, "missingRequired": miss,
                       "skippedOpen": [s for s in self.state["skipped"] if s not in self.state["answers"]],
                       **self.counts()}
        known = self.known.get(q.get("knownKey", "")) if q.get("knownKey") else None
        payload = {k: q.get(k) for k in ("id", "section", "kind", "help", "example", "choices", "suggestions", "required")}
        payload.update({"prompt": self.prompt_for(q, team_name), "done": False,
                        "attempt": self.state["attempts"].get(q["id"], 0) + 1,
                        "allowSkip": not q.get("required"), "allowUnsure": bool(q.get("allowUnsure")),
                        "allowOther": bool(q.get("allowOther")),
                        "minChars": q.get("minChars"), "minWords": q.get("minWords"),
                        "knownValue": (known or {}).get("value") if isinstance(known, dict) else None,
                        "knownSource": (known or {}).get("source") if isinstance(known, dict) else None,
                        **self.counts()})
        return 0, payload

    def cmd_answer(self, qid: str, text: str, source: str, confirmed_from: str | None) -> tuple:
        q = self.by_id.get(qid)
        if q is None:
            return 2, {"accepted": False, "reason": "unknown-question", "qid": qid}
        cur = self.current()
        is_edit = qid in self.state["answers"]
        is_circle_back = qid in self.state["skipped"]
        if not (is_edit or is_circle_back or (cur and cur["id"] == qid)):
            return 2, {"accepted": False, "reason": "out-of-order", "expected": cur["id"] if cur else None}
        if is_edit and self.state["answers"][qid].get("value") == (text or "").strip():
            return 0, {"accepted": True, "qid": qid, "duplicate": True,
                       "shortAccepted": bool(self.state["answers"][qid].get("shortAccepted")), **self.counts()}
        ok, reason, follow_up = self.validate(q, text)
        attempts = self.state["attempts"].get(qid, 0) + 1
        self.state["attempts"][qid] = attempts
        short_accepted = False
        if not ok:
            if reason == "too-short" and attempts >= 2:
                short_accepted = True                      # one follow-up only, then accept
            else:
                atomic_write(self.state_path, self.state)
                return 3, {"accepted": False, "reason": reason, "followUp": follow_up, "attempt": attempts}
        entry = {"qid": qid, "value": text.strip(), "at": now_iso(), "source": source,
                 "shortAccepted": short_accepted, "confirmedFrom": confirmed_from,
                 "replaces": self.state["answers"].get(qid, {}).get("at")}
        self.state_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:        # append-only truth, written FIRST
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self.state["answers"][qid] = entry
        self.state["skipped"] = [s for s in self.state["skipped"] if s != qid]
        self.state["unsure"] = [s for s in self.state["unsure"] if s != qid]
        atomic_write(self.state_path, self.state)
        return 0, {"accepted": True, "qid": qid, "shortAccepted": short_accepted,
                   "replaces": entry["replaces"], **self.counts()}

    def cmd_skip(self, qid: str, unsure: bool) -> tuple:
        q = self.by_id.get(qid)
        cur = self.current()
        if q is None or not cur or cur["id"] != qid:
            return 2, {"skipped": False, "reason": "not-the-current-question", "expected": cur["id"] if cur else None}
        if unsure:
            if not q.get("allowUnsure"):
                return 2, {"skipped": False, "reason": "unsure-not-offered"}
            if qid not in self.state["unsure"]:
                self.state["unsure"].append(qid)           # caller now fetches suggestions; question stays current
            atomic_write(self.state_path, self.state)
            return 0, {"skipped": False, "unsure": True, "qid": qid}
        if q.get("required"):
            return 2, {"skipped": False, "reason": "required-question", "hint": "offer I am not sure instead"}
        self.state["skipped"].append(qid)
        atomic_write(self.state_path, self.state)
        return 0, {"skipped": True, "qid": qid}

    def last_answered(self):
        if not self.state["answers"]:
            return None
        return max(self.state["answers"].values(), key=lambda a: a.get("at", ""))

    def cmd_status(self) -> tuple:
        cur = self.current()
        last = self.last_answered()
        return 0, {"next": cur["id"] if cur else None,
                   "nextPrompt": self.prompt_for(cur) if cur else None,
                   "nextSection": cur.get("section") if cur else None,
                   "lastAnsweredId": last["qid"] if last else None,
                   "lastAnsweredPrompt": self.prompt_for(self.by_id[last["qid"]]) if last and last["qid"] in self.by_id else None,
                   "missingRequired": self.missing_required(),
                   "skippedOpen": list(self.state["skipped"]), "unsureOpen": list(self.state["unsure"]),
                   "shortAccepted": [k for k, v in self.state["answers"].items() if v.get("shortAccepted")],
                   **self.counts()}

    def write_handoff(self) -> Path:
        """The eight snake_case keys the Command Center seam and the reminders parse."""
        c = self.counts()
        cur = self.current()
        last = self.last_answered()
        if c["answeredTotal"] == 0:
            status = "not_started"
        elif not self.missing_required():
            status = "ready"
        else:
            status = "in_progress"
        order = {q["id"]: i + 1 for i, q in enumerate(self.questions)}
        lines = [
            "# Interview Handoff", "",
            "> Written by scripts/interview_gate.py. Do not edit by hand.", "",
            f"status: {status}",
            f"next_question_number: {order[cur['id']] if cur else 0}",
            f"last_question_number: {order.get(last['qid'], 0) if last else 0}",
            f"total_questions_answered: {c['answeredTotal']}",
            f"total_questions_estimated: {c['requiredTotal']}",
            "skipped_questions: " + json.dumps(list(self.state["skipped"])),
            f"started_date: {self.state.get('startedAt', '')}",
            f"last_updated: {now_iso()}", "",
        ]
        path = self.state_dir / HANDOFF_NAME
        atomic_write_text(path, "\n".join(lines), 0o600)
        return path

    def cmd_complete_check(self) -> tuple:
        miss = self.missing_required()
        if miss:
            return 3, {"complete": False, "missingRequired": miss,
                       "plain": [f"Still needed: {self.prompt_for(self.by_id[m])}" for m in miss]}
        return 0, {"complete": True, **self.counts()}


# ---- defaults -------------------------------------------------------------------------------
def _registry_default(here: Path) -> Path:
    first = here.parent / "interview" / "questions.v2.json"
    return first if first.exists() else here / "questions.final.json"


def _workspace_config_root() -> Path:
    """The folder that holds openclaw.json, chosen the way platform/common.sh chooses it."""
    for name in ("OPENCLAW_ROOT", "OC_ROOT", "OC_CONFIG"):
        value = os.environ.get(name)
        if value:
            return Path(value).expanduser()
    home_root = Path(os.path.expanduser("~")) / ".openclaw"
    data_root = Path("/data/.openclaw")
    if data_root.is_dir() and not home_root.is_dir():
        return data_root
    return home_root


def _configured_workspace() -> str:
    """agents.defaults.workspace from the box configuration file, or an empty string."""
    try:
        data = json.loads((_workspace_config_root() / "openclaw.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    agents = data.get("agents")
    defaults = agents.get("defaults") if isinstance(agents, dict) else None
    value = defaults.get("workspace") if isinstance(defaults, dict) else None
    return os.path.expanduser(value.strip()) if isinstance(value, str) and value.strip() else ""


def resolve_workspace() -> Path:
    """Python port of platform/common.sh oc_set_platform_paths, same order, same default."""
    workspace = (os.environ.get("OPENCLAW_WORKSPACE_PATH")
                 or os.environ.get("OPENCLAW_WORKSPACE_ROOT")
                 or _configured_workspace())
    if not workspace:
        data_workspace = Path("/data/.openclaw/workspace")
        workspace = (str(data_workspace) if data_workspace.is_dir()
                     else str(Path(os.path.expanduser("~")) / ".openclaw" / "workspace"))
    path = Path(workspace).expanduser()
    if not path.is_absolute():
        raise GateError(f"the client workspace must be an absolute path: {workspace}")
    return path


def default_state_dir() -> Path:
    return resolve_workspace() / "company-discovery"


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Workforce Interview step gate")
    ap.add_argument("--registry")
    ap.add_argument("--state-dir")
    sub = ap.add_subparsers(dest="cmd")
    n = sub.add_parser("next"); n.add_argument("--team-name")
    a = sub.add_parser("answer"); a.add_argument("--qid", required=True); a.add_argument("--text", required=True)
    a.add_argument("--source", default="web"); a.add_argument("--confirmed-from")
    s = sub.add_parser("skip"); s.add_argument("--qid", required=True)
    u = sub.add_parser("unsure"); u.add_argument("--qid", required=True)
    st = sub.add_parser("status"); st.add_argument("--write-handoff", action="store_true")
    sub.add_parser("complete-check")
    args = ap.parse_args()
    if not args.cmd:
        ap.print_usage(sys.stderr)
        return 2
    registry = Path(args.registry) if args.registry else _registry_default(Path(__file__).resolve().parent)
    writes = args.cmd in ("answer", "skip", "unsure") or (args.cmd == "status" and args.write_handoff)
    try:
        state_dir = Path(args.state_dir) if args.state_dir else default_state_dir()
        if writes:
            with GateLock(state_dir):
                gate = Gate(registry, state_dir)
                if args.cmd == "answer":
                    rc, out = gate.cmd_answer(args.qid, args.text, args.source, args.confirmed_from)
                elif args.cmd == "skip":
                    rc, out = gate.cmd_skip(args.qid, False)
                elif args.cmd == "unsure":
                    rc, out = gate.cmd_skip(args.qid, True)
                else:
                    rc, out = gate.cmd_status()
                    out["handoff"] = str(gate.write_handoff())
        else:
            gate = Gate(registry, state_dir)
            if args.cmd == "next":
                rc, out = gate.cmd_next(args.team_name)
            elif args.cmd == "status":
                rc, out = gate.cmd_status()
            else:
                rc, out = gate.cmd_complete_check()
    except GateError as exc:
        print(json.dumps({"error": "tooling", "undetermined": True, "detail": str(exc)}))
        return 1
    except OSError as exc:
        print(json.dumps({"error": "tooling", "undetermined": True, "detail": f"file error: {exc}"}))
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
