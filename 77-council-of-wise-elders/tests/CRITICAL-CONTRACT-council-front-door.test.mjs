#!/usr/bin/env node
// CRITICAL CONTRACT — council-front-door-before-routing (CTR-194)
//
// Created with the CTR-194 source fix, NOT RUN in that lane (the lane was
// barred from test suites). Run it manually with:
//   node 77-council-of-wise-elders/tests/CRITICAL-CONTRACT-council-front-door.test.mjs
//
// It locks the two halves of the defect: an explicit Council ask must be
// handled by the front door before any routing policy, and every generator that
// stamps or injects that policy must carry the same narrow exception. It is
// offline, reads repo files only, and writes nothing.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SKILL = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = resolve(SKILL, "..");
const read = (rel) => readFileSync(join(REPO, rel), "utf8");
const readSkill = (rel) => readFileSync(join(SKILL, rel), "utf8");

const EXCEPTION = "COUNCIL ASK (narrow exception)";
const FRONTDOOR = "council-ask";
const CHAMBER = "`Chamber link:`";

// 1. Canonical V4.3 policy carries the narrow exception and the front-door rule.
const policyModule = read("shared-utils/ceo_execution_policy.py");
assert.ok(policyModule.includes(EXCEPTION), "POLICY lacks the narrow Council-ask exception");
assert.ok(policyModule.includes(FRONTDOOR), "POLICY does not name the Council front door");
assert.ok(policyModule.includes("NOT routed through mc-route.sh"), "POLICY exception does not carve out routing");
assert.ok(policyModule.includes(CHAMBER), "POLICY does not require the exact Chamber link line");

