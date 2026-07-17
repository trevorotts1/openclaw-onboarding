#!/usr/bin/env python3
"""ghl_inventory.py — ZHC page/funnel inventory + staged lifecycle
(flag -> operator card -> fail-closed execute) + evidence-root retention
(U31 / B-U17, "nothing auto-deletes client content").

WHY THIS EXISTS
----------------
VERIFIED absence at HEAD (B.11 claim #19): no GoHighLevel-side page
lifecycle existed anywhere in this skill — no inventory of ZHC pages/funnels
per location, no aging, no stale detection, no archive/garbage-collection
flow, and no retention policy for the `v2-<RUN_ID>` run-evidence roots
`cc_board.py` already discovers. What DID exist was duplicate-prevention
that STOPS a build and demands manual cleanup with no tooling behind it
(`ghl_method.resolve_install_target` raising `InstallTargetError` on >1
page carrying the same build marker). This module gives that manual-cleanup
demand a queue, and gives the fleet's aging pages a lifecycle that a human
approves before anything is ever removed.

THE DOCTRINE — nothing auto-deletes client content
----------------------------------------------------
Three independent stages, each a separate, individually-callable function:

  1. FLAG (read-only, pure) — `flag_lifecycle_candidates` classifies pages
     already enumerated into an `InventoryReport` as STALE (draft,
     unpublished past a threshold), SUPERSEDED (an older page in the same
     funnel/name-family than the newest verified one), or DUPLICATE
     (2+ pages sharing one build marker — the exact ambiguity
     `ghl_method.resolve_install_target` itself would refuse to resolve;
     reused here, never re-derived).
  2. CARD — `post_lifecycle_card` posts ONE operator card per distinct
     candidate set, deduped against an on-disk event-ledger so a repeated
     maintenance-window run never spams a second card for the same
     unresolved candidates.
  3. EXECUTE — `execute_approved_deletes` is fail-closed BY CONSTRUCTION: it
     refuses (raises `LifecycleGuardError`, deletes nothing, anywhere) unless
     every id being deleted was flagged, carded, delivered, AND explicitly
     named in `approved_ids`. Every actual delete follows a mandatory
     present -> pre-delete restorable export -> delete -> absent receipt
     chain — "no receipt = not deleted", the same F6 discipline
     `ghl_receipts.py` established for creates, mirrored here for removals.

Evidence-root RETENTION (`prune_evidence_roots`) is a fourth, independent
concern: it keeps the newest N `v2-<RUN_ID>` roots per funnel-slug group
(reusing `cc_board.list_evidence_runs` — never re-deriving evidence-root
discovery) plus every root an OPEN card still references, skips (never even
considers) any root a `blocked` card references, and only ever COMPRESSES
older roots — it never deletes a run-evidence root outright.

WHAT THIS MODULE IS *NOT*
--------------------------
This module performs NO GHL I/O and opens NO browser of its own — same
isolation discipline as `ghl_selector_drift_probe.py` / `ghl_object_router.py`.
Every live read (which funnels/pages exist, whether an id is still present)
and every live write (delete) is a caller-injected callable. Production
wiring sketches (`live_page_lister_over_rest_canvas`, ...) are provided but
deliberately NOT exercised by CI — they need a real seeded agent-browser
session, same discipline as `ghl_selector_drift_probe.live_finder_over_browser_
manager`.

**THE ONE LIVE GAP THIS UNIT SHIPS WITHOUT A WIRED ROUTE**: discovering the
SET of funnel ids for a location. Neither the official GHL public API (no
Funnels endpoint exists there at all — checked against Skill 44's own
`endpoints.py`) nor the proven internal SPA-canvas REST family
(`ghl_rest_canvas.py`, which only proves fetch-a-known-funnel-by-id and
list-pages-within-a-known-funnel) documents a "list every funnel for a
location" call. `run_canary.py`-style DOM discovery (a live browser snapshot
of the Sites -> Funnels list) is the most likely live route but has never
been probed. `funnel_lister` is therefore a REQUIRED caller-supplied
dependency with no default live implementation — wiring + proving it is a
live leg owed to the operator (parallel to U22), never fabricated here.

CLI
---
    python3 ghl_inventory.py --selftest
    python3 ghl_inventory.py --advisory --inventory-json <path> --flags-json <path>
    python3 ghl_inventory.py --prune --base-dir <dir> [--keep-n N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import cc_board  # noqa: E402 -- reuse resolve_evidence_base / list_evidence_runs
import ghl_method  # noqa: E402 -- reuse resolve_install_target / InstallTargetError

INVENTORY_VERSION = "v1.0.0"

# ZHC naming prefix (case-insensitive match). Duplicated as a bare regex
# (not imported from ghl_builder) so this read-only, network-free module
# carries zero import-time coupling to ghl_builder's much larger surface —
# same "performs no GHL I/O, imports nothing GHL-specific it doesn't have to"
# isolation discipline as ghl_receipts.py / ghl_selector_drift_probe.py. The
# pattern itself is intentionally byte-identical to ghl_builder.ZHC_PREFIX_RE
# (single naming convention, two independent, decoupled call sites).
ZHC_PREFIX_RE = re.compile(r"^\s*zhc\b", re.IGNORECASE)

DEFAULT_STALE_DRAFT_DAYS = 30
DEFAULT_RETENTION_KEEP_N = 10

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"
VALID_STATUSES = (STATUS_DRAFT, STATUS_PUBLISHED)

CARD_KIND_STALE = "stale-lifecycle"
CARD_KIND_SUPERSEDED = "superseded-lifecycle"
CARD_KIND_DUPLICATE = "duplicate-marker"
VALID_CARD_KINDS = (CARD_KIND_STALE, CARD_KIND_SUPERSEDED, CARD_KIND_DUPLICATE)

_LIFECYCLE_SUBDIR = "page-lifecycle"
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    """UTC ISO-8601 timestamp — matches cc_board._ts()/ghl_builder._now() byte-for-byte."""
    return time.strftime(_TS_FMT, time.gmtime())


def _parse_ts(ts: str) -> Optional[datetime]:
    """Parse an ISO-8601 'Z' timestamp. Returns None (never raises) on any
    unparsable input — a page with an unreadable `created` timestamp is
    NEVER guessed at; callers must treat None as "cannot judge age", not as
    "infinitely old"."""
    if not ts or not isinstance(ts, str):
        return None
    candidate = ts.strip()
    for fmt in (_TS_FMT, "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(candidate, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _is_zhc(name: str, pattern: Optional["re.Pattern[str]"] = None) -> bool:
    return bool((pattern or ZHC_PREFIX_RE).match(name or ""))


def _slugify(name: str) -> str:
    """Same normalization idiom as ghl_builder.build_manifest's path
    slugging (lowercase, non-alnum collapsed to '-', stripped) — reused here
    verbatim for a stable "name family" grouping key, with the ZHC prefix
    stripped first so 'ZHC Foo' and a later 'ZHC Foo v2' rebuild still group
    together."""
    s = (name or "").strip()
    s = ZHC_PREFIX_RE.sub("", s, count=1).strip()
    s = re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")
    return s or "untitled"


def _atomic_write_json(path: str, payload: Any) -> str:
    """write-then-rename — a reader can never observe a half-written file
    (same discipline as ghl_receipts.write_receipt)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


