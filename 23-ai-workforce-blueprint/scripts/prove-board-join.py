#!/usr/bin/env python3
"""
prove-board-join.py — AF-BOARD-JOIN-DRIFT.

THE C-SERIES JOIN. The one contract nothing in the repo asserted end-to-end:

    chosenDepartments  ==  provisioned department tree  ==  CC-DISPLAYED workspaces

Three layers, each already individually guarded, NONE of them joined:

  LAYER 1 — CHOSEN     the departments the client actually picked in the interview.
                       Persisted by build-workforce.write_chosen_departments_artifact()
                       (C7) into <company_dir>/departments.json AND build-state
                       canonicalReconciliation.chosenDepartments.slugs.
                       Guarded by: test-chosen-departments-artifact.sh (the artifact
                       is written and readable).

  LAYER 2 — PROVISIONED  the department directories materialized on disk under
                       <company_dir>/departments/<slug>/.
                       Guarded by: test-department-instantiation.sh (roster ==
                       _index.json == folders), test-phantom-dept-collision-gate.sh
                       (C5: the same canonical dept is never materialized twice).

  LAYER 3 — DISPLAYED  the `workspaces` rows in the Command Center's
                       mission-control.db — the Kanban columns / department rail
                       the CLIENT ACTUALLY SEES. Written by
                       32-command-center-setup/scripts/seed-workspaces.py, which
                       reads the SAME departments.json artifact.
                       Guarded by: guard-department-runtime-parity.py (every board
                       row has an OpenClaw runtime behind it).

Every one of those guards is INTRA-layer. Not one of them proves the layers AGREE.
So all three could be internally consistent and still describe three different
companies:

  * a department the client CHOSE that was never provisioned  -> a promised dept
    that does not exist;
  * a department PROVISIONED that the client never chose      -> a phantom tree
    burning tokens and SOP budget;
  * a department CHOSEN + PROVISIONED but never seeded onto the board -> the
    client PAID for it and CANNOT SEE IT (the "13 headless workspaces" class);
  * a department DISPLAYED that was never chosen              -> a ghost Kanban
    column with no tree and no runtime behind it (the C3/C6 class);
  * a department the eliminate path DECLINED that is still on the board.

This script is the JOIN. It is structural: it reads the three layers from their
REAL sources (the C7 artifact / build-state, the on-disk tree, the CC SQLite DB)
and diffs them. It never inspects, never samples, never trusts a status field.

--------------------------------------------------------------------------------
JOIN KEY
--------------------------------------------------------------------------------
The three layers do NOT use the same spelling for a department:

  chosen      canonical bare slug          "billing-finance"
  provisioned on-disk dir, variant-legal   "billing"   (CANONICAL_VARIANT_SLUGS)
  displayed   CC workspaces.slug           "billing-finance"  (seed-workspaces.py
              canonicalises "dept-billing-finance" -> "billing-finance")

So a naive set-diff produces FALSE drift. The join key is
department-floor.canonical_slug_for() — the SAME resolver the C5 collision gate
uses — falling back to shared-utils/canonical_slug.canonical_dept_slug() for
genuine custom departments (which map to themselves and can never collide with a
canonical). That makes this join variant-tolerant in exactly the way the floor
gate already is, and drift-intolerant in every other way.

--------------------------------------------------------------------------------
THE CEO / MASTER-ORCHESTRATOR COLUMN (explicit, not hidden)
--------------------------------------------------------------------------------
generate_departments_json() ALWAYS prepends a CEO entry
(slug "ceo", workspacePath "departments/master-orchestrator") so the Command
Center renders the CEO at the top of the rail. The CEO is the Master Orchestrator
— the main agent ABOVE the worker departments — not a worker department, and it
does not necessarily own a departments/<slug>/ subtree.

Therefore `ceo` (and its on-disk alias `master-orchestrator`) is EXEMPT from the
PROVISIONED comparisons and is reported under `orchestrator_exempt` so the
exemption is visible in the verdict rather than silently swallowed. It is NOT
exempt from the chosen<->displayed comparison: a CEO column that the client chose
but that is missing from the board is still drift.

--------------------------------------------------------------------------------
ARCHIVE-AWARENESS (the A8 / C6 eliminate path)
--------------------------------------------------------------------------------
"Displayed" means displayed. If the workspaces table carries an archive/lifecycle
column (archived_at / archived / is_archived / deleted_at / status), an ARCHIVED
row is NOT displayed and is excluded from the displayed set. That makes the join
correct today (no such column -> every row is displayed) AND correct after the CC
soft-archive lifecycle lands: archiving a department the client still has chosen
becomes CHOSEN_NOT_DISPLAYED drift, and archiving a DECLINED department is
correctly invisible to this gate.

--------------------------------------------------------------------------------
COMPANY SCOPING (multi-company boxes)
--------------------------------------------------------------------------------
One mission-control.db can hold the `workspaces` rows of MORE THAN ONE company
(company A's 10 rows and company B's 57 in the same table). Joining company A's
tree against ALL of those rows manufactures FALSE drift — every one of B's
departments would land in DISPLAYED_NOT_CHOSEN / DISPLAYED_NOT_PROVISIONED — and
because the QC gate turns any non-zero rc into "not materialized", a false drift
can block "done" indefinitely on a healthy box.

So the DISPLAY layer is always scoped to ONE company_id:
  * --company-slug <id>   explicit; always wins.
  * otherwise AUTO: when the board holds MORE THAN ONE distinct company_id we
    resolve this company's id from the same sources seed-workspaces.py used
    (company-config.json .slug -> the ZHC dir name -> slugified company name).
  * when the board holds zero or one distinct company_id there is nothing to
    disambiguate and NO filter is applied — identical to the unscoped behavior, so
    scoping cannot invent a new false-fail on a single-company box.
See company_slug_candidates() / resolve_company_slug() for the full rationale.

--------------------------------------------------------------------------------
EXIT CODES (fail-closed — this gate never passes on uncertainty)
--------------------------------------------------------------------------------
  0  JOIN OK          chosen == provisioned == displayed (every pairwise diff empty)
  1  GATE CANNOT RUN  bad usage / unreadable inputs / import failure
  2  AF-BOARD-JOIN-DRIFT   one or more of the six diff classes is non-empty
  3  CANNOT-VOUCH     the board exists but the join cannot be trusted:
                        - no chosen list for this company (pre-C7 build)   -> we
                          refuse to re-derive the floor and call it "chosen"
                        - the workspaces table exists but has ZERO rows    -> the
                          board was never seeded; that is not a pass
                        - the workspaces table has rows but NONE for this company
                        - the DB is present but unreadable
  4  NOT-APPLICABLE   there is no Command Center on this box (no mission-control.db,
                      or the DB has no `workspaces` table). The DISPLAY layer does
                      not exist yet, so there is nothing to join. Reported loudly.

USAGE
  python3 prove-board-join.py                            # resolve everything live
  python3 prove-board-join.py --company-dir <dir>        # explicit company dir
  python3 prove-board-join.py --company-dir <dir> --db <mission-control.db>
  python3 prove-board-join.py ... --company-slug acme    # disambiguate multi-tenant
  python3 prove-board-join.py ... --json                 # machine-readable verdict

Read-only. Never writes. Idempotent. Depends only on the Python stdlib.
"""

