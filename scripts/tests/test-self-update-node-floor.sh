#!/usr/bin/env bash
# Node-floor test for scripts/self-update.sh. OpenClaw 2026.10.6+ refuses every
# command on a Node below its engines.node, so the job must bring the Node the
# gateway runs up to the floor BEFORE the OpenClaw upgrade step, WITHOUT moving the
# gateway LaunchAgent to another node binary (macOS folder consent is per node
# binary path: a private Node with no consent hangs on ~/Downloads/openclaw-master-files,
# and the rollback runs on it too = exit 70, Big Fleet Roll 20261029), and must PROVE
# afterwards that the gateway answers, runs a floor-meeting Node and can read the
# Master Files folder.
# Runs the REAL script (and the REAL oc-supervisor-install.py) in a throwaway
# HOME/OPENCLAW_ROOT with stub npm, curl, git, uname, lsof, ps, launchctl and brew,
# a fixture LaunchAgent, fixture node binaries and a fixture install-cli.sh. Nothing
# leaves this machine; the real ~/.openclaw, Node, LaunchAgents and Homebrew are never
# read or written.
#
# Covers:
#   A  Node 26.8.1 < 26.12.1   -> same line (26.12.1) installed under <root>/tools/cli-node by
#                                 OpenClaw's installer (argv + clean env asserted); the plist is
#                                 BYTE-IDENTICAL (nothing rewritten, nothing kept in node-floor/);
#                                 the old node file is untouched; npm runs under the private Node
#                                 through the OC_ATOMIC_NPM wrapper even with the old node ahead on
#                                 PATH; the post-restart proof ran as a launchd job (the plist's node
#                                 as top, the gateway's runtime as child); node_before/node_after
#   B  Node 24.21.0            -> 24.22.1 (same line)
#   C  Node 22.14.0            -> 24.22.1 (lowest compatible even line)
#   D  Node 26.12.3 already ok -> nothing downloaded, plist byte-identical, no npm wrapper, probe runs
#   E  installer fails midway  -> box exactly as found, upgrade NOT run, exit 25, stuck_reason
#   F  installer installs a Node that is still below the floor -> same
#   G  npm view fails          -> nothing touched, upgrade NOT run
#   H  engines.node is a caret range this job cannot read -> refuses, nothing touched
#   I  no gateway LaunchAgent  -> step skipped, not recorded, upgrade runs, no probe (old behavior)
#   J  LaunchAgents directory read-only -> the job still succeeds (the plist is never written)
#   K  private runtime already installed and satisfying -> reused, installer not run
#   L  --brew-node-upgrade, Homebrew owns the gateway's node -> `brew upgrade node` (non-interactive,
#                                 stdin closed), plist byte-identical, no private runtime, no wrapper
#   M  Homebrew present, flag NOT given -> brew never upgrades; the private runtime is used
#   N  flag given but the upgrade does not raise the node -> falls back to the private runtime
#   O  flag given but the gateway's node is not Homebrew's -> brew never upgrades
#   P  the LaunchAgent's node has no folder consent (read hangs) -> exit 26, named, probe job booted out
#   Q  the gateway's child runtime has no consent -> exit 26 (the chain, not only the top, is read)
#   R  the live gateway runs a Node below the floor -> exit 26, node_after is the MEASURED version
#   S  the gateway process cannot be identified -> exit 26, UNDETERMINED (never a pass)
#   T  /healthz never answers 200 -> exit 26, needs_host_restart
#   U  launchd refuses the probe job -> exit 26
#   V  Master Files folder absent -> the protected parent is read instead
#   W  the real probe script, run under a real node (when one exists): reads, falls back on ENOENT,
#      fails on a missing parent and on a failing child
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

# ── fixture node ─────────────────────────────────────────────────────────────
# `node --version` prints the version. `node <...>/probe.js DIR [CHILD RESULT]` stands in for the real
# probe script (which the real node would run): a path listed in NOCONSENT hangs (an unanswered macOS
# consent prompt); otherwise it reads DIR (or its parent), runs CHILD the same way, and writes RESULT.
cat > "$T/mknode.sh" <<'EOF'
#!/usr/bin/env bash
mkdir -p "$(dirname "$1")"
cat > "$1" <<NODE
#!/bin/sh
case "\$1" in
  *probe.js)
    case ":\${NOCONSENT:-}:" in *":\$0:"*) exec sleep 120 ;; esac
    js="\$1"; dir="\$2"; child="\${3:-}"; res="\${4:-}"
    [ -d "\$dir" ] || [ -d "\$(dirname "\$dir")" ] || exit 1
    [ -z "\$child" ] || "\$child" "\$js" "\$dir" || exit 1
    [ -z "\$res" ] || echo ok > "\$res"
    exit 0 ;;
esac
echo v$2
NODE
chmod 755 "$1"
EOF
chmod 755 "$T/mknode.sh"; export MKNODE="$T/mknode.sh"

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
  */healthz) [ -n "$wfmt" ] && printf '%s' "${HEALTHZ_CODE:-200}"; exit 0 ;;
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

