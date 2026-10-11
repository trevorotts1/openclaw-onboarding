#!/usr/bin/env bash
# ============================================================================
# deploy.sh — Drama Studio mini-app deploy / dry-run / zone guard (U4)
# ----------------------------------------------------------------------------
# FILES ONLY. This unit builds the deploy files and proves the dry-run path and
# the zone guard. It performs NO deployment: no wrangler call, no Cloudflare
# mutation, no bucket creation, no secret creation, no token use. The real
# deploy is a separate, later, Trevor-authorized step ("One bucket, two
# secrets, scoped project-object 45-day retention; deploy.sh --dry-run then
# real deploy").
#
# Reuses the Book Writer deploy pattern (53-book-writer/mini-app/deploy):
#   TRUST LAYER (deliberate, same shape):
#     - worker/wrangler.toml (U2, the service) keeps every real id as
#       <PLACEHOLDER>. This script resolves placeholders at deploy time into a
#       THROWAWAY temp config in $TMPDIR (deleted on exit) and passes it to
#       npx wrangler via --config. The toml itself is never rewritten; nothing
#       real ever lands in git.
#     - The token VALUE is env-only (CLOUDFLARE_DRAMA_STUDIO_API_TOKEN). It is
#       forwarded to CLOUDFLARE_API_TOKEN (wrangler's native auth var) per
#       call. No token value is ever printed.
#     - Secret values are read from the environment ONLY and piped to wrangler
#       stdin. They are never echoed.
#
#   ZONE GUARD (hard, cannot be disabled) — refuses any zone that is not the
#   intended BlackCEO Cloudflare account's zone:
#     G1  target zone NAME must equal the manifest's intended zone name
#         (zerohumanworkforce.com). A different name is refused.
#     G2  target zone id must not equal a known FOREIGN zone id
#         (STUDIO_FOREIGN_ZONE_ID — the businessaftersixty.com landmine).
#     G3  when an intended account is pinned (STUDIO_INTENDED_ACCOUNT_ID), the
#         target account id must equal it.
#     G4  a live run must resolve a real zone id AND account id. An empty
#         "not found" is a FAIL, never a pass.
#   No real zone/account id is committed; the intended-account pin is supplied
#   by the operator at deploy time (ids are public, secrets are not).
#
#   OPERATIONS:
#     deploy [VERSION]  resolve account+zone, run the zone guard, ensure the R2
#                       bucket, set 45-day lifecycle retention on the project
#                       prefix, set the two secrets, deploy the Worker.
#     status            show the resolved config (no mutations).
#     --dry-run         validate + plan every step WITHOUT any wrangler or API
#                       call. Honest: each step prints PLAN, the guard still
#                       fails hard on a wrong zone, unresolved ids report as
#                       unresolved and never as a pass.
#     --self-test       offline proof (no token, no network) that the guard
#                       refuses a wrong zone/account and that --dry-run is
#                       PLAN-only.
#
# USAGE:
#   ./deploy.sh --dry-run deploy
#   ./deploy.sh --self-test
#   CLOUDFLARE_DRAMA_STUDIO_API_TOKEN=... ./deploy.sh deploy      # NOT this unit
# ============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MINI_APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$SCRIPT_DIR/deploy.manifest.json"
CF_API="https://api.cloudflare.com/client/v4"
LIFECYCLE_RULE_ID="studio-project-retention"

# Manifest-backed config (filled by load_manifest).
WORKER_NAME=""
ROUTE_HOST=""
BUCKET_NAME=""
RETENTION_DAYS=""
RETENTION_PREFIX=""
INTENDED_ZONE_NAME=""
SERVICE_HOME=""
SECRET_NAMES=""
WRANGLER_TOML_REL=""
TOKEN_VAR=""

# Zone-guard inputs. Target values come from the environment when testing the
# guard offline; a live run resolves them from the Cloudflare API.
TARGET_ZONE_NAME="${STUDIO_ZONE_NAME:-}"
TARGET_ZONE_ID="${STUDIO_ZONE_ID:-}"
TARGET_ACCOUNT_ID="${STUDIO_ACCOUNT_ID:-}"
INTENDED_ACCOUNT_ID="${STUDIO_INTENDED_ACCOUNT_ID:-}"
FOREIGN_ZONE_ID="${STUDIO_FOREIGN_ZONE_ID:-}"

