# STAGING NOTES — L1 events package (S44-owned repo home)

Staged: 2026-10-15 (EDT), packaging worker for the S44 room.
Staging dir mirrors the S44-owned repo path `shared-utils/signature_launch/events/`.
This is staging only: nothing was committed, pushed, or written anywhere else.

## Files placed

| File | Source | SHA-256 (as copied) |
|---|---|---|
| `events.py` | `rooms/S44/work/events/events.py` | `b155d3756dafcbee12b2643b880d586bbe42811ee25fbede7d53b9feeae15ac0` (pre-edit copy; staged file then received the SCHEMA_PATH change below) |
| `test_events.py` | `rooms/S44/work/events/test_events.py` | `f388e6fef6fa57eaab378efd3152a3c7433ea877f3423c2a5f4baf720d1f9f22` (unchanged) |
| `purchase-event.schema.json` | `packet/reference/schemas/purchase-event.schema.json` | `c346bbb539927dc109189fb6454bea0fe495eb52f668a632d01c6fc9e779fd20` (unchanged; matches PACKAGE_MANIFEST) |

Copies were verified byte-identical to their sources by SHA-256 before the one edit below. The source files under `work/events/` were not modified.

## The one change: SCHEMA_PATH resolution in staged `events.py`

The original resolves the schema through the packet tree (`parents[4] / "packet" / ...`), which does not exist in the repo layout. The staged copy prefers the vendored schema sitting next to the module and keeps the original packet expression as a fallback if the vendored file is absent.

Original lines:

```python
SCHEMA_PATH = (Path(__file__).resolve().parents[4]
               / "packet" / "reference" / "schemas" / "purchase-event.schema.json")
_SCHEMA = json.loads(SCHEMA_PATH.read_text())
```

Staged lines:

```python
# Packaged layout: the schema is vendored next to this module. Fall back to
# the packet path (room development layout) only if the vendored file is absent.
_VENDORED_SCHEMA_PATH = (Path(__file__).resolve().parent
                         / "purchase-event.schema.json")
_PACKET_SCHEMA_PATH = (Path(__file__).resolve().parents[4]
                       / "packet" / "reference" / "schemas"
                       / "purchase-event.schema.json")
SCHEMA_PATH = (_VENDORED_SCHEMA_PATH if _VENDORED_SCHEMA_PATH.exists()
               else _PACKET_SCHEMA_PATH)
_SCHEMA = json.loads(SCHEMA_PATH.read_text())
```

No other line of `events.py` differs from the source.

## Test result

Run from the staging directory: `python3 -m unittest test_events`

**17 passed / 0 failed (OK).**

An import probe confirms the staged module loads the vendored schema, not the fallback: `events.SCHEMA_PATH` resolves to `.../packaging/shared-utils/signature_launch/events/purchase-event.schema.json`. (From the staging location the packet fallback path does not exist, so a green run is only possible via the vendored file.)

## Reviewer notes

- This is the L1 reference implementation: deterministic, in-memory, test-only semantics. Its own header says so — it is NOT live proof of any GHL behavior, and the production replacements are the durable store / normalizer / processor modules designed in the S44 room.
- The schema vendored here is v1.0 (`schema_version` const `"1.0"`, no `contact_ref`). Under the S49 ruling on CR-S44-001, schema v1.1 (optional nullable `contact_ref`) lands in `shared-utils/signature_launch/domain/` on S49's draft PR #2137, with v1.0 preserved alongside. When that lands, this package's validator should be pointed at the domain v1.1 schema accepting both versions; no processor logic change is needed (contact_ref already travels in processing context).
- The fallback branch exists for the room development layout (`work/events/`), where no vendored schema sits next to the module and the packet tree does. In the repo layout the vendored file will always be present, so the fallback simply never fires.
- `test_events.py` inserts its own directory into `sys.path` and imports `events` as a top-level module; that is how it is run here and how it will run in the repo location.


## Successor — 2026-10-16: dual-version validator (schema v1.1 switch, CR-S44-001)

Successor commit on `s44/siglaunch-production-modules` (after
57556db), placed by S44 swarm lane G from the room's verified
work-layout builds (Lane B report section 4B). CR-S44-001's schema
v1.1 landed on main (7c3d4a2b) in
`shared-utils/signature_launch/domain/`; this package now accepts
BOTH versions.

