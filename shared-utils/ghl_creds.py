#!/usr/bin/env python3
"""shared-utils/ghl_creds.py -- the ONE Convert and Flow (GHL) credential lookup (INF002).

Used by the Skill 59 credential gate and by the install QC of skills 05, 29, 35 and 36
(through shared-utils/ghl-creds.sh). Standard library only. Never prints a credential.

Order (Trevor's rule):
  1. LOCATION ID under every name it is kept under -- GHL_LOCATION_ID,
     GOHIGHLEVEL_LOCATION_ID, GOHIGHLEVEL_ALLOWED_LOCATION_IDS,
     CONVERT_AND_FLOW_LOCATION_ID / convert_and_flow_location (and the CAF/HIGHLEVEL
     spellings) -- in the live env, then every store: ~/.openclaw/secrets/.env,
     ~/.openclaw/.env, ~/clawd/secrets/.env, workspace/.env, workspace/secrets/.env,
     workspace/secrets.env, service-env/ai.openclaw.gateway.env (Mac ~/.openclaw, VPS
     /data/.openclaw and container /home/node/.openclaw roots).
  2. Not found -> the Convert and Flow private integration token (a pit- token under
     GHL_API_KEY, GOHIGHLEVEL_API_KEY, GHL_PRIVATE_TOKEN, GOHIGHLEVEL_CF_PIT,
     CONVERT_AND_FLOW_API_KEY ...). Ask the GHL API which location that location-scoped
     token belongs to and use it. The resolved id is cached in memory and in a small
     state file (an id and a short token fingerprint, never the token).
  3. Neither -> status "missing": the caller installs WITH A NOTE naming what is needed.

Nothing here writes or changes a credential. Agency tokens are never used for step 2.

Typed compatibility contract (GU-018)
------------------------------------
Every credential this module can return is a `Credential` carrying its KIND:

  location_pit  a location-scoped Private Integration Token (`pit-`)
  agency_pit    an agency-scoped PIT -- read ONLY so a refusal can name it
  firebase      a Firebase refresh token (Skill 44 / Skill 06 private rail)
  oauth_grant   a GHL OAuth grant -- NO alias exists today; the kind is declared
                so a caller asking for it gets an honest empty, never a PIT

A kind belongs to the VARIABLE NAME, never to the value's shape: location and
agency PITs are both `pit-` tokens and cannot be told apart offline. The alias
tables are therefore disjoint (enforced at import) and `resolve_credential`
reads only the requested kind's table. It NEVER substitutes one kind for
another, and `require_credential` refuses with the kinds that WERE present.

The location id is a TENANT BINDING, not a credential kind. It is read only
from the location-id aliases / `GHL_LOCATION_ID_FILE`, or (existing behaviour)
from the account itself via `location_for_pit`. It is never inferred from a
name, a store path or a token's prefix.

`resolve()` keeps its pre-GU-018 signature and result keys unchanged: existing
callers of resolve() / shell_exports() / the CLI need no change. `*_FILE`
indirection (frozen contract 4.1) is additive and highest precedence; a broken
`*_FILE` never crashes the CLI path -- it is reported in the note, and
`resolve_credential(strict_files=True)` raises for credentialed callers.
"""
import hashlib
import json
import os
import re
import shlex
import stat
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

LOCATION_NAMES = (
    "GHL_LOCATION_ID",
    "GOHIGHLEVEL_LOCATION_ID",
    "GOHIGHLEVEL_ALLOWED_LOCATION_IDS",
    "CONVERT_AND_FLOW_LOCATION_ID",
    "convert_and_flow_location",
    "CAF_LOCATION_ID",
    "CAF_ALLOWED_LOCATION_IDS",
    "HIGHLEVEL_LOCATION_ID",
)
PIT_NAMES = (
    "GOHIGHLEVEL_API_KEY",
    "GHL_API_KEY",
    "GHL_PRIVATE_TOKEN",
    "GOHIGHLEVEL_CF_PIT",
    "CONVERT_AND_FLOW_API_KEY",
    "CONVERT_AND_FLOW_PIT",
    "CONVERT_AND_FLOW_PRIVATE_INTEGRATION_TOKEN",
    "CONVERTANDFLOW_API_KEY",
    "CONVERTFLOW_API_KEY",
    "GHL_PRIVATE_INTEGRATION_TOKEN",
    "GHL_PIT",
    "GOHIGHLEVEL_PIT",
)
API_BASE = "https://services.leadconnectorhq.com"


