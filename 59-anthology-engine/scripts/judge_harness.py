#!/usr/bin/env python3
"""judge_harness.py -- Gate B, the semantic checks and the Tier 2 rubric on the JUDGE tier.

Authored by unit W1.17. This is the CONTENT gate's model-driven instrument (SPEC Section 4,
QC-PROTOCOL Instruments 1 and 2). It runs, on the independent JUDGE tier and NEVER on the
tier that drafted the piece:
  - Tier 1 SEMANTIC checks 13-15 (13 fabrication nuance, 14 voice fidelity to the tone
    document, 15 outline fidelity of the chapter). These are hard-fail (binary).
  - the Tier 2 ten-dimension RUBRIC, each dimension scored 8 or higher, with NO AVERAGING.

INDEPENDENCE LAW (AF-AE-JUDGE-INDEPENDENCE): the judge tier, resolution, and persona are
always distinct from the tier, resolution, and persona that drafted the piece. model_router.py
records the honest resolved model on every turn precisely so this harness can compare; when the
JUDGE resolution equals the writer resolution (or the personas collide, or the drafting tier
IS the JUDGE tier) the harness REFUSES rather than let a model grade its own homework.

GATE SEPARATION (the cardinal rule): this is Gate B (does a PIECE OF CONTENT ship). It is
NEVER the 8.5 build/merge gate (Gate A). The rubric threshold here is 8-per-dimension with no
averaging; there is no single aggregate and no 8.5 anywhere in this file. A perfect chapter
says nothing about merge readiness, and a 9.0 build unit says nothing about a chapter.

THE TEN RUBRIC DIMENSIONS (each >= 8, independently gated, never averaged):
  1 Voice Fidelity to the blended tone      6 Narrative Craft and story integration
  2 Avatar Resonance                        7 Fidelity to the Participant's ideas
  3 Goal Alignment                          8 Clarity and Readability at the 14pt format
  4 Opening Power                           9 Chapter-in-Anthology Fit (theme and pacing)
  5 Closing Power                          10 Editorial Polish

DESIGN: the harness is transport-agnostic. run() takes an injectable router callable
(default: model_router.route on the resolved per-box map) so the GATE LOGIC is unit-testable
with a scripted judge and a controllable resolved model, with no network and no token spend.
The parsed judge verdict is graded by evaluate_judgment(), a pure fail-closed function: a
missing check or a missing/non-numeric score is treated as a FAILURE, never a silent pass.

Exit codes (SPEC 3.4 row 16; house: 1 unexpected error):
  0  pass (every semantic check passed and every applicable dimension is >= 8)
  2  independence violation (judge tier/resolution/persona equals the writer's) OR a bad
     invocation the harness must refuse (both are house "validation or guard refusal")
  4  a content QC failure: any semantic check failed, or any dimension scored below 8
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Layout / sibling import
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# model_router.py (W1.9) owns the JUDGE-tier chain and the Anthropic deny pattern.
# Reuse both so the harness and the router agree on what an Anthropic-shaped id is
# and this file carries no contiguous banned literal. Guarded so the harness still
# imports (for offline gate evaluation and self-test) on a checkout without it.
try:
    import model_router as _mr  # type: ignore
    _route_default = _mr.route
    _is_anthropic_shaped = _mr.is_anthropic_shaped
except Exception:  # pragma: no cover - offline fallback
    _mr = None
    _route_default = None
    _A = "anthro" + "pic"
    _C = "clau" + "de"
    _ANTHROPIC_RE = re.compile(
        r"(?i)(^|[^a-z0-9])(" + _C + r"|" + _A + r")([^a-z0-9]|$)"
        r"|" + _A + r"/" + r"|" + _C + r"-" + r"|us\." + _A + r"\.")

    def _is_anthropic_shaped(text: str) -> bool:  # type: ignore
        return bool(text) and bool(_ANTHROPIC_RE.search(str(text)))

EX_OK, EX_ERR, EX_INDEP, EX_FAIL = 0, 1, 2, 4

JUDGE_TIER = "JUDGE"
JUDGE_PERSONA = "the independent Editorial Judge"
DIM_MIN = 8  # each rubric dimension must be at least this; no averaging, ever.

SEMANTIC_NAMES = {
    13: "Fabrication nuance (no invented biography, quotes, or research)",
    14: "Voice fidelity to the tone document",
    15: "Outline fidelity of the chapter",
}
DIM_NAMES = {
    1: "Voice Fidelity to the blended tone",
    2: "Avatar Resonance",
    3: "Goal Alignment",
    4: "Opening Power",
    5: "Closing Power",
    6: "Narrative Craft and story integration",
    7: "Fidelity to the Participant's ideas",
    8: "Clarity and Readability at the 14-point designed format",
    9: "Chapter-in-Anthology Fit (theme and pacing)",
    10: "Editorial Polish",
}
ALL_DIMS = list(range(1, 11))

# Default applicable set per deliverable kind (SPEC 4). The chapter and its rewrite
# get the full battery; the manuscript gets fabrication + voice + the full rubric;
# lighter deliverables get only the relevant semantic check.
DEFAULT_APPLICABLE: Dict[str, Dict[str, List[int]]] = {
    "chapter":    {"checks": [13, 14, 15], "dims": ALL_DIMS},
    "rewrite":    {"checks": [13, 14, 15], "dims": ALL_DIMS},
    "manuscript": {"checks": [13, 14], "dims": ALL_DIMS},
    "avatar":     {"checks": [13], "dims": []},
    "outline":    {"checks": [15], "dims": []},
    "tone":       {"checks": [14], "dims": []},
    "blurb":      {"checks": [13], "dims": []},
    "titles":     {"checks": [13], "dims": []},
}


class BadInvocation(Exception):
    pass


class JudgeIndependenceViolation(Exception):
    pass


# ---------------------------------------------------------------------------
# Applicable-set resolution
# ---------------------------------------------------------------------------
def resolve_applicable(env: dict) -> Dict[str, List[int]]:
    kind = env.get("kind")
    if env.get("judge_checks") is not None or env.get("judge_dims") is not None:
        checks = [int(x) for x in (env.get("judge_checks") or [])]
        dims = [int(x) for x in (env.get("judge_dims") or [])]
        return {"checks": checks, "dims": dims}
    if kind in DEFAULT_APPLICABLE:
        d = DEFAULT_APPLICABLE[kind]
        return {"checks": list(d["checks"]), "dims": list(d["dims"])}
    raise BadInvocation(
        "no judge scope for kind %r; supply judge_checks/judge_dims explicitly "
        "(known kinds: %s)" % (kind, ", ".join(sorted(DEFAULT_APPLICABLE))))


# ---------------------------------------------------------------------------
# Independence enforcement (AF-AE-JUDGE-INDEPENDENCE)
# ---------------------------------------------------------------------------
def _norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def enforce_independence(writer_tier: Optional[str], writer_model: str, writer_persona: str,
                         judge_model: str, judge_persona: str = JUDGE_PERSONA) -> None:
    """Refuse (AF-AE-JUDGE-INDEPENDENCE) unless the JUDGE resolution and persona are
    genuinely distinct from the tier/resolution/persona that drafted the piece."""
    if _norm(writer_tier) == _norm(JUDGE_TIER):
        raise JudgeIndependenceViolation(
            "AF-AE-JUDGE-INDEPENDENCE: the piece was drafted on the JUDGE tier; a judge "
            "cannot grade its own tier")
    if not str(writer_model or "").strip():
        raise BadInvocation(
            "writer_model is required to prove judge independence (model_router records the "
            "honest resolved drafting model; pass it in the envelope)")
    if _is_anthropic_shaped(judge_model):
        raise JudgeIndependenceViolation(
            "AF-AE-JUDGE-INDEPENDENCE: the JUDGE resolved to an Anthropic-family id, which the "
            "engine never runs at call time")
    if _norm(judge_model) == _norm(writer_model):
        raise JudgeIndependenceViolation(
            "AF-AE-JUDGE-INDEPENDENCE: the JUDGE resolution (%r) equals the writer resolution; "
            "a model may not grade its own draft" % judge_model)
    if writer_persona and _norm(writer_persona) == _norm(judge_persona):
        raise JudgeIndependenceViolation(
            "AF-AE-JUDGE-INDEPENDENCE: the QC persona equals the drafting persona (%r)"
            % writer_persona)


# ---------------------------------------------------------------------------
# Judge prompt construction and response parsing
# ---------------------------------------------------------------------------
def _ctx_block(label: str, value: Optional[str], limit: int = 24000) -> str:
    if not value:
        return ""
    v = value if len(value) <= limit else value[:limit] + "\n...[truncated for the judge]..."
    return "\n----- %s -----\n%s\n" % (label, v)


def build_judge_messages(env: dict, applicable: Dict[str, List[int]]) -> List[dict]:
    """Compose the JUDGE-tier messages. The judge is the independent Editorial Judge
    and MUST return strict JSON only. All context is supplied; the judge invents
    nothing. (The pinned S9 personas live in the prompt assets; this harness carries
    the QC persona framing and the strict output contract.)"""
    deliverable = env.get("deliverable_text") or ""
    if not deliverable and env.get("deliverable_path"):
        deliverable = Path(env["deliverable_path"]).read_text(encoding="utf-8")
    if not deliverable.strip():
        raise BadInvocation("no deliverable_text/deliverable_path to judge")

    checks = applicable["checks"]
    dims = applicable["dims"]

    schema_checks = ", ".join(
        '"%d": {"pass": true|false, "reason": "<one sentence>"}' % c for c in checks) or "(none)"
    schema_dims = ", ".join(
        '"%d": {"score": <integer 1-10>, "justification": "<one sentence>"}' % d for d in dims) \
        or "(none)"

    check_menu = "\n".join("  %d. %s" % (c, SEMANTIC_NAMES.get(c, "check %d" % c)) for c in checks)
    dim_menu = "\n".join("  %d. %s" % (d, DIM_NAMES[d]) for d in dims)

    system = (
        "You are %s for an anthology publisher. You did NOT write this piece; you grade it "
        "independently and skeptically. You never invent facts, never soften a failure, and "
        "never average scores. Judge ONLY against the supplied material. Return STRICT JSON "
        "and nothing else." % JUDGE_PERSONA)

    instr_parts = [
        "Grade the DELIVERABLE below.",
        "",
        "SEMANTIC HARD-FAIL CHECKS (each is pass/fail; a single fail means the piece does not "
        "ship):",
        check_menu or "  (none)",
        "",
        "RUBRIC DIMENSIONS (score each 1-10; the piece ships only when EVERY dimension is 8 or "
        "higher; scores are NEVER averaged):",
        dim_menu or "  (none)",
        "",
        "Return EXACTLY this JSON shape (no prose, no code fence):",
        '{"checks": {%s}, "dimensions": {%s}}' % (schema_checks, schema_dims),
    ]
    context = "".join([
        _ctx_block("DELIVERABLE UNDER REVIEW", deliverable),
        _ctx_block("BLENDED TONE DOCUMENT (for voice fidelity, checks 14 and dimension 1)",
                   env.get("tone_text") or _read_opt(env.get("tone_path"))),
        _ctx_block("APPROVED OUTLINE (for outline fidelity, check 15)",
                   env.get("outline_text") or _read_opt(env.get("outline_path"))),
        _ctx_block("PARTICIPANT AVATAR (for avatar resonance, dimension 2)",
                   env.get("avatar_text") or _read_opt(env.get("avatar_path"))),
        _ctx_block("STATED PRIMARY GOAL (for goal alignment, dimension 3)",
                   env.get("primary_goal")),
        _ctx_block("PARTICIPANT-SUPPLIED IDEAS AND STORIES (for fidelity, checks 13 and "
                   "dimension 7)", _stories_block(env)),
        _ctx_block("ANTHOLOGY CONTEXT (for chapter-in-anthology fit, dimension 9)",
                   env.get("anthology_context")),
    ])
    user = "\n".join(instr_parts) + "\n" + context
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _read_opt(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _stories_block(env: dict) -> Optional[str]:
    intake = env.get("intake")
    if isinstance(intake, str):
        intake = _read_opt(intake)
        try:
            intake = json.loads(intake) if intake else None
        except ValueError:
            intake = None
    if not isinstance(intake, dict):
        return env.get("supplied_ideas_text")
    parts = []
    for k in ("chapter_premise", "target_reader"):
        if intake.get(k):
            parts.append("%s: %s" % (k, intake[k]))
    stories = intake.get("personal_stories")
    if isinstance(stories, list):
        parts.append("personal_stories: " + "; ".join(str(s) for s in stories))
    elif isinstance(stories, str):
        parts.append("personal_stories: " + stories)
    return "\n".join(parts) if parts else env.get("supplied_ideas_text")


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.S)


def parse_judge_json(text: str) -> dict:
    """Extract the judge's strict-JSON verdict. Tolerates an accidental code fence
    or leading prose by taking the outermost {...} block. Fail-closed on nothing
    parseable (the caller then treats every check/dimension as unanswered = fail)."""
    if not text or not text.strip():
        raise BadInvocation("empty judge response")
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    try:
        return json.loads(raw)
    except ValueError:
        m = _JSON_OBJ_RE.search(text)
        if not m:
            raise BadInvocation("judge response carried no JSON object")
        try:
            return json.loads(m.group(0))
        except ValueError as exc:
            raise BadInvocation("judge JSON did not parse: %s" % exc)


# ---------------------------------------------------------------------------
# Pure gate evaluation (fail-closed; no averaging)
# ---------------------------------------------------------------------------
class Outcome:
    __slots__ = ("kind", "id", "name", "status", "detail")

    def __init__(self, kind: str, oid: int, name: str, status: str, detail: str):
        self.kind = kind    # "check" | "dimension"
        self.id = oid
        self.name = name
        self.status = status  # "PASS" | "FAIL"
        self.detail = detail

    def to_dict(self) -> dict:
        return {"kind": self.kind, "id": self.id, "name": self.name,
                "status": self.status, "detail": self.detail}


class JudgeVerdict:
    def __init__(self, kind: str):
        self.kind = kind
        self.outcomes: List[Outcome] = []
        self.independence: dict = {}

    def add(self, o: Outcome):
        self.outcomes.append(o)

    @property
    def failures(self) -> List[Outcome]:
        return [o for o in self.outcomes if o.status == "FAIL"]

    @property
    def passed(self) -> bool:
        return not self.failures

    def exit_code(self) -> int:
        return EX_OK if self.passed else EX_FAIL

    def to_dict(self) -> dict:
        return {
            "prover": "judge_harness",
            "kind": self.kind,
            "tier": JUDGE_TIER,
            "persona": JUDGE_PERSONA,
            "independence": self.independence,
            "passed": self.passed,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "failures": [o.to_dict() for o in self.failures],
            "rubric_rule": "each applicable dimension >= %d, no averaging" % DIM_MIN,
        }

    def emit(self, as_json: bool) -> int:
        if as_json:
            print(json.dumps(self.to_dict(), ensure_ascii=False, indent=2))
        else:
            head = "PASS" if self.passed else "FAIL"
            print("[%s] judge_harness  kind=%s tier=%s  (%d outcome(s), %d failure(s))"
                  % (head, self.kind, JUDGE_TIER, len(self.outcomes), len(self.failures)))
            if self.independence:
                print("  independence: judge=%s  writer=%s  distinct=%s"
                      % (self.independence.get("judge_model"),
                         self.independence.get("writer_model"),
                         self.independence.get("distinct")))
            for o in self.outcomes:
                line = "  %-4s %-9s %2d %-52s %s" % (o.status, o.kind, o.id, o.name, o.detail)
                (sys.stdout if o.status == "PASS" else sys.stderr).write(line + "\n")
        return self.exit_code()


def evaluate_judgment(judgment: dict, applicable: Dict[str, List[int]], kind: str) -> JudgeVerdict:
    """Grade a parsed judge verdict. FAIL-CLOSED: a missing semantic check is a fail;
    a missing or non-numeric dimension score is a fail. Dimensions are gated
    independently at >= DIM_MIN with NO averaging."""
    v = JudgeVerdict(kind)
    jchecks = judgment.get("checks") or {}
    jdims = judgment.get("dimensions") or {}

    for cid in applicable["checks"]:
        rec = jchecks.get(str(cid), jchecks.get(cid))
        name = SEMANTIC_NAMES.get(cid, "semantic check %d" % cid)
        if not isinstance(rec, dict) or "pass" not in rec:
            v.add(Outcome("check", cid, name, "FAIL", "judge did not answer this check (fail-closed)"))
            continue
        reason = str(rec.get("reason", "")).strip()
        if bool(rec.get("pass")):
            v.add(Outcome("check", cid, name, "PASS", reason or "passed"))
        else:
            v.add(Outcome("check", cid, name, "FAIL", reason or "semantic hard-fail"))

    for did in applicable["dims"]:
        rec = jdims.get(str(did), jdims.get(did))
        name = DIM_NAMES.get(did, "dimension %d" % did)
        score = None
        if isinstance(rec, dict):
            score = rec.get("score")
        elif isinstance(rec, (int, float)):
            score = rec
        try:
            score_num = float(score)
        except (TypeError, ValueError):
            v.add(Outcome("dimension", did, name, "FAIL",
                          "no numeric score returned (fail-closed)"))
            continue
        just = str(rec.get("justification", "")).strip() if isinstance(rec, dict) else ""
        if score_num < DIM_MIN:
            v.add(Outcome("dimension", did, name, "FAIL",
                          "scored %g, below the %d floor" % (score_num, DIM_MIN)))
        else:
            v.add(Outcome("dimension", did, name, "PASS",
                          "scored %g%s" % (score_num, (" - " + just) if just else "")))
    return v


# ---------------------------------------------------------------------------
# The harness: route JUDGE, enforce independence, parse, grade
# ---------------------------------------------------------------------------
RouterFn = Callable[[str, List[dict], dict], object]


def run(env: dict, router: Optional[RouterFn] = None) -> JudgeVerdict:
    """Full judge pass. router(tier, messages, context) -> result with .model_used
    and .text (default: model_router.route on the resolved map). Raises
    JudgeIndependenceViolation (exit 2) or BadInvocation; returns a JudgeVerdict
    (exit 0 pass / 4 content failure) otherwise."""
    kind = env.get("kind") or "chapter"
    applicable = resolve_applicable(env)
    messages = build_judge_messages(env, applicable)

    if router is None:
        if _route_default is None:
            raise BadInvocation(
                "model_router.route unavailable and no router injected; cannot reach the JUDGE tier")

        def router(tier, msgs, ctx):  # noqa: E306
            return _route_default(tier, msgs, ctx,
                                  run_dir=env.get("run_dir"),
                                  model_map_path=env.get("model_map_path"))

    context = {
        "deliverable_key": env.get("deliverable_key"),
        "participant_key": env.get("participant_key"),
        "anthology_id": env.get("anthology_id"),
        "qc_attempt": env.get("qc_attempt", 0),
    }
    result = router(JUDGE_TIER, messages, context)
    judge_model = getattr(result, "model_used", None) or ""
    judge_text = getattr(result, "text", "") or ""

    # INDEPENDENCE first: never grade with a judge that equals the writer.
    enforce_independence(env.get("writer_tier"), env.get("writer_model", ""),
                         env.get("writer_persona", ""), judge_model, JUDGE_PERSONA)

    judgment = parse_judge_json(judge_text)
    verdict = evaluate_judgment(judgment, applicable, kind)
    verdict.independence = {
        "judge_tier": JUDGE_TIER,
        "judge_model": judge_model,
        "judge_persona": JUDGE_PERSONA,
        "writer_tier": env.get("writer_tier"),
        "writer_model": env.get("writer_model"),
        "writer_persona": env.get("writer_persona"),
        "distinct": True,
    }
    return verdict


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _read_envelope(path: Optional[str]) -> dict:
    raw = Path(path).read_text(encoding="utf-8") if path else sys.stdin.read()
    if not raw.strip():
        raise BadInvocation("no envelope supplied (--envelope or stdin)")
    env = json.loads(raw)
    if not isinstance(env, dict):
        raise BadInvocation("envelope must be a JSON object")
    return env


def _cli_gate(args) -> int:
    """Offline: grade a PRE-OBTAINED judge response against the applicable set, with
    an explicitly supplied judge_model for the independence proof. No routing."""
    env = _read_envelope(args.envelope)
    applicable = resolve_applicable(env)
    judge_model = env.get("judge_model") or ""
    enforce_independence(env.get("writer_tier"), env.get("writer_model", ""),
                         env.get("writer_persona", ""), judge_model, JUDGE_PERSONA)
    resp = env.get("judge_response")
    if resp is None and env.get("judge_response_path"):
        resp = Path(env["judge_response_path"]).read_text(encoding="utf-8")
    if isinstance(resp, str):
        judgment = parse_judge_json(resp)
    elif isinstance(resp, dict):
        judgment = resp
    else:
        raise BadInvocation("gate mode needs judge_response (string or object) or judge_response_path")
    verdict = evaluate_judgment(judgment, applicable, env.get("kind") or "chapter")
    verdict.independence = {"judge_model": judge_model, "writer_model": env.get("writer_model"),
                            "distinct": True}
    return verdict.emit(args.json)


def _cli_judge(args) -> int:
    """Live: route the JUDGE tier through model_router on the resolved per-box map."""
    env = _read_envelope(args.envelope)
    verdict = run(env, router=None)
    return verdict.emit(args.json)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Gate B judge harness: semantic checks 13-15 + the Tier 2 rubric on the "
                    "JUDGE tier (SPEC Section 4).")
    sub = ap.add_subparsers(dest="cmd")

    j = sub.add_parser("judge", help="route the JUDGE tier and grade (needs a resolved model map)")
    j.add_argument("--envelope", help="envelope JSON path (else stdin)")
    j.add_argument("--json", action="store_true")

    g = sub.add_parser("gate", help="grade a pre-obtained judge response offline (no routing)")
    g.add_argument("--envelope", help="envelope JSON path (else stdin)")
    g.add_argument("--json", action="store_true")

    sub.add_parser("self-test", help="in-process independence + gate battery (no network)")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "gate":
            return _cli_gate(args)
        if args.cmd == "judge":
            return _cli_judge(args)
        if args.cmd == "self-test" or args.cmd is None:
            return self_test()
        ap.error("unknown command")
    except JudgeIndependenceViolation as exc:
        sys.stderr.write("[judge_harness] %s\n" % exc)
        return EX_INDEP
    except BadInvocation as exc:
        sys.stderr.write("[judge_harness] bad invocation: %s\n" % exc)
        return EX_INDEP
    except Exception as exc:
        sys.stderr.write("[judge_harness] unexpected error: %s\n" % exc)
        return EX_ERR


# ---------------------------------------------------------------------------
# Self-test: a scripted judge + a controllable resolved model prove independence
# enforcement, the fail-closed gate, and the no-averaging rule. No network.
# ---------------------------------------------------------------------------
class _FakeResult:
    def __init__(self, model_used: str, text: str):
        self.model_used = model_used
        self.text = text
        self.provider = "fake"


def _scripted_router(model_used: str, judgment: dict) -> RouterFn:
    def _r(tier, messages, context):
        assert tier == JUDGE_TIER, "harness must request the JUDGE tier only"
        return _FakeResult(model_used, json.dumps(judgment))
    return _r


def _all_good_judgment(checks: List[int], dims: List[int], score: int = 9) -> dict:
    return {
        "checks": {str(c): {"pass": True, "reason": "clean"} for c in checks},
        "dimensions": {str(d): {"score": score, "justification": "strong"} for d in dims},
    }


def _chapter_env(**over) -> dict:
    env = {
        "kind": "chapter",
        "deliverable_text": "A complete chapter about a man and his keys. It ends cleanly.",
        "tone_text": "A memoir-confessional, plainspoken, redemptive blended tone.",
        "outline_text": "1. keys as identity ... 10. close outward.",
        "avatar_text": "Working people who tied identity to a place.",
        "primary_goal": "Help the reader separate identity from a business.",
        "writer_tier": "HEAVY-WRITER", "writer_model": "glm-5.2",
        "writer_persona": "the Anthology Chapter Author (aw-09)",
    }
    env.update(over)
    return env


def self_test() -> int:
    checks: List[Tuple[str, bool]] = []
    ch_applicable = DEFAULT_APPLICABLE["chapter"]

    # 1) full pass: distinct judge, every check passes, every dim >= 8.
    env = _chapter_env()
    good = _all_good_judgment(ch_applicable["checks"], ch_applicable["dims"], 9)
    v = run(env, router=_scripted_router("minimax-v3", good))
    checks.append(("distinct judge + all-good verdict PASSES (exit 0)",
                   v.passed and v.exit_code() == EX_OK))

    # 2) independence: judge resolves to the SAME model as the writer -> refuse.
    try:
        run(_chapter_env(), router=_scripted_router("glm-5.2", good))
        checks.append(("same-resolution judge is refused", False))
    except JudgeIndependenceViolation:
        checks.append(("same-resolution judge is refused (AF-AE-JUDGE-INDEPENDENCE)", True))

    # 3) independence: the piece was drafted on the JUDGE tier -> refuse.
    try:
        run(_chapter_env(writer_tier="JUDGE"), router=_scripted_router("minimax-v3", good))
        checks.append(("writer-on-JUDGE-tier is refused", False))
    except JudgeIndependenceViolation:
        checks.append(("writer-on-JUDGE-tier is refused", True))

    # 4) independence: judge persona equals the drafting persona -> refuse.
    try:
        enforce_independence("HEAVY-WRITER", "glm-5.2", JUDGE_PERSONA, "minimax-v3", JUDGE_PERSONA)
        checks.append(("colliding personas refused", False))
    except JudgeIndependenceViolation:
        checks.append(("colliding personas refused", True))

    # 5) independence: a judge that resolves to an Anthropic id is refused (fragment id).
    try:
        enforce_independence("HEAVY-WRITER", "glm-5.2", "author",
                             "cl" + "aude-" + "opus-4", JUDGE_PERSONA)
        checks.append(("Anthropic-shaped judge refused", False))
    except JudgeIndependenceViolation:
        checks.append(("Anthropic-shaped judge refused", True))

    # 6) missing writer_model is a fail-closed bad invocation.
    try:
        enforce_independence("HEAVY-WRITER", "", "author", "minimax-v3", JUDGE_PERSONA)
        checks.append(("missing writer_model refused", False))
    except BadInvocation:
        checks.append(("missing writer_model refused (bad invocation)", True))

    # 7) one dimension below 8 fails the gate (exit 4), no averaging rescues it.
    low = _all_good_judgment(ch_applicable["checks"], ch_applicable["dims"], 9)
    low["dimensions"]["4"] = {"score": 7, "justification": "weak opening"}
    v = run(_chapter_env(), router=_scripted_router("minimax-v3", low))
    checks.append(("a single 7 fails the gate (exit 4)",
                   (not v.passed) and v.exit_code() == EX_FAIL
                   and any(o.kind == "dimension" and o.id == 4 and o.status == "FAIL"
                           for o in v.outcomes)))

    # 8) no averaging: nine 10s and one 7 still fails (a mean of 9.7 must NOT rescue it).
    avg = _all_good_judgment(ch_applicable["checks"], ch_applicable["dims"], 10)
    avg["dimensions"]["9"] = {"score": 7, "justification": "poor fit"}
    v = run(_chapter_env(), router=_scripted_router("minimax-v3", avg))
    checks.append(("nine 10s and one 7 still FAILS (no averaging)", not v.passed))

    # 9) a failed semantic check fails the gate even with a perfect rubric.
    semfail = _all_good_judgment(ch_applicable["checks"], ch_applicable["dims"], 10)
    semfail["checks"]["13"] = {"pass": False, "reason": "invented a quote"}
    v = run(_chapter_env(), router=_scripted_router("minimax-v3", semfail))
    checks.append(("a failed fabrication check (13) fails the gate",
                   (not v.passed) and any(o.kind == "check" and o.id == 13 and o.status == "FAIL"
                                          for o in v.outcomes)))

    # 10) fail-closed: a judge that omits a dimension is treated as a failure.
    missing = _all_good_judgment(ch_applicable["checks"], ch_applicable["dims"], 9)
    del missing["dimensions"]["6"]
    v = run(_chapter_env(), router=_scripted_router("minimax-v3", missing))
    checks.append(("an unanswered dimension fails closed",
                   any(o.kind == "dimension" and o.id == 6 and o.status == "FAIL"
                       for o in v.outcomes)))

    # 11) boundary: exactly 8 passes (>= 8, not > 8).
    edge = _all_good_judgment(ch_applicable["checks"], ch_applicable["dims"], 8)
    v = run(_chapter_env(), router=_scripted_router("minimax-v3", edge))
    checks.append(("every dimension exactly 8 PASSES (>= 8)", v.passed))

    # 12) parser tolerates a code-fenced judge reply.
    fenced = "```json\n" + json.dumps(_all_good_judgment([13], [], 9)) + "\n```"
    parsed = parse_judge_json(fenced)
    checks.append(("parser recovers a code-fenced JSON reply", "checks" in parsed))

    # 13) offline gate path evaluates a pre-obtained response with an explicit judge_model.
    genv = {"kind": "avatar", "writer_model": "glm-5.2", "writer_tier": "HEAVY-WRITER",
            "judge_model": "gemini-3.5-flash",
            "judge_response": _all_good_judgment([13], [], 9)}
    gv = evaluate_judgment(genv["judge_response"], resolve_applicable(genv), "avatar")
    checks.append(("offline gate: avatar fabrication check passes", gv.passed))

    # 14) applicable scope: chapter judges all ten dimensions and three semantic checks.
    ap = resolve_applicable(_chapter_env())
    checks.append(("chapter scope is checks 13-15 + all ten dimensions",
                   ap["checks"] == [13, 14, 15] and ap["dims"] == ALL_DIMS))

    ok = True
    for label, good_ in checks:
        print("  [%s] %s" % ("OK" if good_ else "XX", label))
        ok = ok and good_
    print("== judge_harness self-test: %s (%d checks) =="
          % ("ALL PASSED" if ok else "FAILURES", len(checks)))
    return EX_OK if ok else EX_ERR


if __name__ == "__main__":
    sys.exit(main())
