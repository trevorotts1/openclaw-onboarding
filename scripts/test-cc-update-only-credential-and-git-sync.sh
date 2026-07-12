#!/usr/bin/env bash
# ============================================================================
# test-cc-update-only-credential-and-git-sync.sh
#
# REGRESSION GUARD for two Skill-32 installer defects fixed together (D6+D7),
# both in 32-command-center-setup/scripts/run-full-install.sh:
#
#   D6 — cc_write_env_local() called cc_mirror_api_auth_to_agent_secrets()
#        UNCONDITIONALLY, including during --update-only (the mode a code-only
#        fleet roll drives via update-skills.sh's CC refresh). The mirror WRITES
#        into $OC_ROOT/secrets/.env whenever MC_API_TOKEN/WEBHOOK_SECRET are
#        absent or empty there — exactly the store
#        scripts/fleet-roll/preflight-credential-guard.sh fingerprints. A
#        code-only roll that never intended to touch credentials would mutate
#        the guarded secrets store mid-roll, the guard's do_verify would see
#        CONTENT CHANGED, and the runbook would force-revert an otherwise
#        healthy box. Fix: gate the mirror call on UPDATE_ONLY — it now runs
#        ONLY on a full install (first-time provisioning); --update-only never
#        writes the credential store. The existing loud post-condition still
#        catches a genuinely under-provisioned update-only box.
#
#   D7 — Both git-refresh call sites used a bare `git pull --ff-only`, which
#        ABORTS on a DETACHED HEAD ("You are not currently on a branch") — the
#        shape of a client Command Center pinned to a version tag. The abort
#        was swallowed to a WARN and the stale checkout kept, so npm install /
#        db:push / build all ran against OLD code and the CC never advanced
#        (observed on multiple client Command Center boxes). Fix: cc_git_sync_to_default_branch()
#        fetches + re-attaches (checkout -B) when detached, or fast-forward
#        merges when already on a branch — never `reset --hard` / `checkout -f`
#        / `clean -f`, so local tracked patches and gitignored files survive,
#        and a genuine conflict is refused non-destructively exactly like the
#        old ff-only abort was.
#
# THIS TEST extracts the REAL functions verbatim (via awk, function-name
# anchored so it survives line-number drift) from the REAL edited
# run-full-install.sh and exercises them against sandboxed HOMEs / a real local
# git remote — no reimplementation of the logic under test.
#
# D6 tests:
#   T1  TEETH               — the OLD unconditional call (same real function,
#                              called the way the OLD code called it) DOES
#                              mutate secrets/.env in update-only-shaped states
#                              (absent + empty-placeholder) — proves the drift
#                              scenario is real, not moot.
#   T2  absent, update-only  — real (FIXED) cc_write_env_local, UPDATE_ONLY=true,
#                              secrets/.env has NO MC_API_TOKEN/WEBHOOK_SECRET ->
#                              file byte-identical after the call (never created
#                              or appended to).
#   T3  empty, update-only   — same, but secrets/.env holds empty placeholders
#                              (MC_API_TOKEN=/WEBHOOK_SECRET=) -> byte-identical
#                              (this is the exact "line count unchanged, content
#                              rewritten" drift signature from the report).
#   T4  present, update-only — secrets/.env already has real values -> preserved
#                              byte-identical (unchanged behavior).
#   T5  full install (NOT update-only) — mirror STILL runs and provisions the
#                              agent secrets store from .env.local, identical to
#                              pre-fix behavior -> first-time provisioning is
#                              NOT broken by the gate.
#   T6  guard stays STRICT   — using the REAL scripts/fleet-roll/
#                              preflight-credential-guard.sh: snapshot -> run
#                              cc_write_env_local(UPDATE_ONLY=true) -> verify
#                              PASSES (no drift from this call site during a
#                              roll); a SEPARATE genuine external mutation
#                              between snapshot/verify is STILL caught (nonzero)
#                              -- the guard itself is untouched and not weakened.
#
# D7 tests:
#   T7  TEETH               — a bare `git pull --ff-only` on a detached-HEAD
#                              checkout (the OLD call shape) FAILS (nonzero) and
#                              leaves HEAD unmoved -- proves the bug is real.
#   T8  detached -> synced   — cc_git_sync_to_default_branch() on the same
#                              detached checkout returns 0, HEAD advances to the
#                              latest origin commit, AND an uncommitted local
#                              edit to an untouched-by-upstream tracked file
#                              (the "local patch" shape) survives unreverted.
#   T9  attached fast-forward — already on a branch, behind origin -> syncs
#                              cleanly (regression check: the non-detached path
#                              still works as before).
#   T10 conflict refused, non-destructively — a local uncommitted edit that
#                              CONFLICTS with the incoming commit on the same
#                              file -> the helper returns nonzero, HEAD/working
#                              tree are LEFT UNCHANGED (no reset --hard, no lost
#                              work) -- identical safety posture to the old
#                              ff-only abort.
#   T11 gitignored files untouched -- a gitignored .env.local-shaped file
#                              survives a successful sync byte-identical.
#   T12 static: no destructive git verbs in the helper's source (reset --hard /
#                              checkout -f / clean -f never appear).
#
# Self-contained: bash + git + a hasher. No gateway, no real credentials, no
# network (all git remotes are local file paths).
# ============================================================================
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
INSTALLER="$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh"
GUARD="$REPO_ROOT/scripts/fleet-roll/preflight-credential-guard.sh"

