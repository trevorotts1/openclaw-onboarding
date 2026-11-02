#!/usr/bin/env python3
"""S75-X11: applied/release gate and its two record formats.

The gate refuses APPLY or RELEASE unless a genuine backup authorization for the
EXACT target exists, the backup actually taken is a targeted tar of ONLY the
files in the reviewed manifest with matching per-file SHA-256, and it refuses
RELEASE unless an independent applied-tree verification receipt exists AFTER
application and binds the applied digest.

The backup is verified as an artifact, not as a word. ``backup_mode: "targeted"``
in the authorization record is a claim; :func:`require_targeted_preservation`
checks the tar's own member list against the reviewed manifest: every changed
file present, no unchanged file present, every per-file digest equal, and no
manifest entry that would delete original work.

Nothing is implied by absence. A record that is missing, or that omits any
required field, is a refusal with a named reason -- never a default-allow. A
new HEAD or digest alone is not verification, and a git merge success is not a
release.

Hard boundary (Trevor, 2026-10-02): no backup is ever created without asking
him first. This module therefore NEVER creates, copies, archives or snapshots a
tree. It only reads records handed to it and returns a decision. The same
backup-authorization check that gates APPLY also gates backup creation:
:func:`require_backup_authorization` must pass before any caller makes a
backup, and it never makes one itself.

No owner authority is minted or simulated here. The gate validates records; it
does not write the owner authority store, and it cannot turn an absence into
consent.

Consistent with the loop's ``installed_apply`` operator decision and without
changing it: an installed copy is refused unless the operator decision says
exactly ``installed_apply is True``. The gate consumes that decision; it never
sets or flips it. A canonical or 999 copy does not require it.

Record formats (all fields required unless marked optional):

  backup authorization       schema "s75.x11.backup-authorization/v1"
    authorization_id   non-empty string, unique id of this authorization
    issuer             exactly "owner:trevor"
    channel            exactly "trevor-command"
    source             exactly "harness-user-input"
    issued_at          ISO-8601 timestamp
    expires_at         optional ISO-8601 timestamp; if present must not be past
    backup_mode        exactly "targeted"
    scope              non-empty list of target ids, must contain this target
    target             {repository, skill_root, target_id, kind, tree_digest}
                       all must equal the target being gated

  applied-tree verification  schema "s75.x11.applied-tree-verification/v1"
    receipt_id         non-empty string
    target             {repository, skill_root, target_id, kind, tree_digest}
    applier            {identity}
    verifier           {identity, independent: true}
    applied_digest     64-hex sha256, must equal target.tree_digest
    applied_at         ISO-8601 timestamp
    verified_at        ISO-8601 timestamp, must be >= applied_at
    checks             non-empty list of {name, status}; every status "PASS"
    result             exactly "PASS"

  targeted preservation      schema "s75.x11.targeted-preservation/v1"
    preservation_id    non-empty string
    target             {repository, skill_root, target_id, kind, tree_digest}
    backup_mode        exactly "targeted"
    archive_sha256     64-hex sha256 of the tar actually created
    members            non-empty list of {path, sha256}: the tar's own entries
    created_at         ISO-8601 timestamp

  reviewed manifest          schema "s75.x11.reviewed-manifest/v1"
    manifest_id        non-empty string
    sha256             64-hex sha256 of the reviewed manifest file
    files              non-empty list of {path, sha256, action}; action is
                       "modify" or "add".  Any other action, including
                       "delete", is ORIGINAL_WORK_DELETED.

  temporary-backup deletion  {preservation_id, deleted_at} -- allowed only for
                             the authorized temporary backup named by
                             preservation_id, only AFTER independent applied-tree
                             verification, and never for original work.

  operator decision (owned elsewhere, consumed unchanged)
    installed_apply    boolean

Stdlib only. Pure reads: no filesystem, process, network or subprocess.
"""
import datetime as _dt

BACKUP_AUTH_SCHEMA = "s75.x11.backup-authorization/v1"
APPLIED_VERIFICATION_SCHEMA = "s75.x11.applied-tree-verification/v1"
TARGETED_PRESERVATION_SCHEMA = "s75.x11.targeted-preservation/v1"
REVIEWED_MANIFEST_SCHEMA = "s75.x11.reviewed-manifest/v1"

