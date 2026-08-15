/**
 * The label that heads every dashboard tile ("OUTSIDE", "BAROMETER",
 * "WIND", …).  Design REVIEW-02: 10px mono, uppercase, tracked 2px,
 * left-aligned.  The previous gauges centred the label because their
 * flex parent used ``alignItems: 'center'``; wrapping the label in
 * this component gives it ``alignSelf: 'flex-start'`` so it hugs the
 * tile's left edge without disturbing the centred gauge SVG beside it.
 *
 * Consumed by TemperatureGauge, BarometerDial, WindCompass,
 * HumidityGauge, RainGauge, SolarUVGauge.
 */
import type { ReactNode } from 'react';

interface TileLabelProps {
  children: ReactNode;
}

export default function TileLabel({ children }: TileLabelProps) {
  return (
    <div style={{
      alignSelf: 'flex-start',
      width: '100%',
      fontSize: 'calc(10px * var(--font-scale))',
      fontFamily: 'var(--font-mono)',
      color: 'var(--color-text-secondary)',
      marginBottom: '6px',
      textTransform: 'uppercase',
      letterSpacing: '2px',
      textAlign: 'left',
    }}>
      {children}
    </div>
  );
}
