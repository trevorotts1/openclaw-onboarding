#!/usr/bin/env python3
"""ghl_routing_drift_check.py — U23/B-U9 monthly routing-drift live proof.

WHAT THIS IS
------------
The scheduled monthly live proof that the decision engine's VERCEL_EMBED
routing path still actually WORKS end to end on real infrastructure, not
just in theory: deploy the golden ADVANCED fixture to Vercel, prove it is
embeddable, and write a dated receipt. This catches a routing DRIFT the
offline regression corpus (``tests/fixtures/routing_corpus.json`` +
``scripts/guard-ghl-method-decision.sh --corpus``) cannot by construction:
the corpus proves ``classify_page``'s LOGIC hasn't regressed (pure, no
network); this proves the VERCEL_EMBED escape hatch the engine routes
ADVANCED pages to is still a live, embeddable deployment path on the
operator's own box.

THE FOUR-STEP PROOF (spec: B-U9 acceptance (d) — "deploy the golden
ADVANCED fixture to Vercel, assert_embeddable, embed in the
operator-authorized test location, render_check PASS")
------------------------------------------------------------------------
  1. Classify the golden ADVANCED fixture — a SELF-CHECK that the fixture
     itself still scores VERCEL_EMBED. If the decision engine's thresholds
     ever drift such that this fixture stops being ADVANCED, the drift
     check would be testing nothing — fail loud instead of silently
     skipping the rest of the proof.
  2. Deploy it to Vercel and prove it is embeddable, via the individual
     ``ghl_vercel`` primitives in the SAME order ``run_pipeline`` uses
     (``prepare_app`` -> ``resolve_token`` -> ``deploy`` -> ``make_public``
     -> ``assert_embeddable``) — called directly rather than through
     ``run_pipeline`` itself so a non-embeddable result can still be
     captured into an honest receipt instead of only ever raising.
  3. GHL-embed leg (splice the iframe into an operator-authorized GHL test
     page, then ``render_check`` PASS): the actual GoHighLevel page
     write/verify is owned by ``ghl_builder``/``ghl_rest_canvas``/
     ``ghl_verify`` (other units' file lane), not re-implemented here —
     this is DEFERRED TO U22's ONE end-to-end operator-box live-proof run,
     the SAME doctrine every other cross-module live leg in this repo
     already follows (B-U10/U24's reconcile leg, B-U16's selector-drift
     probe). The receipt records this leg's status HONESTLY as
     ``"deferred_to_live_run"`` — never fabricated, never silence.
  4. Write a dated receipt to
     ``<evidence_root>/routing/routing-drift-check-<UTC-date>.json``.

GLUE BOUNDARY — same posture as ``ghl_method.py``'s ``decide_and_record``:
this module is PURE ORCHESTRATION over already-real, already-tested
``ghl_vercel``/``ghl_method`` primitives. Every network call goes through an
INJECTED ``requester``/``fetcher`` (a fake in tests, the real HTTP transport
in production) — the identical seam ``ghl_vercel`` itself already uses. No
new network code is written here.

This tool is called by the monthly maintenance-window schedule entry
(``schedule/skill6-routing-drift-check.cron.json``); registering that cron
live is the LIVE-PROOF leg, deferred to U22 exactly like
``scripts/install-github-archive-reconcile-cron.sh``.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Callable

import ghl_method
import ghl_vercel


# The golden ADVANCED fixture: deliberately carries one hard signal (a
# canvas + client fetch = interactive-app score 2) PLUS enough css-fighting
# signals to push it over ADVANCED_THRESHOLD without relying on an external
# framework (keeps the fixture dependency-free). Verified below by the
# self-check in step 1 of run_routing_drift_check, not assumed.
GOLDEN_ADVANCED_FIXTURE_HTML = (
    '<section class="routing-drift-check-fixture">'
    '<canvas id="drift-check-canvas"></canvas>'
    "<script>fetch('/api/routing-drift-check-ping');</script>"
    "<style>"
    ".hero{color:red!important} "
    "body{margin:0} "
    "@font-face{font-family:'DriftCheck';src:url(driftcheck.woff)}"
    "</style>"
    "</section>"
)


class RoutingDriftCheckError(RuntimeError):
    """Raised when the routing-drift check cannot complete, OR the golden
    fixture no longer self-classifies as VERCEL_EMBED (a decision-engine
    regression this check exists to catch), OR the Vercel deployment is not
    embeddable. FAIL LOUD — never silently skip or fabricate a PASS."""


@dataclass
class RoutingDriftCheckReceipt:
    """The outcome of one routing-drift-check run.

    ``ghl_embed_leg``: always ``{"status": "deferred_to_live_run", ...}`` in
    this offline/CODE-MERGE tier — the honest, non-fabricated status of the
    GHL-embed + render_check leg until U22's live-proof run exercises it
    for real.
    """
    marker: str
    classification_method: str
    classification_score: int
    vercel_url: str
    embeddable: bool
    ghl_embed_leg: dict
    receipt_path: str
    checked_at: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )


def run_routing_drift_check(
    evidence_root: str,
    project_dir: str,
    *,
    marker: str | None = None,
    project_name: str = "zhc-routing-drift-check",
    env: dict | None = None,
    requester: Callable | None = None,
    fetcher: Callable | None = None,
) -> RoutingDriftCheckReceipt:
    """Run the four-step routing-drift live proof and write a dated receipt.

    Args:
        evidence_root: The run-evidence root directory. The routing
            subdirectory is created if absent; the dated receipt lands at
            ``<evidence_root>/routing/routing-drift-check-<YYYYMMDD>.json``.
        project_dir: Absolute path for the prepared Vercel project directory
            (forwarded to ``ghl_vercel.prepare_app``).
        marker: Optional explicit marker string (default: a timestamped
            ``ZHC-ROUTING-DRIFT-CHECK-<UTC timestamp>`` marker).
        project_name: Vercel project name (default
            ``"zhc-routing-drift-check"``).
        env: Optional env dict override (Vercel token resolution).
        requester: Injected HTTP callable for ``ghl_vercel.deploy``/
            ``make_public`` (tests only — production omits this and the
            real transport is used).
        fetcher: Injected fetch callable for
            ``ghl_vercel.assert_embeddable`` (tests only).

    Returns:
        A ``RoutingDriftCheckReceipt``.

    Raises:
        ``ValueError``: if ``evidence_root``/``project_dir`` is empty.
        ``RoutingDriftCheckError``: on a decision-engine regression (the
            golden fixture no longer scores VERCEL_EMBED), a Vercel
            deploy/token failure, or a non-embeddable deployment. The
            receipt is still written (honest FAIL) before this is raised
            when the failure happens after deployment.
    """
    if not evidence_root or not str(evidence_root).strip():
        raise ValueError("evidence_root is required.")
    if not project_dir or not str(project_dir).strip():
        raise ValueError("project_dir is required.")

    marker = marker or (
        f"ZHC-ROUTING-DRIFT-CHECK-{time.strftime('%Y%m%d%H%M%S', time.gmtime())}"
    )

    # ── Step 1: self-check — the golden fixture must still classify VERCEL_EMBED
    #    via the SAME derive-signals-from-raw-HTML path U23/B-U9 gap (1)
    #    hardened (classify_page_from_html), not a hand-declared page_spec —
    #    this doubles as a live integration proof of that path.
    decision = ghl_method.classify_page_from_html(GOLDEN_ADVANCED_FIXTURE_HTML)
    if decision.method != ghl_method.PageMethod.VERCEL_EMBED:
        raise RoutingDriftCheckError(
            "DECISION-ENGINE REGRESSION: the golden ADVANCED fixture no "
            f"longer classifies VERCEL_EMBED (got {decision.method.value!r}, "
            f"score={decision.score}, signals={decision.signals}). The "
            "routing-drift check proves nothing until this is fixed — "
            "either the fixture or the engine's thresholds drifted."
        )

    # ── Step 2: deploy to Vercel (prepare -> token -> deploy -> make_public) ──
    #    Called as the individual ghl_vercel primitives (not run_pipeline)
    #    so a NON-EMBEDDABLE result can still be captured into an honest
    #    receipt before re-raising -- run_pipeline's own assert_embeddable
    #    call raises before ever returning, which would make an honest
    #    FAIL-with-receipt impossible if used as a single opaque call.
    try:
        project = ghl_vercel.prepare_app(GOLDEN_ADVANCED_FIXTURE_HTML, marker, project_dir)
        token = ghl_vercel.resolve_token(env)
        deployment = ghl_vercel.deploy(
            project, token, project_name=project_name, requester=requester
        )
        ghl_vercel.make_public(deployment.deployment_id, token, requester=requester)
    except (ghl_vercel.VercelEmbedError, ghl_vercel.VercelTokenError) as exc:
        raise RoutingDriftCheckError(f"Vercel deploy leg failed: {exc}") from exc

    # ── Step 2b: assert_embeddable — the hard gate. Capture a failure into
    #    an honest receipt (never silence) instead of letting it propagate
    #    with nothing written to disk.
    try:
        embeddability = ghl_vercel.assert_embeddable(deployment.url, marker, fetcher=fetcher)
        embeddable = embeddability.embeddable
        embeddability_reason = embeddability.reason
    except ghl_vercel.VercelEmbedError as exc:
        embeddable = False
        embeddability_reason = str(exc)

    # ── Step 3: GHL-embed + render_check — DEFERRED TO U22's live-proof run ──
    ghl_embed_leg = {
        "status": "deferred_to_live_run",
        "reason": (
            "splicing the iframe into an operator-authorized GHL test page "
            "and render_check PASS requires a live ghl_builder/ghl_verify "
            "run with real GoHighLevel credentials -- exercised in U22's "
            "ONE end-to-end operator-box run, the same doctrine as "
            "B-U10/B-U16's deferred live legs."
        ),
    }

    # ── Step 4: write the dated receipt — ALWAYS, embeddable or not ───────────
    routing_dir = os.path.join(str(evidence_root), "routing")
    os.makedirs(routing_dir, exist_ok=True)
    date_stamp = time.strftime("%Y%m%d", time.gmtime())
    receipt_path = os.path.join(
        routing_dir, f"routing-drift-check-{date_stamp}.json"
    )

    record = {
        "marker": marker,
        "classification_method": decision.method.value,
        "classification_score": decision.score,
        "vercel_url": deployment.url,
        "embeddable": embeddable,
        "embeddability_reason": embeddability_reason,
        "ghl_embed_leg": ghl_embed_leg,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

    if not embeddable:
        raise RoutingDriftCheckError(
            f"Vercel deployment {deployment.url} is NOT embeddable: "
            f"{embeddability_reason}. Receipt written to {receipt_path} "
            "(an honest FAIL, never silence)."
        )

    return RoutingDriftCheckReceipt(
        marker=marker,
        classification_method=decision.method.value,
        classification_score=decision.score,
        vercel_url=deployment.url,
        embeddable=embeddable,
        ghl_embed_leg=ghl_embed_leg,
        receipt_path=receipt_path,
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="U23/B-U9 monthly routing-drift live proof — deploy the "
                    "golden ADVANCED fixture to Vercel and prove it is "
                    "embeddable."
    )
    parser.add_argument(
        "--evidence-root", required=True,
        help="Run-evidence root directory (receipt lands under routing/).",
    )
    parser.add_argument(
        "--project-dir", required=True,
        help="Directory to prepare the Vercel deployment project in.",
    )
    args = parser.parse_args(argv)

    try:
        receipt = run_routing_drift_check(args.evidence_root, args.project_dir)
    except (ValueError, RoutingDriftCheckError) as exc:
        print(f"FAIL: {exc}")
        return 1

    print(f"OK: routing-drift-check receipt written to {receipt.receipt_path}")
    print(f"    method={receipt.classification_method} "
          f"embeddable={receipt.embeddable} url={receipt.vercel_url}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
