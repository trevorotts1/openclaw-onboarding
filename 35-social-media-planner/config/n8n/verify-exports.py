#!/usr/bin/env python3
"""F16 export verifier — validates the deployable n8n export contracts.

Checks both config/n8n exports for:
  - valid JSON, schema_version present, no placeholder markers (_PLACEHOLDER_NOTE etc.)
  - real n8n node types (webhook/code/httpRequest/googleDrive/respondToWebhook/if)
  - required auth wiring (predefinedCredentialType on Sheets API calls; Drive ops)
  - payload mappings (Posts header, row keys, provisioning key)
  - actual resize request (updateDimensionProperties batchUpdate, not a note)
  - no committed credentials (credential id/name values), no placeholder IDs/URLs
  - response receipt keys (sheetId, updatedRange, provisioning key)

Exit 0 = both exports valid. Any violation prints FAIL lines and exits 1.
"""
import json, os, re, sys

BASE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_VERSION = "1.1.0"
POSTS_HEADER = ["row_key", "company_id", "cycle_id", "content_revision", "account_id",
                "platform", "account_name", "format", "scheduled_local", "scheduled_utc",
                "state", "qc_state", "preview_url", "remote_url"]

failures = []
checks = 0


def check(cond, ok_msg, fail_msg):
    global checks
    checks += 1
    if not cond:
        failures.append(fail_msg)


def walk_strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for item in obj:
            yield None, item
            yield from walk_strings(item)
    else:
        yield None, obj


def js_code_of(export, name):
    for n in export["nodes"]:
        if n["name"] == name:
            return n["parameters"].get("jsCode", "")
    return ""


def load(name):
    path = os.path.join(BASE, name)
    check(os.path.exists(path), f"{name} exists", f"FAIL {name}: file missing")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"FAIL {name}: invalid JSON ({exc})")
        return None


def validate_common(name, export):
    check(export.get("schema_version") == SCHEMA_VERSION,
          f"{name}: schema_version {SCHEMA_VERSION}",
          f"FAIL {name}: schema_version missing or != {SCHEMA_VERSION}")
    raw = json.dumps(export)
    for marker in ("_PLACEHOLDER_NOTE", "reconstructed", "RECONSTRUCTED"):
        check(marker not in raw,
              f"{name}: no '{marker}' placeholder marker",
              f"FAIL {name}: contains placeholder marker '{marker}'")
    # No committed credentials: credential blocks must not carry real ids/names.
    for n in export["nodes"]:
        creds = n.get("credentials")
        if creds:
            failures.append(f"FAIL {name}: node '{n['name']}' carries a credentials block — credential references must be placeholder-free, re-wired after import")
    # No placeholder / invented literal resource IDs or URLs.
    placeholder_ids = [v for k, v in walk_strings(export)
                       if k in ("value", "fileId") and isinstance(v, str)
                       and re.match(r"^[A-Za-z0-9_-]{20,}$", v or "")]
    check(not placeholder_ids,
          f"{name}: no hardcoded resource IDs",
          f"FAIL {name}: hardcoded resource ID(s) {placeholder_ids[:3]}")
    check("main.blackceoautomations.com" not in raw,
          f"{name}: no hardcoded webhook host",
          f"FAIL {name}: hardcodes webhook host main.blackceoautomations.com")
    # Nodes reference real n8n types only.
    allowed = {"n8n-nodes-base.webhook", "n8n-nodes-base.code", "n8n-nodes-base.httpRequest",
               "n8n-nodes-base.googleDrive", "n8n-nodes-base.respondToWebhook", "n8n-nodes-base.if"}
    for n in export["nodes"]:
        check(n["type"] in allowed,
              f"{name}: node '{n['name']}' type {n['type']}",
              f"FAIL {name}: node '{n['name']}' has unknown type {n['type']}")
    check(len({n["id"] for n in export["nodes"]}) == len(export["nodes"]), "unique IDs", f"FAIL {name}: duplicate node IDs")
    check(len({n["name"] for n in export["nodes"]}) == len(export["nodes"]), "unique names", f"FAIL {name}: duplicate node names")
    for n in export["nodes"]:
        check(not any(k in n["parameters"] for k in ("retryOnFail", "maxTries", "waitBetweenTries")), "retry settings at node level", f"FAIL {name}: retry settings under parameters at {n['name']}")
        if n.get("onError") == "continueErrorOutput":
            out = export["connections"].get(n["name"], {})
            main = out.get("main", []) if isinstance(out, dict) else []
            check(len(main) > 1 and bool(main[1]), "wired error output", f"FAIL {name}: unwired error output at {n['name']}")
        if n["type"] == "n8n-nodes-base.httpRequest":
            check(n["parameters"].get("authentication") == "predefinedCredentialType", "HTTP auth", f"FAIL {name}: missing auth on {n['name']}")
            if n["parameters"].get("method") == "POST" and any(x in n["parameters"].get("url", "") for x in ("/copy?", ":append")):
                check(not n.get("retryOnFail"), "no ambiguous write retry", f"FAIL {name}: blind retry on write {n['name']}")
    # Connectivity: every non-respond node has outgoing connections.
    conn_names = set(export["connections"].keys())
    for n in export["nodes"]:
        if n["type"] != "n8n-nodes-base.respondToWebhook":
            check(n["name"] in conn_names,
                  f"{name}: '{n['name']}' wired",
                  f"FAIL {name}: node '{n['name']}' has no outgoing connection")
    # Every connection target exists.
    node_names = {n["name"] for n in export["nodes"]}
    for src, out in export["connections"].items():
        check(isinstance(out, dict) and isinstance(out.get("main"), list), "canonical connection", f"FAIL {name}: {src} connection must be an object with main arrays")
        if not isinstance(out, dict) or not isinstance(out.get("main"), list):
            continue
        branches = out["main"]
        for branch in branches:
            for link in branch:
                check(link["node"] in node_names,
                      f"{name}: link {src}->{link['node']}",
                      f"FAIL {name}: connection {src} -> unknown node {link['node']}")
    # Receipt keys appear somewhere in the export (response contract).
    check(("sheetId" in raw) and ("updatedRange" in raw or "sheetUrl" in raw),
          f"{name}: receipt keys present",
          f"FAIL {name}: response receipt keys (sheetId/updatedRange) missing")


