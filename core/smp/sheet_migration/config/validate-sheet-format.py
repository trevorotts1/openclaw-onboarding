#!/usr/bin/env python3
"""validate-sheet-format.py — validate the Skill 35 planner sheet contract at
schema 1.3.0 and its n8n export wiring (Owner D27 / decision 35 / plan section
6.15, 2026-10-07; manual H5 rewrite 2026-10-08).

Source line: "add drama song fields to the Weekly Overview (style chosen,
status, KIE cost, video link, channels posted) as schema 1.3.0; migrate live
client sheets with scripts/migrate-template.py (no data loss); update the
row-append webhook payload and config/validate-sheet-format.py."

The installed contract
``35-social-media-planner/config/sheet-template.schema.json`` is authoritative:
the row-append upsert key ``cycle_id`` is PINNED at column U (index 20) and the
five drama-song fields sit at V..Z (indexes 21..25) under the installed payload
keys drama_song_style, drama_song_status, kie_cost_cents, drama_song_video_url
and drama_song_channels.

This is the staged 1.3.0 validator for the wave (Skill 35's own
config/validate-sheet-format.py still checks the 1.2.0 contract and stays
untouched). It keeps every F25 check the upstream validator runs — TEXT_EQ only,
color AND written label, dropdowns, frozen headers, compact This Week view,
never-copied example tab, unique headings, empty starter rows — and adds the
1.3.0 gate:

  * contract schema_version must be exactly 1.3.0,
  * the Weekly Overview must be the 20 legacy headings, then cycle_id at
    index 20 (column U), then the five installed drama-song headings at
    indexes 21..25 (V..Z) — no legacy column moved or renamed,
  * identity_fields.schema_version must keep the appProperties version-match
    the row-append webhook reads,
  * with --export: the staged social-planner-row-append.json payload carries
    the five drama fields, matches them to their Weekly Overview columns, and
    is version-matched to the sheet (1.3.0 writes U..Z with the key at U;
    1.2.0 keeps the 21-cell layout with the same key at U and reports the
    drama fields pending instead of overwriting it).

Usage:
  python3 core/smp/sheet_migration/config/validate-sheet-format.py            # resolve + validate the contract
  python3 core/smp/sheet_migration/config/validate-sheet-format.py PATH.json  # validate that contract
  python3 core/smp/sheet_migration/config/validate-sheet-format.py --export   # + validate the export wiring
  python3 core/smp/sheet_migration/config/validate-sheet-format.py --export --n8n-dir DIR

Contract resolution when no path is given:
  1. core/smp/sheet_schema_130/config/sheet-template.schema.json (sibling 1.3.0 unit)
  2. 35-social-media-planner/config/sheet-template.schema.json (Skill 35's contract)
  3. core/smp/sheet_migration/testdata/sheet-template-1.3.0.json (bundled)

Exit 0 = valid. Violations print FAIL lines and exit 1.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # .../config
MODULE_DIR = os.path.dirname(HERE)                         # .../sheet_migration
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

from migrate import (  # noqa: E402
    DRAMA_SONG_FIELDS,
    DRAMA_SONG_PAYLOAD_KEYS,
    LEGACY_OVERVIEW_HEADINGS,
    OVERVIEW_FIELD_INDEX,
    OVERVIEW_KEY_INDEX,
    OVERVIEW_TAB,
    SCHEMA_TO,
    TECHNICAL_HEADING,
    TECHNICAL_INDEX,
    WEEKLY_OVERVIEW_HEADINGS_130,
)

EXPECTED_THIS_WEEK_COLUMNS = ["Week", "Client", "Next Action", "Drafting", "QC",
                              "Scheduled", "Published", "Needs Attention"]
STAGED_APPEND = os.path.join(HERE, "n8n", "social-planner-row-append.json")
BUNDLED_CONTRACT = os.path.join(MODULE_DIR, "testdata",
                                "sheet-template-1.3.0.json")

failures = []
checks = 0

def check(cond, ok_msg, fail_msg):
    global checks
    checks += 1
    if not cond:
        failures.append(fail_msg)

def repo_root(start):
    """Walk up until the Skill 35 tree is visible; None outside the repo."""
    path = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(path, "35-social-media-planner")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent

def load(path):
    check(os.path.exists(path), "%s exists" % os.path.basename(path),
          "FAIL %s: file missing" % path)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as exc:  # noqa: BLE001
        failures.append("FAIL %s: invalid JSON (%s)" % (path, exc))
        return None

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

def resolve_contract(explicit):
    if explicit:
        return explicit
    root = repo_root(HERE)
    candidates = []
    if root:
        candidates.append(os.path.join(root, "core", "smp", "sheet_schema_130",
                                       "config", "sheet-template.schema.json"))
        candidates.append(os.path.join(root, "35-social-media-planner", "config",
                                       "sheet-template.schema.json"))
    candidates.append(BUNDLED_CONTRACT)
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[-1]

def validate_contract(contract, path=""):
    """F25 checks (upstream) + the 1.3.0 drama-song gate."""
    # --- 1.3.0 gate first: this validator has exactly one supported target.
    version = str(contract.get("schema_version", "")).strip()
    check(version == SCHEMA_TO,
          "contract: schema_version is %s" % SCHEMA_TO,
          "FAIL contract: schema_version is %r, expected %s — the drama-song "
          "fields are not on this contract yet (run scripts/"
          "migrate-template.py, merge sheet_schema_130, or pass the 1.3.0 "
          "contract path)%s" % (version, SCHEMA_TO,
                                (" [%s]" % path) if path else ""))

    statuses = contract.get("status_colors", {}).get("statuses", [])
    check(bool(statuses), "contract: status list present",
          "FAIL contract: status_colors.statuses missing or empty")
    labels = set()
    for st in statuses:
        label = st.get("label")
        if not label:
            failures.append("FAIL contract: a status entry has no written label")
            continue
        labels.add(label)
        # F25 — color AND label, never color as the only signal.
        check(bool(st.get("color")), "status '%s': color present" % label,
              "FAIL status '%s': no color defined" % label)
        check(bool(st.get("color_label")),
              "status '%s': written color label present" % label,
              "FAIL status '%s': no written label describing the color — color "
              "must not be the only signal" % label)

    fmt = json.dumps(contract)
    # Ban the EMITTED condition shape, not prose that describes the ban
    # ("never NUMBER_EQ", "NUMBER_EQ is banned"). Matched per string value so
    # JSON escaping cannot hide a real emission.
    emitted = [v for _k, v in walk_strings(contract)
               if isinstance(v, str)
               and re.search(r'type["\']?\s*[:=]\s*["\']?NUMBER_EQ', v)]
    check(not emitted,
          "contract: no NUMBER_EQ condition emitted for text statuses",
          "FAIL contract: NUMBER_EQ condition appears against text statuses — "
          "must be TEXT_EQ (%r)" % emitted[:1])
    check("TEXT_EQ" in fmt, "contract: TEXT_EQ rule type declared",
          "FAIL contract: no TEXT_EQ conditional format rule type declared")
    check("setDataValidation" in fmt or "dropdown_validation" in fmt,
          "contract: dropdown validation declared",
          "FAIL contract: no setDataValidation dropdown contract")
    check("frozen_headings_row" in fmt, "contract: frozen headers declared",
          "FAIL contract: frozen headers not declared")

    this_week = contract.get("tabs", {}).get("This Week", {})
    check(bool(this_week), "contract: This Week view present",
          "FAIL This Week view tab missing")
    tw_headings = this_week.get("headings", [])
    for col in EXPECTED_THIS_WEEK_COLUMNS:
        check(col in tw_headings, "This Week column '%s'" % col,
              "FAIL This Week view: missing column '%s'" % col)
    check(this_week.get("width", len(tw_headings)) <= 9,
          "This Week stays compact (~8 columns)",
          "FAIL This Week view: %d columns — keep the primary view compact"
          % len(tw_headings))

    example_tabs = [t for t, v in contract.get("tabs", {}).items()
                    if isinstance(v, dict) and (v.get("example_tab") or "Example" in t)]
    check(bool(example_tabs), "contract: separate example tab declared",
          "FAIL contract: no separate example tab for demonstrations")
    for t in example_tabs:
        v = contract["tabs"][t]
        check(v.get("copied_to_clients") is False,
              "tab '%s': never copied to clients" % t,
              "FAIL tab '%s': example tab must declare copied_to_clients=false" % t)

    for tab, cfg in contract.get("tabs", {}).items():
        if not isinstance(cfg, dict):
            continue
        heads = cfg.get("headings") or []
        if heads:
            dupes = {h for h in heads if heads.count(h) > 1}
            check(not dupes, "tab '%s': headings unique" % tab,
                  "FAIL tab '%s': duplicate headings %s (U:AN pattern)"
                  % (tab, sorted(dupes)))

    check(bool(contract.get("starter_rows_rule")),
          "contract: starter-rows-empty rule present",
          "FAIL contract: starter_rows_rule missing — template must start "
          "EMPTY of brand/campaign/publication content")

    # --- the installed 1.3.0 layout on Weekly Overview (plan 6.15 / H5) ----
    # legacy 0..19 (A..T), cycle_id pinned at 20 (U), drama at 21..25 (V..Z).
    ov = contract.get("tabs", {}).get(OVERVIEW_TAB, {})
    heads = list(ov.get("headings") or [])
    check(bool(heads), "contract: '%s' headings present" % OVERVIEW_TAB,
          "FAIL contract: '%s' tab missing or has no headings" % OVERVIEW_TAB)
    if heads:
        legacy_n = len(LEGACY_OVERVIEW_HEADINGS)
        check(heads[:legacy_n] == LEGACY_OVERVIEW_HEADINGS,
              "Weekly Overview: the 20 legacy headings are unchanged and in order",
              "FAIL Weekly Overview: legacy headings moved or were renamed — "
              "1.3.0 must keep them as the prefix (found %r)"
              % (heads[:legacy_n],))
        check(len(heads) > TECHNICAL_INDEX
              and heads[TECHNICAL_INDEX] == TECHNICAL_HEADING,
              "Weekly Overview: the row-append upsert key %r stays at index %d "
              "(column U)" % (TECHNICAL_HEADING, TECHNICAL_INDEX),
              "FAIL Weekly Overview: %r must stay at index %d (column U) — "
              "found %r; moving it puts the webhook key in a drama column and "
              "corrupts live sheets"
              % (TECHNICAL_HEADING, TECHNICAL_INDEX,
                 heads[TECHNICAL_INDEX] if len(heads) > TECHNICAL_INDEX else None))
        check(heads[legacy_n + 1:] == DRAMA_SONG_FIELDS,
              "Weekly Overview: drama-song fields at columns V..Z in order",
              "FAIL Weekly Overview: expected the five drama-song headings "
              "%s after %r at index %d, found %r"
              % (DRAMA_SONG_FIELDS, TECHNICAL_HEADING, TECHNICAL_INDEX,
                 heads[legacy_n + 1:]))
        legacy_set = {str(h).strip().lower() for h in LEGACY_OVERVIEW_HEADINGS}
        legacy_set.add(TECHNICAL_HEADING.strip().lower())
        collisions = [h for h in DRAMA_SONG_FIELDS
                      if h.strip().lower() in legacy_set]
        check(not collisions, "Weekly Overview: drama headings do not collide "
                              "with legacy or key columns",
              "FAIL Weekly Overview: drama-song heading(s) collide with an "
              "existing column: %s" % ", ".join(collisions))
        check(len(heads) == len(WEEKLY_OVERVIEW_HEADINGS_130),
              "Weekly Overview: 26 headings at 1.3.0 "
              "(20 legacy + cycle_id + 5 drama)",
              "FAIL Weekly Overview: %d headings, expected %d"
              % (len(heads), len(WEEKLY_OVERVIEW_HEADINGS_130)))
        for key, idx in OVERVIEW_FIELD_INDEX.items():
            check(idx < len(heads) and heads[idx] == DRAMA_SONG_FIELDS[idx - 21],
                  "payload key '%s' -> column index %d" % (key, idx),
                  "FAIL payload key '%s' does not map to index %d (%r)"
                  % (key, idx, heads[idx] if idx < len(heads) else None))
        check(OVERVIEW_KEY_INDEX < len(heads)
              and heads[OVERVIEW_KEY_INDEX] == TECHNICAL_HEADING,
              "upsert key index is %d at every schema version" % OVERVIEW_KEY_INDEX,
              "FAIL the upsert key index drifted off %d" % OVERVIEW_KEY_INDEX)

    declared = contract.get("drama_song_fields") or ov.get("drama_song_fields")
    if declared is not None:
        check(list(declared) == DRAMA_SONG_FIELDS,
              "contract: declared drama_song_fields match the wave contract",
              "FAIL contract: declared drama_song_fields %r != %r"
              % (list(declared), DRAMA_SONG_FIELDS))

    identity = contract.get("identity_fields", {})
    ident_sv = str(identity.get("schema_version", ""))
    check("appProperties" in ident_sv,
          "contract: identity schema_version keeps the appProperties "
          "version-match the row-append webhook reads",
          "FAIL contract: identity_fields.schema_version no longer documents "
          "the appProperties stamp the webhook version-matches on")

    # Every payload key must be nameable from the contract side.
    for key in DRAMA_SONG_PAYLOAD_KEYS:
        check(bool(key), "payload key '%s' defined" % key,
              "FAIL payload key '%s' missing" % key)

def _node(export, name):
    for n in export.get("nodes", []):
        if n.get("name") == name:
            return n
    return None

def _js(export, name):
    node = _node(export, name)
    if not node:
        return ""
    return (node.get("parameters") or {}).get("jsCode", "") or ""

def validate_row_append(export, path):
    """The staged row-append payload must carry the drama-song fields."""
    name = os.path.basename(path)
    version = str(export.get("schema_version", "")).strip()
    check(version == "1.2.0",
          "%s: payload schema_version 1.2.0" % name,
          "FAIL %s: payload schema_version is %r, expected '1.2.0'"
          % (name, version))
    meta = export.get("meta") or {}
    check(str(meta.get("schema_version", "")).strip() == "1.2.0",
          "%s: meta.schema_version 1.2.0" % name,
          "FAIL %s: meta.schema_version is %r"
          % (name, meta.get("schema_version")))
    contract = export.get("contract") or {}
    check(str(contract.get("schema_version", "")).strip() == "1.2.0",
          "%s: contract.schema_version 1.2.0" % name,
          "FAIL %s: contract.schema_version is %r"
          % (name, contract.get("schema_version")))

    dsc = contract.get("drama_song_contract")
    check(isinstance(dsc, dict), "%s: drama_song_contract declared" % name,
          "FAIL %s: contract.drama_song_contract missing — the payload does "
          "not declare the new fields" % name)
    if isinstance(dsc, dict):
        fields = dsc.get("fields") or []
        keys = [f.get("payload_key") for f in fields]
        heads = [f.get("heading") for f in fields]
        idxs = [f.get("overview_index") for f in fields]
        cols = [f.get("column") for f in fields]
        check(keys == DRAMA_SONG_PAYLOAD_KEYS,
              "%s: drama payload keys in order (installed keys)" % name,
              "FAIL %s: drama payload keys %r != %r"
              % (name, keys, DRAMA_SONG_PAYLOAD_KEYS))
        check(heads == DRAMA_SONG_FIELDS,
              "%s: drama headings match the installed sheet contract" % name,
              "FAIL %s: drama headings %r != %r"
              % (name, heads, DRAMA_SONG_FIELDS))
        check(idxs == [OVERVIEW_FIELD_INDEX[k] for k in DRAMA_SONG_PAYLOAD_KEYS],
              "%s: drama overview indexes 21..25" % name,
              "FAIL %s: drama overview indexes %r" % (name, idxs))
        check(cols == ["V", "W", "X", "Y", "Z"],
              "%s: drama columns V..Z" % name,
              "FAIL %s: drama columns %r != ['V','W','X','Y','Z']"
              % (name, cols))
        tech = dsc.get("technical_column")
        check(isinstance(tech, dict)
              and tech.get("heading") == TECHNICAL_HEADING
              and tech.get("index") == TECHNICAL_INDEX
              and str(tech.get("column", "")).upper() == "U",
              "%s: technical upsert key pinned at index %d (column U)"
              % (name, TECHNICAL_INDEX),
              "FAIL %s: drama_song_contract.technical_column is %r — the %r "
              "upsert key must stay at index %d (column U) or the webhook "
              "writes into a drama column"
              % (name, tech, TECHNICAL_HEADING, TECHNICAL_INDEX))
        accepted = dsc.get("accepted_payload_versions") or []
        check("1.1.0" in accepted and "1.2.0" in accepted,
              "%s: accepts legacy 1.1.0 callers and 1.2.0" % name,
              "FAIL %s: accepted_payload_versions %r must include 1.1.0 and "
              "1.2.0" % (name, accepted))
        check(str(dsc.get("sheet_schema_version")) == SCHEMA_TO,
              "%s: targets sheet schema %s" % (name, SCHEMA_TO),
              "FAIL %s: drama_song_contract.sheet_schema_version is %r"
              % (name, dsc.get("sheet_schema_version")))
        check("appProperties" in str(dsc.get("sheet_version_match", "")),
              "%s: sheet version-match documented (appProperties)" % name,
              "FAIL %s: sheet_version_match does not mention the "
              "appProperties stamp" % name)

    # Validate + Build Keys: carries and normalises the fields, accepts legacy.
    vjs = _js(export, "Validate + Build Keys")
    check(bool(vjs), "%s: 'Validate + Build Keys' node present" % name,
          "FAIL %s: node 'Validate + Build Keys' missing" % name)
    for key in DRAMA_SONG_PAYLOAD_KEYS:
        check(key in vjs, "%s: payload carries '%s'" % (name, key),
              "FAIL %s: 'Validate + Build Keys' does not handle '%s' — the "
              "webhook payload does not carry the new field" % (name, key))
    check("ACCEPTED" in vjs and "'1.1.0'" in vjs and "'1.2.0'" in vjs,
          "%s: payload accepts schema_version 1.1.0 and 1.2.0" % name,
          "FAIL %s: payload version gate does not accept both 1.1.0 and 1.2.0"
          % name)
    check("kie_cost_cents" in vjs and "invalid kie_cost_cents" in vjs,
          "%s: kie_cost_cents is validated" % name,
          "FAIL %s: kie_cost_cents is not validated in the webhook" % name)

    # Version match: the webhook reads the sheet's own stamped version.
    meta_node = _node(export, "Verify Sheet Metadata (F14)")
    check(meta_node is not None,
          "%s: metadata verification node present" % name,
          "FAIL %s: node 'Verify Sheet Metadata (F14)' missing" % name)
    if meta_node:
        url = str((meta_node.get("parameters") or {}).get("url", ""))
        check("properties.appProperties" in url,
              "%s: metadata read includes properties.appProperties" % name,
              "FAIL %s: metadata read does not fetch properties.appProperties, "
              "so the webhook cannot version-match the sheet" % name)

    rd_node = _node(export, "Read Weekly Overview (readback)")
    if rd_node:
        url = str((rd_node.get("parameters") or {}).get("url", ""))
        check("A2:Z" in url,
              "%s: Weekly Overview readback covers A2:Z" % name,
              "FAIL %s: Weekly Overview readback is %r — a 1.3.0 sheet keeps "
              "the drama fields through column Z" % (name, url))
    else:
        check(False, "%s: Weekly Overview readback present" % name,
              "FAIL %s: node 'Read Weekly Overview (readback)' missing" % name)

    # Build Overview Summary: writes the fields, version-matched layout, and
    # NEVER writes over the key column at index 20.
    ojs = _js(export, "Build Overview Summary")
    for key in DRAMA_SONG_PAYLOAD_KEYS:
        check(key in ojs, "%s: overview writes '%s'" % (name, key),
              "FAIL %s: 'Build Overview Summary' does not write '%s'"
              % (name, key))
    check("appProperties" in ojs and "sheetSchema" in ojs,
          "%s: overview version-matches on the sheet's stamped version" % name,
          "FAIL %s: 'Build Overview Summary' does not version-match the sheet"
          % name)
    check("ovLastCol" in ojs and "'Z'" in ojs and "'U'" in ojs,
          "%s: overview picks Z at 1.3.0 and U at 1.2.0" % name,
          "FAIL %s: 'Build Overview Summary' does not select the row width by "
          "sheet version" % name)
    check("KEY_INDEX" in ojs and str(TECHNICAL_INDEX) in ojs,
          "%s: overview keeps the upsert key at index %d (column U)"
          % (name, TECHNICAL_INDEX),
          "FAIL %s: 'Build Overview Summary' does not pin the upsert key at "
          "index %d (column U)" % (name, TECHNICAL_INDEX))
    check("dramaPending" in ojs and "dramaWritten" in ojs,
          "%s: receipt distinguishes written vs pending drama fields" % name,
          "FAIL %s: 'Build Overview Summary' reports neither dramaWritten nor "
          "dramaPending" % name)
    for idx in sorted(OVERVIEW_FIELD_INDEX.values()):
        check(str(idx) in ojs, "%s: overview index %d referenced" % (name, idx),
              "FAIL %s: overview index %d not referenced" % (name, idx))

    for node_name in ("Update Overview Row (upsert)", "Append Overview Row"):
        node = _node(export, node_name)
        check(node is not None, "%s: '%s' present" % (name, node_name),
              "FAIL %s: node '%s' missing" % (name, node_name))
        if node:
            url = str((node.get("parameters") or {}).get("url", ""))
            check("ovLastCol" in url,
                  "%s: '%s' range follows ovLastCol" % (name, node_name),
                  "FAIL %s: '%s' hardcodes the column range (%r) — a 1.3.0 "
                  "sheet writes 26 cells" % (name, node_name, url))

    rjs = _js(export, "Build Receipt")
    for token in ("drama_song_written", "drama_song_pending",
                  "sheet_schema_version", "schema_version: '1.2.0'"):
        check(token in rjs, "%s: receipt carries '%s'" % (name, token),
              "FAIL %s: 'Build Receipt' does not carry '%s'" % (name, token))

    batch = [n for n in export.get("nodes", [])
             if n.get("type") == "n8n-nodes-base.httpRequest"
             and ":batchUpdate" in str((n.get("parameters") or {}).get("url", ""))]
    check(bool(batch), "%s: formatting/sizing runs as a real batchUpdate"
          % name, "FAIL %s: no spreadsheet.batchUpdate node" % name)

def validate_sheet_create(export, path):
    """F25 wiring checks — ported from Skill 35's validator, unchanged."""
    name = os.path.basename(path)
    fmt_node = _node(export, "Build Formatting Requests (F25)")
    check(fmt_node is not None, "%s: F25 formatting node present" % name,
          "FAIL %s: no 'Build Formatting Requests (F25)' node" % name)
    if fmt_node:
        js = (fmt_node.get("parameters") or {}).get("jsCode", "")
        check("TEXT_EQ" in js, "%s: TEXT_EQ conditional rules emitted" % name,
              "FAIL %s: formatting node does not emit TEXT_EQ rules" % name)
        check("type: 'NUMBER_EQ'" not in js and 'type: "NUMBER_EQ"' not in js,
              "%s: no NUMBER_EQ condition emitted for text statuses" % name,
              "FAIL %s: formatting node emits NUMBER_EQ against text" % name)
        check("setDataValidation" in js or "ONE_OF_LIST" in js,
              "%s: dropdown validation emitted" % name,
              "FAIL %s: formatting node emits no setDataValidation dropdown"
              % name)
        check("frozenRowCount" in js, "%s: frozen headers emitted" % name,
              "FAIL %s: formatting node does not freeze header rows" % name)
        check("This Week" in js, "%s: This Week view provisioned" % name,
              "FAIL %s: formatting node does not create the This Week view"
              % name)
        for st in ("Complete", "Failed", "QC Review", "Scheduled", "Published",
                   "Needs Attention"):
            check(st in js, "%s: status '%s' has a color rule + label"
                  % (name, st),
                  "FAIL %s: status '%s' missing from the color/label rule list"
                  % (name, st))
    batch = [n for n in export.get("nodes", [])
             if n.get("type") == "n8n-nodes-base.httpRequest"
             and ":batchUpdate" in str((n.get("parameters") or {}).get("url", ""))]
    check(bool(batch), "%s: formatting runs as a real batchUpdate" % name,
          "FAIL %s: no spreadsheet.batchUpdate node carries the formatting "
          "requests" % name)

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate the planner sheet contract at schema 1.3.0 "
                    "and its n8n export wiring")
    parser.add_argument("contract", nargs="?", default=None,
                        help="contract JSON (default: resolved 1.3.0 contract)")
    parser.add_argument("--export", action="store_true",
                        help="also validate the n8n export wiring")
    parser.add_argument("--n8n-dir", default=os.path.join(HERE, "n8n"),
                        help="directory holding the staged row-append export")
    args = parser.parse_args(argv)

    path = resolve_contract(args.contract)
    contract = load(path)
    if contract is not None:
        validate_contract(contract, path=path)

    exports = []
    if args.export:
        append_path = os.path.join(args.n8n_dir, "social-planner-row-append.json")
        exports.append(append_path)
        export = load(append_path)
        if export is not None:
            validate_row_append(export, append_path)
        root = repo_root(HERE)
        if root:
            create_path = os.path.join(root, "35-social-media-planner", "config",
                                       "n8n", "social-planner-sheet-create.json")
            if os.path.exists(create_path):
                exports.append(create_path)
                create = load(create_path)
                if create is not None:
                    validate_sheet_create(create, create_path)

    print("validate-sheet-format.py (schema %s): %d checks, %d failures"
          % (SCHEMA_TO, checks, len(failures)))
    print("contract: %s" % path)
    if args.export:
        print("exports: %s" % (", ".join(os.path.basename(p) for p in exports)
                               or "(none)"))
    for f in failures:
        print(f)
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())