#!/usr/bin/env python3
"""Build the mini-app questions_payload from the CANONICAL intake JSONs.

SINGLE SOURCE OF TRUTH: the app never hardcodes a question. It renders the
exact prompt/help/kind/allowed_values/value_labels from:

  standard  -> 23-ai-workforce-blueprint/templates/role-library/presentations/
               intake/deck-intake-questions.json
               + intake/upsell-questions.json (the sales/checkout + VSL yes-no)

The curated 7-9 core question set for the app is selected by `--questions`
(comma-separated ids) or defaults to the id list in this script. Edit the JSONs,
not this script, to change what a client is asked. The app's questions.json is
generated from this so the shipped UI is a snapshot of the canonical source.

Usage:
  build_questions_payload.py --run-id RUN123 [--out payload.json]
  build_questions_payload.py --selftest
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# Fields carried straight through from the JSON question objects to the UI.
_PASSTHROUGH = ("id", "order", "prompt", "help", "kind", "required",
                "allowed_values", "value_labels", "default",
                "conditional_on", "ask_if", "block_gate", "storeOn", "key")

# The curated core set the Presentation Interview app asks (13 <= cap 20).
# Every id must exist in deck-intake-questions.json, upsell-questions.json, or
# APP_ONLY_QUESTIONS below.
DEFAULT_CURATED = [
    "presentation_type",          # type-picker (order 0) -- MUST be first, see selftest guard
    "offer_name",                 # company/offer
    "transformation_promise",     # transformation promise
    "audience",                   # audience
    "cta_action",                 # CTA
    "brand_primary",              # logo check
    "image_links",                # image-link capture (app-only)
    "tone",                       # tone
    "final_price",                # price
    "speech_speed_preference",    # speech speed (order 7.5)
    "want_sales_checkout",        # new sales/checkout yes-no (order 7.6)
    "want_vsl_page",              # new VSL yes-no (order 7.7)
    "client_notes",               # extras
]

# Questions the APP asks that have no canonical deck-intake counterpart (they are
# capture UX, not driver fields). brand_primary (logo check) exists canonically;
# image_links is the app's image-link capture and stores under deck_brief.IMAGE_LINKS.
APP_ONLY_QUESTIONS = {
    "image_links": {
        "id": "image_links",
        "section": "deck-intake",
        "order": 6,
        "prompt": "Paste any image links you want used in the deck. (Optional — add up to 5.)",
        "help": "Product photos, headshots, brand imagery. We source images through the approved image pipeline; links here are used as grounded references.",
        "kind": "image_links",
        "storeOn": "deck_brief.IMAGE_LINKS",
        "required": False,
        "block_gate": False,
        "default": [],
    },
}


def _project_question(q: dict) -> dict:
    out = {}
    for k in _PASSTHROUGH:
        if k in q and q[k] is not None:
            out[k] = q[k]
    out.setdefault("kind", "text")
    out.setdefault("required", True)
    return out


def load_specs(root: pathlib.Path) -> tuple[dict, dict, dict | None]:
    """Load the canonical deck-intake + upsell question specs from the repo.

    Returns (merged_spec, empty_spec, store_target). The storeTarget table maps
    short field keys (e.g. "OFFER_NAME") to their qualified intake.json sections
    (e.g. "deck_brief.OFFER_NAME").

    Fallback: when the repo tree is not reachable (e.g. running from the
    standalone app checkout), the app's own questions.json snapshot is used —
    it is generated FROM these canonical files, so it is a valid source.
    """
    intake_dir = (root / "23-ai-workforce-blueprint" / "templates" / "role-library"
                  / "presentations" / "intake")
    standard = intake_dir / "deck-intake-questions.json"
    upsell = intake_dir / "upsell-questions.json"
    merged: dict = {"questions": []}
    store_target: dict | None = None
    if standard.is_file():
        spec = json.loads(standard.read_text(encoding="utf-8"))
        merged["questions"] = spec.get("questions", [])
        store_target = spec.get("storeTarget")
    if upsell.is_file():
        merged["questions"] += json.loads(upsell.read_text(encoding="utf-8")).get("questions", [])
    else:
        # Fallback snapshot (app checkout): pages/questions.json is the curated
        # projection of the canonical files. When root is the payload/ dir (the
        # standalone app layout), the snapshot sits one level up at app/pages.
        for cand in (root / "pages" / "questions.json",
                     root.parent / "pages" / "questions.json",
                     root.parent / "questions.json"):
            if not merged["questions"] and cand.is_file():
                merged["questions"] = json.loads(cand.read_text(encoding="utf-8")).get("questions", [])
                break
    # App-only capture questions (image-link capture) — merged into the pool so
    # the curated set can reference them even when not present in a JSON file.
    merged["questions"] += list(APP_ONLY_QUESTIONS.values())
    return merged, {"questions": merged["questions"]}, store_target


def build_curated_payload(run_id: str, specs: dict, curated_ids: list[str],
                          store_target: dict | None = None) -> dict:
    by_id = {q.get("id"): q for q in specs.get("questions", [])}
    missing = [i for i in curated_ids if i not in by_id]
    if missing:
        raise ValueError(f"curated ids not found in canonical JSONs: {missing}")
    # Order follows the CURATED list (the app's flow), not raw JSON order — the
    # app asks company/offer → promise → audience → CTA → logo → images → tone →
    # price → speech → sales/checkout → VSL → extras.
    questions = []
    for i in curated_ids:
        q = _project_question(by_id[i])
        # Qualify storeOn via the canonical storeTarget table
        # (e.g. "OFFER_NAME" -> "deck_brief.OFFER_NAME") so the frontend can
        # route each answer into the right intake.json section.
        so = q.get("storeOn")
        if so and store_target and so in store_target:
            q["storeOn"] = store_target[so]
        questions.append(q)
    return {
        "run_id": run_id,
        "question_set": "standard",
        "source": "deck-intake-questions.json + upsell-questions.json (curated)",
        "questions": questions,
    }


def selftest() -> int:
    root = _project_root(pathlib.Path(__file__).parent)
    ok = True
    specs, _, store_target = load_specs(root)
    if specs.get("questions"):
        payload = build_curated_payload("RUNTEST", specs, DEFAULT_CURATED, store_target)
        ids = [q["id"] for q in payload["questions"]]
        assert len(ids) <= 20, "curated set must respect cap 20"
        assert len(ids) >= 7, "curated set must keep 7-9 core"
        assert ids[0] == "presentation_type", "first standard question must be the type-picker (presentation_type)"
        assert "speech_speed_preference" in ids, "speech-speed question must be included"
        assert "want_sales_checkout" in ids, "sales/checkout yes-no must be included"
        assert "want_vsl_page" in ids, "VSL yes-no must be included"
        assert all("prompt" in q and q["prompt"] for q in payload["questions"]), "every question needs a prompt"
        offer = next(q for q in payload["questions"] if q["id"] == "offer_name")
        assert offer.get("storeOn") == "deck_brief.OFFER_NAME", f"offer storeOn not qualified: {offer.get('storeOn')}"
        print(f"[selftest] curated OK: {len(ids)} questions ({ids})")
    else:
        print("[selftest] SKIP curated (canonical JSONs not found)", file=sys.stderr)
    print("[selftest] PASS" if ok else "[selftest] FAIL")
    return 0 if ok else 1


def _project_root(start: pathlib.Path) -> pathlib.Path:
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "23-ai-workforce-blueprint").is_dir():
            return parent
    return start


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--questions", default=",".join(DEFAULT_CURATED), help="comma-separated curated ids")
    ap.add_argument("--out", default=None, help="write payload here (default stdout)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if not args.run_id:
        print("error: --run-id is required", file=sys.stderr)
        return 2
    root = _project_root(pathlib.Path(__file__).parent)
    specs, _, store_target = load_specs(root)
    curated = [x.strip() for x in args.questions.split(",") if x.strip()]
    payload = build_curated_payload(args.run_id, specs, curated, store_target)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out} ({len(payload['questions'])} questions)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
