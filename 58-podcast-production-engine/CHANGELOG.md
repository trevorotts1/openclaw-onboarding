# Changelog - 58 Podcast Production Engine (58-podcast-production-engine)

## [1.0.5] - 2026-09-17 - Step 12 DELIVERS the episode documents: Google Drive through the client's Skill 14 credentials, Notion when Workspace is not configured (ISSUE-15)

`scripts/render_documents.py` Step 12 emitted `drive.upload_convert` and `drive.set_permission` as ACTION INTENTS carrying a `cli_hint` of "gws drive files upload (LIVE-VERIFY ...)", and read no delivery configuration at all. Nothing anywhere performed the upload, so a fully provisioned client box still finished an episode with its documents sitting on local disk and delivery logged as not provisioned. Step 16 LINK BACK then had no Episode Package link or Speech Script link to write into Convert and Flow.

Step 12 now PERFORMS the delivery as a two-tier chain. `plan["delivery"]` is the chain summary (`channel`, `performed`, `status`, `documents`, `errors`, `log`) with each tier's own record under `plan["delivery"].tiers`. No tier can fail the episode or change the exit code, and `render --no-deliver` forces the intent-only path.

| Tier | Channel | When |
|---|---|---|
| 1 | Google Drive, the client's own Skill 14 credentials | Skill 14 configured on the box |
| 2 | Notion, the client's own workspace | Skill 14 absent, or the Drive call delivered nothing |
| 3 | Intent only | Neither configured. ONE log line names BOTH prerequisites |

### Tier 1: Google Drive

- Each rendered document is uploaded to Drive converted to a Google Doc, the anyone-with-the-link-can-edit permission the intent describes is applied, every executed intent is stamped `performed: true` with its `file_id` and `link`, and both links are recorded under `plan["links"].package_doc` and `plan["links"].speech_doc`, which is what Steps 16 and 17 read. The intents themselves are kept, not replaced.
- Credential resolution follows Skill 14 and invents no names. Service-account key: `GOOGLE_APPLICATION_CREDENTIALS`, else `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` (Skill 14 INSTALL.md Section 3 Option B), else Skill 14's documented default `~/clawd/secrets/gcp-service-account.json`. Impersonated Workspace user: `GCP_IMPERSONATE_USER`, else `GWS_ACCOUNT`. Both halves are required. The one new name is the optional destination folder `PODCAST_DRIVE_ROOT_FOLDER_ID`; unset, the documents land in the impersonated user's own Drive root.
- Only the full Drive scope is requested. Domain-wide delegation rejects drive.file and drive.readonly for this grant with `unauthorized_client`.
- An anyone-with-link grant inherited from a parent folder cannot be re-applied at file level; Drive answers 403 `cannotModifyInheritedPermission` and the document already carries the access, so that answer is recorded as inherited rather than treated as a failure.
- A permission that fails AFTER a successful upload is recorded as partial, not a fallback trigger: the documents are already in the client's Drive.

### The gws binary is never invoked

Delivery speaks the Drive REST API directly with the client's service account. It does not shell out to `gws`, not even to test for credentials. A bare `gws` call in a headless shell cannot unlock its keyring and gws's own failure mode then rewrites `~/.config/gws/credentials.enc` to `credential_source: "none"`, wiping every account on the box. Step 12 runs headless by definition. `scripts/tests/test_render_documents_drive_delivery.py` parses the module's syntax tree and fails if any call would execute a binary named gws, or if the bare string reaches anything but `shutil.which`.

### Tier 2: Notion

Google Drive delivery only helps a box that has Skill 14 installed. Nearly every client box already has Notion connected, so Notion is the fallback and a box without Google Workspace stops falling through to an intent-only record.

