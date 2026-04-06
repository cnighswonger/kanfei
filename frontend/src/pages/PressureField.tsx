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

function GradientFlowLines({ data }: { data: PressureGridData }) {
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
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

  const lineMaterial = useMemo(
    () => new THREE.LineBasicMaterial({
      vertexColors: true,
      opacity: 0.7,
      transparent: true,
    }),
    [],
  );

  const arrowGeo = useMemo(() => new THREE.ConeGeometry(0.04, 0.12, 6), []);
  const arrowMat = useMemo(
    () => new THREE.MeshBasicMaterial({ color: "#ff1493", transparent: true, opacity: 0.85 }),
    [],
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

function CameraControls({ rotating, zoom }: { rotating: boolean; zoom: number }) {
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
  });
  return <OrbitControls ref={controlsRef} enableDamping dampingFactor={0.1} target={[0, 2, 0]} />;
}

// ---------------------------------------------------------------------------
// Scene wrapper
// ---------------------------------------------------------------------------

function PressureFieldScene({ data, isDark, selected, onSelect, rotating, zoom, radarVisible, radarOpacity, radarTs, flowVisible, statesVisible, stationsVisible }: {
  data: PressureGridData; isDark: boolean;
  selected: StationMarker | null; onSelect: (s: StationMarker | null) => void;
  rotating: boolean; zoom: number;
  radarVisible: boolean; radarOpacity: number; radarTs: number;
  flowVisible: boolean; statesVisible: boolean; stationsVisible: boolean;
}) {
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
        {radarVisible && <RadarOverlay data={data} opacity={radarOpacity} radarTs={radarTs} />}
        {flowVisible && <GradientFlowLines data={data} />}
        {statesVisible && <StateBoundaryLines data={data} isDark={isDark} />}
        {stationsVisible && <StationMarkers data={data} selected={selected} onSelect={onSelect} />}
        <GroundLabels data={data} />
        <CardinalLabels data={data} />
        <PressureScale data={data} pressureUnit={data.pressure_unit || "hPa"} />
      </group>
      <CameraControls rotating={rotating} zoom={zoom} />
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
      <PressureFieldScene data={data} isDark={isDark} selected={selectedStation} onSelect={setSelectedStation} rotating={rotating} zoom={zoom} radarVisible={radarVisible} radarOpacity={radarOpacity} radarTs={radarTs} flowVisible={flowVisible} statesVisible={statesVisible} stationsVisible={stationsVisible} />
      <InfoPanel data={data} isDark={isDark} />
      {/* Scene controls */}
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
        <span style={{ width: 1, height: 18, background: isDark ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.12)" }} />
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={radarVisible}
            onChange={(e) => setRadarVisible(e.target.checked)}
            style={{ accentColor: "var(--color-accent)" }}
          />
          Radar
        </label>
        {radarVisible && (
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11 }}>
            <input
              type="range"
              min={0}
              max={100}
              value={Math.round(radarOpacity * 100)}
              onChange={(e) => setRadarOpacity(Number(e.target.value) / 100)}
              style={{ width: 60, accentColor: "var(--color-accent)" }}
            />
          </label>
        )}
        <span style={{ width: 1, height: 18, background: isDark ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.12)" }} />
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={flowVisible}
            onChange={(e) => setFlowVisible(e.target.checked)}
            style={{ accentColor: "var(--color-accent)" }}
          />
          Flow
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={statesVisible}
            onChange={(e) => setStatesVisible(e.target.checked)}
            style={{ accentColor: "var(--color-accent)" }}
          />
          States
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={stationsVisible}
            onChange={(e) => setStationsVisible(e.target.checked)}
            style={{ accentColor: "var(--color-accent)" }}
          />
          Stations
        </label>
      </div>
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
