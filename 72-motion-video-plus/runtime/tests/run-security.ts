// Security isolation tests for MG-029 (Directive Section 15 MG-029).
//
// Every case runs against the real mechanisms on this machine: the
// real environment of spawned children, the real /proc process tree,
// the real provisioned Chromium, real network namespaces, and a real
// Hyperframes render through the production adapter. Proofs:
//
// 1. Environment: a render child launched through the isolation
//    runner cannot see provider secrets planted in the host
//    environment (allowlist scrub), while a control child launched
//    without isolation can (the plant is real).
// 2. Logs: captured child output is redacted; planted values, bearer
//    tokens, labeled keys, and provider key shapes never survive,
//    while benign content (a sha256-shaped digest) is untouched.
// 3. Asset references: traversal, absolute, URL, encoded, backslash,
//    and symlink-escape references are refused with named rule codes;
//    an ordinary job-relative reference validates.
// 4. Preparation fetch and origin: an approved asset (recorded hash)
//    is fetched and staged; wrong bytes are refused and stage
//    nothing; the local origin serves staged files and refuses
//    traversal and symlink escapes, with the refusals logged.
// 5. Process ownership: cancelling one job kills its recorded root
//    and its token-carrying grandchild, and nothing else: a second
//    job and an unrelated Chromium both survive. A stale registry
//    record pointing at the unrelated Chromium (recycled-pid shape)
//    is refused, not acted on. The shipped sweep script then cleans
//    the remaining recorded job and still leaves the Chromium alone.
// 6. Network: inside the namespace policy a Node child and the real
//    Chromium scene cannot reach a recorder on the host loopback or
//    the host's interface address; outside the policy they can. A
//    real Hyperframes still renders successfully with the loopback
//    policy in force, its processes recorded, no planted secret in
//    any recorded argument. An unrecognized MOTION_RENDER_NETWORK
//    value is refused as NETWORK_MODE_INVALID, never silently
//    defaulted to off.
// 7. Command-like copy: copy full of shell metacharacters passed as a
//    render argument arrives byte-identical and executes nothing; the
//    same copy set as page text renders as text.
//
// Evidence: tests/evidence/mg029/measurements.json.
// Exit code 0 when every case passes, 1 otherwise.

import { spawn, spawnSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { createServer } from "node:http";
import { join, resolve } from "node:path";
import {
  AssetOriginServer,
  buildRenderEnv,
  fetchApprovedAsset,
  findSecretShapes,
  IsolationError,
  networkModeFromEnv,
  pidAlive,
  ProcessRegistry,
  probeNetworkNamespace,
  redactSecrets,
  runIsolated,
  spawnIsolated,
  terminateJobProcesses,
  validateAssetRef,
  type IsolatedChild,
  type IsolatedRunResult,
} from "../src/isolation";
import { HyperframesAdapter } from "../src/adapters/hyperframes";
import type { Manifest } from "../src/validation/generated-types";
import type { ValidatedMotionJob } from "../src/adapters/types";

let passed = 0;
let failed = 0;
function report(ok: boolean, line: string, detail?: string): void {
  if (ok) passed += 1;
  else failed += 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${line}`);
  if (!ok && detail) console.log(`  ${detail}`);
}

const SKILL_DIR = resolve(__dirname, "..", "..", "..");
const REPO_ROOT = resolve(SKILL_DIR, "..");
const TMP_SCRATCH = join(REPO_ROOT, ".scratch", "tmp");
mkdirSync(TMP_SCRATCH, { recursive: true });
process.env.TMPDIR = TMP_SCRATCH;

const FIXTURES = join(SKILL_DIR, "tests", "fixtures", "security");
const EVIDENCE_DIR = join(SKILL_DIR, "tests", "evidence", "mg029");
const WORK = join(REPO_ROOT, ".scratch", "mg029");
rmSync(WORK, { recursive: true, force: true });
mkdirSync(WORK, { recursive: true });
const REGISTRY_DIR = join(WORK, "registry");
const registry = new ProcessRegistry(REGISTRY_DIR);

const PLANTED = {
  KIE_API_KEY: "mg029-planted-kie-3f8a1c9d7b2e",
  FISH_AUDIO_API_KEY: "mg029-planted-fish-55d2a0918c4b",
  GEMINI_API_KEY: "mg029-planted-gemini-91e0b377aa10",
  MG029_PLANTED_SECRET: "mg029-planted-generic-6c41d8f0e2a9",
};
const PLANTED_VALUES = Object.values(PLANTED);

function fixture(name: string): string {
  return join(FIXTURES, name);
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

async function waitFor(cond: () => boolean, timeoutMs: number, what: string): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (cond()) return;
    await sleep(100);
  }
  throw new Error(`timed out waiting for ${what}`);
}

/** The one external endpoint this sandbox offers ordinary processes:
 * the egress proxy named by the proxy environment variables. Returned
 * as a tcp://host:port probe target; only host and port are taken
 * from the variable, never its credentials. Null when no proxy is
 * configured, in which case the loopback recorder is the only
 * control target. */
function proxyTcpTarget(): string | null {
  const raw =
    process.env.https_proxy ?? process.env.HTTPS_PROXY ??
    process.env.http_proxy ?? process.env.HTTP_PROXY;
  if (!raw) return null;
  try {
    const u = new URL(raw);
    return u.hostname && u.port ? `tcp://${u.hostname}:${u.port}` : null;
  } catch {
    return null;
  }
}

