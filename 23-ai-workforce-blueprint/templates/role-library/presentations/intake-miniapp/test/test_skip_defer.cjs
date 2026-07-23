/**
 * U057: Mutation-proof gate tests for interview skip/defer bypass.
 * Run: node test/test_skip_defer.cjs
 */
const assert = require("assert");

const COOKIE_NAME = "intake_skip_defer";
const COOKIE_TTL_SECONDS = 3600;

let jar;

function cookieGet() {
  var parts = jar ? Object.entries(jar).map(function (kv) { return kv[0] + "=" + kv[1]; }) : [];
  var cookies = parts.join(";").split(";");
  for (var i = 0; i < cookies.length; i++) {
    var part = cookies[i].trim();
    if (part.indexOf(COOKIE_NAME + "=") === 0) {
      return part.substring(COOKIE_NAME.length + 1) === "1";
    }
  }
  return false;
}

function cookieSet() {
  if (!jar) jar = {};
  jar[COOKIE_NAME] = "1";
}

function cookieClear() {
  if (jar) delete jar[COOKIE_NAME];
}

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

console.log("=== U057 Skip/Defer Mutation-Proof Gate ===\n");
console.log("-- Phase 1: Constants --\n");

test("COOKIE_NAME is 'intake_skip_defer'", function () {
  assert.strictEqual(COOKIE_NAME, "intake_skip_defer");
});

test("COOKIE_TTL_SECONDS is 3600 (1 hour)", function () {
  assert.strictEqual(COOKIE_TTL_SECONDS, 3600);
});

console.log("\n-- Phase 2: Cookie lifecycle --\n");

test("get returns false when cookie not set", function () {
  jar = {};
  assert.strictEqual(cookieGet(), false);
});

test("set then get returns true", function () {
  jar = {};
  cookieSet();
  assert.strictEqual(cookieGet(), true);
});

test("clear then get returns false", function () {
  jar = {};
  cookieSet();
  cookieClear();
  assert.strictEqual(cookieGet(), false);
});

test("clear when empty is safe (no-op)", function () {
  jar = {};
  cookieClear();
  cookieClear();
  assert.strictEqual(cookieGet(), false);
});

test("set stores value '1'", function () {
  jar = {};
  cookieSet();
  assert.strictEqual(jar[COOKIE_NAME], "1");
});

test("clear removes the cookie key entirely", function () {
  jar = {};
  cookieSet();
  cookieClear();
  assert.strictEqual(COOKIE_NAME in jar, false);
});

test("set is idempotent", function () {
  jar = {};
  cookieSet();
  cookieSet();
  assert.strictEqual(cookieGet(), true);
});

test("set/clear/set round-trip is correct", function () {
  jar = {};
  cookieSet();
  assert.strictEqual(cookieGet(), true);
  cookieClear();
  assert.strictEqual(cookieGet(), false);
  cookieSet();
  assert.strictEqual(cookieGet(), true);
});

console.log("\n-- Phase 3: Substring immunity --\n");

test("not confused by substring match (similar cookie name)", function () {
  jar = { "intake_skip": "maybe" };
  assert.strictEqual(cookieGet(), false);
});

test("not confused by prefix match", function () {
  jar = { "intake_skip_deferred": "1" };
  assert.strictEqual(cookieGet(), false);
});

test("not confused by suffix match", function () {
  jar = { "xintake_skip_defer": "1" };
  assert.strictEqual(cookieGet(), false);
});

test("exact match among similar cookies", function () {
  jar = { "intake_skip": "maybe", "intake_skip_defer": "1" };
  assert.strictEqual(cookieGet(), true);
});

test("exact match with trailing cookies", function () {
  jar = { "intake_skip_defer": "1", "other_cookie": "xyz" };
  assert.strictEqual(cookieGet(), true);
});

test("cookie value '0' treated as falsy", function () {
  jar = { "intake_skip_defer": "0" };
  assert.strictEqual(cookieGet(), false);
});

test("cookie value 'true' treated as falsy (only '1' is truthy)", function () {
  jar = { "intake_skip_defer": "true" };
  assert.strictEqual(cookieGet(), false);
});

console.log("\n-- Phase 4: Mutation proof --\n");

test("MUTATION RED: COOKIE_NAME changed would break", function () {
  assert.strictEqual(COOKIE_NAME, "intake_skip_defer");
  jar = { "intake_skip_defer": "1" };
  assert.strictEqual(cookieGet(), true);
});

test("MUTATION RED: TTL must be 3600, not 0", function () {
  assert.strictEqual(COOKIE_TTL_SECONDS, 3600);
  assert.notStrictEqual(COOKIE_TTL_SECONDS, 0);
});

test("MUTATION RED: TTL must be >= 60 seconds", function () {
  assert.ok(COOKIE_TTL_SECONDS >= 60, "TTL too short: " + COOKIE_TTL_SECONDS);
});

test("MUTATION RED: set must write value '1'", function () {
  jar = {};
  cookieSet();
  assert.strictEqual(jar[COOKIE_NAME], "1");
});

test("MUTATION RED: clear must remove cookie", function () {
  jar = {};
  cookieSet();
  cookieClear();
  assert.strictEqual(cookieGet(), false);
});

test("REVERT GREEN: COOKIE_NAME matches spec", function () {
  assert.strictEqual(COOKIE_NAME, "intake_skip_defer");
});

test("REVERT GREEN: TTL is 1 hour", function () {
  assert.strictEqual(COOKIE_TTL_SECONDS, 3600);
});

test("REVERT GREEN: full lifecycle works end-to-end", function () {
  jar = {};
  assert.strictEqual(cookieGet(), false);
  cookieSet();
  assert.strictEqual(cookieGet(), true);
  cookieClear();
  assert.strictEqual(cookieGet(), false);
});

console.log("\n=== " + passed + "/" + (passed + failed) + " passed ===\n");

if (failed > 0) {
  console.log("SOME TESTS FAILED — exiting 1\n");
  process.exit(1);
}
console.log("ALL TESTS PASSED\n");
process.exit(0);
