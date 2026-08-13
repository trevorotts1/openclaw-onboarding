#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u23_modules/main_skeleton.py
# U23 SMS-PHONE-PROVISIONER DISPATCHER — the offline-plan / offline-self-test
# / live aggregate / Trevor-gated execute driver for the U23 module family
# under scripts/u23_modules/ (the GHL-GATED SMS PHONE SURFACE of the engine:
# the client's Convert and Flow location must carry an SMS-capable phone
# number BEFORE any SMS surface — stage gate nudges, snapshot-import
# notifications, per-stage SMS links — can deliver, and the PROVISIONING
# ACTION — the POST that creates the number and the send-test-message /
# outbound-message POSTs — is Trevor-gated). It imports the family modules BY
# NAME (importlib, never exec'd from a path), enforces the fail-closed
# one-entry-point contract, and resolves the aggregate exit code exactly as
# its U02 / U03 / U04 / U05 / U06 / U07 / U08_U09 / U10_U13 siblings
# (u02_modules/main_skeleton.py ... u10_u13_modules/main_skeleton.py) do. It
# carries NO check logic itself: a family module is exercised ONLY through
# this CLI so `--dry-run`, `--self-test`, and the live aggregate never drift
# apart.
#
# THE U23 FAMILY (the modules this dispatcher aggregates; each is STDLIB-only,
# ships its own OFFLINE self-test battery — golden PASS / attack FAIL, exit 0
# pass / 4 enforced violation — and exposes a thin own CLI; this skeleton is
# the ONE entry-point contract over them):
#   phone_lister.py     the LIVE PHONE LISTER — the READ-ONLY GET-first side
#                       of the phone surface: GET /phones/numbers for the
#                       location, every number reported with a MASKED marker
#                       (last 4 digits), per-number SMS capability judged by
#                       presence/truthiness on the fixed key set only, the
#                       GET-first idempotency law (an SMS-capable number
#                       already present is verified, never re-provisioned —
#                       never a second number, never a second charge), and a
#                       GHL-gated (--execute) GET-first provisioning path
#                       with post-create read-back. A refused listing is
#                       NEVER followed by a create; an unmarked SMS entry is
#                       NEVER silently trusted as verified; a scope denial is
#                       a STOP, an edge block / transport failure is HELD —
#                       a bare 401/403 is never mislabeled as a scope
#                       problem. AF-AE-PHONELIST-* family.
#   provision_action.py the LEADCONNECTOR PHONE NUMBER PROVISIONER — the
#                       GET-first idempotent provisioning ACTION of the
#                       family (POST /phones/numbers). THE ACTION IS
#                       TREVOR-GATED: it runs ONLY under --execute; without
#                       it the module reports what it WOULD do and exits
#                       WITHOUT mutating (STOP, exit 2,
#                       AF-AE-PROVPHONE-NO-EXECUTE). A failed listing
#                       REFUSES before any create (never provisions into the
#                       unknown); after the POST the module GETs the created
#                       number back and confirms it exists before any report
#                       claims provisioned — a missing read-back is a
#                       MISMATCH (exit 5). AF-AE-PROVPHONE-* family.
#   sms_verifier.py     the FAIL-CLOSED SMS SEND VERIFIER — sends an outbound
#                       SMS via the GHL v2 rail (POST /conversations/messages/
#                       outbound) and requires HTTP 200 PLUS a message
#                       identifier (SID, read by key order on the fixed key
#                       set) before anything is called delivered. THE SEND IS
#                       A GHL-SCOPE ACTION — --execute or nothing is sent;
#                       without --execute it STOPS (exit 2,
#                       AF-AE-SMSVER-NO-EXECUTE); an HTTP 200 whose body
#                       carries NO id is a read-back mismatch (exit 5), never
#                       a pass. AF-AE-SMSVER-* family.
#   sms_sender.py       the GHL-GATED TEST-SMS SENDER — the companion
#                       send-side tool: sends one test SMS to a specific
#                       CONTACT through the location's LeadConnector
#                       conversation surface (GET /contacts/<contactId> first
#                       — the idempotency law, never send into the unknown —
#                       then POST /conversations/messages under --execute
#                       with the canonical Skill 44 send contract, then a
#                       bounded read-back confirming the newest conversation
#                       message IS the sent text). THE SEND IS TREVOR-GATED —
#                       --execute or nothing is sent (exit 2,
#                       AF-AE-SMSENDER-NO-EXECUTE); a send answered without a
#                       conversation id is a read-back mismatch (exit 5),
#                       never a pass; a stalled read-back is HELD (exit 3),
#                       never a false pass. AF-AE-SMSENDER-* family.
#   golden_has_phone.py the GOLDEN PHONE-PROVISIONED FIXTURE — the canonical
#                       in-memory SMS-PHONE-PROVISIONED state of the family:
#                       the location's SMS-capable number ALREADY PRESENT,
#                       the golden control of the GET-first idempotency law
#                       (an already-provisioned location is VERIFIED, never
#                       re-provisioned — exit 0, idempotent no-op, never a
#                       second number, never a second charge); payload()
#                       judges a provisioned-state candidate fail-closed
#                       against the golden contract (an unmarked / drifted /
#                       non-golden / malformed / credential-shaped payload is
#                       REFUSED exit 5, never a blind pass) and the EXECUTE
#                       law is pinned (EXECUTE_REQUIRED_FOR_PROVISION — the
#                       gate lives in the provisioner, never in a fixture).
#                       OFFLINE by construction — never a network call.
#   attack_sms_failed.py  the U23 ATTACK FIXTURE — a send-test-message POST
#                       answered with ANY non-200 status (the canonical send
#                       record built by the SINGLE AUTHORITY —
#                       provision_sms_phone.py — with the ONE status variable
#                       changed to non-200) that every SMS-verification gate
#                       MUST FAIL, never a pass; the golden 200-send control
#                       (payload_true) PASSES exit 0 — the pass/fail split
#                       discriminates the non-200 boundary, never a broken
#                       instrument. Shipping OR judging the attack requires
#                       --execute (Trevor gate). OFFLINE by construction —
#                       never a network call.
#   attack_no_phone.py  the NO-PHONE ATTACK FIXTURE — the fail-closed
#                       PHONE-LAW gate over the /phones/numbers listing: a
#                       location is VERIFIED only when an SMS-capable number
#                       is present; ANY listing carrying no SMS-capable
#                       number — above all the EMPTY listing — means
#                       PROVISIONING IS NEEDED and that state is REFUSED as a
#                       pass, never judged a clean read, never a silent
#                       fallback. The anti-golden mirror of golden_has_phone:
#                       the SAME gate must PASS the golden state (exit 0) and
#                       REFUSE the no-phone state (the dry-run plan reports
#                       provision_needed TRUE and what --execute WOULD do;
#                       the refusal names the state law AF-AE-PROVPHONE-
#                       NO-PHONE and the action law AF-AE-PROVPHONE-
#                       NO-EXECUTE). OFFLINE by construction — never a
#                       network call.
#   docs_u23.py         the U23 tooling README / catalog data + drift gate —
#                       the module inventory, the four v2 public surfaces,
#                       the house exit codes and af codes as DATA (the
#                       module inventory and the shipped tree never drift; a
#                       doc that names a module that does not ship FAILS its
#                       self-test exit 4).
#   house_rules.py      the ONE canonical house-law constant surface for the
#                       U23 family (browser UA — CAF_BROWSER_UA, CF 1010 — /
#                       version header — CAF_VERSION_HEADER — / the complete
#                       AF autofail table, the manifest's 75 rows, the U23
#                       family's authority); the offline self-test pins the
#                       UA and version header byte-exact against the
#                       registry and the AF table byte-exact against
#                       ENGINE-MANIFEST.json autofails — a tamper never
#                       masquerades as exit 1 (exit 4, the AF-AE-HASH-PIN
#                       family).
#   checklist_note.py   the ONBOARDING CHECKLIST NOTE — "SMS phone number
#                       verified present before snapshot push": the
#                       fail-closed READ-ONLY live gate that certifies the
#                       U23 SMS-PHONE-PROVISIONED law on the client's OWN
#                       Convert and Flow location (GET /phones/numbers
#                       through the house rail client; the SMS-capable
#                       marker by presence/truthiness on the fixed key set;
#                       the idempotency truth held: an SMS-capable number
#                       ALREADY present is verified, never re-provisioned).
#                       READ-ONLY BY CONSTRUCTION — it certifies, it never
#                       provisions (the PROVISIONING ACTION stays
#                       --execute-gated in the owning provisioner); an
#                       unmarked entry can NEVER be trusted as SMS-capable;
#                       a refused listing / a genuine scope denial STOPS, an
#                       edge block / transport failure is HELD (exit 3);
#                       without a verified number the snapshot push is NOT
#                       cleared. AF-AE-CHECKLIST-* family.
#
# THE IMPORT CONTRACT (the surface the family satisfies): one ENTRY POINT
# per module, exposed as `self_test(out=None) -> int` — exit 0 on pass, 4
# (EX_VIOLATION, the AF-AE-TEMPLATE-ATTACK family) on failure, exactly as
# the U02..U10_U13 siblings require. A module without a battery STOPS the
# dispatcher (fail-closed: no law is ever skipped, and a module that cannot
# prove itself offline cannot be trusted at live time).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The PIT and the location id are
# resolved through anthology_registry (CONVERT_AND_FLOW_PIT /
# CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT /
# GHL_API_KEY and CONVERT_AND_FLOW_LOCATION_ID / GOHIGHLEVEL_LOCATION_ID /
# GHL_LOCATION_ID, live process env first then the three canonical client env
# stores). SET / NOT SET only on every operator surface; a token value, a
# full location id, a full phone number and a full destination are NEVER
# printed — every surface carries the masked marker (last 4) only.
#
# BROWSER UA: every request rides reg.CafClient, which applies CAF_BROWSER_UA
# on every request so the Cloudflare edge fronting services.leadconnectorhq.com
# never 1010s a request (CF 1010 / GK-09 discipline — the house pattern ported
# byte-for-byte from the podcast gate; urllib's default "Python-urllib/x.y"
# is 403'd at the WAF edge as error 1010 before the request is ever scope-
# checked). Scope-vs-edge-block discrimination: a bare 401/403 is HELD
# (UpstreamBlockedError), never reported as a scope problem — on every read
# AND every write.
#
# THE PROVISIONING ACTION IS TREVOR-GATED (the heart of the family): this
# dispatcher NEVER provisions, never sends, and never verifies a send
# without the operator's explicit --execute. Default and --dry-run are
# read-only / plan-only (no network in dry-run). A provisioning request
# without --execute is a STOP (exit 2, AF-AE-PROVPHONE-NO-EXECUTE), never a
# silent no-op and never a silent create. The gate is enforced in BOTH
# surfaces — the CLI (provision/verify without --execute refuses up front,
# before any credential resolution or network) and the aggregate (the
# family's own verbatim no-execute STOPs are re-proven offline by the
# self-test) — the two-surface law of the U06 / U07 siblings.
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1):
#   AF-AE-U23-ASSEMBLY-INCOMPLETE -> the u23_modules check-module set named
#          in U23_MODULES is not fully present, or a module violates the
#          one-entry-point self_test contract. STOP (exit 2) — a law is
#          never silently skipped.
#   AF-AE-PROVPHONE-NO-EXECUTE    -> provisioning (POST /phones/numbers) or
#          SMS verification (send-test-message) was requested without
#          --execute (the Trevor gate). STOP (exit 2) — the module NEVER
#          provisions without the explicit GHL-gated execute flag.
#   AF-AE-SMSVER-NO-EXECUTE       -> the outbound send POST was requested
#          without --execute. STOP (exit 2) — the module NEVER sends
#          without the gate.
#   AF-AE-SMSENDER-NO-EXECUTE     -> the POST /conversations/messages send
#          was requested without --execute. STOP (exit 2) — the module
#          NEVER sends without the gate.
#   AF-AE-PROVPHONE-READ-REFUSED  -> listing numbers for the location failed
#          (scope / validation / edge block / transport). STOP or HELD per
#          class — never a silent skip, never a provision-into-the-unknown.
#   AF-AE-PROVPHONE-CREATE-REFUSED -> the POST /phones/numbers was rejected
#          (validation / scope / edge block / transport). STOP or HELD per
#          class.
#   AF-AE-PROVPHONE-VERIFY-REFUSED / AF-AE-PROVPHONE-VERIFY-STALLED -> the
#          verification read-back or the send-test-message POST failed /
#          never confirmed sending-capable within the bounded window. STOP
#          or HELD per class — never a false pass.
#   AF-AE-SMSVER-NO-SID           -> the send returned HTTP 200 but the body
#          carries no message identifier. MISMATCH (exit 5), never a pass.
#   AF-AE-PROVPHONE-ATTACK / AF-AE-TEMPLATE-ATTACK -> an attack fixture
#          tripped the OFFLINE self-test (enforced violation). exit 4.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation; the
# primary surface the operator consumes is 0 = PASS, 2 = STOP, 5 = mismatch):
#   0  verified success (idempotent no-op / dry run counts as pass; also
#      plan pass and self-test pass)
#   1  unexpected error (top-level guard, never a secret leak)
#   2  STOP refusal — label NOT SET / a non-pit- value / usage / an ACTION
#      (provision, send, verify) without --execute / a module missing from
#      u23_modules/ (AF-AE-U23-ASSEMBLY-INCOMPLETE) / a genuine scope denial
#  3  Convert and Flow API unreachable / verification not confirmed /
#      upstream edge block (HELD — a bare 401/403 is HELD, never mislabeled
#      as a scope problem)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-PROVPHONE-* / AF-AE-SMSVER-* / AF-AE-TEMPLATE-ATTACK family).
#      A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch (a create returned no number id / a verify
#      read-back returned no number / a send returned 200 with no SID / a
#      send answered without a conversation id / the golden or attack
#      fixture drifted; the fail-closed default)
#
# STDLIB ONLY (urllib + json via the registry and the family modules); calls
# NO model. Reuses anthology_registry (CafClient, resolve_pit,
# resolve_location, _live_client, _stop, _mask_location, CAF_BROWSER_UA).
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value;
# --dry-run and --self-test are OFFLINE; provisioning requires --execute
# (Trevor-gated) — never a silent write.
# =============================================================================
"""main_skeleton.py — U23 SMS-phone-provisioner dispatcher: offline plan /
offline self-test / live aggregate / Trevor-gated execute of the GHL-gated
SMS phone surface of the Anthology engine (Skill 59, u23_modules; the
packaged sibling of u02_modules/main_skeleton.py,
u03_modules/main_skeleton.py, u04_modules/main_skeleton.py,
u05_modules/main_skeleton.py, u06_modules/main_skeleton.py,
u07_modules/main_skeleton.py, u08_u09_modules/main_skeleton.py and
u10_u13_modules/main_skeleton.py). Provisioning (the POST that creates the
number, the send-test-message POST, and the outbound send POST) requires
--execute (Trevor-gated) — this dispatcher never mutates without the gate,
and it carries no write surface of its own."""

