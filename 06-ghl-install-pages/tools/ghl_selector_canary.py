#!/usr/bin/env python3
"""ghl_selector_canary.py — selector-drift canary + STOP-with-snapshot resolver (U2 / F3).

WHY THIS EXISTS
----------------
26 of the 28 GHL runtime gates are resolved at act-time against a live snapshot
(gates.json). GHL ships UI changes frequently; refs churn every snapshot; icon-only
toolbar buttons have no accessible name; label drift is real (`Add survey` not
`Create survey`; the Websites tab is an `<a>`, not `role=tab`). Left unmanaged this
is a chronic tax: a client build hits the drift, STOPS mid-run, and the fleet learns
about it one client at a time.

This module gives every anchor documented in the four SELECTORS-LIVE-*.md docs a
MACHINE-READABLE, ORDERED fallback chain (``selectors-live.json``, loaded by
``load_selectors()``) and two things builders/operators actually run:

  1. ``resolve_anchor()`` — the STOP-with-snapshot resolver. Any builder that needs
     to act on a locked anchor calls this instead of hand-rolling selector logic.
     It walks primary -> fallbacks IN ORDER, using a caller-supplied ``finder``
     (the live DOM/snapshot lookup — dependency-injected so this module stays
     network-free and unit-testable). The FIRST hit wins. If nothing in the chain
     resolves, it raises ``SelectorMissError`` carrying the anchor id, the full
     chain that was tried, and a snapshot excerpt for a 5-minute re-capture — it
     NEVER falls through to a guessed CSS selector or a blind coordinate click.
     This is the mechanical form of the D8 "never invent a selector" doctrine.

  2. ``run_canary()`` / the ``--canary`` CLI — a READ-ONLY weekly (or pre-build
     optional) walk of every anchor in the four object docs against the live DOM
     on the operator test sub-account. It never creates or deletes a GHL object;
     it only resolves each anchor via the same STOP-with-snapshot resolver and
     reduces the per-anchor outcomes into a drift report: found / found-by-fallback
     / MISSING. A MISSING anchor files a board card (fail-soft) BEFORE any client
     build hits it — drift is detected once, fleet-wide, not per-client.

  3. ``run_iframe_survival_check()`` / the ``--iframe-survival`` CLI (P3-04 c4)
     — a READ-ONLY weekly companion check that a set of PUBLISHED GHL pages/
     surveys/forms still embed their cross-origin (``*.leadconnectorhq.com``)
     iframe. Iframe survival was proven ONCE (2026-06-27 probe: GHL preview
     does not strip iframes) but never continuously guarded — this closes that
     gap in the same read-only, dependency-injected, fail-soft-board-notify
     shape as ``run_canary()`` (a caller-supplied ``page_fetcher`` does the
     real HTTP GET / agent-browser snapshot; this module performs no network
     I/O of its own). A stripped iframe reuses cc_board.py's existing
     ``VERIFY-FAIL`` taxonomy value (a post-publish render/verification check
     failing is exactly F6's shape) — it deliberately never invents a 7th
     cc_board taxonomy value.

This module performs NO GHL I/O of its own (same discipline as ghl_object_router):
callers inject a ``finder`` / ``page_fetcher`` callable. In production a finder
wraps a live ``agent-browser`` snapshot (see ``live_finder_over_browser_manager``
for the wiring sketch — deliberately NOT exercised by CI, since it needs a real
seeded session) and a page_fetcher wraps a real HTTP GET of a public published-
page URL (see ``live_page_fetcher_over_http``, same discipline). ``--selftest``
and the pytest suite drive the full decision path with fake finders/fetchers: no
network, no browser, no GHL writes.

USAGE
-----
    import ghl_selector_canary as canary
    data = canary.load_selectors()
    anchor = canary.get_anchor(data, "form.builder.save")
    ref = canary.resolve_anchor(anchor, finder=my_snapshot_finder)

    report = canary.run_canary(data, finder=my_snapshot_finder,
                                evidence_root="/tmp/run01")
    print(report.summary())

    targets = canary.load_iframe_survival_targets()["targets"]
    report2 = canary.run_iframe_survival_check(targets, page_fetcher=my_page_fetcher)
    print(report2.summary())

    # CLI
    python3 ghl_selector_canary.py --matrix                  # print anchor counts
    python3 ghl_selector_canary.py --matrix --object-type form
    python3 ghl_selector_canary.py --canary --evidence-root /tmp/canary --selftest
    python3 ghl_selector_canary.py --iframe-survival --evidence-root /tmp/canary --selftest-finder
    python3 ghl_selector_canary.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional

CANARY_VERSION = "v1.1.0"  # P3-04 (c)4: + run_iframe_survival_check / --iframe-survival

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SELECTORS_PATH = os.path.join(_HERE, "selectors-live.json")
DEFAULT_IFRAME_TARGETS_PATH = os.path.join(_HERE, "iframe-survival-targets.json")

VALID_OBJECT_TYPES = ("form", "survey", "funnel", "page")

# Board failure-taxonomy prefix used by cc_board (U9 item 3) — reused here so a
# canary MISS is queryable the same way a live build's SELECTOR-MISS stop is.
BOARD_NOTE_SELECTOR_MISS = "SELECTOR-MISS"
BOARD_NOTE_SELECTOR_GAP = "SELECTOR-GAP"  # known-undocumented surface, not a regression

# Board failure-taxonomy prefix for the iframe-survival check (P3-04 c4). A
# stripped iframe on a published page is a post-publish render/verification
# check failing — exactly cc_board.py's F6 "VERIFY-FAIL" shape (sealed
# verifier / render_check did not PASS). REUSES that existing value; this
# module never invents a 7th cc_board taxonomy entry (see cc_board.py's own
# "_CC_BLOCK_REASONS drifted from spec taxonomy" self-check).
BOARD_NOTE_IFRAME_SURVIVAL_MISS = "VERIFY-FAIL"

# Cross-origin iframe host proven to survive GHL publish (2026-06-27 probe).
# Overridable per-call (run_iframe_survival_check(..., iframe_src_marker=...))
# for a target embedded on a different host.
DEFAULT_IFRAME_SRC_MARKER = "leadconnectorhq.com"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_selectors(path: Optional[str] = None) -> Dict[str, Any]:
    """Load selectors-live.json. Raises FileNotFoundError / json errors as-is —
    a missing/corrupt selector doc is a build-blocking config error, not
    something to silently default around."""
    p = path or DEFAULT_SELECTORS_PATH
    with open(p, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "objects" not in data:
        raise ValueError(f"{p}: missing top-level 'objects' key — not a valid selectors-live.json")
    return data


def iter_anchors(data: Dict[str, Any], object_types: Optional[List[str]] = None
                  ) -> List[Dict[str, Any]]:
    """Flatten data['objects'][*]['anchors'] into a list, each anchor dict
    stamped with its parent object_type and doc for reporting."""
    want = set(object_types) if object_types else None
    out: List[Dict[str, Any]] = []
    for obj_type, obj in data.get("objects", {}).items():
        if want and obj_type not in want:
            continue
        for anchor in obj.get("anchors", []):
            stamped = dict(anchor)
            stamped["object_type"] = obj_type
            stamped["doc"] = obj.get("doc")
            out.append(stamped)
    return out


def get_anchor(data: Dict[str, Any], anchor_id: str) -> Dict[str, Any]:
    for anchor in iter_anchors(data):
        if anchor["id"] == anchor_id:
            return anchor
    raise KeyError(f"no anchor with id {anchor_id!r} in selectors-live.json")


def load_iframe_survival_targets(path: Optional[str] = None) -> Dict[str, Any]:
    """Load iframe-survival-targets.json — the weekly check's target list
    (published GHL page/survey/form URLs on the operator test sub-account).
    Same fail-loud discipline as load_selectors(): a missing/corrupt targets
    doc is a config error, not something to silently default around. An
    EMPTY ``targets`` array is valid (the check simply reports zero targets,
    clean) — this repo intentionally ships no live client URLs; the operator
    populates real published-page URLs on the box that runs the weekly cron."""
    p = path or DEFAULT_IFRAME_TARGETS_PATH
    with open(p, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "targets" not in data:
        raise ValueError(f"{p}: missing top-level 'targets' key — not a valid iframe-survival-targets.json")
    return data


# ---------------------------------------------------------------------------
# STOP-with-snapshot resolver — the mechanical "never blind-click" gate
# ---------------------------------------------------------------------------
class SelectorMissError(Exception):
    """Raised when an anchor's full chain (primary + every fallback) fails to
    resolve against the live snapshot. Carries everything an operator needs to
    re-capture in ~5 minutes: the anchor id, the exact chain that was tried
    (in order), and a snapshot excerpt. A caller that catches this MUST STOP the
    current build phase — it must never proceed on a guessed/blind selector."""

    def __init__(self, anchor_id: str, target: str, chain_tried: List[Dict[str, Any]],
                 snapshot_excerpt: Any = None):
        self.anchor_id = anchor_id
        self.target = target
        self.chain_tried = chain_tried
        self.snapshot_excerpt = snapshot_excerpt
        super().__init__(
            f"SELECTOR-MISS: anchor {anchor_id!r} ({target}) — "
            f"{len(chain_tried)} candidate(s) tried, none resolved. STOP — no blind click."
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "target": self.target,
            "chain_tried": self.chain_tried,
            "snapshot_excerpt": self.snapshot_excerpt,
        }


@dataclass
class ResolveResult:
    anchor_id: str
    object_type: str
    target: str
    status: str          # "primary" | "fallback" | "missing" | "gap"
    used_index: int       # -1 for primary, else index into fallbacks (0-based)
    used_candidate: Dict[str, Any]
    ref: Any = None


def _candidate_chain(anchor: Dict[str, Any]) -> List[Dict[str, Any]]:
    chain = [anchor["primary"]]
    chain.extend(anchor.get("fallbacks", []) or [])
    return chain


def resolve_anchor(anchor: Dict[str, Any],
                    finder: Callable[[Dict[str, Any], Dict[str, Any]], Any],
                    snapshot_provider: Optional[Callable[[], Any]] = None
                    ) -> ResolveResult:
    """Walk anchor['primary'] then anchor['fallbacks'] IN ORDER. ``finder(anchor,
    candidate) -> ref | None`` is the caller-supplied live lookup (real
    implementation snapshots the DOM and matches the candidate descriptor; test
    doubles return a canned ref or None). The FIRST candidate that resolves wins
    — later candidates are never tried once one succeeds, and no candidate is
    ever skipped in favor of "close enough".

    A documented ``page.builder.chrome``-style KNOWN-GAP anchor (confidence 0,
    primary.text == "UNDOCUMENTED") short-circuits to status "gap" without
    calling the finder at all — it is not a regression to report, it is an
    honestly-listed absence from the source docs (§E gap doctrine).

    On total miss: raises SelectorMissError with the full chain + a snapshot
    excerpt (from ``snapshot_provider()`` if given) attached. NEVER returns a
    guessed ref."""
    if anchor.get("confidence") == 0 and anchor.get("primary", {}).get("text") == "UNDOCUMENTED":
        return ResolveResult(anchor["id"], anchor.get("object_type", ""), anchor["target"],
                              "gap", -1, anchor["primary"], None)

    chain = _candidate_chain(anchor)
    for idx, candidate in enumerate(chain):
        ref = finder(anchor, candidate)
        if ref:
            status = "primary" if idx == 0 else "fallback"
            return ResolveResult(anchor["id"], anchor.get("object_type", ""), anchor["target"],
                                  status, -1 if idx == 0 else idx - 1, candidate, ref)

    excerpt = None
    if snapshot_provider is not None:
        try:
            excerpt = snapshot_provider()
        except Exception as exc:  # pragma: no cover - snapshot capture is best-effort
            excerpt = {"snapshot_capture_error": str(exc)}
    raise SelectorMissError(anchor["id"], anchor["target"], chain, excerpt)


# ---------------------------------------------------------------------------
# The weekly (or pre-build-optional) read-only canary
# ---------------------------------------------------------------------------
@dataclass
class CanaryReport:
    started_at: float
    finished_at: float = 0.0
    object_types: List[str] = field(default_factory=list)
    results: List[Dict[str, Any]] = field(default_factory=list)
    misses: List[Dict[str, Any]] = field(default_factory=list)
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    canary_version: str = CANARY_VERSION

    def summary(self) -> Dict[str, Any]:
        counts = {"primary": 0, "fallback": 0, "missing": 0, "gap": 0}
        for r in self.results:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        return {
            "total_anchors": len(self.results),
            "counts": counts,
            "misses": [m["anchor_id"] for m in self.misses],
            "gaps": [g["anchor_id"] for g in self.gaps],
            "clean": len(self.misses) == 0,
            "duration_s": round(self.finished_at - self.started_at, 3),
        }

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["summary"] = self.summary()
        return d


def run_canary(data: Dict[str, Any],
                finder: Callable[[Dict[str, Any], Dict[str, Any]], Any],
                evidence_root: Optional[str] = None,
                object_types: Optional[List[str]] = None,
                snapshot_provider: Optional[Callable[[], Any]] = None,
                board_notifier: Optional[Callable[[Dict[str, Any]], None]] = None
                ) -> CanaryReport:
    """READ-ONLY drift scan. Every anchor is resolved independently via
    resolve_anchor() — a MISS on one anchor never blocks scanning the rest (this
    is a scan, not a build), but each individual resolution still obeys
    STOP-with-snapshot semantics: no anchor is ever guessed. On a MISS,
    board_notifier (fail-soft, like every cc_board call) is invoked with a
    BOARD_NOTE_SELECTOR_MISS-prefixed payload so drift becomes a queryable board
    card before any client build hits it."""
    report = CanaryReport(started_at=time.time(), object_types=list(object_types or VALID_OBJECT_TYPES))
    for anchor in iter_anchors(data, object_types):
        try:
            res = resolve_anchor(anchor, finder, snapshot_provider)
            entry = {
                "anchor_id": res.anchor_id, "object_type": res.object_type,
                "target": res.target, "status": res.status,
                "used_candidate": res.used_candidate,
            }
            report.results.append(entry)
            if res.status == "gap":
                report.gaps.append(entry)
        except SelectorMissError as miss:
            entry = {
                "anchor_id": miss.anchor_id, "object_type": anchor.get("object_type", ""),
                "target": miss.target, "status": "missing",
                "chain_tried": miss.chain_tried, "snapshot_excerpt": miss.snapshot_excerpt,
            }
            report.results.append(entry)
            report.misses.append(entry)
            if board_notifier is not None:
                try:
                    board_notifier({"prefix": BOARD_NOTE_SELECTOR_MISS, **entry})
                except Exception:
                    pass  # board calls are fail-soft, never block the canary
    report.finished_at = time.time()

    if evidence_root:
        os.makedirs(evidence_root, exist_ok=True)
        out_path = os.path.join(evidence_root,
                                 f"selector-canary-{int(report.started_at)}.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh, indent=2, sort_keys=True)
        report.results_path = out_path  # type: ignore[attr-defined]

    return report


# ---------------------------------------------------------------------------
# Weekly iframe-survival check (P3-04 c4) — same read-only / DI discipline as
# run_canary() above, checking a different property: does a PUBLISHED page
# still embed its cross-origin iframe (2026-06-27 probe: GHL preview does not
# strip it — this makes that proof CONTINUOUS instead of a one-time snapshot).
# ---------------------------------------------------------------------------
@dataclass
class IframeSurvivalReport:
    started_at: float
    finished_at: float = 0.0
    results: List[Dict[str, Any]] = field(default_factory=list)
    misses: List[Dict[str, Any]] = field(default_factory=list)
    canary_version: str = CANARY_VERSION

    def summary(self) -> Dict[str, Any]:
        return {
            "total_targets": len(self.results),
            "misses": [m["target"] for m in self.misses],
            "clean": len(self.misses) == 0,
            "duration_s": round(self.finished_at - self.started_at, 3),
        }

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["summary"] = self.summary()
        return d


def run_iframe_survival_check(
    targets: List[Dict[str, str]],
    page_fetcher: Callable[[str], str],
    evidence_root: Optional[str] = None,
    board_notifier: Optional[Callable[[Dict[str, Any]], None]] = None,
    iframe_src_marker: str = DEFAULT_IFRAME_SRC_MARKER,
) -> IframeSurvivalReport:
    """READ-ONLY weekly check that every PUBLISHED target in ``targets`` still
    embeds its cross-origin (``iframe_src_marker``) iframe. Mirrors
    run_canary()'s shape exactly: no network of its own (``page_fetcher(url)
    -> html`` is caller-injected — a real HTTP GET or agent-browser snapshot
    in production, a canned string in tests), one target's failure never
    blocks scanning the rest, and a MISS fail-softly notifies
    ``board_notifier`` (never lets a board outage crash the scan) with the
    REUSED VERIFY-FAIL taxonomy value (never a 7th cc_board category).

    targets: ``[{"id": "...", "url": "https://...", "object_type": "survey"}, ...]``
    — see load_iframe_survival_targets() / iframe-survival-targets.json for the
    on-disk schema this list is normally loaded from.

    A target whose page_fetcher call raises is recorded as a "fetch-error"
    MISS (also board-notified) rather than crashing the whole weekly run —
    one unreachable page must never hide the rest of the report."""
    report = IframeSurvivalReport(started_at=time.time())
    for t in targets:
        entry: Dict[str, Any] = {
            "target": t["id"], "object_type": t.get("object_type", ""), "url": t["url"],
        }
        try:
            html = page_fetcher(t["url"]) or ""
        except Exception as exc:
            entry["status"] = "fetch-error"
            entry["error"] = str(exc)
            report.results.append(entry)
            report.misses.append(entry)
            if board_notifier is not None:
                try:
                    board_notifier({"prefix": BOARD_NOTE_IFRAME_SURVIVAL_MISS, **entry})
                except Exception:
                    pass  # board calls are fail-soft, never block the check
            continue

        survived = ("<iframe" in html) and (iframe_src_marker in html)
        entry["status"] = "survived" if survived else "stripped"
        report.results.append(entry)
        if not survived:
            report.misses.append(entry)
            if board_notifier is not None:
                try:
                    board_notifier({"prefix": BOARD_NOTE_IFRAME_SURVIVAL_MISS, **entry})
                except Exception:
                    pass  # board calls are fail-soft, never block the check
    report.finished_at = time.time()

    if evidence_root:
        os.makedirs(evidence_root, exist_ok=True)
        out_path = os.path.join(evidence_root,
                                 f"iframe-survival-{int(report.started_at)}.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh, indent=2, sort_keys=True)
        report.results_path = out_path  # type: ignore[attr-defined]

    return report


# ---------------------------------------------------------------------------
# Live finder wiring sketch (NOT exercised by tests — needs a real seeded
# session). Kept here so a builder wires the canary to browser_manager without
# re-deriving the resolver contract.
# ---------------------------------------------------------------------------
def live_finder_over_browser_manager(session: str, ab_eval: Callable[[str, str], str]
                                      ) -> Callable[[Dict[str, Any], Dict[str, Any]], Any]:
    """Return a finder() suitable for resolve_anchor()/run_canary() that drives a
    real seeded agent-browser session. ``ab_eval(session, js_expr) -> str`` is the
    thin wrapper around ``browser_manager.sh eval`` the caller already has (kept
    injectable so this module never shells out itself — same discipline as
    ghl_object_router). A live capture run (W2) or the weekly cron canary passes
    this factory's output into run_canary(); offline tests never call it."""

    def _finder(anchor: Dict[str, Any], candidate: Dict[str, Any]) -> Any:
        kind = candidate.get("kind")
        if kind == "role_name":
            expr = f"find role {candidate.get('role')} name {json.dumps(candidate.get('name', ''))}"
        elif kind == "placeholder":
            expr = f"find placeholder {json.dumps(candidate.get('text', ''))}"
        elif kind == "text":
            expr = f"find text {json.dumps(candidate.get('text', ''))}"
        elif kind == "menuitem":
            expr = f"find role menuitem name {json.dumps(candidate.get('name', ''))}"
        else:
            # svg_d_signature / order / coordinate_recipe are runtime-capture by
            # design — the live wiring for those is the builder's own snapshot
            # walk, not a single find expression. Report "not found" here rather
            # than fabricate a match.
            return None
        result = ab_eval(session, expr)
        return result or None

    return _finder


