// Immutable job revision fingerprints (MG-025, Directive Section 16.7).
//
// A job revision is a deterministic fingerprint over everything a
// render consumes: manifest intent, the source bundle (storyboard and
// scene specs), design, datasets, assets, resolved font requirements,
// the compiled timeline plus its MG-021 sidecar, the narration script
// record, and the runtime identity. Each component digest is the
// sha256 of canonical JSON over sorted {path, sha256} content pairs
// (file digests over raw bytes, so the TypeScript and Python
// evaluators agree byte for byte). Two digests are derived:
//
// - designRevision covers the art-direction components (design,
//   assets, fonts). A code-only or copy-only change leaves it intact,
//   so a design approval survives; an image or font change moves it.
// - fullRevision covers all nine components. Any material change
//   moves it, so preview and delivery approvals stale by construction.
//
// Approvals, review receipts, output files, timestamps, absolute
// paths, and the revision lock itself are never component inputs, so
// writing an approval never changes the revision it approves.

import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";
import { canonicalJson, sha256Bytes, sha256Hex } from "./canonical";

export const COMPONENT_NAMES = [
  "manifest",
  "source",
  "design",
  "data",
  "assets",
  "fonts",
  "timeline",
  "narration",
  "runtime",
] as const;
export type ComponentName = (typeof COMPONENT_NAMES)[number];

/** Components whose digests form the design revision (Section 16.7:
 * separate design and full-render digests). */
export const DESIGN_COMPONENTS: ComponentName[] = ["design", "assets", "fonts"];

export interface HashEntry {
  path: string;
  sha256: string | null;
}

export interface ComponentRecord {
  digest: string | null;
  entries: HashEntry[];
}

export interface RevisionProblem {
  category: "MG_INPUT_MISSING" | "MG_HASH_MISMATCH" | "MG_SCHEMA_INVALID";
  path: string;
  message: string;
}

/** The runtime identity a revision binds: the routed engine, its exact
 * probed version, and the runtime-lock content id (the lock's own
 * content hash, for example "lock-314fc289b233ca9e"). */
export interface GateRuntimeIdentity {
  engine: string;
  engineVersion: string;
  runtimeLockId: string;
}

export interface RevisionLock {
  schemaVersion: "1.0";
  jobId: string | null;
  companyId: string | null;
  components: Record<ComponentName, ComponentRecord>;
  designRevision: string | null;
  fullRevision: string | null;
  runtime: GateRuntimeIdentity | null;
  problems: RevisionProblem[];
}

type Doc = Record<string, unknown>;

