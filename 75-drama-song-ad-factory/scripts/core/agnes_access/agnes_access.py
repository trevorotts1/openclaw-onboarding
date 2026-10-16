#!/usr/bin/env python3
"""agnes_access: the client's remembered Agnes answer, and the Agnes key (SPEC A2/A3).

SPEC A2 (decided, LEDGER 13:15) — the client is ASKED DIRECTLY, then the answer is
remembered. No key check, no plan check and no detection ever decides who sees the
AGNES question. The answer lives in the client's own data folder (the folder the
character library already uses):

    <client_dir>/agnes.json    {"subscriber": "yes"|"no", "answered_at": "<UTC>"}

A remembered "no" hides the question on later cards (one recap line, reply ``agnes``
to change it); a remembered "yes" still asks. Anything unreadable or unrecognized
reads as "unknown" — never a crash, never a guess.

SPEC A3 — ``key_value`` is the ONE function that touches the key. It looks in env
``AGNES_AI_API_KEY`` (OpenClaw boxes), then ``AGNES_API_KEY`` (999 computers), then
the ``AGNES_API_KEY=`` line of ``<Documents>/API docs.md`` (the file
nine-router-setup reads). A placeholder value counts as absent. The value stays in
memory only: it never reaches stdout, a log, a receipt, a ledger or a test output.
Only ``key_present`` (a boolean) is safe to print or record.

Stdlib only. No network. Writes are atomic (temp file in the same folder, then rename).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

AGNES_FILE = "agnes.json"
ANSWERS = ("yes", "no")
ENV_NAMES = ("AGNES_AI_API_KEY", "AGNES_API_KEY")
API_DOCS_NAME = "API docs.md"
API_DOCS_NAME_IN_FILE = "AGNES_API_KEY"


class AccessError(ValueError):
    """Plain-English reason a remember write was refused."""


# Placeholder text from nine-router-setup references/credential-contract.md
# ("Reject empty values and placeholder text"). Matched case-insensitively.
_PLACEHOLDER_TOKENS = ("replace_with_real_key", "changeme", "your-key", "your_key")
_PLACEHOLDER_EXACT = ("xxx", "placeholder", "todo", "example", "none", "null",
                      "redacted", "key", API_DOCS_NAME_IN_FILE.lower(),
                      "agnes_ai_api_key")


def _is_placeholder(value):
    """An empty, template or obviously-fake value is not a key (SPEC A3)."""
    v = str(value if value is not None else "").strip()
    if not v:
        return True
    low = v.lower()
    if (low.startswith("<") and low.endswith(">")) or \
       (low.startswith("{{") and low.endswith("}}")):
        return True
    if any(tok in low for tok in _PLACEHOLDER_TOKENS):
        return True
    return low in _PLACEHOLDER_EXACT


def _read(client_dir):
    """The whole agnes.json record as a dict, or {} when it is absent/unreadable."""
    if not client_dir:
        return {}
    path = os.path.join(os.path.expanduser(str(client_dir)), AGNES_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return {}
    return rec if isinstance(rec, dict) else {}


def remembered(client_dir):
    """The remembered answer: "yes", "no", or "unknown" (SPEC A2)."""
    answer = _read(client_dir).get("subscriber")
    return answer if answer in ANSWERS else "unknown"


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def remember(client_dir, answer):
    """Remember the client's answer in <client_dir>/agnes.json, merging.

    Other keys already in the file are kept (this never clobbers them). The write is
    atomic. Returns the stored answer; raises AccessError on an unusable answer or a
    missing client folder.
    """
    stored = str(answer if answer is not None else "").strip().lower()
    if stored not in ANSWERS:
        raise AccessError("The Agnes answer is yes or no, not %r." % (answer,))
    folder = str(client_dir or "").strip()
    if not folder:
        raise AccessError("A client data folder is needed to remember the Agnes answer.")
    folder = os.path.expanduser(folder)
    rec = _read(folder)
    rec["subscriber"] = stored
    rec["answered_at"] = _utcnow()
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, AGNES_FILE)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)
    return stored


def _documents(documents_dir=None):
    """The folder holding API docs.md. ponytail: the nine-router installer resolves the
    real Documents folder per platform (osascript on macOS, OneDrive-safe on Windows)
    because that file can live elsewhere; the factory takes the folder as an argument
    and defaults to ~/Documents. Upgrade path: pass documents_dir explicitly on a box
    whose Documents is not ~/Documents."""
    if documents_dir:
        return os.path.expanduser(str(documents_dir))
    return os.path.expanduser("~/Documents")


def _docs_key(documents_dir):
    """The AGNES_API_KEY= line of <documents_dir>/API docs.md, or None."""
    path = os.path.join(_documents(documents_dir), API_DOCS_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    in_fence = False
    for line in lines:
        text = line.strip()
        if text.startswith("```"):
            in_fence = not in_fence
            continue                       # the fenced EXAMPLE is not the key
        if in_fence or not text or text.startswith(("#", "<!--")):
            continue                       # blanks, headings, comments
        name, sep, value = text.partition("=")
        if not sep or name.strip() != API_DOCS_NAME_IN_FILE:
            continue
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1].strip()
        return value or None
    return None


def key_value(env=None, documents_dir=None):
    """The Agnes key, or None. The ONE function that touches the value (SPEC A3).

    Order: env AGNES_AI_API_KEY, env AGNES_API_KEY, then the API docs.md line.
    A placeholder value counts as absent. The value stays in memory only — it is
    never printed, logged or written anywhere.
    """
    if env is None:
        env = os.environ
    for name in ENV_NAMES:
        found = env.get(name)
        if found is not None and not _is_placeholder(found):
            return str(found).strip()
    key = _docs_key(documents_dir)
    return None if key is None or _is_placeholder(key) else key


def key_present(env=None, documents_dir=None):
    """True when a real (non-placeholder) Agnes key is available. Safe to print."""
    return key_value(env=env, documents_dir=documents_dir) is not None


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="agnes_access",
        description="The remembered Agnes answer and key presence. Never prints the key.")
    sub = parser.add_subparsers(dest="command")
    status = sub.add_parser("status", help="the remembered answer and key presence")
    status.add_argument("--client-dir", default=None,
                        help="the client data folder holding agnes.json")
    status.add_argument("--documents-dir", default=None,
                        help="the folder holding API docs.md (default ~/Documents)")
    args = parser.parse_args(argv)
    if args.command != "status":
        parser.print_help()
        return 2
    print(json.dumps({"remembered": remembered(args.client_dir),
                      "key_present": key_present(documents_dir=args.documents_dir)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
