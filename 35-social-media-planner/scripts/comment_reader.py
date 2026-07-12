#!/usr/bin/env python3
"""comment_reader.py — Skill 35 Phase-4 comment reader (P3-08 Gap B, step 4).

WHY (P3-08 Gap B): Skill 35's campaign funnels the highest-intent reader to a
public comment ("the link is in the comments"), but nothing in the repo reads or
replies to public post comments — `caf`'s `social` group has NO comment/reply
command (playbook §17), and public post comments are NOT a GHL Conversations
event, so they never reach Skill 38's inbound webhook. A reader who followed the
campaign's own instruction and commented got no automated reply from anywhere.

WHAT this does: it turns prospect comment REPLIES into conversations. Given
normalized comment events (read via the §17 posting-ladder's available surface —
official GHL MCP or raw REST, since `caf` has no comment command), it surfaces
each prospect comment as a SYNTHETIC HANDOFF into Skill 38's existing pipeline:
it appends the comment to that contact's conversational log
(`<MASTER_FILES_DIR>/conversational-logs/<contact_id>__<name>.md`, the exact
format Skill 38's inbound hook reads), tagged with post/permalink context. The
comment becomes an inbound conversation Skill 38 already knows how to answer.

HONESTY / fail-closed (P3-08 step 4 + 2.4): this module NEVER fabricates a
comment feed. A channel with no comment-read API surface is LEDGERED per-channel
(returned in `skipped` with an explicit reason) and skipped — never faked. This
module does not itself call any live API; it consumes NORMALIZED comment events
(from a reader the orchestrator supplies for a channel that HAS a surface) so it
is deterministic and unit-testable, and so the "no surface" branch is explicit
rather than a silent empty result.

Input event shape (one per prospect comment reply), JSON list on --input/stdin:
  {
    "channel": "facebook" | "instagram" | "linkedin" | "youtube" |
               "pinterest" | "tiktok",
    "post_id": "<platform post id>",
    "permalink": "https://.../posts/...",           # post/permalink context
    "comment_id": "<platform comment id>",
    "author_id": "<platform author id>",            # maps to contact ref
    "author_name": "<display name>",                # optional
    "text": "<the prospect's comment text>",
    "created_at": "<iso8601>"                        # optional
  }

Output: for every event on a SUPPORTED channel, a synthetic handoff appended to
the contact's conversational log; a JSON summary of {handed_off, skipped} to
stdout. Exit 0 always (per-channel skips are a normal, ledgered outcome, not a
run failure); exit 2 only on a usage / unreadable-input error.

Usage:
  comment_reader.py --master-files-dir DIR [--input events.json] [--dry-run]
  cat events.json | comment_reader.py --master-files-dir DIR
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

# ── Per-channel comment-read capability (the §17 ladder's available surface) ──
# Ground truth, NOT aspiration: which channels expose a comment-READ API this
# pipeline can consume. `caf` has NO comment command on ANY channel (playbook
# §17), so a supported channel is one reachable via the official GHL MCP or raw
# REST. A channel marked None has NO comment-read surface today — its events are
# LEDGERED and skipped, never fabricated. Flip a channel to its surface string
# ONLY when that surface is verified live; until then it stays None (honest gap).
CHANNEL_COMMENT_SURFACE = {
    # GHL Social Planner surfaces FB/IG post interactions via the official MCP /
    # REST read path (the same §17 Tier-1/Tier-3 ladder used for posting).
    "facebook": "ghl-rest",
    "instagram": "ghl-rest",
    # No verified comment-read surface wired for these channels yet — ledger +
    # skip (never faked). Wire per-channel as each surface is proven live.
    "linkedin": None,
    "youtube": None,
    "pinterest": None,
    "tiktok": None,
}

_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(value: str) -> str:
    """Filesystem-safe token for a display name (mirrors Skill 38's
    <contact_id>__<name>.md convention; empty/None → 'prospect')."""
    value = (value or "").strip()
    if not value:
        return "prospect"
    return _SLUG_RE.sub("-", value).strip("-") or "prospect"


def _require(event: dict, key: str) -> str:
    val = event.get(key)
    if val is None or (isinstance(val, str) and not val.strip()):
        raise ValueError(f"comment event missing required field '{key}': {event!r}")
    return str(val)


def log_path_for(master_files_dir: str, contact_ref: str, author_name: str) -> str:
    """Skill 38 inbound-log path for this prospect. contact_ref is the platform
    author id (the stable per-prospect key); the name slug is cosmetic, matching
    Skill 38's `<contact_id>__<name>.md`."""
    logs_dir = os.path.join(master_files_dir, "conversational-logs")
    fname = f"comment-{_slug(contact_ref)}__{_slug(author_name)}.md"
    return os.path.join(logs_dir, fname)


