# INSTALL - 58 Podcast Production Engine

How this skill is turned on for one client box, and what each optional integration
needs. The canonical onboarding runbook is
`universal-sops/podcast-craft/SOP-PODCAST-02-CLIENT-ONBOARDING.md`; this file is the
per-box configuration reference that runbook points at.

No step here restarts the OpenClaw gateway, and no step writes a client credential.
Credentials are supplied per box and reported by label only, never by value.

---

## 1. Activation

`wire.sh` is the entry point the fleet updater runs. It resolves the client slug,
installs the podcast department, registers the intake hook, and runs the activation
health guard. It refuses to run as root and never restarts the gateway.

    bash 58-podcast-production-engine/wire.sh

With no podcast client on the box it prints a WARN naming SOP-PODCAST-07 and exits 0.

Per-client provisioning (Convert and Flow, Cloudflare, the intake route) is
`scripts/provision-podcast-client.sh`; revocation is `scripts/revoke-podcast-client.sh`.
Verify activation at any time with:

    python3 58-podcast-production-engine/scripts/guard-activation-health.py

---

## 2. Document delivery (Step 12): Google Drive, then Notion

Step 12 renders the Episode Package and the Speech Script to disk, then delivers
them through a two-tier chain. Whichever tier delivers records its ids and links in
the documents plan, and Step 16 LINK BACK writes those links into Convert and Flow.

Report what this box can do right now:

    python3 58-podcast-production-engine/scripts/render_documents.py detect

That prints a `tier 1 drive delivery:` line and a `tier 2 notion delivery:` line,
each SET or NOT SET by label. It never prints a value.

### Tier 1: Google Drive

Prerequisite: Skill 14 (`14-google-workspace-integration`) installed on this box
with the CLIENT's own service account. Both halves of the Skill 14 service-account
path are required.

| Setting | Env | Notes |
|---|---|---|
| Service-account key | `GOOGLE_APPLICATION_CREDENTIALS` or `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` | Falls back to Skill 14's default location `~/clawd/secrets/gcp-service-account.json`. |
| Impersonated user | `GCP_IMPERSONATE_USER` or `GWS_ACCOUNT` | The Workspace user the service account acts as through domain-wide delegation. |
| Destination folder | `PODCAST_DRIVE_ROOT_FOLDER_ID` | OPTIONAL. Unset, the documents land in the impersonated user's own Drive root. |

Each document is uploaded as a Google Doc and shared anyone-with-the-link-can-edit.
Only the FULL Drive scope works for this grant; domain-wide delegation rejects
`drive.file` and `drive.readonly` with `unauthorized_client`.

Step 12 speaks the Drive REST API directly and NEVER invokes the `gws` binary, not
even to test for credentials. A bare `gws` call in a headless shell cannot unlock
its keyring, and gws then rewrites its own credential store to
`credential_source: "none"`, wiping every account on the box.

### Tier 2: Notion

Tried when Skill 14 is not configured on this box or the Drive call delivered
nothing. Nearly every client box already has Notion connected. The contract is the
one `37-zhc-closeout` already uses.

| Setting | Env | Notes |
|---|---|---|
| Integration token | `NOTION_API_TOKEN` (also accepted: `NOTION_API_KEY`, `NOTION_TOKEN`) | The CLIENT's own token. The agency token named by `ZHC_AGENCY_NOTION_TOKEN` is refused. |
| Parent page | `NOTION_PODCAST_PARENT`, else `NOTION_PARENT_PAGE_ID`, else `NOTION_WORKSPACE_ROOT_ID` | Must be explicit. Ownership is never inferred from a workspace-wide search, and the agency parent named by `ZHC_AGENCY_NOTION_PARENT_PAGE_ID` is refused. |
| API version | `NOTION_API_VERSION` | OPTIONAL. Defaults to `2022-06-28`. |

Share the client's Notion integration with that parent page before the first run.
Step 12 then creates one `Podcast Episodes` page under it, once, and one page per
episode beneath that. Re-running Step 12 for the same episode REPLACES that page's
content; it never creates a duplicate.

Each episode page carries an episode properties block (title, date, style, mode,
runtime) followed by the rendered content as Notion blocks. The Notion API cannot
upload a file, so the published audio from Step 15 is LINKED, never uploaded.

### Tier 3: neither configured

Step 12 keeps the intent-only record and logs ONE line naming both prerequisites.
The episode still completes and the rendered files on disk are the deliverables.

An API error on either tier is recorded on the documents plan and never fails the
episode. `render --no-deliver` forces the intent-only path.

---

## 3. What this skill never does

- Never uses an operator, agency, or another client's credential. Every integration
  above is the named client's own.
- Never calls an Anthropic model, provider, key, or host at runtime.
  `scripts/guard-no-anthropic-runtime.py` fails the build on any Anthropic reference.
- Never messages the client. The engine enrolls the workflow and stops; Convert and
  Flow owns every customer message.
- Never restarts the gateway, and never writes engine state outside
  `scripts/podcast_state.py`, which is the sole writer.
