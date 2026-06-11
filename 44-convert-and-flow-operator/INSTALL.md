# Skill 44 — Convert and Flow Operator: Install Guide

## Prerequisites

- Skill 01 (TYP) installed
- Skill 02 (BYUP) installed — back up config before editing
- Skill 36 (GHL MCP Setup) installed — skill 44 is Tier 0 in skill 36's chain
- Skill 41 (Build With AI Playbook) installed — skill 44 consumes its dependency-first contract
- Python 3.9+ on the install box
- Active GHL / Convert and Flow account with a Location PIT

---

## Action 1: Detect platform

```bash
if [[ "$(uname)" == "Darwin" ]]; then
  PLATFORM="mac"
  TOOLS_ROOT="$HOME/.openclaw/tools"
else
  PLATFORM="vps"
  TOOLS_ROOT="/data/.openclaw/tools"
fi
CAF_DIR="$TOOLS_ROOT/convert-and-flow-cli"
```

## Action 2: Create venv and install engine

```bash
mkdir -p "$CAF_DIR"
python3 -m venv "$CAF_DIR/.venv"
source "$CAF_DIR/.venv/bin/activate"

# Copy engine from master files (includes wire-ghl-env.sh + verify-ghl-live.sh)
cp -r "$MASTER_FILES_DIR/44-convert-and-flow-operator/tools/engine/." "$CAF_DIR/engine/"
chmod +x "$CAF_DIR/engine/wire-ghl-env.sh" "$CAF_DIR/engine/verify-ghl-live.sh" 2>/dev/null || true
cd "$CAF_DIR/engine"
pip install -e . --quiet
deactivate
```

## Action 3: Install the wrapper (single source — copies committed engine wrapper)