def render_handoff_entry(event: dict, now_iso: str) -> str:
    """The markdown block appended to the contact's conversational log — a
    synthetic INBOUND turn tagged with post/permalink context so Skill 38's
    playbook pipeline treats it exactly like any other inbound message."""
    channel = _require(event, "channel")
    permalink = event.get("permalink") or event.get("post_id") or "(unknown post)"
    author = event.get("author_name") or event.get("author_id") or "prospect"
    created = event.get("created_at") or now_iso
    text = _require(event, "text")
    comment_id = event.get("comment_id") or "(unknown)"
    return (
        f"\n### Inbound — public comment ({channel}) — {created}\n"
        f"- source: Skill 35 comment-reader (synthetic handoff)\n"
        f"- post/permalink: {permalink}\n"
        f"- comment_id: {comment_id}\n"
        f"- author: {author}\n"
        f"- text: {text}\n"
        f"- NOTE for Skill 38: this arrived as a PUBLIC COMMENT, not a GHL "
        f"Conversations DM. Reply per the matching conversation playbook; the "
        f"reply channel is the public comment thread (or invite to DM), NOT SMS.\n"
    )


def run(events, master_files_dir: str, dry_run: bool = False):
    """Process normalized comment events. Returns a summary dict:
      {"handed_off": [...], "skipped": [...]}
    A skip carries an explicit per-channel reason (the ledgered no-surface case
    or a malformed event) — it is a normal outcome, never a silent drop."""
    handed_off = []
    skipped = []
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for idx, event in enumerate(events):
        if not isinstance(event, dict):
            skipped.append({"index": idx, "reason": "event is not an object"})
            continue
        channel = (event.get("channel") or "").strip().lower()
        if channel not in CHANNEL_COMMENT_SURFACE:
            skipped.append({"index": idx, "channel": channel or None,
                            "reason": "unknown channel"})
            continue
        surface = CHANNEL_COMMENT_SURFACE[channel]
        if surface is None:
            # Ledger the per-channel gap; NEVER fabricate a comment feed.
            skipped.append({"index": idx, "channel": channel,
                            "reason": "no comment-read API surface wired for "
                                      "this channel (ledgered, not fabricated)"})
            continue
        try:
            contact_ref = _require(event, "author_id")
            entry = render_handoff_entry(event, now_iso)
        except ValueError as exc:
            skipped.append({"index": idx, "channel": channel,
                            "reason": f"malformed event: {exc}"})
            continue

        path = log_path_for(master_files_dir, contact_ref,
                            event.get("author_name") or "")
        if not dry_run:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            header_needed = not os.path.exists(path)
            with open(path, "a", encoding="utf-8") as fh:
                if header_needed:
                    fh.write(f"# Conversation log — {contact_ref}\n"
                             f"(seeded by Skill 35 comment-reader; Skill 38 owns "
                             f"replies)\n")
                fh.write(entry)
        handed_off.append({"index": idx, "channel": channel,
                           "surface": surface, "contact_ref": contact_ref,
                           "log_path": path, "dry_run": dry_run})

    return {"handed_off": handed_off, "skipped": skipped}


def _load_events(input_path):
    raw = open(input_path, encoding="utf-8").read() if input_path else sys.stdin.read()
    raw = raw.strip()
    if not raw:
        return []
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("events", data.get("comments", [data]))
    if not isinstance(data, list):
        raise ValueError("input must be a JSON list of comment events "
                         "(or an object with an 'events' list)")
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description="Skill 35 comment reader (P3-08)")
    ap.add_argument("--master-files-dir", required=True,
                    help="OpenClaw master-files dir (holds conversational-logs/)")
    ap.add_argument("--input", default=None,
                    help="JSON file of comment events (default: stdin)")
    ap.add_argument("--dry-run", action="store_true",
                    help="classify + report, write nothing")
    args = ap.parse_args(argv)

    try:
        events = _load_events(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"comment_reader: cannot read input: {exc}", file=sys.stderr)
        return 2

    summary = run(events, args.master_files_dir, dry_run=args.dry_run)
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
