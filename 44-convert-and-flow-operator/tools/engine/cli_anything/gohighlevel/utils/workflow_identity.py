"""Pre-write workflow graph identity validation."""
from collections.abc import Mapping
import importlib.util
from pathlib import Path

_IDENTITY_FN = None
_IDENTITY_LOADED = False


def _identity_fn():
    """Load and cache validate_graph.identity_failures, or None if unavailable."""
    global _IDENTITY_FN, _IDENTITY_LOADED

    if _IDENTITY_LOADED:
        return _IDENTITY_FN

    _IDENTITY_LOADED = True
    source = Path(__file__).resolve()

    try:
        for parent in [source] + list(source.parents):
            for candidate in (
                parent / "tools" / "validate_graph.py",
                parent / "validate_graph.py",
            ):
                if not candidate.is_file():
                    continue

                spec = importlib.util.spec_from_file_location(
                    "caf_validate_graph_identity", str(candidate)
                )
                if spec is None or spec.loader is None:
                    return None

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                _IDENTITY_FN = getattr(module, "identity_failures", None)
                return _IDENTITY_FN
    except (OSError, ImportError, AttributeError):
        return None

    return None


def plan_identity_refusals(campaign):
    """Return pre-write refusal tuples for structurally unsafe workflow plans."""
    from cli_anything.gohighlevel.utils.workflow_builder import link_steps

    refusals = []
    identity_fn = _identity_fn()

    for key, wf_def in campaign.items():
        if not isinstance(wf_def, Mapping):
            continue

        name = wf_def.get("name") or key
        templates = wf_def.get("templates")

        if templates is None:
            templates = []
        elif not isinstance(templates, list):
            refusals.append((
                key, None, False, False, None,
                f"{name}: 'templates' must be a list - refusing to build.",
            ))
            continue

        linked, unlinked = link_steps(templates)

        if unlinked:
            refusals.append((
                key, None, False, False, None,
                f"{name}: branch node(s) {', '.join(unlinked)} have no authored branch targets - refusing to build a graph whose conditions cannot be wired. Author next/branches on each branch node in the plan.",
            ))

        if identity_fn is None:
            refusals.append((
                key, None, False, False, None,
                f"{name}: graph identity validator tools/validate_graph.py is absent - refusing to write a workflow whose graph cannot be validated.",
            ))
            continue

        for failure in identity_fn(linked):
            kind = failure.get("kind")

            if kind == "DUPLICATE_ID":
                ids = ", ".join(str(value) for value in failure.get("ids", []))
                reason = (
                    f"{name}: duplicate node id(s) {ids} - refusing to build; "
                    "every node id must be unique."
                )
            elif kind == "ID_MISSING":
                reason = f"{name}: a node has no id - refusing to build."
            elif kind == "DANGLING":
                reason = (
                    f"{name}: node {failure.get('node_id')} field "
                    f"{failure.get('field')} targets missing id "
                    f"{failure.get('target')} - refusing to build."
                )
            elif kind == "MALFORMED_BRANCH":
                reason = (
                    f"{name}: if_else node {failure.get('node_id')} must have "
                    "a branches map of exactly two distinct existing ids - "
                    "refusing to build."
                )
            elif kind == "ROOT":
                roots = failure.get("roots", [])
                reason = (
                    f"{name}: expected exactly one root node (parentKey null); "
                    f"found {roots} - refusing to build."
                )
            elif kind == "PARENT_INVALID":
                reason = (
                    f"{name}: node {failure.get('node_id')} parentKey "
                    f"{failure.get('parentKey')} does not exist - refusing to build."
                )
            elif kind == "PARENT_CYCLE":
                reason = (
                    f"{name}: parent cycle {failure.get('cycle')} - refusing to build."
                )
            else:
                reason = (
                    f"{name}: graph identity validation failed for kind "
                    f"{kind!r} - refusing to build."
                )

            refusals.append((key, None, False, False, None, reason))

    return refusals
