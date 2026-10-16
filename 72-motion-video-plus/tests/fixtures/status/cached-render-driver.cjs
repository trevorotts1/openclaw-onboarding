// MG-046 cached-render driver. This is a test fixture, not
// production code: the run-status.ts runner spawns it as a child
// process so a production-path dispatch (MotionDispatcher.
// renderFinalCached with the real Remotion adapter) can be
// genuinely killed mid-render (SIGKILL) and resumed by a later
// process, with the cache session state under the job directory as
// the only handoff.
//
// Usage: node cached-render-driver.cjs <config.json>
// Config: {
//   distSrc: absolute path of runtime/dist/src,
//   jobDir: the two-scene fixture job package,
//   outDir: the Remotion adapter's output directory
// }
// Output: a "REPORT <json>" line (the CachedRenderOutcome's cache
// report plus the assembled artifact path), exit 0 on success; an
// "ERROR <json>" line and exit 5 on failure.

"use strict";

const { readFileSync } = require("node:fs");
const { join } = require("node:path");

function fixtureApproval(jobId) {
  // The dispatcher's fixture-context approval record (the MG-004
  // contract): an approved delivery decision for a fixture_only
  // job, labeled not_verified. Production gate binding is proven
  // separately in run-approvals.ts and in the run-status
  // production lifecycle case.
  return {
    schema_version: "2.0",
    approval_id: "mg046-fixture-approval",
    job_id: jobId,
    company_id: "fixture-company",
    scope: "delivery",
    decision: "approved",
    subject_revision: "fixture",
    artifact_refs: [],
    actor_id: "mg046-test-runner",
    source_event_ref: null,
    authority_status: "not_verified",
  };
}

async function main() {
  const config = JSON.parse(readFileSync(process.argv[2], "utf8"));
  const { createRegistry, MotionDispatcher } = require(join(config.distSrc, "adapters", "index.js"));
  const { createRemotionAdapter } = require(join(config.distSrc, "adapters", "remotion.js"));
  const manifest = JSON.parse(readFileSync(join(config.jobDir, "manifest.json"), "utf8"));
  const adapter = createRemotionAdapter({ outputDir: config.outDir });
  const dispatcher = new MotionDispatcher(createRegistry([adapter]));
  const outcome = await dispatcher.renderFinalCached(
    config.jobDir,
    fixtureApproval(manifest.job_id),
    { timeoutMs: 1_200_000 }
  );
  console.log(
    `REPORT ${JSON.stringify({
      cache: outcome.cache,
      artifacts: outcome.evidence.artifacts,
      outputPaths: outcome.evidence.outputPaths,
      engine: outcome.evidence.engine,
    })}`
  );
  process.exit(0);
}

main().catch((err) => {
  console.log(
    `ERROR ${JSON.stringify({
      category: err && err.category ? err.category : "MG_RENDER_FAILED",
      message: err && err.message ? err.message : String(err),
    })}`
  );
  process.exit(5);
});
