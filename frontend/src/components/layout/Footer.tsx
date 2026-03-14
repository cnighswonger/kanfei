interface FooterProps {
  lastUpdate: Date | null;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export default function Footer({ lastUpdate }: FooterProps) {
  return (
    <footer
      style={{
        padding: '12px 20px',
        borderTop: '1px solid var(--color-border)',
        background: 'var(--color-bg-secondary)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        fontSize: '12px',
        color: 'var(--color-text-muted)',
        fontFamily: 'var(--font-body)',
        flexShrink: 0,
      }}
    >
      <span>Kanfei v0.1.0</span>
      <span>
        {lastUpdate ? `Last update: ${formatTime(lastUpdate)}` : 'No data received'}
      </span>
    </footer>
  );
}
