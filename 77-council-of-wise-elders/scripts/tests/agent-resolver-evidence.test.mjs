// Agent-resolver evidence for the selected-tree gate (scripts/agent-resolver-evidence.mjs)
// and the second gate pass wire.sh runs with it. A box with several Council
// copies used to fail every roll with "agent selection unproven" unless a human
// exported COUNCIL_AGENT_SKILL_DIR; the real OpenClaw resolver is now asked
// instead, while the gate itself stays exactly as strict (no answer = refusal).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { chmodSync, cpSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { defaultAgentId, resolveAgentSkillDir } from "../agent-resolver-evidence.mjs";

const SKILL = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const GOOD_ENTRY = "#!/usr/bin/env node\nif (process.argv.includes('--help')) process.exit(0);\nprocess.exit(2);\n";
const NAME = "council-of-wise-elders";

function tmp(t) {
  const d = realpathSync(mkdtempSync(join(tmpdir(), "cwe-agent-ev-")));
  t.after(() => rmSync(d, { recursive: true, force: true }));
  return d;
}

// A fake `openclaw`: prints $FAKE_ANSWER (a file) and records its argv.
function fakeCli(dir, answer, { code = 0 } = {}) {
  mkdirSync(dir, { recursive: true });
  const cli = join(dir, "openclaw");
  writeFileSync(join(dir, "answer.json"), typeof answer === "string" ? answer : JSON.stringify(answer));
  writeFileSync(cli, `#!/bin/sh\necho "$@" >> "${dir}/argv.log"\ncat "${dir}/answer.json"\nexit ${code}\n`);
  chmodSync(cli, 0o755);
  return cli;
}

const info = (baseDir, name = NAME) => ({ name, baseDir, filePath: `${baseDir}/SKILL.md` });

test("agent id order matches obs_default_agent", () => {
  assert.equal(defaultAgentId({ agents: { defaults: { systemAgent: { agentId: "sys" } } } }, {}), "sys");
  assert.equal(defaultAgentId({ agents: { entries: { b: {}, a: { default: true } } } }, {}), "a");
  assert.equal(defaultAgentId({ agents: { list: [{ id: "x" }, { id: "main" }] } }, {}), "main");
  assert.equal(defaultAgentId({ agents: { entries: { z: {}, m: {} } } }, {}), "m");
  assert.equal(defaultAgentId({}, {}), "");
  assert.equal(defaultAgentId({ agents: { entries: { a: {} } } }, { OPENCLAW_AGENT_ID: "env" }), "env");
});

test("the resolver's baseDir is returned, asked for the default agent", (t) => {
  const d = tmp(t);
  const cli = fakeCli(join(d, "bin"), info("/srv/agents/skills/council-of-wise-elders"));
  const r = resolveAgentSkillDir({ cli, config: { agents: { defaults: { systemAgent: { agentId: "main" } } } }, env: { PATH: "/usr/bin:/bin" }, home: d });
  assert.equal(r.dir, "/srv/agents/skills/council-of-wise-elders");
  assert.equal(readFileSync(join(d, "bin", "argv.log"), "utf8").trim(), `skills info ${NAME} --agent main --json`);
});

test("no answer is no evidence: error, other skill, relative path, not JSON, nonzero exit", (t) => {
  const d = tmp(t);
  const ask = (answer, opts) => resolveAgentSkillDir({ cli: fakeCli(join(d, String(Math.random())), answer, opts), config: {}, env: { PATH: "/usr/bin:/bin" }, home: d });
  assert.equal(ask({ ok: false, error: { message: "Pass --agent <id>." } }).dir, null);
  assert.equal(ask(info("/srv/other", "some-other-skill")).dir, null);
  assert.equal(ask(info("relative/skills/x")).dir, null);
  assert.equal(ask("not json at all").dir, null);
  assert.equal(ask(info("/srv/x"), { code: 1 }).dir, null);
});

