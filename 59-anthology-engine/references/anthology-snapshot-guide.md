<!-- OPERATOR HEADER -->
<!-- Skill 59 reference doc - the ANTHOLOGY CONVERT AND FLOW INSTALL SNAPSHOT. -->
<!-- Full content lives here (not in SKILL.md/INSTRUCTIONS.md - those get a 1-2 line pointer only). -->
<!-- A snapshot NEVER contains a real token. The platform is Convert and Flow (a LeadConnector v2 -->
<!-- white-label); nothing Anthropic appears in this file. Added 2026-07-10. -->

# Anthology Engine — Convert and Flow Install Snapshot

The Anthology Engine (Skill 59) ships a Convert and Flow (GoHighLevel / LeadConnector
v2) snapshot so per-client onboarding is a ONE-IMPORT step instead of a hand-build. The
snapshot pre-creates everything the engine needs that the setup API cannot create on its
own — most importantly the **pipeline** (pipelines are UI-only; there is no API to create
one) and the **tag-triggered notification automation** — plus the 28 contact custom
fields, the release tags, the forms, and the four REPLACE-ME location custom values the
provisioner fills per client.

This is an OPERATOR-ONLY surface. A participant naming a snapshot, a pipeline, a tag, or a
custom value does NOTHING. The snapshot is built once by the operator in the operator's OWN
template location and imported per install into the client's OWN location.

The authoritative machine contract for WHAT the snapshot must contain is
`config/anthology-snapshot-contract.json`. It is pinned against the engine's single source
of truth (`config/field-map.json` + `config/engine-config.template.json`) by
`scripts/qc-snapshot-contract.sh`, so a snapshot that drifts from the engine fails CI before
it can ship.

---

## 1. What the snapshot contains

1. **The standard pipeline `Anthology Engine`** with its **nine exact stages, in order**:
   Intake, Avatar, Tone, Title, Outline, Chapter, Cover, Delivered, Assembled. Both the
   pipeline name and every stage name are load-bearing: onboarding
   (`provision-anthology-client.sh` step 3) FINDS the pipeline BY NAME and BINDS it through
   the client's OWN private-integration token, and the runtime resolves stage moves BY
   STAGE NAME. GoHighLevel exposes no API to create a pipeline, so the snapshot is the ONLY
   scalable way to put it in the client account.
2. **The 28 contact custom fields** (model = contact), byte-identical to
   `field-map.json → provisioning.fields`: 27 `LARGE_TEXT` free-text keys plus exactly one
   `SINGLE_OPTIONS` field (the U8 cover choice, whose picklist options are the four cover
   styles `Signature`, `Bold Editorial`, `Fine Art`, `Pure Type`, in that order). Field NAMES
   must equal the `create_name` values exactly, because the API DERIVES `fieldKey =
   contact.<name>`. The provisioner's step 2 is create-or-verify + idempotent, so a snapshot
   that already carries all 28 fields makes step 2 a verify-only no-op.
3. **The four REPLACE-ME location custom values** the tag-notification automation reads:
   `anthology_webhook_url`, `anthology_hook_secret`, `producer`, `producer_email`. The
   engine's own Python reads ZERO location custom values — these belong to the snapshot's
   notification automation, exactly as Skill 38's snapshot carries `openclaw_hook_url` /
   `openclaw_hooks_bearer`. They ship as clearly-labeled placeholders, never real values.
4. **The eight release tags** (`anthology-release-avatar` / `-tone` / `-outline` /
   `-chapter` / `-rewrite` / `-cover` / `-final`, and `anthology-delivered`). Tags do not
   have to be pre-declared for the engine to work (GoHighLevel creates a tag on first
   add-tags call), but seeding them keeps the account clean and lets the notification
   automation pre-bind its triggers.
5. **The tag-triggered notification automation**, shipped DISABLED. When a release tag lands
   on a contact it greets the producer/participant and (optionally) calls the box's intake
   hook. Its trigger is contact-tag-added on the three LIVE slugs (avatar / tone / outline)
   first, with the three wired-ahead slugs added when those gates ship. Its ordered actions
   are: a Custom Webhook POST (URL = the `anthology_webhook_url` custom value, Authorization
   header = the `anthology_hook_secret` custom value), a producer-branded email, and an
   optional SMS. This automation is the single biggest thing the snapshot adds beyond
   field/pipeline parity — the engine EMITS the release tags, but nothing in the repo turns
   a tag into the client-facing email + SMS (workflow JSON exports are banned from the repo
   by `scan-no-json-exports.sh`).
