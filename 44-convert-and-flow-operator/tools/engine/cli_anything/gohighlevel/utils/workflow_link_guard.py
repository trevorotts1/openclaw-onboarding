"""Guard shared by the deploy scripts: refuse an unwired branch graph."""
from cli_anything.gohighlevel.utils import workflow_builder


def link_steps_or_refuse(templates):
    """Link steps, refusing a graph whose branch nodes have no authored targets."""
    linked, unlinked = workflow_builder.link_steps(templates)
    if unlinked:
        raise SystemExit(
            "Error: branch node(s) " + ", ".join(str(node) for node in unlinked)
            + " have no authored branch targets - refusing to build a graph "
              "whose conditions cannot be wired."
        )
    return linked
