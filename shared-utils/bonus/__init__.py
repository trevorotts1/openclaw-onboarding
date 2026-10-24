"""Bonus membership / access capability (Purple Billboard, R-13 / T-14).

The decision module is `access_capability`; it reports the honest capability
state of the optional bonus membership and the supported route, and it refuses
an unattended grant rather than inventing one.
"""

from . import access_capability  # noqa: F401

__all__ = ["access_capability"]
