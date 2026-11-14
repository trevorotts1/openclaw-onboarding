#!/usr/bin/env python3
"""
deliverable_paths.py — MASTER Part 8 FIX 4: THE single source of truth for the
canonical run-dir path of every deliverable key.

WHY THIS EXISTS (Fix 4 — "One canonical path per deliverable"):
Before this module the same deliverable was addressed at DIFFERENT run-dir
paths by DIFFERENT enforcement surfaces, which drifted independently:

  * audio was written by the speech/audio roles to
    working/delivery/PRESENTER-AUDIO.mp3 (phase_verifiers.py's pattern, the
    P9-DELIVER manifest phase's produces_artifact, runfacts.py and
    workingset.py) while the operator bundle gate demanded it at
    deliverables/PRESENTER-AUDIO.mp3 — so the gate reported present files as
    missing and blocks were misattributed.
  * the speech markdown was addressed at THREE paths
    (working/deliverables/, working/delivery/, working/presenter-speech/ —
    build_deck.py's fuzzy-locate candidate list), so a writer that used one
    and a checker that used another passed each other in the dark.
  * infographic_png: phase_verifiers.py's pre-curation pattern said
    working/delivery/infographic.png while the Fix 2 producer
    (scripts/build_infographic.py) writes working/deliverables/infographic.png
    and the manifest's P8.3-INFOGRAPHIC phase declares the deliverables/ path.

THIS FILE is now the ONE place a key maps to its canonical run-dir relative
path. Consumers import CANONICAL_PATHS (or call deliverable_path()) instead of
hand-writing the relative path:

  - presentation_job/deliverables.py (U05 whitelist canon)  [W02-B4]
  - scripts/delivery_gate.py (delivery boundary gate)       [W02-B4]
  - scripts/fix_bundle_complete.py                          [wired]
  - build_deck.py DELIVERABLES_REQUIRED                     [documented]
  - pitch_engines_check.chk_speech_hook_count               [documented]

``python3 presentation_job/deliverable_paths.py --audit`` proves the canon:
one path per key for all TEN bundle keys plus the TWO workbook PDFs,
cross-checked against the PIPELINE-MANIFEST phases' produces_artifact,
phase_verifiers.py's pre-curation patterns, presentation_job/deliverables.py's
DELIVERABLE_AUDIT_SPEC, and build_deck.py's DELIVERABLES_REQUIRED. Exit 0 on
agreement; exit 1 naming every disagreement (the QC.md FIX 4 control —
temporarily editing one manifest path must make the audit exit 1 naming it).

The two workbook PDFs are the DELIVERABLES_GATED_SEPARATELY artifacts
(P8.25-WORKBOOK): not part of the ten-key bundle canon, but each still has
exactly one canonical path. PRESENTER-AUDIO-WEBINAR.mp3 (the webinarized intro
audio, a P9-SPEECH-WEBINAR-INTRO intermediate) is recorded as an ALIAS entry —
it is not a client deliverable key but consumers ask for it by name.

Zero third-party deps (stdlib only) — this module must import cleanly on a
deployed client box with no extra packages installed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

__all__ = [
    "CANONICAL_PATHS",
    "ALIAS_PATHS",
    "WORKBOOK_PATHS",
    "deliverable_path",
    "audit_paths",
    "main",
]

# ---------------------------------------------------------------------------
# THE CANONICAL PATH MAP — key -> run-dir relative path. ONE entry per key.
#
# The canon is the path the PRODUCER writes, which is also the path its phase's
# verifier checks (phase_verifiers.py _DELIVERY_PATTERN_BY_KEY, aligned with the
# manifest's produces_artifact). Two directories are in use, by producer:
#   working/deliverables/  — every phase-produced artifact, including the
#                            -FINAL deck pair written by P8-ASSEMBLE.
#   working/delivery/      — the audio (P9-DELIVER) and the webinar video
#                            (P9.6-WEBINAR-VIDEO).
# Older spellings — the run-dir root, or working/delivery/ for the deck pair —
# live in ALIAS_PATHS: accepted for reads, never written by a producer. The
# audit below reports any manifest producer that still writes one.
#
# {deck_slug} templates are literal (curly braces) in the map; use
# deliverable_path(key, deck_slug=...) to expand.
# ---------------------------------------------------------------------------
CANONICAL_PATHS = {
    # P8-ASSEMBLE writes the -FINAL deck into working/deliverables/;
    # P8.1-PDF-EXPORT exports the PDF beside it.
    "deck_pptx":         "working/deliverables/{deck_slug}-FINAL.pptx",
    "deck_pdf":          "working/deliverables/{deck_slug}-FINAL.pdf",
    # P8.1-PDF-EXPORT / P8.2-GUIDE / P9-SPEECH / P9.1-SPEECH-PDF /
    # P8.4-FISH-TAG / P7-TELEPROMPTER all write into working/deliverables/.
    "guide_pdf":         "working/deliverables/PRESENTER-GUIDE.pdf",
    "speech_md":         "working/deliverables/PRESENTERS-SPEECH.md",
    "speech_pdf":        "working/deliverables/PRESENTERS-SPEECH.pdf",
    "speech_fish_md":    "working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md",
    "teleprompter_html": "working/deliverables/presenter-teleprompter.html",
    # P9-DELIVER's own produces_artifact (manifest) — the audio lands here.
    "audio_mp3":         "working/delivery/PRESENTER-AUDIO.mp3",
    # FIX 2 (MASTER Part 8): the producer build_infographic.py writes
    # working/deliverables/infographic.png (also the manifest phase's
    # produces_artifact). phase_verifiers.py's pre-curation glob additionally
    # accepts the legacy working/delivery/ copy — recorded as an ALIAS below,
    # never as the canon (two canons is the bug this module deletes).
    "infographic_png":   "working/deliverables/infographic.png",
    # P9.6-WEBINAR-VIDEO (Feature L2-G) — the rendered webinar video.
    "webinar_mp4":       "working/delivery/{deck_slug}-WEBINAR.mp4",
}

# The TWO workbook PDFs (P8.25-WORKBOOK — DELIVERABLES_GATED_SEPARATELY, not
# part of the ten-key bundle). One canonical path each; the fillable variant
# additionally has an ALIAS short name accepted by workbook_builder.py's
# uploader ("...-FILLABLE.pdf" is the shipped form; the bare "...-WORKBOOK.pdf"
# is the regular form — both canonical, listed under their own names).
WORKBOOK_PATHS = {
    "workbook_pdf":           "working/deliverables/{deck_slug}-WORKBOOK.pdf",
    "workbook_pdf_fillable":  "working/deliverables/{deck_slug}-WORKBOOK-FILLABLE.pdf",
}

# Legacy/secondary spellings that consumers may still encounter. ALIASES ARE
# NOT CANONICAL — they exist so an audit can name exactly which non-canonical
# sites were seen, and so a writer/read pair that both use a legacy path
# keeps working until it is migrated. Mapping is key -> list of run-dir
# relative paths (glob-capable) that are ACCEPTED but not authoritative.
ALIAS_PATHS = {
    "infographic_png": [
        "working/delivery/infographic.png",       # phase_verifiers legacy glob
        "working/renders/infographic.png",        # raw render per SOP 9.10 step 6
    ],
    "speech_md": [
        "working/delivery/PRESENTERS-SPEECH.md",          # delivery-staged copy
        "working/presenter-speech/PRESENTERS-SPEECH.md",  # role scratch dir
        "working/presenter-speech/speech.md",             # scratch name
    ],
    "audio_mp3": [
        "working/delivery/PRESENTER-AUDIO-WEBINAR.mp3",   # webinarized intro variant (separate artifact)
    ],
    # The -FINAL deck pair: the canon is the producer's working/deliverables/
    # path (P8-ASSEMBLE + P8.1-PDF-EXPORT). The staged working/delivery/ copy
    # and the bare run-dir-root names are older spellings of the same files —
    # accepted for reads, never written by a producer (the audit reports any
    # manifest producer that declares one of them).
    "deck_pptx": [
        "working/delivery/{deck_slug}-FINAL.pptx",   # staged delivery copy
        "{deck_slug}-FINAL.pptx",                    # run-dir root (pre-PD-062)
    ],
    "deck_pdf": [
        "working/delivery/{deck_slug}-FINAL.pdf",    # staged delivery copy
        "{deck_slug}-FINAL.pdf",                     # run-dir root spelling
    ],
}

def deliverable_path(key: str, deck_slug: str = "deck"):
    """Return the canonical run-dir relative Path for a deliverable key.

    Expands the {deck_slug} template when present. Unknown keys raise
    KeyError — a caller asking for a path that has no canon must fail loud:
    a silent guess is exactly the drift this module deletes.
    """
    try:
        rel = CANONICAL_PATHS[key]
    except KeyError:
        if key in WORKBOOK_PATHS:
            rel = WORKBOOK_PATHS[key]
        else:
            raise
    return Path(rel.replace("{deck_slug}", deck_slug))

# ---------------------------------------------------------------------------
# THE AUDIT — QC.md FIX 4 proof: one path per key for all ten keys plus the
# two workbook PDFs, cross-checked against
#   1. PIPELINE-MANIFEST.json (build_bundle_files + phases[].produces_artifact)
#   2. phase_verifiers.py's _DELIVERY_PATTERN_BY_KEY (the P9-DELIVER patterns)
#   3. presentation_job/deliverables.py's DELIVERABLE_AUDIT_SPEC
#      (filename_template + standardized_dest)
#   4. build_deck.py's DELIVERABLES_REQUIRED (filename)
# Exit 0 iff every key has exactly ONE canonical path and every surface
# agrees (modulo the documented legacy-alias set). Exit 1 naming each
# disagreement — this is the control the QC proof runs: edit one manifest
# path, the audit exits 1 naming it.
# ---------------------------------------------------------------------------

def _manifest_location():
    """Locate universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json by
    walking upward from this module (the repo layout pins it 4-5 levels up)."""
    cur = Path(__file__).resolve().parent
    for _ in range(8):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if (cur / "universal-sops").is_dir() and not (cur / "presentation_job").is_dir():
            cand2 = cur / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
            if cand2.is_file():
                return cand2
        cur = cur.parent
    return None

def _scripts_dir():
    """The presentations/scripts dir (this module's parent's parent)."""
    return Path(__file__).resolve().parent.parent

def _norm_glob(p: str) -> str:
    """Normalize a glob/pattern to a comparable form: strip surrounding
    whitespace; keep {deck_slug} literal; collapse '*'-prefix noise on
    {deck_slug}-templated names (working/delivery/*-FINAL.pptx and
    working/delivery/{deck_slug}-FINAL.pptx are the same canon). A bare
    filename with no directory (manifest entries like '*-FINAL.pptx' or
    '{deck_slug}-WORKBOOK-FILLABLE.pdf') is normalized as if rooted in
    working/deliverables/ — the flat pre-curation output dir every
    phase-produced file lands in unless the phase says otherwise."""
    s = (p or "").strip().rstrip("/")
    parts = s.split("/")
    out = []
    for part in parts:
        if part.startswith("*") and "-" in part:
            out.append("{deck_slug}" + part[1:])
        else:
            out.append(part)
    s = "/".join(out)
    if "/" not in s:
        # Bare filename: treat as a working/deliverables/ relative name (the
        # producing phases' flat output dir), matching '*-FINAL.pptx'-style
        # bundle-dir entries to their staged working/delivery/ twins.
        return "working/deliverables/" + s
    return s

def _producer_norm(p: str) -> str:
    """Normalize a manifest produces_artifact entry for the ten bundle keys.

    Same slug folding as _norm_glob, but WITHOUT _norm_glob's flat-bundle
    assumption: a bare filename here is a run-dir-root path, which is exactly
    the deck pair's pre-PD-062 spelling. _norm_glob keeps its meaning for the
    workbook loop, where a bare name really does mean working/deliverables/."""
    s = (p or "").strip().rstrip("/")
    out = []
    for part in s.split("/"):
        if part.startswith("*") and "-" in part:
            out.append("{deck_slug}" + part[1:])
        else:
            out.append(part)
    return "/".join(out)

def _same_artifact_alias(key: str, alias: str) -> bool:
    """True when `alias` is an older spelling of the SAME file as the canon —
    its slug-stripped basename matches. A different artifact recorded under the
    same key (PRESENTER-AUDIO-WEBINAR.mp3 vs PRESENTER-AUDIO.mp3) is not one."""
    canon = CANONICAL_PATHS.get(key, "")
    return (Path(alias.replace("{deck_slug}", "")).name
            == Path(canon.replace("{deck_slug}", "")).name)

def _audit_paths(manifest_path=None):
    """Run the cross-surface audit. Returns (ok, problems) where problems is a
    list of strings naming every disagreement (suitable for one line each).

    `manifest_path` overrides the auto-located PIPELINE-MANIFEST.json so a
    caller can audit an edited manifest (the PD-216 control pair)."""
    # Make the sibling imports resolvable when this file is run as a SCRIPT
    # (python3 presentation_job/deliverable_paths.py --audit): the scripts/
    # dir must be on sys.path for `import presentation_job` / `import build_deck`.
    scripts = _scripts_dir()
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    problems = []
    scripts = _scripts_dir()

    # Surface 0: self-consistency — exactly one path per key, non-empty.
    if len(CANONICAL_PATHS) != 10:
        problems.append(f"CANONICAL_PATHS must carry exactly the ten bundle keys; "
                        f"has {len(CANONICAL_PATHS)}")
    dup = {}
    for k, v in CANONICAL_PATHS.items():
        dup.setdefault(v, []).append(k)
    for v, ks in dup.items():
        if len(ks) > 1:
            problems.append(f"two keys share one canonical path {v!r}: {ks}")
    if len(WORKBOOK_PATHS) != 2:
        problems.append(f"WORKBOOK_PATHS must carry exactly the two workbook PDFs; "
                        f"has {len(WORKBOOK_PATHS)}")

    # Surface 3 (cheap, import-light): deliverables.py DELIVERABLE_AUDIT_SPEC —
    # filename_template / standardized_dest must agree with the canon's basename.
    try:
        from presentation_job.deliverables import DELIVERABLE_AUDIT_SPEC  # noqa: E402
    except Exception as exc:  # noqa: BLE001 — the audit must be runnable standalone
        problems.append(f"deliverables.py spec unreadable ({exc!r}) — cannot cross-check")
        spec_by_key = {}
    else:
        spec_by_key = {s["key"]: s for s in DELIVERABLE_AUDIT_SPEC}
        for key, rel in CANONICAL_PATHS.items():
            spec = spec_by_key.get(key)
            if spec is None:
                problems.append(f"{key}: canonical path exists but key absent from "
                                f"DELIVERABLE_AUDIT_SPEC")
                continue
            canon_name = Path(rel.replace("{deck_slug}", "")).name
            tmpl_name = Path(spec["filename_template"].replace("{deck_slug}", "")).name
            dest_name = Path(spec["standardized_dest"]).name
            # The canon's (slug-stripped) basename must match the spec's
            # filename_template; the flat-bundle dest may differ (curation renames).
            if canon_name != tmpl_name:
                problems.append(
                    f"{key}: canon basename {canon_name!r} != DELIVERABLE_AUDIT_SPEC "
                    f"filename_template {tmpl_name!r}")
            # standardized_dest is the POST-curation flat name; the canon is
            # pre-curation. Record agreement of key presence only for dest.

    # Surface 4: build_deck.DELIVERABLES_REQUIRED (import build_deck only if
    # cheap; fall back to a regex read of the table to avoid pulling the
    # renderer's import side effects).
    bd_table = None
    try:
        import build_deck  # noqa: E402
        bd_table = [(d["key"], d["filename"]) for d in build_deck.DELIVERABLES_REQUIRED]
    except Exception:  # noqa: BLE001 — regex fallback below
        bd_table = None
    if bd_table is None:
        try:
            import re as _re
            src = (scripts / "build_deck.py").read_text(encoding="utf-8", errors="replace")
            block = src[src.index("DELIVERABLES_REQUIRED = ["):]
            block = block[:block.index("]")]
            rows = _re.findall(
                r'"key":\s*"([^"]+)",\s*\n\s*"filename":\s*"([^"]+)"', block)
            bd_table = rows
        except Exception as exc:  # noqa: BLE001
            problems.append(f"build_deck.DELIVERABLES_REQUIRED unreadable ({exc!r}) "
                            f"— cannot cross-check")
            bd_table = []
    bd_by_key = dict(bd_table or {})
    for key, rel in CANONICAL_PATHS.items():
        fname = bd_by_key.get(key)
        if fname is None:
            problems.append(f"{key}: absent from build_deck.DELIVERABLES_REQUIRED")
            continue
        canon_name = Path(rel.replace("{deck_slug}", "")).name
        bd_name = Path(fname.replace("{deck_slug}", "")).name
        if canon_name != bd_name:
            problems.append(f"{key}: canon basename {canon_name!r} != "
                            f"build_deck.DELIVERABLES_REQUIRED filename {bd_name!r}")

    # Surface 2: phase_verifiers._DELIVERY_PATTERN_BY_KEY (regex read; the
    # module imports build_deck lazily and is heavier than needed here).
    try:
        src = (scripts / "phase_verifiers.py").read_text(encoding="utf-8", errors="replace")
        start = src.index("_DELIVERY_PATTERN_BY_KEY = {")
        end = src.index("}", start)
        block = src[start:end]
        import re as _re
        pv_pairs = _re.findall(r'"([a-z_0-9]+)":\s*"([^"]+)"', block)
        pv_by_key = dict(pv_pairs)
    except Exception as exc:  # noqa: BLE001
        problems.append(f"phase_verifiers._DELIVERY_PATTERN_BY_KEY unreadable ({exc!r})")
        pv_by_key = {}
    for key, rel in CANONICAL_PATHS.items():
        pat = pv_by_key.get(key)
        if pat is None:
            problems.append(f"{key}: absent from phase_verifiers._DELIVERY_PATTERN_BY_KEY")
            continue
        if _norm_glob(pat) != _norm_glob(rel):
            # Accept the documented alias: pv's infographic legacy delivery/ glob.
            aliases = {a for a in ALIAS_PATHS.get(key, [])}
            if _norm_glob(pat) in {_norm_glob(a) for a in aliases}:
                continue
            problems.append(f"{key}: phase_verifiers pattern {pat!r} != canon {rel!r}")

    # Surface 1: PIPELINE-MANIFEST.json — build_bundle_files keyset + the
    # producing phases' produces_artifact for each key.
    mpath = Path(manifest_path) if manifest_path else _manifest_location()
    if mpath is None or not Path(mpath).is_file():
        problems.append("PIPELINE-MANIFEST.json not found (searched upward from "
                        "the module) — cannot cross-check")
    else:
        try:
            man = json.loads(Path(mpath).read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"PIPELINE-MANIFEST.json unreadable ({exc!r})")
            man = {}
        build_files = man.get("build_bundle_files") or []
        if sorted(build_files) != sorted(CANONICAL_PATHS.keys()):
            problems.append(f"manifest build_bundle_files {sorted(build_files)} != "
                            f"canon keys {sorted(CANONICAL_PATHS.keys())}")
        # produces_artifact per phase: map normalized declaration -> phase ids.
        # `produced` keeps run-dir-root bare names as written (the ten keys);
        # `produced_flat` applies the workbook flat-bundle convention.
        produced = {}
        produced_flat = {}
        for ph in (man.get("phases") or []):
            pa = ph.get("produces_artifact")
            if not pa:
                continue
            items = pa if isinstance(pa, list) else [pa]
            for it in items:
                produced.setdefault(_producer_norm(str(it)), []).append(ph.get("id"))
                produced_flat.setdefault(_norm_glob(str(it)), []).append(ph.get("id"))
        for key, rel in CANONICAL_PATHS.items():
            canon = _producer_norm(rel)
            alias_norms = {_producer_norm(a) for a in ALIAS_PATHS.get(key, [])
                           if _same_artifact_alias(key, a)}
            hits = {n: ids for n, ids in produced.items()
                    if n == canon or n in alias_norms}
            if not hits:
                problems.append(f"{key}: no manifest phase produces the canonical "
                                f"path {rel!r} (or a documented alias)")
            # Every producer of this artifact must declare the CANONICAL path.
            # A producer that still writes an older spelling is the drift this
            # unit deletes, so it is reported by name.
            for n, ids in sorted(hits.items()):
                if n == canon:
                    continue
                names = ", ".join(str(i) for i in ids)
                problems.append(
                    f"{key}: manifest producer {names} writes the alias {n!r}, "
                    f"not the canonical path {rel!r}")

        # Workbook: P8.25-WORKBOOK must produce both workbook paths (bare
        # names here are the flat bundle dir, per _norm_glob).
        for wkey, wrel in WORKBOOK_PATHS.items():
            if _norm_glob(wrel) not in produced_flat:
                problems.append(f"{wkey}: no manifest phase produces {wrel!r}")

    ok = not problems
    return ok, problems

def audit_paths(manifest_path=None):
    """Public audit entry: returns (ok, problems)."""
    return _audit_paths(manifest_path=manifest_path)

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="FIX 4 audit: one canonical path per deliverable key, "
                    "cross-checked against the manifest, phase_verifiers, "
                    "deliverables.py, and build_deck.DELIVERABLES_REQUIRED.")
    ap.add_argument("--audit", action="store_true",
                    help="run the cross-surface audit (exit 0 pass / 1 fail)")
    ap.add_argument("--json", action="store_true",
                    help="emit the audit report as JSON")
    ap.add_argument("--manifest", default=None,
                    help="audit this PIPELINE-MANIFEST.json instead of the "
                         "auto-located one (the edited-manifest control)")
    args = ap.parse_args(argv)

    if args.audit or args.json:
        ok, problems = audit_paths(manifest_path=args.manifest)
        print("DELIVERABLE PATH AUDIT (MASTER Part 8 FIX 4)")
        print(f"canonical keys ({len(CANONICAL_PATHS)}):")
        for key in sorted(CANONICAL_PATHS):
            print(f"  {key:<16} -> {CANONICAL_PATHS[key]}")
        print(f"workbook pdfs ({len(WORKBOOK_PATHS)}):")
        for key in sorted(WORKBOOK_PATHS):
            print(f"  {key:<16} -> {WORKBOOK_PATHS[key]}")
        if problems:
            print(f"DISAGREEMENTS ({len(problems)}):")
            for p in problems:
                print(f"  - {p}")
        else:
            print("all surfaces agree: manifest produces_artifact, "
                  "phase_verifiers patterns, deliverables.DELIVERABLE_AUDIT_SPEC, "
                  "build_deck.DELIVERABLES_REQUIRED")
        if args.json:
            print(json.dumps({
                "ok": ok,
                "canonical_paths": dict(CANONICAL_PATHS),
                "workbook_paths": dict(WORKBOOK_PATHS),
                "alias_paths": {k: list(v) for k, v in ALIAS_PATHS.items()},
                "problems": problems,
            }, indent=2))
        return 0 if ok else 1

    ap.print_help()
    return 2

if __name__ == "__main__":  # pragma: no cover - operator entry point
    sys.exit(main())
