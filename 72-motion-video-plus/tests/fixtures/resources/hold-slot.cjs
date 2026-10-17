// MG-028 fixture: acquire one render slot from a child process and
// hold it, proving the budget ledger is genuinely cross-process (a
// second process's reservation is visible to, and blocks, the first).
//
// Usage: node hold-slot.cjs <stateDir> <holdMs>
// Prints "ACQUIRED <reservation-id>" once the slot is held, releases
// it after holdMs, and exits 0.

const { join } = require("node:path");

const resources = require(join(
  __dirname,
  "..",
  "..",
  "..",
  "runtime",
  "dist",
  "src",
  "resources",
  "index.js"
));

async function main() {
  const stateDir = process.argv[2];
  const holdMs = Number(process.argv[3] ?? "3000");
  const budget = new resources.RenderBudget(resources.deriveBudgetPolicy(stateDir));
  const reservation = await budget.acquire({
    engine: "remotion",
    jobId: "cross-process-child-job",
    operation: "renderFinal",
    profile: {
      memoryMB: 128,
      browserUnits: 1,
      encodeUnits: 1,
      diskMB: 16,
      nestedConcurrency: 1,
      label: "cross-process hold fixture",
    },
  });
  console.log(`ACQUIRED ${reservation.id}`);
  setTimeout(async () => {
    await reservation.release();
    process.exit(0);
  }, holdMs);
}

main().catch((err) => {
  console.error(err && err.message ? err.message : String(err));
  process.exit(1);
});
