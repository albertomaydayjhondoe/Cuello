"""Modelo de datos del layout "nresponsive".

Este schema es el contrato compartido entre el motor (Python), la integración
Android (Kotlin) y el prototipo web (TypeScript). Cualquier cambio aqui debe
replicarse en `mobile/android/.../NresponsiveSchema.kt` y
`web/src/nresponsive/schema.ts`.

Convenciones:
  * Las coordenadas ``bounds`` estan en densidad-independientes (dp) y son
    relativas al canvas, con origen en la esquina superior izquierda.
  * Los cuadrantes se nombran por posicion espacial ("top_left", ...) y NO
    como q1..q4, para evitar la colision con los "q1..q4" del dataset
    UniLayout-Data, donde q1..q4 identifican dominios de contenido
    (marketing, articulos cientificos), no regiones de pantalla.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "nresponsive/1.0"


class Orientation(str, Enum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class ElementType(str, Enum):
    BUTTON = "button"
    TEXT = "text"
    IMAGE = "image"
    INPUT = "input"
    NAV = "nav"
    CONTAINER = "container"
    LIST = "list"
    FAB = "fab"


class Quadrant(str, Enum):
    """Cuadrantes espaciales de pantalla."""

    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


class Easing(str, Enum):
    LINEAR = "Linear"
    FAST_OUT_SLOW_IN = "FastOutSlowIn"
    EASE_IN_OUT = "EaseInOut"
    EASE_OUT = "EaseOut"


@dataclass
class Size:
    w: float
    h: float


@dataclass
class Bounds:
    x: float
    y: float
    w: float
    h: float

    def right(self) -> float:
        return self.x + self.w

    def bottom(self) -> float:
        return self.y + self.h

    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)

    def intersection(self, other: "Bounds") -> float:
        ix = max(0.0, min(self.right(), other.right()) - max(self.x, other.x))
        iy = max(0.0, min(self.bottom(), other.bottom()) - max(self.y, other.y))
        return ix * iy

    def to_dict(self) -> Dict[str, float]:
        return {"x": round(self.x, 2), "y": round(self.y, 2),
                "w": round(self.w, 2), "h": round(self.h, 2)}


@dataclass
class Canvas:
    width: float
    height: float
    unit: str = "dp"
    density: float = 1.0

    @property
    def orientation(self) -> Orientation:
        return Orientation.LANDSCAPE if self.width > self.height else Orientation.PORTRAIT

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {"width": self.width, "height": self.height, "unit": self.unit,
                "density": self.density, "orientation": self.orientation.value}


@dataclass
class Element:
    id: str
    type: ElementType
    bounds: Bounds
    quadrant: Optional[Quadrant] = None
    critical: bool = False
    priority: float = 0.5
    min_size: Size = field(default_factory=lambda: Size(48.0, 48.0))
    scrollable: bool = False
    text: Optional[str] = None
    z: int = 0
    # Tamano de diseno, independiente de la orientacion. El motor escala
    # siempre a partir de este valor, nunca a partir de las coordenadas del
    # layout anterior; de lo contrario el encogimiento se acumularia y una
    # rotacion de ida y vuelta no devolveria el layout a su sitio.
    design_size: Optional[Size] = None

    def intrinsic_size(self) -> Size:
        return self.design_size or Size(self.bounds.w, self.bounds.h)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "bounds": self.bounds.to_dict(),
            "quadrant": self.quadrant.value if self.quadrant else None,
            "critical": self.critical,
            "priority": round(self.priority, 3),
            "min_size": {"w": self.min_size.w, "h": self.min_size.h},
            "design_size": {"w": self.intrinsic_size().w,
                            "h": self.intrinsic_size().h},
            "scrollable": self.scrollable,
            "text": self.text,
            "z": self.z,
        }


@dataclass
class Transition:
    element_id: str
    from_bounds: Bounds
    to_bounds: Bounds
    duration_ms: int
    delay_ms: int = 0
    easing: Easing = Easing.FAST_OUT_SLOW_IN
    # "move" | "enter" | "exit" | "stay"
    kind: str = "move"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "element_id": self.element_id,
            "from": self.from_bounds.to_dict(),
            "to": self.to_bounds.to_dict(),
            "duration_ms": self.duration_ms,
            "delay_ms": self.delay_ms,
            "easing": self.easing.value,
            "kind": self.kind,
        }


@dataclass
class Layout:
    canvas: Canvas
    elements: List[Element]
    layout_id: str = "layout"
    schema_version: str = SCHEMA_VERSION
    generated_by: Dict[str, Any] = field(default_factory=dict)
    transitions: List[Transition] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    animation_budget_ms: int = 300

    def by_id(self, element_id: str) -> Optional[Element]:
        for e in self.elements:
            if e.id == element_id:
                return e
        return None

    def quadrant_map(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {q.value: [] for q in Quadrant}
        for e in self.elements:
            if e.quadrant:
                out[e.quadrant.value].append(e.id)
        return out

    @property
    def total_animation_ms(self) -> int:
        if not self.transitions:
            return 0
        return max(t.delay_ms + t.duration_ms for t in self.transitions)

    def to_dict(self, include_transitions: bool = True) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "layout_id": self.layout_id,
            "canvas": self.canvas.to_dict(),
            "generated_by": self.generated_by,
            "elements": [e.to_dict() for e in self.elements],
            "quadrant_map": self.quadrant_map(),
            "metrics": self.metrics,
            "animation": {
                "strategy": "rolling",
                "budget_ms": self.animation_budget_ms,
                "total_duration_ms": self.total_animation_ms,
            },
        }
        if include_transitions:
            d["transitions"] = [t.to_dict() for t in self.transitions]
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Layout":
        canvas = Canvas(**{k: d["canvas"][k] for k in ("width", "height")
                           if k in d["canvas"]},
                        unit=d["canvas"].get("unit", "dp"),
                        density=d["canvas"].get("density", 1.0))
        elements: List[Element] = []
        for raw in d.get("elements", []):
            b = raw["bounds"]
            q = raw.get("quadrant")
            ms = raw.get("min_size") or {}
            ds = raw.get("design_size") or {}
            elements.append(Element(
                id=raw["id"],
                type=ElementType(raw["type"]),
                bounds=Bounds(b["x"], b["y"], b["w"], b["h"]),
                quadrant=Quadrant(q) if q else None,
                critical=bool(raw.get("critical", False)),
                priority=float(raw.get("priority", 0.5)),
                min_size=Size(float(ms.get("w", 48.0)), float(ms.get("h", 48.0))),
                scrollable=bool(raw.get("scrollable", False)),
                text=raw.get("text"),
                z=int(raw.get("z", 0)),
                design_size=(Size(float(ds["w"]), float(ds["h"]))
                             if ds.get("w") and ds.get("h") else None),
            ))
        return Layout(
            canvas=canvas,
            elements=elements,
            layout_id=d.get("layout_id", "layout"),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            generated_by=d.get("generated_by", {}),
            metrics=d.get("metrics", {}),
            animation_budget_ms=int(
                (d.get("animation") or {}).get("budget_ms", 300)),
        )

    def validate(self) -> List[str]:
        """Devuelve la lista de violaciones del schema (vacia si es valido)."""
        errs: List[str] = []
        if self.schema_version != SCHEMA_VERSION:
            errs.append(f"schema_version inesperado: {self.schema_version}")
        seen = set()
        for e in self.elements:
            if e.id in seen:
                errs.append(f"id duplicado: {e.id}")
            seen.add(e.id)
            if e.bounds.w <= 0 or e.bounds.h <= 0:
                errs.append(f"{e.id}: bounds no positivos")
            if e.critical and (e.bounds.w < e.min_size.w - 0.01
                               or e.bounds.h < e.min_size.h - 0.01):
                errs.append(f"{e.id}: elemento critico por debajo de min_size")
        return errs


def quadrant_of_point(x: float, y: float, canvas: Canvas) -> Quadrant:
    """Cuadrante espacial que contiene el punto (x, y)."""
    left = x < canvas.width / 2.0
    top = y < canvas.height / 2.0
    if top and left:
        return Quadrant.TOP_LEFT
    if top and not left:
        return Quadrant.TOP_RIGHT
    if not top and left:
        return Quadrant.BOTTOM_LEFT
    return Quadrant.BOTTOM_RIGHT


def assign_quadrant(bounds: Bounds, canvas: Canvas) -> Quadrant:
    """Cuadrante que contiene el centro del elemento."""
    cx, cy = bounds.center()
    return quadrant_of_point(cx, cy, canvas)


def asdict_any(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    return asdict(obj)
