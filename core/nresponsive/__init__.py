"""nresponsive - motor de layout adaptativo generado por IA.

Reemplaza el diseno responsive por breakpoints con re-generacion de layout:
dado un canvas (dispositivo), una orientacion y un contexto de uso, produce
un layout + un plan de animacion "rolling".

Uso rapido:

    from nresponsive import LayoutGenerator, Canvas

    gen = LayoutGenerator(mode="offline")
    layout, info = gen.generate(Canvas(411, 914), "media_player")
    rotated, _ = gen.generate(Canvas(914, 411), "media_player",
                              previous=layout)

Las metricas de calidad viven en `nresponsive.metrics` y estan alineadas con
las restricciones que verbaliza el evaluador de Uni-Layout.
"""

from .schema import (
    SCHEMA_VERSION,
    Bounds,
    Canvas,
    Easing,
    Element,
    ElementType,
    Layout,
    Orientation,
    Quadrant,
    Size,
    Transition,
    assign_quadrant,
    quadrant_of_point,
)
from .metrics import (
    Metrics,
    alignment_score,
    center_fill,
    coverage_ratio,
    critical_visible,
    evaluate,
    overlap_ratio,
    prominence_score,
    teleport_distance,
    whitespace_ratio,
)
from .rolling import (
    ANCHOR_QUADRANTS,
    DEFAULT_BUDGET_MS,
    READING_ORDER,
    RollingEngine,
    rotated_canvas,
)
from .generator import (
    DEFAULT_TEMPLATE,
    TEMPLATES,
    LayoutGenerator,
    sample_layout,
    template_to_elements,
)

__version__ = "1.0.0"

__all__ = [
    "SCHEMA_VERSION",
    "ANCHOR_QUADRANTS",
    "READING_ORDER",
    "DEFAULT_BUDGET_MS",
    "DEFAULT_TEMPLATE",
    "TEMPLATES",
    "Bounds",
    "Canvas",
    "Easing",
    "Element",
    "ElementType",
    "Layout",
    "LayoutGenerator",
    "Metrics",
    "Orientation",
    "Quadrant",
    "RollingEngine",
    "Size",
    "Transition",
    "alignment_score",
    "assign_quadrant",
    "center_fill",
    "coverage_ratio",
    "critical_visible",
    "evaluate",
    "overlap_ratio",
    "prominence_score",
    "quadrant_of_point",
    "rotated_canvas",
    "sample_layout",
    "teleport_distance",
    "template_to_elements",
    "whitespace_ratio",
]