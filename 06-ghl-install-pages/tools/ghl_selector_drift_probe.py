#!/usr/bin/env python3
"""ghl_selector_drift_probe.py — selector-drift canary + STOP-with-snapshot resolver (U2 / F3).

RENAMED (U30/B-U16, 2026-07-16): this module shipped as ``ghl_selector_canary.py``
through U29; the file is renamed here to retire the operator-banned coded term
from the identifier (see ``scripts/docs-language-allowlist.json``'s U30-owned
``legacy_filenames`` entries, now removed). ONLY the file's OWN NAME changed —
internal identifiers (``CanaryReport``, ``run_canary()``, ``BOARD_NOTE_SELECTOR_MISS``,
the conventional ``import ... as canary`` alias, etc.) are UNCHANGED; the docs-language
CI guard only scans doc prose (*.md/*.mdx/*.rst/*.txt), never Python identifiers, so
there is no cross-cutting rename obligation here beyond the file's own name and the
handful of doc/tooling cross-references that name it by path (updated in this same
commit — ``ENV-MATRIX.md``, ``SKILL.md``, ``scripts/vps-mount-proof.sh``,
``tests/test_b_u15_env_matrix_live_proof.py``, ``tests/test_ghl_inventory.py``,
``tools/ghl_inventory.py``, ``tools/iframe-survival-targets.json``,
``tools/selectors-live.json``, ``scripts/probe/p304-agent-browser-conformance-probe.py``,
``scripts/docs-language-allowlist.json``). CHANGELOG.md history is NOT rewritten
(standing doctrine — see check-docs-language.py's own module docstring).

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
     surveys/forms/communities/courses/channels still embed their cross-origin
     (``*.leadconnectorhq.com``) iframe. Iframe survival was proven ONCE
     (2026-06-27 probe: GHL preview does not strip iframes) but never
     continuously guarded — this closes that gap in the same read-only,
     dependency-injected, fail-soft-board-notify shape as ``run_canary()`` (a
     caller-supplied ``page_fetcher`` does the real HTTP GET / agent-browser
     snapshot; this module performs no network I/O of its own). A stripped
     iframe reuses cc_board.py's existing ``VERIFY-FAIL`` taxonomy value (a
     post-publish render/verification check failing is exactly F6's shape) —
     it deliberately never invents a 7th cc_board taxonomy value. U106 added
     ``community``/``course``/``channel`` as valid target ``object_type``
     values (see ``iframe-survival-targets.json``'s ``_schema``) — the check
     itself never branches on object_type, so this is purely additive.

  4. ``notify_once()`` (U106) — an idempotent board-card gate wrapping any
     ``board_notifier`` call: a REPEATED scan of the SAME still-drifted target
     (a selector miss, a stripped iframe) must file EXACTLY ONE open card, not
     a fresh duplicate on every re-run of a weekly/pre-build check. Persists a
     tiny on-disk "seen cards" ledger under ``<evidence_root>/routing/
     board-cards-seen.json`` when an evidence_root is given (best-effort — a
     missing/unwritable evidence_root just means no dedup memory; the notifier
     still fires, this NEVER blocks the scan). ``run_iframe_survival_check()``
     routes its board notifications through it automatically.

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
    import ghl_selector_drift_probe as canary
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
    python3 ghl_selector_drift_probe.py --matrix                  # print anchor counts
    python3 ghl_selector_drift_probe.py --matrix --object-type form
    python3 ghl_selector_drift_probe.py --canary --evidence-root /tmp/canary --selftest
    python3 ghl_selector_drift_probe.py --iframe-survival --evidence-root /tmp/canary --selftest-finder
    python3 ghl_selector_drift_probe.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

CANARY_VERSION = "v1.3.0"  # P3-04 (c)4: + run_iframe_survival_check / --iframe-survival
                            # v1.2.0 (U30/B-U16): module renamed from
                            # ghl_selector_canary.py; + dedupe_board_notifier /
                            # clear_dedupe_state_for_resolved (idempotent
                            # SELECTOR-MISS card across the daily probe's
                            # repeat runs); scheduled daily via
                            # schedule/skill6-selector-drift-probe.cron.json
                            # v1.3.0 (U106/E5-1): + notify_once (generic
                            # caller-keyed idempotent card gate, independent
                            # of dedupe_board_notifier's anchor/target-keyed
                            # wrapper) + community/course/channel targets +
                            # flatten_community_course_anchors /
                            # probe_community_course_selectors

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
# U106 — notify_once(): idempotent board-card gate.
#
# A weekly/pre-build check re-runs on the SAME still-drifted target every time
# it fires (that is the point of a continuous check). Left unguarded, calling
# board_notifier on every run would file a fresh duplicate card each pass — the
# operator would see the SAME miss re-carded weekly instead of ONE open card
# they can track to resolution. This wraps any board_notifier call with a tiny
# on-disk "seen cards" ledger keyed by a caller-supplied stable card_key, so a
# repeated miss on the SAME target files exactly ONE card; a NEW target (or the
# same target after its ledger entry is cleared / a fresh evidence_root) still
# cards normally.
# ---------------------------------------------------------------------------
_BOARD_CARDS_SEEN_FILENAME = "board-cards-seen.json"


def _load_seen_cards(evidence_root: Optional[str]) -> Dict[str, Any]:
    if not evidence_root:
        return {}
    path = os.path.join(evidence_root, "routing", _BOARD_CARDS_SEEN_FILENAME)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - missing/corrupt ledger = no dedup memory, never a crash
        return {}


def _save_seen_cards(evidence_root: Optional[str], seen: Dict[str, Any]) -> None:
    if not evidence_root:
        return
    try:
        routing_dir = os.path.join(evidence_root, "routing")
        os.makedirs(routing_dir, exist_ok=True)
        path = os.path.join(routing_dir, _BOARD_CARDS_SEEN_FILENAME)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(seen, fh, indent=2, sort_keys=True)
    except Exception:  # noqa: BLE001 - best-effort persistence, never blocks the caller
        pass


def notify_once(
    evidence_root: Optional[str],
    card_key: str,
    notifier: Optional[Callable[[Dict[str, Any]], None]],
    payload: Dict[str, Any],
) -> bool:
    """Fire ``notifier(payload)`` at most ONCE per distinct ``card_key`` across
    repeated calls that share the same ``evidence_root`` — the idempotent
    board-card gate (U106). Returns True iff the notifier was actually invoked
    THIS call (a fresh card); False when this ``card_key`` was already carded
    (a repeat — deliberately skipped so the board never sees a duplicate) or
    when ``notifier`` is None.

    ``evidence_root=None`` disables the dedup memory entirely (every call
    fires, matching ``run_canary``/``run_iframe_survival_check``'s existing
    behaviour when called without an evidence_root) — this keeps the change
    fully backward compatible with every existing caller/test.

    Fail-soft like every board call in this module: a notifier that raises is
    swallowed (never blocks the scan), and a ledger that cannot be
    read/written just means no dedup memory for this run, never a crash."""
    if notifier is None:
        return False
    seen = _load_seen_cards(evidence_root)
    if card_key in seen:
        return False
    fired = False
    try:
        notifier(payload)
        fired = True
    except Exception:  # noqa: BLE001 - board calls are fail-soft
        pass
    seen[card_key] = {"first_notified_at": time.time(),
                      "prefix": payload.get("prefix")}
    _save_seen_cards(evidence_root, seen)
    return fired


# ---------------------------------------------------------------------------
# IDEMPOTENT board-notify wrapper (U30/B-U16 item 4) — a PERSISTENT
# (not-yet-fixed) drift must produce EXACTLY ONE SELECTOR-MISS card across
# REPEAT scheduled runs of the daily maintenance-window probe (see
# schedule/skill6-selector-drift-probe.cron.json), never a fresh duplicate
# card every time the SAME unresolved miss is re-scanned. run_canary()'s own
# board_notifier is called once per MISS per RUN (correct, run-scoped); this
# wrapper adds a persisted, cross-RUN ledger on top so the CALLER gets
# idempotent behavior without run_canary() itself needing any cross-run
# state (it stays a pure, dependency-injected, single-run scan).
# ---------------------------------------------------------------------------
def _load_dedupe_state(state_path: str) -> Set[str]:
    """Fail-soft read: a missing/corrupt state file is 'nothing notified
    yet' — never raises."""
    try:
        with open(state_path, encoding="utf-8") as fh:
            data = json.load(fh)
        return set(data.get("notified", []))
    except Exception:  # noqa: BLE001
        return set()


