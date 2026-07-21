#!/usr/bin/env bash
# test-installer-credential-store.sh — T2-21 / A45.
#
# WHY THIS EXISTS
#   Two installers wrote credentials only to legacy stores that the same skills'
#   checks never read. 30-fish-audio-api-reference/INSTALL.md wrote to
#   ~/.clawdbot/clawdbot.json and ~/clawd/secrets/.env; 08-vercel-setup and
#   10-github-setup searched a hardcoded four-path list and fell back to
#   ~/clawd/secrets/.env. Every one of those skills' QC scripts sources
#   $SECRETS_ENV, which lib-shared.sh:38-44 defines as ~/.openclaw/secrets/.env
#   (Mac) or /data/.openclaw/secrets/.env (VPS). The install wrote the credential
#   where nothing read it and the verification then reported it ABSENT on a box
#   the owner had configured correctly.
#
# WHAT THIS PROVES — both directions, per skill:
#   DIRECTION A (the defect, i.e. the mutation the QC row calls for): write the
#     credential the way the OLD installer said, to the legacy path. Run that
#     skill's own QC. Assert it reports the credential ABSENT. This is the false
#     failure the finding describes; if this direction ever stops failing, the
#     test has stopped testing anything.
#   DIRECTION B (the fix): write the credential to the store resolved through
#     lib-shared.sh, exactly as the NEW installer says. Run the same QC. Assert
#     it finds the credential.
#
#   Direction A is deliberately the FIRST assertion. A test that only checks the
#   happy path would pass against the unfixed repository.
#
# Everything runs inside a throwaway HOME. No fleet box is touched, no live
# network call decides a verdict (the QC's API probes are warn_only by design),
# and no real credential is used — the values below are literal test strings.
#
# EXIT: 0 all directions passed · 1 a direction failed · 2 could not run.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0
FAIL=0

red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }

# Literal test values. Not credentials — no live service accepts them.
TEST_FISH_KEY="test-not-a-real-key-fish"
TEST_FISH_VOICE="test-not-a-real-voice-id"
TEST_VERCEL="test-not-a-real-token-vercel"
TEST_GITHUB="test-not-a-real-token-github"

command -v jq >/dev/null 2>&1 || true   # not required; QC scripts do not need it

# build_sandbox <skill-dir-name> -> prints the sandbox HOME
# Lays out a minimal but REAL install tree: the skills root with lib-shared.sh
# beside the skill folder, which is exactly how the QC scripts resolve
# "$SKILL_DIR/../lib-shared.sh".
build_sandbox() {
  local skill="$1" home
  home="$(mktemp -d)"
  mkdir -p "$home/.openclaw/skills"
  cp "$REPO_ROOT/lib-shared.sh" "$home/.openclaw/skills/lib-shared.sh"
  cp -R "$REPO_ROOT/$skill" "$home/.openclaw/skills/$skill"
  printf '%s' "$home"
}

# qc_reports_set <sandbox-home> <skill> <qc-script> <assertion-label>
#   The label is the EXACT text that skill's QC prints for its credential check,
#   read out of the QC script itself — not a guess. A PASS line means the QC
#   found the credential; anything else means it did not.
#   0 = found · 1 = not found
qc_reports_set() {
  local home="$1" skill="$2" qc="$3" label="$4" out
  out="$(HOME="$home" bash "$home/.openclaw/skills/$skill/$qc" 2>&1)"
  printf '%s' "$out" | grep -qF "✓ PASS — ${label}"
}

check() {  # check <label> <expected: SET|ABSENT> <actual-rc>
  local label="$1" expected="$2" rc="$3"
  local actual="ABSENT"; [ "$rc" -eq 0 ] && actual="SET"
  if [ "$actual" = "$expected" ]; then
    green "  ✓ $label — QC reports $actual (expected $expected)"
    PASS=$((PASS + 1))
  else
    red   "  ✗ $label — QC reports $actual, expected $expected"
    FAIL=$((FAIL + 1))
  fi
}

echo ""
echo "═══ T2-21 / A45 — credentials must land where the skill's own check reads them ═══"

# ─────────────────────────────────────────────────────────────────────────────
# Skill 30 — Fish Audio
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "── 30-fish-audio-api-reference ──"

H="$(build_sandbox 30-fish-audio-api-reference)" || { red "could not build sandbox"; exit 2; }

# DIRECTION A — the defect. Write where the OLD installer said.
mkdir -p "$H/clawd/secrets" "$H/.clawdbot"
{
  printf 'FISH_AUDIO_API_KEY=%s\n' "$TEST_FISH_KEY"
  printf 'FISH_AUDIO_VOICE_ID=%s\n' "$TEST_FISH_VOICE"
} > "$H/clawd/secrets/.env"
printf '{"env":{"vars":{"FISH_AUDIO_API_KEY":"%s"}}}\n' "$TEST_FISH_KEY" > "$H/.clawdbot/clawdbot.json"
qc_reports_set "$H" 30-fish-audio-api-reference qc-fish-audio-api-reference.sh "FISH_AUDIO_API_KEY set"
check "DIRECTION A (legacy path — the defect)" ABSENT $?