> **Why copy instead of heredoc?** The committed wrapper at
> `tools/engine/caf` is the single source of truth. Copying it to the install
> directory means there is exactly one place to edit the wrapper logic; the
> INSTALL.md heredoc approach created a second copy that could silently diverge
> (as happened with the `gohighlevel.main` entrypoint bug fixed in PR #167).

```bash
# Copy the committed wrapper + aliases from the engine directory
cp "$MASTER_FILES_DIR/44-convert-and-flow-operator/tools/engine/caf"          "$CAF_DIR/caf"
cp "$MASTER_FILES_DIR/44-convert-and-flow-operator/tools/engine/convertandflow" "$CAF_DIR/convertandflow"
cp "$MASTER_FILES_DIR/44-convert-and-flow-operator/tools/engine/ghl"           "$CAF_DIR/ghl"
chmod +x "$CAF_DIR/caf" "$CAF_DIR/convertandflow" "$CAF_DIR/ghl"
```

> **What the wrapper does:** maps canonical `GOHIGHLEVEL_*` env vars to the engine's
> internal `GHL_*` names, auto-seeds `CAF_ALLOWED_LOCATION_IDS` from
> `GOHIGHLEVEL_LOCATION_ID` on a blank whitelist, enforces `CAF_DRAFT_ONLY=true` by
> default, and invokes the engine via `python -m cli_anything.gohighlevel`.

## Action 4: Add wrapper dir to PATH (persistent)

### Mac
```bash
# Add to .zshrc (or .bash_profile)
echo "export PATH=\"$CAF_DIR:\$PATH\"" >> "$HOME/.zshrc"
source "$HOME/.zshrc"

# Also wire via openclaw config
openclaw config set env.vars.PATH "$CAF_DIR:\${PATH}"
```

### VPS
```bash
# Add to openclaw gateway env
openclaw config set env.vars.PATH "$CAF_DIR:/usr/local/bin:/usr/bin:/bin"
```

## Action 5: Wire credentials into the gateway-inherited env (single source)

> **WHY A SCRIPT, NOT INLINE `openclaw config set` (Evelyn VPS bug, 2026-06-11):**
> The previous install left the `GOHIGHLEVEL_*` creds **only** in
> `~/.openclaw/secrets/.env` — a file the OpenClaw gateway/agent **process never
> loads.** When the agent invoked `caf`, the gateway's process env had no
> `GOHIGHLEVEL_LOCATION_ID`, so the engine died at
> `Error: GHL_LOCATION_ID environment variable is not set.` while the install had
> already reported success. On the Hostinger VPS it was worse: the docker-compose
> `env_file` (`/docker/<project>/.env`) carried **empty placeholder lines**
> (`GOHIGHLEVEL_API_KEY=` with no value, no FIREBASE line). docker injects an empty
> `env_file` value as an **empty string** into the container process env, and an
> empty string still wins against the secrets file for any consumer that reads
> `os.environ` — so it **masked** the real value everywhere.
>
> The committed script `tools/engine/wire-ghl-env.sh` is the **single source** for
> all of this so the logic can never drift from an inline heredoc (the same drift
> class as the `gohighlevel.main` bug). It:
> 1. Wires all **5** canonical vars into `openclaw.json` `env.vars` (the block the
>    gateway inherits at process start). It tries `openclaw config set` first and
>    **falls back to a direct JSON deep-merge** into `openclaw.json` when
>    `config set` rejects the nested key — the supported pattern on OpenClaw
>    2026.5.20+ (same approach as `31-upgraded-memory-system/scripts/activate-memory-stack.sh`).
> 2. **VPS only:** ALSO populates the host `/docker/<project>/.env`, **replacing
>    any empty `GOHIGHLEVEL_*=` placeholder line in place** (an empty placeholder
>    overrides the real value with an empty string). Reached only when `/docker`
>    is visible (i.e. run on the host, not inside the container).
> 3. **Mac only:** wires `env.vars` but does **NOT** restart the gateway
>    (rescue-Mac rule); it prints that a `launchctl kickstart` may be needed for
>    the running gateway to inherit the new `env.vars`.

The 5 canonical vars (engine wrapper maps `GOHIGHLEVEL_*` → `GHL_*`):
`GOHIGHLEVEL_API_KEY` (PIT, required), `GOHIGHLEVEL_LOCATION_ID` (required),
`GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` (optional — workflow writes only),
`GOHIGHLEVEL_ALLOWED_LOCATION_IDS` (write-location whitelist — defaults to the
client's own location), `GOHIGHLEVEL_DRAFT_ONLY` (write-safety default — `true`).

```bash
# Single-source wiring. Reads values from the process env OR ~/.openclaw/secrets/.env.
bash "$CAF_DIR/engine/wire-ghl-env.sh"
WIRE_RC=$?

if [ "$WIRE_RC" -eq 2 ]; then
  # Required creds (API key / location id) are genuinely absent everywhere.
  # This is NOT a hard failure and NOT a silent success: the CLI is installed but
  # cannot reach GHL yet. Mark it installed-with-missing-prereqs and tell the
  # operator EXACTLY which vars to add to ~/.openclaw/secrets/.env, then re-run.
  echo "[skill44] INSTALLED-WITH-MISSING-PREREQS: add GOHIGHLEVEL_API_KEY + GOHIGHLEVEL_LOCATION_ID"
  echo "[skill44] to ~/.openclaw/secrets/.env, then re-run: bash \"$CAF_DIR/engine/wire-ghl-env.sh\""
elif [ "$WIRE_RC" -ne 0 ]; then
  echo "ERROR: wire-ghl-env.sh failed (rc=$WIRE_RC)"; exit 1
fi
```

> **VPS host context:** if you run the installer on the Hostinger **host** (so
> `/docker` is visible), the script auto-finds and updates the OpenClaw project's
> `/docker/<project>/.env`. Then apply with a **force-recreate** so the container
> re-reads `env_file` (a plain `docker restart` does NOT re-read it):
> ```bash
> docker compose -f /docker/<project>/docker-compose.yml up -d --force-recreate
> ```
> If the installer is running **inside** the container (where `/docker` is not
> visible), the `env.vars` wiring above is the gateway-inherited path; populate
> the host `env_file` from the host separately if needed.

Firebase token (workflow writes — OPTIONAL at install time): the script wires it
automatically when present in the env / secrets file; absence is a no-op, never a
failure. If the client captures it later, just re-run `wire-ghl-env.sh`.

---

## Action 5b: Load the Token Grabber Chrome Extension (first time)

> **What this does:** The Token Grabber is a small Chrome extension that reads your
> Firebase refresh token from the logged-in GHL / Convert and Flow page and copies it
> to your clipboard. It makes **zero network calls** — it only reads from your own
> browser's storage.

### Get the extension folder

The extension folder is already included in this skill at:
```
44-convert-and-flow-operator/tools/chrome-extension/
```
It contains four files: `manifest.json`, `popup.html`, `popup.js`, `icon48.png`.

> **Do NOT upload this to the Chrome Web Store.** We are using the "load unpacked"
> method — the extension lives as a folder on your computer, not in the Chrome store.

### Install steps (one time)

1. Open Chrome and go to: **chrome://extensions**
2. Flip the **Developer mode** toggle in the top-right corner to **ON**.
3. Click the **"Load unpacked"** button that appears.
4. Navigate to the `tools/chrome-extension/` folder inside this skill and click **Select**.
5. The "Convert and Flow Token Grabber" extension will appear in your list. Done.

### Grab your token

1. Open any logged-in page on:
   - `https://app.convertandflow.com`
   - `https://app.gohighlevel.com`
   - `https://app.leadconnectorhq.com`
2. Click the extension icon in your Chrome toolbar.
3. Click **"Grab Refresh Token"**.
4. Click **"Copy to Clipboard"** — the token is now on your clipboard.

### Store the token

Paste the value into your secrets file:
```
GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=<paste token here>
```

Then wire it into OpenClaw:
```bash
openclaw config set env.vars.GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN "$GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN"
```

### After editing extension files

Because the extension is "unpacked" (not from the Chrome store), it does **not**
auto-update. If you ever edit the extension files, go back to **chrome://extensions**
and click the **↻ (refresh)** icon on the extension card to reload it.

> **Note on extension IDs:** Chrome assigns a unique extension ID when you load unpacked.
> Each computer gets its own ID — that is normal and expected. (The operator's installed
> copy has ID `mghmjilakepcjpjinhcgnnghenlfigid` as a reference example only; your ID
> will be different and does not affect how the extension works.)

---

## Action 6: Run `caf doctor`

```bash
caf doctor
```

Expected output: all checks green. If the Firebase token is absent, `caf doctor` should report
WARN (not FAIL) — the skill works for standard ops without it.

---

## Action 6b: FAIL-LOUD live verify gate (MANDATORY — never report success on a dead caf)

> **WHY (Evelyn VPS bug, 2026-06-11):** the install reported success while `caf`
> could not reach GHL at all (creds only in `secrets/.env`, masked by empty docker
> `env_file` placeholders). A "skill installed" flag is **not** proof the tool
> works. This gate runs a **real read** against GHL using **only the inherited
> process env** (it deliberately does NOT source any secrets file — it reproduces
> exactly what the gateway/agent process sees) and **FAILS LOUDLY** if it errors.
> Never mark skill 44 success when `caf` can't reach GHL.

```bash
bash "$CAF_DIR/engine/verify-ghl-live.sh"
VERIFY_RC=$?

case "$VERIFY_RC" in
  0)
    echo "[skill44] LIVE-VERIFIED: caf reached GHL with a real read. Skill 44 is live."
    ;;
  2)
    # Required creds genuinely absent. Installed-with-missing-prereqs — the gate
    # already printed exactly which vars. NOT a success, NOT a hard crash.
    echo "[skill44] INSTALLED-WITH-MISSING-PREREQS (see verify output for the exact vars)."
    echo "[skill44] Add them to ~/.openclaw/secrets/.env, re-run wire-ghl-env.sh, then re-run this gate."
    ;;
  *)
    # rc=1: creds present but the live read FAILED. This FAILS the install step.
    echo "ERROR: skill 44 live verify FAILED — caf could not reach GHL despite creds being present."
    echo "       Do NOT report skill 44 as successfully installed. See the verify output above."
    exit 1
    ;;
esac
```

> **What the gate runs:** `caf workflows list` (the workflow-read path), falling
> back to `caf contacts list --limit 1` (PIT-only) if the workflow read fails —
> because workflow reads can legitimately fail without the Firebase token, while a
> PIT-only contacts read still proves core reachability. Exit 0 = live; exit 2 =
> installed-with-missing-prereqs (lists the vars); exit 1 = present-but-unreachable
> (fails the install).

---

## Action 7: Apply CORE_UPDATES to agent core files (auto)

> **This step is mandatory.** Until the sentinel is present in AGENTS.md / TOOLS.md /
> MEMORY.md the agent does NOT know Skill 44 is installed and will not use Tier 0.

```bash
WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
SENTINEL="<!-- skill:44-convert-and-flow-operator:core-update-applied -->"
CORE_UPDATES="$MASTER_FILES_DIR/44-convert-and-flow-operator/CORE_UPDATES.md"

# Guard: skip if already applied
if grep -qF "$SENTINEL" "$WORKSPACE/AGENTS.md" 2>/dev/null; then
  echo "[skill44] CORE_UPDATES already applied — skipping."
else
  echo "[skill44] Applying CORE_UPDATES to AGENTS.md / TOOLS.md / MEMORY.md ..."

  # --- AGENTS.md ---
  cat >> "$WORKSPACE/AGENTS.md" <<'AGENTS_BLOCK'

## Convert and Flow Operator — Tier 0 (skill 44)

Skill 44 is the FIRST STOP in the 6-tier GHL access chain. Try it before any MCP.

### When to use Tier 0

- Any GHL operation the CLI covers (contacts, opportunities, calendars, conversations,
  documents, payments, forms, social, locations, workflow reads): use `caf <command>`.
- Workflow BUILD or EDIT: check Firebase token first (see token-aware routing in skill 36
  AGENTS.md). Present + healthy = Tier 0 builds directly. Absent = Tier 4 backstop.
- Media upload: SKIP Tier 0. Always Tier 3 (POST /medias/upload-file).
- Rate limit (429): STOP. Never fall through. Surface reset time in plain English.

### Per-operation routing

See the full 6-tier table in skill 36's AGENTS.md block. Skill 44 owns Tier 0;
skill 36 owns the routing law for all 6 tiers.

### Disclosure format

[GHL tier used: 0 — convertandflow <command>]
<!-- skill:44-convert-and-flow-operator:core-update-applied -->
AGENTS_BLOCK

  # --- TOOLS.md ---
  cat >> "$WORKSPACE/TOOLS.md" <<'TOOLS_BLOCK'

## Convert and Flow CLI — Tier 0 GHL operator (skill 44)

Commands: caf / convertandflow / ghl

Installed at: ~/.openclaw/tools/convert-and-flow-cli/caf (Mac) or /data/.openclaw/tools/convert-and-flow-cli/caf (VPS)
Health: caf doctor

| Domain | Commands |
|---|---|
| contacts | caf contacts list/get/create/update/tag/untag |
| opportunities | caf opportunities list/get/update |
| calendars | caf calendars list/appointments |
| conversations | caf conversations list/get/send |
| documents | caf documents list/get/send |
| payments | caf payments list (= transactions); invoices/orders/transactions; create-invoice |
| forms | caf forms list/submissions |
| social | caf social accounts/post/schedule |
| locations | caf locations get/customfields/customvalues |
| workflows (read) | caf workflows list/get/export |
| workflows (write) | caf workflows build/patch-email/patch-trigger/restore [Firebase token required] |

Credentials: GOHIGHLEVEL_API_KEY (PIT), GOHIGHLEVEL_LOCATION_ID, GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN (workflow writes only).
<!-- skill:44-convert-and-flow-operator:core-update-applied -->
TOOLS_BLOCK

  # --- MEMORY.md ---
  INSTALL_DATE="$(date +%Y-%m-%d)"
  cat >> "$WORKSPACE/MEMORY.md" <<MEMORY_BLOCK

## Convert and Flow Operator — Installed ${INSTALL_DATE}

Skill 44 (Tier 0) installed. CLI at ~/.openclaw/tools/convert-and-flow-cli/.
Credentials: GOHIGHLEVEL_API_KEY (PIT), GOHIGHLEVEL_LOCATION_ID.
Firebase token for workflow writes: GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN (optional at install).
Write safety: GOHIGHLEVEL_DRAFT_ONLY=true, location whitelist, approval gate.
Health: caf doctor
<!-- skill:44-convert-and-flow-operator:core-update-applied -->
MEMORY_BLOCK

  echo "[skill44] CORE_UPDATES applied."
fi
```

---

## Client-Facing Disclosure: Firebase Token Auto-Re-Grab (Mac installs only)

> **PLAIN LANGUAGE (binding transparency requirement — PRD Section 3.2):**
>
> On Mac installs, your AI agent can refresh the Convert and Flow / GoHighLevel
> access token automatically when it expires. Here is what that means in plain language:
>
> - This token is the same one you copied from your browser at onboarding.
> - When it expires, your agent reads a fresh copy from your own logged-in Chrome
>   profile on THIS Mac — the same profile you normally browse in.
> - The token never leaves your Mac except into your own secrets file on this same machine.
> - Every time the agent refreshes the token, it logs a notification to your Telegram channel.
>   Nothing is silent.
> - If you ever want to turn this off, remove `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` from your
>   secrets file. The agent will ask you to re-grab it manually next time it needs a workflow build.
>
> **VPS installs:** there is no Chrome in the container, so the agent cannot auto-re-grab.
> On a VPS, the agent will notify you via Telegram: "I need you to grab the Convert and Flow
> token to build workflows directly" — you copy it from your browser and paste it in.

---

---

## Note: Write-location whitelist auto-seed (CAF_ALLOWED_LOCATION_IDS)

The wrapper reads `CAF_ALLOWED_LOCATION_IDS` (or its canonical alias
`GOHIGHLEVEL_ALLOWED_LOCATION_IDS`) as the list of location IDs that are
allowed to receive write operations (create/update/delete contacts, build
workflows, etc.). If **both** variables are empty the engine rejects every
write — which silently blocks all CRM operations on a fresh single-location install.

**What the wrapper now does automatically:** when neither variable is set, the
wrapper seeds the whitelist with the client's own `GOHIGHLEVEL_LOCATION_ID` and
logs a visible line to stderr:

```
[caf] Allowed write locations set to <id>; add more in CAF_ALLOWED_LOCATION_IDS
```

This means a standard single-location install works without any extra
configuration. If you manage multiple sub-accounts under one agent, add them
as a comma-separated list:

```bash
openclaw config set env.vars.GOHIGHLEVEL_ALLOWED_LOCATION_IDS \
  "$GOHIGHLEVEL_LOCATION_ID,<second-location-id>"
```

The draft-only and approval-gate safeties remain unchanged — the whitelist
controls WHICH locations can be written; the other guards control HOW writes are
approved and published.

---

## Done When

- [ ] `wire-ghl-env.sh` wired all present GHL vars into `openclaw.json` `env.vars` (Action 5)
- [ ] VPS: `/docker/<project>/.env` has NO empty `GOHIGHLEVEL_*=` placeholder lines (replaced in place)
- [ ] `verify-ghl-live.sh` exits 0 (live) — or exit 2 (installed-with-missing-prereqs, vars listed); NEVER reported success on exit 1 (Action 6b)
- [ ] `caf doctor` exits green (or WARN for missing Firebase token — not FAIL)
- [ ] `caf contacts list --limit 3` returns real contacts
- [ ] `caf workflows list` returns the workflow list
- [ ] `caf` resolves on PATH inside openclaw gateway
- [ ] `qc-convert-and-flow.sh` exits 0
- [ ] CORE_UPDATES sentinel present in AGENTS.md (auto-applied by Action 7)
