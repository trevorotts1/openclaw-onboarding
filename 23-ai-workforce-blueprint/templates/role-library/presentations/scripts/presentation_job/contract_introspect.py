"""Derive, MECHANICALLY, the constraint set an agent-authored artifact is judged by.

WHY THIS MODULE EXISTS (the class defect, not the instance)
-----------------------------------------------------------
An agent phase is dispatched with ARTIFACT_CONTRACTS[phase] as its only
statement of "what a passing artifact looks like".  That text was hand-written.
The rules it is graded against live somewhere else entirely: phase_verifiers.py,
intelligence_engines_check.py, pitch_engines_check.py, build_deck.py's _chk_*
preflights, and PIPELINE-MANIFEST.json's gate_codes / autofails registry.

Nothing tied the two together.  So the author wrote BLIND against part of its own
rule set, and each missing rule was discovered ONE PAID RE-AUTHOR AT A TIME.
Measured, live, on run pres-wave-e-v3-1787240658 (2026-08-20), the P4-COPY copy
artifact and the phases that re-judge it burned SEVEN serial autofail discoveries
(AF-NO-FELT-STAKES, AF-NO-RECAP, AF-NO-VILLAIN, AF-NARRATIVE-HARMONY at P4-COPY;
AF-C8 at P1Q-COPY-QC; AF-SP-P3-PITCH / AF-SP-PRICE-IN-TEACH at P-SP-P3-HYGIENE).
There are 181 registered autofail codes.  Serial discovery cannot converge.

The fix is NOT "hand-copy the rules into the contract" -- a hand-copied list is
exactly what drifts.  The fix is to DERIVE the list from the code that judges,
every time the module is imported, and to have a test that goes RED the moment a
rule exists in the judging path but is absent from the contract's own prose.

WHAT IS DERIVED vs WHAT IS DECLARED
-----------------------------------
DERIVED (read out of files at import time, never re-typed here):
  * which checker functions sit on P4-COPY's verification path        (AST)
  * which autofail codes those checkers can emit                      (AST)
  * each code's own failure message / requirement text                (AST)
  * the phase's gate_codes and preflight checker names        (PIPELINE-MANIFEST)
  * every registered autofail whose own trigger text names the artifact
    this phase produces                                       (PIPELINE-MANIFEST)
  * the AF-C8 doctrine + its ARCHETYPE CARVE-OUT block  (MASTER-QC-AUTOFAIL-
    RULESET.md -- AF-C8 has NO mechanical Python check and is NOT in the
    autofails registry; the doctrine file is its only machine-readable home)

DECLARED (a short, auditable scoping judgement, stated once, here):
  * the SCOPE RULE below -- which rings of the judging graph belong in a
    P4-COPY author's contract.  This is a judgement, so it is written down
    where a reviewer can argue with it, instead of being smeared through a
    hand-copied list.

SCOPE RULE (why this is not a dump of all 181 codes)
----------------------------------------------------
A code belongs in P4-COPY's contract iff it is judged against the file P4-COPY
WRITES (working/copy/slides_copy.md), at P4-COPY's own gate or at any later
phase that re-reads that same file.  Four rings, each mechanically enumerable:

  RING 1  "verifier"   -- phase_verifiers.PHASE_VERIFIERS["P4-COPY"] and every
                          checker transitively reachable from it.
  RING 2  "preflight"  -- the manifest's P4-COPY preflight + additional_
                          preflights checkers, and its declared gate_codes.
  RING 3  "downstream" -- every phase that RE-JUDGES slides_copy.md after
                          P4-COPY produced it: enumerated as (a) the manifest
                          autofails whose own registry entry names
                          slides_copy.md, and (b) P1Q-COPY-QC's gate_codes
                          (that phase's whole job is grading this file).
  RING 4  "doctrine"   -- rules with no Python checker and no registry entry,
                          graded by a human/agent role reading the file.  Today
                          that is exactly AF-C8, sourced verbatim from
                          MASTER-QC-AUTOFAIL-RULESET.md.

EXCLUDED, deliberately: every code judged against a DIFFERENT artifact.  The two
AF-SP-* codes from the live run are the worked example -- build_deck._chk_sp_no_pitch
reads working/copy/sp_intake.json and working/copy/sp_structure.json, NOT
slides_copy.md, so they are P-SP-STRUCTURE's author's constraints, not P4-COPY's.
Putting them in P4-COPY's contract would tell the copywriter to fix a file it
does not write.  See phase_constraint_audit() for the whole-pipeline table.

This module NEVER loosens, disables or reinterprets a rule.  It only reads them.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

_THIS_FILE = Path(__file__).resolve()
SCRIPTS_DIR = _THIS_FILE.parent.parent  # presentation_job/ -> scripts/

# The artifact P4-COPY produces; the scope rule keys off it.
P4_COPY_ARTIFACT = "working/copy/slides_copy.md"

MANIFEST_REL_CANDIDATES: Tuple[str, ...] = (
    # 1. materialized department: <dept>/sops/PIPELINE-MANIFEST.json
    #    (identical resolution order to presentation_job.manifest.resolve_manifest
    #    candidate 2 -- the file the ENGINE actually runs against)
    "sops/PIPELINE-MANIFEST.json",
    # 2. repo / worktree: the canonical cluster copy, walked up to.
    "universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json",
)
RULESET_REL_CANDIDATES: Tuple[str, ...] = (
    "sops/MASTER-QC-AUTOFAIL-RULESET.md",
    "universal-sops/presentation-slide-craft/MASTER-QC-AUTOFAIL-RULESET.md",
)


class IntrospectionError(RuntimeError):
    """Raised when the judging path cannot be read.  NEVER swallowed silently by
    a caller that then pretends the rule set is empty -- an empty rule set is
    indistinguishable from 'no rules', which is the blindness this module kills."""


class Rule(NamedTuple):
    """One constraint the artifact is judged by.

    code        the autofail code, or "" for an un-coded preflight floor.
    requirement human-readable text, sourced from the checker's own failure
                message / docstring / the manifest's own trigger prose.
                NEVER authored here.
    source      file::symbol that the requirement text was read out of.
    ring        verifier | preflight | gate | downstream | doctrine
    """

    code: str
    requirement: str
    source: str
    ring: str


# ---------------------------------------------------------------------------
# File resolution
# ---------------------------------------------------------------------------

def _walk_up_for(rel_candidates: Sequence[str], start: Path, hops: int = 12) -> Path:
    # Candidate 1 is department-relative (scripts/../sops/...); try it first and
    # exactly once, mirroring resolve_manifest's "no walk-up for the dept copy".
    dept_first = (start.parent / rel_candidates[0])
    if dept_first.is_file():
        return dept_first.resolve()
    cur = start
    for _ in range(hops):
        for rel in rel_candidates:
            cand = cur / rel
            if cand.is_file():
                return cand.resolve()
        if cur.parent == cur:
            break
        cur = cur.parent
    raise IntrospectionError(
        "could not locate any of "
        + ", ".join(rel_candidates)
        + f" walking up from {start} (12 hops)"
    )


_FILE_CACHE: Dict[str, Path] = {}


def manifest_path() -> Path:
    if "manifest" not in _FILE_CACHE:
        _FILE_CACHE["manifest"] = _walk_up_for(MANIFEST_REL_CANDIDATES, SCRIPTS_DIR)
    return _FILE_CACHE["manifest"]


def ruleset_path() -> Path:
    if "ruleset" not in _FILE_CACHE:
        _FILE_CACHE["ruleset"] = _walk_up_for(RULESET_REL_CANDIDATES, SCRIPTS_DIR)
    return _FILE_CACHE["ruleset"]


_MANIFEST_CACHE: Dict[str, dict] = {}


def manifest() -> dict:
    if "m" not in _MANIFEST_CACHE:
        _MANIFEST_CACHE["m"] = json.loads(manifest_path().read_text(encoding="utf-8"))
    return _MANIFEST_CACHE["m"]


def manifest_phase(phase_id: str) -> dict:
    for ph in manifest().get("phases", []):
        if ph.get("id") == phase_id:
            return ph
    raise IntrospectionError(f"phase {phase_id!r} not in {manifest_path()}")


def autofail_registry() -> Dict[str, dict]:
    return {a["code"]: a for a in manifest().get("autofails", []) if a.get("code")}


def registry_trigger(code: str) -> str:
    """The registry's own human-readable trigger prose for `code` ("" if absent)."""
    entry = autofail_registry().get(code)
    return (entry or {}).get("trigger", "") or ""


