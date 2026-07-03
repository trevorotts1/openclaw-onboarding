# FORM-CREATION-CHECKLIST — everything that must happen to create a GHL form

**Rail:** Skill 6 (`06-ghl-install-pages`) — the ONE GHL delivery rail (funnels /
websites / surveys already; this ADDS forms).
**Sources:** the Go High Level form-builder walkthrough video (watched, 167 frames),
its canonical transcript, `form-click-map.md` (42 anchors), cross-checked against
the GHL survey custom-field-pull technique.

> ⚠️ **NAMING.** Convert and Flow = Go High Level = GHL = one platform (builder
> iframe is `leadconnectorhq.com`). Any third-party form-tool name that may appear
> in a source caption filename is a **mislabel** — this is Go High Level. Never
> write a non-GHL tool name in any deliverable.
> 🔒 **Fleet-wide repo.** No client names, domains, or form IDs in any committed file.

**Two-layer doctrine (governs every item below):** the SMART reasoning layer
(high-reasoning model) does ALL deciding and emits fully-explicit artifacts; the
DUMB browser operator (often MiniMax-M3) only executes. If any checklist item
requires judgment, it belongs to the SMART layer — never the browser.

---

## PHASE 0 — PRE-FLIGHT (SMART layer; NOTHING touches a browser yet)

### 0.1 Purpose — what / why / for whom
- [ ] **P0-1** State the form's PURPOSE in one sentence (lead capture / registration /
      intake / feedback / application). No purpose → no build.
- [ ] **P0-2** State WHO fills it in (visitor persona) and WHAT happens after
      submit (workflow, pipeline, calendar, email). This drives fields + tags.
- [ ] **P0-3** Confirm this is a single-step FORM. Multi-step / branching intake
      → that is the SURVEY rail (`tools/ghl_survey_builder.py`), not this one.

### 0.2 Field inventory (see form-reasoning-layer.md §3 for the decision method)
- [ ] **P0-4** List every field: `label · source(standard|custom) · type ·
      required|hidden · width% · placeholder · query_key`.
- [ ] **P0-5** Standard-first rule: map to a built-in contact field (Quick Add:
      Personal Info / Address / etc.) wherever one exists. Custom fields ONLY
      when no standard field fits.
- [ ] **P0-6** Required and Hidden are **mutually exclusive** per field (video
      14:09–14:12; enforced by `_resolve_fields`).
- [ ] **P0-7** Keep the ask minimal: the most-utilized set is First Name, Last
      Name, Phone, Email, Submit (video 16:44). Every extra field must justify
      itself against conversion cost.

### 0.3 Custom fields + tags — zhc convention (PINNED)
- [ ] **P0-8** Every agent-created **custom-field unique key** = `zhc_<snake_slug>`
      (lowercase, no spaces) → merge token `{{contact.zhc_<slug>}}`.
      Example: `zhc_podcast_rating`. The client-facing **Label stays human**
      ("Podcast Rating") — the marker lives in the KEY.
- [ ] **P0-9** Every agent-created **tag** = `zhc_<snake_slug>` (GHL lowercases
      tags). Example: `zhc_podcast_lead`.
- [ ] **P0-10** The **form NAME** (container) = uppercase `ZHC ` prefix
      (`ghl_builder.ensure_zhc_prefix` fleet convention), e.g.
      `ZHC Podcast Signup Form`. Two conventions on purpose: NAMES → `ZHC `,
      machine KEYS/TAGS → `zhc_`.
- [ ] **P0-11** **Existence check BEFORE create (idempotent).** Via Skill 44:
      `caf locations` list custom fields + list tags → any existing artifact whose
      key/name already equals the target `zhc_…` is stamped `action:"reuse"`;
      only the remainder is `action:"create"`. Zero duplicates, ever.

### 0.4 Dependency pre-creation (API, not browser)
- [ ] **P0-12** Emit `routing/form-dependency-plan.json` (custom fields + tags,
      each with `zhc_` key, GHL data type, and create|reuse action).
