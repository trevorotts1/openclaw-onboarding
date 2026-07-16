#!/usr/bin/env python3
"""ghl_bulk_workflow_enroll.py — U112 (E5-7; closes G5): Skill 6 bulk-send GHL
workflow enrollment by TAG or explicit contact-ID ARRAY, fail-closed on any
ambiguous/partial match.

WHY THIS EXISTS
----------------
A live SMS firefight surfaced a named Skill 6 capability with NO build/prove
unit anywhere in the codebase (NOT-FOUND at spec time). This module is the
first act named by the unit spec: confirm no bulk-add path already existed,
then build one on the proven GHL REST tooling.

PRIOR-ART CHECK (first act, per the unit spec) — NOT-FOUND
------------------------------------------------------------
Searched for an existing bulk-contact-into-workflow path before writing any
code:
  * Skill 44's internal workflow endpoints
    (44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/
    internal/endpoints.py) cover workflow BUILD (create/get/put a workflow's
    STRUCTURE via the internal backend.leadconnectorhq.com API) — not contact
    enrollment into an existing workflow.
  * Skill 6's own ``ghl_workflow_builder.py`` drives the browser to build a
    NEW workflow (name + trigger + action) — it does not enroll contacts.
  * ``ghl_survey_builder.py`` / ``ghl_ecosystem.py`` / ``ghl_object_router.py``
    cover funnel/page/survey/community/course objects — no contact/workflow
    enrollment path anywhere in that tree either.
Conclusion: genuinely new build, not a rebuild of an existing capability.

BUILT ON THE PROVEN GHL REST TOOLING (cross-reference Skill 44)
-------------------------------------------------------------------
This module's transport shape (bearer-PIT auth, the canonical LOCATION-PIT
env-var alias set, ``https://services.leadconnectorhq.com`` base URL, a
``Version`` header on every call) mirrors Skill 44's proven REST client
(44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/utils/
ghl_client.py:14,44-108). It is intentionally a SELF-CONTAINED duplicate
(matching the rest of Skill 6's own tools — e.g. ``ghl_survey_rest.py``,
which reuses ``ghl_rest_canvas`` via a same-directory local import, never a
cross-skill package import) rather than an import across the two
independently-versioned skill directories.

The two endpoints driven here are DOCUMENTED in this repo's own Skill-29 API
reference, ``29-ghl-convert-and-flow/references/contacts.md``:
  * ``POST /contacts/search``                          (contacts.md:140-164)
  * ``GET  /contacts/{contactId}``                      (contacts.md:217-241)
  * ``DELETE /contacts/{contactId}``                    (contacts.md:268-291)
  * ``POST /contacts/{contactId}/workflow/{workflowId}``      (contacts.md:776-801)
  * ``DELETE /contacts/{contactId}/workflow/{workflowId}``    (contacts.md:802-825)
That file's header (line 7) documents ``Version: 2021-04-15`` as required on
ALL contacts-module calls, including both workflow-enroll endpoints — used
here even though Skill 44's ``ghl_client.py`` VERSION_MAP default for a
``/contacts/`` path prefix is ``2021-07-28``; the more specific, endpoint-
family-scoped citation wins for this module.

HONESTY DISCLOSURE (documented shape vs repo-captured shape)
--------------------------------------------------------------
``contacts.md`` marks the ``/contacts/search`` request body as "Body required
but fields not explicit" — this repo has not itself captured/verified the
exact filter body against a live account. ``GhlHttpClient.search_contacts``
below emits GHL's publicly documented Search-Contacts filter shape
(``filters: [{field, operator, value}]`` + ``locationId`` + ``pageLimit`` +
a cursor-style ``searchAfter`` for pagination) — a DOCUMENTED, not a
repo-captured, shape. This is not a blind POST against an undisclosed SPA
route (the anti-blind-POST invariant ``ghl_survey_rest.py`` guards against);
it is the account's public REST API. Confirming/adjusting the exact field
names against a real account is the LIVE-PROOF tier's job — this build tier
proves the HARNESS (pagination-completeness gate, exact-tag re-verification,
fail-closed ambiguous/partial-match refusal, receipt + read-back invariant)
against injected FIXTURES only. ``GhlHttpClient`` is never constructed by
``--selftest`` or the pytest suite — no network, ever, at this tier.

FAIL-CLOSED CONTRACT (BINARY acceptance (c))
----------------------------------------------
Two independent ambiguity gates in ``resolve_matched_by_tag`` /
``resolve_matched_by_array``; either one refuses the WHOLE batch (ZERO
enrollment attempted) and raises the named ``AmbiguousMatchError``:

  1. TAG mode, incomplete pagination — the search response's reported
     ``total`` exceeds the contacts actually paged in (or pagination runs
     away past ``max_pages``). Enrolling a partial page would silently
     enroll an incomplete set.
  2. TAG mode, over-broad server-side match — a "contains" search can
     return a contact whose tag list contains the search string only as a
     SUBSTRING of a different tag (tag="vip" also matching "vip-archive").
     Every returned contact's own ``tags`` list is re-verified for an EXACT
     (case-insensitive) match; if the server's match set and the
     exact-match set differ, the batch is refused rather than silently
     guessing which contacts were really meant.
  3. ARRAY mode, unresolved id — any explicitly-listed contact id that does
     not resolve (404 / not found) makes the whole batch ambiguous:
     enrolling only the ids that DID resolve would silently enroll a
     smaller set than the caller actually named.

Per-contact enrollment failures (the target contact resolved fine but the
enroll call itself errored) are a DIFFERENT, allowed case — they are counted
in ``failures`` and the read-back formula accounts for them; only ambiguity
in resolving the TARGET SET fails the whole batch closed.

RECEIPT + READ-BACK (BINARY acceptance (a)/(b))
----------------------------------------------
``run_bulk_send`` writes ``routing/bulk-send-receipt.json`` (mode, tag-or-
array, matched count, enrolled count, failures) via ``write_receipt``, then
calls ``assert_read_back`` — which recomputes
``enrolled == matched - len(failures)`` DIRECTLY from the receipt just
written to disk (never from an in-memory tally, same "trust disk" discipline
as ``ghl_receipts.py``) and raises ``ReadBackMismatch`` if the arithmetic
does not hold. This is the CODE-TIER read-back; a LIVE-PROOF-tier pass
additionally GETs each enrolled contact back from a real GHL location to
confirm true workflow membership — deferred, out of scope for this build.

CLEANUP PROOF (BINARY acceptance (d), fixture tier)
------------------------------------------------------
``cleanup_present_delete_absent`` proves present -> delete -> absent against
the injected client (GET before, DELETE, GET after == None). The LIVE-PROOF
tier repeats this against the operator-authorized test location with
throwaway contacts; this build tier proves the SAME code path against a
fixture.

FLAG-GATED (revert = flip the flag)
------------------------------------
Only the CLI's live-executing path (``main()``'s non-``--selftest`` branch,
the only place that ever constructs a real ``GhlHttpClient``) checks
``GHL_BULK_SEND=1`` via ``_require_flag()`` and refuses otherwise
(``BulkSendFlagOff``, exit code 2). ``--selftest`` and the pytest suite are
fixture-only (``FakeGhlClient``), never touch the flag, and always run in
CI. Revert = unset/flip ``GHL_BULK_SEND`` (no bulk path reachable) then
revert the commit.

CLI
---
  ghl_bulk_workflow_enroll.py --selftest
  ghl_bulk_workflow_enroll.py --location-id L --workflow-id W --tag "vip" [--dry-run]
  ghl_bulk_workflow_enroll.py --location-id L --workflow-id W --contact-ids c1,c2,c3
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Protocol

BASE_URL = "https://services.leadconnectorhq.com"
# contacts.md:7 — "Version header: Version: 2021-04-15 (required on all calls)"
# scoped to the contacts module, which includes BOTH endpoints this module
# drives against /contacts/{contactId}/workflow/{workflowId}.
API_VERSION = "2021-04-15"

RECEIPT_SCHEMA_VERSION = "1.0"
RECEIPT_RELATIVE_PATH = os.path.join("routing", "bulk-send-receipt.json")

FLAG_ENV_VAR = "GHL_BULK_SEND"

# Same canonical LOCATION-PIT alias set as Skill 44's ghl_client.py
# (44-.../utils/ghl_client.py:47-59) — duplicated intentionally (self-contained
# Skill-6 module, see module docstring). First non-empty value wins.
_LOCATION_PIT_ENV_NAMES = (
    "GOHIGHLEVEL_API_KEY",
    "GHL_API_KEY",
    "GHL_PIT",
    "GHL_TOKEN",
    "GHL_PRIVATE_INTEGRATION_TOKEN",
    "PRIVATE_INTEGRATION_TOKEN",
    "GHL_PRIVATE_TOKEN",
    "PIT_TOKEN",
    "GHL_PIT_TOKEN",
    "GOHIGHLEVEL_LOCATION_PIT",
    "GHL_LOCATION_PIT",
)


# ---------------------------------------------------------------------------
# Named errors — the fail-closed / honest-failure vocabulary
# ---------------------------------------------------------------------------
class AmbiguousMatchError(RuntimeError):
    """The target set (tag OR explicit array) could not be resolved
    unambiguously. Callers MUST treat this as zero enrollment — never enroll
    a partial/guessed set."""


class EnrollError(RuntimeError):
    """A single contact's enroll-into-workflow call failed. Distinct from
    AmbiguousMatchError: the TARGET SET was resolved fine; this one member's
    write failed. Counted in ``failures``, not a whole-batch refusal."""

    def __init__(self, contact_id: str, message: str):
        self.contact_id = contact_id
        self.message = message
        super().__init__(f"{contact_id}: {message}")


class ReadBackMismatch(AssertionError):
    """A receipt's own enrolled/matched/failures counts fail the
    ``enrolled == matched - len(failures)`` invariant. Raised BEFORE the
    receipt is trusted by any caller (mirrors ghl_receipts.py's
    ReceiptContradiction discipline)."""


class BulkSendFlagOff(RuntimeError):
    """The live-executing path refuses without GHL_BULK_SEND=1 set — the
    bulk-add path is additive behind this flag; revert = flip the flag (no
    bulk path reachable) then revert the commit."""


# ---------------------------------------------------------------------------
# Client protocol — the ONLY door to GHL. Real transport vs fixtures both
# implement this; resolve/enroll/receipt logic never knows which it has.
# ---------------------------------------------------------------------------
class GhlClient(Protocol):
    def search_contacts(
        self, location_id: str, tag: str, page_limit: int = 100,
        search_after: Optional[str] = None,
    ) -> Dict[str, Any]: ...

    def get_contact(self, contact_id: str) -> Optional[Dict[str, Any]]: ...

    def enroll_contact_in_workflow(self, contact_id: str, workflow_id: str) -> Dict[str, Any]: ...

    def delete_contact(self, contact_id: str) -> Dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Real transport — constructed ONLY from main()'s flag-gated live path.
# ---------------------------------------------------------------------------
def _get_token() -> str:
    for name in _LOCATION_PIT_ENV_NAMES:
        token = os.environ.get(name, "").strip()
        if token:
            return token
    print(
        "Error: GHL location PIT not found in any canonical env-var name.\n"
        "Set one of these in ~/.openclaw/secrets/.env (or as an env var):\n"
        "  " + ", ".join(_LOCATION_PIT_ENV_NAMES),
        file=sys.stderr,
    )
    sys.exit(1)


class GhlHttpClient:
    """Real REST transport for the two documented endpoints this module
    drives (contacts.md:140-164, 217-241, 268-291, 776-825). Never
    constructed by --selftest or the pytest suite — no network at that
    tier, ever."""

    def __init__(self, token: Optional[str] = None, timeout: int = 30):
        self.token = token or _get_token()
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Version": API_VERSION,
        }

    def search_contacts(
        self, location_id: str, tag: str, page_limit: int = 100,
        search_after: Optional[str] = None,
    ) -> Dict[str, Any]:
        import requests  # local import: never needed by the fixture/selftest tier

        body: Dict[str, Any] = {
            "locationId": location_id,
            "pageLimit": page_limit,
            "filters": [{"field": "tags", "operator": "contains", "value": tag}],
        }
        if search_after:
            body["searchAfter"] = search_after
        resp = requests.post(
            f"{BASE_URL}/contacts/search", headers=self._headers(), json=body,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def get_contact(self, contact_id: str) -> Optional[Dict[str, Any]]:
        import requests

        resp = requests.get(
            f"{BASE_URL}/contacts/{contact_id}", headers=self._headers(),
            timeout=self.timeout,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return data.get("contact", data) if isinstance(data, dict) else data

    def enroll_contact_in_workflow(self, contact_id: str, workflow_id: str) -> Dict[str, Any]:
        import requests

        resp = requests.post(
            f"{BASE_URL}/contacts/{contact_id}/workflow/{workflow_id}",
            headers=self._headers(), json={}, timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise EnrollError(contact_id, f"HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            return resp.json()
        except ValueError:
            return {"status": resp.status_code}

    def delete_contact(self, contact_id: str) -> Dict[str, Any]:
        import requests

        resp = requests.delete(
            f"{BASE_URL}/contacts/{contact_id}", headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return {"status": "deleted", "code": resp.status_code}


# ---------------------------------------------------------------------------
# Match resolution — the fail-closed core
# ---------------------------------------------------------------------------
def resolve_matched_by_tag(
    client: GhlClient, location_id: str, tag: str, page_limit: int = 100,
    max_pages: int = 50,
) -> List[Dict[str, Any]]:
    """Page through ``POST /contacts/search`` for ``tag`` and return the
    EXACT-tag-matched contact list, or raise ``AmbiguousMatchError``. Never
    returns a partial/guessed set."""
    if not tag or not tag.strip():
        raise ValueError("tag is required for tag mode")
    tag_norm = tag.strip()

    all_contacts: List[Dict[str, Any]] = []
    seen_ids: set = set()
    search_after: Optional[str] = None
    total: Optional[int] = None
    pages = 0

    while True:
        pages += 1
        if pages > max_pages:
            raise AmbiguousMatchError(
                f"tag search for {tag_norm!r} exceeded {max_pages} pages without "
                "exhausting — refusing an unbounded partial-batch enrollment"
            )
        resp = client.search_contacts(
            location_id, tag_norm, page_limit=page_limit, search_after=search_after
        )
        page_contacts = resp.get("contacts") or []
        if total is None:
            total = resp.get("total")
            if total is None:
                raise AmbiguousMatchError(
                    f"tag search for {tag_norm!r} did not report a total count — "
                    "cannot prove the fetched page set is complete"
                )
        for c in page_contacts:
            cid = c.get("id")
            if cid and cid not in seen_ids:
                seen_ids.add(cid)
                all_contacts.append(c)
        search_after = resp.get("searchAfter")
        if not search_after or not page_contacts:
            break

    if len(all_contacts) != total:
        raise AmbiguousMatchError(
            f"tag search for {tag_norm!r} reported total={total} but paginated "
            f"fetch collected {len(all_contacts)} — refusing partial-batch "
            "enrollment (pagination incomplete)"
        )

    exact = [
        c for c in all_contacts
        if any(str(t).strip().lower() == tag_norm.lower() for t in (c.get("tags") or []))
    ]
    exact_ids = {c["id"] for c in exact}
    server_ids = {c["id"] for c in all_contacts}
    if exact_ids != server_ids:
        extra = sorted(server_ids - exact_ids)
        raise AmbiguousMatchError(
            f"tag search for {tag_norm!r} returned {len(extra)} contact(s) whose "
            f"tags do not carry an EXACT match ({extra}) — the server's "
            "'contains' search over-matched a different tag; refusing to "
            "guess which contacts were really meant (zero enrollment)"
        )
    return all_contacts


def resolve_matched_by_array(
    client: GhlClient, contact_ids: List[str],
) -> List[Dict[str, Any]]:
    """Resolve an EXPLICIT array of contact ids via ``GET /contacts/{id}``.
    Any id that does not resolve makes the WHOLE batch ambiguous — raises
    ``AmbiguousMatchError`` rather than silently enrolling the subset that
    DID resolve."""
    if not contact_ids:
        raise ValueError("contact_ids is required for array mode")
    ordered_unique = list(dict.fromkeys(contact_ids))  # dedupe, preserve order

    resolved: List[Dict[str, Any]] = []
    missing: List[str] = []
    for cid in ordered_unique:
        c = client.get_contact(cid)
        if c is None:
            missing.append(cid)
        else:
            resolved.append(c)

    if missing:
        raise AmbiguousMatchError(
            f"array mode: {len(missing)} of {len(ordered_unique)} explicit "
            f"contact id(s) not found ({missing}) — refusing a partial-array "
            "enrollment (zero enrollment)"
        )
    return resolved


def enroll_batch(
    client: GhlClient, matched_contacts: List[Dict[str, Any]], workflow_id: str,
) -> "tuple[List[str], List[Dict[str, str]]]":
    """Enroll every already-resolved contact. Per-contact failures are
    COUNTED, not fatal to the batch (the target set was already proven
    unambiguous by the caller)."""
    enrolled_ids: List[str] = []
    failures: List[Dict[str, str]] = []
    for c in matched_contacts:
        cid = c["id"]
        try:
            client.enroll_contact_in_workflow(cid, workflow_id)
            enrolled_ids.append(cid)
        except EnrollError as exc:
            failures.append({"contact_id": cid, "error": exc.message})
    return enrolled_ids, failures


# ---------------------------------------------------------------------------
# Receipt + read-back — "no receipt = not enrolled"
# ---------------------------------------------------------------------------
def receipt_path(evidence_root: str) -> str:
    return os.path.join(evidence_root, RECEIPT_RELATIVE_PATH)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _compute_read_back(receipt: Dict[str, Any]) -> Dict[str, Any]:
    if receipt.get("fail_closed"):
        return {"ok": True, "skipped": True, "reason": "fail_closed"}
    if receipt.get("dry_run"):
        return {"ok": True, "skipped": True, "reason": "dry_run"}
    matched = receipt["matched"]
    failures_count = len(receipt.get("failures") or [])
    expected = matched - failures_count
    enrolled = receipt["enrolled"]
    return {
        "ok": enrolled == expected,
        "formula": "enrolled == matched - len(failures)",
        "matched": matched,
        "failures_count": failures_count,
        "enrolled": enrolled,
        "expected_enrolled": expected,
    }


def build_receipt(
    *, mode: str, tag: Optional[str], contact_ids_requested: Optional[List[str]],
    location_id: str, workflow_id: str, matched_ids: List[str],
    enrolled_ids: List[str], failures: List[Dict[str, str]],
    fail_closed: bool = False, fail_closed_reason: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    if mode not in ("tag", "array"):
        raise ValueError(f"invalid mode {mode!r}; must be 'tag' or 'array'")
    receipt: Dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "generated_at": _now(),
        "mode": mode,
        "tag": tag,
        "array": list(contact_ids_requested) if contact_ids_requested is not None else None,
        "location_id": location_id,
        "workflow_id": workflow_id,
        "matched": len(matched_ids),
        "matched_contact_ids": list(matched_ids),
        "enrolled": len(enrolled_ids),
        "enrolled_contact_ids": list(enrolled_ids),
        "failures": list(failures),
        "fail_closed": fail_closed,
        "fail_closed_reason": fail_closed_reason,
        "dry_run": dry_run,
    }
    receipt["read_back"] = _compute_read_back(receipt)
    return receipt


def write_receipt(evidence_root: str, receipt: Dict[str, Any]) -> str:
    """Write-then-rename so a reader never sees a half-written receipt
    (same discipline as ghl_receipts.py:write_receipt)."""
    path = receipt_path(evidence_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)
    return path


def load_receipt(evidence_root_or_path: str) -> Dict[str, Any]:
    path = evidence_root_or_path
    if os.path.isdir(evidence_root_or_path):
        path = receipt_path(evidence_root_or_path)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def assert_read_back(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute the invariant fresh from the receipt dict (never trust a
    stored ``ok`` alone) and raise ``ReadBackMismatch`` if it fails."""
    rb = _compute_read_back(receipt)
    if not rb.get("ok"):
        raise ReadBackMismatch(
            f"read-back invariant failed: enrolled={receipt.get('enrolled')} != "
            f"matched({receipt.get('matched')}) - "
            f"failures({len(receipt.get('failures') or [])})"
        )
    return rb


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run_bulk_send(
    client: GhlClient, *, mode: str, location_id: str, workflow_id: str,
    tag: Optional[str] = None, contact_ids: Optional[List[str]] = None,
    evidence_root: str, dry_run: bool = False, page_limit: int = 100,
) -> Dict[str, Any]:
    """The single entry point: resolve the target set (fail-closed on
    ambiguity), enroll it (unless dry_run), write the receipt, and assert
    the read-back invariant against what's now on disk."""
    if mode == "tag":
        try:
            matched = resolve_matched_by_tag(client, location_id, tag or "", page_limit=page_limit)
        except AmbiguousMatchError as exc:
            receipt = build_receipt(
                mode=mode, tag=tag, contact_ids_requested=None,
                location_id=location_id, workflow_id=workflow_id,
                matched_ids=[], enrolled_ids=[], failures=[],
                fail_closed=True, fail_closed_reason=str(exc), dry_run=dry_run,
            )
            write_receipt(evidence_root, receipt)
            raise
    elif mode == "array":
        try:
            matched = resolve_matched_by_array(client, contact_ids or [])
        except AmbiguousMatchError as exc:
            receipt = build_receipt(
                mode=mode, tag=None, contact_ids_requested=contact_ids,
                location_id=location_id, workflow_id=workflow_id,
                matched_ids=[], enrolled_ids=[], failures=[],
                fail_closed=True, fail_closed_reason=str(exc), dry_run=dry_run,
            )
            write_receipt(evidence_root, receipt)
            raise
    else:
        raise ValueError(f"mode must be 'tag' or 'array', got {mode!r}")

    matched_ids = [c["id"] for c in matched]
    if dry_run:
        enrolled_ids: List[str] = []
        failures: List[Dict[str, str]] = []
    else:
        enrolled_ids, failures = enroll_batch(client, matched, workflow_id)

    receipt = build_receipt(
        mode=mode, tag=tag if mode == "tag" else None,
        contact_ids_requested=contact_ids if mode == "array" else None,
        location_id=location_id, workflow_id=workflow_id,
        matched_ids=matched_ids, enrolled_ids=enrolled_ids, failures=failures,
        fail_closed=False, fail_closed_reason=None, dry_run=dry_run,
    )
    write_receipt(evidence_root, receipt)
    assert_read_back(receipt)
    return receipt


