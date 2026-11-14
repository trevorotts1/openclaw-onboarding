"""The ONE list of priority-shift ship-gate item ids (PD-304).

The P-SHIFT-QC ship gate has one artifact, `working/qc/priority_shift_report.json`,
and three things that must agree on its shape: the dispatcher's output contract
(what the grading model is told to write), the step check that grades it
(`runfacts.verify_priority_shift`, reached through
`PHASE_VERIFIERS["P-SHIFT-QC"]`), and the renderer's own writer
(`build_deck._chk_priority_shift_ledger`). Keeping three hand-typed copies of the
id list is how a check and its contract drift apart, so the list lives HERE and
every consumer imports it.

PROVENANCE (PD-304, copied in this unit's own change): both constants were read
out of `build_deck._chk_priority_shift_ledger`, which today writes fifteen rows
through its local `add(item, ok, evidence)` helper -- `{"item": item, "pass":
..., "evidence": ...}` -- for ids `0_attention_is_the_no1_job` through
`14_one_promise_one_wow_one_demonstration`, in that order. That writer's own
docstring/error text still says "14-item"; the CODE writes fifteen (items 0-14).
Per decision D-41 the code's list wins: the ids below are every id the writer
writes, in the writer's order, and no doctrine text is changed by this unit.
`tests/test_pd_priority_shift_items.py` proves the copy still equals the writer's
own output, so this module cannot drift from the writer while the writer keeps
its own literal list; once PD-097 makes the writer import this tuple, that test
becomes a tautology by construction instead of a parity check.

Nothing here reads a file, a run dir or the environment: pure constants, so it is
safe to import from the dispatcher at engine start.
"""
from __future__ import annotations

from typing import Tuple

#: The row key that carries an item's id in each `items[]` row of
#: working/qc/priority_shift_report.json. Read out of the writer's `add()`:
#: `rows.append({"item": item, ...})`.
PRIORITY_SHIFT_ID_KEY = "item"

#: Every id `build_deck._chk_priority_shift_ledger` writes, in the order it
#: writes them (fifteen rows: item 0, the North Star, through item 14).
PRIORITY_SHIFT_ITEM_IDS: Tuple[str, ...] = (
    "0_attention_is_the_no1_job",
    "1_creation_mode_identified",
    "2_priority_stack_named",
    "3_priority_shift_engineered",
    "4_present_cost_exposed",
    "5_higher_priority_lever",
    "6_value_anchored_high",
    "7_urgency_scarcity",
    "8_ability_unblocked",
    "9_rerank_demanded",
    "10_trigger_fired",
    "11_proclamation_hedge_free",
    "12_peak_and_ending",
    "13_most_vivid_by_the_end",
    "14_one_promise_one_wow_one_demonstration",
)
