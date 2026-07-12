#!/usr/bin/env python3
"""
refresh-stale-roles.py — THE ARTIFACT-REFRESH-QUEUE CONSUMER (P2-08 step 2).

────────────────────────────────────────────────────────────────────────────
THE GAP THIS CLOSES
────────────────────────────────────────────────────────────────────────────
`.artifact-refresh-queue.json` has had a PRODUCER since v12.27.0
(detect-stale-artifacts.py, invoked from update-skills.sh and
shared-utils/workspace-dept-refresh.sh) but NEVER a CONSUMER. A box that
updates its skills keeps its OLD role docs forever — the library content
changes, the queue faithfully records "this role is now STALE", and nothing
ever acts on that record (Presentation spec §13.9 deploy trap; P2-08 (b)).

v16.0.2 shipped floor-fill-driver.py, which closed the MISSING-role half of
this gap (a box that lacks a role the library now ships gets it created).
It is explicitly skip-existing / no-clobber — it will never touch a role
that already has a folder on disk. That leaves the STALE half of the gap
wide open: a role the box already has, whose canonical content changed
upstream, never gets refreshed. THIS script is that missing half.

────────────────────────────────────────────────────────────────────────────
SCOPE (P2-08 (c) step 2, extended by D2 to close the sop/dept drain gap)
────────────────────────────────────────────────────────────────────────────
Drains queue items where status == "STALE" and kind is "role", "sop" (D2), or
"dept" (D2):
  - role: unchanged since P2-08 (see refresh_one() below, MOVED VERBATIM from
    the original single-kind consumer) — re-fills how-to.md from the role
    library.
  - sop (D2): re-copies the dept-level SOP file bytes from
    templates/role-library/<dept>/sops/<fname> over the client's EXISTING
    copy under departments/<dept-dir>/sops/<fname> (see refresh_sop()).
  - dept (D2): a department's content_sha is a ROLLUP hash over its member
    roles' content_shas (hash-content-manifest.py) — there is no independent
    dept-level file to overwrite. Draining a STALE dept row is a provenance
    RESTAMP only (source_content_sha -> the queue row's own "current" sha),
    applied via _apply_state_restamps() once this run's STALE member
    roles/SOPs have brought the rollup back into agreement.
  - MISSING roles/SOPs/depts stay floor-fill-driver.py's job (this script
    never creates a new role folder, SOP file, or department scaffold — if
    the artifact isn't already on disk, the item is skipped loudly, not
    fabricated).
  - kind == "persona", and status == "ORPHAN" / "UNTRACKED" / "MISSING"
    items are left untouched in the queue — out of this unit's scope. (The
    stale-SOP-*library*-ghost case, a different defect, was fixed at
    v19.50.0 via ingest-sop-library.sh + the row-count gate.)

For each in-scope item:
  1. Parse "<dept>/<role-slug>" from the item's "key".
  2. Locate the role's EXISTING folder on disk under
     departments/<dept>-dept/ (idempotent: it must already be there; if
     it's missing, this is not actually a "stale" case on this box and the
     item is skipped loudly, never silently, never crashing the drain).
  3. Re-run the SAME library_lookup() + try_library_fill() machinery
     create_role_workspace() itself uses (build-workforce.py's own
     canonical fill path) — real content, identical to what a fresh build
     would produce, never hand-authored or stubbed.
  4. Overwrite ONLY how-to.md with the freshly filled + re-stamped content.
     IDENTITY.md / SOUL.md / MEMORY.md / HEARTBEAT.md are role-specific
     (never library-templated) and are NEVER touched.
  5. On success, the item is dropped from the queue (it is no longer
     actionable — the fresh provenance marker now carries the CURRENT
     content_sha, so a re-run of detect-stale-artifacts.py will classify
     it CURRENT). On failure (poisoned entry: nonexistent path, corrupt
     row, library miss, fill-too-thin), the item is left in the queue,
     a loud WARN is printed, and THE DRAIN CONTINUES — one bad row never
     aborts the update.

Fully additive / idempotent / re-runnable: a role already CURRENT is not in
the queue in the first place (detect-stale-artifacts.py only emits
actionable items), so re-running this script when the queue is already
drained is a no-op that prints "0 artifact(s) refreshed".

────────────────────────────────────────────────────────────────────────────
CLI
────────────────────────────────────────────────────────────────────────────
  --workspace <dir>    client workspace root (default: platform-appropriate
                        resolution, same as detect-stale-artifacts.py).
  --queue-file <path>  default: <workspace>/.artifact-refresh-queue.json
  --apply              actually write files + rewrite the queue. Without
                        this flag the script is DRY-RUN: it reports exactly
                        what it would refresh/skip but touches nothing.

EXIT CODES
  0   drain complete, or a benign/legitimate skip — nothing to drain, no
      queue, everything already CURRENT, an out-of-scope kind/status row, a
      missing library source, or a missing EXISTING dest (the latter two are
      floor-fill-driver.py's MISSING job, not this drain's) — a missing/
      corrupt queue is reported and skipped, never fatal to the caller
      (update-skills.sh).
  3   at least one IN-SCOPE sop/dept refresh genuinely failed — a real IO
      error re-copying a SOP, a malformed in-scope row, or a
      .workforce-build-state.json restamp write failure (D2). The drain
      still ran to completion (one bad row never aborts it); this code only
      tells the caller the completeness contract was NOT met. Also writes
      <workspace>/.artifact-refresh-receipt.json {ok, refreshed, skipped,
      failed_inscope, remaining_inscope_stale, ...} and prints
      "DRAIN_STATUS ok=<0|1> ..." on stdout as a pipe-immune cross-check.
  1   only on a usage error (bad CLI args).
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Self-locating skill-23 resolution (same pattern as floor-fill-driver.py) ──
_SCRIPT = Path(__file__).resolve()
_DEFAULT_SKILL_DIR = _SCRIPT.parent.parent


def _resolve_skill_dir() -> Path:
    cands = []
    env = os.environ.get("OPENCLAW_SKILL23_DIR")
    if env:
        cands.append(Path(env))
    cands.append(_DEFAULT_SKILL_DIR)
    cands.append(Path.home() / ".openclaw/skills/23-ai-workforce-blueprint")
    cands.append(Path("/data/.openclaw/skills/23-ai-workforce-blueprint"))
    for c in cands:
        try:
            if (c / "scripts" / "create_role_workspaces.py").is_file():
                return c
        except OSError:
            continue
    return _DEFAULT_SKILL_DIR


SKILL_DIR = _resolve_skill_dir()
SCRIPTS = SKILL_DIR / "scripts"
LIBRARY = SKILL_DIR / "templates" / "role-library"
sys.path.insert(0, str(SCRIPTS))
import create_role_workspaces as crw  # type: ignore  # noqa: E402

HOME = os.path.expanduser("~")

_NN_RE = re.compile(r'^\d{1,3}[-_]')
_ROLE_RE = re.compile(r'^(?:ROLE|role)--')


def norm(name: str) -> str:
    """Same normalization floor-fill-driver.py uses to match a queue slug
    against an on-disk folder name (strip NN- prefix / ROLE-- prefix,
    collapse --, lowercase)."""
    n = str(name or "").strip()
    n = _NN_RE.sub('', n)
    n = _ROLE_RE.sub('', n)
    if n.endswith('.md'):
        n = n[:-3]
    n = n.replace('--', '-')
    return n.lower()


def resolve_workspace(explicit):
    """Mirrors detect-stale-artifacts.py's resolve_workspace()."""
    if explicit:
        return Path(explicit)
    candidates = [
        "/data/.openclaw/workspace",
        os.path.join(HOME, ".openclaw", "workspace"),
    ]
    for c in candidates:
        if os.path.isdir(os.path.join(c, "departments")) or \
           os.path.isfile(os.path.join(c, ".workforce-build-state.json")):
            return Path(c)
    if os.path.isdir("/data/.openclaw"):
        return Path("/data/.openclaw/workspace")
    return Path(os.path.join(HOME, ".openclaw", "workspace"))


