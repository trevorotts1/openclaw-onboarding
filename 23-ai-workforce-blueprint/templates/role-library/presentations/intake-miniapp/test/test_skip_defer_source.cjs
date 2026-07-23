/**
 * U057: Source-level mutation proof for skip-defer.js.
 * Reads the actual source file and verifies critical constants are intact.
 * Run: node test/test_skip_defer_source.cjs
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

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

var srcPath = path.join(__dirname, "..", "pages", "skip-defer.js");
var src;
try {
  src = fs.readFileSync(srcPath, "utf8");
} catch (e) {
  console.log("  [FAIL] Cannot read skip-defer.js: " + e.message);
  process.exit(1);
}

console.log("-- Phase 1: Source file exists --\n");

test("source file is not empty", function () {
  assert.ok(src.length > 100, "source file too short: " + src.length + " chars");
});

console.log("\n-- Phase 2: Critical constants in source --\n");

test("source contains COOKIE_NAME = 'intake_skip_defer'", function () {
  assert.ok(
    src.indexOf('"intake_skip_defer"') !== -1 ||
    src.indexOf("'intake_skip_defer'") !== -1,
    "COOKIE_NAME not found in source"
  );
});

test("source contains COOKIE_TTL_SECONDS = 3600", function () {
  assert.ok(
    /COOKIE_TTL_SECONDS\s*=\s*3600/.test(src),
    "COOKIE_TTL_SECONDS = 3600 not found in source"
  );
});

test("source contains cookie set with max-age", function () {
  assert.ok(/max-age/.test(src), "max-age not found");
});

test("source contains cookie clear with max-age=0", function () {
  assert.ok(/max-age=0/.test(src), "max-age=0 not found");
});

test("source contains SameSite=Lax", function () {
  assert.ok(/SameSite=Lax/i.test(src), "SameSite=Lax not found");
});

test("source contains path=/", function () {
  assert.ok(/path=\//.test(src), "path=/ not found");
});

console.log("\n-- Phase 3: No forbidden model references --\n");

test("source does not reference Anthropic models", function () {
  var lowered = src.toLowerCase();
  var bad = ["anthropic", "claude", "opus", "sonnet", "haiku"];
  var found = bad.filter(function (w) { return lowered.indexOf(w) !== -1; });
  assert.deepStrictEqual(found, [], "Forbidden model references: " + found.join(", "));
});

console.log("\n-- Phase 4: Mutation RED verification --\n");

var ttlMatch = src.match(/COOKIE_TTL_SECONDS\s*=\s*(\d+)/);
test("COOKIE_TTL_SECONDS extraction succeeds", function () {
  assert.ok(ttlMatch, "Could not extract COOKIE_TTL_SECONDS from source");
});

if (ttlMatch) {
  var actualTTL = parseInt(ttlMatch[1], 10);
  console.log("  Extracted COOKIE_TTL_SECONDS value: " + actualTTL);

  test("MUTATION RED: COOKIE_TTL_SECONDS is 3600 (not 0)", function () {
    assert.strictEqual(actualTTL, 3600, "TTL was mutated to " + actualTTL);
    assert.notStrictEqual(actualTTL, 0, "TTL is 0 — bypass disabled");
  });

  test("MUTATION RED: COOKIE_TTL_SECONDS >= 60", function () {
    assert.ok(actualTTL >= 60, "TTL " + actualTTL + " is less than 60 seconds");
  });
}

console.log("\n-- Phase 5: Structure checks --\n");

test("source contains cookieGet", function () {
  assert.ok(/cookieGet/.test(src), "cookieGet not found");
});
test("source contains cookieSet", function () {
  assert.ok(/cookieSet/.test(src), "cookieSet not found");
});
test("source contains cookieClear", function () {
  assert.ok(/cookieClear/.test(src), "cookieClear not found");
});
test("source contains renderDashboard", function () {
  assert.ok(/renderDashboard/.test(src), "renderDashboard not found");
});
test("source contains 'Skip for now' text", function () {
  assert.ok(/Skip for now/.test(src), "'Skip for now' not found");
});
test("source contains skip-banner style", function () {
  assert.ok(/skip-banner/.test(src), "skip-banner not found");
});

console.log("\n=== " + passed + "/" + (passed + failed) + " passed ===\n");

if (failed > 0) {
  console.log("MUTATION DETECTED — tests caught regression!\n");
  process.exit(1);
}
console.log("ALL CLEAN — no mutation detected\n");
process.exit(0);
