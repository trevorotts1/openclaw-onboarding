#!/usr/bin/env node
// f32_count_mirror.js — TypeScript-formula mirror of the F32 social-planner
// prompt counting rule, runnable under plain node.
//
//   Python: len(unicodedata.normalize("NFC", final).strip())
//   TS:     Array.from(normalized.trim()).length   (code points, NOT .length)
//
// NFC normalization in JS: String.prototype.normalize("NFC").
// Reads the parity fixture JSON path from argv[2] (default: sibling
// f32_count_parity.json), prints one JSON result line per fixture, exits 0 if
// every expected count matches, 2 otherwise.

const fs = require("fs");
const path = require("path");

function tsCount(input) {
  const normalized = input.normalize("NFC");
  const trimmed = normalized.trim();
  return Array.from(trimmed).length; // code points
}

const fixturePath = process.argv[2] ||
  path.join(__dirname, "f32_count_parity.json");
const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf-8"));

let failures = 0;
for (const fx of fixture.fixtures) {
  const input = fx.input_kind === "repeat_x" ? "x".repeat(fx.count) : fx.input;
  const got = tsCount(input);
  const ok = got === fx.expected;
  if (!ok) failures++;
  console.log(JSON.stringify({
    name: fx.name, expected: fx.expected, got, ok,
    impl: "Array.from(normalized.trim()).length",
  }));
}
process.exit(failures === 0 ? 0 : 2);