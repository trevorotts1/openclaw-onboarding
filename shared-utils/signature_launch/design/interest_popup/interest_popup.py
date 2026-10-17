"""Branded interest popup: the landing page's visitor identity capture.

Owner: S71. Implements doc 16 section 1 ("Branded interest popup ...
Captures visitor identity, not launch strategy") and doc 07 section 4
(interest popup component).

Contract:

- The visitor form captures exactly four fields: first name, last name,
  email, phone. They map to the native CRM contact fields of the same
  names (NATIVE_FIELD_MAP). No strategy questions, no survey, and no
  payment/card field of any kind exists in this component.
- The CTA on the page opens the popup (doc 07 section 3/4). The popup
  itself performs no network submission and invents no form ID, hidden
  endpoint or payment form (doc 07 section 4). On submit it emits one
  interest-capture payload (build_interest_capture) through the
  ``sl:interest-capture`` DOM event (see interest_popup.js). The S06
  delivery adapter performs the actual native submission; routing to
  the next page happens only after a verified successful native
  submission or approved API receipt, which the consumer signals back
  through markVerified(). A client-side "thanks" state is never treated
  as contact creation.
- Consent: consent statements are supplied by the launch's approved
  communication policy (doc 02 launch record, communication group).
  Each renders as a checkbox whose text IS the statement, unchecked by
  default. A required statement left unchecked blocks the capture.
  Providing a phone number is not blanket permission for automated
  marketing texts (doc 07 section 4): consent is captured per statement
  and carried in the payload for the consumer to honor.
- A failed submission retains the (non-sensitive) entered values and
  shows a clear error; the JS behavior implements that state.

All interpolated text is HTML-escaped (doc 16 section 6: untrusted text
is escaped, never concatenated raw). Deterministic, standard library
only; rendering is a pure function of the config dict.
"""

import html

COMPONENT_NAME = "interest-popup"
COMPONENT_VERSION = "1.0.0"
COMPONENT_OWNER = "S71"

# The exact visitor field set, in display order. Nothing may be added
# here without a change order: doc 07 section 4 fixes this component to
# first name, last name, email and phone.
POPUP_FIELDS = ("first_name", "last_name", "email", "phone")

FIELD_SPECS = {
    "first_name": {
        "label": "First name",
        "input_type": "text",
        "autocomplete": "given-name",
        "inputmode": None,
    },
    "last_name": {
        "label": "Last name",
        "input_type": "text",
        "autocomplete": "family-name",
        "inputmode": None,
    },
    "email": {
        "label": "Email",
        "input_type": "email",
        "autocomplete": "email",
        "inputmode": "email",
    },
    "phone": {
        "label": "Phone",
        "input_type": "tel",
        "autocomplete": "tel",
        "inputmode": "tel",
    },
}

# Component field -> native CRM contact field the S06 adapter binds.
NATIVE_FIELD_MAP = {
    "first_name": "first_name",
    "last_name": "last_name",
    "email": "email",
    "phone": "phone",
}

DEFAULT_HEADING = "Get the details"
DEFAULT_SUBMIT_LABEL = "Continue"
DEFAULT_PENDING_TEXT = (
    "Your details were received. We are confirming your registration; "
    "this page will continue automatically once confirmed."
)
DEFAULT_VERIFIED_TEXT = "Confirmed. Taking you to the next step now."
DEFAULT_ERROR_TEXT = (
    "Something went wrong sending your details. Your entries are still "
    "here; please try again."
)

_EVENT_NAME = "interest_capture"


def _esc(value):
    return html.escape(str(value), quote=True)


def validate_capture(values, consent):
    """Validate a prospective capture. Returns a list of error strings.

    values: dict over POPUP_FIELDS. consent: dict statement_id -> bool.
    Required-consent checking needs the statement list, so this helper
    only checks the four fields; build_interest_capture adds consent.
    """
    errors = []
    for field in POPUP_FIELDS:
        value = (values or {}).get(field)
        if value is None or not str(value).strip():
            errors.append("%s is required" % FIELD_SPECS[field]["label"])
    email = str((values or {}).get("email") or "").strip()
    if email and ("@" not in email or email.startswith("@") or email.endswith("@")):
        errors.append("Email does not look like an email address")
    return errors


