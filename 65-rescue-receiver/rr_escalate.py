#!/usr/bin/env python3
"""rr_escalate.py - the ONE command a client's agent runs to ask Rescue Rangers for help.

Shipped to every box by the normal roll. It replaces the 110-line
copy-and-paste shell block in scripts/rescue-escalation-section.md.tpl. The
agent supplies three plain-text values; everything else is read from the box
by this script.

WHAT IT DOES, IN ORDER
  1. Reads the webhook address, the shared secret and the box slug from the
     runtime environment first and the secrets store second. The store is
     PARSED line by line, by the rules of shared-utils/rescue-env.sh. It is
     never sourced as shell and no value is printed.
  2. Reads the real OpenClaw version by running "openclaw --version".
  3. Checks whether the REPLY leg is enrolled on this box (RR_RECEIVER_URL,
     RR_BOX_TOKEN and RR_BOX_SLUG all present). The result changes what the
     agent is told to say to the owner. It never blocks the escalation.
  4. Creates a request_id (a random id made once per escalation) and writes
     the full request to a durable outbox file BEFORE anything is sent.
  5. Sends the request. The secret travels in a request header set inside
     this process. It is never placed on a command line.
  6. Reads the answer as JSON and decides the state from NAMED fields.
  7. On acceptance, records the ticket id and the conversation the request
     came from (the owner's chat on this box) in a local file, so the reply
     can be delivered into that same conversation. Chat ids never leave the box.
  8. Prints ONE JSON object. The agent reads "state" and says "say_to_owner".

FLUSH: "rr_escalate.py flush" re-sends anything still in the outbox, using the
SAME request_id, so a retry can never create a second ticket. A cron on the box
runs flush every 5 minutes. An escalation is therefore never lost to a short
outage, and the agent never has to "wait 2 minutes and try again" by hand.

RESOLVE (RRX-007): "rr_escalate.py resolve --ticket <id> --fixed <one line>"
closes the case FROM THE BOX. It builds one operation_id from the ticket and
the fixed text, so running it twice sends the same identifier and cannot close
two tickets. It rides the same outbox and the same send path as "send".

STATUS (RRX-007): "rr_escalate.py status --ticket <id>" prints the outcome the
poll recorded for that ticket, so the agent can answer the owner from the
conversation the case came from.

STATES (printed in "state")
  accepted               ticket created; ticket id is in "ticket_id"
  already_being_worked   this problem already has a ticket; do not send again
  queued_will_retry      could not reach Rescue Rangers; saved; flush will resend
  needs_owner_action     Rescue Rangers answered with a message for the owner
  not_an_incident        Rescue Rangers decided this is not an incident
  setup_problem          the address, the secret or the box slug is missing or refused
  invalid_request        a required value was empty; fix it and run again
  resolved               (resolve) Rescue Rangers recorded the repair
  unknown_incident       (resolve) Rescue Rangers has no open case for that ticket
  outcome_recorded       (status) the poll recorded an outcome for that ticket
  waiting                (status) the ticket is open; no outcome recorded yet
  unknown_ticket         (status) this box has no record of that ticket

Exit codes: 0 accepted / already_being_worked / needs_owner_action / not_an_incident,
            10 queued_will_retry, 20 setup_problem, 21 invalid_request, 2 internal failure.

Usage:
  python3 rr_escalate.py send --person "Owner Name" --client "<client label>" --agent "<agent name>" \
      --box-type "<VPS | Mac Mini | MacBook Pro>" --problem-file p.txt --tried-file t.txt [--loop]
  python3 rr_escalate.py flush
  python3 rr_escalate.py resolve --ticket <id> --fixed "what fixed it, one line"
  python3 rr_escalate.py status --ticket <id>
  python3 rr_escalate.py selftest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

DEFAULT_URL = "https://main.blackceoautomations.com/webhook/rr-v2-intake"
MAX_ATTEMPTS = 12            # flush gives up after 12 tries (about one hour at a 5-minute cadence)
TIMEOUT_S = 60
ORIGIN_TIMEOUT_S = 30        # the owner-chat helper gets its own, shorter limit
USER_AGENT = "rr-escalate/1.0"   # a bare Python user agent has been refused by Cloudflare on this fleet
SECRETS_REJECTED_DETAIL = "the secrets file has a line the installer will reject"
_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_CHAT_ID_RE = re.compile(r"-?[0-9]+\Z")   # digits, optional leading minus, nothing else
_TICKET_RE = re.compile(r"[A-Za-z0-9._-]+\Z")   # RRX-007: safe in a file name and in a request
WAITING_SAY = ("Our support team is still working on this. I will message you here as soon as "
               "there is an answer.")


# ---------------------------------------------------------------- box facts
def oc_root() -> str:
    for cand in (os.environ.get("OC_CONFIG_ROOT", ""), "/data/.openclaw", os.path.expanduser("~/.openclaw")):
        if cand and os.path.isdir(cand):
            return cand
    return ""


def parse_dotenv(path: str) -> tuple[dict[str, str], bool]:
    """Parse a dotenv file by the rules of shared-utils/rescue-env.sh.

    Never sources or executes the file. Returns (values, rejected) where
    `rejected` is True when a line is one the shell parser would refuse the
    whole file for. A rejected file still yields every key that parses clean:
    a junk line elsewhere must never stop a box asking for help.
    """
    values: dict[str, str] = {}
    rejected = False
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            raw_lines = fh.read().split("\n")
    except OSError:
        return values, False
    for raw in raw_lines:
        line = raw[1:] if raw.startswith("﻿") else raw   # a byte-order mark is ignored
        line = line.rstrip(" \t")                             # only trailing blanks are trimmed
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):                        # RRX-011: an export prefix is ignored
            line = line[len("export "):]
        name, sep, value = line.partition("=")
        if not sep or not _KEY_RE.match(name):
            rejected = True                                   # no "=", or a key with a blank in it
            continue
        if value.startswith(('"', "'")):
            mark = value[0]
            if len(value) < 2 or not value.endswith(mark):
                rejected = True                               # unterminated quote: the key is not set
                continue
            value = value[1:-1]                               # quoted: keep everything between the marks
        else:
            cut = re.search(r"[ \t]#", value)                 # bare: drop a trailing blank+# comment
            if cut:
                value = value[:cut.start()]
            value = value.rstrip(" \t")
        values[name] = value                                  # the LAST line that sets a key wins
    return values, rejected


def dotenv_get(path: str, key: str) -> str:
    """Read one KEY from a dotenv file by parsing. Never executes the file."""
    return parse_dotenv(path)[0].get(key, "")


def secrets_rejected(root: str) -> bool:
    """True when the secrets store has a line the shell parser refuses."""
    return parse_dotenv(os.path.join(root, "secrets", ".env"))[1]


def setting(root: str, key: str) -> str:
    return os.environ.get(key, "") or dotenv_get(os.path.join(root, "secrets", ".env"), key)


def openclaw_version() -> str:
    for cand in ("openclaw", os.path.expanduser("~/.local/bin/openclaw"), "/opt/homebrew/bin/openclaw",
                 "/usr/local/bin/openclaw", "/data/.npm-global/bin/openclaw"):
        try:
            p = subprocess.run([cand, "--version"], capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = p.stdout.strip()
        if p.returncode == 0 and text:
            return text.splitlines()[0][:80]
    return "unknown (openclaw --version did not run)"


def reply_leg_enrolled(root: str) -> bool:
    store = os.path.join(root, "secrets", ".env")
    return all(dotenv_get(store, k) for k in ("RR_RECEIVER_URL", "RR_BOX_TOKEN", "RR_BOX_SLUG"))


def resolve_origin(root: str) -> dict | None:
    """Ask the box's OWN helper which conversation this case came from.

    The helper uses `local`, so it must run under bash. The command string is
    fixed and the only value handed to it is the path, as $1 -- nothing else is
    interpolated. A value that is not digits (an optional leading minus is
    allowed) is not a chat id and means "no origin".
    """
    helper = os.path.join(root, "skills", "shared-utils", "resolve-owner-chat.sh")
    if not os.path.isfile(helper):
        return None
    try:
        p = subprocess.run(["bash", "-c", 'source "$1" && resolve_owner_chat_id', "_", helper],
                           capture_output=True, text=True, timeout=ORIGIN_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    target = p.stdout.strip()
    if not _CHAT_ID_RE.match(target):
        return None
    return {"channel": "telegram", "account": "default", "target": target}


# ---------------------------------------------------------------- files
def state_dir(root: str, *parts: str) -> str:
    d = os.path.join(root, "state", "rr-escalate", *parts)
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def atomic_json(path: str, doc: dict) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".new-", dir=os.path.dirname(path))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def read_text(path: str | None, inline: str | None) -> str:
    if path:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    return (inline or "").strip()


# ---------------------------------------------------------------- wire
def post(url: str, secret: str, body: dict) -> tuple[int, dict | None]:
    """Returns (http_code, parsed_json_or_None). http_code 0 means no answer at all."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json", "X-Rescue-Secret": secret, "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            code, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        code, raw = exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, None
    try:
        doc = json.loads(raw.decode("utf-8"))
        return code, doc if isinstance(doc, dict) else None
    except ValueError:
        return code, None


