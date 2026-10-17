/**
 * Runtime capacity admission (CWE-028, directive Sections 13, 15.7,
 * and 34.3: queue/capacity.ts is owned by CWE-028; CWE-027 builds
 * durable scheduling against this service and explicitly excludes
 * this file).
 *
 * Capacity is runtime state, deliberately separate from the durable
 * budget ledger: it bounds how many provider operations may be IN
 * FLIGHT at once, across sessions, while the budget service
 * (src/budgets) bounds how much may be SPENT. A slot here is admission
 * to run, not money; acquiring a slot reserves no budget, and
 * releasing a slot refunds nothing. The two compose at dispatch:
 * reserve budget first (durable, fenced), then acquire capacity,
 * then dispatch; on any failure after admission, release the slot.
 *
 * Fairness (Section 15.7): work is admitted in two classes, 'private'
 * and 'company', mirroring session visibility. A defined minimum
 * share of the total slots (private_reserved_slots) can only ever be
 * taken by private work: company admissions are capped at
 * total_slots - private_reserved_slots no matter how long company
 * work stays busy, so a continuously busy company scope cannot starve
 * private scopes of their minimum share. Private work may use any
 * free slot, including the reserved share.
 *
 * Full means full: when no slot is available for the caller's class,
 * tryAcquire returns a typed CAPACITY_FULL decision. Work is never
 * queued unboundedly inside this service and never silently dropped:
 * the caller sees the refusal, the counts that caused it, and decides
 * (surface it, retry later, or cancel something) with full
 * information. Scheduling and retry policy belong to CWE-027.
 *
 * Cancellation frees capacity immediately: release() and
 * cancelScope() remove slots synchronously, in the same call, not at
 * the next sweep. A slot also carries a TTL aligned with the
 * operation lease (60 seconds, Section 15.8) so a worker that dies
 * without releasing cannot hold capacity forever; heartbeat()
 * renews a live slot, and expired slots are reclaimed lazily on the
 * next admission or explicitly via sweepExpired(). Restart resets
 * capacity to empty, which is correct: no operation of a dead process
 * is still running, and budget durability lives in the budget
 * service, not here.
 */

import { OPERATION_LEASE_TTL_MS } from '../cli/leases.js';
import { BudgetCapacityError } from '../budgets/errors.js';

export type CapacityClass = 'private' | 'company';

export interface CapacityConfig {
  /** Total concurrent operations admitted across all classes. */
  total_slots: number;
  /**
   * Slots only private work may take: the Section 15.7 minimum share
   * company work can never consume. Must leave at least one slot
   * reachable by company work.
   */
  private_reserved_slots: number;
  /** Slot TTL in milliseconds; defaults to the operation lease TTL. */
  slot_ttl_ms?: number;
}

export interface CapacityToken {
  token_id: string;
  operation_key: string;
  work_class: CapacityClass;
  /** Opaque scope identity (for example tenant:company:installation). */
  scope_key: string;
  acquired_at_ms: number;
  expires_at_ms: number;
}

export type CapacityDecision =
  | { admitted: true; token: CapacityToken }
  | {
      admitted: false;
      code: 'CAPACITY_FULL';
      work_class: CapacityClass;
      /** Slots currently held by the caller's class. */
      class_in_use: number;
      /** The class ceiling that refused this admission. */
      class_limit: number;
      total_in_use: number;
      total_slots: number;
      action: string;
    };

export interface CapacityUsage {
  total_in_use: number;
  total_slots: number;
  by_class: Record<CapacityClass, number>;
  class_limits: Record<CapacityClass, number>;
  by_scope: Record<string, number>;
}

/** Default composition values; hosts override through config. */
export const DEFAULT_CAPACITY_CONFIG: CapacityConfig = {
  total_slots: 9,
  private_reserved_slots: 3,
  slot_ttl_ms: OPERATION_LEASE_TTL_MS,
};

let fallbackTokenCounter = 0;

export class RuntimeCapacity {
  private readonly totalSlots: number;
  private readonly privateReservedSlots: number;
  private readonly slotTtlMs: number;
  private readonly nowMs: () => number;
  private readonly newTokenId: () => string;
  private readonly slots = new Map<string, CapacityToken>();

