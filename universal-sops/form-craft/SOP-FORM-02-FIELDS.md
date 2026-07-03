# SOP-FORM-02: FIELD RESOLUTION (STANDARD via Quick Add / CUSTOM via Add Object Fields)

**Cluster:** Form-Craft Rules (`universal-sops/form-craft/`)
**Master authority:** `06-ghl-install-pages/tools/ghl_form_builder.py` (`_resolve_fields`, `zhc_field_key`) + `_run_preflight` F-P4/F-P6/F-P7
**Owning role:** Skill 6 THINK layer
**Stage:** P1-FIELDS
**Produces:** `routing/form-plan.json` (fully-specified field list)
**Gates:** AF-FORM-ZHC-KEY, AF-FORM-REQ-HIDDEN-EXCL, AF-FORM-CUSTOM-VIA-OBJECT-FIELDS, AF-FORM-QUERYKEY-SLUG, AF-FORM-FIELD-MISSING

---

## 0. WHY THIS SOP EXISTS

The DUMB browser makes NO decisions, so every field property must be RESOLVED and final before the
click list is emitted. `_resolve_fields` normalizes each requested field into a complete dict — source,
element, label, type, width, required/hidden, query key or `zhc_` field key. A field left half-resolved
is a field the weak operator guesses.

## 1. THE TWO SOURCES (the hard split)

| Source | How it reaches the form | Key rule |
|---|---|---|
| **STANDARD** | Drag the **Quick Add** tile from the Form Element panel (Personal Info / Address / Text / Choice / Rating / Other …). | Carries a **query key** (URL param). |
| **CUSTOM** | Drag the **pre-created** field from **Add Object Fields** (the SECOND left-panel tab; object dropdown = Contact). | Carries a `zhc_` **field key**; **NEVER created on the fly**. |

`_resolve_fields` infers `source` when unstated: `standard` if the element matches a Quick-Add tile
in the taxonomy, else `custom`. A custom field is stamped `add_via = "add_object_fields"` — the only
sanctioned path (F-P7 / AF-FORM-CUSTOM-VIA-OBJECT-FIELDS).

## 2. PER-FIELD PROPERTIES (every one is final at P1)

- **Label** — the client-facing, HUMAN text ("Podcast Rating"). The `zhc_` marker lives in the KEY,
  never the label.
- **Query key** (standard fields) — a lowercase, no-space, no-special **slug** (`_slug(label)`), e.g.
  `city`. Not a slug ⇒ AF-FORM-QUERYKEY-SLUG.
- **Field key** (custom fields) — `zhc_<snake_slug>` via `zhc_field_key`, idempotent (never
  double-prefixed), e.g. `zhc_podcast_rating` → merge token `{{contact.zhc_podcast_rating}}`. Not
  `zhc_`-prefixed ⇒ AF-FORM-ZHC-KEY (F-P4).
- **Field width** — `50` or `100` percent. Two 50%-width fields (e.g. City + State) share one row —
  they MUST stack on mobile (verified at QC).
- **Required** / **Hidden** — **MUTUALLY EXCLUSIVE.** `_resolve_fields` forces `hidden=False` if both
  are set and stamps a warning; a field with both still true ⇒ AF-FORM-REQ-HIDDEN-EXCL. Hidden is for
  score / tag / pass-through data.
- **Type-specific settings** — e.g. a Rating field's icon / alignment / count / store-as; a
  dropdown/radio's options. Captured now so the operator only fills, never chooses.

## 3. DEFAULT-FIELD DISCIPLINE

GHL seeds a scratch form with First Name / Last Name / Phone / Email + two consent checkboxes. The
brief's `keep_default_fields` decides which stay; the rest are queued for deletion at build F4. A kept
default wrongly deleted (or a requested field that never lands) ⇒ AF-FORM-FIELD-MISSING.

## 4. VERIFY BEFORE ADVANCING

The dry-run writes `routing/form-plan.json`; preflight F-P4 (`zhc_field_keys`), F-P6 (`zhc_form_name`),
and F-P7 (`custom_via_object_fields`) must PASS:

```
python3 06-ghl-install-pages/tools/ghl_form_builder.py --dry-run --location-id <LOCATION_ID> --form-name "<form>"
```

PASS = every field is fully resolved and P2-DEPENDENCIES may begin. Any `AF-FORM-*` field code = fix
the field spec and re-run. Never rename a field or drop the `zhc_` marker to make a gate pass —
escalate to the owner instead.