def classify(code: int, doc: dict | None) -> str:
    """Decide the state from the HTTP code and NAMED JSON fields only."""
    if code == 0 or code == 429 or 500 <= code <= 599:
        return "queued_will_retry"
    if code in (401, 403):
        return "setup_problem"
    if code == 400:
        # RRX-011: 400 is "the payload was refused". The intake also answers 400
        # for a box name it cannot resolve -- a setup problem, not an empty value.
        status = str((doc or {}).get("status") or "")
        return "invalid_request" if status == "invalid_payload" else "setup_problem"
    if 300 <= code <= 399:
        return "queued_will_retry"          # a redirect wall is not an answer
    if code != 200 or doc is None:
        return "queued_will_retry"          # a 200 that is not JSON is not an acceptance
    # RRX-011: an explicit refusal is never "queued" -- the intake said no.
    if doc.get("accepted") is False:
        if str(doc.get("message") or "").strip():
            return "needs_owner_action"
        return "setup_problem" if str(doc.get("status") or "") == "unauthorized" else "invalid_request"
    status = str(doc.get("status") or "")
    if status == "duplicate_ignored":
        return "already_being_worked"
    if status in ("accepted_human_followup", "held_account_standing"):
        return "needs_owner_action"
    if status == "non_incident":
        return "not_an_incident"
    if status == "missing_message":
        return "setup_problem"              # the old, retired relay answers this; the address is wrong
    if isinstance(doc.get("ticketId"), str) and doc["ticketId"]:
        return "accepted"
    return "queued_will_retry"


