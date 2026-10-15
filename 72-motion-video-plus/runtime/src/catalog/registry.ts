// The component registry (Directive MG-018, Sections 7, 16.1).
//
// The registry is the catalog the shipped validators and the future
// orchestrator consult before any adapter or render work:
// - validateSceneProps classifies a scene document early: unknown ids
//   fail MG_UNKNOWN_COMPONENT, known ids with invalid props fail
//   MG_SCHEMA_INVALID, schema-valid scenes with impossible motion
//   intervals fail MG_TIMELINE_INVALID, and registered-but-unavailable
//   components fail MG_CAPABILITY_UNSUPPORTED. No silent substitution
//   ever happens: an unavailable component is refused, never replaced.
// - requireDispatchable is the dispatch gate with the same categories.
// - register implements the governed custom-component path: a new
//   component is accepted only with its closed input schema, proof
//   contract, and tests present in the same call, plus an engineering
//   review attestation (Section 16.1). Partial registrations are refused.
//
// Verdict parity note: for C05 the catalog defers to the canonical
// contracts scene schema (derived, not copied), and the unknown-id
// classification replicates the shipped MG-007 rule exactly, so catalog
// verdicts match the shipped TypeScript and Python validators on every
// case except one deliberate divergence: a component the catalog knows
// by identity but cannot yet dispatch (C10-C12; C04 and C09 became
// dispatchable with MG-017, C06-C08 with MG-016, and C01-C03 with
// MG-044, each through its own registered schema) is rejected by
// the shipped validators as MG_UNKNOWN_COMPONENT (they have not
// registered it at all) and by the catalog as
// MG_CAPABILITY_UNSUPPORTED. The accept/reject verdict is identical;
// only the category differs, for the reason recorded in errors.ts.

import Ajv2020, { type ValidateFunction } from "ajv/dist/2020";
import {
  loadContractsSchema,
  validateAgainstDef,
} from "../validation/validate";
import { c01Entry } from "./c01";
import { c02Entry } from "./c02";
import { c03Entry } from "./c03";
import { c04Entry } from "./c04";
import { c05Entry } from "./c05";
import { c06Entry } from "./c06";
import { c07Entry } from "./c07";
import { c08Entry } from "./c08";
import { c09Entry } from "./c09";
import { pendingEntries } from "./pending";
import { validateCatalogEntry } from "./entry-schema";
import {
  CatalogError,
  firstCatalogCategory,
  type CatalogErrorCategory,
  type CatalogFinding,
} from "./errors";
import type {
  ComponentEntry,
  LayoutDescriptor,
  RegistrationBundle,
} from "./types";

const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/;

/** Const-mismatch instance paths the shipped dispatch rule tolerates. */
const COMPONENT_CONST_PATHS = new Set([
  "/component_id",
  "/component_version",
  "/motion/kind",
]);

/** The official Section 7.1 component ids. */
export const OFFICIAL_COMPONENT_IDS: string[] = [
  "C01",
  "C02",
  "C03",
  "C04",
  "C05",
  "C06",
  "C07",
  "C08",
  "C09",
  "C10",
  "C11",
  "C12",
];

export interface ScenePropsValidation {
  valid: boolean;
  /** The entry the document dispatches to; null when none applies. */
  entry: ComponentEntry | null;
  findings: CatalogFinding[];
  firstErrorCategory: CatalogErrorCategory | null;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function schemaFindings(
  errors: { instancePath: string; message?: string }[]
): CatalogFinding[] {
  return errors.map((error) => ({
    category: "MG_SCHEMA_INVALID" as const,
    path: error.instancePath,
    message: error.message ?? "schema violation",
  }));
}

export class ComponentRegistry {
  private readonly entriesByKey = new Map<string, ComponentEntry>();
  private readonly validators = new Map<string, ValidateFunction>();

  constructor(entries: ComponentEntry[] = []) {
    for (const entry of entries) {
      this.addEntry(entry);
    }
  }

