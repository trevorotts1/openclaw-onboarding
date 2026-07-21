#!/usr/bin/env python3
"""
detect-stale-artifacts.py — per-artifact CURRENT / STALE / MISSING / ORPHAN /
UNTRACKED detector for a client workforce.

Given a CLIENT workspace + the repo role-library manifest (_index.json, stamped
by hash-content-manifest.py), reports — per role / per dept-level SOP / per
department / per shared persona — whether the client's built copy is:

  CURRENT   — the client built it from the SAME source content_sha the manifest
              now carries.
  STALE     — the client's source content_sha != the manifest's CURRENT content_sha
              (the canonical library content changed since this client was built)
              → "this client's role X is out of date."
  MISSING   — the manifest offers an artifact the client has NO built copy of
              (a role / SOP / dept the library now ships that this client lacks).
  ORPHAN    — the client built an artifact whose key is NOT in the manifest
              (role removed/renamed in the library) → flag for operator review.
  UNTRACKED — the client has a built role file with content but NO provenance
              marker (built before the provenance system shipped) → treated as
              STALE-unknown so it is re-checked.

This is READ-ONLY on the client side. It is the mechanism that drives the refresh
flow: rc 10 + the --json item list become the work queue (re-instantiate STALE
via _instantiate_role_from_library, add MISSING, rewrite build-state provenance,
re-stamp markers).

──────────────────────────────────────────────────────────────────────────────
WHY THIS IS FALSE-POSITIVE-FREE
──────────────────────────────────────────────────────────────────────────────
Detection compares the CANONICAL-SOURCE content_sha (computed by
hash-content-manifest.py over the library TEMPLATE with {{TOKENS}} intact), NOT a
hash of the rendered client bytes. The client's recorded source_content_sha is the
SOURCE hash copied from the manifest at instantiation. So a future edit to ONE
role .md changes ONLY that artifact's content_sha at the next manifest run, which
flags ONLY the clients built from the old sha, for ONLY that artifact — precise,
per-artifact, no per-client/day false positives.

──────────────────────────────────────────────────────────────────────────────
INPUTS
──────────────────────────────────────────────────────────────────────────────
  --workspace <dir>   client workspace root (the dir containing departments/ and
                      .workforce-build-state.json). Default: resolve via the
                      build-workforce path logic (VPS /data first, then ~).
  --manifest <path>   repo _index.json (default: this skill's
                      templates/role-library/_index.json).
  --json              emit a machine-readable verdict instead of the table.

EXIT CODES
  0   all artifacts CURRENT (nothing to refresh).
  10  at least one STALE / MISSING / ORPHAN / UNTRACKED (actionable drift —
      feeds the refresh flow).
  2   could not load the manifest or the workspace.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_DEFAULT_MANIFEST = _SKILL_DIR / "templates" / "role-library" / "_index.json"

HOME = os.path.expanduser("~")

# ONE department-directory resolver for the whole floor pipeline (detector,
# STALE drain, MISSING materializer) — see create_role_workspaces.resolve_dept_dir.
# The import is guarded: this detector is READ-ONLY and must stay runnable on a
# box or fixture where the builder module is absent, so it falls back to an
# equivalent local probe rather than refusing to run.
sys.path.insert(0, str(_SCRIPT_DIR))
try:
    from create_role_workspaces import resolve_dept_dir as _resolve_dept_dir  # type: ignore
except Exception:  # pragma: no cover - exercised only on a bundle without the builder
    _DEPT_DECOR_RE = re.compile(r'^dept[-_]|[-_]dept$')

    def _norm_dept_fallback(name):
        n = str(name or "").strip().lower()
        n = _DEPT_DECOR_RE.sub('', n)
        n = n.replace('_', '-')
        return re.sub(r'-{2,}', '-', n).strip('-')

    def _resolve_dept_dir(departments_root, dept_slug):
        departments_root = Path(departments_root)
        if not departments_root.is_dir():
            return None
        for cand in (departments_root / dept_slug, departments_root / f"{dept_slug}-dept"):
            if cand.is_dir():
                return cand
        target = _norm_dept_fallback(dept_slug)
        if not target:
            return None
        try:
            entries = sorted(departments_root.iterdir())
        except OSError:
            return None
        for e in entries:
            try:
                if e.is_dir() and _norm_dept_fallback(e.name) == target:
                    return e
            except OSError:
                continue
        return None

# Provenance HTML-comment marker the build writes into each how-to.md.
# e.g. <!-- workforce-provenance: source=role-library role-slug=X dept=Y
#         content_sha=sha256:... content_version=1.0.0 instantiated=... generator=... -->
_PROVENANCE_LINE_RE = re.compile(r"workforce-provenance:")
_PROV_FIELD_RE = re.compile(r"(\w[\w-]*)=([^\s]+)")

# Persona provenance marker the build writes into each governing-personas.md, e.g.
#   <!-- workforce-persona-provenance: persona-slug=growth-strategist
#        content_sha=sha256:... content_version=1.0.0 source=persona-library -->
# Personas are a shared pool, so the SAME persona marker may appear in several
# departments' governing-personas.md files; we de-dup on the persona key.
_PERSONA_PROV_LINE_RE = re.compile(r"workforce-persona-provenance:")


# ─── WORKSPACE RESOLUTION ─────────────────────────────────────────────────────

def resolve_workspace(explicit):
    """Resolve the client workspace root. Mirrors build-workforce path logic."""
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
    # Default to the platform-appropriate path even if not present yet.
    if os.path.isdir("/data/.openclaw"):
        return Path("/data/.openclaw/workspace")
    return Path(os.path.join(HOME, ".openclaw", "workspace"))


# ─── MANIFEST: build CURRENT = {key -> content_sha} ───────────────────────────

def load_current(manifest):
    """
    Build CURRENT = {artifact-key -> content_sha} for every canonical artifact:
      roles    : "<dept>/<slug>"
      depts    : "<dept>"            (the bare dept id)
      sops     : "<dept>/<sop-slug>"
      personas : "persona/<slug>"    (shared pool — not per-dept)
    Returns (current dict, meta dict).
    """
    current = {}
    kind = {}   # key -> "role" | "dept" | "sop"
    label = {}  # key -> human label (title / dept / sop slug)

    for role in manifest.get("roles", []):
        slug = role.get("slug")
        dept = role.get("dept")
        sha = role.get("content_sha")
        if not (slug and dept and sha):
            continue
        key = f"{dept}/{slug}"
        current[key] = sha
        kind[key] = "role"
        label[key] = role.get("title", slug)

    depts = manifest.get("departments", {})
    if isinstance(depts, dict):
        for did, d in depts.items():
            if isinstance(d, dict) and d.get("content_sha"):
                current[did] = d["content_sha"]
                kind[did] = "dept"
                label[did] = did

    for s in manifest.get("sops", []):
        if not isinstance(s, dict):
            continue
        slug = s.get("slug")
        dept = s.get("dept")
        sha = s.get("content_sha")
        if not (slug and dept and sha):
            continue
        key = f"{dept}/{slug}"
        current[key] = sha
        kind[key] = "sop"
        label[key] = slug

    # Personas are a SHARED library, not per-dept. They are keyed "persona/<slug>"
    # so a persona key can never collide with a "<dept>/<slug>" role/sop key. A
    # client's governing-personas.md files are rendered by filtering this shared
    # pool, so a client is STALE on a persona when the persona's source content_sha
    # changed since the client recorded it (library-level + per-persona detection).
    for p in manifest.get("personas", []):
        if not isinstance(p, dict):
            continue
        slug = p.get("slug")
        sha = p.get("content_sha")
        if not (slug and sha):
            continue
        key = f"persona/{slug}"
        current[key] = sha
        kind[key] = "persona"
        label[key] = slug

    meta = {
        "manifest_version": manifest.get("version"),
        "content_manifest": manifest.get("content_manifest", {}),
    }
    return current, kind, label, meta


# ─── CLIENT: build BUILT_FROM = {key -> source_content_sha} ───────────────────

def load_built_from_state(workspace):
    """
    FAST PATH: read .workforce-build-state.json.artifactProvenance.
    Returns (built_from dict, present_keys set, found_bool).
    """
    state_path = workspace / ".workforce-build-state.json"
    if not state_path.is_file():
        return {}, set(), False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, set(), False
    ap = state.get("artifactProvenance")
    if not isinstance(ap, dict):
        return {}, set(), False

    built_from = {}
    for key, rec in (ap.get("roles") or {}).items():
        if isinstance(rec, dict) and rec.get("source_content_sha"):
            built_from[key] = rec["source_content_sha"]
    for key, rec in (ap.get("depts") or {}).items():
        if isinstance(rec, dict) and rec.get("source_content_sha"):
            built_from[key] = rec["source_content_sha"]
    for key, rec in (ap.get("sops") or {}).items():
        if isinstance(rec, dict) and rec.get("source_content_sha"):
            built_from[key] = rec["source_content_sha"]
    # Personas: recorded keyed by bare slug; normalize to the shared "persona/<slug>"
    # key space so they match load_current and never collide with role/sop keys.
    for key, rec in (ap.get("personas") or {}).items():
        if isinstance(rec, dict) and rec.get("source_content_sha"):
            norm = key if str(key).startswith("persona/") else f"persona/{key}"
            built_from[norm] = rec["source_content_sha"]
    return built_from, set(built_from.keys()), True


# ─── ON-DISK PRESENCE (the fast path is otherwise filesystem-BLIND) ───────────
#
# load_built_from_state() reads ONLY .workforce-build-state.json. It never looks
# at the filesystem. So an artifact the box BUILT and later LOST — a role folder
# deleted by a tree-reshuffling pass, exactly the loss this detector exists to
# catch — stays recorded in artifactProvenance and classifies CURRENT. MISSING
# could never fire for it, the gap-map came back empty, floor-fill-driver.py had
# nothing to materialize, and the update reported success over a stripped floor.
#
# build-workforce.py writes artifactProvenance on every build, so the fast path
# is the NORMAL path on a freshly built box: the entire MISSING pipeline was dead
# there. The marker-scan fallback (load_built_from_disk) never had this problem —
# it only reports what it can see — so this makes the fast path agree with the
# fallback rather than introducing a new classification.
#
# Presence is verified against the department's REAL directory (crw.resolve_dept_dir:
# bare id / legacy "-dept" suffix / normalized scan absorbing case + separator
# drift), because an exact-path probe misses a real `Sales/` on every
# case-sensitive Linux box and would report the whole department LOST.

_NN_PREFIX_RE = re.compile(r'^\d{1,3}[-_]')
_ROLE_PREFIX_RE = re.compile(r'^(?:ROLE|role)--')


def _norm_artifact(name):
    """Normalize a role/SOP name or on-disk folder/file name to one key."""
    n = str(name or "").strip()
    n = _NN_PREFIX_RE.sub('', n)
    n = _ROLE_PREFIX_RE.sub('', n)
    if n.endswith(".md"):
        n = n[:-3]
    return n.replace('--', '-').lower()


def _scan_dept_dir(dept_dir):
    """Return (role_keys, sop_keys) actually present in a department directory."""
    roles, sops = set(), set()
    for base in (dept_dir, dept_dir / "roles"):
        if not base.is_dir():
            continue
        try:
            entries = list(base.iterdir())
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir() and ((e / "IDENTITY.md").is_file() or (e / "how-to.md").is_file()):
                    roles.add(_norm_artifact(e.name))
                elif e.is_file() and e.suffix == ".md":
                    roles.add(_norm_artifact(e.name))
            except OSError:
                continue
    sops_dir = dept_dir / "sops"
    if sops_dir.is_dir():
        try:
            for e in sops_dir.iterdir():
                if e.is_file() and e.suffix == ".md":
                    sops.add(_norm_artifact(e.name))
        except OSError:
            pass
    return roles, sops


def prune_absent_from_disk(workspace, built_from, present_keys, kind):
    """Drop every recorded key whose artifact is NOT actually on disk, so
    classify() sees it as MISSING instead of trusting a stale build record.

    Returns (built_from, present_keys, dropped_keys).

    Conservative by construction — it only ever REMOVES a claim of presence, and
    only when it can positively establish absence:
      * no departments/ directory at all -> verify nothing (a box mid-build, or
        a state-file-only fixture, must not be reported as totally wiped).
      * persona/* keys are skipped: personas are a shared pool rendered into each
        department's governing-personas.md, not a per-key artifact on disk.
    """
    departments_root = Path(workspace) / "departments"
    if not departments_root.is_dir():
        return built_from, present_keys, []

    scan_cache = {}

    def dept_scan(dept_id):
        if dept_id not in scan_cache:
            d = _resolve_dept_dir(departments_root, dept_id)
            scan_cache[dept_id] = (d, _scan_dept_dir(d)) if d is not None else (None, (set(), set()))
        return scan_cache[dept_id]

    dropped = []
    for key in sorted(set(built_from) | set(present_keys)):
        if str(key).startswith("persona/"):
            continue
        if "/" not in str(key):
            # department-level artifact: present iff its directory resolves.
            if _resolve_dept_dir(departments_root, key) is None:
                dropped.append(key)
            continue
        dept_id, artifact = str(key).split("/", 1)
        dept_dir, (role_keys, sop_keys) = dept_scan(dept_id)
        if dept_dir is None:
            # The whole department is gone. Every artifact under it is gone too.
            dropped.append(key)
            continue
        k = _norm_artifact(artifact)
        this_kind = kind.get(key)
        if this_kind == "sop":
            found = k in sop_keys
        elif this_kind == "role":
            found = k in role_keys
        else:
            # Unknown/orphan key: present if EITHER space has it (never guess it away).
            found = (k in role_keys) or (k in sop_keys)
        if not found:
            dropped.append(key)

    if dropped:
        gone = set(dropped)
        built_from = {k: v for k, v in built_from.items() if k not in gone}
        present_keys = {k for k in present_keys if k not in gone}
    return built_from, present_keys, dropped


def parse_provenance_marker(text):
    """Parse a workforce-provenance marker line → dict of fields, or {}."""
    for line in text.split("\n", 50)[:50]:
        if _PROVENANCE_LINE_RE.search(line):
            fields = dict(_PROV_FIELD_RE.findall(line))
            return fields
    return {}


def load_built_from_disk(workspace):
    """
    FALLBACK: scan departments/<dept>/NN-<slug>/how-to.md for the provenance
    marker. Returns (built_from dict, untracked list of keys, present_keys set).
    A how-to.md with content but no marker → UNTRACKED.
    """
    built_from = {}
    untracked = []
    present = set()
    depts_dir = workspace / "departments"
    if not depts_dir.is_dir():
        return built_from, untracked, present
    for dept_dir in sorted(p for p in depts_dir.iterdir() if p.is_dir()):
        dept = dept_dir.name
        # Persona provenance: shared pool, recorded in each dept's governing-personas.md.
        gov = dept_dir / "governing-personas.md"
        if gov.is_file():
            try:
                gtext = gov.read_text(encoding="utf-8")
            except OSError:
                gtext = ""
            for line in gtext.split("\n"):
                if _PERSONA_PROV_LINE_RE.search(line):
                    fields = dict(_PROV_FIELD_RE.findall(line))
                    pslug = fields.get("persona-slug")
                    psha = fields.get("content_sha")
                    if pslug and psha:
                        key = f"persona/{pslug}"
                        # Shared pool: keep the first sha seen; all depts pin the
                        # same library persona, so dups carry the same sha.
                        built_from.setdefault(key, psha)
                        present.add(key)
        for role_dir in sorted(p for p in dept_dir.iterdir() if p.is_dir()):
            how_to = role_dir / "how-to.md"
            if not how_to.is_file():
                continue
            try:
                text = how_to.read_text(encoding="utf-8")
            except OSError:
                continue
            # Folder is "NN-<slug>"; the slug is everything after the first dash.
            folder = role_dir.name
            slug = folder.split("-", 1)[1] if "-" in folder else folder
            fields = parse_provenance_marker(text)
            if fields.get("content_sha"):
                # Prefer the marker's own role-slug/dept when present.
                m_slug = fields.get("role-slug") or slug
                m_dept = fields.get("dept") or dept
                key = f"{m_dept}/{m_slug}"
                built_from[key] = fields["content_sha"]
                present.add(key)
            elif len(text.strip()) > 0 and "[PENDING" not in text:
                # Content present but no provenance marker → built pre-provenance.
                key = f"{dept}/{slug}"
                untracked.append(key)
                present.add(key)
    return built_from, untracked, present


# ─── CLASSIFY ─────────────────────────────────────────────────────────────────

def classify(current, kind, label, built_from, present_keys, untracked_keys):
    """
    Classify every artifact. Returns (items list, summary counter).

    Each item: {key, kind, label, status, built_from, current}.
    """
    items = []
    summary = {"current": 0, "stale": 0, "missing": 0, "orphan": 0, "untracked": 0}
    untracked_set = set(untracked_keys)

    # Every canonical key in the manifest:
    for key in sorted(current):
        cur_sha = current[key]
        if key in untracked_set:
            status = "UNTRACKED"
        elif key in built_from:
            status = "CURRENT" if built_from[key] == cur_sha else "STALE"
        elif key in present_keys:
            # Present on disk but not in built_from and not flagged untracked:
            # treat as STALE so it is re-checked (defensive).
            status = "STALE"
        else:
            status = "MISSING"
        summary[status.lower()] += 1
        items.append({
            "key": key,
            "kind": kind.get(key, "?"),
            "label": label.get(key, key),
            "status": status,
            "built_from": built_from.get(key),
            "current": cur_sha,
        })

    # ORPHANS: client built a key absent from the manifest.
    manifest_keys = set(current)
    for key in sorted(set(built_from) | present_keys):
        if key not in manifest_keys:
            summary["orphan"] += 1
            items.append({
                "key": key,
                "kind": "orphan",
                "label": key,
                "status": "ORPHAN",
                "built_from": built_from.get(key),
                "current": None,
            })
    return items, summary


# ─── OUTPUT ───────────────────────────────────────────────────────────────────

def print_table(items, summary, meta, workspace, source):
    print("=" * 104)
    print("PER-ARTIFACT STALENESS — CURRENT / STALE / MISSING / ORPHAN / UNTRACKED")
    print(f"workspace : {workspace}")
    print(f"manifest  : v{meta.get('manifest_version')}  "
          f"(content_manifest schema {meta.get('content_manifest', {}).get('manifest_schema')})")
    print(f"build record source: {source}")
    print("=" * 104)
    print(f"{'DEPT/ARTIFACT':<52}{'KIND':<8}{'STATUS':<11}{'built_from':<11}{'current'}")
    print("-" * 104)
    actionable = [i for i in items if i["status"] != "CURRENT"]
    shown = actionable if actionable else items
    for i in shown:
        bf = (i["built_from"] or "—")
        bf = bf.replace("sha256:", "")[:8] if bf != "—" else "—"
        cu = (i["current"] or "—")
        cu = cu.replace("sha256:", "")[:8] if cu != "—" else "—"
        k = i["key"] if len(i["key"]) <= 50 else i["key"][:47] + "..."
        print(f"{k:<52}{i['kind']:<8}{i['status']:<11}{bf:<11}{cu}")
    print("-" * 104)
    print(f"CURRENT={summary['current']}  STALE={summary['stale']}  "
          f"MISSING={summary['missing']}  ORPHAN={summary['orphan']}  "
          f"UNTRACKED={summary['untracked']}")
    if not actionable:
        print("RESULT: all artifacts CURRENT (rc=0)")
    else:
        print(f"RESULT: {len(actionable)} artifact(s) need refresh "
              f"(STALE/MISSING/ORPHAN/UNTRACKED) (rc=10)")
    print("=" * 104)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Detect per-artifact CURRENT/STALE/MISSING/ORPHAN/UNTRACKED "
                    "for a client workforce vs the repo content-manifest.")
    parser.add_argument("--workspace", default=None,
                        help="Client workspace root (default: resolved via the "
                             "build-workforce path logic).")
    parser.add_argument("--manifest", default=str(_DEFAULT_MANIFEST),
                        help=f"Repo _index.json (default: {_DEFAULT_MANIFEST}).")
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON instead of the table.")
    args = parser.parse_args(argv)

    # ── load manifest ──────────────────────────────────────────────────────────
    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        return 2
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: could not load manifest {manifest_path}: {e}", file=sys.stderr)
        return 2
    if not manifest.get("content_manifest"):
        print(f"ERROR: manifest {manifest_path} carries no content_manifest header — "
              f"run hash-content-manifest.py first.", file=sys.stderr)
        return 2

    current, kind, label, meta = load_current(manifest)

    # ── load client build record ────────────────────────────────────────────────
    workspace = resolve_workspace(args.workspace)
    if not workspace.exists():
        print(f"ERROR: workspace not found at {workspace}", file=sys.stderr)
        return 2

    built_from, present_keys, found_state = load_built_from_state(workspace)
    untracked = []
    lost = []
    if found_state:
        source = ".workforce-build-state.json artifactProvenance (fast path)"
        # The build record is a claim about the past, not an observation of the
        # present. Verify it against the tree before trusting it, or an artifact
        # the box built and later LOST classifies CURRENT forever.
        built_from, present_keys, lost = prune_absent_from_disk(
            workspace, built_from, present_keys, kind)
        if lost:
            source += f" + on-disk presence check ({len(lost)} recorded artifact(s) NOT on disk)"
    else:
        bf_disk, untracked, present_disk = load_built_from_disk(workspace)
        built_from = bf_disk
        present_keys = present_disk
        source = "workspace provenance markers (fallback scan)"

    items, summary = classify(current, kind, label, built_from, present_keys, untracked)

    if args.json:
        print(json.dumps({
            "workspace": str(workspace),
            "manifest": str(manifest_path),
            "manifest_version": meta.get("manifest_version"),
            "build_record_source": source,
            "summary": summary,
            "items": items,
        }, indent=2))
    else:
        print_table(items, summary, meta, workspace, source)

    actionable = (summary["stale"] + summary["missing"] +
                  summary["orphan"] + summary["untracked"])
    return 10 if actionable else 0


if __name__ == "__main__":
    sys.exit(main())
