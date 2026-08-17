#!/usr/bin/env python3
"""
_interview_transcript.py — the ONE shared reader for the interview transcript
(workforce-interview-answers.md), plaintext OR encrypted (U048).

WHY THIS EXISTS (2026-07-30 incident on a client Mac mini box / its rescue agent):
The Command Center added transcript encryption at rest (U048,
blackceo-command-center src/lib/interview/crypto.ts): the canonical transcript
is written to `workforce-interview-answers.md.enc` — a chacha20-poly1305
envelope — and the plaintext `.md` is removed once migrated
(migratePlaintextFile()). Every Skill-23 script that gates a real build on the
transcript (qc-interview-completion.py, build-workforce.py's
_genuine_interview_answers_file()/verify_interview_complete()) only knew the
PLAINTEXT path. For a client whose transcript was already encrypted, every one
of those gates saw "Transcript not found" and permanently refused to build —
even though a genuine, complete interview existed on disk. This module is
imported by ALL of them so the path-resolution + decrypt logic can never drift
apart the way canonical_decline.py's docstring warns three separate copies of
the decline-provenance rule once did.

WIRE FORMAT (MUST match blackceo-command-center/src/lib/interview/crypto.ts
EXACTLY — see docstring there):
  "enc:v1:" + base64(nonce(12 bytes) ‖ tag(16 bytes) ‖ ciphertext)
  cipher = chacha20-poly1305, key = 32 bytes.

KEY RESOLUTION (mirrors crypto.ts resolveInterviewKey(), READ-ONLY on the
Python side — this module NEVER creates key material, only reads what the
Node side already created; a missing salt file / unset env means decryption
is genuinely impossible, not a bug to paper over):
  1. MC_INTERVIEW_SECRET env var (trimmed, SHA-256 -> 32 bytes)
  2. MC_BOX_SECRET env var (same treatment)
  3. Per-box salt file ~/.openclaw/.interview-key-salt (>=32 bytes, written by
     the Node side on first encrypt) + os.uname hostname, SHA-256(hostname
     bytes + salt[:32]) -> 32 bytes.
  If none of the three are available, key resolution fails explicitly — the
  caller gets a clear "no key material available" reason, never a silent
  wrong-key decrypt attempt (AEAD would reject it anyway, but we want the
  diagnostic to say WHY).

FAIL-CLOSED CONTRACT (binding — do not weaken):
  - Transcript genuinely absent (no plaintext, no .enc, at any candidate path)
    -> content=None, reason="not-found", tried=[...] (diagnostic, not a guess).
  - .enc present but the key can't be resolved, or decryption/AEAD-integrity
    fails (wrong key, tampered/corrupt envelope) -> content=None,
    reason="undecryptable" / "no-key-material" (DISTINCT from not-found).
  - Plaintext present -> read as before (zero behavior change for clients
    who never encrypted).
  This module NEVER writes decrypted plaintext to disk and NEVER logs
  transcript content — callers must follow the same rule (do not print
  `result.content`; only counts/lengths/booleans are safe to log).

NO-FABRICATION: this module reads and reports; it never writes to the
transcript, and it never invents content when decryption is unavailable.
"""

from __future__ import annotations

import base64
import hashlib
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path

ENVELOPE_PREFIX = "enc:v1:"
NONCE_BYTES = 12
TAG_BYTES = 16

# Lazily imported so a box without the `cryptography` package can still import
# this module and read PLAINTEXT transcripts (regression safety) — only the
# .enc decrypt path needs it, and its absence is reported as a precise reason
# rather than an ImportError crashing the whole QC/build script.
try:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305  # type: ignore
    _HAVE_CRYPTOGRAPHY = True
except Exception:  # noqa: BLE001
    ChaCha20Poly1305 = None  # type: ignore
    _HAVE_CRYPTOGRAPHY = False


# ── Key resolution (mirrors crypto.ts resolveInterviewKey(), read-only) ──────

def _salt_path() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".openclaw" / ".interview-key-salt"