import argparse
import importlib.util
import json
import os
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent
SHARED_UTILS = REPO_ROOT / "shared-utils"

RC_OK = 0
RC_CANNOT_RUN = 1
RC_DRIFT = 2
RC_CANNOT_VOUCH = 3
RC_NOT_APPLICABLE = 4

# The CEO column is the Master Orchestrator surfaced as a board column, not a
# worker department. These are the slugs it can appear under (build-workforce
# emits slug "ceo" with workspacePath "departments/master-orchestrator").
ORCHESTRATOR_KEYS = {"ceo", "master-orchestrator"}
ORCHESTRATOR_CANONICAL = "ceo"

# Columns that, if present on `workspaces`, mean a row can be hidden from the
# board. Checked in order; the first one present wins.
#   (column name, predicate -> True when the row IS displayed)
ARCHIVE_COLUMNS = [
    ("archived_at", lambda v: v is None or str(v).strip() == ""),
    ("deleted_at", lambda v: v is None or str(v).strip() == ""),
    ("archived", lambda v: not _truthy(v)),
    ("is_archived", lambda v: not _truthy(v)),
    ("status", lambda v: str(v or "").strip().lower() not in ("archived", "deleted", "hidden")),
]

CHOSEN_ARTIFACT = "departments.json"


def _truthy(v):
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "y", "t")


