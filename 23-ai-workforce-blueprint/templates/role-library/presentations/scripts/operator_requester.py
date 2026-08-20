#!/usr/bin/env python3
"""operator_requester.py -- the sanctioned OPERATOR chat-id fallback for a
Presentations deck that has no chat-surface requester (FIX F19).

THE GAP THIS CLOSES
--------------------
Both real intake paths -- deck-intake-driver.py's --complete/--signature
finalizers and the interview-app bridge's cmd_ingest() -- already knew how to
carry a requester FORWARD once one existed on the chat surface (env vars a
dispatcher exported: PRESENTATION_REQUESTER_CHAT_ID / ROUTE_PRES_REQUESTER_
CHAT_ID / MC_ROUTE_REQUESTER_CHAT_ID -- see cc_board.py's _REQUESTER_ENV_KEYS,
mirrored byte-for-byte in deck-intake-driver.py). Neither had anywhere to turn
when NONE of those were set: a genuinely operator-initiated CLI run, or an
interview-app session nobody dispatched from a client chat. That case resolved
to {} forever, so presentation_job.py --new's own F1 hard-fail ("no
requester.chat_id in intake") caught EVERY such run and the department could
not take an unattended order -- a human had to hand-stamp working/copy/
intake.json's requester_chat_id after the fact (verified: pres-wave-e-zhc-
1787175621 is the only run on this box carrying one, and only for that
reason).

THE FIX
-------
A LAST-RESORT operator fallback -- never a client identity, never invented --
read BY NAME from the sanctioned OpenClaw config store, mirroring the exact
precedent already used department-wide for operator escalation contacts:
  - 23-ai-workforce-blueprint/scripts/_qc_operator_chat.py's KEYS tuple
    (OPERATOR_ESCALATION_CHAT_ID -> OPERATOR_HELP_CHAT_ID ->
    OPERATOR_TELEGRAM_CHAT_ID), reused here byte-for-byte;
  - shared-utils/operator-chat-id.sh's tiered env-then-config precedence;
  - presentation_job/capacity.py's OPENCLAW_CONFIG = ~/.openclaw/openclaw.json
    constant/pattern.

Order: process env first (a fleet roll / operator export), then
~/.openclaw/openclaw.json's env.vars, same tiered keys, by NAME -- nothing
here is ever hardcoded. Returns ("", "") -- never a fabricated id -- when
nothing is configured; a run that stays at ("", "") is EXPECTED to keep
failing resolve_intake.py's MissingRequester gate (fix F04). This module only
ever ADDS a legitimate source; it never bypasses that gate, and it never
prints the resolved value -- callers persist it into the run's own
working/copy/intake.json (the whole point), but must not echo it to a
log/console.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Tuple

# Mirrors 23-ai-workforce-blueprint/scripts/_qc_operator_chat.py's KEYS tuple
# byte-for-byte -- one operator-chat-id vocabulary, read in both places.
OPERATOR_CHAT_ID_ENV_KEYS: Tuple[str, ...] = (
    "OPERATOR_ESCALATION_CHAT_ID",
    "OPERATOR_HELP_CHAT_ID",
    "OPERATOR_TELEGRAM_CHAT_ID",
)

# Mirrors presentation_job/capacity.py's OPENCLAW_CONFIG constant/pattern.
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"


def _first_nonempty_env(keys: Tuple[str, ...], env: dict) -> str:
    for key in keys:
        val = str(env.get(key) or "").strip()
        if val:
            return val
    return ""


def _first_nonempty_config_vars(keys: Tuple[str, ...], config_path: Path) -> str:
    """Read env.vars.<key> (in order) from an openclaw.json-shaped file.
    Tolerates absence/corruption -- returns "" rather than raising, matching
    resolve_intake.py's own _read_json_dict() precedent."""
    if not config_path.is_file():
        return ""
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(cfg, dict):
        return ""
    env_vars = (cfg.get("env") or {}).get("vars")
    if not isinstance(env_vars, dict):
        return ""
    return _first_nonempty_env(keys, env_vars)


def resolve_operator_chat_id(
    config_path: Optional[Path] = None,
    env: Optional[dict] = None,
) -> Tuple[str, str]:
    """Return (chat_id, channel) for the sanctioned OPERATOR fallback, or
    ("", "") when none is configured anywhere.

    `channel` is always "telegram" when a chat_id resolves -- every
    OPERATOR_*_CHAT_ID in this codebase names a Telegram chat (see
    shared-utils/operator-chat-id.sh). Never raises; never fabricates; never
    prints the resolved value itself (that is the caller's job to avoid too).

    `config_path` / `env` are injectable ONLY for tests -- production callers
    call this with no arguments and get the real process env + the real
    ~/.openclaw/openclaw.json.
    """
    src_env = env if env is not None else os.environ
    chat_id = _first_nonempty_env(OPERATOR_CHAT_ID_ENV_KEYS, src_env)
    if not chat_id:
        path = Path(config_path) if config_path else OPENCLAW_CONFIG
        chat_id = _first_nonempty_config_vars(OPERATOR_CHAT_ID_ENV_KEYS, path)
    return (chat_id, "telegram") if chat_id else ("", "")
