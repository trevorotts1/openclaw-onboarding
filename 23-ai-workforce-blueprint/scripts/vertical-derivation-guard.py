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

RETROACTIVE-RECLASSIFICATION GRANDFATHERING (naming map
`universal_primary_history`)
A department can STOP being a universal primary. When it does, every client
provisioned while it WAS one is holding it legitimately — it was floor, not a
vertical, on the day it landed. Judging that provisioning by today's
classification is not a violation detection, it is a clock error, and it is
install-blocking (run-full-install.sh phase=3b treats rc=3 as fail_install).
The concrete case: commit b3e25876 (v14.28.1, 2026-06-28) removed
"universal_primary": true from real-estate/`listings`. BEFORE it,
apply_vertical_packs PHASE 1 looped over EVERY pack and added that pack's
primary UNCONDITIONALLY, never consulting _detect_vertical_packs — so every
client built in that era received `listings` regardless of industry. The fix
was forward-only; no fleet remediation ever ran.

So a provisioned vertical-specific department is GRANDFATHERED — reported, but
not a violation — when BOTH hold:
  1. CLASSIFICATION: the naming map's `universal_primary_history.demotions`
     carries a WELL-FORMED entry for that exact department id, naming the
     demoting commit and the UTC instant of the demotion. The entry is IGNORED
     unless it is complete, names a real vertical-pack department, and that
     department is NOT still universal_primary today.
  2. EVIDENCE: at least one WITNESS proves the department was already
     provisioned BEFORE that instant — see provisioning_witnesses(). No
     witness -> NOT grandfathered -> still rc=3. Absence of evidence is never
     a grandfather.
It is REFUSED outright, whatever the witnesses say, when the build's own
verticalPacks record names the department in addedDepartments with an
appliedAt at/after the demotion — a direct record of a post-demotion add beats
circumstantial pre-dating.

WHY THIS CANNOT BECOME A BLANKET BYPASS
  - There is NO flag, env var, or CLI option that disables the check. The only
    lever is a per-department, dated, commit-attributed row in the naming map.
  - The row's claim is falsifiable against git: `department` must actually have
    carried universal_primary=true before `demoted_by_commit`.
  - A row grants nothing on its own — every box must still produce its own
    dated witness.
  - It cannot reach a department that was never a universal primary, so the
    real leak this guard exists to catch (a real-estate set landing on a
    coaching client: showings / open-house / closing-coordinator /
    local-market-intelligence / lead-generation) is untouched.
  - check_add() ignores the table completely: grandfathering never authorizes
    a NEW materialization, it only explains an OLD one.
  - Grandfathered departments are inventoried in the receipt and printed on
    EVERY run, PASS or FAIL. Downgrading a FATAL to silence would be the same
    disease as a checker that reports success without measuring reality; this
    downgrades FATAL to LOUD, which is a different thing.

USAGE
  python3 vertical-derivation-guard.py --departments-dir DIR [--build-state PATH]
      [--core-answers PATH] [--naming-map PATH] [--out PATH] [--json]
  python3 vertical-derivation-guard.py --check-add DEPT_ID
      [--declared pack1,pack2 | --build-state PATH | --core-answers PATH]
      [--naming-map PATH]

