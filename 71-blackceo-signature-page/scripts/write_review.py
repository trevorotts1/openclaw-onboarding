#!/usr/bin/env python3
"""Write a Review Receipt v2 file (Skill 71 fix plan, Item 2).

This is the ONLY sanctioned way to create a review file. Usage:

  python3 scripts/write_review.py <run_dir> <stage> <item-id> \
      --scores '<json>' --verdict pass|fail \
      --performed-check '<what the reviewer actually did>' \
      --next-current-artifact '<artifact this review advances or blocks>' \
      [--artifact <rel-path>] [--author-session <session-id>] \
      [--repair-attempt <0-3>] [--automatic-failures '<json list>'] \
      [--specific-defects '<json list>'] \
      [--standard-file <path-under-assets/visual-standards>]

A review that scores a trait criterion (`wireframe_trait_completeness` or
`mockup_trait_fidelity`) must name the visual standard file it compared the
artifact against, and that file must exist under
`assets/visual-standards/` in this skill. `assets/visual-standards/README.md`
already requires the reviewer to name the standard file compared; this
writer now enforces it instead of trusting the note text. A review with no
trait criterion may cite a standard file or omit it.

--scores is a JSON object mapping criterion name to {"score": number,
"note": string}. Every note must be at least 40 characters of real evidence
text; a note that is only the artifact's filename is rejected.

The SOP's evidentiary fields (fix plan Amendment 6, Item 2 delta) are part
of every review record: automatic_failures (list, empty allowed, absence
not allowed), repair_attempt (integer 0 to 3, the focused repair attempt
this review follows), specific_defects (list of named defects, required
non-empty on a fail verdict), performed_check (what the reviewer actually
did, in the reviewer's own words, distinct from the criterion notes), and
next_current_artifact (the artifact this review advances or blocks).

The reviewer session id is read from the environment, in order:
OPENCLAW_SESSION_ID, CLAUDE_CODE_SESSION_ID, CLAUDE_SESSION_ID. If none is
set, the review is STILL written, with reviewer_session "UNKNOWN" and
independent_review: false, and a warning printed to stderr: the SOP rule
for an environment that cannot name its reviewing session is to report
the limitation, never to simulate independence. The gate stamps such runs
SELF-REVIEWED or UNKNOWN; they can never claim INDEPENDENT status.

The artifact's SHA-256 is computed here from the file on disk, never taken
from the caller. author_session is taken from --author-session when given,
else from the stage receipt (author_session, falling back to author_agent),
else the literal "unknown-author" (the gate will flag a missing author
session at close; this script does not invent one). independent_review is
computed here from the two sessions: true only when the reviewer session
is a real, named session different from the author session.

The file is written atomically to
<run_dir>/private/reviews/<stage>/<item-id>.review.json with the v2
fields: item, artifact, artifact_sha256, author_session, reviewer_session,
reviewed_at, criteria, verdict, automatic_failures, repair_attempt,
specific_defects, performed_check, next_current_artifact,
independent_review.

Model independence (graphics hooks, SOP-GIP-02): a review of generated
images or of the prompt that made them must come from a DIFFERENT MODEL than
the one that authored the prompt. Pass --author-model and --reviewer-model (or
set SKILL71_REVIEWER_MODEL) and/or --require-model-independence. When the rule
is active, independent_review is true only when BOTH models are named and they
differ; an unnamed model counts as NOT independent (the limitation is recorded,
never simulated). The review then also carries author_model, reviewer_model and
model_independence (independent | same_model | unknown). With none of the
three given the record is byte-for-byte what it was before.

A pass verdict may not cite an automatic failure listed in the stage contract's
graphics_autofails block (AF-G1..AF-G8): a pass with a graphics automatic
failure is refused, the same as SOP-GIP-02's "any hit = FAIL".

Exit codes: 0 written (including UNKNOWN-session writes), 1 invalid
review content, 2 usage / unreadable input.
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SESSION_ENV_VARS = ("OPENCLAW_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")
MIN_NOTE_CHARS = 40
UNKNOWN_SESSION = "UNKNOWN"
STANDARD_SET_DIR = "assets/visual-standards"
TRAIT_CRITERIA = ("wireframe_trait_completeness", "mockup_trait_fidelity")
FILE_SUFFIXES = ("json", "md", "html", "png", "txt", "pdf", "jpg", "jpeg")
REVIEWER_MODEL_ENV = "SKILL71_REVIEWER_MODEL"
UNKNOWN_MODEL = "UNKNOWN"


def _model_key(model):
    return " ".join(str(model or "").strip().lower().split())


def model_independence(author_model, reviewer_model):
    """'independent' only when both models are named and differ; an unnamed
    model is 'unknown' and counts as not independent."""
    a, r = _model_key(author_model), _model_key(reviewer_model)
    if not a or not r:
        return "unknown"
    return "same_model" if a == r else "independent"


def graphics_autofail_codes(contract):
    """AF-G codes the stage contract lists (data, not prose)."""
    rows = contract.get("graphics_autofails") or []
    return sorted(str(r.get("code")) for r in rows if isinstance(r, dict) and r.get("code"))


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def reviewer_session_from_env():
    for name in SESSION_ENV_VARS:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def load_contract():
    contract_path = Path(os.environ.get(
        "STAGE_GATE_CONTRACT",
        str(SKILL_ROOT / "references" / "stage-contract.json")))
    try:
        return json.loads(contract_path.read_text(encoding="utf-8"))
    except Exception:
        return {"stages": {}}


def item_stem(path):
    name = path.name
    for suffix in (".review.json",):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return Path(name).stem


def resolve_artifact(run_dir, stage, item_id, contract):
    """Find the artifact file a review item refers to.

    Resolution order: an explicit stage artifact / per-file / review-covers
    glob match whose stem equals item_id; a literal covered path; the
    stage's page-visual-bible style special case (stem match across all
    stage artifact globs); for item_id == "stage", the first file matched
    by the stage's first artifact glob.
    """
    spec = (contract.get("stages") or {}).get(stage) or {}
    patterns = []
    for art in spec.get("artifacts", []):
        patterns.append(art["glob"])
    if spec.get("per_file_glob"):
        patterns.append(spec["per_file_glob"])
    covers = spec.get("review_covers")
    if isinstance(covers, str):
        covers = [covers]
    literal_items = []
    for entry in covers or []:
        if any(ch in entry for ch in "*?["):
            patterns.append(entry)
        else:
            literal_items.append(entry)
    if item_id == "stage":
        for pattern in patterns:
            matches = sorted(p for p in run_dir.glob(pattern) if p.is_file())
            if matches:
                return matches[0]
        return None
    for pattern in patterns:
        for p in sorted(run_dir.glob(pattern)):
            if p.is_file() and item_stem(p) == item_id:
                return p
    for entry in literal_items:
        candidate = run_dir / entry
        if candidate.is_file():
            if item_stem(candidate) == item_id or entry == item_id:
                return candidate
        if entry == item_id:
            # A named covered item (e.g. page-visual-bible): resolve by stem
            # against every artifact the stage declares.
            for pattern in patterns:
                for p in sorted(run_dir.glob(pattern)):
                    if p.is_file() and item_stem(p) == item_id:
                        return p
    # Suffix-disambiguated ids (page-visual-bible-json, page-visual-bible-md)
    # come from covered files that share a folder and a stem but differ by
    # file suffix: match stem plus the suffix named by the id's tail.
    if "-" in item_id:
        stem_wanted, _, ext_wanted = item_id.rpartition("-")
        if ext_wanted.lower() in FILE_SUFFIXES:
            for pattern in patterns:
                for p in sorted(run_dir.glob(pattern)):
                    if (p.is_file() and item_stem(p) == stem_wanted
                            and p.suffix.lstrip(".").lower() == ext_wanted.lower()):
                        return p
    # Disambiguated ids (desktop-part-01, mobile-part-01) come from covered
    # folders whose file stems collide: match stem plus parent folder name.
    if "-" in item_id:
        parent_wanted, _, stem_wanted = item_id.partition("-")
        for pattern in patterns:
            for p in sorted(run_dir.glob(pattern)):
                if (p.is_file() and item_stem(p) == stem_wanted
                        and p.parent.name == parent_wanted):
                    return p
    # Last resort: any file in the run tree with this stem.
    for p in sorted(run_dir.rglob("*")):
        if p.is_file() and item_stem(p) == item_id and "private" not in p.parts:
            return p
    return None


def receipt_author_session(run_dir, stage):
    rp = run_dir / "private" / "receipts" / f"{stage}.json"
    if rp.exists():
        try:
            receipt = json.loads(rp.read_text(encoding="utf-8"))
        except Exception:
            return None
        for key in ("author_session", "author_agent"):
            value = receipt.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def validate_scores(raw):
    """Return (criteria, error_lines)."""
    try:
        data = json.loads(raw)
    except Exception as exc:
        return None, [f"--scores is not valid JSON: {exc}"]
    if not isinstance(data, dict) or not data:
        return None, ["--scores must be a non-empty JSON object mapping "
                      "criterion name to {score, note}"]
    errors = []
    for name, entry in sorted(data.items()):
        if not isinstance(entry, dict):
            errors.append(f"criterion {name!r}: value must be an object "
                          f"{{score, note}} (Review Receipt v2 carries an "
                          f"evidence note per criterion)")
            continue
        score = entry.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            errors.append(f"criterion {name!r}: score must be a number")
        note = entry.get("note")
        if not isinstance(note, str) or not note.strip():
            errors.append(f"criterion {name!r}: note is missing; every scored "
                          f"criterion needs an evidence note of at least "
                          f"{MIN_NOTE_CHARS} characters")
        elif len(note.strip()) < MIN_NOTE_CHARS:
            errors.append(f"criterion {name!r}: note is {len(note.strip())} "
                          f"characters; at least {MIN_NOTE_CHARS} required "
                          f"(name the evidence, not a verdict word)")
    return (data if not errors else None), errors


def parse_string_list(raw, flag):
    """Parse a JSON list-of-strings CLI value; return (list, error)."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"{flag}: invalid JSON ({e})"
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        return None, f"{flag}: must be a JSON list of strings"
    return [x.strip() for x in value if x.strip()], None