# DIRECTION B — the fix. Write to the store lib-shared.sh resolves.
mkdir -p "$H/.openclaw/secrets"
{
  printf 'FISH_AUDIO_API_KEY=%s\n' "$TEST_FISH_KEY"
  printf 'FISH_AUDIO_VOICE_ID=%s\n' "$TEST_FISH_VOICE"
} > "$H/.openclaw/secrets/.env"
qc_reports_set "$H" 30-fish-audio-api-reference qc-fish-audio-api-reference.sh "FISH_AUDIO_API_KEY set"
check "DIRECTION B (canonical store — the fix)" SET $?
rm -rf "$H"

# ─────────────────────────────────────────────────────────────────────────────
# Skill 08 — Vercel
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "── 08-vercel-setup ──"

H="$(build_sandbox 08-vercel-setup)" || { red "could not build sandbox"; exit 2; }
mkdir -p "$H/clawd/secrets"
printf 'VERCEL_TOKEN=%s\n' "$TEST_VERCEL" > "$H/clawd/secrets/.env"
qc_reports_set "$H" 08-vercel-setup qc-vercel-setup.sh "VERCEL_TOKEN set"
check "DIRECTION A (legacy path — the defect)" ABSENT $?

mkdir -p "$H/.openclaw/secrets"
printf 'VERCEL_TOKEN=%s\n' "$TEST_VERCEL" > "$H/.openclaw/secrets/.env"
qc_reports_set "$H" 08-vercel-setup qc-vercel-setup.sh "VERCEL_TOKEN set"
check "DIRECTION B (canonical store — the fix)" SET $?
rm -rf "$H"

# ─────────────────────────────────────────────────────────────────────────────
# Skill 10 — GitHub
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "── 10-github-setup ──"

H="$(build_sandbox 10-github-setup)" || { red "could not build sandbox"; exit 2; }
mkdir -p "$H/clawd/secrets"
printf 'GITHUB_TOKEN=%s\n' "$TEST_GITHUB" > "$H/clawd/secrets/.env"
qc_reports_set "$H" 10-github-setup qc-github-setup.sh "GITHUB_TOKEN or GH_TOKEN present"
check "DIRECTION A (legacy path — the defect)" ABSENT $?

mkdir -p "$H/.openclaw/secrets"
printf 'GITHUB_TOKEN=%s\n' "$TEST_GITHUB" > "$H/.openclaw/secrets/.env"
qc_reports_set "$H" 10-github-setup qc-github-setup.sh "GITHUB_TOKEN or GH_TOKEN present"
check "DIRECTION B (canonical store — the fix)" SET $?
rm -rf "$H"

# ─────────────────────────────────────────────────────────────────────────────
# STATIC — no installer may still direct a credential WRITE at a legacy store.
# This is what actually regresses: prose drifts back long before a runtime does.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "── static: installers must not direct a credential write to a legacy store ──"
STATIC_RC=0
python3 - "$REPO_ROOT" <<'PY' || STATIC_RC=$?
import pathlib, re, sys

root = pathlib.Path(sys.argv[1])
# The files A45 re-pointed at the canonical store. Each is checked for a line
# that WRITES a credential to a legacy path. Prose that names a legacy path in
# order to explain why it is wrong is not a defect — a write is.
TARGETS = [
    "30-fish-audio-api-reference/INSTALL.md",
    "30-fish-audio-api-reference/SKILL.md",
    "08-vercel-setup/INSTALL.md",
    "10-github-setup/INSTALL.md",
    "10-github-setup/QC.md",
]
LEGACY = ("clawd/secrets/.env", ".clawdbot/clawdbot.json", "~/.openclaw/.env", "~/secrets/.env")
# A line WRITES when it redirects into a path, creates one, assigns it as the
# destination, or instructs a human/agent to put a value there.
WRITE = re.compile(
    r">>\s*[\"']?[~$]|>\s*[\"']?[~$]|mkdir\s+-p|SECRETS_FILE=[~$/]|SECRETS_ENV=[~$/]|"
    r"^\s*Add (?:to|both to)\b|\bAdd `[A-Z_]+` to\b",
)
# The one-time migration loop READS a legacy path on purpose.
MIGRATION = re.compile(r"LEGACY|migrat", re.IGNORECASE)

problems = []
for rel in TARGETS:
    p = root / rel
    if not p.is_file():
        problems.append(f"CANNOT RUN: {rel} is missing")
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not any(l in line for l in LEGACY):
            continue
        if MIGRATION.search(line):
            continue
        if WRITE.search(line):
            problems.append(f"{rel}:{i} WRITES a credential to a legacy store: {line.strip()}")

if problems:
    print("  \u2717 static check FAILED")
    for prob in problems:
        print(f"    {prob}")
    cannot_run = any(prob.startswith("CANNOT RUN") for prob in problems)
    sys.exit(2 if cannot_run else 1)
print(f"  \u2713 static check \u2014 no credential WRITE to a legacy store in {len(TARGETS)} installer documents")
PY
if [ "$STATIC_RC" -eq 0 ]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); fi

echo ""
echo "═══ Result: $PASS passed | $FAIL failed ═══"
[ "$FAIL" -gt 0 ] && { red "A45 credential-store test FAILED"; exit 1; }
green "A45 credential-store test PASSED"
exit 0
