# Convert and Flow CLI

A command-line interface for GoHighLevel that lets you (or OpenClaw) drive your CRM from the terminal — contacts, opportunities, calendars, conversations, workflows, emails, payments, forms, social media, locations, and documents.

Part of the BlackCEO fleet — Skill 44: Convert and Flow Operator.

---

## What you get

- **11 command groups** covering the full GHL surface (contacts, opportunities, calendars, workflows, conversations, emails, payments, forms, social, locations, documents).
- **A REPL** — type `ghl` with no args and you get an interactive shell with autocomplete.
- **Workflow builders** — Python scripts that take a markdown file and turn it into a live GHL workflow (see `builders/`).
- **A Chrome extension** that grabs the Firebase token you need to use the "internal" GHL API (the public API can't create workflows; the internal one can).
- **A Claude Code skill** at `cli_anything/gohighlevel/skills/SKILL.md` so Claude can use the CLI on your behalf.

---

## Install (60 seconds)

Requirements: **Python 3.10+** and a GoHighLevel sub-account.

```bash
git clone <this repo> gohighlevel-cli
cd gohighlevel-cli
./install.sh
```

The installer creates a `.venv/`, installs the package, and copies `.env.example` → `.env`.

Open `~/.openclaw/secrets/.env` and fill in:

```env
GOHIGHLEVEL_API_KEY=pit-xxxxxxxx-...        # GHL Settings -> Private Integrations
GOHIGHLEVEL_LOCATION_ID=YOUR_LOCATION_ID    # the long ID in your GHL URL
```

The wrapper maps `GOHIGHLEVEL_API_KEY` -> `GHL_API_KEY` and `GOHIGHLEVEL_LOCATION_ID` -> `GHL_LOCATION_ID` at runtime. Engine source code stays untouched.

Smoke test:

```bash
./ghl contacts list --limit 5
```

You should see 5 contacts (or an empty list, depending on the account). Done.

---

## Quickstart examples

```bash
# Contacts
./ghl contacts search --query "test@"
./ghl contacts create --first-name Test --last-name User --email test@example.com
./ghl contacts tags add --contact-id <id> --tag consulti_trial

# Workflows
./ghl --json workflows list
./ghl workflows enroll --contact-id <id> --workflow-id <id>

# Opportunities
./ghl opportunities list --pipeline-id <id>

# Conversations
./ghl conversations list --contact-id <id>

# REPL (no args = interactive shell with autocomplete)
./ghl
```

`--json` works on most read commands and pipes cleanly into `jq`.

---

## Workflow building (the powerful part)

The public GHL API is read-only for workflows. To **create or update** workflows, the CLI uses GHL's internal API — and that needs a Firebase refresh token.

### Step 1 — grab the token

1. In Chrome, go to `chrome://extensions/` → enable Developer Mode.
2. Click **Load unpacked** → pick the `chrome-extension/` folder in this repo.
3. Open any `app.gohighlevel.com` page while logged in.
4. Click the extension icon → **Grab Refresh Token** → **Copy to Clipboard**.
5. Paste it into `~/.openclaw/secrets/.env` as `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=...`.

### Step 2 — build a workflow

`builders/` has example builders that turn a markdown email-sequence doc into a live workflow:

```bash
# Course Interest sequence (10 emails, 14 days)
python builders/wf1-course-interest-builder.py

# High Ticket Interest sequence (5 emails + 1 SMS)
python builders/wf5-ht-interest-builder.py

# Post-Call Sales (3 tag-triggered branch workflows)
python builders/wf6-post-call-sales-builder.py

# Consulti free-trial nurture (8 emails)
python builders/consulti-nurture-builder.py

# Post-purchase nurture (6 emails)
python builders/post-purchase-nurture-builder.py
```

Each builder supports `--update` to re-deploy without creating a duplicate workflow.

---

## Project layout

```
convert-and-flow-cli/
├── ghl                         # the executable wrapper (also: caf, convertandflow)
├── setup.py                    # package definition
├── install.sh                  # one-shot installer
├── .env.example                # template for your secrets
│
├── cli_anything/               # the actual Python package
│   └── gohighlevel/            # GHL commands
│       ├── gohighlevel_cli.py  # ~1,260 lines of CLI
│       ├── utils/              # API clients (public + internal + workflow builder)
│       └── skills/SKILL.md     # OpenClaw skill manifest
│
├── chrome-extension/           # Firebase token grabber (Convert and Flow Token Grabber)
│   ├── manifest.json
│   ├── popup.html
│   ├── popup.js
│   └── icon48.png
│
└── builders/                   # example workflow builders
    ├── wf1-course-interest-builder.py
    ├── wf5-ht-interest-builder.py
    ├── wf6-post-call-sales-builder.py
    ├── consulti-nurture-builder.py
    ├── post-purchase-nurture-builder.py
    ├── email-sequences-doc-builder.py
    └── _email_sequences_parser.py
```

---

## Using it with Claude Code

The repo includes a Claude Code skill so Claude can call the CLI on your behalf:

1. Copy `cli_anything/gohighlevel/skills/SKILL.md` into a Claude Code skills directory (e.g. `~/.claude/skills/gohighlevel-cli/SKILL.md`).
2. Add `ghl` to your shell's PATH (or symlink the `ghl` wrapper somewhere on PATH).
3. In any Claude Code session, say "use the gohighlevel-cli skill" and Claude will be able to run `ghl ...` for you.

---

## Two layers of GHL API

The CLI talks to two APIs:

| API | What it can do | How it authenticates |
|-----|----------------|----------------------|
| **Public** (`services.leadconnectorhq.com`) | Read everything, create contacts/opportunities/etc. **Workflows are GET-only here.** | `GHL_API_KEY` (Private Integration Token) |
| **Internal** (`backend.leadconnectorhq.com`) | Everything the GHL UI can do — including **creating workflows**. Hidden behind a `--experimental` flag on commands that use it. | Firebase JWT, refreshed from `GHL_FIREBASE_REFRESH_TOKEN` |

You only need the Firebase token if you want to **build** workflows. Everything else works with just the API key.

---

## Security notes

- `.env` is gitignored. **Never** commit it.
- The Firebase refresh token is sensitive (it's your full GHL session). Treat it like a password.
- The bundled Chrome extension only reads from IndexedDB on `*.convertandflow.com`, `*.gohighlevel.com`, and `*.leadconnectorhq.com` — no network calls, nothing stored, nothing transmitted.

---

## License

Private / personal use.
