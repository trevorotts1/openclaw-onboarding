/**
 * Harness transport tests: envelope scan past launcher junk, isolation
 * flags gated on --help, dedicated cwd, and bounded transient retry.
 * Fake harnesses are small sh scripts; a wrapper around the real spawn
 * captures argv, env and cwd.
 */

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { chmodSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import {
  HostCallTransportError,
  SubprocessHostCallTransport,
} from '../src/cli/host-call-transport.js';

const REQUEST = {
  system: 's',
  input: { a: 1 },
  route_id: 'claude-configured',
} as unknown as Parameters<SubprocessHostCallTransport['generate']>[0];

const FIVE_FLAGS =
  'Usage: claude [options]\n  --no-session-persistence\n  --disable-slash-commands\n  --strict-mcp-config\n  --tools <tools...>\n  --settings <file-or-json>\n  --model <model>\n';

interface Call {
  args: readonly string[];
  env: NodeJS.ProcessEnv;
  cwd: string | undefined;
}

function capture() {
  const calls: Call[] = [];
  const impl = ((exe: string, args: readonly string[], opts: { env: NodeJS.ProcessEnv; cwd?: string }) => {
    calls.push({ args, env: opts.env, cwd: opts.cwd });
    return (spawn as (...a: unknown[]) => unknown)(exe, args, opts);
  }) as unknown as typeof spawn;
  return { calls, impl, runs: () => calls.filter((c) => c.args[0] !== '--help') };
}

/** Write a fake harness: --help prints helpText; otherwise reads stdin, runs body. */
function fake(helpText: string, body: string): { exe: string; dir: string } {
  const dir = mkdtempSync(join(tmpdir(), 'l3-harness-'));
  const exe = join(dir, 'fake-harness');
  writeFileSync(
    exe,
    `#!/bin/sh\nif [ "$1" = "--help" ]; then printf '%s\\n' '${helpText.replace(/'/g, "'\\''")}'; exit 0; fi\ncat >/dev/null\nN_FILE='${dir}/n'\nN=$(cat "$N_FILE" 2>/dev/null || echo 0); N=$((N+1)); echo $N > "$N_FILE"\n${body}\n`,
    'utf8',
  );
  chmodSync(exe, 0o755);
  return { exe, dir };
}

const ENVELOPE = JSON.stringify({
  type: 'result',
  is_error: false,
  result: 'CARD',
  session_id: 'sess-1',
  usage: { input_tokens: 11, output_tokens: 7 },
});
const JUNK = Array.from({ length: 12 }, (_, i) => `guard line ${i}: ok`).join('\\n');
const noSleep = async () => {};

test('12 junk stdout lines then a valid envelope: card text is envelope.result with tokens', async () => {
  const { exe } = fake('', `printf '${JUNK}\\n'\nprintf '%s\\n' '${ENVELOPE}'`);
  const res = await new SubprocessHostCallTransport({ executable: exe }).generate(REQUEST);
  assert.equal(res.text, 'CARD');
  assert.equal(res.usage.input_tokens, 11);
  assert.equal(res.usage.output_tokens, 7);
  assert.equal(res.provider_request_id, 'sess-1');
});

test('junk lines then an is_error envelope on the last line: error carries the detail', async () => {
  const err = JSON.stringify({ type: 'result', is_error: true, result: 'Invalid API key detail' });
  const { exe } = fake('', `printf '${JUNK}\\n'\nprintf '%s\\n' '${err}'\nexit 1`);
  await assert.rejects(
    new SubprocessHostCallTransport({ executable: exe, sleepImpl: noSleep }).generate(REQUEST),
    (e: unknown) => e instanceof HostCallTransportError && /Invalid API key detail/.test(e.message),
  );
});

test('output with no JSON line keeps the plain-text fallback', async () => {
  const { exe } = fake('', `printf 'just some words\\n'`);
  const res = await new SubprocessHostCallTransport({ executable: exe }).generate(REQUEST);
  assert.equal(res.text, 'just some words');
  assert.equal(res.usage.input_tokens, null);
});

test('config dir: set only when given; model only when pinned', async () => {
  const { exe } = fake('', `printf '%s\\n' '${ENVELOPE}'`);
  const withDir = capture();
  await new SubprocessHostCallTransport({ executable: exe, configDir: '/h/.claude-nine', spawnImpl: withDir.impl }).generate(REQUEST);
  assert.equal(withDir.runs()[0].env.CLAUDE_CONFIG_DIR, '/h/.claude-nine');
  assert.ok(!withDir.runs()[0].args.includes('--model'));

  const saved = process.env.CLAUDE_CONFIG_DIR;
  delete process.env.CLAUDE_CONFIG_DIR;
  try {
    const without = capture();
    await new SubprocessHostCallTransport({ executable: exe, model: 'sonnet', spawnImpl: without.impl }).generate(REQUEST);
    assert.equal(without.runs()[0].env.CLAUDE_CONFIG_DIR, undefined);
    assert.deepEqual(without.runs()[0].args.slice(0, 6), ['--print', '--output-format', 'stream-json', '--verbose', '--model', 'sonnet']);
  } finally {
    if (saved !== undefined) process.env.CLAUDE_CONFIG_DIR = saved;
  }
});

test('--help listing the five flags adds them; --help runs once across 3 calls; cwd is the empty dir', async () => {
  const { exe } = fake(FIVE_FLAGS, `printf '%s\\n' '${ENVELOPE}'`);
  const cap = capture();
  const t = new SubprocessHostCallTransport({ executable: exe, spawnImpl: cap.impl });
  for (let i = 0; i < 3; i += 1) await t.generate(REQUEST);
  assert.equal(cap.calls.filter((c) => c.args[0] === '--help').length, 1);
  assert.equal(cap.runs().length, 3);
  const args = cap.runs()[0].args;
  assert.deepEqual(args, [
    '--print', '--output-format', 'json',
    '--no-session-persistence', '--disable-slash-commands', '--strict-mcp-config',
    '--tools', '', '--settings', '{"disableAllHooks":true}',
  ]);
  for (const bad of ['--bare', '--setting-sources', '--effort']) assert.ok(!args.includes(bad));
  assert.equal(cap.runs()[0].cwd, join(tmpdir(), 'council-harness-cwd'));
  assert.notEqual(cap.runs()[0].cwd, process.cwd());
});

test('--help listing none of the flags gives exactly the base argv (plus --model)', async () => {
  const { exe } = fake('Usage: claude [options]\n  --print\n  --model <model>\n  --setting-sources <s>\n  --allowed-tools <t>\n', `printf '%s\\n' '${ENVELOPE}'`);
  const cap = capture();
  await new SubprocessHostCallTransport({ executable: exe, spawnImpl: cap.impl }).generate(REQUEST);
  assert.deepEqual(cap.runs()[0].args, ['--print', '--output-format', 'json']);
  // An unreadable probe never drops isolation: every flag is passed.
  const { exe: exe2 } = fake('', `printf '%s\\n' '${ENVELOPE}'`);
  const cap2 = capture();
  await new SubprocessHostCallTransport({ executable: exe2, model: 'opus', spawnImpl: cap2.impl }).generate(REQUEST);
  assert.deepEqual(cap2.runs()[0].args, [
    '--print', '--output-format', 'stream-json', '--verbose', '--model', 'opus', ...ALL_ISOLATION,
  ]);
});

const ALL_ISOLATION = [
  '--no-session-persistence', '--disable-slash-commands', '--strict-mcp-config',
  '--tools', '', '--settings', '{"disableAllHooks":true}',
];
const INIT = JSON.stringify({ type: 'system', subtype: 'init' });
const CONN = `echo 'API Error: Connection error (ECONNRESET)' >&2\necho 'key sk-abcdefgh12345 end' >&2\nexit 1`;

test('transient failure once then success: resolves after 2 spawns', async () => {
  const { exe } = fake('', `if [ "$N" = 1 ]; then ${CONN}; fi\nprintf '%s\\n' '${ENVELOPE}'`);
  const cap = capture();
  const sleeps: number[] = [];
  const res = await new SubprocessHostCallTransport({
    executable: exe, spawnImpl: cap.impl, sleepImpl: async (ms) => { sleeps.push(ms); },
  }).generate(REQUEST);
  assert.equal(res.text, 'CARD');
  assert.equal(cap.runs().length, 2);
  assert.deepEqual(sleeps, [5000]);
});

test('always-transient failure: rejects after 3 spawns with attempt count and redacted tail', async () => {
  const { exe } = fake('', CONN);
  const cap = capture();
  const sleeps: number[] = [];
  await assert.rejects(
    new SubprocessHostCallTransport({
      executable: exe, spawnImpl: cap.impl, sleepImpl: async (ms) => { sleeps.push(ms); },
    }).generate(REQUEST),
    (e: unknown) => {
      assert.ok(e instanceof HostCallTransportError);
      assert.match(e.message, /3 attempts/);
      assert.match(e.message, /ECONNRESET/);
      assert.match(e.message, /\[redacted\]/);
      assert.ok(!e.message.includes('sk-abcdefgh12345'));
      return true;
    },
  );
  assert.equal(cap.runs().length, 3);
  assert.deepEqual(sleeps, [5000, 15000]);
});

test('deadline kill: 1 spawn, unknownCompletion, never replayed', async () => {
  const { exe } = fake('', `printf '%s\\n' '${INIT}'\nexec sleep 5`);
  const cap = capture();
  await assert.rejects(
    new SubprocessHostCallTransport({ executable: exe, spawnImpl: cap.impl, timeoutMs: 300, sleepImpl: noSleep }).generate(REQUEST),
    (e: unknown) => e instanceof HostCallTransportError && e.unknownCompletion === true && !e.retryable,
  );
  assert.equal(cap.runs().length, 1);
});

test('help probe that hangs is killed, is not cached, and the call still gets every isolation flag', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'w35-hang-'));
  const exe = join(dir, 'fake-harness');
  writeFileSync(exe, `#!/bin/sh\nif [ "$1" = "--help" ]; then exec sleep 30; fi\ncat >/dev/null\nprintf '%s\\n' '${INIT}'\nprintf '%s\\n' '${ENVELOPE}'\n`, 'utf8');
  chmodSync(exe, 0o755);
  const cap = capture();
  const t = new SubprocessHostCallTransport({ executable: exe, spawnImpl: cap.impl, helpTimeoutMs: 200 });
  const res = await t.generate(REQUEST);
  assert.equal(res.text, 'CARD');
  assert.deepEqual(cap.runs()[0].args, ['--print', '--output-format', 'stream-json', '--verbose', ...ALL_ISOLATION]);
  await t.generate(REQUEST);
  assert.equal(cap.calls.filter((c) => c.args[0] === '--help').length, 2, 'a failed probe is re-probed, not cached');
});

