#!/usr/bin/env python3
"""
department-floor.py - the ONE source of truth for the HARD department floor.

FLOOR (computed live from department-naming-map.json v2.6.2): 29 departments =
23 mandatory canonical + 6 universal-primary vertical-pack (one per pack that
EXPLICITLY flags universal_primary=true; the real-estate pack flags none as of
v2.6.1 so its listings dept is industry-gated, not universal). v2.6.2
(2026-07-16, operator ruling) added Funnels as the 23rd mandatory dept: Skill
6's cc_board.py unconditionally stamps department_slug='funnels' for every
job_type='funnel' card regardless of a client's declared vertical, so only a
mandatory (non-vertical-gated) registration actually closes the live misroute
to the general-task catch-all on a standard-floor box — see
funnels-suggested-roles.md and department-naming-map.json's mandatory.funnels
entry for the full reasoning. The count is
ALWAYS derived at runtime from len(HARDCODED_MANDATORY) + the count of
universal-primary pack depts, so no integer is hardcoded as a gate. Below the
floor is only ever reached by an EXPLICIT recorded decline (a mandatory dept, a
universal-primary vertical, or a custom dept the owner declined in Phase 5.5).

WHY THIS EXISTS (the bug it kills):
Clients kept landing with HEAVILY-REDUCED workforces (one client 3 depts, others
3-per-dept / 6-dept / legacy) DESPITE the repo carrying 216 role templates,
the mandatory canonical departments, and 7 industry vertical packs. Diagnosis
found THREE places that trusted the build-state JSON as proof of completion
instead of counting REAL departments on disk:
  1. verify-zhc-standard.sh step-2 read `.departments[]` from the build-state
     JSON, so a hand-seeded 3-dept JSON (a seeded-fiction build-state) reported
     "all canonical present" and passed the floor.
  2. qc-completeness.sh measured per-dept staffing of whatever was ON DISK but
     had NO floor concept at all - 3 well-staffed depts returned PASS.
  3. run-closeout.sh / resume-workforce-build.sh self-completed on JSON
     status=done / closeoutStatus=done with zero disk verification.

THE FIX (this module): compute the EXPECTED floor =
    len(HARDCODED_MANDATORY) mandatory canonical departments
    + len(universal_primary_vertical_departments(...)) universal-primary
      vertical-pack departments (one per pack, marked universal_primary=true in
      department-naming-map.json - these fire for EVERY client regardless of
      industry, giving the universal-primary floor)
    − any department the client EXPLICITLY declined (recorded as an explicit
      decline in build-state canonicalReconciliation.decisions == "no")

    Industry keyword matching STILL adds additional pack departments on top of
    the computed floor, but those extras are not gating - the gate only checks
    for the universal primaries (plus the mandatory set). exit 3 fires when disk
    is below the computed floor or a specific mandatory/universal-primary dept is
    missing. Exit 3 never fires for missing EXTRA (keyword-matched) pack depts -
    those are flavor, not floor.

    NOTE: the computed floor count is ALWAYS derived at runtime from the live
    data (len(HARDCODED_MANDATORY) + count of universal-primary pack depts) so
    the reported number can NEVER drift from what evaluate_floor() enforces.
    No integer floor counts are hardcoded in any human-readable string.

…and then count the REAL department directories ON DISK and FAIL hard when disk
is below the floor or a mandatory/universal-primary dept is missing from disk.
The build-state JSON is NEVER trusted as proof of floor compliance - only disk
is.

Reads the SAME source of truth as build-workforce.py:
    23-ai-workforce-blueprint/department-naming-map.json  (.mandatory + .vertical_packs)

USAGE
  python3 department-floor.py --json            # machine-readable verdict to stdout
  python3 department-floor.py                   # human summary to stderr
  python3 department-floor.py --check-collisions [--json]  # C5 phantom-duplicate gate
EXIT CODES
  0  floor met (all mandatory(−declines) + all universal primaries(−declines) on disk)
     / --check-collisions: no phantom duplicate dept trees
  3  floor NOT met (below computed floor or a mandatory/universal-primary dept missing)
  5  --check-collisions only: phantom duplicate dept trees present (two sibling dirs
     resolving to the same canonical slug, or a phantom '.bak' dept dir on disk)
  7  no workforce / cannot resolve company on disk

The floor verdict (--json / default) also carries INFORMATIONAL `slug_collisions`
and `phantom_backup_dirs` fields (they never change the floor rc; use
--check-collisions to gate on them).

The exact floor count is computed dynamically from HARDCODED_MANDATORY +
universal_primary_vertical_departments(); print it with --json or the default
human summary to see the live count.

This module is import-safe: `from department_floor import evaluate_floor`
(after adding the scripts dir to sys.path) returns the verdict dict directly.
Read-only. Never writes. Idempotent.
"""

import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
NAMING_MAP = SKILL_DIR / "department-naming-map.json"

