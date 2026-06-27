# GoHighLevel Build Spec — from Trevor's Transcript (AUTHORITATIVE)

**Skill:** 06 — ghl-install-pages
**Status:** Canonical build recipe. This is the source-of-truth, step-by-step procedure for an
agent building a funnel or website page inside GoHighLevel (Go High Level) / Convert and Flow.
**Foundation source:** Trevor's official walkthrough transcript
`Comprehensive Guide to Building Funnels and Websites in Go High Level 2.vtt`
(~21 min, WebVTT, narration fully read; timestamps below are guide-only).
**Authority model:** Every step here is sourced `transcript` (authoritative — Trevor stated/demonstrated
it) OR `minimax-suspect` (a click-through-research claim that is **probe-gated**, NOT authority — must be
proven by a live save round-trip before it constrains a build).

> Read this BEFORE `v2-autonomous-build-sop.md` and `gates.json`. Where the autonomous REST-first
> path and this transcript disagree on *coverage* (e.g. SEO panel, media folders), the transcript
> wins on *what must be true at the end* — the REST path must reach the same end-state.

---

## 0. Two pillars (Trevor's framing, ~00:35–01:14)

Skill 6 has two key elements an agent must master:
1. **Media storage / media library** (same thing — Trevor uses both names; the GHL setting should be
   unified so the system knows). Handled via **API / MCP / Skill 44 — NEVER browser control.**
2. **The Sites area** — funnels and websites — specifically the **Code Block** element.

"Grocery-shopping" principle (~21:13): think the funnel/page out **before** building — decide what
forms, calendars, tags, and workflows it needs, and **pre-build those first**.

---

## 1. The canonical build recipe (funnel path)

Ordered exactly as Trevor demonstrates. Each step tagged with source + whether the parallel harden
run owns its implementation.

| # | Step | Detail (from transcript) | Source | ownedByHarden |
|---|------|--------------------------|--------|---------------|
| 1 | **Sites → Funnels** | Left menu → Sites. Top orange bar shows Funnels / Stores / Webinars / Analytics / Quizzes / QR codes / Websites. Start on **Funnels**. (~02:49–03:19) | transcript | false |
| 2 | **New Funnel** | Blue **New Funnel** button, top-right. (~03:19–03:28) | transcript | false |
| 3 | **Name with ZHC prefix** | Every funnel AND every website built by the AI **must** carry a **`ZHC` prefix** so it is identifiable as agent-built. Example: `ZHC test`. (~03:28–03:47) | transcript | false |
| 4 | **Create** | Blue **Create** button. (~03:47–03:59) | transcript | false |
| 5 | **Add new step** | New page → **Add new step** (blue) (or Import). Name the step; ZHC-prefix it too (e.g. `ZHC test June 2026`). Optional **path** for organization (optional). (~03:59–04:39) | transcript | false |
| 6 | **Create funnel step** | Click **Create funnel step** → step is created but has **no content**. (~04:39–05:00) | transcript | false |
| 7 | **Create from blank** | Middle control box → **Create from blank** (or the Edit button — both open the builder). (~05:00–05:14) | transcript | false |
| 8 | **Close Ask AI** | Hit the **X** on the "Ask AI" panel — the internal AI is **not** used; this gives a clean window. (~05:14–05:32) | transcript | false |
| 9 | **Create a blank section** | Add a blank section to have something to work with. (~05:32–05:49) | transcript | false |
| 10 | **Add elements** | Top-right, next to Ask AI: the **+ (plus)** button = **Add elements**. (~05:49–06:04) | transcript | false |
| 11 | **Drag in a Code Block** | From Add elements (Custom area) drag the **Code Block** element into the section. There may be **one or several** code blocks depending on the design — agent decides the best layout. (~06:04–06:22) | transcript | false |
| 12 | **Select the GREEN box (section)** | Hovering shows a **GREEN box (the section)** and a **BLUE box (the element)**. Click the **GREEN** box → a **Sections** panel opens on the right. The green = section level; this is where the width toggle lives. (~06:22–06:56) | transcript | false |
| 13 | **Enable "Allow Rows to take entire width"** | In the Sections panel scroll down to **"Allow Rows to take entire width."** **MUST be ON (full width).** OFF/default = content is **condensed / scrunched to the MIDDLE** of the page (visible but thin) — not what we want. Most-emphasized point in the video (repeated 3+×). Gradient / background-blur / width options also live here; Styles/Padding tab if needed. (~06:56–07:35) | transcript | **true** |
| 13b | **Alt route: "Show settings" under Publish** | Newer/easier route to the same toggle: the **Show settings / Hide settings** icon directly **under the Publish button** (top-right) opens the Sections area → select **Allow Rows to take entire width.** Trevor calls it "an update, an easier way." Use as an alternate selector/path. (~12:06–12:26; repeated for websites ~18:10–18:25) | transcript | **true** |
| 14 | **Double-click the inner Custom HTML box** | With full-width set, **double-click** the **Custom HTML & JavaScript** (blue inner) box. A **Custom code** panel opens right, with a **General** tab where you can **name the element**. (~07:35–08:15) | transcript | false |
| 15 | **Open Code Editor** | Click **Open code editor** → a code box opens. (~08:15–08:19) | transcript | false |
| 16 | **Paste the code** | Paste **naked HTML** (straight HTML written for the GHL code-block area) **OR** the **Vercel embed code** when the page was built in Vercel first. (~08:19–08:31, 12:56–13:25) | transcript | false |
| 17 | **SAVE CODE (1st save)** | Inside the editor, hit **Save** to save the code. (~08:31–08:40) | transcript | false |
| 18 | **SAVE PAGE (2nd save)** | Then the **Save** box at top next to **Publish** — hit **Save** again. **Two saves: save the CODE, then save the PAGE.** Both are required. (~08:40–09:05) | transcript | false |
| 19 | **SEO / AI-search "Content" panel** | After saving, the left side shows **SEO and AI search optimization**. Expand the **Content** box and fill it out (see §2). (~09:05–10:16) | transcript | false |
| 20 | **Back → next step** | Hit **Back**; step 1 is added. For a multi-step funnel, **Add new step** again and number it **`ZHC part 2`** … `ZHC part N`. Repeat the whole recipe per step. (~10:16–10:45) | transcript | false |

