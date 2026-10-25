/**
 * WER-007 route-discovery tests.
 *
 * Runner (the runtime's own runner):
 *   node --import tsx --test tests/route-discovery.test.ts
 *
 * Tier A only: no network, no credentials are printed, no provider
 * dispatch. Every host configuration is a synthetic directory created
 * under the OS temp directory. The real live-host probe, the second
 * configured model switch on a real box, and transport attribution are
 * deferred to WER-026/027 and are NOT claimed here.
 */

import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import {
  RouteDiscoveryError,
  buildRouteSnapshot,
  discoverConfiguredRoutes,
  discoverHostRoutes,
  discoverHostLayout,
  resolveDiscoveredCredential,
  resolveRouteForDispatch,
  routeDiscoveryInfo,
  routeOffersModel,
  routeUsableWithModel,
  type RouteSnapshotOptions,
} from '../src/cli/route-discovery.js';
import {
  UNKNOWN_ROUTE_IDENTITY,
  verifyRouteSnapshotHash,
  withTransportReportedIdentity,
} from '../src/providers/route-snapshot.js';

function makeHome(label: string): string {
  return mkdtempSync(join(tmpdir(), `w05u001-${label}-`));
}

function writeConfig(root: string, filename: string, text: string): void {
  mkdirSync(root, { recursive: true });
  writeFileSync(join(root, filename), text, 'utf8');
}

function snapshotOptions(overrides: Partial<RouteSnapshotOptions> = {}): RouteSnapshotOptions {
  return {
    sessionId: 'session-w05u001',
    sessionOwner: 'owner-w05u001',
    policySha256: 'a'.repeat(64),
    createdAt: '2026-10-18T12:00:00.000Z',
    capabilityVersion: 'catalog-w05u001',
    scope: {
      tenantId: 'tenant-w05u001',
      companyId: 'company-w05u001',
      installationId: 'install-w05u001',
      ownerSubject: 'owner-w05u001',
    },
    ...overrides,
  };
}

const NON_DEFAULT_ROOT_CONFIG = {
  agents: {
    entries: {
      main: { workspace: '' }, // filled per test
    },
    defaults: {
      workspace: '', // must lose to the selected agent override
      model: { primary: 'acme/model-b' },
    },
  },
  models: {
    providers: {
      acme: {
        baseUrl: 'http://127.0.0.1:1234/v1',
        api: 'openai-completions',
        models: [{ id: 'model-a' }, { id: 'model-b' }],
      },
    },
  },
  skills: { load: { extraDirs: [] as string[] } },
};

test('discovers routes under a NON-default config root and state root without touching ~/.openclaw', () => {
  const home = makeHome('nondefault');
  const root = join(home, 'custom-claw-root');
  const workspace = join(root, 'agent-main-workspace');
  const extraSkills = join(root, 'extra-skills');

  // A decoy ~/.openclaw must never be read when the host names another root.
  writeConfig(
    join(home, '.openclaw'),
    'openclaw.json',
    JSON.stringify({
      models: {
        providers: {
          decoy: { baseUrl: 'http://127.0.0.1:9999/v1', api: 'openai-completions', models: [{ id: 'decoy-model' }] },
        },
      },
    }),
  );

  const config = JSON.parse(JSON.stringify(NON_DEFAULT_ROOT_CONFIG)) as typeof NON_DEFAULT_ROOT_CONFIG;
  config.agents.entries.main.workspace = workspace;
  config.agents.defaults.workspace = join(root, 'wrong-default-workspace');
  config.skills.load.extraDirs = [extraSkills];
  writeConfig(root, 'openclaw.json', JSON.stringify(config));

  const env = { OPENCLAW_ROOT: root, PATH: '' };
  const { layout, routes } = discoverHostRoutes({ homeDir: home, env });

  assert.equal(layout.configRoot, root, 'the configured root is used, not ~/.openclaw');
  assert.equal(layout.stateRoot, root, 'state root is the actual host root');
  assert.equal(layout.configPath, join(root, 'openclaw.json'));
  assert.equal(layout.workspace, workspace);
  assert.equal(layout.workspaceSource, 'agent_override');
  assert.equal(layout.selectedAgentId, 'main');
  assert.ok(layout.extraSkillDirs.includes(extraSkills));
  assert.ok(
    layout.secretsEnvFiles.every((p) => p.startsWith(root)),
    'secret stores are resolved under the discovered root, not ~/.openclaw',
  );
  // The WER-005 receipt bridge answers the installed-runtime question; it
  // is consumed, not re-implemented, and its absence is explicit.
  assert.equal(layout.runtime.installed, false);
  assert.equal(layout.runtime.failureCode, 'RUNTIME_NOT_INSTALLED');
  assert.ok(layout.runtime.checked.some((p) => p.endsWith('active.json')));

  const ids = routes.map((r) => r.routeId);
  assert.deepEqual(ids, ['acme-configured']);
  assert.equal(ids.includes('decoy-configured'), false, 'the decoy ~/.openclaw is never read');

  const route = routes[0];
  assert.equal(route.composable, true);
  assert.equal(route.kind, 'compatible');
  assert.equal(route.compatible?.modelId, 'model-b', 'agent default primary wins over multiple models');
  assert.equal(route.host.configRoot, root);
  assert.equal(route.host.stateRoot, root);

  const serialized = JSON.stringify({ layout, routes });
  assert.equal(serialized.includes(join(home, '.openclaw')), false);
  assert.equal(serialized.includes('decoy-model'), false);

  assert.deepEqual(discoverConfiguredRoutes({ homeDir: home, env }), routes);
});

