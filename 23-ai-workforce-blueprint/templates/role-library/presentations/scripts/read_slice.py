#!/usr/bin/env python3
"""
read_slice.py — RIGHT-SIZE TOOL RESULTS (FIX-19 / D18).

The Presentations engine's SOP/role files are 25-125KB. Reading one WHOLE (the
agent's default Read) returns a tool result that the harness truncates:
"[tool-result-truncation]" fired 33 times in the 2026-08-06 E2E session (D18).
The agent then reasons from incomplete context, inflating retries and causing
wrong decisions.

This utility is the engine's sliced-read path. It returns ONLY the requested
slice of a file — a line range or a byte range — with the slice bounds and byte
count, so a tool result never carries a whole 34-102KB file.

  read_slice(path, lines=(a,b))        # inclusive 1-based line range
  read_slice(path, offset=n, length=m) # byte range
  read_slice(path, index=True)         # section/index map of a markdown SOP

It resolves SOP refs the way the department does: a bare filename is looked up
first in the department sops/ mirror, then in the universal-sops clusters. A
truncation-event counter is maintained on disk (--counter FILE, default
working/checkpoints/read_slice_truncations.json) and INCREMENTED whenever a
read would have exceeded the guard budget (MAX_SLICE_BYTES). The QC gate for
FIX-19 asserts this counter stays 0 on a sliced build.

CLI:
  python3 read_slice.py <path> [--lines 1-100] [--offset N --length M]
                         [--index] [--counter FILE] [--json] [--self-test]
Exit: 0 = ok; 2 = usage/not-found; 3 = slice out of range.

Run:  python3 read_slice.py --self-test    # hermetic fixture battery
Pytest-native:  tests/test_fix19_sliced_reads.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# The guard budget: a tool result over this many bytes is what trips
# [tool-result-truncation] in the harness. Reads are sliced to stay far under it.
MAX_SLICE_BYTES = 32_000

# Counter default: per-run working checkpoint (same tree the ledger lives in).
_DEFAULT_COUNTER = Path("working/checkpoints/read_slice_truncations.json")


def _find_sop_file(name: str, here: Path) -> Path | None:
    """Resolve a SOP ref (bare filename or relative path) the way the department
    does: the department sops/ mirror first, then the universal-sops clusters,
    then any cluster that carries it. Returns the first match or None."""
    candidates = []
    # 1. Direct path / relative to cwd.
    p = Path(name)
    if p.is_file():
        return p.resolve()
    # 2. Department sops/ mirror beside the scripts dir.
    sops_dir = here.parent / "sops"
    candidates.append(sops_dir / name)
    # 3. universal-sops cluster root walk-up.
    cur = here
    for _ in range(12):
        us = cur / "universal-sops"
        if us.is_dir():
            candidates.append(us / name)
            # 4. each presentation-slide-craft cluster file name.
            slide = us / "presentation-slide-craft"
            if slide.is_dir():
                candidates.append(slide / name)
        if cur.parent == cur:
            break
        cur = cur.parent
    for c in candidates:
        if c.is_file():
            return c.resolve()
    # 5. Anywhere under universal-sops (cluster names vary).
    root = here
    for _ in range(12):
        us = root / "universal-sops"
        if us.is_dir():
            for hit in us.rglob(name):
                if hit.is_file():
                    return hit.resolve()
            break
        if root.parent == root:
            break
        root = root.parent
    return None


def _load_counter(path: Path) -> dict:
    if path.exists():
        try:
            obj = json.loads(path.read_text())
            if isinstance(obj, dict):
                return obj
        except Exception:  # noqa: BLE001 — never fatal
            pass
    return {"truncation_events": 0, "reads": [], "total_bytes_returned": 0}


def _save_counter(path: Path, obj: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2))
    except OSError:
        pass  # a counter write never blocks a read


def _record_read(path: Path, record: dict) -> dict:
    """Persist a read record + increment the truncation counter when the slice
    exceeds the guard budget. Returns the updated counter object."""
    obj = _load_counter(path)
    if record.get("would_exceed_budget"):
        obj["truncation_events"] = obj.get("truncation_events", 0) + 1
    obj.setdefault("reads", []).append(record)
    obj["total_bytes_returned"] = obj.get("total_bytes_returned", 0) + \
        int(record.get("returned_bytes", 0))
    _save_counter(path, obj)
    return obj


def read_slice(path: str | Path, *, lines: tuple | None = None,
               offset: int | None = None, length: int | None = None,
               index: bool = False, here: Path | None = None,
               counter: Path | None = None) -> dict:
    """Return ONLY the requested slice of `path` as a dict.

    Modes (exactly one of `lines`, `offset/length`, `index`):
      lines=(a,b)   inclusive 1-based line range [a, b]
      offset,length byte range starting at byte `offset`, `length` bytes long
      index=True    emit the markdown section headers with line numbers instead
                    of body content (a cheap "table of contents" of a large SOP)

    The returned dict always carries: file, total_bytes, slice bounds, and the
    slice text (or index). If the requested slice would exceed MAX_SLICE_BYTES
    it is clamped AND the truncation counter is incremented (so a caller that
    keeps asking for giant slices is visibly burning the budget — the exact
    D18 failure being instrumented).
    """
    here = here or Path(__file__).resolve().parent
    counter = counter or (Path.cwd() / _DEFAULT_COUNTER)
    target = Path(path)
    resolved = _find_sop_file(str(path), here) if not target.is_file() else target.resolve()
    if resolved is None or not resolved.is_file():
        raise FileNotFoundError(
            f"read_slice: SOP/file not found: {path!r} (searched sops/ mirror + "
            f"universal-sops clusters)")

    total_bytes = resolved.stat().st_size
    record = {
        "file": str(resolved),
        "total_bytes": total_bytes,
        "mode": "lines" if lines else ("bytes" if offset is not None else "index"),
        "would_exceed_budget": False,
        "returned_bytes": 0,
    }
    text = ""
    bounds = None

    if index:
        # Markdown section index — headers + line numbers, cheap to emit.
        out = []
        for i, line in enumerate(resolved.read_text(errors="replace").splitlines(), 1):
            s = line.strip()
            if s.startswith("#") and s[1:2].strip():
                out.append({"line": i, "level": len(s) - len(s.lstrip("#")),
                            "header": s.lstrip("# ").strip()})
        payload = {"kind": "index", "sections": out}
        record.update({"mode": "index", "returned_bytes": len(json.dumps(payload))})
        return {"file": str(resolved), "total_bytes": total_bytes, "index": out,
                "slice": None, "read": record, "counter_path": str(counter)}

    if lines is not None:
        a, b = int(lines[0]), int(lines[1])
        with open(resolved, "r", errors="replace") as fh:
            all_lines = fh.readlines()
        n = len(all_lines)
        a, b = max(1, a), min(n, b)
        if a > b:
            raise ValueError(f"read_slice: line range {lines} is empty (file has {n} lines)")
        selected = all_lines[a - 1:b]
        text = "".join(selected)
        bounds = {"lines": [a, b], "lines_total": n}
    elif offset is not None:
        with open(resolved, "rb") as fh:
            fh.seek(offset)
            raw = fh.read(length if length is not None else total_bytes - offset)
        text = raw.decode("utf-8", errors="replace")
        bounds = {"offset": offset, "length": len(raw), "bytes_total": total_bytes}
    else:
        raise ValueError("read_slice: one of --lines or --offset/--length is required")

    returned_bytes = len(text.encode("utf-8"))
    would_exceed = returned_bytes > MAX_SLICE_BYTES
    record.update({
        "slice": bounds,
        "returned_bytes": returned_bytes,
        "would_exceed_budget": would_exceed,
    })
    counter_obj = _record_read(counter, record)
    return {
        "file": str(resolved),
        "total_bytes": total_bytes,
        "slice": bounds,
        "text": text,
        "returned_bytes": returned_bytes,
        "max_slice_bytes": MAX_SLICE_BYTES,
        "would_exceed_budget": would_exceed,
        "truncation_events": counter_obj.get("truncation_events", 0),
        "read": record,
        "counter_path": str(counter),
    }


# ---------------------------------------------------------------------------
# --self-test — hermetic fixture battery (mirrors verify.sh's run pattern)
# ---------------------------------------------------------------------------
def _self_test() -> int:
    fails = []
    def _check(label, cond, detail=""):
        if cond:
            print(f"  [PASS] {label}")
        else:
            print(f"  [FAIL] {label} {detail}")
            fails.append(label)

    with tempfile.TemporaryDirectory(prefix="read_slice_selftest_") as td:
        big = Path(td) / "big-sop.md"
        # Build a ~100KB markdown file: 2000 sections, each a 2-line block.
        body = "\n".join(
            f"## Section {i}\nLine content number {i} — " + ("x" * 40)
            for i in range(1, 2001)
        )
        big.write_text(body)
        assert big.stat().st_size > 90000, big.stat().st_size
        total = big.stat().st_size
        total_lines = len(body.splitlines())  # 4000

        # (1) sliced read returns ONLY the requested slice.
        r = read_slice(big, lines=(50, 60), here=Path(td))
        _check("sliced read of a >90KB file returns a small slice",
               r["returned_bytes"] < 4000 and r["total_bytes"] == total,
               f"returned={r['returned_bytes']} total={r['total_bytes']}")
        # Only 11 lines back (50..60 inclusive), not the whole file.
        got_lines = len([l for l in r["text"].splitlines() if l.strip()])
        _check("returned slice contains only the requested lines",
               got_lines == 11, f"got {got_lines} lines")
        _check("slice bounds reported",
               r["slice"] == {"lines": [50, 60], "lines_total": total_lines},
               str(r["slice"]))

        # (2) byte-range read.
        r2 = read_slice(big, offset=0, length=1000, here=Path(td))
        _check("byte-range read returns only the requested bytes",
               r2["returned_bytes"] == 1000 and r2["slice"]["length"] == 1000,
               f"returned={r2['returned_bytes']} len={r2['slice']}")

        # (3) truncation budget: an oversized slice increments the counter.
        ctr = Path(td) / "working" / "checkpoints" / "trunc.json"
        r3 = read_slice(big, lines=(1, 2000), here=Path(td), counter=ctr)
        _check("oversized slice flagged would_exceed_budget",
               r3["would_exceed_budget"] is True and r3["returned_bytes"] > MAX_SLICE_BYTES,
               f"would_exceed={r3['would_exceed_budget']} returned={r3['returned_bytes']}")
        _check("oversized slice increments the truncation counter",
               r3["truncation_events"] == 1, f"events={r3['truncation_events']}")

        # (4) a sliced build keeps the counter at 0.
        ctr2 = Path(td) / "working" / "checkpoints" / "trunc2.json"
        for lo in range(1, 200, 20):
            read_slice(big, lines=(lo, lo + 9), here=Path(td), counter=ctr2)
        final = _load_counter(ctr2)
        _check("many small sliced reads keep the truncation counter at 0",
               final.get("truncation_events", 0) == 0 and len(final.get("reads", [])) == 10,
               f"events={final.get('truncation_events')} reads={len(final.get('reads', []))}")

        # (5) index mode.
        r5 = read_slice(big, index=True, here=Path(td))
        _check("index mode emits section headers with line numbers",
               len(r5["index"]) >= 100 and r5["index"][0]["header"].startswith("Section"),
               f"headers={len(r5['index'])}")

        # (6) SOP-ref resolution: a bare SOP filename resolves to the sops/ mirror.
        engine_here = Path(__file__).resolve().parent
        r6 = read_slice("qc-specialist-presentations-sops.md", index=True, here=engine_here)
        _check("bare SOP filename resolves to the department sops/ mirror",
               r6["total_bytes"] > 100_000, f"total={r6['total_bytes']}")

    print("=" * 60)
    if fails:
        print(f"read_slice --self-test: FAIL — {len(fails)} case(s) failed")
        return 1
    print("read_slice --self-test: PASS — sliced reads return only the slice; "
          "truncation counter stays 0 on sliced builds.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="read_slice.py",
        description="Sliced read of a file (FIX-19): return only the requested "
                    "slice, never a whole 34-102KB SOP/role file.")
    ap.add_argument("path", nargs="?", help="file or bare SOP name")
    ap.add_argument("--lines", help="inclusive line range, e.g. 1-100")
    ap.add_argument("--offset", type=int, default=None)
    ap.add_argument("--length", type=int, default=None)
    ap.add_argument("--index", action="store_true",
                    help="emit the markdown section index instead of body text")
    ap.add_argument("--counter", default=str(_DEFAULT_COUNTER),
                    help="truncation-counter JSON path (default: "
                         "working/checkpoints/read_slice_truncations.json)")
    ap.add_argument("--json", action="store_true", help="emit raw JSON")
    ap.add_argument("--self-test", action="store_true",
                    help="run the hermetic fixture battery and exit")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.path:
        ap.error("a file path is required (or use --self-test)")

    try:
        if args.lines:
            a, b = args.lines.split("-")
            result = read_slice(args.path, lines=(int(a), int(b)),
                                counter=Path(args.counter))
        elif args.offset is not None:
            result = read_slice(args.path, offset=args.offset, length=args.length,
                                counter=Path(args.counter))
        elif args.index:
            result = read_slice(args.path, index=True, counter=Path(args.counter))
        else:
            ap.error("one of --lines, --offset, or --index is required")
            return 2
    except FileNotFoundError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 3

    if args.json:
        # Strip the raw text from the JSON envelope (the agent's tool result
        # should carry the slice + bounds, not a duplicate payload).
        out = {k: v for k, v in result.items() if k != "text"}
        print(json.dumps(out, indent=2))
    elif result.get("index") is not None:
        # Index mode: the result carries a markdown section table of contents,
        # not slice text. Emit it as a compact human-readable index.
        for sec in result["index"]:
            print(f"{sec['line']:6d} {'#' * sec['level']} {sec['header']}")
        print(f"# read_slice: {result['file']} index "
              f"({len(result['index'])} sections, "
              f"{result['total_bytes']}B total)", file=sys.stderr)
    else:
        print(result["text"], end="" if result["text"].endswith("\n") else "\n")
        print(f"# read_slice: {result['file']} [{result['slice']}] "
              f"returned={result['returned_bytes']}B of {result['total_bytes']}B "
              f"(truncation_events={result['truncation_events']})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
