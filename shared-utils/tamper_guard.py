#!/usr/bin/env python3
"""tamper_guard.py - FIX-PLAN Item 32: the anti-tampering switch.

Implements B12's design (build/b12-antitamper/DESIGN.md). Every in-scope
skill install (design Section 1; the published set lives in
tamper-guard-scope.json) carries a sealed, staff-signed inventory of its
files. This guard lives OUTSIDE the trees it watches (design Section 2.4)
and verifies them byte-exactly:

  * at load (session start / engine Phase-0 preflight):  verify, session-start
  * on the fleet watchdog cadence (600 s):               watchdog
  * after every update roll (post-roll, lock released):  verify

Divergence (design Section 3) locks that one skill on that one
install at once. Extraction behavior (design Section 4) runs through
the three-strike ladder (DEV-1 as amended, below): each strike is
recorded and notified at warning time, and the third standing strike
locks the struck skill. Either way the response is the same once it
fires: the incident is recorded FIRST, staff are notified off the
box, the tree is moved bytes-preserved into off-tree quarantine, and
a stub takes its place (design Section 6). Reinstatement is
staff-only, requires the recorded user_spoke_to_staff attestation,
and restores from canonical source, never from quarantine by default
(design Section 7).

DEVIATIONS FROM THE FIX-PLAN LETTER, AS DESIGNED (design Section 11).
They were built exactly as designed and flagged here, in the operator
doc (TAMPER-GUARD.md), and in the build manifest. The owner ruled on
2026-10-15: DEV-1 to DEV-4 are accepted as built, and DEV-1's posture
is then EXTENDED the same day by his warn-first amendment (design
amendment build/b38-antitamper/AMENDMENT-2026-10-15.md, with his
calls on its flagged points F1 to F8), which this build implements:

  DEV-1  Judgment-layer posture, as amended: comprehension and use
         never score as extraction (the Section 4.1 "does not count"
         list is an explicit scoring pass). Every conversational and
         pattern trigger warns first: a strike is recorded, the
         client sees the strike notice, and the owner is notified and
         asked for his call (allow the behavior, or remove the
         strike). Strikes accumulate PER CLIENT across all guarded
         skills; the third standing strike locks automatically
         through the Section 6 response. Corroboration never skips
         the warning. Ordinary D1/D3 events are strikes (the act
         itself is still denied at once); bulk mechanical dumping
         locks immediately, even on a first offense (thresholds at
         the constants below). The integrity trigger is not part of
         the ladder and keeps its immediate lockout. DEV-2, DEV-3,
         and DEV-4 stand as accepted, unchanged.
  DEV-2  Harness-shape immediacy: in the 999 Claude Code shape, chat
         replies pass through no hook, so a CONVERSATIONAL lock is
         recorded at once, tool-level denial is immediate, and the
         quarantine/stub lands at the next session start. In OpenClaw
         shapes conversational locks land immediately.
  DEV-3  Update window and crashed-update grace: divergence inside a
         verified update window does not lock; a crashed update gets
         one staff-notified 24-hour grace window. Events are logged and
         notified immediately; only the lock waits.
  DEV-4  Rollout baseline adoption: a pre-guard install with no
         manifest adopts a signed baseline from its installed tree on
         first run (recorded, staff-notified) instead of locking the
         whole fleet on day one.

EXEMPTION DISCIPLINE (design Section 5, owner standing order): staff
context exempts the conversational trigger ONLY when established by an
authenticated channel: a staff token from the box secrets store, the
token-authenticated Command Center path, or a staff SSH session. The
exemption check in this module can be satisfied only by a StaffContext
minted by authenticate_staff() from environment-held credentials. A
conversational claim of staff status ("I am staff", a claimed staff
code typed in chat) has NO effect on any check here; it is logged as
AF-TAMPER-EXEMPT-CLAIM and notified, and never unlocks anything.

PATTERN REUSE (design Sections 2.4 and 4, brief instruction): the
conversational layer reuses the DEL-17 two-strike pattern shipped in
75-drama-song-ad-factory/scripts/two_strike/ (state outside every skill
folder with a hard refusal to live inside one, silent staff notices,
shared extraction-marker vocabulary, hermetic selftest discipline). The
design governs where the two differ: Item 32 quarantines bytes-preserved
instead of wiping, uses the design Section 6.3 stub text, and, under
the owner's 2026-10-15 amendment, warns first for every conversational
and pattern trigger through the three-strike ladder (DEV-1 as
amended), rather than the two-strike module's flat count.

HONESTY LIMITS (design Section 9; these stay visible on purpose):
  * A client who owns their box has root. Skills are plain files with
    no encryption at rest. A determined owner can read everything,
    disable this guard, or wipe the local log. The guard defends the
    agent-mediated surface, casual browsing, and unattributed drift;
    it makes tampering detected, evidenced, and reported off-box at
    trigger time. It is NOT proof against the box's root user.
  * In the 999 shape, ordinary chat replies pass through no hook, so
    the D3 egress check cannot run on live chat text there; the
    judgment layer runs after the fact over stored transcripts
    (DEV-2).
  * In OpenClaw shapes, D3 on agent replies and D1 at the gateway need
    the gateway's outbound-inspection / tool-policy hook. That hook
    was NOT verified against the installed gateway version (design
    Section 9 point 3, UNVERIFIED). The functions here implement the
    checks; the wiring points are the PreToolUse hook shape (999) and
    the gateway policy layer (OpenClaw) once verified.
  * Locking does not recall content already extracted. The honest
    claim is detection and response; the egress rules shrink the
    window, they do not close it retroactively.

Exit codes (department discipline, gate_integrity_check.py):
  0 = pass / allowed / clean
  1 = violation found / blocked / refused (an incident may be recorded)
  2 = could not run (configuration fault; a GUARDFAULT, never a lock
      against the client for a staff provisioning mistake, design 2.3)
  3 = usage error

Stdlib only. No AI runs inside this module at runtime: the judgment
layer is a deterministic rubric evaluator over transcript exports,
modeled on intake_trace_check.py, exactly as that precedent works.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# Constants (design references in comments; tune only with the design)
# --------------------------------------------------------------------------

MANIFEST_NAME = "integrity-manifest.json"
LOCK_MARKER_NAME = ".tamper-locked"
STUB_VERSION_NAME = "skill-version.txt"

# Design Section 6.3(b): the stub SKILL.md is exactly this text, then the
# reference line. Nothing else: no instructions, no internal detail.
STUB_TEXT = "This skill is currently disabled. Please contact staff for assistance."

# The warning notice (design Section 6.6, as amended by the owner
# ruling of 2026-10-15, call F8): the client is told plainly that a
# strike was recorded and that Trevor was notified. No thresholds, no
# counting rules, no rule detail: naming the ladder's edges would
# teach them to the person probing them.
JUDGMENT_WARNING_TEXT = (
    "This conversation has been flagged for staff review. A strike "
    "has been recorded on your account, and Trevor has been "
    "notified.")

# Design Section 2.5: the watchdog runs on the existing 600 s cadence.
WATCHDOG_CADENCE_SECONDS = 600

# Design Section 3.4 / DEV-3: stale-lock age and the crashed-update grace.
STALE_LOCK_SECONDS = 30 * 60
UPDATE_GRACE_HOURS = 24

# Design Section 2.3: key rotation window, per the fleet key template
# precedent (sp-turn-ledger-keys.template.json uses 14 days).
KEY_ROTATION_WINDOW_DAYS = 14

# Design Section 4.2 D3: egress fires at 200 consecutive verbatim
# characters OR 3 matching shingles. Shingles are overlapping 8-word
# windows over normalized text (design Section 2.2: word windows).
EGRESS_VERBATIM_CHARS = 200
EGRESS_SHINGLE_MIN = 3
SHINGLE_WORDS = 8

# The three-strike ladder (owner ruling 2026-10-15; amendment
# Sections A2/B, calls F1/F5/F6): lockout is automatic at the third
# STANDING strike, counted per client across every guarded skill on
# the install. Strikes one and two are warnings only.
STRIKES_TO_LOCKOUT = 3

# Bulk mechanical dumping thresholds (amendment call F2, the split;
# the ruling leaves the values to the crew, to be set in the build
# and stated in the record; they are also stated in TAMPER-GUARD.md).
# A bulk event is not a conversational act at all, so it locks
# immediately through the Section 6 response, even on a first
# offense, while the act itself is denied like any other.
#   BULK_EGRESS_VERBATIM_CHARS: a single outbound payload carrying a
#     verbatim span of internal text at or above 2000 characters
#     (ten times the ordinary D3 threshold) is a mechanical dump of
#     sealed text, not a slipped quote.
BULK_EGRESS_VERBATIM_CHARS = 2000
#   BULK_GATED_ACTS_PER_SESSION: more than 10 denied gated source
#     acts (D1 trips: reads, copies, archives, or transmits of
#     in-scope source toward outside destinations) inside one
#     session is a scripted sweep, not a client fumbling with agent
#     tooling. The skill's own execution reads are allowed at the
#     gate and never counted. (The third bulk form, an archive
#     action over an in-scope tree, needs no number: the action
#     itself is the bulk form.)
BULK_GATED_ACTS_PER_SESSION = 10

# Trigger / event classes (design Sections 3.2 and 6.4).
CLS_INTEGRITY = "AF-TAMPER-INTEGRITY"
CLS_MANIFEST = "AF-TAMPER-MANIFEST"
CLS_EXTRACT = "AF-TAMPER-EXTRACT"
CLS_EXEMPT_CLAIM = "AF-TAMPER-EXEMPT-CLAIM"
CLS_GUARDFAULT = "AF-TAMPER-GUARDFAULT"
EV_UPDATE_INCOMPLETE = "UPDATE_INCOMPLETE"
EV_BASELINE_ADOPTED = "BASELINE_ADOPTED"
EV_REBASELINE = "REBASELINE"
EV_REINSTATEMENT = "REINSTATEMENT"
EV_GUARDFAULT = "GUARDFAULT"
# Design Section 2.3 requires every old-key acceptance to be audit
# logged; the design's class list has no name for that record, so this
# audit class is an implementation addition, flagged in the manifest.
EV_KEY_ACCEPTANCE = "KEY_ACCEPTANCE"
# The ladder's staff-resolution classes (owner ruling 2026-10-15;
# amendment B5 and call F3): a pardon REMOVES a strike, an allow
# VOIDS it. Both append records of these classes against the warning
# incident; neither edits or deletes the warning record itself.
EV_STRIKE_PARDON = "STRIKE_PARDON"
EV_STRIKE_ALLOW = "STRIKE_ALLOW"

# Park reason written for in-flight runs (design Section 6.3(d)).
PARK_REASON = "TAMPER_LOCKED"

# Built-in exclusions (design Section 3.3). The per-skill box-state
# paths and publish-time named files are ADDED to this list inside the
# signed manifest at generation time; the box can never extend it.
BUILTIN_EXCLUSIONS = [
    "__pycache__/**",
    "*.pyc",
    "*.bak-unify-*",
]

ENV_GUARD_HOME = "TAMPER_GUARD_HOME"
ENV_CLIENT_NAME = "TAMPER_GUARD_CLIENT_NAME"
ENV_KEYS_FILE = "TAMPER_GUARD_KEYS_FILE"
ENV_KEY = "TAMPER_GUARD_KEY"
ENV_KEY_ID = "TAMPER_GUARD_KEY_ID"
ENV_UPDATE_LOCK = "TAMPER_GUARD_UPDATE_LOCK_PATH"
DEFAULT_UPDATE_LOCK = "/tmp/openclaw-update.lock"  # update-skills.sh

_HERE = Path(__file__).resolve().parent
PATTERNS_PATH = _HERE / "tamper-guard-patterns.json"
SCOPE_PATH = _HERE / "tamper-guard-scope.json"
UPDATER_PATH = _HERE.parent / "update-skills.sh"


class GuardError(Exception):
    """Base error carrying a stable machine-readable code."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


class GuardConfigError(GuardError):
    """A staff-side provisioning fault (design Section 2.3).

    A configuration failure is a GUARD FAULT: it is reported to staff
    and the skill is NOT locked. A staff provisioning mistake must not
    lock a paying client as a tamperer.
    """


