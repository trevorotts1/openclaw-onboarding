#!/usr/bin/env bash
# tests/unit/rr029-descriptor-target.test.sh
# ---------------------------------------------------------------------------
# RR-029 — the ONE descriptor (shared-utils/oc-env-descriptor.sh) resolves
# exactly one approved root / state db / service-or-container / gateway port,
# carries canonical box+company identity, rejects a decoy database, and gates
# on APP readiness rather than process/container existence.
# Fully offline: no live box, no `openclaw` CLI, no real network probe
# (a stub curl stands in for the health endpoint).
# ---------------------------------------------------------------------------
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DESC="$REPO_ROOT/shared-utils/oc-env-descriptor.sh"
[ -f "$DESC" ] || { echo "FATAL: $DESC not found"; exit 2; }

export OC_SKIP_CLI_PROBE=1
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/root/agents/main"
printf '{"agents":{"list":[{"id":"main"}]}}' > "$WORK/root/openclaw.json"

# Field reader: dh <env-prefix...> -- <printf-format>
dsc() { OC_CONFIG_ROOT="$WORK/root" "$@" bash -c \
  '. "$1"; ocd_init; printf "%s" "$2"' _ "$DESC" "$DSC_FMT"; }

bash -n "$DESC" && ok "descriptor passes bash -n" || bad "descriptor has a syntax error"

# --- 1. root resolution honours OC_CONFIG_ROOT -----------------------------
out="$(OC_CONFIG_ROOT="$WORK/root" bash -c '. "$1"; ocd_init; printf "%s|%s" "$OCD_ROOT" "$OCD_JSON_STATE"' _ "$DESC")"
[ "$out" = "$WORK/root|present" ] && ok "OC_CONFIG_ROOT honoured; config state=present" || bad "root resolution: $out"

# --- 2. DECOY REJECTION: 0-byte sqlite must never win ----------------------
if command -v sqlite3 >/dev/null 2>&1; then
  mkdir -p "$WORK/decoy/state"
  : > "$WORK/decoy/state/openclaw.sqlite"                        # candidate 1: zero bytes
  printf 'create table t (x integer);\n' | sqlite3 "$WORK/decoy/state.sqlite" >/dev/null 2>&1  # candidate 2: real
  out="$(OC_CONFIG_ROOT="$WORK/decoy" bash -c '. "$1"; ocd_init; printf "%s|%s" "${OCD_DB:-none}" "$OCD_DB_NOTE"' _ "$DESC")"
  [ "${out%%|*}" = "$WORK/decoy/state.sqlite" ] \
    && ok "0-byte decoy rejected; real candidate accepted" || bad "decoy handling picked: ${out%%|*}"
  case "$out" in
    *"zero-bytes"*) ok "rejection reason recorded (zero-bytes) — absence != broken instrument" ;;
    *) bad "rejection reason missing from: ${out#*|}" ;;
  esac
else
  echo "  (sqlite3 absent — decoy case UNDETERMINED, not counted as a pass)"
fi

# --- 3. IDENTITY: canonical box + company, env-first -----------------------
out="$(OC_CONFIG_ROOT="$WORK/root" OC_BOX_SLUG=qc-box COMPANY_SLUG=qc-co bash -c \
  '. "$1"; ocd_init; printf "%s|%s|%s" "$OCD_BOX_SLUG" "$OCD_COMPANY_SLUG" "$(ocd_identity_prefix)"' _ "$DESC")"
[ "$out" = "qc-box|qc-co|[box=qc-box company=qc-co]" ] \
  && ok "box/company resolved from canonical env; prefix is the exact reportable form" \
  || bad "identity resolution: $out"
out="$(OC_CONFIG_ROOT="$WORK/root" FLEET_STANDING_BOX_SLUG=qc-stand bash -c '. "$1"; ocd_init; printf "%s" "$OCD_BOX_SLUG"' _ "$DESC")"
[ "$out" = "qc-stand" ] && ok "FLEET_STANDING_BOX_SLUG accepted as the standing-box name" || bad "standing box slug: $out"

# --- 4. ONE EXACT TARGET per platform -------------------------------------
tgt() { OC_CONFIG_ROOT="$WORK/root" env "$@" bash -c '. "$1"; ocd_init; printf "%s|%s" "$OCD_TARGET_MODE" "$OCD_TARGET_ID"' _ "$DESC"; }
out="$(tgt OC_PLATFORM=mac OC_SERVICE_LABEL=ai.openclaw.gateway)"
[ "$out" = "launchd|ai.openclaw.gateway" ] && ok "mac -> the EXACT launchd label (no substring scan)" || bad "mac target: $out"
out="$(tgt OC_PLATFORM=mac OC_SERVICE_LABEL=com.blackceo.openclaw)"
[ "$out" = "launchd|com.blackceo.openclaw" ] && ok "mac -> label override honoured verbatim" || bad "mac label override: $out"
out="$(tgt OC_PLATFORM=vps-host OC_CONTAINER=openclaw)"
[ "$out" = "docker|openclaw" ] && ok "vps-host -> the EXACT container name (no --filter name= scan)" || bad "vps-host target: $out"
out="$(tgt OC_PLATFORM=vps-host OC_CONTAINER=client-x-gateway)"
[ "$out" = "docker|client-x-gateway" ] && ok "vps-host -> neighbour containers are never scanned or picked" || bad "vps-host container override: $out"
out="$(tgt OC_PLATFORM=vps-container)"
[ "$out" = "process|openclaw-gateway" ] && ok "inside container -> process mode (docker CLI absent by design)" || bad "container target: $out"
out="$(tgt OC_PLATFORM=unknown)"
[ "$out" = "unknown|" ] && ok "unresolved platform -> NO target claimed (undetermined, never a guess)" || bad "unknown platform target: $out"