def _read_json(path: str) -> Optional[Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 1) Inventory — read-only enumeration
# ---------------------------------------------------------------------------
@dataclass
class PageRecord:
    """One row of the per-location ZHC page inventory. Field names match the
    spec's literal schema: {funnel, page, marker, status, created,
    last_verified, last_build_run_id} — `funnel_name`/`page_name` are
    additive (for human-readable cards/logs), never load-bearing."""
    funnel: str
    page: str
    marker: str
    status: str
    created: str
    last_verified: str
    last_build_run_id: str = ""
    funnel_name: str = ""
    page_name: str = ""

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}, got {self.status!r}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InventoryReport:
    location_id: str
    generated_at: str
    pages: List[PageRecord] = field(default_factory=list)
    inventory_version: str = INVENTORY_VERSION

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["pages"] = [p.to_dict() for p in self.pages]
        return d

    def summary(self) -> Dict[str, Any]:
        return {
            "location_id": self.location_id,
            "generated_at": self.generated_at,
            "total_pages": len(self.pages),
            "drafts": sum(1 for p in self.pages if p.status == STATUS_DRAFT),
            "published": sum(1 for p in self.pages if p.status == STATUS_PUBLISHED),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InventoryReport":
        pages = [PageRecord(**p) for p in data.get("pages", [])]
        return cls(
            location_id=data.get("location_id", ""),
            generated_at=data.get("generated_at", ""),
            pages=pages,
            inventory_version=data.get("inventory_version", INVENTORY_VERSION),
        )


def enumerate_zhc_inventory(
    location_id: str,
    *,
    funnel_lister: Callable[[str], List[Dict[str, Any]]],
    page_lister: Callable[[str, str], List[Dict[str, Any]]],
    zhc_prefix_re: Optional["re.Pattern[str]"] = None,
    now: Optional[Callable[[], str]] = None,
) -> InventoryReport:
    """READ-ONLY: enumerate every ZHC-prefixed funnel's pages for one
    location. ZERO write calls BY CONSTRUCTION — this function contains no
    write-capable code path at all; `funnel_lister(location_id)` and
    `page_lister(funnel_id, location_id)` are the ONLY I/O it performs, both
    caller-injected reads (same DI discipline as
    ghl_selector_drift_probe.run_canary's `finder`). A page inherits ZHC
    ownership from either its OWN name or its parent funnel's ZHC-prefixed
    name (a page can be un-renamed even when its funnel carries the
    provenance prefix) — the fleet invariant (every ZHC object is
    fleet-owned) makes this unambiguous per B.11 claim #19/#20.

    Never raises on a single bad record: a funnel/page dict missing its id
    is skipped (not fabricated), so one malformed record can never abort the
    whole enumeration.
    """
    pattern = zhc_prefix_re or ZHC_PREFIX_RE
    ts = (now or _now)()
    pages: List[PageRecord] = []

    for f in funnel_lister(location_id) or []:
        if not isinstance(f, dict):
            continue
        fname = str(f.get("name") or "")
        fid = str(f.get("id") or f.get("funnel_id") or "")
        if not fid or not _is_zhc(fname, pattern):
            continue
        for p in page_lister(fid, location_id) or []:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or p.get("page_id") or "")
            pname = str(p.get("name") or "")
            if not pid:
                continue
            status = str(p.get("status") or STATUS_DRAFT).strip().lower()
            if status not in VALID_STATUSES:
                status = STATUS_PUBLISHED if p.get("published") else STATUS_DRAFT
            pages.append(PageRecord(
                funnel=fid,
                page=pid,
                marker=str(p.get("marker") or ""),
                status=status,
                created=str(p.get("createdAt") or p.get("created") or ""),
                last_verified=ts,
                last_build_run_id=str(p.get("last_build_run_id") or ""),
                funnel_name=fname,
                page_name=pname,
            ))

    return InventoryReport(location_id=location_id, generated_at=ts, pages=pages)


def write_inventory(evidence_base: str, report: InventoryReport) -> str:
    """Write `<evidence_base>/page-lifecycle/inventory-<location>.json`."""
    path = os.path.join(
        evidence_base, _LIFECYCLE_SUBDIR, f"inventory-{report.location_id}.json"
    )
    return _atomic_write_json(path, report.to_dict())


def load_inventory(path: str) -> Optional[InventoryReport]:
    data = _read_json(path)
    return InventoryReport.from_dict(data) if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# 2) FLAG — pure classification, no I/O
# ---------------------------------------------------------------------------
@dataclass
class FlagResult:
    stale: List[Dict[str, Any]] = field(default_factory=list)
    superseded: List[Dict[str, Any]] = field(default_factory=list)
    duplicates: List[Dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.stale or self.superseded or self.duplicates)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _stale_candidates(
    pages: List[PageRecord], *, now_dt: datetime, stale_draft_days: int
) -> List[Dict[str, Any]]:
    out = []
    for p in pages:
        if p.status != STATUS_DRAFT:
            continue
        created_dt = _parse_ts(p.created)
        if created_dt is None:
            continue  # unparsable created -- never guess, never flag
        age_days = (now_dt - created_dt).total_seconds() / 86400.0
        if age_days > stale_draft_days:
            out.append({
                "id": p.page, "funnel": p.funnel, "marker": p.marker,
                "reason": f"draft unpublished for {age_days:.1f} days "
                          f"(threshold {stale_draft_days})",
                "age_days": round(age_days, 1),
            })
    return out


