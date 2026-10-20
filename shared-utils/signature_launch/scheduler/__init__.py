"""Signature Launch swarm scheduler (WF-SWARM lane).

Reads a launch plan (shared-utils/signature_launch_contract/launch-plan.schema.json)
and turns `waits_for` into waves of units that may start together.
"""
