#!/usr/bin/env python3
"""
refresh-build-state-from-index.py — Skill 23 AI Workforce Blueprint (§1.3)

PURPOSE
    Re-syncs .workforce-build-state.json from the authoritative _index.json
    + on-disk dept directories. Called by converge after every add-*.sh run.

    This is the single derivation step: _index.json (authoritative) → build-state
    (derived). The org-chart, infographic, and Notion closeout are downstream of
    build-state and are rendered by converge after this script runs.

WHAT IT DOES
    1. Loads _index.json (the CANONICAL role catalog — used only to look up
       the planned role count for a department that IS canonical; it is never
       the source of WHICH departments this client has).
    2. Loads existing .workforce-build-state.json (FAIL LOUD if absent — box
       must have been built first)
    3. For EACH DEPARTMENT ALREADY IN THIS CLIENT'S build-state (their own
       roster, never the canonical index): refreshes rolesPlanned (from the
       index when the dept is canonical; preserved untouched when it is a
       client custom dept the index has never heard of) and rolesDone (disk
       truth). NEVER adds a department the client does not already have —
       that is the job of the build/reconciliation pipeline (build-workforce.py
       reconcile_canonical_floor()), which records an auditable, provenanced
       decision per department. A blind sync from the canonical index used to
       add every canonical department to a custom-company client's roster
       while their own real departments (living outside the guessed tree)
       stayed unmeasured forever — see DONE-IS-GATED.md and the resolver
       below.
    4. Per-dept roleLibraryFilled/sopLibraryFilled set via backfill-build-state heuristics
    5. Recomputes top-level totals from the CLIENT's own department set (not
       the canonical index's)
    6. Atomically writes the updated state
    7. Exits 0, prints "changed=<0|1>" on stdout

DEPARTMENTS TREE RESOLUTION
    Which on-disk directory holds this client's departments is resolved, not
    guessed: config-derived (openclaw.json agents.list dept-<slug>.workspace —
    ground truth for what the agents actually run from) wins outright when it
    resolves; otherwise every fixed candidate (workspaceRoot, the legacy
    workspace tree, zero-human-company/<companySlug>/departments, any sibling
    zero-human-company/*/departments) is SCORED by how many of the client's
    OWN department slugs actually resolve inside it (suffix-tolerant: a slug
    stored on disk as "<slug>-dept" still matches). If two or more distinct
    directories tie for the best nonzero score, resolution is AMBIGUOUS and
    the script exits FATAL rather than silently measuring the wrong tree — a
    confident wrong measurement here corrupts the honesty-floor write (DEFECT
    #5, below). The resolved tree + method are recorded in build-state
    (departmentsTreeResolution) so a caller can tell what was measured.

USAGE
    python3 refresh-build-state-from-index.py
    python3 refresh-build-state-from-index.py --dry-run
    python3 refresh-build-state-from-index.py --verbose
    python3 refresh-build-state-from-index.py --strict   (default: gate status:done on library+wiring)
    python3 refresh-build-state-from-index.py --counts-only  (update counts only, never flip status)

EXIT CODES
    0 — success
    1 — FATAL (no build-state found, malformed files, departments tree
        resolution ambiguous, etc.)
"""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ─── Path resolvers ──────────────────────────────────────────────────────────

