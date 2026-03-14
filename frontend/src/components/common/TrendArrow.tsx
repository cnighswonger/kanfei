/**
 * Animated trend arrow indicator.
 */

interface TrendArrowProps {
  trend: 'rising' | 'falling' | 'steady' | null;
  size?: number;
}

export default function TrendArrow({ trend, size = 16 }: TrendArrowProps) {
  if (!trend) return null;

  const color =
    trend === 'rising' ? 'var(--color-success)' :
    trend === 'falling' ? 'var(--color-danger)' :
    'var(--color-text-secondary)';

  const arrow =
    trend === 'rising' ? '\u2197' :   // ↗
    trend === 'falling' ? '\u2198' :   // ↘
    '\u2192';                           // →

  return (
    <span
      style={{
        fontSize: `${size}px`,
        color,
        fontWeight: 'bold',
        lineHeight: 1,
        display: 'inline-block',
        transition: 'color 0.3s ease',
      }}
      title={`Pressure ${trend}`}
    >
      {arrow}
    </span>
  );
}
