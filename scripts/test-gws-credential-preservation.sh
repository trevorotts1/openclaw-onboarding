#!/usr/bin/env bash
# ============================================================================
# test-gws-credential-preservation.sh  (v16.1.7)
#
# REGRESSION GUARD — the fleet update/install/verify path must NEVER cause a
# client's Google Workspace credential store to be cleared, re-keyed, or touched.
#
# PROVEN ROOT CAUSE of the v16.1.x wipe: the repo ships exactly ONE runtime gws
# call — `gws auth status` in 14-google-workspace-integration/qc-...sh. The
# onboarding verification gate (lib-onboarding-state.sh oc_gate_skill) runs that
# QC HEADLESS (`bash qc-*.sh >/dev/null 2>&1`, no TTY) and the watchdog/resume
# crons + the update path drive it over skill 14. With no TTY gws cannot decrypt
# its file keyring, so gws's OWN known failure mode rewrites
# ~/.config/gws/credentials.enc to credential_source:"none" — erasing the OAuth.
# The repo never deletes the file; the bare call is the only trigger surface.
#
# THIS TEST exercises the REAL repo code against a sandbox HOME seeded with fake
# credentials + a file-keyring key + gws-acct* stores + secrets/.env, with a fake
# `gws` on PATH that faithfully models gws's headless self-clearing. It asserts:
#   T1  the harness has TEETH        — a bare/unguarded `gws auth status` run
#                                       headless DOES wipe the seeded creds (so a
#                                       future regression that re-adds it is caught)
#   T2  real QC, headless            — creds survive BYTE-IDENTICAL, gws NEVER
#                                       invoked, keyring + gws-acct* + secrets/.env
#                                       untouched, credential_source stays valid
#   T3  real GATE (oc_gate_skill)    — driving the LIVE trigger path headless also
#                                       leaves every store byte-identical
#   T4  positive branch              — with an interactive opt-in + a healthy gws,
#                                       the auth probe STILL runs (QC not lobotomised)
#                                       and the read leaves creds byte-identical
#   T5  static invariants            — guarded call shape, keyring-backend pin not
#                                       dropped, and NO install/update/verify script
#                                       can rm/mv/chmod/chown/overwrite ~/.config/gws*
#                                       or issue gws remove/logout/revoke/delete
#   T6  resilience: shell env        — scripts/harden-gws-credential-resilience.sh
#                                       forces the file keyring backend for every
#                                       shell via APPEND-ONLY ~/.zshenv/.bashrc/
#                                       .profile blocks (user content preserved,
#                                       idempotent) so any bare gws cannot self-wipe
#   T7  resilience: gws-as wrapper   — installs a PATH wrapper that FORCES the file
#                                       backend even if the caller pre-set the
#                                       dangerous OS-keyring backend, routes named
#                                       accounts, and only ever `exec gws`
#   T8  resilience: off-box backup   — snapshots credentials.enc + the file-keyring
#                                       key off-box (secrets/backups/<box>-gws),
#                                       byte-identical + copy-only (live store never
#                                       mutated), private 600, change-gated
#
# Self-contained: bash + stdlib python3 only. No gateway / no real gws required.
# Consumes only repo file content (no untrusted GitHub event fields).
# ============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QC_REAL="$REPO_ROOT/14-google-workspace-integration/qc-google-workspace-integration.sh"
LIB_STATE="$REPO_ROOT/lib-onboarding-state.sh"
HARDENER="$REPO_ROOT/scripts/harden-gws-credential-resilience.sh"

PASS=0; FAIL=0
ok()   { printf '  \033[32m✓ PASS\033[0m — %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31m✗ FAIL\033[0m — %s\n' "$1"; FAIL=$((FAIL+1)); }
hdr()  { printf '\n\033[1m%s\033[0m\n' "$1"; }

[ -f "$QC_REAL" ]   || { echo "FATAL: QC not found at $QC_REAL"; exit 2; }
[ -f "$LIB_STATE" ] || { echo "FATAL: state lib not found at $LIB_STATE"; exit 2; }

sha() { python3 - "$1" <<'PY'
import hashlib,sys
try: print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())
except Exception: print("MISSING")
PY
}

