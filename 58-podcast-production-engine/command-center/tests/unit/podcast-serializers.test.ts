/**
 * Serializer boundary proof (dashboard-design Section 9, acceptance
 * criterion 6): the client serializers must never emit any operator-only
 * field, verified on the serialized JSON itself, not the UI. Runs with the
 * repo's standard unit runner: node --import tsx --test tests/unit/*.test.ts
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  OPERATOR_ONLY_JOB_KEYS,
  toClientEvents,
  toClientJob,
  toClientQueueRow,
  toOperatorEvents,
  toOperatorJob,
  toOperatorQueueRow,
  toSummary,
} from '../../src/lib/podcast/serializers';
import { STAGE_META, PIPELINE_ORDER, progressFor, stageMetaFor } from '../../src/lib/podcast/stages';
import type { PodcastJobRow, PodcastJobEventRow, PodcastStatus } from '../../src/lib/podcast/types';

function fullyPopulatedRow(): PodcastJobRow {
  return {
    job_id: 'pj_01HZXTESTROW0000000000000',
    client_id: 'test-client',
    location_id: 'loc_internal_test',
    contact_id: 'contact_test_1',
    submission_fingerprint: 'f'.repeat(64),
    mode: 'interview_style_podcast',
    style: 'provocative',
    show_name: 'Test Show',
    host_name: 'Test Host',
    submitter_first_name: 'Pat',
    submitter_last_name: 'Example',
    submitter_email: 'pat@example.com',
    submitter_phone: '+15550100000',
    status: 'queued_credit_out',
    resume_stage: 'producing_audio',
    attempt_count: 2,
    failed_step: 'step_11_audio',
    last_error: 'sanitized error text',
    queue_state: 'held',
    queued_at: '2026-07-01 00:00:00',
    queued_service: 'fish_audio',
    queue_deadline: '2026-08-30 00:00:00',
    aged_out_at: null,
    cost_accrued_usd: 1.23,
    writing_model: 'kimi-2.6',
    research_tool: 'perplexity',
    episode_title: 'A Test Episode',
    episode_description: 'Description',
    episode_number: 7,
    podbean_permalink: 'https://example.com/e/7',
    episode_package_url: 'https://example.com/pkg',
    speech_script_url: 'https://example.com/script',
    book_teaser_url: 'https://example.com/teaser',
    mp3_media_url: 'https://example.com/audio.mp3',
    cover_image_url: 'https://example.com/cover.jpg',
    spoken_word_count: 1400,
    runtime_minutes: 10,
    publish_timestamp: null,
    created_at: '2026-06-30 00:00:00',
    updated_at: '2026-07-01 00:00:00',
    completed_at: null,
    pii_scrubbed_at: null,
  };
}

test('client job serialization emits zero operator-only keys', () => {
  const clientJson = JSON.parse(JSON.stringify(toClientJob(fullyPopulatedRow())));
  for (const key of OPERATOR_ONLY_JOB_KEYS) {
    assert.equal(key in clientJson, false, `client payload leaked operator key: ${key}`);
  }
  // Spot-check leak-prone values never appear anywhere in the client JSON.
  const flat = JSON.stringify(clientJson);
  assert.equal(flat.includes('fish_audio'), false, 'client payload leaked the depleted service');
  assert.equal(flat.includes('kimi-2.6'), false, 'client payload leaked the writing model');
  assert.equal(flat.includes('1.23'), false, 'client payload leaked cost');
  assert.equal(flat.includes('step_11_audio'), false, 'client payload leaked failed step');
  assert.equal(flat.includes('sanitized error text'), false, 'client payload leaked error text');
  assert.equal(flat.includes('loc_internal_test'), false, 'client payload leaked location id');
});

test('client job serialization keeps the SPEC-required fields', () => {
  const job = toClientJob(fullyPopulatedRow());
  assert.equal(job.submitterFirstName, 'Pat');
  assert.equal(job.submitterLastName, 'Example');
  assert.equal(job.submitterEmail, 'pat@example.com');
  assert.equal(job.submitterPhone, '+15550100000');
  assert.equal(job.episodeTitle, 'A Test Episode');
  assert.equal(job.links.podbeanPermalink, 'https://example.com/e/7');
  assert.equal(typeof job.heldDays, 'number');
});

test('operator job serialization carries the verbose fields', () => {
  const job = toOperatorJob(fullyPopulatedRow());
  assert.equal(job.costAccruedUsd, 1.23);
  assert.equal(job.attemptCount, 2);
  assert.equal(job.writingModel, 'kimi-2.6');
  assert.equal(job.queuedService, 'fish_audio');
  assert.equal(job.failedStep, 'step_11_audio');
  assert.equal(job.resumeStage, 'producing_audio');
});

test('client events drop notes, cost deltas, and non-transition events', () => {
  const rows: PodcastJobEventRow[] = [
    { event_id: 1, job_id: 'pj_x', at: '2026-07-01 00:00:00', from_status: 'received', to_status: 'researching', note: 'internal note', cost_delta_usd: 0.5 },
    { event_id: 2, job_id: 'pj_x', at: '2026-07-01 00:01:00', from_status: null, to_status: null, note: 'cost marker', cost_delta_usd: 0.9 },
  ];
  const clientEvents = JSON.parse(JSON.stringify(toClientEvents(rows)));
  assert.equal(clientEvents.length, 1, 'non-transition events must not reach clients');
  assert.equal('note' in clientEvents[0], false);
  assert.equal('costDeltaUsd' in clientEvents[0], false);
  const operatorEvents = toOperatorEvents(rows);
  assert.equal(operatorEvents.length, 2);
  assert.equal(operatorEvents[0].note, 'internal note');
  assert.equal(operatorEvents[1].costDeltaUsd, 0.9);
});

test('client queue rows never name the depleted service', () => {
  const clientRow = JSON.parse(JSON.stringify(toClientQueueRow(fullyPopulatedRow())));
  assert.equal('queuedService' in clientRow, false);
  assert.equal('queueDeadline' in clientRow, false);
  assert.equal('resumeStage' in clientRow, false);
  const operatorRow = toOperatorQueueRow(fullyPopulatedRow(), true);
  assert.equal(operatorRow.queuedService, 'fish_audio');
  assert.equal(operatorRow.payloadPresent, true);
});

test('summary hides spend from clients and shows it to operators', () => {
  const counts = { inProduction: 1, published: 2, publishedThisMonth: 1, held: 1, failed: 0, spendThisMonth: 3.21 };
  const clientSummary = JSON.parse(JSON.stringify(toSummary(counts, false)));
  assert.equal('spendThisMonth' in clientSummary, false);
  const operatorSummary = toSummary(counts, true);
  assert.equal(operatorSummary.spendThisMonth, 3.21);
});

test('stage taxonomy covers every status and aged-out override applies', () => {
  const statuses: PodcastStatus[] = [
    'received', 'researching', 'writing', 'in_qc', 'generating_art',
    'producing_audio', 'publishing', 'enrolling', 'complete', 'failed', 'queued_credit_out',
  ];
  for (const s of statuses) {
    assert.ok(STAGE_META[s], `missing stage meta for ${s}`);
    assert.ok(STAGE_META[s].clientLabel.length > 0);
  }
  assert.equal(stageMetaFor('failed', 'aged_out').clientLabel, 'Expired');
  assert.equal(PIPELINE_ORDER.length, 9, 'the progress meter is 9 segments');
  assert.equal(progressFor('complete', null).filled, 9);
  assert.equal(progressFor('received', null).filled, 1);
});