/** Drive the provisioned Chromium over a file:// page through
 * puppeteer-core (the engines' own control path) and return the
 * isolated run result; the DOM is on stdout. */
async function runPage(opts: {
  chrome: string;
  profile: string;
  htmlPath: string;
  jobId: string;
  network: "off" | "loopback";
  waitMs?: number;
}): Promise<IsolatedRunResult> {
  const puppeteerCoreDir = join(
    REPO_ROOT,
    "shared-utils", "motion-render-runtime", ".runtime", "current",
    "node_modules", "puppeteer-core"
  );
  return runIsolated(
    process.execPath,
    [
      fixture("browser-driver.cjs"),
      puppeteerCoreDir,
      opts.chrome,
      opts.profile,
      opts.htmlPath,
      String(opts.waitMs ?? 7000),
    ],
    { jobId: opts.jobId, cwd: WORK, registry, network: opts.network, timeoutMs: 120000 }
  );
}

function findChrome(): string | null {
  const candidates = [
    join(
      REPO_ROOT,
      "shared-utils", "motion-render-runtime", ".runtime", "current",
      "node_modules", ".remotion", "chrome-headless-shell", "linux64",
      "chrome-headless-shell-linux64", "chrome-headless-shell"
    ),
  ];
  for (const c of candidates) if (existsSync(c)) return c;
  return null;
}

const measurements: Record<string, unknown> = {};

// ---------------------------------------------------------------------
// 1. Environment scrubbing.
// ---------------------------------------------------------------------

async function sectionEnv(): Promise<void> {
  const baseEnv: NodeJS.ProcessEnv = {
    PATH: process.env.PATH ?? "/usr/bin:/bin",
    HOME: "/home/render-operator",
    LANG: "en_US.UTF-8",
    MOTION_RUNTIME_DIR: "/some/runtime",
    NODE_OPTIONS: "--require /tmp/evil-injection.js",
    LD_PRELOAD: "/tmp/evil-preload.so",
    HTTP_PROXY: "http://proxy.invalid:8080",
    AWS_SECRET_ACCESS_KEY: "mg029-planted-aws-77aa10c4d3",
    GITHUB_TOKEN: "mg029-planted-gh-12bc90de77",
    ...PLANTED,
  };
  const built = buildRenderEnv(baseEnv, { jobId: "mg029-env" });
  report(
    built.env.PATH === baseEnv.PATH && built.env.HOME === baseEnv.HOME &&
      built.env.MOTION_RUNTIME_DIR === "/some/runtime",
    "env scrub: ordinary and runtime configuration variables survive"
  );
  const leakedNames = Object.keys(PLANTED).filter((k) => k in built.env);
  report(
    leakedNames.length === 0 &&
      !("AWS_SECRET_ACCESS_KEY" in built.env) &&
      !("GITHUB_TOKEN" in built.env),
    "env scrub: provider secrets and tokens are withheld (names checked)",
    `leaked: ${leakedNames.join(", ")}`
  );
  report(
    !("NODE_OPTIONS" in built.env) && !("LD_PRELOAD" in built.env) && !("HTTP_PROXY" in built.env),
    "env scrub: code-injection and proxy egress variables are withheld"
  );
  report(
    PLANTED_VALUES.every((v) => !Object.values(built.env).includes(v)),
    "env scrub: no planted secret VALUE is present under any name"
  );
  report(
    built.removedNames.includes("KIE_API_KEY") &&
      built.removedNames.includes("NODE_OPTIONS") &&
      built.jobToken !== null &&
      built.env.MOTION_JOB_TOKEN === built.jobToken &&
      built.env.MOTION_JOB_ID === "mg029-env",
    "env scrub: removed names are reported and the job carries its ownership token"
  );

  // The same proof through a real child process.
  const probe = await runIsolated(process.execPath, [fixture("env-probe.cjs")], {
    jobId: "mg029-env-child",
    cwd: WORK,
    registry,
    baseEnv: { ...process.env, ...PLANTED, NODE_OPTIONS: "--require /tmp/evil.js" },
    network: "off",
  });
  let childEnv: Record<string, string> = {};
  try {
    childEnv = JSON.parse(probe.stdout) as Record<string, string>;
  } catch {
    childEnv = {};
  }
  report(
    probe.exitCode === 0 &&
      PLANTED_VALUES.every((v) => !Object.values(childEnv).includes(v)) &&
      !("KIE_API_KEY" in childEnv) && !("NODE_OPTIONS" in childEnv),
    "env child: a real render child sees no planted secret and no injection variable",
    `exit=${probe.exitCode}, keys=${Object.keys(childEnv).join(",")}`
  );
  measurements.envRemovedNames = probe.removedEnvNames;
}