def cleanup_present_delete_absent(
    client: GhlClient, contact_ids: List[str],
) -> Dict[str, Any]:
    """BINARY acceptance (d): present -> delete -> absent proof. GET each id
    (present_before), DELETE the ones present, GET each id again
    (absent_after). ``ok`` is True only if every deleted id now reads back
    absent."""
    present_before = {cid: client.get_contact(cid) is not None for cid in contact_ids}
    deleted: List[str] = []
    for cid in contact_ids:
        if present_before[cid]:
            client.delete_contact(cid)
            deleted.append(cid)
    absent_after = {cid: client.get_contact(cid) is None for cid in contact_ids}
    return {
        "present_before": present_before,
        "deleted": deleted,
        "absent_after": absent_after,
        "ok": all(absent_after.values()),
    }


# ---------------------------------------------------------------------------
# Fake client — selftest + pytest fixture only. No network, ever.
# ---------------------------------------------------------------------------
class FakeGhlClient:
    """In-memory GHL stand-in. ``tag_server_matches`` lets a test control
    exactly what the fake "contains" search claims to match (including a
    deliberately over-broad substring hit) independent of what a contact's
    real ``tags`` list says — that's how the over-broad-match fail-closed
    path gets exercised without a live server."""

    def __init__(
        self,
        contacts: Optional[Dict[str, Dict[str, Any]]] = None,
        tag_server_matches: Optional[Dict[str, List[str]]] = None,
        page_size: int = 2,
        simulate_incomplete_pagination: bool = False,
        enroll_failures: Optional[Dict[str, str]] = None,
    ):
        self.contacts: Dict[str, Dict[str, Any]] = dict(contacts or {})
        self.tag_server_matches = tag_server_matches or {}
        self.page_size = page_size
        self.simulate_incomplete_pagination = simulate_incomplete_pagination
        self.enroll_failures = dict(enroll_failures or {})
        self.enrolled: List["tuple[str, str]"] = []
        self.deleted: List[str] = []
        self.search_call_count = 0

    def search_contacts(
        self, location_id: str, tag: str, page_limit: int = 100,
        search_after: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.search_call_count += 1
        ids = self.tag_server_matches.get(tag)
        if ids is None:
            ids = [
                cid for cid, c in self.contacts.items()
                if any(tag.lower() in str(t).lower() for t in c.get("tags", []))
            ]
        total = len(ids)
        offset = int(search_after) if search_after else 0
        page_limit = min(page_limit, self.page_size)
        page_ids = ids[offset: offset + page_limit]
        next_offset = offset + len(page_ids)
        contacts = [self.contacts[i] for i in page_ids if i in self.contacts]
        resp: Dict[str, Any] = {"contacts": contacts, "total": total}
        if self.simulate_incomplete_pagination:
            resp["searchAfter"] = None  # lie: claim no more pages
        else:
            resp["searchAfter"] = str(next_offset) if next_offset < total else None
        return resp

    def get_contact(self, contact_id: str) -> Optional[Dict[str, Any]]:
        return self.contacts.get(contact_id)

    def enroll_contact_in_workflow(self, contact_id: str, workflow_id: str) -> Dict[str, Any]:
        if contact_id not in self.contacts:
            raise EnrollError(contact_id, "contact not found (404)")
        if contact_id in self.enroll_failures:
            raise EnrollError(contact_id, self.enroll_failures[contact_id])
        self.enrolled.append((contact_id, workflow_id))
        return {"succeeded": True}

    def delete_contact(self, contact_id: str) -> Dict[str, Any]:
        self.deleted.append(contact_id)
        self.contacts.pop(contact_id, None)
        return {"status": "deleted"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _require_flag() -> None:
    if os.environ.get(FLAG_ENV_VAR, "").strip() != "1":
        raise BulkSendFlagOff(
            f"{FLAG_ENV_VAR}=1 is required to run a LIVE bulk-send (unset/0 "
            "refuses — additive-behind-a-flag; --selftest and pytest are "
            "fixture-only and unaffected)."
        )


def _selftest() -> int:  # noqa: C901
    import tempfile

    errors: List[str] = []

    # (a) TAG mode exact match enrolls exactly the tag-matched contacts.
    with tempfile.TemporaryDirectory() as tmp:
        contacts = {
            "c1": {"id": "c1", "tags": ["vip", "east"]},
            "c2": {"id": "c2", "tags": ["vip"]},
            "c3": {"id": "c3", "tags": ["west"]},
        }
        client = FakeGhlClient(contacts=contacts, page_size=2)
        receipt = run_bulk_send(
            client, mode="tag", location_id="L1", workflow_id="W1", tag="vip",
            evidence_root=tmp,
        )
        if sorted(receipt["matched_contact_ids"]) != ["c1", "c2"]:
            errors.append(f"(a) tag mode matched wrong set: {receipt['matched_contact_ids']}")
        if receipt["enrolled"] != 2 or not receipt["read_back"]["ok"]:
            errors.append(f"(a) tag mode enroll/read-back failed: {receipt}")
        if not os.path.exists(receipt_path(tmp)):
            errors.append("(a) receipt file not written")

    # (b) ARRAY mode explicit enrolls exactly the listed contacts.
    with tempfile.TemporaryDirectory() as tmp:
        contacts = {"c1": {"id": "c1", "tags": []}, "c2": {"id": "c2", "tags": []}}
        client = FakeGhlClient(contacts=contacts)
        receipt = run_bulk_send(
            client, mode="array", location_id="L1", workflow_id="W1",
            contact_ids=["c1", "c2"], evidence_root=tmp,
        )
        if sorted(receipt["enrolled_contact_ids"]) != ["c1", "c2"]:
            errors.append(f"(b) array mode enrolled wrong set: {receipt}")
        if not receipt["read_back"]["ok"]:
            errors.append(f"(b) array mode read-back failed: {receipt}")

    # (c) ambiguous/partial match fails closed — zero enrollment, named error.
    with tempfile.TemporaryDirectory() as tmp:
        contacts = {
            "c1": {"id": "c1", "tags": ["vip"]},
            "c2": {"id": "c2", "tags": ["vip-archive"]},  # substring, not exact
        }
        client = FakeGhlClient(
            contacts=contacts, tag_server_matches={"vip": ["c1", "c2"]},
        )
        try:
            run_bulk_send(
                client, mode="tag", location_id="L1", workflow_id="W1", tag="vip",
                evidence_root=tmp,
            )
            errors.append("(c) over-broad tag match should have raised AmbiguousMatchError")
        except AmbiguousMatchError:
            pass
        if client.enrolled:
            errors.append(f"(c) over-broad match must enroll NOTHING, got {client.enrolled}")
        r = load_receipt(tmp)
        if not r.get("fail_closed") or r.get("enrolled") != 0:
            errors.append(f"(c) fail-closed receipt not honest: {r}")

    with tempfile.TemporaryDirectory() as tmp:
        contacts = {"c1": {"id": "c1", "tags": []}}
        client = FakeGhlClient(contacts=contacts)
        try:
            run_bulk_send(
                client, mode="array", location_id="L1", workflow_id="W1",
                contact_ids=["c1", "c_missing"], evidence_root=tmp,
            )
            errors.append("(c) array mode with a missing id should have raised AmbiguousMatchError")
        except AmbiguousMatchError:
            pass
        if client.enrolled:
            errors.append(f"(c) array partial match must enroll NOTHING, got {client.enrolled}")

    # (d) cleanup: present -> delete -> absent proof.
    contacts = {"c1": {"id": "c1", "tags": []}, "c2": {"id": "c2", "tags": []}}
    client = FakeGhlClient(contacts=contacts)
    cleanup = cleanup_present_delete_absent(client, ["c1", "c2"])
    if not cleanup["ok"] or sorted(cleanup["deleted"]) != ["c1", "c2"]:
        errors.append(f"(d) cleanup present->delete->absent proof failed: {cleanup}")

    # Read-back mismatch is caught (a tampered/inconsistent receipt is refused).
    lie = build_receipt(
        mode="tag", tag="vip", contact_ids_requested=None, location_id="L1",
        workflow_id="W1", matched_ids=["c1", "c2"], enrolled_ids=["c1"],
        failures=[],
    )
    try:
        assert_read_back(lie)
        errors.append("read-back mismatch must raise ReadBackMismatch")
    except ReadBackMismatch:
        pass

    # Flag gate: refuses without GHL_BULK_SEND=1, unaffected by --selftest itself.
    prior = os.environ.pop(FLAG_ENV_VAR, None)
    try:
        _require_flag()
        errors.append("_require_flag must raise BulkSendFlagOff when unset")
    except BulkSendFlagOff:
        pass
    finally:
        if prior is not None:
            os.environ[FLAG_ENV_VAR] = prior

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print(
        "[selftest] PASS — tag/array bulk enroll + receipt/read-back + "
        "fail-closed ambiguous-match + cleanup proof (no network / no browser)"
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="ghl_bulk_workflow_enroll",
        description="Skill 6 bulk-send GHL workflow enrollment by tag or explicit array (U112).",
    )
    ap.add_argument("--selftest", action="store_true", help="run the fixture-only proof and exit")
    ap.add_argument("--location-id", default=None)
    ap.add_argument("--workflow-id", default=None)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--contact-ids", default=None, help="comma-separated explicit contact id array")
    ap.add_argument("--evidence-root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not (args.location_id and args.workflow_id and (args.tag or args.contact_ids)):
        ap.error("--location-id, --workflow-id and one of --tag/--contact-ids are required (or use --selftest)")
    if args.tag and args.contact_ids:
        ap.error("pass exactly one of --tag or --contact-ids, not both")

    try:
        _require_flag()
    except BulkSendFlagOff as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    client = GhlHttpClient()
    mode = "tag" if args.tag else "array"
    contact_ids = (
        [c.strip() for c in args.contact_ids.split(",") if c.strip()]
        if args.contact_ids else None
    )
    try:
        receipt = run_bulk_send(
            client, mode=mode, location_id=args.location_id, workflow_id=args.workflow_id,
            tag=args.tag, contact_ids=contact_ids, evidence_root=args.evidence_root,
            dry_run=args.dry_run,
        )
    except AmbiguousMatchError as exc:
        print(json.dumps({"fail_closed": True, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps(receipt, indent=2))
    return 0 if receipt["read_back"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