# --- 5. APP READINESS gates on the health contract, not existence ----------
mkdir -p "$WORK/bin"
mkcurl() {
  cat > "$WORK/bin/curl" <<CU
#!/bin/bash
case "${OC_FIX_MODE:-ready}" in
  $1
esac
CU
  chmod +x "$WORK/bin/curl"
}
ready() { PATH="$WORK/bin:$PATH" OC_FIX_MODE="$1" OC_APP_READY_URL=http://127.0.0.1:18789/healthz \
  OC_APP_READY_ATTEMPTS="${2:-1}" OC_APP_READY_TIMEOUT=2 \
  bash -c '. "$1"; ocd_init; ocd_app_ready; printf "%s|%s" "$OCD_READY" "$OCD_READY_DETAIL"' _ "$DESC"; }

mkcurl 'ready) printf "{\"ok\":true,\"status\":\"live\"}\n200" ;;
  *) exit 99 ;;'
out="$(ready ready)";   [ "${out%%|*}" = "ready" ]       && ok "200 + ok:true -> ready"                  || bad "ready case: $out"
mkcurl 'ready) printf "{\"ok\":false,\"status\":\"starting\"}\n200" ;; *) exit 99 ;;'
out="$(ready ready)";   [ "${out%%|*}" = "not-ready" ]   && ok "200 WITHOUT ok:true -> not-ready (container Up is not app health)" || bad "notok case: $out"
mkcurl 'ready) printf "{\"ok\":true,\"status\":\"live\"}\n503" ;; *) exit 99 ;;'
out="$(ready ready)";   [ "${out%%|*}" = "not-ready" ]   && ok "ok:true at a non-200 status -> not-ready"  || bad "status case: $out"
mkcurl 'ready) printf "curl: (7) Failed to connect\n000"; exit 7 ;; *) exit 99 ;;'
out="$(ready ready)";   [ "${out%%|*}" = "not-ready" ]   && ok "connection refused -> not-ready (gateway down)" || bad "refuse case: $out"
mkcurl 'ready) printf "curl: (28) timed out\n000"; exit 28 ;; *) exit 99 ;;'
out="$(ready ready)";   [ "${out%%|*}" = "undetermined" ] && ok "timeout -> undetermined, never ready and never clean" || bad "slow case: $out"
mkcurl 'ready) echo "syntax garbage not even http"; exit 0 ;; *) exit 99 ;;'
out="$(ready ready 2)"; [ "${out%%|*}" = "not-ready" ]   && ok "malformed body -> not-ready (no accidental clean)" || bad "malformed case: $out"

# A single slow probe must not manufacture "undetermined" when a retry succeeds:
# the live gateway was measured answering this URL in 1.2ms yet one cold attempt
# returned rc=28. Only the repeated verdict may be reported.
mkcurl 'ready) n=0; [ -f "$OC_FIX_CTR" ] && n="$(cat "$OC_FIX_CTR")"
  n=$((n + 1)); printf "%s" "$n" > "$OC_FIX_CTR"
  if [ "$n" -lt 3 ]; then printf "curl: (28) timed out\n000"; exit 28; fi
  printf "{\"ok\":true,\"status\":\"live\"}\n200" ;;
  *) exit 99 ;;'
CTR="$WORK/ctr"; : > "$CTR"
out="$(PATH="$WORK/bin:$PATH" OC_FIX_CTR="$CTR" OC_FIX_MODE=ready OC_APP_READY_URL=http://127.0.0.1:18789/healthz \
  OC_APP_READY_ATTEMPTS=3 OC_APP_READY_TIMEOUT=2 \
  bash -c '. "$1"; ocd_init; ocd_app_ready; printf "%s|%s" "$OCD_READY" "$OCD_READY_DETAIL"' _ "$DESC")"
[ "${out%%|*}" = "ready" ] && ok "two slow probes then success -> ready (flake retried, not reported)" || bad "retry case: $out"
# and the inverse: a persistently unhealthy app must not be retried into "ready"
mkcurl 'ready) printf "{\"ok\":false,\"status\":\"starting\"}\n200" ;; *) exit 99 ;;'
out="$(ready ready 3)"
[ "${out%%|*}" = "not-ready" ] \
  && ok "3 attempts of a never-healthy body -> still not-ready (retry cannot launder a dead app)" \
  || bad "wedged case: $out"

# --- 6. a missing INSTRUMENT is undetermined, never clean -----------------
# (Note: a port is always resolvable by design — the discovery order ends in
# the documented 18789 default — so the honest absence case is a missing
# probe tool, which must never be reported as healthy.)
mkdir -p "$WORK/nobin"
out="$(PATH="$WORK/nobin" OC_CONFIG_ROOT="$WORK/root" OC_APP_READY_URL=http://127.0.0.1:18789/healthz \
  /bin/bash -c '. "$1"; ocd_init; ocd_app_ready; printf "%s" "$OCD_READY"' _ "$DESC" 2>/dev/null)"
[ "$out" = "undetermined" ] \
  && ok "no curl on PATH -> undetermined (a missing instrument is not a clean bill)" \
  || bad "missing-instrument case: ${out:-empty}"

echo "[rr029-descriptor-target] PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
echo "[rr029-descriptor-target] PASS (descriptor target + readiness)"
exit 0