# lsof / ps: the process serving the gateway port is GW_PID, started from GW_EXE (empty GW_PID = nothing listens).
cat > "$T/bin/lsof" <<'EOF'
#!/usr/bin/env bash
[ -z "${GW_PID:-}" ] || echo "$GW_PID"
exit 0
EOF
REAL_PS="$(command -v ps)"; export REAL_PS
cat > "$T/bin/ps" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = -o ] && [ "${2:-}" = comm= ] && [ "${3:-}" = -p ] && [ -n "${GW_PID:-}" ] && [ "${4:-}" = "$GW_PID" ]; then
  echo "  ${GW_EXE:-}"; exit 0
fi
exec "$REAL_PS" "$@"
EOF

# launchctl: `bootstrap` captures the probe job and RUNS its ProgramArguments in the background (what
# launchd does); `bootout` kills it. Every call is logged.
cat > "$T/bin/launchctl" <<'EOF'
#!/usr/bin/env bash
echo "launchctl $*" >> "$LAUNCHCTL_LOG"
case "$1" in
  bootstrap)
    [ "${LAUNCHCTL_BOOTSTRAP_RC:-0}" = 0 ] || exit "$LAUNCHCTL_BOOTSTRAP_RC"
    plist="$3"
    cp "$plist" "$PROBE_CAPTURE/probe.plist"; cp "$(dirname "$plist")/probe.js" "$PROBE_CAPTURE/probe.js"
    cmd="$(python3 -I -c 'import plistlib,shlex,sys;print(shlex.join(plistlib.load(open(sys.argv[1],"rb"))["ProgramArguments"]))' "$plist")"
    eval "$cmd" >/dev/null 2>&1 &
    echo $! > "$PROBE_CAPTURE/pid" ;;
  bootout)
    [ -f "$PROBE_CAPTURE/pid" ] && kill "$(cat "$PROBE_CAPTURE/pid")" 2>/dev/null
    : ;;
esac
exit 0
EOF

# brew: --prefix answers BREW_PREFIX; `upgrade node` (when BREW_UPGRADE_RAISES=1) installs a 26.13.0 keg and
# relinks opt/node to it, as brew does. Every call is logged with the environment that matters.
cat > "$T/bin/brew" <<'EOF'
#!/usr/bin/env bash
echo "brew $* | NO_AUTO_UPDATE=${HOMEBREW_NO_AUTO_UPDATE:-} NO_CLEANUP=${HOMEBREW_NO_INSTALL_CLEANUP:-} NONINTERACTIVE=${NONINTERACTIVE:-} stdin=$([ -t 0 ] && echo tty || echo closed)" >> "$BREW_LOG"
case "$1" in
  --prefix) echo "$BREW_PREFIX" ;;
  upgrade)
    [ "${BREW_UPGRADE_RAISES:-1}" = 1 ] || exit "${BREW_UPGRADE_RC:-0}"
    "$MKNODE" "$BREW_PREFIX/Cellar/node/26.13.0/bin/node" 26.13.0
    ln -sfn ../Cellar/node/26.13.0 "$BREW_PREFIX/opt/node"
    exit "${BREW_UPGRADE_RC:-0}" ;;
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
"$MKNODE" "\$prefix/tools/node-v\$ver/bin/node" "\$shown"
printf '%s\n' '#!/bin/sh' 'echo "npm-first-node=\$(command -v node)"' > "\$prefix/tools/node-v\$ver/bin/npm"
chmod 755 "\$prefix/tools/node-v\$ver/bin/npm"
ln -sfn "node-v\$ver" "\$prefix/tools/node"
exit 0
EOF
  INSTALLER_SRC="$T/installer.sh"; export INSTALLER_SRC
}

printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/fix/oc-schema-migrate.py"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/fix/weekly-full-update.sh"
# Records what the atomic upgrade would have seen: the node the plist names (through the real
# resolver, copied next to it by the job), the head of PATH, the node PATH resolves, and the npm the
# job handed it. Like the real script it puts the plist's node dir FIRST on PATH, then runs that npm.
cat > "$T/fix/oc-atomic-upgrade.sh" <<'EOF'
#!/usr/bin/env bash
pn="$(python3 "$(dirname "$0")/oc-supervisor-install.py" node)"
{ echo "ran $*"
  echo "plist_node=$pn"
  echo "path_head=${PATH%%:*}"
  echo "path_node=$(command -v node)"
  echo "atomic_npm=${OC_ATOMIC_NPM:-}"
  if [ -n "${OC_ATOMIC_NPM:-}" ]; then
    echo "atomic_npm_body=$(tr '\n' '|' < "$OC_ATOMIC_NPM")"
    echo "atomic_npm_runs=$(PATH="$(dirname "$pn"):$PATH" "$OC_ATOMIC_NPM" --version)"
  fi; } >> "$ATOMIC_LOG"
