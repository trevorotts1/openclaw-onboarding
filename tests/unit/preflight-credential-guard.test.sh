#!/usr/bin/env bash
# ============================================================================
# preflight-credential-guard.test.sh
#
# FAIL-FIRST regression guard for scripts/fleet-roll/preflight-credential-guard.sh
# — the P6-01 fleet-roll credential guard. The ONE property this whole test
# exists for:
#
#     a fleet roll that mutates/wipes a credential store between snapshot and
#     verify MUST be caught (nonzero) — and the guard must NEVER print a secret.
#
# Every test is that property asked a different way.
#
#   T1  TEETH (fail-first)   — the wipe scenario is a REAL regression: a no-op
#                              stub guard (always exit 0) PASSES it. So if the
#                              real guard ever regresses to a no-op, this proves
#                              the scenario would sail through — establishing the
#                              test has teeth before we trust T2's pass.
#   T2  wipe is DETECTED     — the REAL guard, run after a simulated wipe, EXITS
#                              NONZERO. Four wipe shapes: file deleted, file
#                              content changed, env key disappeared, env value
#                              changed. Each must refuse.
#   T3  unchanged PASSES     — snapshot then no change -> verify exits 0.
#   T4  never emits a secret — across snapshot + drift-verify + restore, no
#                              seeded secret VALUE appears on stdout/stderr, and
#                              the snapshot manifest holds hashes only.
#   T5  fail-closed          — missing snapshot dir, corrupt manifest, and an
#                              unreadable store each REFUSE (nonzero).
#   T6  restore              — restore puts a wiped file store back byte-identical
#                              and a subsequent verify passes.
#
# Self-contained: bash + coreutils + a hasher (shasum/sha256sum/python3). No
# gateway, no real credentials, no network. Uses only sandbox HOMEs.
#
# Run:  bash tests/unit/preflight-credential-guard.test.sh
# ============================================================================
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
GUARD="$REPO_ROOT/scripts/fleet-roll/preflight-credential-guard.sh"

PASS=0; FAIL=0
ok()  { printf '  \033[32m✓ PASS\033[0m — %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  \033[31m✗ FAIL\033[0m — %s\n' "$1"; FAIL=$((FAIL+1)); }
hdr() { printf '\n\033[1m%s\033[0m\n' "$1"; }

[ -f "$GUARD" ] || { echo "FATAL: guard not found at $GUARD"; exit 2; }

# Distinctive fake secret VALUES — if any reaches output, T4 fails.
SEC_ENV_FILE_TOKEN="pit-FAKE-GHL-TOKEN-AAAA1111"
SEC_PM2_TOKEN="FAKE-PM2-INJECTED-SECRET-BBBB2222"
SEC_LIVE_GHL="pit-FAKE-LIVE-GHL-CCCC3333"
SEC_LIVE_TG="1234567890:FAKE-LIVE-TG-DDDD4444"

# ---- sandbox builder --------------------------------------------------------
# Creates a fresh sandbox HOME with a secrets/.env, a pm2 dump, an env-keys
# file, and a stores file that points the guard ONLY at the sandbox (no real
# box paths touched). Echoes the sandbox root.
make_sandbox() {
  local sb; sb="$(mktemp -d)"
  mkdir -p "$sb/.openclaw/secrets" "$sb/.pm2"
  cat > "$sb/.openclaw/secrets/.env" <<ENV
GHL_API_KEY=$SEC_ENV_FILE_TOKEN
SOME_OTHER=notasecret
ENV
  cat > "$sb/.pm2/dump.pm2" <<PM2
{"apps":[{"name":"openclaw","env":{"TELEGRAM_BOT_TOKEN":"$SEC_PM2_TOKEN"}}]}
PM2
  # env-keys file: the live-process keys we fingerprint
  cat > "$sb/env-keys.txt" <<KEYS
GHL_API_KEY
TELEGRAM_BOT_TOKEN
KEYS
  # stores file: LABEL<TAB>PATH (tab-separated)
  printf 'secrets-env\t%s\n' "$sb/.openclaw/secrets/.env" >  "$sb/stores.tsv"
  printf 'pm2-dump\t%s\n'    "$sb/.pm2/dump.pm2"          >> "$sb/stores.tsv"
  printf '%s' "$sb"
}

# Run the guard with the sandbox wiring. Args: <mode> <backupdir> <sandbox>
# plus the live-env values exported for the run.
run_guard() {
  local mode="$1" backup="$2" sb="$3"
  PREFLIGHT_HOME="$sb" \
  PREFLIGHT_STORES_FILE="$sb/stores.tsv" \
  PREFLIGHT_ENV_KEYS_FILE="$sb/env-keys.txt" \
  GHL_API_KEY="$SEC_LIVE_GHL" \
  TELEGRAM_BOT_TOKEN="$SEC_LIVE_TG" \
    bash "$GUARD" "$mode" "$backup"
}