# Changing a file is allowed. Removing the original is not.
PRESERVED_ACTIONS = ("modify", "add")

OWNER_ISSUER = "owner:trevor"
OWNER_CHANNEL = "trevor-command"
OWNER_SOURCE = "harness-user-input"
BACKUP_MODE = "targeted"
TARGET_KINDS = ("canonical", "installed", "999")

_HEX64 = frozenset("0123456789abcdef")


class GateRefusal(Exception):
    """A named refusal. Absence and malformation are refusals, not defaults."""

    def __init__(self, code, detail):
        super().__init__("%s: %s" % (code, detail))
        self.code = code
        self.detail = detail


class Target(object):
    """The exact copy being applied or released. Identity, not a filename."""

    __slots__ = ("repository", "skill_root", "target_id", "kind", "tree_digest")

    def __init__(self, repository, skill_root, target_id, kind, tree_digest):
        for name, value in (("repository", repository),
                            ("skill_root", skill_root),
                            ("target_id", target_id)):
            if not _nonempty(value):
                raise GateRefusal("MALFORMED_TARGET", "%s must be a non-empty string" % name)
        if kind not in TARGET_KINDS:
            raise GateRefusal("MALFORMED_TARGET",
                              "kind must be one of %s" % (", ".join(TARGET_KINDS),))
        if not _is_sha256(tree_digest):
            raise GateRefusal("MALFORMED_TARGET", "tree_digest must be 64-hex sha256")
        self.repository = repository
        self.skill_root = skill_root
        self.target_id = target_id
        self.kind = kind
        self.tree_digest = tree_digest

    def as_dict(self):
        return {"repository": self.repository, "skill_root": self.skill_root,
                "target_id": self.target_id, "kind": self.kind,
                "tree_digest": self.tree_digest}


def _nonempty(value):
    return isinstance(value, str) and value.strip() != ""


def _is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(c in _HEX64 for c in value)


def _field(record, key, where):
    if not isinstance(record, dict):
        raise GateRefusal("MALFORMED_RECORD", "%s is not an object" % where)
    if key not in record:
        raise GateRefusal("MALFORMED_RECORD",
                          "%s is missing required field %r" % (where, key))
    return record[key]


def _text(record, key, where):
    value = _field(record, key, where)
    if not _nonempty(value):
        raise GateRefusal("MALFORMED_RECORD",
                          "%s field %r must be a non-empty string" % (where, key))
    return value


def _timestamp(record, key, where):
    raw = _field(record, key, where)
    if not _nonempty(raw):
        raise GateRefusal("MALFORMED_RECORD",
                          "%s field %r must be an ISO-8601 string" % (where, key))
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        stamp = _dt.datetime.fromisoformat(text)
    except ValueError:
        raise GateRefusal("MALFORMED_RECORD",
                          "%s field %r is not an ISO-8601 timestamp" % (where, key))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=_dt.timezone.utc)
    return stamp


def _record_target(record, where):
    raw = _field(record, "target", where)
    if not isinstance(raw, dict):
        raise GateRefusal("MALFORMED_RECORD", "%s target is not an object" % where)
    out = {}
    for key in ("repository", "skill_root", "target_id", "kind", "tree_digest"):
        value = _field(raw, key, where + ".target")
        if not _nonempty(value):
            raise GateRefusal("MALFORMED_RECORD",
                              "%s target field %r must be a non-empty string" % (where, key))
        out[key] = value
    return out


def _match_target(record, target, where, code):
    declared = _record_target(record, where)
    actual = target.as_dict()
    for key in ("repository", "skill_root", "target_id", "kind", "tree_digest"):
        if declared[key] != actual[key]:
            raise GateRefusal(code, "%s.target.%s %r does not match gated %r"
                              % (where, key, declared[key], actual[key]))


