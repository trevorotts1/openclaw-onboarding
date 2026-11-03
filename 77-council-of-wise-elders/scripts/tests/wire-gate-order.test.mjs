// wire.sh gate ordering: a selected-tree gate refusal must never leave
// active.json naming a release the service and the front-door shim do not run.
//
// The check runs the REAL provisioner against a throwaway HOME. Every service
// command (launchctl, pm2, curl, cloudflared, openclaw) is a stub placed FIRST
// on PATH that records its argv, so nothing on the operator machine is started
// and an empty mutation list is meaningful. A positive control proves the same
// stubs do record mutations when they are asked to.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const skillDir = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const wire = join(skillDir, "wire.sh");
const STUBBED = ["launchctl", "pm2", "curl", "cloudflared", "openclaw"];
const MUTATION = /^(?:launchctl (?:bootstrap|bootout|kickstart)|pm2 )/m;

const sha256 = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");

function executable(dir, name, body) {
  const path = join(dir, name);
  writeFileSync(path, body);
  chmodSync(path, 0o755);
  return path;
}

function writeStubs(dir, log) {
  mkdirSync(dir, { recursive: true });
  for (const name of STUBBED) {
    executable(dir, name, `#!/bin/sh\nprintf '%s %s\\n' "${name}" "$*" >> "$STUBLOG"\nexit 1\n`);
  }
  writeFileSync(log, "");
  return dir;
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

// Every regular file under the fixture HOME, hashed, so "nothing was written"
// is a measurement and not an assumption. The stub log is excluded because the
// stubs append to it by design.
function snapshot(root, log) {
  const out = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (full === log) continue;
      if (entry.isDirectory()) walk(full);
      else if (entry.isFile()) out.push(`${sha256(full)}  ${full}`);
    }
  };
  walk(root);
  return out.sort().join("\n");
}

function buildFixture(t) {
  const home = mkdtempSync(join(tmpdir(), "cwe-wire-order-"));
  t.after(() => rmSync(home, { recursive: true, force: true }));
  const oc = join(home, ".openclaw");
  const prefix = join(oc, "council-runtime");
  const release = join(prefix, "releases", "rel-old");
  mkdirSync(join(release, "dist"), { recursive: true });
  mkdirSync(join(release, "scripts"), { recursive: true });
  mkdirSync(join(prefix, "bin"), { recursive: true });
  mkdirSync(join(oc, "council-data"), { recursive: true });
  // A second council tree on the box with no agent-resolver answer: this is the
  // gate refusal the ordering has to survive (the real two-root shape).
  mkdirSync(join(home, ".agents", "skills", "council-of-wise-elders"), { recursive: true });
  writeFileSync(join(home, ".agents", "skills", "council-of-wise-elders", "SKILL.md"), "---\nname: council-of-wise-elders\n---\n");
  writeFileSync(join(release, "dist", "blackceo-council.mjs"), '#!/usr/bin/env node\nconsole.log("old release");\n');
  writeFileSync(join(release, "scripts", "service-launch.mjs"), '// fixture launcher target\n');
  const mark = "# managed-by: 77-council-of-wise-elders/wire.sh";
  writeFileSync(
    join(prefix, "active.json"),
    `${JSON.stringify({
      releaseId: "rel-old",
      releasePath: release,
      nodeExecutable: process.execPath,
      dataDir: join(oc, "council-data"),
    }, null, 2)}\n`,
  );
  writeFileSync(join(prefix, "releases", "install-record.json"), `${JSON.stringify({ skill_dir: skillDir }, null, 2)}\n`);
  const shim = join(prefix, "bin", "blackceo-council");
  writeFileSync(shim, `#!/bin/sh\n${mark}\nexec ${process.execPath} ${join(release, "dist", "blackceo-council.mjs")} "$@"\n`);
  chmodSync(shim, 0o755);
  const launcher = join(prefix, "bin", "council-service");
  writeFileSync(launcher, `#!/bin/sh\n${mark}\nCOUNCIL_SERVICE_DATA_DIR='${join(oc, "council-data")}'; export COUNCIL_SERVICE_DATA_DIR\nexec ${process.execPath} ${join(release, "scripts", "service-launch.mjs")}\n`);
  chmodSync(launcher, 0o755);
  writeFileSync(
    join(prefix, "service.json"),
    `${JSON.stringify({ schema: "council-service/v1", release_id: "rel-old", launcher_sha256: sha256(launcher) }, null, 2)}\n`,
  );
  return { home, oc, prefix, shim, launcher, release };
}

