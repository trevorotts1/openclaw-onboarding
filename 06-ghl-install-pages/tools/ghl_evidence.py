#!/usr/bin/env python3
"""ghl_evidence.py: the S06-08 tenant-safe read-back + no-secret evidence
contract for Skill 06 (doc 18 section 7, A27 evidence side).

THE CONTRACT (Q1/Q2 dispositions, S06-08 Checkpoint 1)
-----------------------------------------------------
ONE tenant-safe read-back contract, satisfied two ways. Nothing is renamed
or re-keyed; there is NO unified replacement schema.

Form 1: record families that ARE records (verify summary + raw verify
records, router/object receipts, ladder receipts, the builder run report /
run-state document, inventory exports) carry the contract fields natively
and additively:

  * ``expected_location_id``: the location the run was gated for, or None
    when the producing call was not given one.
  * ``observed_location_id``: the location a read-back actually observed,
    or None when no read could obtain one.
  * ``tenant_binding``: exactly one of "bound" (expected and observed both
    present and equal), "mismatch" (both present and unequal), "unbound"
    (either absent). A record that cannot bind states "unbound" explicitly;
    the field is never silently omitted on records produced by
    S06-08-and-later code.
  * ``run_id`` where the producing API knows it.
  * ``redactions``: the count of secret redactions applied to the record
    before it was written (see NO SECRETS below), so the scrubbing is itself
    evidenced.

  Cross-tenant rule: observed != expected is a CONTRADICTION
  (VerifyContradiction / ReceiptContradiction class), never a pass. A PASS
  record whose binding is not "bound" in a run that declared an expected
  location fails the assert_consistent mirror invariants.

Form 2: file-shaped artifacts (render manifest + DOM/PNG/console captures,
the ID-handoff record routing/id-handoff.json, provisioning and path-set
receipts when present in a run root) are bound through the per-run READ-BACK
INDEX in this module (schema skill6-readback-index/1, precedent shape:
tools/ghl_id_handoff.py's skill6-id-handoff/1): one index per run at the
run's evidence root, stamping run id, expected location id, and each member
artifact's path + sha256. The ID-handoff record is a MEMBER of the index
set, not a competing index. The artifacts named in this paragraph are the
index's DESIGNATED members; the inventory export and the run-state document
are not among them (they satisfy the contract in Form 1, per the deviation
note below).

DEVIATION S06-08-DEV-01 (coordinator-accepted, recorded in the room
evidence): the Q1 disposition's item 2 assigned the inventory export and
the run-state document to Form 2 above. As shipped, both satisfy the
contract in Form 1 instead: each is a single JSON document carrying the
full contract field set natively (inventory export:
``observed_location_id``, ``tenant_binding``, ``tenant_mismatch_rows``;
run-state document: ``expected_location_id``, ``trace_suppression``,
``redactions``), and neither is a designated member of the read-back
index. The shipped assignment is the contract; the disposition's letter
is superseded on this one point by the deviation record.

Q2 grandfathering: the fields are additive-optional everywhere. A legacy
record WITHOUT them is treated as tenant-unbound and flagged as such by the
reducers, never silently bound. Old evidence roots stay readable. Nothing
already written is re-stamped.

NOT evidence: order plans (skill6-order-plan/1) are inputs only, never
stamped, never swept, never cited as proof. The three pre-existing location
fields keep their names and strengths and none satisfies this contract
alone: order-plan ``location_id`` (declared input, never compared to a
read-back), ID-handoff ``scope.locationRef`` (optional caller-supplied
label, never derived or validated), inventory ``location_id`` (the location
the enumeration was ASKED for; the listers are wired public defaults since
S06-07, and enumerate still records the asked-for id and verifies nothing
about lister tenant).

Credential presence is stated as "resolvable via the canonical resolver"
(tools/ghl_secret_resolver.py). Capability-probe output is env-presence
only and is never cited as evidence of resolvability.

NO SECRETS (Q3 disposition: BOTH strategies)
--------------------------------------------
* Write-time scrubbing for every text sink, via ``EvidenceScrubber``:
  generic secret-SHAPED patterns (this module's pattern set is shapes only,
  so the set itself can never become a leak list) PLUS the run's resolved
  secret VALUES, supplied by the caller and held in memory only, never
  persisted, never written into any artifact as a pattern list. Every
  redaction is counted and the count recorded on the record.
* Capture-time SUPPRESSION where masking cannot be done honestly (binary
  captures on sensitive steps), with the suppression recorded: the
  ghl_login_browser.py precedent (capture_artifacts default False). The
  trace-suppression record shape and validator live here (Q5 disposition:
  S06-08 states the rule and records the flag; S06-06/S79 own the capture
  surfaces). No trace or network-body recording is permitted on a login or
  payment step unless the scrubber is wired for that surface AND the
  no-secret sweep passes for it.

PERMISSIONS (Q4 adopted interim default, recorded at S06-08 build start)
------------------------------------------------------------------------
Evidence roots are mode 0700 on creation; evidence files are mode 0600,
set explicitly by the writer, never left to umask. ``audit_evidence_permissions``
reports a root whose files or directories grant group/other access: a
permission failure is REPORTED, never silently accepted.

INTEGRITY HONESTY (prep R1): writers come in two classes and the code says
which is which. Atomic writers (temp + fsync + rename) cannot leave a torn
file. Plain in-place writers (the four ghl_verify.verify_all writes: raw
log, summary, render manifest, mock sentinel) CAN be torn by a kill
mid-write; a partial or unparseable evidence file is FAILED evidence,
never a pass: the consistency guards and readers treat it that way.

NQ5 known limitation: browser_manager's bm_provision_preflight is
advisory-only and writes no receipt, so advisory provisioning state is
invisible to the evidence record BY DESIGN. The provisioning receipt
(skill6-vps-provisioning/1) is the evidence artifact when the check runs.

Self-test: ``python3 ghl_evidence.py --selftest`` (no network, no browser).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from typing import Any, Iterable, Optional

# ── Permissions (Q4 adopted interim default) ────────────────────────────────
ROOT_MODE = 0o700
FILE_MODE = 0o600

# ── Tenant binding states ────────────────────────────────────────────────────
BINDING_BOUND = "bound"
BINDING_MISMATCH = "mismatch"
BINDING_UNBOUND = "unbound"

READBACK_INDEX_SCHEMA = "skill6-readback-index/1"
READBACK_INDEX_REL = "readback-index.json"

REDACTED = "[REDACTED]"


class EvidenceContradiction(Exception):
    """A read-back index (or a record checked against it) contradicts its
    evidence: a missing artifact, a hash mismatch, or a tenant mismatch.
    Contradictions are never passes."""


class TraceSuppressionError(Exception):
    """A trace-suppression record claims capture was NOT suppressed on a
    step the contract requires suppressed (login / payment)."""


# ── Tenant binding ───────────────────────────────────────────────────────────

def tenant_binding(expected: Any, observed: Any) -> str:
    """Derive the binding state from an expected/observed location pair.

    Both present and equal -> "bound"; both present and unequal ->
    "mismatch"; either absent -> "unbound" (never silently bound, per Q2).
    """
    exp = str(expected).strip() if isinstance(expected, str) else expected
    obs = str(observed).strip() if isinstance(observed, str) else observed
    if exp and obs:
        return BINDING_BOUND if exp == obs else BINDING_MISMATCH
    return BINDING_UNBOUND


def tenant_fields(
    expected: Any = None,
    observed: Any = None,
    *,
    run_id: Any = None,
) -> dict:
    """The additive contract fields for one record (Q1 form 1)."""
    fields = {
        "expected_location_id": expected if expected else None,
        "observed_location_id": observed if observed else None,
        "tenant_binding": tenant_binding(expected, observed),
    }
    if run_id is not None:
        fields["run_id"] = run_id
    return fields


def effective_binding(record: dict) -> str:
    """A record's binding, derived from its location fields when the record
    predates the explicit ``tenant_binding`` stamp (Q2: absent = unbound,
    flagged by derivation, never silently bound)."""
    stamped = record.get("tenant_binding")
    if stamped in (BINDING_BOUND, BINDING_MISMATCH, BINDING_UNBOUND):
        return stamped
    return tenant_binding(
        record.get("expected_location_id"), record.get("observed_location_id")
    )


# Observed-location extraction from rendered DOM text. A rendered GHL page
# names its location in its media CDN paths (assets.cdn.filesafe.space/<id>/)
# and in app URLs (/location/<id>/). One DISTINCT id is an observation; zero
# or several distinct ids is no observation (never a guess).
_OBSERVED_PATTERNS = (
    re.compile(r"assets\.cdn\.filesafe\.space/([A-Za-z0-9]{16,32})/"),
    re.compile(r"/location/([A-Za-z0-9]{16,32})(?:[/?#\"']|$)"),
)


def extract_observed_location_id(text: Any) -> Optional[str]:
    """Return the single distinct location id a rendered-DOM text names, or
    None when it names none, or more than one (ambiguous = unobserved)."""
    if not isinstance(text, str) or not text:
        return None
    found = set()
    for pattern in _OBSERVED_PATTERNS:
        found.update(pattern.findall(text))
    if len(found) == 1:
        return next(iter(found))
    return None


# ── The evidence scrubber (Q3: write-time scrubbing) ────────────────────────
#
# Generic secret SHAPES only. This pattern set must never contain a real
# value: it is safe to ship, print, and commit precisely because it matches
# shapes, not secrets. Resolved secret VALUES are supplied per-run to
# EvidenceScrubber(...) and held in memory only.

def _bearer_repl(match: "re.Match[str]") -> str:
    return f"{match.group(1)} {REDACTED}"


def _assignment_repl(match: "re.Match[str]") -> str:
    return f"{match.group(1)}{match.group(2)}{REDACTED}"


_SHAPE_PATTERNS: tuple = (
    # Authorization: Bearer <value>
    (re.compile(r"(?i)\b(Bearer)\s+[A-Za-z0-9._\-]{8,}"), _bearer_repl),
    # JSON Web Token (three base64url segments, header starts eyJ)
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}\b"),
     REDACTED),
    # GoHighLevel Private Integration Token shape
    (re.compile(r"\bpit-[A-Za-z0-9_\-]{8,}"), REDACTED),
    # Provider-prefixed key shapes (GitHub, Slack, Stripe-style, OpenAI-style)
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"), REDACTED),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), REDACTED),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"), REDACTED),
    (re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_\-]{16,}\b"), REDACTED),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTED),
    # key = value / "key": value assignments for secret-named keys. The value
    # may be quoted or bare; the key and separator are preserved so the
    # redacted text still shows WHICH field carried a secret.
    (re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|"
        r"id[_-]?token|client[_-]?secret|password|passwd|secret|token|pit)\b"
        r"(?:[\"'])?"
        r"(\s*[:=]\s*)"
        r"(?:\"[^\"]{4,}\"|'[^']{4,}'|[^\s,;\"'}\]]{4,})"
    ), _assignment_repl),
)

# Values shorter than this are never treated as resolved secrets: replacing
# very short strings would mangle ordinary evidence text.
_MIN_VALUE_LEN = 8


class EvidenceScrubber:
    """Value-aware redactor for evidence text (Q3 write-time scrubbing).

    ``secret_values`` are the run's resolved secret values. They are held in
    memory only, used for literal replacement, and NEVER persisted: this
    object writes nothing, and its pattern set (module-level shapes) is the
    only part that ever appears in an artifact, as a count, never a list.

    Scrubbing is idempotent: the REDACTED marker matches no pattern, so
    re-scrubbing an already-scrubbed structure counts zero new redactions.
    """

    def __init__(self, secret_values: Iterable[Any] | None = None) -> None:
        values = set()
        for v in secret_values or ():
            if isinstance(v, str) and len(v) >= _MIN_VALUE_LEN:
                values.add(v)
        # Longest first, so a value that contains another is consumed whole.
        self._values = sorted(values, key=len, reverse=True)

    def scrub_text(self, text: Any) -> tuple:
        """Return (scrubbed_text, redaction_count). Non-strings pass through
        unchanged with a zero count."""
        if not isinstance(text, str) or not text:
            return text, 0
        count = 0
        out = text
        for value in self._values:
            hits = out.count(value)
            if hits:
                out = out.replace(value, REDACTED)
                count += hits
        for pattern, repl in _SHAPE_PATTERNS:
            out, n = pattern.subn(repl, out)
            count += n
        return out, count

    def scrub_obj(self, obj: Any) -> tuple:
        """Deep-scrub every string VALUE in a JSON-shaped structure (dict
        keys are schema, not secrets, and are left as-is). Returns
        (scrubbed_obj, total_redactions). The input is not mutated."""
        if isinstance(obj, str):
            return self.scrub_text(obj)
        if isinstance(obj, dict):
            total = 0
            out = {}
            for key, value in obj.items():
                scrubbed, n = self.scrub_obj(value)
                out[key] = scrubbed
                total += n
            return out, total
        if isinstance(obj, (list, tuple)):
            total = 0
            items = []
            for value in obj:
                scrubbed, n = self.scrub_obj(value)
                items.append(scrubbed)
                total += n
            return (items if isinstance(obj, list) else tuple(items)), total
        return obj, 0


_DEFAULT_SCRUBBER = EvidenceScrubber()


def scrub_obj(obj: Any, secret_values: Iterable[Any] | None = None) -> tuple:
    """Convenience: scrub with a fresh scrubber (generic shapes, plus any
    resolved values supplied for this call)."""
    if secret_values is None:
        return _DEFAULT_SCRUBBER.scrub_obj(obj)
    return EvidenceScrubber(secret_values).scrub_obj(obj)


def scrub_text(text: Any, secret_values: Iterable[Any] | None = None) -> tuple:
    """Convenience wrapper over EvidenceScrubber.scrub_text."""
    if secret_values is None:
        return _DEFAULT_SCRUBBER.scrub_text(text)
    return EvidenceScrubber(secret_values).scrub_text(text)


# ── Permission-explicit evidence IO (Q4 interim default) ────────────────────

def ensure_private_dir(path: str) -> str:
    """Create ``path`` (and any missing parents) with mode 0700 on every
    directory this call creates. Existing directories are left untouched:
    auditing them is audit_evidence_permissions' job, not a silent chmod."""
    if not path:
        return path
    missing = []
    cursor = os.path.abspath(path)
    while not os.path.isdir(cursor):
        missing.append(cursor)
        parent = os.path.dirname(cursor)
        if parent == cursor:
            break
        cursor = parent
    for directory in reversed(missing):
        os.mkdir(directory, ROOT_MODE)
        # mkdir honours umask; set the mode explicitly (Q4: never umask).
        os.chmod(directory, ROOT_MODE)
    return path


