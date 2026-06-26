# V2 Autonomous Funnels-Department Build SOP (Skill 06, T4)

**Purpose.** Make the autonomous-agent (V2) build path actually **BUILD in
GoHighLevel** — using the proven token-only REST autosave + the real image
pipeline + the Skill-44 ecosystem — instead of emitting local-only HTML and
"build-with-AI" prompt specs. This SOP is what the Funnels / Web-Dev department
agent's instructions point to. It is the V2 counterpart of the V1 fixed build
harness (`<OPERATOR_HOME>/clawd/skill6-fix/build.py`): the SAME canonical
recipe, driven autonomously off the department board instead of a one-shot
script.

**Scope of THIS phase (T4).** SOP + tooling wire-in + the bounded dispatcher
contract + the telemetry-scrub gate + the canonical verify contract. **NO live
GHL** is run in this phase, and **NO git**. The SOP is written so that when it IS
run live (a later phase, on the operator fixture only), a partial build still
leaves verifiable on-disk evidence and the canonical verifier cannot be gamed.

---

## INTAKE — Board card producer (run FIRST, before any gate)

When a customer funnel or website request arrives, the dept agent MUST post ONE
card to the Command Center Kanban board **before** running any gate (P0, P1, P2)
or build step. Boarding is fail-soft — a board outage or missing credentials
NEVER blocks the build; the build continues unregistered.

```python
# Run from the repo root (or the operator fixture's skill6-fix working dir).
from tools.cc_board import ingest_task

task_id = ingest_task(
    title="<short card title, e.g. 'Sales Funnel Build — <brand>'",
    description="<customer request brief, markdown OK>",
    job_type="funnel",    # 'funnel' → department_slug='funnels'
                          # 'website' → department_slug='web-development'
    priority="high",      # low | medium | high | critical
    # idempotency_key omitted → auto uuid4; supply a deterministic key for retries
)
# task_id is None if the board is unreachable — build continues either way.
```

**department_slug routing** (controlled by `job_type`):
- `'funnel'`, `'sales-funnel'`, `'opt-in'`, `'multistep'` → `department_slug='funnels'`
- `'website'`, `'landing-page'`, `'single-page'`, `'web-development'` → `department_slug='web-development'`

**What the POST sends** to `POST /api/tasks/ingest`:
```json
{
  "title": "<card title>",
  "description": "<brief>",
  "source": "funnel",
  "department_slug": "funnels",
  "idempotency_key": "<uuid4 or caller-supplied>",
  "priority": "high"
}
```
Fields intentionally OMITTED (the ingest route ignores them and the CC
`TaskStatus` enum does NOT include them): `task_type`, `stage`, `parent_task_id`,
`depends_on`, `waiting_on_dependency`. The ingest route always creates the task at
`backlog` status and then calls `routeTask()` server-side — the producer never
sets status.

**Credentials from environment** (never hardcoded):
```
MISSION_CONTROL_URL   base URL of the Command Center (absent → board disabled, build continues)
MC_API_TOKEN          long-lived bearer for the middleware layer (optional)
WEBHOOK_SECRET        HMAC-SHA256 signing secret for the per-route layer (optional)
CC_BOARD_TIMEOUT      per-request timeout in seconds (default 8)
```

**Verify the producer works** (no network required):
```bash
python3 06-ghl-install-pages/tools/cc_board.py --selftest
# exits 0 on pass
```

**Live demo** (proves a real card lands on the board + routes off CEO):
```bash
MISSION_CONTROL_URL=https://<cc-url> MC_API_TOKEN=<tok> \
  python3 06-ghl-install-pages/tools/cc_board.py --demo
# prints {"ok": true, "task_id": "<uuid>", "idempotency_key": "skill6-demo-<uuid>"}
```

**Write the returned task_id into the routing receipt** so downstream steps
can reference the board card:
```bash
echo '{"task_id":"'$TASK_ID'","department_slug":"funnels","source":"funnel"}' \
  > routing/intake-receipt.json
```

**Scope note:** this step lands the card on the board (Goal A). It does NOT
trigger the Skill-6 BUILD — that is Goal D (the dispatcher in §1 / `v2_dispatcher.py`),
which is a separate, follow-on wiring step.

---

## 0. The V2 gap this SOP closes (grounded in the prior run)

