#!/usr/bin/env python3
"""Convierte las muestras reales de feedback humano de UniLayout-Data al
schema nresponsive.

Este script sustituye al "fine-tuning con Layout-HF100k" del encargo original:
el dataset Layout-HF100k NO existe en HuggingFace (busqueda exhaustiva sin
resultados) ni en el repositorio Uni-Layout. Lo que la organizacion si publica
es `shuolucs/UniLayout-Data`, cuyo subdirectorio `dpo_reward_data/` contiene
datos reales de feedback humano con puntuaciones del reward model:

    score-reward_model_*.json   4000 muestras con logits_0 / logits_1
    eval-reward_model_*.json    mismo formato, particion de evaluacion

Cada muestra trae:
  * `question`: instruccion con el tamano de canvas y las bounding boxes
    agrupadas por categoria;
  * `label_answer`: juicio binario de calidad (0/1);
  * `logits_0`, `logits_1`: logits del reward model, que dan una recompensa
    continua mucho mas informativa que la etiqueta binaria.

Salida: un JSONL con pares (layout nresponsive, recompensa) listo para
`finetune_reward.py`.

Uso:
    python datasets/scripts/prepare_feedback_dataset.py \
        --input datasets/raw --output datasets/processed
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "core"))

from nresponsive import (  # noqa: E402
    Bounds,
    Canvas,
    Element,
    ElementType,
    Layout,
    evaluate,
)

CANVAS_RE = re.compile(r"(\d+)\s*[*x]\s*(\d+)")
CATEGORY_RE = re.compile(r"([A-Za-z_][A-Za-z_0-9]*)\s*:")
# Cuadruples [x1, y1, x2, y2] con tolerancia a espacios y negativos.
BOX_RE = re.compile(
    r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*"
    r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]"
)

# Mapeo de las categorias del evaluador a tipos del schema nresponsive.
CATEGORY_TO_TYPE: Dict[str, ElementType] = {
    "text": ElementType.TEXT,
    "logo": ElementType.IMAGE,
    "underlay": ElementType.CONTAINER,
    "embellishment": ElementType.CONTAINER,
    "image": ElementType.IMAGE,
    "button": ElementType.BUTTON,
    "title": ElementType.TEXT,
    "list": ElementType.LIST,
    "table": ElementType.CONTAINER,
    "figure": ElementType.IMAGE,
}

# Elementos que el evaluador considera interaccionables y por tanto criticos.
CRITICAL_CATEGORIES = {"button", "logo"}


def parse_canvas(question: str) -> Optional[Tuple[float, float]]:
    m = CANVAS_RE.search(question)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def parse_elements(question: str, canvas: Canvas) -> List[Element]:
    """Extrae los elementos agrupados por categoria.

    Se asocia cada cuadruple a la ultima categoria mencionada antes que el,
    lo que funciona con el formato anidado del evaluador
    (`text: ['a': [..], 'b': [..]], logo: [[..]]`).
    """
    markers = [(m.start(), m.group(1).lower()) for m in CATEGORY_RE.finditer(question)]
    if not markers:
        return []

    elements: List[Element] = []
    counters: Dict[str, int] = {}

    for match in BOX_RE.finditer(question):
        start = match.start()
        category = None
        for pos, name in markers:
            if pos < start:
                category = name
            else:
                break
        if category is None or category not in CATEGORY_TO_TYPE:
            continue

        x1, y1, x2, y2 = (float(g) for g in match.groups())
        # El evaluador usa [x_min, y_min, x_max, y_max] sobre la imagen.
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0 or w > canvas.width or h > canvas.height:
            continue
        # Se recorta al canvas: hay muestras reales con cajas fuera de rango.
        x1 = min(max(0.0, x1), canvas.width - 1)
        y1 = min(max(0.0, y1), canvas.height - 1)
        w = min(w, canvas.width - x1)
        h = min(h, canvas.height - y1)

        counters[category] = counters.get(category, 0) + 1
        etype = CATEGORY_TO_TYPE[category]
        critical = category in CRITICAL_CATEGORIES
        elements.append(Element(
            id=f"{category}_{counters[category]}",
            type=etype,
            bounds=Bounds(x1, y1, w, h),
            critical=critical,
            priority=0.9 if critical else 0.5,
            min_size=__import__("nresponsive").Size(24.0, 24.0),
        ))
    return elements


def reward_from_logits(logits_0: float, logits_1: float) -> float:
    """Recompensa continua en (0, 1) a partir de los logits del reward model.

    softmax(logits)[1] es la probabilidad de "layout calificado"; es una senal
    mas fina que la etiqueta binaria.
    """
    m = max(logits_0, logits_1)
    e0, e1 = math.exp(logits_0 - m), math.exp(logits_1 - m)
    return e1 / (e0 + e1)


def convert_record(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    question = record.get("question") or ""
    dims = parse_canvas(question)
    if dims is None:
        return None
    canvas = Canvas(width=dims[0], height=dims[1])
    elements = parse_elements(question, canvas)
    if not elements:
        return None

    layout = Layout(canvas=canvas, elements=elements,
                    layout_id=f"feedback-{record.get('sku_id', 'unknown')}")
    layout.metrics = evaluate(elements, canvas).to_dict()

    l0 = float(record.get("logits_0", 0.0))
    l1 = float(record.get("logits_1", 0.0))
    return {
        "layout": layout.to_dict(include_transitions=False),
        "reward": round(reward_from_logits(l0, l1), 6),
        "label": int(record.get("label_answer", 0) or 0),
        "logits": [l0, l1],
        "n_elements": len(elements),
        "source": "shuolucs/UniLayout-Data:score-reward_model",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=str(REPO_ROOT / "datasets" / "raw"))
    ap.add_argument("--output", default=str(REPO_ROOT / "datasets" / "processed"))
    ap.add_argument("--limit", type=int, default=0, help="0 = sin limite")
    args = ap.parse_args()

    in_dir, out_dir = Path(args.input), Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(in_dir.glob("*reward_model*.json"))
    if not files:
        print(f"No hay ficheros de reward en {in_dir}.\n"
              f"Ejecuta primero python datasets/scripts/fetch_datasets.py",
              file=sys.stderr)
        return 1

    total_in = total_out = 0
    for path in files:
        split = "train" if path.name.startswith("score") else "eval"
        records = json.loads(path.read_text(encoding="utf-8"))
        total_in += len(records)
        out_path = out_dir / f"feedback_{split}.jsonl"
        written = 0
        with out_path.open("w", encoding="utf-8") as fh:
            for rec in records:
                if args.limit and written >= args.limit:
                    break
                converted = convert_record(rec)
                if converted is None:
                    continue
                fh.write(json.dumps(converted, ensure_ascii=False) + "\n")
                written += 1
        total_out += written
        print(f"{path.name} -> {out_path.name}: {written} muestras")

    print(f"\ntotal: {total_in} entradas -> {total_out} layouts convertidos")
    if total_out:
        print(f"salida en {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())