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

FIX 64 (one notification transport, W14a-B3 implementation): subsystem alerts
used to pass the SUBSYSTEM NAME ("watchdog", "supervisor", "capacity",
"credit") as the chat_id -- a name no gateway target can resolve, so the
stall/capacity/supervisor alert could never land anywhere. Resolution happens
at BOTH boundaries, single-sourced:
  - report.py dispatch3 (the choke point inside the engine) resolves a known
    subsystem LABEL to OWNER_CHAT_ID before the payload ever reaches a
    transport, via report.resolve_subsystem_chat();
  - THIS script (the transport itself) re-checks independently, because
    dispatch3 keeps the label verbatim when OWNER_CHAT_ID is unset (never a
    fabricated id) and any OTHER caller (a stub in a test, the retired
    tools/presentation-notify.sh, a hand-run pipe) may bypass dispatch3
    entirely. The rule implemented here:
      * a chat_id that is a NUMERIC Telegram chat id (optionally signed, and
       /or a -100... supergroup id) is a real target -- sent as-is;
      * anything else is treated as a subsystem NAME and the numeric operator
        chat id is resolved from the tiered env keys
        (PRESENTATION_OWNER_CHAT_ID -> OPENCLAW_OWNER_CHAT_ID -> OWNER_CHAT_ID
        -> OWNER_TELEGRAM_CHAT_ID -> TELEGRAM_CHAT_ID, then the
        OPERATOR_ESCALATION/HELP/TELEGRAM keys operator_requester.py shares,
        then the openclaw.json env.vars fallback those keys expose);
      * the subsystem name is preserved in the message prefix so the alert
        still says where it came from;
      * no numeric id resolvable anywhere -> exit 4 (undeliverable, queued
        for --sweep-undeliverable), never a fabricated id, never a silent
        drop, and never the subsystem name handed to the gateway as a target.

FIX 23 (presentation rev2 waves): the transport is gateway-only. Rollback:
set PRESENTATION_NOTIFY_DIRECT_TELEGRAM=1 to restore the legacy direct-Bot-API
path (reads OPERATOR_TELEGRAM_BOT_TOKEN again); that flag is the only supported
pre-fix coexistence mode, and it stays opt-in -- the gateway is the default.

Exit codes (stable dispatch3 contract, see tests/test_report.py):
  0  -- sent via the gateway (or dry-run dispatch succeeded)
  2  -- transport misconfiguration (gateway CLI absent AND no legacy flag)
  3  -- stdin is not valid JSON
  4  -- no chat_id in payload and no OWNER_CHAT_ID fallback, OR a subsystem
        name chat_id that could not be resolved to a numeric target
  5  -- gateway send rejected/failed (non-zero gateway exit, timeout, OSError)