The prior V2 run (`v2-client-agent/v2-…`) produced, per its own
`scorecard/verify-summary.json`:

| Stage | Prior V2 status | Why it failed |
|---|---|---|
| S1 route | DONE | routing worked (department=funnels, task assigned to the specialist, not CEO) — **keep as-is** |
| S3 images | **ABSENT** | the agent never ran the image pipeline; `images/` empty |
| S4 funnel | **SPEC-ONLY** | only a `build-with-ai-prompt.md`; no GHL funnel, no preview URL, no autosave 201 |
| S5 website | **LOCAL-HTML-ONLY** | wrote `website/index.html` etc. to disk; nothing in GHL |
| dispatch | **hung (HTTP 000)** | `POST /api/tasks/<id>/dispatch` hung; the task sat in `backlog`; no executor fired |
| telemetry | **leaked** | captured turn telemetry carried `redacted-client__<verb>` MCP tool names |

Two root causes, two fixes:

1. **No live executor for the Funnels department** → the task never ran. Fix:
   §1 (a live dept executor OR a bounded backlog dispatcher).
2. **The agent, when it did run, produced local HTML** because its instructions
   never pinned the canonical token-only REST autosave path. Fix: §2–§5 (this
   SOP, pinned into the dept agent's instructions).

Plus the evidence-hygiene fix: §6 (scrub the leaked client namespace) and §7
(the ONE canonical verifier).

---

## 1. A live executor for the Funnels / Web-Dev department (the whole V2 gap)

The department board had the task in `backlog` and `POST /api/tasks/<id>/dispatch`
hung (HTTP 000), so no build ever fired.

> **REQUIRED DEFAULT — Option B (the bounded coded dispatcher).** Under the resume
> path the executor MUST default to the bounded dispatcher
> `tools/v2_dispatcher.py` (`dispatch_one`) — it is the CODED enforcement of the
> bounds below: a HARD `max_inflight = 1`, a `1800s` wall-clock cap that converts
> a hang into a recorded `FAILED` (the HTTP-000 fix), and a `30s` poll backoff
> (`DEFAULT_MAX_INFLIGHT` / `DEFAULT_WALLCLOCK_CAP_S` / `DEFAULT_POLL_BACKOFF_S`).
> Self-check the wiring with `python3 tools/v2_dispatcher.py --selftest`. Option A
> is an explicit OPERATOR OPT-IN only (the "3 retries" prose path is
> agent-discretionary and is NOT the default); do not fall back to it implicitly.

### Option B — the bounded coded dispatcher (REQUIRED DEFAULT)
A small, bounded loop/cron that pulls `backlog` tasks off the department board
and runs them on the department model, driven by `tools/v2_dispatcher.py`
(`dispatch_one`) — never an unbounded ad-hoc loop. **Bounded** = it MUST have:

- a **max in-flight = 1** (one build at a time — mirrors the per-item ledger
  doctrine; never fan out a second build over the same fixture),
- a **per-task wall-clock cap** (default 1800s) after which the task is marked
  `FAILED` with the partial evidence captured (never left hung at HTTP 000),
- a **poll backoff** (default 30s) so it does not spin, and
- a **pre-warm step** that triggers GHL tool discovery ONCE before the build turn
  (the prior V2 timed out ~570s at tool-discovery; pre-warming the GHL MCP /
  agent-browser session moves that cost out of the build turn).

**Dispatcher contract (state, so a partial run is resumable — not prose):**

```
backlog -> dispatched -> building -> verified | FAILED
```

- `dispatched`: the dispatcher claimed the task (writes `routing/task-record.json`
  with `claimed_at`, `max_inflight=1`).
- `building`: the dept agent is running §2–§5; it writes `funnel/ledger.json`,
  `website/ledger.json`, `images/manifest.json`, `ecosystem/*.json`, and
  `logs/{funnel,website}-preview.log` **as it goes** (so even a crash leaves
  evidence).
- `verified`: the canonical verifier (§7) ran and `overall_pass` is recorded
  (true OR false — a false is reported honestly, never massaged).
- `FAILED`: the wall-clock cap hit, or a step refused (e.g. sub-account
  MISMATCH); the partial evidence + the failure reason are written. **Never**
  leave a task hung — a hang is a `FAILED` with `reason="dispatch timeout"`.

**Raise the gateway build-turn timeout** for the dept agent (the prior V2 timed
out at tool-discovery). The build turn needs headroom for: seed+activate, GHL
tool discovery (pre-warmed), per-page read→splice→autosave→verify, image gen +
upload, and ecosystem creation.

---

## P0. Offer Spec — consume offer-spec.json from Chief Sales Officer

When this SOP is invoked as part of the full-funnel pipeline (SOP-07), the P0
stage has already completed before this SOP runs. The dept agent MUST read the
offer-spec.json produced by the Chief Sales Officer before beginning any build.

```
cat working/funnels/<slug>/offer-spec.json
```

Assert ALL six fields are present and non-null (no `[CLIENT TO SUPPLY]` surviving
from the P0 handoff): `product_name`, `deliverables`, `price_points`, `guarantee`,
`bonuses`, `positioning`. If any field is missing or still `[CLIENT TO SUPPLY]`,
HALT and return a structured handback to the orchestrator — do NOT proceed to P1
or the build with an incomplete offer spec. Write `routing/p0-gate.json`
`{offer_spec_complete: true|false, missing_fields: [...]}`.

---

## P1. Funnel Spec — consume funnel-spec.json, persona-grounded on hormozi-100m-offers

When invoked as part of the full-funnel pipeline, P1 (the Funnel Strategist) has
already produced `working/funnels/<slug>/funnel-spec.json` before this SOP runs.
The dept agent MUST:

1. **Read funnel-spec.json.** Confirm: `funnel_type` is one of the five canonical
   strings (`short-form squeeze`, `long-form sales`, `video-sales-letter`,
   `application`, `webinar`, `2-step`). Confirm `pages` array is non-empty and
   every page has at least a `hero` and `cta` section slot. If any check fails,
   HALT with a structured handback — do NOT build against a malformed spec.

2. **Verify persona-selection-log.md entry.** Read
   `working/funnels/<slug>/persona-selection-log.md`. Confirm an entry exists with
   `selected_persona: hormozi-100m-offers` for the funnel architecture task. If the
   log entry is missing, HALT — the P1 stage is not done. Return to orchestrator.

3. **Write P1 gate receipt.** `routing/p1-gate.json`:
   `{funnel_spec_valid: true, funnel_type: "<type>", persona_log_verified: true,
   persona_selected: "hormozi-100m-offers"}`.

The dept agent does NOT re-run P1 persona selection. P1 persona grounding is owned
by the Funnel Strategist. This step is GATE-ONLY: verify and proceed.

---

## P2. Copy Persona Attachment — verify copy.md persona grounding before build

When invoked as part of the full-funnel pipeline, P2 copy (from the Conversion
Copywriter) must be APPROVED before the build begins (SOP-07 P4 depends on P2
APPROVED). The dept agent MUST:

1. **Confirm copy.md status is APPROVED.** Read the artifact header. If status is
   `PENDING-QC` or `REVISED-PENDING-QC`, HALT — P4 cannot begin until P2 is
   APPROVED. Return `status: waiting_on_dependency` to the orchestrator.

2. **Verify copy persona log.** Read `working/funnels/<slug>/persona-selection-log.md`.
   Confirm an entry exists for the copy task (distinct from the P1 funnel-spec
   entry). The copy persona must be one of: `bly`, `wiebe`, `miller`, `hormozi`,
   `cialdini`. If the copy persona log entry is missing, HALT and return a
   structured handback — the Conversion Copywriter's Gate 1 requires this entry and
   its absence means copy QC was incomplete.

3. **Write P2 attach receipt.** `routing/p2-persona-attach.json`:
   `{copy_status: "APPROVED", copy_persona_verified: true,
   copy_persona_selected: "<persona id>"}`.

4. **Proceed to S2 (the canonical build recipe below).** All three pre-flight
   gates (P0, P1, P2) must show `true` in their gate receipts before the first
   GHL autosave call.

---

## 2. The canonical build recipe the dept agent MUST follow (NOT local HTML)

This is the pinned recipe. It is the V1 *fixed* path (the solver doc §2 +
`ghl_rest_canvas` + `ghl_builder.emit_rest_save_plan`), driven autonomously. The
dept agent does NOT write standalone HTML files as the deliverable — local HTML
is at most a scratch draft of the copy; the **deliverable is content saved into
GHL pages via REST autosave, verified at a real `/preview/` URL.**

### 2.0 Auth (token-only — reuse verbatim, never re-implement)
```
python3 06-ghl-install-pages/tools/seed-ghl-auth.py --print-seed --out <RUN>/ghl-auth-seed.json
bash   06-ghl-install-pages/tools/inject-ghl-auth.sh <session> <RUN>/ghl-auth-seed.json --pre-open
```
- Mints the Firebase `id_token` (the `token-id` header value). Seeds Firebase
  IndexedDB + the SPA cookies; activates via `store.dispatch('auth/get')` +
  `$router.push`. **NEVER reload** (a reload re-runs the boot IIFE → signs the
  seeded session out).
- **HARD sub-account gate before ANY write:** read `GET /oauth/2/login/current`
  → take the live location/company; assert
  `ghl_builder.subaccount_matches(current_location_id, "$GHL_LOCATION_ID")`
  is `ok`. On MISMATCH → refuse, mark the task `FAILED`, write the guard verdict.
  (The plan emitters already gate on this; the agent must not bypass it.)

### 2.1–2.6 Per page: read → splice → autosave → verify → revert
**SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown,
reaper backstop.** Before the first step, acquire the gateway once:
`bash tools/browser_manager.sh ensure` (lock + lease + TTL + teardown trap), and
route every step through it (`bash tools/browser_manager.sh eval -- --stdin`) —
NEVER call `agent-browser` directly and NEVER invent a per-iteration session
name. The python emitters refuse outside a `browser_manager.browser_session()`
bracket, and each emitted plan ends with a guaranteed close step.

The agent does NOT hand-roll the fetch. It calls
`ghl_builder.emit_rest_save_plan(...)` to get the ordered, gated, draft-by-default
plan and executes each step's `eval`/`argv` **through the gateway** (the
funnels/builder origin is Cloudflare-1010-gated for bare Python):