def _superseded_candidates(
    pages: List[PageRecord], *, slug_of_page: Callable[[PageRecord], str]
) -> List[Dict[str, Any]]:
    groups: Dict[tuple, List[PageRecord]] = {}
    for p in pages:
        key = (p.funnel, slug_of_page(p))
        groups.setdefault(key, []).append(p)

    out = []
    for (funnel, slug), group in groups.items():
        if len(group) < 2:
            continue
        dated = [(p, _parse_ts(p.created)) for p in group]
        dated = [(p, d) for p, d in dated if d is not None]
        if len(dated) < 2:
            continue  # can't order without at least 2 parseable timestamps
        dated.sort(key=lambda pair: pair[1], reverse=True)
        current_page, _ = dated[0]
        for older_page, _ in dated[1:]:
            out.append({
                "id": older_page.page, "funnel": funnel, "marker": older_page.marker,
                "reason": f"superseded by newer verified marker "
                          f"{current_page.marker!r} on page {current_page.page!r} "
                          f"(same funnel/name-family {slug!r})",
                "superseded_by": current_page.page,
            })
    return out


def detect_duplicate_markers(report: InventoryReport) -> List[Dict[str, Any]]:
    """Reuses `ghl_method.resolve_install_target`'s OWN ambiguity rule
    (never re-derives it): every marker that would raise `InstallTargetError`
    at build time — 2+ live pages carrying the identical build marker within
    one funnel. Duplicates that trip this get a dedicated card carrying the
    ambiguous ids (spec, item 2)."""
    by_funnel: Dict[str, List[PageRecord]] = {}
    for p in report.pages:
        by_funnel.setdefault(p.funnel, []).append(p)

    duplicates: List[Dict[str, Any]] = []
    for funnel_id, pages in by_funnel.items():
        markers = sorted({p.marker for p in pages if p.marker})
        existing_pages = [{"id": p.page, "marker": p.marker} for p in pages]
        for marker in markers:
            try:
                ghl_method.resolve_install_target(existing_pages, marker)
            except ghl_method.InstallTargetError as exc:
                ambiguous_ids = [p.page for p in pages if p.marker == marker]
                duplicates.append({
                    "id": ambiguous_ids[0],  # anchor id for candidate-id bookkeeping
                    "funnel": funnel_id,
                    "marker": marker,
                    "ambiguous_ids": ambiguous_ids,
                    "reason": str(exc),
                })
    return duplicates


def flag_lifecycle_candidates(
    report: InventoryReport,
    *,
    now: Optional[str] = None,
    stale_draft_days: int = DEFAULT_STALE_DRAFT_DAYS,
    slug_of_page: Optional[Callable[[PageRecord], str]] = None,
) -> FlagResult:
    """Pure function — NO I/O, safe to call as often as desired. Classifies
    every page in `report` into STALE / SUPERSEDED / DUPLICATE (a page may
    appear in more than one bucket; each bucket is independently actionable
    and independently carded)."""
    now_dt = _parse_ts(now) if now else datetime.now(timezone.utc)
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    slug_fn = slug_of_page or (lambda p: _slugify(p.page_name))

    return FlagResult(
        stale=_stale_candidates(report.pages, now_dt=now_dt, stale_draft_days=stale_draft_days),
        superseded=_superseded_candidates(report.pages, slug_of_page=slug_fn),
        duplicates=detect_duplicate_markers(report),
    )


# ---------------------------------------------------------------------------
# 3) CARD — idempotent operator-card posting (on-disk event-ledger dedupe)
# ---------------------------------------------------------------------------
def _dedupe_key(card_kind: str, candidate_ids: Sequence[str]) -> str:
    raw = card_kind + "|" + "|".join(sorted(candidate_ids))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _load_card_ledger(ledger_path: str) -> Dict[str, Any]:
    data = _read_json(ledger_path) if ledger_path else None
    return data if isinstance(data, dict) else {}


def _candidate_ids(candidates: Sequence[Dict[str, Any]]) -> List[str]:
    ids = set()
    for c in candidates:
        cid = str(c.get("id") or c.get("page") or "")
        if cid:
            ids.add(cid)
    return sorted(ids)


def post_lifecycle_card(
    card_kind: str,
    candidates: List[Dict[str, Any]],
    *,
    ledger_path: str,
    board_notifier: Callable[[Dict[str, Any]], Any],
    now: Optional[Callable[[], str]] = None,
) -> Dict[str, Any]:
    """ONE operator card per DISTINCT candidate set, idempotent across
    repeat runs via an on-disk event-ledger keyed by
    sha256(card_kind + sorted candidate ids). A re-run that sees the SAME
    candidate set never re-notifies `board_notifier` (never a duplicate
    card) — a run whose candidate set changed gets its own dedupe key and an
    honest fresh card.

    Never raises: `board_notifier` failing is caught and recorded as
    `delivered=False` (fail-soft, matching every cc_board call site's
    discipline elsewhere in this repo) — NOT recorded as delivered, so the
    next run retries the notify rather than silently losing the card.
    """
    if card_kind not in VALID_CARD_KINDS:
        raise ValueError(f"card_kind must be one of {VALID_CARD_KINDS}, got {card_kind!r}")
    ts = (now or _now)()
    if not candidates:
        return {"posted": False, "reason": "no candidates", "dedupe_key": None}

    ids = _candidate_ids(candidates)
    key = _dedupe_key(card_kind, ids)
    ledger = _load_card_ledger(ledger_path)

    existing = ledger.get(key)
    if existing and existing.get("delivered"):
        return {"posted": False, "reason": "deduped (event-ledger)", "dedupe_key": key,
                "prior": existing}

    payload = {
        "card_kind": card_kind,
        "dedupe_key": key,
        "candidate_ids": ids,
        "candidates": candidates,
        "ts": ts,
    }
    try:
        result = board_notifier(payload)
        delivered = True
        error = None
    except Exception as exc:  # noqa: BLE001 -- board calls are fail-soft everywhere in this repo
        result = None
        delivered = False
        error = str(exc)

    ledger[key] = {
        "card_kind": card_kind,
        "candidate_ids": ids,
        "delivered": delivered,
        "posted_at": ts,
        "error": error,
    }
    if ledger_path:
        _atomic_write_json(ledger_path, ledger)

    return {"posted": delivered, "dedupe_key": key, "result": result, "error": error}