class Kind(str, Enum):
    """The credential CLASS a value belongs to. See the module docstring."""

    location_pit = "location_pit"
    agency_pit = "agency_pit"
    firebase = "firebase"
    oauth_grant = "oauth_grant"


# Agency PITs (frozen contract 4.1) -- listed so a refusal can say "I saw an
# agency token, it is NOT a location credential". Never a location_pit source.
AGENCY_PIT_NAMES = (
    "GOHIGHLEVEL_AGENCY_PIT",
    "GOHIGHLEVEL_AGENCY_API_KEY",
    "GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT",
    "GHL_AGENCY_PIT",
)

# Firebase refresh tokens (frozen contract 4.1). Same three names, same order,
# as 06-ghl-install-pages/tools/ghl_auth.py REFRESH_ENV_VARS.
FIREBASE_REFRESH_NAMES = (
    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
    "CAF_FIREBASE_REFRESH_TOKEN",
    "GHL_FIREBASE_REFRESH_TOKEN",
)

# No OAuth grant alias is honoured anywhere in the family today. Declared empty
# so Kind.oauth_grant resolves to an honest empty rather than a PIT.
OAUTH_GRANT_NAMES = ()

KIND_ALIASES = {
    Kind.location_pit: PIT_NAMES,
    Kind.agency_pit: AGENCY_PIT_NAMES,
    Kind.firebase: FIREBASE_REFRESH_NAMES,
    Kind.oauth_grant: OAUTH_GRANT_NAMES,
}

# *_FILE indirection (frozen contract 4.1): the file's CONTENTS are the value,
# highest precedence. No agency / oauth file variable is frozen, so none exists.
KIND_FILE_VARS = {
    Kind.location_pit: ("GHL_LOCATION_PIT_FILE",),
    Kind.agency_pit: (),
    Kind.firebase: ("GHL_REFRESH_TOKEN_FILE",),
    Kind.oauth_grant: (),
}

# Location id is a TENANT BINDING, deliberately not a Kind.
TENANT_ID_NAMES = LOCATION_NAMES
TENANT_ID_FILE_VARS = ("GHL_LOCATION_ID_FILE",)


@dataclass(frozen=True)
class Credential:
    """A resolved credential plus its kind. Repr never shows the value."""

    kind: Kind
    value: str
    source: str   # "env:NAME" | "file:<store>:NAME" | "file-var:NAME"
    alias: str    # the bare variable name it was read from

    def __repr__(self):
        return "Credential(kind=%s, alias=%r, source=%r, value=<redacted>)" % (
            self.kind.value, self.alias, self.source)

    __str__ = __repr__


class CredentialUnavailable(LookupError):
    """No credential of the requested kind, and substitution is refused.

    `seen` names the OTHER kinds that were present, so an agency-only box
    reports "agency_pit present, refusing to substitute" instead of a bare
    "missing".
    """

    def __init__(self, kind, seen=()):
        self.kind = Kind(kind)
        self.seen = tuple(Kind(k) for k in seen)
        msg = "no %s credential found" % self.kind.value
        if self.seen:
            msg += "; found only %s -- refusing to substitute a different credential kind" % (
                ", ".join(sorted(k.value for k in self.seen)))
        super().__init__(msg)


class CredentialFileError(RuntimeError):
    """A *_FILE variable is set but its target is unusable: missing, unreadable,
    empty, or group/world-accessible. Names the variable, path and mode only."""


def _is_placeholder_shape(v):
    """Dummy-LITERAL placeholder, never a credential. Ported from the frozen
    family resolver (06-ghl-install-pages/tools/ghl_secret_resolver.py
    is_placeholder_shape): pit-abc*, changeme*, xxx*, your-*/your_*, a *_here or
    *-here suffix, or an angle-bracket token. Deliberately prefix/suffix only --
    the refresh-token class has no length floor and no free-text match, because
    a merely SHORT token is a real (if doomed) token, rejected at the exchange."""
    v = (v or "").strip()
    if not v:
        return True
    low = v.lower()
    return (low.startswith(("pit-abc", "changeme", "xxx", "your-", "your_"))
            or low.endswith(("_here", "-here"))
            or (v.startswith("<") and v.endswith(">")))