// ---- wire.sh's second gate pass, run from the real wire.sh text -------------
function copyTree(dir, version) {
  mkdirSync(join(dir, "advisors"), { recursive: true });
  mkdirSync(join(dir, "runtime", "dist"), { recursive: true });
  writeFileSync(join(dir, "version"), `${version}\n`);
  writeFileSync(join(dir, "skill-version.txt"), `v${version}\n`);
  writeFileSync(join(dir, "SKILL.md"), `---\nname: ${NAME}\nversion: ${version}\n---\n\nConvening is the approval: no grant to resolve.\n`);
  writeFileSync(join(dir, "runtime", "dist", "blackceo-council.mjs"), GOOD_ENTRY);
  writeFileSync(join(dir, "manifest.json"), JSON.stringify({
    skill_version: version,
    runtime_entry: {
      path: "runtime/dist/blackceo-council.mjs",
      sha256: createHash("sha256").update(GOOD_ENTRY).digest("hex"),
      bytes: Buffer.byteLength(GOOD_ENTRY),
    },
  }));
}

// The gate block of wire.sh (from `GT_RC=0` to the verdict `if`), run against a
// fixture home that holds two copies: the wired one and a shadowing ~/.agents one.
function runWireGate(t, { agentVersion, answer }) {
  const home = tmp(t);
  const wired = join(home, ".openclaw", "skills", `77-${NAME}`);
  const shadow = join(home, ".agents", "skills", NAME);
  copyTree(wired, "1.0.69");
  // SKILL_DIR is the wired fixture; it carries the real gate scripts it runs.
  cpSync(join(SKILL, "scripts"), join(wired, "scripts"), { recursive: true });
  if (agentVersion === "1.0.69") cpSync(wired, shadow, { recursive: true });
  else copyTree(shadow, agentVersion);
  const bin = join(home, "bin");
  fakeCli(bin, answer(shadow));
  const text = readFileSync(join(SKILL, "wire.sh"), "utf8");
  const block = text.slice(text.indexOf("\nGT_RC=0\n"), text.indexOf('\nif [ "$GT_RC" -ne 0 ]; then\n  say "NOT_READY TREE_GATE'));
  assert.ok(block.includes("GT_ARGS="), "gate block not found in wire.sh");
  const run = join(home, "run.sh");
  writeFileSync(run, `set -u\nNODE='${process.execPath}'\nSKILL_DIR='${wired}'\nP='${join(home, "p")}'\nHOME='${home}'\nOC='${join(home, ".openclaw")}'\n${block}\necho "GT_RC=$GT_RC"\n`);
  const r = spawnSync("bash", [run], {
    encoding: "utf8",
    env: { PATH: `${bin}:${dirname(process.execPath)}:/usr/bin:/bin`, HOME: home },
  });
  return { out: `${r.stdout}${r.stderr}`, home };
}

test("wire.sh: several copies, no env, the resolver names the current copy: the gate passes", (t) => {
  const { out } = runWireGate(t, { agentVersion: "1.0.69", answer: (shadow) => info(shadow) });
  assert.match(out, /SELECTED-TREE: OK/);
  assert.match(out, /GT_RC=0/);
  assert.doesNotMatch(out, /agent selection unproven/);
});

test("wire.sh: the resolver names a STALE shadow copy: still refused, with the real reason", (t) => {
  const { out } = runWireGate(t, { agentVersion: "1.0.59", answer: (shadow) => info(shadow) });
  assert.match(out, /updating only an unused directory/);
  assert.match(out, /GT_RC=1/);
});

test("wire.sh: the resolver gives no answer: the selection stays unproven and refused", (t) => {
  const { out } = runWireGate(t, { agentVersion: "1.0.69", answer: () => ({ ok: false, error: { message: "Pass --agent <id>." } }) });
  assert.match(out, /agent selection unproven/);
  assert.match(out, /GT_RC=1/);
});

test("the gate CLI started through a symlinked path still runs (it must never pass by not running)", (t) => {
  const d = tmp(t);
  symlinkSync(join(SKILL, "scripts"), join(d, "linked-scripts"));
  const r = spawnSync(process.execPath, [join(d, "linked-scripts", "selected-tree-gate.mjs"), "--skill-dir", join(d, "nowhere"), "--home", d, "--no-load"], { encoding: "utf8" });
  assert.match(r.stdout, /SELECTED-TREE: (OK|FAIL)/);
  assert.equal(r.status, 1);
});
