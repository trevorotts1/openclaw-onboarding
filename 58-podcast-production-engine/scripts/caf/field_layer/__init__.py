#!/usr/bin/env python3
"""
Convert and Flow field layer for the Podcast Production Engine.

Public surface:
  resolver.resolve_credentials   - ENV-CHECK-BEFORE-FAIL (PIT + Location ID)
  field_map.get_or_build_field_map - cached field-key to field-id map
  writer.write_link_back         - batch-then-URL-last write + read-back verify
  writer.verify_read_back        - byte-for-byte read-back on its own

Data plane is Skill 44 caf (Tier 0) plus Skill 29 REST (Tier 3) ONLY. No Model
Context Protocol path exists here by construction (design Section 1). Client
visible name is always Convert and Flow.
"""
from __future__ import annotations

__all__ = [
    "constants",
    "redact",
    "state",
    "resolver",
    "transport",
    "field_map",
    "writer",
]
