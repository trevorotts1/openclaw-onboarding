#!/usr/bin/env python3
"""Skill 71 mandatory stage gate.

Commands:
  init <run_dir>                require intake.json, create private/state.json + private/receipts/
  check <run_dir> <stage>       gate for STARTING a stage (exit 0 = may start)
  close <run_dir> <stage>       gate for CLOSING a stage (exit 0 = closed; records hashes)
  check-item <run_dir> <stage> <item-id>   gate for STARTING one item of an itemized stage
  close-item <run_dir> <stage> <item-id>   gate for CLOSING one item of an itemized stage
  block-item <run_dir> <stage> <item-id> --reason <text>   record an item as blocked
  report <run_dir>              write REPORT.md (exit 0 only if every required stage is closed)

The gate owns the stage list (references/stage-contract.json). It never trusts a
validator result written by an agent: close re-runs every validator itself.
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import page_role  # noqa: E402  every page type's canonical copy spec (landing forms, thank-you)

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
GATE_BUILTINS = {"gate:must_supply", "gate:brand_fonts", "gate:intake_engine", "gate:intake_design_style", "gate:intake_page_kind", "gate:noop",
                 "gate:grade_calibrated", "gate:image_grade_full_set", "gate:copy_handoff"}


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
    data.setdefault("items", {})
    return data, state_path


def save_state(run_dir, state):
    state_path = run_dir / "private" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state_path


def design_board_start_failures(run_dir, stage):
    """SPF021: the design-board stage starts only on the client's resolved brand colors
    (resolution consumed from scripts/brand_colors.py through design_board.py)."""
    if stage != "design-board":
        return []
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import design_board
        design_board.brand_resolution(run_dir)
    except design_board.BoardError as exc:
        return [f"stage design-board cannot start: {exc}"]
    finally:
        sys.path.pop(0)
    return []


def brand_path_for(run_dir):
    """The run's brand file: the one scripts/brand_colors.py resolved (see brand_colors.brand_path)."""
    return _brand_colors().brand_path(run_dir)


def _brand_colors():
    """scripts/brand_colors.py (SPF019): the brand-color resolution every image stage passes."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import brand_colors
    finally:
        sys.path.pop(0)
    return brand_colors


def brand_color_failures(run_dir, stage):
    """Refusal lines when `stage` makes images and the client's brand colors are unresolved."""
    line = _brand_colors().failure(run_dir, stage)
    return [f"stage {stage}: {line}"] if line else []


def brand_path_for_checked(run_dir):
    """Gate builtins read the same resolved file as every other check (a run's private/brand.json
    pin counts only when brand_colors.resolve accepts it)."""
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


def resolve_brand_placeholder(cmd, run_dir, stage, receipt, as_argv=False):
    """Substitute {run_dir}/{brand}/{file}/{sauce} in a validator command.

    Per-file validators ({file} in the template) return a 4-tuple
    ("__per_file__", raw_template, files, substitutions): the template is left
    unsubstituted so the caller can tokenize once and substitute inside tokens,
    keeping a path that contains spaces in one argv entry.

    as_argv=True returns an already-tokenized argv list for the non-per-file
    case instead of a string, for the same reason (the gate runs it directly).
    """
    brand = brand_path_for(run_dir)
    spec = STAGES[stage]
    # S44-05: the substituted values are shell tokens, not raw text. A run
    # directory containing a space (or non-ASCII) must survive the
    # shlex.split in run_one_validator as ONE argv entry, so quote each
    # value before it enters the command string.
    substitutions = {
        "{run_dir}": str(run_dir),
        "{brand}": str(brand),
    }
    if "{copy_version}" in cmd or "{copy_spec}" in cmd:
        # S4 CR-2 / S1 copy wiring: the copy spec path is selected by the
        # intake's copy_version. No recorded selection is a gate failure,
        # never a silent default (S4 CR-1's fail-closed rule).
        try:
            intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
        except Exception:
            intake = {}
        cv = intake.get("copy_version") if isinstance(intake, dict) else None
        if cv not in page_role.copy_versions():
            return None, ["copy stage validator needs intake.json copy_version "
                          "(\"standard\" or \"long-form\", or the page type's own form such as "
                          "\"thank-you\"), the required intake decision "
                          "(Amendment 6, Items 18/19); none is recorded"]
        substitutions["{copy_version}"] = cv
        substitutions["{copy_spec}"] = page_role.spec_ref(cv)
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
    # An empty {sauce} must stay empty (quoting "" would add a spurious
    # empty argv entry); a set flag is a single safe token.
    substitutions["{sauce}"] = sauce
    if "{file}" in cmd:
        if not files:
            return None, [f"per-file validator has no files to validate "
                          f"(glob {per_file!r} matched none and the receipt lists none)"]
        # Per-file validators run once per file. Return the template UNSUBSTITUTED
        # with the substitution map, so the caller tokenizes once and substitutes
        # inside tokens ({file} included) instead of re-tokenizing a path.
        return ("__per_file__", cmd, files, substitutions), []
    if files:
        substitutions["{file}"] = files[0]
    if as_argv:
        return substitute_argv(cmd, substitutions), []
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


# Shared-service generation check: success is wired to image files on
# disk, never to a script reaching its end. A wrapper may run only some
# of the four stages (final-mockups follow the client's approval), so the
# check covers the stages that left a stage-executor-record.json.
GENERATED_IMAGE_STAGES = ("desktop-wireframe", "mobile-tablet",
                          "visual-mockup", "final-mockups")
EXECUTOR_RECORD = "stage-executor-record.json"
# Mockup parts carry the stage's documented raster width; the wireframe
# stages are dimension-checked by validate_wireframe.py, never here.
MOCKUP_PART_WIDTHS = (("visual-mockup/desktop", 1440),
                      ("visual-mockup/mobile", 390),
                      ("final-mockups/desktop", 1440),
                      ("final-mockups/mobile", 390))
MOCKUP_WIDTH_TOLERANCE_PX = 2

def stages_that_ran(run_dir):
    return [s for s in GENERATED_IMAGE_STAGES
            if (run_dir / s / EXECUTOR_RECORD).is_file()]

def verify_generated_images(run_dir):
    """Return (failure_lines, image_count) for a generation run.

    A run that produced zero images is a failure even when every command
    it ran exited 0; so is an executed stage with no image, or a mockup
    part that is unreadable or the wrong width. Empty failures and a
    positive count mean success.
    """
    failures = []
    count = 0
    for stage in stages_that_ran(run_dir):
        n = sum(1 for p in run_dir.glob(f"{stage}/**/*.png") if p.is_file())
        count += n
        if n == 0:
            failures.append(f"generated images: stage {stage} ran and "
                            "produced no image")
    try:
        from PIL import Image
    except Exception as exc:
        failures.append(f"generated images: Pillow is required to read "
                        f"image dimensions ({exc})")
        Image = None
    if Image is not None:
        for prefix, want in MOCKUP_PART_WIDTHS:
            for path in sorted(run_dir.glob(f"{prefix}/part-*.png")):
                if not path.is_file():
                    continue
                try:
                    with Image.open(path) as im:
                        width = im.size[0]
                except Exception as exc:
                    failures.append(
                        f"generated images: {path.relative_to(run_dir)} is "
                        f"not a readable image ({exc})")
                    continue
                if abs(width - want) > MOCKUP_WIDTH_TOLERANCE_PX:
                    failures.append(
                        f"generated images: {path.relative_to(run_dir)} is "
                        f"{width}px wide, expected {want}px "
                        f"(+/-{MOCKUP_WIDTH_TOLERANCE_PX}px) for "
                        f"{'desktop' if want == 1440 else 'mobile'}")
    if count == 0:
        failures.append(
            "generated images: the run produced zero images across "
            + ", ".join(GENERATED_IMAGE_STAGES)
            + "; reaching the end of the pipeline is not a generated run")
    return failures, count

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
    # Review files recorded at close (Item 2) are evidence too: tampering with
    # a review after close is caught by the same hash check.
    recorded_reviews = dep_entry.get("review_hashes") or {}
    for rel, recorded in recorded_reviews.items():
        p = run_dir / rel
        if not p.exists():
            lines.append(f"dependency {dep}: recorded review file missing: {rel}")
            continue
        actual = sha256_file(p)
        if actual != recorded:
            lines.append(f"dependency {dep}: review changed after close: {rel} "
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
        # The launch profile flag is appended to the template before tokenizing:
        # the flag is its own argv entry either way.
        raw, profile_line = apply_launch_profile(raw, run_dir)
        if profile_line:
            failures.append(profile_line)
            continue
        resolved, rlines = resolve_brand_placeholder(raw, run_dir, stage, receipt,
                                                     as_argv=True)
        failures.extend(rlines)
        if resolved is None:
            continue
        if isinstance(resolved, tuple) and resolved[0] == "__per_file__":
            _, cmd_tpl, files, substitutions = resolved
            # Split the template ONCE, then substitute {file} inside the matching
            # argv entries: a file path that contains spaces must stay ONE
            # argument instead of being re-tokenized by shlex.split.
            argv_tpl = substitute_argv(cmd_tpl, substitutions)
            for fpath in files:
                argv = [tok.replace("{file}", fpath) for tok in argv_tpl]
                line = run_one_validator(argv, run_dir)
                if line:
                    failures.append(line)
        else:
            line = run_one_validator(resolved, run_dir)
            if line:
                failures.append(line)
    return failures


def substitute_argv(template, substitutions):
    """Tokenize a validator template ONCE, then substitute inside each token.

    Substituting into the string first and splitting afterwards tears a path
    that contains a space into several arguments. A token that substitutes to
    nothing (an unengaged {sauce}) is dropped, as the old string form dropped it.
    """
    argv = []
    for tok in shlex.split(template):
        substituted = tok
        had_placeholder = False
        for k, v in substitutions.items():
            if k in substituted:
                had_placeholder = True
            substituted = substituted.replace(k, v)
        if substituted or not had_placeholder:
            argv.append(substituted)
    return argv

def run_one_validator(cmd, run_dir):
    """Run one validator command; return None on exit 0 else a failure line.

    `cmd` is either a shell-style string (split here) or an already-split argv
    list. Callers that substitute a path into a template pass argv, so a path
    containing spaces is never re-tokenized.
    """
    if isinstance(cmd, str):
        parts = shlex.split(cmd)
        label = cmd
    else:
        parts = list(cmd)
        label = shlex.join(parts)
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
        return f"validator timed out: {label}"
    if proc.returncode != 0:
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        detail = (out or err or "(no output)")[:600]
        return f"validator exit {proc.returncode}: {label}\n    {detail}"
    return None


CTA_MARKER_RE = re.compile(r"\[CTA BUTTON:\s*(.*?)\]", re.S)
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]*)\)")


def _norm_label(text):
    return " ".join(str(text).replace("**", " ").replace("__", " ").split())


def copy_handoff_failure(manifest_path, public_path, manuscript_path):
    """Update plan Item 8: the copy-to-renderer handoff check.

    The pinned source for button labels and destinations is
    copy/public-copy.md: each button is a Markdown link carrying the
    exact label and the destination. The [CTA BUTTON: ...] markers live
    only in copy/internal-manuscript.md (validate_copy_structure.py's
    CTA map reads them there; validate_public_copy.py fails any public
    file carrying the literal marker). Every declared CTA must resolve
    a label and a destination from the public file. The declared set is
    the copy manifest's `ctas` inventory when it carries one, else the
    manuscript's CTA markers with the manifest's `cta_destination`;
    when both inventories exist they must agree exactly. Prose links
    (the Section 12 in-letter link) are not CTAs and never counted.
    Returns a failure line, or None when the handoff is complete.
    """
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except Exception as exc:
        return f"gate:copy_handoff: copy manifest unreadable: {exc}"
    if not isinstance(manifest, dict):
        return "gate:copy_handoff: copy manifest is not a JSON object"
    try:
        public_text = Path(public_path).read_text(encoding="utf-8")
    except Exception as exc:
        return f"gate:copy_handoff: public copy unreadable: {exc}"
    manuscript_text = ""
    if manuscript_path:
        try:
            manuscript_text = Path(manuscript_path).read_text(encoding="utf-8")
        except Exception:
            manuscript_text = ""
    links = {}
    for label, dest in MD_LINK_RE.findall(public_text):
        links.setdefault(_norm_label(label), set()).add(dest.strip())
    page_destination = str(manifest.get("cta_destination") or "").strip()
    declared = []
    raw_ctas = manifest.get("ctas")
    if isinstance(raw_ctas, list):
        for entry in raw_ctas:
            if isinstance(entry, dict) and str(entry.get("label") or "").strip():
                declared.append({
                    "label": _norm_label(entry["label"]),
                    "destination": str(entry.get("destination")
                                       or page_destination).strip(),
                })
    markers = [_norm_label(m) for m in CTA_MARKER_RE.findall(manuscript_text)]
    marker_set = set(markers)
    if declared:
        declared_set = {d["label"] for d in declared}
        if marker_set and declared_set != marker_set:
            parts = []
            if declared_set - marker_set:
                parts.append("manifest only: " + ", ".join(sorted(declared_set - marker_set)))
            if marker_set - declared_set:
                parts.append("manuscript only: " + ", ".join(sorted(marker_set - declared_set)))
            return ("gate:copy_handoff: the copy manifest's CTA inventory does "
                    "not match the internal manuscript's CTA markers ("
                    + "; ".join(parts)
                    + "); the handoff carries one CTA inventory, recorded in "
                    "the manifest (update plan Item 8)")
        ctas = declared
    else:
        ctas = [{"label": label, "destination": page_destination}
                for label in dict.fromkeys(markers)]
    problems = []
    for cta in ctas:
        if not cta["destination"]:
            problems.append(
                f"CTA {cta['label']!r} has no destination: the copy manifest "
                "records no cta_destination and the entry carries none")
        elif cta["destination"] not in links.get(cta["label"], set()):
            problems.append(
                f"CTA {cta['label']!r} does not resolve in copy/public-copy.md: "
                f"no Markdown link carries that label with destination "
                f"{cta['destination']!r}")
    if problems:
        return ("gate:copy_handoff: " + "; ".join(problems)
                + "; the pinned source for button labels and destinations is "
                "the Markdown links in copy/public-copy.md (update plan Item 8)")
    return None


