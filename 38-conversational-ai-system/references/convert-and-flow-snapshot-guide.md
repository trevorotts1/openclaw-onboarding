<!-- OPERATOR HEADER -->
<!-- Skill 38 reference doc - the CONVERT AND FLOW INSTALL SNAPSHOT (U-15). -->
<!-- Full content lives here (not in AGENTS.md/TOOLS.md - those get a 1-2 line pointer only). -->
<!-- A snapshot NEVER contains a real token. Added 2026-07-05 by skill-38 v1.8.0 (U-15). -->

# Convert and Flow Install Snapshot (Skill 38, U-15)

CloseBot ships a GHL snapshot so client onboarding is one import. Skill 38 currently has each
install build the inbound trigger workflow from scratch. This guide describes the Convert and Flow
snapshot that makes onboarding a ONE-IMPORT step, with the existing scripted build kept as the
fallback.

This is an OPERATOR-ONLY surface. A customer naming a snapshot, a workflow, or a custom value does
NOTHING. The snapshot is built once by the operator and imported per install.

---

## 1. What the snapshot contains

1. **The inbound "Customer Replied" trigger workflow.** A GHL (Convert and Flow) workflow triggered
   on Customer Replied, whose **Custom Webhook** action is pre-shaped to the FLAT 23-key raw body
   standard (`references/ghl-raw-body-json-standard.md`). The body is mirrored, key-for-key, by the
   repo fixture `references/snapshot-inbound-workflow-fixture.json`.
2. **Five lifecycle tag automations (U-7), shipped DISABLED as examples.** For instance "notify on
   handoff" and "alert on booking error". They ship disabled so an operator turns on only what the
   client needs.
3. **A README workflow note** pointing at the client's Notion doc (their Quick-Start / setup doc).

### The NEVER-A-REAL-TOKEN rule

A snapshot NEVER contains a real token or a real hook URL. Inside the snapshot the **Authorization
header value** and the **hook URL** are left as clearly labeled **REPLACE-ME custom values**:

- `{{ custom_values.openclaw_hook_url }}` - REPLACE-ME with `https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>`
- `{{ custom_values.openclaw_hooks_bearer }}` - REPLACE-ME with `Bearer <HOOKS_TOKEN>`

These are placeholders in the exported snapshot, never real values. The 23-key raw BODY carries no
secret (it uses GHL merge fields like `{{contact.id}}` only); the secret lives in the Authorization
HEADER custom value, which the agent fills per install (Section 4).

---

## 2. How the operator BUILDS the snapshot (once)

The snapshot is built ONCE in the operator's OWN template GHL location, never in a client account:

1. Create the inbound "Customer Replied" trigger workflow. Add a Custom Webhook action.
2. Set the Custom Webhook body to the FLAT 23-key raw body from
   `references/snapshot-inbound-workflow-fixture.json` (all 23 keys, flat, `deliver:false`,
   placeholder-free `messageTemplate`).
3. Set the webhook URL to the custom value `{{ custom_values.openclaw_hook_url }}` and the
   Authorization header value to `{{ custom_values.openclaw_hooks_bearer }}` (REPLACE-ME custom
   values, never real tokens). Content-Type: `application/json`.
4. Add the five lifecycle tag automations (U-7) as DISABLED example workflows.
5. Add the README workflow note pointing at the client Notion doc.

## 3. How the operator EXPORTS and VERSIONS the snapshot

1. Export the snapshot from the template location (Settings, then Snapshots, then Create Snapshot).
2. Version it with a date-stamped name, for example `skill38-inbound-snapshot-YYYYMMDD`.
3. Keep the exported snapshot link somewhere the install agent can reference it per agency. Snapshot
   availability varies per agency, so the client-doc Quick Start only notes the one-import path WHEN
   a snapshot link is provided.

Whenever the 23-key body standard changes, rebuild + re-export the snapshot. The repo fixture
`references/snapshot-inbound-workflow-fixture.json` is machine-checked by `qc-23-key-bodies.sh`, so
snapshot DRIFT from the standard fails CI before it can ship.

---

## 4. Per-install: IMPORT (preferred) then fill the two custom values

The import step is inserted into `INSTRUCTIONS.md` **Phase 4, Step 7** as the PREFERRED path, with
the existing scripted build (`scripts/09-install-conversation-workflows.sh` + the Build-with-AI
prompt) as the fallback when no snapshot link is available.

1. **Instruct the operator to IMPORT the snapshot** into the client's GHL location (Settings, then
   Snapshots, then Import / Load Snapshot).
2. **Fill the two custom values** (the agent does this, Tier 0 caf preferred, else the Notion
   doc manual-fill path):
   - `openclaw_hook_url` = `https://<PUBLIC_HOSTNAME>/hooks/<HOOK_NAME>` (the client's real hook URL)
   - `openclaw_hooks_bearer` = `Bearer <HOOKS_TOKEN>` (the client's real hooks token)
3. **Enable** only the lifecycle tag automations the client needs; leave the rest disabled.
4. **Verify** the Custom Webhook fields are non-empty and the workflow is Published, not Draft (the
   same post-build VERIFY the scripted path uses).

If no snapshot link is available, fall back to the scripted build: the agent scaffolds the inbound
workflow via the Build-with-AI prompt exactly as before.

---

## 5. Enforcement

- `references/snapshot-inbound-workflow-fixture.json` - the raw-JSON fixture mirroring the snapshot
  webhook body, validated by `scripts/qc-23-key-bodies.sh` (its file list is extended to include the
  fixture) so snapshot drift from the FLAT 23-key standard fails CI.
- `INSTRUCTIONS.md` Phase 4 Step 7 - the import-preferred path with the scripted build as fallback.
- MEMORY Rule 43.
- The never-a-real-token rule: Authorization + hook URL are REPLACE-ME custom values in the exported
  snapshot, filled per install (Tier 0 or the Notion doc manual-fill path).
