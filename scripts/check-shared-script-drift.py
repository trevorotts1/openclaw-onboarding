#!/usr/bin/env python3
"""
check-shared-script-drift.py — SHARED-SCRIPT AUTHORITY / HASH-LOCK GATE (F24).

────────────────────────────────────────────────────────────────────────────
THE DEFECT
────────────────────────────────────────────────────────────────────────────
The presentations render helpers ship from TWO trees under one filename:

  CANONICAL  23-ai-workforce-blueprint/templates/role-library/presentations/scripts/
  MIRROR     23-ai-workforce-blueprint/templates/presentation-render/

`kie_generate.py` exists in both at 694 vs 613 lines. BOTH copies carry a
prose "LOCKSTEP NOTE" instructing the next editor to "keep their LOGIC
identical when editing either" — and NOTHING enforced it. The role-library
copy's own docstring already records the outcome:

    "FIX 68/67 STATUS (W21b): the role-library copy carries the platform-aware
     secrets order (presentation_job.oc_paths) AND the FIX 67 secret-name canon
     ... The presentation-render twin has NOT yet received that port"

That is a lockstep requirement written in English, graded by nobody. Same
disease as the 8 disagreeing SOPs (scripts/check-duplicate-sop-drift.py, GATE 6)
and the diverging drift-gate scripts: two artifacts under one name, each
internally consistent, disagreeing with each other, with no comparator.

`slides.schema.json` is duplicated across the same two trees and also disagrees.

────────────────────────────────────────────────────────────────────────────
WHY THE MIRROR COPY CANNOT SIMPLY BE DELETED OR QUARANTINED
────────────────────────────────────────────────────────────────────────────
The MIRROR copy is a LIVE dependency of Skill 06, not a retired path:

    06-ghl-install-pages/tools/ghl_media.py
        _KIE_GENERATE_RELPATH = os.path.join(
            "..", "..", "23-ai-workforce-blueprint", "templates",
            "presentation-render", "kie_generate.py")
        kie_generate_path()  -> raises FileNotFoundError if it is gone
        generate_images()    -> shells exactly that file

Delete or move the mirror copy and GHL media generation dies with
"reused KIE generator not found". So the fix is a HASH-LOCK, not a deletion:
pin both copies at their exact current bytes so neither can move silently,
and prove — in the gate itself — that the Skill-06 dependency still resolves.

────────────────────────────────────────────────────────────────────────────
WHAT THIS GATE ASSERTS
────────────────────────────────────────────────────────────────────────────
CHECK A — LIVE-DEPENDENCY LIVENESS (fail-closed, never waivable)
    Every entry in LIVE_DEPENDENCIES names a consumer file and the constant it
    resolves the shared script through. The constant is read with `ast` (never
    imported — the consumer pulls third-party deps), resolved relative to the
    consumer, and must (1) exist on disk and (2) live inside the MIRROR tree.
    A constant that cannot be parsed is a HARD ERROR (exit 2), never a pass:
    a gate that silently stops looking is the defect it exists to catch.

CHECK B — HASH-LOCK on every shared basename
    Every basename present in BOTH trees must be byte-identical, OR carry a
    waiver in shared-script-authority.json that pins the sha256 of BOTH copies.
    A waiver does not say "this filename may disagree" — it tolerates the
    known divergence at EXACTLY its current bytes. Edit either copy, one
    character, and the pinned pair no longer matches, the waiver stops
    applying, and the gate FAILS. A newly duplicated filename that disagrees
    has no waiver and fails immediately. A waiver whose pair has vanished is
    reported as an orphan.

The gate never rewrites either copy: reconciling the two `kie_generate.py`
implementations is a code decision that belongs to the operator (the
role-library docstring already names the four functions to port). This gate
makes the divergence impossible to EXTEND, and impossible to forget.

────────────────────────────────────────────────────────────────────────────
CLI
────────────────────────────────────────────────────────────────────────────
  --check      (default) scan + compare + apply waivers. exit 0 clean, 1 drift.
  --json       machine-readable report on stdout.
  --self-test  prove the checker still DISCRIMINATES, on scratch trees:
               identical passes, divergence fails, a correctly pinned waiver
               passes, a stale pin fails, a missing live dependency fails.
               A green --check means nothing if this does not hold.
  --record     REGENERATE the waivers from the current on-disk state. An
               explicit operator action — never run by CI. Use after
               deliberately reconciling (or deliberately changing) a copy, so
               the new bytes become the pinned baseline.
  --repo-root  override the repo root (default: walk up from this file).

EXIT CODES
  0  no shared basename disagrees except pairs whose BOTH shas match a
     recorded waiver, and every declared live dependency resolves.
  1  a shared basename disagrees without a current waiver, a recorded waiver
     no longer matches the bytes on disk, or a declared live dependency no
     longer resolves to a file inside the mirror tree.
  2  the gate could not run (repo layout not found, registry unreadable, a
     live-dependency constant that could not be parsed).
"""
import argparse
import ast
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REGISTRY_NAME = "shared-script-authority.json"