def set_private_file(path: str) -> None:
    """Set an evidence file's mode to 0600 explicitly."""
    os.chmod(path, FILE_MODE)


def write_text_private(path: str, text: str) -> str:
    """PLAIN in-place write (NOT atomic, the R1 honesty class of the four
    verify_all writes) with the file mode set to 0600 explicitly. A kill
    mid-write can leave a torn file; torn evidence is failed evidence,
    never a pass, and the consistency guards treat it that way."""
    parent = os.path.dirname(path)
    if parent:
        ensure_private_dir(parent)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    set_private_file(path)
    return path


def write_json_private(path: str, obj: Any) -> str:
    """Plain in-place JSON write at 0600 (see write_text_private)."""
    return write_text_private(path, json.dumps(obj, indent=2))


def atomic_write_json_private(path: str, obj: Any) -> str:
    """Atomic JSON write: temp file in the same directory, mode 0600 set on
    the temp BEFORE fsync + rename, so the file never exists at a looser
    mode. This is the writer class of write_receipt / run-state save() /
    inventory _atomic_write_json / write_handoff, now mode-explicit."""
    parent = os.path.dirname(path)
    if parent:
        ensure_private_dir(parent)
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, default=str)
        fh.flush()
        os.chmod(tmp, FILE_MODE)
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


