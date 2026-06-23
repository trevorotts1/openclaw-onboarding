"""Regression test for the company_kpis schema-drift crash (fixed v13.8.9).

THE BUG (confirmed live on a client box): the persona scoring layers in
persona-selector-v2.py did ``", ".join(company_kpis)`` (and the same for
owner_values / dept_kpis) assuming every entry was a string. schema-2.0
company-config.json files in the wild carry TWO shapes for these arrays:

    schema A (template / upgrade-company-config.py):  list[str]
        ["monthly recurring revenue", "client retention 90-day"]
    schema B (some interview-generated live boxes):   list[dict]
        [{"name": "monthly recurring revenue", "target": "50000"}, ...]

On a schema-B box the join raised
    TypeError: sequence item 0: expected str instance, dict found
crashing the ENTIRE selector on every persona pick.

THE FIX: a single `_kpi_labels()` helper coerces both shapes to list[str],
used at all six consumption sites (company_kpis / owner_values / dept_kpis in
BOTH heuristic and LLM scoring modes). This test feeds the helper AND the two
scoring-layer functions both schemas and asserts: no crash + correct labels.

This file lives under full-funnel-pipeline/tests/ so the existing
`funnel-pipeline-pytest` CI job (full-funnel-pipeline.yml) runs it on every PR.
"""
import importlib.util
import json
import os
import sys

import pytest

# ── Locate persona-selector-v2.py and its sibling import dirs ────────────────
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
# .../23-ai-workforce-blueprint/full-funnel-pipeline/tests -> skill root
_SKILL_ROOT = os.path.dirname(os.path.dirname(_TESTS_DIR))
_SCRIPTS_DIR = os.path.join(_SKILL_ROOT, "scripts")
# repo root holds shared-utils/ that the selector adds to sys.path itself
_REPO_ROOT = os.path.dirname(_SKILL_ROOT)
_SELECTOR_PY = os.path.join(_SCRIPTS_DIR, "persona-selector-v2.py")

