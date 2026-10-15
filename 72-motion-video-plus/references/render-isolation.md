# Render Isolation (MG-029)

Generated scene code and remote assets are untrusted inputs. This
document describes the isolation layer that keeps a render from
exposing provider credentials, reaching the network, escaping its job
directory, or taking unrelated processes down with it: what the code
did before this layer existed (from current-code inspection), the
controls that now exist, exactly how they are wired into the render
path, and the platform limits that remain, stated plainly.

The implementation lives in `runtime/src/isolation/`. The test suite
is `runtime/tests/run-security.ts` (wired into the runtime test chain
as `run-security`), with fixtures in `tests/fixtures/security/` and
its evidence record in `tests/evidence/mg029/measurements.json`.

## What existed before (inspected, not assumed)

- **Hyperframes adapter subprocesses** (`runtime/src/adapters/hyperframes.ts`,
  `runProcess`): spawned with checked argument arrays and no shell
  (good), but with the FULL host environment minus one deleted name
  (`GEMINI_API_KEY`). Every other provider secret in the host
  environment (the KIE and Fish Audio keys among them) was inherited
  by the engine CLI, the Chromium it launches, and ffmpeg. Children
  were tracked in an in-memory map only; cancellation sent SIGTERM to
  the CLI process alone, so a browser child could be orphaned by its
  parent's death, and nothing on disk recorded what had been launched.
- **Chromium cleanup** (`scripts/sweep-chromium.sh`): pattern-based.
  It killed any process whose command line contained both `--headless`
  and a marker string (default `mvplus`, the same for every run). It
  could not prove the processes it killed were the pipeline's, two
  concurrent runs shared the marker, and a process that merely
  carried the string in an argument was a target.
- **Remotion adapter**: renders in-process through the Node API; its
  Chromium inherits the host process environment as-is. There was no
  boundary description for how such a host process should be launched.
- **Asset preparation** (`scripts/prepare_assets.py`, MG-011):
  verified declared local files (existence, sha256, containment inside
  the job directory) but had no fetch discipline for URL-sourced
  assets and no controlled origin for serving staged assets; the
  contracts schema already forbids absolute, traversal, and URL asset
  paths in manifests.