  /** The production registry: the available components (C04 and C09
   * through MG-017, C05 through MG-006/MG-018, C06-C08 through MG-016,
   * C01-C03 through MG-044) plus the remaining Section 7.1 identities
   * registered with explicit unavailable states. */
  static createDefault(): ComponentRegistry {
    return new ComponentRegistry([c01Entry(), c02Entry(), c03Entry(), c04Entry(), c05Entry(), c06Entry(), c07Entry(), c08Entry(), c09Entry(), ...pendingEntries()]);
  }

  private key(componentId: string, version: string): string {
    return `${componentId}@${version}`;
  }

  private addEntry(entry: ComponentEntry): void {
    const problems = validateCatalogEntry(entry);
    if (problems.length > 0) {
      throw new CatalogError(
        "MG_SCHEMA_INVALID",
        `Catalog entry ${entry.componentId} ${entry.version} is malformed: ${problems.join("; ")}`,
        problems.map((message) => ({
          category: "MG_SCHEMA_INVALID" as const,
          path: "",
          message,
        }))
      );
    }
    const key = this.key(entry.componentId, entry.version);
    if (this.entriesByKey.has(key)) {
      throw new CatalogError(
        "MG_SCHEMA_INVALID",
        `Duplicate catalog entry ${key}.`
      );
    }
    this.entriesByKey.set(key, entry);
  }

  /** All registered entries, sorted by component id then version. */
  list(): ComponentEntry[] {
    return [...this.entriesByKey.values()].sort((a, b) =>
      a.componentId === b.componentId
        ? a.version.localeCompare(b.version)
        : a.componentId.localeCompare(b.componentId)
    );
  }

  get(componentId: string, version: string): ComponentEntry | null {
    return this.entriesByKey.get(this.key(componentId, version)) ?? null;
  }

  versionsOf(componentId: string): ComponentEntry[] {
    return this.list().filter((entry) => entry.componentId === componentId);
  }

  /** Compile (once) the Ajv validator for one entry's closed input schema,
   * with the canonical contracts $defs attached so schemas may reference
   * shared definitions exactly as the shipped validators compile them. */
  private validatorFor(entry: ComponentEntry): ValidateFunction {
    const key = this.key(entry.componentId, entry.version);
    const cached = this.validators.get(key);
    if (cached) {
      return cached;
    }
    if (entry.inputSchema === null) {
      throw new CatalogError(
        "MG_CAPABILITY_UNSUPPORTED",
        `Component ${entry.componentId} ${entry.version} has no registered input schema.`
      );
    }
    const contracts = loadContractsSchema() as unknown as {
      $defs: Record<string, unknown>;
    };
    const { $defs: ownDefs, ...rest } = entry.inputSchema as {
      $defs?: Record<string, unknown>;
    } & Record<string, unknown>;
    const wrapped = {
      $schema: "https://json-schema.org/draft/2020-12/schema",
      ...rest,
      $defs: { ...contracts.$defs, ...(ownDefs ?? {}) },
    };
    const ajv = new Ajv2020({ allErrors: true, strict: false });
    const validate = ajv.compile(wrapped);
    this.validators.set(key, validate);
    return validate;
  }

  private validateAgainstEntry(
    entry: ComponentEntry,
    doc: Record<string, unknown>
  ): CatalogFinding[] {
    const validate = this.validatorFor(entry);
    if (validate(doc)) {
      return [];
    }
    return schemaFindings(validate.errors ?? []);
  }

  /** The intra-scene timeline rule the shipped validators enforce
   * (Section 16.6): start < end <= hold <= duration_frames. Applied only
   * to documents carrying the canonical motion fields. */
  private timelineFindings(doc: Record<string, unknown>): CatalogFinding[] {
    const findings: CatalogFinding[] = [];
    const motion = doc.motion;
    const duration = doc.duration_frames;
    if (!isPlainObject(motion) || typeof duration !== "number") {
      return findings;
    }
    const start = motion.start_frame;
    const end = motion.end_frame_exclusive;
    const hold = motion.hold_to_frame_exclusive;
    if (
      typeof start !== "number" ||
      typeof end !== "number" ||
      typeof hold !== "number"
    ) {
      return findings;
    }
    if (!(start < end)) {
      findings.push({
        category: "MG_TIMELINE_INVALID",
        path: "/motion",
        message:
          "Motion start_frame must be before end_frame_exclusive within the scene.",
      });
    }
    if (!(end <= hold)) {
      findings.push({
        category: "MG_TIMELINE_INVALID",
        path: "/motion",
        message: "Motion end exceeds the scene hold end.",
      });
    }
    if (!(hold <= duration)) {
      findings.push({
        category: "MG_TIMELINE_INVALID",
        path: "/motion",
        message: "Motion hold exceeds scene duration.",
      });
    }
    return findings;
  }