[ -f "$INSTALLER" ] || { echo "FATAL: installer not found at $INSTALLER"; exit 2; }
[ -f "$GUARD" ]     || { echo "FATAL: preflight guard not found at $GUARD"; exit 2; }

PASS=0; FAIL=0
ok()  { printf '  \033[32m✓ PASS\033[0m — %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  \033[31m✗ FAIL\033[0m — %s\n' "$1"; FAIL=$((FAIL+1)); }
hdr() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# Extract ONE function verbatim, anchored by name (survives line-number drift).
# Prints nothing (and the caller should treat it as fatal) if not found.
extract_func() {
  local name="$1" file="$2"
  awk -v pat="^${name}\\\\(\\\\) \\\\{" '
    $0 ~ pat { p=1 }
    p { print }
    p && /^}/ { exit }
  ' "$file"
}

FRAG="$(mktemp)"
for fn in log cc_env_has_nonempty cc_env_set_if_absent cc_env_get \
          cc_mirror_api_auth_to_agent_secrets cc_resolve_sovereign_model \
          cc_resolve_judge_model cc_write_env_local cc_git_sync_to_default_branch; do
  body="$(extract_func "$fn" "$INSTALLER")"
  if [ -z "$body" ]; then
    echo "FATAL: could not extract function '$fn' from $INSTALLER (name/shape drift?)"
    exit 2
  fi
  printf '%s\n\n' "$body" >> "$FRAG"
done

# ============================================================================
# PART D6 — credential-mirror update-only gate
# ============================================================================

# Build a sandbox box: OC_ROOT (agent secrets live under $OC_ROOT/secrets/.env)
# and DASHBOARD_DIR (.env.local lives here). OC_CONFIG points at a NONEXISTENT
# file so cc_resolve_sovereign_model / cc_resolve_judge_model short-circuit to
# empty (their own documented no-config branch) — real code, exercised, just
# steered down its already-existing "nothing configured" path.
make_box() {
  local box; box="$(mktemp -d)"
  mkdir -p "$box/oc-root/secrets" "$box/oc-root/workspace" "$box/dashboard"
  printf '%s' "$box"
}

sha() { (command -v shasum >/dev/null 2>&1 && shasum -a 256 || sha256sum) < "$1" 2>/dev/null | awk '{print $1}'; }