test('parses a JSON5 host configuration (comments, unquoted keys, single quotes, trailing commas)', () => {
  const home = makeHome('json5');
  const root = join(home, 'json5-root');
  const text = `{
    // host configuration in JSON5, as OpenClaw writes it
    agents: {
      defaults: { model: { primary: 'p5/m-one' }, },
    },
    models: {
      providers: {
        p5: {
          baseUrl: 'http://127.0.0.1:1234/v1',
          api: 'openai-completions',
          /* two configured models; the primary selects one */
          models: [ { id: 'm-one' }, { id: 'm-two' }, ],
        },
      },
    },
  }
  `;
  writeConfig(root, 'openclaw.json5', text);

  const layout = discoverHostLayout({ homeDir: home, env: { OPENCLAW_ROOT: root, PATH: '' } });
  assert.equal(layout.configFormat, 'json5');
  assert.equal(layout.configPath, join(root, 'openclaw.json5'));

  const routes = discoverConfiguredRoutes({ homeDir: home, env: { OPENCLAW_ROOT: root, PATH: '' } });
  const route = routes.find((r) => r.routeId === 'p5-configured');
  assert.ok(route);
  assert.equal(route.composable, true);
  assert.equal(route.compatible?.modelId, 'm-one');
});

test('resolves a named secret REFERENCE by name and never leaks the value into discovery, snapshot or error output', () => {
  const secretValue = 'sk-w05u001-do-not-print-3f9a';
  const secretName = 'W05_U001_TEST_KEY';
  const home = makeHome('secret');
  const root = join(home, 'secret-root');
  writeConfig(
    root,
    'openclaw.json',
    JSON.stringify({
      agents: { defaults: { model: { primary: 'acme/only-model' } } },
      models: {
        providers: {
          acme: {
            baseUrl: 'https://api.example.test/v1',
            api: 'openai-completions',
            apiKey: `\${${secretName}}`,
            models: [{ id: 'only-model' }],
          },
        },
      },
    }),
  );
  const env = { OPENCLAW_ROOT: root, PATH: '', [secretName]: secretValue };

  const { layout, routes } = discoverHostRoutes({ homeDir: home, env });
  assert.equal(routes.length, 1);
  const route = routes[0];
  assert.equal(route.composable, true);
  assert.equal(route.compatible?.credential.state, 'present');
  assert.equal(route.compatible?.credential.envVar, secretName);
  assert.equal(route.compatible?.credential.source, 'process.env');
  assert.equal(route.compatible?.credential.reference, `\${${secretName}}`);

  // The reference resolves by NAME at flight time only.
  assert.equal(resolveDiscoveredCredential(route, env), secretValue);

  const serialized = JSON.stringify({ layout, routes });
  assert.equal(serialized.includes(secretValue), false, 'discovery never copies the value');
  assert.ok(serialized.includes(`\${${secretName}}`), 'the reference is recorded, not the value');

  const { snapshot } = {
    snapshot: buildRouteSnapshot(route, snapshotOptions()),
  };
  assert.equal(JSON.stringify(snapshot).includes(secretValue), false, 'the receipt carries no value');
  assert.equal(verifyRouteSnapshotHash(snapshot), true);

  // An inaccessible reference is an explicit, secret-free failure.
  const missingRoot = join(home, 'missing-root');
  writeConfig(
    missingRoot,
    'openclaw.json',
    JSON.stringify({
      agents: { defaults: { model: { primary: 'acme/only-model' } } },
      models: {
        providers: {
          acme: {
            baseUrl: 'https://api.example.test/v1',
            api: 'openai-completions',
            apiKey: '${W05_U001_MISSING_KEY}',
            models: [{ id: 'only-model' }],
          },
        },
      },
    }),
  );
  let thrown: unknown;
  try {
    resolveRouteForDispatch('acme-configured', {
      homeDir: home,
      env: { OPENCLAW_ROOT: missingRoot, PATH: '' },
    });
  } catch (err) {
    thrown = err;
  }
  assert.ok(thrown instanceof RouteDiscoveryError);
  assert.equal(thrown.code, 'ROUTE_SECRET_REFERENCE_UNRESOLVED');
  assert.ok(thrown.message.includes('W05_U001_MISSING_KEY'), 'the reference NAME is named');
  assert.equal(thrown.message.includes(secretValue), false, 'no secret value in the error');
  assert.equal(JSON.stringify(thrown.checked).includes(secretValue), false);
});