// ---------------------------------------------------------------------
// 2. Log redaction and the leak control.
// ---------------------------------------------------------------------

async function sectionRedaction(): Promise<void> {
  const control = spawnSync(process.execPath, [fixture("leaky-child.cjs")], {
    env: { ...process.env, ...PLANTED },
    encoding: "utf8",
  });
  report(
    PLANTED_VALUES.some((v) => control.stdout.includes(v)),
    "leak control: without isolation the fixture child's planted secret reaches its output (the plant is real)"
  );
  const isolated = await runIsolated(process.execPath, [fixture("leaky-child.cjs")], {
    jobId: "mg029-leak",
    cwd: WORK,
    registry,
    baseEnv: { ...process.env, ...PLANTED },
    network: "off",
  });
  const shapes = findSecretShapes(isolated.stdout, PLANTED_VALUES);
  report(
    shapes.length === 0 &&
      !isolated.stdout.includes("FAKEBEARERTOKEN0123456789") &&
      !isolated.stdout.includes("FAKE-LABELED-KEY-0123456789") &&
      !isolated.stdout.includes("sk-fakeproviderkey0123456789abcd"),
    "redaction: captured output holds no planted value, bearer token, labeled key, or provider key shape",
    `shapes found: ${shapes.join(", ") || "none"}; output: ${isolated.stdout.slice(0, 200)}`
  );
  report(
    isolated.stdout.includes(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    "redaction: benign content (a sha256-shaped digest) survives untouched"
  );
  const direct = redactSecrets(
    "token is mg029-planted-kie-3f8a1c9d7b2e ok",
    PLANTED_VALUES
  );
  report(
    direct === "token is [redacted] ok",
    "redaction: exact host values are replaced wherever they appear"
  );
}

// ---------------------------------------------------------------------
// 3. Asset reference validation.
// ---------------------------------------------------------------------

function sectionPaths(): void {
  const jobDir = join(WORK, "job");
  mkdirSync(join(jobDir, "assets"), { recursive: true });
  writeFileSync(join(jobDir, "assets", "ok.png"), "png-bytes");
  const outside = join(WORK, "outside");
  mkdirSync(outside, { recursive: true });
  writeFileSync(join(outside, "secret.png"), "outside-bytes");
  symlinkSync(outside, join(jobDir, "linked"), "dir");

  const cases: Array<{ ref: string; code: string | null }> = [
    { ref: "assets/ok.png", code: null },
    { ref: "../outside/secret.png", code: "ASSET_REF_TRAVERSAL" },
    { ref: "assets/../../outside/secret.png", code: "ASSET_REF_TRAVERSAL" },
    { ref: "/etc/passwd", code: "ASSET_REF_ABSOLUTE" },
    { ref: "C:/Windows/secret.png", code: "ASSET_REF_ABSOLUTE" },
    { ref: "C:\\Windows\\secret.png", code: "ASSET_REF_BACKSLASH" },
    { ref: "https://evil.example/x.png", code: "ASSET_REF_EXTERNAL" },
    { ref: "file:///etc/passwd", code: "ASSET_REF_EXTERNAL" },
    { ref: "//evil.example/x.png", code: "ASSET_REF_EXTERNAL" },
    { ref: "data:image/png;base64,AAAA", code: "ASSET_REF_EXTERNAL" },
    { ref: "assets/%2e%2e/outside.png", code: "ASSET_REF_TRAVERSAL" },
    { ref: "assets\\..\\secret.png", code: "ASSET_REF_BACKSLASH" },
    { ref: "linked/secret.png", code: "ASSET_REF_ESCAPE" },
    { ref: "assets/missing.png", code: "ASSET_REF_MISSING" },
    { ref: "", code: "ASSET_REF_EMPTY" },
  ];
  for (const c of cases) {
    const v = validateAssetRef(c.ref, { jobDir, mustExist: true });
    if (c.code === null) {
      report(
        v.ok && v.resolvedPath === join(jobDir, "assets", "ok.png"),
        `asset ref ${JSON.stringify(c.ref)}: valid, resolves inside the job`,
        `got ok=${v.ok} findings=${JSON.stringify(v.findings)}`
      );
    } else {
      report(
        !v.ok && v.findings.length === 1 && v.findings[0].code === c.code,
        `asset ref ${JSON.stringify(c.ref)}: refused as ${c.code}`,
        `got ok=${v.ok} findings=${JSON.stringify(v.findings)}`
      );
    }
  }
}

// ---------------------------------------------------------------------
// 4. Approved fetch and the local origin.
// ---------------------------------------------------------------------

const PNG_1PX = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
  "base64"
);

