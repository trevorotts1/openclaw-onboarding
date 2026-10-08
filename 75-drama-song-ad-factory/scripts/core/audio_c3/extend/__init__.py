"""audio_c3.extend: Suno extend-to-exact-length (BO-AUDIO2-U3). stdlib only.

A take short of the target length is topped up through the Suno extend route
to exact seconds (reference receipt: 282 s -> 300 s instrumental outro); a
take already long enough never calls extend. The timing map is contiguous
from 0.0 to the target. No transport lives here - the extend call is an
injected callable, so every test is mocked and every call is zero-spend.
"""
from .suno_extend import (  # noqa: F401
    DEFAULT_EXTEND_VERSION,
    EXIT,
    EXACT_TOL_S,
    EXTEND_CATALOG_ID,
    MAX_EXTEND_ROUNDS,
    MIN_PROGRESS_S,
    OVERLAP_S,
    SCHEMA_VERSION,
    TOOL_VERSION,
    ExtendError,
    build_extend_request,
    catalog,
    endpoint,
    plan_extend,
    route_model,
    timing_map,
    top_up,
    version_enum,
)

__all__ = [
    "DEFAULT_EXTEND_VERSION",
    "EXIT",
    "EXACT_TOL_S",
    "EXTEND_CATALOG_ID",
    "MAX_EXTEND_ROUNDS",
    "MIN_PROGRESS_S",
    "OVERLAP_S",
    "SCHEMA_VERSION",
    "TOOL_VERSION",
    "ExtendError",
    "build_extend_request",
    "catalog",
    "endpoint",
    "plan_extend",
    "route_model",
    "timing_map",
    "top_up",
    "version_enum",
]
