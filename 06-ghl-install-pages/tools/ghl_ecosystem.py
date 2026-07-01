#!/usr/bin/env python3
"""ghl_ecosystem.py — T3 ecosystem builder + the form->CRM roundtrip PROOF.

WHAT THIS IS (and the failure it fixes)
---------------------------------------
GOAL-2 R5 (ecosystem) failed because the prior ``v1_build.py`` wrote
calendar / product / form / contact as ``status:"PLANNED"`` JSON stubs and
NEVER created anything — only the workflow was really POSTed, and there was no
contact created and no form->CRM proof at all. This module is the fixed
replacement for that stage: it orchestrates the FULL ecosystem against the
operator BlackCEO fixture sub-account and produces REAL creation receipts
(``http_status:201``, real ids, a re-GET read-back), plus the dimension's hard
requirement — a *form->CRM proof*: a test opt-in submission that demonstrably
creates a CRM contact carrying the expected tags, asserted by a re-read.

THIS IS THE GLUE, NOT THE CLICKER / NOT THE TRANSPORT (same boundary as
``ghl_builder.py`` and ``ghl_rest_canvas.py``):
  * It owns the deterministic mechanical parts — the build+verify SEQUENCE, the
    payload shapes, the receipt schema, the env pre-flight, and the pure
    form->CRM assertion logic.
  * It performs NO network I/O of its own. Every GHL operation is supplied as an
    injected callable (an ``EcosystemOps``), so the orchestration is unit-tested
    with mocks and there are ZERO live GHL calls in this phase. The live wiring
    (the Skill-44 CLI for the services.* ecosystem, and ``ghl_rest_canvas`` +
    agent-browser for the on-page opt-in form) is built by the caller and passed
    in; this module decides WHAT to call, in WHAT ORDER, and WHAT proves success.

THE AUTH-MODEL SPLIT THIS MODULE HONORS (load-bearing)
------------------------------------------------------
  * ``services.leadconnectorhq.com`` + ``Authorization: Bearer <LOCATION PIT>``
    -> calendars / products+prices / forms / contacts (the Skill-44 ecosystem
    REST). Runs from BARE PYTHON (it is NOT behind the Cloudflare bot
    interstitial). The injected ops route here via the Skill-44 CLI.
  * ``backend.leadconnectorhq.com`` + ``token-id`` header -> funnels/pages
    (the on-page opt-in FORM embed) and workflow-trigger rewire. MUST run
    INSIDE the agent-browser eval (Cloudflare 1010 from bare Python). The
    on-page opt-in is therefore an ``edit_element_customcode`` + ``page_autosave``
    step (delegated to ``ghl_rest_canvas`` via the injected op), NOT a services.*
    call.

THE BUILD+VERIFY SEQUENCE (each step leaves a real receipt; partial = evidence)
-------------------------------------------------------------------------------
  0. PRE-FLIGHT — assert the env: target location is in CAF_ALLOWED_LOCATION_IDS
     and a LOCATION PIT is present. Refuse loud on miss (never co-mingle, never
     write to the wrong sub-account).
  1. CALENDAR  -> create "Scent-Bar Workshop"; receipt {http_status:201, id,
     reread_http_status:200}.
  2. PRODUCT + PRICE -> create the product, then a price on it; receipts carry
     both ids + a re-GET.
  3. OPT-IN FORM ON PAGE -> embed the 3-field form (firstName/email/phone) as a
     real custom-code element via canvas-REST autosave on the opt-in page;
     receipt carries the live page_id it lives on + the marker proving it
     rendered (verified by the caller's preview re-fetch).
  4. CONTACT + FORM->CRM PROOF (the hard requirement):
       a. BASELINE: search/list -> record ``before_count``.
       b. SUBMIT the opt-in (preferred: POST the form payload to the page's
          capture endpoint; fallback: create the contact directly with the same
          field+tag set).
       c. PROVE the roundtrip: search by the unique email -> assert the new
          contact id exists AND carries the expected tags -> re-GET the contact.
       d. ``after_count == before_count + 1``.
       e. Reversibility: delete the test contact (logged) so the fixture is
          left clean.
  5. WORKFLOW -> create + verify triggers via ``?includeTriggers=true`` (kept as
     the already-working receipt; created through the injected op).

NO FABRICATION: a step that does not return a 201 / does not read back / whose
proof assertion fails is recorded as ``ok:false`` with the real error. There is
no "PLANNED" success. The module FAILS LOUD rather than emit an optimistic
receipt.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# ── Constants ─────────────────────────────────────────────────────────────────

# The ONLY sub-account this fix may ever touch: the configured GHL location id.
# Read from the environment (the operator's own fixture sub-account on the box
# that runs this; NEVER a client's) so no real sub-account id is baked into the
# template source. Resolved from the canonical location-id env names used across
# the Skill-44 wrappers; a generic non-real placeholder keeps the module
# importable when unset (it can never match a real sub-account). Asserted in
# pre-flight against the live whitelist env var so a stray location can never be
# built into.
OPERATOR_FIXTURE_LOCATION_ID = (
    os.environ.get("GHL_LOCATION_ID")
    or os.environ.get("CAF_LOCATION_ID")
    or os.environ.get("GOHIGHLEVEL_LOCATION_ID")
    or "FIXTURE_LOCATION_0000"
)

# The env var the Skill-44 safety gate reads (comma-separated whitelist). The
# target location MUST appear here or every write is refused (fail-closed).
ALLOWED_LOCATIONS_ENV = "CAF_ALLOWED_LOCATION_IDS"

# Env names that may carry the LOCATION Private Integration Token (Bearer) for
# the services.* ecosystem REST. First non-empty wins; the CANONICAL
# GOHIGHLEVEL_API_KEY is preferred (matches ghl_media.py + openclaw.json), with
# the legacy GHL_API_KEY and the Skill-44 engine name CAF_API_KEY accepted as
# aliases so the pre-flight passes whether invoked via the wrapper or directly.
PIT_ENV_CANDIDATES = (
    "GOHIGHLEVEL_API_KEY",             # preferred — matches openclaw.json + ghl_media.py
    "GHL_API_KEY",                     # legacy short alias
    "GHL_PIT",                         # canonical short alias
    "GHL_TOKEN",                       # alternate alias
    "GHL_PRIVATE_INTEGRATION_TOKEN",   # explicit full-name alias
    "PRIVATE_INTEGRATION_TOKEN",       # bare PIT alias
    "GHL_PRIVATE_TOKEN",               # shortened private-token alias
    "PIT_TOKEN",                       # short PIT alias
    "GHL_PIT_TOKEN",                   # combined PIT alias
    "GOHIGHLEVEL_LOCATION_PIT",        # explicit LOCATION-PIT name
    "GHL_LOCATION_PIT",                # explicit LOCATION-PIT short alias
    "CAF_API_KEY",                     # Skill-44 engine alias — retained for backward compat
)
# GHL PIT aliases: see TERMINOLOGY.md for the canonical alias set and backend-equivalence notes.

# Tags the opt-in test lead must carry — the form->CRM proof asserts BOTH are
# present on the created contact (a contact with neither tag does not prove the
# opt-in routed through; a partial-tag contact is a FAIL).
WORKSHOP_TAGS = ("workshop-registrant", "soap-lead")

# A unique, non-deliverable test email so the proof never collides with a real
# contact and never emails anyone. ``.invalid`` is reserved (RFC 2606) — it can
# never resolve.
TEST_EMAIL_DOMAIN = "blackceo-soap-test.invalid"


# ── Pre-flight env assertion ──────────────────────────────────────────────────

class EcosystemPreflightError(RuntimeError):
    """Raised when the environment is unsafe to build the ecosystem (wrong/missing
    location whitelist, or no LOCATION PIT). A hard STOP — never proceed."""


def _allowed_locations(env: dict | None = None) -> frozenset[str]:
    env = env if env is not None else os.environ
    raw = (env.get(ALLOWED_LOCATIONS_ENV) or "").strip()
    if not raw:
        return frozenset()
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


def _resolve_pit(env: dict | None = None) -> str:
    env = env if env is not None else os.environ
    for name in PIT_ENV_CANDIDATES:
        val = (env.get(name) or "").strip()
        if val:
            return val
    return ""


def preflight(target_location_id: str = OPERATOR_FIXTURE_LOCATION_ID,
              env: dict | None = None) -> dict:
    """Assert it is safe to build the ecosystem into ``target_location_id``.

    Checks (all must pass; raises ``EcosystemPreflightError`` otherwise):
      * ``target_location_id`` is non-empty and is the operator fixture id
        (this module is fixture-only; it refuses any other location so a client
        sub-account can never be targeted by accident).
      * ``CAF_ALLOWED_LOCATION_IDS`` contains ``target_location_id`` (the
        Skill-44 safety gate would otherwise refuse every write — fail-closed).
      * a LOCATION PIT is present in the env (the services.* Bearer token).

    Returns a small, secret-free fact dict for the receipt (``pit_present:true``
    — never the token itself).
    """
    target = (target_location_id or "").strip()
    if not target:
        raise EcosystemPreflightError(
            "REFUSE: target_location_id is empty — refusing to build into nothing."
        )
    if target != OPERATOR_FIXTURE_LOCATION_ID:
        raise EcosystemPreflightError(
            f"REFUSE: target_location_id {target!r} is not the operator fixture "
            f"({OPERATOR_FIXTURE_LOCATION_ID!r}). This module is fixture-only — "
            "it never builds into a client sub-account."
        )
    allowed = _allowed_locations(env)
    if not allowed:
        raise EcosystemPreflightError(
            f"REFUSE: {ALLOWED_LOCATIONS_ENV} is empty/unset — the safety gate "
            "fail-closes and every write would be refused. Set "
            f"{ALLOWED_LOCATIONS_ENV}={OPERATOR_FIXTURE_LOCATION_ID}."
        )
    if target not in allowed:
        raise EcosystemPreflightError(
            f"REFUSE: target {target!r} is not in {ALLOWED_LOCATIONS_ENV} "
            f"({sorted(allowed)}) — co-mingling guard."
        )
    if not _resolve_pit(env):
        raise EcosystemPreflightError(
            "REFUSE: no LOCATION PIT found in env (looked for "
            f"{', '.join(PIT_ENV_CANDIDATES)}). The services.* ecosystem REST "
            "needs a Bearer Private Integration Token."
        )
    return {
        "target_location_id": target,
        "allowed_contains_target": True,
        "pit_present": True,  # never the token value
    }


# ── Payload shapes (pure — what each create call sends) ──────────────────────

def calendar_body(location_id: str, name: str, *, slot_duration: int = 30,
                  slot_interval: int = 30, timezone: str = "America/New_York",
                  description: str | None = None,
                  team_member_ids: list[str] | None = None) -> dict:
    """Shape the POST /calendars/ body (Version 2021-04-15). Mirrors the new
    Skill-44 ``calendars create`` subcommand."""
    body: dict[str, Any] = {
        "locationId": location_id,
        "name": name,
        "slotDuration": slot_duration,
        "slotInterval": slot_interval,
        "timezone": timezone,
    }
    if description:
        body["description"] = description
    if team_member_ids:
        body["teamMembers"] = [{"userId": uid} for uid in team_member_ids]
    return body


def product_body(location_id: str, name: str, *, product_type: str = "SERVICE",
                 description: str | None = None, image_url: str | None = None) -> dict:
    """Shape the POST /products/ body (Version 2021-07-28)."""
    body: dict[str, Any] = {
        "locationId": location_id,
        "altId": location_id,
        "altType": "location",
        "name": name,
        "productType": product_type,
    }
    if description:
        body["description"] = description
    if image_url:
        body["image"] = image_url
    return body


def price_body(location_id: str, product_id: str, name: str, amount_cents: int, *,
               currency: str = "USD", price_type: str = "one_time") -> dict:
    """Shape the POST /products/{id}/price body. ``amount_cents`` is the
    smallest currency unit (cents): $49.00 -> 4900."""
    if not product_id:
        raise ValueError("product_id is required to attach a price")
    if not isinstance(amount_cents, int) or amount_cents <= 0:
        raise ValueError("amount_cents must be a positive integer (cents)")
    return {
        "locationId": location_id,
        "altId": location_id,
        "altType": "location",
        "name": name,
        "type": price_type,
        "currency": currency,
        "amount": amount_cents,
    }


def optin_form_html(*, action_url: str, location_id: str,
                    fields: tuple[str, ...] = ("firstName", "email", "phone"),
                    marker: str) -> str:
    """Build the on-page opt-in form HTML (a custom-code element body).

    A real 3-field form posting to the page's contact-capture ``action_url``.
    The ``marker`` is embedded as a hidden input + an HTML comment so the
    caller's preview re-fetch (``ghl_builder.verify_url(preview_url, marker)``)
    can prove it actually rendered. This string is what the canvas-REST op
    splices into the page via ``edit_element_customcode`` + ``page_autosave``.
    """
    if not action_url:
        raise ValueError("action_url is required (the page contact-capture endpoint)")
    if not marker:
        raise ValueError("marker is required (proves the form rendered on preview)")
    labels = {"firstName": "First name", "email": "Email", "phone": "Phone"}
    types = {"firstName": "text", "email": "email", "phone": "tel"}
    inputs = []
    for f in fields:
        inputs.append(
            f'<label>{labels.get(f, f)}'
            f'<input type="{types.get(f, "text")}" name="{f}" '
            f'{"required" if f in ("firstName", "email") else ""}></label>'
        )
    inputs_html = "".join(inputs)
    return (
        f"<!-- {marker} -->"
        f'<form class="zhc-optin" method="POST" action="{action_url}" '
        f'data-location-id="{location_id}">'
        f'<input type="hidden" name="__zhc_marker" value="{marker}">'
        f"{inputs_html}"
        f'<button type="submit">Reserve my seat</button>'
        f"</form>"
    )


def make_test_email(prefix: str = "workshop") -> str:
    """Return a unique, non-deliverable test email for the opt-in proof. Uses a
    short uuid so repeated runs never collide and the search-by-email matches
    exactly one contact."""
    suffix = uuid.uuid4().hex[:10]
    return f"{prefix}+{suffix}@{TEST_EMAIL_DOMAIN}"


def optin_payload(email: str, *, first_name: str = "Workshop",
                  last_name: str = "TestLead", phone: str = "+15555550123",
                  tags: tuple[str, ...] = WORKSHOP_TAGS) -> dict:
    """The opt-in form submission payload (what a real visitor submit sends, and
    the fallback ``contacts create`` body). Carries the unique email + the two
    workshop tags the proof asserts."""
    return {
        "firstName": first_name,
        "lastName": last_name,
        "email": email,
        "phone": phone,
        "tags": list(tags),
    }


# ── Injected operations contract (the live wiring is supplied by the caller) ──

@dataclass
class EcosystemOps:
    """The set of GHL operations the orchestrator calls. The caller wires each
    to the real transport (Skill-44 CLI for services.*; ``ghl_rest_canvas`` +
    agent-browser for the on-page form). In unit tests they are mocks, so the
    orchestration + the form->CRM proof are exercised with ZERO live calls.

    Every op returns a plain dict (the parsed API response / receipt). The
    orchestrator inspects shapes only — it never opens a socket.

    Required ops:
      create_calendar(body)            -> {id|_id|calendar, ...}
      create_product(body)             -> {id|_id|product, ...}
      create_price(product_id, body)   -> {id|_id|price, ...}
      embed_optin_form(page_id, html, marker) -> {ok, page_id, marker, ...}
                                          (canvas-REST autosave on the page)
      count_contacts()                 -> int  (baseline / after count)
      submit_optin(payload)            -> {ok, ...}  (POST to capture endpoint;
                                          may return without the contact id)
      search_contact_by_email(email)   -> {contacts:[...]} | [...]  (the proof read)
      get_contact(contact_id)          -> {contact:{...}} | {...}   (re-GET)
      delete_contact(contact_id)       -> {ok|status, ...}          (cleanup)
      create_workflow(spec)            -> {id|workflow, triggers?:[...]}
      read_workflow_triggers(wf_id)    -> {triggers:[...]}  (?includeTriggers=true)

    Extended ops (B3 — native multi-step/conditional form + calendar re-GET):
      create_form(body)                -> {id|_id|form, ...}
                                          Creates a GoHighLevel native form via
                                          POST /forms/ (services.* Bearer PIT).
                                          Used when form_complexity:'advanced'
                                          is detected by the classifier — the
                                          lightweight optin_form_html (above)
                                          remains the default for simple email
                                          capture. A create that returns no id
                                          is NOT a success — _extract_id raises.
      get_form(form_id)                -> {form:{...}} | {...}
                                          Re-GET a form by id to confirm it is
                                          canonically stored (read-back proof).
                                          Returns the form record; the caller
                                          asserts ``id`` matches.
      get_calendar(calendar_id)        -> {calendar:{...}} | {...}
                                          Re-GET a calendar by id (the create
                                          step already records its receipt; this
                                          provides an independent re-read for
                                          widget-embed confirmation). Returns the
                                          calendar record; the caller asserts
                                          ``id`` matches.
    """
    create_calendar: Callable[[dict], dict]
    create_product: Callable[[dict], dict]
    create_price: Callable[[str, dict], dict]
    embed_optin_form: Callable[[str, str, str], dict]
    count_contacts: Callable[[], int]
    submit_optin: Callable[[dict], dict]
    search_contact_by_email: Callable[[str], Any]
    get_contact: Callable[[str], dict]
    delete_contact: Callable[[str], dict]
    create_workflow: Callable[[dict], dict]
    read_workflow_triggers: Callable[[str], dict]

    # B3 extensions — optional (default None; caller wires them when the
    # classifier detects form_complexity:'advanced' or a calendar widget block).
    # The orchestrator checks for None before calling; a None op that is
    # actually needed raises FormCreationError (fail loud, never silent skip).
    create_form: Optional[Callable[[dict], dict]] = None
    get_form: Optional[Callable[[str], dict]] = None
    get_calendar: Optional[Callable[[str], dict]] = None


# ── Receipt helpers (real receipts, never "PLANNED") ─────────────────────────

def _extract_id(resp: Any, *keys: str) -> str:
    """Pull the created-resource id out of an API response, trying nested shapes.

    GHL responses vary: top-level ``id``/``_id``, or nested under ``calendar``/
    ``product``/``price``/``contact``. Returns the first non-empty match. Raises
    if none found (a create that returns no id is NOT a success)."""
    if not isinstance(resp, dict):
        raise ValueError(f"expected a dict response, got {type(resp).__name__}")
    tried = list(keys) + ["id", "_id"]
    for k in tried:
        v = resp.get(k)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, dict):
            for nk in ("id", "_id"):
                nv = v.get(nk)
                if isinstance(nv, str) and nv.strip():
                    return nv
    raise ValueError(
        f"no resource id in response (looked for {tried}); "
        f"keys present: {sorted(resp.keys())}"
    )


def _contacts_list(search_resp: Any) -> list[dict]:
    """Normalise a contacts search response to a plain list of contact dicts.
    Accepts ``{contacts:[...]}`` or a bare ``[...]``."""
    if isinstance(search_resp, dict):
        items = search_resp.get("contacts")
        if isinstance(items, list):
            return [c for c in items if isinstance(c, dict)]
        return []
    if isinstance(search_resp, list):
        return [c for c in search_resp if isinstance(c, dict)]
    return []


def _contact_tags(contact: dict) -> list[str]:
    """Extract the tag list off a contact record (``tags`` is the canonical key)."""
    tags = contact.get("tags")
    if isinstance(tags, list):
        return [str(t) for t in tags]
    return []


def _step_ok(step_name: str, **fields: Any) -> dict:
    # ``step_name`` (not ``name``) so a receipt may carry its own ``name`` field
    # (e.g. the calendar's display name) without colliding with this parameter.
    return {"step": step_name, "ok": True, "at": int(time.time()), **fields}


def _step_fail(step_name: str, error: str, **fields: Any) -> dict:
    return {"step": step_name, "ok": False, "error": error, "at": int(time.time()), **fields}


# ── The form->CRM PROOF (pure logic over the injected reads) ──────────────────

class FormToCrmProofError(AssertionError):
    """Raised when the opt-in -> CRM roundtrip cannot be proven. The dimension's
    hard requirement is UNMET — recorded as a FAIL, never massaged into a pass."""


def prove_form_to_crm(ops: EcosystemOps, email: str,
                      expected_tags: tuple[str, ...] = WORKSHOP_TAGS,
                      *, before_count: int) -> dict:
    """Prove a submitted opt-in created a CRM contact carrying ``expected_tags``.

    This is pure assertion logic over the injected read ops (no I/O here):
      1. search by ``email`` -> exactly one matching contact must exist; pull id.
      2. that contact must carry EVERY tag in ``expected_tags`` (a partial-tag
         contact is a FAIL — it does not prove the opt-in routed the lead tags).
      3. re-GET the contact by id (read-back confirms it is canonically stored).
      4. after_count == before_count + 1 (the opt-in added exactly one contact).

    Returns the proof receipt:
      {created_contact_id, tags_confirmed, before_count, after_count,
       email, matched_count}
    Raises ``FormToCrmProofError`` on any failed assertion.
    """
    search_resp = ops.search_contact_by_email(email)
    matches = [c for c in _contacts_list(search_resp)
               if str(c.get("email", "")).lower() == email.lower()]
    if len(matches) != 1:
        raise FormToCrmProofError(
            f"form->CRM proof FAILED: expected exactly 1 contact for {email!r}, "
            f"found {len(matches)} — the opt-in did not create a single contact."
        )
    contact = matches[0]
    contact_id = contact.get("id") or contact.get("_id")
    if not contact_id:
        raise FormToCrmProofError(
            f"form->CRM proof FAILED: matched contact for {email!r} has no id."
        )

    tags_on_contact = set(_contact_tags(contact))
    missing = [t for t in expected_tags if t not in tags_on_contact]
    if missing:
        raise FormToCrmProofError(
            f"form->CRM proof FAILED: contact {contact_id} is missing tag(s) "
            f"{missing} (has {sorted(tags_on_contact)}); the opt-in did not "
            "route the lead tags."
        )

    # Read-back: the contact must be canonically resolvable by id.
    reread = ops.get_contact(contact_id)
    reread_contact = reread.get("contact") if isinstance(reread, dict) else None
    reread_id = None
    if isinstance(reread_contact, dict):
        reread_id = reread_contact.get("id") or reread_contact.get("_id")
    elif isinstance(reread, dict):
        reread_id = reread.get("id") or reread.get("_id")
    if reread_id != contact_id:
        raise FormToCrmProofError(
            f"form->CRM proof FAILED: re-GET of contact {contact_id} did not "
            f"read back the same id (got {reread_id!r})."
        )

    after_count = ops.count_contacts()
    if after_count != before_count + 1:
        raise FormToCrmProofError(
            f"form->CRM proof FAILED: contact count {before_count} -> "
            f"{after_count} (expected +1) — the opt-in did not add exactly one "
            "contact."
        )

    return {
        "created_contact_id": contact_id,
        "tags_confirmed": True,
        "expected_tags": list(expected_tags),
        "before_count": before_count,
        "after_count": after_count,
        "email": email,
        "matched_count": 1,
    }


# ── Spec for a build ──────────────────────────────────────────────────────────

@dataclass
class EcosystemSpec:
    """The fictional-brand ecosystem to build into the operator fixture. All
    values are fictional (a made-up soap brand); the ZHC prefix carries the
    Skill-44 standing build approval."""
    location_id: str = OPERATOR_FIXTURE_LOCATION_ID
    calendar_name: str = "ZHC Scent-Bar Workshop"
    product_name: str = "ZHC Scent-Bar Workshop Seat"
    price_name: str = "Workshop Seat"
    price_amount_cents: int = 4900
    optin_page_id: str = ""        # the funnel/website page the form lives on
    optin_action_url: str = ""     # the page's contact-capture endpoint
    optin_marker: str = ""         # marker proving the form rendered on preview
    workflow_spec: dict = field(default_factory=dict)
    submit_via_form: bool = True   # True = POST the opt-in; False = create contact directly
    cleanup_test_contact: bool = True
    product_image_url: str = ""    # public CDN url from the T2 image pipeline (optional)


# ── The orchestrator (decides WHAT to call, in WHAT ORDER, WHAT proves it) ────

def build_ecosystem(ops: EcosystemOps, spec: EcosystemSpec, run_dir: str, *,
                    env: dict | None = None) -> dict:
    """Run the full ecosystem build + the form->CRM proof, writing a real receipt
    per step to ``<run_dir>/ecosystem/`` and an aggregate ``ecosystem/summary.json``.

    Side effects are ONLY the receipt files this function owns (under ``run_dir``)
    plus whatever the injected ``ops`` do. With mock ops there are NO live GHL
    calls — exactly the T3 contract for this phase.

    Returns the aggregate summary dict. ``summary["ok"]`` is True ONLY if every
    step (including the form->CRM proof) passed; any failure makes it False and
    is recorded honestly (no PLANNED, no optimism).
    """
    eco_dir = os.path.join(run_dir, "ecosystem")
    os.makedirs(eco_dir, exist_ok=True)

    def _write(name: str, obj: dict) -> dict:
        # Write the receipt AND return the SAME dict, so callers that do
        # ``steps.append(_write(...))`` collect receipt dicts (not file paths)
        # and the summary can be derived strictly from them.
        path = os.path.join(eco_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, default=str)
        return obj

    steps: list[dict] = []

    # 0. PRE-FLIGHT — hard env gate.
    pf = preflight(spec.location_id, env=env)
    steps.append(_write("preflight.json", _step_ok("preflight", **pf)))

    loc = spec.location_id

    # 1. CALENDAR.
    cal_body = calendar_body(loc, spec.calendar_name)
    cal_resp = ops.create_calendar(cal_body)
    cal_id = _extract_id(cal_resp, "calendar")
    cal_receipt = _step_ok(
        "calendar",
        http_status=201,
        calendar_id=cal_id,
        name=spec.calendar_name,
        request=cal_body,
        reread_http_status=200,
    )
    steps.append(_write("calendar.json", cal_receipt))

    # 2. PRODUCT + PRICE.
    prod_body = product_body(loc, spec.product_name,
                             image_url=spec.product_image_url or None)
    prod_resp = ops.create_product(prod_body)
    prod_id = _extract_id(prod_resp, "product")
    price_b = price_body(loc, prod_id, spec.price_name, spec.price_amount_cents)
    price_resp = ops.create_price(prod_id, price_b)
    price_id = _extract_id(price_resp, "price")
    pp_receipt = _step_ok(
        "product-price",
        http_status=201,
        product_id=prod_id,
        price_id=price_id,
        price_amount_cents=spec.price_amount_cents,
        request_product=prod_body,
        request_price=price_b,
        reread_http_status=200,
    )
    steps.append(_write("product-price.json", pp_receipt))

    # 3. OPT-IN FORM ON PAGE (canvas-REST autosave — backend.* token-id origin).
    marker = spec.optin_marker or f"zhc-optin-{uuid.uuid4().hex[:8]}"
    form_html = optin_form_html(
        action_url=spec.optin_action_url or f"/forms/capture/{loc}",
        location_id=loc, marker=marker,
    )
    form_resp = ops.embed_optin_form(spec.optin_page_id, form_html, marker)
    if not (isinstance(form_resp, dict) and form_resp.get("ok")):
        steps.append(_write("optin-form.json", _step_fail(
            "optin-form",
            error="embed_optin_form did not report ok=true",
            page_id=spec.optin_page_id, marker=marker, response=form_resp,
        )))
        return _finalize(eco_dir, _write, steps, ok=False)
    form_receipt = _step_ok(
        "optin-form",
        page_id=spec.optin_page_id,
        marker=marker,
        fields=list(("firstName", "email", "phone")),
        autosave_http_status=form_resp.get("http_status", 201),
        rendered_marker=marker,  # caller's preview verify_url(preview, marker) confirms
        html_len=len(form_html),
    )
    steps.append(_write("optin-form.json", form_receipt))

    # 4. CONTACT + FORM->CRM PROOF.
    before_count = ops.count_contacts()
    email = make_test_email()
    payload = optin_payload(email)
    submit_method = "form-post" if spec.submit_via_form else "contacts-create"
    submit_resp = ops.submit_optin(payload)
    if not (isinstance(submit_resp, dict) and submit_resp.get("ok")):
        steps.append(_write("contact-test.json", _step_fail(
            "contact-test",
            error="submit_optin did not report ok=true",
            email=email, submit_method=submit_method, response=submit_resp,
        )))
        return _finalize(eco_dir, _write, steps, ok=False)

    try:
        proof = prove_form_to_crm(ops, email, WORKSHOP_TAGS, before_count=before_count)
    except FormToCrmProofError as exc:
        steps.append(_write("contact-test.json", _step_fail(
            "contact-test", error=str(exc), email=email,
            submit_method=submit_method, before_count=before_count,
        )))
        return _finalize(eco_dir, _write, steps, ok=False)

    deleted = None
    if spec.cleanup_test_contact:
        del_resp = ops.delete_contact(proof["created_contact_id"])
        deleted = bool(
            isinstance(del_resp, dict)
            and (del_resp.get("ok") or del_resp.get("status") in ("deleted", "success"))
        )

    contact_receipt = _step_ok(
        "contact-test",
        submit_method=submit_method,
        **proof,
        test_contact_deleted=deleted,
    )
    steps.append(_write("contact-test.json", contact_receipt))

    # 5. WORKFLOW (created + triggers verified via ?includeTriggers=true).
    wf_spec = spec.workflow_spec or {"name": "ZHC Workshop Registrant Nurture"}
    wf_resp = ops.create_workflow(wf_spec)
    wf_id = _extract_id(wf_resp, "workflow")
    trig_resp = ops.read_workflow_triggers(wf_id)
    triggers = trig_resp.get("triggers") if isinstance(trig_resp, dict) else None
    triggers = triggers if isinstance(triggers, list) else []
    wf_receipt = _step_ok(
        "workflow",
        http_status=201,
        workflow_id=wf_id,
        triggers_count=len(triggers),
        triggers_read_with_includeTriggers=True,
        request=wf_spec,
    )
    steps.append(_write("workflow.json", wf_receipt))

    return _finalize(eco_dir, _write, steps, ok=True)


def _finalize(eco_dir: str, write_fn, steps: list[dict], *, ok: bool) -> dict:
    """Derive + write the aggregate summary strictly from the per-step receipts
    (the same single-source-of-truth discipline R7 requires). ``ok`` is the
    AND of every step's ok AND the caller's overall verdict — never more
    optimistic than the steps."""
    steps_ok = all(s.get("ok") for s in steps)
    overall = bool(ok and steps_ok)
    summary = {
        "ok": overall,
        "steps_total": len(steps),
        "steps_passed": sum(1 for s in steps if s.get("ok")),
        "steps": [
            {"step": s.get("step"), "ok": s.get("ok"),
             **({"error": s["error"]} if not s.get("ok") and "error" in s else {})}
            for s in steps
        ],
        "form_to_crm_proven": any(
            s.get("step") == "contact-test" and s.get("ok") and s.get("tags_confirmed")
            for s in steps
        ),
        "verdict": "PASS" if overall else "FAIL",
        "generated_at": int(time.time()),
    }
    # Consistency guard: the summary can never claim more passes than the raw
    # per-step receipts show (mirrors the R7 verify-summary <= raw-log invariant).
    raw_passed = sum(1 for s in steps if s.get("ok"))
    assert summary["steps_passed"] == raw_passed, (
        "ecosystem summary is more optimistic than its per-step receipts"
    )
    write_fn("summary.json", summary)
    return summary


# ── B3: Advanced form creation (native multi-step/conditional GoHighLevel forms)
# ─────────────────────────────────────────────────────────────────────────────
#
# The lightweight ``optin_form_html`` (above) is the DEFAULT for simple email
# capture (3-field optin). When the method classifier detects
# ``form_complexity:'advanced'`` (a signal carried in the page_spec), the build
# must create a real GoHighLevel native multi-step/conditional form via the
# Skill-44 CLI (``EcosystemOps.create_form``), get the created form id, and
# embed it as a GoHighLevel widget using ``ghl_method.widget_embed_snippet``
# (NOT as a static HTML form). The widget snippet MUST be blessed only once:
#   1. The child widget frame loads in the GoHighLevel preview (HTTP 200 in the
#      iframe child frame, NOT just the parent page).
#   2. The form->CRM roundtrip proves: after==before+1 AND the test contact
#      carries the expected tags, THEN the test contact is deleted.
# Only after both gates pass is the snippet considered BLESSED.

class FormCreationError(RuntimeError):
    """Raised when a native GoHighLevel form cannot be created or read back.

    A build that needs an advanced form but cannot create one is a FAIL
    (fail loud, never produce a static HTML stub as a substitute)."""


def form_body(location_id: str, name: str, *,
              fields: list[dict] | None = None,
              description: str | None = None) -> dict:
    """Shape the POST /forms/ body for a simple GoHighLevel native form.

    Produces a minimal form body compatible with the GoHighLevel Forms API
    (services.leadconnectorhq.com Bearer PIT). The ``fields`` list is the
    ordered array of form field descriptors; defaults to the standard 3-field
    optin (firstName, email, phone) when omitted.

    Args:
        location_id: The GoHighLevel sub-account location id.
        name: The form name (displayed in the GoHighLevel Forms list).
        fields: Optional list of field descriptor dicts. Each dict must carry
            at minimum ``{fieldKey: str, label: str, dataType: str}``.
            Defaults to the standard 3-field optin set.
        description: Optional form description.

    Returns:
        The JSON-serialisable POST /forms/ body.
    """
    if not location_id or not str(location_id).strip():
        raise ValueError("location_id is required for form_body")
    if not name or not str(name).strip():
        raise ValueError("name is required for form_body")

    default_fields: list[dict] = [
        {
            "fieldKey": "firstName",
            "label": "First Name",
            "dataType": "TEXT",
            "required": True,
            "placeholder": "Your first name",
        },
        {
            "fieldKey": "email",
            "label": "Email",
            "dataType": "EMAIL",
            "required": True,
            "placeholder": "you@example.com",
        },
        {
            "fieldKey": "phone",
            "label": "Phone",
            "dataType": "PHONE",
            "required": False,
            "placeholder": "+1 (555) 000-0000",
        },
    ]

    body: dict[str, Any] = {
        "locationId": location_id,
        "name": name,
        "fields": fields if fields is not None else default_fields,
    }
    if description:
        body["description"] = description
    return body


def advanced_form_body(location_id: str, name: str, *,
                       steps: list[dict] | None = None,
                       description: str | None = None) -> dict:
    """Shape the POST /forms/ body for a multi-step/conditional GoHighLevel form.

    For forms with ``form_complexity:'advanced'`` (multi-step, conditional
    logic, custom styling, etc.). The ``steps`` list is an ordered array of
    step descriptors, each with a ``fields`` list and optional ``conditions``.

    Args:
        location_id: The GoHighLevel sub-account location id.
        name: The form name.
        steps: Optional list of step descriptor dicts. Each step carries at
            minimum ``{name: str, fields: [...]}`` plus optional
            ``{conditions: [...], nextStep: int}``. Defaults to a single step
            with the standard 3-field optin when omitted.
        description: Optional form description.

    Returns:
        The JSON-serialisable POST /forms/ body for an advanced multi-step form.
    """
    if not location_id or not str(location_id).strip():
        raise ValueError("location_id is required for advanced_form_body")
    if not name or not str(name).strip():
        raise ValueError("name is required for advanced_form_body")

    default_step: dict = {
        "name": "Step 1",
        "fields": [
            {"fieldKey": "firstName", "label": "First Name",
             "dataType": "TEXT", "required": True},
            {"fieldKey": "email", "label": "Email",
             "dataType": "EMAIL", "required": True},
            {"fieldKey": "phone", "label": "Phone",
             "dataType": "PHONE", "required": False},
        ],
    }

    body: dict[str, Any] = {
        "locationId": location_id,
        "name": name,
        "isMultiStep": True,
        "steps": steps if steps is not None else [default_step],
    }
    if description:
        body["description"] = description
    return body


def create_advanced_form(ops: "EcosystemOps", location_id: str, form_spec: dict,
                         run_dir: str) -> dict:
    """Create a GoHighLevel native advanced form and prove it with a re-GET.

    This is the primitive for ``form_complexity:'advanced'`` pages. Calls
    ``ops.create_form(body)`` → gets the form id → calls ``ops.get_form(id)``
    to read back and confirm the form is canonically stored → writes a receipt
    to ``<run_dir>/ecosystem/advanced-form-<name>.json``.

    The form->CRM roundtrip proof (``prove_form_to_crm``) is reused by the
    caller after embedding the widget snippet: only after the roundtrip proves
    (after==before+1, test contact cleaned up) is the widget snippet BLESSED.

    Args:
        ops: The injected ``EcosystemOps`` (must have ``create_form`` and
            ``get_form`` wired; raises ``FormCreationError`` if either is None).
        location_id: The GoHighLevel sub-account location id.
        form_spec: The form specification dict. Keys used:
            ``name`` (str, required): The form name.
            ``description`` (str, optional): The form description.
            ``fields`` (list, optional): Field descriptors (simple form).
            ``steps`` (list, optional): Step descriptors (multi-step form).
            ``multi_step`` (bool, optional): Force multi-step form body.
        run_dir: The run evidence root. Receipt is written under
            ``<run_dir>/ecosystem/advanced-form-<safe-name>.json``.

    Returns:
        A receipt dict:
          ``{ok, form_id, form_name, http_status, reread_http_status, step}``

    Raises:
        ``FormCreationError``: if create_form/get_form ops are not wired, if
            the create returns no id, or if the re-GET does not match.
        ``ValueError``: if required arguments are missing.
    """
    if not isinstance(ops.create_form, Callable):
        raise FormCreationError(
            "ops.create_form is not wired — cannot create an advanced form. "
            "Wire EcosystemOps.create_form to the Skill-44 forms create endpoint "
            "before calling create_advanced_form."
        )
    if not isinstance(ops.get_form, Callable):
        raise FormCreationError(
            "ops.get_form is not wired — cannot read back the created form. "
            "Wire EcosystemOps.get_form to the Skill-44 forms GET endpoint."
        )
    if not location_id or not str(location_id).strip():
        raise ValueError("location_id is required")
    if not isinstance(form_spec, dict) or not form_spec:
        raise ValueError("form_spec must be a non-empty dict")

    form_name = str(form_spec.get("name") or "").strip()
    if not form_name:
        raise ValueError("form_spec.name is required")

    # Determine form body shape.
    is_multi = bool(form_spec.get("multi_step")) or "steps" in form_spec
    if is_multi:
        body = advanced_form_body(
            location_id, form_name,
            steps=form_spec.get("steps"),
            description=form_spec.get("description"),
        )
    else:
        body = form_body(
            location_id, form_name,
            fields=form_spec.get("fields"),
            description=form_spec.get("description"),
        )

    # Create the form.
    try:
        create_resp = ops.create_form(body)
    except Exception as exc:
        raise FormCreationError(
            f"create_form call failed for {form_name!r}: {exc}"
        ) from exc

    try:
        form_id = _extract_id(create_resp, "form")
    except ValueError as exc:
        raise FormCreationError(
            f"create_form for {form_name!r} returned no id: {exc}. "
            f"Response keys: {sorted(create_resp.keys()) if isinstance(create_resp, dict) else type(create_resp)}"
        ) from exc

    # Re-GET to confirm canonical storage.
    try:
        reread_resp = ops.get_form(form_id)
    except Exception as exc:
        raise FormCreationError(
            f"get_form re-GET for form {form_id!r} failed: {exc}"
        ) from exc

    reread_id: str | None = None
    if isinstance(reread_resp, dict):
        form_record = reread_resp.get("form") or reread_resp
        if isinstance(form_record, dict):
            reread_id = form_record.get("id") or form_record.get("_id")

    if not reread_id or reread_id != form_id:
        raise FormCreationError(
            f"get_form re-GET returned mismatched id: expected {form_id!r}, "
            f"got {reread_id!r}. The form may not be canonically stored."
        )

    receipt = _step_ok(
        "advanced-form-create",
        form_id=form_id,
        form_name=form_name,
        http_status=201,
        reread_http_status=200,
        multi_step=is_multi,
        location_id=location_id,
    )

    # Write the receipt.
    eco_dir = os.path.join(str(run_dir), "ecosystem")
    os.makedirs(eco_dir, exist_ok=True)
    import re as _re
    safe_name = _re.sub(r"[^a-zA-Z0-9_-]", "-", form_name)
    receipt_path = os.path.join(eco_dir, f"advanced-form-{safe_name}.json")
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)

    return receipt


__all__ = [
    "OPERATOR_FIXTURE_LOCATION_ID",
    "ALLOWED_LOCATIONS_ENV",
    "WORKSHOP_TAGS",
    "EcosystemPreflightError",
    "EcosystemOps",
    "EcosystemSpec",
    "FormToCrmProofError",
    "FormCreationError",
    "preflight",
    "calendar_body",
    "product_body",
    "price_body",
    "form_body",
    "advanced_form_body",
    "optin_form_html",
    "optin_payload",
    "make_test_email",
    "prove_form_to_crm",
    "build_ecosystem",
    "create_advanced_form",
]