def build_interest_capture(values, consent, consent_statements):
    """Build the interest-capture payload the component emits on submit.

    The payload is the contract surface for the S06/S44 seam: the
    consumer performs the native submission and only a verified receipt
    may advance the visitor. ``consent`` maps statement id -> bool;
    statements marked required must all be True or the capture is
    invalid and must not be submitted.
    """
    values = values or {}
    consent = consent or {}
    errors = validate_capture(values, consent)
    consent_block = {}
    for statement in consent_statements or []:
        sid = statement["id"]
        checked = bool(consent.get(sid))
        consent_block[sid] = checked
        if statement.get("required") and not checked:
            errors.append("Consent required: %s" % sid)
    return {
        "event": _EVENT_NAME,
        "component": COMPONENT_NAME,
        "component_version": COMPONENT_VERSION,
        "fields": {f: str(values.get(f) or "").strip() for f in POPUP_FIELDS},
        "native_field_map": dict(NATIVE_FIELD_MAP),
        "consent": consent_block,
        "valid": not errors,
        "validation_errors": errors,
    }


def render_interest_popup(config, tokens=None):
    """Render the popup markup. Pure function of config (+ token doc).

    config keys:
      id_prefix        DOM id prefix (default "sl-interest")
      heading          popup heading text
      intro            optional short intro paragraph (plain text)
      submit_label     submit button text
      pending_text     text for the received/pending-verification state
      verified_text    text shown only after the consumer verifies
      error_text       default error text for the error region
      consent_statements  list of {id, text, required} from the launch's
                       approved communication policy; may be empty
      open_label       accessible name for completeness (the CTA itself
                       lives on the page, not in this component)

    tokens is accepted so callers pass the brand resolution through;
    branding reaches the markup via the --sl-* CSS variables emitted by
    tokens.tokens_to_css(), which the page includes alongside
    design.css. The markup therefore carries no hardcoded brand values.
    """
    config = config or {}
    prefix = _esc(config.get("id_prefix") or "sl-interest")
    heading = _esc(config.get("heading") or DEFAULT_HEADING)
    intro = config.get("intro")
    submit_label = _esc(config.get("submit_label") or DEFAULT_SUBMIT_LABEL)
    pending_text = _esc(config.get("pending_text") or DEFAULT_PENDING_TEXT)
    verified_text = _esc(config.get("verified_text") or DEFAULT_VERIFIED_TEXT)
    error_text = _esc(config.get("error_text") or DEFAULT_ERROR_TEXT)
    statements = config.get("consent_statements") or []

    field_blocks = []
    for field in POPUP_FIELDS:
        spec = FIELD_SPECS[field]
        inputmode = ""
        if spec["inputmode"]:
            inputmode = ' inputmode="%s"' % spec["inputmode"]
        field_blocks.append(
            '      <div class="sl-field">\n'
            '        <label for="{p}-{f}">{label}</label>\n'
            '        <input id="{p}-{f}" name="{f}" type="{t}" '
            'autocomplete="{a}"{im} required>\n'
            "      </div>".format(
                p=prefix,
                f=field,
                label=_esc(spec["label"]),
                t=spec["input_type"],
                a=spec["autocomplete"],
                im=inputmode,
            )
        )

    consent_blocks = []
    for statement in statements:
        sid = _esc(statement["id"])
        required = " required" if statement.get("required") else ""
        consent_blocks.append(
            '      <div class="sl-consent">\n'
            '        <label for="{p}-consent-{sid}">'
            '<input id="{p}-consent-{sid}" name="consent_{sid}" '
            'type="checkbox" value="yes"{req}> {text}</label>\n'
            "      </div>".format(
                p=prefix, sid=sid, req=required, text=_esc(statement["text"])
            )
        )

    intro_html = ""
    if intro:
        intro_html = '    <p class="sl-popup-intro">%s</p>\n' % _esc(intro)

    parts = [
        '<div class="sl-popup-overlay" id="%s-overlay" data-state="closed" hidden>' % prefix,
        '  <div class="sl-popup" role="dialog" aria-modal="true" '
        'aria-labelledby="%s-heading">' % prefix,
        '    <button type="button" class="sl-popup-close" '
        'data-sl-popup-close aria-label="Close">&times;</button>',
        '    <h2 id="%s-heading">%s</h2>' % (prefix, heading),
        intro_html.rstrip("\n"),
        '    <form class="sl-popup-form" id="%s-form" novalidate>' % prefix,
        "\n".join(field_blocks),
        "\n".join(consent_blocks),
        '      <p class="sl-popup-error" id="%s-error" role="alert" hidden>%s</p>'
        % (prefix, error_text),
        '      <p class="sl-popup-pending" id="%s-pending" role="status" hidden>%s</p>'
        % (prefix, pending_text),
        '      <p class="sl-popup-verified" id="%s-verified" role="status" hidden>%s</p>'
        % (prefix, verified_text),
        '      <button type="submit" class="sl-popup-submit">%s</button>' % submit_label,
        "    </form>",
        "  </div>",
        "</div>",
    ]
    return "\n".join(p for p in parts if p != "") + "\n"
