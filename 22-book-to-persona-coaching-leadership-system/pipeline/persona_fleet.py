#!/usr/bin/env python3
"""
persona_fleet.py — the hermetic, stdlib-only core shared by the persona
"publish to fleet" tooling (publish-personas-to-fleet.sh),
the divergence GUARD (assert-personas-published.sh), and the pipeline
final-phase status marker (fleet-publish-status.sh).

WHY THIS EXISTS (the divergence it kills)
------------------------------------------
The Skill-22 book pipeline (add-persona-from-source.sh / orchestrator.py /
persona-inbox-watcher.sh) is a WORKSPACE-ONLY writer: it registers a new
persona (blueprint + persona-categories.json entry) under
  ~/.openclaw/workspace/data/coaching-personas/   (Mac)
  /data/.openclaw/.../coaching-personas/           (VPS)
and NEVER writes the repo checkout. The repo-side library — the shipped
  22-book-to-persona-coaching-leadership-system/personas/<slug>/persona-blueprint.md
blueprint dirs + 22-.../persona-categories.json seed + the prebuilt-index
INDEX-MANIFEST.json (persona_count/canonical_persona_count) — was a hand-
maintained artifact. shared-utils/prebuilt-index/build-and-publish.sh
automated ONLY the manifest + release asset; it READS the repo blueprint
dirs / categories to compute counts but never WRITES them. So after a book
build the workspace advances (e.g. 81) while the repo library lags (e.g. 65),
and the N38 count-triad
  blueprint dirs == categories keys == manifest.persona_count == canonical
is caught only LATE (CI / PR / build-preflight), turning main red at the new
count until someone hand-catches the repo up, or shipping the OLD count on a
roll off a stale commit.

This module is the single place that:
  * enumerates the current WORKSPACE persona set (workspace-slugs)
  * SANITIZES a workspace blueprint of operator-local absolute paths so only
    a repo-safe persona-blueprint.md ships (sanitize)
  * SYNCS the repo persona-categories.json from the workspace with
    controlled-vocabulary tag validation (sync-categories)
  * hermetically syncs the manifest COUNT fields (set-manifest-counts)
  * proves the N38 count-TRIAD agrees (triad)
  * reports which workspace personas are missing from the repo (diff-slugs)

Pure stdlib (json, hashlib, argparse, re, pathlib, datetime, shutil, sys).
No network. No third-party deps. Read/compute only — the caller owns the
snapshot/rollback so a failed publish leaves NO half-committed state.

EXIT CODES
  0   ok
  2   usage / IO error (missing file, unreadable json)
  4   controlled-vocabulary violation (a tag is out of the allowed set / shape)
  5   TRIAD DISAGREES (the count invariant is broken)
"""

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

SK22_DIRNAME = "22-book-to-persona-coaching-leadership-system"
MANIFEST_REL = "shared-utils/prebuilt-index/INDEX-MANIFEST.json"
BLUEPRINT_NAME = "persona-blueprint.md"
CANONICAL_ENTRY_FIELDS = ("author", "book", "domain", "perspective", "custom")

# ── Operator-local absolute-path patterns to strip from a shipped blueprint ──
# These are machine/operator-local roots that must NEVER appear in a tracked,
# fleet-wide file. Relative paths (e.g. ./google-embedding-index/) are LEFT
# intact — only absolute operator-local roots are scrubbed.
_LOCAL_PATH_RE = re.compile(
    r"""(?:~|\$HOME)?/(?:
          Users/[^\s`"')]+                         # /Users/<name>/...
        | home/[^\s`"')]+                           # /home/<name>/...
        | data/\.openclaw[^\s`"')]*                 # /data/.openclaw/...
      )
      |
      ~?/?\.openclaw[^\s`"')]*                       # ~/.openclaw/... or .openclaw/...
      |
      ~/Downloads/openclaw-master-files[^\s`"')]*    # the observed 'Saved to:' leak
    """,
    re.VERBOSE,
)