def find_build_state_path() -> Path:
    """Resolve the build-state JSON path (env override first, then VPS, then Mac)."""
    # Test/override hook: lets the acceptance suite point at a sandbox state file.
    env_override = os.environ.get("WORKFORCE_BUILD_STATE_PATH")
    if env_override:
        return Path(env_override)
    candidates = [
        Path("/data/.openclaw/workspace/.workforce-build-state.json"),
        Path.home() / ".openclaw/workspace/.workforce-build-state.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[1] if Path.home().is_dir() else candidates[0]


def find_index_json_path() -> Optional[Path]:
    """Locate the role-library _index.json (env override first, then VPS, then Mac)."""
    # Test/override hook: lets the acceptance suite point at a sandbox index.
    env_override = os.environ.get("WORKFORCE_INDEX_PATH")
    if env_override and Path(env_override).is_file():
        return Path(env_override)
    candidates = [
        Path("/data/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/_index.json"),
        Path.home() / ".openclaw/skills/23-ai-workforce-blueprint/templates/role-library/_index.json",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def find_openclaw_config_path() -> Optional[Path]:
    """Resolve openclaw.json (env override first, then VPS, then Mac)."""
    # Test/override hook: lets the acceptance suite point at a sandbox config.
    env_override = os.environ.get("WORKFORCE_OPENCLAW_CONFIG_PATH")
    if env_override and Path(env_override).is_file():
        return Path(env_override)
    for p in (Path("/data/.openclaw/openclaw.json"), Path.home() / ".openclaw/openclaw.json"):
        if p.is_file():
            return p
    return None


def _oc_root() -> Path:
    """The OpenClaw root this box uses: /data/.openclaw if present, else
    $HOME/.openclaw. Mirrors verify-wiring.sh's OC_ROOT resolution so the two
    gates that read/write the same client build-state agree on platform."""
    data_root = Path("/data/.openclaw")
    if data_root.is_dir():
        return data_root
    return Path.home() / ".openclaw"


_DEPT_PREFIX_RE = re.compile(r"^dept[-_]")
_DEPT_SUFFIX_RE = re.compile(r"[-_]dept$")
_DEPT_SEP_RE = re.compile(r"-+")


def _norm_dept_key(s: str) -> str:
    """Case/suffix/separator-tolerant normalization, mirroring verify-wiring.sh's
    _norm_dept_key(): 'Trading-Operations-Dept' and 'trading_operations' both
    normalize to 'trading-operations'."""
    s = (s or "").lower()
    s = _DEPT_PREFIX_RE.sub("", s)
    s = _DEPT_SUFFIX_RE.sub("", s)
    s = s.replace("_", "-")
    s = _DEPT_SEP_RE.sub("-", s).strip("-")
    return s


def resolve_dept_dir_in_tree(root: Optional[Path], slug: str) -> Optional[Path]:
    """
    DEFECT D fix: resolve a department's real on-disk directory under `root`,
    tolerant of the `-dept` suffix convention and case/separator drift. Mirrors
    create_role_workspaces.resolve_dept_dir() / verify-wiring.sh's
    resolve_one_dept() precedence so every reader of this tree agrees about
    which directory a slug means:
      1. the bare id            <root>/<slug>
      2. the "-dept" suffixed   <root>/<slug>-dept   (a real layout on live boxes)
      3. a normalized scan      case + separator drift
    Without step 2, a slug like "trading-operations" silently measured ZERO
    roles on a box that stores it as "trading-operations-dept/".
    """
    if not root or not root.is_dir():
        return None
    bare = root / slug
    if bare.is_dir():
        return bare
    suffixed = root / f"{slug}-dept"
    if suffixed.is_dir():
        return suffixed
    target = _norm_dept_key(slug)
    if not target:
        return None
    try:
        children = sorted(root.iterdir())
    except OSError:
        return None
    for child in children:
        if child.is_dir() and _norm_dept_key(child.name) == target:
            return child
    return None


def _config_derived_departments_dir(cfg_path: Optional[Path], client_dept_slugs) -> Optional[Path]:
    """
    Resolve the departments tree from openclaw.json agents.list — the path the
    gateway dispatcher and the department agents ACTUALLY run from (ground
    truth, never a guess). For every client department slug with a registered
    `dept-<slug>` agent whose `.workspace` exists on disk, take the workspace's
    PARENT directory. If every resolvable dept agrees on one parent, that
    parent IS the departments tree. Returns None when the config is absent, no
    dept agent resolves, or resolved workspaces disagree on a parent (never
    guesses across a disagreement — falls through to the scored fixed-candidate
    tier instead).
    """
    if not cfg_path or not cfg_path.is_file():
        return None
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    agents = ((cfg.get("agents") or {}).get("list") or [])
    by_id = {a.get("id"): a for a in agents if isinstance(a, dict)}
    parents = set()
    for slug in client_dept_slugs:
        agent = by_id.get(f"dept-{slug}")
        if not agent:
            continue
        ws = agent.get("workspace")
        if not ws:
            continue
        wp = Path(ws)
        if wp.is_dir():
            parents.add(wp.parent)
    if len(parents) == 1:
        return next(iter(parents))
    return None


class AmbiguousDepartmentsTreeError(RuntimeError):
    """Raised when the departments tree cannot be resolved without guessing --
    two or more candidate trees score equally on the client's own department
    set. Refusing to pick one is the safe behavior: a confident wrong
    measurement here corrupts the honesty-floor write (DEFECT #5)."""


class DepartmentsTreeResolution:
    """Result of resolve_departments_tree(): which tree was used (or None if
    nothing is built yet), how it was resolved, and the full scored candidate
    list for diagnostics / state recording."""

    def __init__(self, path, resolved_via, score, checked, candidates):
        self.path = path
        self.resolved_via = resolved_via  # "config" | "scored" | "none"
        self.score = score
        self.checked = checked
        self.candidates = candidates  # list[(str(path), score)]

    def to_state_dict(self) -> dict:
        return {
            "path": str(self.path) if self.path else None,
            "resolvedVia": self.resolved_via,
            "score": self.score,
            "checked": self.checked,
        }


def _departments_tree_candidates(state: dict) -> list:
    """Ordered, deduplicated list of existing directories that MIGHT be the
    departments tree (before scoring). Mirrors verify-wiring.sh
    DEPT_TREE_CANDIDATES so the two gates that read/write the same client
    build-state agree about where to look:
      1. state.workspaceRoot/departments          (explicit, when present)
      2. OC_ROOT/workspace/departments             (the standard tree)
      3. zero-human-company/<companySlug>/departments  for the company slug
         recorded in build-state
      4. any zero-human-company/*/departments found on disk
      5. OC_ROOT/workspace/agents/main/departments (legacy; this script's
         pre-fix sole candidate)
    """
    seen = set()
    out = []

    def add(p):
        if not p:
            return
        p = Path(p)
        try:
            if p in seen or not p.is_dir():
                return
        except OSError:
            return
        seen.add(p)
        out.append(p)

    ws_root = state.get("workspaceRoot")
    if ws_root:
        add(Path(ws_root) / "departments")

    oc_root = _oc_root()
    add(oc_root / "workspace" / "departments")

    company_slug = state.get("companySlug") or state.get("clientSlug")
    for zhc_root in (Path.home() / "clawd" / "zero-human-company",
                      Path("/data/clawd/zero-human-company")):
        if not zhc_root.is_dir():
            continue
        if company_slug:
            add(zhc_root / str(company_slug) / "departments")
        try:
            for child in sorted(zhc_root.iterdir()):
                add(child / "departments")
        except OSError:
            pass

    add(oc_root / "workspace" / "agents" / "main" / "departments")

    return out


def resolve_departments_tree(client_dept_slugs, state: dict, verbose: bool = False) -> DepartmentsTreeResolution:
    """
    DEFECT B + C fix: resolve the ONE on-disk departments directory this
    client's workforce actually lives in.

    Precedence — evidence, not authority; the score decides:
      1. config-derived (openclaw.json agents.list dept-<slug>.workspace) --
         GROUND TRUTH. Preferred outright over every fixed-candidate guess
         whenever it resolves, per client_dept_slugs.
      2. Every fixed candidate from _departments_tree_candidates(), SCORED by
         how many of `client_dept_slugs` (the client's OWN department set --
         DEFECT A) actually resolve to a directory inside it
         (suffix-tolerant -- DEFECT D).

    If NO candidate scores > 0, nothing is built yet -- returns a resolution
    with path=None, resolved_via="none" (the pre-existing "genuinely empty
    box" case; never a failure).

    If two or more DISTINCT directories tie for the best NONZERO score among
    the scored (non-config) candidates, resolution is AMBIGUOUS --
    AmbiguousDepartmentsTreeError is raised rather than silently picking one.
    """
    client_dept_slugs = list(client_dept_slugs)

    cfg_path = find_openclaw_config_path()
    config_dir = _config_derived_departments_dir(cfg_path, client_dept_slugs)
    if config_dir is not None:
        score = sum(1 for s in client_dept_slugs if resolve_dept_dir_in_tree(config_dir, s))
        if verbose:
            print(f"[refresh-build-state] departments tree (config-derived, preferred): "
                  f"{config_dir} — resolves {score}/{len(client_dept_slugs)} dept(s)")
        return DepartmentsTreeResolution(config_dir, "config", score,
                                          len(client_dept_slugs), [(str(config_dir), score)])

    candidates = _departments_tree_candidates(state)
    scored = []
    for c in candidates:
        n = sum(1 for s in client_dept_slugs if resolve_dept_dir_in_tree(c, s))
        scored.append((c, n))
        if verbose:
            print(f"[refresh-build-state] candidate tree: {c} — resolves {n}/{len(client_dept_slugs)} dept(s)")

    if not scored or not client_dept_slugs:
        return DepartmentsTreeResolution(None, "none", 0, len(client_dept_slugs),
                                          [(str(c), n) for c, n in scored])

    best_score = max(n for _, n in scored)
    if best_score == 0:
        return DepartmentsTreeResolution(None, "none", 0, len(client_dept_slugs),
                                          [(str(c), n) for c, n in scored])

    winners = [c for c, n in scored if n == best_score]
    if len(winners) > 1:
        raise AmbiguousDepartmentsTreeError(
            f"{len(winners)} candidate departments trees tie at {best_score}/"
            f"{len(client_dept_slugs)} resolved dept(s); refusing to guess: "
            + "; ".join(str(w) for w in winners)
        )

    return DepartmentsTreeResolution(winners[0], "scored", best_score,
                                      len(client_dept_slugs),
                                      [(str(c), n) for c, n in scored])


# ─── Per-dept status heuristics (reused from backfill-build-state.py) ────────

def detect_role_library_status(dept_dir: Path) -> str:
    """Heuristic: if how-to.md still has [PENDING — FILL FROM LIBRARY], it's pending."""
    if not dept_dir or not dept_dir.is_dir():
        return "pending"
    filled = 0
    total = 0
    for how_to in dept_dir.rglob("how-to.md"):
        total += 1
        try:
            content = how_to.read_text(encoding="utf-8", errors="replace")
            if "PENDING — FILL FROM LIBRARY" not in content and "PENDING" not in content:
                filled += 1
        except OSError:
            pass
    if total == 0:
        return "pending"
    return "done" if filled >= (total * 0.8) else "pending"


def count_roles_on_disk(dept_dir: Path) -> int:
    """
    DEFECT #5 (build-state honesty): count the role folders that ACTUALLY exist
    on disk for a department, so rolesDone reflects DISK TRUTH and can never be
    set to the planned count while the workspace is empty. A role folder is any
    direct subdir that carries a how-to.md (the role's entry point), excluding
    department-level helper dirs (sops/, memory/, _archive, etc.).
    """
    if not dept_dir or not dept_dir.is_dir():
        return 0
    SKIP = {"sops", "memory", "_archive", "_index", "_compliance_audit",
            "_pending_rewrite", "_stage1_drafts"}
    n = 0
    for child in dept_dir.iterdir():
        if not child.is_dir():
            continue
        if child.name in SKIP or child.name.startswith((".", "_")):
            continue
        if (child / "how-to.md").is_file():
            n += 1
    return n


def detect_sop_library_status(dept_dir: Path) -> str:
    """Heuristic: if SOP/ files exist and none are empty stubs, it's done."""
    if not dept_dir or not dept_dir.is_dir():
        return "pending"
    sop_files = list(dept_dir.rglob("SOP/*.md"))
    sop_files = [f for f in sop_files if f.name != "00-INDEX.md"]
    if not sop_files:
        return "pending"
    stub_count = 0
    for f in sop_files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            if "[Step 1 - to be personalized]" in content or len(content.strip()) < 100:
                stub_count += 1
        except OSError:
            pass
    return "done" if stub_count == 0 else "pending"


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-sync .workforce-build-state.json from _index.json + on-disk dirs")
    parser.add_argument("--dry-run", action="store_true", help="No writes, just report")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--strict", action="store_true", default=True,
                        help="Gate status:done on library+wiring booleans from the build-state (default ON)")
    parser.add_argument("--counts-only", action="store_true",
                        help="Update role counts only; never touch status field")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).isoformat()

    # Load _index.json
    index_path = find_index_json_path()
    if not index_path:
        print("FATAL: _index.json not found — install Skill 23 first.", file=sys.stderr)
        sys.exit(1)
    try:
        idx = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"FATAL: cannot read _index.json at {index_path}: {e}", file=sys.stderr)
        sys.exit(1)

    index_depts = idx.get("departments", {})
    if args.verbose:
        print(f"[refresh-build-state] _index.json: {len(index_depts)} depts, "
              f"total_roles={idx.get('total_roles', '?')}")

    # Load build-state (FAIL LOUD if absent)
    state_path = find_build_state_path()
    if not state_path.exists():
        print(f"FATAL: .workforce-build-state.json not found at {state_path}. "
              f"This box must be built with Skill 23 before converge can refresh it.", file=sys.stderr)
        sys.exit(1)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"FATAL: cannot read build-state at {state_path}: {e}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"[refresh-build-state] build-state loaded from {state_path}")

    # Detect departments shape (array vs keyed-object) and preserve it
    existing_depts = state.get("departments", {})
    if isinstance(existing_depts, list):
        dept_shape = "array"
        # Convert to dict for uniform processing
        existing_depts_dict = {
            (d.get("slug") or d.get("id") or str(i)): d
            for i, d in enumerate(existing_depts)
        }
    else:
        dept_shape = "object"
        existing_depts_dict = dict(existing_depts) if existing_depts else {}

    if args.verbose:
        print(f"[refresh-build-state] departments shape: {dept_shape}, "
              f"existing={len(existing_depts_dict)}")

    # DEFECT A + B + C: resolve the departments tree by SCORING candidates
    # against this CLIENT's own department set (existing_depts_dict keys) --
    # never the canonical index. A client with a custom company tree has real
    # departments that a fixed-candidate guess never finds; scoring against
    # what THEY actually have is the only way to pick the right tree without
    # also picking up every generic canonical department.
    client_dept_slugs = list(existing_depts_dict.keys())
    try:
        tree_resolution = resolve_departments_tree(client_dept_slugs, state, verbose=args.verbose)
    except AmbiguousDepartmentsTreeError as e:
        print(f"FATAL: departments tree resolution is ambiguous — refusing to guess. {e}",
              file=sys.stderr)
        print("       A confident wrong measurement here would corrupt the honesty-floor "
              "write (DEFECT #5). Disambiguate by setting .workspaceRoot in build-state to "
              "the workspace whose departments/ holds this workforce, then re-run.",
              file=sys.stderr)
        sys.exit(1)

    depts_dir = tree_resolution.path
    if args.verbose:
        print(f"[refresh-build-state] departments tree resolved via "
              f"'{tree_resolution.resolved_via}': {depts_dir} "
              f"({tree_resolution.score}/{tree_resolution.checked} client dept(s) matched)")

    # Upsert each dept the CLIENT ALREADY HAS in build-state (DEFECT A fix).
    # Never iterate _index.json here -- that adds every canonical department
    # to a client's roster regardless of whether they ever selected it. A
    # department's presence in build-state is the ONLY signal this script
    # trusts for "the client has this department"; the build/reconciliation
    # pipeline (build-workforce.py) is what may add one, with a provenanced
    # decision recorded.
    changed = False
    for slug in list(existing_depts_dict.keys()):
        entry = existing_depts_dict[slug]
        idx_entry = index_depts.get(slug)
        # rolesPlanned is authoritative from _index.json ONLY for a CANONICAL
        # department. A client custom (non-canonical) department has no entry
        # in _index.json -- preserve whatever rolesPlanned was already
        # recorded rather than zeroing it out.
        if idx_entry is not None:
            roles_count = len(idx_entry.get("roles", []))
        else:
            roles_count = entry.get("rolesPlanned", 0)

        # DEFECT D fix: suffix/case/separator-tolerant dept-dir resolution
        # inside the resolved tree, mirroring verify-wiring.sh's
        # resolve_one_dept(). A slug stored on disk as "<slug>-dept/" used to
        # resolve to a non-existent bare path and measure ZERO roles.
        dept_on_disk = resolve_dept_dir_in_tree(depts_dir, slug)
        rl_status = detect_role_library_status(dept_on_disk)
        sop_status = detect_sop_library_status(dept_on_disk)
        # DEFECT #5: rolesDone reflects DISK TRUTH, not the planned count.
        roles_on_disk = count_roles_on_disk(dept_on_disk)

        # C1: Read library/wiring booleans from the gates (written by
        # verify-library-gate.sh / verify-wiring.sh), not the local heuristics.
        # Fall back to the heuristic only if gate fields are absent.
        gate_rl_filled = entry.get("roleLibraryFilled")
        gate_sop_filled = entry.get("sopLibraryFilled")
        gate_wiring = entry.get("wiringStatus", "")
        # If gate fields are missing, seed from heuristic (first-run fallback)
        if gate_rl_filled is None:
            gate_rl_filled = (rl_status == "done")
        if gate_sop_filled is None:
            gate_sop_filled = (sop_status == "done")

        # C2: Gate status:done on all three conditions (library + wiring)
        if args.counts_only:
            # --counts-only: never touch status
            new_status = entry.get("status", "building")
        elif args.strict:
            wiring_done = (gate_wiring == "done")
            dept_done = bool(gate_rl_filled) and bool(gate_sop_filled) and wiring_done
            new_status = "done" if dept_done else entry.get("status", "building")
        else:
            new_status = "done"  # legacy/non-strict: count-based

        # DEFECT #5 (honesty hard floor): a dept can NEVER be "done" while 0
        # roles are on disk, regardless of gate booleans or --strict mode.
        # status:"done" with rolesDone:0 was the exact fiction the canary hit.
        if roles_on_disk == 0 and new_status == "done":
            new_status = entry.get("status", "building")
            if new_status == "done":
                new_status = "building"

        if (entry.get("rolesPlanned") != roles_count or
                entry.get("rolesDone") != roles_on_disk or
                entry.get("status") != new_status):
            entry["rolesPlanned"] = roles_count
            entry["rolesDone"] = roles_on_disk
            entry["status"] = new_status
            entry["roleLibraryFilled"] = gate_rl_filled
            entry["sopLibraryFilled"] = gate_sop_filled
            entry["updatedAt"] = now
            existing_depts_dict[slug] = entry
            changed = True
            if args.verbose:
                print(f"  updated dept: {slug} (planned={roles_count}, "
                      f"onDisk={roles_on_disk}, status={new_status})")

    # Recompute totals from the CLIENT's own department set (DEFECT A fix) --
    # never the canonical index, which would report every canonical
    # department's totals regardless of what this client actually has.
    total_roles = sum(int(d.get("rolesPlanned", 0) or 0) for d in existing_depts_dict.values())
    if state.get("totalRoles") != total_roles or state.get("totalDepartments") != len(existing_depts_dict):
        state["totalRoles"] = total_roles
        state["totalDepartments"] = len(existing_depts_dict)
        changed = True

    # Record which tree was resolved (and how) so a caller can tell what was
    # actually measured, per DEFECT B/C.
    if state.get("departmentsTreeResolution") != tree_resolution.to_state_dict():
        state["departmentsTreeResolution"] = tree_resolution.to_state_dict()
        changed = True

    # Write back in original shape
    if dept_shape == "array":
        state["departments"] = list(existing_depts_dict.values())
    else:
        state["departments"] = existing_depts_dict

    state["lastRefreshedAt"] = now
    state["refreshSource"] = "refresh-build-state-from-index.py"

    if args.dry_run:
        print(f"[DRY-RUN] Would write {state_path} (changed={changed})")
        print(f"changed={1 if changed else 0}")
        return

    if changed:
        # Atomic write
        state_dir = state_path.parent
        fd, tmp_path = tempfile.mkstemp(prefix=".build-state.", suffix=".json.tmp",
                                        dir=str(state_dir))
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, indent=2)
                f.write("\n")
            os.replace(tmp_path, str(state_path))
        except OSError as e:
            if Path(tmp_path).exists():
                Path(tmp_path).unlink(missing_ok=True)
            print(f"FATAL: write failed: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"[refresh-build-state] Updated {state_path} ({len(existing_depts_dict)} depts, "
              f"total_roles={total_roles})")
    else:
        if args.verbose:
            print("[refresh-build-state] No changes needed — build-state is current")

    print(f"changed={1 if changed else 0}")


if __name__ == "__main__":
    main()