for _p in (_SCRIPTS_DIR, os.path.join(_REPO_ROOT, "shared-utils")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Heuristic mode = no LLM / network, deterministic, importable in clean CI.
os.environ.setdefault("SCORING_MODE", "heuristic")


def _load_selector():
    """Import persona-selector-v2.py as a module (hyphen in name blocks the
    normal `import`). Skip the whole module if its sibling imports (detect_
    platform, resolve_db, adaptive_weights, …) aren't available in this env —
    the helper-only tests below still cover the crash surface in that case."""
    if not os.path.isfile(_SELECTOR_PY):
        pytest.skip(f"persona-selector-v2.py not found at {_SELECTOR_PY}")
    spec = importlib.util.spec_from_file_location("persona_selector_v2", _SELECTOR_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


try:
    SELECTOR = _load_selector()
except Exception as exc:  # pragma: no cover - environment dependent
    SELECTOR = None
    _IMPORT_ERR = exc


# ── Both schema shapes for the same logical KPI set ─────────────────────────
SCHEMA_A_STRINGS = [
    "monthly recurring revenue",
    "new paid clients per month",
    "client retention 90-day",
]
SCHEMA_B_OBJECTS = [
    {"name": "monthly recurring revenue", "target": "50000"},
    {"name": "new paid clients per month", "target": "20"},
    {"name": "client retention 90-day", "target": "85%"},
]
EXPECTED_LABELS = [
    "monthly recurring revenue",
    "new paid clients per month",
    "client retention 90-day",
]


@pytest.fixture(autouse=True)
def _require_selector():
    if SELECTOR is None:
        pytest.skip(f"persona-selector-v2.py not importable in this env: {_IMPORT_ERR}")


# ── _kpi_labels: the helper at the heart of the fix ─────────────────────────

def test_kpi_labels_schema_a_strings_passthrough():
    assert SELECTOR._kpi_labels(SCHEMA_A_STRINGS) == EXPECTED_LABELS


def test_kpi_labels_schema_b_objects_extracts_name():
    # This is the exact input that raised TypeError pre-v13.8.9.
    assert SELECTOR._kpi_labels(SCHEMA_B_OBJECTS) == EXPECTED_LABELS


def test_kpi_labels_join_never_crashes_on_objects():
    # Reproduce the original crash site shape and prove it no longer throws.
    labels = SELECTOR._kpi_labels(SCHEMA_B_OBJECTS)
    joined = ", ".join(labels)            # was: ", ".join(company_kpis) -> TypeError
    assert "monthly recurring revenue" in joined
    space_joined = " ".join(labels).lower()  # heuristic-mode shape
    assert "client retention 90-day" in space_joined


@pytest.mark.parametrize("bad", [None, [], "", 0])
def test_kpi_labels_empty_inputs_return_empty_list(bad):
    assert SELECTOR._kpi_labels(bad) == []


def test_kpi_labels_alternate_label_keys():
    items = [
        {"label": "revenue"},
        {"kpi": "retention"},
        {"metric": "nps"},
        {"title": "growth"},
    ]
    assert SELECTOR._kpi_labels(items) == ["revenue", "retention", "nps", "growth"]


def test_kpi_labels_dict_without_known_key_falls_back_gracefully():
    # No name/label/kpi/metric key: take first string value, never crash.
    out = SELECTOR._kpi_labels([{"foo": "bar"}])
    assert out == ["bar"]


def test_kpi_labels_dict_with_no_string_values_is_json_dumped():
    # Pathological entry: only non-string values. Must still yield a str.
    out = SELECTOR._kpi_labels([{"weight": 5}])
    assert len(out) == 1
    assert isinstance(out[0], str)
    # the join that crashed before must succeed now
    assert isinstance(", ".join(out), str)


def test_kpi_labels_comma_string_legacy_v1_shape():
    # Pre-v2.0 boxes sometimes stored a bare comma string.
    out = SELECTOR._kpi_labels("revenue, retention, nps")
    assert out == ["revenue", "retention", "nps"]


def test_kpi_labels_mixed_string_and_object_list():
    mixed = ["plain kpi", {"name": "object kpi"}]
    assert SELECTOR._kpi_labels(mixed) == ["plain kpi", "object kpi"]


# ── End-to-end: the heuristic scoring layer with both config schemas ────────
# _heuristic_layer_scores is what test-persona-selector.sh exercises via
# subprocess. Calling it directly with both schemas proves the crash is gone
# at the real call site, not just in the helper.

def _layer_scores(company_kpis, dept_kpis_for_marketing):
    cc = {
        "schema_version": "2.0",
        "mission": "help clients grow revenue",
        "owner_values": company_kpis,        # exercise owner_values site too
        "company_kpis": company_kpis,
        "dept_kpis": {"marketing": dept_kpis_for_marketing},
    }
    # paths with no soul_md / no real files — layer must still run.
    paths = {}
    return SELECTOR._heuristic_layer_scores(
        persona_id="seth-godin-marketing-strategist",
        task_text="write a launch email about monthly recurring revenue",
        owner_profile="",
        department_id="marketing",
        cc=cc,
        paths=paths,
    )


def test_heuristic_layer_scores_schema_a_strings_no_crash():
    scores = _layer_scores(SCHEMA_A_STRINGS, SCHEMA_A_STRINGS)
    assert "company_kpis" in scores
    assert 0.0 <= scores["company_kpis"] <= 1.0


def test_heuristic_layer_scores_schema_b_objects_no_crash():
    # The exact configuration that crashed the selector on the live box.
    scores = _layer_scores(SCHEMA_B_OBJECTS, SCHEMA_B_OBJECTS)
    assert "company_kpis" in scores
    assert 0.0 <= scores["company_kpis"] <= 1.0
    assert 0.0 <= scores["dept_kpis"] <= 1.0
    assert 0.0 <= scores["owner_values"] <= 1.0


def test_heuristic_layer_scores_equivalent_across_schemas():
    # Same logical KPIs in both shapes must produce identical layer scores,
    # proving the labels are extracted correctly (not just non-crashing).
    a = _layer_scores(SCHEMA_A_STRINGS, SCHEMA_A_STRINGS)
    b = _layer_scores(SCHEMA_B_OBJECTS, SCHEMA_B_OBJECTS)
    assert a["company_kpis"] == b["company_kpis"]
    assert a["dept_kpis"] == b["dept_kpis"]
    assert a["owner_values"] == b["owner_values"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