def scrub_file_text(path: str, scrubber: EvidenceScrubber | None = None) -> int:
    """Scrub a text artifact in place (DOM / console captures). Returns the
    redaction count; zero when the file is missing or already clean. Binary
    artifacts (PNG) are never passed here: they are capture-time
    suppression territory (Q3), not text scrubbing."""
    if not path or not os.path.isfile(path):
        return 0
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            body = fh.read()
    except OSError:
        return 0
    scrubbed, n = (scrubber or _DEFAULT_SCRUBBER).scrub_text(body)
    if n:
        write_text_private(path, scrubbed)
    return n


def sha256_file(path: str) -> str:
    """sha256 of a file's bytes, or "" when it cannot be read."""
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


# ── Permission audit (step 8: failures are reported, never accepted) ────────

def audit_evidence_permissions(root: str) -> dict:
    """Audit an evidence root against the Q4 interim default (0700 dirs /
    0600 files). Returns {"root", "checked_dirs", "checked_files",
    "problems": [{"path", "mode", "problem"}, ...]}. Any directory or file
    granting group/other access is a problem: REPORTED here so a run (or a
    test) can refuse to treat the root as access-controlled evidence.
    Unauthenticated receipt access is denied by these bits: a receipt store
    under a 0700 root of 0600 files is not readable by other local users."""
    problems: list = []
    checked_dirs = 0
    checked_files = 0
    if not root or not os.path.isdir(root):
        return {
            "root": root,
            "checked_dirs": 0,
            "checked_files": 0,
            "problems": [{"path": root, "mode": None,
                          "problem": "evidence root does not exist"}],
        }
    for dirpath, _dirnames, filenames in os.walk(root):
        checked_dirs += 1
        dir_mode = stat.S_IMODE(os.stat(dirpath).st_mode)
        if dir_mode & 0o077:
            problems.append({
                "path": dirpath, "mode": oct(dir_mode),
                "problem": "directory grants group/other access (Q4 default is 0700)",
            })
        for name in filenames:
            fpath = os.path.join(dirpath, name)
            try:
                file_mode = stat.S_IMODE(os.stat(fpath).st_mode)
            except OSError:
                continue
            checked_files += 1
            if file_mode & 0o077:
                problems.append({
                    "path": fpath, "mode": oct(file_mode),
                    "problem": "file grants group/other access (Q4 default is 0600)",
                })
    return {
        "root": root,
        "checked_dirs": checked_dirs,
        "checked_files": checked_files,
        "problems": problems,
    }