DRY_RUN=0
R_ZONE_ID=""
R_ACCOUNT_ID=""
TMP_CONFIG=""

cleanup() {
  if [ -n "$TMP_CONFIG" ] && [ -f "$TMP_CONFIG" ]; then rm -f "$TMP_CONFIG"; fi
  return 0
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Logging helpers (same shape as the Book Writer deploy pattern)
# ---------------------------------------------------------------------------
say()  { printf '  %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*" >&2; }
die()  { printf 'FATAL %s\n' "$*" >&2; exit 1; }
step() { if [ "$DRY_RUN" -eq 1 ]; then printf 'PLAN  %s\n' "$*"; else printf 'STEP  %s\n' "$*"; fi; }

# ---------------------------------------------------------------------------
# Manifest load (node is a hard requirement, same as the pattern)
# ---------------------------------------------------------------------------
load_manifest() {
  [ -f "$MANIFEST" ] || die "missing manifest $MANIFEST"
  command -v node >/dev/null 2>&1 || die "node is required to read the manifest"
  local k v
  while IFS=$'\t' read -r k v; do
    case "$k" in
      worker_name)         WORKER_NAME="$v" ;;
      route_host)          ROUTE_HOST="$v" ;;
      bucket_name)         BUCKET_NAME="$v" ;;
      retention_days)      RETENTION_DAYS="$v" ;;
      retention_prefix)    RETENTION_PREFIX="$v" ;;
      intended_zone_name)  INTENDED_ZONE_NAME="$v" ;;
      service_home)        SERVICE_HOME="$v" ;;
      secrets)             SECRET_NAMES="$v" ;;
      wrangler_toml)       WRANGLER_TOML_REL="$v" ;;
      token_var)           TOKEN_VAR="$v" ;;
    esac
  done < <(node -e '
    const fs = require("fs");
    const m = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
    const rows = [
      ["worker_name",        (m.worker && m.worker.name) || ""],
      ["route_host",         (m.worker && m.worker.route_host) || ""],
      ["bucket_name",        (m.bucket && m.bucket.name) || ""],
      ["retention_days",     String((m.bucket && m.bucket.retention_days) ?? "")],
      ["retention_prefix",   (m.bucket && m.bucket.retention_prefix) || ""],
      ["intended_zone_name", (m.cloudflare && m.cloudflare.intended_zone_name) || ""],
      ["service_home",       m.service_home || ""],
      ["secrets",            (m.secrets || []).map(s => (s && s.name) || s).join(" ")],
      ["wrangler_toml",      (m.env && m.env.wrangler_toml) || ""],
      ["token_var",          (m.env && m.env.token_var) || ""],
    ];
    for (const [k, v] of rows) process.stdout.write(k + "\t" + v + "\n");
  ' "$MANIFEST")

  [ -n "$WORKER_NAME" ]         || die "manifest missing worker.name"
  [ -n "$INTENDED_ZONE_NAME" ]  || die "manifest missing cloudflare.intended_zone_name"
  [ -n "$TOKEN_VAR" ]           || die "manifest missing env.token_var"
  # Default the target zone name to the intended one (an operator may override
  # it only to prove the guard refuses a different name).
  [ -n "$TARGET_ZONE_NAME" ] || TARGET_ZONE_NAME="$INTENDED_ZONE_NAME"
}

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
require_wrangler() {
  command -v npx >/dev/null 2>&1 || die "npx is required (wrangler runs via npx). Install Node.js >= 18."
}

require_token() {
  if [ -z "${!TOKEN_VAR:-}" ]; then
    die "$TOKEN_VAR is not set. The token value is read from the environment only (never committed)."
  fi
}