# ---------------------------------------------------------------------------
# AST plumbing -- read the checkers WITHOUT importing them.
#
# Static parsing (not runtime import) is deliberate: build_deck.py is ~670 KB
# and this module is imported by dispatcher.py at engine start.  ast.parse of
# every file below measures ~80 ms total on the operator box, has no import side
# effects, and cannot be defeated by an import-time failure in an unrelated
# module.  Where a RUNTIME cross-check is cheap and meaningful, the drift test
# runs it as an independent control (see test_contract_completeness.py).
# ---------------------------------------------------------------------------

_AST_CACHE: Dict[str, ast.Module] = {}
_SRC_CACHE: Dict[str, str] = {}


def module_source(mod: str) -> str:
    if mod not in _SRC_CACHE:
        p = SCRIPTS_DIR / (mod + ".py")
        if not p.is_file():
            raise IntrospectionError(f"checker module not found: {p}")
        _SRC_CACHE[mod] = p.read_text(encoding="utf-8", errors="replace")
    return _SRC_CACHE[mod]


def module_tree(mod: str) -> ast.Module:
    if mod not in _AST_CACHE:
        _AST_CACHE[mod] = ast.parse(module_source(mod), filename=str(SCRIPTS_DIR / (mod + ".py")))
    return _AST_CACHE[mod]