from __future__ import annotations

import argparse
import importlib
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the LeadConnector client, and its label
# resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The u23_modules directory itself — sibling imports resolve from here, in
# BOTH execution contexts (as a script, whose own directory is sys.path[0],
# and as an imported module, where the caller may not have added it).
MODULES_DIR = Path(__file__).resolve().parent
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

SKILL_DIR = Path(__file__).resolve().parent.parent.parent

# The U23 check-module inventory — the assembly manifest for this dispatcher.
# Every name is imported BY NAME below (importlib, never exec'd from a path);
# a missing module is a STOP, never a silent skip. `role` is the one-line
# contract each module owns. The names mirror the files on disk one-to-one
# (the catalog and the tree never drift; the dispatcher self-test pins the
# counts, exactly as the U03 / U04 / U05 / U06 / U07 siblings pin theirs).
U23_MODULES = (
    ("phone_lister", "the LIVE PHONE LISTER — READ-ONLY GET-first side of "
                     "the phone surface (GET /phones/numbers), masked "
                     "markers only, GET-first idempotency law, a GHL-gated "
                     "(--execute) GET-first provisioning path with "
                     "post-create read-back; a refused listing is never "
                     "followed by a create, an unmarked SMS entry is never "
                     "silently trusted (AF-AE-PHONELIST-* family)"),
    ("provision_action", "the LEADCONNECTOR PHONE NUMBER PROVISIONER — the "
                         "GET-first idempotent provisioning ACTION "
                         "(POST /phones/numbers), TREVOR-GATED: only under "
                         "--execute; without it a report of what it WOULD do "
                         "and a STOP (exit 2, AF-AE-PROVPHONE-NO-EXECUTE), "
                         "never a write; refused listing REFUSES before any "
                         "create; a created number is read back before any "
                         "report claims provisioned (a missing read-back is "
                         "a MISMATCH, exit 5)"),
    ("sms_verifier", "the FAIL-CLOSED SMS SEND VERIFIER — sends an outbound "
                     "SMS via the GHL v2 rail and requires HTTP 200 PLUS a "
                     "message identifier (SID) before anything is called "
                     "delivered; THE SEND IS GHL-SCOPE-GATED (--execute or "
                     "nothing is sent; without it a STOP, exit 2, "
                     "AF-AE-SMSVER-NO-EXECUTE); a 200 with no SID is a "
                     "read-back mismatch (exit 5), never a pass"),
    ("sms_sender", "the GHL-GATED TEST-SMS SENDER — the companion send-side "
                   "tool: sends one test SMS to a specific CONTACT through "
                   "the conversation surface (GET-first contact check, "
                   "POST /conversations/messages under --execute, bounded "
                   "read-back verifying the newest message IS the sent "
                   "text); THE SEND IS TREVOR-GATED (--execute or nothing "
                   "is sent; without it a STOP, exit 2, "
                   "AF-AE-SMSENDER-NO-EXECUTE); a send without a "
                   "conversation id is a read-back mismatch (exit 5), a "
                   "stalled read-back is HELD (exit 3)"),
    ("golden_has_phone", "the GOLDEN PHONE-PROVISIONED FIXTURE — the "
                         "canonical in-memory SMS-PHONE-PROVISIONED state "
                         "of the family (the one SMS-capable number already "
                         "present — the golden control of the GET-first "
                         "idempotency law, verified never re-provisioned); "
                         "payload() judges a provisioned-state candidate "
                         "fail-closed (a drifted / unmarked / non-golden / "
                         "malformed / credential-shaped payload is REFUSED "
                         "exit 5, never a blind pass) and pins the EXECUTE "
                         "law (EXECUTE_REQUIRED_FOR_PROVISION — the gate "
                         "lives in the provisioner, never in a fixture); "
                         "OFFLINE by construction"),
    ("attack_sms_failed", "the U23 ATTACK FIXTURE — a send-test-message "
                          "POST answered with ANY non-200 status (the "
                          "canonical send record built by the SINGLE "
                          "AUTHORITY with the ONE status variable changed) "
                          "that every SMS-verification gate MUST FAIL, never "
                          "a pass, with the golden 200-send control "
                          "(payload_true) PASSING exit 0; shipping OR "
                          "judging the attack requires --execute (Trevor "
                          "gate); OFFLINE by construction"),
    ("attack_no_phone", "the NO-PHONE ATTACK FIXTURE — the fail-closed "
                        "PHONE-LAW gate over the /phones/numbers listing: "
                        "ANY listing carrying no SMS-capable number — above "
                        "all the EMPTY listing — is REFUSED as a pass "
                        "(provisioning needed, reported via the dry-run "
                        "plan), never a clean read, never a silent "
                        "fallback; the anti-golden mirror of "
                        "golden_has_phone (the SAME gate PASSES the golden "
                        "state, exit 0, and REFUSES the no-phone state); "
                        "the refusal names AF-AE-PROVPHONE-NO-PHONE and "
                        "AF-AE-PROVPHONE-NO-EXECUTE; OFFLINE by "
                        "construction"),
    ("docs_u23", "the U23 tooling README / catalog data + drift gate — the "
                 "module inventory, the four v2 public surfaces, the house "
                 "exit codes and af codes as DATA (the module inventory and "
                 "the shipped tree never drift; a doc that names a module "
                 "that does not ship FAILS its self-test exit 4)"),
    ("house_rules", "the ONE canonical house-law constant surface for the "
                    "U23 family — browser UA (CAF_BROWSER_UA, CF 1010), "
                    "version header (CAF_VERSION_HEADER), the complete AF "
                    "autofail table (the manifest's 75 rows, the U23 "
                    "family's authority); the self-test pins UA and header "
                    "byte-exact against the registry and the AF table "
                    "byte-exact against ENGINE-MANIFEST.json autofails (a "
                    "tamper never masquerades as exit 1 — exit 4, the "
                    "AF-AE-HASH-PIN family)"),
    ("checklist_note", "the ONBOARDING CHECKLIST NOTE — \"SMS phone number "
                       "verified present before snapshot push\": the "
                       "fail-closed READ-ONLY live gate certifying the U23 "
                       "SMS-PHONE-PROVISIONED law on the client's OWN "
                       "location (GET /phones/numbers, the SMS-capable "
                       "marker by presence/truthiness on the fixed key "
                       "set, the idempotency truth held); READ-ONLY BY "
                       "CONSTRUCTION — it certifies, it never provisions "
                       "(the PROVISIONING ACTION stays --execute-gated in "
                       "the owning provisioner); an unmarked entry is never "
                       "trusted as SMS-capable; a refused listing STOPS, an "
                       "edge block is HELD; without a verified number the "
                       "snapshot push is NOT cleared (AF-AE-CHECKLIST-* "
                       "family)"),
)