# ── SHARED DECLINE READER (Issue #2 / Bulletproofing a) ──────────────────────
# Import the ONE normalizer + provenance-gated decline reader so this floor
# checker and build-workforce.py compare declines in the SAME normalized space
# (the drift that caused the residual over-provision bug). Add this script's
# own dir to sys.path so the import resolves whether run as a script or loaded
# via importlib in the CI test harnesses.
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from canonical_decline import (  # noqa: E402
    norm as _shared_norm,
    canonical_decline_set as _shared_canonical_decline_set,
)

# Hardcoded MANDATORY fallback - IDENTICAL to build-workforce.load_canonical_floor()
# so the floor is still enforced on a broken install that lost the naming map.
# CANONICAL FRAMING: the department floor is 23 mandatory + 6 universal-primary
# = 29, all derived LIVE from department-naming-map.json (v2.6.2). This list is
# ONLY the 23 mandatory ids; the 6 universal-primary ids live in
# HARDCODED_UNIVERSAL_PRIMARY below. The full shipped role catalog (every role
# template, far larger than the 29-department floor) is tracked separately in
# templates/role-library/_index.json - do NOT conflate that catalog size with the
# floor. (Historical note: earlier revisions carried stale floor arithmetic such
# as 24/26/28/29(7-universal-era) that mixed the mandatory count with the total;
# the ONLY authoritative numbers now are 23 + 6 = 29 — v2.6.2 added "funnels" as
# the 23rd mandatory dept, 2026-07-16, operator ruling.)
HARDCODED_MANDATORY = [
    "marketing", "sales", "billing-finance", "customer-support",
    "web-development", "app-development", "graphics", "video", "audio",
    "research", "communications", "crm", "openclaw-maintenance", "legal",
    "social-media", "paid-advertisement", "personal-assistant",
    "general-task", "project-architecture-office",
    "bugs", "healer", "quality-control", "funnels",
]

# Hardcoded UNIVERSAL-PRIMARY fallback - the 6 universal-primary vertical-pack
# department ids (one per pack that flags universal_primary=true in
# department-naming-map.json v2.6.1). BROKEN-INSTALL SAFETY NET ONLY: consulted
# solely when the live map yields NO universal primaries (map missing / unreadable
# / corrupt) so a broken install still enforces the FULL 22 + 6 = 28 floor instead
# of silently degrading to 22 and dropping every universal-primary vertical. MUST
# stay in lockstep with the universal_primary=true depts in
# department-naming-map.json and with build-workforce._HARDCODED_UNIVERSAL_PRIMARY.
# On a healthy install the live derivation in universal_primary_vertical_departments()
# returns the 6 real ids and this fallback is NEVER consulted (no gate behavior
# changes on a healthy map).
HARDCODED_UNIVERSAL_PRIMARY = [
    "presentations", "scheduling-dispatch", "logistics-fulfillment",
    "engineering", "account-management", "podcast",
]

# Known legacy aliases + variant slugs a canonical dept can appear under on disk.
# Mirrors build-workforce.CANONICAL_ID_ALIASES + CANONICAL_VARIANT_SLUGS so a
# dept that exists under a different folder name still counts as "present".
CANONICAL_VARIANT_SLUGS = {
    "billing-finance": ["finance", "finance-ops", "billing", "finance-billing", "accounting"],
    "customer-support": ["support", "customer-service", "cs", "client-success"],
    "web-development": ["web-dev", "webdev", "website", "web"],
    "app-development": ["app-dev", "appdev", "mobile", "application-development"],
    "legal": ["legal-compliance", "compliance", "legal-ops", "risk-compliance"],
    "graphics": ["graphics-design", "design", "creative", "graphic-design"],
    "openclaw-maintenance": ["openclaw", "maintenance", "ops", "platform-maintenance"],
    "paid-advertisement": ["paid-ads", "paid-advertising", "ads", "advertising", "paid-media"],
    "social-media": ["social", "smm", "social-media-management"],
    "crm": ["crm-ops", "customer-relationship-management"],
    "communications": ["comms", "communication", "pr", "public-relations"],
    "video": ["video-production", "video-content", "video-editing"],
    "audio": ["audio-production", "audio-content", "sound", "podcast"],
}


def _norm(s):
    """Normalize a slug for membership comparison: lowercase, strip non-alphanumerics.
    DELEGATES to the shared canonical_decline.norm so this checker and
    build-workforce.py can never normalize differently (Issue #2)."""
    return _shared_norm(s)


def load_naming_map():
    try:
        return json.load(open(NAMING_MAP))
    except (OSError, json.JSONDecodeError):
        return {}


def mandatory_ids(nm):
    m = list((nm.get("mandatory") or {}).keys())
    return m or list(HARDCODED_MANDATORY)


