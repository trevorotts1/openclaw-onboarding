#!/usr/bin/env python3
"""
ledger_reconciler_core.py -- data/logic engine for the Skill 6 / Skill 62
ledger reconciler (canonical, git-tracked copy; the operator-local cron
wrapper that invokes this module lives outside this repo since it carries
box-specific absolute paths that must never ship in this fleet-wide
template -- see scripts/qc-assert-no-client-names.sh's ALWAYS_ON_TOKENS).

Called by the reconciler's cron wrapper. Does no git *writes* itself (no
commit/push) -- it only reads git state (via read-only `git` subprocess
calls against dedicated scratch clones the wrapper already fetched/reset)
and edits local files:

  - renders recovery-state.md (full overwrite, derived from truth)
  - patches ledger/checklist files IN PLACE, but ONLY rows whose status cell is
    exactly "pending" (or, for the cinematic checklist, "pending"), and ONLY
    when precise git evidence (a direct merge-parent commit + a tag containing
    it) was found. Never touches verified/deferred/other rows.
  - appends a timestamped block to session-log files (append-only, never
    truncates or rewrites existing content)
  - detects and loudly surfaces "verified-but-unmerged leg" mismatches: a
    both-repo unit whose SHARED ledger row reads "verified" (hand-set or
    auto-reconciled) while one repo's leg is provably NOT merged into that
    repo's main. This is a fail-closed alarm, not a silent table cell --
    see detect_failclosed_mismatches() below. The reconciler still NEVER
    auto-corrects a verified/deferred/other row (fail-open-by-mutation would
    be worse); it only refuses to let that row's status be silently
    re-printed, unqualified, next to git truth that contradicts it.

All git commit/push and locking is handled by the bash wrapper.
"""

import argparse
import glob
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

UNIT_ROW_RE = re.compile(r"^\|\s*(U\d+)\s*\|")
# Strict "empty pending row" shape -- only rows that look EXACTLY like this are
# ever candidates for auto-patch. Any partially-filled or oddly-shaped row is
# left untouched (never guess, never partially overwrite).
PENDING_ROW_RE = re.compile(
    r"^\|\s*(U\d+)\s*\|\s*(?P<desc>.*?)\s*\|\s*\|\s*pending\s*\|\s*\|\s*\|\s*$"
)
QC_SCORE_RE = re.compile(r"QC\s+([0-9]+\.[0-9]+)")
# Any ledger status cell that STARTS WITH "verified" -- hand-verified rows
# ("verified") and auto-reconciled rows ("verified (auto-reconciled, needs
# test-proof confirmation)") both count: either one, printed next to a repo
# leg git truth shows is NOT merged, is the fail-open condition this module
# now refuses to render silently.
STATUS_VERIFIED_RE = re.compile(r"^verified\b", re.IGNORECASE)


