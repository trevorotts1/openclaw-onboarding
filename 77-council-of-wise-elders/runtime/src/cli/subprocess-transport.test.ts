/**
 * WER-008 slice tests: structured executable resolver and bounded
 * subprocess transport.
 *
 * SCOPE: these are simulated-shim and local subprocess tests. Native
 * Windows host execution, real provider calls and live transport
 * capture are NOT exercised here; they are deferred to WER-027.
 *
 * Runner: node --import tsx --test src/cli/subprocess-transport.test.ts
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import assert from 'node:assert/strict';
import test, { after } from 'node:test';

import { freezeRouteSnapshot, type CouncilRouteSnapshot } from '../providers/route-snapshot.js';
import type { TransportRequest } from './host-ports.js';
import {
  ExecutableResolutionError,
  resolveCommand,
} from './executable-resolver.js';
import { isSafeToRetry } from './operation-attempts.js';
import {
  BoundedSubprocessTransport,
  TransportRouteError,
  type BoundedSubprocessError,
} from './subprocess-transport.js';

const PROMPT_SENTINEL = 'PROMPT_SENTINEL_W04_U001_do-not-put-me-in-argv';
const scratch = mkdtempSync(join(tmpdir(), 'operator-W04-U001-'));

after(() => {
  rmSync(scratch, { recursive: true, force: true });
});

function snapshot(): CouncilRouteSnapshot {
  return freezeRouteSnapshot({
    selection: {
      schema: 'wise-elders.route-selection/v1',
      selectionSource: 'explicit',
      routeId: 'route-fixture',
      routeRevision: 1,
      routeKind: 'fixed_model',
      providerSlug: 'fixture',
      requestedRoute: 'fixture-route',
      requestedModelOrAlias: 'fixture-model-v1',
      combinationMembers: null,
      reasoning: { requested: 'medium', applied: 'medium', supported: true, limitation: null },
      fallbackPolicy: 'none',
      providerAccountRef: null,
      capabilitySnapshot: {
        contextWindowTokens: 128000,
        maxOutputTokens: 4096,
        capabilities: ['text'],
        supportedReasoningLevels: ['low', 'medium', 'high'],
      },
      credential: {
        state: 'present',
        envVar: 'FIXTURE_API_KEY',
        source: 'process.env',
        checked: ['process.env'],
      },
      identityLevel: 'configured',
      scope: { tenantId: 't', companyId: 'c', installationId: 'i', ownerSubject: null },
      createdAt: '2026-10-18T00:00:00.000Z',
    },
    sessionId: 'session-fixture',
    sessionOwner: 'owner-fixture',
    host: {
      baseUrl: 'http://127.0.0.1:9',
      configProfile: 'fixture-profile',
      apiFamily: 'openai_compatible',
    },
    reasoning: {
      requested: 'medium',
      supported: ['low', 'medium', 'high'],
      applied: 'medium',
      limitation: null,
      paramStyle: 'reasoning_effort',
    },
    capabilityVersion: 'cap-1',
    policySha256: '0'.repeat(64),
    limits: { requestsPerMinute: null, tokensPerMinute: null, maxConcurrency: null },
    createdAt: '2026-10-18T00:00:00.000Z',
  });
}

function request(overrides: Partial<TransportRequest> = {}): TransportRequest {
  return {
    purpose: 'advisor',
    session_id: 'session-fixture',
    seat_id: 'simon-sinek',
    round: 1,
    route_id: 'route-fixture',
    model_policy: {
      selection: 'explicit',
      route_id: 'route-fixture',
      requested_model_id: 'fixture-model-v1',
      reasoning_preference: 'medium',
      fallback_policy: 'none',
    },
    system: `System contract ${PROMPT_SENTINEL}`,
    input: { brief: PROMPT_SENTINEL },
    ...overrides,
  };
}

function script(name: string, source: string): string {
  const path = join(scratch, name);
  writeFileSync(path, source, 'utf8');
  return path;
}

function nodeInvocation(scriptPath: string): {
  kind: 'native';
  file: string;
  args: string[];
  target: string;
} {
  return {
    kind: 'native',
    file: process.execPath,
    args: [scriptPath],
    target: process.execPath,
  };
}

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function waitUntilGone(pid: number, timeoutMs = 3000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!isAlive(pid)) return true;
    await new Promise((resolve) => setTimeout(resolve, 40));
  }
  return !isAlive(pid);
}

// ---------------------------------------------------------------------------
// Structured resolver (simulated Windows shapes; NOT a native Windows run)
// ---------------------------------------------------------------------------

test('resolver: Windows .cmd shim path with SPACES and NON-ASCII resolves exactly', () => {
  const target =
    'C:\\Users\\Zoë Müller\\AppData\\Local\\Programs\\Council Elders\\council shim.cmd';
  const invocation = resolveCommand({
    command: target,
    args: ['--print', '--output-format', 'json'],
    platform: 'win32',
    env: { Path: '', ComSpec: 'C:\\Windows\\System32\\cmd.exe' },
    isFile: (path) => path === target,
  });

  assert.equal(invocation.kind, 'windows-cmd-shim');
  assert.equal(invocation.target, target);
  assert.equal(invocation.file, 'C:\\Windows\\System32\\cmd.exe');
  assert.deepEqual(invocation.args.slice(0, 3), ['/d', '/s', '/c']);
  const payload = invocation.args[3];
  assert.ok(payload.includes(`"${target}"`), 'the exact non-ASCII path stays quoted and intact');
  assert.ok(payload.includes('"--output-format"'));
  assert.ok(!payload.includes(PROMPT_SENTINEL));
});

test('resolver: Windows PATHEXT lookup finds a native .exe under a path with spaces', () => {
  const dir = 'C:\\Program Files\\Council Elders';
  const expected = `${dir}\\council.exe`;
  const invocation = resolveCommand({
    command: 'council',
    platform: 'win32',
    env: { Path: dir },
    isFile: (path) => path === expected,
  });
  assert.equal(invocation.kind, 'native');
  assert.equal(invocation.file, expected);
  assert.deepEqual(invocation.args, []);
});

test('resolver: PowerShell script uses -File with a real argv, no shell string', () => {
  const target = 'C:\\Program Files\\Council Elders\\run council.ps1';
  const invocation = resolveCommand({
    command: target,
    args: ['--print'],
    platform: 'win32',
    env: { Path: '' },
    isFile: (path) => path === target,
  });
  assert.equal(invocation.kind, 'powershell-script');
  assert.equal(invocation.file, 'powershell.exe');
  assert.deepEqual(invocation.args.slice(0, 7), [
    '-NoLogo',
    '-NoProfile',
    '-NonInteractive',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    target,
  ]);
  assert.equal(invocation.args[7], '--print');
  assert.ok(!invocation.args.join('\u0000').includes(PROMPT_SENTINEL));
});

test('resolver: POSIX path with spaces stays one argv element', () => {
  const target = '/opt/Council Elders/bin/council launcher';
  const invocation = resolveCommand({
    command: target,
    args: ['--print'],
    platform: 'linux',
    env: { PATH: '' },
    isFile: (path) => path === target,
  });
  assert.equal(invocation.kind, 'native');
  assert.equal(invocation.file, target);
  assert.deepEqual(invocation.args, ['--print']);
});

test('resolver: a .cmd shim on a non-Windows platform is refused, never sent to WSL or bash', () => {
  assert.throws(
    () =>
      resolveCommand({
        command: '/tmp/council shim.cmd',
        platform: 'linux',
        env: { PATH: '' },
        isFile: (path) => path === '/tmp/council shim.cmd',
      }),
    (error: unknown) =>
      error instanceof ExecutableResolutionError &&
      error.code === 'EXECUTABLE_UNSUPPORTED_SCRIPT',
  );
});

test('resolver: missing command fails typed instead of falling back to a shell', () => {
  assert.throws(
    () => resolveCommand({ command: 'no-such-council-binary', platform: 'linux', env: { PATH: '/nonexistent' }, isFile: () => false }),
    (error: unknown) =>
      error instanceof ExecutableResolutionError && error.code === 'EXECUTABLE_NOT_FOUND',
  );
});

// ---------------------------------------------------------------------------
// Bounded transport
// ---------------------------------------------------------------------------

test('transport: prompt goes on stdin and never appears in the spawn argv', async () => {
  const echo = script(
    'echo.mjs',
    `let data = '';
     process.stdin.setEncoding('utf8');
     process.stdin.on('data', (chunk) => { data += chunk; });
     process.stdin.on('end', () => {
       process.stdout.write(JSON.stringify({ stdin: data, argv: process.argv.slice(2) }));
     });`,
  );
  const captured: Array<{ file: string; args: string[] }> = [];
  const transport = new BoundedSubprocessTransport({
    snapshot: snapshot(),
    command: 'unused',
    invocation: nodeInvocation(echo),
    modelFlag: '--model',
    effortFlag: '--reasoning',
    spawnImpl: ((file: string, args: readonly string[], options: unknown) => {
      captured.push({ file, args: [...args] });
      return (spawn as unknown as (...a: unknown[]) => ChildProcess)(file, args, options);
    }) as typeof spawn,
  });

  const response = await transport.generate(request());
  const payload = JSON.parse(response.text) as { stdin: string; argv: string[] };

  assert.ok(payload.stdin.includes(PROMPT_SENTINEL), 'prompt content reached the child on stdin');
  assert.ok(!payload.stdin.includes('--model'), 'pinned flags are not part of the prompt');

  assert.equal(captured.length, 1);
  const argvText = captured[0].args.join('\u0000');
  assert.ok(!argvText.includes(PROMPT_SENTINEL), 'prompt content never appears in the argv');
  assert.ok(captured[0].args.includes('fixture-model-v1'), 'pinned model flag is present');
  assert.ok(captured[0].args.includes('--reasoning'), 'pinned effort flag is present');
  assert.ok(payload.argv.every((arg) => !arg.includes(PROMPT_SENTINEL)));
});

test('transport: pinned profile is frozen at construction, not read from a mutable global', async () => {
  const echoEnv = script(
    'echo-env.mjs',
    `process.stdout.write(JSON.stringify({ value: process.env.COUNCIL_TEST_MUTABLE ?? null }));`,
  );
  process.env.COUNCIL_TEST_MUTABLE = 'before';
  try {
    const transport = new BoundedSubprocessTransport({
      snapshot: snapshot(),
      command: 'unused',
      invocation: nodeInvocation(echoEnv),
      env: { ...process.env, COUNCIL_TEST_MUTABLE: 'before' },
    });
    process.env.COUNCIL_TEST_MUTABLE = 'after';
    const response = await transport.generate(request());
    assert.equal(JSON.parse(response.text).value, 'before');
    assert.equal(transport.pinnedProfile.modelId, 'fixture-model-v1');
    assert.equal(transport.pinnedProfile.effort, 'medium');
    assert.equal(transport.pinnedProfile.configProfile, 'fixture-profile');
  } finally {
    delete process.env.COUNCIL_TEST_MUTABLE;
  }
});

test('transport: oversized stdout is refused at the byte bound', async () => {
  const loud = script('loud.mjs', `process.stdout.write('x'.repeat(4096));`);
  const transport = new BoundedSubprocessTransport({
    snapshot: snapshot(),
    command: 'unused',
    invocation: nodeInvocation(loud),
    maxStdoutBytes: 1024,
    timeoutMs: 5000,
    attemptIdFactory: () => 'a1',
  });

  await assert.rejects(
    transport.generate(request()),
    (error: unknown) => {
      const typed = error as BoundedSubprocessError;
      assert.equal(typed.code, 'COUNCIL_TRANSPORT_OUTPUT_BOUND');
      assert.equal(typed.disposition, 'potentially_dispatched');
      return true;
    },
  );
  const record = transport.attemptFor('session-fixture:advisor:r1:simon-sinek', 'a1');
  assert.equal(record?.disposition, 'potentially_dispatched');
});

test('transport: a timeout is recorded as potentially-dispatched, never safe-to-retry', async () => {
  const sleeping = script('sleep.mjs', `setTimeout(() => {}, 30000);`);
  const transport = new BoundedSubprocessTransport({
    snapshot: snapshot(),
    command: 'unused',
    invocation: nodeInvocation(sleeping),
    timeoutMs: 120,
    attemptIdFactory: () => 'timeout-attempt',
  });

  await assert.rejects(
    transport.generate(request()),
    (error: unknown) => {
      const typed = error as BoundedSubprocessError;
      assert.equal(typed.code, 'COUNCIL_TRANSPORT_TIMEOUT');
      assert.equal(typed.disposition, 'potentially_dispatched');
      assert.equal(typed.unknownCompletion, true);
      assert.equal(typed.retryable, false);
      return true;
    },
  );

  const record = transport.attemptFor('session-fixture:advisor:r1:simon-sinek', 'timeout-attempt');
  assert.ok(record, 'the attempt was recorded before launch');
  assert.equal(record?.disposition, 'potentially_dispatched');
  assert.equal(isSafeToRetry(record!), false, 'a timeout is not proof the provider did no work');
});

test('transport: cancellation terminates the whole child process tree', async () => {
  const pidFile = join(scratch, 'tree-pids.json');
  const treeScript = script(
    'tree.mjs',
    `import { spawn } from 'node:child_process';
     import { writeFileSync } from 'node:fs';
     const grandchild = spawn(process.execPath, ['-e', 'setTimeout(() => {}, 30000)'], {
       stdio: 'ignore',
     });
     writeFileSync(${JSON.stringify(pidFile)}, JSON.stringify({
       parent: process.pid,
       grandchild: grandchild.pid,
     }));
     setTimeout(() => {}, 30000);`,
  );

  const controller = new AbortController();
  const transport = new BoundedSubprocessTransport({
    snapshot: snapshot(),
    command: 'unused',
    invocation: nodeInvocation(treeScript),
    timeoutMs: 20000,
    attemptIdFactory: () => 'cancel-attempt',
  });

  const running = transport.generate(request({ signal: controller.signal }));

  const deadline = Date.now() + 3000;
  while (!existsSync(pidFile) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 40));
  }
  assert.ok(existsSync(pidFile), 'the child tree reported its pids');
  const pids = JSON.parse(readFileSync(pidFile, 'utf8')) as {
    parent: number;
    grandchild: number;
  };

  controller.abort();

  await assert.rejects(running, (error: unknown) => {
    const typed = error as BoundedSubprocessError;
    assert.equal(typed.code, 'COUNCIL_TRANSPORT_CANCELLED');
    assert.equal(typed.disposition, 'potentially_dispatched');
    return true;
  });

  assert.equal(await waitUntilGone(pids.parent), true, 'the child process is gone');
  assert.equal(await waitUntilGone(pids.grandchild), true, 'the grandchild process is gone');
});

test('transport: a snapshot failing verifyRouteSnapshotHash is refused before dispatch', async () => {
  const base = snapshot();
  const tampered = { ...base, snapshotSha256: 'f'.repeat(64) };
  let spawned = 0;
  assert.throws(
    () =>
      new BoundedSubprocessTransport({
        snapshot: tampered,
        command: 'unused',
        spawnImpl: ((...args: unknown[]) => {
          spawned += 1;
          return (spawn as unknown as (...a: unknown[]) => ChildProcess)(...args);
        }) as typeof spawn,
      }),
    (error: unknown) =>
      error instanceof TransportRouteError &&
      error.code === 'COUNCIL_ROUTE_SNAPSHOT_REFUSED',
  );
  assert.equal(spawned, 0, 'no child was spawned');
});

test('transport: a snapshot mutated after construction is refused at dispatch', async () => {
  const base = snapshot();
  const mutable = { ...base } as CouncilRouteSnapshot;
  let spawned = 0;
  const transport = new BoundedSubprocessTransport({
    snapshot: mutable,
    command: 'unused',
    spawnImpl: ((...args: unknown[]) => {
      spawned += 1;
      return (spawn as unknown as (...a: unknown[]) => ChildProcess)(...args);
    }) as typeof spawn,
  });
  mutable.snapshotSha256 = 'e'.repeat(64);

  await assert.rejects(
    transport.generate(request()),
    (error: unknown) =>
      error instanceof TransportRouteError &&
      error.code === 'COUNCIL_ROUTE_SNAPSHOT_REFUSED',
  );
  assert.equal(spawned, 0, 'the tampered snapshot was refused before any spawn');
});

test('transport: a request contradicting the frozen pin is refused before dispatch', async () => {
  let spawned = 0;
  const transport = new BoundedSubprocessTransport({
    snapshot: snapshot(),
    command: 'unused',
    spawnImpl: ((...args: unknown[]) => {
      spawned += 1;
      return (spawn as unknown as (...a: unknown[]) => ChildProcess)(...args);
    }) as typeof spawn,
  });

  await assert.rejects(
    transport.generate(request({ route_id: 'some-other-route' })),
    (error: unknown) =>
      error instanceof TransportRouteError && error.code === 'COUNCIL_ROUTE_PIN_MISMATCH',
  );
  await assert.rejects(
    transport.generate(
      request({
        model_policy: {
          selection: 'explicit',
          route_id: 'route-fixture',
          requested_model_id: 'a-different-model',
          reasoning_preference: 'medium',
          fallback_policy: 'none',
        },
      }),
    ),
    (error: unknown) =>
      error instanceof TransportRouteError && error.code === 'COUNCIL_ROUTE_PIN_MISMATCH',
  );
  assert.equal(spawned, 0);
});

test('transport: a successful JSON envelope resolves and records completion', async () => {
  const envelope = script(
    'envelope.mjs',
    `process.stdin.resume();
     process.stdin.on('end', () => {
       process.stdout.write(JSON.stringify({
         result: 'council answer',
         session_id: 'sess-1',
         model: 'fixture-model-v1',
         usage: { input_tokens: 11, output_tokens: 22 },
       }));
     });`,
  );
  const transport = new BoundedSubprocessTransport({
    snapshot: snapshot(),
    command: 'unused',
    invocation: nodeInvocation(envelope),
    attemptIdFactory: () => 'ok-attempt',
  });

  const response = await transport.generate(request());
  assert.equal(response.text, 'council answer');
  assert.equal(response.provider_request_id, 'sess-1');
  assert.equal(response.reported_model_id, 'fixture-model-v1');
  assert.equal(response.usage.output_tokens, 22);
  assert.equal(
    transport.attemptFor('session-fixture:advisor:r1:simon-sinek', 'ok-attempt')?.disposition,
    'completed',
  );
});