def universal_primary_vertical_departments(nm):
    """
    Return the list of universal primary vertical-pack department ids - one per
    pack that EXPLICITLY marks a dept universal_primary=true. These are added to
    EVERY client regardless of industry, giving the len(HARDCODED_MANDATORY) +
    len(result) mandatory floor (computed at runtime - no integer is hardcoded here).

    EXPLICIT-OPT-IN ONLY (v2.6.1): a pack contributes a universal primary ONLY when
    one of its depts carries universal_primary=true. There is NO depts[0] fallback.
    The old fallback auto-promoted the FIRST dept of any pack that lacked the flag,
    which silently forced an industry-specific dept (e.g. real-estate's `listings`,
    the first dept in its pack) onto EVERY client's floor - including coaching /
    consulting clients that have nothing to do with that industry. Removing the
    flag from `listings` plus dropping this fallback makes such a dept industry-
    gated (it now only appears via keyword match in matched_vertical_pack_departments)
    while explicitly-flagged primaries (e.g. saas/`engineering`) stay universal.
    A pack with no flagged dept contributes NOTHING to the universal floor.

    BROKEN-INSTALL SAFETY NET: if the map is unreadable and this live derivation
    comes back EMPTY, the return falls back to HARDCODED_UNIVERSAL_PRIMARY (the 6
    ids) so the enforced floor stays 22 + 6 = 28, never silently 22. This is
    distinct from the removed depts[0] auto-promotion above - it fires ONLY on a
    broken/missing map, never on a healthy install.
    """
    packs = nm.get("vertical_packs") or {}
    primary_ids = []
    seen = set()
    for pack_id, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        depts = pack.get("auto_add_departments", []) or []
        if not depts:
            continue
        # EXPLICIT ONLY: find the universal_primary dept. No depts[0] fallback -
        # a pack with no flagged dept contributes no universal-floor department.
        primary = None
        for dept in depts:
            if isinstance(dept, dict) and dept.get("universal_primary"):
                primary = dept
                break
        if primary:
            did = primary.get("id")
            if did and did not in seen:
                seen.add(did)
                primary_ids.append(did)
    # BROKEN-INSTALL SAFETY NET: if the live map yielded NO universal primaries
    # (map missing / unreadable / corrupt), fall back to the hardcoded 6 so the
    # floor degrades to the FULL 28 (22 + 6), NOT 22. Mirrors mandatory_ids()'s
    # `m or list(HARDCODED_MANDATORY)` fail-safe-to-the-larger-floor pattern. A
    # healthy map always populates primary_ids with the 6 real ids above, so this
    # fallback never fires on a good install (no healthy-path behavior change).
    return primary_ids or list(HARDCODED_UNIVERSAL_PRIMARY)


def matched_vertical_pack_departments(nm, core_answers):
    """
    Return the list of vertical-pack department ids for the client - includes:
      1. All universal primary departments (one per pack, always present for every
         client - these are the universal primaries that form the top layer of the
         computed mandatory floor alongside HARDCODED_MANDATORY).
      2. Additional pack departments that match the client's industry keywords
         (flavor/extras on top of the computed floor, not gating).

    De-duped. Deterministic. Uses the SAME keyword-match logic as
    build-workforce._detect_vertical_packs().
    """
    packs = nm.get("vertical_packs") or {}
    haystack = " ".join([
        str(core_answers.get("industry", "") or ""),
        str(core_answers.get("company_description", "") or ""),
        str(core_answers.get("biggest_challenge", "") or ""),
        str(core_answers.get("tools", "") or ""),
    ]).lower()

    # Phase 1: add the EXPLICIT universal primary from every pack that has one.
    # No depts[0] fallback (v2.6.1): a pack with no universal_primary=true dept
    # contributes nothing here - its depts only appear via the Phase 2 keyword
    # match below, keeping industry-specific depts (e.g. listings) off generic floors.
    all_dept_ids = []
    seen = set()
    for pack_id, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        depts = pack.get("auto_add_departments", []) or []
        if not depts:
            continue
        primary = None
        for dept in depts:
            if isinstance(dept, dict) and dept.get("universal_primary"):
                primary = dept
                break
        if primary:
            did = primary.get("id") if isinstance(primary, dict) else None
            if did and did not in seen:
                seen.add(did)
                all_dept_ids.append(did)

    # Phase 2: keyword-match extras (additional pack depts beyond the primary).
    for pack_id, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        hit = False
        for kw in pack.get("auto_add_keywords", []) or []:
            k = str(kw).strip().lower()
            if not k:
                continue
            if " " in k:
                if k in haystack:
                    hit = True
                    break
            elif re.search(r"\b" + re.escape(k) + r"\b", haystack):
                hit = True
                break
        if not hit:
            continue
        for dept in pack.get("auto_add_departments", []) or []:
            did = dept.get("id") if isinstance(dept, dict) else None
            if did and did not in seen:
                seen.add(did)
                all_dept_ids.append(did)
    return all_dept_ids


