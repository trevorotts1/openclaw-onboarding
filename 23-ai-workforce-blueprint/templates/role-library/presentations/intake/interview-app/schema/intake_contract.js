// =============================================================================
// PRES-006 — schema-driven intake completeness gate + version-aware migration.
// =============================================================================
// The PRES-006-owned Worker (worker/src/index.js) imports THIS module. It
// reads the one canonical field-path contract (intake_fields.js) and derives
// everything: the required set, the false-vs-missing distinction, and the
// legacy migration. The hand-copied REQUIRED_BRIEF_FIELDS array that used to
// live in the worker (and to drift) is gone — this is its only replacement.
// (deployed-r2/src/index.js is PRES-005-owned since the disjoint-ownership
// repair and keeps its own pres005 completeness gate.)
//
// Pure functions only — unit-testable with `node --test` offline, no
// Cloudflare runtime, no network.

import { INTAKE_CONTRACT } from "./intake_fields.js";

const CONTRACT = INTAKE_CONTRACT;

/** "deck_brief.OFFER_NAME" -> ["deck_brief", "OFFER_NAME"]. */
export function splitPath(path) {
  const i = path.indexOf(".");
  if (i === -1) return [path, ""];
  return [path.slice(0, i), path.slice(i + 1)];
}

/** The section object a canonical path names, created empty when absent.
 *  Returns null when the path is malformed. */
export function sectionFor(intake, path, create = false) {
  const [section, rest] = splitPath(path);
  if (!section || !rest) return null;
  let obj = intake[section];
  if (!obj || typeof obj !== "object") {
    if (!create) return null;
    obj = {};
    intake[section] = obj;
  }
  return obj;
}

/** Read one canonical path WITHOUT creating anything. Returns undefined when
 *  absent. Only the two-level paths this contract defines are supported. */
export function readPath(intake, path) {
  if (!intake || typeof intake !== "object") return undefined;
  const [section, rest] = splitPath(path);
  const obj = intake[section];
  if (!obj || typeof obj !== "object") return undefined;
  const [key, sub] = splitPath(rest);
  if (sub) {
    const inner = obj[key];
    if (!inner || typeof inner !== "object") return undefined;
    return inner[sub];
  }
  return obj[key];
}

/** Write one canonical path, creating its section when absent. */
export function writePath(intake, path, value) {
  const obj = sectionFor(intake, path, true);
  if (!obj) return false;
  const [section, rest] = splitPath(path);
  const [key, sub] = splitPath(rest);
  if (sub) {
    let inner = obj[key];
    if (!inner || typeof inner !== "object") {
      inner = {};
      obj[key] = inner;
    }
    inner[sub] = value;
    return true;
  }
  obj[key] = value;
  return true;
}

// ---------------------------------------------------------------------------
// MISSING vs ANSWERED — the false/no distinction
// ---------------------------------------------------------------------------

/** A field is PRESENT when it holds a real answer. The strings "false" and
 *  "no" (and boolean false) are REAL ANSWERS — a decline recorded by the
 *  client — and never count as missing. undefined / null / blank-string /
 *  empty-array are missing. */
export function isPresent(value) {
  if (value === undefined || value === null) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return true; // an array (even empty for optional image_links) is an answer record
  return true; // numbers, booleans, objects
}

/**
 * The canonical completeness check. Returns { ok, missing: [canonical paths],
 * contract_version }. Distinguishes "answered no/false" from "never asked /
 * never answered" — only the latter is missing.
 */
export function validateIntakeCompleteness(intake) {
  const missing = [];
  for (const path of CONTRACT.required_fields) {
    if (!isPresent(readPath(intake, path))) missing.push(path);
  }
  return { ok: missing.length === 0, missing, contract_version: CONTRACT.version };
}

// ---------------------------------------------------------------------------
// Version-aware legacy migration
// ---------------------------------------------------------------------------

function normalizeBooleanish(value, table) {
  if (typeof value !== "string") return value;
  const norm = value.trim().toLowerCase();
  if (Object.prototype.hasOwnProperty.call(table, norm)) return table[norm];
  return value;
}

function sameValue(a, b, table) {
  if (a === undefined || b === undefined) return false;
  const na = typeof a === "string" ? normalizeBooleanish(a, table).trim().toLowerCase() : a;
  const nb = typeof b === "string" ? normalizeBooleanish(b, table).trim().toLowerCase() : b;
  return String(na).toLowerCase() === String(nb).toLowerCase();
}

