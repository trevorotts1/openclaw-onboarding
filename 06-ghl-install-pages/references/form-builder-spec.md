# Skill 6 — FORM Builder (Convert and Flow / GHL) — DESIGN / SPEC

**Status:** DESIGN + REVIEWABLE DRAFT. **PENDING-LIVE-RUN.** Dry-run is the default
and the only path exercised in this review. In-app selectors are **runtime
snapshot-gates** (snapshot the live DOM, pick the ref at runtime) — no invented
CSS is shipped as fact, matching the rest of Skill 6.

**Scope:** Add a FORMS capability to Skill 6 — the ONE GHL delivery rail (funnels,
websites, surveys already exist; this ADDS forms). Capabilities: create a form;
add standard + custom fields; retrieve the embed / JavaScript snippet; embed the
form inside a GHL page/funnel/website (with CSS polish); attach tags.

> ⚠️ **Naming:** *Convert and Flow = Go High Level = GHL* (also `leadconnectorhq.com`
> on the builder iframe) — one platform. Any third-party form-tool name that may
> appear in a source caption filename is a **mislabel** — this is Go High Level.
> Never write a non-GHL tool name in any deliverable.

**Sources:** the Go High Level form-builder walkthrough video (1134.5 s) with its
captions and keyframes, normalized into the canonical transcript. Custom-field
pull technique cross-checked against the GHL survey custom-field-pull walkthrough.

---

## 1. The core problem: a DUMB browser operator

The agent BROWSER OPERATOR is not smart — it frequently runs on **MiniMax-M3**
(see `EXECUTE_LADDER` in `ghl_form_builder.py` and `ghl_survey_builder.py`), far
weaker than the reasoning model. If we hand it a fuzzy goal ("build a signup
form"), it will guess field names, invent keys, mis-drag elements, and skip the
embed step. So the design is a **hard two-layer split**.

### Layer 1 — SMART / THINK (reasoning model; this is `ghl_form_builder.py`)
Decides **what** and **why**, then removes all ambiguity:
- Chooses the **standard** fields (Quick-Add tiles) and their exact label /
  width / required / hidden / placeholder / query-key.
- Chooses the **custom** fields + **tags**, derives their **`zhc_` keys**, and
  emits a **dependency plan** the GHL-API layer (Skill 44) pre-creates.
- Picks the **embed target** (funnel/website/page) and any **custom CSS**.
- Emits a fully-explicit, ordered **click list** (`form-click-list.json`) — every
  target string spelled out — plus `form-plan.json` and
  `form-dependency-plan.json`.

### Layer 2 — DUMB / DO (MiniMax-M3 browser operator via agent-browser)
Executes the click list **verbatim**. Makes **no decisions**. On every step:
1. **a11y ref first** — `snapshot -i` → pick the `@eN` ref for the target text/role.
2. **visible-text fallback** — click the exact verbatim `target` string.
3. **documented CSS last** — never invent CSS as fact.
4. **explicit waits** on visible text before and after each step (no fixed sleeps).
5. **screenshot** after each material step.
6. **one action per command.**

This mirrors the proven survey-builder split (`tools/ghl_survey_builder.py`,
"GLUE, NOT THE CLICKER"). The forms tool is the same shape.

---

## 2. Where custom fields + tags come from (NOT the browser)

The video shows two ways to get a custom field onto a form:

| Path | What happens | Verdict for agent builds |
|---|---|---|
| **A. Create-on-the-fly** (drag e.g. Rating) | GHL invents a **random unique-key suffix** ("rating rat584…"); a human then opens Advanced Settings → Custom Field Name and renames it lowercase-one-word (08:01–10:23) | **DISALLOWED.** Leaves naming + a random key to the dumb browser = fragile, un-prefixed, non-idempotent |
| **B. Add Object Fields** (drag a PRE-CREATED field) | The field's **unique key + custom-field name are LOCKED**; only the **Label** is editable (12:14–14:12) | **CANONICAL.** Deterministic, idempotent, carries the `zhc_` marker |

**Decision:** the THINK layer **pre-creates every custom field and tag through the
GHL-API operator, then the browser only DRAGS them in via Add Object Fields.**

### Which skill creates them? → Skill 44 (`44-convert-and-flow-operator`)
Reasoned from the repo:
- Skill 44 is the **Tier-0 GHL operator** — the `caf` CLI (aka `convertandflow`/
  `ghl`), **PIT-authenticated**, giving direct CRM access to contacts (tag/untag),
  **locations (list custom fields / custom values)**, forms, and **workflow builds**.
- Skill 44 already **"REFUSES to build a workflow whose dependencies (tags, custom
  fields, custom values) are missing"** — i.e. it is the component that
  creates/looks-up these objects.
