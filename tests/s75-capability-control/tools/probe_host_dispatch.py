#!/usr/bin/env python3
"""Minimal live host-dispatch probe for S75-W04-U2 (evidence only).

Proves the chosen model through the INSTALLED host (the 9Router at
ANTHROPIC_BASE_URL) with the smallest non-destructive completion probe, then
correlates the router-side requestDetails receipt. The API key is read from the
router's own key table and never printed or saved.

    python3 -I tools/probe_host_dispatch.py --model openrouter/xiaomi/mimo-v2.6-pro
"""
import argparse
import datetime as _dt
import json
import os
import sqlite3
import sys
import urllib.request

UNIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTER_DB = os.path.expanduser("~/.9router/db/data.sqlite")
HOST_BASE = os.environ.get("S75_HOST_BASE", "http://127.0.0.1:20128")
KEY_NAME = os.environ.get("S75_KEY_NAME", "local-claude-nine")


def now_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="microseconds")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", default=os.path.join(UNIT_ROOT, "evidence"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    con = sqlite3.connect(ROUTER_DB)
    row = con.execute("SELECT key FROM apiKeys WHERE name=? AND isActive=1", (KEY_NAME,)).fetchone()
    if not row:
        print("no active api key named %r in router db" % KEY_NAME)
        return 2
    api_key = row[0]

    body = {
        "model": args.model,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
    }
    req = urllib.request.Request(
        HOST_BASE + "/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    sent_at = now_iso()
    status = None
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8")
    received_at = now_iso()
    # The gateway emits two response shapes: a JSON body or an SSE stream whose
    # message_start event carries the response model metadata.
    response_model = None
    router_receipt_id = None
    thinking_block_seen = False
    try:
        resp_doc = json.loads(raw)
        if isinstance(resp_doc, dict):
            response_model = resp_doc.get("model")
            router_receipt_id = resp_doc.get("id")
    except ValueError:
        events = []
        for line in raw.splitlines():
            if line.startswith("data:"):
                try:
                    evt = json.loads(line[5:].strip())
                except ValueError:
                    continue
                events.append(evt)
                if evt.get("type") == "message_start":
                    message = evt.get("message") or {}
                    response_model = message.get("model")
                    router_receipt_id = message.get("id")
                if evt.get("type") == "content_block_start" and (evt.get("content_block") or {}).get("type") == "thinking":
                    thinking_block_seen = True
        resp_doc = {"sse_events": len(events), "message_start_model": response_model,
                    "thinking_block_seen": thinking_block_seen}

    # Redact anything credential-shaped before saving.
    def scrub(obj):
        if isinstance(obj, dict):
            return {k: ("<redacted>" if any(m in k.lower() for m in ("key", "token", "secret", "auth")) else scrub(v))
                    for k, v in obj.items()}
        if isinstance(obj, list):
            return [scrub(v) for v in obj]
        return obj

    receipt = {
        "probe": "host-dispatch",
        "requested_model": args.model,
        "http_status": status,
        "response_model": response_model,
        "router_receipt_id": router_receipt_id,
        "thinking_block_seen": thinking_block_seen,
        "sent_at": sent_at,
        "received_at": received_at,
        "request": {"model": body["model"], "max_tokens": body["max_tokens"]},
        "response": scrub(resp_doc),
    }

    # Correlate the router-side receipt (server/router request receipt).
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, timestamp, provider, model, status FROM requestDetails "
        "WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 5",
        (sent_at[:19],),
    ).fetchall()
    receipt["router_request_rows"] = [dict(r) for r in rows]
    con.close()

    name = "host-dispatch-%s.json" % args.model.replace("/", "_")
    path = os.path.join(args.out, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("status=%s response_model=%s saved=%s router_rows=%d"
          % (status, response_model, path, len(receipt["router_request_rows"])))
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
