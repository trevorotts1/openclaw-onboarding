#!/usr/bin/env python3
"""Asset registry and preparation worklist for Skill 38 (T-07).

T-06 answers "what is the business?". This module answers the next question a
30-day campaign plan needs: "what does the client actually have, what is
missing, and what must be prepared before any campaign can run?"

It builds on the accepted acquisition brief (`acquisition_brief.py`) rather
than duplicating it:

  * the brief's asset kinds and required-for-campaign set are imported and
    asserted as a subset of this registry's kinds, so the two can never drift
    apart silently;
  * the brief's provenances and trusted-provenance rule are reused, so an
    assumption is refused here exactly as it is refused there;
  * `sync_from_brief` imports the brief's present/absent assessments with
    their evidence, and `link_defaults` joins each asset to the brief fact
    that references it;
  * preparation-plan inputs are resolved from trusted brief facts, and any
    input the brief cannot supply is listed as explicitly blocked.

Doctrine, enforced in code:

  * a missing asset is recorded as missing. It is never invented, never
    written as a placeholder path/label, and never promoted to ready by
    absence of a complaint;
  * an asset claim must carry a source (client-provided or discovered) and an
    evidence pointer. A claim with no provenance, or one resting on an
    assumption, is refused. The pointer itself must be real shape: an existing
    path, a usable http/https URL, or a named source. A string that merely
    contains "://" proves nothing;
  * the preparation worklist names the exact deliverable and the inputs it
    needs. It plans preparation only: nothing here generates, downloads or
    fabricates an asset;
  * campaign readiness is green only when every required kind is present with
    trusted provenance. Otherwise it names every blocker;
  * state lives in one JSON document written by atomic replace under an
    exclusive lock, and re-applying identical operations is a no-op, so two
    processes produce the same bytes as one.

Python 3 standard library only.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as _datetime
import json
import os
import re
import tempfile
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

try:  # the tools directory is normally on sys.path
    import acquisition_brief as _brief
except ImportError:  # pragma: no cover - package-style import
    from . import acquisition_brief as _brief  # type: ignore

SCHEMA = "skill38.asset_registry.v1"
CAMPAIGN_DAYS = 30

# --------------------------------------------------------------------- kinds
# The seven kinds a campaign planner must know about. The first five are the
# brief's kinds; video and prior_posts are additional campaign inputs.
ASSET_KINDS: Tuple[str, ...] = (
    "logo",
    "photos",
    "testimonials",
    "offer_documents",
    "links",
    "video",
    "prior_posts",
)

# A 30-day campaign cannot run without a mark, imagery, proof, the offer
# document and at least one owned link. Video and prior posts help, but their
# absence does not block a campaign.
REQUIRED_FOR_CAMPAIGN = frozenset(
    {"logo", "photos", "testimonials", "offer_documents", "links"}
)

# The brief owns its own required set. It must remain a subset of ours: this
# module is the stricter campaign gate, and it never quietly relaxes the brief.
_BRIEF_REQUIRED = frozenset(_brief.ASSET_REQUIRED_FOR_CAMPAIGN)
if not _BRIEF_REQUIRED <= REQUIRED_FOR_CAMPAIGN:
    raise RuntimeError(
        "asset_registry required kinds %r no longer cover the acquisition "
        "brief's required kinds %r"
        % (sorted(REQUIRED_FOR_CAMPAIGN), sorted(_BRIEF_REQUIRED))
    )
if not set(_brief.ASSET_KINDS) <= set(ASSET_KINDS):
    raise RuntimeError(
        "asset_registry kinds %r no longer cover the acquisition brief's "
        "kinds %r" % (list(ASSET_KINDS), list(_brief.ASSET_KINDS))
    )

# ------------------------------------------------------------------- sources
SOURCE_CLIENT_PROVIDED = "client_provided"
SOURCE_DISCOVERED = "discovered"
SOURCE_MUST_PREPARE = "must_prepare"
# An asset this registry's own preparation worklist produced. It is never
# relabelled client_provided: the client did not supply it.
SOURCE_PREPARED = "prepared"
SOURCES = (
    SOURCE_CLIENT_PROVIDED,
    SOURCE_DISCOVERED,
    SOURCE_MUST_PREPARE,
    SOURCE_PREPARED,
)
# Sources that assert an asset exists. must_prepare asserts the opposite.
PRESENT_SOURCES = (
    SOURCE_CLIENT_PROVIDED,
    SOURCE_DISCOVERED,
    SOURCE_PREPARED,
)

_BRIEF_SOURCE_MAP = {
    _brief.PROVENANCE_CLIENT_STATED: SOURCE_CLIENT_PROVIDED,
    _brief.PROVENANCE_DISCOVERED: SOURCE_DISCOVERED,
}

# ----------------------------------------------------------------- readiness
READY = "ready"
MISSING = "missing"
MUST_PREPARE = "must_prepare"
UNASSESSED = "unassessed"
READINESS_STATES = (READY, MISSING, MUST_PREPARE, UNASSESSED)


class AssetRegistryError(Exception):
    """Base class for registry failures."""


class UnknownKindError(AssetRegistryError):
    """The requested asset kind is not part of the registry."""


class InvalidClaimError(AssetRegistryError):
    """An asset claim is malformed, unprovenanced, or self-contradictory."""


class UnprovenancedClaimError(InvalidClaimError):
    """An asset is claimed without a source or without evidence."""


class UntrustedProvenanceError(InvalidClaimError):
    """An asset claim rests on an assumption or an unverified source."""


class MissingAssetError(AssetRegistryError):
    """A ready asset was required, but the asset is missing or unassessed."""


class UnknownBriefFactError(AssetRegistryError):
    """The fact id is not part of the acquisition brief."""


class RegistryCorruptError(AssetRegistryError):
    """The registry file exists but cannot be read as a valid registry."""


# ---------------------------------------------------------- preparation plan


@dataclasses.dataclass(frozen=True)
class PreparationInput:
    """One input the preparer must have before the work can start."""

    label: str
    fact_id: Optional[str] = None


@dataclasses.dataclass(frozen=True)
class PreparationSpec:
    """The exact deliverable for a missing kind and the inputs it needs."""

    kind: str
    deliverable: str
    inputs: Tuple[PreparationInput, ...]


def _inp(label: str, fact_id: Optional[str] = None) -> PreparationInput:
    return PreparationInput(label=label, fact_id=fact_id)


PREPARATION_SPECS: Dict[str, PreparationSpec] = {
    "logo": PreparationSpec(
        kind="logo",
        deliverable=(
            "A primary logo lockup (horizontal) as PNG with a transparent "
            "background, plus a 1024x1024 square icon for avatars"
        ),
        inputs=(
            _inp("business legal or trading name", "business.legal_name"),
            _inp("any existing mark, wordmark or rough sketch"),
            _inp("brand colours, if any"),
        ),
    ),
    "photos": PreparationSpec(
        kind="photos",
        deliverable=(
            "Six usable photographs: one of the owner or team, two of the "
            "work or product in use, two of the premises or setting, and one "
            "clean shot usable as a wide banner"
        ),
        inputs=(
            _inp("what the business sells and to whom", "business.what_you_do"),
            _inp("the service area", "geography.service_area"),
            _inp("access to the business location or product"),
        ),
    ),
    "testimonials": PreparationSpec(
        kind="testimonials",
        deliverable=(
            "Three testimonial texts, each with the reviewer's name, the "
            "specific result they got, and written permission to publish"
        ),
        inputs=(
            _inp("the main offer the reviewer bought", "offers.primary_offer"),
            _inp("contactable past customers"),
            _inp("published consent from each reviewer"),
        ),
    ),
    "offer_documents": PreparationSpec(
        kind="offer_documents",
        deliverable=(
            "A one-page offer document: what the buyer gets, the price, the "
            "terms, and what happens after they buy"
        ),
        inputs=(
            _inp("the main offer", "offers.primary_offer"),
            _inp("the price", "offers.price_range"),
        ),
    ),
    "links": PreparationSpec(
        kind="links",
        deliverable=(
            "A canonical destination link per owned channel (booking page, "
            "profile, store) that the campaign can point at without redirects"
        ),
        inputs=(
            _inp("which accounts the business controls", "channels.owned_channels"),
            _inp("admin access to those accounts", "channels.channel_access"),
            _inp("final destination URLs"),
        ),
    ),
    "video": PreparationSpec(
        kind="video",
        deliverable=(
            "One 30-60 second vertical proof video of the work in progress, "
            "with usable audio or a caption script"
        ),
        inputs=(
            _inp("the main offer the video must sell", "offers.primary_offer"),
            _inp("a subject willing to appear on camera"),
        ),
    ),
    "prior_posts": PreparationSpec(
        kind="prior_posts",
        deliverable=(
            "An export of the last 90 days of published posts per owned "
            "channel, so proven angles are reused rather than guessed"
        ),
        inputs=(
            _inp("which accounts the business controls", "channels.owned_channels"),
            _inp("admin access to those accounts", "channels.channel_access"),
        ),
    ),
}

# Assets that a brief fact references. Linking is a join, never a copy: the
# fact keeps its own value and provenance.
DEFAULT_FACT_LINKS: Dict[str, str] = {
    "testimonials": "proof.proof_assets",
    "offer_documents": "offers.primary_offer",
    "links": "channels.owned_channels",
}


def _utc_now() -> _datetime.datetime:
    return _datetime.datetime.now(_datetime.timezone.utc)


def _iso(moment: _datetime.datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_datetime.timezone.utc)
    return moment.astimezone(_datetime.timezone.utc).isoformat(
        timespec="microseconds"
    )


# ----------------------------------------------------------- evidence shapes
# An evidence pointer names where the asset really is. Three shapes are
# accepted: an existing path on this machine, a genuine web URL, or -- for a
# claim the client or a discovery source states -- a named source such as the
# person or system that holds it. Every other string is a fabricated pointer
# and is refused. A bare "://" is never proof of anything.
#
# The achievable bar for a URL, stated honestly: OFFLINE EXISTENCE CANNOT BE
# VERIFIED. What can be verified is that the string is structurally a URL that
# could name a real asset -- scheme http or https, a host with a dot, and a
# host that is not a special-use name (RFC 2606/6761 reserve test, example,
# invalid, localhost, local and example.com/net/org precisely because they can
# never resolve to a real asset). Whether that URL serves the asset is checked
# by whoever consumes it, never claimed here.
_URL_SCHEMES = ("http", "https")
_URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.[A-Za-z0-9]{1,8}$")
_RESERVED_TLDS = frozenset({"test", "example", "invalid", "localhost", "local"})
_RESERVED_HOSTS = frozenset(
    {"example.com", "example.net", "example.org", "localhost"}
)


def _looks_like_url(evidence: str) -> bool:
    """True when the string claims to be a URI rather than a path or a name."""
    if "://" in evidence:
        return True
    if _WINDOWS_DRIVE_RE.match(evidence):
        return False
    return bool(_URL_SCHEME_RE.match(evidence))


def _looks_like_path(evidence: str) -> bool:
    """True when the string claims to be a file location rather than a name."""
    separators = ["/", "\\", os.sep]
    if os.altsep:
        separators.append(os.altsep)
    if any(separator in evidence for separator in separators):
        return True
    if evidence.startswith(("~", ".")):
        return True
    return bool(_FILENAME_RE.match(evidence))


def _check_url_shape(evidence: str) -> str:
    try:
        parts = urlsplit(evidence)
        host = (parts.hostname or "").strip().lower()
    except ValueError as exc:  # malformed bracketed host, bad port
        raise UnprovenancedClaimError(
            "evidence %r is not a usable URL: %s" % (evidence, exc)
        ) from exc
    scheme = (parts.scheme or "").lower()
    if scheme not in _URL_SCHEMES:
        raise UnprovenancedClaimError(
            "evidence %r is not a usable URL: only http and https can point at "
            "a web asset" % evidence
        )
    if not parts.netloc or not host or "." not in host:
        raise UnprovenancedClaimError(
            "evidence %r is not a usable URL: it names no dotted host"
            % evidence
        )
    if (
        host.rsplit(".", 1)[-1] in _RESERVED_TLDS
        or any(
            host == reserved or host.endswith("." + reserved)
            for reserved in _RESERVED_HOSTS
        )
    ):
        raise UnprovenancedClaimError(
            "evidence %r is not a usable URL: host %r is a reserved special-use "
            "name that can never name a real asset" % (evidence, host)
        )
    return evidence


class AssetRegistry:
    """Per-tenant asset registry with a preparation worklist and a gate.

    All state lives in one JSON document written by atomic replace under an
    exclusive lock. Two processes applying the same operations produce the
    same bytes; a interrupted writer leaves the previous valid document.
    """

    def __init__(
        self,
        path: str,
        *,
        brief: Optional[Any] = None,
        clock: Optional[Callable[[], _datetime.datetime]] = None,
    ) -> None:
        self.path = os.path.abspath(path)
        self.brief = brief
        self._clock = clock or _utc_now
        self._state: Dict[str, Any] = self._empty_state()
        self.load()

    # ---------------------------------------------------------------- state

    def _empty_state(self) -> Dict[str, Any]:
        now = _iso(self._clock())
        return {
            "schema": SCHEMA,
            "created_at": now,
            "updated_at": now,
            "assets": {},
            "links": {},
            "supplied_inputs": {},
            "events": [],
        }

    def _now(self) -> str:
        return _iso(self._clock())

    def load(self) -> "AssetRegistry":
        if not os.path.exists(self.path):
            return self
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, ValueError) as exc:
            raise RegistryCorruptError(
                "cannot read asset registry at %s: %s" % (self.path, exc)
            ) from exc
        if not isinstance(document, dict):
            raise RegistryCorruptError(
                "asset registry at %s is not a JSON object" % self.path
            )
        if document.get("schema") != SCHEMA:
            raise RegistryCorruptError(
                "asset registry at %s has schema %r, expected %r"
                % (self.path, document.get("schema"), SCHEMA)
            )
        for key in ("assets", "links", "supplied_inputs"):
            if not isinstance(document.get(key), dict):
                raise RegistryCorruptError(
                    "asset registry at %s is missing %r" % (self.path, key)
                )
        if not isinstance(document.get("events"), list):
            raise RegistryCorruptError(
                "asset registry at %s is missing 'events'" % self.path
            )
        self._state = document
        return self

    def save(self) -> None:
        """Atomically persist. A crash leaves the previous document intact."""
        self._state["updated_at"] = self._now()
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix="." + os.path.basename(self.path) + ".",
            suffix=".tmp",
            dir=directory,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    self._state,
                    handle,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        self._fsync_directory(directory)

    @staticmethod
    def _fsync_directory(directory: str) -> None:
        try:
            descriptor = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)

    @contextlib.contextmanager
    def _locked(self):
        """Exclusive cross-process lock around load-mutate-save.

        The lock file is `<registry>.lock` and is intentionally left in place.
        ponytail: no fcntl (Windows) means single-writer is assumed; add an
        msvcrt branch only if this ever runs on Windows.
        """
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        handle = open(self.path + ".lock", "a+", encoding="utf-8")
        try:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except ImportError:  # pragma: no cover - Windows
                pass
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except ImportError:  # pragma: no cover - Windows
                pass
            handle.close()

    def _event(self, name: str, **fields: Any) -> None:
        event = {"event": name, "at": self._now()}
        event.update(fields)
        self._state["events"].append(event)

    # ------------------------------------------------------------ validation

    @staticmethod
    def _check_kind(kind: Any) -> str:
        if kind not in ASSET_KINDS:
            raise UnknownKindError(
                "%r is not an asset kind; expected one of %s"
                % (kind, ", ".join(ASSET_KINDS))
            )
        return kind

    @staticmethod
    def _check_evidence(evidence: Any) -> str:
        if not isinstance(evidence, str):
            raise UnprovenancedClaimError(
                "an asset claim needs an evidence pointer (a path, link or "
                "named source), not %r" % (evidence,)
            )
        cleaned = evidence.strip()
        if not cleaned:
            raise UnprovenancedClaimError(
                "an asset claim needs a non-empty evidence pointer"
            )
        return cleaned

    @staticmethod
    def _check_evidence_shape(evidence: str, *, allow_named: bool) -> str:
        """Refuse a fabricated pointer. Shape discipline, not existence faith.

        Accepted: an existing path, a URL that clears `_check_url_shape`, and
        (when `allow_named`) a named source -- a plain name of who or what
        holds the asset. Everything else claims to be a location while naming
        nothing that exists, which is a placeholder, not evidence.
        """
        if os.path.exists(evidence):
            return evidence
        if _looks_like_url(evidence):
            return _check_url_shape(evidence)
        if _looks_like_path(evidence):
            raise UnprovenancedClaimError(
                "evidence %r names no file that exists; a path pointing at "
                "nothing is a placeholder, not an asset" % evidence
            )
        if not allow_named:
            raise UnprovenancedClaimError(
                "evidence %r is neither an existing path nor a usable http/"
                "https URL; the finished asset must be pointed at" % evidence
            )
        if not any(character.isalnum() for character in evidence):
            raise UnprovenancedClaimError(
                "evidence %r is not a name of anything; a named source must "
                "actually name one" % evidence
            )
        return evidence

    @staticmethod
    def _check_detail(detail: Any) -> Optional[str]:
        if detail is None:
            return None
        if not isinstance(detail, str):
            raise InvalidClaimError("asset detail must be a string or None")
        cleaned = detail.strip()
        return cleaned or None

    # ---------------------------------------------------------------- claims

    def record_present(
        self,
        kind: str,
        *,
        source: str,
        evidence: str,
        detail: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an asset the client has, with its provenance.

        Refused: no source, a source that asserts something else (must_prepare),
        an assumed provenance, an empty evidence pointer, and any pointer that
        only looks like one -- a URL-shaped string that is not a usable
        http/https URL, or a path that names no file that exists. A named
        source (who holds it, where it came from) is accepted as evidence for a
        stated claim. Re-recording the identical claim is a no-op: same record,
        no new event, same timestamp.
        """
        kind = self._check_kind(kind)
        if source not in PRESENT_SOURCES:
            raise UnprovenancedClaimError(
                "a present asset needs source %s, got %r"
                % (" or ".join(PRESENT_SOURCES), source)
            )
        evidence = self._check_evidence(evidence)
        evidence = self._check_evidence_shape(evidence, allow_named=True)
        detail = self._check_detail(detail)

        with self._locked():
            self.load()
            existing = self._state["assets"].get(kind)
            if (
                isinstance(existing, dict)
                and existing.get("readiness") == READY
                and existing.get("source") == source
                and existing.get("evidence") == evidence
                and existing.get("detail") == detail
            ):
                return dict(existing)
            record = {
                "kind": kind,
                "readiness": READY,
                "source": source,
                "evidence": evidence,
                "detail": detail,
                "recorded_at": self._now(),
                "required_for_campaign": kind in REQUIRED_FOR_CAMPAIGN,
            }
            self._state["assets"][kind] = record
            self._state["links"].pop(kind, None)
            self._state["supplied_inputs"].pop(kind, None)
            self._event(
                "asset_recorded",
                kind=kind,
                readiness=READY,
                source=source,
            )
            self.save()
            return dict(record)

    def record_missing(
        self,
        kind: str,
        reason: str,
        *,
        prepare: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Record that the client does not have this asset.

        No value, path or placeholder is written: only the kind, the readiness
        and the stated reason. `prepare` defaults to True for required kinds,
        so a required gap lands on the preparation worklist automatically.
        """
        kind = self._check_kind(kind)
        if not isinstance(reason, str) or not reason.strip():
            raise InvalidClaimError(
                "a missing asset needs a non-empty reason; it is never "
                "recorded silently"
            )
        reason = reason.strip()
        if prepare is None:
            prepare = kind in REQUIRED_FOR_CAMPAIGN

        with self._locked():
            self.load()
            existing = self._state["assets"].get(kind)
            if (
                isinstance(existing, dict)
                and existing.get("readiness") == MISSING
                and existing.get("reason") == reason
                and existing.get("prepare") is bool(prepare)
            ):
                return dict(existing)
            record = {
                "kind": kind,
                "readiness": MISSING,
                "source": SOURCE_MUST_PREPARE,
                "reason": reason,
                "prepare": bool(prepare),
                "evidence": None,
                "detail": None,
                "recorded_at": self._now(),
                "required_for_campaign": kind in REQUIRED_FOR_CAMPAIGN,
            }
            self._state["assets"][kind] = record
            self._state["links"].pop(kind, None)
            self._event(
                "asset_missing",
                kind=kind,
                reason=reason,
                prepare=bool(prepare),
            )
            self.save()
            return dict(record)

    def request_preparation(self, kind: str) -> Dict[str, Any]:
        """Add a missing optional asset to the worklist. Never creates one."""
        kind = self._check_kind(kind)
        with self._locked():
            self.load()
            record = self._state["assets"].get(kind)
            if record is None:
                raise MissingAssetError(
                    "%s is unassessed; record whether the client has it before "
                    "planning preparation" % kind
                )
            if record.get("readiness") != MISSING:
                raise InvalidClaimError(
                    "%s is not missing; there is nothing to prepare" % kind
                )
            if record.get("prepare") is True:
                return dict(record)
            record["prepare"] = True
            record["recorded_at"] = self._now()
            self._event("preparation_requested", kind=kind)
            self.save()
            return dict(record)

    def supply_input(self, kind: str, label: str, *, evidence: str) -> Dict[str, Any]:
        """Record that a preparer already holds one worklist input.

        Evidence is required: an input is never assumed available.
        """
        kind = self._check_kind(kind)
        spec = PREPARATION_SPECS[kind]
        labels = [item.label for item in spec.inputs]
        if label not in labels:
            raise InvalidClaimError(
                "%r is not an input of the %s preparation plan; expected one "
                "of %s" % (label, kind, "; ".join(labels))
            )
        evidence = self._check_evidence(evidence)
        with self._locked():
            self.load()
            bucket = self._state["supplied_inputs"].setdefault(kind, {})
            existing = bucket.get(label)
            if isinstance(existing, dict) and existing.get("evidence") == evidence:
                return dict(existing)
            record = {"label": label, "evidence": evidence, "recorded_at": self._now()}
            bucket[label] = record
            self._event("input_supplied", kind=kind, label=label)
            self.save()
            return dict(record)

    def mark_ready(self, kind: str, *, evidence: str) -> Dict[str, Any]:
        """Promote a prepared asset once it actually exists on disk.

        This is the only path from must_prepare to ready, and it demands an
        evidence pointer to the finished file or link: an existing path, or a
        usable http/https URL. A named source is not enough here -- preparation
        produced something, so it must be pointed at. Nothing is generated here;
        the caller must already have produced the real asset. The asset keeps
        source `prepared`: it was not client-provided.
        """
        kind = self._check_kind(kind)
        evidence = self._check_evidence(evidence)
        evidence = self._check_evidence_shape(evidence, allow_named=False)
        return self.record_present(
            kind, source=SOURCE_PREPARED, evidence=evidence
        )

    # ---------------------------------------------------------------- links

    def link_to_brief_fact(self, kind: str, fact_id: str) -> Dict[str, Any]:
        """Join a present asset to the brief fact that references it.

        Refused when the kind is not present, the fact id is unknown, the fact
        is unanswered, or the fact rests on an assumption. The link stores the
        fact's provenance, never a copy of its value in place of evidence.
        """
        kind = self._check_kind(kind)
        spec = _brief.FACT_SPECS_BY_ID.get(fact_id)
        if spec is None:
            raise UnknownBriefFactError(
                "%r is not a fact in the acquisition brief" % (fact_id,)
            )
        if self.brief is None:
            raise AssetRegistryError(
                "no acquisition brief is attached to this registry"
            )
        record = self._state["assets"].get(kind)
        if record is None or record.get("readiness") != READY:
            raise MissingAssetError(
                "%s is not recorded as present; a link to %s would claim an "
                "asset the client does not have" % (kind, fact_id)
            )
        fact = self.brief.get(fact_id)
        if fact is None:
            raise UntrustedProvenanceError(
                "%s has no recorded value; %s cannot be linked to it"
                % (fact_id, kind)
            )
        if fact.provenance not in _brief.TRUSTED_PROVENANCES:
            raise UntrustedProvenanceError(
                "%s rests on provenance %r; an assumption is never evidence "
                "for %s" % (fact_id, fact.provenance, kind)
            )

        with self._locked():
            self.load()
            current = self._state["assets"].get(kind)
            if current is None or current.get("readiness") != READY:
                raise MissingAssetError(
                    "%s is not recorded as present; a link to %s would claim "
                    "an asset the client does not have" % (kind, fact_id)
                )
            existing = self._state["links"].get(kind)
            if (
                isinstance(existing, dict)
                and existing.get("fact_id") == fact_id
                and existing.get("fact_provenance") == fact.provenance
                and existing.get("fact_recorded_at") == fact.recorded_at
            ):
                return dict(existing)
            link = {
                "kind": kind,
                "fact_id": fact_id,
                "fact_provenance": fact.provenance,
                "fact_recorded_at": fact.recorded_at,
                "linked_at": self._now(),
            }
            self._state["links"][kind] = link
            self._event(
                "asset_linked", kind=kind, fact_id=fact_id, provenance=fact.provenance
            )
            self.save()
            return dict(link)

    def link_defaults(self) -> List[Dict[str, Any]]:
        """Link every present default-linked kind to its brief fact.

        Unanswered facts are skipped (the link is not yet possible). A fact
        that exists but is untrusted raises, because an assumption must not
        become asset evidence.
        """
        if self.brief is None:
            raise AssetRegistryError(
                "no acquisition brief is attached to this registry"
            )
        links: List[Dict[str, Any]] = []
        for kind, fact_id in DEFAULT_FACT_LINKS.items():
            record = self._state["assets"].get(kind)
            if record is None or record.get("readiness") != READY:
                continue
            if self.brief.get(fact_id) is None:
                continue
            links.append(self.link_to_brief_fact(kind, fact_id))
        return links

    def sync_from_brief(self) -> Dict[str, int]:
        """Import the brief's present/absent asset assessments.

        Present assessments carry their provenance across; an assessment with
        no source, or one resting on an assumption, is refused rather than
        upgraded to a real asset. Absent assessments become missing records.
        """
        if self.brief is None:
            raise AssetRegistryError(
                "no acquisition brief is attached to this registry"
            )
        report = self.brief.asset_report()
        imported = 0
        missing = 0
        for entry in report["present"]:
            source = entry.get("source")
            if source not in _BRIEF_SOURCE_MAP:
                raise UntrustedProvenanceError(
                    "the brief claims %s is present with provenance %r; that "
                    "claim has no trusted source, so it is refused"
                    % (entry["kind"], source)
                )
            self.record_present(
                entry["kind"],
                source=_BRIEF_SOURCE_MAP[source],
                evidence=entry.get("detail") or "acquisition brief present assessment",
                detail=entry.get("detail"),
            )
            imported += 1
        for entry in report["missing"]:
            self.record_missing(
                entry["kind"],
                entry.get("detail") or "confirmed absent in the acquisition brief",
            )
            missing += 1
        return {"imported": imported, "missing": missing}

    # ------------------------------------------------------- classification

    def classify(self) -> Dict[str, Dict[str, Any]]:
        """Every kind with its source, readiness and campaign requirement.

        `must_prepare` is derived, never stored as a third state: it is a
        missing asset that sits on the preparation worklist.
        """
        classification: Dict[str, Dict[str, Any]] = {}
        for kind in ASSET_KINDS:
            record = self._state["assets"].get(kind)
            required = kind in REQUIRED_FOR_CAMPAIGN
            if record is None:
                classification[kind] = {
                    "kind": kind,
                    "readiness": UNASSESSED,
                    "source": None,
                    "required_for_campaign": required,
                    "detail": None,
                    "evidence": None,
                    "reason": None,
                    "on_worklist": False,
                    "linked_fact_id": None,
                }
                continue
            if record.get("readiness") == READY:
                readiness = READY
                on_worklist = False
            elif record.get("prepare"):
                readiness = MUST_PREPARE
                on_worklist = True
            else:
                readiness = MISSING
                on_worklist = False
            link = self._state["links"].get(kind)
            classification[kind] = {
                "kind": kind,
                "readiness": readiness,
                "source": record.get("source"),
                "required_for_campaign": required,
                "detail": record.get("detail"),
                "evidence": record.get("evidence"),
                "reason": record.get("reason"),
                "on_worklist": on_worklist,
                "linked_fact_id": link.get("fact_id") if link else None,
            }
        return classification

    # --------------------------------------------------------- worklist

    def _input_status(self, item: PreparationInput, kind: str) -> Dict[str, Any]:
        supplied = self._state["supplied_inputs"].get(kind, {}).get(item.label)
        if supplied:
            return {
                "label": item.label,
                "satisfied": True,
                "satisfied_by": "supplied",
                "evidence": supplied.get("evidence"),
            }
        if item.fact_id is not None and self.brief is not None:
            fact = self.brief.get(item.fact_id)
            if fact is not None and fact.provenance in _brief.TRUSTED_PROVENANCES:
                return {
                    "label": item.label,
                    "satisfied": True,
                    "satisfied_by": "brief:" + item.fact_id,
                    "evidence": fact.provenance,
                }
        return {
            "label": item.label,
            "satisfied": False,
            "satisfied_by": None,
            "evidence": None,
            "fact_id": item.fact_id,
        }

    def preparation_worklist(self) -> List[Dict[str, Any]]:
        """The exact thing to prepare per missing asset, and what it needs.

        Returns a plan, never asset content. Each entry names the deliverable
        and every input, with unsatisfied inputs listed separately so the
        blocker is explicit rather than discovered mid-preparation.
        """
        worklist: List[Dict[str, Any]] = []
        for kind in ASSET_KINDS:
            record = self._state["assets"].get(kind)
            # Unassessed kinds are never called missing: that would invent an
            # answer. Only a recorded absence earns a worklist entry.
            if record is None:
                continue
            if not (
                record.get("readiness") == MISSING and record.get("prepare") is True
            ):
                continue
            spec = PREPARATION_SPECS[kind]
            inputs = [self._input_status(item, kind) for item in spec.inputs]
            blocked = [item["label"] for item in inputs if not item["satisfied"]]
            worklist.append(
                {
                    "kind": kind,
                    "deliverable": spec.deliverable,
                    "inputs": inputs,
                    "blocked_on_inputs": blocked,
                    "status": "awaiting_inputs" if blocked else "ready_to_prepare",
                    "required_for_campaign": kind in REQUIRED_FOR_CAMPAIGN,
                    "reason": (record or {}).get("reason")
                    or "not yet assessed with the client",
                }
            )
        return worklist

    # ------------------------------------------------------------ readiness

    def campaign_readiness(self) -> Dict[str, Any]:
        """Plain answer: can a 30-day campaign run on this asset set?

        Green only when every required kind is present with a trusted source
        and an evidence pointer. Every blocker is named with its state.
        """
        classification = self.classify()
        blockers: List[Dict[str, str]] = []
        ready: List[str] = []
        for kind in ASSET_KINDS:
            entry = classification[kind]
            if entry["readiness"] == READY:
                ready.append(kind)
                continue
            if not entry["required_for_campaign"]:
                continue
            blockers.append(
                {
                    "kind": kind,
                    "state": entry["readiness"],
                    "reason": entry.get("reason")
                    or "the client has not confirmed whether this exists",
                }
            )
        sufficient = not blockers
        if sufficient:
            plain = (
                "Asset set is sufficient for a %d-day campaign: every required "
                "asset is present with provenance and evidence." % CAMPAIGN_DAYS
            )
        else:
            plain = (
                "Asset set is NOT sufficient for a %d-day campaign. Blocked by: %s."
                % (
                    CAMPAIGN_DAYS,
                    "; ".join(
                        "%s (%s)" % (item["kind"], item["state"]) for item in blockers
                    ),
                )
            )
        return {
            "sufficient": sufficient,
            "campaign_days": CAMPAIGN_DAYS,
            "required_kinds": [
                kind for kind in ASSET_KINDS if kind in REQUIRED_FOR_CAMPAIGN
            ],
            "ready_kinds": ready,
            "blockers": blockers,
            "worklist_count": len(
                [k for k, v in classification.items() if v["on_worklist"]]
            ),
            "plain": plain,
        }

    def is_campaign_ready(self) -> bool:
        return self.campaign_readiness()["sufficient"]

    def require_ready(self, kind: str) -> Dict[str, Any]:
        """Return a ready asset or fail loudly. No placeholder fallback."""
        kind = self._check_kind(kind)
        record = self._state["assets"].get(kind)
        if record is None or record.get("readiness") != READY:
            state = record.get("readiness") if record else UNASSESSED
            raise MissingAssetError(
                "%s is %s; a %d-day campaign needs the real asset first"
                % (kind, state, CAMPAIGN_DAYS)
            )
        return dict(record)

    # ------------------------------------------------------------- snapshot

    def snapshot(self) -> Dict[str, Any]:
        """Complete planner-facing view. Missing assets appear only as gaps."""
        return {
            "schema": SCHEMA,
            "path": self.path,
            "assets": self.classify(),
            "links": {kind: dict(link) for kind, link in self._state["links"].items()},
            "supplied_inputs": {
                kind: {label: dict(item) for label, item in bucket.items()}
                for kind, bucket in self._state["supplied_inputs"].items()
            },
            "preparation_worklist": self.preparation_worklist(),
            "readiness": self.campaign_readiness(),
            "brief_attached": self.brief is not None,
            "brief_required_kinds": sorted(_BRIEF_REQUIRED),
        }
