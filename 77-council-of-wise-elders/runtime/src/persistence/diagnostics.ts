/**
 * The single diagnostic capture sink (CWE-006, directive Section 16.6).
 *
 * Section 16.6 is absolute: there is ONE DiagnosticRetentionPolicy
 * implementation, applied by a single diagnostic sink; other modules
 * cannot write raw bodies directly. This class is that sink for the
 * persistence layer. Raw provider and tool bodies are memory-only by
 * default; a body is persisted only when ALL of the following hold:
 *
 * - an explicit grant is on record for this one named session, issued
 *   by the session owner or an audited support action (a grant row in
 *   council_diagnostic_capture, recorded by recordGrant);
 * - the canonical contracts gate (CWE-003 evaluateCapture) allows the
 *   capture: window open, byte ceilings respected, session not deleted
 *   or revoked;
 * - redaction succeeded and the protected payload store is available.
 *
 * On any failure the sink records only safe metadata (error code,
 * byte count, response hash) and never falls back to plaintext
 * temporary files. Stored payload bytes live in protected files under
 * the council data directory (mode 0600); the database holds only the
 * reference, the counters, and the deadline. Byte counters are
 * computed from the stored rows, so the per-operation and per-session
 * ceilings survive restart and resume. Reads re-check grant
 * revocation and the TTL deadline at read time: an expired payload is
 * inaccessible before any physical cleanup runs.
 *
 * The never-captured classes (hidden reasoning, access tokens,
 * cookies, authentication headers, private keys) are refused by the
 * contracts gate and additionally by the schema CHECK; the sink
 * records only a metadata row naming the refusal, never the content.
 */

import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  evaluateCapture,
  isCaptureExpired,
  sha256Hex,
  validateDiagnosticRetentionPolicy,
  type Clock,
  type DiagnosticRetentionPolicy,
  type IdSource,
} from '../contracts/index.js';
import {
  assertEnvelopePurpose,
  type AuthorizationEnvelope,
} from './envelope.js';
import { PersistenceError, sessionDeleted, sessionNotFound } from './errors.js';
import type { EventJournal } from './journal.js';
import {
  DELETION_TOMBSTONE_OPERATION,
  DELETION_TOMBSTONE_SOURCE,
} from './repositories.js';
import type { CouncilDatabase, SqliteDatabaseHandle } from './sqlite.js';

/**
 * Redact secret-shaped material from a body before capture. Returns
 * the redacted body, or null when redaction is unavailable (the sink
 * then stores metadata only). The default implementation scrubs the
 * shapes the never-captured and secret rules name; hosts may inject a
 * stronger redactor.
 */
export function defaultDiagnosticRedactor(body: string): string {
  return body
    .replace(
      /("(?:access_token|refresh_token|id_token|api_key|apikey|api-key|password|passwd|secret|client_secret|authorization|cookie|set-cookie)"\s*:\s*")[^"]*(")/gi,
      '$1[REDACTED]$2',
    )
    .replace(/((?:authorization|cookie|set-cookie)\s*:\s*)[^\r\n]+/gi, '$1[REDACTED]')
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, 'Bearer [REDACTED]')
    .replace(/\b(sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9-]{8,})\b/g, '[REDACTED]');
}

export type DiagnosticRedactor = (body: string) => string | null;

export interface DiagnosticGrant {
  grant_id: string;
  policy: DiagnosticRetentionPolicy;
  window_started_at: string;
  window_ends_at: string;
  revoked_at: string | null;
}

export type CaptureOutcome =
  | {
      stored: 'payload';
      capture_id: string;
      byte_count: number;
      truncated: boolean;
      payload_deadline_at: string;
    }
  | { stored: 'metadata'; capture_id: string; reason_code: string }
  | { stored: 'none'; reason_code: string };

interface GrantRow {
  id: string;
  policy_schema_version: string;
  authorized_by_principal: string;
  authorization_kind: 'owner' | 'audited_support';
  window_started_at: string;
  window_ends_at: string;
  capture_window_minutes: number;
  payload_ttl_hours: number;
  max_bytes_per_operation: number;
  max_bytes_per_session: number;
  revoked_at: string | null;
}

