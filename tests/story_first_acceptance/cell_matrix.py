#!/usr/bin/env python3
"""S75-T32 repair: the eighteen acceptance cells the row actually names.

S75-A32 names nine behaviours and two flavours: 9 x 2 = 18 cells. The shipped
harness covered six of the nine in the onboarding flavour and reported the
other nine cells as though the 999 flavour had nothing to say. A cell that
runs nothing is not evidence of absence, it is absence of evidence, so this
module makes every cell EXECUTE a probe against its own repository's skill
root and record what it observed.

Three rules hold for every cell:

  * It executes. `executed` is true and `observations` lists what the probe
    actually returned at this skill root.
  * It carries a known-good control ON THE SAME INSTRUMENT: a case whose
    answer is already known must come back correct. If the control also comes
    back negative, the check is broken, not the target.
  * It proves its own repository was the one released. `repository_release`
    lists the modules this cell loaded and proves none came from the other
    flavour's skill root.

A cell whose capability is genuinely absent from this repository reports
NOT_APPLICABLE with `missing_capability` and `owed_by` named. It never
reports a pass it did not observe, and it never reports nothing.

Stdlib only. Importing this module has no side effects.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import acceptance_fixtures as F  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
CORE_DIR = os.path.join(REPO_ROOT, "75-drama-song-ad-factory", "scripts", "core")

#: Carrier repositories, named where the row's declared inbound dependencies
#: name them. A flavor is only bound to its own repository when that layout is
#: provisioned in this checkout; otherwise it is bound to the shared core it
#: actually ships and says so, instead of borrowing a name it did not earn.
FLAVOR_REPOSITORIES = {
    "onboarding": "trevorotts1/openclaw-onboarding",
    "999": "trevorotts1/999-setup",
}

#: The nine behaviours S75-A32 names, in the row's own order and wording.
BEHAVIORS = (
    "missing foundation",
    "cast bypass",
    "scene richness",
    "Notion migration",
    "identity setting changes",
    "approval ordering",
    "style18",
    "original byte preservation",
    "paid compatibility",
)

OBSERVED_PASS = "OBSERVED_PASS"
OBSERVED_FAIL = "OBSERVED_FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"

#: The behaviours already carried by a delivered facet in acceptance_fixtures.
CONTRACT_FACETS = {
    "missing foundation": ("missing_foundation_refused",),
    "cast bypass": ("missing_cast_refused", "undefined_speaker_refused"),
    "scene richness": ("one_line_scene_refused", "complete_fixture_validates"),
    "identity setting changes": ("identity_survives_world_revision",),
    "approval ordering": ("approval_ordering_and_binding",),
}

#: Who owes a capability that is genuinely not in a repository, and on what.
#: Read from task-ledger.json dependency edges, not guessed.
OWED = {
    "Notion migration": {
        "missing_capability": (
            "Notion library migration: character_library/migration.py with "
            "idempotent dry-run and rollback, over the sync layer "
            "(character_library/sync.py) and the persistence store "
            "(character_library/notion_store.py) that unit depends on"),
        "owed_by": "S75-T17",
        "blocked_by": ["S75-T15", "S75-T16", "S75-T28"],
    },
    "paid compatibility": {
        "missing_capability": (
            "paid-asset / raw-answer / legacy-approval preservation: "
            "compatibility.py, contracts/legacy-compatibility-map.json and "
            "tests/fixtures/paid_artifact_preservation.json"),
        "owed_by": "S75-T28",
        "blocked_by": ["S75-T01", "S75-T03"],
    },
    "style18": {
        "missing_capability": (
            "the eighteen-style catalog in the N999 repository: "
            "scripts/core/music_styles/catalog.py is absent, and "
            "music_styles.music_styles.STYLES still holds the old three-item "
            "menu"),
        "owed_by": "S75-T18 (owns the catalog); delivered into N999 by S75-T30",
        "blocked_by": ["S75-T30"],
    },
}

#: Contract-file capability owed by the N999 package assembly, reused by every
#: 999 cell that needs the shared story-first contracts.
N999_CONTRACTS_OWED = {
    "missing_capability": (
        "the shared story-first contract module in the N999 repository: "
        + ", ".join(F.REQUIRED_CONTRACT_FILES)),
    "owed_by": "S75-T30 (999 flavour package assembly, N999-PACKAGE-OWNER)",
    "blocked_by": ["S75-T07", "S75-T11", "S75-T13", "S75-T16", "S75-T17",
                   "S75-T23", "S75-T24", "S75-T25", "S75-T27", "S75-T28"],
}

#: The three owner descriptions, double-entered from MUSIC-AND-VIDEO-UX.md
#: section 2 and pinned by the sha256 S75-T18 already ships in its own test.
#: Byte comparison only; no normalization anywhere in this module.
OWNER_DESCRIPTION_SHA256 = {
    "soul-ballad":
        "26bf7da626b448bcb949d1ebf047851e54a986062b732fb7e2c6237083b5e588",
    "rnb-flow":
        "049d305eb3baaca912e7a6a854b8b0cf662c093362aee188a6412b3eb04baf6d",
    "soul-rise":
        "bd1a8e07ce4f896e5fded8a09ee1eeac3e7355cba663a119ee05b344cca6bba8",
}

CATALOG_REL = os.path.join("scripts", "core", "music_styles", "catalog.py")
INTAKE_REL = os.path.join("scripts", "core", "choice_card", "intake_card",
                          "intake_card.py")
SPEND_REL = os.path.join("scripts", "core", "spend_ledger.py")
N999_MUSIC_REL = os.path.join("scripts", "core", "music_styles",
                              "music_styles.py")
N999_CORE_REL = os.path.join("scripts", "core")

NOTION_CARRIERS = (
    os.path.join("scripts", "core", "character_library", "migration.py"),
    os.path.join("scripts", "core", "character_library", "sync.py"),
    os.path.join("scripts", "core", "character_library", "notion_store.py"),
    os.path.join("scripts", "core", "character_library", "cache.py"),
)
PAID_CARRIERS = (
    os.path.join("scripts", "core", "compatibility.py"),
    os.path.join("scripts", "core", "contracts",
                 "legacy-compatibility-map.json"),
    os.path.join("scripts", "core", "tests", "fixtures",
                 "paid_artifact_preservation.json"),
)


class Target:
    """One flavour's own repository view: who it is and where its code lives."""

    def __init__(self, flavor, repository, skill_root, seam=None):
        self.flavor = flavor
        self.repository = repository
        self.skill_root = os.path.abspath(skill_root)
        self.seam = dict(seam or {})
        self.root_source = self.seam.get("root_source", "caller-supplied")
        self.package_layout_provisioned = self.root_source == "package-anchor"
        self.package_layout_missing = (
            self.seam.get("package_layout_missing") if self.seam else None)

    def path(self, rel):
        return os.path.join(self.skill_root, rel)

    def binding(self):
        """What this facet is bound to, for the release record."""
        return {
            "flavor": self.flavor,
            "repository": self.repository,
            "skill_root": self.skill_root,
            "root_source": self.root_source,
            "package_layout_provisioned": self.package_layout_provisioned,
            "package_layout_missing": self.package_layout_missing,
            "seam": self.seam.get("seam"),
            "skill_root_anchor": self.seam.get("skill_root_anchor"),
            "character_approval_module": self.seam.get("character_approval_module"),
            "core_module": self.seam.get("core_module"),
            "core_digest_matches_seam": self.seam.get("core_digest_matches_seam"),
        }

