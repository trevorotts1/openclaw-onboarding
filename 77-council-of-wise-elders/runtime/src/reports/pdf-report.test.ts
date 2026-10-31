/**
 * CTR-136 saved-session PDF report tests (regression, UNEXECUTED in the
 * CTR-136 lane build; Trevor owns running tests).
 *
 * Runner (the runtime's own test runner):
 *   node --import tsx --test src/reports/pdf-report.test.ts
 *
 * What these two cases pin, without any network, provider call or
 * installed service:
 * - a report is built only from a completed sitting: before COMPLETED,
 *   neither the verdict nor the renderer is touched, and each refusal is
 *   a typed code with a status the front door can send;
 * - the served document is a real PDF attachment: the filename is built
 *   from IDs only, the media type is application/pdf, metadata pinning
 *   is length-preserving, and HTML is rejected instead of being served
 *   as a PDF.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import type { TrustedPrincipal } from '../authorization/index.js';
import type { StoredSession } from '../cli/host-ports.js';
import {
  composeCouncilReportDownload,
  createHostPdfRenderer,
  pinVolatilePdfMetadata,
  validatePdfBytes,
  type CouncilReportDownloadDeps,
} from './index.js';
import { ReportExportError } from './errors.js';
import { REPORT_FORMAT_REGISTRY, reportFilename } from './registry.js';

const principal: TrustedPrincipal = {
  tenant_id: 'local-tenant',
  company_id: 'local-company',
  installation_id: 'install-test',
  subject: 'local-owner',
  channel: 'local_owner',
  support_access: false,
};

function session(state: string): StoredSession {
  return {
    spec: {
      session_id: 'session-test-1',
      question: 'Which option should we take?',
      mode: 'medium',
      seat_ids: [],
      visibility: 'private',
      created_at: '2026-10-30T00:00:00.000Z',
    },
    brief: {} as StoredSession['brief'],
    scope: {
      tenant_id: 'local-tenant',
      company_id: 'local-company',
      installation_id: 'install-test',
      owner_subject: 'local-owner',
    },
    state: { state } as StoredSession['state'],
    sample: false,
  } as StoredSession;
}

test('a saved-session report is refused before any verdict or renderer work until the sitting completes', async () => {
  const watched = { verdict: 0, render: 0 };
  const port = composeCouncilReportDownload({
    readSession: () => session('DELIBERATING'),
    listCards: () => [],
    readVerdict: () => {
      watched.verdict += 1;
      return null;
    },
    isSessionDeleted: () => false,
    journal: {
      async appendExportRecord() {},
      async findExportRecord() {
        return null;
      },
    },
    principal,
    pdf: {
      probe: () => ({ available: true, method: 'chrome-headless', executable: '/bin/false', detail: 'test' }),
      async render() {
        watched.render += 1;
        return Buffer.alloc(0);
      },
    },
    nowUtc: () => '2026-10-30T12:00:00.000Z',
  });

  const unknownDeps: CouncilReportDownloadDeps = {
    readSession: () => null,
    listCards: () => [],
    readVerdict: () => null,
    isSessionDeleted: () => false,
    journal: {
      async appendExportRecord() {},
      async findExportRecord() {
        return null;
      },
    },
    principal,
    pdf: {
      probe: () => ({ available: true, method: 'chrome-headless', executable: '/bin/false', detail: 'test' }),
      async render() {
        return Buffer.alloc(0);
      },
    },
    nowUtc: () => '2026-10-30T12:00:00.000Z',
  };
  const missing = await composeCouncilReportDownload(unknownDeps).readPdf({
    session_id: 'session-unknown',
  });
  assert.equal(missing.ok, false);
  if (!missing.ok) {
    assert.equal(missing.status, 404);
    assert.equal(missing.code, 'SESSION_NOT_FOUND');
  }

  const unfinished = await port.readPdf({ session_id: 'session-test-1' });
  assert.equal(unfinished.ok, false);
  if (!unfinished.ok) {
    assert.equal(unfinished.status, 409);
    assert.equal(unfinished.code, 'REPORT_SESSION_NOT_COMPLETE');
  }
  // No verdict read, no render: the report has no input to invent from.
  assert.equal(watched.verdict, 0);
  assert.equal(watched.render, 0);
});

test('the download contract is a real PDF attachment built from IDs only', async () => {
  const filename = reportFilename({
    session_id: 'session-test-1',
    verdict_revision: 2,
    format: 'pdf',
    redacted: false,
  });
  assert.equal(filename, 'council-report-session-test-1-r2.pdf');
  assert.match(filename, /^[A-Za-z0-9._-]+$/);
  assert.equal(REPORT_FORMAT_REGISTRY.pdf.media_type, 'application/pdf');

  // HTML is never a PDF, however it is named.
  assert.throws(
    () => validatePdfBytes(Buffer.from('<!doctype html><p>print me</p>')),
    (error: unknown) => error instanceof ReportExportError && error.code === 'EXPORT_RENDER_FAILED',
  );

  // A disabled host says so with the typed not-ready refusal.
  const renderer = createHostPdfRenderer({ PATH: '', HOME: '/nonexistent', COUNCIL_PDF_DISABLED: '1' });
  const capability = renderer.probe();
  assert.equal(capability.available, false);
  await assert.rejects(
    () => renderer.render('<html></html>'),
    (error: unknown) => error instanceof ReportExportError && error.code === 'EXPORT_FORMAT_NOT_READY',
  );

  // Volatile metadata pinning keeps the byte length, so the PDF xref stays valid.
  const sample = Buffer.from(
    '%PDF-1.4\n/CreationDate (D:20261030120000Z) /ModDate (D:20261030120000Z)\n/ID [<A1B2C3D4><E5F6A7B8>]\n%%EOF\n',
    'latin1',
  );
  const pinned = pinVolatilePdfMetadata(sample);
  assert.equal(pinned.length, sample.length);
  assert.equal(pinned.toString('latin1').includes('20261030120000'), false);
});
