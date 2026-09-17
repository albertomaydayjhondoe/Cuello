#!/usr/bin/env python3
"""Comprueba que el port JS del motor coincide con el Python.

El motor existe tres veces (Python, Kotlin, JS). Sin una comprobacion
automatica, los tres divergen en cuanto se toca uno. Este script es la red de
seguridad: ejecuta `node web/parity.mjs`, compara cuadrantes y geometria con
`core/nresponsive/rolling.py` y falla si se separan.

Uso:
    python scripts/check_parity.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "core"))

from nresponsive import Canvas  # noqa: E402
from nresponsive.generator import template_to_elements  # noqa: E402
from nresponsive.rolling import RollingEngine  # noqa: E402

CANVASES = {
    "portrait": Canvas(width=411, height=914),
    "landscape": Canvas(width=914, height=411),
}

TOLERANCE = 0.05  # dp; solo absorbe el redondeo a dos decimales


def python_output() -> dict:
    engine = RollingEngine()
    out: dict = {}
    for template in ("media_player", "dashboard"):
        for name, canvas in CANVASES.items():
            elements = template_to_elements(template, canvas)
            layout = engine.plan(elements, canvas)
            out[f"{template}/{name}"] = [
                [e.id, e.quadrant.value,
                 round(e.bounds.x, 2), round(e.bounds.y, 2),
                 round(e.bounds.w, 2), round(e.bounds.h, 2)]
                for e in layout.elements
            ]
            out[f"{template}/{name}/transitions"] = [
                [t.element_id, t.kind, t.delay_ms, t.duration_ms]
                for t in layout.transitions
            ]
    return out


def js_output() -> dict:
    proc = subprocess.run(
        ["node", str(REPO_ROOT / "web" / "parity.mjs")],
        capture_output=True, text=True, cwd=REPO_ROOT / "web",
    )
    if proc.returncode != 0:
        raise SystemExit(f"node fallo:\n{proc.stderr}")
    return json.loads(proc.stdout)


def main() -> int:
    try:
        js = js_output()
    except FileNotFoundError:
        print("node no esta disponible; se omite la comprobacion de paridad.",
              file=sys.stderr)
        return 0

    py = python_output()
    problems: list[str] = []

    if set(py) != set(js):
        problems.append(f"conjuntos distintos: py={sorted(py)} js={sorted(js)}")

    for key in sorted(set(py) & set(js)):
        if key.endswith("/transitions"):
            py_rows = [tuple(r) for r in py[key]]
            js_rows = [tuple(r) for r in js[key]]
            if py_rows != js_rows:
                problems.append(
                    f"{key}: plan de transiciones distinto\n"
                    f"      py={py_rows}\n      js={js_rows}")
            continue
        py_rows = {r[0]: r for r in py[key]}
        js_rows = {r[0]: r for r in js[key]}
        if set(py_rows) != set(js_rows):
            problems.append(f"{key}: elementos distintos py={sorted(py_rows)} js={sorted(js_rows)}")
            continue
        for eid, pr in py_rows.items():
            jr = js_rows[eid]
            if pr[1] != jr[1]:
                problems.append(f"{key}/{eid}: cuadrante py={pr[1]} js={jr[1]}")
            for i, field in enumerate(("x", "y", "w", "h"), start=2):
                if abs(pr[i] - jr[i]) > TOLERANCE:
                    problems.append(
                        f"{key}/{eid}: {field} py={pr[i]} js={jr[i]} "
                        f"(delta {abs(pr[i]-jr[i]):.2f})")

    if problems:
        print(f"DIVERGENCIAS ({len(problems)}):", file=sys.stderr)
        for p in problems[:40]:
            print(f"  {p}", file=sys.stderr)
        return 1

    total = sum(len(v) for k, v in py.items() if not k.endswith("/transitions"))
    n_trans = sum(len(v) for k, v in py.items() if k.endswith("/transitions"))
    print(f"paridad OK: {len(py)} escenarios, {total} elementos, "
          f"{n_trans} transiciones, tolerancia {TOLERANCE} dp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())