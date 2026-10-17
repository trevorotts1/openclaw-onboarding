"""Executable reference contracts for the Signature Launch specification.

These pure functions test the packet's proposed route and metric semantics.
They do not call GHL, create rooms, authorize charges, or implement production
identity/approval checks. The real adapters must validate native evidence.
"""
from dataclasses import dataclass
from math import isfinite
from typing import Dict, Iterable, Mapping, Optional, FrozenSet, Tuple


@dataclass(frozen=True)
class Extras:
    upsell_1: bool = True
    downsell_1: bool = True
    upsell_2: bool = True

    def __post_init__(self) -> None:
        if any(type(v) is not bool for v in (self.upsell_1, self.downsell_1, self.upsell_2)):
            raise ValueError('Extra-offer flags must be booleans.')
        if not self.upsell_1 and (self.downsell_1 or self.upsell_2):
            raise ValueError('This launch profile requires U1 for D1/U2 qualification.')


@dataclass(frozen=True)
class Unit:
    task_id: str
    weight: float
    status: str

    def __post_init__(self) -> None:
        if not self.task_id or not isfinite(self.weight) or self.weight <= 0:
            raise ValueError('Each task requires an ID and finite positive weight.')


def weighted_percent(units: Iterable[Unit], completed_status: str = 'verified') -> float:
    rows = list(units)
    if not rows:
        raise ValueError('No baseline: percentage cannot be calculated.')
    if len({u.task_id for u in rows}) != len(rows):
        raise ValueError('Duplicate task ID would distort the baseline.')
    return 100.0 * sum(u.weight for u in rows if u.status == completed_status) / sum(u.weight for u in rows)


def merge_percent(owner_approved: bool, units: Iterable[Unit]) -> float:
    if type(owner_approved) is not bool:
        raise ValueError('Approval must come from a validated boolean status.')
    if not owner_approved:
        return 0.0
    return weighted_percent(units, 'merged_and_verified')


def hourly_net_pp(before: float, after: float, minutes: float, same_scope: bool = True) -> Optional[float]:
    if not same_scope:
        return None
    if not all(isfinite(x) for x in (before, after, minutes)):
        raise ValueError('Progress samples must be finite.')
    if minutes <= 0 or not 0 <= before <= 100 or not 0 <= after <= 100:
        raise ValueError('Invalid progress sample window/value.')
    return (after - before) / (minutes / 60.0)


SCORE_WEIGHTS = {'useful_capacity': 35, 'ready_dispatch': 25, 'critical_path': 20,
                 'review_flow': 10, 'collision_discipline': 10}


def swarm_score(ratios: Mapping[str, Optional[float]]) -> Tuple[Optional[int], float]:
    if set(ratios) - set(SCORE_WEIGHTS):
        raise ValueError('Unknown score component.')
    weighted = 0.0
    covered = 0
    for name, weight in SCORE_WEIGHTS.items():
        value = ratios.get(name)
        if value is None:
            continue
        if not isfinite(value) or not 0 <= value <= 1:
            raise ValueError('Score ratios must be finite values between zero and one.')
        weighted += weight * value
        covered += weight
    coverage = covered / 100.0
    if coverage < 0.60:
        return None, coverage
    return int(round(100.0 * weighted / covered)), coverage


def resolve_after(stage: str, event: str, purchased: FrozenSet[str], extras: Extras,
                  payment_verified: bool = False) -> Tuple[str, FrozenSet[str]]:
    """Resolve one proposed transition; payment_verified is supplied by a trusted
    adapter in production, never by an untrusted browser/client claim.
    """
    allowed = {'checkout', 'upsell_1', 'downsell_1', 'upsell_2'}
    if stage not in allowed:
        raise ValueError('This helper only models purchase-stage transitions.')
    if stage != 'checkout' and not any(x.startswith('MAIN-') for x in purchased):
        raise ValueError('A verified main purchase is required before extras.')
    if stage == 'upsell_1' and not extras.upsell_1:
        raise ValueError('U1 is disabled.')
    if stage == 'downsell_1' and (not extras.downsell_1 or 'U1' in purchased):
        raise ValueError('D1 is disabled or incompatible with accepted U1.')
    if stage == 'upsell_2' and (not extras.upsell_2 or not ({'U1', 'D1'} & purchased)):
        raise ValueError('U2 requires enabled status and successful U1 or D1.')
    if event in {'payment_pending', 'payment_failed', 'requires_customer_action'}:
        return stage, purchased
    if event == 'payment_succeeded':
        if not payment_verified:
            raise ValueError('A clicked button or redirect does not prove payment.')
        if stage == 'checkout':
            if not any(x.startswith('MAIN-') for x in purchased):
                raise ValueError('Native main purchase evidence is missing.')
            return ('upsell_1' if extras.upsell_1 else 'thank_you'), purchased
        slot = {'upsell_1': 'U1', 'downsell_1': 'D1', 'upsell_2': 'U2'}[stage]
        updated = purchased | {slot}
        if {'U1', 'D1'} <= updated:
            raise ValueError('U1 and D1 are mutually exclusive in this profile.')
        target = 'upsell_2' if stage in {'upsell_1', 'downsell_1'} and extras.upsell_2 else 'thank_you'
        return target, frozenset(updated)
    if event == 'explicit_decline':
        if stage == 'checkout':
            raise ValueError('Abandoned initial checkout is not a paid thank-you path.')
        target = 'downsell_1' if stage == 'upsell_1' and extras.downsell_1 else 'thank_you'
        return target, purchased
    raise ValueError('Unknown event; do not infer a decline or success.')


def validate_graph(graph: Mapping) -> None:
    nodes = graph['nodes']
    ids = [n['page_id'] for n in nodes]
    roles = [n['role'] for n in nodes]
    if len(set(ids)) != len(ids) or len(set(roles)) != len(roles):
        raise ValueError('Duplicate node or role, including duplicate U2.')
    if roles.count('landing') != 1 or roles.count('thank_you') != 1:
        raise ValueError('One landing and final thank-you required.')
    adjacency: Dict[str, list] = {i: [] for i in ids}
    for edge in graph['edges']:
        if edge['from'] not in adjacency or edge['to'] not in adjacency:
            raise ValueError('Dangling edge.')
        adjacency[edge['from']].append(edge['to'])
    entry = next(n['page_id'] for n in nodes if n['role'] == 'landing')
    terminal = next(n['page_id'] for n in nodes if n['role'] == 'thank_you')
    seen, active = set(), set()
    def visit(node: str) -> None:
        if node in active:
            raise ValueError('Progression graph contains a cycle.')
        if node in seen:
            return
        active.add(node)
        if not adjacency[node] and node != terminal:
            raise ValueError('Nonterminal dead end.')
        for target in adjacency[node]:
            visit(target)
        active.remove(node)
        seen.add(node)
    visit(entry)
    if seen != set(ids):
        raise ValueError('Unreachable enabled node.')
