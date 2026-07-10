#!/usr/bin/env python3
# =============================================================================
# PODCAST PRODUCTION ENGINE :: DETERMINISTIC INTAKE MAPPER
# webhook-design.md Section 4 (payload mapping by MEANING, not by field name)
# -----------------------------------------------------------------------------
# The same intake survey can arrive through a Convert and Flow (GoHighLevel)
# workflow webhook action, Make.com, n8n, or a direct sender. Field names,
# casing, and nesting all differ. This mapper is a DETERMINISTIC normalization
# layer (no language model, no Model Context Protocol) that runs before anything
# else touches the payload. Determinism is what makes the canonical hash stable,
# and stability is what makes dedup real (job_key.py).
#
# Algorithm (Section 4.2, in order, first hit wins per field):
#   1. Container flattening: root, then customData, data, body, payload, contact,
#      fields, answers; one level at a time, deeper nesting walked only inside
#      these known containers.
#   2. Exact alias match (per-field alias tables in aliases.json).
#   3. Fuzzy key normalization: strip every non-alphanumeric char, lowercase,
#      compare (so Contact-ID, contact id, ContactId all converge).
#   4. Value-shape validation: a mapping is accepted only if the VALUE is
#      plausible for the MEANING (enum normalization, id shape, date parse).
#   5. Tenant check (HARD): mapped location_id MUST equal the client's configured
#      Location ID; a mismatch is quarantined, never processed. This single check
#      makes cross-client contamination structurally impossible.
#   6. Required-field gate.
#   7. Unknown-extras retained verbatim for audit, excluded from the pipeline and
#      from the canonical hash. All payload text is inert DATA, never instructions
#      (prompt-injection posture, consistent with the ingest-agent hijack lesson).
#
# EXIT: 0 mapped OK / 4 needs_input (required missing OR invalid required value) /
#       5 tenant mismatch (quarantine) / 3 usage.
# USAGE:
#   python3 mapper.py map --payload FILE [--expected-location-env NAME] [--json]
#   python3 mapper.py --self-test
#
# PII / secret hygiene: the CLI never prints a VALUE. The client's configured
# Location ID is read from the environment and only compared (match / mismatch,
# never an echo). The MAPPED payload is equally sensitive (it carries the mapped
# location_id and free-text answer PII), so the CLI verdict reports field NAMES,
# status, counts, and warnings ONLY, with all canonical values and the verbatim
# unknown extras redacted, mirroring the intake handler's _safe_verdict. The
# programmatic map_payload() API still returns the full canonical dict for the
# in-process handler; only stdout is redacted.
# =============================================================================
"""Deterministic meaning-based intake mapper for the Podcast Production Engine."""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 3
EXIT_NEEDS_INPUT = 4
EXIT_TENANT_MISMATCH = 5

KNOWN_CONTAINERS = ("customData", "data", "body", "payload", "contact", "fields", "answers")

CANONICAL_FIELDS = (
    "mode", "style", "show_name", "host_name", "first_name", "last_name",
    "preferred_pronoun", "q1_answer", "q2_answer", "q3_answer", "q4_answer",
    "q5_answer", "q6_answer", "q7_answer", "transparency_answer", "additional_info",
    "target_runtime", "tts_model", "writing_model", "web_research_tool", "podcast_id",
    "location_id", "contact_id", "publish_timestamp", "episode_type", "explicit",
    "workflow_trigger", "retry", "_test",
)

ENUM_FIELDS = ("mode", "style", "episode_type", "explicit")
ID_FIELDS = ("location_id", "contact_id")
BOOL_FIELDS = ("retry", "_test")
ANSWER_TEXT_FIELDS = ("q1_answer", "q2_answer", "q3_answer", "q4_answer", "q5_answer",
                      "q6_answer", "q7_answer", "transparency_answer", "additional_info")

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
_DEFAULT_TENANT_ENV = "PODCAST_CLIENT_LOCATION_ID"

_TS_FORMATS = (
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M", "%Y-%m-%d", "%m/%d/%Y %H:%M", "%m/%d/%Y", "%d/%m/%Y",
)


