/**
 * Runtime-only preflight. Skill packaging/structural doctor may run on older
 * Node releases, but Council execution requires the bundled SQLite store.
 */
export function isSupportedCouncilRuntimeNode(version) {
  const match = /^v?(\d+)\.(\d+)\.(\d+)$/.exec(String(version));
  if (!match) return false;
  const major = Number(match[1]);
  const minor = Number(match[2]);
  return (major === 22 && minor >= 13) || major >= 24;
}

/**
 * Test the actual Node binary running the installer, not another PATH node.
 * A successful module import alone is not enough: verify read/write/close.
 */
export async function verifyCouncilSqlite() {
  const { DatabaseSync } = await import('node:sqlite');
  const db = new DatabaseSync(':memory:');
  try {
    db.exec('CREATE TABLE council_runtime_probe (value INTEGER NOT NULL)');
    db.prepare('INSERT INTO council_runtime_probe (value) VALUES (?)').run(77);
    const row = db.prepare('SELECT value FROM council_runtime_probe LIMIT 1').get();
    if (row?.value !== 77) {
      throw new Error('node:sqlite probe did not round-trip the expected record');
    }
  } finally {
    db.close();
  }
}