# credential_source still valid (no account cleared to "none") ?
creds_valid() { python3 - "$1" <<'PY'
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: print("INVALID-JSON"); sys.exit(0)
srcs=[a.get("credential_source") for a in d.get("accounts",{}).values()]
print("VALID" if srcs and all(s and s!="none" for s in srcs) else "CLEARED")
PY
}

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
BIN="$SANDBOX/bin"; mkdir -p "$BIN"

# ── fake `gws` that models the real CLI ──────────────────────────────────────
#   FAKE_GWS_MODE=wipe (default): on `auth status`, models the headless
#       self-clearing failure — rewrites credentials.enc to credential_source
#       "none" and exits 1 (THE eraser).
#   FAKE_GWS_MODE=healthy: on `auth status`, prints "authenticated" exit 0,
#       touching NOTHING (a TTY/decryptable gws).
#   Every call appends to $GWS_INVOKED_FLAG so we can assert (non-)invocation.
cat > "$BIN/gws" <<'GWS'
#!/usr/bin/env bash
echo "INVOKED $*" >> "${GWS_INVOKED_FLAG:-/dev/null}"
if [ "${1:-} ${2:-}" = "auth status" ]; then
  if [ "${FAKE_GWS_MODE:-wipe}" = "healthy" ]; then
    echo "authenticated as workspace-user (active)"; exit 0
  fi
  CRED="$HOME/.config/gws/credentials.enc"
  if [ -f "$CRED" ]; then
    python3 - "$CRED" <<'PY'
import json,sys
p=sys.argv[1]
try: d=json.load(open(p))
except Exception: d={"accounts":{}}
for a in d.get("accounts",{}).values():
    a["credential_source"]="none"; a.pop("refresh_token",None)
json.dump(d,open(p,"w"))
PY
  fi
  echo "error: keyring locked (headless); credentials cleared" >&2
  exit 1
fi
exit 0
GWS
chmod +x "$BIN/gws"
# a node so the QC's `command -v node` assert does not FAIL (keep QC exit clean)
printf '#!/usr/bin/env bash\nexit 0\n' > "$BIN/node"; chmod +x "$BIN/node"

# ── seed a sandbox HOME exactly like a real client box ───────────────────────
seed_home() {
  local H="$1"
  rm -rf "$H"; mkdir -p "$H/.config/gws" "$H/.config/gws-acct-primary" \
    "$H/.config/gws-acct-secondary" "$H/.openclaw/secrets" \
    "$H/.openclaw/skills/14-google-workspace-integration"
  cat > "$H/.config/gws/credentials.enc" <<'JSON'
{"version":1,"accounts":{"acct-primary":{"credential_source":"oauth2","email":"workspace-user-1@example.test","refresh_token":"FAKE-RT-PRIMARY-0001"},"acct-secondary":{"credential_source":"oauth2","email":"workspace-user-2@example.test","refresh_token":"FAKE-RT-SECONDARY-0002"}}}
JSON
  # file-keyring key (the thing gws needs to decrypt; must stay byte-untouched)
  printf 'FAKE-FILE-KEYRING-KEY-BYTES-0xDEADBEEF\n' > "$H/.config/gws/keyring.key"
  printf '{"token":"FAKE-ACCT-PRIMARY"}\n'   > "$H/.config/gws-acct-primary/token.json"
  printf '{"token":"FAKE-ACCT-SECONDARY"}\n' > "$H/.config/gws-acct-secondary/token.json"
  # secrets/.env (sourced by the QC) — includes the keyring-backend export
  cat > "$H/.openclaw/secrets/.env" <<'ENV'
GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file
SOME_FAKE_API_KEY=sk-fake-0000
ENV
  chmod 600 "$H/.openclaw/secrets/.env"   # model real-box perms (also satisfies the chmod-600 QC gate)
  # installed SKILL.md so the "uses gws" warn passes (mentions gws)
  printf -- '---\nname: google-workspace-integration\n---\nUses the gws CLI.\n' \
    > "$H/.openclaw/skills/14-google-workspace-integration/SKILL.md"
  # the installed copy of the QC the gate globs+runs
  cp "$QC_REAL" "$H/.openclaw/skills/14-google-workspace-integration/qc-google-workspace-integration.sh"
}

