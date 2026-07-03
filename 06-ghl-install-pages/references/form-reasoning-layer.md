# REASONING-LAYER — how the SMART agent decides the form, fields, custom fields, and tags

**Who runs this:** a high-reasoning model (the fleet's top thinking tier —
never the browser-operator model). Its whole job is to remove EVERY decision
from the dumb browser layer. Output = three resolved artifacts
(`form-plan.json`, `form-dependency-plan.json`, `form-click-list.json`) + the
run ledger. The browser gets zero judgment calls.

> ⚠️ Convert and Flow = Go High Level = GHL — one platform. Never a non-GHL tool name.

---

## 1. Inputs

- The owner/client request (verbatim — client sovereignty: build EXACTLY what
  was asked, never floor/cap/substitute).
- Client context: location_id, brand (colors/fonts for CSS), privacy/terms
  URLs, business name + SMS use-case for consent copy, target funnel/website
  page for the embed, downstream automation intent.
- Live location state via Skill 44: existing custom fields, tags, folders,
  workflows (the idempotency baseline).

## 2. Decide the form PURPOSE (what / why / for whom)

Answer in writing before anything else:
1. **What** is this form? (lead capture / event registration / intake /
   feedback / application / order.)
2. **Why** — what business outcome does a submission trigger? (new lead in
   pipeline X, booking, segmentation, follow-up sequence.)
3. **For whom** — who fills it in, on what device, at what funnel stage? (Cold
   traffic → fewest fields; booked client intake → richer fields tolerated.)
4. **Single-step?** Forms are single-step. Multi-step / conditional journeys →
   route to the SURVEY rail instead. Do not force a survey into a form.

## 3. Decide the FIELD SET

**Doctrine: minimum viable ask, standard-first, custom-last.**

1. Start from the conversion-proven core (video 16:44): First Name, Last Name,
   Phone, Email, Submit. The scratch form pre-seeds exactly these (+ consent
   checkboxes + footer) — plan deletions/keeps explicitly.
2. For every additional datum, map it to a **standard field** if one exists
   (Quick Add: Personal Info · Address [Address/City/State/Country/Postal
   Code/Organization/Website] · Text · Choice · Rating · Other). Standard
   fields have clean query keys (`city`, `state`) and no custom-field debt.
3. **Custom field ONLY when no standard fits** (e.g. "podcast rating",
   "show title"). Each one costs CRM schema forever — justify it.
4. Per field, fix ALL properties now: `label` (human), `type`, `required` XOR
   `hidden` (never both), `width%` (50% to pair two on a row), `placeholder`,
   `query_key` (lowercase, no spaces — doubles as the URL-prefill param),
   type-specific settings (e.g. Rating: icon/count/store-as — store-as
   Absolute|Percentage|Fraction changes the DATA SHAPE, so pick it to match
   how automations will read the value).
5. **Hidden fields** carry data the visitor shouldn't see (score, campaign
   value, phase-passing). A hidden field still needs a source (URL param via
   query key, or preset value).
6. Layout/readability: use Text/HTML elements to segment anything > ~7 inputs
   (video 16:44 — "not a wall of 20 fields"); order fields easy→sensitive;
   phone/email required only if the follow-up truly needs them.
7. Consent + compliance are part of the field set: SMS consent checkbox copy
   (business name + use case — A2P/TCPA), privacy + terms URLs. Placeholders
   `[BUSINESS NAME]` etc. must be resolved HERE, in the plan.

## 4. Decide the CUSTOM FIELDS (and pre-create them via the API)

**Pinned convention (zhc marker):**
- Custom-field **unique key** = `zhc_<snake_slug>` → `{{contact.zhc_<slug>}}`.
  Example: `zhc_podcast_rating`. Label stays human ("Podcast Rating").
- **Which skill creates them: Skill 44 — `44-convert-and-flow-operator` (the
  `caf` CLI).** Reasoning: "44-caf" and "the GHL-API skill" are the SAME skill
  — Skill 44 is the Tier-0 GHL API operator holding the LOCATION PIT, already
  lists custom fields/values (`locations`), already enforces
  dependencies-before-builds, and Skill 6's own doctrine says "grocery-shopping
  rule: pre-build forms/calendars/tags/workflows (Skill 44) BEFORE the page."
  There is no separate GHL-API skill to prefer.
- **Idempotency (GET-first):** list existing fields/tags → exact `zhc_` key
  match ⇒ `action:"reuse"`; else `action:"create"`. Also scan for an existing
  NON-zhc field of the same meaning (e.g. client already has "Podcast Rating")
  — if found, surface it to the owner rather than silently duplicating the
  semantic; default to reuse-with-approval.
