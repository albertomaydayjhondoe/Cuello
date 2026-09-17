// Reproduce la ruta que ejecuta el boton "Girar dispositivo": plan con
// `previous`, que es la rama que arrastra los cuadrantes. Sirve para verificar
// el flujo completo sin depender de un navegador.
//   node web/rotate_check.mjs

import { plan, evaluate, BUDGET_MS } from './engine.js';
import { instantiate } from './templates.js';

const PORTRAIT = { width: 411, height: 914 };
const LANDSCAPE = { width: 914, height: 411 };

let failures = 0;
const check = (cond, msg) => {
  if (!cond) { failures += 1; console.error(`  FALLO: ${msg}`); }
};

for (const template of ['media_player', 'dashboard']) {
  const portrait = plan(instantiate(template, PORTRAIT), PORTRAIT, null, `${template}-p`);
  const landscape = plan(instantiate(template, LANDSCAPE), LANDSCAPE, portrait, `${template}-l`);
  const back = plan(instantiate(template, PORTRAIT), PORTRAIT, landscape, `${template}-p2`);

  console.log(`\n${template}`);
  console.log(`  portrait  -> landscape  rolling=${landscape.animation.totalDurationMs}ms`);
  console.log(`  landscape -> portrait   rolling=${back.animation.totalDurationMs}ms`);

  const ids = (l) => l.elements.map((e) => e.id).sort().join('|');
  const crit = (l) => l.elements.filter((e) => e.critical).map((e) => e.id).sort().join('|');

  check(ids(portrait) === ids(landscape), 'se perdieron elementos al girar');
  check(crit(portrait) === crit(landscape), 'cambiaron los criticos al girar');
  check(landscape.animation.totalDurationMs <= BUDGET_MS, 'rolling excede 300 ms');
  check(evaluate(landscape).critical_visible, 'criticos no visibles en apaisado');
  check(evaluate(portrait).critical_visible, 'criticos no visibles en retrato');

  // Los cuadrantes deben rotar, no recargarse: cada elemento cambia de
  // cuadrante segun el mapa, no segun la geometria nueva.
  const moved = landscape.elements.filter((e) => {
    const before = portrait.elements.find((p) => p.id === e.id);
    return before && before.quadrant !== e.quadrant;
  }).length;
  console.log(`  elementos que cambiaron de cuadrante: ${moved}/${landscape.elements.length}`);
  check(moved > 0, 'ningun elemento cambio de cuadrante: no hubo rolling');

  // Ida y vuelta estable.
  const drift = portrait.elements.map((p) => {
    const b = back.elements.find((e) => e.id === p.id);
    return b ? Math.hypot(p.bounds.x - b.bounds.x, p.bounds.y - b.bounds.y) : 1e9;
  });
  const maxDrift = Math.max(...drift);
  console.log(`  deriva maxima ida/vuelta: ${maxDrift.toFixed(3)} dp`);
  check(maxDrift < 1.0, `deriva excesiva: ${maxDrift}`);
}

console.log(failures === 0 ? '\nOK: ruta de rotacion verificada' : `\n${failures} FALLOS`);
process.exit(failures === 0 ? 0 : 1);