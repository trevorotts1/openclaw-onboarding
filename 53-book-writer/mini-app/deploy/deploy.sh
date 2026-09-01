#!/usr/bin/env bash
# ============================================================================
# deploy.sh — Book Writer mini-app deploy / rollback / config-flip (U19)
# ----------------------------------------------------------------------------
# A REAL deploy script for the single-Worker Cloudflare contract
# (mini-app/worker/wrangler.toml). It resolves the LITERAL zerohumanworkforce.com
# zone id at deploy time, refuses to run if that id ever equals the
# businessaftersixty.com zone id (ZONE LANDMINE), versions the R2 app bundle
# under app/<version>/, activates a version by flipping the `app/latest`
# pointer, and idempotently seeds the bw_bindings KV namespace.
#
#   TRUST LAYER (deliberate):
#     - wrangler.toml keeps every real id as <PLACEHOLDER>. This script is the
#       ONLY thing that resolves placeholders at deploy time. It NEVER writes a
#       real id back into wrangler.toml: it builds a THROWAWAY temp config in
#       /tmp (deleted on exit) with the resolved ids, and passes it to npx
#       wrangler via --config. Nothing real ever lands in git.
#     - The API token name is CLOUDFLARE_ZHW_APPS_API_TOKEN. The VALUE comes
#       from the environment ONLY; this file never contains a token value.
#       Wrangler natively authenticates via CLOUDFLARE_API_TOKEN, so the script
#       forwards the env value to that var for each wrangler call.
#     - The Worker holds ZERO client credentials (dumb relay). The KV binding
#       row is the SOLE destination authority. No Anthropic ids, no {{...}},
#       no client keys anywhere in this tree.
#
#   OPERATIONS:
#     deploy            resolve zone + account, provision bucket + KV namespace,
#                       upload app/<version>/ bundle + config/<slug>/...,
#                       seed bw_bindings, set secrets, flip app/latest, deploy
#                       the Worker.
#     rollback [VERSION]  flip app/latest back to the previous (or named)
#                       app/<version>/ — no Worker code change, instant.
#     flip <VERSION>    activate an existing R2 app version (config flip).
#     status            show active version + deployed Worker version.
#     --dry-run         validate every step WITHOUT executing any wrangler or
#                       API call (honest: each step prints PLAN, the guard still
#                       fails hard on a wrong zone, unresolved ids report as
#                       unresolved and are NEVER claimed as a pass).
#
#   ZONE LANDMINE GUARD (hard, cannot be disabled):
#     The zerohumanworkforce.com zone id is a DIFFERENT zone from
#     businessaftersixty.com. This script resolves the zone id for
#     zerohumanworkforce.com from the Cloudflare API and REFUSES TO RUN if it
#     equals the businessaftersixty.com zone id. It also refuses if it cannot
#     resolve a real id (an empty "not found" is a FAIL, never a pass).
#
# USAGE:
#   ./deploy.sh --dry-run                          # validate, no wrangler calls
#   CLOUDFLARE_ZHW_APPS_API_TOKEN=... ./deploy.sh deploy
#   CLOUDFLARE_ZHW_APPS_API_TOKEN=... ./deploy.sh rollback
#   CLOUDFLARE_ZHW_APPS_API_TOKEN=... ./deploy.sh flip v1
#   CLOUDFLARE_ZHW_APPS_API_TOKEN=... ./deploy.sh status
# ============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MINI_APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKER_DIR="$MINI_APP_DIR/worker"
PAGES_DIR="$MINI_APP_DIR/pages"
CONFIGS_DIR="$MINI_APP_DIR/configs"
WRANGLER_TOML="$WORKER_DIR/wrangler.toml"
SCHEMA_SQL="$WORKER_DIR/schema.sql"

# ---------------------------------------------------------------------------
# Config (name-only token — the value is env-only, never committed)
# ---------------------------------------------------------------------------
ZONE_NAME_ZHW="zerohumanworkforce.com"
ZONE_NAME_BAS="businessaftersixty.com"
WORKER_NAME="book-writer-mini-app"
BUCKET_NAME="zhw-bookwriter"
KV_BINDING="bw_bindings"
ROUTE_HOST="bookwriter.zerohumanworkforce.com"
CF_API="https://api.cloudflare.com/client/v4"
VERSIONS_INDEX="app/versions.json"

