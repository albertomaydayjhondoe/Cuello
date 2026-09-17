# Limitaciones medidas

Este documento recoge lo que **no** funciona y lo que se midió para llegar a esa
conclusión. Es intencionadamente explícito: el encargo original pedía reutilizar
el checkpoint de Uni-Layout y ajustar con `Layout-HF100k`, y ninguna de las dos
cosas es posible con lo que hay publicado.

## 1. El dataset `Layout-HF100k` no existe

No aparece en HuggingFace, ni en el repositorio `JD-GenX/Uni-Layout`, ni en el
README de GenAUI. Se buscó por nombre y por las variantes `Layout-HF100K`,
`layout_hf100k` y `HF100k`. No hay resultados.

## 2. Los pesos del reward model no están publicados

`shuolucs/UniLayout-Reward` existe, pero su `model.safetensors.index.json`
referencia tres shards:

```
model-00001-of-00003.safetensors   HTTP 404
model-00002-of-00003.safetensors   HTTP 404
model-00003-of-00003.safetensors   HTTP 404
```

Es un LLaVA-Llama de ~13.8 GB. Sin los shards no hay forma de cargar el modelo,
así que **no se puede reutilizar como juez**. Lo único reutilizable de la
organización es el formato de sus datos.

## 3. El evaluador de Uni-Layout no expone métricas geométricas

`third_party/Uni-Layout/evaluation.py` consulta un juez LLaVA multimodal y
extrae un veredicto por categoría con expresiones regulares. No calcula solape,
cobertura ni alineación. Las métricas de `core/nresponsive/metrics.py` son
propias, escritas para traducir a números las restricciones que ese evaluador
verbaliza en sus prompts:

| Restricción en el prompt del evaluador | Métrica implementada |
| --- | --- |
| "do not overlap" | `overlap_ratio` |
| "avoid leaving the important central position vacant" | `center_fill` |
| "prominent position" | `prominence_score` |
| "the layout should fill the canvas reasonably" | `coverage_ratio`, `whitespace_ratio` |

## 4. Las etiquetas de feedback humano no separan bien por geometría

`shuolucs/UniLayout-Data` es el único dataset real publicado (licencia `other`).
Su subdirectorio `dpo_reward_data/` contiene dos ficheros con **estructuras
distintas**, algo que no es evidente a primera vista:

| Fichero | Filas | Campos |
| --- | --- | --- |
| `score-reward_model_1.json` | 4000 | `question`, `label_answer`, `gpt_answer`, `logits_0`, `logits_1` |
| `eval-reward_model_1.json` | 4000 | `question`, `label_answer`, `gpt_answer` (sin logits) |

Algunos puntos medidos sobre estos datos, tras convertir 6000 registros con
bounding boxes reales (`datasets/scripts/prepare_feedback_dataset.py`):

| Medida | Valor |
| --- | --- |
| Correlación `logits` del reward con `label_answer` | −0.027 |
| Acuerdo de `gpt_answer` con `label_answer` | 0.4910 |
| Validación cruzada aleatoria (5-fold) sobre la etiqueta | 0.6057 |
| Clase mayoritaria | 0.5000 |
| **Validación agrupada por canvas** | **0.5279** |
| Margen honesto sobre el azar | **+0.0279** |

La lectura importante: la validación cruzada **aleatoria** da 0.6057 y parece un
modelo decente, pero es enganosa. Los registros vienen en grupos con el mismo
tamaño de canvas — un único canvas de 513×750 es dos tercios del dataset — y un
split aleatorio filtra información de plantilla al conjunto de validación. Al
retener canvas completos, la exactitud cae a 0.5279.

Ese 0.5279 tampoco aguanta. El dataset tiene 42 tamaños de canvas distintos, pero
**solo 2 superan el mínimo de 100 muestras** por grupo, así que el "margen
honesto" de +0.0279 se calcula promediando dos números: no es evidencia de que la
geometría generalice. Las correlaciones individuales (`overlap_ratio` −0.164,
`alignment_score` +0.147) están medidas sobre el conjunto completo, con el canvas
dominante pesando dos tercios, así que describen esa plantilla, no una regla
general.

Por eso `datasets/scripts/finetune_reward.py` usa validación agrupada y dispone
de un modo `--mode gate` que **falla con código de salida distinto de cero** si
el margen no supera 0.02 **o** si se evaluaron menos de 5 grupos. En este dataset
se cumplen ambas condiciones de fallo, y `has_signal` sale `false`. Es
preferible un script que se niegue a producir un modelo que uno que reporte una
exactitud inflada: la conclusión es que **estos datos no permiten entrenar un
reward head fiable**.

## 5. Sin emulador Android

`/dev/kvm` no existe en este entorno, así que no se puede arrancar un emulador y
la demo Android no se puede ver ejecutándose aquí. Lo que sí está verificado:

- el APK compila (`app-debug.apk`, 7.9 MB);
- 12 tests JVM puros del motor pasan, incluidos rotación, preservación de
  críticos, presupuesto de animación e ida y vuelta sin deriva;
- la demo web ejecuta el mismo motor portado a JS y sí se verifica en navegador.

El port a JS no es una reimplementación libre: `scripts/check_parity.py` compara
cuadrantes y geometría contra el Python y falla si divergen.

## 6. Licencias

| Componente | Licencia | Uso comercial |
| --- | --- | --- |
| `JD-GenX/Uni-Layout` | propio de JD.COM | **No** |
| `shuolucs/UniLayout-Data` | `other` | No claro |
| `SarthakVaswani/GenAUI_Readme` | solo README | n/a |
| `cyberagent/crello` | CC BY 4.0 | Sí |
| `google/rico` | CC BY 4.0 | Sí |

El README de Uni-Layout dice textualmente:

> "The datasets and code provided in this repository are licensed exclusively
> for academic research purposes. Commercial use, reproduction, or distribution
> requires express written permission from JD.COM."

Esto **choca** con el requisito de licencias permisivas del encargo. La decisión
tomada: el código de `third_party/Uni-Layout` **no se copia ni se deriva** en
ninguna parte de `core/`, `mobile/` ni `web/`. Esos directorios son código
original bajo licencia permisiva. De Uni-Layout solo se han leído los prompts de
su evaluador para alinear la semántica de las métricas, y se ha usado el formato
de sus datos. Antes de distribuir o usar comercialmente este proyecto hay que
resolver esa dependencia (sustituir el dataset de feedback por uno con licencia
permisiva, o pedir permiso a JD.COM).

## 7. Qué queda por hacer si se quisiera cerrar del todo

1. Sustituir `UniLayout-Data` por feedback propio o por Crello/Rico (CC BY 4.0).
2. Entrenar el reward model multimodal cuando se publiquen los shards.
3. Levantar un AVD con KVM disponible en otro host y ejecutar la demo Android.
4. Elegir la política de prominencia al rotar (ver `README_nresponsive.md`). Ya
   están medidas tres variantes: suben `composite` de 0.613 a ~0.77 pero cuestan
   entre 37 y 245 dp de deriva en la ida y vuelta. Es una decisión de producto
   —reversibilidad frente a prominencia—, no una optimización pendiente.
5. Pasar el sentido real de giro desde el sensor de rotación; hoy solo se conoce
   la orientación destino.
6. El presupuesto de animación queda en 280 ms sobre un criterio de 300 ms. El
   margen (`TRANSITION_SAFETY_MS = 20`) absorbe el reloj real de Compose, que
   añade unos milisegundos sobre lo planificado.