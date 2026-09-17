"""Metricas geometricas de calidad de layout.

El evaluador oficial de Uni-Layout (`third_party/Uni-Layout/evaluation.py`) es
unicamente un modelo LLaVA de juicio binario 0/1; el repositorio NO contiene
metricas geometricas, y los pesos del checkpoint `UniLayout-Reward` no estan
publicados (los shards referenciados por `model.safetensors.index.json`
devuelven HTTP 404).

Por eso este modulo implementa metricas deterministas y calculables en local
que reproducen las mismas restricciones que el evaluador verbaliza en sus
prompts (ver `datasets/raw/score-reward_model_*.json`):

  * "the layouts do not overlap or block each other, except for the underlay"
    -> overlap_ratio (excluyendo elementos marcados como underlay)
  * "the larger layout area should be placed in a prominent position"
    -> prominence_score
  * "avoid leaving the important central position vacant"
    -> whitespace_ratio / center_fill
  * "do not leave the canvas too crowded"
    -> coverage_ratio

Estas metricas son una aproximacion local y reproducible; NO pretenden
sustituir al reward model. Sirven como (a) senal de recompensa para el
fine-tuning y (b) criterio de verificacion en CI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from .schema import Bounds, Canvas, Element

# Elementos que el evaluador permite solapar con el resto ("except for the
# underlay").
UNDERLAY_TYPES = {"container", "image"}


@dataclass
class Metrics:
    overlap_ratio: float
    coverage_ratio: float
    whitespace_ratio: float
    center_fill: float
    alignment_score: float
    prominence_score: float
    critical_visible: bool
    critical_count: int

    def to_dict(self) -> Dict[str, float]:
        return {
            "overlap_ratio": round(self.overlap_ratio, 4),
            "coverage_ratio": round(self.coverage_ratio, 4),
            "whitespace_ratio": round(self.whitespace_ratio, 4),
            "center_fill": round(self.center_fill, 4),
            "alignment_score": round(self.alignment_score, 4),
            "prominence_score": round(self.prominence_score, 4),
            "critical_visible": self.critical_visible,
            "critical_count": self.critical_count,
        }

    def composite(self) -> float:
        """Puntuacion global 0..1, mayor es mejor.

        Pondera las restricciones del evaluador. Es la senal que usa
        `datasets/scripts/finetune_reward.py`.
        """
        penalty = min(1.0, self.overlap_ratio * 4.0)
        score = (
            0.30 * (1.0 - penalty)
            + 0.20 * self.alignment_score
            + 0.20 * self.prominence_score
            + 0.15 * self.center_fill
            + 0.15 * self.whitespace_ratio
        )
        if not self.critical_visible:
            score *= 0.25
        return max(0.0, min(1.0, score))


def _is_underlay(e: Element) -> bool:
    return e.type.value in UNDERLAY_TYPES


def overlap_ratio(elements: Sequence[Element], canvas: Canvas,
                  exclude_underlay: bool = True) -> float:
    """Fraccion del area del canvas ocupada por solapes no permitidos."""
    pool = [e for e in elements if not (exclude_underlay and _is_underlay(e))]
    total_overlap = 0.0
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            total_overlap += pool[i].bounds.intersection(pool[j].bounds)
    canvas_area = canvas.width * canvas.height
    if canvas_area <= 0:
        return 0.0
    return total_overlap / canvas_area


def coverage_ratio(elements: Sequence[Element], canvas: Canvas) -> float:
    """Fraccion del canvas cubierta por la union de los elementos."""
    canvas_area = canvas.width * canvas.height
    if canvas_area <= 0:
        return 0.0
    # Aproximacion por rejilla: robusta y suficiente para 10-30 elementos.
    return _covered_fraction(elements, canvas)


def _covered_fraction(elements: Sequence[Element], canvas: Canvas,
                      grid: int = 64) -> float:
    cell_w = canvas.width / grid
    cell_h = canvas.height / grid
    covered = 0
    for gy in range(grid):
        cy = (gy + 0.5) * cell_h
        for gx in range(grid):
            cx = (gx + 0.5) * cell_w
            for e in elements:
                b = e.bounds
                if b.x <= cx <= b.right() and b.y <= cy <= b.bottom():
                    covered += 1
                    break
    return covered / float(grid * grid)


def whitespace_ratio(elements: Sequence[Element], canvas: Canvas) -> float:
    """Cercania a una ocupacion objetivo (~0.45). Penaliza vacio y saturacion."""
    cov = coverage_ratio(elements, canvas)
    target = 0.45
    return max(0.0, 1.0 - abs(cov - target) / target)


def center_fill(elements: Sequence[Element], canvas: Canvas,
                band: float = 0.2) -> float:
    """Cobertura en la banda central; el evaluador penaliza el centro vacio."""
    cx0, cx1 = canvas.width * (0.5 - band / 2), canvas.width * (0.5 + band / 2)
    cy0, cy1 = canvas.height * (0.5 - band / 2), canvas.height * (0.5 + band / 2)
    band_area = max(1e-6, (cx1 - cx0) * (cy1 - cy0))
    covered = 0.0
    for e in elements:
        b = e.bounds
        ix = max(0.0, min(b.right(), cx1) - max(b.x, cx0))
        iy = max(0.0, min(b.bottom(), cy1) - max(b.y, cy0))
        covered += ix * iy
    return min(1.0, covered / band_area)


def alignment_score(elements: Sequence[Element], tolerance: float = 8.0) -> float:
    """Alineacion a guias verticales/horizontales.

    Premia que los bordes (x, right, centro-x) de los elementos coincidan con
    los de otros elementos dentro de `tolerance` dp.
    """
    if len(elements) < 2:
        return 1.0
    values: List[float] = []
    for e in elements:
        b = e.bounds
        values += [b.x, b.right(), b.center()[0]]
    values.sort()
    aligned = 0
    total = 0
    for v in values:
        total += 1
        for u in values:
            if u is not v and abs(u - v) <= tolerance:
                aligned += 1
                break
    return aligned / float(total) if total else 1.0


def prominence_score(elements: Sequence[Element], canvas: Canvas) -> float:
    """El area mayor debe estar en posicion prominente (superior o central)."""
    if not elements:
        return 1.0
    canvas_area = canvas.width * canvas.height
    biggest = max(elements, key=lambda e: e.bounds.area())
    cy = biggest.bounds.center()[1]
    # Prominente = tercio superior o banda central.
    if cy <= canvas.height / 3.0:
        return 1.0
    if abs(cy - canvas.height / 2.0) <= canvas.height / 6.0:
        return 0.85
    rel_area = biggest.bounds.area() / canvas_area if canvas_area else 0.0
    return max(0.0, 0.5 - rel_area)


def critical_visible(elements: Sequence[Element], canvas: Canvas) -> Tuple[bool, int]:
    """(todos_visibles, cantidad_de_criticos).

    Un elemento critico es visible si (a) esta dentro del canvas y (b) cumple
    su `min_size` (target tactil minimo).
    """
    crit = [e for e in elements if e.critical]
    if not crit:
        return True, 0
    for e in crit:
        b = e.bounds
        inside = (b.x >= -0.01 and b.y >= -0.01
                  and b.right() <= canvas.width + 0.01
                  and b.bottom() <= canvas.height + 0.01)
        big_enough = (b.w >= e.min_size.w - 0.01 and b.h >= e.min_size.h - 0.01)
        if not (inside and big_enough):
            return False, len(crit)
    return True, len(crit)


def evaluate(elements: Sequence[Element], canvas: Canvas) -> Metrics:
    """Calcula todas las metricas de una vez."""
    visible, n_crit = critical_visible(elements, canvas)
    return Metrics(
        overlap_ratio=overlap_ratio(elements, canvas),
        coverage_ratio=coverage_ratio(elements, canvas),
        whitespace_ratio=whitespace_ratio(elements, canvas),
        center_fill=center_fill(elements, canvas),
        alignment_score=alignment_score(elements),
        prominence_score=prominence_score(elements, canvas),
        critical_visible=visible,
        critical_count=n_crit,
    )


def teleport_distance(before: Sequence[Element],
                      after: Sequence[Element]) -> float:
    """Distancia media de desplazamiento (dp) entre dos disposiciones.

    Metrica de estabilidad: un "rolling" correcto evita que los elementos
    salten de forma erratica entre orientaciones.
    """
    prev = {e.id: e for e in before}
    dists = []
    for e in after:
        if e.id in prev:
            x0, y0 = prev[e.id].bounds.center()
            x1, y1 = e.bounds.center()
            dists.append(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
    return sum(dists) / len(dists) if dists else 0.0