# snapshot every credential store's sha (plain vars — bash 3.2 portable)
SNAP_CRED=""; SNAP_KEY=""; SNAP_ACCT1=""; SNAP_ACCT2=""; SNAP_ENV=""
snapshot() {
  local H="$1"
  SNAP_CRED="$(sha "$H/.config/gws/credentials.enc")"
  SNAP_KEY="$(sha "$H/.config/gws/keyring.key")"
  SNAP_ACCT1="$(sha "$H/.config/gws-acct-primary/token.json")"
  SNAP_ACCT2="$(sha "$H/.config/gws-acct-secondary/token.json")"
  SNAP_ENV="$(sha "$H/.openclaw/secrets/.env")"
}
assert_all_untouched() {
  local H="$1" label="$2" allok=1
  [ "$(sha "$H/.config/gws/credentials.enc")"       = "$SNAP_CRED" ] || allok=0
  [ "$(sha "$H/.config/gws/keyring.key")"           = "$SNAP_KEY"  ] || allok=0
  [ "$(sha "$H/.config/gws-acct-primary/token.json")"   = "$SNAP_ACCT1" ] || allok=0
  [ "$(sha "$H/.config/gws-acct-secondary/token.json")" = "$SNAP_ACCT2" ] || allok=0
  [ "$(sha "$H/.openclaw/secrets/.env")"            = "$SNAP_ENV"  ] || allok=0
  if [ "$allok" -eq 1 ]; then ok "$label — all credential stores BYTE-IDENTICAL"; else bad "$label — a credential store changed"; fi
  if [ "$(creds_valid "$H/.config/gws/credentials.enc")" = "VALID" ]; then
    ok "$label — credential_source stays valid (no account cleared)"
  else
    bad "$label — credential_source was CLEARED to none"
  fi
}

# ============================================================================
hdr "T1 — harness teeth: a BARE/unguarded \`gws auth status\` DOES wipe (headless)"
# ============================================================================
H="$SANDBOX/home-t1"; seed_home "$H"
VULN="$SANDBOX/qc-vulnerable.sh"
cat > "$VULN" <<'VULN'
#!/usr/bin/env bash
# the PRE-FIX shape — a bare, unguarded gws call
gws auth status 2>&1 | grep -qiE 'authenticated|active|logged'
VULN
chmod +x "$VULN"
INVOKED="$SANDBOX/invoked-t1"; : > "$INVOKED"
HOME="$H" PATH="$BIN:$PATH" GWS_INVOKED_FLAG="$INVOKED" FAKE_GWS_MODE=wipe \
  bash "$VULN" >/dev/null 2>&1 </dev/null
if [ "$(creds_valid "$H/.config/gws/credentials.enc")" = "CLEARED" ] && [ -s "$INVOKED" ]; then
  ok "vulnerable bare call wiped creds + invoked gws (detector works → real-QC tests have teeth)"
else
  bad "harness could not reproduce a wipe — the regression detector is INERT (fix the test)"
fi

# ============================================================================
hdr "T2 — REAL QC run headless (exactly as oc_gate_skill: bash qc >/dev/null 2>&1)"
# ============================================================================
H="$SANDBOX/home-t2"; seed_home "$H"; snapshot "$H"
INVOKED="$SANDBOX/invoked-t2"; : > "$INVOKED"
# unset opt-in + no TTY (</dev/null) → must SKIP the gws probe
env -u OC_GWS_AUTH_PROBE HOME="$H" PATH="$BIN:$PATH" GWS_INVOKED_FLAG="$INVOKED" \
  FAKE_GWS_MODE=wipe bash "$QC_REAL" >/dev/null 2>&1 </dev/null
if [ ! -s "$INVOKED" ]; then ok "headless QC NEVER invoked gws (probe skipped)"; else bad "headless QC invoked gws: $(cat "$INVOKED")"; fi
assert_all_untouched "$H" "T2"

