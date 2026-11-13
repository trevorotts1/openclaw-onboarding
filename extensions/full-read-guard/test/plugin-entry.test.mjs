// The plugin entry registers what OpenClaw needs and nothing else.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import register, { TOOL_MATCHER } from '../dist/index.js';
import { PLUGIN_DIR } from './helpers.mjs';

function fakeApi(config = {}) {
  const calls = { on: [], tools: [] };
  return {
    calls,
    pluginConfig: config,
    logger: { info() {}, warn() {}, error() {} },
    on(name, fn, opts) { calls.on.push({ name, fn, opts }); },
    registerTool(factory, opts) { calls.tools.push({ factory, opts }); },
  };
}

test('registers before_tool_call, after_tool_call, session resets and the read_skill tool', () => {
  const api = fakeApi({ skillsDir: '/nonexistent-skills-dir', stateDir: path.join(PLUGIN_DIR, '.no-state') });
  register(api);
  const names = api.calls.on.map((c) => c.name);
  for (const n of ['before_tool_call', 'after_tool_call', 'session_start', 'session_end', 'after_compaction']) assert.ok(names.includes(n), n);
  const before = api.calls.on.find((c) => c.name === 'before_tool_call');
  assert.deepEqual(before.opts.matcher, TOOL_MATCHER);
  assert.ok(TOOL_MATCHER.includes('read') && TOOL_MATCHER.includes('exec') && TOOL_MATCHER.includes('bash'));
  assert.equal(api.calls.tools.length, 1);
  assert.equal(api.calls.tools[0].opts.name, 'read_skill');
  assert.equal(api.calls.tools[0].factory({ sessionKey: 'x' }).name, 'read_skill');
});

test('disabled or mode off registers nothing', () => {
  const a = fakeApi({ enabled: false });
  assert.equal(register(a), null);
  assert.equal(a.calls.on.length, 0);
  const b = fakeApi({ mode: 'off' });
  assert.equal(register(b), null);
});

test('a broken api never throws out of registration', () => {
  assert.doesNotThrow(() => register({ pluginConfig: {}, on() { throw new Error('nope'); }, logger: { error() {} } }));
});

test('plugin manifest declares the tool, the config schema and the entry file', () => {
  const m = JSON.parse(fs.readFileSync(path.join(PLUGIN_DIR, 'openclaw.plugin.json'), 'utf8'));
  assert.equal(m.id, 'full-read-guard');
  assert.deepEqual(m.contracts.tools, ['read_skill']);
  assert.equal(m.main, './dist/index.js');
  assert.deepEqual(Object.keys(m.configSchema.properties).sort(), ['chunkChars', 'enabled', 'loopBreakerRepeats', 'maxBlocksPerRun', 'mode', 'skillsDir', 'stateDir']);
  assert.equal(m.configSchema.additionalProperties, false);
  const pkg = JSON.parse(fs.readFileSync(path.join(PLUGIN_DIR, 'package.json'), 'utf8'));
  assert.equal(pkg.version, m.version);
  assert.deepEqual(pkg.openclaw.extensions, ['./dist/index.js']);
  assert.ok(!('hooks' in m));
});