require_files() {
  [ -f "$MANIFEST" ]        || die "missing $MANIFEST"
  [ -f "$SCRIPT_DIR/deploy.sh" ] || die "missing $SCRIPT_DIR/deploy.sh"
  # Service/UI files belong to U2/U3. Report them honestly; only a live deploy
  # requires them (a dry-run must not depend on units that have not landed).
  local worker_toml="$MINI_APP_DIR/$WRANGLER_TOML_REL"
  if [ -f "$worker_toml" ]; then
    say "preflight: service config present ($WRANGLER_TOML_REL)"
  elif [ "$DRY_RUN" -eq 1 ]; then
    warn "preflight: service config $WRANGLER_TOML_REL absent (U2 not landed yet) — dry-run reports it as unresolved, no pass claimed"
  else
    die "preflight: missing $worker_toml (U2 service contract). Cannot deploy."
  fi
}

# Run a wrangler command with the operator token forwarded.
wr() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'PLAN  npx wrangler %s\n' "$*"
    return 0
  fi
  CLOUDFLARE_API_TOKEN="${!TOKEN_VAR:-}" \
  CLOUDFLARE_ACCOUNT_ID="${R_ACCOUNT_ID:-}" \
    npx wrangler "$@"
}

# ---------------------------------------------------------------------------
# Cloudflare API helpers (token from env; results are not secrets)
# ---------------------------------------------------------------------------
cf_api() {
  # cf_api <method> <path> [<json-body>]  -> prints JSON body; dies on non-200.
  # Dry-run is strictly offline: no curl, no token.
  local method="$1" path="$2" body="${3:-}"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  local code out
  out="$(mktemp "${TMPDIR:-/tmp}/studio-cf.XXXXXX")"
  if [ -n "$body" ]; then
    code="$(curl -sS -o "$out" -w '%{http_code}' -X "$method" \
      -H "Authorization: Bearer ${!TOKEN_VAR:-}" \
      -H "Content-Type: application/json" \
      --data "$body" "$CF_API$path" 2>/dev/null || echo 000)"
  else
    code="$(curl -sS -o "$out" -w '%{http_code}' -X "$method" \
      -H "Authorization: Bearer ${!TOKEN_VAR:-}" \
      -H "Content-Type: application/json" \
      "$CF_API$path" 2>/dev/null || echo 000)"
  fi
  local resp; resp="$(cat "$out" 2>/dev/null || true)"; rm -f "$out"
  if [ "$code" != "200" ]; then
    die "Cloudflare API $method $path returned HTTP $code: $resp"
  fi
  printf '%s\n' "$resp"
}

json_field() {
  # json_field <dotted-path>  -> reads JSON on stdin, prints the field or "".
  node -e '
    let s = ""; process.stdin.on("data", d => s += d).on("end", () => {
      let j; try { j = JSON.parse(s); } catch { process.stdout.write(""); process.exit(0); }
      let v = j;
      for (const p of process.argv[1].split(".")) {
        if (!p) continue;
        if (v === null || typeof v !== "object" || !(p in v)) { process.stdout.write(""); process.exit(0); }
        v = v[p];
      }
      process.stdout.write(v === null || v === undefined ? "" : String(v));
    });
  ' "$1"
}

# ---------------------------------------------------------------------------
# Resolution: zone id + account id (live, or supplied by the operator)
# ---------------------------------------------------------------------------
resolve_account_and_zone() {
  step "resolve: zone id + account id for $TARGET_ZONE_NAME"
  R_ZONE_ID="$TARGET_ZONE_ID"
  R_ACCOUNT_ID="$TARGET_ACCOUNT_ID"

  if [ "$DRY_RUN" -eq 1 ] && [ -z "${!TOKEN_VAR:-}" ]; then
    # No token, dry-run: nothing to resolve. Supplied values still count.
    return 0
  fi

  if [ -z "$R_ZONE_ID" ]; then
    local zdata
    zdata="$(cf_api GET "/zones?name=$TARGET_ZONE_NAME&per_page=1")"
    R_ZONE_ID="$(printf '%s' "$zdata" | json_field "result.0.id")"
    [ -n "$R_ACCOUNT_ID" ] || R_ACCOUNT_ID="$(printf '%s' "$zdata" | json_field "result.0.account.id")"
  fi
}

