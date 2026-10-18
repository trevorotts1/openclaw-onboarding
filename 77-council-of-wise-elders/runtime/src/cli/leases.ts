/**
 * Operation leases (CWE-004 foundation; production worker lifecycle
 * owned by CWE-027; durable wiring WER-010).
 *
 * `DurableOperationLeaseProvider` is the CLI host's lease provider. A
 * claim raises the session's journaled `lease_epoch` with a
 * compare-and-swap write through CWE-006's repository layer, which is
 * exactly the fencing generation CWE-028's budget service reads before
 * it reserves, settles, releases, or renews. The generation therefore
 * lives in the durable store, never in a process-local variable: a
 * stale holder presenting an older epoch is fenced out of every
 * spending commit even if it kept its lease object.
 *
 * `InProcessLeaseProvider` remains the foundation form for sessions
 * the durable authorization store does not hold (CWE-004 synthetic
 * fixtures); the durable provider routes to it only when the session is
 * absent from that store.
 *
 * In-process operation leases (CWE-004 foundation; production worker
 * lifecycle owned by CWE-027). Implements the council operation lease of
 * directive Section 15.8, which is deliberately separate from the host
 * scheduler's observed 90-second job lease:
 *
 * - TTL 60 seconds, heartbeat every 15 seconds while the owner is alive.
 * - Every claim raises a monotonically increasing fencing epoch for the
 *   operation key; only the current epoch may commit.
 * - Losing a lease (expiry or a newer claim) fences out late results:
 *   a stale worker can never publish or release money twice.
 * - Lease renewal never renews a spending grant or resets retry
 *   counters; those live in the budget ledger and the grant service.
 */

import type { Clock, SessionStateRecord } from '../contracts/index.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import type { CouncilRepositories } from '../persistence/repositories.js';
import { CouncilError } from './errors.js';
import type { CapacityLeaseProvider, OperationLease } from './host-ports.js';

export const OPERATION_LEASE_TTL_MS = 60_000;
export const OPERATION_LEASE_HEARTBEAT_MS = 15_000;

interface LeaseRecord extends OperationLease {
  released: boolean;
}

export class InProcessLeaseProvider implements CapacityLeaseProvider {
  private readonly leases = new Map<string, LeaseRecord>();
  private readonly now: () => number;

  constructor(now: () => number = () => Date.now()) {
    this.now = now;
  }

  claim(
    operation_key: string,
    owner_id: string,
    ttl_ms: number = OPERATION_LEASE_TTL_MS,
  ): OperationLease {
    const previous = this.leases.get(operation_key);
    const epoch = (previous?.epoch ?? 0) + 1;
    const lease: LeaseRecord = {
      operation_key,
      owner_id,
      epoch,
      expires_at_ms: this.now() + ttl_ms,
      released: false,
    };
    this.leases.set(operation_key, lease);
    return { ...lease };
  }

  private current(lease: OperationLease): LeaseRecord {
    const record = this.leases.get(lease.operation_key);
    if (
      !record ||
      record.released ||
      record.epoch !== lease.epoch ||
      record.owner_id !== lease.owner_id
    ) {
      throw new CouncilError(
        'COUNCIL_LEASE_LOST',
        `Lease for operation ${lease.operation_key} is no longer current (epoch ${lease.epoch} is fenced out).`,
        {
          retryable: false,
          action:
            'Discard the late result. The current lease owner is the only writer for this operation.',
          exitCode: 3,
        },
      );
    }
    if (this.now() > record.expires_at_ms) {
      throw new CouncilError(
        'COUNCIL_LEASE_LOST',
        `Lease for operation ${lease.operation_key} expired at ${new Date(record.expires_at_ms).toISOString()}.`,
        {
          retryable: false,
          action: 'Reclaim the operation with a fresh lease if the work is still wanted.',
          exitCode: 3,
        },
      );
    }
    return record;
  }

  heartbeat(lease: OperationLease): OperationLease {
    const record = this.current(lease);
    record.expires_at_ms = this.now() + OPERATION_LEASE_TTL_MS;
    return { ...record };
  }

  assertCurrent(lease: OperationLease): void {
    this.current(lease);
  }

  release(lease: OperationLease): void {
    const record = this.leases.get(lease.operation_key);
    if (record && record.epoch === lease.epoch && record.owner_id === lease.owner_id) {
      record.released = true;
    }
  }
}

