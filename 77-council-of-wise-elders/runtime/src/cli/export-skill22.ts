import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { exportSkill22 } from '../sources/skill22-exporter.js';

const usage = 'node scripts/export-skill22.mjs --skill22-root <dir> --mapping <json> --out <new-json-file>';
try {
  const args = process.argv.slice(2);
  if (args.length === 1 && args[0] === '--help') {
    console.log(usage);
  } else {
    const options = new Map<string, string>();
    for (let i = 0; i < args.length; i += 2) {
      if (!['--skill22-root', '--mapping', '--out'].includes(args[i]) || !args[i + 1] || options.has(args[i])) throw new Error('usage');
      options.set(args[i], args[i + 1]);
    }
    if (options.size !== 3) throw new Error('usage');
    const result = exportSkill22(options.get('--skill22-root')!, JSON.parse(readFileSync(options.get('--mapping')!, 'utf8')));
    // Exclusive create: never overwrite a source, mapping, symlink, prior export or advisor pack.
    writeFileSync(resolve(options.get('--out')!), JSON.stringify(result, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
    console.log(JSON.stringify({ exported_evidence: result.receipts.length, unresolved: result.diagnostics.length }));
    process.exitCode = result.diagnostics.length ? 2 : 0;
  }
} catch {
  // No filenames, source text or raw schema errors in process diagnostics.
  console.error(JSON.stringify({ code: 'EXPORT_INPUT_OR_OUTPUT_ERROR', usage,
    remedy: 'Check the mapping schema, readable Skill22 registry/persona files and a writable output path that does not yet exist.' }));
  process.exitCode = 1;
}