# Run cc_write_env_local (or, for T1, the bare pre-fix mirror call) for real in
# a subshell with the box's vars wired + the extracted fragment sourced.
run_write_env_local() {
  local box="$1" update_only="$2"
  ( set -u
    OC_ROOT="$box/oc-root"
    DASHBOARD_DIR="$box/dashboard"
    OC_CONFIG="$box/oc-root/no-such-openclaw.json"
    STATE_FILE="$box/oc-root/workspace/no-such-state.json"
    LOG_FILE="$box/oc-root/workspace/install.log"
    UPDATE_ONLY="$update_only"
    # shellcheck disable=SC1090
    source "$FRAG"
    cc_write_env_local >/dev/null 2>&1
  )
}

# T1 — the OLD (pre-fix) call shape: cc_mirror_api_auth_to_agent_secrets called
# UNCONDITIONALLY regardless of UPDATE_ONLY, exactly as the reported defect
# describes. Proves the scenario has teeth before trusting T2/T3's pass.
hdr "T1 — teeth: the OLD unconditional mirror call DOES mutate secrets/.env"
BOX="$(make_box)"
printf 'GATEWAY_TOKEN=abc\nMC_API_TOKEN=tok-from-dot-env-local\nWEBHOOK_SECRET=whs-from-dot-env-local\n' \
  > "$BOX/dashboard/.env.local"
# state B: agent secrets file absent entirely
BEFORE_EXISTS=0; [ -f "$BOX/oc-root/secrets/.env" ] && BEFORE_EXISTS=1
( OC_ROOT="$BOX/oc-root"; LOG_FILE="$BOX/oc-root/workspace/install.log"
  # shellcheck disable=SC1090
  source "$FRAG"
  cc_mirror_api_auth_to_agent_secrets "$BOX/dashboard/.env.local" >/dev/null 2>&1
)
AFTER_HAS=0
grep -q '^MC_API_TOKEN=tok-from-dot-env-local$' "$BOX/oc-root/secrets/.env" 2>/dev/null && AFTER_HAS=1
if [ "$BEFORE_EXISTS" -eq 0 ] && [ "$AFTER_HAS" -eq 1 ]; then
  ok "T1: unconditional mirror call DOES write secrets/.env from an absent state — scenario is real"
else
  bad "T1: unconditional mirror call did not mutate secrets/.env as expected (harness broken)"
fi
rm -rf "$BOX"

# T2 — FIXED cc_write_env_local, UPDATE_ONLY=true, secrets/.env ABSENT
hdr "T2 — fixed: --update-only + absent agent secrets -> NO mutation"
BOX="$(make_box)"
printf 'MC_API_TOKEN=tok-value\nWEBHOOK_SECRET=whs-value\n' > "$BOX/dashboard/.env.local"
run_write_env_local "$BOX" "true"
if [ ! -e "$BOX/oc-root/secrets/.env" ]; then
  ok "T2: secrets/.env still does not exist after --update-only run (mirror never invoked)"
else
  bad "T2: secrets/.env was CREATED during --update-only (D6 regression) — content: $(cat "$BOX/oc-root/secrets/.env" 2>/dev/null | tr '\n' ';')"
fi
rm -rf "$BOX"

# T3 — FIXED cc_write_env_local, UPDATE_ONLY=true, secrets/.env has EMPTY
# placeholders (the exact "line count unchanged, content rewritten" drift shape)
hdr "T3 — fixed: --update-only + empty placeholders -> byte-identical"
BOX="$(make_box)"
printf 'MC_API_TOKEN=tok-value\nWEBHOOK_SECRET=whs-value\n' > "$BOX/dashboard/.env.local"
printf 'MC_API_TOKEN=\nWEBHOOK_SECRET=\nSOME_OTHER=keep-me\n' > "$BOX/oc-root/secrets/.env"
chmod 600 "$BOX/oc-root/secrets/.env" 2>/dev/null || true
BEFORE_SHA="$(sha "$BOX/oc-root/secrets/.env")"
run_write_env_local "$BOX" "true"
AFTER_SHA="$(sha "$BOX/oc-root/secrets/.env")"
if [ "$BEFORE_SHA" = "$AFTER_SHA" ]; then
  ok "T3: secrets/.env byte-identical after --update-only run (empty placeholders untouched)"
