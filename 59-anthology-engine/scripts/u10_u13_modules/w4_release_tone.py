#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u10_u13_modules/w4_release_tone.py
# (W4 template generator)
# ANTHOLOGY-RELEASE-TONE TEMPLATE — EMAIL + SMS (OFFLINE data generators).
# The ONLY client-facing copy the anthology-release-tone tag may send:
#   trigger tag  anthology-release-tone  (the §3 release bus; s2_producer gate)
#   actions      send-email + send-sms
#   email links  {{contact.anthology_tone_pdf_url}} (PDF view) +
#                {{contact.anthology_tone_doc_url}} (Google Doc edit)
#   sms link     {{contact.anthology_tone_doc_url}}
# (contract rows: config/anthology-snapshot-contract.json
# workflows.release_notifications "Anthology Release: Tone" + copy_law).
# This module is a TEMPLATE GENERATOR, never a messenger: it renders the
# exact email/sms payloads and the stage review link OFFLINE — zero network,
# zero credentials, nothing ever sent. A send path (nudge_send.py / caf
# delivery) fills the rendered slots at send time; this module never touches
# a token, an env secret, or the wire.
# -----------------------------------------------------------------------------
# COPY LAW (workflows.copy_law — Trevor's verbatim law for every client-facing
# word these workflows carry; enforced here at GENERATION time so a templated
# release can never drift from the law):
#   EDITORS, NEVER AI ........ "editors" and "editorial team" are the ONLY
#        byline actors. "AI", "ghostwriter", "automated", "generated" and
#        every model/tool name are ABSENT from the generated copy (guards
#        below refuse such strings by word boundary, with the single
#        enforcement-context exception of the module's own docstring).
#   ZERO EM-DASHES .......... U+2014 is FORBIDDEN in generated copy. Every
#        sentence uses commas, periods, or a colon instead. The generators
#        refuse (ValueError) if any rendered string contains U+2014.
#   SIGN-OFF ................ "The Editors" or "{{ custom_values.producer }}"
#        only, never a person's raw name and never a model persona. The
#        email sign-off is "The Editors"; SMS never carries a sign-off (the
#        SMS shape law: one warm sentence plus ONE link).
#   STANDING INSTRUCTION .... "The PDF is yours to view. The Google Doc is
#        the one you edit, and it is the version we use." — byte-exact, in
#        every release email (copy_law.standing_instruction).
#   STAGE FORM LINK ......... <forms_base>/widget/form/<form_id>?anthology_id=
#        <minted>&stage=<stage> — the U08 pre-fill law: the TWO query params
#        pre-fill the form's HIDDEN fields client-side
#        (contact_id/anthology_id/stage universal hidden-field contract;
#        prefill_verifier.py owns the verifier). The default form is the
#        universal-review form (pin riNlAkYbcW3g92VRLqq0 — the Review Fire
#        trigger AND the form the release emails link) and the default stage
#        token is "s2_gate" (the EXACT STAGE_CURSORS vocabulary of
#        anthology_state.py; an out-of-vocabulary stage is a ValueError,
#        never a fabricated token).
#   MERGES ................... Every client-facing value that must be filled
#        at send time is a {{ ... }} merge slot (GHL merge tags, spaces
#        exactly as the contract writes them: {{ custom_values.producer }});
#        never a literal value.
#   ONE PDF VIEW + ONE DOC EDIT ..... each email carries the Tone PDF (view)
#        link plus the Tone Google Doc (edit) link, both from the contact
#        custom fields (field-map deliverable_fields tone -> doc_url /
#        pdf_url); the SMS carries ONLY the doc link.
#   NO CODE FENCES / NO INTERNAL NAMES ... zero code fences, zero internal
#        tool or model names (the nudge-template discipline).
#   NO TOKENS ................ this module holds no credential surface:
#        nothing to resolve, nothing that could ever print a secret. The
#        self-test proves every rendered string is secret-free (no "Bearer",
#        no "sk-", no key-shaped value).
#
# OFFLINE: plan / render / self-test all run with no network and no
# credential; rendering is PURE (same inputs -> same bytes).
#
# STDLIB ONLY. Importable by the u10_u13 package init and by the W4 assembler
# sibling; executed directly with the same contract as the sibling modules
# (plan / render / self-test). Exit codes (house convention):
#   0  plan / render / self-test pass
#   1  unexpected error
#   2  usage or a law violation detected offline (e.g. an out-of-vocabulary
#      stage token, an em-dash, an AI-word, an unknown form slug)
# =============================================================================

