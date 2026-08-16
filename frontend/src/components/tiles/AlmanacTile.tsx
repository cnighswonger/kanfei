/**
 * Almanac tile: sunrise/sunset, day length, moon phase.  Backend
 * returns pre-formatted display strings for sun times and
 * ``moon.illumination`` already as a percentage — pass both through.
 * Station type / firmware live in the station-status footer strip
 * per Design's REVIEW-05 P3.
 */
import { useEffect, useState } from 'react';
import { fetchAstronomy } from '../../api/client.ts';
import type { AstronomyResponse } from '../../api/types.ts';
import TileLabel from '../common/TileLabel.tsx';

export default function AlmanacTile() {
  const [astro, setAstro] = useState<AstronomyResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetchAstronomy()
        .then((a) => { if (!cancelled) setAstro(a); })
        .catch(() => { /* astronomy is optional; tile renders "—" placeholders */ });
    };
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      padding: '10px 14px',
      background: 'var(--color-bg-card)',
      borderRadius: 'var(--gauge-border-radius, 16px)',
      border: '1px solid var(--color-border)',
      height: '100%',
      boxSizing: 'border-box',
      overflow: 'hidden',
    }}>
      <TileLabel>Almanac for today</TileLabel>
      <table style={{
        width: '100%',
        borderCollapse: 'collapse',
        fontFamily: 'var(--font-gauge)',
        fontSize: 'calc(12px * var(--font-scale))',
        color: 'var(--color-text)',
      }}>
        <tbody>
          <Row label="Sunrise / sunset" value={
            astro
              ? `${astro.sun.sunrise} · ${astro.sun.sunset}`
              : '—'
          } />
          <Row label="Day length" value={
            astro
              ? `${astro.sun.day_length}${astro.sun.day_change ? ' ' + astro.sun.day_change : ''}`
              : '—'
          } />
          <Row label="Moon" value={
            astro
              ? `${astro.moon.phase} ${Math.round(astro.moon.illumination)}%`
              : '—'
          } />
        </tbody>
      </table>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <tr style={{ borderBottom: `var(--rule-width, 1px) var(--rule-style, solid) var(--rule-hair, rgba(0,0,0,0.1))` }}>
      <td style={{
        padding: '6px 0',
        color: 'var(--color-text-secondary)',
        fontFamily: 'var(--font-body)',
        fontSize: 'calc(12px * var(--font-scale))',
      }}>{label}</td>
      <td style={{ padding: '6px 0', textAlign: 'right' }}>{value}</td>
    </tr>
  );
}
