#!/usr/bin/env python3
"""
test-zhe-persona-index-sufficiency.py — regression suite for the ZHE persona
index check in prove-zhe.py (check_personas_canonical).

WHAT THIS PINS
--------------
The old check required `rows >= int(4413 * 0.90) == 3971` raw rows in the
coaching-personas `embeddings` table. 4413 was a snapshot of ONE box at ONE
moment, taken while that box was MID-MIGRATION between two indexers that store
DIFFERENT UNITS:

    gemini-indexer.py          (legacy)  -> one row per CHARACTER CHUNK
    gemini-section-indexer.py  (current) -> one row per `##` SECTION

gemini-section-indexer.py deletes every chunk row for a persona and replaces it
with one row per section, so a FULLY MIGRATED box has roughly a third of the
rows the constant was taken from. The floor therefore rejected boxes for being
correctly built, and the tempting remedy — rebuilding the index — is DESTRUCTIVE
and reproduces the same row count, so it could never have helped.

The replacement asserts COVERAGE derived from the corpus in front of us: most
on-disk personas appear in the index, plus a conservative per-persona row
minimum. Both are unit-agnostic, so a chunk index and a section index both pass.

Test 1 is the load-bearing one: a CORRECT, fully-migrated section-level index
must PASS the new rule and would have FAILED the old 3971-row floor.

HERMETIC: builds sqlite fixtures under a mktemp dir. Touches no workspace, no
~/.openclaw, no client box, no network. prove-zhe.py is imported as a module and
only its pure check function is exercised — nothing is executed against a real
OpenClaw root.

USAGE: python3 test-zhe-persona-index-sufficiency.py
EXIT:  0 = all pass, 1 = one or more failed
"""
import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PASSED = 0
FAILED = 0

# ── HERMETIC SANDBOX (must be established BEFORE prove-zhe.py is imported) ────
# prove-zhe.py imports detect_platform, which resolves an OpenClaw root at module
# load time and aborts when it finds none. We give it a throwaway one INSIDE our
# temp dir and redirect HOME there, so nothing in this suite can reach the real
# ~/.openclaw. /data/.openclaw takes precedence over $HOME in the platform
# detector, so we refuse to run if it exists rather than risk a live workspace.
if os.path.isdir("/data/.openclaw"):
    print("SKIP: /data/.openclaw exists — a HOME override cannot contain this run.",
          file=sys.stderr)
    sys.exit(0)

SANDBOX = tempfile.mkdtemp(prefix="zhe-index-sandbox.")
os.makedirs(os.path.join(SANDBOX, ".openclaw", "workspace"), exist_ok=True)
os.environ["HOME"] = SANDBOX
os.environ["OPENCLAW_PLATFORM"] = "mac"   # documented CI/static-check override


def ok(msg):
    global PASSED
    PASSED += 1
    print(f"  PASS: {msg}")


def bad(msg):
    global FAILED
    FAILED += 1
    print(f"  FAIL: {msg}", file=sys.stderr)


def check(cond, msg):
    ok(msg) if cond else bad(msg)


