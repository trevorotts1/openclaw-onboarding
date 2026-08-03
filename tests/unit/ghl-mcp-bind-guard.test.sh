#!/usr/bin/env bash
# tests/unit/ghl-mcp-bind-guard.test.sh — v21.5.2
#
# Proves the D6 loopback fix ACTUALLY MOVES THE BIND, rather than merely
# declaring an environment variable that nothing reads.
#
# WHY THIS TEST IS THE WHOLE POINT
#   The GHL community MCP holds a client's GoHighLevel Private Integration Token
#   and serves `GET /tools` to anyone who asks, with no authentication. Measured
#   on the canary: `lsof` -> `TCP *:8765 (LISTEN)` (every interface) and a fleet
#   survey found 19 Mac client boxes LAN-exposed in exactly that state.
#
#   The obvious "fix" — putting HOST=127.0.0.1 in the plist / pm2 env / compose —
#   DOES NOTHING. The bind address is a hardcoded string literal in the pinned
#   third-party source, in BOTH entry points:
#       src/main.ts:209         app.listen(port, '0.0.0.0', …)
#       src/http-server.ts:176  this.app.listen(this.port, '0.0.0.0', …)
#   There is no HOST, no MCP_SERVER_HOST, no knob. A grep-based QC check would
#   have happily gone green on a fix that changed nothing.
#
#   So the repo generates .ghl-mcp-bind-guard.cjs and preloads it with
#   `node --require`. It wraps net.Server.prototype.listen — which express's
#   app.listen(), http.createServer().listen() and BOTH upstream entry points all
#   funnel through — and rewrites the host argument before the real bind.
#
#   Being outside dist/ is not an accident: it is the durability property. The
#   installer REBUILDS dist/ from the pinned commit and atomically swaps it on
#   every run, so a patch applied to dist/ is reverted by the next build on every
#   box. The guard survives because a rebuild never touches it. Case (5) proves
#   exactly that.
#
# Cases:
#   (1) CONTROL — a server calling listen(port,'0.0.0.0') binds all interfaces.
#   (2) GUARDED — the identical server binds 127.0.0.1.
#   (3) The guard is entry-point agnostic: the class-method call shape used by
#       src/http-server.ts is enforced the same way.
#   (4) FAIL-CLOSED ON VALUE — a routable GHL_MCP_BIND_HOST is coerced back to
#       loopback (a typo or a copied config cannot re-expose the box).
#   (5) SURVIVES A dist/ REBUILD — the exact failure mode that makes a dist patch
#       useless: wipe and re-create dist/, and the guard is still in force.
#   (6) FAIL-OPEN ON SHAPE — an unrecognised listen shape (unix socket) still
#       starts. A security guard that bricks 38 client boxes is a worse outage
#       than the one it prevents.
#
# Node built-ins only (http.Server extends net.Server and does not override
# listen, so this exercises the same code path express does). No network egress,
# no credentials, no third-party install required.
#
# Exit 0 = all cases pass.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUTOSTART="$REPO_ROOT/scripts/ghl-mcp-autostart.sh"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== ghl-mcp-bind-guard.test.sh (v21.5.2) ==="
echo ""