export interface DurableLeaseProviderOptions {
  repositories: CouncilRepositories;
  envelope: AuthorizationEnvelope;
  clock: Clock;
  /**
   * Resolve the session an operation key belongs to. The engine's keys
   * are scope-qualified and include the session id; a host supplies its
   * own derivation here rather than having the lease layer guess.
   */
  sessionIdForOperation(operationKey: string): string | null;
  nowMs?: () => number;
  ttlMs?: number;
  /**
   * Foundation provider for synthetic sessions the durable
   * authorization store never mirrored. Never used for a durable
   * session record.
   */
  fallback?: CapacityLeaseProvider;
}

interface HeldLease {
  owner_id: string;
  epoch: number;
  expires_at_ms: number;
  durable: boolean;
}

/**
 * Durable operation lease provider (Section 15.8).
 *
 * Claiming writes the next fencing generation into the session's
 * journaled state record (compare-and-swap), so the generation is
 * durable and is the SAME value CWE-028's budget service fences on.
 * Renewal rewrites the journaled state record (same generation, new
 * expiry) and never touches spending grants or retry counters.
 *
 * A holder that lost its lease — a newer claim, expiry, or a restart —
 * is refused by `assertCurrent`, and every budget finalization it
 * attempts is independently refused by the service's epoch fence.
 */
export class DurableOperationLeaseProvider implements CapacityLeaseProvider {
  private readonly held = new Map<string, HeldLease>();
  private readonly repositories: CouncilRepositories;
  private readonly envelope: AuthorizationEnvelope;
  private readonly clock: Clock;
  private readonly sessionIdForOperation: (operationKey: string) => string | null;
  private readonly nowMs: () => number;
  private readonly ttlMs: number;
  private readonly fallback?: CapacityLeaseProvider;

  constructor(options: DurableLeaseProviderOptions) {
    this.repositories = options.repositories;
    this.envelope = options.envelope;
    this.clock = options.clock;
    this.sessionIdForOperation = options.sessionIdForOperation;
    this.nowMs = options.nowMs ?? (() => Date.now());
    this.ttlMs = options.ttlMs ?? OPERATION_LEASE_TTL_MS;
    this.fallback = options.fallback;
  }

  /** The session's current DURABLE generation, or null when unmirrored. */
  currentEpoch(sessionId: string): number | null {
    const session = this.repositories.getSession(this.envelope, sessionId);
    return session ? session.state.lease_epoch : null;
  }

  claim(
    operation_key: string,
    owner_id: string,
    ttl_ms: number = this.ttlMs,
  ): OperationLease {
    const sessionId = this.sessionIdForOperation(operation_key);
    const session = sessionId
      ? this.repositories.getSession(this.envelope, sessionId)
      : null;
    if (!sessionId || !session) {
      if (this.fallback) {
        const lease = this.fallback.claim(operation_key, owner_id, ttl_ms);
        this.held.set(operation_key, {
          owner_id: lease.owner_id,
          epoch: lease.epoch,
          expires_at_ms: lease.expires_at_ms,
          durable: false,
        });
        return lease;
      }
      throw new CouncilError(
        'COUNCIL_LEASE_LOST',
        `Operation ${operation_key} names no session in the durable authorization store, so no fencing generation can be raised.`,
        {
          retryable: false,
          action:
            'Mirror the session into the authorization store before claiming an operation lease.',
          exitCode: 3,
        },
      );
    }
    const epoch = session.state.lease_epoch + 1;
    const expiresAt = this.nowMs() + ttl_ms;
    const record: SessionStateRecord = {
      ...session.state,
      lease_epoch: epoch,
      state_version: session.state.state_version + 1,
      updated_at: this.clock.nowUtc(),
    };
    try {
      this.repositories.writeStateRecord(
        this.envelope,
        record,
        session.state.state_version,
        {
          type: 'session_state_changed',
          payload: {
            reason: 'operation_lease_claimed',
            operation_key,
            owner_id,
            lease_epoch: epoch,
            expires_at_ms: expiresAt,
          },
        },
      );
    } catch (error) {
      // The compare-and-swap lost the race to another claimer: exactly
      // one claimant may own a generation.
      throw new CouncilError(
        'COUNCIL_LEASE_LOST',
        `Lease for operation ${operation_key} could not be claimed: the session fencing generation changed underneath this claimant (${error instanceof Error ? error.message : String(error)}).`,
        {
          retryable: true,
          action: 'Re-read the session and reclaim the operation if the work is still wanted.',
          exitCode: 3,
        },
      );
    }
    this.held.set(operation_key, {
      owner_id,
      epoch,
      expires_at_ms: expiresAt,
      durable: true,
    });
    return {
      operation_key,
      owner_id,
      epoch,
      expires_at_ms: expiresAt,
    };
  }