# ============================================================================
hdr "T3 — REAL verification GATE oc_gate_skill (the live trigger path), headless"
# ============================================================================
H="$SANDBOX/home-t3"; seed_home "$H"; snapshot "$H"
INVOKED="$SANDBOX/invoked-t3"; : > "$INVOKED"
(
  set +e
  export HOME="$H" PATH="$BIN:$PATH" GWS_INVOKED_FLAG="$INVOKED" FAKE_GWS_MODE=wipe
  export OC_CONFIG="$H/.openclaw" OC_SKILLS_DIR="$H/.openclaw/skills"
  export ONBOARDING_STATE_FILE="$H/.openclaw/.onboarding-state.json"
  unset OC_GWS_AUTH_PROBE
  # shellcheck disable=SC1090
  source "$LIB_STATE"
  oc_state_seed "$OC_SKILLS_DIR" >/dev/null 2>&1 || true
  oc_gate_skill 14-google-workspace-integration >/dev/null 2>&1 </dev/null || true
) </dev/null
if [ ! -s "$INVOKED" ]; then ok "oc_gate_skill ran QC headless WITHOUT invoking gws"; else bad "oc_gate_skill invoked gws: $(cat "$INVOKED")"; fi
assert_all_untouched "$H" "T3"

# ============================================================================
hdr "T4 — positive branch: opt-in + healthy gws → probe STILL runs, creds intact"
# ============================================================================
H="$SANDBOX/home-t4"; seed_home "$H"; snapshot "$H"
INVOKED="$SANDBOX/invoked-t4"; : > "$INVOKED"
OC_GWS_AUTH_PROBE=1 HOME="$H" PATH="$BIN:$PATH" GWS_INVOKED_FLAG="$INVOKED" \
  FAKE_GWS_MODE=healthy bash "$QC_REAL" >/dev/null 2>&1 </dev/null
if [ -s "$INVOKED" ]; then ok "opt-in path DID invoke the auth probe (QC not lobotomised)"; else bad "opt-in path did not run the auth probe"; fi
assert_all_untouched "$H" "T4"

# ============================================================================
hdr "T5 — static source invariants"
# ============================================================================
# (a) the ONLY EXECUTABLE `gws auth status` in the repo lives in the QC, guarded.
#     (comments + human-readable messages and this test file are not executions.)
AUTH_SITES="$(python3 - "$REPO_ROOT" <<'PY'
import os,re,sys
root=sys.argv[1]; SELF="scripts/test-gws-credential-preservation.sh"
for dp,dn,fn in os.walk(root):
    if '/.git' in dp: continue
    for f in fn:
        if not (f.endswith('.sh') or f.endswith('.py')): continue
        rel=os.path.relpath(os.path.join(dp,f),root)
        if rel==SELF: continue
        for n,l in enumerate(open(os.path.join(dp,f),errors='ignore').read().splitlines(),1):
            if 'gws auth status' not in l: continue
            s=l.strip()
            if s.startswith('#'): continue                          # comment
            if re.match(r'(yellow|green|red|echo|printf)\b', s):     # message string
                continue
            print(f"{rel}:{n}: {s}")
PY
)"
N_HITS="$(printf '%s\n' "$AUTH_SITES" | grep -c . || true)"
if [ "$N_HITS" -eq 1 ] && printf '%s' "$AUTH_SITES" | grep -q 'qc-google-workspace-integration.sh'; then
  ok "exactly ONE executable \`gws auth status\` in the repo, and it is in the skill-14 QC"
else
  bad "unexpected executable \`gws auth status\` call site(s): $AUTH_SITES"
fi
# (b) that call is guarded by BOTH a TTY/opt-in check AND a creds-present check
if grep -q 'gws_creds_present' "$QC_REAL" \
   && grep -qE '\[ -t 0 \]' "$QC_REAL" \
   && grep -q 'OC_GWS_AUTH_PROBE' "$QC_REAL"; then
  ok "QC gws probe is guarded (TTY OR opt-in) AND creds-present"
else
  bad "QC gws probe guard tokens missing"
fi
# verify the guard actually WRAPS the call: the line before `gws auth status`
# inside the QC must be the guard `if { [ -t 0 ] ... } && gws_creds_present; then`
if python3 - "$QC_REAL" <<'PY'
import sys,re
src=open(sys.argv[1]).read().splitlines()
# only the EXECUTABLE occurrence (skip comments + message strings)
def executable(l):
    s=l.strip()
    if 'gws auth status' not in l: return False
    if s.startswith('#'): return False
    if re.match(r'(yellow|green|red|echo|printf)\b', s): return False
    return True
