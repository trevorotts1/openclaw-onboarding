#!/usr/bin/env python3
"""
Scan for incomplete AI Workforce interviews and send Telegram nudges.

Cadence (per PRD v2.1):
- +24h idle  : "You're {progress}% done. Want to keep going?"
- +72h idle  : "Still want to finish? You stopped at {last_question}."
- +168h idle : "Want me to finish your setup with best-guess defaults? Reply YES."

After the final nudge, if owner replies YES, automation triggers Option B
(Quick Setup) which completes the build in 25-45 min using best-guess defaults.

Run via cron every 6 hours:
    0 */6 * * * /usr/bin/python3 /path/to/shared-utils/nudge-incomplete-interviews.py

Idempotent: records which nudges have been sent per company to avoid re-sending.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from detect_platform import get_openclaw_paths


NUDGE_CONFIG = [
    {
        "key": "nudge_24h",
        "hours_idle": 24,
        "message_template": (
            "Hey {name} 👋 — you're {progress}% done setting up your AI workforce. "
            "Want to pick back up? Open your setup here:\n{link}\n\n"
            "Everything you've answered is saved."
        ),
    },
    {
        "key": "nudge_72h",
        "hours_idle": 72,
        "message_template": (
            "Hey {name} — still want to finish your AI workforce setup? "
            "You stopped at: {last_question}\n\n"
            "Resume here: {link}"
        ),
    },
    {
        "key": "nudge_168h",
        "hours_idle": 168,
        "message_template": (
            "Hey {name} — last check-in on your AI workforce setup. "
            "Want me to finish it for you with industry best-guess defaults? "
            "Reply YES and I'll handle it. Or open: {link}"
        ),
    },
]


def parse_handoff(handoff_path: Path) -> dict:
    """
    Parse interview-handoff.md to extract: last_activity, progress_percent,
    nudges_sent, last_question, owner_name, complete.

    Format expected (frontmatter or top-of-file):
        last_activity: 2026-05-15T14:23:00Z
        progress_percent: 42
        last_question: "Q-D5: When a customer has an issue..."
        nudges_sent: ["nudge_24h"]
        complete: false
        owner_name: Trevor
    """
    try:
        content = handoff_path.read_text(encoding="utf-8")
    except Exception:
        return {"complete": True}

    meta = {"complete": False, "nudges_sent": [], "owner_name": "there", "progress_percent": 0, "last_question": "(start)"}

    for key in ["last_activity", "progress_percent", "last_question", "complete", "owner_name"]:
        m = re.search(rf"^\s*{key}\s*:\s*(.+)$", content, flags=re.MULTILINE)
        if m:
            v = m.group(1).strip()
            if key == "progress_percent":
                try:
                    meta[key] = int(v)
                except ValueError:
                    meta[key] = 0
            elif key == "complete":
                meta[key] = v.lower() in ("true", "yes", "1", "complete", "done")
            else:
                meta[key] = v.strip('"').strip("'")

    # Parse nudges_sent (JSON array or comma-separated)
    m = re.search(r"^\s*nudges_sent\s*:\s*(.+)$", content, flags=re.MULTILINE)
    if m:
        raw = m.group(1).strip()
        try:
            meta["nudges_sent"] = json.loads(raw)
        except Exception:
            meta["nudges_sent"] = [s.strip().strip('"').strip("'") for s in raw.strip("[]").split(",") if s.strip()]

    # last_activity → datetime
    m = re.search(r"^\s*last_activity\s*:\s*(.+)$", content, flags=re.MULTILINE)
    if m:
        try:
            meta["last_activity"] = datetime.fromisoformat(m.group(1).strip().rstrip("Z"))
        except Exception:
            meta["last_activity"] = None
    else:
        meta["last_activity"] = None

    return meta


def record_nudge_sent(handoff_path: Path, nudge_key: str):
    """Append nudge to nudges_sent in the handoff file."""
    content = handoff_path.read_text(encoding="utf-8")
    if "nudges_sent:" in content:
        # Update existing line
        def repl(m):
            raw = m.group(1).strip()
            try:
                lst = json.loads(raw)
            except Exception:
                lst = [s.strip().strip('"').strip("'") for s in raw.strip("[]").split(",") if s.strip()]
            if nudge_key not in lst:
                lst.append(nudge_key)
            return f"nudges_sent: {json.dumps(lst)}"
        content = re.sub(r"^(nudges_sent:\s*)(.+)$", lambda m: f"nudges_sent: {json.dumps([nudge_key])}", content, count=1, flags=re.MULTILINE)
    else:
        content += f"\nnudges_sent: {json.dumps([nudge_key])}\n"
    handoff_path.write_text(content, encoding="utf-8")


def send_telegram_nudge(meta: dict, cfg: dict, company_slug: str, dry_run: bool = False):
    """
    Send Telegram nudge using TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env vars.
    Falls back to printing if not configured or if --dry-run.
    """
    link = f"https://t.me/your-openclaw-bot?start=resume_{company_slug}"
    # If a deployed dashboard URL is configured, use that
    dashboard_url = os.environ.get("OPENCLAW_DASHBOARD_URL")
    if dashboard_url:
        link = f"{dashboard_url.rstrip('/')}/onboarding/resume/{company_slug}"

    message = cfg["message_template"].format(
        name=meta.get("owner_name", "there"),
        progress=meta.get("progress_percent", 0),
        last_question=meta.get("last_question", "(beginning)"),
        link=link,
    )

    if dry_run:
        print(f"  [DRY-RUN] Would send Telegram nudge ({cfg['key']}): {message}")
        return True

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print(f"  [SKIP] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set. Would have sent: {message}")
        return False

    import urllib.request
    import urllib.parse
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    try:
        with urllib.request.urlopen(url, data=data, timeout=10) as resp:
            resp.read()
        print(f"  Sent Telegram nudge ({cfg['key']}) to chat_id={chat_id}")
        return True
    except Exception as e:
        print(f"  Telegram send failed ({cfg['key']}): {e}")
        return False


def scan_and_nudge(dry_run: bool = False) -> dict:
    paths = get_openclaw_paths()
    zhc_root = paths["company_root"]
    counts = {"checked": 0, "nudged": 0, "skipped_complete": 0, "skipped_recent": 0}

    if not zhc_root.exists():
        print(f"Zero-human-company root not found: {zhc_root}")
        return counts

    now = datetime.utcnow()
    for company in zhc_root.iterdir():
        if not company.is_dir():
            continue
        handoff = company / "interview-handoff.md"
        if not handoff.exists():
            continue
        counts["checked"] += 1
        meta = parse_handoff(handoff)

        if meta["complete"]:
            counts["skipped_complete"] += 1
            continue
        if not meta.get("last_activity"):
            counts["skipped_recent"] += 1
            continue

        hours_idle = (now - meta["last_activity"]).total_seconds() / 3600
        nudges_sent = meta.get("nudges_sent", [])

        # Find the largest applicable nudge that hasn't been sent
        for cfg in NUDGE_CONFIG:
            if hours_idle >= cfg["hours_idle"] and cfg["key"] not in nudges_sent:
                print(f"  Company {company.name}: idle {hours_idle:.1f}h, sending {cfg['key']}")
                ok = send_telegram_nudge(meta, cfg, company.name, dry_run=dry_run)
                if ok and not dry_run:
                    record_nudge_sent(handoff, cfg["key"])
                counts["nudged"] += 1
                break  # one nudge per scan per company
        else:
            counts["skipped_recent"] += 1

    return counts


def main():
    parser = argparse.ArgumentParser(description="Send Telegram nudges for incomplete workforce interviews")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually send, just report")
    args = parser.parse_args()

    counts = scan_and_nudge(dry_run=args.dry_run)
    print()
    print("=" * 50)
    print(f"Checked:           {counts['checked']} interviews")
    print(f"Nudged:            {counts['nudged']}")
    print(f"Skipped (done):    {counts['skipped_complete']}")
    print(f"Skipped (recent):  {counts['skipped_recent']}")
    print("=" * 50)


if __name__ == "__main__":
    main()
