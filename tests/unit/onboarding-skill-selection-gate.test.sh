#!/usr/bin/env bash
# tests/unit/onboarding-skill-selection-gate.test.sh
# SHARED onboarding installation gate (WG1): lib-onboarding-state.sh
# oc_skill_registered / oc_skill_selection_status must verify the skill the
# INTENDED OpenClaw agent actually RESOLVES — resolver path evidence, runtime
# distribution (declared built entry point present and matching its recorded
# identity), and artifact/version identity consistent across every version
# carrier present. An installation record or a fallback directory is NOT proof
# of agent selection: selection that cannot be established is BLOCKED, never
# PASS. Hermetic (mktemp HOME, fake `openclaw`, no network, no model calls).
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0
ok() { echo "PASS $1"; }
bad() { echo "FAIL $1"; fail=1; }

mkdir -p "$T/h"

sha256() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else sha256sum "$1" | awk '{print $1}'; fi
}

# ---- fixture builders ------------------------------------------------------
# mk_tree <root> <version> — a correct selected-tree fixture: four version
# carriers in agreement + a manifest-recorded built entry point whose sha256
# and bytes match the file on disk.
mk_tree() {
  local root="$1" ver="$2" sum bytes
  mkdir -p "$root/01-demo/runtime/dist"
  printf -- '---\nname: demo\nversion: %s\n---\n' "$ver" > "$root/01-demo/SKILL.md"
  printf 'v%s\n' "$ver" > "$root/01-demo/skill-version.txt"
  printf '%s\n' "$ver" > "$root/01-demo/version"
  printf 'export const demo = 1;\n' > "$root/01-demo/runtime/dist/demo.mjs"
  sum=$(sha256 "$root/01-demo/runtime/dist/demo.mjs")
  bytes=$(wc -c < "$root/01-demo/runtime/dist/demo.mjs" | tr -d ' ')
  printf '{"skill":"demo","skill_version":"%s","runtime_entry":{"path":"runtime/dist/demo.mjs","sha256":"%s","bytes":%s}}\n' \
    "$ver" "$sum" "$bytes" > "$root/01-demo/manifest.json"
}

# mk_cli <bindir> <resolved-skill-md-path|''> — fake openclaw that answers
# `skills info` the way the product does (Details: Source / Path). Empty path
# prints Ready with NO resolver path (selection cannot be established).
mk_cli() {
  local bindir="$1" p="$2"
  mkdir -p "$bindir"
  {
    printf '#!/bin/sh\n'
    printf 'echo "ARGS:$*" >> "%s/args"\n' "$T"
    if [ -n "$p" ]; then
      printf 'cat <<'"'"'OUT'"'"'\ndemo ✓ Ready\n\nDetails:\n  Source: openclaw-managed\n  Path: %s\n  Visible to model: yes\nOUT\n' "$p"
    else
      printf 'echo "demo ✓ Ready"\n'
    fi
    printf 'exit 0\n'
  } > "$bindir/openclaw"
  chmod +x "$bindir/openclaw"
}

# sel <bindir> <skills-root> [expected_version] [path] — run the tri-state,
# print "rc=<rc> <line>". Optional 4th arg replaces PATH entirely.
sel() {
  local bindir="$1" root="$2" exp="${3:-}" pth=""
  pth="${4:-$bindir:$PATH}"
  HOME="$T/h" PATH="$pth" OC_CONFIG="$T/h/.openclaw" OC_SKILLS_DIR="$root" bash -c '
    source "$1" 2>/dev/null
    rc=0; oc_skill_selection_status 01-demo "$2" || rc=$?
    echo "rc=$rc"
  ' _ "$REPO/lib-onboarding-state.sh" "$exp"
}

# bool <bindir> <skills-root> [expected_version] — run the preserved boolean.
bool() {
  local bindir="$1" root="$2" exp="${3:-}"
  HOME="$T/h" PATH="$bindir:$PATH" OC_CONFIG="$T/h/.openclaw" OC_SKILLS_DIR="$root" bash -c '
    source "$1" 2>/dev/null
    oc_skill_registered 01-demo "$2" >/dev/null 2>&1
    echo "rc=$?"
  ' _ "$REPO/lib-onboarding-state.sh" "$exp"
}

# never_success <label> <output-of-sel> — hard red line: BLOCKED/UNKNOWN can
# never be read as success. Fails if the code reports PASS/rc 0.
never_success() {
  local label="$1" out="$2"
  if printf '%s' "$out" | grep -q '^rc=0' || printf '%s' "$out" | grep -q '^PASS'; then
    bad "$label reported success"
  else
    ok "$label never PASS"
  fi
}