# ── Trace suppression (Q5: S06-08 states the rule, records the flag) ────────

# Steps whose captures may carry credentials or payment data. On these steps
# artifacts are SUPPRESSED at capture time (login precedent) and the
# suppression is what the evidence records.
TRACE_SUPPRESSED_STEPS = ("login", "payment")


def trace_suppression_record(
    step: str,
    *,
    artifacts_suppressed: bool = True,
    capture_artifacts: bool = False,
) -> dict:
    """One step's trace-suppression record for run evidence."""
    return {
        "step": step,
        "capture_artifacts": bool(capture_artifacts),
        "artifacts_suppressed": bool(artifacts_suppressed),
    }


def default_trace_suppression() -> list:
    """The contract's default record set: login AND payment steps, both
    suppressed (Q5)."""
    return [trace_suppression_record(step) for step in TRACE_SUPPRESSED_STEPS]


def validate_trace_suppression(records: Iterable[dict] | None) -> None:
    """Refuse a record set that claims a login or payment step captured
    artifacts unsuppressed. Raises TraceSuppressionError. A record set that
    simply omits a step makes no claim and is not refused here: consumers
    that require the flags check presence themselves."""
    for record in records or ():
        step = str(record.get("step", ""))
        if step in TRACE_SUPPRESSED_STEPS:
            if record.get("artifacts_suppressed") is not True:
                raise TraceSuppressionError(
                    f"trace suppression violated: step {step!r} does not record "
                    "artifacts_suppressed=True (Q5: login and payment captures "
                    "are suppressed at capture time and the suppression is "
                    "recorded, never the artifacts)"
                )
            if record.get("capture_artifacts"):
                raise TraceSuppressionError(
                    f"trace suppression violated: step {step!r} records "
                    "capture_artifacts=True alongside suppression"
                )


