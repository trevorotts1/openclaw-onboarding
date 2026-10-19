// W11-U002 self-check over the recorded journey evidence.
// Reads only files in this directory; no runtime, no network, no DB.
// Fails (exit 1) if any recorded assertion does not hold.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const readJson = (p) => JSON.parse(readFileSync(join(here, p), 'utf8'));
const sha = (p) => createHash('sha256').update(readFileSync(join(here, p))).digest('hex');

const journey = readJson('journey.json');
const failures = [];
const check = (name, ok, detail = '') => {
  if (ok) console.log(`PASS ${name}${detail ? ` (${detail})` : ''}`);
  else failures.push(`${name}${detail ? ` (${detail})` : ''}`);
};

check('three rounds recorded', journey.rounds.length === 3, `rounds=${journey.rounds.length}`);
check(
  'each round completed with nine seats',
  journey.rounds.every((r) => r.state === 'COMPLETED' && r.seat_count === 9),
  journey.rounds.map((r) => `${r.session_id}:${r.seat_count}`).join(' '),
);
check(
  'each round executed card rounds 1,2,3 with nine seats each',
  journey.rounds.every(
    (r) =>
      r.card_rounds.length === 3 &&
      r.card_rounds.every((c) => c.round >= 1 && c.round <= 3 && c.c === 9 && c.seats === 9),
  ),
  journey.rounds.map((r) => r.card_rounds.map((c) => `r${c.round}=${c.c}`).join(',')).join(' | '),
);
check(
  'nine distinct advisor packs exercised',
  new Set(journey.rounds[0].seat_ids).size === 9 &&
    journey.rounds.every((r) => r.export_report.distinct_pack_versions === 9),
  `packs=${journey.rounds[0].seat_ids.length}`,
);
check(
  'exported reports reference nine seats',
  journey.rounds.every((r) => r.export_report.seat_count === 9),
);
for (const r of journey.rounds) {
  check(
    `round${r.round} md export hash matches artifact`,
    sha(`raw/exports/round${r.round}.md`) === r.export_hashes.md,
    r.export_hashes.md.slice(0, 16),
  );
  check(
    `round${r.round} json export hash matches artifact`,
    sha(`raw/exports/round${r.round}.json`) === r.export_hashes.json,
    r.export_hashes.json.slice(0, 16),
  );
  check(
    `round${r.round} repeated json export is byte-identical`,
    r.export_hashes.json === r.export_hashes.json_repeat,
  );
}
const stable = ['sessions', 'cards', 'verdicts', 'checkpoints'];
check(
  'replay delta is zero for sessions/cards/verdicts/checkpoints',
  stable.every((k) => journey.delta_replay.before[k] === journey.delta_replay.after[k]),
  JSON.stringify(
    Object.fromEntries(stable.map((k) => [k, journey.delta_replay.after[k] - journey.delta_replay.before[k]])),
  ),
);
check(
  'export delta is zero for sessions/cards/verdicts/checkpoints',
  stable.every((k) => journey.delta_export.before_replay[k] === journey.delta_export.after[k]),
  JSON.stringify(
    Object.fromEntries(
      stable.map((k) => [k, journey.delta_export.after[k] - journey.delta_export.before_replay[k]]),
    ),
  ),
);
check(
  'export adds only its journal event',
  journey.delta_export.after.events - journey.delta_export.before_replay.events === 1,
  `events+${journey.delta_export.after.events - journey.delta_export.before_replay.events}`,
);
check(
  'authorization store has zero delta across export',
  Object.values(journey.authorization_db_export_delta).every((v) => v === 0),
);
check(
  'duplicate create yields one session',
  journey.duplicate_create.duplicate_exit === 3 && journey.duplicate_create.sessions_after === 1,
);
check(
  'restart preserves every session id with no duplication',
  journey.restart.rounds.every((r) => r.outputs_identical && r.state === 'COMPLETED'),
  journey.restart.rounds.map((r) => r.session_id).join(','),
);
check(
  'cross-round isolation refusals recorded',
  journey.isolation.round2_sees_round1_status_exit === 3 &&
    journey.isolation.round2_sees_round1_pause_exit === 3 &&
    journey.isolation.round3_sees_round1_status_exit === 3,
);
check(
  'round 1 export is byte-identical before and after round 3',
  journey.isolation.round1_export_before_round3.md === journey.isolation.round1_export_after_round3.md &&
    journey.isolation.round1_export_before_round3.json === journey.isolation.round1_export_after_round3.json,
);
check(
  'failed/invalid rounds left no adopted verdict',
  journey.failed_rounds.refused_start_bad_grant.verdicts === 0 &&
    journey.failed_rounds.refused_start_bad_grant.session_state === 'DRAFT' &&
    journey.failed_rounds.killed_mid_start.verdicts === 0 &&
    journey.failed_rounds.invalid_create.sessions === 0,
);

if (failures.length) {
  console.error(`FAIL ${failures.length} assertion(s):`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
console.log('PASS all recorded journey assertions');
