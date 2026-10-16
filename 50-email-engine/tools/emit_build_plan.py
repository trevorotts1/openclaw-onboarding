#!/usr/bin/env python3
# =============================================================================
# SKILL 50 — EMAIL ENGINE :: P4 DEPLOY-PLAN EMITTER  (DRAFT-ONLY handoff to Skill 44)
# -----------------------------------------------------------------------------
# Deterministic, model-free, stdlib-only. Reads the locked brief.json + the
# QC-passed emails.json (approved copy) and emits the Skill-44 (Convert & Flow /
# GoHighLevel) build plan JSON consumed by `caf workflows build --from-plan`.
#
# SCOPE: workflow EMAIL steps only (email + wait) — NOT GHL Campaigns/Broadcasts
# or reusable Email Builder templates. EVERY workflow is emitted as a DRAFT
# (status:"draft"); this script NEVER sends anything and issues no provider call.
# A human approves + the Skill-44 qc-built-workflow.sh (>=8.5) runs before any send.
#
# SIGNATURE LAUNCH PROFILE (S50-07, spec 13 section 7): when the inputs name the
# signature_launch_landing_10 profile, the plan additionally carries the profile
# name, per-email approved content hashes (sha256 over subjects/previews/body/
# ctas), EXPLICIT subject/preview variant pairs (never a flattened list),
# enrollment conditions, timing anchors, stop/suppression rules (promotion
# suppressed after a verified purchase; eligibility rechecked immediately before
# each scheduled send), sender configuration REFERENCES (never credential
# values), and draft_only=true. Non-launch plans keep the legacy shape.
#
# Step shapes mirror 44-.../utils/workflow_builder.py email_step() + wait_step()
# + link_steps(). IDs are DETERMINISTIC (derived from the workflow slug + slot),
# so the emitted plan is stable and testable — no random uids, no timestamps in
# the step ids.
#
# USAGE:
#   emit_build_plan.py --brief brief.json --emails emails.json [--out build-plan.json]
#                      [--folder "Email Engine"] [--workflow-slug my-seq]
#   emit_build_plan.py --selftest
#
# EXIT CODES: 0 ok / 2 usage-or-structural-invalid / 3 IO
# =============================================================================
"""Deterministic DRAFT-ONLY Skill-44 build-plan emitter for the Email Engine."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_IO = 3

VERIFIED_STEP_TYPES = ("email", "wait")

SIGNATURE_LAUNCH_PROFILE = "signature_launch_landing_10"
SIGNATURE_LAUNCH_SEQ_ID = "sequence-signature-launch-landing-10"
SIGNATURE_LAUNCH_POSITION = "signature-launch-landing-10"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
# Credential-shaped keys must never appear in a plan: sender configuration is
# carried as named REFERENCES only (keys ending in _ref are references, allowed).
_CREDENTIAL_KEY_RE = re.compile(
    r"(password|passwd|secret|api[-_]?key|credential|private[-_]?key|(^|_)token(_|$))",
    re.IGNORECASE)


def _slugify(text, fallback="email-sequence"):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or fallback


def dm_email(text):
    """Render plain body copy into a minimal, deterministic HTML block.

    Double line breaks -> paragraphs; single line breaks -> <br>. No provider,
    no network, no template engine — just a stable structural render."""
    text = (text or "").replace("\r\n", "\n").strip()
    paras = re.split(r"\n\s*\n", text)
    out = []
    for p in paras:
        p = p.strip()
        if not p:
            continue
        out.append("<p>" + p.replace("\n", "<br>\n") + "</p>")
    return "\n".join(out)


def email_content_hash(email):
    """Approved content hash for one email: sha256 over its canonical content
    (subjects, previews, body, ctas). Canonical form is JSON with sorted keys
    and tight separators, UTF-8 encoded; lists stay in authored order (order is
    content). Deterministic across runs and machines, so Skill 44 can recompute
    it and refuse stale or tampered content (spec 13 sections 7 and 10)."""
    canon = {
        "subjects": list(email.get("subjects") or []),
        "previews": list(email.get("previews") or []),
        "body": email.get("body") or "",
        "ctas": list(email.get("ctas") or []),
    }
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def sequence_content_hash(slot_hashes):
    """Sequence-level content hash over the ordered (slot, email hash) pairs."""
    blob = "\n".join("%s:%s" % (slot, h) for slot, h in slot_hashes)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _is_signature_launch(brief, emails_doc):
    """True when the inputs name the Signature Launch profile: the emails doc's
    profile or sequence_type, its canonical sequence id, or the brief's
    sequence_position / profile answer."""
    if not isinstance(emails_doc, dict):
        emails_doc = {}
    answers = (brief or {}).get("answers", {}) if isinstance(brief, dict) else {}
    if not isinstance(answers, dict):
        answers = {}
    return (
        emails_doc.get("profile") == SIGNATURE_LAUNCH_PROFILE
        or emails_doc.get("sequence_type") == SIGNATURE_LAUNCH_PROFILE
        or emails_doc.get("sequence_id") == SIGNATURE_LAUNCH_SEQ_ID
        or answers.get("sequence_position") == SIGNATURE_LAUNCH_POSITION
        or answers.get("profile") == SIGNATURE_LAUNCH_PROFILE
    )


# Profile lifecycle defaults (spec 13 sections 7 and 8). Skill 44 owns re-entry,
# purchase suppression and timing; the plan states the rules as data so the
# consumer enforces them instead of re-deriving them. A purchase suppresses THIS
# campaign only; it never cancels unrelated campaigns or other launches.
_DEFAULT_ENROLLMENT_CONDITIONS = [
    {"rule": "enroll_from_approved_launch_optin", "source_ref": "approved_signature_landing_page"},
    {"rule": "email_consent_required", "policy_ref": "approved_communication_policy"},
    {"rule": "exclude_verified_buyers", "check": "verified_purchase", "timing": "at_enrollment"},
]
_DEFAULT_LIFECYCLE = {
    "stop_rules": [
        {"rule": "stop_on_verified_purchase", "scope": "this_campaign_only"},
        {"rule": "stop_on_unsubscribe", "scope": "this_campaign_only"},
        {"rule": "stop_on_offer_version_superseded", "scope": "this_campaign_only"},
    ],
    "suppression_rules": [
        {"rule": "suppress_promotion_after_verified_purchase",
         "event": "purchase_verified",
         "applies_to": "all_remaining_email_steps", "scope": "this_campaign"},
        {"rule": "recheck_eligibility_immediately_before_send",
         "applies_to": "each_scheduled_email_step",
         "checks": ["verified_purchase", "unsubscribe", "offer_version_current"]},
    ],
    "isolation_note": ("Suppression and stop rules apply to this campaign only; "
                       "a purchase here does not cancel unrelated campaigns or "
                       "other launches."),
}


def email_step(step_id, name, subject, body_text, from_name, order,
               ab_subject=None, preview_text=None,
               variant_pairs=None, content_hash=None, slot=None):
    html = dm_email(body_text)
    step = {
        "id": step_id, "type": "email", "name": "Email: %s" % name, "order": order,
        "attributes": {
            "subject": subject, "body": html, "html": html,
            "fromName": from_name, "attachments": [], "conditions": [],
            "trackingOptions": {"hasTrackingLinks": False, "hasUtmTracking": False, "hasTags": False},
        },
    }
    if variant_pairs is not None:
        # Signature Launch profile: subject and preview travel as EXPLICIT pairs
        # (Pair A = subject A + preview A; Pair B = subject B + preview B), plus
        # the approved content hash. The legacy flat `ab` block is NOT emitted
        # for a paired step: a flattened, unpaired preview list would lose which
        # preview belongs to which subject.
        step["variant_pairs"] = variant_pairs
        if content_hash:
            step["content_hash"] = content_hash
        if slot is not None:
            step["slot"] = slot
        return step
    # A/B subject + preview are carried alongside for the operator (GHL A/B split
    # is configured on the built draft; the schema allows additional properties).
    ab = {}
    if ab_subject:
        ab["subject_b"] = ab_subject
    if preview_text:
        ab["preview_text"] = preview_text if isinstance(preview_text, list) else [preview_text]
    if ab:
        step["ab"] = ab
    return step


def wait_step(step_id, value, unit, order):
    api_unit = {"minutes": "minutes", "hours": "hour", "hour": "hour", "days": "days"}.get(unit, unit)
    label = {"minutes": "Minutes", "hour": "Hour", "hours": "Hours", "days": "Days"}.get(unit, unit.title())
    display = "Wait %d %s" % (value, label)
    return {
        "id": step_id, "type": "wait", "name": display, "order": order,
        "attributes": {
            "type": "time",
            "startAfter": {"type": api_unit, "value": value, "when": "after"},
            "name": display, "cat": "",
        },
    }


def _wait_after(index, objective):
    """Deterministic cadence between emails. Abandoned-cart opens fast (first gap
    1 hour, per the SACRED 1-3hr rule); every other sequence waits 1 day."""
    if objective == "abandoned-cart" and index == 1:
        return (1, "hour")
    return (1, "days")


def build_plan(brief, emails_doc, folder=None, workflow_slug=None):
    answers = (brief or {}).get("answers", {}) if isinstance(brief, dict) else {}
    objective = answers.get("objective") or (emails_doc.get("objective") if isinstance(emails_doc, dict) else None)
    founder = (emails_doc.get("founder_name") if isinstance(emails_doc, dict) else None) \
        or answers.get("founder_name") or ""
    seq_id = (emails_doc.get("sequence_id") if isinstance(emails_doc, dict) else None) \
        or answers.get("sequence_position") or "email-sequence"

    emails = emails_doc.get("emails") if isinstance(emails_doc, dict) and "emails" in emails_doc else None
    if emails is None:
        emails = [emails_doc]  # single-email plan

    slug = _slugify(workflow_slug or seq_id)
    folder = folder or "Email Engine — Drafts"
    launch = _is_signature_launch(brief, emails_doc)

    steps = []
    order = 0
    slot_hashes = []
    wait_anchors = []
    for i, e in enumerate(emails, 1):
        if not isinstance(e, dict):
            continue
        slot = e.get("e_slot", i)
        subjects = e.get("subjects") or [""]
        previews = e.get("previews") or []
        subj_a = subjects[0] if subjects else ""
        subj_b = subjects[1] if len(subjects) > 1 else None
        fw = e.get("framework", "email")
        if launch:
            pairs = {
                "A": {"subject": subj_a,
                      "preview": previews[0] if len(previews) > 0 else ""},
                "B": {"subject": subj_b or "",
                      "preview": previews[1] if len(previews) > 1 else ""},
            }
            digest = email_content_hash(e)
            slot_hashes.append((slot, digest))
            steps.append(email_step(
                "email-%s-e%02d" % (slug, slot),
                "E%d %s" % (slot, fw),
                subj_a, e.get("body", ""), e.get("founder_name") or founder, order,
                variant_pairs=pairs, content_hash=digest, slot=slot,
            ))
        else:
            steps.append(email_step(
                "email-%s-e%02d" % (slug, slot),
                "E%d %s" % (slot, fw),
                subj_a, e.get("body", ""), e.get("founder_name") or founder, order,
                ab_subject=subj_b, preview_text=previews,
            ))
        order += 1
        if i < len(emails):
            val, unit = _wait_after(i, objective)
            steps.append(wait_step("wait-%s-%02d" % (slug, i), val, unit, order))
            order += 1
            wait_anchors.append({"after_email_slot": slot,
                                 "wait_value": val, "wait_unit": unit})

    workflow = {
        "name": "%s (DRAFT)" % seq_id,
        "tag": "email-engine:%s" % slug,
        "status": "draft",
        "templates": steps,
    }
    meta = {
        "deploy_mode": "draft-only",
        "draft_only": True,
        "generator": "50-email-engine/tools/emit_build_plan.py",
        "sequence_id": seq_id,
        "objective": objective,
        "email_count": sum(1 for s in steps if s["type"] == "email"),
        "note": "DRAFT-ONLY. Nothing sends. Human approval + Skill-44 qc-built-workflow.sh (>=8.5) precede any publish. Scope: workflow email steps only.",
    }
    if launch:
        enrollment = None
        for cand in (emails_doc.get("enrollment_conditions") if isinstance(emails_doc, dict) else None,
                     answers.get("enrollment_conditions")):
            if isinstance(cand, list) and cand:
                enrollment = cand
                break
        sender_profile_ref = (
            (emails_doc.get("sender_profile_ref") if isinstance(emails_doc, dict) else None)
            or answers.get("sender_profile_ref") or "sender-config:default")
        reply_to_ref = (
            (emails_doc.get("reply_to_ref") if isinstance(emails_doc, dict) else None)
            or answers.get("reply_to_ref") or "sender-config:default")
        meta.update({
            "profile": SIGNATURE_LAUNCH_PROFILE,
            "content_hashes": {
                "algorithm": "sha256",
                "canonical_fields": ["subjects", "previews", "body", "ctas"],
                "per_email": {"E%s" % slot: digest for slot, digest in slot_hashes},
                "sequence": sequence_content_hash(slot_hashes),
            },
            "variant_strategy": {
                "mode": "explicit_pairs",
                "pairs": ["A", "B"],
                "pairing": ("subject and preview are paired per variant "
                            "(Pair A = subject A + preview A; Pair B = subject B "
                            "+ preview B); pairs are never flattened into an "
                            "unpaired list"),
                "testing": "skill44_native_split_test_or_approved_alternative",
                "unsupported_testing": ("reported as a capability gap by the "
                                        "Skill 44 adapter; the second pair is "
                                        "never silently dropped"),
            },
            "source_ids": {
                "sequence_id": seq_id,
                "profile": SIGNATURE_LAUNCH_PROFILE,
                "brief_sequence_position": answers.get("sequence_position"),
            },
            "target_ids": {
                "consumer": "skill-44",
                "workflow_slug": slug,
                "workflow_name": workflow["name"],
                "mode": "draft",
            },
            "enrollment_conditions": enrollment or _DEFAULT_ENROLLMENT_CONDITIONS,
            "timing_anchors": {
                "anchor_event": "enrollment",
                "timezone_ref": "skill44_location_timezone",
                "steps": wait_anchors,
            },
            "lifecycle": _DEFAULT_LIFECYCLE,
            "sender_config_refs": {
                "sender_profile_ref": sender_profile_ref,
                "reply_to_ref": reply_to_ref,
                "note": ("Named references only, resolved by Skill 44 against "
                         "its own configuration. No credential values are "
                         "carried in this plan."),
            },
        })
    return {
        "folder": folder,
        slug: workflow,
        "_meta": meta,
    }


def _credential_key_errors(plan):
    """Fail closed on credential-shaped keys anywhere in a plan. Sender
    configuration travels as named references only (keys ending in _ref);
    credential VALUES must never enter a build plan (spec 13 section 7)."""
    errors = []

    def _scan(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k)
                if _CREDENTIAL_KEY_RE.search(key) and not key.endswith("_ref"):
                    errors.append(
                        "credential-shaped key %r at %s — build plans carry "
                        "named references only, never credential values" % (key, path))
                _scan(v, path + "/" + key)
        elif isinstance(obj, list):
            for j, v in enumerate(obj):
                _scan(v, "%s/%d" % (path, j))

    _scan(plan, "$")
    return errors


def _validate_launch_plan(plan, meta):
    """Signature Launch profile contract (spec 13 section 7): the extended
    handoff fields are REQUIRED when _meta.profile names the profile."""
    errors = []
    if meta.get("draft_only") is not True:
        errors.append("signature launch plan: _meta.draft_only must be true")
    email_steps = []
    for k in [k for k in plan if k not in ("folder", "_meta")]:
        wf = plan.get(k)
        if not isinstance(wf, dict):
            continue
        for s in wf.get("templates") or []:
            if isinstance(s, dict) and s.get("type") == "email":
                email_steps.append(s)
    ch = meta.get("content_hashes") or {}
    per_email = ch.get("per_email") or {}
    if ch.get("algorithm") != "sha256":
        errors.append("signature launch plan: content_hashes.algorithm must be 'sha256'")
    if not (isinstance(ch.get("sequence"), str) and _HEX64_RE.match(ch["sequence"])):
        errors.append("signature launch plan: content_hashes.sequence missing or not a sha256 hex digest")
    if len(per_email) != len(email_steps):
        errors.append("signature launch plan: content_hashes.per_email has %d entries "
                      "for %d email step(s)" % (len(per_email), len(email_steps)))
    for s in email_steps:
        digest = s.get("content_hash")
        if not (isinstance(digest, str) and _HEX64_RE.match(digest)):
            errors.append("signature launch plan: email step %r missing/invalid content_hash"
                          % s.get("id"))
        elif per_email.get("E%s" % s.get("slot")) != digest:
            errors.append("signature launch plan: email step %r content_hash does not match "
                          "_meta.content_hashes.per_email" % s.get("id"))
        pairs = s.get("variant_pairs")
        if not isinstance(pairs, dict):
            errors.append("signature launch plan: email step %r missing variant_pairs "
                          "(explicit subject/preview pairing is required)" % s.get("id"))
        else:
            for pair in ("A", "B"):
                pv = pairs.get(pair) or {}
                if not (isinstance(pv.get("subject"), str) and pv["subject"].strip()):
                    errors.append("signature launch plan: email step %r pair %s subject "
                                  "missing/empty" % (s.get("id"), pair))
                if not (isinstance(pv.get("preview"), str) and pv["preview"].strip()):
                    errors.append("signature launch plan: email step %r pair %s preview "
                                  "missing/empty" % (s.get("id"), pair))
        if "ab" in s:
            errors.append("signature launch plan: email step %r carries the legacy flat "
                          "'ab' block — profile pairs must not be flattened" % s.get("id"))
    lifecycle = meta.get("lifecycle") or {}
    supp = lifecycle.get("suppression_rules") or []
    rule_names = " ".join(str(r.get("rule", "")) for r in supp if isinstance(r, dict))
    if "verified_purchase" not in rule_names:
        errors.append("signature launch plan: lifecycle.suppression_rules must include "
                      "promotion suppression after a verified purchase")
    if "recheck" not in rule_names:
        errors.append("signature launch plan: lifecycle.suppression_rules must include "
                      "eligibility recheck immediately before each scheduled send")
    if not lifecycle.get("stop_rules"):
        errors.append("signature launch plan: lifecycle.stop_rules missing/empty")
    if not meta.get("enrollment_conditions"):
        errors.append("signature launch plan: enrollment_conditions missing/empty")
    anchors = meta.get("timing_anchors") or {}
    if not anchors.get("anchor_event") or not isinstance(anchors.get("steps"), list):
        errors.append("signature launch plan: timing_anchors missing anchor_event/steps")
    sender_refs = meta.get("sender_config_refs") or {}
    if not sender_refs.get("sender_profile_ref"):
        errors.append("signature launch plan: sender_config_refs.sender_profile_ref "
                      "missing (a named reference is required)")
    return errors


def validate_plan(plan):
    """Light, stdlib-only structural check mirroring build-plan.schema.json +
    workflow_builder.validate_campaign(). Returns a list of error strings."""
    errors = []
    if not isinstance(plan, dict):
        return ["plan is not a JSON object"]
    if not (isinstance(plan.get("folder"), str) and plan["folder"].strip()):
        errors.append("missing/empty top-level 'folder'")
    wf_keys = [k for k in plan if k not in ("folder", "_meta")]
    if not wf_keys:
        errors.append("no workflow entries in the plan")
    for k in wf_keys:
        wf = plan[k]
        if not isinstance(wf, dict):
            errors.append("workflow %r is not an object" % k); continue
        if not (isinstance(wf.get("name"), str) and wf["name"].strip()):
            errors.append("workflow %r: missing 'name'" % k)
        if wf.get("status") != "draft":
            errors.append("workflow %r: status must be 'draft' (draft-only)" % k)
        tmpls = wf.get("templates")
        if not (isinstance(tmpls, list) and tmpls):
            errors.append("workflow %r: missing/empty 'templates'" % k); continue
        for i, s in enumerate(tmpls):
            if not isinstance(s, dict):
                errors.append("workflow %r step %d: not an object" % (k, i)); continue
            if s.get("type") not in VERIFIED_STEP_TYPES:
                errors.append("workflow %r step %d: unverified type %r" % (k, i, s.get("type")))
            for req in ("id", "name"):
                if not (isinstance(s.get(req), str) and s[req].strip()):
                    errors.append("workflow %r step %d: missing %r" % (k, i, req))
            if s.get("type") == "email":
                a = s.get("attributes") or {}
                for req in ("subject", "body", "html", "fromName"):
                    if req not in a:
                        errors.append("workflow %r step %d: email attributes missing %r" % (k, i, req))
    errors.extend(_credential_key_errors(plan))
    meta = plan.get("_meta") if isinstance(plan.get("_meta"), dict) else {}
    if meta.get("profile") == SIGNATURE_LAUNCH_PROFILE:
        errors.extend(_validate_launch_plan(plan, meta))
    return errors


def _load(path, label):
    p = Path(path)
    if not p.is_file():
        print("FATAL: %s not found: %s" % (label, p), file=sys.stderr)
        sys.exit(EXIT_IO)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        print("FATAL: cannot read %s: %s" % (label, exc), file=sys.stderr)
        sys.exit(EXIT_IO)


# ---- self-test --------------------------------------------------------------
def _selftest():
    brief = {"skill": "email-engine", "answers": {"objective": "promotional",
             "founder_name": "Jordan Marsh", "sequence_position": "landing-page-10-promo"}}
    emails = {
        "sequence_type": "landing_page_10", "sequence_id": "sequence-landing-page-10-promo",
        "founder_name": "Jordan Marsh",
        "emails": [
            {"e_slot": 1, "framework": "pastor-solutions", "objective": "promotional",
             "subjects": ["{{contact.first_name}}, subject A here", "disruptive subject B here"],
             "previews": ["preview one", "preview two"],
             "body": "{{contact.first_name}},\n\nLine one.\n\n[CTA ->]\n\nJordan Marsh",
             "ctas": ["[CTA ->]"]},
            {"e_slot": 2, "framework": "pastor-solutions", "objective": "promotional",
             "subjects": ["{{contact.first_name}}, subject A2", "disruptive subject B2"],
             "previews": ["preview one", "preview two"],
             "body": "{{contact.first_name}},\n\nLine two.\n\n[CTA ->]\n\nJordan Marsh",
             "ctas": ["[CTA ->]"]},
        ],
    }
    plan = build_plan(brief, emails, folder="Email Engine — Selftest")
    errs = validate_plan(plan)
    slug = "sequence-landing-page-10-promo"
    checks = []
    checks.append(("structural-valid", not errs, errs))
    wf = plan.get(slug, {})
    checks.append(("workflow-is-draft", wf.get("status") == "draft", wf.get("status")))
    tmpls = wf.get("templates", [])
    email_steps = [s for s in tmpls if s["type"] == "email"]
    wait_steps = [s for s in tmpls if s["type"] == "wait"]
    checks.append(("two-email-steps", len(email_steps) == 2, len(email_steps)))
    checks.append(("one-wait-step", len(wait_steps) == 1, len(wait_steps)))
    checks.append(("deterministic-ids", email_steps[0]["id"] == "email-%s-e01" % slug, email_steps[0]["id"] if email_steps else None))
    checks.append(("fromName-founder", email_steps[0]["attributes"]["fromName"] == "Jordan Marsh", None))
    checks.append(("html-rendered", email_steps[0]["attributes"]["html"].startswith("<p>"), None))
    checks.append(("draft-only-meta", plan["_meta"]["deploy_mode"] == "draft-only", None))
    # abandoned-cart cadence check
    plan_ac = build_plan({"answers": {"objective": "abandoned-cart"}}, emails)
    waits_ac = [s for s in plan_ac[slug]["templates"] if s["type"] == "wait"]
    checks.append(("abandoned-cart-fast-open",
                   bool(waits_ac) and waits_ac[0]["attributes"]["startAfter"]["type"] == "hour", None))
    # legacy shape is unchanged: the flat `ab` block still carries the previews
    checks.append(("legacy-ab-preserved",
                   email_steps[0].get("ab", {}).get("preview_text") == ["preview one", "preview two"], None))
    checks.append(("legacy-no-profile-fields",
                   "profile" not in plan["_meta"] and "variant_pairs" not in email_steps[0], None))

    # ---- Signature Launch profile case (S50-07) ----
    import copy as _copy
    sig_brief = {"skill": "email-engine", "answers": {
        "objective": "promotional", "founder_name": "Jordan Marsh",
        "sequence_position": "signature-launch-landing-10",
        "profile": "signature_launch_landing_10"}}
    sig_emails = {
        "sequence_type": "signature_launch_landing_10",
        "profile": "signature_launch_landing_10",
        "sequence_id": "sequence-signature-launch-landing-10",
        "founder_name": "Jordan Marsh",
        "emails": [
            {"e_slot": 1, "framework": "pastor-solutions", "objective": "promotional",
             "subjects": ["{{contact.first_name}}, pair A subject one", "pair B subject one, disruptive"],
             "previews": ["pair A preview one", "pair B preview one"],
             "body": "{{contact.first_name}},\n\nBody one states the first pain plainly.\n\n[CTA ->]\n\nJordan Marsh",
             "ctas": ["[CTA ->]"]},
            {"e_slot": 2, "framework": "pastor-solutions", "objective": "promotional",
             "subjects": ["{{contact.first_name}}, pair A subject two", "pair B subject two, disruptive"],
             "previews": ["pair A preview two", "pair B preview two"],
             "body": "{{contact.first_name}},\n\nBody two states the second pain plainly.\n\n[CTA ->]\n\nJordan Marsh",
             "ctas": ["[CTA ->]"]},
            {"e_slot": 3, "framework": "pastor-solutions", "objective": "promotional",
             "subjects": ["{{contact.first_name}}, pair A subject three", "pair B subject three, disruptive"],
             "previews": ["pair A preview three", "pair B preview three"],
             "body": "{{contact.first_name}},\n\nBody three states the third pain plainly.\n\n[CTA ->]\n\nJordan Marsh",
             "ctas": ["[CTA ->]"]},
        ],
    }
    sig_slug = "sequence-signature-launch-landing-10"
    sig_plan = build_plan(sig_brief, sig_emails, folder="Email Engine — Selftest")
    sig_errs = validate_plan(sig_plan)
    checks.append(("sig-structural-valid", not sig_errs, sig_errs))
    sig_meta = sig_plan["_meta"]
    checks.append(("sig-profile-named",
                   sig_meta.get("profile") == "signature_launch_landing_10"
                   and sig_meta.get("sequence_id") == "sequence-signature-launch-landing-10", None))
    sig_wf = sig_plan.get(sig_slug, {})
    sig_steps = [s for s in sig_wf.get("templates", []) if s["type"] == "email"]
    checks.append(("sig-draft-only",
                   sig_meta.get("draft_only") is True
                   and sig_meta.get("deploy_mode") == "draft-only"
                   and sig_wf.get("status") == "draft", None))

    def _pairs_ok(step, src):
        vp = step.get("variant_pairs") or {}
        return (vp.get("A", {}).get("subject") == src["subjects"][0]
                and vp.get("A", {}).get("preview") == src["previews"][0]
                and vp.get("B", {}).get("subject") == src["subjects"][1]
                and vp.get("B", {}).get("preview") == src["previews"][1]
                and "ab" not in step)

    checks.append(("sig-pairs-preserved",
                   len(sig_steps) == 3
                   and all(_pairs_ok(s, e) for s, e in zip(sig_steps, sig_emails["emails"])), None))
    recomputed = {"E%d" % e["e_slot"]: email_content_hash(e) for e in sig_emails["emails"]}
    checks.append(("sig-hashes-recompute",
                   recomputed == sig_meta["content_hashes"]["per_email"]
                   and all(s.get("content_hash") == recomputed["E%d" % s["slot"]] for s in sig_steps), None))
    seq_recomputed = sequence_content_hash(
        [(e["e_slot"], recomputed["E%d" % e["e_slot"]]) for e in sig_emails["emails"]])
    checks.append(("sig-sequence-hash-recompute",
                   seq_recomputed == sig_meta["content_hashes"]["sequence"], None))
    tampered = _copy.deepcopy(sig_emails)
    tampered["emails"][0]["body"] += "\n\nOne extra sentence changes the approved content."
    checks.append(("sig-tampered-body-changes-hash",
                   email_content_hash(tampered["emails"][0]) != recomputed["E1"], None))
    tampered_plan = build_plan(sig_brief, tampered, folder="Email Engine — Selftest")
    tampered_steps = [s for s in tampered_plan[sig_slug]["templates"] if s["type"] == "email"]
    checks.append(("sig-plan-hash-tracks-tamper",
                   tampered_steps[0].get("content_hash") != sig_steps[0].get("content_hash"), None))
    supp_rules = [r.get("rule", "") for r in sig_meta["lifecycle"]["suppression_rules"]]
    checks.append(("sig-suppression-rules",
                   any("verified_purchase" in r for r in supp_rules)
                   and any("recheck" in r for r in supp_rules), supp_rules))
    checks.append(("sig-enrollment-and-timing",
                   bool(sig_meta.get("enrollment_conditions"))
                   and sig_meta["timing_anchors"].get("anchor_event") == "enrollment"
                   and len(sig_meta["timing_anchors"].get("steps", [])) == 2, None))
    checks.append(("sig-sender-refs",
                   sig_meta["sender_config_refs"].get("sender_profile_ref") == "sender-config:default"
                   and not _credential_key_errors(sig_plan), None))
    stripped = _copy.deepcopy(sig_plan)
    stripped["_meta"].pop("lifecycle", None)
    checks.append(("sig-validate-rejects-no-lifecycle", bool(validate_plan(stripped)), None))
    flattened = _copy.deepcopy(sig_plan)
    for s in flattened[sig_slug]["templates"]:
        if s.get("type") == "email":
            s.pop("variant_pairs", None)
    checks.append(("sig-validate-rejects-flattened", bool(validate_plan(flattened)), None))
    checks.append(("sig-plan-json-roundtrip",
                   json.loads(json.dumps(sig_plan))["_meta"]["profile"] == "signature_launch_landing_10", None))
    ok = all(c[1] for c in checks)
    print("== emit_build_plan selftest ==")
    for name, good, detail in checks:
        print("  [%s] %-26s%s" % ("PASS" if good else "MISS", name,
                                   "" if good else ("  -> %r" % (detail,))))
    print("== selftest: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return EXIT_OK if ok else EXIT_INVALID


def main(argv=None):
    ap = argparse.ArgumentParser(description="DRAFT-ONLY Skill-44 build-plan emitter (Email Engine, Skill 50).")
    ap.add_argument("--brief", help="path to the locked brief.json")
    ap.add_argument("--emails", help="path to the QC-passed emails.json (approved copy)")
    ap.add_argument("--out", help="write the build plan here (default: stdout)")
    ap.add_argument("--folder", help="GHL folder name for the draft workflow(s)")
    ap.add_argument("--workflow-slug", help="override the workflow slug")
    ap.add_argument("--selftest", action="store_true", help="run built-in fixtures and exit")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.emails:
        ap.error("--emails is required (or use --selftest)")

    brief = _load(args.brief, "brief.json") if args.brief else {}
    emails_doc = _load(args.emails, "emails.json")
    plan = build_plan(brief, emails_doc, folder=args.folder, workflow_slug=args.workflow_slug)
    errs = validate_plan(plan)
    if errs:
        print("FATAL: emitted plan failed structural validation (fail-closed):", file=sys.stderr)
        for e in errs:
            print("  - %s" % e, file=sys.stderr)
        return EXIT_INVALID
    text = json.dumps(plan, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print("wrote DRAFT-ONLY build plan: %s (%d email step(s))" % (args.out, plan["_meta"]["email_count"]))
    else:
        print(text)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