test("a selected-tree gate refusal writes nothing and leaves active.json, service.json and the shim on the same release", async (t) => {
  assert.ok(readdirSync(skillDir).includes("wire.sh"), `the provisioner must be at ${wire}`);
  const fixture = buildFixture(t);
  const stubDir = join(fixture.home, ".stubs");
  const log = join(fixture.home, ".stublog");
  writeStubs(stubDir, log);
  const port = await freePort();

  const before = snapshot(fixture.home, log);
  const result = spawnSync("/bin/bash", [wire, "--idempotent"], {
    encoding: "utf8",
    timeout: 120_000,
    env: {
      HOME: fixture.home,
      OPENCLAW_ROOT: fixture.oc,
      COUNCIL_WIRE_PLATFORM: "mac",
      COUNCIL_NODE: process.execPath,
      COUNCIL_NPM: join(dirname(process.execPath), "npm"),
      COUNCIL_SERVICE_PORT: String(port),
      COUNCIL_DATA_DIR: join(fixture.oc, "council-data"),
      STUBLOG: log,
      PATH: `${stubDir}:${dirname(process.execPath)}:/usr/bin:/bin:/usr/sbin:/sbin`,
    },
  });
  const out = `${result.stdout ?? ""}${result.stderr ?? ""}`;
  const calls = readFileSync(log, "utf8");

  // The refusal is the intended one, from the gate, not an unrelated early exit.
  assert.equal(result.status, 1, out);
  assert.match(out, /agent selection unproven/);
  assert.match(out, /COUNCIL_WIRE: NOT_READY TREE_GATE/);
  // The stub was really the command wire.sh ran, and nothing was mutated.
  assert.match(calls, /^launchctl print /m);
  assert.doesNotMatch(calls, MUTATION);
  // Agreement: active.json names the release the shim and service.json run.
  const active = JSON.parse(readFileSync(join(fixture.prefix, "active.json"), "utf8"));
  assert.equal(active.releaseId, "rel-old");
  assert.ok(readFileSync(fixture.shim, "utf8").includes(active.releasePath), "the front-door shim must exec the release active.json names");
  assert.ok(readFileSync(fixture.launcher, "utf8").includes(join("releases", "rel-old", "scripts", "service-launch.mjs")));
  assert.equal(JSON.parse(readFileSync(join(fixture.prefix, "service.json"), "utf8")).release_id, active.releaseId);
  // Nothing at all was written on the way to the refusal.
  assert.equal(snapshot(fixture.home, log), before, "a gate refusal must not write to the install");

  // Positive control: the same stubs DO record a mutation when one is asked for,
  // so the empty mutation list above is evidence and not a broken filter.
  spawnSync("/bin/sh", [join(stubDir, "launchctl"), "bootstrap", "gui/1/x"], { env: { ...process.env, STUBLOG: log } });
  spawnSync("/bin/sh", [join(stubDir, "pm2"), "restart", "council-of-wise-elders"], { env: { ...process.env, STUBLOG: log } });
  assert.match(readFileSync(log, "utf8"), /^launchctl bootstrap /m);
  assert.match(readFileSync(log, "utf8"), MUTATION);
});

test("the provisioner runs the selected-tree gate before it builds the runtime", () => {
  // Ordering is the invariant, not a comment: the gate block must come before
  // the install-runtime invocation, so a refusal cannot follow an activation.
  const source = readFileSync(wire, "utf8");
  const gate = source.indexOf('scripts/selected-tree-gate.mjs" "${GT_ARGS[@]}"');
  const install = source.indexOf('scripts/install-runtime.mjs" --idempotent');
  assert.ok(gate > 0, "the gate invocation must exist");
  assert.ok(install > 0, "the installer invocation must exist");
  assert.ok(gate < install, "the gate must run before install-runtime");
  // And the shim/service block is after both, so a refusal never reaches it.
  const launcher = source.indexOf("# ------------------------------------------------- 7. generated launcher + shim");
  assert.ok(launcher > install, "the launcher and service block must come after the build");
  assert.ok(statSync(wire).size > 0);
});