async function sectionAssets(): Promise<void> {
  const { createHash } = await import("node:crypto");
  const pngHash = createHash("sha256").update(PNG_1PX).digest("hex");
  const source = createServer((req, res) => {
    if (req.url === "/asset.png") {
      res.writeHead(200, { "Content-Type": "image/png" });
      res.end(PNG_1PX);
    } else if (req.url === "/hop") {
      res.writeHead(302, { Location: "/asset.png" });
      res.end();
    } else if (req.url === "/escape-hop") {
      res.writeHead(302, { Location: "file:///etc/passwd" });
      res.end();
    } else {
      res.writeHead(404);
      res.end();
    }
  });
  await new Promise<void>((r) => source.listen(0, "127.0.0.1", r));
  const sourcePort = (source.address() as { port: number }).port;
  const staging = join(WORK, "staging");
  try {
    const fetched = await fetchApprovedAsset(
      { url: `http://127.0.0.1:${sourcePort}/asset.png`, sha256: pngHash },
      staging
    );
    report(
      fetched.sha256 === pngHash &&
        existsSync(fetched.path) &&
        readFileSync(fetched.path).equals(PNG_1PX),
      "asset fetch: approved bytes are fetched at preparation and staged byte-identical"
    );
    const viaRedirect = await fetchApprovedAsset(
      { url: `http://127.0.0.1:${sourcePort}/hop`, sha256: pngHash, fileName: "hopped.png" },
      staging
    );
    report(
      viaRedirect.fileName === "hopped.png" && existsSync(viaRedirect.path),
      "asset fetch: a redirect that stays inside the fetch policy is followed"
    );
    let mismatchCode = "";
    try {
      await fetchApprovedAsset(
        { url: `http://127.0.0.1:${sourcePort}/asset.png`, sha256: "0".repeat(64), fileName: "wrong.png" },
        staging
      );
    } catch (err) {
      mismatchCode = (err as IsolationError).code ?? "";
    }
    report(
      mismatchCode === "ASSET_HASH_MISMATCH" && !existsSync(join(staging, "wrong.png")),
      "asset fetch: bytes that do not match the recorded hash are refused and stage nothing",
      `code=${mismatchCode}`
    );
    let schemeCode = "";
    let fetchCalled = false;
    try {
      await fetchApprovedAsset(
        { url: "http://assets.example.com/x.png", sha256: pngHash },
        staging,
        {
          fetchImpl: async () => {
            fetchCalled = true;
            throw new Error("must not be called");
          },
        }
      );
    } catch (err) {
      schemeCode = (err as IsolationError).code ?? "";
    }
    report(
      schemeCode === "ASSET_FETCH_REFUSED" && !fetchCalled,
      "asset fetch: plain http to a non-loopback host is refused before any request",
      `code=${schemeCode} fetchCalled=${fetchCalled}`
    );
    let escapeHopCode = "";
    try {
      await fetchApprovedAsset(
        { url: `http://127.0.0.1:${sourcePort}/escape-hop`, sha256: pngHash },
        staging
      );
    } catch (err) {
      escapeHopCode = (err as IsolationError).code ?? "";
    }
    report(
      escapeHopCode === "ASSET_FETCH_REFUSED",
      "asset fetch: a redirect out of the policy (file:) is refused",
      `code=${escapeHopCode}`
    );

    // The origin serves exactly the staged directory.
    writeFileSync(join(WORK, "origin-secret.txt"), "not an asset");
    symlinkSync(join(WORK, "origin-secret.txt"), join(staging, "linked.txt"));
    const origin = await AssetOriginServer.serve(staging);
    try {
      const okRes = await fetch(`${origin.url}/asset.png`);
      const okBytes = Buffer.from(await okRes.arrayBuffer());
      report(
        okRes.status === 200 && okBytes.equals(PNG_1PX),
        "asset origin: a staged file is served byte-identical over loopback"
      );
      const trav = await rawGet(origin.port, "/%2e%2e/origin-secret.txt");
      report(
        trav.status === 403,
        "asset origin: an encoded traversal is refused (403)",
        `status=${trav.status}`
      );
      const linked = await fetch(`${origin.url}/linked.txt`);
      report(
        linked.status === 403,
        "asset origin: a symlink out of the staging root is refused (403)",
        `status=${linked.status}`
      );
      const missing = await fetch(`${origin.url}/nope.png`);
      report(missing.status === 404, "asset origin: an unknown path is a plain 404");
      const post = await fetch(`${origin.url}/asset.png`, { method: "POST" });
      report(post.status === 405, "asset origin: non-GET/HEAD methods are refused (405)");
      report(
        origin.requests.some((r) => r.status === 403) &&
          origin.requests.some((r) => r.status === 200),
        "asset origin: refusals and serves are both in the request log"
      );
      measurements.originRequests = origin.requests;
    } finally {
      await origin.close();
    }
  } finally {
    source.close();
  }
}

