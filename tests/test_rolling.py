"""Tests del motor de rolling.

Cubre los criterios de verificacion del encargo:
  * al pasar de retrato a apaisado la disposicion se actualiza;
  * los elementos criticos (accion y navegacion) siguen visibles y dentro
    del canvas tras la rotacion;
  * el plan de animacion cabe en el presupuesto de 300 ms;
  * no se pierde ni se duplica ningun elemento;
  * las metricas mejoran o se mantienen respecto de una linea base naive.
"""

from __future__ import annotations

import json

import pytest

from nresponsive import (
    Canvas,
    Element,
    ElementType,
    LayoutGenerator,
    Orientation,
    Quadrant,
    RollingEngine,
    assign_quadrant,
    evaluate,
    overlap_ratio,
    sample_layout,
    teleport_distance,
)
from nresponsive.generator import TEMPLATES, template_to_elements

PORTRAIT = Canvas(width=411.0, height=914.0)
LANDSCAPE = Canvas(width=914.0, height=411.0)


@pytest.fixture
def engine() -> RollingEngine:
    return RollingEngine()


def _ids(layout):
    return [e.id for e in layout.elements]


# --------------------------------------------------------------------------
# Reasignacion de cuadrantes
# --------------------------------------------------------------------------
def test_quadrant_assignment_of_known_points():
    assert assign_quadrant(_b(10, 10, 10, 10), PORTRAIT) == Quadrant.TOP_LEFT
    assert assign_quadrant(_b(400, 10, 10, 10), PORTRAIT) == Quadrant.TOP_RIGHT
    assert assign_quadrant(_b(10, 900, 10, 10), PORTRAIT) == Quadrant.BOTTOM_LEFT
    assert assign_quadrant(_b(400, 900, 10, 10), PORTRAIT) == Quadrant.BOTTOM_RIGHT


def _b(x, y, w, h):
    from nresponsive import Bounds
    return Bounds(x, y, w, h)


def test_nav_moves_from_bottom_bar_to_side_rail(engine):
    """La navegacion cambia de cuadrante al girar: es el 'rolling'."""
    elements = template_to_elements("media_player", PORTRAIT)
    portrait = engine.plan(elements, PORTRAIT)

    rotated = engine.plan(portrait.elements, LANDSCAPE, previous=portrait)
    nav = rotated.by_id("nav")

    assert nav is not None
    # En apaisado la navegacion vive en el rail izquierdo.
    assert nav.bounds.x < LANDSCAPE.width * 0.15
    assert nav.bounds.right() <= LANDSCAPE.width * 0.25 + 1
    # El FAB se mantiene en la esquina inferior derecha y no solapa el rail.
    fab = rotated.by_id("fab")
    assert fab.bounds.x > LANDSCAPE.width * 0.5
    assert fab.bounds.intersection(nav.bounds) == 0


def test_quadrant_map_distributes_elements(engine):
    elements = template_to_elements("dashboard", PORTRAIT)
    layout = engine.plan(elements, PORTRAIT)
    qm = layout.quadrant_map()
    assert sum(len(v) for v in qm.values()) == len(layout.elements)
    # Al menos tres cuadrantes deben estar ocupados en una pantalla real.
    assert sum(1 for v in qm.values() if v) >= 3


# --------------------------------------------------------------------------
# Criterio central: rotacion sin perder elementos criticos
# --------------------------------------------------------------------------
@pytest.mark.parametrize("template", list(TEMPLATES))
def test_rotation_preserves_all_elements(engine, template):
    portrait = engine.plan(template_to_elements(template, PORTRAIT), PORTRAIT)
    rotated = engine.plan(portrait.elements, LANDSCAPE, previous=portrait)

    assert sorted(_ids(rotated)) == sorted(_ids(portrait))
    assert rotated.canvas.orientation == Orientation.LANDSCAPE


@pytest.mark.parametrize("template", list(TEMPLATES))
def test_rotation_keeps_critical_elements_visible(engine, template):
    """Los botones de accion y la navegacion nunca desaparecen."""
    portrait = engine.plan(template_to_elements(template, PORTRAIT), PORTRAIT)
    rotated = engine.plan(portrait.elements, LANDSCAPE, previous=portrait)

    crit = [e for e in rotated.elements if e.critical]
    assert crit, "el template debe declarar elementos criticos"

    for e in crit:
        b = e.bounds
        assert b.x >= -0.01 and b.y >= -0.01, f"{e.id} fuera del canvas"
        assert b.right() <= rotated.canvas.width + 0.01, f"{e.id} se sale a la derecha"
        assert b.bottom() <= rotated.canvas.height + 0.01, f"{e.id} se sale abajo"
        assert b.w >= e.min_size.w - 0.01, f"{e.id} mas angosto que su min_size"
        assert b.h >= e.min_size.h - 0.01, f"{e.id} mas bajo que su min_size"


