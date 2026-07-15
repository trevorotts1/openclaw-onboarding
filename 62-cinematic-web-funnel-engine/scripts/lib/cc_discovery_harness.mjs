// cc_discovery_harness.mjs — U23 Command Center ZERO-CHANGE discovery proof.
//
// Ships INSIDE this skill (openclaw-onboarding), never copied into or
// committed against blackceo-command-center. It imports that repo's own
// `matchSkillsForTask()` / `renderMatchedSkillsSection()` / `buildContextPack()`
// / `renderContextPackSection()` (src/lib/context-pack.ts) BY ABSOLUTE PATH from
// an operator-supplied checkout (env CC_REPO_PATH) — a pure read: this file
// never writes anything under CC_REPO_PATH.
//
// Proves (spec 21.2 / checklist item 24 / ledger U23): the existing generic
// Command Center skill matcher discovers and ranks this engine's REAL,
// unmodified, shipped SKILL.md — using only env-var overrides
// (CC_SKILL_ROOTS / CC_SKILL_DEPARTMENT_MAP), with NO Command Center code
// change of any kind.
//
// Invoked by scripts/prove_command_center_discovery.py, which prepares the
// three required env vars below and captures this script's single-line JSON
// stdout as the evidence record.
//
// Required environment variables (all set by the Python caller):
//   CC_REPO_PATH        absolute path to a blackceo-command-center checkout
//   FIXTURE_SKILL_ROOT   dir containing copies of REAL SKILL.md files (built
//                        by the Python caller from THIS onboarding repo)
//   FIXTURE_DEPT_MAP     path to a copy of the REAL skill-department-map.json
//   DATABASE_PATH        pre-set by the caller to an isolated temp sqlite path
//                        (context-pack.ts transitively imports '@/lib/db',
//                        whose C8 guard refuses to resolve a live db path
//                        outside the real CC server process — mirrors the
//                        '_isolated-db.ts' pattern CC's own test suite uses)
//
// Exit 0 + JSON {"overall":"PASS",...} on success. Exit 1 + JSON with the
// first failing check on a genuine mismatch. Exit 3 on a usage/setup error
// (missing env, module shape drift) — never a bare crash with no evidence.

import path from 'node:path';
import fs from 'node:fs';

const CC_REPO = process.env.CC_REPO_PATH;
const FIXTURE_ROOT = process.env.FIXTURE_SKILL_ROOT;
const DEPT_MAP = process.env.FIXTURE_DEPT_MAP;

function usageError(msg) {
  console.log(JSON.stringify({ overall: 'USAGE_ERROR', detail: msg }));
  process.exit(3);
}

if (!CC_REPO || !FIXTURE_ROOT || !DEPT_MAP) {
  usageError('missing one of CC_REPO_PATH / FIXTURE_SKILL_ROOT / FIXTURE_DEPT_MAP');
}
if (!process.env.DATABASE_PATH) {
  usageError('DATABASE_PATH must be pre-set to an isolated temp path (see file header)');
}

process.env.CC_SKILL_ROOTS = FIXTURE_ROOT;
process.env.CC_SKILL_DEPARTMENT_MAP = DEPT_MAP;
// Zero-config keyword path only — deterministic, no network, matches how the
// engine's own client-box runtime never assumes an embedding key is present.
delete process.env.OPENAI_API_KEY;
delete process.env.GOOGLE_API_KEY;
delete process.env.GOOGLE_AI_STUDIO_API_KEY;
delete process.env.GEMINI_API_KEY;
delete process.env.SOP_EMBEDDING_PROVIDER;

const modPath = path.join(CC_REPO, 'src', 'lib', 'context-pack.ts');
if (!fs.existsSync(modPath)) {
  usageError(`CC_REPO_PATH does not contain src/lib/context-pack.ts: ${modPath}`);
}

let mod;
try {
  mod = await import(path.resolve(modPath));
} catch (err) {
  usageError(`failed to import context-pack.ts: ${err && err.message ? err.message : String(err)}`);
}