# The two trees that ship the same filenames. CANONICAL is the tree the
# presentations engine actually runs (presentation-canonical-entry.sh resolves
# --scripts-dir to it; every phase driver imports from it). MIRROR is the tree
# Skill 06 shells into.
CANONICAL_TREE = "23-ai-workforce-blueprint/templates/role-library/presentations/scripts"
MIRROR_TREE = "23-ai-workforce-blueprint/templates/presentation-render"

# Directory components never compared (build caches / VCS / editor scratch).
SKIP_DIR_NAMES = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", "node_modules"}
# Suffixes never compared (generated bytecode).
SKIP_SUFFIXES = {".pyc", ".pyo"}

# Declared LIVE consumers of the MIRROR tree. Each entry:
#   consumer  — repo-relative file that resolves a shared script
#   constant  — the module-level name holding the relative path
#   why       — what breaks if the target disappears
# Read statically with ast; the consumer is never imported.
LIVE_DEPENDENCIES = [
    {
        "consumer": "06-ghl-install-pages/tools/ghl_media.py",
        "constant": "_KIE_GENERATE_RELPATH",
        "why": (
            "ghl_media.kie_generate_path() raises FileNotFoundError and "
            "generate_images() cannot shell the generator — GHL media upload "
            "loses every image."
        ),
    },
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def find_repo_root(start: Path):
    cur = start.resolve()
    for _ in range(12):
        if (cur / CANONICAL_TREE).is_dir() and (cur / MIRROR_TREE).is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _comparable_files(tree: Path):
    """basename -> [paths], deterministic, caches and bytecode excluded."""
    out = {}
    if not tree.is_dir():
        return out
    for p in sorted(tree.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(tree).parts
        if any(part in SKIP_DIR_NAMES or part.startswith(".") for part in rel_parts[:-1]):
            continue
        if p.suffix in SKIP_SUFFIXES or p.name.startswith("."):
            continue
        out.setdefault(p.name, []).append(p)
    return out


def collect_pairs(repo_root: Path):
    """Every (basename, canonical_path, mirror_path) sharing a filename.

    A basename appearing more than once on a side yields one pair per
    occurrence — the gate must never silently pick one.
    """
    canonical = _comparable_files(repo_root / CANONICAL_TREE)
    mirror = _comparable_files(repo_root / MIRROR_TREE)
    pairs = []
    for name in sorted(set(canonical) & set(mirror)):
        for c in canonical[name]:
            for m in mirror[name]:
                pairs.append((name, c, m))
    return pairs


# ---------------------------------------------------------------------------
# CHECK A — live-dependency liveness (static, ast, never an import)
# ---------------------------------------------------------------------------
class DependencyUnreadable(Exception):
    """The consumer's path constant could not be parsed — gate cannot run."""


def _literal_path_from_node(node) -> str:
    """Evaluate a path-shaped expression to a relative string.

    Supports a plain string constant and os.path.join(...) / Path(...).joinpath
    over string constants. Anything else raises — a constant this gate cannot
    read is an ERROR, never an assumed pass.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Call):
        fname = ""
        f = node.func
        if isinstance(f, ast.Attribute):
            fname = f.attr
        elif isinstance(f, ast.Name):
            fname = f.id
        if fname in ("join", "joinpath", "Path") and node.args and not node.keywords:
            return os.path.join(*[_literal_path_from_node(a) for a in node.args])
    raise DependencyUnreadable(
        f"unsupported expression {type(node).__name__} — expected a string "
        f"constant or os.path.join(...) of string constants"
    )


def read_dependency_relpath(consumer_path: Path, constant: str) -> str:
    try:
        tree = ast.parse(consumer_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as e:
        raise DependencyUnreadable(f"could not parse {consumer_path}: {e}") from e
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Name) and t.id == constant:
                value = node.value
                if value is None:
                    raise DependencyUnreadable(
                        f"{constant} in {consumer_path} has no value")
                return _literal_path_from_node(value)
    raise DependencyUnreadable(
        f"module-level constant {constant} not found in {consumer_path} — it was "
        f"renamed or removed; this gate can no longer prove the shared script is "
        f"still reached, so it refuses to report a pass")


def evaluate_dependencies(repo_root: Path):
    """Returns (ok_list, broken_list). Raises DependencyUnreadable on rc-2 class."""
    ok, broken = [], []
    mirror_root = (repo_root / MIRROR_TREE).resolve()
    for dep in LIVE_DEPENDENCIES:
        consumer = repo_root / dep["consumer"]
        if not consumer.is_file():
            broken.append({
                "consumer": dep["consumer"], "constant": dep["constant"],
                "resolved": None,
                "problem": "consumer file not found",
                "why": dep["why"],
            })
            continue
        relpath = read_dependency_relpath(consumer, dep["constant"])
        resolved = Path(os.path.normpath(consumer.parent / relpath))
        rel_display = None
        try:
            rel_display = str(resolved.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            rel_display = str(resolved)
        entry = {
            "consumer": dep["consumer"], "constant": dep["constant"],
            "relpath": relpath, "resolved": rel_display, "why": dep["why"],
        }
        if not resolved.is_file():
            entry["problem"] = ("the shared script it shells is GONE — deleting or "
                                "quarantining the mirror copy breaks this consumer")
            broken.append(entry)
            continue
        try:
            resolved.resolve().relative_to(mirror_root)
        except ValueError:
            entry["problem"] = (f"resolves OUTSIDE {MIRROR_TREE} — this gate no longer "
                                f"covers the file this consumer actually runs")
            broken.append(entry)
            continue
        ok.append(entry)
    return ok, broken


# ---------------------------------------------------------------------------
# CHECK B — hash-lock
# ---------------------------------------------------------------------------
def load_registry(repo_root: Path):
    path = repo_root / "scripts" / REGISTRY_NAME
    if not path.is_file():
        return {"waivers": []}, path
    try:
        return json.loads(path.read_text(encoding="utf-8")), path
    except (OSError, ValueError) as e:
        print(f"FATAL: could not read {path}: {e}", file=sys.stderr)
        sys.exit(2)


def evaluate(repo_root: Path):
    pairs = collect_pairs(repo_root)
    registry, reg_path = load_registry(repo_root)
    waivers = {}
    for w in registry.get("waivers", []):
        waivers[(w["canonical_path"], w["mirror_path"])] = w

    agree, waived, violations, stale = [], [], [], []
    seen_keys = set()
    for name, cpath, mpath in pairs:
        rel_c = str(cpath.relative_to(repo_root))
        rel_m = str(mpath.relative_to(repo_root))
        sc, sm = sha256_of(cpath), sha256_of(mpath)
        key = (rel_c, rel_m)
        seen_keys.add(key)
        record = {"file": name, "canonical_path": rel_c, "mirror_path": rel_m}
        if sc == sm:
            agree.append(record)
            continue
        w = waivers.get(key)
        if w and w.get("canonical_sha256") == sc and w.get("mirror_sha256") == sm:
            waived.append({**record, "reason": w.get("reason", "")})
        elif w:
            changed = []
            if w.get("canonical_sha256") != sc:
                changed.append("canonical")
            if w.get("mirror_sha256") != sm:
                changed.append("mirror")
            stale.append({
                **record,
                "pinned_canonical_sha256": w.get("canonical_sha256"),
                "actual_canonical_sha256": sc,
                "pinned_mirror_sha256": w.get("mirror_sha256"),
                "actual_mirror_sha256": sm,
                "changed_side": "+".join(changed),
            })
        else:
            violations.append({**record, "canonical_sha256": sc, "mirror_sha256": sm})

    orphan_waivers = [{"canonical_path": k[0], "mirror_path": k[1]}
                      for k in sorted(waivers) if k not in seen_keys]

    dep_error = None
    try:
        deps_ok, deps_broken = evaluate_dependencies(repo_root)
    except DependencyUnreadable as e:
        deps_ok, deps_broken = [], []
        dep_error = str(e)

    return {
        "pairs_examined": len(pairs),
        "agree": agree,
        "waived": waived,
        "violations": violations,
        "stale_waivers": stale,
        "orphan_waivers": orphan_waivers,
        "live_dependencies_ok": deps_ok,
        "live_dependencies_broken": deps_broken,
        "live_dependency_error": dep_error,
        "registry_path": str(reg_path),
        "canonical_tree": CANONICAL_TREE,
        "mirror_tree": MIRROR_TREE,
    }


def report_is_clean(r) -> bool:
    return not (r["violations"] or r["stale_waivers"] or r["orphan_waivers"]
                or r["live_dependencies_broken"])


def do_record(repo_root: Path):
    pairs = collect_pairs(repo_root)
    registry, reg_path = load_registry(repo_root)
    prev = {(w["canonical_path"], w["mirror_path"]): w
            for w in registry.get("waivers", [])}
    waivers = []
    for name, cpath, mpath in pairs:
        sc, sm = sha256_of(cpath), sha256_of(mpath)
        if sc == sm:
            continue
        rel_c = str(cpath.relative_to(repo_root))
        rel_m = str(mpath.relative_to(repo_root))
        old = prev.get((rel_c, rel_m), {})
        waivers.append({
            "file": name,
            "canonical_path": rel_c,
            "mirror_path": rel_m,
            "canonical_sha256": sc,
            "mirror_sha256": sm,
            "canonical_side": old.get("canonical_side", "role-library-scripts"),
            "reason": old.get(
                "reason",
                "Pre-existing divergence recorded, not reconciled. Reconciling the two "
                "implementations is a code decision that belongs to the operator. Pinned "
                "by sha256 on BOTH sides: any edit to either copy invalidates this waiver "
                "and the gate fails until the change is reviewed and re-recorded."),
            "recorded_at": old.get(
                "recorded_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        })
    registry["waivers"] = waivers
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    # ensure_ascii=False so re-recording is byte-idempotent: the registry's
    # hand-written evidence prose keeps its em-dashes instead of being rewritten
    # into \uXXXX escapes on every --record.
    reg_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"recorded {len(waivers)} waiver(s) to {reg_path}")
    return 0


# ---------------------------------------------------------------------------
# --self-test — the known-good control, on the instrument itself
# ---------------------------------------------------------------------------
_SELFTEST_CONSUMER = '''"""scratch consumer for --self-test"""
import os

_KIE_GENERATE_RELPATH = os.path.join(
    "..", "..", "23-ai-workforce-blueprint", "templates",
    "presentation-render", "kie_generate.py",
)
'''


def _build_scratch_repo(root: Path, *, canonical_body: str, mirror_body: str,
                        waiver: dict | None, with_mirror_file: bool = True,
                        with_consumer: bool = True):
    canon_dir = root / CANONICAL_TREE
    mirror_dir = root / MIRROR_TREE
    canon_dir.mkdir(parents=True)
    mirror_dir.mkdir(parents=True)
    (canon_dir / "kie_generate.py").write_text(canonical_body, encoding="utf-8")
    if with_mirror_file:
        (mirror_dir / "kie_generate.py").write_text(mirror_body, encoding="utf-8")
    else:
        # tree must still exist, or find_repo_root/mirror scan cannot run
        (mirror_dir / "render_deck.py").write_text("# unrelated\n", encoding="utf-8")
    if with_consumer:
        consumer = root / "06-ghl-install-pages" / "tools" / "ghl_media.py"
        consumer.parent.mkdir(parents=True)
        consumer.write_text(_SELFTEST_CONSUMER, encoding="utf-8")
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    registry = {"_README": "self-test scratch", "waivers": [w for w in ([waiver] if waiver else [])]}
    (scripts / REGISTRY_NAME).write_text(json.dumps(registry, indent=2) + "\n",
                                         encoding="utf-8")


def _waiver_for(canonical_body: str, mirror_body: str, *, stale: bool = False):
    return {
        "file": "kie_generate.py",
        "canonical_path": f"{CANONICAL_TREE}/kie_generate.py",
        "mirror_path": f"{MIRROR_TREE}/kie_generate.py",
        "canonical_sha256": hashlib.sha256(canonical_body.encode()).hexdigest(),
        "mirror_sha256": hashlib.sha256(
            (mirror_body + ("  # pin recorded before this edit" if stale else "")).encode()
        ).hexdigest(),
        "reason": "self-test",
    }


def do_self_test() -> int:
    A = "# canonical\nprint('a')\n"
    B = "# mirror — diverged\nprint('b')\n"
    cases = []

    def case(label, *, canonical_body, mirror_body, waiver, expect_clean,
             with_mirror_file=True, with_consumer=True, expect_reason_key=None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            _build_scratch_repo(root, canonical_body=canonical_body,
                                mirror_body=mirror_body, waiver=waiver,
                                with_mirror_file=with_mirror_file,
                                with_consumer=with_consumer)
            r = evaluate(root)
            clean = report_is_clean(r)
            ok = (clean == expect_clean)
            if ok and expect_reason_key:
                ok = bool(r[expect_reason_key])
            cases.append((label, ok, clean, expect_clean,
                          {k: len(r[k]) for k in ("agree", "waived", "violations",
                                                  "stale_waivers", "orphan_waivers",
                                                  "live_dependencies_broken")}))

    # (a) identical copies, no waiver -> clean
    case("identical copies pass", canonical_body=A, mirror_body=A,
         waiver=None, expect_clean=True)
    # (b) divergence with no waiver -> FAIL (this is the F24 defect class)
    case("unwaived divergence fails", canonical_body=A, mirror_body=B,
         waiver=None, expect_clean=False, expect_reason_key="violations")
    # (c) divergence with a correctly pinned waiver -> clean
    case("correctly pinned waiver passes", canonical_body=A, mirror_body=B,
         waiver=_waiver_for(A, B), expect_clean=True)
    # (d) divergence whose pin no longer matches the bytes -> FAIL
    case("stale pin fails", canonical_body=A, mirror_body=B,
         waiver=_waiver_for(A, B, stale=True), expect_clean=False,
         expect_reason_key="stale_waivers")
    # (e) the live Skill-06 dependency target deleted -> FAIL
    case("deleted live dependency fails", canonical_body=A, mirror_body=B,
         waiver=_waiver_for(A, B), expect_clean=False, with_mirror_file=False,
         expect_reason_key="live_dependencies_broken")
    # (f) the consumer itself gone -> FAIL (never a silent pass)
    case("missing consumer fails", canonical_body=A, mirror_body=A,
         waiver=None, expect_clean=False, with_consumer=False,
         expect_reason_key="live_dependencies_broken")

    # (g) an unreadable path constant is a HARD error, not a pass.
    unreadable_ok = False
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        root.mkdir()
        _build_scratch_repo(root, canonical_body=A, mirror_body=A, waiver=None)
        consumer = root / "06-ghl-install-pages" / "tools" / "ghl_media.py"
        consumer.write_text("import os\n_KIE_GENERATE_RELPATH = os.environ['X']\n",
                            encoding="utf-8")
        r = evaluate(root)
        unreadable_ok = bool(r["live_dependency_error"])
    cases.append(("unparseable path constant errors", unreadable_ok,
                  not unreadable_ok, False, {}))

    failed = [c for c in cases if not c[1]]
    print("== check-shared-script-drift --self-test ==")
    for label, ok, clean, expect_clean, counts in cases:
        mark = "OK  " if ok else "FAIL"
        print(f"  [{mark}] {label} (clean={clean}, expected_clean={expect_clean}) {counts}")
    if failed:
        print("\nSELFTEST_FAIL: the checker no longer discriminates — a green --check "
              "would mean nothing. Failing case(s): "
              + ", ".join(c[0] for c in failed), file=sys.stderr)
        return 1
    print(f"\nSELFTEST_PASS: {len(cases)} discrimination cases hold.")
    return 0


# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Hash-lock the shared presentations render scripts that ship "
                    "from two trees under one filename.")
    ap.add_argument("--check", action="store_true", default=True)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    ap.add_argument("--repo-root", default=None)
    args = ap.parse_args(argv)

    if args.self_test:
        return do_self_test()

    repo_root = Path(args.repo_root) if args.repo_root else find_repo_root(Path(__file__).parent)
    if repo_root is None:
        print(f"FATAL: repo root not found (need {CANONICAL_TREE}/ and {MIRROR_TREE}/)",
              file=sys.stderr)
        return 2

    if args.record:
        return do_record(repo_root)

    try:
        r = evaluate(repo_root)
    except DependencyUnreadable as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2
    if r["live_dependency_error"]:
        print(f"FATAL: {r['live_dependency_error']}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print("== SHARED-SCRIPT AUTHORITY / HASH-LOCK GATE (F24) ==")
        print(f"   canonical tree                 : {CANONICAL_TREE}")
        print(f"   mirror tree                    : {MIRROR_TREE}")
        print(f"   shared basenames examined      : {r['pairs_examined']}")
        print(f"   identical (no drift)           : {len(r['agree'])}")
        print(f"   disagree, waived at pinned sha : {len(r['waived'])}")
        print(f"   disagree, NOT waived           : {len(r['violations'])}")
        print(f"   waivers stale (bytes moved)    : {len(r['stale_waivers'])}")
        print(f"   waivers for vanished pairs     : {len(r['orphan_waivers'])}")
        print(f"   live dependencies resolved     : {len(r['live_dependencies_ok'])}")
        print(f"   live dependencies BROKEN       : {len(r['live_dependencies_broken'])}")
        for d in r["live_dependencies_ok"]:
            print(f"     LIVE OK: {d['consumer']}:{d['constant']} -> {d['resolved']}")
        for v in r["violations"]:
            print(f"\n   DRIFT (unwaived): {v['file']}", file=sys.stderr)
            print(f"     canonical : {v['canonical_path']}  sha {v['canonical_sha256'][:16]}",
                  file=sys.stderr)
            print(f"     mirror    : {v['mirror_path']}  sha {v['mirror_sha256'][:16]}",
                  file=sys.stderr)
        for s in r["stale_waivers"]:
            print(f"\n   STALE PIN: {s['file']} — the {s['changed_side']} copy changed "
                  f"since the hash-lock was recorded.", file=sys.stderr)
            print(f"     canonical pinned {str(s['pinned_canonical_sha256'])[:16]} "
                  f"actual {s['actual_canonical_sha256'][:16]}", file=sys.stderr)
            print(f"     mirror    pinned {str(s['pinned_mirror_sha256'])[:16]} "
                  f"actual {s['actual_mirror_sha256'][:16]}", file=sys.stderr)
        for o in r["orphan_waivers"]:
            print(f"\n   ORPHAN PIN: no such pair on disk any more — "
                  f"{o['canonical_path']} <-> {o['mirror_path']}", file=sys.stderr)
        for b in r["live_dependencies_broken"]:
            print(f"\n   LIVE DEPENDENCY BROKEN: {b['consumer']}:{b['constant']}",
                  file=sys.stderr)
            print(f"     resolved : {b['resolved']}", file=sys.stderr)
            print(f"     problem  : {b['problem']}", file=sys.stderr)
            print(f"     impact   : {b['why']}", file=sys.stderr)

    if not report_is_clean(r):
        print("\nGATE FAILED: the shared presentations render scripts are no longer "
              "hash-locked.\n"
              "  Both trees ship the same filenames and BOTH copies carry a prose\n"
              "  'LOCKSTEP NOTE' telling the next editor to keep their logic identical;\n"
              "  nothing but this gate grades that. The mirror copy is a LIVE Skill-06\n"
              "  dependency (ghl_media.kie_generate_path) — never delete or quarantine it.\n"
              "  Fix by porting the change to the other copy, or — if the divergence is\n"
              "  deliberate — re-record the baseline with:\n"
              "      python3 scripts/check-shared-script-drift.py --record",
              file=sys.stderr)
        return 1
    print("\nGATE PASSED: every shared basename is identical or pinned at its recorded "
          "bytes, and every declared live dependency resolves inside the mirror tree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