def declined_set(build_state):
    """
    The ONLY way to be below the mandatory floor: an EXPLICIT, PROVENANCED decline.

    PROVENANCE-GATED DECLINE MODEL (v10.16.26+ — mirrors build-workforce._canonical_decline_set):
    A decline is ONLY honored when it carries an explicit owner-decision record.
    The default (when provenance is absent) is NO decline — fail-safe to the
    LARGER floor. Bare string 'no' or declinedDepartments[] entries without the
    ownerDeclineConfirmed gate are REJECTED with a warning.

    Accepted forms (either is sufficient):
      1. decisions[cid] is the OBJECT form {decision: "no", source, decidedAt, decidedBy}.
      2. ownerDeclineConfirmed == True + decisions[cid] == "no" (string or object).
      3. ownerDeclineConfirmed == True + declinedDepartments[] (flat list).

    WHY: closes the fabrication vector where a bare string 'no' or flat
    declinedDepartments[] entry (written ad hoc by a non-owner actor) could
    silently shrink the floor with no audit trail.

    Issue #2 fix: DELEGATES to the shared canonical_decline.canonical_decline_set
    so the builder (build-workforce.py) and this on-disk floor checker read the
    EXACT same normalized, provenance-gated decline set. No lockstep drift is
    possible when there is only one reader.
    """
    return _shared_canonical_decline_set(build_state)


def resolve_departments_dir():
    """
    Resolve the active company's departments/ dir ON DISK. Uses detect_platform
    when available, else falls back to the most-recently-modified company under
    ~/clawd/zero-human-company/. Returns Path or None.

    BUG FIX: use detect_platform keys "company_dir" / "company_root" (the keys
    the working qc-completeness.sh uses), NOT the stale "active_zhc_company" /
    "zhc_company_root" keys that never existed. When configured company_root does
    NOT exist, prefer a directly-present <workspace>/departments/ dir rather than
    descending into the first subdir (which may be a single dept folder like
    personal-assistant, causing the whole departments/ tree to be walked as if it
    were the company root -> false floor fail).
    """
    # BUG 2 FIX: sys.path.insert(0, ...) order matters — the LAST insert wins
    # (each call pushes the previous one down).  The old loop inserted lib FIRST,
    # so shared-utils ended up at position 0 and its detect_platform (which returns
    # company_root=~/Downloads/openclaw-master-files/zero-human-company and
    # company_dir=None on the ~/clawd layout) silently shadowed the lib/ version
    # (which correctly resolves company_dir for ~/clawd).  Result: false rc=7.
    # Fix: insert shared-utils first (fallback), then lib/ LAST so lib/ ends at
    # position 0 — exactly the resolution order that qc-completeness.sh uses via
    # the same lib/ detect_platform and that returns a working company_dir.
    for libp in (SKILL_DIR.parent / "shared-utils", SKILL_DIR / "shared-utils", SKILL_DIR / "lib"):
        sys.path.insert(0, str(libp))

    # v20.0.80: the LIVE tree the repair pipeline maintains wins outright.
    # _qc_paths.live_departments_dir() is the ONE definition of that rule
    # (same precedence as floor-fill-driver.py:170-171), shared with
    # _qc_company_info.py so this checker and the repairer can never resolve
    # different trees. Without it a box with BOTH a legacy ~/clawd company tree
    # and a live workspace tree audited the legacy one and reported present
    # departments missing.
    try:
        from _qc_paths import live_departments_dir as _live_dd  # type: ignore
        _live = _live_dd()
        if _live.is_dir():
            return _live
    except ImportError:
        # Partial bundle without _qc_paths.py — fall through to the layouts
        # below rather than fail the gate.
        pass

    zhc_root = None
    workspace = None
    try:
        from detect_platform import get_openclaw_paths  # type: ignore
        paths = get_openclaw_paths()
        # Priority: already-resolved active company dir (same key qc-completeness uses)
        company_dir = paths.get("company_dir")
        if company_dir and Path(company_dir).resolve().is_dir():
            zhc_root = str(Path(company_dir).resolve())
        # Fallback: parent zero-human-company/ + slug scan
        if not zhc_root:
            zhc_root = paths.get("company_root")
            if zhc_root and not Path(zhc_root).is_dir():
                zhc_root = None
        # v20.0.80: detect_platform.get_openclaw_paths() returns "workspace".
        # It has NEVER returned "workspace_root" or "clawd_root", so this line
        # evaluated to None on every box and the fallback below silently used
        # ~/clawd instead of the real workspace — the same wrong-tree defect
        # this release fixes in _qc_company_info.py. Read the real key, and
        # keep the old names as harmless aliases.
        workspace = (paths.get("workspace")
                     or paths.get("workspace_root")
                     or paths.get("clawd_root"))
    except Exception:
        pass
    if not zhc_root:
        ws = Path(workspace) if workspace else Path(os.path.expanduser("~/clawd"))
        # Prefer a directly-present departments/ dir under the workspace root.
        # This avoids descending into a single dept folder (e.g. personal-assistant)
        # and mistaking it for the company root -> false floor fail.
        for direct_depts in (ws / "departments",
                             ws / "zero-human-company" / "departments",
                             Path("/data/.openclaw/workspace/departments")):
            if direct_depts.is_dir():
                return direct_depts
        # Fall back to most-recently-modified subdir under zero-human-company/
        zhc_dir = ws / "zero-human-company"
        if zhc_dir.is_dir():
            cands = sorted(
                (d for d in zhc_dir.iterdir() if d.is_dir() and not d.name.startswith("_")),
                key=lambda d: d.stat().st_mtime, reverse=True,
            )
            if cands:
                zhc_root = str(cands[0])
    if not zhc_root:
        return None
    dd = Path(zhc_root) / "departments"
    if dd.is_dir():
        return dd
    # Non-standard layout: zhc_root itself may be the departments dir
    # (e.g. when detect_platform returns the departments/ path directly)
    zp = Path(zhc_root)
    if zp.is_dir():
        # Only treat it as a departments dir if it contains role-like subdirs,
        # NOT if it looks like a single department (contains role folders only).
        # Heuristic: if it has at least 2 non-hidden subdirs and no how-to.md
        # directly inside, treat as departments root.
        subdirs = [d for d in zp.iterdir() if d.is_dir() and not d.name.startswith((".", "_"))]
        how_to_direct = (zp / "how-to.md").exists()
        if len(subdirs) >= 2 and not how_to_direct:
            return zp
    return None


