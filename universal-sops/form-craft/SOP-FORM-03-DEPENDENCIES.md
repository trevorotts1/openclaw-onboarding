# SOP-FORM-03: PRE-CREATE THE `zhc_` DEPENDENCIES (the grocery-shopping rule)

**Cluster:** Form-Craft Rules (`universal-sops/form-craft/`)
**Master authority:** `06-ghl-install-pages/tools/ghl_form_builder.py` (`plan_dependencies`, `_tag_attachment_plan`, `zhc_tag`) + `_run_preflight` F-P5
**Owning role:** Skill 6 THINK layer emits the plan → **Skill 44 (`44-convert-and-flow-operator`, the `caf` PIT-authenticated CLI)** executes it BEFORE the browser build
**Stage:** P2-DEPENDENCIES
**Produces:** `routing/form-dependency-plan.json` (custom_fields[] + tags[], each stamped `action=create|reuse`) → created IDs in the run ledger
**Gates:** AF-FORM-DEP-UNCREATED, AF-FORM-TAG-ZHC, AF-FORM-DEP-DUP, AF-FORM-DEP-LEDGER-MISSING

---

## 0. WHY THIS SOP EXISTS

The video shows two ways a custom field reaches a form: (A) create-on-the-fly by dragging a raw element,
where GHL mints a random unique-key suffix a human must rename; and (B) **Add Object Fields**, where a
PRE-CREATED custom field drags in with its key + name LOCKED. Path (A) leaves naming and keys to the
weak browser — fragile, un-prefixed, non-idempotent. This design REJECTS (A). The grocery-shopping rule:
**pre-build the forms/calendars/tags/workflows (Skill 44) BEFORE the page.** Custom fields + tags are
created through the GHL-API rail, never the browser.

## 1. THE DEPENDENCY PLAN (`plan_dependencies`)

The THINK layer emits `routing/form-dependency-plan.json`:

- **custom_fields[]** — one entry per CUSTOM field: `field_key` (`zhc_<slug>`), `custom_field_name`
  (== the key), `label` (client-facing), `data_type`, `options`, `settings`, `merge_token`, `action`.
- **tags[]** — one entry per tag: `tag` (`zhc_<slug>` via `zhc_tag`; GHL lowercases tags anyway),
  `action`. A tag not `zhc_`-prefixed ⇒ AF-FORM-TAG-ZHC (F-P5).
- **tag_attachment** — the on-submit method (see §3).

Skill 44 already "REFUSES to build against missing dependencies" — forms lean on exactly that: it
creates/looks-up these on the location, then the browser DRAGS the pre-created `zhc_` fields via Add
Object Fields.

## 2. IDEMPOTENCY (GET-first, no duplicates)

BEFORE creating anything, Skill 44 lists the location's existing custom fields + tags. `plan_dependencies`
stamps each entry:

- **`reuse`** — an existing `zhc_…` key/tag already matches (never re-created).
- **`create`** — the remainder.

Creating a duplicate of an existing `zhc_` field/tag instead of reusing it ⇒ AF-FORM-DEP-DUP. The plan
also surfaces a matching NON-`zhc_` field of the same meaning to the owner rather than silently
duplicating the semantic. **Create-on-the-fly in the browser is DISALLOWED** — a custom field stamped
`create` that never got created by Skill 44 (or was dragged raw) ⇒ AF-FORM-DEP-UNCREATED.

## 3. TAGS: CREATION ≠ ATTACHMENT

- **Creation (here, P2)** — Skill 44 makes the `zhc_<slug>` tag on the location (idempotent, in the
  plan, BEFORE the browser build).
- **Attachment (later, P4)** — how a submitting contact GETS the tag. The GHL form builder has **no
  native add-tag control** (the Text-editor "tag" icon is a merge-value inserter, not a contact tag).
  Canonical path: a Skill-44 **"Form Submitted → Add Contact Tag `{{contact.zhc_…}}`"** workflow, built
  AFTER the form id exists (SOP-FORM-05). Documented alternative: a HIDDEN Tags object-field with a
  preset value (live-verify before first use).

## 4. THE LEDGER IS PROOF

The created field/tag IDs are written to the run ledger. The browser build MUST NOT start until the
plan is executed and the ledger records the created IDs — a missing dependency plan / ledger at build
time ⇒ AF-FORM-DEP-LEDGER-MISSING. The dependency plan is a hard hand-off, not a hope.

## 5. VERIFY BEFORE ADVANCING

```
python3 06-ghl-install-pages/tools/ghl_form_builder.py --dry-run --location-id <LOCATION_ID> --form-name "<form>" --tags "<tag1>, <tag2>"
# then, live: Skill 44 (caf) executes the create|reuse plan and writes the created IDs to the ledger
```

Every `create` entry created (or `reuse` confirmed), every tag `zhc_`-prefixed, no duplicates, ledger
populated = P3-BUILD may begin. Any `AF-FORM-DEP-*` / `AF-FORM-TAG-ZHC` code = fix the plan / re-run
Skill 44, never let the browser create a field. Deliverable label: `<client>__<form>__deps__vNN`.
