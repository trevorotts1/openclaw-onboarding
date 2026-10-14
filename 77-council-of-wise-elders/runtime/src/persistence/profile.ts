/**
 * Council state-authority profile (CWE-006, directive Sections 4.5,
 * 16.1, and 30.2.18).
 *
 * One installation has one authoritative store. The state-authority
 * mode (standalone SQLite on this installation, or managed by the
 * Command Center server) is chosen at installation or session
 * creation, recorded here in the council data directory, and never
 * switched silently: opening the store with a different mode than the
 * recorded one fails loudly with PERSISTENCE_AUTHORITY_MODE_MISMATCH.
 * A managed authority that becomes unreachable surfaces a connection
 * failure to the caller; it never falls back to a standalone database
 * that would diverge and conflict later.
 *
 * The profile contains no secret material by construction: it records
 * the chosen mode, the authority locator (a host-and-path reference,
 * never a credential), and installation bookkeeping only.
 */

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import {
  PERSISTENCE_CONFIG_SCHEMA_VERSION,
  type AuthorityMode,
} from './config.js';
import { PersistenceError } from './errors.js';

export const COUNCIL_PROFILE_FILE_NAME = 'council-profile.json';

export interface CouncilInstallationProfile {
  schema_version: string;
  authority_mode: AuthorityMode;
  /** Managed-mode authority locator (reference only, never a credential). */
  authority_ref: string | null;
  installation_id: string;
  recorded_at: string;
  config_schema_version: string;
}

function profilePath(dataDir: string): string {
  return join(dataDir, COUNCIL_PROFILE_FILE_NAME);
}

/** Read the recorded profile, or null when no store was ever opened. */
export function readInstallationProfile(dataDir: string): CouncilInstallationProfile | null {
  const path = profilePath(dataDir);
  if (!existsSync(path)) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(path, 'utf8'));
  } catch {
    throw new PersistenceError(
      'PERSISTENCE_SCHEMA_UNAVAILABLE',
      `The council installation profile at ${path} is unreadable or corrupt. The store was not opened and no mode was inferred.`,
      { retryable: false, action: 'Restore the profile from backup, or remove it and let the installer choose and record a mode explicitly.' },
    );
  }
  const profile = parsed as CouncilInstallationProfile;
  if (
    typeof profile !== 'object' ||
    profile === null ||
    (profile.authority_mode !== 'standalone' && profile.authority_mode !== 'managed') ||
    typeof profile.installation_id !== 'string' ||
    profile.installation_id.length === 0
  ) {
    throw new PersistenceError(
      'PERSISTENCE_SCHEMA_UNAVAILABLE',
      `The council installation profile at ${path} does not have the recorded shape. The store was not opened and no mode was inferred.`,
      { retryable: false },
    );
  }
  return profile;
}

/**
 * Ensure the profile records exactly `requestedMode`. When no profile
 * exists yet, this installation chooses the mode now and records it
 * (atomic write via a temp file and rename, mode 0600). When a profile
 * exists with a different mode, the open is refused: switching
 * authority mode is an explicit migration, never a silent fallback,
 * including when the recorded authority is unreachable.
 */
export function ensureInstallationProfile(
  dataDir: string,
  requested: {
    authority_mode: AuthorityMode;
    authority_ref: string | null;
    installation_id: string;
    recorded_at: string;
  },
): CouncilInstallationProfile {
  const existing = readInstallationProfile(dataDir);
  if (existing) {
    if (existing.authority_mode !== requested.authority_mode) {
      throw new PersistenceError(
        'PERSISTENCE_AUTHORITY_MODE_MISMATCH',
        `This installation recorded state-authority mode "${existing.authority_mode}" at setup, but the caller requested "${requested.authority_mode}". The mode is never switched silently and an unreachable managed authority never falls back to a standalone database. The store was not opened.`,
        {
          retryable: false,
          action: 'Run an explicit, separately authorized authority migration, or configure the caller with the recorded mode.',
          detail: {
            recorded_mode: existing.authority_mode,
            requested_mode: requested.authority_mode,
          },
        },
      );
    }
    if (
      existing.authority_mode === 'managed' &&
      existing.authority_ref !== null &&
      requested.authority_ref !== null &&
      existing.authority_ref !== requested.authority_ref
    ) {
      throw new PersistenceError(
        'PERSISTENCE_AUTHORITY_MODE_MISMATCH',
        `This installation recorded managed authority "${existing.authority_ref}", but the caller requested "${requested.authority_ref}". Authority is never repointed silently. The store was not opened.`,
        { retryable: false },
      );
    }
    return existing;
  }
  const profile: CouncilInstallationProfile = {
    schema_version: 'wise-elders.installation-profile/v1',
    authority_mode: requested.authority_mode,
    authority_ref: requested.authority_mode === 'managed' ? requested.authority_ref : null,
    installation_id: requested.installation_id,
    recorded_at: requested.recorded_at,
    config_schema_version: PERSISTENCE_CONFIG_SCHEMA_VERSION,
  };
  const path = profilePath(dataDir);
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  const tmp = `${path}.tmp-${process.pid}`;
  writeFileSync(tmp, `${JSON.stringify(profile, null, 2)}\n`, { mode: 0o600 });
  renameSync(tmp, path);
  return profile;
}
