#!/usr/bin/env bash
# propagate-fleet-standing-gate.sh
#
# Seeds the FLEET STANDING GATE env vars onto every fleet box so the
# update-skills.sh chokepoint (FLEET-STANDING-GATE-V1) can consult the
# n8n standing webhook.
#
# Writes FOUR vars per box:
#   FLEET_STANDING_GATE_URL      same for all boxes
#   FLEET_STANDING_GATE_HEADER   same for all boxes
#   FLEET_STANDING_GATE_SECRET   same for all boxes (header-auth shared secret)
#   FLEET_STANDING_BOX_SLUG      PER BOX -- its own slug, the join key
#
# Targets, mirroring propagate-rescue-webhook.sh:
#   Mac : ~/.openclaw/secrets/.env  +  ~/.openclaw/openclaw.json env.vars
#   VPS : container /data/.openclaw/secrets/.env + openclaw.json env.vars
#
# SAFETY
#   - Client boxes get ONLY the narrow header secret. They NEVER get an n8n
#     API key: scoped keys are Enterprise-only, so an n8n API key would grant
#     full access to every workflow and credential on the instance.
#   - Backs up each file before modifying (.bak-pre-standing-gate-<UTC>).
#   - Idempotent: rewrites the four keys, leaves everything else alone.
#   - Unreachable box => SKIP and continue. Never blocks the run.
#   - NEVER echoes the secret value.
#   - No gateway restarts. Env is read fresh by update-skills.sh each run.
#
# Usage:
#   bash propagate-fleet-standing-gate.sh --dry-run          # show plan only
#   bash propagate-fleet-standing-gate.sh --only <slug>      # one box
#   bash propagate-fleet-standing-gate.sh                    # whole fleet
set -uo pipefail

REGISTRY="$HOME/clawd/fleet-prover/box-registry.json"
PROVER="$HOME/clawd/fleet-prover/fleet-roster.json"
SECRETS="$HOME/.openclaw/secrets/secrets.env"
DRY=0; ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    --only)    ONLY="${2:-}"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# shellcheck source=/dev/null
set -a; . "$SECRETS" 2>/dev/null; set +a
URL="${FLEET_STANDING_GATE_URL:-}"
HDR="${FLEET_STANDING_GATE_HEADER:-X-Fleet-Standing-Secret}"
SEC="${FLEET_STANDING_GATE_SECRET:-}"
[ -n "$URL" ] || { echo "FATAL: FLEET_STANDING_GATE_URL not set in $SECRETS" >&2; exit 2; }
[ -n "$SEC" ] || { echo "FATAL: FLEET_STANDING_GATE_SECRET not set in $SECRETS" >&2; exit 2; }

STAMP="$(date -u +%Y%m%d-%H%M%S)"
OK=0; SKIP=0; FAILED=0
declare -a OK_LIST=() SKIP_LIST=() FAIL_LIST=()

echo "=== fleet-standing-gate propagation ${STAMP} ==="
echo "  gate url : $URL"
echo "  header   : $HDR"
echo "  secret   : (length ${#SEC}, not printed)"
[ "$DRY" -eq 1 ] && echo "  MODE     : DRY RUN — nothing will be written"
echo

# Remote snippet: rewrite the 4 keys in an env file + openclaw.json env.vars.
# $1 oc_root  $2 slug
remote_script() {
cat <<'REMOTE'
set -u
OC_ROOT="$1"; SLUG="$2"; URL="$3"; HDR="$4"; SEC="$5"; STAMP="$6"
ENVF="$OC_ROOT/secrets/.env"
JSONF="$OC_ROOT/openclaw.json"
mkdir -p "$OC_ROOT/secrets" 2>/dev/null || true
[ -f "$ENVF" ] || : > "$ENVF"
cp "$ENVF" "$ENVF.bak-pre-standing-gate-$STAMP" 2>/dev/null || true
tmp="$(mktemp)"
grep -v -E '^(FLEET_STANDING_GATE_URL|FLEET_STANDING_GATE_HEADER|FLEET_STANDING_GATE_SECRET|FLEET_STANDING_BOX_SLUG)=' "$ENVF" > "$tmp" 2>/dev/null || true
{
  echo "FLEET_STANDING_GATE_URL=$URL"
  echo "FLEET_STANDING_GATE_HEADER=$HDR"
  echo "FLEET_STANDING_GATE_SECRET=$SEC"
  echo "FLEET_STANDING_BOX_SLUG=$SLUG"
} >> "$tmp"
mv "$tmp" "$ENVF"
chmod 600 "$ENVF" 2>/dev/null || true

if [ -f "$JSONF" ] && command -v python3 >/dev/null 2>&1; then
  cp "$JSONF" "$JSONF.bak-pre-standing-gate-$STAMP" 2>/dev/null || true
  python3 - "$JSONF" "$URL" "$HDR" "$SEC" "$SLUG" <<'PY'
import json,sys
p,url,hdr,sec,slug=sys.argv[1:6]
try:
    d=json.load(open(p))
except Exception as e:
    print("  json parse failed, env file still written:",e); raise SystemExit(0)
env=d.setdefault("env",{}); v=env.setdefault("vars",{})
v["FLEET_STANDING_GATE_URL"]=url
v["FLEET_STANDING_GATE_HEADER"]=hdr
v["FLEET_STANDING_GATE_SECRET"]=sec
v["FLEET_STANDING_BOX_SLUG"]=slug
json.dump(d,open(p,"w"),indent=2)
print("  openclaw.json env.vars updated")
PY
else
  echo "  openclaw.json absent or no python3 — env file only"
fi
echo "  OK $SLUG"
REMOTE
}

