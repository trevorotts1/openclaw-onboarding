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
from dataclasses import dataclass
from typing import Iterator, Literal, Mapping

from .auth import AuthKind
from .errors import ContractViolation

DOC_FETCH_DATE = "2026-10-18"
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
        }


#: Request media types a row may declare.
MEDIA_TYPES: frozenset[str] = frozenset(
    {"application/json", "multipart/form-data", "unknown"}
)
#: Read/write effect vocabularies.  The verb is never the classifier.
EFFECTS: frozenset[str] = frozenset({"read", "write", "non_persisting_write"})
APPROVAL_CLASSES: frozenset[str] = frozenset({"none", "approval", "destructive"})
PAGINATIONS: frozenset[str] = frozenset({"none", "cursor", "page", "offset", "unknown"})
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
    _R("funnels.list", "GET", "/funnels/funnel/list", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/funnels/get-funnels/", alternates=("2023-02-21",),
       pagination="page", availability="public",
       unresolved=("required_query", "scopes")),
    _R("funnels.pages.list", "GET", "/funnels/page", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/funnels/get-pages-by-funnel-id",
       alternates=("2023-02-21",), pagination="page",
       unresolved=("required_query", "scopes")),
    _R("funnels.pages.count", "GET", "/funnels/page/count", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "B-NO-ADAPTER",
       DOCS + "/ghl/funnels/get-pages-count-by-funnel-id",
       availability="public", unresolved=("required_query", "scopes")),
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
    # Community social rows (Document 1 section 11.2, scopes recorded there).
    # The word "oauth" in a scope name does not prohibit a Private Integration
    # token.  The member-list page renders inconsistently across docs views, so
    # its response schema stays unresolved instead of being invented.
    _R("social.community.accounts.users.list", "GET",
       "/social-media-posting/{locationId}/community/accounts/{accountId}/users",
       "v3", "D", PUB, PIT, "path.locationId", False, False, "B-SOCIAL-SPEC",
       SOCIAL_V3_SPEC, scopes=("socialplanner/oauth.readonly",),
       pagination="page", availability="public",
       unresolved=("response_schema_ref",)),
    _R("social.community.authors.validate", "GET",
       "/social-media-posting/{locationId}/community/groups/{groupId}/users/"
       "{contactId}/validate", "v3", "D", PUB, PIT, "path.locationId", False,
       False, "B-SOCIAL-SPEC", SOCIAL_V3_SPEC,
       scopes=("socialplanner/account.readonly",), availability="public",
       unresolved=("response_schema_ref",)),
    _R("social.community.comments.create", "POST",
       "/social-media-posting/comments/community", "v3", "D", PUB, PIT,
       "query.locationId", True, True, "B-SOCIAL-SPEC", SOCIAL_V3_SPEC,
       scopes=("socialplanner/comments.write",), readback="social.comments.list",
       availability="public", unresolved=("request_schema_ref",)),
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
       availability="private_beta",
       unresolved=("doc_url.operation_slug", "response_schema_ref")),
    _R("workflows.logs.aggregate", "GET",
       "/workflows/{workflowId}/logs/aggregate", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "B-WORKFLOW-BETA",
       DOCS + "/ghl/workflows/", scopes=("workflows.logs",),
       availability="private_beta",
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

_AGENCY: tuple[OperationRow, ...] = (
    _R("agency.locations.create", "POST", "/locations", "2021-07-28", "D",
       PUB, AGENCY_AUTH, "none", True, True, "A-UNVERIFIED",
       DOCS + "/ghl/locations/create-location", scopes=("locations.write",),
       approval_class="approval", availability="tenant_restricted",
       readback="locations.get",
       unresolved=("version", "request_schema_ref", "response_schema_ref",
                   "agency_company_id_in_body")),
)

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
    _R("courses.products.create", "POST", "/courses/products", "v3", "D",
       PUB, PIT_OR_OAUTH, "query.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/courses/", availability="public",
       readback="courses.products.read",
       unresolved=("scopes", "doc_url.operation_slug", "request_schema_ref",
                   "response_schema_ref")),
    _R("courses.products.read", "GET", "/courses/products/{courseId}", "v3",
       "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "A-UNVERIFIED", DOCS + "/ghl/courses/", availability="public",
       unresolved=("scopes", "doc_url.operation_slug", "response_schema_ref")),
    _R("courses.import.create", "POST",
       "/courses/courses-exporter/public/import", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", True, True, "B-COURSE-IMPORT",
       DOCS + "/ghl/courses/", scopes=("courses.write",),
       approval_class="approval", availability="public",
       effect="write", pagination="none",
       unresolved=("version", "request_schema_ref", "response_schema_ref")),
    _R("courses.lessons.quiz.create", "POST",
       "/courses/products/{productId}/lessons/{lessonId}/quiz", "v3", "D",
       PUB, PIT_OR_OAUTH, "query.locationId", True, False,
       "B-COURSE-QUIZ-INHERITED", DOCS + "/ghl/courses/",
       scopes=("courses.write",), availability="public",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("courses.quizzes.questions.upsert", "PUT",
       "/courses/products/{productId}/quizzes/{quizId}/questions", "v3", "D",
       PUB, PIT_OR_OAUTH, "query.locationId", True, False,
       "B-COURSE-QUIZ-INHERITED", DOCS + "/ghl/courses/",
       scopes=("courses.write",), availability="public",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("courses.enrollments.create", "POST", "/courses/enrollments", "v3",
       "D", PUB, PIT_OR_OAUTH, "body.locationId", True, True, "A-UNVERIFIED",
       DOCS + "/ghl/courses/", approval_class="approval",
       availability="public", unresolved=("scopes", "request_schema_ref")),
    # Named gaps: the contract requests these operations but the exact public
    # path was not settled by the evidence this lane read.  A future owner
    # sends the reconciled path/scope through a change request; nothing here
    # may be dispatched, because no route is declared.
    _R("courses.categories.create", "POST", UNKNOWN, None, "undocumented", GAP,
       NO_AUTH, "unknown", True, False, "B-COURSE-PATH-UNVERIFIED", None,
       availability="feature_gap",
       unresolved=("method", "path_template", "version", "scopes",
                   "request_schema_ref")),
    _R("courses.lessons.create", "POST", UNKNOWN, None, "undocumented", GAP,
       NO_AUTH, "unknown", True, False, "B-COURSE-PATH-UNVERIFIED", None,
       availability="feature_gap",
       unresolved=("method", "path_template", "version", "scopes",
                   "request_schema_ref")),
    _R("courses.offers.create", "POST", UNKNOWN, None, "undocumented", GAP,
       NO_AUTH, "unknown", True, False, "B-COURSE-PATH-UNVERIFIED", None,
       availability="feature_gap",
       unresolved=("method", "path_template", "version", "scopes",
                   "request_schema_ref")),
    _R("courses.enrollments.products.list", "GET", UNKNOWN, None,
       "undocumented", GAP, NO_AUTH, "unknown", False, False,
       "B-COURSE-PATH-UNVERIFIED", None, availability="feature_gap",
       pagination="cursor",
       unresolved=("path_template", "version", "scopes", "response_schema_ref")),
)

# ---------------------------------------------------------------------------
# 5.10 Monitoring and native AI families (Document 1 section 21.4)
#
# Vendor-contract candidates recorded from the source matrix.  Recording a row
# is not permission to execute it and is not tenant activation: every row stays
# default-deny.  Scope names are transcribed, never derived by swapping
# `.write` for `.readonly`; voice agents, actions and dashboard use distinct
# permissions.  Request/response schemas were not captured, so they stay null
# and are named as unresolved.  Projects API access is a location-specific
# private beta and its UI availability is a separate fact.
# ---------------------------------------------------------------------------
_NATIVE_FAMILIES: tuple[OperationRow, ...] = (
    _R("voice.agents.create", "POST", "/voice-ai/agents", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/voice-ai/create-agent/",
       scopes=("voice-ai-agents.write",), availability="public",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("voice.actions.create", "POST", "/voice-ai/actions", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/voice-ai/", scopes=("voice-ai-agent-goals.write",),
       availability="public",
       unresolved=("doc_url.operation_slug", "request_schema_ref",
                   "response_schema_ref")),
    _R("voice.call_logs.list", "GET", "/voice-ai/dashboard/call-logs", "v3",
       "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "A-UNVERIFIED", DOCS + "/ghl/voice-ai/",
       scopes=("voice-ai-dashboard.readonly",), pagination="cursor",
       availability="public",
       unresolved=("doc_url.operation_slug", "response_schema_ref")),
    _R("voice.call_logs.get", "GET",
       "/voice-ai/dashboard/call-logs/{callId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/voice-ai/", scopes=("voice-ai-dashboard.readonly",),
       availability="public",
       unresolved=("doc_url.operation_slug", "response_schema_ref")),
    _R("conversation.agents.create", "POST", "/conversation-ai/agents", "v3",
       "D", PUB, PIT_OR_OAUTH, "body.locationId", True, False,
       "A-UNVERIFIED", DOCS + "/ghl/conversation-ai/create-agent/",
       scopes=("conversation-ai.write",), availability="public",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("studio.agents.create", "POST", "/agent-studio/agent", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/agent-studio/create-agent/",
       scopes=("agent-studio.write",), availability="public",
       unresolved=("request_schema_ref", "response_schema_ref")),
    _R("studio.versions.publish", "POST",
       "/agent-studio/agent/versions/{versionId}/publish", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, True, "A-UNVERIFIED",
       DOCS + "/ghl/agent-studio/", scopes=("agent-studio.write",),
       approval_class="approval", availability="public",
       unresolved=("doc_url.operation_slug", "request_schema_ref")),
    _R("studio.agents.execute", "POST",
       "/agent-studio/agent/{agentId}/execute", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/agent-studio/", scopes=("agent-studio.write",),
       availability="public",
       unresolved=("doc_url.operation_slug", "request_schema_ref",
                   "response_schema_ref")),
    _R("knowledge_bases.create", "POST", "/knowledge-bases", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/knowledge-base/create-knowledge-base/",
       scopes=("knowledge-bases.write",), availability="public",
       unresolved=("request_schema_ref", "response_schema_ref")),
    # Multipart declaration point for the central transport (Document 1 21.2,
    # V04: PDF/DOC/DOCX, 10 MB).  The exact upload path and its Version were
    # not captured, so no route is declared and nothing can be dispatched.
    _R("knowledge_bases.files.upload", "POST", UNKNOWN, None, "undocumented",
       GAP, NO_AUTH, "unknown", True, False, "B-KB-UPLOAD-PATH", None,
       media="multipart/form-data", availability="feature_gap",
       unresolved=("method", "path_template", "version", "scopes",
                   "request_schema_ref", "size_limit")),
    _R("widgets.create", "POST", "/chat-widget", "v3", "D", PUB,
       PIT_OR_OAUTH, "body.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/chat-widget/create-chat-widget/",
       scopes=("chat-widget.write",), availability="public",
       unresolved=("request_schema_ref", "response_schema_ref")),
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
            if row.version is None and row.route_class != "official_mcp":
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
    "SUPPORTED_VERSIONS",
    "MEDIA_FILE_TYPES",
    "MEDIA_TYPES",
    "EFFECTS",
    "APPROVAL_CLASSES",
    "PAGINATIONS",
    "AVAILABILITIES",
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
