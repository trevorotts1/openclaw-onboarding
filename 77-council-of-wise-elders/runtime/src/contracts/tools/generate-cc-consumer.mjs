/**
 * Generate the Command Center consumer artifact of the canonical contracts.
 *
 * Canonical home (single definition source, CWE-003 / decision D-006):
 *   openclaw-onboarding: 77-council-of-wise-elders/runtime/src/contracts/**
 *   openclaw-onboarding: 77-council-of-wise-elders/schemas/**
 *
 * Consumer artifact (generated, never hand-edited):
 *   blackceo-command-center: src/lib/council/contracts/**
 *
 * Usage:
 *   node generate-cc-consumer.mjs --target <cc contracts dir>
 * Optional overrides:
 *   --canonical <onb contracts dir>   (default: this script's parent dir)
 *   --schemas <onb schemas dir>       (default: <skill root>/schemas)
 *
 * The transform from canonical to consumer is deliberately tiny and total:
 * only home-specific path strings change. Every other byte is copied
 * verbatim. tools/verify-cc-parity.mjs recomputes this exact expected
 * output and compares it byte for byte against a consumer tree, so any
 * hand edit or drift in either home fails the parity check.
 */

import { createHash } from 'node:crypto';
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ONB_PREFIX = '77-council-of-wise-elders/runtime/src/contracts/';
const CC_PREFIX = 'src/lib/council/contracts/';
const ONB_ARTIFACT_REF = '../../../schemas/json-schemas.json';
const CC_ARTIFACT_REF = 'generated/json-schemas.json';

/** Files copied verbatim from the canonical contracts dir. */
export const VERBATIM_FILES = [
  'errors.ts',
  'enums.ts',
  'primitives.ts',
  'canonical-json.ts',
  'sha256.ts',
  'schemas.ts',
  'types.ts',
  'state-machine.ts',
  'scoring.ts',
  'diagnostic-retention.ts',
  'golden-vectors.ts',
  'index.ts',
  'fixtures/examples.ts',
];

/** Files copied with the home-path transform applied. */
export const TRANSFORMED_FILES = ['generate.ts', 'contracts.test.ts'];

export function toConsumerText(fileName, canonicalText) {
  let text = canonicalText.split(ONB_PREFIX).join(CC_PREFIX);
  if (fileName === 'generate.ts') {
    text = text.split(`'${ONB_ARTIFACT_REF}'`).join(`'${CC_ARTIFACT_REF}'`);
    text = text
      .split(`artifact at ${ONB_ARTIFACT_REF} (the skill-level schemas/ directory):`)
      .join(`artifact at ${CC_ARTIFACT_REF}:`);
  }
  return text;
}

function sha256Hex(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

/**
 * Compute the complete expected consumer tree as a Map of
 * relative path -> Buffer. Pure: reads canonical inputs, writes nothing.
 */
export function buildConsumerFiles(canonicalDir, schemasDir) {
  const files = new Map();
  for (const name of VERBATIM_FILES) {
    files.set(name, readFileSync(join(canonicalDir, name)));
  }
  for (const name of TRANSFORMED_FILES) {
    const text = readFileSync(join(canonicalDir, name), 'utf8');
    files.set(name, Buffer.from(toConsumerText(name, text), 'utf8'));
  }
  const readmeTemplate = readFileSync(
    join(canonicalDir, 'tools', 'cc-consumer-README.md'),
    'utf8',
  );
  files.set('README.md', Buffer.from(readmeTemplate, 'utf8'));

  const canonicalArtifact = readFileSync(join(schemasDir, 'json-schemas.json'), 'utf8');
  const consumerArtifact = canonicalArtifact
    .split(`${ONB_PREFIX}schemas.ts`)
    .join(`${CC_PREFIX}schemas.ts`);
  files.set('generated/json-schemas.json', Buffer.from(consumerArtifact, 'utf8'));

  const provenance = [
    '# GENERATED consumer artifact: do not hand-edit',
    '',
    'This tree is generated from the canonical Council of Wise Elders',
    'contracts (CWE-003, decision D-006):',
    '',
    `- Canonical source: openclaw-onboarding \`${ONB_PREFIX}\``,
    `- Canonical JSON Schema artifact: openclaw-onboarding \`77-council-of-wise-elders/schemas/json-schemas.json\``,
    `- Canonical artifact SHA-256: \`${sha256Hex(Buffer.from(canonicalArtifact, 'utf8'))}\``,
    '- Generator: `tools/generate-cc-consumer.mjs` in the canonical contracts folder.',
    '- Parity proof: `tools/verify-cc-parity.mjs` in the canonical contracts folder',
    '  recomputes this tree byte for byte and fails on any drift.',
    '',
    'To regenerate, run the generator from the canonical onboarding tree',
    'with --target pointing at this folder, then run this folder\'s own',
    'generate.ts and test suite (see README.md).',
    '',
  ].join('\n');
  files.set('GENERATED.md', Buffer.from(provenance, 'utf8'));
  return files;
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    if (!key.startsWith('--') || argv[i + 1] === undefined) {
      throw new Error(`bad argument near ${String(key)}`);
    }
    args[key.slice(2)] = argv[i + 1];
  }
  return args;
}

function main() {
  const here = dirname(fileURLToPath(import.meta.url));
  const canonicalDir = join(here, '..');
  const args = parseArgs(process.argv.slice(2));
  const canonical = args.canonical ?? canonicalDir;
  const schemas = args.schemas ?? join(canonical, '..', '..', '..', 'schemas');
  const target = args.target;
  if (!target) {
    throw new Error('--target <cc contracts dir> is required');
  }
  if (!target.replace(/\\/g, '/').endsWith('src/lib/council/contracts')) {
    throw new Error(`refusing to write outside a src/lib/council/contracts tree: ${target}`);
  }
  if (!existsSync(join(schemas, 'json-schemas.json'))) {
    throw new Error(`canonical artifact missing: ${join(schemas, 'json-schemas.json')} (run the canonical generate.ts first)`);
  }
  const files = buildConsumerFiles(canonical, schemas);
  for (const [rel, bytes] of files) {
    const dest = join(target, rel);
    mkdirSync(dirname(dest), { recursive: true });
    writeFileSync(dest, bytes);
    process.stdout.write(`wrote ${relative(process.cwd(), dest)}\n`);
  }
  process.stdout.write(`consumer artifact generated: ${files.size} files\n`);
}

const invokedDirectly =
  process.argv[1] !== undefined &&
  fileURLToPath(import.meta.url) === process.argv[1];
if (invokedDirectly) main();

export { statSync, readdirSync };