/**
 * Migrate a legacy (version 1 / no schema_version) intake record forward to
 * the current contract, IN PLACE. Returns
 *   { ok: true,  migrated: [paths], intake }            — migrated (or already current)
 *   { ok: false, conflicts: [{path, canonical_value, legacy_path, legacy_value}], note }
 *                                                       — contradiction: REFUSED
 *
 * Contradiction rule: when a legacy alias holds a DIFFERENT answer than the
 * canonical path already carries, the record is refused with the migration
 * explanation naming both values — never silently chosen. Equal values
 * (after booleanish normalization "true"/"false" -> "yes"/"no") are folded.
 */
export function migrateIntake(intake) {
  if (!intake || typeof intake !== "object") {
    return { ok: false, conflicts: [], note: "migration refused: intake is not an object" };
  }
  const version = intake.schema_version;
  if (version === CONTRACT.version) {
    return { ok: true, migrated: [], intake };
  }
  if (version !== undefined && version !== null) {
    const v = Number(version);
    if (Number.isFinite(v) && v > CONTRACT.version) {
      return {
        ok: false,
        conflicts: [],
        note: `migration refused: record declares schema_version ${v}, newer than this build's contract version ${CONTRACT.version} — refusing to downgrade`,
      };
    }
  }

  const table = CONTRACT.migration.boolean_normalization;
  const migrated = [];
  const conflicts = [];

  for (const field of CONTRACT.fields) {
    const canonical = field.canonical_path;
    const aliases = field.legacy_aliases || [];
    if (!aliases.length) continue;
    const canonValue = readPath(intake, canonical);
    for (const alias of aliases) {
      const legacyValue = readPath(intake, alias);
      if (legacyValue === undefined || legacyValue === null) continue;
      if (typeof legacyValue === "string" && !legacyValue.trim()) continue;
      if (!isPresent(canonValue)) {
        // Move the legacy answer home (booleanish-normalized for flag fields).
        let moved = legacyValue;
        if (typeof moved === "boolean") moved = moved ? "yes" : "no";
        else moved = normalizeBooleanish(moved, table);
        writePath(intake, canonical, moved);
        migrated.push(`${alias} -> ${canonical}`);
        deleteSectionKey(intake, alias);
      } else if (!sameValue(canonValue, legacyValue, table)) {
        conflicts.push({
          path: canonical,
          canonical_value: canonValue,
          legacy_path: alias,
          legacy_value: legacyValue,
        });
      } else {
        // Same answer in both places: drop the redundant legacy copy.
        deleteSectionKey(intake, alias);
        migrated.push(`${alias} (redundant, matches ${canonical})`);
      }
    }
  }

  if (conflicts.length) {
    const details = conflicts
      .map((c) => `${c.legacy_path}=${JSON.stringify(c.legacy_value)} vs ${c.path}=${JSON.stringify(c.canonical_value)}`)
      .join("; ");
    return {
      ok: false,
      conflicts,
      note:
        `migration refused: contradictory legacy values cannot be migrated ` +
        `(contract v${CONTRACT.version}) — ${details}. Both locations were read; ` +
        `they disagree, so neither was chosen. Resolve the record and re-submit.`,
    };
  }

  intake.schema_version = CONTRACT.version;
  return { ok: true, migrated, intake };
}

/** Delete one alias key ("deck_brief.WANT_SALES_CHECKOUT" or a flat
 *  "WANT_SALES_CHECKOUT") without disturbing anything else. */
function deleteSectionKey(intake, alias) {
  const [section, rest] = splitPath(alias);
  if (!rest) {
    delete intake[section];
    return;
  }
  const obj = intake[section];
  if (obj && typeof obj === "object") delete obj[rest];
}

/** Convenience used by the Workers' POST /api/intake: validate + migrate in
 *  one pass, so a legacy record is either migrated and accepted or refused
 *  with the migration note — never half-migrated into storage. */
export function validateAndMigrate(intake) {
  const mig = migrateIntake(intake);
  if (!mig.ok) return mig;
  const check = validateIntakeCompleteness(intake);
  if (!check.ok) {
    return {
      ok: false,
      missing: check.missing,
      note: "intake incomplete — required fields missing or empty (contract v" + CONTRACT.version + ")",
    };
  }
  return { ok: true, migrated: mig.migrated, missing: [], intake };
}
