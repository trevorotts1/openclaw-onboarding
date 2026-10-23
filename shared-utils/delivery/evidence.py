"""
shared-utils/delivery/evidence.py — truthful evidence and receipt states for
the GHL delivery stream (W4B, stream W4 "Durable execution").

One writer for this file: assignment W4B. States (GHL-DELIVERY-SPEC.md
"Delivery contract"): PLANNED -> CREATED -> CONFIGURED -> PUBLISHED -> VERIFIED
are DISTINCT claims, and every one of them is earned by its own evidence:

    PLANNED     intent recorded; nothing exists on the platform yet.
    CREATED     a native id was read back from the platform.
    CONFIGURED  configuration was read back and matched the requested value
                (spec gap 2: set AND read back — never a blind toggle).
    PUBLISHED   a real public URL was read back (saving is never publishing).
    VERIFIED    a live check of the published artifact passed.

Truth rules enforced here:

1. Adjacent, one step at a time. A receipt never skips a state; multi-step
   callers advance once per state, each with that state's evidence.
2. Evidence is kind-checked. Each state requires its own evidence kind —
   a config readback never earns PUBLISHED, a publish URL never earns VERIFIED.
3. Readbacks must match. Evidence carrying expected/observed values backs a
   state only when observed == expected; a mismatch earns no state.
4. Evidence names real sources. `source` and `detail` are non-empty strings
   naming the real file path, command, or URL the proof came from.
5. Saving != publishing. to_dict/from_dict round-trip preserves state exactly;
   persistence never advances it, and a loaded receipt cannot claim a state
   its evidence chain does not prove (fabricated dicts fail closed).
6. Limitations fail closed at done. A receipt carrying a recorded platform
   limitation (a disabled or missing capability) can never be marked VERIFIED —
   reported as incomplete, never as done.
7. One page published != all published. `state_counts` reports per-state
   counts against the explicit denominator and the every-receipt flags
   separately; nothing infers whole-site publication.
8. Identity is location/kind/parent/logical_id — never name alone.

Integration seams (provisional — GHL-DELIVERY-SPEC.md "confirmed gaps":
upstream modules may not exist yet; these call sites are the contract):

- W1A npage_contract: logical ids are plain strings here; the delivery schema
  owns their shape. Pass schema-validated ids through unchanged.
- W4A checkpoints.py: persistence is its job. Use Receipt.to_dict/from_dict;
  this module performs no IO and never advances state on load.
- W7A publishing coordinator: call mark_published only with the URL actually
  read back from the platform; mark_verified only from a live check.
- W11 cc_board: consume state_counts for configured-object / published /
  owner-accepted rows; the mapping is W11's, the counts are honest here.

Import pattern (from any script in the repo):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared-utils"))
    from delivery.evidence import plan, mark_created

Run the assert-based self-check:

    python3 -I shared-utils/delivery/evidence.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from typing import Dict, Iterable, Mapping, Optional, Tuple
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# STATES — distinct claims, in strict order. Ordering is the contract: every
# transition is exactly one step forward, never a skip and never a downgrade.
# ---------------------------------------------------------------------------
PLANNED = "PLANNED"
CREATED = "CREATED"
CONFIGURED = "CONFIGURED"
PUBLISHED = "PUBLISHED"
VERIFIED = "VERIFIED"

STATES: Tuple[str, ...] = (PLANNED, CREATED, CONFIGURED, PUBLISHED, VERIFIED)
_STATE_INDEX: Mapping[str, int] = {s: i for i, s in enumerate(STATES)}

# Evidence kinds — one per state above PLANNED. PLANNED is the receipt's own
# intent record and needs no external proof; every later state does.
NATIVE_ID_READBACK = "native_id_readback"
CONFIG_READBACK = "config_readback"
PUBLIC_URL_READBACK = "public_url_readback"
LIVE_CHECK = "live_check"

EVIDENCE_KINDS: Tuple[str, ...] = (
    NATIVE_ID_READBACK,
    CONFIG_READBACK,
    PUBLIC_URL_READBACK,
    LIVE_CHECK,
)

REQUIRED_EVIDENCE_KIND: Mapping[str, Optional[str]] = {
    PLANNED: None,
    CREATED: NATIVE_ID_READBACK,
    CONFIGURED: CONFIG_READBACK,
    PUBLISHED: PUBLIC_URL_READBACK,
    VERIFIED: LIVE_CHECK,
}


class EvidenceError(ValueError):
    """Contract violation: a state was claimed without its own matching,
    sourced evidence — or a limitation tried to pass as done."""


def _require_text(value: str, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{what} must be a non-empty string")
    return value.strip()


def _require_state(state: str) -> str:
    if state not in _STATE_INDEX:
        raise EvidenceError(f"unknown state {state!r}; valid: {STATES}")
    return state


@dataclass(frozen=True)
class Evidence:
    """One proof item, naming the real source it came from.

    expected/observed carry readback pairs (spec gap 2): when both are set
    the evidence backs a state only if they match — a blind toggle that was
    never read back, or read back wrong, earns nothing.
    """

    kind: str
    source: str
    detail: str
    expected: Optional[str] = None
    observed: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in EVIDENCE_KINDS:
            raise EvidenceError(f"unknown evidence kind {self.kind!r}; valid: {EVIDENCE_KINDS}")
        object.__setattr__(self, "source", _require_text(self.source, "evidence source"))
        object.__setattr__(self, "detail", _require_text(self.detail, "evidence detail"))
        for label, value in (("expected", self.expected), ("observed", self.observed)):
            if value is not None and not isinstance(value, str):
                raise EvidenceError(f"evidence {label} must be a string or None")

    @property
    def matches(self) -> bool:
        """A readback pair matches only when observed equals expected."""
        return self.expected is None or self.expected == self.observed

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "kind": self.kind,
            "source": self.source,
            "detail": self.detail,
            "expected": self.expected,
            "observed": self.observed,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Optional[str]]) -> "Evidence":
        return cls(
            kind=str(data.get("kind") or ""),
            source=str(data.get("source") or ""),
            detail=str(data.get("detail") or ""),
            expected=data.get("expected"),
            observed=data.get("observed"),
        )


def _validate_chain(state: str, evidence: Tuple[Evidence, ...]) -> None:
    """The evidence chain must prove exactly every state after PLANNED up to
    `state`, in order, each of that state's required kind and matching. A
    loaded or hand-built receipt can never claim more than it proves."""
    chain_states = STATES[1:_STATE_INDEX[state] + 1]
    if len(evidence) != len(chain_states):
        raise EvidenceError(
            f"state {state} needs exactly {len(chain_states)} evidence records "
            f"({', '.join(chain_states)}), got {len(evidence)}"
        )
    for st, ev in zip(chain_states, evidence):
        required = REQUIRED_EVIDENCE_KIND[st]
        if ev.kind != required:
            raise EvidenceError(
                f"evidence for {st} must be kind {required!r}, got {ev.kind!r}"
            )
        if not ev.matches:
            raise EvidenceError(
                f"readback mismatch in evidence for {st} "
                f"(expected={ev.expected!r} observed={ev.observed!r})"
            )


@dataclass(frozen=True)
class Receipt:
    """State and evidence for one delivery object, keyed by identity —
    location/kind/parent/logical_id — never by name alone.

    limitations records real platform restrictions (disabled or missing
    capabilities); a receipt carrying any can never reach VERIFIED.
    """

    logical_id: str
    location: str
    kind: str
    state: str = PLANNED
    parent: Optional[str] = None
    name: Optional[str] = None
    evidence: Tuple[Evidence, ...] = ()
    limitations: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "logical_id", _require_text(self.logical_id, "logical_id"))
        object.__setattr__(self, "location", _require_text(self.location, "location"))
        object.__setattr__(self, "kind", _require_text(self.kind, "receipt kind"))
        _require_state(self.state)
        if not isinstance(self.evidence, tuple):
            object.__setattr__(self, "evidence", tuple(self.evidence))
        if not isinstance(self.limitations, tuple):
            object.__setattr__(self, "limitations", tuple(self.limitations))
        for item in self.evidence:
            if not isinstance(item, Evidence):
                raise EvidenceError("receipt evidence must be Evidence records")
        for item in self.limitations:
            _require_text(item, "limitation")
        _validate_chain(self.state, self.evidence)
        if self.state == VERIFIED and self.limitations:
            raise EvidenceError(
                "receipt carries recorded platform limitations; a disabled or "
                "missing capability is incomplete, never VERIFIED"
            )

    @property
    def identity(self) -> Tuple[str, str, str, str]:
        """(location, kind, parent, logical_id) — the dedupe/reconcile key."""
        return (self.location, self.kind, self.parent or "", self.logical_id)

    def to_dict(self) -> Dict[str, object]:
        return {
            "logical_id": self.logical_id,
            "location": self.location,
            "kind": self.kind,
            "state": self.state,
            "parent": self.parent,
            "name": self.name,
            "evidence": [e.to_dict() for e in self.evidence],
            "limitations": list(self.limitations),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Receipt":
        state = _require_state(str(data.get("state")))
        evidence = tuple(Evidence.from_dict(e) for e in data.get("evidence") or ())  # type: ignore[arg-type]
        limitations = tuple(str(x) for x in data.get("limitations") or ())
        return cls(
            logical_id=str(data.get("logical_id") or ""),
            location=str(data.get("location") or ""),
            kind=str(data.get("kind") or ""),
            state=state,
            parent=data.get("parent"),  # type: ignore[arg-type]
            name=data.get("name"),  # type: ignore[arg-type]
            evidence=evidence,
            limitations=limitations,
        )


def plan(
    logical_id: str,
    location: str,
    kind: str,
    parent: Optional[str] = None,
    name: Optional[str] = None,
) -> Receipt:
    """A PLANNED receipt: intent recorded, nothing created anywhere yet."""
    return Receipt(
        logical_id=logical_id, location=location, kind=kind,
        parent=parent, name=name, state=PLANNED,
    )


def advance(receipt: Receipt, to_state: str, evidence: Evidence) -> Receipt:
    """Move a receipt exactly one state forward, backed by that state's
    evidence kind. Adjacent-only; skips, downgrades, wrong kinds, mismatched
    readbacks, and VERIFIED-over-a-limitation all fail closed."""
    if not isinstance(receipt, Receipt):
        raise EvidenceError("advance requires a Receipt")
    _require_state(to_state)
    if not isinstance(evidence, Evidence):
        raise EvidenceError("advance requires an Evidence record")
    cur = _STATE_INDEX[receipt.state]
    nxt = _STATE_INDEX[to_state]
    if nxt != cur + 1:
        raise EvidenceError(
            f"state {receipt.state} -> {to_state} is not one adjacent step; "
            f"advance once per state with that state's evidence"
        )
    required = REQUIRED_EVIDENCE_KIND[to_state]
    if evidence.kind != required:
        raise EvidenceError(
            f"state {to_state} requires evidence kind {required!r}, got {evidence.kind!r}"
        )
    if not evidence.matches:
        raise EvidenceError(
            f"readback mismatch (expected={evidence.expected!r} "
            f"observed={evidence.observed!r}) earns no state"
        )
    return replace(receipt, state=to_state, evidence=receipt.evidence + (evidence,))


def mark_created(receipt: Receipt, native_id: str, source: str, detail: str = "") -> Receipt:
    """CREATED: the native id was read back from the platform."""
    native_id = _require_text(native_id, "native_id")
    return advance(
        receipt, CREATED,
        Evidence(NATIVE_ID_READBACK, source, detail or f"native id readback: {native_id}"),
    )


def mark_configured(
    receipt: Receipt, source: str, expected: str, observed: str, detail: str = ""
) -> Receipt:
    """CONFIGURED: the setting was read back and matched the request."""
    expected = _require_text(expected, "expected value")
    observed = _require_text(observed, "observed value")
    return advance(
        receipt, CONFIGURED,
        Evidence(CONFIG_READBACK, source, detail or f"config readback {expected!r}",
                 expected=expected, observed=observed),
    )


def mark_published(receipt: Receipt, public_url: str, source: str, detail: str = "") -> Receipt:
    """PUBLISHED: a real public URL was read back. Saving is never publishing."""
    public_url = _require_text(public_url, "public_url")
    parsed = urlparse(public_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise EvidenceError(f"public_url must be an absolute http(s) URL, got {public_url!r}")
    return advance(
        receipt, PUBLISHED,
        Evidence(PUBLIC_URL_READBACK, source, detail or f"public URL readback: {public_url}"),
    )


def mark_verified(receipt: Receipt, source: str, detail: str = "") -> Receipt:
    """VERIFIED: a live check of the published artifact passed."""
    return advance(
        receipt, VERIFIED,
        Evidence(LIVE_CHECK, source, detail or "live check passed"),
    )


def record_limitation(receipt: Receipt, text: str, capability: Optional[str] = None) -> Receipt:
    """Record a real platform restriction. State is untouched — and the
    receipt can never be marked VERIFIED afterwards."""
    text = _require_text(text, "limitation text")
    label = f"{_require_text(capability, 'capability')}: {text}" if capability else text
    return replace(receipt, limitations=receipt.limitations + (label,))


# ---------------------------------------------------------------------------
# Counts — honest aggregates with explicit denominators. One page published is
# never all published; each every_* flag is computed per receipt.
# ---------------------------------------------------------------------------

def state_counts(receipts: Iterable[Receipt]) -> Dict[str, object]:
    """Per-state counts against the explicit denominator (total), plus
    every-receipt flags computed independently — nothing inferred."""
    receipts = tuple(receipts)
    per_state = {s: 0 for s in STATES}
    for r in receipts:
        _require_state(r.state)
        per_state[r.state] += 1
    total = len(receipts)

    def _all_at_least(state: str) -> bool:
        return total > 0 and all(_STATE_INDEX[r.state] >= _STATE_INDEX[state] for r in receipts)

    return {
        "denominator": total,
        "per_state": per_state,
        "every_created": _all_at_least(CREATED),
        "every_configured": _all_at_least(CONFIGURED),
        "every_published": _all_at_least(PUBLISHED),
        "every_verified": _all_at_least(VERIFIED),
        "limited": sum(1 for r in receipts if r.limitations),
    }


def missing_receipts(expected_ids: Iterable[str], receipts: Iterable[Receipt]) -> Tuple[str, ...]:
    """Expected logical ids with no receipt at all — surfaced, never silently
    dropped (spec: report real platform restrictions)."""
    present = {r.logical_id for r in receipts}
    return tuple(sorted(i for i in (_require_text(e, "expected id") for e in expected_ids)
                        if i not in present))


# ---------------------------------------------------------------------------
# Self-check — assert-based, no framework, no IO beyond stdout.
# ---------------------------------------------------------------------------

def _selfcheck() -> int:
    passed = 0

    def ok(cond: bool, msg: str) -> None:
        nonlocal passed
        assert cond, msg
        passed += 1

    def raises(fn, msg: str) -> None:
        nonlocal passed
        try:
            fn()
        except EvidenceError:
            passed += 1
            return
        raise AssertionError(msg)

    src = "evidence.py self-check"

    # 1 — plan: PLANNED with no evidence; identity never uses name alone
    r = plan("page-1", "funnel/alpha", "page", parent="funnel-alpha", name="Home")
    ok(r.state == PLANNED and r.evidence == (), "plan() is PLANNED with no evidence")
    ok(r.identity == ("funnel/alpha", "page", "funnel-alpha", "page-1"),
       "identity is location/kind/parent/logical_id")
    twin = plan("page-2", "funnel/alpha", "page", parent="funnel-alpha", name="Home")
    ok(r.identity != twin.identity, "same name, different logical_id -> different identity")

    # 2 — full chain: each state earned by its own evidence kind
    r2 = mark_created(r, "nat-77", src)
    ok(r2.state == CREATED and len(r2.evidence) == 1, "mark_created -> CREATED")
    r3 = mark_configured(r2, src, expected="true", observed="true")
    ok(r3.state == CONFIGURED, "matching readback -> CONFIGURED")
    r4 = mark_published(r3, "https://example.com/home", src)
    ok(r4.state == PUBLISHED, "public URL readback -> PUBLISHED")
    r5 = mark_verified(r4, src)
    ok(r5.state == VERIFIED and len(r5.evidence) == 4, "live check -> VERIFIED, 4 evidence records")
    ok(r.state == PLANNED, "advance never mutates the original receipt")

    # 3 — adjacent-only: skips and downgrades fail
    raises(lambda: mark_published(r, "https://example.com/x", src),
           "PLANNED -> PUBLISHED must fail (skip)")
    raises(lambda: mark_created(r5, "nat-88", src),
           "VERIFIED -> CREATED must fail (downgrade)")

    # 4 — kind-checked: wrong evidence kind earns nothing
    raises(lambda: advance(r, CREATED, Evidence(CONFIG_READBACK, src, "wrong kind")),
           "config readback must not earn CREATED")

    # 5 — readback must match (spec gap 2: never a blind toggle)
    raises(lambda: mark_configured(r2, src, expected="true", observed="false"),
           "mismatched config readback must not earn CONFIGURED")
    bad_chain = (
        Evidence(NATIVE_ID_READBACK, src, "native id readback: nat-9"),
        Evidence(CONFIG_READBACK, src, "lie", expected="true", observed="false"),
    )
    raises(lambda: Receipt(logical_id="p", location="l", kind="page",
                           state=CONFIGURED, evidence=bad_chain),
           "fabricated chain with mismatched readback must fail closed")

    # 6 — saving != publishing: round-trip preserves state, fabrication fails
    blob = r4.to_dict()
    loaded = Receipt.from_dict(blob)
    ok(loaded == r4 and loaded.state == PUBLISHED,
       "to_dict/from_dict round-trip preserves state exactly")
    lied = dict(blob, state=VERIFIED)  # claims VERIFIED without the live check
    raises(lambda: Receipt.from_dict(lied),
           "loaded receipt claiming VERIFIED without LIVE_CHECK chain must fail")
    raises(lambda: Receipt.from_dict(dict(blob, state="SHIPPED")),
           "unknown state in a loaded receipt must fail")

    # 7 — PUBLISHED needs a real public URL
    raises(lambda: mark_published(r3, "example.com/home", src),
           "non-absolute URL must not earn PUBLISHED")
    raises(lambda: mark_published(r3, "", src), "empty URL must fail")

    # 8 — limitations fail closed at done
    lim = record_limitation(r4, "publish API disabled", capability="ghl_publish")
    ok(lim.state == PUBLISHED and len(lim.limitations) == 1,
       "record_limitation keeps state, records restriction")
    raises(lambda: mark_verified(lim, src),
           "VERIFIED over a recorded limitation must fail")
    ok("ghl_publish" in lim.limitations[0], "limitation names the capability")

    # 9 — counts: explicit denominator, every_* per receipt, nothing inferred
    c = state_counts([r, r2, r4])
    ok(c["denominator"] == 3, "counts carry explicit denominator")
    ok(c["per_state"][PLANNED] == 1 and c["per_state"][CREATED] == 1
       and c["per_state"][PUBLISHED] == 1, "per-state counts are exact")
    ok(c["every_published"] is False and c["every_verified"] is False,
       "one page published is never all published")
    ok(c["limited"] == 0, "limited count is exact")
    c2 = state_counts([r4, r5])
    ok(c2["every_published"] is True and c2["every_verified"] is False,
       "every_published true only when every receipt is at least PUBLISHED")
    c3 = state_counts([])
    ok(c3["denominator"] == 0 and c3["every_published"] is False,
       "empty receipts: denominator 0, no flags claimed")

    # 10 — dropped pages are surfaced, never silent
    missing = missing_receipts(["page-1", "page-3", "page-2"], [r, twin])
    ok(missing == ("page-3",), "missing_receipts reports the dropped id")

    print(f"OK {passed} PASS")
    return 0


if __name__ == "__main__":
    sys.exit(_selfcheck())