def classify_resolve(code: int, doc: dict | None) -> str:
    """RRX-007: decide a resolution's state from the HTTP code and NAMED fields.

    Today's intake answers a resolution with a "status" of resolution_recorded
    or resolution_no_open_ticket (and, after n8n unit N-18, correlation_required).
    A 409 means the intake has no such incident. The retry, refusal and 400
    rules are the same as for a first send.
    """
    if code == 409:
        return "unknown_incident"
    if code == 0 or code == 429 or 500 <= code <= 599:
        return "queued_will_retry"
    if code in (401, 403):
        return "setup_problem"
    if code == 400:
        status = str((doc or {}).get("status") or "")
        return "invalid_request" if status == "invalid_payload" else "setup_problem"
    if 300 <= code <= 399:
        return "queued_will_retry"
    if code != 200 or doc is None:
        return "queued_will_retry"
    status = str(doc.get("status") or "")
    if status in ("resolution_recorded", "resolved"):
        return "resolved"
    if status in ("resolution_no_open_ticket", "correlation_required"):
        return "unknown_incident"
    if isinstance(doc.get("ticketId"), str) and doc["ticketId"]:
        return "resolved"
    return "queued_will_retry"


def owner_reply_leg(state: str, doc: dict, local: str | None) -> str:
    """The reply leg the OWNER is told about. The intake's own verdict wins."""
    if state == "accepted" and doc.get("boxEnrolled") is False:
        return "not_enrolled"       # the intake says this box is not enrolled; never promise a reply
    return local or "not_enrolled"


