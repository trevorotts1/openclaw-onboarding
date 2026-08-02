#!/usr/bin/env python3
# =============================================================================
# SKILL 54 — ANTHOLOGY WRITER :: INTAKE GATE  (fail-closed, stdlib-only)
# -----------------------------------------------------------------------------
# Enforces PRD §3.3: the four fields the pipeline actually consumes must be
# present and non-empty BEFORE any tone/title/chapter is authored. Whitespace-
# only counts as missing. A self-attested "complete" flag is never trusted — we
# check the ledger's real values.
#
# It also enforces the credential rule (D7): a client's provider keys are
# resolved per box from the client's OWN OpenClaw config, never taken through
# intake. Any credential-shaped intake key fails closed.
#
#   AF-AW-INTAKE-MISSING    — any of anthology_title / first_name / last_name /
#                             chapter_premise missing, empty, or whitespace.
#   AF-AW-INTAKE-CREDENTIAL — an intake key looks like a secret (api_key, token,
#                             openrouter, password, ...). Keys never ride intake.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_aw_intake.py <intake.json> [--json] | prove_aw_intake.py --self-test
# =============================================================================
"""Fail-closed intake gate for the Anthology Writer (Skill 54)."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _aw_common as c  # noqa: E402

AF_INTAKE_MISSING = "AF-AW-INTAKE-MISSING"
AF_INTAKE_CREDENTIAL = "AF-AW-INTAKE-CREDENTIAL"
AF_INTAKE_TYPE = "AF-AW-INTAKE-TYPE"
_FIX = Path(__file__).resolve().parent.parent / "test-fixtures"
_INTAKE_SCHEMA = Path(__file__).resolve().parent.parent / "intake" / "aw-intake-schema.json"


def _load_intake_schema():
    """Load aw-intake-schema.json for field-type enforcement. Returns None on any
    load/parse failure (never sys.exit — a missing/broken schema must not block
    the other gate checks; type checking is one layer, not the whole gate)."""
    try:
        return json.loads(_INTAKE_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _allowed_types(prop_schema):
    """Return the set of Python types allowed for a property schema node (plain
    'type' or 'oneOf'/'anyOf' branches). 'string'->str, 'number'/'integer'->int/float,
    'boolean'->bool, 'array'->list, 'object'->dict."""
    if not isinstance(prop_schema, dict):
        return set()
    mapping = {"string": str, "number": [int, float], "integer": [int, float],
               "boolean": bool, "array": list, "object": dict}
    types = set()
    for key in ("oneOf", "anyOf"):
        branches = prop_schema.get(key)
        if isinstance(branches, list):
            for b in branches:
                t = (isinstance(b, dict) and b.get("type"))
                if isinstance(t, str):
                    mapped = mapping.get(t)
                    if mapped:
                        types.add(mapped) if isinstance(mapped, type) else types.update(mapped)
                    elif t in mapping:
                        m = mapping[t]
                        types.add(m) if isinstance(m, type) else types.update(m)
            if types:
                return types
    t = prop_schema.get("type")
    if isinstance(t, str):
        mapped = mapping.get(t)
        if mapped:
            if isinstance(mapped, type):
                return {mapped}
            return set(mapped)
    return set()


def _reject_nonstring(intake, schema, result):
    """Fail-closed: every intake field whose schema includes 'string' as an allowed
    type MUST hold a Python value that is one of the schema's declared types.
    For a pure string field this means isinstance(value, str). For a oneOf/anyOf
    string-or-array field (personal_stories) this means isinstance(value, (str, list)).

    str(False) = 'False' and str(0) = '0' (both non-empty) so the bare non-empty
    gate accepted those as valid; the schema type contract rejects them BEFORE they
    reach the pipeline."""
    props = schema.get("properties") or {} if isinstance(schema, dict) else {}
    for field, prop_schema in props.items():
        val = intake.get(field)
        if val is None:
            continue
        allowed = _allowed_types(prop_schema)
        if not allowed:
            continue
        if not any(isinstance(val, t) for t in allowed):
            result.fail(AF_INTAKE_TYPE,
                        "field %r expects %s in aw-intake-schema.json but received %s (%r)"
                        % (field, allowed_names(allowed), type(val).__name__, val))
    return result


def allowed_names(types_set):
    """Human-readable type names for error messages."""
    names = {str: "string", int: "integer", float: "number", bool: "boolean",
             list: "array", dict: "object"}
    return "/".join(sorted(names.get(t, t.__name__) for t in types_set))


def evaluate(intake: dict) -> c.Result:
    r = c.Result("prove_aw_intake")
    if not isinstance(intake, dict):
        r.fail(AF_INTAKE_MISSING, "intake is not a JSON object")
        return r
    for field in c.INTAKE_REQUIRED:
        val = intake.get(field)
        if val is None or not str(val).strip():
            r.fail(AF_INTAKE_MISSING, "required field %r is missing/empty/whitespace" % field)
    cred = c.credential_shaped_keys(intake)
    for k in cred:
        r.fail(AF_INTAKE_CREDENTIAL,
               "credential-shaped intake key %r is forbidden — client provider keys are "
               "resolved per box from the client's own config, never via intake" % k)
    schema = _load_intake_schema()
    if schema is not None:
        _reject_nonstring(intake, schema, r)
    if r.passed:
        r.note("all 4 required intake fields present: %s" % ", ".join(c.INTAKE_REQUIRED))
        stories = c.story_phrases(intake)
        r.note("personal_stories: %d real anchor(s) to place (N/A slots skipped)" % len(stories))
    return r


def prove(path, as_json=False) -> int:
    return evaluate(c.read_json(path)).emit(as_json)


def self_test() -> int:
    checks = []
    g = _FIX / "golden" / "intake.json"
    checks.append(("golden intake PASSes", evaluate(c.read_json(g)).passed))

    a = evaluate(c.read_json(_FIX / "attack" / "intake_missing.json"))
    checks.append(("missing-field intake AUTOFAILs", not a.passed))
    checks.append(("...with AF-AW-INTAKE-MISSING",
                   any(code == AF_INTAKE_MISSING for code, _ in a.violations)))

    cr = evaluate(c.read_json(_FIX / "attack" / "intake_credential.json"))
    checks.append(("credential-shaped intake AUTOFAILs", not cr.passed))
    checks.append(("...with AF-AW-INTAKE-CREDENTIAL",
                   any(code == AF_INTAKE_CREDENTIAL for code, _ in cr.violations)))

    # FIX-17: non-string values (bool/int/float/None) injected into a required
    # string-typed field must be rejected (AF-AW-INTAKE-TYPE), not pass as valid
    # because str(False)="False" and str(0)="0" are non-empty.
    _tt = _FIX / "attack"
    for fname, field, bad_val in [
        ("intake_bool_false.json", "personal_stories", "false"),
        ("intake_num_zero.json", "primary_goal", "0"),
        ("intake_num_42.json", "first_name", "42"),
    ]:
        fixture = _tt / fname
        obj = c.read_json(fixture)
        ev = evaluate(obj)
        checks.append(("non-string %s=%s rejected AF-AW-INTAKE-TYPE" % (field, bad_val),
                       not ev.passed and any(
                           code == AF_INTAKE_TYPE and field in msg
                           for code, msg in ev.violations)))
    return c.selftest_report("prove_aw_intake", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Anthology Writer intake gate (Skill 54).")
    ap.add_argument("path", nargs="?", help="intake.json to prove")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("a path is required (or use --self-test)")
    return prove(args.path, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