# ---------------------------------------------------------------------------
# ZONE GUARD — the hard gate. Cannot be disabled.
# ---------------------------------------------------------------------------
assert_zone_guard() {
  step "zone-guard: intended zone name = $INTENDED_ZONE_NAME"
  step "zone-guard: target   zone name = ${TARGET_ZONE_NAME:-<unresolved>}"
  step "zone-guard: target   zone id   = ${R_ZONE_ID:-<unresolved>}"
  step "zone-guard: target   account   = ${R_ACCOUNT_ID:-<unresolved>}"

  # G1: the target zone must be the intended BlackCEO zone, by name.
  if [ -n "$TARGET_ZONE_NAME" ] && [ "$TARGET_ZONE_NAME" != "$INTENDED_ZONE_NAME" ]; then
    die "ZONE GUARD BLOCKED (wrong zone): target '$TARGET_ZONE_NAME' is not the intended BlackCEO zone '$INTENDED_ZONE_NAME'. Refusing to act."
  fi

  # G2: the foreign-zone landmine (a known different zone id).
  if [ -n "$R_ZONE_ID" ] && [ -n "$FOREIGN_ZONE_ID" ] && [ "$R_ZONE_ID" = "$FOREIGN_ZONE_ID" ]; then
    die "ZONE GUARD BLOCKED (foreign zone): target zone id ($R_ZONE_ID) equals the known foreign zone id. Refusing to act."
  fi

  # G3: when the intended account is pinned, the target must match it.
  if [ -n "$INTENDED_ACCOUNT_ID" ] && [ -n "$R_ACCOUNT_ID" ] && [ "$R_ACCOUNT_ID" != "$INTENDED_ACCOUNT_ID" ]; then
    die "ZONE GUARD BLOCKED (wrong account): target account '$R_ACCOUNT_ID' is not the intended BlackCEO account. Refusing to act."
  fi

  # G4: a live run must have proven both ids. Empty is a FAIL, never a pass.
  if [ "$DRY_RUN" -eq 0 ]; then
    [ -n "$R_ZONE_ID" ]    || die "ZONE GUARD BLOCKED: could not resolve a zone id for $TARGET_ZONE_NAME (empty). Refusing."
    [ -n "$R_ACCOUNT_ID" ] || die "ZONE GUARD BLOCKED: could not resolve the account id. Refusing."
    say "zone-guard: PASS"
    return 0
  fi

  # Dry-run: never fabricate a PASS it could not prove.
  if [ -z "$R_ZONE_ID" ] || [ -z "$R_ACCOUNT_ID" ]; then
    warn "zone-guard: ids unresolved in --dry-run (no token). No PASS claimed; this run performs no mutations."
  else
    say "zone-guard: PASS"
  fi
}

# ---------------------------------------------------------------------------
# Provision: R2 bucket + 45-day project-object retention
# ---------------------------------------------------------------------------
ensure_bucket() {
  step "r2-bucket: ensure bucket '$BUCKET_NAME' exists"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  if wr r2 bucket list 2>&1 | grep -q "$BUCKET_NAME"; then
    say "r2-bucket: '$BUCKET_NAME' already exists — skipping create"
    return 0
  fi
  say "r2-bucket: creating '$BUCKET_NAME'"
  wr r2 bucket create "$BUCKET_NAME" >/dev/null
}

ensure_retention() {
  # Scoped project-object retention: objects under RETENTION_PREFIX expire
  # after RETENTION_DAYS days. ponytail: the live lifecycle PUT is not exercised
  # by this unit (dry-run only); verify the R2 lifecycle body against the live
  # API when the Deploy row runs.
  step "r2-lifecycle: ${RETENTION_DAYS}d retention on '$RETENTION_PREFIX'"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  local secs=$(( RETENTION_DAYS * 86400 ))
  local body
  body="$(node -e '
    process.stdout.write(JSON.stringify({rules:[{
      id: process.argv[1],
      enabled: true,
      conditions: { prefix: process.argv[2] },
      deleteObjectsTransition: { condition: { type: "Age", maxAge: Number(process.argv[3]) } }
    }]}));
  ' "$LIFECYCLE_RULE_ID" "$RETENTION_PREFIX" "$secs")"
  cf_api PUT "/accounts/$R_ACCOUNT_ID/r2/buckets/$BUCKET_NAME/lifecycle" "$body" >/dev/null
  say "r2-lifecycle: rule '$LIFECYCLE_RULE_ID' -> ${RETENTION_DAYS}d on ${RETENTION_PREFIX}"
}