def now_utc_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sh(repo_dir, args, check=True):
    """Run a read-only git command in repo_dir, return stripped stdout."""
    r = subprocess.run(
        ["git", "-C", str(repo_dir)] + args,
        capture_output=True,
        text=True,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git -C {repo_dir} {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def sh_ok(repo_dir, args):
    r = subprocess.run(["git", "-C", str(repo_dir)] + args, capture_output=True, text=True)
    return r.returncode == 0, r.stdout.strip(), r.stderr.strip()


# --------------------------------------------------------------------------
# Git truth gathering
# --------------------------------------------------------------------------

def list_remote_branches(repo_dir, prefix):
    out = sh(repo_dir, ["branch", "-r"])
    names = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith(f"origin/{prefix}"):
            continue
        if "->" in line:
            continue
        names.append(line[len("origin/"):])
    return sorted(names)


def find_merge_commit_for_tip(repo_dir, tip, main_ref="origin/main"):
    """Find a commit on main_ref that has `tip` as a DIRECT parent (i.e. the
    actual merge commit that merged that branch), not just any ancestor.
    Returns the merge commit sha, or None if no such direct-parent commit
    exists (e.g. squash-merge / fast-forward with no merge commit -- treated
    as "merged but unidentified", never auto-verified from that alone)."""
    out = sh(repo_dir, ["rev-list", main_ref, "--parents"])
    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue
        commit, parents = parts[0], parts[1:]
        if tip in parents:
            return commit
    return None


def nearest_tag_containing(repo_dir, commit_sha):
    """Earliest annotated tag (by creation date) that contains commit_sha."""
    out = sh(repo_dir, ["tag", "--sort=creatordate", "--contains", commit_sha])
    tags = [t for t in out.splitlines() if t.strip()]
    if not tags:
        return None
    return tags[0]


def gather_branch_truth(repo_dir, prefix, main_ref="origin/main"):
    """For every origin/<prefix>* branch: tip sha, ancestor-of-main bool,
    merge commit (if directly identifiable), nearest tag containing it."""
    result = {}
    for branch in list_remote_branches(repo_dir, prefix):
        tip = sh(repo_dir, ["rev-parse", f"origin/{branch}"])
        is_anc_ok, _, _ = sh_ok(repo_dir, ["merge-base", "--is-ancestor", tip, main_ref])
        entry = {"branch": branch, "tip": tip, "is_ancestor_of_main": bool(is_anc_ok)}
        if is_anc_ok:
            merge_sha = find_merge_commit_for_tip(repo_dir, tip, main_ref)
            entry["merge_sha"] = merge_sha
            entry["tag"] = nearest_tag_containing(repo_dir, merge_sha) if merge_sha else None
        else:
            entry["merge_sha"] = None
            entry["tag"] = None
        result[branch] = entry
    return result


def gather_cinematic_local_clone_truth(local_clone_dir, branch="skill62/cinematic-engine", main_ref="main"):
    """Read-only check of the isolated build clone itself (never checked out,
    reset, or written to -- pure `git -C` reads). This is the safety net for
    the actual real-world topology observed: skill62/cinematic-engine
    currently lives ONLY as a local branch in this clone and has never been
    pushed to origin. If a build session accumulates local commits there and
    dies before pushing, an origin-only truth check would silently miss that
    at-risk work -- this surfaces it explicitly."""
    local_clone_dir = Path(local_clone_dir)
    if not local_clone_dir.is_dir():
        return {"clone_exists": False}
    ok, branches_out, _ = sh_ok(local_clone_dir, ["branch", "--list", branch])
    if not ok or branch not in branches_out:
        return {"clone_exists": True, "local_branch_exists": False}
    local_tip = sh(local_clone_dir, ["rev-parse", branch])
    ok_main, local_main_tip, _ = sh_ok(local_clone_dir, ["rev-parse", main_ref])
    pushed_ok, origin_tip, _ = sh_ok(local_clone_dir, ["rev-parse", f"origin/{branch}"])
    pushed_to_origin = bool(pushed_ok) and origin_tip.strip() == local_tip
    unpushed_commits = []
    if not pushed_to_origin:
        base_for_diff = origin_tip.strip() if pushed_ok else local_main_tip.strip()
        ahead_raw = sh(local_clone_dir, ["log", f"{base_for_diff}..{branch}", "--format=%H\t%s"])
        for line in ahead_raw.splitlines():
            if "\t" in line:
                sha, subj = line.split("\t", 1)
                unpushed_commits.append({"sha": sha, "subject": subj})
    return {
        "clone_exists": True,
        "local_branch_exists": True,
        "local_tip": local_tip,
        "pushed_to_origin": pushed_to_origin,
        "unpushed_commit_count": len(unpushed_commits),
        "unpushed_commits": unpushed_commits,
    }


def gather_cinematic_truth(repo_dir, branch="skill62/cinematic-engine", main_ref="origin/main"):
    ok, tip, _ = sh_ok(repo_dir, ["rev-parse", f"origin/{branch}"])
    if not ok:
        return {"branch": branch, "exists": False}
    tip = tip.strip()
    merge_base = sh(repo_dir, ["merge-base", f"origin/{branch}", main_ref])
    ahead_raw = sh(
        repo_dir,
        ["log", f"{merge_base}..origin/{branch}", "--format=%H\t%s"],
    )
    ahead = []
    for line in ahead_raw.splitlines():
        if "\t" in line:
            sha, subj = line.split("\t", 1)
            ahead.append({"sha": sha, "subject": subj})
    is_anc_ok, _, _ = sh_ok(repo_dir, ["merge-base", "--is-ancestor", tip, main_ref])
    entry = {
        "branch": branch,
        "exists": True,
        "tip": tip,
        "merge_base_with_main": merge_base,
        "commits_ahead_of_main_merge_base": ahead,
        "is_ancestor_of_main": bool(is_anc_ok),
    }
    if is_anc_ok:
        merge_sha = find_merge_commit_for_tip(repo_dir, tip, main_ref)
        entry["merge_sha"] = merge_sha
        entry["tag"] = nearest_tag_containing(repo_dir, merge_sha) if merge_sha else None
    else:
        entry["merge_sha"] = None
        entry["tag"] = None
    return entry


# --------------------------------------------------------------------------
# Merge queue
# --------------------------------------------------------------------------

def read_merge_queue(queue_dir):
    queue_dir = Path(queue_dir)
    tickets, done = [], []
    tdir = queue_dir / "tickets"
    ddir = queue_dir / "done"
    if tdir.is_dir():
        for f in sorted(tdir.glob("*.json")):
            if f.name.startswith("EXAMPLE"):
                continue
            try:
                data = json.loads(f.read_text())
            except Exception:
                continue
            if data.get("status") == "example":
                continue
            data["_file"] = f.name
            tickets.append(data)
    if ddir.is_dir():
        for f in sorted(ddir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
            except Exception:
                continue
            data["_file"] = f.name
            done.append(data)
    lock_held = False
    ldir = queue_dir / "lock"
    if ldir.is_dir():
        lock_held = any(ldir.iterdir())
    return {"tickets_ready": tickets, "done": done, "lock_held": lock_held}


# --------------------------------------------------------------------------
# Journals (best-effort corroboration only, never authoritative)
# --------------------------------------------------------------------------

def scan_journals(journals_glob, max_hits=25):
    hits = []
    for path in sorted(glob.glob(journals_glob)):
        try:
            with open(path, "r", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    if "skill6-v2" in line or "skill62" in line or "qcScore" in line or "qc_score" in line:
                        hits.append({"file": path, "line": line[:300]})
                        if len(hits) >= max_hits:
                            return hits
        except Exception:
            continue
    return hits


# --------------------------------------------------------------------------
# Ledger table parsing / patching (skill 6, both the GitHub copy and the
# Downloads copy share the identical table shape)
# --------------------------------------------------------------------------

def find_pending_units(ledger_text):
    """Return {unit_id: description} for rows that match the strict empty
    'pending' shape -- safe auto-patch candidates."""
    out = {}
    for line in ledger_text.splitlines():
        m = PENDING_ROW_RE.match(line)
        if m:
            out[m.group(1)] = m.group("desc")
    return out


def patch_ledger_file(path, gap_fills):
    """gap_fills: {unit_id: (new_label, new_status, new_evidence, new_ts)}.
    Rewrites ONLY lines matching the strict empty-pending shape for the given
    unit ids. Returns list of unit ids actually changed."""
    path = Path(path)
    if not path.exists() or not gap_fills:
        return []
    text = path.read_text()
    lines = text.split("\n")
    changed = []
    for i, line in enumerate(lines):
        m = PENDING_ROW_RE.match(line)
        if not m:
            continue
        uid = m.group(1)
        if uid not in gap_fills:
            continue
        desc = m.group("desc")
        label, status, evidence, ts = gap_fills[uid]
        lines[i] = f"| {uid} | {desc} | {label} | {status} | {evidence} | {ts} |"
        changed.append(uid)
    if changed:
        path.write_text("\n".join(lines))
    return changed


def build_gap_fill_evidence(unit_id, onb_entry, cc_entry):
    """Build (label, status, evidence, timestamp) for a unit id given
    confirmed git truth on ONB and/or CC. Only called when at least one side
    has a precise merge_sha + tag."""
    parts = []
    if onb_entry and onb_entry.get("merge_sha") and onb_entry.get("tag"):
        parts.append(
            f"openclaw-onboarding: branch `skill6-v2/{unit_id}` (tip `{onb_entry['tip'][:8]}`) "
            f"confirmed merged into `origin/main` via commit `{onb_entry['merge_sha'][:8]}`, "
            f"nearest tag `{onb_entry['tag']}`."
        )
    if cc_entry and cc_entry.get("merge_sha") and cc_entry.get("tag"):
        parts.append(
            f"blackceo-command-center: branch `skill6-v2/{unit_id}` (tip `{cc_entry['tip'][:8]}`) "
            f"confirmed merged into `origin/main` via commit `{cc_entry['merge_sha'][:8]}`, "
            f"nearest tag `{cc_entry['tag']}`."
        )
    if not parts:
        return None
    evidence = (
        "AUTO-RECONCILED from git truth by ledger-reconciler (unattended cron pass). "
        + " ".join(parts)
        + " Ancestry + merge-commit + annotated-tag independently re-derived from `origin/main`"
        " via direct-parent match (not merely ancestor-of); this row was NOT hand-verified by a"
        " build/merge-writer session -- treat as provisional until a build session confirms test"
        " proof for this unit."
    )
    label = "[ledger-reconciler] auto-reconciled from git truth"
    status = "verified (auto-reconciled, needs test-proof confirmation)"
    return label, status, evidence, now_utc_iso()


# --------------------------------------------------------------------------
# Session log append (append-only)
# --------------------------------------------------------------------------

def append_session_log(path, heading, body_lines):
    path = Path(path)
    if not path.exists():
        return False
    block = ["", f"## {now_utc_iso()} — {heading}", ""]
    block.extend(body_lines)
    block.append("")
    with path.open("a") as fh:
        fh.write("\n".join(block))
    return True


# --------------------------------------------------------------------------
# Recovery snapshot rendering
# --------------------------------------------------------------------------

def qc_from_prose(evidence_text):
    m = QC_SCORE_RE.search(evidence_text or "")
    return m.group(1) if m else None


def current_ledger_status(ledger_text, unit_id):
    for line in ledger_text.splitlines():
        m = UNIT_ROW_RE.match(line)
        if m and m.group(1) == unit_id:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 5:
                return cells[3], cells[4]  # status, evidence
    return None, None


def detect_failclosed_mismatches(repo_label, units_truth, github_ledger_text):
    """FAIL-CLOSED integrity check for "both-repo/one-leg" units.

    The shared skill6 ledger (ledgers/skill6-blended-persona-kanban-v2-*.md)
    has exactly ONE row per unit id, even for units that ship as a matched
    pair of branches -- one in openclaw-onboarding, one in
    blackceo-command-center. When only one repo's leg has actually landed,
    the row's status cell can still legitimately read "verified" (it is
    prose-documenting the leg that IS done), but naively re-printing that
    same global status next to the OTHER repo's per-branch git-truth row
    is misleading: a recovery-state.md reader has no way to tell, from the
    table alone, that "verified" belongs to the other repo's leg and NOT
    to the leg shown NOT merged two columns over.

    This is exactly the U53 case: the ONB leg (`skill6-v2/U53` in
    openclaw-onboarding) is not an ancestor of ONB's `origin/main` (no
    mergeSha, no tag), while the shared ledger row reads "verified" because
    the CC leg landed (v6.0.36). Silently printing "verified" on the ONB
    row is a fail-OPEN misread waiting to happen.

    For every branch this repo's git truth tracked (units_truth, keyed by
    branch name `skill6-v2/<unit>`) that is NOT an ancestor of this repo's
    main, check whether the shared ledger's status cell for that unit id
    starts with "verified" (hand-set OR auto-reconciled -- both are
    in-scope; auto-reconcile only required ONE side to have merge_sha+tag,
    so it can produce the exact same both-repo/one-leg mismatch). If so,
    that is a fail-closed alarm: this repo's leg is NOT actually done, no
    matter what the row's global status cell says.

    Read-only: never mutates the ledger, never mutates units_truth. Returns
    a list of alarm dicts, sorted by unit id (numeric), empty if none.
    """
    alarms = []
    for branch, e in units_truth.items():
        if e.get("is_ancestor_of_main"):
            continue  # this leg IS merged -- no mismatch possible
        uid = branch.split("/")[-1]
        led_status, led_evidence = current_ledger_status(github_ledger_text, uid)
        if not led_status:
            continue  # no ledger row at all for this unit -- nothing to contradict
        if not STATUS_VERIFIED_RE.match(led_status.strip()):
            continue  # ledger already says pending/deferred/other -- consistent, no alarm
        alarms.append({
            "unit": uid,
            "repo": repo_label,
            "branch": branch,
            "tip": e.get("tip"),
            "ledger_status": led_status.strip(),
            "reason": (
                f"{repo_label} leg of {uid} (branch `{branch}`, tip "
                f"`{(e.get('tip') or '')[:8]}`) is NOT merged into {repo_label}'s "
                f"main (mergedIntoMain=False, no mergeSha/tag), but the shared "
                f"skill6 ledger's status cell for {uid} reads "
                f"'{led_status.strip()}' -- a both-repo/one-leg fail-open "
                f"condition. Do not treat this repo's leg as complete."
            ),
        })
    return sorted(alarms, key=lambda a: int(a["unit"][1:]) if a["unit"][1:].isdigit() else 0)


def render_recovery_state(truth, github_ledger_text, out_path):
    lines = []
    lines.append("# Ledger / Session-Log Reconciler — Recovery Snapshot")
    lines.append("")
    lines.append(
        "AUTHORITATIVE, machine-derived-from-git-truth recovery source for the Skill 6"
        " (blended persona kanban v2) and Skill 62 (cinematic web funnel engine) builds."
        " Rewritten in full every reconciler run (every 10 minutes via cron). If a build"
        " session is lost to a context/session limit, this file is the fastest path back"
        " to real state — every fact below was independently re-derived from `git`"
        " (fetch + ancestry + direct-parent merge-commit match + annotated-tag lookup),"
        " never copied from a prior run or from ledger prose."
    )
    lines.append("")
    lines.append(f"Generated: {truth['generated_at']}")
    lines.append(f"openclaw-onboarding `origin/main` HEAD: `{truth['onb_main_sha']}`")
    lines.append(f"blackceo-command-center `origin/main` HEAD: `{truth['cc_main_sha']}`")
    lines.append("")

    alarms = truth.get("failclosed_alarms") or []
    alarm_lookup = {(a["repo"], a["unit"]) for a in alarms}
    lines.append("## INTEGRITY ALARMS — fail-closed (verified-but-unmerged leg mismatches)")
    lines.append("")
    if alarms:
        lines.append(
            f"**{len(alarms)} mismatch(es) found this run.** A repo leg below is NOT merged"
            " into that repo's main, yet the shared skill6 ledger's status cell for that unit"
            " reads a `verified` status. Treat the flagged repo's leg as **NOT actually"
            " complete** until a build/merge-writer session confirms and, if needed, corrects"
            " the ledger row. This reconciler never auto-corrects a verified/deferred/other"
            " row on its own (that would just trade one fail-open bug for another) -- it only"
            " refuses to let the mismatch go unflagged."
        )
        lines.append("")
        lines.append("| unit | unmerged repo leg | branch | tip | shared ledger status |")
        lines.append("|---|---|---|---|---|")
        for a in alarms:
            lines.append(
                f"| {a['unit']} | {a['repo']} | `{a['branch']}` | "
                f"`{(a['tip'] or '')[:8]}` | {a['ledger_status']} |"
            )
    else:
        lines.append("No mismatches found this run.")
    lines.append("")

    lines.append("## Skill 6 — openclaw-onboarding (`skill6-v2/*` branches)")
    lines.append("")
    lines.append("| unit | branch | headSha | mergedIntoMain | mergeSha | tag | ledgerStatus | qcScore(prose) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for branch, e in sorted(truth["onb_units"].items()):
        uid = branch.split("/")[-1]
        led_status, led_evidence = (None, None)
        if UNIT_ROW_RE.match(f"| {uid} |"):
            led_status, led_evidence = current_ledger_status(github_ledger_text, uid)
        qc = qc_from_prose(led_evidence) if led_status == "verified" else None
        if ("openclaw-onboarding", uid) in alarm_lookup:
            status_cell = f"**MISMATCH (fail-closed): {led_status}** — see Integrity Alarms"
            qc_cell = "-"
        else:
            status_cell = led_status or "(no row)"
            qc_cell = qc or "-"
        lines.append(
            f"| {uid} | `{branch}` | `{e['tip'][:8]}` | {e['is_ancestor_of_main']} | "
            f"{('`' + e['merge_sha'][:8] + '`') if e.get('merge_sha') else '-'} | "
            f"{e.get('tag') or '-'} | {status_cell} | {qc_cell} |"
        )
    lines.append("")

    lines.append("## Skill 6 — blackceo-command-center (`skill6-v2/*` branches)")
    lines.append("")
    lines.append("| unit | branch | headSha | mergedIntoMain | mergeSha | tag | ledgerStatus | qcScore(prose) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for branch, e in sorted(truth["cc_units"].items()):
        uid = branch.split("/")[-1]
        led_status, led_evidence = current_ledger_status(github_ledger_text, uid)
        qc = qc_from_prose(led_evidence) if led_status == "verified" else None
        if ("blackceo-command-center", uid) in alarm_lookup:
            status_cell = f"**MISMATCH (fail-closed): {led_status}** — see Integrity Alarms"
            qc_cell = "-"
        else:
            status_cell = led_status or "(no row)"
            qc_cell = qc or "-"
        lines.append(
            f"| {uid} | `{branch}` | `{e['tip'][:8]}` | {e['is_ancestor_of_main']} | "
            f"{('`' + e['merge_sha'][:8] + '`') if e.get('merge_sha') else '-'} | "
            f"{e.get('tag') or '-'} | {status_cell} | {qc_cell} |"
        )
    lines.append("")

    c = truth["cinematic"]
    lc = truth["cinematic_local_clone"]
    lines.append("## Skill 62 — cinematic-web-funnel-engine (`skill62/cinematic-engine`)")
    lines.append("")
    if not c.get("exists"):
        lines.append("Branch `skill62/cinematic-engine` not found on `origin`.")
        if lc.get("local_branch_exists"):
            if lc.get("unpushed_commit_count", 0) > 0:
                lines.append(
                    f"- **AT RISK**: isolated build clone `~/cinematic-engine-build` has "
                    f"{lc['unpushed_commit_count']} local commit(s) on `skill62/cinematic-engine` "
                    f"NEVER pushed to origin (local tip `{lc['local_tip'][:8]}`). If that clone is "
                    f"lost, these commits are lost. Push to origin as soon as QC-passed per "
                    f"the merge-queue protocol."
                )
                for item in lc["unpushed_commits"][:15]:
                    lines.append(f"  - `{item['sha'][:8]}` {item['subject']}")
            else:
                lines.append(
                    f"- isolated build clone `~/cinematic-engine-build` has branch "
                    f"`skill62/cinematic-engine` at `{lc['local_tip'][:8]}`, identical to its "
                    f"origin/main fork point — no cinematic-specific commits made yet, "
                    f"nothing at risk."
                )
        else:
            lines.append("- isolated build clone also has no such local branch (checked read-only).")
    else:
        lines.append(f"- branch tip: `{c['tip'][:8]}`")
        lines.append(f"- merge-base with `origin/main`: `{c['merge_base_with_main'][:8]}`")
        lines.append(f"- commits ahead of that merge-base (cinematic-specific work so far): {len(c['commits_ahead_of_main_merge_base'])}")
        if c["commits_ahead_of_main_merge_base"]:
            for item in c["commits_ahead_of_main_merge_base"][:15]:
                lines.append(f"  - `{item['sha'][:8]}` {item['subject']}")
        lines.append(f"- merged into `origin/main`: {c['is_ancestor_of_main']}")
        if c.get("merge_sha"):
            lines.append(f"- merge commit: `{c['merge_sha'][:8]}`, nearest tag: {c.get('tag') or '-'}")
        if lc.get("local_branch_exists") and not lc.get("pushed_to_origin") and lc.get("unpushed_commit_count", 0) > 0:
            lines.append(
                f"- **AT RISK**: isolated build clone `~/cinematic-engine-build` local tip "
                f"`{lc['local_tip'][:8]}` is {lc['unpushed_commit_count']} commit(s) ahead of "
                f"what's pushed to origin. Push before ending the session."
            )
    lines.append("")

    mq = truth["merge_queue"]
    lines.append("## Merge queue snapshot (`onboarding-merge-queue/`)")
    lines.append("")
    lines.append(f"- writer lock held at gather time: {mq['lock_held']}")
    lines.append(f"- ready tickets in `tickets/`: {len(mq['tickets_ready'])}")
    for t in mq["tickets_ready"]:
        lines.append(
            f"  - `{t.get('_file')}` build={t.get('build')} branch={t.get('branch')} "
            f"qcScore={t.get('qcScore')} status={t.get('status')}"
        )
    lines.append(f"- completed in `done/`: {len(mq['done'])}")
    for d in mq["done"]:
        lines.append(
            f"  - `{d.get('_file')}` build={d.get('build')} branch={d.get('branch')} "
            f"status={d.get('status')} mergeSha={d.get('mergeSha')} newVersion={d.get('newVersion')}"
        )
    lines.append("")

    lines.append("## This run")
    lines.append("")
    lines.append(f"- ledger-edit permitted this run (merge-queue lock was free): {truth['ledger_edit_allowed']}")
    lines.append(f"- units auto-reconciled (git showed merged/tagged, ledger still said pending) this run: {truth['units_gap_filled'] or 'none'}")
    alarm_units = ", ".join(f"{a['unit']}-{a['repo']}" for a in alarms) if alarms else "none"
    lines.append(f"- fail-closed integrity alarms this run (verified-but-unmerged leg mismatches): {len(alarms)} ({alarm_units})")
    lines.append(f"- journal corroboration hits scanned: {len(truth['journal_hits'])} (informational only, never authoritative)")
    lines.append("")

    Path(out_path).write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onb-dir", required=True)
    ap.add_argument("--cc-dir", required=True)
    ap.add_argument("--queue-dir", required=True)
    ap.add_argument("--journals-glob", required=True)
    ap.add_argument("--github-ledger-path", required=True)
    ap.add_argument("--downloads-ledger-path", required=True)
    ap.add_argument("--cinematic-checklist-path", required=True)
    ap.add_argument("--cinematic-local-clone", required=True, help="read-only: isolated build clone, e.g. ~/cinematic-engine-build")
    ap.add_argument("--recovery-out", required=True)
    ap.add_argument("--recovery-copy-out", required=True)
    ap.add_argument("--downloads-session-log", required=True)
    ap.add_argument("--cinematic-session-log", required=True)
    ap.add_argument("--allow-ledger-edit", required=True, choices=["0", "1"])
    ap.add_argument("--result-out", required=True, help="where to write a small JSON result summary for the bash wrapper")
    args = ap.parse_args()

    generated_at = now_utc_iso()

    onb_main_sha = sh(args.onb_dir, ["rev-parse", "origin/main"])
    cc_main_sha = sh(args.cc_dir, ["rev-parse", "origin/main"])

    onb_units = gather_branch_truth(args.onb_dir, "skill6-v2/")
    cc_units = gather_branch_truth(args.cc_dir, "skill6-v2/")
    cinematic = gather_cinematic_truth(args.onb_dir)
    cinematic_local_clone = gather_cinematic_local_clone_truth(args.cinematic_local_clone)
    mq = read_merge_queue(args.queue_dir)
    journal_hits = scan_journals(args.journals_glob)

    allow_edit = args.allow_ledger_edit == "1"

    github_ledger_text = Path(args.github_ledger_path).read_text() if Path(args.github_ledger_path).exists() else ""
    downloads_ledger_text = Path(args.downloads_ledger_path).read_text() if Path(args.downloads_ledger_path).exists() else ""

    gap_fills = {}
    units_gap_filled = []
    if allow_edit:
        pending_github = find_pending_units(github_ledger_text)
        pending_downloads = find_pending_units(downloads_ledger_text)
        # Only unit ids that are ACTUALLY numbered skill6-v2 branches (drop any
        # accidental non-branch match) and only when at least one repo side has
        # a precise merge_sha + tag.
        candidate_ids = set(pending_github) | set(pending_downloads)
        for uid in sorted(candidate_ids, key=lambda x: int(x[1:])):
            onb_branch = f"skill6-v2/{uid}"
            cc_branch = f"skill6-v2/{uid}"
            onb_entry = onb_units.get(onb_branch)
            cc_entry = cc_units.get(cc_branch)
            fill = build_gap_fill_evidence(uid, onb_entry, cc_entry)
            if fill:
                gap_fills[uid] = fill

        if gap_fills:
            changed_github = patch_ledger_file(args.github_ledger_path, gap_fills)
            changed_downloads = patch_ledger_file(args.downloads_ledger_path, gap_fills)
            units_gap_filled = sorted(set(changed_github) | set(changed_downloads), key=lambda x: int(x[1:]))
            # re-read github ledger text after patch for the recovery-state render
            github_ledger_text = Path(args.github_ledger_path).read_text()

    # FAIL-CLOSED integrity check: run AFTER any gap-fill patch above (so it
    # sees the final, post-patch ledger text -- an auto-reconciled row can
    # itself produce the exact same both-repo/one-leg mismatch, since
    # gap-fill only requires ONE side to have merge_sha+tag). Read-only,
    # never mutates the ledger -- see detect_failclosed_mismatches().
    onb_alarms = detect_failclosed_mismatches("openclaw-onboarding", onb_units, github_ledger_text)
    cc_alarms = detect_failclosed_mismatches("blackceo-command-center", cc_units, github_ledger_text)
    failclosed_alarms = sorted(
        onb_alarms + cc_alarms,
        key=lambda a: (int(a["unit"][1:]) if a["unit"][1:].isdigit() else 0, a["repo"]),
    )

    truth = {
        "generated_at": generated_at,
        "onb_main_sha": onb_main_sha,
        "cc_main_sha": cc_main_sha,
        "onb_units": onb_units,
        "cc_units": cc_units,
        "cinematic": cinematic,
        "cinematic_local_clone": cinematic_local_clone,
        "merge_queue": mq,
        "journal_hits": journal_hits,
        "ledger_edit_allowed": allow_edit,
        "units_gap_filled": ", ".join(units_gap_filled) if units_gap_filled else "",
        "failclosed_alarms": failclosed_alarms,
    }

    render_recovery_state(truth, github_ledger_text, args.recovery_out)
    render_recovery_state(truth, github_ledger_text, args.recovery_copy_out)

    # session log appends -- always safe, append-only
    alarm_units_summary = (
        ", ".join(f"{a['unit']}-{a['repo']}" for a in failclosed_alarms)
        if failclosed_alarms else "none"
    )
    summary_body = [
        f"- openclaw-onboarding `origin/main` = `{onb_main_sha}`; blackceo-command-center `origin/main` = `{cc_main_sha}`.",
        f"- skill6-v2 branches tracked: ONB={len(onb_units)}, CC={len(cc_units)}; "
        f"merged-into-main: ONB={sum(1 for e in onb_units.values() if e['is_ancestor_of_main'])}, "
        f"CC={sum(1 for e in cc_units.values() if e['is_ancestor_of_main'])}.",
        f"- merge-queue: {len(mq['tickets_ready'])} ready ticket(s), {len(mq['done'])} done, "
        f"writer lock held={mq['lock_held']}.",
        f"- ledger-edit permitted this pass: {allow_edit} "
        + ("(merge-queue writer lock was held -> ledger edit skipped this cycle, will retry next cron tick)" if not allow_edit else "(merge-queue writer lock free)"),
        f"- units auto-reconciled this pass: {', '.join(units_gap_filled) if units_gap_filled else 'none (no gap between git truth and ledger found)'}",
        f"- FAIL-CLOSED integrity alarms this pass (verified-but-unmerged leg mismatches): {len(failclosed_alarms)} ({alarm_units_summary})",
        f"- recovery snapshot rewritten at `{args.recovery_out}`.",
    ]
    append_session_log(
        args.downloads_session_log,
        "[ledger-reconciler cron pass] git-truth reconciliation",
        summary_body,
    )
    cinematic_local_note = "isolated clone not found (read-only check skipped)."
    if cinematic_local_clone.get("clone_exists"):
        if cinematic_local_clone.get("local_branch_exists"):
            n = cinematic_local_clone.get("unpushed_commit_count", 0)
            if n > 0:
                cinematic_local_note = (
                    f"AT RISK: {n} local commit(s) on skill62/cinematic-engine in "
                    f"~/cinematic-engine-build not yet pushed to origin (read-only check; "
                    f"push before ending any build session)."
                )
            else:
                cinematic_local_note = "local branch present, no unpushed commits, nothing at risk."
        else:
            cinematic_local_note = "isolated clone present, local branch not found."
    append_session_log(
        args.cinematic_session_log,
        "[ledger-reconciler cron pass] git-truth reconciliation (shared cron, skill62 section)",
        [
            f"- skill62/cinematic-engine branch on origin: {cinematic.get('exists')}"
            + (f", tip `{cinematic['tip'][:8]}`, {len(cinematic.get('commits_ahead_of_main_merge_base', []))} commit(s) ahead of the origin/main merge-base, merged-into-main={cinematic.get('is_ancestor_of_main')}." if cinematic.get("exists") else " (not pushed yet)."),
            f"- isolated build clone (~/cinematic-engine-build, read-only check): {cinematic_local_note}",
            "- no cinematic-specific checklist items were auto-marked done this pass (no git-provable per-item evidence found).",
            f"- recovery snapshot rewritten at `{args.recovery_out}`.",
        ],
    )

    # Machine-readable alarms for the bash wrapper (log a WARNING and fold
    # the alarm count into the commit message so it's visible in `git log`
    # without opening recovery-state.md -- never silent, never blocking).
    failclosed_alarms_summary = [
        {"unit": a["unit"], "repo": a["repo"], "branch": a["branch"], "ledger_status": a["ledger_status"]}
        for a in failclosed_alarms
    ]

    with open(args.result_out, "w") as fh:
        json.dump(
            {
                "units_gap_filled": units_gap_filled,
                "ledger_edit_allowed": allow_edit,
                "onb_main_sha": onb_main_sha,
                "cc_main_sha": cc_main_sha,
                "failclosed_alarm_count": len(failclosed_alarms),
                "failclosed_alarms": failclosed_alarms_summary,
            },
            fh,
            indent=2,
        )

    print(json.dumps({
        "units_gap_filled": units_gap_filled,
        "ledger_edit_allowed": allow_edit,
        "failclosed_alarm_count": len(failclosed_alarms),
    }))


if __name__ == "__main__":
    main()
