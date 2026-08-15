import { useIsMobile } from "../hooks/useIsMobile.ts";
import { useTheme } from "../context/ThemeContext.tsx";
import RxDiagnostics from "../components/panels/RxDiagnostics.tsx";

// --- About-specific overrides ---
// The supercell background blends with default muted grays — use a brighter tone.
const MUTED = "#abb4ca";

/**
 * Per-theme full-page hero behind the About cards, per the Design
 * Agent's SCREENS.md ("About — replaces the weather background with
 * its own full-page plate") + ASSETS.md treatment table.
 *
 * ``scrim`` is a translucent rgba overlay painted on top of the
 * image so the cards' contrast stays legible — dark themes get a
 * navy dim, paper themes get a cream veil.
 *
 * mammoth / classic aren't in the About row of the table: mammoth
 * inherits the paper theme's plate via ``.app-plate`` already, and
 * classic ships without a hero.  For both, ``AboutHero`` returns
 * null and the cards render over the normal shell background.
 */
interface AboutHeroConfig {
  image: string;
  opacity: number;
  position?: string;
  filter?: string;
  blend?: string;
  scrim?: string;
}

const ABOUT_HERO: Record<string, AboutHeroConfig | null> = {
  dark: {
    image: "/about-hero.jpg",
    opacity: 1.0,
    position: "center 40%",
    scrim: "rgba(10, 13, 20, 0.42)",
  },
  light: {
    image: "/about-hero.jpg",
    opacity: 1.0,
    position: "center 40%",
    scrim: "rgba(10, 13, 20, 0.42)",
  },
  glaisher: {
    image: "/glaisher-ascent-1862.jpg",
    opacity: 0.34,
    position: "center",
    scrim: "rgba(237, 226, 196, 0.34)",
  },
  mammoth: null,
  classic: null,
};

// --- Shared styles ---

const cardStyle: React.CSSProperties = {
  background: "var(--color-bg-card)",
  borderRadius: "var(--gauge-border-radius)",
  border: "1px solid var(--color-border)",
  padding: "20px",
  marginBottom: "16px",
};

const sectionTitle: React.CSSProperties = {
  margin: "0 0 12px 0",
  fontSize: "calc(18px * var(--font-scale))",
  fontFamily: "var(--font-heading)",
  color: "var(--color-text)",
};

const bodyText: React.CSSProperties = {
  color: "var(--color-text-secondary)",
  fontSize: "calc(14px * var(--font-scale))",
  fontFamily: "var(--font-body)",
  lineHeight: "1.6",
  margin: 0,
};

const labelStyle: React.CSSProperties = {
  color: MUTED,
  fontSize: "calc(12px * var(--font-scale))",
  fontFamily: "var(--font-body)",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
  marginBottom: "2px",
};

const valueStyle: React.CSSProperties = {
  color: "var(--color-text)",
  fontSize: "calc(14px * var(--font-scale))",
  fontFamily: "var(--font-body)",
  fontWeight: 500,
};

// --- Helpers ---

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginBottom: "10px" }}>
      <div style={labelStyle}>{label}</div>
      <div style={valueStyle}>{value}</div>
    </div>
  );
}

// --- Buy me a Coffee ---

const BMAC_URL = "https://buymeacoffee.com/vsits";

function SupportCard({ isMobile }: { isMobile: boolean }) {
  return (
    <div
      style={{
        ...cardStyle,
        padding: isMobile ? "16px" : "24px",
        textAlign: "center",
        background: "var(--color-bg-card)",
        border: "2px solid var(--color-accent-muted)",
      }}
    >
      <div style={{ fontSize: "calc(28px * var(--font-scale))", marginBottom: "8px" }}>{'\u2615'}</div>
      <h3
        style={{
          ...sectionTitle,
          fontSize: "calc(16px * var(--font-scale))",
          marginBottom: "8px",
        }}
      >
        Support This Project
      </h3>
      <p
        style={{
          ...bodyText,
          fontSize: "calc(13px * var(--font-scale))",
          color: MUTED,
          marginBottom: "16px",
          maxWidth: "380px",
          marginLeft: "auto",
          marginRight: "auto",
        }}
      >
        This is a hobby project built for the weather station community. If you
        find it useful, consider buying me a coffee.
      </p>
      <a
        href={BMAC_URL}
        target="_blank"
        rel="noopener noreferrer"
        style={{
          display: "inline-block",
          padding: "10px 24px",
          borderRadius: "8px",
          background: "var(--color-accent)",
          color: "#fff",
          fontFamily: "var(--font-body)",
          fontSize: "calc(14px * var(--font-scale))",
          fontWeight: 600,
          textDecoration: "none",
          transition: "opacity 0.15s ease",
        }}
      >
        Buy me a Coffee
      </a>
    </div>
  );
}

// --- Main ---