def resolve_interview_key() -> tuple:
    """
    Resolve the 32-byte chacha20-poly1305 key using the EXACT same priority
    order as crypto.ts resolveInterviewKey(), but READ-ONLY: this side never
    creates a salt file (only the Node encrypt path does that; on a box where
    encryption happened, the salt file the encrypter created is already there).

    Returns (key: bytes|None, reason: str). key is None iff no key material
    could be resolved (reason explains which sources were tried and why each
    failed) — this is a normal, expected outcome on a box with no encryption
    configured, NOT a crash.
    """
    from_env = (os.environ.get("MC_INTERVIEW_SECRET") or os.environ.get("MC_BOX_SECRET") or "").strip()
    if from_env:
        return hashlib.sha256(from_env.encode("utf-8")).digest(), "env"

    salt_path = _salt_path()
    try:
        salt = salt_path.read_bytes()
    except OSError:
        return None, (
            f"no key material: MC_INTERVIEW_SECRET/MC_BOX_SECRET unset and no salt "
            f"file at {salt_path} (the Node encrypter creates this on first use — "
            f"its absence means either encryption never ran on this box, or this "
            f"reader is running as a different user/HOME than the encrypter)"
        )
    if len(salt) < 32:
        return None, f"salt file at {salt_path} is shorter than 32 bytes (corrupt)"

    hostname = socket.gethostname() or "unknown-box"
    key = hashlib.sha256(hostname.encode("utf-8") + salt[:32]).digest()
    return key, "salt-file"


