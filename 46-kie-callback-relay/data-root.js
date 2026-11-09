/**
 * data-root.js — Skill 46's ONLY source of durable job state paths (F21 item 11).
 *
 * The resolver itself is NOT implemented here. It lives in exactly one file,
 * `shared-utils/durable-data-root.sh`, which Skill 74's Python adapter also
 * executes. This module's whole job is to
 *   (a) locate that script (repo checkout or installed skills tree), and
 *   (b) run it once and hand back the layout it prints.
 *
 * WHY: Skill 46 used to compute `path.join(workspaceDir, '.kie', ...)` in TWO
 * files (the submitter and the poller), so the location of a paid job's
 * registry, index and done markers depended on whatever directory a caller
 * passed -- a presentation run folder, a skill tree, a temp dir. Nothing
 * survived a reinstall, and two modules could disagree about where one job
 * lived. There is now one computation, one answer, outside every replaceable
 * skill tree: `<root>/data/kie-jobs/<scope>/{registry,index,done,receipts}`.
 *
 * No secrets are read or printed: the resolver prints paths only.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const SCRIPT_NAME = 'durable-data-root.sh';
const DEFAULT_SCOPE = 'kie-callback-relay';

class DataRootError extends Error {
  constructor(detail, searched) {
    super(detail);
    this.name = 'DataRootError';
    this.searched = searched || [];
  }
}

/** Every place the shared resolver can live, most specific first. */
function candidatePaths(env) {
  const home = env.HOME || os.homedir();
  const out = [path.resolve(__dirname, '..', 'shared-utils', SCRIPT_NAME)];
  const skills = env.OPENCLAW_SKILLS_DIR;
  if (skills) out.push(path.join(skills, 'shared-utils', SCRIPT_NAME));
  out.push(path.join(home, '.openclaw', 'skills', 'shared-utils', SCRIPT_NAME));
  out.push('/data/.openclaw/skills/shared-utils/' + SCRIPT_NAME);
  return out;
}

function locateResolver(env) {
  const searched = candidatePaths(env);
  for (const candidate of searched) {
    try { if (fs.statSync(candidate).isFile()) return candidate; } catch (_) { /* next */ }
  }
  throw new DataRootError(
    '[kie-data-root] the shared durable data root resolver ' + SCRIPT_NAME +
    ' was not found; refusing to pick a location for paid-job state (a guessed ' +
    'path is how evidence lands in a transient folder)', searched);
}

// One process-wide cache: the layout for a (script, pin, scope, env-root) tuple
// never changes inside a process, and a deck submits many slides per run.
const _cache = new Map();

/**
 * Resolve the durable layout for one scope.
 *
 * @param {object} [opts]
 * @param {string} [opts.scope]     -- one path segment, e.g. the client slug
 * @param {string} [opts.dataRoot]  -- explicit root pin (operator/test); passed
 *                                    to the resolver, never interpreted here
 * @param {object} [opts.env]       -- environment (defaults to process.env)
 * @returns {{root,scope,state_dir,registry,index,done,receipts,cache,resolver}}
 */
function resolveDataRoot(opts = {}) {
  const env = opts.env || process.env;
  const scope = String(opts.scope || DEFAULT_SCOPE);
  const dataRoot = opts.dataRoot ? String(opts.dataRoot) : '';
  const resolver = locateResolver(env);

  const key = [resolver, scope, dataRoot, env.OPENCLAW_DATA_ROOT || '', env.HOME || '',
               env.OPENCLAW_ROOT || '', env.OC_ROOT || ''].join('\u0000');
  const hit = _cache.get(key);
  if (hit) return { ...hit };

  const childEnv = { ...env };
  if (dataRoot) childEnv.OPENCLAW_DATA_ROOT = dataRoot;

  let raw;
  try {
    raw = execFileSync('bash', [resolver, '--json', '--scope', scope], {
      env: childEnv, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (err) {
    const why = (err && (err.stderr || err.message)) ? String(err.stderr || err.message).trim() : String(err);
    throw new DataRootError(
      '[kie-data-root] the durable data root did not resolve (' + why + '); refusing to ' +
      'write paid-job state to a guessed path', [resolver]);
  }

  let layout;
  try { layout = JSON.parse(String(raw).trim()); } catch (_) {
    throw new DataRootError(
      '[kie-data-root] the resolver printed something other than one JSON layout: ' +
      String(raw).slice(0, 200), [resolver]);
  }
  for (const key of ['root', 'state_dir', 'registry', 'index', 'done', 'receipts']) {
    if (!layout || typeof layout[key] !== 'string' || !layout[key]) {
      throw new DataRootError(
        '[kie-data-root] the resolver layout is missing ' + key, [resolver]);
    }
  }
  layout.resolver = resolver;
  _cache.set(key, layout);
  return { ...layout };
}

/** Create the durable directories a caller is about to write into. */
function ensureDirs(layout, names = ['registry', 'index', 'done']) {
  for (const name of names) {
    if (layout[name]) fs.mkdirSync(layout[name], { recursive: true });
  }
  return layout;
}

module.exports = { resolveDataRoot, ensureDirs, locateResolver, DataRootError, SCRIPT_NAME };
