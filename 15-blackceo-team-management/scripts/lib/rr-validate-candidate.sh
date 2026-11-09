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

# stdout and stderr are kept APART. OpenClaw prints runtime-retry preamble lines
# (`openclaw: Retrying with "<node>" (cached OpenClaw runtime; current Node
# failed runtime admission).`) on stderr whenever a below-floor node is first on
# PATH; folding them into the validation text made a VALID candidate parse as
# "not JSON" and be refused. The verdict is the JSON object `--json` prints.
OUTF="$(mktemp "${TMPDIR:-/tmp}/rr032-validate.XXXXXX")"
ERRF="$(mktemp "${TMPDIR:-/tmp}/rr032-validate.XXXXXX")"
trap 'rm -f "$OUTF" "$ERRF"' EXIT
OPENCLAW_CONFIG_PATH="$CAND" "$OPENCLAW_BIN" config validate --json >"$OUTF" 2>"$ERRF"
RC=$?

python3 - "$RC" "$OUTF" "$ERRF" <<'PYEOF'
import json, re, sys
rc = int(sys.argv[1])
texts = [open(p, errors="replace").read() for p in sys.argv[2:4]]
PREAMBLE = re.compile(r"^openclaw: Retrying with ")


def verdict(text):
    """Last JSON object in text that carries a "valid" key, else None."""
    dec, found, i = json.JSONDecoder(), None, text.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
        except ValueError:
            i = text.find("{", i + 1)
            continue
        if isinstance(obj, dict) and "valid" in obj:
            found = obj
        i = text.find("{", end)
    return found


# stdout first; stderr only if stdout carried no verdict (older CLIs).
parsed = next((v for v in map(verdict, texts) if v is not None), None)
if parsed is None:
    noise = "\n".join(l for t in texts for l in t.splitlines()
                      if l.strip() and not PREAMBLE.match(l))
    print(json.dumps({"rc": rc, "valid": False,
                      "detail": (noise.strip() or "validator produced no JSON")[:400]}))
    sys.exit(0)
issues = parsed.get("issues") or []
detail = "; ".join(str(i.get("message", i) if isinstance(i, dict) else i) for i in issues)[:400]
print(json.dumps({"rc": rc, "valid": bool(parsed.get("valid")) and rc == 0,
                  "detail": detail or ("valid" if parsed.get("valid") else "rejected")}))
PYEOF
exit 0