  private finish(
    entry: ComponentEntry | null,
    findings: CatalogFinding[]
  ): ScenePropsValidation {
    return {
      valid: findings.length === 0,
      entry,
      findings,
      firstErrorCategory: firstCatalogCategory(findings),
    };
  }

  /**
   * Classify a scene document against the catalog. Runs before any
   * adapter or render work and never substitutes components.
   */
  validateSceneProps(doc: unknown): ScenePropsValidation {
    if (!isPlainObject(doc)) {
      return this.finish(null, [
        {
          category: "MG_SCHEMA_INVALID",
          path: "",
          message: "Scene document must be a JSON object.",
        },
      ]);
    }
    const componentId = doc.component_id;
    const componentVersion = doc.component_version;

    // The id itself is unusable: the contracts schema layer owns the
    // detailed shape errors, mirroring the shipped validators.
    if (typeof componentId !== "string" || !ID_PATTERN.test(componentId)) {
      const errors = validateAgainstDef("scene", doc);
      const findings =
        errors.length > 0
          ? schemaFindings(errors)
          : [
              {
                category: "MG_SCHEMA_INVALID" as const,
                path: "/component_id",
                message: "Scene component_id is missing or malformed.",
              },
            ];
      return this.finish(null, findings);
    }

    const versions = this.versionsOf(componentId);

    // Unknown id: replicate the shipped dispatch rule exactly. When the
    // document's only canonical-scene errors are const mismatches at the
    // dispatch paths, the id names no registered component; anything
    // else is a plain schema failure.
    if (versions.length === 0) {
      const errors = validateAgainstDef("scene", doc);
      const onlyDispatchConsts =
        errors.length > 0 &&
        errors.every(
          (error) =>
            error.keyword === "const" &&
            COMPONENT_CONST_PATHS.has(error.instancePath)
        );
      if (onlyDispatchConsts || errors.length === 0) {
        return this.finish(null, [
          {
            category: "MG_UNKNOWN_COMPONENT",
            path: "/component_id",
            message: `Unknown component ${componentId} ${String(componentVersion)}.`,
          },
        ]);
      }
      return this.finish(null, schemaFindings(errors));
    }

    const exact =
      typeof componentVersion === "string"
        ? this.get(componentId, componentVersion)
        : null;

    // Known id, unregistered version.
    if (exact === null) {
      const available = versions.find(
        (entry) => entry.availability === "available"
      );
      if (!available) {
        return this.finish(null, [
          {
            category: "MG_CAPABILITY_UNSUPPORTED",
            path: "/component_id",
            message:
              `Component ${componentId} is registered in the catalog but no ` +
              `version is available for production dispatch. ` +
              `${versions[0].unavailableReason ?? ""}`,
          },
        ]);
      }
      // Mirror the shipped rule: a known component with a wrong version
      // is a schema failure, surfaced by validating against the
      // registered version's closed schema.
      return this.finish(
        available,
        this.validateAgainstEntry(available, doc)
      );
    }

    // Known id and version, but the production bundle has not landed.
    if (exact.availability === "unavailable") {
      return this.finish(exact, [
        {
          category: "MG_CAPABILITY_UNSUPPORTED",
          path: "/component_id",
          message:
            `Component ${componentId} ${exact.version} is registered but ` +
            `unavailable for production dispatch. ${exact.unavailableReason ?? ""}`,
        },
      ]);
    }

    // Available component: closed-schema validation, then the timeline
    // rule, both before any adapter or render work.
    const findings = this.validateAgainstEntry(exact, doc);
    if (findings.length === 0) {
      findings.push(...this.timelineFindings(doc));
    }
    return this.finish(exact, findings);
  }

