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

> **SELF-CHECK (run at each phase).** Run `references/ghl-build-self-check.md`
> top-to-bottom — it is a scannable VIEW of the gates below; **do not advance a
> phase until its bold `Done when:` gate passes.** `ghl_verify.render_check` (§7)
> stays the un-fakeable final backstop — a checkbox is a self-check, the sealed
> verifier is the verdict.

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

**department_slug routing** (controlled by `job_type`, or an explicit `department_slug=` override):
- `'funnel'`, `'sales-funnel'`, `'opt-in'`, `'multistep'` → `department_slug='funnels'`
- `'website'`, `'landing-page'`, `'single-page'`, `'web-development'` → `department_slug='web-development'`
- **P2-COPY dependency card** (`department_slug='marketing'`) — opened automatically for a
  standalone "write it for me" page/website so its copy is authored by the Conversion
  Copywriter, not improvised inline. See **P2.5** below (FIX-COPY-01).

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
`bonuses`, `positioning`. **Plus `founder_name`** — the SEO/AI-search author
(§2.07) and a required pre-flight input that MUST be the FOUNDER's personal name,
sourced from the client / GoHighLevel location record (never free-typed, never the
brand). If any field is missing or still `[CLIENT TO SUPPLY]`,
HALT and return a structured handback to the orchestrator — do NOT proceed to P1
or the build with an incomplete offer spec. Write `routing/p0-gate.json`
`{offer_spec_complete: true|false, founder_name_present: true|false, missing_fields: [...]}`.
(If the upstream offer-spec lacks `founder_name`, P1 step 1.1 obtains it from the
client/GHL record before the build — it is fail-closed there too.)

---

## P0.5 / STEP 0 — Template-first funnel match (reuse-before-reinvent; guide-not-rule)

Before the build phases, a **template-first funnel match** runs as STEP 0 in
`tools/v2_dispatcher.py` (`_resolve_step0` → `funnel_matcher.step0_match`). It is
ADVISORY and NEVER blocks a build (env-gated on `GHL_FUNNEL_INDEX`/`GHL_FUNNEL_CATALOG`,
which the box install exports). It consults the 38-template funnel library
(`06-ghl-install-pages/funnel-templates/`, by category), picks the best-fit proven
template, and — honoring the flexibility contract (HONOR_USER an explicit owner choice;
SUGGEST when unsure; USE_TEMPLATE hands-off; CREATE_NEW only when nothing fits) — writes
`routing/funnel-match.json` + a compact `routing/match-decision.json` receipt, attaches the
matched template's `pageStructure`/`copy_persona`, stamps `task['funnel_template_id']`, and
reads `_links/funnel-to-automation.json` to attach the recommended `linked_automations` for
the COMPLETE-funnel handoff to Skill 44 (`routing/skill44-handoff.json`, written on verify).
The dept agent uses the matched template's `pageStructure` as the page scaffold rather than
reinventing structure. (See `funnel-templates/README.md` and SKILL.md "Funnel template
library (STEP 0)".)

---

## P1. Funnel Spec — consume funnel-spec.json, persona-grounded (template-first)

When invoked as part of the full-funnel pipeline, P1 (the Funnel Strategist) has
already produced `working/funnels/<slug>/funnel-spec.json` before this SOP runs.
The dept agent MUST:

1. **Read funnel-spec.json.** Confirm: `funnel_type` is one of the five canonical
   strings (`short-form squeeze`, `long-form sales`, `video-sales-letter`,
   `application`, `webinar`, `2-step`). Confirm `pages` array is non-empty and
   every page has at least a `hero` and `cta` section slot. If any check fails,
   HALT with a structured handback — do NOT build against a malformed spec.

1.1. **`founder_name` is a REQUIRED build input — fail-closed (transcript §2).**
   The funnel-spec schema MUST carry a non-empty, non-placeholder `founder_name`.
   It is the SEO/AI-search **author** (§2.07) and a build-time data dependency:
   the SEO author MUST be the FOUNDER's personal name, sourced from the client /
   GoHighLevel location record (company owner) — **never free-typed, never the
   brand**. Assert it in this S1/P1 pre-flight with
   `ghl_builder.validate_founder_name(spec["founder_name"], brand=<brand>)`; on a
   missing / placeholder / equals-brand value it raises `SeoValidationError` —
   **HALT** with a structured handback (the build cannot reach the §2 SEO
   end-state without it). If the upstream offer-spec (P0) did not already carry
   `founder_name`, P1 must obtain it from the client/GHL record before building.

1.5. **Verify `funnel_template_id` (template-first).** Confirm funnel-spec.json carries
   `funnel_template_id` (set by the Funnel Strategist at SOP 9.5 step 1.5). If present,
   use the matched template's `pageStructure` from
   `06-ghl-install-pages/funnel-templates/<group>/<funnel_template_id>.json` as the build
   scaffold and carry `linked_automations` to P5. If absent (legacy spec), proceed from
   the section blueprint and note it in the handback — it should have been set at P1.

2. **Verify persona-selection-log.md entry.** Read
   `working/funnels/<slug>/persona-selection-log.md`. Confirm an entry exists naming
   the persona the Funnel Strategist selected for the funnel architecture task (the
   selector's TOP-RANKED slug — NOT a hardcoded default; `hormozi-100m-offers` is the
   typical match for value-ladder tasks but a Brunson funnel persona or `pedro-adao-*`
   may be correct). If the log entry is missing, HALT — P1 is not done. Return to orchestrator.

3. **Write P1 gate receipt.** `routing/p1-gate.json`:
   `{funnel_spec_valid: true, funnel_type: "<type>", funnel_template_id: "<id|null>",
   persona_log_verified: true, persona_selected: "<slug from the log>",
   founder_name_present: true, founder_name: "<the validated founder name>"}`.
   `founder_name_present` MUST be `true` before the first GHL autosave (the §2.07
   SEO author binds to it).

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
   entry). **Two-part rule (D5/B-D1, RATIFIED 2026-07-14 — kills the old bare
   5-surname cap):** (a) **VOICE** — the entry's voice persona may be ANY of the
   **99** catalog personas; VOICE is audience-led, the entire point of the blend,
   and is never restricted to a fixed surname list (D1/B-D1). (b) **copy-craft
   TASK slot** — the entry's task/copy-craft persona MUST be a member of the named
   `copy_craft_pool` in `shared-utils/persona-crosswalk.json` (the five
   direct-response authorities — `bly-copywriters-handbook`, `wiebe-copy-hackers`,
   `miller-building-storybrand`, `hormozi-100m-offers`, `cialdini-influence` —
   plus every `edwards-*` id plus every Brunson-family crosswalk target),
   machine-validated by `persona_crosswalk.py --validate`. **This allowlist
   governs the TASK/CONVERSION slot ONLY** (D3/D-A3, RATIFIED 2026-07-14) — VOICE
   and SUBSTANCE come from the blend, never from this pool. If the copy persona
   log entry is missing, HALT and return a structured handback — the Conversion
   Copywriter's Gate 1 requires this entry and its absence means copy QC was
   incomplete.

