// Shared-runtime resolution for the diagrams render harness
// (Directive MG-017).
//
// The render engines come from the shared render runtime only
// (shared-utils/motion-render-runtime, MG-003): this resolver walks up
// to the provisioned install, reads readiness from the runtime lock
// the provisioner's probe wrote, and fails loudly when the runtime is
// missing or not passing. It follows exactly the rules of the Remotion
// adapter's resolver in src/adapters/remotion.ts; that resolver is
// module-private to the adapter, so this item carries its own rather
// than editing another item's module (recorded as an integration note
// for MG-025, which may export a shared resolver).

import { existsSync, readFileSync, realpathSync } from "node:fs";
import { dirname, join } from "node:path";

export interface DiagramRuntime {
  sharedRuntimeDir: string;
  /** State dir: <shared runtime>/.runtime (bundles and scratch live here). */
  stateDir: string;
  /** Real directory the .runtime/current symlink points at. */
  currentDir: string;
  lockId: string | null;
  remotionVersion: string | null;
  browserExecutable: string;
}

interface RuntimeLockDoc {
  result?: string;
  packages?: Record<string, string>;
  browser?: { executable?: string } | null;
  engines?: Record<string, { status?: string; version?: string }>;
}

function findSharedRuntimeDir(startDir: string): string | null {
  let dir = startDir;
  for (let i = 0; i < 12; i += 1) {
    const candidate = join(dir, "shared-utils", "motion-render-runtime");
    if (existsSync(join(candidate, "provision.sh"))) return candidate;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

export function resolveDiagramRuntime(sharedRuntimeDir?: string): DiagramRuntime {
  const dir = sharedRuntimeDir ?? findSharedRuntimeDir(__dirname);
  if (!dir) {
    throw new Error(
      "shared render runtime (shared-utils/motion-render-runtime) was not found above " +
        __dirname +
        "; provision the repository checkout before rendering diagrams."
    );
  }
  const stateDir = join(dir, ".runtime");
  const currentLink = join(stateDir, "current");
  let currentDir: string | null = null;
  try {
    if (existsSync(currentLink)) currentDir = realpathSync(currentLink);
  } catch {
    currentDir = null;
  }
  if (!currentDir) {
    throw new Error(
      `shared runtime at ${dir} has no readable .runtime/current; run provision.sh first.`
    );
  }
  let lock: RuntimeLockDoc | null = null;
  for (const candidate of [join(stateDir, "runtime-lock.json"), join(currentDir, "runtime-lock.json")]) {
    if (existsSync(candidate)) {
      try {
        lock = JSON.parse(readFileSync(candidate, "utf8")) as RuntimeLockDoc;
        break;
      } catch {
        lock = null;
      }
    }
  }
  if (!lock) {
    throw new Error(`no readable runtime-lock.json under ${stateDir}; run provision.sh first.`);
  }
  if (lock.result !== "pass" || lock.engines?.remotion?.status !== "pass") {
    throw new Error(
      `runtime lock does not record a passing remotion probe (result ${lock.result ?? "?"}, ` +
        `remotion ${lock.engines?.remotion?.status ?? "?"}); re-run provision.sh.`
    );
  }
  if (!existsSync(join(currentDir, "node_modules", "remotion", "package.json"))) {
    throw new Error(`.runtime/current at ${currentDir} does not contain remotion; re-run provision.sh.`);
  }
  const browserExecutable = lock.browser?.executable
    ? join(currentDir, lock.browser.executable)
    : null;
  if (!browserExecutable || !existsSync(browserExecutable)) {
    throw new Error(
      "runtime lock names no usable Chrome Headless Shell executable; re-run provision.sh."
    );
  }
  return {
    sharedRuntimeDir: dir,
    stateDir,
    currentDir,
    lockId: currentDir.split("/").pop() ?? null,
    remotionVersion: lock.packages?.remotion ?? null,
    browserExecutable,
  };
}
