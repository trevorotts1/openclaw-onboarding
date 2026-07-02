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
import json
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_IO = 3

VERIFIED_STEP_TYPES = ("email", "wait")


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


def email_step(step_id, name, subject, body_text, from_name, order,
               ab_subject=None, preview_text=None):
    html = dm_email(body_text)
    step = {
        "id": step_id, "type": "email", "name": "Email: %s" % name, "order": order,
        "attributes": {
            "subject": subject, "body": html, "html": html,
            "fromName": from_name, "attachments": [], "conditions": [],
            "trackingOptions": {"hasTrackingLinks": False, "hasUtmTracking": False, "hasTags": False},
        },
    }
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

    steps = []
    order = 0
    for i, e in enumerate(emails, 1):
        if not isinstance(e, dict):
            continue
        slot = e.get("e_slot", i)
        subjects = e.get("subjects") or [""]
        previews = e.get("previews") or []
        subj_a = subjects[0] if subjects else ""
        subj_b = subjects[1] if len(subjects) > 1 else None
        fw = e.get("framework", "email")
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

    workflow = {
        "name": "%s (DRAFT)" % seq_id,
        "tag": "email-engine:%s" % slug,
        "status": "draft",
        "templates": steps,
    }
    return {
        "folder": folder,
        slug: workflow,
        "_meta": {
            "deploy_mode": "draft-only",
            "generator": "50-email-engine/tools/emit_build_plan.py",
            "sequence_id": seq_id,
            "objective": objective,
            "email_count": sum(1 for s in steps if s["type"] == "email"),
            "note": "DRAFT-ONLY. Nothing sends. Human approval + Skill-44 qc-built-workflow.sh (>=8.5) precede any publish. Scope: workflow email steps only.",
        },
    }


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
