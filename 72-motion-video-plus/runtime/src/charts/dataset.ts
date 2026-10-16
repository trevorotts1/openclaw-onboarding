// Truthful chart-data contracts (Directive MG-015, Sections 5.1, 16.6
// rule 6, 16.9, 17.1 M05).
//
// A chart dataset is a standalone serialized document (canonical home:
// data/*.json inside a job, validated there by the contracts layer). This
// module is the chart-contract layer MG-015 adds on top of the canonical
// dataset shape: it separates the data from any animation, and enforces
// the semantic rules a renderer must be able to trust before a single
// mark is drawn:
//
// - identity, units, and a source note are present (canonical schema);
// - the real-vs-illustrative marking (kind) is present and not
//   contradicted by its own source note: invented evidence fails;
// - the domain has exactly two finite, strictly increasing endpoints;
// - every value is finite and lies inside the declared domain (a value
//   outside the scale's declared extent would be drawn clipped or
//   overflowing, which misrepresents it);
// - category (row) IDs and labels are unique;
// - a missing-value policy and a display-rounding rule are declared
//   (MG-015 requires both), and null values are only accepted under a
//   policy that says how they are handled;
// - declared totals and declared sort order check out against the rows,
//   with M05 arithmetic: exact for integer fixtures, otherwise a
//   relative tolerance no worse than 1e-6.
//
// The canonical contracts schema (references/contracts-v2.schema.json,
// dataset $def) cannot yet represent missing values, a missing-value
// policy, a display-rounding rule, a scale declaration, a declared
// total, or a sort declaration: its rows require a numeric value and
// the object is closed. The MG-015 extension fields validated here
// (scale_type, missing_value_policy, display_rounding, declared_total,
// sort) are therefore chart-layer fields until the schema is revised;
// the audit in the MG-015 report files that gap precisely. All findings
// use the Section 16.9 contract category MG_SCHEMA_INVALID (exit
// class 2), the same category the job-level validators use for dataset
// violations, so both layers agree on the failure surface.

/** The Section 16.9 category every dataset-contract finding carries. */
export const DATASET_ERROR_CATEGORY = "MG_SCHEMA_INVALID" as const;

/** Exit class for MG_SCHEMA_INVALID in the Section 16.9 table. */
export const DATASET_ERROR_EXIT_CLASS = 2 as const;

export type DatasetErrorCategory = typeof DATASET_ERROR_CATEGORY;

export interface DatasetFinding {
  category: DatasetErrorCategory;
  /** Dataset-relative locator, for example "rows[1]/value". */
  path: string;
  message: string;
}

/** Thrown by the asserting entry points; carries every finding. */
export class ChartContractError extends Error {
  readonly category: DatasetErrorCategory = DATASET_ERROR_CATEGORY;
  readonly exitClass: number = DATASET_ERROR_EXIT_CLASS;
  readonly findings: DatasetFinding[];

  constructor(findings: DatasetFinding[]) {
    super(
      findings.length > 0
        ? findings.map((f) => `${f.path}: ${f.message}`).join("; ")
        : "chart data contract violation"
    );
    this.name = "ChartContractError";
    this.findings = findings;
  }
}

export type DatasetKind = "illustrative" | "observed";
export type MissingValuePolicy = "error" | "zero" | "skip" | "interpolate";
export type ScaleType = "linear" | "log";

export interface DisplayRounding {
  /** Fractional digits shown for every displayed value (0 = integers). */
  decimals: number;
}

export interface DatasetSortDeclaration {
  by: "value";
  direction: "ascending" | "descending";
}

export interface ChartDatasetRow {
  id: string;
  label: string;
  /** Null only under a missing-value policy other than "error". */
  value: number | null;
}

/** A dataset that has passed the full MG-015 chart contract. */
export interface ChartDataset {
  schema_version: "2.0";
  id: string;
  kind: DatasetKind;
  source_note: string;
  units: string;
  domain: [number, number];
  scale_type: ScaleType;
  missing_value_policy: MissingValuePolicy;
  display_rounding: DisplayRounding;
  declared_total?: number;
  sort?: DatasetSortDeclaration;
  rows: ChartDatasetRow[];
}

const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/;

const CANONICAL_KEYS = new Set([
  "schema_version",
  "id",
  "kind",
  "source_note",
  "units",
  "domain",
  "rows",
]);

/** MG-015 chart-layer extension fields (see the header note). */
const EXTENSION_KEYS = new Set([
  "scale_type",
  "missing_value_policy",
  "display_rounding",
  "declared_total",
  "sort",
]);

const MISSING_POLICIES: readonly string[] = ["error", "zero", "skip", "interpolate"];

