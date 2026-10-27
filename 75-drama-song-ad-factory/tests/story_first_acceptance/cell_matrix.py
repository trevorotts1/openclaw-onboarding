"""Cross-flavor acceptance cell matrix for S75-T32 / S75-A32. Stdlib only.

The row this file exists to satisfy:

  "Both flavor facets exercise missing foundation/cast bypass/scene richness/
   Notion migration/identity setting changes/approval ordering/style18/original
   byte preservation/paid compatibility; each facet releases its own repository."

Design rules this module holds itself to:

* Nine named checks, two flavors -- eighteen cells. The check list is frozen in
  ``REQUIRED_CHECKS`` and a test asserts it matches the row, so a walk cannot
  lose a check by omission.
* Every runnable cell calls production code. Nothing here re-implements a
  validator.
* Every cell can fail. Each ``run()`` takes ``broken=True``, which perturbs the
  *input condition* only; the assertion block is the same code either way. A
  cell that still reports PASS under ``broken=True`` is a dead check, and the
  falsifiability test fails it.
* Cells whose production module is genuinely absent at this head return
  ``BLOCKED_DEPENDENCY`` naming the owning task and the exact path. They are
  never reported as passing, never skipped and never faked. Their falsifiability
  is proved by injecting a reference provider and a broken provider at the cell
  boundary (see the test module); the production facet still reports BLOCKED.
* A cell reads its production modules through the flavor seam
  (``package_flavor_adapter.resolve``), so the flavor is measured, not
  decorative: anchor, root source, declared package differences and the
  shared-core digest are all facts in the cell's binding and in the receipt.

The migration check is no longer a declared protocol. S75-T17's module landed on
main as ``character_library/migration_plan.py`` with a real contract -- records
are proved from their own bytes, dry run is the default, ``apply`` and
``reverse`` require ``confirm=True``, and a second apply is a NOOP. The cell
drives that contract directly and proves it failable by removing a reference
image, so a record whose identity cannot be proved blocks the whole plan.

One integration protocol is still declared here, for the module that has not
landed. It is the smallest shape the row requires; the owning unit may implement
it however it likes.

  compatibility protocol (S75-T28, ``compatibility.py``):
      classify(record) -> dict
      returns {"state": "COMPATIBLE" | "COMPATIBILITY_LIMITED",
               "readable": <bool>, "regenerated": <bool>}
      A paid legacy record stays readable, is marked compatibility-limited and
      is never regenerated automatically.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(os.path.dirname(HERE))
REPO_ROOT = os.path.dirname(SKILL_ROOT)
CORE_DIR = os.path.join(SKILL_ROOT, "scripts", "core")

if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)
if SKILL_ROOT not in sys.path:
    sys.path.insert(0, SKILL_ROOT)

import package_flavor_adapter as FLAVOR  # noqa: E402


def _load_local(filename):
    """Load a fixture module from this directory by path, not by sys.path name."""
    path = os.path.join(HERE, filename)
    name = "s75t32_" + filename.replace(".py", "")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = _load_local("acceptance_fixtures.py")

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED_DEPENDENCY"

RELEASE_SCHEMA = "s75.t32.facet-release.v1"

#: The nine checks the row names, in the row's order.
REQUIRED_CHECKS = (
    "missing_foundation",
    "cast_bypass",
    "scene_richness",
    "notion_migration",
    "identity_setting_change",
    "approval_ordering",
    "style18",
    "original_byte_preservation",
    "paid_compatibility",
)

#: Declared by the row's own words: every one of these must be present before a
#: script may be generated.
FOUNDATIONS = ("research_bundle", "episode_cast_manifest", "episode_world",
               "causal_story_beats", "scene_plan")

#: Paths each flavor resolves the *same* shared core through. The ONB layout
#: carries the character approval module; the 999 layout deliberately has none.
#: S75-T17 landed ``character_library/migration_plan.py`` on main, so the
#: migration cell now drives that module's real contract (discover / build_plan /
#: apply / reverse / verify) instead of an injected stand-in.
NOTION_MIGRATION_PATHS = ("character_library/migration_plan.py",)
PAID_COMPATIBILITY_PATH = "compatibility.py"


# --- the flavor facet -----------------------------------------------------

class Facet:
    """One package flavor, resolved through the single named seam."""

    def __init__(self, flavor):
        self.flavor = flavor
        self.resolved = FLAVOR.resolve(flavor)
        self.anchor = self.resolved["skill_root_anchor"]
        self.anchor_root = os.path.join(REPO_ROOT, self.anchor)
        if os.path.isdir(self.anchor_root):
            self.root_source = "package-anchor"
            self.core_dir = os.path.join(self.anchor_root, "scripts", "core")
        else:
            # No provisioned layout for this flavor in this repository. The
            # shared core bytes are the same bytes both flavors ship, so the
            # cells still exercise real production code; the receipt records
            # that the layout itself is unprovisioned instead of inventing one.
            self.root_source = "shared-core"
            self.core_dir = CORE_DIR
        self._mods = {}

    def path(self, relative):
        return os.path.join(self.core_dir, relative)

    def has(self, relative):
        return os.path.isfile(self.path(relative))

    def load(self, relative):
        """Load a production module by path from this facet's resolved root."""
        if relative in self._mods:
            return self._mods[relative]
        path = self.path(relative)
        name = "s75t32_%s_%s" % (
            self.flavor.replace("-", "_"),
            relative.replace("/", "_").replace(".py", ""))
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._mods[relative] = module
        return module

    def core_sha256(self):
        with open(self.path("story_first_contracts.py"), "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    def binding(self):
        """What the cells are actually bound to, for the release receipt."""
        core_sha = self.core_sha256()
        approval = self.resolved["character_approval_module"]
        approval_present = bool(
            approval and os.path.isdir(self.anchor_root)
            and os.path.isfile(os.path.join(self.anchor_root, approval)))
        return {
            "flavor": self.flavor,
            "seam": self.resolved["seam"],
            "skill_root_anchor": self.anchor,
            "root_source": self.root_source,
            "core_module": self.resolved["core_module"],
            "core_schema_version": self.resolved["core_schema_version"],
            "core_sha256": core_sha,
            "core_digest_matches_seam": core_sha == self.resolved["core_digest"],
            "character_approval_module": approval,
            "character_approval_present": approval_present,
        }


def _result(cell, status, expected, observed, missing=None, restored=None):
    out = {
        "cell": cell,
        "status": status,
        "expected": expected,
        "observed": observed,
    }
    if missing is not None:
        out["missing"] = list(missing)
    if restored is not None:
        out["restored"] = restored
    return out


def _raise_code(callable_, *args, **kwargs):
    try:
        callable_(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - the exception code is the observation
        return getattr(exc, "code", type(exc).__name__)
    return None


def _refusal(callable_, *args, **kwargs):
    """(code, packet) for one refusal, or (None, None) when the call was admitted."""
    try:
        callable_(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return getattr(exc, "code", type(exc).__name__), getattr(exc, "packet", {})
    return None, None


def _seed(registry, C):
    registry.put("research_bundle", {"claims": [{"claim_id": "c1"}]})
    registry.put("episode_world", F.world())
    registry.put("episode_cast_manifest", F.cast_manifest())
    registry.put("causal_story_beats", {"beats": [{"beat_id": "b1"}]})
    registry.put("scene_plan", {"scenes": [F.rich_scene()]})
    registry.put("script", {"scenes": [F.rich_scene()]})
    registry.put("lyrics", {"lines": [{"line_id": "line_mara_001"}]})
    return registry


# --- 1. missing foundation -------------------------------------------------

def cell_missing_foundation(facet, broken=False, provider=None):
    C = facet.load("story_first_contracts.py")
    registry = C.RunRegistry()
    if broken:
        # Break: hand it the foundation, so the refusal under test cannot happen.
        _seed(registry, C)
    code, packet = _refusal(C.check_stage, "script_lyrics", registry)
    packet = packet or {}
    missing = packet.get("missing", [])
    admitted = _raise_code(C.check_stage, "script_lyrics",
                           _seed(C.RunRegistry(), C)) is None
    expected = ("script_lyrics is refused and the refusal names all five "
                "foundations, and the same stage is admitted once they exist")
    ok = (code in ("MISSING_INPUT", "ORDER")
          and set(missing) == set(FOUNDATIONS) and admitted)
    return _result("missing_foundation", PASS if ok else FAIL, expected,
                   {"refusal_code": code, "missing": sorted(missing),
                    "unfinished_stages": packet.get("unfinished_stages", []),
                    "admitted_when_foundation_present": admitted})


# --- 2. cast bypass --------------------------------------------------------

def cell_cast_bypass(facet, broken=False, provider=None):
    C = facet.load("story_first_contracts.py")
    manifest = F.cast_manifest(empty=not broken)
    defects = C.validate_cast_manifest(manifest, [F.rich_scene()])
    codes = sorted({(d.get("field", ""), d.get("issue", "")) for d in defects})
    absent = C.validate_cast_manifest({}, [])

    leaked_scene = F.rich_scene()
    leaked_scene["cast_ids"] = ["char_mara_001", "char_nobody_009"]
    leak_fields = sorted({d.get("field", "")
                          for d in C.validate_cast_manifest(F.cast_manifest(),
                                                            [leaked_scene])})
    clean = C.validate_cast_manifest(F.cast_manifest(), [F.rich_scene()])
    expected = ("an empty or absent cast is refused, an undefined speaker is "
                "refused, and a complete cast passes")
    ok = (bool(defects) and bool(absent) and "cast_ids" in leak_fields and clean == [])
    return _result("cast_bypass", PASS if ok else FAIL, expected,
                   {"empty_cast_defects": codes,
                    "absent_cast_defects": len(absent),
                    "undefined_speaker_fields": leak_fields,
                    "clean_cast_defects": clean})


# --- 3. scene richness -----------------------------------------------------

def cell_scene_richness(facet, broken=False, provider=None):
    C = facet.load("story_first_contracts.py")
    scene = F.rich_scene() if broken else F.placeholder_scene()
    defects = C.validate_scene(scene, world=F.world())
    fields = sorted({d.get("field", "") for d in defects})
    clean = C.validate_scene(F.rich_scene(), world=F.world())

    # Arm B: a scene with no spoken or sung line and no silent declaration.
    silent = F.rich_scene()
    silent["spoken_dialogue"] = []
    silent["sung_lyrics"] = []
    silent["performance_order"] = []
    no_line = C.validate_scene(silent, world=F.world())
    no_line_fields = sorted({d.get("field", "") for d in no_line})

    expected = ("a one-line placeholder scene is refused on purpose/action/choice/"
                "placeholder line, an empty scene is refused for having no line, "
                "and a rich causal scene passes")
    required = {"dramatic_purpose", "visible_action", "consequential_choice",
                "spoken_dialogue"}
    ok = (required <= set(fields) and "dialogue" in no_line_fields and clean == [])
    return _result("scene_richness", PASS if ok else FAIL, expected,
                   {"placeholder_defect_fields": fields,
                    "no_line_defect_fields": no_line_fields,
                    "rich_scene_defects": clean})


# --- 4. Notion migration --------------------------------------------------

def _load_provider(facet, paths, attribute):
    for relative in paths:
        if facet.has(relative):
            module = facet.load(relative)
            fn = getattr(module, attribute, None)
            if callable(fn):
                return fn, relative
    return None, None


def _call(fn, *args, **kwargs):
    """(value, exception name) for one production call. Real errors are observed,
    never swallowed: the caller turns them into the cell's ``observed`` facts."""
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:  # noqa: BLE001 - the exception name is the observation
        return None, getattr(exc, "code", type(exc).__name__)


def _tree_snapshot(root):
    """Every file under root, path -> sha256. The byte baseline for a round trip."""
    out = {}
    for current, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(current, name)
            with open(path, "rb") as handle:
                out[os.path.relpath(path, root)] = hashlib.sha256(
                    handle.read()).hexdigest()
    return out


def _migration_client(facet, tmp):
    """A client store written by the REAL local writers, never a hand-made shape."""
    CL = facet.load("character_library/character_library.py")
    client = os.path.join(tmp, "client-a")
    images = []
    for name, payload in (("maya.png", b"\x89PNG-maya"),
                          ("dre.png", b"\x89PNG-dre")):
        path = os.path.join(tmp, name)
        with open(path, "wb") as handle:
            handle.write(payload)
        images.append(path)
    CL.save_character(client, "Maya Lee", "Warm, 40s, silver braids.", [images[0]],
                      "Low, calm alto", background="Ohio", ethnicity="Black")
    CL.save_character(client, "Dre", "Sharp suit, calm voice.", [images[1]],
                      "Mid baritone")
    return client


def cell_notion_migration(facet, broken=False, provider=None):
    expected = ("every record is proved from its own bytes, a dry run writes "
                "nothing, a second apply maps nothing new, and reverse restores "
                "the tree byte for byte")
    if not facet.has(NOTION_MIGRATION_PATHS[0]):
        return _result(
            "notion_migration", BLOCKED, expected,
            {"reason": "no migration module at this head", "owned_by": "S75-T17"},
            missing=[facet.path(p) for p in NOTION_MIGRATION_PATHS])
    MIG = facet.load(NOTION_MIGRATION_PATHS[0])

    with tempfile.TemporaryDirectory() as tmp:
        client = _migration_client(facet, tmp)
        if broken:
            # Break: remove one reference image, so the record's identity can no
            # longer be proved from its own files. That is the condition this
            # cell exists to detect, not a different code path.
            os.unlink(os.path.join(client, "character-library", "dre",
                                   "references", "1-dre.png"))
        before = _tree_snapshot(client)
        plan = MIG.build_plan(client)
        dry_run_untouched = _tree_snapshot(client) == before
        stable = plan["plan_digest"] == MIG.build_plan(client)["plan_digest"]
        mapped = [r["new_id"] for r in plan["records"] if r["status"] == "MAPPED"]

        first, first_code = _call(MIG.apply, plan, confirm=True)
        after_first = _tree_snapshot(client)
        second, second_code = _call(MIG.apply, MIG.build_plan(client), confirm=True)
        after_second = _tree_snapshot(client)
        verification, verify_code = _call(MIG.verify, client)
        reversed_run, reverse_code = _call(MIG.reverse, client, confirm=True)
        restored = _tree_snapshot(client) == before

    ok = (len(mapped) == 2 and len(set(mapped)) == 2
          and dry_run_untouched and stable
          and first_code is None and first.get("status") == "APPLIED"
          and second_code is None and second.get("status") == "NOOP"
          and after_second == after_first
          and verify_code is None and verification.get("ok") is True
          and reverse_code is None and reversed_run.get("status") == "REVERSED"
          and restored)
    return _result("notion_migration", PASS if ok else FAIL, expected,
                   {"source": NOTION_MIGRATION_PATHS[0],
                    "mapped": len(mapped), "unique_ids": len(set(mapped)),
                    "dry_run_untouched": dry_run_untouched,
                    "plan_digest_stable": stable,
                    "apply": first_code or first.get("status"),
                    "second_apply": second_code or second.get("status"),
                    "verify": verify_code or verification.get("ok"),
                    "reverse": reverse_code or reversed_run.get("status"),
                    "restored_byte_for_byte": restored})


# --- 5. identity setting changes -----------------------------------------

def cell_identity_setting_change(facet, broken=False, provider=None):
    ID = facet.load("character_bible/identity.py")
    AG = facet.load("artifact_graph.py")

    identity = ID.seal_identity(F.identity_record())
    digest_before = identity["content_digest"]
    ID.validate_identity(identity)
    ID.validate_episode_setting(F.episode_setting())
    ID.validate_episode_setting(F.episode_setting("White House reception", "East Room"))
    digest_after = identity["content_digest"]

    polluted = dict(identity)
    polluted["location"] = "East Room"
    setting_in_identity = _raise_code(ID.validate_identity, polluted)

    with tempfile.TemporaryDirectory() as tmp:
        paths = {}
        for name, blob in (("world", b"world-v1"), ("plan", b"plan-v1"),
                           ("script", b"script-v1"), ("visual", b"visual-v1"),
                           ("identity", b"identity-v1")):
            p = os.path.join(tmp, name + ".txt")
            with open(p, "wb") as fh:
                fh.write(blob)
            paths[name] = p
        with AG.Graph(os.path.join(tmp, "graph.sqlite"), [tmp]) as graph:
            for name, p in paths.items():
                graph.register("run", name, name, name, p)
            graph.depend("run", "plan", "world")
            graph.depend("run", "script", "plan")
            graph.depend("run", "visual", "script")
            if broken:
                # Break: make the reusable identity a dependent of the setting.
                graph.depend("run", "identity", "world")
            affected = sorted(graph.invalidate_upstream_change(
                "run", "world", "setting changed to the White House reception"))
            unaffected = graph.non_dependents("run", "world")

    expected = ("a setting change keeps the identity digest, rejects setting "
                "fields in the identity, and invalidates only world dependents")
    ok = (digest_before == digest_after
          and setting_in_identity == "IdentityDefect"
          and affected == ["plan", "script", "visual", "world"]
          and "identity" in unaffected)
    return _result("identity_setting_change", PASS if ok else FAIL, expected,
                   {"identity_digest_stable": digest_before == digest_after,
                    "setting_field_refusal": setting_in_identity,
                    "affected": affected,
                    "unaffected": unaffected})


# --- 6. approval ordering -------------------------------------------------

def cell_approval_ordering(facet, broken=False, provider=None):
    C = facet.load("story_first_contracts.py")

    def foundation(registry):
        _seed(registry, C)
        registry.put("creative_package_manifest", {"package": "v1"})
        return registry

    def approve(registry):
        return registry.put(
            "package_approval", {"decision": "APPROVED"}, state=C.APPROVED,
            approved_digests={t: registry.digest_of(t)
                              for t in C.APPROVAL_BINDS["package_approval"]})

    early = foundation(C.RunRegistry())
    if broken:
        approve(early)          # Break: the ordering condition is removed.
    early_code = _raise_code(C.check_stage, "music", early)

    late = foundation(C.RunRegistry())
    approve(late)
    admitted = _raise_code(C.check_stage, "music", late) is None
    late.put("script", {"scenes": [F.placeholder_scene()]})
    stale_code, stale_packet = _refusal(C.check_stage, "music", late)
    stale_packet = stale_packet or {}
    stale_targets = sorted({d.get("target", "") for d in
                            stale_packet.get("approval_defects", [])})

    expected = ("music is refused before package approval is elected and refused "
                "again with a stale approval binding when the approved script "
                "digest changes")
    ok = (early_code in ("MISSING_INPUT", "ORDER", "APPROVAL")
          and admitted and stale_code in ("APPROVAL", "ORDER")
          and "script" in stale_targets)
    return _result("approval_ordering", PASS if ok else FAIL, expected,
                   {"music_before_approval": early_code,
                    "music_after_approval": admitted,
                    "music_after_script_change": stale_code,
                    "stale_approval_targets": stale_targets})


# --- 7. style18 ------------------------------------------------------------

def cell_style18(facet, broken=False, provider=None):
    CAT = facet.load("music_styles/catalog.py")
    ids = list(CAT.style_ids())
    restored = None
    if broken:
        # Break: ship seventeen live records and confirm the check notices.
        removed = ids[-1]
        saved = CAT.CATALOG.pop(removed, None)
        try:
            validate_code = _raise_code(CAT.validate_catalog)
            count = len(CAT.style_ids())
            catalog_size = len(CAT.CATALOG)
        finally:
            if saved is not None:
                CAT.CATALOG[removed] = saved
            restored = removed in CAT.CATALOG
    else:
        validate_code = _raise_code(CAT.validate_catalog)
        count = len(ids)
        catalog_size = len(CAT.CATALOG)

    expected = "exactly eighteen unique selectable styles and a clean catalog"
    ok = (count == 18 and catalog_size == 18 and len(set(ids)) == 18
          and validate_code is None)
    return _result("style18", PASS if ok else FAIL, expected,
                   {"style_count": count, "catalog_size": catalog_size,
                    "unique": len(set(ids)),
                    "validate_catalog": validate_code, "restored": restored})


# --- 8. original byte preservation ----------------------------------------

def cell_original_byte_preservation(facet, broken=False, provider=None):
    AG = facet.load("artifact_graph.py")
    with tempfile.TemporaryDirectory() as tmp:
        approved = os.path.join(tmp, "approved_script.txt")
        dependent = os.path.join(tmp, "scene_plan.txt")
        with open(approved, "wb") as fh:
            fh.write(b"scene one: the notice is opened\n")
        with open(dependent, "wb") as fh:
            fh.write(b"scene one plans the shared repair\n")
        with AG.Graph(os.path.join(tmp, "graph.sqlite"), [tmp]) as graph:
            record = graph.register("run", "script", "script", "script_lyrics",
                                    approved)
            graph.register("run", "scene_plan", "scene_plan", "story_plan",
                           dependent)
            graph.depend("run", "scene_plan", "script")
            if broken:
                # Break: the approved original's bytes change after approval.
                with open(approved, "ab") as fh:
                    fh.write(b"x")
            preserved = AG.sha256_file(approved) == record["sha256"]
            verify_code = _raise_code(graph.verify, "run", "script")
            graph.invalidate_upstream_change("run", "scene_plan", "plan revised")
            still_verified = _raise_code(graph.verify, "run", "script")
            after = AG.sha256_file(approved) == record["sha256"]

    expected = ("the approved original keeps its exact sha256 across a dependent "
                "invalidation and a changed byte is detected")
    ok = preserved and verify_code is None and still_verified is None and after
    return _result("original_byte_preservation", PASS if ok else FAIL, expected,
                   {"bytes_preserved": preserved,
                    "verify": verify_code,
                    "verify_after_invalidation": still_verified,
                    "digest_after": after})


# --- 9. paid compatibility (dependency) ----------------------------------

def cell_paid_compatibility(facet, broken=False, provider=None):
    fn, source = (provider, "injected")
    if fn is None:
        fn, source = _load_provider(facet, (PAID_COMPATIBILITY_PATH,), "classify")
    expected = ("a paid legacy artifact stays readable, is marked "
                "compatibility-limited and is never regenerated")
    if fn is None:
        return _result(
            "paid_compatibility", BLOCKED, expected,
            {"reason": "no compatibility module at this head", "owned_by": "S75-T28"},
            missing=[facet.path(PAID_COMPATIBILITY_PATH)])

    legacy = {"artifact_id": "paid_scene_001", "schema": "pre-s75",
              "paid": True, "bytes_sha256": "0" * 64}
    current = {"artifact_id": "paid_scene_002", "schema": "s75.scene.v1",
               "paid": True, "bytes_sha256": "1" * 64}
    legacy_out = fn(legacy)
    current_out = fn(current)
    ok = (legacy_out.get("readable") is True
          and legacy_out.get("state") == "COMPATIBILITY_LIMITED"
          and legacy_out.get("regenerated") is False
          and current_out.get("state") == "COMPATIBLE")
    return _result("paid_compatibility", PASS if ok else FAIL, expected,
                   {"source": source, "legacy": legacy_out, "current": current_out})


# --- the matrix ------------------------------------------------------------

CELLS = (
    ("missing_foundation", cell_missing_foundation),
    ("cast_bypass", cell_cast_bypass),
    ("scene_richness", cell_scene_richness),
    ("notion_migration", cell_notion_migration),
    ("identity_setting_change", cell_identity_setting_change),
    ("approval_ordering", cell_approval_ordering),
    ("style18", cell_style18),
    ("original_byte_preservation", cell_original_byte_preservation),
    ("paid_compatibility", cell_paid_compatibility),
)

#: Cells that accept an injected provider because the production module is owed
#: by another unit. S75-T17's migration module landed on main, so only the paid
#: compatibility module (S75-T28) is still owed; the migration cell drives real
#: production code and proves falsifiability by `broken=True`, like the rest.
PROVIDER_CELLS = ("paid_compatibility",)

#: The production module each provider cell is waiting for.
OWED_PATHS = {
    "paid_compatibility": (PAID_COMPATIBILITY_PATH,),
}

#: Cells that run against production code at any head.
RUNNABLE_CELLS = tuple(name for name, _ in CELLS if name not in PROVIDER_CELLS)


def blocked_cells(facet):
    """The provider cells whose owed module is genuinely absent for this facet.

    Presence on disk is an independent fact, so the test can assert the cell's
    BLOCKED status against it instead of assuming every provider cell is blocked
    forever. A cell whose dependency landed runs, and this returns it as absent
    from the blocked set.
    """
    return tuple(name for name in PROVIDER_CELLS
                 if not any(facet.has(p) for p in OWED_PATHS[name]))


def cell_ids():
    return tuple(name for name, _ in CELLS)


def run_cell(name, facet, broken=False, provider=None):
    for cell_name, fn in CELLS:
        if cell_name == name:
            return fn(facet, broken=broken, provider=provider)
    raise KeyError("unknown acceptance cell: %r" % (name,))


def repository_revision(repo=REPO_ROOT):
    """The exact commit the facet releases from, or UNAVAILABLE. No network."""
    try:
        out = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return "UNAVAILABLE"
    if out.returncode != 0:
        return "UNAVAILABLE"
    return out.stdout.strip() or "UNAVAILABLE"


def run_facet(flavor, broken=False, providers=None):
    """Run all nine checks for one flavor and return that facet's release record.

    Self-contained on purpose: nothing here reads the sibling flavor's record,
    so one facet's result cannot move the other facet's result.
    """
    providers = providers or {}
    facet = Facet(flavor)
    cells = [run_cell(name, facet, broken=broken, provider=providers.get(name))
             for name in cell_ids()]
    counts = {PASS: 0, FAIL: 0, BLOCKED: 0}
    for cell in cells:
        counts[cell["status"]] += 1
    layout_provisioned = facet.root_source == "package-anchor"
    return {
        "schema": RELEASE_SCHEMA,
        "facet": flavor,
        "repository": {
            "name": "openclaw-onboarding",
            "revision": repository_revision(),
            "package_anchor": facet.anchor,
            "root_source": facet.root_source,
            "package_layout_provisioned": layout_provisioned,
            "shared_core": not layout_provisioned,
            "release_file": "%s.json" % flavor,
        },
        "binding": facet.binding(),
        "cells": cells,
        "counts": {"total": len(cells), "pass": counts[PASS],
                   "fail": counts[FAIL], "blocked": counts[BLOCKED]},
        "release_status": PASS if counts[PASS] == len(cells) else (
            FAIL if counts[FAIL] else BLOCKED),
    }
