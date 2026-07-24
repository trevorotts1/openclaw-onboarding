/**
 * U057: Mutation-proof gate tests for interview skip/defer bypass.
 * Exercises the REAL shipped skip-defer.js module via require().
 * Run: node test/test_skip_defer.cjs
 */
const path = require("path");
const assert = require("assert");

// Load the shipped module
const mod = require(path.join(__dirname, "..", "pages", "skip-defer.js"));

var passed = 0;
var failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log("  [PASS] " + name);
    passed++;
  } catch (e) {
    console.log("  [FAIL] " + name + ": " + e.message);
    failed++;
  }
}

function resetJar() {
  mod._jarStr = "";
}

console.log("=== U057 Skip/Defer Mutation-Proof Gate (REAL MODULE) ===\n");
console.log("-- Phase 1: Constants (from shipped module) --\n");

test("COOKIE_NAME is 'intake_skip_defer'", function () {
  assert.strictEqual(mod.COOKIE_NAME, "intake_skip_defer");
});

test("COOKIE_TTL_SECONDS is 3600 (1 hour)", function () {
  assert.strictEqual(mod.COOKIE_TTL_SECONDS, 3600);
});

console.log("\n-- Phase 2: Cookie lifecycle (shipped cookieGet/cookieSet/cookieClear) --\n");

test("get returns false when cookie not set", function () {
  resetJar();
  assert.strictEqual(mod.cookieGet(), false);
});

test("set then get returns true", function () {
  resetJar();
  mod.cookieSet();
  assert.strictEqual(mod.cookieGet(), true);
});

test("clear then get returns false", function () {
  resetJar();
  mod.cookieSet();
  mod.cookieClear();
  assert.strictEqual(mod.cookieGet(), false);
});

test("clear when empty is safe (no-op)", function () {
  resetJar();
  mod.cookieClear();
  mod.cookieClear();
  assert.strictEqual(mod.cookieGet(), false);
});

test("set stores value '1' in jar", function () {
  resetJar();
  mod.cookieSet();
  assert.ok(mod._jarStr.indexOf(mod.COOKIE_NAME + "=1") !== -1,
    "jar must contain " + mod.COOKIE_NAME + "=1, got: " + mod._jarStr);
});

test("clear removes the cookie from jar", function () {
  resetJar();
  mod.cookieSet();
  mod.cookieClear();
  assert.strictEqual(mod.cookieGet(), false);
  assert.ok(mod._jarStr.indexOf(mod.COOKIE_NAME + "=") === -1,
    "jar still contains cookie: " + mod._jarStr);
});

test("set is idempotent", function () {
  resetJar();
  mod.cookieSet();
  mod.cookieSet();
  assert.strictEqual(mod.cookieGet(), true);
});

test("set/clear/set round-trip is correct", function () {
  resetJar();
  mod.cookieSet();
  assert.strictEqual(mod.cookieGet(), true);
  mod.cookieClear();
  assert.strictEqual(mod.cookieGet(), false);
  mod.cookieSet();
  assert.strictEqual(mod.cookieGet(), true);
});

console.log("\n-- Phase 3: Substring immunity (shipped cookieGet) --\n");

test("not confused by substring match (similar cookie name)", function () {
  resetJar();
  mod._jarStr = "intake_skip=maybe";
  assert.strictEqual(mod.cookieGet(), false);
});

test("not confused by prefix match", function () {
  resetJar();
  mod._jarStr = "intake_skip_deferred=1";
  assert.strictEqual(mod.cookieGet(), false);
});

test("not confused by suffix match", function () {
  resetJar();
  mod._jarStr = "xintake_skip_defer=1";
  assert.strictEqual(mod.cookieGet(), false);
});

test("exact match among similar cookies", function () {
  resetJar();
  mod._jarStr = "intake_skip=maybe;intake_skip_defer=1";
  assert.strictEqual(mod.cookieGet(), true);
});

test("exact match with trailing cookies", function () {
  resetJar();
  mod._jarStr = "intake_skip_defer=1;other_cookie=xyz";
  assert.strictEqual(mod.cookieGet(), true);
});

test("cookie value '0' treated as falsy", function () {
  resetJar();
  mod._jarStr = "intake_skip_defer=0";
  assert.strictEqual(mod.cookieGet(), false);
});

test("cookie value 'true' treated as falsy (only '1' is truthy)", function () {
  resetJar();
  mod._jarStr = "intake_skip_defer=true";
  assert.strictEqual(mod.cookieGet(), false);
});

console.log("\n-- Phase 4: Mutation proof (shipped module) --\n");

test("MUTATION RED: COOKIE_NAME changed would break", function () {
  assert.strictEqual(mod.COOKIE_NAME, "intake_skip_defer");
  resetJar();
  mod._jarStr = "intake_skip_defer=1";
  assert.strictEqual(mod.cookieGet(), true);
});

test("MUTATION RED: TTL must be 3600, not 0", function () {
  assert.strictEqual(mod.COOKIE_TTL_SECONDS, 3600);
  assert.notStrictEqual(mod.COOKIE_TTL_SECONDS, 0);
});

test("MUTATION RED: TTL must be >= 60 seconds", function () {
  assert.ok(mod.COOKIE_TTL_SECONDS >= 60, "TTL too short: " + mod.COOKIE_TTL_SECONDS);
});

test("MUTATION RED: set must write value '1'", function () {
  resetJar();
  mod.cookieSet();
  assert.ok(mod._jarStr.indexOf(mod.COOKIE_NAME + "=1") !== -1,
    "jar does not contain " + mod.COOKIE_NAME + "=1: " + mod._jarStr);
});

test("MUTATION RED: clear must remove cookie", function () {
  resetJar();
  mod.cookieSet();
  mod.cookieClear();
  assert.strictEqual(mod.cookieGet(), false);
});

test("REVERT GREEN: COOKIE_NAME matches spec", function () {
  assert.strictEqual(mod.COOKIE_NAME, "intake_skip_defer");
});

test("REVERT GREEN: TTL is 1 hour", function () {
  assert.strictEqual(mod.COOKIE_TTL_SECONDS, 3600);
});

test("REVERT GREEN: full lifecycle works end-to-end", function () {
  resetJar();
  assert.strictEqual(mod.cookieGet(), false);
  mod.cookieSet();
  assert.strictEqual(mod.cookieGet(), true);
  mod.cookieClear();
  assert.strictEqual(mod.cookieGet(), false);
});

console.log("\n" + passed + "/" + (passed + failed) + " passed ===\n");

if (failed > 0) {
  console.log("SOME TESTS FAILED — exiting 1\n");
  process.exit(1);
}
console.log("ALL TESTS PASSED\n");
process.exit(0);