def load_prove_zhe():
    path = os.path.join(SCRIPT_DIR, "prove-zhe.py")
    spec = importlib.util.spec_from_file_location("prove_zhe_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── fixture helpers ──────────────────────────────────────────────────────────

def seed_index(db_path, n_personas, rows_per_persona, persona_col="persona_id",
               tagged=True):
    """Build an `embeddings` table shaped like the real one."""
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            f"CREATE TABLE embeddings ("
            f"id INTEGER PRIMARY KEY, {persona_col} TEXT, content TEXT, "
            f"mode TEXT DEFAULT 'both', section_number INTEGER)"
        )
        modes = ("leadership", "coaching", "both")
        rows = []
        rid = 0
        for p in range(n_personas):
            for s in range(rows_per_persona):
                if tagged:
                    mode, section = modes[rid % 3], (s + 1)
                else:
                    # The documented "migrated but never tagged" shape:
                    # section-tag-migration.py adds `mode` with DEFAULT 'both' and
                    # backfills NULL->'both', so an UNTAGGED box reads mode='both'
                    # everywhere AND section_number all NULL. Leaving real
                    # leadership/coaching modes here would make the row genuinely
                    # tagged via the mode signal and the fixture would not be
                    # testing what it claims to.
                    mode, section = "both", None
                rows.append((rid, f"persona-{p:03d}", f"body-{rid}", mode, section))
                rid += 1
        cur.executemany(
            f"INSERT INTO embeddings (id, {persona_col}, content, mode, section_number) "
            f"VALUES (?, ?, ?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()


def build_corpus(root, n_personas, index_personas, rows_per_persona,
                 persona_col="persona_id", tagged=True, seed_db=True):
    """Lay out <root>/data/coaching-personas/{personas/*, persona-categories.json,
    gemini-index.sqlite} exactly where check_personas_canonical looks."""
    cp = os.path.join(root, "data", "coaching-personas")
    personas = os.path.join(cp, "personas")
    os.makedirs(personas, exist_ok=True)
    for p in range(n_personas):
        d = os.path.join(personas, f"persona-{p:03d}")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "persona-blueprint.md"), "w") as f:
            f.write("## 1 Identity\nbody\n")
    import json
    with open(os.path.join(cp, "persona-categories.json"), "w") as f:
        json.dump({
            "personas": {f"persona-{p:03d}": {} for p in range(n_personas)},
            "domainTags": ["sales", "leadership", "ops"],
        }, f)
    if seed_db:
        seed_index(os.path.join(cp, "gemini-index.sqlite"),
                   index_personas, rows_per_persona,
                   persona_col=persona_col, tagged=tagged)
    return cp


