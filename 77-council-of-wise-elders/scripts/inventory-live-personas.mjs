#!/usr/bin/env node
// Read-only (no file is created, changed or removed). Reports which of the nine Council seats have a live Book-to-Persona
// (Skill 22) persona on this box and which fall back to the shipped brief.
// Output never contains an absolute path; it names resolved_from instead.
import { existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const runtime = new URL('../runtime/', import.meta.url);
const json = process.argv.includes('--json');

async function load() {
  // Built bundle first (client boxes), then TypeScript source through tsx.
  const built = new URL('dist/inventory-live-personas.mjs', runtime);
  if (existsSync(built)) return import(built.href);
  // Source fallback: bundle in memory (write:false) so nothing touches the disk;
  // tsx's loader would create an IPC directory in the system temp dir.
  const require = createRequire(fileURLToPath(new URL('package.json', runtime)));
  const { build } = await import(require.resolve('esbuild'));
  const out = await build({
    entryPoints: [fileURLToPath(new URL('src/sources/persona-root.ts', runtime))],
    bundle: true, write: false, platform: 'node', format: 'esm', target: 'node20', logLevel: 'silent',
  });
  return import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString('base64')}`);
}

let inv;
try {
  inv = (await load()).inventoryLivePersonas();
} catch {
  console.error('INVENTORY_RUNTIME_UNAVAILABLE: run npm install in the Council runtime directory, then retry.');
  process.exit(1);
}

if (json) {
  console.log(JSON.stringify(inv, null, 2));
} else {
  const state = inv.root.unreadable ? `found but UNREADABLE (${inv.root.error}); every seat uses the shipped brief` : inv.root.found ? 'found' : 'not found';
  console.log(`Book-to-Persona store: ${state} (resolved_from: ${inv.root.resolved_from})`);
  for (const s of inv.seats) {
    const detail = s.personas.length ? s.personas.map((p) => `${p.key} [${p.content_level}]`).join(', ') : 'no registered personas';
    console.log(`${s.seat_id.padEnd(18)} ${s.layer.padEnd(22)} ${detail}`);
  }
}
