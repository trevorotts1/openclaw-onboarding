#!/usr/bin/env python3
# _qc_operator_chat.py — resolve the OPERATOR escalation chat id for qc-completeness.
#
# v20.0.9 (SECURITY/PRIVACY): qc-completeness.sh NO LONGER resolves the client owner
# chat (channels.telegram.allowFrom[0]) for its != PASS alert — that path leaked
# internal per-department QC gap tables to real clients. The alert now routes to the
# OPERATOR escalation chat ONLY. This helper resolves the operator chat id from, in
# order:
#   1) the process environment (a fleet roll / operator may export it), then
#   2) openclaw.json env.vars (argv[1] = openclaw.json path),
# checking the canonical OPERATOR_ESCALATION_CHAT_ID first, then the known aliases
# OPERATOR_HELP_CHAT_ID / OPERATOR_TELEGRAM_CHAT_ID (mirrors update-skills.sh's
# send_telegram_progress and migrate-existing-workforce.sh's operator resolver).
#
# Prints the resolved operator chat id, or NOTHING (empty) when none is configured.
# On empty output the caller LOG-ONLYs — it NEVER falls back to the client chat.
#
# Externalized (like _qc_owner_chat.py) to avoid the stock-macOS bash 3.2.57
# python-in-$() heredoc parse hazard.
import json
import os
import sys

KEYS = (
    "OPERATOR_ESCALATION_CHAT_ID",
    "OPERATOR_HELP_CHAT_ID",
    "OPERATOR_TELEGRAM_CHAT_ID",
)


def _first_nonempty(getter):
    for key in KEYS:
        val = str(getter(key) or "").strip()
        if val:
            return val
    return ""


# 1) process environment (roll / operator export)
resolved = _first_nonempty(lambda k: os.environ.get(k, ""))

# 2) openclaw.json env.vars (never channels.telegram.allowFrom)
if not resolved:
    try:
        cfg = json.load(open(sys.argv[1]))
        env_vars = (cfg.get("env", {}) or {}).get("vars", {}) or {}
        resolved = _first_nonempty(lambda k: env_vars.get(k, ""))
    except Exception:
        resolved = ""

print(resolved)