else
  bad "T3: secrets/.env CHANGED during --update-only despite UPDATE_ONLY=true (D6 regression) — before=$BEFORE_SHA after=$AFTER_SHA"
fi
rm -rf "$BOX"

# T4 — FIXED cc_write_env_local, UPDATE_ONLY=true, secrets/.env already has
# real values (state A) -> trivially preserved (sanity check, not the main bug)
hdr "T4 — fixed: --update-only + already-provisioned agent secrets -> preserved"
BOX="$(make_box)"
printf 'MC_API_TOKEN=tok-value\nWEBHOOK_SECRET=whs-value\n' > "$BOX/dashboard/.env.local"
printf 'MC_API_TOKEN=already-set-tok\nWEBHOOK_SECRET=already-set-whs\n' > "$BOX/oc-root/secrets/.env"
chmod 600 "$BOX/oc-root/secrets/.env" 2>/dev/null || true
BEFORE_SHA="$(sha "$BOX/oc-root/secrets/.env")"
run_write_env_local "$BOX" "true"
AFTER_SHA="$(sha "$BOX/oc-root/secrets/.env")"
[ "$BEFORE_SHA" = "$AFTER_SHA" ] && ok "T4: already-provisioned agent secrets stay byte-identical" \
                                   || bad "T4: already-provisioned agent secrets CHANGED (unexpected)"
rm -rf "$BOX"

# T5 — full install (UPDATE_ONLY=false): mirror STILL runs and provisions —
# first-time provisioning must be UNCHANGED by the gate.
hdr "T5 — regression check: FULL install (not --update-only) still provisions agent secrets"
BOX="$(make_box)"
printf 'MC_API_TOKEN=tok-value\nWEBHOOK_SECRET=whs-value\n' > "$BOX/dashboard/.env.local"
run_write_env_local "$BOX" "false"
if grep -q '^MC_API_TOKEN=tok-value$' "$BOX/oc-root/secrets/.env" 2>/dev/null \
   && grep -q '^WEBHOOK_SECRET=whs-value$' "$BOX/oc-root/secrets/.env" 2>/dev/null; then
  ok "T5: full install still mirrors MC_API_TOKEN + WEBHOOK_SECRET into agent secrets (provisioning intact)"
else
  bad "T5: full install FAILED to provision agent secrets — D6 fix broke first-time provisioning: $(cat "$BOX/oc-root/secrets/.env" 2>/dev/null | tr '\n' ';')"
fi
rm -rf "$BOX"

# T6 — the REAL preflight-credential-guard.sh, driven around the REAL fixed
# call, during a simulated --update-only roll: verify must PASS (no drift from
# this call site) — and a genuine SEPARATE external mutation between snapshot
# and verify must STILL be caught (guard stays strict, not neutered).
hdr "T6 — guard stays STRICT: no drift from the fixed update-only call, but real drift still refused"
BOX="$(make_box)"
printf 'MC_API_TOKEN=tok-value\nWEBHOOK_SECRET=whs-value\n' > "$BOX/dashboard/.env.local"
# secrets/.env starts ABSENT (the exact roll-time state that used to drift)
BK="$BOX/guard-backup"
STORESFILE="$BOX/stores.tsv"
printf 'openclaw-secrets-env\t%s\n' "$BOX/oc-root/secrets/.env" > "$STORESFILE"
ENVKEYSFILE="$BOX/envkeys.txt"; : > "$ENVKEYSFILE"   # no live-env keys watched here
PREFLIGHT_HOME="$BOX" PREFLIGHT_STORES_FILE="$STORESFILE" PREFLIGHT_ENV_KEYS_FILE="$ENVKEYSFILE" \
  bash "$GUARD" snapshot "$BK" >/dev/null 2>&1
