// Comprueba que el port JS del motor produce los mismos cuadrantes y
// posiciones que la implementacion Python. Se ejecuta con:
//   node web/parity.mjs > /tmp/js.json
// y el resultado se compara desde scripts/check_parity.py.

import { plan } from './engine.js';
import { instantiate, TEMPLATE_NAMES } from './templates.js';

const CANVASES = { portrait: { width: 411, height: 914 }, landscape: { width: 914, height: 411 } };
const out = {};

for (const template of TEMPLATE_NAMES) {
  for (const [name, canvas] of Object.entries(CANVASES)) {
    const layout = plan(instantiate(template, canvas), canvas, null, `${template}-${name}`);
    out[`${template}/${name}`] = layout.elements.map((e) => [
      e.id, e.quadrant,
      Math.round(e.bounds.x * 100) / 100,
      Math.round(e.bounds.y * 100) / 100,
      Math.round(e.bounds.w * 100) / 100,
      Math.round(e.bounds.h * 100) / 100,
    ]);
    // Las transiciones tambien deben coincidir: son el contrato que consume
    // Compose, y un desfase de timing no lo detecta la comparacion geometrica.
    out[`${template}/${name}/transitions`] = layout.transitions.map((t) => [
      t.elementId, t.kind, t.delayMs, t.durationMs,
    ]);
  }
}

console.log(JSON.stringify(out));