# ---- 1. selected tree correct -> PASS --------------------------------------
mk_tree "$T/s1" "1.0.53"
mk_cli "$T/s1bin" "$T/s1/01-demo/SKILL.md"
out="$(sel "$T/s1bin" "$T/s1" "1.0.53")"
printf '%s\n' "$out" | grep -q '^rc=0' && printf '%s' "$out" | grep -q '^PASS' \
  && ok "selected-tree correct -> PASS" || bad "expected PASS: $out"
out="$(bool "$T/s1bin" "$T/s1" "1.0.53")"
printf '%s' "$out" | grep -q '^rc=0' && ok "boolean true on verified selection" \
  || bad "boolean not true: $out"

# ---- 2. selected tree older than shipped version -> FAIL --------------------
# The PR #2514 shape: the tree the agent selects is 1.0.52 while the shipped
# release contract is 1.0.53. Positive resolver evidence of a stale tree is a
# FAIL, and the unchanged 1.0.52 version file must not win.
mk_tree "$T/s2" "1.0.52"
mk_cli "$T/s2bin" "$T/s2/01-demo/SKILL.md"
out="$(sel "$T/s2bin" "$T/s2" "1.0.53")"
printf '%s' "$out" | grep -q '^rc=1' && printf '%s' "$out" | grep -q '^FAIL selected-version-older' \
  && ok "selected tree older than shipped version -> FAIL" || bad "expected FAIL older: $out"
never_success "stale selected tree" "$out"
out="$(bool "$T/s2bin" "$T/s2" "1.0.53")"
printf '%s' "$out" | grep -qv '^rc=0' && ok "boolean false on stale selection" \
  || bad "boolean true on stale selection: $out"
# same scenario with a correct copy ALSO sitting in a non-selected fallback
# root: still FAIL (the fallback copy is not what the agent resolves)
mk_tree "$T/s2fb" "1.0.53"
out="$(sel "$T/s2bin" "$T/s2" "1.0.53")"
printf '%s' "$out" | grep -q '^rc=1' && printf '%s' "$out" | grep -q '^FAIL' \
  && ok "fallback copy elsewhere does not rescue stale selection" \
  || bad "stale selection rescued by fallback: $out"

# ---- 3. version carriers disagree -> FAIL ----------------------------------
# Exact PR #2514 false-positive case: version file 1.0.52 vs skill-version.txt
# 1.0.53 in the SAME tree. Disagreement is a failure, not a preference.
mk_tree "$T/s3" "1.0.52"
printf 'v1.0.53\n' > "$T/s3/01-demo/skill-version.txt"
mk_cli "$T/s3bin" "$T/s3/01-demo/SKILL.md"
out="$(sel "$T/s3bin" "$T/s3")"
printf '%s' "$out" | grep -q '^rc=1' && printf '%s' "$out" | grep -q '^FAIL version-carriers-disagree' \
  && ok "version carriers disagree -> FAIL" || bad "expected FAIL carriers: $out"
never_success "carrier disagreement" "$out"
out="$(sel "$T/s3bin" "$T/s3" "1.0.53")"
printf '%s' "$out" | grep -q '^rc=1' && ok "carrier disagreement fails even with matching expected" \
  || bad "expected FAIL with expected=1.0.53: $out"
out="$(bool "$T/s3bin" "$T/s3")"
printf '%s' "$out" | grep -qv '^rc=0' && ok "boolean false on carrier disagreement" \
  || bad "boolean true on carrier disagreement: $out"

# ---- 4. correct copy only in a non-selected fallback root -> BLOCKED -------
# The fallback root holds a fully correct 1.0.53 tree, but the resolver gives
# NO path evidence about which tree the agent serves. A fallback directory is
# not proof of agent selection: BLOCKED, never PASS.
mk_tree "$T/s4fb" "1.0.53"
mk_cli "$T/s4bin" ""
out="$(sel "$T/s4bin" "$T/s4fb" "1.0.53")"
printf '%s' "$out" | grep -q '^rc=2' && printf '%s' "$out" | grep -q '^BLOCKED' \
  && ok "fallback-only copy, no resolver path -> BLOCKED" || bad "expected BLOCKED: $out"
never_success "fallback-only copy" "$out"
printf '%s' "$out" | grep -qiE 'registered|[^a-z]ok[^a-z]|^ok' \
  && bad "BLOCKED line printed registered/ok: $out" \
  || ok "BLOCKED line never prints registered or ok"
out="$(bool "$T/s4bin" "$T/s4fb" "1.0.53")"
printf '%s' "$out" | grep -qv '^rc=0' && ok "boolean false when selection unestablished" \
  || bad "boolean true when selection unestablished: $out"

