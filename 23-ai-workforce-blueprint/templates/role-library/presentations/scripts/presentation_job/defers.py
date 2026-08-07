#!/usr/bin/env python3
"""defers_unless gating evaluator for the presentation manifest.

The manifest's optional P-U-* phases carry a ``defers_unless`` expression, e.g.
``intake.want_sales_checkout == "yes"`` or
``intake.want_sales_checkout == "yes" or intake.want_vsl_page == "yes"``.  A phase
whose gate condition is FALSE is DEFERRED (skipped) for that run — never surfaced,
never attested, and (per DESIGN-OPUS.md §4.2) recorded with a skip_attestation so
the attestation chain stays complete and P9-DELIVER never fails on a missing
optional phase.

Intake-key resolution
---------------------
The deck-intake driver (feat/presentation-upsell-intake) stores the upsell answers
under ``pre_presentation_capture.*`` — the questions declare
``storeOn: WANT_SALES_CHECKOUT`` / ``WANT_VSL_PAGE``, and the driver's
``storeTarget`` maps those to ``pre_presentation_capture.WANT_SALES_CHECKOUT`` /
``pre_presentation_capture.WANT_VSL_PAGE``.  The driver ALSO writes a
``waivers[]`` array: when the client declined a branch, a record with
``rule: "sales_checkout"`` / ``rule: "vsl_page"`` and a verbatim
``client_request_quote`` is present (never inferred, never assistant-written).

Resolution order for a leaf key (e.g. ``want_sales_checkout``):

  1. ``intake.pre_presentation_capture.<UPPER_KEY>`` (the storeTarget home)
  2. ``intake.pre_presentation_capture.<key>`` (lowercase tolerant)
  3. ``intake.<key>`` (top-level fallback, the old manifest spelling)
  4. a ``waivers[]`` record whose ``rule`` is the waiver rule for the key → "no"
     (a recorded waiver IS a client decline)
  5. the question's declared default
     (want_sales_checkout → "yes", want_vsl_page → "no")

No ``eval`` of arbitrary manifest text ever happens: the only operator expression
that reaches the evaluator is a boolean combination of already-reduced
True/False literals (whitelist-checked before the final evaluation).
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

# The two optional-branch questions, their pre_presentation_capture storeTarget
# keys, their waiver rules, and their intake-question defaults.
# (Mirrors deck-intake-questions.json + upsell-questions.json.)
_WANT_KEYS: Dict[str, Dict[str, Any]] = {
    "want_sales_checkout": {
        "capture_key": "WANT_SALES_CHECKOUT",
        "waiver_rule": "sales_checkout",
        "default": "yes",
    },
    "want_vsl_page": {
        "capture_key": "WANT_VSL_PAGE",
        "waiver_rule": "vsl_page",
        "default": "no",
    },
}

_YES_VALUES = {"yes", "true", "1", "y", "on"}
_NO_VALUES = {"no", "false", "0", "n", "off"}


def _truthy(v: Any) -> bool:
    """Coerce an intake answer to a boolean yes/no decision."""
    if v is True:
        return True
    if v is False:
        return False
    s = str(v).strip().lower()
    if s in _YES_VALUES:
        return True
    if s in _NO_VALUES:
        return False
    # Unknown value → treat as the client's explicit opt-in only when the answer
    # reads like an affirmation; anything else is NOT consent.
    return False


def _waiver_rules(intake: Dict[str, Any]) -> set:
    """Return the set of waiver rules recorded in intake.waivers[]."""
    waivers = intake.get("waivers")
    if not isinstance(waivers, list):
        return set()
    out = set()
    for w in waivers:
        if isinstance(w, dict) and w.get("rule"):
            out.add(str(w["rule"]))
    return out


def resolve_intake_value(intake: Dict[str, Any], key: str) -> Optional[str]:
    """Resolve a manifest ``intake.<key>`` reference to its stored answer.

    Returns a lower-case string ("yes"/"no") or None when the answer cannot be
    determined.  Never raises on malformed intake data.
    """
    if not isinstance(intake, dict):
        return None

    spec = _WANT_KEYS.get(key)
    if spec is not None:
        cap = intake.get("pre_presentation_capture")
        if isinstance(cap, dict):
            for cand in (spec["capture_key"], key, spec["capture_key"].lower()):
                if cand in cap and cap[cand] is not None:
                    v = str(cap[cand]).strip().lower()
                    if v:
                        return v
        # Top-level fallback.
        if key in intake and intake[key] is not None:
            v = str(intake[key]).strip().lower()
            if v:
                return v
        # A recorded client waiver for this branch IS the decline.
        if spec["waiver_rule"] in _waiver_rules(intake):
            return "no"
        return spec["default"]

    # Generic key: look top-level, then under pre_presentation_capture.
    if key in intake and intake[key] is not None:
        return str(intake[key]).strip().lower()
    cap = intake.get("pre_presentation_capture")
    if isinstance(cap, dict):
        for cand in (key, key.upper()):
            if cand in cap and cap[cand] is not None:
                return str(cap[cand]).strip().lower()
    return None


# Comparison pattern:  <path> == "value"
#   path may be dotted (intake.want_sales_checkout) or bare (funnel_type).
_COMPARE_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_.]*)\s*==\s*"([^"]*)"')


def _reduce_comparisons(expr: str, intake: Dict[str, Any]) -> str:
    """Replace each ``<path> == "value"`` comparison with True/False.

    Paths prefixed with ``intake.`` resolve against the intake record; bare
    paths resolve the same way (the funnel manifests use ``funnel_type``).  An
    expression with no comparisons reduces to "" (the caller treats an empty
    expression as "no gate → run the phase").
    """
    def _sub(m: re.Match) -> str:
        raw_path = m.group(1)
        want = m.group(2)
        if raw_path.startswith("intake."):
            key = raw_path[len("intake."):]
        else:
            key = raw_path
        got = resolve_intake_value(intake, key)
        if got is None:
            return "False"
        return "True" if got == want.strip().lower() else "False"

    return _COMPARE_RE.sub(_sub, expr)


# After comparison reduction, only boolean operators + True/False literals may
# remain.  Rather than ever eval() the reduced string (which would be executing
# manifest-authored text as code), parse it with the AST and walk ONLY the
# boolean-expression nodes.  Anything the AST carries that is not a
# boolean constant / BoolOp / Not / parenthesized expression is a manifest
# authoring error → fail CLOSED (treat the phase as deferred) rather than risk
# executing it.

# Security note: the string reaching _safe_ast_bool is ALWAYS the reduced form
# of the original defers_unless expression — every <path> == "value" comparison
# has already been replaced by a True/False literal via _reduce_comparisons().
# The AST walk below rejects every other node kind (calls, attribute access,
# arithmetic, names, etc.), so no manifest text is ever evaluated as code.


def _safe_ast_bool(node: ast.AST) -> bool:
    """Evaluate a whitelisted boolean-expression AST to a bool. Raises for any
    node kind outside the boolean-constant/BoolOp/Not/paren whitelist."""
    if isinstance(node, ast.Expression):
        return _safe_ast_bool(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_safe_ast_bool(v) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(_safe_ast_bool(v) for v in node.values)
        raise ValueError("unsupported BoolOp")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _safe_ast_bool(node.operand)
    raise ValueError(f"unsupported node in defers_unless expression: {type(node).__name__}")


def _tree_is_whitelisted(node: ast.AST) -> bool:
    """Pre-walk the whole tree and reject ANY node outside the boolean whitelist,
    BEFORE any short-circuit evaluation. A malicious or malformed sub-expression
    makes the entire gate fail closed even if an earlier comparison is True."""
    if isinstance(node, ast.Expression):
        return _tree_is_whitelisted(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return True
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        return all(_tree_is_whitelisted(v) for v in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _tree_is_whitelisted(node.operand)
    return False


def evaluate_defers_unless(expr: Any, intake: Dict[str, Any]) -> bool:
    """Evaluate a phase's ``defers_unless`` expression against the intake record.

    Returns True when the phase should RUN, False when it should be DEFERRED
    (skipped).  A missing/empty/None expression → True (no gate).  A malformed
    or non-whitelisted expression → False (fail closed: never run a phase whose
    gate cannot be proven open).
    """
    if expr is None or expr == "":
        return True
    if not isinstance(expr, str):
        return False

    reduced = _reduce_comparisons(expr.strip(), intake).strip()
    if reduced == "":
        # No recognized comparison in the expression.  If it was only whitespace
        # to begin with it was already handled above; otherwise treat an
        # unparseable expression as fail-closed.
        return False
    try:
        tree = ast.parse(reduced, mode="eval")
    except SyntaxError:
        return False
    if not _tree_is_whitelisted(tree):
        return False
    try:
        return _safe_ast_bool(tree)
    except ValueError:
        return False


def load_intake(run_dir: Path) -> Dict[str, Any]:
    """Load the run's intake record from working/copy/intake.json (best-effort).

    The engine's ``state["intake"]`` is preferred when present; this is the
    fallback for the phase planner / turn-gate that may not have a state object
    in memory.  Returns {} when the file is absent or unparseable.
    """
    p = run_dir / "working" / "copy" / "intake.json"
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def phase_is_deferred(phase: Any, intake: Dict[str, Any]) -> bool:
    """True when the phase has a defers_unless gate and it evaluates false.

    Accepts either a manifest.Phase (has ``.defers_unless`` attribute) or a raw
    manifest dict (has ``["defers_unless"]`` key).
    """
    expr = getattr(phase, "defers_unless", None)
    if expr is None and isinstance(phase, dict):
        expr = phase.get("defers_unless")
    if expr is None or expr == "":
        return False
    return not evaluate_defers_unless(expr, intake)