EXIT CODES (audit mode, mirrors department-floor.py's convention)
  0  PASS — provisioned vertical-specific departments subset declared verticals
         (a PASS may still carry grandfathered residue + warnings; both are
         printed and written to the receipt — 0 never means "nothing to see")
  3  FAIL — a provisioned vertical-specific department's pack was not declared
         and it is not evidenced pre-reclassification residue
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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
NAMING_MAP = SKILL_DIR / "department-naming-map.json"
RECEIPT_RELATIVE_PATH = Path("provisioning") / "vertical-derivation.json"

# Every field a universal_primary_history.demotions[] row MUST carry to be
# honored. A row missing any of these is IGNORED with a warning rather than
# treated as a wildcard — an incomplete row must never widen the grandfather.
DEMOTION_REQUIRED_FIELDS = ("department", "pack", "demoted_at", "demoted_by_commit")

# build-state fields that are UPPER BOUNDS on the moment a department was
# materialized: each one is written at or after the workforce build has already
# put the department in the client's set, so `field < demoted_at` PROVES the
# department predates the demotion. Fields that only LOWER-bound the build
# (interviewCompletedAt, buildStartedAt, buildKickRequestedAt) are deliberately
# NOT here — the interview finishing before a demotion says nothing about when
# the departments landed, and using them would grandfather post-demotion adds.
PROVISIONING_UPPER_BOUND_FIELDS = (
    # written when every department is done (build-state-schema.json: "the
    # build-completion timestamp ... the moment every department is done")
    "buildCompletedAt",
    # ZHC closeout only starts/finishes after the build has produced the depts
    "closeoutStartedAt",
    "closeoutCompletedAt",
    # Command Center install materializes department folders in its phase 3,
    # so its completion bounds their existence
    "commandCenterCompletedAt",
)


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


def _parse_iso(value):
    """Parse an ISO-8601 timestamp into an AWARE UTC datetime, or None.

    build-state timestamps in the wild are a mix of 'Z', '+00:00', '-04:00'
    and bare naive strings (build-workforce.py writes datetime.now().isoformat(),
    which is naive local time). A naive value is read as UTC — the conservative
    reading for a witness, since treating a local timestamp as UTC can only
    move it EARLIER relative to a UTC cutoff for west-of-UTC boxes... which
    would be the permissive direction, so we additionally never accept a
    witness that lands within WITNESS_SAFETY_MARGIN of the cutoff.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# A witness must predate the demotion by more than this, so that timezone
# ambiguity in a naive build-state timestamp (max ±14h in the real world)
# can never be what turns a violation into a grandfather.
WITNESS_SAFETY_MARGIN_SECONDS = 14 * 3600


def universal_primary_demotions(naming_map, dept_idx=None):
    """
    Parse the naming map's `universal_primary_history.demotions` into
    {dept_id: row}, returning (table, warnings).

    A row is honored ONLY if it is complete and internally consistent. Every
    rejection is a warning, never a silent drop — a malformed grandfather row
    is exactly the kind of thing that must not quietly widen a gate.
    """
    warnings = []
    hist = (naming_map or {}).get("universal_primary_history") or {}
    rows = hist.get("demotions") if isinstance(hist, dict) else None
    if rows is None:
        return {}, warnings
    if not isinstance(rows, list):
        warnings.append(
            "DEMOTION_TABLE_MALFORMED: universal_primary_history.demotions is "
            f"{type(rows).__name__}, expected a list — NO department is grandfathered."
        )
        return {}, warnings

    idx = dept_idx if dept_idx is not None else dept_pack_index(naming_map)
    table = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            warnings.append(f"DEMOTION_ROW_IGNORED[{i}]: not an object — ignored.")
            continue
        missing = [f for f in DEMOTION_REQUIRED_FIELDS if not str(row.get(f) or "").strip()]
        if missing:
            warnings.append(
                f"DEMOTION_ROW_IGNORED[{i}]: missing required field(s) {missing} — ignored "
                "(an incomplete row is never a wildcard)."
            )
            continue
        did = str(row["department"]).strip()
        if did in ("*", "all", "ALL") or "*" in did:
            warnings.append(
                f"DEMOTION_ROW_IGNORED[{i}]: department '{did}' looks like a wildcard — "
                "ignored (this table is per-department by design)."
            )
            continue
        meta = idx.get(did)
        if meta is None:
            warnings.append(
                f"DEMOTION_ROW_IGNORED[{i}]: department '{did}' is not declared by any "
                "vertical pack — ignored (nothing to grandfather)."
            )
            continue
        if meta["universal_primary"]:
            warnings.append(
                f"DEMOTION_ROW_IGNORED[{i}]: department '{did}' is STILL universal_primary "
                "today — ignored (it is already excluded from this gate; the row is stale)."
            )
            continue
        when = _parse_iso(row["demoted_at"])
        if when is None:
            warnings.append(
                f"DEMOTION_ROW_IGNORED[{i}]: demoted_at '{row['demoted_at']}' is not a "
                "parseable ISO-8601 timestamp — ignored."
            )
            continue
        table[did] = dict(row, _demoted_at_dt=when)
    return table, warnings


def _dir_birth_time(path):
    """
    Creation ("birth") time of a directory as a UTC datetime, or None.

    A birth time EARLIER than a cutoff is proof the directory existed before
    it — a filesystem fact, not a self-report. A birth time LATER than the
    cutoff proves nothing at all: department folders are re-scaffolded wholesale
    by fleet refreshes (measured 2026-07-21: three boxes carry 36/36 department
    dirs sharing one birth date), so a late birth is used as evidence of
    NOTHING and never disqualifies.

    Python exposes st_birthtime on macOS/BSD but not on Linux, where the guard
    runs inside the client container. GNU coreutils `stat -c %W` does expose
    it there (ext4/xfs/overlayfs store a creation time), so that is the
    fallback: read-only, hard 5s cap, and every failure mode degrades to
    "no filesystem witness".
    """
    try:
        st = os.stat(path)
    except OSError:
        return None
    bt = getattr(st, "st_birthtime", None)
    if bt:
        return datetime.fromtimestamp(float(bt), timezone.utc)
    try:
        proc = subprocess.run(["stat", "-c", "%W", str(path)],
                              capture_output=True, text=True, timeout=5)
        raw = (proc.stdout or "").strip()
        secs = int(raw)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if secs <= 0:  # 0 or '-' means the filesystem has no creation time
        return None
    return datetime.fromtimestamp(float(secs), timezone.utc)


def provisioning_witnesses(dept_id, dept_dirname, departments_dir, build_state, dir_birth_times=None):
    """
    Every admissible piece of evidence for "this department was already
    provisioned by time T", newest-first irrelevant — the caller wants any
    witness that predates a cutoff.

    Each witness is {source, value (ISO), strength}:
      direct      — the build's OWN verticalPacks record names this department
                    in addedDepartments, and appliedAt says when that run
                    happened. The tightest evidence available.
      filesystem  — the department directory's creation time.
      build-window— a build-lifecycle timestamp that is an upper bound on the
                    materialization of the client's whole department set
                    (PROVISIONING_UPPER_BOUND_FIELDS). Box-level, not
                    department-level: it bounds when the SET existed, so it is
                    the weakest of the three and is labelled as such in the
                    receipt so cleanup can be prioritized by evidence quality.
    """
    out = []
    bs = build_state if isinstance(build_state, dict) else {}
    vp = bs.get("verticalPacks")
    if isinstance(vp, dict):
        applied = _parse_iso(vp.get("appliedAt"))
        added_ids = {e.get("id") for e in (vp.get("addedDepartments") or [])
                     if isinstance(e, dict)}
        if applied is not None and dept_id in added_ids:
            out.append({"source": "build-state.verticalPacks.appliedAt "
                                  "(record names this department in addedDepartments)",
                        "value": applied.isoformat(), "strength": "direct", "_dt": applied})

    birth = None
    if dir_birth_times is not None:
        raw = dir_birth_times.get(dept_dirname)
        if raw:
            birth = datetime.fromtimestamp(float(raw), timezone.utc)
    elif departments_dir is not None:
        birth = _dir_birth_time(Path(departments_dir) / dept_dirname)
    if birth is not None:
        out.append({"source": f"filesystem birth time of departments/{dept_dirname}",
                    "value": birth.isoformat(), "strength": "filesystem", "_dt": birth})

    for field in PROVISIONING_UPPER_BOUND_FIELDS:
        dt = _parse_iso(bs.get(field))
        if dt is not None:
            out.append({"source": f"build-state.{field}", "value": dt.isoformat(),
                        "strength": "build-window", "_dt": dt})
    return out


def grandfather_ruling(provisioned_entry, demotion, build_state, departments_dir, dir_birth_times=None):
    """
    Decide whether one provisioned vertical-specific department is
    pre-reclassification residue. Returns (ruling_dict_or_None, refusal_reason_or_None).

    A ruling is only ever produced for a department the demotion table already
    covers; this function's whole job is the EVIDENCE half.
    """
    dept_id = provisioned_entry["id"]
    cutoff = demotion["_demoted_at_dt"]

    # DISQUALIFIER (beats every witness): the build's own record says THIS
    # department was added by a run that happened at/after the demotion.
    bs = build_state if isinstance(build_state, dict) else {}
    vp = bs.get("verticalPacks")
    if isinstance(vp, dict):
        applied = _parse_iso(vp.get("appliedAt"))
        added_ids = {e.get("id") for e in (vp.get("addedDepartments") or [])
                     if isinstance(e, dict)}
        if applied is not None and dept_id in added_ids and applied >= cutoff:
            return None, (
                f"POST_DEMOTION_ADD: build-state.verticalPacks records '{dept_id}' as added "
                f"by a run at {applied.isoformat()}, at/after '{dept_id}' stopped being a "
                f"universal primary ({cutoff.isoformat()}, commit "
                f"{demotion['demoted_by_commit'][:8]}) — not pre-reclassification residue."
            )

    witnesses = provisioning_witnesses(dept_id, provisioned_entry["dir"], departments_dir,
                                       build_state, dir_birth_times)
    qualifying = [w for w in witnesses
                  if (cutoff - w["_dt"]).total_seconds() > WITNESS_SAFETY_MARGIN_SECONDS]
    if not qualifying:
        return None, (
            f"NO_PRE_RECLASSIFICATION_WITNESS: '{dept_id}' stopped being a universal primary at "
            f"{cutoff.isoformat()} (commit {demotion['demoted_by_commit'][:8]}), but this box "
            f"offers no evidence it was provisioned before then "
            f"({len(witnesses)} timestamp(s) examined, none clearing the cutoff) — absence of "
            f"evidence is never a grandfather."
        )

    strength_rank = {"direct": 0, "filesystem": 1, "build-window": 2}
    best = min(qualifying, key=lambda w: (strength_rank.get(w["strength"], 9), w["_dt"]))
    return {
        "id": dept_id,
        "pack": provisioned_entry["pack"],
        "packs": sorted(provisioned_entry.get("packs") or [provisioned_entry["pack"]]),
        "dir": provisioned_entry["dir"],
        "demotedAt": cutoff.isoformat(),
        "demotedByCommit": demotion["demoted_by_commit"],
        "demotedInVersion": demotion.get("demoted_in_version", ""),
        "witness": {k: v for k, v in best.items() if not k.startswith("_")},
        "allWitnesses": [{k: v for k, v in w.items() if not k.startswith("_")} for w in qualifying],
        "status": "GRANDFATHERED_PRE_RECLASSIFICATION",
        "cleanup": demotion.get("cleanup", "OPEN — owner decision; this guard never removes a department."),
        "reason": (
            f"GRANDFATHERED_PRE_RECLASSIFICATION: '{dept_id}' was an explicitly-flagged "
            f"universal primary (shipped to EVERY client regardless of industry) until "
            f"{cutoff.isoformat()}, commit {demotion['demoted_by_commit'][:8]}"
            f"{(' / ' + demotion['demoted_in_version']) if demotion.get('demoted_in_version') else ''}. "
            f"This box evidences provisioning before that: {best['source']} = {best['value']} "
            f"({best['strength']}). Legitimate when it landed; RESIDUE now — reported, not fatal, "
            f"never auto-removed."
        ),
    }, None


def evaluate_vertical_derivation(departments_dir=None, build_state=None, core_answers=None,
                                 naming_map=None, dir_birth_times=None):
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

    warnings = []
    demotions, demotion_warnings = universal_primary_demotions(nm, dept_idx)
    warnings.extend(demotion_warnings)

    declared_from_state, state_source = declared_packs_from_build_state(build_state or {})
    if declared_from_state is not None:
        declared = declared_from_state
        declared_source = state_source
    elif core_answers is not None:
        declared = declared_packs_from_core_answers(core_answers, nm)
        declared_source = "core-answers (re-derived; no build-state verticalPacks record)"
        warnings.append(
            "NO_DECLARATION_RECORD: build-state carries no verticalPacks.detectedPacks "
            "record; the declared set was RE-DERIVED from core_answers. The build's own "
            "audit record is missing and should be restored."
        )
    else:
        # FAIL CLOSED: no record and no core_answers supplied -> the declared
        # set is EMPTY. Mirrors shared-utils/industry-gate.sh: absence of
        # information is never permission. Any vertical-specific department
        # present on disk is then a violation (unexplained provenance).
        declared = {}
        declared_source = "none (fail-closed empty — no build-state record, no core_answers)"
        warnings.append(
            "NO_DECLARATION_RECORD: build-state carries no verticalPacks.detectedPacks "
            "record and no core_answers were supplied, so the DECLARED set is fail-closed "
            "EMPTY — every vertical-specific department on disk is unexplained unless it is "
            "evidenced pre-reclassification residue. This box's declaration record is "
            "MISSING and must be restored; it is not a pass."
        )

    provisioned = provisioned_vertical_departments(dd, dept_idx)
    violations = []
    grandfathered = []
    for p in provisioned:
        # A department declared by SEVERAL packs is explained as soon as ANY of
        # its owning packs is declared — see dept_pack_index()'s docstring.
        owning = p.get("packs") or [p["pack"]]
        if set(owning) & set(declared.keys()):
            continue

        # Undeclared. Before calling it a violation, ask whether it was FLOOR —
        # not a vertical — on the day it was provisioned. Only departments the
        # dated demotion table covers can even be asked, and each must produce
        # its own evidence. See the module docstring.
        demotion = demotions.get(p["id"])
        if demotion is not None:
            ruling, refusal = grandfather_ruling(p, demotion, build_state, dd, dir_birth_times)
            if ruling is not None:
                grandfathered.append(ruling)
                continue
            grandfather_note = f" GRANDFATHER REFUSED — {refusal}"
        else:
            grandfather_note = ""

        owner_desc = f"pack '{p['pack']}'" if len(owning) == 1 else f"packs {sorted(owning)}"
        violations.append({
            "id": p["id"],
            "pack": p["pack"],
            "packs": sorted(owning),
            "reason": (
                f"VERTICAL_NOT_DECLARED: department '{p['id']}' ({owner_desc}) is "
                f"provisioned on disk but none of {sorted(owning)} is in the declared set "
                f"({sorted(declared.keys()) or ['none']}) — source: {declared_source}"
                f"{grandfather_note}"
            ),
        })

    if grandfathered:
        warnings.append(
            "GRANDFATHERED_RESIDUE: {n} department(s) [{ids}] are on disk from BEFORE they "
            "were reclassified as industry-gated. They were the universal floor when they "
            "landed, so they are not force-adds and do not fail this install — but they ARE "
            "residue. This guard never removes a department; cleanup is a separate owner "
            "decision and can be driven from this receipt.".format(
                n=len(grandfathered), ids=", ".join(sorted(g["id"] for g in grandfathered)))
        )

    verdict = "FAIL" if violations else "PASS"
    return {
        "rc": 3 if violations else 0,
        "departmentsDir": str(dd),
        "declaredSource": declared_source,
        "declaredVerticals": [{"pack": k, "matchedKeywords": v} for k, v in sorted(declared.items())],
        "provisionedVerticalDepartments": provisioned,
        "violations": violations,
        "grandfatheredDepartments": grandfathered,
        "warnings": warnings,
        "residueSummary": {
            "grandfatheredCount": len(grandfathered),
            "grandfatheredIds": sorted(g["id"] for g in grandfathered),
            "byWitnessStrength": {
                s: sorted(g["id"] for g in grandfathered if g["witness"]["strength"] == s)
                for s in ("direct", "filesystem", "build-window")
                if any(g["witness"]["strength"] == s for g in grandfathered)
            },
            "declarationRecordPresent": declared_from_state is not None,
            "cleanupOwner": "OWNER DECISION — this guard never removes a department.",
        },
        "verdict": verdict,
        "reason": (
            (
                "provisioned ⊆ declared for every vertical-specific department"
                if not grandfathered else
                "provisioned ⊆ declared for every vertical-specific department, EXCEPT "
                + str(len(grandfathered)) + " grandfathered pre-reclassification residue "
                "department(s) [" + ", ".join(sorted(g["id"] for g in grandfathered))
                + "] — reported, not fatal, NOT cleaned up"
            )
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
        "grandfatheredDepartments": [],
        "warnings": [],
        "residueSummary": {
            "grandfatheredCount": 0,
            "grandfatheredIds": [],
            "byWitnessStrength": {},
            "declarationRecordPresent": False,
            "cleanupOwner": "OWNER DECISION — this guard never removes a department.",
        },
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

    DELIBERATELY IGNORES universal_primary_history. Grandfathering explains a
    department that is ALREADY on disk from a previous classification era; it
    is not a licence to materialize one TODAY. A department demoted out of the
    universal floor is industry-gated from the demotion onward, so adding it
    now still requires a declaration. Wiring the demotion table in here is how
    an evidence-based grandfather would quietly become a blanket bypass, so it
    is not wired in — asserted by test-vertical-derivation-guard.sh case (i5).
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
    # Residue and warnings print on EVERY run, PASS included — a clean rc must
    # never be the reason an operator stops seeing what is actually on disk.
    for g in verdict.get("grandfatheredDepartments") or []:
        print(f"GRANDFATHERED RESIDUE: {g['reason']}", file=sys.stderr)
        print(f"    cleanup: {g['cleanup']}", file=sys.stderr)
    for w in verdict.get("warnings") or []:
        print(f"WARNING: {w}", file=sys.stderr)
    if verdict["violations"]:
        for v in verdict["violations"]:
            print(f"VIOLATION: {v['reason']}", file=sys.stderr)
    summary = verdict.get("residueSummary") or {}
    if summary.get("grandfatheredCount"):
        print(f"RESIDUE INVENTORY: {summary['grandfatheredCount']} grandfathered "
              f"{summary['grandfatheredIds']} by witness strength "
              f"{summary.get('byWitnessStrength')}", file=sys.stderr)
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