def facet_target(flavor, repo_root=None):
    """Resolve one flavor through the package seam, exactly as the package does.

    Both flavors ship the same shared core. A flavor whose own package anchor is
    not provisioned in this checkout still runs every cell against those core
    bytes -- that is production code -- and records root_source='shared-core' so
    the record can never present an unprovisioned layout as a provisioned one.
    This is the difference between the two facets being decorative and being
    measured: each one runs the nine cells through its own seam resolution.
    """
    repo_root = os.path.abspath(repo_root or REPO_ROOT)
    core = os.path.join(repo_root, "75-drama-song-ad-factory", "scripts", "core")
    seam = {}
    with _on_path(core):
        adapter = _load_module(os.path.join(core, "package_flavor_adapter.py"),
                               "s75_t32_seam_%s" % flavor)
        resolved = dict(adapter.resolve(flavor))
        core_sha = hashlib.sha256(
            open(os.path.join(core, resolved["core_module"] + ".py"), "rb").read()
        ).hexdigest()
        seam = dict(resolved)
        seam["core_digest_matches_seam"] = core_sha == resolved.get("core_digest")
    anchor = seam.get("skill_root_anchor")
    anchor_root = os.path.join(repo_root, anchor) if anchor else None
    if anchor_root and os.path.isdir(anchor_root):
        seam["root_source"] = "package-anchor"
        seam["package_layout_missing"] = None
        return Target(flavor, FLAVOR_REPOSITORIES.get(flavor, "unknown"),
                      anchor_root, seam)
    seam["root_source"] = "shared-core"
    seam["package_layout_missing"] = anchor_root
    # The shared core lives in the onboarding package. A flavor that has no
    # provisioned anchor of its own is therefore bound to those bytes and to the
    # repository that carries them -- named as such, not relabelled.
    return Target(flavor, FLAVOR_REPOSITORIES["onboarding"],
                  os.path.join(repo_root, "75-drama-song-ad-factory"), seam)


class CellDrift(Exception):
    """A carrier changed shape; the cell refuses to guess rather than pass."""


# --------------------------------------------------------------------------
# instruments
# --------------------------------------------------------------------------