def is_encrypted_envelope(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(ENVELOPE_PREFIX)


def decrypt_envelope(envelope: str) -> tuple:
    """
    Decrypt a wire-format envelope string to UTF-8 plaintext.

    Returns (plaintext: str|None, reason: str). plaintext is None iff
    decryption failed; reason is one of:
      "cryptography-package-missing" | "no key material: ..." | "malformed-envelope"
      | "decrypt-failed (wrong key or tampered/corrupt envelope)" | "ok"
    NEVER raises. NEVER logs the envelope or plaintext content.
    """
    if not _HAVE_CRYPTOGRAPHY:
        return None, (
            "cryptography-package-missing: the Python 'cryptography' package is not "
            "importable in this interpreter, so an encrypted (.enc) transcript cannot "
            "be decrypted here. Install it (pip install cryptography) in the same "
            "Python environment that runs this script."
        )
    if not is_encrypted_envelope(envelope):
        return None, "malformed-envelope: missing 'enc:v1:' prefix"

    key, key_reason = resolve_interview_key()
    if key is None:
        return None, key_reason

    try:
        raw = base64.b64decode(envelope[len(ENVELOPE_PREFIX):], validate=True)
    except Exception:  # noqa: BLE001
        return None, "malformed-envelope: base64 decode failed"

    if len(raw) < NONCE_BYTES + TAG_BYTES:
        return None, "malformed-envelope: too short to contain nonce+tag"

    nonce = raw[:NONCE_BYTES]
    tag = raw[NONCE_BYTES:NONCE_BYTES + TAG_BYTES]
    ciphertext = raw[NONCE_BYTES + TAG_BYTES:]

    try:
        aead = ChaCha20Poly1305(key)
        # Node's envelope orders (nonce, tag, ciphertext); the `cryptography`
        # AEAD API expects ciphertext with the tag APPENDED at the end.
        plaintext = aead.decrypt(nonce, ciphertext + tag, None)
        return plaintext.decode("utf-8"), "ok"
    except Exception:  # noqa: BLE001
        # Wrong key, tampered envelope, or corrupt data all land here. Do NOT
        # distinguish further — leaking "tag mismatch" vs "wrong key" timing/
        # detail is an unnecessary oracle, and the caller only needs "it did
        # not decrypt" to fail closed correctly.
        return None, "decrypt-failed (wrong key or tampered/corrupt envelope)"


# ── Path resolution ───────────────────────────────────────────────────────────

@dataclass
class ProbeAttempt:
    path: str
    kind: str          # "plaintext" | "encrypted"
    status: str        # "hit" | "missing" | "read-error" | "decrypt-failed" | "no-key-material"
    detail: str = ""


@dataclass
class TranscriptResult:
    content: str | None
    source_path: str | None
    encrypted: bool
    reason: str | None                # populated iff content is None
    tried: list = field(default_factory=list)  # list[ProbeAttempt], diagnostic only

    @property
    def ok(self) -> bool:
        return self.content is not None


def candidate_bases(
    recorded_path: str | None = None,
    company_discovery_dir: str | None = None,
) -> list:
    """
    Build the ordered list of PLAINTEXT candidate paths (no extension games —
    each entry is the exact `.md` path a plaintext transcript would live at).
    Mirrors the probe order already used by qc-interview-completion.py /
    build-workforce.py / _qc_no_web_store.py, so behavior for a non-encrypted
    client is UNCHANGED. `.enc` siblings are derived from this same list by
    read_transcript() below — one candidate list drives both extensions.

    D2 FIX — the resolver never probed where the CONVERSATIONAL lane writes.
    This list used to stop after the two `<workspace>/company-discovery/`
    paths. Two real write locations were therefore invisible to it:

      (a) THE MASTER-FILES TREE. The Telegram/agent-conducted interview logs
          answers to `<master-files>/company-discovery/workforce-interview-
          answers.md` — `~/Downloads/openclaw-master-files` on Mac,
          `/data/openclaw-master-files` on VPS, `MASTER_FILES_DIR` when
          overridden (the same convention build-workforce.py's
          find_master_files_folder() / get_openclaw_paths() resolve, and the
          location SKILL.md and INSTALL.md both document as the permanent
          answer record). Because this resolver never looked there, a fully
          answered conversational interview reported "transcript not found",
          which the completion gate treats as unverifiable and refuses —
          `exit 87`, forever, on an interview that was genuinely finished.

      (b) THE FLAT WORKSPACE FALLBACK. blackceo-command-center's
          answersFilePath() (src/lib/interview/paths.ts) probes
          `<workspace>/workforce-interview-answers.md` as its third candidate.
          This resolver did not, so the two sides of the same seam disagreed
          about where the transcript lives.

    Adding both makes this list a strict SUPERSET of every writer's location.
    Nothing is removed and the existing entries keep their exact priority, so a
    box whose transcript already resolved keeps resolving it from the same
    place — the new paths are only ever reached when the old ones miss.
    """
    home = os.path.expanduser("~")
    candidates = []
    if recorded_path:
        candidates.append(str(recorded_path))
    if company_discovery_dir:
        candidates.append(os.path.join(str(company_discovery_dir), "workforce-interview-answers.md"))
    workspace_bases = ("/data/.openclaw/workspace", os.path.join(home, ".openclaw", "workspace"))
    for base in workspace_bases:
        candidates.append(os.path.join(base, "company-discovery", "workforce-interview-answers.md"))
    # (a) master-files tree — where the conversational/Telegram lane logs answers.
    master_files_bases = []
    env_master = os.environ.get("MASTER_FILES_DIR")
    if env_master:
        master_files_bases.append(env_master)
    master_files_bases.append("/data/openclaw-master-files")
    master_files_bases.append(os.path.join(home, "Downloads", "openclaw-master-files"))
    for base in master_files_bases:
        candidates.append(os.path.join(base, "company-discovery", "workforce-interview-answers.md"))
    # (b) flat workspace fallback — matches the Command Center's third probe.
    for base in workspace_bases:
        candidates.append(os.path.join(base, "workforce-interview-answers.md"))
    # De-dup while preserving order (recorded_path can coincide with a standard one).
    seen = set()
    ordered = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def _try_one_candidate(base: str, tried: list) -> TranscriptResult | None:
    """
    Probe ONE candidate base path and append its attempt(s) to `tried`.
    Returns a TranscriptResult the instant this candidate resolves (plaintext
    hit OR .enc hit-and-decrypted), else None (caller moves to the next
    candidate). A candidate that already ends in `.enc` (e.g. an operator
    passed `--transcript foo.md.enc` explicitly, or a caller's own candidate
    list already carries `.enc` paths) is treated AS an encrypted file
    directly — never mistaken for plaintext, never double-suffixed.
    """
    if base.endswith(".enc"):
        if os.path.isfile(base):
            try:
                envelope = Path(base).read_text(encoding="utf-8").strip()
            except OSError as exc:
                tried.append(ProbeAttempt(base, "encrypted", "read-error", str(exc)))
                return None
            plaintext, reason = decrypt_envelope(envelope)
            if plaintext is not None:
                tried.append(ProbeAttempt(base, "encrypted", "hit"))
                return TranscriptResult(plaintext, base, True, None, tried)
            status = "no-key-material" if reason.startswith("no key material") or reason.startswith(
                "cryptography-package-missing") else "decrypt-failed"
            tried.append(ProbeAttempt(base, "encrypted", status, reason))
        else:
            tried.append(ProbeAttempt(base, "encrypted", "missing"))
        return None

    # 1) Plaintext, exactly as every reader already tried before this fix.
    if os.path.isfile(base):
        try:
            text = Path(base).read_text(encoding="utf-8", errors="ignore")
            tried.append(ProbeAttempt(base, "plaintext", "hit"))
            return TranscriptResult(text, base, False, None, tried)
        except OSError as exc:
            tried.append(ProbeAttempt(base, "plaintext", "read-error", str(exc)))
    else:
        tried.append(ProbeAttempt(base, "plaintext", "missing"))

    # 2) Encrypted sibling.
    enc_path = base + ".enc"
    if os.path.isfile(enc_path):
        try:
            envelope = Path(enc_path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            tried.append(ProbeAttempt(enc_path, "encrypted", "read-error", str(exc)))
            return None
        plaintext, reason = decrypt_envelope(envelope)
        if plaintext is not None:
            tried.append(ProbeAttempt(enc_path, "encrypted", "hit"))
            return TranscriptResult(plaintext, enc_path, True, None, tried)
        status = "no-key-material" if reason.startswith("no key material") or reason.startswith(
            "cryptography-package-missing") else "decrypt-failed"
        tried.append(ProbeAttempt(enc_path, "encrypted", status, reason))
    else:
        tried.append(ProbeAttempt(enc_path, "encrypted", "missing"))
    return None


def read_transcript_at(base: str) -> TranscriptResult:
    """
    Resolve exactly ONE candidate base path (plaintext, then its `.enc`
    sibling) and return its TranscriptResult — content is None with a
    diagnostic reason if neither resolves. Used by callers (e.g.
    build-workforce.py's _genuine_interview_answers_file() /
    verify_interview_complete()) that must evaluate SUBSTANCE per-candidate
    and fall through to their NEXT candidate on a substance failure, rather
    than stopping at the first path that merely EXISTS (see read_transcript()
    below for the "first hit across all candidates" variant).
    """
    tried: list = []
    hit = _try_one_candidate(base, tried)
    if hit is not None:
        return hit
    encrypted_failures = [a for a in tried if a.kind == "encrypted" and a.status in ("decrypt-failed", "no-key-material")]
    if encrypted_failures:
        reason = f"undecryptable: {encrypted_failures[0].detail}"
    else:
        reason = "not-found"
    return TranscriptResult(None, None, False, reason, tried)


def read_transcript(candidates: list) -> TranscriptResult:
    """
    Try each candidate path IN ORDER, returning on the FIRST one that
    resolves (plaintext hit, or .enc hit-and-decrypted) — content is NOT
    evaluated here. Callers that need substance-checking with fallthrough to
    the next candidate on failure (build-workforce.py) should use
    read_transcript_at() per-candidate instead.

    NEVER writes plaintext to disk. NEVER returns/logs raw envelope bytes.
    """
    tried: list = []

    for base in candidates:
        hit = _try_one_candidate(base, tried)
        if hit is not None:
            return hit

    # Nothing hit. Distinguish "genuinely nothing on disk" from "something was
    # there but undecryptable" so the caller's error message is diagnostic,
    # not a false "missing".
    encrypted_failures = [a for a in tried if a.kind == "encrypted" and a.status in ("decrypt-failed", "no-key-material")]
    if encrypted_failures:
        worst = encrypted_failures[0]
        reason = f"undecryptable: {worst.detail} (tried {len(tried)} location(s))"
    else:
        reason = f"not-found: no plaintext or .enc transcript at any of {len(candidates)} candidate location(s)"

    return TranscriptResult(None, None, False, reason, tried)


def format_tried(tried: list) -> str:
    """Human-readable diagnostic summary of every path probed. Safe to print —
    paths and status only, never content."""
    lines = []
    for a in tried:
        extra = f" ({a.detail})" if a.detail else ""
        lines.append(f"  [{a.kind}] {a.path} -> {a.status}{extra}")
    return "\n".join(lines)
