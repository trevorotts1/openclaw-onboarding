// MG-029 fixture: a stand-in render process. Spawns one grandchild
// (same script, --grandchild) that inherits its environment, writes a
// JSON line with both pids to the file named by argv[2], then sleeps
// until killed. Dies on SIGTERM like a normal process.
"use strict";
const { spawn } = require("node:child_process");
const fs = require("node:fs");

if (process.argv.includes("--grandchild")) {
  setInterval(() => {}, 1000);
} else {
  const outFile = process.argv[2];
  const grandchild = spawn(process.execPath, [__filename, "--grandchild"], {
    stdio: "ignore",
  });
  fs.writeFileSync(
    outFile,
    JSON.stringify({ pid: process.pid, grandchildPid: grandchild.pid }) + "\n"
  );
  setInterval(() => {}, 1000);
}
