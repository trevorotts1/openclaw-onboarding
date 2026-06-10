#!/usr/bin/env python3
"""
populate-sops-from-manifest.py — v9.6.2

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

EXIT CODES:
  0 = all SOPs populated, all sub-agents reported success
  1 = manifest missing or malformed
  2 = one or more sub-agents failed (manifest unchanged, can re-run)
  3 = no models available (selector returned Tier 5 owner-input-required)
  4 = inline-queue mode: work files were WRITTEN but SOPs are NOT yet authored.
      This is NOT success. Returning 0 here was the "write a work file and hope"
      terminal-state lie that let the library gate pass with empty SOPs. The
      caller MUST keep sopLibraryStatus=authoring and let the resume cron
      re-fire until the substance gate (verify-library-gate.sh) actually passes.
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

    # 2. Resolve model once (all depts use heavy tier)
    model_id = resolve_model("workforce-sop-writer", "heavy")
    if model_id is None:
        print("[POPULATE-SOPS] Selector returned Tier 5 (owner-input-required). "
              "Run select_model.py --format prompt to see the prompt.", file=sys.stderr)
        return 3

    print(f"[POPULATE-SOPS] Model: {model_id} | parallel cap: {max_parallel} | timeout: {args.timeout}s", file=sys.stderr)

    use_openclaw = openclaw_available()
    print(f"[POPULATE-SOPS] Spawn mode: {'openclaw subagents' if use_openclaw else 'inline queue files'}",
          file=sys.stderr)

    # 3. Spawn (batched up to max_parallel at a time)
    failures = []
    processes_inflight = []

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
        # Throttle
        while len(processes_inflight) >= max_parallel:
            reap()
            if len(processes_inflight) >= max_parallel:
                import time
                time.sleep(2)

        prompt = build_subagent_prompt(entry, instructions, model_id)

        if args.dry_run:
            print(f"[POPULATE-SOPS] DRY RUN — dept {entry['dept_id']} would get {len(entry['sop_files'])} SOPs populated")
            continue

        if use_openclaw:
            try:
                p = spawn_via_openclaw(entry, prompt, model_id, args.timeout)
                processes_inflight.append((p, entry["dept_id"]))
            except Exception as e:
                print(f"[POPULATE-SOPS] Spawn error for {entry['dept_id']}: {e}", file=sys.stderr)
                failures.append((entry["dept_id"], -1, str(e)))
        else:
            spawn_inline(entry, prompt, model_id, args.timeout, dry_run=args.dry_run)

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

    if not use_openclaw:
        # v10.15.18: inline mode only WROTE work files — it did NOT author any
        # SOPs. Returning 0 here used to mark the SOP library "done" and let the
        # gate pass on empty files (the Sheila/Evelyn-stub failure). We now
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