# ---------------------------------------------------------------------------
# Secrets (values from env, never echoed) + Worker deploy
# ---------------------------------------------------------------------------
set_secrets() {
  step "secrets: set $SECRET_NAMES (names from manifest, values from env)"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  local name val
  for name in $SECRET_NAMES; do
    val="${!name:-}"
    if [ -z "$val" ]; then
      warn "secret $name not set in env — skipping (the Worker fails closed until it is set)"
      continue
    fi
    printf '%s\n' "$val" | wr secret put "$name" --name "$WORKER_NAME" >/dev/null
    say "secret $name: set (value never echoed)"
    unset val
  done
}

deploy_worker() {
  step "deploy: npx wrangler deploy (zone-guard already passed)"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  local worker_toml="$MINI_APP_DIR/$WRANGLER_TOML_REL"
  [ -f "$worker_toml" ] || die "deploy: missing $worker_toml"
  TMP_CONFIG="$(mktemp "${TMPDIR:-/tmp}/studio-wrangler.XXXXXX.toml")"
  # Resolve <PLACEHOLDER> ids into a THROWAWAY config; the toml is untouched.
  sed -E \
    -e "s#<PLACEHOLDER_CF_ACCOUNT_ID>#$R_ACCOUNT_ID#g" \
    "$worker_toml" > "$TMP_CONFIG"
  say "deploy: temp config written (deleted on exit) — $WRANGLER_TOML_REL untouched"
  wr deploy --config "$TMP_CONFIG"
}

# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
cmd_status() {
  say "service home: $SERVICE_HOME"
  say "worker-name : $WORKER_NAME"
  say "route       : $ROUTE_HOST"
  say "r2 bucket   : $BUCKET_NAME"
  say "retention   : ${RETENTION_DAYS}d on ${RETENTION_PREFIX}"
  say "secrets     : $SECRET_NAMES"
  say "zone (intended): $INTENDED_ZONE_NAME"
  say "zone (target)  : ${R_ZONE_ID:-<unresolved>}"
}