run_write_env_local "$BOX" "true"
if PREFLIGHT_HOME="$BOX" PREFLIGHT_STORES_FILE="$STORESFILE" PREFLIGHT_ENV_KEYS_FILE="$ENVKEYSFILE" \
   bash "$GUARD" verify "$BK" >/dev/null 2>&1; then
  ok "T6a: preflight-credential-guard verify PASSES around the fixed --update-only call (no false revert)"
else
  bad "T6a: preflight-credential-guard verify FAILED around the fixed call (D6 not actually fixed for the guard's real fingerprint)"
fi
# now cause a genuine, unrelated drift and confirm the guard STILL refuses
printf 'MC_API_TOKEN=some-rotated-value\n' > "$BOX/oc-root/secrets/.env"
chmod 600 "$BOX/oc-root/secrets/.env" 2>/dev/null || true
if PREFLIGHT_HOME="$BOX" PREFLIGHT_STORES_FILE="$STORESFILE" PREFLIGHT_ENV_KEYS_FILE="$ENVKEYSFILE" \
   bash "$GUARD" verify "$BK" >/dev/null 2>&1; then
  bad "T6b: guard PASSED despite a genuine external credential rewrite (guard was weakened — must stay strict)"
else
  ok "T6b: guard still REFUSES on a genuine external credential rewrite (strictness intact)"
fi
rm -rf "$BOX"

# ============================================================================
# PART D7 — detached-HEAD-safe git sync
# ============================================================================

git_id() { git -C "$1" rev-parse HEAD 2>/dev/null; }

# Build: bare "origin" seeded with commit c1 (main.txt + logo-config.json),
# tagged v1.0.0. A second commit c2 is pushed to origin/main afterwards so
# tests can simulate "origin has moved on".
build_origin() {
  local root; root="$(mktemp -d)"
  local origin="$root/origin.git" seed="$root/seed"
  git init --quiet --bare "$origin"
  git init --quiet "$seed"
  git -C "$seed" config user.email test@example.test
  git -C "$seed" config user.name  "Test"
  printf 'v1\n' > "$seed/main.txt"
  printf 'logo=default\nother=keep\n' > "$seed/logo-config.json"
  git -C "$seed" checkout --quiet -b main
  git -C "$seed" add -A
  git -C "$seed" commit --quiet -m c1
  git -C "$seed" remote add origin "$origin"
  git -C "$seed" push --quiet origin main
  git -C "$seed" tag v1.0.0
  git -C "$seed" push --quiet origin v1.0.0
  git -C "$origin" symbolic-ref HEAD refs/heads/main
  printf '%s\t%s\t%s\n' "$root" "$origin" "$seed"
}

# Advance origin/main with commit c2 that touches ONLY main.txt (leaves
# logo-config.json alone -> a non-conflicting local edit to it survives).
advance_origin_nonconflicting() {
  local seed="$1"
  printf 'v2\n' > "$seed/main.txt"
  git -C "$seed" commit --quiet -am c2
  git -C "$seed" push --quiet origin main
}

# Advance origin/main with a commit that changes THE SAME line of
# logo-config.json a local uncommitted edit will also touch (conflict shape).
advance_origin_conflicting_logo() {
  local seed="$1"
  printf 'logo=UPSTREAM-CHANGED\nother=keep\n' > "$seed/logo-config.json"
  git -C "$seed" commit --quiet -am c2-logo
  git -C "$seed" push --quiet origin main
}

sync_fn() {
  local dir="$1" logf="$2"
  ( LOG_FILE="$logf"
    # shellcheck disable=SC1090
    source "$FRAG"
    cc_git_sync_to_default_branch "$dir"
  )
}

