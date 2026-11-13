"""test_pd_runfacts_315_canonical_paths.py -- PD-315 acceptance (A1).

PD-315: ONE path table, used by the sealed record.

  A1-sealed    the sealed record finds every one of the ten bundle keys when
               each sits at its CANONICAL_PATHS location.
  A1-legacy    infographic_png is NOT found when its only file is the legacy
               working/delivery/infographic.png -- no producer writes that path
               (build_infographic.py writes working/deliverables/infographic.png).
  A1-registry  verifier_registry.slice3_verifiers()'s "deliverables:bundle"
               artifacts tuple equals the CANONICAL_PATHS globs, in table order.
  A1-derived   mutating one CANONICAL_PATHS entry moves BOTH lists with it --
               proving each is derived from the table, not a second hardcoded
               copy. This is the half that fails if either list is a literal.

No network, no credentials. Stdlib + pytest/tmp_path only.
"""
import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
for _p in (SCRIPTS, SCRIPTS / "presentation_job"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from presentation_job import deliverable_paths as dp  # noqa: E402
from presentation_job import runfacts as rf  # noqa: E402
import verifier_registry  # noqa: E402


def _canon_globs():
    """The canon table with the {deck_slug} template expanded to a glob."""
    return {k: v.replace("{deck_slug}", "*") for k, v in dp.CANONICAL_PATHS.items()}


def _bundle_spec():
    return next(s for s in verifier_registry.slice3_verifiers()
                if s.gate == "deliverables:bundle")


def test_a1_sealed_finds_every_canonical_key(tmp_path):
    rd = tmp_path / "run"
    for rel in _canon_globs().values():
        p = rd / rel.replace("*", "demo")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    fact = rf._deliverables_fact(rd)
    found = {d.key for d in fact.value if d.found}
    assert found == set(_canon_globs()), (found, set(_canon_globs()))


def test_a1_sealed_rejects_legacy_delivery_infographic(tmp_path):
    rd = tmp_path / "run"
    legacy = rd / "working" / "delivery" / "infographic.png"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(b"x")
    fact = rf._deliverables_fact(rd)
    by_key = {d.key: d for d in fact.value}
    assert not by_key["infographic_png"].found


def test_a1_registry_tuple_is_the_canon_table():
    spec = _bundle_spec()
    assert tuple(spec.artifacts) == tuple(_canon_globs().values())


def test_a1_both_lists_are_derived_from_the_table(monkeypatch):
    sentinel = "working/moved/infographic-SENTINEL.png"
    monkeypatch.setitem(dp.CANONICAL_PATHS, "infographic_png", sentinel)
    assert rf.deliverables_bundle_patterns()["infographic_png"] == sentinel
    assert sentinel in tuple(_bundle_spec().artifacts)