# ── T1 — TEETH: the wipe scenario passes a no-op stub (fail-first) ───────────
hdr "T1 — teeth: a no-op stub guard would MISS the wipe (proves scenario is real)"
SB="$(make_sandbox)"; BK="$SB/bk"
run_guard snapshot "$BK" "$SB" >/dev/null 2>&1 || { bad "T1 snapshot setup failed"; }
# simulate a credential wipe (the exact thing the roll must never cause)
rm -f "$SB/.openclaw/secrets/.env"
# a NO-OP stub guard (what a regressed / toothless guard looks like)
STUB="$SB/stub.sh"; printf '#!/usr/bin/env bash\nexit 0\n' > "$STUB"; chmod +x "$STUB"
if bash "$STUB" verify "$BK" >/dev/null 2>&1; then
  ok "no-op stub returns 0 on a wiped store — scenario genuinely needs teeth"
else
  bad "stub did not return 0 — T1 harness is broken"
fi
rm -rf "$SB"

# ── T2 — the REAL guard DETECTS each wipe shape (nonzero) ────────────────────
hdr "T2 — real guard refuses (nonzero) on every wipe shape"

# T2a: file store deleted
SB="$(make_sandbox)"; BK="$SB/bk"
run_guard snapshot "$BK" "$SB" >/dev/null 2>&1
rm -f "$SB/.openclaw/secrets/.env"
if run_guard verify "$BK" "$SB" >/dev/null 2>&1; then
  bad "T2a: guard PASSED after secrets/.env was deleted (no teeth!)"
else
  ok  "T2a: deleted secrets/.env store detected (nonzero)"
fi
rm -rf "$SB"

# T2b: file store content changed
SB="$(make_sandbox)"; BK="$SB/bk"
run_guard snapshot "$BK" "$SB" >/dev/null 2>&1
printf 'GHL_API_KEY=pit-DIFFERENT-TOKEN-9999\n' > "$SB/.openclaw/secrets/.env"
if run_guard verify "$BK" "$SB" >/dev/null 2>&1; then
  bad "T2b: guard PASSED after secrets/.env content changed"
else
  ok  "T2b: changed secrets/.env content detected (nonzero)"
fi
rm -rf "$SB"

# T2c: live env key disappeared (unset between snapshot and verify)
SB="$(make_sandbox)"; BK="$SB/bk"
run_guard snapshot "$BK" "$SB" >/dev/null 2>&1
# verify with TELEGRAM_BOT_TOKEN NOT exported -> it disappeared
if PREFLIGHT_HOME="$SB" PREFLIGHT_STORES_FILE="$SB/stores.tsv" \
   PREFLIGHT_ENV_KEYS_FILE="$SB/env-keys.txt" GHL_API_KEY="$SEC_LIVE_GHL" \
   bash "$GUARD" verify "$BK" >/dev/null 2>&1; then
  bad "T2c: guard PASSED after a live env credential disappeared"
else
  ok  "T2c: disappeared live env credential detected (nonzero)"
fi
rm -rf "$SB"

# T2d: live env value changed
SB="$(make_sandbox)"; BK="$SB/bk"
run_guard snapshot "$BK" "$SB" >/dev/null 2>&1
if PREFLIGHT_HOME="$SB" PREFLIGHT_STORES_FILE="$SB/stores.tsv" \
   PREFLIGHT_ENV_KEYS_FILE="$SB/env-keys.txt" GHL_API_KEY="$SEC_LIVE_GHL" \
   TELEGRAM_BOT_TOKEN="ROTATED-DIFFERENT-VALUE-0000" \
   bash "$GUARD" verify "$BK" >/dev/null 2>&1; then
  bad "T2d: guard PASSED after a live env credential value changed"
else
  ok  "T2d: changed live env credential value detected (nonzero)"
fi
rm -rf "$SB"

# ── T3 — unchanged creds pass ────────────────────────────────────────────────
hdr "T3 — unchanged credential stores VERIFY clean (exit 0)"
SB="$(make_sandbox)"; BK="$SB/bk"
run_guard snapshot "$BK" "$SB" >/dev/null 2>&1
if run_guard verify "$BK" "$SB" >/dev/null 2>&1; then
  ok  "T3: no drift -> verify exits 0"
else
  bad "T3: verify FAILED on unchanged stores (false positive)"
fi
rm -rf "$SB"

