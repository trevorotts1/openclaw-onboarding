'use client';

/**
 * Token paste gate (design 11.2): the client visits /podcast and pastes the
 * access token once. On success the server sets an HttpOnly session cookie
 * and the page refreshes into the dashboard. Failures show a clean branded
 * "Access unavailable" message with zero detail (fail closed). The token is
 * sent once over the authenticated Cloudflare channel and never stored in
 * the browser.
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { KeyRound, Loader2, Mic } from 'lucide-react';

export default function TokenGate() {
  const router = useRouter();
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy || token.trim().length === 0) return;
    setBusy(true);
    setFailed(false);
    try {
      const res = await fetch('/api/podcast/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: token.trim() }),
      });
      if (res.ok) {
        setToken('');
        router.refresh();
        return;
      }
      setFailed(true);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-6 sm:p-8 shadow-card">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-50">
          <Mic className="h-6 w-6 text-brand-600" aria-hidden="true" />
        </span>
        <h1 className="mt-4 text-card-title text-gray-900">Podcast Studio</h1>
        <p className="mt-1 text-caption text-gray-500">
          Paste your access token to view your episodes. You only need to do this once on this
          device.
        </p>
        <form onSubmit={submit} className="mt-5 space-y-3">
          <label className="block">
            <span className="text-label text-gray-700">Access token</span>
            <div className="relative mt-1">
              <KeyRound
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
                aria-hidden="true"
              />
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="off"
                spellCheck={false}
                placeholder="pdt_..."
                aria-label="Access token"
                className="w-full rounded-xl border border-gray-200 py-2.5 pl-9 pr-3 font-mono text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-none focus:ring-2 focus:ring-brand-100"
              />
            </div>
          </label>
          {failed ? (
            <p className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              Access unavailable.
            </p>
          ) : null}
          <button
            type="submit"
            disabled={busy || token.trim().length === 0}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
            Continue
          </button>
        </form>
      </div>
    </div>
  );
}
