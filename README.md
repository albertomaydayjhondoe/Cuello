# nresponsive

Motor de layouts adaptativos que regenera la disposición al cambiar la
orientación, en lugar de depender de breakpoints responsive. Conserva el
cuadrante lógico de cada elemento, reserva la navegación y las acciones
críticas, y produce un plan de transición `rolling` para que la interfaz se
reordene sin perder contexto.

El motor está implementado en Python, Kotlin/JVM y JavaScript de forma
intencionadamente paralela. La aplicación Android funciona sin red y la demo
web permite comprobar el mismo comportamiento sin emulador.

## Características

- Generación offline determinista para las plantillas `media_player` y
	`dashboard`.
- API FastAPI opcional con generación, evaluación, health check y listado de
	plantillas.
- Rotación por cuadrantes: `top_left`, `top_right`, `bottom_left` y
	`bottom_right`.
- Reserva previa de anclajes para navegación y FAB.
- Empaquetado por estantes dentro de cada cuadrante, compactación y rescate de
	elementos críticos.
- Escalado desde `design_size`, evitando deriva acumulada al alternar
	orientación.
- Métricas de solape, cobertura, espacio vacío, alineación, prominencia y
	visibilidad crítica.
- Transiciones con `delay_ms`, `duration_ms`, `easing` y tipos `move`, `enter`,
	`exit` y `stay`, con presupuesto predeterminado de 300 ms.
- Integración Compose con detección de orientación en caliente, sin recrear la
	Activity.
- Demo web interactiva y comprobación automática de paridad Python/JS.
- Preparación de feedback y gate conservador para el reward head.

## Inicio rápido

Desde la raíz del repositorio:

```bash
python3 -m pytest -q
python3 scripts/check_parity.py
cd web && node rotate_check.mjs
```

La suite Python cubre el motor y sus invariantes. La comprobación de paridad
ejecuta el port JavaScript y compara cuadrantes, geometría y plan de
transiciones para las dos plantillas y ambas orientaciones.

## Demo web

```bash
python3 -m http.server 12000 --directory web
```

Abre <http://localhost:12000>. Para una verificación determinista de la
orientación se puede usar directamente:

```text
http://localhost:12000/?orientation=landscape
```

La demo usa `web/engine.js` y `web/templates.js`. `rotate_check.mjs` valida la
ruta de rotación desde Node sin necesidad de un navegador ni conexión de red.

## API local

La API requiere Python y FastAPI/Uvicorn:

```bash
pip install fastapi uvicorn
PYTHONPATH=core python3 -m uvicorn nresponsive.api:app --port 8000
```

También acepta `--reload` durante el desarrollo. Endpoints disponibles:

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/health` | Estado, plantillas y modo activo |
| `GET` | `/templates` | Plantillas disponibles y predeterminada |
| `POST` | `/layout` | Genera un layout y sus transiciones |
| `POST` | `/evaluate` | Recalcula métricas de un layout existente |

Ejemplo mínimo:

```bash
curl -s http://localhost:8000/layout \
	-H 'content-type: application/json' \
	-d '{"template":"media_player","device":{"width_dp":411,"height_dp":914}}'
```

`POST /layout` acepta `template`, `canvas`, `device`, `previous_layout` y
`mode`. El dispositivo puede aportar `model`, `width_dp`, `height_dp`,
`density`, `orientation`, `locale`, `session_minutes`, `one_handed` y
`top_actions`. Si se envía `previous_layout` y las dimensiones están
intercambiadas, el resultado incluye la rotación y transiciones desde el
layout anterior.

El modo predeterminado es offline y siempre produce una respuesta local. El
modo de modelo remoto es opcional y vuelve a las plantillas offline si el
modelo falla:

```bash
export NRESPONSIVE_MODE=offline
export NRESPONSIVE_MODEL='nombre-del-modelo'
export NRESPONSIVE_BASE_URL='https://servidor.example/v1'
export OPENAI_API_KEY='...'
export NRESPONSIVE_BUDGET_MS=300
export NRESPONSIVE_CORS='http://localhost:12000'
```

No se necesita ninguna de esas variables para usar el motor local. El contrato
JSON usa `schema_version: "nresponsive/1.0"`; las coordenadas y tamaños están
en dp, con origen en la esquina superior izquierda.

## Arquitectura

```text
core/nresponsive/
	schema.py       contrato Canvas, Layout, Element, Bounds y Transition
	rolling.py      cuadrantes, rotación, shelf-pack y transiciones
	metrics.py      métricas geométricas y evaluación
	generator.py    plantillas y generación offline/remota
	api.py          aplicación FastAPI