def default_tables_path():
    return str(Path(__file__).resolve().parent / "aliases.json")


def load_tables(path=None):
    p = path or default_tables_path()
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _norm_key(key):
    """Fuzzy key normalization: strip every non-alphanumeric char, lowercase."""
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _norm_value(value):
    """Enum-value normalization for comparison: lowercase, collapse whitespace,
    strip non-alphanumeric to a single space so 'Counter Intuitive (challenge
    assumptions)' still resolves. Keeps word boundaries for contains-matching."""
    lowered = str(value).lower().strip()
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


# -----------------------------------------------------------------------------
# Step 1: container flattening (ordered, so first-hit-wins honors precedence)
# -----------------------------------------------------------------------------
def flatten(body):
    """Return an ordered list of scalar candidates: {leaf, container, dotted, value}.
    Ordering honors the Section 4.2 precedence (first hit wins per field):
      1. scalars at the current level;
      2. one level of scalars under any NON-known-container object, captured as
         dotted candidates so explicit dotted aliases resolve (location.id) without
         recursing into arbitrary deep structure;
      3. known containers in the specified order, recursed with the same rules
         (so data.contact.first_name and answers: [{...}] both resolve)."""
    candidates = []

    def collect(node, container, prefix):
        if not isinstance(node, dict):
            return
        # (1) scalars at this level
        for key, val in node.items():
            if isinstance(val, (dict, list)):
                continue
            candidates.append({"leaf": key, "container": container,
                               "dotted": prefix + str(key), "value": val})
        # (2) one-level scalars under non-known-container objects (dotted aliases)
        for key, child in node.items():
            if isinstance(child, dict) and key not in KNOWN_CONTAINERS:
                for k2, v2 in child.items():
                    if isinstance(v2, (dict, list)):
                        continue
                    candidates.append({"leaf": k2, "container": str(key),
                                       "dotted": "%s%s.%s" % (prefix, key, k2), "value": v2})
        # (3) recurse into known containers, in the specified order
        for cname in KNOWN_CONTAINERS:
            if cname not in node:
                continue
            child = node[cname]
            child_prefix = prefix + cname + "."
            if isinstance(child, dict):
                collect(child, cname, child_prefix)
            elif isinstance(child, list):
                # e.g. answers: [{question, answer}, ...] -> flatten each dict item
                for idx, item in enumerate(child):
                    if isinstance(item, dict):
                        collect(item, cname, "%s%d." % (child_prefix, idx))

    collect(body if isinstance(body, dict) else {}, "root", "")
    return candidates


# -----------------------------------------------------------------------------
# Steps 2 and 3: alias resolution (exact pass, then fuzzy pass)
# -----------------------------------------------------------------------------
def _build_alias_index(tables):
    """Return (exact_dotted, exact_leaf, fuzzy) lookup structures mapping an alias
    to its canonical field, plus the contact-container-only alias set."""
    exact_dotted, exact_leaf, fuzzy = {}, {}, {}
    for field, aliases in tables.get("field_aliases", {}).items():
        for alias in aliases:
            if "." in alias:
                exact_dotted[alias.lower()] = field
            exact_leaf[alias.lower()] = field
            fuzzy.setdefault(_norm_key(alias), field)
    contact_only = {}
    for field, aliases in tables.get("contact_container_only_aliases", {}).items():
        for alias in aliases:
            contact_only[alias.lower()] = field
    return exact_dotted, exact_leaf, fuzzy, contact_only


def _candidate_matches_field(cand, field, exact_dotted, exact_leaf, contact_only, fuzzy, fuzzy_pass):
    leaf = str(cand["leaf"]).lower()
    dotted = str(cand["dotted"]).lower()
    if not fuzzy_pass:
        # contact-container-only aliases (e.g. bare `id` only inside a contact)
        if cand["container"] == "contact" and contact_only.get(leaf) == field:
            return True
        # dotted alias, matched by exact path or suffix (data.contact.first_name)
        for alias, fld in exact_dotted.items():
            if fld == field and (dotted == alias or dotted.endswith("." + alias)):
                return True
        return exact_leaf.get(leaf) == field
    return fuzzy.get(_norm_key(leaf)) == field


