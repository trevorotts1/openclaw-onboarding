#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_links_gate.py — fail-SOFT link-verification gate for stage 02 of the
Avatar-Alchemist BRAND pipeline (Skill 52). Implements PRD 7 / TODO Ph4 (O4).

Stage 02 (02-avatar-questions-31-32) emits 10 podcasts + 10 TED talks with links
and the source rule is: "every link verifies or degraded:search". This prover:

  * extracts the http(s) links from the stage-02 artifact,
  * does a BOUNDED HTTP check per link (short timeout) with ONE retry,
  * on success marks the link verified; on failure (4xx/5xx/timeout/DNS) marks it
    degraded and stamps the stage 'degraded:search' in a G-LINKS receipt.

FAIL-SOFT by design: an OFFLINE or unreachable box degrades to 'degraded:search'
and STILL exits 0 (the whole skill is offline-first; the web-search capability is
best-effort). It fails CLOSED (exit 2, AF-AV-LINKS-MISSING) ONLY when the stage-02
artifact is empty/absent — that is a real generation failure, not a link problem.

Network is OFF by default (so verify.sh / CI stay deterministic and offline);
pass --online to actually perform the bounded HTTP check on a client box.

stdlib only. Exit 0 = verified or degraded:search (soft), 2 = missing artifact,
3 = usage/IO error.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

STAGE_ID = "02-avatar-questions-31-32"
GATE = "G-LINKS"
DEGRADED = "degraded:search"
VERIFIED = "verified"

_URL_RE = re.compile(r"https?://[^\s)<>\]}\"']+", re.IGNORECASE)


def extract_links(text: str) -> List[str]:
    """Distinct http(s) URLs, trailing punctuation trimmed, order preserved."""
    out: List[str] = []
    seen = set()
    for m in _URL_RE.finditer(str(text)):
        url = m.group(0).rstrip(".,;:!?")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


# --- bounded HTTP fetch (injectable so the self-test is deterministic/offline) ---
def _http_fetch(url: str, timeout: float) -> int:
    """Return an HTTP status code (bounded by timeout). HEAD first, GET fallback.
    Raises on any transport error so check_link() can retry/degrade."""
    import urllib.request  # local import: keeps module import side-effect-free

    hdrs = {"User-Agent": "avatar-alchemist-linkcheck/1.0"}
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return int(getattr(r, "status", 200) or 200)
        except Exception:  # noqa: BLE001
            if method == "GET":
                raise
    raise RuntimeError("unreachable")


def check_link(url: str, fetch: Callable[[str, float], int],
               timeout: float = 5.0, retries: int = 1) -> Tuple[str, Any]:
    """One bounded check + `retries` retries. -> ('verified'|'degraded', info)."""
    last: Any = None
    for _ in range(retries + 1):
        try:
            code = int(fetch(url, timeout))
            if 200 <= code < 400:
                return VERIFIED, code
            last = code
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)[:80]
    return "degraded", last


def verify_stage(text: str, *, fetch: Optional[Callable[[str, float], int]] = None,
                 allow_network: bool = False, timeout: float = 5.0,
                 retries: int = 1, stage_id: str = STAGE_ID) -> Dict[str, Any]:
    """Build the G-LINKS receipt for a stage-02 artifact (fail-soft)."""
    links = extract_links(text)
    details: List[Dict[str, Any]] = []
    verified = degraded = 0

    if allow_network and links:
        fetch = fetch or _http_fetch
        for u in links:
            res, info = check_link(u, fetch, timeout, retries)
            details.append({"url": u, "result": res, "info": str(info)[:80]})
            if res == VERIFIED:
                verified += 1
            else:
                degraded += 1
        status = VERIFIED if (degraded == 0 and verified > 0) else DEGRADED
    else:
        # offline (default) OR no links present -> best-effort degraded:search.
        reason = "offline" if not allow_network else "no-links"
        for u in links:
            details.append({"url": u, "result": "unchecked", "info": reason})
        degraded = len(links)
        status = DEGRADED

    return {
        "gate": GATE,
        "stage": stage_id,
        "status": status,
        "total_links": len(links),
        "verified": verified,
        "degraded": degraded,
        "offline": not allow_network,
        "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rule": "every link verifies or degraded:search (fail-soft, PRD 7 / O4)",
        "details": details[:40],
    }


# ---------------------------------------------------------------------------
# self-test: deterministic, offline (fake fetch); proves verified / degraded /
# retry-recovery / offline / no-links, plus the fail-closed empty-artifact case.
# ---------------------------------------------------------------------------
_GOLDEN_LINKS = (
    "## Q31\n"
    "- The Quiet Authority — https://youtube.com/watch?v=aaa1\n"
    "- Booked and Grounded — https://youtube.com/watch?v=bbb2\n"
    "## Q32\n"
    "- Visibility without vanity — https://www.ted.com/talks/visibility_without_vanity\n"
)