# ---------------------------------------------------------------------------
# --self-test: offline, no token, no network. Proves the guard refuses a wrong
# zone AND a wrong account, and that --dry-run is PLAN-only. Fails hard on any
# regression.
# ---------------------------------------------------------------------------
self_test() {
  local pass=1
  local out; out="$(mktemp "${TMPDIR:-/tmp}/studio-self-test.XXXXXX")"

  # 1. Wrong zone NAME must hard-fail.
  if STUDIO_ZONE_NAME="businessaftersixty.com" bash "$0" --dry-run deploy >"$out" 2>&1; then
    warn "SELFTEST FAIL: wrong-zone-name guard did not refuse"
    pass=0
  elif grep -q "ZONE GUARD BLOCKED (wrong zone)" "$out"; then
    say "SELFTEST OK: wrong zone name refused (non-zero exit, guard message)"
  else
    warn "SELFTEST FAIL: refused but no guard message"
    pass=0
  fi

  # 2. Foreign zone id (landmine) must hard-fail.
  if STUDIO_ZONE_ID="deadbeef" STUDIO_FOREIGN_ZONE_ID="deadbeef" \
       bash "$0" --dry-run deploy >"$out" 2>&1; then
    warn "SELFTEST FAIL: foreign-zone guard did not refuse"
    pass=0
  elif grep -q "ZONE GUARD BLOCKED (foreign zone)" "$out"; then
    say "SELFTEST OK: foreign zone id refused (non-zero exit, guard message)"
  else
    warn "SELFTEST FAIL: foreign zone refused but no guard message"
    pass=0
  fi

  # 3. Wrong account must hard-fail when the intended account is pinned.
  if STUDIO_INTENDED_ACCOUNT_ID="acct-intended" STUDIO_ACCOUNT_ID="acct-other" \
       bash "$0" --dry-run deploy >"$out" 2>&1; then
    warn "SELFTEST FAIL: wrong-account guard did not refuse"
    pass=0
  elif grep -q "ZONE GUARD BLOCKED (wrong account)" "$out"; then
    say "SELFTEST OK: wrong account refused (non-zero exit, guard message)"
  else
    warn "SELFTEST FAIL: wrong account refused but no guard message"
    pass=0
  fi

  # 4. Intended zone dry-run exits 0 and plans the steps.
  if ! STUDIO_ZONE_ID="a9ecc0a0" STUDIO_ACCOUNT_ID="13f808b7" \
        bash "$0" --dry-run deploy >"$out" 2>&1; then
    warn "SELFTEST FAIL: intended-zone --dry-run exited non-zero"
    pass=0
  elif grep -q "^PLAN  r2-bucket:" "$out" && grep -q "^PLAN  deploy:" "$out" \
       && grep -q "zone-guard: PASS" "$out"; then
    say "SELFTEST OK: intended-zone --dry-run planned + guard PASSed"
  else
    warn "SELFTEST FAIL: intended-zone --dry-run did not print expected PLAN/PASS"
    pass=0
  fi

  # 5. Dry-run must not claim a PASS with unresolved ids, and must make no real
  #    call (no token, no curl, no wrangler).
  if ! bash "$0" --dry-run deploy >"$out" 2>&1; then
    warn "SELFTEST FAIL: --dry-run with unresolved ids exited non-zero"
    pass=0
  elif grep -q "zone-guard: PASS" "$out"; then
    warn "SELFTEST FAIL: --dry-run without a token claimed zone-guard PASS"
    pass=0
  elif grep -E "^[^P].*(curl -sS|npx wrangler )" "$out" >/dev/null 2>&1; then
    warn "SELFTEST FAIL: a real wrangler/curl call appeared in dry-run"
    pass=0
  else
    say "SELFTEST OK: --dry-run is PLAN-only, no fabricated PASS"
  fi

  rm -f "$out"
  if [ "$pass" -eq 1 ]; then say "U4 deploy self-test: PASS"; exit 0; fi
  die "U4 deploy self-test: FAIL"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
usage() {
  cat <<'EOF'
USAGE:
  ./deploy.sh [--dry-run] deploy [VERSION]
  ./deploy.sh [--dry-run] status
  ./deploy.sh --self-test

  deploy      resolve account+zone, run the zone guard, ensure the R2 bucket,
              set 45-day project-object retention, set the two secrets, deploy
              the Worker. (The real deploy is a separate, authorized step.)
  status      show the resolved config. No mutations.
  --dry-run   validate + plan WITHOUT any wrangler or API call. Honest: PLAN
              per step, guards still fail hard on a wrong zone.
  --self-test offline guard proof (no token, no network).

ZONE GUARD: refuses any zone that is not the intended BlackCEO zone
(zerohumanworkforce.com by name, plus a foreign-zone-id landmine and an
optional intended-account pin).
EOF
}

main() {
  local cmd=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run)   DRY_RUN=1; shift ;;
      --self-test) load_manifest; self_test ;;
      -h|--help)   usage; exit 0 ;;
      deploy|status) cmd="$1"; shift ;;
      *) shift ;;
    esac
  done
  [ -n "$cmd" ] || { usage; exit 1; }

  load_manifest
  require_files
  require_wrangler
  if [ "$DRY_RUN" -eq 0 ]; then require_token; fi

  resolve_account_and_zone
  assert_zone_guard

  case "$cmd" in
    status) cmd_status ;;
    deploy)
      say "deploy: worker=$WORKER_NAME route=$ROUTE_HOST"
      ensure_bucket
      ensure_retention
      set_secrets
      deploy_worker
      if [ "$DRY_RUN" -eq 1 ]; then
        say "DRY-RUN COMPLETE: no mutations performed. No deploy happened."
      else
        say "DONE deploy (route $ROUTE_HOST)"
      fi
      ;;
  esac
}

main "$@"
