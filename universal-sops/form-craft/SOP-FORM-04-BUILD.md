# SOP-FORM-04: THE DUMB BROWSER BUILD (F1..F13) + EMBED SPLICE

**Cluster:** Form-Craft Rules (`universal-sops/form-craft/`)
**Master authority:** `06-ghl-install-pages/tools/ghl_form_builder.py` (`_emit_click_list` F1..F13) + `SELECTORS-LIVE-form.md` + `references/forms-playbook.md`
**Owning role:** Skill 6 THINK layer emits the click list → **DUMB browser operator (agent-browser)** executes → embed splice via `ghl_rest_canvas`
**Stage:** P3-BUILD
**Produces:** `routing/form-click-list.json` (F1..F13) → `form-operator-report.json` + captured embed snippet + parsed form id + share/preview link + `shots/NNN-<phase>.png`
**Gates:** AF-FORM-AUTH-SEED, AF-FORM-BUILD-DRAFT, AF-FORM-EMBED-VERBATIM, AF-FORM-INVENTED-SELECTOR, AF-FORM-NAME-ZHC

---

## 0. WHY THIS SOP EXISTS

Skill 44 has pre-created the deps; now the browser does the ONE thing it is allowed to do — execute a
fully-resolved click list verbatim. **Skill 6 is the ONE GHL delivery rail.** The browser makes ZERO
decisions; every target string, label, width, and toggle is pre-specified by `_emit_click_list`.

## 1. AUTH — TOKEN-ONLY SEED (the gate that used to burn tokens)

Auth is the seeded token-only session (`seed-ghl-auth.py`: Firebase refresh token exchanged at
`securetoken.googleapis.com` → inject IndexedDB + SPA cookies → activate). **NO login form, NO 2FA.**
Hard rule confirmed live: **never `reload`/full-navigate after seeding** — the whitelabel boot IIFE
would re-run `firebase.signOut()`. All navigation is SPA `router.push` / in-SPA link clicks. A reload
after seed, or any UI-login path, ⇒ AF-FORM-AUTH-SEED.

## 2. THE ORDERED CLICK LIST (F1..F13)

| Phase | What the operator does |
|---|---|
| **F1** nav | Open the seeded app shell → Sites → **Forms** (top secondary-nav). |
| **F2** create | **Create Form** → Start from scratch (default) → **Create** → builder opens. |
| **F3** rename | Rename the default `Form <n>` to the **`ZHC <name>`** container name (F-P6 / AF-FORM-NAME-ZHC). |
| **F4** trim | Delete the default fields the brief did not keep (hover → Remove field). |
| **F5** standard | Drag each **Quick Add** tile onto the canvas; fill Label / Placeholder; set Field Width (50/100); set Query Key; check Required / Hidden. |
| **F6** custom | Open **Add Object Fields** (object = Contact); Search by the `zhc_` key; drag the **pre-created** field in (key + name LOCKED, only Label editable); apply type-specific settings; Required XOR Hidden. |
| **F7** save | **Save** → draft saved. |
| **F8** style | **Styles and Options** → Theme; Options → Advanced → **Custom CSS** (overrides styling + themes); Save. |
| **F9** preview | **Preview** → shows how the form displays. |
| **F10** integrate | **Integrate** → **Copy Embed Code** (capture the JS snippet) + capture the shareable form link. |
| **F11** embed | Splice the snippet into the target GHL page (see §4). |
| **F12** tag | Hand the tag-attach off to a Skill-44 workflow (see SOP-FORM-05). |
| **F13** verify | Form in the Forms list under the ZHC name + embed renders (see SOP-FORM-05). |

## 3. THE `[runtime-capture]` CONSTRAINT (never invent a selector)

The builder canvas is a cross-origin `*.leadconnectorhq.com` iframe. Through the CDP `@ref` rail only
true interactive leaves (buttons, textboxes, checkboxes, links, menuitems, radios) get refs. **Quick-Add
tiles, the Form-Element tabs (`Quick Add` / `Add Object Fields`), builder tabs, and field-property
inputs get NO ref** and cannot be reached by top-frame `text=` / CSS. They are `[runtime-capture]`:
snapshot-and-bind by visible text at runtime, drive by the builder's own drag/click event system.
**Refs churn every snapshot** — snapshot and act on that snapshot immediately. Shipping an invented CSS
selector for these surfaces instead of snapshot-and-bind / STOP-and-report ⇒ AF-FORM-INVENTED-SELECTOR.
Selector strategy per step: a11y ref first → exact visible-text fallback → STOP-and-report on miss;
explicit visible-text waits (no fixed sleeps); one action per step; a screenshot after every material
step.

## 4. EMBED SPLICE — VERBATIM, NO SRI

At F10 the operator retrieves the JS embed snippet (Layout = **Inline** for in-page) + the direct
`…/widget/form/<FORM_ID>` link. At F11 it is spliced **VERBATIM** into a `ghl_rest_canvas` code element
on the target funnel/website/landing page — the existing `SKILL44_WIDGET → FORM` path — with **NO
`integrity`/`crossorigin` (SRI) attributes** (GHL rotates the script). A CSS wrapper around the embed
(plus the form's own Custom CSS box) carries brand polish. Any alteration / re-minify / SRI attr on the
snippet ⇒ AF-FORM-EMBED-VERBATIM.

## 5. DRAFT ONLY

The build ends at a **draft + preview** — it never publishes. A build that goes live without human
approval ⇒ AF-FORM-BUILD-DRAFT. Every operator claim (steps done, embed captured, form id) is a
**hypothesis** until the independent QC gate (SOP-FORM-05) confirms it. Deliverable label:
`<client>__<form>__embed__vNN`.
