"""Frozen operation registry: one row per operation id.

Frozen by the GHL modernization contract ledger, 2026-10-18 (GU-004 section 5,
5.1-5.7) and the family freeze records it cites (GU-003 family, 2026-10-18).
Every field is transcribed from those two sources; nothing here is inferred.
Each row's Version authority is the operation's official page
https://marketplace.gohighlevel.com/docs/ghl/<module>/<operation-slug>/.

Binding rules encoded by this module:

* Version is a property of a row.  There is no global default, no prefix map,
  and no fallback.  ``version is None`` means the route carries no ``Version``
  header (official MCP tool rows), or that the operation is not documented at
  all (``undocumented`` / ``internal`` / retired probe rows).
* No row carries an enablement flag.  Enablement lives in the capability gate
  and is per ``(operation_id, tenant)``; a row that could enable itself would
  break freeze section 3.2 rule 5.
* ``UNKNOWN`` marks a field the evidence did not settle.  ``None`` marks a
  field that has no value at all (for example ``doc_url`` for an operation with
  no public contract).  Neither is ever replaced by a plausible guess.

Value vocabularies beyond the six frozen ``tenant_binding`` literals
(``path.<param>``, ``token-id``, ``connection scope``, ``unknown``, ``n/a``)
are transcribed from the section 5 tables.  The adapter treats any value it
does not recognise as a refusal, so a transcribed unknown can never be
silently injected into a request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterator, Literal, Mapping

from .auth import AuthKind
from .errors import ContractViolation

DOC_FETCH_DATE = "2026-10-18"
#: The revision-3 specification supplied new operation contracts on this date.
#: A row recorded from the specification is NOT a fresh page fetch: the
#: ``doc_evidence`` field says which basis produced it, and the retrieval date
#: is the date that basis was captured, never an invented fetch timestamp.
DOC_SPEC_DATE = "2026-11-08"
UNKNOWN = "UNKNOWN"

DOCS = "https://marketplace.gohighlevel.com/docs"
SOCIAL_V2_SPEC = (
    "https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/"
    "apps/social-media-posting.json"
)
SOCIAL_V3_SPEC = (
    "https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/"
    "apps/v3/social-planner-v3.json"
)
STAGING_DOCS = "https://staging.marketplace.gohighlevel.com/docs"

# The five versions the official Versioning page lists as supported
# (2026-10-18).  ``v4`` is staging-only and is never added here.
SUPPORTED_VERSIONS: frozenset[str] = frozenset(
    {"v3", "2023-02-21", "2021-07-28", "2021-04-15", "legacy"}
)

#: Documented ``type`` values for ``GET /medias/files`` (fetch-media-content).
#: Live 200s were observed for ``file`` on 2026-10-19; the other four are the
#: documented set, not separately probed.
MEDIA_FILE_TYPES: tuple[str, ...] = ("file", "image", "video", "audio", "document")

DocumentedLevel = Literal["D", "S", "internal", "undocumented"]
RouteClass = Literal[
    "public_direct",
    "official_mcp",
    "skill44_private",
    "skill06_authoring",
    "retired",
    "capability_gap",
    "excluded",
]

PUB: RouteClass = "public_direct"
MCP: RouteClass = "official_mcp"
S44P: RouteClass = "skill44_private"
S06: RouteClass = "skill06_authoring"
RET: RouteClass = "retired"
GAP: RouteClass = "capability_gap"
EXCLUDED: RouteClass = "excluded"

PIT = (AuthKind.location_pit,)
OAUTH = (AuthKind.oauth,)
PIT_OR_OAUTH = (AuthKind.location_pit, AuthKind.oauth)
FIREBASE = (AuthKind.firebase_internal,)
# No public auth class is declared by the evidence for browser/canvas
# authoring rows and for the restore gap.  An empty tuple asserts nothing and
# can never satisfy an auth check.
NO_AUTH: tuple[AuthKind, ...] = ()

_OPERATION_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")

# Blocker codes whose rows legitimately have no public contract URL
# (freeze section 3.3: B-NO-CONTRACT, B-INTERNAL, B-RESTORE-NONE, B-NO-ADAPTER).
_NO_URL_BLOCKERS: frozenset[str] = frozenset(
    {
        "B-NO-CONTRACT",
        "B-INTERNAL",
        "B-RESTORE-NONE",
        "B-NO-ADAPTER",
        # A named gap whose exact public path is not settled yet still has no
        # operation page to cite; the row declares UNKNOWN rather than a URL
        # that would imply a contract we did not verify.
        "B-COURSE-PATH-UNVERIFIED",
        "B-KB-UPLOAD-PATH",
    }
)


@dataclass(frozen=True)
class OperationRow:
    """One frozen operation contract.

    The field list matches freeze section 1.4.  ``readback_plan`` names the
    operation id that proves a write (a reference only); it is ``None`` when
    the evidence records no frozen plan, in which case the caller must supply
    a ``ReadbackSpec`` at call time -- never a default.
    """

    operation_id: str
    method: str
    path_template: str
    version: str | None
    version_alternates: tuple[str, ...]
    documented_level: DocumentedLevel
    route_class: RouteClass
    auth_kinds: tuple[AuthKind, ...]
    tenant_binding: str
    write: bool
    approval_required: bool
    scopes_candidate: tuple[str, ...]
    doc_url: str | None
    doc_fetch_date: str | None
    blocker: str | None
    readback_plan: str | None
    #: Query parameters the operation cannot be issued without.  A row that
    #: names one here makes the adapter refuse an omission before transport
    #: instead of letting the service answer 422 (live evidence, GHL-150:
    #: ``GET /medias/files`` without ``type`` -> 422 "type must be a string").
    required_query: tuple[str, ...] = ()
    #: Documented closed value sets for required query parameters, as
    #: ``((name, (allowed, ...)), ...)``.  The adapter refuses any other value.
    query_enums: tuple[tuple[str, tuple[str, ...]], ...] = ()
    # -- contract declarations (Document 1 section 5.1, additive) ----------
    #: The operation's real request media type.  A typed JSON request and a
    #: typed multipart request can never be confused; an unimplemented media
    #: type is refused before transport, never disguised.
    request_media_type: str = "application/json"
    #: Effect of the operation itself, not inferred from the HTTP verb.
    #: ``read`` / ``write`` / ``non_persisting_write`` (validation persists
    #: nothing but consumes the write quota).
    effect: str | None = None
    #: True when a non-persisting call still consumes the write quota.
    consumes_write_quota: bool = False
    #: ``none`` / ``approval`` / ``destructive``.  ``None`` derives from the
    #: frozen ``approval_required`` flag and the method.
    approval_class: str | None = None
    request_schema_ref: str | None = None
    response_schema_ref: str | None = None
    pagination: str = "none"
    #: ``public`` / ``private_beta`` / ``feature_gap`` / ``tenant_restricted``
    #: / ``internal`` / ``retired`` / ``unknown``.  ``None`` derives to
    #: ``unknown``; documentation never activates a tenant.
    availability: str | None = None
    #: Declared fields the evidence did not settle.  Named, never guessed.
    unresolved_fields: tuple[str, ...] = ()
    #: Provenance of ``doc_url``/``doc_fetch_date``.  The revision-3
    #: specification says not every official page was reopened (Section 34.1),
    #: so a row must not claim a fresh fetch it did not perform.
    doc_evidence: str = "frozen"
    #: ``frozen`` when the evidence settled the Version literal; ``unverified``
    #: when only a documentation label is known.  A documented row may carry no
    #: literal (``version is None``) ONLY when this state is ``unverified``, the
    #: field is named in ``unresolved_fields`` and a blocker exists.
    version_state: str = "frozen"
    #: Query parameter names the operation documents, required or optional.
    documented_query: tuple[str, ...] = ()
    #: Named bounds/grammar for documented query parameters, as
    #: ``((name, constraint), ...)``.  Transcribed only where the page states it.
    query_constraints: tuple[tuple[str, str], ...] = ()
    #: Free-text, machine-readable detail about identity that is not carried by
    #: the frozen ``tenant_binding`` (for example an agency companyId the typed
    #: adapter writes into the body itself).  Never a credential value.
    identity_detail: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("required_query",):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise ContractViolation(
                    "row_required_query_invalid", operation_id=self.operation_id
                )
        seen_required: set[str] = set()
        for name in self.required_query:
            if not isinstance(name, str) or not name.strip():
                raise ContractViolation(
                    "row_required_query_invalid", operation_id=self.operation_id
                )
            if name in seen_required:
                raise ContractViolation(
                    "row_required_query_duplicate",
                    operation_id=self.operation_id,
                    detail={"query": name},
                )
            seen_required.add(name)
        seen_enums: set[str] = set()
        for entry in self.query_enums:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise ContractViolation(
                    "row_query_enum_invalid", operation_id=self.operation_id
                )
            name, allowed = entry
            if not isinstance(name, str) or not name.strip() or name not in seen_required:
                # An enum for a parameter the row does not require is a silent
                # no-op: the adapter would never check it.
                raise ContractViolation(
                    "row_query_enum_invalid",
                    operation_id=self.operation_id,
                    detail={"query": str(name)},
                )
            if name in seen_enums:
                raise ContractViolation(
                    "row_query_enum_duplicate",
                    operation_id=self.operation_id,
                    detail={"query": name},
                )
            seen_enums.add(name)
            if (
                not isinstance(allowed, tuple)
                or not allowed
                or any(not isinstance(value, str) or not value for value in allowed)
            ):
                raise ContractViolation(
                    "row_query_enum_invalid",
                    operation_id=self.operation_id,
                    detail={"query": name},
                )
        if not isinstance(self.operation_id, str) or not _OPERATION_ID.match(
            self.operation_id
        ):
            raise ContractViolation(
                "operation_id_invalid", operation_id=str(self.operation_id)
            )
        for field in ("method", "path_template"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractViolation(
                    "row_field_missing",
                    operation_id=self.operation_id,
                    detail={"field": field},
                )
        for kind in self.auth_kinds:
            if not isinstance(kind, AuthKind):
                raise ContractViolation(
                    "row_auth_kind_invalid", operation_id=self.operation_id
                )
        for version in (self.version, *self.version_alternates):
            if version is not None and not isinstance(version, str):
                raise ContractViolation(
                    "row_version_invalid", operation_id=self.operation_id
                )
        if self.approval_required and not self.write:
            raise ContractViolation(
                "approval_on_read", operation_id=self.operation_id
            )
        if not isinstance(self.write, bool):
            raise ContractViolation("row_write_invalid", operation_id=self.operation_id)
        for scope in self.scopes_candidate:
            if not isinstance(scope, str) or not scope.strip() or scope == UNKNOWN:
                raise ContractViolation(
                    "row_scope_invalid", operation_id=self.operation_id
                )
        # -- additive contract declarations ---------------------------------
        if self.request_media_type not in MEDIA_TYPES:
            raise ContractViolation(
                "row_media_type_invalid",
                operation_id=self.operation_id,
                detail={"media_type": str(self.request_media_type)},
            )
        if self.effect is not None and self.effect not in EFFECTS:
            raise ContractViolation(
                "row_effect_invalid",
                operation_id=self.operation_id,
                detail={"effect": str(self.effect)},
            )
        if not isinstance(self.consumes_write_quota, bool):
            raise ContractViolation(
                "row_write_quota_invalid", operation_id=self.operation_id
            )
        if self.resolved_effect == "read" and self.consumes_write_quota:
            raise ContractViolation(
                "row_read_consumes_write_quota", operation_id=self.operation_id
            )
        if self.effect == "write" and not self.write:
            raise ContractViolation(
                "row_effect_write_without_write_flag", operation_id=self.operation_id
            )
        if self.effect == "read" and self.write:
            raise ContractViolation(
                "row_effect_read_with_write_flag", operation_id=self.operation_id
            )
        if self.effect == "non_persisting_write" and self.write:
            raise ContractViolation(
                "row_non_persisting_marked_write", operation_id=self.operation_id
            )
        if self.effect == "non_persisting_write" and not self.consumes_write_quota:
            raise ContractViolation(
                "row_non_persisting_without_quota", operation_id=self.operation_id
            )
        if self.approval_class is not None and self.approval_class not in APPROVAL_CLASSES:
            raise ContractViolation(
                "row_approval_class_invalid",
                operation_id=self.operation_id,
                detail={"approval_class": str(self.approval_class)},
            )
        if self.resolved_approval_class == "destructive" and not self.approval_required:
            raise ContractViolation(
                "destructive_without_approval", operation_id=self.operation_id
            )
        if self.pagination not in PAGINATIONS:
            raise ContractViolation(
                "row_pagination_invalid",
                operation_id=self.operation_id,
                detail={"pagination": str(self.pagination)},
            )
        if self.availability is not None and self.availability not in AVAILABILITIES:
            raise ContractViolation(
                "row_availability_invalid",
                operation_id=self.operation_id,
                detail={"availability": str(self.availability)},
            )
        if not isinstance(self.unresolved_fields, tuple):
            raise ContractViolation(
                "row_unresolved_fields_invalid", operation_id=self.operation_id
            )
        for name in self.unresolved_fields:
            if not isinstance(name, str) or not name.strip():
                raise ContractViolation(
                    "row_unresolved_fields_invalid", operation_id=self.operation_id
                )
        if self.doc_evidence not in DOC_EVIDENCE:
            raise ContractViolation(
                "row_doc_evidence_invalid",
                operation_id=self.operation_id,
                detail={"doc_evidence": str(self.doc_evidence)},
            )
        if self.version_state not in VERSION_STATES:
            raise ContractViolation(
                "row_version_state_invalid",
                operation_id=self.operation_id,
                detail={"version_state": str(self.version_state)},
            )
        if not isinstance(self.documented_query, tuple) or any(
            not isinstance(name, str) or not name.strip()
            for name in self.documented_query
        ):
            raise ContractViolation(
                "row_documented_query_invalid", operation_id=self.operation_id
            )
        if not isinstance(self.query_constraints, tuple):
            raise ContractViolation(
                "row_query_constraints_invalid", operation_id=self.operation_id
            )
        for entry in self.query_constraints:
            if (
                not isinstance(entry, tuple)
                or len(entry) != 2
                or not all(isinstance(value, str) and value.strip() for value in entry)
            ):
                raise ContractViolation(
                    "row_query_constraints_invalid", operation_id=self.operation_id
                )

    # -- derived declarations (never a second stored authority) -------------

    @property
    def resolved_effect(self) -> str:
        return self.effect or ("write" if self.write else "read")

    @property
    def identity_placement(self) -> str:
        """Where the tenant identity rides, derived from ``tenant_binding``."""

        binding = self.tenant_binding
        if binding.startswith("path."):
            return "path"
        if binding.startswith("query."):
            return "query"
        if binding.startswith("body."):
            return "body"
        if binding in ("implicit-pit", "token-id"):
            return "token"
        if binding == "connection scope":
            return "connection"
        if binding in ("n/a", "none"):
            return "none"
        return "unknown"

    @property
    def token_class(self) -> str:
        kinds = {kind.value for kind in self.auth_kinds}
        if not kinds:
            return "none"
        if len(kinds) > 1:
            return "mixed"
        return next(iter(kinds))

    @property
    def resolved_approval_class(self) -> str:
        if self.approval_class is not None:
            return self.approval_class
        if not self.approval_required:
            return "none"
        return "destructive" if self.method.upper() == "DELETE" else "approval"

    @property
    def implementation(self) -> str:
        return {
            "public_direct": "public_rest",
            "official_mcp": "official_mcp",
            "skill44_private": "skill44_private",
            "skill06_authoring": "skill06_browser",
            "retired": "unresolved",
            "capability_gap": "unresolved",
            "excluded": "excluded",
        }[self.route_class]

    @property
    def resolved_availability(self) -> str:
        if self.availability is not None:
            return self.availability
        if self.route_class in ("capability_gap", "retired", "excluded"):
            return "unknown"
        return "unknown"

    def as_contract(self) -> dict[str, object]:
        """This row as the shared ``operation-contract`` JSON shape."""

        return {
            "schema_version": "1.0.0",
            "operation_id": self.operation_id,
            "method": self.method,
            "path_template": self.path_template,
            "version": self.version,
            "version_alternates": list(self.version_alternates),
            "identity_placement": self.identity_placement,
            "identity_binding": self.tenant_binding,
            "token_class": self.token_class,
            "auth_kinds": [kind.value for kind in self.auth_kinds],
            "scopes": list(self.scopes_candidate),
            "scopes_resolved": bool(self.scopes_candidate),
            "effect": self.resolved_effect,
            "consumes_write_quota": self.consumes_write_quota,
            "approval_class": self.resolved_approval_class,
            "doc_url": self.doc_url,
            "doc_retrieved_at": self.doc_fetch_date,
            "request_media_type": self.request_media_type,
            "request_schema_ref": self.request_schema_ref,
            "response_schema_ref": self.response_schema_ref,
            "pagination": self.pagination,
            "readback_operation": self.readback_plan,
            "availability": self.resolved_availability,
            "availability_restriction": self.blocker,
            "implementation": self.implementation,
            "route_class": self.route_class,
            "documented_level": self.documented_level,
            "required_query": list(self.required_query),
            "query_enums": [
                {"name": name, "allowed": list(allowed)}
                for name, allowed in self.query_enums
            ],
            "outcomes": list(RECEIPT_OUTCOMES),
            "unresolved_fields": list(self.unresolved_fields),
            "doc_evidence": self.doc_evidence,
            "version_state": self.version_state,
            "documented_query": list(self.documented_query),
            "query_constraints": [
                {"name": name, "constraint": constraint}
                for name, constraint in self.query_constraints
            ],
            "identity_detail": self.identity_detail,
        }


#: Request media types a row may declare.
MEDIA_TYPES: frozenset[str] = frozenset(
    {"application/json", "multipart/form-data", "unknown"}
)
#: Read/write effect vocabularies.  The verb is never the classifier.
EFFECTS: frozenset[str] = frozenset({"read", "write", "non_persisting_write"})
APPROVAL_CLASSES: frozenset[str] = frozenset({"none", "approval", "destructive"})
PAGINATIONS: frozenset[str] = frozenset({"none", "cursor", "page", "offset", "unknown"})
#: Whether a row's Version literal is settled.  ``unverified`` records a
#: documentation label (or no label) without claiming a live header contract.
VERSION_STATES: frozenset[str] = frozenset({"frozen", "unverified"})
AVAILABILITIES: frozenset[str] = frozenset(
    {
        "public",
        "private_beta",
        "feature_gap",
        "tenant_restricted",
        "internal",
        "retired",
        "unknown",
    }
)
#: Where a row's doc URL and retrieval date came from.  ``frozen`` is the
#: original 2026-10-18 freeze; ``reopened_*`` means the official page was
#: reopened on that date; ``revision3_spec`` means the contract was recorded
#: from the revision-3 specification without reopening the page.
DOC_EVIDENCE: frozenset[str] = frozenset(
    {
        "frozen",
        "reopened_2026-11-07",
        "reopened_2026-11-08",
        "revision3_spec",
        "none",
    }
)
#: The receipt outcome vocabulary shared with the contract schemas.  It is
#: never pushed into the Command Center TaskStatus enum (Section 14 projection).
RECEIPT_OUTCOMES: tuple[str, ...] = (
    "planned",
    "submitted",
    "processing",
    "verified",
    "failed",
    "blocked",
    "unknown_outcome",
    "not_requested",
)


def _R(
    operation_id: str,
    method: str,
    path_template: str,
    version: str | None,
    level: DocumentedLevel,
    route: RouteClass,
    auth: tuple[AuthKind, ...],
    tenant: str,
    write: bool,
    approval: bool,
    blocker: str | None,
    doc_url: str | None,
    *,
    alternates: tuple[str, ...] = (),
    scopes: tuple[str, ...] = (),
    readback: str | None = None,
    required_query: tuple[str, ...] = (),
    query_enums: tuple[tuple[str, tuple[str, ...]], ...] = (),
    media: str = "application/json",
    effect: str | None = None,
    consumes_write_quota: bool = False,
    approval_class: str | None = None,
    req_schema: str | None = None,
    resp_schema: str | None = None,
    pagination: str = "none",
    availability: str | None = None,
    unresolved: tuple[str, ...] = (),
    version_state: str = "frozen",
    documented_query: tuple[str, ...] = (),
    query_constraints: tuple[tuple[str, str], ...] = (),
    identity_detail: str | None = None,
) -> OperationRow:
    return OperationRow(
        operation_id=operation_id,
        method=method,
        path_template=path_template,
        version=version,
        version_alternates=alternates,
        documented_level=level,
        route_class=route,
        auth_kinds=auth,
        tenant_binding=tenant,
        write=write,
        approval_required=approval,
        scopes_candidate=scopes,
        doc_url=doc_url,
        doc_fetch_date=DOC_FETCH_DATE if doc_url else None,
        blocker=blocker,
        readback_plan=readback,
        required_query=required_query,
        query_enums=query_enums,
        request_media_type=media,
        effect=effect,
        consumes_write_quota=consumes_write_quota,
        approval_class=approval_class,
        request_schema_ref=req_schema,
        response_schema_ref=resp_schema,
        pagination=pagination,
        availability=availability,
        unresolved_fields=unresolved,
        version_state=version_state,
        documented_query=documented_query,
        query_constraints=query_constraints,
        identity_detail=identity_detail,
    )


# ---------------------------------------------------------------------------
# 5.0 Locations (GHL-140 amendment, 2026-10-19)
#
# The family freeze recorded no ``locations.*`` row, so no client path could
# reach ``GET /locations/{locationId}`` at all.  This row transcribes the
# official document ``apps/locations.json`` (operation ``get-location``,
# fetched 2026-10-19): Version ``2021-07-28`` and scope ``locations.readonly``
# (Location-Access / Agency-Access).  Nothing else is inferred.
# ---------------------------------------------------------------------------
_LOCATIONS: tuple[OperationRow, ...] = (
    _R("locations.get", "GET", "/locations/{locationId}", "2021-07-28", "D", PUB,
       PIT_OR_OAUTH, "path.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/locations/get-location", scopes=("locations.readonly",)),
    # WF05 reconciliation: documented public sub-account create.  Agency Pro
    # eligibility is a per-tenant account fact, never a default for every
    # agency; the executing credential stays agency_pit and the agency
    # companyId rides the body, never a location id.
    _R("locations.create", "POST", "/locations", "2021-07-28", "D", PUB,
       (AuthKind.agency_pit,), "none", True, True, "A-UNVERIFIED",
       DOCS + "/ghl/locations/create-location", alternates=("v3",),
       scopes=("locations.write",), approval_class="approval",
       availability="tenant_restricted", readback="locations.get",
       identity_detail=("agency companyId rides body.companyId and must equal the "
                        "agency companyId, never a locationId; the typed adapter "
                        "writes it and no location is injected"),
       unresolved=("request_schema_ref", "response_schema_ref")),
)

# ---------------------------------------------------------------------------
# 5.1 Contacts, tags, custom fields, custom values (GU-003-contacts)
# ---------------------------------------------------------------------------
_CONTACTS: tuple[OperationRow, ...] = (
    _R("contacts.list", "GET", "/contacts/", "2021-07-28", "D", RET, PIT_OR_OAUTH,
       "query.locationId", False, False, "B-DEPRECATED",
       DOCS + "/2021-07-28/ghl/contacts/get-contacts",
       scopes=("contacts.readonly",)),
    _R("contacts.get", "GET", "/contacts/{contactId}", "v3", "D", PUB, PIT_OR_OAUTH,
       "path.contactId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/contacts/get-contact"),
    _R("contacts.create", "POST", "/contacts/", "v3", "D", PUB, PIT_OR_OAUTH,
       "body.locationId", True, False, "B-CUST-DUP",
       DOCS + "/ghl/contacts/create-contact"),
    _R("contacts.upsert", "POST", "/contacts/upsert", "v3", "D", PUB, PIT_OR_OAUTH,
       "body.locationId", True, False, "B-CUST-DUP",
       DOCS + "/ghl/contacts/upsert-contact", readback="contacts.get"),
    _R("contacts.update", "PUT", "/contacts/{contactId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "path.contactId", True, False, "B-CUSTOMFIELDS",
       DOCS + "/ghl/contacts/update-contact"),
    _R("contacts.delete", "DELETE", "/contacts/{contactId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "path.contactId", True, True, "B-REPEAT-DELETE",
       DOCS + "/ghl/contacts/delete-contact"),
    _R("contacts.search", "POST", "/contacts/search", "v3", "D", PUB, PIT_OR_OAUTH,
       "body.locationId", False, False, "B-FILTER-SCHEMA",
       DOCS + "/ghl/contacts/search-contacts-advanced",
       scopes=("contacts.readonly",)),
    _R("contacts.tags.add", "POST", "/contacts/{contactId}/tags", "v3", "D", PUB,
       PIT_OR_OAUTH, "path.contactId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/contacts/add-tags"),
    _R("contacts.tags.remove", "DELETE", "/contacts/{contactId}/tags", "v3", "D",
       PUB, PIT_OR_OAUTH, "path.contactId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/contacts/remove-tags"),
    _R("contacts.lookup", "GET", "/contacts/lookup", "v3", "D", PUB, OAUTH,
       "query.locationId", False, False, "B-PIT-LOOKUP",
       DOCS + "/ghl/contacts/lookup-contact"),
    _R("custom_fields.list", "GET", "/locations/{locationId}/customFields", "v3",
       "D", PUB, PIT_OR_OAUTH, "path.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/locations/get-custom-fields",
       scopes=("locations/customFields.readonly",)),
    _R("custom_fields.get", "GET", "/locations/{locationId}/customFields/{id}",
       "v3", "D", PUB, PIT_OR_OAUTH, "path.locationId", False, False,
       "A-UNVERIFIED", DOCS + "/ghl/locations/get-custom-field"),
    _R("custom_fields.create", "POST", "/locations/{locationId}/customFields",
       "v3", "D", PUB, PIT_OR_OAUTH, "path.locationId", True, False,
       "B-OPTIONS-FIELD", DOCS + "/ghl/locations/create-custom-field"),
    _R("custom_values.list", "GET", "/locations/{locationId}/customValues", "v3",
       "D", PUB, PIT_OR_OAUTH, "path.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/locations/get-custom-values"),
    _R("custom_values.create", "POST", "/locations/{locationId}/customValues",
       "v3", "D", PUB, PIT_OR_OAUTH, "path.locationId", True, False,
       "A-UNVERIFIED", DOCS + "/ghl/locations/create-custom-value"),
    _R("custom_values.update", "PUT",
       "/locations/{locationId}/customValues/{id}", "v3", "D", PUB,
       PIT_OR_OAUTH, "path.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/locations/update-custom-value"),
    _R("tags.list", "GET", "/locations/{locationId}/tags", "v3", "D", PUB,
       PIT_OR_OAUTH, "path.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/locations/get-location-tags"),
    _R("tags.create", "POST", "/locations/{locationId}/tags", "v3", "D", PUB,
       PIT_OR_OAUTH, "path.locationId", True, False, "B-NO-ADAPTER",
       DOCS + "/ghl/locations/create-tag"),
)

# ---------------------------------------------------------------------------
# 5.2 Opportunities and pipelines (GU-003-opportunities)
# ---------------------------------------------------------------------------
_OPPORTUNITIES: tuple[OperationRow, ...] = (
    _R("opportunities.search", "GET", "/opportunities/search", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/opportunities/search-opportunity"),
    _R("opportunities.get", "GET", "/opportunities/{id}", "v3", "D", PUB,
       PIT_OR_OAUTH, "path.id", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/opportunities/get-opportunity"),
    _R("opportunities.create", "POST", "/opportunities/", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/opportunities/create-opportunity"),
    _R("opportunities.update", "PUT", "/opportunities/{id}", "v3", "D", PUB,
       PIT_OR_OAUTH, "path.id", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/opportunities/update-opportunity"),
    _R("opportunities.delete", "DELETE", "/opportunities/{id}", "v3", "D", PUB,
       PIT_OR_OAUTH, "path.id", True, True, "A-UNVERIFIED",
       DOCS + "/ghl/opportunities/delete-opportunity"),
    _R("pipelines.list", "GET", "/opportunities/pipelines", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/opportunities/get-pipelines"),
    _R("pipelines.get", "GET", "/opportunities/pipelines/{pipelineId}", "v3", "D",
       PUB, PIT_OR_OAUTH, "path.pipelineId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/opportunities/get-pipeline"),
    _R("pipelines.update", "PUT", "/opportunities/pipelines/{pipelineId}", "v3",
       "D", PUB, PIT_OR_OAUTH, "path.pipelineId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/opportunities/update-pipeline"),
    _R("pipelines.create", "POST", "/opportunities/pipelines", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "B-NO-ADAPTER",
       DOCS + "/ghl/opportunities/create-pipeline"),
    _R("pipelines.delete", "DELETE", "/opportunities/pipelines/{pipelineId}",
       "v3", "D", PUB, PIT_OR_OAUTH, "path.pipelineId", True, True,
       "B-NO-ADAPTER", DOCS + "/ghl/opportunities/delete-pipeline"),
    # No bare-list operation exists; the cited section index is the evidence
    # of that absence, not a contract page for GET /opportunities.
    _R("opportunities.list_probe", "GET", "/opportunities", None, "undocumented",
       RET, PIT_OR_OAUTH, "query.locationId", False, False, "B-DEPRECATED",
       DOCS + "/ghl/opportunities/opportunities"),
    _R("opportunities.upsert", "POST", "/opportunities/upsert", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/opportunities/upsert-opportunity"),
    _R("opportunities.status.update", "PUT", "/opportunities/{id}/status", "v3",
       "D", PUB, PIT_OR_OAUTH, "path.id", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/opportunities/update-opportunity-status"),
    _R("opportunities.followers.add", "POST", "/opportunities/{id}/followers",
       "v3", "D", EXCLUDED, PIT_OR_OAUTH, "path.id", True, False, "NONE",
       DOCS + "/ghl/opportunities/add-followers-opportunity"),
    _R("opportunities.followers.remove", "DELETE",
       "/opportunities/{id}/followers", "v3", "D", EXCLUDED, PIT_OR_OAUTH,
       "path.id", True, False, "NONE",
       DOCS + "/ghl/opportunities/remove-followers-opportunity"),
)

# ---------------------------------------------------------------------------
# 5.3 Conversations, messaging, calendars (GU-003-calendar-conversations)
# ---------------------------------------------------------------------------
_CONVERSATIONS_CALENDARS: tuple[OperationRow, ...] = (
    _R("conversations.messages.send", "POST", "/conversations/messages", "v3",
       "D", PUB, PIT_OR_OAUTH, "implicit-pit", True, True, "B-SEND-STATUS",
       DOCS + "/ghl/conversations/send-a-new-message"),
    _R("conversations.messages.send_in_conversation", "POST",
       "/conversations/messages", "v3", "D", PUB, PIT_OR_OAUTH, "implicit-pit",
       True, True, "B-CONV-BODY",
       DOCS + "/ghl/conversations/send-a-new-message"),
    _R("conversations.search", "GET", "/conversations/search", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "B-CURSOR",
       DOCS + "/ghl/conversations/search-conversation"),
    _R("conversations.get", "GET", "/conversations/{conversationId}", "v3", "D",
       PUB, PIT_OR_OAUTH, "path.conversationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/conversations/get-conversation"),
    _R("conversations.messages.list", "GET",
       "/conversations/{conversationId}/messages", "v3", "D", PUB,
       PIT_OR_OAUTH, "path.conversationId", False, False, "B-CURSOR",
       DOCS + "/ghl/conversations/get-messages"),
    _R("conversations.messages.get_email", "GET",
       "/conversations/messages/email/{id}", "v3", "D", PUB, PIT_OR_OAUTH,
       "implicit-pit", False, False, "B-HEADER-INERT",
       DOCS + "/ghl/conversations/email"),
    # The section index carries no list operation; it is cited as the
    # evidence of absence, never as a contract for GET /conversations/.
    _R("conversations.list_legacy", "GET", "/conversations/", None,
       "undocumented", RET, PIT_OR_OAUTH, "query.locationId", False, False,
       "B-DEPRECATED", DOCS + "/ghl/conversations/conversations"),
    _R("calendars.list", "GET", "/calendars/", "v3", "D", PUB, PIT_OR_OAUTH,
       "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/calendars/get-calendars"),
    _R("calendars.get", "GET", "/calendars/{calendarId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "path.calendarId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/calendars/get-calendar"),
    _R("calendars.create", "POST", "/calendars/", "v3", "D", PUB, PIT_OR_OAUTH,
       "body.locationId", True, False, "B-TEAMMEMBERS",
       DOCS + "/ghl/calendars/create-calendar"),
    _R("calendars.free_slots", "GET", "/calendars/{calendarId}/free-slots", "v3",
       "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False, "B-FREESLOT",
       DOCS + "/ghl/calendars/get-slots"),
    _R("calendars.events.list", "GET", "/calendars/events", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "B-C5-PATH",
       DOCS + "/ghl/calendars/get-calendar-events"),
    _R("appointments.create", "POST", "/calendars/events/appointments", "v3",
       "D", PUB, PIT_OR_OAUTH, "body.locationId", True, False, "B-SLOT",
       DOCS + "/ghl/calendars/create-appointment"),
    _R("appointments.update", "PUT",
       "/calendars/events/appointments/{eventId}", "v3", "D", PUB, PIT_OR_OAUTH,
       "path.eventId", True, False, "B-NO-ADAPTER",
       DOCS + "/ghl/calendars/edit-appointment"),
    _R("events.delete", "DELETE", "/calendars/events/{eventId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "path.eventId", True, True, "B-DELETE-BODY",
       DOCS + "/ghl/calendars/delete-event"),
    _R("calendars.groups.list", "GET", "/calendars/groups", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/calendars/get-groups"),
    _R("calendars.services.catalog", "GET", "/calendars/services/catalog", "v3",
       "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "B-NO-CONTRACT", DOCS + "/ghl/calendars/services"),
    _R("calendars.services.bookings", "POST", "/calendars/services/bookings",
       "v3", "D", PUB, PIT_OR_OAUTH, "body.locationId", True, False,
       "B-NO-CONTRACT", DOCS + "/ghl/calendars/services"),
    _R("calendars.services.locations", "GET", "/calendars/services/locations",
       "v3", "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "B-NO-CONTRACT", DOCS + "/ghl/calendars/services"),
)

# ---------------------------------------------------------------------------
# 5.4 Products, orders, transactions, subscriptions, coupons, invoices,
#     estimates (GU-003-payments-commerce)
#
# Frozen literal is ``v3``; ``2021-07-28`` is the only permitted rollback
# literal for this family and travels per row.
# ---------------------------------------------------------------------------
_PAYMENTS_ALT: tuple[str, ...] = ("2021-07-28",)

# Product/price writes: ``amount`` in CreatePriceDto is a decimal in MAJOR units
# (spec example 99.99, official apps/products.json). Callers never build that
# body by hand: shared-utils/ghl/products_prices.py owns the one conversion
# (ISO-4217 exponent aware) plus the read-first / read-back / approval discipline,
# and the Skill 44 CLI product/price commands route through it.
_PAYMENTS: tuple[OperationRow, ...] = (
    # F11 correction: products.list carried blocker ``B-COMMUNITY-RAIL``, a
    # retired-community-transport code that serves no product route and that no
    # other row in this family carries. The row is a public REST read with no
    # recorded verification, so ``A-UNVERIFIED`` states what is actually known.
    # No other field on the row changed.
    _R("products.list", "GET", "/products/", "v3", "D", PUB, PIT_OR_OAUTH,
       "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/products/list-invoices",
       alternates=_PAYMENTS_ALT),
    _R("products.get", "GET", "/products/{productId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/products/get-product-by-id",
       alternates=_PAYMENTS_ALT),
    _R("products.create", "POST", "/products/", "v3", "D", PUB, PIT_OR_OAUTH,
       "body.locationId", True, True, "B-PRODUCT-422",
       DOCS + "/2021-07-28/ghl/products/create-product",
       alternates=_PAYMENTS_ALT),
    _R("products.update", "PUT", "/products/{productId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/products/update-product-by-id",
       alternates=_PAYMENTS_ALT),
    _R("products.delete", "DELETE", "/products/{productId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", True, True, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/products/delete-product-by-id",
       alternates=_PAYMENTS_ALT),
    _R("products.prices.create", "POST", "/products/{productId}/price", "v3",
       "D", PUB, PIT_OR_OAUTH, "body.locationId", True, True, "B-PRICE-KEY",
       DOCS + "/2021-07-28/ghl/products/create-price-for-product",
       alternates=_PAYMENTS_ALT),
    _R("products.prices.list", "GET", "/products/{productId}/price", "v3", "D",
       PUB, PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/products/list-prices-for-product",
       alternates=_PAYMENTS_ALT),
    _R("orders.list", "GET", "/payments/orders", "v3", "D", PUB, PIT_OR_OAUTH,
       "body.altId+altType=location", False, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/payments/list-orders",
       alternates=_PAYMENTS_ALT),
    _R("orders.get", "GET", "/payments/orders/{orderId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.altId+altType", False, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/payments/get-order-by-id",
       alternates=_PAYMENTS_ALT),
    _R("orders.fulfillments.create", "POST",
       "/payments/orders/{orderId}/fulfillments", "v3", "D", PUB, PIT_OR_OAUTH,
       "body.altId+altType=location", True, True, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/payments/create-order-fulfillment",
       alternates=_PAYMENTS_ALT),
    _R("orders.recordPayment", "POST",
       "/payments/orders/{orderId}/record-payment", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.altId+altType=location", True, True, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/payments/record-order-payment",
       alternates=_PAYMENTS_ALT),
    _R("transactions.list", "GET", "/payments/transactions", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.altId+altType", False, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/payments/list-transactions",
       alternates=_PAYMENTS_ALT),
    _R("transactions.get", "GET", "/payments/transactions/{transactionId}", "v3",
       "D", PUB, PIT_OR_OAUTH, "query.altId+altType", False, False,
       "A-UNVERIFIED", DOCS + "/2021-07-28/ghl/payments/get-transaction-by-id",
       alternates=_PAYMENTS_ALT),
    _R("subscriptions.list", "GET", "/payments/subscriptions", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.altId+altType", False, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/payments/list-subscriptions",
       alternates=_PAYMENTS_ALT),
    _R("subscriptions.get", "GET", "/payments/subscriptions/{subscriptionId}",
       "v3", "D", PUB, PIT_OR_OAUTH, "query.altId+altType", False, False,
       "A-UNVERIFIED", DOCS + "/2021-07-28/ghl/payments/get-subscription-by-id",
       alternates=_PAYMENTS_ALT),
    _R("coupons.list", "GET", "/payments/coupon/list", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.altId+altType", False, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/payments/list-coupons",
       alternates=_PAYMENTS_ALT),
    _R("coupons.get", "GET", "/payments/coupon", "v3", "D", PUB, PIT_OR_OAUTH,
       "query.altId+altType", False, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/payments/get-coupon",
       alternates=_PAYMENTS_ALT),
    _R("coupons.create", "POST", "/payments/coupon", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.altId+altType=location", True, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/payments/create-coupon",
       alternates=_PAYMENTS_ALT),
    _R("coupons.update", "PUT", "/payments/coupon", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.altId+altType=location", True, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/payments/update-coupon",
       alternates=_PAYMENTS_ALT),
    _R("coupons.delete", "DELETE", "/payments/coupon", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.altId+altType=location", True, True, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/payments/delete-coupon",
       alternates=_PAYMENTS_ALT),
    _R("invoices.list", "GET", "/invoices/", "v3", "D", PUB, PIT_OR_OAUTH,
       "query.altId+altType", False, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/invoices/list-invoices",
       alternates=_PAYMENTS_ALT),
    _R("invoices.create", "POST", "/invoices/", "v3", "D", PUB, PIT_OR_OAUTH,
       "body.altId+altType=location", True, True, "B-INVOICE-SCHEMA",
       DOCS + "/2021-07-28/ghl/invoices/create-invoice",
       alternates=_PAYMENTS_ALT, readback="invoices.get"),
    _R("invoices.get", "GET", "/invoices/{invoiceId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.altId+altType", False, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/invoices/get-invoice",
       alternates=_PAYMENTS_ALT),
    _R("invoices.send", "POST", "/invoices/{invoiceId}/send", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.altId+altType=location", True, True, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/invoices/send-invoice",
       alternates=_PAYMENTS_ALT),
    _R("invoices.void", "POST", "/invoices/{invoiceId}/void", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.altId+altType=location", True, True, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/invoices/void-invoice",
       alternates=_PAYMENTS_ALT),
    _R("invoices.recordPayment", "POST",
       "/invoices/{invoiceId}/record-payment", "v3", "D", PUB, PIT_OR_OAUTH,
       "body.altId+altType=location", True, True, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/invoices/record-invoice",
       alternates=_PAYMENTS_ALT),
    _R("invoices.schedules.create", "POST", "/invoices/schedule", "v3", "D",
       PUB, PIT_OR_OAUTH, "body.altId+altType=location", True, False,
       "A-UNVERIFIED", DOCS + "/2021-07-28/ghl/invoices/create-invoice-schedule",
       alternates=_PAYMENTS_ALT),
    _R("estimates.create", "POST", "/invoices/estimate", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.altId+altType=location", True, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/invoices/create-new-estimate",
       alternates=_PAYMENTS_ALT),
    _R("estimates.list", "GET", "/invoices/estimate/list", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.altId+altType", False, False, "A-UNVERIFIED",
       DOCS + "/2021-07-28/ghl/invoices/list-estimates",
       alternates=_PAYMENTS_ALT),
    _R("estimates.send", "POST", "/invoices/estimate/{estimateId}/send", "v3",
       "D", PUB, PIT_OR_OAUTH, "body.altId+altType=location", True, True,
       "A-UNVERIFIED", DOCS + "/2021-07-28/ghl/invoices/send-estimate",
       alternates=_PAYMENTS_ALT),
)

# ---------------------------------------------------------------------------
# 5.5 Forms, surveys, funnels, pages, media (GU-003-content)
#
# Generic shapes recorded by the audit ("page blob", "page autosave",
# "internal page list", "(capture-derived)", "(browser)", "(canvas + browser)")
# are transcribed as UNKNOWN.  No literal is invented for them.
# ---------------------------------------------------------------------------
_CONTENT: tuple[OperationRow, ...] = (
    _R("forms.list", "GET", "/forms/", "v3", "D", PUB, PIT_OR_OAUTH,
       "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/forms/get-forms"),
    _R("forms.submissions.list", "GET", "/forms/submissions", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/forms/get-forms-submissions"),
    _R("forms.update", "PUT", "/forms/{id}", None, "undocumented", S06, NO_AUTH,
       "unknown", True, False, "B-NO-CONTRACT", None),
    _R("forms.custom_files.upload", "POST", "/forms/upload-custom-files", "v3",
       "D", PUB, PIT_OR_OAUTH, "body.locationId", True, False, "B-NO-ADAPTER",
       DOCS + "/ghl/forms/upload-custom-files"),
    _R("surveys.list", "GET", "/surveys/", "v3", "D", PUB, PIT_OR_OAUTH,
       "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/surveys/get-surveys"),
    _R("surveys.get", "GET", "backend.../surveys/{id}", None, "internal", S06,
       FIREBASE, "token-id", False, False, "B-INTERNAL", None),
    _R("surveys.submissions.list", "GET", "/surveys/submissions", "v3", "D",
       PUB, PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/surveys/get-surveys-submissions"),
    _R("surveys.write", UNKNOWN, UNKNOWN, None, "undocumented", S06, NO_AUTH,
       "unknown", True, False, "B-NO-CONTRACT", None),
    # Funnel read paths reconciled 2026-11-08 (Document 1 section 21.3,
    # rechecks V08-V10): the frozen rows carried the older
    # /funnels/ and /funnels/{funnelId}/pages shapes.  The published contract
    # is /funnels/funnel/list and /funnels/page[/count] with query ids.  The
    # exact required query schema and literal Version detail were NOT reopened
    # here, so `unresolved_fields` names them instead of guessing.  No
    # funnel/page authoring endpoint is inferred from these reads.
    _R("funnels.list", "GET", "/funnels/funnel/list", "2023-02-21", "D",
       PUB, PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/funnels/get-funnels/", alternates=("v3",),
       version_state="unverified", pagination="page", availability="public",
       required_query=("locationId", "offset", "limit"),
       documented_query=("locationId", "offset", "limit", "type", "category",
                         "parentId", "name"),
       unresolved=("version.header", "scopes", "response_schema_ref")),
    _R("funnels.pages.list", "GET", "/funnels/page", "2023-02-21", "D",
       PUB, PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/funnels/get-pages-by-funnel-id", alternates=("v3",),
       version_state="unverified", pagination="page", availability="public",
       required_query=("locationId", "funnelId", "limit", "offset"),
       documented_query=("locationId", "funnelId", "limit", "offset", "name"),
       unresolved=("version.header", "scopes", "response_schema_ref",
                   "response.envelope_key")),
    _R("funnels.pages.count", "GET", "/funnels/page/count", "2023-02-21",
       "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "A-UNVERIFIED", DOCS + "/ghl/funnels/get-pages-count-by-funnel-id",
       alternates=("v3",), version_state="unverified", availability="public",
       required_query=("locationId", "funnelId"),
       documented_query=("locationId", "funnelId", "name"),
       unresolved=("version.header", "scopes", "response.envelope_key")),
    _R("funnels.create", "POST", "/funnels/", None, "internal", S06, FIREBASE,
       "token-id", True, False, "B-INTERNAL", None),
    _R("funnels.steps.create", "POST", "/funnels/{funnelId}/steps", None,
       "internal", S06, FIREBASE, "token-id", True, False, "B-INTERNAL", None),
    _R("funnels.get", "GET", "/funnels/{funnelId}", None, "internal", S06,
       FIREBASE, "token-id", False, False, "B-INTERNAL", None),
    _R("funnels.delete", "DELETE", "/funnels/{funnelId}", None, "internal", S06,
       FIREBASE, "token-id", True, True, "B-INTERNAL", None),
    _R("funnels.pages.get", "GET", UNKNOWN, None, "internal", S06, FIREBASE,
       "token-id", False, False, "B-INTERNAL", None),
    _R("funnels.pages.autosave", "POST", UNKNOWN, None, "internal", S06,
       FIREBASE, "token-id", True, False, "B-INTERNAL", None),
    _R("funnels.pages.list_internal", "GET", UNKNOWN, None, "internal", RET,
       FIREBASE, "token-id", False, False, "B-INTERNAL", None),
    _R("funnels.redirects.create", "POST", "/funnels/redirects", "v3", "D",
       PUB, PIT_OR_OAUTH, "body.locationId", True, False, "B-NO-ADAPTER",
       DOCS + "/ghl/funnels/create-redirect"),
    _R("media.upload", "POST", "/medias/upload-file", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/medias/upload-media-content"),
    _R("media.folders.create", "POST", "/medias/folder", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/medias/create-media-folder"),
    _R("media.files.list", "GET", "/medias/files", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/medias/fetch-media-content",
       # Live evidence 2026-10-19 (Mct54Bwi1KlNouGXQcDX): the route answers
       # 422 {"message":["type must be a string","type should not be empty"]}
       # with no ``type``, and 200 {files,count,traceId} with &type=file.  The
       # documented set is the five accepted literals.
       required_query=("type",),
       query_enums=(("type", MEDIA_FILE_TYPES),)),
    _R("forms.authoring", UNKNOWN, UNKNOWN, None, "undocumented", S06, NO_AUTH,
       "n/a", True, False, "B-NO-CONTRACT", None),
    _R("surveys.authoring", UNKNOWN, UNKNOWN, None, "undocumented", S06,
       NO_AUTH, "n/a", True, False, "B-NO-CONTRACT", None),
    _R("funnels.pages.authoring", UNKNOWN, UNKNOWN, None, "undocumented", S06,
       NO_AUTH, "n/a", True, False, "B-NO-CONTRACT", None),
)

# ---------------------------------------------------------------------------
# 5.6 Social accounts, posts, queues, comments (GU-003-social)
#
# The marketplace pages returned only the SPA shell, so the documentation URL
# is the vendor-maintained OpenAPI file that the marketplace renders.  That is
# a documentation-source substitution recorded by GU-003, not an inference.
# ---------------------------------------------------------------------------
_SOCIAL: tuple[OperationRow, ...] = (
    _R("social.accounts.list", "GET",
       "/social-media-posting/{locationId}/accounts", "2021-07-28", "D", PUB,
       PIT, "path.locationId", False, False, "B-SOCIAL-SPEC", SOCIAL_V2_SPEC,
       alternates=("v3",), scopes=("socialplanner/account.readonly",)),
    _R("social.posts.list", "POST",
       "/social-media-posting/{locationId}/posts/list", "2021-07-28", "D", PUB,
       PIT, "path.locationId", False, False, "B-SOCIAL-SPEC", SOCIAL_V2_SPEC,
       alternates=("v3",), scopes=("socialplanner/post.readonly",)),
    _R("social.posts.create", "POST",
       "/social-media-posting/{locationId}/posts", "2021-07-28", "D", PUB, PIT,
       "path.locationId", True, True, "B-SOCIAL-SPEC", SOCIAL_V2_SPEC,
       alternates=("v3",), scopes=("socialplanner/post.write",),
       readback="social.posts.list"),
    _R("social.posts.get", "GET",
       "/social-media-posting/{locationId}/posts/{id}", "2021-07-28", "D", PUB,
       PIT, "path.locationId", False, False, "B-SOCIAL-SPEC", SOCIAL_V2_SPEC,
       alternates=("v3",)),
    _R("social.posts.delete", "DELETE",
       "/social-media-posting/{locationId}/posts/{id}", "2021-07-28", "D", PUB,
       PIT, "path.locationId", True, True, "B-SOCIAL-SPEC", SOCIAL_V2_SPEC,
       alternates=("v3",), readback="social.posts.get"),
    _R("social.statistics", "POST", "/social-media-posting/statistics", "v3",
       "D", PUB, PIT, "body.locationId", False, False, "B-SOCIAL-SPEC",
       SOCIAL_V3_SPEC, scopes=("socialplanner/statistics.readonly",)),
    _R("social.oauth.accounts.list", "GET",
       "/social-media-posting/oauth/{locationId}/{platform}/accounts/{accountId}",
       "2021-07-28", "D", PUB, OAUTH, "path.locationId", False, False,
       "B-SOCIAL-SPEC", SOCIAL_V2_SPEC, alternates=("v3",)),
    _R("social.queues.list", "POST",
       "/social-media-posting/category/queues/list", "v3", "D", PUB, PIT,
       "body.locationId", False, False, "B-SOCIAL-SPEC", SOCIAL_V3_SPEC,
       scopes=("socialplanner/category.readonly",)),
    _R("social.queues.items.list", "POST",
       "/social-media-posting/category/queues/{queueId}/items", "v3", "D", PUB,
       PIT, "path.queueId", False, False, "B-SOCIAL-SPEC", SOCIAL_V3_SPEC,
       scopes=("socialplanner/category.readonly",)),
    _R("social.queues.create", "POST",
       "/social-media-posting/category/queues", "v3", "D", PUB, PIT,
       "body.locationId", True, False, "B-SOCIAL-SPEC", SOCIAL_V3_SPEC,
       scopes=("socialplanner/category.write",), readback="social.queues.list"),
    _R("social.comments.list", "POST",
       "/social-media-posting/comments/{platform}/list", "v3", "D", PUB, PIT,
       "body.locationId", False, False, "B-SOCIAL-SPEC", SOCIAL_V3_SPEC),
    _R("social.comments.create", "POST",
       "/social-media-posting/comments/{platform}", "v3", "D", PUB, PIT,
       "body.locationId", True, True, "B-SOCIAL-SPEC", SOCIAL_V3_SPEC,
       readback="social.comments.list"),
    _R("social.comments.like", "POST/DELETE",
       "/social-media-posting/comments/{platform}/{id}/like", "v3", "D", PUB,
       PIT, "body.locationId", True, True, "B-SOCIAL-SPEC", SOCIAL_V3_SPEC,
       readback="social.comments.list"),
    # Community social rows (Document 1 section 11.2, WF10 ids).  The word
    # "oauth" in a scope name does not prohibit a Private Integration token.
    # The member-list page renders inconsistently across documentation views,
    # so its pagination parameter names and response schema stay unresolved.
    _R("social.community.users.list", "GET",
       "/social-media-posting/{locationId}/community/accounts/{accountId}/users",
       "2021-07-28", "D", PUB, PIT, "path.locationId", False, False,
       "B-SOCIAL-SPEC", SOCIAL_V2_SPEC, alternates=("v3",),
       scopes=("socialplanner/oauth.readonly",), pagination="page",
       availability="public",
       unresolved=("response_schema_ref", "query.pagination_parameter_names")),
    _R("social.community.group_users.validate", "GET",
       "/social-media-posting/{locationId}/community/groups/{groupId}/users/"
       "{contactId}/validate", "2021-07-28", "D", PUB, PIT, "path.locationId",
       False, False, "B-SOCIAL-SPEC", SOCIAL_V2_SPEC, alternates=("v3",),
       scopes=("socialplanner/account.readonly",), availability="public",
       unresolved=("response_schema_ref",)),
    _R("social.comments.community.create", "POST",
       "/social-media-posting/comments/community", "v3", "D", PUB, PIT,
       "query.locationId", True, True, "B-SOCIAL-SPEC", SOCIAL_V3_SPEC,
       scopes=("socialplanner/comments.write",), readback="social.comments.list",
       availability="public",
       unresolved=("request_schema_ref",
                   "body.comment_fields_beyond_isParentThread_notifyAllGroupMembers")),
)


# ---------------------------------------------------------------------------
# 5.7 Workflows and official MCP (GU-003-workflows-mcp)
#
# ``workflows.private.trigger.link`` is a two-call row in the freeze
# (POST /workflow/{loc}/trigger then PUT .../trigger/{id} with targetActionId).
# The registry records the first call; the row is Skill44-private and never
# routed through the public adapter.
# ---------------------------------------------------------------------------
_PRIVATE_VERSION = "2021-07-28"  # internal rail header, recorded by GU-003

_WORKFLOWS_MCP: tuple[OperationRow, ...] = (
    # F11 version reconciliation (2026-11-07). Production contract re-read at
    # https://marketplace.gohighlevel.com/docs/ghl/workflows/get-workflow/:
    # GET /workflows/ documents Version v3, which is the literal this row
    # already carries (the page is titled "Get Workflow (deprecated)" yet still
    # publishes the operation at v3). The recorded live 200 for the same route
    # used 2021-07-28 (GHL_UPDATES_live-ledger.md line 759), and GHL accepts
    # more than one supported Version on several routes, so that literal is a
    # permitted rollback for this row and is recorded as such rather than
    # replacing the documented value. F6 / B-WORKFLOWS-LIST-VERSION stays open
    # until one authorized v3 call is recorded (see
    # evidence/W23/f6-workflows-list-version.md); this row still declares v3.
    _R("workflows.list", "GET", "/workflows/", "v3", "D", PUB, PIT_OR_OAUTH,
       "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/workflows/get-workflow/", scopes=("workflows.readonly",),
       alternates=("2021-07-28",)),
    # F11: production pages re-read 2026-11-07 — add-contact-to-workflow is
    # POST /contacts/{contactId}/workflow/{workflowId} at Version v3 and
    # delete-contact-from-workflow is the same path at Version v3. The rows
    # below match both.
    _R("workflows.enroll", "POST",
       "/contacts/{contactId}/workflow/{workflowId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/contacts/add-contact-to-workflow/"),
    _R("workflows.remove", "DELETE",
       "/contacts/{contactId}/workflow/{workflowId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", True, True, "A-UNVERIFIED",
       DOCS + "/ghl/contacts/delete-contact-from-workflow/"),
    # F11 re-freeze (2026-11-08, Document 1 sections 4.3, 6.2): the five
    # definition pages publish on the PRODUCTION marketplace at Version v3.
    # The earlier frozen rows carried staging-only v4/level S; that
    # interpretation is obsolete for these executable rows.  Every row keeps
    # default-deny through the capability gate: re-freezing a contract never
    # enables a tenant, and no read on one location activates another.
    #
    # Scopes are the five independent workflow permissions (Document 1 4.3):
    # workflows.readonly / .write / .publish / .delete / .logs.  The literal
    # operation-page slug was not captured for the added rows, so the section
    # URL is recorded and `unresolved_fields` names the missing slug.
    #
    # Effect is not inferred from the verb: POST /workflows/search is a READ,
    # and definition validate persists nothing while consuming write quota.
    _R("workflows.step_types.list", "GET", "/workflows/step-types", "v3", "D",
       PUB, PIT_OR_OAUTH, "query.locationId", False, False, "B-WORKFLOW-BETA",
       DOCS + "/ghl/workflows/", scopes=("workflows.readonly",),
       pagination="unknown", availability="private_beta",
       unresolved=("doc_url.operation_slug", "response_schema_ref")),
    _R("workflows.definition.validate", "POST",
       "/workflows/definition/validate", "v3", "D", PUB, PIT_OR_OAUTH,
       "query.locationId", False, False, "B-WORKFLOW-BETA",
       DOCS + "/ghl/workflows/", scopes=("workflows.write",),
       effect="non_persisting_write", consumes_write_quota=True,
       approval_class="none", availability="private_beta",
       req_schema="official:workflows/validate-request",
       unresolved=("doc_url.operation_slug", "request_schema_ref",
                   "response_schema_ref")),
    _R("workflows.search", "POST", "/workflows/search", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", False, False, "B-WORKFLOW-BETA",
       DOCS + "/ghl/workflows/", scopes=("workflows.readonly",),
       effect="read", pagination="page", availability="private_beta",
       unresolved=("doc_url.operation_slug", "request_schema_ref",
                   "response_schema_ref")),
    _R("workflows.definition.read", "GET",
       "/workflows/{workflowId}/definition", "v3", "D", PUB, PIT_OR_OAUTH,
       "query.locationId", False, False, "B-WORKFLOW-BETA",
       DOCS + "/ghl/workflows/", scopes=("workflows.readonly",),
       availability="private_beta",
       unresolved=("doc_url.operation_slug", "response_schema_ref")),
    _R("workflows.definition.create", "POST", "/workflows", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", True, True, "B-WORKFLOW-BETA",
       DOCS + "/ghl/workflows/", scopes=("workflows.write",),
       approval_class="approval", availability="private_beta",
       readback="workflows.definition.read",
       unresolved=("doc_url.operation_slug", "request_schema_ref")),
    _R("workflows.definition.update", "PUT",
       "/workflows/{workflowId}/definition", "v3", "D", PUB, PIT_OR_OAUTH,
       "query.locationId", True, True, "B-WORKFLOW-BETA",
       DOCS + "/ghl/workflows/", scopes=("workflows.write",),
       approval_class="approval", availability="private_beta",
       readback="workflows.definition.read",
       unresolved=("doc_url.operation_slug", "request_schema_ref")),
    _R("workflows.status.publish", "PUT", "/workflows/{workflowId}/status",
       "v3", "D", PUB, PIT_OR_OAUTH, "query.locationId", True, True,
       "B-WORKFLOW-BETA", DOCS + "/ghl/workflows/",
       scopes=("workflows.publish",), approval_class="approval",
       availability="private_beta", readback="workflows.definition.read",
       unresolved=("doc_url.operation_slug", "request_schema_ref")),
    _R("workflows.definition.delete", "DELETE", "/workflows/{workflowId}",
       "v3", "D", PUB, PIT_OR_OAUTH, "query.locationId", True, True,
       "B-WORKFLOW-BETA", DOCS + "/ghl/workflows/",
       scopes=("workflows.delete",), approval_class="destructive",
       availability="private_beta",
       unresolved=("doc_url.operation_slug",)),
    # Workflow logs (Section 6.2 row list; contract details V11/V13): 30-day
    # query windows, 60-day retention, opaque cursors, scope workflows.logs.
    # Aggregate counts are event/cohort facts, never cohort-conversion proof.
    _R("workflows.logs.list", "GET", "/workflows/{workflowId}/logs", "v3",
       "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "B-WORKFLOW-BETA", DOCS + "/ghl/workflows/",
       scopes=("workflows.logs",), pagination="cursor",
       availability="private_beta", required_query=("locationId",),
       documented_query=("locationId", "startDate", "endDate", "action",
                         "referenceId", "referenceCreatedAt", "limit",
                         "statuses", "types", "stepId", "removedReasons",
                         "contactId", "executionId"),
       query_constraints=(
           ("startDate", "ISO 8601 UTC; send with endDate; at most 30 days apart"),
           ("endDate", "ISO 8601 UTC; send with startDate; at most 30 days apart"),
           ("action", "first (default) or next"),
           ("referenceId", "nextCursor.referenceId; required with action=next"),
           ("referenceCreatedAt", "nextCursor.referenceCreatedAt; required with action=next"),
           ("limit", "1..100 records per page; default 15"),
           ("retention", "logs are available for the last 60 days"),
       ),
       unresolved=("doc_url.operation_slug", "response_schema_ref")),
    # WF25 reads the monitoring row as ``workflows.logs`` while Document 1
    # section 6.2 names ``workflows.logs.list``.  Both ids are declared and
    # point at the same route and effect; they are one operation, never two.
    _R("workflows.logs", "GET", "/workflows/{workflowId}/logs", "v3",
       "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "B-WORKFLOW-BETA", DOCS + "/ghl/workflows/",
       scopes=("workflows.logs",), pagination="cursor",
       availability="private_beta", required_query=("locationId",),
       documented_query=("locationId", "startDate", "endDate", "action",
                         "referenceId", "referenceCreatedAt", "limit",
                         "statuses", "types", "stepId", "removedReasons",
                         "contactId", "executionId"),
       query_constraints=(
           ("startDate", "ISO 8601 UTC; send with endDate; at most 30 days apart"),
           ("endDate", "ISO 8601 UTC; send with startDate; at most 30 days apart"),
           ("action", "first (default) or next"),
           ("referenceId", "nextCursor.referenceId; required with action=next"),
           ("referenceCreatedAt", "nextCursor.referenceCreatedAt; required with action=next"),
           ("limit", "1..100 records per page; default 15"),
           ("retention", "logs are available for the last 60 days"),
       ),
       unresolved=("operation_id.alias_of_workflows.logs.list",
                   "doc_url.operation_slug", "response_schema_ref")),
    _R("workflows.logs.aggregate", "GET",
       "/workflows/{workflowId}/logs/aggregate", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "B-WORKFLOW-BETA",
       DOCS + "/ghl/workflows/", scopes=("workflows.logs",),
       availability="private_beta", required_query=("locationId",),
       documented_query=("locationId", "startDate", "endDate", "groupBy",
                         "statuses", "types", "stepId", "removedReasons",
                         "timezone", "limit"),
       query_constraints=(
           ("startDate", "ISO 8601 UTC; send with endDate; at most 30 days apart"),
           ("endDate", "ISO 8601 UTC; send with startDate; at most 30 days apart"),
           ("groupBy", "status, type, stepId, removedReason, or one of week/day/hour"),
           ("timezone", "IANA zone for bucket labels; startDate/endDate stay UTC"),
           ("limit", "maximum grouped rows; default 1000, maximum 5000; overflow is refused 422"),
       ),
       unresolved=("doc_url.operation_slug", "response_schema_ref")),
    _R("workflows.restore", UNKNOWN, UNKNOWN, None, "undocumented", GAP,
       NO_AUTH, "n/a", False, False, "B-RESTORE-NONE", None),
    _R("workflows.private.list", "GET", "/workflow/{loc}/list",
       _PRIVATE_VERSION, "internal", S44P, FIREBASE, "path.locationId", False,
       False, "B-INTERNAL", None),
    _R("workflows.private.get", "GET", "/workflow/{loc}/{wf}",
       _PRIVATE_VERSION, "internal", S44P, FIREBASE, "path.locationId", False,
       False, "B-INTERNAL", None),
    _R("workflows.private.create", "POST", "/workflow/{loc}",
       _PRIVATE_VERSION, "internal", S44P, FIREBASE, "path.locationId", True,
       False, "B-INTERNAL", None),
    _R("workflows.private.save", "PUT", "/workflow/{loc}/{wf}",
       _PRIVATE_VERSION, "internal", S44P, FIREBASE, "path.locationId", True,
       False, "B-INTERNAL", None),
    _R("workflows.private.trigger.link", "POST", "/workflow/{loc}/trigger",
       _PRIVATE_VERSION, "internal", S44P, FIREBASE, "path.locationId", True,
       False, "B-INTERNAL", None),
    _R("workflows.private.publish", "PUT", "/workflow/{loc}/{wf}",
       _PRIVATE_VERSION, "internal", S44P, FIREBASE, "path.locationId", True,
       True, "B-INTERNAL", None),
    _R("mcp.list_locations", "MCP", UNKNOWN, None, "D", MCP, OAUTH,
       "connection scope", False, False, "B-MCP-AUTH",
       DOCS + "/other/mcp"),
    _R("mcp.search_operations", "MCP", UNKNOWN, None, "D", MCP, OAUTH,
       "connection scope", False, False, "B-MCP-AUTH",
       DOCS + "/other/mcp"),
    _R("mcp.describe_operation", "MCP", UNKNOWN, None, "D", MCP, OAUTH,
       "connection scope", False, False, "B-MCP-AUTH",
       DOCS + "/other/mcp"),
    # "Ap = per op" in the freeze: the catalog id is runtime-discovered, so
    # approval is recorded as required and the adapter fails closed rather
    # than letting an undiscovered operation run unapproved.
    _R("mcp.execute_operation", "MCP", UNKNOWN, None, "D", MCP, OAUTH,
       "connection scope", True, True, "B-MCP-CATALOG",
       DOCS + "/other/mcp"),
)

# F6 (GHL-168): ``workflows.list`` above declares Version ``v3``, but the
# recorded live 200 for GET /workflows/ used ``2021-07-28``
# (GHL_UPDATES_live-ledger.md line 759).  Which Version the endpoint requires
# is NOT determinable without a new live call, so the row is deliberately
# unchanged.  Named blocker: B-WORKFLOWS-LIST-VERSION
# (evidence/W23/f6-workflows-list-version.md).

# ---------------------------------------------------------------------------
# 5.8 Agency (Document 1 section 7.2)
#
# POST /locations is an Agency Pro operation: it needs an Agency Token and the
# documented agency company context, never a sub-account PIT and never a
# Command Center company UUID.  The plan category is an owner-supplied fact;
# the executing credential and the live response are still unverified, so the
# row stays default-deny.  The exact Version literal published beside this
# operation was not captured, and the agency identity rides the token plus the
# body `companyId`, so no location path/query binding exists.
# ---------------------------------------------------------------------------
AGENCY_AUTH: tuple[AuthKind, ...] = (AuthKind.agency_pit,)

_AGENCY: tuple[OperationRow, ...] = ()
# WF05 reconciliation: the documented public sub-account create is frozen as
# ``locations.create`` above.  No second agency row is declared here.


# ---------------------------------------------------------------------------
# 5.9 Courses (Document 1 sections 8.2-8.7)
#
# Only the paths the contract states literally are frozen as routes.  The
# category, lesson and offer create paths and the product-enrollment read path
# are NOT stated in the implementation contract this lane read, so they are
# recorded as named capability gaps with UNKNOWN path -- never guessed.  The
# lesson-quiz contract is inherited source evidence, not re-verified here
# (Document 1 line 2702), so its request/response schemas stay unresolved.
# Course ids are never commerce product ids.
# ---------------------------------------------------------------------------
_COURSES: tuple[OperationRow, ...] = (
    # WF06 exact ids.  Paths Document 1 section 8.3 states literally are
    # frozen; a Version literal it did not publish stays ``None`` with
    # ``version_state="unverified"`` and the field named unresolved, so a caller
    # refuses rather than inheriting a CRUD default.  Category/lesson/offer and
    # product-enrollment paths are named gaps, never guessed.  The lesson-quiz
    # contract is inherited source evidence, not re-verified here (Document 1
    # line 2702).  Course ids are never commerce product ids.
    _R("courses.products.create", "POST", "/courses/products", None, "D", PUB,
       PIT_OR_OAUTH, "query.locationId", True, False,
       "B-COURSE-VERSION-UNVERIFIED", DOCS + "/ghl/courses/",
       version_state="unverified", scopes=("courses.write",),
       readback="courses.products.get", availability="public",
       unresolved=("version", "request_schema_ref", "response_schema_ref")),
    _R("courses.products.get", "GET", UNKNOWN, None, "undocumented", GAP,
       NO_AUTH, "unknown", False, False, "B-COURSE-PATH-UNVERIFIED", None,
       availability="feature_gap", version_state="unverified",
       unresolved=("path_template", "version", "response_schema_ref")),
    _R("courses.categories.create", "POST", UNKNOWN, None, "undocumented", GAP,
       NO_AUTH, "unknown", True, False, "B-COURSE-PATH-UNVERIFIED", None,
       availability="feature_gap", version_state="unverified",
       unresolved=("path_template", "version", "scopes", "request_schema_ref")),
    _R("courses.lessons.create", "POST", UNKNOWN, None, "undocumented", GAP,
       NO_AUTH, "unknown", True, False, "B-COURSE-PATH-UNVERIFIED", None,
       availability="feature_gap", version_state="unverified",
       unresolved=("path_template", "version", "scopes", "request_schema_ref")),
    _R("courses.imports.submit", "POST",
       "/courses/courses-exporter/public/import", "2021-07-28", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       "https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/apps/courses.json",
       scopes=("courses.write",), availability="public", pagination="none",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("courses.enrollments.create", "POST", "/courses/enrollments", None, "D",
       PUB, PIT_OR_OAUTH, "body.locationId", True, False,
       "B-COURSE-VERSION-UNVERIFIED", DOCS + "/ghl/courses/",
       version_state="unverified", scopes=("courses.write",),
       availability="public", unresolved=("version", "request_schema_ref")),
    _R("courses.product_enrollments.list", "GET", UNKNOWN, None,
       "undocumented", GAP, NO_AUTH, "unknown", False, False,
       "B-COURSE-PATH-UNVERIFIED", None, availability="feature_gap",
       pagination="cursor", version_state="unverified",
       unresolved=("path_template", "version", "cursor_parameter_names",
                   "response_schema_ref")),
    _R("courses.offers.create", "POST", UNKNOWN, None, "undocumented", GAP,
       NO_AUTH, "unknown", True, False, "B-COURSE-PATH-UNVERIFIED", None,
       availability="feature_gap", version_state="unverified",
       unresolved=("path_template", "version", "offer_body_schema")),
    _R("courses.offers.revoke", "DELETE", UNKNOWN, None, "undocumented", GAP,
       NO_AUTH, "unknown", True, True, "B-COURSE-PATH-UNVERIFIED", None,
       availability="feature_gap", version_state="unverified",
       unresolved=("path_template", "method_and_body", "version")),
    _R("courses.quizzes.create", "POST",
       "/courses/products/{productId}/lessons/{lessonId}/quiz", None, "D", PUB,
       PIT_OR_OAUTH, "query.locationId", True, False,
       "B-COURSE-VERSION-UNVERIFIED", DOCS + "/ghl/courses/",
       version_state="unverified", scopes=("courses.write",),
       availability="public",
       unresolved=("version", "request_schema_ref", "response_schema_ref")),
    _R("courses.quizzes.questions.upsert", "PUT",
       "/courses/products/{productId}/quizzes/{quizId}/questions", None, "D",
       PUB, PIT_OR_OAUTH, "query.locationId", True, False,
       "B-COURSE-VERSION-UNVERIFIED", DOCS + "/ghl/courses/",
       version_state="unverified", scopes=("courses.write",),
       availability="public",
       unresolved=("version", "request_schema_ref", "response_schema_ref")),
)


# Vendor machine-readable contracts retrieved 2026-11-08.  The marketplace
# pages render an application shell; these raw OpenAPI documents are the
# documentation source the marketplace renders, and every literal below is
# transcribed from them.  Retrieval is not a live API call and never enables a
# tenant.
_VOICE_DOC = "https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/apps/voice-ai.json"
_CONVERSATION_DOC = "https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/apps/conversation-ai.json"
_STUDIO_DOC = "https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/apps/agent-studio.json"
_KB_DOC = "https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/apps/knowledge-base.json"
_WIDGET_DOC = "https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/apps/v3/chat-widget-v3.json"
# Schema pointers are file-relative, mirroring the vendor documents' own
# citation style (they already write "../common/common-schemas.json#/...").
_KB_SPEC = "apps/knowledge-base.json"
_CONVERSATION_SPEC = "apps/conversation-ai.json"

_NATIVE_FAMILIES: tuple[OperationRow, ...] = (
    # -- Native Voice AI (WF27; apps/voice-ai.json, Version 2021-04-15) --------
    _R("voiceAi.agents.list", "GET", "/voice-ai/agents", "2021-04-15", "D",
       PUB, PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       _VOICE_DOC, scopes=("voice-ai-agents.readonly",),
       availability="public", pagination="page",
       required_query=("locationId",),
       documented_query=("locationId", "page", "pageSize", "query"),
       unresolved=("response_schema_ref",)),
    _R("voiceAi.agents.get", "GET", "/voice-ai/agents/{agentId}", "2021-04-15",
       "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "A-UNVERIFIED", _VOICE_DOC, scopes=("voice-ai-agents.readonly",),
       availability="public", required_query=("locationId",),
       unresolved=("response_schema_ref",)),
    _R("voiceAi.agents.create", "POST", "/voice-ai/agents", "2021-04-15", "D",
       PUB, PIT_OR_OAUTH, "body.locationId", True, True, "A-UNVERIFIED",
       _VOICE_DOC, scopes=("voice-ai-agents.write",), approval_class="approval",
       availability="public", readback="voiceAi.agents.list",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("voiceAi.agents.update", "PATCH", "/voice-ai/agents/{agentId}",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "query.locationId", True, True,
       "A-UNVERIFIED", _VOICE_DOC, scopes=("voice-ai-agents.write",),
       approval_class="approval", availability="public",
       required_query=("locationId",), readback="voiceAi.agents.get",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("voiceAi.actions.get", "GET", "/voice-ai/actions/{actionId}",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "A-UNVERIFIED", _VOICE_DOC, scopes=("voice-ai-agent-goals.readonly",),
       availability="public", required_query=("locationId",),
       unresolved=("response_schema_ref",)),
    _R("voiceAi.actions.create", "POST", "/voice-ai/actions", "2021-04-15", "D",
       PUB, PIT_OR_OAUTH, "body.locationId", True, True, "A-UNVERIFIED",
       _VOICE_DOC, scopes=("voice-ai-agent-goals.write",),
       approval_class="approval", availability="public",
       readback="voiceAi.actions.get",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("voiceAi.actions.update", "PUT", "/voice-ai/actions/{actionId}",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "body.locationId", True, True,
       "A-UNVERIFIED", _VOICE_DOC, scopes=("voice-ai-agent-goals.write",),
       approval_class="approval", availability="public",
       readback="voiceAi.actions.get",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("voiceAi.calls.list", "GET", "/voice-ai/dashboard/call-logs",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "A-UNVERIFIED", _VOICE_DOC, scopes=("voice-ai-dashboard.readonly",),
       availability="public", pagination="page", required_query=("locationId",),
       documented_query=("locationId", "agentId", "contactId", "callType",
                         "startDate", "endDate", "actionType", "sortBy", "sort",
                         "page", "pageSize"),
       unresolved=("response_schema_ref",)),
    _R("voiceAi.calls.get", "GET", "/voice-ai/dashboard/call-logs/{callId}",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "A-UNVERIFIED", _VOICE_DOC, scopes=("voice-ai-dashboard.readonly",),
       availability="public", required_query=("locationId",),
       unresolved=("response_schema_ref",)),
    # -- Native Conversation AI (WF28/WF30; apps/conversation-ai.json) --------
    _R("conversation_ai.agents.list", "GET", "/conversation-ai/agents/search",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "implicit-pit", False, False,
       "A-UNVERIFIED", _CONVERSATION_DOC, scopes=("conversation-ai.readonly",),
       availability="public", pagination="cursor",
       documented_query=("startAfter", "limit", "query"),
       unresolved=("response_schema_ref",)),
    _R("conversation_ai.agents.get", "GET",
       "/conversation-ai/agents/{agentId}", "2021-04-15", "D", PUB,
       PIT_OR_OAUTH, "implicit-pit", False, False, "A-UNVERIFIED",
       _CONVERSATION_DOC, scopes=("conversation-ai.readonly",),
       availability="public",
       resp_schema=_CONVERSATION_SPEC + "#/components/schemas/EmployeeResponseDTO"),
    _R("conversation_ai.agents.create", "POST", "/conversation-ai/agents",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "implicit-pit", True, True,
       "A-UNVERIFIED", _CONVERSATION_DOC, scopes=("conversation-ai.write",),
       approval_class="approval", availability="public",
       readback="conversation_ai.agents.list",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("conversation_ai.agents.update", "PUT",
       "/conversation-ai/agents/{agentId}", "2021-04-15", "D", PUB,
       PIT_OR_OAUTH, "implicit-pit", True, True, "A-UNVERIFIED",
       _CONVERSATION_DOC, scopes=("conversation-ai.write",),
       approval_class="approval", availability="public",
       readback="conversation_ai.agents.get",
       req_schema=_CONVERSATION_SPEC + "#/components/schemas/UpdateEmployeeDto",
       resp_schema=_CONVERSATION_SPEC + "#/components/schemas/EmployeeResponseDTO"),
    # -- Agent Studio Flow Agents (WF29; apps/agent-studio.json) --------------
    _R("agentStudio.agents.list", "GET", "/agent-studio/agent", "2021-04-15",
       "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "A-UNVERIFIED", _STUDIO_DOC, scopes=("agent-studio.readonly",),
       availability="public", pagination="offset",
       required_query=("locationId", "limit", "offset"),
       documented_query=("locationId", "isPublished", "limit", "offset",
                         "source"),
       unresolved=("response_schema_ref",)),
    _R("agentStudio.agents.create", "POST", "/agent-studio/agent",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "body.locationId", True, True,
       "A-UNVERIFIED", _STUDIO_DOC, scopes=("agent-studio.write",),
       approval_class="approval", availability="public",
       readback="agentStudio.agents.list",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("agentStudio.agents.read", "GET", "/agent-studio/agent/{agentId}",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "A-UNVERIFIED", _STUDIO_DOC, scopes=("agent-studio.readonly",),
       availability="public", required_query=("locationId",),
       unresolved=("response_schema_ref",)),
    _R("agentStudio.agents.metadata.update", "PATCH",
       "/agent-studio/agent/{agentId}", "2021-04-15", "D", PUB,
       PIT_OR_OAUTH, "none", True, True, "A-UNVERIFIED", _STUDIO_DOC,
       scopes=("agent-studio.write",), approval_class="approval",
       availability="public", unresolved=("request_schema_ref",
                                           "response_schema_ref")),
    _R("agentStudio.versions.update", "PATCH",
       "/agent-studio/agent/versions/{versionId}", "2021-04-15", "D", PUB,
       PIT_OR_OAUTH, "none", True, True, "A-UNVERIFIED", _STUDIO_DOC,
       scopes=("agent-studio.write",), approval_class="approval",
       availability="public", unresolved=("request_schema_ref",
                                           "response_schema_ref")),
    _R("agentStudio.versions.promote", "POST",
       "/agent-studio/agent/versions/{versionId}/publish", "2021-04-15", "D",
       PUB, PIT_OR_OAUTH, "none", True, True, "A-UNVERIFIED", _STUDIO_DOC,
       scopes=("agent-studio.write",), approval_class="approval",
       availability="public", readback="agentStudio.agents.read",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("agentStudio.agents.execute", "POST",
       "/agent-studio/agent/{agentId}/execute", "2021-04-15", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, True, "A-UNVERIFIED",
       _STUDIO_DOC, scopes=("agent-studio.write",), approval_class="approval",
       availability="public", unresolved=("request_schema_ref",
                                           "response_schema_ref")),
    # -- Knowledge Bases (WF30; apps/knowledge-base.json, Version 2021-04-15) -
    _R("knowledge_bases.list", "GET", "/knowledge-bases/", "2021-04-15", "D",
       PUB, PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       _KB_DOC, scopes=("knowledge-bases.readonly",), availability="public",
       pagination="cursor", required_query=("locationId",),
       documented_query=("locationId", "query", "limit",
                         "lastKnowledgeBaseId"),
       resp_schema=_KB_SPEC + "#/components/schemas/GetAllKnowledgeBasesPaginatedResponseDTO"),
    _R("knowledge_bases.get", "GET", "/knowledge-bases/{knowledgeBaseId}",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "path.knowledgeBaseId", False,
       False, "A-UNVERIFIED", _KB_DOC, scopes=("knowledge-bases.readonly",),
       availability="public",
       resp_schema=_KB_SPEC + "#/components/schemas/GetKnowledgeBaseByIdResponseDTO"),
    _R("knowledge_bases.create", "POST", "/knowledge-bases/", "2021-04-15", "D",
       PUB, PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       _KB_DOC, scopes=("knowledge-bases.write",), availability="public",
       readback="knowledge_bases.get",
       req_schema=_KB_SPEC + "#/components/schemas/CreateKnowledgeBaseDTO",
       resp_schema=_KB_SPEC + "#/components/schemas/CreateKnowledgeBaseResponseDTO"),
    _R("knowledge_bases.update", "PUT", "/knowledge-bases/{id}", "2021-04-15",
       "D", PUB, PIT_OR_OAUTH, "path.id", True, False, "A-UNVERIFIED",
       _KB_DOC, scopes=("knowledge-bases.write",), availability="public",
       readback="knowledge_bases.get",
       req_schema=_KB_SPEC + "#/components/schemas/UpdateKnowledgeBaseDTO",
       resp_schema=_KB_SPEC + "#/components/schemas/UpdateKnowledgeBaseResponseDTO"),
    _R("knowledge_bases.delete", "DELETE",
       "/knowledge-bases/{knowledgeBaseId}", "2021-04-15", "D", PUB,
       PIT_OR_OAUTH, "path.knowledgeBaseId", True, True, "A-UNVERIFIED",
       _KB_DOC, scopes=("knowledge-bases.write",), approval_class="destructive",
       availability="public",
       resp_schema=_KB_SPEC + "#/components/schemas/DeleteKnowledgeBaseResponseDTO"),
    _R("knowledge_bases.crawler.discover", "POST", "/knowledge-bases/crawler",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "body.locationId", True, False,
       "A-UNVERIFIED", _KB_DOC, scopes=("knowledge-bases.write",),
       availability="public", readback="knowledge_bases.crawler.status",
       req_schema=_KB_SPEC + "#/components/schemas/DiscoverWebsiteRequestDTO",
       resp_schema=_KB_SPEC + "#/components/schemas/DiscoverWebsiteResponseDTO"),
    _R("knowledge_bases.crawler.status", "GET",
       "/knowledge-bases/crawler/status", "2021-04-15", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       _KB_DOC, scopes=("knowledge-bases.readonly",), availability="public",
       required_query=("locationId", "operationId", "knowledgeBaseId"),
       resp_schema=_KB_SPEC + "#/components/schemas/CrawlingStatusResponseDTO"),
    _R("knowledge_bases.crawler.train", "POST",
       "/knowledge-bases/crawler/train", "2021-04-15", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED", _KB_DOC,
       scopes=("knowledge-bases.write",), availability="public",
       readback="knowledge_bases.crawler.status",
       req_schema=_KB_SPEC + "#/components/schemas/TrainDiscoveredUrlsDTO",
       resp_schema=_KB_SPEC + "#/components/schemas/TrainDiscoveredUrlsResponseDTO"),
    _R("knowledge_bases.crawler.urls", "GET", "/knowledge-bases/crawler",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "A-UNVERIFIED", _KB_DOC, scopes=("knowledge-bases.readonly",),
       availability="public", pagination="page",
       required_query=("knowledgeBaseId", "locationId"),
       documented_query=("knowledgeBaseId", "locationId", "page",
                         "pageLength", "query"),
       resp_schema=_KB_SPEC + "#/components/schemas/GetAllUrlsByKnowledgeBaseResponseDTO"),
    _R("knowledge_bases.crawler.delete_urls", "DELETE",
       "/knowledge-bases/crawler", "2021-04-15", "D", PUB, PIT_OR_OAUTH,
       "body.locationId", True, True, "A-UNVERIFIED", _KB_DOC,
       scopes=("knowledge-bases.write",), approval_class="destructive",
       availability="public",
       req_schema=_KB_SPEC + "#/components/schemas/DeleteWebsiteUrlRequestDTO",
       resp_schema=_KB_SPEC + "#/components/schemas/DeleteWebsiteUrlResponseDTO"),
    _R("knowledge_bases.faqs.list", "GET", "/knowledge-bases/faqs",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "A-UNVERIFIED", _KB_DOC, scopes=("knowledge-bases.readonly",),
       availability="public", pagination="cursor",
       required_query=("knowledgeBaseId", "locationId"),
       documented_query=("knowledgeBaseId", "locationId", "limit", "lastFaqId"),
       resp_schema=_KB_SPEC + "#/components/schemas/ListFaqsResponseDTO"),
    _R("knowledge_bases.faqs.create", "POST", "/knowledge-bases/faqs",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "body.locationId", True, False,
       "A-UNVERIFIED", _KB_DOC, scopes=("knowledge-bases.write",),
       availability="public", readback="knowledge_bases.faqs.list",
       req_schema=_KB_SPEC + "#/components/schemas/AddFaqDTO",
       resp_schema=_KB_SPEC + "#/components/schemas/CreateFaqResponseDTO"),
    _R("knowledge_bases.faqs.update", "PUT", "/knowledge-bases/faqs/{id}",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "path.id", True, False,
       "A-UNVERIFIED", _KB_DOC, scopes=("knowledge-bases.write",),
       availability="public", readback="knowledge_bases.faqs.list",
       req_schema=_KB_SPEC + "#/components/schemas/UpdateFaqBodyDTO",
       resp_schema=_KB_SPEC + "#/components/schemas/UpdateFaqResponseDTO"),
    _R("knowledge_bases.faqs.delete", "DELETE", "/knowledge-bases/faqs/{id}",
       "2021-04-15", "D", PUB, PIT_OR_OAUTH, "path.id", True, True,
       "A-UNVERIFIED", _KB_DOC, scopes=("knowledge-bases.write",),
       approval_class="destructive", availability="public",
       resp_schema=_KB_SPEC + "#/components/schemas/DeleteFaqResponseDTO"),
    # File sources: no published vendor operation exists in
    # apps/knowledge-base.json.  The row declares the required multipart media
    # type (so WF01 can never send guessed JSON) and NO route; WF30 refuses with
    # ``file_upload_contract_unresolved`` until a documented operation exists.
    _R("knowledge_bases.sources.upload", "POST", UNKNOWN, None,
       "undocumented", GAP, NO_AUTH, "unknown", True, False, "B-NO-CONTRACT",
       None, media="multipart/form-data", availability="feature_gap",
       unresolved=("method", "path_template", "version", "scopes",
                   "request_schema_ref", "size_limit", "media_type")),
    # -- Chat Widgets (WF31; apps/v3/chat-widget-v3.json, Version v3) ---------
    _R("chat_widgets.list", "GET", "/chat-widget/list", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       _WIDGET_DOC, scopes=("chat-widget.readonly",), availability="public",
       pagination="page", required_query=("locationId", "offset", "limit"),
       documented_query=("locationId", "offset", "limit", "chatType",
                         "excludeChatType", "voiceAiAgentId",
                         "allInOneChatTypes"),
       unresolved=("response_schema_ref",)),
    _R("chat_widgets.get", "GET", "/chat-widget/data/{locationId}/{id}", "v3",
       "D", PUB, PIT_OR_OAUTH, "path.locationId", False, False,
       "A-UNVERIFIED", _WIDGET_DOC, scopes=("chat-widget.readonly",),
       availability="public", unresolved=("response_schema_ref",)),
    _R("chat_widgets.create", "POST", "/chat-widget/", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       _WIDGET_DOC, scopes=("chat-widget.write",), availability="public",
       readback="chat_widgets.list",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("chat_widgets.update", "PUT", "/chat-widget/data/{locationId}/{id}",
       "v3", "D", PUB, PIT_OR_OAUTH, "path.locationId", True, False,
       "A-UNVERIFIED", _WIDGET_DOC, scopes=("chat-widget.write",),
       availability="public", readback="chat_widgets.get",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("chat_widgets.patch", "PATCH",
       "/chat-widget/data/{locationId}/{id}", "v3", "D", PUB, PIT_OR_OAUTH,
       "path.locationId", True, False, "A-UNVERIFIED", _WIDGET_DOC,
       scopes=("chat-widget.write",), availability="public",
       readback="chat_widgets.get",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("chat_widgets.delete", "DELETE", "/chat-widget/{locationId}/{id}",
       "v3", "D", PUB, PIT_OR_OAUTH, "path.locationId", True, True,
       "A-UNVERIFIED", _WIDGET_DOC, scopes=("chat-widget.write",),
       approval_class="destructive", availability="public",
       unresolved=("response_schema_ref",)),
    _R("chat_widgets.clone", "POST", "/chat-widget/clone", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       _WIDGET_DOC, scopes=("chat-widget.write",), availability="public",
       readback="chat_widgets.list",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("chat_widgets.public_config", "GET",
       "/chat-widget/public/config/{id}", "v3", "D", PUB, NO_AUTH,
       "path.id", False, False, "A-UNVERIFIED", _WIDGET_DOC,
       availability="public", documented_query=("id", "version"),
       query_constraints=((
           "version",
           "numeric widget configuration version in the body/schema, never "
           "the HTTP Version header",
       ),),
       unresolved=("response_schema_ref", "query.version_requiredness")),
    # -- Projects (Document 1 section 21.4; private beta, UI is separate) -----
    _R("projects.spaces.create", "POST", "/projects/spaces", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "B-PROJECTS-BETA",
       DOCS + "/ghl/projects/projects-api/",
       scopes=("projects/workspace.write",), availability="private_beta",
       unresolved=("request_schema_ref", "response_schema_ref",
                   "ui_availability")),
    _R("projects.tasks.create", "POST", "/projects/lists/{listId}/tasks",
       "v3", "D", PUB, PIT_OR_OAUTH, "body.locationId", True, False,
       "B-PROJECTS-BETA", DOCS + "/ghl/projects/create-projects-list-task/",
       scopes=("projects/tasks.write",), availability="private_beta",
       unresolved=("request_schema_ref", "response_schema_ref")),
)

_ROWS: tuple[OperationRow, ...] = (
    _LOCATIONS
    + _CONTACTS
    + _OPPORTUNITIES
    + _CONVERSATIONS_CALENDARS
    + _PAYMENTS
    + _CONTENT
    + _SOCIAL
    + _WORKFLOWS_MCP
    + _AGENCY
    + _COURSES
    + _NATIVE_FAMILIES
)

# ---------------------------------------------------------------------------
# Documentation provenance (revision 3.0, Document 1 section 34.1)
#
# The revision says explicitly that not every official source was reopened, and
# that a citation to inherited evidence is not a fresh live test.  A row added
# from the specification therefore records ``revision3_spec`` and the date the
# specification supplied the contract -- never the 2026-10-18 freeze date and
# never a fabricated fetch timestamp.  Rows whose page WAS reopened carry the
# recheck date Document 1 Section 34.4 names.
# ---------------------------------------------------------------------------
_ROW_DOC_EVIDENCE: dict[str, str] = {
    "workflows.definition.read": "reopened_2026-11-07",
    "workflows.definition.create": "reopened_2026-11-07",
    "workflows.definition.update": "reopened_2026-11-07",
    "workflows.status.publish": "reopened_2026-11-07",
    "workflows.definition.delete": "reopened_2026-11-07",
    "workflows.logs.list": "reopened_2026-11-08",
    "workflows.logs": "reopened_2026-11-08",
    "workflows.logs.aggregate": "reopened_2026-11-08",
    "funnels.list": "reopened_2026-11-08",
    "funnels.pages.list": "reopened_2026-11-08",
    "funnels.pages.count": "reopened_2026-11-08",
    "courses.imports.submit": "reopened_2026-11-08",
    "voiceAi.agents.list": "reopened_2026-11-08",
    "voiceAi.agents.get": "reopened_2026-11-08",
    "voiceAi.agents.create": "reopened_2026-11-08",
    "voiceAi.agents.update": "reopened_2026-11-08",
    "voiceAi.actions.get": "reopened_2026-11-08",
    "voiceAi.actions.create": "reopened_2026-11-08",
    "voiceAi.actions.update": "reopened_2026-11-08",
    "voiceAi.calls.list": "reopened_2026-11-08",
    "voiceAi.calls.get": "reopened_2026-11-08",
    "conversation_ai.agents.list": "reopened_2026-11-08",
    "conversation_ai.agents.get": "reopened_2026-11-08",
    "conversation_ai.agents.create": "reopened_2026-11-08",
    "conversation_ai.agents.update": "reopened_2026-11-08",
    "agentStudio.agents.list": "reopened_2026-11-08",
    "agentStudio.agents.create": "reopened_2026-11-08",
    "agentStudio.agents.read": "reopened_2026-11-08",
    "agentStudio.agents.metadata.update": "reopened_2026-11-08",
    "agentStudio.versions.update": "reopened_2026-11-08",
    "agentStudio.versions.promote": "reopened_2026-11-08",
    "agentStudio.agents.execute": "reopened_2026-11-08",
    "knowledge_bases.list": "reopened_2026-11-08",
    "knowledge_bases.get": "reopened_2026-11-08",
    "knowledge_bases.create": "reopened_2026-11-08",
    "knowledge_bases.update": "reopened_2026-11-08",
    "knowledge_bases.delete": "reopened_2026-11-08",
    "knowledge_bases.crawler.discover": "reopened_2026-11-08",
    "knowledge_bases.crawler.status": "reopened_2026-11-08",
    "knowledge_bases.crawler.train": "reopened_2026-11-08",
    "knowledge_bases.crawler.urls": "reopened_2026-11-08",
    "knowledge_bases.crawler.delete_urls": "reopened_2026-11-08",
    "knowledge_bases.faqs.list": "reopened_2026-11-08",
    "knowledge_bases.faqs.create": "reopened_2026-11-08",
    "knowledge_bases.faqs.update": "reopened_2026-11-08",
    "knowledge_bases.faqs.delete": "reopened_2026-11-08",
    "chat_widgets.list": "reopened_2026-11-08",
    "chat_widgets.get": "reopened_2026-11-08",
    "chat_widgets.create": "reopened_2026-11-08",
    "chat_widgets.update": "reopened_2026-11-08",
    "chat_widgets.patch": "reopened_2026-11-08",
    "chat_widgets.delete": "reopened_2026-11-08",
    "chat_widgets.clone": "reopened_2026-11-08",
    "chat_widgets.public_config": "reopened_2026-11-08",
    "projects.spaces.create": "reopened_2026-11-08",
    "projects.tasks.create": "reopened_2026-11-08",
    "workflows.step_types.list": "revision3_spec",
    "workflows.definition.validate": "revision3_spec",
    "workflows.search": "revision3_spec",
    "social.community.users.list": "revision3_spec",
    "social.community.group_users.validate": "revision3_spec",
    "social.comments.community.create": "revision3_spec",
    "locations.create": "revision3_spec",
    "courses.products.create": "revision3_spec",
    "courses.products.get": "revision3_spec",
    "courses.categories.create": "revision3_spec",
    "courses.lessons.create": "revision3_spec",
    "courses.enrollments.create": "revision3_spec",
    "courses.product_enrollments.list": "revision3_spec",
    "courses.offers.create": "revision3_spec",
    "courses.offers.revoke": "revision3_spec",
    "courses.quizzes.create": "revision3_spec",
    "courses.quizzes.questions.upsert": "revision3_spec",
    "knowledge_bases.sources.upload": "revision3_spec",
}

_DOC_EVIDENCE_DATE: dict[str, str] = {
    "reopened_2026-11-07": "2026-11-07",
    "reopened_2026-11-08": DOC_SPEC_DATE,
    "revision3_spec": DOC_SPEC_DATE,
}


def _apply_doc_evidence(
    rows: tuple[OperationRow, ...],
) -> tuple[OperationRow, ...]:
    out: list[OperationRow] = []
    for row in rows:
        basis = _ROW_DOC_EVIDENCE.get(row.operation_id, row.doc_evidence)
        if basis == row.doc_evidence:
            out.append(row)
            continue
        out.append(
            replace(
                row,
                doc_evidence=basis,
                doc_fetch_date=(
                    _DOC_EVIDENCE_DATE.get(basis) if row.doc_url else None
                ),
            )
        )
    return tuple(out)


_ROWS = _apply_doc_evidence(_ROWS)


class OperationRegistry(Mapping[str, OperationRow]):
    """Read-only operation-id -> row mapping."""

    def __init__(self, rows: tuple[OperationRow, ...]) -> None:
        table: dict[str, OperationRow] = {}
        for row in rows:
            if row.operation_id in table:
                raise ContractViolation(
                    "duplicate_operation_id", operation_id=row.operation_id
                )
            table[row.operation_id] = row
        validate(rows)
        self._table = table

    def __getitem__(self, key: str) -> OperationRow:
        return self._table[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._table)

    def __len__(self) -> int:
        return len(self._table)

    def require(self, operation_id: str) -> OperationRow:
        try:
            return self._table[operation_id]
        except KeyError:
            raise ContractViolation(
                "unknown_operation_id", operation_id=str(operation_id)
            ) from None


def validate(rows: tuple[OperationRow, ...]) -> None:
    """Import-time contract checks (freeze sections 1.4, 3.2, 5)."""

    seen: set[str] = set()
    for row in rows:
        if row.operation_id in seen:
            raise ContractViolation(
                "duplicate_operation_id", operation_id=row.operation_id
            )
        seen.add(row.operation_id)

        # No row may carry enablement.  Enablement is the capability gate's.
        if hasattr(row, "enabled"):
            raise ContractViolation(
                "row_carries_enabled", operation_id=row.operation_id
            )

        # Every documented row names a literal version.  Undocumented and
        # internal rows may not invent one.
        if row.documented_level in ("D", "S"):
            # Official MCP tools are documented but send no Version header
            # (freeze section 5.7, "Ver = none").
            # A row whose literal the evidence did not settle may record
            # ``version=None`` ONLY as an explicit unverified gap: the state is
            # ``unverified``, ``version`` is named unresolved, and a blocker
            # exists.  Callers refuse before transport on that trio.
            if row.version is None and row.route_class != "official_mcp":
                if not (
                    row.version_state == "unverified"
                    and "version" in row.unresolved_fields
                    and row.blocker is not None
                ):
                    raise ContractViolation(
                        "documented_row_without_version",
                        operation_id=row.operation_id,
                    )
            if row.doc_url is None:
                raise ContractViolation(
                    "documented_row_without_doc_url",
                    operation_id=row.operation_id,
                )

        if row.version is not None and row.documented_level in ("D", "S"):
            if row.version not in SUPPORTED_VERSIONS and row.version != "v4":
                raise ContractViolation(
                    "unsupported_version_literal",
                    operation_id=row.operation_id,
                    detail={"version": row.version},
                )
        for alternate in row.version_alternates:
            if alternate not in SUPPORTED_VERSIONS:
                raise ContractViolation(
                    "unsupported_version_alternate",
                    operation_id=row.operation_id,
                    detail={"version": alternate},
                )
            if alternate == row.version:
                raise ContractViolation(
                    "duplicate_version_alternate",
                    operation_id=row.operation_id,
                )

        if row.doc_url is None and row.blocker not in _NO_URL_BLOCKERS:
            raise ContractViolation(
                "row_without_contract_url_has_no_reason",
                operation_id=row.operation_id,
            )

        if row.scopes_candidate and row.documented_level not in ("D", "S"):
            raise ContractViolation(
                "scopes_on_undocumented_row", operation_id=row.operation_id
            )

        if row.readback_plan is not None and not row.write:
            raise ContractViolation(
                "readback_plan_on_read", operation_id=row.operation_id
            )


_NAMES: frozenset[str] = frozenset(row.operation_id for row in _ROWS)
# Re-run the readback reference check now that every name is known (a forward
# reference to a row defined later in the tuple must still resolve).
for _row in _ROWS:
    if _row.readback_plan is not None and _row.readback_plan not in _NAMES:
        raise ContractViolation(
            "readback_plan_unknown_operation",
            operation_id=_row.operation_id,
            detail={"readback": _row.readback_plan},
        )

OPERATIONS: OperationRegistry = OperationRegistry(_ROWS)

# ---------------------------------------------------------------------------
# Operation -> declared transport capability (W3 connection 7)
#
# This is a DERIVATION, not new evidence: every value below is read off the
# frozen ``route_class`` of the row above. It answers exactly one question —
# which transport the frozen contract declares for one operation — so a
# dispatcher never has to guess, and never makes a blanket claim about a whole
# tenant or a whole module.
#
#   public_direct      -> api     (public REST)
#   official_mcp       -> mcp     (official MCP tool, no Version header)
#   skill44_private    -> api     (internal rail, never the public adapter)
#   skill06_authoring  -> browser (the authoring surface IS the browser; the
#                                  docstrings of the S06 builder rows say so)
#   retired            -> none    (deprecated; no route to declare)
#   capability_gap     -> none    (NO route is established; ``unresolved`` is
#                                  true and the browser fallback is unproven,
#                                  never declared as a working route)
#   excluded           -> none    (deliberately out of scope)
#
# Nothing here carries enablement — that stays the capability gate's, per
# ``(operation_id, tenant)`` (freeze section 3.2 rule 5).
# ---------------------------------------------------------------------------

TRANSPORT_BY_ROUTE: dict[str, str | None] = {
    PUB: "api",
    MCP: "mcp",
    S44P: "api",
    S06: "browser",
    RET: None,
    GAP: None,
    EXCLUDED: None,
}

#: Rows whose ONLY declared route is the Skill 6 managed browser.
BROWSER_ONLY_ROUTES: frozenset[str] = frozenset({S06})

#: Rows for which the freeze records NO usable route at all.
UNRESOLVED_ROUTES: frozenset[str] = frozenset({GAP})


def declared_transports(operation_id: str) -> tuple[str, ...]:
    """The transports the frozen row declares for ``operation_id``.

    Empty means the row declares no usable route (retired / excluded /
    capability gap). An unknown operation raises ``ContractViolation`` exactly
    like ``OperationRegistry.require`` — never a silent empty answer.
    """

    row = OPERATIONS.require(operation_id)
    transport = TRANSPORT_BY_ROUTE.get(row.route_class)
    return () if transport is None else (transport,)


def browser_route_required(operation_id: str) -> bool:
    """True when the managed browser is the row's ONLY declared route."""

    return OPERATIONS.require(operation_id).route_class in BROWSER_ONLY_ROUTES


