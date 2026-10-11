#!/usr/bin/env python3
"""video_link_delivery.py — hand a finished drama-song video's LINK to delivery,
under the joint-plan decision 5 rule: client-owned GHL first, R2 only as fallback.

WHAT THIS IS
------------
Joint plan section 5, row "U10 required" (verbatim scope): "Only client-owned
GHL-first verified video link and R2 fallback". Decision 5 (answered by Trevor,
2026-10-10) fixes the order: the finished video's PUBLIC CDN link is handed over
from the CLIENT'S OWN GoHighLevel (white label: Convert and Flow) FIRST; Cloudflare
R2 (bucket `drama-studio`) is the FALLBACK, used only when the client's box has no
working GHL path or the GHL upload fails. The R2 copy of a finished video is
deleted 7 days after delivery; GHL copies are never deleted by the studio.

This module owns EXACTLY that decision. It does not upload the video, does not
message anyone, does not schedule anything, and adds no second control service. It
answers one question: "which link may be handed over, and is it really that link?"

It reuses the shape of the repo's proven `ghl_media.py`
(06-ghl-install-pages/tools/ghl_media.py): bare-`urllib` (no `requests`), a fail-loud
`_require`, an INJECTABLE `fetcher` so every path is testable with no live call, a
strict output contract that can only ever describe a link that really resolved, and
a single JSON envelope on stdout with a real exit code. It is not a new delivery
framework.

"VERIFIED" IS NOT A LABEL
-------------------------
A link is deliverable only when `verify_link` has FETCHED it and the bytes it
served hash to the finished video's `expected_sha256`. A 200 that serves the wrong
media is a refusal, exactly like a link that does not resolve. Nothing unverified
is ever handed over.

THE FOUR HARD LINES (each is a guard in `choose_deliverable`)
-------------------------------------------------------------
  1. Never deliver an operator-owned link or an operator-hosted upload as if it
     were the client's. An operator-marked candidate is REFUSED outright (it is not
     silently skipped over into the fallback), and the delivered record's
     `ownership` is derived from a rule, never asserted by the caller.
  2. Never mix one client's media or link into another client's records. A record
     whose `record_client_id` is not the delivering `client_id` is REFUSED.
  3. Never print, log or embed a token or key value. A candidate URL that carries a
     secret in it (or any signed/expiring URL) is REFUSED, and every human-readable
     string this module emits is passed through `_redact`.
  4. Never ship an operator key to a client. This module resolves no credential at
     all: the client-owned GHL media link is a PUBLIC URL, so nothing here needs a
     key. The `token` field exists only so a caller can hand one in for redaction.

NO LIVE SEND, NO CLIENT-BOX WRITE
---------------------------------
There is no send and no client-box write in this file. Its only side effect is the
optional `--out` record file the operator names. Every check uses a local mock
server; no live credential is read or used.

CLI (repo envelope contract, see references/cli-contract.md)
-----------------------------------------------------------
    python3 video_link_delivery.py deliver --request <path.json> [--out <path.json>]

Exactly one JSON object on stdout (no log noise). Exit: 0 ok, 1 error, 4 rejected
(policy/trust refused). `waiting` (2) and `parked` (3) are unused here.

FAIL-LOUD
---------
Every refusal raises `DeliveryRefused` with a stable `reason_code`; an unexpected
failure is reported as `error` with a redacted message and never as a silent ok.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = "blackceo.video-link-delivery/envelope/v1"
TOOL_VERSION = "0.1.0"

# ── constants (the production rules; a test may override the host sets) ───────

# A client-owned GHL media link is the PUBLIC GCS object the media upload returns
# (ghl_media.upload_media): host `storage.googleapis.com`, path `/msgsndr/...`.
DEFAULT_GHL_HOSTS = ("storage.googleapis.com",)
DEFAULT_GHL_PATH_PREFIXES = ("/msgsndr/",)

# The studio's R2 FALLBACK bucket is served from a Cloudflare R2 origin.
DEFAULT_R2_HOST_SUFFIXES = (".r2.dev", ".r2.cloudflarestorage.com")

# Query-parameter names that mean "this URL carries a credential / expires". A
# delivered link must keep working, so a signed or token-bearing URL is refused.
_SIGNED_PARAM_NAMES = frozenset({
    "signature", "sig", "token", "key", "secret", "credential", "credentials",
    "access_key", "accesskeyid", "apikey", "api_key", "password",
    "x-amz-signature", "x-amz-credential", "x-amz-security-token", "x-amz-date",
})
_SIGNED_PARAM_PREFIXES = ("x-amz-", "x-goog-", "x-ms-")

# The R2 fallback copy is deleted 7 days after delivery (decision 5).
R2_RETENTION_DAYS = 7

# Streaming verify: never buffer a whole video in memory.
_CHUNK = 1024 * 1024
DEFAULT_MAX_BYTES = int(os.environ.get("VIDEO_LINK_MAX_BYTES", str(4 * 1024 * 1024 * 1024)))

_REQUIRED_REQUEST_FIELDS = ("client_id", "record_client_id", "expected_sha256")


# ── errors ────────────────────────────────────────────────────────────────────

class DeliveryRefused(RuntimeError):
    """A trust/policy refusal: nothing may be handed over. Exit 4 (`rejected`)."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message