1. **stage_token** — `ghl_rest_canvas.write_token_js_file(id_token, <RUN>/token.js)`;
   feed to `bash tools/browser_manager.sh eval -- --stdin`. **NEVER** bash
   `${VAR@Q}` (mangles the JWT → spurious 401).
2. **page_read** — `GET /funnels/page/<id>`; fetch the signed
   `pageDataDownloadUrl` (no auth header) for the editable blob; read numeric
   `pageVersion`.
3. **edit** — `edit_element_customcode(blob, {section_idx, element_idx}, new_html)`
   where `new_html` carries the page marker **and the real `<img src="<CDN
   url>">`** from §3. Pure splice; the pristine blob is kept as the revert
   baseline.
4. **page_autosave** — POST the edited blob as a **DRAFT**
   (`publish=may_publish(approval)`, default DRAFT; `pageVersion` numeric n+1;
   `pageType:"draft"` keeps the live pointer put). Expect **201**.
5. **verify_preview** — `ghl_builder.verify_url(preview_url, marker)` → HTTP 200
   AND marker in body. Advances the ledger to `previewed`. (NEVER report a page
   good on no-error alone.)
6. **revert_baseline** — re-POST the pristine baseline as a new draft version;
   assert `ghl_rest_canvas.blob_md5(reread) == baseline_md5` (byte-identical;
   live pointer unmoved). Reversibility bar per solver doc §7.2.

