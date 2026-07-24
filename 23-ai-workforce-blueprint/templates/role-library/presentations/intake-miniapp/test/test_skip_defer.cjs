/**
 * U057: Mutation-proof gate tests for interview skip/defer bypass.
 * Exercises the REAL shipped skip-defer.js module via require().
 * Run: node test/test_skip_defer.cjs
 */
const path = require("path");
const assert = require("assert");

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

function resetJar() { mod._jarStr = ""; }

console.log("=== U057 Skip/Defer Mutation-Proof Gate (REAL MODULE) ===\n");
console.log("-- Phase 1: Constants --\n");

test("COOKIE_NAME is 'intake_skip_defer'", function () {
  assert.strictEqual(mod.COOKIE_NAME, "intake_skip_defer");
});

test("COOKIE_TTL_SECONDS is 3600", function () {
  assert.strictEqual(mod.COOKIE_TTL_SECONDS, 3600);
});

console.log("\n-- Phase 2: Cookie lifecycle --\n");

test("get returns false when not set", function () {
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

test("set is idempotent", function () {
  resetJar();
  mod.cookieSet(); mod.cookieSet();
  assert.strictEqual(mod.cookieGet(), true);
});

test("set/clear/set round-trip", function () {
  resetJar();
  mod.cookieSet(); assert.strictEqual(mod.cookieGet(), true);
  mod.cookieClear(); assert.strictEqual(mod.cookieGet(), false);
  mod.cookieSet(); assert.strictEqual(mod.cookieGet(), true);
});

console.log("\n-- Phase 3: Substring immunity --\n");

test("not confused by substring match", function () {
  resetJar(); mod._jarStr = "intake_skip=maybe";
  assert.strictEqual(mod.cookieGet(), false);
});

test("not confused by prefix match", function () {
  resetJar(); mod._jarStr = "intake_skip_deferred=1";
  assert.strictEqual(mod.cookieGet(), false);
});

test("not confused by suffix match", function () {
  resetJar(); mod._jarStr = "xintake_skip_defer=1";
  assert.strictEqual(mod.cookieGet(), false);
});

test("exact match among similar cookies", function () {
  resetJar(); mod._jarStr = "intake_skip=maybe;intake_skip_defer=1";
  assert.strictEqual(mod.cookieGet(), true);
});

test("value '0' treated as falsy", function () {
  resetJar(); mod._jarStr = "intake_skip_defer=0";
  assert.strictEqual(mod.cookieGet(), false);
});

test("value 'true' treated as falsy", function () {
  resetJar(); mod._jarStr = "intake_skip_defer=true";
  assert.strictEqual(mod.cookieGet(), false);
});

console.log("\n-- Phase 4: Mutation proof --\n");

test("MUTATION RED: cookieGet detects set cookie", function () {
  resetJar(); mod.cookieSet();
  assert.strictEqual(mod.cookieGet(), true);
});

test("MUTATION RED: TTL is 3600 not 0", function () {
  assert.strictEqual(mod.COOKIE_TTL_SECONDS, 3600);
  assert.notStrictEqual(mod.COOKIE_TTL_SECONDS, 0);
});

test("MUTATION RED: TTL >= 60", function () {
  assert.ok(mod.COOKIE_TTL_SECONDS >= 60);
});

test("MUTATION RED: cookieClear works", function () {
  resetJar(); mod.cookieSet(); mod.cookieClear();
  assert.strictEqual(mod.cookieGet(), false);
});

console.log("\n" + passed + "/" + (passed + failed) + " passed ===\n");
if (failed > 0) { console.log("SOME TESTS FAILED"); process.exit(1); }
console.log("ALL TESTS PASSED\n");
process.exit(0);
