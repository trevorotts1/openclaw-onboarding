#!/usr/bin/env python3
"""
populate-sops-from-manifest.py — v9.7.0 (PRD 2.12 boundary gate)

Reads sop-research-manifest.json (written by build-workforce.py) and spawns
parallel sub-agents to populate the SOP stubs with real DMAIC content.

The manifest lists every SOP file that needs population. Each entry has the
department's interview context (company name, industry, KPIs, tools,
challenges, role). This script either:

  (a) Spawns native OpenClaw sub-agents via `openclaw subagents spawn` if
      that CLI is available — one sub-agent per department, capped at the
      manifest's `max_parallel_sub_agents` (default 10).
  (b) Falls back to local in-process generation by calling the heavy-tier
      model directly through `select_model.py` if the openclaw CLI sub-agent
      command isn't available.

Either way, the result is the same: each role's SOP files get rewritten in
place, replacing the `[Step 1 - to be personalized]` placeholders with real
DMAIC-structured content derived from Perplexity research + the dept's
interview answers + the role's assigned persona.

PRD 2.12 — BOUNDARY GATE (token-economics protection):
  Before processing any department the script checks sop-boundary-gate.py to
  determine whether the dept is canonical (has a pre-written role-library
  template).  If it is canonical this script REFUSES to author SOPs for it —
  it logs a loud [SOP-BOUNDARY-GATE] REFUSE line and skips that dept.
  Canonical depts must be resolved via _instantiate_role_from_library() in
  build-workforce.py (copy + token-personalise), NEVER via LLM authoring.
  If the entire manifest consists of canonical depts (no custom depts remain),
  the script exits 0 — all work was already done by the copy path.

EXIT CODES:
  0 = all SOPs populated (openclaw sub-agents success), OR manifest contained
      only canonical depts that were already handled by the copy path
  1 = manifest missing or malformed
  2 = one or more sub-agents failed (manifest unchanged, can re-run)
  3 = no models available (selector returned Tier 5 owner-input-required)
  4 = inline-queue mode: work files were WRITTEN but SOPs are NOT yet authored.
      This is NOT success. Returning 0 here was the "write a work file and hope"
      terminal-state lie that let the library gate pass with empty SOPs. The
      caller MUST keep sopLibraryStatus=authoring and let the resume cron
      re-fire until the substance gate (verify-library-gate.sh) actually passes.
  7 = BOUNDARY GATE FAIL: manifest contains canonical dept(s) that were not
      handled by the library copy path. build-workforce.py must be re-run to
      instantiate those depts from the role-library before authoring.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ─── PRD 2.12: canonical boundary gate ───────────────────────────────────────
# Import sop-boundary-gate from the scripts/ directory (same folder as this file).
_BG_DIR = os.path.dirname(os.path.abspath(__file__))
if _BG_DIR not in sys.path:
    sys.path.insert(0, _BG_DIR)
try:
    from sop_boundary_gate import (  # type: ignore
        is_canonical_dept as _is_canonical_dept,
        assert_no_canonical_in_authoring_path as _assert_no_canonical,
        CANONICAL_LIBRARY_DEPT_IDS as _CANONICAL_DEPT_IDS,
    )
    _BOUNDARY_GATE_AVAILABLE = True
except ImportError as _bg_err:
    _BOUNDARY_GATE_AVAILABLE = False
    print(
        f"[SOP-BOUNDARY-GATE] WARNING: could not import sop-boundary-gate ({_bg_err}). "
        f"Boundary gate is DISABLED — canonical depts may enter the authoring path. "
        f"This is a token-economics risk. Ensure sop-boundary-gate.py is present in {_BG_DIR}.",
        file=sys.stderr,
    )
    def _is_canonical_dept(dept_id): return False  # type: ignore  # noqa: E302
    def _assert_no_canonical(manifest_path): return 0  # type: ignore  # noqa: E302
    _CANONICAL_DEPT_IDS = frozenset()  # type: ignore


# ─── PATHS (PRD 1.9: canonical root from get_openclaw_paths()) ────────────────

HOME = Path.home()

# Build the ZHC search roots: canonical root first, legacy roots for backward compat.
def _build_zhc_roots() -> list:
    """Return ZHC root candidates — canonical root first (PRD 1.9)."""
    _su = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared-utils")
    sys.path.insert(0, os.path.realpath(_su))
    roots = []
    try:
        from detect_platform import get_openclaw_paths as _gop
        roots.append(_gop()["company_root"])
    except Exception:
        pass
    roots.extend([
        HOME / "clawd" / "zero-human-company",
        HOME / "clawd" / "zhc",
        Path(os.path.expanduser("~/clawd/zero-human-company")),
        Path(os.path.expanduser("~/clawd/zhc")),
    ])
    return roots

ZHC_SEARCH_ROOTS = _build_zhc_roots()

SELECTOR_CANDIDATES = [
    HOME / "Downloads" / "openclaw-master-files" / "shared-utils" / "select_model.py",
    Path(os.path.expanduser("~/Downloads/openclaw-master-files/shared-utils/select_model.py")),  # PRD item 1.7
]


# ─── MANIFEST DISCOVERY ───────────────────────────────────────────────────────

def find_manifest(explicit_path=None):
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return p
    for root in ZHC_SEARCH_ROOTS:
        if root.is_dir():
            for entry in sorted(root.iterdir()):
                manifest = entry / "sop-research-manifest.json"
                if manifest.exists():
                    return manifest
    return None


# ─── MODEL SELECTION ──────────────────────────────────────────────────────────

def selector_path():
    for c in SELECTOR_CANDIDATES:
        if c.is_file():
            return c
    return None


def resolve_model(skill, purpose_tier="heavy", input_chars=None):
    """Call select_model.py and return model_id, or None if owner-input."""
    sel = selector_path()
    if not sel:
        return "ollama/kimi-k2.6:cloud"  # safe default
    cmd = ["python3", str(sel), "--skill", skill, "--purpose-tier", purpose_tier, "--format", "id"]
    if input_chars is not None:
        cmd.extend(["--input-chars", str(input_chars)])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        mid = r.stdout.strip()
        if mid and "anthropic/" not in mid.lower() and "claude-" not in mid.lower():
            return mid
        if r.returncode == 2:
            return None  # Tier 5 — owner input required
    except Exception as e:
        print(f"[POPULATE-SOPS] Selector error: {e}", file=sys.stderr)
    return "ollama/kimi-k2.6:cloud"


# ─── SUB-AGENT SPAWN ──────────────────────────────────────────────────────────

# v10.15.5: 6-location resolver for the openclaw binary. shutil.which("openclaw")
# alone fails on macOS non-interactive subprocesses (PATH doesn't include
# /opt/homebrew/bin without a login shell) and on VPS containers (different
# canonical paths). Cache the resolution at module load.
def find_openclaw():
    explicit = os.environ.get("OPENCLAW_BIN")
    if explicit and os.access(explicit, os.X_OK):
        return explicit
    candidates = [
        shutil.which("openclaw"),
        "/opt/homebrew/bin/openclaw",
        "/usr/local/bin/openclaw",
        str(Path.home() / ".openclaw" / "bin" / "openclaw"),
        "/data/.npm-global/bin/openclaw",
        "/data/linuxbrew/.linuxbrew/bin/openclaw",
    ]
    for cand in candidates:
        if cand and os.access(cand, os.X_OK):
            return cand
    return None


_OPENCLAW_BIN = find_openclaw()


def openclaw_available():
    """Check if `openclaw subagents spawn` is available."""
    if not _OPENCLAW_BIN:
        return False
    try:
        r = subprocess.run([_OPENCLAW_BIN, "subagents", "--help"],
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def build_subagent_prompt(dept_entry, sub_agent_instructions, model_id):
    """Fill the manifest's instruction template with dept-specific values."""
    return sub_agent_instructions.format(
        DEPT_NAME=dept_entry["dept_name"],
        COMPANY_NAME=dept_entry["company_name"],
        INDUSTRY=dept_entry["industry"] or "unspecified industry",
        DEPT_KPIS=dept_entry["department_kpis"] or "(see dept SOUL.md)",
        DEPT_TOOLS=dept_entry["department_tools"] or "(see dept TOOLS.md)",
        DEPT_HEAD=dept_entry["dept_head"],
        DEPT_DIR=dept_entry["dept_dir"],
    )