"""W4 release-tone template generator: EMAIL + SMS copy, OFFLINE and pure."""

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# The law, pinned at module top so every generator and every self-test
# assertion reads the SAME constants (single-implementation doctrine).
# ---------------------------------------------------------------------------

# The §3 release bus event this template serves (contract row name + tag).
WORKFLOW_NAME = "Anthology Release: Tone"
TRIGGER_TAG = "anthology-release-tone"

# The universal-review decision form — the Review Fire trigger AND the form
# the release emails link (forms_check.FORM_ID_BY_SLUG — the SAME pin
# form_spec_loader.py and title_select_builder.py ship against).
STAGE_FORM_SLUG = "universal-review"
STAGE_FORM_ID = "riNlAkYbcW3g92VRLqq0"

# Exact stage-token vocabulary (anthology_state.STAGE_CURSORS). The default
# stage the release email's review link pre-fills: the participant review
# gate that follows the Tone stage.
STAGE_VOCABULARY = (
    "s0_intake", "s1_avatar", "s1_gate", "s2_tone", "s2_gate",
    "s3_title", "s3_gate", "s4_blurb_outline", "s4_gate_producer",
    "s4_gate_participant", "s5_chapter", "s5_gate", "s6_rewrite",
    "s7_cover", "s8_deliver", "s9_wait_assembly", "approved",
    "delivered", "held", "exception",
)
DEFAULT_STAGE = "s2_gate"

# Field-map deliverable slots for the tone deliverable
# (field-map.json deliverable_fields.tone): the contact custom fields the
# generated email/SMS reference.
PDF_LINK_MERGE = "{{contact.anthology_tone_pdf_url}}"
DOC_LINK_MERGE = "{{contact.anthology_tone_doc_url}}"

# Copy-law merges — spaces EXACTLY as the contract writes them.
PRODUCER_MERGE = "{{ custom_values.producer }}"
PRODUCER_EMAIL_MERGE = "{{ custom_values.producer_email }}"
FIRST_NAME_MERGE = "{{ contact.first_name }}"
ANTHOLOGY_NAME_MERGE = "{{ custom_values.anthology_name }}"

# The standing instruction (copy_law.standing_instruction) — byte-exact.
STANDING_INSTRUCTION = (
    "The PDF is yours to view. The Google Doc is the one you edit, "
    "and it is the version we use."
)

# The only sanctioned sign-off (copy_law: "The Editors" or the producer merge).
SIGN_OFF_EDITORS = "The Editors"
SIGN_OFF_PRODUCER = PRODUCER_MERGE

# The review link's hidden-field query keys — the U08 pre-fill law
# (?anthology_id=<minted>&stage=<stage>; the universal hidden-field contract
# contact_id / anthology_id / stage of the snapshot contract forms block).
ANTHOLOGY_ID_KEY = "anthology_id"
STAGE_KEY = "stage"

# ---------------------------------------------------------------------------
# Guards (offline, fail-closed). A template that cannot prove it obeys the
# law is a ValueError, never a silently-off-copy payload.
# ---------------------------------------------------------------------------

# Word-boundary forbidden shapes in CLIENT-FACING copy: "AI" and
# "ghostwriter" are banned, with "editor"/"editors"/"editorial" REQUIRED to
# be the only byline actors. The enforcement-context exception is the module
# docstring (which must say "AI" to pin the law) — the docstring is not
# generated copy.
_FORBIDDEN_AI = re.compile(r"\b(?:A\.?I\.?|ghostwriter(?:s)?|automated|generated)\b", re.IGNORECASE)
_EDITOR_WORD = re.compile(r"\beditor(?:ial)?(?:s)?\b", re.IGNORECASE)

