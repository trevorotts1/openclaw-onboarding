// Approval issuer trust (MG-025, Directive Section 16.7).
//
// "Do not invent a trust boundary." An approval counts only when three
// things hold at once:
//
// 1. Its actor is a recognized issuer in a registry the trusted
//    workflow controls. The registry and the keyring live OUTSIDE the
//    job package, supplied through MOTION_ISSUER_REGISTRY and
//    MOTION_APPROVER_KEYS (paths to JSON files). The built-in defaults
//    recognize exactly one issuer, the fixture test issuer, so a
//    production job on an installation with no configured trust source
//    reports MG_APPROVAL_AUTHORITY_UNAVAILABLE instead of trusting
//    whatever JSON it finds (Section 16.7).
// 2. Its source event is a detached approval event artifact inside the
//    job package, named by the approval's source_event_ref and bound
//    into the approval's artifact_refs with the event file's exact
//    sha256. The event repeats the approval's binding fields (job,
//    company, scope, decision, revision, actor) and the artifact refs
//    the approver approved (the approval record carries those same
//    refs plus the event binding entry; an event cannot bind its own
//    hash).
// 3. The event carries an HMAC-SHA256 signature over its canonical
//    JSON, keyed with the issuer's key from the keyring. The key never
//    lives in the job package or in this repository for production
//    issuers: the trusted workflow holds it and signs events at import
//    time. An authoring agent can write any JSON it likes into a job
//    directory; without the issuer key it cannot produce an event the
//    evaluator accepts, so an owner approval cannot be forged in an
//    arbitrary JSON file.
//
// The fixture test issuer's key is a published test constant. It is
// valid only for fixture-context jobs under the fixture_only policy,
// its gate results are labeled diagnostic, and production rejects the
// test issuer outright (the MG-010 pattern, generalized).

import { createHmac, timingSafeEqual } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { canonicalJson } from "./canonical";

export const FIXTURE_TEST_ISSUER = "fixture-test-issuer";
export const FIXTURE_TEST_KEY = "fixture-test-key-not-a-secret";
export const POLICY_FIXTURE_ONLY = "fixture_only";
export const POLICY_PRODUCTION = "owner_or_existing_authorized_reviewer";

export type IssuerRole = "owner" | "authorized_reviewer" | "test";

export interface IssuerEntry {
  actorId: string;
  role: IssuerRole;
  policies: string[];
}

export interface IssuerTrust {
  registry: IssuerEntry[];
  keyring: Record<string, string>;
  registrySource: string;
  keyringSource: string;
}

const DEFAULT_REGISTRY: IssuerEntry[] = [
  { actorId: FIXTURE_TEST_ISSUER, role: "test", policies: [POLICY_FIXTURE_ONLY] },
];
const DEFAULT_KEYRING: Record<string, string> = {
  [FIXTURE_TEST_ISSUER]: FIXTURE_TEST_KEY,
};

type Doc = Record<string, unknown>;

function isDoc(value: unknown): value is Doc {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readJsonFile(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8"));
}

/**
 * Load the issuer registry and keyring. Environment overrides point at
 * files controlled by the trusted workflow; anything unreadable or
 * malformed falls back to the built-in fixture-only defaults and says
 * so in the source labels, so a misconfigured installation fails
 * closed (production authority unavailable) rather than open.
 */
export function loadIssuerTrust(env: NodeJS.ProcessEnv = process.env): IssuerTrust {
  let registry = DEFAULT_REGISTRY;
  let registrySource = "built-in fixture-only defaults";
  const registryPath = env.MOTION_ISSUER_REGISTRY;
  if (registryPath && existsSync(registryPath)) {
    try {
      const parsed = readJsonFile(registryPath);
      if (Array.isArray(parsed)) {
        const entries: IssuerEntry[] = [];
        for (const entry of parsed) {
          if (
            isDoc(entry) &&
            typeof entry.actor_id === "string" &&
            (entry.role === "owner" || entry.role === "authorized_reviewer" || entry.role === "test") &&
            Array.isArray(entry.policies)
          ) {
            entries.push({
              actorId: entry.actor_id,
              role: entry.role,
              policies: entry.policies.filter((p): p is string => typeof p === "string"),
            });
          }
        }
        registry = entries;
        registrySource = registryPath;
      }
    } catch {
      registry = DEFAULT_REGISTRY;
      registrySource = "built-in fixture-only defaults (registry file unreadable)";
    }
  }

  let keyring = DEFAULT_KEYRING;
  let keyringSource = "built-in fixture test key only";
  const keyringPath = env.MOTION_APPROVER_KEYS;
  if (keyringPath && existsSync(keyringPath)) {
    try {
      const parsed = readJsonFile(keyringPath);
      if (isDoc(parsed)) {
        const keys: Record<string, string> = {};
        for (const [actor, key] of Object.entries(parsed)) {
          if (typeof key === "string" && key.length > 0) keys[actor] = key;
        }
        keyring = keys;
        keyringSource = keyringPath;
      }
    } catch {
      keyring = DEFAULT_KEYRING;
      keyringSource = "built-in fixture test key only (keyring file unreadable)";
    }
  }

  return { registry, keyring, registrySource, keyringSource };
}

/** The detached approval event artifact (see the header). The
 * signature covers every field except itself. */
export interface ApprovalEvent {
  event_id: string;
  approval_id: string;
  job_id: string;
  company_id: string;
  scope: string;
  decision: string;
  subject_revision: string;
  actor_id: string;
  artifact_refs: Array<{ path: string; sha256: string }>;
  signature: string;
}

/** The event fields the signature covers, in canonical form. */
export function eventSigningPayload(event: Omit<ApprovalEvent, "signature">): string {
  return canonicalJson({
    actor_id: event.actor_id,
    approval_id: event.approval_id,
    artifact_refs: event.artifact_refs,
    company_id: event.company_id,
    decision: event.decision,
    event_id: event.event_id,
    job_id: event.job_id,
    scope: event.scope,
    subject_revision: event.subject_revision,
  });
}

/** Sign an approval event with an issuer key. Called by the trusted
 * workflow at import time, and by tests with test keys. */
export function signApprovalEvent(event: Omit<ApprovalEvent, "signature">, key: string): ApprovalEvent {
  const signature = createHmac("sha256", key).update(eventSigningPayload(event), "utf8").digest("hex");
  return { ...event, signature };
}

/** Verify an event's signature against the issuer key, in constant time. */
export function verifyApprovalEventSignature(event: ApprovalEvent, key: string): boolean {
  const expected = createHmac("sha256", key)
    .update(eventSigningPayload(event), "utf8")
    .digest("hex");
  const a = Buffer.from(expected, "utf8");
  const b = Buffer.from(event.signature ?? "", "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}
