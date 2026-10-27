"""Guards the template graph ledger: every graph valid, every prose template accounted for."""

import importlib.util
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parent
SCHEMA = BASE / "_schema"
LEDGER = SCHEMA / "prose-only.json"
MATCHER = BASE / "_matcher" / "buildable-templates.json"
EXCLUDED_NAMES = {"automation-build.schema.json", "text-sets.json"}
DOC_ONLY_MARKDOWN = {"README.md", "GHL-CAPABILITY-NOTE.md"}


def _checker():
    spec = importlib.util.spec_from_file_location("check_joins", SCHEMA / "check_joins.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def template_dirs():
    return sorted(p for p in BASE.iterdir() if p.is_dir() and not p.name.startswith("_"))


def template_documents():
    documents = {}
    for group in template_dirs():
        for path in sorted(group.glob("*.json")):
            if path.name in EXCLUDED_NAMES:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(document, dict) and ("id" in document or "name" in document):
                documents[path.relative_to(ROOT).as_posix()] = document
    return documents


def buildable(documents):
    return {key for key, document in documents.items() if document.get("build_graph")}


def ledger():
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def test_every_graph_passes_the_join_check():
    checker = _checker()
    documents = template_documents()
    graphs = {key: document for key, document in documents.items() if document.get("build_graph")}
    assert graphs
    for key, document in graphs.items():
        result = checker.inspect(ROOT / key, document)
        assert result is not None, key
        nodes, _joins, errors = result
        assert nodes > 0, key
        assert not errors, f"{key}: {'; '.join(errors)}"


def test_ledger_names_a_specific_missing_fact_per_template():
    documents = template_documents()
    data = ledger()
    entries = data["entries"]
    listed = [entry["path"] for entry in entries]

    assert data["count"] == len(entries)
    assert len(listed) == len(set(listed)), "duplicate paths in prose-only.json"
    assert not (set(listed) & buildable(documents)), "a buildable template is also listed prose-only"

    unaccounted = sorted(set(documents) - buildable(documents) - set(listed))
    assert not unaccounted, f"templates with no graph and no reason: {unaccounted}"

    for entry in entries:
        path = ROOT / entry["path"]
        assert path.is_file(), entry["path"]
        assert path.with_suffix(".md").is_file(), f"{entry['path']} has no prose sibling"
        missing = entry.get("missing", "")
        assert missing.strip(), f"{entry['path']}: empty reason"
        assert len(missing.split()) >= 5, f"{entry['path']}: reason is not specific"


def test_every_markdown_template_is_converted_or_recorded():
    documents = template_documents()
    listed = {entry["path"] for entry in ledger()["entries"]}
    known = buildable(documents) | listed
    markdown = [p for group in template_dirs() for p in sorted(group.glob("*.md"))]
    assert markdown
    for path in markdown:
        sibling = path.with_suffix(".json")
        if sibling.is_file():
            assert sibling.relative_to(ROOT).as_posix() in known, path
        else:
            assert path.name in DOC_ONLY_MARKDOWN, f"{path} is neither converted nor recorded"


def test_generated_summary_counts_match_disk():
    documents = template_documents()
    on_disk = buildable(documents)
    matcher = json.loads(MATCHER.read_text(encoding="utf-8"))
    assert matcher["count"] == len(matcher["templates"]), "buildable-templates.json count is stale"
    assert matcher["count"] == len(on_disk)
    recorded = {template["path"] for template in matcher["templates"]}
    expected = {f"{Path(key).parent.name}/{Path(key).name}" for key in on_disk}
    assert recorded == expected