- Skill 6's own doctrine already says **"grocery-shopping rule: pre-build
  forms/calendars/tags/workflows (Skill 44) BEFORE the page."**

So: **custom fields + tags = Skill 44 (`caf`, LOCATION PIT).** (The generic
"GHL-API skill" people mean *is* Skill 44 — there is no separate one.) The
form-builder emits a normalized **dependency plan**; Skill 44 consumes it (exact
`caf` subcommand names live in Skill 44's own reference — this design does not
invent flags). The survey builder currently creates fields **in-browser** (its
Part 1); **this forms design deliberately moves that to the API layer** for
determinism, idempotency, and enforceable `zhc_` prefixing — a recommended
convergence for the survey builder too (see §9).

---

## 3. The `zhc` agent-created marker — PINNED convention

Every agent-created custom field and tag must be auditable and de-duplicated.

| Object | Convention | Example | Enforced by |
|---|---|---|---|
| **Custom field unique key** (GHL "custom field name"; lowercase, no spaces) | `zhc_<snake_slug>` | `zhc_podcast_rating` → `{{contact.zhc_podcast_rating}}` | `zhc_field_key()`, preflight `F-P4` |
| **Tag** (GHL lowercases tags) | `zhc_<snake_slug>` | `zhc_podcast_lead` | `zhc_tag()`, preflight `F-P5` |
| **Form NAME** (container in the Forms list) | UPPERCASE `ZHC ` prefix (fleet convention, = `ghl_builder.ensure_zhc_prefix`) | `ZHC Podcast Signup Form` | `ensure_zhc_name()`, preflight `F-P6` |

**Two conventions on purpose:** container **NAMES** use `ZHC ` (matches the funnel/
website/step naming already in `ghl_builder.ensure_zhc_prefix`); machine **KEYS +
TAGS** use lowercase `zhc_` because GHL requires lowercase / no-space keys and
lowercases tags. The client-facing **Label** stays human ("Podcast Rating") — the
marker lives in the KEY, not the label.

**Idempotency (no duplicates).** BEFORE creating anything, Skill 44 GETs the
location's existing custom fields + tags. `plan_dependencies()` stamps each entry
`action: "reuse"` (key/name already equals the target `zhc_…`) or `"create"`
(the remainder). Proven in the example: `zhc_facebook_url` → **reuse**,
`zhc_podcast_rating` → **create**. On a real run the `existing_field_keys` /
`existing_tags` inputs come from Skill 44's live listing (`live_get_required:true`
until then).

---

## 4. Canonical build recipe (the ordered click script)

Distilled from `../transcript.md` (canonical) with video timestamps + phase IDs.
The dumb browser receives these as `form-click-list.json`. Selector strings below
are the **visible-text fallback**; the a11y ref is resolved at runtime.