  /** Throwing form of validateSceneProps: returns the dispatch entry. */
  assertSceneProps(doc: unknown): ComponentEntry {
    const result = this.validateSceneProps(doc);
    if (!result.valid || result.entry === null) {
      const category = result.firstErrorCategory ?? "MG_SCHEMA_INVALID";
      throw new CatalogError(
        category,
        result.findings[0]?.message ?? "Scene props failed catalog validation.",
        result.findings
      );
    }
    return result.entry;
  }

  /**
   * The dispatch gate: resolve a component for production or throw a
   * structured CatalogError. Unavailable components are refused with
   * MG_CAPABILITY_UNSUPPORTED; nothing is ever substituted.
   */
  requireDispatchable(
    componentId: string,
    componentVersion: string
  ): ComponentEntry {
    const versions = this.versionsOf(componentId);
    if (versions.length === 0) {
      throw new CatalogError(
        "MG_UNKNOWN_COMPONENT",
        `Unknown component ${componentId} ${componentVersion}.`
      );
    }
    const exact = this.get(componentId, componentVersion);
    if (exact !== null) {
      if (exact.availability === "unavailable") {
        throw new CatalogError(
          "MG_CAPABILITY_UNSUPPORTED",
          `Component ${componentId} ${componentVersion} is registered but unavailable for production dispatch. ${exact.unavailableReason ?? ""}`
        );
      }
      return exact;
    }
    const available = versions.find(
      (entry) => entry.availability === "available"
    );
    if (available) {
      throw new CatalogError(
        "MG_SCHEMA_INVALID",
        `Component ${componentId} has no registered version ${componentVersion}; registered available version: ${available.version}.`
      );
    }
    throw new CatalogError(
      "MG_CAPABILITY_UNSUPPORTED",
      `Component ${componentId} is registered but no version is available for production dispatch. ${versions[0].unavailableReason ?? ""}`
    );
  }

  /**
   * The governed custom-component path (Section 16.1): implement,
   * validate, review, and register before reuse. The call itself takes
   * the entry (carrying its closed input schema, proof contract, and
   * tests) plus the engineering review attestation, and refuses any
   * incomplete registration with MG_SCHEMA_INVALID.
   */
  register(bundle: RegistrationBundle): ComponentEntry {
    const problems: string[] = [];
    if (!isPlainObject(bundle)) {
      throw new CatalogError(
        "MG_SCHEMA_INVALID",
        "Registration bundle must be an object carrying entry and reviewAttestation."
      );
    }
    const entry = bundle.entry;
    if (!isPlainObject(entry)) {
      problems.push(
        "bundle.entry is required: the component entry carrying its schema, proof contract, and tests"
      );
    } else {
      problems.push(...validateCatalogEntry(entry));
      if (entry.availability !== "available") {
        problems.push(
          "a custom registration must register an available component; unavailable identities are reserved for the Section 7 catalog"
        );
      }
      if (OFFICIAL_COMPONENT_IDS.includes(entry.componentId)) {
        problems.push(
          `component_id ${entry.componentId} is an official Section 7 id; official components register through their owning items, not the custom path`
        );
      }
      if (this.versionsOf(entry.componentId).length > 0) {
        problems.push(
          `component_id ${entry.componentId} is already registered; custom registrations must use a new component id`
        );
      }
      if (entry.inputSchema === null || entry.inputSchema === undefined) {
        problems.push(
          "inputSchema is required: a component is unavailable until its schema, proof contract, and tests are registered together (Section 16.1)"
        );
      } else {
        const schema = entry.inputSchema as Record<string, unknown>;
        if (schema.type !== "object" || schema.additionalProperties !== false) {
          problems.push(
            "inputSchema must be a closed object schema (type: object with additionalProperties: false); the catalog has no additionalProperties escape"
          );
        } else {
          try {
            this.compileIsolated(schema);
          } catch (compileError) {
            problems.push(
              `inputSchema does not compile: ${compileError instanceof Error ? compileError.message : String(compileError)}`
            );
          }
        }
      }
      if (entry.proofContract === null || entry.proofContract === undefined) {
        problems.push(
          "proofContract is required: a component is unavailable until its schema, proof contract, and tests are registered together (Section 16.1)"
        );
      } else if (
        !Array.isArray(entry.proofContract.selectors) ||
        entry.proofContract.selectors.length === 0
      ) {
        problems.push("proofContract must declare at least one proof selector");
      }
      if (!Array.isArray(entry.tests) || entry.tests.length === 0) {
        problems.push(
          "tests are required: a component is unavailable until its schema, proof contract, and tests are registered together (Section 16.1)"
        );
      } else {
        const testIds = entry.tests.map((test) => test.id);
        if (new Set(testIds).size !== testIds.length) {
          problems.push("test ids within a registration must be unique");
        }
      }
    }
    const attestation = bundle.reviewAttestation;
    if (!isPlainObject(attestation)) {
      problems.push(
        "reviewAttestation is required: a custom component is implemented, validated, and reviewed before it is registered"
      );
    } else {
      if (attestation.decision !== "approved") {
        problems.push("reviewAttestation.decision must be \"approved\"");
      }
      if (
        typeof attestation.reviewer !== "string" ||
        attestation.reviewer.length === 0
      ) {
        problems.push("reviewAttestation.reviewer must name the reviewer");
      }
      if (
        typeof attestation.statement !== "string" ||
        attestation.statement.length === 0
      ) {
        problems.push("reviewAttestation.statement must state the review outcome");
      }
    }
    if (problems.length > 0) {
      throw new CatalogError(
        "MG_SCHEMA_INVALID",
        `Custom component registration refused: ${problems.join("; ")}`,
        problems.map((message) => ({
          category: "MG_SCHEMA_INVALID" as const,
          path: "",
          message,
        }))
      );
    }
    const accepted = entry as unknown as ComponentEntry;
    this.addEntry(accepted);
    return accepted;
  }