- The convention is the repo's existing one and invents none of it. Token `NOTION_API_TOKEN` (also accepted: `NOTION_API_KEY`, `NOTION_TOKEN`); parent page `NOTION_PODCAST_PARENT`, else `NOTION_PARENT_PAGE_ID`, else `NOTION_WORKSPACE_ROOT_ID`; API version `NOTION_API_VERSION` defaulting to `2022-06-28`. These are the names and the default that `37-zhc-closeout/scripts/ensure-notion-parent-page.sh` and `create-notion-closeout.sh` already use, and `38-conversational-ai-system/references/notion-client-doc-standard.md` is the doc contract.
- **Client ownership is binding**, exactly as Skill 37 enforces it: an EXPLICIT parent page is required because ownership is never inferred from a workspace-wide search, and the agency token (`ZHC_AGENCY_NOTION_TOKEN`) and agency parent (`ZHC_AGENCY_NOTION_PARENT_PAGE_ID`) are both refused. Page discovery uses the direct block-children listing, which is authoritative for direct children, so a search can never match a foreign page.
- One `Podcast Episodes` page under the client's parent, created once, then one page per episode beneath it keyed by the episode title. **Idempotent:** re-running Step 12 for the same episode clears that page's children and rewrites them; it never creates a second page.
- Blocks come from the same manifest the HTML renderer uses, through the new `render_package_markdown` and `markdown_to_notion_blocks` (headings, paragraphs, bulleted items, inline links), appended in chunks of 100, the API's children-per-request limit. Rich text is split into runs at 1900 characters so a long paragraph is carried whole rather than truncated.
- Each page opens with an episode properties block carrying title, date, style, mode, runtime, spoken words and guest. A page parented by a page cannot carry arbitrary Notion properties, so these are page BLOCKS, which is what the API allows.
- **No file upload.** The Notion API cannot upload a file, so the published audio URL from Step 15 is carried as a LINK. The rendered HTML and text files on disk remain the durable base.
- The page id and url land in `delivery.tiers.notion.documents.episode_page` and `plan["links"].episode_page`, the same way the Drive ids are recorded. When the plan's primary destination was already Notion, its `notion.create_page` intents are stamped `performed: true, channel: notion` with that page id and url.

### Fail soft, always

- Neither tier configured: the plan stays intent-only and exactly ONE line is logged naming both prerequisites, rather than one line per tier.
- An API error on either tier, an unreachable endpoint, or a missing signing tool: the failure is recorded on the plan under `delivery.errors` and the failing intent's `error`, and the episode carries on. Work that did succeed keeps its recorded ids.
- Credentials are reported by label and SET or NOT SET only. The key contents, the private key, the minted token, the Notion token, the parent page id and the impersonated address never reach the plan file, stdout or stderr.
- Step 12 still writes NO engine state. `podcast_state.py` remains the sole writer; the documents plan file on disk is Step 12's own record of what it delivered.

### Verification

- New `scripts/tests/test_render_documents_drive_delivery.py` (29 tests) and `scripts/tests/test_render_documents_notion_fallback.py` (28 tests), stdlib only and fully offline with each transport injected. Between them: credentials absent on both tiers gives intents only plus one combined skip line; Drive present gives both documents uploaded, converted, shared and stamped with ids; Drive absent with Notion present creates the episode page with its properties and blocks and records the url; Drive present means the Notion transport is never even constructed; an API error on either tier leaves the exit code at 0 with the error recorded and the local deliverables intact. Also covers idempotent re-runs, the 100-block chunking, the markdown converter, the root-folder env, `--no-deliver`, inherited permissions, error-text bounding, the credential-name contracts, the agency refusals, and that no secret reaches the plan or the logs.
- Skill 58 suite: 430 passing before, 487 after, no regressions.
- `render_documents.py detect` now prints a `tier 1 drive delivery:` line and a `tier 2 notion delivery:` line. New `58-podcast-production-engine/INSTALL.md` documents activation and both tiers; `modules/documents.md`, `SKILL.md` Step 12, SOP-PODCAST-02 section 2.10 and the repo README all carry the two-tier chain.

