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

PRES-029: the validator NEVER overwrites the baseline. Baselines are the
immutable retrieval snapshots (presentation_job.retrieval_store); the
validator reads the baseline BEFORE any fetch, validates the claim against
the exact saved excerpt synthesis consumed, and records a freshness
re-fetch as a NEW snapshot version with a visible changed-source decision
(changed | unchanged | ad_drift | new). A changed source fails its
dependent claims (they must revise), never passes as unchanged.

PRES-030: the anchor word-overlap verdict stays a cheap mechanical filter.
A filter PASS then requires the bounded semantic entailment reviewer
(presentation_job.support_gate.review_claim -- deterministic numeric /
entity / unit / date / negation checks first, then a distinct reviewer
verdict supported / contradicted / insufficient with cited excerpt spans).
Only `supported` may become a factual slide assertion. Verdicts cache by
source-snapshot hash + claim hash + policy version; repair is per-claim
(claims_needing_repair maps failed claims to dependent slides).

Rollback (documented =0 path): PRESENTATION_CITATION_VALIDATION=0 disables
the gate entirely (same strip discipline as
research_web.web_fetch_enabled). Default unset/ON.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from presentation_job import research_web as _rw
from presentation_job import retrieval_store as _rs
from presentation_job import support_gate as _sg
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
    """PRES-029 baseline read: canonical_url -> content_sha256 from the
    IMMUTABLE baseline snapshots (first snapshot per canonical URL -- the
    exact evidence synthesis consumed), NOT from a ledger the validator
    itself rewrites.

    Called ONCE before the validation loop; the validator never writes the
    snapshot store except to append a NEW version on re-fetch (with a
    visible changed-source decision). A changed source therefore fails its
    claims instead of passing as re-anchored evidence. Kept for
    backward-compatible callers; new code paths use baseline_snapshot().
    """
    grouped = _rs.snapshots_by_canonical(run_dir)
    hashes: Dict[str, str] = {}
    for canon, snaps in grouped.items():
        if not canon or not snaps:
            continue
        sha = str(snaps[0].get("content_sha256") or "").strip()
        if sha:
            hashes[canon] = sha
    if hashes:
        return hashes
    # Legacy fallback: a run dir whose snapshots were never reconciled yet
    # (pre-PRES-029 ledger only). Recover first, then read baselines.
    try:
        _rs.recover_snapshots(run_dir)
    except Exception:  # noqa: BLE001 -- recovery is best-effort
        pass
    grouped = _rs.snapshots_by_canonical(run_dir)
    for canon, snaps in grouped.items():
        if not canon or not snaps:
            continue
        sha = str(snaps[0].get("content_sha256") or "").strip()
        if sha:
            hashes[canon] = sha
    return hashes


def _claim_id_for(citation: Dict[str, Any], index: int) -> str:
    """Stable claim ID persisted across research_map, copy and rendering
    manifests (PRES-030 step 4): item_id when the map declares one, else a
    deterministic cit-<index>-<hash8> derived from canonical URL + anchor."""
    item_id = str(citation.get("item_id") or "").strip()
    if item_id:
        return item_id
    seed = f"{citation.get('url', '')}|{citation.get('anchor', '')}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    return f"cit-{index:03d}-{digest}"