  private current(lease: OperationLease): HeldLease {
    const held = this.held.get(lease.operation_key);
    if (!held) {
      throw new CouncilError(
        'COUNCIL_LEASE_LOST',
        `Lease for operation ${lease.operation_key} is not held by this worker (epoch ${lease.epoch}).`,
        {
          retryable: false,
          action:
            'Discard the late result. Only the current lease owner may write.',
          exitCode: 3,
        },
      );
    }
    if (held.owner_id !== lease.owner_id || held.epoch !== lease.epoch) {
      throw new CouncilError(
        'COUNCIL_LEASE_LOST',
        `Lease for operation ${lease.operation_key} is fenced out (presented epoch ${lease.epoch}, held epoch ${held.epoch}).`,
        {
          retryable: false,
          action:
            'Discard the late result. The current lease owner is the only writer for this operation.',
          exitCode: 3,
        },
      );
    }
    if (this.nowMs() > held.expires_at_ms) {
      throw new CouncilError(
        'COUNCIL_LEASE_LOST',
        `Lease for operation ${lease.operation_key} expired at ${new Date(held.expires_at_ms).toISOString()}.`,
        {
          retryable: false,
          action: 'Reclaim the operation with a fresh lease if the work is still wanted.',
          exitCode: 3,
        },
      );
    }
    const sessionId = this.heldSession(lease.operation_key);
    const durableEpoch = sessionId ? this.currentEpoch(sessionId) : null;
    if (sessionId && durableEpoch !== null && durableEpoch !== held.epoch) {
      throw new CouncilError(
        'COUNCIL_LEASE_LOST',
        `Lease for operation ${lease.operation_key} presented generation ${held.epoch}, but the durable session generation is ${durableEpoch}. A stale generation cannot write.`,
        {
          retryable: false,
          action:
            'Discard the late result; only the current generation may commit.',
          exitCode: 3,
        },
      );
    }
    return held;
  }

  private heldSession(operationKey: string): string | null {
    return this.sessionIdForOperation(operationKey);
  }

  heartbeat(lease: OperationLease): OperationLease {
    const existing = this.held.get(lease.operation_key);
    if (existing && !existing.durable) {
      const renewed = this.fallback!.heartbeat(lease);
      existing.expires_at_ms = renewed.expires_at_ms;
      return renewed;
    }
    const held = this.current(lease);
    const sessionId = this.heldSession(lease.operation_key);
    const session = sessionId
      ? this.repositories.getSession(this.envelope, sessionId)
      : null;
    if (!session) {
      throw new CouncilError(
        'COUNCIL_LEASE_LOST',
        `Lease for operation ${lease.operation_key} has no durable session record to renew.`,
        { retryable: false, exitCode: 3 },
      );
    }
    const expiresAt = this.nowMs() + this.ttlMs;
    try {
      this.repositories.writeStateRecord(
        this.envelope,
        {
          ...session.state,
          state_version: session.state.state_version + 1,
          updated_at: this.clock.nowUtc(),
        },
        session.state.state_version,
        {
          type: 'session_state_changed',
          payload: {
            reason: 'operation_lease_heartbeat',
            operation_key: lease.operation_key,
            owner_id: lease.owner_id,
            lease_epoch: held.epoch,
            expires_at_ms: expiresAt,
          },
        },
      );
    } catch (error) {
      throw new CouncilError(
        'COUNCIL_LEASE_LOST',
        `Lease for operation ${lease.operation_key} could not be renewed: ${error instanceof Error ? error.message : String(error)}.`,
        { retryable: true, exitCode: 3 },
      );
    }
    held.expires_at_ms = expiresAt;
    return {
      operation_key: lease.operation_key,
      owner_id: lease.owner_id,
      epoch: lease.epoch,
      expires_at_ms: expiresAt,
    };
  }

  assertCurrent(lease: OperationLease): void {
    const held = this.held.get(lease.operation_key);
    if (held && !held.durable) {
      this.fallback!.assertCurrent(lease);
      return;
    }
    this.current(lease);
  }

  release(lease: OperationLease): void {
    const held = this.held.get(lease.operation_key);
    if (!held) return;
    if (!held.durable) {
      this.fallback!.release(lease);
      this.held.delete(lease.operation_key);
      return;
    }
    if (held.owner_id === lease.owner_id && held.epoch === lease.epoch) {
      this.held.delete(lease.operation_key);
    }
  }
}