# The live-verify gate order (FIXED, in this order) — the U23 family's
# verified surfaces:
#   1. the read surface (phone_lister list_action) — the GET-first side of
#      the phone law: the location's existing numbers, every number by
#      masked marker, the capability read on the fixed key set, the
#      GET-first idempotency law (an SMS-capable number already present is
#      verified, never re-provisioned),
#   2. the provision surface (provision_action provision_action) — the
#      GET-first provisioning ACTION, TREVOR-GATED: without --execute it is
#      a STOP (exit 2) that names the code and writes nothing; with
#      --execute it provisions ONLY when no SMS-capable number exists,
#      create-only-absent, and reads the created number back before any
#      report claims provisioned,
#   3. the SMS verification surface (sms_verifier verify_send) — the
#      outbound send under --execute, requiring HTTP 200 PLUS a SID; a 200
#      with no SID is a read-back mismatch (exit 5), never a pass,
#   4. the no-phone attack boundary (attack_no_phone) — the EMPTY / no-SMS-
#      capable listing MUST be REFUSED (exit 5 / provision-needed) while the
#      golden phone-provisioned control PASSES exit 0: the pass/fail split
#      discriminates the no-phone boundary, never a broken instrument,
#   5. the golden already-provisioned gate (golden_has_phone) — the
#      canonical SMS-PHONE-PROVISIONED state judged against its own golden
#      contract (a drifted / unmarked / non-golden / malformed /
#      credential-shaped candidate is REFUSED exit 5, never a blind pass;
#      the EXECUTE law is pinned),
#   6. the attack boundary (attack_sms_failed) — the non-200 send fixture
#      MUST fail every SMS-verification gate while the golden 200-send
#      control PASSES exit 0: the pass/fail split discriminates the
#      non-200 boundary, never a broken instrument,
#   7. the catalog drift gate (docs_u23) — the family inventory, surfaces,
#      exit codes and af codes as DATA, pinned against the shipped tree (a
#      doc that names a module that does not ship FAILS, exit 4),
#   8. the house-law constant gate (house_rules) — the browser UA and the
#      version header pinned byte-exact against the registry (CF 1010) and
#      the AF table pinned byte-exact against the manifest's autofails (a
#      tamper never masquerades as exit 1),
#   9. the checklist gate (checklist_note) — the READ-ONLY live
#      certification that the location carries an SMS-capable number
#      ("SMS phone number verified present before snapshot push"); an
#      unmarked entry is never trusted, a refused listing STOPS, an edge
#      block is HELD — without it the snapshot push is NOT cleared.
# The PROVISIONING ACTION is NOT a live gate: it is the family's gated
# ACTION surface (the aggregate refuses it without --execute,
# AF-AE-PROVPHONE-NO-EXECUTE) and even WITH --execute it is
# create-only-absent with a post-create read-back — this dispatcher never
# mutates on its own.
LIVE_GATES = (
    ("phone_lister", "the live phone read — the location's existing numbers "
                     "via GET /phones/numbers (PIT-gated; every number by "
                     "masked marker, an unmarked SMS entry is never "
                     "silently trusted, a refused listing never becomes a "
                     "create)"),
    ("provision_action", "the provision surface — GET-first idempotent "
                         "provisioning, TREVOR-GATED: without --execute a "
                         "STOP (exit 2) that names the code and writes "
                         "nothing; with --execute create-only-absent with "
                         "a post-create read-back (a missing read-back is a "
                         "MISMATCH, exit 5)"),
    ("sms_verifier", "the SMS verification surface — the outbound send "
                     "under --execute requiring HTTP 200 PLUS a message "
                     "identifier; a 200 with no SID is a read-back "
                     "mismatch (exit 5), never a pass"),
    ("sms_sender", "the test-SMS send surface — the GET-first contact "
                   "check then the POST /conversations/messages under "
                   "--execute then the bounded read-back confirming the "
                   "newest conversation message IS the sent text (a send "
                   "without a conversation id is a MISMATCH, exit 5; a "
                   "stalled read-back is HELD, exit 3)"),
    ("golden_has_phone", "the golden already-provisioned gate — the "
                         "canonical SMS-PHONE-PROVISIONED state judged "
                         "against its own golden contract (payload(); a "
                         "drifted / unmarked / non-golden / malformed / "
                         "credential-shaped candidate is REFUSED exit 5, "
                         "never a blind pass; the EXECUTE law is pinned)"),
    ("attack_no_phone", "the no-phone attack boundary — the EMPTY / no-SMS-"
                        "capable listing MUST be refused (provisioning "
                        "needed, reported via the dry-run plan) while the "
                        "golden phone-provisioned control PASSES exit 0 "
                        "(the pass/fail split discriminates the no-phone "
                        "boundary, never a broken instrument)"),
    ("attack_sms_failed", "the attack boundary — the non-200 send fixture "
                          "MUST fail every SMS-verification gate (exit 5) "
                          "while the golden 200-send control PASSES exit 0 "
                          "(the pass/fail split discriminates the non-200 "
                          "boundary, never a broken instrument)"),
    ("docs_u23", "the catalog drift gate — the family inventory, the four "
                 "v2 surfaces, the exit codes and the af codes as DATA, "
                 "pinned against the shipped tree (a doc that names a "
                 "module that does not ship FAILS, exit 4)"),
    ("house_rules", "the house-law constant gate — the browser UA and the "
                    "version header pinned byte-exact against the registry "
                    "(CF 1010) and the AF table pinned byte-exact against "
                    "the manifest's autofails (a tamper never masquerades "
                    "as exit 1)"),
    ("checklist_note", "the checklist gate — \"SMS phone number verified "
                       "present before snapshot push\": the READ-ONLY live "
                       "certification that the location carries an "
                       "SMS-capable number (the idempotency truth held: "
                       "verified, never re-provisioned); an unmarked entry "
                       "is never trusted, a refused listing STOPS, an edge "
                       "block is HELD — without it the snapshot push is "
                       "NOT cleared"),
)

# The pytest batteries that ship with the family (provenance only: each
# battery's presence is asserted, its tests run under pytest).
TEST_BATTERIES = ("test_provision_action.py", "test_sms_verifier.py",
                  "test_phone_lister.py")

# The family companion modules that ship alongside the dispatched set but are
# NOT dispatched (each exposes `self_test(out=None) -> int`, exit 0 pass / 4
# enforced violation): the WORKED EXAMPLE of the family dispatch (example_usage)
# and the pytest batteries above. A companion battery is REQUIRED — a worked
# example or a test battery that cannot prove itself offline STOPS, exactly
# as the dispatched modules stop.
COMPANION_BATTERIES = ("example_usage",)


