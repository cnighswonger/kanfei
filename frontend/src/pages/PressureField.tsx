/**
 * PressureField — interactive 3D pressure field visualization.
 *
 * Renders a high-resolution IDW-interpolated pressure grid as a 3D
 * surface mesh using Three.js (react-three-fiber).  Wells (lows),
 * ridges (highs), and gradients are visible as terrain-like topology.
 */
import { useState, useEffect, useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Html } from "@react-three/drei";
import * as THREE from "three";
import { useTheme } from "../context/ThemeContext.tsx";
import { API_BASE } from "../utils/constants.ts";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PressureGridData {
  grid: number[][];
  rows: number;
  cols: number;
  lat_min: number;
  lat_max: number;
  lon_min: number;
  lon_max: number;
  pressure_min: number;
  pressure_max: number;
  station_count: number;
  stations: StationMarker[];
  pressure_unit: string;  // "inHg" | "hPa" | "mb"
  temp_unit: string;      // "F" | "C"
  wind_unit: string;      // "mph" | "kph" | "knots"
}

interface StationMarker {
  lat: number;
  lon: number;
  pressure_hpa: number;
  name: string;
  id?: string;
  source?: string;
  temp_f?: number | null;
  wind_mph?: number | null;
  wind_dir?: number | null;
  pressure_inhg?: number | null;
  updated?: string | null;
  is_home?: boolean;
}

// ---------------------------------------------------------------------------
// Unit formatting helpers
// ---------------------------------------------------------------------------

function fmtPressure(hpa: number, unit: string): string {
  if (unit === "inHg") return `${(hpa / 33.8639).toFixed(2)} inHg`;
  if (unit === "mb") return `${hpa.toFixed(1)} mb`;
  return `${hpa.toFixed(1)} hPa`;
}

function fmtTemp(f: number, unit: string): string {
  if (unit === "C") return `${Math.round((f - 32) * 5 / 9)}°C`;
  return `${Math.round(f)}°F`;
}

function fmtWind(mph: number, unit: string): string {
  if (unit === "kph") return `${Math.round(mph * 1.60934)} kph`;
  if (unit === "knots") return `${Math.round(mph * 0.868976)} kts`;
  return `${Math.round(mph)} mph`;
}

// ---------------------------------------------------------------------------
// Color ramp — blue (low) → cyan → green → yellow → red (high)
// ---------------------------------------------------------------------------

function pressureColor(t: number): [number, number, number] {
  // 8-stop color ramp for tighter contrast between small pressure deltas.
  // t: 0 (min pressure / well) → 1 (max pressure / ridge)
  const stops: [number, number, number, number][] = [
    //  t     R     G     B
    [0.000, 0.10, 0.10, 0.95],  // deep blue
    [0.143, 0.10, 0.45, 0.90],  // blue
    [0.286, 0.10, 0.75, 0.80],  // cyan
    [0.429, 0.15, 0.80, 0.40],  // teal-green
    [0.571, 0.40, 0.82, 0.15],  // green-yellow
    [0.714, 0.80, 0.70, 0.10],  // yellow
    [0.857, 0.95, 0.45, 0.08],  // orange
    [1.000, 0.85, 0.12, 0.05],  // red
  ];
  const tc = Math.max(0, Math.min(1, t));
  for (let i = 0; i < stops.length - 1; i++) {
    if (tc <= stops[i + 1][0]) {
      const s = (tc - stops[i][0]) / (stops[i + 1][0] - stops[i][0]);
      return [
        stops[i][1] + s * (stops[i + 1][1] - stops[i][1]),
        stops[i][2] + s * (stops[i + 1][2] - stops[i][2]),
        stops[i][3] + s * (stops[i + 1][3] - stops[i][3]),
      ];
    }
  }
  const last = stops[stops.length - 1];
  return [last[1], last[2], last[3]];
}

// ---------------------------------------------------------------------------
// 3D Pressure Surface mesh
// ---------------------------------------------------------------------------

function PressureSurface({ data }: { data: PressureGridData }) {
  const meshRef = useRef<THREE.Mesh>(null);

  const { geometry, material } = useMemo(() => {
    const { grid, rows, cols, pressure_min, pressure_max } = data;
    const pRange = pressure_max - pressure_min || 1;

    // Scene dimensions — normalize to manageable units
    const sceneWidth = 10;
    const sceneDepth = 10 * (rows / cols);
    const heightScale = 8; // exaggeration factor for visual impact

    const geo = new THREE.PlaneGeometry(
      sceneWidth, sceneDepth, cols - 1, rows - 1,
    );

    // Rotate to XZ plane (PlaneGeometry is XY by default)
    geo.rotateX(-Math.PI / 2);

    const positions = geo.attributes.position;
    const colors = new Float32Array(positions.count * 3);

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const idx = r * cols + c;
        const p = grid[r][c];
        const t = (p - pressure_min) / pRange;

        // Displace Y (height) by pressure
        positions.setY(idx, t * heightScale);

        // Vertex color
        const [cr, cg, cb] = pressureColor(t);
        colors[idx * 3] = cr;
        colors[idx * 3 + 1] = cg;
        colors[idx * 3 + 2] = cb;
      }
    }

    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geo.computeVertexNormals();

    const mat = new THREE.MeshStandardMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      roughness: 0.6,
      metalness: 0.1,
      flatShading: false,
      transparent: true,
      opacity: 0.75,
    });

    return { geometry: geo, material: mat };
  }, [data]);

  return <mesh ref={meshRef} geometry={geometry} material={material} />;
}

// ---------------------------------------------------------------------------
// Extruded side walls — gives the solid block / terrain slab look
// ---------------------------------------------------------------------------