def _is_real_refresh(v):
    """Refresh-token shape: any non-placeholder value (a short token is a real,
    doomed token -- it fails at the exchange, never by silent substitution)."""
    return bool((v or "").strip()) and not _is_placeholder_shape(v)


KIND_VALIDATORS = {
    Kind.location_pit: lambda v: _is_real_pit(v),
    Kind.agency_pit: lambda v: _is_real_pit(v),
    Kind.firebase: _is_real_refresh,
    Kind.oauth_grant: _is_real_refresh,
}


def _check_kind_tables():
    """Import-time guard: an alias may belong to exactly one kind, and no kind
    alias may collide with a tenant-binding name. A collision would be the
    substitution hole this contract exists to close."""
    owner = {}
    for kind, names in KIND_ALIASES.items():
        for name in names:
            low = name.lower()
            if low in owner and owner[low] is not kind:
                raise RuntimeError(
                    "ghl_creds: alias %s is claimed by both %s and %s"
                    % (name, owner[low].value, kind.value))
            owner[low] = kind
    for name in TENANT_ID_NAMES:
        if name.lower() in owner:
            raise RuntimeError(
                "ghl_creds: %s is a tenant binding and a %s credential alias"
                % (name, owner[name.lower()].value))


_check_kind_tables()


NOTE_MISSING = ("Installed. Convert and Flow location id or private integration token needed "
                "before this skill can reach the account. Add GOHIGHLEVEL_LOCATION_ID (or the "
                "pit- token as GOHIGHLEVEL_API_KEY) to ~/.openclaw/secrets/.env.")
NOTE_UNRESOLVED = ("Installed. A Convert and Flow private integration token was found but the "
                   "location it belongs to could not be read from the API (offline or no scope). "
                   "Add GOHIGHLEVEL_LOCATION_ID to ~/.openclaw/secrets/.env.")

_MEMO = {}


def store_paths():
    """Every env store, highest priority first. Roots: Mac ~/.openclaw, VPS /data/.openclaw,
    container /home/node/.openclaw."""
    home = os.path.expanduser("~")
    roots = [home + "/.openclaw", "/data/.openclaw", "/home/node/.openclaw"]
    out = []
    for r in roots:
        out += [r + "/secrets/.env", r + "/.env", r + "/workspace/secrets.env",
                r + "/workspace/.env", r + "/workspace/secrets/.env",
                r + "/service-env/ai.openclaw.gateway.env"]
    out += [home + "/clawd/secrets/.env", "/data/clawd/secrets/.env"]
    seen, ordered = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def _parse(path):
    vals = {}
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1]
                vals[k.strip()] = v.strip()
    except OSError:
        pass
    return vals


def _is_location_id(v):
    return bool(re.fullmatch(r"[A-Za-z0-9]{12,40}", v or ""))


_PLACEHOLDER_RE = re.compile(
    r"(?i)(your[_-]|xxx|placeholder|changeme|change_me|replace|paste|example|dummy|todo|<|>|_here)")


def _is_real_pit(v):
    return bool(v) and v.startswith("pit-") and len(v) >= 20 and not _PLACEHOLDER_RE.search(v)


def _first(names, sources, valid, first_of_list=False):
    """First valid value for any of `names` (case-insensitive) in `sources`
    [(label, mapping)], env first. A placeholder in one source never shadows a real value
    in another. Returns (value, "label:NAME") or (None, "")."""
    wanted = {n.lower(): n for n in names}
    for label, mapping in sources:
        by_lower = {k.lower(): (k, v) for k, v in mapping.items()}
        for lname in wanted:                       # honour the preferred-name order
            if lname not in by_lower:
                continue
            key, val = by_lower[lname]
            val = (val or "").strip().strip("'\"")
            if first_of_list and "," in val:
                val = val.split(",", 1)[0].strip()
            if val and valid(val):
                return val, "%s:%s" % (label, key)
    return None, ""


def sources_for(environ, stores):
    out = [("env", dict(environ))]
    for p in stores:
        out.append(("file:" + p, _parse(p)))
    return out