def departments_on_disk(departments_dir):
    """Return the set of normalized department folder names actually on disk."""
    present = set()
    if not departments_dir or not departments_dir.is_dir():
        return present
    for d in departments_dir.iterdir():
        if d.is_dir() and not d.name.startswith(".") and not d.name.startswith("_"):
            present.add(_norm(d.name))
    return present


def _present(cid, present_norm):
    """True if canonical/vertical id `cid` is on disk under id or any variant."""
    if _norm(cid) in present_norm:
        return True
    for v in CANONICAL_VARIANT_SLUGS.get(cid, []):
        if _norm(v) in present_norm:
            return True
    return False


# ── C5: PHANTOM-DUPLICATE DEPARTMENT-TREE DETECTION ──────────────────────────
# Two sibling directories under departments/ that normalize to the SAME canonical
# slug (billing + billing-finance, legal + legal-compliance, Sales + sales) are a
# PHANTOM DUPLICATE: the variant-aware _present() counts them as ONE department so
# the floor gate never catches the duplication, and both trees keep diverging
# rosters on disk. These helpers surface the collision so a gate can FAIL and a
# reconcile can merge+archive the loser.

# A phantom backup dept dir: 'Presentations.bak-20260615-024720', 'legal.bak', etc.
_BACKUP_DIR_RE = re.compile(r"\.bak(\b|[-_.]|$)", re.IGNORECASE)


def _is_backup_dirname(name):
    """True for a phantom backup dept dir (any '.bak' / '.bak-<stamp>' folder).
    These are not live departments; they poison the SOP/substance gate and must be
    moved OUT of departments/."""
    return bool(_BACKUP_DIR_RE.search(name))


def all_canonical_ids(nm=None):
    """Every canonical department id — mandatory + universal-primary — used to
    resolve a directory name to its canonical slug for collision detection."""
    nm = nm if nm is not None else load_naming_map()
    ids = list(mandatory_ids(nm))
    for u in universal_primary_vertical_departments(nm):
        if u not in ids:
            ids.append(u)
    return ids


def canonical_slug_for(name, nm=None):
    """
    Resolve a department DIRECTORY name to its canonical slug for collision
    detection. Precedence:
      1. DIRECT canonical-id match (a dir literally named after a canonical id —
         mandatory OR universal-primary — maps to ITSELF). This is what keeps a
         'podcast' universal-primary dir from being folded into 'audio' just
         because 'podcast' also appears in audio's variant list.
      2. VARIANT-slug match (CANONICAL_VARIANT_SLUGS): 'billing' -> 'billing-finance',
         'legal-compliance' -> 'legal', 'graphics-design' -> 'graphics'.
      3. No canonical mapping -> None (a genuine custom department; it maps to
         itself and can never collide with a canonical dept).
    Case/spacing/punctuation-insensitive (delegates to the shared _norm).
    """
    nm = nm if nm is not None else load_naming_map()
    n = _norm(name)
    for cid in all_canonical_ids(nm):
        if _norm(cid) == n:
            return cid
    for cid, variants in CANONICAL_VARIANT_SLUGS.items():
        for v in variants:
            if _norm(v) == n:
                return cid
    return None