function SideWalls({ data }: { data: PressureGridData }) {
  const geometry = useMemo(() => {
    const { grid, rows, cols, pressure_min, pressure_max } = data;
    const pRange = pressure_max - pressure_min || 1;
    const sceneWidth = 10;
    const sceneDepth = 10 * (rows / cols);
    const heightScale = 8;
    const baseY = -0.3; // slightly below the surface minimum

    const vertices: number[] = [];
    const colors: number[] = [];

    const halfW = sceneWidth / 2;
    const halfD = sceneDepth / 2;

    // Helper: add a quad (two triangles) with color
    function addQuad(
      ax: number, ay: number, az: number,
      bx: number, by: number, bz: number,
      cx: number, cy: number, cz: number,
      dx: number, dy: number, dz: number,
      t1: number, t2: number,
    ) {
      // Triangle 1: a, b, c
      vertices.push(ax, ay, az, bx, by, bz, cx, cy, cz);
      // Triangle 2: a, c, d
      vertices.push(ax, ay, az, cx, cy, cz, dx, dy, dz);
      // Colors — blend between the two t values
      const [r1, g1, b1] = pressureColor(t1);
      const [r2, g2, b2] = pressureColor(t2);
      // top verts get surface color, bottom verts get darkened
      const dim = 0.5;
      colors.push(r1, g1, b1, r2 * dim, g2 * dim, b2 * dim, r2, g2, b2);
      colors.push(r1, g1, b1, r2, g2, b2, r1 * dim, g1 * dim, b1 * dim);
    }

    // Front edge (row 0)
    for (let c = 0; c < cols - 1; c++) {
      const t1 = (grid[0][c] - pressure_min) / pRange;
      const t2 = (grid[0][c + 1] - pressure_min) / pRange;
      const x1 = -halfW + (c / (cols - 1)) * sceneWidth;
      const x2 = -halfW + ((c + 1) / (cols - 1)) * sceneWidth;
      const z = -halfD;
      addQuad(
        x1, t1 * heightScale, z,
        x1, baseY, z,
        x2, baseY, z,
        x2, t2 * heightScale, z,
        t1, t2,
      );
    }

    // Back edge (last row)
    for (let c = 0; c < cols - 1; c++) {
      const t1 = (grid[rows - 1][c] - pressure_min) / pRange;
      const t2 = (grid[rows - 1][c + 1] - pressure_min) / pRange;
      const x1 = -halfW + (c / (cols - 1)) * sceneWidth;
      const x2 = -halfW + ((c + 1) / (cols - 1)) * sceneWidth;
      const z = halfD;
      addQuad(
        x2, t2 * heightScale, z,
        x2, baseY, z,
        x1, baseY, z,
        x1, t1 * heightScale, z,
        t2, t1,
      );
    }

    // Left edge (col 0)
    for (let r = 0; r < rows - 1; r++) {
      const t1 = (grid[r][0] - pressure_min) / pRange;
      const t2 = (grid[r + 1][0] - pressure_min) / pRange;
      const z1 = -halfD + (r / (rows - 1)) * sceneDepth;
      const z2 = -halfD + ((r + 1) / (rows - 1)) * sceneDepth;
      const x = -halfW;
      addQuad(
        x, t2 * heightScale, z2,
        x, baseY, z2,
        x, baseY, z1,
        x, t1 * heightScale, z1,
        t2, t1,
      );
    }

    // Right edge (last col)
    for (let r = 0; r < rows - 1; r++) {
      const t1 = (grid[r][cols - 1] - pressure_min) / pRange;
      const t2 = (grid[r + 1][cols - 1] - pressure_min) / pRange;
      const z1 = -halfD + (r / (rows - 1)) * sceneDepth;
      const z2 = -halfD + ((r + 1) / (rows - 1)) * sceneDepth;
      const x = halfW;
      addQuad(
        x, t1 * heightScale, z1,
        x, baseY, z1,
        x, baseY, z2,
        x, t2 * heightScale, z2,
        t1, t2,
      );
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    geo.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    geo.computeVertexNormals();
    return geo;
  }, [data]);

  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial vertexColors side={THREE.DoubleSide} roughness={0.8} transparent opacity={0.75} />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// Gradient flow lines — streamlines of the pressure gradient field
// ---------------------------------------------------------------------------

/** Number of streamlines seeded across the grid. */
const FLOW_SEED_COUNT = 200;
/** Integration steps per streamline (RK4). */
const FLOW_STEPS = 60;
/** Step size as a fraction of grid cells. */
const FLOW_DT = 0.8;

// Coriolis rotation constants (~25° clockwise, NH surface approximation)
const COR_COS = 0.906;  // cos(25°)
const COR_SIN = 0.423;  // sin(25°)
const COR_FRICTION = 0.7; // surface friction reduction

function GradientFlowLines({ data, coriolis }: { data: PressureGridData; coriolis: boolean }) {
  const { grid, rows, cols, pressure_min, pressure_max } = data;
  const sceneWidth = 10;
  const sceneDepth = 10 * (rows / cols);
  const halfW = sceneWidth / 2;
  const halfD = sceneDepth / 2;
  const pRange = (pressure_max - pressure_min) || 1;
  const heightScale = 8;

  const lineSegments = useMemo(() => {
    // --- Compute gradient field (central finite differences) ---
    // gradX[r][c] = dP/dc, gradZ[r][c] = dP/dr (grid-space)
    const gradC: number[][] = [];
    const gradR: number[][] = [];
    for (let r = 0; r < rows; r++) {
      gradC[r] = [];
      gradR[r] = [];
      for (let c = 0; c < cols; c++) {
        const dc = c > 0 && c < cols - 1
          ? (grid[r][c + 1] - grid[r][c - 1]) / 2
          : c === 0 ? grid[r][1] - grid[r][0] : grid[r][c] - grid[r][c - 1];
        const dr = r > 0 && r < rows - 1
          ? (grid[r + 1][c] - grid[r - 1][c]) / 2
          : r === 0 ? grid[1][c] - grid[0][c] : grid[r][c] - grid[r - 1][c];
        gradC[r][c] = dc;
        gradR[r][c] = dr;
      }
    }

    // --- Bilinear sample of gradient at fractional grid position ---
    const sampleGrad = (fr: number, fc: number): [number, number] | null => {
      if (fr < 0 || fr > rows - 1 || fc < 0 || fc > cols - 1) return null;
      const r0 = Math.min(Math.floor(fr), rows - 2);
      const c0 = Math.min(Math.floor(fc), cols - 2);
      const dr = fr - r0;
      const dc = fc - c0;
      const gc = gradC[r0][c0] * (1 - dr) * (1 - dc)
               + gradC[r0][c0 + 1] * (1 - dr) * dc
               + gradC[r0 + 1][c0] * dr * (1 - dc)
               + gradC[r0 + 1][c0 + 1] * dr * dc;
      const gr = gradR[r0][c0] * (1 - dr) * (1 - dc)
               + gradR[r0][c0 + 1] * (1 - dr) * dc
               + gradR[r0 + 1][c0] * dr * (1 - dc)
               + gradR[r0 + 1][c0 + 1] * dr * dc;
      // Apply Coriolis rotation + friction if enabled
      if (coriolis) {
        const gc2 = (gc * COR_COS - gr * COR_SIN) * COR_FRICTION;
        const gr2 = (gc * COR_SIN + gr * COR_COS) * COR_FRICTION;
        return [gc2, gr2];
      }
      return [gc, gr];
    };

    // --- Grid position → scene XYZ (same as StateBoundaryLines toScene) ---
    const toScene = (fr: number, fc: number): THREE.Vector3 | null => {
      if (fr < 0 || fr > rows - 1 || fc < 0 || fc > cols - 1) return null;
      const xNorm = fc / (cols - 1);
      const zNorm = fr / (rows - 1);
      const x = -halfW + xNorm * sceneWidth;
      const z = -halfD + zNorm * sceneDepth;
      // Bilinear height sample
      const r0 = Math.min(Math.floor(fr), rows - 2);
      const c0 = Math.min(Math.floor(fc), cols - 2);
      const dr = fr - r0;
      const dc = fc - c0;
      const p = grid[r0][c0] * (1 - dr) * (1 - dc)
              + grid[r0][c0 + 1] * (1 - dr) * dc
              + grid[r0 + 1][c0] * dr * (1 - dc)
              + grid[r0 + 1][c0 + 1] * dr * dc;
      const y = ((p - pressure_min) / pRange) * heightScale + 0.03;
      return new THREE.Vector3(x, y, z);
    };

    // --- Compute max gradient magnitude for brightness normalization ---
    let maxGradMag = 0;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const m = Math.sqrt(gradC[r][c] ** 2 + gradR[r][c] ** 2);
        if (m > maxGradMag) maxGradMag = m;
      }
    }
    if (maxGradMag < 1e-8) maxGradMag = 1;

    // --- Seed streamlines on a jittered grid ---
    const segments: THREE.BufferGeometry[] = [];
    const arrows: { position: THREE.Vector3; direction: THREE.Vector3 }[] = [];
    const seedSpacing = Math.sqrt((rows * cols) / FLOW_SEED_COUNT);
    for (let sr = seedSpacing / 2; sr < rows - 1; sr += seedSpacing) {
      for (let sc = seedSpacing / 2; sc < cols - 1; sc += seedSpacing) {
        // RK4 integration along negative gradient (high → low pressure)
        const points: THREE.Vector3[] = [];
        const mags: number[] = [];
        let cr = sr, cc = sc;
        for (let step = 0; step < FLOW_STEPS; step++) {
          const pt = toScene(cr, cc);
          if (!pt) break;
          points.push(pt);

          const g = sampleGrad(cr, cc);
          mags.push(g ? Math.sqrt(g[0] ** 2 + g[1] ** 2) : 0);

          // RK4
          const k1 = sampleGrad(cr, cc);
          if (!k1) break;
          const k2 = sampleGrad(cr - k1[1] * FLOW_DT * 0.5, cc - k1[0] * FLOW_DT * 0.5);
          if (!k2) break;
          const k3 = sampleGrad(cr - k2[1] * FLOW_DT * 0.5, cc - k2[0] * FLOW_DT * 0.5);
          if (!k3) break;
          const k4 = sampleGrad(cr - k3[1] * FLOW_DT, cc - k3[0] * FLOW_DT);
          if (!k4) break;

          const drc = (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]) / 6;
          const dcc = (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]) / 6;
          const mag = Math.sqrt(drc * drc + dcc * dcc);
          if (mag < 1e-6) break; // stagnation point

          // Normalize and step (negative gradient = toward low pressure)
          cr -= (drc / mag) * FLOW_DT;
          cc -= (dcc / mag) * FLOW_DT;
        }
        if (points.length > 2) {
          const geo = new THREE.BufferGeometry().setFromPoints(points);
          // Uniform white lines — direction shown by arrowheads
          const colors = new Float32Array(points.length * 3);
          for (let i = 0; i < points.length; i++) {
            const bright = 0.4 + 0.6 * Math.min(mags[i] / maxGradMag, 1);
            colors[i * 3] = bright;
            colors[i * 3 + 1] = bright;
            colors[i * 3 + 2] = bright;
          }
          geo.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
          segments.push(geo);

          // Arrowhead: direction from second-to-last → last point
          const tip = points[points.length - 1];
          const prev = points[points.length - 2];
          const dir = new THREE.Vector3().subVectors(tip, prev).normalize();
          arrows.push({ position: tip, direction: dir });
        }
      }
    }
    return { segments, arrows };
  }, [data, coriolis]); // eslint-disable-line react-hooks/exhaustive-deps

  const lineMaterial = useMemo(
    () => new THREE.LineBasicMaterial({
      vertexColors: true,
      opacity: 0.7,
      transparent: true,
    }),
    [],
  );

  const arrowGeo = useMemo(() => new THREE.ConeGeometry(0.025, 0.07, 6), []);
  const arrowMat = useMemo(
    () => new THREE.MeshBasicMaterial({ color: coriolis ? "#ff8c00" : "#ff1493", transparent: true, opacity: 0.85 }),
    [coriolis],
  );

  return (
    <>
      {lineSegments.segments.map((geo, i) => (
        <primitive key={`l${i}`} object={new THREE.Line(geo, lineMaterial)} />
      ))}
      {lineSegments.arrows.map((arrow, i) => {
        // Orient cone to point along flow direction
        const q = new THREE.Quaternion();
        q.setFromUnitVectors(new THREE.Vector3(0, 1, 0), arrow.direction);
        return (
          <mesh key={`a${i}`} geometry={arrowGeo} material={arrowMat}
            position={[arrow.position.x, arrow.position.y, arrow.position.z]}
            quaternion={q}
          />
        );
      })}
    </>
  );
}

// ---------------------------------------------------------------------------
// Temperature overlay — IDW-interpolated station temps draped on the surface
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Shared wind grid — IDW-interpolated u/v from station observations
// ---------------------------------------------------------------------------