ix=[i for i,l in enumerate(src) if executable(l)]
ok = len(ix)==1
if ok:
    i=ix[0]
    # walk up to the nearest control keyword; must be the guarded `if`
    guard=False
    for j in range(i-1,max(-1,i-6),-1):
        if re.search(r'^\s*if\s', src[j]) and 'gws_creds_present' in src[j] and ('-t 0' in src[j] or 'OC_GWS_AUTH_PROBE' in src[j]):
            guard=True; break
        if re.search(r'^\s*(if|while|until|for)\s', src[j]):
            break
    ok = guard
sys.exit(0 if ok else 1)
PY
then ok "the \`gws auth status\` call is lexically INSIDE the credential-safe guard"
else bad "the \`gws auth status\` call is NOT wrapped by the guard"
fi
# (c) the file-keyring backend is pinned + exported in the QC and not droppable
if grep -qE 'GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND:=file' "$QC_REAL" \
   && grep -q 'export GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND' "$QC_REAL"; then
  ok "QC pins + exports GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file (set-if-unset; never overrides)"
else
  bad "QC does not pin/export the keyring backend"
fi
# (d) NO install/update/verify script issues a store-mutating gws subcommand
#     (executable lines only — skip comments + this test file's own docs).
DESTRUCTIVE_GWS="$(python3 - "$REPO_ROOT" <<'PY'
import os,re,sys
root=sys.argv[1]; SELF="scripts/test-gws-credential-preservation.sh"
pat=re.compile(r'\bgws\s+(auth\s+)?(remove|logout|revoke|delete|reset|clear|unlink|signout|sign-out)\b')
for dp,dn,fn in os.walk(root):
    if '/.git' in dp: continue
    for f in fn:
        if not (f.endswith('.sh') or f.endswith('.py')): continue
        rel=os.path.relpath(os.path.join(dp,f),root)
        if rel==SELF: continue
        for n,l in enumerate(open(os.path.join(dp,f),errors='ignore').read().splitlines(),1):
            s=l.strip()
            if s.startswith('#'): continue
            if pat.search(l): print(f"{rel}:{n}: {s}")
PY
)"
if [ -z "$DESTRUCTIVE_GWS" ]; then
  ok "no \`gws ... remove/logout/revoke/delete/reset/clear/unlink\` anywhere in the repo"
else
  bad "store-mutating gws subcommand found: $DESTRUCTIVE_GWS"
fi
# (e) NO script does a destructive filesystem op against ~/.config/gws*
#     (rm / mv / chmod / chown / truncate / tee / sed -i / overwrite redirect).
#     Read-only probes (ls, cat, test, grep, [ -f ) are allowed.
MUT="$(python3 - "$REPO_ROOT" <<'PY'
import os,re,sys
root=sys.argv[1]
# destructive op tokens that, on a line ALSO touching .config/gws, would mutate it
destr=re.compile(r'(\brm\b|\bmv\b|\bchmod\b|\bchown\b|\btruncate\b|\btee\b(?!\s+-a)|sed\s+-i|>\s*"?\$?\{?HOME)')
gwspath=re.compile(r'\.config/gws')
hits=[]
SELF="scripts/test-gws-credential-preservation.sh"
for dp,dn,fn in os.walk(root):
    if '/.git' in dp: continue
    for f in fn:
        if not (f.endswith('.sh') or f.endswith('.py')): continue
        rel=os.path.relpath(os.path.join(dp,f),root)
        if rel==SELF: continue
        try: lines=open(os.path.join(dp,f),errors='ignore').read().splitlines()
        except Exception: continue
        for n,l in enumerate(lines,1):
            if not gwspath.search(l): continue
            s=l.strip()
            if s.startswith('#'): continue
            # allow a redirect that only sends fd2/stdout to /dev/null (2>/dev/null)
            tmp=re.sub(r'2>\s*/dev/null|>\s*/dev/null','',l)
            if destr.search(tmp):
                hits.append(f"{rel}:{n}: {s}")
for h in hits: print(h)
PY
)"
if [ -z "$MUT" ]; then
  ok "no destructive filesystem op (rm/mv/chmod/chown/truncate/tee/sed -i/overwrite) targets ~/.config/gws*"
