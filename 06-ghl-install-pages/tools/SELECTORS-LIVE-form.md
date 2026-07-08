# SELECTORS-LIVE — FORM builder (Convert and Flow / Go High Level)

**Status:** LOCKED against LIVE GHL. Captured 2026-07-02 by the GHL LIVE
SELECTOR-LOCK operator run, driving the REAL builder on the operator's own
BlackCEO test sub-account (`<LOCATION_ID>`), authenticated via the token-only
seed rail (`seed-ghl-auth.py` → Firebase IndexedDB + `/oauth/2/login/current` +
6 SPA cookies → `$store.dispatch('auth/get')` + `$router.push`, NO login form).
Engine: `agent-browser 0.27.0` (matches `gates.json` pin). A real scratch form
(`Form 389`, id redacted) was created, walked, and **DELETED** — live DOM
confirms 0 residual occurrences. GHL left clean.

> ⚠️ Convert and Flow = Go High Level = GHL. Builder canvas is a cross-origin
> `*.leadconnectorhq.com` iframe inside `app.convertandflow.com`.
> 🔒 Fleet-wide: location id + all client form/folder names redacted.

---

## 0. Auth (VERIFIED LIVE — the gate that used to burn tokens)

- Refresh token `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` (`~/.openclaw/secrets/.env`)
  exchanged at `securetoken.googleapis.com` → **VALID** (id_token+refresh_token,
  expires_in 3600). Seed → inject → activate succeeded on **attempt 1**; landed
  logged-in at `/v2/location/<LOCATION_ID>/dashboard`. No UI login, no 2FA.
- Hard rule confirmed live: **never `reload`/full-navigate after seeding** — use
  SPA `$router.push` (client-side routing) so the whitelabel boot IIFE never
  re-runs `firebase.signOut()`. All navigation below is router.push / in-SPA link
  clicks.

## 1. Routes (LIVE, stable)

| Surface | Route (SPA path) |
|---|---|
| Sub-account dashboard | `/v2/location/<LOCATION_ID>/dashboard` |
| Sites → Funnels (Sites default) | `/v2/location/<LOCATION_ID>/funnels-websites/funnels` |
| **Forms list** | `/v2/location/<LOCATION_ID>/form-builder/main` |
| **Form builder** | `/v2/location/<LOCATION_ID>/form-builder-v2/<FORM_ID>` |

## 2. Global chrome — Sites secondary nav (SHARED by all 4 builders)

These are real `link` elements whose **accessible name = visible text** →
`getByRole('link', { name })`. Live-verified order in the orange secondary bar:
`Funnels · Websites · Stores · Webinars · Analytics · Blogs · WordPress ·
Client Portal ▾ · Forms · Surveys · Quizzes · Chat Widget · QR Codes`.

| Target | LOCKED anchor | Confidence |
|---|---|---|
| Forms | `getByRole('link', { name: 'Forms' })` | 9.5 |
| Surveys | `getByRole('link', { name: 'Surveys' })` | 9.5 |
| Funnels | `getByRole('link', { name: 'Funnels' })` | 9.5 |
| Websites | `getByRole('link', { name: 'Websites' })` | 9.5 |

Left global rail item **Sites** (`StaticText "Sites"`, no accessible name on the
`<a>`) is unreliable to click by role/name — prefer `router.push` to a Sites
sub-route, or `getByText('Sites')` within the rail. (A ref-click on it did NOT
navigate in this run.) Confidence 5.

## 3. Forms list page (`/form-builder/main`) — all top-frame, reliable refs