/** IDW-interpolate observed wind vectors onto the pressure grid. */
function useWindGrid(data: PressureGridData): { uGrid: number[][]; vGrid: number[][] } | null {
  const { rows, cols, stations, lat_min, lat_max, lon_min, lon_max } = data;

  return useMemo(() => {
    const windStations = stations.filter(
      (s) => s.wind_mph != null && s.wind_dir != null && s.wind_mph >= 0
    );
    if (windStations.length < 3) return null;

    // Decompose met-convention wind (dir = FROM, CW from N) to u/v
    const stationUV = windStations.map((s) => {
      const dirRad = (s.wind_dir! * Math.PI) / 180;
      return {
        lat: s.lat, lon: s.lon,
        u: -s.wind_mph! * Math.sin(dirRad),
        v: -s.wind_mph! * Math.cos(dirRad),
      };
    });

    const uGrid: number[][] = [];
    const vGrid: number[][] = [];
    for (let r = 0; r < rows; r++) {
      uGrid[r] = [];
      vGrid[r] = [];
      const lat = lat_min + (r / (rows - 1)) * (lat_max - lat_min);
      for (let c = 0; c < cols; c++) {
        const lon = lon_min + (c / (cols - 1)) * (lon_max - lon_min);
        let wSum = 0, uSum = 0, vSum = 0;
        for (const s of stationUV) {
          const dlat = s.lat - lat;
          const dlon = s.lon - lon;
          const d2 = dlat * dlat + dlon * dlon;
          if (d2 < 1e-10) {
            wSum = 1; uSum = s.u; vSum = s.v;
            break;
          }
          const w = 1 / d2;
          wSum += w;
          uSum += w * s.u;
          vSum += w * s.v;
        }
        uGrid[r][c] = wSum > 0 ? uSum / wSum : 0;
        vGrid[r][c] = wSum > 0 ? vSum / wSum : 0;
      }
    }
    return { uGrid, vGrid };
  }, [rows, cols, stations, lat_min, lat_max, lon_min, lon_max]);
}

/**
 * Build a draped mesh colored by a signed scalar field.
 * Shared by vorticity and divergence overlays.
 */
function buildSignedOverlayGeometry(
  data: PressureGridData,
  field: number[][],
  colorFn: (t: number) => [number, number, number],
): THREE.PlaneGeometry {
  const { grid, rows, cols, pressure_min, pressure_max } = data;
  const sceneWidth = 10;
  const sceneDepth = 10 * (rows / cols);
  const pRange = (pressure_max - pressure_min) || 1;
  const heightScale = 8;

  // p95 normalization
  const allAbs: number[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      allAbs.push(Math.abs(field[r][c]));
    }
  }
  allAbs.sort((a, b) => a - b);
  const p95 = allAbs[Math.floor(allAbs.length * 0.95)] || 1;
  const normScale = Math.max(p95, 1e-10);

  const geo = new THREE.PlaneGeometry(sceneWidth, sceneDepth, cols - 1, rows - 1);
  geo.rotateX(-Math.PI / 2);

  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const idx = r * cols + c;
      const p = grid[r][c];
      const y = ((p - pressure_min) / pRange) * heightScale + 0.05;
      pos.setY(idx, y);

      const raw = field[r][c] / normScale;
      const clamped = Math.max(-1, Math.min(1, raw));
      const t = 0.5 + clamped * 0.5;
      const [cr, cg, cb] = colorFn(t);

      const intensity = Math.min(Math.abs(raw), 1);
      const blend = Math.pow(intensity, 0.8);
      const neutral = 0.35;
      colors[idx * 3] = neutral + (cr - neutral) * blend;
      colors[idx * 3 + 1] = neutral + (cg - neutral) * blend;
      colors[idx * 3 + 2] = neutral + (cb - neutral) * blend;
    }
  }
  pos.needsUpdate = true;
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));

  return geo;
}

// ---------------------------------------------------------------------------
// Vorticity overlay — curl of observed wind field (∂v/∂x - ∂u/∂y)
// ---------------------------------------------------------------------------

/**
 * Diverging color ramp for vorticity.
 * t=0 anticyclonic (warm red/orange), t=0.5 zero, t=1 cyclonic (cyan/blue).
 */
function vorticityColor(t: number): [number, number, number] {
  const tc = Math.max(0, Math.min(1, t));
  if (tc < 0.5) {
    const s = tc / 0.5;
    return [1.0 - 0.3 * s, 0.25 + 0.55 * s, 0.15 + 0.65 * s];
  } else {
    const s = (tc - 0.5) / 0.5;
    return [0.7 - 0.55 * s, 0.8 - 0.15 * s, 0.8 + 0.2 * s];
  }
}

