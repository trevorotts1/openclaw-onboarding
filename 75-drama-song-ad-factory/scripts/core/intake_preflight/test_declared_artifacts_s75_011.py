"""S75-011: every declared stage output is a file the stage really writes.

The declared outputs before this fix included names written by nothing at all
(``script/lyrics.json``, ``video/clips.json``, ``qc/retakes.json``,
``final-qc/record.json``, ``delivery/receipts.json``) and one that is an INPUT
to its stage (``edit/timeline.json``). This module pins the audited truth and
refuses a declared artifact that only ``factory.py`` names.

Two rules, both parsed from source (no stage runs, no provider, no ffmpeg):

1. Every declared artifact is named by at least one non-test, non-factory
   module under ``scripts/`` or ``shared-bridge/`` -- a name that exists only
   in ``factory.py`` is a name nothing writes. The three artifacts whose writer
   is built by another lane are the ONLY exceptions, and they are pinned in
   ``PENDING_WRITERS`` below so a new invented name fails here.
2. The declared artifact tuples are the audited table, stage by stage.

Run: ``python3 -B scripts/core/intake_preflight/test_declared_artifacts_s75_011.py``
"""
import ast
import os
from pathlib import Path
import sys
import unittest

CORE = Path(__file__).resolve().parent.parent
SKILL = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE), str(CORE / "intake_preflight")]
from intake_preflight import factory

#: The audited truth: what each stage really emits, and the file that proves it.
#: research/evidence.json, research/manifest.json, research/bundle.json --
#:   research.py render() writes all three (S75-005).
#: creative/story.json -- read + validated by story_arc.py; the run's own story.
#: creative/blueprint.json -- the Story Beat Blueprint method_plan.py validates.
#: creative/lyrics.json -- the lyric sheet lyric_writer.py reads; required by
#:   script_approval/stage.py 83-86 as creative/lyrics.json.
#: music/picked-song.mp3, song-choices/pick.json -- the pick gate's own output
#:   (song_choices.py writes both).
#: continuity/qc-records.json, continuity/makers.json -- the typed records
#:   character_continuity/stage.py loads (stage.py 100-121).
#: storyboard/shot-list.json, storyboard/contracts.json -- the shot list the
#:   speaker check reads and the contracts approval_package.py records.
#: keyframes/manifest.json -- keyframes.write_manifest() (keyframes.py 155).
#: generation/clips-manifest.json -- PENDING: kie_dispatch.py must write it.
#: qc/retakes-plan.json -- PENDING: retake_manager.py must write it.
#: edit/ad.mp4 -- the rendered master the assembly command writes.
#: qc/final-qc-verdict.json -- PENDING: qc_gate.py must write it (S75-002 B).
#: delivery/01..12 -- the twelve numbered package slots, the exact file names
#:   delivery_package.contract.PACKAGE_ITEMS verifies (U-A13, U-T05).
ARTIFACT_TRUTH = {
    "research": ("research/evidence.json", "research/manifest.json",
                 "research/bundle.json"),
    "creative-strategy": ("creative/story.json", "creative/blueprint.json"),
    "script-lyrics": ("creative/lyrics.json",),
    "music": ("music/picked-song.mp3", "song-choices/pick.json"),
    "continuity-bible": ("continuity/qc-records.json",
                         "continuity/makers.json"),
    "storyboard": ("storyboard/shot-list.json", "storyboard/contracts.json"),
    "image-keyframes": ("keyframes/manifest.json",),
    "video-generation": ("generation/clips-manifest.json",),
    "qc-retakes": ("qc/retakes-plan.json",),
    "assembly": ("edit/ad.mp4",),
    "final-qc": ("qc/final-qc-verdict.json",),
    "delivery": ("delivery/01 - Full Song.mp3",
                 "delivery/01 - Instrumental.mp3",
                 "delivery/01 - Voice Only.mp3",
                 "delivery/01 - About These Audio Files.txt",
                 "delivery/02 - Character Bible.pdf",
                 "delivery/02 - Character Bible Images",
                 "delivery/03 - SCRIPT.pdf",
                 "delivery/04 - Storyboard.pdf",
                 "delivery/05 - Video Captioned.mp4",
                 "delivery/05 - Video Clean.mp4",
                 "delivery/06 - Clip 60s.mp4",
                 "delivery/06 - Clip 90s.mp4",
                 "delivery/07 - Ready-to-Post Kit.pdf",
                 "delivery/08 - Cover Thumbnail.png",
                 "delivery/09 - Lyric Sheet.pdf",
                 "delivery/10 - Captions.srt",
                 "delivery/11 - Character Images",
                 "delivery/12 - Welcome Sheet.pdf"),
}

#: The only declared artifacts whose writer does not exist yet. Each names the
#: script that must write it and the shape it must write. The owning lane is in
#: the U-A03 report; when a lane lands its writer the artifact moves out of
#: here (the entry is then redundant and this test says so).
PENDING_WRITERS = {
    "generation/clips-manifest.json": {
        "script": "scripts/core/kie_dispatch/kie_dispatch.py",
        "writes": "one row per produced clip: path, sha256, model, shot_id",
    },
    "qc/retakes-plan.json": {
        "script": "scripts/core/retake_manager/retake_manager.py",
        "writes": "one row per planned retake: unit, attempt, reason, source_sha256",
    },
    "qc/final-qc-verdict.json": {
        "script": "scripts/core/qc_gate.py",
        "writes": "the gate verdict: gate, producer, reason_code, evaluation",
    },
}

