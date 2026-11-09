/**
 * W28 route-choice tests (Decision 1): per-session route resolution,
 * latest-Flash pick, snapshot shape, per-snapshot transports, and the
 * host-call --model flag. No network: the model list is an injected
 * fetch, every host is a temp directory, executables are fakes.
 */

import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { chmodSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { SubprocessHostCallTransport } from '../src/cli/host-call-transport.js';
import { modelPolicySchema } from '../src/contracts/schemas.js';
import { CompatibleHttpTransport } from '../src/providers/compatible.js';
import {
  HARNESS_DEFAULTS,
  RouteChoiceError,
  listRouteOptions,
  pickLatestFlash,
  resolveSessionRoute,
  transportForSnapshot,
  type RouteChoiceOptions,
} from '../src/service/route-choice.js';

const SCOPE = {
  tenantId: 'tenant-rc',
  companyId: 'company-rc',
  installationId: 'install-rc',
  ownerSubject: 'owner-rc',
};

function makeHome(extra: { deepseek?: boolean } = { deepseek: true }): string {
  const home = mkdtempSync(join(tmpdir(), 'w28-route-choice-'));
  for (const root of ['.claude-nine', '.claude']) mkdirSync(join(home, root), { recursive: true });
  mkdirSync(join(home, '.local', 'bin'), { recursive: true });
  for (const name of ['claude-nine', 'claude']) {
    const exe = join(home, '.local', 'bin', name);
    writeFileSync(exe, '#!/bin/sh\nexit 0\n', 'utf8');
    chmodSync(exe, 0o755);
  }
  mkdirSync(join(home, '.openclaw'), { recursive: true });
  const providers: Record<string, unknown> = {};
  if (extra.deepseek) {
    providers.deepseek = {
      baseUrl: 'https://api.deepseek.test/v1',
      api: 'openai-completions',
      apiKey: 'fixture-key-not-real',
      models: [{ id: 'deepseek-flash' }],
    };
  }
  writeFileSync(join(home, '.openclaw', 'openclaw.json'), JSON.stringify({ models: { providers } }), 'utf8');
  return home;
}

function modelList(ids: string[], seen?: { url?: string; auth?: string }): typeof fetch {
  return (async (url: unknown, init?: { headers?: Record<string, string> }) => {
    if (seen) {
      seen.url = String(url);
      seen.auth = init?.headers?.authorization;
    }
    return new Response(JSON.stringify({ object: 'list', data: ids.map((id) => ({ id })) }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  }) as typeof fetch;
}

function opts(home: string, fetchImpl?: typeof fetch): RouteChoiceOptions {
  return {
    homeDir: home,
    env: { PATH: '/usr/bin:/bin' },
    fetchImpl,
    scope: SCOPE,
    nowUtc: () => '2026-10-19T12:00:00.000Z',
  };
}

async function refusal(promise: Promise<unknown>): Promise<RouteChoiceError> {
  try {
    await promise;
  } catch (error) {
    assert.ok(error instanceof RouteChoiceError, `typed refusal, got ${String(error)}`);
    return error;
  }
  assert.fail('expected a RouteChoiceError');
}

test('pickLatestFlash: newest version wins, then newest build suffix, null without Flash', () => {
  assert.equal(
    pickLatestFlash(['deepseek-chat', 'deepseek-v4-flash', 'deepseek-v4.1-flash', 'deepseek-reasoner']),
    'deepseek-v4.1-flash',
  );
  assert.equal(pickLatestFlash(['deepseek-chat']), null);
  assert.equal(pickLatestFlash([]), null);
  assert.equal(
    pickLatestFlash(['deepseek-v4.1-flash', 'deepseek-v4.2-flash', 'deepseek-v3.2-flash']),
    'deepseek-v4.2-flash',
  );
  assert.equal(pickLatestFlash(['deepseek-v4-flash', 'deepseek-v3.2-flash']), 'deepseek-v4-flash');
  assert.equal(
    pickLatestFlash(['deepseek-v4-flash-0813', 'deepseek-v4-flash-0901', 'deepseek-v4-flash']),
    'deepseek-v4-flash-0901',
  );
});

test('harness table is the Decision 1 default table', () => {
  assert.deepEqual(HARNESS_DEFAULTS, {
    'claude-nine': { route_id: 'claude-nine-configured', model: 'harness_default' },
    'claude-code': { route_id: 'claude-configured', model: 'sonnet' },
    deepseek: { route_id: 'deepseek-configured', model: 'latest_deepseek_flash' },
  });
});

test('deepseek harness: model comes from the live /models list, never the configured id', async () => {
  const home = makeHome();
  const seen: { url?: string; auth?: string } = {};
  const resolved = await resolveSessionRoute(
    { harness: 'deepseek' },
    opts(home, modelList(['deepseek-chat', 'deepseek-v4-flash', 'deepseek-v4.1-flash'], seen)),
  );
  assert.equal(resolved.snapshot.routeId, 'deepseek-configured');
  assert.equal(resolved.snapshot.requestedModelOrAlias, 'deepseek-v4.1-flash');
  assert.notEqual(resolved.snapshot.requestedModelOrAlias, 'deepseek-flash');
  assert.equal(resolved.model_policy.selection, 'client_default');
  assert.equal(resolved.model_policy.requested_model_id, 'deepseek-v4.1-flash');
  assert.equal(resolved.model_label, 'deepseek-v4.1-flash');
  assert.equal(resolved.selection_source, 'client_default');
  assert.equal(resolved.harness, 'deepseek');
  assert.equal(seen.url, 'https://api.deepseek.test/v1/models');
  assert.equal(seen.auth, 'Bearer fixture-key-not-real');
  assert.doesNotThrow(() => modelPolicySchema.parse(resolved.model_policy));
  // Limits belong to the configured model, not to a different Flash.
  assert.equal(resolved.snapshot.capabilitySnapshot.contextWindowTokens, null);
});

test('a newer Flash wins as soon as the provider lists it', async () => {
  const home = makeHome();
  const resolved = await resolveSessionRoute(
    { harness: 'deepseek' },
    opts(home, modelList(['deepseek-v4.1-flash', 'deepseek-v4.2-flash'])),
  );
  assert.equal(resolved.snapshot.requestedModelOrAlias, 'deepseek-v4.2-flash');
});

test('deepseek: failed list or list without Flash is a typed refusal, no fallback to the configured id', async () => {
  const home = makeHome();
  const failing = (async () => {
    throw new Error('connect ECONNREFUSED');
  }) as unknown as typeof fetch;
  assert.equal(
    (await refusal(resolveSessionRoute({ harness: 'deepseek' }, opts(home, failing)))).code,
    'ROUTE_MODEL_LIST_UNAVAILABLE',
  );
  const http500 = (async () => new Response('nope', { status: 500 })) as unknown as typeof fetch;
  assert.equal(
    (await refusal(resolveSessionRoute({ harness: 'deepseek' }, opts(home, http500)))).code,
    'ROUTE_MODEL_LIST_UNAVAILABLE',
  );
  const noFlash = await refusal(
    resolveSessionRoute({ harness: 'deepseek' }, opts(home, modelList(['deepseek-chat', 'deepseek-reasoner']))),
  );
  assert.equal(noFlash.code, 'ROUTE_LATEST_FLASH_NOT_FOUND');
  assert.ok(noFlash.recovery.length > 0);
});

test('claude-code gives claude-configured / sonnet; claude-nine gives its route with no model', async () => {
  const home = makeHome();
  const code = await resolveSessionRoute({ harness: 'claude-code' }, opts(home));
  assert.equal(code.snapshot.routeId, 'claude-configured');
  assert.equal(code.snapshot.requestedModelOrAlias, 'sonnet');
  assert.equal(code.model_label, 'sonnet');
  const nine = await resolveSessionRoute({ harness: 'claude-nine' }, opts(home));
  assert.equal(nine.snapshot.routeId, 'claude-nine-configured');
  assert.equal(nine.snapshot.requestedModelOrAlias, null);
  assert.equal(nine.model_policy.requested_model_id, null);
  assert.equal(nine.model_label, 'claude-nine configured default');
  assert.equal(nine.selection_source, 'client_default');
  for (const r of [code, nine]) {
    assert.equal(r.snapshot.schema, 'wise-elders.route-selection/v1');
    assert.doesNotThrow(() => modelPolicySchema.parse(r.model_policy));
    assert.equal(r.snapshot.scope.installationId, 'install-rc');
    assert.equal(r.snapshot.createdAt, '2026-10-19T12:00:00.000Z');
  }
});

test('explicit route_id and model win and are marked explicit', async () => {
  const home = makeHome();
  const harness = await resolveSessionRoute(
    { route_id: 'claude-configured', model: 'opus', harness: 'deepseek' },
    opts(home),
  );
  assert.equal(harness.selection_source, 'explicit');
  assert.equal(harness.model_policy.selection, 'explicit');
  assert.equal(harness.snapshot.routeId, 'claude-configured');
  assert.equal(harness.snapshot.requestedModelOrAlias, 'opus');
  assert.equal(harness.snapshot.selectionSource, 'explicit');

  // Configured candidate: accepted with no provider call at all.
  const noNetwork = (async () => {
    throw new Error('must not fetch');
  }) as unknown as typeof fetch;
  const configured = await resolveSessionRoute(
    { route_id: 'deepseek-configured', model: 'deepseek-flash' },
    opts(home, noNetwork),
  );
  assert.equal(configured.snapshot.requestedModelOrAlias, 'deepseek-flash');
  assert.equal(configured.selection_source, 'explicit');

  // Offered by the provider list but not configured: accepted.
  const listed = await resolveSessionRoute(
    { route_id: 'deepseek-configured', model: 'deepseek-v9-pro' },
    opts(home, modelList(['deepseek-v9-pro'])),
  );
  assert.equal(listed.snapshot.requestedModelOrAlias, 'deepseek-v9-pro');

  // Model only, with a known harness: that harness's route.
  const modelOnly = await resolveSessionRoute({ model: 'haiku', harness: 'claude-code' }, opts(home));
  assert.equal(modelOnly.snapshot.routeId, 'claude-configured');
  assert.equal(modelOnly.snapshot.requestedModelOrAlias, 'haiku');
  assert.equal(modelOnly.selection_source, 'explicit');
});

test('explicit model on a compatible route absent from list and config is refused', async () => {
  const home = makeHome();
  const error = await refusal(
    resolveSessionRoute(
      { route_id: 'deepseek-configured', model: 'ghost-model' },
      opts(home, modelList(['deepseek-v4.1-flash'])),
    ),
  );
  assert.equal(error.code, 'ROUTE_MODEL_NOT_OFFERED');
  const unreachable = await refusal(
    resolveSessionRoute(
      { route_id: 'deepseek-configured', model: 'ghost-model' },
      opts(home, (async () => {
        throw new Error('down');
      }) as unknown as typeof fetch),
    ),
  );
  assert.equal(unreachable.code, 'ROUTE_MODEL_NOT_OFFERED');
});

test('no route_id and no known harness is ROUTE_CHOICE_REQUIRED; unknown routes are typed', async () => {
  const home = makeHome();
  for (const request of [{}, { harness: null }, { harness: 'unknown' as const }, { model: 'sonnet' }]) {
    assert.equal((await refusal(resolveSessionRoute(request, opts(home)))).code, 'ROUTE_CHOICE_REQUIRED');
  }
  assert.equal(
    (await refusal(resolveSessionRoute({ route_id: 'nope-configured' }, opts(home)))).code,
    'ROUTE_NOT_CONFIGURED',
  );
  const bare = mkdtempSync(join(tmpdir(), 'w28-route-choice-bare-'));
  mkdirSync(join(bare, '.claude-nine'), { recursive: true }); // root, but no executable
  const noExe = await refusal(
    resolveSessionRoute({ harness: 'claude-nine' }, { ...opts(bare), env: { PATH: '' } }),
  );
  assert.ok(['ROUTE_NOT_CONFIGURED', 'ROUTE_NOT_COMPOSABLE'].includes(noExe.code));
});

test('several composable routes at once are not an error', async () => {
  const home = makeHome();
  const options = listRouteOptions({ homeDir: home, env: { PATH: '/usr/bin:/bin' } });
  assert.deepEqual(
    options.filter((o) => o.composable).map((o) => o.route_id).sort(),
    ['claude-configured', 'claude-nine-configured', 'deepseek-configured'],
  );
  const byId = Object.fromEntries(options.map((o) => [o.route_id, o]));
  assert.deepEqual(byId['deepseek-configured'].default_for, ['deepseek']);
  assert.deepEqual(byId['claude-configured'].default_for, ['claude-code']);
  assert.deepEqual(byId['claude-nine-configured'].default_for, ['claude-nine']);
  assert.equal(byId['claude-configured'].failure_code, null);
  // Each harness resolves independently in the same host.
  for (const harness of ['claude-nine', 'claude-code'] as const) {
    await resolveSessionRoute({ harness }, opts(home));
  }
});

test('transportForSnapshot builds the transport for the snapshot route, per call', async () => {
  const home = makeHome();
  const env = { PATH: '/usr/bin:/bin' };
  const nine = await resolveSessionRoute({ harness: 'claude-nine' }, opts(home));
  const code = await resolveSessionRoute({ harness: 'claude-code' }, opts(home));
  const ds = await resolveSessionRoute({ harness: 'deepseek' }, opts(home, modelList(['deepseek-v4.1-flash'])));

  const tNine = transportForSnapshot(nine.snapshot, { homeDir: home, env });
  const tCode = transportForSnapshot(code.snapshot, { homeDir: home, env });
  const tDs = transportForSnapshot(ds.snapshot, { homeDir: home, env });
  assert.ok(tNine instanceof SubprocessHostCallTransport);
  assert.ok(tCode instanceof SubprocessHostCallTransport);
  assert.ok(tDs instanceof CompatibleHttpTransport);
  assert.equal((tNine as SubprocessHostCallTransport).executable, join(home, '.local', 'bin', 'claude-nine'));

  // The pinned model must reach the harness transport (becomes --model).
  assert.equal((tCode as SubprocessHostCallTransport).model, 'sonnet');
  assert.equal((tNine as SubprocessHostCallTransport).model, null);

  // A route that no longer resolves gives null, never another route.
  assert.equal(
    transportForSnapshot({ ...ds.snapshot, routeId: 'gone-configured' }, { homeDir: home, env }),
    null,
  );
});

// ---------------------------------------------------------------------------
// Host-call transport: --model
// ---------------------------------------------------------------------------

function fakeSpawn(captured: { args?: readonly string[] }) {
  return ((_exe: string, args: readonly string[]) => {
    captured.args = args;
    const child = new EventEmitter() as EventEmitter & Record<string, unknown>;
    const stdout = new EventEmitter();
    child.stdout = stdout;
    child.stderr = new EventEmitter();
    child.stdin = { on() {}, end() {
      queueMicrotask(() => {
        stdout.emit('data', Buffer.from(JSON.stringify({ result: 'ok', is_error: false })));
        child.emit('close', 0);
      });
    } };
    child.kill = () => true;
    return child;
  }) as unknown as typeof import('node:child_process').spawn;
}

const REQUEST = {
  system: 's',
  input: { a: 1 },
  route_id: 'claude-configured',
  model_policy: {
    selection: 'client_default',
    route_id: 'claude-configured',
    requested_model_id: null,
    reasoning_preference: null,
    fallback_policy: 'none',
  },
} as unknown as Parameters<SubprocessHostCallTransport['generate']>[0];

test('host-call transport passes --model only when the snapshot pins one', async () => {
  const withModel: { args?: readonly string[] } = {};
  await new SubprocessHostCallTransport({
    executable: '/x/claude',
    model: 'sonnet',
    spawnImpl: fakeSpawn(withModel),
  }).generate(REQUEST);
  // The fake never prints a real help text, so every isolation flag is passed.
  const ISOLATION = [
    '--no-session-persistence', '--disable-slash-commands', '--strict-mcp-config',
    '--tools', '', '--settings', '{"disableAllHooks":true}',
  ];
  const BASE = ['--print', '--output-format', 'stream-json', '--verbose'];
  assert.deepEqual(withModel.args, [...BASE, '--model', 'sonnet', ...ISOLATION]);

  for (const model of [undefined, null]) {
    const without: { args?: readonly string[] } = {};
    await new SubprocessHostCallTransport({
      executable: '/x/claude',
      model,
      spawnImpl: fakeSpawn(without),
    }).generate(REQUEST);
    assert.deepEqual(without.args, [...BASE, ...ISOLATION]);
  }
});

test('transportForSnapshot sets CLAUDE_CONFIG_DIR only for non-default config roots', async () => {
  const home = makeHome();
  const saved = process.env.CLAUDE_CONFIG_DIR;
  delete process.env.CLAUDE_CONFIG_DIR;
  try {
    for (const [harness, expected] of [
      ['claude-code', undefined],
      ['claude-nine', join(home, '.claude-nine')],
    ] as const) {
      const { snapshot } = await resolveSessionRoute({ harness }, opts(home));
      const seen: { env?: NodeJS.ProcessEnv; model?: boolean } = {};
      const spawnImpl = ((_exe: string, args: readonly string[], o: { env: NodeJS.ProcessEnv }) => {
        if (args[0] !== '--help') {
          seen.env = o.env;
          seen.model = args.includes('--model');
        }
        return fakeSpawn({})(_exe, args);
      }) as unknown as typeof import('node:child_process').spawn;
      const t = transportForSnapshot(snapshot, { homeDir: home, env: { PATH: '/usr/bin:/bin' }, spawnImpl });
      await t!.generate(REQUEST);
      assert.equal(seen.env?.CLAUDE_CONFIG_DIR, expected);
      assert.equal(seen.model, harness === 'claude-code');
    }
  } finally {
    if (saved !== undefined) process.env.CLAUDE_CONFIG_DIR = saved;
  }
});

// -------------------------------------------------- W77S-MODES: routes

function providerHome(label: string, providers: Record<string, unknown>): string {
  const home = mkdtempSync(join(tmpdir(), `w77s-route-choice-${label}-`));
  mkdirSync(join(home, '.openclaw'), { recursive: true });
  writeFileSync(
    join(home, '.openclaw', 'openclaw.json'),
    JSON.stringify({ models: { providers } }),
    'utf8',
  );
  return home;
}

test('W77S: an ambiguous-model route is listed as usable-with-a-model, and resolves when one is named', async () => {
  const home = providerHome('ambiguous', {
    acme: {
      baseUrl: 'http://127.0.0.1:1234/v1',
      api: 'openai-completions',
      models: [{ id: 'model-a' }, { id: 'model-b' }],
    },
  });
  const options = listRouteOptions({ homeDir: home, env: { PATH: '' } });
  const acme = options.find((option) => option.route_id === 'acme-configured');
  assert.ok(acme);
  assert.equal(acme.composable, false);
  assert.equal(acme.failure_code, 'ROUTE_MODEL_AMBIGUOUS');
  assert.equal(acme.usable_with_model, true);
  assert.deepEqual(acme.model_candidates, ['model-a', 'model-b']);

  // Without a model the council refuses and names the candidates; it
  // never picks one itself.
  const bare = await refusal(resolveSessionRoute({ route_id: 'acme-configured' }, opts(home)));
  assert.equal(bare.code, 'ROUTE_NOT_COMPOSABLE');
  assert.ok(bare.message.includes('model-a'), 'the refusal names the candidates');
  assert.ok(bare.message.includes('model-b'));

  // With an explicit candidate the session route resolves and the
  // snapshot pins exactly that model.
  const resolved = await resolveSessionRoute(
    { route_id: 'acme-configured', model: 'model-b' },
    opts(home),
  );
  assert.equal(resolved.route.routeId, 'acme-configured');
  assert.equal(resolved.snapshot.requestedModelOrAlias, 'model-b');
  assert.equal(resolved.model_policy.requested_model_id, 'model-b');
  assert.equal(resolved.selection_source, 'explicit');
  assert.equal(resolved.model_label, 'model-b');
  // A model the route does not list is refused as not composable: the
  // route still has no usable model, and the council never substitutes.
  const notListed = await refusal(
    resolveSessionRoute(
      { route_id: 'acme-configured', model: 'model-z' },
      opts(home, modelList([])),
    ),
  );
  assert.equal(notListed.code, 'ROUTE_NOT_COMPOSABLE');
  assert.ok(notListed.message.includes('model-a'), 'the refusal names the candidates');
});

test('W77S: an Ollama route resolves and composes through the /v1 compatible profile', async () => {
  const home = providerHome('ollama', {
    ollama: {
      baseUrl: 'http://127.0.0.1:11434',
      api: 'ollama',
      models: [{ id: 'llama3.1:8b' }],
    },
  });
  const resolved = await resolveSessionRoute({ route_id: 'ollama-configured' }, opts(home));
  assert.equal(resolved.snapshot.requestedModelOrAlias, 'llama3.1:8b');
  assert.equal(resolved.route.compatible?.baseUrl, 'http://127.0.0.1:11434/v1');
  const transport = transportForSnapshot(resolved.snapshot, {
    homeDir: home,
    env: { PATH: '' },
  });
  assert.ok(transport instanceof CompatibleHttpTransport, 'the Ollama profile is the compatible transport');

  // An explicit model from the configured candidates is honoured on the
  // snapshot and still composes.
  const explicit = await resolveSessionRoute(
    { route_id: 'ollama-configured', model: 'llama3.1:8b' },
    opts(home),
  );
  assert.equal(explicit.snapshot.requestedModelOrAlias, 'llama3.1:8b');
  assert.ok(
    transportForSnapshot(explicit.snapshot, { homeDir: home, env: { PATH: '' } }) instanceof
      CompatibleHttpTransport,
  );
});