def find_role_dir(dept_dir: Path, role_slug: str):
    """Locate an EXISTING role folder under dept_dir matching role_slug
    (normalized match, same convention floor-fill-driver.py uses). Returns
    None if not present — this script never creates folders."""
    if not dept_dir.is_dir():
        return None
    target = norm(role_slug)
    for e in dept_dir.iterdir():
        if e.is_dir() and ((e / "how-to.md").exists() or (e / "IDENTITY.md").exists()):
            if norm(e.name) == target:
                return e
    roles_sub = dept_dir / "roles"
    if roles_sub.is_dir():
        for e in roles_sub.iterdir():
            if e.is_dir() and norm(e.name) == target:
                return e
    return None


def refresh_one(workspace: Path, dept_slug: str, role_slug: str, label, apply_: bool):
    """Attempt to refresh one STALE role artifact. Returns (ok, detail)."""
    dept_dir = workspace / "departments" / f"{dept_slug}-dept"
    role_dir = find_role_dir(dept_dir, role_slug)
    if role_dir is None:
        return False, (f"no EXISTING role folder for '{dept_slug}/{role_slug}' under "
                        f"{dept_dir} — not a stale-refresh case on this box (that would "
                        f"be floor-fill's job); skipped, nothing written")

    is_ceo = (norm(role_slug) == "master-orchestrator")
    role_name = label or role_slug.replace("-", " ").title()

    # try_library_fill() does the lookup + token-fill + provenance-header stamp
    # + the >=3072B floor check, IDENTICAL to what create_role_workspace() runs
    # for a brand-new role. Returns None on no-match or too-thin (never a stub).
    filled = crw.try_library_fill(role_name, dept_dir, is_ceo, lib_key=role_slug)
    if filled is None:
        return False, (f"library_fill produced no usable content for "
                        f"'{dept_slug}/{role_slug}' (no library match, or fill below "
                        f"the 3072B floor) — skipped, existing how-to.md left untouched")

    how_to = role_dir / "how-to.md"
    if apply_:
        how_to.write_text(filled, encoding="utf-8")
    return True, f"{dept_slug}/{role_slug} -> {role_dir.name}/how-to.md ({len(filled.encode('utf-8'))}B)"


