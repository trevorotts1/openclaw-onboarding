"""Pytest config for the full-funnel pipeline suite.

The harness drives the REAL persona-selector-v2.py subprocess (P1 + P4), which
takes ~45-120s and needs a persona corpus on disk. For the OFFLINE unit suite we
set FUNNEL_HARNESS_SKIP_SELECTOR=1 so the harness skips that subprocess and the
tests run fast and network-free. The persona-grounding ASSERTION still fires
(the gate reads the selection-log + persona-index), and the CI
`rubric-scorecard-gate` job runs the harness WITHOUT this flag, so the real
selector is still exercised end-to-end in CI.
"""
import os


def pytest_configure(config):
    os.environ.setdefault("FUNNEL_HARNESS_SKIP_SELECTOR", "1")
