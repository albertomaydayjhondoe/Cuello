// Port a JavaScript del motor de rolling (core/nresponsive/rolling.py).
//
// Se mantiene deliberadamente paralelo al Python y al Kotlin: mismas
// constantes, mismo orden de lectura, mismo mapa de rotacion de cuadrantes.
// La demo web lo ejecuta en el navegador, de modo que el rolling se puede
// verificar visualmente sin emulador Android.

export const NAV_BAR_THICKNESS = 64;
export const FAB_SIZE = 56;
export const RAIL_WIDTH = 76;
export const GUTTER = 8;
export const BUDGET_MS = 300;
// Margen para que el total planificado quede estrictamente por debajo del
// presupuesto. El criterio de aceptacion es "< 300 ms" y la animacion real anade
// unos milisegundos de reloj sobre el plan.
export const TRANSITION_SAFETY_MS = 20;

export const READING_ORDER = ['top_left', 'top_right', 'bottom_left', 'bottom_right'];

// Rotacion de cuadrantes. El sentido lo fija la orientacion destino, asi que
// retrato -> apaisado -> retrato es la identidad exacta.
const CW = { top_left: 'top_right', top_right: 'bottom_right', bottom_right: 'bottom_left', bottom_left: 'top_left' };
const CCW = { top_right: 'top_left', bottom_right: 'top_right', bottom_left: 'bottom_right', top_left: 'bottom_left' };

export const rotateQuadrant = (q, clockwise) => (clockwise ? CW : CCW)[q];

export function quadrantOf(b, canvas) {
  const left = b.x + b.w / 2 < canvas.width / 2;
  const top = b.y + b.h / 2 < canvas.height / 2;
  if (top && left) return 'top_left';
  if (top) return 'top_right';
  if (left) return 'bottom_left';
  return 'bottom_right';
}

export function anchorSlots(elements, canvas) {
  const slots = {};
  const navs = elements.filter((e) => e.type === 'nav');
  const fabs = elements.filter((e) => e.type === 'fab');
  const portrait = canvas.width <= canvas.height;

  if (navs.length) {
    const n = navs.length;
    if (portrait) {
      const top = canvas.height - NAV_BAR_THICKNESS;
      const slotW = (canvas.width - GUTTER * (n + 1)) / n;
      navs.forEach((e, i) => {
        slots[e.id] = {
          x: GUTTER + i * (slotW + GUTTER), y: top + GUTTER / 2,
          w: Math.max(slotW, e.minSize.w), h: Math.max(NAV_BAR_THICKNESS - GUTTER, e.minSize.h),
        };
      });
    } else {
      // En apaisado la navegacion pasa a ser un rail lateral.
      const slotH = (canvas.height - GUTTER * (n + 1)) / n;
      navs.forEach((e, i) => {
        slots[e.id] = {
          x: GUTTER / 2, y: GUTTER + i * (slotH + GUTTER),
          w: Math.max(RAIL_WIDTH - GUTTER, e.minSize.w), h: Math.max(slotH, e.minSize.h),
        };
      });
    }
  }

  fabs.forEach((e) => {
    const size = Math.max(FAB_SIZE, e.minSize.w, e.minSize.h);
    const margin = GUTTER + 8;
    const y = navs.length && portrait
      ? canvas.height - NAV_BAR_THICKNESS - size - margin
      : canvas.height - size - margin;
    slots[e.id] = { x: Math.max(0, canvas.width - size - margin), y: Math.max(0, y), w: size, h: size };
  });
  return slots;
}

const contentBounds = (canvas) => (canvas.width <= canvas.height
  ? { x: 0, y: 0, w: canvas.width, h: Math.max(0, canvas.height - NAV_BAR_THICKNESS) }
  : { x: RAIL_WIDTH, y: 0, w: Math.max(0, canvas.width - RAIL_WIDTH), h: canvas.height });

function regionFor(q, content) {
  const w = content.w / 2;
  const h = content.h / 2;
  const x = content.x + (q === 'top_right' || q === 'bottom_right' ? w : 0);
  const y = content.y + (q === 'bottom_left' || q === 'bottom_right' ? h : 0);
  return { x, y, w, h };
}