exit "${ATOMIC_RC:-0}"
EOF
chmod 700 "$T/fix/"*

SECRET="s3cr3t-probe-value-8841"

mkbox() {  # case_dir node_version [with_plist=1] [brew=0]
  C="$1"; NV="$2"; WITH_PLIST="${3:-1}"; WITH_BREW="${4:-0}"
  mkdir -p "$C/home/Library/LaunchAgents" "$C/root/skills" "$C/root/secrets" "$C/oldnode/bin" \
           "$C/npm/lib/node_modules/openclaw/dist" "$C/home/.local/bin" "$C/home/Downloads/openclaw-master-files" \
           "$C/probe"
  # The job puts $HOME/.local/bin (and /usr/local/bin, /opt/homebrew/bin) in front of PATH when they
  # are missing from it; the stubs live in the first of those so a real npm or curl can never win.
  cp "$T/bin/"* "$C/home/.local/bin/"
  printf 'v78.0.0\n' > "$C/root/skills/.onboarding-version"
  printf '{"name":"openclaw","version":"2026.10.4"}\n' > "$C/npm/lib/node_modules/openclaw/package.json"
  : > "$C/npm/lib/node_modules/openclaw/dist/index.js"
  PLIST_NODE="$C/oldnode/bin/node"
  if [ "$WITH_BREW" = 1 ]; then  # the gateway's node is Homebrew's: <prefix>/opt/node -> ../Cellar/node/<ver>
    "$MKNODE" "$C/brew/Cellar/node/$NV/bin/node" "$NV"; mkdir -p "$C/brew/opt"; ln -sfn "../Cellar/node/$NV" "$C/brew/opt/node"
    PLIST_NODE="$C/brew/opt/node/bin/node"
  else
    "$MKNODE" "$C/oldnode/bin/node" "$NV"
  fi
  cksum < "$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$PLIST_NODE")" > "$C/oldnode.sum"
  if [ "$WITH_PLIST" = 1 ]; then
    P="$C/home/Library/LaunchAgents/ai.openclaw.gateway.plist"
    $PY - "$P" "$PLIST_NODE" "$C/npm/lib/node_modules/openclaw/dist/index.js" "$SECRET" <<'PYEOF'
import plistlib, sys
p, node, entry, secret = sys.argv[1:5]
plistlib.dump({"Label": "ai.openclaw.gateway", "KeepAlive": True,
               "ProgramArguments": ["/bin/sh", "/x/ai.openclaw.gateway-env-wrapper.sh", "/x/ai.openclaw.gateway.env",
                                    node, entry, "gateway", "--port", "18789"],
               "EnvironmentVariables": {"OPENCLAW_GATEWAY_TOKEN": secret}}, open(p, "wb"))
PYEOF
    chmod 644 "$P"; cp -p "$P" "$C/plist.orig"
  fi
  : > "$C/atomic.log"; : > "$C/npm.log"; : > "$C/launchctl.log"; : > "$C/brew.log"; : > "$T/install.log"
}

# The gateway as lsof/ps will report it: pid 4242 started from GW_EXE. Default: the cached private runtime
# (the 2026.10.8 child). A case that expects another process exports GW_EXE before run_job.
gw_default() { GW_PID=4242; GW_EXE="$1/root/tools/cli-node/tools/node/bin/node"; }

run_job() {  # case_dir [extra self-update args] -> exit code of the job
  C="$1"; shift
  PATH="$T/bin:$PATH" HOME="$C/home" OPENCLAW_ROOT="$C/root" FIXTURES="$T/fix" TMPDIR="$T/tmp" \
    ATOMIC_LOG="$C/atomic.log" NPM_LOG="$C/npm.log" LAUNCHCTL_LOG="$C/launchctl.log" PROBE_CAPTURE="$C/probe" \
    BREW_LOG="$C/brew.log" BREW_PREFIX="$C/brew" SELF_UPDATE_TCC_PROBE_SECONDS=4 SELF_UPDATE_TCC_HEALTH_SECONDS=2 \
    bash "$SRC" --roll-id "roll-${C##*/}" --openclaw-target 2026.10.8 --foreground "$@" > "$C/out.txt" 2>&1
  echo $?
}

