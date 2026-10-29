#!/usr/bin/env bash
# Node-floor test for scripts/self-update.sh. OpenClaw 2026.10.6+ refuses every
# command on a Node below its engines.node, so the job must bring the Node the
# gateway LaunchAgent runs up to the floor BEFORE the OpenClaw upgrade step.
# Runs the REAL script (and the REAL oc-supervisor-install.py) in a throwaway
# HOME/OPENCLAW_ROOT with stub npm, curl, git and uname, a fixture LaunchAgent,
# fixture node binaries and a fixture install-cli.sh. Nothing leaves this machine;
# the real ~/.openclaw, Node and LaunchAgents are never read or written.
#
# Covers:
#   A  Node 26.8.1 < 26.12.1   -> same line (26.12.1) installed under <root>/tools/cli-node by
#                                 OpenClaw's installer (argv + clean env asserted); ONLY the plist's
#                                 node argument changes; the old node file is untouched; the
#                                 atomic upgrade then runs with the new Node first on PATH and
#                                 in the plist; node_before/node_after in the status file
#   B  Node 24.21.0            -> 24.22.1 (same line)
#   C  Node 22.14.0            -> 24.22.1 (lowest compatible even line)
#   D  Node 26.12.3 already ok -> nothing downloaded, plist byte-identical, upgrade runs
#   E  installer fails midway  -> box exactly as found, upgrade NOT run, exit 25, stuck_reason
#   F  installer installs a Node that is still below the floor -> same
#   G  npm view fails          -> nothing touched, upgrade NOT run
#   H  engines.node is a caret range this job cannot read -> refuses, nothing touched
#   I  no gateway LaunchAgent  -> step skipped, not recorded, upgrade runs (old behavior)
#   J  plist cannot be written -> installed Node removed again, plist unchanged, upgrade NOT run
#   K  private runtime already installed and satisfying -> reused, installer not run
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../self-update.sh"
[ -f "$SRC" ] || { echo "FAIL: $SRC not found" >&2; exit 1; }
[ -f "$HERE/../oc-supervisor-install.py" ] || { echo "FAIL: oc-supervisor-install.py not found" >&2; exit 1; }
PY="python3 -I"
ENGINE_OK='>=24.22.1 <25 || >=26.12.1'

T="$(mktemp -d "${TMPDIR:-/tmp}/self-update-node-floor.XXXXXX")" || exit 1
trap 'chmod -R u+rwX "$T" 2>/dev/null; [ -n "${KEEP:-}" ] || rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/fix" "$T/tmp"
fail=0
ok()  { echo "ok - $*"; }
bad() { echo "FAIL - $*"; fail=1; }

# ── stubs ────────────────────────────────────────────────────────────────────
cat > "$T/bin/curl" <<'EOF'
#!/usr/bin/env bash
[ "$1" = "--version" ] && { echo "curl 8.0.0"; exit 0; }
url=""; dest=""; wfmt=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) dest="$2"; shift 2 ;;
    -w) wfmt="$2"; shift 2 ;;
    --max-time|-m) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
case "$url" in
  */healthz) [ -n "$wfmt" ] && printf '200'; exit 0 ;;
  */api/health) exit 0 ;;
esac
[ -n "$url" ] && [ -n "$dest" ] || exit 2
src="$FIXTURES/$(basename "$url")"
[ -f "$src" ] || { echo "curl-stub: no fixture for $(basename "$url")" >&2; exit 22; }
cp "$src" "$dest"
EOF

REAL_GIT="$(command -v git)"; export REAL_GIT
cat > "$T/bin/git" <<'EOF'
#!/usr/bin/env bash
if [ "$1" = "--version" ]; then echo "git version 2.0"; exit 0; fi
if [ "$1" = "clone" ]; then echo "git-stub: clone refused in tests" >&2; exit 1; fi
exec "$REAL_GIT" "$@"
EOF

# Linux: the 999 and 9router steps are Mac-only, so the job goes straight to the upgrade step.
printf '%s\n' '#!/usr/bin/env bash' 'case "$1" in -s) echo Linux ;; -m) echo x86_64 ;; *) echo Linux ;; esac' > "$T/bin/uname"