# ── T4 — never emits a secret value ──────────────────────────────────────────
hdr "T4 — no seeded secret VALUE ever appears in guard output"
SB="$(make_sandbox)"; BK="$SB/bk"
OUT="$SB/allout.txt"
{
  run_guard snapshot "$BK" "$SB"
  # cause drift so the drift-reporting path also runs
  printf 'GHL_API_KEY=pit-CHANGED-7777\n' > "$SB/.openclaw/secrets/.env"
  run_guard verify "$BK" "$SB"
  run_guard restore "$BK" "$SB"
} > "$OUT" 2>&1 || true
LEAK=0
for secret in "$SEC_ENV_FILE_TOKEN" "$SEC_PM2_TOKEN" "$SEC_LIVE_GHL" "$SEC_LIVE_TG"; do
  if grep -Fq "$secret" "$OUT"; then
    bad "T4: secret VALUE leaked to output: (redacted label match)"
    LEAK=1
  fi
done
[ "$LEAK" -eq 0 ] && ok "T4: no secret value in any guard output stream"
# the snapshot manifest must hold hashes only — never a plaintext value
MLEAK=0
for secret in "$SEC_ENV_FILE_TOKEN" "$SEC_PM2_TOKEN" "$SEC_LIVE_GHL" "$SEC_LIVE_TG"; do
  if grep -Fq "$secret" "$BK/manifest.snapshot" 2>/dev/null; then MLEAK=1; fi
done
[ "$MLEAK" -eq 0 ] && ok "T4: snapshot manifest contains fingerprints only, no plaintext" \
                    || bad "T4: plaintext secret found in manifest.snapshot"
rm -rf "$SB"

# ── T5 — fail-closed on read/parse errors ────────────────────────────────────
hdr "T5 — fail-closed: refuse on missing/corrupt snapshot and unreadable store"
# T5a: verify with no snapshot dir at all
SB="$(make_sandbox)"
if run_guard verify "$SB/nope" "$SB" >/dev/null 2>&1; then
  bad "T5a: verify PASSED with no snapshot dir (should refuse)"
else
  ok  "T5a: missing snapshot dir refused (nonzero)"
fi
# T5b: corrupt manifest
BK="$SB/bk"; run_guard snapshot "$BK" "$SB" >/dev/null 2>&1
printf 'garbage-not-tab-delimited\n' > "$BK/manifest.snapshot"
if run_guard verify "$BK" "$SB" >/dev/null 2>&1; then
  bad "T5b: verify PASSED on a corrupt manifest (should refuse)"
else
  ok  "T5b: corrupt manifest refused (nonzero)"
fi
rm -rf "$SB"
# T5c: an existing-but-unreadable store (skip if running as root, who bypasses perms)
if [ "$(id -u)" != "0" ]; then
  SB="$(make_sandbox)"; BK="$SB/bk"
  chmod 000 "$SB/.openclaw/secrets/.env"
  if run_guard snapshot "$BK" "$SB" >/dev/null 2>&1; then
    bad "T5c: snapshot PASSED with an unreadable store (should refuse)"
  else
    ok  "T5c: unreadable store refused (nonzero)"
  fi
  chmod 600 "$SB/.openclaw/secrets/.env" 2>/dev/null || true
  rm -rf "$SB"
else
  ok  "T5c: skipped (running as root; perm bits don't apply)"
fi

# ── T6 — restore round-trips a wiped store byte-identical ─────────────────────
hdr "T6 — restore recovers a wiped file store byte-identical, then verify passes"
SB="$(make_sandbox)"; BK="$SB/bk"
ORIG_SHA="$( (command -v shasum >/dev/null && shasum -a 256 < "$SB/.openclaw/secrets/.env" || sha256sum < "$SB/.openclaw/secrets/.env") | awk '{print $1}')"
run_guard snapshot "$BK" "$SB" >/dev/null 2>&1
rm -f "$SB/.openclaw/secrets/.env"        # wipe
run_guard restore "$BK" "$SB" >/dev/null 2>&1
if [ -f "$SB/.openclaw/secrets/.env" ]; then
  NEW_SHA="$( (command -v shasum >/dev/null && shasum -a 256 < "$SB/.openclaw/secrets/.env" || sha256sum < "$SB/.openclaw/secrets/.env") | awk '{print $1}')"
  if [ "$ORIG_SHA" = "$NEW_SHA" ]; then ok "T6: restored store is byte-identical"; else bad "T6: restored store differs"; fi
else
  bad "T6: restore did not recreate the store"
fi
if run_guard verify "$BK" "$SB" >/dev/null 2>&1; then
  ok  "T6: verify passes after restore"
else
  bad "T6: verify still fails after restore"
fi
rm -rf "$SB"

# ── summary ──────────────────────────────────────────────────────────────────
printf '\n\033[1m%d passed, %d failed\033[0m\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
