// Shared test helpers: a throwaway "box" with a small skills tree, a manifest, and guard factory.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createGuard } from '../dist/index.js';

export const HERE = path.dirname(fileURLToPath(import.meta.url));
export const PLUGIN_DIR = path.resolve(HERE, '..');
export const REPO = path.resolve(PLUGIN_DIR, '..', '..');
export const REAL_MANIFEST_DIR = path.join(PLUGIN_DIR, 'manifest.d');

export function lines(n, prefix = 'line') {
  return Array.from({ length: n }, (_, i) => `${prefix} ${i + 1}`).join('\n') + '\n';
}

export function makeBox(extraShards = []) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'frg-test-'));
  const skills = path.join(root, 'skills');
  const manifestDir = path.join(root, 'manifest.d');
  const state = path.join(root, 'state');
  const ext = path.join(root, 'ext-docs');
  const w = (rel, content) => {
    const p = path.join(skills, rel);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, content);
    return p;
  };
  w('10-alpha/SKILL.md', '---\nname: alpha\ndepends_on:\n  - 20-beta\n  - universal-sops/sop/SOP-*.md\nlookup: [notes/*.md]\n---\n# Alpha\n' + lines(30, 'alpha step'));
  w('10-alpha/INSTRUCTIONS.md', '# Alpha instructions\n' + lines(10, 'alpha instr'));
  w('10-alpha/references/api.md', '# api reference\n' + lines(20, 'endpoint'));
  w('10-alpha/references/procedure.md', '# procedure\n' + lines(20, 'procedure step'));
  w('10-alpha/notes/extra.md', '# extra notes\n' + lines(5, 'note'));
  w('10-alpha/scripts/run.sh', '#!/bin/sh\necho hi\n');
  w('10-alpha/scripts/run.py', 'print("hi")\n');
  w('10-alpha/data/x.json', '{"a":1}\n');
  w('10-alpha/models.json', '{"m":1}\n');
  w('20-beta/SKILL.md', '---\nname: beta\n---\n# Beta\n' + lines(10, 'beta step'));
  w('20-beta/notes.md', '# beta notes\n' + lines(5, 'beta note'));
  w('30-gamma/SKILL.md', '---\nname: gamma\n---\n# Gamma\n' + lines(5, 'gamma step'));
  w('30-gamma/scripts/go.sh', 'echo go\n');
  w('40-big/SKILL.md', '---\nname: big\n---\n# Big\n' + lines(3000, 'a long instruction line that pads the file'));
  w('50-wide/SKILL.md', '---\nname: wide\n---\n# Wide\n' + 'x'.repeat(30000) + '\n' + lines(5, 'tail'));
  w('85-docs/SKILL.md', '---\nname: docs\n---\n# Docs\n');
  w('85-docs/articles/a1.md', '# article one\n');
  w('universal-sops/sop/SOP-1.md', '# SOP one\n' + lines(5, 'sop1'));
  w('universal-sops/sop/SOP-2.md', '# SOP two\n' + lines(5, 'sop2'));
  w('universal-sops/sop/other.md', '# other\n');
  fs.mkdirSync(path.join(ext, 'sub'), { recursive: true });
  fs.writeFileSync(path.join(ext, 'sub', 'x.md'), '# external doc\n');
  fs.mkdirSync(manifestDir, { recursive: true });
  fs.copyFileSync(path.join(REAL_MANIFEST_DIR, '_defaults.json'), path.join(manifestDir, '_defaults.json'));
  const shard = {
    version: 1,
    skills: [
      { skill: '10-alpha', lookup: [{ glob: 'references/api.md', why: 'api reference' }] },
      { skill: '20-beta', depends_on: ['10-alpha'] },
      { skill: '85-docs', lookup: [{ glob: 'articles/**', why: 'support articles' }], external_lookup_roots: [ext] },
    ],
  };
  fs.writeFileSync(path.join(manifestDir, 'test.json'), JSON.stringify(shard));
  for (const [name, data] of extraShards) fs.writeFileSync(path.join(manifestDir, name), JSON.stringify(data));
  const guard = (opts = {}) => createGuard({ skillsDir: skills, stateDir: opts.stateDir ?? state, manifestDir, env: { HOME: root }, ...opts });
  const cleanup = () => fs.rmSync(root, { recursive: true, force: true });
  return { root, skills, manifestDir, state, ext, w, guard, cleanup, p: (rel) => path.join(skills, rel) };
}

/** Run a before_tool_call decision and return a short label. */
export function verdict(g, toolName, params, ctx = { sessionKey: 'sess-1', runId: 'run-1' }) {
  const r = g.beforeToolCall({ toolName, params }, ctx);
  if (!r) return 'allow';
  if (r.block) return 'block';
  if (r.params) return 'rewrite';
  return 'allow';
}
export function reasonOf(g, toolName, params, ctx = { sessionKey: 'sess-reason', runId: 'run-reason' }) {
  const r = g.beforeToolCall({ toolName, params }, ctx);
  return r && r.blockReason ? r.blockReason : '';
}