class _LinkUnavailable(RuntimeError):
    """The CLIENT-OWNED GHL path could not be used (missing, or did not verify).

    Internal only: it is what authorises the R2 FALLBACK. It never escapes
    `choose_deliverable` — when the fallback cannot be used either, the refusal is
    a `DeliveryRefused` with a stable reason code.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ── small helpers (the ghl_media.py shape) ────────────────────────────────────

def _require(value: Any, name: str) -> None:
    """Reject empty / whitespace-only required values (fail loud, never silently
    proceed with a blank that would target the wrong resource)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise DeliveryRefused("bad-request", f"{name} is required and must be non-empty")


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _request_secrets(request: dict) -> list[str]:
    """The literal strings that must never appear in any output.

    `token` is the caller-held client credential; `secrets` is an explicit extra
    list. Both are treated as opaque values — this module never inspects, uses or
    resolves them, it only guarantees they cannot reach stdout, stderr or a record.
    """
    out: list[str] = []
    for key in ("token", "secrets"):
        val = request.get(key)
        if isinstance(val, str) and val:
            out.append(val)
        elif isinstance(val, list):
            out.extend([str(v) for v in val if str(v)])
    return out


def _redact(text: str, secrets: list[str]) -> str:
    """Mask every occurrence of every secret in `text`.

    Applied to EVERY human-readable string this module emits (`next_action`, every
    evidence line, every refusal message), so a credential can never be logged by
    accident. Defence in depth behind the `token-in-url` refusal, which is what
    stops a credential-bearing LINK from being delivered at all.
    """
    if not text:
        return text
    out = str(text)
    for secret in secrets:
        if secret:
            out = out.replace(secret, "<redacted>")
    return out


# ── the ownership / media rules ───────────────────────────────────────────────

def _host_of(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(str(url)).hostname or "").lower()
    except ValueError:
        return ""


def _path_of(url: str) -> str:
    try:
        return urllib.parse.urlsplit(str(url)).path or ""
    except ValueError:
        return ""


