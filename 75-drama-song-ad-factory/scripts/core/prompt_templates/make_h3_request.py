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


def _ultra_model(quality_mode_path="storyboard/quality-mode.json"):
    """The Ultra model id from the run's quality-mode record, or None."""
    try:
        doc = _load(quality_mode_path)
    except (OSError, ValueError):
        return None
    ultra = doc.get("ultra") if isinstance(doc, dict) else None
    if isinstance(ultra, dict):
        return ultra.get("model")
    return ultra


def build(spec, characters, first_frame_url, shot_id=None, duration=None,
          resolution=None, card_receipt=None, plan=None, review=None,
          last_frame_url=None, reference_image_urls=None):
    """(request, None) or (None, refusal dict)."""
    model = spec.get("model") or MODEL
    if model not in ALLOWED_MODELS:
        return None, {"reason_code": "MODEL_NOT_H3",
                      "detail": "%r is not a canonical MiniMax H3 id; this "
                                "builder never substitutes another model" % (model,)}
    # F-PM-4 / F-QM-2: the end picture (last_frame_url) and the nine-picture
    # references are accepted and emitted, but never mixed with frames in one
    # request. There is no first frame without a supplied url, and no
    # reference-to-video request without its references. U07's dispatch-plan
    # rule (allow pair, approve binding, refuse LAST_FRAME_WITHOUT_FIRST)
    # stays the gate; this is the builder half only.
    refs = [u for u in (reference_image_urls or []) if u]
    if reference_image_urls is not None and not isinstance(reference_image_urls, list):
        return None, {"reason_code": "REFERENCE_IMAGE_URLS_NOT_A_LIST",
                      "detail": "reference_image_urls must be a list of https urls"}
    frames = [u for u in (first_frame_url, last_frame_url) if u]
    if refs and frames:
        return None, {"reason_code": "REFERENCE_MIXED_WITH_FRAMES",
                      "detail": "reference images are never mixed with start or "
                                "end frame in one H3 request; use one or the other"}
    if model == "minimax-h3/reference-to-video":
        if not refs:
            return None, {"reason_code": "REFERENCE_IMAGE_URLS_REQUIRED",
                          "detail": "reference-to-video needs its reference_image_urls"}
    elif not str(first_frame_url or "").startswith("https://"):
        return None, {"reason_code": "FIRST_FRAME_URL_REQUIRED",
                      "detail": "H3 image-to-video needs an https first_frame_url"}
    for u in refs + frames:
        if not str(u).startswith("https://"):
            return None, {"reason_code": "FRAME_URL_REQUIRED",
                          "detail": "%r is not an https url" % (u,)}
    # F-QM-3: H3 never goes above 2K. 4K passes only on the Ultra model the
    # run's quality-mode record names; any other 4K request is refused.
    res = resolution or spec.get("resolution") or "768P"
    if res not in ("768P", "2K"):
        if res != "4K" or model != _ultra_model(spec.get("quality_mode_path")
                                                or "storyboard/quality-mode.json"):
            return None, {"reason_code": "H3_ABOVE_2K",
                          "detail": "MiniMax H3 takes 768P or 2K only; 4K is the "
                                    "Ultra model's, and %r is not it" % (model,)}
    prompt, sections = PT.assemble_h3(spec, characters)
    # N-34 / N-35: the look's locked block and banned-word list ride with the
    # build. The lock travels in spec["style_lock"]; the block is re-derived
    # from the spec's own look/mode so the banned scan strips exactly what the
    # assembler placed (mode and look files are loaded again here, never copied
    # by hand).
    locked = (spec.get("style_lock") or {}).get("h3_block") or ""
    if not locked:
        locked = PT.locked_look_block(spec)
    verdict = PT.check(prompt, sections, model=model,
                       mode_id=spec.get("mode"),
                       locked_block=locked)
    try:
        prompt, verdict = PT.expand(spec, characters, prompt, verdict)
    except PT.PromptTemplateError as exc:
        return None, {"reason_code": getattr(exc, "code", "H3_THIN_SPEC"),
                      "detail": str(exc)}
    state = (verdict or {}).get("verdict") or (verdict or {}).get("status")
    if isinstance(state, str) and state.upper() in ("REFUSE", "TRIM"):
        return None, {"reason_code": "H3_PROMPT_%s" % state.upper(),
                      "detail": verdict}
    rec = PT.receipt(spec, prompt, sections, verdict)
    inp = {"prompt": prompt,
           "duration": int(duration or spec.get("duration_s") or 6),
           "resolution": res}
    if first_frame_url:
        inp["first_frame_url"] = first_frame_url
    if last_frame_url:
        inp["last_frame_url"] = last_frame_url
    if refs:
        inp["reference_image_urls"] = refs
    req = {"model": model,
           "input": inp,
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
    ap.add_argument("--first-frame-url", default=None,
                    help="required for image-to-video/text-to-video; omit for "
                         "reference-to-video, which uses --reference-image-url")
    ap.add_argument("--out", required=True)
    ap.add_argument("--shot-id", default=None)
    ap.add_argument("--duration", type=int, default=None)
    ap.add_argument("--resolution", default=None, choices=("768P", "2K", "4K"))
    ap.add_argument("--last-frame-url", default=None)
    ap.add_argument("--reference-image-url", action="append", dest="reference_image_urls",
                    default=None,
                    help="one of the nine-picture references; repeat for each")
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
                             a.duration, a.resolution, card, plan, review,
                             last_frame_url=a.last_frame_url,
                             reference_image_urls=a.reference_image_urls)
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