def require_backup_authorization(target, backup_authorization, now=None):
    """Refuse unless a genuine, target-exact backup authorization exists.

    Call this before creating ANY backup and before APPLY. It reads the record
    only; it never creates a backup. Absence is MISSING_BACKUP_AUTHORIZATION.
    """
    if backup_authorization is None:
        raise GateRefusal("MISSING_BACKUP_AUTHORIZATION",
                          "no backup authorization record supplied; absence is not permission")
    where = "backup_authorization"
    if _text(backup_authorization, "schema", where) != BACKUP_AUTH_SCHEMA:
        raise GateRefusal("MALFORMED_RECORD",
                          "backup authorization schema is not %s" % BACKUP_AUTH_SCHEMA)
    _text(backup_authorization, "authorization_id", where)
    if _text(backup_authorization, "issuer", where) != OWNER_ISSUER:
        raise GateRefusal("NOT_OWNER_ISSUED",
                          "backup authorization was not issued by the owner")
    if _text(backup_authorization, "channel", where) != OWNER_CHANNEL:
        raise GateRefusal("NOT_OWNER_ISSUED",
                          "backup authorization channel is not an owner command")
    if _text(backup_authorization, "source", where) != OWNER_SOURCE:
        raise GateRefusal("NOT_OWNER_ISSUED",
                          "backup authorization source is not owner input")
    if _text(backup_authorization, "backup_mode", where) != BACKUP_MODE:
        raise GateRefusal("MALFORMED_RECORD",
                          "backup authorization mode must be %r" % BACKUP_MODE)
    _timestamp(backup_authorization, "issued_at", where)
    if "expires_at" in backup_authorization:
        expires = _timestamp(backup_authorization, "expires_at", where)
        if now is None:
            now = _dt.datetime.now(_dt.timezone.utc)
        if expires < now:
            raise GateRefusal("BACKUP_AUTHORIZATION_EXPIRED",
                              "backup authorization expired at %s" % expires.isoformat())
    scope = _field(backup_authorization, "scope", where)
    if not isinstance(scope, list) or not scope or not all(_nonempty(x) for x in scope):
        raise GateRefusal("MALFORMED_RECORD",
                          "backup authorization scope must be a non-empty list of target ids")
    if target.target_id not in scope:
        raise GateRefusal("BACKUP_AUTHORIZATION_TARGET_MISMATCH",
                          "authorization scope does not name target %r" % target.target_id)
    _match_target(backup_authorization, target, where,
                  "BACKUP_AUTHORIZATION_TARGET_MISMATCH")
    return backup_authorization


def _require_applied_verification(target, applied_verification, now=None):
    if applied_verification is None:
        raise GateRefusal("MISSING_APPLIED_TREE_VERIFICATION",
                          "no applied-tree verification receipt supplied; a HEAD or digest alone does not verify")
    where = "applied_verification"
    if _text(applied_verification, "schema", where) != APPLIED_VERIFICATION_SCHEMA:
        raise GateRefusal("MALFORMED_RECORD",
                          "applied verification schema is not %s" % APPLIED_VERIFICATION_SCHEMA)
    _text(applied_verification, "receipt_id", where)
    _match_target(applied_verification, target, where,
                  "APPLIED_VERIFICATION_TARGET_MISMATCH")
    digest = _field(applied_verification, "applied_digest", where)
    if not _is_sha256(digest):
        raise GateRefusal("MALFORMED_RECORD",
                          "applied_digest must be 64-hex sha256")
    if digest != target.tree_digest:
        raise GateRefusal("APPLIED_VERIFICATION_DIGEST_MISMATCH",
                          "verification binds %s, target is %s" % (digest, target.tree_digest))
    applier = _field(applied_verification, "applier", where)
    verifier = _field(applied_verification, "verifier", where)
    applier_id = _text(applier, "identity", where + ".applier")
    verifier_id = _text(verifier, "identity", where + ".verifier")
    independent = _field(verifier, "independent", where + ".verifier")
    if independent is not True:
        raise GateRefusal("APPLIED_VERIFICATION_NOT_INDEPENDENT",
                          "verifier.independent is not exactly true; absence is not independence")
    if verifier_id == applier_id:
        raise GateRefusal("APPLIED_VERIFICATION_NOT_INDEPENDENT",
                          "verifier identity equals applier identity")
    applied_at = _timestamp(applied_verification, "applied_at", where)
    verified_at = _timestamp(applied_verification, "verified_at", where)
    if verified_at < applied_at:
        raise GateRefusal("APPLIED_VERIFICATION_NOT_AFTER_APPLICATION",
                          "verified_at %s precedes applied_at %s"
                          % (verified_at.isoformat(), applied_at.isoformat()))
    checks = _field(applied_verification, "checks", where)
    if not isinstance(checks, list) or not checks:
        raise GateRefusal("MALFORMED_RECORD",
                          "applied verification checks must be a non-empty list")
    for index, check in enumerate(checks):
        name = _text(check, "name", where + ".checks[%d]" % index)
        status = _text(check, "status", where + ".checks[%d]" % index)
        if status != "PASS":
            raise GateRefusal("APPLIED_VERIFICATION_CHECK_FAILED",
                              "check %r status is %r, not PASS" % (name, status))
    if _text(applied_verification, "result", where) != "PASS":
        raise GateRefusal("APPLIED_VERIFICATION_NOT_PASS",
                          "applied verification result is not PASS")
    if now is None:
        now = _dt.datetime.now(_dt.timezone.utc)
    if verified_at > now:
        raise GateRefusal("MALFORMED_RECORD",
                          "verified_at is in the future")
    return applied_verification


