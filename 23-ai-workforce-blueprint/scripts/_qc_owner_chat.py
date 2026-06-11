#!/usr/bin/env python3
# _qc_owner_chat.py — extracted from qc-completeness.sh OWNER_CHAT heredoc.
#
# Externalized v11.18.4 for stock-macOS bash 3.2.57 compatibility (python-in-$()
# parse hazard). Logic byte-equivalent to the former inline heredoc; the
# openclaw.json path is now argv[1] instead of the shell-interpolated $OCJSON.
# Prints the resolved Telegram owner chat id (first allowFrom / ownerAllowFrom),
# or nothing on any error.
import json
import sys

try:
    cfg = json.load(open(sys.argv[1]))
    allow = cfg.get("channels", {}).get("telegram", {}).get("allowFrom", []) \
        or cfg.get("channels", {}).get("telegram", {}).get("ownerAllowFrom", [])
    if allow:
        print(allow[0])
except Exception:
    pass
