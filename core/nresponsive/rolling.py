"""Motor de "rolling": reasignacion de cuadrantes y planificacion de animacion.

El motor recibe los elementos de la orientacion actual y un canvas destino
(por ejemplo, el mismo canvas con ancho/alto intercambiados al girar el
dispositivo) y produce un `Layout` nuevo con:

  1. reasignacion de cuadrantes (los roles cambian entre orientaciones),
  2. empaquetado sin solapes dentro de cada cuadrante,
  3. un plan de transiciones animadas ("rolling") con presupuesto de tiempo.

Garantias (verificadas por `tests/test_rolling.py`):
  * ningun elemento critico queda fuera del canvas ni por debajo de su
    `min_size`;
  * los elementos no-criticos de distinto tipo no se solapan;
  * la animacion total no excede `animation_budget_ms`.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .schema import (
    Bounds,
    Canvas,
    Easing,
    Element,
    ElementType,
    Layout,
    Orientation,
    Quadrant,
    SCHEMA_VERSION,
    Transition,
    assign_quadrant,
)

NAV_BAR_THICKNESS = 64.0
FAB_SIZE = 56.0
RAIL_WIDTH = 76.0
DEFAULT_GUTTER = 8.0
DEFAULT_BUDGET_MS = 300
# Margen para que el total planificado quede estrictamente por debajo del
# presupuesto. El criterio de aceptacion es "< 300 ms" y la animacion real anade
# unos milisegundos de reloj sobre el plan.
TRANSITION_SAFETY_MS = 20

# Orden de lectura de cuadrantes. El "rolling" recorre esta secuencia, asi que
# es también el orden en que se escalonan las animaciones.
READING_ORDER: Tuple[Quadrant, ...] = (
    Quadrant.TOP_LEFT,
    Quadrant.TOP_RIGHT,
    Quadrant.BOTTOM_LEFT,
    Quadrant.BOTTOM_RIGHT,
)

# Reasignacion de cuadrantes al girar. El cuadrante LOGICO de un elemento se
# arrastra a traves de la rotacion; no se recalcula a partir de las
# coordenadas del layout anterior, porque esas coordenadas pertenecen al
# canvas viejo y producirian una reasignacion arbitraria. Al ser `ccw` la
# inversa exacta de `cw`, una rotacion de ida y vuelta devuelve cada elemento
# a su cuadrante original.
_ROTATE_CW: Dict[Quadrant, Quadrant] = {
    Quadrant.TOP_LEFT: Quadrant.TOP_RIGHT,
    Quadrant.TOP_RIGHT: Quadrant.BOTTOM_RIGHT,
    Quadrant.BOTTOM_RIGHT: Quadrant.BOTTOM_LEFT,
    Quadrant.BOTTOM_LEFT: Quadrant.TOP_LEFT,
}
_ROTATE_CCW: Dict[Quadrant, Quadrant] = {v: k for k, v in _ROTATE_CW.items()}


def rotate_quadrant(q: Quadrant, clockwise: bool) -> Quadrant:
    """Reasigna un cuadrante al girar el canvas 90 grados."""
    return (_ROTATE_CW if clockwise else _ROTATE_CCW)[q]

# Cuadrantes que ocupa cada rol de anclaje en cada orientacion. Este mapa ES la
# reasignacion inteligente de cuadrantes: la navegacion pasa de ocupar la banda
# inferior (en retrato) a la banda izquierda (en apaisado), lo que libera el
# cuadrante inferior derecho para el boton de accion principal.
ANCHOR_QUADRANTS: Dict[Orientation, Dict[str, Tuple[Quadrant, ...]]] = {
    Orientation.PORTRAIT: {
        "nav": (Quadrant.BOTTOM_LEFT, Quadrant.BOTTOM_RIGHT),
        "fab": (Quadrant.BOTTOM_RIGHT,),
    },
    Orientation.LANDSCAPE: {
        "nav": (Quadrant.TOP_LEFT, Quadrant.BOTTOM_LEFT),
        "fab": (Quadrant.BOTTOM_RIGHT,),
    },
}


class LayoutError(ValueError):
    pass


def _region_for_quadrant(canvas: Canvas, q: Quadrant,
                         content: Bounds) -> Bounds:
    """Sub-region del area de contenido correspondiente a un cuadrante."""
    w = content.w / 2.0
    h = content.h / 2.0
    x = content.x + (w if q in (Quadrant.TOP_RIGHT, Quadrant.BOTTOM_RIGHT) else 0.0)
    y = content.y + (h if q in (Quadrant.BOTTOM_LEFT, Quadrant.BOTTOM_RIGHT) else 0.0)
    return Bounds(x, y, w, h)


def anchor_slots(elements: Sequence[Element], canvas: Canvas,
                 gutter: float = DEFAULT_GUTTER) -> Dict[str, Bounds]:
    """Posiciones reservadas para los elementos de navegacion/accion.

    Devuelve un mapa element_id -> bounds reservados. Reservar estas zonas
    ANTES de empaquetar el resto es lo que garantiza que los controles
    criticos sigan visibles tras la rotacion.
    """
    slots: Dict[str, Bounds] = {}
    orient = canvas.orientation

    nav_els = [e for e in elements
               if e.type == ElementType.NAV or e.type == ElementType.FAB]
    navs = [e for e in nav_els if e.type == ElementType.NAV]
    fabs = [e for e in nav_els if e.type == ElementType.FAB]

    if navs:
        n = len(navs)
        if orient == Orientation.PORTRAIT:
            band_h = NAV_BAR_THICKNESS
            top = canvas.height - band_h
            slot_w = (canvas.width - gutter * (n + 1)) / n
            for i, e in enumerate(navs):
                x = gutter + i * (slot_w + gutter)
                # Respeta min_size en el eje tactil.
                slots[e.id] = Bounds(x, top + gutter / 2,
                                     max(slot_w, e.min_size.w),
                                     max(band_h - gutter, e.min_size.h))
        else:
            # En apaisado la navegacion se convierte en un rail lateral.
            slot_h = (canvas.height - gutter * (n + 1)) / n
            for i, e in enumerate(navs):
                y = gutter + i * (slot_h + gutter)
                slots[e.id] = Bounds(gutter / 2, y,
                                     max(RAIL_WIDTH - gutter, e.min_size.w),
                                     max(slot_h, e.min_size.h))

    for e in fabs:
        size = max(FAB_SIZE, e.min_size.w, e.min_size.h)
        margin = gutter + 8.0
        x = canvas.width - size - margin
        if navs and orient == Orientation.PORTRAIT:
            # Por encima de la barra inferior.
            y = canvas.height - NAV_BAR_THICKNESS - size - margin
        else:
            y = canvas.height - size - margin
        slots[e.id] = Bounds(max(0.0, x), max(0.0, y), size, size)

    return slots


def content_bounds(canvas: Canvas, slots: Iterable[Bounds]) -> Bounds:
    """Area libre que queda tras reservar los anclajes."""
    orient = canvas.orientation
    if orient == Orientation.PORTRAIT:
        h = canvas.height - NAV_BAR_THICKNESS
        return Bounds(0.0, 0.0, canvas.width, max(0.0, h))
    return Bounds(RAIL_WIDTH, 0.0, max(0.0, canvas.width - RAIL_WIDTH),
                  canvas.height)


def _scale_to_fit(items: List[Element], region: Bounds, fill: float = 0.72,
                  gutter: float = DEFAULT_GUTTER) -> None:
    """Ajusta tamanos para que quepan en `region`, partiendo del tamano de
    diseno. Al ser determinista respecto del diseno, no acumula deriva."""
    if not items:
        return
    total = sum(e.intrinsic_size().w * e.intrinsic_size().h for e in items)
    avail = region.area() * fill
    if total <= 0 or avail <= 0 or total <= avail:
        return
    import math
    k = math.sqrt(avail / total)
    for e in items:
        w = e.intrinsic_size().w * k
        h = e.intrinsic_size().h * k
        if e.critical:
            w = max(w, e.min_size.w)
            h = max(h, e.min_size.h)
        e.bounds.w, e.bounds.h = w, h


def shelf_pack(items: List[Element], region: Bounds,
               gutter: float = DEFAULT_GUTTER) -> List[Element]:
    """Empaqueta por estantes ("shelves") y luego compacta.

    Devuelve los elementos desbordados. Es determinista y garantiza ausencia
    de solapes dentro del cuadrante.
    """
    x = region.x
    y = region.y
    shelf_h = 0.0
    shelves: List[Tuple[float, float, List[Element]]] = []  # top, height, items
    current: List[Element] = []

    for e in items:
        if x + e.bounds.w > region.right() + 0.01 and x > region.x + 0.01:
            shelves.append((y, shelf_h, current))
            current = []
            x = region.x
            y += shelf_h + gutter
            shelf_h = 0.0
        e.bounds.x = x
        e.bounds.y = y
        current.append(e)
        x += e.bounds.w + gutter
        shelf_h = max(shelf_h, e.bounds.h)
    if current:
        shelves.append((y, shelf_h, current))

    # Compactacion: los estantes mas bajos suben para ocupar el hueco libre.
    # Es una mejora puramente estetica, pero tambien la que evita que en
    # apaisado quede el cuadrante inferior vacio.
    cy = region.y
    for top, height, shelf_items in shelves:
        for e in shelf_items:
            e.bounds.y = cy
        cy += height + gutter

    overflow = [e for e in items if e.bounds.bottom() > region.bottom() + 0.01]
    return overflow


def _rescue_criticals(elements: Sequence[Element], canvas: Canvas,
                      gutter: float = DEFAULT_GUTTER) -> None:
    """Ultima barrera: mete los criticos dentro del canvas y respeta min_size."""
    for e in elements:
        if not e.critical:
            continue
        e.bounds.w = max(e.bounds.w, e.min_size.w)
        e.bounds.h = max(e.bounds.h, e.min_size.h)
        e.bounds.w = min(e.bounds.w, canvas.width)
        e.bounds.h = min(e.bounds.h, canvas.height)
        e.bounds.x = min(max(0.0, e.bounds.x), canvas.width - e.bounds.w)
        e.bounds.y = min(max(0.0, e.bounds.y), canvas.height - e.bounds.h)


def _priority_key(e: Element) -> Tuple[int, float, str]:
    # Primero los criticos, luego por prioridad descendente, luego id estable.
    return (0 if e.critical else 1, -e.priority, e.id)


class RollingEngine:
    """Reordena elementos en cuadrantes y planifica la animacion."""

    def __init__(self, gutter: float = DEFAULT_GUTTER,
                 budget_ms: int = DEFAULT_BUDGET_MS,
                 base_duration_ms: int = 180) -> None:
        self.gutter = gutter
        self.budget_ms = budget_ms
        self.base_duration_ms = base_duration_ms

    # -- API principal ----------------------------------------------------
    def plan(self, elements: Sequence[Element], target_canvas: Canvas,
             previous: Optional[Layout] = None,
             layout_id: str = "nresponsive") -> Layout:
        """Genera el layout destino y el plan de transiciones."""
        # Copia profunda manual: el motor nunca muta la entrada.
        working = [
            Element(
                id=e.id, type=e.type,
                bounds=Bounds(e.bounds.x, e.bounds.y, e.bounds.w, e.bounds.h),
                quadrant=e.quadrant, critical=e.critical, priority=e.priority,
                min_size=e.min_size, scrollable=e.scrollable, text=e.text, z=e.z,
                design_size=e.intrinsic_size(),
            )
            for e in elements
        ]

        prev_bounds: Dict[str, Bounds] = {}
        if previous is not None:
            prev_bounds = {e.id: Bounds(e.bounds.x, e.bounds.y,
                                        e.bounds.w, e.bounds.h)
                           for e in previous.elements}

        slots = anchor_slots(working, target_canvas, self.gutter)
        content = content_bounds(target_canvas, slots.values())

        # 1) Colocar anclajes.
        for e in working:
            if e.id in slots:
                e.bounds = slots[e.id]

        # 2) Repartir el resto en cuadrantes, en orden de lectura. Si estamos
        # girando, arrastramos el cuadrante logico del layout anterior; si no,
        # lo derivamos de la posicion en el template.
        flowing = [e for e in working if e.id not in slots]
        flowing.sort(key=_priority_key)
        rotating = (
            previous is not None
            and (previous.canvas.width, previous.canvas.height)
            == (target_canvas.height, target_canvas.width)
        )
        clockwise = self._rotation_is_clockwise(target_canvas)
        prev_quad: Dict[str, Quadrant] = (
            {e.id: e.quadrant for e in previous.elements if e.quadrant}
            if previous is not None else {}
        )

        quad_items: Dict[Quadrant, List[Element]] = {q: [] for q in READING_ORDER}
        for e in flowing:
            if rotating and e.id in prev_quad:
                e.quadrant = rotate_quadrant(prev_quad[e.id], clockwise)
            else:
                e.quadrant = assign_quadrant(e.bounds, target_canvas)
            quad_items[e.quadrant].append(e)

        # 3) Empaquetar cada cuadrante por separado -> sin solapes cruzados.
        for q in READING_ORDER:
            items = quad_items[q]
            if not items:
                continue
            region = _region_for_quadrant(target_canvas, q, content)
            region = Bounds(region.x + self.gutter, region.y + self.gutter,
                            max(1.0, region.w - self.gutter * 2),
                            max(1.0, region.h - self.gutter * 2))
            _scale_to_fit(items, region, gutter=self.gutter)
            shelf_pack(items, region, self.gutter)

        _rescue_criticals(working, target_canvas, self.gutter)

        # 4) Etiquetar cuadrantes finales (para el mapa de cuadrantes).
        for e in working:
            e.quadrant = assign_quadrant(e.bounds, target_canvas)

        transitions = self._plan_transitions(working, prev_bounds)

        return Layout(
            canvas=target_canvas,
            elements=working,
            layout_id=layout_id,
            generated_by={"engine": "RollingEngine",
                          "version": SCHEMA_VERSION,
                          "strategy": "quadrant-rolling"},
            transitions=transitions,
            animation_budget_ms=self.budget_ms,
        )

    def rotate(self, layout: Layout, layout_id: Optional[str] = None) -> Layout:
        """Atajo: rota el canvas y devuelve el layout reordenado."""
        c = layout.canvas
        target = Canvas(width=c.height, height=c.width, unit=c.unit,
                        density=c.density)
        return self.plan(layout.elements, target, previous=layout,
                         layout_id=layout_id or f"{layout.layout_id}-rotated")

    # -- Animacion --------------------------------------------------------
    def _plan_transitions(self, elements: Sequence[Element],
                          prev: Dict[str, Bounds]) -> List[Transition]:
        """Escalona las animaciones como una onda que recorre los cuadrantes."""
        transitions: List[Transition] = []
        by_quad: Dict[Quadrant, List[Element]] = {q: [] for q in READING_ORDER}
        for e in elements:
            by_quad[e.quadrant or Quadrant.TOP_LEFT].append(e)

        wave_index = 0
        staged: List[Tuple[int, Element, str, float]] = []
        for q in READING_ORDER:
            for e in sorted(by_quad[q], key=_priority_key):
                if e.id in prev:
                    old = prev[e.id]
                    dist = ((old.center()[0] - e.bounds.center()[0]) ** 2
                            + (old.center()[1] - e.bounds.center()[1]) ** 2) ** 0.5
                    moved = (abs(old.x - e.bounds.x) > 0.5
                             or abs(old.y - e.bounds.y) > 0.5
                             or abs(old.w - e.bounds.w) > 0.5
                             or abs(old.h - e.bounds.h) > 0.5)
                    staged.append((wave_index, e, "move" if moved else "stay", dist))
                    e._prev = old  # type: ignore[attr-defined]
                else:
                    staged.append((wave_index, e, "enter", 0.0))
                wave_index += 1

        if not staged:
            return []

        # Escalonado proporcional al orden de onda, normalizado al presupuesto.
        n = len(staged)
        # Se reserva un margen para que el total quede estrictamente por debajo
        # del presupuesto, no exactamente en el. El criterio es "< 300 ms", y
        # ademas el reloj real de Compose anade unos milisegundos sobre el plan.
        target = max(60, self.budget_ms - TRANSITION_SAFETY_MS)
        duration = min(self.base_duration_ms, max(90, target // 2))
        max_total_delay = max(0, target - duration)
        step = max_total_delay / n if n > 1 else 0

        for idx, e, kind, dist in staged:
            delay = int(round(step * idx))
            # Las distancias largas duran algo mas, sin romper el presupuesto.
            extra = 0
            if kind == "move" and dist > 0:
                extra = int(min(60, dist / 12.0))
            d = min(target - delay, duration + extra)
            d = max(60, d)
            tr = Transition(
                element_id=e.id,
                from_bounds=getattr(e, "_prev", Bounds(e.bounds.x, e.bounds.y,
                                                       e.bounds.w, e.bounds.h)),
                to_bounds=Bounds(e.bounds.x, e.bounds.y, e.bounds.w, e.bounds.h),
                duration_ms=d,
                delay_ms=delay,
                easing=self._easing_for(e),
                kind=kind,
            )
            transitions.append(tr)
        return transitions

    @staticmethod
    def _easing_for(e: Element) -> Easing:
        if e.critical:
            return Easing.FAST_OUT_SLOW_IN
        return Easing.EASE_OUT

    @staticmethod
    def _rotation_is_clockwise(target_canvas: Canvas) -> bool:
        """Sentido de la reasignacion de cuadrantes.

        Se fija por orientacion destino (no por el historial) para que
        portrait -> landscape -> portrait sea la identidad exacta: al volver
        a retrato se aplica el sentido inverso.
        """
        return target_canvas.orientation == Orientation.LANDSCAPE

    # -- Utilidades -------------------------------------------------------
    @staticmethod
    def to_quadrant_layout(layout: Layout, quadrant: Quadrant) -> Layout:
        """Sub-layout con solo los elementos de un cuadrante (util para tests)."""
        return Layout(
            canvas=layout.canvas,
            elements=[e for e in layout.elements if e.quadrant == quadrant],
            layout_id=f"{layout.layout_id}:{quadrant.value}",
        )


def rotated_canvas(canvas: Canvas) -> Canvas:
    return Canvas(width=canvas.height, height=canvas.width, unit=canvas.unit,
                  density=canvas.density)