def live_page_fetcher_over_http() -> Callable[[str], str]:
    """Return a page_fetcher() suitable for run_iframe_survival_check() that
    performs a real HTTP GET of a published page's PUBLIC url (a published
    GHL preview/live page needs no auth — that is the same 2026-06-27 probe
    this check makes continuous). Kept as a thin, injectable FACTORY (same
    discipline as live_finder_over_browser_manager) — constructing it performs
    NO network I/O; only calling the returned function does. Deliberately NOT
    exercised by CI / --selftest; only the weekly cron or a live wiring calls
    the returned callable."""

    def _fetch(url: str) -> str:
        import urllib.request

        with urllib.request.urlopen(url, timeout=20) as resp:  # noqa: S310 - public GET, read-only
            return resp.read().decode("utf-8", errors="replace")

    return _fetch


# ---------------------------------------------------------------------------
# Offline selftest — no network, no browser, no GHL writes
# ---------------------------------------------------------------------------
def _selftest() -> int:
    data = load_selectors()

    # 1. Schema sanity: every anchor has the required fields, every object type
    #    from the spec (form/survey/funnel/page) is present.
    for obj_type in VALID_OBJECT_TYPES:
        assert obj_type in data["objects"], f"missing object type {obj_type}"
    anchors = iter_anchors(data)
    assert len(anchors) >= 4 * 5, "suspiciously few anchors loaded"
    ids_seen = set()
    for a in anchors:
        for req in ("id", "target", "primary", "confidence", "runtime_capture"):
            assert req in a, f"anchor missing required field {req}: {a}"
        assert a["id"] not in ids_seen, f"duplicate anchor id {a['id']}"
        ids_seen.add(a["id"])
        assert "kind" in a["primary"], f"anchor {a['id']} primary has no 'kind'"

    # 2. resolve_anchor: primary hit.
    always_hit = lambda anchor, candidate: {"ref": "fake-ref"}
    save_anchor = get_anchor(data, "form.builder.save")
    res = resolve_anchor(save_anchor, always_hit)
    assert res.status == "primary" and res.ref == {"ref": "fake-ref"}

    # 3. resolve_anchor: primary miss, fallback hit.
    search_anchor = get_anchor(data, "form.list.search")
    assert search_anchor.get("fallbacks"), "test anchor must have a fallback to exercise this path"
    def _fallback_only(anchor, candidate):
        return None if candidate is anchor["primary"] else "fallback-ref"
    res2 = resolve_anchor(search_anchor, _fallback_only)
    assert res2.status == "fallback"

    # 4. resolve_anchor: total miss -> SelectorMissError, never a guessed ref.
    never_hit = lambda anchor, candidate: None
    try:
        resolve_anchor(save_anchor, never_hit, snapshot_provider=lambda: {"nodes": []})
        raise AssertionError("expected SelectorMissError on total miss")
    except SelectorMissError as miss:
        assert miss.anchor_id == "form.builder.save"
        assert miss.snapshot_excerpt == {"nodes": []}
        assert len(miss.chain_tried) >= 1

    # 5. Known-gap anchor short-circuits without calling finder.
    gap_anchor = get_anchor(data, "page.builder.chrome")
    calls = []
    def _spy(anchor, candidate):
        calls.append(candidate)
        return None
    res3 = resolve_anchor(gap_anchor, _spy)
    assert res3.status == "gap"
    assert calls == [], "gap anchors must short-circuit without probing the live DOM"

    # 6. run_canary: mixed outcome (some hit, one total miss) reduces correctly
    #    and never raises out of the scan.
    def _mixed(anchor, candidate):
        if anchor["id"] == "form.builder.save":
            return None  # force this one to MISS through the whole chain
        return "ref"
    notified = []
    report = run_canary(data, _mixed, object_types=["form"],
                         board_notifier=lambda payload: notified.append(payload))
    assert report.summary()["total_anchors"] == len(iter_anchors(data, ["form"]))
    assert "form.builder.save" in report.summary()["misses"]
    assert len(notified) == 1 and notified[0]["prefix"] == BOARD_NOTE_SELECTOR_MISS

    # 7. run_canary: a failing board_notifier must not crash the scan (fail-soft).
    def _boom(payload):
        raise RuntimeError("board is down")
    report2 = run_canary(data, _mixed, object_types=["form"], board_notifier=_boom)
    assert report2.summary()["clean"] is False  # still surfaces the miss locally

    # 8. run_canary: evidence_root writes a report file.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        report3 = run_canary(data, always_hit, object_types=["survey"], evidence_root=tmp)
        assert report3.summary()["clean"] is True
        written = [f for f in os.listdir(tmp) if f.startswith("selector-canary-")]
        assert len(written) == 1
        with open(os.path.join(tmp, written[0])) as fh:
            on_disk = json.load(fh)
        assert on_disk["summary"]["clean"] is True

    # 9. live_finder_over_browser_manager: pure expression-building, no I/O.
    seen_exprs = []
    def _fake_ab_eval(session, expr):
        seen_exprs.append(expr)
        return "found"
    finder = live_finder_over_browser_manager("sess", _fake_ab_eval)
    r = finder(save_anchor, save_anchor["primary"])
    assert r == "found" and "role button" in seen_exprs[-1] and "Save" in seen_exprs[-1]
    r2 = finder(save_anchor, {"kind": "svg_d_signature", "d": "x", "order": 1})
    assert r2 is None  # runtime-capture kinds never fabricate a live match

    # 10. run_iframe_survival_check: mixed outcome (one survives, one
    #     stripped) reduces correctly, board-notifies with the REUSED
    #     VERIFY-FAIL taxonomy value (never a 7th), and never raises.
    assert BOARD_NOTE_IFRAME_SURVIVAL_MISS == "VERIFY-FAIL"
    survived_html = '<html><iframe src="https://forms.leadconnectorhq.com/widget/survey/x"></iframe></html>'
    stripped_html = "<html><p>no iframe here</p></html>"
    def _page_fetcher(url):
        return survived_html if url.endswith("ok") else stripped_html
    iframe_targets = [
        {"id": "survey.ok", "url": "https://x/ok", "object_type": "survey"},
        {"id": "survey.stripped", "url": "https://x/stripped", "object_type": "survey"},
    ]
    iframe_notified = []
    iframe_report = run_iframe_survival_check(
        iframe_targets, _page_fetcher,
        board_notifier=lambda payload: iframe_notified.append(payload),
    )
    iframe_summary = iframe_report.summary()
    assert iframe_summary["total_targets"] == 2
    assert iframe_summary["misses"] == ["survey.stripped"]
    assert len(iframe_notified) == 1
    assert iframe_notified[0]["prefix"] == "VERIFY-FAIL"

    # 11. live_page_fetcher_over_http: pure lazy factory, no network at
    #     construction time.
    fetcher = live_page_fetcher_over_http()
    assert callable(fetcher)

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_matrix(data: Dict[str, Any], object_types: Optional[List[str]]) -> None:
    anchors = iter_anchors(data, object_types)
    by_type: Dict[str, int] = {}
    for a in anchors:
        by_type[a["object_type"]] = by_type.get(a["object_type"], 0) + 1
    print(json.dumps({
        "version": data.get("version"),
        "captured": data.get("captured"),
        "total_anchors": len(anchors),
        "anchors_by_object_type": by_type,
    }, indent=2, sort_keys=True))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="run offline selftest, no network/browser")
    ap.add_argument("--matrix", action="store_true", help="print the loaded anchor matrix summary")
    ap.add_argument("--canary", action="store_true",
                     help="run the read-only canary (requires a live finder; without one, "
                          "combine with --selftest-finder for an offline dry run)")
    ap.add_argument("--iframe-survival", action="store_true",
                     help="run the read-only weekly iframe-survival check (P3-04 c4; requires a "
                          "live page_fetcher; without one, combine with --selftest-finder for an "
                          "offline dry run)")
    ap.add_argument("--selftest-finder", action="store_true",
                     help="with --canary/--iframe-survival: use an always-hit fake finder/fetcher "
                          "(offline dry run of the report path)")
    ap.add_argument("--object-type", action="append", choices=VALID_OBJECT_TYPES,
                     help="restrict to one or more object types (repeatable)")
    ap.add_argument("--evidence-root", default=None, help="write the canary report JSON here")
    ap.add_argument("--selectors-path", default=None, help="override selectors-live.json path")
    ap.add_argument("--iframe-targets-path", default=None,
                     help="override iframe-survival-targets.json path")
    args = ap.parse_args(argv)

    if args.selftest:
        rc = _selftest()
        print("OK — ghl_selector_canary selftest passed" if rc == 0 else "FAILED")
        return rc

    if args.iframe_survival:
        targets = load_iframe_survival_targets(args.iframe_targets_path)["targets"]
        if not args.selftest_finder:
            print("ERROR: --iframe-survival needs a live page_fetcher wired by the caller "
                  "(see live_page_fetcher_over_http). Pass --selftest-finder for an offline "
                  "dry run of the report path, or import this module and call "
                  "run_iframe_survival_check() with a real fetcher.", file=sys.stderr)
            return 2
        fetcher = lambda url: (
            '<html><iframe src="https://forms.leadconnectorhq.com/widget/survey/x"></iframe></html>'
        )
        report = run_iframe_survival_check(targets, fetcher, evidence_root=args.evidence_root)
        print(json.dumps(report.summary(), indent=2, sort_keys=True))
        return 0 if report.summary()["clean"] else 1

    data = load_selectors(args.selectors_path)

    if args.matrix:
        _print_matrix(data, args.object_type)
        return 0

    if args.canary:
        if not args.selftest_finder:
            print("ERROR: --canary needs a live finder wired by the caller "
                  "(see live_finder_over_browser_manager). Pass --selftest-finder "
                  "for an offline dry run of the report path, or import this module "
                  "and call run_canary() with a real finder.", file=sys.stderr)
            return 2
        finder = lambda anchor, candidate: "fake-ref"
        report = run_canary(data, finder, evidence_root=args.evidence_root,
                             object_types=args.object_type)
        print(json.dumps(report.summary(), indent=2, sort_keys=True))
        return 0 if report.summary()["clean"] else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
