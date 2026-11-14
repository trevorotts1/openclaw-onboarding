#!/usr/bin/env python3
"""pd_step_gate.py - THE RUNNER'S STEP GATE for the Presentation Department.

It replaces every place where the running agent could "check" a step by
pattern-matching text (grep) or "report" a step by printing a success line
(echo). It validates REAL ARTIFACTS on disk against PIPELINE-MANIFEST.json and
refuses to proceed when a prior step was not verifiably done. The agent never
decides a step is done; this script does.

Commands
  before  PHASE   refuse unless (a) every earlier ACTIVE phase has a valid gate
                  receipt whose recorded sha256 still matches the file on disk, and
                  (b) every artifact PHASE consumes exists and passes its type check
  after   PHASE   validate everything PHASE produces, then write the gate receipt
                  <run-dir>/working/checkpoints/step-gate/<PHASE>.json
  complete        refuse unless every ACTIVE phase has a valid receipt, every file in
                  the manifest's build_bundle_files meets its min_bytes floor, and the
                  engine's own state.json says the run is closed
  explain PHASE   print, in plain words, what PHASE must produce (no validation)

Type checks (by extension, on the real bytes - never on a file name alone)
  .json  parses; is an object or list; is not empty
  .md/.txt/.html   non-empty; no line consisting only of TODO / TBD / PLACEHOLDER
  .png   PNG magic bytes; at least 20 KiB        .pdf   starts with %PDF-
  .pptx  ZIP magic; contains ppt/presentation.xml .mp3/.mp4 at least 50 KiB
  glob patterns (slide-*.txt) must match at least one file, and when slides.json
  exists, exactly one file per slide

Exit codes: 0 gate passed, 5 gate REFUSED (reasons printed), 2 cannot determine.
Usage: python3 -I pd_step_gate.py before P4-RENDER --run-dir DIR --manifest PATH [--json]

ENGINE VALUES THIS FILE MIRRORS (read from the files, never guessed):
  presentation_job/phases.py:330   PHASE_STATUS_DONE = "done". The full per-unit
      status enum is phases.py:328-346 (pending, running, done, deferred,
      quarantined, blocked, failed, obsolete). Only "done" means done; a
      "deferred" phase is a legitimate skip.
  presentation_job/phases.py:5651 and :5726   close() sets
      state["terminal"] = "DONE"; every park sets "BLOCKED" (phases.py:4190,
      5108, 5545, 5617, 5635, 5658, 5692, 5710).
  presentation_job/state.py:65   STATE_FILENAME = "state.json", stored at the
      RUN-DIR ROOT (<run_dir>/state.json), not under working/.
  presentation_job/phases.py:1571-1587, 1629-1645, 1737-1742   a routed-around
      phase is status="done", artifacts=[], routed_around=True: nothing was
      produced, so it can never have a gate receipt.
  presentation_job/defers.py:49-76, :128-164, :243-300   how a manifest
      ``defers_unless`` expression resolves an ``intake.<key>`` from the intake
      record (capture key, top-level key, recorded waiver, question default).
STDLIB ONLY. Read-only except the receipt it writes under working/checkpoints/step-gate/.
Every decision reads structured data (manifest, intake, state.json, artifact
bytes) - never text matched out of a log.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile

# presentation_job/phases.py:330 -- the only per-unit status that means done.
DONE_STATES = {"done"}
# presentation_job/phases.py:331,335 -- a legitimate skip: the phase produced
# nothing by design, so there is no artifact and no receipt to demand.
SKIP_STATUSES = {"deferred", "obsolete"}
# presentation_job/state.py:65 -- state.json sits at the RUN-DIR ROOT.
STATE_FILENAME = "state.json"
# presentation_job/phases.py:5651,5726 -- close() writes terminal "DONE";
# every park writes "BLOCKED". Compared literally, as the engine writes it.
CLOSED_TERMINALS = {"DONE"}
PLACEHOLDER_LINES = {"todo", "tbd", "placeholder", "lorem ipsum"}

# presentation_job/defers.py:49-76 -- the election questions, their
# pre_presentation_capture storeTarget key, waiver rule and declared default.
WANT_KEYS = {
    "want_sales_checkout": ("WANT_SALES_CHECKOUT", "sales_checkout", "yes"),
    "want_vsl_page": ("WANT_VSL_PAGE", "vsl_page", "no"),
    "want_motion_graphics": ("WANT_MOTION_GRAPHICS", "motion_graphics", "no"),
    "want_email_sequences": ("WANT_EMAIL_SEQUENCES", "email_sequences", "no"),
}
YES_VALUES = {"yes", "true", "1", "y", "on"}
NO_VALUES = {"no", "false", "0", "n", "off"}


class CannotDetermine(Exception):
    """Exit 2: the gate cannot decide, so it never claims a pass."""


def as_list(v):
    return [] if v is None else ([v] if isinstance(v, str) else [str(x) for x in v])


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_intake(run_dir):
    """The run's intake record (working/copy/intake.json).

    Absent is empty: the engine's own defers.load_intake (defers.py:274-286)
    returns {} and resolve_intake_value then applies the question defaults.
    Present but unreadable is CANNOT DETERMINE -- never treated as a pass.
    """
    path = os.path.join(run_dir, "working", "copy", "intake.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
    except (OSError, ValueError) as exc:
        raise CannotDetermine("working/copy/intake.json unreadable (%s)" % exc)
    if not isinstance(obj, dict):
        raise CannotDetermine("working/copy/intake.json is not a JSON object")
    return obj


def _canon_boolish(value):
    if value in YES_VALUES:
        return "yes"
    if value in NO_VALUES:
        return "no"
    return value


def resolve_intake_value(intake, key):
    """presentation_job/defers.py:128-164, mirrored: return "yes"/"no"/text or None."""
    cap = intake.get("pre_presentation_capture")
    if not isinstance(cap, dict):
        cap = {}
    spec = WANT_KEYS.get(key)
    if spec is not None:
        upper, waiver_rule, default = spec
        for cand in (upper, key, upper.lower()):
            if cand in cap and cap[cand] is not None:
                raw = str(cap[cand]).strip().lower()
                if raw:
                    return _canon_boolish(raw)
        if key in intake and intake[key] is not None:
            raw = str(intake[key]).strip().lower()
            if raw:
                return _canon_boolish(raw)
        waivers = intake.get("waivers")
        if isinstance(waivers, list) and any(
                isinstance(w, dict) and w.get("rule") == waiver_rule
                for w in waivers):
            return "no"
        return default
    if key in intake and intake[key] is not None:
        return str(intake[key]).strip().lower()
    for cand in (key, key.upper()):
        if cand in cap and cap[cand] is not None:
            return str(cap[cand]).strip().lower()
    return None


def is_active(phase, intake):
    """Does this phase apply to this run? Mirrors defers.evaluate_defers_unless.

    The manifest's only grammar is a disjunction of ``intake.<key> == "<value>"``
    clauses (PIPELINE-MANIFEST.json ``defers_unless``). An unresolvable clause
    is False (the engine fails closed too).
    """
    expr = phase.get("defers_unless")
    if not expr:
        return True
    for clause in re.split(r"\s+or\s+", expr):
        left, _, right = clause.partition("==")
        key = left.strip()
        if key.startswith("intake."):
            key = key[len("intake."):]
        want = right.strip().strip('"').strip("'").lower()
        got = resolve_intake_value(intake, key)
        if got is not None and got == want:
            return True
    return False


def engine_state(run_dir):
    path = os.path.join(run_dir, STATE_FILENAME)
    try:
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def phase_ran_nothing(run_dir, phase_id):
    """True only when the engine's own record proves this phase produced nothing.

    Structured fields only (state.json), and only a positive record counts:
    a missing state.json or a missing phase row still demands a receipt.
    """
    state = engine_state(run_dir)
    if state is None:
        return False
    for ps in state.get("phases") or []:
        if not isinstance(ps, dict) or ps.get("id") != phase_id:
            continue
        if ps.get("status") in SKIP_STATUSES:
            return True
        if ps.get("routed_around") is True:
            return True
        return ps.get("status") in DONE_STATES and not (ps.get("artifacts") or [])
    return False


def check_file(path):
    """Return a problem string, or None when the file is real."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return "missing: %s" % path
    if size == 0:
        return "empty file: %s" % path
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
        if ext == ".json":
            with open(path, encoding="utf-8") as fh:
                obj = json.load(fh)
            if not isinstance(obj, (dict, list)) or not obj:
                return "JSON is empty or not an object/list: %s" % path
        elif ext in (".md", ".txt", ".html"):
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.strip().lower() in PLACEHOLDER_LINES:
                        return "placeholder line %r in %s" % (line.strip(), path)
        elif ext == ".png":
            if head != b"\x89PNG\r\n\x1a\n":
                return "not a PNG: %s" % path
            if size < 20 * 1024:
                return "PNG under 20 KiB: %s" % path
        elif ext == ".pdf" and not head.startswith(b"%PDF-"):
            return "not a PDF: %s" % path
        elif ext == ".pptx":
            if not zipfile.is_zipfile(path):
                return "not a PPTX (zip): %s" % path
            with zipfile.ZipFile(path) as zf:
                if "ppt/presentation.xml" not in zf.namelist():
                    return "PPTX has no ppt/presentation.xml: %s" % path
        elif ext in (".mp3", ".mp4") and size < 50 * 1024:
            return "media file under 50 KiB: %s" % path
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        return "unreadable %s (%s)" % (path, exc)
    return None