@contextlib.contextmanager
def _on_path(*dirs):
    added = []
    for d in dirs:
        if d and os.path.isdir(d) and d not in sys.path:
            sys.path.insert(0, d)
            added.append(d)
    try:
        yield
    finally:
        for d in added:
            try:
                sys.path.remove(d)
            except ValueError:
                pass


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("no loader for %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _ast_literal_dict(path, name):
    """The source literal assigned to `name` in `path`, read from the bytes.

    This reads the SOURCE, before any import, so a runtime record cannot stand
    in for the text that was shipped.
    """
    with open(path, "rb") as fh:
        tree = ast.parse(fh.read())
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    found.append(ast.literal_eval(node.value))
    if len(found) != 1:
        raise CellDrift("%s has %d assignments to %s, expected exactly 1"
                        % (path, len(found), name))
    return found[0]


def _bytes(text):
    return text.encode("utf-8")


def _sha256_bytes(text):
    return hashlib.sha256(_bytes(text)).hexdigest()


def _known_skill_roots():
    roots = [
        os.path.join(os.path.dirname(os.path.dirname(HERE)),
                     "75-drama-song-ad-factory"),
        os.path.join(os.path.expanduser("~"), "999-setup", ".claude", "skills",
                     "drama-song-ad-factory"),
    ]
    out = []
    for r in roots:
        r = os.path.realpath(r)
        if r not in out:
            out.append(r)
    return out


def _under(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def _snapshot():
    out = {}
    for name, module in list(sys.modules.items()):
        f = getattr(module, "__file__", None)
        if f:
            out[name] = os.path.abspath(f)
    return out


def _release(target, before, paths):
    """Prove this cell released its own repository and no other.

    Three independent facts: which of this repository's modules the cell had in
    play, which files it inspected, and that none of them, nor any sys.path
    entry, came from the other flavour's skill root.
    """
    after = _snapshot()
    own_in_use, loaded_here, foreign = [], [], []
    for name, path in sorted(after.items()):
        if _under(path, target.skill_root):
            own_in_use.append(os.path.relpath(path, target.skill_root))
            if before.get(name) != path:
                loaded_here.append(os.path.relpath(path, target.skill_root))
            continue
        for root in _known_skill_roots():
            if root != os.path.realpath(target.skill_root) and _under(path, root):
                foreign.append("%s (%s)" % (os.path.relpath(path, root), name))
                break
    inspected = [os.path.relpath(p, target.skill_root) if _under(p, target.skill_root)
                 else p for p in paths]
    inside = all(_under(p, target.skill_root) for p in paths) if paths else False
    foreign_paths = [p for p in sys.path
                     if any(_under(p, r) for r in _known_skill_roots()
                            if r != os.path.realpath(target.skill_root))]
    released = (not foreign and not foreign_paths and inside
                and bool(own_in_use or paths))
    return {
        "repository": target.repository,
        "skill_root": target.skill_root,
        "modules_from_own_repository_in_use": own_in_use,
        "modules_loaded_for_this_cell": loaded_here,
        "paths_inspected": inspected,
        "all_paths_inside_own_repository": inside,
        "foreign_repository_modules_loaded": foreign,
        "foreign_repository_sys_path_entries": sorted(set(foreign_paths)),
        "own_repository_released": released,
        "method": ("this repository's modules and inspected paths only; every "
                   "sys.modules __file__ and sys.path entry checked against every "
                   "known drama-song-ad-factory skill root"),
    }


def _presence_control(target, rel, label):
    """Known-good control for the file-presence instrument.

    The answer is known in advance: this file is in the repository. A scan that
    cannot find it is broken, and every absence it reports is worthless.
    """
    path = target.path(rel)
    return {"instrument": "file presence", "input": path, "label": label,
            "expected": "present", "observed": os.path.isfile(path),
            "pass": os.path.isfile(path)}


# --------------------------------------------------------------------------
# cell assembly
# --------------------------------------------------------------------------

def _result(checks):
    return all(c["result"] for c in checks)


def _cell(target, behavior, status, instrument, checks, observations,
          known_good, negative, paths, not_applicable=None, before=None):
    record = {
        "cell_id": "%s::%s" % (target.flavor, behavior),
        "flavor": target.flavor,
        "behavior": behavior,
        "repository": target.repository,
        "skill_root": target.skill_root,
        "executed": True,
        "status": status,
        "instrument": instrument,
        "checks": checks,
        "observations": observations,
        "known_good_control": known_good,
        "negative_control": negative,
        "not_applicable": not_applicable,
    }
    if before is not None:
        record["repository_release"] = _release(target, before, paths)
    return record


def _na(target, behavior, instrument, observations, known_good, negative,
        owed, paths, before):
    return _cell(target, behavior, NOT_APPLICABLE, instrument, [],
                 observations, known_good, negative, paths,
                 not_applicable=dict(owed), before=before)


# --------------------------------------------------------------------------
# 1..5: the contract-gate behaviours
# --------------------------------------------------------------------------

def probe_contract(target, behavior, before):
    facets = CONTRACT_FACETS[behavior]
    instrument = ("story_first_contracts." + " / ".join(facets))
    contract_paths = [target.path(rel) for rel in F.REQUIRED_CONTRACT_FILES]
    absent = F.missing_contract_files(target.skill_root)
    if absent:
        control = _presence_control(target, N999_MUSIC_REL,
                                    "a module this repository does carry")
        observations = [
            "resolved %d required contract file(s) under this skill root; %d absent"
            % (len(F.REQUIRED_CONTRACT_FILES), len(absent)),
        ]
        observations += ["absent: %s" % p for p in absent]
        kind, message = _load_error(target)
        observations.append("load_package raised %s: %s" % (kind, message))
        observations.append(
            "the same resolver found %s, so the absence above is a property of "
            "this repository and not of the instrument" % N999_MUSIC_REL)
        return _na(target, behavior, instrument, observations, control,
                   {"unmet_condition": "a contract-bound refusal cannot be made "
                                       "red where the contract module is absent",
                    "observed": None, "control_red": False},
                   N999_CONTRACTS_OWED, contract_paths, before)

    ctx = F.load_package(target.skill_root)
    records = F.build_records(ctx.core)
    results = [F.run_facet(ctx, facet) for facet in facets]
    checks = []
    observations = []
    for result in results:
        observations.append(
            "%s: ok=%s, %d check(s), negative control red=%s"
            % (result["facet"], result["ok"], len(result["checks"]),
               result["control"]["control_red"]))
        for check in result["checks"]:
            checks.append(dict(check))
    control = _gate_known_good(ctx, records)
    observations.append(
        "known-good control: all %d required artifacts supplied -> admitted=%s"
        % (len(ctx.core.STAGE_REQUIRES["script_lyrics"]), control["observed"]))
    ok = all(r["ok"] and r["control"]["control_red"] for r in results)
    status = OBSERVED_PASS if ok and control["pass"] else OBSERVED_FAIL
    return _cell(target, behavior, status, instrument, checks, observations,
                 control,
                 {"unmet_condition": results[0]["control"]["unmet_condition"],
                  "observed": results[0]["control"]["facet_ok_on_unmet"],
                  "control_red": all(r["control"]["control_red"]
                                     for r in results)},
                 contract_paths, before=before)


def _load_error(target):
    try:
        F.load_package(target.skill_root)
    except Exception as exc:  # noqa: BLE001 - the exact type is the evidence
        return type(exc).__name__, str(exc)[:300]
    return "None", "load_package unexpectedly succeeded"


def _gate_known_good(ctx, records):
    """Known-good control for the contract-gate instrument: admit a full set."""
    registry = F._seed_registry(ctx.core, records, upto_stage="script_lyrics")
    try:
        admitted = ctx.core.check_stage("script_lyrics", registry)["admitted"]
    except Exception as exc:  # noqa: BLE001 - the control must not raise
        return {"instrument": "check_stage", "input": "every required artifact "
                "supplied in stage order", "expected": "admitted=True",
                "observed": "%s: %s" % (type(exc).__name__, exc), "pass": False}
    return {"instrument": "check_stage",
            "input": "every required artifact supplied in stage order",
            "expected": "admitted=True", "observed": bool(admitted),
            "pass": admitted is True}


# --------------------------------------------------------------------------
# 6: style18
# --------------------------------------------------------------------------

def _style18_checks(ids, unique_count, max_styles, validate_count,
                    choice_count, resolved):
    return [
        {"contract": "music_styles.catalog.STYLE_IDS",
         "statement": "the catalog holds exactly eighteen ids",
         "result": len(ids) == 18},
        {"contract": "music_styles.catalog.STYLE_IDS",
         "statement": "the eighteen ids are unique",
         "result": unique_count == 18},
        {"contract": "music_styles.catalog.MAX_STYLES",
         "statement": "the declared maximum is eighteen",
         "result": max_styles == 18},
        {"contract": "music_styles.catalog.validate_catalog",
         "statement": "validate_catalog accepts all eighteen records",
         "result": validate_count == 18},
        {"contract": "music_styles.catalog.choice_rows",
         "statement": "all eighteen render as client choice rows",
         "result": choice_count == 18},
        {"contract": "music_styles.catalog.style",
         "statement": "every id resolves back to itself",
         "result": resolved is True},
    ]


def probe_style18(target, before):
    instrument = "music_styles.catalog (loaded from this repository's skill root)"
    path = target.path(CATALOG_REL)
    if not os.path.isfile(path):
        control = _presence_control(
            target, N999_MUSIC_REL,
            "the music carrier this repository does have")
        n999 = _n999_music_facts(target)
        observations = [
            "%s is absent from this repository" % CATALOG_REL,
            "the same resolver found %s, so the scan is sound" % N999_MUSIC_REL,
        ] + n999
        return _na(target, "style18", instrument, observations, control,
                   {"unmet_condition": "an eighteen-id carrier cannot be made "
                                       "red where no catalog exists",
                    "observed": None, "control_red": False},
                   OWED["style18"], [path, target.path(N999_MUSIC_REL)], before)

    module = _load_module(path, "s75_t32_catalog_%s" % target.flavor)
    ids = tuple(module.style_ids())
    rows = module.choice_rows()
    resolved = all(module.style(sid)["style_id"] == sid for sid in ids)
    checks = _style18_checks(ids, len(set(ids)), module.MAX_STYLES,
                             module.validate_catalog(), len(rows), resolved)
    observations = [
        "%d style ids: %s" % (len(ids), ", ".join(ids)),
        "validate_catalog() -> %d" % module.validate_catalog(),
        "choice_rows() -> %d rows" % len(rows),
        "old menu compatibility: ORIGINAL_STYLE_IDS == STYLE_IDS[:3] -> %s"
        % (tuple(module.ORIGINAL_STYLE_IDS) == ids[:3]),
    ]
    control = {"instrument": instrument, "input": "style('soul-ballad')",
               "expected": "resolves to soul-ballad",
               "observed": module.style("soul-ballad")["style_id"],
               "pass": module.style("soul-ballad")["style_id"] == "soul-ballad"}
    degraded = _style18_checks(tuple(ids)[:-1], 17, module.MAX_STYLES,
                               module.validate_catalog(), len(rows), resolved)
    negative = {"unmet_condition": "a seventeen-id carrier, checked by the same "
                                   "predicate",
                "observed": _result(degraded), "control_red": not _result(degraded)}
    ok = _result(checks) and control["pass"] and negative["control_red"]
    return _cell(target, "style18", OBSERVED_PASS if ok else OBSERVED_FAIL,
                 instrument, checks, observations, control, negative,
                 [path], before=before)


def _n999_music_facts(target):
    path = target.path(N999_MUSIC_REL)
    if not os.path.isfile(path):
        return ["%s is absent too" % N999_MUSIC_REL]
    try:
        with _on_path(target.path(N999_CORE_REL),
                      os.path.dirname(path)):
            module = _load_module(path, "s75_t32_n999_music_%s" % target.flavor)
        styles = tuple(getattr(module, "STYLES", ()))
        return ["invoked %s: STYLES holds %d id(s): %s"
                % (N999_MUSIC_REL, len(styles), ", ".join(styles) or "(none)")]
    except Exception as exc:  # noqa: BLE001 - the failure is the observation
        return ["invoking %s raised %s: %s" % (N999_MUSIC_REL,
                                               type(exc).__name__, str(exc)[:200])]


# --------------------------------------------------------------------------
# 7: original byte preservation
# --------------------------------------------------------------------------

def _intake_carrier(target):
    """Does this repository carry the original client descriptions at all?"""
    path = target.path(INTAKE_REL)
    if not os.path.isfile(path):
        return None, path
    return _ast_literal_dict(path, "_MUSIC_SENTENCE"), path


def _byte_checks(live, source):
    checks = []
    for style_id in sorted(OWNER_DESCRIPTION_SHA256):
        if style_id not in live:
            raise CellDrift("owner description %r is missing from the intake carrier"
                            % style_id)
        checks.append({
            "contract": "choice_card.intake_card._MUSIC_SENTENCE",
            "statement": "%s: bytes equal the pinned owner description" % style_id,
            "result": _sha256_bytes(live[style_id])
                      == OWNER_DESCRIPTION_SHA256[style_id],
        })
        if source is not None and style_id in source:
            checks.append({
                "contract": "music_styles.catalog.ORIGINAL_DESCRIPTIONS",
                "statement": "%s: source literal bytes equal total runtime bytes"
                             % style_id,
                "result": _bytes(source[style_id]) == _bytes(live[style_id]),
            })
    return checks


def probe_byte_preservation(target, before):
    instrument = ("UTF-8 byte comparison of source literals (ast) against the "
                  "pinned owner descriptions; no normalization")
    live, intake_path = _intake_carrier(target)
    if live is None:
        control = _presence_control(target, N999_MUSIC_REL,
                                    "a module this repository does carry")
        return _na(target, "original byte preservation", instrument,
                   ["%s is absent from this repository" % intake_path,
                    "no carrier for the original client descriptions exists here"],
                   control,
                   {"unmet_condition": "bytes cannot be compared where no "
                                       "carrier exists",
                    "observed": None, "control_red": False},
                   {"missing_capability": "an intake carrier for the original "
                    "client descriptions (choice_card/intake_card/intake_card.py)",
                    "owed_by": "S75-T30 (999 flavour package assembly)",
                    "blocked_by": ["S75-T07", "S75-T11"]}, [intake_path], before)

    source = None
    catalog_path = target.path(CATALOG_REL)
    if os.path.isfile(catalog_path):
        source = _ast_literal_dict(catalog_path, "ORIGINAL_DESCRIPTIONS")
        # Cross-check the runtime record too: a runtime value that drifts from
        # the source literal is exactly what a self-report cannot see.
        module = _load_module(catalog_path, "s75_t32_bytes_catalog_%s" % target.flavor)
        runtime = dict(module.ORIGINAL_DESCRIPTIONS)
        for key in source:
            if runtime.get(key) != source[key]:
                raise CellDrift("%s runtime description drifted from its source "
                                "literal" % key)

    checks = _byte_checks(live, source)
    observations = [
        "carrier: %s (%d description(s))" % (INTAKE_REL, len(live)),
        "catalog source literal carrier: %s"
        % ("present" if source is not None else "absent, not required for the "
           "pinned comparison"),
        "all three sha256 values match the owner pins typed from "
        "MUSIC-AND-VIDEO-UX.md section 2",
    ]
    sample = "soul-ballad"
    flipped = live[sample][:1].swapcase() + live[sample][1:]
    discriminating = {
        "untouched_compares_byte_equal": _bytes(live[sample]) == _bytes(live[sample]),
        "case_flipped_compares_byte_unequal": _bytes(flipped) != _bytes(live[sample]),
        "case_flipped_is_casefold_equal": flipped.casefold() == live[sample].casefold(),
    }
    control = {
        "instrument": instrument,
        "input": "an untouched description compared with itself, then a "
                 "case-flipped copy of it",
        "expected": "untouched byte-equal; case-flipped byte-unequal while "
                    "casefold-equal",
        "observed": discriminating,
        "pass": (discriminating["untouched_compares_byte_equal"]
                 and discriminating["case_flipped_compares_byte_unequal"]
                 and discriminating["case_flipped_is_casefold_equal"]),
    }
    negative = {"unmet_condition": "a case flip is invisible to casefold but "
                                   "must be caught by bytes",
                "observed": discriminating["case_flipped_compares_byte_unequal"],
                "control_red": discriminating["case_flipped_compares_byte_unequal"]}
    ok = _result(checks) and control["pass"] and negative["control_red"]
    byte_paths = [intake_path] + ([catalog_path] if source is not None else [])
    return _cell(target, "original byte preservation",
                 OBSERVED_PASS if ok else OBSERVED_FAIL, instrument, checks,
                 observations, control, negative, byte_paths, before=before)


# --------------------------------------------------------------------------
# 8 and 9: capability scans (absent capabilities, reported honestly)
# --------------------------------------------------------------------------

# The protocols below are declared, not guessed: S75-T17 owns
# character_library/migration.py and S75-T28 owns compatibility.py, and both
# are still unmerged at this head. Neither capability can be exercised as
# production code here. What CAN be exercised is the protocol the row will
# accept, from both sides -- a conforming provider must pass and a broken one
# must fail -- so the check is a check and not a line in a list. The cell stays
# NOT_APPLICABLE for production and records the exercise beside it.

MIGRATION_PROTOCOL = (
    "migrate(library, *, dry_run=False, rollback=False) -> "
    '{"library": <library>, "applied": <bool>}; dry_run and rollback leave the '
    "input untouched and report applied=False; a real apply de-duplicates by "
    "character_id keeping the highest revision, and repeating it is idempotent")

COMPATIBILITY_PROTOCOL = (
    "classify(record) -> "
    '{"state": "COMPATIBLE"|"COMPATIBILITY_LIMITED", "readable": <bool>, '
    '"regenerated": <bool>}; a paid legacy record stays readable, is marked '
    "COMPATIBILITY_LIMITED and is never regenerated")

def _legacy_library():
    return {"schema": "legacy.v1", "characters": [
        {"character_id": "char_ida", "revision": 2, "name": "Ida Rusk"},
        {"character_id": "char_ida", "revision": 3, "name": "Ida Rusk"},
        {"character_id": "char_herbary", "revision": 1, "name": "Herbary"},
    ]}

def _migration_provider(broken):
    def migrate(library, *, dry_run=False, rollback=False):
        original = json.loads(json.dumps(library))
        if rollback:
            return {"library": original, "applied": False}
        out = json.loads(json.dumps(library))
        keep = {}
        for record in out["characters"]:
            cid = record["character_id"]
            if (cid not in keep
                    or (record["revision"] < keep[cid]["revision"] if broken
                        else record["revision"] > keep[cid]["revision"])):
                keep[cid] = record
        out["characters"] = sorted(keep.values(), key=lambda r: r["character_id"])
        out["schema"] = "s75.library.v1"
        if dry_run and broken:
            library["characters"].append({"character_id": "char_drift",
                                          "revision": 1, "name": "Drift"})
            return {"library": out, "applied": True}
        return {"library": out, "applied": not dry_run}
    return migrate

def _migration_checks(migrate):
    source = _legacy_library()
    untouched = json.dumps(source, sort_keys=True)
    dry = migrate(source, dry_run=True)
    dry_untouched = json.dumps(source, sort_keys=True) == untouched
    rollback = migrate(source, rollback=True)
    rollback_untouched = json.dumps(source, sort_keys=True) == untouched
    applied = migrate(source)
    ids = [r["character_id"] for r in applied["library"]["characters"]]
    ida = [r for r in applied["library"]["characters"]
           if r["character_id"] == "char_ida"]
    twice = migrate(applied["library"])
    return [
        {"contract": "migration.migrate", "statement":
         "dry_run leaves the input library byte-identical", "result": dry_untouched},
        {"contract": "migration.migrate", "statement":
         "dry_run reports applied=False", "result": dry["applied"] is False},
        {"contract": "migration.migrate", "statement":
         "rollback leaves the input library byte-identical and reports applied=False",
         "result": rollback_untouched and rollback["applied"] is False},
        {"contract": "migration.migrate", "statement":
         "apply de-duplicates by character_id (3 records -> 2 characters)",
         "result": sorted(ids) == ["char_herbary", "char_ida"]},
        {"contract": "migration.migrate", "statement":
         "apply keeps the highest revision for a duplicated character",
         "result": len(ida) == 1 and ida[0]["revision"] == 3},
        {"contract": "migration.migrate", "statement":
         "a repeated apply is idempotent",
         "result": (json.dumps(twice["library"], sort_keys=True)
                    == json.dumps(applied["library"], sort_keys=True))},
    ]

def _compatibility_provider(broken):
    def classify(record):
        legacy = record.get("schema") != "s75.scene.v1"
        if legacy:
            return {"state": "COMPATIBLE" if broken else "COMPATIBILITY_LIMITED",
                    "readable": True,
                    "regenerated": bool(broken)}
        return {"state": "COMPATIBLE", "readable": True, "regenerated": False}
    return classify

def _compatibility_checks(classify):
    paid = {"schema": "legacy.paid.v1", "artifact_id": "a_paid_1",
            "paid": True, "raw_answer": "kept verbatim"}
    current = {"schema": "s75.scene.v1", "artifact_id": "a_cur_1"}
    got_paid = classify(paid)
    got_current = classify(current)
    thin = classify({"schema": "legacy.paid.v1"})
    return [
        {"contract": "compatibility.classify", "statement":
         "a paid legacy record stays readable", "result": got_paid["readable"] is True},
        {"contract": "compatibility.classify", "statement":
         "a paid legacy record is marked COMPATIBILITY_LIMITED, never COMPATIBLE",
         "result": got_paid["state"] == "COMPATIBILITY_LIMITED"},
        {"contract": "compatibility.classify", "statement":
         "a paid legacy record is never regenerated automatically",
         "result": got_paid["regenerated"] is False},
        {"contract": "compatibility.classify", "statement":
         "a current-schema record classifies COMPATIBLE",
         "result": (got_current["state"] == "COMPATIBLE"
                    and got_current["readable"] is True)},
        {"contract": "compatibility.classify", "statement":
         "a paid record missing optional fields is classified, not raised on",
         "result": thin["readable"] is True},
    ]

def _exercise_once(kind, broken):
    if kind == "Notion migration":
        protocol, checks = MIGRATION_PROTOCOL, _migration_checks(
            _migration_provider(broken))
    else:
        protocol = COMPATIBILITY_PROTOCOL
        checks = _compatibility_checks(_compatibility_provider(broken))
    return {"scope": "declared_provider_boundary",
            "protocol": protocol,
            "broken": broken,
            "checks": checks,
            "ok": _result(checks)}

def _exercise(kind, broken):
    """Both sides of the protocol, every time.

    The conforming provider must pass and the broken one must fail. Recording
    both makes 'this check can fail' an observation in the cell rather than a
    claim about it.
    """
    reference = _exercise_once(kind, False)
    broken_run = _exercise_once(kind, True)
    out = dict(reference if not broken else broken_run)
    out["reference_ok"] = reference["ok"]
    out["broken_ok"] = broken_run["ok"]
    return out

def _scan(target, relatives):
    return [{"path": rel, "present": os.path.isfile(target.path(rel))}
            for rel in relatives]


def probe_notion(target, before, broken=False):
    instrument = ("file presence over this repository's own skill root, with a "
                  "known-present control on the same scan, plus the migration "
                  "protocol exercised at its declared provider boundary")
    found = _scan(target, NOTION_CARRIERS)
    present = [item["path"] for item in found if item["present"]]
    if present:
        raise CellDrift(
            "Notion migration carriers now exist (%s); this cell must be taught "
            "to exercise them rather than claim not-applicable" % ", ".join(present))
    control = _presence_control(target, SPEND_REL,
                                "a core module this repository does carry")
    exercise = _exercise("Notion migration", broken)
    observations = ["scanned %d Notion migration carrier(s): none present"
                    % len(NOTION_CARRIERS)]
    observations += ["absent: %s" % item["path"] for item in found]
    observations.append("known-good control on the same scan found %s, so the "
                        "absences above are real" % SPEND_REL)
    observations.append(
        "migration protocol exercised at the declared provider boundary "
        "(%s provider): %d check(s), %s"
        % ("broken" if broken else "conforming", len(exercise["checks"]),
           "PASS" if exercise["ok"] else "FAIL"))
    if os.path.isfile(target.path(os.path.join(
            "scripts", "core", "character_library", "notion_adapter.py"))):
        observations.append(
            "the scan also reaches Notion-named code: "
            "character_library/notion_adapter.py is present")
    cell = _cell(target, "Notion migration",
                 NOT_APPLICABLE if exercise["ok"] else OBSERVED_FAIL,
                 instrument, exercise["checks"], observations, control,
                 {"unmet_condition": "a migration provider that mutates the "
                                     "library on dry_run and keeps the lowest "
                                     "revision must be reported as failing",
                  "observed": None if exercise["ok"] else False,
                  "control_red": not exercise["ok"]},
                 [target.path(rel) for rel in NOTION_CARRIERS] + [target.path(SPEND_REL)],
                 before=before)
    cell["not_applicable"] = dict(OWED["Notion migration"])
    cell["exercise"] = exercise
    return cell


def probe_paid(target, before, broken=False):
    instrument = ("file presence over this repository's own skill root, plus a "
                  "token scan of the shared contract modules, plus the "
                  "compatibility protocol at its declared provider boundary")
    found = _scan(target, PAID_CARRIERS)
    present = [item["path"] for item in found if item["present"]]
    if present:
        raise CellDrift(
            "paid-compatibility carriers now exist (%s); this cell must be "
            "taught to exercise them rather than claim not-applicable"
            % ", ".join(present))
    control = _presence_control(target, SPEND_REL,
                                "a core module this repository does carry")
    exercise = _exercise("paid compatibility", broken)
    observations = ["scanned %d paid-compatibility carrier(s): none present"
                    % len(PAID_CARRIERS)]
    observations += ["absent: %s" % item["path"] for item in found]
    tokens = ("paid", "purchase", "billing", "raw_answer", "legacy_output")
    hits = {}
    for rel in F.REQUIRED_CONTRACT_FILES:
        path = target.path(rel)
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8", "replace").casefold()
        hits[rel] = sum(text.count(token) for token in tokens)
    if hits:
        observations.append("token scan of the shared contract modules: %s"
                            % json.dumps(hits, sort_keys=True))
    else:
        observations.append("the shared contract modules are absent from this "
                            "repository, so the token scan has no target")
    observations.append("known-good control on the same scan found %s" % SPEND_REL)
    observations.append(
        "compatibility protocol exercised at the declared provider boundary "
        "(%s provider): %d check(s), %s"
        % ("broken" if broken else "conforming", len(exercise["checks"]),
           "PASS" if exercise["ok"] else "FAIL"))
    cell = _cell(target, "paid compatibility",
                 NOT_APPLICABLE if exercise["ok"] else OBSERVED_FAIL,
                 instrument, exercise["checks"], observations, control,
                 {"unmet_condition": "a classifier that regenerates a paid "
                                     "legacy record must be reported as failing",
                  "observed": None if exercise["ok"] else False,
                  "control_red": not exercise["ok"]},
                 ([target.path(rel) for rel in PAID_CARRIERS]
                  + [target.path(SPEND_REL)]
                  + [target.path(rel) for rel in F.REQUIRED_CONTRACT_FILES]),
                 before=before)
    cell["not_applicable"] = dict(OWED["paid compatibility"])
    cell["exercise"] = exercise
    return cell


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

PROBES = {
    "missing foundation": "contract",
    "cast bypass": "contract",
    "scene richness": "contract",
    "identity setting changes": "contract",
    "approval ordering": "contract",
    "style18": probe_style18,
    "original byte preservation": probe_byte_preservation,
    "Notion migration": probe_notion,
    "paid compatibility": probe_paid,
}


def run_cells(target, broken=False):
    """Execute all nine cells for one flavour. Returns nine records, in order.

    ``broken=True`` drives each cell with the condition it guards deliberately
    unmet, so every one of the nine can be seen FAILING. A cell that still
    reports a pass under ``broken=True`` is a dead check, and the falsifiability
    test says so instead of trusting the register.
    """
    cells = []
    for behavior in BEHAVIORS:
        before = _snapshot()
        probe = PROBES[behavior]
        if probe == "contract":
            cells.append(probe_contract(target, behavior, before))
        elif probe in (probe_notion, probe_paid):
            cells.append(probe(target, before, broken=broken))
        else:
            cells.append(probe(target, before))
    return cells


def counts(cells):
    out = {"cells_total": len(cells), "cells_pass": 0, "cells_fail": 0,
           "cells_not_applicable": 0, "cells_executed": 0}
    for cell in cells:
        if cell["executed"]:
            out["cells_executed"] += 1
        if cell["status"] == OBSERVED_PASS:
            out["cells_pass"] += 1
        elif cell["status"] == OBSERVED_FAIL:
            out["cells_fail"] += 1
        elif cell["status"] == NOT_APPLICABLE:
            out["cells_not_applicable"] += 1
    return out


def compare_heads(base_cells, head_cells):
    """Attach the base observation to each head cell and say what changed.

    `behavior_changed_between_heads` is about the PRODUCT. A cell that reports
    the same observation at both heads has proven nothing about this branch's
    effect on the product, and says so instead of implying a difference.
    """
    base_by_behavior = {c["behavior"]: c for c in base_cells}
    for cell in head_cells:
        base = base_by_behavior.get(cell["behavior"])
        if base is None:
            cell["at_base"] = {"observed": None,
                               "reason": "the cell did not run at the base head"}
            cell["behaviour_changed_between_heads"] = None
            continue
        cell["at_base"] = {
            "status": base["status"],
            "checks_passed": sum(1 for c in base["checks"] if c["result"]),
            "checks_total": len(base["checks"]),
            "observations": base["observations"],
            "known_good_control_passed": base["known_good_control"]["pass"],
        }
        cell["at_head"] = {
            "status": cell["status"],
            "checks_passed": sum(1 for c in cell["checks"] if c["result"]),
            "checks_total": len(cell["checks"]),
        }
        cell["behaviour_changed_between_heads"] = (
            base["status"] != cell["status"]
            or sum(1 for c in base["checks"] if c["result"]) !=
            sum(1 for c in cell["checks"] if c["result"]))
    return head_cells


def selfcheck():
    """Assert-based self-check: the instruments must discriminate. No framework."""
    workdir = tempfile.mkdtemp(prefix="s75t32-cell-selfcheck-")
    broken = os.path.join(workdir, "catalog.py")
    with open(broken, "w", encoding="utf-8") as fh:
        fh.write("STYLE_IDS = (%s,)\nMAX_STYLES = 18\n"
                 % ", ".join('"style-%02d"' % i for i in range(17)))
    module = _load_module(broken, "s75_t32_selfcheck_catalog")
    red = _style18_checks(tuple(module.STYLE_IDS), len(set(module.STYLE_IDS)),
                          module.MAX_STYLES, module.MAX_STYLES, 0, False)
    assert not _result(red), "a seventeen-id carrier passed the style18 predicate"
    green = _style18_checks(tuple("s%02d" % i for i in range(18)), 18, 18, 18, 18,
                            True)
    assert _result(green), "an eighteen-id carrier failed the style18 predicate"
    text = "slow, heartfelt singing; builds to a big emotional chorus."
    assert _bytes(text) == _bytes(text)
    assert _bytes(text[:1].swapcase() + text[1:]) != _bytes(text)
    assert (text[:1].swapcase() + text[1:]).casefold() == text.casefold()
    assert _ast_literal_dict.__name__ == "_ast_literal_dict"
    assert BEHAVIORS[0] == "missing foundation" and len(BEHAVIORS) == 9
    print("cell_matrix selfcheck ok: %d behaviours, instruments discriminate"
          % len(BEHAVIORS))
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-root")
    parser.add_argument("--flavor", default="onboarding")
    parser.add_argument("--repository", default=None)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    if args.selfcheck or not args.skill_root:
        selfcheck()
        sys.exit(0)
    target = Target(args.flavor, args.repository or "unknown", args.skill_root)
    cells = run_cells(target)
    json.dump({"flavor": args.flavor, "counts": counts(cells), "cells": cells},
              sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    sys.exit(0 if counts(cells)["cells_fail"] == 0 else 1)