# npm: `view` answers engines.node from NPM_ENGINE (or fails); `pack` builds a tarball that carries the
# fixture installer at package/scripts/install-cli.sh, as the real openclaw package does.
cat > "$T/bin/npm" <<'EOF'
#!/usr/bin/env bash
echo "npm $*" >> "$NPM_LOG"
case "$1" in
  view)
    [ "${NPM_VIEW_RC:-0}" = 0 ] || { echo "npm ERR! network" >&2; exit "$NPM_VIEW_RC"; }
    printf '%s\n' "${NPM_ENGINE:-}"; exit 0 ;;
  pack)
    dest=""; while [ "$#" -gt 0 ]; do [ "$1" = "--pack-destination" ] && dest="$2"; shift; done
    w="$(mktemp -d "${TMPDIR:-/tmp}/npmpack.XXXXXX")"
    mkdir -p "$w/package/scripts"; cp "$INSTALLER_SRC" "$w/package/scripts/install-cli.sh"
    echo "# shared policy (the real install-cli.sh sources it)" > "$w/package/scripts/install-policy.sh"
    tar -czf "$dest/openclaw-fixture.tgz" -C "$w" package; rm -rf "$w"
    echo "openclaw-fixture.tgz"; exit 0 ;;
esac
exit 0
EOF
chmod 700 "$T/bin/"*

# The fixture installer. Paths are baked in because the real call runs it under `env -i`.
mk_installer() {  # mode: ok | fail | wrong
  cat > "$T/installer.sh" <<EOF
#!/usr/bin/env bash
[ -s "\${BASH_SOURCE[0]%/*}/install-policy.sh" ] || { echo "installer: sibling install-policy.sh missing" >&2; exit 3; }
echo "argv: \$*" >> "$T/install.log"
echo "env: \$(env | grep -c '^OPENCLAW_' || true) \$(env | grep -c '^FIXTURES=' || true)" >> "$T/install.log"
prefix=""; ver=""
while [ "\$#" -gt 0 ]; do
  case "\$1" in --prefix) prefix="\$2"; shift 2 ;; --node-version) ver="\$2"; shift 2 ;; *) shift ;; esac
done
mkdir -p "\$prefix/tools/node-v\$ver/bin"
if [ "$1" = fail ]; then echo "installer: sha256 mismatch" >&2; exit 1; fi
shown="\$ver"; [ "$1" = wrong ] && shown="22.0.0"
printf '%s\n' '#!/bin/sh' "echo v\$shown" > "\$prefix/tools/node-v\$ver/bin/node"
chmod 755 "\$prefix/tools/node-v\$ver/bin/node"
ln -sfn "node-v\$ver" "\$prefix/tools/node"
exit 0
EOF
  INSTALLER_SRC="$T/installer.sh"; export INSTALLER_SRC
}

printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/fix/oc-schema-migrate.py"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/fix/weekly-full-update.sh"
# Records what the atomic upgrade would have seen: the node the plist names (through the real
# resolver, copied next to it by the job), the head of PATH, and the node PATH resolves.
cat > "$T/fix/oc-atomic-upgrade.sh" <<'EOF'
#!/usr/bin/env bash
{ echo "ran $*"
  echo "plist_node=$(python3 "$(dirname "$0")/oc-supervisor-install.py" node)"
  echo "path_head=${PATH%%:*}"
  echo "path_node=$(command -v node)"; } >> "$ATOMIC_LOG"
exit "${ATOMIC_RC:-0}"
EOF
chmod 700 "$T/fix/"*

SECRET="s3cr3t-probe-value-8841"

mkbox() {  # case_dir node_version [with_plist=1]
  C="$1"; NV="$2"; WITH_PLIST="${3:-1}"
  mkdir -p "$C/home/Library/LaunchAgents" "$C/root/skills" "$C/root/secrets" "$C/oldnode/bin" \
           "$C/npm/lib/node_modules/openclaw/dist" "$C/home/.local/bin"
  # The job puts $HOME/.local/bin (and /usr/local/bin, /opt/homebrew/bin) in front of PATH when they
  # are missing from it; the stubs live in the first of those so a real npm or curl can never win.
  cp "$T/bin/"* "$C/home/.local/bin/"
  printf 'v78.0.0\n' > "$C/root/skills/.onboarding-version"
  printf '{"name":"openclaw","version":"2026.10.4"}\n' > "$C/npm/lib/node_modules/openclaw/package.json"
  : > "$C/npm/lib/node_modules/openclaw/dist/index.js"
  printf '%s\n' '#!/bin/sh' "echo v$NV" > "$C/oldnode/bin/node"; chmod 755 "$C/oldnode/bin/node"
  if [ "$WITH_PLIST" = 1 ]; then
    P="$C/home/Library/LaunchAgents/ai.openclaw.gateway.plist"
    $PY - "$P" "$C/oldnode/bin/node" "$C/npm/lib/node_modules/openclaw/dist/index.js" "$SECRET" <<'PYEOF'
import plistlib, sys
p, node, entry, secret = sys.argv[1:5]
plistlib.dump({"Label": "ai.openclaw.gateway", "KeepAlive": True,
               "ProgramArguments": ["/bin/sh", "/x/ai.openclaw.gateway-env-wrapper.sh", "/x/ai.openclaw.gateway.env",
                                    node, entry, "gateway", "--port", "18789"],
               "EnvironmentVariables": {"OPENCLAW_GATEWAY_TOKEN": secret}}, open(p, "wb"))
PYEOF
    chmod 644 "$P"; cp -p "$P" "$C/plist.orig"
  fi
  : > "$C/atomic.log"; : > "$C/npm.log"; : > "$T/install.log"
}