def resolve(run_dir, pattern, slug):
    pat = pattern.replace("{deck_slug}", slug or "*")
    return sorted(glob.glob(os.path.join(run_dir, pat)))


def slide_count(run_dir):
    for rel in ("working/copy/slides.json", "slides.json"):
        try:
            with open(os.path.join(run_dir, rel), encoding="utf-8") as fh:
                obj = json.load(fh)
            if isinstance(obj, list) and obj:
                return len(obj)
        except (OSError, ValueError):
            continue
    return None


def check_artifacts(run_dir, patterns, slug):
    problems, files = [], []
    for pattern in patterns:
        hits = resolve(run_dir, pattern, slug)
        if not hits:
            problems.append("nothing on disk for %s" % pattern)
            continue
        if "slide-*" in pattern:
            n = slide_count(run_dir)
            if n is not None and len(hits) != n:
                problems.append("%s matched %d file(s) but the deck has %d slides"
                                % (pattern, len(hits), n))
        for h in hits:
            bad = check_file(h)
            if bad:
                problems.append(bad)
            else:
                files.append(h)
    return problems, files


def receipt_path(run_dir, phase_id):
    return os.path.join(run_dir, "working", "checkpoints", "step-gate", "%s.json" % phase_id)


def receipt_valid(run_dir, phase_id):
    path = receipt_path(run_dir, phase_id)
    try:
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return "no step-gate receipt for %s" % phase_id
    if not isinstance(rec, dict):
        return "%s has a malformed step-gate receipt" % phase_id
    for item in rec.get("artifacts", []):
        if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
            return "%s has a malformed step-gate receipt" % phase_id
        try:
            if sha256(item["path"]) != item["sha256"]:
                return "%s changed after its gate (%s)" % (phase_id, item["path"])
        except OSError:
            return "%s artifact vanished after its gate (%s)" % (phase_id, item["path"])
    return None


