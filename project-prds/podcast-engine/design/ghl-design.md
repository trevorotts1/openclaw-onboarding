# Podcast Production Engine: GoHighLevel / Convert and Flow Integration Design

**Version:** 1.0 (design spec, pre-build)
**Scope:** The complete GoHighLevel data plane for the Podcast Production Engine skill: credential resolution, custom-field read/write, media-library operations, workflow enrollment, rate-limit budgeting, and the credential-check guardrail script.
**Sources:** `PODCAST_EPISODE_GENERATION_SYSTEM.md` (custom_field_map, publishing_pipeline, step_a through step_d, mandatory_credentials, initial_setup_requirements) and `CLAUDE_CODE_BUILD_BRIEF.md` (preserve_these_rules, repo_and_versioning guardrail-script requirement).

**Naming rule (binding):** In every client-visible string, log line a client can see, dashboard label, delivery report, and error message surfaced to a client, the system is called **"Convert and Flow"**, never "GoHighLevel" and never "GHL". Internal code, comments, and operator logs may use GHL. Convert and Flow, GoHighLevel, and GHL are one system; the abbreviation GHL is used below for brevity in this internal document only.

---

## 1. Access-Tier Doctrine: Why This Engine Uses Tier 0 + Tier 3 Only

The canonical GHL access model (Skill 36) is a six-tier escalation chain. This engine **fans out to sub-agents** (up to 50 simultaneous builders, and at runtime the pipeline stages run as delegated sub-agents per fleet doctrine). That single fact decides the architecture:

| Tier | Path | Sub-agent safe? | Engine usage |
|---|---|---|---|
| **0** | Skill 44 `caf` command-line interface (aliases: `caf`, `convertandflow`, `ghl`) | **YES** | **PRIMARY data plane.** Contact reads, custom-field writes, workflow enrollment. Only path that can BUILD workflows (requires the separate Firebase refresh token; build is a setup-time operator task, never runtime). |
| 1 | Official GHL Model Context Protocol server (36 tools) | NO (injects only into the orchestrator session) | **FORBIDDEN in this engine.** |
| 2 | Community Model Context Protocol server (588/834 tools, on-demand curl) | NO (orchestrator-only) | **FORBIDDEN in this engine.** |
| **3** | Direct REST (Skill 29, 413 endpoints, raw HTTPS) | **YES** | **MANDATORY for media uploads** (`POST /medias/upload-file`; no other tier performs binary multipart uploads). Also the sub-agent-safe fallback for every Tier 0 operation. |
| 4 | agent-browser | last resort | Setup-time only (for example, one-time folder creation if a REST folder endpoint is unavailable), never in the per-episode runtime path. |

**Hard rule for the skill:** every GHL touch in the per-episode pipeline goes through Tier 0 `caf` first, Tier 3 REST second. The two Model Context Protocol tiers are structurally unusable here because a sub-agent performing Step 14 (store media) or Step 16 (field write-back) would silently have no tools, and "silently no tools" is exactly the class of false-done failure the quality-control protocol exists to kill. The guardrail script (Section 7) and the skill's runbook text must both state this so no future edit "helpfully" reintroduces a Model Context Protocol call inside a fan-out.

**Escalation within the engine:** Tier 0 fails (binary missing, auth error, command unsupported) -> Tier 3 REST with the same PIT. Tier 3 fails with a non-429 error -> retry per Section 6, then queue + alert per publishing_failure_handling. **Never** escalate to Tiers 1/2/4 at runtime. A 429 never escalates anywhere (Section 6): all tiers share one per-location rate bucket, so tier-hopping on 429 is self-harm.

---

## 2. Per-Client Credential Resolution (PIT + Location ID)

### 2.1 What the credential is

One value, many names: the **Location Private Integration Token (PIT)**, prefix `pit-`. It is identically the "GHL API key", "GoHighLevel API key", "Convert and Flow API key", and "private integration token". The system must never conclude a credential is missing merely because it is labeled differently (mandatory_credentials rule). Two credentials that are **NOT** this credential and must never be merged into its resolver:

- **Agency PIT** (agency-scoped token): separate credential, separate purpose, never substituted for a Location PIT.
- **Firebase refresh token** (Skill 44 workflow-BUILD capability): separate credential, setup-time only.

### 2.2 The 11-alias resolver

Resolution order (first hit wins; canonical name first):

1. `GOHIGHLEVEL_API_KEY` (canonical)
2. `GHL_API_KEY`
3. `GHL_PIT`
4. `GHL_TOKEN`
5. `GHL_PRIVATE_INTEGRATION_TOKEN`
6. `PRIVATE_INTEGRATION_TOKEN`
7. `GHL_PRIVATE_TOKEN`
8. `PIT_TOKEN`
9. `GHL_PIT_TOKEN`
10. `GOHIGHLEVEL_LOCATION_PIT`
11. `GHL_LOCATION_PIT`

**RECOMMENDATION (flagged gap, adopt at build time):** add Convert and Flow-branded aliases to the shared resolver, because clients are onboarded under the "Convert and Flow" name and a client (or a client-side integrator) storing the key as `CONVERTFLOW_API_KEY` is today **falsely reported missing**. Add, in this order after alias 11:

12. `CONVERTFLOW_API_KEY`
13. `CONVERTANDFLOW_API_KEY`
14. `CONVERT_AND_FLOW_API_KEY`
15. `CONVERTFLOW_PIT` / `CONVERTANDFLOW_PIT`

This change belongs in the shared resolver used by Skills 29/36/44, not in a podcast-local fork, so every skill benefits and the fleet keeps ONE resolver.

Location ID resolves the same way with its own alias set: `GHL_LOCATION_ID` (canonical), `GOHIGHLEVEL_LOCATION_ID`, `LOCATION_ID`, `CONVERTANDFLOW_LOCATION_ID`, `CONVERTFLOW_LOCATION_ID`, plus the webhook payload's `{{location_id}}` (payload value, when present, must MATCH the environment value; a mismatch is a hard abort, see Section 7).

### 2.3 ENV-CHECK-BEFORE-FAIL sequence (binding)

A "missing credential" verdict is only valid after ALL of the following, in order, for ALL aliases:

1. **Live process environment FIRST**: `docker exec <gateway> printenv <KEY>` on containerized boxes; `ps eww <gateway_pid>` parse on Mac gateways. The running gateway's environment is the truth the agent actually executes with; files can lag it.
2. **Every environment-store file**: all three known stores on the box (per fleet doctrine: search ALL env stores, live env first), including `.env` files at the platform's documented locations (for example `/docker/<project>/.env` on Hostinger-style hosts).
3. **`openclaw.json`**: check **BOTH** `env.vars.<KEY>` **AND** root-level `env.<KEY>` (both shapes exist in the fleet).
4. **`auth-profiles.json`**.
5. Repeat 1-4 for **all resolver aliases** (11 today, 15+ after the CONVERTFLOW addition).
6. **Broad sweep last**: `grep -ril 'pit-'` across the credential stores to catch a PIT filed under an unknown name. The sweep reports FILE PATHS ONLY, never file contents (Section 7 secrecy rules).

Only "absent everywhere, all aliases" is a valid missing verdict, and the report names every store checked and every alias tried, with **no values printed**.

### 2.4 Isolation rules (binding, from fleet doctrine)

- **Named client's OWN PIT and OWN Location ID only.** Never a shared, master, operator, or agency credential. Never another client's. The publishing pipeline doc states this twice; the guardrail script enforces it (Section 7).
- The engine runs ON the client's own box against the client's own environment. There is no cross-box credential fetch, ever.
- Confirm-set-never-print: every credential check reports `SET` / `NOT SET`, the alias it resolved under, the store it came from, prefix validity (`pit-`), and length. Never the value, never a partial value beyond the 4-character prefix class check, never in debug mode.

---

## 3. Contact Custom Fields: Read and Write