# ---- 5. no resolver evidence available -> BLOCKED --------------------------
# No openclaw CLI reachable: PATH reduced to the system dirs only (the real
# CLI lives in a node/nvm bin dir), isolated HOME so the known-install-location
# scan finds nothing.
mkdir -p "$T/s5empty"
out="$(sel "$T/s5-nobin" "$T/s5empty" "" "/usr/bin:/bin")"
printf '%s' "$out" | grep -q '^rc=2' && printf '%s' "$out" | grep -q '^BLOCKED' \
  && ok "no resolver evidence -> BLOCKED" || bad "expected BLOCKED (no cli): $out"
never_success "no resolver evidence" "$out"

# ---- 2b. runtime distribution: declared entry point must be real -----------
# An archive or executable merely existing is not proof it is valid: the
# manifest-recorded built entry point must exist (not source-only) and match
# its recorded identity.
mk_tree "$T/s6" "1.0.53"
rm -f "$T/s6/01-demo/runtime/dist/demo.mjs"
mk_cli "$T/s6bin" "$T/s6/01-demo/SKILL.md"
out="$(sel "$T/s6bin" "$T/s6")"
printf '%s' "$out" | grep -q '^rc=1' && printf '%s' "$out" | grep -q '^FAIL runtime-entry-missing' \
  && ok "source-only tree (declared entry missing) -> FAIL" || bad "expected FAIL entry-missing: $out"
never_success "source-only tree" "$out"
mk_tree "$T/s7" "1.0.53"
printf 'tampered\n' >> "$T/s7/01-demo/runtime/dist/demo.mjs"
mk_cli "$T/s7bin" "$T/s7/01-demo/SKILL.md"
out="$(sel "$T/s7bin" "$T/s7")"
printf '%s' "$out" | grep -q '^rc=1' && printf '%s' "$out" | grep -q '^FAIL runtime-entry-' \
  && ok "entry point identity mismatch -> FAIL" || bad "expected FAIL entry-mismatch: $out"

# ---- 2c. every BLOCKED branch is pinned by a test ---------------------------
# (i) multi-agent box: the product says the intended agent cannot be told
# apart. Selection cannot be established -> BLOCKED, never PASS.
mk_tree "$T/s8" "1.0.53"
mkdir -p "$T/s8bin"
printf '#!/bin/sh\necho "demo has no explicit owner across 3 agents"\nexit 0\n' > "$T/s8bin/openclaw"
chmod +x "$T/s8bin/openclaw"
out="$(sel "$T/s8bin" "$T/s8" "1.0.53")"
printf '%s' "$out" | grep -q '^rc=2' && printf '%s' "$out" | grep -q '^BLOCKED skill-selection-blocked:agent-selection-unresolved' \
  && ok "multi-agent ambiguity -> BLOCKED agent-selection-unresolved" \
  || bad "expected BLOCKED agent-selection-unresolved: $out"
never_success "multi-agent ambiguity" "$out"

# (ii) the verifier itself cannot run (python3 present but failing/empty):
# that is not success and not a silent pass.
mk_tree "$T/s9" "1.0.53"
mk_cli "$T/s9bin" "$T/s9/01-demo/SKILL.md"
mkdir -p "$T/s9p"
printf '#!/bin/sh\nexit 1\n' > "$T/s9p/python3"
chmod +x "$T/s9p/python3"
out="$(sel "$T/s9bin" "$T/s9" "1.0.53" "$T/s9bin:$T/s9p:/usr/bin:/bin")"
printf '%s' "$out" | grep -q '^rc=2' && printf '%s' "$out" | grep -q '^BLOCKED skill-selection-blocked:verification-did-not-run' \
  && ok "verifier did not run -> BLOCKED verification-did-not-run" \
  || bad "expected BLOCKED verification-did-not-run: $out"
never_success "verifier did not run" "$out"

# ---- 2d. resolver Path naming a DIFFERENT skill -> FAIL --------------------
# The resolver is authority on which tree, but a Path that serves another
# skill is not this skill: identity is cross-checked.
mk_tree "$T/s10" "1.0.53"
mkdir -p "$T/s10/99-other"
printf -- '---\nname: other\nversion: 1.0.53\n---\n' > "$T/s10/99-other/SKILL.md"
printf 'v1.0.53\n' > "$T/s10/99-other/skill-version.txt"
printf '1.0.53\n' > "$T/s10/99-other/version"
mk_cli "$T/s10bin" "$T/s10/99-other/SKILL.md"
out="$(sel "$T/s10bin" "$T/s10" "1.0.53")"
printf '%s' "$out" | grep -q '^rc=1' && printf '%s' "$out" | grep -q '^FAIL selected-tree-name-mismatch' \
  && ok "resolver Path naming another skill -> FAIL name mismatch" \
  || bad "expected FAIL name mismatch: $out"
