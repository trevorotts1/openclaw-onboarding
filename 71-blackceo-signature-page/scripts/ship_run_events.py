#!/usr/bin/env python3
"""Ship Skill 71 run events to the Command Center ingest endpoint.

Fix plan Item 24 (Amendment 1 rider): on fleet-hostinger (and on an
opted-in fleet-mac, and as fleet-contabo's fallback if the Command Center
ever moves off the Contabo host), event delivery is push-primary with a
spool fallback. The gate/runner POST each event as it happens; whatever
could not be delivered lands in the spool directory as JSONL files. This
shipper drains the spool, in order, and can also forward host-index lines
that were never shipped.

Contract (references/run-events-schema.md):
  - Delivery is at-least-once. The server dedupes by event_id, and this
    shipper dedupes locally too, so re-running is always safe.
  - Only schema-shaped lines are ever sent: a line must parse as JSON and
    carry event_id, event_type, schema_version, emitted_at, and run_id.
    Anything else is quarantined (spool/quarantine.jsonl), never sent.
  - The bearer token is read from the file named by
    SKILL71_RUNS_SHIP_TOKEN_FILE at send time and travels only in the
    Authorization header. It is never printed, logged, or written
    anywhere by this script.
  - Nothing beyond the event line is sent: no file contents, no extra
    fields, no run-folder data.

Usage:
  ship_run_events.py [--once] [--dry-run]
Environment:
  SKILL71_RUNS_SHIP_URL        ingest endpoint (required unless --dry-run
                                against a spool only)
  SKILL71_RUNS_SHIP_TOKEN_FILE path to the per-client token file
  SKILL71_RUNS_SPOOL           spool directory (default: ./skill71-spool)
  SKILL71_RUNS_INDEX           optional host index JSONL to also drain
  SKILL71_RUNS_SHIP_STATE      state file path (default: <spool>/ship-state.json)

Exit codes: 0 = everything deliverable was delivered (or dry run),
1 = at least one line could not be delivered (left in place for the next
run), 2 = configuration error.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENVELOPE_FIELDS = ("event_id", "event_type", "schema_version", "emitted_at", "run_id")


def fail_config(msg):
    print(f"ship_run_events: configuration error: {msg}", file=sys.stderr)
    return 2


def load_state(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {"shipped_event_ids": [], "index_offset": 0}


def save_state(path, state):
    state["shipped_event_ids"] = sorted(set(state["shipped_event_ids"]))[-100000:]
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(path)


def parse_line(raw):
    """Return (event_dict, None) or (None, reason). Strict envelope check."""
    try:
        event = json.loads(raw)
    except Exception as exc:
        return None, f"unparseable JSON: {exc}"
    if not isinstance(event, dict):
        return None, "line is not a JSON object"
    missing = [f for f in ENVELOPE_FIELDS if f not in event]
    if missing:
        return None, f"missing envelope fields: {', '.join(missing)}"
    return event, None


def post_events(url, token, events):
    """POST one batch. Returns True on a 2xx, False otherwise."""
    body = json.dumps({"events": events}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        print(f"ship_run_events: ingest answered HTTP {exc.code}", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"ship_run_events: POST failed: {exc}", file=sys.stderr)
        return False


def drain_spool(spool_dir, state, send, dry_run):
    """Send every *.jsonl line in the spool, oldest file first.

    Delivered lines are removed (the file is rewritten without them);
    undeliverable lines stay put. Returns the number of failed lines.
    """
    failures = 0
    spool = Path(spool_dir)
    if not spool.is_dir():
        return 0
    for path in sorted(spool.glob("*.jsonl")):
        if path.name == "quarantine.jsonl":
            continue
        kept = []
        shipped_ids = set(state["shipped_event_ids"])
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            event, reason = parse_line(raw)
            if event is None:
                quarantine(spool, raw, reason)
                continue
            if event["event_id"] in shipped_ids:
                continue  # already delivered earlier; drop the copy
            if dry_run:
                print(f"DRY-RUN would send {event['event_type']} {event['event_id']}")
                kept.append(raw)
                continue
            if send([event]):
                state["shipped_event_ids"].append(event["event_id"])
                shipped_ids.add(event["event_id"])
            else:
                failures += 1
                kept.append(raw)
        if not dry_run:
            if kept:
                path.write_text("\n".join(kept) + "\n", encoding="utf-8")
            else:
                path.unlink()
    return failures


def drain_index(index_path, state, send, dry_run):
    """Forward host-index lines past the recorded byte offset.

    The index is append-only and never rewritten by the shipper; the
    offset and the shipped-id set together make re-runs no-ops.
    """
    failures = 0
    path = Path(index_path)
    if not path.exists():
        return 0
    data = path.read_bytes()
    offset = int(state.get("index_offset", 0))
    if offset > len(data):
        offset = 0  # index was rotated or replaced; the id set still dedupes
    shipped_ids = set(state["shipped_event_ids"])
    pos = offset
    for raw_bytes in data[offset:].splitlines(keepends=True):
        line = raw_bytes.decode("utf-8", errors="replace").strip()
        advance = True
        if line:
            event, reason = parse_line(line)
            if event is None:
                # A malformed index line will never become sendable; log it
                # and move past it (the run-local feed still holds the truth).
                print(f"ship_run_events: index line skipped ({reason})", file=sys.stderr)
            elif event["event_id"] in shipped_ids:
                pass
            elif dry_run:
                print(f"DRY-RUN would send {event['event_type']} {event['event_id']}")
            elif send([event]):
                state["shipped_event_ids"].append(event["event_id"])
                shipped_ids.add(event["event_id"])
            else:
                failures += 1
                advance = False  # stop at the failed line; order is preserved
        if not advance:
            break
        pos += len(raw_bytes)
    if not dry_run:
        state["index_offset"] = pos
    return failures


def quarantine(spool_dir, raw, reason):
    q = Path(spool_dir) / "quarantine.jsonl"
    with q.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"line": raw, "reason": reason}) + "\n")
    print(f"ship_run_events: quarantined a line ({reason})", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ship Skill 71 run events (Item 24).")
    parser.add_argument("--once", action="store_true",
                        help="drain once and exit (the only mode; kept for timer units)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would be sent; send and change nothing")
    parser.add_argument("--url", default=os.environ.get("SKILL71_RUNS_SHIP_URL"))
    parser.add_argument("--token-file",
                        default=os.environ.get("SKILL71_RUNS_SHIP_TOKEN_FILE"))
    parser.add_argument("--spool", default=os.environ.get("SKILL71_RUNS_SPOOL", "./skill71-spool"))
    parser.add_argument("--index", default=os.environ.get("SKILL71_RUNS_INDEX"))
    parser.add_argument("--state",
                        default=os.environ.get("SKILL71_RUNS_SHIP_STATE"))
    args = parser.parse_args(argv)

    if not args.dry_run and not args.url:
        return fail_config("SKILL71_RUNS_SHIP_URL is not set")
    token = None
    if args.token_file:
        try:
            token = Path(args.token_file).read_text(encoding="utf-8").strip()
        except Exception as exc:
            return fail_config(f"cannot read token file: {exc}")
    if not args.dry_run and not token:
        return fail_config("no ship token (SKILL71_RUNS_SHIP_TOKEN_FILE unset or empty)")

    state_path = args.state or str(Path(args.spool) / "ship-state.json")
    state = load_state(state_path)

    def send(events):
        return post_events(args.url, token, events)

    failures = 0
    failures += drain_spool(args.spool, state, send, args.dry_run)
    if args.index:
        failures += drain_index(args.index, state, send, args.dry_run)
    if not args.dry_run:
        Path(args.spool).mkdir(parents=True, exist_ok=True)
        save_state(state_path, state)
    if failures:
        print(f"ship_run_events: {failures} line(s) could not be delivered; left in place",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