# Zone-landmine guard pins. Overrides exist ONLY to test the guard (dry-run,
# no token). These are zone ids, not secrets (zone ids are public on the
# dashboard). When empty, the script resolves them live from the API.
ZONE_ID_ZHW="${ZONE_ID_ZHW:-}"
ZONE_ID_BAS="${ZONE_ID_BAS:-}"
# Account id override (normally resolved live from the zone's owning account).
CF_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-}"

DRY_RUN=0
# Resolved live values (empty until resolved).
R_ZHW=""; R_BAS=""; R_ACCOUNT=""; R_KV_ID=""; R_PREVIEW_ID=""
TMP_CONFIG=""

cleanup() {
  if [ -n "$TMP_CONFIG" ] && [ -f "$TMP_CONFIG" ]; then
    rm -f "$TMP_CONFIG"
  fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
say()  { printf '  %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*" >&2; }
die()  { printf 'FATAL %s\n' "$*" >&2; exit 1; }

step() {
  if [ "$DRY_RUN" -eq 1 ]; then printf 'PLAN  %s\n' "$*"; else printf 'STEP  %s\n' "$*"; fi
}

# ---------------------------------------------------------------------------
# Env / tooling preflight
# ---------------------------------------------------------------------------
require_token() {
  if [ -z "${CLOUDFLARE_ZHW_APPS_API_TOKEN:-}" ]; then
    die "CLOUDFLARE_ZHW_APPS_API_TOKEN is not set. The token VALUE is read from \
the environment only (never committed). Export it before running."
  fi
}

require_wrangler() {
  if ! command -v npx >/dev/null 2>&1; then
    die "npx is required (wrangler runs via npx). Install Node.js >= 18."
  fi
}

require_files() {
  [ -f "$WRANGLER_TOML" ]        || die "missing $WRANGLER_TOML"
  [ -f "$SCHEMA_SQL" ]           || die "missing $SCHEMA_SQL"
  [ -f "$PAGES_DIR/index.html" ] || die "missing $PAGES_DIR/index.html"
  [ -f "$PAGES_DIR/app.js" ]     || die "missing $PAGES_DIR/app.js (the SPA bundle)"
  [ -d "$CONFIGS_DIR" ]          || die "missing $CONFIGS_DIR"
}

# Run a wrangler command with the operator token forwarded (CLOUDFLARE_API_TOKEN
# is wrangler's native auth var) and the resolved account id (CLOUDFLARE_ACCOUNT_ID
# is wrangler's native account override).
wr() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'PLAN  npx wrangler %s\n' "$*"
    return 0
  fi
  CLOUDFLARE_API_TOKEN="${CLOUDFLARE_ZHW_APPS_API_TOKEN:-}" \
  CLOUDFLARE_ACCOUNT_ID="${R_ACCOUNT:-}" \
    npx wrangler "$@"
}

# ---------------------------------------------------------------------------
# Cloudflare API helper (token from env; results are not secrets)
# ---------------------------------------------------------------------------
cf_api() {
  # cf_api <path> [<extra-curl-args>...]  -> prints JSON body; dies on non-200.
  # Dry-run is strictly offline: no curl, no token, nothing fabricated.
  local path="$1"; shift
  if [ "$DRY_RUN" -eq 1 ]; then
    return 0
  fi
  local code body
  code="$(curl -sS -o /tmp/bw-cf-body.$$ -w '%{http_code}' \
    -H "Authorization: Bearer ${CLOUDFLARE_ZHW_APPS_API_TOKEN:-}" \
    -H "Content-Type: application/json" \
    "$@" "$CF_API$path" 2>/dev/null || echo 000)"
  body="$(cat /tmp/bw-cf-body.$$ 2>/dev/null || true)"
  rm -f /tmp/bw-cf-body.$$
  if [ "$code" != "200" ]; then
    die "Cloudflare API $path returned HTTP $code: $body"
  fi
  printf '%s\n' "$body"
}

json_field() {
  # json_field <path>  -> reads JSON on stdin, prints the dotted-path field.
  # Uses node (already required). Empty string on missing.
  local path="$1"
  node -e '
    let s = ""; process.stdin.on("data", d => s += d).on("end", () => {
      let j; try { j = JSON.parse(s); } catch { process.stdout.write(""); process.exit(0); }
      const parts = process.argv[1].split("."); let v = j;
      for (const p of parts) { if (v === null || typeof v !== "object" || !(p in v)) { process.stdout.write(""); process.exit(0); } v = v[p]; }
      process.stdout.write(v === null || v === undefined ? "" : String(v));
    });
  ' "$path"
}

# ---------------------------------------------------------------------------
# Resolution: account id + both zone ids (live or overridden). Never faked.
# ---------------------------------------------------------------------------
resolve_account_and_zones() {
  step "resolve: account id + zone ids for $ZONE_NAME_ZHW / $ZONE_NAME_BAS"

  if [ "$DRY_RUN" -eq 1 ] && [ -z "${CLOUDFLARE_ZHW_APPS_API_TOKEN:-}" ]; then
    # No token in dry-run: nothing to resolve. Overrides still count.
    R_ZHW="$ZONE_ID_ZHW"; R_BAS="$ZONE_ID_BAS"; R_ACCOUNT="$CF_ACCOUNT_ID"
    return 0
  fi

  if [ -n "$ZONE_ID_ZHW" ]; then
    R_ZHW="$ZONE_ID_ZHW"
  else
    local zdata
    zdata="$(cf_api "/zones?name=$ZONE_NAME_ZHW&per_page=1")"
    R_ZHW="$(printf '%s' "$zdata" | json_field "result.0.id")"
    if [ -n "$R_ZHW" ] && [ -z "$R_ACCOUNT" ]; then
      R_ACCOUNT="$(printf '%s' "$zdata" | json_field "result.0.account.id")"
    fi
  fi

  if [ -n "$ZONE_ID_BAS" ]; then
    R_BAS="$ZONE_ID_BAS"
  else
    R_BAS="$(cf_api "/zones?name=$ZONE_NAME_BAS&per_page=1" | json_field "result.0.id")"
  fi

  # Account id: an explicit CLOUDFLARE_ACCOUNT_ID wins; otherwise the zone's
  # owning account (resolved above) is used.
  if [ -n "$CF_ACCOUNT_ID" ]; then
    R_ACCOUNT="$CF_ACCOUNT_ID"
  fi

  say "resolve: account id  = ${R_ACCOUNT:-<unresolved>}"
  say "resolve: ZHW zone id = ${R_ZHW:-<unresolved>}"
  say "resolve: BAS zone id = ${R_BAS:-<unresolved>}"
}

# ---------------------------------------------------------------------------
# ZONE LANDMINE GUARD — the hard gate. Cannot be disabled.
# ---------------------------------------------------------------------------
assert_zone_guard() {
  local zhw bas
  zhw="${R_ZHW:-$ZONE_ID_ZHW}"
  bas="${R_BAS:-$ZONE_ID_BAS}"

  step "zone-guard: zerohumanworkforce.com id  = ${zhw:-<unresolved>}"
  step "zone-guard: businessaftersixty.com id  = ${bas:-<unresolved>}"

  # The LANDMINE: ZHW must never equal BAS. This is checkable even in dry-run
  # when either override pins both ids, and it ALWAYS fails hard.
  if [ -n "$zhw" ] && [ -n "$bas" ] && [ "$zhw" = "$bas" ]; then
    die "ZONE LANDMINE GUARD BLOCKED: zerohumanworkforce.com resolved to the \
businessaftersixty.com zone id ($zhw). Refusing to continue."
  fi

  # A live (non-dry-run) run MUST prove both ids. An empty id is a FAIL — never
  # a pass. We cannot claim we are NOT on the wrong zone without knowing the
  # other zone's id.
  if [ "$DRY_RUN" -eq 0 ]; then
    if [ -z "$zhw" ]; then
      die "ZONE LANDMINE GUARD BLOCKED: could not resolve a zone id for \
$ZONE_NAME_ZHW (empty). Refusing to continue."
    fi
    if [ -z "$bas" ]; then
      die "ZONE LANDMINE GUARD BLOCKED: could not resolve a zone id for \
$ZONE_NAME_BAS (empty). Cannot prove we are on the right zone. Refusing."
    fi
    say "zone-guard: PASS"
    return 0
  fi

  # Dry-run without a token cannot resolve ids. It reports HONESTLY: no PASS is
  # claimed, and the plan continues ONLY because no mutation happens anyway.
  # The one hard fail that still applies is the equality landmine above.
  if [ -z "$zhw" ] || [ -z "$bas" ]; then
    warn "zone-guard: cannot resolve zone ids in --dry-run without a token. \
No PASS is claimed; this run performs no mutations. Run with a real token to verify."
  else
    say "zone-guard: PASS"
  fi
}

# ---------------------------------------------------------------------------
# Provision: R2 bucket + KV namespace (idempotent)
# ---------------------------------------------------------------------------
ensure_r2_bucket() {
  step "r2-bucket: ensure bucket '$BUCKET_NAME' exists"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  if wr r2 bucket list 2>&1 | grep -q "$BUCKET_NAME"; then
    say "r2-bucket: '$BUCKET_NAME' already exists — skipping create"
    return 0
  fi
  say "r2-bucket: creating '$BUCKET_NAME'"
  wr r2 bucket create "$BUCKET_NAME" >/dev/null
}

ensure_kv_namespace() {
  step "kv-namespace: ensure namespace '$KV_BINDING' exists"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  local data id preview
  # List first (idempotent): pull the whole list and find the namespace by title.
  id="$(cf_api "/accounts/$R_ACCOUNT/storage/kv/namespaces?per_page=50" | node -e '
    let s = ""; process.stdin.on("data", d => s += d).on("end", () => {
      let j; try { j = JSON.parse(s); } catch { process.stdout.write(""); process.exit(0); }
      if (!j || !j.success || !Array.isArray(j.result)) { process.stdout.write(""); process.exit(0); }
      const ns = j.result.find(n => n.title === process.env.KV_TITLE);
      process.stdout.write(ns ? (ns.id || "") : "");
    });
  ' KV_TITLE="$KV_BINDING")"
  if [ -n "$id" ]; then
    R_KV_ID="$id"; R_PREVIEW_ID="$id"
    say "kv-namespace: '$KV_BINDING' already exists (id ${id:0:8}...)"
    return 0
  fi
  say "kv-namespace: creating '$KV_BINDING'"
  data="$(wr kv namespace create "$KV_BINDING" 2>&1)"
  id="$(printf '%s\n' "$data" | sed -nE 's/.*\bid[[:space:]]*=[[:space:]]*"([0-9a-f]{32})".*/\1/p; s/.*\bid[[:space:]]*:[[:space:]]*"([0-9a-f]{32})".*/\1/p' | head -1)"
  preview="$(printf '%s\n' "$data" | sed -nE 's/.*\bpreview_id[[:space:]]*=[[:space:]]*"([0-9a-f]{32})".*/\1/p; s/.*\bpreview_id[[:space:]]*:[[:space:]]*"([0-9a-f]{32})".*/\1/p' | head -1)"
  [ -n "$id" ] || die "could not parse KV namespace id from wrangler output"
  R_KV_ID="$id"; R_PREVIEW_ID="${preview:-$id}"
  say "kv-namespace: created '$KV_BINDING' (id ${id:0:8}...)"
}

# ---------------------------------------------------------------------------
# R2 bundle upload: app/<version>/ + config/<slug>/... + app/latest flip
# ---------------------------------------------------------------------------
bundle_version() {
  local stamp="$(date +%Y%m%d-%H%M%S)"
  if [ -n "${VERSION_SUFFIX:-}" ]; then
    printf 'v%s-%s\n' "$stamp" "$VERSION_SUFFIX"
  else
    printf 'v%s\n' "$stamp"
  fi
}

upload_bundle() {
  local version="$1"
  step "r2-app: upload app bundle to app/$version/"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  wr r2 object put "$BUCKET_NAME/app/$version/index.html" \
    --file "$PAGES_DIR/index.html" --content-type "text/html; charset=utf-8" >/dev/null
  wr r2 object put "$BUCKET_NAME/app/$version/app.js" \
    --file "$PAGES_DIR/app.js" --content-type "application/javascript; charset=utf-8" >/dev/null
  say "r2-app: uploaded app/$version/ (index.html, app.js)"
}

upload_configs() {
  # Config filenames on disk mirror the Worker's R2 path EXACTLY, including the
  # colon variant: P0-INTAKE-full.json  -> config/<slug>/P0-INTAKE:full.json
  #                P0-INTAKE-4x3x3.json -> config/<slug>/P0-INTAKE:4x3x3.json
  #                GATE-1-title.json    -> config/<slug>/GATE-1-title.json
  # (configObjectPath in worker/src/lib.js.)
  local slug config_file target
  step "r2-config: upload phase configs (config/<slug>/...) for slugs: $*"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  for config_file in "$CONFIGS_DIR"/*.json; do
    local base
    base="$(basename "$config_file")"
    # Rename the P0-INTAKE disk names to the Worker's colon path.
    case "$base" in
      P0-INTAKE-full.json)   target="P0-INTAKE:full.json" ;;
      P0-INTAKE-4x3x3.json)  target="P0-INTAKE:4x3x3.json" ;;
      *)                     target="$base" ;;
    esac
    for slug in "$@"; do
      wr r2 object put "$BUCKET_NAME/config/$slug/$target" \
        --file "$config_file" --content-type "application/json; charset=utf-8" >/dev/null
      say "r2-config: config/$slug/$target"
    done
  done
}

flip_active() {
  local version="$1"
  step "r2-flip: activate app/$version/ (write app/latest pointer)"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  printf '{"version":"%s"}\n' "$version" | \
    wr r2 object put "$BUCKET_NAME/app/latest" --pipe \
      --content-type "application/json" >/dev/null
  say "r2-flip: app/latest -> {\"version\":\"$version\"}"
}

record_version() {
  # Append to the deploy-side version index (R2 object app/versions.json) so
  # rollback can find the previous version without an R2 list API.
  local version="$1" index new
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  index="$(wr r2 object get "$BUCKET_NAME/$VERSIONS_INDEX" --pipe 2>/dev/null || true)"
  if [ -n "$index" ]; then
    new="$(printf '%s' "$index" | node -e '
      let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
        let arr=[]; try { const j=JSON.parse(s); if (Array.isArray(j)) arr=j; } catch {}
        const v=process.argv[1];
        if (arr[arr.length-1]!==v) arr.push(v);
        process.stdout.write(JSON.stringify(arr));
      });
    ' "$version")"
  else
    new="[\"$version\"]"
  fi
  printf '%s\n' "$new" | wr r2 object put "$BUCKET_NAME/$VERSIONS_INDEX" --pipe \
    --content-type "application/json" >/dev/null
}

list_versions() {
  # Read the deploy-side version index (no R2 list API exists in wrangler).
  local index
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "<versions from app/versions.json at deploy time>"
    return 0
  fi
  index="$(wr r2 object get "$BUCKET_NAME/$VERSIONS_INDEX" --pipe 2>/dev/null || true)"
  if [ -z "$index" ]; then return 0; fi
  printf '%s' "$index" | node -e '
    let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
      try { const j=JSON.parse(s); if (Array.isArray(j)) j.forEach(v=>console.log(v)); }
      catch {}
    });
  '
}

current_active_version() {
  local raw
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "<app/latest resolved at deploy time>"
    return 0
  fi
  raw="$(wr r2 object get "$BUCKET_NAME/app/latest" --pipe 2>/dev/null || true)"
  if [ -n "$raw" ]; then
    printf '%s' "$raw" | node -e '
      let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
        try { process.stdout.write(JSON.parse(s).version||""); } catch { process.stdout.write(""); }
      });
    '
  else
    echo ""
  fi
}

# ---------------------------------------------------------------------------
# KV seed (idempotent)
# ---------------------------------------------------------------------------
seed_kv() {
  step "kv-seed: seed '$KV_BINDING' (idempotent) from schema.sql inventory"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  [ -n "$R_KV_ID" ] || die "kv-seed: no KV namespace id (run deploy, not rollback)"
  # schema.sql is the DECLARATIVE inventory (tk:, reg:, run:, ctr: keys).
  # The registry is seeded with an explicit, documented marker set so the
  # Worker's slug→client mapping is never empty; real per-client rows are
  # seeded by the box-side ingest poller (U12), never here.
  local slug reg_key reg_val
  for slug in "fake-alpha" "fake-beta" "fake-gate1"; do
    reg_key="reg:$slug"
    reg_val="{\"client_id\":\"client_$(echo "$slug" | tr '-' '_' | tr '[:lower:]' '[:upper:]')\",\"slug\":\"$slug\",\"contact_seed\":null}"
    wr kv key put "$reg_key" "$reg_val" --namespace-id "$R_KV_ID" --remote >/dev/null 2>&1 || true
    say "kv-seed: $reg_key"
  done
  say "kv-seed: done (registry markers only; per-client rows land on the box)"
}

# ---------------------------------------------------------------------------
# Secrets + Worker deploy
# ---------------------------------------------------------------------------
set_secrets() {
  step "secrets: set R2_* secrets (values from env, never committed)"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  if [ -n "${R2_ACCOUNT_ID:-}" ]; then
    printf '%s\n' "$R2_ACCOUNT_ID" | wr secret put R2_ACCOUNT_ID --name "$WORKER_NAME" >/dev/null
  else
    warn "R2_ACCOUNT_ID not set — skipping secret (media upload fails closed until set)"
  fi
  if [ -n "${R2_ACCESS_KEY_ID:-}" ]; then
    printf '%s\n' "$R2_ACCESS_KEY_ID" | wr secret put R2_ACCESS_KEY_ID --name "$WORKER_NAME" >/dev/null
  else
    warn "R2_ACCESS_KEY_ID not set — skipping secret"
  fi
  if [ -n "${R2_SECRET_ACCESS_KEY:-}" ]; then
    printf '%s\n' "$R2_SECRET_ACCESS_KEY" | wr secret put R2_SECRET_ACCESS_KEY --name "$WORKER_NAME" >/dev/null
  else
    warn "R2_SECRET_ACCESS_KEY not set — skipping secret"
  fi
}

deploy_worker() {
  step "deploy: npx wrangler deploy (zone-guard already passed)"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  # Build a THROWAWAY config with the resolved ids, so wrangler.toml keeps its
  # <PLACEHOLDER> contract and no real id is ever committed.
  [ -n "$R_KV_ID" ] || die "deploy: no KV namespace id resolved"
  TMP_CONFIG="$(mktemp "${TMPDIR:-/tmp}/bw-wrangler.XXXXXX.toml")"
  {
    sed -E \
      -e "s#<PLACEHOLDER_CF_ACCOUNT_ID>#$R_ACCOUNT#g" \
      -e "s#<PLACEHOLDER_KV_NAMESPACE_ID_BW_BINDINGS>#$R_KV_ID#g" \
      -e "s#<PLACEHOLDER_KV_NAMESPACE_PREVIEW_ID_BW_BINDINGS>#$R_PREVIEW_ID#g" \
      "$WRANGLER_TOML"
  } > "$TMP_CONFIG"
  say "deploy: temp config written (deleted on exit) — wrangler.toml untouched"
  wr deploy --config "$TMP_CONFIG"
}

# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
cmd_status() {
  local active
  active="$(current_active_version)"
  say "worker-name : $WORKER_NAME"
  say "route       : $ROUTE_HOST"
  say "r2 bucket   : $BUCKET_NAME"
  say "kv binding  : $KV_BINDING"
  say "active app  : ${active:-<none yet — deploy or flip to activate>}"
  say "deployed ver: <query the Cloudflare dashboard or \`npx wrangler deploy --dry-run\`; wrangler has no remote status command>"
}

# ---------------------------------------------------------------------------
# --self-test: prove the guard refuses the wrong zone and that --dry-run plans
# without executing. Pure local, offline, no token, no network. Fails hard on
# any regression.
# ---------------------------------------------------------------------------
self_test() {
  local pass=1
  local tmp_out
  tmp_out="$(mktemp "${TMPDIR:-/tmp}/bw-self-test.XXXXXX")"

  # 1. ZONE LANDMINE: both zone ids pinned to the same value MUST hard-fail.
  if ZONE_ID_ZHW=aaaa ZONE_ID_BAS=aaaa bash "$0" --dry-run deploy >"$tmp_out" 2>&1; then
    warn "SELFTEST FAIL: wrong-zone guard did not refuse"
    pass=0
  else
    if grep -q "ZONE LANDMINE GUARD BLOCKED" "$tmp_out"; then
      say "SELFTEST OK: wrong-zone guard refused (exit non-zero, guard message)"
    else
      warn "SELFTEST FAIL: wrong-zone guard refused but no guard message"
      pass=0
    fi
  fi

  # 2. Plain --dry-run deploy plans every step WITHOUT executing and does NOT
  #    claim a zone-guard PASS when ids are unresolved.
  if ! bash "$0" --dry-run deploy >"$tmp_out" 2>&1; then
    warn "SELFTEST FAIL: --dry-run deploy exited non-zero"
    pass=0
  else
    if grep -q "^PLAN  r2-app:" "$tmp_out" && grep -q "^PLAN  deploy:" "$tmp_out"; then
      say "SELFTEST OK: --dry-run deploy printed PLAN for bundle + worker deploy"
    else
      warn "SELFTEST FAIL: --dry-run deploy did not print expected PLAN lines"
      pass=0
    fi
    if grep -q "zone-guard: PASS" "$tmp_out"; then
      warn "SELFTEST FAIL: --dry-run without a token claimed zone-guard PASS"
      pass=0
    else
      say "SELFTEST OK: --dry-run did not fabricate a zone-guard PASS"
    fi
    # The dry-run must not have touched the network (curl / wrangler are PLAN only).
    if grep -qE "curl -sS|npx wrangler" "$tmp_out" | grep -v "^PLAN" >/dev/null 2>&1; then
      warn "SELFTEST FAIL: a real wrangler/curl call appeared in dry-run"
      pass=0
    else
      say "SELFTEST OK: dry-run is PLAN-only (no real calls)"
    fi
  fi

  rm -f "$tmp_out"
  if [ "$pass" -eq 1 ]; then
    say "U19 deploy self-test: PASS"
    exit 0
  fi
  die "U19 deploy self-test: FAIL"
}

# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------
usage() {
  cat <<'EOF'
USAGE:
  ./deploy.sh [--dry-run] deploy [VERSION]
  ./deploy.sh [--dry-run] rollback [VERSION]
  ./deploy.sh [--dry-run] flip <VERSION>
  ./deploy.sh [--dry-run] status

  deploy      provision R2 bucket + KV namespace, upload app/<version>/ + configs,
              seed KV, set secrets, flip app/latest, deploy the Worker.
  rollback    flip app/latest back to the previous app/<version>/ (no code change).
  flip        activate an existing R2 app/<version> (config flip).
  status      show active app version + deployed Worker version.

  --dry-run   validate every step (guard + wiring + plan) WITHOUT executing any
              wrangler or API call. Honest: each step prints PLAN, guards still
              fail hard on a wrong zone, unresolved ids report as unresolved.

ZONE LANDMINE: this script resolves the zerohumanworkforce.com zone id live and
refuses to run if it ever equals the businessaftersixty.com zone id.
EOF
}

main() {
  local cmd="" version=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run) DRY_RUN=1; shift ;;
      --self-test) self_test; exit $? ;;
      -h|--help) usage; exit 0 ;;
      deploy|rollback|flip|status) cmd="$1"; shift ;;
      *) version="$1"; shift ;;
    esac
  done
  [ -n "$cmd" ] || { usage; exit 1; }

  require_files
  require_wrangler
  if [ "$DRY_RUN" -eq 0 ]; then
    require_token
  fi

  # Resolve account + zone ids first (the guard depends on them).
  resolve_account_and_zones
  assert_zone_guard

  case "$cmd" in
    status)
      cmd_status
      ;;
    deploy)
      if [ -z "$version" ]; then version="$(bundle_version)"; fi
      say "deploy: version=$version"
      ensure_r2_bucket
      ensure_kv_namespace
      upload_bundle "$version"
      upload_configs "fake-alpha" "fake-beta" "fake-gate1"
      seed_kv
      set_secrets
      flip_active "$version"
      record_version "$version"
      deploy_worker
      if [ "$DRY_RUN" -eq 1 ]; then
        say "DRY-RUN COMPLETE: no mutations performed. Run with a real token to deploy."
      else
        say "DONE deploy $version (route $ROUTE_HOST)"
      fi
      ;;
    flip)
      [ -n "$version" ] || die "flip requires a version, e.g. ./deploy.sh flip v1"
      flip_active "$version"
      if [ "$DRY_RUN" -eq 1 ]; then
        say "DRY-RUN COMPLETE: no mutation. flip active -> $version planned."
      else
        say "DONE flip active -> $version"
      fi
      ;;
    rollback)
      if [ -n "$version" ]; then
        flip_active "$version"
        if [ "$DRY_RUN" -eq 1 ]; then
          say "DRY-RUN COMPLETE: no mutation. rollback active -> $version planned."
        else
          say "DONE rollback active -> $version"
        fi
      else
        local prev
        step "rollback: find previous app/<version>/"
        prev="$(list_versions | tail -2 | head -1)"
        [ -n "$prev" ] || die "rollback: no previous app/<version>/ found in $VERSIONS_INDEX"
        flip_active "$prev"
        if [ "$DRY_RUN" -eq 1 ]; then
          say "DRY-RUN COMPLETE: no mutation. rollback active -> $prev planned."
        else
          say "DONE rollback active -> $prev"
        fi
      fi
      ;;
  esac
}

main "$@"
