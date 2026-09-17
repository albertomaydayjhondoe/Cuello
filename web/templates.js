// Plantillas de pantalla, espejo de `TEMPLATES` en core/nresponsive/generator.py.
// Las posiciones son fracciones del canvas para que la misma plantilla sirva en
// cualquier tamano y orientacion.

const SPECS = {
  media_player: [
    { id: 'header', type: 'text', fx: 0.04, fy: 0.03, fw: 0.92, fh: 0.06, priority: 0.6, text: 'Now playing' },
    { id: 'cover', type: 'image', fx: 0.10, fy: 0.11, fw: 0.80, fh: 0.42, priority: 0.9 },
    { id: 'progress', type: 'container', fx: 0.10, fy: 0.56, fw: 0.80, fh: 0.03, priority: 0.7 },
    { id: 'play', type: 'button', fx: 0.40, fy: 0.62, fw: 0.20, fh: 0.08, priority: 1.0, critical: true, minW: 56, minH: 48, text: 'Play' },
    { id: 'prev', type: 'button', fx: 0.16, fy: 0.62, fw: 0.14, fh: 0.08, priority: 0.8, critical: true },
    { id: 'next', type: 'button', fx: 0.70, fy: 0.62, fw: 0.14, fh: 0.08, priority: 0.8, critical: true },
    { id: 'related', type: 'list', fx: 0.04, fy: 0.72, fw: 0.92, fh: 0.16, priority: 0.5, scrollable: true },
    { id: 'nav', type: 'nav', priority: 1.0, critical: true, minW: 48, minH: 56 },
    { id: 'fab', type: 'fab', priority: 1.0, critical: true, minW: 56, minH: 56 },
  ],
  dashboard: [
    { id: 'title', type: 'text', fx: 0.04, fy: 0.03, fw: 0.60, fh: 0.05, priority: 0.7, text: 'Dashboard' },
    { id: 'kpi1', type: 'container', fx: 0.04, fy: 0.10, fw: 0.44, fh: 0.14, priority: 0.8 },
    { id: 'kpi2', type: 'container', fx: 0.52, fy: 0.10, fw: 0.44, fh: 0.14, priority: 0.8 },
    { id: 'chart', type: 'image', fx: 0.04, fy: 0.26, fw: 0.92, fh: 0.34, priority: 0.9 },
    { id: 'search', type: 'input', fx: 0.04, fy: 0.62, fw: 0.92, fh: 0.06, priority: 0.6, critical: true, minW: 120, minH: 48 },
    { id: 'list', type: 'list', fx: 0.04, fy: 0.70, fw: 0.92, fh: 0.18, priority: 0.5, scrollable: true },
    { id: 'nav', type: 'nav', priority: 1.0, critical: true, minW: 48, minH: 56 },
  ],
};

export const TEMPLATE_NAMES = Object.keys(SPECS);
export const DEFAULT_TEMPLATE = 'media_player';

/** Instancia una plantilla en un canvas concreto. */
export function instantiate(template, canvas) {
  const specs = SPECS[template];
  if (!specs) throw new Error(`plantilla desconocida: ${template}`);
  return specs.map((s) => {
    const minSize = { w: s.minW ?? 48, h: s.minH ?? 48 };
    // Los anclajes los situa el motor. Su posicion aqui es provisional, pero el
    // tamano de diseno debe ser el minimo real del elemento: si fuese 1x1,
    // scaleToFit razonaria sobre un tamano que no significa nada.
    const bounds = s.fx != null
      ? { x: s.fx * canvas.width, y: s.fy * canvas.height, w: s.fw * canvas.width, h: s.fh * canvas.height }
      : { x: 0, y: 0, w: minSize.w, h: minSize.h };
    return {
      id: s.id, type: s.type, bounds,
      critical: !!s.critical, priority: s.priority ?? 0.5,
      minSize,
      designSize: { w: bounds.w, h: bounds.h },
      scrollable: !!s.scrollable, text: s.text ?? null, z: s.z ?? 0,
    };
  });
}