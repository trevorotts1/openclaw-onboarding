# Forms Playbook — how the FORM capability slots into Skill 6

**Status:** DESIGN + REVIEWABLE DRAFT (PENDING-LIVE-RUN). Additive to Skill 6
(`06-ghl-install-pages`, the ONE GHL delivery rail). Does NOT modify the live
skill or the repo. This is the single operator-facing entry doc for the forms
capability; the authoritative design lives in `form-builder-spec.md` and the
canonical process files in the parent folder.

> ⚠️ **Convert and Flow = Go High Level = GHL** (one platform; builder iframe is
> `leadconnectorhq.com`). Any third-party form-tool name that may appear in a
> source caption filename is a **mislabel** — this is Go High Level. Never write a
> non-GHL tool name in any deliverable.
> 🔒 **Fleet-wide repo.** No client names, domains, or form IDs in any file.

---

## 0. One-paragraph summary

Skill 6 already builds **funnels, websites, and surveys** through a seeded
token-only GHL browser session plus the Skill-44 GHL-API rail. This adds
**forms** as a fourth capability on the *same two rails*, with a hard **two-layer
split**: a **SMART reasoning layer** (fleet top-tier model) decides WHAT form to
build, pre-creates every **custom field + tag** via Skill 44 (idempotent,
`zhc_`-marked), and emits a fully-resolved click list; a **DUMB browser operator**
(often MiniMax-M3) executes the click list verbatim — create the form, drag
standard fields (Quick Add) + pre-created custom fields (Add Object Fields),
style it (Custom CSS), and copy the **embed snippet**, which is spliced into a
GHL page via Skill 6's existing `SKILL44_WIDGET → FORM` path and verified in the
rendered DOM. Tags attach on submit via a Skill-44 workflow. The browser makes
**zero** decisions.

---

## 1. Module / file layout (mirrors the survey capability)

Forms slot in exactly where surveys already live, so nothing about Skill 6's
shape changes — one new tool, one dispatcher verb, one QC script, plus a shared
SOP cluster.

| Concern | Surveys (exists today) | Forms (this draft) | Where it lands at productionization |
|---|---|---|---|
| Builder tool | `tools/ghl_survey_builder.py` | `ghl_form_builder.py` | `06-ghl-install-pages/tools/ghl_form_builder.py` |
| Dispatcher verb | `build_survey` in `tools/v2_dispatcher.py` | `build_form` | add `build_form` next to `build_survey` |
| Browser session rail | `tools/browser_manager.py` (singleton pooled) | *reused as-is* | no change |
| GHL-API rail (fields/tags/workflows) | Skill 44 `caf` (LOCATION PIT) | *reused as-is* | no change |
| Embed splice | `tools/ghl_rest_canvas.py` (`SKILL44_WIDGET → FORM`) | *reused as-is* | no change |
| Render verify | `tools/ghl_verify.py` `render_check` | *reused as-is* | no change |
| QC script | `qc-built-funnel.sh` / `qc-built-workflow.sh` | `qc-built-form.sh` (see `../QC.md`) | new `06-ghl-install-pages/qc-built-form.sh` |
| SKILL.md prose | capability #12 (survey) | capability #15 (form) | apply `SKILL-md-patch.md` |
| Shared SOP cluster | `universal-sops/funnel-craft/` (Skill 49) | `universal-sops/form-craft/` | ship the 4 parent process files as SOP-FORM-01..05 |

**Reading order for a reviewer:** this file → `form-builder-spec.md` (design) →
`form-creation-checklist.md` (the checklist) → `form-reasoning-layer.md` (smart
layer) → `form-browser-operator-instructions.md` + `../tools/examples/form-click-list.example.json`
(dumb layer) → `../qc-built-form.sh` (independent gate) → `form-click-map.md` (the
42-anchor evidence table with video frames).

---

## 2. How it reuses the existing rails (nothing new to stand up)

1. **Browser-operator rail** — the same `browser_manager` singleton pooled
   session, seeded token-only auth (Firebase refresh token; NO login form, NO
   2FA), headless guard, and `RateGovernor` save-spacing that funnels/surveys
   use. The forms click list is just another script fed to the same operator.