function VorticityOverlay({ data, windGrid, opacity }: {
  data: PressureGridData;
  windGrid: { uGrid: number[][]; vGrid: number[][] };
  opacity: number;
}) {
  const { rows, cols } = data;
  const { uGrid, vGrid } = windGrid;

  const geometry = useMemo(() => {
    // Vorticity = ∂v/∂c - ∂u/∂r (c ~ x/lon, r ~ y/lat)
    const vort: number[][] = [];
    for (let r = 0; r < rows; r++) {
      vort[r] = [];
      for (let c = 0; c < cols; c++) {
        const dv_dc = c > 0 && c < cols - 1
          ? (vGrid[r][c + 1] - vGrid[r][c - 1]) / 2
          : c === 0 ? vGrid[r][1] - vGrid[r][0] : vGrid[r][c] - vGrid[r][c - 1];
        const du_dr = r > 0 && r < rows - 1
          ? (uGrid[r + 1][c] - uGrid[r - 1][c]) / 2
          : r === 0 ? uGrid[1][c] - uGrid[0][c] : uGrid[r][c] - uGrid[r - 1][c];
        vort[r][c] = dv_dc - du_dr;
      }
    }
    return buildSignedOverlayGeometry(data, vort, vorticityColor);
  }, [data, rows, cols, uGrid, vGrid]);

  return (
    <mesh geometry={geometry}>
      <meshBasicMaterial
        vertexColors
        transparent
        opacity={opacity}
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// Divergence overlay — ∂u/∂x + ∂v/∂y of observed wind field
// ---------------------------------------------------------------------------

/**
 * Diverging color ramp for convergence/divergence.
 * t=0 convergence (warm amber/red — updraft), t=0.5 zero, t=1 divergence (cool teal/blue — subsidence).
 */
function divergenceColor(t: number): [number, number, number] {
  const tc = Math.max(0, Math.min(1, t));
  if (tc < 0.5) {
    // Convergence (updraft): red-amber (0) → warm orange (0.25) → pale (0.5)
    const s = tc / 0.5;
    return [0.95 - 0.2 * s, 0.3 + 0.45 * s, 0.1 + 0.7 * s];
  } else {
    // Divergence (subsidence): pale (0.5) → teal (0.75) → deep blue-green (1)
    const s = (tc - 0.5) / 0.5;
    return [0.75 - 0.6 * s, 0.75 - 0.1 * s, 0.8 + 0.15 * s];
  }
}

function DivergenceOverlay({ data, windGrid, opacity }: {
  data: PressureGridData;
  windGrid: { uGrid: number[][]; vGrid: number[][] };
  opacity: number;
}) {
  const { rows, cols } = data;
  const { uGrid, vGrid } = windGrid;

  const geometry = useMemo(() => {
    // Divergence = ∂u/∂c + ∂v/∂r (c ~ x/lon, r ~ y/lat)
    const div: number[][] = [];
    for (let r = 0; r < rows; r++) {
      div[r] = [];
      for (let c = 0; c < cols; c++) {
        const du_dc = c > 0 && c < cols - 1
          ? (uGrid[r][c + 1] - uGrid[r][c - 1]) / 2
          : c === 0 ? uGrid[r][1] - uGrid[r][0] : uGrid[r][c] - uGrid[r][c - 1];
        const dv_dr = r > 0 && r < rows - 1
          ? (vGrid[r + 1][c] - vGrid[r - 1][c]) / 2
          : r === 0 ? vGrid[1][c] - vGrid[0][c] : vGrid[r][c] - vGrid[r - 1][c];
        div[r][c] = du_dc + dv_dr;
      }
    }
    return buildSignedOverlayGeometry(data, div, divergenceColor);
  }, [data, rows, cols, uGrid, vGrid]);

  return (
    <mesh geometry={geometry}>
      <meshBasicMaterial
        vertexColors
        transparent
        opacity={opacity}
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  );
}

function tempColor(t: number): [number, number, number] {
  // Vivid blue (cold, t=0) → purple (mid) → vivid red (hot, t=1)
  // Sigmoid contrast stretch so small deltas produce visible color shifts
  const tc = Math.max(0, Math.min(1, t));
  const s = 1 / (1 + Math.exp(-12 * (tc - 0.5))); // steep sigmoid, centered at 0.5
  return [
    0.1 + s * 0.9,           // R: 0.1 → 1.0
    0.15 * (1 - (2 * s - 1) ** 2), // G: low everywhere, slight bump at mid
    1.0 - s * 0.9,           // B: 1.0 → 0.1
  ];
}

function TemperatureOverlay({ data, opacity }: { data: PressureGridData; opacity: number }) {
  const { grid, rows, cols, pressure_min, pressure_max, stations } = data;
  const sceneWidth = 10;
  const sceneDepth = 10 * (rows / cols);
  const pRange = (pressure_max - pressure_min) || 1;
  const heightScale = 8;

  const { geometry } = useMemo(() => {
    // Collect stations with valid temperature
    const tempStations = stations.filter(
      (s): s is StationMarker & { temp_f: number } =>
        s.temp_f != null && s.lat != null && s.lon != null,
    );

    if (tempStations.length < 2) return { geometry: null, tMin: 0, tMax: 0 };

    const temps = tempStations.map((s) => s.temp_f);
    const tMin = Math.min(...temps);
    const tMax = Math.max(...temps);
    const tRange = tMax - tMin || 1;

    const { lat_min, lat_max, lon_min, lon_max } = data;

    const geo = new THREE.PlaneGeometry(sceneWidth, sceneDepth, cols - 1, rows - 1);
    geo.rotateX(-Math.PI / 2);

    const pos = geo.attributes.position;
    const colors = new Float32Array(pos.count * 3);

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const idx = r * cols + c;

        // Height from pressure grid (slight offset above surface, below radar)
        const p = grid[r][c];
        const pt = (p - pressure_min) / pRange;
        pos.setY(idx, pt * heightScale + 0.015);

        // IDW interpolation of temperature at this grid point
        const lat = lat_min + (r / (rows - 1)) * (lat_max - lat_min);
        const lon = lon_min + (c / (cols - 1)) * (lon_max - lon_min);

        let wSum = 0;
        let tSum = 0;
        for (const s of tempStations) {
          const dlat = s.lat - lat;
          const dlon = s.lon - lon;
          const d2 = dlat * dlat + dlon * dlon;
          if (d2 < 1e-10) {
            // Exactly on a station — use its value directly
            wSum = 1;
            tSum = s.temp_f;
            break;
          }
          const w = 1 / d2; // power=2
          wSum += w;
          tSum += w * s.temp_f;
        }
        const tempHere = wSum > 0 ? tSum / wSum : (tMin + tMax) / 2;
        const tt = (tempHere - tMin) / tRange;
        const [cr, cg, cb] = tempColor(tt);
        colors[idx * 3] = cr;
        colors[idx * 3 + 1] = cg;
        colors[idx * 3 + 2] = cb;
      }
    }

    geo.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    geo.computeVertexNormals();
    return { geometry: geo, tMin, tMax };
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!geometry) return null;

  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        vertexColors
        transparent
        opacity={opacity}
        side={THREE.DoubleSide}
        roughness={0.8}
        depthWrite={false}
      />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// State boundary lines — GeoJSON outlines drawn on the pressure surface
// ---------------------------------------------------------------------------

const STATES_GEOJSON_URL =
  "https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json";

function StateBoundaryLines({ data, isDark }: { data: PressureGridData; isDark: boolean }) {
  const { rows, cols, lat_min, lat_max, lon_min, lon_max,
          pressure_min, pressure_max, grid } = data;
  const sceneWidth = 10;
  const sceneDepth = 10 * (rows / cols);
  const halfW = sceneWidth / 2;
  const halfD = sceneDepth / 2;
  const pRange = pressure_max - pressure_min || 1;
  const heightScale = 8;

  const [arcs, setArcs] = useState<[number, number][][]>([]);

  useEffect(() => {
    let cancelled = false;
    fetch(STATES_GEOJSON_URL)
      .then((r) => r.json())
      .then((topo) => {
        if (cancelled) return;
        // TopoJSON → extract arcs and decode delta-encoded coordinates
        const { arcs: rawArcs, transform } = topo;
        const { scale, translate } = transform;
        const decoded: [number, number][][] = rawArcs.map((arc: number[][]) => {
          let x = 0, y = 0;
          return arc.map(([dx, dy]: number[]) => {
            x += dx;
            y += dy;
            return [x * scale[0] + translate[0], y * scale[1] + translate[1]] as [number, number];
          });
        });

        // Collect all arcs referenced by the states object
        const statesObj = topo.objects.states;
        const usedArcs: [number, number][][] = [];
        const resolveArc = (idx: number): [number, number][] => {
          if (idx >= 0) return decoded[idx];
          // Negative index means reversed arc (~idx
          return [...decoded[~idx]].reverse();
        };

        if (statesObj.type === "GeometryCollection") {
          for (const geom of statesObj.geometries) {
            if (geom.type === "Polygon") {
              for (const ring of geom.arcs) {
                const coords: [number, number][] = [];
                for (const idx of ring) coords.push(...resolveArc(idx));
                usedArcs.push(coords);
              }
            } else if (geom.type === "MultiPolygon") {
              for (const polygon of geom.arcs) {
                for (const ring of polygon) {
                  const coords: [number, number][] = [];
                  for (const idx of ring) coords.push(...resolveArc(idx));
                  usedArcs.push(coords);
                }
              }
            }
          }
        }
        setArcs(usedArcs);
      })
      .catch(() => { /* silently degrade — no boundaries shown */ });
    return () => { cancelled = true; };
  }, []);

  // Convert lat/lon to scene XZ + sample pressure grid for Y height
  const toScene = (lon: number, lat: number): [number, number, number] | null => {
    if (lon < lon_min || lon > lon_max || lat < lat_min || lat > lat_max) return null;
    const xNorm = (lon - lon_min) / (lon_max - lon_min);
    const zNorm = (lat - lat_min) / (lat_max - lat_min);
    const x = -halfW + xNorm * sceneWidth;
    const z = -halfD + zNorm * sceneDepth;

    // Sample grid for height (bilinear)
    const gr = zNorm * (rows - 1);
    const gc = xNorm * (cols - 1);
    const r0 = Math.min(Math.floor(gr), rows - 2);
    const c0 = Math.min(Math.floor(gc), cols - 2);
    const fr = gr - r0;
    const fc = gc - c0;
    const p = grid[r0][c0] * (1 - fr) * (1 - fc)
            + grid[r0][c0 + 1] * (1 - fr) * fc
            + grid[r0 + 1][c0] * fr * (1 - fc)
            + grid[r0 + 1][c0 + 1] * fr * fc;
    const y = ((p - pressure_min) / pRange) * heightScale + 0.02; // slight offset above surface

    return [x, y, z];
  };

  const lineSegments = useMemo(() => {
    const segments: THREE.BufferGeometry[] = [];
    for (const arc of arcs) {
      const points: THREE.Vector3[] = [];
      for (const [lon, lat] of arc) {
        const pt = toScene(lon, lat);
        if (pt) {
          points.push(new THREE.Vector3(...pt));
        } else if (points.length > 1) {
          // Clip: emit what we have so far and start a new segment
          const geo = new THREE.BufferGeometry().setFromPoints(points);
          segments.push(geo);
          points.length = 0;
        } else {
          points.length = 0;
        }
      }
      if (points.length > 1) {
        segments.push(new THREE.BufferGeometry().setFromPoints(points));
      }
    }
    return segments;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [arcs, data]);

  const lineMaterial = useMemo(
    () => new THREE.LineBasicMaterial({ color: isDark ? "#ffffff" : "#000000", opacity: 0.4, transparent: true }),
    [isDark],
  );

  return (
    <>
      {lineSegments.map((geo, i) => (
        <primitive key={i} object={new THREE.Line(geo, lineMaterial)} />
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Radar overlay — IEM NEXRAD tiles draped on the pressure surface
// ---------------------------------------------------------------------------

const RADAR_TILE_ZOOM = 6;
const TILE_PX = 256;

function lon2tileF(lon: number, z: number): number {
  return (lon + 180) / 360 * Math.pow(2, z);
}

function lat2tileF(lat: number, z: number): number {
  const r = lat * Math.PI / 180;
  return (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * Math.pow(2, z);
}

function RadarOverlay({ data, opacity, radarTs }: {
  data: PressureGridData; opacity: number; radarTs: number;
}) {
  const { rows, cols, lat_min, lat_max, lon_min, lon_max,
          pressure_min, pressure_max, grid } = data;
  const sceneWidth = 10;
  const sceneDepth = 10 * (rows / cols);
  const heightScale = 8;
  const pRange = pressure_max - pressure_min || 1;

  const [texture, setTexture] = useState<THREE.CanvasTexture | null>(null);

  // Tile range (stable across renders for the same grid bounds)
  const tiles = useMemo(() => {
    const z = RADAR_TILE_ZOOM;
    const txMin = Math.floor(lon2tileF(lon_min, z));
    const txMax = Math.floor(lon2tileF(lon_max, z));
    const tyMin = Math.floor(lat2tileF(lat_max, z)); // north = smaller Y
    const tyMax = Math.floor(lat2tileF(lat_min, z));
    return { txMin, txMax, tyMin, tyMax, nx: txMax - txMin + 1, ny: tyMax - tyMin + 1 };
  }, [lon_min, lon_max, lat_min, lat_max]);

  // Fetch tiles → composite → CanvasTexture
  useEffect(() => {
    let cancelled = false;
    const { txMin, txMax, tyMin, tyMax, nx, ny } = tiles;
    const z = RADAR_TILE_ZOOM;

    const canvas = document.createElement("canvas");
    canvas.width = nx * TILE_PX;
    canvas.height = ny * TILE_PX;
    const ctx = canvas.getContext("2d")!;

    const promises: Promise<void>[] = [];
    for (let ty = tyMin; ty <= tyMax; ty++) {
      for (let tx = txMin; tx <= txMax; tx++) {
        const px = (tx - txMin) * TILE_PX;
        const py = (ty - tyMin) * TILE_PX;
        const url = `https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q/${z}/${tx}/${ty}.png?_=${radarTs}`;
        promises.push(new Promise<void>((resolve) => {
          const img = new Image();
          img.crossOrigin = "anonymous";
          img.onload = () => { if (!cancelled) ctx.drawImage(img, px, py); resolve(); };
          img.onerror = () => resolve();
          img.src = url;
        }));
      }
    }

    Promise.all(promises).then(() => {
      if (cancelled) return;
      const tex = new THREE.CanvasTexture(canvas);
      tex.minFilter = THREE.LinearFilter;
      tex.magFilter = THREE.LinearFilter;
      setTexture((prev) => { prev?.dispose(); return tex; });
    });

    return () => { cancelled = true; };
  }, [tiles, radarTs]);

  // Build geometry with pressure-surface height + custom UVs for tile mapping
  const geometry = useMemo(() => {
    const { txMin, tyMin, nx, ny } = tiles;
    const z = RADAR_TILE_ZOOM;

    const geo = new THREE.PlaneGeometry(sceneWidth, sceneDepth, cols - 1, rows - 1);
    geo.rotateX(-Math.PI / 2);

    const pos = geo.attributes.position;
    const uv = geo.attributes.uv;

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const idx = r * cols + c;

        // Height from pressure grid (tiny offset above pressure surface)
        const p = grid[r][c];
        const t = (p - pressure_min) / pRange;
        pos.setY(idx, t * heightScale + 0.01);

        // Geo position of this vertex
        const lon = lon_min + (c / (cols - 1)) * (lon_max - lon_min);
        const lat = lat_min + (r / (rows - 1)) * (lat_max - lat_min);

        // Map to fractional tile coords → canvas UV
        const fracX = lon2tileF(lon, z);
        const fracY = lat2tileF(lat, z);
        const u_val = (fracX - txMin) / nx;
        const v_val = 1 - (fracY - tyMin) / ny; // flip: canvas Y↓, texture V↑
        uv.setXY(idx, u_val, v_val);
      }
    }
    geo.computeVertexNormals();
    return geo;
  }, [data, tiles]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!texture) return null;

  return (
    <mesh geometry={geometry}>
      <meshBasicMaterial
        map={texture}
        transparent
        opacity={opacity}
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// Station markers — small spheres at actual measurement locations
// ---------------------------------------------------------------------------

interface MarkerPos {
  position: [number, number, number];
  station: StationMarker;
}

function StationMarkers({ data, selected, onSelect }: {
  data: PressureGridData;
  selected: StationMarker | null;
  onSelect: (s: StationMarker | null) => void;
}) {
  const markers: MarkerPos[] = useMemo(() => {
    const { rows, cols, lat_min, lat_max, lon_min, lon_max,
            pressure_min, pressure_max, stations } = data;
    const pRange = pressure_max - pressure_min || 1;
    const sceneWidth = 10;
    const sceneDepth = 10 * (rows / cols);
    const heightScale = 8;

    return stations.map((s) => {
      const xNorm = (s.lon - lon_min) / (lon_max - lon_min);
      const zNorm = (s.lat - lat_min) / (lat_max - lat_min);
      const tP = (s.pressure_hpa - pressure_min) / pRange;
      return {
        position: [
          -sceneWidth / 2 + xNorm * sceneWidth,
          tP * heightScale + 0.08,
          -sceneDepth / 2 + zNorm * sceneDepth,
        ] as [number, number, number],
        station: s,
      };
    });
  }, [data]);

  const [hovered, setHovered] = useState<number | null>(null);

  const labelStyle: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 600,
    color: "#fff",
    background: "rgba(0,0,0,0.7)",
    padding: "2px 6px",
    borderRadius: 4,
    whiteSpace: "nowrap",
    pointerEvents: "none",
    userSelect: "none",
    textShadow: "0 1px 2px rgba(0,0,0,0.8)",
  };

  return (
    <>
      {markers.map((m, i) => {
        const isSelected = selected && selected.lat === m.station.lat && selected.lon === m.station.lon;
        const isHovered = hovered === i;
        const isHome = m.station.is_home === true;
        const showLabel = isHovered || isSelected;

        // Color priority: selected > hovered > home > default
        const baseColor = isHome ? "#34d399" : "#ffffff";  // green for home
        const color = isSelected ? "#fbbf24" : isHovered ? "#93c5fd" : baseColor;
        const intensity = isSelected ? 0.6 : isHovered ? 0.5 : isHome ? 0.5 : 0.3;
        const radius = isSelected ? 0.08 : (isHovered || isHome) ? 0.06 : 0.035;

        return (
          <group key={i} position={m.position}>
            <mesh
              onClick={(e) => {
                e.stopPropagation();
                onSelect(isSelected ? null : m.station);
              }}
              onPointerOver={(e) => { e.stopPropagation(); setHovered(i); document.body.style.cursor = "pointer"; }}
              onPointerOut={() => { setHovered(null); document.body.style.cursor = "auto"; }}
            >
              {isHome
                ? <octahedronGeometry args={[radius * 1.4, 0]} />
                : <sphereGeometry args={[radius, 12, 12]} />
              }
              <meshStandardMaterial
                color={color}
                emissive={color}
                emissiveIntensity={intensity}
              />
            </mesh>
            {showLabel && (
              <Html
                position={[0, 0.2, 0]}
                center
                distanceFactor={12}
                occlude={false}
                zIndexRange={[10, 0]}
              >
                <div style={labelStyle}>
                  {m.station.name || m.station.id || `${m.station.pressure_hpa} hPa`}
                </div>
              </Html>
            )}
          </group>
        );
      })}
    </>
  );
}

// ---------------------------------------------------------------------------
// Ground labels — lat/lon tick marks on the base plane edges
// ---------------------------------------------------------------------------

function GroundLabels({ data }: { data: PressureGridData }) {
  const { rows, cols, lat_min, lat_max, lon_min, lon_max } = data;
  const sceneWidth = 10;
  const sceneDepth = 10 * (rows / cols);
  const halfW = sceneWidth / 2;
  const halfD = sceneDepth / 2;
  const baseY = -0.3;

  const labels: { pos: [number, number, number]; text: string }[] = [];

  // Longitude labels along the front edge (south), every ~1 degree
  const lonStep = Math.max(0.5, Math.round((lon_max - lon_min) / 5));
  const lonStart = Math.ceil(lon_min / lonStep) * lonStep;
  for (let lon = lonStart; lon <= lon_max; lon += lonStep) {
    const xNorm = (lon - lon_min) / (lon_max - lon_min);
    labels.push({
      pos: [-halfW + xNorm * sceneWidth, baseY, -halfD - 0.3],
      text: `${lon.toFixed(1)}°`,
    });
  }

  // Latitude labels along the left edge (west), every ~1 degree
  const latStep = Math.max(0.5, Math.round((lat_max - lat_min) / 5));
  const latStart = Math.ceil(lat_min / latStep) * latStep;
  for (let lat = latStart; lat <= lat_max; lat += latStep) {
    const zNorm = (lat - lat_min) / (lat_max - lat_min);
    labels.push({
      pos: [-halfW - 0.3, baseY, -halfD + zNorm * sceneDepth],
      text: `${lat.toFixed(1)}°`,
    });
  }

  const style: React.CSSProperties = {
    fontSize: 9,
    fontWeight: 500,
    color: "rgba(255,255,255,0.6)",
    whiteSpace: "nowrap",
    pointerEvents: "none",
    userSelect: "none",
  };

  return (
    <>
      {labels.map((l, i) => (
        <Html key={i} position={l.pos} center distanceFactor={16} occlude={false}>
          <div style={style}>{l.text}</div>
        </Html>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Cardinal direction indicators — N/S/E/W at mesh edges
// ---------------------------------------------------------------------------

function CardinalLabels({ data }: { data: PressureGridData }) {
  const { rows, cols } = data;
  const sceneWidth = 10;
  const sceneDepth = 10 * (rows / cols);
  const halfW = sceneWidth / 2;
  const halfD = sceneDepth / 2;

  const dirs: { pos: [number, number, number]; text: string }[] = [
    { pos: [0, 0.5, halfD + 0.6], text: "N" },
    { pos: [0, 0.5, -halfD - 0.6], text: "S" },
    { pos: [halfW + 0.6, 0.5, 0], text: "E" },
    { pos: [-halfW - 0.6, 0.5, 0], text: "W" },
  ];

  const style: React.CSSProperties = {
    fontSize: 14,
    fontWeight: 700,
    color: "rgba(255,255,255,0.75)",
    textShadow: "0 1px 4px rgba(0,0,0,0.6)",
    pointerEvents: "none",
    userSelect: "none",
  };

  return (
    <>
      {dirs.map((d) => (
        <Html key={d.text} position={d.pos} center distanceFactor={14} occlude={false}>
          <div style={style}>{d.text}</div>
        </Html>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Vertical pressure scale — tick marks along the Z (height) axis
// ---------------------------------------------------------------------------

function PressureScale({ data, pressureUnit }: { data: PressureGridData; pressureUnit: string }) {
  const { rows, cols, pressure_min, pressure_max } = data;
  const sceneWidth = 10;
  const sceneDepth = 10 * (rows / cols);
  const halfW = sceneWidth / 2;
  const halfD = sceneDepth / 2;
  const heightScale = 8;
  const pRange = pressure_max - pressure_min || 1;

  // Generate ~4-6 evenly spaced pressure ticks
  const tickCount = 5;
  const ticks: { y: number; label: string }[] = [];
  for (let i = 0; i <= tickCount; i++) {
    const t = i / tickCount;
    const hpa = pressure_min + t * pRange;
    const y = t * heightScale;
    ticks.push({ y, label: fmtPressure(hpa, pressureUnit) });
  }

  const style: React.CSSProperties = {
    fontSize: 9,
    fontWeight: 500,
    color: "rgba(255,255,255,0.6)",
    whiteSpace: "nowrap",
    pointerEvents: "none",
    userSelect: "none",
  };

  return (
    <>
      {ticks.map((tick, i) => (
        <group key={i}>
          <Html
            position={[-halfW - 0.6, tick.y, -halfD - 0.3]}
            center
            distanceFactor={16}
            occlude={false}
          >
            <div style={style}>{tick.label}</div>
          </Html>
          {/* Small tick line */}
          <mesh position={[-halfW - 0.15, tick.y, -halfD - 0.15]}>
            <boxGeometry args={[0.3, 0.02, 0.02]} />
            <meshBasicMaterial color="rgba(255,255,255,0.3)" transparent opacity={0.3} />
          </mesh>
        </group>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Camera controls — orbit + optional auto-rotation + external zoom
// ---------------------------------------------------------------------------

function CameraControls({ rotating, zoom, onBearing }: {
  rotating: boolean; zoom: number; onBearing?: (deg: number) => void;
}) {
  const controlsRef = useRef<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  useFrame((state) => {
    if (!controlsRef.current) return;
    controlsRef.current.autoRotate = rotating;
    controlsRef.current.autoRotateSpeed = 0.5;

    // Zoom: adjust camera distance from target (10 = far, 30 = close)
    const cam = state.camera;
    const target = controlsRef.current.target as THREE.Vector3;
    const dir = cam.position.clone().sub(target).normalize();
    const desiredDist = 22 - zoom * 0.16; // zoom 0→dist 22, zoom 100→dist 6
    const currentDist = cam.position.distanceTo(target);
    const newDist = THREE.MathUtils.lerp(currentDist, desiredDist, 0.08);
    cam.position.copy(target).addScaledVector(dir, newDist);

    controlsRef.current.update();

    // Report camera bearing (azimuth from north) for compass rose.
    // Bearing = camera facing direction relative to scene north (+Z).
    // Scene has scale={[-1,1,1]} so scene-east is world -X.
    // atan2(dx, -dz) gives clockwise angle from north toward east.
    if (onBearing) {
      const dx = cam.position.x - target.x;
      const dz = cam.position.z - target.z;
      const bearing = (Math.atan2(dx, -dz) * 180 / Math.PI + 360) % 360;
      onBearing(bearing);
    }
  });
  return <OrbitControls ref={controlsRef} enableDamping dampingFactor={0.1} target={[0, 2, 0]} />;
}

// ---------------------------------------------------------------------------
// Compass rose — fixed HUD overlay showing camera bearing relative to north
// ---------------------------------------------------------------------------

function CompassRose({ bearing, isDark }: { bearing: number; isDark: boolean }) {
  const size = 88;
  const mid = size / 2;
  const ptrLen = 18; // pointer length from center
  const labelR = mid - 8; // radius for cardinal labels

  const cardinals: { label: string; angle: number; primary: boolean }[] = [
    { label: "N", angle: 0, primary: true },
    { label: "E", angle: 90, primary: false },
    { label: "S", angle: 180, primary: false },
    { label: "W", angle: 270, primary: false },
  ];

  return (
    <div style={{
      position: "absolute",
      top: 72,
      right: 12,
      zIndex: 10,
      width: size,
      height: size,
      pointerEvents: "none",
    }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Outer ring */}
        <circle cx={mid} cy={mid} r={mid - 3}
          fill={isDark ? "rgba(15,15,30,0.85)" : "rgba(255,255,255,0.88)"}
          stroke={isDark ? "rgba(255,255,255,0.2)" : "rgba(0,0,0,0.15)"} strokeWidth={1.5} />
        {/* Tick marks at 30° increments */}
        {Array.from({ length: 12 }, (_, i) => {
          const a = (i * 30 - bearing) * Math.PI / 180;
          const isMajor = i % 3 === 0;
          const r1 = mid - (isMajor ? 16 : 12);
          const r2 = mid - 5;
          return (
            <line key={i}
              x1={mid + r1 * Math.sin(a)} y1={mid - r1 * Math.cos(a)}
              x2={mid + r2 * Math.sin(a)} y2={mid - r2 * Math.cos(a)}
              stroke={isDark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.08)"}
              strokeWidth={isMajor ? 1.5 : 0.75}
            />
          );
        })}
        {/* Rotating group — spins opposite to camera bearing */}
        <g transform={`rotate(${-bearing}, ${mid}, ${mid})`}>
          {/* North pointer (red) */}
          <polygon
            points={`${mid},${mid - ptrLen} ${mid - 5},${mid} ${mid + 5},${mid}`}
            fill="#e74c3c"
          />
          {/* South pointer (subtle) */}
          <polygon
            points={`${mid},${mid + ptrLen} ${mid - 5},${mid} ${mid + 5},${mid}`}
            fill={isDark ? "rgba(255,255,255,0.18)" : "rgba(0,0,0,0.12)"}
          />
          {/* Cardinal labels */}
          {cardinals.map((c) => {
            const rad = (c.angle * Math.PI) / 180;
            const lx = mid + labelR * Math.sin(rad);
            const ly = mid - labelR * Math.cos(rad);
            return (
              <text key={c.label} x={lx} y={ly}
                textAnchor="middle" dominantBaseline="central"
                fontSize={c.primary ? 13 : 11}
                fontWeight={c.primary ? 700 : 600}
                fill={c.primary ? "#e74c3c" : (isDark ? "rgba(255,255,255,0.7)" : "rgba(0,0,0,0.5)")}
              >
                {c.label}
              </text>
            );
          })}
        </g>
        {/* Fixed center dot */}
        <circle cx={mid} cy={mid} r={2.5} fill={isDark ? "#ddd" : "#444"} />
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scene wrapper
// ---------------------------------------------------------------------------

function PressureFieldScene({ data, isDark, selected, onSelect, rotating, zoom, radarVisible, radarOpacity, radarTs, flowVisible, coriolisEnabled, statesVisible, stationsVisible, tempVisible, tempOpacity, vorticityVisible, vorticityOpacity, divergenceVisible, divergenceOpacity, onBearing }: {
  data: PressureGridData; isDark: boolean;
  selected: StationMarker | null; onSelect: (s: StationMarker | null) => void;
  rotating: boolean; zoom: number;
  radarVisible: boolean; radarOpacity: number; radarTs: number;
  flowVisible: boolean; coriolisEnabled: boolean;
  statesVisible: boolean; stationsVisible: boolean;
  tempVisible: boolean; tempOpacity: number;
  vorticityVisible: boolean; vorticityOpacity: number;
  divergenceVisible: boolean; divergenceOpacity: number;
  onBearing?: (deg: number) => void;
}) {
  // Shared wind grid — computed once, used by both vorticity and divergence
  const windGrid = useWindGrid(data);

  return (
    <Canvas
      camera={{ position: [0, 10, -14], fov: 45, near: 0.1, far: 100 }}
      style={{ width: "100%", height: "100%", background: isDark ? "#1a1a2e" : "#e8ecf1" }}
      onPointerMissed={() => onSelect(null)}
    >
      <ambientLight intensity={isDark ? 0.4 : 0.5} />
      <directionalLight position={[5, 8, 5]} intensity={isDark ? 0.8 : 1.0} />
      <directionalLight position={[-3, 4, -3]} intensity={0.3} />
      {/* Mirror X axis so the surface matches standard map orientation */}
      <group scale={[-1, 1, 1]}>
        <PressureSurface data={data} />
        <SideWalls data={data} />
        {tempVisible && <TemperatureOverlay data={data} opacity={tempOpacity} />}
        {vorticityVisible && windGrid && <VorticityOverlay data={data} windGrid={windGrid} opacity={vorticityOpacity} />}
        {divergenceVisible && windGrid && <DivergenceOverlay data={data} windGrid={windGrid} opacity={divergenceOpacity} />}
        {radarVisible && <RadarOverlay data={data} opacity={radarOpacity} radarTs={radarTs} />}
        {flowVisible && <GradientFlowLines data={data} coriolis={coriolisEnabled} />}
        {statesVisible && <StateBoundaryLines data={data} isDark={isDark} />}
        {stationsVisible && <StationMarkers data={data} selected={selected} onSelect={onSelect} />}
        <GroundLabels data={data} />
        <CardinalLabels data={data} />
        <PressureScale data={data} pressureUnit={data.pressure_unit || "hPa"} />
      </group>
      <CameraControls rotating={rotating} zoom={zoom} onBearing={onBearing} />
    </Canvas>
  );
}

// ---------------------------------------------------------------------------
// Info panel
// ---------------------------------------------------------------------------

function InfoPanel({ data, isDark }: { data: PressureGridData; isDark: boolean }) {
  const pu = data.pressure_unit || "hPa";
  const pMin = fmtPressure(data.pressure_min, pu);
  const pMax = fmtPressure(data.pressure_max, pu);

  const panelStyle: React.CSSProperties = {
    position: "absolute",
    top: 12,
    left: 12,
    zIndex: 10,
    background: isDark ? "rgba(20, 20, 40, 0.85)" : "rgba(255, 255, 255, 0.9)",
    border: `1px solid ${isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)"}`,
    borderRadius: 8,
    padding: "10px 14px",
    color: isDark ? "#ccc" : "#333",
    fontSize: 12,
    lineHeight: 1.6,
    backdropFilter: "blur(8px)",
    maxWidth: 220,
  };

  const legendBar: React.CSSProperties = {
    height: 10,
    borderRadius: 3,
    background: "linear-gradient(to right, #1a1af2, #1a73e6, #1abfcc, #26cc66, #66d126, #ccb31a, #f2731a, #d91f0d)",
    margin: "4px 0",
  };

  return (
    <div style={panelStyle}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Pressure Field</div>
      <div>Stations: {data.station_count}</div>
      <div>Range: {pMin} – {pMax}</div>
      <div>Grid: {data.rows} × {data.cols}</div>
      <div style={{ marginTop: 6, fontSize: 10, color: isDark ? "#888" : "#999" }}>Low → High</div>
      <div style={legendBar} />
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: isDark ? "#888" : "#999" }}>
        <span>{pMin}</span>
        <span>{pMax}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Temperature color scale — shown when temp layer is active
// ---------------------------------------------------------------------------

function TempScale({ tMin, tMax, isDark, tempUnit }: {
  tMin: number; tMax: number; isDark: boolean; tempUnit: string;
}) {
  // Build CSS gradient matching tempColor sigmoid ramp
  const stops: string[] = [];
  for (let i = 0; i <= 10; i++) {
    const t = i / 10;
    const [r, g, b] = tempColor(t);
    stops.push(`rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`);
  }

  const panelStyle: React.CSSProperties = {
    position: "absolute",
    top: 160,
    left: 12,
    zIndex: 10,
    background: isDark ? "rgba(20, 20, 40, 0.85)" : "rgba(255, 255, 255, 0.9)",
    border: `1px solid ${isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)"}`,
    borderRadius: 8,
    padding: "8px 12px",
    color: isDark ? "#ccc" : "#333",
    fontSize: 11,
    lineHeight: 1.5,
    backdropFilter: "blur(8px)",
    maxWidth: 180,
  };

  return (
    <div style={panelStyle}>
      <div style={{ fontWeight: 600, marginBottom: 3, fontSize: 11 }}>Temperature</div>
      <div style={{ fontSize: 10, color: isDark ? "#888" : "#999" }}>Cool → Warm</div>
      <div style={{
        height: 8,
        borderRadius: 3,
        background: `linear-gradient(to right, ${stops.join(", ")})`,
        margin: "3px 0",
      }} />
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: isDark ? "#888" : "#999" }}>
        <span>{fmtTemp(tMin, tempUnit)}</span>
        <span>{fmtTemp(tMax, tempUnit)}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Vorticity color scale — shown when vorticity layer is active
// ---------------------------------------------------------------------------

function VorticityScale({ isDark, offsetTop }: { isDark: boolean; offsetTop: number }) {
  // Build CSS gradient matching vorticityColor ramp
  const stops: string[] = [];
  for (let i = 0; i <= 10; i++) {
    const t = i / 10;
    const [r, g, b] = vorticityColor(t);
    stops.push(`rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`);
  }

  const panelStyle: React.CSSProperties = {
    position: "absolute",
    top: offsetTop,
    left: 12,
    zIndex: 10,
    background: isDark ? "rgba(20, 20, 40, 0.85)" : "rgba(255, 255, 255, 0.9)",
    border: `1px solid ${isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)"}`,
    borderRadius: 8,
    padding: "8px 12px",
    color: isDark ? "#ccc" : "#333",
    fontSize: 11,
    lineHeight: 1.5,
    backdropFilter: "blur(8px)",
    maxWidth: 180,
  };

  return (
    <div style={panelStyle}>
      <div style={{ fontWeight: 600, marginBottom: 3, fontSize: 11 }}>Vorticity</div>
      <div style={{ fontSize: 10, color: isDark ? "#888" : "#999" }}>Anticyclonic → Cyclonic</div>
      <div style={{
        height: 8,
        borderRadius: 3,
        background: `linear-gradient(to right, ${stops.join(", ")})`,
        margin: "3px 0",
      }} />
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: isDark ? "#888" : "#999" }}>
        <span>-</span>
        <span>+</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Divergence color scale — shown when divergence layer is active
// ---------------------------------------------------------------------------

function DivergenceScale({ isDark, offsetTop }: { isDark: boolean; offsetTop: number }) {
  const stops: string[] = [];
  for (let i = 0; i <= 10; i++) {
    const t = i / 10;
    const [r, g, b] = divergenceColor(t);
    stops.push(`rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`);
  }

  const panelStyle: React.CSSProperties = {
    position: "absolute",
    top: offsetTop,
    left: 12,
    zIndex: 10,
    background: isDark ? "rgba(20, 20, 40, 0.85)" : "rgba(255, 255, 255, 0.9)",
    border: `1px solid ${isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)"}`,
    borderRadius: 8,
    padding: "8px 12px",
    color: isDark ? "#ccc" : "#333",
    fontSize: 11,
    lineHeight: 1.5,
    backdropFilter: "blur(8px)",
    maxWidth: 180,
  };

  return (
    <div style={panelStyle}>
      <div style={{ fontWeight: 600, marginBottom: 3, fontSize: 11 }}>Convergence / Divergence</div>
      <div style={{ fontSize: 10, color: isDark ? "#888" : "#999" }}>Updraft → Subsidence</div>
      <div style={{
        height: 8,
        borderRadius: 3,
        background: `linear-gradient(to right, ${stops.join(", ")})`,
        margin: "3px 0",
      }} />
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: isDark ? "#888" : "#999" }}>
        <span>Conv</span>
        <span>Div</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Layers popover panel
// ---------------------------------------------------------------------------

function LayersPanel({ isDark, ...props }: {
  isDark: boolean;
  radarVisible: boolean; setRadarVisible: (v: boolean) => void;
  radarOpacity: number; setRadarOpacity: (v: number) => void;
  flowVisible: boolean; setFlowVisible: (v: boolean) => void;
  coriolisEnabled: boolean; setCoriolisEnabled: (v: boolean) => void;
  tempVisible: boolean; setTempVisible: (v: boolean) => void;
  tempOpacity: number; setTempOpacity: (v: number) => void;
  vorticityVisible: boolean; setVorticityVisible: (v: boolean) => void;
  vorticityOpacity: number; setVorticityOpacity: (v: number) => void;
  divergenceVisible: boolean; setDivergenceVisible: (v: boolean) => void;
  divergenceOpacity: number; setDivergenceOpacity: (v: number) => void;
  statesVisible: boolean; setStatesVisible: (v: boolean) => void;
  stationsVisible: boolean; setStationsVisible: (v: boolean) => void;
}) {
  const panelStyle: React.CSSProperties = {
    position: "absolute",
    bottom: 56,
    right: 12,
    zIndex: 10,
    background: isDark ? "rgba(20, 20, 40, 0.92)" : "rgba(255, 255, 255, 0.95)",
    border: `1px solid ${isDark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.1)"}`,
    borderRadius: 8,
    padding: "10px 14px",
    color: isDark ? "#ccc" : "#333",
    fontSize: 11,
    lineHeight: 1.8,
    backdropFilter: "blur(10px)",
    minWidth: 170,
  };

  const rowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 6,
  };

  const sliderStyle: React.CSSProperties = {
    width: 50,
    accentColor: "var(--color-accent)",
    marginLeft: "auto",
  };

  const subRowStyle: React.CSSProperties = {
    ...rowStyle,
    paddingLeft: 18,
    opacity: 0.85,
  };

  return (
    <div style={panelStyle}>
      <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 12 }}>Layers</div>

      {/* Radar */}
      <label style={rowStyle}>
        <input type="checkbox" checked={props.radarVisible}
          onChange={(e) => props.setRadarVisible(e.target.checked)}
          style={{ accentColor: "var(--color-accent)" }} />
        Radar
        {props.radarVisible && (
          <input type="range" min={0} max={100}
            value={Math.round(props.radarOpacity * 100)}
            onChange={(e) => props.setRadarOpacity(Number(e.target.value) / 100)}
            style={sliderStyle} />
        )}
      </label>

      {/* Flow */}
      <label style={rowStyle}>
        <input type="checkbox" checked={props.flowVisible}
          onChange={(e) => props.setFlowVisible(e.target.checked)}
          style={{ accentColor: "var(--color-accent)" }} />
        Flow
      </label>
      {props.flowVisible && (
        <label style={subRowStyle}>
          <input type="checkbox" checked={props.coriolisEnabled}
            onChange={(e) => props.setCoriolisEnabled(e.target.checked)}
            style={{ accentColor: "var(--color-accent)" }} />
          Coriolis
        </label>
      )}

      {/* Vorticity */}
      <label style={rowStyle}>
        <input type="checkbox" checked={props.vorticityVisible}
          onChange={(e) => props.setVorticityVisible(e.target.checked)}
          style={{ accentColor: "var(--color-accent)" }} />
        Vorticity
        {props.vorticityVisible && (
          <input type="range" min={0} max={100}
            value={Math.round(props.vorticityOpacity * 100)}
            onChange={(e) => props.setVorticityOpacity(Number(e.target.value) / 100)}
            style={sliderStyle} />
        )}
      </label>

      {/* Divergence */}
      <label style={rowStyle}>
        <input type="checkbox" checked={props.divergenceVisible}
          onChange={(e) => props.setDivergenceVisible(e.target.checked)}
          style={{ accentColor: "var(--color-accent)" }} />
        Divergence
        {props.divergenceVisible && (
          <input type="range" min={0} max={100}
            value={Math.round(props.divergenceOpacity * 100)}
            onChange={(e) => props.setDivergenceOpacity(Number(e.target.value) / 100)}
            style={sliderStyle} />
        )}
      </label>

      {/* Temp */}
      <label style={rowStyle}>
        <input type="checkbox" checked={props.tempVisible}
          onChange={(e) => props.setTempVisible(e.target.checked)}
          style={{ accentColor: "var(--color-accent)" }} />
        Temp
        {props.tempVisible && (
          <input type="range" min={0} max={100}
            value={Math.round(props.tempOpacity * 100)}
            onChange={(e) => props.setTempOpacity(Number(e.target.value) / 100)}
            style={sliderStyle} />
        )}
      </label>

      {/* States */}
      <label style={rowStyle}>
        <input type="checkbox" checked={props.statesVisible}
          onChange={(e) => props.setStatesVisible(e.target.checked)}
          style={{ accentColor: "var(--color-accent)" }} />
        States
      </label>

      {/* Stations */}
      <label style={rowStyle}>
        <input type="checkbox" checked={props.stationsVisible}
          onChange={(e) => props.setStationsVisible(e.target.checked)}
          style={{ accentColor: "var(--color-accent)" }} />
        Stations
      </label>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Station detail panel — shown when a station marker is clicked
// ---------------------------------------------------------------------------

function StationDetailPanel({ station, isDark, onClose, units }: {
  station: StationMarker; isDark: boolean; onClose: () => void;
  units: { pressure: string; temp: string; wind: string };
}) {
  const panelStyle: React.CSSProperties = {
    position: "absolute",
    top: 12,
    right: 12,
    zIndex: 10,
    background: isDark ? "rgba(20, 20, 40, 0.92)" : "rgba(255, 255, 255, 0.95)",
    border: `1px solid ${isDark ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.12)"}`,
    borderRadius: 8,
    padding: "12px 16px",
    color: isDark ? "#ddd" : "#222",
    fontSize: 12,
    lineHeight: 1.7,
    backdropFilter: "blur(8px)",
    minWidth: 200,
    maxWidth: 260,
  };

  const headStyle: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 8,
    marginBottom: 6,
  };

  const closeBtn: React.CSSProperties = {
    background: "none",
    border: "none",
    color: isDark ? "#888" : "#999",
    cursor: "pointer",
    fontSize: 16,
    padding: 0,
    lineHeight: 1,
  };

  const mutedStyle: React.CSSProperties = {
    color: isDark ? "#888" : "#999",
    fontSize: 11,
  };

  return (
    <div style={panelStyle}>
      <div style={headStyle}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 13 }}>{station.name || station.id || "Station"}</div>
          {station.source && <div style={mutedStyle}>{station.source}{station.id ? ` · ${station.id}` : ""}</div>}
        </div>
        <button style={closeBtn} onClick={onClose} title="Close">{"\u2715"}</button>
      </div>
      <div>Pressure: {fmtPressure(station.pressure_hpa, units.pressure)}</div>
      {station.temp_f != null && <div>Temp: {fmtTemp(station.temp_f, units.temp)}</div>}
      {station.wind_mph != null && (
        <div>Wind: {fmtWind(station.wind_mph, units.wind)}
          {station.wind_dir != null && ` @ ${Math.round(station.wind_dir)}°`}
        </div>
      )}
      {station.updated && (
        <div style={mutedStyle}>
          Updated: {new Date(station.updated).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export default function PressureField() {
  const { themeName } = useTheme();
  const isDark = themeName === "dark";

  const [data, setData] = useState<PressureGridData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedStation, setSelectedStation] = useState<StationMarker | null>(null);
  const [rotating, setRotating] = useState(true);
  const [zoom, setZoom] = useState(50);
  const [radarVisible, setRadarVisible] = useState(true);
  const [radarOpacity, setRadarOpacity] = useState(0.6);
  const [radarTs, setRadarTs] = useState(() => Math.floor(Date.now() / 300000));
  const [flowVisible, setFlowVisible] = useState(false);
  const [statesVisible, setStatesVisible] = useState(true);
  const [stationsVisible, setStationsVisible] = useState(true);
  const [coriolisEnabled, setCoriolisEnabled] = useState(false);
  const [tempVisible, setTempVisible] = useState(false);
  const [tempOpacity, setTempOpacity] = useState(0.6);
  const [vorticityVisible, setVorticityVisible] = useState(false);
  const [vorticityOpacity, setVorticityOpacity] = useState(0.7);
  const [divergenceVisible, setDivergenceVisible] = useState(false);
  const [divergenceOpacity, setDivergenceOpacity] = useState(0.7);
  const [layersOpen, setLayersOpen] = useState(false);
  const [bearing, setBearing] = useState(0);
  const bearingRef = useRef(0);
  // Throttle bearing updates to avoid re-rendering every frame
  const handleBearing = useMemo(() => {
    let rafId = 0;
    return (deg: number) => {
      bearingRef.current = deg;
      if (!rafId) {
        rafId = requestAnimationFrame(() => {
          setBearing(bearingRef.current);
          rafId = 0;
        });
      }
    };
  }, []);

  // Refresh radar tile cache-buster every 5 minutes
  useEffect(() => {
    const id = setInterval(() => setRadarTs(Math.floor(Date.now() / 300000)), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const fetchGrid = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/map/pressure-grid`, { credentials: "same-origin" });
        if (!res.ok) throw new Error(`API ${res.status}`);
        const json = await res.json();
        if (cancelled) return;
        if (!json.grid || json.grid.length === 0) {
          setError("Not enough station data for pressure field visualization.");
        } else {
          setData(json as PressureGridData);
          setError(null);
        }
      } catch (err) {
        if (!cancelled && !data) setError("Failed to load pressure grid data.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchGrid();
    const interval = setInterval(fetchGrid, 5 * 60 * 1000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const containerStyle: React.CSSProperties = {
    flex: 1,
    position: "relative",
    overflow: "hidden",
    height: "100%",
    minHeight: 0,
  };

  const spinnerStyle: React.CSSProperties = {
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    flex: 1,
    color: "var(--color-text-muted)",
    fontSize: 14,
  };

  if (loading) return <div style={spinnerStyle}>Loading pressure field...</div>;
  if (error || !data) return <div style={spinnerStyle}>{error || "No data available."}</div>;

  return (
    <div style={containerStyle}>
      <PressureFieldScene data={data} isDark={isDark} selected={selectedStation} onSelect={setSelectedStation} rotating={rotating} zoom={zoom} radarVisible={radarVisible} radarOpacity={radarOpacity} radarTs={radarTs} flowVisible={flowVisible} coriolisEnabled={coriolisEnabled} statesVisible={statesVisible} stationsVisible={stationsVisible} tempVisible={tempVisible} tempOpacity={tempOpacity} vorticityVisible={vorticityVisible} vorticityOpacity={vorticityOpacity} divergenceVisible={divergenceVisible} divergenceOpacity={divergenceOpacity} onBearing={handleBearing} />
      <CompassRose bearing={bearing} isDark={isDark} />
      <InfoPanel data={data} isDark={isDark} />
      {/* Temperature color scale — only when temp layer active */}
      {tempVisible && (() => {
        const temps = data.stations.filter((s) => s.temp_f != null).map((s) => s.temp_f as number);
        if (temps.length < 2) return null;
        return <TempScale tMin={Math.min(...temps)} tMax={Math.max(...temps)} isDark={isDark} tempUnit={data.temp_unit || "F"} />;
      })()}
      {vorticityVisible && <VorticityScale isDark={isDark} offsetTop={tempVisible ? 230 : 160} />}
      {divergenceVisible && <DivergenceScale isDark={isDark} offsetTop={
        160 + (tempVisible ? 70 : 0) + (vorticityVisible ? 70 : 0)
      } />}
      {/* Minimal scene controls */}
      <div style={{
        position: "absolute",
        bottom: 16,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 10,
        display: "flex",
        alignItems: "center",
        gap: 12,
        background: isDark ? "rgba(20, 20, 40, 0.85)" : "rgba(255, 255, 255, 0.9)",
        border: `1px solid ${isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)"}`,
        borderRadius: 8,
        padding: "8px 16px",
        backdropFilter: "blur(8px)",
        fontSize: 12,
        color: isDark ? "#ccc" : "#333",
      }}>
        <button
          onClick={() => setRotating(!rotating)}
          title={rotating ? "Pause rotation" : "Resume rotation"}
          style={{
            background: "none",
            border: "none",
            color: isDark ? "#ccc" : "#333",
            cursor: "pointer",
            fontSize: 16,
            padding: "2px 4px",
            lineHeight: 1,
          }}
        >
          {rotating ? "\u23F8" : "\u25B6"}
        </button>
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
          Zoom
          <input
            type="range"
            min={0}
            max={100}
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
            style={{ width: 100, accentColor: "var(--color-accent)" }}
          />
        </label>
      </div>
      {/* Layers toggle button */}
      <button
        onClick={() => setLayersOpen(!layersOpen)}
        title="Toggle layers"
        style={{
          position: "absolute",
          bottom: 16,
          right: 12,
          zIndex: 10,
          width: 36,
          height: 36,
          borderRadius: 8,
          border: `1px solid ${isDark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.1)"}`,
          background: layersOpen
            ? (isDark ? "rgba(60, 60, 100, 0.95)" : "rgba(230, 230, 255, 0.95)")
            : (isDark ? "rgba(20, 20, 40, 0.85)" : "rgba(255, 255, 255, 0.9)"),
          backdropFilter: "blur(8px)",
          color: isDark ? "#ccc" : "#333",
          cursor: "pointer",
          fontSize: 18,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 0,
          lineHeight: 1,
        }}
      >
        {"\u{1F5C2}"}
      </button>
      {/* Layers popover */}
      {layersOpen && (
        <LayersPanel
          isDark={isDark}
          radarVisible={radarVisible} setRadarVisible={setRadarVisible}
          radarOpacity={radarOpacity} setRadarOpacity={setRadarOpacity}
          flowVisible={flowVisible} setFlowVisible={setFlowVisible}
          coriolisEnabled={coriolisEnabled} setCoriolisEnabled={setCoriolisEnabled}
          tempVisible={tempVisible} setTempVisible={setTempVisible}
          tempOpacity={tempOpacity} setTempOpacity={setTempOpacity}
          vorticityVisible={vorticityVisible} setVorticityVisible={setVorticityVisible}
          vorticityOpacity={vorticityOpacity} setVorticityOpacity={setVorticityOpacity}
          divergenceVisible={divergenceVisible} setDivergenceVisible={setDivergenceVisible}
          divergenceOpacity={divergenceOpacity} setDivergenceOpacity={setDivergenceOpacity}
          statesVisible={statesVisible} setStatesVisible={setStatesVisible}
          stationsVisible={stationsVisible} setStationsVisible={setStationsVisible}
        />
      )}
      {selectedStation && (
        <StationDetailPanel
          station={selectedStation}
          isDark={isDark}
          onClose={() => setSelectedStation(null)}
          units={{ pressure: data.pressure_unit || "hPa", temp: data.temp_unit || "F", wind: data.wind_unit || "mph" }}
        />
      )}
    </div>
  );
}