const REASON_CODES: Array<[RegExp, string]> = [
  [/never captured/, 'never_captured'],
  [/disabled/, 'capture_disabled'],
  [/one named session/, 'wrong_session'],
  [/no owner or audited support/, 'no_authorization'],
  [/deleted or capture revoked/, 'session_deleted_or_revoked'],
  [/window has closed/, 'window_closed'],
  [/metadata only/, 'protection_unavailable'],
  [/ceiling reached/, 'session_byte_ceiling'],
];

function reasonCode(reason: string): string {
  for (const [pattern, code] of REASON_CODES) {
    if (pattern.test(reason)) return code;
  }
  return 'capture_denied';
}

export class DiagnosticSink {
  private readonly payloadDir: string;

  constructor(
    private readonly db: CouncilDatabase,
    private readonly deps: {
      clock: Clock;
      ids: IdSource;
      dataDir: string;
      journal: EventJournal;
      redact?: DiagnosticRedactor;
    },
  ) {
    this.payloadDir = join(deps.dataDir, 'diagnostics');
  }

  // ------------------------------------------------------------- internals

  private sessionExists(handle: SqliteDatabaseHandle, envelope: AuthorizationEnvelope, sessionId: string): boolean {
    const row = handle
      .prepare(
        `SELECT id FROM council_sessions WHERE tenant_id = ? AND company_id = ? AND id = ?`,
      )
      .get(envelope.tenant_id, envelope.company_id, sessionId) as { id: string } | undefined;
    return row !== undefined;
  }