test('deadline before the harness announced a start: retryable, nothing sent; the fresh call then succeeds', async () => {
  // Spawn 1 never prints an init line (starved launcher); spawn 2 starts at once.
  const { exe } = fake('', `if [ "$N" = 1 ]; then exec sleep 30; fi\nprintf '%s\\n' '${INIT}'\nprintf '%s\\n' '${ENVELOPE}'`);
  const cap = capture();
  const t = new SubprocessHostCallTransport({ executable: exe, spawnImpl: cap.impl, startupTimeoutMs: 300, sleepImpl: noSleep });
  await assert.rejects(t.generate(REQUEST), (e: unknown) =>
    e instanceof HostCallTransportError && e.retryable === true && e.unknownCompletion === false && /no request was sent/.test(e.message));
  assert.equal(cap.runs().length, 1, 'the transport itself never replays; the runner admits the one retry');
  const res = await t.generate(REQUEST);
  assert.equal(res.text, 'CARD');
});

test('deadline and abort kill the whole process group: no grandchild survives', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'w35-tree-'));
  const gone = async (pidFile: string) => {
    const pid = Number(readFileSync(pidFile, 'utf8').trim());
    for (let i = 0; i < 40; i += 1) {
      try { process.kill(pid, 0); } catch { return true; }
      await new Promise((r) => setTimeout(r, 50));
    }
    return false;
  };
  for (const mode of ['deadline', 'abort'] as const) {
    const pidFile = join(dir, `${mode}.pid`);
    const { exe } = fake('', `printf '%s\\n' '${INIT}'\n(sleep 300 & echo $! > '${pidFile}'; wait) &\nwait`);
    const ac = new AbortController();
    const running = new SubprocessHostCallTransport({
      executable: exe, timeoutMs: mode === 'deadline' ? 800 : 60_000, sleepImpl: noSleep,
    }).generate({ ...REQUEST, signal: ac.signal });
    if (mode === 'abort') setTimeout(() => ac.abort(), 600);
    await assert.rejects(running, (e: unknown) => e instanceof HostCallTransportError && e.unknownCompletion === true);
    assert.ok(await gone(pidFile), `${mode}: grandchild killed with the group`);
  }
});

test('non-transient failure: 1 spawn', async () => {
  const { exe } = fake('', `echo 'invalid model' >&2\nexit 1`);
  const cap = capture();
  await assert.rejects(
    new SubprocessHostCallTransport({ executable: exe, spawnImpl: cap.impl, sleepImpl: noSleep }).generate(REQUEST),
    /invalid model/,
  );
  assert.equal(cap.runs().length, 1);
});