def spawn_via_openclaw(dept_entry, prompt, model_id, timeout):
    """Use openclaw CLI sub-agent spawn (preferred path).

    v10.15.5: uses the resolved absolute path from find_openclaw() so the
    subprocess does not depend on the spawning shell's PATH.
    """
    bin_path = _OPENCLAW_BIN or "openclaw"
    cmd = [
        bin_path, "subagents", "spawn",
        "--model", model_id,
        "--purpose-tier", "heavy",
        "--timeout-seconds", str(timeout),
        "--prompt", prompt,
        "--label", f"sop-writer-{dept_entry['dept_id']}",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def spawn_inline(dept_entry, prompt, model_id, timeout, dry_run=False):
    """
    Fallback: write the prompt + context to a per-dept work file and let the
    AI agent (the one running this script) pick it up. Used when the openclaw
    CLI sub-agent command isn't available.
    """
    work_dir = Path(dept_entry["dept_dir"]) / ".sop-write-queue"
    work_dir.mkdir(parents=True, exist_ok=True)
    work_file = work_dir / f"sop-work-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"

    body = f"""# SOP Write Job — {dept_entry['dept_name']} Department

**Status:** PENDING — pick this up and execute the instructions below.
**Model to use:** `{model_id}` (heavy tier; never Anthropic).
**Timeout budget:** {timeout} seconds.
**Dept dir:** `{dept_entry['dept_dir']}`
**SOP files to populate ({len(dept_entry['sop_files'])} files):**
""" + "\n".join(f"  - {sf['role_folder']}/{sf['sop_file']}" for sf in dept_entry["sop_files"]) + f"""

---

## Instructions

{prompt}

---

## When done

1. Mark this file's Status line as: `**Status:** COMPLETE — populated {{N}} SOPs at {{timestamp}}`
2. Append a one-line summary per SOP populated:
   - `- {{role_folder}}/{{sop_file}}: {{line_count}} lines, {{N}} DMAIC sections present`
3. Move this file to: `{work_dir}/done/`
"""
    if dry_run:
        print(f"[POPULATE-SOPS] DRY RUN — would write {work_file}")
        return None
    work_file.write_text(body)
    print(f"[POPULATE-SOPS] Queued: {work_file}", file=sys.stderr)
    return work_file


# ─── ALREADY-AUTHORED SUBSTANCE SKIP (FURNACE GUARD) ──────────────────────────
# A resume fire re-runs this script. Without a skip, EVERY custom dept gets a fresh
# heavy-tier authoring sub-agent (1800s each) on every fire even when its SOPs are
# already written — the SOP furnace. Mirror the on-disk substance check the resume
# cron already trusts (resume-workforce-build.sh:442,476-479: a how-to.md only
# counts as real when it is >= HOW_TO_MIN bytes AND contains no "[PENDING" marker).
# A dept whose SOP files already clear that bar is skipped — no sub-agent spawned.
SOP_SUBSTANCE_MIN = 256  # bytes — mirrors HOW_TO_MIN in resume-workforce-build.sh:442
# Placeholder markers that prove a SOP file is still a stub (the authoring step
# replaces "[Step 1 - to be personalized]" / "[PENDING ...]" with real DMAIC content).
_SOP_PLACEHOLDER_MARKERS = ("[PENDING", "to be personalized", "[Step 1 -")


def _sop_path_for(entry, sf):
    """Resolve a single SOP file's on-disk path from a manifest sop_files item.
    Prefers the absolute role_dir written by build-workforce.py; falls back to
    dept_dir/role_folder."""
    sop_file = sf.get("sop_file", "")
    if not sop_file:
        return None
    role_dir = sf.get("role_dir", "")
    if role_dir:
        return Path(role_dir) / sop_file
    role_folder = sf.get("role_folder", "")
    base = Path(entry.get("dept_dir", ""))
    return (base / role_folder / sop_file) if role_folder else (base / sop_file)


def dept_already_authored(entry):
    """True iff EVERY SOP file for this dept already exists on disk with real
    substance (>= SOP_SUBSTANCE_MIN bytes AND no placeholder markers). Used to
    skip re-spawning the authoring sub-agent on a resume re-fire (furnace guard).
    Conservative: any missing / undersized / stub file → False (author it)."""
    sop_files = entry.get("sop_files", [])
    if not sop_files:
        # No stub files queued → nothing for the authoring path to write; treat as
        # already-handled so we don't spawn a sub-agent with no work.
        return True
    for sf in sop_files:
        path = _sop_path_for(entry, sf)
        if path is None:
            return False
        try:
            if not path.is_file() or path.stat().st_size < SOP_SUBSTANCE_MIN:
                return False
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return False
        if any(marker in content for marker in _SOP_PLACEHOLDER_MARKERS):
            return False
    return True


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Populate Skill 23 SOP stubs from the research manifest.")
    parser.add_argument("--manifest", default=None, help="Path to sop-research-manifest.json")
    parser.add_argument("--dry-run", action="store_true", help="Don't spawn; just print what would happen")
    parser.add_argument("--max-parallel", type=int, default=None, help="Override manifest's max_parallel_sub_agents")
    parser.add_argument("--timeout", type=int, default=1800, help="Sub-agent timeout in seconds (default 1800 / 30 min)")
    args = parser.parse_args()

    # 1. Find manifest
    manifest_path = find_manifest(args.manifest)
    if not manifest_path:
        print("[POPULATE-SOPS] ERROR: No sop-research-manifest.json found in any ZHC folder.", file=sys.stderr)
        print("  Looked in:", file=sys.stderr)
        for r in ZHC_SEARCH_ROOTS:
            print(f"    {r}", file=sys.stderr)
        return 1

    print(f"[POPULATE-SOPS] Manifest: {manifest_path}", file=sys.stderr)
    with open(manifest_path) as f:
        manifest = json.load(f)

    depts = manifest.get("departments", [])
    if not depts:
        print("[POPULATE-SOPS] ERROR: Manifest has no departments. Has the interview run?", file=sys.stderr)
        return 1

    instructions = manifest.get("sub_agent_instructions", "")
    if not instructions:
        print("[POPULATE-SOPS] ERROR: Manifest missing sub_agent_instructions template.", file=sys.stderr)
        return 1

    max_parallel = args.max_parallel or manifest.get("max_parallel_sub_agents", 10)
    company_name = manifest.get("company", "the company")

    # 2. PRD 2.12 — BOUNDARY GATE: assert no canonical dept in authoring manifest.
    # This is a hard check BEFORE any model resolution or sub-agent spawn.
    # canonical depts MUST be handled by the copy path in build-workforce.py;
    # if they appear here something went wrong upstream (library lookup failed
    # or was skipped).  We filter them OUT and log loudly — never author them.
    if _BOUNDARY_GATE_AVAILABLE:
        boundary_rc = _assert_no_canonical(manifest_path)
        if boundary_rc == 7:
            # Violation found — filter canonical depts from the processing list
            # and continue only with custom depts.  If no custom depts remain,
            # that is actually a PASS (all work was done by the copy path).
            canonical_filtered = [e for e in depts if _is_canonical_dept(e.get("dept_id", ""))]
            custom_depts = [e for e in depts if not _is_canonical_dept(e.get("dept_id", ""))]
            print(
                f"[SOP-BOUNDARY-GATE] FILTERED {len(canonical_filtered)} canonical dept(s) "
                f"from authoring manifest. These must be re-run through build-workforce.py "
                f"(library copy path) to get their SOPs — authoring is REFUSED:",
                file=sys.stderr,
            )
            for e in canonical_filtered:
                print(f"  REFUSE: {e.get('dept_id')} ({len(e.get('sop_files', []))} SOP stubs queued — skipped)", file=sys.stderr)
            depts = custom_depts
            if not depts:
                print(
                    f"[POPULATE-SOPS] Manifest contained only canonical depts (all handled by "
                    f"the role-library copy path). Nothing to author. Exiting 0.",
                    file=sys.stderr,
                )
                return 0
            print(
                f"[POPULATE-SOPS] Continuing with {len(depts)} custom dept(s) eligible for authoring.",
                file=sys.stderr,
            )
        else:
            print(
                f"[SOP-BOUNDARY-GATE] Boundary check PASS — {len(depts)} dept(s) in manifest "
                f"are custom (no canonical depts found; library copy path handled canonical work).",
                file=sys.stderr,
            )
    else:
        print(
            f"[SOP-BOUNDARY-GATE] Boundary gate DISABLED — proceeding without canonical check "
            f"(token-economics risk; install sop-boundary-gate.py to enable).",
            file=sys.stderr,
        )

    # 3. Resolve model once (all depts use heavy tier)
    model_id = resolve_model("workforce-sop-writer", "heavy")
    if model_id is None:
        print("[POPULATE-SOPS] Selector returned Tier 5 (owner-input-required). "
              "Run select_model.py --format prompt to see the prompt.", file=sys.stderr)
        return 3

    print(f"[POPULATE-SOPS] Model: {model_id} | parallel cap: {max_parallel} | timeout: {args.timeout}s", file=sys.stderr)

    use_openclaw = openclaw_available()
    print(f"[POPULATE-SOPS] Spawn mode: {'openclaw subagents' if use_openclaw else 'inline queue files'}",
          file=sys.stderr)

    # 4. Spawn (batched up to max_parallel at a time)
    failures = []
    processes_inflight = []
    authored_skips = 0   # depts whose SOPs are already substantive on disk (furnace guard)
    dispatched = 0       # depts actually spawned/queued this run

    def reap():
        nonlocal processes_inflight
        still = []
        for p, dept_id in processes_inflight:
            rc = p.poll()
            if rc is None:
                still.append((p, dept_id))
            elif rc != 0:
                err = p.stderr.read().decode("utf-8", errors="ignore") if p.stderr else ""
                failures.append((dept_id, rc, err[:500]))
                print(f"[POPULATE-SOPS] FAIL {dept_id} rc={rc}: {err[:200]}", file=sys.stderr)
            else:
                print(f"[POPULATE-SOPS] DONE {dept_id}", file=sys.stderr)
        processes_inflight = still

    for entry in depts:
        dept_id = entry.get("dept_id", "")

        # PRD 2.12 per-dept REFUSE: belt-and-suspenders check inside the loop.
        # Even if the manifest-level check above passed, guard each individual
        # dept in case the depts list was modified externally.
        if _BOUNDARY_GATE_AVAILABLE and _is_canonical_dept(dept_id):
            print(
                f"[SOP-BOUNDARY-GATE] REFUSE authoring for canonical dept '{dept_id}' "
                f"(per-loop guard). SOPs must be copied from the role-library, not authored. "
                f"Skipping.",
                file=sys.stderr,
            )
            continue

        # FURNACE GUARD: skip depts whose SOPs are already authored on disk. On a
        # resume re-fire this is what stops a fresh 1800s heavy-tier sub-agent from
        # re-authoring a dept that is already done. --dry-run still reports the skip.
        if dept_already_authored(entry):
            authored_skips += 1
            print(
                f"[POPULATE-SOPS] SKIP {dept_id}: all {len(entry.get('sop_files', []))} SOP file(s) "
                f"already authored on disk (>= {SOP_SUBSTANCE_MIN}B, no placeholders). "
                f"NOT spawning the authoring sub-agent (resume idempotency / furnace guard).",
                file=sys.stderr,
            )
            continue

        # Throttle
        while len(processes_inflight) >= max_parallel:
            reap()
            if len(processes_inflight) >= max_parallel:
                import time
                time.sleep(2)

        prompt = build_subagent_prompt(entry, instructions, model_id)

        if args.dry_run:
            print(f"[POPULATE-SOPS] DRY RUN — dept {dept_id} would get {len(entry['sop_files'])} SOPs populated")
            continue

        if use_openclaw:
            try:
                p = spawn_via_openclaw(entry, prompt, model_id, args.timeout)
                processes_inflight.append((p, dept_id))
                dispatched += 1
            except Exception as e:
                print(f"[POPULATE-SOPS] Spawn error for {dept_id}: {e}", file=sys.stderr)
                failures.append((dept_id, -1, str(e)))
        else:
            spawn_inline(entry, prompt, model_id, args.timeout, dry_run=args.dry_run)
            dispatched += 1

    # Drain remaining
    while processes_inflight:
        reap()
        if processes_inflight:
            import time
            time.sleep(5)

    # 4. Summary
    total = len(depts)
    if failures:
        print(f"\n[POPULATE-SOPS] {total - len(failures)}/{total} departments succeeded; {len(failures)} failed.",
              file=sys.stderr)
        for dept_id, rc, err in failures:
            print(f"  FAIL: {dept_id} (rc={rc})", file=sys.stderr)
        return 2

    # FURNACE GUARD: if every eligible dept was already authored on disk (nothing
    # actually dispatched this run), there is no pending work — return 0 instead of
    # the inline rc=4 "queued-not-authored". A resume that finds the SOPs already
    # substantive must NOT keep the library stuck at 'authoring' forever.
    if dispatched == 0:
        print(
            f"\n[POPULATE-SOPS] {total} custom dept(s) in manifest; {authored_skips} already "
            f"authored on disk, 0 dispatched. SOP substance already present — nothing to author. "
            f"Exiting 0.",
            file=sys.stderr,
        )
        return 0

    if not use_openclaw:
        # v10.15.18: inline mode only WROTE work files — it did NOT author any
        # SOPs. Returning 0 here used to mark the SOP library "done" and let the
        # gate pass on empty files (the empty-file/stub failure). We now
        # return 4 = "queued, NOT authored" so the caller keeps the status at
        # authoring and the resume cron re-fires until verify-library-gate.sh
        # confirms real, substantive SOPs on disk.
        print(f"\n[POPULATE-SOPS] {total} departments QUEUED via inline work files — but NO SOPs are "
              f"authored yet. The AI agent running this install MUST pick up each dept's "
              f".sop-write-queue/ folder and write the real DMAIC SOPs. Returning rc=4 "
              f"(queued-not-authored): the SOP library is NOT done until the substance gate passes.",
              file=sys.stderr)
        return 4

    print(f"\n[POPULATE-SOPS] All {total} departments completed (openclaw sub-agents reported success).",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
