// MG-027 cache test driver. This is a test fixture, not production
// code: the run-cache.ts runner spawns it as a child process so a
// render can be genuinely killed mid-flight (SIGKILL) and resumed by
// a later process, with the cache state file as the only handoff.
//
// Usage: node cache-driver.cjs <config.json>
// Config: {
//   distSrc: absolute path of runtime/dist/src,
//   workDir, jobId, units: [SceneWorkUnit...],
//   scenes: { <sceneId>: { kind: "final", jobDir } |
//                        { kind: "stills", jobDir, frames, chunkSize } },
//   callsLog: absolute path of the render-call log to append to,
//   renderOutBase: adapter output base directory
// }
// Output: a "PLAN <json>" line (the session plan before running), a
// "REPORT <json>" line (the SessionRunReport), exit 0 when the
// report is ok, 3 when it is not, 2 on driver error.
//
// The renderers here are the test's stand-ins for a production
// orchestrator: "final" renders a whole single-scene C05 job through
// the production Remotion adapter's renderFinal; "stills" renders a
// scene as frame chunks through the same adapter's renderStill and
// encodes the segment with ffmpeg, the legacy renderer's model.

"use strict";

const { appendFileSync, copyFileSync, existsSync, readFileSync } = require("node:fs");
const { join } = require("node:path");
const { spawnSync } = require("node:child_process");

function fixtureApproval(jobId) {
  // The fixture approval record from the MG-006 runner: a
  // fixture_only job's diagnostic rendering carries the test runner's
  // own approval record, labeled not_verified. The dispatcher's
  // approval gate (MG-004) is not what MG-027 tests.
  return {
    schema_version: "2.0",
    approval_id: "mg027-fixture-approval",
    job_id: jobId,
    company_id: "fixture-company",
    scope: "delivery",
    decision: "approved",
    subject_revision: "fixture",
    artifact_refs: [],
    actor_id: "mg027-test-runner",
    source_event_ref: null,
    authority_status: "not_verified",
  };
}

function mapProbe(p) {
  return {
    kind: "video",
    width: p.width,
    height: p.height,
    fpsNumerator: p.fpsNumerator,
    fpsDenominator: p.fpsDenominator,
    frames: p.frameCount,
  };
}

async function main() {
  const config = JSON.parse(readFileSync(process.argv[2], "utf8"));
  const { CachedRenderSession } = require(join(config.distSrc, "cache", "index.js"));
  const { createRemotionAdapter } = require(join(config.distSrc, "adapters", "remotion.js"));
  const { loadValidatedJob } = require(join(config.distSrc, "adapters", "index.js"));
  const { probeVideoFile, readPngDimensions } = require(join(config.distSrc, "remotion", "decode.js"));
  const log = (line) => appendFileSync(config.callsLog, `${line}\n`, "utf8");

  const renderers = {
    final: (cfg) => async (ctx) => {
      const adapter = createRemotionAdapter({
        outputDir: join(config.renderOutBase, ctx.sceneId),
      });
      const job = loadValidatedJob(cfg.jobDir);
      log(`render-start ${ctx.sceneId}`);
      const ev = await adapter.renderFinal({ ...job, approval: fixtureApproval(job.jobId) });
      const mp4 = ev.outputPaths.find((p) => p.endsWith(".mp4"));
      if (!mp4) throw new Error(`renderFinal for ${ctx.sceneId} produced no mp4`);
      copyFileSync(mp4, ctx.artifactPath);
      await ctx.reportChunkComplete(0);
      log(`render-done ${ctx.sceneId}`);
      return { probe: mapProbe(probeVideoFile(ctx.artifactPath)) };
    },
    stills: (cfg) => async (ctx) => {
      const adapter = createRemotionAdapter({
        outputDir: join(config.renderOutBase, ctx.sceneId),
      });
      const job = loadValidatedJob(cfg.jobDir);
      const frameName = (f) => `frame-${String(f).padStart(4, "0")}.png`;
      // Review still first, so even a killed run leaves it in the
      // chunk directory for the parent to register as review evidence.
      const reviewPath = join(ctx.chunkDir, "review-f45.png");
      if (!existsSync(reviewPath)) {
        const ev = await adapter.renderStill(job, 45);
        copyFileSync(ev.outputPaths[0], reviewPath);
        log(`review-still ${ctx.sceneId}`);
      }
      const chunks = Math.ceil(cfg.frames / cfg.chunkSize);
      for (let c = 0; c < chunks; c += 1) {
        const from = c * cfg.chunkSize;
        const to = Math.min(cfg.frames, from + cfg.chunkSize);
        if (ctx.completedChunks.includes(c)) {
          for (let f = from; f < to; f += 1) {
            const p = join(ctx.chunkDir, frameName(f));
            const dims = existsSync(p) ? readPngDimensions(p) : null;
            if (!dims || dims.width !== 1920 || dims.height !== 1080) {
              throw new Error(
                `resume claims chunk ${c} of ${ctx.sceneId} but frame ${f} is missing or wrong-sized on disk`
              );
            }
          }
          log(`skip-chunk ${ctx.sceneId} ${c}`);
          continue;
        }
        for (let f = from; f < to; f += 1) {
          const ev = await adapter.renderStill(job, f);
          copyFileSync(ev.outputPaths[0], join(ctx.chunkDir, frameName(f)));
          log(`still ${ctx.sceneId} ${f}`);
        }
        await ctx.reportChunkComplete(c);
        log(`chunk-done ${ctx.sceneId} ${c}`);
      }
      const enc = spawnSync(
        "ffmpeg",
        [
          "-y", "-v", "error", "-framerate", "30",
          "-i", join(ctx.chunkDir, "frame-%04d.png"),
          "-c:v", "libx264", "-pix_fmt", "yuv420p",
          ctx.artifactPath,
        ],
        { encoding: "utf8" }
      );
      if (enc.status !== 0) {
        const err = new Error(`segment encode failed for ${ctx.sceneId}`);
        err.logTail = (enc.stderr || "").slice(-4000);
        throw err;
      }
      log(`encode-done ${ctx.sceneId}`);
      return { probe: mapProbe(probeVideoFile(ctx.artifactPath)) };
    },
  };

  const session = await CachedRenderSession.open({
    workDir: config.workDir,
    jobId: config.jobId,
    units: config.units,
  });
  console.log(`PLAN ${JSON.stringify(session.plan())}`);
  const report = await session.run(
    (unit) => renderers[config.scenes[unit.sceneId].kind](config.scenes[unit.sceneId])
  );
  console.log(`REPORT ${JSON.stringify(report)}`);
  process.exit(report.ok ? 0 : 3);
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(2);
});
