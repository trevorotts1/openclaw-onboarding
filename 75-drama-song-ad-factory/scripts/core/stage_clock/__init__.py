"""stage_clock package - row N-02 (clock), N-68 (overlap), N-96 (budget),
N-108 (overrun diagnosis). Backed by references/time-budgets.json."""
from .clock import StageClock, load_budgets, budget_for  # noqa: F401