class LocalFS:
    """The minimal filesystem shim check_personas_canonical uses."""
    def listdir(self, p):
        try:
            return os.listdir(p)
        except OSError:
            return []

    def isdir(self, p):
        return os.path.isdir(p)

    def read_text(self, p):
        try:
            with open(p, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None


def main():
    pz = load_prove_zhe()

    # prove-zhe runs its sqlite probe through box_python() (ssh on a remote box).
    # For a local fixture, run the same probe source in-process — same SQL, same
    # parsing, zero network, zero box.
    import json as _json

    def local_box_python(fs, src):
        import subprocess
        r = subprocess.run([sys.executable, "-c", src],
                           capture_output=True, text=True, timeout=60)
        try:
            return _json.loads(r.stdout.strip() or "{}")
        except ValueError:
            return {"error": f"probe output not JSON: {r.stdout[:200]} {r.stderr[:200]}"}

    pz.box_python = local_box_python
    fs = LocalFS()

    tmp = os.path.join(SANDBOX, "fixtures")
    os.makedirs(tmp, exist_ok=True)
    # HERMETIC GUARD: every fixture must live under the sandbox we created.
    assert tmp.startswith(SANDBOX), "fixture escaped the sandbox"
    assert os.environ["HOME"] == SANDBOX, "HOME is not redirected into the sandbox"
    try:
        print("=" * 62)
        print("ZHE persona-index sufficiency regression suite")
        print(f"fixture: {tmp}")
        print("=" * 62)

        # The retired floor, recomputed here so the test states it explicitly.
        OLD_FLOOR = int(4413 * 0.90)  # 3971
        check(OLD_FLOOR == 3971, f"the retired floor is {OLD_FLOOR} raw rows")

        # ── 1. THE LOAD-BEARING CASE ────────────────────────────────────────
        # A correct, fully-migrated SECTION-level index over a realistic corpus.
        # 99 personas x 14 median sections = 1386 rows — well under the old 3971
        # floor, which is exactly why correctly-built boxes were failing.
        print("\n[1] a fully-migrated section-level index must PASS")
        ws = os.path.join(tmp, "migrated")
        build_corpus(ws, n_personas=99, index_personas=99, rows_per_persona=14)
        res = pz.check_personas_canonical(fs, ws)
        check(res["index_rows"] == 1386,
              f"section-level index has {res['index_rows']} rows (99 personas x 14 sections)")
        check(res["index_rows"] < OLD_FLOOR,
              f"{res['index_rows']} rows is BELOW the retired {OLD_FLOOR}-row floor "
              f"— the old rule rejected this correct index")
        check(res["pass"] is True,
              "the derived rule PASSES the fully-migrated section-level index")
        check(res["index_personas_covered"] == 99,
              "all 99 personas are covered in the index")

        # ── 2. a legacy CHUNK-level index must still pass ────────────────────
        print("\n[2] a legacy chunk-level index must still PASS (unit-agnostic)")
        ws = os.path.join(tmp, "chunked")
        build_corpus(ws, n_personas=54, index_personas=54, rows_per_persona=82)
        res = pz.check_personas_canonical(fs, ws)
        check(res["index_rows"] == 4428, f"chunk-level index has {res['index_rows']} rows")
        check(res["pass"] is True, "the derived rule PASSES a legacy chunk-level index")

        # ── 3. NEGATIVE: a truncated index must FAIL ─────────────────────────
        print("\n[3] a truncated index must FAIL (the rule still has teeth)")
        ws = os.path.join(tmp, "truncated")
        # 99 personas on disk but only 40 of them indexed — a half-written run.
        build_corpus(ws, n_personas=99, index_personas=40, rows_per_persona=14)
        res = pz.check_personas_canonical(fs, ws)
        check(res["index_personas_covered"] == 40,
              "only 40 of 99 personas are covered")
        check(res["pass"] is False,
              "a half-written index FAILS the coverage rule")

        # ── 4. NEGATIVE: too few rows per persona must FAIL ──────────────────
        print("\n[4] an index with too few rows per persona must FAIL")
        ws = os.path.join(tmp, "thin")
        build_corpus(ws, n_personas=99, index_personas=99, rows_per_persona=1)
        res = pz.check_personas_canonical(fs, ws)
        check(res["pass"] is False,
              "1 row per persona is below the per-persona minimum and FAILS")

        # ── 5. NEGATIVE: an untagged index must FAIL ─────────────────────────
        print("\n[5] an untagged (never section-tagged) index must FAIL")
        ws = os.path.join(tmp, "untagged")
        build_corpus(ws, n_personas=99, index_personas=99, rows_per_persona=14,
                     tagged=False)
        res = pz.check_personas_canonical(fs, ws)
        check(res["index_section_tagged_rows"] == 0, "no rows are section-tagged")
        check(res["pass"] is False, "an untagged index FAILS")

        # ── 6. NEGATIVE: a missing index must FAIL ───────────────────────────
        print("\n[6] a missing index db must FAIL")
        ws = os.path.join(tmp, "noindex")
        build_corpus(ws, n_personas=99, index_personas=0, rows_per_persona=0,
                     seed_db=False)
        res = pz.check_personas_canonical(fs, ws)
        check(res["index_db_exists"] is False, "the index db is absent")
        check(res["pass"] is False, "a missing index FAILS")

        # ── 7. a pre-v2.1 table using `persona` instead of `persona_id` ──────
        print("\n[7] a pre-v2.1 table with a `persona` column is still readable")
        ws = os.path.join(tmp, "legacycol")
        build_corpus(ws, n_personas=45, index_personas=45, rows_per_persona=14,
                     persona_col="persona")
        res = pz.check_personas_canonical(fs, ws)
        check(res["index_persona_column"] == "persona",
              "the probe fell back to the legacy `persona` column")
        check(res["pass"] is True, "a pre-v2.1 index still PASSES")

        # ── 8. the floor is DERIVED, not pinned ──────────────────────────────
        print("\n[8] the floor scales with the corpus (cannot rot)")
        ws_small = os.path.join(tmp, "small")
        build_corpus(ws_small, n_personas=45, index_personas=45, rows_per_persona=14)
        r_small = pz.check_personas_canonical(fs, ws_small)
        ws_big = os.path.join(tmp, "big")
        build_corpus(ws_big, n_personas=150, index_personas=150, rows_per_persona=14)
        r_big = pz.check_personas_canonical(fs, ws_big)
        check(r_big["index_rows_floor"] > r_small["index_rows_floor"],
              f"a 150-persona library demands more rows ({r_big['index_rows_floor']}) "
              f"than a 45-persona one ({r_small['index_rows_floor']})")
        check(r_small["pass"] and r_big["pass"],
              "both library sizes pass against their own derived floor")

    finally:
        shutil.rmtree(SANDBOX, ignore_errors=True)

    print("\n" + "=" * 62)
    print(f"assertions: {PASSED} passed, {FAILED} failed")
    print("=" * 62)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