# ── The per-run read-back index (Q1 form 2) ──────────────────────────────────

def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_readback_index(
    run_dir: str,
    *,
    run_id: str = "",
    expected_location_id: Any = None,
    artifacts: Iterable[dict] = (),
    trace_suppression: Iterable[dict] | None = None,
    notes: Iterable[str] | None = None,
) -> dict:
    """Assemble the per-run read-back index over a run's OWN roots (NQ2:
    the caller passes artifacts from this run's evidence root only: the
    index binds what it is given and verifies by re-hash, so pointing it at
    another run's files is visible in the recorded paths).

    Each artifact entry: {"path": <path, stored as given>, "kind": <label>,
    optionally "observed_location_id": <id a read obtained from it>,
    optionally "redactions": <count of secret redactions applied to the
    artifact before it was written>}. A supplied "redactions" count is
    recorded verbatim on the entry (int-coerced, 0 included); when none is
    supplied the entry omits the field, the same convention as
    "observed_location_id" (S06-08 D3 cure: a supplied count is contract
    data and is never silently dropped).
    Entries are stamped here with sha256 + byte size read from disk; an
    artifact that cannot be read raises EvidenceContradiction (an index
    over missing evidence is a fabrication channel, never written)."""
    stamped = []
    observed_ids = []
    for artifact in artifacts:
        path = artifact.get("path", "")
        digest = sha256_file(path)
        if not digest:
            raise EvidenceContradiction(
                f"read-back index refuses a missing/unreadable artifact: {path!r}"
            )
        entry = {
            "path": path,
            "kind": artifact.get("kind", ""),
            "sha256": digest,
            "bytes": os.path.getsize(path),
        }
        supplied_redactions = artifact.get("redactions")
        if supplied_redactions is not None:
            entry["redactions"] = int(supplied_redactions)
        observed = artifact.get("observed_location_id")
        if observed:
            entry["observed_location_id"] = observed
            entry["tenant_binding"] = tenant_binding(expected_location_id, observed)
            observed_ids.append(observed)
        stamped.append(entry)

    if expected_location_id and observed_ids:
        if any(o != expected_location_id for o in observed_ids):
            run_binding = BINDING_MISMATCH
        else:
            run_binding = BINDING_BOUND
    else:
        run_binding = BINDING_UNBOUND

    suppression = (
        list(trace_suppression) if trace_suppression is not None
        else default_trace_suppression()
    )
    validate_trace_suppression(suppression)

    index_notes = list(notes or ())
    index_notes.append(
        "NQ5: bm_provision_preflight advisory state is not evidence and is "
        "not visible to this index; the provisioning receipt "
        "(skill6-vps-provisioning/1) is the evidence artifact when present."
    )
    return {
        "schema": READBACK_INDEX_SCHEMA,
        "run_id": run_id or os.path.basename(os.path.abspath(run_dir)),
        "run_dir": run_dir,
        "expected_location_id": expected_location_id if expected_location_id else None,
        "tenant_binding": run_binding,
        "created_at": _iso_now(),
        "artifacts": stamped,
        "trace_suppression": suppression,
        "notes": index_notes,
    }