def operation_routes_unresolved(operation_id: str) -> bool:
    """True when the freeze records no usable route (an honest gap)."""

    return OPERATIONS.require(operation_id).route_class in UNRESOLVED_ROUTES


def capability_map() -> dict[str, dict[str, object]]:
    """The operation -> capability mapping for every frozen row.

    Per operation, never per tenant and never a module-wide claim. A caller
    that needs a real capability answer for one tenant still consults the
    capability gate; this map only says what the contract DECLARES.
    """

    mapping: dict[str, dict[str, object]] = {}
    for row in _ROWS:
        mapping[row.operation_id] = {
            "operation": row.operation_id,
            "routeClass": row.route_class,
            "transports": list(declared_transports(row.operation_id)),
            "browserRouteRequired": row.route_class in BROWSER_ONLY_ROUTES,
            "unresolved": row.route_class in UNRESOLVED_ROUTES,
            "write": row.write,
            "approvalRequired": row.approval_required,
            "tenantBinding": row.tenant_binding,
            "version": row.version,
            "effect": row.resolved_effect,
            "approvalClass": row.resolved_approval_class,
            "identityPlacement": row.identity_placement,
            "tokenClass": row.token_class,
            "requestMediaType": row.request_media_type,
            "pagination": row.pagination,
            "availability": row.resolved_availability,
            "implementation": row.implementation,
            "unresolvedFields": list(row.unresolved_fields),
        }
    return mapping


def contract_documents() -> tuple[dict[str, object], ...]:
    """Every frozen row as the shared ``operation-contract`` JSON shape.

    This is the published, hashable copy a consumer (for example the Command
    Center) reads instead of reaching into Python internals.  It is derived
    from the registry, never a second authority.
    """

    return tuple(row.as_contract() for row in _ROWS)


__all__ = [
    "OperationRow",
    "OperationRegistry",
    "OPERATIONS",
    "DOC_FETCH_DATE",
    "DOC_SPEC_DATE",
    "DOC_EVIDENCE",
    "SUPPORTED_VERSIONS",
    "MEDIA_FILE_TYPES",
    "MEDIA_TYPES",
    "EFFECTS",
    "APPROVAL_CLASSES",
    "PAGINATIONS",
    "AVAILABILITIES",
    "VERSION_STATES",
    "RECEIPT_OUTCOMES",
    "UNKNOWN",
    "TRANSPORT_BY_ROUTE",
    "BROWSER_ONLY_ROUTES",
    "UNRESOLVED_ROUTES",
    "declared_transports",
    "browser_route_required",
    "operation_routes_unresolved",
    "capability_map",
    "contract_documents",
]
