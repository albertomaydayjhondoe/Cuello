# nresponsive

Motor de layouts adaptativos que sustituye el responsive tradicional por
generación dinámica de disposición: en lugar de definir puntos de ruptura a
mano, el layout se **regenera** para cada orientación y tamaño de pantalla, y el
cambio se **anima** como un rolling en el que los elementos recorren los
cuadrantes.

El caso que resuelve el motor no es "hay menos ancho, encoge las cosas", sino
"gira el dispositivo y reordena los cuadrantes sin que el usuario pierda ningún
botón de acción ni la navegación".

## Arranque rápido

```bash
# 1. Motor y tests (no requiere nada especial)
python3 -m pytest -q                       # 22 tests

# 2. Demo web; abre http://localhost:12000
python3 -m http.server 12000 --directory web

# 3. Paridad entre el motor Python y su port JS
python3 scripts/check_parity.py

# 4. API local (opcional)
pip install fastapi uvicorn
PYTHONPATH=core python3 -m uvicorn nresponsive.api:app --port 8000

# 5. Android
./scripts/setup_android_sdk.sh ~/android-sdk
cd mobile/android && ./gradlew :app:assembleDebug
cd mobile/android && ./gradlew :nresponsive:test     # 11 tests JVM
```

## El problema, en concreto

Al girar de retrato a apaisado, una app convencional tiene dos finalidades que
chocan:

1. **conservar** la disposición para que el usuario no se desoriente;
2. **reorganizar** porque la geometría de la pantalla es otra.

El motor lo resuelve arrastrando el **cuadrante lógico** de cada elemento en
lugar de recalcularlo desde las coordenadas nuevas. Un elemento que estaba en
`top_left` pasa a `top_right` al girar a apaisado, y vuelve a `top_left` al
volver a retrato. La navegación y la acción principal tienen posiciones
reservadas, así que nunca compiten por sitio con el contenido.

Ese detalle —rotar el cuadrante en lugar de derivarlo de la geometría— es lo que
hace que ida y vuelta sea la identidad exacta: deriva medida de **0.000 dp**.

## Arquitectura

```
core/nresponsive/
  schema.py       Element, Bounds, Canvas, Layout; Element.design_size
  rolling.py      RollingEngine: cuadrantes, rotación, shelf-pack, transiciones
  metrics.py      métricas geométricas (solape, cobertura, prominencia, ...)
  generator.py    plantillas y generador offline
  api.py          endpoint FastAPI POST /layout
mobile/android/
  nresponsive/    motor puro JVM (sin Android): testeable sin emulador
  app/            Compose: OrientationDetector + NresponsiveCanvas animado
web/              port JS del motor + demo verificable en navegador
datasets/scripts/ preparación de datos reales y ajuste del reward head
docs/LIMITATIONS.md  lo que no se pudo hacer y por qué
```

El motor existe **tres veces** (Python, Kotlin, JS) a propósito: la app necesita
correr sin red, y la demo web necesita ser verificable sin emulador.
`scripts/check_parity.py` mantiene los ports sincronizados y falla si divergen.

## El motor, paso a paso

1. **Reservar anclajes.** `anchor_slots` fija la navegación y el FAB antes de
   colocar nada más. En retrato la navegación es una barra inferior; en apaisado
   pasa a ser un rail lateral. Reservar antes de empaquetar es lo que garantiza
   que sigan visibles.
2. **Asignar cuadrantes.** Si hay rotación y el elemento existía antes, se
   hereda su cuadrante rotado; si no, se deriva de su posición en la plantilla.
3. **Ajustar escala desde `design_size`.** No desde el layout anterior. Escalar
   sobre el layout previo acumula error en cada giro; escalar desde el tamaño de
   diseño original es determinista y reversible.
4. **Empaquetar por estantes** (`shelf_pack`) dentro de cada cuadrante, con
   compactación hacia arriba. Al ser por cuadrante, no hay solapes cruzados.
5. **Rescatar críticos.** Última barrera: cualquier elemento crítico se mete
   dentro del canvas y se sube a su `min_size` si el empaquetado lo dejó pequeño.
6. **Planificar transiciones.** Una onda que recorre los cuadrantes en orden de
   lectura, con los críticos primero y curva rápida; el total cabe en el
   presupuesto de 300 ms.

## Ejemplo de JSON de layout

Salida real de `POST /layout` para `media_player` en apaisado, tras girar desde
retrato (recortada a tres elementos). `design_size` es el tamaño de diseño y
`transitions` trae el plan de animación que consume Compose.

