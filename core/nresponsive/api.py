"""Endpoint FastAPI local de generacion de layouts nresponsive.

Arranque:

    PYTHONPATH=core uvicorn nresponsive.api:app --reload --port 8000

El endpoint principal es POST /layout. Es tolerante a fallos: si el modo LLM
esta activo y el modelo no responde, devuelve el layout offline con
``generated_by.source = "offline-template"`` y el motivo del fallback, de modo
que la app Android nunca se queda sin layout.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Faltan dependencias de la API. Instala con:\n"
        "    pip install -r api/requirements.txt\n"
        f"(error original: {exc})"
    ) from exc

from .generator import DEFAULT_TEMPLATE, TEMPLATES, LayoutGenerator
from .metrics import evaluate
from .rolling import RollingEngine
from .schema import Canvas, Layout, Orientation
import os

app = FastAPI(
    title="nresponsive layout API",
    version="1.0.0",
    description="Genera layouts adaptativos por orientacion con plan de "
                "animacion 'rolling'.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("NRESPONSIVE_CORS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class DeviceContext(BaseModel):
    model: str = "generic-android"
    width_dp: float = 411
    height_dp: float = 914
    density: float = 2.625
    orientation: Optional[Orientation] = None
    locale: str = "es"
    # Senales de uso que alimentan al generador.
    session_minutes: float = 0.0
    one_handed: bool = False
    top_actions: List[str] = Field(default_factory=list)


class LayoutRequest(BaseModel):
    template: str = DEFAULT_TEMPLATE
    canvas: Optional[Dict[str, float]] = None
    device: DeviceContext = Field(default_factory=DeviceContext)
    previous_layout: Optional[Dict[str, Any]] = None
    mode: Optional[str] = None


def _generator(mode: Optional[str]) -> LayoutGenerator:
    return LayoutGenerator(
        mode=mode or os.environ.get("NRESPONSIVE_MODE", "offline"),
        model=os.environ.get("NRESPONSIVE_MODEL"),
        base_url=os.environ.get("NRESPONSIVE_BASE_URL"),
        api_key=os.environ.get("OPENAI_API_KEY"),
        engine=RollingEngine(budget_ms=int(
            os.environ.get("NRESPONSIVE_BUDGET_MS", "300"))),
    )


def _resolve_canvas(req: LayoutRequest) -> Canvas:
    if req.canvas:
        return Canvas(width=float(req.canvas["width"]),
                      height=float(req.canvas["height"]),
                      density=float(req.canvas.get("density", 1.0)))
    d = req.device
    w, h = d.width_dp, d.height_dp
    if d.orientation == Orientation.LANDSCAPE and h > w:
        w, h = h, w
    elif d.orientation == Orientation.PORTRAIT and w > h:
        w, h = h, w
    return Canvas(width=w, height=h, density=d.density)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "templates": list(TEMPLATES),
            "mode": os.environ.get("NRESPONSIVE_MODE", "offline")}


@app.get("/templates")
def templates() -> Dict[str, Any]:
    return {"templates": list(TEMPLATES), "default": DEFAULT_TEMPLATE}


@app.post("/layout")
def layout(req: LayoutRequest) -> Dict[str, Any]:
    if req.template not in TEMPLATES:
        raise HTTPException(status_code=404,
                            detail=f"plantilla desconocida: {req.template}")
    canvas = _resolve_canvas(req)
    prev: Optional[Layout] = None
    if req.previous_layout:
        try:
            prev = Layout.from_dict(req.previous_layout)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400,
                                detail=f"previous_layout invalido: {exc}") from exc

    gen = _generator(req.mode)
    result, provenance = gen.generate(
        canvas, req.template,
        context=req.device.model_dump(),
        previous=prev,
    )
    result.metrics = evaluate(result.elements, canvas).to_dict()
    errs = result.validate()
    out = result.to_dict()
    out["generated_by"].update(provenance)
    out["validation_errors"] = errs
    out["rotation"] = {
        "is_rotation": prev is not None
        and prev.canvas.width == canvas.height
        and prev.canvas.height == canvas.width,
        "previous_orientation": prev.canvas.orientation.value if prev else None,
        "current_orientation": canvas.orientation.value,
    }
    return out


@app.post("/evaluate")
def evaluate_layout(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Recalcula metricas de un layout ya generado."""
    try:
        lay = Layout.from_dict(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400,
                            detail=f"layout invalido: {exc}") from exc
    return {"metrics": evaluate(lay.elements, lay.canvas).to_dict(),
            "validation_errors": lay.validate()}