def find_dept_dir(workspace: Path, dept_slug: str):
    """Locate an EXISTING department folder for a BARE manifest dept id (e.g.
    "sales", never "sales-dept"). Tries both on-disk naming conventions this
    skill has shipped -- the bare id first, then the "-dept" suffixed form
    refresh_one()'s role lookup assumes -- and falls back to the bare
    candidate Path if neither exists. Unlike find_role_dir() this never
    returns None: the sop/dept branches below need the Path itself even when
    nothing is there yet, so they can do their own .is_dir() / dest-absent
    check and report exactly where they looked."""
    departments_root = workspace / "departments"
    bare = departments_root / dept_slug
    if bare.is_dir():
        return bare
    suffixed = departments_root / f"{dept_slug}-dept"
    if suffixed.is_dir():
        return suffixed
    return bare


def refresh_sop(workspace: Path, dept_slug: str, sop_slug: str, apply_: bool):
    """Attempt to refresh one STALE dept-level SOP artifact (D2) by
    re-copying the canonical file bytes from the role library over the
    client's EXISTING copy. Returns (ok, detail).

    Mirrors refresh_one()'s skip-vs-fail contract: a missing library source
    or a missing EXISTING dest file is a BENIGN skip (ok=False, no
    exception raised) — that is floor-fill-driver.py's MISSING job, not this
    drain's. An OSError raised during the actual read/write is left to
    PROPAGATE to the caller in main(), which treats that as a genuine
    in-scope failure (failed_inscope), never a benign skip."""
    dept_key = crw.normalize_dept(dept_slug)
    fname = f"{sop_slug}.md"
    src = LIBRARY / dept_key / "sops" / fname
    if not src.is_file():
        return False, (f"no library SOP source at {src} for '{dept_slug}/{sop_slug}' "
                        f"— skipped, nothing written")

    dept_dir = find_dept_dir(workspace, dept_slug)
    dest = dept_dir / "sops" / fname
    if not dest.is_file():
        return False, (f"no EXISTING SOP file for '{dept_slug}/{sop_slug}' at {dest} — "
                        f"not a stale-refresh case on this box (that would be "
                        f"floor-fill's MISSING job); skipped, nothing written")

    content = src.read_text(encoding="utf-8")
    if apply_:
        dest.write_text(content, encoding="utf-8")
    return True, f"{dept_slug}/{sop_slug} -> {dept_dir.name}/sops/{fname} ({len(content.encode('utf-8'))}B)"