# A line that is ONLY a (optionally backticked/bulleted) operator-local path,
# or a "Saved to: <path>" / "Output: <path>" style footer — dropped whole.
_FOOTER_LABEL_RE = re.compile(
    r"^\s*(?:[-*>]\s*)?(?:\*\*|__)?\s*"
    r"(?:saved(?:\s+to)?|output(?:\s+to)?|written\s+to|location|file\s+path|path|index\s+file)"
    r"\s*:?\s*(?:\*\*|__)?\s*`?\s*",
    re.IGNORECASE,
)


def _die(msg, code=2):
    sys.stderr.write(msg.rstrip("\n") + "\n")
    raise SystemExit(code)


def _load_json(path):
    p = Path(path)
    if not p.is_file():
        _die(f"file not found: {p}", 2)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        _die(f"unreadable json {p}: {e}", 2)


def _dump_json(obj, path):
    """Deterministic write: indent=2, preserve key order, trailing newline —
    byte-stable so persona_set_md5 (md5 of the file) is reproducible."""
    Path(path).write_text(
        json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _today():
    return datetime.date.today().isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# SANITIZE
# ─────────────────────────────────────────────────────────────────────────────
def sanitize_text(text):
    """Return (clean_text, dropped, redacted).

    * A line that is only an operator-local path, or a "Saved to: <path>"
      footer, is DROPPED entirely.
    * Any operator-local absolute path that survives inline (path embedded in
      prose) is replaced with the marker <local-path-redacted>.
    Relative paths are untouched.
    """
    out = []
    dropped = 0
    redacted = 0
    for line in text.splitlines():
        has_local = bool(_LOCAL_PATH_RE.search(line))
        if has_local:
            stripped = line.strip().strip("`").strip("*").strip()
            # whole-line footer: "Saved to: <path>" / "<path>" / "- `<path>`"
            after_label = _FOOTER_LABEL_RE.sub("", line)
            after_label_core = _LOCAL_PATH_RE.sub("", after_label).strip().strip("`").strip("*").strip()
            only_path = _LOCAL_PATH_RE.sub("", stripped).strip().strip("`").strip("*").strip()
            if after_label_core == "" or only_path == "":
                dropped += 1
                continue
            # path embedded in prose -> redact the path substring, keep the line
            new_line, n = _LOCAL_PATH_RE.subn("<local-path-redacted>", line)
            redacted += n
            out.append(new_line)
        else:
            out.append(line)
    clean = "\n".join(out)
    if text.endswith("\n"):
        clean += "\n"
    return clean, dropped, redacted


def cmd_sanitize(args):
    src = Path(args.inp)
    if not src.is_file():
        _die(f"blueprint not found: {src}", 2)
    clean, dropped, redacted = sanitize_text(src.read_text(encoding="utf-8"))
    Path(args.out).write_text(clean, encoding="utf-8")
    if args.verbose:
        sys.stderr.write(
            f"sanitize {src.name}: dropped {dropped} path line(s), "
            f"redacted {redacted} inline path(s)\n")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# WORKSPACE ENUMERATION
# ─────────────────────────────────────────────────────────────────────────────
def _blueprint_slugs(personas_dir):
    d = Path(personas_dir)
    if not d.is_dir():
        return set()
    return {p.name for p in d.iterdir()
            if p.is_dir() and (p / BLUEPRINT_NAME).is_file()}


def _categories_slugs(categories_path):
    p = Path(categories_path)
    if not p.is_file():
        return set()
    try:
        return set(json.loads(p.read_text(encoding="utf-8")).get("personas", {}).keys())
    except Exception:  # noqa: BLE001
        return set()


def workspace_slugs(workspace_dir):
    """The publishable workspace set = slugs that have BOTH a blueprint dir AND
    a persona-categories.json entry. Returns (publishable, orphan_blueprint,
    orphan_categories)."""
    ws = Path(workspace_dir)
    bp = _blueprint_slugs(ws / "personas")
    cat = _categories_slugs(ws / "persona-categories.json")
    return sorted(bp & cat), sorted(bp - cat), sorted(cat - bp)


def cmd_workspace_slugs(args):
    pub, orphan_bp, orphan_cat = workspace_slugs(args.workspace)
    for s in orphan_bp:
        sys.stderr.write(f"warn: workspace persona '{s}' has a blueprint but no "
                         f"persona-categories.json entry — not publishable\n")
    for s in orphan_cat:
        sys.stderr.write(f"warn: workspace persona '{s}' has a categories entry "
                         f"but no blueprint — not publishable\n")
    for s in pub:
        print(s)
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# REPO ENUMERATION + TRIAD
# ─────────────────────────────────────────────────────────────────────────────
def _sk22(repo_root):
    return Path(repo_root) / SK22_DIRNAME


def repo_slugs(repo_root):
    sk = _sk22(repo_root)
    bp = _blueprint_slugs(sk / "personas")
    cat = _categories_slugs(sk / "persona-categories.json")
    return sorted(bp & cat), sorted(bp), sorted(cat)


def triad_counts(repo_root):
    sk = _sk22(repo_root)
    personas_dir = sk / "personas"
    cats_path = sk / "persona-categories.json"
    manifest_path = Path(repo_root) / MANIFEST_REL
    dir_count = (sum(1 for p in personas_dir.iterdir() if p.is_dir())
                 if personas_dir.is_dir() else None)
    cats_count = (len(_load_json(cats_path).get("personas", {}))
                  if cats_path.is_file() else None)
    man_count = man_canon = None
    if manifest_path.is_file():
        m = _load_json(manifest_path)
        man_count = int(m.get("persona_count", -1))
        man_canon = int(m.get("canonical_persona_count", -1))
    return {
        "blueprint_dirs": dir_count,
        "categories.json_keys": cats_count,
        "manifest.persona_count": man_count,
        "manifest.canonical_persona_count": man_canon,
    }


def cmd_triad(args):
    vals = triad_counts(args.repo_root)
    present = {k: v for k, v in vals.items() if v is not None}
    agree = len(set(present.values())) == 1 and len(present) == 4
    if args.json:
        print(json.dumps({"counts": vals, "agree": agree}))
    else:
        print("Persona-SET count triad:")
        for k, v in vals.items():
            print(f"  {k} = {v}")
    if not agree:
        sys.stderr.write(
            "\nTRIAD DISAGREES — a persona is in the workspace/asset but the repo "
            "library was not caught up (or a count was bumped without a blueprint). "
            "Bring all four into lockstep in ONE run:\n"
            "    22-book-to-persona-coaching-leadership-system/pipeline/"
            "publish-personas-to-fleet.sh\n")
        return 5
    return 0


def cmd_diff_slugs(args):
    """Print workspace personas missing from the repo library (one per line)."""
    pub, _, _ = workspace_slugs(args.workspace)
    repo_pub, _, _ = repo_slugs(args.repo_root)
    missing = [s for s in pub if s not in set(repo_pub)]
    for s in missing:
        print(s)
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# SYNC CATEGORIES (controlled-vocabulary validated)
# ─────────────────────────────────────────────────────────────────────────────
_KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate_entry(slug, entry, domain_vocab, perspective_vocab):
    errs = []
    if not isinstance(entry, dict):
        return [f"{slug}: categories entry is not an object"]
    dom = entry.get("domain", [])
    per = entry.get("perspective", [])
    cus = entry.get("custom", [])
    if not isinstance(dom, list) or not dom:
        errs.append(f"{slug}: 'domain' must be a non-empty list")
    else:
        for t in dom:
            if t not in domain_vocab:
                errs.append(f"{slug}: domain tag '{t}' is not in the controlled "
                            f"vocabulary domainTags (add it to domainTags first)")
    if not isinstance(per, list):
        errs.append(f"{slug}: 'perspective' must be a list")
    else:
        for t in per:
            if t not in perspective_vocab:
                errs.append(f"{slug}: perspective tag '{t}' is not in the "
                            f"controlled vocabulary perspectiveTags")
    if not isinstance(cus, list):
        errs.append(f"{slug}: 'custom' must be a list")
    else:
        for t in cus:
            if not _KEBAB_RE.match(str(t)):
                errs.append(f"{slug}: custom tag '{t}' is not kebab-case")
    return errs


def sync_categories(workspace_cat_path, repo_cat_path, slugs):
    """Merge the given workspace persona slugs into the repo categories seed,
    validating each entry against the repo's controlled vocabulary. Returns the
    list of slugs actually added/updated. Raises SystemExit(4) on any vocab
    violation (caller rolls back)."""
    ws = _load_json(workspace_cat_path)
    repo = _load_json(repo_cat_path)
    ws_personas = ws.get("personas", {})
    repo_personas = repo.setdefault("personas", {})
    domain_vocab = set(repo.get("domainTags", []))
    perspective_vocab = set(repo.get("perspectiveTags", []))

    errors = []
    to_write = {}
    for slug in slugs:
        entry = ws_personas.get(slug)
        if entry is None:
            errors.append(f"{slug}: no persona-categories.json entry in the workspace")
            continue
        errors.extend(_validate_entry(slug, entry, domain_vocab, perspective_vocab))
        # Ship only the canonical seed fields (drop workspace-only bookkeeping).
        clean = {}
        for f in CANONICAL_ENTRY_FIELDS:
            if f in entry:
                clean[f] = entry[f]
        clean.setdefault("domain", [])
        clean.setdefault("perspective", [])
        clean.setdefault("custom", [])
        to_write[slug] = clean

    if errors:
        for e in errors:
            sys.stderr.write("  ✗ " + e + "\n")
        _die("controlled-vocabulary validation FAILED — no categories written",
             4)

    changed = []
    for slug, clean in to_write.items():
        if repo_personas.get(slug) != clean:
            repo_personas[slug] = clean
            changed.append(slug)
    if changed:
        repo["lastUpdated"] = _today()
    _dump_json(repo, repo_cat_path)
    return changed


def cmd_sync_categories(args):
    slugs = [s for s in (args.slugs or "").split(",") if s]
    changed = sync_categories(args.workspace_cat, args.repo_cat, slugs)
    sys.stderr.write(f"sync-categories: {len(changed)} entr"
                     f"{'y' if len(changed) == 1 else 'ies'} added/updated\n")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# MANIFEST COUNT SYNC (hermetic subset of build-and-publish.sh step 5)
# ─────────────────────────────────────────────────────────────────────────────
def set_manifest_counts(manifest_path, count, repo_cat_path, no_asset=False):
    m = _load_json(manifest_path)
    m["persona_count"] = int(count)
    m["canonical_persona_count"] = int(count)
    m["persona_set_md5"] = hashlib.md5(
        Path(repo_cat_path).read_bytes()).hexdigest()
    m["manifest_last_updated"] = _today()
    if no_asset:
        m["asset_rebuild_required"] = True
        m["fleet_sync_note"] = (
            "Count fields synced hermetically by publish-personas-to-fleet.sh "
            "(--no-asset): blueprint dirs == categories keys == persona_count "
            "== canonical_persona_count. The release ASSET (embeddings) still "
            "needs a real delta embed+publish via "
            "shared-utils/prebuilt-index/build-and-publish.sh (or a full "
            "publish-personas-to-fleet.sh run) before the fleet points at it.")
    _dump_json(m, manifest_path)
    return 0


def cmd_set_manifest_counts(args):
    return set_manifest_counts(args.manifest, args.count, args.repo_cat,
                               no_asset=args.no_asset)


# ─────────────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="persona fleet-sync core")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sanitize")
    s.add_argument("--in", dest="inp", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(func=cmd_sanitize)

    s = sub.add_parser("workspace-slugs")
    s.add_argument("--workspace", required=True)
    s.set_defaults(func=cmd_workspace_slugs)

    s = sub.add_parser("triad")
    s.add_argument("--repo-root", required=True)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_triad)

    s = sub.add_parser("diff-slugs")
    s.add_argument("--workspace", required=True)
    s.add_argument("--repo-root", required=True)
    s.set_defaults(func=cmd_diff_slugs)

    s = sub.add_parser("sync-categories")
    s.add_argument("--workspace-cat", required=True)
    s.add_argument("--repo-cat", required=True)
    s.add_argument("--slugs", required=True, help="comma-separated slugs")
    s.set_defaults(func=cmd_sync_categories)

    s = sub.add_parser("set-manifest-counts")
    s.add_argument("--manifest", required=True)
    s.add_argument("--count", type=int, required=True)
    s.add_argument("--repo-cat", required=True)
    s.add_argument("--no-asset", action="store_true")
    s.set_defaults(func=cmd_set_manifest_counts)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