# T7 — TEETH: bare `git pull --ff-only` on a detached-HEAD checkout FAILS.
hdr "T7 — teeth: bare 'git pull --ff-only' aborts on detached HEAD (proves the bug is real)"
read -r ROOT ORIGIN SEED <<EOF
$(build_origin)
EOF
advance_origin_nonconflicting "$SEED"
CO="$ROOT/checkout-t7"
git clone --quiet "$ORIGIN" "$CO"
git -C "$CO" checkout --quiet v1.0.0
BEFORE="$(git_id "$CO")"
if ( cd "$CO" && git pull --ff-only ) >/dev/null 2>&1; then
  bad "T7: bare 'git pull --ff-only' unexpectedly SUCCEEDED on detached HEAD (harness assumption wrong)"
else
  AFTER="$(git_id "$CO")"
  if [ "$BEFORE" = "$AFTER" ]; then
    ok "T7: bare 'git pull --ff-only' aborts on detached HEAD and leaves HEAD unmoved — bug reproduced"
  else
    bad "T7: bare pull failed but HEAD moved anyway (unexpected)"
  fi
fi
rm -rf "$ROOT"

# T8 — FIXED: detached HEAD -> cc_git_sync_to_default_branch re-attaches and
# advances to latest origin/main; a non-conflicting local uncommitted edit
# survives.
hdr "T8 — fixed: detached HEAD syncs to latest origin/main; local patch survives"
read -r ROOT ORIGIN SEED <<EOF
$(build_origin)
EOF
advance_origin_nonconflicting "$SEED"
LATEST="$(git -C "$SEED" rev-parse main)"
CO="$ROOT/checkout-t8"
git clone --quiet "$ORIGIN" "$CO"
git -C "$CO" checkout --quiet v1.0.0
# local "client patch": uncommitted edit to logo-config.json (untouched by c2)
printf 'logo=CLIENT-CUSTOM\nother=keep\n' > "$CO/logo-config.json"
LOGF="$ROOT/sync.log"
if sync_fn "$CO" "$LOGF" >/dev/null 2>&1; then
  NOW="$(git_id "$CO")"
  if [ "$NOW" = "$LATEST" ]; then
    ok "T8a: detached checkout advanced to latest origin/main ($LATEST)"
  else
    bad "T8a: HEAD did not reach latest origin/main (now=$NOW want=$LATEST)"
  fi
  if grep -q '^logo=CLIENT-CUSTOM$' "$CO/logo-config.json" 2>/dev/null; then
    ok "T8b: local uncommitted patch to logo-config.json survived the sync"
  else
    bad "T8b: local patch to logo-config.json was LOST during sync: $(cat "$CO/logo-config.json" 2>/dev/null)"
  fi
else
  bad "T8: cc_git_sync_to_default_branch FAILED on a clean non-conflicting detached-HEAD sync (should have succeeded)"
fi
rm -rf "$ROOT"

# T9 — regression check: already on a branch (attached), behind origin ->
# fast-forwards cleanly (the previously-working path must keep working).
hdr "T9 — regression: attached branch, behind origin -> clean fast-forward"
read -r ROOT ORIGIN SEED <<EOF
$(build_origin)
EOF
CO="$ROOT/checkout-t9"
git clone --quiet "$ORIGIN" "$CO"
git -C "$CO" checkout --quiet main
advance_origin_nonconflicting "$SEED"
LATEST="$(git -C "$SEED" rev-parse main)"
LOGF="$ROOT/sync.log"
if sync_fn "$CO" "$LOGF" >/dev/null 2>&1; then
  NOW="$(git_id "$CO")"
  [ "$NOW" = "$LATEST" ] && ok "T9: attached branch fast-forwards to latest origin/main" \
                          || bad "T9: attached branch did not reach latest (now=$NOW want=$LATEST)"
else
  bad "T9: cc_git_sync_to_default_branch FAILED on a clean attached fast-forward (should have succeeded)"
fi
rm -rf "$ROOT"