function isDoc(value: unknown): value is Doc {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function componentDigest(name: ComponentName, entries: HashEntry[]): string {
  const sorted = [...entries].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  return sha256Hex(canonicalJson({ component: name, entries: sorted }));
}

function combinedDigest(kind: string, parts: Partial<Record<ComponentName, string | null>>): string | null {
  const names = Object.keys(parts).sort();
  const normalized: Record<string, string> = {};
  for (const name of names) {
    const digest = parts[name as ComponentName];
    if (digest === null || digest === undefined) return null;
    normalized[name] = digest;
  }
  return sha256Hex(canonicalJson({ component: kind, parts: normalized }));
}

export class RevisionComputer {
  private readonly jobDir: string;
  private readonly problems: RevisionProblem[] = [];

  constructor(jobDir: string) {
    this.jobDir = resolve(jobDir);
  }

  private safePath(rel: string): string | null {
    const abs = resolve(join(this.jobDir, rel));
    if (abs !== this.jobDir && !abs.startsWith(this.jobDir + sep)) {
      this.problems.push({
        category: "MG_SCHEMA_INVALID",
        path: rel,
        message: `Path ${rel} escapes the job directory; it cannot enter a revision fingerprint.`,
      });
      return null;
    }
    return abs;
  }

  /** sha256 of a job-relative file's bytes, or null (with a recorded
   * problem) when the file is required but absent. */
  fileEntry(rel: string, required: boolean): HashEntry {
    const abs = this.safePath(rel);
    if (abs === null) return { path: rel, sha256: null };
    if (!existsSync(abs)) {
      if (required) {
        this.problems.push({
          category: "MG_INPUT_MISSING",
          path: rel,
          message: `Revision input ${rel} is missing.`,
        });
      }
      return { path: rel, sha256: null };
    }
    return { path: rel, sha256: sha256Bytes(readFileSync(abs)) };
  }

  private readJson(rel: string): Doc | null {
    const abs = this.safePath(rel);
    if (abs === null || !existsSync(abs)) return null;
    try {
      const parsed: unknown = JSON.parse(readFileSync(abs, "utf8"));
      return isDoc(parsed) ? parsed : null;
    } catch {
      return null;
    }
  }

  private listDataFiles(): string[] {
    const dataDir = join(this.jobDir, "data");
    const out: string[] = [];
    if (!existsSync(dataDir)) return out;
    const walk = (dir: string): void => {
      for (const name of readdirSync(dir).sort()) {
        const abs = join(dir, name);
        if (statSync(abs).isDirectory()) walk(abs);
        else out.push(relative(this.jobDir, abs).split(sep).join("/"));
      }
    };
    walk(dataDir);
    return out.sort();
  }

  compute(runtime: GateRuntimeIdentity | null): RevisionLock {
    const manifest = this.readJson("manifest.json");
    const jobId = typeof manifest?.job_id === "string" ? manifest.job_id : null;
    const companyId = typeof manifest?.company_id === "string" ? manifest.company_id : null;
    const ref = (field: string, fallback: string): string =>
      manifest && typeof manifest[field] === "string" && (manifest[field] as string).length > 0
        ? (manifest[field] as string)
        : fallback;

    const components = {} as Record<ComponentName, ComponentRecord>;
    const finish = (name: ComponentName, entries: HashEntry[]): ComponentRecord => {
      const record = { digest: componentDigest(name, entries), entries };
      components[name] = record;
      return record;
    };

    // Manifest intent.
    finish("manifest", [this.fileEntry("manifest.json", true)]);

    // Source bundle: the storyboard plus every scene spec, by path.
    const sceneSpecs: string[] = [];
    const sceneDataPaths: string[] = [];
    if (manifest && Array.isArray(manifest.scenes)) {
      for (const scene of manifest.scenes) {
        if (isDoc(scene) && typeof scene.spec === "string") sceneSpecs.push(scene.spec);
      }
    }
    const sourcePaths = new Set<string>([ref("storyboard", "storyboard.json"), ...sceneSpecs]);
    finish("source", [...sourcePaths].sort().map((rel) => this.fileEntry(rel, true)));

    // Design record.
    finish("design", [this.fileEntry(ref("design", "design.json"), true)]);

    // Data: every dataset file under data/, plus any scene data_path.
    for (const spec of sceneSpecs) {
      const sceneDoc = this.readJson(spec);
      if (sceneDoc && typeof sceneDoc.data_path === "string") sceneDataPaths.push(sceneDoc.data_path);
    }
    const dataPaths = new Set<string>([...this.listDataFiles(), ...sceneDataPaths]);
    finish("data", [...dataPaths].sort().map((rel) => this.fileEntry(rel, true)));

    // Assets: the assets record plus the bytes of every asset it names.
    // A declared hash that disagrees with the bytes on disk is a tamper
    // signal (MG_HASH_MISMATCH), reported as a problem; the digest
    // always covers the actual bytes.
    const assetsRel = ref("assets", "assets.json");
    const assetsDoc = this.readJson(assetsRel);
    const assetEntries: HashEntry[] = [this.fileEntry(assetsRel, true)];
    if (assetsDoc && Array.isArray(assetsDoc.assets)) {
      for (const asset of assetsDoc.assets) {
        if (!isDoc(asset) || typeof asset.path !== "string") continue;
        const entry = this.fileEntry(asset.path, true);
        if (entry.sha256 !== null && typeof asset.sha256 === "string" && asset.sha256 !== entry.sha256) {
          this.problems.push({
            category: "MG_HASH_MISMATCH",
            path: asset.path,
            message:
              `Asset ${asset.path} declares sha256 ${asset.sha256} in ${assetsRel} but its bytes ` +
              `hash to ${entry.sha256}; the assets record does not describe the asset on disk.`,
          });
        }
        assetEntries.push(entry);
      }
    }
    finish("assets", assetEntries);

    // Resolved fonts: the font requirements the assets record declares
    // (source is the runtime registry; substitution is forbidden, so the
    // requirement record plus the runtime lock pin the resolved font).
    const fontEntries: HashEntry[] = [];
    if (assetsDoc && Array.isArray(assetsDoc.font_requirements)) {
      for (const requirement of assetsDoc.font_requirements) {
        if (!isDoc(requirement)) continue;
        const id = typeof requirement.id === "string" ? requirement.id : "font";
        fontEntries.push({
          path: `font:${id}`,
          sha256: sha256Hex(canonicalJson(requirement)),
        });
      }
    }
    finish("fonts", fontEntries);

    // Timeline: the canonical compiled timeline plus the MG-021
    // sidecar when the package carries one. The sidecar entry is
    // always present in the pair list (null when absent), so adding a
    // sidecar later moves the digest.
    const timelineRel = ref("timeline", "timeline.json");
    const sidecarAbs = join(this.jobDir, "timeline-sidecar.json");
    finish("timeline", [
      this.fileEntry(timelineRel, true),
      existsSync(sidecarAbs)
        ? this.fileEntry("timeline-sidecar.json", true)
        : { path: "timeline-sidecar.json", sha256: null },
    ]);

    // Narration: the job-package narration script record (settlement C
    // in references/approvals-and-gates.md). Absent narration is an
    // explicit empty entry list, so adding narration moves the digest.
    finish(
      "narration",
      existsSync(join(this.jobDir, "narration.json"))
        ? [this.fileEntry("narration.json", true)]
        : []
    );

    // Runtime identity.
    if (runtime) {
      finish("runtime", [
        {
          path: "runtime",
          sha256: sha256Hex(
            canonicalJson({
              engine: runtime.engine,
              engineVersion: runtime.engineVersion,
              runtimeLockId: runtime.runtimeLockId,
            })
          ),
        },
      ]);
    } else {
      components.runtime = { digest: null, entries: [] };
    }

    const designRevision = combinedDigest("design-revision", {
      assets: components.assets.digest,
      design: components.design.digest,
      fonts: components.fonts.digest,
    });
    const fullRevision = combinedDigest("full-revision", {
      manifest: components.manifest.digest,
      source: components.source.digest,
      design: components.design.digest,
      data: components.data.digest,
      assets: components.assets.digest,
      fonts: components.fonts.digest,
      timeline: components.timeline.digest,
      narration: components.narration.digest,
      runtime: components.runtime.digest,
    });

    return {
      schemaVersion: "1.0",
      jobId,
      companyId,
      components,
      designRevision,
      fullRevision,
      runtime,
      problems: this.problems,
    };
  }
}

/** Compute the revision lock for a job directory. Pure: writes nothing. */
export function computeRevisionLock(
  jobDir: string,
  runtime: GateRuntimeIdentity | null
): RevisionLock {
  return new RevisionComputer(jobDir).compute(runtime);
}

/** Compute and persist revision-lock.json in the job directory
 * (Section 16.7). The lock file is never a component input, so writing
 * it cannot change the digests it records. */
export function writeRevisionLock(
  jobDir: string,
  runtime: GateRuntimeIdentity | null
): RevisionLock {
  const lock = computeRevisionLock(jobDir, runtime);
  const persisted = {
    schema_version: lock.schemaVersion,
    job_id: lock.jobId,
    company_id: lock.companyId,
    components: Object.fromEntries(
      COMPONENT_NAMES.map((name) => [
        name,
        { digest: lock.components[name].digest, entries: lock.components[name].entries },
      ])
    ),
    design_revision: lock.designRevision,
    full_revision: lock.fullRevision,
    runtime: lock.runtime,
  };
  writeFileSync(join(jobDir, "revision-lock.json"), JSON.stringify(persisted, null, 2) + "\n", "utf8");
  return lock;
}

/** Names of components whose digests differ between two locks. */
export function diffComponents(a: RevisionLock, b: RevisionLock): ComponentName[] {
  return COMPONENT_NAMES.filter((name) => a.components[name].digest !== b.components[name].digest);
}
