#!/usr/bin/env python3
"""GHL-160 machine check: V4 staging refusal + consumer call paths + route dispositions.

Read-only. No network, no credential read, no live call. Exits 0 only when every
assertion in evidence/W18/v4-and-client-path-verification.md still holds.

Every declared disposition (a route with no registry row, or a retired row a
caller still uses) must still be present at the cited source line. If the source
moves or a route is silently re-pointed, this check fails rather than passing on
stale evidence.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENGINE = REPO / "44-convert-and-flow-operator" / "tools" / "engine"
PKG = ENGINE / "cli_anything" / "gohighlevel"
sys.path.insert(0, str(ENGINE))

from cli_anything.gohighlevel.public.capability import (  # noqa: E402
    ActivationBlock,
    Capability,
    CapabilityGate,
    load_capability_record,
)
from cli_anything.gohighlevel.public.operations import (  # noqa: E402
    OPERATIONS,
    STAGING_DOCS,
    SUPPORTED_VERSIONS,
)

FAILURES: list[str] = []
CHECKS = 0


def check(condition: bool, message: str) -> None:
    global CHECKS
    CHECKS += 1
    if not condition:
        FAILURES.append(message)


def source(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def line_at(rel: str, number: int) -> str:
    lines = source(rel).splitlines()
    if number < 1 or number > len(lines):
        return ""
    return lines[number - 1]


def expect_line(rel: str, number: int, needle: str) -> None:
    check(needle in line_at(rel, number), f"{rel}:{number} no longer contains {needle!r}")


# ---------------------------------------------------------------------------
# 1. Every public V4 row is staging level, v4, B-V4-S, and v4 is not a supported
#    production version.
# ---------------------------------------------------------------------------
V4_PUBLIC = (
    "workflows.definition.read",
    "workflows.definition.create",
    "workflows.definition.update",
    "workflows.status.publish",
    "workflows.definition.delete",
)
V4_WRITES = frozenset(
    {
        "workflows.definition.create",
        "workflows.definition.update",
        "workflows.status.publish",
        "workflows.definition.delete",
    }
)

check("v4" not in SUPPORTED_VERSIONS, "v4 must not be a supported production Version literal")
check(
    "staging-only" in line_at("44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py", 53),
    "operations.py:53 must keep the staging-only comment for v4",
)
check(STAGING_DOCS.startswith("https://staging."), "STAGING_DOCS must be a staging marketplace URL")

for operation_id in V4_PUBLIC:
    row = OPERATIONS.get(operation_id)
    check(row is not None, f"{operation_id}: registry row missing")
    if row is None:
        continue
    check(row.version == "v4", f"{operation_id}: Version must stay v4")
    check(row.documented_level == "S", f"{operation_id}: documented level must stay S (staging)")
    check(row.blocker == "B-V4-S", f"{operation_id}: blocker must stay B-V4-S")
    check(row.route_class == "public_direct", f"{operation_id}: route class must stay public_direct")
    check(
        bool(row.doc_url) and row.doc_url.startswith(STAGING_DOCS),
        f"{operation_id}: doc_url must stay on the staging marketplace",
    )
    check(row.write == (operation_id in V4_WRITES), f"{operation_id}: write flag drifted")
    if operation_id in V4_WRITES:
        check(row.approval_required, f"{operation_id}: V4 write must require approval")

check(
    OPERATIONS["workflows.private.get"].route_class == "skill44_private",
    "workflows.private.get must stay on the Skill 44 private rail",
)

# The V4 operation map must name exactly these rows and no invented route.
workflow_v4_source = source(
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/workflow_v4.py"
)
for fragment in (
    'READ_OPERATION = "workflows.definition.read"',
    'CREATE_OPERATION = "workflows.definition.create"',
    'UPDATE_OPERATION = "workflows.definition.update"',
    'STATUS_OPERATION = "workflows.status.publish"',
    'DELETE_OPERATION = "workflows.definition.delete"',
    '"validation.read": NONE',
    '"restore": NONE',
):
    check(fragment in workflow_v4_source, f"workflow_v4.py lost mapping fragment {fragment!r}")

# ---------------------------------------------------------------------------
# 2. The capability gate is default-deny and cannot enable a V4 write without
#    canary evidence.
# ---------------------------------------------------------------------------
gate = CapabilityGate()
for operation_id in V4_PUBLIC:
    capability = gate.get(operation_id)
    check(not capability.enabled, f"{operation_id}: default gate must not enable anything")
    check(
        capability.activation_blocked is not None,
        f"{operation_id}: a disabled capability must carry an activation block",
    )

blocked = ActivationBlock(reason="r", owner="o", unblock="u")
try:
    Capability(operation_id="workflows.status.publish", enabled=True, activation_blocked=blocked)
except Exception:  # noqa: BLE001 - the invariant is "must raise"
    check(True, "unreachable")
else:
    check(False, "enabled=True with an activation block must be impossible")

try:
    Capability(
        operation_id="workflows.definition.read",
        contract_verified=True,
        adapter_built=True,
        offline_tests_passed=True,
        enabled=True,
    )
except Exception:  # noqa: BLE001
    check(True, "unreachable")
else:
    check(False, "enabled without read_verified must be impossible")

read_only = Capability(
    operation_id="workflows.definition.update",
    contract_verified=True,
    adapter_built=True,
    offline_tests_passed=True,
    read_verified=True,
    canary_verified=False,
)
check(read_only.evidence_ok(), "read_verified + offline evidence must satisfy evidence_ok")
check(not read_only.write_ready(), "a write must not be ready without canary_verified")
check(
    read_only.evidence_ok() and not read_only.write_ready(),
    "V4 write readiness must remain stricter than read enablement",
)

# ---------------------------------------------------------------------------
# 3. The checked-in record admits nothing and carries no V4 row.
# ---------------------------------------------------------------------------
RECORD_TENANT = "Mct54Bwi1KlNouGXQcDX"
record_text = source(
    "44-convert-and-flow-operator/tools/engine/state/ghl-public-capabilities.json"
)
record_document = json.loads(record_text)
record_rows = record_document.get("capabilities") or {}

# The record is bound to one location: any other tenant must fail closed to
# default-deny rather than reuse this tenant's live 200s.
check(
    len(load_capability_record(tenant="XCgFTEA1oDvsPnTqqgoB")) == 0,
    "checked-in record must not load for a foreign tenant (tenant mismatch)",
)
record_gate = load_capability_record(tenant=RECORD_TENANT)
check(
    len(record_gate) == 6
    and len(record_rows) == 6
    and all(
        row.get("read_verified") is True
        and row.get("enabled") is True
        and row.get("canary_verified") is False
        for row in record_rows.values()
    ),
    "checked-in record must carry its six live read-verified rows for its recorded tenant",
)
check(
    record_document.get("tenant") == RECORD_TENANT,
    "record tenant changed without evidence refresh",
)
# A read probe is not a write canary: the record may enable only non-write
# registry rows, so no admitted row can authorize a dispatch as a write.
record_write_rows = [
    operation_id
    for operation_id in record_rows
    if OPERATIONS.get(operation_id) is None or OPERATIONS[operation_id].write
]
check(
    not record_write_rows,
    f"record enables rows outside the read-only registry: {record_write_rows}",
)
for operation_id in V4_PUBLIC:
    check(
        not record_gate.get(operation_id).enabled,
        f"{operation_id}: no V4 capability may be enabled by the checked-in record",
    )
for operation_id in V4_PUBLIC:
    check(
        f'"{operation_id}"' not in record_text,
        f"{operation_id}: V4 row appeared in the checked-in record; refresh this evidence",
    )

# ---------------------------------------------------------------------------
# 4. The refusal path exists in source, before transport.
# ---------------------------------------------------------------------------
adapter_source = source(
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/adapter.py"
)
check("gate = self._gate_for(tenant.location_id)" in adapter_source, "adapter gate must be tenant-bound")
check('"rule": "capability_disabled"' in adapter_source, "adapter must refuse with capability_disabled")
check('"refused_before_transport": True' in adapter_source, "adapter refusal must precede transport")
check(
    "capability.write_ready() if write else capability.enabled" in adapter_source,
    "adapter must require write_ready for a V4 write",
)
check("capability_tenant_mismatch" in adapter_source, "adapter must refuse a foreign-tenant capability")

capability_source = source(
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/capability.py"
)
check("and self.read_verified" in capability_source, "evidence_ok must require read_verified")
check(
    "return self.evidence_ok() and self.canary_verified" in capability_source,
    "write_ready must require canary_verified",
)
# Declared defect: a second, unreachable return in evidence_ok references an
# undefined name. It is dead code, not a live escape.
check(
    capability_source.count("        return (") >= 2 and "and tenant_read" in capability_source,
    "the declared unreachable evidence_ok branch changed; re-review it",
)

for number, operation in (
    (387, "create"),
    (518, "update"),
    (792, "status change"),
    (923, "delete"),
):
    expect_line(
        "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/workflow_v4.py",
        number,
        "if not self._enabled(operation_id):",
    )

# Declared defect F1: the write gate probes capability without a tenant, so a
# fresh adapter answers "disabled" even when the record admits the operation.
expect_line(
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/workflow_v4.py",
    289,
    "return bool(self._public.capability(operation_id).enabled)",
)
expect_line(
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/utils/workflow_builder.py",
    121,
    "capability = v4.capability(key)",
)
expect_line(
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/utils/workflow_builder.py",
    160,
    "public = PublicGhlAdapter(",
)
expect_line(
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py",
    806,
    "from cli_anything.gohighlevel.utils.workflow_builder import load_public_v4",
)

# ---------------------------------------------------------------------------
# 5. Consumer call paths, as recorded in the evidence document.
# ---------------------------------------------------------------------------
# Skill 44 orchestration: the builder and CLI wire the V4 adapter, but the
# route decision probes an unbound capability (F1).
expect_line(
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py",
    880,
    "v4, _route_reason = _get_public_v4(ctx)",
)
expect_line(
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/utils/workflow_builder.py",
    711,
    "result = self.public_v4.create_workflow(",
)
# Skill 35 social planner: Tier-0 `caf` -> legacy client, no public adapter.
expect_line(
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py",
    1945,
    'api.get(f"/social-media-posting/{_loc(ctx)}/accounts")',
)
expect_line(
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py",
    1970,
    'api.post(f"/social-media-posting/{_loc(ctx)}/posts/list", data=params)',
)
expect_line(
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py",
    2073,
    'api.post(f"/social-media-posting/{_loc(ctx)}/posts", data=body)',
)
expect_line(
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py",
    12,
    "from cli_anything.gohighlevel.utils import ghl_client as api",
)
# Skill 06 products/media: raw REST rails, its own Version constant, no adapter.
media_source = source("06-ghl-install-pages/tools/ghl_media.py")
check(
    'GHL_MEDIA_UPLOAD_PATH = "/medias/upload-file"'
    in line_at("06-ghl-install-pages/tools/ghl_media.py", 136)
    and 'GHL_SERVICES_ORIGIN.rstrip("/") + GHL_MEDIA_UPLOAD_PATH' in media_source,
    "ghl_media.py:136 must keep the documented upload path and send it to the services origin",
)
check(
    'GHL_MEDIA_VERSION = "2021-07-28"'
    in line_at("06-ghl-install-pages/tools/ghl_media.py", 149)
    and 'req.add_header("Version", GHL_MEDIA_VERSION)' in media_source,
    "ghl_media.py:149 must keep Skill 06's own legacy Version constant and send it",
)
expect_line("06-ghl-install-pages/tools/ghl_object_router.py", 369, 'm["media"] = ObjectRoute(')
check(
    'm["product"] = ObjectRoute('
    in line_at("06-ghl-install-pages/tools/ghl_object_router.py", 389)
    and "raw HTTPS services.* /products"
    in source("06-ghl-install-pages/tools/ghl_object_router.py"),
    "ghl_object_router.py:389 must keep the product row on the raw services rail",
)
# Signature funnel consumers: injected protocol only, no production binding.
expect_line(
    "44-convert-and-flow-operator/tools/siglaunch/provisioning/provisioning.py",
    29,
    "class Catalog(Protocol):",
)
check(
    "FakeCatalog" in source("44-convert-and-flow-operator/tools/siglaunch/provisioning/test_provisioning.py"),
    "signature provisioning tests must keep the fake catalog",
)
# Extra recorded consumer: Skill 58 reads V4 directly through PublicGhlAdapter.
expect_line(
    "58-podcast-production-engine/scripts/activate-podcast-fb-workflows.py",
    202,
    'adapter.call(operation_id="workflows.list", tenant=tenant)',
)
expect_line(
    "58-podcast-production-engine/scripts/activate-podcast-fb-workflows.py",
    220,
    'adapter.call(operation_id="workflows.definition.read", tenant=tenant,',
)

# No named consumer outside the engine may construct the public adapter yet.
for rel_root in (
    "35-social-media-planner",
    "06-ghl-install-pages",
    "49-signature-funnel",
    "44-convert-and-flow-operator/tools/siglaunch",
):
    hits = []
    for path in (REPO / rel_root).rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "PublicGhlAdapter" in text:
            hits.append(str(path.relative_to(REPO)))
    check(not hits, f"{rel_root}: unexpected public-adapter wiring appeared: {hits}")

# ---------------------------------------------------------------------------
# 6. Routes with no registry row, or a retired row a caller still uses.
# ---------------------------------------------------------------------------
CLI = "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py"
cli_text = source(CLI)

NO_ROW_DISPOSITIONS = {
    # path (normalised): (line, disposition)
    "/proposals/document": (1511, "named gap: no audited public operation row"),
    "/proposals/templates": (1530, "named gap: no audited public operation row"),
    "/proposals/document/send": (1553, "named gap: no audited public operation row"),
    "/proposals/templates/send": (1578, "named gap: no audited public operation row"),
    "/campaigns": (1712, "named gap: no audited public operation row"),
    "/calendars/events/appointments": (689, "named gap: no GET row; appointments.create is POST-only"),
    "/locations/search": (2113, "named gap: no audited public operation row"),
    "/users": (2308, "named gap: no audited public operation row"),
}
RETIRED_DISPOSITIONS = {
    ("GET", "/contacts"): (185, "contacts.list is retired; replacement is contacts.search"),
}

for path, (number, _disposition) in NO_ROW_DISPOSITIONS.items():
    expect_line(CLI, number, f'"{path}' if not path.endswith("/") else f'"{path}/')
for (method, path), (number, _disposition) in RETIRED_DISPOSITIONS.items():
    expect_line(CLI, number, 'api.get("/contacts/"')
    row = OPERATIONS.get("contacts.list")
    check(row is not None and row.route_class == "retired", "contacts.list must stay retired")
    check("contacts.search" in OPERATIONS, "contacts.search replacement must stay registered")

call_pattern = re.compile(r"""api\.(get|post|put|delete|patch)\(\s*f?["']([^"']+)["']""")


def normalise(path: str) -> str:
    path = re.sub(r"%s", "{}", path)
    path = re.sub(r"\{[^{}]*\}", "{}", path)
    return path.rstrip("/") or "/"


registry_by_path: dict[str, list[tuple[str, str]]] = {}
for operation_id, row in OPERATIONS.items():
    template = row.path_template
    if isinstance(template, str) and template.startswith("/"):
        registry_by_path.setdefault(normalise(template), []).append(
            (operation_id, row.route_class)
        )

unmatched: list[tuple[int, str, str]] = []
for number, text in enumerate(cli_text.splitlines(), 1):
    for match in call_pattern.finditer(text):
        method = match.group(1).upper()
        path = normalise(match.group(2))
        rows = registry_by_path.get(path, [])
        method_rows = [row for row in rows if OPERATIONS[row[0]].method.split("/")[0] == method]
        if method_rows:
            for operation_id, route_class in method_rows:
                if route_class == "retired" and (method, path) not in RETIRED_DISPOSITIONS:
                    FAILURES.append(
                        f"{CLI}:{number} still calls retired row {operation_id} ({method} {path})"
                    )
            continue
        if path in NO_ROW_DISPOSITIONS:
            continue
        unmatched.append((number, method, path))

check(not unmatched, f"undeclared route(s) with no registry row: {unmatched}")

# Skill 06 internal canvas routes are named authoring gaps, never public rows.
SKILL06_INTERNAL = (
    ("06-ghl-install-pages/tools/ghl_rest_canvas.py", 126, '/funnels/page/{page_id}'),
    ("06-ghl-install-pages/tools/ghl_rest_canvas.py", 141, '/funnels/builder/autosave/{page_id}'),
    ("06-ghl-install-pages/tools/ghl_rest_canvas.py", 154, '/workflow/{location_id}/{workflow_id}'),
    ("06-ghl-install-pages/tools/ghl_rest_canvas.py", 166, '/workflow/{location_id}/trigger/{trigger_id}'),
    ("06-ghl-install-pages/tools/ghl_rest_canvas.py", 193, '/funnels/funnel/create'),
    ("06-ghl-install-pages/tools/ghl_rest_canvas.py", 206, '/funnels/funnel/create-step'),
    ("06-ghl-install-pages/tools/ghl_rest_canvas.py", 218, '/funnels/funnel/fetch/{funnel_id}'),
    ("06-ghl-install-pages/tools/ghl_rest_canvas.py", 228, '/funnels/page/list?funnelId={funnel_id}&locationId={location_id}'),
    ("06-ghl-install-pages/tools/ghl_rest_canvas.py", 240, '/funnels/funnel/delete'),
    ("06-ghl-install-pages/tools/ghl_funnels_read.py", 138, 'FUNNEL_LIST_PATH = "/funnels/funnel/list"'),
    ("06-ghl-install-pages/tools/ghl_funnels_read.py", 139, 'PAGE_LIST_PATH = "/funnels/page"'),
)
for rel, number, needle in SKILL06_INTERNAL:
    expect_line(rel, number, needle)

# The private trigger rewire is the second call of a two-call freeze row; the
# registry records only the first call and says so.
operations_rel = (
    "44-convert-and-flow-operator/tools/engine/"
    "cli_anything/gohighlevel/public/operations.py"
)
check(
    "``workflows.private.trigger.link`` is a two-call row in the freeze"
    in line_at(operations_rel, 746)
    and OPERATIONS["workflows.private.trigger.link"].method == "POST"
    and OPERATIONS["workflows.private.trigger.link"].path_template
    == "/workflow/{loc}/trigger",
    "operations.py:746 must keep the two-call note and trigger.link's POST first call",
)
check(
    '_R("workflows.private.publish", "PUT", "/workflow/{loc}/{wf}",'
    in line_at(operations_rel, 800)
    and OPERATIONS["workflows.private.publish"].method == "PUT"
    and OPERATIONS["workflows.private.publish"].path_template == "/workflow/{loc}/{wf}",
    "operations.py:800 must keep the Skill 44 private publish PUT row",
)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
if FAILURES:
    print(f"RESULT: FAIL - {len(FAILURES)} of {CHECKS} checks failed")
    for failure in FAILURES:
        print(f"  - {failure}")
    raise SystemExit(1)

print(f"RESULT: PASS - {CHECKS} checks")
print("V4 rows: 5 public rows at level S, Version v4, blocker B-V4-S, staging doc URLs")
print("Gate: default-deny; a V4 write additionally requires canary_verified")
print("Consumers: 44 wired (route probe unbound, declared F1); 58 direct read wired;")
print("           35, 06, signature = legacy/raw rails or protocol-only (declared gaps)")
print("Routes: 8 declared no-row callers; 1 retired-row caller; Skill 06 internal authoring gaps")
raise SystemExit(0)