// 2. Both managed carriers are byte-identical to POLICY.
const py = spawnSync("python3", ["-c", [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(join(REPO, "shared-utils"))})`,
  "from ceo_execution_policy import POLICY",
  "sys.stdout.write(POLICY)",
].join("; ")], { encoding: "utf8" });
assert.equal(py.status, 0, `could not read POLICY: ${py.stderr}`);
const POLICY = py.stdout;
for (const rel of ["AGENTS.md", "23-ai-workforce-blueprint/master-orchestrator-dept/SOP-00-Owner-Task-Routing.md"]) {
  const text = read(rel);
  const marker = "<!-- CEO_EXECUTION_POLICY_V4_3 -->";
  const end = "<!-- END CEO_EXECUTION_POLICY_V4_3 -->";
  const start = text.indexOf(marker) + marker.length + 1;
  assert.equal(text.slice(start, text.indexOf(end)), POLICY, `${rel} drifted from POLICY`);
}
const classifier = read("shared-utils/intake_classifier_policy.txt");
assert.ok(classifier.startsWith(POLICY), "intake classifier policy drifted from POLICY");

// 3. The always-injected routing preamble is POLICY, and the off-mode fallback
//    also names the exception.
const dist = read("extensions/ceo-routing-doctrine/dist/index.js");
assert.ok(dist.includes(EXCEPTION), "ceo-routing-doctrine fallback lacks the Council exception");
assert.ok(dist.includes(FRONTDOOR), "ceo-routing-doctrine preamble does not name the front door");

// 4. The presentation and skill-intent reflexes both carry the narrow exception.
for (const rel of ["scripts/apply-routing-fix.sh", "scripts/apply-fleet-standards.sh"]) {
  assert.ok(read(rel).includes("COUNCIL ASK EXCEPTION (narrow)"), `${rel} reflex lacks the Council exception`);
}
assert.ok(read("scripts/apply-fleet-standards.sh").includes("An explicit Council ask is owned by Skill 77's front door"),
  "skill-intent table does not exclude explicit Council asks");

// 5. The remote-rescue bootstrap teaches the same boundary.
const rr = read("15-blackceo-team-management/templates/remote-rescue/AGENTS.md");
for (const needle of ["Explicit Council ask (not board work)", FRONTDOOR, CHAMBER, "127.0.0.1"]) {
  assert.ok(rr.includes(needle), `remote-rescue template lacks ${needle}`);
}

// 6. wire.sh installs/registers/provisions the interceptor; it does not only
//    copy the skill folder.
const wire = readSkill("wire.sh");
assert.ok(wire.includes("install-council-plugin.mjs"), "wire.sh never invokes the plugin installer");
assert.ok(wire.includes("COUNCIL_PLUGIN:"), "wire.sh does not report the plugin state");
const installer = readSkill("scripts/install-council-plugin.mjs");
for (const needle of ["provision.mjs", "plugins.entries", "plugins.load.paths", "plugins.allow",
  "PLUGIN_API_INCOMPATIBLE", "PLUGIN_BINDING_UNRESOLVED", "PLUGIN_CONFIG_INVALID",
  "atomicWrite", "config", "validate"]) {
  assert.ok(installer.includes(needle), `install-council-plugin.mjs lacks ${needle}`);
}
assert.ok(installer.includes("for (const field of REQUIRED_FIELDS) nextConfig[field] = derived[field]"),
  "installer does not take sender/identity values from the box's own provision output");
assert.ok(!installer.includes("allowFrom"), "installer must never write allowFrom");
const provision = readSkill("extensions/council-before-dispatch/provision.mjs");
for (const needle of ["function peerId", "isDirectPeer", "accountNames.length === 1",
  "authorizedPeers", "AMBIGUOUS_CONVERSATION"]) {
  assert.ok(provision.includes(needle), `provision.mjs lacks the 2026.10.8 binding rule: ${needle}`);
}
const pluginPkg = JSON.parse(readSkill("extensions/council-before-dispatch/package.json"));
const pluginManifest = JSON.parse(readSkill("extensions/council-before-dispatch/openclaw.plugin.json"));
assert.equal(pluginPkg.version, pluginManifest.version, "plugin package and manifest versions disagree");

// 7. Readiness names the missing hook/binding/origin precisely.
const verify = readSkill("scripts/verify-council-box.sh");
for (const code of ["PLUGIN_NOT_INSTALLED", "PLUGIN_NOT_REGISTERED", "PLUGIN_NOT_ALLOWED",
  "PLUGIN_LOAD_PATH_MISSING", "PLUGIN_BINDING_UNRESOLVED", "PLUGIN_BINDING_DRIFT",
  "PLUGIN_NOT_LOADED", "PLUGIN_HOOK_UNVERIFIED", "PUBLIC_ORIGIN_UNSET"]) {
  assert.ok(verify.includes(code), `verify-council-box.sh lacks ${code}`);
}
const pluginVerify = readSkill("scripts/verify-council-plugin.mjs");
assert.ok(pluginVerify.includes("provision.mjs"), "binding verifier does not compare provision.mjs");
assert.ok(pluginVerify.includes("plugins"), "binding verifier does not read the loaded registry");

// 8. A NOOP build cannot pass as a reconciled box: the active pointer, the
//    service receipt, the launcher and the LIVE process are compared, and a
//    healthy old process is refused.
for (const needle of ["running_release", "COUNCIL_RECONCILE:", "FORCE_RESTART",
  "SERVICE_RELEASE_MISMATCH", "service-launch.mjs"]) {
  assert.ok(wire.includes(needle), `wire.sh lacks ${needle}`);
}
assert.ok(readSkill("scripts/install-runtime.mjs").includes("serviceReconcileProblems"),
  "install-runtime NOOP does not report service/launcher drift");
assert.ok(readSkill("scripts/install-runtime.mjs").includes("WARN reconcile:"),
  "install-runtime NOOP does not emit the reconcile warning");
assert.ok(verify.includes("SERVICE_RELEASE_MISMATCH"),
  "verify-council-box.sh does not verify the live process release");
const launcher = readSkill("wire.sh");
assert.ok(launcher.includes("COUNCIL_SERVICE_DATA_DIR") && launcher.includes("COUNCIL_SERVICE_PORT"),
  "launcher reconciliation must preserve the authoritative store and port");
assert.ok(readSkill("runtime/src/service/front-door.ts").includes("/report.pdf"),
  "the served runtime must keep the PDF report route the reconciled process has to expose");

// 9. Packaging can reuse an unchanged runtime build without recompiling it.
assert.ok(readSkill("scripts/build-bundles.mjs").includes("COUNCIL_PACKAGE_REUSE_RUNTIME"),
  "build-bundles has no unchanged-runtime reuse path");

// 9. The shipped extension package still contains every declared file.
for (const rel of ["index.js", "index.ts", "lib/core.mjs", "lib/entry-validate.mjs", "provision.mjs",
  "openclaw.plugin.json", "package.json", "INSTALL.md", "CONTRACT.md"]) {
  readSkill(`extensions/council-before-dispatch/${rel}`);
}

console.log("CRITICAL CONTRACT council-front-door-before-routing: PASS");
