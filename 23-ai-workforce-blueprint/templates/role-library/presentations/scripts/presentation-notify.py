#!/usr/bin/env python3
"""Presentation-notify relay -- called by the engine Reporter.
Contract: reads stdin JSON `{"chat_id":"...","kind":"...","message":"..."}`
Calls Telegram sendMessage API with the operator bot token.
Exits 0 on success, non-zero on failure.
"""
import os, sys, json, urllib.request, urllib.parse

def main():
    BOT = os.environ.get("OPERATOR_TELEGRAM_BOT_TOKEN", "")
    if not BOT:
        print("FATAL: OPERATOR_TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        sys.exit(2)
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"FATAL: stdin is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(3)
    chat_id = payload.get("chat_id") or os.environ.get("OWNER_CHAT_ID", "")
    if not chat_id:
        print("FATAL: no chat_id in payload and OWNER_CHAT_ID is not set", file=sys.stderr)
        sys.exit(4)
    kind = payload.get("kind", "progress")
    msg  = payload.get("message", "")
    text = f"[Presentation Dept] {kind.upper()}: {msg}" if msg else f"[Presentation Dept] {kind.upper()}"
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        if result.get("ok"):
            msg_id = result.get("result", {}).get("message_id")
            print(f"sent: message_id={msg_id}", flush=True)
            sys.exit(0)
        else:
            print(f"API rejected: {result.get('description','unknown')}", file=sys.stderr)
            sys.exit(5)
    except Exception as exc:
        print(f"Transport error: {exc}", file=sys.stderr)
        sys.exit(5)

if __name__ == "__main__":
    main()
