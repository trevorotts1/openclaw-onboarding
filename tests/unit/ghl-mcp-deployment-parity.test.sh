#!/usr/bin/env bash
# tests/unit/ghl-mcp-deployment-parity.test.sh — GHL-120 (W12 distribution)
#
# The community GHL MCP (`ghl-community-mcp`) is RETIRED. This suite proves that
# every distribution path carries the retirement and cannot restore the service:
#
#   onboarding (this repo) -> install.sh
#   onboarding (this repo) -> update-skills.sh -> installed client
#   onboarding (this repo) -> 999-setup front door -> installed client
#   container boot: Contabo + Hostinger start-up templates
#
# EVIDENCE LABELS (never conflated)
#   [STATIC]          source text / packaged bytes are inspected. Nothing is run.
#   [SIMULATED BOOT]  the dump-strip function is executed against a temp PM2_HOME
#                     with a synthetic dump.pm2. NO pm2/launchd/systemd daemon is
#                     started, signalled or stopped. This is NOT a restart test.
#
# NEGATIVE CONTROLS (each must flip the intended check, or the control is vacuous):
#   1. a deliberately reintroduced pm2 dump entry survives a mutation-disabled
#      strip -> the "no retired entry after the strip" assertion fails
#   2. a deliberately planted launchd plist is caught by the no-plist detector
#   3. a deliberately injected container autostart call is caught by the
#      no-autostart detector
#   Plus a packaged-copy parity control: one changed byte in a delivered copy
#   must be caught by the byte-parity check.
#
# Hermetic: all sandboxes are mktemp -d. No launchctl/pm2/systemctl/crontab and
# no network. `pm2` is never invoked (the strip function needs only node).
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CT="$REPO_ROOT/platform/vps/contabo/container-startup.sh"
HG="$REPO_ROOT/platform/vps/hostinger/container-startup.sh"
HG_HOOK="$REPO_ROOT/platform/vps/hostinger/install-startup-hook.sh"
PASS=0; FAIL=0; SKIP=0
ok()   { PASS=$((PASS+1)); printf '  PASS [%s] %s\n' "${2:-STATIC}" "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL [%s] %s\n' "${2:-STATIC}" "$1"; }
skip() { SKIP=$((SKIP+1)); printf '  SKIP %s\n' "$1"; }
TMP="$(mktemp -d "${TMPDIR:-/tmp}/ghl120-parity.XXXXXX")"; trap 'rm -rf "$TMP"' EXIT

# ── helpers ─────────────────────────────────────────────────────────────────
# Executable lines only: a leading-# comment is documentation, not a launch path.
exec_lines() { grep -vE '^[[:space:]]*#' "$1"; }

# extract_fn <file> <function-name> — prints one top-level bash function.
# Brace counting is safe here: the only braces inside these functions are the
# balanced blocks of the embedded node program.
extract_fn() {
  awk -v fn="$2" '
    $0 ~ "^" fn "\\(\\) \\{" { inside=1; depth=0; seen=0 }
    inside {
      print
      depth += gsub(/\{/, "{"); depth -= gsub(/\}/, "}")
      seen=1
      if (seen && depth == 0) exit
    }' "$1"
}

# parity <packaged> <template> — 0 when byte-identical, 1 on any drift.
parity() { cmp -s "$1" "$2"; }

# no_retired_launch <file> — 0 when no executable line can start the service.
no_retired_launch() {
  ! exec_lines "$1" | grep -Eq 'ghl-mcp-(autostart|probe)\.sh|mcp-servers/ghl-community-mcp|openclaw[[:space:]]+mcp[[:space:]]+(set|add)|GHL_COMMUNITY_MCP_URL|com\.clawd\.ghl-mcp|ghl-mcp\.service'
}

# plist_detector <root> — 0 when no retired launch surface is packaged there.
plist_detector() {
  ! find "$1" \( -name 'com.clawd.ghl-mcp*.plist' -o -name 'ghl-mcp.service' \) -print -quit 2>/dev/null | grep -q .
}

# autostart_detector <template> — 0 when the file cannot invoke the retired starter.
autostart_detector() { no_retired_launch "$1"; }

dump_names() {
  node -e 'const fs=require("fs");const l=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));process.stdout.write(l.map(x=>x&&x.name||"?").sort().join(","))' "$1"
}

run_strip() { # run_strip <template> <pm2home>  -> exit code of pm2_dump_excludes_retired
  local fnf="$TMP/fn.$$.sh"
  extract_fn "$1" pm2_dump_excludes_retired > "$fnf"
  [ -s "$fnf" ] || return 9
  PM2_HOME="$2" bash -c 'set -u; . "$1"; pm2_dump_excludes_retired' _ "$fnf"
}

# ── 1. [STATIC] container templates carry the retirement ────────────────────
if [ ! -f "$CT" ] || [ ! -f "$HG" ]; then
  bad "container-startup templates missing"
else
  for pair in "contabo:$CT" "hostinger:$HG"; do
    label="${pair%%:*}"; f="${pair#*:}"
    grep -q 'GHL_MCP_RETIRED' "$f" && ok "$label: template names the retirement" || bad "$label: no GHL_MCP_RETIRED marker"
    grep -q 'pm2_dump_excludes_retired' "$f" && ok "$label: template defines the dump strip" || bad "$label: no dump strip"
    if no_retired_launch "$f"; then ok "$label: no executable line starts or registers the retired service"; else bad "$label: an executable line can start/register the retired service"; fi
    # the strip must run BEFORE the resurrect (never launch then delete)
    ls_line="$(grep -n 'pm2_dump_excludes_retired; then' "$f" | head -1 | cut -d: -f1)"
    rs_line="$(grep -n 'pm2 resurrect' "$f" | grep -v '^[0-9]*:[[:space:]]*#' | head -1 | cut -d: -f1)"
    if [ -n "$ls_line" ] && [ -n "$rs_line" ] && [ "$ls_line" -lt "$rs_line" ]; then
      ok "$label: dump is stripped before pm2 resurrect (fail closed when unprovable)"
    else
      bad "$label: resurrect ordering not proven (strip=$ls_line resurrect=$rs_line)"
    fi
  done
fi

# No retired launch surface is packaged anywhere that is delivered.
if plist_detector "$REPO_ROOT/platform" && plist_detector "$REPO_ROOT/scripts" && plist_detector "$REPO_ROOT/config"; then
  ok "no launchd plist / systemd unit for the retired service is packaged"
else
  bad "a retired launchd plist or systemd unit is packaged"
fi

# The VPS starter is an inert tombstone, not a supervisor.
TOMB="$REPO_ROOT/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh"
if grep -q 'GHL_MCP_RETIRED=1' "$TOMB" && grep -q 'REFUSED' "$TOMB"; then
  ok "VPS start script is an inert tombstone (GHL_MCP_RETIRED=1, refuses)"
else
  bad "VPS start script does not carry the retirement"
fi

# ── 2. [STATIC] distribution + updater paths carry the prune ────────────────
INS="$REPO_ROOT/install.sh"; UPD="$REPO_ROOT/update-skills.sh"
INS_PRUNE="$(awk '/^# >>> GHL-MCP-RETIREMENT-SCRIPTS-BEGIN/,/^# <<< GHL-MCP-RETIREMENT-SCRIPTS-END/' "$INS")"
UPD_PRUNE="$(awk '/^# >>> GHL-MCP-RETIREMENT-PRUNE-BEGIN/,/^# <<< GHL-MCP-RETIREMENT-PRUNE-END/' "$UPD")"
if [ -n "$INS_PRUNE" ] && [ -n "$UPD_PRUNE" ]; then
  ok "both installers ship the retirement prune block"
else
  bad "a retirement prune anchor moved (install=$([ -n "$INS_PRUNE" ] && echo yes || echo no) updater=$([ -n "$UPD_PRUNE" ] && echo yes || echo no))"
fi
for fam in 'ghl-mcp-*.sh' 'qc-assert-ghl-mcp-supervised.sh' 'lib/ghl-mcp-paths.sh'; do
  if printf '%s\n' "$INS_PRUNE" | grep -qF "$fam" && printf '%s\n' "$UPD_PRUNE" | grep -qF "$fam"; then
    ok "prune parity: install.sh and update-skills.sh both remove $fam"
  else
    bad "prune drift: '$fam' is not removed by both installers"
  fi
done
printf '%s\n' "$UPD_PRUNE" | grep -q 'vps/36-ghl-mcp-setup-scripts/\*ghl-mcp\*\.sh' \
  && ok "updater also prunes the VPS retired start script from the delivered platform copy" \
  || bad "updater does not prune the VPS retired start script"

if exec_lines "$INS" | grep -Eq 'bash[^#]*ghl-mcp-autostart'; then
  bad "install.sh can invoke the retired launcher"
else
  ok "install.sh never invokes the retired launcher"
fi
if exec_lines "$UPD" | grep -E 'bash[[:space:]]+("\$AUTOSTART"|[^|#]*ghl-mcp-autostart\.sh)' | grep -vE -- '--retire|--status' | grep -q .; then
  bad "update-skills.sh invokes the retired launcher without --retire/--status"
else
  ok "update-skills.sh only invokes the retirement tool with --retire/--status"
fi
# The delivered destination is pruned, so the retirement tool must still be
# reachable from the freshly-pulled bundle (otherwise the roll cannot retire).
grep -q '"\$ONBOARDING_DIR/scripts/ghl-mcp-autostart.sh"' "$UPD" \
  && ok "updater resolves the retirement tool from the pulled bundle after the destination prune" \
  || bad "updater has no pulled-bundle retirement-tool resolver"

# Both installers delete a stale community pin (a live resurrection trigger).
for f in "$INS" "$UPD"; do
  grep -q 'rm -f "\$OC_CANONICAL_CONFIG_DEST/ghl-mcp-pin.env"' "$f" \
    && ok "$(basename "$f"): removes a stale config/ghl-mcp-pin.env from the destination" \
    || bad "$(basename "$f"): does not remove the stale community pin"
done

# 999 front door: refresh + link only; no GHL lifecycle anywhere.
FD="$REPO_ROOT/shared-utils/lib-frontdoor.sh"
if ! grep -qi 'ghl-mcp' "$FD"; then
  ok "999 front door (lib-frontdoor.sh) has no retired-service lifecycle path"
else
  bad "999 front door mentions the retired service"
fi
grep -q 'link_one_skill' "$FD" && grep -q -- '--skills-only' "$FD" \
  && ok "999 front door links skills / uses --skills-only only (never the full installer)" \
  || bad "999 front door is not provably link-only"
for f in "$REPO_ROOT/scripts/weekly-full-update.sh" "$REPO_ROOT/scripts/setup-weekly-update.sh" "$REPO_ROOT/force-update.sh"; do
  if grep -qi 'ghl-mcp' "$f"; then bad "$(basename "$f") reaches the retired service directly"; else ok "$(basename "$f") leaves retirement to update-skills.sh"; fi
done

# CI is a distribution path too: the guard is retirement-aware, never a starter.
WF="$REPO_ROOT/.github/workflows/ghl-mcp-supervised-guard.yml"
grep -q 'qc-assert-ghl-mcp-supervised.sh' "$WF" && grep -q 'ghl-mcp-assert-runtime.sh' "$WF" \
  && ok "CI runs the retirement-aware gates" \
  || bad "CI does not run the retirement-aware gates"
if grep -E '^[[:space:]]*run:' -A3 "$WF" | grep -E 'bash[^#]*ghl-mcp-autostart\.sh' | grep -vE -- '--retire|--status' | grep -q .; then
  bad "CI invokes the retired launcher without --retire/--status"
else
  ok "CI never starts the retired launcher"
fi

# Startup instructions must describe the retirement, not the old start.
grep -q 'never runs' "$REPO_ROOT/platform/vps/contabo/README.md" \
  && ok "contabo README says the boot path never runs the retired autostart" \
  || bad "contabo README still describes running the retired autostart"
grep -q 'RETIRED community GHL MCP is never restored' "$HG_HOOK" \
  && ok "Hostinger hook comment states the retired service is never restored" \
  || bad "Hostinger hook still implies the GHL MCP is resurrected"
grep -q 'RETIRED' "$REPO_ROOT/platform/README.md" \
  && ok "platform/README marks the community MCP retired on both platforms" \
  || bad "platform/README still documents a live GHL MCP start"
grep -q 'bash scripts/ghl-mcp-autostart.sh --retire' "$REPO_ROOT/scripts/qc-system-integrity.sh" \
  && ! grep -q 'regenerate the service definition' "$REPO_ROOT/scripts/qc-system-integrity.sh" \
  && ok "QC X.13b remediation is retirement-only (no regenerate/start advice)" \
  || bad "QC X.13b still tells the operator to regenerate the retired service"

# ── 3. [STATIC] packaged-copy byte parity (drift must be caught) ────────────
mk_box() {
  local box="$1"
  mkdir -p "$box/skills"
  cp -Rp "$REPO_ROOT/scripts" "$box/scripts" 2>/dev/null
  cp -Rp "$REPO_ROOT/platform" "$box/platform" 2>/dev/null
}
prune_box() { # mirror install.sh scripts prune + update-skills platform prune
  local box="$1" blk="$TMP/ins-prune.sh"
  awk '/^# >>> GHL-MCP-RETIREMENT-SCRIPTS-BEGIN/,/^# <<< GHL-MCP-RETIREMENT-SCRIPTS-END/' "$INS" > "$blk"
  SKILLS_DIR="$box/skills" bash -c 'note(){ :; }; . "$1"' _ "$blk" >/dev/null 2>&1
  extract_fn "$UPD" prune_retired_ghl_mcp_surfaces > "$TMP/upd-prune.sh"
  bash -c 'set -u; . "$1"; prune_retired_ghl_mcp_surfaces "$2" "$3"' _ "$TMP/upd-prune.sh" "$box/scripts" "$box/platform" >/dev/null 2>&1
}

BOX="$TMP/box"; mk_box "$BOX"; prune_box "$BOX"
for pair in "contabo:$CT:$BOX/platform/vps/contabo/container-startup.sh" \
            "hostinger:$HG:$BOX/platform/vps/hostinger/container-startup.sh"; do
  label="${pair%%:*}"; rest="${pair#*:}"; tpl="${rest%%:*}"; dst="${rest#*:}"
  if parity "$dst" "$tpl"; then
    ok "$label: delivered container-startup.sh is byte-identical to the template"
  else
    bad "$label: delivered copy drifted from the template"
  fi
done
if ! find "$BOX/scripts" -name 'ghl-mcp-*.sh' -o -name 'qc-assert-ghl-mcp-supervised.sh' 2>/dev/null | grep -q .; then
  ok "delivered scripts/ carries no retired supervision surface"
else
  bad "a retired supervision surface survived the delivered prune"
fi
[ ! -e "$BOX/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh" ] \
  && ok "delivered platform/ has no retired VPS start script" \
  || bad "delivered platform/ still carries the retired VPS start script"

# PARITY NEGATIVE CONTROL: one changed byte must be caught.
cp "$HG" "$TMP/hg-drift.sh"; printf '\n# drift\n' >> "$TMP/hg-drift.sh"
if parity "$TMP/hg-drift.sh" "$HG"; then
  bad "parity control VACUOUS: a changed packaged copy still compares equal"
else
  ok "parity control: a one-byte drift in a packaged copy is caught"
fi

# Hostinger host installer delivers the exact template.
PROJ="$TMP/proj"; mkdir -p "$PROJ"
printf 'services:\n  openclaw:\n    image: ghcr.io/hostinger/hvps-openclaw:latest\n    volumes:\n      - ./data:/data\n' > "$PROJ/docker-compose.yml"
mkdir -p "$TMP/bin"
printf '#!/bin/sh\nexit 0\n' > "$TMP/bin/docker"; chmod +x "$TMP/bin/docker"
if PATH="$TMP/bin:/usr/bin:/bin:/usr/sbin:/sbin" bash "$HG_HOOK" "$PROJ" >/dev/null 2>&1; then
  parity "$PROJ/data/.openclaw/scripts/container-startup.sh" "$HG" \
    && ok "Hostinger host installer installs the byte-identical template" \
    || bad "Hostinger host installer installed a drifted copy"
  printf '# drift\n' >> "$PROJ/data/.openclaw/scripts/container-startup.sh"
  parity "$PROJ/data/.openclaw/scripts/container-startup.sh" "$HG" \
    && bad "installed-copy parity control VACUOUS: drift still compares equal" \
    || ok "installed-copy parity control: drift in data/.openclaw/scripts is caught"
else
  bad "Hostinger host installer failed on a synthetic project"
fi

# Retirement tool must survive in the pulled bundle even after the destination prune.
PULLED="$TMP/pulled"; mkdir -p "$PULLED"; cp -Rp "$REPO_ROOT/scripts" "$PULLED/scripts"
DST="$TMP/dest-scripts"; cp -Rp "$REPO_ROOT/scripts" "$DST"
extract_fn "$UPD" prune_retired_ghl_mcp_surfaces > "$TMP/prune2.sh"
bash -c 'set -u; . "$1"; prune_retired_ghl_mcp_surfaces "$2" "$3"' _ "$TMP/prune2.sh" "$DST" "$TMP/no-platform" >/dev/null 2>&1
[ -f "$PULLED/scripts/ghl-mcp-autostart.sh" ] && [ ! -e "$DST/ghl-mcp-autostart.sh" ] \
  && ok "destination prune removes the launcher; the pulled bundle keeps the retirement tool" \
  || bad "prune removed the retirement tool from the pulled bundle (roll cannot retire)"

# ── 4. [SIMULATED BOOT] dump strip is load-bearing on both platforms ───────
if command -v node >/dev/null 2>&1; then
  for pair in "contabo:$CT" "hostinger:$HG"; do
    label="${pair%%:*}"; tpl="${pair#*:}"
    PM="$TMP/pm-$label"; mkdir -p "$PM"
    cat > "$PM/dump.pm2" <<'JSON'
[{"name":"blackceo-command-center","script":"ecosystem.config.cjs"},
 {"name":"ghl-community-mcp","script":"dist/main.js","pm_exec_path":"/data/mcp-servers/ghl-community-mcp/dist/main.js"}]
JSON
    rc=0; run_strip "$tpl" "$PM" >/dev/null 2>&1 || rc=$?
    names="$(dump_names "$PM/dump.pm2" 2>/dev/null || echo unreadable)"
    if [ "$rc" = 0 ] && [ "$names" = "blackceo-command-center" ]; then
      ok "$label: a reintroduced pm2 dump entry is stripped before resurrect (retired absent, Command Center kept)" "SIMULATED BOOT"
    else
      bad "$label: dump strip failed to remove the retired entry (rc=$rc names=$names)" "SIMULATED BOOT"
    fi

    # Fail closed on an unreadable dump (resurrect is skipped by the caller).
    printf 'not json' > "$PM/dump.pm2"
    rc=0; run_strip "$tpl" "$PM" >/dev/null 2>&1 || rc=$?
    [ "$rc" = 1 ] && ok "$label: unreadable dump -> strip returns 1 (caller skips resurrect)" "SIMULATED BOOT" \
                   || bad "$label: unreadable dump returned rc=$rc (expected 1)" "SIMULATED BOOT"

    # NEGATIVE CONTROL: disable the retired-entry match. The dump entry must
    # then survive, so the assertion above is proven load-bearing.
    MUT="$TMP/$label-mut.sh"
    python3 - "$tpl" "$MUT" <<'PY'
import sys
src, out = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()
needle = 'const hit = (s) => /ghl[-_]community[-_]mcp/.test(String(s || ""));'
assert needle in s, "strip matcher anchor moved"
open(out, "w", encoding="utf-8").write(s.replace(needle, 'const hit = () => false;'))
PY
    printf '%s\n' '[{"name":"ghl-community-mcp","script":"dist/main.js"}]' > "$PM/dump.pm2"
    rc=0; run_strip "$MUT" "$PM" >/dev/null 2>&1 || rc=$?
    names="$(dump_names "$PM/dump.pm2" 2>/dev/null || echo unreadable)"
    if [ "$rc" = 0 ] && [ "$names" = "ghl-community-mcp" ]; then
      ok "$label: NEGATIVE CONTROL — disabling the matcher lets the reintroduced entry survive (control flips)" "SIMULATED BOOT"
    else
      bad "$label: NEGATIVE CONTROL VACUOUS — entry did not survive a disabled matcher (rc=$rc names=$names)" "SIMULATED BOOT"
    fi
  done
else
  skip "node absent — dump-strip execution skipped"
fi

# ── 5. NEGATIVE CONTROL — launchd plist detector ────────────────────────────
PL="$TMP/plist-box"; mkdir -p "$PL/Library/LaunchAgents"
plist_detector "$PL" && ok "plist detector: a clean tree has no retired launch surface" || bad "plist detector false-positives on a clean tree"
printf '<plist/>\n' > "$PL/Library/LaunchAgents/com.clawd.ghl-mcp.plist"
plist_detector "$PL" && bad "NEGATIVE CONTROL VACUOUS — a planted launchd plist passed the detector" \
                     || ok "NEGATIVE CONTROL: a planted launchd plist fails the detector"
rm -f "$PL/Library/LaunchAgents/com.clawd.ghl-mcp.plist"
printf '<plist/>\n' > "$PL/Library/LaunchAgents/com.clawd.ghl-mcp-probe.plist"
plist_detector "$PL" && bad "NEGATIVE CONTROL VACUOUS — a planted probe plist passed the detector" \
                     || ok "NEGATIVE CONTROL: a planted probe plist fails the detector"
mkdir -p "$PL/etc/systemd/system"; printf '[Unit]\n' > "$PL/etc/systemd/system/ghl-mcp.service"
plist_detector "$PL" && bad "NEGATIVE CONTROL VACUOUS — a planted systemd unit passed the detector" \
                     || ok "NEGATIVE CONTROL: a planted systemd unit fails the detector"

# ── 6. NEGATIVE CONTROL — container autostart detector ─────────────────────
autostart_detector "$CT" && autostart_detector "$HG" \
  && ok "autostart detector: both shipped templates pass" \
  || bad "autostart detector false-positives on a shipped template"
INJ="$TMP/ct-injected.sh"; cp "$CT" "$INJ"
printf '\n# control injection\nbash "$OC/scripts/ghl-mcp-autostart.sh"\n' >> "$INJ"
autostart_detector "$INJ" && bad "NEGATIVE CONTROL VACUOUS — an injected autostart call passed the detector" \
                          || ok "NEGATIVE CONTROL: an injected container autostart call fails the detector"

printf '\n[ghl-mcp-deployment-parity] %d passed, %d failed, %d skipped\n' "$PASS" "$FAIL" "$SKIP"
[ "$FAIL" = 0 ]