3. **Write P2 attach receipt.** `routing/p2-persona-attach.json`:
   `{copy_status: "APPROVED", copy_persona_verified: true,
   copy_persona_selected: "<persona id>"}`.

4. **Proceed to S2 (the canonical build recipe below).** All three pre-flight
   gates (P0, P1, P2) must show `true` in their gate receipts before the first
   GHL autosave call.

---

## P2.5 Standalone page / website copy routing — the P2-COPY mini-epic (FIX-COPY-01)

**The single largest copy-quality lever.** The P0→P2 pre-flight above only runs when
this SOP is invoked *inside* the full-funnel pipeline (SOP-07). A plain, standalone
request — **"build me a landing page"**, **"make me a website"**, **"I need a sales
page"** — does NOT enter that pipeline, so historically its copy was improvised inline
by the build session model (the ~2/10 copy problem). It must not be.

**Intent-signal amendment to SOP-07 Step 1.** Treat the bare phrases **"landing page"**,
**"website"**, and **"sales page"** as copy-authoring intents whenever copy must be
written — i.e. whenever the intake `has_copy` answer is **"write it for me"** and no
APPROVED `copy.md` already exists. These are copy-bearing requests exactly like a
funnel; they simply arrive without the full-funnel epic around them.

**What the dispatcher does automatically.** `tools/v2_dispatcher.py::_run_intake`
(via `_open_copy_dependency`) detects this case and opens a **3-card mini-epic**
(`p1-spec → p2-copy → p4-build`):

1. Posts a **P2-COPY** card routed to the **`marketing`** department (the Conversion
   Copywriter, per SOP-07 Step 3) — `cc_board.ingest_task(..., department_slug="marketing")`,
   fail-soft (board optional).
2. Flags the build task **`waiting_on_dependency`** and writes
   `routing/copy-dependency.json`.
3. **HOLDS the build** — `dispatch_one` returns state `waiting_on_dependency` and the
   injected builder is NEVER called — until an **APPROVED** `copy.md` exists under the
   run dir (checked by `_approved_copy_exists`; a `PENDING-QC` / `REVISED-PENDING-QC`
   header does NOT clear it). A later dispatch, after the Conversion Copywriter's
   `copy.md` is APPROVED, proceeds to the build normally.

The local `waiting_on_dependency` receipt is the **binding** gate; the board card is
visibility only. `"I have copy"` (or an already-APPROVED / explicitly-provided `copy.md`)
is a clean no-op — the build proceeds immediately. Funnels are unaffected: their copy
runs through P0–P2 above, and `has_copy` is a page-only intake question.

---

## 2. The canonical build recipe the dept agent MUST follow (NOT local HTML)

This is the pinned recipe. It is the V1 *fixed* path (the solver doc §2 +
`ghl_rest_canvas` + `ghl_builder.emit_rest_save_plan`), driven autonomously. The
dept agent does NOT write standalone HTML files as the deliverable — local HTML
is at most a scratch draft of the copy; the **deliverable is content saved into
GHL pages via REST autosave, verified at a real `/preview/` URL.**

> **CANONICAL RECIPE — read first.** The authoritative, transcript-derived
> step-by-step (Sites → Funnels → ZHC funnel → step → Create-from-blank → close
> Ask AI → Code Block → **Allow Rows to take entire width** → paste → **two saves
> (CODE then PAGE)** → **SEO panel** → next step) is
> `references/ghl-build-spec-from-transcript.md`. Where this REST-first path and
> the transcript disagree on *coverage*, the transcript wins on *what must be true
> at the end*; the REST path below reaches that same end-state autonomously.

