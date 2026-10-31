# Installer ↔ plugin contract (CTR-127)

Two components, one runtime root. This document is the handshake between them.

## The single source of truth: `<prefix>/active.json`

`77-council-of-wise-elders/scripts/install-runtime.mjs` writes and atomically
re-points `<prefix>/active.json`. That file IS the activation pointer; rollback
re-points it. No second `current` symlink or pointer is added, because a second
pointer is one more thing that can disagree.

The plugin core reads it directly. `provision.mjs` validates the same record but
does **not** copy it into plugin config. An explicit `runtimeRoot` remains an
override for diagnosis only; a value that is not dependency-complete is refused,
never silently replaced.

## What the installer provides

`77-council-of-wise-elders/scripts/install-runtime.mjs`:

**1. `<prefix>/active.json` gains three fields** on every activation:

```json
{
  "releasePath": "/abs/path/releases/rel-<digest12>",
  "dependencyDigest": "<sha256 of the dependency closure payload>",
  "dependencyClosure": "static_metadata_only",
  "dependencyResolutionProven": false
}
```

**2. `<prefix>/receipts/<releaseId>.dependencies.json`** — new receipt:

```
schema       "wise-elders.council-runtime-dependencies/v1"
releaseId, createdAt, sourceManifestDigest
proof        "static_metadata_only"
dependencyResolutionProven  false
package      { name, version }
entries[]    { name, declaredRange, lockVersion, lockIntegrity, lockResolved,
               installedVersion, packageJsonSha256, moduleType, exportTargets,
               installScript }
closure[]    { path, sha256, size }   for dist/brief/permitted-brief.js,
                                      dist/contracts/index.js, dist/index.js
contractsFiles[] { path, sha256 }     every dist/contracts/*.js
importClosure { check: "static_text_and_file_existence",
                resolutionProven: false, entries: [...] }
digest       sha256 over {package, entries, closure, contractsFiles, importClosure}
```

What this proves: `package-lock.json` pins each production dependency with a
version and an integrity digest; the installed package's own `package.json`
reports that same version; every **literal** declared relative export target
exists on disk (subpath *patterns* such as zod's `./v4/locales/*` are not files
and are skipped, not reported missing);
the three runtime graph roots — the advertised package entry plus the plugin
bridge entries — and the contracts modules are present and hashed;
and the emitted module graph reachable from those roots is Node-ESM loadable —
every relative specifier carries an extension, every target exists inside the
release root, every bare specifier names a package installed under that root.
Modules no listed root reaches are outside this check; the claim is bounded to
these roots, never "every module in dist/".

`computeDependencyClosure` **throws** on any graph problem, so an unloadable
build is never activated, never receipted as complete, and never printed as
READY by `--print-runtime-root`.

What it does **not** prove, and must never be labelled as: that Node resolves
those specifiers at runtime. Nothing is imported, resolved or executed. The
observed `ERR_MODULE_NOT_FOUND zod` is caught earlier by construction (the
closure requires `node_modules/<dep>/package.json` inside the release root), but
the receipt is static evidence, not a runtime probe.

The emitted graph is fixed at its source, not papered over at load time: the
runtime's `src/contracts/*.ts` and `src/sources/*.ts` relative specifiers carry
explicit `.js` extensions, which TypeScript keeps verbatim in the emit. No
loader hook, transpiler, monkeypatch or hand-written schema copy exists in
either tree.

**3. `--print-runtime-root`** — a diagnostic source of an explicit plugin
`runtimeRoot`, when one is wanted:

```bash
node <skill-root>/scripts/install-runtime.mjs --prefix <prefix> --print-runtime-root
```

Prints JSON, exit `0` READY / `1` NOT_READY:

```json
{
  "status": "READY",
  "runtimeRoot": "<active.json releasePath>",
  "releaseId": "rel-…",
  "sourceManifestDigest": "…",
  "artifactDigest": "…",
  "dependencyDigest": "…",
  "productionDependencies": ["zod@4.4.3"],
  "dependencyClosure": "static_metadata_only",
  "dependencyResolutionProven": false,
  "receiptRecorded": true
}
```

NOT_READY codes: `COUNCIL_RUNTIME_NOT_ACTIVATED`,
`COUNCIL_RUNTIME_ACTIVE_UNREADABLE`, `COUNCIL_RUNTIME_ACTIVE_NO_RELEASE_PATH`,
`COUNCIL_RUNTIME_RELEASE_MISSING`, `COUNCIL_RUNTIME_CLOSURE_INCOMPLETE`,
`COUNCIL_RUNTIME_DEPENDENCY_DRIFT`, `COUNCIL_RUNTIME_DEPENDENCY_RECEIPT_UNREADABLE`.

**4. `verifyRelease`** now checks the dependency receipt by default. Rollback to a
release that predates the receipt passes `dependencies: "skip"` and prints `WARN
rollback: … dependency closure is UNVERIFIED`. Never `verified` for a skipped
check.

## What the plugin core requires

`lib/core.mjs` resolves the root in this order, with no fallback:

1. explicit `runtimeRoot`, only if dependency-complete;
2. else `<prefix>/active.json` derived from `councilAskPath`
   (`<prefix>/bin/council-ask`), with `releasePath` realpath inside
   `<prefix>/releases`, basename equal to `releaseId`, `receiptPath` realpath
   inside `<prefix>/receipts`, and receipt `releaseId` / digest agreement;
3. else a typed `COUNCIL_RUNTIME_UNRESOLVED` naming the record it could not use.

Before any import it requires the advertised package entry `dist/index.js`,
`dist/brief/permitted-brief.js`, `dist/contracts/index.js`,
`dist/contracts/schemas.js`, `node_modules/zod/package.json` at the runtime's
exact pin, an existing zod ESM import target, and a statically loadable emitted
graph for those three roots: the same relative-import closure the installer
enforces. zod itself is fetched by the installer's `npm ci` from the lockfile's
integrity-pinned registry entry; neither the `.skill` archive nor the plugin
tarball vendors it, so installation needs network access. The checks are static
file evidence, never runtime resolution.
It never imports a dependency-less or extensionless tree, because OpenClaw's
capture would copy an unloadable runtime and keep every digest green.

The dynamic import target is an absolute file URL computed from `active.json`,
so OpenClaw's package capture does not rewrite it (`URL.canParse` specifiers are
skipped by the capture lookup); the release is loaded from its real path with
its own `node_modules` beside it. That is why the release graph, not the plugin
bundle, has to be loadable by plain Node ESM.

## File ownership in `extensions/council-before-dispatch/`

| file | source of truth |
| --- | --- |
| `index.js`, `index.ts`, `lib/core.mjs`, `test/` | plugin core |
| `openclaw.plugin.json` | plugin core (config schema follows the core) |
| `package.json` | packaging identity only |
| `provision.mjs` | per-box identity derivation; writes nothing |
| `install/plugins-entry.example.json` | placeholders only, no ids |
| `INSTALL.md`, `CONTRACT.md` | this contract |
| `fixtures/` | unexecuted input samples |

## Invariants (must not change)

`channel`, `mode`, `displayTimezone` semantics, `timeoutMs` floor, `senderIds`
authorization, `conversationId`/`accountId`/`agentId` binding, brief contents, the
original question text, the provider/route choice, and claim/state files. No
credential, provider, model or auth-boundary change anywhere.