else
  bad "destructive op against ~/.config/gws* found:\n$MUT"
fi
# (f) no script UNSETS or EMPTIES the keyring-backend export (req #3: never drop it)
DROP="$(grep -rnE 'unset[[:space:]]+GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND|GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=("")?[[:space:]]*$' \
  --include='*.sh' --include='*.py' "$REPO_ROOT" || true)"
if [ -z "$DROP" ]; then
  ok "no script unsets or empties GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND"
else
  bad "a script drops the keyring-backend export:\n$DROP"
fi
# (g) req #3: if a script writes a user shell dotfile, it must APPEND (>>), never
#     OVERWRITE (>) — an overwrite could drop the client's KEYRING_BACKEND export.
OVR="$(python3 - "$REPO_ROOT" <<'PY'
import os,re,sys
root=sys.argv[1]
dot=re.compile(r'>\s*"?\$?\{?(HOME|\~)[^>]*?/\.(zshenv|zshrc|bashrc|bash_profile|profile)\b')
appendok=re.compile(r'>>')
hits=[]
for dp,dn,fn in os.walk(root):
    if '/.git' in dp: continue
    for f in fn:
        if not f.endswith('.sh'): continue
        rel=os.path.relpath(os.path.join(dp,f),root)
        try: lines=open(os.path.join(dp,f),errors='ignore').read().splitlines()
        except Exception: continue
        for n,l in enumerate(lines,1):
            s=l.strip()
            if s.startswith('#'): continue
            if dot.search(l) and not appendok.search(l):
                hits.append(f"{rel}:{n}: {s}")
for h in hits: print(h)
PY
)"
if [ -z "$OVR" ]; then
  ok "no install/update script OVERWRITES a user shell dotfile (append-only / read-only)"
else
  bad "a script overwrites a user shell dotfile (could drop KEYRING_BACKEND export):\n$OVR"
fi

# perms helper (portable across macOS `stat -f` and GNU `stat -c`)
perms() { stat -f '%Lp' "$1" 2>/dev/null || stat -c '%a' "$1" 2>/dev/null || echo "?"; }

# ============================================================================
hdr "T6 — resilience hardener: forces the FILE keyring backend for every shell"
# ============================================================================
# The fleet-wide guard: scripts/harden-gws-credential-resilience.sh must bake the
# file backend into the user's shell env (append-only ~/.zshenv etc.) so that
# ANY bare gws — a doc/EXAMPLES step, an agent shell, a cron — inherits it and can
# never self-wipe. Drives the REAL hardener against a sandbox HOME, headless.
if [ ! -f "$HARDENER" ]; then
  bad "harden-gws-credential-resilience.sh MISSING at $HARDENER (fleet resilience not installed)"
else
  H="$SANDBOX/home-t6"; rm -rf "$H"
  mkdir -p "$H/.config/gws" "$H/.openclaw"
  printf 'ORIGINAL-USER-ZSHENV-CONTENT\n' > "$H/.zshenv"          # pre-existing user dotfile
  printf '{"version":1,"accounts":{"a":{"credential_source":"oauth2","refresh_token":"RT-T6"}}}\n' \
    > "$H/.config/gws/credentials.enc"
  printf 'KEYBYTES-T6\n' > "$H/.config/gws/.encryption_key"
  HOME="$H" OC_CONFIG="$H/.openclaw" bash "$HARDENER" >/dev/null 2>&1 </dev/null
  # (a) ~/.zshenv now forces the backend, and the ORIGINAL content is preserved.
  if grep -q 'GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND' "$H/.zshenv" 2>/dev/null \
     && grep -qE 'GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND:?=file' "$H/.zshenv" 2>/dev/null \
     && grep -q 'ORIGINAL-USER-ZSHENV-CONTENT' "$H/.zshenv" 2>/dev/null; then
    ok "T6 — ~/.zshenv forces file backend AND preserves the user's original content (append-only)"
  else
    bad "T6 — ~/.zshenv missing the backend export or clobbered the user's content"
  fi
  # (b) bash + profile shells covered too.
  if grep -q 'GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND' "$H/.bashrc" 2>/dev/null \
     && grep -q 'GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND' "$H/.profile" 2>/dev/null; then
    ok "T6 — ~/.bashrc and ~/.profile also export the file backend (non-zsh shells covered)"
  else
    bad "T6 — ~/.bashrc or ~/.profile missing the backend export"
  fi
  # (c) idempotent: a second run does NOT duplicate the managed block.
  HOME="$H" OC_CONFIG="$H/.openclaw" bash "$HARDENER" >/dev/null 2>&1 </dev/null
  _n_block="$(grep -c 'openclaw:gws-keyring-backend (managed —' "$H/.zshenv" 2>/dev/null || echo 0)"
  if [ "$_n_block" -eq 1 ]; then
    ok "T6 — re-running the hardener is idempotent (exactly one managed block in ~/.zshenv)"
  else
    bad "T6 — hardener not idempotent: $_n_block managed blocks in ~/.zshenv"
  fi
