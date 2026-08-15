/**
 * Almanac tile per Design REVIEW-02: sunrise/sunset, day length with
 * day-over-day change, moon phase with illumination, station type +
 * firmware.  Rendered as a plain 4-row key/value table in the mock.
 */
import { useEffect, useState } from 'react';
import { fetchAstronomy, fetchStationStatus } from '../../api/client.ts';
import type { AstronomyResponse, StationStatus } from '../../api/types.ts';
import TileLabel from '../common/TileLabel.tsx';

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  } catch { return iso; }
}

export default function AlmanacTile() {
  const [astro, setAstro] = useState<AstronomyResponse | null>(null);
  const [station, setStation] = useState<StationStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      Promise.allSettled([fetchAstronomy(), fetchStationStatus()])
        .then(([a, s]) => {
          if (cancelled) return;
          if (a.status === 'fulfilled') setAstro(a.value);
          if (s.status === 'fulfilled') setStation(s.value);
        });
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
      <TileLabel>Almanac for today</TileLabel>
      <table style={{
        width: '100%',
        borderCollapse: 'collapse',
        fontFamily: 'var(--font-gauge)',
        fontSize: 'calc(13px * var(--font-scale))',
        color: 'var(--color-text)',
      }}>
        <tbody>
          <Row label="Sunrise / sunset" value={
            astro
              ? `${fmtTime(astro.sun.sunrise)} · ${fmtTime(astro.sun.sunset)}`
              : '—'
          } />
          <Row label="Day length" value={
            astro
              ? `${astro.sun.day_length}${astro.sun.day_change ? ' ' + astro.sun.day_change : ''}`
              : '—'
          } />
          <Row label="Moon" value={
            astro
              ? `${astro.moon.phase} ${Math.round(astro.moon.illumination * 100)}%`
              : '—'
          } />
          <Row label="Station" value={
            station
              ? `${station.type_name}${station.firmware_version ? ' · FW ' + station.firmware_version : ''}`
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
        padding: '10px 0',
        color: 'var(--color-text-secondary)',
        fontFamily: 'var(--font-body)',
        fontSize: 'calc(13px * var(--font-scale))',
      }}>{label}</td>
      <td style={{ padding: '10px 0', textAlign: 'right' }}>{value}</td>
    </tr>
  );
}
