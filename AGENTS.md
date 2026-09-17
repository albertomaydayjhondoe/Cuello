# AGENTS.md

Conocimiento del repositorio `nresponsive` para futuras sesiones.

## Qué es

Motor de layouts adaptativos que regenera la disposición al girar el dispositivo
en lugar de usar puntos de ruptura responsive. Ver `README_nresponsive.md`.

## Estructura

- `core/nresponsive/` — motor Python: `schema`, `rolling`, `metrics`, `generator`, `api`.
- `mobile/android/nresponsive/` — motor Kotlin puro JVM (sin Android), testeable sin emulador.
- `mobile/android/app/` — app Compose; `OrientationDetector` + `NresponsiveCanvas`.
- `web/` — port JS del motor + demo verificable en navegador.
- `datasets/scripts/` — preparación de datos y ajuste del reward head.
- `docs/LIMITATIONS.md` — lo que no se pudo hacer, con las mediciones que lo justifican.

## El motor está triplicado a propósito

Python, Kotlin y JS implementan lo mismo. La app necesita correr sin red y la
demo web necesita ser verificable sin emulador.

**Al tocar el motor hay que tocar los tres.** Si no, divergen silenciosamente.
`scripts/check_parity.py` es la red de seguridad: compara cuadrantes, geometría
**y el plan de transiciones** entre Python y JS, y falla si divergen.

## Comandos

```bash
python3 -m pytest -q                                   # 24 tests
python3 scripts/check_parity.py                        # Python <-> JS
cd web && node rotate_check.mjs                        # ruta de rotacion
python3 -m http.server 12000 --directory web           # demo

# Android (el wrapper ./gradlew no existe; usar el gradle del sistema)
cd mobile/android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME=$HOME/android-sdk
~/gradle-8.7/bin/gradle :nresponsive:test :app:assembleDebug
```

El build de Android tarda ~20 s en caliente, más de 1000 s en frío. Lanzarlo en
background con `nohup` y hacer poll del log.

## Entorno

- **No hay `/dev/kvm`**: imposible arrancar un emulador. La app Android se
  verifica por compilación + tests JVM. La demo web cubre la verificación visual.
- Solo JDK 21 (no hay 17); el bytecode se compila a target 17.
- El wrapper `gradlew` no está en el repo; usar `~/gradle-8.7/bin/gradle`.

## Trampas conocidas

- **El wrapper de Gradle no existe.** `./gradlew` falla con "No such file or
  directory". Usar el gradle instalado.
- **La rotación de cuadrantes depende de `design_size`.** Escalar desde el layout
  previo acumula error en cada giro; escalar desde `design_size` es determinista
  y da deriva 0.000 dp en ida y vuelta.
- **Los anclajes (nav, fab) deben declarar `design_size` real.** Si se instancian
  con bounds 1×1, `design_size` queda 1×1 y el motor razona sobre una superficie
  sin sentido. Fallo silencioso: no rompe nada, solo empeora los layouts.
- **`eval-reward_model_1.json` no trae logits** y `score-reward_model_1.json` sí.
  Tienen estructuras distintas. Su feedback humano no separa por geometría
  (validación agrupada ≈0.528 vs azar 0.5).
- **El feedback humano no da para entrenar un reward head fiable.** El dataset
  tiene 42 tamaños de canvas, pero solo 2 superan el mínimo de 100 muestras por
  grupo, así que cualquier métrica agrupada se calcula promediando dos números.
  `has_signal` sale `false` y `--mode gate` sale con código 2. Es el resultado
  correcto, no un fallo a arreglar: no bajar `MIN_GROUPS_EVALUATED` para que pase.

- **La identidad de ida y vuelta exige que el mapa de cuadrantes sea una
  involución.** Es la razón de que `_rotation_is_clockwise` dependa de la
  orientación destino y no de dónde cae cada elemento. Un mapa fijo involutivo
  (p. ej. espejo vertical tras rotar) sí sube `prominence` de 0.85 a 1.00 con
  deriva cero; una regla que mire dónde cae el elemento dominante rompe la
  simetría y mete cientos de dp de deriva.
- **Mide sobre la ruta que se sirve, no sobre el motor crudo.** API, Android
  (`LayoutRepository.local`) y la web reinstancian la plantilla en el canvas
  destino antes de rotar. Pasar elementos de retrato directamente al motor da
  cifras pesimistas que no corresponden a ninguna interfaz (0.613 en vez de
  0.703 de media, prominencia 0.38 en vez de 0.85).
- **Los tests de ida y vuelta comprobaban solo los elementos críticos**, con
  200 dp de tolerancia, así que no detectaban esas regresiones. Ahora cubren
  todos los elementos con 0.01 dp. No relajar esa tolerancia.

## Licencias — leer antes de distribuir

`JD-GenX/Uni-Layout` es **solo investigación académica, sin uso comercial ni
redistribución**. Nada de `third_party/Uni-Layout` se copia ni se deriva en el
código propio. El requisito de "solo licencias permisivas" del encargo no se
puede cumplir mientras se dependa de él. Ver `docs/LIMITATIONS.md`.

## Validación de la orientación de la demo web

El extractor de contenido del navegador cachea agresivamente. Para verificar la
orientación de forma determinista, usar `?orientation=landscape` en la URL en
lugar de pulsar "Girar dispositivo"; el botón funciona pero el extractor puede
devolver el estado anterior.