test('an unsupported provider API family fails explicitly and is never reinterpreted as OpenAI-compatible', () => {
  const home = makeHome('family');
  const root = join(home, 'family-root');
  writeConfig(
    root,
    'openclaw.json',
    JSON.stringify({
      agents: { defaults: { model: { primary: 'anth/claude-model' } } },
      models: {
        providers: {
          anth: {
            baseUrl: 'https://api.anthropic.example/v1',
            api: 'anthropic-messages',
            apiKey: '${ANTHROPIC_KEY}',
            models: [{ id: 'claude-model' }],
          },
          unlabelled: {
            baseUrl: 'https://api.unlabelled.example/v1',
            apiKey: '${UNLABELLED_KEY}',
            models: [{ id: 'mystery-model' }],
          },
        },
      },
    }),
  );
  const env = {
    OPENCLAW_ROOT: root,
    PATH: '',
    ANTHROPIC_KEY: 'test-anthropic-value',
    UNLABELLED_KEY: 'test-unlabelled-value',
  };
  const routes = discoverConfiguredRoutes({ homeDir: home, env });

  const anthropicRoute = routes.find((r) => r.routeId === 'anth-configured');
  assert.ok(anthropicRoute);
  assert.equal(anthropicRoute.kind, 'unsupported');
  assert.equal(anthropicRoute.composable, false);
  assert.equal(anthropicRoute.compatible?.apiFamily, 'anthropic_messages');
  assert.equal(anthropicRoute.failure?.code, 'ROUTE_API_FAMILY_UNSUPPORTED');

  // A provider that declares no API family is not assumed compatible either.
  const unlabelled = routes.find((r) => r.routeId === 'unlabelled-configured');
  assert.ok(unlabelled);
  assert.equal(unlabelled.kind, 'unsupported');
  assert.equal(unlabelled.failure?.code, 'ROUTE_API_FAMILY_UNSUPPORTED');

  let thrown: unknown;
  try {
    resolveRouteForDispatch('anth-configured', { homeDir: home, env });
  } catch (err) {
    thrown = err;
  }
  assert.ok(thrown instanceof RouteDiscoveryError);
  assert.equal(thrown.code, 'ROUTE_API_FAMILY_UNSUPPORTED');
  assert.ok(thrown.message.includes('anthropic_messages'));
  assert.equal(routes.length, 2, 'no substitute default route is invented');
  assert.equal(anthropicRoute.compatible?.modelId, 'claude-model');
});

