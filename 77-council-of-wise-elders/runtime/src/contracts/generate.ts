/**
 * JSON Schema generation for the canonical contracts (CWE-003 build step 3).
 *
 * The JSON Schema artifacts are generated from the exact zod definitions in
 * schemas.ts, so generated schemas and generated TypeScript types (types.ts)
 * share one canonical source. Run as a script to (re)write the committed
 * artifact at ../../../schemas/json-schemas.json (the skill-level schemas/ directory):
 *
 *   node --import tsx 77-council-of-wise-elders/runtime/src/contracts/generate.ts
 *
 * The drift test regenerates the artifact in memory and compares it to the
 * committed file byte for byte; a mismatch fails the suite.
 */

import { z } from 'zod';
import {
  actionProposalSchema,
  advisorCardAuthorSchema,
  advisorCardSchema,
  amendmentSchema,
  approvalRecordSchema,
  cardAuthorSchema,
  cardSchema,
  conditionSchema,
  consultCardAuthorSchema,
  consultCardSchema,
  councilEventSchema,
  councilSettingsSchema,
  criticalDomainRequirementSchema,
  decisionBriefSchema,
  diagnosticRetentionPolicySchema,
  draftResolutionSchema,
  endpointContractSchema,
  jobCheckpointSchema,
  operationReceiptSchema,
  ratificationCardAuthorSchema,
  ratificationCardSchema,
  runGrantSchema,
  runPreviewSchema,
  sessionSpecSchema,
  sessionStateRecordSchema,
  verdictSchema,
  CONTRACT_PACKAGE_VERSION,
} from './schemas.js';
import { canonicalStringify } from './canonical-json.js';

export const JSON_SCHEMA_ARTIFACT_PATH = '../../../schemas/json-schemas.json';

const SCHEMA_REGISTRY: Record<string, z.ZodType> = {
  SessionSpec: sessionSpecSchema,
  DecisionBrief: decisionBriefSchema,
  CriticalDomainRequirement: criticalDomainRequirementSchema,
  AdvisorCardAuthor: advisorCardAuthorSchema,
  RatificationCardAuthor: ratificationCardAuthorSchema,
  ConsultCardAuthor: consultCardAuthorSchema,
  CardAuthor: cardAuthorSchema,
  AdvisorCard: advisorCardSchema,
  RatificationCard: ratificationCardSchema,
  ConsultCard: consultCardSchema,
  CouncilCard: cardSchema,
  Condition: conditionSchema,
  ActionProposal: actionProposalSchema,
  Amendment: amendmentSchema,
  DraftResolution: draftResolutionSchema,
  Verdict: verdictSchema,
  SessionStateRecord: sessionStateRecordSchema,
  JobCheckpoint: jobCheckpointSchema,
  RunPreview: runPreviewSchema,
  RunGrant: runGrantSchema,
  ApprovalRecord: approvalRecordSchema,
  CouncilEvent: councilEventSchema,
  CouncilSettings: councilSettingsSchema,
  OperationReceipt: operationReceiptSchema,
  DiagnosticRetentionPolicy: diagnosticRetentionPolicySchema,
  EndpointContract: endpointContractSchema,
};

const CARD_AUTHOR_SCHEMAS = {
  advisor: advisorCardAuthorSchema,
  ratification: ratificationCardAuthorSchema,
  consult: consultCardAuthorSchema,
} as const;

export type CardAuthorKind = keyof typeof CARD_AUTHOR_SCHEMAS;

/**
 * The canonical card contract for one card kind, as a JSON Schema
 * generated from the exact zod author definition the validator
 * enforces (RP-046-3, DEFECT-046-B Cause 2). A composed provider
 * request carries this schema so the model is told the precise shape,
 * including the closed card_kind discriminator, instead of being
 * asked to guess it. Generated per call from the same definitions as
 * the committed artifact above; the artifact registry is untouched,
 * so the committed artifact bytes do not change.
 */
export function cardAuthorJsonSchema(kind: CardAuthorKind): unknown {
  return z.toJSONSchema(CARD_AUTHOR_SCHEMAS[kind], {
    target: 'draft-2020-12',
    unrepresentable: 'throw',
  });
}

/** Generate the full JSON Schema artifact text (deterministic byte output). */
export function generateJsonSchemaArtifact(): string {
  const schemas: Record<string, unknown> = {};
  for (const name of Object.keys(SCHEMA_REGISTRY).sort()) {
    schemas[name] = z.toJSONSchema(SCHEMA_REGISTRY[name], {
      target: 'draft-2020-12',
      unrepresentable: 'throw',
    });
  }
  const artifact = {
    artifact: 'wise-elders.contracts.json-schema',
    package_version: CONTRACT_PACKAGE_VERSION,
    generated_from: '77-council-of-wise-elders/runtime/src/contracts/schemas.ts',
    schemas,
  };
  return `${canonicalStringify(artifact)}\n`;
}

// Script entry: write the committed artifact when run directly.
const invokedDirectly =
  typeof process !== 'undefined' &&
  Array.isArray(process.argv) &&
  process.argv[1] !== undefined &&
  process.argv[1].endsWith('generate.ts');

if (invokedDirectly) {
  void (async () => {
    const { writeFile, mkdir } = await import('node:fs/promises');
    const { dirname, join } = await import('node:path');
    const { fileURLToPath } = await import('node:url');
    const here = dirname(fileURLToPath(import.meta.url));
    const target = join(here, JSON_SCHEMA_ARTIFACT_PATH);
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, generateJsonSchemaArtifact(), 'utf8');
    process.stdout.write(`wrote ${target}\n`);
  })();
}