function rawGet(port: number, path: string): Promise<{ status: number }> {
  return new Promise((resolvePromise, rejectPromise) => {
    const req = require("node:http").request(
      { host: "127.0.0.1", port, path, method: "GET" },
      (res: { statusCode?: number; resume: () => void }) => {
        res.resume();
        resolvePromise({ status: res.statusCode ?? 0 });
      }
    );
    req.on("error", rejectPromise);
    req.end();
  });
}

// ---------------------------------------------------------------------
// 5. Process ownership, cancellation scope, and the sweep.
// ---------------------------------------------------------------------

async function sectionProcesses(): Promise<void> {
  const chrome = findChrome();
  // An unrelated Chromium: launched directly, with no job token in its
  // environment and no registry record. This stands in for the
  // operator's own browser and for every other tenant of the machine.
  let unrelatedPid = -1;
  let unrelated: ReturnType<typeof spawn> | null = null;
  if (chrome) {
    const cleanEnv = { ...process.env };
    delete cleanEnv.MOTION_JOB_TOKEN;
    delete cleanEnv.MOTION_JOB_ID;
    unrelated = spawn(
      chrome,
      [
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        `--user-data-dir=${join(WORK, "unrelated-profile")}`,
        "--remote-debugging-port=0",
        "about:blank",
      ],
      { env: cleanEnv, stdio: "ignore" }
    );
    unrelatedPid = unrelated.pid ?? -1;
    await waitFor(() => pidAlive(unrelatedPid), 15000, "unrelated chromium to start");
  }

  const outA = join(WORK, "job-a.json");
  const outB = join(WORK, "job-b.json");
  const jobA: IsolatedChild = spawnIsolated(process.execPath, [fixture("sleeper.cjs"), outA], {
    jobId: "mg029-job-a",
    cwd: WORK,
    registry,
    network: "off",
  });
  const jobB: IsolatedChild = spawnIsolated(process.execPath, [fixture("sleeper.cjs"), outB], {
    jobId: "mg029-job-b",
    cwd: WORK,
    registry,
    network: "off",
  });
  try {
    await waitFor(() => existsSync(outA) && existsSync(outB), 15000, "sleeper pid files");
    const a = JSON.parse(readFileSync(outA, "utf8")) as { pid: number; grandchildPid: number };
    const b = JSON.parse(readFileSync(outB, "utf8")) as { pid: number; grandchildPid: number };
    report(
      pidAlive(a.pid) && pidAlive(a.grandchildPid) && pidAlive(b.pid) && pidAlive(b.grandchildPid),
      "processes: two jobs are running with live grandchildren before any termination"
    );
    const recordsA = registry.records("mg029-job-a");
    report(
      recordsA.length === 1 && recordsA[0].pid === jobA.pid && recordsA[0].startTimeTicks !== null,
      "processes: the job's root was recorded with its kernel start-time at launch"
    );

    const termA = await terminateJobProcesses(registry, "mg029-job-a", { graceMs: 400 });
    await waitFor(() => !pidAlive(a.pid) && !pidAlive(a.grandchildPid), 10000, "job A tree to die");
    report(
      termA.terminated.includes(a.pid) && !pidAlive(a.grandchildPid),
      "cancel scope: terminating job A killed its root AND its token-carrying grandchild",
      `terminated=${termA.terminated.join(",")} refused=${JSON.stringify(termA.refused)}`
    );
    report(
      pidAlive(b.pid) && pidAlive(b.grandchildPid),
      "cancel scope: job B (root and grandchild) is untouched by job A's termination"
    );
    if (chrome) {
      report(
        pidAlive(unrelatedPid),
        "cancel scope: the unrelated Chromium survives another job's termination"
      );
    }

    // A stale record in the recycled-pid shape: it names the unrelated
    // Chromium's pid but with a start-time that is not its own. The
    // only correct behavior is refusal.
    if (chrome && unrelatedPid > 0) {
      registry.record({
        jobId: "mg029-stale",
        token: "stale-token-not-carried-by-any-process",
        role: "stale",
        bin: "chrome-headless-shell",
        argv: [],
        cwd: WORK,
        pid: unrelatedPid,
        pgid: null,
        startTimeTicks: 1,
        startedAt: new Date().toISOString(),
        state: "running",
        exitCode: null,
      });
      const termStale = await terminateJobProcesses(registry, "mg029-stale", { graceMs: 200 });
      report(
        termStale.terminated.length === 0 &&
          termStale.refused.some((r) => r.pid === unrelatedPid) &&
          pidAlive(unrelatedPid),
        "cancel scope: a stale record naming another process's pid is refused, and that process lives",
        `refused=${JSON.stringify(termStale.refused)}`
      );
    }

    // SIGTERM escalation: a process that ignores TERM is KILLed, and
    // the report says it was terminated rather than assuming success.
    const outC = join(WORK, "job-c.json");
    spawnIsolated(process.execPath, [fixture("sleeper-stubborn.cjs"), outC], {
      jobId: "mg029-job-c",
      cwd: WORK,
      registry,
      network: "off",
    });
    await waitFor(() => existsSync(outC), 15000, "stubborn sleeper pid file");
    const c = JSON.parse(readFileSync(outC, "utf8")) as { pid: number };
    const termC = await terminateJobProcesses(registry, "mg029-job-c", { graceMs: 300 });
    report(
      termC.terminated.includes(c.pid) && !pidAlive(c.pid),
      "cancel scope: a SIGTERM-ignoring process is escalated to SIGKILL and reported terminated",
      `terminated=${termC.terminated.join(",")}`
    );

    // The shipped sweep: cleans recorded job B, leaves the unrelated
    // Chromium and the stale record's victim alone.
    const sweep = spawnSync(
      "bash",
      [join(SKILL_DIR, "scripts", "sweep-chromium.sh"), REGISTRY_DIR],
      { encoding: "utf8", timeout: 60000 }
    );
    await waitFor(() => !pidAlive(b.pid) && !pidAlive(b.grandchildPid), 10000, "job B sweep");
    report(
      sweep.status === 0 && !pidAlive(b.pid) && !pidAlive(b.grandchildPid),
      "sweep: the shipped sweep script terminates the remaining recorded job (root and grandchild)",
      `status=${sweep.status} out=${(sweep.stdout || "").trim()} err=${(sweep.stderr || "").trim().slice(0, 200)}`
    );
    if (chrome) {
      report(
        pidAlive(unrelatedPid),
        "sweep: the unrelated Chromium survives the sweep (no command-line pattern matching)"
      );
    }
    measurements.sweepOutput = (sweep.stdout || "").trim();
  } finally {
    // Test hygiene: nothing this section started may outlive it.
    await terminateJobProcesses(registry, "mg029-job-a", { graceMs: 100 }).catch(() => undefined);
    await terminateJobProcesses(registry, "mg029-job-b", { graceMs: 100 }).catch(() => undefined);
    await terminateJobProcesses(registry, "mg029-job-c", { graceMs: 100 }).catch(() => undefined);
    if (unrelatedPid > 0 && pidAlive(unrelatedPid)) {
      try {
        process.kill(unrelatedPid, "SIGKILL");
      } catch {
        // Already gone.
      }
    }
    jobA.child.removeAllListeners();
    jobB.child.removeAllListeners();
  }
}