test('an ambiguous model selection fails instead of picking one of several configured models', () => {
  const home = makeHome('ambiguous');
  const root = join(home, 'ambiguous-root');
  writeConfig(
    root,
    'openclaw.json',
    JSON.stringify({
      models: {
        providers: {
          acme: {
            baseUrl: 'http://127.0.0.1:1234/v1',
            api: 'openai-completions',
            models: [{ id: 'model-a' }, { id: 'model-b' }],
          },
        },
      },
    }),
  );
  const env = { OPENCLAW_ROOT: root, PATH: '' };
  const routes = discoverConfiguredRoutes({ homeDir: home, env });
  assert.equal(routes.length, 1);
  const route = routes[0];
  assert.equal(route.composable, false);
  assert.equal(route.failure?.code, 'ROUTE_MODEL_AMBIGUOUS');
  assert.equal(route.compatible?.modelId, null, 'no model is chosen');
  assert.deepEqual(route.compatible?.modelCandidates, ['model-a', 'model-b']);

  let thrown: unknown;
  try {
    resolveRouteForDispatch('acme-configured', { homeDir: home, env });
  } catch (err) {
    thrown = err;
  }
  assert.ok(thrown instanceof RouteDiscoveryError);
  assert.equal(thrown.code, 'ROUTE_MODEL_AMBIGUOUS');
  assert.ok(thrown.message.includes('model-a'));
  assert.ok(thrown.message.includes('model-b'));
});

test('discovered routes freeze through verifyRouteSnapshotHash and keep unreported identity UNKNOWN', () => {
  const home = makeHome('snapshot');
  const root = join(home, 'snapshot-root');
  writeConfig(
    root,
    'openclaw.json',
    JSON.stringify({
      agents: { defaults: { model: { primary: 'acme/only-model' } } },
      models: {
        providers: {
          acme: {
            baseUrl: 'http://127.0.0.1:1234/v1',
            api: 'openai-completions',
            models: [{ id: 'only-model', contextWindow: 200000, maxTokens: 32000 }],
          },
        },
      },
    }),
  );
  const env = { OPENCLAW_ROOT: root, PATH: '' };
  const { route } = resolveRouteForDispatch('acme-configured', { homeDir: home, env });

  const snapshot = buildRouteSnapshot(route, snapshotOptions());
  assert.equal(snapshot.schema, 'wise-elders.route-snapshot/v1');
  assert.equal(verifyRouteSnapshotHash(snapshot), true);
  assert.equal(snapshot.identity.configured.providerSlug, 'acme');
  assert.equal(snapshot.identity.configured.modelId, 'only-model');
  assert.equal(snapshot.identity.configured.accountRef, null);
  assert.equal(snapshot.host.apiFamily, 'openai_compatible');
  assert.equal(snapshot.capabilityVersion, 'catalog-w05u001');
  assert.equal(snapshot.selection.capabilitySnapshot.contextWindowTokens, 200000);

  // Discovery is not a probe: transport-reported identity stays UNKNOWN.
  assert.deepEqual(snapshot.identity.transportReported, {
    state: 'unknown',
    modelId: UNKNOWN_ROUTE_IDENTITY,
    reason: 'probe_deferred',
  });
  assert.equal(snapshot.identity.combinationMembers, null);

  // Combination pins keep each unreported member UNKNOWN and still verify.
  const combination = buildRouteSnapshot(
    route,
    snapshotOptions({ combination: { alias: 'elder-pair', members: ['member-1', 'member-2'] } }),
  );
  assert.equal(verifyRouteSnapshotHash(combination), true);
  assert.equal(combination.selection.routeKind, 'combination');
  assert.equal(combination.identity.combinationMembers?.length, 2);
  for (const member of combination.identity.combinationMembers ?? []) {
    assert.deepEqual(member.reported, {
      state: 'unknown',
      modelId: UNKNOWN_ROUTE_IDENTITY,
      reason: 'probe_deferred',
    });
  }

  // Recording evidence later is a new snapshot with the SAME pin hash, and
  // the unreported member stays UNKNOWN.
  const withEvidence = withTransportReportedIdentity(combination, {
    state: 'reported',
    modelId: 'member-1',
    providerRequestId: null,
  });
  assert.equal(verifyRouteSnapshotHash(withEvidence), true);
  assert.equal(withEvidence.snapshotSha256, combination.snapshotSha256);
  const reported = withEvidence.identity.combinationMembers?.find(
    (m) => m.memberModelId === 'member-1',
  );
  const silent = withEvidence.identity.combinationMembers?.find(
    (m) => m.memberModelId === 'member-2',
  );
  assert.equal(reported?.reported.state, 'reported');
  assert.equal(silent?.reported.state, 'unknown');
});

