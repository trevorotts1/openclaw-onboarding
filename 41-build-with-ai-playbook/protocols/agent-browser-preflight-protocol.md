# Agent Browser Preflight Protocol -- Skill 41 Build With AI Playbook Generator

## Purpose

This protocol governs the install-time and runtime verification of Vercel Agent Browser
as the browser-execution rung for Skill 41's automated Build-With-AI executor.
It pairs with `scripts/06-verify-agent-browser.sh`, which is the runnable implementation.

Vercel Agent Browser + MiniMax M3 are the **committed execution stack** for Skill 41's
automated GHL Workflow AI Builder interaction (SPEC decisions (a) and (b)).
This protocol ensures the stack is present and proven before any live build run.

## When to run this preflight

| Trigger | Action |
|---|---|
| First-time Skill 41 install | Run 06-verify-agent-browser.sh as part of the install sequence (after 05-configure-executor-model.sh) |
| OpenClaw upgrade on any client machine | Re-run to confirm Agent Browser survives the upgrade |
| Browser execution fails at runtime | Re-run immediately to confirm install state before diagnosing runtime |
| Client machine OS upgrade (macOS or VPS image) | Re-run — Chromium linkage can break across OS versions |
| After any Docker image recreate on VPS | Re-run inside the new container |

## Preflight sequence (6 steps)

The script runs these steps in order. Every step is a hard gate: failure at any step
triggers the loud escalation banner and exits 1. No silent degradation ever.

### Step 1 — Node.js version gate

- Locates `node` on PATH or at known platform-specific locations.
- **Mac:** checks `$PATH`, then `/opt/homebrew/bin/node`, `/usr/local/bin/node`.
- **VPS:** checks `$PATH`, then `/usr/local/bin/node`, `/usr/bin/node`, nvm shims.
- Verifies Node.js major version >= 18. Agent Browser requires Node 18+ (ES module support,
  native fetch, Web Crypto API).
- **Failure:** LOUD banner + human-escalation directive. Never continues with unsupported Node.

### Step 2 — npm availability

- Locates `npm` on PATH or as a sibling of the resolved `node` binary.
- Required for the conditional install step.
- **Failure:** LOUD banner. Indicates a broken Node.js install.

### Step 3 — Install Agent Browser if absent

The install path is **platform-aware**:

#### Mac (Darwin)

```bash
npm install -g @vercel/agent-browser
```