command -v node >/dev/null 2>&1 || { echo "  SKIP: node not available"; exit 0; }
[ -f "$AUTOSTART" ] || { echo "  FAIL: autostart not found at $AUTOSTART"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ── Extract the REAL guard the installer ships ───────────────────────────────
# Source the autostart with a stubbed environment and call write_bind_guard, so
# this test exercises the shipped generator rather than a copy that could drift.
MCP_DIR="$WORK/mcp"
mkdir -p "$MCP_DIR"
GUARD="$MCP_DIR/.ghl-mcp-bind-guard.cjs"

extract_guard() {
  # Pull the write_bind_guard function body out of the shipped script and run it.
  # We deliberately do NOT source the whole autostart (it would try to talk to
  # launchd/pm2); we take the heredoc it writes, which is the artifact under test.
  # NOTE: the terminator is an EXACT `}` line. The guard's own JavaScript contains
  # `} catch (e) { … }` at column 0, so a looser /^\}/ ends the range early and
  # produces an unterminated heredoc.
  awk '/^write_bind_guard\(\) \{/,/^\}$/' "$AUTOSTART" > "$WORK/gen.sh"
  {
    printf 'BIND_GUARD="%s"\n' "$GUARD"
    cat "$WORK/gen.sh"
    printf 'write_bind_guard\n'
  } > "$WORK/run-gen.sh"
  bash "$WORK/run-gen.sh"
}
extract_guard
if [ ! -s "$GUARD" ]; then
  echo "  FAIL: could not generate the bind guard from $AUTOSTART (write_bind_guard changed shape?)"
  exit 1
fi
node --check "$GUARD" 2>/dev/null && pass "(0) the generated bind guard is syntactically valid JavaScript" \
  || { fail "(0) the generated bind guard is NOT valid JavaScript"; echo "=== Result: $PASS passed | $((FAIL)) failed ==="; exit 1; }

# ── Servers that mirror the two upstream call shapes ─────────────────────────
cat > "$WORK/srv-fn.js" <<'JS'
// Mirrors src/main.ts:209 — app.listen(port, '0.0.0.0', cb)
const http = require('http');
const srv = http.createServer((_q, s) => { s.end('ok'); });
srv.listen(0, '0.0.0.0', () => {
  const a = srv.address();
  console.log(JSON.stringify({ address: a.address, port: a.port }));
  srv.close(() => process.exit(0));
});
JS

cat > "$WORK/srv-class.js" <<'JS'
// Mirrors src/http-server.ts:176 — this.app.listen(this.port, '0.0.0.0', cb)
const http = require('http');
class Legacy {
  constructor() { this.port = 0; this.app = http.createServer((_q, s) => s.end('ok')); }
  start() {
    this.app.listen(this.port, '0.0.0.0', () => {
      const a = this.app.address();
      console.log(JSON.stringify({ address: a.address, port: a.port }));
      this.app.close(() => process.exit(0));
    });
  }
}
new Legacy().start();
JS

cat > "$WORK/srv-ipc.js" <<'JS'
// An unrecognised listen shape (unix domain socket). The guard must LEAVE IT
// ALONE and the server must still start — fail-open on shape.
const http = require('http');
const path = process.env.IPC_PATH;
const srv = http.createServer((_q, s) => s.end('ok'));
srv.listen(path, () => { console.log(JSON.stringify({ ipc: true })); srv.close(() => process.exit(0)); });
JS

addr_of() {  # $1 = script, $2 = "guard"|"noguard", $3.. = extra env assignments
  local script="$1" mode="$2"; shift 2
  local out
  if [ "$mode" = "guard" ]; then
    out="$(env "$@" NODE_OPTIONS="--require \"$GUARD\"" node "$script" 2>/dev/null | tail -1)"
  else
    out="$(env "$@" node "$script" 2>/dev/null | tail -1)"
  fi
  printf '%s' "$out" | sed -n 's/.*"address":"\([^"]*\)".*/\1/p'
}

# ── (1) CONTROL: without the guard the bind is all-interfaces ────────────────
A_CONTROL="$(addr_of "$WORK/srv-fn.js" noguard)"
if [ "$A_CONTROL" = "0.0.0.0" ]; then
  pass "(1) CONTROL: unguarded listen(port,'0.0.0.0') binds 0.0.0.0 (the live fleet exposure)"
else
  fail "(1) CONTROL expected 0.0.0.0, got '${A_CONTROL:-<none>}' — the fixture no longer reproduces the defect"
fi

# ── (2) GUARDED: the identical server binds loopback ─────────────────────────
A_GUARD="$(addr_of "$WORK/srv-fn.js" guard)"
if [ "$A_GUARD" = "127.0.0.1" ]; then
  pass "(2) GUARDED: the same server binds 127.0.0.1 — the bind actually moved"
else
  fail "(2) GUARDED expected 127.0.0.1, got '${A_GUARD:-<none>}' — the guard is not taking effect"
fi

