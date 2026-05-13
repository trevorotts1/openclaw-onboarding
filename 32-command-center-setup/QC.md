# QC Checklist — Skill 32: Command Center Setup

Run this after installation to verify the AI workforce is actually live: workspaces, Telegram topics, dashboard, and tunnel.

---

## Section 1: File Structure + Version Check

```bash
SKILL_DIR="$HOME/.openclaw/skills/32-command-center-setup"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.openclaw/skills/command-center-setup"

echo "Using skill dir: $SKILL_DIR"

for f in SKILL.md INSTALL.md INSTRUCTIONS.md CORE_UPDATES.md command-center-setup.skill skill-version.txt; do
  [ -f "$SKILL_DIR/$f" ] && echo "PASS: $f" || echo "FAIL: $f missing"
done

for s in create-tunnel.sh seed-workspaces.py setup-tunnel-daemon.sh; do
  [ -f "$SKILL_DIR/scripts/$s" ] && echo "PASS: scripts/$s" || echo "FAIL: scripts/$s missing"
done
```

**Pass criteria:** all required files and scripts are present.

---

## Section 2: Local Dependency Checks

```bash
node --version >/dev/null 2>&1 && echo "PASS: node found" || echo "FAIL: node missing"
npm --version >/dev/null 2>&1 && echo "PASS: npm found" || echo "FAIL: npm missing"
pm2 --version >/dev/null 2>&1 && echo "PASS: pm2 found" || echo "FAIL: pm2 missing"
python3 --version >/dev/null 2>&1 && echo "PASS: python3 found" || echo "FAIL: python3 missing"
cloudflared --version >/dev/null 2>&1 && echo "PASS: cloudflared found" || echo "INFO: cloudflared not installed yet"
```

**Pass criteria:** node, npm, pm2, and python3 must exist. `cloudflared` is required once tunnel setup is complete.

---

## Section 3: Skill 23 / Workspace Preconditions

This skill depends on department output from Skill 23.

```bash
for p in "$HOME/clawd/departments" "$HOME/.openclaw/workspaces/command-center" "$HOME/Downloads/openclaw-master-files"; do
  [ -d "$p" ] && echo "INFO: found directory $p"
done

[ -d "$HOME/.openclaw/workspaces/command-center" ] \
  && echo "PASS: command-center workspace root exists" \
  || echo "FAIL: command-center workspace root missing"

find "$HOME/.openclaw/workspaces/command-center" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sed 's#^.*/##' | sort
```

For each department workspace, verify required memory files:

```bash
for d in "$HOME/.openclaw/workspaces/command-center"/*; do
  [ -d "$d" ] || continue
  name=$(basename "$d")
  [ -f "$d/IDENTITY.md" ] && echo "PASS: $name/IDENTITY.md" || echo "FAIL: $name/IDENTITY.md missing"
  [ -f "$d/MEMORY.md" ] && echo "PASS: $name/MEMORY.md" || echo "FAIL: $name/MEMORY.md missing"
  [ -d "$d/memory" ] && echo "PASS: $name/memory/" || echo "FAIL: $name/memory/ missing"
done
```

**Pass criteria:** workspace root exists and every department has `IDENTITY.md`, `MEMORY.md`, and `memory/`.

---

## Section 4: Agent + Binding Checks

Verify `openclaw.json` contains command-center department agents and Telegram bindings.

```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'.openclaw/openclaw.json'
obj = json.loads(p.read_text())
agents = obj.get('agents', {}).get('list', [])
cc = [a for a in agents if 'command-center' in str(a.get('workspace',''))]
print('command-center agent entries:', len(cc))
for a in cc:
    print('-', a.get('name'), '| workspace =', a.get('workspace'))
PY
```

```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'.openclaw/openclaw.json'
obj = json.loads(p.read_text())
channels = obj.get('channels', {})
print('telegram config present:', 'telegram' in channels)
print(json.dumps(channels.get('telegram', {}), indent=2)[:2000])
PY
```

**Pass criteria:** one persistent agent entry per department, plus Telegram topic bindings for those agents.

---

## Section 5: Dashboard Checks

