#!/usr/bin/env python3
"""GHL capability inventory and operation contracts (stream W2, assignment W2A-U1).

Machine-readable catalog of the CURRENT GoHighLevel (Convert and Flow) access
surface across the real transports, plus the operation contracts every delivery
router (object_router, recipe_transport, adapters) must obey.

Binding rules encoded here (GHL-DELIVERY-SPEC.md "Operation choice"):
  * Authorized MCP first -> verified documented API adapter -> managed browser
    execution for unsupported UI operations (per-surface ladders may refine the
    order; the relative MCP -> API -> browser order always holds).
  * Read/list support NEVER implies create/edit support: each entry carries the
    exact operation classes its source documents, route selection requires an
    exact operation-class match, and a dynamic surface (MCP execute_operation,
    CAF CLI) carries NO static write grant -- its operation class is confirmed
    at runtime (describe_operation / CLI help) before use.
  * Never invent endpoints or payloads. Every route below cites a file this
    repository ships. Established authenticated in-browser operations are NOT
    public APIs.
  * A retired, disabled or unverified capability is reported as incomplete,
    never as done.

Provenance is a repo-relative path (plus section where useful). Evidence levels
for the official MCP follow 36-ghl-mcp-setup/SKILL.md "Four evidence levels":
this repo asserts levels 1-2 (documented endpoint + documented catalog) only;
"observed on this box" is level 4 and needs a per-box capture we do not hold.

Runnable check:
    python3 shared-utils/ghl/capability_inventory.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple


class Transport(Enum):
    """Real access transports, cheapest first. Tier numbers per skill 36."""

    CAF_CLI = "caf_cli"                  # Tier 0 -- caf / convertandflow / ghl (skill 44)
    OFFICIAL_MCP = "official_mcp"        # Tier 1 -- hosted official GHL MCP (OAuth)
    COMMUNITY_MCP = "community_mcp"      # Tier 2 -- RETIRED, never a route
    PUBLIC_REST = "public_rest"          # Tier 3 -- services.leadconnectorhq.com + PIT
    MANAGED_BROWSER = "managed_browser"  # Tier 4 -- Skill 06 gated managed builders
    CUA = "cua"                          # Tier 5 -- Codex Computer Use, approval-gated


class OpClass(Enum):
    """Operation classes. Exact membership only -- one class never implies another."""

    READ = "read"
    LIST = "list"
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"
    EXECUTE = "execute"  # side effects: send message, book, enroll, publish


class Support(Enum):
    """Honest support state. RETIRED / UNVERIFIED are never routable."""

    VERIFIED = "verified"            # documented AND the route is recorded here
    DISCOVERABLE = "discoverable"    # dynamic catalog; op class confirmed at runtime
    UNVERIFIED = "unverified"        # named in sources but unproven; NOT routable
    RETIRED = "retired"              # removed from the platform surface
    APPROVAL_GATED = "approval_gated"  # routable only with bundled owner approval


WRITE_CLASSES: FrozenSet[OpClass] = frozenset(
    {OpClass.CREATE, OpClass.EDIT, OpClass.DELETE, OpClass.EXECUTE}
)
READ_CLASSES: FrozenSet[OpClass] = frozenset({OpClass.READ, OpClass.LIST})


@dataclass(frozen=True)
class Capability:
    """One route on one transport with the exact op classes its source documents."""

    capability_id: str
    transport: Transport
    route: str  # REST: "<VERB> <path>"; MCP: tool name; CLI/browser: handler id
    op_classes: FrozenSet[OpClass]  # EMPTY for dynamic surfaces (see resolver)
    support: Support
    provenance: str  # repo-relative source file
    resource: str = ""  # family key used for lookup, e.g. "contacts", "workflows"
    readback: bool = False  # True => read the record back after every write
    constraints: Tuple[str, ...] = ()
    resolver: str = ""  # DISCOVERABLE: how the true op class is confirmed


# --------------------------------------------------------------------------
# Transport status (current, honest -- never claim a disabled capability)
# --------------------------------------------------------------------------

TRANSPORT_STATUS: Dict[Transport, Dict[str, str]] = {
    Transport.CAF_CLI: {
        "status": "available",
        "auth": "PIT for standard ops; Firebase token (GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN) "
                "for workflow BUILD writes (Skill 44 Build API)",
        "provenance": "36-ghl-mcp-setup/SKILL.md (Tier 0); 44-convert-and-flow-operator/SKILL.md",
        "notes": "Covers contacts, opportunities, calendars, conversations, documents, "
                 "payments, forms, social, locations, workflows. NO media commands -- "
                 "media never routes here (29-ghl-convert-and-flow/references/modules.md).",
    },
    Transport.OFFICIAL_MCP: {
        "status": "documented",
        "auth": "OAuth only. A PIT bearer sent to an MCP endpoint is an unverified "
                "compatibility mode, never an equivalent auth path",
        "provenance": "36-ghl-mcp-setup/SKILL.md (Tier 1, 'Documented catalog')",
        "notes": "Evidence levels 1-2 asserted (documented endpoint + documented four-tool "
                 "catalog: list_locations, search_operations, describe_operation, "
                 "execute_operation). Levels 3-4 (account grant, observed on box) NOT held. "
                 "Underlying operation catalog is discovered at runtime via "
                 "search_operations; a count is never parity proof.",
    },
    Transport.COMMUNITY_MCP: {
        "status": "retired",
        "auth": "n/a",
        "provenance": "36-ghl-mcp-setup/SKILL.md ('Tier 2 is RETIRED'); "
                      "05-ghl-setup/SKILL.md (retirement banner)",
        "notes": "ghl-community-mcp must be OFF (absent from openclaw mcp list, no unit, "
                 "no 127.0.0.1:8765 listener). Never repair, reinstall, or route to it. "
                 "Routing goes Tier 1 -> Tier 3.",
    },
    Transport.PUBLIC_REST: {
        "status": "available",
        "auth": "Private Integration Token (PIT) bearer + required 'Version' header "
                "(per-operation version -- read the Ver column of the operation row)",
        "provenance": "05-ghl-setup/INSTRUCTIONS.md; 29-ghl-convert-and-flow/references/<module>.md",
        "notes": "Foundation/fallback tier. Read/list support on a path never implies "
                 "create/edit support on that path.",
    },
    Transport.MANAGED_BROWSER: {
        "status": "gated",
        "auth": "managed authenticated browser session (Skill 06 singleton gateway)",
        "provenance": "06-ghl-install-pages/tools/browser_manager.sh; "
                      "06-ghl-install-pages/tools/gates.json; "
                      "06-ghl-install-pages/tools/fallback-ladder.json",
        "notes": "Gated, managed builder surfaces ONLY (browser_manager.sh singleton: one "
                 "session, lock=1, TTL, guaranteed teardown). Missing gate => harness "
                 "REFUSES (MissingGateError), never freehand-navigates. Bare agent-browser "
                 "at app.gohighlevel.com for workflow build is retired. Live selectors ship "
                 "'status: runtime' until a capture hardening pass flips them to 'captured'.",
    },
    Transport.CUA: {
        "status": "approval_gated",
        "auth": "Codex Computer Use (codex/gpt-5.5), visual automation",
        "provenance": "36-ghl-mcp-setup/SKILL.md (Tier 5)",
        "notes": "Last resort, approval-gated. Never used without a bundled owner approval.",
    },
}

# --------------------------------------------------------------------------
# Operation contracts
# --------------------------------------------------------------------------

CONTRACTS: Dict[str, object] = {
    "selection_rule": (
        "Authorized MCP first -> verified documented API adapter -> managed browser "
        "execution for unsupported UI operations. Per-surface ladders (SURFACE_LADDERS) "
        "refine the order; they never invert read-vs-build routing. Never switch tools to "
        "bypass a denial."
    ),
    "read_build_routing": (
        "READ/LIST never routes to MANAGED_BROWSER. BUILD (create/edit/delete/execute) "
        "routes CAF_CLI (Firebase token for workflow writes) -> documented write route -> "
        "gated managed browser for UI-only surfaces."
    ),
    "no_implication": (
        "Read/list support never implies create/edit support. Route selection requires an "
        "exact op-class match. A dynamic surface carries no static write grant."
    ),
    "no_invention": (
        "Never invent endpoints or payloads. An established authenticated in-browser "
        "operation is NOT a public API. Capture-gated surfaces refuse to blind-POST: the "
        "save route is derived only from a recorded capture receipt."
    ),
    "readback": (
        "Read the record back after every write: capture the returned native ID, GET the "
        "record, confirm the intended change landed. Saving is never publishing."
    ),
    "uncertain_outcome": (
        "Record route/location/target/readback for every operation. Reconcile an uncertain "
        "result before retrying. Bounded backoff on provider limits; report exact HTTP "
        "status and body to the operator (verbose) and nothing to the client."
    ),
    "rate_limits": (
        "GHL REST ~100 requests/minute. Probe X-RateLimit-Daily-Remaining before bulk work. "
        "429: exponential backoff, prefer Retry-After, cap 3 retries. 5xx/timeout: one "
        "retry, then report. A missing credential blocks with the exact fix -- never a "
        "silent 401."
    ),
    "auth_separation": (
        "REST uses the location PIT (GOHIGHLEVEL_API_KEY and aliases). Official MCP uses "
        "OAuth and does not inherit the PIT. Media upload requires a Location PIT, not an "
        "Agency PIT. Never hand a PIT to an MCP endpoint and call it the documented "
        "connection."
    ),
    "denied_routes": (
        "The native GHL node in n8n is never used (limited, often broken -- HTTP Request "
        "nodes only). The community MCP is retired and is never a fallback. Bare freehand "
        "browser automation at app.gohighlevel.com is retired for workflow build."
    ),
}

REST_BASE = "https://services.leadconnectorhq.com"
REST_AUTH_HEADER = "Authorization: Bearer <PIT>"
REST_VERSION_HEADER = "Version: 2021-07-28"
REST_RATE_LIMIT_PER_MIN = 100
MAX_429_RETRIES = 3
MAX_5XX_RETRIES = 1
RATE_LIMIT_PROBE_HEADER = "X-RateLimit-Daily-Remaining"

# Per-surface attempt order (transport enum), from
# 06-ghl-install-pages/tools/fallback-ladder.json (evidence per surface there).
# Default order when a surface is not listed: CLI -> MCP -> REST -> browser.
SURFACE_LADDERS: Dict[str, Tuple[Transport, ...]] = {
    "page": (Transport.PUBLIC_REST, Transport.MANAGED_BROWSER, Transport.OFFICIAL_MCP),
    "funnel": (Transport.PUBLIC_REST, Transport.MANAGED_BROWSER, Transport.OFFICIAL_MCP),
    "form": (Transport.CAF_CLI, Transport.MANAGED_BROWSER),
    "survey": (Transport.MANAGED_BROWSER, Transport.PUBLIC_REST),
    "workflow": (Transport.CAF_CLI, Transport.MANAGED_BROWSER),
}
DEFAULT_LADDER: Tuple[Transport, ...] = (
    Transport.CAF_CLI,
    Transport.OFFICIAL_MCP,
    Transport.PUBLIC_REST,
    Transport.MANAGED_BROWSER,
)

# --------------------------------------------------------------------------
# Documented absences and restrictions (a negative claim carries provenance)
# --------------------------------------------------------------------------

RESTRICTIONS: Dict[str, Tuple[str, str]] = {
    "workflows_rest_read_only": (
        "GET /workflows/ is the ONLY workflow operation in both API generations. "
        "Workflows are read-only via public REST: there is no verified POST/PUT to create "
        "or edit a workflow. REST workflow READ support never implies workflow create/edit.",
        "29-ghl-convert-and-flow/references/campaigns.md; "
        "36-ghl-mcp-setup/GHL-LOOKUP-SOP.md ('public API is read-only for workflows')",
    ),
    "funnel_page_content_no_public_api": (
        "There is no public API endpoint that creates funnel page content. Funnel/website "
        "page buildout is browser-executed (Skill 06 gated builders). "
        "GET /funnels/funnel/list and GET /funnels/page are read-only surface.",
        "36-ghl-mcp-setup/GHL-LOOKUP-SOP.md; 29-ghl-convert-and-flow/references/api-generations.md",
    ),
    "form_field_placement_no_rest": (
        "No field-placement REST API exists for forms: custom fields/tags are pre-created "
        "through the API layer, field placement happens in the gated browser builder.",
        "06-ghl-install-pages/tools/fallback-ladder.json (surface 'form')",
    ),
    "survey_rest_capture_gated": (
        "The survey REST fallback (build_method='rest') refuses to blind-POST; it derives "
        "the save route ONLY from a recorded capture receipt.",
        "06-ghl-install-pages/tools/ghl_survey_rest.py (via fallback-ladder.json surface 'survey')",
    ),
    "products_prices_undocumented_here": (
        "No products/prices endpoint is documented in this repo's verified references. "
        "Products/prices support is INCOMPLETE until an operation is confirmed via the "
        "official MCP search_operations/describe_operation or vendor docs; no endpoint is "
        "invented here. Reported incomplete, never as done.",
        "29-ghl-convert-and-flow/references/ (no /products/ or /prices/ row); "
        "GHL-DELIVERY-SPEC.md Commerce section",
    ),
    "community_mcp_retired": (
        "The self-hosted community GHL MCP is RETIRED and never a route; boxes must verify "
        "it is off. Do not rebuild it because a tool count looks low.",
        "36-ghl-mcp-setup/SKILL.md ('Tier 2 is RETIRED')",
    ),
    "mcp_legacy_tool_names_unverified": (
        "'search' and 'fetch' MCP tool names are UNVERIFIED legacy; the documented catalog "
        "is exactly list_locations, search_operations, describe_operation, execute_operation.",
        "36-ghl-mcp-setup/SKILL.md ('Documented catalog')",
    ),
    "media_not_on_cli": (
        "The CLI has NO media commands; media NEVER routes to Tier 0. Media upload goes "
        "POST /medias/upload-file (Location PIT, not Agency PIT).",
        "29-ghl-convert-and-flow/references/modules.md (media section)",
    ),
    "n8n_native_ghl_node_banned": (
        "Never use the native GHL node in n8n (limited, often broken); HTTP Request nodes "
        "for GHL API calls only.",
        "05-ghl-setup/INSTRUCTIONS.md (Important Rules)",
    ),
    "bare_browser_workflow_build_retired": (
        "Bare agent-browser/Playwright freehand navigation at app.gohighlevel.com for "
        "workflow build is retired; only the gated managed Automations builder routes.",
        "36-ghl-mcp-setup/GHL-LOOKUP-SOP.md (Tier-4 workflow-build routing)",
    ),
}

# --------------------------------------------------------------------------
# Inventory: every route grounded in a file this repository ships
# --------------------------------------------------------------------------

_C = Capability

OPERATIONS: Tuple[Capability, ...] = (
    # --- contacts (REST, VERIFIED) ---
    _C("contacts.search", Transport.PUBLIC_REST, "GET /contacts/search",
       frozenset({OpClass.READ}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md; 29-ghl-convert-and-flow/references/contacts.md",
       resource="contacts"),
    _C("contacts.get", Transport.PUBLIC_REST, "GET /contacts/{contactId}",
       frozenset({OpClass.READ}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md; 29-ghl-convert-and-flow/references/contacts.md",
       resource="contacts"),
    _C("contacts.list", Transport.PUBLIC_REST, "GET /contacts/",
       frozenset({OpClass.LIST}), Support.VERIFIED,
       "29-ghl-convert-and-flow/references/api-generations.md (200 proven across versions)",
       resource="contacts"),
    _C("contacts.upsert", Transport.PUBLIC_REST, "POST /contacts/upsert",
       frozenset({OpClass.CREATE, OpClass.EDIT}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md; 29-ghl-convert-and-flow/references/contacts.md",
       resource="contacts", readback=True,
       constraints=("match keys (email/phone) + owner-supplied fields only; never a tags "
                    "array here; createNewIfDuplicateAllowed only when explicitly asked",
                    "read back after write")),
    _C("contacts.create", Transport.PUBLIC_REST, "POST /contacts/",
       frozenset({OpClass.CREATE}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md; 29-ghl-convert-and-flow/references/contacts.md",
       resource="contacts", readback=True,
       constraints=("explicit NEW record only, even if a match exists",)),
    _C("contacts.update", Transport.PUBLIC_REST, "PUT /contacts/{contactId}",
       frozenset({OpClass.EDIT}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md; 29-ghl-convert-and-flow/references/contacts.md",
       resource="contacts", readback=True,
       constraints=("send only supplied fields",)),
    _C("contacts.add_tags", Transport.PUBLIC_REST, "POST /contacts/{contactId}/tags",
       frozenset({OpClass.EDIT}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md; 29-ghl-convert-and-flow/references/contacts.md",
       resource="contacts", readback=True,
       constraints=("additive tag route; upsert never carries a tags array",)),

    # --- conversations (REST, VERIFIED) ---
    _C("conversations.send_message", Transport.PUBLIC_REST, "POST /conversations/messages",
       frozenset({OpClass.EXECUTE}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md; 29-ghl-convert-and-flow/references/conversations.md",
       resource="conversations", readback=True,
       constraints=("type field selects SMS vs Email on the same endpoint; "
                    "never send live client communications without binding intent",)),

    # --- calendars (REST, VERIFIED) ---
    _C("calendars.list", Transport.PUBLIC_REST, "GET /calendars/",
       frozenset({OpClass.LIST}), Support.VERIFIED,
       "29-ghl-convert-and-flow/references/calendars.md", resource="calendars"),
    _C("calendars.create", Transport.PUBLIC_REST, "POST /calendars/",
       frozenset({OpClass.CREATE}), Support.VERIFIED,
       "29-ghl-convert-and-flow/references/calendars.md", resource="calendars", readback=True),
    _C("calendars.free_slots", Transport.PUBLIC_REST, "GET /calendars/{calendarId}/free-slots",
       frozenset({OpClass.READ}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md", resource="calendars"),
    _C("calendars.events_list", Transport.PUBLIC_REST, "GET /calendars/events",
       frozenset({OpClass.LIST}), Support.VERIFIED,
       "29-ghl-convert-and-flow/references/calendars.md", resource="calendars"),
    _C("calendars.book_appointment", Transport.PUBLIC_REST, "POST /calendars/events/appointments",
       frozenset({OpClass.CREATE}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md; 29-ghl-convert-and-flow/references/calendars.md",
       resource="calendars", readback=True),

    # --- opportunities (REST, VERIFIED) ---
    _C("opportunities.search", Transport.PUBLIC_REST, "GET /opportunities/search",
       frozenset({OpClass.LIST}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md", resource="opportunities"),
    _C("opportunities.create", Transport.PUBLIC_REST, "POST /opportunities/",
       frozenset({OpClass.CREATE}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md", resource="opportunities", readback=True),
    _C("opportunities.update", Transport.PUBLIC_REST, "PUT /opportunities/{id}",
       frozenset({OpClass.EDIT}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md", resource="opportunities", readback=True),

    # --- media (REST, VERIFIED) ---
    _C("medias.list", Transport.PUBLIC_REST, "GET /medias/",
       frozenset({OpClass.LIST}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md; 29-ghl-convert-and-flow/references/medias.md",
       resource="media"),
    _C("medias.upload", Transport.PUBLIC_REST, "POST /medias/upload-file",
       frozenset({OpClass.CREATE}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md; 29-ghl-convert-and-flow/references/modules.md",
       resource="media", readback=True,
       constraints=("multipart/form-data via curl -F (never hand-set the boundary); "
                    "Location PIT required, not Agency PIT; 25 MB files / 500 MB video",
                    "never routes to CAF_CLI (no media commands)")),

    # --- funnels (REST read-only surface, VERIFIED) ---
    _C("funnels.list", Transport.PUBLIC_REST, "GET /funnels/funnel/list",
       frozenset({OpClass.LIST}), Support.VERIFIED,
       "29-ghl-convert-and-flow/references/api-generations.md", resource="funnels"),
    _C("funnels.pages_list", Transport.PUBLIC_REST, "GET /funnels/page",
       frozenset({OpClass.LIST}), Support.VERIFIED,
       "29-ghl-convert-and-flow/references/api-generations.md", resource="funnels"),
    _C("funnels.pages_count", Transport.PUBLIC_REST, "GET /funnels/page/count",
       frozenset({OpClass.READ}), Support.VERIFIED,
       "29-ghl-convert-and-flow/references/api-generations.md", resource="funnels"),

    # --- workflows (REST read-only surface, VERIFIED) ---
    _C("workflows.get", Transport.PUBLIC_REST, "GET /workflows/",
       frozenset({OpClass.LIST}), Support.VERIFIED,
       "29-ghl-convert-and-flow/references/campaigns.md", resource="workflows",
       constraints=("workflows are READ-ONLY via public REST; this route's read/list "
                    "support never implies workflow create/edit",)),
    _C("workflows.enroll_contact", Transport.PUBLIC_REST,
       "POST /contacts/{contactId}/workflow/{workflowId}",
       frozenset({OpClass.EXECUTE}), Support.VERIFIED,
       "29-ghl-convert-and-flow/references/campaigns.md", resource="workflows",
       readback=True,
       constraints=("contact enrollment only -- not workflow create/edit",)),
    _C("workflows.unenroll_contact", Transport.PUBLIC_REST,
       "DELETE /contacts/{contactId}/workflow/{workflowId}",
       frozenset({OpClass.EXECUTE}), Support.VERIFIED,
       "29-ghl-convert-and-flow/references/campaigns.md", resource="workflows",
       readback=True,
       constraints=("contact unenrollment only -- not workflow delete",)),

    # --- locations (REST, VERIFIED) ---
    _C("locations.search", Transport.PUBLIC_REST, "GET /locations/search",
       frozenset({OpClass.LIST}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md; 29-ghl-convert-and-flow/references/agency-api.md",
       resource="locations"),
    _C("locations.get", Transport.PUBLIC_REST, "GET /locations/{locationId}",
       frozenset({OpClass.READ}), Support.VERIFIED,
       "05-ghl-setup/INSTRUCTIONS.md; 29-ghl-convert-and-flow/references/agency-api.md",
       resource="locations"),

    # --- dynamic surfaces: no static write grant (op class resolved at runtime) ---
    _C("mcp.list_locations", Transport.OFFICIAL_MCP, "list_locations",
       frozenset(), Support.DISCOVERABLE,
       "36-ghl-mcp-setup/SKILL.md (documented catalog, evidence level 2)",
       resource="locations",
       resolver="tool is read-class by catalog name; confirm via describe_operation"),
    _C("mcp.search_operations", Transport.OFFICIAL_MCP, "search_operations",
       frozenset(), Support.DISCOVERABLE,
       "36-ghl-mcp-setup/SKILL.md (documented catalog, evidence level 2)",
       resource="discovery",
       resolver="discovery tool; the operation catalog is runtime-discovered"),
    _C("mcp.describe_operation", Transport.OFFICIAL_MCP, "describe_operation",
       frozenset(), Support.DISCOVERABLE,
       "36-ghl-mcp-setup/SKILL.md (documented catalog, evidence level 2)",
       resource="discovery",
       resolver="schema-capture tool; use it to confirm an operation's true op class"),
    _C("mcp.execute_operation", Transport.OFFICIAL_MCP, "execute_operation",
       frozenset(), Support.DISCOVERABLE,
       "36-ghl-mcp-setup/SKILL.md (documented catalog, evidence level 2)",
       resource="dynamic",
       resolver="op class MUST be confirmed via search_operations + describe_operation "
                "before use; read/list confirmation never implies create/edit"),
    _C("caf.std_ops", Transport.CAF_CLI, "caf <module> <command>",
       frozenset(), Support.DISCOVERABLE,
       "36-ghl-mcp-setup/SKILL.md (Tier 0); 44-convert-and-flow-operator/SKILL.md",
       resource="dynamic",
       resolver="covered modules: contacts, opportunities, calendars, conversations, "
                "documents, payments, forms, social, locations, workflows; confirm the "
                "command's op class via CLI help before use. Media is NOT covered. "
                "Workflow WRITES need the Firebase token Build API"),
    _C("caf.workflow_build", Transport.CAF_CLI, "caf Build API (Firebase token)",
       frozenset(), Support.DISCOVERABLE,
       "36-ghl-mcp-setup/GHL-LOOKUP-SOP.md (BUILD path Tier 0)",
       resource="workflow",
       resolver="workflow create/edit via Skill 44 internal Build API; requires "
                "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN"),

    # --- managed browser: UI-only surfaces, gated (Skill 06) ---
    _C("browser.page_content", Transport.MANAGED_BROWSER,
       "06-ghl-install-pages gated page/funnel builders",
       frozenset({OpClass.CREATE, OpClass.EDIT}), Support.VERIFIED,
       "06-ghl-install-pages/tools/fallback-ladder.json (surface 'page'); "
       "06-ghl-install-pages/tools/ghl_builder.py",
       resource="page",
       constraints=("singleton browser_manager gateway (lock=1, TTL, teardown); "
                    "missing gate => MissingGateError refusal, never freehand; "
                    "this in-browser operation is NOT a public API",)),
    _C("browser.form_build", Transport.MANAGED_BROWSER,
       "06-ghl-install-pages/tools/ghl_form_builder.py",
       frozenset({OpClass.CREATE, OpClass.EDIT}), Support.VERIFIED,
       "06-ghl-install-pages/tools/fallback-ladder.json (surface 'form')",
       resource="form",
       constraints=("custom fields/tags pre-created through the API layer first; "
                    "field placement is browser-only (no REST route exists)",)),
    _C("browser.survey_build", Transport.MANAGED_BROWSER,
       "06-ghl-install-pages/tools/ghl_survey_builder.py",
       frozenset({OpClass.CREATE, OpClass.EDIT}), Support.VERIFIED,
       "06-ghl-install-pages/tools/fallback-ladder.json (surface 'survey')",
       resource="survey",
       constraints=("primary lane is the browser drag rail; REST fallback is "
                    "capture-gated and refuses blind-POST",)),
    _C("browser.workflow_build", Transport.MANAGED_BROWSER,
       "06-ghl-install-pages/tools/ghl_workflow_builder.py",
       frozenset({OpClass.CREATE, OpClass.EDIT}), Support.VERIFIED,
       "36-ghl-mcp-setup/GHL-LOOKUP-SOP.md (Tier-4 workflow-build routing); "
       "06-ghl-install-pages/tools/fallback-ladder.json (surface 'workflow')",
       resource="workflow",
       constraints=("gated managed Automations builder only (automations_builder_gates "
                    "registry in tools/gates.json); bare freehand browser is retired; "
                    "token circularity: Tier 4 needs the Firebase token session",)),

    # --- Codex Computer Use: last resort, approval-gated ---
    _C("cua.visual", Transport.CUA, "codex computer use",
       frozenset(), Support.APPROVAL_GATED,
       "36-ghl-mcp-setup/SKILL.md (Tier 5)",
       resource="dynamic",
       resolver="routable only with a bundled owner approval naming test location, "
                "temporary objects, and operations"),
)

# --------------------------------------------------------------------------
# Selection and validation
# --------------------------------------------------------------------------


class UnsupportedOperation(Exception):
    """Raised when no verified route exists for the exact operation requested."""


def supports(cap: Capability, op_class: OpClass) -> bool:
    """Exact membership only. Read/list support never implies create/edit support."""
    return op_class in cap.op_classes


def routable(cap: Capability, *, dynamic_confirmed: bool) -> bool:
    if cap.support in (Support.RETIRED, Support.UNVERIFIED):
        return False
    if cap.support == Support.APPROVAL_GATED:
        return False  # requires a bundled approval, never an automatic route
    if cap.support == Support.DISCOVERABLE:
        return dynamic_confirmed  # caller confirmed the true op class at runtime
    return True


def select_route(
    op_class: OpClass,
    *,
    resource: Optional[str] = None,
    surface: Optional[str] = None,
    dynamic_confirmed: bool = False,
) -> List[Capability]:
    """Candidate routes for the EXACT op class, in attempt order.

    Returns [] when nothing verified routes -- callers must report that as
    incomplete, never as done. READ/LIST never routes to MANAGED_BROWSER.
    """
    ladder = SURFACE_LADDERS.get(surface or "", DEFAULT_LADDER)
    out = [
        cap for cap in OPERATIONS
        if supports(cap, op_class)
        and (not resource or cap.resource == resource)
        and routable(cap, dynamic_confirmed=dynamic_confirmed)
        and not (op_class in READ_CLASSES and cap.transport is Transport.MANAGED_BROWSER)
    ]
    order = {t: i for i, t in enumerate(ladder)}
    out.sort(key=lambda c: (order.get(c.transport, len(ladder)), c.capability_id))
    return out


def require_route(op_class: OpClass, **kw) -> Capability:
    routes = select_route(op_class, **kw)
    if not routes:
        raise UnsupportedOperation(
            f"no verified route for {op_class.value} "
            f"(resource={kw.get('resource')!r}, surface={kw.get('surface')!r}); "
            f"report incomplete, never as done"
        )
    return routes[0]


_REST_VERB_CLASSES = {
    "GET": frozenset({OpClass.READ, OpClass.LIST}),
    "POST": frozenset({OpClass.CREATE, OpClass.EDIT, OpClass.EXECUTE}),
    "PUT": frozenset({OpClass.CREATE, OpClass.EDIT}),
    "PATCH": frozenset({OpClass.EDIT}),
    "DELETE": frozenset({OpClass.DELETE, OpClass.EXECUTE}),
}


def validate_inventory() -> List[str]:
    """Return invariant violations. Empty list == inventory is honest."""
    problems: List[str] = []
    seen_ids = set()
    for cap in OPERATIONS:
        if cap.capability_id in seen_ids:
            problems.append(f"duplicate capability id {cap.capability_id}")
        seen_ids.add(cap.capability_id)
        if not cap.provenance:
            problems.append(f"{cap.capability_id}: missing provenance")
        if cap.transport is Transport.COMMUNITY_MCP:
            problems.append(f"{cap.capability_id}: retired community MCP must not be an entry")
        if cap.support in (Support.RETIRED, Support.UNVERIFIED):
            problems.append(f"{cap.capability_id}: retired/unverified entries are not routable")
        if cap.support is Support.DISCOVERABLE and (cap.op_classes or not cap.resolver):
            problems.append(
                f"{cap.capability_id}: dynamic surface must carry NO static op classes "
                "and must name a resolver"
            )
        if cap.transport is Transport.PUBLIC_REST:
            verb, _, path = cap.route.partition(" ")
            allowed = _REST_VERB_CLASSES.get(verb)
            if allowed is None or not path.startswith("/"):
                problems.append(f"{cap.capability_id}: malformed REST route {cap.route!r}")
            elif not cap.op_classes <= allowed:
                problems.append(
                    f"{cap.capability_id}: verb {verb} cannot carry "
                    f"{sorted(c.value for c in cap.op_classes - allowed)}"
                )
        if cap.op_classes & WRITE_CLASSES and cap.transport is Transport.PUBLIC_REST and not cap.readback:
            problems.append(f"{cap.capability_id}: REST write without readback contract")
    return problems


def capability_report() -> Dict[str, object]:
    """Honest summary: what routes, what is incomplete, what is retired."""
    by_support: Dict[str, List[str]] = {}
    for cap in OPERATIONS:
        by_support.setdefault(cap.support.value, []).append(cap.capability_id)
    incomplete = [
        f"{rid}: {stmt.splitlines()[0]}"
        for rid, (stmt, _prov) in RESTRICTIONS.items()
        if "INCOMPLETE" in stmt or "no public API" in stmt or "No field-placement" in stmt
    ]
    return {
        "counts": {k: len(v) for k, v in sorted(by_support.items())},
        "by_support": {k: sorted(v) for k, v in sorted(by_support.items())},
        "incomplete": incomplete,
        "retired": [t.value for t, s in TRANSPORT_STATUS.items() if s["status"] == "retired"],
    }


# --------------------------------------------------------------------------
# Runnable check (assert-based self-check)
# --------------------------------------------------------------------------


def self_check() -> None:
    # 1. Inventory is internally honest.
    problems = validate_inventory()
    assert not problems, f"inventory violations: {problems}"

    # 2. Read/list support never implies create/edit support (canonical case:
    #    workflows are read-only via REST).
    wf_read = select_route(OpClass.LIST, resource="workflows", dynamic_confirmed=False)
    assert any(c.route == "GET /workflows/" for c in wf_read), wf_read
    for write in (OpClass.CREATE, OpClass.EDIT, OpClass.DELETE):
        assert select_route(write, resource="workflows", dynamic_confirmed=False) == [], (
            f"workflows must not expose {write.value} on any static route"
        )

    # 3. Funnels: read surface exists; funnel page CONTENT write is browser-only
    #    (no invented public API).
    assert select_route(OpClass.LIST, resource="funnels"), "funnels read surface missing"
    assert select_route(OpClass.CREATE, resource="funnels", dynamic_confirmed=False) == [], (
        "no verified REST create for funnels may exist"
    )
    page_build = select_route(OpClass.CREATE, resource="page", surface="page")
    assert any(c.transport is Transport.MANAGED_BROWSER for c in page_build), page_build

    # 4. Reads never route through the browser.
    for op in (OpClass.READ, OpClass.LIST):
        for cap in select_route(op, dynamic_confirmed=True):
            assert cap.transport is not Transport.MANAGED_BROWSER, cap.capability_id

    # 5. Retired community MCP is absent from every ladder and from the inventory.
    assert all(
        Transport.COMMUNITY_MCP not in ladder
        for ladder in list(SURFACE_LADDERS.values()) + [DEFAULT_LADDER]
    )
    assert TRANSPORT_STATUS[Transport.COMMUNITY_MCP]["status"] == "retired"

    # 6. Write contracts: readback is required on REST writes.
    upsert = next(c for c in OPERATIONS if c.capability_id == "contacts.upsert")
    assert upsert.readback and upsert.op_classes == frozenset({OpClass.CREATE, OpClass.EDIT})

    # 7. Products/prices: reported INCOMPLETE, never as done, never invented.
    assert select_route(OpClass.CREATE, resource="products", dynamic_confirmed=False) == []
    assert any("products_prices" in rid for rid in RESTRICTIONS)

    # 8. Dynamic surfaces carry no static write grant.
    for cap in OPERATIONS:
        if cap.support is Support.DISCOVERABLE:
            assert cap.op_classes == frozenset() and cap.resolver, cap.capability_id
    assert select_route(OpClass.CREATE, dynamic_confirmed=True) != [], (
        "confirmed dynamic surface must be able to route"
    )

    # 9. Bounded backoff.
    assert MAX_429_RETRIES == 3 and MAX_5XX_RETRIES == 1

    # 10. Missing route raises and says "incomplete", never "done".
    try:
        require_route(OpClass.CREATE, resource="products")
    except UnsupportedOperation as exc:
        assert "incomplete" in str(exc)
    else:
        raise AssertionError("require_route must refuse unverified products create")


if __name__ == "__main__":
    self_check()
    _report = capability_report()
    print("capability_inventory self-check: PASS")
    print(f"  routes catalogued: {len(OPERATIONS)}")
    print(f"  support counts: {_report['counts']}")
    print(f"  retired transports: {_report['retired']}")
    print(f"  incomplete (reported, never as done): {len(_report['incomplete'])} restrictions")