st() { $PY -c '
import json, sys
d = json.load(open(sys.argv[1])); v = d.get(sys.argv[2], "")
print(json.dumps(v, sort_keys=True) if isinstance(v, dict) else v)' "$1/root/fleet-refresh/agent-pull-status.json" "$2" 2>/dev/null; }
step() { $PY -c 'import json,sys;print(json.load(open(sys.argv[1]))["step_exit_codes"].get(sys.argv[2],"absent"))' "$1/root/fleet-refresh/agent-pull-status.json" "$2" 2>/dev/null; }

plist_same() { cmp -s "$1/plist.orig" "$1/home/Library/LaunchAgents/ai.openclaw.gateway.plist"; }
untouched() {  # case_dir: plist byte-identical, no private runtime, no node-floor dir, the gateway's node file intact
  plist_same "$1" && [ ! -e "$1/root/tools" ] && [ ! -e "$1/root/node-floor" ] \
    && [ "$(cksum < "$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "${2:-$1/oldnode/bin/node}")")" = "$(cat "$1/oldnode.sum")" ]
}
ran_upgrade() { grep -q '^ran --upgrade --target-version 2026.10.8' "$1/atomic.log"; }
no_secret() { ! grep -rqF "$SECRET" "$1/out.txt" "$1/root/self-update" "$1/root/fleet-refresh/agent-pull-status.json" 2>/dev/null; }
probe_arg() {  # case_dir index: ProgramArguments[index] of the captured probe job
  $PY -c 'import plistlib,sys;print(plistlib.load(open(sys.argv[1],"rb"))["ProgramArguments"][int(sys.argv[2])])' "$1/probe/probe.plist" "$2" 2>/dev/null; }

export NPM_ENGINE="$ENGINE_OK"
unset NOCONSENT HEALTHZ_CODE LAUNCHCTL_BOOTSTRAP_RC BREW_UPGRADE_RAISES BREW_UPGRADE_RC NPM_VIEW_RC

# ── A: 26.8.1 -> 26.12.1, same line ──────────────────────────────────────────
echo "# A"
mk_installer ok
mkbox "$T/A" 26.8.1; gw_default "$T/A"; export GW_PID GW_EXE
rc="$(run_job "$T/A")"; PRIV="$T/A/root/tools/cli-node/tools/node/bin/node"; PBIN="$T/A/root/tools/cli-node/tools/node/bin"
[ "$rc" = 0 ] && ok "A: job exits 0" || bad "A: exit $rc: $(tail -5 "$T/A/out.txt")"
[ "$(st "$T/A" node_before)" = "26.8.1" ] && [ "$(st "$T/A" node_after)" = "26.12.1" ] \
  && ok "A: status node_before=26.8.1 node_after=26.12.1 (measured from the process serving the gateway port)" \
  || bad "A: status node_before=$(st "$T/A" node_before) node_after=$(st "$T/A" node_after)"
grep -q -- "--node-only --prefix $T/A/root/tools/cli-node --node-version 26.12.1" "$T/install.log" \
  && ok "A: OpenClaw's installer ran --node-only into <root>/tools/cli-node with 26.12.1 (same line)" || bad "A: installer argv: $(cat "$T/install.log")"
grep -q '^env: 0 0$' "$T/install.log" && ok "A: installer ran in a clean environment (no OPENCLAW_*, nothing of the job's)" || bad "A: installer env: $(grep '^env' "$T/install.log")"
grep -q 'npm pack openclaw@2026.10.8' "$T/A/npm.log" && ok "A: installer taken from the TARGET package" || bad "A: npm calls: $(cat "$T/A/npm.log")"
plist_same "$T/A" && ok "A: the LaunchAgent plist is BYTE-IDENTICAL (node argument, mode, environment: nothing rewritten)" || bad "A: plist changed"
[ ! -e "$T/A/root/node-floor" ] && ok "A: no node-floor/ copy kept (there is nothing to put back)" || bad "A: node-floor/ exists"
[ "$(cksum < "$T/A/oldnode/bin/node")" = "$(cat "$T/A/oldnode.sum")" ] && ok "A: the box's own node file is untouched" || bad "A: old node changed"
ran_upgrade "$T/A" && ok "A: atomic upgrade ran after the Node step" || bad "A: atomic did not run"
grep -q "^plist_node=$T/A/oldnode/bin/node$" "$T/A/atomic.log" && grep -q "^path_head=$PBIN$" "$T/A/atomic.log" \
  && ok "A: the atomic upgrade saw the ORIGINAL node in the plist and the private runtime first on the job's PATH" || bad "A: atomic saw: $(cat "$T/A/atomic.log")"
grep -q "^atomic_npm=$T/tmp/self-update\.[^/]*/npm-private$" "$T/A/atomic.log" \
  && grep -qF "atomic_npm_body=#!/bin/sh|PATH=\"$PBIN:\$PATH\"; export PATH|exec \"$PBIN/npm\" \"\$@\"|" "$T/A/atomic.log" \
  && grep -q "^atomic_npm_runs=npm-first-node=$PBIN/node$" "$T/A/atomic.log" \
  && ok "A: the atomic upgrade got OC_ATOMIC_NPM = a wrapper that runs the private npm on the private Node, even with the old node ahead on PATH (the exit-78 fix)" \
  || bad "A: npm wrapper: $(grep '^atomic_npm' "$T/A/atomic.log")"
