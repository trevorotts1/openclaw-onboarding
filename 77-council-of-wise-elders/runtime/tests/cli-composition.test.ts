/**
 * CWE-050 CLI composition tests (ONBOARDING/PORTABLE stream): the
 * standalone CLI surface composed from the accepted parts.
 *
 * - CWE-049 standalone list item 1: `authorization` delegates to
 *   CWE-049's handler; doctor reports the service composed.
 * - CWE-049 standalone list item 2: `create` binds the session to the
 *   provisioned installation scope (localScope alignment) and mirrors
 *   it into the authorization store at creation, so a preview freezes
 *   exactly what was created.
 * - B15 portable half: `export` runs through CWE-038's
 *   ReportExportService: the markdown is the validated decision
 *   report carrying the exact verdict hash, JSON mode returns the
 *   registered deliverable, and PDF refuses as not ready (CWE-044).
 */
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { runCli, type CliIo } from '../src/cli/dispatcher.js';
import { buildSampleSession } from '../src/cli/fixture-transport.js';
import {
  resolveStandaloneInstallation,
  standaloneScope,
} from '../src/cli/authorization.js';
import type { PinnedRouteSnapshot } from '../src/budgets/index.js';

function capture() {
  let out = '';
  let err = '';
  const io: CliIo = {
    out: (t: string) => {
      out += t;
    },
    err: (t: string) => {
      err += t;
    },
  };
  return { io, out: () => out, err: () => err };
}

test('cli composition: create mirrors into the authorization store; preview and export run composed', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'cwe050-cli-'));
  const sample = buildSampleSession();
  const specPath = join(dir, 'spec.json');
  const briefPath = join(dir, 'brief.json');
  writeFileSync(specPath, JSON.stringify(sample.spec), 'utf8');
  writeFileSync(briefPath, JSON.stringify(sample.brief), 'utf8');

  let c = capture();
  assert.equal(
    await runCli(
      ['create', '--spec', specPath, '--brief', briefPath, '--json', '--data-dir', dir],
      c.io,
    ),
    0,
  );
  const created = JSON.parse(c.out()) as { session_id: string; sample: boolean };
  assert.equal(created.session_id, sample.spec.session_id);
  assert.equal(created.sample, false);

  // The preview only works because create mirrored the session into
  // the authorization store in the same installation namespace.
  const scopeFields = standaloneScope(resolveStandaloneInstallation(dir));
  const snapshot: PinnedRouteSnapshot = {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: 'explicit',
    routeId: sample.spec.model_policy.route_id,
    routeRevision: 1,
    routeKind: 'fixed_model',
    providerSlug: 'provider-fixture',
    requestedRoute: sample.spec.model_policy.route_id,
    requestedModelOrAlias: 'model-fixture',
    combinationMembers: null,
    reasoning: { requested: null, applied: null, supported: null, limitation: null },
    fallbackPolicy: 'none',
    providerAccountRef: null,
    capabilitySnapshot: {
      contextWindowTokens: 200000,
      maxOutputTokens: 8000,
      capabilities: ['text'],
      supportedReasoningLevels: null,
    },
    credential: {
      state: 'present',
      envVar: 'PROVIDER_FIXTURE_API_KEY',
      source: 'process.env',
      checked: ['process.env'],
    },
    identityLevel: 'configured',
    scope: {
      tenantId: scopeFields.tenant_id,
      companyId: scopeFields.company_id,
      installationId: scopeFields.installation_id,
      ownerSubject: scopeFields.owner_subject,
    },
    createdAt: '2026-10-14T12:00:00.000Z',
  };
  const snapshotPath = join(dir, 'route-snapshot.json');
  writeFileSync(snapshotPath, JSON.stringify(snapshot), 'utf8');

  c = capture();
  assert.equal(
    await runCli(
      [
        'authorization', 'preview', sample.spec.session_id,
        '--route-snapshot', snapshotPath,
        '--json', '--data-dir', dir,
      ],
      c.io,
    ),
    0,
  );
  const preview = JSON.parse(c.out()) as { preview: { preview_id: string } };
  assert.ok(preview.preview.preview_id, 'the composed preview returns a preview id');

  c = capture();
  assert.equal(
    await runCli(['doctor', '--json', '--data-dir', dir], c.io),
    0,
  );
  const doctor = JSON.parse(c.out()) as {
    checks: Array<{ name: string; ok: boolean; detail: string }>;
  };
  const authCheck = doctor.checks.find((x) => x.name === 'run_authorization_service');
  assert.equal(authCheck?.ok, true);
  assert.ok(authCheck?.detail.includes('composed'));

  // Complete the sample session in its own data directory (the
  // sample fixture carries a fixed session ID, already used above),
  // then export through CWE-038.
  const sampleDir = mkdtempSync(join(tmpdir(), 'cwe050-cli-sample-'));
  c = capture();
  assert.equal(await runCli(['sample', 'run', '--json', '--data-dir', sampleDir], c.io), 0);

  c = capture();
  assert.equal(
    await runCli(['verdict', 'sess-fixture-1', '--json', '--data-dir', sampleDir], c.io),
    0,
  );
  const verdictEnvelope = JSON.parse(c.out()) as {
    verdict: { content_sha256: string };
  };
  const verdict = verdictEnvelope.verdict;
  assert.equal(verdict.content_sha256.length, 64);

  const outPath = join(sampleDir, 'report.md');
  c = capture();
  assert.equal(
    await runCli(
      ['export', 'sess-fixture-1', '--format', 'md', '--out', outPath, '--json', '--data-dir', sampleDir],
      c.io,
    ),
    0,
  );
  const exported = JSON.parse(c.out()) as {
    deliverable_id: string;
    verdict_content_sha256: string;
  };
  assert.equal(exported.verdict_content_sha256, verdict.content_sha256);
  const markdown = readFileSync(outPath, 'utf8');
  assert.ok(markdown.includes('# Council of Wise Elders: Decision Report'));
  assert.ok(markdown.includes(verdict.content_sha256));

  c = capture();
  assert.equal(
    await runCli(['export', 'sess-fixture-1', '--format', 'pdf', '--json', '--data-dir', sampleDir], c.io),
    3,
  );
  assert.equal(
    (JSON.parse(c.err()) as { error: { code: string } }).error.code,
    'COUNCIL_FEATURE_NOT_READY',
  );
});