### 3.1 Field key -> field ID resolution (setup-time, cached)

GHL contact API writes address custom fields by **field ID**, while this spec's contract is stated in **field keys** (`contact.<key>`). At first-run smoke test (workflow Step 0):

1. `GET /locations/{locationId}/customFields` (Tier 3) or the `caf` equivalent listing.
2. Build the map `{fieldKey -> fieldId, fieldType, folder}` for every key in Section 3.2/3.3.
3. Persist it in the per-client state file (Section 8). Refresh only when a write fails with an unknown-field error or on operator command, not per episode.
4. Any REQUIRED key absent from the account -> **STOP**: "the custom fields are missing; contact support to have them created via the snapshot." **Never create the standardized fields silently** (initial_setup_requirements rule).

### 3.2 READ fields (input side, exact keys, verbatim from custom_field_map)

| Purpose | Exact key | Notes |
|---|---|---|
| Style selector (main) | `contact.podcast_survey_writing_style` | radio; routes Style Engine |
| Style selector (Personal variant) | `contact.select_your_presentation_style_personal_podcast` | radio, where present |
| Preferred pronoun | `contact.my_preferred_pronoun` | folder Additional Info; governs ALL pronoun use |
| Transparency answer (SMIQ, Single Most Important Question) | `contact.podcast_interview_smiq` | mandatory vulnerability beat |
| SMIQ supporting/history (read if present) | `contact.smiq_answers`, `contact.smiq_history`, `contact.my_client_smiq_answers`, `contact.my_client_smiq_history` | optional |
| Additional info | `contact.podcast_survey__additional_info` | **DOUBLE underscore** between survey and additional; the resolver map must assert this exact key and never fall back to a single-underscore variant |
| Visual description | Podcast Survey quick visual description field | feeds image pipeline only, never spoken |
| Per-style question answers | Podcast Survey fields labeled Barry Q1/Q6, Brene Q1/Q6, Dan Q1/Q2/Q7, Jia Q1/Q6/Q7 | internal labels only; forbidden in any output |
| Release date | `contact.date_for_release` | folder Personal Podcast; future date -> Podbean publish_timestamp |

Read path: Tier 0 `caf` contact-get by `{{contact_id}}`; Tier 3 fallback `GET /contacts/{contactId}` with `Version: 2021-07-28` header, then map returned `customFields[].id` back through the cached key map.

### 3.3 WRITE fields (link-back, workflow Step 16, exact keys)

| Value written | Exact key | Required? |
|---|---|---|
| Podbean episode permalink | `contact.podcast_survey_episode_url` | YES. **Write LAST among the five** (see 3.4) |
| Episode title | `contact.podcast_survey_episode_title` | YES |
| Episode description | `contact.podcast_survey_episode_description` | YES |
| Episode Package document link | `contact.finish_podcast_google_doc_link` | YES |
| Speech Script document link | `contact.podcast_transcript_link` | YES |
| Full transcript text | `contact.podcast_full_transcript` | optional, only if storing text rather than a link |
| Book teaser PDF link | `contact.book_teaser` | **Interview mode only.** Field **may not exist**: if absent from the field map, (a) surface the founder reminder "create a custom field named book_teaser", (b) note the absence in the delivery report, (c) **never silently create it**, (d) do NOT fail the episode over it |

These keys are standardized across every client; only the Location ID and PIT differ per client. Do not guess, rename, or invent keys.

### 3.4 Write mechanics and ordering

