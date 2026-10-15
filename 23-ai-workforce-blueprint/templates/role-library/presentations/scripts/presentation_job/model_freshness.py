#!/usr/bin/env python3
"""model_freshness.py -- FIX 31: the pre-run model freshness check.

WHAT THIS IS (B11 design, build/b11-freshness/DESIGN.md)
--------------------------------------------------------
Before a run starts, this module checks the provider's CURRENT model
catalog for the family and provider of the client's selected models. If
a newer successor exists in the same family on the same provider, the
client is offered the choice: switch, keep, or decide later. It never
switches a model by itself, never blocks a run for keeping the older
model, and records the check and the client's decision in the run
record and the capability profile.

THE THREE HOOKS (B28's manifest names the exact call sites)
-----------------------------------------------------------
  Hook A (intake)  -- deck-intake-driver.py's resource_plan turn. After
    the model plan is recorded (and immediately after FIX 18's route
    honesty decision is recorded), the driver runs intake_check()
    against the just-saved profile and presents any offer in the same
    turn, attached after the route_honesty block. An explicit decision
    label in the client's answer ("model_freshness: switch|keep|defer")
    is recorded through record_freshness_decision() BEFORE the check, so
    it settles the offer that was outstanding when the turn began.
  Hook B (launch)  -- launcher.dispatch(), immediately after
    _announce_route_honesty(): launch_check() writes the run record and
    prints through launcher's summary lines. It has NO refusal return
    value; dispatch ignores everything except the printed lines.
  Hook C (poller)  -- launch_plan.write_launch_plan(), at the same call
    site family as route_honesty.write_launch_sidecar: the same
    launch_check(), record-only. This path is non-interactive: it can
    record and update pending offers, it cannot present one.

CATALOG ACCESS -- ONE DOOR, NO SECOND NETWORK PATH
--------------------------------------------------
Catalog readings come ONLY through capacity.refresh_provider_inventory()
restricted to the selections' providers (the explicit discovery door,
cached process-wide for capacity.INVENTORY_TTL_S). This module never
touches the network itself, never keeps a second raw-response cache, and
never handles a credential: capacity's probe verdicts carry model ids,
pricing and error strings only. Two reading layers, in order:

  layer 1  the inventory snapshot (live, or "inventory-cache" when the
           snapshot's own cache served it -- the result's requests_made
           proves which);
  layer 2  the profile's persisted probe inventory (wired_models +
           probed_at, written by capacity's persist path), usable while
           its age is at most FRESHNESS_TTL_S (default 900s, tunable
           through PRESENTATION_MODEL_FRESHNESS_TTL_S).

Offline rule, stated plainly: a live failure with no within-TTL layer-2
reading is "unknown-offline" -- a statement about the CHECK, never about
the model. No offer is ever made from data older than the TTL, and no
"fresh" verdict is ever issued without a reading. The run proceeds on
the recorded selection either way.

SUCCESSOR DETECTION IS STRUCTURAL (design section 3)
----------------------------------------------------
A candidate is a successor only when it parses to the same (stem,
variant) identity on the same provider, carries a strictly greater
version tuple, carries no exclusion tag (preview / beta / free / ...),
and is not expired in the provider's own catalog (OpenRouter's
expiration_date, read through capacity's model_pricing). Name matching
alone never qualifies anything. An unversioned selection (deepseek-flash)
can never be offered a successor: there is no version to be newer than.

RECORDING (design section 1.6; field names audited against
resource_profile.redact_record, which drops secret-named keys on every
write -- per-pair rows are LISTS, never dicts keyed by capability class):
  profile["interview"]["model_freshness"]  -- append-only log of check
    rows and decision rows, linked by check_id;
  profile["model_freshness"]               -- {last_checked_at,
    last_status, pending: [...]} summary;
  profile["model_plan"]                    -- changed ONLY through
    resource_profile.record_model_plan, and only on an accepted switch.
  profile["model_choices"]                 -- B27's unified record: each
    decision recorded by record_freshness_decision also lands there, in
    that record's shape (the offered successor as a recommendation shown
    on its provider family's row, the client's outcome as the response,
    an applied switch as the family's selection, written only through
    resource_profile.record_model_choice).

ROLLBACK: PRESENTATION_MODEL_FRESHNESS=0 makes every public function a
no-op that writes nothing.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FLAG_ENV = "PRESENTATION_MODEL_FRESHNESS"
FLAG_DEFAULT = "1"

TTL_ENV = "PRESENTATION_MODEL_FRESHNESS_TTL_S"
#: Layer-2 (profile-cache) readings are usable for at most this many
#: seconds. A reading older than this can ground NO verdict and NO offer.
FRESHNESS_TTL_S = 900.0

RUN_RECORD_NAME = ".model-freshness.json"

STATUS_FRESH = "fresh"
STATUS_SUCCESSOR = "successor-available"
STATUS_OFFLINE = "unknown-offline"

OUTCOMES = ("switch", "keep", "defer")

#: The freshness offer as it is described inside B27's unified
#: model-choice record (the `reason` on the recommendation entry a
#: decision recorded here folds there). No numbers and no
#: recommendation vocabulary: this surface never calls its offer a
#: recommendation in client-facing copy, and a recorded reason must
#: not go stale against the catalog it names.
MODEL_CHOICES_REASON = (
    "Model freshness: a newer model in the same family is listed in "
    "the provider catalog."
)

#: Providers whose probe endpoint is not a model list (capacity's probe
#: def carries models_endpoint=False, e.g. kie's credit read) expose no
#: catalog to check against: the honest verdict is unknown-offline with
#: this note, never an empty-catalog "fresh".
NO_MODEL_LIST_NOTE = "provider exposes no model list"


# ---------------------------------------------------------------------------
# Sibling modules (package-relative, flat-layout fallback -- the same
# import posture as route_honesty.py and launch_plan.py)
# ---------------------------------------------------------------------------
def _sibling(name):
    import importlib
    if __package__:
        try:
            return importlib.import_module(f".{name}", __package__)
        except Exception:  # noqa: BLE001 -- fall through to the flat layout
            pass
    try:
        return importlib.import_module(name)
    except Exception:  # noqa: BLE001 -- a missing sibling degrades, never raises
        return None


_CAPACITY = None
_CAPACITY_TRIED = False
_RESOURCE_PROFILE = None
_RESOURCE_PROFILE_TRIED = False
_ROUTER = None
_ROUTER_TRIED = False
_CATALOG = None
_CATALOG_TRIED = False


def _capacity():
    global _CAPACITY, _CAPACITY_TRIED
    if not _CAPACITY_TRIED:
        _CAPACITY_TRIED = True
        _CAPACITY = _sibling("capacity")
    return _CAPACITY


def _resource_profile():
    global _RESOURCE_PROFILE, _RESOURCE_PROFILE_TRIED
    if not _RESOURCE_PROFILE_TRIED:
        _RESOURCE_PROFILE_TRIED = True
        _RESOURCE_PROFILE = _sibling("resource_profile")
    return _RESOURCE_PROFILE


def _router():
    global _ROUTER, _ROUTER_TRIED
    if not _ROUTER_TRIED:
        _ROUTER_TRIED = True
        _ROUTER = _sibling("model_router")
    return _ROUTER


def _catalog():
    global _CATALOG, _CATALOG_TRIED
    if not _CATALOG_TRIED:
        _CATALOG_TRIED = True
        _CATALOG = _sibling("model_catalog")
    return _CATALOG


def flag_enabled() -> bool:
    """True unless the operator exported PRESENTATION_MODEL_FRESHNESS=0.

    Default ON per the rev2 rollback doctrine. `=0` is the documented
    rollback: every public function below is a no-op that writes nothing,
    and every consumer behaves byte-for-byte as it did before FIX 31."""
    raw = os.environ.get(FLAG_ENV, FLAG_DEFAULT)
    return str(raw).strip().strip("'\"") != "0"


def freshness_ttl_s() -> float:
    """The layer-2 TTL in seconds: FRESHNESS_TTL_S unless the operator
    tuned it through PRESENTATION_MODEL_FRESHNESS_TTL_S. An invalid or
    non-positive value is ignored, never guessed into a longer window."""
    raw = (os.environ.get(TTL_ENV) or "").strip()
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return FRESHNESS_TTL_S


def _now() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _parse_ts(raw: Any) -> Optional[datetime.datetime]:
    """Parse an ISO timestamp into an aware datetime, or None."""
    if isinstance(raw, datetime.datetime):
        parsed = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.datetime.fromisoformat(
                raw.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _canon_provider(provider: Any) -> str:
    """One canonical provider spelling for comparisons and records.

    capacity.normalize_provider is the authority (it folds deepseek ->
    deepseek-direct and recognises client-declared providers); the
    catalog's normalizer and a plain dash-fold are fallbacks so a partial
    deploy still compares like with like."""
    text = str(provider or "").strip()
    if not text:
        return ""
    cap = _capacity()
    if cap is not None:
        try:
            hit = cap.normalize_provider(text)
            if hit:
                return str(hit)
        except Exception:  # noqa: BLE001 -- normalization never kills a check
            pass
    cat = _catalog()
    if cat is not None:
        try:
            hit = cat.normalize_provider_id(text)
            if hit:
                return str(hit)
        except Exception:  # noqa: BLE001
            pass
    return text.lower().replace("_", "-").replace(" ", "-")


# ---------------------------------------------------------------------------
# Section 3: the model-id parser and the structural successor rule
# ---------------------------------------------------------------------------
#: Word tokens that mark a pre-release or channel variant. They are
#: collected as tags and never enter the stem or the variant.
TAG_TOKENS = frozenset({
    "preview", "exp", "experimental", "beta", "alpha", "rc", "dev",
    "nightly", "free", "snapshot", "wip",
})

#: The disqualifying subset (S4): a candidate carrying any of these is
#: never offered as a successor, however new it is. The step-4 suffix tag
#: "cloud" is deliberately NOT here: an Ollama Cloud listing that appends
#: ":cloud" to the same model is the same serving, not a different one.
EXCLUSION_TAGS = TAG_TOKENS

_DOTTED_VERSION = re.compile(r"^v?(\d+(?:\.\d+)+)v?$")
_V_INT_VERSION = re.compile(r"^v(\d{1,2})$")
_BARE_INT_VERSION = re.compile(r"^\d{1,2}$")
_SIZE_TOKEN = re.compile(r"^\d+(?:\.\d+)?b$")
_DATE_8 = re.compile(r"^\d{8}$")
_DATE_4 = re.compile(r"^\d{4}$")
_DATE_2 = re.compile(r"^\d{2}$")


def parse_model_id(raw_id: Any) -> Optional[Dict[str, Any]]:
    """Parse one served model id into {stem, version, variant, tags,
    served_id}, or None when nothing parseable remains.

    The steps are the design's, in its order: lowercase and trim (the
    full original is kept as served_id -- offers and records always name
    the served id); legacy fold through the catalog; namespace strip;
    ":cloud" / ":free" suffix tags; date-suffix strip (a date segment is
    never a version component); tokenize on - _ and space, keeping dots
    inside tokens; the version token is the FIRST dotted number, the
    first v-prefixed integer, or the first bare one-or-two-digit integer
    (a run of 3+ digits without a dot is never a version, and a
    digits-plus-b token is a size, not a version); stem is everything
    before it, variant everything after it minus tag and date tokens.
    With no version token, the stem is the first token and the variant
    is the rest."""
    if not isinstance(raw_id, str):
        return None
    served = raw_id.strip()
    if not served:
        return None
    work = served.lower()
    cat = _catalog()
    fold = getattr(cat, "fold_legacy_flash_model_id", None) if cat else None
    if callable(fold):
        try:
            work = fold(work)
        except Exception:  # noqa: BLE001 -- a fold failure keeps the raw id
            pass
    if "/" in work:
        work = work.split("/", 1)[1]
        if callable(fold):
            try:
                work = fold(work)
            except Exception:  # noqa: BLE001
                pass
    tags: List[str] = []
    changed = True
    while changed:
        changed = False
        for suffix in (":cloud", ":free"):
            if work.endswith(suffix):
                work = work[: -len(suffix)]
                tags.append(suffix[1:])
                changed = True
    tokens = [t for t in re.split(r"[-_ ]+", work) if t]
    if not tokens:
        return None
    # Date suffixes: a trailing YYYYMMDD run, or a trailing YYYY MM DD
    # triple (the tokenized form of 2026-10-01). Stripped before the
    # version scan so a date can never pose as a version.
    while tokens and _DATE_8.match(tokens[-1]):
        tokens.pop()
    if (len(tokens) >= 3 and _DATE_4.match(tokens[-3])
            and _DATE_2.match(tokens[-2]) and _DATE_2.match(tokens[-1])
            and 1 <= int(tokens[-2]) <= 12 and 1 <= int(tokens[-1]) <= 31):
        tokens = tokens[:-3]
    if not tokens:
        return None
    kept: List[str] = []
    for tok in tokens:
        if tok in TAG_TOKENS:
            tags.append(tok)
        else:
            kept.append(tok)
    tokens = kept
    if not tokens:
        return None
    version: Optional[Tuple[int, ...]] = None
    version_idx: Optional[int] = None
    for idx, tok in enumerate(tokens):
        dotted = _DOTTED_VERSION.match(tok)
        if dotted:
            version = tuple(int(p) for p in dotted.group(1).split("."))
            version_idx = idx
            break
        vint = _V_INT_VERSION.match(tok)
        if vint:
            version = (int(vint.group(1)),)
            version_idx = idx
            break
        if _SIZE_TOKEN.match(tok):
            continue  # a size (70b, 27b) is not a version; keep scanning
        if _BARE_INT_VERSION.match(tok):
            version = (int(tok),)
            version_idx = idx
            break
        # A bare run of 3+ digits is never a version: keep scanning.
    if version_idx is not None:
        stem = "-".join(tokens[:version_idx])
        variant = "-".join(
            t for t in tokens[version_idx + 1:]
            if not _DATE_8.match(t) and not _DATE_4.match(t))
    else:
        stem = tokens[0]
        variant = "-".join(tokens[1:])
    return {"stem": stem, "version": version, "variant": variant,
            "tags": sorted(set(tags)), "served_id": served}


def _version_cmp(a: Tuple[int, ...], b: Tuple[int, ...]) -> int:
    """Tuple comparison with the shorter tuple zero-padded: (5,) pads to
    (5, 0) and so beats (4, 1); components compare as integers, never as
    strings, so (5, 3) < (5, 10)."""
    width = max(len(a), len(b))
    pa = tuple(a) + (0,) * (width - len(a))
    pb = tuple(b) + (0,) * (width - len(b))
    return (pa > pb) - (pa < pb)


def _family_of(parsed: Optional[Dict[str, Any]]) -> Optional[str]:
    """The family key a pair is checked, offered and suppressed under:
    stem plus variant (deepseek-v4.1-flash and the legacy-folded
    deepseek-flash are one family, deepseek-flash)."""
    if not parsed:
        return None
    fam = parsed["stem"]
    if parsed["variant"]:
        fam = f"{fam}-{parsed['variant']}"
    return fam or None


def _norm_id_for_compare(model_id: Any) -> str:
    """Fold a served id for presence comparisons only: lowercase,
    namespace-stripped, ":cloud" / ":free" suffixes removed. Folding a
    name for comparison is never evidence of presence by itself -- it
    only lets the Ollama Cloud ":cloud" listing and the catalog's bare
    id compare like-for-like."""
    work = str(model_id or "").strip().lower()
    if "/" in work:
        work = work.split("/", 1)[1]
    changed = True
    while changed:
        changed = False
        for suffix in (":cloud", ":free"):
            if work.endswith(suffix):
                work = work[: -len(suffix)]
                changed = True
    return work


def _is_expired(pricing_entry: Any, *, now: Optional[datetime.datetime] = None) -> bool:
    """S5: an OpenRouter candidate whose catalog expiration_date parses
    to a past date is excluded. An unparseable date proves nothing and
    excludes nothing."""
    if not isinstance(pricing_entry, dict):
        return False
    raw = pricing_entry.get("expiration_date")
    if not raw:
        return False
    moment = _parse_ts(raw)
    if moment is None:
        try:
            day = datetime.date.fromisoformat(str(raw).strip()[:10])
        except ValueError:
            return False
        return day < (now or _now()).date()
    return moment.date() < (now or _now()).date()


# ---------------------------------------------------------------------------
# Display names -- ONE helper, used identically by the intake turn, the
# pending surface and the launcher line (design 4.2)
# ---------------------------------------------------------------------------
_BRAND_TOKENS = {
    "deepseek": "DeepSeek", "glm": "GLM", "kimi": "Kimi", "gpt": "GPT",
    "ollama": "Ollama", "llama": "Llama", "qwen": "Qwen",
    "mistral": "Mistral", "gemini": "Gemini", "claude": "Claude",
}

_PROVIDER_DISPLAY = {
    "deepseek-direct": "DeepSeek Direct",
    "openrouter": "OpenRouter",
    "ollama-cloud": "Ollama Cloud",
    "agnes": "Agnes",
    "kie": "Kie.ai",
}


def display_name(model_id: Any) -> str:
    """Humanize a served id: deepseek-v4.1-flash -> "DeepSeek V4.1
    Flash". The namespace and any :cloud / :free suffix are serving
    detail, not part of the name a client reads."""
    work = str(model_id or "").strip()
    if "/" in work:
        work = work.rsplit("/", 1)[-1]
    work = work.split(":", 1)[0]
    parts = [t for t in re.split(r"[-_ ]+", work) if t]
    out: List[str] = []
    for tok in parts:
        low = tok.lower()
        if re.match(r"^v\d", low):
            out.append("V" + tok[1:])
        elif low in _BRAND_TOKENS:
            out.append(_BRAND_TOKENS[low])
        else:
            out.append(tok[:1].upper() + tok[1:])
    return " ".join(out) or str(model_id or "")


def provider_display(provider: Any) -> str:
    canon = _canon_provider(provider)
    if canon in _PROVIDER_DISPLAY:
        return _PROVIDER_DISPLAY[canon]
    cap = _capacity()
    defs = getattr(cap, "PROVIDER_PROBE_DEFS", {}) if cap else {}
    label = (defs.get(canon) or {}).get("label")
    if label:
        return str(label)
    return display_name(canon)


def _fmt_price(value: Any) -> str:
    """A per-million price as printed in the offer: exact digits from
    the catalog reading, trailing zeros trimmed, never rounded into a
    different number and never estimated."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{number:.6f}".rstrip("0").rstrip(".")
    return text or "0"


