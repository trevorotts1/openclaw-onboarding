/**
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