def _save_dedupe_state(state_path: str, ids: Iterable[str]) -> None:
    """Fail-soft write: persistence is best-effort and must NEVER block the
    underlying board notification it wraps."""
    try:
        parent = os.path.dirname(state_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as fh:
            json.dump({"notified": sorted(set(ids))}, fh, indent=2, sort_keys=True)
    except Exception:  # noqa: BLE001
        pass


def dedupe_board_notifier(
    board_notifier: Callable[[Dict[str, Any]], None],
    *,
    state_path: str,
) -> Callable[[Dict[str, Any]], None]:
    """Wrap ``board_notifier`` (the callable passed to ``run_canary(...,
    board_notifier=...)`` / ``run_iframe_survival_check(..., board_notifier=
    ...)``) with a persisted 'already notified' ledger keyed by the miss's
    own id (``anchor_id`` for a selector miss, ``target`` for an iframe-
    survival miss), so a PERSISTENT drift produces EXACTLY ONE SELECTOR-MISS
    (or VERIFY-FAIL) card across repeat daily probe runs — 'a seeded probe
    failure produces exactly ONE SELECTOR-MISS-prefixed card (idempotent
    across repeat runs)' (B-U16 item 4 acceptance (c)). An id that stops
    appearing in a miss payload (the drift healed) simply never gets
    re-checked here — see :func:`clear_dedupe_state_for_resolved` to
    positively clear it so a FUTURE regression on that same id re-notifies
    instead of being silenced forever by a stale ledger entry.

    ``state_path``: a small JSON file at a caller-owned location (e.g. under
    the daily probe's own evidence/park directory). Every read/write here is
    fail-soft (:func:`_load_dedupe_state` / :func:`_save_dedupe_state`) — a
    corrupt or missing state file never crashes the probe, and a persistence
    failure never blocks the underlying ``board_notifier`` call.

    The RETURNED callable has the SAME shape as ``board_notifier`` — drop it
    straight into ``run_canary(..., board_notifier=dedupe_board_notifier(...))``
    unchanged."""
    def _wrapped(payload: Dict[str, Any]) -> None:
        key = str(payload.get("anchor_id") or payload.get("target") or "")
        notified = _load_dedupe_state(state_path)
        if key and key in notified:
            return  # an OPEN card already exists for this exact miss — no duplicate
        board_notifier(payload)
        if key:
            notified.add(key)
            _save_dedupe_state(state_path, notified)

    return _wrapped


def clear_dedupe_state_for_resolved(*, state_path: str,
                                    still_missing_ids: Iterable[str]) -> None:
    """Drop any dedupe-ledger id NOT present in ``still_missing_ids`` — call
    this once per probe run with the CURRENT run's full miss-id set so an
    anchor/target that stopped missing (the drift healed) is cleared from the
    ledger, letting a FUTURE regression on that same id re-notify instead of
    being permanently silenced by a stale entry. Fail-soft (best-effort,
    same discipline as :func:`dedupe_board_notifier`'s own persistence);
    never raises."""
    notified = _load_dedupe_state(state_path)
    remaining = notified & set(still_missing_ids)
    if remaining != notified:
        _save_dedupe_state(state_path, remaining)


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
    (``object_type`` also accepts ``community``/``course``/``channel`` as of
    U106 — this function never branches on it) — see
    load_iframe_survival_targets() / iframe-survival-targets.json for the
    on-disk schema this list is normally loaded from.

    A target whose page_fetcher call raises is recorded as a "fetch-error"
    MISS (also board-notified) rather than crashing the whole weekly run —
    one unreachable page must never hide the rest of the report.

    U106: every board notification routes through ``notify_once()`` keyed on
    the target id, so a target that stays broken across REPEATED runs (with
    the same ``evidence_root``) files exactly ONE card, never a fresh
    duplicate on every re-run — pass ``evidence_root=None`` (the default) to
    keep the old un-deduped behaviour (every call fires; matches every
    existing caller/test)."""
    report = IframeSurvivalReport(started_at=time.time())
    for t in targets:
        entry: Dict[str, Any] = {
            "target": t["id"], "object_type": t.get("object_type", ""), "url": t["url"],
        }
        card_key = f"{BOARD_NOTE_IFRAME_SURVIVAL_MISS}:{t['id']}"
        try:
            html = page_fetcher(t["url"]) or ""
        except Exception as exc:
            entry["status"] = "fetch-error"
            entry["error"] = str(exc)
            report.results.append(entry)
            report.misses.append(entry)
            notify_once(evidence_root, card_key, board_notifier,
                       {"prefix": BOARD_NOTE_IFRAME_SURVIVAL_MISS, **entry})
            continue

        survived = ("<iframe" in html) and (iframe_src_marker in html)
        entry["status"] = "survived" if survived else "stripped"
        report.results.append(entry)
        if not survived:
            report.misses.append(entry)
            notify_once(evidence_root, card_key, board_notifier,
                       {"prefix": BOARD_NOTE_IFRAME_SURVIVAL_MISS, **entry})
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
# U106 — community/course/channel selector-drift probe (E5-1, closes G1).
#
# ghl_community_builder.py / ghl_course_builder.py ship their OWN nested
# selector map (selectors-live-communities-courses.json — a different shape
# than this module's flat objects.<type>.anchors[] selectors-live.json) and
# already gate every in-area click/fill on a D8 STOP-and-report when an
# anchor's status is not "locked"/"verified-shared-rail" (see
# ghl_community_builder.anchor()). That STOP is a per-build-time discovery —
# nothing scans the CAPTURED map itself, read-only, to catch a regression
# (an anchor that USED to be "locked" flipping back to "capture-pending" after
# a live re-capture finds it broken) before a client build hits it. This is
# that scan: purely a JSON-shape walk (no browser, no live DOM — the drift
# signal IS the anchor's own recorded status), reusing run_canary()'s exact
# SELECTOR-MISS taxonomy value and notify_once()'s idempotent card gate.
# ---------------------------------------------------------------------------
_COMMUNITY_COURSE_OK_STATUS = {"verified-shared-rail", "locked"}


def flatten_community_course_anchors(selectors: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten the nested `community`/`course` selector map (the shape
    ghl_community_builder.load_selectors() / selectors-live-communities-
    courses.json ships — NOT this module's own selectors-live.json shape)
    into a flat list of {"id": "community.group_nav.add_channel_control",
    "status": "...", "anchor": "...", "object_type": "community"} records —
    the same flat shape run_canary() already works with for the other four
    object types (form/survey/funnel/page).

    Purely a JSON-shape walk: a leaf is any dict carrying a "status" key;
    every other key is a nesting level. Meta keys (leading underscore, e.g.
    "_doc", "_idempotency", "_cleanup_reality") are skipped, matching the
    convention already used throughout this selector doc."""
    out: List[Dict[str, Any]] = []

    def _walk(node: Any, path: List[str], object_type: str) -> None:
        if not isinstance(node, dict):
            return
        if "status" in node:
            out.append({"id": ".".join(path), "status": node.get("status"),
                       "anchor": node.get("anchor"), "object_type": object_type})
            return
        for k, v in node.items():
            if k.startswith("_"):
                continue
            _walk(v, path + [k], object_type)

    for top in ("community", "course"):
        if top in selectors:
            _walk(selectors[top], [top], top)
    return out


def probe_community_course_selectors(
    selectors: Dict[str, Any],
    evidence_root: Optional[str] = None,
    board_notifier: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> CanaryReport:
    """READ-ONLY companion probe (U106) for the community/course/channel
    builders: classify every in-area anchor already captured in
    selectors-live-communities-courses.json as drifted (status is neither
    "locked" nor "verified-shared-rail") or actionable — WITHOUT touching a
    live DOM. Same read-only / dependency-injected / fail-soft-board-notify
    shape as run_canary(), reusing the SAME BOARD_NOTE_SELECTOR_MISS taxonomy
    value (never an 8th cc_board category), and every notification routes
    through notify_once() so a still-drifted anchor across REPEATED probes
    (same evidence_root) files exactly ONE card, never a duplicate — the scan
    itself still reports the ongoing miss on every call; only the CARD is
    deduped.

    `selectors` is the already-loaded dict (caller supplies it — usually
    `ghl_community_builder.load_selectors()`; a test supplies a seeded
    deepcopy), keeping this function itself import-light and offline-only."""
    report = CanaryReport(started_at=time.time(), object_types=["community", "course"])
    for a in flatten_community_course_anchors(selectors):
        ok = a["status"] in _COMMUNITY_COURSE_OK_STATUS
        entry: Dict[str, Any] = {
            "anchor_id": a["id"], "object_type": a["object_type"], "target": a["id"],
            "status": "primary" if ok else "missing",
            "used_candidate": {"status": a["status"], "anchor": a.get("anchor")},
        }
        report.results.append(entry)
        if not ok:
            report.misses.append(entry)
            notify_once(evidence_root, f"{BOARD_NOTE_SELECTOR_MISS}:{a['id']}",
                       board_notifier, {"prefix": BOARD_NOTE_SELECTOR_MISS, **entry})
    report.finished_at = time.time()

    if evidence_root:
        os.makedirs(evidence_root, exist_ok=True)
        out_path = os.path.join(
            evidence_root, f"community-course-selector-probe-{int(report.started_at)}.json")
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

    # 12. dedupe_board_notifier (U30/B-U16 item 4): a seeded, PERSISTENT miss
    #     notifies exactly ONCE across repeat runs; a board_notifier failure
    #     is never recorded as a successful notify.
    import tempfile
    with tempfile.TemporaryDirectory() as dtmp:
        dstate = os.path.join(dtmp, "dedupe.json")
        dnotified = []
        dwrapped = dedupe_board_notifier(lambda p: dnotified.append(p), state_path=dstate)
        for _ in range(3):
            run_canary(data, _mixed, object_types=["form"], board_notifier=dwrapped)
        assert len(dnotified) == 1, "repeat runs of the SAME miss must yield exactly one card"

        def _boom_notifier(p):
            raise RuntimeError("board down")
        dstate2 = os.path.join(dtmp, "dedupe2.json")
        dwrapped2 = dedupe_board_notifier(_boom_notifier, state_path=dstate2)
        try:
            dwrapped2({"anchor_id": "form.builder.save", "prefix": BOARD_NOTE_SELECTOR_MISS})
            raise AssertionError("expected the underlying notifier's RuntimeError to propagate")
        except RuntimeError:
            pass
        assert _load_dedupe_state(dstate2) == set(), "a failed notify must not be recorded"

    # 13. U106 — notify_once(): a repeated card on the SAME key (same
    #     evidence_root) fires exactly once; a different key always fires;
    #     no evidence_root disables dedup entirely (backward compatible).
    with tempfile.TemporaryDirectory() as tmp:
        fired: List[Any] = []
        r1 = notify_once(tmp, "SELECTOR-MISS:x", lambda p: fired.append(p), {"prefix": "SELECTOR-MISS"})
        r2 = notify_once(tmp, "SELECTOR-MISS:x", lambda p: fired.append(p), {"prefix": "SELECTOR-MISS"})
        r3 = notify_once(tmp, "SELECTOR-MISS:y", lambda p: fired.append(p), {"prefix": "SELECTOR-MISS"})
        assert (r1, r2, r3) == (True, False, True), f"notify_once dedup wrong: {(r1, r2, r3)}"
        assert len(fired) == 2, f"notify_once fired count wrong: {len(fired)} (want 2)"
    fired2: List[Any] = []
    r4 = notify_once(None, "SELECTOR-MISS:x", lambda p: fired2.append(p), {"prefix": "x"})
    r5 = notify_once(None, "SELECTOR-MISS:x", lambda p: fired2.append(p), {"prefix": "x"})
    assert r4 and r5 and len(fired2) == 2, \
        "notify_once with evidence_root=None should fire every call (no dedup)"

    # 14. U106 — flatten_community_course_anchors / probe_community_course_selectors:
    #     a seeded drift (one LOCKed anchor flipped back to capture-pending)
    #     reports exactly one miss and, across REPEATED probes on the same
    #     evidence_root, files exactly ONE SELECTOR-MISS card (idempotent).
    fake_sels = {
        "community": {
            "_idempotency": {"note": "skip me"},
            "group_nav": {
                "add_channel_control": {"status": "locked", "anchor": "getByRole(...)"},
                "channel_name_input": {"status": "locked", "anchor": "getByPlaceholder(...)"},
            },
        },
        "course": {
            "outline": {"add_lesson": {"status": "locked", "anchor": "getByRole(...)"}},
        },
    }
    flat = flatten_community_course_anchors(fake_sels)
    ids = {a["id"] for a in flat}
    assert ids == {"community.group_nav.add_channel_control", "community.group_nav.channel_name_input",
                   "course.outline.add_lesson"}, f"flatten_community_course_anchors wrong ids: {ids}"

    clean_report = probe_community_course_selectors(fake_sels)
    assert clean_report.summary()["clean"], \
        "probe_community_course_selectors should be clean with all-locked anchors"

    import copy
    drifted = copy.deepcopy(fake_sels)
    drifted["community"]["group_nav"]["add_channel_control"]["status"] = "capture-pending"
    with tempfile.TemporaryDirectory() as tmp2:
        cards: List[Any] = []

        def _notifier(payload):
            cards.append(payload)

        rep1 = probe_community_course_selectors(drifted, evidence_root=tmp2, board_notifier=_notifier)
        rep2 = probe_community_course_selectors(drifted, evidence_root=tmp2, board_notifier=_notifier)
        assert not rep1.summary()["clean"] and not rep2.summary()["clean"], \
            "seeded drift should report NOT clean on every repeated probe"
        assert "community.group_nav.add_channel_control" in rep1.summary()["misses"], \
            "seeded drift anchor missing from the miss list"
        assert len(cards) == 1, \
            f"seeded drift across 2 repeated probes should file exactly 1 card, got {len(cards)}"
        assert cards[0]["prefix"] == BOARD_NOTE_SELECTOR_MISS, \
            f"seeded drift card used the wrong taxonomy prefix: {cards[0]['prefix']}"

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
    ap.add_argument("--community-course-probe", action="store_true",
                     help="U106: read-only drift scan of selectors-live-communities-courses.json's "
                          "already-captured statuses (no live finder needed — always offline-safe)")
    ap.add_argument("--object-type", action="append", choices=VALID_OBJECT_TYPES,
                     help="restrict to one or more object types (repeatable)")
    ap.add_argument("--evidence-root", default=None, help="write the canary report JSON here")
    ap.add_argument("--selectors-path", default=None, help="override selectors-live.json path")
    ap.add_argument("--iframe-targets-path", default=None,
                     help="override iframe-survival-targets.json path")
    args = ap.parse_args(argv)

    if args.selftest:
        rc = _selftest()
        print("OK — ghl_selector_drift_probe selftest passed" if rc == 0 else "FAILED")
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

    if args.community_course_probe:
        try:
            import ghl_community_builder as _cb_mod  # lazy — keeps this module import-light
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: --community-course-probe needs ghl_community_builder importable "
                  f"({type(exc).__name__}: {exc}).", file=sys.stderr)
            return 2
        cc_selectors = _cb_mod.load_selectors()
        report = probe_community_course_selectors(cc_selectors, evidence_root=args.evidence_root)
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
