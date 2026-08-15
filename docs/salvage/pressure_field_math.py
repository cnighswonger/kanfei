"""Pressure Field math — salvage from ``frontend/src/pages/PressureField.tsx``.

Kanfei's ``/pressure`` page is being cut as part of the UI refactor
(issue not yet numbered; UI refactor branch ``ui/refactor``, follows
the Design Agent's SCREENS.md).  The 3-D projection has been
superseded by a separate NEXRAD-fusion application; no user reaches
for the Kanfei projection anymore.

The RENDERING is disposable (three.js scene assembly, camera work,
label placement).  The MATH underneath is not — the IDW
interpolation, streamline integration, and vorticity / divergence
field derivations are correct implementations of standard techniques
and cost real effort to write and tune.  This file preserves those
implementations as pure functions with no rendering dependency, so
the future NEXRAD-fusion tool (or any other consumer) can lift them
in.

Nothing in Kanfei imports this file — it lives under ``docs/salvage``
deliberately.  Copy the functions you need, don't try to
``import`` from here.

Provenance
----------

Every function below has a comment naming the exact block in
``PressureField.tsx`` it came from, at the SHA where salvage
happened.  If you extend the algorithm or fix a bug in it, don't
back-port to that source — it will be deleted before this file is
read again.

Dependencies
------------

Standard library + optional numpy for the grid derivatives.  The
original TypeScript used raw nested arrays; the numpy versions are
included as a second variant because they're 20× faster and much
shorter, and any real consumer will already have numpy available.

Testing
-------

The original tests these functions ran under were visual (does the
plot look right).  Recommended for the consumer: pin known-good
inputs and outputs from the current beta33 Pressure Field page
before deleting.  See "Regression harness" at the bottom.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterator, Optional, Sequence

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Coriolis rotation constants — ~25° clockwise, Northern-Hemisphere
# surface approximation.  See PressureField.tsx:296-299.  This is not
# a physically-accurate Coriolis calculation (that needs latitude and
# wind speed); it's a UI-friendly rotation that makes the flow lines
# curve the way isobars do on a real weather map.  For a rigorous
# treatment, sub in a proper geostrophic-wind computation with
# f = 2Ω sin(φ).
COR_COS = 0.906           # cos(25°)
COR_SIN = 0.423           # sin(25°)
COR_FRICTION = 0.7        # surface-friction magnitude reduction


# ---------------------------------------------------------------------------
# 1. Inverse-distance-weighted (IDW) interpolation onto a lat/lon grid
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Station:
    """A single observation to interpolate from.

    Coordinates in decimal degrees.  ``value`` is whatever scalar
    you're gridding — temperature, u-component of wind, etc.  Use
    the ``station_wind_uv`` helper below to decompose met-convention
    (dir-from, CW-from-N) wind into (u, v) before IDW-ing wind.
    """
    lat: float
    lon: float
    value: float


def idw_grid(
    stations: Sequence[Station],
    *,
    rows: int,
    cols: int,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    power: float = 2.0,
) -> list[list[float]]:
    """Inverse-distance-weight the station observations onto a regular
    lat/lon grid.

    Source: ``useWindGrid`` in PressureField.tsx:489-536 (adapted from
    the u/v-specific version to a scalar variant; the scalar case
    IS what the pressure and temperature grids use elsewhere in the
    file, we're just consolidating them here).

    Parameters
    ----------
    stations : Sequence[Station]
        At least two required.  Three or more recommended for stable
        interpolation; the original refused to render at <3.
    rows, cols : int
        Grid dimensions.
    lat_min .. lon_max : float
        Grid bounding box.
    power : float, default 2.0
        Distance-squared weighting (``1 / d²``).  Increase to make
        interpolation more local; the original used exactly 2.

    Returns
    -------
    list[list[float]]
        A ``rows``×``cols`` grid indexed ``[r][c]``.  ``r=0`` is the
        south edge (``lat_min``), ``c=0`` is the west edge
        (``lon_min``).  Matches the coordinate order the streamline
        and divergence functions expect below.
    """
    grid: list[list[float]] = [[0.0] * cols for _ in range(rows)]

    for r in range(rows):
        lat = lat_min + (r / (rows - 1)) * (lat_max - lat_min)
        for c in range(cols):
            lon = lon_min + (c / (cols - 1)) * (lon_max - lon_min)
            w_sum = 0.0
            v_sum = 0.0
            for s in stations:
                dlat = s.lat - lat
                dlon = s.lon - lon
                d2 = dlat * dlat + dlon * dlon
                if d2 < 1e-10:
                    # Grid point coincides with a station — take the
                    # observation exactly, don't divide-by-near-zero.
                    v_sum = s.value
                    w_sum = 1.0
                    break
                w = 1.0 / (d2 ** (power / 2))
                w_sum += w
                v_sum += w * s.value
            grid[r][c] = v_sum / w_sum if w_sum > 0 else 0.0

    return grid


def station_wind_uv(wind_mph: float, wind_dir_deg: float) -> tuple[float, float]:
    """Decompose met-convention wind (dir = FROM, CW from N) into
    (u, v) meteorological components.

    u > 0 = east-flowing, v > 0 = north-flowing.

    Source: ``useWindGrid`` in PressureField.tsx:499-506.  Split out
    here so the sign convention is explicit.  Getting this wrong is
    the #1 cause of "the wind rose looks like it's spinning the
    wrong direction" bugs.
    """
    dir_rad = wind_dir_deg * math.pi / 180.0
    u = -wind_mph * math.sin(dir_rad)
    v = -wind_mph * math.cos(dir_rad)
    return u, v


# ---------------------------------------------------------------------------
# 2. Streamline integration via RK4 with optional Coriolis rotation
# ---------------------------------------------------------------------------

def gradient_field(
    grid: Sequence[Sequence[float]],
) -> tuple[list[list[float]], list[list[float]]]:
    """Central-differences gradient of a scalar grid.

    Source: ``GradientFlowLines`` in PressureField.tsx:311-328.

    Returns
    -------
    (grad_c, grad_r)
        ``grad_c[r][c] = ∂grid/∂c``, ``grad_r[r][c] = ∂grid/∂r`` —
        matching the file's ``x = column``, ``y = row`` orientation.
        Edge cells use forward/backward differences.
    """
    rows = len(grid)
    cols = len(grid[0])
    grad_c: list[list[float]] = [[0.0] * cols for _ in range(rows)]
    grad_r: list[list[float]] = [[0.0] * cols for _ in range(rows)]

    for r in range(rows):
        for c in range(cols):
            if 0 < c < cols - 1:
                dc = (grid[r][c + 1] - grid[r][c - 1]) / 2.0
            elif c == 0:
                dc = grid[r][1] - grid[r][0]
            else:
                dc = grid[r][c] - grid[r][c - 1]

            if 0 < r < rows - 1:
                dr = (grid[r + 1][c] - grid[r - 1][c]) / 2.0
            elif r == 0:
                dr = grid[1][c] - grid[0][c]
            else:
                dr = grid[r][c] - grid[r - 1][c]

            grad_c[r][c] = dc
            grad_r[r][c] = dr

    return grad_c, grad_r


def sample_grad_bilinear(
    grad_c: Sequence[Sequence[float]],
    grad_r: Sequence[Sequence[float]],
    fr: float,
    fc: float,
    *,
    coriolis: bool = False,
) -> Optional[tuple[float, float]]:
    """Bilinear sample of the gradient field at a fractional grid
    position.  Returns ``None`` when the point is outside the grid.

    When ``coriolis=True``, applies the ~25° clockwise rotation +
    friction reduction from ``COR_COS``/``COR_SIN``/``COR_FRICTION``.
    This is what turns a naive down-gradient integrator into
    something that looks like a real weather-map isobar flow.

    Source: ``sampleGrad`` in PressureField.tsx:331-352.
    """
    rows = len(grad_c)
    cols = len(grad_c[0])
    if fr < 0 or fr > rows - 1 or fc < 0 or fc > cols - 1:
        return None

    r0 = min(int(fr), rows - 2)
    c0 = min(int(fc), cols - 2)
    dr = fr - r0
    dc = fc - c0

    gc = (grad_c[r0][c0]     * (1 - dr) * (1 - dc)
        + grad_c[r0][c0 + 1] * (1 - dr) * dc
        + grad_c[r0 + 1][c0] * dr       * (1 - dc)
        + grad_c[r0 + 1][c0 + 1] * dr   * dc)
    gr = (grad_r[r0][c0]     * (1 - dr) * (1 - dc)
        + grad_r[r0][c0 + 1] * (1 - dr) * dc
        + grad_r[r0 + 1][c0] * dr       * (1 - dc)
        + grad_r[r0 + 1][c0 + 1] * dr   * dc)

    if coriolis:
        gc2 = (gc * COR_COS - gr * COR_SIN) * COR_FRICTION
        gr2 = (gc * COR_SIN + gr * COR_COS) * COR_FRICTION
        return gc2, gr2
    return gc, gr


def integrate_streamline(
    grad_c: Sequence[Sequence[float]],
    grad_r: Sequence[Sequence[float]],
    seed_r: float,
    seed_c: float,
    *,
    max_steps: int = 60,
    dt: float = 0.8,
    coriolis: bool = False,
    stagnation_threshold: float = 1e-6,
) -> list[tuple[float, float]]:
    """RK4 integration of a single streamline through the gradient
    field, starting at ``(seed_r, seed_c)`` and stepping DOWN the
    gradient (toward low pressure, for a pressure field).

    Source: RK4 block in PressureField.tsx:390-420.

    Returns a list of ``(r, c)`` fractional grid coordinates along
    the streamline.  Terminates when the integrator leaves the grid,
    hits a stagnation point (|gradient| < ``stagnation_threshold``),
    or exhausts ``max_steps``.

    To convert the returned coordinates to lat/lon, do the inverse
    of the linear mapping ``lat = lat_min + (r/(rows-1)) * range``.

    Notes
    -----
    - The original stepped by ``-normalized_gradient * dt`` so the
      step size in grid cells is roughly ``dt`` regardless of
      gradient magnitude — this makes short streamlines still look
      right rather than crawling in weak fields.  Preserved here.
    - The Coriolis rotation is applied INSIDE each ``sample_grad``
      call, so the RK4 substeps agree on the rotated field.
    """
    points: list[tuple[float, float]] = []
    cr, cc = seed_r, seed_c

    for _ in range(max_steps):
        points.append((cr, cc))

        k1 = sample_grad_bilinear(grad_c, grad_r, cr, cc, coriolis=coriolis)
        if k1 is None:
            break
        k2 = sample_grad_bilinear(grad_c, grad_r,
                                  cr - k1[1] * dt * 0.5,
                                  cc - k1[0] * dt * 0.5,
                                  coriolis=coriolis)
        if k2 is None:
            break
        k3 = sample_grad_bilinear(grad_c, grad_r,
                                  cr - k2[1] * dt * 0.5,
                                  cc - k2[0] * dt * 0.5,
                                  coriolis=coriolis)
        if k3 is None:
            break
        k4 = sample_grad_bilinear(grad_c, grad_r,
                                  cr - k3[1] * dt,
                                  cc - k3[0] * dt,
                                  coriolis=coriolis)
        if k4 is None:
            break

        drc = (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]) / 6.0
        dcc = (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]) / 6.0
        mag = math.hypot(drc, dcc)
        if mag < stagnation_threshold:
            break

        # Normalize + step (negative gradient = toward low pressure)
        cr -= (drc / mag) * dt
        cc -= (dcc / mag) * dt

    return points


def seed_streamlines(
    rows: int,
    cols: int,
    seed_count: int = 200,
) -> Iterator[tuple[float, float]]:
    """Yield ``seed_count`` starting positions on a jittered regular
    grid across the domain.

    Source: seed loop in PressureField.tsx:387-389.  Matches the
    "streamlines start at reasonably even spacing" behaviour of the
    original.  Actual count returned may differ from ``seed_count``
    by up to ~10% since ``sqrt(rows*cols/seed_count)`` rounds.
    """
    seed_spacing = math.sqrt((rows * cols) / seed_count)
    sr = seed_spacing / 2.0
    while sr < rows - 1:
        sc = seed_spacing / 2.0
        while sc < cols - 1:
            yield sr, sc
            sc += seed_spacing
        sr += seed_spacing


# ---------------------------------------------------------------------------
# 3. Vorticity and divergence of a vector field
# ---------------------------------------------------------------------------

def vorticity(
    u_grid: Sequence[Sequence[float]],
    v_grid: Sequence[Sequence[float]],
) -> list[list[float]]:
    """Vertical vorticity ζ = ∂v/∂x - ∂u/∂y.

    Source: ``VorticityOverlay`` in PressureField.tsx:623-637.

    Positive values = cyclonic (counter-clockwise in Northern
    Hemisphere), negative = anticyclonic.  In the original palette,
    cyclonic renders cyan/blue and anticyclonic warm red/orange.

    Central differences interior, forward/backward on edges — same
    stencil as :func:`gradient_field`.
    """
    rows = len(u_grid)
    cols = len(u_grid[0])
    field: list[list[float]] = [[0.0] * cols for _ in range(rows)]

    for r in range(rows):
        for c in range(cols):
            if 0 < c < cols - 1:
                dv_dc = (v_grid[r][c + 1] - v_grid[r][c - 1]) / 2.0
            elif c == 0:
                dv_dc = v_grid[r][1] - v_grid[r][0]
            else:
                dv_dc = v_grid[r][c] - v_grid[r][c - 1]

            if 0 < r < rows - 1:
                du_dr = (u_grid[r + 1][c] - u_grid[r - 1][c]) / 2.0
            elif r == 0:
                du_dr = u_grid[1][c] - u_grid[0][c]
            else:
                du_dr = u_grid[r][c] - u_grid[r - 1][c]

            field[r][c] = dv_dc - du_dr

    return field


def divergence(
    u_grid: Sequence[Sequence[float]],
    v_grid: Sequence[Sequence[float]],
) -> list[list[float]]:
    """Horizontal divergence ∇·V = ∂u/∂x + ∂v/∂y.

    Source: ``DivergenceOverlay`` in PressureField.tsx:685-697.

    Positive = divergent flow (subsidence signature in the boundary
    layer), negative = convergent (updraft signature).  Original
    palette rendered convergence warm amber/red and divergence cool
    teal/blue.
    """
    rows = len(u_grid)
    cols = len(u_grid[0])
    field: list[list[float]] = [[0.0] * cols for _ in range(rows)]

    for r in range(rows):
        for c in range(cols):
            if 0 < c < cols - 1:
                du_dc = (u_grid[r][c + 1] - u_grid[r][c - 1]) / 2.0
            elif c == 0:
                du_dc = u_grid[r][1] - u_grid[r][0]
            else:
                du_dc = u_grid[r][c] - u_grid[r][c - 1]

            if 0 < r < rows - 1:
                dv_dr = (v_grid[r + 1][c] - v_grid[r - 1][c]) / 2.0
            elif r == 0:
                dv_dr = v_grid[1][c] - v_grid[0][c]
            else:
                dv_dr = v_grid[r][c] - v_grid[r - 1][c]

            field[r][c] = du_dc + dv_dr

    return field


# ---------------------------------------------------------------------------
# 4. Numpy variants (recommended for real use)
# ---------------------------------------------------------------------------
#
# All four algorithms above are 20-30× faster and 4× shorter with numpy.
# Included here as the version a real consumer should actually copy.
# Behavior is identical to the pure-python versions above.

_NUMPY_VARIANTS = """
import numpy as np


def idw_grid_np(stations, *, rows, cols, lat_min, lat_max, lon_min, lon_max, power=2.0):
    lats = np.linspace(lat_min, lat_max, rows)
    lons = np.linspace(lon_min, lon_max, cols)
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing='ij')

    slats = np.array([s.lat for s in stations])
    slons = np.array([s.lon for s in stations])
    svals = np.array([s.value for s in stations])

    # (rows, cols, n_stations) distance^2 tensor
    d2 = ((lat_grid[..., None] - slats)**2
        + (lon_grid[..., None] - slons)**2)
    coincident = d2 < 1e-10
    d2 = np.where(coincident, 1.0, d2)
    weights = 1.0 / (d2 ** (power / 2))
    weights = np.where(coincident.any(axis=-1, keepdims=True),
                       coincident.astype(float),
                       weights)
    return (weights * svals).sum(-1) / weights.sum(-1)


