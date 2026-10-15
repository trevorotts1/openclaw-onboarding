#!/usr/bin/env python3
"""route_honesty.py -- the numeric honesty block (FIX 18, presentation rev2).

WHAT THIS IS
------------
At the resource_plan moment, when the client's selected route involves
Ollama, the client sees ONCE a plain-terms statement carrying three things:

  (a) THE PLAN NUMBERS for their setup -- the concurrency their Ollama tier
      actually buys, read from capacity.py's tables (CAP_TABLE for the
      resolved ceiling, ACCOUNT_LIMITS for the raw account limit and the
      operator reserve it is derived from), and what that means for a deck
      of their size in the only terms the code can honestly support:
      rounds of parallel work (ceil(deck_slides / ceiling)).
  (b) THE SPEED WARNING -- Ollama routes, local or cloud, are materially
      slower for this workload than direct API routes. Stated plainly,
      with NO multiplier: the retired "up to 16x faster" phrasing stays
      retired, and no other multiple is invented to replace it.
  (c) THE STANDING RECOMMENDATION (owner ruling 2026-10-13, mandated copy
      intent, not a plan option): for best results, use OpenRouter or
      DeepSeek Direct, with the reason -- neither route holds a deck back
      with a provider concurrency cap (OpenRouter has none at all;
      DeepSeek Direct's cap, read from the same CAP_TABLE, sits far above
      deck scale), so on those routes the machine is the only limit.

WHAT THIS MODULE NEVER DOES
---------------------------
  * It never invents a wall-clock estimate. The engine carries NO measured
    per-slide or per-stage time for the client's setup, so the block SAYS
    the estimate does not exist instead of dressing a guess as a number.
    Rounds of work at a measured concurrency is arithmetic on a table,
    labelled as such; minutes would be a fabrication.
  * It never prescribes. The client selects their model (or their
    configured default applies); this block is a recommendation with
    reasons, presented as guidance. Declining it is one action (keep the
    Ollama selection in the same answer), carries no penalty language,
    and the run proceeds on the client's selection exactly as chosen.
  * It never re-asks. Shown once per account-level answer set (fix-orders
    D8: only account-level resource answers carry over). The decision is
    recorded in the resource profile; a later run on the same account does
    not re-open it. A CHANGED selection re-opens the block once, for the
    new selection.

THE RECORD (additive; the B27 convergence point)
------------------------------------------------
The decision lives in the resource profile as `profile["route_honesty"]`
(the current record) plus an append-only log at
`profile["interview"]["route_honesty"]` (the same two-part shape the
profile already uses for interview.resource_plan / interview.model_plan):

    {
      "status": "offered" | "accepted" | "declined",
      "shown_signature":  <the selection the block was rendered for>,
      "decided_signature": <the selection in force after the answer>,
      "selection": {<slot>: {"provider": ..., "model": ...}, ...},
      "provider": "ollama-cloud",
      "plan_tier": "$20/month" | "$100/month" | None,
      "concurrency_ceiling": 3 | 8 | None,
      "deck_slides": <int the numbers were computed for> | None,
      "shown_at": ..., "decided_at": ...,
      "source": "intake"
    }

"accepted" means the client, after the offer, selected a route with no
Ollama in it. "declined" means the client's selection in force after the
answer still routes through Ollama -- they kept their pick, which is
their right, and the run proceeds on it. The record NEVER mutates the
model plan; it only reads it.

B27's unified model-choice record (profile["model_choices"]: per-family
rows written only through resource_profile's model-choice writers) has
landed (PR #2035). record_route_decision() -- the single writer of this
record's decision half -- now ALSO folds each decision into that record,
in its shape: the recommendation this block showed is recorded on the
family row of the Ollama route it was shown against, with the client's
response ("accepted" / "declined") as the entry's response. The
signatures and the slot snapshot have no home in the unified record's
shape and stay here; this record remains the module's working record
(ask-once, the launch restatement), and no caller changed when the fold
landed.

B11 SEAM (model freshness)
--------------------------
B11's freshness check joins this same moment (its DESIGN.md Hooks A/B/C).
The seam is mechanical:
  * intake: pending_honesty(profile) is the surface a consumer reads
    (the same posture as resource_profile.open_gap_records); the driver
    attaches this block to the resource_plan turn's output first, and
    B11's freshness offer attaches immediately after it, in the same turn.
  * launch: launcher.dispatch() prints launch_summary() immediately after
    model_plan_gate and before the FIX 11 mode-plan block; B11's one
    freshness summary line prints immediately after, inside the same
    pre-launch summary.
  * poller --new path: write_launch_sidecar() writes .route-honesty.json
    from launch_plan.write_launch_plan(); B11's record-only hook rides
    the same call site.
model_freshness.py lands beside this module in this same package and
imports it the same sibling way this module imports resource_profile.

REDACTION: every key above survives resource_profile.redact_record() by
construction -- no key contains a secret-named substring (key / token /
secret / password / auth / credential / cookie / bearer). The test suite
pins the save/load round trip so a future field rename cannot silently
drop the record the way "authoring" (auth) once threatened to.

Rollout flag: PRESENTATION_ROUTE_HONESTY=1 (default ON).
PRESENTATION_ROUTE_HONESTY=0 is the documented rollback: this module is
inert -- no block is rendered, nothing is recorded, and every consumer
(the intake driver, the launcher, the poller launch plan) behaves
byte-for-byte as before this fix.
"""

