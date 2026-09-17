"""Generacion de layouts: LLM opcional con fallback offline determinista.

Dos modos:

  * ``--mode offline`` (por defecto): usa una plantilla de cuadrantes
    determinista. Cero dependencias, cero red, reproducible. Satisface el
    requisito "el sistema debe ser funcional incluso sin conexion".
  * ``--mode llm``: consulta un endpoint compatible con OpenAI. Si falla
    (sin red, timeout, JSON invalido), cae automaticamente al modo offline.

El JSON que devuelve el modelo se valida contra el schema y, si es invalido,
se descarta y se usa la plantilla. Nunca se propaga un layout roto a la UI.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .rolling import RollingEngine, content_bounds, anchor_slots
from .schema import (
    Bounds,
    Canvas,
    Element,
    ElementType,
    Layout,
    Orientation,
)

# Plantilla de pantallas moviles. Se declara como fracciones del canvas para
# ser independiente de la orientacion y del tamano en dp.
TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "media_player": [
        {"id": "header", "type": "text", "fx": 0.04, "fy": 0.03,
         "fw": 0.92, "fh": 0.06, "priority": 0.6, "text": "Now playing"},
        {"id": "cover", "type": "image", "fx": 0.10, "fy": 0.11,
         "fw": 0.80, "fh": 0.42, "priority": 0.9},
        {"id": "progress", "type": "container", "fx": 0.10, "fy": 0.56,
         "fw": 0.80, "fh": 0.03, "priority": 0.7},
        {"id": "play", "type": "button", "fx": 0.40, "fy": 0.62,
         "fw": 0.20, "fh": 0.08, "priority": 1.0, "critical": True,
         "min_w": 56, "min_h": 48, "text": "Play"},
        {"id": "prev", "type": "button", "fx": 0.16, "fy": 0.62,
         "fw": 0.14, "fh": 0.08, "priority": 0.8, "critical": True,
         "min_w": 48, "min_h": 48},
        {"id": "next", "type": "button", "fx": 0.70, "fy": 0.62,
         "fw": 0.14, "fh": 0.08, "priority": 0.8, "critical": True,
         "min_w": 48, "min_h": 48},
        {"id": "related", "type": "list", "fx": 0.04, "fy": 0.72,
         "fw": 0.92, "fh": 0.16, "priority": 0.5, "scrollable": True},
        {"id": "nav", "type": "nav", "priority": 1.0, "critical": True,
         "min_w": 48, "min_h": 56},
        {"id": "fab", "type": "fab", "priority": 1.0, "critical": True,
         "min_w": 56, "min_h": 56},
    ],
    "dashboard": [
        {"id": "title", "type": "text", "fx": 0.04, "fy": 0.03, "fw": 0.60,
         "fh": 0.05, "priority": 0.7, "text": "Dashboard"},
        {"id": "kpi1", "type": "container", "fx": 0.04, "fy": 0.10, "fw": 0.44,
         "fh": 0.14, "priority": 0.8},
        {"id": "kpi2", "type": "container", "fx": 0.52, "fy": 0.10, "fw": 0.44,
         "fh": 0.14, "priority": 0.8},
        {"id": "chart", "type": "image", "fx": 0.04, "fy": 0.26, "fw": 0.92,
         "fh": 0.34, "priority": 0.9},
        {"id": "search", "type": "input", "fx": 0.04, "fy": 0.62, "fw": 0.92,
         "fh": 0.06, "priority": 0.6, "critical": True, "min_w": 120,
         "min_h": 48},
        {"id": "list", "type": "list", "fx": 0.04, "fy": 0.70, "fw": 0.92,
         "fh": 0.18, "priority": 0.5, "scrollable": True},
        {"id": "nav", "type": "nav", "priority": 1.0, "critical": True,
         "min_w": 48, "min_h": 56},
    ],
}

DEFAULT_TEMPLATE = "media_player"


def template_to_elements(template: str, canvas: Canvas) -> List[Element]:
    """Instancia una plantilla en las dimensiones concretas de `canvas`."""
    spec = TEMPLATES.get(template)
    if spec is None:
        raise KeyError(f"plantilla desconocida: {template}")
    out: List[Element] = []
    for item in spec:
        min_size = _size(item.get("min_w", 48), item.get("min_h", 48))
        if "fx" in item:
            b = Bounds(item["fx"] * canvas.width, item["fy"] * canvas.height,
                       item["fw"] * canvas.width, item["fh"] * canvas.height)
        else:
            # Los anclajes los situa el motor. Su posicion aqui es provisional,
            # pero el tamano de diseno debe ser el minimo real del elemento: si
            # fuese 1x1, `_scale_to_fit` y el empaquetado razonarian sobre un
            # tamano que no significa nada.
            b = Bounds(0, 0, min_size.w, min_size.h)
        out.append(Element(
            id=item["id"],
            type=ElementType(item["type"]),
            bounds=b,
            critical=bool(item.get("critical", False)),
            priority=float(item.get("priority", 0.5)),
            min_size=min_size,
            scrollable=bool(item.get("scrollable", False)),
            text=item.get("text"),
            design_size=_size(b.w, b.h),
        ))
    return out


def _size(w: float, h: float):
    from .schema import Size
    return Size(w, h)


class LayoutGenerator:
    """Genera layouts; el LLM es opcional y siempre tiene fallback."""

    def __init__(self, mode: str = "offline", model: Optional[str] = None,
                 base_url: Optional[str] = None, api_key: Optional[str] = None,
                 engine: Optional[RollingEngine] = None) -> None:
        self.mode = mode
        self.model = model or os.environ.get("NRESPONSIVE_MODEL", "gpt-4o-mini")
        self.base_url = base_url or os.environ.get(
            "NRESPONSIVE_BASE_URL", "https://api.openai.com/v1")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.engine = engine or RollingEngine()

    # -- API -------------------------------------------------------------
    def generate(self, canvas: Canvas, template: str = DEFAULT_TEMPLATE,
                 context: Optional[Dict[str, Any]] = None,
                 previous: Optional[Layout] = None,
                 ) -> tuple[Layout, Dict[str, Any]]:
        """Devuelve (layout, procedencia).

        `procedencia` indica que via se uso finalmente, para trazabilidad.
        """
        context = context or {}
        if self.mode == "llm":
            layout, info = self._try_llm(canvas, template, context, previous)
            if layout is not None:
                return layout, info
            fallback, finfo = self._offline(canvas, template, previous)
            finfo["fallback_reason"] = info.get("error", "llm-unavailable")
            return fallback, finfo
        return self._offline(canvas, template, previous)

    # -- Offline ---------------------------------------------------------
    def _offline(self, canvas: Canvas, template: str,
                 previous: Optional[Layout],
                 ) -> tuple[Layout, Dict[str, Any]]:
        elements = template_to_elements(template, canvas)
        layout = self.engine.plan(elements, canvas, previous=previous,
                                  layout_id=f"{template}-{canvas.orientation.value}")
        return layout, {"source": "offline-template", "template": template,
                        "model": None, "network": False}

    # -- LLM -------------------------------------------------------------
    def _try_llm(self, canvas: Canvas, template: str,
                 context: Dict[str, Any], previous: Optional[Layout],
                 ) -> tuple[Optional[Layout], Dict[str, Any]]:
        if not self.api_key:
            return None, {"source": "llm", "error": "sin OPENAI_API_KEY",
                          "network": True}
        try:
            raw = self._call_llm(canvas, template, context, previous)
            elements = self._parse_llm_elements(raw, canvas)
            layout = self.engine.plan(elements, canvas, previous=previous,
                                      layout_id=f"llm-{canvas.orientation.value}")
            return layout, {"source": "llm", "model": self.model,
                            "network": True, "endpoint": self.base_url}
        except Exception as exc:  # noqa: BLE001 - el fallback es el contrato
            return None, {"source": "llm", "error": f"{type(exc).__name__}: {exc}",
                          "network": True}

    def _call_llm(self, canvas: Canvas, template: str,
                  context: Dict[str, Any], previous: Optional[Layout]) -> str:
        import urllib.request

        prompt = self._build_prompt(canvas, template, context, previous)
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system",
                 "content": "You are a UI layout generator. Reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]

    @staticmethod
    def _build_prompt(canvas: Canvas, template: str, context: Dict[str, Any],
                      previous: Optional[Layout]) -> str:
        prev_desc = "none"
        if previous is not None:
            prev_desc = json.dumps(
                [{"id": e.id, "type": e.type.value, "bounds": e.bounds.to_dict()}
                 for e in previous.elements])
        return (
            "Generate a mobile UI layout as JSON.\n"
            f"Canvas: {canvas.width}x{canvas.height} dp, "
            f"orientation={canvas.orientation.value}.\n"
            f"Screens: {', '.join(TEMPLATES)}\n"
            f"Requested screen: {template}\n"
            f"Device/usage context: {json.dumps(context)}\n"
            f"Previous layout: {prev_desc}\n"
            "Rules: keep every element inside the canvas; never let elements "
            "overlap except containers; place the largest element in a "
            "prominent position; keep the centre band occupied; navigation "
            "and primary action elements must keep at least 48dp.\n"
            'Respond as {"elements":[{"id":str,"type":str,"bounds":'
            '{"x":num,"y":num,"w":num,"h":num},"critical":bool,'
            '"priority":num}]}'
        )

    @staticmethod
    def _parse_llm_elements(raw: str, canvas: Canvas) -> List[Element]:
        """Parsea y sanea la respuesta del modelo. Lanza si es inusable."""
        doc = json.loads(raw)
        items = doc.get("elements") if isinstance(doc, dict) else None
        if not isinstance(items, list) or not items:
            raise ValueError("respuesta sin 'elements'")
        out: List[Element] = []
        for it in items:
            b = it["bounds"]
            ew, eh = float(b["w"]), float(b["h"])
            if ew <= 0 or eh <= 0:
                raise ValueError(f"bounds invalidos para {it.get('id')}")
            out.append(Element(
                id=str(it["id"]),
                type=ElementType(it.get("type", "container")),
                bounds=Bounds(float(b["x"]), float(b["y"]), ew, eh),
                critical=bool(it.get("critical", False)),
                priority=float(it.get("priority", 0.5)),
                min_size=_size(*( (56, 56) if it.get("critical") else (1, 1) )),
            ))
        # Validacion estructural: un layout con ids duplicados o vacio se
        # considera inutilizable.
        ids = [e.id for e in out]
        if len(set(ids)) != len(ids):
            raise ValueError("ids duplicados en la respuesta del modelo")
        return out


def sample_layout(template: str = DEFAULT_TEMPLATE,
                  width: float = 411.0, height: float = 914.0) -> Dict[str, Any]:
    """JSON de ejemplo listo para incrustar en documentacion o en tests."""
    gen = LayoutGenerator(mode="offline")
    canvas = Canvas(width=width, height=height)
    layout, _ = gen.generate(canvas, template)
    return layout.to_dict()