# ---------------------------------------------------------------------------
# 4) EXECUTE — fail-closed delete, present -> export -> delete -> absent
# ---------------------------------------------------------------------------
class LifecycleGuardError(RuntimeError):
    """Raised when execute_approved_deletes is asked to remove something
    that was never flagged + carded + delivered + explicitly approved — the
    fail-closed guard (BINARY acceptance (e)). Deletes NOTHING when raised,
    not even the ids in the same batch that WOULD have been legitimate."""


@dataclass
class ExecuteReport:
    dedupe_key: str
    results: List[Dict[str, Any]] = field(default_factory=list)

    def all_deleted(self) -> bool:
        return bool(self.results) and all(r.get("status") == "deleted" for r in self.results)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def execute_approved_deletes(
    dedupe_key: str,
    approved_ids: Sequence[str],
    *,
    ledger_path: str,
    exporter: Callable[[str], Dict[str, Any]],
    deleter: Callable[[str], None],
    prober: Callable[[str], bool],
    evidence_base: str,
    now: Optional[Callable[[], str]] = None,
) -> ExecuteReport:
    """FAIL-CLOSED delete execution — the ONLY function in this module that
    may ever call `deleter`. Guarantees:

      1. `dedupe_key` must name a DELIVERED card in the on-disk event-ledger
         — an unknown/undelivered key raises `LifecycleGuardError` and
         deletes nothing, anywhere.
      2. Every id in `approved_ids` must be among THAT card's own
         `candidate_ids` — approving an id that was never flagged/carded is
         refused the same way (deletes nothing, anywhere).
      3. For each approved id, independently: PRESENT proof (`prober`) ->
         pre-delete RESTORABLE export written to
         `<evidence_base>/page-lifecycle/exports/<id>-<ts>.json` ->
         `deleter(id)` -> ABSENT proof (`prober`) -> a receipt (present ->
         delete -> absent proof + the export path) written to
         `<evidence_base>/page-lifecycle/receipts/<id>-<ts>.json`. "No
         receipt = not deleted" — the F6 discipline, mirrored for removals.

    One id's runtime failure (not present, deleter raises, absent-check
    still true) is recorded as a FAILED per-id entry and does NOT abort the
    rest of that batch — only a call-shape violation (#1/#2) aborts before
    any deletion starts anywhere.
    """
    ledger = _load_card_ledger(ledger_path)
    card = ledger.get(dedupe_key)
    if not card or not card.get("delivered"):
        raise LifecycleGuardError(
            f"REFUSE: dedupe_key {dedupe_key!r} does not name a delivered "
            "operator card in the event-ledger — nothing may be deleted "
            "without an approved card."
        )
    approved_set = {str(a) for a in approved_ids}
    card_ids = set(card.get("candidate_ids") or [])
    outside = approved_set - card_ids
    if outside:
        raise LifecycleGuardError(
            f"REFUSE: approved id(s) {sorted(outside)} were never part of "
            f"card {dedupe_key!r}'s flagged candidates {sorted(card_ids)} — "
            "nothing deletes without being flagged, carded, and approved first."
        )

    ts_fn = now or _now
    results: List[Dict[str, Any]] = []
    for obj_id in approved_ids:
        obj_id = str(obj_id)
        ts = ts_fn()
        entry: Dict[str, Any] = {"id": obj_id, "ts": ts}
        try:
            present_before = bool(prober(obj_id))
            entry["present_before"] = present_before
            if not present_before:
                entry["status"] = "skipped-not-present"
            else:
                export = exporter(obj_id)
                export_path = os.path.join(
                    evidence_base, _LIFECYCLE_SUBDIR, "exports", f"{obj_id}-{ts}.json"
                )
                _atomic_write_json(export_path, export)
                entry["export_path"] = export_path

                deleter(obj_id)

                absent_after = not bool(prober(obj_id))
                entry["absent_after"] = absent_after
                entry["status"] = "deleted" if absent_after else "delete-unconfirmed"
        except Exception as exc:  # noqa: BLE001 -- one id's failure never aborts the batch
            entry["status"] = "failed"
            entry["error"] = str(exc)

        receipt_path = os.path.join(
            evidence_base, _LIFECYCLE_SUBDIR, "receipts", f"{obj_id}-{ts}.json"
        )
        _atomic_write_json(receipt_path, entry)
        entry["receipt_path"] = receipt_path
        results.append(entry)

    return ExecuteReport(dedupe_key=dedupe_key, results=results)


# ---------------------------------------------------------------------------
# 5) Evidence-root RETENTION — keep last N per funnel-slug, compress older
# ---------------------------------------------------------------------------
@dataclass
class PruneReport:
    base_dir: str
    kept: List[str] = field(default_factory=list)
    compressed: List[str] = field(default_factory=list)
    skipped_blocked: List[str] = field(default_factory=list)
    skipped_open_card: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_RUN_ID_TRAILING_NONCE_RE = re.compile(
    r"[-_](?:\d{8,}|[0-9a-f]{6,}|\d{4}-\d{2}-\d{2}.*)$", re.IGNORECASE
)


def _default_slug_of(run_dir: str) -> str:
    """Best-effort funnel-slug grouping key for a `v2-<RUN_ID>` evidence
    root: strip the `v2-` prefix, then repeatedly strip a trailing
    timestamp/hex-nonce segment (the `<name>-<date>-<hex-suffix>` run-id
    shape used elsewhere in this repo, e.g. `fix/…-20260715-053412` in the
    ledger's own commit-branch naming) until nothing more matches — so a
    doubly-suffixed id like `acme-20260715-abcdef01` reduces to `acme`, not
    a partial `acme-20260715`. Group-by-own-full-id is the safe fallback
    when nothing strips (never over-groups unrelated runs together).
    Callers with a real per-run manifest carrying a `funnel_slug` field
    should inject their own `slug_of` instead of relying on this heuristic.
    """
    base = os.path.basename(run_dir.rstrip("/"))
    if base.startswith("v2-"):
        base = base[len("v2-"):]
    stripped = base
    while True:
        nxt = _RUN_ID_TRAILING_NONCE_RE.sub("", stripped)
        if nxt == stripped:
            break
        stripped = nxt
    return stripped or base