from __future__ import annotations

import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Feature flag (rollback path = explicitly-documented safe path)
# ---------------------------------------------------------------------------
FLAG_ENV = "PRESENTATION_ROUTE_HONESTY"
FLAG_DEFAULT = "1"

OLLAMA_CLOUD = "ollama-cloud"

#: Provider tokens that name a LOCAL Ollama route. capacity.py deliberately
#: refuses these as purchased capacity (a local daemon buys no plan), but a
#: model-plan slot can still route through one, and the speed warning is
#: about the route, not the receipt.
_LOCAL_OLLAMA_TOKENS = frozenset({
    "ollama-local", "ollama-localhost", "local-ollama",
})


def flag_enabled() -> bool:
    """True unless the operator exported PRESENTATION_ROUTE_HONESTY=0."""
    return os.environ.get(FLAG_ENV, FLAG_DEFAULT) != "0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Sibling imports (package-relative first, direct file run second -- the
# same posture resource_profile.py and capacity.py use for each other)
# ---------------------------------------------------------------------------
def _capacity():
    try:
        from . import capacity as _cap  # package-relative (python3 -m)
        return _cap
    except ImportError:  # pragma: no cover - direct file run
        import capacity as _cap  # type: ignore[no-redef]
        return _cap


def _resource_profile():
    try:
        from . import resource_profile as _rp  # package-relative
        return _rp
    except ImportError:  # pragma: no cover - direct file run
        import resource_profile as _rp  # type: ignore[no-redef]
        return _rp


# ---------------------------------------------------------------------------
# Deck size coercion (the driver and the launcher hand us whatever the
# intake recorded: an int, "55", "55 slides", or nothing at all)
# ---------------------------------------------------------------------------
_INT_RE = re.compile(r"(\d{1,4})")


def coerce_deck_slides(*values: Any) -> Optional[int]:
    """The first plausible deck size among `values`, or None.

    None is an honest answer: the block then speaks in per-round terms
    instead of deck-specific rounds, rather than inventing a deck size."""
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            if 1 <= value <= 2000:
                return value
            continue
        if isinstance(value, str):
            m = _INT_RE.search(value)
            if m:
                n = int(m.group(1))
                if 1 <= n <= 2000:
                    return n
    return None


# ---------------------------------------------------------------------------
# The selection picture: does this client's route involve Ollama?
# ---------------------------------------------------------------------------
def _is_ollama_provider(raw: Any, cap: Any) -> bool:
    """True when a provider spelling routes through Ollama, cloud or local."""
    if not isinstance(raw, str) or not raw.strip():
        return False
    if cap is not None:
        try:
            if cap.normalize_provider(raw) == OLLAMA_CLOUD:
                return True
            token = cap.canonical_provider_token(raw)
        except Exception:  # noqa: BLE001 -- a broken canon is not a route
            token = None
    else:
        token = raw.strip().lower().replace("_", "-").replace(" ", "-")
    return token in _LOCAL_OLLAMA_TOKENS