@pytest.mark.parametrize("template", list(TEMPLATES))
def test_round_trip_rotation_is_stable(engine, template):
    """Girar dos veces devuelve TODOS los elementos a su sitio.

    Se comprueba sobre el layout completo y no solo sobre los criticos: los
    elementos no criticos son justo los que se descolocan sin que nadie lo
    note. Una politica de cuadrantes que dependa de donde cae el elemento
    dominante rompe esta identidad (medido: 244 dp de deriva en media_player),
    asi que el test la vigila.
    """
    portrait = engine.plan(template_to_elements(template, PORTRAIT), PORTRAIT)
    landscape = engine.plan(portrait.elements, LANDSCAPE, previous=portrait)
    back = engine.plan(landscape.elements, PORTRAIT, previous=landscape)

    assert sorted(_ids(back)) == sorted(_ids(portrait))
    drift = teleport_distance(portrait.elements, back.elements)
    assert drift < 0.01, f"la ida y vuelta no es identidad: {drift:.2f} dp"
    assert {e.id: e.quadrant for e in portrait.elements} == {
        e.id: e.quadrant for e in back.elements}, "cuadrantes no restaurados"


@pytest.mark.parametrize("template", list(TEMPLATES))
def test_repeated_rotation_does_not_accumulate_drift(engine, template):
    """Veinte viajes seguidos no descolocan la disposicion."""
    current = engine.plan(template_to_elements(template, PORTRAIT), PORTRAIT)
    reference = {e.id: e.bounds for e in current.elements}

    for _ in range(20):
        landscape = engine.plan(current.elements, LANDSCAPE, previous=current)
        current = engine.plan(landscape.elements, PORTRAIT, previous=landscape)

    for e in current.elements:
        ref = reference[e.id]
        assert abs(e.bounds.x - ref.x) < 0.01 and abs(e.bounds.y - ref.y) < 0.01, (
            f"{e.id} derivo tras 20 viajes: ({e.bounds.x:.2f},{e.bounds.y:.2f}) "
            f"vs ({ref.x:.2f},{ref.y:.2f})")


# --------------------------------------------------------------------------
# Ruta servida: las tres interfaces reinstancian la plantilla en el canvas
# destino antes de rotar. Medir de otra forma da cifras que no corresponden a
# ningun interfaz, asi que esta ruta queda fijada por test.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("template", list(TEMPLATES))
def test_served_route_rotation_is_equivalent_to_reinstantiating(template):
    """Rotar por la ruta servida == plantilla nativa del destino + previous."""
    from nresponsive import LayoutGenerator

    gen = LayoutGenerator()
    portrait, _ = gen.generate(PORTRAIT, template, context={}, previous=None)
    rotated, _ = gen.generate(LANDSCAPE, template, context={}, previous=portrait)

    # Equivalente: instanciar la plantilla en el canvas destino y pasar el
    # layout de retrato como anterior.
    direct = RollingEngine().plan(
        template_to_elements(template, LANDSCAPE), LANDSCAPE, previous=portrait)

    assert {e.id: e.bounds for e in rotated.elements} == {
        e.id: e.bounds for e in direct.elements}


@pytest.mark.parametrize("template", list(TEMPLATES))
def test_served_route_rotation_keeps_quality(template):
    """La ruta servida no hunde las metricas al rotar.

    Fija el suelo medido (prominence >= 0.85, composite >= 0.60) para que una
    regresion en el generador o en el motor no pase inadvertida.
    """
    from nresponsive import LayoutGenerator

    gen = LayoutGenerator()
    portrait, _ = gen.generate(PORTRAIT, template, context={}, previous=None)
    rotated, _ = gen.generate(LANDSCAPE, template, context={}, previous=portrait)
    m = evaluate(rotated.elements, LANDSCAPE)

    assert m.prominence_score >= 0.85, f"prominencia degradada: {m.prominence_score}"
    assert m.composite() >= 0.60, f"composite degradado: {m.composite()}"
    assert m.critical_visible, "algun critico quedo fuera del canvas"
    assert rotated.animation_budget_ms <= 300


# --------------------------------------------------------------------------
# Animacion dentro del presupuesto
# --------------------------------------------------------------------------
@pytest.mark.parametrize("template", list(TEMPLATES))
def test_animation_fits_budget(engine, template):
    portrait = engine.plan(template_to_elements(template, PORTRAIT), PORTRAIT)
    rotated = engine.plan(portrait.elements, LANDSCAPE, previous=portrait)

    assert rotated.transitions, "una rotacion debe producir transiciones"
    for t in rotated.transitions:
        assert t.delay_ms >= 0
        assert t.duration_ms >= 60
    assert rotated.total_animation_ms < rotated.animation_budget_ms, (
        f"{template}: animacion {rotated.total_animation_ms} ms no es < "
        f"presupuesto {rotated.animation_budget_ms} ms"
    )
    # El criterio de aceptacion es "< 300 ms" en terminos absolutos, no solo
    # respecto al presupuesto configurado.
    assert rotated.total_animation_ms < 300, (
        f"{template}: animacion {rotated.total_animation_ms} ms no es < 300 ms"
    )