# The two must DIFFER; identical results would mean the test proves nothing.
if [ -n "$A_CONTROL" ] && [ -n "$A_GUARD" ] && [ "$A_CONTROL" != "$A_GUARD" ]; then
  pass "(2b) MUTATION PROOF: control and guarded runs differ ($A_CONTROL -> $A_GUARD)"
else
  fail "(2b) control and guarded runs did not differ — this test cannot detect a regression"
fi

# ── (3) The legacy class-method entry point is covered too ───────────────────
A_CLASS="$(addr_of "$WORK/srv-class.js" guard)"
if [ "$A_CLASS" = "127.0.0.1" ]; then
  pass "(3) the src/http-server.ts call shape is guarded too (entry-point agnostic)"
else
  fail "(3) legacy entry-point shape bound '${A_CLASS:-<none>}' instead of 127.0.0.1"
fi

# ── (4) FAIL-CLOSED on a routable host value ─────────────────────────────────
A_BAD="$(addr_of "$WORK/srv-fn.js" guard GHL_MCP_BIND_HOST=0.0.0.0)"
if [ "$A_BAD" = "127.0.0.1" ]; then
  pass "(4) a routable GHL_MCP_BIND_HOST=0.0.0.0 is coerced back to loopback (fail-closed on value)"
else
  fail "(4) GHL_MCP_BIND_HOST=0.0.0.0 produced '${A_BAD:-<none>}' — the coercion is missing"
fi

# The documented escape hatch must still work, or an operator with a real need
# has no supported path and will disable the guard wholesale.
A_OPT="$(addr_of "$WORK/srv-fn.js" guard GHL_MCP_BIND_HOST=0.0.0.0 GHL_MCP_ALLOW_PUBLIC_BIND=1)"
if [ "$A_OPT" = "0.0.0.0" ]; then
  pass "(4b) the explicit GHL_MCP_ALLOW_PUBLIC_BIND=1 escape hatch is honoured"
else
  fail "(4b) escape hatch produced '${A_OPT:-<none>}' instead of 0.0.0.0"
fi

# ── (5) SURVIVES A dist/ REBUILD ─────────────────────────────────────────────
# The installer rebuilds dist/ from the pinned commit and atomically swaps it in
# on EVERY run. Anything patched into dist/ is therefore reverted on every box at
# the next build — which is precisely why the fix does not live there.
mkdir -p "$MCP_DIR/dist"
printf 'console.log("old build");\n' > "$MCP_DIR/dist/main.js"
GUARD_SHA_BEFORE="$(shasum -a 256 "$GUARD" 2>/dev/null | awk '{print $1}')"
rm -rf "$MCP_DIR/dist"                      # the swap: old dist discarded
mkdir -p "$MCP_DIR/dist"                    # …and a freshly built one moved in
printf 'console.log("rebuilt from the pinned commit");\n' > "$MCP_DIR/dist/main.js"
GUARD_SHA_AFTER="$(shasum -a 256 "$GUARD" 2>/dev/null | awk '{print $1}')"
A_AFTER_REBUILD="$(addr_of "$WORK/srv-fn.js" guard)"
if [ -n "$GUARD_SHA_BEFORE" ] && [ "$GUARD_SHA_BEFORE" = "$GUARD_SHA_AFTER" ] && [ "$A_AFTER_REBUILD" = "127.0.0.1" ]; then
  pass "(5) the guard survives a full dist/ rebuild+swap and still binds loopback (a dist patch would NOT)"
else
  fail "(5) the guard did not survive a dist/ rebuild (sha ${GUARD_SHA_BEFORE:-?} -> ${GUARD_SHA_AFTER:-?}, bind '${A_AFTER_REBUILD:-<none>}')"
fi

# ── (6) FAIL-OPEN on an unrecognised shape ───────────────────────────────────
IPC_SOCK="$WORK/ipc.sock"
if IPC_PATH="$IPC_SOCK" NODE_OPTIONS="--require \"$GUARD\"" node "$WORK/srv-ipc.js" >/dev/null 2>&1; then
  pass "(6) an unrecognised listen shape (unix socket) still starts — the guard fails OPEN on shape"
else
  fail "(6) the guard broke a unix-socket listen — it must never prevent a server from starting"
fi

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