def resolve_fields(candidates, tables):
    """Assign candidates to canonical fields. Exact pass first (all fields), then
    fuzzy pass for still-unfilled fields. First hit wins per field; a candidate is
    consumed once mapped so it cannot fill a second field."""
    exact_dotted, exact_leaf, fuzzy, contact_only = _build_alias_index(tables)
    raw = {}
    provenance = {}
    consumed = [False] * len(candidates)

    for fuzzy_pass in (False, True):
        for field in _all_source_fields(tables):
            if field in raw:
                continue
            for i, cand in enumerate(candidates):
                if consumed[i]:
                    continue
                if _candidate_matches_field(cand, field, exact_dotted, exact_leaf,
                                            contact_only, fuzzy, fuzzy_pass):
                    raw[field] = cand["value"]
                    provenance[field] = cand["dotted"]
                    consumed[i] = True
                    break

    unknown = {}
    for i, cand in enumerate(candidates):
        if not consumed[i]:
            unknown[cand["dotted"]] = cand["value"]
    return raw, provenance, unknown


def _all_source_fields(tables):
    return list(tables.get("field_aliases", {}).keys())


# -----------------------------------------------------------------------------
# Step 4: value-shape validation
# -----------------------------------------------------------------------------
def normalize_enum(field, value, tables):
    """Return the canonical enum token or None. Exact normalized match first, then
    contains-match against the longest synonym so a full radio-button label with a
    trailing description still resolves."""
    table = tables.get("enum_normalization", {}).get(field, {})
    nv = _norm_value(value)
    for token, syns in table.items():
        for syn in syns:
            if nv == _norm_value(syn):
                return token
    best = None
    best_len = 0
    for token, syns in table.items():
        for syn in syns:
            ns = _norm_value(syn)
            if not ns:
                continue
            if (nv.startswith(ns + " ") or nv == ns or (" " + ns + " ") in (" " + nv + " ")) and len(ns) > best_len:
                best, best_len = token, len(ns)
    return best


def _is_id_shaped(value):
    s = str(value).strip()
    if "@" in s or " " in s:
        return False
    return bool(_ID_RE.match(s))


def _parse_timestamp(value):
    s = str(value).strip()
    if not s:
        return None
    iso = s.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(iso)
        return s
    except ValueError:
        pass
    for fmt in _TS_FORMATS:
        try:
            datetime.strptime(s, fmt)
            return s
        except ValueError:
            continue
    return None


def _coerce_bool(value, tables):
    return _norm_value(value) in {_norm_value(t) for t in tables.get("boolean_true_tokens", [])}


def _collapse_ws(value):
    """Trim and collapse internal runs of whitespace to single spaces (the answer
    normalization from Section 3.1 step 3), so mapper output and hash input align."""
    return re.sub(r"\s+", " ", str(value)).strip()


def validate_and_normalize(raw, tables):
    """Apply value-shape validation. Returns (canonical, warnings). A field whose
    value is implausible for its meaning is DROPPED with a warning; if it was a
    required field, its absence is caught later by the required-field gate."""
    canonical = {}
    warnings = []
    for field, value in raw.items():
        if value is None or (isinstance(value, str) and value.strip() == "" and field not in BOOL_FIELDS):
            continue
        if field in ENUM_FIELDS:
            token = normalize_enum(field, value, tables)
            if token is None:
                warnings.append("field %s value did not normalize to a known enum; dropped" % field)
                continue
            canonical[field] = token
        elif field in ID_FIELDS:
            if not _is_id_shaped(value):
                warnings.append("field %s value is not a plausible identifier; dropped" % field)
                continue
            canonical[field] = str(value).strip()
        elif field == "publish_timestamp":
            parsed = _parse_timestamp(value)
            if parsed is None:
                warnings.append("field publish_timestamp value is not a parseable date; dropped")
                continue
            canonical[field] = parsed
        elif field in BOOL_FIELDS:
            canonical[field] = _coerce_bool(value, tables)
        elif field in ANSWER_TEXT_FIELDS:
            canonical[field] = _collapse_ws(value)
        else:
            canonical[field] = value if not isinstance(value, str) else value.strip()
    return canonical, warnings