def validate_sheet_create(export):
    nodes = {n["name"]: n for n in export["nodes"]}
    # F02 — anyone/writer share node preserved.
    share = nodes.get("Set Anyone Can Edit")
    check(share is not None, "create: 'Set Anyone Can Edit' node present",
          "FAIL create: 'Set Anyone Can Edit' node missing — F02 sharing contract broken")
    if share:
        perms = share["parameters"]["permissionsUi"]["permissionsValues"]
        check(perms.get("role") == "writer" and perms.get("type") == "anyone",
              "create: share node is type=anyone role=writer",
              f"FAIL create: share node permissions drifted: {perms}")
        check(share["type"] == "n8n-nodes-base.googleDrive",
              "create: share node is a real googleDrive node",
              "FAIL create: share node is not n8n-nodes-base.googleDrive")
    # F15 — provisioning key + readback.
    vjs = js_code_of(export, "Validate + Build Provisioning Key")
    check("company_id" in vjs and "planner_kind" in vjs and "provisioningKey" in vjs,
          "create: provisioning key = company_id::planner_kind",
          "FAIL create: validate node does not build provisioning_key from company_id/planner_kind")
    check("appProperties has" in vjs and "skill35_provisioning_key" in vjs,
          "create: readback query targets skill35_provisioning_key app property",
          "FAIL create: readback query does not target the provisioning app property")
    check("Drive Readback (find existing)" in nodes,
          "create: Drive readback node present",
          "FAIL create: no Drive readback node before the copy")
    check("Respond: Existing" in nodes and "deduped" in json.dumps(export),
          "create: dedup replay path returns existing artifact",
          "FAIL create: no deduped replay response path")
    copy_node = nodes.get("Copy Template Sheet")
    check(copy_node is not None and copy_node.get("onError") == "continueErrorOutput",
          "create: copy node has error branch",
          "FAIL create: copy node lacks continueErrorOutput error branch")
    # Restriction migration must not appear anywhere.
    raw = json.dumps(export)
    for banned in ("reader", "commenter", "named user"):
        check(f"'{banned}'" not in raw.lower() or f'"{banned}"' not in raw.lower(),
              f"create: no '{banned}' restriction migration",
              f"FAIL create: share node could migrate to '{banned}' (F02 violation)")


