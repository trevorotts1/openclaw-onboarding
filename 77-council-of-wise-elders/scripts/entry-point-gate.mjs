#!/usr/bin/env node
// Council of Wise Elders: entry-point gate (installer truth rule).
//
// The packaging/install verifier must verify the ACTUAL executable it
// ships: byte hash against the recorded build plus a real load. It must
// fail VISIBLY with an actionable error when the build is failed or
// missing, never declare 'ready' from SKILL.md or source presence, and
// never silently reuse an old bundle.
//
// The recorded build lives in manifest.json as `runtime_entry`
// ({path, sha256, bytes}), written by scripts/build-bundles.mjs at
// packaging time. scripts/build-bundles.mjs and scripts/verify-bundles.mjs
// both gate through this module, so there is one truth rule.
//
// ponytail: only the CLI entry (package.json `bin`) is hash+load gated;
// add a full dist artifact receipt when a failure shows the rest of
// dist/ needs its own gate (install-runtime.mjs already receipts dist/).
//
// Usage (module): checkEntryPoint(root, manifest) -> {ok, problems, entry}

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

export const ENTRY_PATH = "runtime/dist/blackceo-council.mjs";

const REBUILD =
  "build it with `npm ci --no-audit --no-fund && npm run build` in runtime/, " +
  "then repackage with `node scripts/build-bundles.mjs`";

/** Read and load-check the on-disk entry point. */
export function readEntryPoint(root, { load = true } = {}) {
  const abs = join(root, ENTRY_PATH);
  if (!existsSync(abs)) {
    return {
      ok: false,
      problems: [`entry point missing: ${ENTRY_PATH} — the package has no built executable; ${REBUILD}`],
      entry: null,
    };
  }
  let st;
  try {
    st = statSync(abs);
  } catch (error) {
    return {
      ok: false,
      problems: [`entry point unreadable: ${ENTRY_PATH}: ${String(error.message).split("\n")[0]}; ${REBUILD}`],
      entry: null,
    };
  }
  if (!st.isFile()) {
    return {
      ok: false,
      problems: [`entry point is not a regular file: ${ENTRY_PATH} is a directory or special file; ${REBUILD}`],
      entry: null,
    };
  }
  if (st.size === 0) {
    return {
      ok: false,
      problems: [
        `entry point is empty (0 bytes): ${ENTRY_PATH} exists but carries no executable — ` +
        `an existing path is not a valid artifact; ${REBUILD}`,
      ],
      entry: { path: ENTRY_PATH, sha256: createHash("sha256").update(Buffer.alloc(0)).digest("hex"), bytes: 0 },
    };
  }
  let bytes;
  try {
    bytes = readFileSync(abs);
  } catch (error) {
    return {
      ok: false,
      problems: [`entry point unreadable: ${ENTRY_PATH}: ${String(error.message).split("\n")[0]}; ${REBUILD}`],
      entry: null,
    };
  }
  const entry = {
    path: ENTRY_PATH,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    bytes: bytes.length,
  };
  const problems = [];
  if (load) {
    const syntax = spawnSync(process.execPath, ["--check", abs], { encoding: "utf8" });
    if (syntax.status !== 0) {
      problems.push(
        `entry point failed node --check: ${ENTRY_PATH}: ` +
        `${(syntax.stderr ?? "").trim().split("\n")[0] ?? "unknown error"}; ${REBUILD}`);
    } else {
      const smoke = spawnSync(process.execPath, [abs, "--help"], { encoding: "utf8", timeout: 60_000 });
      if (smoke.status !== 0) {
        problems.push(
          `entry point failed to load: ${ENTRY_PATH} exited ${smoke.status} on --help: ` +
          `${((smoke.stderr ?? smoke.stdout ?? "").trim().split("\n")[0]) ?? ""}; ${REBUILD}`);
      }
    }
  }
  return { ok: problems.length === 0, problems, entry };
}

/** Gate the installed/packaged entry point against the recorded build. */
export function checkEntryPoint(root, manifest, opts = {}) {
  const read = readEntryPoint(root, opts);
  const problems = [...read.problems];
  const recorded = manifest?.runtime_entry ?? null;
  if (!recorded) {
    problems.push(
      `manifest.json records no runtime entry: this package carries no verified executable; ${REBUILD}`);
  } else if (read.entry) {
    if (read.entry.sha256 !== recorded.sha256 || read.entry.bytes !== recorded.bytes) {
      problems.push(
        `stale entry point: ${read.entry.path} is sha256 ${read.entry.sha256} (${read.entry.bytes} bytes) ` +
        `but manifest.json records ${recorded.sha256} (${recorded.bytes} bytes): ` +
        `an old bundle is never reused silently; ${REBUILD}`);
    }
  }
  return { ok: problems.length === 0, problems, entry: read.entry, recorded };
}