grep -q "^launchctl bootstrap gui/$(id -u) " "$T/A/launchctl.log" && grep -q "^launchctl bootout gui/$(id -u)/ai.openclaw.tcc-probe\." "$T/A/launchctl.log" \
  && [ "$(probe_arg "$T/A" 0)" = "$T/A/oldnode/bin/node" ] && [ "$(probe_arg "$T/A" 3)" = "$PRIV" ] \
  && [ "$(probe_arg "$T/A" 2)" = "$T/A/home/Downloads/openclaw-master-files" ] \
  && ok "A: the proof ran as a launchd job in gui/<uid>: the plist's node as top, the gateway's runtime as child, reading the Master Files folder; job booted out" \
  || bad "A: probe: $(cat "$T/A/launchctl.log") args: $(probe_arg "$T/A" 0) | $(probe_arg "$T/A" 3) | $(probe_arg "$T/A" 2)"
[ "$(step "$T/A" node-floor)" = 0 ] && [ "$(step "$T/A" upgrade)" = 0 ] && [ "$(step "$T/A" tcc-probe)" = 0 ] \
  && ok "A: steps node-floor=0 upgrade=0 tcc-probe=0 recorded" || bad "A: steps: $(st "$T/A" step_exit_codes)"
grep -q "tcc-probe: /healthz 200; the gateway serves from Node 26.12.1" "$T/A/out.txt" \
  && ok "A: the log names what was proven" || bad "A: log lacks the tcc-probe line"
no_secret "$T/A" && ok "A: no environment value reached the log or status file" || bad "A: a secret value leaked"
[ -z "$(find "$T/tmp" -maxdepth 1 -name 'self-update.*' 2>/dev/null)" ] \
  && ok "A: the job's work directory (wrapper, probe files) is removed at exit" || bad "A: work directory left behind"

# ── B / C: which line ────────────────────────────────────────────────────────
echo "# B C"
mkbox "$T/B" 24.21.0; gw_default "$T/B"; export GW_PID GW_EXE; rc="$(run_job "$T/B")"
[ "$rc" = 0 ] && [ "$(st "$T/B" node_after)" = "24.22.1" ] && grep -q -- "--node-version 24.22.1" "$T/install.log" && plist_same "$T/B" \
  && ok "B: Node 24.21.0 -> 24.22.1 (same major line), plist untouched" || bad "B: rc=$rc after=$(st "$T/B" node_after)"
mkbox "$T/C" 22.14.0; gw_default "$T/C"; export GW_PID GW_EXE; rc="$(run_job "$T/C")"
[ "$rc" = 0 ] && [ "$(st "$T/C" node_after)" = "24.22.1" ] && grep -q -- "--node-version 24.22.1" "$T/install.log" && plist_same "$T/C" \
  && ok "C: Node 22.14.0 -> 24.22.1 (lowest compatible even line), plist untouched" || bad "C: rc=$rc after=$(st "$T/C" node_after)"

# ── D: already satisfied ─────────────────────────────────────────────────────
echo "# D"
mkbox "$T/D" 26.12.3; GW_PID=4242; GW_EXE="$T/D/oldnode/bin/node"; export GW_PID GW_EXE; rc="$(run_job "$T/D")"
[ "$rc" = 0 ] && [ "$(st "$T/D" node_before)" = "26.12.3" ] && [ "$(st "$T/D" node_after)" = "26.12.3" ] \
  && untouched "$T/D" && ! grep -q 'npm pack' "$T/D/npm.log" && [ ! -s "$T/install.log" ] && ran_upgrade "$T/D" \
  && ! grep -q "^path_head=$T/D/root" "$T/D/atomic.log" && grep -q '^atomic_npm=$' "$T/D/atomic.log" \
  && ok "D: Node meets the floor -> no download, plist byte-identical, PATH unchanged, no npm wrapper, upgrade ran" || bad "D: rc=$rc"
[ "$(step "$T/D" tcc-probe)" = 0 ] && ok "D: the post-restart proof still runs when the floor was already met" || bad "D: steps $(st "$T/D" step_exit_codes)"

# ── E / F: install failures leave the box as found ───────────────────────────
echo "# E F"
mk_installer fail; mkbox "$T/E" 26.8.1; rc="$(run_job "$T/E")"
[ "$rc" = 25 ] && untouched "$T/E" && ! ran_upgrade "$T/E" && [ -z "$(cat "$T/E/atomic.log")" ] \
  && [ "$(st "$T/E" node_before)" = "26.8.1" ] && [ -z "$(st "$T/E" node_after)" ] \
  && st "$T/E" stuck_reason | grep -q '^node floor: ' \
  && [ "$(step "$T/E" node-floor)" = 25 ] && [ "$(step "$T/E" upgrade)" = absent ] && [ "$(step "$T/E" tcc-probe)" = absent ] \
  && ok "E: failed install -> exit 25, prefix and plist exactly as found, upgrade NOT run, no probe, stuck_reason names the floor" \
  || bad "E: rc=$rc stuck=$(st "$T/E" stuck_reason) tree=$(ls "$T/E/root")"