- **Primary:** Tier 0 `caf` contact-update. **Fallback:** Tier 3 `PUT /contacts/{contactId}` with a `customFields: [{id, value}, ...]` body.
- **Batch shape:** one update call carrying title, description, Episode Package link, transcript link (and book_teaser when applicable), then a **second, separate call** writing `podcast_survey_episode_url` alone. Reason: the client-account workflow **04-Podcast is Completed is triggered by the Podcast Survey Episode URL field changing**. Writing the URL is therefore potentially a live customer-facing trigger, and it must land only after (a) the Podbean permalink is real and verified, and (b) every other field is already in place so the workflow reads a complete record. This ordering is the cheap insurance that no customer is ever notified about a half-written record.
- **Preconditions for ANY write:** Podbean episode created and permalink captured; both documents created and links captured; media uploaded (Section 4). Field writes never precede publish.
- **Read-back verification (no false done):** after the writes, `GET` the contact and compare every written value byte-for-byte. Only a passing read-back counts as "Convert and Flow save confirmed" in the delivery report. A mismatch retries the write once, then enters failure handling.
- **Value hygiene:** links are bare URLs (no markdown, no surrounding quotes); title/description have no code fences and no em dash characters (preserve_these_rules).

---

## 4. Media Library Operations (Tier 3 REST, mandatory)

Media upload is the one operation where Tier 3 is not a fallback but the **only** path: `POST /medias/upload-file` (multipart/form-data). Tier 0 `caf` does not do binary multipart; the Model Context Protocol tiers are forbidden here anyway.

### 4.1 Folder structure: create-once, reuse-forever

Target structure in the client's Convert and Flow media library:

```
podcast/                 (parent)
  podcast images/        (cover art JPEGs)
  podcast episodes/      (episode MP3s; book teaser PDFs also live under the podcast folder area)
```

**ensure_folders() (idempotent, runs at setup and self-heals at runtime):**

1. Check the per-client state file for cached folder IDs. If present, verify with one cheap `GET /medias/files?parentId=<id>&limit=1` and use them.
2. Cache miss/stale: `GET /medias/files` filtered to folders (`type=folder`, `sortBy=createdAt`, paginate), match names **case-insensitively and trimmed** (`podcast`, `podcast images`, `podcast episodes`) so a manually created "Podcast" folder is reused, never duplicated.
3. Create only what is missing, parent before children, then re-list to capture IDs. **Build-time verification note (no guessing):** the exact folder-create endpoint must be confirmed against the Skill 29 endpoint catalog (413 endpoints) during the build; if REST folder creation is genuinely unavailable, folder creation degrades to a one-time setup task via Tier 4 agent-browser at onboarding, and the runtime engine only ever LOOKS UP folders. Runtime never depends on folder creation succeeding mid-episode.
4. Persist `{podcast_folder_id, images_folder_id, episodes_folder_id}` in the state file.

Duplicate-folder guard: if listing finds two case-insensitive matches for the same name, use the oldest, log a warning for the operator, create nothing.

### 4.2 Uploads (per episode, workflow Step 14)

| Asset | Destination folder | Content type | Filename rule |
|---|---|---|---|
| Cover image | `podcast images/` | image/jpeg | letters/numbers/underscores/dashes only, no extra period before extension (`client_name_episode_title.jpg`) |
| Episode MP3 | `podcast episodes/` | audio/mpeg | client name first, then episode title (`Leanne Dolce - The Power of Marketing.mp3`); letters, numbers, spaces, underscores, dashes only |
| Book teaser PDF (Interview mode only) | podcast folder area | application/pdf | same character rules |

Per upload: `POST /medias/upload-file` with the file part, name, and the target folder ID; headers `Authorization: Bearer <PIT>`, `Version: 2021-07-28`. Capture the returned **public media URL**.

**Public-reachability verification (mandatory before the URL is used anywhere):** issue an unauthenticated `HEAD` (fallback ranged `GET`) against the returned URL and require HTTP 200 plus a matching content type. The image URL feeds the Podbean episode logo and "must be a real, publicly reachable URL of the correctly sized image" (step_a); an unverified URL is a downstream Podbean failure waiting to happen.

Upload failure: one retry after 10 seconds (not for 429; see Section 6), then failure handling. Partial-upload cleanup: if the MP3 uploads but the image fails terminally, the episode is NOT partially published; the run stops before Podbean per the pipeline ordering.

---

## 5. Workflow Enrollment (Skill 44 `caf`, Interview mode only)

### 5.1 The two workflows (exact names, standardized across clients)

