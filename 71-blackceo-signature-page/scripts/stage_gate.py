#!/usr/bin/env python3
"""Skill 71 mandatory stage gate.

Commands:
  init <run_dir>                require intake.json, create private/state.json + private/receipts/
  check <run_dir> <stage>       gate for STARTING a stage (exit 0 = may start)
  close <run_dir> <stage>       gate for CLOSING a stage (exit 0 = closed; records hashes)
  report <run_dir>              write REPORT.md (exit 0 only if every required stage is closed)

The gate owns the stage list (references/stage-contract.json). It never trusts a
validator result written by an agent: close re-runs every validator itself.
"""
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = Path(os.environ.get(
    "STAGE_GATE_CONTRACT",
    str(SKILL_ROOT / "references" / "stage-contract.json"),
))
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
STAGES = CONTRACT["stages"]
ORDER = CONTRACT["stage_order"]

MUST_SUPPLY_STRINGS = ("TREVOR_MUST_SUPPLY", "CLIENT_MUST_SUPPLY")
RECEIPT_STATUS = {"pass", "fail", "blocked", "not_authorized"}
STATUS_LINE = {
    "pass": "PASS",
    "fail": "FAIL",
    "blocked": "BLOCKED",
    "not_authorized": "NOT AUTHORIZED",
}
NOT_RUN = "NOT RUN"
WARN = "WARN"

# Validator tokens handled inside this script (no external script required).
GATE_BUILTINS = {"gate:must_supply", "gate:brand_fonts", "gate:noop"}


def fail_exit(lines):
    print("FAIL")
    for line in lines:
        print(f"- {line}")
    return 1


def load_contract_stage(stage):
    spec = STAGES.get(stage)
    if spec is None:
        return None, [f"unknown stage {stage!r}; contract has: {', '.join(ORDER)}"]
    return spec, []


def load_state(run_dir):
    state_path = run_dir / "private" / "state.json"
    if not state_path.exists():
        return {"stages": {}, "receipts": {}}, state_path
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: unreadable state.json: {exc}")
        sys.exit(2)
    data.setdefault("stages", {})
    data.setdefault("receipts", {})
    return data, state_path


def save_state(run_dir, state):
    state_path = run_dir / "private" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state_path


def brand_path_for(run_dir):
    """Resolve the run's brand file. intake.json names it; fallback is the skill's own BlackCEO file."""
    intake = run_dir / "intake.json"
    if intake.exists():
        try:
            data = json.loads(intake.read_text(encoding="utf-8"))
            bf = data.get("brand_file")
            if bf:
                p = Path(bf)
                return p if p.is_absolute() else (run_dir / bf)
        except Exception:
            pass
    return SKILL_ROOT / "assets" / "brand" / "blackceo-brand.json"


# Test hook: a run folder may pin its own brand file for gate builtins.
def brand_path_for_checked(run_dir):
    pinned = run_dir / "private" / "brand.json"
    if pinned.exists():
        return pinned
    return brand_path_for(run_dir)


def brand_must_supply(brand_file):
    try:
        text = brand_file.read_text(encoding="utf-8")
    except Exception as exc:
        return [f"brand file unreadable: {brand_file}: {exc}"]
    found = [s for s in MUST_SUPPLY_STRINGS if s in text]
    if not found:
        return []
    missing_keys = find_must_supply_keys(brand_file)
    if fonts_derivable(brand_file):
        non_font = [k for k in missing_keys if not k.startswith("fonts")]
        if not non_font:
            return []  # only fonts.* missing under derive-document: not blocked
        missing_keys = non_font
    return [f"brand file {brand_file} contains {', '.join(found)} values: "
            f"missing brand facts must be supplied by the owner before intake closes. "
            f"Missing keys: " + ", ".join(missing_keys)]


def find_must_supply_keys(brand_file):
    try:
        data = json.loads(brand_file.read_text(encoding="utf-8"))
    except Exception:
        return ["(file not valid JSON)"]
    missing = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str) and any(s in node for s in MUST_SUPPLY_STRINGS):
            missing.append(path)

    walk(data, "")
    return missing or ["(none located)"]