# ── Load department-floor.py (hyphenated filename -> importlib) ────────────────
def _load_floor():
    path = SCRIPT_DIR / "department-floor.py"
    if not path.is_file():
        raise RuntimeError(f"department-floor.py not found at {path}")
    spec = importlib.util.spec_from_file_location("department_floor_join", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_canonical_slug():
    """shared-utils/canonical_slug.canonical_dept_slug — the SAME normaliser
    seed-workspaces.py uses to write workspaces.slug. Using it here means the
    display side of the join can never normalise differently from the seeder."""
    sys.path.insert(0, str(SHARED_UTILS))
    try:
        from canonical_slug import canonical_dept_slug  # type: ignore
        return canonical_dept_slug
    except ImportError:
        import re as _re

        def _fallback(raw):
            if not raw or not isinstance(raw, str):
                return ""
            s = raw.strip().lower()
            if s.startswith("dept-"):
                s = s[5:]
            if s.endswith("-dept"):
                s = s[:-5]
            s = s.replace(" ", "-").replace("_", "-")
            s = _re.sub(r"-{2,}", "-", s)
            return s.strip("-")

        return _fallback


# ── LAYER 1: CHOSEN ───────────────────────────────────────────────────────────
def read_chosen_for_company(company_dir, build_state=None):
    """
    The client's chosen department set, SCOPED TO THIS COMPANY DIR.

    Deliberately NOT build-workforce.read_chosen_departments()'s global default:
    that reader falls back to the box-wide build-state, which would make this gate
    compare a sandbox/company-A tree against company-B's chosen list. A gate that
    can be pointed at the wrong company is not a gate.

    Resolution (authoritative first):
      1. <company_dir>/departments.json                      -> ("artifact")
      2. build-state canonicalReconciliation.chosenDepartments, but ONLY when it is
         PROVABLY scoped to THIS company_dir — either its recorded artifactPath
         lives inside it, or its recorded companyDir IS it            -> ("build-state")
      3. ([], "none")  — NEVER re-derived from the floor.

    WHY companyDir MATTERS (a failed artifact write must not buy a pass):
    build-workforce.write_chosen_departments_artifact() is deliberately fail-soft —
    an OSError writing <company_dir>/departments.json is a WARNING, never a raise,
    so a build continues. On such a box the artifact is absent and artifactPath is
    recorded as None. If the ONLY scope key were artifactPath, that record would be
    unusable, this reader would return ([], "none"), and the QC gate would SKIP the
    join as though the box were a pre-C7 build — a box whose durable write FAILED
    would be indistinguishable from a box that never had the feature, and would get
    a silent PASS. Scoping on companyDir (stamped by the same writer) keeps the
    chosen list readable when the artifact write failed, so the join still RUNS and
    the drift is still caught. A write failure cannot buy a pass.
    """
    cdir = Path(company_dir)
    artifact = cdir / CHOSEN_ARTIFACT
    try:
        data = json.loads(artifact.read_text())
    except (OSError, json.JSONDecodeError):
        data = None
    if isinstance(data, list):
        out, seen = [], set()
        for entry in data:
            s = None
            if isinstance(entry, dict):
                s = entry.get("slug") or entry.get("id")
            elif isinstance(entry, str):
                s = entry
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        if out:
            return out, "artifact"

    if isinstance(build_state, dict):
        recon = build_state.get("canonicalReconciliation") or {}
        chosen = recon.get("chosenDepartments") if isinstance(recon, dict) else None
        if isinstance(chosen, dict):
            slugs = chosen.get("slugs")
            in_scope = False
            try:
                resolved_cdir = cdir.resolve()
            except OSError:
                resolved_cdir = None
            # (a) the artifact this record points at lives in THIS company dir
            ap = chosen.get("artifactPath")
            if ap and resolved_cdir is not None:
                try:
                    in_scope = Path(ap).resolve().parent == resolved_cdir
                except OSError:
                    in_scope = False
            # (b) the record names THIS company dir directly — survives a failed
            #     (fail-soft) artifact write, where artifactPath is None.
            cd = chosen.get("companyDir")
            if not in_scope and cd and resolved_cdir is not None:
                try:
                    in_scope = Path(cd).resolve() == resolved_cdir
                except OSError:
                    in_scope = False
            if in_scope and isinstance(slugs, list) and slugs:
                return [s for s in slugs if s], "build-state"
    return [], "none"


# ── LAYER 2: PROVISIONED ──────────────────────────────────────────────────────
def read_provisioned(departments_dir, df):
    """Live department dirs on disk (raw names). '.bak' trees and hidden/underscore
    dirs are excluded — they are not departments (that is C5's contract, and
    _raw_department_dirs is the single source of truth for the split)."""
    live, _backups = df._raw_department_dirs(Path(departments_dir))
    return live


# ── LAYER 3: DISPLAYED ────────────────────────────────────────────────────────
def resolve_db(explicit=None):
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    sys.path.insert(0, str(SHARED_UTILS))
    try:
        from resolve_db import find_dashboard_db  # type: ignore
        p = find_dashboard_db()
        return p if p and Path(p).is_file() else None
    except ImportError:
        for cand in (
            Path(os.environ["DASHBOARD_DB_PATH"]) if "DASHBOARD_DB_PATH" in os.environ else None,
            Path(os.environ["DATABASE_PATH"]) if "DATABASE_PATH" in os.environ else None,
            Path.home() / "projects/command-center/mission-control.db",
            Path("/data/projects/command-center/mission-control.db"),
        ):
            if cand and cand.is_file():
                return cand
    return None


def read_displayed(db_path, company_slug=None):
    """
    Read the DISPLAYED workspaces from the Command Center DB.

    Returns (rows, archived_rows, company_ids, archive_column) where
      rows          = [(slug, name, company_id)] that ARE on the board
      archived_rows = [(slug, name, company_id)] hidden by the lifecycle column
      company_ids   = every distinct company_id present in the table
      archive_column = the lifecycle column detected, or None

    Raises LookupError when the `workspaces` table does not exist (NOT-APPLICABLE).
    """
    # Read-only, and URL-quoted: a real workspace path can contain spaces
    # (~/Downloads/openclaw-master-files/...), which an unquoted file: URI would
    # silently truncate.
    uri = "file:" + urllib.parse.quote(str(Path(db_path).resolve())) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        cur = conn.cursor()
        tbl = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='workspaces'"
        ).fetchone()
        if not tbl:
            raise LookupError("no `workspaces` table")

        cols = [r[1] for r in cur.execute("PRAGMA table_info(workspaces)").fetchall()]
        if "slug" not in cols:
            raise LookupError("`workspaces` table has no `slug` column")

        archive_col = None
        archive_pred = None
        for name, pred in ARCHIVE_COLUMNS:
            if name in cols:
                archive_col, archive_pred = name, pred
                break

        sel = ["slug",
               "name" if "name" in cols else "slug",
               "company_id" if "company_id" in cols else "''"]
        if archive_col:
            sel.append(archive_col)
        rows = cur.execute(f"SELECT {', '.join(sel)} FROM workspaces").fetchall()
    finally:
        conn.close()

    displayed, archived, company_ids = [], [], set()
    for r in rows:
        slug, name, cid = r[0], r[1], r[2]
        company_ids.add(cid)
        if company_slug is not None and cid != company_slug:
            continue
        if archive_col and not archive_pred(r[3]):
            archived.append((slug, name, cid))
        else:
            displayed.append((slug, name, cid))
    return displayed, archived, company_ids, archive_col