SAY = {
    "accepted_enrolled": "I could not fix this on my own, so I have asked our Rescue Rangers support team for help. "
                         "Your reference is {ticket}. You do not need to do anything. I will message you here as soon as "
                         "there is an answer or a fix.",
    "accepted_not_enrolled": "I could not fix this on my own, so I have asked our Rescue Rangers support team for help. "
                             "Your reference is {ticket}. A person on the support team will follow up with you directly.",
    "already_being_worked": "Our Rescue Rangers support team is already working on this problem. I will message you here "
                            "when there is an update.",
    "queued_will_retry": "I could not reach our support team just now. I have saved the request and it will be sent "
                         "automatically. I will tell you when it has gone through.",
    "needs_owner_action": "{message}",
    "not_an_incident": "Our support team looked at this and it does not need a repair. {message}",
    "setup_problem": "I cannot reach our support team from this computer because of a setup problem on our side. "
                     "Please tell your support contact that Rescue Rangers is not connected on this computer.",
    "invalid_request": "",
    # RRX-007: the two answers a resolution can get.
    "resolved": "Rescue Rangers has recorded the repair. This case is closed.",
    "unknown_incident": "Rescue Rangers has no open case for this problem, so there was nothing to close.",
}


def result(state: str, **extra) -> dict:
    key = state
    if state == "accepted":
        # RRX-011: a case over the daily limit is answered accepted with
        # notificationCapped:true. No reply will come from us, so never promise one.
        if extra.get("reply_leg") == "enrolled" and extra.get("capped") is not True:
            key = "accepted_enrolled"
        else:
            key = "accepted_not_enrolled"
    say = SAY[key].format(ticket=extra.get("ticket_id") or "", message=extra.get("message") or "").strip()
    out = {"state": state, "say_to_owner": say}
    out.update(extra)
    return out


def exit_code(state: str) -> int:
    return {"queued_will_retry": 10, "setup_problem": 20, "invalid_request": 21}.get(state, 0)


SENT_STATES = ("accepted", "already_being_worked", "needs_owner_action", "not_an_incident", "resolved")


def deliver(root: str, entry_path: str, classifier=classify) -> dict:
    """Send one outbox entry. Moves it to sent/ or failed/ when it is finished."""
    with open(entry_path, encoding="utf-8") as fh:
        entry = json.load(fh)
    url = setting(root, "RESCUE_RANGERS_WEBHOOK_URL") or DEFAULT_URL
    secret = setting(root, "RESCUE_RANGERS_WEBHOOK_SECRET")
    rid = entry["body"]["request_id"]
    if not secret:
        return result("setup_problem", request_id=rid, detail="RESCUE_RANGERS_WEBHOOK_SECRET is not set in the environment or the secrets store")
    entry["attempts"] = int(entry.get("attempts", 0)) + 1
    entry["last_attempt_at"] = int(time.time())
    atomic_json(entry_path, entry)
    code, doc = post(url, secret, entry["body"])
    state = classifier(code, doc)
    doc = doc or {}
    extra = dict(request_id=rid, http=code, ticket_id=str(doc.get("ticketId") or ""),
                 message=str(doc.get("message") or ""),
                 reply_leg=owner_reply_leg(state, doc, entry.get("reply_leg")),
                 capped=doc.get("notificationCapped") is True, attempts=entry["attempts"])
    if code == 400:
        # RRX-011: never a bare invalid_request -- say what the intake said.
        extra["detail"] = "the intake answered 400 (status %s): %s" % (
            str(doc.get("status") or "none"), str(doc.get("message") or "no message"))
    out = result(state, **extra)
    if state == "queued_will_retry" and entry["attempts"] < MAX_ATTEMPTS:
        return out                                        # stays in the outbox
    final_dir = "sent" if state in SENT_STATES else "failed"
    entry["final"] = out
    atomic_json(os.path.join(state_dir(root, final_dir), rid + ".json"), entry)
    os.unlink(entry_path)
    if state == "accepted":
        # The conversation this request came from stays ON THE BOX. The reply leg reads it.
        atomic_json(os.path.join(state_dir(root, "origins"), out["ticket_id"] + ".json"),
                    {"ticket_id": out["ticket_id"], "request_id": rid, "origin": entry.get("origin"),
                     "recorded_at": int(time.time())})
    return out