mobile/android/
	nresponsive/    motor Kotlin/JVM puro y tests sin emulador
	app/            Compose, OrientationDetector y NresponsiveCanvas
web/
	engine.js       port JavaScript del motor
	templates.js    plantillas de la demo
	parity.mjs      salida para la comprobación de paridad
datasets/scripts/ preparación de feedback y reward head
docs/             limitaciones y resultados no concluyentes
```

El flujo del `RollingEngine` es:

1. Reserva `anchor_slots` para navegación y FAB.
2. Hereda o asigna el cuadrante lógico de cada elemento.
3. Escala desde `design_size`, nunca desde el layout anterior.
4. Empaqueta por estantes dentro de cada cuadrante.
5. Garantiza que los elementos críticos respeten su `min_size` y el canvas.
6. Genera transiciones con duración total dentro del presupuesto.

La transformación de cuadrantes es una involución. Por eso portrait ->
landscape -> portrait devuelve todos los elementos a sus bounds originales con
deriva medida de `0.000 dp`. El motor no distingue giro horario y antihorario:
`OrientationDetector` expone orientación, no el sensor físico de rotación.

## Android

El módulo `mobile/android/nresponsive` es Kotlin/JVM puro y se puede probar sin
emulador. La app Compose mantiene la Activity mediante
`configChanges="orientation|screenSize|..."`, detecta el cambio y anima el
canvas con las transiciones recibidas.

Este repositorio no contiene `gradlew`; usa el Gradle instalado y Java 21 (el
bytecode se configura con target 17):

```bash
cd mobile/android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME="$HOME/android-sdk"
~/gradle-8.7/bin/gradle :nresponsive:test :app:assembleDebug
```

Para instalar el SDK base en un entorno compatible:

```bash
cd ../..
./scripts/setup_android_sdk.sh "$HOME/android-sdk"
```

El APK debug se genera en `mobile/android/app/build/outputs/apk/debug/`.
Este entorno no tiene `/dev/kvm`, por lo que la validación Android se limita a
tests JVM y compilación; la demo web cubre la inspección visual.

## Datos y reward head

```bash
python3 datasets/scripts/prepare_feedback_dataset.py
python3 datasets/scripts/finetune_reward.py --mode gate
python3 datasets/scripts/finetune_reward.py --mode heuristic
```

El gate puede terminar con código 2 correctamente: el feedback disponible no
aporta señal fiable. Hay 42 tamaños de canvas, pero solo dos superan el mínimo
de muestras por grupo; no se debe rebajar ese umbral para forzar un resultado.
Los detalles y las alternativas están en
[docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Verificación y estado conocido

La validación esperada incluye 24 tests Python, 12 tests Kotlin/JVM, paridad
Python/JS para 32 escenarios de elementos y transiciones, rotación reversible y
un plan de animación de 280 ms dentro del presupuesto de 300 ms. Ejecuta los
comandos anteriores para reproducirla en el entorno actual.

La mejora de prominencia al recolocar el elemento dominante durante una
rotación se midió, pero rompe la reversibilidad con derivas de decenas o
cientos de dp. La política base prioriza la identidad exacta. Uni-Layout no se
incluye ni se redistribuye: su licencia limita el uso a investigación
académica. Consulta [docs/LIMITATIONS.md](docs/LIMITATIONS.md) antes de
distribuir.

## Licencia

El código propio del repositorio está bajo la licencia indicada en
[LICENSE](LICENSE). Las restricciones de cualquier dependencia externa deben
revisarse por separado antes de uso comercial o redistribución.