// Reduce tamanos desde el tamano de diseno, nunca desde el layout previo:
// asi la transformacion es determinista y reversible.
function scaleToFit(items, region, fill = 0.72) {
  if (!items.length) return;
  const total = items.reduce((s, e) => s + e.designSize.w * e.designSize.h, 0);
  const avail = region.w * region.h * fill;
  if (total <= 0 || avail <= 0 || total <= avail) return;
  const k = Math.sqrt(avail / total);
  items.forEach((e) => {
    e.w = e.designSize.w * k;
    e.h = e.designSize.h * k;
    if (e.critical) {
      e.w = Math.max(e.w, e.minSize.w);
      e.h = Math.max(e.h, e.minSize.h);
    }
  });
}

function shelfPack(items, region) {
  const shelves = [];
  let current = [];
  let x = region.x;
  let shelfH = 0;

  items.forEach((e) => {
    if (x + e.w > region.x + region.w + 0.01 && x > region.x + 0.01) {
      shelves.push({ items: current, h: shelfH });
      current = [];
      shelfH = 0;
      x = region.x;
    }
    e.x = x;
    current.push(e);
    shelfH = Math.max(shelfH, e.h);
    x += e.w + GUTTER;
  });
  shelves.push({ items: current, h: shelfH });

  let cy = region.y;
  shelves.forEach((s) => {
    s.items.forEach((e) => { e.y = cy; });
    cy += s.h + GUTTER;
  });
}

function rescueCriticals(items, canvas) {
  items.filter((e) => e.critical).forEach((e) => {
    e.w = Math.min(Math.max(e.w, e.minSize.w), canvas.width);
    e.h = Math.min(Math.max(e.h, e.minSize.h), canvas.height);
    e.x = Math.min(Math.max(0, e.x), Math.max(0, canvas.width - e.w));
    e.y = Math.min(Math.max(0, e.y), Math.max(0, canvas.height - e.h));
  });
}

const priorityKey = (a, b) => {
  if (a.critical !== b.critical) return a.critical ? -1 : 1;
  if (a.priority !== b.priority) return b.priority - a.priority;
  return a.id < b.id ? -1 : 1;
};

function planTransitions(working, previous) {
  const prevBounds = {};
  if (previous) previous.elements.forEach((e) => { prevBounds[e.id] = e.bounds; });

  const staged = [];
  READING_ORDER.forEach((q) => {
    working.filter((e) => e.quadrant === q).sort(priorityKey).forEach((e) => {
      const o = prevBounds[e.id];
      let kind = 'enter';
      if (o) {
        const moved = Math.abs(o.x - e.x) > 0.5 || Math.abs(o.y - e.y) > 0.5
          || Math.abs(o.w - e.w) > 0.5 || Math.abs(o.h - e.h) > 0.5;
        kind = moved ? 'move' : 'stay';
      }
      staged.push({ el: e, kind });
    });
  });
  if (!staged.length) return [];

  const target = Math.max(60, BUDGET_MS - TRANSITION_SAFETY_MS);
  const duration = Math.min(180, Math.max(90, Math.floor(target / 2)));
  const maxTotalDelay = Math.max(0, target - duration);
  const step = staged.length > 1 ? maxTotalDelay / staged.length : 0;

  return staged.map(({ el, kind }, idx) => {
    const delay = Math.round(step * idx);
    const from = prevBounds[el.id] || { x: el.x, y: el.y, w: el.w, h: el.h };
    const dist = Math.hypot(
      from.x + from.w / 2 - (el.x + el.w / 2),
      from.y + from.h / 2 - (el.y + el.h / 2),
    );
    const extra = kind === 'move' ? Math.min(60, Math.floor(dist / 12)) : 0;
    return {
      elementId: el.id,
      from,
      to: { x: el.x, y: el.y, w: el.w, h: el.h },
      durationMs: Math.max(60, Math.min(target - delay, duration + extra)),
      delayMs: delay,
      kind,
    };
  });
}

/**
 * Genera el layout destino y su plan de animacion.
 * @param elements elementos del template ya instanciados en `targetCanvas`
 * @param previous layout vigente, para arrastrar cuadrantes al girar
 */
