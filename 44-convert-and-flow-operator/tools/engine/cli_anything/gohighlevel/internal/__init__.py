"""cli_anything.gohighlevel.internal — public adapter surface.

The CLI and (refactored) workflow_builder import ONLY these names.
Nothing else reaches into transport / endpoints / contract directly.

adapter-design §3.
"""
from cli_anything.gohighlevel.internal.adapter_types import (
    AdapterResult,
    AdapterError,
    ProbeResult,
)
from cli_anything.gohighlevel.internal.adapter import InternalAdapter, get_adapter
from cli_anything.gohighlevel.internal.probe import run_contract_probe
from cli_anything.gohighlevel.internal.degrade import (
    is_write_disabled,
    disable_writes,
    clear_write_disable,
)
from cli_anything.gohighlevel.internal.guards import (
    data_dir,
    write_lock,
    snapshot_workflow,
    step_backoff,
)

__all__ = [
    # Types
    "AdapterResult",
    "AdapterError",
    "ProbeResult",
    # Adapter
    "InternalAdapter",
    "get_adapter",
    # Probe
    "run_contract_probe",
    # Degrade
    "is_write_disabled",
    "disable_writes",
    "clear_write_disable",
    # Guards
    "data_dir",
    "write_lock",
    "snapshot_workflow",
    "step_backoff",
]