- `06-Podcast_Episode_Is_Ready` (adds the "podcast episode is ready" tag, updates the opportunity)
- `04-Podcast is Completed` (triggered by the Podcast Survey Episode URL field changing; runs internal notifications, adds "Podcast Completed Survey Style" tag, waits, continues the follow-up sequence)

### 5.2 Setup-time discovery (once per client, never guessed)

Via Skill 44 `caf` workflow listing: resolve both workflow names to workflow IDs, record each workflow's **actual trigger mechanism** (direct add, tag-triggered + which tag, or field-triggered + which field), and store both in the state file. If either workflow is missing by name, STOP setup and surface it to the founder; building the workflow is a Skill 44 **build** operation requiring the separate Firebase refresh token, an operator decision, never an autonomous runtime act.

### 5.3 Runtime enrollment (workflow Step 17)

**Gate (hard):** enrollment runs only after (1) Podbean episode exists with permalink captured, AND (2) all Step 16 field writes passed read-back verification. Enrolling earlier notifies a customer about an episode that is not there; the responsibility-boundary rule makes that a total failure.

Sequence:

1. The Step 16 URL write has already fired `04-Podcast is Completed` **if** setup discovery confirmed it is field-change triggered in this account. Verify via `caf` (contact's active workflow enrollments): if the contact is enrolled in 04, record "04 enrolled via field trigger". If not, enroll explicitly.
2. Enroll the guest into `06-Podcast_Episode_Is_Ready` explicitly via `caf` (direct add to workflow by workflow ID + contact ID), unless discovery recorded a tag trigger, in which case apply the recorded tag via `caf` instead.
3. Verify both enrollments via a `caf` read. Both confirmed -> "workflow enrollment confirmation" line in the delivery report. Either unconfirmed after one retry -> failure handling; the episode is NOT marked delivered (publishing_failure_handling: delivered requires publish + permalink written + workflow triggered).

**Double-enrollment guard:** never explicitly enroll into 04 when the field trigger already enrolled the contact; the verify-then-enroll order above makes double SMS impossible from our side.

**Mode guard:** Personal Podcast mode NEVER touches these two workflows. Personal mode updates the running episode spreadsheet instead and sends no customer message. The enrollment function takes `mode` as an argument and hard-refuses `personal_podcast_style`.

**Boundary (both modes):** after enrollment (or the spreadsheet update), the engine STOPS. Convert and Flow owns all customer messaging. The engine never sends SMS or email itself.

---

## 6. Rate-Limit Budgeting

**The bucket:** 100 requests / 10 seconds burst + 200,000 / day, **per Location, shared across every tier and every process using that location's PIT**. The `caf` command-line interface, Skill 29 REST calls, other skills on the same box, and any Convert and Flow-touching cron all drain one bucket.

**Per-episode budget (worst case, Interview mode):** roughly 20-30 requests: contact read (1-2), field-map verification (0-1), folder verification (1-3), uploads (2-3), reachability HEADs (2-3, not GHL-bucket but counted for hygiene), field writes (2), read-back (1), enrollment ops (2-4), enrollment verification (1-2). Trivial against the burst limit at single-episode cadence; what matters is the **daily** budget on multi-episode days and shared-tenant days.

**Rules:**

1. **Probe before bulk.** Before Step 14 begins, issue one cheap authenticated GET (the same call doubles as the PIT-pairing check, Section 7) and read `X-RateLimit-Daily-Remaining` (and the 10-second-window remaining header). Require `daily_remaining >= max(500, 10 x episode_budget)` to proceed. Below the floor: queue the job in the hold queue (same mechanics as the credit-out queue: keep the full payload and completed work, alert the founder, resume when the window resets, 60-day maximum hold applies), do not start a publish phase that could die mid-write.
2. **Pace, do not race.** Sub-agents performing GHL calls serialize through a per-location token-bucket throttle in the state directory (Section 8): sustained ceiling ~5 requests/second with jitter, far under the 10/second average the burst window allows, leaving headroom for whatever else shares the bucket. Fan-out is for CPU-bound work (writing, rendering, audio), never for parallel GHL hammering.
3. **On 429: full stop.** Do **NOT** blind-retry. Do **NOT** fall through tiers (Tier 0 -> Tier 3 on a 429 hits the identical bucket and just digs the hole). Read `Retry-After` (or the interval header) and schedule exactly one resume after that window plus jitter. A second consecutive 429 -> hold-queue the job and alert the founder with the failing step and captured state, per publishing_failure_handling. Never mark delivered.
4. **Record consumption.** After each episode, log requests used and last-seen `X-RateLimit-Daily-Remaining` into the state file; the client dashboard's pipeline view can surface "Convert and Flow daily budget" from it, and the daily smoke test can alert on abnormal burn (a runaway loop elsewhere on the box shows up here first).

---

## 7. Credential-Check Guardrail Script (Python) — `ghl_credential_gate.py`

The build brief requires Python guardrails that stop the skill from bypassing its own process. This script is the GHL gate: **no GHL operation in this engine runs unless the gate has passed for this client in this run.** The pipeline invokes it at Step 0 (full mode) and re-invokes it cheaply (cached mode) before Steps 14-17.

### 7.1 Contract

```
ghl_credential_gate.py --client <client_name>
                       --expected-location-id <id | from-registry>
                       --state-dir <per-client state dir>
                       [--mode full|cached]      # full = live checks; cached = verify state freshness (< 24h)
                       [--check-fields]          # run the custom_field_map smoke test
                       [--json]                  # machine-readable verdict for the pipeline
```

Exit codes: `0` PASS · `2` credential missing (valid verdict only after the full Section 2.3 sequence) · `3` **isolation violation** (pairing mismatch / commingling: hard abort + founder alert) · `4` required custom fields missing (client must contact support) · `5` rate-limit floor not met.

### 7.2 Checks, in order

1. **Resolve PIT** through all aliases (11 canonical + the recommended CONVERTFLOW additions once adopted) across the full ENV-CHECK-BEFORE-FAIL sequence (Section 2.3): live gateway process environment first, then env-store files, `openclaw.json` (both `env.vars.<KEY>` and root `env.<KEY>`), `auth-profiles.json`, then the `grep -ril 'pit-'` path-only sweep. Emit an audit table: alias x store -> FOUND/not, plus which alias+store won.
2. **Shape check:** resolved value starts with `pit-` and is plausibly long. Report `prefix_ok: true, length: N` only.
3. **Resolve Location ID** through its alias set; if the run carries a webhook `{{location_id}}`, require equality with the environment value (mismatch -> exit 3).
4. **Live pairing proof:** `GET /locations/{expected_location_id}` with the resolved PIT. HTTP 200 -> this PIT genuinely belongs to this location. 401/403/404 -> exit 3. This same response's rate headers satisfy check 7.
5. **Isolation / anti-commingling proof:** compute `sha256(PIT)[:12]` and compare against the fingerprint stored in this client's state file (write-on-first-pass). A changed fingerprint is logged for the operator. If a fleet-level registry of client fingerprints is available on the operator box, a matching fingerprint under a DIFFERENT client name is a commingling alarm -> exit 3 + alert. The fingerprint is one-way; no value is recoverable or printed.
6. **Custom-field smoke test** (`--check-fields`, first run per client): fetch the field list, require every REQUIRED key from Sections 3.2/3.3 (exact-match, including the double underscore in `podcast_survey__additional_info`); report `book_teaser` as `present` or `ABSENT (remind founder to create custom field book_teaser; do not create silently)` without failing the gate for it. Missing REQUIRED fields -> exit 4 with the support-path message.
7. **Rate floor:** `X-RateLimit-Daily-Remaining` from check 4 must clear the Section 6 floor, else exit 5.
8. **Write verdict** (timestamp, winning alias name, store, location ID, fingerprint, field-map hash, daily-remaining) to the state file for `cached` mode.

### 7.3 Secrecy rules (absolute, enforced in code)

- The PIT value never appears in stdout, stderr, logs, JSON output, exceptions, or tracebacks. A module-level redaction wrapper scrubs the resolved value from any string it emits, and HTTP-layer debug logging is disabled.
- Reports say only: alias name, store name, `SET`/`NOT SET`, `prefix_ok`, `length`.
- The `grep -ril` sweep is filename-only by construction (`-l`); file contents are never read into the report.
- The token travels only inside a `requests` Authorization header built in memory; never through a shell string, never into `subprocess` argv, never into an environment dump.
- No mode, flag, or verbosity level weakens any of this.

---

## 8. Per-Client State File

`<state-dir>/ghl-state.json` (owned by the skill, per client, on the client's own box):

```
{
  "client": "<name>",
  "location_id": "<id>",
  "pit_fingerprint": "<sha256-12>",
  "pit_alias": "GOHIGHLEVEL_API_KEY", "pit_store": "live-process-env",
  "gate": {"last_pass": "<iso8601>", "mode": "full"},
  "field_map": {"podcast_survey_episode_url": "<fieldId>", "...": "...",
                "book_teaser": null},
  "book_teaser_field_present": false,
  "folders": {"podcast": "<id>", "podcast images": "<id>", "podcast episodes": "<id>"},
  "workflows": {"06-Podcast_Episode_Is_Ready": {"id": "<id>", "trigger": "direct_add"},
                "04-Podcast is Completed": {"id": "<id>", "trigger": "field:podcast_survey_episode_url"}},
  "rate": {"last_daily_remaining": 198450, "last_probe": "<iso8601>"},
  "throttle": {"bucket_path": "<state-dir>/ghl-throttle.lock"}
}
```

No secret material is ever stored here (fingerprint only). The file is the create-once-reuse memory for folders, field IDs, and workflow IDs, and the freshness source for the gate's `cached` mode.

---

## 9. Runtime Sequence (Steps 14-17 of the episode workflow, GHL view)

```
[gate cached-pass] -> ensure_folders (state hit)                       Tier 3
  -> upload cover JPEG -> HEAD-verify public URL                       Tier 3
  -> upload MP3        -> HEAD-verify public URL                       Tier 3
  -> (Interview) upload book-teaser PDF -> HEAD-verify                 Tier 3
[Podbean publish happens here; permalink captured]                     (out of GHL scope)
  -> write title/description/package-link/transcript-link
     (+ book_teaser if field exists)                                   Tier 0 caf (Tier 3 fallback)
  -> write podcast_survey_episode_url ALONE, LAST                      Tier 0 caf (Tier 3 fallback)
  -> read-back verify all written fields                               Tier 0 caf
  -> (Interview) verify/enroll 04, enroll 06, verify both              Tier 0 caf (Skill 44)
  -> (Personal) update running spreadsheet; NO workflows               (out of GHL scope)
  -> STOP. Convert and Flow owns all customer messaging.
```

Any failure: retry per section rules -> hold-queue with full state -> founder alert naming the failing step. "Delivered" requires publish + permalink written + enrollment confirmed; anything less is not delivered.

---

## 10. Open Items for the Build (verify, never guess)

1. Confirm the exact media **folder-create** endpoint against the Skill 29 catalog; wire the Tier 4 onboarding fallback only if REST truly lacks it.
2. Confirm, per client at setup, the real trigger mechanism of both workflows via Skill 44 discovery (04 is documented as field-triggered; verify per account).
3. Land the **CONVERTFLOW_\*** alias additions in the SHARED resolver (Skills 29/36/44) and restamp any skill-index content hashes that change as a result.
4. Confirm `X-RateLimit-Daily-Remaining` header casing/name against a live response during the operator-box canary run before any client box sees the skill.
5. Add the gate script to the repo's guardrail set so the quality-control pipeline can refuse any episode whose delivery report lacks a gate PASS, a field read-back PASS, and an enrollment verification PASS.