fi

# ============================================================================
hdr "T7 — resilience hardener: installs a gws-as wrapper that FORCES file backend"
# ============================================================================
# The wrapper is the belt-and-suspenders for non-zsh / non-interactive shells and
# for explicit scripted/cron calls: it must force the file backend even if the
# caller pre-set the dangerous OS-keyring backend, and must only ever `exec gws`.
if [ ! -f "$HARDENER" ]; then
  bad "hardener missing — cannot verify gws-as wrapper"
else
  H="$SANDBOX/home-t7"; rm -rf "$H"; mkdir -p "$H/.config/gws" "$H/.openclaw" "$H/.config/gws-acct-sales"
  printf '{"version":1,"accounts":{}}\n' > "$H/.config/gws/credentials.enc"
  HOME="$H" OC_CONFIG="$H/.openclaw" bash "$HARDENER" >/dev/null 2>&1 </dev/null
  WRAP="$H/.openclaw/bin/gws-as"
  if [ -x "$WRAP" ]; then
    ok "T7 — gws-as wrapper installed + executable at ~/.openclaw/bin/gws-as"
  else
    bad "T7 — gws-as wrapper not installed at ~/.openclaw/bin/gws-as"
  fi
  # a fake gws that echoes the env the wrapper hands it
  BIN7="$SANDBOX/bin7"; mkdir -p "$BIN7"
  printf '#!/usr/bin/env bash\necho "BK=${GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND:-unset} CD=${GOOGLE_WORKSPACE_CLI_CONFIG_DIR:-unset} A=$*"\n' > "$BIN7/gws"
  chmod +x "$BIN7/gws"
  if [ -x "$WRAP" ]; then
    # even with the DANGEROUS keyring backend pre-set, the wrapper must force file
    OUT_DEF="$(GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=keyring HOME="$H" PATH="$BIN7:$PATH" bash "$WRAP" default drive files list 2>&1)"
    OUT_ACCT="$(env -u GOOGLE_WORKSPACE_CLI_CONFIG_DIR HOME="$H" PATH="$BIN7:$PATH" bash "$WRAP" sales gmail messages list 2>&1)"
    if printf '%s' "$OUT_DEF" | grep -q 'BK=file'; then
      ok "T7 — gws-as forces BACKEND=file even when the caller pre-set keyring (self-wipe blocked)"
    else
      bad "T7 — gws-as did NOT force the file backend: $OUT_DEF"
    fi
    if printf '%s' "$OUT_ACCT" | grep -q 'gws-acct-sales'; then
      ok "T7 — gws-as routes a named account to its per-account config dir"
    else
      bad "T7 — gws-as did not route the named account: $OUT_ACCT"
    fi
  fi
  # static: the installed wrapper forces file + only execs gws (no destructive verb)
  if grep -qE 'GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file' "$WRAP" 2>/dev/null \
     && grep -qE '^\s*exec gws ' "$WRAP" 2>/dev/null \
     && ! grep -qE '\bgws +(auth +)?(remove|logout|revoke|delete|reset|clear|unlink)\b' "$WRAP" 2>/dev/null \
     && ! grep -q 'gws auth status' "$WRAP" 2>/dev/null; then
    ok "T7 — installed wrapper pins file backend, only execs gws, no destructive/self-clearing verb"
  else
    bad "T7 — installed wrapper shape is unsafe"
  fi
