// Durable front door + desktop pop (CTR-103) - the QC blocker on CTR-102:
//   * `wire.sh` baked $SKILL_DIR/scripts/council-entry.mjs into the installed
//     `council-ask` shim. When wire.sh runs from a lane worktree or a temporary
//     clone, post-merge hygiene deletes that checkout and the installed front
//     door becomes `node MODULE_NOT_FOUND`.
//   * the desktop pop was gated on THIS subprocess's `launchctl managername`
//     being Aqua, so a gateway service context silently skipped it while the
//     docs promised it always fired.
// Every check here runs in a sandbox: no network, no real council, no paid
// call, no browser, no service. The pop is exercised with PATH stubs only.
import assert from "node:assert/strict";
import { chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const SCRIPTS = join(dirname(fileURLToPath(import.meta.url)), "..");

function sandbox(t) {
  const d = realpathSync(mkdtempSync(join(tmpdir(), "cwe-frontdoor-")));
  t.after(() => rmSync(d, { recursive: true, force: true }));
  return d;
}

function writeExe(path, body) {
  writeFileSync(path, body);
  chmodSync(path, 0o755);
  return path;
}

// A throwaway "skill checkout" holding only the two front-door files.
function fakeSkillCheckout(root) {
  const dir = join(root, "checkout", "77-council-of-wise-elders");
  mkdirSync(join(dir, "scripts"), { recursive: true });
  for (const f of ["council-entry.mjs", "chamber-visual.sh"]) {
    copyFileSync(join(SCRIPTS, f), join(dir, "scripts", f));
  }
  return dir;
}

test("the installed front door still runs after the checkout that installed it is gone", (t) => {
  const d = sandbox(t);
  const skill = fakeSkillCheckout(d);
  const prefix = join(d, "council-runtime");

  const install = spawnSync("bash", [join(SCRIPTS, "install-front-door.sh"), prefix, "rel-test", skill, process.execPath], { encoding: "utf8" });
  assert.equal(install.status, 0, install.stderr);
  const entry = install.stdout.trim();
  assert.equal(entry, join(prefix, "frontdoor", "rel-test", "scripts", "council-entry.mjs"));
  assert.ok(existsSync(entry), "installed entry must exist");
  assert.ok(existsSync(join(dirname(entry), "chamber-visual.sh")), "the pop helper must be installed beside the entry");

  // The QC failure shape: delete the source checkout, then run the front door.
  rmSync(join(d, "checkout"), { recursive: true, force: true });
  assert.equal(existsSync(join(skill, "scripts", "council-entry.mjs")), false, "source checkout is gone");

  const env = {
    HOME: d,
    PATH: process.env.PATH,
    WISE_ELDERS_SERVICE_JSON: join(d, "absent-service.json"),
    WISE_ELDERS_SERVICE_ORIGIN: "http://127.0.0.1:9", // closed port: no service, no network
  };
  const run = spawnSync(process.execPath, [entry, "authority"], { encoding: "utf8", env, timeout: 30_000 });
  assert.equal(run.status, 3, `expected the typed not-ready exit, got ${run.status}: ${run.stderr}`);
  assert.doesNotMatch(run.stderr, /MODULE_NOT_FOUND|Cannot find module/, "the installed shim must not exec a deleted path");
  assert.match(run.stdout, /service health: DOWN/);
  assert.match(run.stdout, new RegExp(`front door: ${entry.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));

  const asJson = spawnSync(process.execPath, [entry, "authority", "--json"], { encoding: "utf8", env, timeout: 30_000 });
  assert.equal(asJson.status, 3);
  const parsed = JSON.parse(asJson.stdout.trim());
  assert.equal(parsed.front_door, entry);
  assert.equal(parsed.service_up, false);
  assert.equal(parsed.skill_root, join(prefix, "frontdoor", "rel-test"));
});

test("install-front-door refuses to install from a checkout without the entry", (t) => {
  const d = sandbox(t);
  const skill = fakeSkillCheckout(d);
  rmSync(join(skill, "scripts", "council-entry.mjs"));
  const r = spawnSync("bash", [join(SCRIPTS, "install-front-door.sh"), join(d, "prefix"), "rel-x", skill, process.execPath], { encoding: "utf8" });
  assert.equal(r.status, 1);
  assert.match(r.stderr, /FRONTDOOR_INSTALL_FAILED/);
});

// ------------------------------------------------------------- pop stubs
function popStubs(d, { manager = "Background", guiRc = 0, uid = "501", consoleUid = "501", consoleUser = "trevor" } = {}) {
  const bin = join(d, "bin");
  mkdirSync(bin, { recursive: true });
  const openLog = join(d, "open.log");
  const asuserLog = join(d, "asuser.log");
  writeFileSync(openLog, "");
  writeFileSync(asuserLog, "");
  const env = (extra = {}) => ({
    ...process.env,
    PATH: `${bin}:/usr/bin:/bin`,
    STUB_MANAGER: manager,
    STUB_GUI_RC: String(guiRc),
    STUB_UID: uid,
    STUB_CONSOLE_UID: consoleUid,
    STUB_CONSOLE_USER: consoleUser,
    STUB_OPEN_LOG: openLog,
    STUB_ASUSER_LOG: asuserLog,
    ...extra,
  });
  writeExe(join(bin, "uname"), "#!/bin/sh\n[ \"${1:-}\" = \"-s\" ] && { printf 'Darwin\\n'; exit 0; }\nprintf 'Darwin\\n'\n");
  writeExe(join(bin, "stat"), "#!/bin/sh\nprintf '%s\\n' \"${STUB_CONSOLE_USER:-trevor}\"\n");
  writeExe(join(bin, "id"), "#!/bin/sh\nif [ \"${1:-}\" = \"-u\" ]; then\n  if [ -n \"${2:-}\" ]; then printf '%s\\n' \"${STUB_CONSOLE_UID:-501}\"; else printf '%s\\n' \"${STUB_UID:-501}\"; fi\n  exit 0\nfi\nprintf '%s\\n' \"${STUB_UID:-501}\"\n");
  writeExe(join(bin, "launchctl"), "#!/bin/sh\ncase \"${1:-}\" in\n  managername) printf '%s\\n' \"${STUB_MANAGER:-Background}\"; exit 0 ;;\n  print) exit \"${STUB_GUI_RC:-0}\" ;;\n  asuser) printf '%s\\n' \"$*\" >> \"${STUB_ASUSER_LOG}\"; exit 0 ;;\nesac\nexit 0\n");
  writeExe(join(bin, "open"), "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"${STUB_OPEN_LOG}\"\n");
  return { bin, env, openLog, asuserLog };
}

function runPop(d, opts = {}) {
  const stubs = popStubs(d, opts.stubs ?? {});
  const r = spawnSync("bash", [join(SCRIPTS, "chamber-visual.sh"), "--session", "S1"], {
    encoding: "utf8", env: stubs.env(opts.extraEnv ?? {}), cwd: d,
  });
  const links = r.stdout.split("\n").filter((l) => l.startsWith("Chamber link:"));
  return {
    ...r, ...stubs, links,
    openCalls: readFileSync(stubs.openLog, "utf8").trim(),
    asuserCalls: readFileSync(stubs.asuserLog, "utf8").trim(),
  };
}

test("an Aqua context opens the pop and still prints exactly one link line", (t) => {
  const d = sandbox(t);
  const r = runPop(d, { stubs: { manager: "Aqua" } });
  assert.equal(r.status, 0);
  assert.equal(r.links.length, 1);
  assert.match(r.stdout, /^Chamber link: /);
  assert.match(r.openCalls, /chamber\/#session=S1/);
  assert.match(r.stderr, /pop: opened/);
});

test("a non-Aqua gateway with a reachable GUI session for the same user still delivers the pop", (t) => {
  // The QC finding: the pop must not depend on THIS subprocess being Aqua.
  const d = sandbox(t);
  const r = runPop(d, { stubs: { manager: "Background", guiRc: 0, uid: "501", consoleUid: "501" } });
  assert.equal(r.status, 0);
  assert.match(r.openCalls, /chamber\/#session=S1/, "the pop is delivered from the service context through the user's GUI session");
  assert.match(r.stderr, /pop: opened/);
});

test("a root daemon bridges into the console user's GUI domain", (t) => {
  const d = sandbox(t);
  const r = runPop(d, { stubs: { manager: "System", guiRc: 0, uid: "0", consoleUid: "501", consoleUser: "trevor" } });
  assert.equal(r.status, 0);
  assert.match(r.asuserCalls, /asuser 501 open/);
  assert.match(r.stderr, /pop: opened \(via gui session of uid 501\)/);
});

test("a headless context never claims a pop it could not deliver", (t) => {
  const d = sandbox(t);
  const r = runPop(d, { stubs: { manager: "Background", guiRc: 1, uid: "501", consoleUid: "501" } });
  assert.equal(r.status, 0);
  assert.equal(r.links.length, 1, "the link is always printed, even with no desktop");
  assert.equal(r.openCalls, "", "no opener was spawned");
  assert.match(r.stderr, /pop: skipped \(no GUI session/);
});

test("COUNCIL_CHAMBER_GUI=0 disables the pop but keeps the link (the test hook stays authoritative)", (t) => {
  const d = sandbox(t);
  const r = runPop(d, { stubs: { manager: "Aqua" }, extraEnv: { COUNCIL_CHAMBER_GUI: "0" } });
  assert.equal(r.status, 0);
  assert.equal(r.links.length, 1);
  assert.equal(r.openCalls, "");
  assert.match(r.stderr, /pop: skipped \(COUNCIL_CHAMBER_GUI=0\)/);
});

test("COUNCIL_CHAMBER_OPEN=0 disables the pop independently of the context", (t) => {
  const d = sandbox(t);
  const r = runPop(d, { stubs: { manager: "Aqua" }, extraEnv: { COUNCIL_CHAMBER_OPEN: "0" } });
  assert.equal(r.status, 0);
  assert.equal(r.links.length, 1);
  assert.equal(r.openCalls, "");
  assert.match(r.stderr, /pop: disabled \(COUNCIL_CHAMBER_OPEN=0\)/);
});
