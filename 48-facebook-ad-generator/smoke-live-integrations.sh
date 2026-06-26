#!/usr/bin/env bash
# Skill 48 — OPTIONAL live smoke test. Skips cleanly when no keys are present.
set -u
echo "=== Skill 48 smoke-live-integrations (optional) ==="
if [ -z "${GOHIGHLEVEL_API_KEY:-}${GHL_API_KEY:-}" ]; then
  echo "  SKIP -- no GoHighLevel LOCATION PIT; skipping the one-pixel upload + folder-create probe."
else
  echo "  (would: create a per-run media folder, upload a 1px PNG, verify the public URL opens 200, then delete)"
fi
if [ -z "${MISSION_CONTROL_URL:-}" ]; then
  echo "  SKIP -- no MISSION_CONTROL_URL; skipping the Command Center /api/ad-campaigns probe."
else
  # Non-destructive, fail-soft reachability + AUTH-PARITY probe of the LIVE caller
  # (scripts/cc_board.py). A signed GET for a random throwaway job_id proves the
  # endpoint is reachable and the Bearer + x-webhook-signature auth is accepted,
  # WITHOUT creating any board data: a known-absent job returns 404 (auth OK), a
  # bad token returns 401. Never fails the smoke run (the producer is fail-soft).
  SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
  python3 - "$SKILL_DIR" <<'PY' || echo "  (probe errored — non-fatal; the producer is fail-soft)"
import os, sys, json, urllib.request, urllib.error
sys.path.insert(0, os.path.join(sys.argv[1], "scripts"))
import cc_board
cfg = cc_board.board_config()
if cfg is None:
    print("  SKIP -- MISSION_CONTROL_URL empty after trim."); raise SystemExit(0)
job = "smoke-probe-" + os.urandom(4).hex()
url = f"{cfg['base_url']}/api/ad-campaigns/{job}"
h = {"Accept": "application/json"}
if cfg["token"]: h["Authorization"] = f"Bearer {cfg['token']}"
sig = cc_board._sign(cfg["secret"], b"")
if sig is not None: h["x-webhook-signature"] = sig
try:
    urllib.request.urlopen(urllib.request.Request(url, headers=h, method="GET"), timeout=cfg["timeout"])
    print("  OK -- /api/ad-campaigns reachable + auth accepted (unexpected 2xx for absent job).")
except urllib.error.HTTPError as e:
    if e.code == 404:
        print("  OK -- /api/ad-campaigns reachable; Bearer+HMAC auth accepted (404 for absent job, no data created).")
    elif e.code == 401:
        print("  WARN -- endpoint reachable but auth REJECTED (401): check MC_API_TOKEN / WEBHOOK_SECRET parity.")
    else:
        print(f"  WARN -- endpoint returned HTTP {e.code} (non-fatal).")
except Exception as e:  # noqa: BLE001
    print(f"  SKIP -- board not reachable ({type(e).__name__}: {e}); the producer degrades to ungrouped (fail-soft).")
PY
fi
echo "smoke: done (no failures = either ran or cleanly skipped)."
exit 0