def _apply_state_restamps(workspace: Path, sop_restamps: dict, dept_restamps: dict) -> bool:
    """Additively merge freshly-refreshed sop/dept source_content_sha values
    into .workforce-build-state.json's artifactProvenance (D2), leaving
    artifactProvenance.roles / .personas — and everything else in the state
    file — completely untouched.

    sop_restamps / dept_restamps are {key -> {"source_content_sha": ..., ...}}
    maps built by main() from the queue rows' own "current" sha (the
    manifest sha detect-stale-artifacts.py already resolved when it produced
    the queue). Returns True on success, False on a genuine state-write
    failure — NEVER raises, so a poisoned/unwritable state file cannot abort
    the drain; the caller decides whether that failure is in-scope-fatal."""
    if not sop_restamps and not dept_restamps:
        return True
    state_path = workspace / ".workforce-build-state.json"
    try:
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            state = {}
        if not isinstance(state, dict):
            state = {}
        ap = state.get("artifactProvenance")
        if not isinstance(ap, dict):
            ap = {}
        ap.setdefault("roles", {})
        ap.setdefault("personas", {})
        sops = dict(ap.get("sops") or {})
        depts = dict(ap.get("depts") or {})
        sops.update(sop_restamps)
        depts.update(dept_restamps)
        ap["sops"] = sops
        ap["depts"] = depts
        state["artifactProvenance"] = ap
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return True
    except (OSError, json.JSONDecodeError) as e:
        print(f"  refresh-stale-roles: WARN could not write state restamps to {state_path}: {e}",
              file=sys.stderr)
        return False