# Secret-shaped fragments that must never appear in generated copy (a
# template cannot print a token it never holds; the guard keeps the render
# honest even against a future merge-slot mistake).
_SECRET_SHAPES = re.compile(
    r"(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|ANTHOLOGY_HOOK_SECRET|"
    r"[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,})"
)


def _assert_copy_law(text, label):
    """Fail-closed copy-law check on one generated string.

    Refuses: any U+2014 em-dash, any forbidden AI/ghostwriter shape, any
    secret-shaped fragment. Raises ValueError with the exact offending
    fragment and the label of the payload that carried it.
    """
    if "—" in text:
        raise ValueError(
            "copy-law violation in %s: em-dash (U+2014) is forbidden in "
            "client-facing copy; use a comma, a period, or a colon." % label
        )
    m = _FORBIDDEN_AI.search(text)
    if m:
        raise ValueError(
            "copy-law violation in %s: forbidden word %r (editors are the "
            "only byline actors; AI and ghostwriter shapes are banned)."
            % (label, m.group(0))
        )
    m = _SECRET_SHAPES.search(text)
    if m:
        raise ValueError(
            "copy-law violation in %s: secret-shaped fragment %r must never "
            "appear in generated copy." % (label, m.group(0))
        )
    if "{{" in text and "}}" not in text:
        raise ValueError(
            "copy-law violation in %s: unbalanced merge slot (a {{ without "
            "its }})." % label
        )
    return text


# ---------------------------------------------------------------------------
# The generators. Each returns plain-text client-facing copy; the email is
# plain text (the same client-clean shape the nudge templates use), so the
# same law guards cover every channel.
# ---------------------------------------------------------------------------


def email_subject(anthology_name=ANTHOLOGY_NAME_MERGE):
    """Subject line: the tone deliverable is ready. ``anthology_name`` is the
    GHL merge slot by default; a caller that renders an offline preview may
    pass a literal name (preview values are test values, never secrets)."""
    return _assert_copy_law(
        "Your tone for %s is ready" % anthology_name, "email_subject"
    )


def email_body(anthology_name=ANTHOLOGY_NAME_MERGE,
               first_name=FIRST_NAME_MERGE,
               pdf_link=PDF_LINK_MERGE,
               doc_link=DOC_LINK_MERGE,
               sign_off=SIGN_OFF_EDITORS,
               stage_form_link=None):
    """Render the release-tone EMAIL body (plain text).

    Slots (all GHL merges by default): the author's first name, the
    anthology name, the Tone PDF view link, the Tone Google Doc edit link,
    and the review form link. The sign-off is "The Editors" (or the
    producer merge when the operator pins it). The review link is optional
    and must be produced by :func:`stage_form_link` (the U08 pre-fill law)
    when present; a malformed link is a ValueError, never a dropped link.
    """
    parts = []
    parts.append("Hi %s," % first_name)
    parts.append("")
    parts.append("Your tone for %s is ready." % anthology_name)
    parts.append("")
    parts.append("You can view the PDF here:")
    parts.append(pdf_link)
    parts.append("")
    parts.append("And you can edit your Google Doc here:")
    parts.append(doc_link)
    parts.append("")
    parts.append(STANDING_INSTRUCTION)
    if stage_form_link:
        parts.append("")
        parts.append("If you are happy with it, you can move to the next "
                     "step by opening this link:")
        parts.append(stage_form_link)
    parts.append("")
    parts.append("Thank you for being part of %s." % anthology_name)
    parts.append("")
    parts.append("Warmly,")
    parts.append(sign_off)
    for i, line in enumerate(parts):
        _assert_copy_law(line, "email_body[%d]" % i)
    return "\n".join(parts)