- [ ] **P0-13** **Skill 44 (`44-convert-and-flow-operator`, the `caf` CLI — this
      IS "the GHL-API skill") executes the plan on the LOCATION PIT** and returns
      IDs. In-browser create-on-the-fly (random unique-key suffix, video
      08:01–10:23) is **DISALLOWED** for agent builds — non-deterministic,
      un-prefixed, non-idempotent.
- [ ] **P0-14** Record every `action:"create"` result in the **run ledger**
      (`routing/form-run-ledger.json`) — this is the rollback manifest.

### 0.5 Session / safety gates (inherited Skill-6 invariants)
- [ ] **P0-15** `location_id` present + **location gate** passes (correct
      sub-account; never co-mingle clients; client's OWN keys only).
- [ ] **P0-16** Seeded token-only session (Firebase refresh token; NO login form,
      NO 2FA path). Headless guard on. Singleton pooled browser via
      `browser_manager`. `RateGovernor` spacing on saves.
- [ ] **P0-17** Preflight gates F-P1..F-P8 PASS (`ghl_form_builder.py
      _run_preflight`): location, gate, spec, zhc keys, zhc tags, ZHC name,
      custom-via-Object-Fields-only, headless.
- [ ] **P0-18** Emit `routing/form-plan.json` + `routing/form-click-list.json`
      (every placeholder resolved — the browser receives ZERO open decisions).

---

## PHASE 1 — BUILD (DUMB browser operator; script = form-browser-operator-instructions.md)

- [ ] **B-1** Navigate: left rail **Sites** → secondary nav **Forms** → Forms list
      loads (`All forms` tab + `+ Create form` visible). (video 00:05–00:56)
- [ ] **B-2** Create: **+ Create form** → modal "Create new form" → **Start from
      Scratch** → **Create** → builder opens with default `Form <n>`. (00:56–01:39)
- [ ] **B-3** Rename: click the top-center name → type `ZHC <name>` → **Enter**;
      name persists in the top bar. (04:22–05:03)
- [ ] **B-4** Trim defaults: the scratch form pre-seeds First Name, Last Name,
      Phone*, Email*, two consent checkboxes, Submit, and a Privacy/Terms Text
      element. Delete only what the plan says (select field → trash icon).
      (01:39–02:27)
- [ ] **B-5** Standard fields: left panel **Quick Add** → drag each planned tile
      onto the canvas at its planned position → set Label / Placeholder /
      Required-or-Hidden / **Field Width** (50% packs two per row) / Query Key
      (lowercase, no spaces — URL-prefill param). (05:03–08:16)
- [ ] **B-6** Custom fields: left panel **Add Object Fields** tab (Object =
      Contact) → **Search by Name** for the pre-created `zhc_` field → drag onto
      canvas → set the human **Label** (Custom Field Name + Unique Key are
      LOCKED — that lock is the proof it is the pre-created field) →
      Required-or-Hidden per plan. (12:14–14:12)
- [ ] **B-7** Type-specific settings where the plan says so (e.g. Rating:
      icon / alignment / count ≤10 / low-high labels / store-as
      Absolute|Percentage|Fraction / colors). (10:35–12:14)
- [ ] **B-8** Consent + footer: update the two consent-checkbox texts (replace
      `[BUSINESS NAME]` / use-case placeholders with plan values) and the
      Privacy Policy | Terms of Service Text-element links to the client's real
      URLs. Starters MUST NOT ship. (01:39–02:27, 17:39)
- [ ] **B-9** **Save** (top-right) — wait for the unsaved-dot to clear. (14:16)
- [ ] **B-10** Style: **Styles and Options** toggle → Styles (Layout / Colors &
      Background / Miscellaneous) → Themes if planned → Advanced (FORM / INPUT
      FIELD / LABEL / SHORT LABEL / PLACEHOLDER) → **CUSTOM CSS** box gets
      `{{CUSTOM_CSS}}` verbatim (Custom CSS overrides styling + themes) →
      **Save**. Field-level styling needs the field selected; form-level needs
      it deselected. (14:26–16:44)
- [ ] **B-11** Post-submit behavior: **Settings** tab → on-submit action
      (thank-you message vs redirect URL per plan) + spam protection (Captcha
      element / built-in setting per plan). *(Not shown in the video — Settings
      tab was never opened; first live run must capture this screen.)*
- [ ] **B-12** **Preview** — desktop AND mobile toggles; screenshot both. (18:14)

---

## PHASE 2 — EMBED (retrieve snippet, splice into the host page)

- [ ] **E-1** **Integrate** → "Embed or Share Form" modal → **Embed Code** tab →
      set Layout Type per plan (**Inline** for in-page; Popup / Polite slide-in /
      Sticky sidebar for overlays) + trigger/activation/deactivation options →
      **Copy embed code** (the `<script>` JS snippet). Also open **Share** tab
      and capture the direct link `https://<location-domain>/widget/form/<formId>`
      → parse out `<formId>`. (18:14–18:54)
- [ ] **E-2** Method decision (SMART layer, already in the plan):
      - **JS embed snippet (Inline)** — DEFAULT for splicing into a Skill-6 page
        blob code element (the existing `SKILL44_WIDGET → FORM` path).
      - **Direct link / iframe** — for external (non-GHL) sites or hard-isolated
        embeds.
      - **Native page-builder Form element** — documented alternative when a
        human owns the page in the GHL builder; NOT the agent default (extra
        builder navigation for zero determinism gain).
- [ ] **E-3** Splice the snippet **VERBATIM — strip nothing, add nothing, and NO
      `integrity`/`crossorigin` SRI attributes** (GHL rotates the embed script;
      SRI breaks on the next deploy) into a `ghl_rest_canvas` code element on the
      target funnel/website page. Optional CSS wrapper for page-side polish.
- [ ] **E-4** Save the host page (existing Skill-6 save/verify discipline;
      201-autosave is NOT proof — see QC).

---

## PHASE 3 — TAGS (attachment ≠ creation)

- [ ] **T-1** Tags were already **created** (Phase 0, Skill 44, `zhc_` prefixed,
      GET-first). Never create tags in this phase.
- [ ] **T-2** **Attach on submit via a Skill-44 workflow**: trigger **"Form
      Submitted" (this form's ID)** → action **"Add Contact Tag" → `zhc_<slug>`**.
      The GHL form builder has NO native add-tag control (verified: the video
      never shows one; the Text-editor tag icon is a merge-value inserter).
      Build AFTER the form exists (needs the form ID). Skill 44 PLAN-MODE +
      WF-1..21 + rubric ≥ 8.5 gates apply.
- [ ] **T-3** Documented alternative ONLY (not default): a hidden Tags
      object-field with a preset value — must be live-verified before first use.

---

## PHASE 4 — VERIFY (independent; gate = ../qc-built-form.sh, see ../QC.md)

- [ ] **V-1** Run every QC-F1..QC-F10 check via `../qc-built-form.sh` (form in list under
      `ZHC ` name, all fields present, custom-field keys locked to
      `contact.zhc_…`, preview renders desktop+mobile, embed snippet in the
      RENDERED host DOM via `ghl_verify.render_check`, tag workflow exports
      clean, idempotency re-run = all-reuse).
- [ ] **V-2** QC runs as a SEPARATE gate (independent verifier, not the builder).
      No "done" until it passes.

---

## FAILURE / ROLLBACK (no orphaned zhc artifacts)

- [ ] **R-1** Every created artifact (custom field, tag, form, workflow, page
      splice) is appended to `routing/form-run-ledger.json` at creation time.
- [ ] **R-2** On abort/failure: delete ONLY ledger entries with
      `action:"create"` from THIS run, in reverse order (workflow → page splice →
      form → tags → fields). **NEVER delete `action:"reuse"` artifacts** — they
      predate this run.
- [ ] **R-3** **Never delete a form that has submissions** (data loss). If
      submissions exist, archive/rename to `ZHC ZZ-ROLLBACK <name>` and report.
- [ ] **R-4** Orphan sweep: a periodic audit can list all `zhc_`-prefixed
      fields/tags and reconcile against run ledgers — the prefix is what makes
      agent artifacts findable and auditable.
- [ ] **R-5** Browser failure mid-build: the click list is checkpointed per step;
      resume = re-open the form by `ZHC ` name and continue from the last
      verified step (steps are idempotent-by-verification: check POST condition
      first; if already true, skip).