| Phase | Action | Verbatim target(s) | Video ts / frame |
|---|---|---|---|
| **F1 Navigate to Forms** | left nav **Sites** → Funnels page → top secondary nav **Forms** (~¾ across) | `Sites`, `Forms` | 00:05–00:56 |
| **F2 Create form** | blue **Create Form** (top-right; fallback `Add Form`) → leave **Start from scratch** selected (or pick template) → blue **Create** at bottom of pop-up | `Create Form`, `Start from scratch`, `Create` | 00:56–01:39 |
| **F3 Rename form** | click default **`Form N`** at top → type **`ZHC <name>`** → **Enter** | `Form 1`, `<ZHC name>`, `Enter` | 04:22–05:03 |
| **F4 Trim defaults** | delete unneeded defaults (First/Last/Phone/Email/T&C are auto-added) | per-field trash | 01:39–02:27 |
| **F5 Standard fields (Quick Add)** | left **Form Elements** → drag tile from its **category** onto the canvas → right panel: **Label**, **Placeholder**, **Field Width** (50% packs two per row), **Query Key** (URL param — lowercase/no-space), **Required**/**Hidden** | e.g. `City`, `State`, `Field Width = 50%`, `Required` | 05:03–08:16 |
| **F6 Custom fields (Add Object Fields)** | **second left tab** **Add Object Fields** (NOT Quick Add; Object = Contact) → **Search by Name** the `zhc_` key → **drag** in → set **Label** (key locked) → field-type settings (e.g. Rating icon/count/store) → **Required**/**Hidden** (not both) | `Add Object Fields`, `Search by Name`, `<label>`, `Required` | 12:14–14:12 (+10:35–12:14 for Rating settings) |
| **F7 Save draft** | blue **Save** (top-right) | `Save` | 14:16–14:31 |
| **F8 Style** | **Styles and Options** (under Save): field-level vs form-level (**Options → Advanced**): border width / corner radius / colors; **Custom CSS** (overrides themes); **Themes** tab; **Styles** tab (Layout / Colors & Background / Miscellaneous=agency branding) → Save | `Styles and Options`, `Options`, `Advanced`, `Custom CSS`, `Save` | 14:26–16:44 |
| **F9 Preview** | **Preview** (top-right) | `Preview` | 18:14–18:23 |
| **F10 Integrate → embed** | **Integrate** (top-right) → blue **Copy Embed Code** (JS snippet) + **Share** (link/social) + **Email** (template); capture snippet **and** form link | `Integrate`, `Copy Embed Code` | 18:23–18:54 |
| **F11 Embed into page** *(handoff)* | paste snippet **VERBATIM (no SRI)** into a `ghl_rest_canvas` code element on the target funnel/website/page; optional CSS wrapper; then `ghl_verify.render_check` | — | design |
| **F12 Attach tags** *(handoff)* | Skill 44 builds **Form Submitted → Add Contact Tag** workflow (tags already `zhc_`-created); alt = hidden Tags object-field | — | design (13:43–14:12 hints hidden-field tags) |
| **F13 Verify** | form in Forms list under `ZHC ` name; `render_check` 200 + snippet marker in RENDERED DOM; custom fields/tags re-GET 200 | — | design |

**Required + Hidden are mutually exclusive** (14:09–14:12) — enforced in
`_resolve_fields` (forces `hidden=False` and records a warning). **Hidden** fields
are for score / a tag to pass / data for the next phase (13:43–14:09).

---

## 5. Embedding the form + CSS styling

- **Retrieve:** F10 captures the **JavaScript embed snippet** ("Copy Embed Code")
  and the shareable **form link**.
- **Embed:** F11 hands the snippet to Skill 6's existing page-blob splice
  (`ghl_rest_canvas` code element). This is exactly the **`SKILL44_WIDGET → FORM`**
  path already in SKILL.md's Phase-5 method table: *"embed the GoHighLevel-generated
  snippet **verbatim (no `integrity`/`crossorigin` SRI attrs)** — GHL rotates the
  embed script and SRI hashes break on the next deploy."*
- **Make it look good:** two levers — (1) GHL **Custom CSS** box inside the form's
  Styles & Options (overrides themes; set from `task['custom_css']` at F8), and
  (2) a CSS wrapper around the embed in the host page's code element at F11.
- **Verify:** the snippet `<script>`/`<iframe>` tag must appear in the **rendered
  (JS-hydrated) DOM** via `ghl_verify.render_check` (200 + marker). A 201 autosave
  is not proof.

---

## 6. Tags: creation vs. attachment (they are different)

- **Creation** = Skill 44 makes the `zhc_<slug>` tag on the location (idempotent
  GET-first). Done in the dependency plan, BEFORE the browser build.
