# Branded interest popup

**Component:** `interest-popup` v1.0.0 · **Owner:** S71 · **Implements:** doc 16 §1 (component inventory, "Branded interest popup — captures visitor identity, not launch strategy") and doc 07 §4 (interest popup component). Behavior rules also follow doc 16 §5 (interactive states) and §6 (native-element boundary).

## Purpose

The reusable popup a landing page's CTA opens to capture a visitor's
identity for the launch: first name, last name, email, phone — nothing
else. It is a capture surface, not a questionnaire and not a checkout.

## Inputs

`render_interest_popup(config, tokens=None)` where `config` carries:

- `id_prefix` — DOM id prefix (one popup instance per prefix).
- `heading`, `intro`, `submit_label` — plain-text copy (escaped).
- `pending_text`, `verified_text`, `error_text` — state copy overrides.
- `consent_statements` — `[{id, text, required}]` from the launch's
  approved communication policy (doc 02 launch record, communication
  group). The component ships no consent wording of its own.

`tokens` is the brand resolution from `../brand_loader/`; branding
reaches the popup through the `--sl-*` CSS variables (emit
`tokens.tokens_to_css()` on the page) plus `../../design.css`. The
markup contains no hardcoded brand values.

## Outputs / DOM contract

`interest_popup.py` renders the overlay/dialog markup (namespaced
`sl-` classes): a visible close control, labelled fields with correct
`autocomplete`/`inputmode`, consent checkboxes (text is the statement,
unchecked by default), an error region (`role="alert"`), a
pending-verification region and a verified region (both `role="status"`,
hidden until their state).

`interest_popup.js` wires behavior: open from any
`[data-sl-popup-open="<id_prefix>"]` element, focus into the dialog,
Escape/close/overlay dismissal, and focus restoration to the
originating CTA.

## Events (the contract surface)

On submit, after local validation, the component dispatches
`sl:interest-capture` on `document` with the payload built by
`build_interest_capture()`:

```json
{
  "event": "interest_capture",
  "component": "interest-popup",
  "component_version": "1.0.0",
  "fields": {"first_name": "...", "last_name": "...", "email": "...", "phone": "..."},
  "native_field_map": {"first_name": "first_name", "last_name": "last_name", "email": "email", "phone": "phone"},
  "consent": {"<statement_id>": true},
  "valid": true,
  "validation_errors": []
}
```

The component performs **no network submission** and knows no form ID,
endpoint or payment form (doc 07 §4). The S06 delivery adapter
consumes the event, performs the actual native submission, and calls:

- `window.slInterestPopup.markVerified(prefix, receipt)` — only with a
  verified native submission result or approved API receipt; moves the
  popup to the verified state and dispatches `sl:interest-verified`.
  Routing to the next page is the consumer's act, after this point.
- `window.slInterestPopup.markFailed(prefix, message)` — shows the
  error and retains the entered values.

A client-side "thanks" state is never contact creation: the
post-submit state is *pending verification* until `markVerified`.

Two error cases are kept distinct in the error region:

- **Validation failure** (nothing was sent): the JS shows validation
  copy — "Nothing was sent. Please fix the following and try again:"
  followed by the specific problems. The configured `error_text` is
  never used for this case.
- **Send failure** (the consumer's native submission failed): shown
  only via `markFailed()` — the adapter's message when given,
  otherwise the configured `error_text` (default: "Something went
  wrong sending your details...").

The browser payload is built to the same contract as
`build_interest_capture()` in `interest_popup.py`, including
`component_version`; the Python module is canonical and the JS
validation (including the email rule: no `@`, leading `@`, or
trailing `@` is invalid) mirrors it exactly.

While a submission is pending, the submit control is disabled and
further submits are ignored: one visitor action emits at most one
`sl:interest-capture`. `markFailed()` re-enables the control for a
retry; `markVerified()` leaves it disabled.

## Hard rules carried

- Field set is exactly `{first_name, last_name, email, phone}`
  (`POPUP_FIELDS`); no strategy/survey questions, and **no card or
  payment field anywhere** in markup or script.
- Consent: statements render unchecked; every `required` statement must
  be checked or the capture is invalid and is not emitted. Providing a
  phone number is not blanket permission for automated marketing texts
  (doc 07 §4) — consent travels per statement in the payload.
- Failure retains non-sensitive entered values and shows a clear
  error (JS state `error`).
- Native-element boundary (doc 16 §6): a cross-origin native form's
  internals are styled in its own builder, not from this component's
  CSS; this component never claims to reach across origins.

## Follow-ups outside this component

- Wiring the landing page's CTA and the S06 install request to this
  component belongs to S71-02/S71-05 (page-side integration), not here.

## Tests

`tests/test_interest_popup.py` (stdlib unittest): rendered field set is
exactly the four fields; no card/payment field names appear in markup
or JS; consent boxes render unchecked and required; capture builder
validates fields and required consent (including the trailing-`@`
email case); interpolated copy is escaped; no invented endpoint/
form-id strings in the JS; the JS payload's top-level field set is
extracted and asserted equal to the Python payload's. When Node.js is
available, `tests/js_harness.js` additionally executes the real JS
against a minimal DOM stub and behaviorally verifies the payload
(including `component_version`), the trailing-`@` rejection, the
validation-vs-send error copy, and the duplicate-submit guard; the
Python test skips that case when Node is absent.