def main():
    parser = argparse.ArgumentParser(description="Write a Skill 71 Review Receipt v2 file.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("stage")
    parser.add_argument("item_id")
    parser.add_argument("--scores", required=True,
                        help="JSON object: criterion -> {score, note}")
    parser.add_argument("--verdict", required=True, choices=("pass", "fail"))
    parser.add_argument("--artifact", default=None,
                        help="artifact path relative to run_dir (default: resolved "
                             "from the stage contract and item id)")
    parser.add_argument("--author-session", default=None,
                        help="session that authored the artifact (default: read "
                             "from the stage receipt)")
    parser.add_argument("--performed-check", required=True,
                        help="what the reviewer actually did, in the reviewer's "
                             "own words (SOP evidentiary field)")
    parser.add_argument("--next-current-artifact", required=True,
                        help="the artifact this review advances or blocks "
                             "(SOP evidentiary field)")
    parser.add_argument("--repair-attempt", type=int, default=0,
                        help="focused repair attempt this review follows, 0 to 3 "
                             "(SOP evidentiary field)")
    parser.add_argument("--automatic-failures", default="[]",
                        help="JSON list of automatic failures found, if any "
                             "(SOP evidentiary field; empty list allowed)")
    parser.add_argument("--specific-defects", default="[]",
                        help="JSON list of named defects; required non-empty "
                             "when the verdict is fail (SOP evidentiary field)")
    parser.add_argument("--author-model", default=None,
                        help="model that authored the prompt/artifact under review "
                             "(model-independence rule; unnamed counts as not independent)")
    parser.add_argument("--reviewer-model", default=None,
                        help="model doing this review (default: $" + REVIEWER_MODEL_ENV + ")")
    parser.add_argument("--require-model-independence", action="store_true",
                        help="apply the model-independence rule even when no model is named "
                             "(then both models are unknown, so the review is not independent)")
    parser.add_argument("--standard-file", default=None,
                        help="the visual standard file this review compared the "
                             "artifact against, relative to the skill root. "
                             "Required when a trait criterion is scored; must "
                             "exist under " + STANDARD_SET_DIR + "/")
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    if not run_dir.exists():
        print(f"ERROR: run_dir does not exist: {run_dir}")
        return 2
    if "/" in args.item_id or "\\" in args.item_id or args.item_id in (".", ".."):
        print(f"ERROR: invalid item id {args.item_id!r}")
        return 2

    # SOP rule (Amendment 6, Item 2 delta): when the environment cannot
    # name its reviewing session, the limitation is recorded, not
    # simulated. The review is written with reviewer_session UNKNOWN and
    # independent_review false, and the run can never claim INDEPENDENT.
    reviewer_session = reviewer_session_from_env()
    session_unknown = reviewer_session is None
    if session_unknown:
        reviewer_session = UNKNOWN_SESSION
        print("WARNING: no reviewer session id in the environment (looked "
              "for " + ", ".join(SESSION_ENV_VARS) + "); writing the review "
              "with reviewer_session UNKNOWN and independent_review false. "
              "The limitation is recorded, not simulated.", file=sys.stderr)

    criteria, errors = validate_scores(args.scores)
    if errors:
        print("FAIL")
        for line in errors:
            print(f"- {line}")
        return 1

    automatic_failures, err = parse_string_list(args.automatic_failures,
                                                "--automatic-failures")
    if err:
        print("FAIL")
        print(f"- {err}")
        return 1
    specific_defects, err = parse_string_list(args.specific_defects,
                                              "--specific-defects")
    if err:
        print("FAIL")
        print(f"- {err}")
        return 1
    content_errors = []
    if not 0 <= args.repair_attempt <= 3:
        content_errors.append(
            f"--repair-attempt must be an integer from 0 to 3, "
            f"got {args.repair_attempt}")
    performed_check = (args.performed_check or "").strip()
    if len(performed_check) < 10:
        content_errors.append(
            "--performed-check must describe, in the reviewer's own words, "
            "the check actually performed (at least 10 characters)")
    next_current_artifact = (args.next_current_artifact or "").strip()
    if not next_current_artifact:
        content_errors.append(
            "--next-current-artifact must name the artifact this review "
            "advances or blocks")
    if args.verdict == "fail" and not specific_defects:
        content_errors.append(
            "a fail verdict requires --specific-defects naming the defects "
            "found (SOP evidentiary field)")
    # Fix 9 (task 3.6): a trait-scored review names the standard file it
    # was compared against, and the file must actually exist in the
    # bundled set. The note text is not trusted to carry the citation.
    standard_file = None
    trait_scored = [c for c in sorted(criteria) if c in TRAIT_CRITERIA]
    cited = (args.standard_file or "").strip()
    if trait_scored and not cited:
        content_errors.append(
            "a trait-scored review (" + ", ".join(trait_scored) + ") must "
            "name the standard file it was compared against with "
            "--standard-file <path under " + STANDARD_SET_DIR + "> "
            "(assets/visual-standards/README.md, 'How reviewers use this set')")
    elif cited:
        candidate = (SKILL_ROOT / cited)
        try:
            resolved = candidate.resolve()
            standard_root = (SKILL_ROOT / STANDARD_SET_DIR).resolve()
            resolved.relative_to(standard_root)
        except (ValueError, OSError):
            content_errors.append(
                "--standard-file " + repr(cited) + " is not a file under "
                + STANDARD_SET_DIR + "/; a review cites the bundled standard set")
        else:
            if not resolved.is_file():
                content_errors.append(
                    "--standard-file " + repr(cited) + " does not exist under "
                    + STANDARD_SET_DIR + "/")
            else:
                standard_file = str(resolved.relative_to(SKILL_ROOT.resolve()))
    if content_errors:
        print("FAIL")
        for line in content_errors:
            print(f"- {line}")
        return 1

    contract = load_contract()
    hit = [f for f in automatic_failures
           if any(f == code or f.startswith(code + ":") or f.startswith(code + " ")
                  for code in graphics_autofail_codes(contract))]
    if args.verdict == "pass" and hit:
        print("FAIL")
        print("- a pass verdict cannot cite a graphics automatic failure ("
              + ", ".join(hit) + "); any hit is a FAIL (SOP-GIP-02)")
        return 1
    if args.artifact:
        artifact_path = run_dir / args.artifact
        if not artifact_path.is_file():
            print(f"ERROR: --artifact {args.artifact!r} is not a file under {run_dir}")
            return 2
    else:
        artifact_path = resolve_artifact(run_dir, args.stage, args.item_id, contract)
        if artifact_path is None:
            print(f"ERROR: cannot resolve an artifact for stage {args.stage!r} "
                  f"item {args.item_id!r} from the stage contract; pass "
                  f"--artifact <path-relative-to-run-dir> explicitly")
            return 2
    artifact_rel = str(artifact_path.relative_to(run_dir))

    for name, entry in sorted(criteria.items()):
        note = entry["note"].strip()
        if note == artifact_path.name or note == artifact_rel:
            print("FAIL")
            print(f"- criterion {name!r}: note is only the artifact filename; "
                  f"write the evidence the score rests on")
            return 1

    author_session = (args.author_session or "").strip() \
        or receipt_author_session(run_dir, args.stage) \
        or "unknown-author"

    independent_review = (not session_unknown) and reviewer_session != author_session
    author_model = (args.author_model or "").strip() or None
    reviewer_model = ((args.reviewer_model or "").strip()
                      or os.environ.get(REVIEWER_MODEL_ENV, "").strip() or None)
    model_rule = bool(args.require_model_independence or author_model or reviewer_model)
    model_state = model_independence(author_model, reviewer_model)
    if model_rule and model_state != "independent":
        independent_review = False
        print("WARNING: model independence is " + model_state + "; writing the review with "
              "independent_review false (a reviewer model must differ from the prompt author's "
              "model, and an unnamed model counts as not independent).", file=sys.stderr)

    review = {
        "item": args.item_id,
        "artifact": artifact_rel,
        "artifact_sha256": sha256_file(artifact_path),
        "author_session": author_session,
        "reviewer_session": reviewer_session,
        "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "criteria": criteria,
        "verdict": args.verdict,
        "automatic_failures": automatic_failures,
        "repair_attempt": args.repair_attempt,
        "specific_defects": specific_defects,
        "performed_check": performed_check,
        "next_current_artifact": next_current_artifact,
        "independent_review": independent_review,
    }
    # The citation is recorded only when it was made, so the Review
    # Receipt v2 field set is unchanged for reviews with no trait
    # criterion (tests/test_review_v2.py pins that exact set).
    if standard_file:
        review["standard_file"] = standard_file
    if model_rule:
        review["author_model"] = author_model or UNKNOWN_MODEL
        review["reviewer_model"] = reviewer_model or UNKNOWN_MODEL
        review["model_independence"] = model_state

    out_dir = run_dir / "private" / "reviews" / args.stage
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.item_id}.review.json"
    fd, tmp_name = tempfile.mkstemp(dir=str(out_dir), prefix=".review-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(review, indent=2) + "\n")
        os.replace(tmp_name, out_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    print(f"WROTE: {out_path}")
    print(f"  artifact: {artifact_rel} sha256 {review['artifact_sha256'][:12]}...")
    print(f"  reviewer_session: {reviewer_session}  author_session: {author_session}")
    print(f"  independent_review: {str(independent_review).lower()}")
    if standard_file:
        print(f"  standard_file: {standard_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
