#!/usr/bin/env python3
"""ghl_secret_resolver.py — the ONE shared secret resolver for Skill 06.

Every GHL credential this skill resolves — the Firebase refresh token
(ghl_auth.py / seed-ghl-auth.py), the LOCATION PIT and the location id
(ghl_media.py), and the Tier-2 client store reads (ghl_auth_fallback.py) —
goes through this module, so the precedence contract exists exactly once:

  1. *_FILE indirection: a variable such as GHL_REFRESH_TOKEN_FILE naming a
     file whose CONTENTS are the secret (the Docker-secrets / mounted-file
     shape the install packet specifies). The file must not be group- or
     world-accessible: a set *_FILE variable whose target is missing,
     unreadable, empty, or carries any group/other permission bit is a
     PRECISE failure — the error names the variable, the path, and the mode,
     never the contents.
  2. The live environment, across the credential's canonical alias chain,
     preferred alias first.
  3. The canonical env stores (ENV_STORES), NAME-MAJOR: a preferred alias
     found in a later store beats a legacy alias in an earlier store.

Placeholder-shaped values (see is_placeholder) are SKIPPED at every layer —
a placeholder is not a credential — and the Resolution records which layers
saw one, so a caller can fail loud with that note instead of a bare
"missing".

NOTHING in this module prints, logs, or places a resolved or candidate
value inside an error message. Errors name variables, paths, and modes
only.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence, Tuple

# Canonical env stores, in order — the SAME list ghl_media.py has always
# used (~/.openclaw/secrets/.env is the authoritative operator store).
ENV_STORES = (
    "~/.openclaw/secrets/.env",
    "~/clawd/secrets/.env",
    "~/.openclaw/workspace/.env",
)


class SecretResolutionError(RuntimeError):
    """A secret could not be resolved, or a *_FILE indirection is broken.

    The message names variables, paths, and modes only — never a value."""


class SecretFileError(SecretResolutionError):
    """A *_FILE variable is set but its target cannot be trusted or read:
    missing, unreadable, empty, or group/world-accessible. Raised
    immediately — a broken indirection never falls through silently to
    weaker sources."""

    file_error = True


@dataclass
class Resolution:
    """Outcome of attempt_resolution(). value is "" when nothing resolved."""

    value: str = ""
    source: str = ""  # env var name, *_FILE var name, or "NAME in <store>"
    env_placeholder_seen: bool = False
    store_placeholder_seen: bool = False
    file_placeholder_seen: bool = False

    @property
    def placeholder_seen(self) -> bool:
        return (
            self.env_placeholder_seen
            or self.store_placeholder_seen
            or self.file_placeholder_seen
        )


def is_placeholder(value: str) -> bool:
    """True when value is a documentation placeholder, not a real
    credential. Ported verbatim from ghl_media._is_placeholder (the proven
    reference implementation — root-caused a false "PIT is DEAD/EXPIRED"
    alarm on 2026-08-03, where the 10-char doc placeholder pit-abc123
    is non-empty and so outranked the real credential under a naive
    first-non-empty-wins resolver). Shapes: shorter than 20 characters (a
    real PIT / refresh token is far longer), a known dummy literal
    (pit-abc..., changeme..., xxx..., your-... / your_...,
    a *_here / *-here suffix), or an angle-bracket token (<...>).
    The value is only ever inspected for shape — never logged or returned.
    """
    if not value:
        return True
    if len(value) < 20:
        return True
    return is_placeholder_shape(value)


def is_placeholder_shape(value: str) -> bool:
    """True when ``value`` matches a dummy-LITERAL placeholder shape (the
    ``pit-abc...`` / ``changeme...`` / ``xxx...`` / ``your-...`` / ``*_here`` /
    angle-bracket shapes), WITHOUT the length floor is_placeholder adds.

    The refresh-token class screens with this predicate: its documented
    placeholders are dummy literals, while a merely SHORT value is a real
    (if doomed) token the mint must reject precisely at the exchange —
    and the orchestrator's alias-precedence contract is specified over
    short dummy values that are not placeholder-shaped. The PIT and
    location classes use full is_placeholder (their doc placeholders are
    short, e.g. the 10-char ``pit-abc123``, so the length floor is
    load-bearing there)."""
    if not value:
        return True
    low = value.lower()
    if low.startswith("pit-abc") or low.startswith("changeme") or low.startswith("xxx") \
       or low.startswith("your-") or low.startswith("your_") \
       or low.endswith("_here") or low.endswith("-here") \
       or (value.startswith("<") and value.endswith(">")):
        return True
    return False


def _clean_value(raw: str) -> str:
    """Strip surrounding whitespace and one layer of surrounding quotes."""
    return raw.strip().strip("'\"").strip()


def first_of_comma_list(value: str) -> str:
    """First entry of a comma-separated allowlist value (single-location
    builds pin one id; *_ALLOWED_LOCATION_IDS callers rely on this)."""
    return value.split(',', 1)[0].strip() if ',' in value else value


def parse_store_lines(lines: Sequence[str], key: str) -> str:
    """Return the cleaned value of the FIRST line defining key in a
    store file's lines, or "" when the key is not defined. Line rules (the
    ones every reader in this skill has always used): blank lines and #
    comments are skipped, a leading export  is accepted, the key is the
    text before the first =, and surrounding quotes are stripped."""
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        k, _, v = line.partition("=")
        if k.strip() != key:
            continue
        return _clean_value(v)
    return ""


def parse_store_file(path: str, key: str) -> str:
    """Value of key in the store file at path ("" when the file is
    absent/unreadable or the key is not defined). Never raises."""
    try:
        with open(os.path.expanduser(path), encoding="utf-8", errors="replace") as fh:
            return parse_store_lines(fh.read().splitlines(), key)
    except OSError:
        return ""


def scan_env_stores(
    names: Sequence[str],
    stores: Optional[Sequence[str]] = None,
    transform: Optional[Callable[[str], str]] = None,
    seen: Optional[dict] = None,
    placeholder_check: Callable[[str], bool] = is_placeholder,
) -> Tuple[str, str]:
    """Search the env stores for the first usable value of any of
    names, NAME-MAJOR (name preference outranks store order, so a
    preferred alias in a later store beats a legacy alias in an earlier
    one). Returns (value, "NAME in <store_path>") or ("", ""). Never
    raises — a missing/unreadable store is simply skipped. stores=None
    means the module ENV_STORES, read at call time (the test seam).

    Placeholder-shaped values are skipped (and recorded via
    seen["store_placeholder"] when a seen dict is passed) so a
    store line is never treated as real just because it lives in a file.
    transform (e.g. first-of-comma-list for allowlist values) is applied
    to each candidate before the placeholder check, matching the historic
    ghl_media store-scan semantics exactly.
    """
    if stores is None:
        stores = ENV_STORES
    for name in names:
        for store_path in stores:
            expanded = os.path.expanduser(store_path)
            if not os.path.isfile(expanded):
                continue
            try:
                with open(expanded, encoding="utf-8", errors="replace") as fh:
                    lines = fh.read().splitlines()
            except OSError:
                continue
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].lstrip()
                k, _, v = line.partition("=")
                if k.strip() != name:
                    continue
                v = _clean_value(v)
                if transform is not None:
                    v = transform(v)
                if v and not placeholder_check(v):
                    return v, f"{name} in {store_path}"
                if v and seen is not None:
                    seen["store_placeholder"] = True
    return "", ""


def read_secret_file(path: str, *, file_var: str) -> str:
    """Read the secret held in the file a *_FILE variable names.

    Returns the stripped contents. Raises SecretFileError (precise, and
    value-free: variable, path, and mode only) when the target is missing,
    group/world-accessible, unreadable, or empty. Placeholder screening is
    the caller's layer (attempt_resolution skips a placeholder-shaped file
    value like any other placeholder source).
    """
    expanded = os.path.expanduser(path)
    if not os.path.isfile(expanded):
        raise SecretFileError(
            f"{file_var} is set to {expanded} but that file does not exist. "
            "Point the variable at the mounted secret file, or unset it to "
            "use the env/store sources instead."
        )
    mode = stat.S_IMODE(os.stat(expanded).st_mode)
    if mode & 0o077:
        raise SecretFileError(
            f"{file_var} points at {expanded} with permissions {oct(mode)} — "
            "a group/world-accessible secret file is refused. Set the file "
            "to mode 0600 (owner read/write only), or unset the variable."
        )
    try:
        with open(expanded, encoding="utf-8", errors="replace") as fh:
            value = fh.read().strip()
    except OSError as exc:
        raise SecretFileError(
            f"{file_var} is set to {expanded} but the file could not be read "
            f"({exc.__class__.__name__}). Fix the mount, or unset the variable."
        ) from exc
    if not value:
        raise SecretFileError(
            f"{file_var} is set to {expanded} but the file is empty. A set "
            "*_FILE variable must name a file holding the secret; fix the "
            "mount, or unset the variable."
        )
    return value


def attempt_resolution(
    env: Optional[Mapping[str, str]],
    *,
    file_vars: Sequence[str] = (),
    aliases: Sequence[str] = (),
    stores: Optional[Sequence[str]] = None,
    search_stores: bool = True,
    transform: Optional[Callable[[str], str]] = None,
    store_transform: Optional[Callable[[str], str]] = None,
    placeholder_check: Callable[[str], bool] = is_placeholder,
) -> Resolution:
    """Resolve one credential through the shared contract.

    Precedence: (1) each *_FILE variable in file_vars (in order) whose
    target file holds a usable value; (2) the live env across aliases,
    preferred first; (3) the canonical stores, name-major. Placeholder-
    shaped candidates are skipped at every layer and recorded on the
    returned Resolution. Raises SecretFileError for a broken *_FILE
    indirection (missing / loose-permissions / unreadable / empty target).

    env=None resolves against the process environment. An explicit
    mapping is read as given (mapping + the files its *_FILE variables
    name); whether the stores join in is the caller's search_stores
    choice.
    """
    src: Mapping[str, str] = env if env is not None else os.environ
    if stores is None:
        stores = ENV_STORES
    res = Resolution()

    # 1) *_FILE indirection (highest precedence).
    for fv in file_vars:
        raw_path = (src.get(fv, "") or "").strip()
        if not raw_path:
            continue
        value = read_secret_file(raw_path, file_var=fv)  # raises SecretFileError
        if transform is not None:
            value = transform(value)
        if placeholder_check(value):
            res.file_placeholder_seen = True
            continue
        res.value, res.source = value, fv
        return res

    # 2) Live env across the alias chain.
    for name in aliases:
        v = _clean_value(str(src.get(name, "") or ""))
        if transform is not None:
            v = transform(v)
        if not v:
            continue
        if placeholder_check(v):
            res.env_placeholder_seen = True
            continue
        res.value, res.source = v, name
        return res

    # 3) Canonical stores (name-major).
    if search_stores:
        seen: dict = {}
        value, source = scan_env_stores(
            aliases, stores,
            transform=store_transform if store_transform is not None else transform,
            seen=seen, placeholder_check=placeholder_check)
        if seen.get("store_placeholder"):
            res.store_placeholder_seen = True
        if value:
            res.value, res.source = value, source
    return res


def failure_message(
    label: str,
    *,
    aliases: Sequence[str] = (),
    file_vars: Sequence[str] = (),
    stores: Optional[Sequence[str]] = None,
    placeholder_seen: bool = False,
) -> str:
    """The standard honest-failure text: names EVERY source checked (each
    *_FILE variable, each alias, each store) and never any value."""
    if stores is None:
        stores = ENV_STORES
    checked = []
    if file_vars:
        checked.append("*_FILE variables: " + ", ".join(file_vars))
    checked.append("env vars: " + ", ".join(aliases))
    checked.append("stores: " + ", ".join(stores))
    msg = f"{label} not found in any source. Checked, in order: " + ". ".join(checked) + "."
    if placeholder_seen:
        msg += (
            " Note: at least one candidate value was a documentation "
            "PLACEHOLDER (short / dummy-shaped) and was SKIPPED rather than "
            "used — a placeholder is not a credential."
        )
    msg += " No value is printed here by design."
    return msg


__all__ = [
    "ENV_STORES",
    "Resolution",
    "SecretFileError",
    "SecretResolutionError",
    "attempt_resolution",
    "failure_message",
    "first_of_comma_list",
    "is_placeholder",
    "is_placeholder_shape",
    "parse_store_file",
    "parse_store_lines",
    "read_secret_file",
    "scan_env_stores",
]