never_success "wrong skill selected" "$out"

# a matching DIRECTORY name must not rescue a tree whose SKILL.md says it is
# another skill: the declared name is authoritative.
mk_tree "$T/s10b" "1.0.53"
printf -- '---\nname: other\nversion: 1.0.53\n---\n' > "$T/s10b/01-demo/SKILL.md"
mk_cli "$T/s10bbin" "$T/s10b/01-demo/SKILL.md"
out="$(sel "$T/s10bbin" "$T/s10b" "1.0.53")"
printf '%s' "$out" | grep -q '^rc=1' && printf '%s' "$out" | grep -q '^FAIL selected-tree-name-mismatch' \
  && ok "matching folder name with a different SKILL.md name -> FAIL" \
  || bad "expected FAIL name mismatch (declared name): $out"
never_success "declared name mismatch" "$out"

# ---- 2f. staleness is disclosed, supplied from the source copy, and an
# unreadable source version is BLOCKED rather than skipped -------------------
# (i) no expected version: PASS must SAY the staleness comparison did not run
out="$(sel "$T/s1bin" "$T/s1")"
printf '%s' "$out" | grep -q 'stale-check-not-possible-no-expected-version' \
  && ok "no expected version -> PASS discloses the staleness check did not run" \
  || bad "expected staleness disclosure: $out"

# (ii) oc_gate_skill supplies the shipment expectation from the source copy
# beside the lib: a stale selected tree then FAILS.
mkdir -p "$T/repo/01-demo" "$T/state"
cp "$REPO/lib-onboarding-state.sh" "$T/repo/lib-onboarding-state.sh"
printf 'v1.0.53\n' > "$T/repo/01-demo/skill-version.txt"
gate_reason() { # gate_reason <repo-root> -- run oc_gate_skill with recording stubs
  HOME="$T/h" PATH="$T/s12bin:$PATH" OC_CONFIG="$T/h/.openclaw" OC_SKILLS_DIR="$T/s12" \
  bash -c '
    source "$1/lib-onboarding-state.sh" 2>/dev/null
    oc_state_mark_field() { return 0; }
    oc_state_set() { printf "STATE:%s:%s\n" "$1" "${2:-}${3:+ $3}"; return 0; }
    oc_gate_skill 01-demo; _grc=$?
    echo "gate_rc=$_grc"
  ' _ "$1"
}
mk_tree "$T/s12" "1.0.52"
mk_cli "$T/s12bin" "$T/s12/01-demo/SKILL.md"
out="$(gate_reason "$T/repo")"
printf '%s' "$out" | grep -q 'gate_rc=1' && printf '%s' "$out" | grep -q 'selected-version-older' \
  && ok "oc_gate_skill supplies the source expectation (stale tree FAILS)" \
  || bad "expected FAIL via supplied expectation: $out"

# (iii) a source copy whose version is present but EMPTY is not a licence to skip
: > "$T/repo/01-demo/skill-version.txt"
out="$(gate_reason "$T/repo")"
printf '%s' "$out" | grep -q 'gate_rc=1' && printf '%s' "$out" | grep -q 'expected-version-unreadable' \
  && ok "unreadable source version -> BLOCKED expected-version-unreadable" \
  || bad "expected BLOCKED unreadable expectation: $out"

# ---- 2e. no identity evidence at all -> FAIL -------------------------------
# No version carrier and no declared runtime entry: silence is not evidence.
mkdir -p "$T/s11/01-demo/advisors"
printf -- '---\nname: demo\n---\n' > "$T/s11/01-demo/SKILL.md"
mkdir -p "$T/s11bin"
printf '#!/bin/sh\necho "demo ✓ Ready"\necho "Details:"\necho "  Source: openclaw-managed"\necho "  Path: %s"\n' "$T/s11/01-demo/SKILL.md" > "$T/s11bin/openclaw"
chmod +x "$T/s11bin/openclaw"
out="$(sel "$T/s11bin" "$T/s11")"
printf '%s' "$out" | grep -q '^rc=1' && printf '%s' "$out" | grep -q '^FAIL no-identity-evidence' \
  && ok "no version carrier and no declared entry -> FAIL no-identity-evidence" \
  || bad "expected FAIL no-identity-evidence: $out"
never_success "no identity evidence" "$out"

exit $fail