def test_transitions_reference_existing_elements(engine):
    portrait = engine.plan(template_to_elements("media_player", PORTRAIT), PORTRAIT)
    rotated = engine.plan(portrait.elements, LANDSCAPE, previous=portrait)
    ids = set(_ids(rotated))
    for t in rotated.transitions:
        assert t.element_id in ids
        assert t.to_bounds.w > 0 and t.to_bounds.h > 0


def test_critical_elements_use_fast_easing(engine):
    portrait = engine.plan(template_to_elements("media_player", PORTRAIT), PORTRAIT)
    rotated = engine.plan(portrait.elements, LANDSCAPE, previous=portrait)
    crit_ids = {e.id for e in rotated.elements if e.critical}
    for t in rotated.transitions:
        if t.element_id in crit_ids:
            assert t.easing.value == "FastOutSlowIn"


# --------------------------------------------------------------------------
# Calidad geometrica
# --------------------------------------------------------------------------
@pytest.mark.parametrize("template", list(TEMPLATES))
def test_no_unintended_overlap_after_rotation(engine, template):
    portrait = engine.plan(template_to_elements(template, PORTRAIT), PORTRAIT)
    rotated = engine.plan(portrait.elements, LANDSCAPE, previous=portrait)
    ratio = overlap_ratio(rotated.elements, rotated.canvas)
    assert ratio < 0.02, f"{template}: solape {ratio:.4f} del canvas"


@pytest.mark.parametrize("template", list(TEMPLATES))
def test_metrics_are_better_than_naive_scaling(engine, template):
    """El rolling debe superar a un simple escalado proporcional."""
    portrait = engine.plan(template_to_elements(template, PORTRAIT), PORTRAIT)
    rotated = engine.plan(portrait.elements, LANDSCAPE, previous=portrait)

    naive = _naive_scale(portrait, LANDSCAPE)
    assert evaluate(rotated.elements, rotated.canvas).composite() >= \
        evaluate(naive, LANDSCAPE).composite()


def _naive_scale(layout, target: Canvas):
    """Linea base: estira las coordenadas al nuevo canvas."""
    sx = target.width / layout.canvas.width
    sy = target.height / layout.canvas.height
    out = []
    for e in layout.elements:
        out.append(Element(
            id=e.id, type=e.type,
            bounds=_b(e.bounds.x * sx, e.bounds.y * sy,
                      e.bounds.w * sx, e.bounds.h * sy),
            critical=e.critical, priority=e.priority, min_size=e.min_size,
        ))
    return out


def test_metrics_are_coherent(engine):
    portrait = engine.plan(template_to_elements("dashboard", PORTRAIT), PORTRAIT)
    m = evaluate(portrait.elements, PORTRAIT)
    d = m.to_dict()
    for key in ("overlap_ratio", "coverage_ratio", "whitespace_ratio",
                "center_fill", "alignment_score", "prominence_score"):
        assert 0.0 <= d[key] <= 1.0, f"{key} fuera de rango: {d[key]}"
    assert m.critical_visible is True
    assert 0.0 <= m.composite() <= 1.0


# --------------------------------------------------------------------------
# Contrato JSON / schema
# --------------------------------------------------------------------------
def test_layout_json_is_self_consistent(engine):
    portrait = engine.plan(template_to_elements("media_player", PORTRAIT), PORTRAIT)
    doc = portrait.to_dict()
    assert doc["schema_version"] == "nresponsive/1.0"
    assert doc["canvas"]["orientation"] == "portrait"
    assert doc["animation"]["strategy"] == "rolling"

    from nresponsive import Layout
    restored = Layout.from_dict(doc)
    assert _ids(restored) == _ids(portrait)
    assert restored.canvas.width == portrait.canvas.width
    assert restored.validate() == []


def test_generated_sample_layout_validates():
    doc = sample_layout("media_player")
    from nresponsive import Layout
    lay = Layout.from_dict(doc)
    assert lay.validate() == []
    # Debe poder serializarse a JSON sin perder nada.
    assert json.loads(json.dumps(doc))["elements"]


def test_rotated_element_preserves_min_size_contract(engine):
    """Un elemento critico no puede encogerse por debajo del target tactil."""
    elements = template_to_elements("dashboard", PORTRAIT)
    layout = engine.plan(elements, LANDSCAPE, previous=None)
    search = layout.by_id("search")
    assert search.bounds.w >= search.min_size.w - 0.01
    assert search.bounds.h >= search.min_size.h - 0.01


def test_anchors_have_meaningful_design_size():
    """Los anclajes (nav, fab) deben declarar su tamano minimo como diseno.

    Si se instancian con bounds 1x1, el tamano de diseno queda en 1x1 y el motor
    razona sobre una superficie que no significa nada. Es un fallo silencioso:
    no rompe ningun calculo, solo produce layouts peores.
    """
    elements = template_to_elements("media_player", PORTRAIT)
    for e in elements:
        assert e.intrinsic_size().w > 1.0, f"{e.id} con ancho de diseno degenerado"
        assert e.intrinsic_size().h > 1.0, f"{e.id} con alto de diseno degenerado"
    nav = next(e for e in elements if e.id == "nav")
    assert nav.intrinsic_size().w == nav.min_size.w
    assert nav.intrinsic_size().h == nav.min_size.h