# ── COMPANY SCOPING — never join THIS company's tree against ANOTHER company's board ──
#
# THE BUG THIS KILLS: read_displayed() with company_slug=None returns EVERY row in
# the `workspaces` table. On a multi-company box — one mission-control.db whose
# table holds company A's 10 rows and company B's 57 — joining A's chosen list and
# A's tree against ALL 67 rows manufactures FALSE drift: every one of B's
# departments lands in DISPLAYED_NOT_CHOSEN and DISPLAYED_NOT_PROVISIONED. That
# verdict does not stay local: qc-assert-workspace-departments-built.sh turns it
# into rc=6, and lib-onboarding-state.sh maps ANY non-zero rc to "not
# materialized", which feeds BOTH oc_overall_goal_check AND the watchdog kill
# condition. A false drift can therefore block "done" indefinitely on a perfectly
# healthy box. A gate that can be pointed at the wrong company is not a gate.
#
# THE JOIN KEY ON THE DISPLAY SIDE is workspaces.company_id, which
# 32-command-center-setup/scripts/seed-workspaces.py writes from
# company_info["slug"] (`company_slug = company_info["slug"]`). That slug resolves,
# in the seeder's own priority order:
#     1. <company_dir>/company-config.json  ->  .slug   (whose default is the ZHC
#                                                        company DIR NAME)
#     2. else a slug derived from the company NAME
# so we must offer the SAME candidate spellings rather than assume the dir name.
#
# FAIL-SAFE ASYMMETRY (deliberate, and the reason this cannot regress the fleet):
# when the board carries ZERO or ONE distinct company_id there is nothing to
# disambiguate, so we apply NO filter — byte-for-byte the pre-existing behavior.
# That keeps this fix from inventing a NEW false-fail class on the single-company
# boxes that make up the fleet (e.g. a box whose company_id was derived from the
# company NAME and does not equal its dir name: filtering on the dir name there
# would find zero rows and CANNOT-VOUCH a healthy board). We narrow the read ONLY
# when the table actually holds more than one company — which is exactly and only
# when the unscoped read is wrong.
def company_slug_candidates(company_dir):
    """Every spelling seed-workspaces.py could have written as workspaces.company_id
    for this company dir, most-authoritative first. Pure — touches no database."""
    cdir = Path(company_dir)
    out = []

    def _add(v):
        if isinstance(v, str) and v.strip() and v.strip() not in out:
            out.append(v.strip())

    cfg = {}
    try:
        cfg = json.loads((cdir / "company-config.json").read_text())
    except (OSError, json.JSONDecodeError):
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}

    _add(cfg.get("slug"))            # 1. the seeder's authoritative source
    _add(cdir.name)                  # 2. the seeder's own default for .slug
    if cfg.get("name"):              # 3. the seeder's last-resort name derivation
        _add(re.sub(r"[^a-z0-9]+", "-", str(cfg["name"]).lower()).strip("-"))
    return out


