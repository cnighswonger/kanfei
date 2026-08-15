/**
 * Zambretti forecast sentence tile per Design REVIEW-02.
 *
 * Renders the Zambretti local forecast (e.g. "Fairly fine, becoming
 * less settled") as italic serif body copy with a
 * "ZAMBRETTI · N% CONFIDENCE" mono-caps footer.  Independent of the
 * hero temperature tile in this PR — a later composition PR may fold
 * it into the current-conditions region.
 */
import { useEffect, useState } from 'react';
import { fetchForecast } from '../../api/client.ts';
import type { LocalForecast } from '../../api/types.ts';
import TileLabel from '../common/TileLabel.tsx';

export default function ZambrettiTile() {
  const [local, setLocal] = useState<LocalForecast | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetchForecast()
        .then((r) => { if (!cancelled) setLocal(r.local ?? null); })
        .catch((e) => { if (!cancelled) setError(String(e)); });
    };
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      padding: '16px',
      background: 'var(--color-bg-card)',
      borderRadius: 'var(--gauge-border-radius, 16px)',
      border: '1px solid var(--color-border)',
      height: '100%',
      boxSizing: 'border-box',
    }}>
      <TileLabel>Zambretti</TileLabel>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        {error && <div style={{ color: 'var(--color-danger)', fontSize: 'calc(12px * var(--font-scale))' }}>{error}</div>}
        {!error && !local && (
          <div style={{ color: 'var(--color-text-muted)', fontSize: 'calc(13px * var(--font-scale))' }}>Loading…</div>
        )}
        {local && (
          <>
            <div style={{
              fontFamily: 'var(--font-heading)',
              fontSize: 'calc(20px * var(--font-scale))',
              fontStyle: 'italic',
              color: 'var(--color-text)',
              lineHeight: 1.3,
              marginBottom: '10px',
            }}>
              {local.text}
            </div>
            <div style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'calc(10px * var(--font-scale))',
              letterSpacing: '2px',
              textTransform: 'uppercase',
              color: 'var(--color-text-muted)',
            }}>
              Zambretti · {local.confidence}% confidence
            </div>
          </>
        )}
      </div>
    </div>
  );
}