mk_installer wrong; mkbox "$T/F" 26.8.1; rc="$(run_job "$T/F")"
[ "$rc" = 25 ] && untouched "$T/F" && ! ran_upgrade "$T/F" && st "$T/F" stuck_reason | grep -q "runtime reports '22.0.0'" \
  && ok "F: an installed Node still below the floor is refused and removed again" || bad "F: rc=$rc tree=$(find "$T/F/root" -maxdepth 3 | head)"

# ── G / H: cannot read the floor ─────────────────────────────────────────────
echo "# G H"
mk_installer ok; mkbox "$T/G" 26.8.1; export NPM_VIEW_RC=1; rc="$(run_job "$T/G")"; unset NPM_VIEW_RC
[ "$rc" = 25 ] && untouched "$T/G" && ! ran_upgrade "$T/G" && st "$T/G" stuck_reason | grep -q 'could not read engines.node' \
  && ok "G: npm view failing -> exit 25, nothing touched, upgrade NOT run" || bad "G: rc=$rc stuck=$(st "$T/G" stuck_reason)"
mkbox "$T/H" 26.8.1; NPM_ENGINE='^24.22.1'; rc="$(run_job "$T/H")"; NPM_ENGINE="$ENGINE_OK"
[ "$rc" = 25 ] && untouched "$T/H" && ! ran_upgrade "$T/H" && st "$T/H" stuck_reason | grep -q 'refusing to guess' \
  && ok "H: a range the job cannot read -> refuses instead of guessing" || bad "H: rc=$rc stuck=$(st "$T/H" stuck_reason)"

# ── I: no LaunchAgent ────────────────────────────────────────────────────────
echo "# I"
mkbox "$T/I" 26.8.1 0; unset GW_PID; rc="$(run_job "$T/I")"
[ "$rc" = 0 ] && ran_upgrade "$T/I" && [ ! -s "$T/install.log" ] && [ ! -e "$T/I/root/tools" ] && [ ! -s "$T/I/launchctl.log" ] \
  && [ "$(step "$T/I" node-floor)" = absent ] && [ "$(step "$T/I" tcc-probe)" = absent ] && [ "$(step "$T/I" upgrade)" = 0 ] \
  && ok "I: no gateway LaunchAgent -> step skipped and not recorded, no probe, upgrade ran as before" || bad "I: rc=$rc steps=$(st "$T/I" step_exit_codes)"

# ── J: the plist is never written ────────────────────────────────────────────
echo "# J"
if [ "$(id -u)" = 0 ]; then
  echo "skip - J: running as root, a read-only directory does not stop root"
else
  mkbox "$T/J" 26.8.1; gw_default "$T/J"; export GW_PID GW_EXE; chmod 555 "$T/J/home/Library/LaunchAgents"
  rc="$(run_job "$T/J")"; chmod 755 "$T/J/home/Library/LaunchAgents"
  [ "$rc" = 0 ] && plist_same "$T/J" && ran_upgrade "$T/J" \
    && ok "J: an unwritable LaunchAgents directory changes nothing: the plist is never written, the upgrade ran" || bad "J: rc=$rc"
fi

# ── K: reuse ─────────────────────────────────────────────────────────────────
echo "# K"
mk_installer ok; mkbox "$T/K" 26.8.1; gw_default "$T/K"; export GW_PID GW_EXE
"$MKNODE" "$T/K/root/tools/cli-node/tools/node-v24.22.1/bin/node" 24.22.1
ln -sfn node-v24.22.1 "$T/K/root/tools/cli-node/tools/node"
rc="$(run_job "$T/K")"
[ "$rc" = 0 ] && [ ! -s "$T/install.log" ] && plist_same "$T/K" && [ "$(st "$T/K" node_after)" = "24.22.1" ] \
  && ok "K: a satisfying private runtime is reused (installer not run), plist untouched" || bad "K: rc=$rc after=$(st "$T/K" node_after)"

# ── L: --brew-node-upgrade, Homebrew owns the gateway's node ─────────────────
echo "# L"
mk_installer ok; mkbox "$T/L" 26.8.1 1 1; GW_PID=4242; GW_EXE="$T/L/brew/opt/node/bin/node"; export GW_PID GW_EXE
rc="$(run_job "$T/L" --brew-node-upgrade)"
[ "$rc" = 0 ] && grep -q '^brew upgrade node | NO_AUTO_UPDATE=1 NO_CLEANUP=1 NONINTERACTIVE=1 stdin=closed$' "$T/L/brew.log" \
  && ok "L: brew upgrade node ran non-interactively (no auto-update, old keg kept, stdin closed)" || bad "L: rc=$rc brew: $(cat "$T/L/brew.log")"
plist_same "$T/L" && [ ! -e "$T/L/root/tools" ] && [ ! -s "$T/install.log" ] && [ ! -e "$T/L/root/node-floor" ] \
  && grep -q '^atomic_npm=$' "$T/L/atomic.log" && ! grep -q "^path_head=$T/L/root" "$T/L/atomic.log" \
  && ok "L: plist byte-identical, no private runtime, no npm wrapper, PATH not led by a private node" || bad "L: tree=$(ls "$T/L/root") atomic=$(cat "$T/L/atomic.log")"
