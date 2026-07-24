/**
 * U057: Source-level mutation proof for skip-defer.js.
 * Checks constants and presence of critical strings in the shipped source file.
 * Coupled to the real file: requires skip-defer.js to exist at the correct path.
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const sourcePath = path.join(__dirname, "..", "pages", "skip-defer.js");
const source = fs.readFileSync(sourcePath, "utf8");

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

console.log("=== U057 Skip/Defer Source Mutation Proof ===\n");
console.log("-- Phase 1: Source file exists --\n");

test("source file is not empty", function () {
  assert.ok(source.length > 100, "source too short: " + source.length);
});

console.log("\n-- Phase 2: Critical constants in source --\n");

test("source contains COOKIE_NAME = 'intake_skip_defer'", function () {
  assert.ok(source.indexOf("intake_skip_defer") !== -1, "COOKIE_NAME not found");
});

test("source contains COOKIE_TTL_SECONDS = 3600", function () {
  assert.ok(source.indexOf("COOKIE_TTL_SECONDS = 3600") !== -1, "TTL 3600 not found");
});

test("source contains cookie set with max-age", function () {
  assert.ok(source.indexOf("max-age=") !== -1, "max-age not found");
});

test("source contains cookie clear with max-age=0", function () {
  assert.ok(source.indexOf("max-age=0") !== -1, "max-age=0 not found");
});

test("source contains SameSite=Lax", function () {
  assert.ok(source.indexOf("SameSite=Lax") !== -1, "SameSite not found");
});

test("source contains path=/", function () {
  assert.ok(source.indexOf("path=/") !== -1, "path=/ not found");
});

console.log("\n-- Phase 3: No forbidden model references --\n");

test("source does not reference Anthropic models", function () {
  assert.ok(source.indexOf("claude-sonnet") === -1, "found claude-sonnet reference");
});

console.log("\n-- Phase 4: Mutation RED verification --\n");

test("COOKIE_TTL_SECONDS extraction succeeds", function () {
  var m = source.match(/COOKIE_TTL_SECONDS\s*=\s*(\d+)/);
  assert.ok(m, "cannot extract TTL from source");
  var ttl = parseInt(m[1], 10);
  console.log("  Extracted COOKIE_TTL_SECONDS value: " + ttl);
});

test("MUTATION RED: COOKIE_TTL_SECONDS is 3600 (not 0)", function () {
  var m = source.match(/COOKIE_TTL_SECONDS\s*=\s*(\d+)/);
  var ttl = parseInt(m[1], 10);
  assert.strictEqual(ttl, 3600);
  assert.notStrictEqual(ttl, 0);
});

test("MUTATION RED: COOKIE_TTL_SECONDS >= 60", function () {
  var m = source.match(/COOKIE_TTL_SECONDS\s*=\s*(\d+)/);
  var ttl = parseInt(m[1], 10);
  assert.ok(ttl >= 60, "TTL " + ttl + " is less than 60 seconds");
});

console.log("\n-- Phase 5: Structure checks --\n");

var checks = ["cookieGet", "cookieSet", "cookieClear", "renderDashboard", "Skip for now", "skip-banner"];
for (var i = 0; i < checks.length; i++) {
  test("source contains " + checks[i], function() {
    assert.ok(source.indexOf(checks[i]) !== -1);
  });
}

console.log("\n" + passed + "/" + (passed + failed) + " passed ===\n");
if (failed > 0) { console.log("SOME TESTS FAILED"); process.exit(1); }
console.log("ALL CLEAN — no mutation detected\n");
process.exit(0);
