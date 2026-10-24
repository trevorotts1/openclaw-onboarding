#!/usr/bin/env python3
"""Tenant and canonical contact identity for Skill 38 (DATA-CONTRACTS 1).

One person on two channels resolves to ONE canonical_contact_id inside a
tenant. The same identifiers in a different tenant never resolve together.

Enforcement lives here and in the SQLite keys, not in a path convention:

  * every lookup is keyed by tenant_id first;
  * a canonical id is derived from tenant_id plus the root verified
    identifier, so two tenants cannot mint the same identity from the same
    email or phone;
  * a verified identifier in tenant B is a different row from the same value
    in tenant A, so no query can join across tenants;
  * an identity root is an explicit allowlist of person-unique kinds
    (IDENTITY_ROOT_TYPES); anything placement-, ad-, campaign- or
    thread-scoped is a CHANNEL_REFERENCE attribute and is structurally unable
    to carry or merge a canonical contact, whatever the provenance argument
    says (DATA-CONTRACTS 2);
  * a public placement never carries a canonical contact (DATA-CONTRACTS 2).

Contract schemas under schemas/ are owned by T-08. They were not present at
this base commit, so this module implements the contract text directly; the
dependency is recorded in the T-11 BUILD.md.

Python 3 standard library only.
"""

import contextlib
import hashlib
import re
import sqlite3
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROVENANCE_PERSON_DIRECTED = "person_directed"
PROVENANCE_PUBLIC_PLACEMENT = "public_placement"

SUPPRESSION_NONE = "none"
SUPPRESSION_CHANNEL_OPT_OUT = "channel_opt_out"
SUPPRESSION_GLOBAL_STOP = "global_stop"
SUPPRESSION_RANK = {
    SUPPRESSION_NONE: 0,
    SUPPRESSION_CHANNEL_OPT_OUT: 1,
    SUPPRESSION_GLOBAL_STOP: 2,
}

CHANNEL_IDENTIFIER_TYPES = {
    "facebook": "fb_psid",
    "fb": "fb_psid",
    "messenger": "fb_psid",
    "instagram": "ig_psid",
    "ig": "ig_psid",
    "sms": "sms_number",
    "email": "email",
    "phone": "phone",
}

# Identity roots are an explicit allowlist of PERSON-UNIQUE identifier kinds.
# Anything scoped to a placement, ad, campaign, page or conversation/thread
# names something that many people share, so it can never be an identity root
# (DATA-CONTRACTS 2). Unknown kinds are refused outright rather than guessed.
IDENTITY_ROOT_TYPES = frozenset(
    {
        "fb_psid",
        "ig_psid",
        "sms_number",
        "email",
        "phone",
        "login_id",
    }
)

CHANNEL_REFERENCE_TYPES = frozenset(
    {
        "conversation_id",
        "thread_id",
        "thread_ref",
        "dm_id",
        "placement_id",
        "ad_id",
        "adset_id",
        "campaign_id",
        "page_id",
        "post_id",
        "comment_id",
        "message_id",
    }
)

IDENTITY_ROOT = "identity_root"
CHANNEL_REFERENCE = "channel_reference"

_IDENT_TYPE_RE = re.compile(r"^[a-z0-9_]{1,32}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id  TEXT PRIMARY KEY,
    label      TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    tenant_id            TEXT NOT NULL,
    canonical_contact_id TEXT NOT NULL,
    provenance           TEXT NOT NULL,
    suppression          TEXT NOT NULL DEFAULT 'none',
    unknown_sends        INTEGER NOT NULL DEFAULT 0,
    reminder_total       INTEGER NOT NULL DEFAULT 0,
    created_at           REAL NOT NULL,
    PRIMARY KEY (tenant_id, canonical_contact_id)
);

