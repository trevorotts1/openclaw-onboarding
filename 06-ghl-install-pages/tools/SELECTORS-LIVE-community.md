# SELECTORS-LIVE — COMMUNITY / GROUP + CHANNELS builder (`ghl_community_builder.py`)

**Status:** ⚠️ **CAPTURE-PENDING** (NOT yet locked). The live selector-capture run
for communities has **not** been fully performed — see §Block + §Live-capture below.
Per **D8 (zero invented selectors)** this doc records what is VERIFIED for the shared
leadconnectorhq rail, the anchor VALUES OBSERVED in the 2026-07-10 live-capture attempt
(recorded, not yet LOCKed), plus the exact capture procedure to LOCK the rest. The
machine-readable companion the builder loads is
`selectors-live-communities-courses.json` (every in-area target there is
`status:"capture-pending"`; a REQUIRED capture-pending anchor makes the live build
STOP-and-report — it never guesses CSS).

## Phase A (2026-07-10) — the builders are now agent-browser 0.27.0 LIVE-READY

The 2026-07-10 live-capture attempt found real DOM anchors but also 5 code/reality gaps
that would stop a live build even with anchors locked. Phase A (branch
`skill6-community-course-live-ready`, offline code only) closes all 5 so Phase B is a
pure capture-then-run:

- **(a) anchor→executor resolver** (`tools/ghl_ab_executor.py`): agent-browser 0.27.0
  `click`/`fill` REJECT Playwright `getByRole/getByText/getByPlaceholder` strings. The
  resolver translates every anchor into the accepted `find <locator> <value> <action>
  [--name]` call, plus a **native DOM `.click()` via eval** for the Naive-UI submits
  ("Create Group", "CREATE CHANNEL") where `find … click`/`click @ref` report Done but
  do NOT submit. Dynamic values are `shlex.quote`d so a multi-word `--name` survives the
  `browser_cmd` space-join + `shlex.split` re-parse. `exec:"native"` in the JSON marks
  the submit anchors. Both builders route every click/fill through it.
- **(b) list-scan idempotency**: the communities list has **NO search box** (captured
  live). Idempotency is a **list-scan** (`_list_has` — enumerate the rendered group list,
  match by name/slug), not a search-box type. The false `list_page.search_box`,
  `row_actions`, `delete_menuitem` community anchors are removed.
- **(c) group identity = slug + white-label portal host** (`_capture_group_identity`):
  after Create the SPA lands on `https://<portal_host>/communities/groups/<slug>/home`;
  groups are keyed by **SLUG** (no opaque id in the route; the Tier-2 `validate_group_slug`
  tool independently confirms slug keying).
- **(d) HONEST no-group-delete**: GHL community GROUPS have **NO delete** on any known
  rail — not in the UI (only Active↔Inactive), and **NOT** on Tier-1 (36) or Tier-2 (588
  community-MCP) tool lists (no `delete_community`/`delete_group`/`delete_channel`; only
  `validate_group_slug`). Literal 0-residue is impossible for a group → cleanup =
  `_deactivate_group` (set **Inactive**, documented residue, **not a fake delete**). The
  true 0-residue proof is scoped to **COURSES**, which ARE deletable (Tier-2
  `delete_course*` + the row "More actions" menu).
- **(e) render-check on the right URL**: PUBLIC group → anonymous `render_check` on the
  derived member-visible portal URL; PRIVATE group → authenticated in-session portal
  check (an anonymous fetch hits the login wall).

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

Anchors marked **OBSERVED** were seen in the 2026-07-10 live-capture attempt and are
recorded in the JSON `anchor`/`observed` fields (status still `capture-pending` — Phase B
LOCKs them via the full create-then-deactivate procedure).

| Surface | Target | OBSERVED value / capture recipe |
|---|---|---|
| Route | communities list route | **OBSERVED** `/v2/location/<LOC>/memberships/communities/community-groups` (top document under app.convertandflow.com — NOT an iframe; only the chat widget is an iframe). Reached via Memberships → "Communities" sub-nav. |
| Route | group portal + identity | **OBSERVED** post-create URL `https://<portal_host>/communities/groups/<slug>/home`; keyed by **SLUG** (e.g. `zhc-capture-probe-c6`) — NO opaque id (fix c) |
| List | (search box) | **NONE** — the communities list has NO search box (fix b: list-scan idempotency, not search) |
| List | Create-Group button | **OBSERVED** `getByRole('button',{name:'Create Group'})` → opens a **FULL PAGE** `/memberships/communities/create-group` (not a modal) |
| Create page | name / slug / description | **OBSERVED** `getByPlaceholder('Group Name')`, `getByPlaceholder('Group Slug')` (auto), `getByPlaceholder('Enter a brief description')` |
| Create page | privacy | **OBSERVED** a switch (default = **PUBLIC**); settings radios "Public/Private Group Radio Button" |
| Create page | Create confirm | **OBSERVED** `getByRole('button',{name:'Create Group'})` — **Naive-UI submit → `exec:native`** (find/@ref click do NOT submit; native `.click()` fires the toast) |
| Group nav | **Add-Channel** control | **OBSERVED** `+ Add Channel` button (`getByRole('button',{name:'Add Channel'})`) |
| Group nav | channel name / description / confirm | **OBSERVED** `getByPlaceholder('e.g Marketing Reports')`, `getByPlaceholder('Enter Description')`, confirm `CREATE CHANNEL` (**`exec:native`**) |
| Group settings | Active↔Inactive status toggle (cleanup — fix d) | capture the group-Settings status toggle; **there is NO delete** (documented residue) |

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
7. **CLEANUP = set Inactive** (fix d — GHL has NO group delete on any known rail): open
   the scratch group's Settings and toggle status → Inactive; record that toggle anchor.
   The group ROW/portal REMAINS — this is documented residue, NOT a fake delete. (The
   true 0-residue delete proof lives in the COURSE capture, which IS deletable.)
8. Flip each captured target in `selectors-live-communities-courses.json` from
   `capture-pending` → `locked` with its real `anchor` + `conf` (keep the `exec:native`
   hints on the two submit anchors); update §2 here. Self-grade ≥ 8.5 (routes+nav+create,
   channel flow, honest Inactive cleanup, no invented selectors) like SELECTORS-LIVE-survey.md.

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
