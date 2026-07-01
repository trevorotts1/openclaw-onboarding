---
name: "convert-and-flow-operator"
description: "Convert and Flow CLI — contacts, opportunities, calendars, workflows, conversations, emails, payments, forms, social media, and locations on any GHL sub-account"
triggers:
  - convert and flow
  - caf
  - convertandflow
  - ghl cli
  - ghl contacts
  - ghl workflows
  - ghl calendars
---

# convert-and-flow-operator

Command-line interface for the GoHighLevel CRM and Marketing API. Manage contacts, pipeline opportunities, calendars, workflows, conversations, emails, payments, forms, social media posts, and locations from the command line or interactive REPL.

## Prerequisites

- Python 3.10+
- `GOHIGHLEVEL_API_KEY` — your GHL Private Integration Token
- `GOHIGHLEVEL_LOCATION_ID` — your GHL location/sub-account ID (required, no default)
- `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` — comma-separated whitelist of approved location IDs (required for writes)
- Installed at `~/.openclaw/tools/convert-and-flow-cli/.venv`

## Installation

```bash
bash install.sh
```

## Usage

### CLI Mode (one-shot commands)
```bash
caf --json contacts list
caf contacts get <contact_id>
caf contacts create --email user@example.com --first-name John --last-name Doe
caf opportunities list --status open
caf calendars list
caf workflows list
caf conversations list --status unread
caf payments transactions
caf forms list
caf social posts
caf locations get
```

### REPL Mode (interactive)
```bash
caf
# or
convertandflow
```

### Global Options
- `--json` — Output as machine-readable JSON (recommended for agents)
- `--location-id <ID>` — Override GOHIGHLEVEL_LOCATION_ID for this command
- `--dry-run` — Print every write's method+URL+payload; no data is sent to GHL
- `--experimental` — Enable workflow creation commands (internal GHL API + Firebase token required)
- `--version` — Show CLI version
- `--help` — Show help

## Safety Controls

All writes are gated by `cli_anything/gohighlevel/utils/safety_gate.py`:

| Control | Env var | Default | Effect |
|---------|---------|---------|--------|
| Location whitelist | `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` | empty (refuses all writes) | Hard-fails any write targeting a non-approved sub-account |
| Draft-only | `GOHIGHLEVEL_DRAFT_ONLY` | `true` | Workflow triggers created with `active: false` |
| Global dry-run | `--dry-run` flag or `CAF_DRY_RUN=true` | off | Prints payload, never sends |
| Approval gate | `CAF_APPROVAL_TOKEN` or ZHC- prefix | required | Refuses internal-API writes without explicit approval |

## Command Groups

| Group | Description | Key Commands |
|-------|-------------|--------------|
| `contacts` | Contact management | list, get, create, update, delete, search, add-tag, remove-tag |
| `opportunities` | Pipeline deals | list, get, create, update, delete, pipelines |
| `calendars` | Scheduling | list, get, slots, appointments, book, groups |
| `workflows` | Automation workflows | list, enroll, remove, create (--experimental), create-step (--experimental), create-n8n (--experimental) |
| `conversations` | Messaging (SMS, email, chat) | list, get, messages, send |
| `emails` | Email campaigns/templates | list-campaigns |
| `payments` | Financial operations | transactions, orders, invoices, create-invoice |
| `forms` | Form management | list, submissions |
| `social` | Social media posting | accounts, posts, create-post |
| `locations` | Sub-account management | get, search, tags, custom-fields, custom-values |

## Agent Usage Notes

- Always use `--json` flag for programmatic consumption
- Contact search uses `contacts search <query>` for name-based search
- Workflow creation requires `--experimental` plus a Firebase refresh token
- Workflow creation requires `CAF_APPROVAL_TOKEN` or a ZHC-prefixed workflow name
- Social media posting requires OAuth-connected accounts
- All public endpoints require valid `GOHIGHLEVEL_API_KEY` bearer token
- Public API base URL: `https://services.leadconnectorhq.com`
- Internal API base URL: `https://backend.leadconnectorhq.com`
- API version header: `2021-07-28`

## Examples

```bash
# List contacts as JSON
caf --json contacts list --limit 50

# Dry-run a contact create (prints payload, sends nothing)
caf --dry-run contacts create --email lead@company.com --first-name Jane

# Create a contact with tags (requires approved location + approval token)
caf contacts create --email lead@company.com --first-name Jane --last-name Smith --tag "hot-lead"

# Search contacts
caf contacts search "john"

# List pipeline opportunities
caf --json opportunities list --status open

# Get available calendar slots
caf calendars slots <calendar_id> --start 2026-03-25 --end 2026-03-30

# Create a workflow from JSON (ZHC-prefixed name = standing approval)
caf --experimental workflows create --name "ZHC-Onboarding" --from-json campaign.json

# Send SMS in conversation
caf conversations send <conversation_id> --type SMS --message "Thanks for your interest!"
```