#: Where a writer may live. ``tests/`` is excluded by name below.
SCAN_ROOTS = ("scripts", "shared-bridge")


def _is_evidence_file(rel):
    """A file that can vouch for a name: not a test, not factory.py."""
    base = os.path.basename(rel)
    return not base.startswith("test_") and base != "factory.py"


def _string_constants(path):
    """Every string literal in one module, or () when it will not parse."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return ()
    return tuple(n.value for n in ast.walk(tree)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str))


def _named_outside_factory(artifact):
    """Relative paths of every non-test, non-factory module naming ``artifact``.

    The tree is parsed once per process (``_EVIDENCE``); each artifact is then
    one pass over the cached constants."""
    base = os.path.basename(artifact)
    return [rel for rel, consts in _evidence_index()
            if any(base in c for c in consts)]


_EVIDENCE = None


def _evidence_index():
    """[(skill-relative path, string constants)] for every evidence module."""
    global _EVIDENCE
    if _EVIDENCE is not None:
        return _EVIDENCE
    rows = []
    for root_name in SCAN_ROOTS:
        root = SKILL / root_name
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(str(root)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in sorted(filenames):
                if not fn.endswith(".py"):
                    continue
                path = Path(dirpath) / fn
                rel = os.path.relpath(str(path), str(SKILL))
                if not _is_evidence_file(rel):
                    continue
                consts = _string_constants(path)
                if consts:
                    rows.append((rel, consts))
    _EVIDENCE = rows
    return _EVIDENCE


class DeclaredArtifactsMatchTheTruth(unittest.TestCase):
    def test_the_twelve_stages_are_the_audited_twelve(self):
        self.assertEqual(tuple(factory.CANONICAL_STAGES),
                         tuple(ARTIFACT_TRUTH))

    def test_every_stage_declares_its_audited_artifacts(self):
        for stage in factory.CANONICAL_STAGES:
            self.assertEqual(
                tuple(factory.STAGE_DESCRIPTORS[stage]["artifacts"]),
                ARTIFACT_TRUTH[stage],
                "%s declares a different output inventory than the audit" % stage)

    def test_the_registry_publishes_the_same_inventory(self):
        for stage in factory.CANONICAL_STAGES:
            entry = factory.STAGE_REGISTRY[stage]
            self.assertEqual(tuple(entry["required_artifacts"]),
                             ARTIFACT_TRUTH[stage], stage)
            self.assertIn(entry["output_producer"], ARTIFACT_TRUTH[stage], stage)
            for ev in entry["required_evidence"]:
                self.assertIn(ev, ARTIFACT_TRUTH[stage], stage)


class EveryArtifactIsNamedOutsideFactory(unittest.TestCase):
    def test_no_declared_artifact_is_named_only_in_factory(self):
        for stage in factory.CANONICAL_STAGES:
            for artifact in ARTIFACT_TRUTH[stage]:
                if artifact in PENDING_WRITERS:
                    continue
                named = _named_outside_factory(artifact)
                self.assertTrue(
                    named,
                    "%s (%s) is declared but named by nothing outside factory.py"
                    % (artifact, stage))

    def test_pending_writers_are_exactly_the_audited_gaps(self):
        declared = {a for stage in ARTIFACT_TRUTH
                    for a in ARTIFACT_TRUTH[stage]}
        self.assertEqual(set(PENDING_WRITERS) - declared, set(),
                         "a pending writer names an artifact no stage declares")
        for artifact, spec in PENDING_WRITERS.items():
            self.assertTrue((SKILL / spec["script"]).is_file(),
                            "%s: writer %s does not exist" % (artifact, spec["script"]))
            self.assertTrue(spec["writes"].strip(),
                            "%s: the pending manifest shape is empty" % artifact)

    def test_a_pending_artifact_that_gains_a_writer_is_reportable(self):
        """A landed writer leaves its pending entry behind -- say so by name."""
        stale = [a for a in PENDING_WRITERS if _named_outside_factory(a)]
        self.assertEqual(stale, [],
                         "these artifacts now have a writer: remove them from "
                         "PENDING_WRITERS: %s" % ", ".join(sorted(stale)))

    def test_no_declared_artifact_carries_a_placeholder(self):
        for stage in factory.CANONICAL_STAGES:
            for artifact in ARTIFACT_TRUTH[stage]:
                for token in factory.PLACEHOLDER_TOKENS:
                    self.assertNotIn(token, artifact,
                                     "%s (%s) is a placeholder" % (artifact, stage))

    def test_every_stage_script_resolves_on_disk(self):
        for stage in factory.CANONICAL_STAGES:
            script = factory.STAGE_DESCRIPTORS[stage]["script"]
            self.assertTrue((SKILL / script).is_file(),
                            "%s script does not resolve: %s" % (stage, script))


if __name__ == "__main__":
    unittest.main()