6. **The forms** as a hidden-field contract: one REQUIRED universal author-intake form plus
   three per-stage gate forms (title-subtitle-selection, outline-approval,
   chapter-approve-or-rewrite). Every form carries the universal hidden fields `contact_id`,
   `anthology_id`, `stage`, re-stamped on gate re-entry. Concrete form ids are bound per
   anthology at book creation, not at snapshot time.

### The NEVER-A-REAL-TOKEN rule

A snapshot NEVER contains a real token or a real hook URL. Inside the exported snapshot the
webhook URL and the Authorization header value are left as clearly-labeled REPLACE-ME
location custom values:

- `{{ custom_values.anthology_webhook_url }}` — REPLACE-ME with
  `https://<PUBLIC_HOSTNAME>/hooks/anthology-intake` (the client's real intake hook URL).
- `{{ custom_values.anthology_hook_secret }}` — REPLACE-ME with `Bearer <HOOKS_TOKEN>`,
  resolved BY LABEL from `ANTHOLOGY_INTAKE_HOOK_SECRET`.

These are placeholders in the exported snapshot, never real values. They are filled per
install by `scripts/anthology_snapshot.py provision-custom-values`, which resolves the hook
secret BY LABEL and NEVER prints its value (SET / NOT SET only).

---

## 2. How the operator BUILDS the snapshot (once)

The snapshot is built ONCE in the operator's OWN Anthology template Convert and Flow
location `2HIKGNgsixWx0yds7Qnx`, never in a client account:

1. Create the pipeline named exactly `Anthology Engine` with the nine stages above, in
   order (Intake → Avatar → Tone → Title → Outline → Chapter → Cover → Delivered →
   Assembled).
2. Create the 28 contact custom fields. Use `bash scripts/anthology_snapshot.py plan` to
   print the exact field list, and `field-map.json → provisioning.fields` for the
   authoritative `create_name` + `data_type` of each. Create the cover choice as
   SINGLE_OPTIONS with the four style options in order.
3. Create the four location custom values as REPLACE-ME placeholders (Settings → Custom
   Values): `anthology_webhook_url`, `anthology_hook_secret`, `producer`, `producer_email`.
   Do not put real values here — the placeholders are what ships.
4. Seed the eight release tags.
5. Build the tag-triggered notification automation (contact-tag-added on the LIVE slugs →
   Custom Webhook using the two REPLACE-ME custom values → producer email → optional SMS).
   Ship it DISABLED. Set the Custom Webhook Content-Type to `application/json`.
6. Create the universal author-intake form and the three per-stage gate forms with the
   hidden fields `contact_id`, `anthology_id`, `stage`.

## 3. How the operator EXPORTS and VERSIONS the snapshot

1. Export the snapshot from the template location (Settings → Snapshots → Create Snapshot).
2. Version it with the date-stamped name recorded in the contract's `snapshot_version`
   (currently `anthology-engine-snapshot-20260710`). Bump both the exported name and the
   contract's `snapshot_version` whenever the pipeline / fields / tags / forms / automation
   change and the snapshot is re-cut.
3. Keep the exported snapshot link where the install agent can reference it per install.

Whenever the field-map or the pipeline changes, rebuild + re-export the snapshot. The repo
fixture `config/anthology-snapshot-contract.json` is machine-checked by
`scripts/qc-snapshot-contract.sh`, so snapshot drift from the engine fails CI before it can
ship.

---

## 4. Per-install: IMPORT (operator, manual) then fill + verify (scripted)

There is NO agency → subaccount auto-push (see Section 6). The import is a MANUAL, operator-
run step, then the provisioner finishes the per-client tail.

1. **Import the snapshot** into the client's OWN Convert and Flow location (Settings →
   Snapshots → Import / Load Snapshot). This is done ONCE per client, by the operator, in
   the client's own account.