2. **GHL-API rail (Skill 44)** — the LOCATION-PIT `caf` operator already lists +
   creates **custom fields**, lists + creates **tags**, and builds **workflows**,
   and already refuses to build against missing dependencies. Forms lean on
   exactly this: pre-create the `zhc_` fields/tags, then (post-build) the
   `Form Submitted → Add Contact Tag` workflow.
3. **Embed rail** — the page-blob splice (`ghl_rest_canvas` code element) is the
   existing `SKILL44_WIDGET → FORM` path in SKILL.md's Phase-5 method table. The
   form embed snippet is spliced **verbatim, no SRI** (GHL rotates the script).
4. **Verify rail** — `ghl_verify.render_check` proves the widget marker is in the
   JS-hydrated DOM (a 201 autosave is not proof) — identical discipline to pages.

Net new surface area: one Python tool + one QC script + prose. Everything
load-bearing is already proven by the funnel/website/survey rails.

---

## 3. The reasoning → browser handoff (the contract)

The SMART layer emits three artifacts into the run's `routing/`; the DUMB layer
consumes only the third.

- `form-plan.json` — resolved intent: `ZHC ` form name, ordered field list with
  every property final (label/type/required-xor-hidden/width%/placeholder/
  query_key/type-specific), consent + footer copy, style + custom CSS, embed
  method + target page, tag plan, on-submit behavior.
- `form-dependency-plan.json` — custom fields + tags with `zhc_` keys, GHL data
  types, and `create|reuse` actions → **executed by Skill 44 BEFORE any browser
  step**; created IDs written to the run ledger. (Example:
  `../tools/examples/form-dependency-plan.example.json`.)
- `form-click-list.json` — the fully-resolved click script (every
  `{{PLACEHOLDER}}` filled; every step has pre-wait / find / act / post-verify /
  evidence) per `form-browser-operator-instructions.md`. (Example:
  `../tools/examples/form-click-list.example.json`, 53 steps.)

Preflight `F-P1..F-P8` must PASS before the browser is dispatched. The browser
returns `form-operator-report.json` (per-step status + the captured embed
snippet + share link + parsed form ID); the SMART layer treats every operator
claim as a **hypothesis** until the independent QC gate confirms it.

**Why the split is non-negotiable:** the browser operator commonly runs on
MiniMax-M3, far weaker than the reasoning tier, and MiniMax is capability-suspect
on this fleet (probe-gate it). If handed a fuzzy goal it guesses field names,
invents keys, mis-drags, and skips the embed. So it is given zero judgment: a11y
ref first → exact visible-text fallback → STOP-and-report (never an invented CSS
selector), explicit waits, one action per step, screenshot each material step.

---

## 4. ZHC enforcement (agent-created marker + idempotency)

| Object | Convention | Example | Gate |
|---|---|---|---|
| Custom-field **unique key** (lowercase, no spaces) | `zhc_<snake_slug>` → `{{contact.zhc_<slug>}}` | `zhc_podcast_rating` | preflight `F-P4` |
| **Tag** (GHL lowercases tags) | `zhc_<snake_slug>` | `zhc_podcast_lead` | preflight `F-P5` |
| Form **NAME** (container) | UPPERCASE `ZHC ` (`ghl_builder.ensure_zhc_prefix`) | `ZHC Podcast Signup Form` | preflight `F-P6` |

Two conventions on purpose: container **NAMES** use `ZHC ` (matches funnel/step
naming); machine **KEYS + TAGS** use lowercase `zhc_` (GHL key/tag rules). The
client-facing **Label** stays human — the marker lives in the KEY, not the label.

**Idempotency (GET-first, no duplicates):** before creating anything, Skill 44
lists the location's existing custom fields + tags; `plan_dependencies()` stamps
each entry `reuse` (an existing `zhc_…` already matches) or `create` (the
remainder). It also surfaces a matching NON-`zhc_` field of the same meaning to
the owner rather than silently duplicating the semantic. **Create-on-the-fly in
the browser is DISALLOWED** (`F-P7`) — GHL would mint a random unique-key suffix
that a weak operator must rename (typo-prone, un-prefixed, non-idempotent).
Custom fields reach the form ONLY by dragging the pre-created field from **Add
Object Fields** (name + key LOCKED = proof it is the pre-created field).

