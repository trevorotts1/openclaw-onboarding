#!/usr/bin/env python3
"""dedup-agents-md.py — mechanical, marker-guard-safe duplicate-block remover
for the LIVE (gateway-injected) AGENTS.md bootstrap file.

ROOT CAUSE THIS FIXES
----------------------
scripts/apply-fleet-standards.sh stamps ~10 marker-guarded blocks into the
live AGENTS.md using the idiom:

    if grep -qF "$MARKER" file; then <no-op>; else cat >> file; fi

That guard false-negatives whenever a historical stamp predates the marker
(or the marker text drifted), so the block RE-APPENDS on a later run. Measured
on a fleet box: up to 8 copies of one heading, ~23,000 bytes of pure
repetition in a single AGENTS.md. Total prompt injection is empirically capped
at ~400,000 chars — past that the file is SILENTLY TRUNCATED (no error, no
log), so the agent loses its own rules every turn.

The grep-guard fix (a4f94e89) stops FUTURE re-appends. It does NOT remove
duplicates already on disk. This script is that cleanup.

WHAT THIS SCRIPT DOES — strictly mechanical, no model/LLM judgment anywhere
----------------------------------------------------------------------------
  1. Resolves the LIVE AGENTS.md via shared-utils/resolve_injected_core_files.py
     (the repo's ONE sanctioned way to learn where the gateway-injected
     workspace files live — see that module's docstring). If no file resolves,
     prints an informational SKIP and exits 0.
  2. Parses the file into blocks delimited by markdown headings (`^#{1,3} `),
     skipping any heading found inside a fenced ``` code block (payload text,
     not a real section boundary — mirrors the same guard update-skills.sh's
     CORE_UPDATES.md merge step already uses for the identical reason).
  3. Removes ONLY exact-duplicate blocks: identical heading text AND
     byte-identical body. Never touches a near-duplicate (bodies differing by
     even one byte) — those are left alone and reported as NEAR-DUP for
     manual review.
  4. When a duplicate cluster contains a copy carrying its own
     `<!-- MARKER -->` line (the live stamp — the line immediately preceding
     the heading, in the exact shape apply-fleet-standards.sh writes it), that
     copy is kept. Otherwise the FIRST occurrence in document order is kept.
     Never keeps zero copies of anything.
  5. Verifies BEGIN/END skill-wiring pairs
     (`<!-- BEGIN skill:NN:agents -->` / `<!-- END skill:NN:agents -->`,
     written by update-skills.sh's CORE_UPDATES.md merge step) stay balanced
     in the proposed output. If collapsing duplicates would leave any pair
     unbalanced, NOTHING is written and the script exits non-zero with a loud
     message — never guess, never partially apply.
  6. Backs up the original file to a timestamped sibling before writing, then
     verifies the backup byte-for-byte (filecmp.cmp, shallow=False — the pure-
     Python equivalent of `cmp -s`) and refuses to proceed if that check fails.
  7. Idempotent: a second run against an already-deduped file removes nothing
     and says so plainly. A file with zero duplicates is left byte-identical
     (no write, no backup — nothing to back up).
  8. Never prints file body content or secrets — only heading text (structural
     markdown titles, truncated defensively), byte counts, and line numbers.

USAGE
-----
    dedup-agents-md.py                       # DRY-RUN (the default) against the
                                              #   resolved live AGENTS.md; reports
                                              #   only, writes nothing
    dedup-agents-md.py --dry-run             # same, explicit
    dedup-agents-md.py --apply               # actually write (after backup+verify)
    dedup-agents-md.py --file PATH [--apply] # operate on an explicit file instead
                                              #   of resolving one (used by
                                              #   apply-fleet-standards.sh, and by
                                              #   tests against fixtures)
    dedup-agents-md.py --agent-id ceo ...    # resolve a non-"main" agent's workspace
    dedup-agents-md.py --hard-cap-chars N    # override the truncation-risk
                                              #   threshold (default: env
                                              #   FLEET_CORE_BOOTSTRAP_HARD_CAP_CHARS
                                              #   or 380000 — matches
                                              #   apply-fleet-standards.sh)

Exit codes: 0 = OK (skip / idempotent no-op / dry-run report / successful
apply). 2 = usage or IO error. 3 = refused to write (BEGIN/END would be
unbalanced, or the backup failed its byte-for-byte verification) — nothing
was written in either case.

Always prints exactly one line starting with `[AGENTS DEDUP] ` summarizing the
outcome, so a caller (or post-roll `grep '\\[AGENTS DEDUP\\]'` across a log) can
see the result even when the rest of the output is suppressed.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections import OrderedDict
from pathlib import Path

HEADING_RE = re.compile(r"^#{1,3} ")
MARKER_RE = re.compile(r"^<!--\s*(\S+)\s*-->\s*$")
FENCE_RE = re.compile(r"^[ \t]*```")
BEGIN_RE = re.compile(r"^<!--\s*BEGIN\s+skill:(.+?):(.+?)\s*-->\s*$")
END_RE = re.compile(r"^<!--\s*END\s+skill:(.+?):(.+?)\s*-->\s*$")

DEFAULT_HARD_CAP_CHARS = 380000


# ---------------------------------------------------------------------------
# Workspace resolution — PRD 1.11 single-source-of-truth
# ---------------------------------------------------------------------------

def _find_shared_utils(script_dir: Path):
    """Locate shared-utils/resolve_injected_core_files.py from any of the
    layouts this script might be deployed into (repo checkout, or a box's
    persistent scripts/ directory sitting next to a delivered shared-utils/)."""
    candidates = [
        script_dir.parent / "shared-utils",
        Path.home() / ".openclaw" / "skills" / "shared-utils",
        Path("/data/.openclaw/skills/shared-utils"),
        script_dir / "shared-utils",
    ]
    for c in candidates:
        if (c / "resolve_injected_core_files.py").is_file():
            return c
    return None


def _inline_find_openclaw_root() -> Path:
    """Fallback ONLY — mirrors resolve_injected_core_files.py's own
    _find_openclaw_root() so this script still resolves correctly if the
    shared helper is unreachable (e.g. copied out of the repo tree in
    isolation). The shared helper is always tried FIRST; this never runs
    when it succeeds."""
    env_root = os.environ.get("FLEET_REFRESH_ROOT", "").strip()
    if env_root:
        return Path(env_root)
    for p in (Path("/data/.openclaw"), Path.home() / ".openclaw", Path.home() / "clawd"):
        if p.exists():
            return p
    return Path.home() / ".openclaw"


def _inline_find_openclaw_config(root: Path):
    env_cfg = os.environ.get("OC_JSON", "").strip()
    if env_cfg:
        p = Path(env_cfg)
        return p if p.is_file() else None
    for c in (root / "openclaw.json", root / "workspace" / "openclaw.json"):
        if c.is_file():
            return c
    return None


def resolve_agents_md(agent_id: str, explicit: str | None):
    """Returns (path: Path, resolved_from: str)."""
    if explicit:
        return Path(explicit), "explicit --file"

    script_dir = Path(__file__).resolve().parent
    su = _find_shared_utils(script_dir)
    if su is not None:
        sys.path.insert(0, str(su))
        try:
            from resolve_injected_core_files import resolve_injected_core_files  # type: ignore

            r = resolve_injected_core_files(agent_id)
            return r["agents_md"], r["resolved_from"]
        except Exception as e:  # pragma: no cover - defensive only
            print(
                f"[AGENTS DEDUP] WARN: resolve_injected_core_files import/resolve failed ({e}); "
                "falling back to inline resolution",
                file=sys.stderr,
            )

    # Inline fallback — kept in lockstep with resolve_injected_core_files.py's
    # documented 3-step priority. Only reached if the shared helper cannot be
    # found/imported at all.
    root = _inline_find_openclaw_root()
    cfg = _inline_find_openclaw_config(root)
    workspace = None
    resolved_from = "default"
    if cfg is not None and cfg.is_file():
        try:
            data = json.loads(cfg.read_text())
        except Exception:
            data = {}
        for ag in (data.get("agents", {}).get("list") or []):
            if isinstance(ag, dict) and ag.get("id") == agent_id:
                ws = ag.get("workspace")
                if ws:
                    workspace = Path(os.path.expanduser(ws))
                    resolved_from = f"agents.list[{agent_id}].workspace"
                break
        if workspace is None:
            dw = (data.get("agents", {}) or {}).get("defaults", {}).get("workspace")
            if dw:
                workspace = Path(os.path.expanduser(dw))
                resolved_from = "agents.defaults.workspace"
    if workspace is None:
        workspace = root / "workspace"
        resolved_from = "default"
    return workspace / "AGENTS.md", resolved_from


# ---------------------------------------------------------------------------
# Block parsing
# ---------------------------------------------------------------------------

def _fenced_line_flags(lines):
    """list[bool], same length as lines — True if that line sits inside a
    fenced ``` code block. A line that itself opens/closes a fence counts as
    'inside' (excluded from heading detection either way)."""
    flags = [False] * len(lines)
    in_fence = False
    for i, ln in enumerate(lines):
        stripped = ln.rstrip("\r\n")
        if FENCE_RE.match(stripped):
            flags[i] = True
            in_fence = not in_fence
            continue
        flags[i] = in_fence
    return flags


def parse_blocks(text: str):
    """Returns (lines, preamble_end, blocks).

    lines:        text.splitlines(keepends=True)
    preamble_end: index where the first block (see below) starts (len(lines)
                  if there are no headings at all)
    blocks:       list of dicts: start, end (line indices into `lines`, end
                  exclusive), heading (exact heading line text, no newline),
                  body (raw joined text strictly between this block's heading
                  and the START of the next block), marker (the single-token
                  marker string if this heading carries one, else None)

    A block's `start` is NOT always its heading line. Both apply-fleet-
    standards.sh's per-block stamp guard (`<!-- TOKEN -->` immediately above
    the heading) and update-skills.sh's CORE_UPDATES.md wiring
    (`<!-- BEGIN skill:NN:target -->` immediately above the heading) write a
    single comment line directly before the heading it belongs to. Under a
    naive "split purely on heading lines" scheme that line would attach to
    the PRECEDING block's tail instead: two otherwise byte-identical copies
    of a block would then compare as different (one contaminated with a
    trailing marker/BEGIN line meant for whatever follows it), which breaks
    both exact-duplicate detection and the "prefer the marked copy" rule.
    Pulling a recognized prefix line into the block it actually belongs to
    fixes both. An END line is never treated as a prefix — it is always the
    closing marker of whatever block precedes it, and is picked up naturally
    because it falls before the NEXT block's start.
    """
    lines = text.splitlines(keepends=True)
    in_fence = _fenced_line_flags(lines)

    heading_idx = []
    for i, ln in enumerate(lines):
        if in_fence[i]:
            continue
        if HEADING_RE.match(ln.rstrip("\r\n")):
            heading_idx.append(i)

    n = len(heading_idx)
    block_start = [0] * n
    marker_tok: list = [None] * n
    for k, hidx in enumerate(heading_idx):
        prefix_idx = None
        tok = None
        if hidx - 1 >= 0:
            prev = lines[hidx - 1].rstrip("\r\n")
            m = MARKER_RE.match(prev)
            if m:
                prefix_idx = hidx - 1
                tok = m.group(1)
            elif BEGIN_RE.match(prev):
                prefix_idx = hidx - 1
        block_start[k] = prefix_idx if prefix_idx is not None else hidx
        marker_tok[k] = tok

    preamble_end = block_start[0] if n else len(lines)

    blocks = []
    for k, hidx in enumerate(heading_idx):
        end = block_start[k + 1] if k + 1 < n else len(lines)
        heading_text = lines[hidx].rstrip("\r\n")
        body_text = "".join(lines[hidx + 1 : end])
        blocks.append(
            {
                "start": block_start[k],
                "end": end,
                "heading": heading_text,
                "body": body_text,
                "marker": marker_tok[k],
            }
        )
    return lines, preamble_end, blocks


def decide_removals(blocks):
    """Pairwise-exact-dup collapse, grouped by heading then by exact body.

    Returns (removed: set[int] indices into `blocks`,
             per_heading_removed: dict heading -> count removed,
             near_dup_headings: dict heading -> distinct body-variant count)
    """
    heading_groups = OrderedDict()
    for i, b in enumerate(blocks):
        heading_groups.setdefault(b["heading"], []).append(i)

    removed = set()
    per_heading_removed = {}
    near_dup_headings = {}

    for heading, idxs in heading_groups.items():
        if len(idxs) < 2:
            continue

        body_clusters = OrderedDict()
        for i in idxs:
            body_clusters.setdefault(blocks[i]["body"], []).append(i)

        removed_here = 0
        for _body, cluster_idxs in body_clusters.items():
            if len(cluster_idxs) == 1:
                continue
            marked = [i for i in cluster_idxs if blocks[i]["marker"] is not None]
            keep = marked[0] if marked else cluster_idxs[0]
            for i in cluster_idxs:
                if i != keep:
                    removed.add(i)
                    removed_here += 1

        if removed_here:
            per_heading_removed[heading] = removed_here

        if len(body_clusters) > 1:
            near_dup_headings[heading] = len(body_clusters)

    return removed, per_heading_removed, near_dup_headings


def rebuild(lines, preamble_end, blocks, removed):
    out = list(lines[:preamble_end])
    for i, b in enumerate(blocks):
        if i in removed:
            continue
        out.extend(lines[b["start"] : b["end"]])
    return "".join(out)


# ---------------------------------------------------------------------------
# BEGIN/END skill-wiring balance check
# ---------------------------------------------------------------------------

def begin_end_counts(text: str):
    begin_counts = {}
    end_counts = {}
    for ln in text.splitlines():
        m = BEGIN_RE.match(ln)
        if m:
            key = (m.group(1), m.group(2))
            begin_counts[key] = begin_counts.get(key, 0) + 1
            continue
        m = END_RE.match(ln)
        if m:
            key = (m.group(1), m.group(2))
            end_counts[key] = end_counts.get(key, 0) + 1
    return begin_counts, end_counts


def is_balanced(text: str):
    b, e = begin_end_counts(text)
    keys = set(b) | set(e)
    mismatches = {k: (b.get(k, 0), e.get(k, 0)) for k in keys if b.get(k, 0) != e.get(k, 0)}
    return (len(mismatches) == 0), mismatches


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _default_hard_cap():
    try:
        return int(os.environ.get("FLEET_CORE_BOOTSTRAP_HARD_CAP_CHARS", str(DEFAULT_HARD_CAP_CHARS)))
    except ValueError:
        return DEFAULT_HARD_CAP_CHARS


def _truncate_for_report(s: str, n: int = 120) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Mechanically remove exact-duplicate blocks from the live AGENTS.md.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--file", help="Explicit path to AGENTS.md (skips workspace resolution)")
    ap.add_argument("--agent-id", default="main", help="Agent id to resolve the workspace for (default: main)")
    ap.add_argument("--apply", action="store_true", help="Write changes (after backup + verify)")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit dry-run: report only, never write. This is also the DEFAULT when neither flag is given.",
    )
    ap.add_argument(
        "--hard-cap-chars",
        type=int,
        default=None,
        help="Override the truncation-risk threshold (default: env FLEET_CORE_BOOTSTRAP_HARD_CAP_CHARS or 380000)",
    )
    args = ap.parse_args(argv)

    apply_mode = bool(args.apply) and not args.dry_run
    if args.apply and args.dry_run:
        print("[dedup-agents-md] both --apply and --dry-run given — --dry-run wins (no changes written)")
    mode_label = "APPLY" if apply_mode else "DRY-RUN"
    print(f"[dedup-agents-md] mode={mode_label}"
          + ("" if apply_mode else " (this is the default — pass --apply to write changes)"))

    hard_cap = args.hard_cap_chars if args.hard_cap_chars is not None else _default_hard_cap()

    path, resolved_from = resolve_agents_md(args.agent_id, args.file)

    if path is None or not path.is_file():
        print(f"[AGENTS DEDUP] SKIP: no AGENTS.md found at {path} (resolved_from={resolved_from}) — nothing to dedupe")
        return 0

    try:
        raw = path.read_bytes()
    except OSError as e:
        print(f"[dedup-agents-md] ERROR: could not read {path}: {e}", file=sys.stderr)
        print(f"[AGENTS DEDUP] ERROR: unreadable file at {path} — nothing done")
        return 2

    text = raw.decode("utf-8", errors="surrogateescape")
    before_bytes = len(raw)

    lines, preamble_end, blocks = parse_blocks(text)
    removed, per_heading_removed, near_dup_headings = decide_removals(blocks)
    blocks_removed_total = sum(per_heading_removed.values())
    near_dup_count = len(near_dup_headings)

    output_text = rebuild(lines, preamble_end, blocks, removed)
    after_bytes = len(output_text.encode("utf-8", errors="surrogateescape"))
    saved = before_bytes - after_bytes
    after_chars = len(output_text)

    print(f"[dedup-agents-md] file: {path} (resolved_from={resolved_from})")
    print(f"[dedup-agents-md] headings found: {len(blocks)}")

    if per_heading_removed:
        print("[dedup-agents-md] exact-duplicate blocks removed, per heading:")
        for heading, count in per_heading_removed.items():
            print(f"[dedup-agents-md]   {count:>3} removed  {_truncate_for_report(heading)}")
    else:
        print("[dedup-agents-md] no exact-duplicate blocks found")

    if near_dup_headings:
        print("[dedup-agents-md] NEAR-DUP (manual review) — same heading, bodies differ by at least one byte:")
        for heading, variants in near_dup_headings.items():
            print(f"[dedup-agents-md]   {variants:>3} distinct body variants  {_truncate_for_report(heading)}")

    print(f"[dedup-agents-md] size: before={before_bytes} bytes, after={after_bytes} bytes, saved={saved} bytes")

    if after_chars > hard_cap:
        print(
            f"[dedup-agents-md] ⛔ WARNING: resulting size {after_chars:,} chars STILL EXCEEDS the hard cap "
            f"{hard_cap:,} — past this point the gateway is empirically known to SILENTLY TRUNCATE injected "
            f"context (no error, no log). Manual review of the NEAR-DUP list above (if any) and/or further "
            f"trimming is needed."
        )

    if blocks_removed_total == 0:
        print(
            f"[AGENTS DEDUP] before={before_bytes} after={after_bytes} saved=0 blocks_removed=0 "
            f"near_dups={near_dup_count} — already deduplicated (idempotent no-op)"
        )
        return 0

    # Marker-balance guard: refuse only if this dedup would make balance WORSE
    # than it already is.
    #
    # An absolute "must be perfectly balanced" test is wrong in practice. Measured
    # on real fleet data 2026-07-31: 3 of 4 sampled boxes already carry the SAME
    # pre-existing orphan (`16-summarize-youtube:agents  BEGIN=0 END=1`) BEFORE
    # dedup runs — a skill-wiring defect that has nothing to do with duplicate
    # blocks. Refusing on it would have skipped dedup on most of the fleet,
    # including the most duplicated boxes, delivering almost nothing while the
    # ~400,000-char truncation cliff kept eating their instructions.
    #
    # So compare per-marker imbalance BEFORE vs AFTER. A pre-existing imbalance we
    # neither caused nor worsened is passed through untouched (and still reported,
    # so it gets fixed at its real source). Anything dedup would actually make
    # worse still refuses the entire write — never a partial apply.
    _, before_mm = is_balanced(text)
    _, after_mm = is_balanced(output_text)

    def _skew(mm, key):
        b_count, e_count = mm.get(key, (0, 0))
        return abs(b_count - e_count)

    def _worse(key):
        """Did dedup make THIS marker's wiring worse?

        Two independent ways, because raw skew alone is not enough:

        1. The imbalance grew.
        2. We destroyed the LAST BEGIN while ENDs remain. Skew can *shrink* while
           this happens (1 BEGIN/3 END -> 0 BEGIN/1 END is skew 2 -> 1), yet it is
           strictly worse: with no opening marker left, apply-fleet-standards.sh's
           `grep -qF "$MARKER"` guard stops matching and re-appends the whole block
           on the next run. That is the exact accretion bug this tool exists to
           clean up, so causing it would be self-defeating.
        """
        before_b, _ = before_mm.get(key, (0, 0))
        after_b, after_e = after_mm.get(key, (0, 0))
        if _skew(after_mm, key) > _skew(before_mm, key):
            return True
        return before_b > 0 and after_b == 0 and after_e > 0

    worsened = {k: after_mm[k] for k in after_mm if _worse(k)}

    carried_over = {k: v for k, v in after_mm.items() if k not in worsened}
    if carried_over:
        print(
            "[dedup-agents-md] NOTE: pre-existing BEGIN/END imbalance carried through "
            "unchanged (NOT caused by dedup — fix at the skill-wiring source):"
        )
        for (folder, target), (b_count, e_count) in carried_over.items():
            print(f"[dedup-agents-md]     skill:{folder}:{target}  BEGIN={b_count} END={e_count}")

    if worsened:
        print(
            "[dedup-agents-md] ⛔ REFUSED: collapsing these duplicates would leave "
            "BEGIN/END skill-wiring marker pairs MORE UNBALANCED than they already "
            "are — nothing written:"
        )
        for (folder, target), (b_count, e_count) in worsened.items():
            was_b, was_e = before_mm.get((folder, target), (0, 0))
            print(
                f"[dedup-agents-md]     skill:{folder}:{target}  "
                f"BEGIN={b_count} END={e_count} (was BEGIN={was_b} END={was_e})"
            )
        print(
            f"[AGENTS DEDUP] before={before_bytes} after={after_bytes} saved={saved} "
            f"blocks_removed={blocks_removed_total} near_dups={near_dup_count} — "
            f"REFUSED (dedup would worsen BEGIN/END balance; nothing written)"
        )
        return 3 if apply_mode else 0

    if not apply_mode:
        print(
            f"[AGENTS DEDUP] before={before_bytes} after={after_bytes} saved={saved} "
            f"blocks_removed={blocks_removed_total} near_dups={near_dup_count} — "
            f"DRY-RUN (no changes written; pass --apply to write)"
        )
        return 0

    # --- APPLY: backup, verify, atomic write ---------------------------------
    timestamp = time.strftime("%Y%m%d%H%M%S")
    backup_path = path.with_name(path.name + f".bak-dedup-{timestamp}")
    try:
        shutil.copy2(str(path), str(backup_path))
    except OSError as e:
        print(f"[dedup-agents-md] ERROR: could not create backup {backup_path}: {e}", file=sys.stderr)
        print(
            f"[AGENTS DEDUP] before={before_bytes} after={after_bytes} saved={saved} "
            f"blocks_removed={blocks_removed_total} near_dups={near_dup_count} — "
            f"REFUSED (backup could not be created; nothing written)"
        )
        return 3

    if not filecmp.cmp(str(path), str(backup_path), shallow=False):
        print(
            f"[dedup-agents-md] ⛔ REFUSED: backup {backup_path} did NOT verify byte-for-byte "
            "against the original — nothing written",
            file=sys.stderr,
        )
        print(
            f"[AGENTS DEDUP] before={before_bytes} after={after_bytes} saved={saved} "
            f"blocks_removed={blocks_removed_total} near_dups={near_dup_count} — "
            f"REFUSED (backup verification failed; nothing written)"
        )
        return 3

    try:
        fd, tmp_name = tempfile.mkstemp(prefix=".dedup-agents-md-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(output_text.encode("utf-8", errors="surrogateescape"))
            os.replace(tmp_name, str(path))
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as e:
        print(f"[dedup-agents-md] ERROR: could not write {path}: {e}", file=sys.stderr)
        print(
            f"[AGENTS DEDUP] before={before_bytes} after={after_bytes} saved={saved} "
            f"blocks_removed={blocks_removed_total} near_dups={near_dup_count} — "
            f"REFUSED (write failed; original file intact, backup at {backup_path.name})"
        )
        return 3

    print(f"[dedup-agents-md] wrote {path} (backup: {backup_path.name})")
    print(
        f"[AGENTS DEDUP] before={before_bytes} after={after_bytes} saved={saved} "
        f"blocks_removed={blocks_removed_total} near_dups={near_dup_count} — "
        f"WRITTEN (backup={backup_path.name})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