def prune_evidence_roots(
    base_dir: str,
    *,
    keep_n: int = DEFAULT_RETENTION_KEEP_N,
    open_card_referenced_roots: Optional[Sequence[str]] = None,
    blocked_card_referenced_roots: Optional[Sequence[str]] = None,
    slug_of: Optional[Callable[[str], str]] = None,
    compressor: Optional[Callable[[str], str]] = None,
) -> PruneReport:
    """Retention sweep over the run-evidence roots `cc_board.py` already
    discovers (`cc_board.list_evidence_runs` — evidence-root discovery is
    NEVER re-derived here). Keeps the newest `keep_n` roots PER FUNNEL-SLUG
    GROUP (`slug_of(run_dir)`) plus every root in
    `open_card_referenced_roots`; NEVER even considers a root in
    `blocked_card_referenced_roots` (checked first, independently of the
    keep_n/open-card logic). Only ever COMPRESSES an aged-out root — never
    deletes one outright (spec: "compress older", restorable).

    `compressor(run_dir) -> archive_path` performs the real compress in
    production; a fake in tests just records the call so retention SELECTION
    is proven without touching real files unnecessarily.
    """
    runs = cc_board.list_evidence_runs(base_dir)
    slug_fn = slug_of or _default_slug_of
    open_set = set(open_card_referenced_roots or ())
    blocked_set = set(blocked_card_referenced_roots or ())
    compress_fn = compressor or (lambda run_dir: run_dir)

    groups: Dict[str, List[str]] = {}
    for run_dir in runs:
        groups.setdefault(slug_fn(run_dir), []).append(run_dir)

    report = PruneReport(base_dir=base_dir)
    for group in groups.values():
        # v2-<RUN_ID> roots are timestamp-fresh per run (v2-autonomous-
        # build-sop.md: "a fresh RUN_ID"); lexicographic descending on the
        # directory name is the same ordering cc_board.list_evidence_runs
        # already returns runs in (sorted ascending via os.listdir), so
        # reversing it here is newest-first without re-deriving a new sort.
        ordered = sorted(group, reverse=True)
        for idx, run_dir in enumerate(ordered):
            if run_dir in blocked_set:
                report.skipped_blocked.append(run_dir)
                continue
            if idx < keep_n:
                report.kept.append(run_dir)
                continue
            if run_dir in open_set:
                report.kept.append(run_dir)
                report.skipped_open_card.append(run_dir)
                continue
            compress_fn(run_dir)
            report.compressed.append(run_dir)

    return report


