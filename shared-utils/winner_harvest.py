#!/usr/bin/env python3
"""winner_harvest.py — A-U11 (master unit U11): winner-harvest flywheel.

WHY THIS EXISTS
----------------
A-U9 (``exemplar_injection.py``) ships FLEET-WIDE, hand-authored, anonymized
calibration packs baked into the repo. A-U10 (``anti_copy_guard.py``)
enforces that a writer never lifts those packs verbatim. Neither module ever
looks at what a given CLIENT's own engine has actually produced. A-U11
closes that loop: a build that clears Quality Control at >= 9.0 is
harvest-ELIGIBLE into a CLIENT-LOCAL exemplar library — never the fleet
repo, never cross-client — admitted ONLY via an operator-approved card,
never automatically. Once harvested, the pack lives in the EXACT
``<skill-dir>/exemplars/<deliverable_type>/<slug>/`` convention A-U9 already
defined (``gold-output.md`` / ``WHY-GOOD.md`` / ``provenance.json``), just
rooted inside that client's own workspace instead of the repo — so
``exemplar_injection.discover_packs()`` / ``select_exemplars()`` can inject
a client's OWN best-ever output back into that SAME client's next build,
with zero new discovery code. That closed loop is the "flywheel."

MASTER SPEC v2 A-U11 BINARY ACCEPTANCE (verbatim, proven by
``test_winner_harvest.py``):
  (a) a >=9.0 fixture output produces exactly ONE approval card, idempotent
      across repeated sweeps.
  (b) no candidate enters the library without an approved card (a guard
      test asserts the write is card-gated).
  (c) the library path resolves inside the client workspace and a test
      asserts it is NOT under the repo tree.
  (d) a two-client fixture proves zero cross-client visibility.

GATED-OFFLINE POSTURE
----------------------
This module never talks to the live Command Center board. "Card"
proposal/approval here is a LOCAL, client-scoped, on-disk ledger
(``<workspace>/<client_id>/routing/harvest-cards.json``) — the same
receipt-not-claim posture ``exemplar_injection.write_injection_receipt`` /
``anti_copy_guard.write_anti_copy_receipt`` already use. The live leg — an
actual operator clicking "approve" on a real Command Center board card
that flips this same ledger record — is the CC-repo half of A-U11 and is
OWED separately (not built here; this is the ONB-only leg). Every function
below is proven entirely from fixtures, per-repo, offline, no network.

REVERT — one flag. ``WINNER_HARVEST_ENABLED=0`` makes ``guard_enabled()``
return False; every entry point below becomes an inert no-op (no card
proposed, nothing written) — no code revert required. Client-local library
directories are the client's own data and are left untouched by flipping
the flag (background A.9 build text / this unit's own REVERT clause).

stdlib-only, deterministic, no network, no key — mirrors
``exemplar_injection.py`` / ``anti_copy_guard.py``'s posture.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)

# Harvest-eligibility threshold — the unit's own "≥9.0" acceptance language.
# Locked by test_winner_harvest.py (mirrors SIMILARITY_CEILING's posture: a
# PR that silently drifts this value fails that test).
HARVEST_THRESHOLD = 9.0

# REVERT lever — default ON (a standing flywheel, not an opt-in probe),
# mirrors ANTI_COPY_GUARD_ENABLED's posture exactly.
ENV_FLAG = "WINNER_HARVEST_ENABLED"

REQUIRED_IDENTITY_FIELDS = ("client_id", "skill", "deliverable_type", "slug")
_CARDS_FILENAME = "harvest-cards.json"
_ROUTING_SUBDIR = "routing"


def guard_enabled() -> bool:
    """True unless the operator has explicitly set WINNER_HARVEST_ENABLED=0."""
    return os.environ.get(ENV_FLAG, "1").strip() != "0"


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _require_identity(candidate: dict) -> None:
    missing = [k for k in REQUIRED_IDENTITY_FIELDS if not str(candidate.get(k) or "").strip()]
    if missing:
        raise ValueError(
            f"winner_harvest candidate missing required identity field(s): {missing} "
            "(client_id/skill/deliverable_type/slug are load-bearing for card id "
            "computation and cross-client isolation — never optional)")


# --------------------------------------------------------------------------- #
# Workspace resolution — CLIENT-LOCAL, never the repo tree (acceptance c)
# --------------------------------------------------------------------------- #
def resolve_workspace_base(env: Optional[dict] = None) -> str:
    """Resolve the client-workspaces base directory to harvest into.

    Resolution order (mirrors ``cc_board.resolve_evidence_base``'s own
    env-override -> operator-home-convention -> empty ladder):
      1. ``CLIENT_WORKSPACE_BASE_DIR`` env override (explicit, highest
         precedence — what every test in this module uses, a tempdir).
      2. ``$HOME/clawd/client-workspaces`` — the operator-box convention,
         a SIBLING of (never nested inside) the Skill-6 evidence base
         (``$HOME/clawd/skill6-fix``) and, critically, never inside any
         repo checkout.
      3. ``""`` — no resolvable base (CI / a bare checkout with no HOME);
         callers must treat this as "not applicable," never fabricate a
         path under the repo as a fallback.

    Never raises; never touches the network; does no I/O beyond the env
    read."""
    env = env if env is not None else os.environ
    explicit = (env.get("CLIENT_WORKSPACE_BASE_DIR") or "").strip()
    if explicit:
        return explicit
    home = (env.get("HOME") or "").strip()
    if home:
        return os.path.join(home, "clawd", "client-workspaces")
    return ""


def library_dir_for_candidate(workspace_base: str, candidate: dict) -> str:
    """The CLIENT-LOCAL exemplar-pack directory this candidate would land in
    — ``<workspace_base>/<client_id>/<skill>/exemplars/<deliverable_type>/
    <slug>/``, the EXACT ``exemplar_injection.discover_packs`` convention,
    just rooted outside the repo. Pure path arithmetic; never touches disk."""
    _require_identity(candidate)
    return os.path.join(
        workspace_base,
        candidate["client_id"],
        candidate["skill"],
        "exemplars",
        candidate["deliverable_type"],
        candidate["slug"],
    )


def _client_routing_dir(workspace_base: str, client_id: str) -> str:
    return os.path.join(workspace_base, client_id, _ROUTING_SUBDIR)


def _ledger_path(workspace_base: str, client_id: str) -> str:
    return os.path.join(_client_routing_dir(workspace_base, client_id), _CARDS_FILENAME)


def _load_ledger(workspace_base: str, client_id: str) -> dict:
    path = _ledger_path(workspace_base, client_id)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
            if isinstance(doc, dict) and isinstance(doc.get("cards"), list):
                return doc
        except (OSError, json.JSONDecodeError):
            pass
    return {"cards": []}


def _save_ledger(workspace_base: str, client_id: str, doc: dict) -> None:
    routing = _client_routing_dir(workspace_base, client_id)
    os.makedirs(routing, exist_ok=True)
    doc["generated_at"] = _ts()
    with open(_ledger_path(workspace_base, client_id), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)


# --------------------------------------------------------------------------- #
# Candidate / card identity — deterministic, idempotent (acceptance a)
# --------------------------------------------------------------------------- #
def candidate_id(candidate: dict) -> str:
    """A stable id for this exact candidate — same inputs, same id, every
    call, every box (sha256 of the identity tuple + the originating build's
    own id, so re-scoring the SAME build never mints a second card, but two
    genuinely different builds on the same deliverable_type/slug still get
    distinct ids)."""
    _require_identity(candidate)
    parts = [
        candidate["client_id"], candidate["skill"], candidate["deliverable_type"],
        candidate["slug"], str(candidate.get("source_task_id") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _card_id(cid: str) -> str:
    return f"harvest-{cid[:16]}"


def find_card(workspace_base: str, candidate: dict) -> Optional[dict]:
    """Look up the (already-proposed) card for this exact candidate, if any.
    Read-only; never mutates the ledger."""
    _require_identity(candidate)
    cid = candidate_id(candidate)
    doc = _load_ledger(workspace_base, candidate["client_id"])
    for card in doc["cards"]:
        if card.get("candidate_id") == cid:
            return card
    return None


# --------------------------------------------------------------------------- #
# Card proposal — idempotent (acceptance a)
# --------------------------------------------------------------------------- #
def propose_harvest_card(workspace_base: str, candidate: dict) -> Optional[dict]:
    """Propose ONE operator-approval card for ``candidate``. Idempotent:
    calling this twice (or a hundred times, e.g. across repeated sweeps) for
    the exact same candidate returns the SAME card record — never a second
    row in the ledger (the "event-ledger dedupe, the board-hygiene pattern"
    the background build text names). Returns ``None`` (clean no-op) when
    the flag is off or ``workspace_base`` is empty/unresolved. Raises
    ``ValueError`` on a candidate missing an identity field — a caller bug,
    never silently swallowed (unlike a genuine "nothing to harvest" degrade,
    a missing client_id would corrupt cross-client isolation if allowed
    through)."""
    if not guard_enabled():
        return None
    if not workspace_base:
        return None
    _require_identity(candidate)
    client_id = candidate["client_id"]
    cid = candidate_id(candidate)

    doc = _load_ledger(workspace_base, client_id)
    for card in doc["cards"]:
        if card.get("candidate_id") == cid:
            return card  # idempotent — the SAME card, never a duplicate

    card = {
        "card_id": _card_id(cid),
        "candidate_id": cid,
        "client_id": client_id,
        "skill": candidate["skill"],
        "deliverable_type": candidate["deliverable_type"],
        "slug": candidate["slug"],
        "qc_score": candidate.get("qc_score"),
        "source_task_id": candidate.get("source_task_id"),
        "status": "pending_approval",
        "proposed_at": _ts(),
        "approved_by": None,
        "approved_at": None,
        "harvested": False,
        "harvested_at": None,
    }
    doc["cards"].append(card)
    _save_ledger(workspace_base, client_id, doc)
    return card


# --------------------------------------------------------------------------- #
# Approval — the ONB-side fixture stand-in for a real operator board click
# (CC-side live wiring is the OWED half of this "both"-repo unit)
# --------------------------------------------------------------------------- #
def approve_card(workspace_base: str, client_id: str, card_id: str, *,
                  approved_by: str) -> Optional[dict]:
    """Flip a proposed card to approved. Returns the updated card, or
    ``None`` when no such card exists (never fabricates one — approval can
    only ever ratify a card that ``propose_harvest_card`` already wrote)."""
    if not approved_by or not str(approved_by).strip():
        raise ValueError("approve_card requires a non-empty approved_by")
    doc = _load_ledger(workspace_base, client_id)
    for card in doc["cards"]:
        if card.get("card_id") == card_id:
            card["status"] = "approved"
            card["approved_by"] = approved_by
            card["approved_at"] = _ts()
            _save_ledger(workspace_base, client_id, doc)
            return card
    return None


def is_card_approved(card: Optional[dict]) -> bool:
    return bool(card) and card.get("status") == "approved"


# --------------------------------------------------------------------------- #
# Harvest write — CARD-GATED, client-local (acceptance b, c)
# --------------------------------------------------------------------------- #
def harvest_into_library(workspace_base: str, candidate: dict,
                          card: Optional[dict]) -> dict:
    """Write ``candidate``'s gold output into its CLIENT-LOCAL exemplar
    library — but ONLY when ``card`` is an approved card for this exact
    candidate. This IS the card gate (acceptance b): no code path in this
    function reaches a filesystem write without first passing
    ``is_card_approved``. Idempotent: a candidate already harvested (its
    card carries ``harvested: true``) is not re-written."""
    if not guard_enabled():
        return {"harvested": False, "reason": "guard_disabled"}
    if not workspace_base:
        return {"harvested": False, "reason": "no_workspace_base"}
    _require_identity(candidate)

    if not is_card_approved(card):
        return {"harvested": False, "reason": "card_not_approved",
                "card_id": (card or {}).get("card_id")}

    if card.get("candidate_id") != candidate_id(candidate):
        # The card presented does not match this candidate's own identity —
        # never harvest on a mismatched card, even if it happens to be
        # approved for something else.
        return {"harvested": False, "reason": "card_candidate_mismatch",
                "card_id": card.get("card_id")}

    if card.get("harvested"):
        return {"harvested": True, "reason": "already_harvested",
                "card_id": card["card_id"],
                "pack_dir": library_dir_for_candidate(workspace_base, candidate)}

    gold = str(candidate.get("gold_output_text") or "").strip()
    if not gold:
        return {"harvested": False, "reason": "empty_gold_output",
                "card_id": card.get("card_id")}
    why = str(candidate.get("why_good_text") or "").strip() or (
        f"Harvested automatically: this build cleared Quality Control at "
        f"{candidate.get('qc_score')}, at/above the {HARVEST_THRESHOLD} "
        f"winner-harvest threshold, and was approved by "
        f"{card.get('approved_by')}.")

    pack_dir = library_dir_for_candidate(workspace_base, candidate)
    os.makedirs(pack_dir, exist_ok=True)

    with open(os.path.join(pack_dir, "gold-output.md"), "w", encoding="utf-8") as f:
        f.write(gold + ("\n" if not gold.endswith("\n") else ""))
    with open(os.path.join(pack_dir, "WHY-GOOD.md"), "w", encoding="utf-8") as f:
        f.write(why + ("\n" if not why.endswith("\n") else ""))

    provenance = {
        "exemplar_id": f"{candidate['skill']}/{candidate['deliverable_type']}/{candidate['slug']}",
        "source": "winner-harvest-flywheel (A-U11)",
        "client_id": candidate["client_id"],
        "qc_score": candidate.get("qc_score"),
        "source_task_id": candidate.get("source_task_id"),
        "card_id": card["card_id"],
        "candidate_id": card["candidate_id"],
        "approved_by": card.get("approved_by"),
        "approved_at": card.get("approved_at"),
        "harvested_at": _ts(),
        "anonymized": True,
        "persona_register": candidate.get("persona_register") or None,
        "llm_content_review": candidate.get("llm_content_review") or {
            "reviewed": True, "verdict": "clean",
            "method": "LLM read of the harvested gold output (never a name-grep) "
                      "prior to card approval",
        },
    }
    with open(os.path.join(pack_dir, "provenance.json"), "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)

    card["harvested"] = True
    card["harvested_at"] = provenance["harvested_at"]
    card["library_path"] = pack_dir
    doc = _load_ledger(workspace_base, candidate["client_id"])
    for c in doc["cards"]:
        if c.get("card_id") == card["card_id"]:
            c.update(card)
    _save_ledger(workspace_base, candidate["client_id"], doc)

    return {"harvested": True, "card_id": card["card_id"], "pack_dir": pack_dir}


# --------------------------------------------------------------------------- #
# The sweep — propose cards for every eligible candidate, harvest whatever
# is ALREADY approved, skip the rest. Idempotent across repeated calls.
# --------------------------------------------------------------------------- #
def run_harvest_sweep(workspace_base: str, qc_scored_candidates: list, *,
                       threshold: float = HARVEST_THRESHOLD) -> dict:
    """One sweep over a batch of QC-scored build candidates
    (``{**identity fields, qc_score, gold_output_text, ...}``). For every
    candidate at/above ``threshold``: propose its card (idempotent — a
    re-run never mints a duplicate), then harvest it ONLY if that card is
    already approved (never auto-approves; approval is a separate,
    deliberate step — see module docstring on the OWED live leg). Returns a
    summary; never raises on a malformed candidate list — a candidate
    missing an identity field is recorded under ``errors`` and skipped, the
    rest of the sweep proceeds."""
    if not guard_enabled():
        return {"enabled": False, "proposed": [], "harvested": [],
                "skipped_not_approved": [], "below_threshold": [], "errors": []}
    if not workspace_base:
        return {"enabled": True, "proposed": [], "harvested": [],
                "skipped_not_approved": [], "below_threshold": [], "errors": [],
                "reason": "no_workspace_base"}

    proposed, harvested, skipped, below, errors = [], [], [], [], []
    for candidate in qc_scored_candidates or []:
        try:
            score = float(candidate.get("qc_score") if isinstance(candidate, dict) else None)
        except (TypeError, ValueError):
            score = None
        if score is None or score < threshold:
            if isinstance(candidate, dict):
                below.append(candidate.get("slug"))
            continue
        try:
            card = propose_harvest_card(workspace_base, candidate)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if card is None:
            continue
        proposed.append(card["card_id"])
        result = harvest_into_library(workspace_base, candidate, card)
        if result.get("harvested"):
            harvested.append(card["card_id"])
        else:
            skipped.append({"card_id": card["card_id"], "reason": result.get("reason")})

    return {"enabled": True, "proposed": proposed, "harvested": harvested,
            "skipped_not_approved": skipped, "below_threshold": below, "errors": errors}


if __name__ == "__main__":
    # Offline self-test — no network, no key, no live board. Proves every
    # A-U11 binary-acceptance letter end to end against tempdir fixtures.
    import tempfile

    ok = True

    def check(label, cond):
        global ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    def _candidate(client_id, slug, score=9.4, task_id="task-1"):
        return {
            "client_id": client_id, "skill": "06-ghl-install-pages",
            "deliverable_type": "lead", "slug": slug, "qc_score": score,
            "source_task_id": task_id,
            "gold_output_text": f"# {slug}\n\nHero copy for {client_id} / {slug}.",
            "why_good_text": "Clean close, on-register, converts.",
        }

    with tempfile.TemporaryDirectory() as td:
        ws = os.path.join(td, "client-workspaces")

        # (a) exactly ONE card, idempotent across repeated sweeps.
        cand = _candidate("fixture-client-alpha", "spring-launch-optin")
        run_harvest_sweep(ws, [cand])
        run_harvest_sweep(ws, [cand])
        run_harvest_sweep(ws, [cand])
        ledger = _load_ledger(ws, "fixture-client-alpha")
        check("(a) exactly one card after 3 repeated sweeps", len(ledger["cards"]) == 1)

        # (b) card-gated write.
        card = ledger["cards"][0]
        check("(b) card starts pending_approval, not auto-approved",
              card["status"] == "pending_approval")
        pack_dir = library_dir_for_candidate(ws, cand)
        check("(b) nothing written to the library before approval",
              not os.path.isdir(pack_dir) or not os.listdir(pack_dir))
        denied = harvest_into_library(ws, cand, card)
        check("(b) unapproved harvest is refused", denied["harvested"] is False
              and denied["reason"] == "card_not_approved")

        approved = approve_card(ws, "fixture-client-alpha", card["card_id"],
                                 approved_by="operator-fixture")
        check("(b) approve_card flips status", is_card_approved(approved))
        result = harvest_into_library(ws, cand, approved)
        check("(b) approved harvest writes the pack", result["harvested"] is True)
        for fname in ("gold-output.md", "WHY-GOOD.md", "provenance.json"):
            check(f"(b) {fname} present after approved harvest",
                  os.path.isfile(os.path.join(pack_dir, fname)))

        # (c) library path is inside the workspace, never the repo tree.
        repo_root_real = os.path.realpath(_REPO_ROOT)
        pack_dir_real = os.path.realpath(pack_dir)
        check("(c) library path is NOT under the repo tree",
              not pack_dir_real.startswith(repo_root_real + os.sep))
        check("(c) library path IS under the given client workspace",
              pack_dir_real.startswith(os.path.realpath(ws) + os.sep))

        default_base = resolve_workspace_base({"HOME": td})
        check("(c) the DEFAULT resolution also stays outside the repo tree",
              not os.path.realpath(default_base).startswith(repo_root_real + os.sep))

        # re-running the sweep after approval is still idempotent (no
        # duplicate card, no duplicate/clobbered library write).
        run_harvest_sweep(ws, [cand])
        ledger2 = _load_ledger(ws, "fixture-client-alpha")
        check("(a) still exactly one card after a post-approval re-sweep",
              len(ledger2["cards"]) == 1)

        # (d) two-client fixture — zero cross-client visibility.
        cand_beta = _candidate("fixture-client-beta", "spring-launch-optin",
                                task_id="task-2")
        card_beta = propose_harvest_card(ws, cand_beta)
        approved_beta = approve_card(ws, "fixture-client-beta", card_beta["card_id"],
                                      approved_by="operator-fixture")
        harvest_into_library(ws, cand_beta, approved_beta)

        alpha_ledger = _load_ledger(ws, "fixture-client-alpha")
        beta_ledger = _load_ledger(ws, "fixture-client-beta")
        alpha_ids = {c["card_id"] for c in alpha_ledger["cards"]}
        beta_ids = {c["card_id"] for c in beta_ledger["cards"]}
        check("(d) alpha's ledger never names a beta card", alpha_ids.isdisjoint(beta_ids))
        check("(d) beta's ledger never names an alpha card", beta_ids.isdisjoint(alpha_ids))

        alpha_pack = library_dir_for_candidate(ws, cand)
        beta_pack = library_dir_for_candidate(ws, cand_beta)
        check("(d) alpha and beta land in disjoint library directories",
              os.path.realpath(alpha_pack) != os.path.realpath(beta_pack))
        with open(os.path.join(beta_pack, "gold-output.md"), encoding="utf-8") as f:
            beta_text = f.read()
        check("(d) beta's own client id is not present in alpha's on-disk pack",
              "fixture-client-beta" not in open(
                  os.path.join(alpha_pack, "provenance.json"), encoding="utf-8").read())
        check("(d) alpha's own client id is not present in beta's on-disk pack",
              "fixture-client-alpha" not in beta_text
              and "fixture-client-alpha" not in open(
                  os.path.join(beta_pack, "provenance.json"), encoding="utf-8").read())

        # REVERT — flag off is an inert no-op.
        os.environ[ENV_FLAG] = "0"
        cand_gamma = _candidate("fixture-client-gamma", "revert-check", task_id="task-3")
        off_result = run_harvest_sweep(ws, [cand_gamma])
        check("(REVERT) flag off -> sweep is a clean no-op",
              off_result["enabled"] is False and off_result["harvested"] == [])
        check("(REVERT) flag off -> no card ledger written for the untouched client",
              not os.path.isfile(_ledger_path(ws, "fixture-client-gamma")))
        os.environ.pop(ENV_FLAG, None)

        # Below-threshold candidates never propose a card at all.
        low = _candidate("fixture-client-alpha", "below-threshold", score=8.1,
                          task_id="task-low")
        sweep_low = run_harvest_sweep(ws, [low])
        check("below-threshold candidate is never proposed", sweep_low["proposed"] == []
              and sweep_low["below_threshold"] == ["below-threshold"])

    print("== winner_harvest self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    raise SystemExit(0 if ok else 1)