  private compileIsolated(schema: Record<string, unknown>): void {
    const contracts = loadContractsSchema() as unknown as {
      $defs: Record<string, unknown>;
    };
    const { $defs: ownDefs, ...rest } = schema as {
      $defs?: Record<string, unknown>;
    } & Record<string, unknown>;
    const ajv = new Ajv2020({ allErrors: true, strict: false });
    ajv.compile({
      $schema: "https://json-schema.org/draft/2020-12/schema",
      ...rest,
      $defs: { ...contracts.$defs, ...(ownDefs ?? {}) },
    });
  }

  /**
   * Compute the concrete layout descriptor a component produces from
   * one design record (canonical contracts design shape) for one layout
   * variant. Two jobs sharing a primitive but carrying different design
   * records produce different descriptors: the anti-template evidence.
   */
  describeLayout(
    entry: ComponentEntry,
    design: Record<string, unknown>,
    layoutVariant: string
  ): LayoutDescriptor {
    const variant = entry.layoutVariants.find(
      (candidate) => candidate.id === layoutVariant
    );
    if (!variant) {
      throw new CatalogError(
        "MG_SCHEMA_INVALID",
        `Component ${entry.componentId} has no layout variant ${layoutVariant}.`
      );
    }
    const colors = design.colors as
      | { background?: unknown; ink?: unknown; accent?: unknown }
      | undefined;
    const layouts = design.layouts as
      | Record<string, Record<string, unknown>>
      | undefined;
    const layout = layouts?.[layoutVariant];
    if (!colors || !layout) {
      throw new CatalogError(
        "MG_SCHEMA_INVALID",
        `Design record ${String(design.id)} has no colors or layouts.${layoutVariant} block to describe.`
      );
    }
    return {
      componentId: entry.componentId,
      componentVersion: entry.version,
      layoutVariant,
      designId: String(design.id),
      palette: {
        background: String(colors.background),
        ink: String(colors.ink),
        accent: String(colors.accent),
      },
      geometry: JSON.parse(JSON.stringify(layout)) as Record<string, unknown>,
      typeScalePx: {
        headline: Number(layout.headline_px),
        label: Number(layout.label_px),
        value: Number(layout.value_px),
        disclosure: Number(layout.disclosure_px),
      },
      composition: entry.variation.composition,
      framing: entry.variation.framing,
      typeTreatment: entry.variation.typeTreatment,
      pacing: entry.variation.pacing,
    };
  }
}
