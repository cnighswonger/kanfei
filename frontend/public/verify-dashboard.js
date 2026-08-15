// Dashboard self-check — paste into the browser console on the dashboard.
//
// Purpose: catch the whole class of fit-and-fill defects without a design review
// round trip. Every check is a measurement, not an opinion. Run it after any
// layout change; all six should print PASS.
//
//   copy(await fetch('/verify-dashboard.js').then(r => r.text()))  // or just paste
//
// Checks 1-3 are the ones that have bitten this page repeatedly; check 6 covers
// "the fonts are off".
//
// Requires data-tile-id on each tile. Add data-role="hero-value" to the hero
// numeral for the sharpest type check.

(() => {
  const tiles = [...document.querySelectorAll('[data-tile-id]')];
  if (!tiles.length) return console.error('No [data-tile-id] elements — add the attribute or update the selector.');

  const results = [];
  const pass = (n, msg) => results.push(['PASS', n, msg]);
  const fail = (n, msg, rows) => results.push(['FAIL', n, msg, rows]);

  const id = (t) => t.dataset.tileId;
  const box = (t) => t.getBoundingClientRect();

  // ── 1. No tile clips its own content ─────────────────────────────────────────
  // The current defect: fixed rowSpan heights + overflow:hidden, so the ET block,
  // the hero chips and Station Status are cut mid-row. A tile must never be
  // shorter than what's in it.
  const clipped = tiles
    .map((t) => {
      // measure the tallest descendant stack, ignoring the tile's own overflow
      const inner = t.scrollHeight, outer = t.clientHeight;
      return { tile: id(t), contentPx: inner, boxPx: outer, shortBy: inner - outer };
    })
    .filter((r) => r.shortBy > 2);
  clipped.length
    ? fail(1, `${clipped.length} tile(s) shorter than their content`, clipped)
    : pass(1, 'no tile clips its content');

  // ── 2. No two tiles overlap ──────────────────────────────────────────────────
  const overlaps = [];
  for (let i = 0; i < tiles.length; i++) {
    for (let j = i + 1; j < tiles.length; j++) {
      const a = box(tiles[i]), b = box(tiles[j]);
      const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (ox > 2 && oy > 2) overlaps.push({ a: id(tiles[i]), b: id(tiles[j]), ox: Math.round(ox), oy: Math.round(oy) });
    }
  }
  overlaps.length ? fail(2, `${overlaps.length} overlapping pair(s)`, overlaps) : pass(2, 'no overlaps');

  // ── 3. No dead space below the last tile ─────────────────────────────────────
  // A grid whose container is taller than its content leaves the plate alone in
  // the lower half, which is what made the engraving look overwhelming.
  const grid = tiles[0].closest('[data-dashboard-grid]') || tiles[0].parentElement;
  const lastBottom = Math.max(...tiles.map((t) => box(t).bottom));
  const trailing = Math.round(box(grid).bottom - lastBottom);
  Math.abs(trailing) <= 24
    ? pass(3, `grid ends ${trailing}px after last tile`)
    : fail(3, `${trailing}px of dead space below the last tile`, [{ gridBottom: Math.round(box(grid).bottom), lastBottom: Math.round(lastBottom) }]);

  // ── 4. Every chart series is inside its y-domain ──────────────────────────────
  // Dew point is currently invisible: the domain is computed from temperature
  // alone (~90-100), so a 77.9 dew line falls below the plot floor.
  const svgs = [...document.querySelectorAll('[data-tile-id] svg')];
  const outOfBox = [];
  svgs.forEach((svg) => {
    const vb = (svg.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
    if (vb.length !== 4) return;
    svg.querySelectorAll('path[d], polyline[points]').forEach((p) => {
      try {
        const b = p.getBBox();
        if (!b.width && !b.height) return;
        if (b.y < vb[1] - 1 || b.y + b.height > vb[1] + vb[3] + 1) {
          outOfBox.push({ tile: id(p.closest('[data-tile-id]')), stroke: getComputedStyle(p).stroke, top: +b.y.toFixed(1), bottom: +(b.y + b.height).toFixed(1), viewBox: svg.getAttribute('viewBox') });
        }
      } catch (e) {}
    });
  });
  outOfBox.length ? fail(4, `${outOfBox.length} series outside the plot box`, outOfBox) : pass(4, 'all series within their plot box');

  // ── 5. No off-palette colour ─────────────────────────────────────────────────
  // Anything not traceable to a CSS custom property is a literal hex someone left
  // inline — that's how the cyan humidity arc and the red solar value happened.
  const themeVals = new Set(
    [...document.styleSheets].flatMap((s) => { try { return [...s.cssRules]; } catch (e) { return []; } })
      .flatMap((r) => (r.style ? [...r.style].filter((p) => p.startsWith('--')).map((p) => r.style.getPropertyValue(p).trim().toLowerCase()) : []))
  );
  const rootStyle = getComputedStyle(document.documentElement);
  for (const p of rootStyle) if (p.startsWith('--')) themeVals.add(rootStyle.getPropertyValue(p).trim().toLowerCase());
  const toHex = (rgb) => {
    const m = rgb.match(/\d+/g);
    return m ? '#' + m.slice(0, 3).map((n) => (+n).toString(16).padStart(2, '0')).join('') : null;
  };
  const strays = new Map();
  tiles.forEach((t) => t.querySelectorAll('*').forEach((el) => {
    const cs = getComputedStyle(el);
    [['color', cs.color], ['fill', cs.fill], ['stroke', cs.stroke]].forEach(([prop, v]) => {
      if (!v || !v.startsWith('rgb')) return;
      const hex = toHex(v);
      if (!hex || hex === '#000000') return;
      if (themeVals.has(hex)) return;
      // saturated screen colours are the tell: high chroma on a paper theme
      const [r, g, b] = hex.match(/\w\w/g).map((h) => parseInt(h, 16));
      const chroma = Math.max(r, g, b) - Math.min(r, g, b);
      if (chroma < 90) return;
      const key = `${hex} (${prop})`;
      strays.set(key, (strays.get(key) || 0) + 1);
    });
  }));
  strays.size
    ? fail(5, `${strays.size} saturated colour(s) not found in any CSS variable`, [...strays].map(([k, n]) => ({ colour: k, count: n })))
    : pass(5, 'no off-palette saturated colours');

  // ── 6. Type roles are actually applied ───────────────────────────────────────
  // "Fonts are all off" is usually text that landed on `body` because no document
  // said which role it takes. See the type map in REVIEW-04-fit-and-type.md.
  const fontOf = (el) => {
    const cs = getComputedStyle(el);
    return { family: cs.fontFamily.split(',')[0].replace(/["']/g, ''), size: Math.round(parseFloat(cs.fontSize)), style: cs.fontStyle };
  };
  const typeIssues = [];
  // the hero is the load-bearing case: display role, italic, ~104px
  const hero = document.querySelector('[data-role="hero-value"]')
    || tiles.find((t) => id(t) === 'outside-temp')?.querySelector('*');
  if (hero) {
    const f = fontOf(hero);
    const expected = getComputedStyle(document.documentElement).getPropertyValue('--type-display-size').trim();
    if (f.size < 90) typeIssues.push({ element: 'hero value', problem: `${f.size}px — display role is ${expected || '104px'}` });
    if (f.style !== 'italic') typeIssues.push({ element: 'hero value', problem: `font-style ${f.style} — display role is italic on paper themes` });
  }
  // any label-looking text (short, uppercase) that is NOT mono has the wrong role
  tiles.forEach((t) => t.querySelectorAll('*').forEach((el) => {
    const txt = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join('');
    if (!txt || txt.length > 32) return;
    const cs = getComputedStyle(el);
    const isCaps = cs.textTransform === 'uppercase' || (txt === txt.toUpperCase() && /[A-Z]{3}/.test(txt));
    if (!isCaps) return;
    const fam = cs.fontFamily.toLowerCase();
    if (!/mono/.test(fam)) typeIssues.push({ element: txt.slice(0, 24), problem: `label in ${cs.fontFamily.split(',')[0]} — sectionLabel role is mono` });
  }));
  typeIssues.length
    ? fail(6, `${typeIssues.length} element(s) on the wrong type role`, typeIssues.slice(0, 20))
    : pass(6, 'type roles applied correctly');

  // ── 7. Page fits the viewport ────────────────────────────────────────────────
  // The dashboard is a glance surface; it should not scroll at the design width.
  const over = document.documentElement.scrollHeight - window.innerHeight;
  over <= 8
    ? pass(7, 'page fits without scrolling')
    : fail(7, `page is ${over}px taller than the viewport`, [{ scrollHeight: document.documentElement.scrollHeight, viewport: window.innerHeight }]);

  // ── report ───────────────────────────────────────────────────────────────────
  console.log('%cDashboard self-check', 'font: bold 14px sans-serif');
  results.forEach(([verdict, n, msg, rows]) => {
    const style = verdict === 'PASS' ? 'color:#3f6b35' : 'color:#a0342e;font-weight:bold';
    console.log(`%c${verdict}%c  ${n}. ${msg}`, style, '');
    if (rows) console.table(rows);
  });
  const failed = results.filter((r) => r[0] === 'FAIL').length;
  console.log(failed ? `%c${failed} check(s) failed` : '%cAll checks passed', failed ? 'color:#a0342e' : 'color:#3f6b35');
  return { passed: results.length - failed, failed };
})();