def _host_set(request: dict, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """The host rule for a candidate class.

    The DEFAULT is the production rule (a client-owned GHL media link is served by
    `storage.googleapis.com/msgsndr/...`; the R2 fallback by a Cloudflare R2
    origin). A request may pass an explicit list to point the same rule at a local
    mock server — the rule itself, not the guard, is what is being parameterised.
    """
    val = request.get(key)
    if isinstance(val, list) and val:
        return tuple(str(v).strip().lower() for v in val if str(v).strip())
    return default


def _is_ghl_media_url(url: str, request: dict) -> bool:
    """True iff `url` is a CLIENT-OWNED GHL media link (host + media path)."""
    host = _host_of(url)
    hosts = _host_set(request, "ghl_allowed_hosts", DEFAULT_GHL_HOSTS)
    if host not in hosts:
        return False
    prefixes = request.get("ghl_path_prefixes")
    prefixes = tuple(prefixes) if isinstance(prefixes, list) and prefixes else DEFAULT_GHL_PATH_PREFIXES
    path = _path_of(url)
    return any(path.startswith(str(p)) for p in prefixes)


def _is_r2_url(url: str, request: dict) -> bool:
    """True iff `url` is served by the studio's R2 FALLBACK origin."""
    host = _host_of(url)
    exact = request.get("r2_allowed_hosts")
    if isinstance(exact, list) and exact:
        return host in tuple(str(v).strip().lower() for v in exact if str(v).strip())
    suffix = request.get("r2_host_suffixes")
    suffixes = tuple(suffix) if isinstance(suffix, list) and suffix else DEFAULT_R2_HOST_SUFFIXES
    return any(host.endswith(str(s)) for s in suffixes)


def _is_operator_owned(candidate: dict, request: dict) -> bool:
    """True iff this candidate is marked as the OPERATOR's, not the client's.

    Two independent markers, because either one alone can be got wrong: the
    owning GHL location id, and the serving host. A candidate carrying either is
    the operator's and may never be delivered as the client's.
    """
    owner = str(candidate.get("owner_location_id", "")).strip()
    operator_ids = request.get("operator_location_ids") or []
    if owner and owner in {str(v).strip() for v in operator_ids}:
        return True
    operator_hosts = request.get("operator_hosts") or []
    host = _host_of(candidate.get("url", ""))
    return bool(host) and host in {str(v).strip().lower() for v in operator_hosts}


def _embeds_secret(url: str, secrets: list[str]) -> bool:
    """True iff `url` carries a credential or would expire.

    Either an actual secret value appears in the URL, or the query string names a
    signed/expiring parameter. An expiring URL cannot be the client's permanent
    link, and a URL with a credential in it would put that credential in the
    delivered record — both are refused.
    """
    text = str(url)
    for secret in secrets:
        if secret and secret in text:
            return True
    try:
        query = urllib.parse.parse_qsl(urllib.parse.urlsplit(text).query, keep_blank_values=True)
    except ValueError:
        return True
    for name, _value in query:
        low = name.strip().lower().rstrip("[]")
        if low in _SIGNED_PARAM_NAMES or low.startswith(_SIGNED_PARAM_PREFIXES):
            return True
    return False


# ── verification: the step that makes "verified" mean something ───────────────

def verify_link(
    url: str,
    expected_sha256: str,
    *,
    fetcher: Callable[[urllib.request.Request, int], Any] | None = None,
    timeout: int = 30,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    """FETCH `url` and prove it serves the finished video, byte for byte.

    A link counts as verified only when the fetch returns HTTP 200 AND the streamed
    bytes hash to `expected_sha256`. A 200 that serves something else is a failure,
    not a pass — that is the difference between "resolved" and "the right media".

    FAIL-LOUD, never fatal: every failure is returned as `{ok: False, reason: ...}`
    so the caller decides between the fallback and a refusal. Nothing is fabricated:
    `sha256` is the digest actually computed (`""` when nothing was read).

    Args:
        url: The link to fetch.
        expected_sha256: The finished video's sha256 (lower-case hex).
        fetcher: Injectable `(Request, timeout) -> response-like`; default
            `urllib.request.urlopen`. Tests pass a local mock transport.
        timeout: HTTP timeout seconds.
        max_bytes: Hard cap on streamed bytes (a video that exceeds it is refused
            rather than buffered).

    Returns:
        `{ok, url, http, sha256, bytes, reason}`.
    """
    result = {"ok": False, "url": url, "http": 0, "sha256": "", "bytes": 0, "reason": ""}
    try:
        req = urllib.request.Request(url, method="GET")
        resp = fetcher(req, timeout) if fetcher is not None else urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        result["http"] = int(getattr(exc, "code", 0) or 0)
        result["reason"] = "http-%d" % result["http"]
        return result
    except (urllib.error.URLError, OSError, ValueError) as exc:
        result["reason"] = "unreachable"
        # The reason carries the exception CLASS only — never its text, which can
        # echo the URL (and therefore anything the URL carries).
        result["error_class"] = type(exc).__name__
        return result

    try:
        status = int(resp.getcode())
    except Exception:  # noqa: BLE001 — a transport that cannot report a status is a failure
        result["reason"] = "no-status"
        return result
    result["http"] = status
    if status != 200:
        result["reason"] = "http-%d" % status
        return result

    digest = hashlib.sha256()
    total = 0
    try:
        while True:
            chunk = resp.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                result["bytes"] = total
                result["reason"] = "too-large"
                return result
            digest.update(chunk)
    except (urllib.error.URLError, OSError) as exc:
        result["bytes"] = total
        result["reason"] = "read-failed"
        result["error_class"] = type(exc).__name__
        return result

    result["sha256"] = digest.hexdigest()
    result["bytes"] = total
    if result["sha256"].lower() != str(expected_sha256).strip().lower():
        result["reason"] = "media-mismatch"
        return result
    result["ok"] = True
    return result


def _require_verified(link: dict, expected_sha256: str, fetcher, timeout: int) -> dict:
    """`verify_link`, but a failure becomes `_LinkUnavailable` — which is what
    authorises the R2 fallback for the GHL path, and is turned into a refusal when
    the fallback cannot be used either."""
    v = verify_link(link.get("url", ""), expected_sha256, fetcher=fetcher, timeout=timeout)
    if not v["ok"]:
        raise _LinkUnavailable(v["reason"] or "unverified")
    return v


# ── selection ────────────────────────────────────────────────────────────────

def _all_candidates(request: dict) -> list[tuple[str, dict]]:
    """Every candidate a request names, for the guards that apply to ALL of them.

    `stored_link` is a previously recorded link: provenance, never a deliverable
    (it may be stale, or another owner's), but it is still guarded so a foreign or
    credential-bearing link can never be mixed into the record.
    """
    out: list[tuple[str, dict]] = []
    for name in ("ghl_candidate", "r2_candidate", "stored_link"):
        cand = request.get(name)
        if isinstance(cand, dict) and str(cand.get("url", "")).strip():
            out.append((name, cand))
    return out


def _select_ghl_candidate(request: dict) -> dict | None:
    """GHL-first: the deliverable GHL link is the FRESH client-owned candidate
    uploaded to the CLIENT'S OWN media library. A stored/previous link is never
    preferred — it may be stale or belong to another owner."""
    return request.get("ghl_candidate") or None


def _delivered(link: dict, verified: dict, source: str, fallback_reason: str | None, request: dict) -> dict:
    """Build the delivered record. `ownership` is DERIVED from `source`, never
    taken from the caller — an operator-hosted upload can therefore never be
    labelled as the client's."""
    if source == "ghl":
        ownership = "client-ghl"
        if not _is_ghl_media_url(link.get("url", ""), request):
            raise DeliveryRefused(
                "record-invariant",
                "refusing to record a client-owned GHL delivery for a link that is not "
                "a client-owned GHL media URL",
            )
    elif source == "r2":
        ownership = "studio-r2-fallback"
        if not _is_r2_url(link.get("url", ""), request):
            raise DeliveryRefused(
                "record-invariant",
                "refusing to record an R2 fallback delivery for a link that is not served "
                "by the studio R2 origin",
            )
    else:  # pragma: no cover — guarded by the callers
        raise DeliveryRefused("record-invariant", f"unknown delivery source {source!r}")

    record: dict[str, Any] = {
        "url": link.get("url", ""),
        "source": source,
        "ownership": ownership,
        "fallback": source == "r2",
        "client_id": request.get("client_id", ""),
        "client_location_id": request.get("client_location_id", ""),
        "sha256": verified.get("sha256", ""),
        "bytes": verified.get("bytes", 0),
        "verified_http": verified.get("http", 0),
        "verified_at": _now_iso(),
    }
    if source == "r2":
        record["fallback_reason"] = fallback_reason or "ghl-unavailable"
        # Decision 5: the R2 copy of a finished video is deleted 7 days after
        # delivery. The studio-owned GHL copy is never deleted.
        # ponytail: this records the deadline only; the deletion itself is the
        # U5 owned-run cleanup receipt, not built here.
        delete_at = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=R2_RETENTION_DAYS)
        record["r2_delete_after"] = delete_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return record


def choose_deliverable(request: dict, *, fetcher=None, timeout: int = 30) -> dict:
    """Decide the ONE link that may be handed over. Raises `DeliveryRefused` else.

    Order is load-bearing and is the whole point of this unit:

      1. cross-client guard  — the record and the delivery must be the same client
      2. credential guard    — no candidate URL may carry or embed a secret
      3. operator guard      — an operator-marked candidate is refused outright
      4. GHL-first           — the client-owned GHL candidate, VERIFIED, wins
      5. R2 fallback         — only when the client-owned GHL path was unavailable,
                               and only when the R2 copy VERIFIES
      6. otherwise refuse    — nothing unverified is ever handed over

    Args:
        request: the delivery request (see the module docstring / README).
        fetcher: injectable transport, forwarded to `verify_link` (tests only).
        timeout: HTTP timeout seconds.

    Returns:
        The delivered record (`ownership` derived from the source).

    Raises:
        DeliveryRefused: with a stable `reason_code`. Never returns an unverified
            or foreign link.
    """
    if not isinstance(request, dict):
        raise DeliveryRefused("bad-request", "request must be a JSON object")
    for field in _REQUIRED_REQUEST_FIELDS:
        _require(request.get(field), field)
    _require(request.get("client_location_id"), "client_location_id")

    secrets = _request_secrets(request)

    # 1) Never mix one client's media or link into another client's records.
    if str(request.get("record_client_id", "")) != str(request.get("client_id", "")):
        raise DeliveryRefused(
            "cross-client-delivery",
            _redact(
                "refusing to deliver a link into a record belonging to another client "
                f"(record_client_id={request.get('record_client_id')!r}, "
                f"client_id={request.get('client_id')!r})",
                secrets,
            ),
        )

    # 2) Never deliver a link that carries or embeds a token or key value.
    for name, cand in _all_candidates(request):
        if _embeds_secret(str(cand.get("url", "")), secrets):
            raise DeliveryRefused(
                "token-in-url",
                _redact(
                    f"refusing to deliver {name}: its URL carries a credential or is a "
                    "signed/expiring link, and a delivered link must neither embed a "
                    "secret nor expire",
                    secrets,
                ),
            )

    # 3) Never deliver an operator-owned link or an operator-hosted upload as if it
    #    were the client's. Refused outright — never skipped over into the fallback,
    #    because a fallback around an operator link would hide the mix-up.
    for name, cand in _all_candidates(request):
        if _is_operator_owned(cand, request):
            raise DeliveryRefused(
                "operator-owned-link",
                _redact(
                    f"refusing to deliver {name}: it is marked as OPERATOR-owned (its "
                    "owning location id or serving host is the operator's), and only a "
                    "client-owned link may be handed to the client",
                    secrets,
                ),
            )

    # 4) GHL-first: the client-owned link, verified, is the deliverable.
    ghl = _select_ghl_candidate(request)
    ghl_unavailable = "ghl-missing"
    if ghl is not None:
        if not _is_ghl_media_url(ghl.get("url", ""), request):
            raise DeliveryRefused(
                "ghl-candidate-not-client-media",
                _redact(
                    "refusing the GHL candidate: it is not a client-owned GHL media link "
                    "(expected the client's own GoHighLevel media host and media path)",
                    secrets,
                ),
            )
        if str(ghl.get("owner_location_id", "")) != str(request.get("client_location_id", "")):
            raise DeliveryRefused(
                "ghl-candidate-not-client-owned",
                _redact(
                    "refusing the GHL candidate: its owning location id is not this "
                    "client's, so it is not the client's own media",
                    secrets,
                ),
            )
        try:
            verified = _require_verified(ghl, request["expected_sha256"], fetcher, timeout)
        except _LinkUnavailable as exc:
            ghl_unavailable = "ghl-unverified:" + exc.reason
        else:
            return _delivered(ghl, verified, "ghl", None, request)

    # 5) R2 is a FALLBACK, used only because the client-owned GHL path was not usable.
    r2 = request.get("r2_candidate")
    if isinstance(r2, dict) and str(r2.get("url", "")).strip():
        if not _is_r2_url(r2.get("url", ""), request):
            raise DeliveryRefused(
                "r2-candidate-not-studio-media",
                _redact(
                    "refusing the R2 fallback candidate: it is not served by the studio's "
                    "R2 origin",
                    secrets,
                ),
            )
        try:
            verified = _require_verified(r2, request["expected_sha256"], fetcher, timeout)
        except _LinkUnavailable as exc:
            raise DeliveryRefused(
                "fallback-unverified",
                _redact(
                    "refusing to deliver the R2 fallback: it did not verify "
                    f"({exc.reason}) — nothing unverified is ever handed over",
                    secrets,
                ),
            ) from exc
        return _delivered(r2, verified, "r2", ghl_unavailable, request)

    # 6) Nothing verified: refuse rather than hand over anything unverified.
    raise DeliveryRefused(
        "no-verified-deliverable-link",
        _redact(
            f"refusing to deliver: no verified client-owned GHL link and no verified R2 "
            f"fallback ({ghl_unavailable}). Nothing unverified is ever handed over",
            secrets,
        ),
    )


# ── envelope + CLI ───────────────────────────────────────────────────────────

def _envelope(command: str, outcome: str, reason_code: str, next_action: str, *, data=None, evidence=None, run_id=None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "command": command,
        "run_id": run_id or uuid.uuid4().hex[:12],
        "outcome": outcome,
        "reason_code": reason_code,
        "next_action": next_action,
        "evidence": list(evidence or []),
        "data": dict(data or {}),
    }


_EXIT = {"ok": 0, "error": 1, "waiting": 2, "parked": 3, "rejected": 4}


def _emit(env: dict) -> int:
    sys.stdout.write(json.dumps(env, ensure_ascii=True) + "\n")
    return _EXIT.get(env.get("outcome", "error"), 1)


def _cmd_deliver(args) -> int:
    try:
        raw = Path(args.request).read_text(encoding="utf-8")
        request = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return _emit(_envelope(
            "deliver", "error", "bad-request",
            f"the request file could not be read as JSON ({type(exc).__name__})",
        ))

    secrets = _request_secrets(request if isinstance(request, dict) else {})
    try:
        record = choose_deliverable(request, timeout=args.timeout)
    except DeliveryRefused as exc:
        return _emit(_envelope(
            "deliver", "rejected", exc.reason_code,
            _redact(exc.message, secrets),
        ))
    except Exception as exc:  # noqa: BLE001 — never a silent ok, never a traceback
        return _emit(_envelope(
            "deliver", "error", "internal-error",
            _redact(f"delivery failed unexpectedly ({type(exc).__name__})", secrets),
        ))

    if args.out:
        try:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            return _emit(_envelope(
                "deliver", "error", "record-write-failed",
                f"the delivered record could not be written ({type(exc).__name__})",
            ))

    evidence = [
        f"source={record['source']}",
        f"ownership={record['ownership']}",
        f"verified_http={record['verified_http']}",
        f"bytes={record['bytes']}",
        f"sha256={record['sha256']}",
    ]
    if record.get("fallback"):
        evidence.append(f"fallback_reason={record['fallback_reason']}")
    return _emit(_envelope(
        "deliver", "ok", "delivered",
        "hand the verified client-owned link to the delivery record",
        data={"delivery": record},
        evidence=evidence,
    ))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Drama studio video-link delivery (client owned GHL first, R2 fallback).")
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("deliver", help="choose and verify the ONE link that may be delivered")
    d.add_argument("--request", required=True, help="path to the delivery request JSON")
    d.add_argument("--out", default=None, help="optional path to write the delivered record JSON")
    d.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    d.set_defaults(func=_cmd_deliver)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
