import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  DEFAULT_INTERVAL_SECONDS,
  HOST_COMMAND_PATHS,
  LAUNCHD_SCHEMA,
  buildLaunchAgentPlist,
  launchctlCommands,
  verifyCommandPaths,
} from "../launchd.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const UID = process.getuid();
const PLIST = join(
  homedir(),
  "Library/LaunchAgents/ai.blackceo.wise-elders.supervisor.plist",
);

test("launchctl resolves to the real executable on THIS host", () => {
  assert.equal(HOST_COMMAND_PATHS.launchctl, "/bin/launchctl");
  const commands = launchctlCommands({
    label: "ai.blackceo.wise-elders.supervisor",
    plist_path: PLIST,
    uid: UID,
  });
  const checks = verifyCommandPaths(commands);
  assert.equal(checks.length, 1);
  assert.deepEqual(checks[0], { path: "/bin/launchctl", executable: true });
});

test("the command arrays are exactly the launchctl invocation forms", () => {
  const label = "ai.blackceo.wise-elders.supervisor";
  const commands = launchctlCommands({ label, plist_path: PLIST, uid: UID });
  const target = `gui/${UID}`;
  const service = `${target}/${label}`;
  assert.equal(commands.schema, LAUNCHD_SCHEMA);
  assert.deepEqual(commands.start, ["/bin/launchctl", "bootstrap", target, PLIST]);
  assert.deepEqual(commands.status, ["/bin/launchctl", "print", service]);
  assert.deepEqual(commands.stop, ["/bin/launchctl", "bootout", target, PLIST]);
  assert.deepEqual(commands.restart, ["/bin/launchctl", "kickstart", "-k", service]);
  assert.equal(commands.installed, false);
  assert.equal(commands.registered, false);
});

test("the plist content is a ten-minute LaunchAgent with real absolute arguments", () => {
  const plist = buildLaunchAgentPlist({
    label: "ai.blackceo.wise-elders.supervisor",
    program_arguments: ["/usr/local/bin/node", "/opt/wise-elders/supervisor.mjs"],
    plist_path: PLIST,
    output_path: "/tmp/supervisor.out.log",
    error_path: "/tmp/supervisor.err.log",
    working_directory: "/opt/wise-elders",
    environment: { ZONE: "operator", BETA: "a&b" },
  });
  assert.equal(plist.schema, LAUNCHD_SCHEMA);
  assert.equal(plist.installed, false);
  assert.equal(plist.registered, false);
  assert.equal(plist.interval_seconds, DEFAULT_INTERVAL_SECONDS);
  assert.match(plist.content, /<key>Label<\/key>/);
  assert.match(plist.content, /ai\.blackceo\.wise-elders\.supervisor/);
  assert.match(plist.content, /<string>\/usr\/local\/bin\/node<\/string>/);
  assert.match(plist.content, /<key>StartInterval<\/key>\n  <integer>600<\/integer>/);
  assert.match(plist.content, /<key>RunAtLoad<\/key>\n  <false\/>/);
  assert.match(plist.content, /<string>a&amp;b<\/string>/);
  assert.equal(plist.content.includes("Date.now"), false);
  assert.equal(plist.plist_path, PLIST);
});

test("the module cannot register a service: no process spawning at all", () => {
  const source = readFileSync(join(here, "..", "launchd.mjs"), "utf8");
  for (const forbidden of [
    "node:child_process",
    "spawnSync",
    "spawn(",
    "execSync",
    "execFileSync",
    '"load"',
    '"unload"',
  ]) {
    assert.equal(source.includes(forbidden), false, `launchd.mjs must not contain ${forbidden}`);
  }
});