## [1.0.4] - 2026-09-17 - re-pin the webhook layer's schema verification to the installed OpenClaw 2026.9.4

The three files in `scripts/webhook/` that carry a LIVE-VERIFIED stamp still named OpenClaw 2026.6.11 while the fleet runs 2026.9.4. A stale stamp on a schema-drift note is worse than no stamp: it tells the next reader the contract was checked against a version that is no longer on any box. Re-verified against the installed package and re-pinned:

- `flow_client.py`: `createFlowRequestSchema` is unchanged at 2026.9.4, still a `strictObject` of `{action, controllerId?, goal(req), status?, notifyPolicy?, currentStep?, stateJson?, waitJson?}`. Its handler still only calls `taskFlow.tryCreateManaged`, and that function is a pure store insert. The route CREATES a queued flow and dispatches NOTHING; the string `autoAdvance` appears nowhere in the installed package. That is recorded in the header now, because it is the reason the gateway hook mapping exists at all.
- `route-template.json5` and `README.md`: route config schema unchanged, stamps moved to 2026.9.4.

Also hardened the template-syntax note in `register-podcast-hook.sh`. The claim that `{{payload}}` embeds the whole body is wrong and the failure it causes is silent, so the note now records the EXECUTED proof rather than a reading: importing the installed `dist/hooks-*.mjs` and calling its exported `applyHookMappings` with a flat survey body returns `BODY=` for `{{payload}}` and the full JSON object for `{{.}}`. `resolveTemplateExpr` does not special-case the bare word `payload`, so it falls through to `getByPath(ctx.payload, "payload")` and looks for a key literally named `payload` inside the body. Anyone "correcting" `{{.}}` to the more natural-looking `{{payload}}` ships a hook that wakes the agent with an empty payload block.

No behavior change: the shipped mapping already used `{{.}}`.

## [1.0.3] - 2026-09-17 - activation train: the engine now turns itself on, and the GHL contract points at a surface that answers

Four defects that together meant a fully provisioned box could accept an intake and never produce an episode.

### Activation never ran on any client box (ISSUE-01)
- `provision-podcast-client.sh` verified each activation helper by re-running it as `$helper --check <the same install args>`. Neither shipped helper has ever accepted `--check`; both reject an unknown flag with exit 2. Every provision therefore died at `activation:department` with exit 22 AFTER the department install had already succeeded, so the fleet guarantee (provision implies processor active) was never actually met.
- `activation_step` now takes install arguments and verify arguments separately, split by a `--` separator, and refuses to report a piece ACTIVE when no verify surface was declared. The department step runs `--client-slug <slug> --prime-session` and is verified with `install-podcast-department.sh --verify --client-slug <slug>`; the hook step is verified with the new `register-podcast-hook.sh --verify --client-slug <slug>`.
- `PODCAST_CLIENT_SLUG` is exported once at provision so the helpers' documented env fallback is real.
- New `scripts/tests/test_activation_step_contract.sh` drives the real `activation_step` against fake helpers that reject `--check` exactly as the shipped ones do. It fails 8 assertions against the pre-fix code.

