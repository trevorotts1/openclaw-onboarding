/**
 * Loopback endpoint acquisition (WER-022).
 *
 * The port-selection contract is the WER-021 front door's, NOT a copy:
 * identity-based reuse, an unrelated listener refused and LEFT RUNNING, and
 * every candidate port's blocker reported. This module only maps that
 * contract into platform refusal codes, so there is exactly one
 * implementation of "which listener is mine" in the runtime.
 *
 * What is added here is the honest platform statement: a free port proves
 * only that the current network namespace can bind it. It never proves the
 * host can reach it, and it never proves a container is reachable from
 * outside (`host.docker.internal` and a fixed port are not evidence).
 */

import type { CouncilFrontDoor } from '../service/front-door.js';
import type { ServiceStartBlocker } from '../service/types.js';
import {
  platformRefusal,
  type PlatformCondition,
  type PlatformRefusal,
  type PlatformRefusalCode,
} from './types.js';

export interface EndpointRefusal {
  code: PlatformRefusalCode;
  condition: PlatformCondition;
  service_code: string;
  port: number | null;
  detail: string;
  recovery: string;
}

export type EndpointAcquisition =
  | {
      kind: 'acquired';
      outcome: 'started' | 'reused';
      origin: string;
      port: number;
      /** True: the caller owns the handle and must stop() it when started. */
      owns_listener: boolean;
    }
  | { kind: 'refused'; code: 'PLATFORM_ENDPOINT_UNAVAILABLE'; refusals: EndpointRefusal[] };

function classifyCode(serviceCode: string): {
  code: PlatformRefusalCode;
  condition: PlatformCondition;
} {
  switch (serviceCode) {
    case 'PORT_IN_USE_UNRELATED':
      return { code: 'PLATFORM_PORT_UNRELATED_LISTENER', condition: 'UNRELATED_LISTENER' };
    case 'SERVICE_HOST_NOT_LOOPBACK':
      return { code: 'PLATFORM_HOST_NOT_LOOPBACK', condition: 'HOST_NOT_LOOPBACK' };
    default:
      return { code: 'PLATFORM_ENDPOINT_UNAVAILABLE', condition: 'ENDPOINT_UNAVAILABLE' };
  }
}

function translate(blocker: ServiceStartBlocker): EndpointRefusal {
  const { code, condition } = classifyCode(blocker.code);
  return {
    code,
    condition,
    service_code: blocker.code,
    port: null,
    detail: blocker.detail,
    recovery: blocker.recovery,
  };
}

/**
 * Start/resolve the front door and report the endpoint it actually owns.
 *
 * A verified matching service is reused (the caller never stops it); an
 * unrelated listener is refused untouched; when no candidate works, every
 * refusal is returned so the caller sees all checked ports.
 */
export async function acquireServiceEndpoint(
  frontDoor: CouncilFrontDoor,
): Promise<EndpointAcquisition> {
  const outcome = await frontDoor.start();

  if (outcome.outcome === 'started' || outcome.outcome === 'reused') {
    return {
      kind: 'acquired',
      outcome: outcome.outcome,
      origin: outcome.origin,
      port: outcome.port,
      owns_listener: outcome.outcome === 'started',
    };
  }

  const refusals = outcome.blockers.map(translate);
  if (refusals.length === 0) {
    refusals.push({
      code: 'PLATFORM_ENDPOINT_UNAVAILABLE',
      condition: 'ENDPOINT_UNAVAILABLE',
      service_code: 'SERVICE_START_REFUSED',
      port: null,
      detail: 'The front door refused to start without naming a blocker.',
      recovery: 'Re-run service start with at least one valid loopback port candidate.',
    });
  }
  return { kind: 'refused', code: 'PLATFORM_ENDPOINT_UNAVAILABLE', refusals };
}

/** A refusal view of the same acquisition, for callers that want one shape. */
export function endpointRefusal(acquisition: EndpointAcquisition): PlatformRefusal | null {
  if (acquisition.kind === 'acquired') return null;
  const first = acquisition.refusals[0];
  const unrelated = acquisition.refusals.some(
    (refusal) => refusal.code === 'PLATFORM_PORT_UNRELATED_LISTENER',
  );
  return platformRefusal({
    code: first.code,
    condition: first.condition,
    detail: acquisition.refusals.map((refusal) => refusal.detail).join(' | '),
    recovery: first.recovery,
    checked: acquisition.refusals.map(
      (refusal) => `${refusal.service_code}${refusal.port === null ? '' : `:${refusal.port}`}`,
    ),
    unknowns: unrelated
      ? ['no free loopback port was found; the unrelated listener was left running']
      : [],
  });
}