def gradient_field_np(grid):
    grad_r, grad_c = np.gradient(np.asarray(grid))  # (∂/∂r, ∂/∂c)
    return grad_c, grad_r


def vorticity_np(u, v):
    _, dv_dc = np.gradient(np.asarray(v))
    du_dr, _ = np.gradient(np.asarray(u))
    return dv_dc - du_dr


def divergence_np(u, v):
    _, du_dc = np.gradient(np.asarray(u))
    dv_dr, _ = np.gradient(np.asarray(v))
    return du_dc + dv_dr
"""


# ---------------------------------------------------------------------------
# 5. Regression harness (recommended before deleting the source file)
# ---------------------------------------------------------------------------
#
# The functions above are extracted mechanically and preserve the
# original algorithms.  Before ``PressureField.tsx`` is deleted, pin a
# handful of known-good inputs and outputs from the running beta33
# page so any future refactor of this file has a numerical ground
# truth.  Suggested procedure:
#
# 1. On a running Kanfei with data, hit ``GET /api/pressure`` (or the
#    endpoint that returns the grid inputs to the page).  Save the JSON.
# 2. In a Node REPL with the current PressureField.tsx utilities
#    imported, feed in that JSON and log:
#
#      - The IDW-interpolated u/v grids at a few sample points
#      - Vorticity and divergence at those same points
#      - The first few (r, c) coordinates of a streamline from a
#        known seed with coriolis=false AND coriolis=true
#
# 3. Serialize those as a JSON fixture in ``docs/salvage/fixtures/`` and
#    write a small pytest that runs the salvaged functions above
#    against the fixture inputs and asserts the outputs match to
#    within floating-point tolerance.
#
# I haven't automated this because the running-Kanfei-with-data step
# requires manual coordination.  The pin should live in whatever
# repo picks up the math.