const { matchSkillsForTask, renderMatchedSkillsSection, buildContextPack, renderContextPackSection } = mod;
if (typeof matchSkillsForTask !== 'function' || typeof renderMatchedSkillsSection !== 'function' ||
    typeof buildContextPack !== 'function' || typeof renderContextPackSection !== 'function') {
  usageError('context-pack.ts no longer exports the four expected symbols (module shape drift) — re-verify spec 21.2 against the live CC repo before trusting this proof');
}

const SKILL_NAME = 'cinematic-web-funnel-engine';
const results = { checks: [] };
function record(name, pass, detail) {
  results.checks.push({ name, pass, detail });
}

// ---------------------------------------------------------------------------
// 1. Every real, registered spec-3.4 / skill-department-map.json intent
//    trigger for this skill, dept-scoped to its real owning department
//    (web-development), must surface it.
// ---------------------------------------------------------------------------
const triggers = [
  'build me an animated website',
  'create a cinematic landing page',
  'make a scroll animation website',
  'build an immersive funnel',
  'create a cinematic squeeze page',
  'make my website move as I scroll',
  'build a premium interactive sales page',
  'turn this brand story into a scroll experience',
  'create a Vercel-hosted funnel connected to GoHighLevel',
  'build a cinematic website with complete copy',
];

let hitCount = 0;
for (const trig of triggers) {
  const matches = await matchSkillsForTask({ title: trig, description: trig, department: 'web-development' });
  const names = matches.map((m) => m.name);
  const hit = names.includes(SKILL_NAME);
  if (hit) hitCount++;
  record(`trigger:"${trig}"`, hit, `names=[${names.join(', ')}]`);
}
record('all-registered-triggers-hit', hitCount === triggers.length, `${hitCount}/${triggers.length}`);

// ---------------------------------------------------------------------------
// 2. A genuinely keyword-disjoint task (shares no vocabulary with any fixture
//    skill's name/description) must NOT surface this skill — proves the
//    matcher is discriminating, not "return everything".
// ---------------------------------------------------------------------------
const disjoint = await matchSkillsForTask({
  title: 'order office supplies for the team',
  description: 'restock printer paper and coffee for the break room',
  department: 'web-development',
});
record('keyword-disjoint-task-returns-no-match', disjoint.length === 0, `names=[${disjoint.map((m) => m.name).join(', ')}]`);

// ---------------------------------------------------------------------------
// 3. Full round trip on the strongest positive: real on-disk path, resolvable,
//    "SKILLS AVAILABLE FOR THIS TASK" render, and both the auto-dispatch
//    (buildContextPack/renderContextPackSection) and manual-dispatch
//    (renderMatchedSkillsSection direct) paths carry it through.
// ---------------------------------------------------------------------------
const primary = await matchSkillsForTask({
  title: 'build me an animated website',
  description: 'create a cinematic landing page with scroll-controlled scenes',
  department: 'web-development',
});
const skill62 = primary.find((m) => m.name === SKILL_NAME);
record('skill-in-top-n', Boolean(skill62), `top-N=[${primary.map((m) => m.name).join(', ')}]`);