---

## 2. SEO / AI-search "Content" panel — REQUIRED (transcript, ~09:05–10:16)

Trevor: *"content keywords authors and meta links tags and canonical links are added — this is really
key."* The autonomous REST path currently populates **none** of this; it is a real gap the build must close.

| Field | Rule | Source |
|-------|------|--------|
| **Description / metadata** | Fill out the page description and metadata for SEO. | transcript |
| **Keywords** | Must be **RESEARCHED**, not placeholder — "investigate the pre-keywords… use the power of your research to figure out best practices." | transcript |
| **Author** | **MUST be the name of the FOUNDER.** This is a build-time data dependency — the founder's name must be a required pre-flight input. | transcript |
| **Images** | Add any relevant images. | transcript |
| **Links + Tags** | Use the dropdown; add anything relevant. | transcript |
| **Language** | **English** (nothing to change). | transcript |
| **Schema markup** | Optional — add only if more relevant. | transcript |
| **Canonical links** | Add the canonical link. Called out explicitly as "really key." | transcript |
| **CSS** | Any CSS the page needs is handled in this build/code area too. | transcript |

---

## 3. Media storage discipline (transcript, ~01:14–02:42, 13:26–14:24)

- **One clearly-named folder per funnel/website**, with **subfolders** as needed. Clear organization
  is the main point. `source=transcript`.
- **Upload image → GHL returns a link → reference THAT media-storage link in the HTML.** That link is
  how images pull into the page. `source=transcript`.
- **NO browser control for media storage.** Use one of: **GHL API**, **GHL official MCP**, **GHL
  community MCP**, or **Skill 44** to create folders and upload. `source=transcript`.
- Tooling already exists: `ghl_media.py` (`create_media_folder`, `upload_media`, folder-name prefix).
  This run does **not** re-implement it; it documents the per-build STEP.

---

## 4. Pre-build dependencies — "grocery shopping" (transcript, ~19:24–21:27)

Think the funnel/page out first; build dependencies **in advance**:
- **Forms, calendars, tags, workflows** — create via **Skill 44 / GHL API / GHL community MCP** (not
  browser) before building the page, so they can be embedded. `source=transcript`.