def _write_receipt(workspace: Path, ok: bool, refreshed: int, skipped: int,
                    failed_inscope: int, remaining_inscope_stale: int, apply_: bool) -> None:
    """Write <workspace>/.artifact-refresh-receipt.json — a pipe-immune
    backup of the drain outcome (D2) so a caller whose stdout got swallowed
    by a `| tee` pipeline (update-skills.sh's pipefail-correct capture) can
    still recover {ok: bool, ...} straight off disk. Best-effort: an OSError
    here is reported but never raised — the receipt is a documented
    cross-check, not the contract's source of truth (the process exit code
    is)."""
    receipt = {
        "ok": bool(ok),
        "apply": bool(apply_),
        "refreshed": refreshed,
        "skipped": skipped,
        "failed_inscope": failed_inscope,
        "remaining_inscope_stale": remaining_inscope_stale,
        "generator": "refresh-stale-roles.py",
        "at": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = workspace / ".artifact-refresh-receipt.json"
    try:
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"  refresh-stale-roles: WARN could not write receipt to {receipt_path}: {e}",
              file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Drain STALE role/sop/dept-kind entries from "
                    ".artifact-refresh-queue.json by re-copying fresh content from the "
                    "role library (P2-08, extended by D2 for sop/dept).")
    parser.add_argument("--workspace", default=None,
                        help="Client workspace root (default: resolved platform-appropriately).")
    parser.add_argument("--queue-file", default=None,
                        help="Default: <workspace>/.artifact-refresh-queue.json")
    parser.add_argument("--apply", action="store_true",
                        help="Actually write files + rewrite the queue. Default: dry-run report only.")
    args = parser.parse_args(argv)

    workspace = resolve_workspace(args.workspace)
    queue_path = Path(args.queue_file) if args.queue_file else workspace / ".artifact-refresh-queue.json"

    if not queue_path.is_file():
        print(f"  refresh-stale-roles: no refresh queue found at {queue_path} — nothing to drain")
        return 0

    try:
        raw = queue_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        print(f"  refresh-stale-roles: WARN queue file unreadable/corrupt at {queue_path} "
              f"({e}) — skipped loudly, update continues", file=sys.stderr)
        return 0

    items = data.get("items", [])
    if not isinstance(items, list):
        print("  refresh-stale-roles: WARN queue 'items' is not a list — treating as empty, "
              "update continues", file=sys.stderr)
        items = []

    refreshed = 0
    skipped = 0
    failed_inscope = 0
    remaining_items = []
    state_updates = {"sops": {}, "depts": {}}

    for it in items:
        if not isinstance(it, dict):
            print(f"  refresh-stale-roles: WARN malformed queue row ({it!r}) — "
                  f"skipped loudly, drain continues", file=sys.stderr)
            skipped += 1
            continue

        _kind = it.get("kind")
        _status = it.get("status")

        # ── ROLE branch (MOVED VERBATIM from the original single-kind consumer) ──
        if _kind == "role" and _status == "STALE":
            key = it.get("key", "")
            if not isinstance(key, str) or "/" not in key:
                print(f"  refresh-stale-roles: WARN malformed key '{key}' in a STALE role row — "
                      f"skipped loudly, drain continues", file=sys.stderr)
                skipped += 1
                remaining_items.append(it)
                continue

            dept_slug, role_slug = key.split("/", 1)
            try:
                ok, detail = refresh_one(workspace, dept_slug, role_slug, it.get("label"), args.apply)
            except Exception as e:  # a poisoned entry must NEVER abort the drain
                ok, detail = False, f"EXCEPTION refreshing '{key}': {e}"

            if ok:
                refreshed += 1
                print(f"  refresh-stale-roles: REFRESHED {detail}")
            else:
                skipped += 1
                print(f"  refresh-stale-roles: WARN SKIPPED {detail}", file=sys.stderr)
                remaining_items.append(it)  # stays queued for the next run
            continue

        # ── SOP branch (D2: dept-level SOP rows were never drained) ──
        if _kind == "sop" and _status == "STALE":
            key = it.get("key", "")
            if not isinstance(key, str) or "/" not in key:
                print(f"  refresh-stale-roles: WARN malformed key '{key}' in a STALE sop row — "
                      f"skipped loudly, drain continues", file=sys.stderr)
                skipped += 1
                failed_inscope += 1
                remaining_items.append(it)
                continue

            dept_slug, sop_slug = key.split("/", 1)
            try:
                ok, detail = refresh_sop(workspace, dept_slug, sop_slug, args.apply)
            except OSError as e:  # genuine in-scope IO failure -- counts against the contract
                ok, detail = False, f"OSError refreshing SOP '{key}': {e}"
                failed_inscope += 1
            except Exception as e:  # a poisoned entry must NEVER abort the drain
                ok, detail = False, f"EXCEPTION refreshing SOP '{key}': {e}"
                failed_inscope += 1

            if ok:
                refreshed += 1
                print(f"  refresh-stale-roles: REFRESHED {detail}")
                cur = it.get("current")
                if args.apply and cur:
                    state_updates["sops"][key] = {
                        "source_content_sha": cur,
                        "restamped_at": datetime.now(timezone.utc).isoformat(),
                        "generator": "refresh-stale-roles.py",
                    }
            else:
                skipped += 1
                print(f"  refresh-stale-roles: WARN SKIPPED {detail}", file=sys.stderr)
                remaining_items.append(it)  # stays queued for the next run
            continue

        # ── DEPT branch (D2: stale dept-rollup rows were never drained) ──
        if _kind == "dept" and _status == "STALE":
            key = it.get("key", "")
            if not isinstance(key, str) or not key or "/" in key:
                print(f"  refresh-stale-roles: WARN malformed key '{key}' in a STALE dept row — "
                      f"skipped loudly, drain continues", file=sys.stderr)
                skipped += 1
                failed_inscope += 1
                remaining_items.append(it)
                continue

            dept_dir = find_dept_dir(workspace, key)
            if not dept_dir.is_dir():
                skipped += 1
                print(f"  refresh-stale-roles: WARN SKIPPED no EXISTING department folder for "
                      f"'{key}' under {workspace / 'departments'} — not a stale-refresh case on "
                      f"this box (that would be floor-fill's job); skipped, nothing written",
                      file=sys.stderr)
                remaining_items.append(it)
                continue

            # A dept's content_sha is a ROLLUP over its member roles (see
            # hash-content-manifest.py) -- there is no independent dept-level file
            # to overwrite. Once this run's STALE member roles/SOPs above have been
            # refreshed, the rollup is naturally back in sync; draining this row is
            # a provenance RESTAMP only (_apply_state_restamps below).
            refreshed += 1
            print(f"  refresh-stale-roles: REFRESHED {key} (dept rollup restamp — "
                  f"no independent dept-level file)")
            cur = it.get("current")
            if args.apply and cur:
                state_updates["depts"][key] = {
                    "source_content_sha": cur,
                    "restamped_at": datetime.now(timezone.utc).isoformat(),
                    "generator": "refresh-stale-roles.py",
                }
            continue

        # ── out of scope for this consumer -- left queued untouched ──
        remaining_items.append(it)

    if args.apply:
        new_summary = dict(data.get("summary", {})) if isinstance(data.get("summary"), dict) else {}
        if "stale" in new_summary:
            new_summary["stale"] = max(0, new_summary["stale"] - refreshed)
        new_data = dict(data)
        new_data["items"] = remaining_items
        new_data["summary"] = new_summary
        new_data["last_drain"] = {
            "at": datetime.now(timezone.utc).isoformat(),
            "refreshed": refreshed,
            "skipped": skipped,
            "failed_inscope": failed_inscope,
            "generator": "refresh-stale-roles.py",
        }
        try:
            queue_path.write_text(json.dumps(new_data, indent=2), encoding="utf-8")
        except OSError as e:
            print(f"  refresh-stale-roles: WARN could not rewrite queue file {queue_path}: {e}",
                  file=sys.stderr)

    # Merge sop/dept provenance restamps AFTER the queue rewrite above (D2) --
    # additive-only, never touches artifactProvenance.roles / .personas.
    if state_updates["sops"] or state_updates["depts"]:
        if not _apply_state_restamps(workspace, state_updates["sops"], state_updates["depts"]):
            failed_inscope += len(state_updates["sops"]) + len(state_updates["depts"])

    remaining_inscope_stale = sum(
        1 for it in remaining_items
        if isinstance(it, dict) and it.get("kind") in ("sop", "dept") and it.get("status") == "STALE"
    )

    mode = "" if args.apply else " (DRY-RUN -- pass --apply to write)"
    print(f"  refresh-stale-roles: {refreshed} artifact(s) refreshed, {skipped} skipped, "
          f"{len(remaining_items)} item(s) remain queued{mode}")

    ok_contract = (failed_inscope == 0)
    _write_receipt(workspace, ok_contract, refreshed, skipped, failed_inscope,
                   remaining_inscope_stale, args.apply)
    print(f"  refresh-stale-roles: DRAIN_STATUS ok={1 if ok_contract else 0} "
          f"failed_inscope={failed_inscope} remaining_inscope_stale={remaining_inscope_stale}")
    return 0 if ok_contract else 3


if __name__ == "__main__":
    sys.exit(main())