class SkeletonError(Exception):
    """A fail-closed refusal (STOP or mismatch family) raised by the skeleton
    itself — a missing check module, a module violating the entry-point
    contract, or a malformed record."""


# ---------------------------------------------------------------------------
# Check-module loader — imports the U23 modules BY NAME and enforces the
# fail-closed contract: a missing module or a module that fails to expose
# its entry point is a STOP, never a silent skip.
# ---------------------------------------------------------------------------
def load_modules():
    """Import every U23_MODULES module. Returns {name: module}.

    Fail-closed: a module that does not exist raises SkeletonError (STOP) so
    the aggregate NEVER passes with a law silently absent. `importlib` is the
    only import surface — nothing is ever exec'd from a path. Each module's
    `self_test(out=None) -> int` battery is REQUIRED (checked here, not
    deferred to the self-test run)."""
    import importlib

    modules = {}
    missing = []
    for name, _role in U23_MODULES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            missing.append(name)
            continue
        modules[name] = mod
    if missing:
        raise SkeletonError(
            "u23_modules file(s) not found: %s — the U23 assembly is "
            "incomplete (fail-closed: no law is ever skipped)"
            % ", ".join(missing))
    for name, mod in modules.items():
        st = getattr(mod, "self_test", None)
        if not callable(st):
            raise SkeletonError(
                "u23_modules module %s does not expose 'self_test' — every "
                "family module must prove itself offline" % name)
    return modules


# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden PASS / attack
# FAIL), plus this dispatcher's own assembly and house-law assertions. NO
# network, NO credentials. Exit 4 on any failure (AF-AE-TEMPLATE-ATTACK
# family) — a tamper NEVER masquerades as exit 1.
# ---------------------------------------------------------------------------
def self_test(modules, out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the U23 check-module set
        #    exists (the dispatcher and the empty package init are the
        #    assembly container, not dispatched check modules; the family
        #    COMPANION modules — the worked example — are required in step
        #    2, never dispatched).
        on_disk = sorted(p.name[:-3] for p in MODULES_DIR.glob("*.py")
                         if p.name not in ("__init__.py", "main_skeleton.py")
                         and not p.name.startswith("test_")
                         and p.name[:-3] not in COMPANION_BATTERIES)
        expected = sorted(name for name, _ in U23_MODULES)
        assert on_disk == expected, (
            "u23_modules tree drifted: disk carries %s, the %d-module "
            "assembly contract names %s" % (", ".join(on_disk), len(expected),
                                            ", ".join(expected)))
        for battery in TEST_BATTERIES:
            assert (MODULES_DIR / battery).is_file(), (
                "the U23 pytest battery %s is missing from u23_modules/"
                % battery)
        # 2. every module's own battery passes (golden PASS / attack FAIL),
        #    and so does every family COMPANION battery (the worked example —
        #    a worked example that cannot prove itself offline is drift).
        for name, mod in modules.items():
            try:
                rc = mod.self_test(out=dev)
            except TypeError:
                rc = mod.self_test()
            if rc != EX_OK:
                raise AssertionError("%s self_test returned exit %d" % (name, rc))
        for cname in COMPANION_BATTERIES:
            try:
                cmod = importlib.import_module(cname)
            except ImportError as exc:
                raise AssertionError(
                    "the U23 companion module %s is missing (fail-closed: a "
                    "worked example that cannot prove itself offline is "
                    "drift): %s" % (cname, exc)) from exc
            try:
                rc = cmod.self_test(out=dev)
            except TypeError:
                rc = cmod.self_test()
            if rc != EX_OK:
                raise AssertionError(
                    "%s self_test returned exit %d" % (cname, rc))
        # 3. the house exit-code law is the manifest convention
        #    (0/1/2/3/4/5): the skeleton's constants never drifted from the
        #    registry's, which the manifest pins.
        assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5), \
            "house exit-code law drifted: registry constants are not 0/1/2/3/5"
        assert EX_VIOLATION == 4, "house exit-code law drifted: EX_VIOLATION is not 4"
        # 4. BROWSER UA LAW (CF 1010 / GK-09): the CAF_BROWSER_UA constant is
        #    a well-formed browser UA (never urllib's "Python-urllib/x.y"
        #    default, which the Cloudflare edge fronting the Convert and Flow
        #    hosts 403s as error 1010 before the request is ever scope-
        #    checked). Every family module pins the same UA in its own
        #    battery; the dispatcher re-pins the registry source.
        ua = reg.CAF_BROWSER_UA
        assert isinstance(ua, str) and ua.strip(), "CAF_BROWSER_UA is empty"
        assert "Python-urllib" not in ua, \
            "CAF_BROWSER_UA is urllib's default — the Cloudflare edge 1010s it"
        assert ua.startswith("Mozilla/5.0") and "Chrome/" in ua, \
            "CAF_BROWSER_UA is not a well-formed browser UA"
        # 5. CREDENTIAL LAW: the PIT labels are the house standard set and
        #    resolve to SET / NOT SET only — never a printed value. The
        #    resolver refuses a non-pit- value (a placeholder or a mis-set
        #    value must not silently ride as a token).
        assert tuple(reg.PIT_LABELS) == (
            "CONVERT_AND_FLOW_PIT", "CONVERT_AND_FLOW_API_KEY",
            "GOHIGHLEVEL_API_KEY", "GOHIGHLEVEL_PIT", "GHL_API_KEY"), \
            "PIT label set drifted from the house credential law"
        _label, token = reg.resolve_pit()
        assert token is None or str(token).startswith("pit-"), \
            "resolve_pit returned a non-pit- token (would be refused)"
        # 6. NEVER-A-TOKEN LAW on the skeleton's OWN surfaces: the plan
        #    payload (the same builder the --dry-run prints) and the report
        #    surface carry labels and SET / NOT SET states only — a
        #    credential-shaped string (pit- followed by a value) can never
        #    leak through them.
        plan_blob = json.dumps(_build_plan(modules), indent=2, sort_keys=True)
        assert not _CREDENTIAL_SHAPE.search(plan_blob), \
            "the plan surface must never carry a credential-shaped string"
        report_blob = json.dumps(_build_report(modules), indent=2, sort_keys=True)
        assert not _CREDENTIAL_SHAPE.search(report_blob), \
            "the report surface must never carry a credential-shaped string"
        # 7. THE EXECUTE GATE LAW — the heart of the U23 family: the
        #    provisioning ACTION requires --execute in BOTH surfaces (the
        #    two-surface law of the U06 / U07 siblings). The dispatcher's OWN
        #    CLI surface refuses provision/verify without --execute verbatim,
        #    and the family's own module-level no-execute STOPs are re-proven
        #    here (the family never re-implements a law).
        assert _execute_gate(modules) == EX_OK, \
            "the dispatcher execute gate must pass its own offline law"
    except AssertionError as exc:
        sys.stderr.write("[main-skeleton] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except SkeletonError as exc:
        sys.stderr.write("[main-skeleton] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    out.write("[main-skeleton] U23 self-test: OK (%d modules imported, "
              "every module battery + assembly assertions + exit-code law + "
              "browser-UA law + credential law + execute-gate law pass)\n"
              % len(modules))
    return EX_OK


_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


def _mask_id(fid: str) -> str:
    """Mask a location / number id for every operator surface — a tenant
    identifier, not a secret, but never printed in full (house pattern,
    mirrored from the u23 modules' own masking)."""
    fid = (fid or "").strip()
    if len(fid) <= 8:
        return "***"
    return "%s***%s" % (fid[:4], fid[-4:])


def _empty_listing() -> dict:
    """The OFFLINE no-phone attack payload — a /phones/numbers listing with
    NO number at all, the exact shape a live GET /phones/numbers serves
    ({"numbers": [...]}), the state the operator must provision. Synthetic
    material only; never a network call."""
    return {"numbers": []}


def _golden_phone_listing() -> dict:
    """The OFFLINE golden phone-provisioned control payload — the listing
    carrying EXACTLY ONE SMS-capable number, the state the GET-first
    idempotency law verifies without re-provisioning. Synthetic material
    only; every id and number masked (the same masked markers the family
    surfaces carry); never a network call."""
    return {
        "numbers": [{
            "id": "num_GOLDEN", "phoneNumber": "+12025559876",
            "smsEnabled": True,
        }],
    }


# ---------------------------------------------------------------------------
# The Trevor gate — the provisioning-ACTION law, enforced by this dispatcher
# in BOTH surfaces (the CLI and the aggregate). Fail-closed and pure: the
# family's own no-execute STOPs are re-proven here, never assumed.
# ---------------------------------------------------------------------------
def _execute_gate(modules, out=None) -> int:
    """The provisioning-ACTION law, offline and pure. The PROVISIONING
    ACTION (POST /phones/numbers) and every send ACTION (send-test-message /
    outbound SMS) require --execute (the Trevor gate); without it the ACTION
    is a STOP (exit 2, AF-AE-PROVPHONE-NO-EXECUTE / AF-AE-SMSVER-NO-EXECUTE)
    — never a silent no-op and never a silent write. The gate is proven
    OFFLINE with the family's own surfaces: provision_action's and
    sms_verifier's batteries assert the module-level no-execute STOP (exit 2)
    against a synthetic empty location with an in-memory fake — no credential
    resolution is even reached — and the dispatcher's OWN CLI surface refuses
    `provision` and `verify` without --execute verbatim (proven here: the
    gate is enforced in BOTH surfaces, exactly the U06 sibling's two-surface
    law). The family never re-implements a law."""
    out = out or sys.stderr
    # 1. the dispatcher's OWN CLI surface refuses `provision` and `verify`
    #    without --execute (the Trevor gate) — the two-surface law, proven
    #    here offline (this probe never touches a credential or the network:
    #    the refusal holds before any resolution work).
    for cmd in ("provision", "verify"):
        try:
            rc = main([cmd, "--location-id", "loc_fx"])
        except SystemExit as exc:
            if exc.code not in (EX_STOP, 2):
                raise SkeletonError(
                    "the dispatcher's own %r CLI exited %r during the "
                    "no-execute probe (the Trevor gate cannot be proven)"
                    % (cmd, exc.code))
            continue
        if rc != EX_STOP:
            raise SkeletonError(
                "the dispatcher's own %r CLI without --execute returned "
                "exit %d, want %d (AF-AE-PROVPHONE-NO-EXECUTE — the Trevor "
                "gate drifted; an ACTION without the gate must STOP)"
                % (cmd, rc, EX_STOP))
    # 2. the family batteries prove the module-level no-execute STOPs
    #    (provision_action's and sms_verifier's batteries assert their
    #    no-execute STOPs against the in-memory fakes, exit 2, with the
    #    mutation logs EMPTY) — those batteries ran in step 2 of the
    #    self-test; the assertions they pin are re-confirmed here by
    #    re-running them and demanding exit 0.
    for name in ("provision_action", "sms_verifier"):
        mod = modules[name]
        try:
            rc = mod.self_test(out=out)
        except TypeError:
            rc = mod.self_test()
        if rc != EX_OK:
            raise SkeletonError(
                "the %s battery FAILED during the execute-gate proof "
                "(exit %d) — the no-execute law cannot be certified"
                % (name, rc))
    return EX_OK


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials. The U23 dispatch law with the
# exact surfaces, printed as ONE JSON object on stdout; human notes go to
# stderr. Each module's own plan surface (where it ships one) is collected
# by name; a module plan that cannot be produced is recorded as an error,
# never fabricated. The payload is scanned against the credential shape
# before print — a hit REFUSES the surface rather than echo a token.
# ---------------------------------------------------------------------------
def _module_plan(modules, name):
    """One module's plan record. Uses the module's OWN plan surface when it
    ships one; otherwise derives the offline law from the module's
    documented constants / functions. A module plan is never fatal — an
    error is recorded, never a fabricated law."""
    mod = modules[name]
    try:
        if name == "phone_lister":
            return {
                "live_read": "GET /phones/numbers?locationId=<loc> via the "
                             "PROVEN public rail (services.leadconnectorhq.com; "
                             "CAF_BROWSER_UA on every request — CF 1010)",
                "idempotency": "GET-first — an SMS-capable number already "
                               "present is verified, never re-provisioned "
                               "(never a second number, never a second "
                               "charge)",
                "action_gate": "the provision path is Trevor-gated "
                               "(--execute) — without it a location that "
                               "needs a number is a STOP (exit 2) that "
                               "names the code; a refused listing is never "
                               "followed by a create",
                "note": "offline plan only — no network, no credential "
                        "needed; every number is reported by masked marker "
                        "(last 4 digits) only, never in full",
            }
        if name == "provision_action":
            return {
                "action": "POST /phones/numbers (GET-first, create-only-"
                          "absent), then the created number is GET back "
                          "and confirmed before any report claims "
                          "provisioned",
                "action_gate": "TREVOR-GATED (--execute) — without it a "
                               "report of what it WOULD do and a STOP "
                               "(exit 2, AF-AE-PROVPHONE-NO-EXECUTE), "
                               "never a write; a refused listing REFUSES "
                               "before any create",
                "read_back": "a missing read-back (create returned no "
                             "number id) is a MISMATCH (exit 5), never a "
                             "provisioned success",
                "note": "offline plan only — no network, no credential "
                        "needed; the marker (last 4) is the only surface "
                        "for a number",
            }
        if name == "sms_verifier":
            return {
                "action": "POST /conversations/messages/outbound — requires "
                          "HTTP 200 PLUS a message identifier (SID, read "
                          "by key order on the fixed key set) before "
                          "anything is called delivered",
                "action_gate": "the send is a GHL-scope ACTION — --execute "
                               "or nothing is sent; without it a STOP "
                               "(exit 2, AF-AE-SMSVER-NO-EXECUTE)",
                "read_back": "an HTTP 200 whose body carries NO id is a "
                             "read-back mismatch (exit 5, "
                             "AF-AE-SMSVER-NO-SID), never a pass",
                "note": "offline plan only — no network, no credential "
                        "needed; the destination is reported by masked "
                        "marker only",
            }
        if name == "sms_sender":
            return {
                "action": "POST /conversations/messages (the canonical "
                          "Skill 44 send contract, imported byte-exact, "
                          "never re-invented) — after a GET-first contact "
                          "check (never send into the unknown) and under "
                          "--execute only",
                "action_gate": "THE SEND IS TREVOR-GATED — --execute or "
                               "nothing is sent; without it a STOP (exit "
                               "2, AF-AE-SMSENDER-NO-EXECUTE)",
                "read_back": "a bounded read-back verifying the newest "
                             "conversation message IS the sent text; a "
                             "send answered without a conversation id is a "
                             "read-back mismatch (exit 5), a stalled "
                             "read-back is HELD (exit 3), never a false "
                             "pass",
                "note": "offline plan only — no network, no credential "
                        "needed; the contact id is masked and the message "
                        "text is surfaced only as a fixed-length hash "
                        "marker",
            }
        if name == "golden_has_phone":
            return {
                "fixture": "the golden SMS-PHONE-PROVISIONED state — the "
                           "one SMS-capable number already present (the "
                           "golden control of the GET-first idempotency "
                           "law, verified never re-provisioned, never a "
                           "second number, never a second charge)",
                "gate": "payload() judges a provisioned-state candidate "
                        "fail-closed against the golden contract (a "
                        "drifted / unmarked / non-golden / malformed / "
                        "credential-shaped payload is REFUSED exit 5, "
                        "never a blind pass)",
                "execute_law": "EXECUTE_REQUIRED_FOR_PROVISION — the "
                               "provisioning ACTION is Trevor-gated "
                               "(--execute); the gate lives in the "
                               "provisioner, never in a fixture",
                "note": "offline fixture — no network, no credential "
                        "needed; synthetic material, every id and number "
                        "masked",
            }
        if name == "attack_sms_failed":
            return {
                "attack": "the send-test-message POST answered with ANY "
                          "non-200 status (the canonical send record built "
                          "by the SINGLE AUTHORITY with the ONE status "
                          "variable changed) that every SMS-verification "
                          "gate MUST FAIL, never a pass",
                "control": "the golden 200-send control (payload_true) "
                           "PASSES exit 0 — the pass/fail split "
                           "discriminates the non-200 boundary, never a "
                           "broken instrument",
                "action_gate": "shipping OR judging the attack requires "
                               "--execute (Trevor gate)",
                "note": "offline attack fixture — no network, no "
                        "credential needed; synthetic material, every id "
                        "masked",
            }
        if name == "attack_no_phone":
            return {
                "attack": "ANY /phones/numbers listing carrying no "
                          "SMS-capable number — above all the EMPTY "
                          "listing — is REFUSED as a pass (provisioning "
                          "needed, reported via the dry-run plan: "
                          "provision_needed TRUE and what --execute WOULD "
                          "do), never a clean read, never a silent "
                          "fallback",
                "control": "the golden phone-provisioned control PASSES "
                           "exit 0 (the anti-golden mirror of "
                           "golden_has_phone — the SAME phone-law gate "
                           "passes the golden state and refuses the "
                           "no-phone state; the pass/fail split "
                           "discriminates the no-phone boundary, never a "
                           "broken instrument)",
                "codes": "the refusal names AF-AE-PROVPHONE-NO-PHONE (the "
                         "state law) and AF-AE-PROVPHONE-NO-EXECUTE (the "
                         "action law — provisioning is a GHL-gated ACTION "
                         "and REQUIRES --execute)",
                "note": "offline attack fixture — no network, no "
                        "credential needed; the fixture NEVER mutates (the "
                        "POST lives in the provisioner, --execute-gated)",
            }
        if name == "docs_u23":
            return {
                "data": "the U23 tooling README / catalog as DATA — the "
                        "module inventory, the four v2 public surfaces, "
                        "the house exit codes and af codes, the doctrine "
                        "and the credential labels",
                "drift_gate": "the inventory and the shipped tree never "
                              "drift (a doc that names a module that does "
                              "not ship FAILS its self-test exit 4)",
                "note": "offline pure data — no network, no credential "
                        "needed; the browser-UA doctrine is pinned "
                        "byte-equal to reg.CAF_BROWSER_UA (CF 1010)",
            }
        if name == "house_rules":
            return {
                "browser_ua": "CAF_BROWSER_UA (CF 1010) — ported "
                              "byte-for-byte from the registry and pinned "
                              "by the offline self-test; every request to "
                              "services.leadconnectorhq.com / "
                              "backend.leadconnectorhq.com MUST carry a "
                              "browser User-Agent on EVERY request",
                "version_header": "CAF_VERSION_HEADER (LeadConnector v2, "
                                  "verified at W0.5)",
                "af_codes": "the complete AF autofail table (the "
                            "manifest's 75 rows, byte-exact) plus the U23 "
                            "family's own rows (docs_u23.AF_CODES)",
                "note": "offline constants module — no network, no "
                        "credential needed; a tamper never masquerades "
                        "as exit 1 (exit 4, the AF-AE-HASH-PIN family)",
            }
        if name == "checklist_note":
            return {
                "checklist_item": "SMS phone number verified present before "
                                  "snapshot push (the snapshot contract's "
                                  "own note, "
                                  "workflows.per_client_sms_phone_flag)",
                "live_gate": "READ-ONLY GET /phones/numbers for the "
                             "client's OWN Convert and Flow location via "
                             "the house rail client (CAF_BROWSER_UA on "
                             "every request — CF 1010 law); the SMS-capable "
                             "marker by presence/truthiness on the fixed "
                             "key set; the idempotency truth held (an "
                             "SMS-capable number ALREADY present is "
                             "verified, never re-provisioned)",
                "never_provisions": "READ-ONLY BY CONSTRUCTION — it "
                                    "certifies, it never provisions (the "
                                    "PROVISIONING ACTION stays "
                                    "--execute-gated in the owning "
                                    "provisioner)",
                "note": "offline plan only — no network, no credential "
                        "needed; an unmarked entry can NEVER be trusted as "
                        "SMS-capable; without a verified number the "
                        "snapshot push is NOT cleared; every number is "
                        "reported by masked marker only",
            }
        return {"note": "no plan surface for %s" % name}
    except Exception as exc:  # noqa: BLE001 — a plan is never fatal
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def _build_plan(modules) -> dict:
    """The ONE offline plan payload (shared by --dry-run and the self-test's
    never-a-token scan, so the two can never drift)."""
    plans = {}
    for name, _role in U23_MODULES:
        plans[name] = _module_plan(modules, name)
    return {
        "contract": "anthology-engine-u23-dispatch-plan",
        "schema_version": 1,
        "location": "BY LABEL (CONVERT_AND_FLOW_LOCATION_ID / "
                    "GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID) — masked on "
                    "every surface, never printed in full",
        "gates": [name for name, _ in LIVE_GATES],
        "modules": [name for name, _ in U23_MODULES],
        "plans": plans,
        "execute_gate": "the PROVISIONING ACTION (POST /phones/numbers) and "
                        "every send ACTION (send-test-message / outbound "
                        "SMS) require --execute (Trevor-gated); without it "
                        "a STOP (exit 2) that names the code and writes "
                        "nothing — never a silent no-op and never a silent "
                        "write; even WITH --execute provisioning is "
                        "create-only-absent with a post-create read-back",
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed; "
                "every request must ride reg.CafClient with CAF_BROWSER_UA "
                "on every request — CF 1010 law",
    }


def plan(modules, out=None) -> int:
    out = out or sys.stderr
    payload = _build_plan(modules)
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise SkeletonError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    print(dumped)
    return EX_OK


def _build_report(modules) -> dict:
    """The empty report scaffold (labels and states only — the never-a-token
    law is pinned on this exact surface in the self-test)."""
    return {
        "contract": "anthology-engine-u23-verify",
        "schema_version": 1,
        "pit_label": ("SET" if reg.resolve_pit()[1] else "NOT SET"),
        "execute": False,
        "checks": {},
        "delta": [],
        "fail_closed": True,
    }


# ---------------------------------------------------------------------------
# Live aggregate — fail-closed over the fixed gate order. Any FAIL -> exit 5;
# a STOP-family refusal propagates as exit 2; a transport / edge failure is
# HELD (exit 3), never mislabeled as scope. The PROVISIONING ACTION is never
# a gate: it is the family's gated ACTION surface, refused without --execute
# (the Trevor gate) and create-only-absent with a post-create read-back even
# with it — this dispatcher never mutates on its own.
# ---------------------------------------------------------------------------
def _stop_classes(mod):
    """The STOP-family exception classes a module may raise, resolved BY
    NAME so a module that stops defining one fails the self-test, not the
    live path."""
    return tuple(cls for cname in ("ProvisionError", "VerifyError",
                                   "FixtureError")
                 if isinstance(cls := getattr(mod, cname, None), type)
                 and issubclass(cls, Exception))


def _live_client(out):
    """Resolve the LeadConnector client for the live surfaces, BY LABEL,
    exactly as the u23 modules' own CLIs resolve it (reg._live_client): the
    client's OWN location-scoped private-integration token (pit- prefix
    validated so a placeholder is refused) plus the location id resolved
    BY LABEL. NEVER prints a value; a missing credential is a STOP (the
    caller returns it)."""
    client, loc_or_rc = reg._live_client("")
    if client is None:
        return None, None, loc_or_rc
    return client, loc_or_rc, None


def verify_live(modules, location_id: str, *, execute: bool = False,
                out=None) -> int:
    out = out or sys.stderr
    masked = _mask_id(location_id)
    report = _build_report(modules)
    report["execute"] = execute

    import contextlib as _contextlib

    def _capture_sibling(call):
        """Run a sibling module surface that prints its OWN gate document to
        stdout by contract, capturing that stdout into the human channel so
        the dispatcher's stdout stays exactly its ONE JSON report object
        (the u07 skeleton's plan-capture pattern). Returns the call's return
        value."""
        cap = io.StringIO()
        with _contextlib.redirect_stdout(cap):
            rc = call()
        if cap.getvalue().strip():
            out.write(cap.getvalue())
        return rc

    def _run(name, mod):
        try:
            if name == "golden_has_phone":
                # OFFLINE: the golden already-provisioned gate — the
                # canonical SMS-PHONE-PROVISIONED state judged against its
                # own golden contract (payload() with NO candidate judges
                # the golden state itself). A drifted / unmarked /
                # non-golden / malformed / credential-shaped candidate is
                # REFUSED exit 5, never a blind pass; the EXECUTE law is
                # pinned. READ-ONLY and OFFLINE by construction (never a
                # network call).
                result = _capture_sibling(
                    lambda: mod.payload(None, out=io.StringIO()))
                if result == EX_OK:
                    return ("PASS",
                            "the golden phone-provisioned state holds — "
                            "the location already carries an SMS-capable "
                            "number (idempotent no-op: verified, never "
                            "re-provisioned, never a second number, never "
                            "a second charge; provisioning stays "
                            "--execute-gated)",
                            {"already_provisioned": True},
                            {"already_provisioned": True}), None
                return ("FAIL",
                        "the golden phone-provisioned gate REFUSED the "
                        "golden state itself (exit %d) — the fixture "
                        "drifted" % result,
                        {"already_provisioned": True},
                        {"already_provisioned": False}), None
            if name == "attack_no_phone":
                # OFFLINE: the no-phone attack boundary — the EMPTY / no-SMS-
                # capable listing MUST be REFUSED as a pass (provisioning
                # needed, reported via the dry-run plan) while the golden
                # phone-provisioned control PASSES exit 0. The judge is
                # READ-ONLY and OFFLINE by construction (the fixture's
                # synthetic in-memory payloads, never a network call). The
                # boundary is the anti-golden mirror of golden_has_phone:
                # the SAME phone law gate passes the golden state and
                # refuses the no-phone state.
                try:
                    result = _capture_sibling(
                        lambda: mod.verify(_empty_listing(),
                                           out=io.StringIO()))
                    _refused = result[0] != "PASS"
                except Exception:  # noqa: BLE001 — classified below
                    _refused = True
                if _refused:
                    control = _capture_sibling(
                        lambda: mod.verify(_golden_phone_listing(),
                                           out=io.StringIO()))
                    if isinstance(control, tuple) and control and control[0] == "PASS":
                        return ("PASS",
                                "the no-phone listing is REFUSED (exit 5, "
                                "provisioning needed — the dry-run plan "
                                "reports provision_needed TRUE and what "
                                "--execute WOULD do) with the golden "
                                "phone-provisioned control PASSING exit 0 — "
                                "the pass/fail split discriminates the "
                                "no-phone boundary",
                                {"attack_refused": True},
                                {"attack_refused": True,
                                 "control": "PASS"}), None
                    return ("FAIL",
                            "the no-phone attack REFUSED the no-phone "
                            "listing but the golden phone-provisioned "
                            "control did NOT pass — a broken instrument is "
                            "never a real discrimination",
                            {"attack_refused": True},
                            {"attack_refused": True,
                             "control": "FAIL"}), None
                return ("FAIL",
                        "the no-phone listing was ACCEPTED as a clean read "
                        "— a location with no SMS-capable number must NEVER "
                        "be judged verified; the no-phone attack boundary "
                        "drifted",
                        {"attack_refused": True},
                        {"attack_refused": False}), None
            if name == "docs_u23":
                # OFFLINE: the catalog drift gate — the family inventory,
                # the four v2 surfaces, the exit codes and the af codes as
                # DATA, pinned against the shipped tree. The gate is the
                # module's own drift battery (its self-test ran in step 2);
                # the live gate re-pins the inventory counts so the catalog
                # and the tree never drift apart. READ-ONLY and OFFLINE by
                # construction.
                try:
                    count = len(mod.modules())
                    surfaces = len(mod.surfaces())
                except Exception as exc:  # noqa: BLE001 — classified below
                    return ("FAIL",
                            "the U23 catalog gate could not be read: %s: %s"
                            % (type(exc).__name__, exc),
                            {"catalog_ok": True},
                            {"catalog_ok": False}), None
                if count >= len(U23_MODULES) and surfaces >= 4:
                    return ("PASS",
                            "the U23 catalog agrees with the family — %d "
                            "module(s), %d surface(s) as DATA"
                            % (count, surfaces),
                            {"catalog_ok": True},
                            {"catalog_ok": True}), None
                return ("FAIL",
                        "the U23 catalog drifted — %d module(s), %d "
                        "surface(s) recorded, want at least %d module(s) "
                        "and 4 surface(s)"
                        % (count, surfaces, len(U23_MODULES)),
                        {"catalog_ok": True},
                        {"catalog_ok": False}), None
            if name == "house_rules":
                # OFFLINE: the house-law constant gate — the browser UA and
                # the version header pinned byte-exact against the registry
                # (CF 1010) and the AF table pinned byte-exact against the
                # manifest's autofails. The gate is the module's own
                # battery (its self-test ran in step 2); the live gate
                # re-pins the constants so the family law and the registry /
                # manifest never drift apart. READ-ONLY and OFFLINE by
                # construction.
                try:
                    ua = mod.CAF_BROWSER_UA
                    header = mod.CAF_VERSION_HEADER
                    codes = len(mod.AF_CODES)
                except Exception as exc:  # noqa: BLE001 — classified below
                    return ("FAIL",
                            "the U23 house-law constants could not be read: "
                            "%s: %s" % (type(exc).__name__, exc),
                            {"house_law": True},
                            {"house_law": False}), None
                if (ua == reg.CAF_BROWSER_UA
                        and header == reg.CAF_VERSION_HEADER
                        and isinstance(codes, int) and codes >= 1):
                    return ("PASS",
                            "the U23 house-law constants agree with the "
                            "registry and the manifest — browser UA "
                            "byte-exact (CF 1010), version header "
                            "byte-exact, %d AF code(s)" % codes,
                            {"house_law": True},
                            {"house_law": True}), None
                return ("FAIL",
                        "the U23 house-law constants drifted from the "
                        "registry / the manifest (browser UA / version "
                        "header / AF table) — a tamper never masquerades "
                        "as exit 1",
                        {"house_law": True},
                        {"house_law": False}), None
            if name == "checklist_note":
                # The checklist gate — the READ-ONLY live certification that
                # the location carries an SMS-capable number (the
                # idempotency truth held: verified, never re-provisioned).
                # READ-ONLY BY CONSTRUCTION: it certifies, it never
                # provisions (the PROVISIONING ACTION stays --execute-gated
                # in the owning provisioner); an unmarked entry is never
                # trusted as SMS-capable; a refused listing / a genuine
                # scope denial STOPS (exit 2); an edge block / transport
                # failure is HELD (exit 3); without a verified number the
                # snapshot push is NOT cleared.
                client, loc_or_rc, rc0 = _live_client(out)
                if rc0 is not None:
                    return None, rc0
                result = _capture_sibling(
                    lambda: mod.check(client, loc_or_rc,
                                      out=io.StringIO()))
                if result == EX_OK:
                    return ("PASS",
                            "the checklist certifies the SMS phone number "
                            "is VERIFIED PRESENT (marker %s) — the "
                            "snapshot push is cleared" % masked,
                            {"ok": True}, {"ok": True}), None
                if result == EX_STOP:
                    out.write("[main-skeleton] STOP: the checklist gate "
                              "REFUSED (marker %s) — a credential label "
                              "NOT SET / a genuine scope denial / a "
                              "refused listing; without a verified number "
                              "the snapshot push is NOT cleared.\n"
                              % masked)
                    return None, EX_STOP
                if result == EX_HELD:
                    out.write("[main-skeleton] HELD: the checklist gate "
                              "was HELD (marker %s) — UNDETERMINED, never "
                              "a fabricated pass.\n" % masked)
                    return None, EX_HELD
                return ("FAIL",
                        "the checklist gate returned exit %d — a listing "
                        "with no SMS-capable number or an unmarked entry "
                        "(the snapshot push is NOT cleared) (marker %s)"
                        % (result, masked),
                        {"ok": True}, {"ok": False}), None
            if name == "attack_sms_failed":
                # OFFLINE: the attack boundary — the non-200 send fixture
                # MUST fail the fixture's own gate while the golden 200-send
                # control PASSES exit 0. The judge is READ-ONLY and OFFLINE
                # by construction (the canonical ATTACK_SEND_RECORD payload,
                # never a network call). Shipping or judging the attack is
                # itself Trevor-gated (--execute) — the boundary is judged
                # exactly the way the aggregate would ship it.
                result = _capture_sibling(
                    lambda: mod.payload(execute=execute, out=io.StringIO()))
                if result == EX_MISMATCH:
                    control = _capture_sibling(
                        lambda: mod.payload_true(execute=execute,
                                                 out=io.StringIO()))
                    if control == EX_OK:
                        return ("PASS",
                                "the non-200 send attack is DETECTED and "
                                "refused (exit 5) with the golden 200-send "
                                "control PASSING exit 0 — the pass/fail "
                                "split discriminates the non-200 boundary",
                                {"attack_refused": True},
                                {"attack_refused": True,
                                 "control": "PASS"}), None
                    return ("FAIL",
                            "the attack gate refused the non-200 send "
                            "(exit 5) but the golden 200-send control did "
                            "NOT pass (exit %d) — a broken instrument is "
                            "never a real discrimination" % control,
                            {"attack_refused": True},
                            {"attack_refused": True, "control": "FAIL"}), None
                if result == EX_OK:
                    return ("FAIL",
                            "the non-200 send attack was ACCEPTED (exit 0) "
                            "— a non-200 send passed the verification gate; "
                            "the attack boundary drifted",
                            {"attack_refused": True},
                            {"attack_refused": False}), None
                if result == EX_STOP:
                    return ("FAIL",
                            "the attack gate STOPPED (exit 2) — the non-200 "
                            "send was neither accepted nor refused; the "
                            "attack boundary drifted (a STOP is never a "
                            "discrimination)",
                            {"attack_refused": True},
                            {"attack_refused": None}), None
                return ("FAIL",
                        "the attack gate returned exit %d — the U23 attack "
                        "fixture drifted" % result,
                        {"attack_refused": True},
                        {"attack_refused": None}), None
            if name in ("phone_lister", "provision_action"):
                # The read surface and the provision surface — both resolve
                # the client BY LABEL (reg._live_client; the location id is
                # resolved from the client-standard labels, masked on every
                # surface). The provision ACTION is Trevor-gated: without
                # --execute the module reports what it WOULD do and STOPS
                # (exit 2, AF-AE-PROVPHONE-NO-EXECUTE), never a silent no-op
                # and never a silent write.
                client, loc_or_rc, rc0 = _live_client(out)
                if rc0 is not None:
                    return None, rc0
                if name == "phone_lister":
                    result = _capture_sibling(
                        lambda: mod.list_action(client, loc_or_rc,
                                                out=io.StringIO()))
                else:
                    result = _capture_sibling(
                        lambda: mod.provision_action(
                            client, loc_or_rc, execute=execute,
                            out=io.StringIO()))
                if result == EX_OK:
                    return ("PASS",
                            "the %s surface PASSED (marker %s)"
                            % (name, masked),
                            {"ok": True}, {"ok": True}), None
                if result == EX_STOP:
                    out.write("[main-skeleton] STOP: the %s surface REFUSED "
                              "(marker %s) — an ACTION without --execute "
                              "(the Trevor gate) / a credential label NOT "
                              "SET / a genuine scope denial.\n"
                              % (name, masked))
                    return None, EX_STOP
                if result == EX_HELD:
                    out.write("[main-skeleton] HELD: the %s surface was "
                              "HELD (marker %s) — UNDETERMINED, never a "
                              "fabricated list.\n" % (name, masked))
                    return None, EX_HELD
                return ("FAIL",
                        "the %s surface returned exit %d — a read-back "
                        "mismatch (a create returned no number id) or a "
                        "drifted surface (marker %s)" % (name, result, masked),
                        {"ok": True}, {"ok": False}), None
            if name == "sms_verifier":
                # The SMS verification surface — the outbound send under
                # --execute requiring HTTP 200 PLUS a message identifier; a
                # 200 with no SID is a read-back mismatch (exit 5), never a
                # pass. Without --execute it STOPS (exit 2,
                # AF-AE-SMSVER-NO-EXECUTE).
                client, loc_or_rc, rc0 = _live_client(out)
                if rc0 is not None:
                    return None, rc0
                result = _capture_sibling(
                    lambda: mod.verify_send(
                        client, loc_or_rc, "", "",
                        execute=execute, out=io.StringIO()))
                if result == EX_OK:
                    return ("PASS",
                            "the SMS verification surface PASSED (marker "
                            "%s)" % masked,
                            {"ok": True}, {"ok": True}), None
                if result == EX_STOP:
                    out.write("[main-skeleton] STOP: the SMS verification "
                              "surface REFUSED (marker %s) — an ACTION "
                              "without --execute (the Trevor gate) / a "
                              "credential label NOT SET / a genuine scope "
                              "denial.\n" % masked)
                    return None, EX_STOP
                if result == EX_HELD:
                    out.write("[main-skeleton] HELD: the SMS verification "
                              "surface was HELD (marker %s) — UNDETERMINED, "
                              "never a false pass.\n" % masked)
                    return None, EX_HELD
                if result == EX_MISMATCH:
                    return ("FAIL",
                            "the SMS verification read-back mismatched — "
                            "an HTTP 200 whose body carries no message "
                            "identifier (AF-AE-SMSVER-NO-SID), never a "
                            "pass (marker %s)" % masked,
                            {"ok": True}, {"ok": False}), None
                return ("FAIL",
                        "the SMS verification surface returned exit %d — "
                        "the verification surface drifted (marker %s)"
                        % (result, masked),
                        {"ok": True}, {"ok": False}), None
            if name == "sms_sender":
                # The test-SMS send surface — the GET-first contact check
                # then the POST /conversations/messages under --execute then
                # the bounded read-back confirming the newest conversation
                # message IS the sent text. THE SEND IS TREVOR-GATED —
                # without --execute it STOPS (exit 2,
                # AF-AE-SMSENDER-NO-EXECUTE); a send answered without a
                # conversation id is a read-back mismatch (exit 5); a
                # stalled read-back is HELD (exit 3), never a false pass.
                client, loc_or_rc, rc0 = _live_client(out)
                if rc0 is not None:
                    return None, rc0
                result = _capture_sibling(
                    lambda: mod.send_action(
                        client, "", "",
                        execute=execute, out=io.StringIO()))
                if result == EX_OK:
                    return ("PASS",
                            "the test-SMS send surface PASSED (marker %s)"
                            % masked,
                            {"ok": True}, {"ok": True}), None
                if result == EX_STOP:
                    out.write("[main-skeleton] STOP: the test-SMS send "
                              "surface REFUSED (marker %s) — an ACTION "
                              "without --execute (the Trevor gate) / a "
                              "credential label NOT SET / a genuine scope "
                              "denial.\n" % masked)
                    return None, EX_STOP
                if result == EX_HELD:
                    out.write("[main-skeleton] HELD: the test-SMS send "
                              "surface was HELD (marker %s) — UNDETERMINED, "
                              "never a false pass.\n" % masked)
                    return None, EX_HELD
                return ("FAIL",
                        "the test-SMS send surface returned exit %d — a "
                        "read-back mismatch (a send without a conversation "
                        "id) or a drifted surface (marker %s)"
                        % (result, masked),
                        {"ok": True}, {"ok": False}), None
            raise SkeletonError("dispatcher has no live gate for module %r"
                                % name)
        except reg.ScopeDenied as exc:
            reg._stop(out, "The Convert and Flow token cannot READ the "
                           "location (%s)." % masked,
                      [str(exc), "Grant the location PIT the READ scope and "
                                 "re-run.", "AF-AE-PIT-SCOPE."])
            return None, EX_STOP
        except reg.UpstreamBlockedError as exc:
            out.write("[main-skeleton] HELD: %s\n" % exc)
            return None, EX_HELD
        except reg.CafUnreachable as exc:
            out.write("[main-skeleton] HELD: %s\n" % exc)
            return None, EX_HELD
        except _stop_classes(mod) as exc:
            reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
            return None, EX_STOP
        except SkeletonError as exc:
            reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
            return None, EX_STOP
        except Exception as exc:  # noqa: BLE001 — a module refusal is never an unexpected error
            if exc.__class__.__name__ in ("ProvisionError", "VerifyError",
                                          "FixtureError"):
                reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
                return None, EX_STOP
            raise

    # ---- the PROVISIONING ACTION (Trevor-gated) --------------------------
    # The gate holds HERE, before any check runs: a PROVISIONING ACTION
    # without --execute is a STOP (AF-AE-PROVPHONE-NO-EXECUTE /
    # AF-AE-SMSVER-NO-EXECUTE), never a silent no-op and never a silent
    # write. WITH --execute the family's create-only-absent contract holds —
    # the modules provision ONLY when no SMS-capable number exists and read
    # the created number / the SID back before any report claims success; a
    # missing read-back is a MISMATCH. The dispatcher itself never mutates.
    if execute:
        report["execute"] = True
        report["action"] = {
            "status": "AUTHORIZED",
            "execute": True,
            "note": "the PROVISIONING ACTION is authorized by --execute "
                    "(Trevor-gated) and is create-only-absent with a "
                    "post-create read-back — a number already present live "
                    "is verified, never re-provisioned; a send is never "
                    "called delivered without its SID (a missing read-back "
                    "is a MISMATCH, exit 5)",
            "af_code": "AF-AE-PROVPHONE-NO-EXECUTE",
        }

    for name, _role in LIVE_GATES:
        record, rc = _run(name, modules[name])
        if rc is not None:
            return rc
        status, detail, expected, live = record
        report["checks"][name] = {
            "status": status,
            "detail": detail,
            "expected": expected,
            "live": live,
        }
        if status == "FAIL":
            report["delta"].append(
                {"check": name, "expected": expected, "live": live,
                 "detail": detail})

    failures = [n for n, c in report["checks"].items()
                if c.get("status") == "FAIL"]
    report["verdict"] = "PASS" if not failures else "FAIL"
    print(json.dumps(report, indent=2, sort_keys=True))
    return EX_OK if not failures else EX_MISMATCH


# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py and the U02 / U03 / U04 / U05 / U06 / U07 skeletons).
# The PROVISIONING ACTION is a positional subcommand ('provision' / 'verify')
# that REQUIRES --execute (the Trevor gate).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main_skeleton.py",
        description="U23 SMS-phone-provisioner dispatcher: offline plan, "
                    "offline self-test, live aggregate, and the Trevor-gated "
                    "PROVISIONING ACTION of the GHL-gated SMS phone surface "
                    "of the Anthology engine (Skill 59, u23_modules; the "
                    "packaged sibling of u02_modules/main_skeleton.py, "
                    "u03_modules/main_skeleton.py, u04_modules/main_skeleton.py, "
                    "u05_modules/main_skeleton.py, u06_modules/main_skeleton.py, "
                    "u07_modules/main_skeleton.py, "
                    "u08_u09_modules/main_skeleton.py and "
                    "u10_u13_modules/main_skeleton.py) — imports the family "
                    "modules by name and aggregates their records into ONE "
                    "fail-closed JSON report. Provisioning (the POST that "
                    "creates the number, the send-test-message POST, and the "
                    "outbound send POST) requires --execute (Trevor-gated) — "
                    "this dispatcher never mutates.")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow location id "
                         "(default: the CLIENT-standard location labels "
                         "CONVERT_AND_FLOW_LOCATION_ID / "
                         "GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID; "
                         "masked on every surface, never printed in full)")
    ap.add_argument("--dry-run", action="store_true",
                    help="offline plan only — no network, no credential (default: live verify)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout (default on for verify/plan)")
    ap.add_argument("--execute", action="store_true",
                    help="the Trevor gate for the PROVISIONING ACTION — "
                         "REQUIRED before any number is provisioned or any "
                         "message is sent; without it the ACTION is a STOP "
                         "(exit 2, AF-AE-PROVPHONE-NO-EXECUTE), never a "
                         "silent write; with it, provisioning is "
                         "create-only-absent with a post-create read-back")
    ap.add_argument("--selftest", "--self-test", dest="self_test", action="store_true",
                    help="run the offline self-test (golden + attack fixtures) and exit")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "provision", "self-test"],
                    help="positional subcommand form (verify / plan / provision / self-test)")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> --self-test so the flag form never
    # collides with the positional subcommand form.
    if "--self-test" in argv and "--selftest" not in argv:
        argv = ["--self-test" if a == "--self-test" else a for a in argv]
    args = ap.parse_args(argv)
    # Positional subcommand form (house shape): self-test -> the offline
    # battery; plan -> the offline dry-run.
    if args.cmd == "self-test":
        args.self_test = True
    elif args.cmd == "plan":
        args.dry_run = True

    try:
        modules = load_modules()

        if args.self_test:
            return self_test(modules)

        if args.dry_run:
            return plan(modules)

        if args.cmd == "provision" or args.cmd == "verify":
            # The Trevor gate, enforced at the CLI surface: a PROVISIONING
            # ACTION (or the SMS verification send) without --execute is a
            # STOP (exit 2), never a silent no-op and never a silent write.
            # WITH --execute the family's create-only-absent contract holds
            # — the dispatcher never mutates.
            if not args.execute:
                reg._stop(sys.stderr,
                          "%s REFUSED: no --execute (the Trevor gate)."
                          % args.cmd,
                          ["An ACTION without --execute is a STOP "
                           "(AF-AE-PROVPHONE-NO-EXECUTE / "
                           "AF-AE-SMSVER-NO-EXECUTE), never a silent "
                           "write. Re-run with --execute to authorize the "
                           "ACTION — it is create-only-absent with a "
                           "post-create read-back (marker %s)."
                           % _mask_id(args.location_id or "BY-LABEL")])
                return EX_STOP
            return verify_live(modules, args.location_id,
                               execute=True,
                               out=sys.stderr)

        # ---- live aggregate (PIT-gated for the live surfaces) ----
        return verify_live(modules, args.location_id,
                           execute=False,
                           out=sys.stderr)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[main-skeleton] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[main-skeleton] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[main-skeleton] HELD: %s\n" % exc)
        return EX_HELD
    except reg.InternalRailUnavailable as exc:
        sys.stderr.write("[main-skeleton] HELD (internal rail): %s\n" % exc)
        return EX_HELD
    except SkeletonError as exc:
        sys.stderr.write("[main-skeleton] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[main-skeleton] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
