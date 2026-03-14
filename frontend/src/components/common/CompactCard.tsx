interface CompactCardProps {
  label: string;
  children: React.ReactNode;
  secondary?: React.ReactNode;
  onClick?: () => void;
}

export default function CompactCard({
  label,
  children,
  secondary,
  onClick,
}: CompactCardProps) {
  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "8px 10px",
        background: "var(--color-bg-card)",
        borderRadius: "var(--gauge-border-radius, 16px)",
        boxShadow: "var(--gauge-shadow, 0 4px 24px rgba(0,0,0,0.4))",
        border: "1px solid var(--color-border)",
        height: "100%",
        boxSizing: "border-box",
        cursor: onClick ? "pointer" : undefined,
        gap: "2px",
      }}
    >
      <div
        style={{
          fontSize: "10px",
          fontFamily: "var(--font-body)",
          color: "var(--color-text-secondary)",
          textTransform: "uppercase",
          letterSpacing: "0.5px",
        }}
      >
        {label}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "center",
          gap: "2px",
        }}
      >
        {children}
      </div>
      {secondary && (
        <div
          style={{
            fontSize: "10px",
            fontFamily: "var(--font-gauge)",
            color: "var(--color-text-muted)",
            whiteSpace: "nowrap",
          }}
        >
          {secondary}
        </div>
      )}
    </div>
  );
}