// ---------------------------------------------------------------------
// 6. Network policy and the adapter under it.
// ---------------------------------------------------------------------

async function sectionNetwork(): Promise<void> {
  // A mistyped policy value is a hard refusal, not a silent "off": an
  // operator who asked for a policy and typo'd it must not get an
  // open render. Recognized values (and an unset variable) still
  // parse to their modes.
  let modeCode = "";
  try {
    networkModeFromEnv({ MOTION_RENDER_NETWORK: "sometimes" });
  } catch (err) {
    modeCode = (err as IsolationError).code ?? "";
  }
  report(
    modeCode === "NETWORK_MODE_INVALID" &&
      networkModeFromEnv({}) === "off" &&
      networkModeFromEnv({ MOTION_RENDER_NETWORK: "loopback" }) === "loopback" &&
      networkModeFromEnv({ MOTION_RENDER_NETWORK: "deny" }) === "deny",
    "network policy: an unrecognized MOTION_RENDER_NETWORK value is refused as NETWORK_MODE_INVALID, not silently defaulted to off",
    `code=${modeCode}`
  );

  const probe = probeNetworkNamespace();
  measurements.namespaceProbe = probe;
  report(
    probe.supported,
    `network: a namespace flavor works on this machine (${probe.flavor ?? "none"})`,
    probe.detail
  );
  if (!probe.supported) return;

  const hits: string[] = [];
  const recorder = createServer((req, res) => {
    hits.push(req.url ?? "/");
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("recorded");
  });
  await new Promise<void>((r) => recorder.listen(0, "0.0.0.0", r));
  const port = (recorder.address() as { port: number }).port;
  const loopUrl = `http://127.0.0.1:${port}/hit-loopback`;
  // The second target is the sandbox's own egress proxy: a real
  // off-loopback endpoint an unpoliced process can connect to. (The
  // host's interface address is NOT a usable target on this box: the
  // link is proxy-mediated and self-address connections fail even
  // unpoliced, verified from the shell.)
  const outsideTarget = proxyTcpTarget();
  const targets = [loopUrl, ...(outsideTarget ? [outsideTarget] : [])];
  try {
    // Control: no namespace. The recorder answers and the outside
    // endpoint connects.
    const control = await runIsolated(
      process.execPath,
      [fixture("fetch-worker.cjs"), ...targets],
      { jobId: "mg029-net-control", cwd: WORK, registry, network: "off", timeoutMs: 60000 }
    );
    const hitsAfterControl = hits.length;
    report(
      control.stdout.includes(`${loopUrl} reached`) &&
        (outsideTarget === null || control.stdout.includes(`${outsideTarget} reached`)) &&
        hitsAfterControl >= 1,
      "network control: without the policy the child reaches the recorder and the outside endpoint (targets are real)",
      `stdout=${control.stdout.trim()} hits=${hits.join(",")}`
    );

    // The mechanism itself: inside the namespace there is no default
    // route and no interface but loopback.
    const routesIn = await runIsolated("sh", ["-c", "ip route; ip addr show"], {
      jobId: "mg029-net-routes",
      cwd: WORK,
      registry,
      network: "loopback",
      timeoutMs: 60000,
    });
    report(
      !/^default /m.test(routesIn.stdout) && routesIn.stdout.includes("127.0.0.1"),
      "network policy: the namespace's routing table has no default route, loopback only",
      `routes=${routesIn.stdout.trim().slice(0, 200)}`
    );

    // Under the loopback policy: the namespace's loopback is a
    // different loopback, and there is no route off it.
    const isolated = await runIsolated(
      process.execPath,
      [fixture("fetch-worker.cjs"), ...targets],
      { jobId: "mg029-net-isolated", cwd: WORK, registry, network: "loopback", timeoutMs: 60000 }
    );
    report(
      isolated.stdout.includes(`${loopUrl} blocked`) &&
        (outsideTarget === null || isolated.stdout.includes(`${outsideTarget} blocked`)) &&
        hits.length === hitsAfterControl,
      "network policy: inside the namespace the child reaches neither the host-loopback recorder nor the outside endpoint",
      `stdout=${isolated.stdout.trim()} hits=${hits.join(",")}`
    );

    // Deny: even a server the child itself starts on its own loopback
    // is out of reach of a second namespaced process; the fetch to the
    // host recorder stays blocked too.
    const denied = await runIsolated(
      process.execPath,
      [fixture("fetch-worker.cjs"), loopUrl],
      { jobId: "mg029-net-deny", cwd: WORK, registry, network: "deny", timeoutMs: 60000 }
    );
    report(
      denied.stdout.includes(`${loopUrl} blocked`) && hits.length === hitsAfterControl,
      "network policy: deny leaves the child with no IP path at all",
      `stdout=${denied.stdout.trim()}`
    );

    // The real browser executing a hostile scene.
    const chrome = findChrome();
    if (!chrome) {
      report(false, "network scene: chrome-headless-shell not found in the shared runtime");
    } else {
      const sceneTemplate = readFileSync(fixture("network-scene.html"), "utf8");
      const sceneHtml = sceneTemplate
        .replaceAll("__LOOPBACK_URL__", loopUrl)
        // The second scene target is a dead loopback port: not
        // asserted either way (this box offers a page no usable
        // off-loopback HTTP target; the process-level probes above
        // carry the outside-endpoint proof).
        .replaceAll("__HOSTIP_URL__", "http://127.0.0.1:9/unreachable")
        .replaceAll("__PUBLIC_URL__", "https://example.com/mg029-probe");
      const scenePath = join(WORK, "network-scene.html");
      writeFileSync(scenePath, sceneHtml, "utf8");
      const hitsBeforeSceneControl = hits.length;
      const sceneControl = await runPage({
        chrome,
        profile: join(WORK, "scene-control-profile"),
        htmlPath: scenePath,
        jobId: "mg029-scene-control",
        network: "off",
      });
      report(
        hits.length > hitsBeforeSceneControl,
        "network scene control: the hostile scene reaches the recorder from an unpoliced browser",
        `new hits=${hits.slice(hitsBeforeSceneControl).join(",")} dom=${(sceneControl.stdout.match(/loopback=\w+/) ?? ["?"])[0]}`
      );
      const hitsBeforeSceneIsolated = hits.length;
      const sceneIsolated = await runPage({
        chrome,
        profile: join(WORK, "scene-isolated-profile"),
        htmlPath: scenePath,
        jobId: "mg029-scene-isolated",
        network: "loopback",
      });
      report(
        hits.length === hitsBeforeSceneIsolated &&
          sceneIsolated.stdout.includes("loopback=blocked"),
        "network scene: inside the policy the scene's fetches and beacons never leave the namespace",
        `new hits=${hits.slice(hitsBeforeSceneIsolated).join(",")} dom=${(sceneIsolated.stdout.match(/loopback=\w+/) ?? ["?"])[0]} stderr=${sceneIsolated.stderr.slice(0, 160)}`
      );
      measurements.recorderHits = hits;
    }

    // The production adapter rendering under the policy.
    await sectionAdapterUnderPolicy(port);
  } finally {
    recorder.close();
  }
}

