// Fails when the committed ui/questions.json drifts from a fresh export of
// intake_card.py --format studio-json (the only place questions are defined).
// Usage: node questions-drift.mjs   (QUESTIONS_FILE=path to check another copy)
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const skillRoot = resolve(here, '..', '..', '..'); // ui/checks -> 75-drama-song-ad-factory
const intakeCard = join(skillRoot, 'scripts', 'core', 'choice_card', 'intake_card', 'intake_card.py');
const committedPath = process.env.QUESTIONS_FILE || join(skillRoot, 'mini-app', 'ui', 'questions.json');

let freshText;
try {
  freshText = execFileSync('python3', [intakeCard, '--format', 'studio-json'], { encoding: 'utf8' });
} catch (err) {
  console.error(`questions-drift: export failed: ${String(err.message).split('\n')[0]}`);
  process.exit(2);
}

if (!existsSync(committedPath)) {
  console.log(`questions-drift: DRIFT missing committed file ${committedPath}`);
  process.exit(1);
}

let fresh;
let committed;
try {
  fresh = JSON.parse(freshText);
  committed = JSON.parse(readFileSync(committedPath, 'utf8'));
} catch (err) {
  console.log(`questions-drift: DRIFT not valid JSON: ${String(err.message).split('\n')[0]}`);
  process.exit(1);
}

if (JSON.stringify(fresh) === JSON.stringify(committed)) {
  console.log(`questions-drift: OK ${committedPath} matches a fresh export (${fresh.question_count} questions)`);
  process.exit(0);
}

const cut = (v) => {
  const s = JSON.stringify(v);
  return s === undefined ? 'undefined' : s.length > 140 ? `${s.slice(0, 137)}...` : s;
};

function why(a, b) {
  const ka = Object.keys(a || {});
  const kb = Object.keys(b || {});
  if (ka.join(',') !== kb.join(',')) return `top-level keys fresh=[${ka}] committed=[${kb}]`;
  for (const k of ka) {
    if (k === 'questions') continue;
    if (a[k] !== b[k]) return `${k}: fresh=${cut(a[k])} committed=${cut(b[k])}`;
  }
  const qa = a.questions || [];
  const qb = b.questions || [];
  for (let i = 0; i < Math.max(qa.length, qb.length); i += 1) {
    const x = qa[i];
    const y = qb[i];
    if (JSON.stringify(x) === JSON.stringify(y)) continue;
    if (!x || !y) return `question[${i}]: fresh=${x ? x.id : 'missing'} committed=${y ? y.id : 'missing'}`;
    const fields = [...new Set([...Object.keys(x), ...Object.keys(y)])];
    for (const f of fields) {
      if (JSON.stringify(x[f]) !== JSON.stringify(y[f])) {
        return `question[${i}].${f} (${x.id}): fresh=${cut(x[f])} committed=${cut(y[f])}`;
      }
    }
  }
  return 'content differs';
}

console.log(`questions-drift: DRIFT ${why(fresh, committed)}`);
process.exit(1);