def resolve_company_slug(company_dir, company_ids):
    """The workspaces.company_id this company's rows live under, or None when no
    filter should be applied. `company_ids` = every distinct company_id in the
    table. See the block comment above for the fail-safe asymmetry."""
    ids = {c for c in (company_ids or ()) if c is not None and str(c) != ""}
    if len(ids) <= 1:
        return None          # single-company board: nothing to disambiguate.
    cands = company_slug_candidates(company_dir)
    for cand in cands:
        if cand in ids:
            return cand
    # A multi-company board on which NOT ONE of this company's spellings appears:
    # this company has no board rows at all. Return the best candidate so the
    # caller's "rows for X but NONE for Y" CANNOT-VOUCH branch fires. We never fall
    # back to "join against everybody" — that is the bug.
    return cands[0] if cands else None


def resolve_company_slug_from_db(company_dir, db_path):
    """Same resolution for a caller that holds a DB path but has not read rows yet
    (the QC gate). Returns None on an absent/unreadable/board-less DB — the
    caller's own NOT-APPLICABLE / CANNOT-VOUCH paths own those states."""
    if not db_path:
        return None
    try:
        _disp, _arch, company_ids, _col = read_displayed(db_path)
    except (LookupError, sqlite3.Error, OSError):
        return None
    return resolve_company_slug(company_dir, company_ids)


# ── THE JOIN ──────────────────────────────────────────────────────────────────
def make_keyer(df, canonical_dept_slug):
    nm = df.load_naming_map()

    def key(raw):
        """Resolve ANY department spelling (chosen slug / on-disk dir / CC slug)
        to the ONE canonical join key. Canonical + variant slugs collapse onto the
        canonical id; genuine customs map to their own bare slug."""
        if not raw:
            return ""
        bare = canonical_dept_slug(str(raw)) or str(raw).strip().lower()
        if bare in ORCHESTRATOR_KEYS:
            return ORCHESTRATOR_CANONICAL
        cid = df.canonical_slug_for(bare, nm)
        return cid or bare

    return key