def run_self_test() -> int:
    ok = True

    def ok_fetch(url: str, timeout: float) -> int:
        return 200

    def flaky_fetch(url: str, timeout: float) -> int:
        # every ...ted.com link 404s; podcasts 200 -> mixed -> degraded:search
        return 404 if "ted.com" in url else 200

    # stateful fetch: first call raises, second returns 200 -> proves the retry
    calls: Dict[str, int] = {}

    def retry_fetch(url: str, timeout: float) -> int:
        calls[url] = calls.get(url, 0) + 1
        if calls[url] == 1:
            raise TimeoutError("simulated first-attempt timeout")
        return 200

    # 1) all verified (online, healthy)
    r = verify_stage(_GOLDEN_LINKS, fetch=ok_fetch, allow_network=True)
    if r["status"] == VERIFIED and r["verified"] == 3 and r["degraded"] == 0:
        print("SELF-TEST ok: all links reachable -> status 'verified'.")
    else:
        ok = False; print(f"SELF-TEST FAIL: healthy check -> {r['status']} v={r['verified']} d={r['degraded']}")

    # 2) some links 404 -> degraded:search (soft, exit-0 path)
    r = verify_stage(_GOLDEN_LINKS, fetch=flaky_fetch, allow_network=True)
    if r["status"] == DEGRADED and r["degraded"] >= 1 and r["verified"] >= 1:
        print("SELF-TEST ok: partial failure -> status 'degraded:search' (fail-soft).")
    else:
        ok = False; print(f"SELF-TEST FAIL: partial check -> {r['status']} v={r['verified']} d={r['degraded']}")

    # 3) retry recovers a first-attempt failure
    res, info = check_link("https://youtube.com/watch?v=retry", retry_fetch, timeout=1, retries=1)
    if res == VERIFIED and calls.get("https://youtube.com/watch?v=retry") == 2:
        print("SELF-TEST ok: one retry recovers a transient failure -> 'verified'.")
    else:
        ok = False; print(f"SELF-TEST FAIL: retry -> {res} calls={calls}")

    # 4) offline (default) -> degraded:search, exit-0, marked offline
    r = verify_stage(_GOLDEN_LINKS, allow_network=False)
    if r["status"] == DEGRADED and r["offline"] and r["total_links"] == 3:
        print("SELF-TEST ok: offline box -> status 'degraded:search' (never blocks).")
    else:
        ok = False; print(f"SELF-TEST FAIL: offline -> {r['status']} offline={r['offline']}")

    # 5) no resolvable links (golden placeholder-note style) -> degraded:search
    r = verify_stage("## Q31\n- The Quiet Authority (link resolved at runtime)\n", allow_network=True)
    if r["status"] == DEGRADED and r["total_links"] == 0:
        print("SELF-TEST ok: no resolvable links -> status 'degraded:search' (best-effort).")
    else:
        ok = False; print(f"SELF-TEST FAIL: no-links -> {r['status']} n={r['total_links']}")

    # 6) NEGATIVE / fail-closed: an empty stage-02 artifact is a real generation
    #    failure -> AF-AV-LINKS-MISSING (exit 2), not a link degrade.
    if _stage_text_status("") is None and _stage_text_status("   \n") is None:
        print("SELF-TEST ok: empty stage-02 artifact fails closed (AF-AV-LINKS-MISSING).")
    else:
        ok = False; print("SELF-TEST FAIL: empty artifact not treated as missing.")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def _stage_text_status(text: str) -> Optional[str]:
    """None => missing (fail-closed); else the raw text."""
    return None if not str(text).strip() else text


def _handle(text: str, run_dir: Optional[Path], online: bool, timeout: float, retries: int) -> int:
    if _stage_text_status(text) is None:
        print(f"FAIL [AF-AV-LINKS-MISSING] stage '{STAGE_ID}' produced no non-empty artifact "
              f"(G-LINKS fail-closed).")
        return 2
    receipt = verify_stage(text, allow_network=online, timeout=timeout, retries=retries)
    if run_dir is not None:
        rec_dir = run_dir / "receipts"
        rec_dir.mkdir(parents=True, exist_ok=True)
        out = rec_dir / f"G-LINKS-{STAGE_ID}.json"
        out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(f"receipt -> {out}")
    print(f"G-LINKS status: {receipt['status']} "
          f"(links={receipt['total_links']} verified={receipt['verified']} "
          f"degraded={receipt['degraded']} offline={receipt['offline']})")
    return 0


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Avatar-Alchemist stage-02 link gate (fail-soft, PRD 7 / O4).")
    ap.add_argument("--run", help="run dir (reads artifacts/02-*.md, writes receipts/G-LINKS-*.json)")
    ap.add_argument("--stage-file", help="check a single stage-02 artifact file (read-only, prints receipt)")
    ap.add_argument("--online", action="store_true", help="actually perform the bounded HTTP check (default OFF/offline)")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()
    try:
        if args.run:
            run_dir = Path(args.run)
            art = run_dir / "artifacts" / f"{STAGE_ID}.md"
            text = art.read_text(encoding="utf-8", errors="replace") if art.is_file() else ""
            return _handle(text, run_dir, args.online, args.timeout, args.retries)
        if args.stage_file:
            p = Path(args.stage_file)
            text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
            return _handle(text, None, args.online, args.timeout, args.retries)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: {exc}")
        return 3
    print("USAGE ERROR: pass --run <dir> | --stage-file <file> | --self-test.")
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
