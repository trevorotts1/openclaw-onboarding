#!/usr/bin/env python3
"""Presentation-notify relay -- called by the engine Reporter (report.py dispatch3).
Contract: reads stdin JSON `{"chat_id":"...","kind":"...","message":"..."}`
and sends via the OpenClaw gateway (`openclaw message send`), matching the
Command Center notify.ts transport contract. NEVER posts to api.telegram.org
directly -- the raw Bot API with the operator token violates the fleet
gateway-only rule (see delivery-concierge.md step 3 and CC src/lib/notify.ts
"GATEWAY-ONLY: every send goes through `openclaw message send`").
Exits 0 on success, non-zero on failure (dispatch3 maps non-zero to
UNDETERMINED and queues the message for retry via --sweep-undeliverable).

FIX 23 (presentation rev2 waves): the transport is gateway-only. Rollback:
set PRESENTATION_NOTIFY_DIRECT_TELEGRAM=1 to restore the legacy direct-Bot-API
path (reads OPERATOR_TELEGRAM_BOT_TOKEN again); that flag is the only supported
pre-fix coexistence mode, and it stays opt-in -- the gateway is the default.

Exit codes (stable dispatch3 contract, see tests/test_report.py):
  0  -- sent via the gateway (or dry-run dispatch succeeded)
  2  -- transport misconfiguration (gateway CLI absent AND no legacy flag)
  3  -- stdin is not valid JSON
  4  -- no chat_id in payload and no OWNER_CHAT_ID fallback
  5  -- gateway send rejected/failed (non-zero gateway exit, timeout, OSError)
"""
import os, sys, json, shutil, subprocess

DEFAULT_NOTIFY_TIMEOUT_S = 30  # matches CC src/lib/notify.ts OWNER_SEND_TIMEOUT_MS

# The gateway transport contract (openclaw 2026.x CLI flags). --target and
# --message are the real flags; the old --to/--text do not exist (commander
# rejects them) -- same finding notify.ts documents.
_GATEWAY_CHANNEL_DEFAULT = "telegram"


def _notify_timeout_s() -> float:
    raw = os.environ.get("PRESENTATION_NOTIFY_TIMEOUT_S", "")
    if not raw:
        return DEFAULT_NOTIFY_TIMEOUT_S
    try:
        val = float(raw)
    except ValueError:
        return DEFAULT_NOTIFY_TIMEOUT_S
    return val if val > 0 else DEFAULT_NOTIFY_TIMEOUT_S


def _send_via_gateway(chat_id: str, text: str) -> int:
    """Route through `openclaw message send` (the fleet gateway). Returns the
    gateway process exit code; 0 means the send was dispatched/accepted."""
    cli = shutil.which("openclaw") or "openclaw"
    channel = (os.environ.get("PRESENTATION_NOTIFY_CHANNEL")
               or _GATEWAY_CHANNEL_DEFAULT).strip() or _GATEWAY_CHANNEL_DEFAULT
    argv = [
        cli, "message", "send",
        "--channel", channel,
        "--target", chat_id,
        "--message", text,
        "--json",
    ]
    if os.environ.get("PRESENTATION_NOTIFY_DRY_RUN") == "1":
        argv.append("--dry-run")
    try:
        proc = subprocess.run(argv, shell=False, capture_output=True,
                              text=True, timeout=_notify_timeout_s())
    except subprocess.TimeoutExpired:
        print(f"FATAL: openclaw message send timed out after "
              f"{_notify_timeout_s():.0f}s", file=sys.stderr)
        return 5
    except OSError as exc:
        print(f"FATAL: could not execute the openclaw gateway CLI: {exc}",
              file=sys.stderr)
        return 5
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:200]
        print(f"FATAL: openclaw message send rc={proc.returncode}: {detail}",
              file=sys.stderr)
        return 5
    # Parse best-effort; --json output carries the gateway's message id when
    # a real (non-dry-run) send completed.
    out = (proc.stdout or "").strip()
    msg_id = ""
    for line in reversed(out.splitlines()):
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            doc = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg_id = (doc.get("message_id")
                  or (doc.get("payload") or {}).get("message_id")
                  or "")
        if msg_id:
            break
    print(f"sent: transport=openclaw-gateway message_id={msg_id or 'n/a'}",
          flush=True)
    return 0


def _send_direct_telegram(chat_id: str, text: str) -> int:
    """LEGACY rollback path ONLY (PRESENTATION_NOTIFY_DIRECT_TELEGRAM=1).
    Posts straight to api.telegram.org with the operator bot token. Kept so an
    operator can revert to the pre-FIX-23 posture without a code rollback; not
    reachable unless the flag is explicitly set."""
    import urllib.request, urllib.parse
    bot = os.environ.get("OPERATOR_TELEGRAM_BOT_TOKEN", "")
    if not bot:
        print("FATAL: OPERATOR_TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 2
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{bot}/sendMessage",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        if result.get("ok"):
            print(f"sent: message_id={result.get('result', {}).get('message_id')}",
                  flush=True)
            return 0
        print(f"API rejected: {result.get('description','unknown')}",
              file=sys.stderr)
        return 5
    except Exception as exc:
        print(f"Transport error: {exc}", file=sys.stderr)
        return 5


def main() -> int:
    direct_rollback = os.environ.get("PRESENTATION_NOTIFY_DIRECT_TELEGRAM") == "1"
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"FATAL: stdin is not valid JSON: {exc}", file=sys.stderr)
        return 3
    chat_id = payload.get("chat_id") or os.environ.get("OWNER_CHAT_ID", "")
    if not chat_id:
        print("FATAL: no chat_id in payload and OWNER_CHAT_ID is not set",
              file=sys.stderr)
        return 4
    kind = payload.get("kind", "progress")
    msg = payload.get("message", "")
    text = (f"[Presentation Dept] {str(kind).upper()}: {msg}" if msg
            else f"[Presentation Dept] {str(kind).upper()}")
    if direct_rollback:
        return _send_direct_telegram(chat_id, text)
    if not shutil.which("openclaw"):
        print("FATAL: openclaw gateway CLI not found on PATH; the gateway-only "
              "transport cannot deliver. Set PRESENTATION_NOTIFY_DIRECT_TELEGRAM=1 "
              "only for a documented, temporary rollback.", file=sys.stderr)
        return 2
    return _send_via_gateway(chat_id, text)


if __name__ == "__main__":
    sys.exit(main())