def write_readback_index(run_dir: str, index: dict) -> str:
    """Write the index at the run's durable evidence root (atomic, 0600)."""
    path = os.path.join(run_dir, READBACK_INDEX_REL)
    return atomic_write_json_private(path, index)


def verify_readback_index(index: dict) -> dict:
    """Re-verify an index against disk: every member artifact must exist
    with the recorded sha256, and no member may observe a different tenant
    than the index's expected location. Any failure raises
    EvidenceContradiction. Returns the recomputed tenant summary."""
    expected = index.get("expected_location_id")
    observed_ids = []
    for entry in index.get("artifacts", []):
        path = entry.get("path", "")
        actual = sha256_file(path)
        if not actual:
            raise EvidenceContradiction(
                f"read-back index member is missing on disk: {path!r}"
            )
        if actual != entry.get("sha256"):
            raise EvidenceContradiction(
                f"read-back index hash mismatch for {path!r}: index records "
                f"{entry.get('sha256')!r}, disk hashes {actual!r}: evidence "
                "has changed since the index was written"
            )
        observed = entry.get("observed_location_id")
        if observed:
            observed_ids.append(observed)
            if expected and observed != expected:
                raise EvidenceContradiction(
                    f"read-back index tenant mismatch: {path!r} observed "
                    f"location {observed!r} against expected {expected!r}"
                )
    recomputed = (
        tenant_binding(expected, observed_ids[0])
        if expected and len(set(observed_ids)) == 1
        else (BINDING_MISMATCH if expected and observed_ids else BINDING_UNBOUND)
    )
    if index.get("tenant_binding") == BINDING_BOUND and recomputed != BINDING_BOUND:
        raise EvidenceContradiction(
            "read-back index claims tenant_binding 'bound' but re-verification "
            f"computes {recomputed!r}"
        )
    validate_trace_suppression(index.get("trace_suppression"))
    return {
        "ok": True,
        "artifacts": len(index.get("artifacts", [])),
        "tenant_binding": recomputed,
    }