export default function About() {
  const isMobile = useIsMobile();
  const { themeName } = useTheme();
  const pad = isMobile ? "12px" : "20px";
  const hero = ABOUT_HERO[themeName] ?? null;

  return (
    <>
      {hero && (
        <>
          {/* Full-page hero background per the active theme. */}
          <div
            aria-hidden="true"
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 0,
              backgroundImage: `url(${hero.image})`,
              backgroundSize: "cover",
              backgroundPosition: hero.position ?? "center",
              backgroundRepeat: "no-repeat",
              opacity: hero.opacity,
              filter: hero.filter,
              mixBlendMode: (hero.blend ?? "normal") as React.CSSProperties["mixBlendMode"],
              pointerEvents: "none",
            }}
          />
          {hero.scrim && (
            <div
              aria-hidden="true"
              style={{
                position: "fixed",
                inset: 0,
                zIndex: 0,
                background: hero.scrim,
                pointerEvents: "none",
              }}
            />
          )}
        </>
      )}

      <div style={{ flex: 1, overflowY: "auto", minHeight: 0, maxWidth: "860px", margin: "0 auto", padding: isMobile ? "0 12px 12px" : pad, position: "relative", zIndex: 1 }}>
      {/* Name + Description */}
      <div style={{ ...cardStyle, padding: isMobile ? "14px" : "20px" }}>
        <h2
          style={{
            fontFamily: "var(--font-heading)",
            fontSize: isMobile ? "calc(22px * var(--font-scale))" : "calc(26px * var(--font-scale))",
            color: "var(--color-text)",
            margin: "0 0 4px 0",
          }}
        >
          Kanfei
        </h2>
        <p
          style={{
            ...bodyText,
            fontSize: "calc(13px * var(--font-scale))",
            color: MUTED,
            marginBottom: "20px",
          }}
        >
          Weather Station Dashboard & Logger
        </p>
        <div style={{
          display: "flex",
          alignItems: isMobile ? "flex-start" : "center",
          gap: isMobile ? "12px" : "20px",
          flexDirection: isMobile ? "column" : "row",
          marginBottom: "14px",
        }}>
          <div style={{
            fontSize: "calc(42px * var(--font-scale))",
            fontFamily: "serif",
            lineHeight: 1,
            color: "var(--color-text)",
            direction: "rtl",
            letterSpacing: "2px",
          }}>
            {'\u05DB\u05B7\u05BC\u05E0\u05B0\u05E4\u05B5\u05D9'}
          </div>
          <div>
            <div style={{
              fontSize: "calc(14px * var(--font-scale))",
              fontFamily: "var(--font-body)",
              color: "var(--color-text-secondary)",
              fontStyle: "italic",
              marginBottom: "4px",
            }}>
              kanfei ruach {'\u2014'} "wings of the wind"
            </div>
            <div style={{
              fontSize: "calc(12px * var(--font-scale))",
              fontFamily: "var(--font-body)",
              color: MUTED,
            }}>
              Psalm 104:2{'\u2013'}3 (KJV) {'\u2014'} "Who coverest thyself with light as with a garment: who stretchest out the heavens like a curtain: Who layeth the beams of his chambers in the waters: who maketh the clouds his chariot: who walketh upon the wings of the wind."
            </div>
          </div>
        </div>
        <p style={bodyText}>
          A self-hosted web dashboard and data logger for personal weather
          stations. Supports Davis Instruments, Ecowitt, WeatherFlow Tempest,
          and Ambient Weather. Features real-time monitoring, historical
          charting, NWS forecasts, AI-powered nowcasting, and spray
          application advisory.
        </p>
      </div>

      {/* Software Stack */}
      <div style={{ ...cardStyle, padding: isMobile ? "14px" : "20px" }}>
        <h3 style={sectionTitle}>Software</h3>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
            gap: "4px 24px",
          }}
        >
          <InfoRow label="Version" value={__KANFEI_VERSION__} />
          <InfoRow label="Frontend" value="React + TypeScript + Vite" />
          <InfoRow label="Backend" value="Python FastAPI" />
          <InfoRow label="Database" value="SQLite (SQLAlchemy)" />
          <InfoRow label="Protocol" value="Multi-driver (serial, HTTP, UDP)" />
        </div>
      </div>

      {/* RX Diagnostics — hides itself when the driver doesn't report
          reception counters or when the caller isn't admin. */}
      <RxDiagnostics isMobile={isMobile} />

      {/* Credits */}
      <div style={{ ...cardStyle, padding: isMobile ? "14px" : "20px" }}>
        <h3 style={sectionTitle}>Credits</h3>
        <p style={{ ...bodyText, fontSize: "calc(13px * var(--font-scale))" }}>
          Built with open-source software. Weather data from the National
          Weather Service, Open-Meteo, and NOAA. AI nowcasting powered by
          Anthropic Claude.
        </p>
      </div>

      {/* Support */}
      <SupportCard isMobile={isMobile} />
    </div>
    </>
  );
}