def cmd_send(a) -> int:
    root = oc_root()
    if not root:
        print(json.dumps(result("setup_problem", detail="no OpenClaw folder found on this computer")))
        return 20
    person = (a.person or "").strip()
    problem = read_text(a.problem_file, a.problem)
    tried = read_text(a.tried_file, a.tried)
    missing = [n for n, v in (("person", person), ("problem", problem), ("tried", tried)) if not v]
    if missing:
        print(json.dumps(result("invalid_request", detail="these values are empty: " + ", ".join(missing))))
        return 21
    slug = setting(root, "FLEET_STANDING_BOX_SLUG")
    if not slug:
        print(json.dumps(result("setup_problem", detail="FLEET_STANDING_BOX_SLUG is not set; the box cannot identify itself")))
        return 20
    if a.loop and not problem.startswith("LOOP:"):
        problem = "LOOP: " + problem
    enrolled = reply_leg_enrolled(root)
    rid = "req-" + uuid.uuid4().hex
    body = {
        "action": "escalate", "request_id": rid, "operation_id": rid,
        "person": person,
        "clientName": (a.client or "").strip() or slug,
        "agentName": (a.agent or "").strip() or "main",
        "boxName": slug,
        "boxType": (a.box_type or "").strip() or "unknown",
        "openclawVersion": openclaw_version(),
        "problem": problem, "alreadyTried": tried,
        "returnTo": "box-poll" if enrolled else "none",
        "replyLeg": "enrolled" if enrolled else "not_enrolled",
    }
    origin = None
    if a.origin_json:
        try:
            origin = json.loads(a.origin_json)
        except ValueError:
            origin = None
        if not origin:
            origin = None
    else:
        # RRX-001a: no explicit origin -- ask the box which conversation this came from.
        origin = resolve_origin(root)
    # RRX-001a: with no origin there is no conversation to deliver into, so the
    # owner is told a person will follow up directly, whatever the local leg says.
    owner_leg = "enrolled" if (enrolled and origin) else "not_enrolled"
    entry = {"body": body, "attempts": 0, "created_at": int(time.time()),
             "reply_leg": owner_leg, "origin": origin}
    path = os.path.join(state_dir(root, "outbox"), rid + ".json")
    atomic_json(path, entry)                               # durable BEFORE the send
    out = deliver(root, path)
    if secrets_rejected(root):
        out.setdefault("detail", SECRETS_REJECTED_DETAIL)
    print(json.dumps(out, sort_keys=True))
    return exit_code(out["state"])


def cmd_flush(_a) -> int:
    root = oc_root()
    if not root:
        return 20
    rejected = secrets_rejected(root)
    box = state_dir(root, "outbox")
    worst = 0
    for name in sorted(os.listdir(box)):
        if not name.endswith(".json") or name.startswith("."):
            continue
        out = deliver(root, os.path.join(box, name))
        if rejected:
            out.setdefault("detail", SECRETS_REJECTED_DETAIL)
        print(json.dumps(out, sort_keys=True))
        worst = max(worst, exit_code(out["state"]))
    return worst


