#!/usr/bin/env bash
# rr-validate-candidate.sh — validate a CANDIDATE config with the installed OpenClaw.
#
# RR-032 requires the candidate to be validated BEFORE it reaches the live path.
# A structural JSON check cannot see a schema violation — `Unrecognized key:
# "telegram"` is perfectly valid JSON — so the real validator must run against
# the candidate, and it must run with OPENCLAW_CONFIG_PATH pointed at the
# CANDIDATE rather than at the live file.
#
# Contract: rr-validate-candidate.sh <candidate>
#   prints {"rc":N,"valid":bool,"detail":"..."} on stdout and always exits 0,
#   because the caller (rr-config-transaction.py) reads the JSON to decide.
#   Exit 0 with valid:false is a REJECTION, not a driver failure.
#
# Fail-closed: no openclaw on PATH => valid:false. An unvalidated candidate is
# never promoted on the strength of a structural check alone.

set -uo pipefail

CAND="${1:?usage: rr-validate-candidate.sh <candidate>}"
[ -f "$CAND" ] || { printf '{"rc":2,"valid":false,"detail":"candidate missing: %s"}\n' "$CAND"; exit 0; }

OPENCLAW_BIN="${OPENCLAW_BIN:-$(command -v openclaw || true)}"
if [ -z "$OPENCLAW_BIN" ]; then
  printf '{"rc":127,"valid":false,"detail":"openclaw not on PATH; refusing to promote an unvalidated candidate"}\n'
  exit 0
fi

OUT="$(OPENCLAW_CONFIG_PATH="$CAND" "$OPENCLAW_BIN" config validate --json 2>&1)"
RC=$?

python3 - "$RC" "$OUT" <<'PYEOF'
import json, sys
rc = int(sys.argv[1])
raw = sys.argv[2]
try:
    parsed = json.loads(raw)
except ValueError:
    print(json.dumps({"rc": rc, "valid": False,
                      "detail": (raw.strip() or "validator produced no JSON")[:400]}))
    sys.exit(0)
issues = parsed.get("issues") or []
detail = "; ".join(str(i.get("message", i) if isinstance(i, dict) else i) for i in issues)[:400]
print(json.dumps({"rc": rc, "valid": bool(parsed.get("valid")) and rc == 0,
                  "detail": detail or ("valid" if parsed.get("valid") else "rejected")}))
PYEOF
exit 0