# ── Self-test ────────────────────────────────────────────────────────────────

def _selftest() -> int:
    import tempfile

    # Tenant binding derivation.
    assert tenant_binding("locA", "locA") == "bound"
    assert tenant_binding("locA", "locB") == "mismatch"
    assert tenant_binding("locA", None) == "unbound"
    assert tenant_binding(None, "locA") == "unbound"
    assert effective_binding({"expected_location_id": "locA"}) == "unbound"

    # Scrubber: values (memory only) + shapes; idempotent; counted.
    secret = "pit-fixture-1234567890abcdef"
    scrubber = EvidenceScrubber([secret])
    out, n = scrubber.scrub_text(f"auth failed for {secret} in body")
    assert secret not in out and n == 1, out
    out2, n2 = scrubber.scrub_text(out)
    assert n2 == 0 and out2 == out
    shaped, n3 = scrubber.scrub_text("Authorization: Bearer abcdefgh12345678")
    assert "abcdefgh12345678" not in shaped and n3 == 1
    assigned, n4 = scrubber.scrub_text('{"refresh_token": "fixture-value-1234"}')
    assert "fixture-value-1234" not in assigned and n4 == 1
    obj, n5 = scrubber.scrub_obj({"a": [secret, {"b": "clean"}]})
    assert n5 == 1 and obj["a"][1]["b"] == "clean"

    # Observed extraction: one distinct id only.
    dom = '<img src="https://assets.cdn.filesafe.space/Ab1Cd2Ef3Gh4Ij5Kl6Mn/media/x.png">'
    assert extract_observed_location_id(dom) == "Ab1Cd2Ef3Gh4Ij5Kl6Mn"
    assert extract_observed_location_id("<p>no ids here</p>") is None

    # Permissions + index round trip over a tmp root.
    with tempfile.TemporaryDirectory() as tmp:
        root = ensure_private_dir(os.path.join(tmp, "run"))
        member = os.path.join(root, "routing", "id-handoff.json")
        write_json_private(member, {"schema": "skill6-id-handoff/1"})
        assert stat.S_IMODE(os.stat(member).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(root).st_mode) == 0o700
        index = build_readback_index(
            root, run_id="run-selftest", expected_location_id="Ab1Cd2Ef3Gh4Ij5Kl6Mn",
            artifacts=[{"path": member, "kind": "id_handoff",
                        "observed_location_id": "Ab1Cd2Ef3Gh4Ij5Kl6Mn"}],
        )
        assert index["tenant_binding"] == "bound"
        path = write_readback_index(root, index)
        loaded = json.loads(open(path).read())
        assert verify_readback_index(loaded)["ok"] is True
        audit = audit_evidence_permissions(root)
        assert audit["problems"] == [], audit
        # A loosened file is REPORTED, not silently accepted.
        os.chmod(member, 0o644)
        audit2 = audit_evidence_permissions(root)
        assert any(p["path"] == member for p in audit2["problems"])

    # Trace suppression validator refuses an unsuppressed payment record.
    try:
        validate_trace_suppression(
            [{"step": "payment", "capture_artifacts": True,
              "artifacts_suppressed": False}]
        )
        raise AssertionError("unsuppressed payment record was accepted")
    except TraceSuppressionError:
        pass

    print("ghl_evidence selftest: OK")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="S06-08 evidence contract")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        raise SystemExit(_selftest())
    parser.print_help()
    raise SystemExit(2)