  constructor(
    config: CapacityConfig = DEFAULT_CAPACITY_CONFIG,
    deps: { nowMs?: () => number; newTokenId?: () => string } = {},
  ) {
    if (
      !Number.isSafeInteger(config.total_slots) ||
      config.total_slots < 1 ||
      !Number.isSafeInteger(config.private_reserved_slots) ||
      config.private_reserved_slots < 0 ||
      config.private_reserved_slots >= config.total_slots
    ) {
      throw new BudgetCapacityError(
        'CAPACITY_CONFIG_INVALID',
        `Capacity requires total_slots >= 1 and 0 <= private_reserved_slots < total_slots; got total_slots ${config.total_slots} and private_reserved_slots ${config.private_reserved_slots}. A private reserve that swallows every slot would starve company work entirely, which is the mirror image of the Section 15.7 failure.`,
        {
          retryable: false,
          action: 'Correct the capacity configuration and rebuild the service.',
        },
      );
    }
    this.totalSlots = config.total_slots;
    this.privateReservedSlots = config.private_reserved_slots;
    this.slotTtlMs = config.slot_ttl_ms ?? OPERATION_LEASE_TTL_MS;
    if (!Number.isSafeInteger(this.slotTtlMs) || this.slotTtlMs < 1) {
      throw new BudgetCapacityError(
        'CAPACITY_CONFIG_INVALID',
        `slot_ttl_ms must be a positive integer; got ${this.slotTtlMs}.`,
        { retryable: false },
      );
    }
    this.nowMs = deps.nowMs ?? (() => Date.now());
    this.newTokenId =
      deps.newTokenId ??
      (() => `capacity-token-${(fallbackTokenCounter += 1)}`);
  }

  /** The admission ceiling for a class (Section 15.7 fairness rule). */
  classLimit(workClass: CapacityClass): number {
    return workClass === 'company'
      ? this.totalSlots - this.privateReservedSlots
      : this.totalSlots;
  }

  /**
   * Admit one operation, or refuse with a typed CAPACITY_FULL result.
   * Idempotent per operation_key: re-acquiring a live operation
   * returns its existing token instead of consuming a second slot.
   */
  tryAcquire(input: {
    operation_key: string;
    work_class: CapacityClass;
    scope_key: string;
  }): CapacityDecision {
    this.sweepExpired();
    const existing = this.slots.get(input.operation_key);
    if (existing) return { admitted: true, token: { ...existing } };
    const usage = this.usage();
    const classLimit = this.classLimit(input.work_class);
    const classInUse = usage.by_class[input.work_class];
    if (classInUse >= classLimit || usage.total_in_use >= this.totalSlots) {
      return {
        admitted: false,
        code: 'CAPACITY_FULL',
        work_class: input.work_class,
        class_in_use: classInUse,
        class_limit: classLimit,
        total_in_use: usage.total_in_use,
        total_slots: this.totalSlots,
        action:
          input.work_class === 'company'
            ? 'Company capacity is at its fairness ceiling. Private minimum share is protected and cannot be borrowed; retry when company work drains or cancel running company work.'
            : 'All capacity slots are in use. Retry when an operation finishes or is cancelled; nothing was queued or dropped silently.',
      };
    }
    const now = this.nowMs();
    const token: CapacityToken = {
      token_id: this.newTokenId(),
      operation_key: input.operation_key,
      work_class: input.work_class,
      scope_key: input.scope_key,
      acquired_at_ms: now,
      expires_at_ms: now + this.slotTtlMs,
    };
    this.slots.set(input.operation_key, token);
    return { admitted: true, token: { ...token } };
  }

  /** Renew a live slot's TTL (the operation lease heartbeat cadence). */
  heartbeat(tokenId: string): CapacityToken | null {
    for (const token of this.slots.values()) {
      if (token.token_id !== tokenId) continue;
      if (token.expires_at_ms <= this.nowMs()) {
        this.slots.delete(token.operation_key);
        return null;
      }
      token.expires_at_ms = this.nowMs() + this.slotTtlMs;
      return { ...token };
    }
    return null;
  }

  /** Free a slot immediately. Returns false when the token is unknown. */
  release(tokenId: string): boolean {
    for (const token of this.slots.values()) {
      if (token.token_id === tokenId) {
        this.slots.delete(token.operation_key);
        return true;
      }
    }
    return false;
  }

  /**
   * Free every slot held by one scope (session cancellation). The
   * capacity is available to new admissions in the same tick; returns
   * how many slots were freed.
   */
  cancelScope(scopeKey: string): number {
    let freed = 0;
    for (const token of [...this.slots.values()]) {
      if (token.scope_key === scopeKey) {
        this.slots.delete(token.operation_key);
        freed += 1;
      }
    }
    return freed;
  }

  /** Reclaim slots whose TTL lapsed without a release or heartbeat. */
  sweepExpired(): number {
    const now = this.nowMs();
    let freed = 0;
    for (const token of [...this.slots.values()]) {
      if (token.expires_at_ms <= now) {
        this.slots.delete(token.operation_key);
        freed += 1;
      }
    }
    return freed;
  }

  /** Current usage, after reclaiming expired slots. */
  usage(): CapacityUsage {
    this.sweepExpired();
    const byClass: Record<CapacityClass, number> = { private: 0, company: 0 };
    const byScope: Record<string, number> = {};
    for (const token of this.slots.values()) {
      byClass[token.work_class] += 1;
      byScope[token.scope_key] = (byScope[token.scope_key] ?? 0) + 1;
    }
    return {
      total_in_use: this.slots.size,
      total_slots: this.totalSlots,
      by_class: byClass,
      class_limits: {
        private: this.classLimit('private'),
        company: this.classLimit('company'),
      },
      by_scope: byScope,
    };
  }
}
