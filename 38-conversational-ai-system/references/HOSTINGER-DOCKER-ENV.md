# Hostinger Docker VPS — Where the Environment Lives + How to Find Any Key (Skill 38)

> **Read this BEFORE you ever say "I don't have that API key" or "I can't find the env."**
>
> On a Hostinger VPS, OpenClaw runs **inside Docker**. ~95% of "I can't find it" reports are the
> agent never having looked in `/docker/<project>/.env`. This file tells you exactly where the
> environment lives and gives you a copy-paste discovery sequence you MUST run before reporting
> anything missing.

These facts are **verified live on a real client box** (a Hostinger Docker VPS). Use them exactly.

---

## 1. Where the environment lives

OpenClaw on a Hostinger VPS is a Docker container. There are three places the environment surfaces, and
you must understand the relationship between them:

| Location | Path | What it is |
|---|---|---|
| **Host `.env` (CANONICAL)** | `/docker/<project>/.env` | The docker-compose `env_file`. This is the canonical place to **read** AND **add** API keys. ALL the client's keys live here. |
| **Container mirror** | `/data/.openclaw/.env` (inside the container) | Bind-mounted from host `/docker/<project>/data/.openclaw/.env` via docker-compose `volumes: ./data:/data`. Scripts that `grep` an env file read this one. |
| **Live process env** | `docker exec <container> printenv` | The actual environment variables the OpenClaw process sees right now. Ground truth for "what the running process actually has." |

The host-level `/docker/<project>/.env` is wired into the container two ways:

1. **`env_file:`** in `docker-compose.yml` → the keys become real process environment variables
   (visible via `docker exec <container> printenv`).
2. **`volumes: ./data:/data`** bind mount → host `/docker/<project>/data/.openclaw/.env` shows up
   inside the container at `/data/.openclaw/.env`, where file-reading scripts find it.

Both persist across container restarts (bind mounts + host file). Host-level `/docker/<project>/.env`
is the one to edit — it matches the existing pattern (the Anthropic / OpenAI / Gemini keys all live
there) and it is what `docker exec printenv` reflects.

### What a real host `.env` contains

On the verified box, `/docker/<project>/.env` held ALL of these (your client's set will be similar):

```
OPENCLAW_GATEWAY_TOKEN
ANTHROPIC_API_KEY
OPENAI_API_KEY
GEMINI_API_KEY
MOONSHOT_API_KEY
OPENROUTER_API_KEY
TELEGRAM_BOT_TOKEN
XAI_API_KEY
OLLAMA_API_KEY
CLOUDFLARE_API_TOKEN
GHL_API_KEY
GHL_LOCATION_ID
NOTION_API_KEY
OPENCLAW_HOOKS_TOKEN
PODBEAN_PODCAST_ID
```

If you can see keys like `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in there, **you are in the right place.**

---

## 2. The EXACT discovery sequence (copy-paste)

Run this, in this order, EVERY time before you conclude a key/env value is missing:

```bash
# Step 1 — find the container + derive the project name
docker ps --format "{{.Names}}"
#   e.g. output:  openclaw-hy5t-openclaw-1
#   the project is the part BEFORE  -openclaw-1  →  openclaw-hy5t
#   so the host env dir is:  /docker/openclaw-hy5t/

# (confirm the project dir exists)
ls -d /docker/*/

# Step 2 — read the canonical host env file (substitute <project>)
cat /docker/<project>/.env
#   …or just LIST the key NAMES without exposing values:
grep -oE "^[A-Z_]+=" /docker/<project>/.env | sort -u

# Step 3 — ground-truth: what the live process actually sees
docker exec <container> printenv | grep -E "API_KEY|TOKEN"
#   <container> is the name from Step 1, e.g. openclaw-hy5t-openclaw-1
```

If a key you need shows up in Step 2 or Step 3 → use it. If it does NOT show up but OTHER keys do →
the key simply needs to be **ADDED here** (see §4), it is NOT "missing / I can't find it."

---

## 3. THE HARD RULE (non-negotiable)

**BEFORE claiming any API key or env value is missing, you MUST run the discovery sequence in §2.**

- If you can see OTHER keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.) in `/docker/<project>/.env`,
  you are in the **RIGHT place**. A key you need that isn't there should be **ADDED here** (§4),
  **NOT reported as "I can't find it."**
- Do **NOT** say "I don't have this information" / "I don't have access to that key" until you have
  **actually `cat`'d `/docker/<project>/.env`** AND **run `docker exec <container> printenv`**.
- ~95% of "I can't find it" is the agent never having looked in `/docker/<project>/.env`. Looking in
  `~/.openclaw/.env` or the home directory on a Hostinger Docker box and finding nothing is **not**
  evidence the key is missing — those are not where the Docker container's environment lives.

If, after running the full §2 sequence, the key genuinely is not present anywhere, THEN (and only then)
you may tell the operator it needs to be created/added — and you immediately point them to §4 for how
to add it.

---

## 4. How to ADD a key (the canonical procedure)

When a key genuinely needs to be added (confirmed missing per §3):

```bash
# 1) Append to the canonical HOST env file (substitute <project> and your KEY/value)
echo 'NEW_API_KEY=the-value-here' >> /docker/<project>/.env

# 2) Mirror it into the container-side env file so file-reading scripts also see it
echo 'NEW_API_KEY=the-value-here' >> /docker/<project>/data/.openclaw/.env

# 3) Recreate the container so the new env_file values are actually loaded.
#    plain `restart` does NOT reload env_file changes — you MUST force-recreate.
docker compose -f /docker/<project>/docker-compose.yml up -d --force-recreate

# 4) Verify the live process now sees it
docker exec <container> printenv | grep NEW_API_KEY
```

> **`docker compose restart` does NOT reload `env_file` changes.** Use
> `docker compose up -d --force-recreate` after editing `/docker/<project>/.env`, or the new variable
> will not appear in the running container.

---

## 5. The `hooks.token` wrapper gotcha (VPS-specific)

The Hostinger wrapper at `/hostinger/server.mjs` runs on **every container boot** and **rewrites**
`hooks.token` in `openclaw.json` to:

```
$OPENCLAW_HOOKS_TOKEN  ||  hooks_${OPENCLAW_GATEWAY_TOKEN}
```

This is the wrapper, NOT `openclaw doctor`. Consequence: to make a HOOKS_TOKEN persistent across boots,
**`OPENCLAW_HOOKS_TOKEN` must be set in the host `/docker/<project>/.env`** (per §4). If it is not set,
the wrapper silently derives `hooks_<gateway-token>` on every boot and any token you set by hand is lost
on the next recreate. See `references/GHL-INBOUND-AND-PLAYBOOKS.md` §1 (the four-token model) for how
`OPENCLAW_HOOKS_TOKEN` relates to the GHL Build-with-AI prompt's `Authorization: Bearer` header.

---

## 6. Quick reference — common mistakes that cause false "missing key" reports

- ❌ Looking in `~/.openclaw/.env` on the host shell and finding nothing → that's not the container's env.
- ❌ Running `printenv` in the **host** shell instead of `docker exec <container> printenv`.
- ❌ Editing `/docker/<project>/.env` then running `docker compose restart` (does not reload env_file).
- ❌ Concluding "no key" because one search path was empty without running the full §2 sequence.
- ✅ Run §2 in full → if other keys are visible, you're in the right place → add (§4) or use, never "missing."