if (skill62) {
  record('location-is-skillmd', skill62.location.endsWith('SKILL.md'), skill62.location);
  record('location-resolvable-on-disk', skill62.resolvable === true, String(skill62.resolvable));
  record('location-under-fixture-root', skill62.location.startsWith(FIXTURE_ROOT), skill62.location);
  record('match-kind-is-keyword-zero-config', skill62.matchKind === 'keyword', skill62.matchKind);
  record('score-positive', skill62.score > 0, String(skill62.score));

  const manualBlock = renderMatchedSkillsSection(primary);
  record('manual-dispatch-block-header', /SKILLS AVAILABLE FOR THIS TASK/.test(manualBlock), '');
  record('manual-dispatch-block-has-name', manualBlock.includes(SKILL_NAME), '');
  record('manual-dispatch-block-has-path', manualBlock.includes(skill62.location), '');

  const pack = buildContextPack({
    task: { id: 't-u23-proof', title: 'build me an animated website', description: 'x', department: 'web-development', workspace_id: null },
    agent: { id: 'a-u23-proof', name: 'Funnel Builder', role: 'web-development' },
    specialistType: 'permanent',
    matchedSkills: primary,
  });
  record('auto-dispatch-pack-carries-skill', pack.matched_skills.some((m) => m.name === SKILL_NAME), '');
  const autoSection = renderContextPackSection(pack);
  record('auto-dispatch-render-has-block', /SKILLS AVAILABLE FOR THIS TASK/.test(autoSection), '');
} else {
  record('location-is-skillmd', false, 'SKIPPED — skill not in top-N, see skill-in-top-n');
  record('location-resolvable-on-disk', false, 'SKIPPED');
  record('location-under-fixture-root', false, 'SKIPPED');
  record('match-kind-is-keyword-zero-config', false, 'SKIPPED');
  record('score-positive', false, 'SKIPPED');
  record('manual-dispatch-block-header', false, 'SKIPPED');
  record('manual-dispatch-block-has-name', false, 'SKIPPED');
  record('manual-dispatch-block-has-path', false, 'SKIPPED');
  record('auto-dispatch-pack-carries-skill', false, 'SKIPPED');
  record('auto-dispatch-render-has-block', false, 'SKIPPED');
}

// ---------------------------------------------------------------------------
// Non-gating observations — real, reproducible behavior worth recording, but
// NOT specific to this skill's registration and therefore not asserted
// pass/fail here (spec 21.2/25.14: no bespoke CC change merely to special-
// case one skill; a systemic gap affecting the whole 30-skill catalog is a
// separately-justified, separately-scoped, generic Command Center decision).
// ---------------------------------------------------------------------------
const observations = [];

const crossDept = await matchSkillsForTask({
  title: 'build me an animated website',
  description: 'build me an animated website',
  department: 'crm',
});
const crossHit = crossDept.find((m) => m.name === SKILL_NAME);
observations.push({
  name: 'dept-scope-on-real-map-shape',
  detail:
    `department='crm' (not this skill's owning department) still returns ` +
    `departments=${JSON.stringify(crossHit ? crossHit.departments : null)} for a cinematic-worded task. ` +
    `The real skill-department-map.json ships "skills" as an ARRAY of skill-record objects; ` +
    `context-pack.ts loadSkillDeptMap() only recognizes a dept->skills object, a skill->depts ` +
    `object, or a bare skill->depts object — none of which match the array shape — so it returns ` +
    `null and every skill (all ~30 client-facing entries, not just this one) is currently treated ` +
    `as globally scoped rather than department-scoped. Pre-existing, catalog-wide, NOT introduced ` +
    `by this registration. Out of scope for a single skill's build unit.`,
});

const videoAdjacent = await matchSkillsForTask({
  title: 'burn captions into this video',
  description: 'add subtitles and export an SRT for this clip',
  department: 'video',
});
observations.push({
  name: 'zero-config-keyword-breadth',
  detail:
    `names=[${videoAdjacent.map((m) => m.name).join(', ')}] for a captions/subtitles task. The ` +
    `zero-config keyword-overlap fallback (no client embedding key configured) scores on raw ` +
    `substring overlap, so any two genuinely video-related skills can co-match a video-adjacent ` +
    `task. Expected, pre-existing behavior of the fallback path shared by every installed skill, ` +
    `not a defect introduced by this registration.`,
});

results.observations = observations;

const allPass = results.checks.every((c) => c.pass);
results.overall = allPass ? 'PASS' : 'FAIL';
results.skill_name = SKILL_NAME;
results.generated_at = new Date().toISOString();
console.log(JSON.stringify(results));
process.exit(allPass ? 0 : 1);
