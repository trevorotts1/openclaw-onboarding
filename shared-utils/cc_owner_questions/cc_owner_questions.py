#!/usr/bin/env python3
"""Command Center owner questions: list, recognise and answer from chat.

The Command Center stores each question for the client, adds a plain-English
recommendation and pushes ONE message to the client's chat that ends with
"(ref Q-ABC123)". This helper is the agent's side: it finds the open questions,
recognises which one a client reply belongs to, and posts the client's exact
words back. It NEVER sends a Telegram or chat message itself.

Subcommands
  open   [--json]
  match  --text TEXT [--json]
  answer --ref Q-XXXXXX|ID --text TEXT --source-message-ref ID [--channel telegram|webchat] [--json]

Exit codes
  0  success (answer applied, listing printed, or a question matched)
  1  match found nothing / ambiguous (match only)
  2  bad usage
  3  Command Center unreachable, or no MC_API_TOKEN on this box
  4  Command Center needs updating (the owner-questions route is missing)
  5  unknown question (404 from a Command Center that has the route)
  6  already answered (409)
  7  message not verified by the Command Center (422)
  8  any other Command Center error

Python 3 standard library only. The token is read, sent as a bearer header and
never printed.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:4000"
TIMEOUT = 20
REF_RE = re.compile(r"\bQ-([A-Za-z0-9]{4,12})\b", re.I)
NEEDS_UPDATE = ("The Command Center on this box needs updating: it does not have the "
                "owner-questions route yet. Tell the operator; do not ask the client to retry.")

# Same store order as scripts/mc-route.sh (_ENV_STORES), then the live env.
ENV_STORES = [
    "~/projects/command-center/.env.local",
    "~/projects/command-center/.env",
    "/data/projects/command-center/.env.local",
    "/data/projects/command-center/.env",
    "~/.openclaw/secrets/.env",
    "/data/.openclaw/secrets/.env",
]


def _parse_dotenv(path):
    out = {}
    try:
        with open(os.path.expanduser(path), "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("export "):
                    s = s[len("export "):]
                if "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                out[k] = v
    except OSError:
        return {}
    return out


def resolve(*keys):
    for store in ENV_STORES:
        kv = _parse_dotenv(store)
        for k in keys:
            if kv.get(k):
                return kv[k]
    for k in keys:
        if os.environ.get(k):
            return os.environ[k]
    return ""


def resolve_base():
    explicit = os.environ.get("CC_OWNER_QUESTIONS_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    ingest = os.environ.get("MC_ROUTE_INGEST_URL", "").strip()
    if ingest:
        return re.sub(r"/api/tasks/ingest/?$", "", ingest).rstrip("/")
    mcu = os.environ.get("MISSION_CONTROL_URL", "").strip()
    if mcu:
        return mcu.rstrip("/")
    return DEFAULT_BASE


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect so the bearer token never follows one to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)
REF_OK = re.compile(r"^(Q-[A-Z0-9]{4,12}|[A-Za-z0-9-]{8,64})$")


class CCError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _request(method, path, body=None):
    token = resolve("MC_API_TOKEN")
    if not token:
        raise CCError(3, "No MC_API_TOKEN found on this box, so the Command Center cannot be reached.")
    url = resolve_base() + path
    data = None
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace") if e.fp else ""
        status = e.code
    except (urllib.error.URLError, OSError) as e:
        raise CCError(3, "Command Center unreachable at %s (%s)." % (resolve_base(), getattr(e, "reason", e)))
    if 300 <= status < 400:
        raise CCError(8, "Command Center answered with a redirect (HTTP %s); redirects are refused "
                         "so the token is never forwarded. Check the Command Center address." % status)
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except ValueError:
        parsed = None
    return status, parsed, raw


def _msg(parsed, fallback):
    if isinstance(parsed, dict):
        for k in ("message", "error", "detail"):
            if isinstance(parsed.get(k), str) and parsed[k]:
                return parsed[k]
    return fallback


def _is_route_missing(status, parsed):
    """A 404 with no JSON object body is a Command Center without the route."""
    return status == 404 and not isinstance(parsed, dict)


def list_open():
    status, parsed, _ = _request("GET", "/api/owner-questions?status=open")
    if _is_route_missing(status, parsed) or status == 404:
        raise CCError(4, NEEDS_UPDATE)
    if status != 200 or not isinstance(parsed, dict):
        raise CCError(8, "Command Center returned HTTP %s for the open-questions list." % status)
    qs = parsed.get("questions")
    return qs if isinstance(qs, list) else []


def _show(q):
    return "%s  %s\n  Recommendation: %s" % (
        q.get("short_code") or q.get("id"), q.get("question", ""), q.get("recommendation", ""))


def cmd_open(args):
    qs = list_open()
    if args.json:
        print(json.dumps({"questions": qs}))
    elif not qs:
        print("No open questions.")
    else:
        for q in qs:
            print(_show(q))
    return 0


def find_ref(text):
    m = REF_RE.search(text or "")
    return "Q-" + m.group(1).upper() if m else None


def cmd_match(args):
    ref = find_ref(args.text)
    if ref:
        res = {"match": "explicit", "ref": ref}
        print(json.dumps(res) if args.json else ref)
        return 0
    qs = list_open()
    if len(qs) == 1:
        q = qs[0]
        res = {"match": "single-open", "ref": q.get("short_code") or q.get("id"),
               "question": q.get("question"), "recommendation": q.get("recommendation")}
        print(json.dumps(res) if args.json else "single-open %s  %s" % (res["ref"], res["question"]))
        return 0
    res = {"match": "ambiguous" if qs else "none", "open_count": len(qs)}
    print(json.dumps(res) if args.json else ("none" if not qs else "ambiguous %d open" % len(qs)))
    return 1


def cmd_answer(args):
    if not args.text.strip():
        print("The answer text is empty.", file=sys.stderr)
        return 2
    if not args.source_message_ref.strip():
        print("--source-message-ref is required (the real inbound message id).", file=sys.stderr)
        return 2
    ref = args.ref.strip()
    if ref[:2].upper() == "Q-":
        ref = ref.upper()
    if ".." in ref or not REF_OK.match(ref):
        print("--ref must look like Q-ABC123 or a question id.", file=sys.stderr)
        return 2
    path = "/api/owner-questions/%s/chat-answer" % urllib.parse.quote(ref, safe="")
    body = {"answer": args.text, "channel": args.channel,
            "source_message_ref": args.source_message_ref}
    status, parsed, _ = _request("POST", path, body)
    if status == 200:
        if not (isinstance(parsed, dict) and parsed.get("success") is True):
            raise CCError(8, "The Command Center did not confirm the answer was saved.")
        out = parsed
        print(json.dumps(out) if args.json else
              "Answer recorded for %s%s." % (ref, "" if out.get("applied") is not False else
                                              " (recorded, not yet applied)"))
        return 0
    if _is_route_missing(status, parsed):
        raise CCError(4, NEEDS_UPDATE)
    if status == 404:
        raise CCError(5, "No open question matches %s." % ref)
    if status == 409:
        raise CCError(6, "That question was already answered.")
    if status == 422:
        raise CCError(7, "The Command Center could not verify that chat message: %s" %
                      _msg(parsed, "message not verified"))
    raise CCError(8, "Command Center returned HTTP %s: %s" % (status, _msg(parsed, "error")))


def build_parser():
    p = argparse.ArgumentParser(description="Command Center owner questions (read, match, answer).")
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open", help="list open owner questions")
    o.add_argument("--json", action="store_true")
    m = sub.add_parser("match", help="find which question a client message answers")
    m.add_argument("--text", required=True)
    m.add_argument("--json", action="store_true")
    a = sub.add_parser("answer", help="post the client's reply back")
    a.add_argument("--ref", required=True)
    a.add_argument("--text", required=True)
    a.add_argument("--source-message-ref", required=True)
    a.add_argument("--channel", default="telegram", choices=["telegram", "webchat"])
    a.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        return {"open": cmd_open, "match": cmd_match, "answer": cmd_answer}[args.cmd](args)
    except CCError as e:
        print(e.message, file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