- **Legacy scripts** (`scripts/render.js`, `scripts/preflight.js`):
  launch Chromium with `--no-sandbox`. That predates this item, sits
  outside the V2 adapter path, and is NOT changed by this item (the
  files are outside MG-029's claims). It is recorded here because a
  reader of this document should know the legacy pipeline's browser
  launches do not pass through this layer; operators who need the
  boundary on the legacy path should treat those launches as a known
  gap for a future item, not as covered.

## Threat model

A scene can contain arbitrary JavaScript and markup authored by an
agent or generated from untrusted material. The render must assume
the scene will try to: read its process environment and exfiltrate
what it finds; fetch local and remote URLs (SSRF against host
services, phone-home, asset substitution at render time); reference
files outside its job directory; pass shell-shaped strings anywhere a
shell might see them; and survive cancellation, leaving processes
behind. The operator's own browser and other jobs' renders are
bystanders that must never be harmed by a render or its cleanup.

Static lint (`runtime/src/lint`, MG-030) is NOT the security boundary
and this layer does not lean on it. Lint reads code and reports rule
violations; a scene that passes lint can still attempt every action
above at run time. The boundary is what running code can reach:
environment, network, filesystem, and process lifetime.

## The controls

### Environment (isolation/env.ts)

Render children receive an ALLOWLISTED environment, built by
`buildRenderEnv` from the host environment:

- Only named variables survive (path/locale plumbing, XDG locations,
  the runtime's `MOTION_*` configuration surface).
- Any secret-shaped name (matching `API_KEY`, `TOKEN`, `SECRET`,
  `PASSWORD`, `PRIVATE_KEY`, `CREDENTIAL`, `AUTH`, and similar) is
  refused even if allowlisted later; this covers the provider keys
  this pipeline uses without enumerating vendors.
- Non-secret vectors are refused by name: `NODE_OPTIONS` and
  `LD_PRELOAD`/`LD_LIBRARY_PATH` (code injection into the child) and
  the `*_PROXY` variables (a ready-made egress path; children make
  no network calls by design).
- The builder returns the NAMES withheld (never values) for evidence.
- The child also receives `MOTION_JOB_ID` and a per-job ownership
  token `MOTION_JOB_TOKEN`, inherited by all descendants; this token
  is how process ownership is proven later. The token is an
  attribution label, not a credential: it grants nothing, and its
  visibility to the job's own processes is by design.

Captured child output is secret-redacted before it is stored as a log
or evidence (`redactSecrets`): exact host secret values first, then
labeled assignments, bearer tokens, and well-known provider key
shapes. Benign content is preserved byte-for-byte (a bare sha256
digest matches no pattern and survives). Redaction is defense in
depth for logs; the primary control is that children never receive
the values.

### Process ownership (isolation/processes.ts) and the sweep

Every child launched through this layer is recorded BEFORE it can do
work in a per-job registry file: job id, ownership token, role,
binary, secret-redacted argument array, pid, process group, and the
pid's kernel start-time ticks from `/proc/<pid>/stat`. The registry
directory defaults to `~/.local/state/motion-render/processes`
(`MOTION_PROCESS_REGISTRY_DIR` overrides) and persists across the
launching process's death, which is what makes orphan attribution
possible.

Termination (`terminateJobProcesses`, used by adapter cancellation)
signals a process only when ownership is proven AT SIGNAL TIME:

- a recorded pid whose current start-time still equals the recorded
  start-time (a recycled pid fails and is left running, reported as
  refused), or
- a live pid whose `/proc/<pid>/environ` carries the job's token
  (descendants: browser children of a dead engine process).

SIGTERM first, a grace period, then SIGKILL, with identity re-verified
immediately before SIGKILL. The caller's own process group is never
signaled. Anything unverifiable is left running and reported; PID
numbers and command-line text are never trusted alone.

`scripts/sweep-chromium.sh` keeps its path and its end-of-run role
and nothing else: it now reads the same registry files (an embedded
Python implements the identical verification rules; the format is the
contract between the two) and terminates only recorded, verified
processes. Its old marker argument is accepted and ignored with a
printed notice. A Chromium the runtime did not launch (the operator's
browser, another tool's browser, another job's browser under a
different job record) is invisible to it.

### Network (isolation/network.ts)

Render-time network restriction is a Linux network namespace per
render process tree, created with `unshare(1)`; the render command is
the namespace's init command and everything it spawns inherits it.

- `loopback`: the namespace loopback is raised. Processes can reach
  each other on 127.0.0.1 inside the namespace (browser control
  channels, local helper servers) and nothing else: no route exists
  to the LAN, the internet, or the host's own loopback services,
  which live in a different namespace.
- `deny`: loopback stays down; no IP traffic at all. For pure
  file-and-pipe tools.
- `off` (default today): no namespace. Existing behavior is
  unchanged until a deployment sets a policy.

Flavor: as root, `unshare -n` (caller's user namespace untouched, so
Chromium sandboxing is unaffected). Unprivileged callers fall back to
`unshare -rn`; see limits below. Support is probed once per process
(`probeNetworkNamespace`), including an actual loopback raise.

Fail closed: the policy is requested through `MOTION_RENDER_NETWORK`
or per call; an unrecognized value is an error, and a requested
policy this machine cannot enforce throws
`NETWORK_ISOLATION_UNAVAILABLE` and the launch is refused. Running
unrestricted while claiming a policy would be worse than not running.

### Assets (isolation/paths.ts, isolation/assets.ts)

Reference validation (`validateAssetRef`) runs before the filesystem
is touched for content, and refuses with named rule codes:
`ASSET_REF_TRAVERSAL` (`..` segments, including percent-encoded),
`ASSET_REF_ABSOLUTE` (POSIX absolute, Windows drive),
`ASSET_REF_EXTERNAL` (any URL scheme, protocol-relative, `file:`,
`data:`), `ASSET_REF_BACKSLASH`, `ASSET_REF_NULL_BYTE`,
`ASSET_REF_ESCAPE` (resolves outside the job after symlink
resolution), `ASSET_REF_MISSING`, `ASSET_REF_EMPTY`. Findings carry
category `MG_SECURITY_VIOLATION` for hostile shapes and
`MG_SCHEMA_INVALID` for plain contract problems, matching the
preparation layer's vocabulary.

Fetching happens at preparation time only, through
`fetchApprovedAsset`: the caller supplies the sha256 recorded for the
asset at intake, and only bytes hashing to it are staged; anything
else is refused (`ASSET_HASH_MISMATCH`) and stages nothing. Fetch
policy: https only, except http to a loopback host (local intake
tooling); redirects are checked hop by hop against the same policy;
a byte cap bounds the download; the staged file lands atomically
under a single safe path segment.

Staged assets are served to renders through `AssetOriginServer`, a
static file server bound to 127.0.0.1 only. It serves nothing outside
the staging root: lexical traversal and symlink escapes are refused
(403) and every request, served or refused, is in its request log. It
never fetches anything itself. Renders addressing assets by URL use
this origin and no other; the adapters' local-file flow continues to
copy verified files into the generated project as before.

### Job directories and the launcher

`createJobWorkDir` gives each job its own writable set (root, tmp,
home, cache, assets staging) named by job and token; the launcher
points the child's `HOME`, `TMPDIR`, and `XDG_CACHE_HOME` there, so
browser profiles and caches stay inside the job's boundary. The
Hyperframes adapter honors `MOTION_JOB_WORK_ROOT` by giving each
child a job-specific `TMPDIR`.

`runtime/src/isolation/launch.ts` (compiled to
`dist/isolation/launch.js`) runs any command under the full boundary:

    node dist/isolation/launch.js --job <jobId> [--network off|loopback|deny]
        [--work-root <dir>] [--registry-dir <dir>] -- <bin> [args...]

This is how in-process engines get the same boundary the subprocess
engines get in the adapters: launch the engine's host process through
the launcher and the host, and the browsers it spawns, inherit the
scrubbed environment, the work directories, the namespace, and the
registry record. SIGINT/SIGTERM to the launcher terminate the job's
recorded processes, and a JSON evidence line (job, pid, policy,
withheld environment NAMES) goes to stderr at exit.

### Adapter wiring

In `runtime/src/adapters/hyperframes.ts`, at the launch and cleanup
attach points only (render semantics, preview behavior, and the
dispatcher's gate are untouched, per MG-024/MG-025 ownership):

- `runProcess` builds every child environment through
  `buildRenderEnv` (with the engine's own control flags applied
  after), wraps the command in the network namespace when
  `MOTION_RENDER_NETWORK` requests a policy, spawns detached, records
  the child in the registry, redacts captured output (stdout: exact
  values only, since it carries JSON reports; stderr: full patterns),
  and kills the child's process GROUP on timeout.
- `cancel` signals process groups and then runs the registry
  termination as a backstop for token-carrying descendants.
- Asset references in `assetFindings`/`copyAsset` pass through
  `validateAssetRef`; a hostile reference fails validation with its
  rule code named, and copies use the validated resolved path.

The Remotion adapter renders in-process, so it has no subprocess
attach point for environment or network; its boundary is the
launcher's, above. The dispatcher (`dispatch.ts`) is unchanged.

## Platform limits, honestly

- **Linux only.** The identity proofs read `/proc`; the namespace
  mechanism is `unshare`. On a platform without them the probe
  reports unsupported and requested policies fail closed.
- **Root vs user namespaces.** This machine runs the runtime as
  root, so `unshare -n` is used and Chromium's own sandbox is
  untouched. On an unprivileged host the `-rn` flavor maps the
  caller to root inside a user namespace; inside such a namespace a
  Chromium sandbox that relies on setuid helpers or unprivileged
  namespace nesting may not initialize. This layer does NOT disable
  browser or OS security anywhere to compensate: where a deployment
  needs the user-namespace flavor, the container image must provide
  a working browser sandbox story (for example a setuid sandbox
  helper), and that is a documented deployment requirement, not
  something the render path silently works around.
- **The namespace is not a filesystem sandbox.** A namespaced render
  still sees the host filesystem (job containment comes from the
  asset validation, preparation discipline, and job directories).
  Mount-namespace or container confinement is a deployment layer
  above this one.
- **Ownership proof assumes cooperating processes.** Start-time and
  environ-token proofs attribute processes among the runtime's own
  jobs on a shared machine. A malicious process running as the same
  user is outside this model (it could read `/proc` itself); the
  boundary against the SCENE is the namespace, the scrubbed
  environment, and filesystem containment, and same-user attackers
  are a host-security concern, not a render concern.
- **The policy default is off.** `MOTION_RENDER_NETWORK` defaults to
  `off` so this item changed no existing render behavior; the
  mechanism is proven by test with the policy on, and turning it on
  for production renders is a deployment decision this document
  recommends (`loopback` for engine renders, `deny` for pure media
  tools). Until a deployment sets it, renders run with the scrubbed
  environment, registry, and redaction, but without the namespace.
- **Redaction is best-effort.** It covers exact host values and the
  secret shapes this pipeline is known to print. A program that
  encodes a secret before printing defeats pattern redaction; it
  cannot print what it never received, which is why the environment
  scrub is the primary control.

## Evidence

`runtime/tests/run-security.ts` proves, against the real machine:
secret plants reaching a control child but never an isolated one;
redaction of planted values and key shapes with benign content
intact; the asset-reference refusal table; hash-pinned preparation
fetch and origin refusals; cancellation killing exactly one job's
tree while a second job and an unrelated Chromium survive; a stale
record refused; the sweep script cleaning the remaining recorded job
and still sparing the unrelated Chromium; a Node child and the real
Chromium scene failing to reach a host-loopback recorder or the
sandbox egress endpoint inside the namespace while reaching them
outside it; a real Hyperframes still rendering under the loopback
policy with every child recorded and no planted secret in the
records; and shell-shaped copy arriving byte-identical as an
argument and rendering as page text without executing. Results are
recorded in `tests/evidence/mg029/measurements.json`.