class Refusal(GuardError):
    """A staff-flow refusal (reinstatement / re-baseline preconditions)."""


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)


def _canonical(obj) -> bytes:
    """Canonical serialization: the intake_trace_check FIX-3 discipline
    (json.dumps sort_keys, tight separators), used for every digest and
    signature in this module."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split()


def shingles_for_text(text: str) -> set[str]:
    """Overlapping word-window shingle hashes (design Section 2.2).

    Returns SHA-256 hashes of normalized 8-word windows. Hashes, not
    text, are what the registry stores: the guard never builds a second
    readable copy of the sealed content."""
    words = _normalize_words(text)
    out = set()
    if len(words) < SHINGLE_WORDS:
        return out
    for i in range(len(words) - SHINGLE_WORDS + 1):
        window = " ".join(words[i:i + SHINGLE_WORDS])
        out.add(_sha256_bytes(window.encode("utf-8")))
    return out


def _path_matches(pattern: str, rel: str) -> bool:
    """Match a signed exclusion pattern against a relative POSIX path.

    Supports the design Section 3.3 shapes: exact paths, ``*.ext``
    suffixes at any depth, and ``dir/**`` subtree patterns."""
    if pattern.endswith("/**"):
        base = pattern[:-3]
        return rel == base or rel.startswith(base + "/")
    if "/" not in pattern:
        return fnmatch.fnmatch(rel.rsplit("/", 1)[-1], pattern)
    return fnmatch.fnmatch(rel, pattern)


def _is_excluded(rel: str, exclusions: list[str]) -> bool:
    return any(_path_matches(p, rel) for p in exclusions)


# --------------------------------------------------------------------------
# Fleet key handling (design Section 2.3; template discipline per
# Skill 51's sp-turn-ledger-keys.template.json: per-client/environment
# keys, current + previous, values only in the secrets store, key IDs
# safe to log, values never logged or committed)
# --------------------------------------------------------------------------

class KeyRing:
    def __init__(self, current_id: str, current_key: str,
                 previous_id: str | None = None,
                 previous_key: str | None = None,
                 rotation_started_at: str | None = None):
        self.current_id = current_id
        self.current_key = current_key
        self.previous_id = previous_id
        self.previous_key = previous_key
        self.rotation_started_at = rotation_started_at

    def sign(self, digest: str) -> str:
        return hmac.new(self.current_key.encode("utf-8"),
                        digest.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify(self, digest: str, signature: str, key_id: str) -> str:
        """Return 'current', 'previous', 'previous-expired', or 'invalid'.

        'previous' is returned only inside the bounded rotation window;
        after the window the previous key fails closed (design 2.3)."""
        if key_id == self.current_id:
            expected = hmac.new(self.current_key.encode("utf-8"),
                                digest.encode("utf-8"),
                                hashlib.sha256).hexdigest()
            return "current" if hmac.compare_digest(expected, signature) \
                else "invalid"
        if self.previous_id is not None and key_id == self.previous_id \
                and self.previous_key is not None:
            expected = hmac.new(self.previous_key.encode("utf-8"),
                                digest.encode("utf-8"),
                                hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                return "invalid"
            if self.rotation_started_at:
                started = _parse_iso(self.rotation_started_at)
                deadline = started + timedelta(
                    days=KEY_ROTATION_WINDOW_DAYS)
                if _now() > deadline:
                    return "previous-expired"
            return "previous"
        return "invalid"


def load_keyring(environ: dict | None = None) -> KeyRing:
    """Load the fleet tamper-guard key from the secrets environment.

    Raises GuardConfigError on any provisioning problem; callers turn
    that into a GUARDFAULT record and DO NOT lock (design Section 2.3).
    Key VALUES are read here and never logged, printed, or stored."""
    env = os.environ if environ is None else environ
    keys_file = env.get(ENV_KEYS_FILE)
    if keys_file:
        try:
            data = json.loads(Path(keys_file).read_text(encoding="utf-8"))
            current = data["current"]
            previous = data.get("previous") or {}
            return KeyRing(
                current_id=current["key_id"],
                current_key=current["key"],
                previous_id=previous.get("key_id"),
                previous_key=previous.get("key"),
                rotation_started_at=data.get("rotation_started_at"),
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise GuardConfigError(
                "KEYS_FILE_UNUSABLE",
                f"tamper-guard keys file unusable: {exc}") from exc
    key = env.get(ENV_KEY)
    if key:
        return KeyRing(current_id=env.get(ENV_KEY_ID, "env-current"),
                       current_key=key)
    raise GuardConfigError(
        "KEY_NOT_PROVISIONED",
        "no tamper-guard fleet key in the environment "
        f"({ENV_KEYS_FILE} / {ENV_KEY} unset): staff provisioning fault")


# --------------------------------------------------------------------------
# Staff authentication (design Section 5). A StaffContext can be minted
# ONLY here, ONLY from environment-held credentials. Nothing in the
# conversational path accepts staff status from message content.
# --------------------------------------------------------------------------

class StaffContext:
    """An authenticated staff context. Constructed only by
    authenticate_staff(); the conversational checks test
    ``isinstance(x, StaffContext)`` and nothing else."""

    def __init__(self, actor: str, method: str):
        self.actor = actor          # credential identifier, never a secret
        self.method = method        # secrets-token | cc-token | ssh

    def __repr__(self):  # never carries a credential value
        return f"StaffContext(actor={self.actor!r}, method={self.method!r})"


def authenticate_staff(method: str, presented: str | None = None,
                       environ: dict | None = None) -> StaffContext | None:
    """Verify a staff authentication attempt through an authenticated
    channel. Returns a StaffContext on success, None on failure.

    Channels (design Section 5, any one):
      secrets-token: the staff credential held in the box secrets store,
        presented by staff tooling and verified against the secrets env.
      cc-token:      the Command Center operator channel's fail-closed
        bearer token, verified against the secrets env.
      ssh:           a staff SSH session invoking the guard directly;
        the session wrapper exports TAMPER_GUARD_STAFF_SSH=1 only after
        SSH authentication. A client chat session never holds any of
        these, and nothing said in conversation reaches this function.
    """
    env = os.environ if environ is None else environ
    if method == "secrets-token":
        expected = env.get("TAMPER_GUARD_STAFF_TOKEN")
        actor = env.get("TAMPER_GUARD_STAFF_ACTOR", "staff-token")
        if expected and presented and hmac.compare_digest(
                expected, presented):
            return StaffContext(actor=actor, method=method)
        return None
    if method == "cc-token":
        expected = env.get("TAMPER_GUARD_CC_TOKEN")
        actor = env.get("TAMPER_GUARD_CC_ACTOR", "command-center-operator")
        if expected and presented and hmac.compare_digest(
                expected, presented):
            return StaffContext(actor=actor, method=method)
        return None
    if method == "ssh":
        if env.get("TAMPER_GUARD_STAFF_SSH") == "1":
            return StaffContext(
                actor=env.get("TAMPER_GUARD_STAFF_ACTOR",
                              env.get("USER", "staff-ssh")),
                method=method)
        return None
    return None


# --------------------------------------------------------------------------
# Guard state (design Section 2.4): everything the guard keeps lives
# OUTSIDE every guarded tree:
#   $TAMPER_GUARD_HOME or $HOME/.openclaw/security/tamper-guard/
#     registry.json     scope installs, digests, windows, lock state
#     incidents.jsonl   append-only incident log (design Section 6.4)
#     heartbeat.jsonl   scheduled-verification heartbeat (Section 6.5)
#     notify-outbox.jsonl  file-queue notification fallback (Section 6.2)
#     quarantine/       bytes-preserved locked trees (Section 6.3)
#     shingles/         per-skill egress shingle hashes (Section 4.2 D3)
# Following the two-strike precedent, a state root inside a skill tree
# is REFUSED: guard state inside a sealed tree would be sealed itself
# and could be wiped or forged with the tree it watches.
# --------------------------------------------------------------------------

def default_guard_home() -> Path:
    override = os.environ.get(ENV_GUARD_HOME)
    if override:
        return Path(override)
    return Path.home() / ".openclaw" / "security" / "tamper-guard"


def _assert_state_outside_trees(root: Path) -> None:
    resolved = root.resolve()
    parts = resolved.parts
    if "skills" in parts:
        raise GuardError("STATE_ROOT_INSIDE_SKILLS_ROOT",
                         f"guard state root is under a skills dir: {root}")
    if re.search(r"(^|/)\d\d-[^/]+$", str(resolved)):
        raise GuardError("STATE_ROOT_INSIDE_SKILL_FOLDER",
                         f"guard state root is a skill folder: {root}")
    parent = resolved
    while parent != parent.parent:
        if (parent / "SKILL.md").is_file():
            raise GuardError(
                "STATE_ROOT_INSIDE_SKILL_FOLDER",
                f"guard state root is inside a skill tree: {root}")
        parent = parent.parent


class Guard:
    def __init__(self, home: Path | None = None, environ: dict | None = None):
        self.home = Path(home) if home else default_guard_home()
        _assert_state_outside_trees(self.home)
        self.environ = os.environ if environ is None else environ
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "quarantine").mkdir(exist_ok=True)
        (self.home / "shingles").mkdir(exist_ok=True)
        self._registry_path = self.home / "registry.json"
        self._incidents_path = self.home / "incidents.jsonl"
        self._heartbeat_path = self.home / "heartbeat.jsonl"
        self._outbox_path = self.home / "notify-outbox.jsonl"

    # -- registry ------------------------------------------------------
    def registry(self) -> dict:
        if self._registry_path.is_file():
            try:
                return json.loads(
                    self._registry_path.read_text(encoding="utf-8"))
            except ValueError:
                return {"version": 1, "trees": {}}
        return {"version": 1, "trees": {}}

    def save_registry(self, reg: dict) -> None:
        tmp = self._registry_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(reg, indent=1, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, self._registry_path)

    def tree_entry(self, slug: str) -> dict:
        return self.registry().setdefault("trees", {}).get(slug, {})

    def update_tree_entry(self, slug: str, **fields) -> None:
        reg = self.registry()
        entry = reg.setdefault("trees", {}).setdefault(slug, {})
        entry.update(fields)
        self.save_registry(reg)

    # -- incident log (append-only JSONL, design Section 6.4) ---------
    def append_record(self, record: dict) -> dict:
        with open(self._incidents_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def records(self) -> list[dict]:
        if not self._incidents_path.is_file():
            return []
        out = []
        for line in self._incidents_path.read_text(
                encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def find_record(self, incident_id: str) -> dict | None:
        for rec in self.records():
            if rec.get("incident_id") == incident_id:
                return rec
        return None

    def new_incident_id(self) -> str:
        stamp = _now().strftime("%Y%m%dT%H%M%S")
        return f"TG-{stamp}-{secrets.token_hex(3).upper()}"

    def box_identity(self) -> dict:
        return {
            "hostname": socket.gethostname() or "unknown-host",
            "shape": self.environ.get("TAMPER_GUARD_SHAPE", "unspecified"),
        }

    def client_name(self) -> str | None:
        """The client's name as recorded at install time (owner
        ruling 2026-10-15, call F4). The installer records it in the
        guard registry under the top-level "client_name" key when the
        install is made, and the TAMPER_GUARD_CLIENT_NAME environment
        value, when set, takes precedence (it is the operator's
        override on a box whose registry predates the field).
        Notifications carry this name so Trevor reads which client
        was warned in plain terms, not a hostname he must translate.
        When neither source has a value there is no name to report:
        records carry None here and the box identity stands, exactly
        as before this field existed. A missing name never blocks a
        record, a notification, or a strike."""
        name = self.environ.get(ENV_CLIENT_NAME)
        if name:
            return name
        stored = self.registry().get("client_name")
        if isinstance(stored, str) and stored:
            return stored
        return None

    def base_record(self, slug: str, trigger_class: str,
                    evidence: dict, action_taken: str,
                    actor: str = "tamper-guard") -> dict:
        return {
            "incident_id": self.new_incident_id(),
            "ts": _iso(_now()),
            "box": self.box_identity(),
            "client": self.client_name(),
            "skill": slug,
            "trigger_class": trigger_class,
            "evidence": evidence,
            "action_taken": action_taken,
            "actor": actor,
        }

    # -- the three-strike ladder ledger (owner ruling 2026-10-15) ----
    # The incident log stays the append-only evidence; nothing below
    # edits or deletes a log record. The ledger is a derived index
    # over the log, kept in the registry's top-level "strikes" list
    # beside the per-skill tree entries (the per-skill
    # judgment_warnings field stays as the judgment layer's evidence
    # index, as the amendment's B5 keeps it). One entry per strike:
    # the warning incident id, the skill the strike arose on, the
    # trigger kind, the session, and the resolution state
    # (standing | pardoned | voided). The standing count is PER
    # CLIENT across every guarded skill on this install (call F6):
    # probes against two different skills add up to the same
    # lockout. Strikes never expire on their own (call F5); the only
    # ways off the ladder are staff pardon and staff allow.

    def record_strike(self, incident_id: str, slug: str, kind: str,
                      session_id: str = "") -> dict:
        reg = self.registry()
        entry = {"incident_id": incident_id, "skill": slug,
                 "kind": kind, "session_id": session_id,
                 "recorded_at": _iso(_now()), "state": "standing"}
        reg.setdefault("strikes", []).append(entry)
        self.save_registry(reg)
        return entry

    def standing_strikes(self) -> list[dict]:
        return [e for e in self.registry().get("strikes", [])
                if e.get("state") == "standing"]

    def standing_strike_count(self) -> int:
        return len(self.standing_strikes())

    def strike_sessions(self, kind: str) -> set[str]:
        """Sessions already holding a strike of one trigger kind,
        standing or resolved (call F5: one strike per session for a
        continuous attempt; a pardon or allow does not reopen the
        same session's one strike)."""
        return {e.get("session_id") for e in self.registry().get(
            "strikes", [])
            if e.get("kind") == kind and e.get("session_id")}

    def note_gated_act(self, session_id: str) -> int:
        """Count one denied D1 act toward its session's bulk tally
        (call F2) and return the session's new total. Only acts the
        gate DENIED reach this counter: the skill's own execution
        reads are allowed earlier in the gate and never counted, and
        acts already answered by a lockout short-circuit before
        counting."""
        if not session_id:
            return 0
        reg = self.registry()
        acts = reg.setdefault("gated_acts", {})
        acts[session_id] = int(acts.get(session_id, 0)) + 1
        self.save_registry(reg)
        return acts[session_id]

    def resolve_strike(self, incident_id: str,
                       resolution: str) -> bool:
        """Mark a strike pardoned or voided in the ledger. The
        incident-log record is never edited (the log is append-only);
        the resolution lives here and in its own appended record."""
        reg = self.registry()
        for entry in reg.get("strikes", []):
            if entry.get("incident_id") == incident_id:
                entry["state"] = resolution
                entry["resolved_at"] = _iso(_now())
                self.save_registry(reg)
                return True
        return False

    # -- staff notification (design Section 6.2) ------------------------
    def notify_staff(self, record: dict) -> dict:
        """Notify staff off-box through the fleet's existing transports,
        following Skill 51's skill.json notify_transport precedent:
        gateway by default, file-queue fallback, env override command.
        This module's transports, in order:
          1. TAMPER_GUARD_NOTIFY_CMD (override command; JSON on stdin)
          2. TAMPER_GUARD_GATEWAY_CMD (gateway command; JSON on stdin)
          3. file queue at notify-outbox.jsonl (fallback; always works)
        Returns {"transport": ..., "ok": bool}. Notification leaving the
        box at trigger time is a design requirement, and the fallback
        guarantees a staff-visible copy even when no gateway is wired.
        """
        payload = json.dumps(record, sort_keys=True)
        for env_name, label in (("TAMPER_GUARD_NOTIFY_CMD", "override-cmd"),
                                ("TAMPER_GUARD_GATEWAY_CMD", "gateway")):
            cmd = self.environ.get(env_name)
            if cmd:
                try:
                    proc = subprocess.run(
                        cmd, shell=True, input=payload.encode("utf-8"),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, timeout=15)
                    if proc.returncode == 0:
                        return {"transport": label, "ok": True}
                except (OSError, subprocess.SubprocessError):
                    pass
        with open(self._outbox_path, "a", encoding="utf-8") as fh:
            fh.write(payload + "\n")
        return {"transport": "file-queue", "ok": True}

    def record_and_notify(self, slug: str, trigger_class: str,
                          evidence: dict, action_taken: str,
                          actor: str = "tamper-guard",
                          incident_id: str | None = None) -> dict:
        """Design Section 6 order: the incident is recorded FIRST,
        then staff are notified, then anything else happens."""
        record = self.base_record(slug, trigger_class, evidence,
                                  action_taken, actor=actor)
        if incident_id:
            record["incident_id"] = incident_id
        record["notification"] = {"transport": "pending", "ok": False}
        self.append_record(record)  # 6.1 RECORD FIRST, before anything moves
        note = self.notify_staff(record)  # 6.2 NOTIFY STAFF off-box
        record["notification"] = note
        return record

    # -- shingles (design Sections 2.2 and 4.2 D3) ----------------------
    def store_shingles(self, slug: str, shingles: set[str]) -> None:
        path = self.home / "shingles" / f"{slug}.json"
        path.write_text(json.dumps(sorted(shingles)), encoding="utf-8")

    def load_shingles(self, slug: str) -> set[str]:
        path = self.home / "shingles" / f"{slug}.json"
        if not path.is_file():
            return set()
        return set(json.loads(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------
# Signed allow-list sourcing (design Section 3.3): the box-state paths
# come from update-skills.sh's oc_skill_box_state_paths() itself, never
# from a second list that can drift. The function is a per-skill case
# statement whose branch prints one path per line, either with echo
# (one path) or with printf (a format string, then one quoted path per
# line); this parser reads the paths out of whichever emitter form a
# branch uses, so an updater entry that grows a second path, or moves
# from echo to printf, is still sourced from the updater itself.
# --------------------------------------------------------------------------

def box_state_paths_for(skill_folder_name: str,
                        updater_path: Path | None = None) -> list[str]:
    path = updater_path or UPDATER_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    match = re.search(
        r"oc_skill_box_state_paths\(\)\s*\{(.*?)\n\}", text, re.DOTALL)
    if not match:
        return []
    branch = re.search(
        re.escape(skill_folder_name) + r"\)\s*(.*?);;",
        match.group(1), re.DOTALL)
    if not branch:
        return []
    command = branch.group(1)
    if re.search(r"\bprintf\b", command):
        # printf '<format>' "path" ["path" ...]: the first quoted
        # string is the format, every later quoted string is one
        # printed path, in argument order.
        quoted = re.findall(r"\"([^\"]+)\"|'([^']+)'", command)
        strings = [double or single for double, single in quoted]
        if strings and "%" in strings[0]:
            strings = strings[1:]
        return strings
    # echo form: the historical behavior, unchanged. The branch prints
    # its one path as the first double-quoted string after echo.
    entry = re.search(r"echo\s+\"([^\"]+)\"", command)
    return [entry.group(1)] if entry else []


# --------------------------------------------------------------------------
# The integrity manifest (design Section 2). One manifest at the root of
# each sealed tree. The signature is HMAC-SHA256 over manifest_digest
# with the fleet tamper-guard key. The manifest file itself, and any
# paths matched by its signed exclusions, are not covered entries.
# --------------------------------------------------------------------------

def _tree_version(tree: Path) -> str:
    version_file = tree / STUB_VERSION_NAME
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    manifest_file = tree / "connection-manifest.json"
    if manifest_file.is_file():
        try:
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("version"):
                return str(data["version"])
        except ValueError:
            pass
    return "unknown"


def collect_tree_files(tree: Path, exclusions: list[str]) -> dict:
    """Walk a tree and return ({rel: entry}, shingle set) for every
    covered file: everything except the manifest itself and paths
    matched by the signed exclusions."""
    files: dict[str, dict] = {}
    shingles: set[str] = set()
    for path in sorted(tree.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(tree).as_posix()
        if rel == MANIFEST_NAME:
            continue
        if _is_excluded(rel, exclusions):
            continue
        data = path.read_bytes()
        files[rel] = {
            "sha256": _sha256_bytes(data),
            "size": len(data),
            "executable": bool(os.access(path, os.X_OK)
                               and path.stat().st_mode & 0o111),
        }
        if len(data) <= 4_000_000:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = ""
            if text:
                shingles |= shingles_for_text(text)
    return files, shingles


def manifest_digest_of(manifest_body: dict) -> str:
    """SHA-256 over the canonical serialization of the manifest body
    (design Section 2.1: everything except the signature; the digest
    field itself is necessarily excluded, or the value could never
    be computed)."""
    body = {k: v for k, v in manifest_body.items()
            if k not in ("signature", "manifest_digest")}
    return _sha256_bytes(_canonical(body))


def build_manifest(tree: Path, slug: str, keyring: KeyRing | None,
                   extra_exclusions: list[str] | None = None,
                   generated_by: str = "tamper_guard.py generate",
                   source_commit: str = "") -> tuple[dict, set[str]]:
    """Build (and, when a keyring is given, sign) the manifest for a
    tree. Exclusions = built-ins + the skill's SKILL-BOX-STATE paths
    (design Section 3.3) + publish-time named extras."""
    exclusions = list(BUILTIN_EXCLUSIONS)
    exclusions += box_state_paths_for(tree.name)
    for extra in (extra_exclusions or []):
        if extra not in exclusions:
            exclusions.append(extra)
    files, shingles = collect_tree_files(tree, exclusions)
    body = {
        "skill": slug,
        "version": _tree_version(tree),
        "source_commit": source_commit,
        "generated_at": _iso(_now()),
        "generated_by": generated_by,
        "key_id": keyring.current_id if keyring else None,
        "files": files,
        "exclusions": sorted(exclusions),
    }
    body["manifest_digest"] = manifest_digest_of(body)
    if keyring:
        body["signature"] = keyring.sign(body["manifest_digest"])
    else:
        # Repo-committed form (design Section 2.2 mechanics note in
        # TAMPER-GUARD.md): PR CI holds no key, so the committed
        # manifest is digest-sealed only; the fleet key signs it at
        # publish/install time, and from registration on, the checker
        # requires the signature.
        body["signature"] = None
    return body, shingles


def write_manifest(tree: Path, manifest: dict) -> Path:
    path = tree / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True),
                    encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Verification (design Sections 2.5, 2.6, 3.1, 3.4)
# --------------------------------------------------------------------------

def compare_tree(tree: Path, manifest: dict) -> list[dict]:
    """The byte-exact divergence test (design Section 3.1 steps 3-5),
    pure: no state, no side effects. Returns divergence evidence rows:
    {path, kind: CONTENT|MISSING_FILE|EXTRA_FILE, expected_sha256,
    actual_sha256, expected_size, actual_size}."""
    exclusions = manifest.get("exclusions", [])
    declared = manifest.get("files", {})
    divergences: list[dict] = []
    for rel, entry in sorted(declared.items()):
        path = tree / rel
        if not path.is_file():
            divergences.append({
                "path": rel, "kind": "MISSING_FILE",
                "expected_sha256": entry["sha256"], "actual_sha256": None,
                "expected_size": entry["size"], "actual_size": None})
            continue
        actual_sha = _sha256_file(path)
        actual_size = path.stat().st_size
        if actual_sha != entry["sha256"] or actual_size != entry["size"]:
            divergences.append({
                "path": rel, "kind": "CONTENT",
                "expected_sha256": entry["sha256"],
                "actual_sha256": actual_sha,
                "expected_size": entry["size"],
                "actual_size": actual_size})
    for path in sorted(tree.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(tree).as_posix()
        if rel == MANIFEST_NAME or rel in declared:
            continue
        if _is_excluded(rel, exclusions):
            continue
        divergences.append({
            "path": rel, "kind": "EXTRA_FILE",
            "expected_sha256": None,
            "actual_sha256": _sha256_file(path),
            "expected_size": None,
            "actual_size": path.stat().st_size})
    return divergences


def manifest_signature_status(manifest: dict, keyring: KeyRing) -> str:
    """Design Sections 3.1 steps 1-2 and 2.6, pure.
    Returns: unsigned | digest-mismatch | invalid | previous-expired |
    previous | current."""
    signature = manifest.get("signature")
    if not signature:
        return "unsigned"
    if manifest_digest_of(manifest) != manifest.get("manifest_digest"):
        return "digest-mismatch"
    verdict = keyring.verify(manifest["manifest_digest"], signature,
                             manifest.get("key_id") or "")
    return {"current": "current", "previous": "previous",
            "previous-expired": "previous-expired"}.get(verdict, "invalid")


def update_lock_state(lock_path: Path | None = None,
                      environ: dict | None = None) -> str:
    """Read the updater's lock (update-skills.sh acquires
    /tmp/openclaw-update.lock as the FIRST call in main()). Returns:
      held    - an updater holds it now (flock held, or live pid dir)
      stale   - present but abandoned: pid holder dead, or the lock is
                older than STALE_LOCK_SECONDS (design Section 3.4)
      absent  - no lock present
    The lock path is injectable for hermetic tests and box shapes."""
    env = os.environ if environ is None else environ
    path = lock_path or Path(env.get(ENV_UPDATE_LOCK, DEFAULT_UPDATE_LOCK))
    if not path.exists():
        return "absent"
    if path.is_dir():
        pid_file = path / "pid"
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            return "held"
        except (OSError, ValueError):
            return "stale"
    # flock form: the file persists after release, so state is whether
    # a non-blocking flock succeeds; age breaks the tie for stale.
    try:
        import fcntl
        fd = os.open(path, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            held = False
        except OSError:
            held = True
        finally:
            os.close(fd)
    except OSError:
        held = False
    if held:
        return "held"
    age = time.time() - path.stat().st_mtime
    return "stale" if age > STALE_LOCK_SECONDS else "absent"


class Checker:
    """The full verification run for one tree: signature, registry,
    byte comparison, update window, grace, baseline adoption, and the
    response. Constructed per run point so each caller (load check,
    watchdog, post-roll) gets identical semantics (design 2.5)."""

    def __init__(self, guard: Guard, keyring: KeyRing | None = None,
                 key_error: GuardConfigError | None = None,
                 install_shape: str = "openclaw",
                 baseline_adoption_allowed: bool = True,
                 engine_marker_dir: Path | None = None):
        self.guard = guard
        self._keyring = keyring
        self._key_error = key_error
        self.install_shape = install_shape
        self.baseline_adoption_allowed = baseline_adoption_allowed
        self.engine_marker_dir = engine_marker_dir

    def keyring(self) -> KeyRing:
        if self._key_error is not None:
            raise self._key_error
        if self._keyring is None:
            self._keyring = load_keyring(self.guard.environ)
        return self._keyring

    # -- the response, design Section 6 in its exact order -------------
    def respond_lockout(self, tree: Path, slug: str, trigger_class: str,
                        evidence: dict, sub_rule: str | None = None,
                        defer_stub: bool = False) -> dict:
        """6.1 record FIRST, 6.2 notify, 6.3 lock out and stub.
        With defer_stub (DEV-2, conversational trigger in the harness
        shape) the record and notification still happen NOW, tool
        denial is immediate via the pending-lock entry, and the
        quarantine/stub is applied by session_start()."""
        ev = dict(evidence)
        if sub_rule:
            ev["sub_rule"] = sub_rule
        record = self.guard.record_and_notify(
            slug, trigger_class, ev, "locked")
        incident_id = record["incident_id"]
        if defer_stub:
            self.guard.update_tree_entry(
                slug, pending_lock={"incident_id": incident_id,
                                    "trigger_class": trigger_class,
                                    "sub_rule": sub_rule,
                                    "recorded_at": _iso(_now())})
            return {"locked": True, "pending": True,
                    "incident_id": incident_id,
                    "user_text": stub_user_text(incident_id)}
        self._apply_lock(tree, slug, incident_id, trigger_class)
        return {"locked": True, "pending": False,
                "incident_id": incident_id,
                "user_text": stub_user_text(incident_id)}

    def respond_strike(self, tree: Path, slug: str, evidence: dict,
                       sub_rule: str, session_id: str = "",
                       defer_stub: bool = False) -> dict:
        """The ladder step for a conversational or pattern strike
        (owner ruling 2026-10-15; amendment Sections A2/B2/B3 and
        calls F1/F5/F6).

        The strike is recorded FIRST and staff are notified at
        warning time, through the same record-and-notify path every
        guard event uses; the notification names the client (F4) and
        asks for Trevor's call: allow the behavior, or remove the
        strike (A3). The client sees the strike notice (F8). Strikes
        one and two carry no further consequence (F1). One strike per
        session per trigger kind for a continuous attempt (F5): a
        repeat of a kind inside a session that already holds that
        kind's strike is refused and recorded, but records no second
        strike. When the strike just recorded is the third STANDING
        strike on the client's record, counted across every guarded
        skill on the install (F6), the struck skill locks out
        automatically through respond_lockout above, unchanged
        (deferred to the next session start in the harness shape,
        DEV-2)."""
        guard = self.guard
        ev = dict(evidence)
        ev["sub_rule"] = sub_rule
        if session_id and session_id in guard.strike_sessions(sub_rule):
            record = guard.record_and_notify(
                slug, CLS_EXTRACT,
                {**ev, "note": "repeat of a strike kind already "
                               "recorded for this session; refused, "
                               "no second strike (F5: one strike per "
                               "session for a continuous attempt)"},
                "warned")
            return {"action": "warn", "strike_recorded": False,
                    "standing_strikes": guard.standing_strike_count(),
                    "incident_id": record["incident_id"],
                    "user_text": JUDGMENT_WARNING_TEXT}
        record = guard.record_and_notify(slug, CLS_EXTRACT, ev,
                                         "warned")
        guard.record_strike(record["incident_id"], slug, sub_rule,
                            session_id)
        standing = guard.standing_strike_count()
        if standing >= STRIKES_TO_LOCKOUT:
            outcome = self.respond_lockout(
                tree, slug, CLS_EXTRACT,
                {**ev, "strike_incident": record["incident_id"],
                 "standing_strikes": standing,
                 "note": "third standing strike on the client's "
                         "record, counted per client across guarded "
                         "skills; automatic lockout (F6)"},
                sub_rule=sub_rule, defer_stub=defer_stub)
            return {"action": "lock", "strike_recorded": True,
                    "standing_strikes": standing,
                    "strike_incident_id": record["incident_id"],
                    **outcome}
        return {"action": "warn", "strike_recorded": True,
                "standing_strikes": standing,
                "incident_id": record["incident_id"],
                "user_text": JUDGMENT_WARNING_TEXT}

    def _apply_lock(self, tree: Path, slug: str, incident_id: str,
                    trigger_class: str) -> None:
        guard = self.guard
        version = _tree_version(tree)
        # 6.3(a): move the tree, bytes preserved, to off-tree
        # quarantine. Nothing is deleted; quarantined bytes are
        # evidence and are never executed again.
        dest = guard.home / "quarantine" / slug / incident_id
        dest.parent.mkdir(parents=True, exist_ok=True)
        if tree.exists():
            shutil.move(str(tree), str(dest))
        # 6.3(b): the stub tree: same folder name, ONLY the stub
        # SKILL.md (stub text + reference line), the version file, and
        # the lock marker. No scripts, no entry points.
        tree.mkdir(parents=True, exist_ok=True)
        (tree / "SKILL.md").write_text(
            STUB_TEXT + f"\nReference: {incident_id}\n", encoding="utf-8")
        (tree / STUB_VERSION_NAME).write_text(version + "\n",
                                              encoding="utf-8")
        (tree / LOCK_MARKER_NAME).write_text(json.dumps({
            "incident_id": incident_id, "ts": _iso(_now()),
            "trigger_class": trigger_class}, indent=1), encoding="utf-8")
        # 6.3(c): the engine disable marker, naming the skill only.
        if self.engine_marker_dir:
            write_engine_disable_marker(self.engine_marker_dir, slug,
                                        incident_id)
        guard.update_tree_entry(slug, locked_incident=incident_id,
                                pending_lock=None)

    def apply_pending_lock(self, tree: Path, slug: str) -> dict | None:
        """DEV-2: land a deferred conversational lock at session start."""
        entry = self.guard.tree_entry(slug)
        pending = entry.get("pending_lock")
        if not pending:
            return None
        incident_id = pending["incident_id"]
        self._apply_lock(tree, slug, incident_id,
                         pending.get("trigger_class", CLS_EXTRACT))
        self.guard.append_record({
            "incident_id": incident_id, "ts": _iso(_now()),
            "box": self.guard.box_identity(), "skill": slug,
            "trigger_class": pending.get("trigger_class", CLS_EXTRACT),
            "evidence": {"phase": "session_start",
                         "note": "DEV-2: deferred conversational lock "
                                 "applied at session start"},
            "action_taken": "locked", "actor": "tamper-guard"})
        return {"incident_id": incident_id,
                "user_text": stub_user_text(incident_id)}

    # -- the verification run -------------------------------------------
    def verify(self, tree: Path, slug: str) -> dict:
        """Returns a verdict dict: {verdict, slug, ...}. Verdicts:
        OK | LOCKED | UPDATE_IN_PROGRESS | UPDATE_INCOMPLETE |
        BASELINE_ADOPTED | GUARDFAULT | LOCKED_OUT (this run locked)."""
        guard = self.guard
        entry = guard.tree_entry(slug)
        if (tree / LOCK_MARKER_NAME).is_file() or entry.get(
                "locked_incident"):
            return {"verdict": "LOCKED", "slug": slug,
                    "incident_id": entry.get("locked_incident")}
        if not tree.is_dir():
            outcome = self.respond_lockout(
                tree, slug, CLS_INTEGRITY,
                {"divergences": [{"path": ".", "kind": "MISSING_TREE"}]})
            return {"verdict": "LOCKED_OUT", "slug": slug, **outcome}

        lock_state = update_lock_state(environ=guard.environ)
        if lock_state == "held":
            # Design 3.4: inside a verified update window the checker
            # returns UPDATE_IN_PROGRESS; no incident, no lockout.
            guard.update_tree_entry(slug,
                                    update_window_opened_at=_iso(_now()))
            return {"verdict": "UPDATE_IN_PROGRESS", "slug": slug}

        try:
            keyring = self.keyring()
        except GuardConfigError as exc:
            # Design 2.3: a staff provisioning fault is a GUARD FAULT,
            # reported to staff; the skill is NOT locked.
            record = guard.record_and_notify(
                slug, CLS_GUARDFAULT,
                {"fault": exc.code, "detail": str(exc)}, "none")
            return {"verdict": "GUARDFAULT", "slug": slug,
                    "incident_id": record["incident_id"]}

        manifest_path = tree / MANIFEST_NAME
        if not manifest_path.is_file():
            return self._manifest_missing(tree, slug, keyring)

        try:
            manifest = json.loads(
                manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return self._divergence(tree, slug, CLS_MANIFEST,
                                    {"fault": "MANIFEST_UNPARSEABLE",
                                     "detail": str(exc)}, lock_state)

        status = manifest_signature_status(manifest, keyring)
        if status == "unsigned":
            if entry.get("manifest_digest"):
                # Registered installs are signed at install; an
                # unsigned manifest here was swapped in (design 2.6).
                return self._divergence(
                    tree, slug, CLS_MANIFEST,
                    {"fault": "MANIFEST_UNSIGNED_AFTER_REGISTRATION"},
                    lock_state)
            # First contact with a repo-shipped manifest: verify the
            # tree against it, then sign at install and register
            # (design 2.2 install-time rule; see TAMPER-GUARD.md).
            divergences = compare_tree(tree, manifest)
            if divergences:
                return self._divergence(tree, slug, CLS_INTEGRITY,
                                        {"divergences": divergences},
                                        lock_state)
            manifest["key_id"] = keyring.current_id
            manifest["signature"] = keyring.sign(
                manifest["manifest_digest"])
            write_manifest(tree, manifest)
            guard.update_tree_entry(
                slug, manifest_digest=manifest["manifest_digest"],
                tree=str(tree))
            _, shingles = collect_tree_files(
                tree, manifest.get("exclusions", []))
            guard.store_shingles(slug, shingles)
            return {"verdict": "OK", "slug": slug,
                    "note": "signed-at-install"}
        if status in ("digest-mismatch", "invalid", "previous-expired"):
            return self._divergence(
                tree, slug, CLS_MANIFEST,
                {"fault": "MANIFEST_SIGNATURE_" + status.upper().replace(
                    "-", "_"),
                 "key_id": manifest.get("key_id")}, lock_state)
        if status == "previous":
            # Old-key acceptance inside the rotation window is audit
            # logged on every acceptance (design Section 2.3).
            guard.append_record(guard.base_record(
                slug, EV_KEY_ACCEPTANCE,
                {"key_id": manifest.get("key_id"),
                 "note": "previous key accepted inside rotation window"},
                "none"))
        registered = entry.get("manifest_digest")
        if registered and registered != manifest.get("manifest_digest"):
            return self._divergence(
                tree, slug, CLS_MANIFEST,
                {"fault": "MANIFEST_SWAPPED",
                 "registered_digest": registered,
                 "presented_digest": manifest.get("manifest_digest")},
                lock_state)
        if not registered:
            guard.update_tree_entry(
                slug, manifest_digest=manifest.get("manifest_digest"),
                tree=str(tree))

        divergences = compare_tree(tree, manifest)
        if divergences:
            return self._divergence(tree, slug, CLS_INTEGRITY,
                                    {"divergences": divergences},
                                    lock_state)
        if entry.get("update_window_opened_at"):
            guard.update_tree_entry(slug, update_window_opened_at=None)
        grace = entry.get("grace")
        if grace:
            guard.update_tree_entry(slug, grace=None)
            guard.append_record(guard.base_record(
                slug, EV_UPDATE_INCOMPLETE,
                {"resolution": "tree verifies after crashed update",
                 "grace_incident": grace.get("incident_id")}, "none"))
        return {"verdict": "OK", "slug": slug}

    def _manifest_missing(self, tree: Path, slug: str,
                          keyring: KeyRing) -> dict:
        entry = self.guard.tree_entry(slug)
        if entry.get("manifest_digest"):
            # The install WAS sealed; a missing manifest now is the
            # named attack TP2 (design Sections 2.6 and 8).
            return self._divergence(
                tree, slug, CLS_MANIFEST,
                {"fault": "MANIFEST_MISSING"}, "absent")
        if self.baseline_adoption_allowed:
            # DEV-4: a pre-guard install adopts a signed baseline from
            # its installed tree on first run, recorded and notified,
            # instead of locking on day one.
            manifest, shingles = build_manifest(
                tree, slug, keyring,
                generated_by="tamper_guard.py DEV-4 baseline adoption")
            write_manifest(tree, manifest)
            self.guard.store_shingles(slug, shingles)
            record = self.guard.record_and_notify(
                slug, EV_BASELINE_ADOPTED,
                {"manifest_digest": manifest["manifest_digest"],
                 "files_sealed": len(manifest["files"]),
                 "note": "DEV-4: pre-guard install; baseline adopted "
                         "from the installed tree"}, "none")
            self.guard.update_tree_entry(
                slug, manifest_digest=manifest["manifest_digest"],
                tree=str(tree))
            return {"verdict": "BASELINE_ADOPTED", "slug": slug,
                    "incident_id": record["incident_id"]}
        return self._divergence(tree, slug, CLS_MANIFEST,
                                {"fault": "MANIFEST_MISSING"}, "absent")

    def _divergence(self, tree: Path, slug: str, trigger_class: str,
                    evidence: dict, lock_state: str) -> dict:
        """DEV-3 routing: divergence with crashed-update evidence does
        not lock inside its one grace window; the event is recorded
        and notified immediately either way (design Section 3.4)."""
        entry = self.guard.tree_entry(slug)
        crashed = lock_state == "stale" or bool(
            entry.get("update_window_opened_at"))
        if crashed:
            grace = entry.get("grace")
            if grace is None:
                record = self.guard.record_and_notify(
                    slug, EV_UPDATE_INCOMPLETE,
                    {**evidence,
                     "note": "DEV-3: crashed update suspected; 24 h "
                             "grace opened; staff notified now, the "
                             "lock waits for the grace close"},
                    "none")
                closes = _now() + timedelta(hours=UPDATE_GRACE_HOURS)
                self.guard.update_tree_entry(
                    slug, grace={"incident_id": record["incident_id"],
                                 "opened_at": _iso(_now()),
                                 "closes_at": _iso(closes)},
                    update_window_opened_at=None)
                return {"verdict": "UPDATE_INCOMPLETE", "slug": slug,
                        "incident_id": record["incident_id"],
                        "grace_closes_at": _iso(closes)}
            if _now() < _parse_iso(grace["closes_at"]):
                return {"verdict": "UPDATE_INCOMPLETE", "slug": slug,
                        "incident_id": grace["incident_id"],
                        "grace_closes_at": grace["closes_at"]}
            # Grace closed and the tree still cannot verify: it
            # becomes a normal integrity failure and locks (DEV-3).
            evidence = {**evidence,
                        "grace_incident": grace["incident_id"],
                        "note": "DEV-3 grace closed; locking now"}
        outcome = self.respond_lockout(tree, slug, trigger_class,
                                       evidence)
        return {"verdict": "LOCKED_OUT", "slug": slug, **outcome}


# --------------------------------------------------------------------------
# Stub, engine markers, and the phase-gate check (design Sections
# 6.3(b)-(d) and 6.6)
# --------------------------------------------------------------------------

def stub_user_text(incident_id: str) -> str:
    """What the user sees (design Section 6.6): the stub text plus the
    incident reference, no rule detail and no accusation."""
    return f"{STUB_TEXT}\nReference: {incident_id}"


def write_engine_disable_marker(marker_dir: Path, slug: str,
                                incident_id: str) -> Path:
    """Design Section 6.3(c): for wired content, the guard writes a
    disable marker into the department tree's governed checkpoint area
    (on a box: the installed department's working/security/tamper-locks,
    which sits under the design Section 3.3 working/** allow-list, so
    writing it never trips the department tree's own seal). The marker
    names the skill, never the trigger detail."""
    marker_dir.mkdir(parents=True, exist_ok=True)
    path = marker_dir / f"{slug}.json"
    path.write_text(json.dumps({
        "skill": slug, "disabled": True, "incident_id": incident_id,
        "ts": _iso(_now())}, indent=1), encoding="utf-8")
    return path


def clear_engine_disable_marker(marker_dir: Path | None, slug: str) -> None:
    if marker_dir:
        path = marker_dir / f"{slug}.json"
        if path.is_file():
            path.unlink()


def engine_disabled(marker_dir: Path | None, slug: str) -> bool:
    if not marker_dir:
        return False
    return (marker_dir / f"{slug}.json").is_file()


def phase_gate_check(guard: Guard, slug: str,
                     marker_dir: Path | None = None) -> dict:
    """The check the engine's Phase-0 preflight and each phase gate
    call (design Sections 2.5 and 6.3(c)-(d)).

    A locked skill refuses new launches at canonical entry with the
    stub text. A run already in flight completes its current phase and
    parks HERE, at the next phase gate, with park reason TAMPER_LOCKED
    (parked, not failed; resumable after reinstatement, when the
    markers clear and this check returns allowed again)."""
    entry = guard.tree_entry(slug)
    incident_id = entry.get("locked_incident")
    pending = entry.get("pending_lock")
    if pending and not incident_id:
        incident_id = pending.get("incident_id")
    if incident_id or engine_disabled(marker_dir, slug):
        return {"allowed": False, "park_reason": PARK_REASON,
                "incident_id": incident_id,
                "user_text": stub_user_text(incident_id or "unknown")}
    return {"allowed": True, "park_reason": None}


def session_start(guard: Guard, checker: Checker, tree: Path,
                  slug: str) -> dict:
    """Load-time check (design Section 2.5 point 1; in the 999 shape
    the SessionStart hook calls this). Applies any DEV-2 deferred
    conversational lock first, then verifies the tree. After a lockout,
    every fresh session sees only the stub (design TP10)."""
    applied = checker.apply_pending_lock(tree, slug)
    if applied:
        return {"verdict": "LOCKED", "slug": slug, **applied}
    if (tree / LOCK_MARKER_NAME).is_file():
        entry = guard.tree_entry(slug)
        return {"verdict": "LOCKED", "slug": slug,
                "incident_id": entry.get("locked_incident"),
                "user_text": stub_user_text(
                    entry.get("locked_incident") or "unknown")}
    return checker.verify(tree, slug)


# --------------------------------------------------------------------------
# Trigger (b), deterministic layer (design Section 4.2). All three
# rules DENY the act at the moment it occurs. Under the owner ruling
# of 2026-10-15 (DEV-1 as amended) their consequence is a strike on
# the three-strike ladder, except bulk mechanical dumping, which
# locks immediately through the Section 6 response (the F2 split;
# thresholds at the constants above). The conversational entry points
# take staff ONLY as a StaffContext minted by authenticate_staff();
# message content can never create one (design Section 5).
# --------------------------------------------------------------------------

def load_patterns() -> dict:
    return json.loads(PATTERNS_PATH.read_text(encoding="utf-8"))


def _contains_any(text: str, phrases: list[str]) -> str | None:
    for phrase in phrases:
        if phrase in text:
            return phrase
    return None


def detect_exempt_claim(text: str,
                        patterns: dict | None = None) -> str | None:
    patterns = patterns or load_patterns()
    return _contains_any(" " + text.lower() + " ",
                         [p for p in patterns["exempt_claim_patterns"]])


def detect_d2(text: str, patterns: dict | None = None) -> dict | None:
    """D2 dump-request patterns: a dump verb combined with an
    internal-artifact reference, or a direct extraction phrase from
    the versioned pattern set (design Section 4.2)."""
    patterns = patterns or load_patterns()
    lowered = text.lower()
    phrase = _contains_any(lowered, patterns["extraction_phrases"])
    if phrase:
        return {"rule": "D2", "matched": phrase, "form": "extraction-phrase"}
    verb = _contains_any(lowered, patterns["dump_verbs"])
    artifact = _contains_any(lowered, patterns["internal_artifacts"])
    if verb and artifact:
        return {"rule": "D2", "matched": f"{verb} + {artifact}",
                "form": "verb+artifact"}
    return None


class ConversationalGuard:
    """D1/D2/D3 enforcement for one install. Holds the Checker used to
    run the ladder strike path, and the full Section 6 response when
    the ladder (third standing strike) or a bulk event fires it."""

    def __init__(self, guard: Guard, checker: Checker,
                 install_shape: str = "openclaw"):
        self.guard = guard
        self.checker = checker
        self.install_shape = install_shape

    def _defer(self) -> bool:
        # DEV-2: conversational locks in the harness shape land at the
        # next session start; tool-level denial stays immediate.
        return self.install_shape == "claude-nine"

    def evaluate_message(self, text: str, slug: str, tree: Path,
                         session_id: str = "",
                         staff: StaffContext | None = None) -> dict:
        """One conversational turn (design Sections 4.2 D2 and 5).

        staff is a StaffContext or None; it can only come from
        authenticate_staff(). A staff CLAIM inside the text is detected
        and logged as AF-TAMPER-EXEMPT-CLAIM (log and notify only; it
        never exempts, never unlocks) and is attached as corroborating
        evidence when a deterministic rule fires in the same session.

        Under the amended ladder (owner ruling 2026-10-15, A2) a D2
        hit refuses the request and records a strike with the strike
        notice shown and Trevor notified; it does NOT lock on its
        own. Lockout comes only from the ladder (the third standing
        strike), and corroboration never skips the warning.
        """
        guard = self.guard
        entry = guard.tree_entry(slug)
        locked_id = entry.get("locked_incident") or (
            entry.get("pending_lock") or {}).get("incident_id")
        if locked_id:
            # Design Section 6.6: every later attempt to use the
            # locked skill returns the stub text until reinstatement.
            return {"action": "locked",
                    "user_text": stub_user_text(locked_id)}
        claim = detect_exempt_claim(text)
        claim_record = None
        if claim:
            claim_record = guard.record_and_notify(
                slug, CLS_EXEMPT_CLAIM,
                {"matched": claim, "session_id": session_id,
                 "excerpt": text[:200],
                 "note": "unauthenticated exemption claim; no effect "
                         "on any check (design Section 5)"},
                "none")
        hit = detect_d2(text)
        if hit is None:
            return {"action": "allow", "claim_logged": bool(claim_record)}
        if isinstance(staff, StaffContext):
            # Authenticated staff context: fully exempt from the
            # conversational trigger (design Section 5).
            return {"action": "allow", "exempt": "authenticated-staff",
                    "staff_actor": staff.actor,
                    "claim_logged": bool(claim_record)}
        evidence = {"sub_rule": "D2", "matched": hit["matched"],
                    "form": hit["form"], "session_id": session_id,
                    "excerpt": text[:200]}
        if claim_record:
            evidence["corroboration"] = {
                "exempt_claim_incident": claim_record["incident_id"],
                "matched": claim}
        return self.checker.respond_strike(
            tree, slug, evidence, "D2", session_id=session_id,
            defer_stub=self._defer())

    def tool_gate(self, action: str, target: Path, tree: Path, slug: str,
                  caller_root: Path | None = None,
                  destination: Path | None = None,
                  staff: StaffContext | None = None,
                  session_id: str = "") -> dict:
        """D1 tool gate (design Section 4.2): from a non-staff context,
        a tool call that reads, copies, archives, or transmits in-scope
        skill source files outside the skill's own execution paths is
        denied at the moment it occurs. Under the amended ladder
        (owner ruling 2026-10-15, F2) an ordinary trip records a
        strike and the skill locks only through the ladder; the bulk
        forms lock immediately: an archive action over an in-scope
        tree, or denied gated acts in one session crossing
        BULK_GATED_ACTS_PER_SESSION. The skill's own scripts reading
        their own files during a run is execution, not extraction:
        the distinction is caller and destination."""
        if action not in ("read", "copy", "archive", "transmit"):
            return {"allowed": True, "reason": "action-not-gated"}
        entry = self.guard.tree_entry(slug)
        locked_id = entry.get("locked_incident") or (
            entry.get("pending_lock") or {}).get("incident_id")
        if locked_id:
            # Already locked (or a DEV-2 pending lock): tool denial is
            # immediate and does not re-run the lockout.
            return {"allowed": False, "reason": "LOCKED",
                    "incident_id": locked_id}
        try:
            target.resolve().relative_to(tree.resolve())
        except (ValueError, OSError):
            return {"allowed": True, "reason": "target-outside-tree"}
        if isinstance(staff, StaffContext):
            return {"allowed": True, "reason": "authenticated-staff",
                    "staff_actor": staff.actor}
        if caller_root is not None:
            try:
                caller_root.resolve().relative_to(tree.resolve())
                # The skill's own execution paths reading their own
                # files toward the tree itself or a run workspace is
                # execution. A copy OUT of the tree is not.
                if destination is None or _inside(destination, tree):
                    return {"allowed": True, "reason": "own-execution"}
            except (ValueError, OSError):
                pass
        evidence = {"sub_rule": "D1", "action": action,
                    "target": str(target),
                    "caller_root": str(caller_root) if caller_root
                    else None,
                    "destination": str(destination) if destination
                    else None,
                    "session_id": session_id}
        if action == "archive":
            # Bulk form (F2): archiving an in-scope tree is the
            # mechanical whole-tree dump itself, not a conversational
            # act; it locks at once, even on a first offense. No
            # strike is recorded: the lockout record is the record.
            outcome = self.checker.respond_lockout(
                tree, slug, CLS_EXTRACT,
                {**evidence, "bulk": "archive-action",
                 "note": "bulk mechanical dump: an archive action "
                         "over an in-scope tree locks immediately, "
                         "even on first offense (F2)"},
                sub_rule="D1")
            return {"allowed": False, "reason": "D1-BULK", **outcome}
        outcome = self.checker.respond_strike(
            tree, slug, evidence, "D1", session_id=session_id)
        if outcome["action"] != "lock" and session_id:
            # Bulk form (F2): a session whose denied gated acts cross
            # the threshold is running a scripted sweep; it locks at
            # once. The strike above still stands on the record.
            acts = self.guard.note_gated_act(session_id)
            if acts > BULK_GATED_ACTS_PER_SESSION:
                outcome = self.checker.respond_lockout(
                    tree, slug, CLS_EXTRACT,
                    {**evidence, "bulk": "gated-act-count",
                     "gated_acts_in_session": acts,
                     "note": "bulk mechanical dump: denied gated "
                             "source acts in one session crossed "
                             "the bulk threshold; locks immediately, "
                             "even on first offense (F2)"},
                    sub_rule="D1")
                return {"allowed": False, "reason": "D1-BULK",
                        **outcome}
        return {"allowed": False, "reason": "D1", **outcome}

    def egress_check(self, text: str, slug: str, tree: Path,
                     session_id: str = "",
                     staff: StaffContext | None = None) -> dict:
        """D3 egress span check (design Section 4.2): outbound content
        from a non-staff context is checked for verbatim spans of
        in-scope internal text. At or above threshold the payload is
        blocked and replaced. Under the amended ladder (owner ruling
        2026-10-15, F2) an ordinary block records a strike and the
        replacement text is the strike notice; a bulk payload (a
        verbatim span at or above BULK_EGRESS_VERBATIM_CHARS) locks
        at once and the replacement is the stub text, as is a block
        that is itself the third standing strike. Client run
        artifacts are never in the shingle set (the set is built only
        from shipped covered files, Section 2.2), so explaining the
        client's own results can never trip this rule."""
        if isinstance(staff, StaffContext):
            return {"blocked": False, "reason": "authenticated-staff"}
        entry = self.guard.tree_entry(slug)
        locked_id = entry.get("locked_incident") or (
            entry.get("pending_lock") or {}).get("incident_id")
        if locked_id:
            return {"blocked": True, "reason": "LOCKED",
                    "replacement": stub_user_text(locked_id)}
        sealed = self.guard.load_shingles(slug)
        if not sealed:
            return {"blocked": False, "reason": "no-shingle-set"}
        words = _normalize_words(text)
        matched = 0
        longest_run_words = 0
        run = 0
        run_start = 0
        longest_span = ""
        if len(words) >= SHINGLE_WORDS:
            for i in range(len(words) - SHINGLE_WORDS + 1):
                window = " ".join(words[i:i + SHINGLE_WORDS])
                if _sha256_bytes(window.encode("utf-8")) in sealed:
                    matched += 1
                    if run == 0:
                        run_start = i
                    run += 1
                    if run > longest_run_words:
                        longest_run_words = run
                        longest_span = " ".join(
                            words[run_start:run_start + run + SHINGLE_WORDS - 1])
                else:
                    run = 0
        longest_chars = len(longest_span)
        if longest_chars >= EGRESS_VERBATIM_CHARS or \
                matched >= EGRESS_SHINGLE_MIN:
            evidence = {"sub_rule": "D3", "session_id": session_id,
                        "matched_shingles": matched,
                        "longest_verbatim_chars": longest_chars,
                        "excerpt": longest_span[:200]}
            if longest_chars >= BULK_EGRESS_VERBATIM_CHARS:
                # Bulk form (F2): one payload carrying a verbatim
                # span this large is a mechanical dump of sealed
                # text; it locks at once, even on a first offense.
                # The payload is still blocked and stub-replaced.
                outcome = self.checker.respond_lockout(
                    tree, slug, CLS_EXTRACT,
                    {**evidence, "bulk": "oversized-egress-payload",
                     "note": "bulk mechanical dump: a single egress "
                             "payload at or above the bulk verbatim "
                             "threshold locks immediately, even on "
                             "first offense (F2)"},
                    sub_rule="D3", defer_stub=self._defer())
                return {"blocked": True, "reason": "D3-BULK",
                        "replacement": outcome["user_text"], **outcome}
            outcome = self.checker.respond_strike(
                tree, slug, evidence, "D3", session_id=session_id,
                defer_stub=self._defer())
            return {"blocked": True, "reason": "D3",
                    "replacement": outcome["user_text"], **outcome}
        return {"blocked": False, "matched_shingles": matched,
                "longest_verbatim_chars": longest_chars}


def _inside(path: Path, tree: Path) -> bool:
    try:
        path.resolve().relative_to(tree.resolve())
        return True
    except (ValueError, OSError):
        return False


# --------------------------------------------------------------------------
# Trigger (b), judgment layer (design Section 4.3). An out-of-band
# transcript evaluator modeled on intake_trace_check.py: deterministic,
# stdlib only, NO AI at runtime, post-hoc over transcript exports
# (JSON list of {role, text} turns, or plain-text speaker lines). The
# rubric is design Section 4.1 with the Section 4.4 worked examples as
# its calibration corpus (every example is exercised by the test suite).
#
# DEV-1 POSTURE, AS AMENDED (owner ruling 2026-10-15; amendment
# Sections A1/A2 and calls F1/F5/F6): DEV-1's warn-first step is
# extended into the three-strike ladder, not replaced. Before
# scoring, the A1 exclusion pass drops comprehension and use turns,
# so they can never count toward the signals. A positive records ONE
# strike per session (F5), however it is corroborated: corroboration
# never skips the warning and a corroborated positive still counts
# one strike. The third standing strike, counted per client across
# all guarded skills (F6), locks through the Section 6 response.
# has_deterministic_corroboration() survives as evidence recorded on
# the strike record; it decides nothing by itself anymore.
# --------------------------------------------------------------------------

def _turns_from_transcript(data) -> list[dict]:
    if isinstance(data, list):
        turns = []
        for item in data:
            if isinstance(item, dict):
                role = item.get("role") or item.get("speaker") or ""
                text = (item.get("text") or item.get("content")
                        or item.get("message") or "")
                turns.append({"role": str(role), "text": str(text)})
        return turns
    if isinstance(data, str):
        turns = []
        for line in data.splitlines():
            match = re.match(r"(?i)^(user|human|client|assistant|agent)"
                             r"\s*:\s*(.*)$", line.strip())
            if match:
                turns.append({"role": match.group(1).lower(),
                              "text": match.group(2)})
            elif turns:
                turns[-1]["text"] += "\n" + line
        return turns
    return []


def _is_comprehension_or_use(lowered: str, patterns: dict) -> bool:
    """The A1 exclusion (owner ruling 2026-10-15): the design
    Section 4.1 "does not count" list as an explicit scoring pass.
    A turn counts as comprehension or use when it carries one of the
    versioned comprehension markers (a how-to-use framing, a
    business-level ask, the client's own work product or run, a
    troubleshooting or redo ask) AND names no internal artifact and
    no verbatim-text extraction phrase: the design Section 4.1 line
    is that describing behavior and results is ordinary use while
    disclosing the shipped text or construction is extraction, so a
    turn asking for the text itself is never reclassified as
    comprehension by a polite framing around it."""
    if _contains_any(lowered, patterns["internal_artifacts"]):
        return False
    if _contains_any(lowered, patterns["extraction_phrases"]):
        return False
    return _contains_any(
        lowered, patterns["comprehension_markers"]) is not None


def score_transcript(turns: list[dict],
                     patterns: dict | None = None) -> dict:
    """The rubric (pure). Signals over USER turns only:
      sequential:  requests for successive internal procedure content
      paraphrase:  paraphrase-extraction phrasing
      framing:     jailbreak framings aimed at confidentiality
    Positive when sequential >= 3, paraphrase >= 2, framing >= 2, or
    mixed signals total >= 4 across at least two classes: incremental
    reconstruction is a pattern across turns, not one phrase.
    Comprehension and use turns are excluded by construction BEFORE
    any signal phrase in them is counted (A1): the exclusion is a
    property of this function, so every caller inherits it."""
    patterns = patterns or load_patterns()
    signals: dict[str, list[int]] = {"sequential": [], "paraphrase": [],
                                     "framing": []}
    for idx, turn in enumerate(turns):
        if turn.get("role", "").lower() not in (
                "user", "human", "client"):
            continue
        lowered = turn.get("text", "").lower()
        if _is_comprehension_or_use(lowered, patterns):
            continue
        for cls in signals:
            if _contains_any(lowered, patterns["judgment"][cls]):
                signals[cls].append(idx)
    counts = {k: len(v) for k, v in signals.items()}
    classes_hit = sum(1 for v in counts.values() if v > 0)
    positive = (counts["sequential"] >= 3 or counts["paraphrase"] >= 2
                or counts["framing"] >= 2
                or (sum(counts.values()) >= 4 and classes_hit >= 2))
    return {"positive": positive, "signals": signals, "counts": counts}


def has_deterministic_corroboration(guard: Guard) -> bool:
    """Any deterministic AF-TAMPER-EXTRACT incident anywhere in this
    install's history (design TP8: same install history)."""
    for rec in guard.records():
        if rec.get("trigger_class") == CLS_EXTRACT and \
                (rec.get("evidence") or {}).get("sub_rule") in (
                        "D1", "D2", "D3"):
            return True
    return False


def evaluate_transcript(data, guard: Guard, checker: Checker, slug: str,
                        tree: Path, session_id: str = "",
                        staff: StaffContext | None = None,
                        install_shape: str = "openclaw") -> dict:
    """Run the judgment layer over a transcript export and apply the
    ladder (DEV-1 as amended by the owner ruling of 2026-10-15).
    Returns {verdict: clean|warned|locked, ...}.

    A positive records a strike through Checker.respond_strike: warn,
    notice, notify; the third standing strike on the client's record
    locks. Corroboration is computed and recorded as evidence only:
    it never skips the warning and never adds a second strike (F5).
    The per-skill registry judgment_warnings list is appended for
    every recorded judgment strike, warned or locking, exactly as
    the DEV-1 build recorded it: it remains this layer's evidence
    index (amendment B5), while the ladder's count lives in the
    per-client strike ledger."""
    turns = _turns_from_transcript(data)
    scored = score_transcript(turns)
    if not scored["positive"]:
        return {"verdict": "clean", **scored}
    if isinstance(staff, StaffContext):
        return {"verdict": "clean", "exempt": "authenticated-staff",
                **scored}
    entry = guard.tree_entry(slug)
    prior_warnings = len(entry.get("judgment_warnings") or [])
    corroborated = has_deterministic_corroboration(guard) or any(
        rec.get("trigger_class") == CLS_EXEMPT_CLAIM
        and (rec.get("evidence") or {}).get("session_id") == session_id
        for rec in guard.records())
    evidence = {"sub_rule": "JUDGMENT", "session_id": session_id,
                "rubric_counts": scored["counts"],
                "signal_turns": scored["signals"],
                "prior_warnings": prior_warnings,
                "corroborated": corroborated}
    outcome = checker.respond_strike(
        tree, slug, evidence, "JUDGMENT", session_id=session_id,
        defer_stub=(install_shape == "claude-nine"))
    if outcome.get("strike_recorded"):
        warnings = list(entry.get("judgment_warnings") or [])
        warnings.append(outcome.get("strike_incident_id")
                        or outcome["incident_id"])
        guard.update_tree_entry(slug, judgment_warnings=warnings)
    if outcome["action"] == "lock":
        return {"verdict": "locked", **outcome, **scored}
    return {"verdict": "warned",
            "incident_id": outcome["incident_id"],
            "user_text": JUDGMENT_WARNING_TEXT, **scored}


# --------------------------------------------------------------------------
# Reinstatement and re-baseline (design Sections 7.1-7.3). Staff-only,
# authenticated channel only. There is NO conversational path to
# reinstatement, at all (design Section 5).
# --------------------------------------------------------------------------

def reinstate(guard: Guard, checker: Checker, slug: str, tree: Path,
              incident_id: str, staff: StaffContext | None,
              user_spoke_to_staff: bool,
              canonical_source: Path | None,
              forensic: bool = False,
              second_confirmation: bool = False) -> dict:
    if not isinstance(staff, StaffContext):
        raise Refusal("STAFF_AUTH_REQUIRED",
                      "reinstatement requires an authenticated staff "
                      "context (design Section 7.1)")
    if not user_spoke_to_staff:
        raise Refusal(
            "ATTESTATION_REQUIRED",
            "reinstatement refuses without the recorded "
            "user_spoke_to_staff attestation: staff must attest the "
            "user has spoken to staff (design Section 7.1). The "
            "system cannot verify a conversation it was not part of "
            "and does not pretend to.")
    original = guard.find_record(incident_id)
    if original is None:
        raise Refusal("INCIDENT_NOT_FOUND",
                      f"no incident record for {incident_id}")
    if forensic:
        if not second_confirmation:
            raise Refusal("FORENSIC_CONFIRMATION_REQUIRED",
                          "restoring quarantined bytes requires a "
                          "second staff confirmation (design 7.2)")
        source = guard.home / "quarantine" / slug / incident_id
        if not source.is_dir():
            raise Refusal("QUARANTINE_NOT_FOUND",
                          "no quarantined tree for this incident")
        restore_source = "quarantine-forensic"
    else:
        if canonical_source is None or not Path(canonical_source).is_dir():
            raise Refusal("CANONICAL_SOURCE_REQUIRED",
                          "reinstatement restores from canonical "
                          "source, never from quarantine by default "
                          "(design Section 7.2 step 2)")
        source = Path(canonical_source)
        restore_source = "canonical"
    # Verify the candidate tree BEFORE it replaces the stub: on
    # failure the skill stays locked and the failure is recorded
    # (design Section 7.2 step 3). The forensic path is the one
    # exception, and it is honest about why: quarantined bytes diverge
    # from their manifest BY DEFINITION (that is why they were
    # locked), so a forensic restore re-seals the restored tree under
    # the staff member's signature instead, on the record.
    manifest_path = source / MANIFEST_NAME
    if not manifest_path.is_file():
        raise Refusal("SOURCE_UNSEALED",
                      "the restore source carries no integrity "
                      "manifest; refusing to install an unsealed tree")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        keyring = checker.keyring()
    except GuardConfigError as exc:
        raise Refusal("GUARDFAULT", str(exc)) from exc
    forensic_reseal = False
    if forensic:
        forensic_reseal = True
    else:
        status = manifest_signature_status(manifest, keyring)
        if status not in ("current", "previous"):
            raise Refusal("SOURCE_SIGNATURE_INVALID",
                          f"restore source manifest status: {status}")
        divergences = compare_tree(source, manifest)
        if divergences:
            raise Refusal("SOURCE_DIVERGED",
                          "restore source does not verify against its "
                          f"manifest: {len(divergences)} divergence(s)")
    # Swap: remove the stub, install the verified tree.
    if tree.exists():
        shutil.rmtree(tree)
    shutil.copytree(source, tree)
    if forensic_reseal:
        manifest, shingles = build_manifest(
            tree, slug, keyring,
            generated_by="tamper_guard.py forensic restore re-seal "
                         "(design 7.2)")
        write_manifest(tree, manifest)
        guard.store_shingles(slug, shingles)
    clear_engine_disable_marker(checker.engine_marker_dir, slug)
    guard.update_tree_entry(
        slug, locked_incident=None, pending_lock=None,
        manifest_digest=manifest["manifest_digest"], tree=str(tree))
    record = guard.record_and_notify(
        slug, EV_REINSTATEMENT,
        {"original_incident": incident_id,
         "restore_source": restore_source,
         "forensic_reseal": forensic_reseal,
         "user_spoke_to_staff": True,
         "scope": slug},
        "reinstated", actor=staff.actor)
    return {"reinstated": True, "incident_id": incident_id,
            "record_id": record["incident_id"],
            "restore_source": restore_source}


def rebaseline(guard: Guard, checker: Checker, slug: str, tree: Path,
               staff: StaffContext | None, reason: str) -> dict:
    """Design Section 7.3: for deliberate staff-caused divergence
    (the operator-annotation case). Staff review the diverged tree;
    the guard generates a fresh manifest from it and the staff member
    signs through the authenticated channel. Recorded, attributed."""
    if not isinstance(staff, StaffContext):
        raise Refusal("STAFF_AUTH_REQUIRED",
                      "re-baseline requires an authenticated staff "
                      "context (design Section 7.3)")
    if not reason or not reason.strip():
        raise Refusal("REASON_REQUIRED",
                      "a re-baseline records a reason string")
    try:
        keyring = checker.keyring()
    except GuardConfigError as exc:
        raise Refusal("GUARDFAULT", str(exc)) from exc
    source = tree
    entry = guard.tree_entry(slug)
    locked_incident = entry.get("locked_incident")
    if (tree / LOCK_MARKER_NAME).is_file() and locked_incident:
        candidate = guard.home / "quarantine" / slug / locked_incident
        if candidate.is_dir():
            source = candidate
    manifest, shingles = build_manifest(
        source, slug, keyring,
        generated_by="tamper_guard.py re-baseline (staff, Section 7.3)")
    if source != tree:
        if tree.exists():
            shutil.rmtree(tree)
        shutil.copytree(source, tree)
    write_manifest(tree, manifest)
    guard.store_shingles(slug, shingles)
    clear_engine_disable_marker(checker.engine_marker_dir, slug)
    guard.update_tree_entry(
        slug, locked_incident=None, pending_lock=None,
        manifest_digest=manifest["manifest_digest"], tree=str(tree))
    record = guard.record_and_notify(
        slug, EV_REBASELINE,
        {"reason": reason, "manifest_digest": manifest["manifest_digest"],
         "files_sealed": len(manifest["files"])},
        "re-baselined", actor=staff.actor)
    return {"rebaselined": True, "record_id": record["incident_id"],
            "manifest_digest": manifest["manifest_digest"]}


# --------------------------------------------------------------------------
# The ladder's staff calls (owner ruling 2026-10-15; amendment B5 and
# call F3). Every warning notification asks Trevor for one of two
# calls on the strike: allow the behavior, or remove the strike. Both
# are staff acts, entered ONLY through authenticate_staff(), the only
# channel through which staff acts exist in this system; there is no
# conversational path to either, and no reply path is built (F4: his
# call reaches staff in whatever channel the notification reached
# him, and staff enter it here). Both APPEND their record to the
# incident log in the existing record shape, naming the warning
# incident, the skill and install, the staff identity, and the call
# as given. The original warning record is never edited or deleted,
# because the log is append-only by design; what the record shows
# afterward is the warning plus the resolution beside it.
#   pardon ("remove the strike"): the strike is REMOVED. It does not
#     count toward the ladder and does not serve as a prior warning.
#   allow ("allow the behavior"): the strike is VOID, judged
#     legitimate, as if never recorded. No whitelist, no time box
#     (F3): the next identical ask is judged fresh.
# Neither act reinstates a locked skill: a resolution that arrives
# after a strike-three lockout reduces the standing count, and
# reinstatement stays the separate Section 7 flow above, because
# reinstatement also restores verified content, which neither call
# addresses (amendment B5).
# --------------------------------------------------------------------------

def _strike_resolution(guard: Guard, staff: StaffContext | None,
                       incident_id: str, trigger_class: str,
                       resolution: str, call: str) -> dict:
    if not isinstance(staff, StaffContext):
        raise Refusal("STAFF_AUTH_REQUIRED",
                      "a strike resolution requires an authenticated "
                      "staff context (amendment B5: staff acts exist "
                      "only through the authenticated channel)")
    original = guard.find_record(incident_id)
    if original is None:
        raise Refusal("INCIDENT_NOT_FOUND",
                      f"no incident record for {incident_id}")
    if not guard.resolve_strike(incident_id, resolution):
        raise Refusal("NOT_A_STRIKE",
                      f"incident {incident_id} is not a recorded "
                      "strike on the ladder")
    record = guard.record_and_notify(
        original.get("skill") or "", trigger_class,
        {"warning_incident": incident_id,
         "skill": original.get("skill"),
         "call": call,
         "note": "staff resolution of a ladder strike (owner ruling "
                 "2026-10-15); the warning record stands in the "
                 "append-only log and the strike no longer counts"},
        resolution, actor=staff.actor)
    return {"resolved": resolution, "warning_incident": incident_id,
            "record_id": record["incident_id"],
            "standing_strikes": guard.standing_strike_count()}


def pardon_strike(guard: Guard, staff: StaffContext | None,
                  incident_id: str) -> dict:
    """Trevor's "remove the strike" call (amendment B5): the strike
    is pardoned off the client's standing count."""
    return _strike_resolution(guard, staff, incident_id,
                              EV_STRIKE_PARDON, "pardoned",
                              "remove the strike")


def allow_strike(guard: Guard, staff: StaffContext | None,
                 incident_id: str) -> dict:
    """Trevor's "allow the behavior" call (amendment call F3): the
    strike is void, as if never recorded; the next identical ask is
    judged fresh, with nothing whitelisted and nothing time-boxed."""
    return _strike_resolution(guard, staff, incident_id,
                              EV_STRIKE_ALLOW, "voided",
                              "allow the behavior")


# --------------------------------------------------------------------------
# Watchdog and heartbeat (design Sections 2.5 and 6.5)
# --------------------------------------------------------------------------

def watchdog(guard: Guard, checker: Checker,
             trees: list[tuple[Path, str]]) -> dict:
    """One scheduled verification pass over every registered in-scope
    tree, on the fleet's 600 s cadence (the box scheduler invokes this;
    the cadence constant is WATCHDOG_CADENCE_SECONDS). Each pass writes
    a heartbeat record; a box whose heartbeat stops is staff-visible
    as a missing signal."""
    verdicts = {}
    for tree, slug in trees:
        verdicts[slug] = checker.verify(tree, slug)["verdict"]
    record = {"ts": _iso(_now()), "cadence_seconds": WATCHDOG_CADENCE_SECONDS,
              "box": guard.box_identity(), "trees": verdicts}
    with open(guard._heartbeat_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return record


# --------------------------------------------------------------------------
# Repo-side CI check (design Section 2.2 publish rule; FP8). PR CI holds
# no key, so this checks digest consistency only: every covered file's
# hash against the manifest, and the manifest digest against its body.
# The fleet-key signature is verified on the box, where the key lives.
# --------------------------------------------------------------------------

def ci_check(tree: Path) -> list[dict]:
    manifest_path = tree / MANIFEST_NAME
    if not manifest_path.is_file():
        return [{"path": MANIFEST_NAME, "kind": "MANIFEST_MISSING"}]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [{"path": MANIFEST_NAME, "kind": "MANIFEST_UNPARSEABLE",
                 "detail": str(exc)}]
    problems = []
    if manifest_digest_of(manifest) != manifest.get("manifest_digest"):
        problems.append({"path": MANIFEST_NAME,
                         "kind": "MANIFEST_DIGEST_MISMATCH"})
    problems.extend(compare_tree(tree, manifest))
    return problems


def load_scope() -> dict:
    return json.loads(SCOPE_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _make_guard_and_checker(args) -> tuple[Guard, Checker]:
    guard = Guard(environ=os.environ)
    keyring = None
    key_error = None
    try:
        keyring = load_keyring(os.environ)
    except GuardConfigError as exc:
        key_error = exc
    checker = Checker(
        guard, keyring=keyring, key_error=key_error,
        install_shape=getattr(args, "shape", "openclaw"),
        baseline_adoption_allowed=not getattr(
            args, "no_baseline_adoption", False),
        engine_marker_dir=Path(args.engine_markers) if getattr(
            args, "engine_markers", None) else None)
    return guard, checker


def _staff_from_args(args) -> StaffContext | None:
    method = getattr(args, "staff_method", None)
    if not method:
        return None
    token = None
    token_env = getattr(args, "staff_token_env", None)
    if token_env:
        token = os.environ.get(token_env)
    return authenticate_staff(method, presented=token)


def _print(obj) -> None:
    print(json.dumps(obj, indent=1, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FIX-PLAN Item 32 tamper guard (design: B12). "
                    "Exit codes: 0 pass/allow, 1 violation/blocked/"
                    "refused, 2 guard fault, 3 usage.")
    parser.add_argument("--shape", default="openclaw",
                        choices=("openclaw", "claude-nine"),
                        help="install shape (DEV-2 deferral applies to "
                             "claude-nine conversational locks)")
    parser.add_argument("--engine-markers", default=None,
                        help="department governed checkpoint dir for "
                             "engine disable markers (design 6.3(c))")
    parser.add_argument("--no-baseline-adoption", action="store_true",
                        help="disable DEV-4 baseline adoption")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("generate", help="build+sign a tree's manifest "
                                        "(publish time; design 2.2)")
    p.add_argument("tree")
    p.add_argument("--slug", required=True)
    p.add_argument("--source-commit", default="")
    p.add_argument("--exclude", action="append", default=[])

    p = sub.add_parser("ci-check", help="repo-side digest check (FP8)")
    p.add_argument("tree")

    p = sub.add_parser("verify", help="verify one tree (load/post-roll)")
    p.add_argument("tree")
    p.add_argument("--slug", required=True)

    p = sub.add_parser("session-start", help="DEV-2 pending locks + verify")
    p.add_argument("tree")
    p.add_argument("--slug", required=True)

    p = sub.add_parser("watchdog", help="verify every registered tree "
                                        "and write the heartbeat")
    p.add_argument("--tree", action="append", default=[],
                   help="SLUG=PATH, repeatable; defaults to registry")

    p = sub.add_parser("message", help="D2 check on one user message")
    p.add_argument("tree")
    p.add_argument("--slug", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--session-id", default="")
    p.add_argument("--staff-method", default=None)
    p.add_argument("--staff-token-env", default=None)

    p = sub.add_parser("tool-gate", help="D1 tool gate decision")
    p.add_argument("tree")
    p.add_argument("--slug", required=True)
    p.add_argument("--action", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--caller-root", default=None)
    p.add_argument("--destination", default=None)
    p.add_argument("--session-id", default="")
    p.add_argument("--staff-method", default=None)
    p.add_argument("--staff-token-env", default=None)

    p = sub.add_parser("egress", help="D3 egress span check")
    p.add_argument("tree")
    p.add_argument("--slug", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--session-id", default="")
    p.add_argument("--staff-method", default=None)
    p.add_argument("--staff-token-env", default=None)

    p = sub.add_parser("transcript", help="judgment layer over a "
                                          "transcript export (JSON or text)")
    p.add_argument("tree")
    p.add_argument("--slug", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--session-id", default="")
    p.add_argument("--staff-method", default=None)
    p.add_argument("--staff-token-env", default=None)

    p = sub.add_parser("gate-check", help="phase-gate / preflight check")
    p.add_argument("--slug", required=True)

    p = sub.add_parser("reinstate", help="staff-only reinstatement "
                                         "(design Section 7)")
    p.add_argument("tree")
    p.add_argument("--slug", required=True)
    p.add_argument("--incident", required=True)
    p.add_argument("--source", default=None,
                   help="canonical source tree (not quarantine)")
    p.add_argument("--forensic", action="store_true")
    p.add_argument("--second-confirmation", action="store_true")
    p.add_argument("--user-spoke-to-staff", action="store_true",
                   help="the recorded attestation (design 7.1)")
    p.add_argument("--staff-method", default=None)
    p.add_argument("--staff-token-env", default=None)

    p = sub.add_parser("rebaseline", help="staff re-baseline (design 7.3)")
    p.add_argument("tree")
    p.add_argument("--slug", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--staff-method", default=None)
    p.add_argument("--staff-token-env", default=None)

    p = sub.add_parser("pardon-strike", help="staff call on a warning: "
                                             "remove the strike (B5)")
    p.add_argument("--incident", required=True)
    p.add_argument("--staff-method", default=None)
    p.add_argument("--staff-token-env", default=None)

    p = sub.add_parser("allow-strike", help="staff call on a warning: "
                                            "allow the behavior, voiding "
                                            "the strike (F3)")
    p.add_argument("--incident", required=True)
    p.add_argument("--staff-method", default=None)
    p.add_argument("--staff-token-env", default=None)

    args = parser.parse_args(argv)
    guard, checker = _make_guard_and_checker(args)

    try:
        if args.cmd == "generate":
            try:
                keyring = checker.keyring()
            except GuardConfigError:
                keyring = None  # unsigned repo form (see build_manifest)
            manifest, shingles = build_manifest(
                Path(args.tree), args.slug, keyring,
                extra_exclusions=args.exclude,
                source_commit=args.source_commit)
            write_manifest(Path(args.tree), manifest)
            guard.store_shingles(args.slug, shingles)
            guard.update_tree_entry(
                args.slug, tree=str(Path(args.tree)),
                manifest_digest=manifest["manifest_digest"])
            _print({"generated": args.slug,
                    "files": len(manifest["files"]),
                    "digest": manifest["manifest_digest"],
                    "signed": bool(manifest["signature"])})
            return 0
        if args.cmd == "ci-check":
            problems = ci_check(Path(args.tree))
            _print({"tree": args.tree, "problems": problems})
            return 1 if problems else 0
        if args.cmd == "verify":
            result = checker.verify(Path(args.tree), args.slug)
            _print(result)
            return 0 if result["verdict"] in (
                "OK", "UPDATE_IN_PROGRESS", "UPDATE_INCOMPLETE",
                "BASELINE_ADOPTED") else 1
        if args.cmd == "session-start":
            result = session_start(guard, checker, Path(args.tree),
                                   args.slug)
            _print(result)
            return 0 if result["verdict"] in (
                "OK", "UPDATE_IN_PROGRESS", "UPDATE_INCOMPLETE",
                "BASELINE_ADOPTED") else 1
        if args.cmd == "watchdog":
            trees = []
            for item in args.tree:
                slug, _, path = item.partition("=")
                trees.append((Path(path), slug))
            if not trees:
                for slug, entry in guard.registry().get(
                        "trees", {}).items():
                    if entry.get("tree"):
                        trees.append((Path(entry["tree"]), slug))
            _print(watchdog(guard, checker, trees))
            return 0
        if args.cmd == "gate-check":
            result = phase_gate_check(
                guard, args.slug,
                Path(args.engine_markers) if args.engine_markers
                else None)
            _print(result)
            return 0 if result["allowed"] else 1
        if args.cmd in ("message", "tool-gate", "egress", "transcript"):
            convo = ConversationalGuard(guard, checker,
                                        install_shape=args.shape)
            staff = _staff_from_args(args)
            if args.cmd == "message":
                result = convo.evaluate_message(
                    args.text, args.slug, Path(args.tree),
                    session_id=args.session_id, staff=staff)
                _print(result)
                return 1 if result["action"] == "lock" else 0
            if args.cmd == "tool-gate":
                result = convo.tool_gate(
                    args.action, Path(args.target), Path(args.tree),
                    args.slug,
                    caller_root=Path(args.caller_root)
                    if args.caller_root else None,
                    destination=Path(args.destination)
                    if args.destination else None,
                    staff=staff, session_id=args.session_id)
                _print(result)
                return 0 if result["allowed"] else 1
            if args.cmd == "egress":
                result = convo.egress_check(
                    args.text, args.slug, Path(args.tree),
                    session_id=args.session_id, staff=staff)
                _print(result)
                return 1 if result["blocked"] else 0
            raw = Path(args.file).read_text(encoding="utf-8")
            try:
                data = json.loads(raw)
            except ValueError:
                data = raw
            result = evaluate_transcript(
                data, guard, checker, args.slug, Path(args.tree),
                session_id=args.session_id, staff=staff,
                install_shape=args.shape)
            _print(result)
            return 1 if result["verdict"] == "locked" else 0
        if args.cmd == "reinstate":
            result = reinstate(
                guard, checker, args.slug, Path(args.tree),
                args.incident, _staff_from_args(args),
                args.user_spoke_to_staff,
                Path(args.source) if args.source else None,
                forensic=args.forensic,
                second_confirmation=args.second_confirmation)
            _print(result)
            return 0
        if args.cmd == "rebaseline":
            result = rebaseline(guard, checker, args.slug,
                                Path(args.tree), _staff_from_args(args),
                                args.reason)
            _print(result)
            return 0
        if args.cmd == "pardon-strike":
            result = pardon_strike(guard, _staff_from_args(args),
                                   args.incident)
            _print(result)
            return 0
        if args.cmd == "allow-strike":
            result = allow_strike(guard, _staff_from_args(args),
                                  args.incident)
            _print(result)
            return 0
    except Refusal as exc:
        _print({"refused": exc.code, "detail": str(exc)})
        return 1
    except GuardConfigError as exc:
        _print({"guardfault": exc.code, "detail": str(exc)})
        return 2
    except GuardError as exc:
        _print({"error": exc.code, "detail": str(exc)})
        return 2
    return 3


if __name__ == "__main__":
    sys.exit(main())
