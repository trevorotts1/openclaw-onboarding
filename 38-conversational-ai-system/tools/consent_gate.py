#!/usr/bin/env python3
"""consent_gate.py - scoped refusal, global opt-out, human precedence.

Contract basis: Purple-Billboard DATA-CONTRACTS section 7 ("Capture, refusal
and one SMS email ask"), applied at the section 3 fresh gate. Python 3
standard library only.

Section 7 precedence, implemented in this order and reported that way:

  1. global stop        suppresses outbound for that contact, every channel
  2. channel opt-out    blocks THAT channel only
  3. sequence refusal   blocks THAT sequence only
  4. human ownership    fences the bot until an explicit release
  5. field refusal      suppresses that ask/topic/offer/campaign only

"Unknown refusal scope is not broader permission": when a dispatch does not
say which channel it is on and a channel opt-out exists, the gate BLOCKS
(SUPPRESSED, reason channel_unresolved) instead of assuming the refusal was
about some other channel. The same rule applies to the legacy
contacts.suppression column, which records no channel at all.

A refusal is never broader than the scope recorded: a topic refusal cannot
block a different topic, a channel opt-out cannot block another channel, and
a global stop overrides every narrower grant. A grant lifts exactly its own
scope (latest decision wins per exact scope), and NEVER lifts a human fence
or a global stop recorded at the global scope - those need their own explicit
release, which is the point of the fence.

Every decision here is evaluated by the caller's gate ON EVERY DISPATCH
(see make_gate_evaluator), so a suppression recorded after an action was
queued still blocks the send: queue-time consent is never permission.

Capture: ConsentCapture wraps collection_lock.CaptureStore, so a consent
capture that fails midway resumes from its own cursor in a new process, never
restarts from step 0, and a rejected capture stays rejected and cannot be
advanced. A decision row is written at most once per (capture, step) before
the cursor moves, so a crash between the two is replayed idempotently.

Storage lives in the same SQLite file as tenant_identity/collection_lock (own
tables, additive) so one database is one tenant boundary. tenant_identity and
collection_lock are dependencies and are not modified here.

Import:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tenant_identity import TenantIdentity
    from consent_gate import ConsentStore, ConsentCapture, make_gate_evaluator

Assert-based self-check:  python3 -I consent_gate.py
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))

from collection_lock import (  # noqa: E402
    CaptureComplete,
    CaptureRejected,
    CaptureStore,
    CollectionLock,
)
from tenant_identity import (  # noqa: E402
    SUPPRESSION_CHANNEL_OPT_OUT,
    SUPPRESSION_GLOBAL_STOP,
    SUPPRESSION_NONE,
    TenantIdentity,
    VerificationError,
)

# ── vocabulary ──────────────────────────────────────────────────────────────

SCOPE_GLOBAL = "global"
SCOPE_CHANNEL = "channel"
SCOPE_SEQUENCE = "sequence"
SCOPE_TOPIC = "topic"
SCOPE_OFFER = "offer"
SCOPE_CAMPAIGN = "campaign"

SCOPES = (SCOPE_GLOBAL, SCOPE_CHANNEL, SCOPE_SEQUENCE, SCOPE_TOPIC,
          SCOPE_OFFER, SCOPE_CAMPAIGN)
VALUE_SCOPES = (SCOPE_CHANNEL, SCOPE_SEQUENCE, SCOPE_TOPIC, SCOPE_OFFER,
                SCOPE_CAMPAIGN)

DECISION_REFUSE = "refuse"
DECISION_GRANT = "grant"
DECISIONS = (DECISION_REFUSE, DECISION_GRANT)

REASON_GLOBAL = "consent:global_stop"
REASON_LEGACY_GLOBAL = "consent:global_stop_recorded_in_identity"
REASON_CHANNEL = "consent:channel_opt_out"
REASON_CHANNEL_UNRESOLVED = "consent:channel_unresolved"
REASON_LEGACY_CHANNEL = "consent:channel_opt_out_recorded_in_identity"
REASON_SEQUENCE = "consent:sequence_refusal"
REASON_SEQUENCE_UNRESOLVED = "consent:sequence_unresolved"
REASON_HUMAN = "consent:human_owned"
REASON_FIELD = "consent:field_refusal"

# Reported verbatim in every verdict's evidence.
PRECEDENCE = "global>channel>sequence>human>field"

FENCE_ACTIVE = "human"
FENCE_RELEASED = "released"

SCHEMA = """
CREATE TABLE IF NOT EXISTS consent_decisions (
    tenant_id            TEXT NOT NULL,
    canonical_contact_id TEXT NOT NULL,
    seq                  INTEGER NOT NULL,
    decision             TEXT NOT NULL,
    scope_kind           TEXT NOT NULL,
    scope_value          TEXT NOT NULL DEFAULT '',
    reason               TEXT NOT NULL DEFAULT '',
    actor                TEXT NOT NULL DEFAULT '',
    capture_id           TEXT,
    step_index           INTEGER,
    recorded_at          REAL NOT NULL,
    PRIMARY KEY (tenant_id, canonical_contact_id, seq)
);

