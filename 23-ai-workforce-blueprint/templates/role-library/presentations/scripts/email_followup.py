#!/usr/bin/env python3
"""email_followup.py -- the Skill 50 email-sequence delivery option (FIX-PLAN Item 33c).

WHAT THIS IS
------------
The presentations department offers Skill 50 (the Email Engine) as an
ELECTION-GATED delivery option, beside the sales/checkout and VSL upsell
elections. The client is asked at intake (intake/upsell-questions.json
want_email_sequences, order 7.9; the same pair lives in
intake/deck-intake-questions.json's growth_assets / decline_context turns and
in the PRES-006 contract, schema/intake_fields.js):

  * want_email_sequences == "yes"  -> the election is ON. At delivery time
    this module PREPARES a draft package (below) and hands it to Skill 44's
    operator surface for HUMAN approval.
  * want_email_sequences == "no"   -> a CLIENT WAIVER. The decline is valid
    only with the client's own verbatim reason at
    EMAIL_SEQUENCES_DECLINED_REASON, stored word-for-word as the waiver's
    client_request_quote. A bare "no" FAILS CLOSED
    (AF-EMAIL-WAIVER-MISSING), exactly like the sales/checkout and VSL
    gates (sales_checkout_builder.resolve_sales_checkout_gate /
    vsl_builder.resolve_vsl_gate, same < 3 chars floor as
    presentation_job/waivers.py).
  * absent / blank                 -> DEFER. Silence is NOT consent and NOT
    a decline; nothing is prepared and the run record says so.
  * anything else                  -> FAIL CLOSED
    (AF-EMAIL-VALUE-UNRECOGNIZED). An unrecognized answer is never guessed.

THE DELIVERY CONTRACT (what "prepare" means, and what it never means)
---------------------------------------------------------------------
When the election is on, this module writes, inside the run dir:

  working/email/email-brief.json      the DRAFT brief package: one entry per
                                      sequence (sequence definition, audience,
                                      trigger, brief answers sourced ONLY from
                                      the run record, delivered page/deck
                                      links read from the run's own receipts).
  working/email/skill44-handoff.json  the handoff record for Skill 44's
                                      operator surface: what was prepared, the
                                      approval step, and where the approval
                                      and workflow id get recorded back.
  working/checkpoints/email.json     the RUN RECORD for this branch (written
                                      on EVERY outcome: prepared, waived,
                                      deferred, gate-blocked, Skill 50
                                      unavailable), mirroring
                                      working/checkpoints/sales_checkout.json.

Two sequences are covered by the one election:

  * landing-page-10-promo (Skill 50's 10-email promo sequence), prepared
    only when the run also elected the sales/checkout page
    (WANT_SALES_CHECKOUT == "yes"): it serves the page launch. Without an
    elected page launch it is recorded not_applicable, with the reason.
  * high-ticket-appointment (Skill 50's 12-email appointment sequence),
    the post-delivery follow-up, prepared on every elected run.

DRAFT-ONLY, HUMAN APPROVAL, NOTHING SENDS. The prepared package is a DRAFT.
It is NOT Skill 50's locked brief: Skill 50's brief contract
(50-email-engine/schema/brief.schema.json) requires its own one-block intake
attestation (asked_all_at_once + question_block_msg_id), which is captured in
Skill 50's intake at approval time and is NEVER fabricated here. On human
approval at Skill 44's operator surface, Skill 50 runs P1-P4 through its
canonical entry (email-engine-entry.sh); its P4 emits a DRAFT-ONLY
build-plan.json for Skill 44 (every workflow status "draft"; Skill 50 never
emits a published workflow). The approval and the resulting workflow id are
recorded back into working/checkpoints/email.json. This module contains no
network code, no send path, and no arming path at all: it reads intake.json
and the run's own receipts, and writes the three files above. When Item 33a's
Skill 44 two-way seam (ghl-ops-request.json out, ghl-ops-receipt.json back)
lands, the handoff record written here is the object that seam carries; the
approval + workflow-id return path lands in the same checkpoint either way.

SKILL 50 UNAVAILABLE. If no 50-email-engine install is found on this box, an
elected run prepares NOTHING and the run record carries the fallback: the
election was answered, but Skill 50 is unavailable on this install, so no
email follow-up is prepared (the B13 re-survey fallback: today's state, no
email follow-up, and the run record says why).

READ SHAPES. The gate reads BOTH live intake shapes via
_resolve_capture_field(), nested pre_presentation_capture.* preferred
(the documented contract; intake_writer.py writes this), flat top-level as
fallback (deck-intake-driver.py's cmd_complete writes upsell answers flat).
Same resolution order as the sales/VSL builder gates.

PHASE WIRING. The manifest phase for this executor (P-U-EMAIL-PREP, order
9.1, defers_unless intake.want_email_sequences == "yes") is specified in
sops/EMAIL-SEQUENCE-BUILDER-SOP.md section 3; its registration is sequenced
with the manifest lockstep after this branch merges (the B30 precedent:
registration specified exactly, landed with the manifest owner's change),
so this module is also directly runnable by an operator:

    python3 scripts/email_followup.py --run-dir <RUN_DIR>
    python3 scripts/email_followup.py --selftest

No canonical-entry nonce is required: this module spends nothing, calls no
provider, and writes nothing outside the run dir (contrast the builders,
whose nonce guards Kie spend and GHL writes).

EXIT CODES
    0  -- DEFERRED (election absent), WAIVED (declined with a verbatim
          reason), PREPARED (draft package written, awaiting human
          approval), or NOT PREPARED (Skill 50 unavailable; recorded).
    2  -- usage error (missing run dir / unreadable intake).
    3  -- GATE BLOCKED: a bare "no" with no verbatim client reason, or an
          unrecognized WANT_EMAIL_SEQUENCES value
          (AF-EMAIL-WAIVER-MISSING / AF-EMAIL-VALUE-UNRECOGNIZED).
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Exit codes (mirror the sibling builders: 0 ok/deferred/waived, 2 usage,
# 3 gate blocked).
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_GATE_BLOCKED = 3

# ---------------------------------------------------------------------------
# Waiver mechanic constants (mirror sales_checkout_builder.py's: the same
# < 3 chars floor as presentation_job/waivers.py, and the field names from
# upsell-questions.json's storeTarget / waiver_field_mapping.email_sequences).
# ---------------------------------------------------------------------------
MIN_WAIVER_QUOTE_CHARS = 3
WANT_FIELD = "WANT_EMAIL_SEQUENCES"
REASON_FIELD = "EMAIL_SEQUENCES_DECLINED_REASON"
SALES_WANT_FIELD = "WANT_SALES_CHECKOUT"
WAIVER_RULE = "email_sequences"
AF_WAIVER_MISSING = "AF-EMAIL-WAIVER-MISSING"
AF_VALUE_UNRECOGNIZED = "AF-EMAIL-VALUE-UNRECOGNIZED"

# Run-dir artifacts (the delivery contract's three files).
BRIEF_REL = Path("working") / "email" / "email-brief.json"
HANDOFF_REL = Path("working") / "email" / "skill44-handoff.json"
CHECKPOINT_REL = Path("working") / "checkpoints" / "email.json"

APPROVAL_STATUS = "AWAITING_HUMAN_APPROVAL"

#: The sequences the one election covers. sequence_position values are Skill
#: 50's own (schema/brief.schema.json's sequence_position description);
#: email_count is Skill 50's SACRED sequence length (10 / 12), enforced on
#: its side by AF-EMAIL-SEQUENCE-LENGTH when it runs.
SEQUENCES = (
    {
        "sequence_id": "landing-page-10-promo",
        "sequence_position": "landing-page-10-promo",
        "email_count": 10,
        "objective": "promotional",
        "name": "Landing-page promo sequence (10 emails, Skill 50)",
        "trigger": "the elected sales/checkout page launch",
        "audience_description": (
            "the client's list: visitors and buyers of the delivered "
            "sales/checkout page"),
        "requires_sales_checkout": True,
    },
    {
        "sequence_id": "high-ticket-appointment",
        "sequence_position": "high-ticket-appointment",
        "email_count": 12,
        "objective": "upsell",
        "objective_note": (
            "recorded as upsell at preparation time (post-delivery follow-up "
            "to the next step); Skill 50's P1-SELECT confirms the objective "
            "with the operator at approval time"),
        "buyer_type": "all",
        "buyer_type_note": (
            "'all' is Skill 50's own value for the full 12-email buyer-type "
            "sequence (spontaneous, methodical, humanistic, competitive); "
            "P1-SELECT refines it at approval time"),
        "name": "Appointment follow-up sequence (12 emails, Skill 50)",
        "trigger": "delivery completion (post-delivery follow-up)",
        "audience_description": (
            "buyers of the delivered offer, followed up for the appointment "
            "or next step the deck's call to action names"),
        "requires_sales_checkout": False,
    },
)


# ---------------------------------------------------------------------------
# intake.json helpers (mirror the sibling builders)
# ---------------------------------------------------------------------------
def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return {}


def load_intake(run_dir: Path) -> dict:
    return _read_json(run_dir / "working" / "copy" / "intake.json")


def resolve_brief(intake: dict) -> Dict[str, Any]:
    brief = intake.get("deck_brief")
    return brief if isinstance(brief, dict) else {}


def resolve_deck_slug(run_dir: Path, intake: dict) -> str:
    slug = intake.get("deck_slug") or run_dir.name
    return str(slug).strip() or "presentation"


def _resolve_capture_field(intake: dict, pre: dict, field: str) -> Any:
    """Resolve one pre_presentation_capture field from whichever of the two
    live intake shapes actually carries it (identical semantics to
    sales_checkout_builder._resolve_capture_field: NESTED preferred, FLAT as
    fallback, a present-but-blank nested value still falls through; silence
    in both shapes returns None/blank and the caller's absent handling --
    DEFER -- is unchanged)."""
    raw = pre.get(field)
    if isinstance(raw, dict):
        raw = raw.get("value")
    if raw is not None and str(raw).strip():
        return raw
    flat = intake.get(field)
    if isinstance(flat, dict):
        flat = flat.get("value")
    return flat


# ---------------------------------------------------------------------------
# THE GATE -- resolve_email_gate()
# ---------------------------------------------------------------------------
def resolve_email_gate(intake: dict) -> Dict[str, Any]:
    """Resolve WANT_EMAIL_SEQUENCES against upsell-questions.json's
    waiver_field_mapping.email_sequences. Returns {"decision":
    "defer"|"prepare"|"waived"|"fail_closed", "detail": str, ...}.

    Never conflates "absent" with "declined" -- silence is NOT consent
    (upsell-questions.json's own words, verbatim). A "no" ALWAYS requires a
    real, non-empty verbatim client reason at
    EMAIL_SEQUENCES_DECLINED_REASON or the gate fails closed (mirrors
    presentation_job/waivers.py's `len(quote) < 3` self-authored-waiver
    guard)."""
    pre = intake.get("pre_presentation_capture")
    pre = pre if isinstance(pre, dict) else {}

    raw = _resolve_capture_field(intake, pre, WANT_FIELD)
    if raw is None or not str(raw).strip():
        return {
            "decision": "defer",
            "detail": (
                f"pre_presentation_capture.{WANT_FIELD} is absent/blank -- "
                "this run's intake never asked/answered the email-sequence "
                "election. DEFERRING: an absent answer is NEVER treated as "
                "a decline (silence is not consent) and never as an "
                "election. Nothing is prepared."
            ),
            "want_raw": raw,
        }

    norm = str(raw).strip().lower()
    if norm == "yes":
        return {"decision": "prepare", "detail": "client answered yes.",
                "want_raw": raw}

    if norm != "no":
        return {
            "decision": "fail_closed",
            "detail": (
                f"{AF_VALUE_UNRECOGNIZED}: {WANT_FIELD}={raw!r} is neither "
                "'yes' nor 'no' -- refusing to guess (mirrors "
                "intake_writer.py's UngroundedDeckTypeError fail-closed "
                "discipline: an unrecognized answer is never defaulted)."
            ),
            "want_raw": raw,
        }

    # norm == "no": a decline REQUIRES the client's own verbatim reason.
    reason_raw = _resolve_capture_field(intake, pre, REASON_FIELD)
    reason = str(reason_raw or "").strip()
    if len(reason) < MIN_WAIVER_QUOTE_CHARS:
        return {
            "decision": "fail_closed",
            "detail": (
                f"{AF_WAIVER_MISSING}: {WANT_FIELD}=no but {REASON_FIELD} "
                "is missing/blank -- a decline with no verbatim client "
                "reason is not a waiver (upsell-questions.json "
                "waiver_field_mapping.email_sequences; 'silence is NOT "
                "consent'). Refusing to silently skip the preparation."
            ),
            "want_raw": raw,
            "reason_raw": reason_raw,
        }

    return {
        "decision": "waived",
        "detail": "client declined with a recorded verbatim reason -- "
                  "gated OUT (not a failure).",
        "want_raw": raw,
        "quote": reason,
    }


# ---------------------------------------------------------------------------
# Skill 50 availability (the B13 fallback's trigger)
# ---------------------------------------------------------------------------
def find_skill50(start: Optional[Path] = None) -> Optional[Path]:
    """Walk every ancestor of this file (or of `start`) looking for the
    sibling 50-email-engine skill dir. Works identically inside this repo
    checkout/worktree and on a deployed client box, because both mirror the
    same repo-root skill layout -- no absolute path is ever assumed
    (mirrors sales_checkout_builder._find_ghl_rest_canvas_dir)."""
    here = (start or Path(__file__)).resolve()
    for parent in here.parents:
        cand = parent / "50-email-engine"
        if (cand / "SKILL.md").is_file():
            return cand
    return None


# ---------------------------------------------------------------------------
# Delivered links -- read the run's OWN receipts; never invented.
# ---------------------------------------------------------------------------
def _delivered_links(run_dir: Path) -> Dict[str, Any]:
    """Best-effort read of the delivered page/deck links from receipts the
    run itself produced. Absence is recorded as None, never filled in: a
    link that is not on record at preparation time is recorded from the
    install receipt at approval time instead."""
    page_url = None
    receipt = _read_json(run_dir / "working" / "sales-checkout" / "build_receipt.json")
    for key in ("page_url", "url", "funnel_url"):
        v = receipt.get(key)
        if isinstance(v, str) and v.strip():
            page_url = v.strip()
            break

    deck_url = None
    media = _read_json(run_dir / "working" / "checkpoints" / "media_library.json")
    stack = [media]
    while stack and deck_url is None:
        node = stack.pop()
        if isinstance(node, dict):
            for key in ("pptx_ghl_url", "deck_url", "ghl_url", "url"):
                v = node.get(key)
                if isinstance(v, str) and v.strip().startswith("http"):
                    deck_url = v.strip()
                    break
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return {"page_url": page_url, "deck_url": deck_url}


# ---------------------------------------------------------------------------
# The draft brief package
# ---------------------------------------------------------------------------
def _brief_answers(intake: dict, seq: Dict[str, Any]) -> Dict[str, Any]:
    """The Skill 50 brief answers this run's record can TRUTHFULLY supply.

    Sourced only from facts the run record carries (the deck brief, the
    resolved client name). Anything the record does not carry is None and
    is named in the package's missing_inputs as an approval-time input --
    never invented, and Skill 50's one-block attestation fields
    (asked_all_at_once / question_block_msg_id) are NEVER fabricated here:
    they are captured by Skill 50's own intake at approval time."""
    brief = resolve_brief(intake)
    offer = brief.get("OFFER_NAME")
    brand_voice = brief.get("TONE")
    founder = intake.get("client_name") or intake.get("client")
    answers: Dict[str, Any] = {
        "objective": seq["objective"],
        "offer": offer if isinstance(offer, str) and offer.strip() else None,
        "brand_voice": (brand_voice if isinstance(brand_voice, str)
                        and brand_voice.strip() else None),
        "founder_name": (founder if isinstance(founder, str)
                         and founder.strip() else None),
        "sequence_position": seq["sequence_position"],
    }
    if "buyer_type" in seq:
        answers["buyer_type"] = seq["buyer_type"]
    return answers


def build_sequence_package(run_dir: Path, intake: dict, seq: Dict[str, Any],
                           links: Dict[str, Any]) -> Dict[str, Any]:
    """One sequence's DRAFT package: the brief-to-be plus the delivery
    contract around it (definition, audience, trigger, approval step)."""
    brief = resolve_brief(intake)
    answers = _brief_answers(intake, seq)
    missing = [k for k, v in answers.items() if v is None]
    audience_value = brief.get("AUDIENCE")
    package: Dict[str, Any] = {
        "sequence_id": seq["sequence_id"],
        "name": seq["name"],
        "status": "DRAFT_AWAITING_HUMAN_APPROVAL",
        "sequence_definition": {
            "skill": "email-engine",
            "sequence_position": seq["sequence_position"],
            "email_count": seq["email_count"],
            "objective": seq["objective"],
        },
        "audience": {
            "description": seq["audience_description"],
            "source_field": "deck_brief.AUDIENCE",
            "value": (audience_value if isinstance(audience_value, str)
                      and audience_value.strip() else None),
        },
        "trigger": seq["trigger"],
        "brief_answers": answers,
        "delivered_links": links,
        "missing_inputs": missing,
        "approval": {
            "status": APPROVAL_STATUS,
            "surface": "Skill 44 operator surface (Convert and Flow)",
            "rule": (
                "A human approves before Skill 50 runs. On approval, "
                "Skill 50 executes P1 SELECT -> P2 GENERATE -> P3 QC -> "
                "P4 DEPLOY through email-engine-entry.sh; P4 emits a "
                "DRAFT-ONLY build-plan.json for Skill 44 (every workflow "
                "status stays 'draft') and the Skill-44 built-workflow QC "
                "gate runs on the draft. Nothing sends at any step of "
                "this contract. The approval and the resulting workflow "
                "id are recorded back into working/checkpoints/email.json."
            ),
        },
    }
    if "objective_note" in seq:
        package["objective_note"] = seq["objective_note"]
    if "buyer_type_note" in seq:
        package["buyer_type_note"] = seq["buyer_type_note"]
    return package


# ---------------------------------------------------------------------------
# The preparation entry point -- writes the run record on EVERY outcome.
# ---------------------------------------------------------------------------
def prepare_draft_packages(run_dir: Path, intake: dict,
                           skill50_dir: Optional[Path] = None,
                           _skill50_searched: bool = False) -> Dict[str, Any]:
    """Run the email gate for one run dir and act on its decision.

    Elected: prepare the draft package(s) and the Skill 44 handoff record.
    Declined / unanswered / blocked / Skill 50 unavailable: prepare nothing.
    Every outcome writes working/checkpoints/email.json (the run record for
    this branch) and returns the checkpoint dict; the caller maps the gate
    decision to the exit code.

    `skill50_dir` is injectable for tests: pass a Path to force "available",
    or pass _skill50_searched=True with skill50_dir=None to force the
    unavailable path without searching the filesystem."""
    run_dir = Path(run_dir)
    gate = resolve_email_gate(intake)
    now = datetime.now(timezone.utc).isoformat()
    checkpoint: Dict[str, Any] = {
        "deck_slug": resolve_deck_slug(run_dir, intake),
        "recorded_at": now,
        "source": "presentations/scripts/email_followup.py",
        "election": {"field": WANT_FIELD, "value": gate.get("want_raw")},
        "gate": gate,
        "packages": [],
        "approval": {"status": "NOT_APPLICABLE"},
    }

    if gate["decision"] == "defer":
        checkpoint["outcome"] = "deferred_nothing_prepared"
    elif gate["decision"] == "waived":
        checkpoint["outcome"] = "waived_nothing_prepared"
        checkpoint["waiver"] = {
            "rule": WAIVER_RULE,
            "client_request_quote": gate.get("quote"),
        }
    elif gate["decision"] == "fail_closed":
        checkpoint["outcome"] = "gate_blocked_nothing_prepared"
    else:  # prepare
        if not _skill50_searched and skill50_dir is None:
            skill50_dir = find_skill50()
        checkpoint["skill50"] = {
            "available": skill50_dir is not None,
            "path": str(skill50_dir) if skill50_dir is not None else None,
        }
        pre = intake.get("pre_presentation_capture")
        pre = pre if isinstance(pre, dict) else {}
        sales_raw = _resolve_capture_field(intake, pre, SALES_WANT_FIELD)
        sales_yes = str(sales_raw or "").strip().lower() == "yes"
        links = _delivered_links(run_dir)
        prepared: List[Dict[str, Any]] = []
        for seq in SEQUENCES:
            entry: Dict[str, Any] = {"sequence_id": seq["sequence_id"]}
            if seq.get("requires_sales_checkout") and not sales_yes:
                entry["status"] = "not_applicable"
                entry["detail"] = (
                    "no page launch was elected "
                    f"({SALES_WANT_FIELD} is not 'yes'), so the promo "
                    "sequence has no launch to serve. Nothing prepared "
                    "for this sequence.")
            elif skill50_dir is None:
                entry["status"] = "not_prepared"
                entry["detail"] = (
                    "Skill 50 (50-email-engine) is unavailable on this "
                    "install, so no email follow-up is prepared (the "
                    "election was answered 'yes'; the fallback is the "
                    "pre-integration state, recorded here so the run "
                    "record says why).")
            else:
                entry["status"] = "prepared_draft"
                entry["detail"] = (
                    "draft package prepared in working/email/"
                    "email-brief.json; awaiting human approval at Skill "
                    "44's operator surface. Nothing sent, nothing armed.")
                prepared.append(build_sequence_package(
                    run_dir, intake, seq, links))
            checkpoint["packages"].append(entry)

        if prepared:
            brief_doc = {
                "skill": "email-engine",
                "document": "email-brief draft package (presentations "
                            "delivery phase, FIX-PLAN Item 33c)",
                "status": "DRAFT_AWAITING_HUMAN_APPROVAL",
                "prepared_by": "presentations/scripts/email_followup.py",
                "prepared_at": now,
                "deck_slug": checkpoint["deck_slug"],
                "note": (
                    "This package is a preparation DRAFT, not Skill 50's "
                    "locked brief. Skill 50's brief contract "
                    "(50-email-engine/schema/brief.schema.json) requires "
                    "its own one-block intake attestation "
                    "(asked_all_at_once + question_block_msg_id), captured "
                    "in Skill 50's intake at approval time; it is never "
                    "fabricated here. Brief answers below are sourced "
                    "only from this run's record; anything the record "
                    "does not carry is null and named in missing_inputs "
                    "as an approval-time input."),
                "packages": prepared,
            }
            brief_path = run_dir / BRIEF_REL
            brief_path.parent.mkdir(parents=True, exist_ok=True)
            brief_path.write_text(
                json.dumps(brief_doc, indent=2, ensure_ascii=False),
                encoding="utf-8")

            handoff = {
                "kind": "skill44-operator-handoff",
                "prepared_by": "presentations/scripts/email_followup.py",
                "prepared_at": now,
                "deck_slug": checkpoint["deck_slug"],
                "status": APPROVAL_STATUS,
                "brief_package": str(BRIEF_REL),
                "run_record": str(CHECKPOINT_REL),
                "packages": [
                    {
                        "sequence_id": p["sequence_id"],
                        "name": p["name"],
                        "email_count": p["sequence_definition"]["email_count"],
                        "objective": p["sequence_definition"]["objective"],
                        "audience": p["audience"]["description"],
                        "trigger": p["trigger"],
                        "status": APPROVAL_STATUS,
                    }
                    for p in prepared
                ],
                "approval_step": (
                    "A human reviews the draft package at Skill 44's "
                    "operator surface. On approval: Skill 50 runs P1-P4 "
                    "through email-engine-entry.sh and its P4 emits the "
                    "DRAFT-ONLY build-plan.json that Skill 44 executes; "
                    "the workflow stays a draft until Skill 44's own "
                    "approval + QC (>= 8.5) complete. Record the approval "
                    "(approver + time) and the resulting workflow id back "
                    "into working/checkpoints/email.json. On decline: "
                    "record the operator decision in the same checkpoint. "
                    "Nothing is sent or armed on either path by this "
                    "handoff itself."),
                "wiring_gate": (
                    "Drafts and approvals are recorded per object (this "
                    "handoff + working/checkpoints/email.json). No live "
                    "send exists in this handoff; no workflow is created "
                    "by the presentations engine."),
            }
            handoff_path = run_dir / HANDOFF_REL
            handoff_path.write_text(
                json.dumps(handoff, indent=2, ensure_ascii=False),
                encoding="utf-8")
            checkpoint["outcome"] = "prepared_awaiting_human_approval"
            checkpoint["approval"] = {"status": APPROVAL_STATUS,
                                       "surface": "Skill 44 operator surface"}
            checkpoint["artifacts"] = {
                "brief_package": str(BRIEF_REL),
                "handoff": str(HANDOFF_REL),
            }
        elif skill50_dir is None:
            checkpoint["outcome"] = "elected_skill50_unavailable_nothing_prepared"
        else:
            checkpoint["outcome"] = "elected_nothing_applicable_prepared"

    ckpt_path = run_dir / CHECKPOINT_REL
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    ckpt_path.write_text(
        json.dumps(checkpoint, indent=2, ensure_ascii=False),
        encoding="utf-8")
    checkpoint["_checkpoint_path"] = str(ckpt_path)
    return checkpoint


# ---------------------------------------------------------------------------
# Self-test -- deterministic, offline, temp dirs only.
# ---------------------------------------------------------------------------
def _selftest() -> int:
    fails: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        if cond:
            print(f"  [PASS] {name}")
        else:
            print(f"  [FAIL] {name} {extra}")
            fails.append(name)

    def intake_with(pre: dict, brief: Optional[dict] = None) -> dict:
        return {
            "deck_slug": "selftest-deck",
            "client_name": "Selftest Founder",
            "deck_brief": brief if brief is not None else {
                "OFFER_NAME": "Selftest Offer",
                "TONE": "confident, direct",
                "AUDIENCE": "selftest audience",
            },
            "pre_presentation_capture": pre,
        }

    print("== email_followup.py --selftest ==")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fake_skill = root / "repo" / "50-email-engine"
        fake_skill.mkdir(parents=True)
        (fake_skill / "SKILL.md").write_text("# fake\n", encoding="utf-8")

        # 1. Gate decisions over the nested shape.
        g = resolve_email_gate(intake_with({WANT_FIELD: "yes"}))
        check("nested yes -> prepare", g["decision"] == "prepare")
        g = resolve_email_gate(intake_with({}))
        check("nested absent -> defer", g["decision"] == "defer")
        g = resolve_email_gate(intake_with(
            {WANT_FIELD: "no", REASON_FIELD: "We run our own email."}))
        check("nested no + verbatim reason -> waived",
              g["decision"] == "waived"
              and g.get("quote") == "We run our own email.")
        g = resolve_email_gate(intake_with({WANT_FIELD: "no"}))
        check("nested no, no reason -> fail_closed AF-EMAIL-WAIVER-MISSING",
              g["decision"] == "fail_closed"
              and AF_WAIVER_MISSING in g["detail"])
        g = resolve_email_gate(intake_with(
            {WANT_FIELD: "no", REASON_FIELD: "  "}))
        check("nested no, blank reason -> fail_closed",
              g["decision"] == "fail_closed")
        g = resolve_email_gate(intake_with({WANT_FIELD: "maybe"}))
        check("unrecognized value -> fail_closed AF-EMAIL-VALUE-UNRECOGNIZED",
              g["decision"] == "fail_closed"
              and AF_VALUE_UNRECOGNIZED in g["detail"])

        # 2. Gate decisions over the flat (driver) shape.
        flat = {"WANT_EMAIL_SEQUENCES": "yes", "deck_brief": {}}
        g = resolve_email_gate(flat)
        check("flat yes -> prepare", g["decision"] == "prepare")
        g = resolve_email_gate({"deck_brief": {}})
        check("flat absent -> defer", g["decision"] == "defer")

        # 3. Elected + Skill 50 available + sales elected: both packages.
        run1 = root / "run1"
        (run1 / "working" / "copy").mkdir(parents=True)
        ck = prepare_draft_packages(
            run1, intake_with({WANT_FIELD: "yes", SALES_WANT_FIELD: "yes"}),
            skill50_dir=fake_skill, _skill50_searched=True)
        check("elected prepares both sequences",
              ck["outcome"] == "prepared_awaiting_human_approval"
              and [p["status"] for p in ck["packages"]]
              == ["prepared_draft", "prepared_draft"])
        brief_doc = _read_json(run1 / BRIEF_REL)
        check("brief package carries both sequences, draft status",
              len(brief_doc.get("packages", [])) == 2
              and brief_doc.get("status") == "DRAFT_AWAITING_HUMAN_APPROVAL")
        pkg = brief_doc["packages"][0]
        check("promo package: definition + audience + trigger + approval",
              pkg["sequence_definition"]["email_count"] == 10
              and pkg["audience"]["value"] == "selftest audience"
              and "launch" in pkg["trigger"]
              and pkg["approval"]["status"] == APPROVAL_STATUS)
        check("brief answers sourced from the run record",
              pkg["brief_answers"]["offer"] == "Selftest Offer"
              and pkg["brief_answers"]["brand_voice"] == "confident, direct"
              and pkg["brief_answers"]["founder_name"] == "Selftest Founder")
        handoff = _read_json(run1 / HANDOFF_REL)
        check("handoff awaits human approval, names the record-back step",
              handoff.get("status") == APPROVAL_STATUS
              and "working/checkpoints/email.json" in handoff["approval_step"])
        check("checkpoint written on the prepared path",
              (run1 / CHECKPOINT_REL).is_file())

        # 4. Elected, sales NOT elected: promo not_applicable, appt prepared.
        run2 = root / "run2"
        (run2 / "working" / "copy").mkdir(parents=True)
        ck = prepare_draft_packages(
            run2, intake_with({WANT_FIELD: "yes", SALES_WANT_FIELD: "no"}),
            skill50_dir=fake_skill, _skill50_searched=True)
        check("no page launch: promo not_applicable, appointment prepared",
              [p["status"] for p in ck["packages"]]
              == ["not_applicable", "prepared_draft"])

        # 5. Elected but Skill 50 unavailable: nothing prepared, recorded.
        run3 = root / "run3"
        (run3 / "working" / "copy").mkdir(parents=True)
        ck = prepare_draft_packages(
            run3, intake_with({WANT_FIELD: "yes", SALES_WANT_FIELD: "yes"}),
            skill50_dir=None, _skill50_searched=True)
        check("Skill 50 unavailable: nothing prepared, fallback recorded",
              ck["outcome"] == "elected_skill50_unavailable_nothing_prepared"
              and not (run3 / BRIEF_REL).exists()
              and (run3 / CHECKPOINT_REL).is_file())

        # 6. Declined: checkpoint carries the verbatim quote; no package dir.
        run4 = root / "run4"
        (run4 / "working" / "copy").mkdir(parents=True)
        ck = prepare_draft_packages(
            run4, intake_with({WANT_FIELD: "no",
                               REASON_FIELD: "We run our own email."}),
            skill50_dir=fake_skill, _skill50_searched=True)
        check("declined: waived, verbatim quote on the run record",
              ck["outcome"] == "waived_nothing_prepared"
              and ck["waiver"]["client_request_quote"]
              == "We run our own email."
              and not (run4 / "working" / "email").exists())

        # 7. Unanswered: deferred, recorded, nothing prepared.
        run5 = root / "run5"
        (run5 / "working" / "copy").mkdir(parents=True)
        ck = prepare_draft_packages(run5, intake_with({}),
                                    skill50_dir=fake_skill,
                                    _skill50_searched=True)
        check("unanswered: deferred, recorded, nothing prepared",
              ck["outcome"] == "deferred_nothing_prepared"
              and not (run5 / "working" / "email").exists())

    print("=" * 50)
    if fails:
        print(f"[selftest] FAIL ({len(fails)} check(s)): {fails}")
        return 1
    print("[selftest] PASS (gate decisions both shapes; elected prepares a "
          "draft package awaiting human approval; declined/unanswered/"
          "unavailable prepare nothing and the run record says why)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", default=None,
                    help="deck run directory (contains working/copy/intake.json)")
    ap.add_argument("--selftest", action="store_true",
                    help="offline deterministic self-test")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.run_dir:
        ap.error("--run-dir is required (or --selftest)")
    run_dir = Path(args.run_dir).expanduser()
    if not run_dir.is_dir():
        print(f"error: run dir not found: {run_dir}", file=sys.stderr)
        return EXIT_USAGE
    intake = load_intake(run_dir)
    if not intake:
        print(f"error: no readable intake.json under {run_dir / 'working' / 'copy'}",
              file=sys.stderr)
        return EXIT_USAGE
    checkpoint = prepare_draft_packages(run_dir, intake)
    decision = checkpoint["gate"]["decision"]
    print(f"email gate: {decision} -- {checkpoint['gate']['detail']}")
    print(f"outcome: {checkpoint['outcome']} "
          f"(run record: {checkpoint['_checkpoint_path']})")
    if decision == "fail_closed":
        return EXIT_GATE_BLOCKED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
