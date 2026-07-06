"""Executable-specification oracle for the Podcast Production Engine inbound webhook layer.

This package is NOT the production mapper. The production mapper, job-key module,
and intake ledger are owned by the webhook-layer slice (W1.16) and ship under
58-podcast-production-engine/scripts/webhook/. This package encodes the same
contract, derived line-by-line from design/webhook-design.md Sections 3 and 4, so
that the independent unit tests in this directory are self-verifying and provable
on any branch (including this one, before the production mapper is merged in).

When the production mapper is present and bound (see conftest.py and README.md),
these same tests run against it instead, which is the independent-check role this
slice exists to serve. If the production mapper diverges from the contract encoded
here, the tests fail, which is exactly the intent.

Contract surface exposed by this oracle (the interface the tests target):
  map_payload(raw, tenant_location_id, aliases=None, style_transparency_slot=None)
      -> MappingResult
  compute_job_key(canonical) -> str
  Ledger(base_dir)           -> ledger object (claim / read / touch_duplicate / count)
  intake(raw, tenant_location_id, ledger, on_accept=None, ...) -> dict
"""

from .job_key import compute_job_key, HASH_FIELDS, canonical_submission
from .mapper import map_payload, MappingResult
from .ledger import Ledger
from .intake import intake

__all__ = [
    "compute_job_key",
    "HASH_FIELDS",
    "canonical_submission",
    "map_payload",
    "MappingResult",
    "Ledger",
    "intake",
]
