#!/usr/bin/env python3
"""FIX 20 -- citation-validation gate that actually fetches.

FIX 19's research phase retrieves real pages and records them in
working/research/retrieval_ledger.jsonl, but the pre-FIX-20
AF-RESEARCH-UNCITED gate in build_deck.py was a STRING COUNT: it counted
http(s) URLs in the research brief and never fetched a single one, so a
brief full of fabricated non-resolving URLs passed the gate. This module is
the validation half of AF-RESEARCH-UNCITED: it GET-fetches every required
citation under FIX 19's bounded public-network policy (HEAD alone is
insufficient) and requires, per citation:

  * HTTP 200 after the allowed redirects (BoundedFetcher._policy_fetch's
    200-only policy -- a non-200 final status refuses, never passes),
  * >= MIN_EXTRACT_CHARS (200) characters of RELEVANT extracted text
    (navigation/boilerplate stripped by research_web.extract_text),
  * the citation anchor matches by the EXACT-PHRASE (>= 8 normalized words)
    OR >= 60%-non-stopword-token test -- research_web.evaluate_anchor, the
    SAME relevance contract FIX 19 uses, so the two cannot drift,
  * content UNCHANGED since the FIX 19 retrieval (content_sha256 equals the
    retrieval ledger's row for the same canonical URL -- the
    "content-mismatched" fail case).

It fails on fabricated (non-resolving), unreachable, irrelevant,
private-network, over-cap, and content-mismatched sources. A URL that merely
resolves but does not support its anchor FAILS -- that is the whole point of
the gate.

Caching: one network fetch per canonical URL per validation run
(BoundedFetcher's cache, keyed by canonical URL; each row carries its
content_sha256). Duplicate citations of the same URL reuse the cached row,
so the report records one row PER CITATION while the fetch count stays one.
The validator ALSO holds its own resolve-cache for refused rows (a refused
fetch is never cached by BoundedFetcher -- the validator memoizes the
refusal so a fabricated URL cited three times costs exactly one attempt).

Report: one validation row per citation written to
working/research/citation_validation.json (alongside the FIX 19 retrieval
ledger; the FIX 20 input is that ledger + working/research/research_map.json
+ the research brief, and the report is the FIX 20 output).

Rollback (documented =0 path): PRESENTATION_CITATION_VALIDATION=0 disables
the gate entirely (same strip discipline as
research_web.web_fetch_enabled). Default unset/ON.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from presentation_job import research_web as _rw
from presentation_job.checkpoint import atomic_write_text

FLAG_ENV = "PRESENTATION_CITATION_VALIDATION"

# The FIX 20 input artifacts. RESEARCH_MAP_REL mirrors build_deck's constant
# (same SOP 9.5 artifact); BRIEF_GLOB mirrors the AF-RESEARCH-UNCITED gate's
# brief scan so a deck split across several brief files is fully covered.
RESEARCH_MAP_REL = "working/research/research_map.json"
BRIEF_GLOB = "working/research/brief-*.md"
CITATION_REPORT_REL = "working/research/citation_validation.json"


def citation_validation_enabled() -> bool:
    """Default ON. The only value that disables is exactly "0" (quotes and
    whitespace stripped, so an EMPTY value counts as unset, never OFF) --
    identical discipline to research_web.web_fetch_enabled / the dispatcher
    parallel flag."""
    raw = os.environ.get(FLAG_ENV)
    if raw is None:
        return True
    return raw.strip().strip("'\"") != "0"


# ---------------------------------------------------------------------------
# Citation inventory -- every required (URL, anchor) pair.
# ---------------------------------------------------------------------------
def _brief_urls(run_dir: Path) -> List[str]:
    """Every http(s) URL cited by the research brief(s), in file order."""
    urls: List[str] = []
    seen = set()
    for bm in sorted(run_dir.glob(BRIEF_GLOB)):
        try:
            text = bm.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in re.findall(r'https?://[^\s\)\]\>,\'"\\]+', text,
                              flags=re.IGNORECASE):
            u = str(raw).rstrip(".").strip()
            if u not in seen:
                seen.add(u)
                urls.append(u)
    return urls


def _map_citations(run_dir: Path) -> List[Dict[str, Any]]:
    """Every assigned[] item in research_map.json carrying a source_url -- the
    (URL, anchor) pairs the research-to-slide map declares. Returns [] when the
    map is absent or unparseable (the AF-RESEARCH-WEAVE gate owns that failure;
    this module only validates pairs it can read)."""
    map_path = run_dir / RESEARCH_MAP_REL
    if not map_path.is_file():
        return []
    try:
        obj = json.loads(map_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return []
    if not isinstance(obj, dict):
        return []
    out: List[Dict[str, Any]] = []
    for s in obj.get("slides") or []:
        if not isinstance(s, dict):
            continue
        for a in s.get("assigned") or []:
            if not isinstance(a, dict):
                continue
            url = str(a.get("source_url", "") or "").strip()
            if not url:
                continue
            out.append({
                "item_id": str(a.get("item_id", "") or "").strip(),
                "slide": s.get("slide"),
                "slug": str(obj.get("deck_slug", "") or ""),
                "url": url,
                "anchor": str(a.get("anchor", "") or "").strip(),
            })
    return out


def load_citation_inventory(run_dir: Path) -> Dict[str, Any]:
    """The complete citation set: map-declared (URL, anchor) pairs PLUS every
    brief URL (a brief URL without a map anchor is still a required citation --
    it must resolve, return 200, and yield >= 200 extracted chars; the anchor
    test applies only where an anchor exists). De-duplicated by (canonical
    URL, anchor, item_id) so the same pair is validated once per citation
    instance, but distinct anchors on one URL each get their own entry."""
    citations = _map_citations(run_dir)
    for u in _brief_urls(run_dir):
        if not any(c["url"] == u and c["anchor"] == "" for c in citations):
            citations.append({
                "item_id": "", "slide": None, "slug": "",
                "url": u, "anchor": "",
            })
    return {"citations": citations, "deck_slug": _deck_slug(run_dir)}


def _deck_slug(run_dir: Path) -> str:
    map_path = run_dir / RESEARCH_MAP_REL
    if not map_path.is_file():
        return ""
    try:
        obj = json.loads(map_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return ""
    return str(obj.get("deck_slug", "") or "") if isinstance(obj, dict) else ""


def _load_ledger_hashes(run_dir: Path) -> Dict[str, str]:
    """canonical_url -> content_sha256 for every NETWORK-FETCHED row in the
    FIX 19 retrieval ledger. The same canonical URL re-fetched with a DIFFERENT
    body is the "content-mismatch" fail case (evidence changed between the
    research phase and this validation run)."""
    ledger = run_dir / "working" / "research" / _rw.LEDGER_NAME
    if not ledger.is_file():
        return {}
    try:
        obj = json.loads(ledger.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    hashes: Dict[str, str] = {}
    for row in (obj or {}).get("rows") or []:
        if not isinstance(row, dict):
            continue
        if not row.get("network_fetch"):
            continue
        canon = str(row.get("canonical_url", "") or "").strip()
        sha = str(row.get("content_sha256", "") or "").strip()
        if canon and sha:
            hashes[canon] = sha
    return hashes


def _content_floor_verdict(fetched: Dict[str, Any]) -> Dict[str, Any]:
    """The no-anchor floor: HTTP 200 AND >= MIN_EXTRACT_CHARS relevant chars.
    (research_web.evaluate_anchor requires an anchor; a bare URL citation is
    validated against the content floor alone.)"""
    text = _extracted(fetched)
    verdict: Dict[str, Any] = {"anchor": ""}
    if fetched.get("status") != 200 or len(text) < _rw.MIN_EXTRACT_CHARS:
        verdict.update({
            "supported": False,
            "why": fetched.get("refused")
                   or f"HTTP {fetched.get('status')} / {len(text)} extracted chars "
                      f"(< {_rw.MIN_EXTRACT_CHARS})",
        })
        return verdict
    verdict.update({"supported": True, "basis": "content-floor (no anchor)"})
    return verdict


def _extracted(fetched: Dict[str, Any]) -> str:
    ext = fetched.get("extracted")
    return ext if isinstance(ext, str) else ""


# ---------------------------------------------------------------------------
# The gate.
# ---------------------------------------------------------------------------
def validate_citations(
    run_dir: Path,
    *,
    fetch_transport: Optional[Callable[[str], Tuple[int, str, str]]] = None,
    max_unique: int = _rw.MAX_UNIQUE_URLS,
    env: Optional[dict] = None,
) -> Dict[str, Any]:
    """Fetch + evaluate every required citation under the FIX 19 bounded
    public-network policy. Returns the report dict (ALSO written to
    working/research/citation_validation.json). `fetch_transport` is the
    injectable (url) -> (status, canonical, body) transport -- default is the
    real SSRF-guarded _policy_fetch; proofs inject a stub so no network is
    ever dialed."""
    citations = load_citation_inventory(run_dir)["citations"]
    fetcher = _rw.BoundedFetcher(
        run_dir, max_unique=max_unique,
        fetch_transport=fetch_transport, env=env)
    ledger_hashes = _load_ledger_hashes(run_dir)

    rows: List[Dict[str, Any]] = []
    resolve_cache: Dict[str, Dict[str, Any]] = {}  # canonical -> row (incl. refusals)
    for c in citations:
        url = c["url"]
        canon = _rw.canonical_url(url)
        if canon in resolve_cache:
            fetched = resolve_cache[canon]
        else:
            fetched = fetcher.fetch_page(url)
            resolve_cache[canon] = fetched
        verdict: Dict[str, Any]
        sha = str(fetched.get("content_sha256", "") or "")
        if fetched.get("status") == 200 and sha and canon in ledger_hashes \
                and ledger_hashes[canon] != sha:
            verdict = {
                "anchor": c["anchor"],
                "supported": False,
                "why": "content-mismatch: the fetched body no longer matches the "
                       "FIX 19 retrieval ledger's content_sha256 for this canonical "
                       "URL (evidence changed between phases)",
            }
        elif c["anchor"]:
            verdict = fetcher.evaluate_anchor(fetched, c["anchor"])
        else:
            verdict = _content_floor_verdict(fetched)
        rows.append({
            "item_id": c["item_id"],
            "slide": c["slide"],
            "url": url,
            "canonical_url": str(fetched.get("canonical_url") or canon),
            "anchor": c["anchor"],
            "status": int(fetched.get("status", 0) or 0),
            "extraction_length": int(fetched.get("extraction_length", 0) or 0),
            "content_sha256": sha,
            "network_fetch": bool(fetched.get("network_fetch")),
            "fetch_ordinal": fetched.get("fetch_ordinal"),
            "supported": bool(verdict.get("supported")),
            "basis": verdict.get("basis"),
            "why": verdict.get("why", "") or "",
            "refused": fetched.get("refused", "") or "",
        })

    failures = [
        {
            "url": r["url"],
            "anchor": r["anchor"],
            "item_id": r["item_id"],
            "status": r["status"],
            "extraction_length": r["extraction_length"],
            "why": r["why"] or r["refused"] or "unsupported",
        }
        for r in rows if not r["supported"]
    ]
    report = {
        "deck_slug": _deck_slug(run_dir),
        "validated_at": _rw._utcnow(),
        "gate": "AF-RESEARCH-UNCITED (FIX 20 citation validation)",
        "policy": {
            "max_unique_urls": max_unique,
            "min_extract_chars": _rw.MIN_EXTRACT_CHARS,
            "anchor_min_words": _rw.ANCHOR_MIN_WORDS,
            "anchor_token_match": _rw.ANCHOR_TOKEN_MATCH,
            "fetcher": "presentation_job.research_web.BoundedFetcher",
            "relevance": "presentation_job.research_web.evaluate_anchor",
        },
        "result": "pass" if not failures else "fail",
        "citations_total": len(rows),
        "unique_urls": len(resolve_cache),
        "network_fetches": sum(1 for v in resolve_cache.values()
                                if v.get("network_fetch")),
        "failures": failures,
        "citations": rows,
    }
    try:
        path = run_dir / CITATION_REPORT_REL
        atomic_write_text(path, json.dumps(report, indent=2, ensure_ascii=False))
    except OSError:
        pass  # report write is best-effort; the in-memory verdicts still bind
    return report


def check_citations(
    run_dir: Path,
    *,
    fetch_transport: Optional[Callable[[str], Tuple[int, str, str]]] = None,
    max_unique: int = _rw.MAX_UNIQUE_URLS,
    env: Optional[dict] = None,
) -> str:
    """The gate entry point consumed by build_deck._chk_citation_validated.
    Returns "" when every required citation verifies (or when there is nothing
    to verify), else the AF-RESEARCH-UNCITED failure reason naming the
    validation report."""
    report = validate_citations(
        run_dir, fetch_transport=fetch_transport,
        max_unique=max_unique, env=env)
    if report["result"] == "pass":
        return ""
    bad = report["failures"]
    detail = "; ".join(
        f"{f['url']} (status={f['status']}, {f['extraction_length']} chars, "
        f"anchor={f['anchor'] or '<none>'}): {f['why']}"
        for f in bad[:6]
    )
    if len(bad) > 6:
        detail += f"; ... and {len(bad) - 6} more"
    return (
        f"AF-RESEARCH-UNCITED: citation validation FAILED -- {len(bad)} of "
        f"{report['citations_total']} required citation(s) did not verify against "
        f"the public web under the FIX 19 bounded fetch policy (HTTP 200 + "
        f">= {_rw.MIN_EXTRACT_CHARS} relevant extracted chars + anchor match by "
        f"exact-phrase/60%-token, content hash unchanged from the retrieval "
        f"ledger). Fabricated, unreachable, irrelevant, private-network, over-cap, "
        f"and content-mismatched sources ALL FAIL. Full per-citation record: "
        f"{CITATION_REPORT_REL}. First failures: {detail}"
    )
