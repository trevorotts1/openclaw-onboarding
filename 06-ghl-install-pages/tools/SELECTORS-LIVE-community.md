# SELECTORS-LIVE — COMMUNITY / GROUP + CHANNELS builder (`ghl_community_builder.py`)

**Status:** ⚠️ **CAPTURE-PENDING** (NOT yet locked). The live selector-capture run
for communities has **not** been performed — see §Block below. Per **D8 (zero
invented selectors)** this doc records ONLY what is VERIFIED for the shared
leadconnectorhq rail, plus the exact capture procedure to LOCK the rest. The
machine-readable companion the builder loads is
`selectors-live-communities-courses.json` (every in-area target there is
`status:"capture-pending"`; a REQUIRED capture-pending anchor makes the live build
STOP-and-report — it never guesses CSS).

> Convert and Flow = Go High Level = GHL. Communities/Courses live under the left-rail
> **Memberships** area (VERIFIED — `references/form-click-map.md` global-rail capture;
> spec §5). 🔒 location id + client names redacted on capture.

## Block — why this is CAPTURE-PENDING and not LOCKED

The capture run requires the singleton agent-browser on the operator box. At build
time that box was **PARKED** (circuit-breaker durable marker, `location=abortloc`,
tripped 6 opens / 7200 s) with **39 live browser processes** from concurrent Skill-6
agents. The browser is a hard SERIAL singleton (`browser_manager.sh`); forcing a
capture into 39 concurrent sessions would violate serialization and corrupt sibling
runs, and un-park is operator-only. Auth itself is healthy (token mints, len 951;
`agent-browser 0.27.0` matches the pin) — **only** the box contention blocks capture.
Re-run the procedure below when the box is free (or on a private test box).

## 1. VERIFIED shared-rail facts (safe to act on)

| Fact | Anchor | Conf | Source |
|---|---|---|---|
| Left-rail **Memberships** entry (StaticText, like Sites) | `getByText('Memberships')` | 8.0 | form-click-map global-rail capture; spec §5 |
| Sites → **Client Portal ▾** exists | `getByText('Client Portal')` | 7.5 | SELECTORS-LIVE-form.md §2; spec §5 |
| ZHC naming on the group name | `ensure_zhc_name` → `ZHC <name>` | — | skill convention |
| Search-first idempotency (list pages have a search box) | pattern (forms/surveys locked) | — | F14; SELECTORS-LIVE-form/survey §2 |
| Builder canvas is a cross-origin `*.leadconnectorhq.com` iframe (IF the community editor is that iframe — **ASSUMED**, capture confirms) | — | — | shared-rail constraint |

## 2. CAPTURE-PENDING targets (the capture run must LOCK each)

Each row: what to capture and the ordered **fallback chain** (a capture RECIPE, NOT
a fact — never hardcode a fallback as a locked anchor). Full machine list in the JSON.

| Surface | Target | Capture recipe (ordered fallbacks) |
|---|---|---|
| Route | communities list route segment | reach via Memberships → Communities/Groups tab (`getByText`); **never** deep-link |
| Route | group-builder route + `GROUP_ID` shape | capture id from `location.href` / iframe `.src` (form ids are `[A-Za-z0-9]{15,30}`) |
| List | search box placeholder | `getByPlaceholder('Search…')` → list-header `textbox` |
| List | Create-Group button **name** (UNKNOWN: forms="Create form", surveys="Add survey") | `getByRole('button',{name:/Create\|Add\|New.*(Group\|Community)/})` → `getByText` |
| List | row Actions → Delete → confirm | `getByRole('button',{name:'Actions'})` → `menuitem 'Delete'` → dialog `Delete` |
| Modal | name / description inputs | `getByPlaceholder` → dialog `textbox`/`textarea` |
| Modal | privacy control shape (radio/switch/dropdown) | `getByText('Private')` → the public/private control |
| Modal | Create confirm | `getByRole('button',{name:'Create'})` → dialog primary |
| Group nav | **Add-Channel** control (least-known surface) | `getByRole('button',{name:'Add Channel'})` → `+` header icon (SVG path-d + order) → `getByText` |
| Group nav | channel name input + Create confirm | `getByPlaceholder('Channel name')` → dialog `textbox` + primary |

## 3. §capture_procedure (run to LOCK — mirrors the 2026-07-02 form/survey runs)

1. Confirm the box is FREE and NOT parked: `ls ~/.openclaw/workspace/.park/` shows no
   `*.parked` / `*.BLOCKED`; no live `agent-browser` processes; else STOP.
2. Bring up the token-only seeded session (headless, singleton gateway) to the
   operator **test** sub-account — reuse `ghl_form_builder._seed_and_land` (never a
   login form). Confirm `app:` (logged-in), not `login:`.
3. Left-rail **Memberships** (`getByText`) → snapshot `-i --json`; record the
   Communities/Groups nav + list route from `location.pathname`.
4. Search box: type a probe; record its placeholder/role. Create **one scratch group**
   `ZHC Capture Probe` → record every create-modal field anchor + the privacy control
   shape + the Create button's exact role+name.
5. From the created group capture `GROUP_ID` (`location.href` / iframe `.src`); record
   the public/client-portal URL shape (needed for `render_check`).
6. Add **one scratch channel**; record the Add-Channel trigger + the channel modal +
   how the channel appears in the group nav snapshot (the idempotency read-back).
7. **DELETE** the scratch group (search → Actions → Delete → confirm); snapshot proves
   **0 residue**.
8. Flip each captured target in `selectors-live-communities-courses.json` from
   `capture-pending` → `locked` with its real `anchor` + `conf`; update §2 here.
   Self-grade ≥ 8.5 (routes+nav+create+delete, channel flow, cleanup 0 residue, no
   invented selectors) exactly like SELECTORS-LIVE-survey.md.

## Self-grade (of THIS capture-pending scaffold)

| Criterion | /10 |
|---|---|
| Honesty (no invented selectors; block stated) | 10 |
| VERIFIED shared-rail facts cited | 9 |
| Capture procedure completeness (LOCK-ready) | 9 |
| In-area coverage | n/a — deferred to capture by design |

**Overall (scaffold): honest CAPTURE-PENDING.** The builder + QC gate are complete and
proven in dry-run/selftest; the live path STOP-and-reports at the first capture-pending
REQUIRED anchor until this doc is LOCKED by the procedure above.