- **Custom forms MUST push submissions into the contact record** — when a custom form is filled out it
  has to write into the person's CRM contact record. Already encoded as the form→CRM proof gate;
  reinforced here. `source=transcript`.

---

## 5. Websites path (transcript, ~16:26–18:55)

Identical recipe, different area:
- Sites → top orange bar → **Websites** → blue **New website** → name (ZHC) → **Create**.
- **Add new page** → name it; **all pages must carry the `ZHC` prefix** (home, about, etc. — add as
  many pages as needed). `source=transcript`.
- **Create from blank** → close Ask AI (X) → **+ Add elements** → drag **Code Block** → use the **Show
  settings** icon under Publish → **Allow Rows to take entire width** → open code editor → paste →
  **save code then save page** → SEO panel. Same process, repeated per page. `source=transcript`.

---

## 6. Naked-HTML vs Vercel-embed decision (transcript, ~18:59–19:24)

- **Naked HTML** — write straight HTML compatible with the GHL code-block area and paste it in. Default.
- **Vercel embed** — when the page "has a lot of special features… things you might not be able to
  render through the code block area," build the funnel/page in **Vercel** and pull it in via the
  **embed link / embed code** pasted into the code editor. Trevor's demonstrated escape hatch.
  `source=transcript`.

> NOTE (probe-gated): the click-research claim that "GHL strips `<iframe>` on save" is
> **minimax-suspect** and is **contradicted in direction** by this demonstrated Vercel-embed workflow
> (which presupposes the embed renders). Do NOT let any sanitizer lint ban `<iframe>` until a live save
> round-trip settles it. The harden run owns that live probe (see §8).

---

## 7. Auth / token discipline (transcript, ~14:26–15:29)

The reason an agent gets into the page easily is the seeded **Firebase refresh token**. Trevor's
explicit instruction:
- **Never assume** a client lacks a **private integration token**, a **location ID**, or a **Firebase
  refresh token.** `source=transcript`.
- **Search ALL environments** before concluding you lack a credential: OpenClaw secrets, the box's
  `.env`, and — on a VPS — the **Docker** environment area AND the **OpenClaw** environment area. Do a
  thorough search; only then state clearly that the info is missing. `source=transcript`.

> The harden run owns the **3 auth-seed fixes**; this run only records the transcript instruction.

---

## 8. Probe-gated (minimax-suspect) claims — NOT authority

These came from the MiniMax click-through research, may be hallucinated, and must be proven by a LIVE
save round-trip before they constrain a build. **All are owned by the parallel harden run** (its live
iframe/strip/empty probe + sanitizer lint), not this run.

| Claim | Status | Source | ownedByHarden |
|-------|--------|--------|---------------|
| GHL strips `<iframe>` on save | UNRESOLVED — transcript leans AGAINST (Vercel-embed escape hatch). Do not ban iframe pre-proof. | minimax-suspect | **true** |
| GHL strips `<script>` / external CSS on save | NOT demonstrated in transcript — live-probe required. | minimax-suspect | **true** |
| Empty / near-empty code element renders blank | NOT addressed in transcript — live-probe required. | minimax-suspect | **true** |
| Exact `allowRowMaxWidth` pixel width when OFF (~1170 centered) | Direction confirmed by transcript (condensed-middle); exact px is live-check. | minimax-suspect | **true** |
| `gates.json` selectors as the *only* path to the toggle | Transcript adds the Show-settings route; selectors are priors, not authority. | minimax-suspect | **true** |

---

## 9. Ownership boundary (do not fight the harden run)

The parallel harden run (`wu9dnrsak`) OWNS and is implementing, and this run builds **alongside**, not
against, these:
- the full-width `allowRowMaxWidth` default (steps 13 / 13b above are documentation of its target)
- the un-fakeable `render_check` (P0)
- the child-link-chain invariant
- the LIVE iframe / strip / empty probe + sanitizer lint (§8)
- selectors-as-priors in `gates.json`
- the 3 auth-seed fixes (§7)
- the rate-limit governor

**This run owns the transcript BUILD-RECIPE items** (§1 steps, §2 SEO panel, §3 media discipline, §4
pre-build, §5 websites, §6 naked-vs-embed) — the authoritative end-state every build must reach.