**Ledger as you go.** `ghl_builder.ledger_write(run_id, surface, step, state)` at
each landed step (`code-saved` → `page-saved` → `previewed`; `published` only on
`may_publish`). Workflows use the parallel `wf-rewired` state. A crash mid-build
leaves a truthful furthest-reached ledger.

**No synthetic stubs.** Save the **fetched** preview DOM as `<step>-preview.html`
(real capture via `ghl_verify.screenshot_plan`'s `dom` step), and **real PNG**
screenshots (desktop 1440×900 + mobile 390×844) — never the V1 SVG placeholders,
never a hand-written "preview" HTML that was never fetched.

---

## 3. Images (R2) — real rasters, real CDN, referenced in-page

The dept agent MUST run the proven image pipeline (NOT write SVG placeholders,
NOT leave `images/` empty):

1. **Generate** real PNGs from copy-derived prompts via the repo's verified
   generator (`23-ai-workforce-blueprint/templates/presentation-render/
   kie_generate.py`, `mode:"t2i"` when there is no logo to seed) — it submits to
   `api.kie.ai`, polls, downloads, and **verifies PNG magic bytes** (`b"\x89PNG"`,
   FAIL-LOUD on non-PNG). Requires `KIE_API_KEY` in the client env store; **if
   absent → honest FAIL recorded in `images/manifest.json`, never an SVG stub.**
2. **Upload** each PNG to GHL media via `tools/ghl_media.py`
   (`POST services.leadconnectorhq.com/medias/upload-file`, Bearer LOCATION PIT,
   `Version: 2021-07-28`) → capture `{fileId, public url}`. **Auth-model split:**
   media upload is the `services.*` origin with a Bearer PIT — **bare Python OK**
   (NOT the Cloudflare-1010-gated funnels-builder origin).
3. **Re-verify** each CDN URL is a genuine HTTP 200 and log it to
   `logs/asset-cdn.log` (real `status=200 | <https url> | OK` lines — kill the
   `LOCAL-SVG-PLACEHOLDER` line).
4. **Reference** the public CDN `<img>` in-page via the §2 splice (step 3 above).
5. `images/manifest.json` maps `{id, prompt, file, cdn_url(https),
   cdn_http_status:200, used_on_page_id}` — **no `file://`, no placeholder note.**

(T2 owns `ghl_media.py` + the manifest contract; this SOP pins that the dept
agent USES it rather than stubbing.)

---

## 4. Ecosystem (R5) — real objects + a form→CRM proof

Pre-req: `export CAF_ALLOWED_LOCATION_IDS="$GHL_LOCATION_ID"` (the configured GHL
location id) + the LOCATION
PIT so the Skill-44 safety gate passes. **Auth-model split:** calendars /
products / forms / contacts are the `services.*` origin + Bearer PIT — **bare
Python OK** (the Skill-44 CLI), NOT the WAF-gated funnels origin.

The dept agent creates REAL objects and writes **creation receipts** (`status:201`,
ids, re-GET 200) — NOT `status:"PLANNED"` stubs:

1. **Calendar** — "Scent-Bar Workshop" via the Skill-44 CLI `calendars create`
   (T3) → `ecosystem/calendar.json` receipt.
2. **Product/price** — via `payments create-product` + `create-price` (T3) →
   `ecosystem/product-price.json` receipts.
3. **Opt-in form** — a real 3-field form embedded on the opt-in page (custom-code
   element via the §2 splice), posting to GHL contact capture → `optin-form.json`
   with the live `page_id` + the marker proving it rendered.
4. **CRM contact + form→CRM PROOF (the dimension's hard requirement):**
   - baseline `contacts search` → `before_count`;
   - submit the opt-in (or `contacts create` with a unique
     `…@<brand>-test.invalid` email + tags `workshop-registrant`, `soap-lead`);
   - **prove the roundtrip**: `contacts search` by that email → assert the new id
     exists AND carries both tags → re-GET `contacts/{id}`;
   - write `ecosystem/contact-test.json` with `created_contact_id`,
     `tags_confirmed:true`, `before_count`/`after_count` (after = before+1),
     `submit_method`; then `contacts delete {id}` after proof, logged.
5. **Workflow** — `POST /workflow/<loc>` + `/workflow/<loc>/trigger`; verify via
   `?includeTriggers=true` (the load-bearing read). `workflow.json` is a real
   receipt.

---

## 5. What the dept agent MUST NOT do (the local-HTML anti-pattern)

- **MUST NOT** treat `website/index.html` (or any local HTML file) as the
  deliverable. Local HTML is scratch at most; the deliverable is GHL page content
  saved via REST autosave and verified at a real `/preview/` URL.
- **MUST NOT** emit "build-with-AI prompt" specs in place of a build (the prior
  S4 SPEC-ONLY failure).
- **MUST NOT** write SVG image placeholders or synthetic "preview" HTML that was
  never fetched (the R7 SVG-screenshot failure).
- **MUST NOT** write `status:"PLANNED"` ecosystem stubs in place of real
  creation receipts.
- **MUST NOT** bypass `subaccount_matches` or `may_publish`, or publish without
  explicit approval. Automation produces `/preview/` URLs only; true go-live
  needs the client Connect-Domain step (NOT automatable — never faked).
- **MUST NOT** reload the seeded session, or stage the token via bash `${VAR@Q}`.

---

## 6. Evidence hygiene — scrub leaked client namespaces (R7 P3)

Before ANY captured turn telemetry lands under the V2 evidence root, run it
through `tools/scrub_turn_telemetry.py` so a leaked client-namespaced MCP
tool-name (`redacted-client__<verb>`, as seen in the prior V2 capture) is
neutralised to `mcp__redacted__<verb>` (the tool VERB is preserved for debugging;
the client namespace is removed):

```
python3 06-ghl-install-pages/tools/scrub_turn_telemetry.py <RUN>/logs/agent-turn-*.json
# post-write gate (fail-loud if anything slipped through):
python3 06-ghl-install-pages/tools/scrub_turn_telemetry.py --check <RUN>/logs/agent-turn-*.json
```

The repo + the durable evidence root are FLEET-WIDE — no client name/namespace
may ever appear in them. The `--check` gate exits non-zero if a leak remains, so
the dispatcher can refuse to mark a task `verified` while telemetry is dirty.

---

## 7. The ONE canonical verifier (R7 — kills the 6/6-vs-1/6 contradiction)

V2 uses the SAME canonical verifier as V1 — `tools/ghl_verify.py`
(`ghl_builder.py verify-all` delegates to it). There is exactly ONE source of
truth and the summary is a guarded pure reduction of it:

```
python3 06-ghl-install-pages/tools/ghl_builder.py verify-all <RUN> <RUN>/pages.json \
    --run-id <id> --version client-agent --brand "<fictional brand>"
```

- writes `logs/final-preview-verify.json` (raw per-page HTTP 200 + marker — the
  source of truth) FIRST;
- derives `scorecard/verify-summary.json` STRICTLY by reducing that array
  (`passed = sum(1 for r if r.PASS)`); the summary can never claim more than the
  raw log;
- a hard guard (`ghl_verify.assert_consistent`) raises `VerifyContradiction` and
  the CLI exits non-zero if the summary is EVER more optimistic than the raw log
  (the exact 6/6-vs-1/6 defect is structurally impossible);
- exits non-zero on `overall_pass:false` — a failing/partial build cannot read as
  success.

`pages.json` is the list the dept agent built (each `{step, page_id,
preview_url, marker}`). The dispatcher marks the task `verified` ONLY after this
runs and records the (honest) verdict.

---

## 8. V2 evidence root (no conflation, never /tmp)

- V2 evidence: `<OPERATOR_HOME>/clawd/skill6-fix/v2-<RUN_ID>/` — a fresh
  RUN_ID, **separate** from any V1 run dir (honor the no-conflation rule).
- Subtree (written as the build proceeds): `routing/`, `copy/`, `images/`
  (manifest + real PNGs), `funnel/` (ledger + `<step>-preview.html`), `website/`
  (ledger + `<step>-preview.html`), `ecosystem/` (real receipts),
  `screenshots/` (real PNGs), `logs/` (`{funnel,website}-preview.log`,
  `asset-cdn.log`, scrubbed `agent-turn-*.json`, `final-preview-verify.json`),
  `scorecard/verify-summary.json`.
- Never `/tmp`. Reboot-survivable. The routing layer (S1) is unchanged — it
  already worked.

---

## 9. Definition of done for the V2 build path (honest bar)

A V2 build is DONE when, on the operator fixture only (a later live phase):

1. the dept executor/dispatcher (§1) **picked up the task and ran it** (no hang;
   `routing/task-record.json` shows `dispatched → building → verified|FAILED`);
2. real GHL pages carry the marker + a real `<img>` and verify HTTP 200 at their
   `/preview/` URLs (§2, §3) — confirmed by the canonical verifier (§7);
3. the ecosystem objects are real creation receipts incl. the form→CRM
   roundtrip proof (§4);
4. telemetry is scrubbed and the `--check` gate is clean (§6);
5. evidence is under `skill6-fix/v2-<RUN_ID>/`, no conflation (§8);
6. the verdict (`overall_pass`) is whatever the raw log proves — a sub-8.5 result
   is reported as FAIL, never massaged.

Going live (a real public domain) remains a CLIENT Connect-Domain step and is
NOT automated; preview URLs + draft saves are the bar.
```
