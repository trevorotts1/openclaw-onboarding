'use client';

/**
 * Operator token screen (/podcast/ops/access, design 11.3): lists dashboard
 * tokens (id, label, created, last used, status), mints new ones showing
 * the raw value exactly once, and revokes with a reason. Revocation takes
 * effect on the very next request. Raw values are never persisted, never
 * logged, and never shown again after the mint dialog closes.
 */

import { useCallback, useEffect, useState } from 'react';
import { Copy, KeyRound, Loader2, ShieldOff } from 'lucide-react';
import { ErrorState, LoadingState } from './states';
import type { TokenListItem } from '@/lib/podcast/types';
import { absoluteTime, relativeTime } from '@/lib/podcast/format';

export default function OpsAccess() {
  const [tokens, setTokens] = useState<TokenListItem[] | null>(null);
  const [error, setError] = useState(false);
  const [label, setLabel] = useState('');
  const [minting, setMinting] = useState(false);
  const [minted, setMinted] = useState<{ tokenId: string; rawTokenShownOnce: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(false);
    fetch('/api/podcast/ops/tokens', { cache: 'no-store' })
      .then((res) => {
        if (!res.ok) throw new Error('bad status');
        return res.json() as Promise<{ tokens: TokenListItem[] }>;
      })
      .then((json) => setTokens(json.tokens))
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const mint = async (e: React.FormEvent) => {
    e.preventDefault();
    if (minting) return;
    setMinting(true);
    setMinted(null);
    setCopied(false);
    try {
      const res = await fetch('/api/podcast/ops/tokens', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: label.trim() || null }),
      });
      if (res.ok) {
        const json = (await res.json()) as { tokenId: string; rawTokenShownOnce: string };
        setMinted(json);
        setLabel('');
        load();
      } else {
        setError(true);
      }
    } catch {
      setError(true);
    } finally {
      setMinting(false);
    }
  };

  const revoke = async (tokenId: string) => {
    const reason = window.prompt('Reason for revoking this token?') ?? '';
    setRevoking(tokenId);
    try {
      await fetch(`/api/podcast/ops/tokens/${encodeURIComponent(tokenId)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      });
      load();
    } finally {
      setRevoking(null);
    }
  };

  const copyMinted = async () => {
    if (!minted) return;
    try {
      await navigator.clipboard.writeText(minted.rawTokenShownOnce);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  if (error && tokens === null) return <ErrorState onRetry={load} />;
  if (tokens === null) return <LoadingState rows={3} kpis={0} />;

  return (
    <div className="space-y-6">
      <form
        onSubmit={mint}
        className="rounded-2xl border border-gray-200 bg-white p-4 sm:p-5 shadow-card"
      >
        <h2 className="text-sub-heading text-gray-900">Mint a dashboard token</h2>
        <p className="mt-1 text-caption text-gray-500">
          The raw token is shown exactly once, right here. Store it in the client&apos;s own
          credential store; it is never displayed again.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label, e.g. primary client access"
            aria-label="Token label"
            className="flex-1 min-w-[200px] rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
          <button
            type="submit"
            disabled={minting}
            className="flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-700 disabled:opacity-60"
          >
            {minting ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <KeyRound className="h-4 w-4" aria-hidden="true" />
            )}
            Mint token
          </button>
        </div>
        {minted ? (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3">
            <div className="text-label text-amber-800">
              Shown once. Copy it now; it will not appear again.
            </div>
            <div className="mt-2 flex items-center gap-2">
              <code className="flex-1 overflow-x-auto rounded-lg bg-white px-3 py-2 font-mono text-sm text-gray-800 border border-amber-200">
                {minted.rawTokenShownOnce}
              </code>
              <button
                type="button"
                onClick={() => void copyMinted()}
                className="flex items-center gap-1 rounded-lg border border-amber-300 px-3 py-2 text-sm text-amber-800 transition-colors hover:bg-amber-100"
              >
                <Copy className="h-4 w-4" aria-hidden="true" />
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>
        ) : null}
      </form>

      <section>
        <h2 className="text-sub-heading text-gray-900 mb-3">Existing tokens</h2>
        {tokens.length === 0 ? (
          <p className="text-caption text-gray-500">
            No tokens yet. Tokens can also be minted by the engine&apos;s state writer during
            provisioning.
          </p>
        ) : (
          <div className="space-y-2">
            {tokens.map((t) => {
              const dead = t.revokedAt !== null;
              return (
                <div
                  key={t.tokenId}
                  className={`flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 ${
                    dead ? 'border-gray-200 bg-gray-50' : 'border-gray-200 bg-white'
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-caption text-gray-700">{t.tokenId}</span>
                      {dead ? (
                        <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-600">
                          Revoked
                        </span>
                      ) : (
                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-600">
                          Active
                        </span>
                      )}
                    </div>
                    <div className="text-caption text-gray-500">
                      {t.label ?? 'No label'} · created{' '}
                      <span title={absoluteTime(t.createdAt)}>{relativeTime(t.createdAt)}</span>
                      {t.lastUsedAt ? (
                        <>
                          {' '}· last used{' '}
                          <span title={absoluteTime(t.lastUsedAt)}>{relativeTime(t.lastUsedAt)}</span>
                        </>
                      ) : (
                        ' · never used'
                      )}
                      {dead && t.revokedReason ? <> · reason: {t.revokedReason}</> : null}
                    </div>
                  </div>
                  {!dead ? (
                    <button
                      onClick={() => void revoke(t.tokenId)}
                      disabled={revoking === t.tokenId}
                      className="flex items-center gap-1 rounded-lg border border-red-200 px-3 py-1.5 text-sm text-red-600 transition-colors hover:bg-red-50 disabled:opacity-60"
                    >
                      {revoking === t.tokenId ? (
                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                      ) : (
                        <ShieldOff className="h-4 w-4" aria-hidden="true" />
                      )}
                      Revoke
                    </button>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-gray-200 bg-white p-4 sm:p-5 shadow-card">
        <h2 className="text-sub-heading text-gray-900">Churn runbook</h2>
        <p className="mt-1 text-caption text-gray-600 max-w-2xl">
          Full revocation is a three-blade kill switch: revoke every token here and deactivate the
          client through the engine (application blade), remove the Cloudflare Access application
          and tunnel ingress for the hostname (edge blade), and let the deactivated engine refuse
          new submissions (engine blade). The step-by-step procedure lives in the fleet Cloudflare
          revocation runbook; run it from the operator box, never from this dashboard.
        </p>
      </section>
    </div>
  );
}