def _raw_department_dirs(departments_dir):
    """
    Raw (un-normalized) dept dir names on disk, split into (live, backups).
    Hidden/underscore dirs are dropped; '.bak' dirs are collected as backups.
    Unlike departments_on_disk() this preserves the actual folder names (needed to
    identify WHICH sibling to keep vs archive in a collision).
    """
    live, backups = [], []
    if not departments_dir:
        return live, backups
    p = departments_dir if isinstance(departments_dir, Path) else Path(departments_dir)
    if not p.is_dir():
        return live, backups
    for d in sorted(p.iterdir(), key=lambda x: x.name):
        if not d.is_dir() or d.name.startswith((".", "_")):
            continue
        if _is_backup_dirname(d.name):
            backups.append(d.name)
        else:
            live.append(d.name)
    return live, backups


def sibling_slug_collisions(departments_dir, nm=None):
    """
    Detect phantom-duplicate department trees: 2+ sibling dirs under departments/
    that resolve to the SAME canonical slug. Returns a deterministic list of
    collision groups, each: {"canonical": <id>, "dirs": [<raw names, sorted>]}.
    Only canonical collisions are reported (customs map to None -> distinct, and a
    filesystem cannot hold two identically-named siblings anyway).
    """
    nm = nm if nm is not None else load_naming_map()
    live, _ = _raw_department_dirs(departments_dir)
    by_canonical = {}
    for name in live:
        cid = canonical_slug_for(name, nm)
        if cid is None:
            continue
        by_canonical.setdefault(cid, [])
        if name not in by_canonical[cid]:
            by_canonical[cid].append(name)
    collisions = []
    for cid in sorted(by_canonical):
        dirs = sorted(by_canonical[cid])
        if len(dirs) > 1:
            collisions.append({"canonical": cid, "dirs": dirs})
    return collisions


def read_core_answers(build_state, departments_dir):
    """
    Resolve the industry signal needed to compute matched vertical packs.
    Prefer build-state companyIndustry/industry fields; fall back to the
    company-discovery answers file on disk if present.
    """
    bs = build_state or {}
    ca = {
        "industry": bs.get("companyIndustry") or bs.get("industry") or "",
        "company_description": bs.get("companyDescription") or bs.get("company_description") or "",
        "biggest_challenge": bs.get("biggestChallenge") or "",
        "tools": bs.get("tools") or "",
    }
    if any(ca.values()):
        return ca
    # Fallback: scan the company-discovery answers doc for free-text signal.
    if departments_dir:
        company_dir = departments_dir.parent
        for cand in list(company_dir.glob("**/workforce-interview-answers.md")) + \
                    list(company_dir.glob("**/*workforce-proposal.md")):
            try:
                txt = cand.read_text(errors="ignore")
                ca["company_description"] = (ca["company_description"] + " " + txt)[:20000]
                return ca
            except Exception:
                continue
    return ca


