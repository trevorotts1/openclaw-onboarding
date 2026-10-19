#!/usr/bin/env python3
"""Skill 71 wireframe build spec: which style reference a wireframe request
sends, and the annotated build-spec prompt block it carries.

Owner reading (Trevor, 2026-10-19): the Drive wireframes the owner likes are
files 1, 3 and 4 (the `chatgpt-wireframe-1`, `-3`, `-4` sheets in
assets/visual-standards/wireframes/). The greyscale Set for Life sheet is not
a style target; only its annotation conventions survive, as written rules in
references/wireframe-build-spec.json.

What this module owns (everything is data in that JSON file):
  - reference_urls(stage, request): the one style reference a desktop or
    mobile wireframe job attaches, chosen by stage and by the request's form
    (standard or long-form). It refuses by name a request that still lists the
    greyscale sheet.
  - prompt_block(...): the annotated build-spec block (section chip and name
    tab, inline type specs, labelled image plates, filled CTA, contiguous
    bands, widths header strip, behaviour note, pair rules, founder-letter
    rule, example flaws not to copy). It names no hex colour: the client's
    colours come from the BRAND COLORS line (scripts/brand_colors.py).
  - refuse_colourless_prose(text): a request template that asks for "warm grey
    line work ... no colour fill" contradicts the SOP and is refused.

It never calls a provider and never reads a secret. scripts/stage_executor.py
is the only caller.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = SKILL_ROOT / "references" / "wireframe-build-spec.json"
STANDARDS = SKILL_ROOT / "assets" / "visual-standards"
WIREFRAME_STAGES = ("desktop-wireframe", "mobile-tablet")
FORMS = ("standard", "long-form")
FORM_LABEL = {"standard": "Standard", "long-form": "Long-Form"}


class SpecError(Exception):
    """A named refusal; stage_executor.py re-raises it as ExecutorError."""


_SPEC = None


def spec() -> dict:
    global _SPEC
    if _SPEC is None:
        try:
            _SPEC = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SpecError(f"cannot read {SPEC_FILE.name}: {exc}")
    return _SPEC


def canon(value) -> str:
    """Canonical section tag: "S02A", "02A", "2a" -> "2A"; anything else as given."""
    text = re.sub(r"^S(?=\d)", "", str(value).strip().upper())
    match = re.fullmatch(r"0*(\d+)([A-Z]?)", text)
    return f"{int(match.group(1))}{match.group(2)}" if match else str(value).strip()


def section_tag(section: dict, index: int) -> str:
    tag = canon(section.get("section_id", ""))
    return tag if re.fullmatch(r"\d+[A-Z]?", tag) else str(index)


_NOTED = set()


def form_of(request: dict, strict: bool = False) -> str:
    """The selected form: request copy_version, metadata.copy_version, the
    section check the executor recorded, else inferred from the section ids
    (a lettered id means long-form, exactly 12 plain ids means standard).
    Undeterminable: a paid run (strict) is refused; a free run uses standard
    and says so once on stderr."""
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    check = request.get("_section_check")
    declared = [request.get("copy_version"), metadata.get("copy_version"),
                check[0] if isinstance(check, (tuple, list)) and check else None]
    for value in declared:
        norm = re.sub(r"[^a-z]", "", str(value or "").lower())
        if norm in ("standard", "standardv6"):
            return "standard"
        if norm in ("longform", "longformv6"):
            return "long-form"
    tags = [canon((s or {}).get("section_id", "")) for s in request.get("sections") or []]
    if any(re.fullmatch(r"\d+[A-Z]", t) for t in tags):
        return "long-form"
    if len(tags) == 12 and all(re.fullmatch(r"\d+", t) for t in tags):
        return "standard"
    if strict:
        raise SpecError(
            "the wireframe form is not known: declare copy_version (standard or long-form) "
            "in the production request, so the right style reference and form rules are used "
            "(a paid run never guesses the form)")
    if "form" not in _NOTED:
        _NOTED.add("form")
        print("NOTE wireframe_form: copy_version is not declared; the free run used the "
              "standard form (a paid run refuses)", file=sys.stderr)
    return "standard"


def style_reference(stage: str, form: str) -> dict:
    try:
        entry = spec()["style_references"][form][stage]
    except KeyError:
        raise SpecError(f"no wireframe style reference for stage {stage!r}, form {form!r}")
    rel = entry["file"]
    path = STANDARDS / rel
    if not path.is_file():
        raise SpecError(f"the bundled wireframe style reference {rel} is missing")
    return {"name": Path(rel).stem, "path": path, "label": entry["label"],
            "url": spec()["reference_base_url"] + rel, "form": form,
            "extra_rule": entry.get("extra_rule", "")}


def _is_greyscale_sheet(ref: str) -> bool:
    never = spec()["never_style_references"]
    low = Path(str(ref).split("?")[0]).name.lower()
    if any(token in low for token in never["match"]):
        return True
    path = Path(str(ref))
    if path.is_file():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return digest in never["sha256"]
    return False


def reference_urls(stage: str, request: dict, strict: bool = False) -> list:
    """The style reference a wireframe job attaches, first in attach order.
    Refuses by name a request-level reference that is the greyscale sheet."""
    if stage not in WIREFRAME_STAGES:
        return []
    for ref in request.get("references") or []:
        if _is_greyscale_sheet(ref):
            raise SpecError(
                f"{stage}: the request lists the greyscale Set for Life wireframe as a "
                f"reference ({Path(str(ref)).name}); it is no longer a wireframe style "
                "reference. Remove it: the stage attaches "
                f"{style_reference(stage, form_of(request, strict))['name']} itself "
                "(references/wireframe-build-spec.json)")
    return [style_reference(stage, form_of(request, strict))["url"]]


_NEGATED = re.compile(r"\b(never|not|no|don'?t|do not|avoid|without|isn'?t|is not)\b", re.I)
_PLATE_SUBJECT = re.compile(
    r"^\W*(?:image\s+|photo\s+)?(plates?|placeholders?|photos?|photography|images?|portraits?)\b", re.I)


def refuse_colourless_prose(stage: str, text: str) -> None:
    """Refuse prose that asks for a colourless sheet. Tested sentence by
    sentence: a phrase negated earlier in its sentence ("never grey line work")
    or in a sentence whose subject is the image plates ("plates are neutral grey
    with no colour fill") restates the build spec and passes. A plate word later
    in a sentence about the layout does not exempt it: the run-002 template
    "Draw the layout only: ... type placeholders and image boxes in warm grey
    line work on ivory, no photography, no colour fill." is refused."""
    for sentence in re.split(r"(?<=[.!?;])\s+|\n", text):
        if _PLATE_SUBJECT.search(sentence):
            continue
        for pattern in spec()["colourless_prose"]:
            match = re.search(pattern, sentence, re.I)
            if match and not _NEGATED.search(sentence[:match.start()]):
                raise SpecError(
                    f"{stage}: the request's prompt asks for a colourless sheet "
                    f"({match.group(0)!r}). A wireframe is an annotated build spec in the "
                    "client's brand colors (SOP Stage 4A); remove that instruction")


def short_direction(text: str, words: int = 8) -> str:
    """The plate label's art direction: the first clause, at most `words` words."""
    clause = re.split(r"\s[-–—]\s|[;,.]", str(text or ""), maxsplit=1)[0]
    return " ".join(clause.split()[:words]).strip(" -")


def _plates(section: dict) -> str:
    labels = []
    allowed = spec()["ratio_labels"]
    for slot in section.get("slots") or []:
        ratio = str(slot.get("aspect_ratio") or "").strip()
        if ratio and ratio != "auto" and ratio not in allowed:
            raise SpecError(
                f"section {section.get('section_id')}: slot {slot.get('slot_id', '?')} has "
                f"aspect_ratio {ratio!r}, which is not a valid ratio label "
                f"({', '.join(allowed)})")
        shown = ratio if ratio and ratio != "auto" else "the nearest listed ratio to the plate as drawn"
        direction = short_direction(slot.get("art_direction")) or "image to be generated"
        labels.append(f"one plate labelled \"IMAGE {shown} - {direction}\"")
    return "; ".join(labels)


def _type_specs(stage: str, section: dict) -> str:
    given = section.get("type_specs")
    if isinstance(given, dict) and given:
        return "; ".join(f"{str(k).upper()} / {v}" for k, v in given.items())
    return "; ".join(f"{k.upper()} / {v}" for k, v in spec()["type_scale_default"][stage].items())


def _note(stage: str, section: dict, cta: str) -> str:
    notes = section.get("behavior_notes")
    if isinstance(notes, str) and notes.strip():
        return notes.strip()
    if isinstance(notes, list) and any(isinstance(n, str) and n.strip() for n in notes):
        return next(n.strip() for n in notes if isinstance(n, str) and n.strip())
    if not cta:
        return "No CTA"
    return "CTA full width below the copy" if stage == "mobile-tablet" else "CTA below the copy"


def _cta(section: dict) -> str:
    value = section.get("cta") or section.get("_copy_source_cta")
    if isinstance(value, dict):
        value = value.get("label")
    return str(value or "").strip().rstrip(".")


def prompt_block(stage: str, section: dict, index: int, total: int, width: int,
                 request: dict) -> str:
    """The build-spec block for one wireframe slice, composed from the JSON."""
    if stage not in WIREFRAME_STAGES:
        return ""
    s = spec()
    blocks = s["blocks"]
    form = form_of(request)
    ref = style_reference(stage, form)
    tag = section_tag(section, index)
    name = str(section.get("section_name") or section.get("section_id") or tag)
    cta = _cta(section)
    mobile = stage == "mobile-tablet"
    scale = s["type_scale_default"][stage]
    strip = s["header_strip"][stage]
    long_form = form == "long-form"
    lines = [line.format(form_label=FORM_LABEL[form], platform="mobile" if mobile else "desktop",
                         width=width, tag=tag, name=name, position=index, total=total)
             for line in blocks["intro"]]
    lines += [blocks["style_reference"], blocks["colour"], blocks["grammar_head"]]
    lines.append(blocks["chip"].format(tag=tag, name_caps=name.upper()))
    lines.append(blocks["type_specs"].format(type_specs=_type_specs(stage, section)))
    plates = _plates(section)
    lines.append(blocks["plates_some"].format(plates=plates, ratio_list=", ".join(s["ratio_labels"]))
                 if plates else blocks["plates_none"])
    if cta:
        shape = blocks["cta_shape_mobile" if mobile else "cta_shape_desktop"]
        solution = long_form and re.fullmatch(r"\d+[A-Z]", tag) is not None
        lines.append(blocks["cta_some"].format(
            cta_shape=shape, cta=cta, microcopy_size=scale["CTA microcopy"].upper(),
            cta_strip=blocks["cta_strip_long_form"] if solution and not mobile else ""))
    else:
        lines.append(blocks["cta_none"])
    lines.append(blocks["bands"])
    lines.append(blocks["strip_first"].format(page=strip["page_px"], content=strip["content_px"])
                 if index == 1 else blocks["strip_other"])
    lines.append(blocks["behaviour"].format(note=_note(stage, section, cta)))
    if mobile:
        lines.append(blocks["mobile"].format(width=width))
        if ref["extra_rule"] and form == "standard":
            lines.append(ref["extra_rule"])
    else:
        lines.append(blocks["long_form_desktop" if long_form else "standard_desktop"])
    if long_form and tag in ("2", "3", "4"):
        lines.append(blocks["pain"])
    elif long_form and re.fullmatch(r"[234]A", tag):
        lines.append(blocks["solution"])
    label = f"{name} {section.get('section_id', '')}".lower()
    if tag == "11" or "step" in label:
        lines.append(blocks["steps"])
    if tag == "12" or "founder" in label or "letter" in label:
        lines.append(blocks["letter"].format(portrait_position="above it" if mobile else "beside it"))
    lines.append(blocks["do_not_copy"])
    return "\n".join(lines)


def describe_refs(refs) -> str:
    """One quotable line per reference, for --preflight."""
    out = []
    for n, ref in enumerate(refs, start=1):
        text = str(ref)
        out.append(f"{n}={text if text.startswith('http') else Path(text).name}")
    return " ".join(out)


if __name__ == "__main__":
    raise SystemExit("wireframe_spec.py is a library; run scripts/stage_executor.py --preflight")