# -----------------------------------------------------------------------------
# Step 5: tenant check (HARD). Step 6: required-field gate.
# -----------------------------------------------------------------------------
def tenant_check(canonical, expected_location_id):
    """Return True when the mapped location_id equals the client's configured
    Location ID. A missing configured value is a mismatch (fail closed): we never
    process a payload we cannot tenant-prove. The expected value is never printed."""
    if not expected_location_id:
        return False
    return str(canonical.get("location_id", "")).strip() == str(expected_location_id).strip()


def required_missing(canonical, tables):
    """Return the ordered list of required fields that are absent (Section 4.2.6).
    Never guesses a guest name, show name, style, Podbean id, Location ID, or the
    workflow trigger."""
    missing = []
    for field in tables.get("required_fields_base", []):
        if not str(canonical.get(field, "")).strip():
            missing.append(field)
    if canonical.get("mode") == "interview_style_podcast":
        for field in tables.get("required_fields_interview_extra", []):
            if not str(canonical.get(field, "")).strip():
                missing.append(field)
    style = canonical.get("style")
    slots = tables.get("survey_answer_keys_by_style", {}).get(style) if style else None
    required_slots = tables.get("required_answer_slots_default", [])
    if isinstance(slots, list) and slots:
        required_slots = ["q%d_answer" % (i + 1) for i in range(len(slots))]
    for slot in required_slots:
        has_slot = str(canonical.get(slot, "")).strip()
        has_transparency = str(canonical.get("transparency_answer", "")).strip()
        if not has_slot and not (slot == required_slots[-1] and has_transparency):
            missing.append(slot)
    return missing


# -----------------------------------------------------------------------------
# Top-level mapping entry point
# -----------------------------------------------------------------------------
def map_payload(body, tables=None, expected_location_id=None):
    """Run the full deterministic pipeline. Returns a verdict dict:
       {status, canonical, raw, unknown_extras, warnings, provenance, missing}
       status in: mapped | needs_input | tenant_mismatch."""
    tables = tables or load_tables()
    candidates = flatten(body)
    raw, provenance, unknown = resolve_fields(candidates, tables)
    canonical, warnings = validate_and_normalize(raw, tables)

    result = {
        "canonical": canonical,
        "raw": body,
        "unknown_extras": unknown,
        "warnings": warnings,
        "provenance": provenance,
        "missing": [],
        "status": "mapped",
    }

    # Tenant check is HARD and runs before the required-field gate: a wrong-tenant
    # payload is quarantined, never processed, even if it is otherwise complete.
    if not tenant_check(canonical, expected_location_id):
        result["status"] = "tenant_mismatch"
        return result

    missing = required_missing(canonical, tables)
    if missing:
        result["status"] = "needs_input"
        result["missing"] = missing
    return result