> **ZHC naming (transcript ~03:28, step 20).** Every funnel/website/step name
> carries the **UPPERCASE `ZHC ` prefix** (emitted by
> `ghl_builder.ensure_zhc_prefix`; matching is case-insensitive so an existing
> `zhc`/`Zhc` is never double-prefixed). Multi-step funnels auto-number each
> created step **`ZHC part 2` … `ZHC part N`** via
> `ghl_builder.zhc_step_name(name, order)` when no step name is supplied.

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

### 2.0.1 Credential preflight — LOAD THE ENV STORE FIRST (step 0 of every build)

**This is a HARD GATE that runs BEFORE any page is built.** It exists because the
image step once false-failed ("GHL LOCATION PIT not found") on a LOCATION PIT the
operator had used for SIX MONTHS — the value was in the canonical store the whole
time; the agent simply ran in a clean shell where the store had never been sourced.

**Where the GHL credentials LIVE (env var name → store):**

| Credential | Env var (preferred → alias) | Store (resolution order) |
|---|---|---|
| LOCATION PIT (media-scoped) | `GOHIGHLEVEL_API_KEY` → `GHL_API_KEY` → `GOHIGHLEVEL_LOCATION_PIT` → `GHL_LOCATION_PIT` | `~/.openclaw/secrets/.env` → `~/clawd/secrets/.env` → `~/.openclaw/workspace/.env` |
| Location id | `GOHIGHLEVEL_LOCATION_ID` → `GHL_LOCATION_ID` → `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` → `CAF_ALLOWED_LOCATION_IDS` | same stores |
| KIE image key | `KIE_API_KEY` | same stores |

The LOCATION PIT is what media upload REQUIRES (`medias.write` scope). The **AGENCY**
PIT (`GOHIGHLEVEL_AGENCY_PIT` / `GOHIGHLEVEL_AGENCY_API_KEY` /
`GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT` / `GHL_AGENCY_PIT`) **401s for media** — it is
NOT interchangeable. Reach for the LOCATION-class name ONLY; never substitute an
agency token.

**Step 0 — source the store, then assert resolution, BEFORE building:**
```bash
# The gateway/launchd wrapper exports secrets/.env in a real fleet build, but an
# isolated agent shell may start clean — so LOAD IT EXPLICITLY first.
set -a; source ~/.openclaw/secrets/.env 2>/dev/null; set +a

# Then assert BOTH the LOCATION PIT and location id resolve. The resolver itself
# also searches the stores, so this fails ONLY if the credential is truly absent.
python3 - <<'PY'
import sys; sys.path.insert(0, "06-ghl-install-pages/tools")
import ghl_media as m
m.resolve_location_pit()   # raises naming every var + store if truly missing
m.resolve_location_id()
print("CREDS OK")
PY
export CAF_ALLOWED_LOCATION_IDS="${GOHIGHLEVEL_LOCATION_ID:-$GHL_LOCATION_ID}"
```

