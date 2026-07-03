# CLICK-MAP — Create a GHL Form via Browser Operator (Convert and Flow / Go High Level)

**Source:** the Go High Level form-builder walkthrough video (1134.5 s / 18:54, 1920x854), analyzed frame-by-frame; coordinates below are in a 1280-wide space (approximate). Narration is normalized in the canonical transcript.

> ⚠️ **NAMING.** The platform is **Convert and Flow = Go High Level (GHL)** = "leadconnectorhq.com" builder iframe. Any third-party form-tool name that may appear in a source caption filename is a **mislabel** — this is Go High Level. Never write a non-GHL tool name in any deliverable.
> 🔒 **Fleet-wide repo.** Any real client name, subdomain, or form ID from the source is **redacted** here to `<location-name>` / `<location-domain>` / `<formId>`. Do not reintroduce them.

---

## How to read this map (two-layer split)

This map is written as the **DUMB browser-operator script**. Every step gives a **visible-text primary anchor** (the reliable locator for a weak MiniMax-class operator), a **position hint**, an optional **best-guess DOM anchor**, the **typed value**, the **expected result**, and a **wait/verify cue**.

- **SMART layer (high-reasoning agent — the fleet's top thinking tier)** decides: which fields, which are custom vs standard, the `zhc`-prefixed custom-field/tag names, field widths/rows, styling, and fills every `{{PLACEHOLDER}}` before handing this script down.
- **DUMB layer (browser operator)** only executes clicks/types/drags and checks the verify cue. It makes **no naming or field decisions**.
- ⚠️ **DOM caveat:** the builder runs inside a cross-origin iframe (`app.gohighlevel.com` → `*.leadconnectorhq.com`). Exact `id`/`data-*`/`aria-label` values are **not legible from video frames** and drift between GHL releases. Treat every "best-guess anchor" below as a **hint only** — the operator MUST take a fresh `browser_snapshot` and bind to the **visible text / role** at runtime. Anchors marked `[runtime-capture]` have no stable guess and must be read from the live snapshot.

---

## Persistent UI chrome (reference — not steps)

**GHL global left rail (vertical, dark, ~x0–150):** top account switcher ("`<location-name>`" + city), then AI spark icon, Contacts, Conversations, Calendars, Payments, Automation, **Sites** (globe icon — our entry), Memberships, Opportunities, Marketing, Dashboard, Launchpad, Media Storage, Reputation, Reporting… **Settings** pinned at bottom (~y547).

**Sites secondary top nav (orange bar, ~y50):** `Funnels | Stores | Webinars | Analytics | Quizzes | QR Codes | Websites | Blogs | WordPress | Client Portal ▾ | Forms | Surveys | Chat Widget`. **Forms** sits ~three-quarters across (~x815).

**Forms sub-page header:** section title "Forms", tabs `All forms | Analytics | Submissions` (~y90), right side `Form features` button, a folder icon, blue **`+ Create form`** (~x1230,y90).

**Form-builder top bar (row 1, ~y17):** `← Back` (x30) · centered **form-name text + ✎ pencil** (x625) · right cluster **`Preview`** (x1095) · **`Integrate`** (x1170) · blue **`Save`** (x1240, shows an orange dot when there are unsaved changes).

**Form-builder toolbar (row 2, ~y50):** left = **`+`** (x27, opens the Form Element panel) · a stack/duplicate icon (x51) · **desktop** + **mobile** device-preview toggles (x93/x116). Center = tabs `Edit | Settings | Submissions | Notifications | Analytics` (x512–754). Right = a round grid/snap icon (x1153) · **undo ↶** (x1188) · **redo ↷** (x1212) · **⇄ Styles-and-Options** toggle (x1246, directly under Save).

**Form Element panel (left, opens at ~x0–235):** header "Form Element" + ✕ close. Two tabs: **`Quick Add`** and **`Add Object Fields`**.

**Field properties panel (right, opens at ~x1040–1270 when a field is selected):** `← back` + field-type title; collapsible `GENERAL SETTINGS`; then type-specific + `ADVANCED SETTINGS`.

---

## PHASE A — Navigate to the Forms area  (00:05–00:56)

### Step 1 — Open Sites
- **Screen/context:** any GHL page (video starts on a loading Dashboard, frame `t000091`).
- **Click:** left-rail **`Sites`** (globe icon), ~x42,y260. Primary anchor: `getByRole('link'|'button', name=/^Sites$/)`. Best-guess: nav item with globe icon. `[hint]`
- **Type:** —
- **Expected:** Sites area loads on its default tab = **Funnels** (orange nav bar appears; heading "Funnels — Create and manage funnels…"). Rows may skeleton-load first.
- **Verify:** orange secondary nav visible AND `Funnels` tab is the active (white) tab. Wait for the orange bar.

### Step 2 — Confirm Funnels page (transient)
- **Context:** Funnels list (frame `t000324`). Table headers `Name | Last updated | Funnel steps`.
- **No click** — this is a landmark. If the operator lands here, proceed.
- **Verify:** heading text "Funnels".

### Step 3 — Click Forms in the secondary nav
- **Click:** top orange nav **`Forms`** button, ~x815,y50 (about ¾ across; between `WordPress`/`Client Portal ▾` and `Surveys`). Primary anchor: `getByText('Forms', exact)` within the secondary nav bar. Best-guess: `a[href*="/form-builder"]` or nav tab. `[hint]`
- **Expected:** page switches to the **Forms** sub-app; sub-tabs `All forms | Analytics | Submissions` appear; `+ Create form` button top-right (frame `t000534`).
- **Verify:** `All forms` tab visible AND `+ Create form` button present. Wait for table headers `Name | Updated on | Updated by`.

### Step 4 — (Landmark) Forms list loaded
- **Context:** existing forms list (frame `t000630`; rows-per-page 20, "1–20 of 54").
- **Verify:** `+ Create form` clickable (top-right, blue).

---

## PHASE B — Create the form (scratch vs template)  (00:56–01:39)

### Step 5 — Click Create form
- **Click:** blue **`+ Create form`**, ~x1230,y90. Anchor: `getByRole('button', name=/Create form/i)`. `[hint]`
- **Expected:** modal **"Create new form"** opens (frame `t000700`) with two cards + `Cancel` / blue `Create`.
- **Verify:** modal title "Create new form" visible.

### Step 6 — Choose "Start from Scratch"
- **Context:** modal has two radio cards: **left = "Start from Scratch"** ("Design from scratch using the form builder", big ⊕, radio top-right) and **right = "From templates"** ("Jump start with an awesome prebuilt form", "Over 1000+ Templates" thumbnail).
- **Click:** the **`Start from Scratch`** card (its radio), ~x540,y210. Anchor: `getByText('Start from Scratch')` → click card/radio. `[hint]`  *(It is selected by default; click to be explicit.)*
- **Expected:** left card gets a blue border + filled radio.
- **Verify:** "Start from Scratch" card shows selected (blue outline, frame `t000918`).
- **SMART-layer note:** template path is out of scope for this rail; always scratch unless told otherwise.

### Step 7 — Click Create
- **Click:** blue **`Create`** button, bottom-right of modal, ~x825,y405. Anchor: `getByRole('button', name=/^Create$/)`. `[hint]`
- **Expected:** modal closes; brief blank/loading screen (frame `t000924`); then the **form builder** opens with a new form named **`Form <n>`** (e.g. "Form 125").
- **Verify (wait):** builder chrome present — `← Back`, centered form-name + pencil, `Preview/Integrate/Save`, and a default form on canvas. This is a heavy load; wait for the `Save` button to render.

---

## PHASE C — Builder orientation & default fields  (01:39–03:50)

### Step 8 — (Landmark) Default form contents
- **Context:** frames `t000956`/`t001050`. A brand-new scratch form is **pre-seeded** with:
  1. **First Name** (label + "Enter your first name")
  2. **Last Name** ("Enter your last name")
  3. **Phone \*** ("+1 (555) 000-0000", required)
  4. **Email \*** ("your@email.com", required)
  5. **Terms & Conditions** = **two consent checkboxes** (non-marketing SMS + marketing SMS) whose text contains merge placeholders `[BUSINESS NAME]` and `[USE_CASE_FROM_CAMPAIGN_DESCRIPTION]`
  6. blue **Submit** button
  7. footer **Privacy Policy | Terms of Service** links (this is a **Text element**, see Phase K)
- **SMART-layer note:** decide which defaults to keep/delete. Delete a field = select it → trash icon (top-right of the selected field's blue bar). The footer Privacy/Terms text and `[BUSINESS NAME]`/consent copy are **starters that must be updated** for the client.

### Step 9 — Open the Form Element panel (if closed)
- **Click:** toolbar **`+`** (x27,y50) OR it may already be open. Anchor: first icon-button in row 2. `[runtime-capture]`
- **Expected:** left **"Form Element"** panel opens, tab **`Quick Add`** active (frame `t000956`).
- **Verify:** panel header "Form Element" + tabs "Quick Add" / "Add Object Fields".

### Step 10 — (Reference) Quick Add categories
Scroll the left panel to see the full Quick-Add taxonomy (frames `t001190`–`t002380`). Categories → elements:
- **Personal Info:** Full Name · First Name · Last Name · Date of birth · Phone · Email
- **Submit:** Submit
- **Payments:** Sell Products · Collect Payment
- **Address:** Address *(badge "Updated")* · City · State · Country · Postal Code · Organization · Website
- **Text:** Single Line · Multi Line · Text Box List *(Text Box also per narration)*
- **Choice Elements:** Single Dropdown · Multi Dropdown · Checkbox · Radio
- **Rating:** Rating *(badge "New")*
- **Customized:** Text · Html · Captcha · Source · T & C · Score
- **Other Elements:** Image · File Upload · Monetary · Number · Date Picker · Signature *(Picture Date Picker per narration)*
- **Second tab `Add Object Fields`** (frame `t002380`): an **object selector dropdown = "Contact"**, a blue **`+ Add`** button, a **"Search by Name"** box, and grouped **custom-field folders** with counts: the GHL defaults `CONTACT (n) · GENERAL INFO (n) · ADDITIONAL INFO (n)` followed by the location's own folders `<CUSTOM FOLDER 1> (n) · <CUSTOM FOLDER 2> (n) · …` (folder names are the client's — redacted here; treat as data at runtime). **This tab is where pre-created custom fields live** (Phase H), and `+ Add` can create a new one inline `[dialog not shown — see Ambiguities]`.

---

## PHASE D — Rename the form  (04:22–05:03)

### Step 11 — Click the default form name
- **Click:** centered form-name text at top, ~x625,y17 (reads "Form <n>"; a ✎ pencil sits to its right). Anchor: `getByText(/^Form \d+$/)` in the top bar, or the pencil icon. `[hint]`
- **Expected:** the name becomes an **editable, highlighted** text field (frame `t002730` shows "Form 125" selected blue).
- **Verify:** name text is selected/editable.

### Step 12 — Type the form name
- **Type:** `{{FORM_NAME}}` (video used "Test Form 12"). SMART layer supplies a clear human name.
- **Expected:** field shows the new text.

### Step 13 — Commit the name
- **Action:** press **Enter** (narration: click the name, type, then hit Enter). Anchor: `keyboard Enter`.
- **Expected:** top-center now shows `{{FORM_NAME}}` (frame `t002940` shows "Test Form 12").
- **Verify:** name persists in the top bar.

---

## PHASE E — Add STANDARD fields via Quick Add (State + City, 50%/row)  (05:03–08:16)

### Step 14 — Scroll to the Address category
- **Action:** in the left `Quick Add` panel, scroll down to **Address** (frame `t003150`). Anchor: `getByText('Address')` section header.
- **Verify:** tiles `Address · City · State · Country · Postal Code · Organization · Website` visible.

### Step 15 — Drag the State element onto the form
- **Drag source:** **`State`** tile (Address group), ~x190,y254 (⋮⋮ drag-dots at tile top). Anchor: `getByText('State')` tile. `[hint]`
- **Drop target:** onto the form where the field should go (video drops it above Phone). Use `browser_drag(source=State tile, target=form drop-zone between Last Name and Phone)`.
- **Expected:** a new **State** field appears (label "State", placeholder "Enter your state"); it auto-selects (blue outline + gear/trash icons); the **right properties panel titled "Text"** opens (frame `t003394`).
- **Verify:** right panel shows `Label = State`, `Query Key = state`, `Field Width = 100 %`, `Required`/`Hidden` unchecked.

### Step 16 — (Reference) Standard-field property panel
Right panel "Text" → `GENERAL SETTINGS`:
- **Label** (text) = "State"
- **Label Alignment** = 4 buttons: left `|←`, top `↑`, right `→|`, **`Form Default`** (+ a device dropdown ▾)
- **Placeholder** = "Enter your state"
- **Short Label** = "Please Input"
- **Query Key** (ⓘ) = "state" — tooltip: *"The query key that can be used as a URL param to populate this field"* (frame `t003570`). Keep **lowercase, no spaces/special chars**.
- **Field Width** = `100 %`
- **Required** ☐ / **Hidden** ☐ (mutually exclusive — see Step 18)

### Step 17 — Set State Required
- **Click:** **`Required`** checkbox (right panel, ~x1055,y475). Anchor: `getByLabel('Required')` in props panel. `[runtime-capture]`
- **Expected:** field label becomes "State \*"; **Hidden** greys out/disables (frame `t003850`).
- **Verify:** Required is checked, Hidden disabled.

### Step 18 — Set State Field Width = 50%
- **Click+type:** **`Field Width`** input, clear, type `50` (~x1147,y443). Anchor: numeric input under "Field Width" label. `[runtime-capture]`
- **Expected:** value = `50`, unit `%`. State now occupies half a row (frame `t003850`).
- **SMART-layer note:** 50% lets a second element share the row.

### Step 19 — Drag the City element above State
- **Drag source:** **`City`** tile (Address group), ~x115,y254. Anchor: `getByText('City')` tile. `[hint]`
- **Drop target:** **directly above** the State field (video drops City above State). `browser_drag(City tile → drop-zone above State)`.
- **Expected:** **City** field inserted above State (frame `t004410`: "City \*" over "State \*"); City auto-selects, its props open (Query Key `city`, Placeholder "Enter your city").
- **Verify:** City field present; right panel `Label = City`.

### Step 20 — Set City Required
- **Click:** `Required` checkbox for City. `[runtime-capture]`
- **Verify:** "City \*".

### Step 21 — Set City Field Width = 50%
- **Type:** `50` in City `Field Width`.
- **Expected:** City + State now render **two-per-row at 50% each** (frame `t004760`).
- **Verify:** City and State on the same row, both 50%.

> **Standard-vs-custom cue:** State/City map to **built-in contact fields** → their **Query Key is clean** (`state`, `city`) and there is **no random suffix**. Contrast with Phase F.

---

## PHASE F — Create a CUSTOM field ON THE FLY (Rating example)  (08:01–10:23)

### Step 22 — Scroll to the Rating element
- **Action:** left `Quick Add` panel → scroll to **Rating** category (frame `t005040`; below Choice Elements). Anchor: `getByText('Rating')` section + tile (⭐, "New" badge).

### Step 23 — Drag Rating under Email
- **Drag source:** **`Rating`** tile, ~x40,y335. Anchor: `getByText('Rating')` tile. `[hint]`
- **Drop target:** below the Email field. `browser_drag(Rating tile → drop-zone under Email)`.
- **Expected:** a **Rating** field appears with **an auto-generated label like `Rating rat584 1ssw`** — a **random letters+numbers suffix** (frame `t005250`). The right panel titles **"Rating"**.
- **Verify:** field label contains a random token (e.g. matches `/rat\w+/`).

> 🔑 **This is the "it's a custom field" signal.** When a Quick-Add element does **not** map to a standard contact field, GHL **auto-creates a brand-new custom field** and stamps a random unique key. Standard fields never do this.

### Step 24 — (Reference) Rating GENERAL SETTINGS
Right "Rating" panel: `Label` (= "Rating rat584 1ssw") · `Label Alignment` · `Short Label` · `Field Width 100%` · `Required ☐` · collapsible **`RATING SETTINGS`** · collapsible **`ADVANCED SETTINGS`** (frame `t005250`).

### Step 25 — Expand Advanced Settings
- **Click:** **`ADVANCED SETTINGS`** disclosure (right panel). Anchor: `getByText('ADVANCED SETTINGS')`. `[hint]`
- **Expected:** reveals **`Custom Field Name`** (ⓘ, editable = "Rating rat584 1ssw") and **`Unique Key`** (ⓘ, greyed/read-only = "rating_rat_584_1_ssw") (frame `t005530`).
- **Verify:** both fields visible; Unique Key is disabled.

### Step 26 — Set the Custom Field Name
- **Click+type:** **`Custom Field Name`** input; clear the random default and type `{{CUSTOM_FIELD_NAME}}` — convention: **match the label, all lowercase, one word** (video typed `postcastrating`; intended "podcastrating"). Anchor: input under "Custom Field Name". `[runtime-capture]`
- **Expected:** as you type, the on-canvas **Label updates** to match, and **Unique Key becomes `rating_rat584_<yourvalue>`** (frames `t005810`→`t006020`: Label "postcastrating", Unique Key "rating_rat584_postcastrating"). Unique Key ⓘ tooltip: *"the system-generated key for this custom field. Once set, it cannot be changed."*
- **Verify:** Custom Field Name = your value; Unique Key ends with your value and is read-only.

> ⛔ **zhc convention (SMART layer must enforce, not shown in video):** any **agent-created** custom field or tag MUST be prefixed **`zhc`** (agent-created marker). Because GHL derives the Unique Key from the Custom Field Name, the SMART layer sets **`Custom Field Name = zhc<lowercasename>`** (e.g. `zhcpodcastrating`) so the key carries the marker. **Before creating,** the SMART layer checks (via the GHL-API skill) for an existing `zhc`-prefixed field/tag of the same intent and **reuses it** — idempotent, no duplicates. See "Custom fields & the API skill" below.

---

## PHASE G — Rating type-specific settings  (10:35–12:14)

### Step 27 — Expand Rating Settings
- **Click:** **`RATING SETTINGS`** disclosure. Anchor: `getByText('RATING SETTINGS')`. `[hint]`
- **Expected (frame `t006440`):** reveals:
  - **Icon:** 5 choices — ⭐ star · ♥ heart · 👍 thumbs-up · 🚩 flag · 💡 globe/lightbulb
  - **Icon Alignment:** left `|←` · right `→|` · center
  - **Count:** dropdown (default `5`, "up to 10")
  - **Lowest Rating:** "Bad" · **Highest Rating:** "Good"
  - **How to Store Rating Fields in Custom Fields:** dropdown (default **Absolute**)
  - **Icon Selected State:** color `#FBBF24` · **Icon Unselected State:** color `#E5E7EB`

### Step 28 — Pick an icon (thumbs-up)
- **Click:** the **thumbs-up** icon (3rd), ~x1140,y313. Anchor: 3rd button in the Icon row. `[runtime-capture]`
- **Expected:** canvas icons switch to thumbs-up (frame `t006650`).

### Step 29 — (Optional) icon alignment / count / labels
- Set **Icon Alignment**, **Count** (≤10), **Lowest/Highest Rating** labels as needed. `[runtime-capture]`

### Step 30 — Choose the store format
- **Click:** **`How to Store Rating Fields in Custom Fields`** dropdown → options **Absolute** (✓ default) · **Percentage** · **Fraction** (frame `t007070`). Tooltip: *"When you rate 4 out of 5 stars: Absolute = 4 out of 5; Percentage = 80; Fraction = 0.8."*
- **Verify:** chosen value shown.

### Step 31 — (Optional) selected/unselected colors
- Edit **Icon Selected State** / **Icon Unselected State** hex swatches (frame `t006860`). `[runtime-capture]`

---

## PHASE H — Add a PRE-CREATED custom field (Add Object Fields)  (12:14–14:12)

### Step 32 — Switch to the Add Object Fields tab
- **Click:** left panel tab **`Add Object Fields`**, ~x178,y104. Anchor: `getByText('Add Object Fields')`. `[hint]`
- **Expected:** panel shows the **`Contact`** object dropdown, blue **`+ Add`**, **`Search by Name`**, and the custom-field **folders** (frame `t007630`).
- **Verify:** folder list with counts visible.

### Step 33 — Open the folder that holds the field
- **Click:** the target folder header, e.g. **`<CUSTOM FOLDER> (n)`**, ~x50,y281. Anchor: `getByText(/<folder name>/)`. `[hint — folder names are client data; bind to the plan's value at runtime]`
- **Expected:** folder expands listing its custom fields, each with a ⋮⋮ drag handle: e.g. `Facebook URL · Short Bio · <custom field 3> · <custom field 4> · …` (frame `t007630`).
- **SMART-layer note:** to find a specific field fast, type its name into **Search by Name** instead of hunting folders. To scope by object, use the `Contact` dropdown.

### Step 34 — Drag the pre-created field onto the form
- **Drag source:** e.g. **`Facebook URL`** row, ~x48,y315 (its ⋮⋮ handle). Anchor: `getByText('Facebook URL')` row in the folder. `[hint]`
- **Drop target:** desired form position (video drops under the Rating field). `browser_drag(Facebook URL row → drop-zone)`.
- **Expected:** the field is added and selected; right props panel opens with `Label = Facebook URL`, `Query Key = facebook_url`, `Field Width 100%`, `Required`/`Hidden` (frame `t007837`).
- **Verify:** new field on canvas + props panel populated.

### Step 35 — Confirm the locked Advanced Settings
- **Click:** **`ADVANCED SETTINGS`** in the props panel.
- **Expected (frame `t007980`):** **`Custom Field Name` = "Facebook URL" (greyed/locked)** and **`Unique Key` = "contact.facebook_url" (greyed/locked)** — because this field was created previously, **you cannot change name or key**.
- **Verify:** both greyed.

### Step 36 — Change the Label (allowed)
- **Click+type:** props **`Label`** → `{{FIELD_LABEL}}` (video: "Personal Facebook URL"). Anchor: `Label` input. `[runtime-capture]`
- **Expected:** on-canvas label updates (frame `t008190`); Query Key/Unique Key stay unchanged.
- **Verify:** new label shown.

### Step 37 — (Optional) Required OR Hidden — not both
- **Click:** `Required` **or** `Hidden` (mutually exclusive). Video sets **Required** → "Personal Facebook URL \*" and Hidden greys out (frame `t008610`).
- **SMART-layer note (from narration):** **Hidden** fields are for passing data the visitor shouldn't see — e.g. a **score**, a **tag value you want the contact to have**, or data to hand to the next phase of a multi-step flow. (This is a hidden **field value**, not the GHL contact-tag system — see Phase N.)

---

## PHASE I — Save the draft  (14:16–14:31)

### Step 38 — Save
- **Click:** blue **`Save`** (top-right, x1240,y17). Anchor: `getByRole('button', name=/^Save$/)`. `[hint]`
- **Expected:** draft saves; the orange "unsaved" dot on Save clears.
- **Verify:** toast/indicator or the Save dot disappears. Wait for save to settle before styling.

---

## PHASE J — Style the form: Styles / Themes / Advanced + Custom CSS  (14:26–16:44)

### Step 39 — Open Styles and Options
- **Click:** the **⇄ Styles-and-Options** toggle in row 2, far right directly under Save (~x1246,y50). Anchor: last icon-button in the builder toolbar. `[runtime-capture]`
- **Expected:** right panel switches to a **Styles** panel with three tabs **`Styles | Themes | Advanced`** and a ✕ to close (frame `t008890`).
- **Verify:** tabs `Styles/Themes/Advanced` visible.

> **Selection scope (narration):** with a **field selected**, style edits apply to **that field**; **deselect** the field (click empty canvas) then use `Options`/`Advanced` to edit **form-level** styling.

### Step 40 — Styles tab → Layout
- **Context (frame `t008890`):** `Styles` tab, **`LAYOUT`** section: `Show Image` toggle · `Columns` (Single Column ▾) · `Input Style` (Box ▾) · `Width 800 PX` · `Field Spacing 16` · `Label Width 200 PX` · `Label Alignment` · `Margin & Padding` (visual 16px box) · `Show Label` toggle.
- The `Styles` tab has **three collapsible sections** (frame `t010150`): **`LAYOUT` · `COLORS & BACKGROUND` · `MISCELLANEOUS`** (Miscellaneous controls **agency branding**).

### Step 41 — Themes tab
- **Click:** **`Themes`** tab. Anchor: `getByText('Themes')`. `[hint]`
- **Expected:** pick from **pre-created themes** and update styles. `[theme grid not detailed in frames — Ambiguity]`

### Step 42 — Advanced tab → per-section styling
- **Click:** **`Advanced`** tab (frame `t009103`). Sections (collapsible): **`FORM`** (Border Width `1px`, Corner Radius `8px`, Border Color `#FFFFFF`, Border Style solid/dashed/dotted/none, Shadow color `#57647E36` + Horizontal/Vertical/Blur/Spread) → **`INPUT FIELD`** (font color, active-tab color, border, radius, shadows) → **`LABEL`** → **`SHORT LABEL`** → **`PLACEHOLDER`** (Placeholder Color `#667085FF`, Font Family `Inter`, Font Size `16px`, Weight `400`) → **`CUSTOM CSS`**.
- `[runtime-capture]` for each numeric/color input.

### Step 43 — Custom CSS (highest precedence)
- **Click:** **`CUSTOM CSS`** disclosure at the bottom of the Advanced tab (frame `t009660`). Tooltip (ⓘ): *"Custom CSS takes precedence over form styling & themes and may have an impact on the theme's styling."*
- **Type:** paste `{{CUSTOM_CSS}}` into the code box (line-numbered editor). Anchor: the CSS code textarea. `[runtime-capture]`
- **SMART-layer note:** put final look-and-feel here; it **overrides** Styles + Themes. Good place to force brand colors, button styling, responsive tweaks when embedded.
- **Verify:** CSS text present in the editor.

### Step 44 — Save styling
- **Click:** `Save`. Verify the unsaved dot clears.

---

## PHASE K — Text / HTML layout elements + footer text element  (16:44–18:09)

### Step 45 — (Reference) most-used + segmenting elements
- **Narration:** most-utilized fields = **First Name, Last Name, Phone, Email, Submit**, plus **Text fields** and **Choice** elements. Use **`Text`** / **`Html`** elements (Customized group) to **segment** the form so it isn't just a wall of 20 inputs.

### Step 46 — The footer Privacy/Terms is a Text element
- **Click:** the **Privacy Policy | Terms of Service** block at the form bottom (frames `t010591`/`t010719`). Anchor: `getByText('Privacy Policy')` block.
- **Expected:** it selects as a **Text element** exposing a **rich-text editor** — toolbar: undo/redo, text-color `A`, line-height `1.5`, **link 🔗**, image, and a **tag/merge-value icon** (inserts custom values/merge fields into the text — **NOT** a contact tag), plus font (`Inter`), `Paragraph`, `16px`, `B I U S`, color, highlight, alignment, lists, code. Right panel = `Text` GENERAL SETTINGS (Weight 400, Background, Border, Corner Radius, Padding).
- **SMART-layer note:** the Privacy/Terms hyperlinks are starter text; update the link URLs and copy for the client here.

---

## PHASE L — Preview  (18:14–18:22)

### Step 47 — Preview
- **Click:** **`Preview`** (top-right, x1095,y17; frame `t010920`). Anchor: `getByRole('button', name=/Preview/i)`. `[hint]`
- **Expected:** a preview of how the form displays (device toggles desktop/mobile available in row 2).
- **Verify:** preview renders; close/return to Edit.

---

## PHASE M — Integrate: Embed code / Share / Email  (18:14–18:54)

### Step 48 — Open Integrate
- **Click:** **`Integrate`** (top-right, x1170,y17). Anchor: `getByRole('button', name=/Integrate/i)`. `[hint]`
- **Expected:** modal **"Embed or Share Form"** opens with a left menu **`Embed Code | Share | Email`** (frame `t011062`).
- **Verify:** modal title "Embed or Share Form".

### Step 49 — Embed Code tab (the JS snippet)
- **Context (frame `t011062`):** `Embed Code` selected. Options:
  - **Embed Layout Type:** `Sticky sidebar` · `Polite slide-in` · `Popup` · **`Inline`** (Inline selected by default — the standard drop-in).
  - **Trigger type:** `Show on scrolling __%` · `Show after __ seconds` · **`Always show`** (default).
  - **Activation options:** `Activate on __ visit` · **`Always activated`** (default).
  - **Deactivation options:** `Deactivate after showing __ times` · `Deactivate once lead is collected` · **`Never deactivate`** (default).
- **Click:** blue **`Copy embed code`** (bottom-right, ~x853,y516). Anchor: `getByRole('button', name=/Copy embed code/i)`. `[hint]`
- **Expected:** the **`<script>` JS embed snippet** is copied to clipboard.
- **SMART-layer note:** for a normal in-page/funnel embed pick **Inline**; use Popup/Slide-in/Sidebar for overlays.
- **Verify:** copy confirmation / clipboard has a `leadconnectorhq` form script.

### Step 50 — Share tab (direct link + socials)
- **Click:** left menu **`Share`** (frame `t011200`). Shows **Share via Socials** (Facebook · WhatsApp · LinkedIn · X), **Copy Link** field = `https://<location-domain>/widget/form/<formId>` with a copy icon, and **`Open Form Link`**.
- **Use:** copy the direct form link, or share to a social channel.

### Step 51 — Email tab
- **Click:** left menu **`Email`**. Narration: **select a template and email the form out directly**. `[panel contents not shown in frames — Ambiguity]`

### Step 52 — Close
- **Click:** modal ✕ (x897,y51). Returns to the builder (frame `t011327`). Done.

---

## PHASE N — Attaching a TAG (NOT shown in this video — documented for the skill)

**What the video actually shows re: tags:** only (a) the narration that a **Hidden field** can carry "a tag you want the contact to have," and (b) a **tag/merge-value icon** in the Text-element editor (inserts custom values into text). **Neither is the GHL contact-tag system**, and the video **never opens a form-level "Add Tag" setting nor a workflow**. So:

- **`tag_flow_seen = false`.**
- **Native GHL reality (SMART-layer guidance):** the GHL **form builder has no "add tag" control**. Tagging a contact on submission is done **outside the builder**, via a **Workflow** (or the legacy Trigger): trigger = **"Form Submitted" (this form)** → action = **"Add Tag" → `{{TAG}}`**. This is the **workflow-trigger** path, not a form setting.
- ⛔ **zhc + idempotency:** any agent-applied tag MUST be **`zhc`-prefixed** (e.g. `zhc-podcast-lead`); the SMART layer first checks for an existing `zhc` tag of the same intent (GHL-API) and reuses it — no duplicates.

---

## Custom fields & the API skill (SMART-layer, cross-referenced)

Two ways custom fields enter a browser-built form:
1. **On-the-fly (Phase F):** drag a non-standard element (Rating, etc.); GHL auto-creates a custom field with a random key. Rename via **Advanced Settings → Custom Field Name** (set to `zhc<name>`). Fast, but the key/name is derived and the operator is weak — risk of duplicates/typos.
2. **Pre-created (Phase H):** fields made **beforehand** appear under **Add Object Fields** and are dragged in; name/key are **locked**, only Label is editable.

**Recommended split for this rail:** the **SMART layer creates required custom fields up-front via a GHL-API skill** (idempotent, `zhc`-prefixed, verified) so the DUMB operator only has to **drag them from Add Object Fields** and set Label/Required/Width. Which skill:
- **GHL custom fields/tags are a Convert-and-Flow / Go High Level API concern** → use the **GHL-API skill** (the one that owns the GHL API key = the PIT `pit-…`) to `GET` existing custom fields/tags (idempotency check for a `zhc` match) and `POST` to create if missing.
- **`44-caf`** is the GHL **workflow/automation ("CAF") builder** — use it for the **Phase-N tagging workflow** ("Form Submitted → Add Tag `zhc…`"), **not** for creating the custom field itself.
- (Confirm exact skill IDs/entry points against the live Skill index before wiring — see Ambiguities.)

---

## Selector / anchor reference (captured)

| # | Element (visible text) | Region / position | Primary anchor (operator) | DOM guess | Confidence |
|---|---|---|---|---|---|
| 1 | Sites | left rail, globe, ~x42,y260 | text "Sites" | nav globe item | hint |
| 2 | Forms | orange top nav, ~x815,y50 | text "Forms" | `a[href*=form]` | hint |
| 3 | All forms (tab) | forms header, ~x237,y90 | text "All forms" | — | hint |
| 4 | + Create form | top-right, ~x1230,y90 | role button /Create form/ | — | hint |
| 5 | Start from Scratch (card) | modal left, ~x540,y210 | text "Start from Scratch" | radio card | hint |
| 6 | From templates (card) | modal right, ~x745,y210 | text "From templates" | radio card | hint |
| 7 | Create (modal) | modal bottom-right, ~x825,y405 | role button /^Create$/ | — | hint |
| 8 | Form-name text + ✎ | top bar center, ~x625,y17 | text /^Form \d+$/ | editable title | hint |
| 9 | Preview | top-right, ~x1095,y17 | role button /Preview/ | — | hint |
| 10 | Integrate | top-right, ~x1170,y17 | role button /Integrate/ | — | hint |
| 11 | Save | top-right, ~x1240,y17 | role button /^Save$/ | — | hint |
| 12 | + (add element) | toolbar left, ~x27,y50 | first toolbar icon | — | runtime |
| 13 | ⇄ Styles and Options | toolbar right, ~x1246,y50 | last toolbar icon | — | runtime |
| 14 | Quick Add (tab) | left panel, ~x60,y104 | text "Quick Add" | — | hint |
| 15 | Add Object Fields (tab) | left panel, ~x178,y104 | text "Add Object Fields" | — | hint |
| 16 | State (tile) | Address group, ~x190,y254 | text "State" tile | — | hint |
| 17 | City (tile) | Address group, ~x115,y254 | text "City" tile | — | hint |
| 18 | Rating (tile) | Rating group, ~x40,y335 | text "Rating" tile | — | hint |
| 19 | Label (prop) | right panel | label "Label" input | — | runtime |
| 20 | Query Key (prop) | right panel | label "Query Key" input | — | runtime |
| 21 | Field Width (prop) | right panel | label "Field Width" input | — | runtime |
| 22 | Required (prop) | right panel | checkbox "Required" | — | runtime |
| 23 | Hidden (prop) | right panel | checkbox "Hidden" | — | runtime |
| 24 | ADVANCED SETTINGS (disclosure) | right panel | text "ADVANCED SETTINGS" | — | hint |
| 25 | Custom Field Name (prop) | right panel | label "Custom Field Name" input | — | runtime |
| 26 | Unique Key (read-only) | right panel | label "Unique Key" input (disabled) | — | runtime |
| 27 | RATING SETTINGS (disclosure) | right panel | text "RATING SETTINGS" | — | hint |
| 28 | Icon row (star/heart/thumbs/flag/globe) | right panel | nth button in Icon row | — | runtime |
| 29 | How to Store … (dropdown) | right panel | label "How to Store Rating Fields…" | — | runtime |
| 30 | Contact (object dropdown) | Add Object Fields | combobox "Contact" | — | runtime |
| 31 | + Add (custom field) | Add Object Fields | role button /Add/ near Contact | — | runtime |
| 32 | Search by Name | Add Object Fields | placeholder "Search by Name" | — | hint |
| 33 | `<custom folder>` (folder) | Add Object Fields | text /`<folder name>`/ | — | hint (client data) |
| 34 | Facebook URL (field row) | folder list | text "Facebook URL" row | ⋮⋮ handle | hint |
| 35 | Styles / Themes / Advanced (tabs) | right styles panel | text "Styles"/"Themes"/"Advanced" | — | hint |
| 36 | CUSTOM CSS (disclosure + editor) | Advanced tab bottom | text "CUSTOM CSS" | code textarea | runtime |
| 37 | Privacy Policy / Terms (Text element) | form footer | text "Privacy Policy" | rich-text block | hint |
| 38 | Embed Code / Share / Email (menu) | Integrate modal left | text of each | — | hint |
| 39 | Embed Layout Type (Sticky/Slide-in/Popup/Inline) | Integrate modal | text of each option | — | hint |
| 40 | Copy embed code | Integrate modal bottom-right | role button /Copy embed code/ | — | hint |
| 41 | Copy Link field | Share tab | text field w/ /widget/form/ URL | — | hint |
| 42 | Open Form Link | Share tab | role button /Open Form Link/ | — | hint |

**Total distinct anchors captured: 42.**

---

## Ambiguities / not clearly shown in the video

1. **Real DOM selectors** — the builder is a cross-origin `leadconnectorhq.com` iframe; no `id`/`data-*`/`aria-label` is legible from frames. All anchors are visible-text/position; operator MUST re-snapshot at runtime.
2. **Tagging** — video shows **no** form-level tag control and **no** workflow; the `tag/merge` icon in the Text editor is for custom-value insertion, not contact tags. The Phase-N workflow path is **inferred** (standard GHL), not demonstrated.
3. **`+ Add` inline custom-field dialog** (Add Object Fields tab) — the button is visible but never clicked; its create-field dialog fields/behavior are **not shown**.
4. **Delete-field interaction** — narration says defaults "can be deleted"; the exact trash-icon click isn't demonstrated (gear+trash icons are visible on a selected field's blue bar).
5. **Settings / Notifications / Submissions tabs** — never opened; on-submit action, redirect/thank-you, notifications config are **out of frame** (relevant if the skill needs post-submit behavior).
6. **Themes tab grid** — narration says "choose from pre-created themes," but the theme options aren't shown.
7. **Integrate → Email tab** — narration ("select a template and email the form") but the panel UI isn't shown.
8. **Preview panel** — the Preview button is clicked/hovered (`t010920`) but the resulting preview view isn't captured in a frame.
9. **Native drop-in on a funnel/website page** — the video only reaches **Copy embed code**; it does **not** show pasting the form into a GHL funnel/website page via the page-builder's native Form element. That embed-into-page step is **assumed downstream**, not demonstrated.
10. **Custom Field Name typo** — video typed `postcastrating` (should be `podcastrating`); confirms "lowercase one word" convention but the demo value has a typo.
11. **Exact API/skill IDs** — "GHL-API skill" vs "44-caf" roles are reasoned from naming; confirm against the live Skill index before wiring the custom-field/tag automation.
12. **`+` vs `⇄` toolbar icons** — icon-only buttons; mapping (`+`=add element, `⇄`=Styles/Options) is inferred from behavior across frames, not from labels.
13. **Text Box vs Text Box List / Picture Date Picker / Score** — some Quick-Add tiles listed in narration weren't all individually legible; taxonomy merges frame + narration.