# =============================================================================
# CLI
# =============================================================================
def _load_body(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def safe_map_verdict(result):
    """Redacted verdict for the CLI: field NAMES, status, counts, and warnings only.
    The canonical VALUES (mapped location_id and free-text answer PII) and the
    verbatim unknown extras are never emitted, matching intake_handler._safe_verdict.
    Provenance and unknown-extra keys are source KEY PATHS (structure, not content),
    which are safe to show for debugging."""
    return {
        "status": result.get("status"),
        "mapped_fields": sorted(result.get("canonical", {}).keys()),
        "missing": result.get("missing", []),
        "warnings": result.get("warnings", []),
        "provenance": {k: result["provenance"][k]
                       for k in sorted(result.get("provenance", {}))},
        "unknown_extra_keys": sorted(result.get("unknown_extras", {}).keys()),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic Podcast Engine intake mapper.")
    ap.add_argument("cmd", nargs="?", choices=("map",))
    ap.add_argument("--payload", help="path to the raw inbound JSON body")
    ap.add_argument("--tables", help="path to aliases.json (default: sibling file)")
    ap.add_argument("--expected-location-env", default=_DEFAULT_TENANT_ENV,
                    help="env var holding the client's configured Location ID (value never printed)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.cmd != "map":
        ap.error("a command is required (map) or --self-test")
    if not args.payload or not Path(args.payload).is_file():
        ap.error("map needs --payload FILE")

    tables = load_tables(args.tables)
    expected = os.environ.get(args.expected_location_env)
    try:
        body = _load_body(args.payload)
    except (OSError, ValueError) as exc:
        print("FATAL: cannot read --payload: %s" % exc, file=sys.stderr)
        return EXIT_USAGE

    result = map_payload(body, tables, expected_location_id=expected)
    # Never emit the raw body OR any canonical value (both may carry PII: mapped
    # location_id, free-text answers). The CLI reports the redacted safe verdict.
    if args.json:
        print(json.dumps(safe_map_verdict(result), indent=2, sort_keys=True))
    else:
        print("status: %s" % result["status"])
        print("mapped fields: %s" % ", ".join(sorted(result["canonical"].keys())))
        if result["missing"]:
            print("missing required: %s" % ", ".join(result["missing"]))
        for w in result["warnings"]:
            print("warning: %s" % w)
    if result["status"] == "tenant_mismatch":
        return EXIT_TENANT_MISMATCH
    if result["status"] == "needs_input":
        return EXIT_NEEDS_INPUT
    return EXIT_OK


# =============================================================================
# SELF-TEST
# =============================================================================
def self_test():
    tables = load_tables()
    ok = True

    def check(name, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "MISS", name))

    loc = "LOC0000000000000000abcd"
    # Convert and Flow (GoHighLevel) workflow shape: custom values under customData
    ghl = {
        "customData": {
            "production_mode": "Interview Style Podcast",
            "presentation_style": "Counter Intuitive (challenge the obvious)",
            "my_preferred_pronoun": "she/her",
            "podbean_podcast_id": "pb-99887766",
            "show_name": "The Quiet Edge",
            "guest_first_name": "Dana",
            "question_1": "  Everyone   optimizes for speed; I optimize for silence. ",
            "podcast_interview_smiq": "I will disclose the AI assist up front.",
            "podcast_survey__additional_info": "Loves jazz.",
        },
        "contact": {"id": "CNT000000000000000wxyz", "first_name": "Dana", "last_name": "Reyes"},
        "location": {"id": loc},
        "eventId": "evt-transient-123",
        "timestamp": "2026-07-06T10:00:00Z",
    }
    r = map_payload(ghl, tables, expected_location_id=loc)
    c = r["canonical"]
    check("GHL: status mapped", r["status"] == "mapped")
    check("GHL: mode normalized", c.get("mode") == "interview_style_podcast")
    check("GHL: style normalized from radio label", c.get("style") == "counter_intuitive")
    check("GHL: contact_id from contact-container `id`", c.get("contact_id") == "CNT000000000000000wxyz")
    check("GHL: location_id from location.id", c.get("location_id") == loc)
    check("GHL: podcast_id via podbean alias", c.get("podcast_id") == "pb-99887766")
    check("GHL: q1 whitespace collapsed", c.get("q1_answer") == "Everyone optimizes for speed; I optimize for silence.")
    check("GHL: transport eventId not mapped", "eventId" not in c.values() and "evt-transient-123" in r["unknown_extras"].values())

    # Make.com shape: flat data container, camelCase, human enum forms. Vulnerable
    # has 2 real answer slots (E1: survey_answer_keys_by_style.vulnerable), so a
    # complete submission answers both q1 and q2.
    mk = {
        "data": {
            "mode": "Personal", "style": "vulnerable",
            "contactId": "CNTmakemakemake123456", "locationId": loc,
            "podcastId": "pb-55", "firstName": "Sam", "q1": "My failure taught me everything.",
            "q2": "Warm, unhurried, and direct.",
        }
    }
    r2 = map_payload(mk, tables, expected_location_id=loc)
    check("Make: status mapped", r2["status"] == "mapped")
    check("Make: mode Personal -> personal_podcast_style", r2["canonical"].get("mode") == "personal_podcast_style")
    check("Make: fuzzy contactId -> contact_id", r2["canonical"].get("contact_id") == "CNTmakemakemake123456")

    # n8n shape: nested body container, snake and dash mixed. Provocative has 3 real
    # answer slots (E1: survey_answer_keys_by_style.provocative); the transparency
    # answer (podcast_interview_smiq) covers only the LAST slot (q3_answer) via the
    # required_missing() fallback, so a complete submission still answers q2 directly.
    n8 = {
        "body": {
            "Production-Mode": "interview", "writing_style": "Provocative",
            "contact_id": "CNTn8nn8nn8nn8n000001", "location_id": loc,
            "podcast_id": "pb-1", "first_name": "Lee", "show_name": "Edges",
            "host_name": "Lee", "answer_1": "Comfort is the enemy.",
            "answer_2": "The evidence that overturns it.",
            "podcast_interview_smiq": "Transparent about sponsorship.",
        }
    }
    r3 = map_payload(n8, tables, expected_location_id=loc)
    check("n8n: fuzzy Production-Mode -> interview", r3["canonical"].get("mode") == "interview_style_podcast")
    check("n8n: style Provocative", r3["canonical"].get("style") == "provocative")
    check("n8n: status mapped (interview extras present)", r3["status"] == "mapped")

    # Tenant mismatch: correct shape, wrong location
    r4 = map_payload(mk, tables, expected_location_id="SOMEOTHERTENANTID99999")
    check("tenant mismatch quarantined", r4["status"] == "tenant_mismatch")

    # Missing required style -> needs_input, names the field
    bad = {"data": {"mode": "Personal", "contactId": "CNTaaaaaaaaaaaaaaaaa1",
                    "locationId": loc, "podcastId": "pb-2", "firstName": "Ann",
                    "q1": "x"}}
    r5 = map_payload(bad, tables, expected_location_id=loc)
    check("missing style -> needs_input", r5["status"] == "needs_input" and "style" in r5["missing"])

    # Interview mode missing host_name/show_name -> needs_input
    inc = {"data": {"mode": "Interview", "style": "passionate",
                    "contactId": "CNTbbbbbbbbbbbbbbbbb2", "locationId": loc,
                    "podcastId": "pb-3", "firstName": "Ivy", "q1": "y",
                    "podcast_interview_smiq": "z"}}
    r6 = map_payload(inc, tables, expected_location_id=loc)
    check("interview missing show/host -> needs_input", r6["status"] == "needs_input"
          and "show_name" in r6["missing"] and "host_name" in r6["missing"])

    # Email in an id field is rejected by value-shape validation (dropped -> missing)
    spoof = {"data": {"mode": "Personal", "style": "vulnerable",
                      "contactId": "attacker@evil.example", "locationId": loc,
                      "podcastId": "pb-4", "firstName": "Ed", "q1": "q"}}
    r7 = map_payload(spoof, tables, expected_location_id=loc)
    check("email-shaped contact_id rejected -> needs_input", r7["status"] == "needs_input"
          and "contact_id" in r7["missing"])

    # _test coercion to bool
    tflag = dict(mk["data"]); tflag["_test"] = "true"
    r8 = map_payload({"data": tflag}, tables, expected_location_id=loc)
    check("_test coerced to bool true", r8["canonical"].get("_test") is True)

    # CLI safe verdict redacts every PII VALUE (location_id, answer text, unknown
    # extras) while still reporting field NAMES for debugging.
    leaky = map_payload(ghl, tables, expected_location_id=loc)
    safe = safe_map_verdict(leaky)
    blob = json.dumps(safe)
    check("safe verdict keeps field names", "location_id" in safe["mapped_fields"]
          and "transparency_answer" in safe["mapped_fields"])
    check("safe verdict hides location_id value", loc not in blob)
    check("safe verdict hides answer PII", "optimizes for silence" not in blob
          and "disclose the AI assist" not in blob)
    check("safe verdict hides unknown-extra values", "evt-transient-123" not in blob)
    check("safe verdict exposes no canonical values key", "canonical" not in safe and "raw" not in safe)

    # E1: survey_answer_keys_by_style ships filled with the REAL legacy GHL survey
    # field keys (PODCAST-SNAPSHOT-BUILD-MANIFEST.md Section A Group 2), one entry
    # per style, in the exact positional order the required-field gate expects
    # (the Nth key corresponds to q<N>_answer). Pin the exact lists so a future
    # accidental edit (typo, dropped key, wrong order) fails loudly.
    survey_keys = tables.get("survey_answer_keys_by_style", {})
    check("E1: counter_intuitive keys", survey_keys.get("counter_intuitive")
          == ["podcast_survey__barry_q1", "podcast_survey__barry_q6"])
    check("E1: vulnerable keys", survey_keys.get("vulnerable")
          == ["podcast_survey__brene_q1", "podcast_survey__brene_q6"])
    check("E1: provocative keys", survey_keys.get("provocative")
          == ["podcast_survey__dan_q1", "podcast_survey__dan_q2", "podcast_survey__dan_q7"])
    check("E1: passionate keys", survey_keys.get("passionate")
          == ["podcast_survey__jia_q1", "podcast_survey__jia_q6", "podcast_survey__jia_q7"])

    # E1: required_missing() sizes the required-slot gate from len(survey_answer_
    # keys_by_style[style]) (mapper.py step 6). Counter Intuitive has 2 real answer
    # slots, so a submission with only q1 answered must still be needs_input naming
    # q2_answer; Provocative has 3, so q1+q2 alone must still name q3_answer missing.
    ci_partial = {"data": {"mode": "Personal", "style": "counter_intuitive",
                           "contactId": "CNTe1e1e1e1e1e1e1e1e1e1", "locationId": loc,
                           "podcastId": "pb-e1-1", "firstName": "Robin",
                           "q1": "Thesis answer for the E1 self-test."}}
    r9 = map_payload(ci_partial, tables, expected_location_id=loc)
    check("E1: CI 1-of-2 slots -> needs_input naming q2_answer",
          r9["status"] == "needs_input" and "q2_answer" in r9["missing"]
          and "q1_answer" not in r9["missing"])

    ci_full = dict(ci_partial["data"]); ci_full["q2"] = "Tone answer for the E1 self-test."
    r10 = map_payload({"data": ci_full}, tables, expected_location_id=loc)
    check("E1: CI 2-of-2 slots -> mapped", r10["status"] == "mapped")

    pro_partial = {"data": {"mode": "Personal", "style": "provocative",
                            "contactId": "CNTe1e1e1e1e1e1e1e1e1e2", "locationId": loc,
                            "podcastId": "pb-e1-2", "firstName": "Sam",
                            "q1": "Popular assumption on trial.", "q2": "Overturning evidence."}}
    r11 = map_payload(pro_partial, tables, expected_location_id=loc)
    check("E1: Provocative 2-of-3 slots -> needs_input naming q3_answer",
          r11["status"] == "needs_input" and "q3_answer" in r11["missing"])

    # The existing last-slot transparency fallback (required_missing, step 6) still
    # covers Provocative's 3rd slot when the SMIQ transparency answer is present.
    pro_partial_smiq = dict(pro_partial["data"])
    pro_partial_smiq["podcast_interview_smiq"] = "Transparent about the methodology."
    r12 = map_payload({"data": pro_partial_smiq}, tables, expected_location_id=loc)
    check("E1: Provocative 2-of-3 slots + transparency -> mapped (last-slot fallback)",
          r12["status"] == "mapped")

    print("== mapper self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
