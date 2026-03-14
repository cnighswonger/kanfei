/**
 * Renders a value with its unit label.
 */

interface UnitDisplayProps {
  value: number | null;
  unit: string;
  decimals?: number;
  fontSize?: string;
  nullText?: string;
}

export default function UnitDisplay({
  value,
  unit,
  decimals = 1,
  fontSize = '16px',
  nullText = '--',
}: UnitDisplayProps) {
  return (
    <span style={{ fontFamily: 'var(--font-gauge)', fontSize, color: 'var(--color-text)' }}>
      {value !== null ? value.toFixed(decimals) : nullText}
      <span style={{
        fontSize: '0.65em',
        color: 'var(--color-text-muted)',
        fontFamily: 'var(--font-body)',
        marginLeft: '2px',
      }}>
        {unit}
      </span>
    </span>
  );
}