```json
{
  "schema_version": "nresponsive/1.0",
  "layout_id": "media_player",
  "canvas": { "width": 914.0, "height": 411.0, "unit": "dp", "density": 1.0,
              "orientation": "landscape" },
  "rotation": { "is_rotation": true, "previous_orientation": "portrait",
                "current_orientation": "landscape" },
  "elements": [
    {
      "id": "nav", "type": "nav", "critical": true, "priority": 1.0,
      "bounds": { "x": 4.0, "y": 8.0, "w": 68.0, "h": 395.0 },
      "quadrant": "bottom_left",
      "min_size": { "w": 48.0, "h": 56.0 },
      "design_size": { "w": 48.0, "h": 56.0 }
    },
    {
      "id": "play", "type": "button", "critical": true, "priority": 1.0,
      "text": "Play",
      "bounds": { "x": 84.0, "y": 213.5, "w": 157.01, "h": 48.0 },
      "quadrant": "bottom_left",
      "min_size": { "w": 56.0, "h": 48.0 },
      "design_size": { "w": 182.8, "h": 32.88 }
    },
    {
      "id": "cover", "type": "image", "critical": false, "priority": 0.9,
      "bounds": { "x": 503.0, "y": 213.5, "w": 447.27, "h": 105.59 },
      "quadrant": "bottom_right",
      "min_size": { "w": 48.0, "h": 48.0 },
      "design_size": { "w": 731.2, "h": 172.62 }
    }
  ],
  "quadrant_map": {
    "top_left": ["prev"],
    "top_right": [],
    "bottom_left": ["progress", "play", "next", "related", "nav"],
    "bottom_right": ["header", "cover", "fab"]
  },
  "metrics": {
    "overlap_ratio": 0.0127, "coverage_ratio": 0.3618,
    "whitespace_ratio": 0.804, "center_fill": 0.1,
    "alignment_score": 0.2222, "prominence_score": 0.85,
    "critical_visible": true, "critical_count": 5
  },
  "animation": { "strategy": "rolling", "budget_ms": 300,
                 "total_duration_ms": 280 },
  "transitions": [
    { "element_id": "play", "kind": "move", "delay_ms": 31, "duration_ms": 160,
      "easing": "FastOutSlowIn",
      "from": { "x": 213.5, "y": 433.0, "w": 71.13, "h": 63.27 },
      "to":   { "x": 84.0,  "y": 213.5, "w": 157.01, "h": 48.0 } }
  ],
  "validation_errors": []
}
```

Nota sobre `play`: nace con 71×63 en retrato y aterriza en 157×48. La forma
cambia porque el hueco del cuadrante es otro; lo que se conserva es el área
táctil mínima (56×48), no la forma. Es el comportamiento buscado: el botón no
desaparece ni se vuelve inalcanzable, pero se adapta a la ranura disponible.

## Renderizado en Compose

El plan se consume sin lógica adicional en la UI: cada elemento anima sus cuatro
propiedades con el `delay_ms`, `duration_ms` y `easing` que ya vienen calculados.

```kotlin
@Composable
fun NresponsiveCanvas(layout: Layout, previousBounds: Map<String, Bounds>) {
    BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
        val sx = maxWidth.value / layout.canvas.width
        val sy = maxHeight.value / layout.canvas.height
        layout.elements.sortedBy { it.z }.forEach { element ->
            key(element.id) {
                AnimatedElement(
                    fromBounds = previousBounds[element.id] ?: element.bounds,
                    toBounds = element.bounds,
                    transition = layout.transitions.find { it.elementId == element.id },
                    sx = sx, sy = sy,
                )
            }
        }
    }
}
```

En Android la Activity declara `configChanges="orientation|screenSize|..."` para
**no** recrearse al girar. Así el cambio llega en caliente,
`OrientationDetector` emite el evento y el canvas anima el reordenamiento en
lugar de recargar la pantalla.

## Criterios de aceptación

| Criterio | Estado | Cómo se verificó |
| --- | --- | --- |
| Reorganizar en < 300 ms | Cumple (280 ms, con margen) | `total_duration_ms` del plan; tests Python/Kotlin/JS |
| Acciones y navegación siempre visibles | Cumple | `anchor_slots` reserva sitio; `critical_visible` en las métricas |
| Coherencia con el evaluador de Uni-Layout | Parcial | Métricas propias alineadas con sus restricciones; ver limitaciones |
| Sin conexión | Cumple | El motor corre en el dispositivo; el endpoint es opcional |
| Ida y vuelta sin deriva | Cumple | 0.000 dp medidos |