fi

# ============================================================================
hdr "T8 — resilience hardener: off-box snapshot, byte-identical, source untouched"
# ============================================================================
# A wipe by ANY path must be recoverable: the hardener snapshots credentials.enc
# + its file-keyring key off-box (secrets/backups/<box>-gws) WITHOUT ever mutating
# the live store, only when creds are present + changed.
if [ ! -f "$HARDENER" ]; then
  bad "hardener missing — cannot verify off-box backup"
else
  H="$SANDBOX/home-t8"; rm -rf "$H"; mkdir -p "$H/.config/gws" "$H/.openclaw"
  printf '{"version":1,"accounts":{"a":{"credential_source":"oauth2","refresh_token":"RT-T8"}}}\n' \
    > "$H/.config/gws/credentials.enc"
  printf 'KEYBYTES-T8\n' > "$H/.config/gws/.encryption_key"
  SRC_CRED="$(sha "$H/.config/gws/credentials.enc")"
  SRC_KEY="$(sha "$H/.config/gws/.encryption_key")"
  HOME="$H" OC_CONFIG="$H/.openclaw" bash "$HARDENER" >/dev/null 2>&1 </dev/null
  # live store never mutated
  if [ "$(sha "$H/.config/gws/credentials.enc")" = "$SRC_CRED" ] \
     && [ "$(sha "$H/.config/gws/.encryption_key")" = "$SRC_KEY" ]; then
    ok "T8 — hardener left the LIVE gws store byte-identical (backup is copy-only, never a move)"
  else
    bad "T8 — hardener mutated the live gws store"
  fi
  SNAP_DIR="$(ls -1dt "$H/.openclaw/secrets/backups/"*-gws/*/ 2>/dev/null | head -1 || true)"
  if [ -n "$SNAP_DIR" ] \
     && [ "$(sha "${SNAP_DIR}credentials.enc")" = "$SRC_CRED" ] \
     && [ "$(sha "${SNAP_DIR}.encryption_key")" = "$SRC_KEY" ]; then
    ok "T8 — off-box snapshot holds credentials.enc + the file-keyring key, byte-identical (restorable)"
  else
    bad "T8 — off-box snapshot missing or not byte-identical to the source store"
  fi
  # snapshot files are private (600)
  if [ -n "$SNAP_DIR" ] && [ "$(perms "${SNAP_DIR}credentials.enc")" = "600" ]; then
    ok "T8 — snapshot credential files are private (chmod 600)"
  else
    bad "T8 — snapshot credential perms are not 600 (got $( [ -n "$SNAP_DIR" ] && perms "${SNAP_DIR}credentials.enc" ))"
  fi
  # idempotent: unchanged creds → no second snapshot; rotated creds → new snapshot
  HOME="$H" OC_CONFIG="$H/.openclaw" bash "$HARDENER" >/dev/null 2>&1 </dev/null
  N1="$(ls -1d "$H/.openclaw/secrets/backups/"*-gws/*/ 2>/dev/null | grep -c . || true)"
  sleep 1
  printf '{"version":1,"accounts":{"a":{"credential_source":"oauth2","refresh_token":"RT-T8-ROTATED"}}}\n' \
    > "$H/.config/gws/credentials.enc"
  HOME="$H" OC_CONFIG="$H/.openclaw" bash "$HARDENER" >/dev/null 2>&1 </dev/null
  N2="$(ls -1d "$H/.openclaw/secrets/backups/"*-gws/*/ 2>/dev/null | grep -c . || true)"
  if [ "$N1" -eq 1 ] && [ "$N2" -eq 2 ]; then
    ok "T8 — snapshot is change-gated (no dup when unchanged; a fresh snapshot when creds rotate)"
  else
    bad "T8 — snapshot change-gating wrong (unchanged→$N1 expected 1; rotated→$N2 expected 2)"
  fi
fi

# ============================================================================
hdr "RESULT: $PASS passed | $FAIL failed"
# ============================================================================
[ "$FAIL" -eq 0 ] || { printf '\033[31mgws-credential-preservation guard FAILED\033[0m\n'; exit 1; }
printf '\033[32mgws-credential-preservation guard PASS\033[0m\n'
exit 0
