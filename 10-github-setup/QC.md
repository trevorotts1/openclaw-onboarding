# QC Checklist - Skill 10: GitHub Setup
**Version:** v6.5.9

Run this after installation. Every section must pass before you mark GitHub setup complete.

---

## 1. File and version checks

```bash
SKILL_DIR="$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding/10-github-setup"
ls -1 "$SKILL_DIR"
cat "$SKILL_DIR/skill-version.txt"
```

- [ ] Required files exist: `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`, `github-setup-full.md`, `QC.md`, `skill-version.txt`
- [ ] `skill-version.txt` returns `v6.5.9`
- [ ] `github-setup-full.md` is non-empty

---

## 2. Core file update checks

```bash
grep -n "GitHub" ~/clawd/AGENTS.md ~/clawd/TOOLS.md ~/clawd/MEMORY.md
```

- [ ] `AGENTS.md` references browser PAT creation plus local git config
- [ ] `TOOLS.md` references `GITHUB_TOKEN` and `GITHUB_USERNAME`
- [ ] `MEMORY.md` contains a short install reminder, not a giant paste
- [ ] Core docs mention minimum PAT scopes: `repo`, `read:org`, `workflow`

---

## 3. Local git checks

```bash
git --version
git config --global --get user.name
git config --global --get user.email
git config --global --get credential.helper
```

- [ ] `git` is installed
- [ ] Global `user.name` is set
- [ ] Global `user.email` is set
- [ ] Credential helper is configured

**PASS:** Git is usable without re-entering identity every commit.

---

## 4. Secret storage checks

Check the CANONICAL store — the same file `qc-github-setup.sh` reads. Presence
only; never print a token value.

```bash
SKILLS_DIR="$HOME/.openclaw/skills"; [ -d /data/.openclaw/skills ] && SKILLS_DIR=/data/.openclaw/skills
[ -f "$SKILLS_DIR/lib-shared.sh" ] && . "$SKILLS_DIR/lib-shared.sh"
command -v resolve_platform_paths >/dev/null 2>&1 || resolve_platform_paths() {
  if [ -d /data/.openclaw ]; then export SECRETS_ENV="/data/.openclaw/secrets/.env"
  else export SECRETS_ENV="$HOME/.openclaw/secrets/.env"; fi
}
resolve_platform_paths
echo "Canonical secrets store: $SECRETS_ENV"
for k in GITHUB_TOKEN GITHUB_USERNAME; do
  if grep -q "^${k}=." "$SECRETS_ENV" 2>/dev/null; then echo "$k: SET"; else echo "$k: NOT-SET"; fi
done
```

- [ ] `GITHUB_TOKEN` reports SET in the canonical store
- [ ] `GITHUB_USERNAME` reports SET in the canonical store
- [ ] Token starts with `ghp_`
- [ ] Token is not written into repo docs or committed files

---

## 5. API verification tests

### 5A. Login test
```bash
# $SECRETS_ENV was resolved in section 4 above — the canonical store.
set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user | jq -r '.login'
```

- [ ] Returns the expected GitHub username
- [ ] Does not return `null`

### 5B. Scope header test
```bash
curl -sI -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user | tr -d '
' | grep -i '^x-oauth-scopes:'
```

- [ ] Header includes `repo`
- [ ] Header includes `read:org`
- [ ] Header includes `workflow`

**PASS:** PAT is valid and has the required least-privilege scopes.

---

## 6. Failure conditions

Fail this skill if any of these happen:

- [ ] `skill-version.txt` is wrong
- [ ] `GITHUB_TOKEN` or `GITHUB_USERNAME` is missing
- [ ] API call returns `Bad credentials`, `Requires authentication`, or `null`
- [ ] Scope header is missing one of `repo`, `read:org`, or `workflow`
- [ ] Git identity or credential helper is not configured

---

## Final pass rule

Pass only if all of the following are true:

- [ ] Files and version are correct
- [ ] Core file summaries are correct and lean
- [ ] Git is configured locally
- [ ] PAT and username are stored correctly
- [ ] GitHub API login and scope checks pass

---

## 🔴 INSTALL-TIME QC RUBRIC (v9.3.0+ standard — added automatically)

After install, score yourself honestly against this rubric. **Pass gate: 8.5/10 minimum.** Below 8.5 = loop back and fix until passing (max 5 loops, then escalate to owner).

### Score breakdown (10 points)

| Section | Points | What it tests |
|---|---|---|
| Prerequisites + INSTALL-CONTRACT.md acknowledged | 1.0 | INSTALL-CONTRACT.md was read this session AND acknowledged in your work log for this specific skill. All prerequisite skills installed. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md (this file), any referenced `references/*.md`. Reading happened BEFORE any command was run. |
| INSTALL.md steps executed in order | 1.5 | No skipping, no reordering, no improvising. If a step was skipped, owner consent is documented. |
| Credentials at canonical paths with canonical names | 1.5 | `~/.openclaw/secrets/.env` (Mac) / `~/.openclaw/secrets/.env` (VPS), chmod 600. Canonical env-var names used (not deprecated ones). For GHL: `GOHIGHLEVEL_API_KEY` (a PIT, not an API key) + `GOHIGHLEVEL_LOCATION_ID`. |
| Functional checks pass | 1.5 | The skill's specific smoke tests (API reachability, software present, etc.) all return expected results. No 4xx/5xx unhandled. |
| CORE_UPDATES.md applied surgically | 1.0 | Only labeled sections added to labeled core files. No SOUL.md / IDENTITY.md / USER.md / HEARTBEAT.md touched unless this skill's CORE_UPDATES.md explicitly labels them. |
| Skill-specific QC items above all checked | 1.5 | Every checkbox in the skill-specific sections of THIS QC.md is ticked. |
| Security | 0.5 | No PIT or other secret leaked into chat / logs / commits / .md files. Secrets file chmod 600. |
| Owner-facing confirmation message sent | 0.5 | The final summary was sent in plain English with structure: "Skill NN active. Anything pending your attention: [list]." |

### Loop-until-passing rule

If score < 8.5:
1. Identify the lowest-scoring section
2. Apply the smallest fix possible
3. Re-run only the failed checks
4. Re-score
5. After 5 loops, STOP and escalate to owner via Telegram with: which sections failed, what you tried, what's blocking

### Bundled `qc-skill-NN.sh`

If a `qc-skill-NN.sh` script exists in this skill folder, run it. Exit 0 is required in addition to the rubric score. The script catches mechanical items the rubric assumes (file modes, env-var format, network reachability).

### Self-audit before declaring done

Recite in your work log:
1. INSTALL-CONTRACT.md acknowledged for this skill: ✓ / ✗
2. All .md files read before execution: ✓ / ✗
3. INSTALL.md step order followed verbatim: ✓ / ✗
4. QC rubric score: __/10 (≥ 8.5 to pass)
5. Bundled qc-*.sh exited 0: ✓ / ✗ / N/A
6. No shortcuts taken (no `--force`, etc.): ✓ / ✗
7. Owner confirmation message sent: ✓ / ✗

If any answer is ✗, this skill is NOT done. Loop back.