"""
import os, re, sys, json, shutil, subprocess

DEFAULT_NOTIFY_TIMEOUT_S = 30  # matches CC src/lib/notify.ts OWNER_SEND_TIMEOUT_MS

# The gateway transport contract (openclaw 2026.x CLI flags). --target and
# --message are the real flags; the old --to/--text do not exist (commander
# rejects them) -- same finding notify.ts documents.
_GATEWAY_CHANNEL_DEFAULT = "telegram"

# FIX 64: a numeric Telegram chat id is a deliverable target -- the gateway
# accepts signed integers (negative for groups/supergroups, including the
# -100... supergroup prefix) and bare positive ids for users. Anything that
# is not numeric is a LABEL (a subsystem name like "watchdog"), never a
# target, and must be resolved before a send is attempted.
_NUMERIC_CHAT_ID_RE = re.compile(r"^-?\d+$")

# FIX 64: the operator chat-id tier, byte-for-byte the order
# run_signature_deck.py::_resolve_owner_route already reads -- one vocabulary,
# not a second divergent list.
OWNER_CHAT_ID_ENV_KEYS = (
    "PRESENTATION_OWNER_CHAT_ID",
    "OPENCLAW_OWNER_CHAT_ID",
    "OWNER_CHAT_ID",
    "OWNER_TELEGRAM_CHAT_ID",
    "TELEGRAM_CHAT_ID",
    # The OPERATOR_* keys operator_requester.py sanctions (FIX F19's
    # last-resort operator fallback) -- same tier, appended behind the
    # presentation-specific keys so an explicit owner route always wins.
    "OPERATOR_ESCALATION_CHAT_ID",
    "OPERATOR_HELP_CHAT_ID",
    "OPERATOR_TELEGRAM_CHAT_ID",
)

def _first_nonempty_env(keys, env):
    for key in keys:
        val = str(env.get(key) or "").strip()
        if val:
            return val
    return ""

def _openclaw_config_path():
    """Path of the openclaw.json env store (operator_requester.py's constant
    pattern, re-derived here so the transport has no package import
    dependency -- this script must run standalone under a bare python3)."""
    return os.path.join(os.path.expanduser("~"), ".openclaw", "openclaw.json")

def _first_nonempty_config_vars(keys, config_path):
    """Read env.vars.<key> (in order) from an openclaw.json-shaped file.
    Tolerates absence/corruption -- returns "" rather than raising, matching
    operator_requester.py's own precedent."""
    if not config_path or not os.path.isfile(config_path):
        return ""
    try:
        with open(config_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return ""
    if not isinstance(cfg, dict):
        return ""
    env_vars = (cfg.get("env") or {}).get("vars")
    if not isinstance(env_vars, dict):
        return ""
    return _first_nonempty_env(keys, env_vars)

def is_numeric_chat_id(chat_id) -> bool:
    """FIX 64: True only for a numeric Telegram chat id (optionally signed).
    A subsystem label ("watchdog"/"supervisor"/"capacity"/"credit") is never
    numeric, so it never passes this check."""
    return bool(_NUMERIC_CHAT_ID_RE.match(str(chat_id or "").strip()))

def resolve_numeric_operator_chat_id(env=None, config_path=None) -> str:
    """FIX 64: resolve the numeric operator chat id from the tiered env keys,
    falling back to ~/.openclaw/openclaw.json's env.vars (operator_requester
    precedent). Returns "" -- never a fabricated id -- when nothing resolves.
    `env` / `config_path` are injectable ONLY for tests (hermetic; production
    reads os.environ and the real ~/.openclaw/openclaw.json)."""
    src_env = os.environ if env is None else env
    chat_id = _first_nonempty_env(OWNER_CHAT_ID_ENV_KEYS, src_env)
    if not chat_id:
        chat_id = _first_nonempty_config_vars(
            OWNER_CHAT_ID_ENV_KEYS,
            config_path if config_path is not None else _openclaw_config_path())
    return chat_id

def resolve_chat_id_for_transport(chat_id, env=None, config_path=None) -> tuple:
    """FIX 64: map the payload chat_id to a deliverable (numeric) target.

    Returns (target_chat_id, prefix). prefix is "" for an already-numeric id
    and "[watchdog] " (the label) for a resolved subsystem name, so the alert
    text still says where it came from. A label that cannot be resolved to a
    numeric id returns ("", "") -- the caller exits 4 (undeliverable, queued
    for --sweep-undeliverable) instead of handing the gateway a target it can
    never deliver to. `env` / `config_path` are injectable ONLY for tests."""
    raw = str(chat_id or "").strip()
    if is_numeric_chat_id(raw):
        return (raw, "")
    # Non-numeric: a subsystem label. Resolve the operator target.
    operator = resolve_numeric_operator_chat_id(env, config_path)
    if operator and is_numeric_chat_id(operator):
        return (operator, f"[{raw}] ")
    return ("", "")


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
    # FIX 64: resolve a non-numeric chat_id (a subsystem label such as
    # "watchdog"/"supervisor"/"capacity") to the numeric operator chat id at
    # this transport boundary, independent of report.py's dispatch3 (which
    # keeps the label verbatim when OWNER_CHAT_ID is unset, and which any
    # non-engine caller may have bypassed). A label with no resolvable
    # numeric operator id is UNDELIVERABLE (exit 4, queued for
    # --sweep-undeliverable) -- never the label handed to the gateway as a
    # target, never a fabricated id, never a silent drop. The label survives
    # in the message prefix.
    target, label_prefix = resolve_chat_id_for_transport(chat_id)
    if not target:
        print(
            "FATAL: chat_id "
            f"{str(chat_id).strip()!r} is not a numeric Telegram chat id and "
            "no numeric operator chat id could be resolved (tiered "
            "PRESENTATION_OWNER_CHAT_ID/OPENCLAW_OWNER_CHAT_ID/OWNER_CHAT_ID/"
            "OWNER_TELEGRAM_CHAT_ID/TELEGRAM_CHAT_ID/OPERATOR_*_CHAT_ID env, "
            "then ~/.openclaw/openclaw.json env.vars) -- undeliverable, "
            "queued for --sweep-undeliverable",
            file=sys.stderr)
        return 4
    chat_id = target
    text = (f"[Presentation Dept] {label_prefix}{str(kind).upper()}: {msg}"
            if msg
            else f"[Presentation Dept] {label_prefix}{str(kind).upper()}")
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