def join(chosen, provisioned, displayed, key):
    """Return the verdict dict. Every set is keyed; every diff is reported with the
    RAW spellings that produced it so an operator can act on it."""
    def index(items):
        out = {}
        for raw in items:
            k = key(raw)
            if not k:
                continue
            out.setdefault(k, []).append(raw)
        return out

    chosen_idx = index(chosen)
    prov_idx = index(provisioned)
    disp_idx = index(displayed)

    chosen_keys = set(chosen_idx)
    prov_keys = set(prov_idx)
    disp_keys = set(disp_idx)

    # The CEO/master-orchestrator column is not a worker department: it is exempt
    # from the TREE comparisons only. It stays in the board comparison.
    orchestrator_exempt = sorted(
        (chosen_keys | prov_keys | disp_keys) & {ORCHESTRATOR_CANONICAL}
    )
    chosen_tree = chosen_keys - {ORCHESTRATOR_CANONICAL}
    prov_tree = prov_keys - {ORCHESTRATOR_CANONICAL}

    def fmt(keys, *idxs):
        out = []
        for k in sorted(keys):
            raws = []
            for idx in idxs:
                raws.extend(idx.get(k, []))
            out.append({"department": k, "as": sorted(set(raws))} if raws else {"department": k, "as": []})
        return out

    diffs = {
        "CHOSEN_NOT_PROVISIONED": fmt(chosen_tree - prov_tree, chosen_idx),
        "PROVISIONED_NOT_CHOSEN": fmt(prov_tree - chosen_tree, prov_idx),
        "CHOSEN_NOT_DISPLAYED": fmt(chosen_keys - disp_keys, chosen_idx),
        "DISPLAYED_NOT_CHOSEN": fmt(disp_keys - chosen_keys, disp_idx),
        "PROVISIONED_NOT_DISPLAYED": fmt(prov_tree - disp_keys, prov_idx),
        "DISPLAYED_NOT_PROVISIONED": fmt(
            (disp_keys - prov_keys) - {ORCHESTRATOR_CANONICAL}, disp_idx
        ),
    }
    drift = any(v for v in diffs.values())
    return {
        "rc": RC_DRIFT if drift else RC_OK,
        "status": "AF-BOARD-JOIN-DRIFT" if drift else "JOIN-OK",
        "chosen": sorted(chosen_keys),
        "provisioned": sorted(prov_keys),
        "displayed": sorted(disp_keys),
        "counts": {
            "chosen": len(chosen_keys),
            "provisioned": len(prov_keys),
            "displayed": len(disp_keys),
        },
        "orchestrator_exempt": orchestrator_exempt,
        "diffs": diffs,
        "drift_classes": sorted(k for k, v in diffs.items() if v),
    }


REMEDIATION = {
    "CHOSEN_NOT_PROVISIONED":
        "the client chose this department and it was NEVER BUILT. Re-run the "
        "workforce build (build-workforce.py / post-build-role-workspaces.py).",
    "PROVISIONED_NOT_CHOSEN":
        "a department tree exists that the client never chose (phantom tree / a "
        "declined dept that was never removed). Reconcile with "
        "reconcile-legacy-tree.py, or record the decision if it IS wanted.",
    "CHOSEN_NOT_DISPLAYED":
        "the client PAID for this department and CANNOT SEE IT — it has no live "
        "Command Center column (never seeded, or archived while still chosen). "
        "Re-run 32-command-center-setup/scripts/seed-workspaces.py (and un-archive).",
    "DISPLAYED_NOT_CHOSEN":
        "a GHOST board column the client never chose. Remove/archive the "
        "workspaces row, or record the choice if it IS wanted.",
    "PROVISIONED_NOT_DISPLAYED":
        "a headless workspace: a real department tree with no board column behind "
        "it. Re-run seed-workspaces.py.",
    "DISPLAYED_NOT_PROVISIONED":
        "a board column with no department tree behind it — tasks routed there can "
        "never resolve a runtime. Build the tree or remove the column.",
}