def sms_body(doc_link=DOC_LINK_MERGE, first_name=FIRST_NAME_MERGE):
    """Render the release-tone SMS body: ONE warm sentence plus ONE link
    (the sms_shape law; the SMS carries the doc link only, never the PDF).
    No sign-off — the SMS shape law has no room for one."""
    text = "%s, your tone is ready to review. Here is your Google Doc: %s" % (
        first_name, doc_link
    )
    return _assert_copy_law(text, "sms_body")


def stage_form_link(form_id=STAGE_FORM_ID,
                    anthology_id="",
                    stage=DEFAULT_STAGE,
                    forms_base="https://link.msgsndr.com"):
    """Build the stage review form link — the U08 pre-fill law:

        <forms_base>/widget/form/<form_id>?anthology_id=<minted>&stage=<stage>

    ``anthology_id`` is the MINTED anthology id: the template slot keeps the
    GHL merge marker ``{{ contact.anthology_id }}`` when no value is given
    (the pre-fill hydrates it client-side from the query param); a caller
    rendering an offline preview passes a synthetic fixture value. ``stage``
    must be EXACTLY one of the STAGE_CURSORS vocabulary (an
    out-of-vocabulary token is a ValueError, never a fabricated token).
    """
    if stage not in STAGE_VOCABULARY:
        raise ValueError(
            "stage token %r is not in the STAGE_CURSORS vocabulary; the "
            "pre-fill law demands an exact vocabulary token." % stage
        )
    if not anthology_id:
        anthology_id = "{{ contact.anthology_id }}"
    link = "%s/widget/form/%s?%s=%s&%s=%s" % (
        forms_base.rstrip("/"), form_id,
        ANTHOLOGY_ID_KEY, anthology_id, STAGE_KEY, stage,
    )
    return _assert_copy_law(link, "stage_form_link")


# ---------------------------------------------------------------------------
# The render surface (pure; deterministic bytes for identical inputs).
# ---------------------------------------------------------------------------

EMAIL_SLOT_KEYS = ("subject", "body", "from_name", "reply_to", "pdf_link", "doc_link", "stage_form_link")
SMS_SLOT_KEYS = ("body", "doc_link")


def render_email(sign_off=SIGN_OFF_EDITORS,
                 producer=PRODUCER_MERGE,
                 producer_email=PRODUCER_EMAIL_MERGE,
                 form_id=STAGE_FORM_ID,
                 anthology_id="",
                 stage=DEFAULT_STAGE,
                 forms_base="https://link.msgsndr.com"):
    """The complete EMAIL payload of the anthology-release-tone workflow:
    subject, body, producer-branded from_name, reply_to, and the per-stage
    link set (Tone PDF view + Tone Doc edit + the pre-filled review form
    link). Pure and offline; every value is a merge slot unless the caller
    deliberately renders an offline preview (fixture values, never secrets)."""
    link = stage_form_link(
        form_id=form_id, anthology_id=anthology_id, stage=stage,
        forms_base=forms_base,
    )
    payload = {
        "subject": email_subject(),
        "body": email_body(
            sign_off=sign_off, stage_form_link=link,
        ),
        "from_name": producer,
        "reply_to": producer_email,
        "pdf_link": PDF_LINK_MERGE,
        "doc_link": DOC_LINK_MERGE,
        "stage_form_link": link,
    }
    for key in EMAIL_SLOT_KEYS:
        _assert_copy_law(payload[key], "render_email[%s]" % key)
    return payload


def render_sms(doc_link=DOC_LINK_MERGE, first_name=FIRST_NAME_MERGE):
    """The complete SMS payload: ONE warm sentence plus ONE doc link.
    Pure and offline; link is the merge slot by default."""
    payload = {"body": sms_body(doc_link=doc_link, first_name=first_name),
               "doc_link": doc_link}
    for key in SMS_SLOT_KEYS:
        _assert_copy_law(payload[key], "render_sms[%s]" % key)
    return payload