# ---------------------------------------------------------------------------
# 6) Board tie-in advisory — /api/health/deep (item 4; B-U13/U27-plumbed)
# ---------------------------------------------------------------------------
def inventory_advisory(
    report: InventoryReport,
    flags: FlagResult,
    *,
    orphan_media: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Reduce one inventory + its flag pass into the `/api/health/deep`
    advisory shape (item 4): `{pages_total, drafts_stale, superseded,
    orphan_media}`. Pure, no I/O — same reduce-from-disk-state discipline as
    `cc_board.reconcile()`'s `.as_dict()`, which the Command Center's own
    `/api/health/deep` probe already consumes (B-U13/U27, verified). This
    function produces the SAME kind of drop-in JSON for the inventory/
    lifecycle facet; CLI `--advisory` prints it for a subprocess-JSON caller."""
    return {
        "location_id": report.location_id,
        "generated_at": report.generated_at,
        "pages_total": len(report.pages),
        "drafts_stale": len(flags.stale),
        "superseded": len(flags.superseded),
        "duplicate_markers": len(flags.duplicates),
        "orphan_media": len(orphan_media or []),
    }


# ---------------------------------------------------------------------------
# 7) Orphaned ZHC media — report-only, never deletes
# ---------------------------------------------------------------------------
def find_orphan_media(
    media_lister: Callable[[], List[Dict[str, Any]]],
    referenced_urls: Sequence[str],
) -> List[Dict[str, Any]]:
    """Report-only (this module never deletes media — item 2's "same
    operator card, report-only" is literal): every ZHC media-library object
    whose URL is not present in `referenced_urls` (the caller's own scan of
    every SURVIVING page's fetched HTML for CDN URLs — both proven read
    primitives elsewhere in this repo, neither invoked directly by this pure
    reducer). `media_lister()` is a caller-injected live read; this function
    performs no I/O of its own."""
    refs = set(referenced_urls or ())
    orphans = []
    for m in media_lister() or []:
        if not isinstance(m, dict):
            continue
        url = m.get("url") or ""
        if url and url not in refs:
            orphans.append(m)
    return orphans


# ---------------------------------------------------------------------------
# Live wiring sketches — NOT exercised by CI (need a real seeded session).
# Kept so a live-proof pass wires this module without re-deriving the
# contract. Same discipline as ghl_selector_drift_probe.live_finder_over_browser_
# manager / live_page_fetcher_over_http.
# ---------------------------------------------------------------------------
def live_page_lister_over_rest_canvas(
    session: str, ab_eval: Callable[[str, str], Any]
) -> Callable[[str, str], List[Dict[str, Any]]]:
    """Return a `page_lister(funnel_id, location_id)` for
    `enumerate_zhc_inventory` that drives a real seeded agent-browser session
    via the PROVEN `ghl_rest_canvas.page_list` step. `ab_eval(session,
    js_expr) -> parsed body` is the thin wrapper the caller already has
    (kept injectable so this module never shells out itself). Deliberately
    NOT exercised by CI/--selftest — needs a real seeded session; the weekly
    maintenance-window sweep or a live-proof pass wires this."""
    import ghl_rest_canvas  # noqa: WPS433 (intentional local import)

    def _lister(funnel_id: str, location_id: str) -> List[Dict[str, Any]]:
        # No `session=` kwarg here deliberately: that path additionally
        # emits an `argv` via ghl_rest_canvas.agent_browser_eval_cmd, which
        # asserts an ACTIVE browser_manager.browser_session() singleton
        # gateway. This sketch only needs the eval JS string; `ab_eval`
        # (the caller's own already-seeded-session wrapper) is what actually
        # runs it — so the singleton-gateway assertion is the live caller's
        # responsibility, not this pure step-builder call's.
        step = ghl_rest_canvas.page_list(funnel_id, location_id)
        body = ab_eval(session, step["eval"])
        if not isinstance(body, dict):
            return []
        for key in ("funnelPages", "pages", "data", "steps"):
            candidate = body.get(key)
            if isinstance(candidate, list):
                return [p for p in candidate if isinstance(p, dict)]
        return []

    return _lister


def live_funnel_lister_over_browser_manager(
    session: str, ab_eval: Callable[[str, str], Any]
) -> Callable[[str], List[Dict[str, Any]]]:
    """UNPROVEN sketch — see the module docstring's "ONE LIVE GAP" note. No
    confirmed route exists yet (public API: none; internal SPA-canvas
    family: only fetch-by-known-id). Raises `NotImplementedError` if ever
    actually called, so a caller can never silently get an empty/fabricated
    funnel list mistaken for "this location truly has zero ZHC funnels" —
    the live-proof pass MUST either confirm a `/funnels/funnel/list` REST
    route or wire a DOM-snapshot walk before this can return real data."""

    def _lister(location_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError(
            "live_funnel_lister_over_browser_manager: no proven live route "
            "for 'list every funnel for a location' exists yet in this repo "
            "— wiring + proving this is a live leg owed to the operator "
            "(parallel to U22), never fabricated. Inject a real "
            "funnel_lister once that route is confirmed."
        )

    return _lister


# ---------------------------------------------------------------------------
# Offline selftest — no network, no browser, no GHL writes
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile

    errors: List[str] = []

    # ---- enumerate_zhc_inventory ----------------------------------------
    def fake_funnels(loc):
        return [
            {"id": "f1", "name": "ZHC Founders Circle"},
            {"id": "f2", "name": "Not ZHC — client's own funnel"},
        ]

    def fake_pages(funnel_id, loc):
        if funnel_id == "f1":
            return [
                {"id": "p1", "name": "ZHC Page One", "marker": "zhc-p1",
                 "status": "draft", "createdAt": "2020-01-01T00:00:00Z"},
                {"id": "p2", "name": "ZHC Page Two", "marker": "zhc-p2",
                 "status": "published", "createdAt": "2026-07-01T00:00:00Z"},
            ]
        return [{"id": "x1", "name": "should never appear", "status": "draft"}]

    report = enumerate_zhc_inventory(
        "loc1", funnel_lister=fake_funnels, page_lister=fake_pages,
        now=lambda: "2026-07-15T00:00:00Z",
    )
    if len(report.pages) != 2:
        errors.append(f"enumerate should skip the non-ZHC funnel entirely: {report.pages}")
    if any(p.page == "x1" for p in report.pages):
        errors.append("non-ZHC funnel's pages leaked into the inventory")

    # inventory write/load round-trip
    with tempfile.TemporaryDirectory() as tmp:
        path = write_inventory(tmp, report)
        if not os.path.isfile(path):
            errors.append("write_inventory did not create a file")
        loaded = load_inventory(path)
        if loaded is None or len(loaded.pages) != 2:
            errors.append(f"load_inventory round-trip broken: {loaded}")

    # ---- flag_lifecycle_candidates: stale ---------------------------------
    flags = flag_lifecycle_candidates(report, now="2026-07-15T00:00:00Z", stale_draft_days=30)
    if [c["id"] for c in flags.stale] != ["p1"]:
        errors.append(f"stale flag should catch only p1 (old draft): {flags.stale}")
    if any(c["id"] == "p2" for c in flags.stale):
        errors.append("a PUBLISHED page must never be flagged stale regardless of age")

    # a page that later published, even if old, is never flagged
    published_old = enumerate_zhc_inventory(
        "loc1",
        funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
        page_lister=lambda f, loc: [{"id": "p9", "name": "ZHC old but live",
                                      "status": "published",
                                      "createdAt": "2019-01-01T00:00:00Z"}],
        now=lambda: "2026-07-15T00:00:00Z",
    )
    flags2 = flag_lifecycle_candidates(published_old, now="2026-07-15T00:00:00Z")
    if flags2.stale:
        errors.append("published pages must never be flagged stale, no matter how old")

    # unparsable created -> never guessed/flagged
    bad_ts = enumerate_zhc_inventory(
        "loc1",
        funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
        page_lister=lambda f, loc: [{"id": "p10", "name": "ZHC bad ts",
                                      "status": "draft", "createdAt": "not-a-date"}],
        now=lambda: "2026-07-15T00:00:00Z",
    )
    flags3 = flag_lifecycle_candidates(bad_ts, now="2026-07-15T00:00:00Z")
    if flags3.stale:
        errors.append("an unparsable created timestamp must never be treated as stale")

    # ---- flag_lifecycle_candidates: superseded ----------------------------
    superseded_report = enumerate_zhc_inventory(
        "loc1",
        funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
        page_lister=lambda f, loc: [
            {"id": "old", "name": "ZHC Landing", "marker": "m-old",
             "status": "published", "createdAt": "2026-01-01T00:00:00Z"},
            {"id": "new", "name": "ZHC Landing", "marker": "m-new",
             "status": "published", "createdAt": "2026-06-01T00:00:00Z"},
        ],
        now=lambda: "2026-07-15T00:00:00Z",
    )
    flags4 = flag_lifecycle_candidates(superseded_report, now="2026-07-15T00:00:00Z")
    if [c["id"] for c in flags4.superseded] != ["old"]:
        errors.append(f"superseded flag should catch only the older 'old' page: {flags4.superseded}")
    if flags4.superseded and flags4.superseded[0]["superseded_by"] != "new":
        errors.append("superseded reason must name the newer marker's page as the successor")

    # ---- detect_duplicate_markers (reuses ghl_method.resolve_install_target) --
    dup_report = enumerate_zhc_inventory(
        "loc1",
        funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
        page_lister=lambda f, loc: [
            {"id": "d1", "name": "ZHC A", "marker": "shared-marker", "status": "draft"},
            {"id": "d2", "name": "ZHC B", "marker": "shared-marker", "status": "draft"},
        ],
        now=lambda: "2026-07-15T00:00:00Z",
    )
    dups = detect_duplicate_markers(dup_report)
    if len(dups) != 1 or sorted(dups[0]["ambiguous_ids"]) != ["d1", "d2"]:
        errors.append(f"duplicate-marker detection broken: {dups}")
    # cross-check: the SAME condition really does raise InstallTargetError
    # at the source-of-truth function — never a re-derived rule.
    try:
        ghl_method.resolve_install_target(
            [{"id": "d1", "marker": "shared-marker"}, {"id": "d2", "marker": "shared-marker"}],
            "shared-marker",
        )
        errors.append("expected InstallTargetError to prove the duplicate rule is the same one")
    except ghl_method.InstallTargetError:
        pass

    # ---- post_lifecycle_card: idempotent event-ledger dedupe --------------
    with tempfile.TemporaryDirectory() as tmp:
        ledger_path = os.path.join(tmp, "card-ledger.json")
        calls = []
        result1 = post_lifecycle_card(
            CARD_KIND_STALE, flags.stale, ledger_path=ledger_path,
            board_notifier=lambda payload: calls.append(payload),
            now=lambda: "2026-07-15T00:00:00Z",
        )
        result2 = post_lifecycle_card(
            CARD_KIND_STALE, flags.stale, ledger_path=ledger_path,
            board_notifier=lambda payload: calls.append(payload),
            now=lambda: "2026-07-16T00:00:00Z",
        )
        if len(calls) != 1:
            errors.append(f"post_lifecycle_card must notify exactly ONCE across repeat runs, got {len(calls)}")
        if not result1["posted"] or result2["posted"]:
            errors.append(f"first call should post, second should dedupe: {result1} / {result2}")
        if result1["dedupe_key"] != result2["dedupe_key"]:
            errors.append("same candidate set must produce the same dedupe key")

        # A DIFFERENT candidate set gets its OWN card (not deduped away).
        other_candidates = [{"id": "zzz", "funnel": "f9", "marker": "m9", "reason": "test"}]
        result3 = post_lifecycle_card(
            CARD_KIND_STALE, other_candidates, ledger_path=ledger_path,
            board_notifier=lambda payload: calls.append(payload),
            now=lambda: "2026-07-16T00:00:00Z",
        )
        if len(calls) != 2 or not result3["posted"]:
            errors.append("a genuinely different candidate set must get its own fresh card")

        # A failing board_notifier is recorded as NOT delivered (retryable).
        ledger_path2 = os.path.join(tmp, "card-ledger-2.json")
        def _boom(payload):
            raise RuntimeError("board down")
        result4 = post_lifecycle_card(
            CARD_KIND_DUPLICATE, dups, ledger_path=ledger_path2, board_notifier=_boom,
        )
        if result4["posted"] is not False or result4["error"] != "board down":
            errors.append(f"a failing board_notifier must record delivered=False, not raise: {result4}")
        # retried on the next call once the board is back up.
        result5 = post_lifecycle_card(
            CARD_KIND_DUPLICATE, dups, ledger_path=ledger_path2,
            board_notifier=lambda payload: "ok",
        )
        if not result5["posted"]:
            errors.append("an undelivered card must be retried on the next run, not permanently deduped")

    # ---- execute_approved_deletes: fail-closed guard (acceptance e) -------
    with tempfile.TemporaryDirectory() as tmp:
        ledger_path = os.path.join(tmp, "card-ledger.json")
        post = post_lifecycle_card(
            CARD_KIND_STALE, flags.stale, ledger_path=ledger_path,
            board_notifier=lambda payload: "ok",
        )
        key = post["dedupe_key"]

        # (e) — an id never flagged/carded/approved must be REFUSED, and
        # NOTHING may delete, not even the id(s) that WOULD be legitimate.
        deleter_calls = []
        try:
            execute_approved_deletes(
                key, ["never-flagged-id"], ledger_path=ledger_path,
                exporter=lambda i: {"id": i}, deleter=lambda i: deleter_calls.append(i),
                prober=lambda i: True, evidence_base=tmp,
            )
            errors.append("execute_approved_deletes must REFUSE an id outside the card's candidates")
        except LifecycleGuardError:
            pass
        if deleter_calls:
            errors.append("the fail-closed guard must call deleter ZERO times on a refusal")

        # an unknown/undelivered dedupe_key is refused outright.
        try:
            execute_approved_deletes(
                "not-a-real-key", ["p1"], ledger_path=ledger_path,
                exporter=lambda i: {"id": i}, deleter=lambda i: deleter_calls.append(i),
                prober=lambda i: True, evidence_base=tmp,
            )
            errors.append("execute_approved_deletes must REFUSE an unknown dedupe_key")
        except LifecycleGuardError:
            pass
        if deleter_calls:
            errors.append("an unknown-card refusal must call deleter ZERO times")

        # (c) — a LEGITIMATE approved delete: present -> export -> delete ->
        # absent, with receipts.
        present_state = {"p1": True}
        def _prober(i):
            return present_state.get(i, False)
        def _deleter(i):
            present_state[i] = False
        report_exec = execute_approved_deletes(
            key, ["p1"], ledger_path=ledger_path,
            exporter=lambda i: {"id": i, "page_data": "restorable copy"},
            deleter=_deleter, prober=_prober, evidence_base=tmp,
            now=lambda: "2026-07-15T00:00:01Z",
        )
        if not report_exec.all_deleted():
            errors.append(f"a legitimate approved delete should succeed cleanly: {report_exec.to_dict()}")
        entry = report_exec.results[0]
        if not (entry.get("present_before") and entry.get("absent_after")):
            errors.append(f"missing present->absent proof: {entry}")
        if not os.path.isfile(entry.get("export_path", "")):
            errors.append("pre-delete restorable export was not written to disk")
        if not os.path.isfile(entry.get("receipt_path", "")):
            errors.append("delete receipt was not written to disk")

        # deleting an already-ABSENT approved id is skipped, never fabricated.
        present_state["p1"] = False
        # re-post a card for p1 alone so it's independently approvable again.
        ledger_path3 = os.path.join(tmp, "card-ledger-3.json")
        post2 = post_lifecycle_card(
            CARD_KIND_STALE, [{"id": "p1"}], ledger_path=ledger_path3,
            board_notifier=lambda payload: "ok",
        )
        report_exec2 = execute_approved_deletes(
            post2["dedupe_key"], ["p1"], ledger_path=ledger_path3,
            exporter=lambda i: {"id": i}, deleter=lambda i: deleter_calls.append(i),
            prober=_prober, evidence_base=tmp,
        )
        if report_exec2.results[0]["status"] != "skipped-not-present":
            errors.append("an already-absent id must be skipped, never re-deleted/fabricated")
        if "p1" in deleter_calls:
            errors.append("deleter must never be called for an already-absent id")

    # ---- prune_evidence_roots ---------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        def _mk_run(name):
            run_dir = os.path.join(tmp, name)
            os.makedirs(os.path.join(run_dir, "routing"), exist_ok=True)
            with open(os.path.join(run_dir, "routing", "intake-receipt.json"), "w") as fh:
                json.dump({"ok": True}, fh)
            return run_dir

        # 12 runs in the same slug group ("acme") -> keep newest 10, compress 2.
        made = [_mk_run(f"v2-acme-{i:02d}") for i in range(12)]
        compressed_calls = []
        prune = prune_evidence_roots(
            tmp, keep_n=10,
            slug_of=lambda d: "acme",  # force one group for a deterministic test
            compressor=lambda d: compressed_calls.append(d) or d,
        )
        if len(prune.kept) != 10 or len(prune.compressed) != 2:
            errors.append(f"prune should keep 10 / compress 2 of 12: kept={len(prune.kept)} compressed={len(prune.compressed)}")
        if set(compressed_calls) != set(prune.compressed):
            errors.append("compressor must be called for exactly the compressed set")

        # a root referenced by an OPEN card is kept even past keep_n.
        oldest = sorted(made)[0]
        prune2 = prune_evidence_roots(
            tmp, keep_n=10, slug_of=lambda d: "acme",
            open_card_referenced_roots=[oldest],
            compressor=lambda d: d,
        )
        if oldest not in prune2.kept or oldest in prune2.compressed:
            errors.append("a root referenced by an open card must never be compressed")

        # a root referenced by a BLOCKED card is skipped even if it would
        # otherwise be kept (never even considered for compression).
        newest = sorted(made)[-1]
        prune3 = prune_evidence_roots(
            tmp, keep_n=1, slug_of=lambda d: "acme",
            blocked_card_referenced_roots=[newest],
            compressor=lambda d: d,
        )
        if newest not in prune3.skipped_blocked or newest in prune3.compressed:
            errors.append("a root referenced by a blocked card must be skipped, never compressed")

    # ---- inventory_advisory -------------------------------------------------
    advisory = inventory_advisory(report, flags, orphan_media=[{"id": "m1"}])
    if advisory != {
        "location_id": "loc1", "generated_at": "2026-07-15T00:00:00Z",
        "pages_total": 2, "drafts_stale": 1, "superseded": 0,
        "duplicate_markers": 0, "orphan_media": 1,
    }:
        errors.append(f"inventory_advisory shape/values wrong: {advisory}")

    # ---- find_orphan_media (report-only) -----------------------------------
    orphans = find_orphan_media(
        lambda: [{"id": "m1", "url": "https://cdn/a.png"},
                 {"id": "m2", "url": "https://cdn/b.png"}],
        referenced_urls=["https://cdn/a.png"],
    )
    if [o["id"] for o in orphans] != ["m2"]:
        errors.append(f"find_orphan_media should report only the unreferenced one: {orphans}")

    # ---- live_funnel_lister_over_browser_manager: honest NotImplementedError --
    sketch = live_funnel_lister_over_browser_manager("sess", lambda s, e: None)
    try:
        sketch("loc1")
        errors.append("the unproven funnel-list live route must never silently return data")
    except NotImplementedError:
        pass

    # ---- live_page_lister_over_rest_canvas: pure expression-building, no I/O --
    seen = []
    def _fake_ab_eval(session, js):
        seen.append(js)
        return {"funnelPages": [{"id": "px", "name": "ZHC Live"}]}
    live_lister = live_page_lister_over_rest_canvas("sess", _fake_ab_eval)
    live_pages = live_lister("f1", "loc1")
    if [p["id"] for p in live_pages] != ["px"]:
        errors.append(f"live_page_lister_over_rest_canvas parsing broken: {live_pages}")
    if not seen or "funnelId=f1" not in seen[-1]:
        errors.append("live_page_lister_over_rest_canvas must emit the real page_list eval")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — ghl_inventory (U31/B-U17) verified (no network / no browser)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="run offline selftest, no network/browser")
    ap.add_argument("--advisory", action="store_true",
                     help="reduce an inventory + flags JSON pair into the /api/health/deep shape")
    ap.add_argument("--inventory-json", help="path to a written inventory.json (with --advisory)")
    ap.add_argument("--flags-json", help="path to a written flags.json (with --advisory)")
    ap.add_argument("--prune", action="store_true",
                     help="run the evidence-root retention sweep (compress-only, never deletes)")
    ap.add_argument("--base-dir", help="evidence base dir (with --prune); defaults to "
                     "cc_board.resolve_evidence_base()")
    ap.add_argument("--keep-n", type=int, default=DEFAULT_RETENTION_KEEP_N,
                     help="roots to keep per funnel-slug group (with --prune)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.advisory:
        if not args.inventory_json:
            print("ERROR: --advisory requires --inventory-json", file=sys.stderr)
            return 2
        report = load_inventory(args.inventory_json)
        if report is None:
            print(f"ERROR: could not load inventory JSON: {args.inventory_json}", file=sys.stderr)
            return 2
        flags_data = _read_json(args.flags_json) if args.flags_json else None
        flags = FlagResult(**flags_data) if isinstance(flags_data, dict) else flag_lifecycle_candidates(report)
        print(json.dumps(inventory_advisory(report, flags), indent=2, sort_keys=True))
        return 0

    if args.prune:
        base_dir = args.base_dir or cc_board.resolve_evidence_base()
        if not base_dir:
            print("ERROR: no evidence base dir resolvable (pass --base-dir or set HOME)", file=sys.stderr)
            return 2
        report = prune_evidence_roots(base_dir, keep_n=args.keep_n)
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
