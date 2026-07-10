#!/usr/bin/env python3
"""Build the mini-app questions_payload from the CANONICAL intake JSONs.

SINGLE SOURCE OF TRUTH: the mini-app never hardcodes a question. It renders the
exact prompt/help/kind/allowed_values/value_labels from:

  standard  -> 23-ai-workforce-blueprint/templates/role-library/presentations/
               intake/deck-intake-questions.json
  signature -> 51-signature-presentation/intake/sp-8-questions.json
               (q1..q8 + the frame-selection question)

The box calls this to produce the payload it POSTs to the Worker's /api/sessions.
Edit the JSONs, not this script, to change what a client is asked.

Usage:
  build_questions_payload.py --set standard  --run-id RUN123 [--out payload.json]
  build_questions_payload.py --set signature --run-id RUN123
  build_questions_payload.py --selftest
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# Fields carried straight through from the JSON question objects to the UI.
_PASSTHROUGH = ("id", "order", "prompt", "help", "kind", "required",
                "allowed_values", "value_labels", "default")


def _project_root(start: pathlib.Path) -> pathlib.Path:
    """Walk up until we find the repo markers, else return start."""
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "23-ai-workforce-blueprint").is_dir() and (parent / "51-signature-presentation").is_dir():
            return parent
    return start


def default_standard_path(root: pathlib.Path) -> pathlib.Path:
    return (root / "23-ai-workforce-blueprint" / "templates" / "role-library"
            / "presentations" / "intake" / "deck-intake-questions.json")


def default_signature_path(root: pathlib.Path) -> pathlib.Path:
    return root / "51-signature-presentation" / "intake" / "sp-8-questions.json"


def _project_question(q: dict) -> dict:
    """Keep only UI-relevant fields; drop resolverHint/storeOn/section internals."""
    out = {}
    for k in _PASSTHROUGH:
        if k in q and q[k] is not None:
            out[k] = q[k]
    out.setdefault("kind", "text")
    out.setdefault("required", True)
    return out


def build_standard_payload(spec: dict) -> list[dict]:
    qs = sorted(spec.get("questions", []), key=lambda q: q.get("order", 0))
    return [_project_question(q) for q in qs]


def build_signature_payload(spec: dict) -> list[dict]:
    qs = sorted(spec.get("questions", []), key=lambda q: q.get("order", 0))
    out = [_project_question(q) for q in qs]
    frame = spec.get("frame_selection_question")
    if frame:
        out.append(_project_question(frame))
    return out


def build_payload(run_id: str, question_set: str, standard_spec: dict,
                  signature_spec: dict | None) -> dict:
    if question_set == "standard":
        questions = build_standard_payload(standard_spec)
    elif question_set == "signature":
        if signature_spec is None:
            raise ValueError("signature set requested but sp-8-questions.json not loaded")
        questions = build_signature_payload(signature_spec)
    else:
        raise ValueError(f"unknown question_set '{question_set}'")
    if not questions:
        raise ValueError("no questions produced — check the source JSON")
    return {
        "run_id": run_id,
        "question_set": question_set,
        "source": "deck-intake-questions.json" if question_set == "standard" else "sp-8-questions.json",
        "questions": questions,
    }


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def selftest() -> int:
    root = _project_root(pathlib.Path(__file__).parent)
    sp = default_standard_path(root)
    sig = default_signature_path(root)
    ok = True
    if sp.is_file():
        std = build_payload("RUNTEST", "standard", _load(sp), None)
        n = len(std["questions"])
        assert n >= 8, f"standard payload too small: {n}"
        assert std["questions"][0]["id"] == "presentation_type", "first standard question must be the type-picker (presentation_type)"
        assert all("prompt" in q and q["prompt"] for q in std["questions"]), "every question needs a prompt"
        print(f"[selftest] standard OK: {n} questions")
    else:
        print(f"[selftest] SKIP standard (not found: {sp})", file=sys.stderr)
    if sig.is_file():
        sigp = build_payload("RUNTEST", "signature", _load(sp) if sp.is_file() else {"questions": []}, _load(sig))
        ids = [q["id"] for q in sigp["questions"]]
        for q in ("q1", "q8", "frame_selection"):
            assert q in ids, f"signature payload missing {q}: {ids}"
        assert len(ids) == 9, f"signature payload should have 9 questions, got {len(ids)}"
        print(f"[selftest] signature OK: {ids}")
    else:
        print(f"[selftest] SKIP signature (not found: {sig})", file=sys.stderr)
    print("[selftest] PASS" if ok else "[selftest] FAIL")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Build the mini-app questions_payload from the canonical intake JSONs.")
    ap.add_argument("--set", dest="qset", choices=["standard", "signature"], default="standard")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--questions-file", default=None, help="override path to deck-intake-questions.json")
    ap.add_argument("--sp-file", default=None, help="override path to sp-8-questions.json")
    ap.add_argument("--out", default=None, help="write payload here (default stdout)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if not args.run_id:
        print("error: --run-id is required", file=sys.stderr)
        return 2

    root = _project_root(pathlib.Path(__file__).parent)
    std_path = pathlib.Path(args.questions_file) if args.questions_file else default_standard_path(root)
    sig_path = pathlib.Path(args.sp_file) if args.sp_file else default_signature_path(root)

    if not std_path.is_file():
        print(f"error: cannot find deck-intake-questions.json at {std_path}", file=sys.stderr)
        return 3
    standard_spec = _load(std_path)
    signature_spec = _load(sig_path) if (args.qset == "signature" and sig_path.is_file()) else None
    if args.qset == "signature" and signature_spec is None:
        print(f"error: cannot find sp-8-questions.json at {sig_path}", file=sys.stderr)
        return 3

    payload = build_payload(args.run_id, args.qset, standard_spec, signature_spec)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out} ({len(payload['questions'])} questions)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