def ollama_context(profile: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The Ollama facts of the client's CURRENT selection, or None.

    The trigger, per FIX-PLAN Item 18 ("the warning fires when an
    Ollama-routed step is in the run's model plan") plus the model-choice
    principle's default arm ("or their configured default applies"):

      * any DECLARED model-plan slot routes through Ollama -> involved;
      * nothing is declared at all, but the profile carries an ollama-cloud
        account (detected / present) -> the account's route picture
        involves Ollama at the resource_plan moment (the tier question
        this turn asks is itself about that account);
      * slots ARE declared and none routes through Ollama -> NOT involved,
        however many providers the profile happens to carry. A client who
        selected their way off Ollama is never warned about a route they
        are not on.
    """
    prof = profile if isinstance(profile, dict) else {}
    cap = _capacity()
    rp = _resource_profile()
    plan = rp.model_plan(prof) if rp is not None else {}
    declared_slots: List[str] = []
    ollama_slots: List[str] = []
    for slot, spec in sorted((plan or {}).items()):
        if not isinstance(spec, dict):
            continue
        provider = spec.get("provider")
        if not provider:
            continue
        declared_slots.append(slot)
        if _is_ollama_provider(provider, cap):
            ollama_slots.append(slot)

    entry = rp.get_provider(prof, OLLAMA_CLOUD) if rp is not None else None
    account_present = bool(
        isinstance(entry, dict)
        and (entry.get("detected") or entry.get("presence")
             or entry.get("plan_known") or entry.get("locked")))
    if not account_present and rp is not None:
        # The engine's own ask-once surface says an Ollama plan answer is
        # still owed for this account: the resource_plan moment is then
        # about Ollama whether or not a probe has stamped the entry yet.
        try:
            account_present = any(
                q.get("provider") == OLLAMA_CLOUD
                for q in rp.pending_questions(profile=prof))
        except Exception:  # noqa: BLE001 -- a broken surface is not a route
            account_present = False
    if not ollama_slots and declared_slots:
        return None  # declared, and declared OFF Ollama
    if not ollama_slots and not account_present:
        return None
    plan_tier = None
    tier_locked = False
    if isinstance(entry, dict):
        plan_tier = entry.get("plan_tier")
        tier_locked = bool(entry.get("locked") or entry.get("plan_known"))
    local_only = bool(ollama_slots) and not account_present and not entry
    return {
        "slots": ollama_slots,
        "declared_slots": declared_slots,
        "via": "model-plan" if ollama_slots else "account",
        "plan_tier": plan_tier if tier_locked else None,
        "tier_locked": tier_locked,
        "local_only": local_only,
    }


def selection_signature(profile: Optional[Dict[str, Any]]) -> str:
    """A stable, readable fingerprint of the account-level answer set the
    block is shown against: every declared slot's provider/model plus the
    Ollama plan tier in force. Any change to the selection changes this
    string, which is exactly what re-opens the block (once) -- and nothing
    else does."""
    prof = profile if isinstance(profile, dict) else {}
    rp = _resource_profile()
    plan = rp.model_plan(prof) if rp is not None else {}
    parts: List[str] = []
    for slot in sorted(plan or {}):
        spec = plan.get(slot)
        if isinstance(spec, dict) and spec.get("provider"):
            parts.append(f"{slot}={spec.get('provider')}/{spec.get('model')}")
    ctx = ollama_context(prof)
    tier = ctx.get("plan_tier") if ctx else None
    parts.append(f"ollama-tier={tier or ''}")
    parts.append(f"ollama={'yes' if ctx else 'no'}")
    return ";".join(parts)


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------
def current_record(profile: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    prof = profile if isinstance(profile, dict) else {}
    rec = prof.get("route_honesty")
    return rec if isinstance(rec, dict) else None


def block_owed(profile: Optional[Dict[str, Any]]) -> bool:
    """True when the block must be presented at this resource_plan moment:
    the flag is on, the route involves Ollama, and no decision is on record
    FOR THE SELECTION CURRENTLY IN FORCE. An "offered" record is a showing,
    not a decision -- it never closes the question by itself."""
    if not flag_enabled():
        return False
    prof = profile if isinstance(profile, dict) else {}
    if ollama_context(prof) is None:
        return False
    rec = current_record(prof)
    if rec and rec.get("status") in ("accepted", "declined"):
        if rec.get("decided_signature") == selection_signature(prof):
            return False
    return True


def pending_honesty(profile: Optional[Dict[str, Any]] = None,
                    deck_slides: Optional[int] = None,
                    config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """The intake/notification surface for FIX 18 -- the same posture as
    resource_profile.open_gap_records(): everything a consumer (the intake
    driver today, B11's freshness check beside it tomorrow) needs to
    present the block once and record the answer, without re-deriving the
    state machine. Returns {"owed", "record", "block"}; "block" is the
    rendered text when owed, else None."""
    rp = _resource_profile()
    prof = profile if profile is not None else rp.load_profile(config_dir)
    owed = block_owed(prof)
    rendered = render_block(prof, deck_slides=deck_slides) if owed else None
    return {
        "owed": owed,
        "record": current_record(prof),
        "block": rendered["text"] if rendered else None,
        "facts": rendered["facts"] if rendered else None,
    }


# ---------------------------------------------------------------------------
# Rendering -- every number from capacity.py's tables, never a literal
# ---------------------------------------------------------------------------
def _tier_rows(cap: Any) -> List[Dict[str, Any]]:
    """The Ollama rows of the capacity tables, as renderable facts."""
    rows = []
    for plan in cap.PLANS_BY_PROVIDER.get(OLLAMA_CLOUD, ()):
        ceiling = cap.CAP_TABLE.get((OLLAMA_CLOUD, plan))
        limit, reserve = cap.ACCOUNT_LIMITS.get((OLLAMA_CLOUD, plan), (None, None))
        rows.append({"plan": plan, "ceiling": ceiling,
                     "account_limit": limit, "reserve": reserve})
    return rows


def _ceiling_clause(row: Dict[str, Any]) -> str:
    """One tier's numbers as a clause (no plan prefix), from the tables."""
    ceiling = row["ceiling"]
    limit, reserve = row["account_limit"], row["reserve"]
    if limit is not None and reserve:
        return (f"allows {limit} at once at the account; this engine uses "
                f"{ceiling} at a time and keeps {reserve} in reserve for "
                f"your other work")
    if limit is not None:
        return (f"allows {limit} at once at the account, and this engine "
                f"uses {ceiling} at a time")
    return f"allows {ceiling} at a time"


def _ceiling_sentence(row: Dict[str, Any]) -> str:
    """One tier's numbers in plain terms, from the tables."""
    return f"{row['plan']} {_ceiling_clause(row)}"


def recommendation_text(cap: Any) -> str:
    """THE mandated recommendation (owner ruling 2026-10-13), rendered with
    the DeepSeek Direct numbers read from CAP_TABLE at render time."""
    ds_caps = sorted(
        n for (p, _plan), n in cap.CAP_TABLE.items() if p == "deepseek-direct")
    if len(ds_caps) >= 2:
        ds_span = f"{ds_caps[0]} to {ds_caps[-1]}"
    elif ds_caps:
        ds_span = f"{ds_caps[0]}"
    else:  # pragma: no cover - the table always carries DeepSeek rows today
        ds_span = "hundreds"
    return (
        "Recommendation: for best results, use OpenRouter or DeepSeek "
        "Direct. Neither route holds a deck back with a provider "
        "concurrency cap: OpenRouter has no provider concurrency cap at "
        f"all, and DeepSeek Direct's cap ({ds_span} at once) is far above "
        "any deck this engine builds, so on those routes your machine is "
        "the only limit."
    )


SPEED_WARNING = (
    "Speed: Ollama routes, whether local or cloud, are materially slower "
    "for this workload than direct API routes."
)

NO_ESTIMATE_NOTE = (
    "One honest limit: this engine has no measured per-slide time for "
    "your setup, so there is no honest minutes estimate for the "
    "difference, and we will not invent one. The concurrency numbers "
    "here come from your plan's own table; the time difference is real "
    "but unmeasured in this engine."
)

CHOICE_NOTE = (
    "The choice is yours, and it is recorded once: keep your Ollama "
    "selection in this answer and the run proceeds on it exactly as "
    "chosen, or name an OpenRouter or DeepSeek Direct model instead. "
    "Declining this recommendation changes nothing about how your deck "
    "is handled, and we will not ask again unless you change your "
    "selection."
)

#: The standing recommendation as it is described inside B27's unified
#: model-choice record (the `reason` on the recommendation entry a route
#: decision folds there). No numbers: the capacity tables move, and a
#: recorded reason must not go stale against them; the rendered block
#: remains the only place numbers are quoted, read live at render time.
MODEL_CHOICES_REASON = (
    "Route honesty: for best results use OpenRouter or DeepSeek "
    "Direct, because neither route holds a deck back with a provider "
    "concurrency cap, so on those routes your machine is the only limit."
)


def render_block(profile: Optional[Dict[str, Any]],
                 deck_slides: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Render the honesty block for the profile's current selection.

    Pure: reads the profile dict and capacity's tables, writes nothing.
    Returns {"text", "facts"} or None when the route does not involve
    Ollama (or the flag is off). `facts` carries the machine-readable
    numbers the text was built from, so a consumer never has to parse the
    prose to recover them."""
    if not flag_enabled():
        return None
    prof = profile if isinstance(profile, dict) else {}
    ctx = ollama_context(prof)
    if ctx is None:
        return None
    cap = _capacity()
    rows = _tier_rows(cap)
    slides = coerce_deck_slides(deck_slides)
    facts: Dict[str, Any] = {
        "provider": OLLAMA_CLOUD,
        "plan_tier": ctx.get("plan_tier"),
        "tier_locked": bool(ctx.get("tier_locked")),
        "local_only": bool(ctx.get("local_only")),
        "deck_slides": slides,
        "slots": list(ctx.get("slots") or []),
        "via": ctx.get("via"),
    }

    lines: List[str] = []
    lines.append(
        "ROUTE HONESTY (shown once, then remembered): your selected "
        "route uses Ollama, so here are your real numbers before this "
        "turn is recorded.")

    # (a) the plan numbers
    if ctx.get("local_only"):
        lines.append(
            "Your numbers: your selection routes through Ollama on your "
            "own machine. A local route has no purchased plan tier, so "
            "there is no provider concurrency number to quote for it: "
            "its pace is set by your machine and the local model, and "
            "this engine carries no measured figure for either.")
        facts["concurrency_ceiling"] = None
    elif ctx.get("tier_locked") and ctx.get("plan_tier"):
        row = next((r for r in rows if r["plan"] == ctx["plan_tier"]), None)
        if row is not None:
            lines.append(
                f"Your numbers: your Ollama Cloud plan is {row['plan']}: "
                f"it {_ceiling_clause(row)}.")
            facts["concurrency_ceiling"] = row["ceiling"]
            if slides and row["ceiling"]:
                rounds = math.ceil(slides / row["ceiling"])
                facts["rounds"] = rounds
                lines.append(
                    f"For a deck of {slides} slides, the slide work alone "
                    f"runs in rounds of at most {row['ceiling']} at a "
                    f"time: about {rounds} rounds. Every parallel stage "
                    f"of the build follows the same cap.")
        else:  # pragma: no cover - a locked tier always has a table row
            lines.append(
                "Your numbers: your Ollama Cloud plan tier is recorded, "
                "but the capacity table carries no row for it, so no "
                "concurrency number is quoted for it here.")
            facts["concurrency_ceiling"] = None
    else:
        joined = "; ".join(_ceiling_sentence(r) for r in rows)
        lines.append(
            "Your numbers: your Ollama Cloud plan tier is not recorded "
            f"yet, and the tier sets the pace: {joined}. The tier you "
            "confirm in this turn is the one these numbers follow.")
        facts["concurrency_ceiling"] = None
        if slides:
            per_tier = []
            for r in rows:
                if r["ceiling"]:
                    per_tier.append(
                        f"at {r['ceiling']} at a time ({r['plan']}), about "
                        f"{math.ceil(slides / r['ceiling'])} rounds")
            if per_tier:
                lines.append(
                    f"For a deck of {slides} slides, the slide work alone "
                    f"runs in rounds: {'; '.join(per_tier)}.")

    # (b) the speed warning
    lines.append(SPEED_WARNING)

    # (c) the mandated recommendation
    lines.append(recommendation_text(cap))
    if slides:
        lines.append(
            f"On OpenRouter or DeepSeek Direct, those {slides} slides "
            "carry no provider round limit at deck scale: the work can "
            "be in flight all at once, as fast as your machine can run "
            "it.")

    # the honest absence of a time estimate
    lines.append(NO_ESTIMATE_NOTE)

    # the choice, with no penalty attached to either side of it
    lines.append(CHOICE_NOTE)

    return {"text": "\n".join(lines), "facts": facts}


# ---------------------------------------------------------------------------
# Writers -- the ONLY writers of the route_honesty record
# ---------------------------------------------------------------------------
def _selection_snapshot(profile: Dict[str, Any]) -> Dict[str, Any]:
    rp = _resource_profile()
    plan = rp.model_plan(profile) if rp is not None else {}
    return {slot: dict(spec) for slot, spec in sorted((plan or {}).items())
            if isinstance(spec, dict) and spec.get("provider")}


def _base_record(profile: Dict[str, Any],
                 deck_slides: Optional[int]) -> Dict[str, Any]:
    ctx = ollama_context(profile) or {}
    cap = _capacity()
    ceiling = None
    if ctx.get("tier_locked") and ctx.get("plan_tier") and cap is not None:
        ceiling = cap.CAP_TABLE.get((OLLAMA_CLOUD, ctx["plan_tier"]))
    return {
        "provider": OLLAMA_CLOUD,
        "plan_tier": ctx.get("plan_tier"),
        "concurrency_ceiling": ceiling,
        "deck_slides": coerce_deck_slides(deck_slides),
        "selection": _selection_snapshot(profile),
        "shown_signature": selection_signature(profile),
    }


def note_block_shown(deck_slides: Optional[int] = None,
                     profile: Optional[Dict[str, Any]] = None,
                     config_dir: Optional[Path] = None,
                     source: str = "intake") -> Optional[Dict[str, Any]]:
    """Record THAT the block was presented (status "offered"), without
    recording a decision the client has not made yet.

    Called by the intake driver when it attaches the block to the
    resource_plan turn. A showing never overwrites a decision already on
    record for the current selection, and never fires when the block is
    not owed. Returns the record written, or the existing record when no
    write was needed, or None when the surface is inert."""
    if not flag_enabled():
        return None
    rp = _resource_profile()
    base = profile if profile is not None else rp.load_profile(config_dir)
    if not block_owed(base):
        return current_record(base)

    def _apply(prof: Dict[str, Any]) -> Dict[str, Any]:
        rec = _base_record(prof, deck_slides)
        rec.update({
            "status": "offered",
            "decided_signature": None,
            "shown_at": _now(),
            "decided_at": None,
            "source": str(source or "intake"),
        })
        prof["route_honesty"] = rec
        log = prof.setdefault("interview", {}).setdefault("route_honesty", [])
        log.append({"event": "shown", "status": "offered",
                    "shown_signature": rec["shown_signature"],
                    "at": rec["shown_at"], "source": rec["source"]})
        return rec

    if profile is not None:
        rec = _apply(profile)
        rp.save_profile(profile, config_dir)
        return dict(rec)
    with rp.profile_transaction(config_dir) as prof:
        if not block_owed(prof):
            return current_record(prof)
        written = _apply(prof)
    return dict(written)


def _selection_pairs(selection: Any) -> List:
    """The distinct (provider, model) pairs of a selection snapshot, in
    slot order."""
    pairs: List = []
    for _slot, spec in sorted((selection or {}).items()):
        if isinstance(spec, dict) and spec.get("provider") \
                and spec.get("model"):
            pair = (spec["provider"], spec["model"])
            if pair not in pairs:
                pairs.append(pair)
    return pairs


def _ollama_selection_pairs(selection: Any, cap: Any) -> List:
    """The pairs of a selection snapshot that route through Ollama."""
    return [pair for pair in _selection_pairs(selection)
            if _is_ollama_provider(pair[0], cap)]


def _correct_fold_shown_at(prof: Dict[str, Any], provider: str,
                           model: str, shown_at: str, cap: Any) -> None:
    """Correct the recommendation entry the fold just appended so its
    shown_at is the moment the block was actually shown (the offered
    record's stamp), not the moment the decision folded it. The appended
    entry is the latest offered one for its model in the family's row."""
    token = None
    if cap is not None:
        try:
            token = cap.canonical_provider_token(provider)
        except Exception:  # noqa: BLE001 -- spelling fold only
            token = None
    if not token:
        token = str(provider or "").strip().lower() \
            .replace("_", "-").replace(" ", "-")
    for row in prof.get("model_choices") or []:
        if isinstance(row, dict) and row.get("provider_family") == token:
            for entry in reversed(row.get("recommendations_shown") or []):
                if isinstance(entry, dict) and entry.get("model") == model \
                        and entry.get("response") == "offered":
                    entry["shown_at"] = shown_at
                    return


def _fold_route_decision_into_model_choices(
        prof: Dict[str, Any], rec: Dict[str, Any],
        prior: Dict[str, Any]) -> None:
    """Fold one recorded route decision into B27's unified model-choice
    record (profile["model_choices"]), in that record's shape.

    The recommendation this module shows is a ROUTE recommendation (use
    OpenRouter or DeepSeek Direct instead of the Ollama route); it names
    no model. The unified record's recommendation entries are keyed by
    (provider family, model), so the entry is recorded on the family row
    of the Ollama route the block was shown against -- one entry per
    distinct Ollama model in the selection the block was shown for --
    with MODEL_CHOICES_REASON as the reason and the decision's status as
    the response. The shown selection is the offered record's snapshot
    when it stands for this showing, else the decision's own snapshot.
    An acceptance whose shown selection carried no Ollama model (the
    offer rode the account arm) folds against the models the client
    moved to. A decision with no model anywhere folds nothing: the
    unified record keys recommendations by model, and no model is ever
    invented to fill the gap.

    Writes go ONLY through resource_profile's model-choice writers, on
    this function's in-flight profile, so the fold lands in the same
    profile write as the decision itself. No selection is ever written
    here: accepting the recommendation reaches a selection only through
    the client's own plan answer (the model-plan recorder), never
    through this record (owner decision 4). A failure inside the fold is
    announced on stderr and never un-records the decision."""
    import sys
    try:
        rp = _resource_profile()
        if rp is None:
            return
        status = rec.get("status")
        if status not in ("accepted", "declined"):
            return
        cap = _capacity()
        shown_sel = None
        if prior.get("status") == "offered" and \
                prior.get("shown_signature") == rec.get("shown_signature"):
            shown_sel = prior.get("selection")
        pairs = _ollama_selection_pairs(shown_sel, cap)
        if not pairs:
            pairs = _ollama_selection_pairs(rec.get("selection"), cap)
        if not pairs and status == "accepted":
            pairs = _selection_pairs(rec.get("selection"))
        for provider, model in pairs:
            row = rp.model_choice_row(provider, profile=prof) or {}
            entries = row.get("recommendations_shown") or []
            offered = any(
                isinstance(e, dict) and e.get("model") == model
                and e.get("response") == "offered" for e in entries)
            if not offered:
                rp.record_recommendation_shown(
                    provider, model, MODEL_CHOICES_REASON, profile=prof)
                if prior.get("shown_at"):
                    _correct_fold_shown_at(
                        prof, provider, model, prior["shown_at"], cap)
            rp.record_recommendation_response(
                provider, model, status, profile=prof)
    except Exception as exc:  # noqa: BLE001 -- the fold never un-records
        print(f"route_honesty: model-choice fold failed "
              f"({exc.__class__.__name__}: {exc})", file=sys.stderr)


def record_route_decision(pre_signature: Optional[str] = None,
                          pre_owed: Optional[bool] = None,
                          deck_slides: Optional[int] = None,
                          profile: Optional[Dict[str, Any]] = None,
                          config_dir: Optional[Path] = None,
                          source: str = "intake") -> Optional[Dict[str, Any]]:
    """Record the client's decision after the resource_plan answer lands.

    THE CONVERGENCE POINT for B27's model-choice record: this is the one
    writer of the decision half of the record, and since B27 landed
    (PR #2035) it also folds the decision into profile["model_choices"]
    through _fold_route_decision_into_model_choices -- the re-point the
    build record named, landed with no caller changed.

    `pre_signature` / `pre_owed` describe the selection the block was
    owed for BEFORE the answer was recorded (the intake driver captures
    them at the top of the resource_plan branch, before the plan-tier and
    model-plan recorders run). When omitted, they are derived from the
    profile's own record: an "offered" record IS an outstanding offer, and
    its shown_signature is the selection that offer was made against.

    The verdict reads the selection in force AFTER the answer:
      still routes through Ollama  -> "declined" (they kept their pick;
                                      the run proceeds on it);
      no longer routes via Ollama  -> "accepted".
    Nothing is recorded when no offer was outstanding (pre_owed False):
    an offer that never happened is never invented after the fact.
    This function NEVER mutates the model plan."""
    if not flag_enabled():
        return None
    rp = _resource_profile()
    base = profile if profile is not None else rp.load_profile(config_dir)
    if pre_owed is None:
        standing = current_record(base)
        owed_before = bool(standing and standing.get("status") == "offered")
        if pre_signature is None and standing:
            pre_signature = standing.get("shown_signature")
    else:
        owed_before = bool(pre_owed)
    if not owed_before:
        return current_record(base)
    shown_sig = pre_signature or selection_signature(base)

    def _apply(prof: Dict[str, Any]) -> Dict[str, Any]:
        # `prof` here is the POST-answer state (the driver's recorders
        # have already saved when it calls us; a direct caller hands the
        # post-answer profile in). The verdict reads the selection in
        # force as it stands now.
        ctx_after = ollama_context(prof)
        status = "declined" if ctx_after is not None else "accepted"
        rec = _base_record(prof, deck_slides)
        prior = current_record(prof) or {}
        rec.update({
            "status": status,
            "shown_signature": shown_sig,
            "decided_signature": selection_signature(prof),
            "shown_at": prior.get("shown_at") if prior.get("status") == "offered"
                        and prior.get("shown_signature") == shown_sig else None,
            "decided_at": _now(),
            "source": str(source or "intake"),
        })
        prof["route_honesty"] = rec
        log = prof.setdefault("interview", {}).setdefault("route_honesty", [])
        log.append({"event": "decision", "status": status,
                    "shown_signature": shown_sig,
                    "decided_signature": rec["decided_signature"],
                    "at": rec["decided_at"], "source": rec["source"]})
        _fold_route_decision_into_model_choices(prof, rec, prior)
        return rec

    if profile is not None:
        rec = _apply(profile)
        rp.save_profile(profile, config_dir)
        return dict(rec)
    with rp.profile_transaction(config_dir) as prof:
        written = _apply(prof)
    return dict(written)


# ---------------------------------------------------------------------------
# Launch surface -- the restatement at launch (Item 18: "and again at
# launch"). A summary, never a second ask: the decision, once recorded,
# is reported; the launch proceeds on the client's selection either way.
# ---------------------------------------------------------------------------
def launch_summary(profile: Optional[Dict[str, Any]] = None,
                   deck_slides: Optional[int] = None,
                   config_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """The pre-launch restatement for a run whose route involves Ollama.

    Returns {"text", "record"} or None when the route does not involve
    Ollama (or the flag is off). The text carries the same numbers, the
    same warning and the recorded decision (or the standing
    recommendation, plainly labelled unrecorded, when intake never
    produced one). It never blocks and never re-asks."""
    if not flag_enabled():
        return None
    rp = _resource_profile()
    prof = profile if profile is not None else rp.load_profile(config_dir)
    ctx = ollama_context(prof)
    if ctx is None:
        return None
    cap = _capacity()
    slides = coerce_deck_slides(deck_slides)
    rec = current_record(prof)
    ceiling = None
    if ctx.get("tier_locked") and ctx.get("plan_tier") and cap is not None:
        ceiling = cap.CAP_TABLE.get((OLLAMA_CLOUD, ctx["plan_tier"]))
    facts: Dict[str, Any] = {
        "provider": OLLAMA_CLOUD,
        "plan_tier": ctx.get("plan_tier"),
        "concurrency_ceiling": ceiling,
        "deck_slides": slides,
        "decision": (rec or {}).get("status"),
        "decided_at": (rec or {}).get("decided_at"),
        "selection": _selection_snapshot(prof),
    }
    numbers = ""
    if ceiling is not None:
        numbers = (f"Ollama Cloud {ctx['plan_tier']}: {ceiling} at a time"
                   + (f"; a deck of {slides} slides runs its slide work "
                      f"in about {math.ceil(slides / ceiling)} rounds"
                      if slides else ""))
    elif ctx.get("local_only"):
        numbers = "a local Ollama route (no purchased plan tier)"
    else:
        numbers = "Ollama Cloud, plan tier not recorded"
    if rec and rec.get("status") in ("accepted", "declined"):
        decision_line = (
            f"route recommendation {rec['status']} at intake "
            f"({rec.get('decided_at')}); proceeding on the client's "
            "selection")
    else:
        decision_line = (
            "no route decision on record; the standing recommendation "
            "is OpenRouter or DeepSeek Direct for best results; "
            "proceeding on the client's selection")
    text = (f"route honesty: this run routes through Ollama ({numbers}). "
            f"{SPEED_WARNING} {decision_line}.")
    return {"text": text, "record": facts}


def write_launch_sidecar(run_dir: Path,
                         profile: Optional[Dict[str, Any]] = None,
                         deck_slides: Optional[int] = None,
                         config_dir: Optional[Path] = None) -> bool:
    """Write .route-honesty.json beside the other launch sidecars.

    The durable launch record for the dispatch path that does NOT go
    through the launcher (the poller's --new branch, launch_plan.py's
    call site; the launcher writes the same file at its own print site,
    so both paths leave the same evidence). Best-effort, always: a
    record that cannot be written is announced on stderr by the caller
    pattern and never blocks a dispatch. Returns True when a sidecar
    was written."""
    import json
    import sys
    summary = launch_summary(profile=profile, deck_slides=deck_slides,
                             config_dir=config_dir)
    if summary is None:
        return False
    path = Path(run_dir) / ".route-honesty.json"
    payload = {"run_dir": str(run_dir), "route_honesty": summary["record"],
               "text": summary["text"]}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError as exc:
        print(f"route_honesty: could not write {path.name}: {exc}",
              file=sys.stderr)
        return False
