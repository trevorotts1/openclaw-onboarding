# SOP-FORM-01: LOCK THE FORM BRIEF IN ONE BLOCK

**Cluster:** Form-Craft Rules (`universal-sops/form-craft/`)
**Master authority:** `FORM-PIPELINE-MANIFEST.json` + `06-ghl-install-pages/tools/ghl_form_builder.py` (`_build_form_plan` + `_run_preflight` F-P1/F-P2/F-P3) + `MASTER-FORM-QC-AUTOFAIL-RULESET.md`
**Owning role:** GHL form-build operator (Web-Development / CRM / Marketing) — Skill 6 THINK layer
**Stage:** P0-INTAKE
**Produces:** the locked form brief (task spec) → seeds `routing/form-plan.json`
**Gates this stage satisfies:** AF-FORM-INTAKE-TYPE, AF-FORM-INTAKE-LOCATION, AF-FORM-INTAKE-SPEC, AF-FORM-INTAKE-EMBED-TARGET, AF-FORM-INTAKE-TRUTHGATE, AF-FORM-INTAKE-UNLOCKED

---

## 0. WHY THIS SOP EXISTS

A form built on a thin or split brief is the form that mints an un-prefixed custom field, guesses the
embed page, or fabricates a consent line. The brief is the precondition for everything downstream — it
is asked as ONE block, answered, and LOCKED before a single field is resolved. A self-attested "brief
complete" flag is never trusted: `_run_preflight` reads the actual `location_id` + spec, and the DUMB
browser is handed nothing ambiguous.

## 1. THE ONE-BLOCK RULE

Deliver the intake questions in a SINGLE message, never one-question-per-turn. Lock these:

| Field | What it is |
|---|---|
| `location_id` | The client's OWN sub-account `<LOCATION_ID>` (else AF-FORM-INTAKE-LOCATION). Never a co-mingled location. |
| **standard fields** | Which GHL Quick-Add tiles (First/Last Name, Email, Phone, City, State, …) the form carries. |
| **custom fields** | Which CUSTOM fields are needed (each becomes a pre-created `zhc_` field via Skill 44 — see SOP-FORM-03). Capture label + data-type + any type-specific settings (e.g. Rating icon/count/store-as). |
| **tags** | Which tags a submission should attach (each becomes a `zhc_` tag). Confirmed real (truth gate). |
| **embed target** | WHERE the form embeds: `{type: funnel|website|page, page_id/url}` (else AF-FORM-INTAKE-EMBED-TARGET). Layout defaults to **Inline** for in-page. |
| **styling / custom CSS** | Brand colors, buttons, responsive tweaks; the form's Custom CSS box + a host-page wrapper. |
| **keep / delete defaults** | GHL seeds a scratch form with First Name / Last Name / Phone / Email / consent. Which to KEEP, which to DELETE. |
| **form NAME** | The container name (auto-prefixed to `ZHC <name>` — see SOP-FORM-04). |

## 2. THE TRUTH GATE

Every **tag**, every **consent / T&C line**, and any **bonus** promised on the form MUST be confirmed
REAL at intake. The two default consent placeholders GHL seeds (`[BUSINESS NAME]` /
`[USE_CASE_FROM_CAMPAIGN_DESCRIPTION]`) MUST be replaced with the client's real business name + use
case — never shipped as placeholders. An unconfirmed tag / consent line is AF-FORM-INTAKE-TRUTHGATE.
The engine never fabricates a tag, a consent, or urgency.

## 3. WRONG-ENGINE + CO-MINGLE GUARDS

- If the request is not a **GHL** form (a caption filename may mislabel Go High Level as a third-party
  tool), it is AF-FORM-INTAKE-TYPE — this is Go High Level; never write a non-GHL tool name.
- The build targets the named client's OWN `<LOCATION_ID>` only. A different location is
  AF-FORM-LOCATION-COMINGLE (F-P2 location gate).

## 4. LOCK IT

Assemble the task spec (`location_id`, `form_fields`, `tags`, `embed_target`, `styling`/`custom_css`,
`keep_default_fields`, `form_name`) and mark the brief locked. An unlocked brief is
AF-FORM-INTAKE-UNLOCKED — field resolution (P1) may not begin.

## 5. VERIFY BEFORE ADVANCING

The THINK layer runs the preflight; F-P1 (`location_id`), F-P2 (location gate), and F-P3 (`spec_present`)
must PASS:

```
python3 06-ghl-install-pages/tools/ghl_form_builder.py --dry-run \
  --location-id <LOCATION_ID> --form-name "<form>" --tags "<tag1>, <tag2>"
```

Preflight PASS = the brief is locked and P1-FIELDS may begin. Any `AF-FORM-INTAKE-*` /
`AF-FORM-PREFLIGHT` code = fix the brief and re-run. Never guess a missing field — return the gap list
to the owner and STOP.