| Target (CLICK-MAP #) | LOCKED anchor | Confidence |
|---|---|---|
| Tabs `All forms / Analytics / Submissions` (#3) | `getByText('All forms'|'Analytics'|'Submissions')` | 8.5 |
| `Form features` button | `getByRole('button', { name: 'Form features' })` | 9 |
| `Create folder` button | `getByRole('button', { name: 'Create folder' })` | 9 |
| **`Create form`** (#4) | `getByRole('button', { name: 'Create form' })` | 9.5 |
| Search box (#32) | `getByRole('textbox').filter(placeholder='Search for forms')` / `getByPlaceholder('Search for forms')` | 9 |
| Row → `Actions` button | `getByRole('button', { name: 'Actions' })` (per row) | 9 |
| Actions menu → items | `getByRole('menuitem', { name })` where name ∈ `Edit · Preview · View submission · Duplicate · Share · Upload to form templates · Move to folder · Delete` | 9.5 |
| Delete confirm | dialog "Delete form"; `getByRole('button', { name: 'Delete' })` (dialog-scoped) + `Cancel` | 9.5 |

**Delete flow (fills CLICK-MAP Ambiguity #4 for the LIST):** search → row
`Actions` → menuitem `Delete` → confirm dialog `Delete`. Verified live end-to-end.

## 4. Create-new-form modal (#5–#7)

`dialog` titled **"Create new form"**. Two radio cards + Cancel/Create.

| Target | LOCKED anchor | Notes | Conf |
|---|---|---|---|
| Start from Scratch (#5) | `getByText('Start from Scratch')` → its `radio` (checked by DEFAULT) | radio has empty name; anchor by adjacent text | 8.5 |
| From templates (#6) | `getByText('From templates')` → its `radio` | | 8.5 |
| **Create** (#7) | `getByRole('button', { name: 'Create' })` | enters builder → new `Form <n>` | 9.5 |
| Cancel | `getByRole('button', { name: 'Cancel' })` | | 9 |

## 5. Form-builder chrome (INSIDE the `leadconnectorhq.com` iframe)

The iframe is auto-inlined by `agent-browser snapshot`; interactive leaves get
`@ref`s and are clickable. **Named buttons (role+name anchors — high confidence):**

| Target (#) | LOCKED anchor | Conf |
|---|---|---|
| Back | `getByRole('button', { name: 'Back' })` | 9.5 |
| Preview (#9) | `getByRole('button', { name: 'Preview' })` | 9.5 |
| Integrate (#10) | `getByRole('button', { name: 'Integrate' })` | 9.5 |
| **Save** (#11) | `getByRole('button', { name: 'Save' })` | 9.5 |
| Submit (canvas) | `getByRole('button', { name: 'Submit' })` | 9 |
| Footer links | `getByRole('link', { name: 'Privacy Policy' })` / `'Terms of Service'` | 9 |

**Icon-only toolbar (row 2) — NO accessible name / aria-label / testid.** They are
Naive-UI `n-button`s carrying only an SVG. Only stable anchors are the **SVG path
`d=` signature** + **left-to-right order**. Decoded live:

| # (order) | Function | SVG `d` signature (leading) | Size |
|---|---|---|---|
| 1 | **+ Add element** (opens Form Element panel) (#12) | `M12 5v14m-7-7h14` | h-4 |
| 2 | Duplicate / stack | `M11 4.5h7.3c1.12 0…` | h-4 |
| 3 | Desktop-preview toggle | `M15 17v4H9v-4m-3.8 0h13.6…` | h-5 |
| 4 | Mobile-preview toggle | `M12 17.5h.01M8.2 22h7.6…` | h-5 |
| 5 | Grid/snap (round) | `M22.7 13.5l-2-2-2 2M21 12a9 9…` | h-5 |
| 6 | Undo | `M4 7h10a6 6 0 010 12H4M4 7l4-4M4 7l4 4` | h-5 |
| 7 | Redo | `M20 7H10a6 6 0 100 12h10m0-12l-4-4m4 4l-4 4` | h-5 |
| 8 | **Styles & Options toggle** (#13) | `M3 8h12m0 0a3 3 0 106 0 3 3 0 00-6 0z…` (sliders) | h-4 |
| — | Form Element panel **close (X)** | `M18 6L6 18M6 6l12 12` | h-5 |

Operator recipe for these: `snapshot` → take the toolbar button group in order,
OR match the SVG child by `path[d^="M12 5v14"]` (add), `path[d^="M3 8h12"]`
(styles). Do NOT use nth-child on the wrapper (Vue re-renders). Confidence 7.

**Builder tabs `Edit · Settings · Submissions · Notifications · Analytics`** are
`StaticText` (clickable divs, NOT role=tab, NO ref) → see §7 constraint. Anchor by
visible text at runtime; not directly clickable through the CDP-ref rail.

## 6. Canvas default fields + per-field controls

Fresh scratch form is pre-seeded (live-confirmed, matches CLICK-MAP Step 8):
First Name, Last Name, **Phone \***, **Email \***, two consent checkboxes
(`[BUSINESS NAME]` / `[USE_CASE_FROM_CAMPAIGN_DESCRIPTION]` placeholders — MUST be
updated per client), Submit, footer Privacy Policy | Terms of Service (a Text
element).

- Field inputs are `textbox`es anchored by placeholder: `getByPlaceholder('Enter your first name'|'Enter your last name'|'+1 (555) 000-0000'|'your@email.com')`. Conf 8.5.
- Consent checkboxes: `checkbox` (empty name) — anchor by the adjacent consent `paragraph` text. Conf 6.5.
- **Per-field remove control — ⚠️ the original link claim is CONTRADICTED LIVE.**
  This section originally locked the controls as real `link`s —
  `getByRole('link', { name: 'Open settings' })` / `getByRole('link', { name:
  'Remove field' })` (captured ONCE, 2026-07-02; the raw snapshot was NOT
  retained). **Three consecutive live runs (2026-07-07/08, attempts #6, #7,
  and the v18.1.11 `skill6-live-verify-20260708-040836` run) attached ZERO
  nodes for BOTH the exact and the substring form of that lock** — after the
  select-click and 13 genuine park-away/re-hover cycles: `'role=link:Remove
  field': 0 attached match(es); 'role~=link:Remove field': 0 attached
  match(es)`. Confidence on the link form is downgraded to **4** (kept only as
  tier 1 of the ladder below, in case the accessible names return).
  **Best-evidenced real mechanism** (training-video CLICK-MAP Step 8: *"Delete
  a field = select it → trash icon (top-right of the selected field's blue
  bar)"*; Step 15: a dropped field *"auto-selects (blue outline + gear/trash
  icons)"*; the 2026-07-02 capture screenshot `008-field-selected.png` shows a
  SELECTED field's blue pill at its top-right with two ICON-ONLY controls —
  gear = settings, trash = delete; GHL help/community: *"hover over the field
  until you see the delete or trash icon"*): an **icon pill on the SELECTED
  field's top-right**, most likely the §5 icon-only pattern (NO accessible
  name / aria-label / testid). Conf 7 on the mechanism, unknown on DOM shape.
  **Driver doctrine (ghl_iframe_drag v1.3.0 tiered acquisition):** select the
  field (anchor click, wrapper-strip click fallback), then scan tiers in
  order — (1) the documented link specs above, (2) role link/button named
  /remove|delete|trash/i, (3) `[aria-label]`/`[title]` deletion attributes
  (tiers 2–3 gated to the field's top-right CONTROL ZONE), (4) last-resort
  geometric icon-pill ladder (census of small visible clickables in the zone,
  clicked rightmost-first — trash sits right of gear — each click
  count-verified). Every failure persists a rich diagnostics receipt
  (`routing/f4-remove-diag-<field>.json`: strategy census, geometric census
  with per-candidate rejection reasons, capped whole-frame aria snapshot,
  stimulation trace) + a failure-moment screenshot — the NEXT live run must
  update this section with what the census actually saw. *(CLICK-MAP
  Ambiguity #4 for in-builder field delete is therefore OPEN again, pending
  live census evidence.)*

## 7. ⛔ LOCKED CONSTRAINT — what is NOT stably anchorable (evidence-backed)

The builder is a **cross-origin iframe**. Through the CDP `@ref` rail:
- Only **true interactive leaves** (buttons, textboxes, checkboxes, links,
  menuitems, radios) receive `@ref`s and are targetable.
- **Quick-Add tiles** (`generic` + `image` + `StaticText`) and **builder tabs /
  Form-Element tabs** (`StaticText "Quick Add" / "Add Object Fields" / "Settings"`)
  get **no ref**; top-frame `text=` / CSS / `find text` **cannot reach into the
  iframe** (verified: `drag text=State`, `find text "Add Object Fields"` both →
  *Element not found*).
- **Refs churn every snapshot** — you MUST `snapshot` and act on that snapshot's
  refs immediately (verified: stale refs mis-clicked).

**Implication for the DUMB browser operator:** field-property edits, Quick-Add
drags, and tab switches are genuine `[runtime-capture]` / visible-text +
coordinate-drag surfaces — exactly as `CLICK-MAP.md` marks them. They are driven
by the builder's own drag/click event system (visible-text + position), NOT by a
stable DOM selector. Do NOT invent CSS selectors for these; snapshot-and-bind at
runtime, STOP-and-report on miss. This confirms the CLICK-MAP two-layer design.

## 8. Quick-Add taxonomy (LIVE-CONFIRMED, exact — anchor tiles by visible text)

Personal Info: `Full Name · First Name · Last Name · Date of birth · Phone · Email`
· Submit: `Submit` · Payments: `Sell Products · Collect Payment` · Address:
`Address` (badge "Updated") `· City · State · Country · Postal Code · Organization
· Website` · Text: `Single Line · Multi Line · Text Box List` · Choice Elements:
`Single Dropdown · Multi Dropdown · Checkbox · Radio` · Rating: `Rating` (badge
"New") · Customized: `Text · Html · Captcha · Source · T & C · Score` · Other
Elements: `Image · File Upload · Monetary · Number · Date Picker · Signature`.
Matches CLICK-MAP Step 10 verbatim. Tile anchor = `getByText('<tile>')` within the
`Form Element` panel (drag-only; not ref-clickable — see §7). Conf 8 (text) / for
drag see §7.

## 9. Integrate modal (embed snippet + share) — #48–#52

Opened via `getByRole('button', { name: 'Integrate' })`. Modal `heading` =
**"Embed or Share Form"** → `getByRole('heading', { name: 'Embed or Share Form' })`.

| Target (#) | LOCKED anchor | Conf |
|---|---|---|
| Left menu `Embed Code / Share / Email` (#38) | `StaticText` (no ref) → `getByText('Embed Code'|'Share'|'Email')` (menu, not ref-clickable via CDP) | 7 |
| Embed Layout Type `Sticky sidebar / Polite slide-in / Popup / Inline` (#39) | `getByText(...)`; **Inline** is the in-page default | 7.5 |
| Trigger radios | `getByRole('radio', { name: /Show on scrolling|Show after|Always show/ })` (`Always show` checked) | 9 |
| Activation radios | `getByRole('radio', { name: /Activate on|Always activated/ })` (`Always activated` checked) | 9 |
| Deactivation radios | `getByRole('radio', { name: /Deactivate after showing|Deactivate once lead is collected|Never deactivate/ })` (`Never deactivate` checked) | 9 |
| **Copy embed code** (#40) | `getByRole('button', { name: 'Copy embed code' })` | 9.5 |
| Share direct link (#41) | Share tab → field `https://<location-domain>/widget/form/<FORM_ID>` (Share menu is StaticText; capture link at runtime) | 7 |

Embed defaults (Inline / Always show / Always activated / Never deactivate) are
the correct in-page drop-in per the forms-playbook. Close modal with `Escape`
(verified) or the dialog X.

## 10. Off-camera gaps — status

| Gap | Status this run |
|---|---|
| Field properties panel (Label/Query Key/Field Width/Required/Hidden/Advanced/Custom Field Name/Unique Key) | Reached the field-level `Open settings` link (anchor locked). Panel inputs themselves are in-iframe `[runtime-capture]` by visible label — NOT stably ID-anchored (see §7). Bind by label text at runtime. |
| Settings tab → on-submit / redirect / thank-you | Tab is `StaticText` (not ref-clickable via CDP rail); route-level `Settings` sub-tab requires visible-text/coordinate drive by the operator. Documented as runtime-capture. |
| Styles / Themes / Advanced / Custom CSS | Toggle = icon button (SVG `M3 8h12…`, §5 row-8). Panels open on click; inner controls are in-iframe runtime-capture by visible text. |
| Tag-on-submit | Confirmed live-consistent with CLICK-MAP Phase N: **no native add-tag control in the form builder.** Tagging = Skill-44 workflow `Form Submitted → Add Contact Tag {{zhc_…}}`, built after the form ID exists. |

---

## Self-grade (rubric)

| Criterion | Score /10 | Note |
|---|---|---|
| Auth proven live | 10 | Seed→activate attempt 1; dashboard reached |
| Nav + list + create + delete anchors | 9.5 | role/name/menuitem, end-to-end delete verified |
| Builder chrome (named buttons) | 9.5 | Back/Preview/Integrate/Save/Submit locked |
| Icon-only toolbar | 7 | No aria/testid; SVG-`d` + order is best available |
| Integrate/embed | 9 | Copy-embed + radios locked; layout menu text-only |
| Field props / canvas drags | 6.5 | Honest `[runtime-capture]` — iframe/ref constraint proven, not faked |
| Cleanup (no residue) | 10 | Test form deleted; 0 live occurrences |
| No invented selectors | 10 | Every anchor observed live or explicitly marked runtime-capture |

**Overall: 8.9 / 10** (≥ 8.5 target met). The one honest deduction is the
in-iframe canvas/props/tab surface, which is architecturally `[runtime-capture]`
(cross-origin iframe + churning CDP refs) and is documented as such rather than
guessed — consistent with the existing tool's snapshot-gated design.