def fonts_derivable(brand_file):
    """True when the brand file's font_policy authorizes derive-document."""
    try:
        data = json.loads(brand_file.read_text(encoding="utf-8"))
    except Exception:
        return False
    policy = data.get("font_policy") or {}
    return (isinstance(policy, dict)
            and policy.get("when_brand_fonts_missing") == "derive-document")


def resolve_brand_placeholder(cmd, run_dir, stage, receipt):
    """Substitute {run_dir}/{brand}/{file}/{sauce} in a validator command.

    Per-file validators ({file} in the template) return ("__per_file__", cmd, files)
    with every OTHER placeholder already substituted, so run_validators only has to
    swap {file} once per file.
    """
    brand = brand_path_for(run_dir)
    spec = STAGES[stage]
    substitutions = {
        "{run_dir}": str(run_dir),
        "{brand}": str(brand),
    }
    files = []
    per_file = spec.get("per_file_glob")
    if per_file:
        count_of = spec.get("count_of")
        needed = 1
        if count_of:
            needed = count_inventory(run_dir, count_of)
        glob_matches = sorted(run_dir.glob(per_file))
        if needed > 0:
            if len(glob_matches) < needed:
                return None, [f"expected {needed} files matching {per_file}, found {len(glob_matches)}"]
            elif len(glob_matches) > needed:
                return None, [f"expected {needed} files matching {per_file}, found {len(glob_matches)}"]
        if receipt and "validator_files" in receipt:
            files = [str(run_dir / f) for f in receipt.get("validator_files", [])]
        elif glob_matches:
            files = [str(p) for p in glob_matches]
    # The visual bible decides the sauce flag; it must be resolved BEFORE the
    # per-file early return so {sauce} reaches per-file validator commands too.
    sauce = ""
    bible_path = run_dir / "visual-mockup" / "page-visual-bible.json"
    if bible_path.exists():
        try:
            bible = json.loads(bible_path.read_text(encoding="utf-8"))
            sauce = "--sauce-only" if bible.get("selection_mode") == "SECRET_SAUCE_ONLY" else ""
        except Exception:
            sauce = ""
    # Always substitute {sauce}, even when empty: an unsubstituted token would be
    # shipped to the validator as a literal argument.
    substitutions["{sauce}"] = sauce
    if "{file}" in cmd:
        if not files:
            return None, [f"per-file validator has no files to validate "
                          f"(glob {per_file!r} matched none and the receipt lists none)"]
        # Per-file validators run per file; {file} is replaced once per file -> expand to N commands.
        per_file_cmd = cmd
        for k, v in substitutions.items():
            per_file_cmd = per_file_cmd.replace(k, v)
        return ("__per_file__", per_file_cmd, files), []
    if files:
        substitutions["{file}"] = files[0]
    for k, v in substitutions.items():
        cmd = cmd.replace(k, v)
    return cmd, []