# T10 — a GENUINE conflict (local uncommitted edit conflicts with the incoming
# commit on the same file) is refused NON-DESTRUCTIVELY: nonzero return, HEAD
# unmoved, local edit NOT overwritten.
hdr "T10 — conflict refused non-destructively (no lost work, no reset --hard)"
read -r ROOT ORIGIN SEED <<EOF
$(build_origin)
EOF
advance_origin_conflicting_logo "$SEED"
CO="$ROOT/checkout-t10"
git clone --quiet "$ORIGIN" "$CO"
git -C "$CO" checkout --quiet v1.0.0
BEFORE="$(git_id "$CO")"
# local edit conflicts: touches the exact same line c2-logo changed upstream
printf 'logo=LOCAL-CONFLICTING-EDIT\nother=keep\n' > "$CO/logo-config.json"
LOGF="$ROOT/sync.log"
if sync_fn "$CO" "$LOGF" >/dev/null 2>&1; then
  bad "T10: cc_git_sync_to_default_branch SUCCEEDED despite a genuine conflict (should have refused)"
else
  AFTER="$(git_id "$CO")"
  STILL_LOCAL=0
  grep -q '^logo=LOCAL-CONFLICTING-EDIT$' "$CO/logo-config.json" 2>/dev/null && STILL_LOCAL=1
  if [ "$BEFORE" = "$AFTER" ] && [ "$STILL_LOCAL" -eq 1 ]; then
    ok "T10: conflict refused (nonzero), HEAD unmoved, local edit preserved untouched — non-destructive"
  else
    bad "T10: refused but NOT non-destructively (HEAD moved=$([ "$BEFORE" != "$AFTER" ] && echo yes || echo no), local edit lost=$([ "$STILL_LOCAL" -eq 0 ] && echo yes || echo no))"
  fi
fi
rm -rf "$ROOT"

# T11 — a gitignored file (the .env.local / *.db shape) survives a successful
# sync byte-identical (no git operation ever touches an ignored path).
hdr "T11 — gitignored file (.env.local-shaped) untouched by a successful sync"
read -r ROOT ORIGIN SEED <<EOF
$(build_origin)
EOF
advance_origin_nonconflicting "$SEED"
CO="$ROOT/checkout-t11"
git clone --quiet "$ORIGIN" "$CO"
git -C "$CO" checkout --quiet v1.0.0
printf 'env.local\n*.db\n' > "$CO/.gitignore"
printf 'MC_API_TOKEN=super-secret-value\n' > "$CO/env.local"
BEFORE_SHA="$(sha "$CO/env.local")"
LOGF="$ROOT/sync.log"
sync_fn "$CO" "$LOGF" >/dev/null 2>&1
AFTER_SHA="$(sha "$CO/env.local")"
[ "$BEFORE_SHA" = "$AFTER_SHA" ] && ok "T11: gitignored env.local byte-identical after sync" \
                                  || bad "T11: gitignored env.local was modified by the sync (should be impossible via git)"
rm -rf "$ROOT"

# T12 — static: the helper's own source never invokes a destructive git verb.
hdr "T12 — static: cc_git_sync_to_default_branch never uses reset --hard / checkout -f / clean -f"
FN_SRC="$(extract_func cc_git_sync_to_default_branch "$INSTALLER")"
BADHIT=0
printf '%s\n' "$FN_SRC" | grep -Eq 'reset[[:space:]]+--hard'   && { bad "T12: found 'reset --hard' in cc_git_sync_to_default_branch"; BADHIT=1; }
printf '%s\n' "$FN_SRC" | grep -Eq 'checkout[[:space:]]+-f\b'  && { bad "T12: found 'checkout -f' in cc_git_sync_to_default_branch"; BADHIT=1; }
printf '%s\n' "$FN_SRC" | grep -Eq 'clean[[:space:]]+-f'       && { bad "T12: found 'clean -f' in cc_git_sync_to_default_branch"; BADHIT=1; }
[ "$BADHIT" -eq 0 ] && ok "T12: no destructive git verb present in the helper's source"

rm -f "$FRAG"

# ── summary ──────────────────────────────────────────────────────────────────
printf '\n\033[1m%d passed, %d failed\033[0m\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
