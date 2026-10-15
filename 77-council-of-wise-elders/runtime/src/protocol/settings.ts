/**
 * Scoped council settings (CWE-050; directive Sections 15.6, 17.2):
 * the nonsecret budget and behavior settings, per installation scope.
 *
 * The settings contract (CWE-003 councilSettingsSchema) is nonsecret
 * BY CONSTRUCTION: it admits only budget ceilings, concurrency and
 * retry limits, and the fallback policy. The strict schema rejects
 * any other key, so a credential can never be stored as a "setting";
 * this service validates every write through the contract validator
 * and rejects unknown or secret-shaped keys by name.
 *
 * Settings are read when a run is authorized: a session's ceilings
 * freeze into its grant at preview time (CWE-049), so changing a
 * setting never rewrites a running session's budget. Unset scopes read
 * as DEFAULT_COUNCIL_SETTINGS, including the Section 15.6 ceiling of
 * 50 provider requests per session.
 *
 * Persistence is a port: hosts back it with their own store (the
 * standalone host uses a file in the per-user data directory, written
 * with owner-only permissions; tests use the in-memory port below).
 */

import {
  DEFAULT_COUNCIL_SETTINGS,
  validateCouncilSettings,
  type CouncilSettings,
} from '../contracts/index.js';
import { ProtocolError } from './errors.js';

export interface SettingsPersistencePort {
  read(scopeKey: string): CouncilSettings | null;
  write(scopeKey: string, settings: CouncilSettings): void;
}

/** Scope key for settings: one settings record per installation. */
export function settingsScopeKey(scope: {
  tenant_id: string;
  company_id: string;
  installation_id: string;
}): string {
  return `${scope.tenant_id}/${scope.company_id}/${scope.installation_id}`;
}

const SECRET_SHAPED_KEY = /(key|token|secret|password|credential|auth)/i;

export class CouncilSettingsService {
  constructor(private readonly persistence: SettingsPersistencePort) {}

  /** The effective settings for a scope: stored value, else defaults. */
  getSettings(scope: {
    tenant_id: string;
    company_id: string;
    installation_id: string;
  }): CouncilSettings {
    return this.persistence.read(settingsScopeKey(scope)) ?? DEFAULT_COUNCIL_SETTINGS;
  }

  /**
   * Replace a scope's settings. The full record is validated through
   * the CWE-003 contract validator; partial or unknown fields fail.
   */
  updateSettings(
    scope: { tenant_id: string; company_id: string; installation_id: string },
    settings: unknown,
  ): CouncilSettings {
    if (settings && typeof settings === 'object') {
      for (const key of Object.keys(settings as Record<string, unknown>)) {
        if (SECRET_SHAPED_KEY.test(key)) {
          throw new ProtocolError(
            'SETTINGS_INVALID',
            `Settings are nonsecret by contract; the key "${key}" looks like a credential and can never be stored as a setting.`,
            { key },
          );
        }
      }
    }
    const check = validateCouncilSettings(settings);
    if (!check.ok) {
      throw new ProtocolError(
        'SETTINGS_INVALID',
        `Settings failed contract validation: ${check.issues.map((i) => i.message).join('; ')}`,
        {},
      );
    }
    this.persistence.write(settingsScopeKey(scope), check.value);
    return check.value;
  }
}

/** In-memory persistence port (embedding and tests). */
export class InMemorySettingsPersistence implements SettingsPersistencePort {
  private readonly values = new Map<string, CouncilSettings>();
  read(scopeKey: string): CouncilSettings | null {
    return this.values.get(scopeKey) ?? null;
  }
  write(scopeKey: string, settings: CouncilSettings): void {
    this.values.set(scopeKey, settings);
  }
}