def _require_installed_apply(target, operator_decision):
    """Consume the operator decision unchanged; never set or flip it."""
    if target.kind != "installed":
        return None
    if not isinstance(operator_decision, dict):
        raise GateRefusal("INSTALLED_APPLY_NOT_AUTHORIZED",
                          "installed copy with no operator decision; installed_apply is not implied")
    value = operator_decision.get("installed_apply")
    if value is not True:
        raise GateRefusal("INSTALLED_APPLY_NOT_AUTHORIZED",
                          "operator decision installed_apply is %r, not true" % (value,))
    return True


def _file_entries(record, key, where):
    """Validate a {path, sha256[, action]} list into a path-keyed mapping."""
    raw = _field(record, key, where)
    if not isinstance(raw, list) or not raw:
        raise GateRefusal("MALFORMED_RECORD",
                          "%s field %r must be a non-empty list" % (where, key))
    entries = {}
    for index, item in enumerate(raw):
        at = "%s.%s[%d]" % (where, key, index)
        path = _text(item, "path", at)
        digest = _field(item, "sha256", at)
        if not _is_sha256(digest):
            raise GateRefusal("MALFORMED_RECORD", "%s sha256 must be 64-hex" % at)
        if path in entries:
            raise GateRefusal("DUPLICATE_FILE_PATH",
                              "%s names %r twice" % (where, path))
        entries[path] = digest
    return entries


def _manifest_entries(reviewed_manifest, where):
    entries = _file_entries(reviewed_manifest, "files", where)
    for item in reviewed_manifest["files"]:
        action = _field(item, "action", where + ".files")
        if action not in PRESERVED_ACTIONS:
            raise GateRefusal("ORIGINAL_WORK_DELETED",
                              "%s entry %r action is %r; original work is never deleted"
                              % (where, item["path"], action))
    return entries


