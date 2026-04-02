# QC Checklist - Skill 10: GitHub Setup
**Version:** v6.5.6

Run this after installation. Every section must pass before you mark GitHub setup complete.

---

## 1. File and version checks

```bash
SKILL_DIR="$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding/10-github-setup"
ls -1 "$SKILL_DIR"
cat "$SKILL_DIR/skill-version.txt"
```

- [ ] Required files exist: `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`, `github-setup-full.md`, `QC.md`, `skill-version.txt`
- [ ] `skill-version.txt` returns `v6.5.6`
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

```bash
grep -n '^GITHUB_TOKEN=' ~/clawd/secrets/.env 2>/dev/null
grep -n '^GITHUB_USERNAME=' ~/clawd/secrets/.env 2>/dev/null
```

- [ ] `GITHUB_TOKEN` exists in secrets storage
- [ ] `GITHUB_USERNAME` exists in secrets storage
- [ ] Token starts with `ghp_`
- [ ] Token is not written into repo docs or committed files

---

## 5. API verification tests

### 5A. Login test
```bash
source ~/clawd/secrets/.env 2>/dev/null || true
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