def render(include_email=True, include_sms=True, **email_kwargs):
    """The full EMAIL + SMS render (the workflow's action pair)."""
    out = {"workflow": WORKFLOW_NAME, "trigger_tag": TRIGGER_TAG}
    if include_email:
        out["email"] = render_email(**email_kwargs)
    if include_sms:
        out["sms"] = render_sms()
    return out


# ---------------------------------------------------------------------------
# CLI: plan / render / self-test, all OFFLINE.
# ---------------------------------------------------------------------------


def plan():
    print("W4 TEMPLATE  %s" % WORKFLOW_NAME)
    print("trigger tag: %s  (s2_producer §3 release bus)" % TRIGGER_TAG)
    print("channels:    EMAIL + SMS")
    print("email links: %s (PDF view) + %s (Doc edit)" % (PDF_LINK_MERGE, DOC_LINK_MERGE))
    print("sms link:    %s (Doc edit only)" % DOC_LINK_MERGE)
    print("copy law:    editors never AI; zero em-dashes; sign-off '%s' or %s"
          % (SIGN_OFF_EDITORS, PRODUCER_MERGE))
    print("standing:    %s" % STANDING_INSTRUCTION)
    print("stage form:  slug %s pin %s pre-filled %s=<minted>&%s=<stage> "
          "(default stage %s)" % (STAGE_FORM_SLUG, STAGE_FORM_ID,
                                  ANTHOLOGY_ID_KEY, STAGE_KEY, DEFAULT_STAGE))
    print("offline:     no network, no credential, nothing sent")
    return 0