- **Attachment** = how a submitting contact GETS the tag. **GHL's form builder has
  no native "add tag" control.** Canonical, testable path: a Skill-44 **"Form
  Submitted → Add Contact Tag"** workflow (built AFTER the form exists — it needs
  the form id; Skill 44's PLAN-MODE + WF-1..21 + rubric ≥ 8.5 gates apply).
  Documented alternative: a **hidden Tags object-field** with a preset value
  (the transcript's "a new tag you want this person to have" via hidden fields).
- The dumb browser does **none** of this.

---

## 7. Preflight gates (THINK layer, before any browser step)

`_run_preflight` (hard-stops unless noted):
- `F-P1 location_id` present · `F-P2 location_gate` (no co-mingling; delegated) ·
  `F-P3 spec_present`.
- **`F-P4 zhc_field_keys`** — every custom field key starts `zhc_`.
- **`F-P5 zhc_tags`** — every tag starts `zhc_`.
- **`F-P6 zhc_form_name`** — form name carries `ZHC `.
- **`F-P7 custom_via_object_fields`** — every custom field routed via Add Object
  Fields (create-on-the-fly disallowed).
- `F-P8 headless_guard` (soft in review; live-enforced via `ghl_builder`).

Plus the inherited Skill-6 invariants: seeded token-only session (no login/2FA),
correct sub-account, singleton pooled browser via `browser_manager`, `RateGovernor`
spacing on saves, never publish without approval, run-evidence written OUTSIDE the
skill dir.

---

## 8. Files in this proposal

| File | Role |
|---|---|
| `../tools/ghl_form_builder.py` | Tool — mirrors `ghl_survey_builder.py`. `build_form(task, evidence_root, dry_run=True)`; `--dry-run` default, `--selftest`, CLI. THINK-only in dry-run; live path is a spec skeleton (PENDING-LIVE-RUN). Standalone-runnable (soft imports). |
| `../tools/examples/form-click-list.example.json` | Example dumb-browser click script (F1–F13, 54 steps) for a "Podcast Signup" form. |
| `../tools/examples/form-dependency-plan.example.json` | Example Skill-44 handoff: custom fields + tags with `zhc_` keys + create/reuse actions. |
| `../tools/examples/example-run/routing/*` | Full example dry-run output (plan, dependency plan, click list, preflight). |
| SKILL.md prose | Applied to `../SKILL.md` (capability #15 + tools entry + Critical-Things bullets). |
| `forms-playbook.md` | Operator-facing orientation + how to review + run. |

Verified: `python3 ghl_form_builder.py --selftest` → PASS (zhc enforcement,
idempotency reuse, no-both required/hidden, all F1–F13 phases present, embed +
tag handoffs present, no banned/purged model slugs, no non-GHL tool-name leak).

---

## 9. Open questions / risks for the reviewer

1. **Live selectors are unproven.** F1–F13 targets are transcript-derived and
   **runtime snapshot-gated**. First live run on a **test sub-account** must
   confirm: the `Forms` sub-nav label, `Create Form` vs `Add Form`, the form-builder
   iframe host/path (`form-builder-v2/<formId>`?), the `Add Object Fields` tab
   label, `Styles and Options` / `Integrate` / `Copy Embed Code` strings, and the
   default-name pattern (`Form 1`).
2. **Custom-field creation moved to API** — diverges from the survey builder's
   in-browser Part 1. Recommend converging the survey builder onto the same
   API-first + `zhc_` path (out of scope here; flag only).
3. **Rating "store as"** (absolute/percentage/fraction) affects the custom-field
   data type — confirm Skill 44 creates the matching field type.
4. **Tag attachment default** is `workflow`; confirm the hidden-Tags-object-field
   alternative actually assigns tags in current GHL before offering it.
5. **QC gate:** forms should ride the same `qc-built-*.sh` / render_check evidence
   discipline; define a `qc-built-form.sh` (analogous to `qc-built-funnel.sh`)
   before flipping `--no-dry-run`.
6. **No live run claimed.** Consistent with SKILL.md's PENDING-LIVE-RUN posture.