### Files added or changed

| File | Source | SHA-256 (as placed) |
|---|---|---|
| `events.py` | `rooms/S44/work/events/events.py` (placed dual build) | `2c7fbb70042dc646afea29d338e7b2fb33fecc6eef1572ecb9e0fb57c8a7d2be` — one adaptation vs the source: the module header no longer carries the lane-phase "not landed anywhere" note; it records the dual-version build and this placement. No code line differs. |
| `purchase-event.v1.1.schema.json` | domain `purchase-event.schema.json` bytes (via the work-layout vendored copy) | `311d04820360193a892929e6cf12788372db85977caf1e1277a8f3024515806a` |
| `test_events_dual.py` | `rooms/S44/work/events/test_events_dual.py` | `28ad863b5a85382134661ed78329a928c0b5cf70eb382787822ec3be76b2d43f` — one adaptation vs the source (Lane B 4B.4): `DomainSiblingLayoutTests`' domain source repointed from the work-layout vendored `domain-src/` copy to the real repo sibling, `Path(__file__).parent.parent / "domain"`. Assertions untouched. |
| `purchase-event.schema.json` | unchanged (v1.0) | `c346bbb539927dc109189fb6454bea0fe495eb52f668a632d01c6fc9e779fd20` |
| `test_events.py` | unchanged | `f388e6fef6fa57eaab378efd3152a3c7433ea877f3423c2a5f4baf720d1f9f22` |

### How the dual registry resolves in this layout

Candidates in order: the vendored files beside the module, then the
sibling `domain/` directory (present once this branch merges onto
main, which carries it), then the packet fallback (room development
layout). Every file is registered under the version its own
`schema_version` const declares — in `domain/` the un-suffixed file
is v1.1; beside this module the un-suffixed file is v1.0.
`validate_event` dispatches on the event's stamped version and fails
closed on any other, missing, or non-string version, and on
non-object events. If no v1.0 schema is found anywhere, import fails
loudly; if v1.1 is absent, the module still loads and v1.1 events
fail closed with a named error.

### Test result

Branch layout (this branch does not yet carry `domain/`; it lands
via main): `test_events` **17/17 OK**; `test_events_dual` **25/26** —
the one error is `DomainSiblingLayoutTests`, a FileNotFoundError on
`shared-utils/signature_launch/domain/purchase-event.schema.json`,
an absent-main-side-directory error, not a code failure.
Post-merge layout harness (lane G scratch: this package beside the
real domain files, byte-verified `311d0482…` / `c346bbb5…`):
**43/43 OK** (17 original + 26 dual).


## Successor — 2026-10-16: import-depth guard fix (S44 swarm lane I)

Successor commit on `s44/siglaunch-production-modules` (after
3f2dd53). Fixes a latent import-time crash the S44 watchdog exposed:
the dual module's packet-fallback schema candidate was built with
`Path(__file__).resolve().parents[4]` UNGUARDED at import time. In
this layout the path is deep enough, so the defect stayed invisible
under the room's TMPDIR rule (temp copies land deep inside the
workspace); but whenever the module is copied to a shallow path —
fewer than 5 ancestors, e.g. a temp dir directly under /tmp, which a
default TMPDIR produces — import crashed with `IndexError` instead
of merely missing the fallback. The watchdog's L1 re-run without the
TMPDIR override scored the work-layout suites 42/43 with
`DomainSiblingLayoutTests` erroring on exactly this.

### The fix

Mirror of the coordinator's work-layout fix, byte-for-byte in the
code block: the packet fallback is appended to `_SCHEMA_CANDIDATES`
only when the module path is deep enough for the packet tree to be
an ancestor —

```python
_PARENTS = Path(__file__).resolve().parents
if len(_PARENTS) > 4:
    _SCHEMA_CANDIDATES.append(
        _PARENTS[4] / "packet" / "reference" / "schemas"
        / "purchase-event.schema.json")
```

— with an explanatory comment recording the watchdog find. No other
code line differs from 3f2dd53; the lane-G placement header is
untouched, and a full diff against the work-layout module shows the
header paragraph as the only remaining difference between the two
copies.

### Files added or changed