/**
 * Phrases that admit the values are not real evidence. An "observed"
 * dataset whose own source note carries one of these contradicts its
 * marking and fails as invented evidence. This is an internal
 * consistency check only: no validator can prove real-world truth, so
 * the rule is deliberately narrow and deterministic.
 */
const CONTRADICTION_MARKERS: readonly string[] = [
  "illustrative",
  "invented",
  "made up",
  "made-up",
  "fabricated",
  "fictional",
  "not evidence",
  "not real",
];

type Doc = Record<string, unknown>;

function isDoc(value: unknown): value is Doc {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** M05 comparison: exact when both sides are integers, otherwise a
 * relative tolerance of 1e-6. */
export function numbersMatch(actual: number, expected: number): boolean {
  if (Number.isInteger(actual) && Number.isInteger(expected)) return actual === expected;
  const scale = Math.max(Math.abs(actual), Math.abs(expected), 1);
  return Math.abs(actual - expected) <= 1e-6 * scale;
}

/**
 * Canonical-shape validation only: the rules the shipped contracts
 * schema (dataset $def) plus the job-level semantic layer already
 * enforce (shape, closed keys within the canonical set, finite values,
 * unique row IDs, exactly two strictly increasing domain endpoints).
 * A dataset can pass this and still fail the MG-015 chart contract.
 */
export function validateCanonicalShape(doc: unknown): DatasetFinding[] {
  return validate(doc, false);
}

/**
 * Full MG-015 chart-contract validation. Returns every finding; an
 * empty list means the document is a ChartDataset a renderer may trust.
 */
export function validateDataset(doc: unknown): DatasetFinding[] {
  return validate(doc, true);
}

/** Validate and return the typed dataset, or throw ChartContractError
 * carrying every finding. */
export function assertChartDataset(doc: unknown): ChartDataset {
  const findings = validateDataset(doc);
  if (findings.length > 0) throw new ChartContractError(findings);
  return doc as ChartDataset;
}

function validate(doc: unknown, full: boolean): DatasetFinding[] {
  const findings: DatasetFinding[] = [];
  const add = (path: string, message: string): void => {
    findings.push({ category: DATASET_ERROR_CATEGORY, path, message });
  };

  if (!isDoc(doc)) {
    add("", "Dataset must be a JSON object.");
    return findings;
  }

  // Closed key set: canonical keys always; MG-015 extension keys only
  // under the full chart contract.
  for (const key of Object.keys(doc)) {
    if (CANONICAL_KEYS.has(key)) continue;
    if (full && EXTENSION_KEYS.has(key)) continue;
    add(
      key,
      full
        ? `Unknown dataset field "${key}": the chart data contract is closed.`
        : `Unknown dataset field "${key}": the canonical dataset shape is closed.`
    );
  }

  if (doc.schema_version !== "2.0") {
    add("schema_version", 'Dataset schema_version must be "2.0".');
  }

  if (typeof doc.id !== "string" || !ID_PATTERN.test(doc.id)) {
    add("id", "Dataset id must be a well-formed identifier string.");
  }

  // Real-vs-illustrative marking (MG-015): required, never inferred.
  const kind = doc.kind;
  if (kind === undefined) {
    add(
      "kind",
      "Dataset is unmarked: kind must declare \"illustrative\" or \"observed\"; unmarked data may not be presented as real."
    );
  } else if (kind !== "illustrative" && kind !== "observed") {
    add("kind", `Dataset kind must be "illustrative" or "observed", got ${JSON.stringify(kind)}.`);
  }

  if (typeof doc.source_note !== "string" || doc.source_note.length === 0) {
    add("source_note", "Dataset source_note must be a non-empty string naming the data source.");
  } else if (kind === "observed") {
    const note = doc.source_note.toLowerCase();
    const marker = CONTRADICTION_MARKERS.find((m) => note.includes(m));
    if (marker) {
      add(
        "source_note",
        `Dataset declares kind "observed" but its source note admits the values are not real evidence ("${marker}"): invented evidence fails.`
      );
    }
  }

  if (typeof doc.units !== "string" || doc.units.length === 0) {
    add("units", "Dataset units must be a non-empty string.");
  }

  // Domain: exactly two finite, strictly increasing endpoints (16.6
  // rule 6, identical wording family to the job-level semantic layer).
  const domain = doc.domain;
  let domainPair: [number, number] | null = null;
  if (!Array.isArray(domain) || domain.length !== 2) {
    add("domain", "Dataset domain must have exactly two endpoints.");
  } else if (!isFiniteNumber(domain[0]) || !isFiniteNumber(domain[1]) || !(domain[0] < domain[1])) {
    add("domain", "Dataset domain endpoints must be finite and strictly increasing.");
  } else {
    domainPair = [domain[0], domain[1]];
  }

  // Scale declaration: linear by default; log must be declared here
  // before any log scale may be built from this dataset (scale.ts).
  let scaleType: ScaleType = "linear";
  if (doc.scale_type !== undefined) {
    if (doc.scale_type !== "linear" && doc.scale_type !== "log") {
      add("scale_type", `Dataset scale_type must be "linear" or "log", got ${JSON.stringify(doc.scale_type)}.`);
    } else {
      scaleType = doc.scale_type;
    }
  }
  if (scaleType === "log" && domainPair && !(domainPair[0] > 0)) {
    add("domain", "A log scale requires a domain of positive values; log of zero or a negative is undefined.");
  }

  // Missing-value policy (MG-015): a declared policy is required.
  let policy: MissingValuePolicy | null = null;
  if (doc.missing_value_policy === undefined) {
    if (full) {
      add(
        "missing_value_policy",
        "MG-015 requires a declared missing-value policy (\"error\", \"zero\", \"skip\", or \"interpolate\"); the canonical schema does not carry one yet."
      );
    }
  } else if (
    typeof doc.missing_value_policy !== "string" ||
    !MISSING_POLICIES.includes(doc.missing_value_policy)
  ) {
    add(
      "missing_value_policy",
      `Dataset missing_value_policy must be one of ${MISSING_POLICIES.join(", ")}, got ${JSON.stringify(doc.missing_value_policy)}.`
    );
  } else {
    policy = doc.missing_value_policy as MissingValuePolicy;
  }

  // Display rounding (MG-015): a declared rule is required so displayed
  // values can be checked against it (M05).
  if (doc.display_rounding === undefined) {
    if (full) {
      add(
        "display_rounding",
        "MG-015 requires a declared display-rounding rule ({decimals: n}); the canonical schema does not carry one yet."
      );
    }
  } else if (!isDoc(doc.display_rounding)) {
    add("display_rounding", "Dataset display_rounding must be an object of the form {decimals: n}.");
  } else {
    for (const key of Object.keys(doc.display_rounding)) {
      if (key !== "decimals") {
        add(`display_rounding/${key}`, `Unknown display_rounding field "${key}".`);
      }
    }
    const decimals = doc.display_rounding.decimals;
    if (!Number.isInteger(decimals) || (decimals as number) < 0 || (decimals as number) > 10) {
      add("display_rounding/decimals", "Display rounding decimals must be an integer between 0 and 10.");
    }
  }

  if (doc.declared_total !== undefined && !isFiniteNumber(doc.declared_total)) {
    add("declared_total", "Dataset declared_total must be a finite number when present.");
  }

  let sortDecl: DatasetSortDeclaration | null = null;
  if (doc.sort !== undefined) {
    if (!isDoc(doc.sort)) {
      add("sort", 'Dataset sort must be an object of the form {by: "value", direction: "ascending"|"descending"}.');
    } else {
      for (const key of Object.keys(doc.sort)) {
        if (key !== "by" && key !== "direction") {
          add(`sort/${key}`, `Unknown sort field "${key}".`);
        }
      }
      if (doc.sort.by !== "value") {
        add("sort/by", 'Dataset sort.by must be "value".');
      }
      if (doc.sort.direction !== "ascending" && doc.sort.direction !== "descending") {
        add("sort/direction", 'Dataset sort.direction must be "ascending" or "descending".');
      }
      if (doc.sort.by === "value" && (doc.sort.direction === "ascending" || doc.sort.direction === "descending")) {
        sortDecl = { by: "value", direction: doc.sort.direction };
      }
    }
  }

  // Rows.
  const rows = doc.rows;
  if (!Array.isArray(rows) || rows.length === 0) {
    add("rows", "Dataset rows must be a non-empty array.");
    return findings;
  }
  const seenIds = new Set<string>();
  const seenLabels = new Set<string>();
  rows.forEach((row, i) => {
    const at = `rows[${i}]`;
    if (!isDoc(row)) {
      add(at, "Dataset row must be an object.");
      return;
    }
    for (const key of Object.keys(row)) {
      if (key !== "id" && key !== "label" && key !== "value") {
        add(`${at}/${key}`, `Unknown dataset row field "${key}".`);
      }
    }
    if (typeof row.id !== "string" || !ID_PATTERN.test(row.id)) {
      add(`${at}/id`, "Dataset row id must be a well-formed identifier string.");
    } else if (seenIds.has(row.id)) {
      add(`${at}/id`, `Duplicate dataset category id "${row.id}".`);
    } else {
      seenIds.add(row.id);
    }
    if (typeof row.label !== "string" || row.label.length === 0) {
      add(`${at}/label`, "Dataset row label must be a non-empty string.");
    } else if (seenLabels.has(row.label)) {
      add(`${at}/label`, `Duplicate dataset category label "${row.label}": categories must be unique.`);
    } else {
      seenLabels.add(row.label);
    }
    const value = row.value;
    if (value === null || value === undefined) {
      // A missing value is only acceptable when a declared policy says
      // how it is handled; the "error" policy by definition rejects it.
      if (full && policy !== "zero" && policy !== "skip" && policy !== "interpolate") {
        add(
          `${at}/value`,
          `Dataset row "${typeof row.id === "string" ? row.id : i}" has a missing value with no handling policy: ` +
            (policy === "error"
              ? 'the declared policy is "error".'
              : "missing_value_policy is absent or does not handle missing values.")
        );
      } else if (!full) {
        add(`${at}/value`, `Dataset row "${typeof row.id === "string" ? row.id : i}" has a non-finite value.`);
      }
    } else if (!isFiniteNumber(value)) {
      add(`${at}/value`, `Dataset row "${typeof row.id === "string" ? row.id : i}" has a non-finite value.`);
    } else if (domainPair && (value < domainPair[0] || value > domainPair[1])) {
      add(
        `${at}/value`,
        `Dataset row "${typeof row.id === "string" ? row.id : i}" value ${value} lies outside the declared domain [${domainPair[0]}, ${domainPair[1]}]: it would be drawn clipped or overflowing.`
      );
    }
  });

  if (!full) return findings;

  // Totals and sort are evaluated on policy-resolved values; both are
  // MG-015 checks, so they run only under the full contract, and only
  // when nothing above produced a finding: arithmetic on rows that
  // already failed (non-finite, missing without a policy, out of
  // domain) would report a second, misleading failure.
  if (findings.length > 0) return findings;
  const typed = doc as unknown as ChartDataset;
  const resolved = resolveRowValues(typed);

  if (isFiniteNumber(doc.declared_total)) {
    const sum = resolved.reduce((acc, r) => acc + (r.value ?? 0), 0);
    if (!numbersMatch(sum, doc.declared_total)) {
      add(
        "declared_total",
        `Dataset declared_total ${doc.declared_total} does not match the row total ${sum} (M05: exact for integers, 1e-6 relative otherwise).`
      );
    }
  }

  if (sortDecl) {
    const seq = resolved.filter((r) => r.value !== null).map((r) => r.value as number);
    for (let i = 1; i < seq.length; i += 1) {
      const ok =
        sortDecl.direction === "ascending" ? seq[i] >= seq[i - 1] : seq[i] <= seq[i - 1];
      if (!ok) {
        add(
          "sort",
          `Dataset rows violate the declared sort order (${sortDecl.direction} by value) at resolved position ${i}.`
        );
        break;
      }
    }
  }

  return findings;
}

/**
 * Resolve row values under the dataset's missing-value policy.
 * - "error": no nulls survive validation; any present null stays null
 *   here and callers must treat it as a contract violation.
 * - "zero": a missing value counts as exactly 0.
 * - "skip": a missing value stays null and produces no mark; geometry
 *   consumers must exclude the row.
 * - "interpolate": a missing value is linearly interpolated between
 *   its nearest numeric neighbours; a run at an edge takes the nearest
 *   numeric value. If every row is missing the dataset cannot be
 *   resolved and every value stays null.
 */
export function resolveRowValues(
  dataset: ChartDataset
): Array<{ row: ChartDatasetRow; value: number | null }> {
  const policy = dataset.missing_value_policy;
  const numericIdx = dataset.rows
    .map((row, i) => (typeof row.value === "number" ? i : -1))
    .filter((i) => i >= 0);
  return dataset.rows.map((row, i) => {
    if (typeof row.value === "number") return { row, value: row.value };
    switch (policy) {
      case "zero":
        return { row, value: 0 };
      case "interpolate": {
        if (numericIdx.length === 0) return { row, value: null };
        const prev = [...numericIdx].reverse().find((j) => j < i);
        const next = numericIdx.find((j) => j > i);
        if (prev === undefined && next === undefined) return { row, value: null };
        if (prev === undefined) return { row, value: dataset.rows[next as number].value };
        if (next === undefined) return { row, value: dataset.rows[prev].value };
        const v0 = dataset.rows[prev].value as number;
        const v1 = dataset.rows[next].value as number;
        const t = (i - prev) / (next - prev);
        return { row, value: v0 + (v1 - v0) * t };
      }
      case "skip":
      case "error":
      default:
        return { row, value: null };
    }
  });
}