# ---------------------------------------------------------------------------
# Section 1.3: the effective selections -- what routing will actually use
# ---------------------------------------------------------------------------
def effective_selections(profile: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The deduplicated selection set for one profile.

    Declared plan: for each slot in model_router.SLOT_CLASSES, the
    slot's declared {provider, model} read through plan_slot semantics
    (a half-declared slot is not a declaration), with the declared id
    resolved to the SERVED id through declared_alias_def / the catalog
    served_ids table; a raw wired id is checked verbatim.
    selected_source = "client-plan".

    No declared plan: the department defaults -- the primary alias of
    each slot's first capability class in CAPABILITY_CANDIDATES,
    resolved through the catalog. Derived from router + catalog at
    runtime, never hardcoded; at HEAD this deduplicates to two pairs.
    selected_source = "department-default", and each pair also carries
    overlay_slot (the representative slot a switch would be declared
    on), because a default has no client slot of its own.

    Rows are dicts {slot, provider, selected_model, selected_source,
    overlay_slot}, deduplicated by (provider, served model id) in slot
    order."""
    router = _router()
    if router is None or not isinstance(profile, dict):
        return []
    rows: List[Dict[str, Any]] = []
    seen = set()

    def _served(spec_provider: str, declared_model: str,
                alias_def: Optional[Dict[str, Any]]) -> str:
        if alias_def:
            try:
                served = router._served_model(alias_def, spec_provider)
                if served:
                    return str(served)
            except Exception:  # noqa: BLE001 -- fall back to the declared id
                pass
        return declared_model

    plan = router.model_plan(profile)
    declared_any = False
    for slot in router.SLOT_CLASSES:
        spec = router.plan_slot(plan, slot)
        if spec is None:
            continue
        declared_any = True
        alias_def = None
        try:
            alias_def, _src = router.declared_alias_def(spec)
        except Exception:  # noqa: BLE001 -- a raw wired id is checked verbatim
            alias_def = None
        provider = _canon_provider(spec["provider"])
        served = _served(spec["provider"], spec["model"], alias_def)
        key = (provider, served)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"slot": slot, "provider": provider,
                     "selected_model": served,
                     "selected_source": "client-plan",
                     "overlay_slot": slot})
    if declared_any:
        return rows

    for slot, classes in router.SLOT_CLASSES.items():
        if not classes:
            continue
        candidates = router.CAPABILITY_CANDIDATES.get(classes[0]) or []
        if not candidates:
            continue
        alias = (candidates[0] or {}).get("alias")
        if not alias:
            continue
        try:
            alias_def = router.resolve_alias(alias)
        except Exception:  # noqa: BLE001 -- an unresolvable default is skipped
            alias_def = None
        if not alias_def or not alias_def.get("provider"):
            continue
        provider = _canon_provider(alias_def["provider"])
        served = _served(str(alias_def["provider"]),
                         str(alias_def.get("model") or ""), alias_def)
        if not served:
            continue
        key = (provider, served)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"slot": "default", "provider": provider,
                     "selected_model": served,
                     "selected_source": "department-default",
                     "overlay_slot": slot})
    return rows


def _public_selection(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"slot": row.get("slot"), "provider": row.get("provider"),
            "selected_model": row.get("selected_model"),
            "selected_source": row.get("selected_source")}


# ---------------------------------------------------------------------------
# Profile state: the freshness log, the summary, decisions, pending offers
# ---------------------------------------------------------------------------
def _log_rows(profile: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(profile, dict):
        return []
    interview = profile.get("interview")
    if not isinstance(interview, dict):
        return []
    rows = interview.get("model_freshness")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _summary(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(profile, dict):
        return {}
    summary = profile.get("model_freshness")
    return summary if isinstance(summary, dict) else {}


def _pending_rows(profile: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pending = _summary(profile).get("pending")
    if not isinstance(pending, list):
        return []
    return [r for r in pending if isinstance(r, dict)]


def pending_offers(profile: Optional[Dict[str, Any]] = None,
                   config_dir: Optional[Any] = None) -> List[Dict[str, Any]]:
    """The offers waiting for a client answer, read from the profile.
    Mirrors resource_profile.open_gap_records()' posture: a pure read of
    the recorded state; nothing here presents or decides anything."""
    if not flag_enabled():
        return []
    if profile is None:
        rp = _resource_profile()
        if rp is None:
            return []
        profile = rp.load_profile(config_dir)
    return [dict(r) for r in _pending_rows(profile)]


def _decision_rows(profile: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in _log_rows(profile) if r.get("kind") == "decision"]


def _pair_key(provider: Any, family: Any) -> Tuple[str, str]:
    return (str(provider or ""), str(family or ""))


def _declined_successor(profile: Dict[str, Any], provider: str,
                        family: str, selected_model: str) -> Optional[str]:
    """The successor a "keep" decision already declined for this exact
    (provider, family, selected_model) tuple, or None. Suppression is
    scoped to the tuple: the offer fires again only when a strictly
    newer successor than the declined one qualifies."""
    declined: Optional[str] = None
    for row in _decision_rows(profile):
        if row.get("outcome") != "keep":
            continue
        if _pair_key(row.get("provider"), row.get("family")) != (provider, family):
            continue
        if row.get("selected_model") != selected_model:
            continue
        declined = row.get("successor_model") or declined
    return declined


# ---------------------------------------------------------------------------
# Section 2 + 5: catalog readings -- layer 1 (inventory snapshot), then
# layer 2 (the profile's persisted probe inventory, TTL-judged)
# ---------------------------------------------------------------------------
def _profile_provider_entry(profile: Dict[str, Any],
                            provider: str) -> Optional[Dict[str, Any]]:
    providers = profile.get("providers")
    if not isinstance(providers, dict):
        return None
    cap = _capacity()
    canon = getattr(cap, "canonical_provider_token", None) if cap else None

    def _fold(key: Any) -> str:
        if callable(canon):
            try:
                return str(canon(str(key)) or "")
            except Exception:  # noqa: BLE001
                pass
        return str(key or "").strip().lower().replace("_", "-").replace(" ", "-")

    want = _fold(provider)
    for key, entry in providers.items():
        if isinstance(entry, dict) and _fold(key) == want:
            return entry
    return None


def _read_catalogs(profile: Dict[str, Any],
                   selections: List[Dict[str, Any]],
                   transport: Optional[Any],
                   config_dir: Optional[Any]) -> Dict[str, Dict[str, Any]]:
    """One reading per selected provider:
    {models (list or None), source, snapshot_revision, probed_at,
     error, pricing}.

    Check order per provider (design 5.1): the inventory snapshot
    (which serves its own process cache when warm, then a live refresh),
    then the profile's persisted inventory when the live attempt failed
    or the provider cannot be probed, judged against FRESHNESS_TTL_S.
    A successful live refresh also rewrites layer 2 (persist=True)."""
    readings: Dict[str, Dict[str, Any]] = {}
    providers = sorted({s["provider"] for s in selections if s.get("provider")})
    if not providers:
        return readings
    cap = _capacity()
    result: Optional[Dict[str, Any]] = None
    refresh_error: Optional[str] = None
    if cap is not None:
        try:
            result = cap.refresh_provider_inventory(
                providers=providers, transport=transport,
                persist=True, config_dir=config_dir)
        except Exception as exc:  # noqa: BLE001 -- a broken door is offline, not fatal
            refresh_error = f"{exc.__class__.__name__}: {exc}"
    probes = (result or {}).get("probes")
    probes = probes if isinstance(probes, dict) else {}
    ttl = freshness_ttl_s()
    now = _now()
    for provider in providers:
        reading: Dict[str, Any] = {
            "models": None, "source": "none", "snapshot_revision": None,
            "probed_at": None, "error": None, "pricing": {},
        }
        readings[provider] = reading
        spec = {}
        if cap is not None:
            defs = getattr(cap, "PROVIDER_PROBE_DEFS", {}) or {}
            spec = defs.get(provider) or {}
            if provider not in defs or spec.get("models_endpoint") is False:
                # No models endpoint exists for this provider (a probe
                # def without one, like kie's credit read, or no def at
                # all, like a client-declared provider this build has
                # never heard of): there is no catalog to check against.
                reading["error"] = NO_MODEL_LIST_NOTE
                continue
        live_error = refresh_error
        verdict = probes.get(provider)
        if isinstance(verdict, dict):
            if verdict.get("ok"):
                reading["models"] = list(verdict.get("models") or [])
                reading["source"] = ("inventory-cache" if (result or {}).get("cached")
                                      else "live")
                reading["snapshot_revision"] = (result or {}).get("snapshot_revision")
                reading["probed_at"] = (result or {}).get("probed_at")
                pricing = verdict.get("model_pricing")
                reading["pricing"] = pricing if isinstance(pricing, dict) else {}
                continue
            live_error = verdict.get("models_error") or live_error \
                or "catalog probe failed"
        elif result is not None:
            live_error = live_error or "provider not in inventory snapshot"
        # Layer 2: the profile's persisted probe inventory.
        entry = _profile_provider_entry(profile, provider)
        wired = entry.get("wired_models") if isinstance(entry, dict) else None
        probed_raw = entry.get("probed_at") if isinstance(entry, dict) else None
        if isinstance(wired, list) and probed_raw:
            probed_at = _parse_ts(probed_raw)
            if probed_at is not None:
                age = (now - probed_at).total_seconds()
                reading["probed_at"] = str(probed_raw)
                if age <= ttl:
                    reading["models"] = list(wired)
                    reading["source"] = "profile-cache"
                    reading["error"] = None
                    continue
                # Stale beyond the TTL: recorded as such, grounds nothing.
                reading["source"] = "profile-cache"
                reading["error"] = live_error or "profile cache stale"
                continue
        reading["error"] = live_error or "no catalog reading available"
    return readings


# ---------------------------------------------------------------------------
# Section 1.4: the per-pair check and the verdict object
# ---------------------------------------------------------------------------
def _check_pair(selection: Dict[str, Any], reading: Dict[str, Any],
                profile: Dict[str, Any], checked_at: str) -> Dict[str, Any]:
    provider = selection["provider"]
    selected = selection["selected_model"]
    parsed = parse_model_id(selected)
    family = _family_of(parsed)
    if family is None:
        family = _norm_id_for_compare(selected) or str(selected)
    row: Dict[str, Any] = {
        "check_id": f"{checked_at}|{provider}|{family}",
        "provider": provider,
        "slot": selection.get("slot"),
        "family": family,
        "selected_model": selected,
        "selected_source": selection.get("selected_source"),
        "status": STATUS_OFFLINE,
        "successor_model": None,
        "selected_in_catalog": None,
        "catalog_source": reading.get("source") or "none",
        "snapshot_revision": reading.get("snapshot_revision"),
        "probed_at": reading.get("probed_at"),
        "catalog_error": None,
        "note": None,
        "_catalog_models": None,
        "_pricing": reading.get("pricing") or {},
        "_suppressed": False,
    }
    models = reading.get("models")
    if models is None:
        row["catalog_error"] = reading.get("error") or "no catalog reading available"
        if row["catalog_error"] == NO_MODEL_LIST_NOTE:
            row["note"] = NO_MODEL_LIST_NOTE
        return row
    row["_catalog_models"] = list(models)
    wanted = _norm_id_for_compare(selected)
    row["selected_in_catalog"] = any(
        _norm_id_for_compare(m) == wanted for m in models)
    if parsed is None:
        row["status"] = STATUS_FRESH
        row["note"] = "unparseable-selection"
        return row
    if parsed["version"] is None:
        # S1: an unversioned selection can never be offered a successor.
        row["status"] = STATUS_FRESH
        row["note"] = "unversioned-selection"
        return row

    qualifying: List[Tuple[Dict[str, Any], str]] = []
    tagged: List[Tuple[str, List[str]]] = []
    expired: List[str] = []
    rereleased: List[str] = []
    pricing = reading.get("pricing") or {}
    for candidate_id in models:
        if _norm_id_for_compare(candidate_id) == wanted:
            continue  # the selection itself, however this provider spells it
        cand = parse_model_id(candidate_id)
        if cand is None or cand["version"] is None:
            continue  # an unparseable catalog id is simply never a successor
        if (cand["stem"], cand["variant"]) != (parsed["stem"], parsed["variant"]):
            continue  # S3: identity is (stem, variant) on this provider
        order = _version_cmp(cand["version"], parsed["version"])
        if order == 0:
            rereleased.append(candidate_id)
            continue
        if order < 0:
            continue
        if set(cand["tags"]) & set(EXCLUSION_TAGS):
            tagged.append((candidate_id, cand["tags"]))
            continue  # S4
        if _is_expired(pricing.get(candidate_id)):
            expired.append(candidate_id)
            continue  # S5
        qualifying.append((cand, candidate_id))

    notes: List[str] = []
    if tagged:
        cid, ctags = tagged[0]
        notes.append(
            f"same-family candidate {cid} was seen and excluded: "
            f"tagged {'/'.join(ctags)}")
    if expired:
        notes.append(
            f"newer same-family candidate {expired[0]} is expired in "
            f"the provider catalog and was not offered")
    if rereleased:
        notes.append(
            f"re-release seen: {rereleased[0]} (same version, not a successor)")

    if not qualifying:
        row["status"] = STATUS_FRESH
        row["note"] = "; ".join(notes) or None
        return row

    def _winner_key(item: Tuple[Dict[str, Any], str]):
        cand, cid = item
        version = cand["version"] or ()
        padded = tuple(version) + (0,) * (8 - len(version))
        # Highest version wins. Ties: prefer the served id with no
        # suffix beyond identity (no namespace, no :tag), then the
        # lexicographically smallest full served id. (capacity's probe
        # surface carries ids and pricing only, so the design's
        # OpenRouter `created` tie-break has no input on this seam and
        # the deterministic order below is what decides.)
        penalty = (1 if "/" in cid else 0) + (1 if ":" in cid else 0)
        return (tuple(-n for n in padded), penalty, cid)

    qualifying.sort(key=_winner_key)
    winner = qualifying[0][1]
    row["status"] = STATUS_SUCCESSOR
    row["successor_model"] = winner
    declined = _declined_successor(profile, provider, family, selected)
    if declined:
        declined_parsed = parse_model_id(declined)
        winner_parsed = parse_model_id(winner)
        if (declined_parsed and winner_parsed
                and declined_parsed["version"] is not None
                and winner_parsed["version"] is not None
                and _version_cmp(winner_parsed["version"],
                                 declined_parsed["version"]) <= 0):
            row["_suppressed"] = True
            notes.append(
                f"successor {winner} was already declined (keep); "
                f"not re-offered")
    row["note"] = "; ".join(notes) or None
    return row


def check_freshness(profile: Optional[Dict[str, Any]] = None,
                    config_dir: Optional[Any] = None,
                    transport: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Run the freshness check and return the verdict object:
    {checked_at, status, checks, offers, effective_selection}.

    Never raises. An exception anywhere inside the check is recorded as
    unknown-offline with the exception class name in catalog_error
    (design 5.3): a freshness failure is a statement about the check,
    and there is no path from it to a refusal anywhere. `transport`
    threads through to capacity's probe seam so tests and proofs inject
    catalog responses offline. Returns None only when the flag is off.
    Pure: this function writes nothing; record_check() and launch_check()
    are the writers."""
    if not flag_enabled():
        return None
    checked_at = _now_iso()
    try:
        if profile is None:
            rp = _resource_profile()
            profile = rp.load_profile(config_dir) if rp is not None else {}
        if not isinstance(profile, dict):
            profile = {}
        selections = effective_selections(profile)
        readings = _read_catalogs(profile, selections, transport, config_dir)
        checks: List[Dict[str, Any]] = []
        for selection in selections:
            reading = readings.get(selection["provider"]) or {
                "models": None, "source": "none", "snapshot_revision": None,
                "probed_at": None, "error": "no catalog reading available",
                "pricing": {},
            }
            try:
                checks.append(_check_pair(selection, reading, profile,
                                          checked_at))
            except Exception as exc:  # noqa: BLE001 -- per-pair isolation
                row = {
                    "check_id": f"{checked_at}|{selection['provider']}|"
                                f"{selection['selected_model']}",
                    "provider": selection["provider"],
                    "slot": selection.get("slot"),
                    "family": _norm_id_for_compare(selection["selected_model"]),
                    "selected_model": selection["selected_model"],
                    "selected_source": selection.get("selected_source"),
                    "status": STATUS_OFFLINE, "successor_model": None,
                    "selected_in_catalog": None,
                    "catalog_source": reading.get("source") or "none",
                    "snapshot_revision": reading.get("snapshot_revision"),
                    "probed_at": reading.get("probed_at"),
                    "catalog_error": f"freshness check failed: "
                                     f"{exc.__class__.__name__}",
                    "note": None, "_catalog_models": None,
                    "_pricing": {}, "_suppressed": False,
                }
                checks.append(row)
        offers: List[Dict[str, Any]] = []
        for row in checks:
            if row["status"] == STATUS_SUCCESSOR and not row.get("_suppressed"):
                offers.append(_build_offer(row))
        if any(r["status"] == STATUS_SUCCESSOR for r in checks):
            status = STATUS_SUCCESSOR
        elif any(r["status"] == STATUS_OFFLINE for r in checks):
            status = STATUS_OFFLINE
        else:
            status = STATUS_FRESH
        return {"checked_at": checked_at, "status": status,
                "checks": checks, "offers": offers,
                "effective_selection": [_public_selection(s)
                                        for s in selections]}
    except Exception as exc:  # noqa: BLE001 -- the hook boundary contract
        return {"checked_at": checked_at, "status": STATUS_OFFLINE,
                "checks": [], "offers": [], "effective_selection": [],
                "error": exc.__class__.__name__}


# ---------------------------------------------------------------------------
# Section 4: the offer surface -- wording, prices, cached-reading honesty
# ---------------------------------------------------------------------------
def _build_offer(row: Dict[str, Any]) -> Dict[str, Any]:
    offer = {
        "check_id": row.get("check_id"),
        "provider": row.get("provider"),
        "family": row.get("family"),
        "slot": row.get("slot"),
        "selected_model": row.get("selected_model"),
        "selected_source": row.get("selected_source"),
        "successor_model": row.get("successor_model"),
        "catalog_source": row.get("catalog_source"),
        "probed_at": row.get("probed_at"),
    }
    offer["text"] = render_offer_text(offer, pricing=row.get("_pricing") or {})
    return offer


def render_offer_text(offer: Dict[str, Any],
                      pricing: Optional[Dict[str, Any]] = None) -> str:
    """The offer wording (design 4.2). Numbers come only from the
    catalog reading: on OpenRouter, the priced line is included solely
    when the reading carries BOTH models' prompt and completion prices;
    when either is missing the line is omitted entirely, and no price is
    ever estimated. A cached reading is named as one, with its read
    time. The word "recommended" never appears here: recommendation
    language belongs to FIX 18's block, not to this choice."""
    provider = offer.get("provider") or ""
    selected = offer.get("selected_model") or ""
    successor = offer.get("successor_model") or ""
    prov = provider_display(provider)
    sel_name = display_name(selected)
    suc_name = display_name(successor)
    is_default = offer.get("selected_source") == "department-default"
    origin = "the department default" if is_default else "your saved choice"
    lines = ["Model update available."]
    lines.append(
        f"This run is set to use {sel_name} on {prov} ({origin}).")
    price_line = ""
    pricing = pricing or {}
    if _canon_provider(provider) == "openrouter":
        # capacity's pricing extraction zero-fills a model whose catalog
        # item carries NO pricing blob (float(... or 0)), so an all-zero
        # entry is indistinguishable from "unpriced" on this seam. An
        # entry counts as priced only when at least one direction is a
        # real nonzero figure: printing a fabricated "$0" price for a
        # paid model is exactly the invented number this surface exists
        # to refuse, and the design's rule for a missing price is to
        # omit the line entirely.
        def _priced(entry: Any) -> Optional[Tuple[Any, Any]]:
            if not isinstance(entry, dict):
                return None
            prompt = entry.get("prompt_per_million")
            completion = entry.get("completion_per_million")
            if prompt is None or completion is None:
                return None
            try:
                if float(prompt) <= 0 and float(completion) <= 0:
                    return None
            except (TypeError, ValueError):
                return None
            return prompt, completion

        sel_prices = _priced(pricing.get(selected))
        suc_prices = _priced(pricing.get(successor))
        if sel_prices is not None and suc_prices is not None:
            price_line = (
                f" It is listed at ${_fmt_price(suc_prices[0])} "
                f"in / ${_fmt_price(suc_prices[1])} out "
                f"per million tokens; your current model is listed at "
                f"${_fmt_price(sel_prices[0])} in / "
                f"${_fmt_price(sel_prices[1])} out.")
    lines.append(
        f"{prov} now lists {suc_name} in the same family.{price_line}")
    if offer.get("catalog_source") not in (None, "live"):
        lines.append(
            f"Checked against the provider's catalog as read at "
            f"{offer.get('probed_at')}.")
    lines.append("Your call:")
    if is_default:
        lines.append(
            f"1. Switch to {suc_name}. The choice is saved as your "
            f"choice, and this run and future runs use it.")
    else:
        lines.append(
            f"1. Switch to {suc_name}. Your saved choice updates, and "
            f"this run and future runs use it.")
    lines.append(
        f"2. Keep {sel_name}. Nothing changes. We will not ask about "
        f"{suc_name} again; a newer one would be a new question.")
    lines.append(
        f"3. Decide later. This run uses {sel_name}, and the choice "
        f"stays waiting for you.")
    lines.append("Keeping your current model never blocks your run.")
    return "\n".join(lines)


def pending_offer_block(profile: Optional[Dict[str, Any]] = None,
                        config_dir: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """The pending offers rendered for an interactive surface (the
    intake resource_plan turn): {"offers": [...], "text": ...}, or None
    when nothing is waiting. Read from the profile only -- presenting a
    pending offer never runs a new check and never touches the network."""
    offers = pending_offers(profile, config_dir=config_dir)
    if not offers:
        return None
    rendered = []
    for row in offers:
        offer = dict(row)
        offer.setdefault("selected_source", "client-plan")
        offer["text"] = render_offer_text(offer)
        rendered.append(offer)
    text = "\n\n".join(o["text"] for o in rendered)
    return {"offers": rendered, "text": text}


# ---------------------------------------------------------------------------
# Recording: check rows, pending rows, decisions (design 1.6 + 1.7)
# ---------------------------------------------------------------------------
def _log_row_from_check(row: Dict[str, Any], surface: str,
                        checked_at: str) -> Dict[str, Any]:
    return {"kind": "check", "check_id": row.get("check_id"),
            "checked_at": checked_at, "surface": surface,
            "provider": row.get("provider"), "family": row.get("family"),
            "selected_model": row.get("selected_model"),
            "selected_source": row.get("selected_source"),
            "status": row.get("status"),
            "successor_model": row.get("successor_model"),
            "catalog_source": row.get("catalog_source"),
            "snapshot_revision": row.get("snapshot_revision"),
            "note": row.get("note")}


def _pending_row_from_offer(offer: Dict[str, Any], surface: str,
                            checked_at: str) -> Dict[str, Any]:
    return {"provider": offer.get("provider"),
            "family": offer.get("family"),
            "selected_model": offer.get("selected_model"),
            "successor_model": offer.get("successor_model"),
            "offered_at": checked_at, "surface": surface,
            "check_id": offer.get("check_id"),
            "catalog_source": offer.get("catalog_source"),
            "probed_at": offer.get("probed_at")}


def record_check(verdict: Optional[Dict[str, Any]], *, surface: str,
                 config_dir: Optional[Any] = None,
                 interactive: bool = False) -> Optional[Dict[str, Any]]:
    """Persist one verdict's profile effects inside ONE profile
    transaction. This is the only writer of check rows and pending rows.

    interactive=True (the intake surface): every pair's check row is
    logged, a live offer becomes (or stays) a pending row, and a pending
    successor a fresh reading no longer lists is withdrawn with the
    reason logged.

    interactive=False (the launch surfaces): the deliberately narrow
    rule of design 1.7 -- (a) a successor neither already pending nor
    already decided for that pair earns one check row plus the pending
    row; (b) a pending successor absent from a fresh live catalog loses
    its pending row, with a check row noting the withdrawal. Every other
    launch verdict lives only in the run record."""
    if not flag_enabled() or not verdict:
        return None
    checks = verdict.get("checks") or []
    if not checks:
        return None
    rp = _resource_profile()
    if rp is None:
        return None
    checked_at = verdict.get("checked_at") or _now_iso()
    offers_by_pair = {
        _pair_key(o.get("provider"), o.get("family")): o
        for o in (verdict.get("offers") or []) if isinstance(o, dict)}
    recorded = 0
    with rp.profile_transaction(config_dir) as prof:
        interview = prof.get("interview")
        if not isinstance(interview, dict):
            interview = {}
            prof["interview"] = interview
        log = interview.get("model_freshness")
        if not isinstance(log, list):
            log = []
            interview["model_freshness"] = log
        summary = prof.get("model_freshness")
        if not isinstance(summary, dict):
            summary = {}
        pending = summary.get("pending")
        if not isinstance(pending, list):
            pending = []
        decisions = [r for r in log
                     if isinstance(r, dict) and r.get("kind") == "decision"]
        changed = False
        for row in checks:
            if not isinstance(row, dict):
                continue
            pair = _pair_key(row.get("provider"), row.get("family"))
            catalog_models = row.get("_catalog_models")
            withdrawn: List[Dict[str, Any]] = []
            if isinstance(catalog_models, list):
                live_ids = {_norm_id_for_compare(m) for m in catalog_models}
                withdrawn = [
                    p for p in pending
                    if _pair_key(p.get("provider"), p.get("family")) == pair
                    and _norm_id_for_compare(p.get("successor_model"))
                    not in live_ids]
            # Withdrawn-by-selection: the client has since declared the
            # pending successor directly as their saved selection (a
            # later plan answer naming it), so the offer is moot -- the
            # design does not name this edge; it is handled like a
            # catalog withdrawal, removed and logged, never presented
            # against a selection that already names the successor.
            moot: List[Dict[str, Any]] = []
            if row.get("selected_model"):
                moot = [
                    p for p in pending
                    if _pair_key(p.get("provider"), p.get("family")) == pair
                    and p.get("successor_model") == row.get("selected_model")
                    and p.get("selected_model") != row.get("selected_model")]
            offer = offers_by_pair.get(pair)

            def _remove(rows: List[Dict[str, Any]]) -> None:
                nonlocal changed
                for stale in rows:
                    if stale in pending:
                        pending.remove(stale)
                        changed = True

            def _withdrawal_notes() -> List[str]:
                notes = []
                if withdrawn:
                    notes.append(
                        f"pending successor "
                        f"{withdrawn[0].get('successor_model')} is no "
                        f"longer listed in the catalog; the offer is "
                        f"withdrawn")
                if moot:
                    notes.append(
                        f"pending successor "
                        f"{moot[0].get('successor_model')} is already "
                        f"the saved selection; the offer is withdrawn")
                return notes

            if interactive:
                logrow = _log_row_from_check(row, surface, checked_at)
                notes = _withdrawal_notes()
                if notes:
                    logrow["note"] = "; ".join(
                        [logrow["note"]] + notes if logrow.get("note")
                        else notes)
                    _remove(withdrawn)
                    _remove(moot)
                log.append(logrow)
                recorded += 1
                changed = True
                if offer is not None:
                    already = any(
                        _pair_key(p.get("provider"), p.get("family")) == pair
                        and p.get("successor_model")
                        == offer.get("successor_model")
                        for p in pending)
                    if not already:
                        pending.append(
                            _pending_row_from_offer(offer, surface, checked_at))
                continue
            # Launch surfaces: the narrow rule, nothing more.
            if offer is not None:
                already_pending = any(
                    _pair_key(p.get("provider"), p.get("family")) == pair
                    and p.get("successor_model") == offer.get("successor_model")
                    for p in pending)
                already_decided = any(
                    _pair_key(d.get("provider"), d.get("family")) == pair
                    and d.get("selected_model") == row.get("selected_model")
                    and d.get("successor_model") == offer.get("successor_model")
                    for d in decisions)
                if not already_pending and not already_decided:
                    log.append(_log_row_from_check(row, surface, checked_at))
                    recorded += 1
                    pending.append(
                        _pending_row_from_offer(offer, surface, checked_at))
                    changed = True
            elif withdrawn or moot:
                _remove(withdrawn)
                _remove(moot)
                logrow = _log_row_from_check(row, surface, checked_at)
                notes = _withdrawal_notes()
                logrow["note"] = "; ".join(
                    [logrow["note"]] + notes if logrow.get("note")
                    else notes)
                log.append(logrow)
                recorded += 1
                changed = True
        if interactive or changed:
            summary["last_checked_at"] = checked_at
            summary["last_status"] = verdict.get("status")
            summary["pending"] = pending
            prof["model_freshness"] = summary
    return {"recorded_checks": recorded,
            "pending": [dict(p) for p in pending if isinstance(p, dict)]}


def _fold_freshness_decision_into_model_choices(
        rp: Any, provider: str, successor: Optional[str],
        final_outcome: str, config_dir: Optional[Any],
        offered_at: Optional[str]) -> None:
    """Land one recorded freshness decision in B27's unified
    model-choice record (profile["model_choices"]), in that record's
    shape -- the convergence B40's build record named for B27's landing.

    The offered successor is recorded as a recommendation shown on its
    provider family's row (resource_profile.record_recommendation_shown),
    stamped with the offer's own time when it is known. The client's
    outcome becomes the entry's response: "switch" and "switch-refused"
    are recorded as "accepted" (the client accepted; a refusal is
    validation's act, its reason kept in the freshness log's detail, not
    a change of the client's mind); "keep" is "declined"; "defer"
    records no response, so the entry stands at "offered" -- the unified
    record's waiting state, exactly as the offer stands in the pending
    list. An applied switch additionally writes the family's selection
    through resource_profile.record_model_choice (source "selected"):
    the client did select the successor. No other outcome writes a
    selection, and a refused switch never does -- the saved selection
    did not move.

    Writes go only through resource_profile's model-choice writers. A
    failure inside the fold is announced on stderr and never un-records
    the decision the caller already wrote."""
    if rp is None or not provider or not successor:
        return
    try:
        prof = rp.load_profile(config_dir)
        row = rp.model_choice_row(provider, profile=prof) or {}
        entries = row.get("recommendations_shown") or []
        offered = any(
            isinstance(e, dict) and e.get("model") == successor
            and e.get("response") == "offered" for e in entries)
        if not offered:
            rp.record_recommendation_shown(
                provider, successor, MODEL_CHOICES_REASON, profile=prof)
            if offered_at:
                fresh = rp.model_choice_row(provider, profile=prof) or {}
                token = fresh.get("provider_family")
                for choice_row in prof.get("model_choices") or []:
                    if isinstance(choice_row, dict) and \
                            choice_row.get("provider_family") == token:
                        for entry in reversed(
                                choice_row.get("recommendations_shown")
                                or []):
                            if isinstance(entry, dict) and \
                                    entry.get("model") == successor and \
                                    entry.get("response") == "offered":
                                entry["shown_at"] = offered_at
                                break
                        break
        if final_outcome in ("switch", "switch-refused"):
            rp.record_recommendation_response(
                provider, successor, "accepted", profile=prof)
        elif final_outcome == "keep":
            rp.record_recommendation_response(
                provider, successor, "declined", profile=prof)
        if final_outcome == "switch":
            rp.record_model_choice(provider, successor,
                                   source="selected", profile=prof)
        rp.save_profile(prof, config_dir)
    except Exception as exc:  # noqa: BLE001 -- the fold never un-records
        print(f"model freshness: model-choice fold failed "
              f"({exc.__class__.__name__}: {exc})", file=sys.stderr)


def record_freshness_decision(check_id: Optional[str], outcome: str,
                              config_dir: Optional[Any] = None
                              ) -> Optional[Dict[str, Any]]:
    """Record the client's decision for one offered successor, inside a
    profile transaction. The single freshness-decision writer (the
    convergence pattern B28 set with record_route_decision). Since B27
    landed (PR #2035), the recorded decision also lands in B27's
    unified model-choice record through
    _fold_freshness_decision_into_model_choices -- the convergence this
    module's build record named for that landing.

    outcome is "switch", "keep" or "defer" -- the only three outcomes
    there are. Returns the recorded result {outcome, detail, message,
    ...}, or None when no check or pending offer carries `check_id`
    (nothing was outstanding, so nothing is recorded).

    On "switch" the change is applied FIRST through
    resource_profile.record_model_plan with a single-slot overlay
    (PRESERVE-BEFORE-OVERLAY keeps every other slot and its floor
    waivers), so a validation refusal leaves the saved selection exactly
    as it was; the refusal is then recorded as outcome "switch-refused"
    with the reason in `detail`, and the pending offer stays waiting --
    a refused switch never retries silently and never falls back to a
    different model. "keep" removes the pending row and suppresses the
    offer for that tuple (a strictly newer successor is a new question).
    "defer" keeps the pending row and refreshes its offered_at."""
    if not flag_enabled():
        return None
    outcome = str(outcome or "").strip().lower()
    if outcome not in OUTCOMES:
        raise ValueError(
            f"unknown freshness outcome {outcome!r} -- the outcomes are "
            f"{', '.join(OUTCOMES)}")
    rp = _resource_profile()
    if rp is None or not check_id:
        return None
    profile = rp.load_profile(config_dir)
    target: Optional[Dict[str, Any]] = None
    for row in reversed(_log_rows(profile)):
        if row.get("kind") == "check" and row.get("check_id") == check_id \
                and row.get("successor_model"):
            target = row
            break
    if target is None:
        for row in reversed(_pending_rows(profile)):
            if row.get("check_id") == check_id and row.get("successor_model"):
                target = row
                break
    if target is None:
        return None
    provider = str(target.get("provider") or "")
    family = str(target.get("family") or "")
    selected = target.get("selected_model")
    successor = target.get("successor_model")
    decided_at = _now_iso()
    final_outcome = outcome
    detail: Optional[str] = None

    if outcome == "switch":
        overlay_slot: Optional[str] = None
        for sel in effective_selections(profile):
            if sel["provider"] == provider and sel["selected_model"] == selected:
                overlay_slot = sel.get("overlay_slot") or sel.get("slot")
                break
        if overlay_slot is None:
            final_outcome = "switch-refused"
            detail = (f"the saved selection no longer names {selected} "
                      f"on {provider}, so there is no slot to update")
        if final_outcome == "switch":
            try:
                rp.record_model_plan(
                    {overlay_slot: {"provider": provider, "model": successor}},
                    source="interview", config_dir=config_dir)
            except ValueError as exc:
                final_outcome = "switch-refused"
                detail = str(exc)
            except Exception as exc:  # noqa: BLE001 -- a store failure is a refusal, recorded
                final_outcome = "switch-refused"
                detail = f"{exc.__class__.__name__}: {exc}"

    with rp.profile_transaction(config_dir) as prof:
        interview = prof.get("interview")
        if not isinstance(interview, dict):
            interview = {}
            prof["interview"] = interview
        log = interview.get("model_freshness")
        if not isinstance(log, list):
            log = []
            interview["model_freshness"] = log
        decision_row: Dict[str, Any] = {
            "kind": "decision", "check_id": check_id,
            "decided_at": decided_at, "surface": "intake",
            "provider": provider, "family": family,
            "selected_model": selected, "successor_model": successor,
            "outcome": final_outcome,
        }
        if detail:
            decision_row["detail"] = detail
        log.append(decision_row)
        summary = prof.get("model_freshness")
        if not isinstance(summary, dict):
            summary = {}
            prof["model_freshness"] = summary
        pending = summary.get("pending")
        if not isinstance(pending, list):
            pending = []
        if final_outcome in ("switch", "keep"):
            pending = [
                p for p in pending
                if not (_pair_key(p.get("provider"), p.get("family"))
                        == (provider, family)
                        and p.get("successor_model") == successor)]
        elif final_outcome == "defer":
            for p in pending:
                if _pair_key(p.get("provider"), p.get("family")) \
                        == (provider, family) \
                        and p.get("successor_model") == successor:
                    p["offered_at"] = decided_at
        summary["pending"] = pending

    _fold_freshness_decision_into_model_choices(
        rp, provider, successor, final_outcome, config_dir,
        target.get("offered_at") or target.get("checked_at"))

    prov = provider_display(provider)
    if final_outcome == "switch":
        message = (f"Switched to {display_name(successor)} on {prov}. "
                   f"Your saved choice is updated, and this run and "
                   f"future runs use it.")
    elif final_outcome == "switch-refused":
        message = (f"The switch to {display_name(successor)} could not "
                   f"be applied: {detail} Your saved model stays "
                   f"{display_name(selected)}, and the run proceeds on it.")
    elif final_outcome == "keep":
        message = (f"Keeping {display_name(selected)}. We will not ask "
                   f"about {display_name(successor)} again; a newer one "
                   f"would be a new question.")
    else:
        message = (f"Decide later noted. This run uses "
                   f"{display_name(selected)}, and the choice stays "
                   f"waiting for you.")
    return {"outcome": final_outcome, "check_id": check_id,
            "provider": provider, "family": family,
            "selected_model": selected, "successor_model": successor,
            "detail": detail, "message": message, "decided_at": decided_at}


def intake_check(config_dir: Optional[Any] = None,
                 transport: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Hook A's one call: check the just-saved profile and record the
    verdict at the intake surface (check rows logged, offers pending).
    Returns the verdict (whose "offers" the driver presents in the same
    turn), or None when the flag is off."""
    verdict = check_freshness(config_dir=config_dir, transport=transport)
    if verdict is None:
        return None
    try:
        record_check(verdict, surface="intake", config_dir=config_dir,
                     interactive=True)
    except Exception as exc:  # noqa: BLE001 -- recording never kills intake
        print(f"model freshness: could not record the intake check "
              f"({exc.__class__.__name__}: {exc})", file=sys.stderr)
    return verdict


# ---------------------------------------------------------------------------
# Section 1.5: the launch run record (Hooks B and C share this writer, so
# both dispatch paths leave the same evidence -- the FT-18 parity shape)
# ---------------------------------------------------------------------------
_PUBLIC_ROW_FIELDS = (
    "check_id", "provider", "slot", "family", "selected_model",
    "selected_source", "status", "successor_model", "selected_in_catalog",
    "catalog_source", "snapshot_revision", "probed_at", "catalog_error",
    "note",
)


def _public_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {field: row.get(field) for field in _PUBLIC_ROW_FIELDS}


def _run_decision(profile: Dict[str, Any],
                  verdict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The decision state a launch records for the currently offered
    successor: the recorded decision when one exists for that exact
    successor, else "pending" while the offer waits, else None."""
    decisions = _decision_rows(profile)
    pending = _pending_rows(profile)
    for row in verdict.get("checks") or []:
        if not isinstance(row, dict) or row.get("status") != STATUS_SUCCESSOR:
            continue
        pair = _pair_key(row.get("provider"), row.get("family"))
        successor = row.get("successor_model")
        for dec in reversed(decisions):
            if _pair_key(dec.get("provider"), dec.get("family")) == pair \
                    and dec.get("selected_model") == row.get("selected_model") \
                    and dec.get("successor_model") == successor:
                return {"outcome": dec.get("outcome"),
                        "successor_model": successor,
                        "decided_at": dec.get("decided_at"),
                        "surface": dec.get("surface")}
        for pend in pending:
            if _pair_key(pend.get("provider"), pend.get("family")) == pair \
                    and pend.get("successor_model") == successor:
                return {"outcome": "pending",
                        "successor_model": successor,
                        "decided_at": None,
                        "surface": pend.get("surface")}
    return None


def launch_check(run_dir: Any, mode: Optional[str] = None,
                 config_dir: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Hooks B and C: run the check at launch, write the run record,
    update the profile only under record_check's narrow launch rule,
    and return the verdict (enriched with "decision" and "run_record").

    There is NO refusal return value: every failure mode lands as an
    unknown-offline verdict in the record and the launch proceeds. The
    run record (<run_dir>/.model-freshness.json) ACCUMULATES checks
    across dispatches of the same run (a resume appends); its top-level
    status and decision always describe the latest check. The same
    object is merged into state.json under "model_freshness" when
    state.json exists, through the launcher's own _merge_run_state_field
    (StateStore under the run's RunLock); on a --new launch state.json
    does not exist yet in this window, so the sidecar is the record."""
    if not flag_enabled():
        return None
    run_path = Path(run_dir).expanduser()
    verdict = check_freshness(config_dir=config_dir)
    if verdict is None:
        return None
    try:
        record_check(verdict, surface="launch", config_dir=config_dir,
                     interactive=False)
    except Exception as exc:  # noqa: BLE001 -- recording never blocks a launch
        print(f"model freshness: could not record the launch check "
              f"({exc.__class__.__name__}: {exc})", file=sys.stderr)
    rp = _resource_profile()
    profile: Dict[str, Any] = {}
    if rp is not None:
        try:
            profile = rp.load_profile(config_dir)
        except Exception:  # noqa: BLE001 -- an unreadable store is unmeasured
            profile = {}
    decision = _run_decision(profile, verdict)
    record: Dict[str, Any] = {
        "run_dir": str(run_path),
        "surface": "launch",
        "checked_at": verdict.get("checked_at"),
        "mode": mode,
        "status": verdict.get("status"),
        "checks": [_public_row(r) for r in (verdict.get("checks") or [])
                   if isinstance(r, dict)],
        "decision": decision,
        "effective_selection": verdict.get("effective_selection") or [],
    }
    sidecar = run_path / RUN_RECORD_NAME
    try:
        existing: Dict[str, Any] = {}
        if sidecar.is_file():
            loaded = json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        prior_checks = existing.get("checks")
        if isinstance(prior_checks, list) and prior_checks:
            record["checks"] = prior_checks + record["checks"]
        run_path.mkdir(parents=True, exist_ok=True)
        tmp = sidecar.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, indent=2, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, sidecar)
    except (OSError, ValueError) as exc:
        print(f"model freshness: could not write the run record "
              f"{sidecar}: {exc}", file=sys.stderr)
    if (run_path / "state.json").is_file():
        try:
            launcher = _sibling("launcher")
            merge = getattr(launcher, "_merge_run_state_field", None)
            if callable(merge):
                merge(run_path,
                      lambda state: state.__setitem__("model_freshness",
                                                       record))
        except Exception:  # noqa: BLE001 -- the sidecar already carries it
            pass
    out = dict(verdict)
    out["decision"] = decision
    out["run_record"] = record
    return out


def launch_summary_lines(verdict: Optional[Dict[str, Any]]) -> List[str]:
    """The launcher's pre-launch freshness lines (design 4.1: the line
    is a record, not an offer). One line per notable pair (a successor
    waiting, or a check that could not be made), else one line stating
    the selections are current."""
    if not verdict:
        return []
    lines: List[str] = []
    offline_seen = set()
    for row in verdict.get("checks") or []:
        if not isinstance(row, dict):
            continue
        provider = row.get("provider") or ""
        if row.get("status") == STATUS_SUCCESSOR and not row.get("_suppressed"):
            suc = display_name(row.get("successor_model"))
            sel = display_name(row.get("selected_model"))
            prov = provider_display(provider)
            if row.get("selected_source") == "department-default":
                lines.append(
                    f"launcher: model freshness: {suc} is available as "
                    f"the successor to the department default {sel} "
                    f"({prov}). This run keeps the department default; "
                    f"the choice is waiting in your profile.")
            else:
                lines.append(
                    f"launcher: model freshness: {suc} is available as "
                    f"the successor to your saved {sel} ({prov}). This "
                    f"run keeps your saved model; the choice is waiting "
                    f"in your profile.")
        elif row.get("status") == STATUS_OFFLINE and provider not in offline_seen:
            offline_seen.add(provider)
            lines.append(
                f"launcher: model freshness: check offline for "
                f"{provider_display(provider)}; run proceeds on the "
                f"saved selection.")
    if not lines:
        lines.append(
            "launcher: model freshness: no newer model found for the "
            "recorded selections; the run proceeds on them.")
    return lines