| File | Change | SHA-256 (as placed) |
|---|---|---|
| `events.py` | guarded packet-fallback construction (diff vs 3f2dd53: −2 lines, +12 lines, one hunk) | `ed814fa9be3dd975254911755ee8f8b90e415588244c1e7d98bbe280a0725fd6` |
| `test_events_dual.py` | NEW `ShallowPathImportTests` class (+26 lines, one test): copies the module and both vendored schemas into a temp dir directly under /tmp and asserts a clean import with both versions installed. Copied verbatim from the work layout; the only remaining difference between the two test files is the pre-existing `domain_src` adaptation (Lane B 4B.4). | `928f885d9e3e685ccf5964d7113f6f48459c2964ef2ce53b0a2bb252d17096e7` |
| `purchase-event.schema.json`, `purchase-event.v1.1.schema.json`, `test_events.py` | unchanged | `c346bbb5…fd20`, `311d0482…806a`, `f388e6fe…f22` |

### Test result (lane I, `python3 -m unittest discover` per package)

Branch layout, run TWICE — once under the room TMPDIR rule
(workspace scratch) and once with TMPDIR unset (default /tmp, the
shallow condition that exposed the defect). Identical results both
runs: `test_events` **17/17 OK**; `test_events_dual` **26/27** — the
one error remains `DomainSiblingLayoutTests`, a FileNotFoundError on
the absent `shared-utils/signature_launch/domain/` sibling (lands
via main), environmental and disclosed, NOT an IndexError. No
IndexError anywhere under either run; `ShallowPathImportTests`
passes in the branch layout under both TMPDIR conditions.
Post-merge layout harness (this package beside the real domain
files from current main, byte-verified `311d0482…` / `c346bbb5…`),
TMPDIR unset: **44/44 OK** (17 original + 27 dual).

---

## 2026-10-18 — schema v1.2 dual-acceptance placement (candidate s44/siglaunch-crs82003-v12)

Staged by the S44 room under MAIN's closure sequence (2026-10-18).
Source: `rooms/S44/work/events/`, copied byte-identical (hashes below
computed in-process at placement).

| File | Change | SHA-256 (as placed) |
|---|---|---|
| `events.py` | schema candidate list gains v1.2: the vendored `purchase-event.v1.2.schema.json` is registered by its own `schema_version` const ("1.2"), and validation dispatches across 1.0 / 1.1 / 1.2, fail-closed on any other version. `parent_order_ref` is acceptance-only at this layer: optional, version-scoped, never load-bearing, never stamped by the normalizer (producer stamping is the later CR-S44-003 step, gated on consumer acceptance). | `fdab91a07127298eb0e847704131cb357acab409e09a24730a63e57460fdbe7e` |
| `purchase-event.v1.2.schema.json` | NEW: vendored schema 1.2 as landed via PR #2190 (S49's C9 note). | `4f9e8122b2767d098ab980be9f33e4503bb1f9e3cc4f4bda17a3990e325378c0` |
| `test_events_dual.py` | dual/triple-version dispatch coverage updated for the 1.2 candidate. | `dd3dbfad0cc7c1194f85f7ab168a28c22300b62427794699b0249cca33ffc9b4` |
| `test_events_v12.py` | NEW: v1.2 acceptance suite (version-scoped `parent_order_ref`; acceptance only, no stamping). | `8a8b736a8a368f64f2105f8034bd9fdc7a6fcdb4bf97c9564b832a7c7f2600c5` |
| `purchase-event.schema.json`, `purchase-event.v1.1.schema.json`, `test_events.py` | unchanged | `c346bbb5…fd20`, `311d0482…806a`, `f388e6fe…f22` |

### Test result (`python3 -m unittest discover`, this package)

Run under BOTH TMPDIR conditions (room scratch TMPDIR and unset),
identical results each way:

- Work layout (`rooms/S44/work/events`): **63/63 OK**.
- Branch layout as placed: **62/63**, the one error being the known,
  previously disclosed `DomainSiblingLayoutTests` FileNotFoundError —
  the test copies its fixture schemas from a `domain-src/` directory
  that exists only in the room work layout (same environmental
  artifact, same disclosure, as the landed v1.1 successor).
- Post-merge layout harness (this package with `domain-src/` in
  place): **63/63 OK** under both TMPDIR conditions.
