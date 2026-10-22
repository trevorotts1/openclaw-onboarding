#!/usr/bin/env python3
"""make_h3_request.py — build a paid-ready MiniMax H3 video request.

WHY THIS EXISTS
    kie_dispatch refuses an H3 prompt that was not assembled through
    `prompt_templates.assemble_h3` and is not backed by a matching
    `prompt_templates.receipt()` (PROMPT_NOT_TEMPLATED). Nothing in the run
    path called the assembler, so every H3 shot had to be hand-built and the
    only way it could dispatch was by substituting another model. That is the
    defect this CLI closes: it is the one supported way to produce an H3
    request, and it never invents, pads or truncates a prompt.

WHAT IT DOES
    Reads a shot spec (the fixture shape under
    references/prompt-templates/fixtures/h3-specs/) plus a character record,
    assembles the prompt, measures it with the module's own band check,
    writes the receipt, and emits the exact request object kie_dispatch takes:

        {"model": "minimax-h3/image-to-video",
         "input": {"prompt", "duration", "resolution", "first_frame_url"},
         "prompt_receipt": {...}, "request_kind": "video", "shot_id": ...}

    The model id is fixed. H3 means H3: this file never maps the family onto
    another vendor id, and `--model` only accepts the three canonical ids.

CLI
    python3 make_h3_request.py --spec <spec.json> --characters <chars.json>
        --first-frame-url <https url> --out <request.json>
        [--shot-id <id>] [--duration <s>] [--resolution 768P|2K]
        [--card-receipt <path>] [--storyboard-plan <path>] [--storyboard-review <path>]

    Exit 0 ok; 2 refused (band REFUSE, bad vocab, bad url); 1 error.
    Stdlib only. No network, no spend.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import prompt_templates as PT  # noqa: E402

MODEL = "minimax-h3/image-to-video"
ALLOWED_MODELS = ("minimax-h3/image-to-video", "minimax-h3/text-to-video",
                  "minimax-h3/reference-to-video")


def _load(path):
    with open(os.path.expanduser(path), encoding="utf-8") as fh:
        return json.load(fh)


def build(spec, characters, first_frame_url, shot_id=None, duration=None,
          resolution=None, card_receipt=None, plan=None, review=None):
    """(request, None) or (None, refusal dict)."""
    model = spec.get("model") or MODEL
    if model not in ALLOWED_MODELS:
        return None, {"reason_code": "MODEL_NOT_H3",
                      "detail": "%r is not a canonical MiniMax H3 id; this "
                                "builder never substitutes another model" % (model,)}
    if not str(first_frame_url or "").startswith("https://"):
        return None, {"reason_code": "FIRST_FRAME_URL_REQUIRED",
                      "detail": "H3 image-to-video needs an https first_frame_url"}
    prompt, sections = PT.assemble_h3(spec, characters)
    verdict = PT.check(prompt, sections, model=model)
    state = (verdict or {}).get("verdict") or (verdict or {}).get("status")
    if isinstance(state, str) and state.upper() in ("REFUSE", "TRIM"):
        return None, {"reason_code": "H3_PROMPT_%s" % state.upper(),
                      "detail": verdict}
    rec = PT.receipt(spec, prompt, sections, verdict)
    req = {"model": model,
           "input": {"prompt": prompt,
                     "duration": int(duration or spec.get("duration_s") or 6),
                     "resolution": resolution or spec.get("resolution") or "768P",
                     "first_frame_url": first_frame_url},
           "request_kind": "video",
           "shot_id": shot_id or spec.get("shot_id"),
           "prompt_receipt": rec}
    if isinstance(card_receipt, dict) and card_receipt:
        req["card_receipt"] = card_receipt
    if isinstance(plan, list) and plan:
        shots = [dict(s, status="storyboard_approved") for s in plan]
        req["storyboard"] = {"shots": shots, "review": review or {}}
    return req, None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build a template-receipted H3 request")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--characters", required=True)
    ap.add_argument("--first-frame-url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--shot-id", default=None)
    ap.add_argument("--duration", type=int, default=None)
    ap.add_argument("--resolution", default=None, choices=("768P", "2K"))
    ap.add_argument("--card-receipt", default=None)
    ap.add_argument("--storyboard-plan", default=None)
    ap.add_argument("--storyboard-review", default=None)
    a = ap.parse_args(argv)
    try:
        spec = _load(a.spec)
        chars = _load(a.characters)
        card = _load(a.card_receipt) if a.card_receipt else None
        plan_raw = _load(a.storyboard_plan) if a.storyboard_plan else None
        plan = plan_raw.get("shots") if isinstance(plan_raw, dict) else plan_raw
        review = _load(a.storyboard_review) if a.storyboard_review else None
        req, refusal = build(spec, chars, a.first_frame_url, a.shot_id,
                             a.duration, a.resolution, card, plan, review)
        if refusal is not None:
            json.dump({"outcome": "refused", **refusal}, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 2
        out = os.path.expanduser(a.out)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(req, fh, indent=2, sort_keys=True)
            fh.write("\n")
        json.dump({"outcome": "ok", "out": out,
                   "chars": len(req["input"]["prompt"]),
                   "prompt_sha256": req["prompt_receipt"]["prompt_sha256"],
                   "verdict": (req["prompt_receipt"].get("check") or {}).get("verdict")},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    except PT.PromptTemplateError as exc:
        json.dump({"outcome": "refused", "reason_code": getattr(exc, "code", "TEMPLATE"),
                   "detail": str(exc)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 2
    except Exception as exc:                             # noqa: BLE001
        json.dump({"outcome": "error", "detail": "%s: %s" % (type(exc).__name__, exc)},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