def _top_level_funcs(mod: str) -> Dict[str, ast.FunctionDef]:
    return {
        n.name: n
        for n in module_tree(mod).body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _module_level_assigns(mod: str) -> Dict[str, ast.AST]:
    out: Dict[str, ast.AST] = {}
    for n in module_tree(mod).body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = n.value
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value is not None:
            out[n.target.id] = n.value
    return out


def _import_aliases(mod: str) -> Dict[str, str]:
    """`import intelligence_engines_check as _iec` -> {"_iec": "intelligence_engines_check"}.
    Walks the whole tree so `try: import X as Y` inside a Try block is seen."""
    out: Dict[str, str] = {}
    for n in ast.walk(module_tree(mod)):
        if isinstance(n, ast.Import):
            for a in n.names:
                out[a.asname or a.name] = a.name
    return out


def literal_text(node: ast.AST) -> Optional[str]:
    """Recover a source string literal: plain, implicitly-concatenated, f-string
    (interpolations rendered as {...}), or `a + b` of literals.  Returns None
    when the value is not statically knowable."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: List[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append("{...}")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = literal_text(node.left)
        right = literal_text(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _code_dicts(node: ast.AST) -> List[Tuple[str, str]]:
    """Every `{"code": "AF-...", "detail": "..."}` literal inside `node`'s subtree.

    This is the shape BOTH engine checkers emit (intelligence_engines_check
    appends them to `problems`; pitch_engines_check returns lists of them and
    _normalize()s them into the same shape), so one extractor covers both."""
    found: List[Tuple[str, str]] = []
    for n in ast.walk(node):
        if not isinstance(n, ast.Dict):
            continue
        code: Optional[str] = None
        detail: Optional[str] = None
        for k, v in zip(n.keys, n.values):
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                continue
            if k.value == "code":
                t = literal_text(v)
                if t and t.startswith("AF-"):
                    code = t
            elif k.value == "detail":
                detail = literal_text(v)
        if code:
            found.append((code, (detail or "").strip()))
    return found


def _container_dispatch_targets(mod: str, node: ast.AST, bound: Dict[str, str]) -> List[str]:
    """Resolve a table-driven dispatch to the function names it selects.

    Handles exactly two shapes, both present in pitch_engines_check.run():
        CHECKS["1Q"]                       -- literal-key subscript
        CHECKS.get(phase, CHECKS["1Q"])    -- .get() whose key is a bound literal
    `bound` carries string keyword arguments propagated from the CALLER (e.g.
    check_copy calls run(run_dir, phase="1Q"), so phase -> "1Q").

    Deliberately does NOT treat a bare Name reference to a function container
    (e.g. ALL_CHECKS, which run() only selects when phase == "all") as a
    dispatch: over-approximating here would drag SPEECH-QC-only checks into a
    COPY contract.  The drift test cross-checks this resolver against a runtime
    import of the same module, so an under-approximation cannot pass silently."""
    assigns = _module_level_assigns(mod)

    def _names_from_container(container: ast.AST, key: Optional[str]) -> List[str]:
        if key is not None and isinstance(container, ast.Dict):
            for k, v in zip(container.keys, container.values):
                if isinstance(k, ast.Constant) and k.value == key:
                    return _names_from_container(v, None)
            return []
        if isinstance(container, (ast.List, ast.Tuple, ast.Set)):
            return [e.id for e in container.elts if isinstance(e, ast.Name)]
        return []

    targets: List[str] = []

    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        holder = assigns.get(node.value.id)
        key_node = node.slice
        if holder is not None and isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            targets += _names_from_container(holder, key_node.value)

    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.args
    ):
        holder = assigns.get(node.func.value.id)
        arg0 = node.args[0]
        key: Optional[str] = None
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
            key = arg0.value
        elif isinstance(arg0, ast.Name):
            key = bound.get(arg0.id)
        if holder is not None and key is not None:
            targets += _names_from_container(holder, key)

    return targets


def _walk_checker(
    mod: str,
    fn_name: str,
    ring: str,
    *,
    bound: Optional[Dict[str, str]] = None,
    seen: Optional[Set[Tuple[str, str]]] = None,
    rules: Optional[List[Rule]] = None,
    visited_symbols: Optional[List[str]] = None,
) -> List[Rule]:
    """Collect every AF code emitted by `mod.fn_name` and everything it calls
    inside the same module (plus table dispatch)."""
    bound = dict(bound or {})
    seen = seen if seen is not None else set()
    rules = rules if rules is not None else []
    visited_symbols = visited_symbols if visited_symbols is not None else []

    funcs = _top_level_funcs(mod)
    node = funcs.get(fn_name)
    if node is None or (mod, fn_name) in seen:
        return rules
    seen.add((mod, fn_name))
    visited_symbols.append(f"{mod}.{fn_name}")

    source = f"scripts/{mod}.py::{fn_name}"
    for code, detail in _code_dicts(node):
        rules.append(Rule(code, detail or registry_trigger(code), source, ring))

    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in funcs:
            kwargs = {
                kw.arg: kw.value.value
                for kw in n.keywords
                if kw.arg and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)
            }
            _walk_checker(
                mod, n.func.id, ring,
                bound={**bound, **kwargs}, seen=seen, rules=rules,
                visited_symbols=visited_symbols,
            )
        for target in _container_dispatch_targets(mod, n, bound):
            if target in funcs:
                _walk_checker(
                    mod, target, ring,
                    bound=bound, seen=seen, rules=rules,
                    visited_symbols=visited_symbols,
                )

    return rules


# ---------------------------------------------------------------------------
# RING 1 -- the phase's own substance verifier
# ---------------------------------------------------------------------------

def verifier_entry_points(phase_id: str) -> List[Tuple[str, str]]:
    """(module, function) pairs the phase's registered verifier delegates to.

    Derived, not declared: read PHASE_VERIFIERS[phase_id] out of
    phase_verifiers.py, then read that function's body for calls of the form
    `<alias>.<func>(...)` where <alias> is an imported module."""
    assigns = _module_level_assigns("phase_verifiers")
    table = assigns.get("PHASE_VERIFIERS")
    if not isinstance(table, ast.Dict):
        raise IntrospectionError("phase_verifiers.PHASE_VERIFIERS is not a dict literal")

    verifier_name: Optional[str] = None
    for k, v in zip(table.keys, table.values):
        if isinstance(k, ast.Constant) and k.value == phase_id:
            if isinstance(v, ast.Name):
                verifier_name = v.id
            else:
                # e.g. _verify_qc_report("...") / _registry_gate_verifier("...")
                # -- a factory call, not a plain function reference.
                raise IntrospectionError(
                    f"PHASE_VERIFIERS[{phase_id!r}] is a factory call, not a named "
                    "function; engine-checker entry points cannot be read statically"
                )
            break
    if verifier_name is None:
        raise IntrospectionError(f"PHASE_VERIFIERS has no entry for {phase_id!r}")

    fn = _top_level_funcs("phase_verifiers").get(verifier_name)
    if fn is None:
        raise IntrospectionError(f"phase_verifiers.{verifier_name} not found")

    aliases = _import_aliases("phase_verifiers")
    entries: List[Tuple[str, str]] = []
    for n in ast.walk(fn):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id in aliases
        ):
            pair = (aliases[n.func.value.id], n.func.attr)
            if pair not in entries:
                entries.append(pair)
    if not entries:
        raise IntrospectionError(
            f"phase_verifiers.{verifier_name} delegates to no imported checker module "
            "-- the entry-point resolver found nothing, which is under-derivation, "
            "not an empty rule set"
        )
    return entries


# ---------------------------------------------------------------------------
# RING 2 -- manifest preflight + declared gate codes
# ---------------------------------------------------------------------------

def preflight_checkers(phase_id: str) -> List[str]:
    ph = manifest_phase(phase_id)
    names: List[str] = []
    pre = ph.get("preflight") or {}
    if pre.get("checker"):
        names.append(pre["checker"])
    for extra in ph.get("additional_preflights") or []:
        if extra.get("checker"):
            names.append(extra["checker"])
    return names


def _build_deck_checker_rules(checker: str, ring: str) -> List[Rule]:
    """A build_deck _chk_* preflight's requirement, from its OWN text:
      * every registered autofail whose py_symbol / check_script names it, and
      * the checker function's docstring + its literal failure-return strings
        (which is where an un-coded floor like the 500-char slides_copy minimum
        is actually written down)."""
    rules: List[Rule] = []
    for code, entry in sorted(autofail_registry().items()):
        symbols = [entry.get("py_symbol") or ""] + list(entry.get("secondary_py_symbols") or [])
        script = entry.get("check_script") or ""
        if checker in symbols or checker in script:
            rules.append(Rule(code, entry.get("trigger", ""), f"PIPELINE-MANIFEST.autofails[{code}]", ring))

    if rules:
        # The checker already has a registered code carrying its requirement --
        # its docstring would only restate it, and this text is handed to a
        # model whose prompt budget is already the reason P4-COPY was retuned.
        return rules

    # No registered code: the checker enforces an UN-CODED floor (e.g.
    # _chk_slides_copy's near-empty minimum).  Un-coded does not mean
    # un-enforced, so its own docstring / literal failure strings become the
    # requirement -- this is exactly the kind of rule that never reached the
    # author before, because it has no code to look up.
    fn = _top_level_funcs("build_deck").get(checker)
    if fn is not None:
        doc = (ast.get_docstring(fn) or "").strip()
        msgs: List[str] = []
        for n in ast.walk(fn):
            if isinstance(n, ast.Return) and n.value is not None:
                t = literal_text(n.value)
                if t and t.strip():
                    msgs.append(t.strip())
        blurb = doc or "; ".join(dict.fromkeys(msgs))
        if blurb:
            rules.append(Rule("", blurb, f"scripts/build_deck.py::{checker}", ring))
    return rules


# ---------------------------------------------------------------------------
# RING 3 -- downstream phases that RE-JUDGE the same file
# ---------------------------------------------------------------------------

def registry_codes_naming_artifact(artifact_rel: str) -> List[str]:
    """Every registered autofail whose OWN registry entry names this artifact.

    This is the mechanical enumeration of "other things that read the file this
    phase writes" -- it needs no call-graph analysis and no judgement, because
    the registry entry itself states what the code is triggered by."""
    needle = Path(artifact_rel).name
    out: List[str] = []
    for code, entry in sorted(autofail_registry().items()):
        if needle in json.dumps(entry):
            out.append(code)
    return out


# The QC phase whose ENTIRE JOB is grading P4_COPY_ARTIFACT.  This one link is
# DECLARED, not derived -- the manifest states it in prose ("Copy QC (Phase 1Q)
# -- sequenced AFTER Slide Copy (O1 re-sequence: a QC follows the artifact it
# grades...)") but not in any machine-readable "grades:" field, and inventing a
# fuzzy string match on that prose would be a worse kind of guess than naming it
# here where a reviewer can see it.  Its twenty-five gate CODES are still read
# straight out of the manifest -- only the phase id is typed.
P4_COPY_QC_PHASE = "P1Q-COPY-QC"


def label_matched_phase_codes(artifact_rel: str) -> List[Tuple[str, str, str]]:
    """(phase_id, code, label) for every phase whose OWN preflight label both
    names this artifact AND names the code it gates it with.

    This is the strict version of "other phases that read my file": a phase like
    P0B-PRIORITY declares in its own label that it checks
    'eight build-move beat tags monotonic in slides_copy.md; AF-NO-SHIFT'.  Only
    AF-NO-SHIFT is taken from it -- its five SIBLING gate codes judge
    priority_shift_spec.json, a file P4-COPY does not write, and telling the
    copywriter to fix those would repeat the exact scoping error that would put
    the AF-SP-* codes (which judge sp_structure.json) in this contract."""
    needle = Path(artifact_rel).name
    out: List[Tuple[str, str, str]] = []
    for ph in manifest().get("phases", []):
        if ph.get("id") == "P4-COPY":
            continue
        labels = []
        pre = ph.get("preflight") or {}
        if pre.get("label"):
            labels.append(pre["label"])
        for extra in ph.get("additional_preflights") or []:
            if extra.get("label"):
                labels.append(extra["label"])
        for label in labels:
            if needle not in label:
                continue
            for code in (ph.get("gate_codes") or []):
                if code in label:
                    out.append((ph["id"], code, label))
    return out


# ---------------------------------------------------------------------------
# RING 4 -- doctrine with no Python checker and no registry entry
# ---------------------------------------------------------------------------

_AF_C8_SECTION_RE = re.compile(
    r"^##\s*AF-C8\s+ARCHETYPE\s+CARVE-OUT.*?$(.*?)(?=^---\s*$|\Z)",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)
_CARVEOUT_FENCE_RE = re.compile(r"```\s*\n(DEFAULT slides.*?)```", re.IGNORECASE | re.DOTALL)


def af_c8_doctrine() -> Tuple[str, str]:
    """(prose, carve_out_block) read verbatim from MASTER-QC-AUTOFAIL-RULESET.md.

    AF-C8 is graded by the QC Specialist role reading slides_copy.md.  It has no
    Python checker anywhere in this codebase and no PIPELINE-MANIFEST.autofails
    entry, so the doctrine file is the only machine-readable source of truth --
    parsing it (rather than re-typing the numbers) is what keeps this contract
    from drifting away from the ruling the moment the ruling is amended."""
    text = ruleset_path().read_text(encoding="utf-8", errors="replace")
    m = _AF_C8_SECTION_RE.search(text)
    if not m:
        raise IntrospectionError(
            f"AF-C8 ARCHETYPE CARVE-OUT section not found in {ruleset_path()} "
            "-- the doctrine moved or was removed; the contract must not silently "
            "fall back to an unstated ceiling"
        )
    section = m.group(1)
    fence = _CARVEOUT_FENCE_RE.search(section)
    if not fence:
        raise IntrospectionError(
            f"AF-C8 carve-out numbers block not found inside the carve-out section of {ruleset_path()}"
        )
    prose = " ".join(
        line.strip()
        for line in section.split("```")[0].splitlines()
        if line.strip()
    )
    return prose, fence.group(1).strip()


# ---------------------------------------------------------------------------
# The composed rule set
# ---------------------------------------------------------------------------

def _dedupe(rules: Sequence[Rule]) -> List[Rule]:
    """One entry per code.

    RING wins by first appearance, and rules are composed in ring priority order
    (verifier > gate > preflight > downstream > doctrine), so a code that both
    blocks this phase AND is re-checked downstream is filed under the gate that
    stops it soonest.

    REQUIREMENT TEXT is the LONGEST message the winning ring offers for that
    code.  A checker often emits the same code from several branches -- a short
    "cannot verify, artifact absent" defer message and a long "here is the rule
    you broke" message.  Handing the author the short one would technically be
    'sourced from the checker' and still teach nothing, which is the whole
    defect this module exists to kill.  Un-coded floors are keyed by source so
    two distinct preflight floors both survive."""
    order: List[str] = []
    best: Dict[str, Rule] = {}
    for r in rules:
        key = r.code or f"@{r.source}"
        if key not in best:
            order.append(key)
            best[key] = r
            continue
        cur = best[key]
        if r.ring == cur.ring and len(r.requirement or "") > len(cur.requirement or ""):
            best[key] = Rule(cur.code, r.requirement, r.source, cur.ring)
    return [best[k] for k in order]


_RULES_CACHE: Dict[str, List[Rule]] = {}


def p4_copy_rules() -> List[Rule]:
    """The full derived constraint set for working/copy/slides_copy.md."""
    if "p4" in _RULES_CACHE:
        return _RULES_CACHE["p4"]

    rules: List[Rule] = []

    # RING 1 -- substance verifier -> engine checkers.
    for mod, fn in verifier_entry_points("P4-COPY"):
        rules.extend(_walk_checker(mod, fn, "verifier"))

    # RING 2 -- manifest gate codes + preflight checkers.
    ph = manifest_phase("P4-COPY")
    for code in ph.get("gate_codes") or []:
        rules.append(Rule(code, registry_trigger(code), "PIPELINE-MANIFEST.P4-COPY.gate_codes", "gate"))
    for checker in preflight_checkers("P4-COPY"):
        rules.extend(_build_deck_checker_rules(checker, "preflight"))

    # RING 3 -- everything else that re-judges this same file.
    for code in registry_codes_naming_artifact(P4_COPY_ARTIFACT):
        rules.append(
            Rule(code, registry_trigger(code), f"PIPELINE-MANIFEST.autofails[{code}]", "downstream")
        )
    for phase_id, code, _label in label_matched_phase_codes(P4_COPY_ARTIFACT):
        rules.append(
            Rule(code, registry_trigger(code), f"PIPELINE-MANIFEST.{phase_id}.preflight.label", "downstream")
        )
    for code in manifest_phase(P4_COPY_QC_PHASE).get("gate_codes") or []:
        rules.append(
            Rule(code, registry_trigger(code), f"PIPELINE-MANIFEST.{P4_COPY_QC_PHASE}.gate_codes", "downstream")
        )

    # RING 4 -- doctrine-only.
    prose, carve_out = af_c8_doctrine()
    rules.append(
        Rule(
            "AF-C8",
            prose + "\n" + carve_out,
            f"{ruleset_path().name}::AF-C8 ARCHETYPE CARVE-OUT",
            "doctrine",
        )
    )

    result = _dedupe(rules)
    if not result:
        raise IntrospectionError("derived an EMPTY rule set for P4-COPY -- refusing to pretend there are no rules")
    _RULES_CACHE["p4"] = result
    return result


def p4_copy_codes() -> List[str]:
    """Every autofail code the P4-COPY artifact can be failed on, sorted."""
    return sorted({r.code for r in p4_copy_rules() if r.code})


# ---------------------------------------------------------------------------
# Rendering -- the block that goes INTO the contract
# ---------------------------------------------------------------------------

_RING_HEADINGS = {
    "verifier": (
        "A. GRADED BY THIS PHASE'S OWN SUBSTANCE VERIFIER "
        "(phase_verifiers.verify('P4-COPY') -> the writing/pricing engines). "
        "Any one of these blocks the phase immediately."
    ),
    "gate": "B. DECLARED GATE CODES for this phase (PIPELINE-MANIFEST P4-COPY.gate_codes).",
    "preflight": "C. PREFLIGHT CHECKERS the engine runs against this artifact.",
    "downstream": (
        "D. RE-JUDGED LATER against this SAME file (Copy-QC and the registered "
        "autofails whose own trigger names slides_copy.md). Passing A-C and "
        "failing these still costs a full re-author."
    ),
    "doctrine": "E. DOCTRINE-ONLY (no Python checker; graded by the QC Specialist role reading this file).",
}
_RING_ORDER = ("verifier", "gate", "preflight", "downstream", "doctrine")


def _one_line(text: str, limit: int = 300) -> str:
    flat = " ".join(str(text).split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def render_constraint_index(rules: Optional[Sequence[Rule]] = None) -> str:
    """The MECHANICAL CONSTRAINT INDEX appended to ARTIFACT_CONTRACTS["P4-COPY"].

    Generated at import time from p4_copy_rules() so a rule added to any checker
    on the judging path reaches the author on the very next dispatch, with no
    human in the loop.  The hand-written contract points above it stay: they
    teach the LITERAL syntax (ARC markers, field names) that no failure message
    contains.  The drift test enforces that a new code also earns hand-written
    guidance -- this index is the floor, not the ceiling."""
    rules = list(rules if rules is not None else p4_copy_rules())
    lines: List[str] = [
        "MECHANICAL CONSTRAINT INDEX -- auto-derived at engine start from the code "
        "that actually judges this artifact (presentation_job/contract_introspect.py). "
        "This is the COMPLETE set of failure codes reachable against "
        f"{P4_COPY_ARTIFACT}. Nothing here is optional and nothing here is advisory: "
        "each line is the checker's own failure message, quoted. Satisfy every one "
        "of them in the SAME pass -- each miss costs a full re-author."
    ]
    for ring in _RING_ORDER:
        subset = [r for r in rules if r.ring == ring]
        if not subset:
            continue
        lines.append("")
        lines.append(_RING_HEADINGS[ring])
        for r in sorted(subset, key=lambda x: (x.code == "", x.code, x.source)):
            if r.ring == "doctrine":
                # The AF-C8 carve-out numbers are a table; keep them literal.
                lines.append(f"  * {r.code} [{r.source}]:")
                for sub in r.requirement.splitlines():
                    if sub.strip():
                        lines.append("      " + sub.rstrip())
                continue
            label = r.code or f"(un-coded floor) {r.source.split('::')[-1]}"
            lines.append(f"  * {label}: {_one_line(r.requirement)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Whole-pipeline audit -- which agent phases author blind?
# ---------------------------------------------------------------------------

def agent_phase_ids() -> List[str]:
    return [
        ph["id"]
        for ph in manifest().get("phases", [])
        if (ph.get("executor") or {}).get("kind") == "agent"
    ]


def codes_judging_phase(phase_id: str) -> Dict[str, List[str]]:
    """Best-effort, per-phase: which codes judge this phase's artifact.

    Returns {"verifier": [...], "gate": [...], "preflight": [...], "notes": [...]}.
    Never raises -- an unreadable ring is reported as a note so the audit table
    distinguishes 'no codes' from 'could not be determined'."""
    out: Dict[str, List[str]] = {"verifier": [], "gate": [], "preflight": [], "notes": []}
    try:
        ph = manifest_phase(phase_id)
    except IntrospectionError as exc:
        out["notes"].append(str(exc))
        return out

    out["gate"] = list(ph.get("gate_codes") or [])

    try:
        for mod, fn in verifier_entry_points(phase_id):
            out["verifier"].extend(r.code for r in _walk_checker(mod, fn, "verifier") if r.code)
    except IntrospectionError as exc:
        out["notes"].append(f"verifier: {exc}")

    for checker in preflight_checkers(phase_id):
        rs = _build_deck_checker_rules(checker, "preflight")
        got = [r.code for r in rs if r.code]
        out["preflight"].extend(got)
        if not got:
            out["notes"].append(f"preflight {checker}: no registered code (un-coded floor)")

    out["verifier"] = sorted(set(out["verifier"]))
    out["preflight"] = sorted(set(out["preflight"]))
    return out


def phase_constraint_audit(contracts: Dict[str, str]) -> List[dict]:
    """One row per agent-executor phase: codes it is judged by vs codes its
    ARTIFACT_CONTRACTS entry actually names.

    `contracts` is passed in (rather than imported) so this module never imports
    dispatcher -- dispatcher imports THIS module, and a cycle would be a very
    stupid way to break the engine."""
    rows: List[dict] = []
    for phase_id in agent_phase_ids():
        judged = codes_judging_phase(phase_id)
        all_codes = sorted(set(judged["verifier"]) | set(judged["gate"]) | set(judged["preflight"]))
        text = contracts.get(phase_id, "")
        named = sorted(c for c in all_codes if c in text)
        missing = sorted(c for c in all_codes if c not in text)
        rows.append(
            {
                "phase": phase_id,
                "has_static_contract": phase_id in contracts,
                "artifact": manifest_phase(phase_id).get("produces_artifact", ""),
                "judged_by": all_codes,
                "contract_names": named,
                "missing": missing,
                "notes": judged["notes"],
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Self-report (used by the drift test and by operators debugging a derivation)
# ---------------------------------------------------------------------------

def derivation_report() -> dict:
    entry_points = verifier_entry_points("P4-COPY")
    visited: List[str] = []
    for mod, fn in entry_points:
        _walk_checker(mod, fn, "verifier", visited_symbols=visited)
    rules = p4_copy_rules()
    return {
        "manifest_path": str(manifest_path()),
        "ruleset_path": str(ruleset_path()),
        "manifest_version": manifest().get("manifest_version"),
        "registry_size": len(autofail_registry()),
        "entry_points": [f"{m}.{f}" for m, f in entry_points],
        "visited_checkers": visited,
        "codes": p4_copy_codes(),
        "code_count": len(p4_copy_codes()),
        "rule_count": len(rules),
        "by_ring": {
            ring: sorted({r.code for r in rules if r.ring == ring and r.code})
            for ring in _RING_ORDER
        },
    }


if __name__ == "__main__":  # pragma: no cover -- operator convenience
    print(json.dumps(derivation_report(), indent=2))
    print()
    print(render_constraint_index())
