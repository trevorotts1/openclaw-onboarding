#!/usr/bin/env node
// Behavioral checks for the Skill 58 n8n exports (standing-check EF3xsMuSQheZ98U6).
// Runs the exported Code-node source in-process; no network. Run from the repo root:
//   node 58-podcast-production-engine/scripts/tests/podcast-n8n-standing-fixes.test.js
const fs = require('fs'); const path = require('path'); const assert = require('assert');
const dir = path.join(__dirname, '..', '..', 'config', 'n8n');
function load(f) { const w = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')); return [w, Object.fromEntries(w.nodes.map(n => [n.name, n]))]; }
{ const [w, N] = load('podcast-standing-check.workflow.json');
const code = N['Code — Determine Standing Verdict'].parameters.jsCode;
const run = (body, rows) => new Function('$', '$input', code)(() => ({ first: () => ({ json: { body } }) }), { all: () => rows.map(r => ({ json: r })) })[0].json.responseBody;
const row = { last_name: 'Doe', email: 'a@b.co', podbean_channel_id: 'C1', good_standing: 'YES' };
assert.strictEqual(run({ client_last_name: 'doe', client_email: 'A@b.co', podcast_id: 'C1' }, [row]).good_standing, true);
assert.strictEqual(run({ client_last_name: 'Smith', client_email: 'a@b.co' }, [row]).reason, 'identity_unknown');
assert.strictEqual(run({ client_last_name: 'Doe', client_email: 'a@b.co' }, [{ ...row, good_standing: 'NO' }]).reason, 'not_in_good_standing');
const f = N['Roster Lookup — Good Standing + Identity'].parameters.filters.conditions;
assert.deepStrictEqual(f.map(c => c.keyName), ['email']);
console.log('selftest_standing: all checks passed');
}