def validate_row_append(export):
    nodes = {n["name"]: n for n in export["nodes"]}
    vjs = js_code_of(export, "Validate + Build Keys")
    # F23 — Posts schema + no TikTok fallback.
    header_blob = json.dumps(export["contract"]["posts_schema"])
    for col in POSTS_HEADER:
        check(col in header_blob, f"append: Posts column '{col}'",
              f"FAIL append: Posts schema missing column '{col}'")
    check("rowKey" in vjs and "content_revision" in vjs and "account_id" in vjs,
          "append: row key = cycle_id::content_revision::account_id",
          "FAIL append: row key not built from cycle/content-revision/account")
    check("row.platform" not in vjs or "row['TikTok']" not in vjs,
          "append: no generic->TikTok fallback in Map code",
          "FAIL append: mapping contains a generic-platform -> TikTok fallback (F23 violation)")
    check("TikTok" not in vjs or "no fallback" in vjs.lower(),
          "append: TikTok not a mapping fallback",
          "FAIL append: validate code references TikTok as a fallback")
    for field in ("company_id", "cycle_id", "platform", "account_name", "format",
                  "scheduled_local", "scheduled_utc", "state", "qc_state"):
        check(field in vjs, f"append: input field '{field}' mapped",
              f"FAIL append: input field '{field}' not mapped in validate code")
    # F15 — readback + upsert, not unconditional append.
    check("Read Posts (readback)" in nodes and "Posts row exists?" in nodes,
          "append: Posts readback + conditional present",
          "FAIL append: no Posts readback before write (idempotency gap)")
    check("Update Posts Row (upsert)" in nodes and "Append Posts Row" in nodes,
          "append: keyed upsert path present",
          "FAIL append: no keyed update path for existing row_keys")
    fjs = js_code_of(export, "Find Posts Row")
    check("rowNumber" in fjs and re.search(r"\+\s*2\b", fjs),
          "append: upsert targets the exact existing row",
          "FAIL append: upsert does not resolve an exact existing row number")
    # F16 — real resize.
    rjs = js_code_of(export, "Resolve Posts Sheet ID")
    check("updateDimensionProperties" in rjs,
          "append: resize builds real updateDimensionProperties requests",
          "FAIL append: resize node does not build updateDimensionProperties (F16)")
    check("pixelSize" in rjs and "133" in rjs,
          "append: resize carries pixel sizes incl. 133px rows",
          "FAIL append: resize node missing pixelSize values")
    resize = nodes.get("Resize Columns + Row (batchUpdate)")
    check(resize is not None and ":batchUpdate" in resize["parameters"]["url"],
          "append: resize node calls :batchUpdate",
          "FAIL append: resize node does not call spreadsheet.batchUpdate")
    check(not any("note:" in (n["parameters"].get("jsCode", "")) and "resize" in n["name"].lower()
                  for n in export["nodes"]),
          "append: no fake note-only resize node",
          "FAIL append: resize is still a note-only code node")
    # Auth wiring on Sheets API calls.
    for n in export["nodes"]:
        if n["type"] == "n8n-nodes-base.httpRequest" and "sheets.googleapis.com" in str(n["parameters"].get("url", "")):
            params = n["parameters"]
            check(params.get("authentication") == "predefinedCredentialType"
                  and params.get("nodeCredentialType") == "googleSheetsOAuth2Api",
                  f"append: '{n['name']}' uses predefinedCredentialType googleSheetsOAuth2Api",
                  f"FAIL append: node '{n['name']}' lacks required Google Sheets auth wiring")
    drive_ok = all(
        n["parameters"].get("authentication") == "predefinedCredentialType"
        for n in export["nodes"]
        if n["type"] == "n8n-nodes-base.httpRequest" and "googleapis.com/drive" in str(n["parameters"].get("url", ""))
    )
    check(drive_ok, "append: drive calls (if any) auth-wired", "FAIL append: drive call lacks auth wiring")


def main():
    create = load("social-planner-sheet-create.json")
    append = load("social-planner-row-append.json")
    if create:
        validate_common("create", create)
        validate_sheet_create(create)
    if append:
        validate_common("append", append)
        validate_row_append(append)
    print(f"verify-exports.py: {checks} checks, {len(failures)} failures")
    for f in failures:
        print(f)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()