test('missing host configuration and unknown route ids fail explicitly', () => {
  const home = makeHome('missing');
  const env = { PATH: '' };

  let missing: unknown;
  try {
    resolveRouteForDispatch('acme-configured', { homeDir: home, env });
  } catch (err) {
    missing = err;
  }
  assert.ok(missing instanceof RouteDiscoveryError);
  assert.equal(missing.code, 'ROUTE_HOST_CONFIG_MISSING');
  assert.ok(missing.checked.some((p) => p.endsWith('openclaw.json')));

  const root = join(home, 'present-root');
  writeConfig(
    root,
    'openclaw.json',
    JSON.stringify({
      agents: { defaults: { model: { primary: 'acme/only-model' } } },
      models: {
        providers: {
          acme: {
            baseUrl: 'http://127.0.0.1:1234/v1',
            api: 'openai-completions',
            models: [{ id: 'only-model' }],
          },
        },
      },
    }),
  );

  let unknown: unknown;
  try {
    resolveRouteForDispatch('other-configured', {
      homeDir: home,
      env: { OPENCLAW_ROOT: root, PATH: '' },
    });
  } catch (err) {
    unknown = err;
  }
  assert.ok(unknown instanceof RouteDiscoveryError);
  assert.equal(unknown.code, 'ROUTE_ID_UNKNOWN');
  assert.ok(unknown.message.includes('acme-configured'));
  assert.ok(unknown.message.includes('does not fall back'));
});

test('conflicting workspace pins fail explicitly instead of choosing one', () => {
  const home = makeHome('conflict');
  const root = join(home, 'conflict-root');
  writeConfig(root, 'openclaw.json', JSON.stringify({ models: { providers: {} } }));
  let thrown: unknown;
  try {
    discoverHostLayout({
      homeDir: home,
      env: {
        OPENCLAW_ROOT: root,
        PATH: '',
        OPENCLAW_WORKSPACE_PATH: join(root, 'a'),
        OPENCLAW_WORKSPACE_ROOT: join(root, 'b'),
      },
    });
  } catch (err) {
    thrown = err;
  }
  assert.ok(thrown instanceof RouteDiscoveryError);
  assert.equal(thrown.code, 'ROUTE_HOST_CONFIG_INVALID');
});

// -------------------------------------------------- W77S-MODES: routes

/** A host whose only provider is an Ollama endpoint, written as given. */
function ollamaHome(label: string, provider: Record<string, unknown>): string {
  const home = makeHome(label);
  writeConfig(
    join(home, '.openclaw'),
    'openclaw.json',
    JSON.stringify({ models: { providers: { ollama: provider } } }),
  );
  return home;
}

test('W77S: an ollama route composes through the /v1 compatible surface', () => {
  const home = ollamaHome('ollama-local', {
    baseUrl: 'http://127.0.0.1:11434',
    api: 'ollama',
    models: [{ id: 'llama3.1:8b' }],
  });
  const env = { OPENCLAW_ROOT: join(home, '.openclaw'), PATH: '' };
  const routes = discoverConfiguredRoutes({ homeDir: home, env });
  assert.equal(routes.length, 1);
  const route = routes[0];
  assert.equal(route.routeId, 'ollama-configured');
  assert.equal(route.kind, 'compatible');
  assert.equal(route.composable, true, route.notComposableReason ?? '');
  assert.equal(route.failure, null);
  assert.equal(route.compatible?.baseUrl, 'http://127.0.0.1:11434/v1');
  assert.equal(route.compatible?.apiFamily, 'ollama_chat');
  assert.equal(route.compatible?.modelId, 'llama3.1:8b');
  // A local daemon needs no credential, and nothing is invented for it.
  assert.equal(route.compatible?.credential.state, 'not_required');

  // An endpoint that already carries /v1 is left exactly as configured.
  const already = ollamaHome('ollama-v1', {
    baseUrl: 'http://127.0.0.1:11434/v1',
    api: 'ollama',
    models: [{ id: 'llama3.1:8b' }],
  });
  const again = discoverConfiguredRoutes({
    homeDir: already,
    env: { OPENCLAW_ROOT: join(already, '.openclaw'), PATH: '' },
  });
  assert.equal(again[0].compatible?.baseUrl, 'http://127.0.0.1:11434/v1');
});