export function plan(elements, targetCanvas, previous = null, layoutId = 'nresponsive') {
  const working = elements.map((e) => ({
    ...e,
    x: e.bounds.x, y: e.bounds.y, w: e.bounds.w, h: e.bounds.h,
    designSize: e.designSize || { w: e.bounds.w, h: e.bounds.h },
  }));

  const slots = anchorSlots(elements, targetCanvas);
  working.forEach((e) => { if (slots[e.id]) Object.assign(e, slots[e.id]); });

  const rotating = previous
    && previous.canvas.width === targetCanvas.height
    && previous.canvas.height === targetCanvas.width;
  const clockwise = targetCanvas.width > targetCanvas.height;
  const prevQuad = {};
  if (previous) previous.elements.forEach((e) => { if (e.quadrant) prevQuad[e.id] = e.quadrant; });

  const flowing = working.filter((e) => !slots[e.id]).sort(priorityKey);
  const quadItems = Object.fromEntries(READING_ORDER.map((q) => [q, []]));
  flowing.forEach((e) => {
    e.quadrant = rotating && prevQuad[e.id]
      ? rotateQuadrant(prevQuad[e.id], clockwise)
      : quadrantOf({ x: e.x, y: e.y, w: e.w, h: e.h }, targetCanvas);
    quadItems[e.quadrant].push(e);
  });

  const content = contentBounds(targetCanvas);
  READING_ORDER.forEach((q) => {
    const items = quadItems[q];
    if (!items.length) return;
    const r = regionFor(q, content);
    const region = {
      x: r.x + GUTTER, y: r.y + GUTTER,
      w: Math.max(1, r.w - GUTTER * 2), h: Math.max(1, r.h - GUTTER * 2),
    };
    scaleToFit(items, region);
    shelfPack(items, region);
  });

  rescueCriticals(working, targetCanvas);
  working.forEach((e) => {
    e.quadrant = quadrantOf({ x: e.x, y: e.y, w: e.w, h: e.h }, targetCanvas);
  });

  const transitions = planTransitions(working, previous);
  return {
    layoutId,
    canvas: targetCanvas,
    elements: working.map((e) => ({
      id: e.id, type: e.type, critical: e.critical, text: e.text, z: e.z || 0,
      quadrant: e.quadrant, minSize: e.minSize,
      bounds: { x: e.x, y: e.y, w: e.w, h: e.h },
    })),
    quadrantMap: Object.fromEntries(READING_ORDER.map((q) => [
      q, working.filter((e) => e.quadrant === q).map((e) => e.id),
    ])),
    animation: {
      strategy: 'rolling',
      budgetMs: BUDGET_MS,
      totalDurationMs: transitions.reduce((m, t) => Math.max(m, t.delayMs + t.durationMs), 0),
    },
    transitions,
  };
}

/** Metricas geometricas, equivalentes a core/nresponsive/metrics.py. */
export function evaluate(layout) {
  const { elements, canvas } = layout;
  const area = canvas.width * canvas.height;
  let overlap = 0;
  const pool = elements.filter((e) => e.type !== 'container' && e.type !== 'image');
  for (let i = 0; i < pool.length; i += 1) {
    for (let j = i + 1; j < pool.length; j += 1) {
      const a = pool[i].bounds;
      const b = pool[j].bounds;
      const ix = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
      const iy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
      overlap += ix * iy;
    }
  }
  const coverage = elements.reduce((s, e) => s + e.bounds.w * e.bounds.h, 0) / area;
  const crit = elements.filter((e) => e.critical);
  const critVisible = crit.length > 0 && crit.every((e) => (
    e.bounds.x >= -0.01 && e.bounds.y >= -0.01
    && e.bounds.x + e.bounds.w <= canvas.width + 0.01
    && e.bounds.y + e.bounds.h <= canvas.height + 0.01
    && e.bounds.w >= e.minSize.w - 0.01 && e.bounds.h >= e.minSize.h - 0.01
  ));
  return {
    overlap_ratio: overlap / area,
    coverage_ratio: coverage,
    whitespace_ratio: 1 - coverage,
    critical_visible: critVisible,
    critical_count: crit.length,
    quadrant_occupancy: READING_ORDER.filter((q) => layout.quadrantMap[q].length).length,
  };
}