run_job() {  # case_dir -> exit code of the job
  C="$1"
  PATH="$T/bin:$PATH" HOME="$C/home" OPENCLAW_ROOT="$C/root" FIXTURES="$T/fix" TMPDIR="$T/tmp" \
    ATOMIC_LOG="$C/atomic.log" NPM_LOG="$C/npm.log" \
    bash "$SRC" --roll-id "roll-${C##*/}" --openclaw-target 2026.10.8 --foreground > "$C/out.txt" 2>&1
  echo $?
}

st() { $PY -c '
import json, sys
d = json.load(open(sys.argv[1])); v = d.get(sys.argv[2], "")
print(json.dumps(v, sort_keys=True) if isinstance(v, dict) else v)' "$1/root/fleet-refresh/agent-pull-status.json" "$2" 2>/dev/null; }

plist_node() { $PY -c 'import plistlib,sys;print(plistlib.load(open(sys.argv[1],"rb"))["ProgramArguments"][3])' "$1/home/Library/LaunchAgents/ai.openclaw.gateway.plist"; }
untouched() {  # case_dir: plist byte-identical, no private runtime, no node-floor dir, old node file intact
  cmp -s "$1/plist.orig" "$1/home/Library/LaunchAgents/ai.openclaw.gateway.plist" \
    && [ ! -e "$1/root/tools" ] && [ ! -e "$1/root/node-floor" ] \
    && [ "$(cat "$1/oldnode/bin/node")" = "$(printf '#!/bin/sh\necho v%s' "$2")" ]
}
ran_upgrade() { grep -q '^ran --upgrade --target-version 2026.10.8' "$1/atomic.log"; }
no_secret() { ! grep -rqF "$SECRET" "$1/out.txt" "$1/root/self-update" "$1/root/fleet-refresh/agent-pull-status.json" 2>/dev/null; }

export NPM_ENGINE="$ENGINE_OK"

# ── A: 26.8.1 -> 26.12.1, same line ──────────────────────────────────────────
echo "# A"
mk_installer ok; NPM_ENGINE="$ENGINE_OK"; unset NPM_VIEW_RC
mkbox "$T/A" 26.8.1; OLDSUM="$(cksum < "$T/A/oldnode/bin/node")"
rc="$(run_job "$T/A")"; PRIV="$T/A/root/tools/cli-node/tools/node/bin/node"
[ "$rc" = 0 ] && ok "A: job exits 0" || bad "A: exit $rc"
[ "$(st "$T/A" node_before)" = "26.8.1" ] && [ "$(st "$T/A" node_after)" = "26.12.1" ] \
  && ok "A: status node_before=26.8.1 node_after=26.12.1" || bad "A: status node_before=$(st "$T/A" node_before) node_after=$(st "$T/A" node_after)"
grep -q -- "--node-only --prefix $T/A/root/tools/cli-node --node-version 26.12.1" "$T/install.log" \
  && ok "A: OpenClaw's installer ran --node-only into <root>/tools/cli-node with 26.12.1 (same line)" || bad "A: installer argv: $(cat "$T/install.log")"
grep -q '^env: 0 0$' "$T/install.log" && ok "A: installer ran in a clean environment (no OPENCLAW_*, nothing of the job's)" || bad "A: installer env: $(grep '^env' "$T/install.log")"
grep -q 'npm pack openclaw@2026.10.8' "$T/A/npm.log" && ok "A: installer taken from the TARGET package" || bad "A: npm calls: $(cat "$T/A/npm.log")"
[ "$(plist_node "$T/A")" = "$PRIV" ] && ok "A: LaunchAgent node argument is the private runtime" || bad "A: plist node $(plist_node "$T/A")"
$PY - "$T/A/plist.orig" "$T/A/home/Library/LaunchAgents/ai.openclaw.gateway.plist" "$SECRET" <<'PYEOF' && ok "A: every other plist field unchanged (wrapper args, port, KeepAlive, environment), mode 644" || bad "A: plist other fields changed"
import os, plistlib, sys
a, b = plistlib.load(open(sys.argv[1], "rb")), plistlib.load(open(sys.argv[2], "rb"))
a["ProgramArguments"][3] = b["ProgramArguments"][3]
assert a == b, (a, b)
assert b["EnvironmentVariables"]["OPENCLAW_GATEWAY_TOKEN"] == sys.argv[3]
assert os.stat(sys.argv[2]).st_mode & 0o7777 == 0o644
PYEOF
[ "$(cksum < "$T/A/oldnode/bin/node")" = "$OLDSUM" ] && ok "A: the box's own node file is untouched" || bad "A: old node changed"
cmp -s "$T/A/plist.orig" "$T/A/root/node-floor/gateway.plist.before" \
  && [ "$(stat -f %Lp "$T/A/root/node-floor/gateway.plist.before" 2>/dev/null || stat -c %a "$T/A/root/node-floor/gateway.plist.before")" = 600 ] \
  && ok "A: previous LaunchAgent kept byte-identical, mode 600" || bad "A: saved plist missing or wrong mode"
ran_upgrade "$T/A" && ok "A: atomic upgrade ran after the Node step" || bad "A: atomic did not run"
grep -q "^plist_node=$PRIV$" "$T/A/atomic.log" && grep -q "^path_head=$T/A/root/tools/cli-node/tools/node/bin$" "$T/A/atomic.log" \
  && grep -q "^path_node=$PRIV$" "$T/A/atomic.log" \
  && ok "A: the atomic upgrade saw the new Node in the plist and first on PATH" || bad "A: atomic saw: $(cat "$T/A/atomic.log")"
[ "$($PY -c 'import json;print(json.load(open("'"$T"'/A/root/fleet-refresh/agent-pull-status.json"))["step_exit_codes"].get("node-floor"))')" = 0 ] \
  && ok "A: step node-floor=0 recorded" || bad "A: step code"
no_secret "$T/A" && ok "A: no environment value reached the log or status file" || bad "A: a secret value leaked"

# ── B / C: which line ────────────────────────────────────────────────────────
echo "# B C"
mkbox "$T/B" 24.21.0; rc="$(run_job "$T/B")"
[ "$rc" = 0 ] && [ "$(st "$T/B" node_after)" = "24.22.1" ] && grep -q -- "--node-version 24.22.1" "$T/install.log" \
  && ok "B: Node 24.21.0 -> 24.22.1 (same major line)" || bad "B: rc=$rc after=$(st "$T/B" node_after)"
mkbox "$T/C" 22.14.0; rc="$(run_job "$T/C")"
[ "$rc" = 0 ] && [ "$(st "$T/C" node_after)" = "24.22.1" ] && grep -q -- "--node-version 24.22.1" "$T/install.log" \
  && ok "C: Node 22.14.0 -> 24.22.1 (lowest compatible even line)" || bad "C: rc=$rc after=$(st "$T/C" node_after)"

# ── D: already satisfied ─────────────────────────────────────────────────────
echo "# D"
mkbox "$T/D" 26.12.3; rc="$(run_job "$T/D")"
[ "$rc" = 0 ] && [ "$(st "$T/D" node_before)" = "26.12.3" ] && [ "$(st "$T/D" node_after)" = "26.12.3" ] \
  && untouched "$T/D" 26.12.3 && ! grep -q 'npm pack' "$T/D/npm.log" && [ ! -s "$T/install.log" ] && ran_upgrade "$T/D" \
  && ! grep -q "^path_head=$T/D/root" "$T/D/atomic.log" \
  && ok "D: Node meets the floor -> no download, plist byte-identical, PATH unchanged, upgrade ran" || bad "D: rc=$rc"

# ── E / F: install failures leave the box as found ───────────────────────────
echo "# E F"
mk_installer fail; mkbox "$T/E" 26.8.1; rc="$(run_job "$T/E")"
[ "$rc" = 25 ] && untouched "$T/E" 26.8.1 && ! ran_upgrade "$T/E" && [ -z "$(cat "$T/E/atomic.log")" ] \
  && [ "$(st "$T/E" node_before)" = "26.8.1" ] && [ -z "$(st "$T/E" node_after)" ] \
  && st "$T/E" stuck_reason | grep -q '^node floor: ' \
  && $PY -c 'import json,sys;c=json.load(open(sys.argv[1]))["step_exit_codes"];sys.exit(0 if c.get("node-floor")==25 and "upgrade" not in c else 1)' "$T/E/root/fleet-refresh/agent-pull-status.json" \
  && ok "E: failed install -> exit 25, prefix and plist exactly as found, upgrade NOT run, stuck_reason names the floor" \
  || bad "E: rc=$rc stuck=$(st "$T/E" stuck_reason) tree=$(ls "$T/E/root")"
mk_installer wrong; mkbox "$T/F" 26.8.1; rc="$(run_job "$T/F")"
[ "$rc" = 25 ] && untouched "$T/F" 26.8.1 && ! ran_upgrade "$T/F" && st "$T/F" stuck_reason | grep -q "runtime reports '22.0.0'" \
  && ok "F: an installed Node still below the floor is refused and removed again" || bad "F: rc=$rc tree=$(find "$T/F/root" -maxdepth 3 | head)"

# ── G / H: cannot read the floor ─────────────────────────────────────────────
echo "# G H"
mk_installer ok; mkbox "$T/G" 26.8.1; export NPM_VIEW_RC=1; rc="$(run_job "$T/G")"; unset NPM_VIEW_RC
[ "$rc" = 25 ] && untouched "$T/G" 26.8.1 && ! ran_upgrade "$T/G" && st "$T/G" stuck_reason | grep -q 'could not read engines.node' \
  && ok "G: npm view failing -> exit 25, nothing touched, upgrade NOT run" || bad "G: rc=$rc stuck=$(st "$T/G" stuck_reason)"
mkbox "$T/H" 26.8.1; NPM_ENGINE='^24.22.1'; rc="$(run_job "$T/H")"; NPM_ENGINE="$ENGINE_OK"
[ "$rc" = 25 ] && untouched "$T/H" 26.8.1 && ! ran_upgrade "$T/H" && st "$T/H" stuck_reason | grep -q 'refusing to guess' \
  && ok "H: a range the job cannot read -> refuses instead of guessing" || bad "H: rc=$rc stuck=$(st "$T/H" stuck_reason)"

# ── I: no LaunchAgent ────────────────────────────────────────────────────────
echo "# I"
mkbox "$T/I" 26.8.1 0; rc="$(run_job "$T/I")"
[ "$rc" = 0 ] && ran_upgrade "$T/I" && [ ! -s "$T/install.log" ] && [ ! -e "$T/I/root/tools" ] \
  && $PY -c 'import json,sys;c=json.load(open(sys.argv[1]))["step_exit_codes"];sys.exit(0 if "node-floor" not in c and c.get("upgrade")==0 else 1)' "$T/I/root/fleet-refresh/agent-pull-status.json" \
  && ok "I: no gateway LaunchAgent -> step skipped and not recorded, upgrade ran as before" || bad "I: rc=$rc"

# ── J: plist cannot be written ───────────────────────────────────────────────
echo "# J"
if [ "$(id -u)" = 0 ]; then
  echo "skip - J: running as root, a read-only directory does not stop root"
else
  mkbox "$T/J" 26.8.1; chmod 555 "$T/J/home/Library/LaunchAgents"
  rc="$(run_job "$T/J")"; chmod 755 "$T/J/home/Library/LaunchAgents"
  [ "$rc" = 25 ] && untouched "$T/J" 26.8.1 && ! ran_upgrade "$T/J" && st "$T/J" stuck_reason | grep -q 'point the gateway LaunchAgent' \
    && ok "J: unwritable LaunchAgent -> installed Node removed again, plist unchanged, upgrade NOT run" || bad "J: rc=$rc tree=$(find "$T/J/root" -maxdepth 3 | head)"
fi

# ── K: reuse ─────────────────────────────────────────────────────────────────
echo "# K"
mk_installer ok; mkbox "$T/K" 26.8.1
mkdir -p "$T/K/root/tools/cli-node/tools/node-v24.22.1/bin"
printf '%s\n' '#!/bin/sh' 'echo v24.22.1' > "$T/K/root/tools/cli-node/tools/node-v24.22.1/bin/node"; chmod 755 "$T/K/root/tools/cli-node/tools/node-v24.22.1/bin/node"
ln -sfn node-v24.22.1 "$T/K/root/tools/cli-node/tools/node"
rc="$(run_job "$T/K")"
[ "$rc" = 0 ] && [ ! -s "$T/install.log" ] && [ "$(plist_node "$T/K")" = "$T/K/root/tools/cli-node/tools/node/bin/node" ] && [ "$(st "$T/K" node_after)" = "24.22.1" ] \
  && ok "K: a satisfying private runtime is reused (installer not run), plist pointed at it" || bad "K: rc=$rc after=$(st "$T/K" node_after)"

[ "$fail" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit "$fail"