def require_targeted_preservation(target, preservation, reviewed_manifest, now=None):
    """Refuse unless the backup is a targeted tar of ONLY the reviewed files.

    Verifies the artifact, not the claim: member set must equal the reviewed
    manifest's file set exactly, and every per-file sha256 must match.
    """
    if preservation is None:
        raise GateRefusal("MISSING_TARGETED_PRESERVATION",
                          "no targeted preservation record; an unverified backup is not preservation")
    if reviewed_manifest is None:
        raise GateRefusal("MISSING_REVIEWED_MANIFEST",
                          "no reviewed manifest; per-file SHA cannot be checked without it")
    where = "preservation"
    if _text(preservation, "schema", where) != TARGETED_PRESERVATION_SCHEMA:
        raise GateRefusal("MALFORMED_RECORD",
                          "preservation schema is not %s" % TARGETED_PRESERVATION_SCHEMA)
    _text(preservation, "preservation_id", where)
    _match_target(preservation, target, where, "PRESERVATION_TARGET_MISMATCH")
    if _text(preservation, "backup_mode", where) != BACKUP_MODE:
        raise GateRefusal("MALFORMED_RECORD",
                          "preservation backup_mode must be %r" % BACKUP_MODE)
    if not _is_sha256(_field(preservation, "archive_sha256", where)):
        raise GateRefusal("MALFORMED_RECORD", "archive_sha256 must be 64-hex sha256")
    _timestamp(preservation, "created_at", where)
    mwhere = "reviewed_manifest"
    if _text(reviewed_manifest, "schema", mwhere) != REVIEWED_MANIFEST_SCHEMA:
        raise GateRefusal("MALFORMED_RECORD",
                          "manifest schema is not %s" % REVIEWED_MANIFEST_SCHEMA)
    _text(reviewed_manifest, "manifest_id", mwhere)
    if not _is_sha256(_field(reviewed_manifest, "sha256", mwhere)):
        raise GateRefusal("MALFORMED_RECORD", "manifest sha256 must be 64-hex sha256")
    reviewed = _manifest_entries(reviewed_manifest, mwhere)
    backed_up = _file_entries(preservation, "members", where)
    missing = sorted(set(reviewed) - set(backed_up))
    if missing:
        raise GateRefusal("BACKUP_MISSING_CHANGED_FILE",
                          "tar omits changed files: %s" % (", ".join(missing),))
    extra = sorted(set(backed_up) - set(reviewed))
    if extra:
        raise GateRefusal("BACKUP_INCLUDES_UNCHANGED_FILE",
                          "tar carries files that are not being changed: %s"
                          % (", ".join(extra),))
    for path in sorted(reviewed):
        if backed_up[path] != reviewed[path]:
            raise GateRefusal("PER_FILE_SHA_MISMATCH",
                              "%s tar sha %s, reviewed manifest %s"
                              % (path, backed_up[path], reviewed[path]))
    return preservation


def require_temporary_backup_deletion(target, preservation, reviewed_manifest,
                                      applied_verification, deletion, now=None):
    """Allow deleting ONLY this authorized temporary backup, ONLY after an
    independent applied-tree verification passed. Original work is never a
    deletion candidate: the manifest guard already refuses delete entries."""
    require_targeted_preservation(target, preservation, reviewed_manifest, now=now)
    _require_applied_verification(target, applied_verification, now=now)
    if deletion is None:
        raise GateRefusal("MISSING_DELETION_RECORD",
                          "no deletion record; deleting a backup without one is refused")
    where = "deletion"
    named = _text(deletion, "preservation_id", where)
    if named != preservation["preservation_id"]:
        raise GateRefusal("DELETION_NOT_AUTHORIZED_BACKUP",
                          "deletion names %r, authorized temporary backup is %r"
                          % (named, preservation["preservation_id"]))
    deleted_at = _timestamp(deletion, "deleted_at", where)
    verified_at = _timestamp(applied_verification, "verified_at",
                             "applied_verification")
    if deleted_at < verified_at:
        raise GateRefusal("BACKUP_DELETION_BEFORE_VERIFICATION",
                          "deleted_at %s precedes verified_at %s"
                          % (deleted_at.isoformat(), verified_at.isoformat()))
    return deletion


def check_apply(target, backup_authorization, operator_decision=None, now=None,
                preservation=None, reviewed_manifest=None):
    """Refuse APPLY unless a genuine target-exact backup authorization exists
    AND the backup is a verified targeted tar of only the files to change.

    Applied-tree verification cannot exist before application, so it is a
    RELEASE requirement, not an APPLY one; it is never inferred from absence.
    """
    require_backup_authorization(target, backup_authorization, now=now)
    _require_installed_apply(target, operator_decision)
    require_targeted_preservation(target, preservation, reviewed_manifest, now=now)
    return {"decision": "ALLOW_APPLY", "target": target.as_dict(),
            "backup_authorization_id": backup_authorization["authorization_id"],
            "preservation_id": preservation["preservation_id"],
            "installed_apply": target.kind == "installed"}