## Un trade-off medido, no oculto

Conservar los cuadrantes al girar tiene un coste, y conviene saber cuánto:

| Plantilla | Vía | `composite` | `prominence_score` |
| --- | --- | --- | --- |
| media_player | generación fresca | 0.712 | 1.00 |
| media_player | rotación | 0.558 | 0.37 |
| dashboard | generación fresca | 0.758 | 1.00 |
| dashboard | rotación | 0.667 | 0.38 |
| **media** | **fresca** | **0.735** | 1.00 |
| **media** | **rotación** | **0.613** | **0.38** |

Rotar puntúa ~0.12 menos. La causa es concreta: `prominence_score` premia que el
elemento más grande esté en el tercio superior, y al rotar el cuadrante el
elemento grande (el `cover` o el `chart`) puede acabar abajo. En el caso medido,
`cover` pasa de `cy=0.15H` a `cy=0.81H`.

Esto no es un bug de implementación, es la consecuencia de la decisión de diseño.
Se podría recuperar la prominencia aplicando una regla "el cuadrante dominante
nunca baja del ecuador", y sería una mejora real. **No está implementado** porque
no hay forma de verificarlo en este entorno más allá de las métricas propias, y
afirmar que mejora la calidad visual sin poder mirarlo sería especular. Queda
como el siguiente paso natural.

Sobre el sentido de giro: `_rotation_is_clockwise` lo fija por la orientación
destino, no por el sensor. Es deliberado — así portrait → landscape → portrait es
la identidad exacta — pero significa que **no se distingue girar a la izquierda
de girar a la derecha**. `OrientationDetector` expone la orientación, no el
sentido. Distinguirlos requeriría leer el sensor de rotación y pasarlo como
parámetro; el motor ya acepta el dato, solo no se le está dando.

## Datos

El encargo pedía ajustar con `Layout-HF100k`. Ese dataset **no existe** en
HuggingFace. Lo que sí se hizo, con datos reales:

```bash
python3 datasets/scripts/prepare_feedback_dataset.py   # 6000 layouts reales
python3 datasets/scripts/finetune_reward.py --mode gate      # verifica señal
python3 datasets/scripts/finetune_reward.py --mode heuristic # puntuar sin entrenar
```

Resultado honesto: la validación cruzada aleatoria da 0.6057, que es fuga de
plantilla y no significa nada. La agrupada por canvas da 0.5279 frente a 0.5 del
azar, un margen de +0.0279 que **suena** a señal.

No lo es, y el gate lo rechaza (`exit 2`). El motivo es la cobertura: el dataset
tiene 42 tamaños de canvas distintos, pero **solo 2 superan el mínimo de 100
muestras** por grupo. Un margen promediado sobre dos grupos no es evidencia; el
canal dominante, 513×750, es dos tercios del total. El gate exige ahora un mínimo
de 5 grupos evaluados además del margen, así que `has_signal` sale `false`.

En una frase: **no hay señal fiable en este dataset**, y el código lo dice en vez
de disimularlo. Detalle completo en [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Licencias

El código de este repositorio es original y de licencia permisiva. **Pero
`JD-GenX/Uni-Layout` no lo es**: su README lo limita a investigación académica y
prohíbe expresamente el uso comercial y la redistribución sin permiso de JD.COM.
Por eso nada de `third_party/Uni-Layout` se copia ni se deriva en `core/`,
`mobile/` ni `web/`; de él solo se han leído los prompts del evaluador para
alinear la semántica de las métricas.

El requisito de "licencias permisivas" del encargo **no se puede cumplir** si se
depende de Uni-Layout. Ver [docs/LIMITATIONS.md](docs/LIMITATIONS.md#6-licencias)
para las alternativas antes de distribuir.

## Estado

Verificado en este entorno:

- 22 tests Python + 11 tests Kotlin, todos verdes;
- APK debug compila (7.9 MB);
- paridad Python↔JS en 32 elementos y 32 transiciones;
- rotación ida y vuelta sin deriva (0.000 dp) en las dos plantillas;
- animación en 280 ms sobre un criterio de menos de 300 ms.

No verificado: la demo Android ejecutándose. Este entorno no tiene `/dev/kvm`,
así que no se puede arrancar un emulador. La demo web cubre esa carencia
ejecutando el mismo motor en el navegador.