### Nothing on a client box ever ACTIVATED the engine (ISSUE-01)
- `install.sh` only copied the activation files; `update-skills.sh` had no podcast branch at all, and its per-skill wiring loop runs `wire.sh` / `install.sh` / `scripts/install.sh` / `setup-*.sh`, none of which this skill shipped. New `wire.sh` is that entry point: it resolves the client slug (env, else the slug already recorded in the box's registered intake route, else `PODCAST_INTAKE_ROUTE_ID`) and the intake secret, runs the department installer, the hook registrar and `guard-activation-health.py`, refuses to run as root, and never restarts the gateway. With no podcast client on the box it prints a loud WARN naming SOP-PODCAST-07 and exits 0. `install.sh` gained a matching guarded call.

### The queued flow had no trigger, and the shipped GHL contract could not reach one (ISSUE-02, ISSUE-03)
- `register-podcast-hook.sh` now also writes a GATEWAY HOOK MAPPING: `hooks.mappings[]` id `podcast-intake-<slug>`, `match.path` `podcast-intake-<slug>`, `action: agent`, `agentId` the podcast agent, `sessionKey podcast:intake:<slug>`, `sessionMode: persistent`, `wakeMode: now`, `deliver: false`, `allowUnsafeExternalContent: false`, plus a deterministic `messageTemplate` that runs the intake handler in `trigger-flow` mode and then the step driver. That mapping is what converts an inbound survey POST into a podcast agent turn; the plugin route never did, because it accepts only the `{"action":"create_flow"}` envelope.
- The whole request body reaches the template as `{{.}}`, verified against the installed platform's resolver. `{{payload}}` renders empty; there is no whole-body alias.
- The registrar enables the hooks ingress, and when the box has no `hooks.token` it points it at the SAME env label as the route SecretRef (`${PODCAST_INTAKE_HOOK_SECRET}`), so onboarding manages one secret for both surfaces. An existing token owned by another integration is never overwritten. It adds the `hook:` session-key prefix when `hooks.defaultSessionKey` is unset, which the installed gateway requires or it refuses to start. The mapping is prepended so a pre-existing catch-all mapping cannot shadow it, and it fails closed when `hooks.enabled` is explicitly false or the secret label is unset.
- The GHL snapshot contract now matches: custom value 4 is `https://SET-AT-PROVISIONING/hooks/podcast-intake-<client-slug>` and custom value 5 travels as the `Authorization: Bearer` HEADER. The gateway reads the token from `Authorization: Bearer` or `x-openclaw-token` and nowhere else, so the old "header if supported, else payload field" fallback does not work for this endpoint and is documented as such. SOP-PODCAST-02 sections 2.2 and 2.8, `webhook-design.md` sections 1, 7 and 8, `scripts/webhook/README.md`, `route-template.json5` and the SKILL.md trigger contradiction were all corrected to the same contract.
- New assertions in `scripts/tests/test_register_podcast_hook.sh` cover the mapping fields, the template, the token custody rules, `--verify`, and symmetric removal.

### Dead scheduler slice pruned (ISSUE-03)
- Deleted `SCHEDULER.md`, `scripts/podcast_scheduler_runner.sh`, `scripts/install-podcast-scheduler.sh`, `config/launchd/com.openclaw.podcast-scheduler.plist.template`, the repo `config/cron.d/podcast-scheduler` entry and `tests/unit/podcast-scheduler.test.sh`. They polled for a `podcast_controller.py` that exists nowhere in this engine.
- `guard-cron-inventory.py` no longer RECOGNIZES a `podcast-scheduler` cron as a lawful box tick. It contradicted `guard-activation-health.py`, which has always failed a cron naming either dead daemon. A cron naming `podcast-scheduler` or `podcast-controller` is now reported as `AF-PPE-POLLER` and counts against the per-client census.
- `revoke-podcast-client.sh` no longer calls a scheduler installer that does not ship; step 9d scans for dead-daemon cron residue instead.

### Podcast SOPs reach the Command Center library (ISSUE-12)
- `32-command-center-setup/scripts/ingest-sop-library.py --craft-clusters` ingests `universal-sops/<cluster>/SOP-*.md` into the SOP library, mapping `podcast-craft` to department `podcast`. Idempotent by slug, no download, no embedding call, no cost. Carried by `update-skills.sh` step U6c1b, which runs unconditionally, so an already-populated box gets the rows too. `ingest-sop-library.sh` is deliberately NOT touched: its already-populated skip gate is contractually a no-write path and `tests/unit/sop-library-update-path-ingest.test.sh` asserts the database is left byte-identical there.

### Also
- `scripts/provision-podcast-client.sh` gained the bash 3.2 re-exec guard.

## [1.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