CREATE TABLE IF NOT EXISTS identifiers (
    tenant_id            TEXT NOT NULL,
    ident_type           TEXT NOT NULL,
    ident_value          TEXT NOT NULL,
    canonical_contact_id TEXT NOT NULL,
    verified             INTEGER NOT NULL DEFAULT 0,
    source               TEXT NOT NULL DEFAULT '',
    created_at           REAL NOT NULL,
    PRIMARY KEY (tenant_id, ident_type, ident_value)
);

CREATE INDEX IF NOT EXISTS identifiers_by_contact
    ON identifiers (tenant_id, canonical_contact_id);

CREATE TABLE IF NOT EXISTS contact_merges (
    tenant_id         TEXT NOT NULL,
    source_contact_id TEXT NOT NULL,
    target_contact_id TEXT NOT NULL,
    reason            TEXT NOT NULL DEFAULT '',
    merged_at         REAL NOT NULL
);

-- Channel references are attributes, not identity. No uniqueness on
-- (ref_type, ref_value): two different people may share one thread id, and
-- that must never fuse them (DATA-CONTRACTS 2).
CREATE TABLE IF NOT EXISTS contact_channel_refs (
    tenant_id            TEXT NOT NULL,
    canonical_contact_id TEXT NOT NULL,
    ref_type             TEXT NOT NULL,
    ref_value            TEXT NOT NULL,
    source               TEXT NOT NULL DEFAULT '',
    created_at           REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS channel_refs_by_contact
    ON contact_channel_refs (tenant_id, canonical_contact_id);

CREATE INDEX IF NOT EXISTS channel_refs_by_value
    ON contact_channel_refs (tenant_id, ref_type, ref_value);
"""


class TenantError(Exception):
    """Base error for tenant/contact identity."""


class UnknownTenant(TenantError):
    """The tenant is missing or was never registered."""


class UnknownChannel(TenantError):
    """The channel name has no identifier type mapping."""


class ContactError(TenantError):
    """Base error for contact identity operations."""


class VerificationError(ContactError):
    """A tenant/contact reference did not satisfy the contract."""


def classify_identifier(ident_type: str) -> str:
    """Return IDENTITY_ROOT or CHANNEL_REFERENCE; refuse everything else.

    The classification is structural: it depends only on the identifier kind,
    never on what a caller says about provenance. A placement-, ad-, campaign-
    or thread-scoped kind is a CHANNEL_REFERENCE and can never become an
    identity root.
    """
    if not isinstance(ident_type, str) or not ident_type.strip():
        raise VerificationError("identifier type is required")
    kind = ident_type.strip().lower()
    if not _IDENT_TYPE_RE.match(kind):
        raise VerificationError(
            "identifier type %r is not a simple token" % (ident_type,)
        )
    if kind in IDENTITY_ROOT_TYPES:
        return IDENTITY_ROOT
    if kind in CHANNEL_REFERENCE_TYPES:
        return CHANNEL_REFERENCE
    raise VerificationError(
        "unknown identifier kind %r; only person-unique identity roots and"
        " channel references are recognised" % (ident_type,)
    )


def normalize_identifier(ident_type: str, value: str) -> Tuple[str, str]:
    """Return (type, value) normalized for a PERSON-UNIQUE identity root.

    Only email case is folded. Phone and PSID values stay exactly as the
    verified provider gave them; formatting normalization belongs to the
    provider adapter that marks the identifier verified.

    Anything placement-, ad-, campaign- or thread-scoped is refused here, so a
    public placement cannot reach a canonical contact through this function no
    matter what the provenance argument claims (DATA-CONTRACTS 2).
    """
    if classify_identifier(ident_type) != IDENTITY_ROOT:
        raise VerificationError(
            "identifier kind %r is not a person-unique identity root; a"
            " placement, ad, campaign or conversation reference never"
            " carries a canonical contact" % (ident_type,)
        )
    kind = ident_type.strip().lower()
    return kind, _normalize_value(kind, value)


def normalize_channel_ref(ref_type: str, value: str) -> Tuple[str, str]:
    """Return (type, value) for a channel reference attribute.

    A channel reference is stored against a contact but never used as an
    identity root and never used to merge two contacts.
    """
    if classify_identifier(ref_type) != CHANNEL_REFERENCE:
        raise VerificationError(
            "identifier kind %r is a person-unique identity root, not a"
            " channel reference" % (ref_type,)
        )
    kind = ref_type.strip().lower()
    return kind, _normalize_value(kind, value)


def _normalize_value(kind: str, value: Any) -> str:
    if value is None or not isinstance(value, str) or not value.strip():
        raise VerificationError("identifier value is required for type %r" % kind)
    normalized = value.strip()
    if kind == "email":
        normalized = normalized.casefold()
    return normalized


def canonical_contact_id_for(tenant_id: str, ident_type: str, value: str) -> str:
    """Deterministic, tenant-scoped canonical contact id.

    Determinism makes binding idempotent across processes. The tenant id is
    inside the hash, so the same email in two tenants yields two ids.
    """
    digest = hashlib.sha256(
        ("%s\x1f%s\x1f%s" % (tenant_id, ident_type, value)).encode("utf-8")
    ).hexdigest()
    return "cc_" + digest[:24]


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VerificationError("%s is required" % name)
    return value.strip()


class TenantIdentity:
    """Tenant-scoped contact resolution and verification."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_schema()

    # -- storage ---------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    connection = _connect

    def init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
            conn.executescript(SCHEMA)
        finally:
            conn.close()

    @contextlib.contextmanager
    def _write(self):
        """Serialized write transaction shared with the collection lock."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    @contextlib.contextmanager
    def _read(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    # Public names for the sibling collection-lock module; the same
    # transactions keep identity and lock writes serialized on one database.
    write_transaction = _write
    read_transaction = _read

    # -- tenants ---------------------------------------------------------

    def register_tenant(self, tenant_id: str, label: str = "") -> str:
        tenant_id = _require_text(tenant_id, "tenant_id")
        with self._write() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO tenants (tenant_id, label, created_at)"
                " VALUES (?, ?, ?)",
                (tenant_id, label or "", time.time()),
            )
        return tenant_id

    def require_tenant(self, tenant_id: str) -> str:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise UnknownTenant("tenant_id is required")
        tenant_id = tenant_id.strip()
        with self._read() as conn:
            row = conn.execute(
                "SELECT tenant_id FROM tenants WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
        if row is None:
            raise UnknownTenant("unknown tenant %r" % (tenant_id,))
        return tenant_id

    def is_registered(self, tenant_id: str) -> bool:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            return False
        with self._read() as conn:
            row = conn.execute(
                "SELECT 1 FROM tenants WHERE tenant_id = ?", (tenant_id.strip(),)
            ).fetchone()
        return row is not None

    # -- binding and resolution -----------------------------------------

    def bind(
        self,
        tenant_id: str,
        identifiers: Iterable[Sequence[Any]],
        provenance: str = PROVENANCE_PERSON_DIRECTED,
        source: str = "",
    ) -> str:
        """Bind identifiers to one canonical contact and return its id.

        identifiers: iterable of (ident_type, value, verified). A 2-tuple is
        accepted as verified=False. At least one verified identifier is
        required; unverified claims are stored but never reconcile contacts.
        """
        self.require_tenant(tenant_id)
        if provenance == PROVENANCE_PUBLIC_PLACEMENT:
            raise VerificationError(
                "a public placement never carries a canonical contact"
            )
        if provenance != PROVENANCE_PERSON_DIRECTED:
            raise VerificationError(
                "unsupported contact provenance %r" % (provenance,)
            )

        claims: Dict[Tuple[str, str], bool] = {}
        refs: List[Tuple[str, str]] = []
        for item in identifiers or ():
            if len(item) == 3:
                ident_type, value, verified = item
            elif len(item) == 2:
                ident_type, value = item
                verified = False
            else:
                raise VerificationError(
                    "identifier must be (type, value[, verified])"
                )
            if classify_identifier(ident_type) == CHANNEL_REFERENCE:
                # Stored as an attribute only: never an identity root and
                # never merge authority, so two people sharing one thread id
                # stay two people (DATA-CONTRACTS 2).
                refs.append(normalize_channel_ref(ident_type, value))
                continue
            key = normalize_identifier(ident_type, value)
            claims[key] = claims.get(key, False) or bool(verified)

        if not claims:
            raise VerificationError(
                "empty contact: at least one person-unique identifier is"
                " required; a channel reference alone never carries a"
                " canonical contact"
            )
        verified_claims = sorted(k for k, ok in claims.items() if ok)
        if not verified_claims:
            raise VerificationError(
                "contact has no verified identifier; reconciliation requires"
                " verification"
            )

        source = source or ""
        now = time.time()
        with self._write() as conn:
            linked: List[str] = []
            for ident_type, value in verified_claims:
                row = conn.execute(
                    "SELECT canonical_contact_id FROM identifiers"
                    " WHERE tenant_id = ? AND ident_type = ? AND ident_value = ?"
                    " AND verified = 1",
                    (tenant_id, ident_type, value),
                ).fetchone()
                if row is not None:
                    linked.append(row["canonical_contact_id"])

            linked = sorted(set(linked))
            if linked:
                contact_id = linked[0]
                for other in linked[1:]:
                    self._merge_locked(
                        conn,
                        tenant_id,
                        other,
                        contact_id,
                        "verified-identifier reconciliation",
                    )
            else:
                root_type, root_value = verified_claims[0]
                contact_id = canonical_contact_id_for(
                    tenant_id, root_type, root_value
                )
                conn.execute(
                    "INSERT OR IGNORE INTO contacts"
                    " (tenant_id, canonical_contact_id, provenance, suppression,"
                    "  unknown_sends, reminder_total, created_at)"
                    " VALUES (?, ?, ?, ?, 0, 0, ?)",
                    (
                        tenant_id,
                        contact_id,
                        provenance,
                        SUPPRESSION_NONE,
                        now,
                    ),
                )

            for (ident_type, value), verified in sorted(claims.items()):
                row = conn.execute(
                    "SELECT canonical_contact_id, verified FROM identifiers"
                    " WHERE tenant_id = ? AND ident_type = ? AND ident_value = ?",
                    (tenant_id, ident_type, value),
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO identifiers"
                        " (tenant_id, ident_type, ident_value,"
                        "  canonical_contact_id, verified, source, created_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            tenant_id,
                            ident_type,
                            value,
                            contact_id,
                            1 if verified else 0,
                            source,
                            now,
                        ),
                    )
                    continue
                if row["canonical_contact_id"] == contact_id:
                    if verified and not row["verified"]:
                        conn.execute(
                            "UPDATE identifiers SET verified = 1, source = ?"
                            " WHERE tenant_id = ? AND ident_type = ?"
                            " AND ident_value = ?",
                            (source, tenant_id, ident_type, value),
                        )
                    continue
                if verified and row["verified"]:
                    # A verified identifier proves both rows are one person.
                    self._merge_locked(
                        conn,
                        tenant_id,
                        row["canonical_contact_id"],
                        contact_id,
                        "verified-identifier reconciliation",
                    )
                elif verified:
                    # Upgrade an unverified claim; it had no merge authority.
                    conn.execute(
                        "UPDATE identifiers"
                        " SET canonical_contact_id = ?, verified = 1, source = ?"
                        " WHERE tenant_id = ? AND ident_type = ?"
                        " AND ident_value = ?",
                        (
                            contact_id,
                            source,
                            tenant_id,
                            ident_type,
                            value,
                        ),
                    )
            for ref_type, ref_value in sorted(set(refs)):
                conn.execute(
                    "INSERT INTO contact_channel_refs"
                    " (tenant_id, canonical_contact_id, ref_type, ref_value,"
                    "  source, created_at)"
                    " SELECT ?, ?, ?, ?, ?, ?"
                    " WHERE NOT EXISTS (SELECT 1 FROM contact_channel_refs"
                    "   WHERE tenant_id = ? AND canonical_contact_id = ?"
                    "   AND ref_type = ? AND ref_value = ?)",
                    (
                        tenant_id,
                        contact_id,
                        ref_type,
                        ref_value,
                        source,
                        now,
                        tenant_id,
                        contact_id,
                        ref_type,
                        ref_value,
                    ),
                )
            return contact_id

    def resolve(
        self,
        tenant_id: str,
        ident_type: str,
        value: str,
        verified_only: bool = True,
    ) -> Optional[str]:
        """Resolve an identifier inside one tenant, or None."""
        self.require_tenant(tenant_id)
        ident_type, value = normalize_identifier(ident_type, value)
        sql = (
            "SELECT canonical_contact_id FROM identifiers"
            " WHERE tenant_id = ? AND ident_type = ? AND ident_value = ?"
        )
        if verified_only:
            sql += " AND verified = 1"
        with self._read() as conn:
            row = conn.execute(sql, (tenant_id, ident_type, value)).fetchone()
        return row["canonical_contact_id"] if row is not None else None

    def resolve_channel(
        self, tenant_id: str, channel: str, channel_ref: str
    ) -> Optional[str]:
        """Resolve a channel reference (fb/ig/sms/email/phone) to a contact."""
        if not isinstance(channel, str) or not channel.strip():
            raise UnknownChannel("channel is required")
        ident_type = CHANNEL_IDENTIFIER_TYPES.get(channel.strip().lower())
        if ident_type is None:
            raise UnknownChannel("unknown channel %r" % (channel,))
        return self.resolve(tenant_id, ident_type, channel_ref)

    # -- verification ----------------------------------------------------

    def verify(self, tenant_id: str, canonical_contact_id: str) -> Dict[str, Any]:
        """Return the contact row or raise; never returns another tenant's row."""
        self.require_tenant(tenant_id)
        if (
            not isinstance(canonical_contact_id, str)
            or not canonical_contact_id.strip()
        ):
            raise VerificationError("empty contact")
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM contacts"
                " WHERE tenant_id = ? AND canonical_contact_id = ?",
                (tenant_id, canonical_contact_id.strip()),
            ).fetchone()
            if row is None:
                foreign = conn.execute(
                    "SELECT tenant_id FROM contacts"
                    " WHERE canonical_contact_id = ?",
                    (canonical_contact_id.strip(),),
                ).fetchone()
                if foreign is not None:
                    raise VerificationError(
                        "contact belongs to another tenant; cross-tenant"
                        " resolution is denied"
                    )
                raise VerificationError(
                    "unknown contact %r" % (canonical_contact_id,)
                )
        contact = dict(row)
        if contact["provenance"] == PROVENANCE_PUBLIC_PLACEMENT:
            raise VerificationError(
                "a public placement never carries a canonical contact"
            )
        return contact

    def contact(
        self, tenant_id: str, canonical_contact_id: str
    ) -> Optional[Dict[str, Any]]:
        """Tenant-scoped read; None when the id is absent or foreign."""
        self.require_tenant(tenant_id)
        if (
            not isinstance(canonical_contact_id, str)
            or not canonical_contact_id.strip()
        ):
            return None
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM contacts"
                " WHERE tenant_id = ? AND canonical_contact_id = ?",
                (tenant_id, canonical_contact_id.strip()),
            ).fetchone()
        return dict(row) if row is not None else None

    def identifiers(
        self, tenant_id: str, canonical_contact_id: str
    ) -> List[Dict[str, Any]]:
        self.require_tenant(tenant_id)
        with self._read() as conn:
            rows = conn.execute(
                "SELECT ident_type, ident_value, verified FROM identifiers"
                " WHERE tenant_id = ? AND canonical_contact_id = ?"
                " ORDER BY ident_type, ident_value",
                (tenant_id, canonical_contact_id),
            ).fetchall()
        return [dict(r) for r in rows]

    def channel_refs(
        self, tenant_id: str, canonical_contact_id: str
    ) -> List[Dict[str, Any]]:
        """Channel references recorded against one contact.

        Attributes only: the same ref_value may appear on many contacts.
        """
        self.require_tenant(tenant_id)
        with self._read() as conn:
            rows = conn.execute(
                "SELECT ref_type, ref_value FROM contact_channel_refs"
                " WHERE tenant_id = ? AND canonical_contact_id = ?"
                " ORDER BY ref_type, ref_value",
                (tenant_id, canonical_contact_id),
            ).fetchall()
        return [dict(r) for r in rows]

    def merge(
        self,
        tenant_id: str,
        source_contact_id: str,
        target_contact_id: str,
        reason: str = "",
    ) -> str:
        """Administrative merge. bind() is the verified reconciliation path.

        Preservation rules (DATA-CONTRACTS 1): the stricter suppression wins,
        unknown sends and prior reminder totals are added, never dropped.
        """
        self.require_tenant(tenant_id)
        self.verify(tenant_id, source_contact_id)
        self.verify(tenant_id, target_contact_id)
        with self._write() as conn:
            return self._merge_locked(
                conn, tenant_id, source_contact_id, target_contact_id, reason
            )

    def _merge_locked(
        self,
        conn: sqlite3.Connection,
        tenant_id: str,
        source_contact_id: str,
        target_contact_id: str,
        reason: str,
    ) -> str:
        if source_contact_id == target_contact_id:
            return target_contact_id
        source = conn.execute(
            "SELECT suppression, unknown_sends, reminder_total FROM contacts"
            " WHERE tenant_id = ? AND canonical_contact_id = ?",
            (tenant_id, source_contact_id),
        ).fetchone()
        target = conn.execute(
            "SELECT suppression, unknown_sends, reminder_total FROM contacts"
            " WHERE tenant_id = ? AND canonical_contact_id = ?",
            (tenant_id, target_contact_id),
        ).fetchone()
        if source is None:
            return target_contact_id
        if target is None:
            conn.execute(
                "UPDATE contacts SET canonical_contact_id = ?"
                " WHERE tenant_id = ? AND canonical_contact_id = ?",
                (target_contact_id, tenant_id, source_contact_id),
            )
            return target_contact_id

        source_rank = SUPPRESSION_RANK.get(source["suppression"], 0)
        target_rank = SUPPRESSION_RANK.get(target["suppression"], 0)
        suppression = (
            source["suppression"] if source_rank > target_rank
            else target["suppression"]
        )
        conn.execute(
            "UPDATE contacts SET suppression = ?, unknown_sends = ?,"
            " reminder_total = ?"
            " WHERE tenant_id = ? AND canonical_contact_id = ?",
            (
                suppression,
                source["unknown_sends"] + target["unknown_sends"],
                source["reminder_total"] + target["reminder_total"],
                tenant_id,
                target_contact_id,
            ),
        )
        conn.execute(
            "UPDATE identifiers SET canonical_contact_id = ?"
            " WHERE tenant_id = ? AND canonical_contact_id = ?",
            (target_contact_id, tenant_id, source_contact_id),
        )
        conn.execute(
            "UPDATE contact_channel_refs SET canonical_contact_id = ?"
            " WHERE tenant_id = ? AND canonical_contact_id = ?",
            (target_contact_id, tenant_id, source_contact_id),
        )
        conn.execute(
            "DELETE FROM contacts WHERE tenant_id = ? AND canonical_contact_id = ?",
            (tenant_id, source_contact_id),
        )
        conn.execute(
            "INSERT INTO contact_merges"
            " (tenant_id, source_contact_id, target_contact_id, reason, merged_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                tenant_id,
                source_contact_id,
                target_contact_id,
                reason or "",
                time.time(),
            ),
        )
        return target_contact_id