def run_builtin(name, args, run_dir):
    """Built-in gate validators."""
    if name == "gate:must_supply":
        brand = brand_path_for_checked(run_dir)
        if brand.name == _brand_colors().UNRESOLVED:
            # no owned, colored brand file: say so (and ask) instead of "file unreadable"
            return "gate:must_supply: " + _brand_colors().failure(run_dir)
        problems = brand_must_supply(brand)
        if problems:
            return "gate:must_supply: " + "; ".join(problems)
        return None
    if name == "gate:intake_engine":
        try:
            intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return f"gate:intake_engine: intake.json unreadable ({exc})"
        if not isinstance(intake, dict) or intake.get("image_engine") not in ("kie", "agnes"):
            return ("gate:intake_engine: intake.json must carry image_engine \"kie\" or \"agnes\" "
                    "(write it with scripts/write_intake.py)")
        return None
    if name == "gate:intake_design_style":
        # The client chooses A Block, B Circle or C Hybrid before any wireframe
        # (references/design-styles.md). A production run cannot close intake
        # without a recorded choice; test runs are exempt and carry no style.
        try:
            intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return f"gate:intake_design_style: intake.json unreadable ({exc})"
        if not isinstance(intake, dict):
            return "gate:intake_design_style: intake.json is not an object"
        if intake.get("test_run") is True and not intake.get("design_style"):
            return None
        if intake.get("design_style") not in ("A", "B", "C") or intake.get(
                "design_style_source") not in ("client_choice", "recommended_accepted"):
            return ("gate:intake_design_style: intake.json must carry design_style A, B or C and "
                    "design_style_source client_choice or recommended_accepted; ask the client with "
                    "`python3 scripts/design_style.py question`, then record it with "
                    "scripts/write_intake.py --design-style (references/design-styles.md)")
        return None
    if name == "gate:intake_page_kind":
        # The landing-role page is a signature sales page or a signature landing
        # (opt-in) page (references/page-kinds.json). A production run cannot close
        # intake without the recorded kind, and the kind must allow the run's copy
        # form; test runs are exempt.
        try:
            intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return f"gate:intake_page_kind: intake.json unreadable ({exc})"
        if not isinstance(intake, dict):
            return "gate:intake_page_kind: intake.json is not an object"
        if intake.get("test_run") is True and not intake.get("page_kind"):
            return None
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            import page_kinds
            import page_role
            if page_role.declared_role(run_dir) != page_role.LANDING_ROLE:
                return None  # only the landing role has a page kind
            page_kinds.check(intake.get("page_kind"), intake.get("copy_version") or intake.get("page_version"))
        except page_kinds.KindError as exc:
            return (f"gate:intake_page_kind: {exc}; record the page with "
                    "scripts/write_intake.py --page-kind sales|opt_in")
        finally:
            sys.path.pop(0)
        return None
    if name == "gate:noop":
        # Test-only builtin: always passes.
        return None
    if name == "gate:grade_calibrated":
        # S2 GCR-S2-1 (Item 8/Item 6): a production close of
        # image-generation-qc is refused while the grade thresholds it
        # would be judged by are uncalibrated. Test runs are exempt (the
        # condition is scoped to production exactly as the request wrote
        # it); the publish-verify leg lives in check_publish_rules.
        try:
            intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
        except Exception:
            intake = {}
        if isinstance(intake, dict) and intake.get("test_run") is True:
            return None
        brand = brand_path_for(run_dir)
        try:
            bdata = json.loads(brand.read_text(encoding="utf-8"))
        except Exception as exc:
            return f"gate:grade_calibrated: brand file unreadable: {exc}"
        grade = bdata.get("grade") or {}
        if grade.get("min_mean_saturation") is None or grade.get("min_luma_std") is None:
            return ("image grade thresholds are uncalibrated (grade.min_mean_saturation / "
                    "grade.min_luma_std are null in the brand file): a production run cannot "
                    "be certified against uncalibrated thresholds. Calibrate per Item 8 "
                    "(scripts/calibrate_grade.py) or close this stage in a test run.")
        return None
    if name == "gate:image_grade_full_set":
        # S2 GCR-S2-2: the per-file validator line sees one file at a
        # time, so the set-level checks (duplicates across the set,
        # ratio truth against the inventory) never run at the gate. This
        # builtin runs the same validator once over the whole set.
        if not args:
            return "gate:image_grade_full_set: missing stage argument"
        stage = args[0]
        spec = STAGES.get(stage) or {}
        glob_pat = spec.get("per_file_glob")
        if not glob_pat:
            return f"gate:image_grade_full_set: stage {stage} has no per_file_glob"
        files = sorted(str(p) for p in run_dir.glob(glob_pat) if p.is_file())
        if not files:
            return None  # the per-file line already failed on the empty set
        brand = brand_path_for(run_dir)
        cmd = [sys.executable, str(SKILL_ROOT / "scripts" / "validate_image_grade.py"),
               *files, "--brand", str(brand)]
        inventory = run_dir / "desktop-wireframe" / "image-inventory.json"
        if inventory.is_file():
            cmd += ["--inventory", str(inventory)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                  cwd=str(SKILL_ROOT))
        except subprocess.TimeoutExpired:
            return "gate:image_grade_full_set: full-set validator timed out"
        if proc.returncode != 0:
            detail = ((proc.stdout or "").strip() or (proc.stderr or "").strip()
                      or "(no output)")[:600]
            return (f"gate:image_grade_full_set: full-set image grade pass failed "
                    f"(exit {proc.returncode}): {detail}")
        return None
    if name == "gate:brand_fonts":
        # S3 Request 3: a brand-fonts waiver recorded at intake excuses
        # this check for the run; the waiver prints in REPORT.md via
        # collect_warnings. An unrecorded absence is never a waiver.
        try:
            _intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
        except Exception:
            _intake = {}
        if isinstance(_intake, dict) and any(
                isinstance(w, dict) and w.get("gate") == "brand-fonts"
                and str(w.get("reason") or "").strip()
                for w in _intake.get("layout_waivers") or []):
            return None
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
        if derived:
            # Update plan Item 7: on the derive path the gate checks the
            # derivation DOCUMENTATION fields in the font map (the same
            # three field names the visual bible carries), never an
            # approval: no approval exists at this stage. The approval is
            # recorded once, at the visual bible review, in the bible's
            # font_reviewer (enforced by validate_visual_direction.py and
            # the publish-verify rules below). font_reviewer here names
            # the designated reviewer (the visual-mockup stage's
            # independent bible reviewer) as a forward reference only.
            problems = []
            if str(fonts.get("fonts_source") or "").strip() != "derived":
                problems.append('fonts_source is not "derived"')
            if not str(fonts.get("font_rationale") or "").strip():
                problems.append("font_rationale is empty")
            reviewer = str(fonts.get("font_reviewer") or "").strip()
            if not reviewer or reviewer in MUST_SUPPLY_STRINGS:
                problems.append("font_reviewer names no designated reviewer")
            if problems:
                return ("gate:brand_fonts: derived fonts are not documented "
                        "in the font map: " + "; ".join(problems)
                        + "; font_policy derive-document requires the font map "
                        "to carry fonts_source \"derived\", a written "
                        "font_rationale, and font_reviewer naming the "
                        "designated reviewer, so the visual bible can lift "
                        "them verbatim (update plan Item 7)")
        return None
    if name == "gate:copy_handoff":
        # Update plan Item 8: every CTA declared by the copy manifest
        # (or by the internal manuscript's CTA markers) must resolve a
        # label and a destination from the pinned source,
        # copy/public-copy.md's Markdown links. See copy_handoff_failure.
        manifest = None
        public = None
        manuscript = None
        i = 0
        while i < len(args):
            if args[i] == "--manifest" and i + 1 < len(args):
                manifest = Path(args[i + 1])
            elif args[i] == "--public-copy" and i + 1 < len(args):
                public = Path(args[i + 1])
            elif args[i] == "--manuscript" and i + 1 < len(args):
                manuscript = Path(args[i + 1])
            i += 1
        if manifest is None or public is None:
            return "gate:copy_handoff: missing --manifest or --public-copy"
        return copy_handoff_failure(manifest, public, manuscript)
    return f"unknown builtin validator {name}"


# Review Receipt v2 (fix plan Item 2): session ids that prove nothing.
PLACEHOLDER_SESSIONS = {"", "-", "none", "null", "nil", "n/a", "na", "tbd", "todo",
                        "native", "placeholder", "fake", "dummy", "test", "unknown",
                        "unknown-author", "0"}
MIN_REVIEW_NOTE_CHARS = 40
# Amendment 6, Item 2 delta: when the reviewing environment cannot name its
# session, write_review.py records reviewer_session as "UNKNOWN" with
# independent_review false (the limitation is reported, not simulated).
# "UNKNOWN" stays a placeholder for author sessions and for any claimed
# independence, but it is not a missing-session failure for the reviewer.
UNKNOWN_SESSION = "UNKNOWN"


def _is_placeholder_session(value):
    return not isinstance(value, str) or value.strip().lower() in PLACEHOLDER_SESSIONS


def _is_unknown_session(value):
    return isinstance(value, str) and value.strip().upper() == UNKNOWN_SESSION


def required_review_items(run_dir, stage):
    """Enumerate the items a stage's close requires review files for.

    Returns a list of (item_id, artifact_rel_or_None). Per-file stages: one
    item per file matched by per_file_glob. review_covers stages: one item
    per covered file (covers may be a single glob string or a list mixing
    globs, literal paths, and named items such as page-visual-bible, whose
    artifact is resolved from the review file itself). All other stages:
    the single item "stage".
    """
    spec = STAGES[stage]
    per_file = spec.get("per_file_glob")
    if per_file:
        return [(p.stem, str(p.relative_to(run_dir)))
                for p in sorted(run_dir.glob(per_file)) if p.is_file()]
    covers = spec.get("review_covers")
    if covers:
        entries = [covers] if isinstance(covers, str) else list(covers)
        raw = []
        for entry in entries:
            if any(ch in entry for ch in "*?["):
                for p in sorted(run_dir.glob(entry)):
                    if p.is_file():
                        raw.append((p.stem, str(p.relative_to(run_dir)),
                                    p.parent.name, p.suffix.lstrip(".")))
            else:
                candidate = run_dir / entry
                if candidate.is_file():
                    raw.append((candidate.stem, entry, candidate.parent.name,
                                candidate.suffix.lstrip(".")))
                elif "/" in entry:
                    # A covered file path that is absent: name the item by
                    # the file's base name (the stage's artifact check fails
                    # the close separately for the missing artifact).
                    raw.append((Path(entry).stem, None, Path(entry).parent.name,
                                Path(entry).suffix.lstrip(".")))
                else:
                    raw.append((entry, None, "", ""))
        # Stems can collide: one review file cannot evidence two different
        # artifacts. Collisions across folders are disambiguated by parent
        # folder (desktop-part-01, mobile-part-01); collisions inside one
        # folder are disambiguated by file suffix (page-visual-bible-json,
        # page-visual-bible-md).
        stem_counts = {}
        for stem, _, _, _ in raw:
            stem_counts[stem] = stem_counts.get(stem, 0) + 1
        parent_counts = {}
        for stem, _, parent, _ in raw:
            parent_counts[(parent, stem)] = parent_counts.get((parent, stem), 0) + 1
        items = []
        for stem, rel, parent, suffix in raw:
            if stem_counts[stem] == 1:
                item_id = stem
            elif parent and parent_counts[(parent, stem)] == 1:
                item_id = f"{parent}-{stem}"
            elif suffix:
                item_id = f"{stem}-{suffix}"
            elif parent:
                item_id = f"{parent}-{stem}"
            else:
                item_id = stem
            items.append((item_id, rel))
        return items
    return [("stage", None)]


