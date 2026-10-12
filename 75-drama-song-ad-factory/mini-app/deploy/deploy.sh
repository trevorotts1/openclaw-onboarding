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
#                       bucket, resolve/create the DS_STUDIO KV namespace, set
#                       45-day lifecycle retention on the project prefix, set the
#                       required secrets, deploy the Worker, ensure the proxied
#                       CNAME for the route host.
#     status            show the resolved config (no mutations).
#     --dry-run         validate + plan every step WITHOUT any wrangler or API
#                       call. Honest: each step prints PLAN, the guard still
#                       fails hard on a wrong zone, unresolved ids report as
#                       unresolved and never as a pass.
#     --self-test       offline proof (no token, no network): the guard refuses
#                       a wrong zone/account, --dry-run is PLAN-only, and each
#                       fixed deploy defect (absolute main, KV id, account
#                       resolution, required secrets, DNS) has a case.
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
SERVICE_ENTRY=""
KV_BINDING=""
KV_TITLE=""
SECRET_NAMES=""
REQUIRED_SECRET_NAMES=""
OPTIONAL_SECRET_NAMES=""
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
R_KV_ID=""
TMP_CONFIG=""
TMP_DIR=""

cleanup() {
  if [ -n "$TMP_CONFIG" ] && [ -f "$TMP_CONFIG" ]; then rm -f "$TMP_CONFIG"; fi
  if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then rmdir "$TMP_DIR" 2>/dev/null || true; fi
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
      service_entry)       SERVICE_ENTRY="$v" ;;
      kv_binding)          KV_BINDING="$v" ;;
      kv_title)            KV_TITLE="$v" ;;
      secrets)             SECRET_NAMES="$v" ;;
      secrets_required)    REQUIRED_SECRET_NAMES="$v" ;;
      secrets_optional)    OPTIONAL_SECRET_NAMES="$v" ;;
      wrangler_toml)       WRANGLER_TOML_REL="$v" ;;
      token_var)           TOKEN_VAR="$v" ;;
    esac
  done < <(node -e '
    const fs = require("fs");
    const m = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
    const secrets = m.secrets || [];
    const names = (arr) => arr.map(s => (s && s.name) || s).join(" ");
    const rows = [
      ["worker_name",        (m.worker && m.worker.name) || ""],
      ["route_host",         (m.worker && m.worker.route_host) || ""],
      ["bucket_name",        (m.bucket && m.bucket.name) || ""],
      ["retention_days",     String((m.bucket && m.bucket.retention_days) ?? "")],
      ["retention_prefix",   (m.bucket && m.bucket.retention_prefix) || ""],
      ["intended_zone_name", (m.cloudflare && m.cloudflare.intended_zone_name) || ""],
      ["service_home",       m.service_home || ""],
      ["service_entry",      (m.worker && m.worker.service_entry) || ""],
      ["kv_binding",         (m.worker && m.worker.kv_binding) || ""],
      ["kv_title",           (m.worker && m.worker.kv_title) || ""],
      ["secrets",            names(secrets)],
      ["secrets_required",   names(secrets.filter(s => s && s.required))],
      ["secrets_optional",   names(secrets.filter(s => s && !s.required))],
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

  # Zone id: resolve by NAME only when the operator did not supply one.
  if [ -z "$R_ZONE_ID" ]; then
    R_ZONE_ID="$(cf_api GET "/zones?name=$TARGET_ZONE_NAME&per_page=1" | json_field "result.0.id")"
  fi

  # Account id: resolved INDEPENDENTLY of the zone. A supplied STUDIO_ZONE_ID
  # must never skip account resolution — the live G4 guard needs a real account
  # id — so fetch the zone by id and read the account it belongs to. An empty
  # result is left empty, so G4 still fails hard.
  if [ -z "$R_ACCOUNT_ID" ] && [ -n "$R_ZONE_ID" ]; then
    R_ACCOUNT_ID="$(cf_api GET "/zones/$R_ZONE_ID" | json_field "result.0.account.id")"
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
# Guarded-zone re-check — used by the DNS step, which writes a record into a
# zone. It may only ever write into the guarded BlackCEO zone; it refuses any
# other zone NAME, the known foreign zone ID, and an unresolved zone id.
# ---------------------------------------------------------------------------
require_guarded_zone() {
  local who="$1"
  if [ -n "$TARGET_ZONE_NAME" ] && [ "$TARGET_ZONE_NAME" != "$INTENDED_ZONE_NAME" ]; then
    die "$who: refuse — target zone '$TARGET_ZONE_NAME' is not the guarded zone '$INTENDED_ZONE_NAME'"
  fi
  if [ -n "$FOREIGN_ZONE_ID" ] && [ -n "$R_ZONE_ID" ] && [ "$R_ZONE_ID" = "$FOREIGN_ZONE_ID" ]; then
    die "$who: refuse — target zone id is the known foreign zone id"
  fi
  if [ -z "$R_ZONE_ID" ]; then
    die "$who: refuse — no guarded zone id resolved (empty)"
  fi
}

# ---------------------------------------------------------------------------
# Provision: R2 bucket + KV namespace + 45-day project-object retention
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
# KV namespace: resolve DS_STUDIO by title, create it only if absent. Its id is
# resolved into the throwaway wrangler config so no <PLACEHOLDER_KV_*> id ever
# reaches wrangler.
# ---------------------------------------------------------------------------
ensure_kv_namespace() {
  step "kv-namespace: ensure '$KV_BINDING' exists (title '$KV_TITLE')"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  [ -n "$R_ACCOUNT_ID" ] || die "kv-namespace: no resolved account id — cannot resolve '$KV_BINDING'"
  local id
  # Find by title via the API (idempotent).
  id="$(cf_api GET "/accounts/$R_ACCOUNT_ID/storage/kv/namespaces?per_page=100" | node -e '
    let s = ""; process.stdin.on("data", d => s += d).on("end", () => {
      let j; try { j = JSON.parse(s); } catch { process.stdout.write(""); process.exit(0); }
      if (!j || !Array.isArray(j.result)) { process.stdout.write(""); process.exit(0); }
      const ns = j.result.find(n => n.title === process.argv[1]);
      process.stdout.write(ns ? (ns.id || "") : "");
    });
  ' "$KV_TITLE")"
  if [ -n "$id" ]; then
    R_KV_ID="$id"
    say "kv-namespace: '$KV_BINDING' already exists (id ${id:0:8}...)"
    return 0
  fi
  # Create only if absent.
  say "kv-namespace: creating '$KV_BINDING'"
  id="$(cf_api POST "/accounts/$R_ACCOUNT_ID/storage/kv/namespaces" \
        "$(node -e 'process.stdout.write(JSON.stringify({title: process.argv[1]}))' "$KV_TITLE")" \
      | json_field "result.id")"
  [ -n "$id" ] || die "kv-namespace: could not resolve a namespace id for '$KV_BINDING' (empty)"
  R_KV_ID="$id"
  say "kv-namespace: created '$KV_BINDING' (id ${id:0:8}...)"
}

# ---------------------------------------------------------------------------
# DNS: ensure a PROXIED CNAME for the route host exists in the GUARDED zone,
# creating it only if absent. Refuses any zone but the guarded one.
# ---------------------------------------------------------------------------
ensure_dns() {
  step "dns: ensure proxied CNAME $ROUTE_HOST -> $INTENDED_ZONE_NAME (guarded zone only)"
  if [ "$DRY_RUN" -eq 1 ]; then
    # No write in dry-run; a wrong zone NAME is still refused, never planned.
    if [ -n "$TARGET_ZONE_NAME" ] && [ "$TARGET_ZONE_NAME" != "$INTENDED_ZONE_NAME" ]; then
      die "dns: refuse — target zone '$TARGET_ZONE_NAME' is not the guarded zone '$INTENDED_ZONE_NAME'"
    fi
    return 0
  fi
  # Hard gate: this step writes only into the guarded BlackCEO zone.
  require_guarded_zone "dns"
  local existing
  existing="$(cf_api GET "/zones/$R_ZONE_ID/dns_records?type=CNAME&name=$ROUTE_HOST&per_page=1" \
              | json_field "result.0.id")"
  if [ -n "$existing" ]; then
    say "dns: CNAME $ROUTE_HOST already exists — skipping create"
    return 0
  fi
  local body
  body="$(node -e 'process.stdout.write(JSON.stringify({type:"CNAME",name:process.argv[1],content:process.argv[2],proxied:true}))' \
          "$ROUTE_HOST" "$INTENDED_ZONE_NAME")"
  cf_api POST "/zones/$R_ZONE_ID/dns_records" "$body" >/dev/null
  say "dns: created proxied CNAME $ROUTE_HOST -> $INTENDED_ZONE_NAME"
}

# ---------------------------------------------------------------------------
# Secrets (values from env, never echoed) + Worker deploy
# ---------------------------------------------------------------------------
set_secrets() {
  step "secrets: set (required) $REQUIRED_SECRET_NAMES (values from env, never echoed)"
  step "secrets: set (optional) $OPTIONAL_SECRET_NAMES (values from env, never echoed)"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  local name val
  # Required secrets (the service README bindings). A missing one FAILS the
  # deploy — the Worker fails closed without them.
  for name in $REQUIRED_SECRET_NAMES; do
    val="${!name:-}"
    if [ -z "$val" ]; then
      die "secrets: required secret $name is not set in the environment (source the operator env file); no value is ever printed"
    fi
    printf '%s\n' "$val" | wr secret put "$name" --name "$WORKER_NAME" >/dev/null
    say "secret $name: set (value never echoed)"
    unset val
  done
  # Optional secrets: the R2 S3 presign keys are deferred until presign ships
  # (the service does not read them at runtime). They stay optional so their
  # absence never fails the deploy.
  for name in $OPTIONAL_SECRET_NAMES; do
    val="${!name:-}"
    if [ -z "$val" ]; then
      warn "secret $name not set in env — optional, skipping (R2 S3 presign keys are deferred until presign ships)"
      continue
    fi
    printf '%s\n' "$val" | wr secret put "$name" --name "$WORKER_NAME" >/dev/null
    say "secret $name: set (value never echoed)"
    unset val
  done
}

# Build the THROWAWAY wrangler config from the committed toml. The toml keeps
# every real id as <PLACEHOLDER>; here they are resolved, and — because the
# config is written into $TMPDIR — the `main` entrypoint is rewritten to the
# ABSOLUTE path of the service entrypoint, so wrangler can find it regardless
# of the config file's directory. Pure text transform: no network, no wrangler.
#   write_resolved_config <src_toml> <dst_toml> <account_id> <kv_id> <main_abs>
write_resolved_config() {
  local src="$1" dst="$2" acct="$3" kv="$4" main_abs="$5"
  [ -f "$src" ] || die "config: missing $src"
  sed -E \
    -e "s#<PLACEHOLDER_CF_ACCOUNT_ID>#${acct}#g" \
    -e "s#<PLACEHOLDER_KV_NAMESPACE_ID_DS_STUDIO>#${kv}#g" \
    -e "s#<PLACEHOLDER_KV_NAMESPACE_PREVIEW_ID_DS_STUDIO>#${kv}#g" \
    -e "s#^(main[[:space:]]*=[[:space:]]*).*#\1\"${main_abs}\"#" \
    "$src" > "$dst"
}

deploy_worker() {
  step "deploy: npx wrangler deploy (zone-guard already passed)"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  local worker_toml="$MINI_APP_DIR/$WRANGLER_TOML_REL"
  [ -f "$worker_toml" ] || die "deploy: missing $worker_toml"
  [ -n "$R_KV_ID" ] || die "deploy: no KV namespace id resolved for '$KV_BINDING'"
  local main_abs="$MINI_APP_DIR/$SERVICE_ENTRY"
  [ -f "$main_abs" ] || die "deploy: service entrypoint $main_abs not found (U2 service contract)"
  # BSD mktemp substitutes only TRAILING X's, so make a temp DIR and write a
  # config named wrangler.toml inside it (wrangler keys format off the .toml
  # extension). A literal "…XXXXXX.toml" would collide on the second deploy.
  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/studio-wrangler.XXXXXX")"
  TMP_CONFIG="$TMP_DIR/wrangler.toml"
  # Resolve <PLACEHOLDER> ids AND make `main` absolute; the toml is untouched.
  write_resolved_config "$worker_toml" "$TMP_CONFIG" "$R_ACCOUNT_ID" "$R_KV_ID" "$main_abs"
  say "deploy: temp config written (main + ids resolved; deleted on exit) — $WRANGLER_TOML_REL untouched"
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

  # ── DEPLOY-FIX: one case per fixed deploy defect (RED without its fix) ─────

  # F1: deploy_worker's temp config must carry an ABSOLUTE `main`. The temp
  #     config is written into $TMPDIR, so the committed relative main could
  #     not resolve ("entry-point file at \"src/index.js\" was not found").
  local fcfg; fcfg="$(mktemp "${TMPDIR:-/tmp}/studio-f1.XXXXXX")"
  write_resolved_config "$MINI_APP_DIR/$WRANGLER_TOML_REL" "$fcfg" \
    "acct-selftest" "kv-selftest" "$MINI_APP_DIR/service/src/index.js" 2>/dev/null || true
  if grep -qE "^main[[:space:]]*=[[:space:]]*\"$MINI_APP_DIR/service/src/index.js\"" "$fcfg"; then
    say "SELFTEST OK (F1): temp config main is the absolute service entrypoint"
  else
    warn "SELFTEST FAIL (F1): temp config main is not the absolute service entrypoint"
    pass=0
  fi
  rm -f "$fcfg"

  # F3: the KV namespace id must be resolved INTO the config with no
  #     <PLACEHOLDER> left for wrangler to choke on.
  local kcfg; kcfg="$(mktemp "${TMPDIR:-/tmp}/studio-f3.XXXXXX")"
  write_resolved_config "$MINI_APP_DIR/$WRANGLER_TOML_REL" "$kcfg" \
    "acct-selftest" "kv-selftest" "$MINI_APP_DIR/service/src/index.js" 2>/dev/null || true
  if grep -qE '<PLACEHOLDER_[A-Z0-9_]+>' "$kcfg"; then
    warn "SELFTEST FAIL (F3): a <PLACEHOLDER_id> survived into the config"
    pass=0
  elif grep -qE "^[[:space:]]*id[[:space:]]*=[[:space:]]*\"kv-selftest\"" "$kcfg"; then
    say "SELFTEST OK (F3): KV namespace id resolved into the config, no placeholder left"
  else
    warn "SELFTEST FAIL (F3): KV namespace id not resolved into the config"
    pass=0
  fi
  rm -f "$kcfg"

  # F3b: ensure_kv_namespace resolves an EXISTING namespace by title (no create).
  _t_f3_existing() {
    cf_api() { printf '{"success":true,"result":[{"title":"DS_STUDIO","id":"kv-existing-id"}]}'; }
    DRY_RUN=0; R_ACCOUNT_ID="acct"; KV_BINDING="DS_STUDIO"; KV_TITLE="DS_STUDIO"; R_KV_ID=""
    ensure_kv_namespace >/dev/null 2>&1
    printf '%s' "$R_KV_ID"
  }
  if [ "$( ( _t_f3_existing ) 2>/dev/null )" = "kv-existing-id" ]; then
    say "SELFTEST OK (F3): ensure_kv_namespace finds an existing DS_STUDIO by title"
  else
    warn "SELFTEST FAIL (F3): ensure_kv_namespace did not resolve the existing namespace"
    pass=0
  fi

  # F3c: ensure_kv_namespace CREATES the namespace only when absent.
  _t_f3_create() {
    cf_api() { case "$1" in
      GET)  printf '{"result":[]}' ;;
      POST) printf '{"result":{"id":"kv-created-id"}}' ;;
    esac; }
    DRY_RUN=0; R_ACCOUNT_ID="acct"; KV_BINDING="DS_STUDIO"; KV_TITLE="DS_STUDIO"; R_KV_ID=""
    ensure_kv_namespace >/dev/null 2>&1
    printf '%s' "$R_KV_ID"
  }
  if [ "$( ( _t_f3_create ) 2>/dev/null )" = "kv-created-id" ]; then
    say "SELFTEST OK (F3): ensure_kv_namespace creates DS_STUDIO only when absent"
  else
    warn "SELFTEST FAIL (F3): ensure_kv_namespace did not create/parse the namespace id"
    pass=0
  fi

  # F2: a supplied STUDIO_ZONE_ID must still resolve the account — the live G4
  #     guard needs a real account id. Stub the API; assert the account.
  _t_f2() {
    cf_api() { printf '{"result":[{"id":"zone-xyz","account":{"id":"acct-live"}}]}'; }
    DRY_RUN=0; R_ZONE_ID=""; R_ACCOUNT_ID=""
    TARGET_ZONE_ID="zone-xyz"; TARGET_ACCOUNT_ID=""; TARGET_ZONE_NAME="zerohumanworkforce.com"
    TOKEN_VAR="SELFTEST_DUMMY_VAR"
    resolve_account_and_zone >/dev/null 2>&1
    printf '%s' "$R_ACCOUNT_ID"
  }
  if [ "$( ( _t_f2 ) 2>/dev/null )" = "acct-live" ]; then
    say "SELFTEST OK (F2): account resolved even though STUDIO_ZONE_ID was supplied"
  else
    warn "SELFTEST FAIL (F2): a supplied STUDIO_ZONE_ID skipped account resolution"
    pass=0
  fi

  # F4: the service secret NAMES (DS_ENROLLMENT_SECRET, DS_ADMIN_KEY,
  #     R2_ACCOUNT_ID) come from the manifest's required list; a missing
  #     REQUIRED secret fails the deploy; a missing OPTIONAL one only warns.
  _t_has() { case " $1 " in *" $2 "*) return 0 ;; *) return 1 ;; esac; }
  if _t_has "$REQUIRED_SECRET_NAMES" "DS_ENROLLMENT_SECRET" \
     && _t_has "$REQUIRED_SECRET_NAMES" "DS_ADMIN_KEY" \
     && _t_has "$REQUIRED_SECRET_NAMES" "R2_ACCOUNT_ID"; then
    say "SELFTEST OK (F4): the service secret names are in the manifest's required list"
  else
    warn "SELFTEST FAIL (F4): DS_ENROLLMENT_SECRET / DS_ADMIN_KEY / R2_ACCOUNT_ID missing from the required secrets"
    pass=0
  fi
  _t_f4_required_missing() {
    DRY_RUN=0; WORKER_NAME="w"; REQUIRED_SECRET_NAMES="ST_REQ_MISSING"; OPTIONAL_SECRET_NAMES=""
    set_secrets
  }
  if ( _t_f4_required_missing ) >"$out" 2>&1; then
    warn "SELFTEST FAIL (F4): a missing required secret did not fail the deploy"
    pass=0
  elif grep -q "required secret ST_REQ_MISSING" "$out"; then
    say "SELFTEST OK (F4): a missing required secret fails the deploy (fail closed, no value printed)"
  else
    warn "SELFTEST FAIL (F4): required-secret failure not detected"
    pass=0
  fi
  _t_f4_optional_missing() {
    DRY_RUN=0; WORKER_NAME="w"; REQUIRED_SECRET_NAMES=""; OPTIONAL_SECRET_NAMES="ST_OPT_MISSING"
    wr() { return 0; }
    set_secrets
  }
  if ( _t_f4_optional_missing ) >"$out" 2>&1; then
    say "SELFTEST OK (F4): a missing OPTIONAL secret (R2 S3) does not fail the deploy"
  else
    warn "SELFTEST FAIL (F4): a missing optional secret failed the deploy"
    pass=0
  fi

  # F5: the DNS step refuses any zone but the guarded one, creates the proxied
  #     CNAME only when absent, and skips when it already exists.
  _t_f5_refuse() {
    DRY_RUN=0; R_ZONE_ID="zone-xyz"; FOREIGN_ZONE_ID=""
    TARGET_ZONE_NAME="elsewhere.example"; INTENDED_ZONE_NAME="zerohumanworkforce.com"
    ROUTE_HOST="studio.zerohumanworkforce.com"; R_ACCOUNT_ID="acct"
    ensure_dns
  }
  if ( _t_f5_refuse ) >"$out" 2>&1; then
    warn "SELFTEST FAIL (F5): the DNS step did not refuse a non-guarded zone"
    pass=0
  elif grep -q "dns: refuse" "$out"; then
    say "SELFTEST OK (F5): the DNS step refuses any zone but the guarded one"
  else
    warn "SELFTEST FAIL (F5): zone refusal not detected"
    pass=0
  fi
  local dnsbody; dnsbody="$(mktemp "${TMPDIR:-/tmp}/studio-f5.XXXXXX")"
  _t_f5_create() {
    cf_api() { case "$1" in
      GET)  printf '{"result":[]}' ;;
      POST) printf '%s' "$3" > "$ST_DNS_BODY_FILE"; printf '{"result":{"id":"rec-new"}}' ;;
    esac; }
    DRY_RUN=0; R_ZONE_ID="zone-xyz"; FOREIGN_ZONE_ID=""
    TARGET_ZONE_NAME="zerohumanworkforce.com"; INTENDED_ZONE_NAME="zerohumanworkforce.com"
    ROUTE_HOST="studio.zerohumanworkforce.com"; R_ACCOUNT_ID="acct"
    ensure_dns
  }
  ST_DNS_BODY_FILE="$dnsbody"
  if ( _t_f5_create ) >"$out" 2>&1 \
     && grep -q '"proxied":true' "$dnsbody" \
     && grep -q 'studio.zerohumanworkforce.com' "$dnsbody"; then
    say "SELFTEST OK (F5): the DNS step creates a proxied CNAME for the route host when absent"
  else
    warn "SELFTEST FAIL (F5): the DNS step did not create the proxied CNAME body"
    pass=0
  fi
  rm -f "$dnsbody"
  _t_f5_skip() {
    cf_api() { printf '{"result":[{"id":"rec-existing"}]}'; }
    DRY_RUN=0; R_ZONE_ID="zone-xyz"; FOREIGN_ZONE_ID=""
    TARGET_ZONE_NAME="zerohumanworkforce.com"; INTENDED_ZONE_NAME="zerohumanworkforce.com"
    ROUTE_HOST="studio.zerohumanworkforce.com"; R_ACCOUNT_ID="acct"
    ensure_dns
  }
  if ( _t_f5_skip ) >"$out" 2>&1 && grep -q "already exists" "$out"; then
    say "SELFTEST OK (F5): the DNS step skips when the CNAME already exists"
  else
    warn "SELFTEST FAIL (F5): the DNS step did not skip an existing CNAME"
    pass=0
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
      ensure_kv_namespace
      set_secrets
      deploy_worker
      ensure_dns
      if [ "$DRY_RUN" -eq 1 ]; then
        say "DRY-RUN COMPLETE: no mutations performed. No deploy happened."
      else
        say "DONE deploy (route $ROUTE_HOST)"
      fi
      ;;
  esac
}

main "$@"
