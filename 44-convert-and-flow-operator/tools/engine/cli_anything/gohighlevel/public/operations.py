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
    {"B-NO-CONTRACT", "B-INTERNAL", "B-RESTORE-NONE", "B-NO-ADAPTER"}
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

    def __post_init__(self) -> None:
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

_PAYMENTS: tuple[OperationRow, ...] = (
    _R("products.list", "GET", "/products/", "v3", "D", PUB, PIT_OR_OAUTH,
       "query.locationId", False, False, "B-COMMUNITY-RAIL",
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
    _R("funnels.list", "GET", "/funnels/", "v3", "D", PUB, PIT_OR_OAUTH,
       "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/funnels/get-funnels", alternates=("2023-02-21",)),
    _R("funnels.pages.list", "GET", "/funnels/{funnelId}/pages", "v3", "D",
       PUB, PIT_OR_OAUTH, "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/funnels/get-pages-by-funnel-id",
       alternates=("2023-02-21",)),
    _R("funnels.pages.count", "GET", "/funnels/{funnelId}/pages/count", "v3",
       "D", PUB, PIT_OR_OAUTH, "query.locationId", False, False,
       "B-NO-ADAPTER", DOCS + "/ghl/funnels/get-pages-count-by-funnel-id"),
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
       DOCS + "/ghl/medias/fetch-media-content"),
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
    _R("workflows.list", "GET", "/workflows/", "v3", "D", PUB, PIT_OR_OAUTH,
       "query.locationId", False, False, "A-UNVERIFIED",
       DOCS + "/ghl/workflows/get-workflow/", scopes=("workflows.readonly",)),
    _R("workflows.enroll", "POST",
       "/contacts/{contactId}/workflow/{workflowId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", True, False, "A-UNVERIFIED",
       DOCS + "/ghl/contacts/add-contact-to-workflow/"),
    _R("workflows.remove", "DELETE",
       "/contacts/{contactId}/workflow/{workflowId}", "v3", "D", PUB,
       PIT_OR_OAUTH, "query.locationId", True, True, "A-UNVERIFIED",
       DOCS + "/ghl/contacts/delete-contact-from-workflow/"),
    _R("workflows.definition.read", "GET",
       "/workflows/{workflowId}/definition", "v4", "S", PUB, PIT_OR_OAUTH,
       "query.locationId", False, False, "B-V4-S",
       STAGING_DOCS + "/ghl/workflows/get-workflow-definition/index.html"),
    _R("workflows.definition.create", "POST", "/workflows/", "v4", "S", PUB,
       PIT_OR_OAUTH, "query.locationId", True, True, "B-V4-S",
       STAGING_DOCS + "/ghl/workflows/create-workflow/index.html"),
    _R("workflows.definition.update", "PUT",
       "/workflows/{workflowId}/definition", "v4", "S", PUB, PIT_OR_OAUTH,
       "query.locationId", True, True, "B-V4-S",
       STAGING_DOCS + "/ghl/workflows/update-workflow-definition/index.html"),
    _R("workflows.status.publish", "PUT", "/workflows/{workflowId}/status",
       "v4", "S", PUB, PIT_OR_OAUTH, "query.locationId", True, True, "B-V4-S",
       STAGING_DOCS + "/ghl/workflows/update-workflow-status/index.html",
       scopes=("workflows.publish",)),
    _R("workflows.definition.delete", "DELETE", "/workflows/{workflowId}",
       "v4", "S", PUB, PIT_OR_OAUTH, "query.locationId", True, True, "B-V4-S",
       STAGING_DOCS + "/ghl/workflows/delete-workflow/index.html"),
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

_ROWS: tuple[OperationRow, ...] = (
    _LOCATIONS
    + _CONTACTS
    + _OPPORTUNITIES
    + _CONVERSATIONS_CALENDARS
    + _PAYMENTS
    + _CONTENT
    + _SOCIAL
    + _WORKFLOWS_MCP
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

__all__ = [
    "OperationRow",
    "OperationRegistry",
    "OPERATIONS",
    "DOC_FETCH_DATE",
    "SUPPORTED_VERSIONS",
    "UNKNOWN",
]