def review_scores_summary(run_dir, stage):
    """Aggregate the stage's v2 review criteria into a small summary dict."""
    reviews_dir = run_dir / "private" / "reviews" / stage
    values = []
    if reviews_dir.is_dir():
        for p in sorted(reviews_dir.glob("*.review.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            criteria = data.get("criteria") or {}
            if isinstance(criteria, dict):
                for entry in criteria.values():
                    if isinstance(entry, dict):
                        score = entry.get("score")
                        if isinstance(score, (int, float)) and not isinstance(score, bool):
                            values.append(float(score))
    if not values:
        return None
    return {"criteria_count": len(values), "min": min(values),
            "mean": round(sum(values) / len(values), 3)}


def check_review_scores(run_dir, stage, receipt):
    """Review Receipt v2 verification for close (fix plan Items 2 and 12).

    Scores live only in per-item files private/reviews/<stage>/<item>.review.json
    written by scripts/write_review.py. A stage receipt carrying v1 scores
    fails close with the migration message; the scores path is deleted, not
    deprecated.
    """
    spec = STAGES[stage]
    failures = []
    legacy_scores = receipt.get("scores")
    if isinstance(legacy_scores, dict) and legacy_scores:
        failures.append(
            f"stage {stage}: receipt carries Review Receipt v1 scores; v1 is retired. "
            f"Migration: remove scores from private/receipts/{stage}.json and write one "
            f"Review Receipt v2 file per item at private/reviews/{stage}/<item-id>.review.json "
            f"with scripts/write_review.py, from the reviewing session")
    review_required = bool(spec.get("review_required")) or spec.get("min_scores") is not None
    if not review_required:
        return failures
    author_agent = receipt.get("author_agent")
    if not author_agent:
        failures.append(f"stage {stage}: receipt missing author_agent")
    receipt_author_session = receipt.get("author_session") or author_agent
    items = required_review_items(run_dir, stage)
    if not items:
        failures.append(f"stage {stage}: review is required but no reviewable items "
                        f"could be enumerated from the stage contract")
        return failures
    all_scores = []
    for item_id, artifact_rel in items:
        where = f"stage {stage} item {item_id}"
        review_path = run_dir / "private" / "reviews" / stage / f"{item_id}.review.json"
        if not review_path.exists():
            named = f" (artifact {artifact_rel})" if artifact_rel else ""
            failures.append(
                f"{where}: missing review file private/reviews/{stage}/{item_id}.review.json"
                f"{named}; uncovered items cannot close. Write it with "
                f"scripts/write_review.py from the reviewing session")
            continue
        try:
            review = json.loads(review_path.read_text(encoding="utf-8"))
        except Exception as exc:
            failures.append(f"{where}: review file unreadable: {exc}")
            continue
        if not isinstance(review, dict):
            failures.append(f"{where}: review file is not a JSON object")
            continue
        if review.get("item") != item_id:
            failures.append(f"{where}: review file item is {review.get('item')!r}, "
                            f"expected {item_id!r}")
        rel = review.get("artifact")
        if not isinstance(rel, str) or not rel:
            failures.append(f"{where}: review file names no artifact")
            rel = None
        if rel is not None and artifact_rel is not None and rel != artifact_rel:
            failures.append(f"{where}: review covers artifact {rel!r} but the item's "
                            f"artifact is {artifact_rel!r}")
        if rel is not None:
            artifact_path = run_dir / rel
            if not artifact_path.is_file():
                failures.append(f"{where}: reviewed artifact missing on disk: {rel}")
            else:
                actual = sha256_file(artifact_path)
                if actual != review.get("artifact_sha256"):
                    failures.append(
                        f"{where}: artifact hash mismatch for {rel} (review recorded "
                        f"{str(review.get('artifact_sha256'))[:12]}..., on-disk "
                        f"{actual[:12]}...); the graded bytes changed after review")
        author_session = review.get("author_session")
        reviewer_session = review.get("reviewer_session")
        reviewer_unknown = _is_unknown_session(reviewer_session)
        if _is_placeholder_session(author_session):
            failures.append(f"{where}: review author_session is missing or a placeholder "
                            f"({author_session!r})")
        if _is_placeholder_session(reviewer_session) and not reviewer_unknown:
            failures.append(f"{where}: review reviewer_session is missing or a placeholder "
                            f"({reviewer_session!r}); reviews must be stamped by "
                            f"scripts/write_review.py from a real session")
        if (not _is_placeholder_session(author_session)
                and not _is_placeholder_session(reviewer_session)
                and reviewer_session == author_session):
            failures.append(f"{where}: reviewer_session equals author_session "
                            f"({reviewer_session!r}); review must be independent")
        if (not _is_placeholder_session(reviewer_session)
                and isinstance(receipt_author_session, str)
                and reviewer_session == receipt_author_session):
            failures.append(f"{where}: reviewer_session equals the stage receipt's author "
                            f"session ({receipt_author_session!r}); review must be independent")
        if review.get("verdict") != "pass":
            failures.append(f"{where}: review verdict is {review.get('verdict')!r}, "
                            f"not 'pass'")
        # Amendment 6, Item 2 delta: the SOP's evidentiary fields are part
        # of the v2 schema. A review without them is an incomplete record,
        # and a review that records automatic failures cannot close its
        # stage (zero auto-fails is one leg of the Item 12 per-artifact rule).
        for list_field in ("automatic_failures", "specific_defects"):
            if list_field not in review:
                failures.append(f"{where}: review file is missing {list_field} "
                                f"(Review Receipt v2 schema, Amendment 6)")
            elif not isinstance(review[list_field], list):
                failures.append(f"{where}: review {list_field} must be a list")
        repair_attempt = review.get("repair_attempt")
        if "repair_attempt" not in review:
            failures.append(f"{where}: review file is missing repair_attempt "
                            f"(Review Receipt v2 schema, Amendment 6)")
        elif (not isinstance(repair_attempt, int) or isinstance(repair_attempt, bool)
                or not 0 <= repair_attempt <= 3):
            failures.append(f"{where}: review repair_attempt must be an integer "
                            f"from 0 to 3, got {repair_attempt!r}")
        for text_field in ("performed_check", "next_current_artifact"):
            value = review.get(text_field)
            if not isinstance(value, str) or not value.strip():
                failures.append(f"{where}: review {text_field} is missing or empty "
                                f"(Review Receipt v2 schema, Amendment 6)")
        independent_flag = review.get("independent_review")
        if "independent_review" not in review:
            failures.append(f"{where}: review file is missing independent_review "
                            f"(Review Receipt v2 schema, Amendment 6)")
        elif not isinstance(independent_flag, bool):
            failures.append(f"{where}: review independent_review must be a boolean")
        elif reviewer_unknown and independent_flag:
            failures.append(f"{where}: reviewer_session is UNKNOWN but "
                            f"independent_review is true; the limitation must be "
                            f"recorded, not simulated")
        if (review.get("verdict") == "fail"
                and isinstance(review.get("specific_defects"), list)
                and not review["specific_defects"]):
            failures.append(f"{where}: verdict is 'fail' but specific_defects is "
                            f"empty; a fail verdict must name its defects")
        recorded_autofails = review.get("automatic_failures")
        if isinstance(recorded_autofails, list) and recorded_autofails:
            failures.append(
                f"{where}: review records {len(recorded_autofails)} automatic "
                f"failure(s): " + "; ".join(str(x) for x in recorded_autofails)
                + "; zero automatic failures are required to close "
                  "(Item 12 per-artifact rule)")
        criteria = review.get("criteria")
        if not isinstance(criteria, dict) or not criteria:
            failures.append(f"{where}: review file carries no criteria scores")
            continue
        for cname, entry in sorted(criteria.items()):
            if not isinstance(entry, dict):
                failures.append(f"{where}: criterion {cname!r} is not a {{score, note}} object")
                continue
            score = entry.get("score")
            if not isinstance(score, (int, float)) or isinstance(score, bool):
                failures.append(f"{where}: criterion {cname!r} score is not a number")
            else:
                all_scores.append((item_id, cname, float(score)))
            note = entry.get("note")
            if not isinstance(note, str) or not note.strip():
                failures.append(f"{where}: criterion {cname!r} has no evidence note")
            elif len(note.strip()) < MIN_REVIEW_NOTE_CHARS:
                failures.append(f"{where}: criterion {cname!r} note is "
                                f"{len(note.strip())} characters; at least "
                                f"{MIN_REVIEW_NOTE_CHARS} required")
    min_scores = spec.get("min_scores") or {}
    each = min_scores.get("each")
    if each is not None and all_scores:
        bad = [(i, c, v) for i, c, v in all_scores if v < each]
        for i, c, v in bad:
            failures.append(f"stage {stage}: score below minimum {each}: "
                            f"item {i} criterion {c} = {v:g}")
    avg = min_scores.get("average")
    if avg is not None:
        if not all_scores:
            failures.append(f"stage {stage}: min_scores average {avg} required but no "
                            f"v2 review criteria were found")
        else:
            # Amendment 6, Item 12 delta: the average is PER ARTIFACT. Every
            # reviewed file must reach the contract average with its own
            # criteria; a strong file can no longer carry a weak one across
            # the close (cross-file pooling is removed).
            by_item = {}
            for i, _c, v in all_scores:
                by_item.setdefault(i, []).append(v)
            for item_id, _rel in items:
                values = by_item.get(item_id)
                if not values:
                    continue  # missing or empty reviews failed above by name
                mean = sum(values) / len(values)
                if mean < avg:
                    failures.append(f"stage {stage}: item {item_id} average score "
                                    f"{mean:.2f} across its {len(values)} reviewed "
                                    f"criteria is below minimum {avg} (per-artifact "
                                    f"rule: every file must reach the average "
                                    f"itself; cross-file pooling is not allowed)")
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


KIE74_DIR = Path("receipts") / "kie74"


def _kie74_file(run_dir, task_id):
    safe = "".join(c for c in str(task_id) if c.isalnum() or c in "_-")[:80] or "task"
    return run_dir / KIE74_DIR / f"{safe}.json"


def _kie74_problems(run_dir, stage, tasks, alias=False):
    """Each Skill 74 task id must be unique and backed by its own result file in receipts/kie74/.

    With alias=True (Item 28 step 3, a claude-nine run transported by
    the 999 kie skill), the result file may name the kie skill as its
    adapter and carries no adapter_mode (Skill 74's mode system is its
    own); every other requirement is identical: unique task ids, a
    readable result file per task, task_id match, state success.
    """
    problems, seen = [], {}
    for x in tasks:
        if not isinstance(x, dict) or not _real_id(x.get("task_id")):
            continue
        tid = x["task_id"]
        if tid in seen:
            problems.append(f"stage {stage}: task_id {tid!r} is used for both {seen[tid]} and {x.get('file')}")
        seen[tid] = x.get("file")
        f = _kie74_file(run_dir, tid)
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            problems.append(f"stage {stage}: task_id {tid!r} has no readable {KIE74_DIR}/{f.name} "
                            f"(record it with kie74_receipt.py)")
            continue
        ok = (isinstance(obj, dict) and obj.get("task_id") == tid
              and obj.get("state") == "success")
        if ok and alias:
            ok = obj.get("adapter") in ("74-kie-live-adapter", "kie")
        elif ok:
            ok = (obj.get("adapter") == "74-kie-live-adapter"
                  and obj.get("adapter_mode") == "active")
        if not ok:
            problems.append(f"stage {stage}: {KIE74_DIR}/{f.name} is not a successful active Skill 74 result for {tid!r}")
    ids = {}
    d = run_dir / KIE74_DIR
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            tid = json.loads(f.read_text(encoding="utf-8")).get("task_id")
        except (OSError, ValueError, AttributeError):
            continue
        if tid in ids:
            problems.append(f"stage {stage}: {KIE74_DIR}/{f.name} and {ids[tid]} carry the same task_id {tid!r}")
        ids[tid] = f.name
    return problems


def _agnes_selected(run_dir):
    try:
        intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(intake, dict) and str(intake.get("image_engine", "")).strip().lower() == "agnes"


# ---------------------------------------------------------------------------
# A23 per-provider branch (reconciled matrix Q10, action 9; fixtures
# F-A23-1..F-A23-4). The transport-block requirement is per provider:
#
# - KIE (Skill 74 route, incl. the claude-nine alias): the real KIE task
#   ID is required per task, backed by its receipts/kie74 result file,
#   with preflight / budget / model / N43 checks (unchanged; enforced in
#   check_transport / check_item_transport below).
# - Agnes (Skill 63 route): generation is SYNCHRONOUS and the provider
#   issues no task ID. The honest Agnes task shape is: task_id explicit
#   null or the key omitted, request_id recorded only if the provider
#   returned one, mode "sync" when a mode is declared, and no polling
#   artefacts. Parity target: S63's provider_receipt.validate_receipt
#   (PR #2157) — it refuses any non-null task_id on an Agnes receipt,
#   refuses any non-null KIE-named field on an Agnes receipt, and
#   requires the real task ID on a KIE receipt.
#
# This validation only READS the receipt. No code path here mints,
# defaults, or back-fills a task ID for Agnes: an absent identifier is
# recorded as absent, never repaired into an invented one.

AGNES_SYNC_MODE = "sync"


def _agnes_task_problems(who, task):
    """Per-task Agnes-branch problems for one transport task entry."""
    problems = []
    if "task_id" in task and task["task_id"] is not None:
        problems.append(
            f"{who}: Agnes task_id must be null (synchronous Agnes results "
            f"have no task ID; do not attach one), got {task['task_id']!r} "
            f"(A23: no false KIE task IDs for Agnes)")
    for key in task:
        lowered = str(key).lower()
        if "kie" in lowered and task[key] is not None:
            problems.append(
                f"{who}: Agnes receipt must not carry a KIE identifier "
                f"field {key!r} with a value (A23)")
        if "poll" in lowered and task[key] is not None:
            problems.append(
                f"{who}: Agnes receipt carries polling artefact {key!r}; "
                f"a synchronous result has no polling evidence (A23, "
                f"F-A23-4)")
    mode = task.get("mode")
    if mode is not None and mode != AGNES_SYNC_MODE:
        problems.append(
            f"{who}: Agnes task mode must be 'sync' (synchronous "
            f"provider), got {mode!r} (A23)")
    if task.get("model_id") is not None and not _real_id(task.get("model_id")):
        problems.append(
            f"{who}: Agnes model_id {task.get('model_id')!r} is missing "
            f"or a placeholder")
    if task.get("request_id") is not None and not _real_id(task.get("request_id")):
        problems.append(
            f"{who}: Agnes request_id {task.get('request_id')!r} is a "
            f"placeholder; record the provider-returned request ID or "
            f"omit it (A23)")
    return problems


def _agnes_transport_problems(stage, transport):
    """Transport-level Agnes-branch problems (the declared mode)."""
    mode = transport.get("mode")
    if mode is not None and mode != AGNES_SYNC_MODE:
        return [f"stage {stage}: Agnes transport.mode must be 'sync' "
                f"(synchronous provider; 'active' is the Skill 74 mode "
                f"system), got {mode!r} (A23)"]
    return []


# ---------------------------------------------------------------------------
# Launch profile wiring (S71-02): under the signature_launch_landing
# profile, the copy stage's public-copy validation runs with S71-03's
# no-offer-pricing gate engaged (packet doc 07 section 3: no offer
# pricing on a Signature Launch landing page). The gate itself is an
# opt-in flag on validate_public_copy.py owned by S71-03; the profile is
# what engages it. Until the gate lands in this tree, a profile run's
# copy stage fails closed naming the missing gate rather than silently
# validating without it. Non-profile runs are untouched.

LAUNCH_PROFILE_NAME = "signature_launch_landing"
NO_OFFER_PRICING_FLAG = "--no-offer-pricing"


def launch_profile_active(run_dir):
    return intake_data(run_dir).get("launch_profile") == LAUNCH_PROFILE_NAME


def apply_launch_profile(cmd, run_dir):
    """Engage the profile's no-offer-pricing gate on a validator command.

    Returns (command, failure_line_or_None): the command with the flag
    appended when the profile is active and the validator on disk
    supports it; a named failure when the profile is active but the
    on-disk validator has no such flag; the command unchanged otherwise.
    """
    if "validate_public_copy.py" not in cmd or not launch_profile_active(run_dir):
        return cmd, None
    if NO_OFFER_PRICING_FLAG in cmd:
        return cmd, None
    script = SKILL_ROOT / "scripts" / "validate_public_copy.py"
    try:
        supported = NO_OFFER_PRICING_FLAG in script.read_text(encoding="utf-8")
    except OSError:
        supported = False
    if not supported:
        return cmd, ("launch profile signature_launch_landing requires the "
                     "no-offer-pricing gate (S71-03), but "
                     "scripts/validate_public_copy.py on disk does not "
                     "support --no-offer-pricing; the copy stage cannot "
                     "close under the profile without the gate engaged")
    return cmd + " " + NO_OFFER_PRICING_FLAG, None


def _intake_runtime(run_dir):
    try:
        intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return intake.get("runtime") if isinstance(intake, dict) else None


LAYOUT_REFERENCE_FILES = (
    "Sales Page - Elevation Conference - Desktop(1).jpg",
    "screencapture-blackceochallenge-reg-va-2026-09-29-15_52_07.png",
    "screencapture-blackceochallenge-reg-va-2026-09-29-15_52_07-2.png",
)
LAYOUT_GATE_STAGES = ("desktop-wireframe", "mobile-tablet", "visual-mockup")
LAYOUT_SUBSTITUTIONS_NAME = "substitutions.json"


def _layout_substitution_record(skill_root=None):
    """Parse assets/page-references/substitutions.json, the standing
    house-default registry (Ruling 5, 2026-10-14; Item 17, ruled
    2026-10-15: each complete entry is the APPROVED HOUSE DEFAULT for
    its named reference, the fallback a run uses when the original
    file was not supplied).

    A substitution counts only when its record is complete: the named
    file, status "substituted", a non-empty ruled_by, ruling_date, and
    ruling, and at least one stand-in entry with a file name. Any
    defect (unreadable file, malformed JSON, an incomplete entry)
    means NO substitution for that name: the record fails closed,
    exactly like a waiver without a reason is not a waiver. Returns
    (substitutions, outstanding): substitutions maps a named file to
    its record entry; outstanding lists the names the record itself
    marks outstanding.
    """
    root = SKILL_ROOT if skill_root is None else Path(skill_root)
    path = root / "assets" / "page-references" / LAYOUT_SUBSTITUTIONS_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, []
    if not isinstance(data, dict):
        return {}, []
    substitutions = {}
    for entry in data.get("substitutions") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("named_file")
        stand_ins = entry.get("stand_in_files") or []
        if (isinstance(name, str) and name
                and entry.get("status") == "substituted"
                and str(entry.get("ruled_by") or "").strip()
                and str(entry.get("ruling_date") or "").strip()
                and str(entry.get("ruling") or "").strip()
                and isinstance(stand_ins, list) and stand_ins
                and all(isinstance(s, dict) and str(s.get("file") or "").strip()
                        for s in stand_ins)):
            substitutions[name] = entry
    outstanding = [e.get("named_file") for e in data.get("outstanding") or []
                   if isinstance(e, dict) and e.get("status") == "outstanding"
                   and isinstance(e.get("named_file"), str) and e.get("named_file")]
    return substitutions, outstanding


def _layout_references_waived(run_dir):
    """A layout-references waiver counts only as recorded at intake.

    Two recorded shapes are honored (reconciled at integration, S8):
    the intake writer's layout_waivers list with a "layout-references"
    entry (S3 Request 3), and the flat fields the page-references
    README names (layout_references_waived true with a non-empty
    layout_references_waiver_reason). An unrecorded absence is never
    a waiver under either shape.
    """
    try:
        intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(intake, dict):
        return False
    for w in intake.get("layout_waivers") or []:
        if isinstance(w, dict) and w.get("gate") == "layout-references" and str(w.get("reason") or "").strip():
            return True
    return (intake.get("layout_references_waived") is True
            and bool(str(intake.get("layout_references_waiver_reason") or "").strip()))


def _is_supplied_entry(entry):
    """A run inventory entry is a supplied asset when its source begins
    with "supplied" (e.g. "supplied-logo", "supplied-founder-photo"):
    the asset already exists and no generation is performed for it
    (Item 3 supplied-asset path)."""
    if not isinstance(entry, dict):
        return False
    source = entry.get("source")
    return isinstance(source, str) and source.strip().lower().startswith("supplied")


def _supplied_inventory_entries(run_dir):
    """The run's supplied inventory entries, keyed by inventory id."""
    inv_path = run_dir / "desktop-wireframe" / "image-inventory.json"
    out = {}
    if inv_path.is_file():
        try:
            data = json.loads(inv_path.read_text(encoding="utf-8"))
        except ValueError:
            return out
        images = data.get("images", []) if isinstance(data, dict) else []
        for e in images:
            if _is_supplied_entry(e) and e.get("id"):
                out[str(e["id"])] = e
    return out


def style_selection_problems(run_dir):
    """GCR-S2-4 (Item 10, Amendment 6 Part B1): a run with no style
    selection record cannot close image-inventory-prompts. The record
    at image-inventory-prompts/style-selection.json must conform to
    references/style-selection.schema.json and govern every image in
    the run's inventory (a record's applies_to is "all" or a list of
    inventory image ids)."""
    stage = "image-inventory-prompts"
    path = run_dir / stage / "style-selection.json"
    if not path.is_file():
        return [f"stage {stage}: no style selection record at "
                f"{stage}/style-selection.json (Amendment 6, Part B1); "
                "a run with no selection record cannot close this stage"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return [f"stage {stage}: {stage}/style-selection.json is not "
                "readable JSON"]
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or not isinstance(data.get("selections"), list)
            or not data["selections"]):
        return [f"stage {stage}: style-selection.json does not conform "
                "to references/style-selection.schema.json (schema_version "
                "1 with a non-empty selections list)"]
    problems = []
    try:
        import jsonschema
        schema = json.loads((SKILL_ROOT / "references"
                             / "style-selection.schema.json").read_text(
                                 encoding="utf-8"))
        jsonschema.validate(data, schema)
    except ImportError:
        for i, rec in enumerate(data["selections"]):
            if not isinstance(rec, dict) or any(
                    k not in rec for k in ("applies_to", "source_library",
                                           "style_id", "branded_name")):
                problems.append(
                    f"stage {stage}: style-selection.json selections[{i}] "
                    "lacks a required field (applies_to, source_library, "
                    "style_id, branded_name)")
    except Exception as exc:
        problems.append(f"stage {stage}: style-selection.json fails "
                        f"references/style-selection.schema.json: {exc}")
    if problems:
        return problems
    inventory_ids = []
    supplied_ids = set()
    inv_path = run_dir / "desktop-wireframe" / "image-inventory.json"
    if inv_path.is_file():
        try:
            entries = [e for e in
                       json.loads(inv_path.read_text(
                           encoding="utf-8")).get("images", [])
                       if isinstance(e, dict)]
            inventory_ids = [e.get("id") for e in entries]
            supplied_ids = {str(e["id"]) for e in entries
                            if _is_supplied_entry(e) and e.get("id")}
        except ValueError:
            inventory_ids = []
    # Item 3: supplied entries (source begins with "supplied") are
    # exempt from style-selection governance; no selection record has
    # to govern them and "all" does not need to reach them.
    governed_ids = [i for i in inventory_ids if str(i) not in supplied_ids]
    governed = set()
    for rec in data["selections"]:
        applies = rec.get("applies_to")
        if applies == "all":
            governed.update(governed_ids)
        elif isinstance(applies, list):
            governed.update(applies)
    for image_id in governed_ids:
        if image_id not in governed:
            problems.append(f"stage {stage}: inventory image {image_id} "
                            "has no governing style selection record")
    return problems


def layout_reference_sources(run_dir=None):
    """Item 17 (ruled 2026-10-15): resolve each named layout reference
    in order and report the source a run uses for it.

    Resolution order per reference: (1) the supplied or bundled
    original file in assets/page-references/; (2) the approved house
    default recorded in the standing registry
    (assets/page-references/substitutions.json); (3) a recorded owner
    waiver in the run's intake, kept for true exceptions. Only a
    reference with none of the three is "unresolved", and only an
    unresolved reference stops the layout stages, naming it. Returns
    one dict per named reference, in LAYOUT_REFERENCE_FILES order:
    {named_file, source, detail}, where source is "original",
    "house_default", "waiver", or "unresolved".
    """
    substitutions, _outstanding = _layout_substitution_record()
    waived = (_layout_references_waived(run_dir)
              if run_dir is not None else False)
    sources = []
    for name in LAYOUT_REFERENCE_FILES:
        entry = substitutions.get(name)
        if (SKILL_ROOT / "assets" / "page-references" / name).is_file():
            detail = "original file"
            if entry is not None and any(
                    str(s.get("file") or "") == name
                    for s in entry.get("stand_in_files") or []):
                detail = ("original file (bundled ruled capture, owner "
                          f"ruling {entry.get('ruling_date')})")
            sources.append({"named_file": name, "source": "original",
                            "detail": detail})
        elif entry is not None:
            files = ", ".join(str(s.get("file"))
                              for s in entry.get("stand_in_files") or [])
            sources.append({"named_file": name, "source": "house_default",
                            "detail": f"house default: {files} "
                                      f"(owner ruling "
                                      f"{entry.get('ruling_date')})"})
        elif waived:
            sources.append({"named_file": name, "source": "waiver",
                            "detail": "waiver: recorded owner waiver "
                                      "in intake.json"})
        else:
            sources.append({"named_file": name, "source": "unresolved",
                            "detail": "unresolved: no original file, no "
                                      "registered house default, no "
                                      "recorded waiver"})
    return sources


def layout_gate_failures(run_dir):
    """Item 13 as amended by Item 17 (ruled 2026-10-15): each of the
    three layout references must RESOLVE at wireframe and mockup
    close: the supplied or bundled original file, or the approved
    house default recorded in the standing registry
    (assets/page-references/substitutions.json; Ruling 5, 2026-10-14,
    for the two Challenge screenshots; Decision 4, 2026-10-15, for
    the Elevation Conference capture), or a recorded owner waiver in
    intake for a true exception. The stage stops only for a reference
    with no resolution, and the failure names it. The gate reads the
    registry, not the stand-in binaries: the Challenge PDFs (108 MB)
    are held in the diagnostic record and bundling them here is a
    separate owner-visible step."""
    sources = layout_reference_sources(run_dir)
    unresolved = [s["named_file"] for s in sources
                  if s["source"] == "unresolved"]
    if not unresolved:
        return []
    fallback = [f"{s['named_file']} <- {s['detail']}" for s in sources
                if s["source"] == "house_default"]
    note = ""
    if fallback:
        note = ("; resolved by approved house default: "
                + "; ".join(fallback))
    return ["unresolved layout reference(s) in assets/page-references/: "
            + ", ".join(unresolved) + note
            + "; each reference resolves in order (the original file, "
              "the registered house default in substitutions.json, a "
              "recorded owner waiver in intake.json) and none applied "
              "(Item 13 as amended by Item 17)"]


def _ratio_problem(who, task):
    req, gen, src = task.get("requested_ratio"), task.get("generated_ratio"), task.get("model_source")
    if not (isinstance(req, str) and isinstance(gen, str) and req and gen):
        return f"{who}: requested_ratio and generated_ratio are required"
    if req in N43_LEGACY_ONLY:
        if gen != req or src not in ("legacy-ratio-route", "explicit-request", "department-pin"):
            return f"{who}: N43 sends {req} to the legacy route only (generated_ratio {gen!r}, model_source {src!r})"
    elif src in ("explicit-request", "department-pin"):
        # an explicit request or a pin overrides the default's ratio substitutions, with evidence
        ev = task.get("evidence")
        e = ev.strip() if isinstance(ev, str) else ""
        if not (len(e) >= 12 and len(e.split()) >= 3 and len(set(e.replace(" ", ""))) > 1
                and e.lower() not in BAD_IDS and e != task.get("model_id")):
            return (f"{who}: model_source {src!r} needs evidence naming the request text or the pin id "
                    f"(at least 12 characters and 3 words, not a placeholder or a repeated character)")
    elif gen != N43_SUBSTITUTIONS.get(req, req):
        return (f"{who}: N43 ratio rule violated: requested {req}, generated {gen}, "
                f"expected {N43_SUBSTITUTIONS.get(req, req)}")
    return None


def _supplied_transport_problems(run_dir, stage, item_id, artifact_rel, task):
    """Item 3 supplied-asset transport slice: a supplied item (inventory
    source begins with "supplied") is satisfied not by a Skill 74 task
    but by a transport.tasks entry carrying {"supplied_asset": true,
    "sha256": <sha256 of the filed bytes>}. The recorded sha256 is
    verified against the actual bytes on disk, and against the sha256
    recorded on the inventory entry when the entry records one."""
    who = f"stage {stage} item {item_id} ({artifact_rel})"
    if not isinstance(task, dict) or task.get("supplied_asset") is not True:
        return [f"{who}: item is a supplied asset (no generation was "
                f"performed for it); its transport entry must carry "
                f"supplied_asset: true and the sha256 of the filed bytes "
                f"instead of a generation task"]
    recorded = task.get("sha256")
    if not isinstance(recorded, str) or not recorded.strip():
        return [f"{who}: supplied-asset transport entry carries no "
                f"sha256 of the filed bytes"]
    if not artifact_rel or not (run_dir / artifact_rel).is_file():
        return [f"{who}: supplied asset file {artifact_rel} is not on disk"]
    actual = sha256_file(run_dir / artifact_rel)
    if recorded.strip().lower() != actual.lower():
        return [f"{who}: supplied-asset sha256 mismatch: the transport "
                f"entry records {recorded.strip()} but the filed bytes "
                f"hash to {actual}"]
    entry = _supplied_inventory_entries(run_dir).get(str(item_id)) or {}
    inv_sha = entry.get("sha256")
    if (isinstance(inv_sha, str) and inv_sha.strip()
            and inv_sha.strip().lower() != actual.lower()):
        return [f"{who}: the filed bytes hash to {actual} but the "
                f"inventory entry records sha256 {inv_sha.strip()} for "
                f"this supplied asset"]
    return []


def check_transport(run_dir, stage, receipt):
    """Image stages must prove the Skill 66/67 -> Skill 74 route (or an explicit Agnes route)."""
    spec = STAGES[stage]
    if not spec.get("transport_required"):
        return []
    t = receipt.get("transport")
    if not isinstance(t, dict):
        return [f"stage {stage}: receipt missing transport block (references/kie-generation-route.md section 3)"]
    skill = t.get("skill")
    # Item 28 step 3 environment alias: on a run whose intake declares
    # runtime "claude-nine" (the 999 Claude Code harness edition), the
    # 999 native kie skill may be recorded as the transport performing
    # both the policy and transport roles, provided its receipt carries
    # the same fields as the 74 route (task ids, per-task result files,
    # ratio checks, preflight and budget flags). The evidence standard
    # does not drop; only the skill's name changes. Skill 74's mode
    # system is its own and is not required of the alias.
    kie_alias = skill == "kie" and _intake_runtime(run_dir) == "claude-nine"
    if skill not in TRANSPORTS and not kie_alias:
        return [f"stage {stage}: transport.skill {skill!r} is not an approved route {sorted(TRANSPORTS)}; "
                f"a hand-rolled createTask is not"]
    policy, provider = TRANSPORTS[skill] if skill in TRANSPORTS else ("kie", "kie")
    kie_like = skill == "74-kie-live-adapter" or kie_alias
    problems = []
    if t.get("policy") != policy:
        problems.append(f"stage {stage}: transport.policy must be {policy!r}, got {t.get('policy')!r}")
    cost = receipt.get("cost")
    if isinstance(cost, dict) and cost.get("provider") != provider:
        problems.append(f"stage {stage}: cost.provider must be {provider!r} for {skill}, got {cost.get('provider')!r}")
    if skill == "63-agnes-image" and not _agnes_selected(run_dir):
        problems.append(f"stage {stage}: the Agnes route needs intake.json image_engine: \"agnes\" "
                        f"(the client must have selected Agnes)")
    if skill == "74-kie-live-adapter" and t.get("mode") != "active":
        problems.append(f"stage {stage}: transport.mode must be 'active' (shadow never dispatches), got {t.get('mode')!r}")
    if skill == "63-agnes-image":
        problems.extend(_agnes_transport_problems(stage, t))
    files = sorted(str(p.relative_to(run_dir)) for p in run_dir.glob(spec.get("per_file_glob", "")) if p.is_file())
    tasks = t.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return problems + [f"stage {stage}: transport.tasks must list one entry per generated file"]
    got = sorted(str(x.get("file")) for x in tasks if isinstance(x, dict))
    if got != files:
        problems.append(f"stage {stage}: transport.tasks cover {got} but the stage has {files}")
    # Item 3: files belonging to supplied inventory entries are
    # verified through the supplied-asset slice, never the task checks.
    supplied_here = {}
    for supplied_id in _supplied_inventory_entries(run_dir):
        # A supplied file that is missing from disk has no on-disk glob
        # match; fall back to its expected path so its transport entry
        # still reaches _supplied_transport_problems(), whose
        # not-on-disk branch names the file (Item 3 review defect D1).
        rel = (item_artifact_rel(run_dir, stage, supplied_id)
               or expected_item_artifact_rel(stage, supplied_id))
        if rel:
            supplied_here[rel] = supplied_id
    if kie_like:
        problems.extend(_kie74_problems(run_dir, stage, tasks, alias=kie_alias))
    for i, x in enumerate(tasks):
        who = f"stage {stage}: transport.tasks[{i}] ({x.get('file') if isinstance(x, dict) else '?'})"
        if not isinstance(x, dict):
            problems.append(f"{who} is not an object")
            continue
        if str(x.get("file")) in supplied_here:
            problems.extend(_supplied_transport_problems(
                run_dir, stage, supplied_here[str(x.get("file"))],
                str(x.get("file")), x))
            continue
        if skill == "63-agnes-image":
            # A23 Agnes branch: honest absence, never a KIE task ID.
            problems.extend(_agnes_task_problems(who, x))
            continue
        if not kie_like:
            continue
        if kie_alias and x.get("model_source") == "user-pin":
            # Item 28 step 3 vocabulary mapping: on a claude-nine run
            # the generated policy names the pin a user pin where the
            # onboarding law says department pin. Validation maps the
            # value on a working copy; the stored receipt keeps
            # "user-pin" (references/kie-policy-999.json).
            x = {**x, "model_source": "department-pin"}
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


# ---------------------------------------------------------------------------
# Item-level gates (fix plan Item 20).
#
# Itemized stages (contract flag "itemized": true; today
# image-inventory-prompts and image-generation-qc) gain per-item state under
# state["items"][stage][item_id] and three subcommands: check-item,
# close-item, block-item. The canonical item id space is the inventory id
# space (IMG-001, ...); an item's artifact and review files are located by
# numeric suffix, because the stages name their files differently
# (IMG-001.txt vs Image-01.png, whose review item id is its file stem;
# the generation file carries the two-digit delivered name, Item 26).
#
# The weld this cuts: a generation item opens the moment ITS prompt item is
# closed. Stage-level `check` for image-generation-qc is unchanged and still
# requires the whole dependency chain; only item flow is finer-grained.
# Stage `close` for an itemized stage gains fan-in verification (every item
# in the universe closed at item level) ahead of the existing artifact /
# validator / review / cost / transport checks, which still run in full.

ITEMIZED_STAGES = ("image-inventory-prompts", "image-generation-qc")
# Itemized stage -> the itemized stage whose items it feeds (and whose
# stage-level, non-per-file artifacts it structurally requires).
ITEM_FEEDS = {"image-generation-qc": "image-inventory-prompts"}


def is_itemized(stage):
    spec = STAGES.get(stage) or {}
    return bool(spec.get("itemized")) or stage in ITEMIZED_STAGES


def _item_number(item_id):
    m = re.search(r"(\d+)\s*$", str(item_id))
    return int(m.group(1)) if m else None


def item_universe(run_dir, stage):
    """Canonical item ids for an itemized stage, from its count_of inventory."""
    spec = STAGES[stage]
    rel = spec.get("count_of")
    if not rel:
        return []
    path = run_dir / rel
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    entries = []
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        for key in ("images", "inventory", "entries", "slots"):
            if isinstance(data.get(key), list):
                entries = data[key]
                break
    ids = []
    for e in entries:
        if isinstance(e, dict) and e.get("id"):
            ids.append(str(e["id"]))
        elif isinstance(e, str):
            ids.append(e)
    return ids


def item_artifact_rel(run_dir, stage, item_id):
    """The item's artifact path (run-relative), matched by numeric suffix."""
    spec = STAGES[stage]
    pattern = spec.get("per_file_glob")
    want = _item_number(item_id)
    if not pattern or want is None:
        return None
    for p in sorted(run_dir.glob(pattern)):
        if p.is_file() and _item_number(p.stem) == want:
            return str(p.relative_to(run_dir))
    return None


def expected_item_artifact_rel(stage, item_id):
    """The item's expected artifact path (run-relative), derived from the
    stage's per_file_glob instead of the on-disk glob (the same derivation
    swarm_runner.expected_item_artifact uses), or None when the pattern
    or the item number cannot name one. Unlike item_artifact_rel() this
    names the path even when the file is absent, which is what lets a
    caller report a missing file by name."""
    spec = STAGES[stage]
    pattern = spec.get("per_file_glob")
    want = _item_number(item_id)
    if not pattern or want is None or "*" not in Path(pattern).name:
        return None
    prefix, _, suffix = Path(pattern).name.partition("*")
    stem = str(item_id) if str(item_id).startswith(prefix) else f"{prefix}{want:03d}"
    return str(Path(pattern).parent / f"{stem}{suffix}")


def item_review_item_id(run_dir, stage, item_id):
    """The review-file item id for an item: its artifact's file stem."""
    rel = item_artifact_rel(run_dir, stage, item_id)
    if rel is None:
        return None
    return Path(rel).stem


def host_shape():
    """Amendment 1 profile detection (S6 emission spec section 6.1):
    FLEET_SHAPE env wins; Darwin is fleet-mac; a container is
    fleet-contabo; other Linux is fleet-hostinger."""
    env = os.environ.get("FLEET_SHAPE")
    if env in ("fleet-mac", "fleet-hostinger", "fleet-contabo"):
        return env
    import platform
    if platform.system() == "Darwin":
        return "fleet-mac"
    if Path("/.dockerenv").exists():
        return "fleet-contabo"
    try:
        if "container" in Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="ignore"):
            return "fleet-contabo"
    except Exception:
        pass
    return "fleet-hostinger"


def emit_event(run_dir, event):
    """Append one event to the run's feed, per references/run-events-schema.md
    (Items 24/25; S6's gate-side emission spec, implemented at integration).

    Fills the frozen envelope (event_id, event_type, schema_version,
    emitted_at, run_id). Also appends to the host index when
    SKILL71_RUNS_INDEX is set (with run_dir added), and attempts the
    Command Center POST when SKILL71_RUNS_SHIP_URL is set, falling back
    to the SKILL71_RUNS_SPOOL spool on failure (the token is read from
    SKILL71_RUNS_SHIP_TOKEN_FILE at send time and never printed or
    stored). Emission failure never fails the gate command: events are
    evidence about the gate, and a broken index path must not block a
    client's page; the failure prints as a WARN line on stderr.
    """
    try:
        state, _ = load_state(run_dir)
        if not state.get("run_id"):
            # A run initialized before Item 24 has no id; mint and store
            # one at the first emission so every line carries a run_id.
            state["run_id"] = str(uuid.uuid4())
            save_state(run_dir, state)
        full = dict(event)
        full.setdefault("event_id", str(uuid.uuid4()))
        full["schema_version"] = "1.0"
        full["emitted_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        full["run_id"] = state.get("run_id")
        line = json.dumps(full, sort_keys=True)
        path = run_dir / "private" / "run-events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        external = dict(full)
        external["run_dir"] = str(run_dir)
        ext_line = json.dumps(external, sort_keys=True)
        index = os.environ.get("SKILL71_RUNS_INDEX")
        if index:
            ipath = Path(index)
            ipath.parent.mkdir(parents=True, exist_ok=True)
            with open(ipath, "a", encoding="utf-8") as f:
                f.write(ext_line + "\n")
        ship_url = os.environ.get("SKILL71_RUNS_SHIP_URL")
        if ship_url:
            delivered = False
            try:
                headers = {"Content-Type": "application/json"}
                token_file = os.environ.get("SKILL71_RUNS_SHIP_TOKEN_FILE")
                if token_file:
                    token = Path(token_file).read_text(encoding="utf-8").strip()
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                req = urllib.request.Request(
                    ship_url, data=ext_line.encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    delivered = 200 <= resp.status < 300
            except Exception:
                delivered = False
            if not delivered:
                spool = os.environ.get("SKILL71_RUNS_SPOOL")
                if spool:
                    sdir = Path(spool)
                    sdir.mkdir(parents=True, exist_ok=True)
                    with open(sdir / "gate-spool.jsonl", "a", encoding="utf-8") as f:
                        f.write(ext_line + "\n")
    except Exception as exc:
        print(f"WARN: run event emission failed ({exc}); the gate command continues",
              file=sys.stderr)


def item_state(run_dir, stage, item_id, state=None):
    if state is None:
        state, _ = load_state(run_dir)
    return (state.get("items") or {}).get(stage, {}).get(item_id, {})


def item_dependency_failures(run_dir, stage, item_id):
    """check-item core: the item's OWN dependencies, nothing wider."""
    spec = STAGES[stage]
    state, _ = load_state(run_dir)
    lines = []
    universe = item_universe(run_dir, stage)
    if item_id not in universe:
        lines.append(f"stage {stage}: unknown item {item_id!r}; the stage's item "
                     f"universe comes from {spec.get('count_of')} "
                     f"({', '.join(universe) or 'no inventory found'})")
        return lines
    upstream = ITEM_FEEDS.get(stage)
    if upstream is None:
        # Prompt items: the stage's contract dependencies, item-scoped: the
        # depends_on stages closed, the requires_artifacts present.
        for dep in spec.get("depends_on", []):
            dep_state = state.get("stages", {}).get(dep, {})
            if dep_state.get("status") != "closed":
                lines.append(f"item {item_id} cannot start: stage dependency {dep} "
                             f"is not closed (status: "
                             f"{dep_state.get('status', 'not closed')})")
            else:
                lines.extend(verify_dep_receipt(run_dir, dep, state))
        for rel in spec.get("requires_artifacts", []):
            if not (run_dir / rel).exists():
                lines.append(f"item {item_id} cannot start: required artifact "
                             f"missing: {rel}")
        return lines
    # Generation items: the matching upstream ITEM must be closed (the weld
    # cut), and the upstream stage's structural (non-per-file) artifacts must
    # exist. The upstream STAGE does not have to be closed.
    want = _item_number(item_id)
    match = None
    for uid, entry in (state.get("items") or {}).get(upstream, {}).items():
        if _item_number(uid) == want:
            match = (uid, entry)
            break
    if match is None or match[1].get("status") != "closed":
        lines.append(f"item {item_id} cannot start: its {upstream} item "
                     f"(number {want}) is not closed")
    up_spec = STAGES[upstream]
    for art in up_spec.get("artifacts", []):
        if art["glob"] == up_spec.get("per_file_glob"):
            continue
        matches = sorted(run_dir.glob(art["glob"]))
        if len(matches) < art.get("min_count", 1):
            lines.append(f"item {item_id} cannot start: upstream structural "
                         f"artifact missing: {art['glob']}")
    return lines


def run_item_validators(run_dir, stage, artifact_rel):
    """Run the stage's validators against ONE item's file only (the same
    placeholder substitutions resolve_brand_placeholder performs for the
    per-file case, scoped to the single file)."""
    spec = STAGES[stage]
    failures = []
    brand = brand_path_for(run_dir)
    sauce = ""
    bible_path = run_dir / "visual-mockup" / "page-visual-bible.json"
    if bible_path.exists():
        try:
            bible = json.loads(bible_path.read_text(encoding="utf-8"))
            sauce = "--sauce-only" if bible.get("selection_mode") == "SECRET_SAUCE_ONLY" else ""
        except Exception:
            sauce = ""
    for raw in spec.get("validators", []):
        # Split the template ONCE, then substitute inside each argv entry, so a
        # run folder path containing spaces is never re-tokenized. A placeholder
        # that substitutes to nothing (an unengaged {sauce}) drops its token
        # exactly as it did when the command was a substituted string.
        substitutions = {
            "{run_dir}": str(run_dir),
            "{brand}": str(brand),
            "{file}": str(run_dir / artifact_rel),
            "{sauce}": sauce,
        }
        argv = substitute_argv(raw, substitutions)
        line = run_one_validator(argv, run_dir)
        if line:
            failures.append(line)
    return failures


def check_item_review(run_dir, stage, item_id, receipt):
    """Verify ONE item's Review Receipt v2 file: the per-item slice of
    check_review_scores, with Amendment 6 per-artifact scoring (this item's
    mean must meet min_scores.average and every criterion min_scores.each).
    Stage close re-verifies everything at fan-in; this replaces nothing."""
    spec = STAGES[stage]
    failures = []
    review_required = bool(spec.get("review_required")) or spec.get("min_scores") is not None
    if not review_required:
        return failures
    where = f"stage {stage} item {item_id}"
    review_item = item_review_item_id(run_dir, stage, item_id)
    if review_item is None:
        return [f"{where}: cannot locate the item's artifact, so its review "
                f"item id is unknown"]
    review_path = run_dir / "private" / "reviews" / stage / f"{review_item}.review.json"
    if not review_path.exists():
        return [f"{where}: missing review file private/reviews/{stage}/"
                f"{review_item}.review.json; uncovered items cannot close. Write "
                f"it with scripts/write_review.py from the reviewing session"]
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{where}: review file unreadable: {exc}"]
    if not isinstance(review, dict):
        return [f"{where}: review file is not a JSON object"]
    if review.get("item") != review_item:
        failures.append(f"{where}: review file item is {review.get('item')!r}, "
                        f"expected {review_item!r}")
    artifact_rel = item_artifact_rel(run_dir, stage, item_id)
    rel = review.get("artifact")
    if not isinstance(rel, str) or not rel:
        failures.append(f"{where}: review file names no artifact")
        rel = None
    if rel is not None and artifact_rel is not None and rel != artifact_rel:
        failures.append(f"{where}: review covers artifact {rel!r} but the item's "
                        f"artifact is {artifact_rel!r}")
    if rel is not None:
        artifact_path = run_dir / rel
        if not artifact_path.is_file():
            failures.append(f"{where}: reviewed artifact missing on disk: {rel}")
        else:
            actual = sha256_file(artifact_path)
            if actual != review.get("artifact_sha256"):
                failures.append(
                    f"{where}: artifact hash mismatch for {rel} (review recorded "
                    f"{str(review.get('artifact_sha256'))[:12]}..., on-disk "
                    f"{actual[:12]}...); the graded bytes changed after review")
    author_session = review.get("author_session")
    reviewer_session = review.get("reviewer_session")
    if _is_placeholder_session(author_session):
        failures.append(f"{where}: review author_session is missing or a "
                        f"placeholder ({author_session!r})")
    if _is_placeholder_session(reviewer_session):
        failures.append(f"{where}: review reviewer_session is missing or a "
                        f"placeholder ({reviewer_session!r}); reviews must be "
                        f"stamped by scripts/write_review.py from a real session")
    if (not _is_placeholder_session(author_session)
            and not _is_placeholder_session(reviewer_session)
            and reviewer_session == author_session):
        failures.append(f"{where}: reviewer_session equals author_session "
                        f"({reviewer_session!r}); review must be independent")
    receipt_author_session = receipt.get("author_session") or receipt.get("author_agent")
    if (not _is_placeholder_session(reviewer_session)
            and isinstance(receipt_author_session, str)
            and reviewer_session == receipt_author_session):
        failures.append(f"{where}: reviewer_session equals the stage receipt's "
                        f"author session ({receipt_author_session!r}); review "
                        f"must be independent")
    if review.get("verdict") != "pass":
        failures.append(f"{where}: review verdict is {review.get('verdict')!r}, "
                        f"not 'pass'")
    criteria = review.get("criteria")
    if not isinstance(criteria, dict) or not criteria:
        failures.append(f"{where}: review file carries no criteria scores")
        return failures
    scores = []
    for cname, entry in sorted(criteria.items()):
        if not isinstance(entry, dict):
            failures.append(f"{where}: criterion {cname!r} is not a "
                            f"{{score, note}} object")
            continue
        score = entry.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            failures.append(f"{where}: criterion {cname!r} score is not a number")
        else:
            scores.append((cname, float(score)))
        note = entry.get("note")
        if not isinstance(note, str) or not note.strip():
            failures.append(f"{where}: criterion {cname!r} has no evidence note")
        elif len(note.strip()) < MIN_REVIEW_NOTE_CHARS:
            failures.append(f"{where}: criterion {cname!r} note is "
                            f"{len(note.strip())} characters; at least "
                            f"{MIN_REVIEW_NOTE_CHARS} required")
    min_scores = spec.get("min_scores") or {}
    each = min_scores.get("each")
    if each is not None:
        for cname, value in scores:
            if value < each:
                failures.append(f"{where}: score below minimum {each}: "
                                f"criterion {cname} = {value:g}")
    avg = min_scores.get("average")
    if avg is not None:
        if not scores:
            failures.append(f"{where}: min_scores average {avg} required but "
                            f"the review carries no numeric criteria")
        else:
            mean = sum(v for _, v in scores) / len(scores)
            if mean < avg:
                failures.append(f"{where}: per-artifact average score {mean:.2f} "
                                f"across {len(scores)} criteria is below "
                                f"minimum {avg}")
    return failures


def check_item_transport(run_dir, stage, item_id, receipt):
    """Per-item slice of check_transport for close-item: the stage receipt's
    transport block must cover THIS item's file with a valid Skill 74 task.
    Stage close re-verifies the full task list at fan-in."""
    spec = STAGES[stage]
    if not spec.get("transport_required"):
        return []
    artifact_rel = item_artifact_rel(run_dir, stage, item_id)
    if artifact_rel is None and str(item_id) in _supplied_inventory_entries(run_dir):
        # Item 3 review defect D1: a supplied item whose file is missing
        # from disk has no on-disk glob match, so resolve its expected
        # path; the supplied slice below then reports the file as not
        # on disk instead of the slice never being reached.
        artifact_rel = expected_item_artifact_rel(stage, item_id)
    t = receipt.get("transport")
    if not isinstance(t, dict):
        return [f"stage {stage}: receipt missing transport block "
                f"(references/kie-generation-route.md section 3)"]
    skill = t.get("skill")
    # Item 28 step 3 transport alias, mirroring check_transport: on a
    # claude-nine run the 999 kie skill performs both roles.
    kie_alias = (skill == "kie"
                 and (intake_data(run_dir) or {}).get("runtime") == "claude-nine")
    if skill not in TRANSPORTS and not kie_alias:
        return [f"stage {stage}: transport.skill {skill!r} is not an approved "
                f"route {sorted(TRANSPORTS)}; a hand-rolled createTask is not"]
    policy, provider = TRANSPORTS[skill] if skill in TRANSPORTS else ("kie", "kie")
    problems = []
    if t.get("policy") != policy:
        problems.append(f"stage {stage}: transport.policy must be {policy!r}, "
                        f"got {t.get('policy')!r}")
    cost = receipt.get("cost")
    if isinstance(cost, dict) and cost.get("provider") != provider:
        problems.append(f"stage {stage}: cost.provider must be {provider!r} "
                        f"for {skill}, got {cost.get('provider')!r}")
    if skill == "63-agnes-image" and not _agnes_selected(run_dir):
        problems.append(f"stage {stage}: the Agnes route needs intake.json "
                        f"image_engine: \"agnes\" (the client must have "
                        f"selected Agnes)")
    if skill == "74-kie-live-adapter" and t.get("mode") != "active":
        problems.append(f"stage {stage}: transport.mode must be 'active' "
                        f"(shadow never dispatches), got {t.get('mode')!r}")
    if skill == "63-agnes-image":
        problems.extend(_agnes_transport_problems(stage, t))
    tasks = t.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return problems + [f"stage {stage}: transport.tasks must list one "
                           f"entry per generated file"]
    mine = [x for x in tasks
            if isinstance(x, dict) and str(x.get("file")) == artifact_rel]
    if not mine:
        return problems + [f"stage {stage} item {item_id}: transport.tasks "
                           f"has no entry for {artifact_rel}"]
    x = mine[0]
    who = f"stage {stage} item {item_id} ({artifact_rel})"
    if str(item_id) in _supplied_inventory_entries(run_dir):
        # Item 3: a supplied item's slice is satisfied by a
        # supplied-asset entry verified against the filed bytes,
        # never by a generation task.
        return problems + _supplied_transport_problems(
            run_dir, stage, item_id, artifact_rel, x)
    if skill == "63-agnes-image":
        # A23 Agnes branch, per-item slice: same rules as the stage check.
        problems.extend(_agnes_task_problems(who, x))
    if kie_alias and x.get("model_source") == "user-pin":
        # Validation-time vocabulary mapping (see check_transport).
        x = {**x, "model_source": "department-pin"}
    if skill == "74-kie-live-adapter" or kie_alias:
        if not _real_id(x.get("task_id")):
            problems.append(f"{who}: task_id {x.get('task_id')!r} is missing "
                            f"or a placeholder")
        else:
            f = _kie74_file(run_dir, x["task_id"])
            try:
                obj = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                problems.append(f"{who}: task_id {x['task_id']!r} has no "
                                f"readable {KIE74_DIR}/{f.name} (record it "
                                f"with kie74_receipt.py)")
            else:
                if kie_alias:
                    file_ok = (isinstance(obj, dict)
                               and obj.get("adapter") in ("74-kie-live-adapter", "kie")
                               and obj.get("task_id") == x["task_id"]
                               and obj.get("state") == "success")
                else:
                    file_ok = (isinstance(obj, dict)
                               and obj.get("adapter") == "74-kie-live-adapter"
                               and obj.get("task_id") == x["task_id"]
                               and obj.get("state") == "success"
                               and obj.get("adapter_mode") == "active")
                if not file_ok:
                    problems.append(f"{who}: {KIE74_DIR}/{f.name} is not a "
                                    f"successful active Skill 74 result for "
                                    f"{x['task_id']!r}")
        if x.get("preflight_ok") is not True:
            problems.append(f"{who}: preflight_ok must be true (balance "
                            f"covers price x 1.30)")
        if x.get("budget_exit") != 0:
            problems.append(f"{who}: budget_exit must be 0 "
                            f"(prompt-budget --check passed)")
        if not _real_id(x.get("model_id")):
            problems.append(f"{who}: model_id is missing")
        if x.get("model_source") not in MODEL_SOURCES:
            problems.append(f"{who}: model_source must be one of "
                            f"{list(MODEL_SOURCES)}")
        rp = _ratio_problem(who, x)
        if rp:
            problems.append(rp)
    return problems


def _require_itemized(stage):
    spec, errs = load_contract_stage(stage)
    if errs:
        return None, errs
    if not is_itemized(stage):
        return None, [f"stage {stage} is not itemized; item commands apply "
                      f"only to stages marked \"itemized\": true in the "
                      f"contract ({', '.join(s for s in ORDER if is_itemized(s))}). "
                      f"Use check/close for whole-stage flow."]
    return spec, []


def cmd_check_item(run_dir, stage, item_id):
    spec, errs = _require_itemized(stage)
    if errs:
        return fail_exit(errs)
    entry = item_state(run_dir, stage, item_id)
    if entry.get("status") == "closed":
        print(f"PASS: item {item_id} of stage {stage} is already closed")
        return 0
    if entry.get("status") == "blocked":
        return fail_exit([f"item {item_id} of stage {stage} is blocked: "
                          f"{entry.get('blocked_reason', 'no reason recorded')}"])
    failures = item_dependency_failures(run_dir, stage, item_id) + brand_color_failures(run_dir, stage)
    if failures:
        return fail_exit(failures)
    print(f"PASS: item {item_id} of stage {stage} may start (its own "
          f"dependencies are satisfied; the stage need not be closed)")
    return 0


def cmd_close_item(run_dir, stage, item_id):
    spec, errs = _require_itemized(stage)
    if errs:
        return fail_exit(errs)
    failures = item_dependency_failures(run_dir, stage, item_id)
    artifact_rel = item_artifact_rel(run_dir, stage, item_id)
    if artifact_rel is None:
        failures.append(f"stage {stage} item {item_id}: artifact not found "
                        f"(per-file glob {spec.get('per_file_glob')!r}, numeric "
                        f"suffix {_item_number(item_id)})")
    entry = item_state(run_dir, stage, item_id)
    if entry.get("status") == "closed" and artifact_rel is not None:
        recorded = (entry.get("artifact_hashes") or {}).get(artifact_rel)
        if recorded == sha256_file(run_dir / artifact_rel):
            print(f"PASS: item {item_id} of stage {stage} is already closed "
                  f"(artifact unchanged)")
            return 0
        failures.append(f"stage {stage} item {item_id}: item is closed but "
                        f"its artifact changed after close; the item's review "
                        f"must be redone against the new bytes")
    status, receipt, rlines = receipt_status(run_dir, stage)
    failures.extend(rlines)
    if not receipt:
        failures.append(f"stage {stage}: no receipt at "
                        f"private/receipts/{stage}.json; the stage's agents "
                        f"must write it before item close")
    elif receipt.get("status") == "fail":
        failures.append(f"stage {stage}: receipt status is 'fail'; item "
                        f"close refused")
    if not failures:
        failures.extend(run_item_validators(run_dir, stage, artifact_rel))
        failures.extend(check_item_review(run_dir, stage, item_id, receipt))
        failures.extend(check_cost(run_dir, stage, receipt))
        failures.extend(check_item_transport(run_dir, stage, item_id, receipt))
    if failures:
        return fail_exit(failures)
    record_item_close(run_dir, stage, item_id, artifact_rel)
    print(f"CLOSED item: {item_id} of stage {stage} (artifact verified, item "
          f"validators re-run by the gate, item review checked)")
    return 0


def _prompt_budget_record(prompt_path):
    """Best-effort Decision 1 budget record for a prompt artifact.

    Runs validate_prompt.inspect() on the file (default model, no run
    context, matching how the stage contract invokes the validator)
    and returns {"characters", "percent_of_max", "budget"} for the
    close entry. Any failure returns None: recording the budget never
    blocks a close that has already passed its validators.
    """
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "skill71_validate_prompt", SKILL_ROOT / "scripts" / "validate_prompt.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result = mod.inspect(Path(prompt_path).read_text(encoding="utf-8"))
        telemetry = result["telemetry"]
        return {"characters": telemetry["characters"],
                "percent_of_max": telemetry["percent_of_max"],
                "budget": telemetry["budget"]}
    except Exception:
        return None


def record_item_close(run_dir, stage, item_id, artifact_rel):
    state, _ = load_state(run_dir)
    review_item = item_review_item_id(run_dir, stage, item_id)
    review_rel = f"private/reviews/{stage}/{review_item}.review.json"
    review_path = run_dir / review_rel
    entry = {
        "status": "closed",
        "closed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "artifact_hashes": {artifact_rel: sha256_file(run_dir / artifact_rel)},
        "review": review_rel if review_path.exists() else None,
        "review_item": review_item,
    }
    if review_path.exists():
        entry["review_hash"] = sha256_file(review_path)
    if stage == "image-inventory-prompts":
        budget_record = _prompt_budget_record(run_dir / artifact_rel)
        if budget_record is not None:
            entry["prompt_budget"] = budget_record
    state.setdefault("items", {}).setdefault(stage, {})[item_id] = entry
    save_state(run_dir, state)
    emit_event(run_dir, {"event_type": "item_closed", "stage": stage,
                         "item_id": item_id, "closed_at": entry["closed_at"],
                         "artifact_hash": entry["artifact_hashes"][artifact_rel]})


def cmd_block_item(run_dir, stage, item_id, reason):
    spec, errs = _require_itemized(stage)
    if errs:
        return fail_exit(errs)
    if item_id not in item_universe(run_dir, stage):
        return fail_exit([f"stage {stage}: unknown item {item_id!r}"])
    state, _ = load_state(run_dir)
    entry = state.setdefault("items", {}).setdefault(stage, {}).setdefault(item_id, {})
    entry["status"] = "blocked"
    entry["blocked_reason"] = reason
    entry["blocked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_state(run_dir, state)
    emit_event(run_dir, {"event_type": "item_blocked", "stage": stage,
                         "item_id": item_id, "failures": [reason],
                         "blocked_at": entry["blocked_at"]})
    print(f"BLOCKED item: {item_id} of stage {stage}: {reason}")
    return 0


# ---------------------------------------------------------------------------
# Browser teardown and hygiene gate (fix plan Item 33).
#
# A stage whose contract entry carries "uses_browser": true (today
# ghl-install-test, publish-verify, and automation-wiring), and any
# stage the session registry holds sessions for, may not close until
# the reaper pass has
# accounted for every browser session the run opened for it. The
# registry, probe, reaper, and receipt writer live in
# scripts/browser_sessions.py, loaded by path the way validators resolve
# against the skill root; the gate owns the verdict: unaccounted above
# zero refuses the close, naming the sessions, and headed launches
# refuse it too unless an owner override is on record in the receipt.
# The pass runs before anything else in check and close (Item 33 HOW 2:
# the gate is the recovery path when the runner died before teardown).
# cmd_report prints the plan's REPORT.md line and, when a REPORT.json
# already exists, fills its frozen hygiene object (S6 Item 25,
# references/report-json.schema.json) from the same roll-up the Item 25
# writer uses: report_hygiene_object() below.

def _browser_sessions_module():
    path = SKILL_ROOT / "scripts" / "browser_sessions.py"
    if not path.exists():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "skill71_browser_sessions", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _page_result_module():
    path = SKILL_ROOT / "scripts" / "page_result.py"
    if not path.exists():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "skill71_page_result", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _automation_handoff_module():
    path = SKILL_ROOT / "scripts" / "automation_handoff.py"
    if not path.exists():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "skill71_automation_handoff", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def emit_install_handoff(run_dir):
    """R71H producer side (Item 31, S71-08 P1): at ghl-install-test
    close, emit handoff/automation-handoff.json from the run's records
    (funnel-completion form IDs are the sole form source) and hash-lock
    it, then check_install_handoff verifies what was written. Returns
    failure lines; an emitter refusal refuses the close."""
    mod = _automation_handoff_module()
    if mod is None:
        if intake_data(run_dir).get("publish_target") == "ghl":
            return ["stage ghl-install-test: the automation hand-off "
                    "cannot be produced: scripts/automation_handoff.py "
                    "is missing from the skill; a GHL install cannot "
                    "close without its R71H emitter"]
        return []
    failures, _record = mod.emit_handoff(
        run_dir, deploy_mode=mod.ONLY_DEPLOY_MODE, requesting_room="S71")
    return failures


def stage_uses_browser(run_dir, stage):
    if STAGES[stage].get("uses_browser"):
        return True
    # Conditional browser use (publish-verify when a browser produced
    # its evidence): sessions on record make the stage accountable.
    mod = _browser_sessions_module()
    return bool(mod and mod.stage_has_sessions(run_dir, stage))


def browser_hygiene_pass(run_dir, stage):
    """Reaper sweep + receipt for one stage; returns failure lines."""
    mod = _browser_sessions_module()
    if mod is None:
        return [f"stage {stage}: browser hygiene cannot be verified: "
                f"scripts/browser_sessions.py is missing from the skill; "
                f"a browser-using stage cannot close without the Item 33 "
                f"session accounting"]
    receipt = mod.sweep_and_receipt(run_dir, stage)
    lines = []
    if receipt["unaccounted"] > 0:
        names = ", ".join(receipt.get("_unaccounted_names") or [])
        lines.append(
            f"stage {stage}: browser hygiene: {receipt['unaccounted']} "
            f"session(s) unaccounted ({names}); every browser session "
            f"must be torn down or reaped before the stage closes "
            f"(Item 33)")
    if receipt["headed_launches"] > 0 \
            and not receipt.get("owner_override_headed"):
        lines.append(
            f"stage {stage}: browser hygiene: "
            f"{receipt['headed_launches']} headed browser launch(es) "
            f"recorded and no owner override is on record in "
            f"{stage}/browser-hygiene.json; headed launches violate the "
            f"Browser Engine Contract (Item 33)")
    return lines


def report_hygiene_object(run_dir):
    """The run's REPORT.json hygiene object (frozen field names, S6):
    recorded counts summed from the per-stage browser-hygiene.json
    receipts, or status not_recorded with null counts when no stage
    receipt exists."""
    mod = _browser_sessions_module()
    if mod is None:
        return {"status": "not_recorded", "opened": None, "closed": None,
                "orphans_found": None, "reaped": None,
                "unaccounted": None, "headed_launches": None}
    return mod.run_rollup(run_dir, ORDER)


def cmd_init(run_dir):
    intake = run_dir / "intake.json"
    if not intake.exists():
        return fail_exit([f"init requires {intake} (the intake stage writes it)"])
    state, _ = load_state(run_dir)
    (run_dir / "private" / "receipts").mkdir(parents=True, exist_ok=True)
    # Item 24 (S6 emission spec 6.1): mint the run_id when the run has
    # none and record the run identity; re-running init on an existing
    # run emits nothing.
    fresh = not state.get("run_id")
    if fresh:
        idata = intake_data(run_dir)
        state["run_id"] = str(uuid.uuid4())
        for key in ("page_name", "brand_id", "client"):
            if idata.get(key) is not None:
                state[key] = idata[key]
        state["host_shape"] = host_shape()
    save_state(run_dir, state)
    if fresh:
        idata = intake_data(run_dir)
        event = {"event_type": "run_initialized", "host_shape": state["host_shape"],
                 "test_run": bool(idata.get("test_run"))}
        for key in ("page_name", "brand_id", "client"):
            if state.get(key) is not None:
                event[key] = state[key]
        emit_event(run_dir, event)
        # Item 11 rider (spec 6.7): a drift recorded by a provisioning
        # time pin check with no run context enters the feed of the
        # first run initialized afterward, while it is still outstanding.
        drift_path = run_dir / "private" / "pin-drift.json"
        if drift_path.is_file():
            try:
                records = json.loads(drift_path.read_text(encoding="utf-8"))
            except Exception:
                records = []
            for rec in records if isinstance(records, list) else []:
                if isinstance(rec, dict) and rec.get("authority_id"):
                    emit_event(run_dir, {
                        "event_type": "pin_drift",
                        "authority_id": rec["authority_id"],
                        "pinned_sha": rec.get("pinned_sha"),
                        "observed_sha": rec.get("observed_sha")})
    print(f"PASS: run initialized at {run_dir}")
    print(f"  state: {run_dir / 'private' / 'state.json'}")
    print(f"  receipts dir: {run_dir / 'private' / 'receipts'}")
    return 0


# ---------------------------------------------------------------------------
# S5 delivery and funnel checks (fix plan Items 5, 6, 31, 32, 34).
# ---------------------------------------------------------------------------

def intake_data(run_dir):
    try:
        data = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def receipt_at(run_dir, stage):
    try:
        data = json.loads((run_dir / "private" / "receipts" / f"{stage}.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def automation_wiring_applicability(run_dir):
    """Item 31: automation-wiring is required exactly when the intake says
    the page publishes into GHL and the automation scope is workflows."""
    intake = intake_data(run_dir)
    pt, scope = intake.get("publish_target"), intake.get("automation_scope")
    required = pt == "ghl" and scope == "workflows"
    reason = (f"intake.publish_target={pt!r}, intake.automation_scope={scope!r}: "
              f"automation-wiring is required only when publish_target is \"ghl\" "
              f"and automation_scope is \"workflows\" (fix plan Item 31)")
    return required, reason


def record_not_applicable(run_dir, stage, reason):
    state, _ = load_state(run_dir)
    state["stages"][stage] = {
        "status": "not_applicable",
        "receipt_status": "not_applicable",
        "reason": reason,
        "closed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    save_state(run_dir, state)


def check_install_handoff(run_dir):
    """Item 31 hand-off at ghl-install-test close: Skill 6 records
    handoff/automation-handoff.json (IDs only, never credentials), and its
    form IDs come from Item 32's funnel-completion receipt and nowhere
    else. The hand-off hash is recorded into state at close (record_close)
    and publish-verify verifies the file is unchanged."""
    intake = intake_data(run_dir)
    if intake.get("publish_target") != "ghl":
        return []
    failures = []
    hp = run_dir / "handoff" / "automation-handoff.json"
    if not hp.is_file():
        return [f"stage ghl-install-test: GHL publish target requires "
                f"handoff/automation-handoff.json at close (fix plan Item 31): "
                f"location, funnel, page, and form IDs only, never credentials"]
    try:
        handoff = json.loads(hp.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"stage ghl-install-test: handoff/automation-handoff.json unreadable: {exc}"]
    for key in ("location_id", "funnel_id", "page_id"):
        if not handoff.get(key):
            failures.append(f"stage ghl-install-test: hand-off is missing {key}")
    handoff_forms = handoff.get("forms")
    if not isinstance(handoff_forms, list) or not handoff_forms:
        failures.append("stage ghl-install-test: hand-off lists no forms")
        handoff_forms = []
    fc = {}
    try:
        fc = json.loads((run_dir / "ghl-install-test" / "funnel-completion.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    if isinstance(fc, dict) and fc.get("status") != "not_applicable":
        fc_ids = {f.get("form_id") for f in fc.get("forms") or [] if isinstance(f, dict)}
        ho_ids = {f.get("form_id") for f in handoff_forms if isinstance(f, dict)}
        if fc_ids != ho_ids:
            failures.append(f"stage ghl-install-test: hand-off form IDs {sorted(map(str, ho_ids))} "
                            f"do not equal funnel-completion.json form IDs "
                            f"{sorted(map(str, fc_ids))}; Item 32's receipt is the sole "
                            f"source of the hand-off's form IDs (fix plan Item 31)")
    if intake.get("automation_scope") == "workflows" and "conversational_requirements" not in handoff:
        failures.append("stage ghl-install-test: hand-off carries no "
                        "conversational_requirements (Item 31 conversational rider)")
    return failures


def check_parity_evidence(run_dir):
    """Update Plan Item 16: the approved final mockup is the design source
    of truth for the responsive-html stage, and the stage closes only on
    parity evidence against it: the side-by-side parity sheets at 1440
    and 390 (scripts/compare_sheet.py) and its structural drift table in
    responsive-html/compare/compare-report.json, whose drift status must
    be "pass". A missing sheet, a missing report, or a drift status of
    fail / skipped-no-html / unavailable-playwright blocks the close by
    name: a page that drifted from its approved mockup, or whose drift
    was never measured, does not close on internal consistency alone.
    A stage-close hook (not a contract validator) because the report is
    a run-level record the validator itself writes."""
    failures = []
    compare_dir = run_dir / "responsive-html" / "compare"
    for width in (1440, 390):
        if not list(compare_dir.glob(f"compare-{width}-*.png")):
            failures.append(
                f"stage responsive-html: parity evidence missing: no "
                f"side-by-side parity sheet at {width}px "
                f"(responsive-html/compare/compare-{width}-*.png); the "
                f"parity sheet at 1440 and 390 is required close evidence "
                f"against the approved final mockup (Update Plan Item 16)")
    report_path = compare_dir / "compare-report.json"
    if not report_path.is_file():
        failures.append(
            "stage responsive-html: parity evidence missing: "
            "responsive-html/compare/compare-report.json (the "
            "compare_sheet.py structural drift table) is not on record; "
            "the stage cannot close without the drift table (Update "
            "Plan Item 16)")
        return failures
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        failures.append(
            f"stage responsive-html: compare-report.json unreadable: {exc}")
        return failures
    drift = report.get("drift") if isinstance(report, dict) else None
    status = drift.get("status") if isinstance(drift, dict) else None
    if status != "pass":
        failures.append(
            f"stage responsive-html: structural drift table status is "
            f"{status!r}, not 'pass'; named drift failures block close "
            f"(Update Plan Item 16)")
        if isinstance(drift, dict):
            for width, block in (drift.get("widths") or {}).items():
                if isinstance(block, dict):
                    for line in block.get("failures") or []:
                        failures.append(
                            f"stage responsive-html: [{width}px] {line}")
    return failures


def check_publish_rules(run_dir, receipt):
    """Item 6 publish discipline, enforced at a publish-verify PASS close,
    plus Item 31's hand-off carry-forward check."""
    failures = []
    if receipt.get("status") != "pass":
        return failures
    intake = intake_data(run_dir)
    # Rule 1: a test run never closes as a production delivery.
    if intake.get("test_run"):
        failures.append("stage publish-verify: intake.test_run is true; a test run "
                        "cannot close publish-verify as a production pass (fix plan "
                        "Item 6). Close as not_authorized, or run production with "
                        "test_run false.")
    # Rule 2: derived fonts require an independent font review. When the
    # bible's fonts came from the derive path, the bible's font_reviewer
    # session must differ from the session that authored the font map
    # (Item 2 session rules).
    bible = {}
    try:
        bible = json.loads((run_dir / "visual-mockup" / "page-visual-bible.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    if isinstance(bible, dict) and bible.get("fonts_source") == "derived":
        reviewer = bible.get("font_reviewer")
        fap = receipt_at(run_dir, "font-action-plan")
        author_session = fap.get("author_session") or fap.get("author_agent")
        if _is_placeholder_session(reviewer):
            failures.append("stage publish-verify: the visual bible's fonts are derived "
                            "(fonts_source \"derived\") but the bible names no real "
                            "font_reviewer session; derived fonts require an independent "
                            "font review record (fix plan Item 6)")
        elif not _is_placeholder_session(author_session) and reviewer == author_session:
            failures.append(f"stage publish-verify: the bible's font_reviewer session "
                            f"({reviewer!r}) is the same session that authored the font "
                            f"map; the font identity decision requires an independent "
                            f"reviewer (fix plan Item 6, Item 2 session rules)")
    # Rule 3: OWNER-ORDERED SCOPE CHANGE (Amendment 6, C11). Brand Law
    # designs the uncalibrated-grade state as WARN-only. Trevor's Order 4(b)
    # overrides that design for production closes: the pixel grade gate
    # ships ON and fails CLOSED, so a production publish-verify refuses to
    # close while the brand file's grade thresholds are uncalibrated. The
    # only release is a recorded owner waiver in the receipt; any waiver
    # prints in REPORT.md (collect_warnings below). A conforming Brand Law
    # text amendment is queued in Item 30.
    brand = brand_path_for(run_dir)
    try:
        b = json.loads(brand.read_text(encoding="utf-8"))
        grade = b.get("grade") or {}
        uncalibrated = grade.get("min_mean_saturation") is None or grade.get("min_luma_std") is None
    except Exception:
        uncalibrated = False
    if uncalibrated:
        waivers = receipt.get("publish_waivers") or []
        waived = any(isinstance(w, dict)
                     and w.get("rule") == "uncalibrated_grade_thresholds"
                     and w.get("approved_by") == "owner"
                     and isinstance(w.get("reason"), str) and w["reason"].strip()
                     for w in waivers)
        if not waived:
            failures.append(f"stage publish-verify: brand grade thresholds are "
                            f"uncalibrated in {brand.name} (grade.min_mean_saturation / "
                            f"grade.min_luma_std are null); production close refused "
                            f"under the owner-ordered grade gate (fix plan Item 6, "
                            f"Amendment 6 C11). Calibrate the gold set (Item 8) or "
                            f"record an owner waiver in the receipt's publish_waivers; "
                            f"a waiver prints in REPORT.md.")
    # Item 31: publish-verify carries the automation hand-off forward
    # unchanged; the hash recorded at ghl-install-test close must match.
    # R71H seam P2 completes the gate: on a GHL run a missing locked
    # hash refuses by name too (there is nothing to verify the carried
    # file against), and a mismatch names both hashes.
    state, _ = load_state(run_dir)
    recorded = (state.get("stages", {}).get("ghl-install-test") or {}).get("handoff_sha256")
    if recorded:
        hp = run_dir / "handoff" / "automation-handoff.json"
        if not hp.is_file():
            failures.append("stage publish-verify: handoff/automation-handoff.json is "
                            "missing; publish-verify carries the install hand-off "
                            "forward unchanged (fix plan Item 31)")
        else:
            actual = sha256_file(hp)
            if actual != recorded:
                failures.append("stage publish-verify: handoff/automation-handoff.json "
                                "changed after ghl-install-test close (SHA-256 mismatch: "
                                f"the hash locked at ghl-install-test close is {recorded}, "
                                f"the file on disk hashes to {actual}); the hand-off is "
                                "carried forward unchanged (fix plan Item 31)")
    elif intake.get("publish_target") == "ghl":
        failures.append("stage publish-verify: no hand-off hash is locked in state "
                        "(stages.ghl-install-test.handoff_sha256 is absent); a GHL "
                        "run's publish close verifies handoff/automation-handoff.json "
                        "against the hash locked at ghl-install-test close, and there "
                        "is no locked hash to verify against (fix plan Item 31)")
    return failures


def derive_conversational_triggers(run_dir):
    """Item 31 conversational rider: the trigger set is derived from Item
    32's funnel-completion receipt, never hand-listed. One opt-in trigger
    per opt-in form, one purchase trigger per bound order form, one
    booking trigger per booking or calendar step."""
    fc = {}
    try:
        fc = json.loads((run_dir / "ghl-install-test" / "funnel-completion.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    triggers = []
    if isinstance(fc, dict) and fc.get("status") != "not_applicable":
        for f in fc.get("forms") or []:
            if isinstance(f, dict) and f.get("form_id"):
                triggers.append({"trigger": "opt-in", "source_id": f["form_id"]})
        for o in fc.get("order_forms") or []:
            if isinstance(o, dict) and o.get("bound") is True and o.get("order_form_id"):
                triggers.append({"trigger": "purchase", "source_id": o["order_form_id"]})
        for s in fc.get("steps") or []:
            if isinstance(s, dict) and s.get("type") in ("booking", "calendar"):
                triggers.append({"trigger": "booking",
                                 "source_id": s.get("step_id") or s.get("name")})
    return triggers


def check_automation_wiring(run_dir, receipt):
    """Item 31 verification of the automation-wiring receipt against the
    hand-off and the derived conversational trigger set."""
    failures = []
    hp = run_dir / "handoff" / "automation-handoff.json"
    try:
        handoff = json.loads(hp.read_text(encoding="utf-8"))
    except Exception:
        return ["stage automation-wiring: handoff/automation-handoff.json is missing "
                "or unreadable; the stage executes against that hand-off and "
                "nothing else (fix plan Item 31)"]
    workflows = receipt.get("workflows")
    if not isinstance(workflows, list):
        failures.append("stage automation-wiring: receipt carries no workflows array")
        workflows = []
    covered = {}
    for w in workflows:
        if not isinstance(w, dict):
            failures.append("stage automation-wiring: workflow entry is not an object")
            continue
        name = w.get("name") or w.get("workflow_id") or "?"
        if not w.get("workflow_id"):
            failures.append(f"stage automation-wiring: workflow {name!r} records no workflow_id")
        trig = w.get("trigger") or {}
        if trig.get("type") != "form_submitted" or not trig.get("form_id"):
            failures.append(f"stage automation-wiring: workflow {name!r} trigger must be "
                            f"{{type: \"form_submitted\", form_id}}")
        else:
            covered[trig["form_id"]] = w
        if w.get("build_method") not in ("caf-cli", "tier4-browser-backstop"):
            failures.append(f"stage automation-wiring: workflow {name!r} build_method must be "
                            f"\"caf-cli\" (Tier 0, primary) or \"tier4-browser-backstop\", "
                            f"got {w.get('build_method')!r}")
        qc = w.get("qc") or {}
        if qc.get("script") != "qc-built-workflow.sh":
            failures.append(f"stage automation-wiring: workflow {name!r} qc.script must be "
                            f"Skill 44's qc-built-workflow.sh")
        if qc.get("exit_code") != 0:
            failures.append(f"stage automation-wiring: workflow {name!r} QC exit_code is "
                            f"{qc.get('exit_code')!r}, must be 0")
        if qc.get("checklist_complete") is not True:
            failures.append(f"stage automation-wiring: workflow {name!r} checklist is not "
                            f"recorded complete")
        inst = qc.get("checklist_instance")
        if not inst or not (run_dir / inst).is_file():
            failures.append(f"stage automation-wiring: workflow {name!r} QC checklist "
                            f"instance {inst!r} is not on disk (a filled checklist "
                            f"instance is a required artifact under automation-wiring/)")
        rb = w.get("readback") or {}
        if rb.get("exists") is not True:
            failures.append(f"stage automation-wiring: workflow {name!r} read-back does "
                            f"not confirm the workflow exists")
    exceptions = {}
    for e in receipt.get("form_exceptions") or []:
        if isinstance(e, dict) and e.get("form_id"):
            exceptions[e["form_id"]] = e
    for form in handoff.get("forms") or []:
        fid = form.get("form_id") if isinstance(form, dict) else None
        if fid and fid not in covered:
            ex = exceptions.get(fid)
            if not (ex and isinstance(ex.get("no_workflow_reason"), str)
                    and ex["no_workflow_reason"].strip()):
                failures.append(f"stage automation-wiring: hand-off form {fid} is neither "
                                f"trigger-covered by a recorded workflow nor carrying an "
                                f"explicit no_workflow_reason")
    # Amendment 4 credential scope: workflow writes through the caf CLI
    # need the Firebase refresh token; without it, and without a declared
    # backstop, only the backstop may have built the workflows.
    intake = intake_data(run_dir)
    creds = intake.get("credentials") or {}
    firebase_present = (creds.get("firebase_refresh_token") or {}).get("present")
    if firebase_present is False and not intake.get("firebase_backstop_declared"):
        for w in workflows:
            if isinstance(w, dict) and w.get("build_method") == "caf-cli":
                failures.append(f"stage automation-wiring: workflow {w.get('name')!r} was "
                                f"built via caf-cli but intake records the Firebase "
                                f"refresh token absent and no Tier 4 backstop declared; "
                                f"workflow writes require the token or the recorded "
                                f"backstop (Amendment 4 credential rider)")
    # Conversational rider: every derived trigger maps to a workflow with a
    # named Skill 38 playbook on SMS and email tracks, or a recorded owner
    # override (printed in REPORT.md by collect_warnings).
    triggers = derive_conversational_triggers(run_dir)
    conv = {}
    for c in receipt.get("conversational") or []:
        if isinstance(c, dict):
            conv[(c.get("trigger"), c.get("source_id"))] = c
    overrides = {}
    for o in receipt.get("conversational_overrides") or []:
        if isinstance(o, dict):
            overrides[(o.get("trigger"), o.get("source_id"))] = o
    derived_classes = set()
    for t in triggers:
        derived_classes.add(t["trigger"])
        key = (t["trigger"], t["source_id"])
        entry = conv.get(key)
        if entry is None:
            ov = overrides.get(key)
            if not (ov and ov.get("approved_by") == "owner"
                    and isinstance(ov.get("reason"), str) and ov["reason"].strip()):
                failures.append(f"stage automation-wiring: conversational trigger "
                                f"{t['trigger']} on {t['source_id']} maps to no workflow "
                                f"with a Skill 38 playbook, and no owner override is "
                                f"recorded (Item 31 conversational rider)")
            continue
        pb = entry.get("playbook") or {}
        if pb.get("system") != "38-conversational-ai-system" or not pb.get("playbook_name"):
            failures.append(f"stage automation-wiring: conversational entry for "
                            f"{t['trigger']} on {t['source_id']} names no Skill 38 "
                            f"playbook (system \"38-conversational-ai-system\" plus a "
                            f"playbook_name)")
        channels = set(pb.get("channels") or entry.get("channels") or [])
        if not {"sms", "email"} <= channels:
            failures.append(f"stage automation-wiring: conversational entry for "
                            f"{t['trigger']} on {t['source_id']} must carry SMS and "
                            f"email tracks, got {sorted(channels)}")
        doc = pb.get("doc_artifact") or entry.get("doc_artifact")
        if doc and not (run_dir / doc).is_file():
            failures.append(f"stage automation-wiring: playbook document {doc!r} for "
                            f"{t['trigger']} on {t['source_id']} is not on disk")
        if not entry.get("workflow_id"):
            failures.append(f"stage automation-wiring: conversational entry for "
                            f"{t['trigger']} on {t['source_id']} names no workflow_id")
    not_present = set(receipt.get("conversational_not_present") or [])
    for cls in ("opt-in", "purchase", "booking"):
        if cls not in derived_classes and cls not in not_present:
            failures.append(f"stage automation-wiring: trigger class {cls!r} has no "
                            f"instance in this funnel and is not recorded "
                            f"conversational_not_present")
    # Row 9: the GHL pack (Skills 6 + 44 + 38's conversational layer) ships
    # and is versioned as ONE decision; a wiring run records its version.
    if workflows and not receipt.get("ghl_pack_version"):
        failures.append("stage automation-wiring: receipt records no ghl_pack_version "
                        "(the GHL pack, Skills 6 + 44 + 38 conversational layer, is "
                        "versioned as one)")
    return failures


def test_run_flag(run_dir):
    return bool(intake_data(run_dir).get("test_run"))


def run_deliverables_check(run_dir):
    """Item 34: run scripts/check_deliverables.py against the run and
    return (ok, summary, failures)."""
    import subprocess
    cmd = [sys.executable, str(SKILL_ROOT / "scripts" / "check_deliverables.py"),
           str(run_dir), "--json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        data = json.loads(proc.stdout or "{}")
        return bool(data.get("ok")), data.get("summary") or {}, data.get("failures") or []
    except Exception as exc:
        return False, {}, [f"deliverables checker could not run: {exc}"]


def cmd_check(run_dir, stage):
    spec, errs = load_contract_stage(stage)
    if errs:
        return fail_exit(errs)
    if stage_uses_browser(run_dir, stage):
        hygiene_failures = browser_hygiene_pass(run_dir, stage)
        if hygiene_failures:
            return fail_exit(hygiene_failures)
    failures = check_requires(run_dir, stage) + brand_color_failures(run_dir, stage)
    failures += design_board_start_failures(run_dir, stage)
    if failures:
        return fail_exit(failures)
    print(f"PASS: stage {stage} may start (all dependencies closed with matching receipts and artifacts)")
    return 0


def cmd_close(run_dir, stage):
    spec, errs = load_contract_stage(stage)
    if errs:
        return fail_exit(errs)
    # Item 19: a stage that places supplied assets carries any UNDERSIZED
    # flag in its close evidence. The flag never blocks the close.
    if stage in SUPPLIED_PLACING_STAGES:
        for line in supplied_size_flag_lines(run_dir):
            print(line)
    # Item 31: a conditional stage that does not apply closes as
    # not_applicable, recorded in state (and cited in REPORT.md), never
    # silently skipped and never forced through the receipt machinery.
    if stage == "automation-wiring":
        required, reason = automation_wiring_applicability(run_dir)
        if not required:
            record_not_applicable(run_dir, stage, reason)
            print(f"NOT APPLICABLE: stage {stage} recorded in state.json ({reason})")
            return 0
    failures = brand_color_failures(run_dir, stage)
    # Item 33: the reaper pass runs before anything else is evaluated,
    # so a run whose runner died still gets its sessions accounted, and
    # the receipt it writes satisfies the stage's artifact contract.
    if stage_uses_browser(run_dir, stage):
        failures.extend(browser_hygiene_pass(run_dir, stage))
    status, receipt, rlines = receipt_status(run_dir, stage)
    failures.extend(rlines)
    if not receipt:
        failures.append(f"stage {stage}: no receipt at private/receipts/{stage}.json; "
                        f"the stage's agents must write it before close")
    receipt_status_val = receipt.get("status") if receipt else None
    if receipt_status_val == "fail":
        failures.append(f"stage {stage}: receipt status is 'fail'; close refused")
    # R71H seam P2: a filed dispatch refusal is itself a close verdict
    # for automation-wiring. The receipt records the receiver's refusal
    # reason verbatim; the stage stays open and the close names the
    # refusal, whatever else the close would find.
    if stage == "automation-wiring" and receipt:
        refusal = receipt.get("dispatch_refusal")
        if isinstance(refusal, dict) and str(refusal.get("reason") or "").strip():
            failures.append(f"stage automation-wiring: the automation dispatch was "
                            f"refused: {refusal['reason']} (refusal filed in "
                            f"private/receipts/automation-wiring.json; a refused "
                            f"dispatch leaves the stage open, R71H seam packet "
                            f"section 4)")

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
        # Itemized stages (Item 20): stage close is fan-in verification:
        # every item in the universe must be closed at item level first.
        if is_itemized(stage):
            state, _ = load_state(run_dir)
            for uid in item_universe(run_dir, stage):
                entry = (state.get("items") or {}).get(stage, {}).get(uid, {})
                if entry.get("status") == "blocked":
                    failures.append(f"stage {stage}: fan-in: item {uid} is blocked: "
                                    f"{entry.get('blocked_reason', 'no reason recorded')}")
                elif entry.get("status") != "closed":
                    failures.append(f"stage {stage}: fan-in: item {uid} is not closed "
                                    f"at item level (close it with close-item)")
        # Re-run validators
        failures.extend(run_validators(run_dir, stage, receipt))
        # Review / scores / cost
        failures.extend(check_review_scores(run_dir, stage, receipt))
        failures.extend(check_cost(run_dir, stage, receipt))
        failures.extend(check_transport(run_dir, stage, receipt))
        # S5 delivery rules (Items 6, 31)
        if stage == "responsive-html":
            failures.extend(check_parity_evidence(run_dir))
        elif stage == "ghl-install-test":
            failures.extend(emit_install_handoff(run_dir))
            failures.extend(check_install_handoff(run_dir))
        elif stage == "publish-verify":
            failures.extend(check_publish_rules(run_dir, receipt))
        elif stage == "automation-wiring":
            failures.extend(check_automation_wiring(run_dir, receipt))
        # Item 13 / S3 Request 2, as amended by Item 17: layout
        # reference RESOLUTION at wireframe and mockup close (original
        # file, registered house default, or recorded waiver; the
        # failure path is in layout_gate_failures).
        if stage in LAYOUT_GATE_STAGES:
            failures.extend(layout_gate_failures(run_dir))
        # GCR-S2-4 (Item 10, Amendment 6 Part B1): the style selection
        # record must exist, conform, and govern every inventory image
        # before image-inventory-prompts can close. A stage-close hook
        # (not a contract validator) because contract validators also
        # run per item under Item 20, and the record is a run-level
        # property.
        if stage == "image-inventory-prompts":
            failures.extend(style_selection_problems(run_dir))

    if failures:
        # Item 25 (S6 emission spec 6.4): a refused close is a state
        # transition too; emit stage_blocked with the failure lines.
        emit_event(run_dir, {"event_type": "stage_blocked", "stage": stage,
                             "failures": list(failures),
                             "blocked_at": datetime.now(timezone.utc).strftime(
                                 "%Y-%m-%dT%H:%M:%SZ")})
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
    # Item 2: record the v2 review files' hashes too, so a review edited
    # after close fails the downstream hash check like a changed artifact.
    review_hashes = {}
    reviews_dir = run_dir / "private" / "reviews" / stage
    if reviews_dir.is_dir():
        for p in sorted(reviews_dir.glob("*.review.json")):
            if p.is_file():
                review_hashes[str(p.relative_to(run_dir))] = sha256_file(p)
    entry = {
        "status": "closed",
        "receipt_status": status,
        "closed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "artifact_counts": counts,
        "artifact_hashes": hashes,
        "review_hashes": review_hashes,
        "receipt": {
            "author_agent": receipt.get("author_agent"),
            "reviewer_agent": receipt.get("reviewer_agent"),
            "author_session": receipt.get("author_session"),
            "started_at": receipt.get("started_at"),
            "finished_at": receipt.get("finished_at"),
            "cost": receipt.get("cost"),
            "scores_summary": review_scores_summary(run_dir, stage),
            "review_files": sorted(review_hashes),
        },
    }
    # Item 31: record the automation hand-off's hash at install close so
    # publish-verify can verify it is carried forward unchanged.
    if stage == "ghl-install-test":
        hp = run_dir / "handoff" / "automation-handoff.json"
        if hp.is_file():
            entry["handoff_sha256"] = sha256_file(hp)
    state["stages"][stage] = entry
    state["receipts"][stage] = f"private/receipts/{stage}.json"
    save_state(run_dir, state)
    # Item 25 (S6 emission spec 6.3): emit stage_closed from the values
    # just recorded.
    dur = None
    started, finished = receipt.get("started_at"), receipt.get("finished_at")
    if started and finished:
        try:
            dur = max(0, int((datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
                              - datetime.fromisoformat(str(started).replace("Z", "+00:00"))
                              ).total_seconds()))
        except Exception:
            dur = None
    cost_event = None
    cost = receipt.get("cost")
    if isinstance(cost, dict) and cost.get("provider") is not None:
        before, after = cost.get("credits_before"), cost.get("credits_after")
        if (isinstance(before, (int, float)) and isinstance(after, (int, float))
                and not isinstance(before, bool) and not isinstance(after, bool)):
            cost_event = {"provider": str(cost["provider"]),
                          "credits_used": before - after}
    emit_event(run_dir, {"event_type": "stage_closed", "stage": stage,
                         "receipt_status": status,
                         "closed_at": entry["closed_at"],
                         "duration_s": dur,
                         "scores_summary": entry["receipt"].get("scores_summary"),
                         "cost": cost_event,
                         "artifact_hashes": hashes,
                         "review_files": sorted(review_hashes)})


def stage_line(run_dir, stage, state):
    spec = STAGES[stage]
    st = state.get("stages", {}).get(stage, {})
    if st.get("status") == "not_applicable":
        return "NOT APPLICABLE"
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


# Update Plan Item 19: stages that place supplied assets into the page;
# an UNDERSIZED verdict recorded at intake prints in each one's evidence.
SUPPLIED_PLACING_STAGES = ("visual-mockup", "image-inventory-prompts",
                           "image-generation-qc", "image-map-upload",
                           "final-mockups", "responsive-html")


def supplied_size_flag_lines(run_dir):
    """Item 19: the named UNDERSIZED lines from intake.json's
    supplied_asset_size_checks records (written by write_intake.py).
    OK records are on file in the intake record; only the flags print."""
    lines = []
    try:
        data = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
    except Exception:
        return lines
    if not isinstance(data, dict):
        return lines
    for record in data.get("supplied_asset_size_checks") or []:
        if not isinstance(record, dict) or record.get("verdict") != "UNDERSIZED":
            continue
        asset, slot = record.get("asset_px") or {}, record.get("slot_px") or {}
        short = record.get("shortfall_px") or {}
        lines.append(
            f"SUPPLIED ASSET SIZE {record.get('id')} ({record.get('source')}): "
            f"asset {asset.get('width')}x{asset.get('height')} px, "
            f"slot {slot.get('width')}x{slot.get('height')} px: UNDERSIZED "
            f"(shortfall {short.get('width')}x{short.get('height')} px; flagged "
            "at intake under Item 19, never substituted, upscaled, or "
            "regenerated)")
    return lines


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
    # Items 13/14: recorded intake waivers are always visible in the report.
    if intake.exists():
        try:
            _idata = json.loads(intake.read_text(encoding="utf-8"))
        except Exception:
            _idata = {}
        if isinstance(_idata, dict):
            for w in _idata.get("layout_waivers") or []:
                if isinstance(w, dict):
                    warns.append(f"layout waiver recorded ({w.get('gate')}): {w.get('reason')}")
            if _idata.get("layout_references_waived") is True:
                warns.append("layout waiver recorded (layout-references, flat form): "
                             f"{_idata.get('layout_references_waiver_reason')}")
            # S71-02: an imported launch profile is always visible in the
            # report, with the launch it binds the run to.
            _launch = _idata.get("launch")
            if _idata.get("launch_profile"):
                _lid = _launch.get("launch_id") if isinstance(_launch, dict) else None
                _rev = _launch.get("revision") if isinstance(_launch, dict) else None
                warns.append(f"launch profile active: {_idata['launch_profile']} "
                             f"(launch {_lid}, revision {_rev}); the run's "
                             f"launch context is recorded in intake.json")
    # Items 13/17: REPORT.md prints, per layout reference, the source
    # this run used (original file, house default by name, or
    # waiver), so a fallback is visible, never silent, and a
    # substituted set is never implied to be the original set.
    for _s in layout_reference_sources(run_dir):
        warns.append(f"layout reference source ({_s['named_file']}): "
                     f"{_s['detail']}")
    # Item 19: an undersized supplied asset is always visible in the
    # report, named, with both sizes and the shortfall.
    warns.extend(supplied_size_flag_lines(run_dir))
    # Item 13 (Ruling 5): recorded reference substitutions and any
    # outstanding reference are always visible in the report, so a
    # report never implies the substituted set is the original set.
    _subs, _outst = _layout_substitution_record()
    for _name in _outst:
        warns.append(f"layout reference outstanding ({_name}): the "
                     "registry marks it outstanding (Item 13)")
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
    # Item 31: a not_applicable stage is cited in the report with the intake
    # values it was decided from, never silently absent.
    aw_state = state.get("stages", {}).get("automation-wiring", {})
    if aw_state.get("status") == "not_applicable":
        warns.append(f"automation-wiring NOT APPLICABLE: {aw_state.get('reason', '')}")
    # Item 6 downgrade rule: any publish-verify waiver prints in REPORT.md.
    pv_receipt = receipt_at(run_dir, "publish-verify")
    for w in pv_receipt.get("publish_waivers") or []:
        if isinstance(w, dict):
            warns.append(f"publish-verify waiver accepted ({w.get('rule')}): "
                         f"{w.get('reason')} (approved by {w.get('approved_by')}); "
                         f"the close proceeded under Item 6's downgrade rule")
    # Item 31: Tier 4 backstop use and conversational owner overrides are
    # always visible in the report, never silent.
    aw_receipt = receipt_at(run_dir, "automation-wiring")
    for w in aw_receipt.get("workflows") or []:
        if isinstance(w, dict) and w.get("build_method") == "tier4-browser-backstop":
            warns.append(f"automation workflow {w.get('name')!r} was built via the "
                         f"Tier 4 browser backstop (Skill 44), not the Tier 0 caf CLI")
    for o in aw_receipt.get("conversational_overrides") or []:
        if isinstance(o, dict):
            warns.append(f"conversational coverage owner override: trigger "
                         f"{o.get('trigger')} on {o.get('source_id')}: {o.get('reason')} "
                         f"(approved by {o.get('approved_by')})")
    # R71H seam P2: a filed dispatch refusal or failure is always
    # visible in the report with its recorded reason, never silent.
    _refusal = aw_receipt.get("dispatch_refusal")
    if isinstance(_refusal, dict) and str(_refusal.get("reason") or "").strip():
        warns.append(f"automation dispatch refused: {_refusal['reason']} "
                     f"(automation-wiring stays open)")
    _dfailure = aw_receipt.get("dispatch_failure")
    if isinstance(_dfailure, dict) and str(_dfailure.get("reason") or "").strip():
        warns.append(f"automation dispatch failed: {_dfailure['reason']} "
                     f"(automation-wiring stays open)")
    return warns


def compute_review_mode(run_dir):
    """Item 7: derive the run's review mode from its v2 review files.

    INDEPENDENT only when every review names a real reviewer session that
    never overlaps an author session and every review records
    independent_review true. SELF-REVIEWED when sessions overlap or any
    review is not independent (stages named). UNKNOWN when the run carries
    no v2 review data, or when every reviewer session is recorded as
    UNKNOWN (Amendment 6, Item 2 delta: an environment that cannot name
    its reviewing session reports the limitation; those reviews are never
    independent). Derived from evidence only; no agent input.
    """
    reviews_root = run_dir / "private" / "reviews"
    records = []
    if reviews_root.is_dir():
        for p in sorted(reviews_root.glob("*/*.review.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            reviewer = data.get("reviewer_session")
            author = data.get("author_session")
            reviewer = reviewer.strip() if isinstance(reviewer, str) else ""
            author = author.strip() if isinstance(author, str) else ""
            flag = data.get("independent_review")
            flag = flag if isinstance(flag, bool) else None
            if reviewer or author:
                records.append((p.parent.name, reviewer, author, flag))
    if not records or not any(r for _, r, _, _ in records):
        return "Review mode: UNKNOWN (no v2 review data)"
    named = [(s, r, a, f) for s, r, a, f in records
             if r and not _is_unknown_session(r)]
    if not named:
        return ("Review mode: UNKNOWN (reviewer sessions recorded as UNKNOWN; "
                "the limitation is on record and independence is not claimed)")
    reviewer_sessions = {r for _, r, _, _ in named}
    author_sessions = {a for _, _, a, _ in records if a}
    overlap_stages = sorted({stage for stage, r, a, _ in records
                             if r and not _is_unknown_session(r)
                             and (r == a or r in author_sessions)})
    unverified_stages = sorted(
        {stage for stage, r, _, f in records
         if not r or _is_unknown_session(r) or f is False}
        - set(overlap_stages))
    if overlap_stages or unverified_stages:
        reasons = []
        if overlap_stages:
            reasons.append(f"reviewer sessions overlap author sessions on "
                           f"stages: {', '.join(overlap_stages)}")
        if unverified_stages:
            reasons.append(f"reviews not independent on stages: "
                           f"{', '.join(unverified_stages)}")
        return "Review mode: SELF-REVIEWED (" + "; ".join(reasons) + ")"
    return (f"Review mode: INDEPENDENT ({len(reviewer_sessions)} reviewer sessions, "
            f"{len(author_sessions)} author sessions, no overlap)")


# Fix 12.4 (task 4.3): the four-image rule, enforced at report time.
# The per-stage artifacts prove presence per glob; this proves the SET
# exists for every page role the run declares. A run missing any of the
# four can never report complete.
FOUR_IMAGE_GLOBS = (
    "desktop-wireframe/section-*.png",
    "mobile-tablet/section-*.png",
    "final-mockups/desktop/part-*.png",
    "final-mockups/mobile/part-*.png",
)

def declared_page_roles(run_dir):
    """The page roles this run declares (references/page-request.schema.json
    enum). A launch-context run records intake.json's launch.page_role and
    places the same request at run_dir/page-request.json; a classic run with
    neither builds the signature landing page, the skill's one page role."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import page_role  # the one reader: a page type's own copy_version names its role too
    finally:
        sys.path.pop(0)
    return [page_role.declared_role(run_dir)]

def four_image_gaps(run_dir):
    """(page_role, glob) pairs whose glob resolves to no file in the run."""
    return [(role, pattern)
            for role in declared_page_roles(run_dir)
            for pattern in FOUR_IMAGE_GLOBS
            if not any(run_dir.glob(pattern))]

def cmd_report(run_dir):
    state, _ = load_state(run_dir)
    now = datetime.now(timezone.utc)
    lines = []
    lines.append(f"# Skill 71 Run Report")
    lines.append("")
    lines.append("Structured twin: REPORT.json (schema skill71/report-json/1.0)")
    lines.append("")
    lines.append(f"Generated by scripts/stage_gate.py report at {now.isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## Stages")
    lines.append("")
    lines.append("| Stage | Status | Closed at | Duration |")
    lines.append("|---|---|---|---|")
    durations = {}
    stage_rows = []
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
        # REPORT.json twin (Item 25): the same row as data, with the
        # close record behind it.
        _cost = receipt.get("cost") if isinstance(receipt, dict) else None
        _cost_json = None
        if isinstance(_cost, dict) and _cost.get("provider") is not None:
            _b, _a = _cost.get("credits_before"), _cost.get("credits_after")
            if (isinstance(_b, (int, float)) and isinstance(_a, (int, float))
                    and not isinstance(_b, bool) and not isinstance(_a, bool)):
                _cost_json = {"provider": str(_cost["provider"]),
                              "credits_used": _b - _a}
        stage_rows.append({
            "stage": stage,
            "status": line,
            "closed_at": st.get("closed_at"),
            "duration_s": durations.get(stage),
            "receipt_status": st.get("receipt_status"),
            "scores_summary": (st.get("receipt") or {}).get("scores_summary"),
            "cost": _cost_json,
            "artifact_hashes": st.get("artifact_hashes") or {},
            "review_files": (st.get("receipt") or {}).get("review_files") or [],
        })
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
    lines.append("## Browser hygiene")
    lines.append("")
    hygiene = report_hygiene_object(run_dir)
    if hygiene["status"] == "recorded":
        lines.append(f"Browser hygiene: {hygiene['opened']} sessions opened, "
                     f"{hygiene['closed']} closed, {hygiene['reaped']} "
                     f"orphans reaped.")
    else:
        lines.append("Browser hygiene: not recorded.")
    lines.append("")

    # SPF030: the page role and, for the landing role, its page kind.
    kind = intake_data(run_dir).get("page_kind")
    if kind:
        lines.append(f"Page: role {', '.join(declared_page_roles(run_dir))}, kind {kind}")
        lines.append("")

    # Fix 12.4: the four-image rule forces incomplete; it never refuses the
    # report, because the report is where the absence must be visible.
    image_gaps = four_image_gaps(run_dir)
    if image_gaps:
        required_closed = False
    overall = "RUN COMPLETE" if required_closed else "RUN INCOMPLETE"
    # Item 6, rule 1: a test run's report never reads as a production
    # delivery, even when every stage closed (a test run cannot close
    # publish-verify as a production pass at all; see check_publish_rules).
    if required_closed and test_run_flag(run_dir):
        overall = "TEST RUN, NOT A PRODUCTION DELIVERY"
    # Item 34: report generation refuses for a completed run while the
    # deliverables checker fails; the Deliverables line is earned only by
    # a clean, complete, manifest-verified folder.
    if required_closed:
        ok, summary, d_failures = run_deliverables_check(run_dir)
        if not ok:
            print("FAIL: report refused: the deliverables folder does not verify "
                  "(fix plan Item 34)")
            for line in d_failures:
                print(f"- {line}")
            return 1
        lines.append(f"Deliverables: complete ({summary.get('files')} files, "
                     f"manifest verified)")
        lines.append("")
    if not required_closed:
        missing = [s for s in ORDER
                   if stage_line(run_dir, s, state) in ("FAIL", "BLOCKED", NOT_RUN)]
        reasons = []
        if missing:
            reasons.append(f"not closed: {', '.join(missing)}")
        if image_gaps:
            reasons.append("four-image rule not satisfied: "
                           + ", ".join(f"{role} missing {pattern}"
                                       for role, pattern in image_gaps))
        lines.append(f"**{overall}** — " + "; ".join(reasons))
    else:
        lines.append(f"**{overall}**")
    rm_line = compute_review_mode(run_dir)
    lines.append(rm_line)
    report_path = run_dir / "REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Item 25 (S6 emission spec 6.5): write the structured twin in the
    # same pass, from the same values, then emit report_generated. The
    # hygiene object comes from report_hygiene_object() (Item 33's
    # roll-up, the function S7 named as this writer's source).
    report_json_path = run_dir / "REPORT.json"
    rm_data = _review_mode_data(run_dir, rm_line)
    if test_run_flag(run_dir):
        overall_json = "test-run"
    elif required_closed:
        overall_json = "complete"
    else:
        overall_json = "incomplete"
    merged_artifacts = {}
    for row in stage_rows:
        merged_artifacts.update(row["artifact_hashes"])
    idata = intake_data(run_dir)
    twin = {
        "schema_version": "1.0",
        "run_id": state.get("run_id"),
        "host_shape": state.get("host_shape") or host_shape(),
        "generated_at": now.isoformat(timespec="seconds"),
        "overall": overall_json,
        "review_mode": rm_data,
        "stages": stage_rows,
        "warnings": warns,
        "owner_blocked": [],
        "waivers": [w for w in warns
                    if w.startswith("layout waiver recorded")
                    or w.startswith("publish-verify waiver accepted")],
        "hygiene": hygiene,
        "totals": {
            "cost_by_provider": costs,
            "slowest_stages": [{"stage": s, "duration_s": secs}
                               for s, secs in sorted(
                                   durations.items(), key=lambda kv: -kv[1])[:3]],
        },
        "artifacts": merged_artifacts,
        "compare_sheets": ([str(p) for p in sorted(compare_dir.glob("*.png"))]
                           if compare_dir.exists() else []),
    }
    # Identity fields are plain strings in the schema: include each
    # only when the run actually carries a value.
    for _key in ("page_name", "brand_id", "client"):
        _val = state.get(_key, idata.get(_key))
        if _val is not None:
            twin[_key] = _val
    report_json_path.write_text(json.dumps(twin, indent=2) + "\n", encoding="utf-8")
    emit_event(run_dir, {"event_type": "report_generated",
                         "overall": overall_json,
                         "review_mode": rm_data["mode"],
                         "report_json_path": str(report_json_path),
                         "report_md_path": str(report_path)})
    # S71-05 (Signature Launch): a run that carries a page-request.json
    # (doc 02 section 6) also emits its page-result.json and
    # page-handoff.json in this same pass. Legacy runs without a
    # page-request are untouched. A launch run whose result cannot be
    # built validly fails the report: an invalid handoff must never
    # ride a passing report.
    if (run_dir / "page-request.json").exists():
        pr_mod = _page_result_module()
        if pr_mod is None:
            print("FAIL: page-result emission (S71-05): "
                  "scripts/page_result.py is missing from the skill; "
                  "a launch run cannot report without it")
            return 1
        pr_ok, pr_lines = pr_mod.emit_for_report(run_dir)
        for line in pr_lines:
            print(line)
        if not pr_ok:
            return 1
    print(f"wrote {report_path}")
    print(f"OVERALL: {overall}")
    return 0 if required_closed else 1


def _review_mode_data(run_dir, line):
    """Item 25: Item 7's review-mode stamp as data, beside its line.

    Counts are recomputed from the run's v2 review files with the same
    overlap rule compute_review_mode applies (a named reviewer session
    that equals its author session or any author session overlaps).
    """
    mode = "UNKNOWN"
    if line.startswith("Review mode: "):
        mode = line[len("Review mode: "):].split(" (")[0].strip() or "UNKNOWN"
    reviewers, authors, overlap = set(), set(), set()
    reviews_root = run_dir / "private" / "reviews"
    records = []
    if reviews_root.is_dir():
        for p in sorted(reviews_root.glob("*/*.review.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            r = data.get("reviewer_session")
            a = data.get("author_session")
            r = r.strip() if isinstance(r, str) else ""
            a = a.strip() if isinstance(a, str) else ""
            records.append((p.parent.name, r, a))
            if r:
                reviewers.add(r)
            if a:
                authors.add(a)
    for stage, r, a in records:
        if r and not _is_unknown_session(r) and (r == a or r in authors):
            overlap.add(stage)
    return {"mode": mode, "reviewer_sessions": len(reviewers),
            "author_sessions": len(authors),
            "overlap_stages": sorted(overlap), "line": line}


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
    p_check_item = sub.add_parser("check-item", help="gate for starting one item of an itemized stage")
    p_check_item.add_argument("run_dir", type=Path)
    p_check_item.add_argument("stage")
    p_check_item.add_argument("item_id")
    p_close_item = sub.add_parser("close-item", help="gate for closing one item of an itemized stage")
    p_close_item.add_argument("run_dir", type=Path)
    p_close_item.add_argument("stage")
    p_close_item.add_argument("item_id")
    p_block_item = sub.add_parser("block-item", help="record an item of an itemized stage as blocked, with a named reason")
    p_block_item.add_argument("run_dir", type=Path)
    p_block_item.add_argument("stage")
    p_block_item.add_argument("item_id")
    p_block_item.add_argument("--reason", required=True)
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
    if args.cmd == "check-item":
        return cmd_check_item(args.run_dir, args.stage, args.item_id)
    if args.cmd == "close-item":
        return cmd_close_item(args.run_dir, args.stage, args.item_id)
    if args.cmd == "block-item":
        return cmd_block_item(args.run_dir, args.stage, args.item_id, args.reason)
    return 2


if __name__ == "__main__":
    sys.exit(main())