def bundle_hits(run_dir, filename, slug):
    """Every file under working/ matching a deliverables_required filename."""
    name = filename.replace("{deck_slug}", slug or "*")
    pattern = os.path.join(run_dir, "working", "**", name)
    return sorted(glob.glob(pattern, recursive=True))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["before", "after", "complete", "explain"])
    ap.add_argument("phase", nargs="?")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    run_dir = os.path.realpath(args.run_dir)

    try:
        with open(args.manifest, encoding="utf-8") as fh:
            manifest = json.load(fh)
        phases = sorted(manifest["phases"], key=lambda p: p.get("order", 0))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("CANNOT DETERMINE: manifest unreadable (%s)" % exc)
        return 2
    by_id = {p["id"]: p for p in phases}
    if args.command != "complete" and args.phase not in by_id:
        print("CANNOT DETERMINE: %r is not a manifest phase id" % args.phase)
        return 2

    if args.command == "explain":
        p = by_id[args.phase]
        print("%s produces: %s" % (p.get("name"), as_list(p.get("produces_artifact"))))
        print("it needs first: %s" % as_list(p.get("consumes")))
        return 0

    try:
        intake = load_intake(run_dir)
    except CannotDetermine as exc:
        print("CANNOT DETERMINE: %s -- refusing to guess whether an optional phase applies"
              % exc)
        return 2
    slug = intake.get("deck_slug")
    reasons = []

    if args.command in ("before", "complete"):
        limit = (by_id[args.phase].get("order", 0)
                 if args.command == "before" else float("inf"))
        for p in phases:
            if p.get("order", 0) >= limit:
                break
            if not is_active(p, intake):
                continue
            if phase_ran_nothing(run_dir, p["id"]):
                continue
            bad = receipt_valid(run_dir, p["id"])
            if bad:
                reasons.append(bad)
    if args.command == "before":
        probs, _ = check_artifacts(run_dir, as_list(by_id[args.phase].get("consumes")), slug)
        reasons += ["input for %s: %s" % (args.phase, x) for x in probs]
    if args.command == "after":
        probs, files = check_artifacts(run_dir, as_list(by_id[args.phase].get("produces_artifact")), slug)
        reasons += probs
        if not reasons:
            rec = {"phase": args.phase,
                   "artifacts": [{"path": f, "sha256": sha256(f), "bytes": os.path.getsize(f)}
                                 for f in files]}
            path = receipt_path(run_dir, args.phase)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(rec, fh, indent=2)
            os.replace(tmp, path)
    if args.command == "complete":
        floors = {d.get("key"): d for d in manifest.get("deliverables_required", [])}
        for key in manifest.get("build_bundle_files", []):
            spec = floors.get(key)
            if not spec:
                reasons.append("bundle key %s has no deliverables_required row" % key)
                continue
            hits = bundle_hits(run_dir, str(spec.get("filename") or ""), slug)
            if not hits:
                reasons.append("bundle file missing: %s" % spec.get("filename"))
            elif os.path.getsize(hits[0]) < int(spec.get("min_bytes", 1)):
                reasons.append("bundle file under its floor (%s < %s bytes): %s"
                               % (os.path.getsize(hits[0]), spec.get("min_bytes"), hits[0]))
        state = engine_state(run_dir)
        if state is None:
            reasons.append("engine %s unreadable or absent" % STATE_FILENAME)
        elif str(state.get("terminal") or "") not in CLOSED_TERMINALS:
            reasons.append("engine %s terminal is %r, not closed"
                           % (STATE_FILENAME, state.get("terminal")))

    verdict = "REFUSED" if reasons else "PASSED"
    if args.json:
        print(json.dumps({"gate": args.command, "phase": args.phase,
                          "verdict": verdict, "reasons": reasons}, indent=2))
    else:
        print("STEP GATE %s %s: %s" % (args.command, args.phase or "", verdict))
        for r in reasons:
            print("  - %s" % r)
    return 5 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