def render(v, company_dir, departments_dir, db_path, chosen_source, archive_col, archived):
    print("=" * 78)
    print("AF-BOARD-JOIN-DRIFT gate — chosen == provisioned == displayed")
    print(f"company dir      : {company_dir}")
    print(f"departments dir  : {departments_dir}")
    print(f"command-center db: {db_path}")
    print(f"chosen source    : {chosen_source}")
    print(f"company scope    : {v.get('company_slug') or '(unscoped)'} "
          f"[{v.get('company_slug_source', 'n/a')}]  "
          f"board company_ids: {', '.join(v.get('board_company_ids') or []) or '(none)'}")
    print(f"archive column   : {archive_col or '(none — every workspaces row is displayed)'}")
    print("-" * 78)
    print(f"{'DEPARTMENT':<30} {'CHOSEN':>7} {'PROVIS':>7} {'DISPLAY':>8}")
    print("-" * 78)
    every = sorted(set(v["chosen"]) | set(v["provisioned"]) | set(v["displayed"]))
    for k in every:
        c = "Y" if k in v["chosen"] else "-"
        p = "Y" if k in v["provisioned"] else ("n/a" if k in v["orchestrator_exempt"] else "-")
        d = "Y" if k in v["displayed"] else "-"
        print(f"{k:<30} {c:>7} {p:>7} {d:>8}")
    print("-" * 78)
    print(f"CHOSEN={v['counts']['chosen']}  PROVISIONED={v['counts']['provisioned']}  "
          f"DISPLAYED={v['counts']['displayed']}")
    if v["orchestrator_exempt"]:
        print(f"orchestrator column (exempt from the TREE comparison only): "
              f"{', '.join(v['orchestrator_exempt'])}")
    if archived:
        print(f"archived (NOT displayed): {', '.join(sorted(a[0] for a in archived))}")

    if v["rc"] == RC_OK:
        print("JOIN OK — every chosen department is provisioned AND on the client's board; "
              "nothing is provisioned or displayed that was not chosen.")
        return

    print("", file=sys.stderr)
    print("INVARIANT VIOLATED — AF-BOARD-JOIN-DRIFT: the three layers disagree.", file=sys.stderr)
    for cls in v["drift_classes"]:
        entries = v["diffs"][cls]
        names = ", ".join(
            e["department"] + (f" (as {'/'.join(e['as'])})" if e["as"] and e["as"] != [e["department"]] else "")
            for e in entries
        )
        print(f"  {cls}: {names}", file=sys.stderr)
        print(f"    -> {REMEDIATION[cls]}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Prove chosen == provisioned == displayed.")
    ap.add_argument("--company-dir", help="ZHC company dir (parent of departments/)")
    ap.add_argument("--departments-dir", help="explicit departments dir (implies --company-dir=<its parent>)")
    ap.add_argument("--db", help="explicit mission-control.db path")
    ap.add_argument("--company-slug", help="workspaces.company_id to join on (multi-tenant DBs)")
    ap.add_argument("--json", action="store_true", help="emit the verdict as JSON on stdout")
    args = ap.parse_args(argv)

    try:
        df = _load_floor()
    except Exception as e:  # noqa: BLE001
        print(f"AF-BOARD-JOIN-DRIFT: GATE CANNOT RUN — {e}", file=sys.stderr)
        return RC_CANNOT_RUN
    canonical_dept_slug = _load_canonical_slug()

    # ── resolve the company / departments dirs ──
    if args.departments_dir:
        departments_dir = Path(args.departments_dir)
        company_dir = Path(args.company_dir) if args.company_dir else departments_dir.parent
    elif args.company_dir:
        company_dir = Path(args.company_dir)
        departments_dir = company_dir / "departments"
    else:
        dd = df.resolve_departments_dir()
        if dd is None:
            print("AF-BOARD-JOIN-DRIFT: GATE CANNOT RUN — no departments dir resolved "
                  "(pass --company-dir).", file=sys.stderr)
            return RC_CANNOT_RUN
        departments_dir = Path(dd)
        company_dir = departments_dir.parent

    if not departments_dir.is_dir():
        print(f"AF-BOARD-JOIN-DRIFT: GATE CANNOT RUN — departments dir does not exist: "
              f"{departments_dir}", file=sys.stderr)
        return RC_CANNOT_RUN

    # ── LAYER 3 first: is there a Command Center on this box at all? ──
    db_path = resolve_db(args.db)
    if db_path is None:
        print("AF-BOARD-JOIN-DRIFT: NOT APPLICABLE — no Command Center database "
              "(mission-control.db) on this box, so no department is DISPLAYED yet. "
              "The join cannot be run until the Command Center is installed.",
              file=sys.stderr)
        if args.json:
            print(json.dumps({"rc": RC_NOT_APPLICABLE, "status": "NOT-APPLICABLE",
                              "reason": "no mission-control.db"}, indent=2))
        return RC_NOT_APPLICABLE

    # Read the board UNFILTERED first: `company_ids` (every distinct company_id in
    # the table) is what tells us whether this is a multi-company board at all, and
    # therefore whether a scope filter is required. We filter immediately below.
    try:
        displayed_rows, archived_rows, company_ids, archive_col = read_displayed(db_path)
    except LookupError as e:
        print(f"AF-BOARD-JOIN-DRIFT: NOT APPLICABLE — {e} in {db_path}. The Command "
              f"Center board has not been created yet.", file=sys.stderr)
        if args.json:
            print(json.dumps({"rc": RC_NOT_APPLICABLE, "status": "NOT-APPLICABLE",
                              "reason": str(e)}, indent=2))
        return RC_NOT_APPLICABLE
    except sqlite3.Error as e:
        print(f"AF-BOARD-JOIN-DRIFT: CANNOT VOUCH — mission-control.db is present but "
              f"unreadable ({e}). Refusing to pass on an unreadable board.", file=sys.stderr)
        return RC_CANNOT_VOUCH

    # ── COMPANY SCOPING: an explicit --company-slug always wins; otherwise scope
    #    automatically (multi-company board) or not at all (single-company board).
    #    Doing this HERE rather than at one call site means EVERY consumer — the QC
    #    gate, the CI suite, an operator running this bare — is scoped correctly.
    if args.company_slug:
        company_slug, slug_source = args.company_slug, "explicit (--company-slug)"
    else:
        company_slug = resolve_company_slug(company_dir, company_ids)
        slug_source = ("auto-resolved (multi-company board)" if company_slug
                       else "none (single-company board — no filter needed)")
    if company_slug is not None:
        displayed_rows = [r for r in displayed_rows if r[2] == company_slug]
        archived_rows = [r for r in archived_rows if r[2] == company_slug]

    # ── LAYER 1: the chosen list, scoped to THIS company ──
    build_state = df.load_build_state()
    chosen, chosen_source = read_chosen_for_company(company_dir, build_state)
    if not chosen:
        print(f"AF-BOARD-JOIN-DRIFT: CANNOT VOUCH — no durable chosen-departments list "
              f"for {company_dir} (neither {company_dir}/departments.json nor a "
              f"build-state canonicalReconciliation.chosenDepartments record scoped to "
              f"it). The C7 artifact is the ONLY authoritative statement of what the "
              f"client chose; this gate will NOT re-derive it from the floor and call "
              f"that 'chosen'.", file=sys.stderr)
        return RC_CANNOT_VOUCH

    # ── the board must actually be seeded for THIS company ──
    if not displayed_rows and not archived_rows:
        if not company_ids:
            # The board exists as a schema but carries NOT ONE row while the client
            # chose N departments. That is the "they paid for it and cannot see any
            # of it" state — the loudest possible version of the bug this gate is
            # for. It is emphatically NOT a pass.
            print(f"AF-BOARD-JOIN-DRIFT: CANNOT VOUCH — the Command Center workspaces "
                  f"table exists but is EMPTY while the client chose {len(chosen)} "
                  f"departments ({', '.join(chosen)}). The board was never seeded — run "
                  f"32-command-center-setup/scripts/seed-workspaces.py. An empty board is "
                  f"not a pass.", file=sys.stderr)
        else:
            print(f"AF-BOARD-JOIN-DRIFT: CANNOT VOUCH — the workspaces table has rows for "
                  f"company_id(s) {sorted(str(c) for c in company_ids)} but NONE for "
                  f"'{company_slug}' ({slug_source}). Every department this company "
                  f"chose is therefore invisible on its board. Refusing to pass a board "
                  f"that does not describe this company.", file=sys.stderr)
        return RC_CANNOT_VOUCH

    # ── LAYER 2 ──
    provisioned = read_provisioned(departments_dir, df)

    key = make_keyer(df, canonical_dept_slug)
    verdict = join(chosen, provisioned, [r[0] for r in displayed_rows], key)
    verdict["company_dir"] = str(company_dir)
    verdict["departments_dir"] = str(departments_dir)
    verdict["db"] = str(db_path)
    verdict["chosen_source"] = chosen_source
    verdict["company_slug"] = company_slug
    verdict["company_slug_source"] = slug_source
    verdict["board_company_ids"] = sorted(str(c) for c in company_ids)
    verdict["archive_column"] = archive_col
    verdict["archived_not_displayed"] = sorted(r[0] for r in archived_rows)

    render(verdict, company_dir, departments_dir, db_path, chosen_source, archive_col, archived_rows)
    if args.json:
        print(json.dumps(verdict, indent=2))
    return verdict["rc"]


if __name__ == "__main__":
    sys.exit(main())