def count_inventory(run_dir, rel):
    inv = run_dir / rel
    if not inv.exists():
        return 0
    try:
        data = json.loads(inv.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if isinstance(data, list):
        return len(data)
    for key in ("images", "inventory", "entries", "slots"):
        if isinstance(data.get(key), list):
            return len(data[key])
    return 0


def artifacts_for(run_dir, stage):
    """Return (globs_ok, missing_lines, found_counts)."""
    spec = STAGES[stage]
    problems = []
    counts = {}
    for art in spec.get("artifacts", []):
        pattern, min_count = art["glob"], art.get("min_count", 1)
        matches = sorted(run_dir.glob(pattern))
        counts[pattern] = len(matches)
        if len(matches) < min_count:
            problems.append(
                f"stage {stage}: artifact glob {pattern!r} matched {len(matches)} file(s), "
                f"requires {min_count}"
            )
    return problems, counts


def receipt_status(run_dir, stage):
    """Return (status, receipt_dict_or_None, lines). status '' when no receipt."""
    rp = run_dir / "private" / "receipts" / f"{stage}.json"
    if not rp.exists():
        return "", None, []
    try:
        receipt = json.loads(rp.read_text(encoding="utf-8"))
    except Exception as exc:
        return "fail", None, [f"receipt {rp} unreadable: {exc}"]
    status = receipt.get("status")
    if status not in RECEIPT_STATUS:
        return "fail", receipt, [f"receipt {rp} has invalid status {status!r}"]
    return status, receipt, []


def check_requires(run_dir, stage):
    """check command: the FULL transitive dependency chain is closed with matching
    hashes; requires_artifacts exist. Every unclosed transitive dep is named."""
    lines = []
    spec = STAGES[stage]
    state, _ = load_state(run_dir)

    # Transitive closure of depends_on, in contract order.
    seen = []
    stack = list(spec.get("depends_on", []))
    while stack:
        dep = stack.pop(0)
        if dep in seen:
            continue
        seen.append(dep)
        stack.extend(STAGES.get(dep, {}).get("depends_on", []))

    for dep in seen:
        dep_state = state.get("stages", {}).get(dep, {})
        if dep_state.get("status") != "closed":
            lines.append(f"stage {stage} cannot start: dependency {dep} is not closed "
                         f"(status: {dep_state.get('status', 'not closed')})")
            continue
        lines.extend(verify_dep_receipt(run_dir, dep, state))

    for rel in spec.get("requires_artifacts", []):
        p = run_dir / rel
        if not p.exists():
            lines.append(f"stage {stage} cannot start: required artifact missing: {rel}")

    return lines


def verify_dep_receipt(run_dir, dep, state=None):
    """Verify a closed dependency: receipt status pass/not_authorized, and every
    close-recorded artifact hash still matches the file on disk."""
    if state is None:
        state, _ = load_state(run_dir)
    lines = []
    status, receipt, rlines = receipt_status(run_dir, dep)
    lines.extend(rlines)
    if not status:
        lines.append(f"stage {stage_name_placeholder()} cannot start: dependency {dep} has no receipt at "
                     f"private/receipts/{dep}.json")
        return lines
    if status == "fail":
        lines.append(f"stage dependency {dep} receipt status is 'fail'")
        return lines
    if status == "blocked":
        lines.append(f"dependency {dep} is BLOCKED")
        return lines
    if status == "not_authorized":
        if not STAGES[dep].get("may_be_not_authorized", False):
            lines.append(f"dependency {dep} is not_authorized "
                         f"but the contract does not allow it for that stage")
        return lines
    # status == pass: verify hashes recorded at close (state.json) still match disk.
    dep_entry = state.get("stages", {}).get(dep, {})
    recorded_hashes = dep_entry.get("artifact_hashes") or {}
    if not recorded_hashes:
        lines.append(f"dependency {dep}: closed without recorded artifact hashes; "
                     f"re-close the stage")
    for rel, recorded in recorded_hashes.items():
        p = run_dir / rel
        if not p.exists():
            lines.append(f"dependency {dep}: recorded artifact missing: {rel}")
            continue
        actual = sha256_file(p)
        if actual != recorded:
            lines.append(f"dependency {dep}: artifact changed after close: {rel} "
                         f"(recorded {recorded[:12]}... != on-disk {actual[:12]}...)")
    return lines


def stage_name_placeholder():
    return "(calling stage)"


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def run_validators(run_dir, stage, receipt):
    """Re-run every validator; return list of failure lines."""
    spec = STAGES[stage]
    failures = []
    for raw in spec.get("validators", []):
        resolved, rlines = resolve_brand_placeholder(raw, run_dir, stage, receipt)
        failures.extend(rlines)
        if resolved is None:
            continue
        if isinstance(resolved, tuple) and resolved[0] == "__per_file__":
            _, cmd_tpl, files = resolved
            for fpath in files:
                cmd = cmd_tpl.replace("{file}", fpath)
                line = run_one_validator(cmd, run_dir)
                if line:
                    failures.append(line)
        else:
            line = run_one_validator(resolved, run_dir)
            if line:
                failures.append(line)
    return failures


def run_one_validator(cmd, run_dir):
    """Run one validator command; return None on exit 0 else a failure line."""
    parts = shlex.split(cmd)
    if not parts:
        return "validator failed: empty command (nothing to run)"
    if parts[0] in GATE_BUILTINS:
        return run_builtin(parts[0], parts[1:], run_dir)
    # Relative script paths resolve against the skill root, not the run folder.
    p0 = Path(parts[0])
    if not p0.is_absolute() and (SKILL_ROOT / parts[0]).exists():
        parts[0] = str(SKILL_ROOT / parts[0])
    try:
        proc = subprocess.run(parts, capture_output=True, text=True, timeout=600,
                              cwd=str(SKILL_ROOT))
    except subprocess.TimeoutExpired:
        return f"validator timed out: {cmd}"
    if proc.returncode != 0:
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        detail = (out or err or "(no output)")[:600]
        return f"validator exit {proc.returncode}: {cmd}\n    {detail}"
    return None


def run_builtin(name, args, run_dir):
    """Built-in gate validators."""
    if name == "gate:must_supply":
        brand = brand_path_for_checked(run_dir)
        problems = brand_must_supply(brand)
        if problems:
            return "gate:must_supply: " + "; ".join(problems)
        return None
    if name == "gate:noop":
        # Test-only builtin: always passes.
        return None
    if name == "gate:brand_fonts":
        font_map = None
        brand = None
        i = 0
        while i < len(args):
            if args[i] == "--font-map" and i + 1 < len(args):
                font_map = Path(args[i + 1])
            elif args[i] == "--brand" and i + 1 < len(args):
                brand = Path(args[i + 1])
            i += 1
        if brand is None:
            brand = brand_path_for_checked(run_dir)
        if font_map is None or brand is None:
            return "gate:brand_fonts: missing --font-map or --brand"
        try:
            fonts = json.loads(font_map.read_text(encoding="utf-8"))
            branddata = json.loads(brand.read_text(encoding="utf-8"))
        except Exception as exc:
            return f"gate:brand_fonts: unreadable input: {exc}"
        allowed = set()
        for v in (branddata.get("fonts") or {}).values():
            allowed.add(str(v))
        banned = set(branddata.get("banned_fonts") or [])
        used = set()
        def collect(node):
            if isinstance(node, dict):
                for v in node.values():
                    collect(v)
            elif isinstance(node, list):
                for v in node:
                    collect(v)
            elif isinstance(node, str):
                used.add(node)
        collect(fonts.get("fonts", fonts))
        derived = fonts_derivable(brand) and any(
            str(v) in MUST_SUPPLY_STRINGS for v in allowed)
        placeholders = sorted(f for f in used if f in MUST_SUPPLY_STRINGS)
        if placeholders:
            return ("gate:brand_fonts: font map still carries placeholder values: "
                    + ", ".join(placeholders)
                    + "; font_policy derive-document requires real derived families")
        bad = sorted(f for f in used if f not in allowed and f not in ("", "-"))
        if bad and not derived:
            return ("gate:brand_fonts: fonts not in the brand file: " + ", ".join(bad)
                    + "; brand fonts: " + ", ".join(sorted(allowed)))
        banned_used = sorted(f for f in used if f in banned)
        if banned_used:
            return "gate:brand_fonts: banned fonts used: " + ", ".join(banned_used)
        return None
    return f"unknown builtin validator {name}"


def check_review_scores(run_dir, stage, receipt):
    """Review/score requirements for close."""
    spec = STAGES[stage]
    failures = []
    author = receipt.get("author_agent")
    reviewer = receipt.get("reviewer_agent")
    if spec.get("review_required"):
        if not author:
            failures.append(f"stage {stage}: receipt missing author_agent")
        if not reviewer:
            failures.append(f"stage {stage}: review_required but receipt missing reviewer_agent")
        elif author and reviewer == author:
            failures.append(f"stage {stage}: reviewer_agent equals author_agent "
                            f"({author!r}); review must be independent")
        # review_covers: every matched artifact must be listed by name in review_files with a score
        covers = spec.get("review_covers")
        if covers and author and reviewer and reviewer != author:
            matched = sorted(run_dir.glob(covers))
            listed = receipt.get("review_files") or {}
            for p in matched:
                rel = str(p.relative_to(run_dir))
                entry = listed.get(rel)
                if not isinstance(entry, dict) or entry.get("score") is None:
                    failures.append(
                        f"stage {stage}: review must list every {covers} file with a score; "
                        f"missing or unscored: {rel}"
                    )
    min_scores = spec.get("min_scores")
    if min_scores:
        scores = receipt.get("scores") or {}
        if not scores:
            failures.append(f"stage {stage}: min_scores required but receipt.scores is empty")
        else:
            each = min_scores.get("each")
            if each is not None:
                bad = [k for k, v in scores.items()
                       if not isinstance(v, (int, float)) or isinstance(v, bool) or v < each]
                if bad:
                    failures.append(
                        f"stage {stage}: scores below minimum {each}: " +
                        ", ".join(f"{k}={scores[k]}" for k in sorted(bad))
                    )
            avg = min_scores.get("average")
            if avg is not None:
                vals = [v for v in scores.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
                if not vals or (sum(vals) / len(vals)) < avg:
                    shown = (sum(vals) / len(vals)) if vals else 0
                    failures.append(f"stage {stage}: average score {shown:.2f} below minimum {avg}")
    return failures


def check_cost(run_dir, stage, receipt):
    """Paid-generation stages must carry cost {provider, credits_before, credits_after}."""
    spec = STAGES[stage]
    if not spec.get("cost_required"):
        return []
    cost = receipt.get("cost")
    problems = []
    if not isinstance(cost, dict):
        problems.append(f"stage {stage}: image stage receipt missing cost "
                        f"{{provider, credits_before, credits_after}}")
    else:
        for key in ("provider", "credits_before", "credits_after"):
            if key not in cost:
                problems.append(f"stage {stage}: receipt.cost missing {key}")
    return problems


# Image generation route (references/kie-generation-route.md): policy owner, then Skill 74 transport.
# skill -> (policy owner, cost provider). Agnes is allowed only when the client selected it.
TRANSPORTS = {"74-kie-live-adapter": ("66-kie-image", "kie"), "63-agnes-image": ("63-agnes-image", "agnes")}
MODEL_SOURCES = ("latest-family", "explicit-request", "department-pin", "legacy-ratio-route")
BAD_IDS = {"", "-", "none", "null", "nil", "n/a", "na", "tbd", "todo", "native", "placeholder",
           "fake", "dummy", "test", "unknown", "0"}
# AGENTS.md N43 ratio rules (kie-common-rules.md rule 11). Ratios only; model ids come from Skill 66.
N43_SUBSTITUTIONS = {"5:4": "4:3", "4:5": "3:4", "2:1": "16:9", "1:2": "9:16"}
N43_LEGACY_ONLY = ("3:1", "1:3", "9:21")


def _real_id(value):
    return isinstance(value, str) and value.strip().lower() not in BAD_IDS


def _ratio_problem(who, task):
    req, gen, src = task.get("requested_ratio"), task.get("generated_ratio"), task.get("model_source")
    if not (isinstance(req, str) and isinstance(gen, str) and req and gen):
        return f"{who}: requested_ratio and generated_ratio are required"
    if req in N43_LEGACY_ONLY:
        if gen != req or src not in ("legacy-ratio-route", "explicit-request", "department-pin"):
            return f"{who}: N43 sends {req} to the legacy route only (generated_ratio {gen!r}, model_source {src!r})"
    elif src in ("explicit-request", "department-pin"):
        pass  # an explicit request or a pin overrides the default's ratio substitutions
    elif gen != N43_SUBSTITUTIONS.get(req, req):
        return (f"{who}: N43 ratio rule violated: requested {req}, generated {gen}, "
                f"expected {N43_SUBSTITUTIONS.get(req, req)}")
    return None


def check_transport(run_dir, stage, receipt):
    """Image stages must prove the Skill 66/67 -> Skill 74 route (or an explicit Agnes route)."""
    spec = STAGES[stage]
    if not spec.get("transport_required"):
        return []
    t = receipt.get("transport")
    if not isinstance(t, dict):
        return [f"stage {stage}: receipt missing transport block (references/kie-generation-route.md section 3)"]
    skill = t.get("skill")
    if skill not in TRANSPORTS:
        return [f"stage {stage}: transport.skill {skill!r} is not an approved route {sorted(TRANSPORTS)}; "
                f"a hand-rolled createTask is not"]
    policy, provider = TRANSPORTS[skill]
    problems = []
    if t.get("policy") != policy:
        problems.append(f"stage {stage}: transport.policy must be {policy!r}, got {t.get('policy')!r}")
    cost = receipt.get("cost")
    if isinstance(cost, dict) and cost.get("provider") != provider:
        problems.append(f"stage {stage}: cost.provider must be {provider!r} for {skill}, got {cost.get('provider')!r}")
    if skill == "74-kie-live-adapter" and t.get("mode") != "active":
        problems.append(f"stage {stage}: transport.mode must be 'active' (shadow never dispatches), got {t.get('mode')!r}")
    files = sorted(str(p.relative_to(run_dir)) for p in run_dir.glob(spec.get("per_file_glob", "")) if p.is_file())
    tasks = t.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return problems + [f"stage {stage}: transport.tasks must list one entry per generated file"]
    got = sorted(str(x.get("file")) for x in tasks if isinstance(x, dict))
    if got != files:
        problems.append(f"stage {stage}: transport.tasks cover {got} but the stage has {files}")
    for i, x in enumerate(tasks):
        who = f"stage {stage}: transport.tasks[{i}] ({x.get('file') if isinstance(x, dict) else '?'})"
        if not isinstance(x, dict):
            problems.append(f"{who} is not an object")
            continue
        if skill != "74-kie-live-adapter":
            continue
        if not _real_id(x.get("task_id")):
            problems.append(f"{who}: task_id {x.get('task_id')!r} is missing or a placeholder")
        if x.get("preflight_ok") is not True:
            problems.append(f"{who}: preflight_ok must be true (balance covers price x 1.30)")
        if x.get("budget_exit") != 0:
            problems.append(f"{who}: budget_exit must be 0 (prompt-budget --check passed)")
        if not _real_id(x.get("model_id")):
            problems.append(f"{who}: model_id is missing")
        if x.get("model_source") not in MODEL_SOURCES:
            problems.append(f"{who}: model_source must be one of {list(MODEL_SOURCES)}")
        rp = _ratio_problem(who, x)
        if rp:
            problems.append(rp)
    return problems


def cmd_init(run_dir):
    intake = run_dir / "intake.json"
    if not intake.exists():
        return fail_exit([f"init requires {intake} (the intake stage writes it)"])
    state, _ = load_state(run_dir)
    (run_dir / "private" / "receipts").mkdir(parents=True, exist_ok=True)
    save_state(run_dir, state)
    print(f"PASS: run initialized at {run_dir}")
    print(f"  state: {run_dir / 'private' / 'state.json'}")
    print(f"  receipts dir: {run_dir / 'private' / 'receipts'}")
    return 0


def cmd_check(run_dir, stage):
    spec, errs = load_contract_stage(stage)
    if errs:
        return fail_exit(errs)
    failures = check_requires(run_dir, stage)
    if failures:
        return fail_exit(failures)
    print(f"PASS: stage {stage} may start (all dependencies closed with matching receipts and artifacts)")
    return 0


def cmd_close(run_dir, stage):
    spec, errs = load_contract_stage(stage)
    if errs:
        return fail_exit(errs)
    failures = []
    status, receipt, rlines = receipt_status(run_dir, stage)
    failures.extend(rlines)
    if not receipt:
        failures.append(f"stage {stage}: no receipt at private/receipts/{stage}.json; "
                        f"the stage's agents must write it before close")
    receipt_status_val = receipt.get("status") if receipt else None
    if receipt_status_val == "fail":
        failures.append(f"stage {stage}: receipt status is 'fail'; close refused")

    # Artifacts on disk
    art_problems, counts = artifacts_for(run_dir, stage)
    failures.extend(art_problems)

    # not_authorized path
    if receipt and receipt_status_val == "not_authorized":
        if not spec.get("may_be_not_authorized", False):
            failures.append(f"stage {stage}: not_authorized is not allowed for this stage")
        elif art_problems:
            failures.append(f"stage {stage}: not_authorized close still requires the stage's "
                            f"artifacts-or-receipt contract to be satisfied; matched: {counts}")
        if not failures:
            record_close(run_dir, stage, receipt, "not_authorized", counts)
            print(f"CLOSED (not_authorized): stage {stage} recorded in state.json")
            return 0

    if not failures:
        # Re-run validators
        failures.extend(run_validators(run_dir, stage, receipt))
        # Review / scores / cost
        failures.extend(check_review_scores(run_dir, stage, receipt))
        failures.extend(check_cost(run_dir, stage, receipt))
        failures.extend(check_transport(run_dir, stage, receipt))

    if failures:
        return fail_exit(failures)

    record_close(run_dir, stage, receipt, "pass", counts)
    print(f"CLOSED: stage {stage} (artifacts verified, validators re-run by the gate, "
          f"review and scores checked)")
    return 0


def record_close(run_dir, stage, receipt, status, counts):
    state, _ = load_state(run_dir)
    hashes = {}
    for art in STAGES[stage].get("artifacts", []):
        for p in sorted(run_dir.glob(art["glob"])):
            rel = str(p.relative_to(run_dir))
            if p.is_file():
                hashes[rel] = sha256_file(p)
    state["stages"][stage] = {
        "status": "closed",
        "receipt_status": status,
        "closed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "artifact_counts": counts,
        "artifact_hashes": hashes,
        "receipt": {
            "author_agent": receipt.get("author_agent"),
            "reviewer_agent": receipt.get("reviewer_agent"),
            "started_at": receipt.get("started_at"),
            "finished_at": receipt.get("finished_at"),
            "cost": receipt.get("cost"),
            "scores": receipt.get("scores"),
        },
    }
    state["receipts"][stage] = f"private/receipts/{stage}.json"
    save_state(run_dir, state)


def stage_line(run_dir, stage, state):
    spec = STAGES[stage]
    st = state.get("stages", {}).get(stage, {})
    rstatus, receipt, rlines = receipt_status(run_dir, stage)
    closed = st.get("status") == "closed"
    rstatus = receipt.get("status") if receipt else None
    if closed and rstatus == "pass":
        line = "PASS"
    elif closed and rstatus == "not_authorized":
        line = "NOT AUTHORIZED"
    elif closed:
        line = "FAIL"
    elif rstatus == "blocked":
        line = "BLOCKED"
    elif rstatus == "fail":
        line = "FAIL"
    elif rstatus == "not_authorized":
        line = "NOT AUTHORIZED"
    elif rstatus == "pass":
        line = "FAIL"  # receipt says pass but close never succeeded
    elif rstatus is None:
        line = NOT_RUN
    else:
        line = NOT_RUN
    return line


def collect_warnings(run_dir, state):
    warns = []
    intake = run_dir / "intake.json"
    test_run = False
    if intake.exists():
        try:
            data = json.loads(intake.read_text(encoding="utf-8"))
            test_run = bool(data.get("test_run"))
        except Exception:
            pass
    if test_run:
        warns.append("intake.test_run is true: placeholder warnings are allowed this run "
                     "(validate_page.py reports them as WARN, not FAIL)")
    # Uncalibrated grade thresholds
    brand = brand_path_for(run_dir)
    try:
        b = json.loads(brand.read_text(encoding="utf-8"))
        grade = b.get("grade") or {}
        if grade.get("min_mean_saturation") is None or grade.get("min_luma_std") is None:
            warns.append("image grade thresholds are uncalibrated (grade.min_mean_saturation / "
                         "grade.min_luma_std are null): validate_image_grade.py emitted "
                         "WARN measurements only")
    except Exception:
        warns.append(f"brand file unreadable for WARN scan: {brand}")
    return warns


def cmd_report(run_dir):
    state, _ = load_state(run_dir)
    now = datetime.now(timezone.utc)
    lines = []
    lines.append(f"# Skill 71 Run Report")
    lines.append("")
    lines.append(f"Generated by scripts/stage_gate.py report at {now.isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## Stages")
    lines.append("")
    lines.append("| Stage | Status | Closed at | Duration |")
    lines.append("|---|---|---|---|")
    durations = {}
    required_closed = True
    for stage in ORDER:
        line = stage_line(run_dir, stage, state)
        st = state.get("stages", {}).get(stage, {})
        closed_at = st.get("closed_at", "-")
        _, receipt, _ = receipt_status(run_dir, stage)
        receipt = receipt or {}
        dur = "-"
        started = receipt.get("started_at") if isinstance(receipt, dict) else None
        finished = receipt.get("finished_at") if isinstance(receipt, dict) else None
        if closed_at != "-" and started and finished:
            try:
                t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(finished.replace("Z", "+00:00"))
                secs = max(0, int((t1 - t0).total_seconds()))
                dur = f"{secs // 3600}h{secs % 3600 // 60:02d}m{secs % 60:02d}s"
                durations[stage] = secs
            except Exception:
                dur = "-"
        lines.append(f"| {stage} | {line} | {closed_at} | {dur} |")
        if line in ("FAIL", "BLOCKED", NOT_RUN):
            required_closed = False
    lines.append("")
    warns = collect_warnings(run_dir, state)
    lines.append("## WARNs")
    lines.append("")
    if warns:
        for w in warns:
            lines.append(f"- WARN: {w}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Cost")
    lines.append("")
    costs = {}
    for stage in ORDER:
        _, receipt, _ = receipt_status(run_dir, stage)
        if not isinstance(receipt, dict):
            continue
        cost = receipt.get("cost")
        if not isinstance(cost, dict):
            continue
        provider = str(cost.get("provider", "unknown"))
        before = cost.get("credits_before")
        after = cost.get("credits_after")
        if isinstance(before, (int, float)) and isinstance(after, (int, float)) \
                and not isinstance(before, bool) and not isinstance(after, bool):
            costs[provider] = costs.get(provider, 0.0) + (before - after)
    if costs:
        for provider, used in sorted(costs.items()):
            lines.append(f"- {provider}: {used:.2f} credits used (summed from receipts "
                         f"credits_before - credits_after)")
    else:
        lines.append("- (no cost data in receipts; NOT UNDETERMINED by assumption — "
                     "no image-stage receipt carried cost fields)")
    lines.append("")
    lines.append("## Slowest stages")
    lines.append("")
    if durations:
        for stage, secs in sorted(durations.items(), key=lambda kv: -kv[1])[:3]:
            lines.append(f"- {stage}: {secs // 3600}h{secs % 3600 // 60:02d}m{secs % 60:02d}s")
    else:
        lines.append("- (no stage durations recorded)")
    lines.append("")
    lines.append("## Compare sheets")
    lines.append("")
    compare_dir = run_dir / "responsive-html" / "compare"
    if compare_dir.exists():
        for p in sorted(compare_dir.glob("*.png")):
            lines.append(f"- {p}")
    else:
        lines.append("- (none; responsive-html not closed or compare_sheet.py not run)")
    lines.append("")

    overall = "RUN COMPLETE" if required_closed else "RUN INCOMPLETE"
    if not required_closed:
        missing = [s for s in ORDER
                   if stage_line(run_dir, s, state) in ("FAIL", "BLOCKED", NOT_RUN)]
        lines.append(f"**{overall}** — not closed: {', '.join(missing)}")
    else:
        lines.append(f"**{overall}**")
    report_path = run_dir / "REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {report_path}")
    print(f"OVERALL: {overall}")
    return 0 if required_closed else 1


def main():
    parser = argparse.ArgumentParser(description="Skill 71 mandatory stage gate.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init", help="initialize run state")
    p_init.add_argument("run_dir", type=Path)
    p_check = sub.add_parser("check", help="gate for starting a stage")
    p_check.add_argument("run_dir", type=Path)
    p_check.add_argument("stage")
    p_close = sub.add_parser("close", help="gate for closing a stage")
    p_close.add_argument("run_dir", type=Path)
    p_close.add_argument("stage")
    p_report = sub.add_parser("report", help="write REPORT.md")
    p_report.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    args.run_dir = args.run_dir.resolve()
    if not args.run_dir.exists():
        print(f"FAIL: run_dir does not exist: {args.run_dir}")
        return 2
    if args.cmd == "init":
        return cmd_init(args.run_dir)
    if args.cmd == "check":
        return cmd_check(args.run_dir, args.stage)
    if args.cmd == "close":
        return cmd_close(args.run_dir, args.stage)
    if args.cmd == "report":
        return cmd_report(args.run_dir)
    return 2


if __name__ == "__main__":
    sys.exit(main())
