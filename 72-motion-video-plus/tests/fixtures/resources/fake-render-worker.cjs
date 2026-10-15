// MG-028 fixture: a fake render worker with a real process footprint.
//
// Stands in for a browser/encoder process in the budget stress tests:
// it allocates and touches a real block of memory (so RSS accounting
// sees it), announces itself with an alive-marker file carrying its
// pid, sleeps like a render, then writes its output file and exits.
// With --fail-code it dies hard without output, like a crashed
// encoder. It uses no shell and no network.

const { writeFileSync, rmSync, mkdirSync } = require("node:fs");
const { join } = require("node:path");

function arg(name, fallback) {
  const idx = process.argv.indexOf(`--${name}`);
  return idx >= 0 && idx + 1 < process.argv.length ? process.argv[idx + 1] : fallback;
}

const id = arg("id", "worker");
const out = arg("out", "");
const content = arg("content", "");
const sleepMs = Number(arg("sleep-ms", "1000"));
const allocMB = Number(arg("alloc-mb", "0"));
const aliveDir = arg("alive-dir", "");
const failCode = Number(arg("fail-code", "0"));

if (aliveDir) {
  mkdirSync(aliveDir, { recursive: true });
  writeFileSync(join(aliveDir, `${id}.alive`), `${process.pid}\n`, "utf8");
}

// Allocate and touch pages so the reservation's memory has a real
// RSS cost the sampler can see.
const blocks = [];
for (let i = 0; i < allocMB; i += 1) {
  const buf = Buffer.alloc(1024 * 1024, 0x5a);
  buf[0] = 1;
  blocks.push(buf);
}

setTimeout(() => {
  if (failCode !== 0) {
    process.exit(failCode);
  }
  if (out) writeFileSync(out, content, "utf8");
  if (aliveDir) rmSync(join(aliveDir, `${id}.alive`), { force: true });
  process.exit(0);
}, sleepMs);