[ "$(st "$T/L" node_before)" = "26.8.1" ] && [ "$(st "$T/L" node_after)" = "26.13.0" ] && [ "$(step "$T/L" tcc-probe)" = 0 ] \
  && ok "L: node_before=26.8.1 node_after=26.13.0, proof passed on the upgraded Homebrew node" || bad "L: before=$(st "$T/L" node_before) after=$(st "$T/L" node_after)"

# ── M: Homebrew present, flag not given ──────────────────────────────────────
echo "# M"
mkbox "$T/M" 26.8.1 1 1; GW_PID=4242; GW_EXE="$T/M/root/tools/cli-node/tools/node/bin/node"; export GW_PID GW_EXE
rc="$(run_job "$T/M")"
[ "$rc" = 0 ] && ! grep -q 'upgrade' "$T/M/brew.log" && plist_same "$T/M" && [ -s "$T/install.log" ] && [ "$(st "$T/M" node_after)" = "26.12.1" ] \
  && ok "M: without the flag brew is never asked to upgrade; the private runtime is used (the default)" || bad "M: rc=$rc brew=$(cat "$T/M/brew.log")"

# ── N: flag given, upgrade does not raise the node ───────────────────────────
echo "# N"
mkbox "$T/N" 26.8.1 1 1; GW_PID=4242; GW_EXE="$T/N/root/tools/cli-node/tools/node/bin/node"; export GW_PID GW_EXE
export BREW_UPGRADE_RAISES=0 BREW_UPGRADE_RC=1; rc="$(run_job "$T/N" --brew-node-upgrade)"; unset BREW_UPGRADE_RAISES BREW_UPGRADE_RC
[ "$rc" = 0 ] && grep -q '^brew upgrade node' "$T/N/brew.log" && plist_same "$T/N" && [ -s "$T/install.log" ] && [ "$(st "$T/N" node_after)" = "26.12.1" ] \
  && ok "N: a brew upgrade that leaves the node below the floor falls back to the private runtime, plist untouched" || bad "N: rc=$rc brew=$(cat "$T/N/brew.log")"

# ── O: flag given, the gateway's node is not Homebrew's ──────────────────────
echo "# O"
mkbox "$T/O" 26.8.1; GW_PID=4242; GW_EXE="$T/O/root/tools/cli-node/tools/node/bin/node"; export GW_PID GW_EXE; mkdir -p "$T/O/brew"
rc="$(run_job "$T/O" --brew-node-upgrade)"
[ "$rc" = 0 ] && ! grep -q 'upgrade' "$T/O/brew.log" && plist_same "$T/O" && [ -s "$T/install.log" ] \
  && ok "O: the node the LaunchAgent names is not Homebrew's -> no brew upgrade, private runtime" || bad "O: rc=$rc brew=$(cat "$T/O/brew.log")"

# ── P / Q: no folder consent ─────────────────────────────────────────────────
echo "# P Q"
mkbox "$T/P" 26.8.1; gw_default "$T/P"; export GW_PID GW_EXE
export NOCONSENT="$T/P/oldnode/bin/node"; rc="$(run_job "$T/P")"; unset NOCONSENT
[ "$rc" = 26 ] && ran_upgrade "$T/P" && [ "$(step "$T/P" upgrade)" = 0 ] && [ "$(step "$T/P" tcc-probe)" = 26 ] \
  && st "$T/P" stuck_reason | grep -q 'did not finish reading .*openclaw-master-files within 4 s' \
  && grep -q "^launchctl bootout gui/$(id -u)/ai.openclaw.tcc-probe\." "$T/P/launchctl.log" \
  && ok "P: a top node with no folder consent -> exit 26, named in stuck_reason, the hung probe job booted out" \
  || bad "P: rc=$rc stuck=$(st "$T/P" stuck_reason) steps=$(st "$T/P" step_exit_codes)"
[ "$(st "$T/P" needs_host_restart)" = "False" ] && ok "P: a folder-consent hang is not reported as a host restart" || bad "P: needs_host_restart=$(st "$T/P" needs_host_restart)"
mkbox "$T/Q" 26.8.1; gw_default "$T/Q"; export GW_PID GW_EXE
export NOCONSENT="$T/Q/root/tools/cli-node/tools/node/bin/node"; rc="$(run_job "$T/Q")"; unset NOCONSENT
[ "$rc" = 26 ] && [ "$(step "$T/Q" tcc-probe)" = 26 ] && st "$T/Q" stuck_reason | grep -q 'did not finish reading' \
  && ok "Q: the child runtime with no consent is caught too (the whole chain is read, not only the top)" || bad "Q: rc=$rc stuck=$(st "$T/Q" stuck_reason)"

