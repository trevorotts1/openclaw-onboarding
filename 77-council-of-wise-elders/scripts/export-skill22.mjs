#!/usr/bin/env node
// Built by the standard Council runtime install/build; no network/model calls.
import { existsSync } from 'node:fs';
const entry = new URL('../runtime/dist/export-skill22.mjs', import.meta.url);
if (!existsSync(entry)) {
  console.error('EXPORT_RUNTIME_NOT_BUILT: run npm run build in the Council runtime directory, then retry.');
  process.exitCode = 1;
} else {
  await import(entry.href);
}