**HARD RULE — real research before any "credential missing" claim.** Before the
build may record ANY credential as missing (an `honest_fail`), it MUST have searched
EVERY known var name across EVERY env store above. `ghl_media.resolve_location_pit()`
/ `resolve_location_id()` already do this (live env across all aliases → then
`secrets/.env` → `clawd/secrets/.env` → `workspace/.env`). An `honest_fail` for a GHL
credential is VALID **only** when that search came back empty, and the recorded
failure MUST name exactly which vars and which stores were checked (the resolver's
RuntimeError message already does — quote it verbatim). "env var empty" is **not**
the same as "credential missing" — if the live env is empty, the env was simply not
loaded; source the store and retry. (Memory rules `client-box-env-stores.md` ("Search
ALL env stores") and `credential-check-live-process-env-first.md` are encoded here.)

### 2.05 Method decision — classify before build (DEFAULT DIRECT; escalate to VERCEL or Skill-44)

Before writing any page blob the build MUST classify each page and record the
decision in `routing/method-decision.json`. Every page entry MUST have a
justified method field.

**Decision table:**

| Page classifier score | Method | What it means |
|---|---|---|
| `SIMPLE` (static content, CSS fits GHL builder, no JS interactivity) | `DIRECT` — native GoHighLevel page blob | HTML fragment in a GoHighLevel code element; §2.06 `general.general.colors` list required |
| `ADVANCED` (rich interactivity, third-party JS, complex CSS that GHL builder overrides) | `VERCEL_EMBED` — build/host on Vercel, iframe into GoHighLevel | See Vercel end-to-end flow below |
| `CALENDAR` / `FORM` / `DATA_PUSH` (needs a real GoHighLevel calendar, form, or CRM write) | `SKILL44_WIDGET` — call Skill 44 to create the GoHighLevel object, embed the GoHighLevel-generated embed snippet | See Skill-44 widget flow below |

`classify_page(page_spec)` (in `tools/ghl_rest_canvas.py`) returns one of
`SIMPLE | ADVANCED | CALENDAR | FORM | DATA_PUSH`. Default is `SIMPLE` — the
build escalates ONLY when the classifier positively scores `ADVANCED` or a
widget type. Do NOT use Vercel for simple pages.

**VERCEL end-to-end (for ADVANCED pages):**
1. `vercel_build.prepare(page_spec)` — bundle the page assets
2. `vercel_build.deploy(bundle)` — deploy; capture the Vercel deployment URL
3. `vercel_build.disable_sso(deployment_url)` — hard gate: the deployment MUST be
   publicly accessible without SSO/auth wall; if the gate fails, halt and flag
4. `vercel_build.assert_embeddable(deployment_url)` — hard gate: `X-Frame-Options`
   must NOT be `SAMEORIGIN`/`DENY`; if the gate fails, halt and flag
5. Generate an iframe snippet via `ghl_method.iframe_embed_snippet(url)`:
   `<iframe src="<deployment_url>" width="100%" ...>`
6. Paste the iframe snippet into a GoHighLevel DIRECT-method code element (the
   page blob still needs the §2.06 theme colors list)
7. (Non-blocking, after the page is live) `ghl_vercel.run_pipeline`'s
   `evidence_root=` hook fires `ghl_github_archive.archive_async` to push the
   same generated files to a per-page GitHub repo, satisfying the operator's
   standing "source always also lives in GitHub" rule. This step runs AFTER
   step 4's embeddability gate passes and can never delay/block/fail steps
   1-6; any archive failure is recorded, not raised. See SKILL.md's
   "VERCEL_EMBED is a direct API upload to Vercel, PLUS a non-blocking GitHub
   archive" note and `tools/ghl_github_reconcile.py` for the later
   confirm-or-retry sweep.

> **IFRAME SURVIVES — CONFIRMED (live probe, 2026-06-27).** A live authenticated
> `/preview/` round-trip rendered `<iframe data-zhc src="…">` elements verbatim
> (2 of 2, `src` intact, no stripping); inline `<script data-zhc>` survived AND
> executed; external `<link rel="stylesheet">` + inline `<style>@import…</style>`
> survived and applied; nothing rendered blank. GoHighLevel's preview renderer
> does NOT sanitize iframes/scripts/CSS in custom-code blocks, so the
> VERCEL_EMBED iframe escape hatch is sound. Do NOT add a sanitizer that bans
> `<iframe>`.

**Skill-44 widget flow (for CALENDAR / FORM / DATA_PUSH pages):**
1. Call Skill 44 (`44-convert-and-flow-operator`) to CREATE the real GoHighLevel
   object (calendar, form, or workflow) — do NOT fake it or use a placeholder
2. Capture the GoHighLevel-generated embed snippet (`form_embed.js` or calendar
   widget JS) from the Skill-44 creation receipt
3. Emit the embed snippet VERBATIM into the page's code element — do NOT add or
   modify `integrity`/`crossorigin` attributes (GoHighLevel rotates the embed
   script and SRI hashes would immediately break it)
4. The GoHighLevel form or calendar object MUST have a creation receipt
   (`status:201`, real id, re-GET 200) in `ecosystem/`; `status:"PLANNED"` is a
   hard FAIL

**`routing/method-decision.json` format:**
```json
[
  {"page_id": "<id>", "page_slug": "<slug>", "classify_score": "SIMPLE",
   "method": "DIRECT", "justification": "static landing page, no JS deps"},
  {"page_id": "<id>", "page_slug": "<slug>", "classify_score": "FORM",
   "method": "SKILL44_WIDGET", "justification": "opt-in form needs CRM write",
   "skill44_receipt": "ecosystem/optin-form.json"}
]
```

This section SUPERSEDES any prior framing that described Vercel as a "manual
last resort" — it is now a first-class, automated, classified path.

---

### 2.06 Theme/colors list — MANDATORY for every page blob

Every page blob POSTed to GoHighLevel MUST carry a populated
`general.general.colors` list. Without it GoHighLevel's renderer reads `.colors`
off `undefined` and returns HTTP 500 — the page cannot display even if bytes
were stored successfully.

> **DOC-TRUTH.** `defaultSettings.colors` does NOT exist in real GoHighLevel
> page blobs (see `ghl_rest_canvas.new_page_blob` docstring). The live render
> path is `general.general.colors`, and the value is an **18-entry list of
> `{label, value}` dicts**, NOT a `{bodyBgColor, btnBgColor, …}` object.

**Required shape (the canonical 18-entry palette — `_FLAT_THEME_COLORS`):**
```json
{
  "general": {
    "general": {
      "colors": [
        {"label": "Transparent", "value": "transparent"},
        {"label": "Primary",     "value": "#37ca37"},
        {"label": "Secondary",   "value": "#188bf6"},
        {"label": "White",       "value": "#ffffff"},
        {"label": "Gray",        "value": "#cbd5e0"},
        {"label": "Black",       "value": "#000000"}
        /* …12 more: Red, Orange, Yellow, Green, Teal, Malibu, Indigo,
           Purple, Pink, Cobalt, Smoke, Overlay — 18 entries total */
      ]
    }
  }
}
```

**Assembly rule (pure, not golden-loaded).** `ghl_rest_canvas.new_page_blob()`
is a **pure, self-contained** function: it assembles the blob from the inlined
`_FLAT_*` constants (`_FLAT_THEME_COLORS`, `_FLAT_PAGE_STYLES`,
`_FLAT_SECTION_METADATA`/`_FLAT_SECTION_GENERAL`) — there is NO file I/O at build
time and it does NOT load a `references/golden/` reference (the golden capture is
historical provenance only). `ghl_rest_canvas.py::assert_renderable` enforces the
invariant that `general.general.colors` is a non-empty list of `{label, value}`
dicts before any save; a theme-less blob never reaches GoHighLevel.

**Per-client brand.** To ship a client palette, call
`ghl_method.build_theme_colors(palette, base=_FLAT_THEME_COLORS)` — it overrides
only the labels the client supplies (case-insensitive: `primary`, `secondary`,
…) and returns the SAME 18-entry list, so the shape GoHighLevel depends on is
preserved. Pair it with `ghl_method.apply_palette_to_page_styles(_FLAT_PAGE_STYLES,
palette)` so the `:root{--primary:…}` CSS variables stay in sync with the colors
list. (Wiring these into `new_page_blob` lives in `ghl_rest_canvas.py`.)

**Fragment rule.** The `rawCustomCode` value inside a code element MUST be an
HTML *fragment* (body-level markup only — `<div>`, `<section>`, etc.). A full
`<!DOCTYPE html>…</html>` document stuffed inside a code element will not parse
into visible builder content and the GoHighLevel editor will show a blank canvas.

**Structure rule.** Elements MUST be nested `section → row → column → element`,
NOT placed directly inside `section.elements`. Flat structure is not recognized
by GoHighLevel's renderer.

---

### 2.07 SEO / AI-search "Content" panel — REQUIRED, gated populated (transcript §2)

After the two saves the transcript fills the **SEO and AI-search optimization →
Content** panel (~09:05–10:16): *"content keywords authors and meta links tags and
canonical links are added — this is really key."* The autonomous REST path now
populates it. The `seoMeta` rides **inside the `pageData` autosave** (no separate
endpoint) and is emitted as an **ordered save step AFTER the page save**.

**How it is wired (no hand-rolling):** pass a `seo` spec to
`ghl_builder.emit_rest_save_plan(..., seo=<spec>)`. The plan then:
1. builds a VALIDATED `seoMeta` via `ghl_builder.build_seo_meta(**seo)` — which
   **HALTs (`SeoValidationError`) before autosave** on any unmet gate;
2. splices it onto the edited blob (`edited["seoMeta"]`) so the page autosave
   persists it; and
3. appends an ordered `seo_apply` step carrying the `seoMeta` + its expectations.

**The gates `build_seo_meta` enforces (transcript + audit overlookedImprovements):**

| Field | Rule (fail-closed) |
|-------|--------------------|
| `title` | non-empty, **≤ 60 chars** (`SEO_TITLE_MAX`) |
| `description` | non-empty, **≤ 160 chars** (`SEO_DESC_MAX`) |
| `keywords` | **RESEARCHED**: ≥ 3 distinct, non-placeholder terms (`SEO_MIN_DISTINCT_KEYWORDS`) — no `[CLIENT TO SUPPLY]`/`keyword`/`lorem` filler |
| `author` | **:= `founder_name`** — the FOUNDER's name (P0/P1 §1.1), never the brand, never blank (`validate_founder_name`) |
| `canonicalUrl` | absolute **`https`**, host = the page's preview/live domain, **NOT** a Firebase/storage host (`_FORBIDDEN_CANONICAL_HOST_FRAGMENTS`) |
| `ogImage` | a GHL media-storage CDN URL that **re-verifies HTTP 200** (reuse the §3 asset-cdn re-verify — the `seo_apply` step's `og_image_http_200` expectation) |
| `language` | set **explicitly `en`** (`SEO_DEFAULT_LANGUAGE`) — never inherit the GHL default |
| `links` / `tags` | absolute http(s) links; non-placeholder tags |
| **`keywords` ∈ copy (H1)** | **each researched keyword MUST actually appear in the page's body copy** (case-insensitive), not only in the meta panel — `ghl_builder.assert_keywords_in_copy(seo_meta, page_copy)` returns the absent keywords; this is the mirror of the copy-fidelity gate (P1-4) in the keyword→copy direction, and a keyword present only in meta is a HARD FAIL |

**Gate the end-state.** `ghl_builder.assert_seo_populated(seo_meta)` (and
`ghl_rest_canvas.assert_seo_populated(page_data, founder_name=...)`) re-assert a
saved `seoMeta` is fully populated with `author == founder_name` — the QC scripts
call this so a build that skipped or stubbed the panel scores a §2 miss. A blank
or placeholder SEO panel is a HARD FAIL, not a warning. **Pass the page's body
copy** as `assert_seo_populated(seo_meta, page_copy=<body text>)` (or call
`ghl_builder.assert_keywords_in_copy(seo_meta, page_copy)` directly) so the **H1
keyword-in-copy gate** fires: every researched keyword must appear in the visible
copy, or each absent keyword folds into the fail `reasons`. The check is OPT-IN
(omit `page_copy` to skip it) so existing callers are unaffected; the build path
supplies the copy so keyword-stuffed meta cannot silently pass.

---

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

   **IDEMPOTENT RE-INSTALL (no duplicates).** Before creating a NEW page, list
   the sub-account's existing pages and call
   `ghl_method.resolve_install_target(existing_pages, marker, page_name=…)`. If
   an existing page already carries the page's **stable** ZHC marker (in its
   marker field or stored HTML), it returns `action="update"` with that
   `page_id` — re-install IN PLACE over it instead of creating a duplicate. Use
   a STABLE marker derived from the funnel/page slug (NOT a per-run nonce) so
   re-runs converge on the same page. More than one page carrying the same
   marker raises `InstallTargetError` (a prior run left duplicates → halt for
   manual cleanup, never guess).
3. **edit** — `edit_element_customcode(blob, {section_idx, element_idx}, new_html)`
   where `new_html` carries the page marker **and the real `<img src="<CDN
   url>">`** from §3. Pure splice; the pristine blob is kept as the revert
   baseline.
4. **page_autosave** — POST the edited blob as a **DRAFT**
   (`publish=may_publish(approval)`, default DRAFT; `pageVersion` numeric n+1;
   `pageType:"draft"` keeps the live pointer put). Expect **201**.
5. **verify_preview** — `ghl_verify.render_check(preview_url, marker)` → HTTP 200
   AND marker present in the **RENDERED (hydrated) DOM**, AND zero render errors,
   captured as real DOM snapshot + PNG screenshot + browser console artifacts.
   Advances the ledger to `previewed` **only** on all three conditions.

   **COPY-FIDELITY (P1-4).** Pass the page's approved copy to `verify_page` via
   `copy_tokens` (a list of approved phrases) or `copy_md_path` (the APPROVED
   copy.md from P2). `ghl_verify` then asserts every approved copy token appears
   in the rendered visible text (scripts/styles stripped); a missing token folds
   into `render_errors` → PASS False. This catches a page that renders 200 +
   marker but ships stale/placeholder copy instead of the approved P2 copy. The
   gate is opt-in — omit the tokens to skip it (marker-only verify, unchanged).

   **EXPLICITLY NOT ACCEPTABLE as pass criteria:**
   - Raw HTTP shell returning 200 (does not load the JavaScript-rendered page)
   - Marker found in stored blob / Firebase bytes (proves storage, NOT render)
   - Hand-written ledger entry or `.md` file claiming the page verified
   - Any non-200 HTTP status re-labeled as an "API difference"

   Every page MUST produce on-disk artifacts: `<step>-preview.html` (real fetched
   DOM), `<step>-preview-desktop.png` (1440×900), `<step>-preview-mobile.png`
   (390×844), `<step>-console.json` (browser console, zero errors required).
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

**Credential prerequisite (DO §2.0.1 FIRST).** The image step needs the LOCATION
PIT + location id + `KIE_API_KEY` resolved. These live in the env stores per the
§2.0.1 table; the image pipeline resolves them via
`ghl_media.resolve_location_pit()` / `resolve_location_id()`, which search EVERY
known alias across the live env AND the stores (`~/.openclaw/secrets/.env` →
`~/clawd/secrets/.env` → `~/.openclaw/workspace/.env`) before declaring anything
missing. A "GHL LOCATION PIT not found" honest_fail is VALID **only** when that
search came back empty — and the error already names every var + store it checked.
If the live env is empty, the store was simply not sourced; run the §2.0.1 step-0
`source ~/.openclaw/secrets/.env` and retry — NEVER record the credential as
missing on an empty env var alone (that was the six-month false-fail bug).

The dispatcher invokes the image pipeline via the NAMED callable entrypoint
(`run_image_pipeline` in `tools/ghl_image_stage.py`) — it MUST NOT hand-roll an
image loop or call `kie_generate.py` directly:

```python
import sys; sys.path.insert(0, "06-ghl-install-pages/tools")
from ghl_image_stage import run_image_pipeline   # raises ImagePipelineError on failure

result = run_image_pipeline(
    page_spec,                 # the per-page spec (copy + page_id + optional images[])
    RUN_DIR,                   # evidence root — writes images/ + logs/ subtrees
    location_id=None,          # None → resolved from env/stores (operator fixture)
    location_pit=None,         # None → resolved from env/stores (LOCATION PIT, never agency)
)
# result["manifest"] = [{id, prompt, file, cdn_url(https), cdn_http_status:200, used_on_page_id}]
# result["ok"] is False (with an honest error + a FAIL manifest record) on any failure —
# it NEVER returns a synthetic/stub cdn_url, file://, or SVG placeholder.
```

**Media-storage folder discipline (transcript §3, ~01:14–02:42 — the per-build
STEP).** Trevor's rule: **one clearly-named folder per funnel/website, with
per-page subfolders as needed** ("clear organization is the main point"). Media
storage and the media library are the SAME area (Trevor uses both names). Create
the structure ONCE per build, BEFORE the upload stage, via
`ghl_media.ensure_funnel_media_folders(funnel_name, location_id, pit,
page_names=[...])` — it makes the funnel folder + a subfolder per page on the
`services.*` + Bearer **LOCATION**-PIT path (the same auth split as upload), and
**NO browser control** is ever used for media (API / MCP / Skill 44 only). Pass
the returned per-page `folderId` as `upload_media(parent_id=...)` so each page's
images land in its subfolder. **Fail-soft:** if the GHL plan exposes no folder
endpoint, the wrapper returns `mode:"name-prefix"` and the images stay grouped via
`media_folder_name_prefix(...)` prepended to each file name (still findable).

Internally `run_image_pipeline` executes four stages in order:

1. **Generate** real PNGs from copy-derived prompts via the repo's verified
   generator (`23-ai-workforce-blueprint/templates/presentation-render/
   kie_generate.py`, `mode:"t2i"` when there is no logo to seed) — it submits to
   `api.kie.ai`, polls, downloads, and **verifies PNG magic bytes** (`b"\x89PNG"`,
   FAIL-LOUD on non-PNG). Requires `KIE_API_KEY` resolved per §2.0.1; **if truly
   absent (after the store search) → honest FAIL recorded in
   `images/manifest.json`, never an SVG stub.**
2. **Upload** each PNG (into the funnel's media folder / per-page subfolder from
   the discipline step above) via `tools/ghl_media.py`
   (`POST services.leadconnectorhq.com/medias/upload-file`, **Bearer LOCATION
   PIT** — the agency PIT 401s, `Version: 2021-07-28`) → capture
   `{fileId, public url}`. **Auth-model split:** media upload is the `services.*`
   origin with a Bearer PIT — **bare Python OK** (NOT the Cloudflare-1010-gated
   funnels-builder origin).
3. **Re-verify** each CDN URL is a genuine HTTP 200 and log it to
   `logs/asset-cdn.log` (real `status=200 | <https url> | OK` lines — kill the
   `LOCAL-SVG-PLACEHOLDER` line). A non-200 CDN URL raises `ImagePipelineError`.
4. **Reference** the public CDN `<img>` in-page via the §2 splice (step 3 above).

`images/manifest.json` maps `{id, prompt, file, cdn_url(https),
cdn_http_status:200, used_on_page_id}` — **no `file://`, no placeholder note.**

**Un-fakeable gate:** After the page is saved and `ghl_verify.render_check` runs,
the rendered DOM artifact MUST contain the `<img src="...">` tag pointing to a
GoHighLevel CDN URL. If the image `src` does not appear in the RENDERED body, the
page is FAIL — the image is confirmed only in the rendered page, not in stored bytes.

(T2 owns `ghl_media.py` + the manifest contract; T4 adds `ghl_image_stage.py` as
the dispatcher-facing entrypoint; this SOP pins that the dept agent USES them
rather than stubbing.)

---

## 4. Ecosystem (R5) — real objects + a form→CRM proof

Pre-req (resolved by the §2.0.1 credential preflight — do that step 0 first):
`export CAF_ALLOWED_LOCATION_IDS="${GOHIGHLEVEL_LOCATION_ID:-$GHL_LOCATION_ID}"`
(the configured GHL location id) + the **LOCATION** PIT (`GOHIGHLEVEL_API_KEY`,
never the agency PIT) so the Skill-44 safety gate passes. If either is empty,
`source ~/.openclaw/secrets/.env` first — they live there per the §2.0.1 table;
do NOT declare them missing on an empty env var alone. **Auth-model split:**
calendars / products / forms / contacts are the `services.*` origin + Bearer PIT —
**bare Python OK** (the Skill-44 CLI), NOT the WAF-gated funnels origin.

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

### 4.1 Embed widget flow — how GoHighLevel objects land on pages

When the §2.05 method decision routes a page to `SKILL44_WIDGET`, the ecosystem
object creation (above) MUST precede the page splice:

1. **Create** the GoHighLevel object via Skill 44 (calendar, form, or workflow
   trigger). Capture the creation receipt: `status:201`, live `id`, re-GET 200.
   Write to `ecosystem/<type>.json`.
2. **Extract the embed snippet** from the Skill-44 receipt. GoHighLevel provides
   a `form_embed.js` URL (for forms) or a calendar widget JS tag. Use the snippet
   verbatim — do NOT invent your own embed code and do NOT add `integrity` or
   `crossorigin` attributes (GoHighLevel rotates the embed script; SRI hashes
   break immediately on the next GoHighLevel deploy).
3. **Splice** the embed snippet into the page blob's code element via the §2.1–2.6
   edit step — the same REST autosave path. The page blob MUST still carry the
   §2.06 theme/colors object.
4. **Verify** that the rendered page (via `ghl_verify.render_check`) loads the
   embed snippet tag in the hydrated DOM — the `src` attribute of the script/iframe
   tag must appear in the rendered body. This is confirmed by `render_check`'s DOM
   artifact, not by storage grep.
5. **Never fake a GoHighLevel object.** If Skill 44 returns an error, the build
   records an honest FAIL for that page — it does NOT substitute a static HTML
   mock of a form or calendar.

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

## 7. The ONE canonical verifier — sealed-mode contract (R7)

V2 uses `tools/ghl_verify.py` exclusively. The verdict is a machine-only output.

**The sealed-mode contract (production runs MUST use `live=True`):**

```
python3 06-ghl-install-pages/tools/ghl_builder.py verify-all <RUN> <RUN>/pages.json \
    --run-id <id> --version client-agent --brand "<fictional brand>" --live
```

- The `--live` flag sets `live=True` in `ghl_verify`; a mock verifier or any
  verifier instance with `live=False` is REJECTED in a real production run with
  a non-zero exit. A `trust:"MOCK"` entry in any summary CAN NEVER SHIP.
- writes `logs/final-preview-verify.json` (raw per-page `render_check` results —
  HTTP status, marker-in-rendered-DOM boolean, render-error count, artifact paths)
  **FIRST**; this is the ONLY authoritative source of truth;
- derives `scorecard/verify-summary.json` STRICTLY by reducing that array
  (`passed = sum(1 for r if r.render_pass)`); the summary CAN NEVER claim more
  than the raw log (`ghl_verify.assert_consistent` raises `VerifyContradiction`
  and exits non-zero if the summary is more optimistic than the evidence);
- exits non-zero on `overall_pass:false` — a failing/partial build cannot read as
  success;
- the dispatcher marks the task `verified` ONLY by reading `scorecard/verify-summary.json`
  written by `ghl_verify` — NOT by reading any ledger, `.md` file, or hand-assembled
  JSON. Ledgers and `.md` files are non-authoritative for the verdict and are
  ignored by the gate reader;
- `ghl_gate require-pass` is the ONLY mechanism that asserts the final verdict;
  the dispatcher MUST call it before marking `verified`.

`pages.json` is the list the dept agent built (each `{step, page_id,
preview_url, marker}`).

---

## 7.1 Forbidden verification shortcuts

Each item below is a banned shortcut. The code guard that now rejects it is noted.

| Shortcut | Why it fails | Code guard that rejects it |
|---|---|---|
| Marker found in stored Firebase blob | Proves bytes were stored; the page can 500 on load | `ghl_verify.render_check` — only checks the rendered DOM |
| Marker found via raw HTTP shell (`curl`/`requests`) | Does not execute JavaScript; GoHighLevel pages need JS to render | `ghl_verify` requires a headless browser render pass |
| Hand-written ledger or `.md` declaring PASS | Any human can write any string; not machine-derived | `ghl_gate require-pass` reads ONLY `scorecard/verify-summary.json` from `ghl_verify` |
| Re-labeling HTTP 500 (or any non-200) as "API difference" | A non-200 is a render failure, full stop | `ghl_verify.render_check` treats any non-200 as `render_pass:false`, hard FAIL |
| Re-using a mock verifier (`live=False`) in a real run | Mock returns a pre-canned answer, not a real page load | `--live` flag; `ghl_verify` exits non-zero if `trust=="MOCK"` in output |
| Independent re-verifier that reads storage instead of loading the page | Same as marker-in-blob — does not detect 500s | The independent verifier MUST call `ghl_verify.render_check`, not a grep |
| **"Credential not found" on an empty env var without searching the stores** | The token may be sitting in `secrets/.env`; an empty env var means "not loaded", not "missing" (the six-month false-fail) | `ghl_media.resolve_location_pit/id` search every alias × every store first, and name what they checked (§2.0.1) |

**No build can self-declare PASS.** The producer runs `ghl_verify`; `ghl_verify`
writes `scorecard/verify-summary.json`; `ghl_gate require-pass` reads it. Those
three steps are the only path to a PASS verdict. Skipping any step = FAIL.

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
2a. each page's `seoMeta` is **populated + validated** (§2.07): title ≤ 60,
   description ≤ 160, ≥ 3 researched keywords **each appearing in the page body
   copy (H1 keyword-in-copy gate)**, **author == the intake `founder_name`**,
   `https` canonical on the page's own domain, `ogImage` 200, `language == "en"` —
   `ghl_builder.assert_seo_populated(seo_meta, page_copy=<body text>)` passes (the
   `page_copy` arg fires the keyword-in-copy gate; keywords stuffed only in meta
   are a FAIL — a blank/stub SEO panel is a FAIL, not a warning);
2b. the build's media lives under **one named funnel folder (+ per-page subfolders
   where used)** created via `ghl_media.ensure_funnel_media_folders` on the
   non-browser `services.*` path (§3), or the `name-prefix` fallback when the plan
   has no folder endpoint;
3. the ecosystem objects are real creation receipts incl. the form→CRM
   roundtrip proof (§4);
4. telemetry is scrubbed and the `--check` gate is clean (§6);
5. evidence is under `skill6-fix/v2-<RUN_ID>/`, no conflation (§8);
6. the verdict (`overall_pass`) is whatever the raw log proves — a sub-8.5 result
   is reported as FAIL, never massaged;
7. **BUILD-QC GATE (FAB-QC ≥ 8.5).** The library-aware build-quality gate
   `qc-built-funnel.sh <slug>` (shared scorer `shared-utils/fab_qc.py`, rubric
   `universal-sops/funnel-automation-build-quality-rubric.md`) scores the build on the
   six dimensions — template fidelity, copy substance (no surviving placeholders),
   render/soundness (the §7 `ghl_verify` scorecard is the hard floor), persona grounding,
   flexibility honored (the persisted `routing/match-decision.json`), funnel↔automation
   link integrity — and returns ≥ 8.5. This is a SUPERSET overlay on top of the canonical
   `ghl_verify` floor; a build below 8.5 is NOT done. Both numbers are surfaced.

   **The FAB-artifact PRODUCER makes this gate fire on a REAL build.** FAB-QC scores
   `build/fab-artifact.json`. The dispatcher PRODUCES that file from the real build result:
   right after the verifier passes (and before the FAB gate), `dispatch_one` calls
   `_emit_fab_artifact()` → `shared-utils/fab_artifact.build_funnel_artifact(task, build)`,
   normalising the matched `funnel_template_id`, the built pages, the **actual copy the
   builder wrote**, the flex decision, and the attached `linked_automations` into the
   artifact shape the scorer reads. It runs only on a template-aware build (a
   `routing/match-decision.json` receipt from STEP 0 exists) and never clobbers an
   artifact already on disk. **Builder contract:** the injected builder MUST echo the copy
   it pushed per page (`build['pages'][i]['copy']`, or loose `headline`/`body`/`cta`/text
   `blocks`) so the producer can hand real copy to D2 — a build that echoes no copy is
   correctly failed as thin by D2 (fail-closed, by design). Without this producer the FAB
   gate had nothing to score and was a silent no-op on every real funnel build.

Going live (a real public domain) remains a CLIENT Connect-Domain step and is
NOT automated; preview URLs + draft saves are the bar.
```