def load_build_state():
    candidates = [
        "/data/.openclaw/workspace/.workforce-build-state.json",
        os.path.join(os.path.expanduser("~"), ".openclaw", "workspace", ".workforce-build-state.json"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                return json.load(open(p))
            except (OSError, json.JSONDecodeError):
                return {}
    return {}


# ── C7: AUTHORITATIVE READ OF THE DURABLE "CHOSEN-LIST" ARTIFACT ─────────────
# The departments the client CHOSE during the interview are persisted by
# build-workforce.write_chosen_departments_artifact() in two places:
#   1. build-state  canonicalReconciliation.chosenDepartments.slugs   (durable record)
#   2. <company_dir>/departments.json                                 (durable artifact)
# Downstream (QC gates, closeout, Command Center seeding) must be able to read
# the chosen set AUTHORITATIVELY instead of re-deriving the floor and guessing.
# department-floor is the single tool every gate already consumes, so the chosen
# list is surfaced here — as INFORMATIONAL verdict fields. It never changes the
# floor rc (0/3/7) and it NEVER fabricates a chosen set: when neither source
# exists the reader returns [] with source "none", and the caller decides.

CHOSEN_DEPARTMENTS_ARTIFACT = "departments.json"


def read_chosen_departments(build_state=None, departments_dir=None):
    """
    Read the client's chosen department set. Resolution order (authoritative first):
      1. build-state canonicalReconciliation.chosenDepartments.slugs;
      2. the <company_dir>/departments.json artifact (company_dir = departments_dir's
         parent — where build-workforce writes it);
      3. ([], "none") — NEVER fabricated from the floor.
    Returns (slugs, source) with source in {"build-state", "artifact", "none"}.
    """
    bs = build_state if build_state is not None else load_build_state()
    recon = bs.get("canonicalReconciliation", {}) if isinstance(bs, dict) else {}
    chosen = recon.get("chosenDepartments") if isinstance(recon, dict) else None
    if isinstance(chosen, dict):
        slugs = chosen.get("slugs")
        if isinstance(slugs, list) and slugs:
            return [s for s in slugs if s], "build-state"
    if departments_dir:
        p = departments_dir if isinstance(departments_dir, Path) else Path(departments_dir)
        artifact = p.parent / CHOSEN_DEPARTMENTS_ARTIFACT
        try:
            data = json.loads(artifact.read_text())
        except (OSError, json.JSONDecodeError):
            return [], "none"
        out, seen = [], set()
        for entry in (data if isinstance(data, list) else []):
            s = entry.get("slug") or entry.get("id") if isinstance(entry, dict) else None
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        if out:
            return out, "artifact"
    return [], "none"


def evaluate_floor(departments_dir=None, build_state=None, core_answers=None):
    """
    Compute the HARD department floor and compare it to REAL on-disk departments.

    The floor = len(HARDCODED_MANDATORY) mandatory + len(universal_primary_vertical_departments())
    universal-primary vertical-pack departments. Both counts are derived at runtime
    from the live data so the reported floor ALWAYS equals what this function enforces.
    Additional keyword-matched pack departments are tracked but do NOT gate the floor.

    Returns a verdict dict:
      {
        "rc": 0|3|7,
        "departments_dir": str|None,
        "mandatory": [...],              # canonical mandatory dept ids
        "declined": [...],
        "universal_primary_vertical": [...],  # universal pack primaries (always required)
        "matched_vertical_departments": [...],  # universal primaries + keyword extras
        "expected_floor": [...],         # mandatory(−declined) + universal primaries(−declined)
        "expected_floor_count": int,     # computed floor minus any explicit declines
        "on_disk_count": int,
        "missing_mandatory": [...],      # mandatory not found on disk (not declined)
        "missing_universal_primary": [...],  # universal-primary depts missing from disk
        "slug_collisions": [{"canonical": id, "dirs": [...]}],  # C5 phantom duplicates (informational)
        "phantom_backup_dirs": [...],    # C5 '.bak' dept dirs on disk (informational)
        "chosen_departments": [...],     # C7 durable chosen-list (informational, never fabricated)
        "chosen_departments_source": "build-state"|"artifact"|"none",
        "floor_met": bool,
        "reason": str,
      }
    """
    nm = load_naming_map()
    if build_state is None:
        build_state = load_build_state()
    if departments_dir is None:
        departments_dir = resolve_departments_dir()
    if departments_dir is None:
        return {
            "rc": 7, "departments_dir": None, "floor_met": False,
            "reason": "no workforce / cannot resolve departments dir on disk",
            "mandatory": [], "declined": [], "universal_primary_vertical": [],
            "matched_vertical_departments": [],
            "expected_floor": [], "expected_floor_count": 0, "on_disk_count": 0,
            "missing_mandatory": [], "missing_universal_primary": [],
            "slug_collisions": [], "phantom_backup_dirs": [],
            "chosen_departments": [], "chosen_departments_source": "none",
        }

    if core_answers is None:
        core_answers = read_core_answers(build_state, departments_dir)

    mand = mandatory_ids(nm)
    declined = declined_set(build_state)
    universal_primaries = universal_primary_vertical_departments(nm)
    matched_verticals = matched_vertical_pack_departments(nm, core_answers)
    present = departments_on_disk(departments_dir)

    expected_mand = [c for c in mand if _norm(c) not in declined]
    # Floor gate: only the universal primaries (one per pack, not all keyword-matched extras).
    expected_universal_primary = [v for v in universal_primaries if _norm(v) not in declined]
    expected_floor = expected_mand + expected_universal_primary

    missing_mandatory = [c for c in expected_mand if not _present(c, present)]
    missing_universal_primary = [v for v in expected_universal_primary if not _present(v, present)]

    floor_met = (not missing_mandatory) and (not missing_universal_primary)
    rc = 0 if floor_met else 3

    # Reason string uses the live computed floor count - never a hardcoded integer.
    _expected_floor_count = len(expected_mand) + len(expected_universal_primary)
    reason = (
        f"floor met ({_expected_floor_count}-department standard: "
        f"{len(mand)} mandatory + {len(universal_primaries)} universal-primary-vertical"
        f" − {len(declined)} declined)"
    )
    if not floor_met:
        bits = []
        if missing_mandatory:
            bits.append("missing mandatory: " + ", ".join(missing_mandatory))
        if missing_universal_primary:
            bits.append("missing universal-primary vertical: " + ", ".join(missing_universal_primary))
        reason = " | ".join(bits)

    # C5: surface phantom-duplicate trees + backup dirs in the verdict. INFORMATIONAL
    # here (does NOT change the floor rc contract 0/3/7); the dedicated
    # `--check-collisions` gate returns rc=5 on these so callers opt in explicitly,
    # and qc-assert-workspace-departments-built.sh FAILS on them (AF-PHANTOM-DEPT-TREE).
    slug_collisions = sibling_slug_collisions(departments_dir, nm)
    phantom_backup_dirs = _raw_department_dirs(departments_dir)[1]

    # C7: the durable chosen-list, read authoritatively (build-state, then the
    # <company>/departments.json artifact). INFORMATIONAL — never changes the floor
    # rc and never fabricated: [] / "none" when the client's choice was never
    # persisted (an OLD build that predates the durable artifact).
    chosen, chosen_source = read_chosen_departments(build_state, departments_dir)

    return {
        "rc": rc,
        "departments_dir": str(departments_dir),
        "mandatory": mand,
        "declined": sorted(declined),
        "universal_primary_vertical": universal_primaries,
        "matched_vertical_departments": matched_verticals,
        "expected_floor": expected_floor,
        "expected_floor_count": len(expected_floor),
        "on_disk_count": len(present),
        "missing_mandatory": missing_mandatory,
        "missing_universal_primary": missing_universal_primary,
        "slug_collisions": slug_collisions,
        "phantom_backup_dirs": phantom_backup_dirs,
        "chosen_departments": chosen,
        "chosen_departments_source": chosen_source,
        "floor_met": floor_met,
        "reason": reason,
    }


def main(argv):
    as_json = "--json" in argv
    # Allow an explicit --departments-dir for the smoke test.
    dd = None
    for i, a in enumerate(argv):
        if a == "--departments-dir" and i + 1 < len(argv):
            dd = Path(argv[i + 1])

    # C5 gate: --check-collisions FAILs (rc=5) when phantom-duplicate dept trees
    # (two sibling dirs resolving to the same canonical slug) OR phantom '.bak'
    # dept dirs are present on disk. Separate from the floor rc (0/3/7) so a caller
    # opts into the collision gate explicitly. rc=7 when no departments dir resolves.
    if "--check-collisions" in argv:
        dd_resolved = dd or resolve_departments_dir()
        if dd_resolved is None:
            report = {"rc": 7, "departments_dir": None, "slug_collisions": [],
                      "phantom_backup_dirs": [],
                      "reason": "no workforce / cannot resolve departments dir on disk"}
            if as_json:
                print(json.dumps(report, indent=2))
            else:
                print("department-floor.py --check-collisions: no departments dir on disk (rc=7)",
                      file=sys.stderr)
            return 7
        collisions = sibling_slug_collisions(dd_resolved)
        backups = _raw_department_dirs(dd_resolved)[1]
        rc = 5 if (collisions or backups) else 0
        report = {
            "rc": rc,
            "departments_dir": str(dd_resolved),
            "slug_collisions": collisions,
            "phantom_backup_dirs": backups,
            "reason": ("phantom duplicate dept trees present" if collisions or backups
                       else "no phantom duplicate dept trees"),
        }
        if as_json:
            print(json.dumps(report, indent=2))
        else:
            print("============================================", file=sys.stderr)
            print(f"department-floor.py --check-collisions ({report['departments_dir']})", file=sys.stderr)
            for g in collisions:
                print(f"  COLLISION: canonical '{g['canonical']}' materialized as "
                      f"{len(g['dirs'])} sibling dirs: {', '.join(g['dirs'])}", file=sys.stderr)
            for b in backups:
                print(f"  PHANTOM BACKUP DIR: {b} (must be moved OUT of departments/)", file=sys.stderr)
            print(f"RESULT: {'PHANTOM TREES PRESENT' if rc else 'CLEAN'} (rc={rc})", file=sys.stderr)
        return rc

    verdict = evaluate_floor(departments_dir=dd)
    if as_json:
        print(json.dumps(verdict, indent=2))
    else:
        _floor_label = (
            f"{verdict['expected_floor_count']}-department standard"
            f" ({len(verdict['mandatory'])} mandatory"
            f" + {len(verdict['universal_primary_vertical'])} universal-primary-vertical"
            f" − {len(verdict['declined'])} declined)"
        )
        print("============================================", file=sys.stderr)
        print(f"department-floor.py - HARD floor verdict ({_floor_label})", file=sys.stderr)
        print(f"departments_dir = {verdict['departments_dir']}", file=sys.stderr)
        print(f"expected floor  = {verdict['expected_floor_count']} "
              f"({len(verdict['mandatory'])} mandatory "
              f"+ {len(verdict['universal_primary_vertical'])} universal-primary-vertical "
              f"− {len(verdict['declined'])} declined)", file=sys.stderr)
        print(f"on disk         = {verdict['on_disk_count']} departments", file=sys.stderr)
        if verdict["missing_mandatory"]:
            print(f"MISSING mandatory         : {', '.join(verdict['missing_mandatory'])}", file=sys.stderr)
        if verdict["missing_universal_primary"]:
            print(f"MISSING universal-primary : {', '.join(verdict['missing_universal_primary'])}", file=sys.stderr)
        print(f"RESULT: {'FLOOR MET' if verdict['floor_met'] else 'FLOOR NOT MET'} "
              f"(rc={verdict['rc']})", file=sys.stderr)
    return verdict["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
