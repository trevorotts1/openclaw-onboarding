#!/usr/bin/env python3
"""verify-model-pins.py — catch unresolvable agent model pins BEFORE they kill an agent.

WHY THIS EXISTS
---------------
Nothing in the stack validates a model pin between the moment it is written and
the moment an agent dies on it. Not `openclaw config validate`, not `doctor`,
not any health check. A box can carry eight dead department heads and report
perfectly healthy, because a bad pin is only discovered when that specific
department is finally handed real work — which can be months later.

Live incident 2026-07-31: a client's Web Development head was pinned to
`ollama/kimi-k2.6:cloud` on a box that registers `ollama-cloud`, not `ollama`.
OpenClaw fell through to the IMPLICIT local Ollama provider (127.0.0.1:11434),
nothing was listening, and the agent died 2 ms after dispatch — twice — with
"Unknown model ... Ollama requires authentication". That auth wording sent two
escalations chasing the client's credentials, which were fine the entire time.

WHAT IT CHECKS (read-only by default)
-------------------------------------
  1. UNREGISTERED PROVIDER — pin's provider prefix is not in models.providers.
     This is the fatal one: 'ollama/x' on an ollama-cloud box silently means
     "local daemon" and cannot resolve.
  2. NOT ALLOWLISTED — pin is absent from agents.defaults.models. Treated as a
     WARNING, not an error: the allowlist behaves as a catalog on some builds
     and such pins can still resolve. Verified live across 23 boxes.
  3. NO FALLBACK CHAIN (AGENTS.md N31) — a bare-string model bypasses fallbacks
     entirely, so one provider hiccup is fatal instead of survivable. This is
     what turns a single bad pin into a company-wide outage.
  4. ALL-OLLAMA CHAIN — every rung on one provider. An Ollama Cloud cap/429 is
     ACCOUNT-level, so the whole chain fails as a single unit.
  5. ANTHROPIC PIN — client boxes must never pin Anthropic models (cost
     doctrine). Reported separately.

EXIT CODES:  0 = clean (or warnings only)   1 = fatal pins found   2 = bad usage
Use --strict to also fail on warnings.
"""
import argparse, json, os, sys

ANTHROPIC_MARKERS = ('anthropic/', 'claude-')
OLLAMA_FAMILY = {'ollama', 'ollama-cloud'}


def provider_of(mid):
    return mid.split('/', 1)[0] if isinstance(mid, str) and '/' in mid else None


def refs_of(model):
    """Every model id referenced by an agent's model field (string or object)."""
    if isinstance(model, str):
        return [model]
    if isinstance(model, dict):
        out = []
        if model.get('primary'):
            out.append(model['primary'])
        out += [f for f in (model.get('fallbacks') or []) if isinstance(f, str)]
        return out
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default=os.path.expanduser('~/.openclaw/openclaw.json'))
    ap.add_argument('--json', action='store_true', help='machine-readable output')
    ap.add_argument('--strict', action='store_true', help='exit 1 on warnings too')
    args = ap.parse_args()

    if not os.path.exists(args.config):
        print(f"verify-model-pins: no config at {args.config}", file=sys.stderr)
        return 2
    try:
        cfg = json.load(open(args.config))
    except Exception as e:
        print(f"verify-model-pins: unparsable config: {e}", file=sys.stderr)
        return 2

    agents = cfg.get('agents') or {}
    lst = agents.get('list') or []
    defs = agents.get('defaults') or {}
    allow = set((defs.get('models') or {}).keys())
    provs = set(((cfg.get('models') or {}).get('providers') or {}).keys())

    fatal, warn = [], []

    def inspect(label, model):
        for mid in refs_of(model):
            p = provider_of(mid)
            if p is None:
                warn.append((label, mid, 'malformed id (no provider prefix)'))
                continue
            if p not in provs:
                # the fatal class: unregistered provider. 'ollama' additionally
                # resolves to the implicit LOCAL daemon, which is worse than a
                # clean failure because the error message blames authentication.
                extra = ' -> falls through to IMPLICIT LOCAL daemon 127.0.0.1:11434' if p == 'ollama' else ''
                fatal.append((label, mid, f'provider "{p}" NOT registered on this box{extra}'))
            elif mid not in allow:
                warn.append((label, mid, 'not in agents.defaults.models allowlist'))
            if any(m in mid for m in ANTHROPIC_MARKERS):
                warn.append((label, mid, 'ANTHROPIC pin on a client box (cost doctrine)'))

    no_fallback, all_ollama = [], []

    for i, a in enumerate(lst):
        label = f'agents.list[{i}]:{a.get("id") or "?"}'
        m = a.get('model')
        if m is None:
            continue
        inspect(label, m)
        if isinstance(m, str):
            no_fallback.append(label)
        elif isinstance(m, dict):
            chain = refs_of(m)
            if len(chain) <= 1:
                no_fallback.append(label)
            elif chain and all(provider_of(x) in OLLAMA_FAMILY for x in chain):
                all_ollama.append(label)

    for key, blk in (('agents.defaults.model', defs.get('model')),
                     ('agents.defaults.subagents.model', (defs.get('subagents') or {}).get('model')),
                     ('agents.defaults.heartbeat.model', (defs.get('heartbeat') or {}).get('model'))):
        if blk:
            inspect(key, blk)

    if args.json:
        print(json.dumps({
            'config': args.config, 'agents': len(lst),
            'providers': sorted(provs), 'allowlist_size': len(allow),
            'fatal': [{'where': w, 'model': m, 'why': y} for w, m, y in fatal],
            'warnings': [{'where': w, 'model': m, 'why': y} for w, m, y in warn],
            'no_fallback_chain': no_fallback, 'all_ollama_chain': all_ollama,
        }, indent=2))
    else:
        print(f"verify-model-pins: {len(lst)} agents | providers={sorted(provs)} | allowlist={len(allow)}")
        if fatal:
            print(f"\nFATAL — these pins cannot resolve and WILL kill the agent at launch ({len(fatal)}):")
            for w, m, y in fatal:
                print(f"  ✗ {w}\n      {m}\n      {y}")
        if no_fallback:
            print(f"\nN31 — no fallback chain, single point of failure ({len(no_fallback)}):")
            for w in no_fallback[:40]:
                print(f"  ! {w}")
            if len(no_fallback) > 40:
                print(f"  … and {len(no_fallback) - 40} more")
        if all_ollama:
            print(f"\nALL-OLLAMA chain — an account-level cap takes these down together ({len(all_ollama)}):")
            for w in all_ollama[:20]:
                print(f"  ! {w}")
        if warn:
            print(f"\nWARNINGS ({len(warn)}):")
            for w, m, y in warn[:40]:
                print(f"  - {w}: {m} — {y}")
        if not (fatal or warn or no_fallback or all_ollama):
            print("\n✓ clean — every pin resolves, every agent has a fallback chain.")

    if fatal:
        return 1
    if args.strict and (warn or no_fallback or all_ollama):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