def claims_needing_repair(report: Dict[str, Any]) -> Dict[str, List[Any]]:
    """PRES-030 step 5, repair-by-claim: map each failed claim_id to the
    dependent slide(s) that must re-run. A single failed claim re-runs its
    reviewer + listed slides/QC, never the whole research/deck pipeline."""
    out: Dict[str, List[Any]] = {}
    for row in report.get("citations") or []:
        if row.get("supported"):
            continue
        out.setdefault(str(row.get("claim_id") or "unknown"), []).append(
            row.get("slide"))
    return out


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
    validate_against_fresh: bool = False,
) -> Dict[str, Any]:
    """Validate every required citation. Returns the report dict (ALSO
    written to working/research/citation_validation.json). `fetch_transport`
    is the injectable (url) -> (status, canonical, body) transport --
    default is the real SSRF-guarded _policy_fetch; proofs inject a stub so
    no network is ever dialed.

    PRES-029 default (validate_against_fresh=False): claims validate against
    the exact BASELINE snapshot synthesis consumed -- zero new network,
    zero new versions, freshness "reused". Pass validate_against_fresh=True
    for an explicit freshness audit: genuinely new bytes version a NEW
    snapshot with a visible changed-source decision (changed | unchanged |
    ad_drift), and `changed` fails its dependent claims (they must revise).
    """
    citations = load_citation_inventory(run_dir)["citations"]
    # PRES-029: the baseline is read ONCE, BEFORE any fetch, from the
    # immutable snapshot store -- and validation never overwrites it. The
    # old SMOKE-1 F29 "read the ledger after each fetch" discipline existed
    # because fetch_page appended the fresh row to the SAME ledger the
    # baseline was read from; comparing a fetch against the row it just
    # wrote could never mismatch. Snapshots fix the aliasing at the root:
    # baseline rows are immutable, fresh versions append as NEW snapshots
    # with a visible changed-source decision below.
    try:
        _rs.recover_snapshots(run_dir)
    except Exception:  # noqa: BLE001 -- recovery is best-effort
        pass
    baselines: Dict[str, Dict[str, Any]] = {}
    for canon in {_rw.canonical_url(c["url"]) for c in citations}:
        snap = _rs.baseline_snapshot(run_dir, canon)
        if snap is not None:
            baselines[canon] = snap
    fetcher = _rw.BoundedFetcher(
        run_dir, max_unique=max_unique,
        fetch_transport=fetch_transport, env=env)
    rows: List[Dict[str, Any]] = []
    resolve_cache: Dict[str, Dict[str, Any]] = {}  # canonical -> row (incl. refusals)
    for index, c in enumerate(citations):
        url = c["url"]
        canon = _rw.canonical_url(url)
        claim_id = _claim_id_for(c, index)
        baseline = baselines.get(canon)
        # PRES-029: claims validate against the BASELINE snapshot -- the
        # exact evidence synthesis consumed. Baselines carry a 200-char
        # preview only, so the full baseline excerpt is rehydrated from the
        # fetcher's recovered durable row (same bytes the research phase
        # fetched, zero new network) or, when the run dir predates durable
        # extracts, from one bounded fetch of the still-unseen URL.
        fetched: Dict[str, Any]
        transport_used = False
        baseline_full = ""
        if baseline is not None and int(baseline.get("status") or 0) \
                == 200 and str(baseline.get("extracted_preview") or ""):
            # Complete baseline (real status + real extract): validate
            # against it with zero new network.
            durable = fetcher.cache.get(canon) or {}
            baseline_full = str(durable.get("extracted") or "")
            if not baseline_full:
                baseline_full = str(
                    baseline.get("extracted_preview") or "")
            fetched = {
                "url": url,
                "canonical_url": canon,
                "status": int(baseline.get("status") or 0),
                "extracted": baseline_full,
                "extraction_length": len(baseline_full),
                "content_sha256": str(
                    baseline.get("content_sha256") or ""),
                "network_fetch": True,
                "fetch_ordinal": baseline.get("fetch_ordinal"),
                "baseline_retrieval_id": baseline.get("retrieval_id"),
            }
            resolve_cache.setdefault(canon, fetched)
        elif canon in resolve_cache:
            fetched = resolve_cache[canon]
        else:
            fetched = fetcher.fetch_page(url)
            resolve_cache[canon] = fetched
            # A recovered durable row surfacing here (the fetcher knew the
            # URL from restart recovery) is grounded evidence, not a fresh
            # fetch -- never a transport spend. Only a genuinely new
            # network hit counts.
            transport_used = bool(fetched.get("network_fetch")) and \
                fetched.get("fetch_ordinal") is None and \
                not fetcher.cache.get(canon)
        sha = str(fetched.get("content_sha256", "") or "")
        # PRES-029 freshness: an explicit re-fetch (validate_against_fresh,
        # below) versions a NEW snapshot with a visible changed-source
        # decision -- never a silent baseline replace. The default path
        # validates against the baseline with ZERO new network: freshness
        # stays "reused" and no new version is minted.
        freshness: Dict[str, Any] = {
            "decision": "reused",
            "baseline_retrieval_id": (baseline or {}).get("retrieval_id"),
            "evidence": ("baseline snapshot reused; no re-fetch "
                         "(validate_against_fresh=False)") if baseline
            else "no baseline snapshot for this canonical URL",
        }
        if (validate_against_fresh and baseline is not None and sha
                and fetched.get("network_fetch")):
            # Explicit freshness audit: spend exactly one bounded re-fetch
            # for this canonical URL (first citation mints it; later
            # citations reuse the versioned snapshot), then version the new
            # bytes as a NEW snapshot with a visible decision.
            fresh_text = ""
            if canon in resolve_cache and resolve_cache[canon].get(
                    "_fresh_text") is not None:
                fresh_text = str(resolve_cache[canon]["_fresh_text"])
                fresh_sha = str(resolve_cache[canon]["_fresh_sha"])
                fresh_status = int(resolve_cache[canon]["status"] or 0)
                fresh_query = resolve_cache[canon].get("query")
            else:
                # Force a real re-fetch past the recovered cache: the
                # fetcher reuses durable rows, so call the bounded
                # transport directly under the same policy.
                fresh_query = (fetcher.cache.get(canon) or {}).get("query")
                try:
                    transport = fetcher._fetch_transport
                    fresh_status, _fresh_canon, fresh_body = transport(url)
                    fresh_text = _rw.extract_text(fresh_body)
                    fresh_sha = _rs.sha256_text(fresh_body)
                except _rw.ResearchWebError as exc:
                    fresh_text = ""
                    fresh_sha = ""
                    fresh_status = 0
                    fresh_query = None
                    freshness = {
                        "decision": "refetch_failed",
                        "baseline_retrieval_id": baseline.get("retrieval_id"),
                        "evidence": f"freshness re-fetch refused: {exc}",
                    }
                resolve_cache[canon]["_fresh_text"] = fresh_text
                resolve_cache[canon]["_fresh_sha"] = fresh_sha
            if fresh_text:
                already = _rs.latest_snapshot(run_dir, canon)
                if already is None or \
                        already.get("content_sha256") != fresh_sha:
                    try:
                        fresh_snap = _rs.save_snapshot(
                            run_dir, query=fresh_query,
                            url=url, canonical_url=canon,
                            status=fresh_status,
                            body_or_excerpt=fresh_text, is_body=False,
                            raw_body_for_hash=None,
                            _content_sha_passthrough=fresh_sha)
                        cmp = _rs.compare_snapshot_to_baseline(baseline,
                                                               fresh_snap)
                        freshness = {
                            "decision": cmp["decision"],
                            "baseline_retrieval_id":
                                baseline.get("retrieval_id"),
                            "new_retrieval_id": fresh_snap["retrieval_id"],
                            "evidence": cmp["evidence"],
                        }
                    except _rs.SnapshotPersistenceError as exc:
                        freshness = {
                            "decision": "persistence_failed",
                            "baseline_retrieval_id":
                                baseline.get("retrieval_id"),
                            "evidence": str(exc),
                        }
                else:
                    freshness = {
                        "decision": "unchanged",
                        "baseline_retrieval_id": baseline.get("retrieval_id"),
                        "evidence": "re-fetch bytes identical to baseline "
                                    "content hash; no new version minted",
                    }
        verdict: Dict[str, Any]
        review: Optional[Dict[str, Any]] = None
        anchor = c["anchor"]
        if fetched.get("status") == 200 and freshness.get("decision") \
                == "changed":
            # Changed source: the baseline the claim was synthesized from no
            # longer holds. Dependent claims fail and must revise -- a fresh
            # fetch never re-anchors stale evidence as unchanged.
            verdict = {
                "anchor": anchor,
                "supported": False,
                "basis": None,
                "why": "changed-source: the re-fetched body differs from "
                       "the baseline snapshot in normalized substance "
                       f"({freshness.get('evidence')}). Dependent claims "
                       "must be revised against the new snapshot, never "
                       "passed as unchanged.",
            }
        elif anchor:
            # PRES-030: cheap mechanical filter first, then the DISTINCT
            # semantic reviewer. The filter owns reachability; the reviewer
            # owns truth. Only review-supported becomes a slide assertion.
            mechanical = fetcher.evaluate_anchor(fetched, anchor)
            if not mechanical.get("supported"):
                verdict = mechanical
            else:
                excerpt_text = _extracted(fetched)
                snap_hash = str(
                    (baseline or {}).get("content_sha256") or sha)
                claim_hash = hashlib.sha256(
                    anchor.encode("utf-8")).hexdigest()
                cached = _rs.lookup_validation(
                    run_dir, snap_hash, claim_hash,
                    _sg.POLICY_VERSION)
                if isinstance(cached, dict) and cached.get("verdict"):
                    review = cached
                else:
                    review = _sg.review_claim(
                        excerpt_text, anchor, claim_id=claim_id,
                        snapshot_hash=snap_hash, mechanical=mechanical)
                    _rs.store_validation(run_dir, snap_hash, claim_hash,
                                         _sg.POLICY_VERSION, review)
                verdict = {
                    "anchor": anchor,
                    "supported": review.get("verdict") == "supported",
                    "basis": ("semantic-" + str(review.get("verdict"))
                              if review.get("verdict") != "supported"
                              else "semantic-supported"),
                    "why": "; ".join(review.get("reasons") or []),
                    "review": review,
                }
        else:
            verdict = _content_floor_verdict(fetched)
        rows.append({
            "item_id": c["item_id"],
            "claim_id": claim_id,
            "slide": c["slide"],
            "url": url,
            "canonical_url": str(fetched.get("canonical_url") or canon),
            "anchor": anchor,
            "status": int(fetched.get("status", 0) or 0),
            "extraction_length": int(fetched.get("extraction_length", 0) or 0),
            "content_sha256": sha,
            "baseline_retrieval_id": (baseline or {}).get("retrieval_id"),
            "baseline_sha256": (baseline or {}).get("content_sha256"),
            "freshness": freshness,
            "network_fetch": bool(fetched.get("network_fetch")),
            "fetch_ordinal": fetched.get("fetch_ordinal"),
            "supported": bool(verdict.get("supported")),
            "basis": verdict.get("basis"),
            "why": verdict.get("why", "") or "",
            "refused": fetched.get("refused", "") or "",
            "review": review,
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
            "snapshot_policy": _rs.POLICY_VERSION,
            "entailment_policy": _sg.POLICY_VERSION,
            "reviewer": _sg.REVIEWER_ID,
        },
        "result": "pass" if not failures else "fail",
        "citations_total": len(rows),
        "unique_urls": len(resolve_cache),
        "network_fetches": sum(1 for v in resolve_cache.values()
                                if v.get("network_fetch")),
        "failures": failures,
        "citations": rows,
    }
    report["claims_needing_repair"] = claims_needing_repair(report)
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