Run as the current user (the Mac operator's login user). Homebrew-managed Node.js
installs npm in a user-writable prefix by default. If a permissions error occurs,
fix with:

```bash
sudo chown -R "$(whoami)" "$(npm config get prefix)"
```

Do NOT run as root on Mac.

#### VPS (Linux, Hostinger Docker)

The OpenClaw service user on VPS is `node`. Writing to the global npm prefix as root
causes a config-ownership freeze (OpenClaw cannot read its own config after restart).
**Always install as the `node` user:**

```bash
# If already running as 'node' user (or any non-root user):
npm install -g @vercel/agent-browser

# If running as root (e.g., docker exec with default root):
su -s /bin/sh node -c "npm install -g @vercel/agent-browser"
```

The script detects the current user at runtime and picks the correct path automatically.

After install the script re-locates the binary to confirm it is on PATH. If not found
after install, it fails loudly: a ghost install (npm reports success but binary is
unreachable) is treated as a failure, not a pass.

### Step 4 — Headless Chrome CDP probe

Runs a minimal ES-module Node.js script that:

1. Calls `createBrowser({ headless: true })` from `@vercel/agent-browser`
2. Opens a blank page (`about:blank`)
3. Evaluates `1 + 1` via CDP and asserts the result is `2`
4. Closes the browser cleanly

This proves the entire chain: npm package is loadable, Chromium binary is present
and launchable, CDP channel is operational, JS engine inside the browser responds.

**Common failure causes and fixes:**

| Symptom | Likely Cause | Fix |
|---|---|---|
| `Cannot find module '@vercel/agent-browser'` | Install step did not add the package to the Node.js module search path used by this node binary | Verify `npm root -g` matches where the package was installed; adjust `NODE_PATH` |
| `Failed to launch browser` or `spawn chromium ENOENT` | Chromium/Chrome not installed | Mac: `brew install --cask google-chrome`; VPS: `apt install chromium-browser` (or `/data/linuxbrew/.linuxbrew/bin/brew install chromium`) |
| `Running as root without --no-sandbox` | VPS container running as root; Chrome refuses to launch without sandbox flag | Set `AGENT_BROWSER_CHROMIUM_FLAGS=--no-sandbox` env var, then re-run (or switch to `node` user) |
| `EACCES` on temp dir | Chrome needs a writable temp directory | Ensure `/tmp` is writable by the service user |
| Probe hangs > 30s | Chromium started but CDP handshake stalled | Check for zombie Chrome processes (`ps aux | grep chrome`); kill them and retry |

### Step 5 — Encrypted auth vault check

The vault (`$OC_HOME/agent-browser-vault/`) stores the encrypted GHL session credentials
that Agent Browser uses to log into GHL and interact with the Workflow AI Builder.

| Vault state | Script behaviour |
|---|---|
| Directory does not exist | WARNING (not hard failure on first install). Human-escalation note logged. |
| Directory exists, no `.enc` files | WARNING. Auth pairing step has not been run yet. |
| Directory exists, `.enc` files present, readable | PASS. |
| Directory exists but not readable by current user | HARD FAILURE. Permissions error. Fix: `chmod +r $VAULT_DIR` |

**On a first-time install:** it is normal for the vault to not exist yet. Run the GHL
auth pairing step (separate from this preflight) to populate it, then re-run this
preflight to confirm vault reachability.

**At runtime (before a live build run):** the vault MUST be populated. If it is empty,
the build run fails at authentication -- degrade to human-escalation per the failure
protocol below.

### Step 6 — Preflight result record

Writes `$OC_HOME/skill-41-agent-browser-preflight.json` with fields:

```json
{
  "ts": "2026-06-03T00:00:00Z",
  "skill": "41-build-with-ai-playbook",
  "check": "agent-browser-preflight",
  "result": "PASS",
  "platform": "mac | vps",
  "node_bin": "/opt/homebrew/bin/node",
  "node_version": "v20.12.0",
  "agent_browser_bin": "/opt/homebrew/bin/agent-browser",
  "agent_browser_version": "1.0.0",
  "cdp_headless_probe": "PASSED",
  "vault_dir": "/Users/operator/.openclaw/agent-browser-vault",
  "vault_status": "OK | EMPTY | NOT_CREATED_YET"
}
```

This record is consumed by:
- `11-run-qc-checklist.sh` (confirms agent-browser preflight passed before sealing QC)
- The MiniMax executor preflight (gap #4) which checks this record exists and result=PASS
- Runtime harness (L1 auth test, L2 build-execution test) which gates on vault_status=OK

## Failure protocol: NEVER silent

If ANY step fails, the script:

1. Prints a loud multi-line banner (`!!!` bordered block) to stdout.
2. States the **reason** (exact error), the **impact** (browser rung unavailable),
   and the **required action** (human manual build, then fix and re-run).
3. Exits 1.

The calling install sequence (`INSTALL.md` and future `install.sh` wrappers) MUST treat
exit 1 from this script as a blocker that halts the automated build pipeline.
The agent MUST NOT attempt automated GHL browser interaction while this script returns exit 1.

**Human-escalation directive (agent behaviour on failure):**

```
"The Agent Browser preflight failed. The browser execution rung is unavailable.
 I cannot complete the GHL Workflow AI Builder step automatically.
 Please complete the GHL build step manually (Automations > Build using AI > paste prompt).
 I will guide you through the exact paste and verify the result.
 Once the environment issue is resolved and 06-verify-agent-browser.sh exits 0,
 automated browser execution will resume."
```

## Idempotency

Re-running `06-verify-agent-browser.sh` on an already-healthy system:
- Skips the install step (binary already found).
- Re-runs the CDP probe (fast, < 5s).
- Re-checks vault state.
- Overwrites the preflight result record with a fresh timestamp.
- Exits 0 if all checks pass.

Safe to run as part of every skill update or routine health check.

## Platform path reference

| Item | Mac (Darwin) | VPS (Linux, Docker) |
|---|---|---|
| OpenClaw home | `$HOME/.openclaw` | `/data/.openclaw` |
| Agent Browser vault | `$HOME/.openclaw/agent-browser-vault/` | `/data/.openclaw/agent-browser-vault/` |
| Preflight result | `$HOME/.openclaw/skill-41-agent-browser-preflight.json` | `/data/.openclaw/skill-41-agent-browser-preflight.json` |
| npm install user | Current user (operator login) | `node` service user |
| Chromium (Mac) | `brew install --cask google-chrome` or Chromium | Built into Docker image or via linuxbrew |
| VPS sandbox flag | Not needed (not running as root) | May need `--no-sandbox` if running as root |

## Relationship to MiniMax executor preflight (gap #4)

Gap #4 (`05-configure-executor-model.sh`) configures the **model** (MiniMax M3 via Ollama
Cloud or OpenRouter). Gap #5 (this protocol + `06-verify-agent-browser.sh`) verifies the
**browser**. Together they form the complete executor stack:

```
Executor stack = Agent Browser (gap #5) + MiniMax M3 (gap #4)
```

Run order during install:
1. `05-configure-executor-model.sh` -- configure the MiniMax model
2. `06-verify-agent-browser.sh` -- install + verify the browser (this script)

Both must pass before the skill's QC runner (`11-run-qc-checklist.sh`) proceeds to
the live harness tests (L1-L5, gap #6).

## See also

- `scripts/06-verify-agent-browser.sh` -- the runnable implementation of this protocol
- `scripts/05-configure-executor-model.sh` -- MiniMax executor preflight (gap #4)
- `references/platform-differences.md` -- Mac vs VPS path layout
- `protocols/build-with-ai-protocol.md` -- the master protocol governing automated builds
- `INSTALL.md` -- full install sequence (scripts 00 through 06)