# ── R: the live gateway runs a Node below the floor ──────────────────────────
echo "# R"
mkbox "$T/R" 26.8.1; GW_PID=4242; GW_EXE="$T/R/oldnode/bin/node"; export GW_PID GW_EXE
rc="$(run_job "$T/R")"
[ "$rc" = 26 ] && [ "$(st "$T/R" node_after)" = "26.8.1" ] && st "$T/R" stuck_reason | grep -q 'gateway process runs Node 26.8.1 .* below engines.node' && [ ! -s "$T/R/probe/probe.js" ] \
  && ok "R: a gateway still on the below-floor Node -> exit 26, node_after is the MEASURED 26.8.1, no folder read is claimed" || bad "R: rc=$rc after=$(st "$T/R" node_after) stuck=$(st "$T/R" stuck_reason)"

# ── S: gateway process unidentifiable ────────────────────────────────────────
echo "# S"
mkbox "$T/S" 26.8.1; unset GW_PID GW_EXE
rc="$(run_job "$T/S")"
[ "$rc" = 26 ] && st "$T/S" stuck_reason | grep -q 'UNDETERMINED' && [ -z "$(st "$T/S" node_after)" ] \
  && ok "S: an unidentifiable gateway process is UNDETERMINED, never a pass (exit 26, node_after left empty)" || bad "S: rc=$rc stuck=$(st "$T/S" stuck_reason)"

# ── T: /healthz never 200 ────────────────────────────────────────────────────
echo "# T"
mkbox "$T/T" 26.8.1; gw_default "$T/T"; export GW_PID GW_EXE
export HEALTHZ_CODE=503; rc="$(run_job "$T/T")"; unset HEALTHZ_CODE
[ "$rc" = 26 ] && st "$T/T" stuck_reason | grep -q '/healthz did not answer 200 within 2 s' && [ "$(st "$T/T" needs_host_restart)" = "True" ] \
  && ok "T: /healthz not 200 -> exit 26, needs_host_restart set" || bad "T: rc=$rc stuck=$(st "$T/T" stuck_reason) restart=$(st "$T/T" needs_host_restart)"

# ── U: launchd refuses the probe job ─────────────────────────────────────────
echo "# U"
mkbox "$T/U" 26.8.1; gw_default "$T/U"; export GW_PID GW_EXE
export LAUNCHCTL_BOOTSTRAP_RC=5; rc="$(run_job "$T/U")"; unset LAUNCHCTL_BOOTSTRAP_RC
[ "$rc" = 26 ] && st "$T/U" stuck_reason | grep -q 'launchd would not load the probe job' \
  && ok "U: a probe job launchd will not load is a failed proof, not a skipped one" || bad "U: rc=$rc stuck=$(st "$T/U" stuck_reason)"

# ── V: Master Files folder absent ────────────────────────────────────────────
echo "# V"
mkbox "$T/V" 26.8.1; gw_default "$T/V"; export GW_PID GW_EXE; rmdir "$T/V/home/Downloads/openclaw-master-files"
rc="$(run_job "$T/V")"
[ "$rc" = 0 ] && [ "$(step "$T/V" tcc-probe)" = 0 ] && ok "V: no Master Files folder yet -> the protected parent (Downloads) is read instead, proof passes" || bad "V: rc=$rc stuck=$(st "$T/V" stuck_reason)"

# ── W: the real probe script under a real node ───────────────────────────────
echo "# W"
JS="$T/A/probe/probe.js"; RN="$(command -v node 2>/dev/null || true)"
if [ -z "$RN" ] || [ ! -s "$JS" ]; then
  echo "skip - W: no real node on this machine"
else
  W="$T/W"; mkdir -p "$W/d"; rm -f "$W/res"
  "$RN" "$JS" "$W/d" "$RN" "$W/res" 2>/dev/null; r1=$?
  [ "$r1" = 0 ] && [ "$(cat "$W/res" 2>/dev/null)" = ok ] && ok "W: real node: reads the folder, runs the child the same way, writes the result" || bad "W: rc=$r1"
  rm -f "$W/res"; "$RN" "$JS" "$W/d/not-yet" "$RN" "$W/res" 2>/dev/null; r2=$?
  [ "$r2" = 0 ] && [ "$(cat "$W/res" 2>/dev/null)" = ok ] && ok "W: real node: a missing Master Files folder falls back to its parent" || bad "W: ENOENT fallback rc=$r2"
  rm -f "$W/res"; "$RN" "$JS" "$W/no/such/dir" "$RN" "$W/res" 2>/dev/null; r3=$?
  [ "$r3" != 0 ] && [ ! -e "$W/res" ] && ok "W: real node: a missing parent fails and writes no result" || bad "W: missing parent rc=$r3"
  rm -f "$W/res"; "$RN" "$JS" "$W/d" /usr/bin/false "$W/res" 2>/dev/null; r4=$?
  [ "$r4" != 0 ] && [ ! -e "$W/res" ] && ok "W: real node: a failing child fails the proof and writes no result" || bad "W: failing child rc=$r4"
fi

[ "$fail" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit "$fail"