async function sectionAdapterUnderPolicy(_recorderPort: number): Promise<void> {
  const src = join(SKILL_DIR, "tests", "fixtures", "modes", "powerpoint_graphic");
  const jobDir = join(WORK, "adapter-job");
  rmSync(jobDir, { recursive: true, force: true });
  cpSync(src, jobDir, { recursive: true });
  const scenePath = join(jobDir, "scenes", "bar-01.json");
  const scene = JSON.parse(readFileSync(scenePath, "utf8")) as Record<string, unknown>;
  scene.engine = "hyperframes";
  writeFileSync(scenePath, JSON.stringify(scene, null, 2) + "\n", "utf8");
  const manifest = JSON.parse(readFileSync(join(jobDir, "manifest.json"), "utf8")) as Manifest;
  (manifest.rendering as { default_engine: string }).default_engine = "hyperframes";
  writeFileSync(join(jobDir, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n", "utf8");
  const job: ValidatedMotionJob = { jobDir, jobId: manifest.job_id, manifest };

  const savedEnv = {
    MOTION_RENDER_NETWORK: process.env.MOTION_RENDER_NETWORK,
    MOTION_PROCESS_REGISTRY_DIR: process.env.MOTION_PROCESS_REGISTRY_DIR,
    KIE_API_KEY: process.env.KIE_API_KEY,
    FISH_AUDIO_API_KEY: process.env.FISH_AUDIO_API_KEY,
  };
  process.env.MOTION_RENDER_NETWORK = "loopback";
  process.env.MOTION_PROCESS_REGISTRY_DIR = REGISTRY_DIR;
  process.env.KIE_API_KEY = PLANTED.KIE_API_KEY;
  process.env.FISH_AUDIO_API_KEY = PLANTED.FISH_AUDIO_API_KEY;
  try {
    const adapter = new HyperframesAdapter();
    const still = await adapter.renderStill(job, 75);
    const outPath = join(jobDir, still.outputPaths[0]);
    report(
      still.exitCode === 0 && existsSync(outPath),
      "adapter under policy: a real Hyperframes still renders with the loopback namespace in force",
      `outputs=${still.outputPaths.join(",")}`
    );
    const adapterRegistry = new ProcessRegistry(REGISTRY_DIR);
    const records = adapterRegistry.records(manifest.job_id);
    const registryText = JSON.stringify(adapterRegistry.read(manifest.job_id) ?? {});
    report(
      records.length > 0 && records.every((r) => r.startTimeTicks !== null),
      "adapter under policy: every engine child was recorded with a start-time identity anchor",
      `records=${records.length} roles=${records.map((r) => r.role).join(",")}`
    );
    report(
      PLANTED_VALUES.every((v) => !registryText.includes(v)),
      "adapter under policy: no planted secret appears in any recorded process record"
    );
    measurements.adapterRecords = records.map((r) => ({
      role: r.role,
      pid: r.pid,
      state: r.state,
    }));
  } finally {
    for (const [k, v] of Object.entries(savedEnv)) {
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
  }
}

// ---------------------------------------------------------------------
// 7. Command-like copy is data.
// ---------------------------------------------------------------------

async function sectionCopy(): Promise<void> {
  const marker = join(WORK, "pwned-marker");
  const copy = `Sale ends soon! "; rm -rf / ; $(touch ${marker}) \`touch ${marker}\` && echo owned`;
  const echoed = await runIsolated(process.execPath, [fixture("echo-argv.cjs"), copy], {
    jobId: "mg029-copy",
    cwd: WORK,
    registry,
    network: "off",
  });
  let argvSeen: string[] = [];
  try {
    argvSeen = JSON.parse(echoed.stdout) as string[];
  } catch {
    argvSeen = [];
  }
  report(
    argvSeen.length === 1 && argvSeen[0] === copy && !existsSync(marker),
    "copy: shell-shaped copy passed as an argument arrives byte-identical and executes nothing",
    `argv=${JSON.stringify(argvSeen)} marker=${existsSync(marker)}`
  );

  const chrome = findChrome();
  if (chrome) {
    const pagePath = join(WORK, "copy-page.html");
    writeFileSync(
      pagePath,
      "<!doctype html><html><body><div id=\"stage\"></div><script>" +
        `document.getElementById("stage").textContent = ${JSON.stringify(copy)};` +
        "</script></body></html>",
      "utf8"
    );
    const dom = await runPage({
      chrome,
      profile: join(WORK, "copy-profile"),
      htmlPath: pagePath,
      jobId: "mg029-copy-page",
      network: "off",
      waitMs: 3000,
    });
    report(
      dom.stdout.includes("$(touch") && !existsSync(marker),
      "copy: shell-shaped copy set as page text renders as text in the DOM and executes nothing",
      `marker=${existsSync(marker)}`
    );
  }
}

// ---------------------------------------------------------------------

async function main(): Promise<void> {
  await sectionEnv();
  await sectionRedaction();
  sectionPaths();
  await sectionAssets();
  await sectionProcesses();
  await sectionNetwork();
  await sectionCopy();
  measurements.passed = passed;
  measurements.failed = failed;
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  writeFileSync(
    join(EVIDENCE_DIR, "measurements.json"),
    JSON.stringify(measurements, null, 2) + "\n",
    "utf8"
  );
  console.log(`Security: ${passed}/${passed + failed} cases passed, ${failed} failed.`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((err: unknown) => {
  console.error(`run-security crashed: ${(err as Error).stack ?? String(err)}`);
  process.exit(1);
});