def json_records(directory: str):
    """Yield (name, parsed) for every non-hidden JSON file in a folder. Read only."""
    if not os.path.isdir(directory):
        return
    for name in sorted(os.listdir(directory)):
        if name.startswith(".") or not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict):
            yield name, rec


def written_at_key(rec: dict):
    """A comparable key for "written_at", numeric or ISO text. Same types compare."""
    v = rec.get("written_at")
    if isinstance(v, bool):
        return (0, "")
    if isinstance(v, (int, float)):
        return (1, float(v))
    return (0, str(v or ""))


def resolve_operation_id(ticket: str, fixed: str) -> str:
    """RRX-007: the same on a re-run, so one resolution never closes two tickets."""
    digest = hashlib.sha1((ticket + "|" + fixed).encode("utf-8")).hexdigest()
    return "res-" + ticket + "-" + digest[:16]


def newest_attempt_id(root: str, ticket: str) -> str:
    """The attempt_id of the newest done record for this ticket, or "" -- never invented."""
    best, best_key = None, None
    for _name, rec in json_records(os.path.join(root, "state", "rr-receiver", "done")):
        if rec.get("ticket_id") != ticket:
            continue
        key = written_at_key(rec)
        if best is None or key > best_key:
            best, best_key = rec, key
    if best is None:
        return ""
    attempt = best.get("attempt_id")
    return attempt if isinstance(attempt, str) and attempt else ""


def sent_record(root: str, ticket: str) -> dict:
    """The sent/ record whose final.ticket_id is this ticket, or {}."""
    for _name, rec in json_records(os.path.join(root, "state", "rr-escalate", "sent")):
        final = rec.get("final")
        if isinstance(final, dict) and final.get("ticket_id") == ticket:
            return rec
    return {}


def cmd_resolve(a) -> int:
    """RRX-007: the box closes its own case, through the same outbox as send."""
    root = oc_root()
    if not root:
        print(json.dumps(result("setup_problem", detail="no OpenClaw folder found on this computer")))
        return 20
    ticket = (a.ticket or "").strip()
    if not _TICKET_RE.match(ticket):
        print(json.dumps(result("invalid_request", detail="the ticket id may use only letters, digits, '.', '_' and '-'")))
        return 21
    fixed = (a.fixed or "").strip()
    if not fixed:
        print(json.dumps(result("invalid_request", detail="--fixed is empty")))
        return 21
    slug = setting(root, "FLEET_STANDING_BOX_SLUG")
    if not slug:
        print(json.dumps(result("setup_problem", detail="FLEET_STANDING_BOX_SLUG is not set; the box cannot identify itself")))
        return 20
    op = resolve_operation_id(ticket, fixed)
    known = sent_record(root, ticket)
    known_body = known.get("body") if isinstance(known.get("body"), dict) else {}
    text = "RESOLVED: " + fixed
    body = {
        "action": "escalate", "request_id": op,
        "boxName": slug, "runtime_id": slug,
        "clientName": str(known_body.get("clientName") or slug),
        "agentName": str(known_body.get("agentName") or "main"),
        "incident_id": ticket, "operation_id": op,
        "result_digest": "sha256-" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "problem": text,
    }
    attempt = newest_attempt_id(root, ticket)
    if attempt:
        body["attempt_id"] = attempt      # kept when the box has one; never invented
    entry = {"body": body, "attempts": 0, "created_at": int(time.time()),
             "reply_leg": "enrolled" if reply_leg_enrolled(root) else "not_enrolled", "origin": None}
    path = os.path.join(state_dir(root, "outbox"), op + ".json")
    atomic_json(path, entry)                               # durable BEFORE the send
    out = deliver(root, path, classify_resolve)
    if secrets_rejected(root):
        out.setdefault("detail", SECRETS_REJECTED_DETAIL)
    print(json.dumps(out, sort_keys=True))
    return exit_code(out["state"])


