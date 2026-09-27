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
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).parent))
from detect_platform import get_openclaw_paths


# OPERATOR chat IDs — MUST match install.sh OPERATOR_CHAT_IDS exactly.
# (v12.3.8/fix/v12.3.8-cron-resolver-parity)
# These IDs must NEVER receive a client-owner nudge. The env fallback
# TELEGRAM_CHAT_ID can carry an operator ID (e.g. when the SSH session that
# runs the nudge cron inherits TELEGRAM_CHAT_ID=5252140759 from the operator's
# shell). A corrupted build-state can also carry an operator ID in owner_chat.
# Any such value is rejected below — skip-and-warn instead of nudging operator.
OPERATOR_CHAT_IDS = {"5252140759", "6663821679", "6771245262"}


NUDGE_CONFIG_DEFAULT = [
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

# ── AI WORKFORCE STANDARD-FIRST (2026-08-04): review-prebuilt-company copy ──────
# When WORKFORCE_NUDGE_COPY=review-prebuilt-company (set by interview-nudge-cron.sh
# for standard-first boxes whose prebuild is done), these templates replace the
# default "finish your interview" copy. The owner already has a pre-built company
# — they are reviewing it, not answering setup questions from scratch.
NUDGE_CONFIG_REVIEW = [
    {
        "key": "nudge_24h",
        "hours_idle": 24,
        "message_template": (
            "Hey {name} 👋 — your AI workforce has been pre-built and is ready for review. "
            "You're {progress}% through the review. Want to pick back up?\n\n"
            "Open your company here: {link}\n\n"
            "Everything is saved and ready when you are."
        ),
    },
    {
        "key": "nudge_72h",
        "hours_idle": 72,
        "message_template": (
            "Hey {name} — still want to review your pre-built AI workforce? "
            "You stopped at: {last_question}\n\n"
            "Resume your review here: {link}"
        ),
    },
    {
        "key": "nudge_168h",
        "hours_idle": 168,
        "message_template": (
            "Hey {name} — last check-in on your AI workforce review. "
            "Your pre-built company is saved and I'm ready to pick up right where you left off. "
            "When you're ready to continue, open it here: {link}\n\n"
            "Just message me and we'll finish the review together."
        ),
    },
]

# ── Select active nudge config based on WORKFORCE_NUDGE_COPY env var ────────────
_WNF_NUDGE_COPY = os.environ.get("WORKFORCE_NUDGE_COPY", "default")
if _WNF_NUDGE_COPY == "review-prebuilt-company":
    NUDGE_CONFIG = NUDGE_CONFIG_REVIEW
else:
    NUDGE_CONFIG = NUDGE_CONFIG_DEFAULT


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


# ── Interview-link resolver (ILG-009) ──────────────────────────────────────────
# Nudge links must open the client's REAL interview, not a guess. The ONLY
# sources a nudge may use are the configured public origin the verified
# invitation path (shared-utils/interview_invitation.py resolve) already
# accepts: the verified commandCenterPublicOrigin record, MC_TENANT_PUBLIC_URL,
# commandCenterUrl, or OPENCLAW_DASHBOARD_URL — and all four must agree when
# more than one is present. Anything else (no source at all, conflicting
# sources, a non-HTTPS value, a loopback/IP-literal host) is a skip-with-
# reason, never a fabricated link. The placeholder t.me bot link that used to
# live here pointed nowhere; INSTRUCTIONS.md:1105 separately forbids
# constructing resume-slug links, so the dashboard-URL branch
# below resolves to the stable /interview page, the same page the verified
# invitation bookmarks after sign-in.
def resolve_interview_link(state: dict, env=None):
    """
    Returns (link, reason). link is the stable /interview URL when the box's
    configured public origin is known and unambiguous; otherwise link is None
    and reason names what was checked (for skip-with-reason logging).
    Never raises on bad input — every refusal returns (None, reason).
    """
    env = env if env is not None else os.environ
    if not isinstance(state, dict):
        return None, "build state is not an object"

    def _clean(value):
        return value.strip() if isinstance(value, str) and value.strip() else None

    candidates = []
    record = state.get("commandCenterPublicOrigin")
    if isinstance(record, dict):
        if record.get("verified") is True:
            origin = _clean(record.get("origin"))
            if origin:
                candidates.append(("commandCenterPublicOrigin", origin))
        else:
            return None, "canonical public origin unverified"
    for key in ("MC_TENANT_PUBLIC_URL", "OPENCLAW_DASHBOARD_URL"):
        value = _clean(env.get(key, ""))
        if value:
            candidates.append((key, value))
    url_value = _clean(state.get("commandCenterUrl"))
    if url_value:
        candidates.append(("commandCenterUrl", url_value))

    if not candidates:
        return None, (
            "no configured public origin "
            "(commandCenterPublicOrigin/MC_TENANT_PUBLIC_URL/"
            "commandCenterUrl/OPENCLAW_DASHBOARD_URL all absent)"
        )

    origins = []
    for source, raw in candidates:
        try:
            parts = urlsplit(raw)
        except Exception:
            return None, f"{source} is not a parseable URL"
        if parts.scheme != "https":
            return None, f"{source} is not a public HTTPS origin"
        host = (parts.hostname or "").lower()
        if not host or host == "localhost" or host.endswith((".localhost", ".local")) or "." not in host:
            return None, f"{source} is not a public hostname"
        try:
            import ipaddress as _ipaddress

            _ipaddress.ip_address(host)
            return None, f"{source} is an IP literal, not a hostname"
        except ValueError:
            pass
        origins.append("https://" + parts.netloc.lower().rstrip("/"))

    if len(set(origins)) != 1:
        return None, "public origin configuration conflict"
    return origins[0].rstrip("/") + "/interview", ""


def _gateway_ack(payload, target):
    """Accepted-delivery check for the gateway's --json receipt.

    Same contract as shared-utils/interview_invitation.py acknowledgement():
    a parsed JSON payload (or its payload/result wrapper) with ok, a real
    messageId, the same recipient, the telegram channel, and no
    suppressed/failed/partial/pending status. Reuses that implementation when
    importable; the inline fallback below mirrors it field-for-field so a box
    whose skills tree predates the helper still validates receipts instead of
    crashing or blindly trusting rc==0.
    """
    try:
        from interview_invitation import acknowledgement as _ack

        return _ack(payload, target)
    except Exception:
        pass
    if not isinstance(payload, dict) or payload.get("ok") is False or payload.get("dryRun") is True:
        return None
    data = payload.get("payload", payload.get("result", payload))
    if not isinstance(data, dict) or data.get("ok") is False or data.get("dryRun") is True:
        return None
    if any(item.get("status") in ("suppressed", "failed", "partial", "pending") for item in (payload, data)):
        return None
    message_id = data.get("messageId", data.get("message_id"))
    recipient = data.get("chatId", data.get("chat_id", data.get("to", data.get("target"))))
    channel = data.get("channel", payload.get("channel", "telegram"))
    if isinstance(message_id, bool) or not isinstance(message_id, (str, int)) or not str(message_id).strip():
        return None
    if str(recipient) != target or channel != "telegram":
        return None
    return {"messageId": str(message_id), "channel": "telegram"}


def send_telegram_nudge(meta: dict, cfg: dict, company_slug: str, dry_run: bool = False,
                         _state=None):
    """
    Send Telegram nudge via the OpenClaw gateway ONLY (openclaw message send).

    BINDING RULE: All Telegram sends go through `openclaw message send`.
    Direct HTTP to the Telegram Bot API is FORBIDDEN (see memory rule:
    "Never bypass OpenClaw's gateway for Telegram").

    If the openclaw CLI is not on PATH, log and skip — do NOT fall back
    to direct HTTP.

    Target resolution priority:
      1. meta["owner_chat"] — from .workforce-build-state.json ownerChat
      2. meta["chat_id"]    — legacy handoff frontmatter
      3. TELEGRAM_CHAT_ID env var — last resort
    """
    import subprocess as _sp  # local to keep module-level imports clean

    # Real interview link from the box's configured public origin — or no
    # link at all. A nudge must never carry a guessed/placeholder URL.
    link_state = _state if isinstance(_state, dict) else {}
    link, link_reason = resolve_interview_link(link_state)
    if link is None:
        print(
            f"  [SKIP] No interview link for {company_slug} ({cfg['key']}): "
            f"{link_reason}."
        )
        # Dry-run callers only render the message; a missing link is still a
        # skip, but report it without requiring a chat target or gateway.
        return False

    message = cfg["message_template"].format(
        name=meta.get("owner_name", "there"),
        progress=meta.get("progress_percent", 0),
        last_question=meta.get("last_question", "(beginning)"),
        link=link,
    )

    if dry_run:
        print(f"  [DRY-RUN] Would send Telegram nudge ({cfg['key']}): {message}")
        return True

    # Resolve target chat ID (state-driven primary).
    # OPERATOR-REJECTION GUARD (v12.3.8/fix/v12.3.8-cron-resolver-parity):
    # reject any value that matches a known operator chat ID regardless of
    # which source it came from (owner_chat, chat_id, or TELEGRAM_CHAT_ID env).
    # A corrupted build-state or an inherited operator env var must never cause
    # nudges to land in the operator's chat instead of the client owner's.
    _raw_chat_id = (
        str(meta.get("owner_chat") or "")
        or str(meta.get("chat_id") or "")
        or os.environ.get("TELEGRAM_CHAT_ID", "")
    )
    _normalized = _raw_chat_id.strip().replace("telegram:", "").replace("tg:", "")
    if _normalized in OPERATOR_CHAT_IDS:
        print(
            f"  [SKIP] Resolved chat_id ({_raw_chat_id}) is an OPERATOR id — "
            f"refusing to send nudge ({cfg['key']}) to operator instead of client owner. "
            "Set ownerChat in build state or OPENCLAW_OWNER_CHAT_ID env var."
        )
        return False
    chat_id = _raw_chat_id

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
             "--target", chat_id, "--message", message, "--json"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as e:
        print(f"  openclaw message send error ({cfg['key']}): {e}")
        return False
    if result.returncode != 0:
        print(f"  openclaw message send failed ({cfg['key']}): rc={result.returncode} {result.stderr[:200]}")
        return False
    try:
        receipt = json.loads(result.stdout)
    except ValueError:
        receipt = None
    if _gateway_ack(receipt, chat_id) is None:
        print(
            f"  openclaw message send unverified ({cfg['key']}): "
            "gateway acceptance unverified; reconcile before retry"
        )
        return False
    print(f"  Sent Telegram nudge ({cfg['key']}) to chat_id={chat_id} via openclaw gateway")
    return True


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
    counts = {"checked": 0, "nudged": 0, "skipped_complete": 0, "skipped_recent": 0,
              "skipped_no_link": 0, "send_failed": 0}

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
                # Skip-with-reason BEFORE any chat/gateway work: without a
                # configured public origin there is no truthful link to send.
                link, link_reason = resolve_interview_link(state if isinstance(state, dict) else {})
                if link is None:
                    print(f"  [SKIP] No interview link for {company.name} ({cfg['key']}): {link_reason}.")
                    counts["skipped_no_link"] += 1
                    break  # one nudge slot per scan per company
                ok = send_telegram_nudge(meta, cfg, company.name, dry_run=dry_run, _state=state)
                if ok and not dry_run:
                    # Record in state (primary) and handoff (legacy compat)
                    record_nudge_sent_state(state_path, cfg["key"])
                    if handoff.exists():
                        record_nudge_sent(handoff, cfg["key"])
                    counts["nudged"] += 1
                elif not ok and not dry_run:
                    # Receipt captured, delivery unverified: do NOT record the
                    # nudge as sent (retry stays eligible), but do NOT retry
                    # in this scan either — reconcile before retry.
                    counts["send_failed"] += 1
                else:
                    counts["nudged"] += 1
                break  # one nudge per scan per company
        else:
            # PRD-2.15 (v12.3.12): no applicable nudge AND interview is incomplete.
            # If idle >= 168h, this is the dead-end: all nudges exhausted + owner silent.
            # Mark the interview as STALLED (first-class state, per INSTRUCTIONS.md:796).
            # NO new owner message — watchdog reads this flag for STUCK_MID_INTERVIEW.
            if hours_idle >= 168 and not meta.get("complete"):
                if state_path.exists() and not dry_run:
                    try:
                        import json as _json
                        _s = _json.loads(state_path.read_text())
                        if not _s.get("interviewStalled"):
                            from datetime import timezone as _tz
                            _s["interviewStalled"] = True
                            _s["interviewStalledAt"] = datetime.now(_tz.utc).strftime(
                                "%Y-%m-%dT%H:%M:%SZ"
                            )
                            state_path.write_text(_json.dumps(_s, indent=2))
                            print(
                                f"  Company {company.name}: nudges exhausted at {hours_idle:.1f}h idle — "
                                f"marked interviewStalled=true (watchdog will escalate operator)"
                            )
                    except Exception as e:
                        print(f"  WARN: could not write interviewStalled for {company.name}: {e}")
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
    print(f"Skipped (no link): {counts.get('skipped_no_link', 0)}")
    print(f"Send failed:       {counts.get('send_failed', 0)}")
    print("=" * 50)


if __name__ == "__main__":
    main()