test('W77S: Ollama Cloud composes with its configured key reference and /v1', () => {
  const home = makeHome('ollama-cloud');
  writeConfig(
    join(home, '.openclaw'),
    'openclaw.json',
    JSON.stringify({
      models: {
        providers: {
          'ollama-cloud': {
            baseUrl: 'https://ollama.com',
            api: 'ollama',
            apiKey: '${OLLAMA_CLOUD_KEY}',
            models: [{ id: 'qwen3:cloud' }],
          },
        },
      },
    }),
  );
  const env = {
    OPENCLAW_ROOT: join(home, '.openclaw'),
    OLLAMA_CLOUD_KEY: 'fixture-value-not-a-real-key',
    PATH: '',
  };
  const route = discoverConfiguredRoutes({ homeDir: home, env })[0];
  assert.equal(route.composable, true, route.notComposableReason ?? '');
  assert.equal(route.compatible?.baseUrl, 'https://ollama.com/v1');
  assert.equal(route.compatible?.credential.state, 'present');
  assert.equal(route.compatible?.credential.envVar, 'OLLAMA_CLOUD_KEY');
  // The report carries the NAME and the checked stores, never the value.
  assert.equal(JSON.stringify(route.compatible?.credential).includes('fixture-value'), false);
});

test('W77S: a route whose only failure is model ambiguity becomes usable with a named model', () => {
  const home = makeHome('ambiguous');
  writeConfig(
    join(home, '.openclaw'),
    'openclaw.json',
    JSON.stringify({
      models: {
        providers: {
          acme: {
            baseUrl: 'http://127.0.0.1:1234/v1',
            api: 'openai-completions',
            models: [{ id: 'model-a' }, { id: 'model-b' }],
          },
        },
      },
    }),
  );
  const env = { OPENCLAW_ROOT: join(home, '.openclaw'), PATH: '' };
  const route = discoverConfiguredRoutes({ homeDir: home, env })[0];
  assert.equal(route.composable, false);
  assert.equal(route.failure?.code, 'ROUTE_MODEL_AMBIGUOUS');
  assert.equal(routeUsableWithModel(route), true, 'nothing else blocks this route');
  assert.deepEqual(route.compatible?.modelCandidates, ['model-a', 'model-b']);
  assert.equal(routeOffersModel(route, 'model-b'), true);
  assert.equal(routeOffersModel(route, 'model-c'), false);
  assert.equal(routeOffersModel(route, null), false);

  // Strict resolution: no model is a refusal, never a guess.
  assert.throws(
    () => resolveRouteForDispatch('acme-configured', { homeDir: home, env }),
    (error: unknown) =>
      error instanceof RouteDiscoveryError && error.code === 'ROUTE_MODEL_AMBIGUOUS',
  );
  // A model outside the candidate list is refused the same way.
  assert.throws(
    () => resolveRouteForDispatch('acme-configured', { homeDir: home, env }, 'model-c'),
    (error: unknown) =>
      error instanceof RouteDiscoveryError && error.code === 'ROUTE_MODEL_AMBIGUOUS',
  );
  // An explicit candidate makes it usable, and the snapshot pins it.
  const resolved = resolveRouteForDispatch('acme-configured', { homeDir: home, env }, 'model-b');
  assert.equal(resolved.route.routeId, 'acme-configured');
  const snapshot = buildRouteSnapshot(resolved.route, snapshotOptions({ model: 'model-b' }));
  assert.equal(snapshot.selection.requestedModelOrAlias, 'model-b');
  assert.equal(snapshot.identity.configured.modelId, 'model-b', 'the caller-chosen model is what the snapshot pins');

  // The listing shows usable-with-a-model and the candidates.
  const info = routeDiscoveryInfo(route, false);
  assert.equal(info.usable_with_model, true);
  assert.deepEqual(info.model_candidates, ['model-a', 'model-b']);
});
