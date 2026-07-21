#!/usr/bin/env python3
"""
vertical-derivation-guard.py — U107 (E5-2; closes G2a): a vertical is NEVER
force-added to a client who is not that vertical.

WHY THIS EXISTS
The interview->provisioning gate itself (interviewComplete, corroborated by
qc-interview-completion.py) is VERIFIED — it correctly blocks REAL workforce
materialization until the AI Workforce interview is done
(32-command-center-setup/PREREQS.json:21-31, run-full-install.sh v12.9.27).
What the interview gate does NOT prove is a NARROWER invariant an operator
reported (UNVERIFIED from primary source before this unit; reproduced here,
not assumed): that once provisioning DOES run, the vertical-specific
department set it materializes is STRICTLY a function of what the interview
declared — e.g. a real-estate department set never lands on a client whose
interview never said real estate.

build-workforce.py's apply_vertical_packs() already gates Phase-2 keyword
extras on _detect_vertical_packs(core_answers, ...) matching, and writes an
auditable `verticalPacks` block into build-state — but that record is
self-reported by the SAME process that did the adding, and nothing
independently re-derives "declared" from "provisioned" and asserts
containment, nor refuses an out-of-band add. This module is that independent
check + refusal primitive, in the same "trust disk, not the JSON's own
self-report" spirit as department-floor.py (see that file's header for the
department-floor bug this mirrors).

TWO PRIMITIVES
  1. evaluate_vertical_derivation() — AUDIT: compare the vertical-specific
     departments actually PROVISIONED (on disk) against the verticals
     DECLARED (preferably build-state's verticalPacks.detectedPacks record;
     falls back to re-deriving from core_answers when no such record exists).
     Asserts provisioned (subset) declared for every vertical-specific
     department (universal-primary departments are excluded by design — see
     department-naming-map.json's universal_primary flag / department-floor.
     universal_primary_vertical_departments(): those ship to EVERY client
     regardless of industry, so they are never declaration-gated). Writes an
     auditable receipt.
  2. check_add() — REFUSAL: given a proposed department id and the currently
     declared pack set, decide allowed/refused BEFORE materialization, with a
     named error. Callable by any provisioning code path that is about to
     scaffold a vertical-pack department (defense in depth alongside
     apply_vertical_packs' own Phase-2 gate).

KEYWORD-MATCH LOCKSTEP: declared_packs_from_core_answers() intentionally
duplicates the SAME word-boundary/substring keyword-match algorithm as
build-workforce._detect_vertical_packs() / department-floor.
matched_vertical_pack_departments() — the codebase already carries two such
copies (build-workforce.py and department-floor.py); this is a third,
independent by design (an independent auditor sharing the auditee's own
implementation would not catch a bug in that implementation). Cross-checked
for drift by test-vertical-derivation-guard.sh's lockstep assertions.

FAIL CLOSED: no build-state verticalPacks record AND no core_answers supplied
-> declared set is treated as EMPTY (mirrors shared-utils/industry-gate.sh's
"absence of information is never permission to install" doctrine). Any
vertical-specific department found on disk under that condition is a
violation with unexplained provenance.

USAGE
  python3 vertical-derivation-guard.py --departments-dir DIR [--build-state PATH]
      [--core-answers PATH] [--naming-map PATH] [--out PATH] [--json]
  python3 vertical-derivation-guard.py --check-add DEPT_ID
      [--declared pack1,pack2 | --build-state PATH | --core-answers PATH]
      [--naming-map PATH]

EXIT CODES (audit mode, mirrors department-floor.py's convention)
  0  PASS — provisioned vertical-specific departments subset declared verticals
  3  FAIL — a provisioned vertical-specific department's pack was not declared
  7  cannot resolve a departments dir

EXIT CODES (--check-add mode)
  0  allowed
  1  refused (VERTICAL_NOT_DECLARED, named error printed to stderr)

Read-only against departments-dir (never creates/deletes a department). The
only write is the receipt file (--out, or the default
<departments_dir>/../provisioning/vertical-derivation.json).
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
NAMING_MAP = SKILL_DIR / "department-naming-map.json"
RECEIPT_RELATIVE_PATH = Path("provisioning") / "vertical-derivation.json"


def load_naming_map(path=None):
    p = Path(path) if path else NAMING_MAP
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def dept_pack_index(nm):
    """dept_id -> {"pack": first_pack_id, "packs": [all_pack_ids],
    "universal_primary": bool} for every department declared inside any
    vertical_packs[*].auto_add_departments.

    A department id MAY be declared by MORE THAN ONE pack (the naming map
    really does this: `community-management` is declared by both
    personal-pro-dev and content-creator; `podcast` by both personal-pro-dev
    and content-creator). An earlier version of this index kept only the LAST
    declaring pack, which made attribution depend on naming-map key order and
    produced install-blocking FALSE FAILS: a personal-pro-dev client whose
    interview legitimately declared personal-pro-dev, provisioned
    `community-management` as a Phase-2 extra from THAT pack, was reported as
    a content-creator violation because content-creator happens to be
    declared later in the map.

    So `packs` carries EVERY declaring pack, and the ownership questions are
    answered set-wise:
      - allowed  <=> ANY owning pack is declared (mirrors build-workforce
        apply_vertical_packs Phase 2, which adds the dept from whichever
        matched pack declares it);
      - universal_primary <=> ANY owning pack flags it universal_primary
        (mirrors Phase 1, which adds it to EVERY client from the flagging
        pack — so it is genuinely floor, not a vertical, once any pack
        flags it).
    `pack` is retained as the FIRST declaring pack for receipt/back-compat
    readability; correctness decisions must use `packs`.
    """
    packs = nm.get("vertical_packs") or {}
    idx = {}
    for pack_id, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        for dept in pack.get("auto_add_departments", []) or []:
            if not isinstance(dept, dict):
                continue
            did = dept.get("id")
            if not did:
                continue
            entry = idx.get(did)
            if entry is None:
                idx[did] = {
                    "pack": pack_id,
                    "packs": [pack_id],
                    "universal_primary": bool(dept.get("universal_primary")),
                }
            else:
                if pack_id not in entry["packs"]:
                    entry["packs"].append(pack_id)
                # ANY declaring pack flagging it universal_primary makes it floor.
                entry["universal_primary"] = entry["universal_primary"] or bool(dept.get("universal_primary"))
    return idx


def declared_packs_from_core_answers(core_answers, nm):
    """
    Interview-derived-only vertical declaration (Phase-2 keyword match).
    MUST stay in lockstep with build-workforce._detect_vertical_packs() /
    department-floor.matched_vertical_pack_departments() — same haystack,
    same word-boundary/substring rule. See module docstring "KEYWORD-MATCH
    LOCKSTEP". Returns {pack_id: [matched_keywords]}.
    """
    packs = nm.get("vertical_packs") or {}
    haystack = " ".join([
        str((core_answers or {}).get("industry", "") or ""),
        str((core_answers or {}).get("company_description", "") or ""),
        str((core_answers or {}).get("biggest_challenge", "") or ""),
        str((core_answers or {}).get("tools", "") or ""),
    ]).lower()
    declared = {}
    for pack_id, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        hits = []
        for kw in pack.get("auto_add_keywords", []) or []:
            k = str(kw).strip().lower()
            if not k:
                continue
            if " " in k:
                if k in haystack:
                    hits.append(kw)
            elif re.search(r"\b" + re.escape(k) + r"\b", haystack):
                hits.append(kw)
        if hits:
            declared[pack_id] = hits
    return declared


def declared_packs_from_build_state(build_state):
    """
    Read the auditable verticalPacks.detectedPacks record build-workforce.py
    writes (apply_vertical_packs -> _write_vertical_pack_record). Returns
    (declared_dict_or_None, source_label). declared_dict is
    {pack_id: [matched_keywords]}. None means NO record exists at all —
    distinct from an EMPTY record (which means the build genuinely detected
    no vertical) — so the caller can decide how to fail-close.
    """
    vp = (build_state or {}).get("verticalPacks")
    if not isinstance(vp, dict):
        return None, "none"
    detected = vp.get("detectedPacks")
    if not isinstance(detected, list):
        return None, "none"
    out = {}
    for entry in detected:
        if isinstance(entry, dict) and entry.get("pack"):
            out[entry["pack"]] = entry.get("matchedKeywords", [])
    return out, "build-state.verticalPacks.detectedPacks"


def _slug_norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def departments_on_disk(departments_dir):
    names = []
    if not departments_dir:
        return names
    p = departments_dir if isinstance(departments_dir, Path) else Path(departments_dir)
    if not p.is_dir():
        return names
    for d in p.iterdir():
        if d.is_dir() and not d.name.startswith((".", "_")):
            names.append(d.name)
    return names


def provisioned_vertical_departments(departments_dir, dept_idx):
    """
    Vertical-SPECIFIC (non-universal-primary) departments actually present on
    disk, each mapped to its owning pack. Universal-primary departments are
    excluded BY DESIGN — they ship to every client regardless of industry
    (department-naming-map.json universal_primary flag), so they are never
    subject to the "declared before provisioned" invariant this guard checks.

    Folder-name matching is normalized (lowercase, non-alnum stripped) but,
    unlike department-floor.py's CANONICAL_VARIANT_SLUGS, does not carry a
    historical-alias table — vertical-pack departments are materialized
    directly under their department-naming-map.json `id`
    (build-workforce.apply_vertical_packs._add_dept), so no alias table
    exists for them yet. If a future alias table is added for vertical-pack
    ids, extend this function's normalization to match, in lockstep with
    build-workforce.py's folder-naming.
    """
    norm_idx = {_slug_norm(did): (did, meta) for did, meta in dept_idx.items()}
    out = []
    for name in departments_on_disk(departments_dir):
        hit = norm_idx.get(_slug_norm(name))
        if not hit:
            continue
        did, meta = hit
        if meta["universal_primary"]:
            continue
        out.append({"id": did, "dir": name, "pack": meta["pack"], "packs": list(meta["packs"])})
    return out


def evaluate_vertical_derivation(departments_dir=None, build_state=None, core_answers=None, naming_map=None):
    """
    Compare provisioned vertical-specific departments (disk truth) to
    declared verticals (build-state record, or re-derived from core_answers,
    or fail-closed empty). Returns a verdict dict — see module docstring for
    the exit-code contract (rc field).
    """
    nm = naming_map if naming_map is not None else load_naming_map()

    if departments_dir is None:
        return _no_departments_dir_verdict("no departments_dir supplied")
    dd = departments_dir if isinstance(departments_dir, Path) else Path(departments_dir)
    if not dd.is_dir():
        return _no_departments_dir_verdict(f"departments dir does not exist: {dd}")

    dept_idx = dept_pack_index(nm)

    declared_from_state, state_source = declared_packs_from_build_state(build_state or {})
    if declared_from_state is not None:
        declared = declared_from_state
        declared_source = state_source
    elif core_answers is not None:
        declared = declared_packs_from_core_answers(core_answers, nm)
        declared_source = "core-answers (re-derived; no build-state verticalPacks record)"
    else:
        # FAIL CLOSED: no record and no core_answers supplied -> the declared
        # set is EMPTY. Mirrors shared-utils/industry-gate.sh: absence of
        # information is never permission. Any vertical-specific department
        # present on disk is then a violation (unexplained provenance).
        declared = {}
        declared_source = "none (fail-closed empty — no build-state record, no core_answers)"

    provisioned = provisioned_vertical_departments(dd, dept_idx)
    violations = []
    for p in provisioned:
        # A department declared by SEVERAL packs is explained as soon as ANY of
        # its owning packs is declared — see dept_pack_index()'s docstring.
        owning = p.get("packs") or [p["pack"]]
        if not (set(owning) & set(declared.keys())):
            owner_desc = f"pack '{p['pack']}'" if len(owning) == 1 else f"packs {sorted(owning)}"
            violations.append({
                "id": p["id"],
                "pack": p["pack"],
                "packs": sorted(owning),
                "reason": (
                    f"VERTICAL_NOT_DECLARED: department '{p['id']}' ({owner_desc}) is "
                    f"provisioned on disk but none of {sorted(owning)} is in the declared set "
                    f"({sorted(declared.keys()) or ['none']}) — source: {declared_source}"
                ),
            })

    verdict = "FAIL" if violations else "PASS"
    return {
        "rc": 3 if violations else 0,
        "departmentsDir": str(dd),
        "declaredSource": declared_source,
        "declaredVerticals": [{"pack": k, "matchedKeywords": v} for k, v in sorted(declared.items())],
        "provisionedVerticalDepartments": provisioned,
        "violations": violations,
        "verdict": verdict,
        "reason": (
            "provisioned ⊆ declared for every vertical-specific department"
            if not violations else "; ".join(v["reason"] for v in violations)
        ),
    }


def _no_departments_dir_verdict(reason):
    return {
        "rc": 7,
        "departmentsDir": None,
        "declaredSource": "n/a",
        "declaredVerticals": [],
        "provisionedVerticalDepartments": [],
        "violations": [],
        "verdict": "UNKNOWN",
        "reason": reason,
    }


def check_add(dept_id, declared_packs, naming_map=None):
    """
    Refusal primitive (BINARY acceptance (c)): would adding `dept_id` be
    allowed given the currently declared pack set? A department that is not a
    vertical-pack department at all (canonical/mandatory/custom), or a
    universal-primary vertical department, is always allowed — this guard
    gates ONLY vertical-specific (non-universal-primary) pack departments.

    Returns (allowed: bool, error_or_None: str). The error string is a NAMED
    error ("VERTICAL_NOT_DECLARED: ...") so a caller/log/receipt can grep it
    reliably, per BINARY acceptance (c)'s "refused with a named error".
    """
    nm = naming_map if naming_map is not None else load_naming_map()
    dept_idx = dept_pack_index(nm)
    meta = dept_idx.get(dept_id)
    if meta is None or meta["universal_primary"]:
        return True, None
    declared_set = set(declared_packs or [])
    owning = meta.get("packs") or [meta["pack"]]
    # Allowed as soon as ANY owning pack is declared (multi-pack departments).
    if set(owning) & declared_set:
        return True, None
    owner_desc = (f"vertical pack '{owning[0]}'" if len(owning) == 1
                  else f"vertical packs {sorted(owning)}")
    return False, (
        f"VERTICAL_NOT_DECLARED: refusing to add department '{dept_id}' — it belongs to "
        f"{owner_desc}, which the interview did not declare "
        f"(declared packs: {sorted(declared_set) or ['none']})."
    )


def write_receipt(verdict, out_path):
    out = Path(out_path)
    receipt = dict(verdict)
    receipt["schemaVersion"] = "1.0"
    receipt["generatedAt"] = datetime.now(timezone.utc).isoformat()
    receipt["source"] = "vertical-derivation-guard.py evaluate_vertical_derivation (U107)"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(receipt, f, indent=2, sort_keys=True)
        return True
    except OSError as e:
        print(f"[VERTICAL-DERIVATION WARNING] could not write receipt to {out}: {e}", file=sys.stderr)
        return False


def _default_build_state():
    candidates = [
        "/data/.openclaw/workspace/.workforce-build-state.json",
        os.path.join(os.path.expanduser("~"), ".openclaw", "workspace", ".workforce-build-state.json"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p) as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                return {}
    return {}


def _load_json_arg(path):
    if not path:
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[VERTICAL-DERIVATION] could not read {path}: {e}", file=sys.stderr)
        return None


def _print_audit_human(verdict):
    print("============================================", file=sys.stderr)
    print("vertical-derivation-guard.py — U107 audit", file=sys.stderr)
    print(f"departments_dir = {verdict['departmentsDir']}", file=sys.stderr)
    print(f"declared source = {verdict['declaredSource']}", file=sys.stderr)
    print(f"declared verticals    = {[d['pack'] for d in verdict['declaredVerticals']] or ['none']}", file=sys.stderr)
    print(f"provisioned vertical-specific depts = "
          f"{[d['id'] for d in verdict['provisionedVerticalDepartments']] or ['none']}", file=sys.stderr)
    if verdict["violations"]:
        for v in verdict["violations"]:
            print(f"VIOLATION: {v['reason']}", file=sys.stderr)
    print(f"RESULT: {verdict['verdict']} (rc={verdict['rc']})", file=sys.stderr)


def main(argv):
    as_json = "--json" in argv

    def _arg(flag):
        for i, a in enumerate(argv):
            if a == flag and i + 1 < len(argv):
                return argv[i + 1]
        return None

    naming_map_path = _arg("--naming-map")
    nm = load_naming_map(naming_map_path) if naming_map_path else load_naming_map()

    if "--check-add" in argv:
        dept_id = _arg("--check-add")
        declared_arg = _arg("--declared")
        if declared_arg is not None:
            declared_packs = [p.strip() for p in declared_arg.split(",") if p.strip()]
        else:
            bs_path = _arg("--build-state")
            ca_path = _arg("--core-answers")
            bs = _load_json_arg(bs_path) if bs_path else _default_build_state()
            declared_from_state, _src = declared_packs_from_build_state(bs)
            if declared_from_state is not None:
                declared_packs = list(declared_from_state.keys())
            else:
                ca = _load_json_arg(ca_path) if ca_path else None
                declared_packs = list(declared_packs_from_core_answers(ca or {}, nm).keys()) if ca else []
        allowed, error = check_add(dept_id, declared_packs, naming_map=nm)
        if as_json:
            print(json.dumps({"deptId": dept_id, "declaredPacks": sorted(declared_packs),
                               "allowed": allowed, "error": error}, indent=2, sort_keys=True))
        else:
            if allowed:
                print(f"ALLOWED: '{dept_id}' may be added (declared packs: {sorted(declared_packs) or ['none']})",
                      file=sys.stderr)
            else:
                print(error, file=sys.stderr)
        return 0 if allowed else 1

    dd_arg = _arg("--departments-dir")
    dd = Path(dd_arg) if dd_arg else None
    bs_path = _arg("--build-state")
    bs = _load_json_arg(bs_path) if bs_path else _default_build_state()
    ca_path = _arg("--core-answers")
    ca = _load_json_arg(ca_path) if ca_path else None

    verdict = evaluate_vertical_derivation(departments_dir=dd, build_state=bs, core_answers=ca, naming_map=nm)

    out_arg = _arg("--out")
    if out_arg:
        write_receipt(verdict, out_arg)
    elif verdict["departmentsDir"]:
        write_receipt(verdict, Path(verdict["departmentsDir"]).parent / RECEIPT_RELATIVE_PATH)

    if as_json:
        print(json.dumps(verdict, indent=2, sort_keys=True))
    else:
        _print_audit_human(verdict)
    return verdict["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