def _read_secret_file(raw_path, var):
    """Read the secret a *_FILE variable names. Returns (value, error). Never
    raises and never includes the contents in the error: variable, path and
    mode only. A group/world-accessible file is refused (family contract)."""
    path = os.path.expanduser((raw_path or "").strip())
    if not os.path.isfile(path):
        return "", "%s is set to %s but that file does not exist" % (var, path)
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        return "", "%s points at %s but its mode could not be read" % (var, path)
    if mode & 0o077:
        return "", ("%s points at %s with permissions %s -- a group/world-accessible "
                    "secret file is refused" % (var, path, oct(mode)))
    try:
        value = Path(path).read_text(encoding="utf-8", errors="replace").strip().strip("'\"")
    except OSError:
        return "", "%s points at %s but the file could not be read" % (var, path)
    if not value:
        return "", "%s is set to %s but the file is empty" % (var, path)
    return value, ""


def _credential(kind, environ, stores):
    """Internal: (Credential|None, file_error). Reads ONLY `kind`'s tables, so
    another kind's value can never satisfy this request."""
    kind = Kind(kind)
    for fv in KIND_FILE_VARS[kind]:
        raw = (environ.get(fv) or "").strip()
        if not raw:
            continue
        value, err = _read_secret_file(raw, fv)
        if err:
            return None, err
        if KIND_VALIDATORS[kind](value):
            return Credential(kind, value, "file-var:" + fv, fv), ""
        # placeholder-shaped file contents: a placeholder is not a credential
    value, source = _first(KIND_ALIASES[kind], sources_for(environ, stores),
                           KIND_VALIDATORS[kind])
    if value:
        return Credential(kind, value, source, source.rsplit(":", 1)[-1]), ""
    return None, ""


def credential_kind(name):
    """The Kind an env-var name belongs to, or None for a tenant binding /
    unknown name. Case-insensitive, matching the resolver."""
    low = (name or "").strip().lower()
    for kind, names in KIND_ALIASES.items():
        if any(n.lower() == low for n in names):
            return kind
    return None


def resolve_credential(kind, environ=None, stores=None, strict_files=True):
    """The credential of `kind`, or None. NEVER returns another kind.

    A broken *_FILE raises CredentialFileError when strict_files (default:
    a credentialed caller must not silently fall through to a weaker source);
    resolve() passes strict_files=False so the install-QC CLI still runs.
    """
    environ = os.environ if environ is None else environ
    stores = store_paths() if stores is None else stores
    cred, err = _credential(kind, environ, stores)
    if err and strict_files:
        raise CredentialFileError(err)
    return cred


def require_credential(kind, environ=None, stores=None):
    """resolve_credential, but a refusal instead of None. The refusal names the
    other kinds present -- e.g. an agency-only box says agency_pit was found and
    will not be substituted."""
    environ = os.environ if environ is None else environ
    stores = store_paths() if stores is None else stores
    kind = Kind(kind)
    cred, err = _credential(kind, environ, stores)
    if err:
        raise CredentialFileError(err)
    if cred is not None:
        return cred
    seen = [k for k in KIND_ALIASES if k is not kind and _credential(k, environ, stores)[0]]
    raise CredentialUnavailable(kind, seen)


def resolve_tenant_id(environ=None, stores=None):
    """The location id as (value, source) or (None, ""). Tenant binding only:
    reads the location-id aliases and GHL_LOCATION_ID_FILE, and NEVER derives a
    tenant from a token, a store path or a name."""
    environ = os.environ if environ is None else environ
    stores = store_paths() if stores is None else stores
    for fv in TENANT_ID_FILE_VARS:
        raw = (environ.get(fv) or "").strip()
        if not raw:
            continue
        value, _err = _read_secret_file(raw, fv)
        if "," in value:
            value = value.split(",", 1)[0].strip()
        if _is_location_id(value):
            return value, "file-var:" + fv
    return _first(TENANT_ID_NAMES, sources_for(environ, stores), _is_location_id,
                  first_of_list=True)


def _fp(pit):
    return hashlib.sha256(pit.encode()).hexdigest()[:12]


def _default_cache_path():
    for root in ("/data/.openclaw", os.path.expanduser("~/.openclaw")):
        if os.path.isdir(root):
            return root + "/state/ghl-location-cache.json"
    return None


