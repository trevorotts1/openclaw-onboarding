// ============================================================================
// Book Writer mini-app — U18 e2e fixtures (offline, FICTITIOUS only)
// ----------------------------------------------------------------------------
// Two fake clients (alpha / beta) plus the configs the suite drives. The phase
// configs are the REAL ones shipped by U01 (mini-app/configs/*.json), served
// by the stub Worker exactly as the real Worker (U02) serves them from R2. The
// KV binding rows are the SOLE destination authority (mirrors U02/U03/U15) —
// they carry client_id + location_id so the box poller / write-back knows where
// each answer lands. No real names, no real locations, no credentials.
// ============================================================================

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const miniAppRoot = path.resolve(here, '../..');
const configsDir = path.join(miniAppRoot, 'configs');

function loadConfig(name) {
  return JSON.parse(readFileSync(path.join(configsDir, name), 'utf8'));
}

// Real U01 configs, so the e2e exercises production data shapes.
export const CONFIG_P0_INTAKE = loadConfig('P0-INTAKE-full.json');   // 16 questions
export const CONFIG_GATE_1 = loadConfig('GATE-1-title.json');         //  2 questions
export const CONFIG_GATE_2 = loadConfig('GATE-2-outline.json');       //  1 question

// ---------------------------------------------------------------------------
// FICTITIOUS clients — alpha and beta. Each owns a token, a slug, a phase, a
// run, a client_id, and a location_id. The location_id is what the stub GHL
// keys its records on: alpha's answers must land ONLY on location-alpha and
// beta's ONLY on location-beta (T10 isolation proof).
// ---------------------------------------------------------------------------

function hex32(ch) {
  return ch.repeat(32);
}

export const CLIENTS = {
  alpha: {
    slug: 'fake-alpha',
    phaseId: 'P0-INTAKE',
    mode: 'full',
    token: hex32('a'),
    run_id: 'run_e2e_alpha',
    client_id: 'client_alpha_fake',
    location_id: 'loc_alpha_fake',
  },
  beta: {
    slug: 'fake-beta',
    phaseId: 'P0-INTAKE',
    mode: 'full',
    token: hex32('b'),
    run_id: 'run_e2e_beta',
    client_id: 'client_beta_fake',
    location_id: 'loc_beta_fake',
  },
  // A GATE-1-title client for the fast completion walk (T9) — its binding is
  // scoped to the GATE-1-title phase, so the universal link is not a misfit.
  gate1: {
    slug: 'fake-gate1',
    phaseId: 'GATE-1-title',
    mode: 'full',
    token: hex32('c'),
    run_id: 'run_e2e_gate1',
    client_id: 'client_gate1_fake',
    location_id: 'loc_gate1_fake',
  },
};

// exp unit: the codebase is internally inconsistent (lib.js validateTokenRow
// reads exp in MILLISECONDS; answers.js/save.js read it in SECONDS). A
// millisecond-epoch value in the far future satisfies every validator.
const FUTURE = Date.now() + 24 * 60 * 60 * 1000; // +24h (ms epoch, huge as seconds too)

function bindingFor(client) {
  return {
    client_id: client.client_id,
    location_id: client.location_id,
    slug: client.slug,
    phase_id: client.phaseId,
    run_id: client.run_id,
    exp: FUTURE,
    status: 'open',
    mode: client.mode,
    intake_id: `intake_${client.slug}_fake`,
  };
}

export const BINDINGS = {
  alpha: bindingFor(CLIENTS.alpha),
  beta: bindingFor(CLIENTS.beta),
  gate1: bindingFor(CLIENTS.gate1),
};

// The phase config the SPA should render for a client (mirrors the Worker:
// P0-INTAKE resolves to the mode-specific file).
export function configForPhase(client) {
  if (client.phaseId === 'P0-INTAKE') return CONFIG_P0_INTAKE;
  if (client.phaseId === 'GATE-1-title') return CONFIG_GATE_1;
  if (client.phaseId === 'GATE-2-outline') return CONFIG_GATE_2;
  return CONFIG_P0_INTAKE;
}

export function contextFor(client) {
  return {
    slug: client.slug,
    phase_id: client.phaseId,
    mode: client.mode,
    run_id: client.run_id,
    exp: FUTURE,
    phase_order: ['P0-INTAKE', 'GATE-1-title', 'GATE-2-outline', 'GATE-3-approval', 'GATE-4-approval-r2'],
    current_phase: client.phaseId,
  };
}
