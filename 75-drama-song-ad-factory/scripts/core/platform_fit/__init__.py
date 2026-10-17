"""Platform fit: researched platform specs with a re-verify clock, plus the
delivered-file checker that answers PASS / FLAG / UNDETERMINED / NOT_AVAILABLE
for them (SPEC B3 and B3a; method 8.2 and Step 17)."""
from .platform_fit import (  # noqa: F401
    ASPECT_TOLERANCE_PCT, DEFAULT_REVERIFY_DAYS, FLAG, NOT_AVAILABLE, PASS,
    ROW_FIELDS, SPECS_PATH, STALE_SPEC, UNDETERMINED, UNDETERMINED_SPEC,
    UNKNOWN_PLACEMENT, check, evaluate, fits, load_specs, probe_file, row_for,
)
