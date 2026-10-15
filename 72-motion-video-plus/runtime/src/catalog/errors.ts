// Catalog error categories (Directive MG-018, Section 16.9).
//
// The catalog reports four stable categories:
// - MG_SCHEMA_INVALID (exit class 2): props or registration bundles that
//   violate a closed schema or the registration contract.
// - MG_UNKNOWN_COMPONENT (exit class 2): a component_id the catalog has
//   never registered, mirroring the shipped MG-007 validators.
// - MG_TIMELINE_INVALID (exit class 2): a schema-valid scene whose motion
//   interval contradicts its duration, mirroring the shipped validators'
//   intra-scene timeline rule.
// - MG_CAPABILITY_UNSUPPORTED (exit class 3): a component the catalog has
//   registered by identity but whose production bundle (closed input
//   schema, proof contract, and tests, registered together per Section
//   16.1) has not landed yet. Section 16.9 places
//   MG_CAPABILITY_UNSUPPORTED in the dependency class, exit 3, "Required
//   dependency unavailable": the named capability exists in the catalog
//   but the runtime cannot yet execute it. That is distinct from an
//   unknown id (a contract error, exit 2) and it never falls back to a
//   substitute component. Note that the adapters layer names its sibling
//   category MG_CAPABILITY_MISSING; the catalog deliberately uses the
//   Section 16.9 stable-table name.

export type CatalogErrorCategory =
  | "MG_SCHEMA_INVALID"
  | "MG_UNKNOWN_COMPONENT"
  | "MG_TIMELINE_INVALID"
  | "MG_CAPABILITY_UNSUPPORTED";

/** Blocking order for first-error reporting, mirroring the shipped order. */
export const CATALOG_CATEGORY_ORDER: CatalogErrorCategory[] = [
  "MG_SCHEMA_INVALID",
  "MG_UNKNOWN_COMPONENT",
  "MG_TIMELINE_INVALID",
  "MG_CAPABILITY_UNSUPPORTED",
];

export function exitClassForCatalogCategory(
  category: CatalogErrorCategory
): number {
  switch (category) {
    case "MG_SCHEMA_INVALID":
    case "MG_UNKNOWN_COMPONENT":
    case "MG_TIMELINE_INVALID":
      return 2;
    case "MG_CAPABILITY_UNSUPPORTED":
      return 3;
  }
}

export interface CatalogFinding {
  category: CatalogErrorCategory;
  /** JSON-pointer-style path into the offending document, "" for the root. */
  path: string;
  message: string;
}

/** First category present, in CATALOG_CATEGORY_ORDER, or null when clean. */
export function firstCatalogCategory(
  findings: CatalogFinding[]
): CatalogErrorCategory | null {
  for (const category of CATALOG_CATEGORY_ORDER) {
    if (findings.some((finding) => finding.category === category)) {
      return category;
    }
  }
  return null;
}

export class CatalogError extends Error {
  readonly category: CatalogErrorCategory;
  readonly exitClass: number;
  readonly findings: CatalogFinding[];

  constructor(
    category: CatalogErrorCategory,
    message: string,
    findings: CatalogFinding[] = []
  ) {
    super(message);
    this.name = "CatalogError";
    this.category = category;
    this.exitClass = exitClassForCatalogCategory(category);
    this.findings = findings;
  }
}