  private isDeleted(envelope: AuthorizationEnvelope, sessionId: string): boolean {
    const row = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT request_key FROM council_request_keys
            WHERE tenant_id = ? AND source = ? AND operation = ? AND request_key = ?`,
        )
        .get(
          envelope.tenant_id,
          DELETION_TOMBSTONE_SOURCE,
          DELETION_TOMBSTONE_OPERATION,
          sessionId,
        ),
    ) as { request_key: string } | undefined;
    return row !== undefined;
  }

  private grantRow(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): GrantRow | null {
    const row = handle
      .prepare(
        `SELECT id, policy_schema_version, authorized_by_principal, authorization_kind,
                window_started_at, window_ends_at, capture_window_minutes,
                payload_ttl_hours, max_bytes_per_operation, max_bytes_per_session,
                revoked_at
           FROM council_diagnostic_capture
          WHERE tenant_id = ? AND company_id = ? AND session_id = ?
            AND record_kind = 'grant' AND revoked_at IS NULL
          ORDER BY created_at DESC LIMIT 1`,
      )
      .get(envelope.tenant_id, envelope.company_id, sessionId) as GrantRow | undefined;
    return row ?? null;
  }

  private policyFromGrant(grant: GrantRow, sessionId: string): DiagnosticRetentionPolicy {
    return {
      schema_version: grant.policy_schema_version as DiagnosticRetentionPolicy['schema_version'],
      enabled: true,
      authorized_by_principal: grant.authorized_by_principal,
      authorization_kind: grant.authorization_kind,
      session_id: sessionId,
      capture_window_minutes: grant.capture_window_minutes,
      payload_ttl_hours: grant.payload_ttl_hours,
      max_bytes_per_operation: grant.max_bytes_per_operation,
      max_bytes_per_session: grant.max_bytes_per_session,
    };
  }

  /** Bytes captured under one grant, computed from stored rows. */
  capturedBytesForGrant(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    grantId: string,
  ): number {
    const row = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT COALESCE(SUM(byte_count), 0) AS total FROM council_diagnostic_capture
            WHERE tenant_id = ? AND company_id = ? AND session_id = ?
              AND record_kind = 'payload' AND grant_id = ?`,
        )
        .get(envelope.tenant_id, envelope.company_id, sessionId, grantId),
    ) as { total: number };
    return Number(row.total);
  }

  // ---------------------------------------------------------------- grants

  /**
   * Record an explicit diagnostic grant for one named session. The
   * policy must be enabled and carry an authorizing principal and
   * kind (the canonical contract refuses anything weaker), the
   * envelope actor must be that principal, and the session must exist
   * and not be deleted. The grant is journaled (grant_issued).
   */
  recordGrant(
    envelope: AuthorizationEnvelope,
    policy: DiagnosticRetentionPolicy,
  ): DiagnosticGrant {
    assertEnvelopePurpose(envelope, 'diagnostic_capture', 'Diagnostic grant');
    const check = validateDiagnosticRetentionPolicy(policy);
    if (!check.ok || !policy.enabled || policy.session_id === null) {
      throw new PersistenceError(
        'PERSISTENCE_DIAGNOSTIC_DENIED',
        'A diagnostic grant requires a valid, enabled DiagnosticRetentionPolicy naming one session and an authorizing principal. The grant was not recorded.',
        { retryable: false, detail: check.ok ? null : { issues: check.issues } },
      );
    }
    if (policy.authorized_by_principal !== envelope.actor_subject) {
      throw new PersistenceError(
        'PERSISTENCE_DIAGNOSTIC_DENIED',
        'The envelope actor is not the principal named in the diagnostic policy. An enabled flag in a request body is not authority; the grant was not recorded.',
        { retryable: false },
      );
    }
    const sessionId = policy.session_id;
    if (this.isDeleted(envelope, sessionId)) throw sessionDeleted(sessionId);
    const now = this.deps.clock.nowUtc();
    const windowEnds = new Date(
      Date.parse(now) + policy.capture_window_minutes * 60_000,
    ).toISOString();
    const grantId = this.deps.ids.newId();
    this.db.write((handle) => {
      if (!this.sessionExists(handle, envelope, sessionId)) {
        throw sessionNotFound(sessionId);
      }
      handle
        .prepare(
          `INSERT INTO council_diagnostic_capture
             (tenant_id, company_id, session_id, id, record_kind, grant_id,
              policy_schema_version, authorized_by_principal, authorization_kind,
              window_started_at, window_ends_at, capture_window_minutes,
              payload_ttl_hours, max_bytes_per_operation, max_bytes_per_session,
              operation_id, data_class, byte_count, truncated, redaction_status,
              payload_protected_ref, payload_deadline_at, response_hash, error_code,
              captured_at, revoked_at, revoked_by, created_at)
           VALUES (?, ?, ?, ?, 'grant', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 0,
                   NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?)`,
        )
        .run(
          envelope.tenant_id,
          envelope.company_id,
          sessionId,
          grantId,
          policy.schema_version,
          policy.authorized_by_principal,
          policy.authorization_kind,
          now,
          windowEnds,
          policy.capture_window_minutes,
          policy.payload_ttl_hours,
          policy.max_bytes_per_operation,
          policy.max_bytes_per_session,
          now,
        );
      this.deps.journal.append(handle, envelope, sessionId, {
        event_id: this.deps.ids.newId(),
        type: 'grant_issued',
        from_state: null,
        to_state: null,
        actor_subject: envelope.actor_subject,
        payload: {
          grant_id: grantId,
          authorization_kind: policy.authorization_kind,
          capture_window_minutes: policy.capture_window_minutes,
          payload_ttl_hours: policy.payload_ttl_hours,
        },
        created_at: now,
      });
    });
    return {
      grant_id: grantId,
      policy,
      window_started_at: now,
      window_ends_at: windowEnds,
      revoked_at: null,
    };
  }

  /** The session's active (unrevoked) grant, or null. */
  activeGrant(envelope: AuthorizationEnvelope, sessionId: string): DiagnosticGrant | null {
    const row = this.db.read((handle) => this.grantRow(handle, envelope, sessionId));
    if (!row) return null;
    return {
      grant_id: row.id,
      policy: this.policyFromGrant(row, sessionId),
      window_started_at: row.window_started_at,
      window_ends_at: row.window_ends_at,
      revoked_at: row.revoked_at,
    };
  }

  /**
   * Revoke a grant. Revocation blocks late writes immediately (the
   * schema trigger also refuses payload inserts under a revoked
   * grant) and every later read re-checks revocation, so previously
   * captured content becomes inaccessible to reads and export at once.
   * Payload files are removed by sweepRevokedAndExpired or by the
   * caller's deletion flow; access never waits for the sweep.
   */
  revokeGrant(envelope: AuthorizationEnvelope, sessionId: string, grantId: string): void {
    assertEnvelopePurpose(envelope, 'diagnostic_capture', 'Diagnostic grant revocation');
    const now = this.deps.clock.nowUtc();
    this.db.write((handle) => {
      const result = handle
        .prepare(
          `UPDATE council_diagnostic_capture
              SET revoked_at = ?, revoked_by = ?
            WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND id = ?
              AND record_kind = 'grant' AND revoked_at IS NULL`,
        )
        .run(now, envelope.actor_subject, envelope.tenant_id, envelope.company_id, sessionId, grantId);
      if (Number(result.changes) !== 1) {
        throw new PersistenceError(
          'PERSISTENCE_DIAGNOSTIC_DENIED',
          `No active diagnostic grant ${grantId} exists for session ${sessionId} in this scope. Nothing was revoked.`,
          { retryable: false },
        );
      }
      this.deps.journal.append(handle, envelope, sessionId, {
        event_id: this.deps.ids.newId(),
        type: 'grant_revoked',
        from_state: null,
        to_state: null,
        actor_subject: envelope.actor_subject,
        payload: { grant_id: grantId },
        created_at: now,
      });
    });
  }

  // --------------------------------------------------------------- capture

  /**
   * Capture one provider or tool body under the session's grant. This
   * is the only write path for raw bodies in the persistence layer.
   * Policy denials never throw: they return a metadata or none outcome
   * with a reason code, so a denied capture cannot crash the operation
   * it was observing.
   */
  capture(
    envelope: AuthorizationEnvelope,
    input: {
      sessionId: string;
      operationId: string;
      dataClass: string;
      body: string;
      errorCode?: string | null;
    },
  ): CaptureOutcome {
    assertEnvelopePurpose(envelope, 'diagnostic_capture', 'Diagnostic capture');
    const now = this.deps.clock.nowUtc();
    const nowMs = Date.parse(now);
    const grant = this.db.read((handle) => this.grantRow(handle, envelope, input.sessionId));
    if (!grant) return { stored: 'none', reason_code: 'no_active_grant' };
    if (!this.db.read((handle) => this.sessionExists(handle, envelope, input.sessionId))) {
      return { stored: 'none', reason_code: 'session_not_found' };
    }
    const policy = this.policyFromGrant(grant, input.sessionId);
    let redacted: string | null = null;
    let protectionEstablished = true;
    try {
      redacted = (this.deps.redact ?? defaultDiagnosticRedactor)(input.body);
      if (redacted === null) protectionEstablished = false;
    } catch {
      protectionEstablished = false;
    }
    const redactedBytes = redacted === null ? 0 : Buffer.byteLength(redacted, 'utf8');
    const decision = evaluateCapture({
      policy,
      sessionId: input.sessionId,
      dataClass: input.dataClass,
      byteLength: protectionEstablished ? redactedBytes : Buffer.byteLength(input.body, 'utf8'),
      sessionBytesAlreadyCaptured: this.capturedBytesForGrant(envelope, input.sessionId, grant.id),
      minutesSinceWindowStart: (nowMs - Date.parse(grant.window_started_at)) / 60_000,
      protectionEstablished,
      sessionDeletedOrRevoked:
        this.isDeleted(envelope, input.sessionId) || grant.revoked_at !== null,
    });
    if (!decision.allowed) {
      const code = reasonCode(decision.reason);
      const captureId = this.deps.ids.newId();
      const neverClass = [
        'hidden_reasoning',
        'access_token',
        'cookie',
        'authentication_header',
        'private_key',
      ].includes(input.dataClass);
      this.db.write((handle) => {
        handle
          .prepare(
            `INSERT INTO council_diagnostic_capture
               (tenant_id, company_id, session_id, id, record_kind, grant_id,
                policy_schema_version, authorized_by_principal, authorization_kind,
                window_started_at, window_ends_at, capture_window_minutes,
                payload_ttl_hours, max_bytes_per_operation, max_bytes_per_session,
                operation_id, data_class, byte_count, truncated, redaction_status,
                payload_protected_ref, payload_deadline_at, response_hash, error_code,
                captured_at, revoked_at, revoked_by, created_at)
             VALUES (?, ?, ?, ?, 'metadata', ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                     NULL, ?, ?, ?, 0, ?, NULL, NULL, ?, ?, ?, NULL, NULL, ?)`,
          )
          .run(
            envelope.tenant_id,
            envelope.company_id,
            input.sessionId,
            captureId,
            grant.id,
            input.operationId,
            neverClass ? null : input.dataClass,
            Buffer.byteLength(input.body, 'utf8'),
            protectionEstablished ? 'redacted' : 'unavailable',
            sha256Hex(Buffer.from(input.body, 'utf8')),
            input.errorCode ?? code,
            now,
            now,
          );
      });
      return { stored: 'metadata', capture_id: captureId, reason_code: code };
    }
    // Allowed: persist the redacted body to the protected store, then
    // record the payload row. The file is written first so a failed
    // row insert leaves only an unreferenced file, never a row
    // pointing at missing content.
    const effective = Buffer.from(redacted as string, 'utf8').subarray(0, decision.effectiveBytes);
    const captureId = this.deps.ids.newId();
    const ref = `diagnostics/${input.sessionId}/${captureId}.bin`;
    const deadline = new Date(nowMs + policy.payload_ttl_hours * 3_600_000).toISOString();
    mkdirSync(join(this.payloadDir, input.sessionId), { recursive: true, mode: 0o700 });
    writeFileSync(join(this.deps.dataDir, ref), effective, { mode: 0o600 });
    try {
      this.db.write((handle) => {
        handle
          .prepare(
            `INSERT INTO council_diagnostic_capture
               (tenant_id, company_id, session_id, id, record_kind, grant_id,
                policy_schema_version, authorized_by_principal, authorization_kind,
                window_started_at, window_ends_at, capture_window_minutes,
                payload_ttl_hours, max_bytes_per_operation, max_bytes_per_session,
                operation_id, data_class, byte_count, truncated, redaction_status,
                payload_protected_ref, payload_deadline_at, response_hash, error_code,
                captured_at, revoked_at, revoked_by, created_at)
             VALUES (?, ?, ?, ?, 'payload', ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                     NULL, ?, ?, ?, ?, 'redacted', ?, ?, ?, ?, ?, NULL, NULL, ?)`,
          )
          .run(
            envelope.tenant_id,
            envelope.company_id,
            input.sessionId,
            captureId,
            grant.id,
            input.operationId,
            input.dataClass,
            effective.byteLength,
            decision.truncated ? 1 : 0,
            ref,
            deadline,
            sha256Hex(Buffer.from(input.body, 'utf8')),
            input.errorCode ?? null,
            now,
            now,
          );
      });
    } catch (error) {
      rmSync(join(this.deps.dataDir, ref), { force: true });
      throw error;
    }
    return {
      stored: 'payload',
      capture_id: captureId,
      byte_count: effective.byteLength,
      truncated: decision.truncated,
      payload_deadline_at: deadline,
    };
  }

  // ------------------------------------------------------------------ read

  /**
   * Read one captured payload. Access is re-decided at read time: the
   * grant must still be active, the session must not be deleted, and
   * the payload must be inside its TTL deadline. An expired or revoked
   * payload is inaccessible even while its file still exists on disk.
   */
  readPayload(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    captureId: string,
  ): { body: string; byte_count: number; truncated: boolean } {
    assertEnvelopePurpose(envelope, 'diagnostic_read', 'Diagnostic payload read');
    if (this.isDeleted(envelope, sessionId)) throw sessionDeleted(sessionId);
    const row = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT byte_count, truncated, payload_protected_ref, payload_deadline_at,
                  captured_at, grant_id
             FROM council_diagnostic_capture
            WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND id = ?
              AND record_kind = 'payload'`,
        )
        .get(envelope.tenant_id, envelope.company_id, sessionId, captureId),
    ) as
      | {
          byte_count: number;
          truncated: number;
          payload_protected_ref: string;
          payload_deadline_at: string;
          captured_at: string;
          grant_id: string;
        }
      | undefined;
    if (!row) {
      throw new PersistenceError(
        'PERSISTENCE_DIAGNOSTIC_DENIED',
        `No captured diagnostic payload ${captureId} exists for session ${sessionId} in this scope.`,
        { retryable: false },
      );
    }
    const grant = this.db.read((handle) => this.grantRow(handle, envelope, sessionId));
    if (!grant || grant.id !== row.grant_id) {
      throw new PersistenceError(
        'PERSISTENCE_DIAGNOSTIC_DENIED',
        'The diagnostic grant for this payload was revoked. Captured content is inaccessible after revocation.',
        { retryable: false },
      );
    }
    const nowMs = Date.parse(this.deps.clock.nowUtc());
    if (
      isCaptureExpired(Date.parse(row.captured_at), nowMs, grant.payload_ttl_hours) ||
      nowMs >= Date.parse(row.payload_deadline_at)
    ) {
      throw new PersistenceError(
        'PERSISTENCE_DIAGNOSTIC_DENIED',
        'This diagnostic payload has passed its retention deadline and is inaccessible, ahead of physical cleanup.',
        { retryable: false },
      );
    }
    const body = readFileSync(join(this.deps.dataDir, row.payload_protected_ref), 'utf8');
    return { body, byte_count: row.byte_count, truncated: row.truncated === 1 };
  }

  /** Metadata view of a session's captures (never payload bytes). */
  listCaptures(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): Array<Record<string, unknown>> {
    return this.db.read((handle) =>
      handle
        .prepare(
          `SELECT id, record_kind, grant_id, operation_id, data_class, byte_count,
                  truncated, redaction_status, payload_deadline_at, response_hash,
                  error_code, captured_at, revoked_at
             FROM council_diagnostic_capture
            WHERE tenant_id = ? AND company_id = ? AND session_id = ?
            ORDER BY created_at ASC`,
        )
        .all(envelope.tenant_id, envelope.company_id, sessionId),
    ) as Array<Record<string, unknown>>;
  }

  // --------------------------------------------------------------- cleanup

  /**
   * Physical cleanup: delete payload files and rows whose retention
   * deadline has passed, and payload files under revoked grants.
   * Access decisions never depend on this sweep having run.
   */
  sweepExpiredAndRevoked(): { removed: number } {
    const now = this.deps.clock.nowUtc();
    const rows = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT p.tenant_id, p.company_id, p.session_id, p.id, p.payload_protected_ref
             FROM council_diagnostic_capture p
            WHERE p.record_kind = 'payload'
              AND (p.payload_deadline_at <= ?
                   OR EXISTS (SELECT 1 FROM council_diagnostic_capture g
                               WHERE g.tenant_id = p.tenant_id AND g.company_id = p.company_id
                                 AND g.session_id = p.session_id AND g.id = p.grant_id
                                 AND g.record_kind = 'grant' AND g.revoked_at IS NOT NULL))`,
        )
        .all(now),
    ) as Array<{
      tenant_id: string;
      company_id: string;
      session_id: string;
      id: string;
      payload_protected_ref: string;
    }>;
    for (const row of rows) {
      rmSync(join(this.deps.dataDir, row.payload_protected_ref), { force: true });
    }
    this.db.write((handle) => {
      for (const row of rows) {
        handle
          .prepare(
            `DELETE FROM council_diagnostic_capture
              WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND id = ?`,
          )
          .run(row.tenant_id, row.company_id, row.session_id, row.id);
      }
    });
    return { removed: rows.length };
  }

  /** Remove protected payload files by reference (post-deletion sweep). */
  purgePayloadFiles(refs: string[]): void {
    for (const ref of refs) {
      rmSync(join(this.deps.dataDir, ref), { force: true });
    }
  }
}