CREATE INDEX IF NOT EXISTS consent_by_scope
    ON consent_decisions
    (tenant_id, canonical_contact_id, scope_kind, scope_value, seq);

-- One decision per capture step: a replay after a crash is a no-op, never a
-- second decision.
CREATE UNIQUE INDEX IF NOT EXISTS consent_capture_step
    ON consent_decisions
    (tenant_id, canonical_contact_id, capture_id, step_index)
    WHERE capture_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS consent_human_fence (
    tenant_id            TEXT NOT NULL,
    canonical_contact_id TEXT NOT NULL,
    state                TEXT NOT NULL DEFAULT 'released',
    actor                TEXT NOT NULL DEFAULT '',
    reason               TEXT NOT NULL DEFAULT '',
    revision             INTEGER NOT NULL DEFAULT 0,
    updated_at           REAL NOT NULL,
    PRIMARY KEY (tenant_id, canonical_contact_id)
);

CREATE TABLE IF NOT EXISTS consent_fence_events (
    tenant_id            TEXT NOT NULL,
    canonical_contact_id TEXT NOT NULL,
    seq                  INTEGER NOT NULL,
    action               TEXT NOT NULL,
    actor                TEXT NOT NULL DEFAULT '',
    reason               TEXT NOT NULL DEFAULT '',
    at                   REAL NOT NULL,
    PRIMARY KEY (tenant_id, canonical_contact_id, seq)
);
"""


class ConsentError(ValueError):
    """Bad consent input or an illegal transition. Always fail closed."""


def _id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConsentError(f"bad_input: {name} must be a non-empty string")
    return value.strip()


def _norm(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _ts(now: Optional[float]) -> float:
    return time.time() if now is None else float(now)


class ConsentStore:
    """Scoped consent decisions and the human-ownership fence, one contact."""

    def __init__(self, identity: TenantIdentity) -> None:
        if not isinstance(identity, TenantIdentity):
            raise TypeError("ConsentStore requires a TenantIdentity")
        self.identity = identity
        self.db_path = identity.db_path
        self.init_schema()

    def init_schema(self) -> None:
        conn = self.identity.connection()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
            conn.executescript(SCHEMA)
        finally:
            conn.close()

    # ── recording decisions ────────────────────────────────────────────────

    def record(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        *,
        decision: str,
        scope_kind: str,
        scope_value: Optional[str] = None,
        reason: str = "",
        actor: str = "",
        capture_id: Optional[str] = None,
        step_index: Optional[int] = None,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Append one refusal or grant. Latest decision wins per exact scope."""
        tenant_id = _id(tenant_id, "tenant_id")
        canonical_contact_id = _id(canonical_contact_id, "canonical_contact_id")
        if decision not in DECISIONS:
            raise ConsentError(f"bad_input: decision {decision!r} not in {DECISIONS}")
        if scope_kind not in SCOPES:
            raise ConsentError(f"bad_input: scope_kind {scope_kind!r} not in {SCOPES}")
        if scope_kind == SCOPE_GLOBAL:
            if scope_value not in (None, ""):
                raise ConsentError("bad_input: a global decision takes no scope value")
            value = ""
        else:
            value = _norm(_id(scope_value, "scope_value"))
        if (capture_id is None) != (step_index is None):
            raise ConsentError(
                "bad_input: capture_id and step_index are both required or both absent")
        if step_index is not None and (not isinstance(step_index, int) or step_index < 0):
            raise ConsentError("bad_input: step_index must be a non-negative integer")

        ts = _ts(now)
        self.identity.verify(tenant_id, canonical_contact_id)
        with self.identity.write_transaction() as conn:
            if decision == DECISION_GRANT:
                latest = conn.execute(
                    "SELECT decision FROM consent_decisions WHERE tenant_id=?"
                    " AND canonical_contact_id=? AND scope_kind=?"
                    " AND scope_value=? ORDER BY seq DESC LIMIT 1",
                    (tenant_id, canonical_contact_id, scope_kind, value),
                ).fetchone()
                if latest is not None and latest["decision"] == DECISION_REFUSE:
                    # Re-entry is an act of authority, not a timeout. Without a
                    # named human and a stated reason there is nothing to audit
                    # and nothing that distinguishes a deliberate release from
                    # a bug that wrote the wrong decision.
                    if not (actor or "").strip() or not (reason or "").strip():
                        raise ConsentError(
                            "reentry_requires_authority: lifting a refusal at"
                            " %s=%r requires a recorded actor and reason"
                            % (scope_kind, value))
            if capture_id is not None:
                existing = conn.execute(
                    "SELECT * FROM consent_decisions WHERE tenant_id = ?"
                    " AND canonical_contact_id = ? AND capture_id = ?"
                    " AND step_index = ?",
                    (tenant_id, canonical_contact_id, capture_id, step_index),
                ).fetchone()
                if existing is not None:
                    # Replay after a crash between decision and cursor move.
                    return dict(existing)
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM consent_decisions"
                " WHERE tenant_id = ? AND canonical_contact_id = ?",
                (tenant_id, canonical_contact_id),
            ).fetchone()["n"]
            conn.execute(
                "INSERT INTO consent_decisions (tenant_id, canonical_contact_id,"
                " seq, decision, scope_kind, scope_value, reason, actor,"
                " capture_id, step_index, recorded_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (tenant_id, canonical_contact_id, int(seq), decision, scope_kind,
                 value, reason or "", actor or "", capture_id, step_index, ts),
            )
            row = conn.execute(
                "SELECT * FROM consent_decisions WHERE tenant_id = ?"
                " AND canonical_contact_id = ? AND seq = ?",
                (tenant_id, canonical_contact_id, int(seq)),
            ).fetchone()
            return dict(row)

    def refuse(self, tenant_id: str, canonical_contact_id: str, *,
               scope_kind: str, scope_value: Optional[str] = None,
               reason: str = "", actor: str = "",
               now: Optional[float] = None) -> Dict[str, Any]:
        return self.record(tenant_id, canonical_contact_id,
                           decision=DECISION_REFUSE, scope_kind=scope_kind,
                           scope_value=scope_value, reason=reason, actor=actor,
                           now=now)

    def grant(self, tenant_id: str, canonical_contact_id: str, *,
              scope_kind: str, scope_value: Optional[str] = None,
              reason: str = "", actor: str = "",
              now: Optional[float] = None) -> Dict[str, Any]:
        return self.record(tenant_id, canonical_contact_id,
                           decision=DECISION_GRANT, scope_kind=scope_kind,
                           scope_value=scope_value, reason=reason, actor=actor,
                           now=now)

    def global_stop(self, tenant_id: str, canonical_contact_id: str, *,
                    reason: str = "", actor: str = "",
                    now: Optional[float] = None) -> Dict[str, Any]:
        """The person said stop. Suppresses every channel, immediately."""
        return self.refuse(tenant_id, canonical_contact_id,
                           scope_kind=SCOPE_GLOBAL, reason=reason or "global_stop",
                           actor=actor, now=now)

    def lift_global_stop(self, tenant_id: str, canonical_contact_id: str, *,
                         reason: str = "", actor: str = "",
                         now: Optional[float] = None) -> Dict[str, Any]:
        """An explicit global grant. This is the ONLY way past a global stop."""
        return self.grant(tenant_id, canonical_contact_id,
                          scope_kind=SCOPE_GLOBAL,
                          reason=reason or "explicit_global_grant", actor=actor,
                          now=now)

    # ── human ownership fence ──────────────────────────────────────────────

    def human_takeover(self, tenant_id: str, canonical_contact_id: str, *,
                       actor: str, reason: str = "",
                       now: Optional[float] = None) -> Dict[str, Any]:
        """A human took the conversation: the bot stops until released."""
        actor = _id(actor, "actor")
        tenant_id = _id(tenant_id, "tenant_id")
        canonical_contact_id = _id(canonical_contact_id, "canonical_contact_id")
        ts = _ts(now)
        self.identity.verify(tenant_id, canonical_contact_id)
        with self.identity.write_transaction() as conn:
            conn.execute(
                "INSERT INTO consent_human_fence (tenant_id, canonical_contact_id,"
                " state, actor, reason, revision, updated_at)"
                " VALUES (?,?,?,?,?,1,?)"
                " ON CONFLICT(tenant_id, canonical_contact_id) DO UPDATE SET"
                " state=excluded.state, actor=excluded.actor,"
                " reason=excluded.reason,"
                " revision=consent_human_fence.revision+1,"
                " updated_at=excluded.updated_at",
                (tenant_id, canonical_contact_id, FENCE_ACTIVE, actor,
                 reason or "human_takeover", ts),
            )
            self._fence_event(conn, tenant_id, canonical_contact_id, "takeover",
                              actor, reason, ts)
            return self._fence_locked(conn, tenant_id, canonical_contact_id)

    def human_release(self, tenant_id: str, canonical_contact_id: str, *,
                      actor: str, reason: str = "",
                      now: Optional[float] = None) -> Dict[str, Any]:
        """Explicit release only. A grant never releases the fence."""
        actor = _id(actor, "actor")
        tenant_id = _id(tenant_id, "tenant_id")
        canonical_contact_id = _id(canonical_contact_id, "canonical_contact_id")
        ts = _ts(now)
        self.identity.verify(tenant_id, canonical_contact_id)
        with self.identity.write_transaction() as conn:
            current = self._fence_locked(conn, tenant_id, canonical_contact_id)
            if not current["active"]:
                raise ConsentError(
                    "illegal_transition: no active human fence to release")
            conn.execute(
                "UPDATE consent_human_fence SET state=?, actor=?, reason=?,"
                " revision=revision+1, updated_at=?"
                " WHERE tenant_id=? AND canonical_contact_id=?",
                (FENCE_RELEASED, actor, reason or "explicit_release", ts,
                 tenant_id, canonical_contact_id),
            )
            self._fence_event(conn, tenant_id, canonical_contact_id, "release",
                              actor, reason, ts)
            return self._fence_locked(conn, tenant_id, canonical_contact_id)

    def human_fence(self, tenant_id: str, canonical_contact_id: str) -> Dict[str, Any]:
        with self.identity.read_transaction() as conn:
            return self._fence_locked(conn, tenant_id, canonical_contact_id)

    @staticmethod
    def _fence_locked(conn: sqlite3.Connection, tenant_id: str,
                      canonical_contact_id: str) -> Dict[str, Any]:
        row = conn.execute(
            "SELECT state, actor, reason, revision, updated_at"
            " FROM consent_human_fence WHERE tenant_id=? AND canonical_contact_id=?",
            (tenant_id, canonical_contact_id),
        ).fetchone()
        if row is None:
            return {"active": False, "state": FENCE_RELEASED, "actor": "",
                    "reason": "", "revision": 0, "updated_at": None}
        data = dict(row)
        data["active"] = data["state"] == FENCE_ACTIVE
        return data

    @staticmethod
    def _fence_event(conn: sqlite3.Connection, tenant_id: str,
                     canonical_contact_id: str, action: str, actor: str,
                     reason: str, ts: float) -> None:
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM consent_fence_events"
            " WHERE tenant_id=? AND canonical_contact_id=?",
            (tenant_id, canonical_contact_id),
        ).fetchone()["n"]
        conn.execute(
            "INSERT INTO consent_fence_events (tenant_id, canonical_contact_id,"
            " seq, action, actor, reason, at) VALUES (?,?,?,?,?,?,?)",
            (tenant_id, canonical_contact_id, int(seq), action, actor or "",
             reason or "", ts),
        )

    # ── reading state ──────────────────────────────────────────────────────

    def active_refusals(self, tenant_id: str,
                        canonical_contact_id: str) -> List[Dict[str, Any]]:
        """Refusals whose scope has no later grant. One row per exact scope."""
        with self.identity.read_transaction() as conn:
            rows = conn.execute(
                "SELECT d.* FROM consent_decisions d"
                " JOIN (SELECT scope_kind, scope_value, MAX(seq) AS mseq"
                "       FROM consent_decisions"
                "       WHERE tenant_id=? AND canonical_contact_id=?"
                "       GROUP BY scope_kind, scope_value) m"
                "  ON d.scope_kind=m.scope_kind AND d.scope_value=m.scope_value"
                " AND d.seq=m.mseq AND d.tenant_id=? AND d.canonical_contact_id=?",
                (tenant_id, canonical_contact_id,
                 tenant_id, canonical_contact_id),
            ).fetchall()
        return [dict(r) for r in rows if r["decision"] == DECISION_REFUSE]

    def decisions(self, tenant_id: str,
                  canonical_contact_id: str) -> List[Dict[str, Any]]:
        with self.identity.read_transaction() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM consent_decisions WHERE tenant_id=?"
                " AND canonical_contact_id=? ORDER BY seq",
                (tenant_id, canonical_contact_id)).fetchall()]

    def fence_events(self, tenant_id: str,
                     canonical_contact_id: str) -> List[Dict[str, Any]]:
        with self.identity.read_transaction() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM consent_fence_events WHERE tenant_id=?"
                " AND canonical_contact_id=? ORDER BY seq",
                (tenant_id, canonical_contact_id)).fetchall()]

    def legacy_suppression(self, tenant_id: str,
                           canonical_contact_id: str) -> str:
        """The contacts.suppression column owned by tenant_identity (read-only)."""
        row = self.identity.contact(tenant_id, canonical_contact_id)
        if row is None:
            return SUPPRESSION_NONE
        return row.get("suppression") or SUPPRESSION_NONE

    # ── the decision ───────────────────────────────────────────────────────

    def decide(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        *,
        channel: Optional[str] = None,
        sequence: Optional[str] = None,
        topic: Optional[str] = None,
        offer: Optional[str] = None,
        campaign: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Section 7 precedence. Returns {"allowed", "reason", "blocking"}.

        Missing channel is NOT treated as "some other channel": an existing
        channel opt-out blocks with channel_unresolved. A sequence refusal is
        treated the same way - a send that cannot name its sequence cannot
        prove it is a different one, so it blocks. Missing topic/offer/campaign
        means the send carries nothing of that kind, so a refusal for that kind
        cannot match it.
        """
        tenant_id = _id(tenant_id, "tenant_id")
        canonical_contact_id = _id(canonical_contact_id, "canonical_contact_id")
        self.identity.verify(tenant_id, canonical_contact_id)
        refusals = self.active_refusals(tenant_id, canonical_contact_id)
        by_scope = {(r["scope_kind"], r["scope_value"]): r for r in refusals}
        channel_key = _norm(channel) if channel else None
        sequence_key = _norm(sequence) if sequence else None
        fence = self.human_fence(tenant_id, canonical_contact_id)
        legacy = self.legacy_suppression(tenant_id, canonical_contact_id)

        def blocked(reason: str, blocking: Dict[str, Any],
                    evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            return {
                "allowed": False,
                "reason": reason,
                "blocking": blocking,
                "evidence": {
                    "precedence": PRECEDENCE,
                    "channel": channel_key,
                    "sequence": sequence_key,
                    "scope": blocking.get("scope_kind"),
                    "scope_value": blocking.get("scope_value", ""),
                    **(evidence or {}),
                },
            }

        # 1. global stop - recorded decision first, then the identity column.
        hit = by_scope.get((SCOPE_GLOBAL, ""))
        if hit is not None:
            return blocked(REASON_GLOBAL, hit)
        if legacy == SUPPRESSION_GLOBAL_STOP:
            return blocked(REASON_LEGACY_GLOBAL,
                           {"scope_kind": SCOPE_GLOBAL, "scope_value": "",
                            "source": "contacts.suppression"},
                           {"legacy_suppression": legacy})

        # 2. channel opt-out - only that channel; unresolved channel blocks.
        if channel_key is not None:
            hit = by_scope.get((SCOPE_CHANNEL, channel_key))
            if hit is not None:
                return blocked(REASON_CHANNEL, hit)
        else:
            chans = [r for r in refusals if r["scope_kind"] == SCOPE_CHANNEL]
            if chans:
                return blocked(
                    REASON_CHANNEL_UNRESOLVED,
                    {"scope_kind": SCOPE_CHANNEL,
                     "scope_value": chans[0]["scope_value"]},
                    {"unknown_scope_is_not_permission": True})
        if legacy == SUPPRESSION_CHANNEL_OPT_OUT:
            # The column records no channel, so it cannot be narrowed.
            return blocked(REASON_LEGACY_CHANNEL,
                           {"scope_kind": SCOPE_CHANNEL, "scope_value": "",
                            "source": "contacts.suppression"},
                           {"legacy_suppression": legacy,
                            "unknown_scope_is_not_permission": True})

        # 3. sequence refusal - only that sequence; an unnamed sequence blocks.
        if sequence_key is not None:
            hit = by_scope.get((SCOPE_SEQUENCE, sequence_key))
            if hit is not None:
                return blocked(REASON_SEQUENCE, hit)
        else:
            seqs = [r for r in refusals if r["scope_kind"] == SCOPE_SEQUENCE]
            if seqs:
                return blocked(
                    REASON_SEQUENCE_UNRESOLVED,
                    {"scope_kind": SCOPE_SEQUENCE,
                     "scope_value": seqs[0]["scope_value"]},
                    {"unknown_scope_is_not_permission": True})

        # 4. human ownership fences the bot.
        if fence["active"]:
            return blocked(REASON_HUMAN,
                           {"scope_kind": "human_fence",
                            "scope_value": fence["actor"],
                            "revision": fence["revision"]},
                           {"human_fence": fence})

        # 5. field refusal - that ask/topic/offer/campaign only.
        for kind, value in ((SCOPE_TOPIC, topic), (SCOPE_OFFER, offer),
                            (SCOPE_CAMPAIGN, campaign)):
            if value is None:
                continue
            hit = by_scope.get((kind, _norm(value)))
            if hit is not None:
                return blocked(REASON_FIELD, hit)
        return {"allowed": True, "reason": "consent:clear", "blocking": None,
                "evidence": {"channel": channel_key, "sequence": sequence_key,
                             "precedence": PRECEDENCE}}

    # ── contact merge ──────────────────────────────────────────────────────

    def fold(self, tenant_id: str, source_contact_id: str,
             target_contact_id: str, *, now: Optional[float] = None) -> int:
        """Move consent from a merged-away contact onto the surviving one.

        The stricter state survives: an active human fence on either side
        stays active, and decisions move in their original order.
        """
        tenant_id = _id(tenant_id, "tenant_id")
        source_contact_id = _id(source_contact_id, "source_contact_id")
        target_contact_id = _id(target_contact_id, "target_contact_id")
        if source_contact_id == target_contact_id:
            raise ConsentError("bad_input: a contact cannot fold onto itself")
        ts = _ts(now)
        self.identity.verify(tenant_id, source_contact_id)
        self.identity.verify(tenant_id, target_contact_id)
        with self.identity.write_transaction() as conn:
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS n FROM consent_decisions"
                " WHERE tenant_id=? AND canonical_contact_id=?",
                (tenant_id, target_contact_id)).fetchone()["n"]
            rows = conn.execute(
                "SELECT * FROM consent_decisions WHERE tenant_id=?"
                " AND canonical_contact_id=? ORDER BY seq",
                (tenant_id, source_contact_id)).fetchall()
            moved = 0
            for row in rows:
                seq += 1
                conn.execute(
                    "INSERT INTO consent_decisions (tenant_id,"
                    " canonical_contact_id, seq, decision, scope_kind,"
                    " scope_value, reason, actor, capture_id, step_index,"
                    " recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (tenant_id, target_contact_id, int(seq), row["decision"],
                     row["scope_kind"], row["scope_value"], row["reason"],
                     row["actor"], None, None, row["recorded_at"]),
                )
                moved += 1
            conn.execute(
                "DELETE FROM consent_decisions WHERE tenant_id=?"
                " AND canonical_contact_id=?",
                (tenant_id, source_contact_id))
            src_fence = self._fence_locked(conn, tenant_id, source_contact_id)
            dst_fence = self._fence_locked(conn, tenant_id, target_contact_id)
            if src_fence["active"] and not dst_fence["active"]:
                conn.execute(
                    "UPDATE consent_human_fence SET state=?, actor=?, reason=?,"
                    " revision=revision+1, updated_at=?"
                    " WHERE tenant_id=? AND canonical_contact_id=?",
                    (FENCE_ACTIVE, src_fence["actor"],
                     "carried_from_merged_contact", ts,
                     tenant_id, target_contact_id),
                )
                self._fence_event(conn, tenant_id, target_contact_id,
                                  "takeover", src_fence["actor"],
                                  "carried_from_merged_contact", ts)
            return moved


# ── the fresh gate adapter ─────────────────────────────────────────────────

def make_gate_evaluator(
    consent: ConsentStore,
    *,
    channel_of: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None,
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Build the outbound_gate evaluator. Called fresh on every dispatch.

    context keys read: the dispatch supplies "action" (the outbox row), so
    tenant/contact come from the action itself; "channel", "topic", "offer"
    and "campaign" may be supplied by the caller. channel_of(action) is an
    optional hook for callers that derive the channel elsewhere.
    """
    if not isinstance(consent, ConsentStore):
        raise TypeError("make_gate_evaluator requires a ConsentStore")

    def evaluator(ctx: Dict[str, Any]) -> Dict[str, Any]:
        action = ctx.get("action") or {}
        tenant_id = action.get("tenant_id")
        contact = action.get("canonical_contact_id")
        if not contact:
            # public_placement: no canonical contact, no person to refuse.
            return {"verdict": "ALLOW",
                    "evidence": {"consent": "no_person", "scope": action.get("scope")}}
        channel = ctx.get("channel")
        if channel is None and channel_of is not None:
            channel = channel_of(action)
        decision = consent.decide(
            tenant_id, contact, channel=channel, sequence=ctx.get("sequence"),
            topic=ctx.get("topic"), offer=ctx.get("offer"),
            campaign=ctx.get("campaign"))
        if decision["allowed"]:
            return {"verdict": "ALLOW", "evidence": decision["evidence"]}
        return {"verdict": "SUPPRESSED",
                "evidence": {"reason": decision["reason"],
                             **decision["evidence"],
                             "blocking": decision["blocking"]},
                "checked_at": ctx.get("now")}

    # Marks the evaluator as reading durable suppression state on every call, so
    # outbound_gate.dispatch() re-runs it inside the transaction that starts the
    # send. A gate that is only consulted once, before the commit, is the defect
    # this attribute exists to prevent.
    evaluator.consent_guard = True
    return evaluator


# ── capture that resumes, never restarts ───────────────────────────────────

class ConsentCapture:
    """A consent capture whose cursor is durable, so a mid-way failure resumes.

    Steps are applied in order: the decision for step N is written once
    (unique per capture+step) and only then does the cursor move to N+1. A
    crash between those two writes replays idempotently. A rejected capture
    raises CaptureRejected on the next step and stays rejected.
    """

    def __init__(self, lock: CollectionLock,
                 consent: Optional[ConsentStore] = None) -> None:
        if not isinstance(lock, CollectionLock):
            raise TypeError("ConsentCapture requires a CollectionLock")
        self.lock = lock
        self.consent = consent or ConsentStore(lock.identity)
        self.captures = CaptureStore(lock)

    def begin(self, tenant_id: str, canonical_contact_id: str,
              collection_sequence_id: str, capture_id: str,
              steps: List[str], *, owner_id: str,
              fence: int) -> Dict[str, Any]:
        return self.captures.begin(
            tenant_id, canonical_contact_id, collection_sequence_id,
            capture_id, steps, owner_id=owner_id, fence=fence)

    def record_step(self, tenant_id: str, canonical_contact_id: str,
                    collection_sequence_id: str, capture_id: str,
                    step_index: int, *, decision: str,
                    scope_kind: str = SCOPE_CHANNEL,
                    scope_value: Optional[str] = None,
                    reason: str = "", actor: str = "",
                    owner_id: str, fence: int) -> Dict[str, Any]:
        state = self.captures.get(tenant_id, canonical_contact_id,
                                  collection_sequence_id, capture_id)
        if state is None:
            raise ConsentError(f"bad_input: unknown capture {capture_id!r}")
        if state["state"] == "rejected":
            raise CaptureRejected(
                "capture rejected: %s" % (state["rejection_reason"],))
        if state["state"] == "complete":
            raise CaptureComplete("capture already complete")
        if step_index < state["cursor"]:
            # Already applied before the interruption. Resume from the cursor;
            # never re-run or restart a completed step.
            return state
        self.consent.record(
            tenant_id, canonical_contact_id, decision=decision,
            scope_kind=scope_kind, scope_value=scope_value, reason=reason,
            actor=actor, capture_id=capture_id, step_index=step_index)
        return self.captures.advance(
            tenant_id, canonical_contact_id, collection_sequence_id,
            capture_id, step_index + 1,
            data={scope_value or scope_kind: decision},
            owner_id=owner_id, fence=fence)

    def serve(self, tenant_id: str, canonical_contact_id: str,
              collection_sequence_id: str, capture_id: str, *,
              help_text: str = "") -> Dict[str, Any]:
        """What to say for a capture that already exists. Never a restart.

        PARTIAL CAPTURE SERVES THE ORIGINAL. The text is the step recorded at
        begin(), read at the capture's own cursor, so an interrupted capture
        resumes the ask the person was already answering instead of minting a
        new one. A rejected capture serves help only: `original` is None and
        `restart_allowed` is False, so no caller can turn a rejected ask into a
        fresh offer. Nothing here writes.
        """
        state = self.captures.get(tenant_id, canonical_contact_id,
                                  collection_sequence_id, capture_id)
        if state is None:
            raise ConsentError(f"bad_input: unknown capture {capture_id!r}")
        steps = state["steps"]
        cursor = int(state["cursor"])
        base = {"capture_id": capture_id, "restart_allowed": False,
                "help": help_text or "help: say adjust, skip or stop"}
        if state["state"] == "rejected":
            return {"kind": "help", "original": None, "original_step_index": None,
                    "remaining": 0,
                    "rejection_reason": state.get("rejection_reason"),
                    **base}
        if state["state"] == "complete":
            return {"kind": "complete", "original": None,
                    "original_step_index": None, "remaining": 0, **base}
        if cursor >= len(steps):
            return {"kind": "awaiting_close", "original": None,
                    "original_step_index": None, "remaining": 0, **base}
        return {"kind": "original", "original": steps[cursor],
                "original_step_index": cursor,
                "remaining": len(steps) - cursor, **base}

    def complete(self, tenant_id: str, canonical_contact_id: str,
                 collection_sequence_id: str, capture_id: str, *,
                 owner_id: str, fence: int) -> Dict[str, Any]:
        return self.captures.complete(
            tenant_id, canonical_contact_id, collection_sequence_id,
            capture_id, owner_id=owner_id, fence=fence)

    def reject(self, tenant_id: str, canonical_contact_id: str,
               collection_sequence_id: str, capture_id: str,
               reason: str = "", *, owner_id: str, fence: int) -> Dict[str, Any]:
        return self.captures.reject(
            tenant_id, canonical_contact_id, collection_sequence_id,
            capture_id, reason, owner_id=owner_id, fence=fence)


# ── assert-based self-check (stdlib only) ──────────────────────────────────

def _selfcheck() -> int:
    import contextlib
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp(prefix="consent-selfcheck-"))
    identity = TenantIdentity(str(d / "consent.sqlite"))
    identity.register_tenant("t1")
    contact = identity.bind("t1", [("sms_number", "+15550100", True)])

    @contextlib.contextmanager
    def unlocked():
        lease = lock.acquire("t1", contact, "seq-1", "selfcheck", 5.0)
        try:
            yield lease
        finally:
            lock.release("t1", contact, "seq-1", "selfcheck", lease.fence)

    lock = CollectionLock(identity)
    consent = ConsentStore(identity)
    passed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        if not cond:
            raise AssertionError("FAIL: " + label)
        passed += 1

    ok(consent.decide("t1", contact, channel="sms")["allowed"], "clear contact allows")
    consent.refuse("t1", contact, scope_kind=SCOPE_TOPIC, scope_value="pricing")
    ok(not consent.decide("t1", contact, channel="sms", topic="pricing")["allowed"],
       "topic refusal blocks that topic")
    ok(consent.decide("t1", contact, channel="sms", topic="onboarding")["allowed"],
       "topic refusal does not block another topic")
    consent.grant("t1", contact, scope_kind=SCOPE_TOPIC, scope_value="pricing",
                  actor="jill", reason="customer asked about pricing again")
    ok(consent.decide("t1", contact, channel="sms", topic="pricing")["allowed"],
       "a grant lifts its own scope")

    consent.refuse("t1", contact, scope_kind=SCOPE_CHANNEL, scope_value="sms")
    ok(not consent.decide("t1", contact, channel="sms")["allowed"], "channel blocked")
    ok(consent.decide("t1", contact, channel="email")["allowed"],
       "channel opt-out does not block another channel")
    ok(not consent.decide("t1", contact)["allowed"],
       "unknown channel is not broader permission")

    consent.global_stop("t1", contact)
    ok(not consent.decide("t1", contact, channel="email", topic="x")["allowed"],
       "global stop blocks every channel")
    consent.grant("t1", contact, scope_kind=SCOPE_TOPIC, scope_value="x")
    ok(not consent.decide("t1", contact, channel="email", topic="x")["allowed"],
       "a narrow grant never lifts a global stop")
    consent.lift_global_stop("t1", contact, actor="jill",
                             reason="customer asked to resume")

    consent.human_takeover("t1", contact, actor="jill")
    ok(not consent.decide("t1", contact, channel="email")["allowed"],
       "human fence blocks sends")
    consent.grant("t1", contact, scope_kind=SCOPE_GLOBAL)
    ok(not consent.decide("t1", contact, channel="email")["allowed"],
       "a grant does not release a human fence")
    consent.human_release("t1", contact, actor="jill")
    ok(consent.decide("t1", contact, channel="email")["allowed"],
       "explicit release re-enables")

    cap = ConsentCapture(lock, consent)
    with unlocked() as lease:
        cap.begin("t1", contact, "seq-1", "cap-1", ["sms", "email", "topic"],
                  owner_id="selfcheck", fence=lease.fence)
        cap.record_step("t1", contact, "seq-1", "cap-1", 0,
                        decision=DECISION_REFUSE, scope_value="sms",
                        owner_id="selfcheck", fence=lease.fence)
        state = cap.record_step("t1", contact, "seq-1", "cap-1", 0,
                                decision=DECISION_REFUSE, scope_value="sms",
                                owner_id="selfcheck", fence=lease.fence)
        ok(state["cursor"] == 1, "replayed step does not move the cursor twice")
        cap.record_step("t1", contact, "seq-1", "cap-1", 1,
                        decision=DECISION_GRANT, scope_value="email",
                        owner_id="selfcheck", fence=lease.fence)
        cap.record_step("t1", contact, "seq-1", "cap-1", 2,
                        decision=DECISION_REFUSE, scope_value="pricing",
                        owner_id="selfcheck", fence=lease.fence)
        done = cap.complete("t1", contact, "seq-1", "cap-1",
                            owner_id="selfcheck", fence=lease.fence)
    ok(done["state"] == "complete" and done["cursor"] == 3,
       "capture completes after every step")
    steps = [r["step_index"] for r in consent.decisions("t1", contact)
             if r["capture_id"] == "cap-1"]
    ok(sorted(steps) == [0, 1, 2], "one decision per step, no duplicates")

    print(f"OK {passed} PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selfcheck())