def _self_test():
    """Offline law proof: golden renders + attack fixtures. A tamper is a
    ValueError (exit 2), never a silent pass."""
    # Golden: the default render (merge slots) obeys every law.
    email = render_email()
    assert email["from_name"] == PRODUCER_MERGE, "from_name must be the producer merge"
    assert email["reply_to"] == PRODUCER_EMAIL_MERGE, "reply_to must be the producer email merge"
    assert email["body"].endswith("\nWarmly,\nThe Editors"), (
        "sign-off must be exactly 'The Editors'")
    assert email["body"].count(STANDING_INSTRUCTION) == 1, (
        "standing instruction must appear exactly once")
    assert "AI" not in email["body"], "banned byline actor in golden email"
    assert "—" not in email["body"], "em-dash in golden email"
    assert PDF_LINK_MERGE in email["body"] and DOC_LINK_MERGE in email["body"], (
        "email must carry BOTH the PDF view link and the Doc edit link")
    sms = render_sms()
    assert sms["body"].count(DOC_LINK_MERGE) == 1 and "http" not in sms["body"], (
        "SMS must carry exactly ONE link (the doc link merge slot; a literal "
        "URL is a send-time fill, never a generated value)")
    assert "—" not in sms["body"], "em-dash in golden SMS"
    link = email["stage_form_link"]
    assert link.startswith("https://link.msgsndr.com/widget/form/%s?%s=" % (
        STAGE_FORM_ID, ANTHOLOGY_ID_KEY)), "stage form link shape"
    assert "&%s=s2_gate" % STAGE_KEY in link, "default stage token missing"
    # The editors-only law: every client-facing actor word in the generated
    # copy is an editor word; no forbidden shape anywhere in the payload.
    blob = json.dumps(email) + json.dumps(sms)
    for m in re.finditer(r"\b[A-Za-z]+(?:s)?\b", blob):
        word = m.group(0).lower()
        if word in ("ai", "ghostwriter", "ghostwriters", "automated", "generated"):
            raise ValueError("self-test: forbidden byline actor %r present" % word)
    # The producer sign-off variant.
    email_prod = render_email(sign_off=SIGN_OFF_PRODUCER)
    assert email_prod["body"].endswith("\nWarmly,\n{{ custom_values.producer }}")
    # The U08 pre-fill law with a synthetic (fixture) anthology id.
    preview = render_email(anthology_id="ANTH_TEST")
    assert "?anthology_id=ANTH_TEST&stage=s2_gate" in preview["stage_form_link"]
    # Attack fixtures — each must be REFUSED.
    def _attack(label, fn):
        try:
            fn()
        except ValueError:
            return
        raise AssertionError("self-test: attack %s was NOT refused" % label)

    _attack("em-dash", lambda: _assert_copy_law("bad — dash", "attack"))
    _attack("ai-word", lambda: _assert_copy_law(
        "an AI wrote this", "attack"))
    _attack("ghostwriter", lambda: _assert_copy_law(
        "the ghostwriter did it", "attack"))
    _attack("secret-shape", lambda: _assert_copy_law(
        "Bearer abcdef0123456789", "attack"))
    _attack("unbalanced-merge", lambda: _assert_copy_law(
        "slot {{ antho", "attack"))
    _attack("out-of-vocabulary-stage", lambda: stage_form_link(stage="s99_bogus"))
    _attack("em-dash-in-body", lambda: _assert_copy_law(
        email_body(first_name="x", anthology_name="y", pdf_link=PDF_LINK_MERGE,
                   doc_link=DOC_LINK_MERGE,
                   stage_form_link=None).replace("ready.", "ready—now."),
        "em-dash-in-body"))
    _attack("ai-in-subject", lambda: email_subject(anthology_name="AI Anthology"))
    _attack("ai-in-sms", lambda: sms_body(doc_link=DOC_LINK_MERGE,
                                          first_name="AI"))
    print("w4_release_tone self-test: OK "
          "(copy law, pre-fill law, channel shape, all attacks refused)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="W4 template generator: anthology-release-tone EMAIL + SMS "
                    "(OFFLINE, no network, no credential)")
    ap.add_argument("--plan", action="store_true",
                    help="print the template contract and exit (OFFLINE)")
    ap.add_argument("--self-test", action="store_true",
                    help="prove the copy law offline and exit")
    ap.add_argument("--render", action="store_true",
                    help="render the EMAIL + SMS payloads as JSON (OFFLINE)")
    ap.add_argument("--email-only", action="store_true",
                    help="with --render: email payload only")
    ap.add_argument("--sms-only", action="store_true",
                    help="with --render: sms payload only")
    ap.add_argument("--stage", default=DEFAULT_STAGE,
                    help="stage token for the review link pre-fill "
                         "(default %s)" % DEFAULT_STAGE)
    ap.add_argument("--form-id", default=STAGE_FORM_ID,
                    help="stage form id (default the universal-review pin)")
    ap.add_argument("--forms-base", default="https://link.msgsndr.com",
                    help="hosted-form base URL (default link.msgsndr.com)")
    ap.add_argument("--anthology-id", default="",
                    help="fixture anthology id for an OFFLINE preview render; "
                         "default keeps the {{ contact.anthology_id }} merge")
    ap.add_argument("--sign-off", choices=("editors", "producer"),
                    default="editors",
                    help="email sign-off: editors (default) or producer merge")
    args = ap.parse_args(argv)
    try:
        if args.self_test:
            return _self_test()
        if args.plan:
            return plan()
        if args.render:
            if args.email_only and args.sms_only:
                ap.error("--email-only and --sms-only are mutually exclusive")
            sign_off = SIGN_OFF_EDITORS if args.sign_off == "editors" else SIGN_OFF_PRODUCER
            payload = render(
                include_email=not args.sms_only,
                include_sms=not args.email_only,
                sign_off=sign_off,
                form_id=args.form_id,
                anthology_id=args.anthology_id,
                stage=args.stage,
                forms_base=args.forms_base,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        ap.error("one of --plan, --self-test, --render is required")
    except SystemExit:
        raise
    except ValueError as exc:
        sys.stderr.write("w4_release_tone: law violation: %s\n" % exc)
        return 2
    except Exception as exc:
        sys.stderr.write("w4_release_tone: unexpected error: %s\n" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