---

## 5. Embed + CSS (make it look good)

- **Retrieve** the JS embed snippet at **Integrate → Copy Embed Code**
  (Layout = **Inline** for in-page; Popup / Slide-in / Sidebar for overlays) plus
  the direct `…/widget/form/<formId>` link.
- **Embed** it VERBATIM (no `integrity`/`crossorigin` SRI) into a
  `ghl_rest_canvas` code element on the target funnel/website/landing page — the
  existing `SKILL44_WIDGET → FORM` path.
- **Style** on two levers: (1) the form's **Custom CSS** box (overrides Styles +
  Themes; set from `task['custom_css']` at build), and (2) a CSS wrapper around
  the embed in the host page. Brand colors/buttons/responsive tweaks go here.
- **Verify** the widget tag in the RENDERED DOM via `render_check` (200 +
  marker), and screenshot desktop + mobile (the 50%-width pairs must stack).

---

## 6. Tags: creation ≠ attachment

- **Creation** = Skill 44 makes the `zhc_<slug>` tag on the location (idempotent,
  in the dependency plan, BEFORE the browser build).
- **Attachment** = how a submitting contact GETS the tag. The GHL form builder
  has **no native add-tag control** (verified across the whole video; the
  Text-editor "tag" icon is a merge-value inserter, not a contact tag). Canonical
  path: a Skill-44 **"Form Submitted → Add Contact Tag"** workflow, built AFTER
  the form ID exists, under Skill 44's PLAN-MODE + WF-1..21 + rubric ≥ 8.5.
  Documented non-default alternative: a hidden Tags object-field with a preset
  value (live-verify before first use).

---

## 7. Where the checklist / QC / instructions live

| Artifact | File | Role |
|---|---|---|
| End-to-end checklist | `form-creation-checklist.md` | Phases 0–4 (preflight → build → embed → tags → verify) + rollback |
| Smart-layer method | `form-reasoning-layer.md` | how the reasoning agent decides form/fields/custom-fields/tags/embed |
| Dumb-layer script | `form-browser-operator-instructions.md` + `../tools/examples/form-click-list.example.json` | the explicit low-IQ click script + example |
| Click evidence | `form-click-map.md` | 42 anchors mapped to video frames |
| Independent QC | `../qc-built-form.sh` (see `../QC.md`) | QC-F1..F11 separate gate; no "done" until it passes |
| Design/spec | `form-builder-spec.md` | authoritative design; preflight gates; open questions |
| SKILL.md prose | (applied to `../SKILL.md`) | capability #15 + tools entry + Critical-Things bullets |
| Tool | `../tools/ghl_form_builder.py` | `--dry-run` default, `--selftest`; THINK-only until live |

At productionization these collapse into Skill 6's tree: the process files become
`universal-sops/form-craft/` (SOP-FORM-01..05 + manifest + QC-autofail ruleset),
the tool + QC script land under `06-ghl-install-pages/`, and the SKILL.md patch
is applied. Then a **live run on a test sub-account** replaces the
runtime-snapshot-gated selectors with confirmed refs before `--no-dry-run`.
**NO git/gh from this design phase — operator only.**

---

## 8. Verify this draft (no network / no browser)

```bash
cd 06-ghl-install-pages/tools
python3 ghl_form_builder.py --selftest        # → [selftest] PASS
python3 ghl_form_builder.py --dry-run \
  --location-id EXAMPLELOC123 --form-name "Podcast Signup" \
  --tags "Podcast Lead, Newsletter" --evidence-root /tmp/form-run-01
```

The self-test asserts `zhc_` enforcement on custom-field keys + tags, `ZHC `
container-name prefix, idempotent create-vs-reuse, required-XOR-hidden, all
F1–F13 phases present, embed + tag handoffs present, no banned/purged model
slugs in the model ladders, and no non-GHL tool-name leak.