- **Type mapping:** choose the GHL field type that matches the form element
  (Rating→number-like per store-as; Dropdown→options list must match EXACTLY
  what the form shows; Date→date; File→file). A mismatch breaks the
  Add-Object-Fields drag or the stored data.
- **Why pre-create instead of in-browser on-the-fly:** the on-the-fly path
  (video 08:01–10:23) makes GHL mint a random unique key which a weak operator
  must then rename — typo-prone (the video itself typo'd `postcastrating`),
  un-prefixed by default, and non-idempotent. Pre-created fields appear in
  **Add Object Fields** with the name/key LOCKED — the browser can only drag
  them, which is exactly the safety property we want. On-the-fly is therefore
  DISALLOWED (preflight `F-P7`).

## 5. Decide the TAGS

- Tag value = `zhc_<snake_slug>` (GHL lowercases tags), e.g. `zhc_podcast_lead`.
- One intent per tag (source/interest/status). Reuse an existing `zhc_` tag of
  the same intent (GET-first) — never mint near-duplicates
  (`zhc_podcast_lead` vs `zhc_podcastlead`).
- **Attachment decision — form setting vs workflow:** the GHL form builder has
  NO native add-tag control (verified across the whole video). Canonical =
  **Skill 44 workflow: trigger "Form Submitted" (this form) → action "Add
  Contact Tag"** — built AFTER the form ID exists, under Skill 44's PLAN-MODE +
  WF-1..21 + rubric gates. Alternative (documented, non-default, must be
  live-verified first): hidden Tags object-field with a preset value.
- Creation (Skill 44, pre-build) and attachment (workflow, post-build) are two
  different steps — plan both.

## 6. Decide the EMBED method + styling

| Situation | Method |
|---|---|
| Form inside a Skill-6-built GHL funnel/website page (default) | **JS embed snippet, Layout=Inline**, spliced VERBATIM (no SRI attrs) into a `ghl_rest_canvas` code element — the existing `SKILL44_WIDGET → FORM` path |
| Overlay behavior wanted (exit intent, delayed) | JS snippet with `Popup` / `Polite slide-in` / `Sticky sidebar` + trigger/activation options |
| External (non-GHL) site, or hard isolation | Direct link `…/widget/form/<formId>` as an iframe src |
| Human-owned page edited manually in the GHL builder | Native page-builder Form element (documented alternative; not the agent default — more fragile navigation, no determinism gain) |

**Styling levers (in order of precedence, low→high):** Styles tab (Layout /
Colors & Background) → Themes → Advanced per-section (FORM / INPUT FIELD /
LABEL / SHORT LABEL / PLACEHOLDER) → **Custom CSS box (overrides everything)**
→ host-page CSS wrapper around the embed. Author brand CSS once, put the
form-side rules in the Custom CSS box and page-side spacing/max-width rules in
the wrapper. Must hold up on mobile (the 50% pairs stack) — QC screenshots
both breakpoints.

## 7. Emit the artifacts (the handoff)

1. `routing/form-plan.json` — resolved intent: `ZHC ` form name, ordered field
   list with every property final, consent/footer copy, style + custom CSS,
   embed method + target page, tag plan, on-submit behavior.
2. `routing/form-dependency-plan.json` — custom fields + tags with `zhc_` keys,
   types, and `create|reuse` actions → **executed by Skill 44 BEFORE any
   browser step**; results (IDs) written to the run ledger.
3. `routing/form-click-list.json` — the fully-resolved click script per
   `form-browser-operator-instructions.md` (every `{{PLACEHOLDER}}` filled; every
   step has find/act/wait/verify).
4. Preflight `F-P1..F-P8` must PASS before dispatching the browser.

## 8. After the browser returns

1. Read `form-operator-report.json`; treat operator claims as hypotheses.
2. Feed `form_id` to Skill 44 → build the tag workflow (Phase T).
3. Splice the embed snippet into the host page; run `ghl_verify.render_check`.
4. Dispatch the INDEPENDENT QC gate `../qc-built-form.sh` (see `../QC.md`); only a
   passing QC-F1..F10 report (render_check 200 + snippet marker in the RENDERED
   DOM) means done.
5. On failure: rollback per the run ledger — delete only THIS run's
   `action:"create"` artifacts, reverse order, never touch `reuse` artifacts,
   never delete a form holding submissions.
