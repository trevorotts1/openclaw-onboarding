#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u23_modules/docs_u23.py
# U23 SMS-PHONE PROVISIONING TOOLING — THE MODULE DOCSTRING / README, SHIPPED
# AS AN IMPORTABLE MODULE (ENGINE-MANIFEST.json row 53 — the GHL-gated
# LeadConnector SMS phone provisioner, scripts/provision_sms_phone.py,
# authored_by U23; CHANGELOG v0.1.24, 2026-08-11).
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u23_modules/ — the U23 tooling's documentation
# module, sibling of the phone lister, the provisioning ACTION, the SMS
# send verifier, the test-sms sender, the golden and attack fixtures, the
# test batteries, and the dispatcher it documents. It is NOT a manifest row:
# the U23 driver scripts/provision_sms_phone.py stays the single manifest row
# (ENGINE-MANIFEST.json row 53, exactly the delivery_report.py row-12 and
# live_verify_template.py row-54 sibling-helper pattern). Imported BY NAME as
# u23_modules.docs_u23 when a consumer wants the family's contract surfaces
# as DATA (the surfaces and their laws, the module inventory, the house exit
# codes, the autofail family, the doctrine) or its rendered README as text.
#
# WHAT THIS OWNS:
#   1. THE README. The module docstring below IS the U23 tooling README: what
#      the tooling provisions and verifies, the four v2 public surfaces, the
#      idempotency / read-back / gated-ACTION laws, the module inventory, the
#      exit-code contract, the credential / browser-UA / fail-closed doctrine.
#      The same content is carried as STRUCTURED DATA (SURFACES, MODULES,
#      EXIT_CODES, AF_CODES, DOCTRINE, CREDENTIAL_LABELS) so a consumer can
#      diff against it instead of parsing prose — and readme() renders the
#      README FROM that data, so the two can never drift.
#   2. THE DRIFT GATE. self_test() proves the documentation still matches
#      the shipped tree: every module the README lists exists on disk next to
#      this module (or in scripts/ for the row-53 driver), every surface row
#      is present exactly once, every house exit code is documented, the
#      browser-UA doctrine is pinned byte-equal to reg.CAF_BROWSER_UA, and
#      the rendered README covers every inventory row. A doc that names a
#      module that does not ship FAILS the self-test (exit 4, the house
#      enforced-violation code) — documentation is data, and stale
#      documentation is drift.
#   3. PURE DATA, BY CONSTRUCTION. Nothing here reads an env var, opens a
#      file at import, touches the network, or holds a credential. A
#      documentation module cannot leak what it never holds. It performs NO
#      requests, so it defines NO User-Agent constant of its own: the
#      browser UA that defeats the Cloudflare edge (CF error 1010) is
#      CAF_BROWSER_UA, owned by anthology_registry.py and applied by its
#      clients (CafClient) — the docs record that doctrine, they do not
#      re-implement it.
#
# THE TOOLING THIS DOCUMENTS (orientation):
#   MASTER-SPEC U23 — the SMS-PHONE PROVISIONING LAW of the anthology engine:
#   the client's Convert and Flow location must carry an SMS-capable phone
#   number BEFORE any SMS surface (stage gate nudges, snapshot-import
#   notifications, per-stage SMS links) can deliver. Every create is
#   Trevor-gated (--execute), every write is proven by read-back (a missing
#   post-create number object is a MISMATCH, exit 5, never a false
#   "provisioned"), and every request rides reg.CafClient, which applies
#   CAF_BROWSER_UA (the Cloudflare edge fronting
#   services.leadconnectorhq.com 403s urllib's default User-Agent, CF error
#   1010, before it ever reaches Convert and Flow).
#   The FOUR public v2 surfaces:
#     GET    /phones/numbers?locationId=<loc>             list existing numbers
#     GET    /phones/numbers/<id>?locationId=<loc>        one number by id
#     POST   /phones/numbers?locationId=<loc>             provision a number
#     POST   /phones/numbers/<id>/send-test-message       send an SMS test
#   (the send-test-message surface belongs to the row-53 driver's bounded
#   SMS-send verification — the same surface the operator watches in the
#   Convert and Flow UI — with a poll of read-back state until the number
#   reports sending-capable or a bounded window elapses: HELD, never a false
#   pass).
#   1. THE IDEMPOTENCY LAW (GET-first, provision only if absent): the tooling
#      LISTS the location's numbers first and provisions ONLY when no number
#      already present matches the requested scope — SMS-capable, judged by
#      PRESENCE / TRUTHINESS on the fixed key set only (smsEnabled /
#      sms_enabled; never any other field of a number). A location that
#      already carries an SMS-enabled number is VERIFIED and skipped (exit 0,
#      idempotent no-op — never a second number, never a second charge). A
#      failed listing REFUSES before any create: the tooling never provisions
#      into the unknown.
#   2. THE READ-BACK LAW: a write is never trusted without read-back. After
#      the POST, the created number is GET by id and must exist before any
#      report claims provisioned (AF-AE-PROVPHONE-READBACK-MISMATCH, exit 5,
#      never a false success). The SMS send is only verified when the send
#      response carries a message identifier (SID — the fail-closed
#      AF-AE-SMSVER-NO-SID rule of the extension verifier: an HTTP 200 whose
#      body carries no identifier is NEVER a pass).
#   3. THE GATED-ACTION LAW (--execute, the Trevor gate — u23_modules/
#      __init__.py doctrine): EVERY provisioning ACTION in this family
#      (create / provision / enable / subscribe / deploy) REFUSES without the
#      operator's explicit --execute (AF-AE-PROVPHONE-NO-EXECUTE / AF-AE-
#      PROVACTION-NO-EXECUTE / AF-AE-PHONELIST-NO-EXECUTE / AF-AE-SMSVER-NO-
#      EXECUTE, exit 2 — never a silent write, never a silent no-op); without
#      --execute a module reports what it WOULD do and exits without
#      mutating. Default and --dry-run are read-only / plan-only (no network
#      in dry-run — the offline plan is the dry-run body).
#   4. THE SCOPE-VS-EDGE LAW: a bare 401/403 is HELD (UpstreamBlockedError /
#      CafUnreachable, exit 3 — retryable, NEVER mislabeled as a scope
#      problem); a genuine location-scope denial is a STOP (exit 2).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE, everywhere in this tooling. The
# token + location resolve through anthology_registry (reg.resolve_pit /
# reg.resolve_location / reg._live_client; PIT first:
# CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY /
# GOHIGHLEVEL_PIT / GHL_API_KEY, then location:
# CONVERT_AND_FLOW_LOCATION_ID / GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID —
# live process env first, then the three canonical client env stores). SET /
# NOT SET only on every operator surface; a token value is NEVER printed. A
# phone number is reported by non-reversible marker only (last 4 digits; the
# verification destination by last 2), the location id is MASKED to its last
# 4 characters, and the SMS message text is NEVER echoed on any surface.
#
# BROWSER UA (CF 1010 LAW): every request rides reg.CafClient, which applies
# CAF_BROWSER_UA on EVERY request — the Cloudflare edge fronting
# services.leadconnectorhq.com 403s urllib's default "Python-urllib/x.y"
# User-Agent at the WAF edge (CF error 1010) before the request ever reaches
# Convert and Flow (W0.6 / GK-09). This documentation module makes NO network
# call and defines NO User-Agent constant of its own — the self-test PINS the
# browser-UA doctrine constant byte-equal to reg.CAF_BROWSER_UA (Mozilla/5.0,
# Chrome-bearing) so a registry regression is caught HERE first.
#
# FAIL-CLOSED (the whole point): a missing credential STOPS (exit 2), a
# non-pit- token is refused, an unreadable listing / a listing with NO number
# row is a REFUSAL before any create (never a provision-into-the-unknown), a
# transport / edge failure is HELD (exit 3, UNDETERMINED — never a verdict),
# a write NEVER happens without the operator's --execute (exit 2) and every
# write must read back (exit 5, never a fabricated success), an unmarked
# number entry is never silently trusted as SMS-capable, a credential-shaped
# string on any surface REFUSES the whole surface rather than print it, and a
# drifted authority (anthology_registry) breaks the family's self-tests FIRST
# (exit 4 — a tamper never masquerades as exit 1). A success is claimed ONLY
# when the live read carries the law. Every deviation is NAMED with its code —
# never a bare "something failed".
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py): move in
# silence (operator-verbose only); NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; STDLIB ONLY (urllib +
# json); calls NO model; never a client PII; READ-ONLY by doctrine — this
# documentation module never writes; the row-53 driver and its extension
# surfaces are the family's gated write surfaces (their OWN --execute, the
# dispatchers never write). Self-test failures are exit 4 (enforced
# violation — the AF-AE-* families below), never exit 1.
#
# USAGE (this module's own machine surface — pure data, nothing to leak):
#   python3 docs_u23.py                ONE JSON catalog of the whole tooling
#   python3 docs_u23.py readme         the rendered README (markdown text)
#   python3 docs_u23.py self-test      OFFLINE drift gate over the docs vs
#                                      the shipped tree; 0 clean, 4 drift
# =============================================================================
"""docs_u23.py -- README / module docstring for the U23 SMS-phone provisioning
tooling, as an importable fail-closed pure-data module: the GHL-gated
LeadConnector phone provisioner (ENGINE-MANIFEST.json row 53), its four v2
public surfaces, the idempotency / read-back / gated-ACTION laws, the
u23_modules inventory, the house exit codes, and the credential / browser-UA
/ fail-closed doctrine contracts. Performs no I/O at import and holds no
credential; readme() is rendered from the same structured data the self-test
asserts against, so documentation and data cannot drift."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# The fixed report contract (mirrors the golden-fixture naming discipline).
# ---------------------------------------------------------------------------
DOC_CONTRACT = "anthology-engine-u23-sms-phone-tooling-docs"
SCHEMA_VERSION = 1

# The U23 driver is the single manifest row; the u23_modules/ siblings ship
# as non-manifest helpers (the delivery_report.py row-12 pattern, exactly
# the docs_u02.py / docs_forms.py siblings). The family's own manifest row is
# STAMPED (row 53, verified at ship time, 2026-08-11).
U23_DRIVER = "provision_sms_phone.py"
U23_MANIFEST_ROW = 53
U23_SHIPPING_VERSION = "v0.1.24 (2026-08-11)"  # skill-version at ship time

# ---------------------------------------------------------------------------
# THE SURFACES AND THEIR LAWS — the family's contract surface, in the FIXED
# order the row-53 driver documents them. Each row is the family's law for
# ONE v2 public surface: the method + path, the role, the law, and the
# fail-closed claim.
# ---------------------------------------------------------------------------
SURFACES = (
    {
        "surface": 1,
        "method": "GET",
        "path": "/phones/numbers?locationId=<loc>",
        "role": ("list the location's existing phone numbers — READ-ONLY, "
                 "the GET-first side every provisioning decision starts from "
                 "(never from memory, never from a blind POST)"),
        "law": ("each entry is only ever used for the SMS-capable marker "
                "(presence / truthiness on the fixed key set smsEnabled / "
                "sms_enabled — never any other field) and the masked number; "
                "a failed listing REFUSES before any create (never a "
                "provision-into-the-unknown)"),
        "fails": ("AF-AE-PROVPHONE-READ-REFUSED / AF-AE-PROVACTION-READ-"
                  "REFUSED / AF-AE-PHONELIST-READ-REFUSED (exit 2 STOP per "
                  "scope/validation class, exit 3 HELD per edge/transport "
                  "class — never mislabeled)"),
    },
    {
        "surface": 2,
        "method": "GET",
        "path": "/phones/numbers/<id>?locationId=<loc>",
        "role": ("read back one number by id — READ-ONLY, the read-back a "
                 "write is never trusted without"),
        "law": ("a post-create GET that returns no number object for the "
                "created id is a MISMATCH (exit 5) — nothing is ever "
                "reported provisioned without read-back"),
        "fails": "AF-AE-PROVPHONE-READBACK-MISMATCH / AF-AE-PROVACTION-"
                 "READBACK-MISMATCH (exit 5)",
    },
    {
        "surface": 3,
        "method": "POST",
        "path": "/phones/numbers?locationId=<loc>",
        "role": ("provision an SMS-capable phone number — the Trevor-gated "
                 "ACTION boundary: runs ONLY under --execute, GET-first "
                 "idempotent (already-provisioned is a verified no-op, never "
                 "a second number, never a second charge)"),
        "law": ("a location that already carries an SMS-enabled number is "
                "VERIFIED and skipped (exit 0, no writes at all); without "
                "--execute the module reports what it WOULD do and exits "
                "without mutating (STOP, exit 2); a create response without "
                "a number id is a read-back mismatch (exit 5)"),
        "fails": ("AF-AE-PROVPHONE-NO-EXECUTE / AF-AE-PROVACTION-NO-EXECUTE "
                  "/ AF-AE-PHONELIST-NO-EXECUTE (exit 2) / "
                  "AF-AE-PROVPHONE-CREATE-REFUSED / AF-AE-PROVACTION-CREATE-"
                  "REFUSED / AF-AE-PHONELIST-CREATE-REFUSED (exit 2 or 3 per "
                  "class, exit 5 on no id)"),
    },
    {
        "surface": 4,
        "method": "POST",
        "path": "/phones/numbers/<id>/send-test-message",
        "role": ("send an SMS test message to verify the number's SMS "
                 "delivery — GHL-gated (--execute), bounded send-test-message "
                 "verification with a poll of read-back state until the "
                 "number reports sending-capable or a bounded window elapses "
                 "(HELD, never a false pass)"),
        "law": ("the row-53 driver's verify surface (provision_sms_phone.py "
                "verify action); the extension verifier (sms_verifier.py) "
                "requires HTTP 200 PLUS a message identifier (SID) before "
                "anything is called delivered — 200 without an id is NEVER a "
                "pass (exit 5)"),
        "fails": ("AF-AE-PROVPHONE-VERIFY-REFUSED (exit 2/3 per class) / "
                  "AF-AE-PROVPHONE-VERIFY-STALLED (exit 3, bounded window "
                  "elapsed — never a false pass) / AF-AE-SMSVER-NO-EXECUTE "
                  "(exit 2) / AF-AE-SMSVER-SEND-REFUSED (exit 2/3) / "
                  "AF-AE-SMSVER-NO-SID (exit 5)"),
    },
)

# ---------------------------------------------------------------------------
# THE MODULE INVENTORY. `place` names the directory relative to this module
# (the u23_modules package itself, or scripts/ for the row-53 driver);
# self-test proves each name exists at that place. `role` is the one-line
# contract each module owns; `offline` names the credential-free surface;
# `exit_codes` follows the house convention (0/1/2/3/5, 4 = self-test).
# ---------------------------------------------------------------------------
MODULES = (
    {
        "name": "provision_sms_phone.py",
        "place": "scripts/",
        "manifest_row": U23_MANIFEST_ROW,
        "role": ("the U23 driver — the SINGLE manifest row. GHL-gated "
                 "LeadConnector SMS phone provisioner for the client "
                 "location: GET /phones/numbers first, provision only when "
                 "no SMS-capable number exists (idempotent no-op on "
                 "already-provisioned), bounded send-test-message "
                 "verification; NEVER provisions or verifies without "
                 "--execute (the POSTs are the GHL-gated ACTIONs); "
                 "--dry-run and --self-test are OFFLINE"),
        "offline": "plan + dry-run + self-test (no token, no network)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "__init__.py",
        "place": "scripts/u23_modules/",
        "manifest_row": None,
        "role": ("fail-closed EMPTY package init — pure namespace container, "
                 "no runtime code; modules are imported BY NAME; records the "
                 "package doctrine (fail-closed, secrets by label, "
                 "browser-UA law for every GoHighLevel / Convert and Flow "
                 "surface, move in silence; ANY provision ACTION — create / "
                 "provision / enable / subscribe / deploy — requires "
                 "--execute explicitly, Trevor-gated)"),
        "offline": "trivially — it is empty",
        "exit_codes": "n/a (no executable surface)",
    },
    {
        "name": "phone_lister.py",
        "place": "scripts/u23_modules/",
        "manifest_row": None,
        "role": ("the LIVE PHONE LISTER — READ-ONLY GET /phones/numbers of "
                 "the location's existing numbers, fail-closed, masked "
                 "markers only (last 4 digits), with a GHL-gated (--execute) "
                 "GET-first provisioning path and bounded read-back; "
                 "never assumes, never prints a full number"),
        "offline": "plan + self-test (no token, no network)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "provision_action.py",
        "place": "scripts/u23_modules/",
        "manifest_row": None,
        "role": ("the PROVISIONING ACTION — the Trevor-gated POST "
                 "/phones/numbers surface: GET-first idempotent (a location "
                 "that already carries an SMS-enabled number is a verified "
                 "no-op), post-create read-back required, NEVER provisions "
                 "without --execute (the create POST is the GHL-scoped "
                 "ACTION boundary); without --execute the module reports "
                 "what it WOULD do and exits without mutating"),
        "offline": "plan + self-test (no token, no network); apply (dry-run "
                   "included) needs the location's OWN PIT BY LABEL",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "sms_verifier.py",
        "place": "scripts/u23_modules/",
        "manifest_row": None,
        "role": ("the FAIL-CLOSED SMS SEND VERIFIER (extension module) — "
                 "POST /conversations/messages/outbound under --execute and "
                 "require HTTP 200 PLUS a message identifier (SID, read by "
                 "key order on the fixed key set id / messageId / "
                 "message_id / sid / messageSid — exact keys only, never "
                 "any other field) before anything is called delivered; the "
                 "send POST is a GHL-scope ACTION — it charges an outbound "
                 "SMS — and runs ONLY under --execute; the identifier is "
                 "surfaced as SET, never echoed"),
        "offline": "plan + dry-run + self-test (no token, no network)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "attack_sms_failed.py",
        "place": "scripts/u23_modules/",
        "manifest_row": None,
        "role": ("the ATTACK FIXTURE — SMS SEND TEST-MESSAGE RETURNS "
                 "NON-200, MUST FAIL: the canonical send record is built by "
                 "the SINGLE AUTHORITY (provision_sms_phone.py — the U23 "
                 "SMS-verification LAW surface, never a second "
                 "implementation), then the ONE variable — the response "
                 "status — is changed from 200 to a non-200 code (the "
                 "house HTTP 502 shape the read-back ladder classifies "
                 "CafUnreachable); deterministic, single-variable, synthetic "
                 "material only; the --execute gate applies fail-closed in "
                 "BOTH directions (the attack payload is REFUSED without "
                 "--execute; its own verify carries execute_required: True)"),
        "offline": "plan + self-test (no network, no token surface)",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "golden_has_phone.py",
        "place": "scripts/u23_modules/",
        "manifest_row": None,
        "role": ("the GOLDEN PHONE-PROVISIONED FIXTURE — the canonical "
                 "in-memory SMS-PHONE PROVISIONED state of the U23 "
                 "provisioner: the client location's SMS-capable number "
                 "ALREADY PRESENT — the golden control of the GET-first "
                 "idempotency law (already-provisioned is VERIFIED, never "
                 "re-provisioned: exit 0, idempotent no-op, never a second "
                 "number, never a second charge); the anti-attack mirror of "
                 "the marker-MISSING attack shape; the listing carries "
                 "EXACTLY ONE number whose SMS marker is PRESENT and TRUE "
                 "(presence/truthiness on the FIXED key set, read through "
                 "the owning module — never re-implemented); synthetic "
                 "deterministic ids only"),
        "offline": "entirely — pure data + builders (synthetic ids only)",
        "exit_codes": "0/1/4/5",
    },
    {
        "name": "attack_no_phone.py",
        "place": "scripts/u23_modules/",
        "manifest_row": None,
        "role": ("the NO-PHONE ATTACK FIXTURE — the fail-closed PHONE-LAW "
                 "gate over the /phones/numbers listing surface: a location "
                 "is VERIFIED only when an SMS-capable number is present; "
                 "ANY listing that carries no SMS-capable number (above all "
                 "a listing with NO number at all — the state the operator "
                 "must provision) is REFUSED as a pass, never a clean read, "
                 "never a silent fallback; the attack half of the "
                 "golden_has_phone.py pair over ONE shared implementation "
                 "of the phone law (verify / dry_run / payload, the "
                 "no-phone state named AF-AE-PROVPHONE-NO-PHONE, the action "
                 "gate named AF-AE-PROVPHONE-NO-EXECUTE)"),
        "offline": "plan + self-test (no network, no token surface)",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "sms_sender.py",
        "place": "scripts/u23_modules/",
        "manifest_row": None,
        "role": ("the GHL-GATED TEST-SMS SENDER — sends one test SMS to a "
                 "given CONTACT through the location's LeadConnector "
                 "conversation surface (addressed by contactId — the "
                 "canonical Skill 44 send-sms contract imported byte-exact, "
                 "never re-invented: POST /conversations/messages, body "
                 "{type SMS / contactId / message}, Version header "
                 "2021-04-15 on the conversations surface — not the "
                 "registry's general 2021-07-28 — via a minimal CafClient "
                 "SUBCLASS whose only addition is the per-request Version "
                 "override; the Bearer, the browser User-Agent, and the "
                 "scope-vs-edge discrimination are inherited unchanged; "
                 "NEVER a hand-rolled raw urllib POST — the exact "
                 "fleet-wide bug PR #651 fixed); idempotent GET-first "
                 "contact check, bounded read-back verification (the newest "
                 "conversation message must BE the sent text, else HELD "
                 "exit 3 — never reported as sent), NEVER sends without "
                 "--execute"),
        "offline": "plan + dry-run + self-test (no token, no network)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "test_provision_action.py",
        "place": "scripts/u23_modules/",
        "manifest_row": None,
        "role": ("the UNIT TESTS for the provisioning ACTION (the "
                 "in-memory fake with a mutation log): the --execute gate is "
                 "provable OFFLINE at the function level (execute=False "
                 "returns EX_STOP and leaves the fake's mutation log EMPTY "
                 "— no write at all, regardless of what the network would "
                 "do) and at the CLI level (the no-execute refusal returns "
                 "BEFORE any credential work); dry-run writes nothing "
                 "(DIFFERENT laws: dry-run is the truthful offline plan, "
                 "exit 0; no-execute is the refusal to act, exit 2); "
                 "fail-closed ladder scope/validation/edge/transport/no-id/"
                 "missing; never-a-token and masked-marker assertions"),
        "offline": "entirely — in-memory fake, zero network, zero secrets, "
                   "zero writes",
        "exit_codes": "0/4 (pytest battery; enforced-violation discipline)",
    },
    {
        "name": "test_phone_lister.py",
        "place": "scripts/u23_modules/",
        "manifest_row": None,
        "role": ("the UNIT TESTS for the phone LISTER (the in-memory fake "
                 "with a mutation log): READ-ONLY ALWAYS (every list path "
                 "must leave the fake's mutation log EMPTY — a listing "
                 "never writes, with or without --execute; list_action "
                 "NEVER requires --execute), the fail-closed ladder "
                 "(a refused listing is never followed by a create, a "
                 "create with no number id is exit 5, an unmarked entry is "
                 "never silently trusted), the Trevor gate "
                 "(AF-AE-PHONELIST-NO-EXECUTE, exit 2, empty mutation "
                 "log), GET-first idempotency (an SMS-capable number "
                 "already present is a verified no-op with ZERO writes), "
                 "never-a-token and masked-marker assertions, the "
                 "browser-UA law pinned against reg.CAF_BROWSER_UA, and "
                 "scope-vs-edge discrimination"),
        "offline": "entirely — in-memory fake, zero network, zero secrets, "
                   "zero writes",
        "exit_codes": "0/4 (pytest battery; enforced-violation discipline)",
    },
    {
        "name": "test_sms_verifier.py",
        "place": "scripts/u23_modules/",
        "manifest_row": None,
        "role": ("the UNIT TESTS for the SMS send verifier (the in-memory "
                 "fake with a mutation log): the ONE law the battery exists "
                 "to enforce — AN UNCONFIRMED SEND IS NEVER CALLED "
                 "DELIVERED — HTTP 200 without a message identifier is "
                 "exit 5 (AF-AE-SMSVER-NO-SID), never a pass; fail-closed "
                 "arguments STOP before any network, no-execute STOP with "
                 "zero sends, happy path is ONE send with the documented "
                 "body and the identifier surfaced SET-only, the "
                 "send-refusal ladder scope/validation/edge/transport "
                 "(edge block never mislabeled as scope), the exact-key "
                 "SID extractor refuses foreign keys, and never-a-token "
                 "assertions; the module's own OFFLINE self-test battery "
                 "runs as a process, and the U23 sibling battery stays "
                 "green"),
        "offline": "entirely — in-memory fake, zero network, zero secrets, "
                   "zero sends",
        "exit_codes": "0/4 (pytest battery; enforced-violation discipline)",
    },
    {
        "name": "main_skeleton.py",
        "place": "scripts/u23_modules/",
        "manifest_row": None,
        "role": ("the U23 SMS-PHONE-PROVISIONER DISPATCHER — imports the "
                 "family modules BY NAME (importlib, never exec'd from a "
                 "path), enforces the fail-closed one-entry-point contract, "
                 "and resolves the aggregate exit code exactly as its U02 / "
                 "U03 / U04 / U05 / U06 / U07 / U08_U09 / U10_U13 "
                 "main_skeleton siblings do; it carries NO check logic "
                 "itself — the ACTION stays behind the siblings' OWN "
                 "--execute (a family module is exercised ONLY through this "
                 "CLI so --dry-run, --self-test, and the live aggregate "
                 "never drift apart)"),
        "offline": "plan + self-test",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "docs_u23.py",
        "place": "scripts/u23_modules/",
        "manifest_row": None,
        "role": ("THIS module — the family's README / documentation as an "
                 "importable fail-closed pure-data module: the four v2 "
                 "public surfaces and their laws, the module inventory, the "
                 "house exit codes, the autofail family, the doctrine, and "
                 "the credential labels; readme() renders FROM the same data "
                 "the self-test asserts against, so documentation and data "
                 "cannot drift; performs no I/O at import and holds no "
                 "credential"),
        "offline": "entirely — pure data; self-test is a read-only "
                   "filesystem drift gate",
        "exit_codes": "0/1/4",
    },
)

# ---------------------------------------------------------------------------
# HOUSE EXIT CODES (0/1/2/3/5; 4 = enforced violation). The exact contract
# the U23 tooling commits to; self-test pins all six.
# ---------------------------------------------------------------------------
EXIT_CODES = {
    0: "verified success — the live surface carries its law (also plan / "
       "dry-run / idempotent no-op / self-test / a documented PASS)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: ("STOP refusal — label NOT SET / non-pit- value / usage / the "
        "--execute gate withheld (AF-AE-PROVPHONE-NO-EXECUTE / "
        "AF-AE-PROVACTION-NO-EXECUTE / AF-AE-PHONELIST-NO-EXECUTE / "
        "AF-AE-SMSVER-NO-EXECUTE: an ACTION without the gate is a refusal, "
        "never a silent write) / a genuine location-scope denial"),
    3: ("HELD — Convert and Flow unreachable / Cloudflare edge block "
        "(CF error 1010) / the SMS verification not confirmed within the "
        "bounded window (AF-AE-PROVPHONE-VERIFY-STALLED) / an "
        "applied-but-unreadable write (the live state is UNDETERMINED, "
        "never reported as built)"),
    4: ("self-test FAILED (the AF-AE-* enforced-violation family — a "
        "tamper never masquerades as exit 1)"),
    5: ("mismatch / fail-closed default — a post-create read-back returned "
        "no number object, a create response carried no number id "
        "(AF-AE-PROVPHONE-READBACK-MISMATCH / AF-AE-PROVACTION-READBACK-"
        "MISMATCH), or an SMS send returned HTTP 200 without a message "
        "identifier (AF-AE-SMSVER-NO-SID) — never a fabricated success"),
}

# ---------------------------------------------------------------------------
# THE AF AUTOfail family of the U23 tooling — the codes the family's own
# surfaces declare. The family's manifest row (53) is STAMPED in
# ENGINE-MANIFEST.json; the autofail families themselves are recorded here
# as the codes the surfaces declare (the manifest's autofails table carries
# the shared AF-AE-TEMPLATE-* / ATTACK codes). Self-test failures are exit
# 4, never 1.
# ---------------------------------------------------------------------------
AF_CODES = (
    ("AF-AE-PROVPHONE-NO-EXECUTE", 2,
     "provisioning (the create POST) or SMS verification (the "
     "send-test-message POST) was requested without the operator's explicit "
     "--execute (the Trevor gate, u23_modules/__init__.py doctrine) — a "
     "refusal, never a silent no-op and never a silent write"),
    ("AF-AE-PROVPHONE-READ-REFUSED", 3,
     "listing numbers for the location failed (scope / validation / edge "
     "block / transport) — STOP (exit 2) or HELD (exit 3) per class, never "
     "a silent skip, never a provision-into-the-unknown"),
    ("AF-AE-PROVPHONE-CREATE-REFUSED", 3,
     "the location exists, no matching number, and the POST /phones/numbers "
     "was rejected (validation / scope / edge block / transport), or the "
     "response carried no number id — STOP, HELD or MISMATCH per class, "
     "never recorded as provisioned"),
    ("AF-AE-PROVPHONE-VERIFY-REFUSED", 3,
     "the verify read-back or the send-test-message POST failed (scope / "
     "validation / edge / transport) — STOP or HELD per class, never a "
     "false pass"),
    ("AF-AE-PROVPHONE-VERIFY-STALLED", 3,
     "the verification read-back never confirmed sending-capable within the "
     "bounded window — HELD (exit 3), never a false pass"),
    ("AF-AE-PROVPHONE-READBACK-MISMATCH", 5,
     "the post-create read-back returned no number object for the created "
     "id — nothing is ever reported provisioned without read-back"),
    ("AF-AE-PROVPHONE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test (enforced violation)"),
    ("AF-AE-PROVACTION-NO-EXECUTE", 2,
     "provisioning (the create POST) was requested without --execute — a "
     "refusal, never a silent write (the provision_action.py extension "
     "surface)"),
    ("AF-AE-PROVACTION-READ-REFUSED", 3,
     "listing numbers for the location failed — STOP or HELD per class, "
     "never a provision-into-the-unknown"),
    ("AF-AE-PROVACTION-CREATE-REFUSED", 3,
     "the create POST was rejected, or the response carried no number id — "
     "STOP, HELD or MISMATCH per class"),
    ("AF-AE-PROVACTION-READBACK-MISMATCH", 5,
     "the post-create read-back returned no number object — nothing is ever "
     "reported provisioned without read-back"),
    ("AF-AE-PROVACTION-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test (enforced violation)"),
    ("AF-AE-PHONELIST-NO-EXECUTE", 2,
     "provisioning (POST /phones/numbers) was requested without --execute — "
     "a refusal, never a silent write (the phone_lister.py surface)"),
    ("AF-AE-PHONELIST-READ-REFUSED", 3,
     "listing numbers for the location failed — STOP or HELD per class, "
     "never a silent skip, never a provision-into-the-unknown"),
    ("AF-AE-PHONELIST-CREATE-REFUSED", 3,
     "the location exists, no matching number, and the POST /phones/numbers "
     "was rejected (including no id on the response) — STOP, HELD or "
     "MISMATCH per class, a refused create is NEVER recorded as "
     "provisioned"),
    ("AF-AE-PHONELIST-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test (enforced violation)"),
    ("AF-AE-SMSVER-NO-EXECUTE", 2,
     "the send POST was requested without --execute — the module NEVER "
     "sends without the explicit GHL-gated execute flag (the "
     "sms_verifier.py extension surface)"),
    ("AF-AE-SMSVER-SEND-REFUSED", 3,
     "the outbound POST was rejected (scope / validation / edge block / "
     "transport) — STOP or HELD per class, never a silent skip, never a "
     "false delivered"),
    ("AF-AE-SMSVER-NO-SID", 5,
     "the send returned HTTP 200 but the body carried NO message identifier "
     "(SID) — a read-back mismatch, never a pass; an unconfirmed send is "
     "never called delivered"),
    ("AF-AE-SMSVER-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test (enforced violation)"),
    ("AF-AE-ATTACKSMSFAILED-ATTACK", 4,
     "the attack fixture tripped the OFFLINE self-test (enforced violation "
     "— the attack_sms_failed.py family)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of a family module or "
     "battery (enforced violation — the house code, shared with the U02 / "
     "U03 / U04 / U05 / U06 / U07 / U08 / U09 families)"),
)

# ---------------------------------------------------------------------------
# DOCTRINE — the house rules the whole U23 tooling commits to, as data so
# the README renders them from the same source the self-test asserts.
# ---------------------------------------------------------------------------
DOCTRINE = (
    ("Fail-closed", "a missing credential, a malformed input, an unreadable "
     "source, or a live read that cannot be completed is a REFUSAL or a "
     "recorded FAIL — never a blind pass, never a fabricated success; an "
     "unmarked number entry is never silently trusted as SMS-capable; an "
     "id / SID is NEVER guessed from memory; a location that already "
     "carries an SMS-enabled number is a verified no-op, never a second "
     "number, never a second charge"),
    ("Secrets", "credentials resolve BY LABEL only (SET / NOT SET); a token "
     "value is never printed, echoed, or reflected in any surface; a phone "
     "number is reported by non-reversible marker only (last 4 digits; the "
     "verification destination by last 2), the location id is MASKED to its "
     "last 4 characters, and the SMS message text is NEVER echoed; the "
     "message identifier is surfaced as SET, never its value; before any "
     "JSON is emitted the payload is scanned against the house credential "
     "shape (pit-<value>) and a hit REFUSES the whole surface"),
    ("Browser UA", "every request to GoHighLevel / Convert and Flow "
     "(services.leadconnectorhq.com) rides reg.CafClient, which applies "
     "CAF_BROWSER_UA on EVERY request — urllib's default "
     "'Python-urllib/x.y' is 403'd at the WAF edge (CF error 1010) before "
     "it ever reaches the API (W0.6 / GK-09); this documentation module "
     "makes NO network call, so it defines NO User-Agent constant of its "
     "own — the self-test PINS the constant byte-equal to reg.CAF_BROWSER_UA "
     "so a registry regression is caught HERE first"),
    ("Scope vs edge", "a bare 401/403 is HELD (UpstreamBlockedError / "
     "CafUnreachable, exit 3), never mislabeled as a scope problem; a "
     "genuine location-scope denial is a STOP (exit 2)"),
    ("Synthetic ids only", "the fixtures carry SYNTHETIC deterministic ids "
     "only (num_EXISTING / num_VOICE / num_SUSPECT / num_NEWQcDX / "
     "loc_QcDX / +12025559876 — the synthetic-id discipline of the sibling "
     "families) — a fixture id is never a real participant, number, "
     "location, or anthology id, and never a real token"),
    ("Single authority", "a law is read once, in one module: "
     "anthology_registry owns the credential resolution, the browser-UA "
     "wiring, and the scope-vs-edge exception classes; provision_sms_phone.py "
     "owns the U23 SMS-verification LAW surface (the send-test-message "
     "mutation and the verification read-back contract — the attack "
     "fixture builds from it, never a second implementation); the "
     "u23_modules/ siblings derive from them, never re-implement; a drift "
     "in an authority breaks the family's self-tests FIRST"),
    ("Gated actions", "--execute is the ONLY flag that performs a "
     "provisioning ACTION (create / provision / enable / subscribe / "
     "deploy — each surface's OWN CLI, Trevor-gated); every other "
     "invocation is a read-only plan or dry-run that prints exactly what it "
     "WOULD do (no network in dry-run); the read-back must prove every "
     "write (AF-AE-PROVPHONE-READBACK-MISMATCH / AF-AE-SMSVER-NO-SID, exit "
     "5); an applied-but-unreadable write is HELD (exit 3) — the live state "
     "is UNDETERMINED, never reported as built"),
    ("Move in silence", "operator-verbose only; NOTHING Anthropic in any "
     "runtime file; Convert and Flow naming in every client surface; "
     "STDLIB ONLY; calls NO model; never a client PII; READ-ONLY by "
     "doctrine — the docs and the fixtures never write; the row-53 driver "
     "and its extension surfaces are the family's gated write surfaces"),
)

# ---------------------------------------------------------------------------
# CREDENTIAL LABELS — BY LABEL ONLY. These are the label NAMES the tooling
# resolves through anthology_registry (live process env first, then the
# three canonical client env stores). A label is a name, never a value; the
# values they resolve to are never held here and never printed anywhere.
# ---------------------------------------------------------------------------
CREDENTIAL_LABELS = {
    "pit": (
        "CONVERT_AND_FLOW_PIT",
        "CONVERT_AND_FLOW_API_KEY",
        "GOHIGHLEVEL_API_KEY",
        "GOHIGHLEVEL_PIT",
        "GHL_API_KEY",
    ),
    "location": (
        "CONVERT_AND_FLOW_LOCATION_ID",
        "GOHIGHLEVEL_LOCATION_ID",
        "GHL_LOCATION_ID",
    ),
}

# Pinned counts (the fixture-counting discipline of golden_fields.py: a
# drifted inventory is drift, never tolerated). Adding a module to the U23
# tooling REQUIRES adding it here AND to the README's inventory — and a
# module the docs name that does not ship FAILS the self-test.
CONTRACT_SURFACE_COUNT = 4
CONTRACT_MODULE_COUNT = 14

class DocsError(Exception):
    """A fail-closed documentation refusal: the README data drifted from
    its own contract, so no catalog is shipped — wrong docs are worse than
    no docs."""

# ---------------------------------------------------------------------------
# Accessors — deep copies, so callers can never mutate the canonical data.
# ---------------------------------------------------------------------------
def surfaces() -> list:
    """The four v2 public surface rows as a mutable deep copy (callers may
    mutate their copy; the canonical tuple is never touched)."""
    return [dict(row) for row in SURFACES]

def modules() -> list:
    """The module inventory as a mutable deep copy."""
    return [dict(row) for row in MODULES]

def exit_codes() -> dict:
    """The house exit-code contract as a plain dict copy."""
    return dict(EXIT_CODES)

def af_codes() -> list:
    """The AF autofail family as plain (code, exit, meaning) tuples in a
    mutable list."""
    return list(AF_CODES)

# ---------------------------------------------------------------------------
# The rendered README — built FROM the data, so prose can never drift from
# the contract. This is the machine-readable form of the module docstring.
# ---------------------------------------------------------------------------
def readme() -> str:
    """The U23 tooling README, rendered from the structured data above.

    One markdown document: what the tooling is, the four v2 public surfaces
    and their laws, the module inventory, the house exit codes, the
    autofail family, the doctrine, and the credential labels. Because every
    section renders from the same constants the self-test asserts, a drift
    in the data FAILS the self-test before it can ship a stale README."""
    lines = [
        "# U23 SMS-phone provisioning tooling — the GHL-gated phone "
        "provisioner and its fail-closed surfaces (README)",
        "",
        "Shipped as `scripts/provision_sms_phone.py` (ENGINE-MANIFEST.json "
        "row %d, authored_by U23; %s) plus the importable siblings in "
        "`scripts/u23_modules/` — the phone lister, the provisioning "
        "ACTION, the SMS send verifier, the test-sms sender, the golden "
        "and attack fixtures, the test batteries, the dispatcher, and this "
        "documentation module — documented machine-side by this module "
        "(`u23_modules.docs_u23`)."
        % (U23_MANIFEST_ROW, U23_SHIPPING_VERSION),
        "",
        "The client's Convert and Flow location must carry an SMS-capable "
        "phone number BEFORE any SMS surface (stage gate nudges, "
        "snapshot-import notifications, per-stage SMS links) can deliver. "
        "Every create is Trevor-gated (--execute — REFUSED without it, "
        "exit 2, never a silent write and never a silent no-op), every "
        "write is proven by read-back (exit 5, never a fabricated success), "
        "and every request rides reg.CafClient, which applies CAF_BROWSER_UA "
        "(the Cloudflare edge fronting services.leadconnectorhq.com 403s "
        "urllib's default User-Agent, CF error 1010, before it ever reaches "
        "Convert and Flow). The live surfaces run only from a session that "
        "can resolve the location's OWN private-integration token BY LABEL "
        "(PIT first, then the canonical client env stores); `plan` / "
        "`dry-run` and `self-test` are OFFLINE (no token, no network).",
        "",
        "## The four v2 public surfaces and their laws",
        "",
    ]
    for row in SURFACES:
        lines.append("%d. **%s %s** — %s. Law: %s. Fails: %s."
                     % (row["surface"], row["method"], row["path"],
                        row["role"], row["law"], row["fails"]))
        lines.append("")
    lines += [
        "## Module inventory",
        "",
    ]
    for row in MODULES:
        place = row["place"].rstrip("/") + "/" + row["name"]
        row_no = ("manifest row %d" % row["manifest_row"]
                  if row["manifest_row"] is not None else "sibling helper")
        lines.append("- `%s` (%s) — %s Offline surface: %s. Exit codes: %s."
                     % (place, row_no, row["role"], row["offline"],
                        row["exit_codes"]))
    lines += [
        "",
        "## Exit codes (house convention 0/1/2/3/5; 4 = enforced violation)",
        "",
    ]
    for code in sorted(EXIT_CODES):
        lines.append("- %d — %s" % (code, EXIT_CODES[code]))
    lines += [
        "",
        "## AF autofail family",
        "",
    ]
    for code, exit_code, meaning in AF_CODES:
        lines.append("- %s (exit %d) — %s" % (code, exit_code, meaning))
    lines += [
        "",
        "## Doctrine",
        "",
    ]
    for name, text in DOCTRINE:
        lines.append("- %s: %s." % (name, text))
    lines += [
        "",
        "## Credentials — by label, never by value",
        "",
    ]
    for group, labels in CREDENTIAL_LABELS.items():
        lines.append("- %s: %s" % (group, ", ".join(labels)))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: the documentation's drift gate. No network, no
# credentials, only read-only filesystem existence checks for the modules
# the README claims ship. A FAILED self-test is exit 4 (enforced
# violation), never 'unexpected error' — the house self-test discipline.
# ---------------------------------------------------------------------------
EX_VIOLATION = 4
EX_OK = 0
EX_ERR = 1

def _module_file(row: dict) -> Path:
    """The on-disk path a README inventory row claims. u23_modules/ rows
    live next to this module; the row-53 driver lives in scripts/."""
    base = Path(__file__).resolve().parent
    if row.get("place", "").strip("/") == "scripts":
        base = base.parent
    return base / row["name"]

def _self_test_body(dev) -> None:
    dev.write("[docs-u23] pinning: %d v2 surfaces, %d modules, exit codes "
              "0..5\n"
              % (CONTRACT_SURFACE_COUNT, CONTRACT_MODULE_COUNT))

    srows = SURFACES
    if len(srows) != CONTRACT_SURFACE_COUNT:
        raise AssertionError(
            "SURFACES carries %d rows, contract is %d — the U23 surface "
            "list drifted; refusing to ship a stale README."
            % (len(srows), CONTRACT_SURFACE_COUNT))
    seen_surfaces = set()
    for row in srows:
        num = row.get("surface")
        if not isinstance(num, int) or num in seen_surfaces:
            raise AssertionError(
                "SURFACES numbers must be unique integers, got %r" % num)
        seen_surfaces.add(num)
        for key in ("method", "path", "role", "law", "fails"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise AssertionError(
                    "SURFACES row %d lost its %r field — the surface "
                    "contract is incomplete." % (num, key))
    if seen_surfaces != set(range(1, CONTRACT_SURFACE_COUNT + 1)):
        raise AssertionError(
            "SURFACES numbers must be exactly 1..%d, got %s"
            % (CONTRACT_SURFACE_COUNT, sorted(seen_surfaces)))

    # The four v2 paths are load-bearing: the U23 SMS-phone law pins the
    # public LeadConnector rail (provision_sms_phone.py surface block), and
    # the phone_lister / provision_action / sms_verifier siblings derive
    # from the same rail — a drifted path is a drifted law.
    paths = tuple(row["path"] for row in srows)
    if paths != ("/phones/numbers?locationId=<loc>",
                 "/phones/numbers/<id>?locationId=<loc>",
                 "/phones/numbers?locationId=<loc>",
                 "/phones/numbers/<id>/send-test-message"):
        raise AssertionError(
            "the documented v2 paths drifted from the U23 phone rail: %r — "
            "refusing to ship a stale README." % (paths,))

    mods = MODULES
    if len(mods) != CONTRACT_MODULE_COUNT:
        raise AssertionError(
            "MODULES carries %d rows, contract is %d — a U23 module was "
            "added or removed without updating the inventory (and this "
            "self-test); refusing to ship a stale README."
            % (len(mods), CONTRACT_MODULE_COUNT))
    seen_names = set()
    for row in mods:
        name = row.get("name")
        if not isinstance(name, str) or not name or name in seen_names:
            raise AssertionError(
                "MODULES names must be unique non-empty strings, got %r"
                % name)
        seen_names.add(name)
        for key in ("place", "role", "offline", "exit_codes"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise AssertionError(
                    "MODULES row %r lost its %r field." % (name, key))
        f = _module_file(row)
        if not f.is_file():
            raise AssertionError(
                "README inventory names %s, but that file does not ship at "
                "%s — documentation drifted from the tree (fail-closed: a "
                "doc that names a module that does not ship must never "
                "pass)." % (name, f))

    if set(EXIT_CODES) != {0, 1, 2, 3, 4, 5}:
        raise AssertionError(
            "EXIT_CODES must carry exactly 0..5 (house convention), got %s"
            % sorted(EXIT_CODES))
    for code in (0, 1, 2, 3, 4, 5):
        if not isinstance(EXIT_CODES[code], str) or not EXIT_CODES[code]:
            raise AssertionError("EXIT_CODES[%d] lost its meaning." % code)

    codes = [c for c, _, _ in AF_CODES]
    if len(codes) != len(set(codes)) or not codes:
        raise AssertionError("AF_CODES must carry unique, non-empty codes.")
    exits = {e for _, e, _ in AF_CODES}
    if not exits <= {2, 3, 4, 5}:
        raise AssertionError(
            "AF family must map only onto STOP/HELD/self-test/mismatch "
            "exits (2/3/4/5), got %s" % sorted(exits))

    if not DOCTRINE or any(
            not isinstance(name, str) or not isinstance(text, str)
            or not name or not text for name, text in DOCTRINE):
        raise AssertionError("DOCTRINE must carry non-empty (name, text) rows.")

    if not CREDENTIAL_LABELS or not all(
            labels and all(isinstance(l, str) and l.isupper() and l
                           for l in labels)
            for labels in CREDENTIAL_LABELS.values()):
        raise AssertionError(
            "CREDENTIAL_LABELS must carry non-empty UPPERCASE label names "
            "only — a label is a name, never a value.")

    # The browser-UA doctrine is pinned byte-equal to the registry — a
    # registry regression is caught HERE first (the family's live surfaces
    # ride reg.CafClient, which applies CAF_BROWSER_UA on every request).
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import anthology_registry as reg  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            "anthology_registry cannot be imported to pin the browser-UA "
            "doctrine (%s: %s)." % (type(exc).__name__, exc))
    if not getattr(reg, "CAF_BROWSER_UA", "") or not (
            "Mozilla/5.0" in reg.CAF_BROWSER_UA
            and "Chrome/" in reg.CAF_BROWSER_UA):
        raise AssertionError(
            "reg.CAF_BROWSER_UA is missing or not a browser User-Agent — "
            "the CF 1010 law drifted; refusing to ship a stale README.")

    # The rendered README must cover the data it renders (a dropped section
    # is drift, never a silent omission), and it must never leak a token:
    # the credential-shape scan is the same never-a-real-token doctrine the
    # sibling builders enforce before every surface.
    rendered = readme()
    for row in SURFACES:
        if row["path"] not in rendered:
            raise AssertionError(
                "readme() no longer renders surface %d (%s) — the README "
                "drifted from SURFACES." % (row["surface"], row["path"]))
    for row in MODULES:
        if row["name"] not in rendered:
            raise AssertionError(
                "readme() no longer renders module %r — the README drifted "
                "from MODULES." % row["name"])
    for code in sorted(EXIT_CODES):
        if str(code) + " —" not in rendered:
            raise AssertionError(
                "readme() no longer renders exit code %d." % code)
    import re as _re
    # A real credential value is pit- followed by alphanumerics; the
    # doctrine's own literal template "pit-<value>" is the SHAPE description,
    # never a credential, and must not trip the scan.
    if _re.search(r"pit-[A-Za-z0-9]+", rendered):
        raise AssertionError(
            "the rendered README carries a credential-shaped string — "
            "REFUSED without printing it (the never-a-real-token "
            "doctrine).")

    dev.write("[docs-u23] PASS — README data and shipped tree agree "
              "(%d surfaces, %d modules, exit 0..5, %d af codes).\n"
              % (len(srows), len(mods), len(codes)))

def self_test(out=None) -> int:
    """The module's own OFFLINE self-test (no network, no credentials).
    Returns 0 on a clean pass, 4 on a detected drift — a stale README never
    masquerades as a pass."""
    import io
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[docs-u23] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family discipline, "
                         "enforced violation): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return 0


# ---------------------------------------------------------------------------
# CLI — ONE JSON catalog object (default), the rendered README, or the
# offline self-test. Pure data; there is nothing secret here to leak.
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="docs_u23.py",
        description="U23 SMS-phone provisioning tooling documentation "
                    "module — README, the four v2 public surfaces and their "
                    "laws, module inventory, exit codes, doctrine, "
                    "credential labels (pure data; nothing to leak).")
    parser.add_argument("cmd", nargs="?", choices=("catalog", "readme",
                                                   "self-test"),
                        default="catalog",
                        help="catalog (default): ONE JSON object; readme: "
                             "the rendered README text; self-test: offline "
                             "drift gate (0 clean, 4 drift)")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "readme":
            sys.stdout.write(readme())
            return EX_OK
        print(json.dumps({
            "contract": DOC_CONTRACT,
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "verifier": U23_DRIVER,
            "manifest_row": U23_MANIFEST_ROW,
            "shipping": U23_SHIPPING_VERSION,
            "surfaces": surfaces(),
            "modules": modules(),
            "exit_codes": exit_codes(),
            "af_codes": af_codes(),
            "doctrine": [{"name": n, "text": t} for n, t in DOCTRINE],
            "credential_labels": {k: list(v)
                                  for k, v in CREDENTIAL_LABELS.items()},
            "note": "pure data — no credential value is held or printed; "
                    "provisioning ACTIONS stay GHL-gated (--execute, "
                    "Trevor-gated)",
        }, indent=2, sort_keys=True))
        return EX_OK
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[docs-u23] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