def check_release(target, backup_authorization, applied_verification,
                  operator_decision=None, now=None,
                  preservation=None, reviewed_manifest=None):
    """Refuse RELEASE unless backup authorization, verified targeted
    preservation AND post-application independent applied-tree verification
    all exist and bind this target."""
    require_backup_authorization(target, backup_authorization, now=now)
    _require_installed_apply(target, operator_decision)
    require_targeted_preservation(target, preservation, reviewed_manifest, now=now)
    _require_applied_verification(target, applied_verification, now=now)
    return {"decision": "ALLOW_RELEASE", "target": target.as_dict(),
            "backup_authorization_id": backup_authorization["authorization_id"],
            "preservation_id": preservation["preservation_id"],
            "applied_verification_id": applied_verification["receipt_id"],
            "installed_apply": target.kind == "installed"}


SCHEMAS = {
    BACKUP_AUTH_SCHEMA: {
        "required": ("authorization_id", "issuer", "channel", "source",
                     "issued_at", "backup_mode", "scope", "target"),
        "optional": ("expires_at",),
        "owner_values": {"issuer": OWNER_ISSUER, "channel": OWNER_CHANNEL,
                         "source": OWNER_SOURCE, "backup_mode": BACKUP_MODE},
    },
    APPLIED_VERIFICATION_SCHEMA: {
        "required": ("receipt_id", "target", "applier", "verifier",
                     "applied_digest", "applied_at", "verified_at",
                     "checks", "result"),
        "required_values": {"result": "PASS"},
    },
    TARGETED_PRESERVATION_SCHEMA: {
        "required": ("preservation_id", "target", "backup_mode",
                     "archive_sha256", "members", "created_at"),
        "required_values": {"backup_mode": BACKUP_MODE},
    },
    REVIEWED_MANIFEST_SCHEMA: {
        "required": ("manifest_id", "sha256", "files"),
        "file_actions": PRESERVED_ACTIONS,
    },
}