def _http_get(url, pit):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + pit, "Version": "2021-07-28",
        "Accept": "application/json",
        # GHL sits behind Cloudflare, which rejects the default Python agent (error 1010).
        "User-Agent": "Mozilla/5.0 (compatible; openclaw-onboarding)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:  # noqa: BLE001 - offline / DNS / TLS: unresolved, never a crash
        return 0, ""


def location_for_pit(pit, http=None):
    """Ask the API which location a location-scoped token belongs to. Exactly one
    location visible -> that id; none or several (an agency token) -> None."""
    status, body = (http or _http_get)(API_BASE + "/locations/search?limit=2", pit)
    if status != 200:
        return None
    try:
        locs = json.loads(body).get("locations") or []
    except (ValueError, AttributeError):
        return None
    ids = [l.get("id") for l in locs if isinstance(l, dict) and _is_location_id(l.get("id"))]
    return ids[0] if len(ids) == 1 and len(locs) == 1 else None


def _cache_get(fp, path):
    if fp in _MEMO:
        return _MEMO[fp]
    try:
        v = json.loads(Path(path).read_text()).get(fp) if path else None
    except (OSError, ValueError):
        v = None
    return v if _is_location_id(v or "") else None


def _cache_put(fp, loc, path):
    _MEMO[fp] = loc
    if not path:
        return
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(p.read_text())
        except (OSError, ValueError):
            data = {}
        data[fp] = loc
        p.write_text(json.dumps(data, indent=1) + "\n")
    except OSError:
        pass


def resolve(environ=None, stores=None, http=None, cache_path="default", use_api=True):
    """Returns {"status": "ok"|"missing"|"unresolved", "location_id", "location_source",
    "pit", "pit_source", "note"}. `pit` is returned for in-process use only and is never
    printed by the CLI. status ok = location known (by name or via the API)."""
    environ = os.environ if environ is None else environ
    stores = store_paths() if stores is None else stores
    cache_path = _default_cache_path() if cache_path == "default" else cache_path
    # Tenant binding: location-id aliases + GHL_LOCATION_ID_FILE only.
    loc, loc_src = resolve_tenant_id(environ, stores)
    # Credential: location_pit ONLY -- an agency/firebase value can never land here.
    pit_cred, file_error = _credential(Kind.location_pit, environ, stores)
    pit = pit_cred.value if pit_cred else None
    pit_src = pit_cred.source if pit_cred else ""
    res = {"status": "ok", "location_id": loc, "location_source": loc_src,
           "pit": pit, "pit_source": pit_src, "note": ""}
    if loc:
        res["note"] = file_error
        return res
    if pit and use_api:
        fp = _fp(pit)
        loc = _cache_get(fp, cache_path)
        src = "state-cache"
        if not loc:
            loc = location_for_pit(pit, http)
            src = "api:/locations/search via " + pit_src
            if loc:
                _cache_put(fp, loc, cache_path)
        if loc:
            res.update(location_id=loc, location_source=src, note=file_error)
            return res
    if pit:
        res.update(status="unresolved", note=NOTE_UNRESOLVED)
    else:
        res.update(status="missing", note=NOTE_MISSING)
    if file_error:
        res["note"] = (res["note"] + " " + file_error).strip()
    return res


def shell_exports(res, environ=None):
    """`export` lines for eval. Sets only what is currently empty. The PIT, when it was
    found in a store but not in the env, is exported into the shell only (never printed
    anywhere else); the location id is an identifier, not a credential."""
    environ = os.environ if environ is None else environ
    lines = ["export GHL_CREDS_STATUS=%s" % shlex.quote(res["status"]),
             "export GHL_CREDS_NOTE=%s" % shlex.quote(res["note"])]
    if res["location_id"] and not environ.get("GOHIGHLEVEL_LOCATION_ID"):
        lines.append("export GOHIGHLEVEL_LOCATION_ID=%s" % shlex.quote(res["location_id"]))
    if res["pit"] and not environ.get("GOHIGHLEVEL_API_KEY"):
        lines.append("export GOHIGHLEVEL_API_KEY=%s" % shlex.quote(res["pit"]))
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    res = resolve()
    if "--json" in argv:
        print(json.dumps({k: v for k, v in res.items() if k != "pit"}, indent=1))
    else:
        print(shell_exports(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