def cmd_status(a) -> int:
    """RRX-007: read the outcome the poll recorded, so the agent can answer the owner."""
    root = oc_root()
    if not root:
        print(json.dumps(result("setup_problem", detail="no OpenClaw folder found on this computer")))
        return 20
    ticket = (a.ticket or "").strip()
    if not _TICKET_RE.match(ticket):
        print(json.dumps(result("invalid_request", detail="the ticket id may use only letters, digits, '.', '_' and '-'")))
        return 21
    path = os.path.join(root, "state", "rr-receiver", "case-outcomes", ticket + ".json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            doc = None
        if isinstance(doc, dict):
            doc["state"] = "outcome_recorded"
            print(json.dumps(doc, sort_keys=True))
            return 0
    if sent_record(root, ticket):
        print(json.dumps({"state": "waiting", "say_to_owner": WAITING_SAY}, sort_keys=True))
        return 0
    print(json.dumps({"state": "unknown_ticket"}, sort_keys=True))
    return 21


def selftest() -> int:
    ok = True
    ok &= classify(0, None) == "queued_will_retry"
    ok &= classify(503, None) == "queued_will_retry"
    ok &= classify(302, None) == "queued_will_retry"
    ok &= classify(403, {"error": "x"}) == "setup_problem"
    ok &= classify(400, {"status": "invalid_payload"}) == "invalid_request"
    ok &= classify(400, {"status": "box_not_found", "message": "no such box"}) == "setup_problem"
    ok &= classify(200, None) == "queued_will_retry"                    # 200 with an HTML page
    ok &= classify(200, {"status": "duplicate_ignored"}) == "already_being_worked"
    ok &= classify(200, {"status": "missing_message"}) == "setup_problem"
    ok &= classify(200, {"accepted": True, "ticketId": "RR-000001"}) == "accepted"
    ok &= classify(200, {"accepted": True, "ticketId": None, "status": "test_suppressed"}) == "queued_will_retry"
    # RRX-011: an explicit accepted:false is never queued_will_retry.
    ok &= classify(200, {"accepted": False, "message": "send us the receipt"}) == "needs_owner_action"
    ok &= classify(200, {"accepted": False, "status": "unauthorized"}) == "setup_problem"
    ok &= classify(200, {"accepted": False}) == "invalid_request"
    # RRX-011: the intake's own enrollment verdict decides what the owner is told.
    ok &= owner_reply_leg("accepted", {"boxEnrolled": False}, "enrolled") == "not_enrolled"
    ok &= owner_reply_leg("accepted", {"boxEnrolled": True}, "enrolled") == "enrolled"
    # RRX-007: a resolution's four outcomes, read from NAMED fields only.
    ok &= classify_resolve(200, {"status": "resolution_recorded"}) == "resolved"
    ok &= classify_resolve(200, {"status": "resolved"}) == "resolved"
    ok &= classify_resolve(200, {"ticketId": "RR-1"}) == "resolved"
    ok &= classify_resolve(200, {"status": "resolution_no_open_ticket"}) == "unknown_incident"
    ok &= classify_resolve(200, {"status": "correlation_required"}) == "unknown_incident"
    ok &= classify_resolve(409, None) == "unknown_incident"
    ok &= classify_resolve(0, None) == "queued_will_retry"
    ok &= classify_resolve(503, None) == "queued_will_retry"
    ok &= classify_resolve(403, None) == "setup_problem"
    ok &= classify_resolve(200, None) == "queued_will_retry"
    # RRX-007: the same resolution always sends the same operation_id.
    ok &= resolve_operation_id("RR-1", "restarted the gateway") == resolve_operation_id("RR-1", "restarted the gateway")
    ok &= resolve_operation_id("RR-1", "a").startswith("res-RR-1-")
    ok &= resolve_operation_id("RR-1", "a") != resolve_operation_id("RR-1", "b")
    ok &= _TICKET_RE.match("RR-000123") is not None and _TICKET_RE.match("../x") is None
    with tempfile.TemporaryDirectory() as d:
        def write(name, text):
            p = os.path.join(d, name)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
            return p

        p = write("last.env", "K=one\nK=two\n")
        ok &= dotenv_get(p, "K") == "two"                              # the LAST line wins
        p = write("comment.env", 'A=bare   # note\nQ="a # b"\n')
        ok &= dotenv_get(p, "A") == "bare"                             # bare: blank+# comment dropped
        ok &= dotenv_get(p, "Q") == "a # b"                            # quoted: the # is kept
        p = write("bom.env", "﻿B=bom\n")
        ok &= dotenv_get(p, "B") == "bom"                              # byte-order mark ignored
        p = write("trim.env", "V=tail   \n BAD KEY=1\n")
        ok &= dotenv_get(p, "V") == "tail"                             # only trailing blanks trimmed
        ok &= dotenv_get(p, "BAD KEY") == "" and parse_dotenv(p)[1] is True   # a blank in the key
        p = write("quote.env", 'U="open\n')
        ok &= dotenv_get(p, "U") == ""                                 # unterminated quote: not set
        p = write("export.env", "export E=ok\n")
        ok &= dotenv_get(p, "E") == "ok"                               # export prefix ignored
        p = write("junk.env", "GOOD=1\nthis line has no equals\n")
        ok &= dotenv_get(p, "GOOD") == "1"                             # a junk line never blocks
        ok &= parse_dotenv(p)[1] is True                               # but it is reported
        p = write("exec.env", "# c\nexport A='one two'\nB=\"x=y\"\nC=$(rm -rf /)\n")
        ok &= dotenv_get(p, "A") == "one two" and dotenv_get(p, "B") == "x=y"
        ok &= dotenv_get(p, "C") == "$(rm -rf /)"                      # returned as text, never executed
        ok &= dotenv_get(p, "MISSING") == ""
    ok &= "RR-1" in result("accepted", ticket_id="RR-1", reply_leg="enrolled")["say_to_owner"]
    ok &= "follow up with you directly" in result("accepted", ticket_id="RR-1", reply_leg="not_enrolled")["say_to_owner"]
    # RRX-011: a capped case is never told to wait for a reply that will not come.
    ok &= "follow up with you directly" in result("accepted", ticket_id="RR-1", reply_leg="enrolled", capped=True)["say_to_owner"]
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Ask Rescue Rangers for help")
    sub = ap.add_subparsers(dest="command")
    s = sub.add_parser("send")
    s.add_argument("--person", required=True)
    s.add_argument("--problem")
    s.add_argument("--problem-file")
    s.add_argument("--tried")
    s.add_argument("--tried-file")
    s.add_argument("--agent", help="this agent's name (stamped into AGENTS.md at install)")
    s.add_argument("--client", help="the client account label (stamped into AGENTS.md at install)")
    s.add_argument("--box-type", help="VPS, Mac Mini or MacBook Pro (stamped into AGENTS.md at install)")
    s.add_argument("--loop", action="store_true", help="the symptom is looping, stuck or no reply")
    s.add_argument("--origin-json", help='{"channel":"telegram","account":"default","target":"<owner chat id>"}')
    sub.add_parser("flush")
    r = sub.add_parser("resolve", help="close this box's own case with Rescue Rangers")
    r.add_argument("--ticket", required=True)
    r.add_argument("--fixed", required=True, help="what fixed it, in one line")
    t = sub.add_parser("status", help="read the outcome recorded for a ticket")
    t.add_argument("--ticket", required=True)
    sub.add_parser("selftest")
    a = ap.parse_args()
    try:
        if a.command == "send":
            return cmd_send(a)
        if a.command == "flush":
            return cmd_flush(a)
        if a.command == "resolve":
            return cmd_resolve(a)
        if a.command == "status":
            return cmd_status(a)
        if a.command == "selftest":
            return selftest()
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"state": "internal_failure", "detail": str(exc)}))
        return 2
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
