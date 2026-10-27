"""Runtime adapters for supported Mac, VPS and Docker hosts (Purple Billboard T-38).

Three small modules, no framework:

  host.py         Detected host facts -> mac / vps / docker adapter, or an
                  explicit refusal. A browser is never assumed and never
                  required. Restart persistence is declared and stays
                  UNVERIFIED until a real registration read-back is supplied.
  external.py     The verified external storage contract: mount identity,
                  resolved destinations, symlink/internal/escape rejection,
                  a no-follow destination handle with a pre-write device/inode
                  recheck, no-replacement publication, and a real child
                  TMPDIR/TMP/TEMP propagation probe with tool-specific cache
                  and output options.
  persistence.py  Restart persistence that reuses the accepted T-12 durable
                  store and reconciliation sweep; engineering teardown can
                  never dispose of durable customer runtime or unknown effects.

Stdlib only. Public entry points::

    from runtime.host import detect_host, adapter_for, browser_capability
    from runtime.external import resolve_destinations, verify_mount, probe_child
    from runtime.persistence import RestartLedger, teardown

There is deliberately no internal fallback anywhere in this package: a missing
mount, an unmapped device, an unverified media identity or an unsupported host
raises a named error instead of quietly writing to /tmp, the internal disk or
an anonymous container volume.
"""

from .external import (  # noqa: F401
    CapacityError,
    ChildProbe,
    Destination,
    DestinationHandle,
    MissingMount,
    MountIdentity,
    PathRejected,
    PropagationError,
    ReboundDestination,
    StorageError,
    UnsupportedTool,
    assert_external,
    open_destination,
    probe_child,
    resolve_destinations,
    temp_env,
    tool_output_options,
    verify_mount,
)
from .host import (  # noqa: F401
    BROWSER_ABSENT,
    BROWSER_AVAILABLE,
    BROWSER_NOT_ASSUMED,
    RUNTIME_DOCKER,
    RUNTIME_MAC,
    RUNTIME_VPS,
    SUPPORTED_RUNTIMES,
    BindingRefused,
    Capabilities,
    DockerAdapter,
    HostFacts,
    MacAdapter,
    PersistencePlan,
    UnsupportedHost,
    VpsAdapter,
    adapter_for,
    browser_capability,
    classify_runtime,
    detect_host,
    verify_persistence,
)
from .persistence import (  # noqa: F401
    CLIENT_RUNTIME,
    DURABLE_STATE,
    ENGINEERING_PROCESS,
    ENGINEERING_TEMP,
    HostRebound,
    RestartLedger,
    ReuseUnavailable,
    TeardownRefused,
    TeardownReport,
    teardown,
)

__all__ = [
    "RUNTIME_MAC", "RUNTIME_VPS", "RUNTIME_DOCKER", "SUPPORTED_RUNTIMES",
    "BROWSER_NOT_ASSUMED", "BROWSER_AVAILABLE", "BROWSER_ABSENT",
    "HostFacts", "Capabilities", "PersistencePlan", "MacAdapter", "VpsAdapter",
    "DockerAdapter", "adapter_for", "classify_runtime", "detect_host",
    "browser_capability", "verify_persistence", "UnsupportedHost",
    "BindingRefused",
    "MountIdentity", "Destination", "DestinationHandle", "ChildProbe",
    "StorageError", "MissingMount", "PathRejected", "CapacityError",
    "ReboundDestination", "PropagationError", "UnsupportedTool",
    "verify_mount", "resolve_destinations", "assert_external",
    "open_destination", "temp_env", "probe_child", "tool_output_options",
    "RestartLedger", "teardown", "TeardownReport", "HostRebound",
    "ReuseUnavailable", "TeardownRefused", "ENGINEERING_TEMP",
    "ENGINEERING_PROCESS", "CLIENT_RUNTIME", "DURABLE_STATE",
]