# --------------------------------------------------------------------------
# Runnable self-check: tiny synthetic in-memory fixtures only. This is not
# owner authority, creates no file and copies no tree.
# --------------------------------------------------------------------------
def _selfcheck():
    target = Target("repo://example", "75-skill", "canonical-copy", "canonical", "a" * 64)
    installed = Target("repo://example", "75-skill", "installed-copy", "installed", "a" * 64)
    auth = {
        "schema": BACKUP_AUTH_SCHEMA, "authorization_id": "synth-auth",
        "issuer": OWNER_ISSUER, "channel": OWNER_CHANNEL, "source": OWNER_SOURCE,
        "issued_at": "2026-10-31T00:00:00Z", "backup_mode": BACKUP_MODE,
        "scope": ["canonical-copy", "installed-copy"],
        "target": dict(target.as_dict()), "_fixture": "synthetic-selfcheck-not-authority",
    }
    verification = {
        "schema": APPLIED_VERIFICATION_SCHEMA, "receipt_id": "synth-verify",
        "target": dict(target.as_dict()),
        "applier": {"identity": "builder"},
        "verifier": {"identity": "independent-checker", "independent": True},
        "applied_digest": "a" * 64,
        "applied_at": "2026-10-31T01:00:00Z",
        "verified_at": "2026-10-31T02:00:00Z",
        "checks": [{"name": "tree-bytes", "status": "PASS"}],
        "result": "PASS", "_fixture": "synthetic-selfcheck-not-authority",
    }
    manifest = {
        "schema": REVIEWED_MANIFEST_SCHEMA, "manifest_id": "manifest-1",
        "sha256": "c" * 64,
        "files": [{"path": "scripts/core/a.py", "sha256": "d" * 64, "action": "modify"}],
        "_fixture": "synthetic-selfcheck-not-authority",
    }
    preservation = {
        "schema": TARGETED_PRESERVATION_SCHEMA, "preservation_id": "preserve-1",
        "target": dict(target.as_dict()), "backup_mode": BACKUP_MODE,
        "archive_sha256": "e" * 64, "created_at": "2026-10-31T00:30:00Z",
        "members": [{"path": "scripts/core/a.py", "sha256": "d" * 64}],
        "_fixture": "synthetic-selfcheck-not-authority",
    }
    now = _dt.datetime(2026, 11, 1, tzinfo=_dt.timezone.utc)
    checks = []

    def refuses(code, fn, *args, **kwargs):
        checks.append(code)
        try:
            fn(*args, **kwargs)
        except GateRefusal as exc:
            assert exc.code == code, "expected %s, got %s" % (code, exc.code)
            return
        raise AssertionError("expected refusal %s, got allow" % code)

    def allows(fn, *args, **kwargs):
        checks.append("ALLOW")
        return fn(*args, **kwargs)

    # Absence is never permission.
    refuses("MISSING_BACKUP_AUTHORIZATION", require_backup_authorization, target, None)
    refuses("MISSING_TARGETED_PRESERVATION", check_apply, target, auth, None, now)
    refuses("MISSING_APPLIED_TREE_VERIFICATION", check_release,
            target, auth, None, None, now, preservation, manifest)
    # The backup is verified as an artifact, not as the word "targeted".
    other = Target("repo://example", "75-skill", "other-copy", "canonical", "a" * 64)
    other_auth = dict(auth); other_auth["target"] = dict(other.as_dict())
    other_auth["scope"] = ["other-copy"]
    refuses("PRESERVATION_TARGET_MISMATCH", check_apply, other, other_auth, None, now,
            preservation, manifest)
    refuses("MISSING_REVIEWED_MANIFEST", check_apply, target, auth, None, now,
            preservation, None)
    broken = dict(preservation)
    broken["members"] = [{"path": "scripts/core/a.py", "sha256": "d" * 64},
                         {"path": "scripts/core/untouched.py", "sha256": "d" * 64}]
    refuses("BACKUP_INCLUDES_UNCHANGED_FILE", require_targeted_preservation,
            target, broken, manifest, now)
    broken = dict(preservation); broken["members"] = []
    refuses("MALFORMED_RECORD", require_targeted_preservation, target, broken, manifest, now)
    broken = dict(preservation); broken["members"] = [
        {"path": "scripts/core/other.py", "sha256": "d" * 64}]
    refuses("BACKUP_MISSING_CHANGED_FILE", require_targeted_preservation,
            target, broken, manifest, now)
    broken = dict(preservation); broken["members"] = [
        {"path": "scripts/core/a.py", "sha256": "f" * 64}]
    refuses("PER_FILE_SHA_MISMATCH", require_targeted_preservation,
            target, broken, manifest, now)
    broken = dict(preservation); broken["members"] = [
        {"path": "scripts/core/a.py", "sha256": "d" * 64},
        {"path": "scripts/core/a.py", "sha256": "d" * 64}]
    refuses("DUPLICATE_FILE_PATH", require_targeted_preservation,
            target, broken, manifest, now)
    deleting = {"schema": REVIEWED_MANIFEST_SCHEMA, "manifest_id": "manifest-2",
                "sha256": "c" * 64,
                "files": [{"path": "scripts/core/a.py", "sha256": "d" * 64,
                           "action": "delete"}]}
    refuses("ORIGINAL_WORK_DELETED", require_targeted_preservation,
            target, preservation, deleting, now)
    # Malformed: a missing field never defaults to valid.
    broken = dict(auth); broken.pop("issued_at")
    refuses("MALFORMED_RECORD", require_backup_authorization, target, broken, now)
    broken = dict(auth); broken["target"] = {k: v for k, v in auth["target"].items()
                                             if k != "tree_digest"}
    refuses("MALFORMED_RECORD", require_backup_authorization, target, broken, now)
    # Wrong issuer / wrong target / expired.
    broken = dict(auth); broken["issuer"] = "owner:someone-else"
    refuses("NOT_OWNER_ISSUED", require_backup_authorization, target, broken, now)
    refuses("BACKUP_AUTHORIZATION_TARGET_MISMATCH",
            require_backup_authorization, other, auth, now)
    broken = dict(auth); broken["expires_at"] = "2026-10-30T00:00:00Z"
    refuses("BACKUP_AUTHORIZATION_EXPIRED", require_backup_authorization, target, broken, now)
    # Apply allows only with authorization; installed needs the operator decision.
    installed_auth = dict(auth); installed_auth["target"] = dict(installed.as_dict())
    installed_auth["_fixture"] = "synthetic-selfcheck-not-authority"
    installed_preservation = dict(preservation)
    installed_preservation["target"] = dict(installed.as_dict())
    installed_preservation["_fixture"] = "synthetic-selfcheck-not-authority"
    assert allows(check_apply, target, auth, None, now,
                  preservation, manifest)["decision"] == "ALLOW_APPLY"
    refuses("INSTALLED_APPLY_NOT_AUTHORIZED", check_apply, installed, installed_auth,
            None, now, installed_preservation, manifest)
    refuses("INSTALLED_APPLY_NOT_AUTHORIZED", check_apply, installed, installed_auth,
            {"installed_apply": "yes"}, now, installed_preservation, manifest)
    assert allows(check_apply, installed, installed_auth,
                  {"installed_apply": True}, now,
                  installed_preservation, manifest)["decision"] == "ALLOW_APPLY"
    # Release requires independent, post-application, digest-bound verification.
    assert allows(check_release, target, auth, verification, None, now,
                  preservation, manifest)["decision"] == "ALLOW_RELEASE"
    broken = dict(verification); broken["target"] = dict(installed.as_dict())
    refuses("APPLIED_VERIFICATION_TARGET_MISMATCH",
            check_release, target, auth, broken, None, now, preservation, manifest)
    broken = dict(verification); broken["applied_digest"] = "b" * 64
    refuses("APPLIED_VERIFICATION_DIGEST_MISMATCH",
            check_release, target, auth, broken, None, now, preservation, manifest)
    broken = dict(verification); broken["verifier"] = {"identity": "builder",
                                                       "independent": True}
    refuses("APPLIED_VERIFICATION_NOT_INDEPENDENT",
            check_release, target, auth, broken, None, now, preservation, manifest)
    broken = dict(verification); broken["verifier"] = {"identity": "independent-checker"}
    refuses("MALFORMED_RECORD", check_release, target, auth, broken, None, now,
            preservation, manifest)
    broken = dict(verification); broken["verifier"] = {"identity": "independent-checker",
                                                       "independent": "true"}
    refuses("APPLIED_VERIFICATION_NOT_INDEPENDENT",
            check_release, target, auth, broken, None, now, preservation, manifest)
    broken = dict(verification)
    broken["applied_at"] = "2026-10-31T03:00:00Z"
    broken["verified_at"] = "2026-10-31T02:00:00Z"
    refuses("APPLIED_VERIFICATION_NOT_AFTER_APPLICATION",
            check_release, target, auth, broken, None, now, preservation, manifest)
    broken = dict(verification); broken["checks"] = [{"name": "x", "status": "FAIL"}]
    refuses("APPLIED_VERIFICATION_CHECK_FAILED",
            check_release, target, auth, broken, None, now, preservation, manifest)
    broken = dict(verification); broken["result"] = "UNKNOWN"
    refuses("APPLIED_VERIFICATION_NOT_PASS",
            check_release, target, auth, broken, None, now, preservation, manifest)
    # Deleting the temporary backup is allowed ONLY after applied verification.
    late = {"preservation_id": "preserve-1", "deleted_at": "2026-10-31T05:00:00Z"}
    early = {"preservation_id": "preserve-1", "deleted_at": "2026-10-31T01:30:00Z"}
    wrong = {"preservation_id": "some-other-backup", "deleted_at": "2026-10-31T05:00:00Z"}
    assert allows(require_temporary_backup_deletion, target, preservation, manifest,
                  verification, late, now) is late
    refuses("BACKUP_DELETION_BEFORE_VERIFICATION",
            require_temporary_backup_deletion, target, preservation, manifest,
            verification, early, now)
    refuses("MISSING_APPLIED_TREE_VERIFICATION",
            require_temporary_backup_deletion, target, preservation, manifest,
            None, late, now)
    refuses("DELETION_NOT_AUTHORIZED_BACKUP",
            require_temporary_backup_deletion, target, preservation, manifest,
            verification, wrong, now)
    return "SELFCHECK_OK %d assertions" % len(checks)


if __name__ == "__main__":
    print(_selfcheck())
