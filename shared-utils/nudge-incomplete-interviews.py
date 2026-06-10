#!/usr/bin/env python3
"""
Scan for incomplete AI Workforce interviews and send Telegram nudges.

Cadence (per PRD v2.1):
- +24h idle  : "You're {progress}% done. Want to keep going?"
- +72h idle  : "Still want to finish? You stopped at {last_question}."
- +168h idle : Resume invitation ONLY — see nudge_168h message_template below.

IMPORTANT — NO FABRICATION POLICY:
This script sends reminders only. It NEVER triggers Option B (Quick Setup),
NEVER runs any autonomous build action, and NEVER writes best-guess defaults
into workforce-interview-answers.md. The only thing that unlocks Option B is
an EXPLICIT, in-conversation owner choice in the CURRENT session with the AI
agent. An unanswered message, a cron tick, or a "Reply YES" response captured
outside a live session does NOT constitute consent. Any code path that would
auto-trigger Option B based on a nudge response is a fabrication bug and must
not be implemented.

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
            "Your answers are saved and I'm ready to pick up right where you left off. "
            "When you're ready to continue, open your setup here: {link}\n\n"
            "Just message me and we'll finish it together."
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
    Send Telegram nudge via the OpenClaw gateway ONLY (openclaw message send).

    BINDING RULE: All Telegram sends go through `openclaw message send`.
    NEVER use direct HTTP to api.telegram.org (see memory rule:
    "Never bypass OpenClaw's gateway for Telegram").

    If the openclaw CLI is not on PATH, log and skip — do NOT fall back
    to direct HTTP.

    Target resolution priority:
      1. meta["owner_chat"] — from .workforce-build-state.json ownerChat
      2. meta["chat_id"]    — legacy handoff frontmatter
      3. TELEGRAM_CHAT_ID env var — last resort
    """
    import subprocess as _sp  # local to keep module-level imports clean

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

    # Resolve target chat ID (state-driven primary)
    chat_id = (
        str(meta.get("owner_chat") or "")
        or str(meta.get("chat_id") or "")
        or os.environ.get("TELEGRAM_CHAT_ID", "")
    )

    if not chat_id:
        print(
            f"  [SKIP] No chat_id available for Telegram nudge ({cfg['key']}). "
            "Set ownerChat in build state or TELEGRAM_CHAT_ID env var."
        )
        return False

    # Gateway send via openclaw CLI only
    import shutil as _shutil
    if not _shutil.which("openclaw"):
        print(
            f"  [SKIP] openclaw CLI not found on PATH — cannot send nudge ({cfg['key']}) "
            "via gateway. No direct-HTTP fallback (binding rule)."
        )
        return False

    try:
        result = _sp.run(
            ["openclaw", "message", "send", "--channel", "telegram",
             "--target", chat_id, "--message", message],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print(f"  Sent Telegram nudge ({cfg['key']}) to chat_id={chat_id} via openclaw gateway")
            return True
        else:
            print(f"  openclaw message send failed ({cfg['key']}): rc={result.returncode} {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  openclaw message send error ({cfg['key']}): {e}")
        return False


def read_build_state(state_path: Path) -> dict:
    """
    Read .workforce-build-state.json. Returns {} if not found or invalid.
    PRD-2.15: build state is the PRIMARY source of interview progress data.
    """
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def merge_meta_from_state(meta: dict, state: dict) -> dict:
    """
    Merge build-state fields into meta dict, preferring state values as primary.
    Falls back to handoff frontmatter values when state fields are absent.
    PRD-2.15: state is primary; handoff is fallback only.
    """
    merged = dict(meta)

    # interviewComplete from state takes priority
    if state.get("interviewComplete") is not None:
        merged["complete"] = bool(state["interviewComplete"])

    # lastQuestionAt from state interviewProgress
    progress = state.get("interviewProgress") or {}
    if progress.get("lastQuestionAt"):
        try:
            ts = progress["lastQuestionAt"].rstrip("Z")
            merged["last_activity"] = datetime.fromisoformat(ts)
        except Exception:
            pass

    # ownerName, ownerChat from state
    if state.get("ownerName"):
        merged["owner_name"] = state["ownerName"]
    if state.get("ownerChat"):
        merged["owner_chat"] = state["ownerChat"]

    # lastQuestionNumber → last_question fallback
    if progress.get("lastQuestionNumber") and not merged.get("last_question"):
        merged["last_question"] = f"Question #{progress['lastQuestionNumber']}"

    # nudges_sent from state (canonical) or handoff (legacy)
    if "nudges_sent" in state:
        merged["nudges_sent"] = state.get("nudges_sent", [])

    # progress_percent estimate from question count
    if not merged.get("progress_percent") and progress.get("lastQuestionNumber"):
        q = progress["lastQuestionNumber"]
        merged["progress_percent"] = min(100, int((q / 30) * 100))

    return merged


def record_nudge_sent_state(state_path: Path, nudge_key: str) -> None:
    """
    Record a sent nudge in the build state file (canonical dedup store).
    Also records in the handoff file if it exists (legacy compat).
    """
    if not state_path.exists():
        return
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return

    sent = list(state.get("nudges_sent") or [])
    if nudge_key not in sent:
        sent.append(nudge_key)
        state["nudges_sent"] = sent
        tmp = Path(str(state_path) + f".tmp.{os.getpid()}")
        try:
            tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
            tmp.replace(state_path)
        except Exception:
            tmp.unlink(missing_ok=True)


def scan_and_nudge(dry_run: bool = False) -> dict:
    paths = get_openclaw_paths()
    zhc_root = paths["company_root"]
    # PRD-2.15: also check the canonical workspace build state path
    workspace = paths.get("workspace") or paths.get("root", Path("/tmp")) / "workspace"
    counts = {"checked": 0, "nudged": 0, "skipped_complete": 0, "skipped_recent": 0}

    if not zhc_root.exists():
        print(f"Zero-human-company root not found: {zhc_root}")
        return counts

    now = datetime.utcnow()
    for company in zhc_root.iterdir():
        if not company.is_dir():
            continue

        # PRD-2.15: PRIMARY source is .workforce-build-state.json
        state_path = workspace / ".workforce-build-state.json"
        state = read_build_state(state_path) if state_path.exists() else {}

        # FALLBACK: handoff frontmatter (only if state is absent)
        handoff = company / "interview-handoff.md"
        meta: dict = {}
        if handoff.exists():
            meta = parse_handoff(handoff)
        elif not state:
            continue  # neither source exists

        counts["checked"] += 1

        # Merge: state is primary, handoff is fallback
        if state:
            meta = merge_meta_from_state(meta, state)

        if meta.get("complete"):
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
                    # Record in state (primary) and handoff (legacy compat)
                    record_nudge_sent_state(state_path, cfg["key"])
                    if handoff.exists():
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
