/**
 * Dashboard page — renders the fixed persona composition.
 *
 * Paper themes overlay two ornamental layers behind the composition
 * per Design's ASSETS.md Dashboard row:
 *   - Glaisher gets a full-cover balloon-ascent photo at 0.12 opacity
 *   - Both paper themes (mammoth + glaisher) get an instruments corner
 *     plate anchored bottom-right at ~0.09-0.10 opacity
 * Dark, light, classic ship with no dashboard-specific background.
 *
 * Persona switch lives here — Agriculture and Weather Nerd land as
 * their own literal-JSX layouts in a follow-up PR.
 */
import EverydayDashboard from "../dashboard/layouts/EverydayDashboard.tsx";
import { useTheme } from "../context/ThemeContext.tsx";
import { usePersona } from "../context/PersonaContext.tsx";

interface DashboardHeroConfig {
  cover?: { image: string; opacity: number; position?: string };
  corner?: { image: string; opacity: number; width: number; height: number };
}

const DASHBOARD_HERO: Record<string, DashboardHeroConfig | null> = {
  glaisher: {
    cover: {
      image: "/glaisher-ascent-1862.jpg",
      opacity: 0.12,
      position: "center",
    },
    corner: {
      image: "/glaisher-instruments.png",
      opacity: 0.10,
      width: 400,
      height: 280,
    },
  },
  mammoth: {
    corner: {
      image: "/glaisher-instruments.png",
      opacity: 0.09,
      width: 400,
      height: 280,
    },
  },
  dark: null,
  light: null,
  classic: null,
};

export default function Dashboard() {
  const { themeName } = useTheme();
  const { persona } = usePersona();
  const hero = DASHBOARD_HERO[themeName] ?? null;

  // Agriculture and Weather Nerd get their own literal-JSX layouts in
  // a follow-up; for now every persona lands on the Everyday
  // composition.  ``persona`` is intentionally destructured so the
  // switch site is obvious once Agriculture/WeatherNerd exist.
  void persona;
  const Layout = EverydayDashboard;

  return (
    <>
      {hero?.cover && (
        <div
          aria-hidden="true"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 0,
            backgroundImage: `url(${hero.cover.image})`,
            backgroundSize: "cover",
            backgroundPosition: hero.cover.position ?? "center",
            backgroundRepeat: "no-repeat",
            opacity: hero.cover.opacity,
            pointerEvents: "none",
          }}
        />
      )}
      {hero?.corner && (
        <div
          aria-hidden="true"
          style={{
            position: "fixed",
            right: 0,
            bottom: 0,
            width: `min(${hero.corner.width}px, 100vw)`,
            aspectRatio: `${hero.corner.width} / ${hero.corner.height}`,
            maxHeight: `${hero.corner.height}px`,
            zIndex: 0,
            backgroundImage: `url(${hero.corner.image})`,
            backgroundSize: "contain",
            backgroundPosition: "right bottom",
            backgroundRepeat: "no-repeat",
            opacity: hero.corner.opacity,
            pointerEvents: "none",
          }}
        />
      )}
      <Layout />
    </>
  );
}
