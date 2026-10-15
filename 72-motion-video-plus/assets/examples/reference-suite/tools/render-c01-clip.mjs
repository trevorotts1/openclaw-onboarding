// MG-044 reference suite tool: render the C01 final clip from the
// MG-044 image-components suite job (tests/evidence/mg044/work/
// c01-job, staged by runtime/tests/run-image-components.ts) through
// the shipped Hyperframes adapter, and copy the result to the suite
// path given as argv[3].
//
// Usage (from 72-motion-video-plus/runtime, after npm run build and
// after run-image-components has staged the job):
//   TMPDIR=<home-filesystem scratch> node \
//     ../assets/examples/reference-suite/tools/render-c01-clip.mjs \
//     <c01-job-dir> <output-mp4>
// The TMPDIR matters: the Hyperframes CLI refuses to render when
// /tmp is nearly full, and this box keeps its scratch on the home
// filesystem. Verified 2026-10-15: the render reproduces
// sequence/clips/beat1-c01.mp4 byte for byte (sha256 c4766e50...).
//
// The render goes through the adapter's governed renderFinal path
// with the same fixture approval the MG-044 suite uses. No new
// render machinery is introduced here.

import { cpSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const runtimeDist = resolve(
  process.env.MOTION_RUNTIME_DIST ?? join(process.cwd(), "dist")
);
const { HyperframesAdapter } = await import(
  join(runtimeDist, "src/adapters/hyperframes.js")
);

const [jobDir, output] = process.argv.slice(2);
if (!jobDir || !output) {
  console.error("usage: render-c01-clip.mjs <c01-job-dir> <output-mp4>");
  process.exit(2);
}
const manifest = JSON.parse(
  (await import("node:fs")).readFileSync(join(jobDir, "manifest.json"), "utf8")
);
const repoRoot = resolve(process.cwd(), "..", "..");
const adapter = new HyperframesAdapter({
  runtimeRoot: join(repoRoot, "shared-utils", "motion-render-runtime"),
});
const approved = {
  jobDir,
  jobId: manifest.job_id,
  manifest,
  approval: {
    schema_version: "2.0",
    approval_id: "mg044-fixture-approval",
    job_id: manifest.job_id,
    company_id: "fixture-company",
    scope: "delivery",
    decision: "approved",
    subject_revision: "mg044-fixture",
    artifact_refs: [],
    actor_id: "mg044-reference-suite-tool",
    source_event_ref: null,
    authority_status: "not_verified",
  },
};
const fin = await adapter.renderFinal(approved);
const src = join(jobDir, fin.outputPaths[0]);
mkdirSync(dirname(output), { recursive: true });
cpSync(src, output);
console.log(`rendered ${src} -> ${output}`);
