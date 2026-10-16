// MG-029 fixture: a process that ignores SIGTERM, proving the
// termination path escalates to SIGKILL instead of reporting success
// while the process lives on.
"use strict";
const fs = require("node:fs");
process.on("SIGTERM", () => {
  process.stdout.write("SIGTERM ignored\n");
});
fs.writeFileSync(process.argv[2], JSON.stringify({ pid: process.pid }) + "\n");
setInterval(() => {}, 1000);