mapfile -t ROWS < <(python3 - "$REGISTRY" "$PROVER" <<'PY'
import json,sys
reg=json.load(open(sys.argv[1])); reg=reg.get("boxes",reg)
try:
    pro=json.load(open(sys.argv[2])); pro=pro.get("boxes",pro)
except Exception:
    pro={}
def prov(slug):
    if slug in pro: return pro[slug]
    bare=slug[len("rescue-"):] if slug.startswith("rescue-") else slug
    return pro.get(bare,{})
for slug,v in sorted(reg.items()):
    p=prov(slug)
    print("\t".join([slug, v.get("kind",""), p.get("ssh_target","") or "",
                     v.get("container","") or "", v.get("ssh_alias","") or ""]))
PY
)

for row in "${ROWS[@]}"; do
  IFS=$'\t' read -r SLUG KIND SSHT CONT ALIAS <<<"$row"
  [ -n "$ONLY" ] && [ "$SLUG" != "$ONLY" ] && continue

  case "$KIND" in
    local)
      echo "[$SLUG] operator box (local)"
      if [ "$DRY" -eq 1 ]; then echo "  would seed locally"; OK=$((OK+1)); OK_LIST+=("$SLUG"); continue; fi
      out="$(remote_script | bash -s -- "$HOME/.openclaw" "$SLUG" "$URL" "$HDR" "$SEC" "$STAMP" 2>&1)"
      rc=$?
      echo "$out" | sed 's/^/  /'
      if [ $rc -eq 0 ]; then OK=$((OK+1)); OK_LIST+=("$SLUG"); else FAILED=$((FAILED+1)); FAIL_LIST+=("$SLUG"); fi
      ;;
    vps)
      TGT="${SSHT:-}"
      if [ -z "$TGT" ] || [ -z "$CONT" ]; then
        echo "[$SLUG] VPS but no ssh_target/container in registry — SKIP"; SKIP=$((SKIP+1)); SKIP_LIST+=("$SLUG"); continue
      fi
      echo "[$SLUG] vps via $TGT (container $CONT)"
      if [ "$DRY" -eq 1 ]; then echo "  would seed /data/.openclaw"; OK=$((OK+1)); OK_LIST+=("$SLUG"); continue; fi
      out="$(remote_script | ssh -o ConnectTimeout=20 -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$TGT" \
             "docker exec -i -u node $CONT bash -s -- /data/.openclaw '$SLUG' '$URL' '$HDR' '$SEC' '$STAMP'" 2>&1)"
      rc=$?
      echo "$out" | sed 's/^/  /' | head -6
      if [ $rc -eq 0 ] && echo "$out" | grep -q "OK $SLUG"; then OK=$((OK+1)); OK_LIST+=("$SLUG")
      else echo "  UNREACHABLE or failed — SKIP"; SKIP=$((SKIP+1)); SKIP_LIST+=("$SLUG"); fi
      ;;
    mac|rescue_mac)
      TGT="${ALIAS:-$SSHT}"; [ -z "$TGT" ] && TGT="$SLUG"
      echo "[$SLUG] mac via $TGT"
      if [ "$DRY" -eq 1 ]; then echo "  would seed \$HOME/.openclaw"; OK=$((OK+1)); OK_LIST+=("$SLUG"); continue; fi
      out="$(remote_script | ssh -o ConnectTimeout=25 -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$TGT" \
             "bash -s -- \$HOME/.openclaw '$SLUG' '$URL' '$HDR' '$SEC' '$STAMP'" 2>&1)"
      rc=$?
      echo "$out" | sed 's/^/  /' | head -6
      if [ $rc -eq 0 ] && echo "$out" | grep -q "OK $SLUG"; then OK=$((OK+1)); OK_LIST+=("$SLUG")
      else echo "  UNREACHABLE or failed — SKIP"; SKIP=$((SKIP+1)); SKIP_LIST+=("$SLUG"); fi
      ;;
    *)
      echo "[$SLUG] unknown kind '$KIND' — SKIP"; SKIP=$((SKIP+1)); SKIP_LIST+=("$SLUG") ;;
  esac
done

echo
echo "=== SUMMARY ==="
echo "  seeded    : $OK"
echo "  skipped   : $SKIP"
echo "  failed    : $FAILED"
[ ${#SKIP_LIST[@]} -gt 0 ] && { echo "  SKIPPED:"; printf '    %s\n' "${SKIP_LIST[@]}"; }
[ ${#FAIL_LIST[@]} -gt 0 ] && { echo "  FAILED:";  printf '    %s\n' "${FAIL_LIST[@]}"; }
exit 0