```bash
HTTP_CODE=$(curl -s -o /tmp/command_center_home.html -w "%{http_code}" http://localhost:4000)
echo "HTTP: $HTTP_CODE"
[ "$HTTP_CODE" = "200" ] && echo "PASS: dashboard reachable" || echo "FAIL: dashboard not reachable"

pm2 list | grep -i command-center \
  && echo "PASS: PM2 has command-center process" \
  || echo "FAIL: command-center PM2 process missing"
```

Run the workspace seeding script if not already done:

```bash
python3 "$SKILL_DIR/scripts/seed-workspaces.py"
```

**Expected:** output like `Seeding complete. Inserted: X | Skipped (already existed): Y`.

**Pass criteria:** dashboard serves on port 4000 and PM2 shows the process.

---

## Section 6: Tunnel Checks (Phase 6b)

If public access has been configured, verify the tunnel token and process.

```bash
grep '^CLOUDFLARE_TUNNEL_TOKEN=' "$HOME/.openclaw/.env" 2>/dev/null \
  && echo "PASS: tunnel token persisted" \
  || echo "INFO: CLOUDFLARE_TUNNEL_TOKEN not yet stored"

pm2 list | grep -i cloudflare-tunnel \
  && echo "PASS: PM2 has cloudflare-tunnel process" \
  || echo "INFO: cloudflare-tunnel process not found"
```

**Pass criteria:** once tunnel setup is complete, both token and PM2 process should exist.

---

## Section 7: Functional Behavior Tests

### 7.1 Department response routing

Send a test message in one department topic.

**Expected:** the correct department head responds in that same topic within about 30 seconds.

### 7.2 Cross-department topic

Send a coordination request in the Cross-Department topic.

**Expected:** the system routes cross-functional discussion there, not into a random department topic.

### 7.3 Department memory isolation

Inspect two department workspaces.

**Expected:** each has its own `MEMORY.md` and `memory/` folder. One department's memory should not overwrite another's.

### 7.4 Persona runtime

Prompt a department with a task that should use persona search.

**Expected:** the department head explains the selected persona/workflow and does not act like a generic bot.

---

## Section 8: Knowledge Verification

**Q1.** What is mandatory before Skill 32 can run?
> **Expected:** Skill 23 must already be complete.

**Q2.** What are the three live surfaces created by this skill?
> **Expected:** persistent department agents, Telegram control room with topics, and a dashboard at localhost:4000.

**Q3.** What must exist in each department workspace?
> **Expected:** `IDENTITY.md`, `MEMORY.md`, and `memory/`.

**Q4.** Where should the dashboard be reachable locally?
> **Expected:** `http://localhost:4000`

**Q5.** What process manager is used for the dashboard and tunnel?
> **Expected:** PM2.

**Pass criteria:** 5/5 correct.

---

## Section 9: Anti-Pattern Checks

Fail the skill if any of these happen:

- Skill 32 is reported complete before Skill 23 outputs exist
- department workspaces are missing or incomplete
- agents.list entries are missing for some departments
- Telegram topics were not created one-per-department plus Cross-Department
- dashboard is not reachable on localhost:4000
- workspace seeding was skipped, leaving only a default workspace in the UI
- cloudflare tunnel is reported live but there is no token or PM2 process
- test message in a department topic is answered by the wrong agent or no agent

**Pass criteria:** zero anti-patterns triggered.

---

## 🔴 INSTALL-TIME QC RUBRIC (v9.3.0+ standard — added automatically)

After install, score yourself honestly against this rubric. **Pass gate: 8.5/10 minimum.** Below 8.5 = loop back and fix until passing (max 5 loops, then escalate to owner).

### Score breakdown (10 points)

| Section | Points | What it tests |
|---|---|---|
| Prerequisites + INSTALL-CONTRACT.md acknowledged | 1.0 | INSTALL-CONTRACT.md was read this session AND acknowledged in your work log for this specific skill. All prerequisite skills installed. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md (this file), any referenced `references/*.md`. Reading happened BEFORE any command was run. |
| INSTALL.md steps executed in order | 1.5 | No skipping, no reordering, no improvising. If a step was skipped, owner consent is documented. |
| Credentials at canonical paths with canonical names | 1.5 | `~/.openclaw/secrets/.env` (Mac) / `/data/.openclaw/secrets/.env` (VPS), chmod 600. Canonical env-var names used (not deprecated ones). For GHL: `GOHIGHLEVEL_API_KEY` (a PIT, not an API key) + `GOHIGHLEVEL_LOCATION_ID`. |
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
