"""F10 sandbox wrapper (CANDIDATE, lane-local, not applied to product).

Trusted-caller-owned launch path for untrusted producers. Forces every
untrusted-producer spawn through macOS Seatbelt via /usr/bin/sandbox-exec
with a profile denying file-write* to the trusted store and denying
network*. Semantics identical to proven V f10.sb
(d192ab358537ea8ea459c122007768e48a62d7c8245601847d61a85584a38381):
allow default; deny file-write* subpath=<store>; deny network*.

Provider/delivery calls stay in the trusted caller: the producer itself
gets no network, so a producer that reads a credential cannot use it.
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

PROFILE_TEMPLATE = """(version 1)
(allow default)
(deny file-write* (subpath "{store}"))
(deny network*)
"""

# Digest of the V proven mechanism profile (215 B). The template above
# carries identical semantics; only the subpath is parameterized.
PROVEN_MECHANISM_SHA256 = "d192ab358537ea8ea459c122007768e48a62d7c8245601847d61a85584a38381"
PROVEN_PRODUCER_SHA256 = "44ad6c1dc9cc4c745bbc669a5555a59df80bc57e1ca44012233048fce1acdd31"

SANDBOX_EXEC = "/usr/bin/sandbox-exec"


def profile_text(store_dir):
    """Render the Seatbelt profile for a concrete trusted-store path."""
    return PROFILE_TEMPLATE.format(store=str(Path(store_dir)))


def profile_digest(store_dir):
    return hashlib.sha256(profile_text(store_dir).encode()).hexdigest()


def build_argv(store_dir, producer_argv):
    """Return argv launching producer_argv under the sandbox profile.

    Writes the rendered profile to a temp file owned by the trusted
    caller and returns [sandbox-exec, -f, profile, *producer_argv].
    Raises FileNotFoundError when sandbox-exec is unavailable
    (fail-closed: no unsandboxed fallback).
    """
    import shutil as _shutil

    if _shutil.which(SANDBOX_EXEC) is None and not Path(SANDBOX_EXEC).exists():
        raise FileNotFoundError("sandbox-exec unavailable; refusing unsandboxed spawn")
    text = profile_text(store_dir)
    if "(deny file-write*" not in text or "(deny network*)" not in text:
        raise ValueError("rendered profile lost a deny rule; refusing spawn")
    tmp = tempfile.NamedTemporaryFile(
        prefix="f10-sandbox-", suffix=".sb", mode="w", delete=False
    )
    with tmp as fh:
        fh.write(text)
    return [SANDBOX_EXEC, "-f", tmp.name] + list(producer_argv)


def wiring_attestation(run_dir=None):
    """Prove the wiring is reached at runtime (called by admit_production).

    Verifies this module's own deny rules render correctly and
    sandbox-exec exists. Returns an additive descriptor; raises on any
    defect so admission fails closed instead of silently unwired.
    Takes no authority decision and changes no admission semantics.
    """
    probe = profile_text("/tmp/f10-attestation-probe")
    if "(deny file-write*" not in probe or "(deny network*)" not in probe:
        raise ValueError("F10 sandbox profile template lost a deny rule")
    if not Path(SANDBOX_EXEC).exists():
        raise ValueError("F10 sandbox-exec missing; untrusted spawn unwired")
    return {
        "enforced": True,
        "launcher": SANDBOX_EXEC,
        "deny": ["file-write*", "network*"],
        "template_sha256": hashlib.sha256(PROFILE_TEMPLATE.encode()).hexdigest(),
    }


def spawn_untrusted(store_dir, producer_argv, **popen_kw):
    """Spawn an untrusted producer confined by the sandbox profile."""
    argv = build_argv(store_dir, producer_argv)
    return subprocess.run(argv, capture_output=True, text=True, **popen_kw)
