#!/usr/bin/env python3
"""prove_content_conversation_loop.py — U88 / GK-26: "The content->conversation
loop, proven end-to-end once on the operator's own box" (master spec crosswalk
G+K.6, GK-26; master id U88).

SCOPE — TWO-TIER PROOF (read this before changing acceptance behavior)
-----------------------------------------------------------------------------
GK-26's own BINARY acceptance text asks for a live operator-box run: a real
Skill 35 post through the real pipeline, a real Tier-0 `caf social create-post`
write, a real inbound DM landing in GHL Conversations, a real Skill 38 brain
reply, and a real Gap-C matcher call — each leg read back from the live system.
That is unavoidably a **live-infra proof**: no fresh scratchpad clone can prove
it, because there is nothing live to read back from.

The master spec's ratified PER-REPO / OFFLINE ACCEPTANCE DOCTRINE (Section E.3,
"OPERATOR RULINGS 2026-07-15 — WAVE-ONE ACCEPTANCE-CRITERIA SPEC AMENDMENT")
states the general principle this build follows: a criterion that can only be
proven by live infra is NOT a merge-gate criterion on its own — it is a
LIVE-PROOF, legitimately deferred, while the CODE backing it must still clear
its own bar **provably, per-repo, and offline** (fixtures / seeds / stubs /
injected clocks, zero network). That doctrine was written for A-U4/A-U5/A-U6/
A-U7/B-U7/B-U8/B-U10 by name, but the same amendment explicitly says "any other
live/operator-box criterion elsewhere in the spec follow[s] the same PER-REPO/
OFFLINE doctrine on principle." U22 (B-U8) and U84 (GK-22) already ship exactly
this two-tier shape in this repo: an OFFLINE/CODE-MERGE tier that is fully
provable now, and a LIVE-PROOF tier that stays honestly "owed" until it is run
for real, once, on the operator's own box.

This script is that OFFLINE/CODE-MERGE tier for U88/GK-26:

  * Leg 1 (Skill 35 pre-gen gate + CTA shape)   — REAL module call, fully offline.
  * Leg 2 (Skill 44 Tier-0 `caf social create-post` + read-back) — driven through
    an injectable adapter seam. The FIXTURE adapter (default, used here) is
    deterministic and touches no network. The LIVE adapter is a documented stub
    (see `LiveAdapters` below) that raises rather than silently fabricate a
    live write — filling it in and running it for real, once, on the operator's
    own box IS the LIVE-PROOF tier this unit still owes.
  * Leg 3 (inbound DM -> GHL Conversations -> Skill 38 tier-ladder brain reply)
    — the tier-ladder RESOLUTION half is a REAL module call against Skill 38's
    own proven fixture pair (tools/tests/fixtures/sample-log.md +
    good-playbook.md); the GHL-Conversations round-trip + the brain's actual
    reply are the live-infra half, same adapter seam as leg 2.
  * Leg 4 (Skill 35 comment_reader synthetic handoff) — REAL module call, fully
    offline (comment_reader.py is itself network-free by design).
  * Leg 5 (Gap C — Skill 6 funnel_matcher fallback + client-link sovereignty)
    — REAL module call (funnel_matcher.match_funnel) against the real 38-
    template catalog on disk; the "page link" a live build would resolve to is
    a clearly-labeled FIXTURE placeholder (no live GHL page exists offline).

Zero client-visible messages are ever sent by this script: FixtureAdapters
makes no network call of any kind (no urllib/http/socket import, no
subprocess call to `caf`), and LiveAdapters is never instantiated by the
default `run()` path — it exists only as a documented seam for the future
live run. See test_prove_content_conversation_loop.py for a fail-first
regression that pins both properties.

Run:
    python3 35-social-media-planner/scripts/prove_content_conversation_loop.py
    or: pytest 35-social-media-planner/scripts/test_prove_content_conversation_loop.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent                      # 35-.../scripts
_35_DIR = _HERE.parent
_REPO_ROOT = _35_DIR.parent
_06_TOOLS = str(_REPO_ROOT / "06-ghl-install-pages" / "tools")
_38_TOOLS = str(_REPO_ROOT / "38-conversational-ai-system" / "tools")

for _p in (str(_HERE), _06_TOOLS, _38_TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pregen_prompt_gate as pgg  # noqa: E402  (Skill 35, leg 1)
import comment_reader  # noqa: E402  (Skill 35, leg 4)
import funnel_matcher as fm  # noqa: E402  (Skill 6, leg 5 / Gap C)
import playbook_engine as pbe  # noqa: E402  (Skill 38, leg 3)

_FUNNEL_TEMPLATES_ROOT = str(_REPO_ROOT / "06-ghl-install-pages" / "funnel-templates")
_38_FIXTURES = _REPO_ROOT / "38-conversational-ai-system" / "tools" / "tests" / "fixtures"
_38_PREREQ_SCRIPT = _REPO_ROOT / "38-conversational-ai-system" / "scripts" / "00-verify-prerequisites.sh"

RUN_MODE_OFFLINE_FIXTURE = "offline-fixture"

# The exact known-good corpus phrase funnel_matcher_cli.py's own selftest already
# proves resolves to the lead-magnet/squeeze-page family — reused verbatim so
# this leg is not a second, unproven vocabulary.
_GAP_C_REQUEST_TEXT = "I want to grow my email list with a free guide"
_GAP_C_EXPECTED_TEMPLATES = {"squeeze-page", "lead-magnet"}


# =============================================================================
# Adapters — the ONE seam between the OFFLINE/CODE-MERGE tier (this script)
# and the LIVE-PROOF tier a future operator-box run owes. See module docstring.
# =============================================================================

class FixtureAdapters:
    """Deterministic, offline, ZERO network. Every method returns a value
    shaped exactly like the real live call's response so the harness logic
    (evidence-bundle assembly, pass/fail wiring) is proven against the real
    interface shape without touching a live box. No urllib/http/socket import
    anywhere in this class — enforced by test_zero_network_import_in_fixture_
    adapters_module in the companion test file."""

    def __init__(self, seed_id: str = "u88-proof") -> None:
        self.seed_id = seed_id

    def create_social_post(self, *, account_ids, text, media_url=None, schedule=None):
        # Real shape mirrors caf's `social create-post` -> `_output(ctx, data,
        # "Post Created")" envelope (44-convert-and-flow-operator/tools/engine/
        # cli_anything/gohighlevel/gohighlevel_cli.py, social_create_post()).
        return {"id": "fixture-post-%s" % self.seed_id, "status": "draft",
                "accountIds": list(account_ids), "summary": text,
                "media": [{"url": u, "type": "image"} for u in (media_url or [])]}

    def read_social_post(self, post_id: str):
        return {"id": post_id, "status": "draft"}

    def deliver_inbound_dm(self, contact_id: str, text: str):
        return {"conversation_id": "fixture-convo-%s" % self.seed_id,
                "contact_id": contact_id, "channel": "sms", "inbound_text": text}

    def brain_reply(self, resolved_tier_ladder: dict):
        tools = ", ".join(resolved_tier_ladder.get("enabled_tools") or [])
        return {
            "reply_text": (
                "[FIXTURE brain reply — represents the live-infra leg deferred to "
                "the operator-box LIVE-PROOF run] workflow=%s phase=%s tools=[%s]"
                % (resolved_tier_ladder.get("active_workflow"),
                   resolved_tier_ladder.get("active_phase"), tools)),
            "tier_used": "fixture-resolved-from-playbook-header",
        }


class LiveAdapters:
    """Deliberately NOT implemented in this build. Wiring these four methods
    to the real `caf social create-post` CLI, a real GHL Conversations
    round-trip, and Skill 38's real inbound webhook + brain IS the LIVE-PROOF
    tier GK-26's own acceptance text describes ("driven ... on the operator's
    own box"). It needs real credentials, a real GHL location, and a human
    present to watch for client-visible leakage — none of which a fresh
    scratchpad clone has. Per the master spec's ratified PER-REPO/OFFLINE
    ACCEPTANCE DOCTRINE and this build's explicit branch/repo-only constraint
    (no live-box deploy, no fleet roll), every method here raises rather than
    silently fabricate a live result — each message cites the exact real call
    it stands in for, so the operator-box run has the four seams already named.
    `run()` below NEVER instantiates this class by default.
    """

    def create_social_post(self, *, account_ids, text, media_url=None, schedule=None):
        raise NotImplementedError(
            "LIVE-PROOF tier owed: `caf social create-post --account-id <id> "
            "--text <text> [--media-url <url>]` (44-convert-and-flow-operator "
            "Tier-0 rail). Run on the operator's own box only.")

    def read_social_post(self, post_id: str):
        raise NotImplementedError(
            "LIVE-PROOF tier owed: `caf social posts` read-back for the queued "
            "post id, on the operator's own box only.")

    def deliver_inbound_dm(self, contact_id: str, text: str):
        raise NotImplementedError(
            "LIVE-PROOF tier owed: send a real inbound DM and read it back via "
            "GHL Conversations, confirming it reaches Skill 38's inbound "
            "webhook, on the operator's own box only.")

    def brain_reply(self, resolved_tier_ladder: dict):
        raise NotImplementedError(
            "LIVE-PROOF tier owed: the real conversational brain's reply, read "
            "back from GHL Conversations after Skill 38's tier-ladder routing, "
            "on the operator's own box only.")


# =============================================================================
# Leg 1 — Skill 35: pre-gen gate (real) -> image + Section-19 QC (fixture,
# standing in for the live, paid kie.ai generation this offline proof must
# never trigger) -> DM-first-with-comment-backup CTA shape (deterministic).
# =============================================================================

def leg1_pregen_gate_and_qc() -> dict:
    post_copy = (
        "Ready to grow your list the smart way? DM us the word GROW and we will "
        "send the swipe file straight to your inbox -- or grab the link in the "
        "comments if DMs are slow to load for you."
    )
    prompt_text = (
        "A warm, editorial flat-lay of a laptop and coffee on a wooden desk, "
        "brand-appropriate, appropriate for the client's audience, no "
        "suggestive content, soft daylight, no on-image text."
    )
    gate_result = pgg.check_prompt(
        prompt_text,
        model="nano-banana-2",
        ratio="4:5",
        pixels="1080x1350",
        platform="instagram",
        text_overlay=None,
        brand_colors="#0B3D2E,#F5EFE0",
        avoid_list_text="no stock-photo smiles, no clipart",
        asset_source="internal-generated",
        qc_receipt=None,
    )
    # FIXTURE — stands in for the live, paid kie.ai generation call + the
    # Section-19 QC Image Checklist scoring pass. Never claimed as "run";
    # explicitly labeled as a fixture representing the deferred live leg.
    qc19_receipt_fixture = {
        "pass": True, "average": 9.1, "checklist": "playbook.md Section 19",
        "source": "FIXTURE -- live kie.ai generation + Section-19 scoring not "
                  "run in this offline proof",
    }
    lower_copy = post_copy.lower()
    dm_idx = lower_copy.find("dm")
    comment_idx = lower_copy.find("comment")
    cta_dm_first = dm_idx != -1 and comment_idx != -1 and dm_idx < comment_idx

    ok = gate_result.ok and qc19_receipt_fixture["pass"] and cta_dm_first
    return {
        "pass": bool(ok),
        "pregen_gate_ok": gate_result.ok,
        "pregen_gate_exit_code": gate_result.exit_code,
        "pregen_gate_problems": gate_result.form_problems + gate_result.quality_problems,
        "qc19_receipt": qc19_receipt_fixture,
        "cta_dm_first_with_comment_backup": cta_dm_first,
        "post_copy": post_copy,
    }


# =============================================================================
# Leg 2 — Skill 44 Tier-0 rail: `caf social create-post` + read-back.
# =============================================================================

def leg2_queue_draft_post(adapters, post_copy: str) -> dict:
    created = adapters.create_social_post(account_ids=["fixture-account-1"], text=post_copy)
    read_back = adapters.read_social_post(created["id"])
    ok = (bool(created.get("id"))
          and read_back.get("id") == created.get("id")
          and read_back.get("status") == "draft")
    return {"pass": bool(ok), "queued_post_id": created.get("id"), "read_back": read_back}


# =============================================================================
# Leg 3 — inbound DM -> GHL Conversations -> Skill 38's documented tier ladder.
# The RESOLUTION half is real (Skill 38's own proven fixture pair); the
# GHL-Conversations round-trip + the brain's live reply run through the
# adapter seam.
# =============================================================================

def leg3_inbound_dm_tier_ladder(adapters) -> dict:
    log_text = (_38_FIXTURES / "sample-log.md").read_text(encoding="utf-8")
    playbook_text = (_38_FIXTURES / "good-playbook.md").read_text(encoding="utf-8")

    resolved = pbe.resolve_from_log(log_text, playbook_text)
    parsed_playbook = pbe.parse_playbook(playbook_text)

    delivered = adapters.deliver_inbound_dm(contact_id="c_test_0001",
                                            text="Can I book a call?")
    reply = adapters.brain_reply(resolved)

    ok = (resolved["active_workflow"] == "good-playbook"
          and resolved["active_phase"] == 4
          and resolved["enabled_tools"] is not None
          and "book_appointment" in resolved["enabled_tools"]
          and bool(delivered.get("conversation_id"))
          and bool(reply.get("reply_text")))
    return {
        "pass": bool(ok),
        "conversation_id": delivered.get("conversation_id"),
        "brain_reply": reply.get("reply_text"),
        "tier_ladder": {
            "active_workflow": resolved["active_workflow"],
            "active_phase": resolved["active_phase"],
            "enabled_tools": resolved["enabled_tools"],
            "model_tier": parsed_playbook["header"].get("model_tier"),
        },
    }


# =============================================================================
# Leg 4 — Skill 35 comment_reader: prospect comment -> fenced synthetic
# handoff into conversational-logs/. REAL module call, fully offline.
# =============================================================================

def leg4_comment_handoff(evidence_root: str) -> dict:
    master_files_dir = os.path.join(evidence_root, "master-files")
    events = [{
        "channel": "facebook",
        "post_id": "fixture-post-u88-proof",
        "permalink": "https://facebook.com/fixture/posts/1",
        "comment_id": "cmt-1",
        "author_id": "prospect-77",
        "author_name": "Prospect Seventy Seven",
        "text": "just commented for the link, thanks!",
        "created_at": "2026-07-15T00:00:00Z",
    }]
    summary = comment_reader.run(events, master_files_dir, dry_run=False)
    handed = summary["handed_off"]
    base_ok = len(handed) == 1 and len(summary["skipped"]) == 0
    fenced_ok = False
    log_path = None
    if base_ok:
        log_path = handed[0]["log_path"]
        fenced_ok = os.path.isfile(log_path)
        if fenced_ok:
            text = Path(log_path).read_text(encoding="utf-8")
            fenced_ok = ("<<<UNTRUSTED-PUBLIC-COMMENT" in text
                        and "<<<END-UNTRUSTED-PUBLIC-COMMENT>>>" in text)
    return {
        "pass": bool(base_ok and fenced_ok),
        "fenced_handoff_file": log_path,
        "handed_off": handed,
        "skipped": summary["skipped"],
    }


# =============================================================================
# Leg 5 — Gap C: no client link -> Skill 6 funnel_matcher fallback; client
# link supplied -> sovereignty wins, matcher never even called.
# =============================================================================

def _load_catalog():
    return fm.Catalog.load(_FUNNEL_TEMPLATES_ROOT)


def _fixture_page_link_for_template(template_id: str) -> str:
    """FIXTURE placeholder standing in for the live GHL page-URL lookup an
    operator-box run performs after a page is actually built/published.
    Deliberately non-resolvable so it can never be mistaken for a real URL."""
    return "<GHL-PAGE-URL-PLACEHOLDER:%s>" % template_id


def resolve_post_link(client_link, request_text: str, catalog) -> dict:
    """Gap C glue: the same sovereignty doctrine already governing every other
    client-owned value in this fleet (client-owned tokens; explicit desire
    never overridden by a suggestion -- funnel_matcher.py's own Mode-1
    docstring: 'no suggestion overrides explicit user desire'). A
    client-supplied link is NEVER overridden, and the matcher is NEVER even
    called in that branch -- the matcher is a fallback, not a competitor to
    sovereignty."""
    if client_link:
        return {"source": "client_supplied", "link": client_link,
                "matcher_invoked": False, "matcher_receipt": None}
    decision = fm.match_funnel({"text": request_text, "just_do_it": True}, catalog)
    link = (_fixture_page_link_for_template(decision["matched_template"])
            if decision.get("matched_template") else None)
    return {"source": "matcher", "link": link, "matcher_invoked": True,
            "matcher_receipt": decision}


def leg5_gap_c_matcher() -> dict:
    catalog = _load_catalog()
    no_link_case = resolve_post_link(None, _GAP_C_REQUEST_TEXT, catalog)
    client_supplied = "https://client-domain.example/their-own-page"
    client_link_case = resolve_post_link(client_supplied, _GAP_C_REQUEST_TEXT, catalog)

    no_link_ok = (no_link_case["matcher_invoked"] is True
                  and no_link_case["link"] is not None
                  and no_link_case["matcher_receipt"] is not None
                  and no_link_case["matcher_receipt"]["matched_template"]
                      in _GAP_C_EXPECTED_TEMPLATES)
    client_link_ok = (client_link_case["matcher_invoked"] is False
                      and client_link_case["link"] == client_supplied
                      and client_link_case["matcher_receipt"] is None)
    return {
        "pass": bool(no_link_ok and client_link_ok),
        "no_link_case": no_link_case,
        "client_link_case": client_link_case,
        "matcher_receipt": no_link_case["matcher_receipt"],
    }


# =============================================================================
# STEP F preflight — best-effort evidence only (never gates a leg). Skill 38's
# own 00-verify-prerequisites.sh STEP F is non-fatal and read-only by design
# (see that script's own header comment).
# =============================================================================

def step_f_preflight_report() -> dict:
    if not _38_PREREQ_SCRIPT.is_file():
        return {"ran": False, "reason": "00-verify-prerequisites.sh not found"}
    # ISOLATED environment: this offline proof must NEVER read the operator's
    # REAL ~/.openclaw secrets/paths, even though the script itself documents
    # itself as read-only/idempotent. Point HOME/MASTER_FILES_DIR/
    # OPENCLAW_SKILLS_DIR at a private, empty tempdir so the script's own
    # env-file probing can only ever find nothing (or fixtures this process
    # itself wrote), never live credentials or a live install. This keeps the
    # branch/repo-only constraint intact while still exercising the real
    # shipped script for genuine plumbing evidence.
    try:
        with tempfile.TemporaryDirectory(prefix="u88-step-f-isolated-home-") as isolated_home:
            env = {
                "HOME": isolated_home,
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "MASTER_FILES_DIR": os.path.join(isolated_home, "master-files"),
                "OPENCLAW_SKILLS_DIR": os.path.join(isolated_home, "skills"),
            }
            proc = subprocess.run(
                ["bash", str(_38_PREREQ_SCRIPT)],
                capture_output=True, text=True, timeout=30, check=False,
                env=env,
            )
    except Exception as exc:  # noqa: BLE001 -- best-effort evidence, never fatal
        return {"ran": False, "reason": "could not execute: %s" % exc}
    step_f_line = next(
        (ln for ln in proc.stdout.splitlines() if "BUILD PATH" in ln), None)
    note = None
    if step_f_line is None:
        note = ("STEP F is non-fatal in the real script, but an EARLIER hard "
                "prereq (Cloudflare key, or skills 05/10/19/29) legitimately "
                "halts this in a repo-only sandbox with no OpenClaw install -- "
                "that halt is reported honestly here, never treated as a leg "
                "failure and never faked as a PASS. On the operator's own box "
                "this line is real evidence; here it is best-effort only.")
    return {"ran": True, "exit_code": proc.returncode,
            "step_f_active_build_path_line": step_f_line, "note": note}


# =============================================================================
# Orchestration + evidence bundle.
# =============================================================================

def run(evidence_root: str | None = None, adapters=None) -> tuple[bool, dict]:
    """Drive all five legs and write ONE evidence bundle. Returns (ok, bundle).

    When ``evidence_root`` is omitted, a throwaway tempdir is used and wiped
    on exit (the offline default -- there is nothing to "revert" because
    nothing outside the tempdir was ever touched). Pass an explicit
    ``evidence_root`` to persist the bundle (e.g. for archiving a real run)."""
    own_tmp = evidence_root is None
    _tmp = tempfile.TemporaryDirectory(prefix="u88-content-conversation-loop-") if own_tmp else None
    if own_tmp:
        evidence_root = _tmp.name
    try:
        adapters = adapters or FixtureAdapters()
        ok = True

        def check(label: str, cond: bool) -> bool:
            nonlocal ok
            ok = ok and bool(cond)
            print("  [%s] %s" % ("PASS" if cond else "FAIL", label))
            return bool(cond)

        print("=" * 78)
        print("U88 / GK-26 -- content->conversation loop, OFFLINE/FIXTURE proof run")
        print("(OFFLINE/CODE-MERGE tier only -- LIVE-PROOF tier deferred, see module docstring)")
        print("=" * 78)

        leg1 = leg1_pregen_gate_and_qc()
        check("Leg 1 (35): pre-gen gate clears + Sec-19 QC fixture passes + DM-first CTA",
              leg1["pass"])

        leg2 = leg2_queue_draft_post(adapters, leg1["post_copy"])
        check("Leg 2 (44 Tier-0 caf social create-post): draft queued + read back",
              leg2["pass"])

        leg3 = leg3_inbound_dm_tier_ladder(adapters)
        check("Leg 3 (GHL Conversations -> 38): inbound resolves via the documented tier ladder",
              leg3["pass"])

        leg4 = leg4_comment_handoff(evidence_root)
        check("Leg 4 (35 comment_reader): fenced synthetic handoff written",
              leg4["pass"])

        leg5 = leg5_gap_c_matcher()
        check("Leg 5 (Gap C, Skill 6 funnel_matcher): fallback + client-link sovereignty",
              leg5["pass"])

        step_f = step_f_preflight_report()
        print("  [INFO] Skill 38 STEP F preflight: %s"
              % (step_f.get("step_f_active_build_path_line") or step_f.get("reason") or "n/a"))

        bundle = {
            "unit": "U88 (GK-26)",
            "run_mode": RUN_MODE_OFFLINE_FIXTURE,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "zero_client_visible_messages": True,
            "live_proof_tier_owed": True,
            "legs": {
                "leg1_pregen_gate_and_qc": leg1,
                "leg2_queued_post": leg2,
                "leg3_inbound_conversation": leg3,
                "leg4_comment_handoff": leg4,
                "leg5_gap_c_matcher": leg5,
            },
            "step_f_preflight": step_f,
            "overall_pass": ok,
        }
        bundle_path = os.path.join(evidence_root, "u88-content-conversation-loop-evidence.json")
        os.makedirs(evidence_root, exist_ok=True)
        with open(bundle_path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2)
        bundle["_bundle_path"] = bundle_path

        print("-" * 78)
        print("evidence bundle: %s" % bundle_path)
        print("== U88/GK-26 OFFLINE/FIXTURE proof: %s =="
              % ("ALL LEGS PASSED" if ok else "FAILED"))
        return ok, bundle
    finally:
        if own_tmp:
            _tmp.cleanup()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="U88/GK-26 content->conversation loop OFFLINE/FIXTURE proof run")
    ap.add_argument("--evidence-root", default=None,
                    help="persist the evidence bundle here instead of a throwaway tempdir")
    args = ap.parse_args(argv)
    if args.evidence_root:
        os.makedirs(args.evidence_root, exist_ok=True)
        ok, _bundle = run(evidence_root=args.evidence_root)
    else:
        ok, _bundle = run()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