2. **Run `provision-anthology-client.sh`.** Step 3 finds + binds the imported pipeline; step
   2 verifies (or backfills) the 28 fields; **step 7.5** (`anthology_snapshot.py`) then:
   - **verifies** the import landed — the `Anthology Engine` pipeline exists by name with all
     nine stages, and all 28 custom fields exist by key (a missing pipeline STOPs with
     `AF-AE-SNAPSHOT-PIPELINE-MISSING`, telling the operator to import the snapshot);
   - **fills** the four REPLACE-ME custom values, idempotently (GET-check then create-only-
     missing / update-in-place): `anthology_webhook_url` from `--public-hostname` + the
     intake route path, `anthology_hook_secret` resolved BY LABEL and never printed,
     `producer` from `--producer`, `producer_email` from `--producer-email`;
   - **stamps** the snapshot-version marker `$STATE_DIR/snapshot-version.json` so the box
     records which snapshot it was provisioned from.
3. **Enable** only the notification automation the client needs (the three LIVE slug triggers
   first; the wired-ahead slugs when those gates ship).

If the hook secret is not yet exported into the client env store when step 7.5 runs, the
Authorization-header custom value is left as its placeholder with a note (HELD under
`--require-live`); export `ANTHOLOGY_INTAKE_HOOK_SECRET` and re-run to fill it.

---

## 5. Enforcement

- `config/anthology-snapshot-contract.json` — the machine-checked fixture pinning the
  pipeline + stages, the 28 fields + types + options, the tags, the custom values, the
  forms, and the notification-automation contract.
- `scripts/qc-snapshot-contract.sh` — the CI DRIFT GATE. It cross-checks the fixture against
  `field-map.json` (pipeline name/stages, field keys/create-names/types, cover options) and
  `engine-config.template.json` (intake route path + credential labels). Any drift FAILS
  (exit 1); a missing file is BLIND (exit 2). Mirrors Skill 38's `qc-23-key-bodies.sh`.
- `scripts/anthology_snapshot.py` — the per-install verify + custom-value fill + version
  stamp mechanism (subcommands `verify-imported`, `provision-custom-values`,
  `stamp-version`, `plan`, `self-test`).
- `provision-anthology-client.sh` step 7.5 — wires all of the above into onboarding.
- The never-a-real-token rule: the webhook URL + Authorization header are REPLACE-ME custom
  values in the exported snapshot, filled per install (the hook secret BY LABEL, never
  printed).

---

## 6. REJECTED mechanism: agency → subaccount API auto-push

An agency-level `push_snapshot_to_subaccounts` API call (auto-loading the snapshot into
child locations from a parent agency) was considered and **REJECTED — not built**. This
fleet's topology is EACH-CLIENT-OWNS-THEIR-OWN-GHL: a client's Convert and Flow location is
owned by the client under their own agency, not a subaccount of a BlackCEO agency. A
snapshot PUSH/LOAD across agency boundaries into a location the operator does not own under
their agency is almost certainly impossible (it would require agency-level ownership the
operator does not have over a client-owned location). The only realistic path is the MANUAL
IMPORT of the exported snapshot into the client's own location (operator-run, Settings →
Snapshots → Import), followed by the per-client fill + verify built here. The rejection is
recorded as a standing guard in the contract's `rejected_mechanisms`, and
`qc-snapshot-contract.sh` fails if it is ever quietly removed. If a future fleet topology
nests client locations under a BlackCEO agency, revisit.

---

## 7. What still requires a working Convert and Flow token before it can RUN live

The MECHANISM + guardrails above are built and offline-tested (self-tests, the drift gate,
and dry-run all pass without a network). The following require a working (unexpired) Convert
and Flow private-integration token, and so are DEFERRED until the token is restored:

- **Cutting the live snapshot** from template location `2HIKGNgsixWx0yds7Qnx` (Sections 2–3).
- **The live per-client import** into a client's own location (Section 4, step 1).
- **`anthology_snapshot.py verify-imported`** against a live location (reading the pipeline
  and custom fields back).
- **`anthology_snapshot.py provision-custom-values`** writing the four custom values live
  (needs the client PIT with customValues WRITE scope + the exported `ANTHOLOGY_INTAKE_HOOK_SECRET`).
- **The canary** — running `provision-anthology-client.sh` end-to-end on the operator's own
  box against a real imported snapshot, and confirming a release tag fires the notification
  automation.
