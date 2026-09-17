#!/usr/bin/env python3
"""Ajuste fino de una cabeza de recompensa de layout sobre feedback humano real.

Antes de leer este script conviene saber que midio y que NO se puede medir con
los datos publicos. El detalle completo esta en docs/LIMITATIONS.md; el
resumen es:

1. `shuolucs/UniLayout-Data` es el unico dataset real de la organizacion. Su
   subdirectorio `dpo_reward_data/` trae dos ficheros con estructura distinta:

     score-reward_model_1.json  4000 muestras CON logits del reward model
     eval-reward_model_1.json   4000 muestras SIN logits (solo etiquetas)

   No existe ningun dataset llamado "Layout-HF100k" en HuggingFace ni en el
   repositorio Uni-Layout.

2. Los pesos del reward model NO estan publicados: `shuolucs/UniLayout-Reward`
   es un LLaVA-Llama de ~13.8 GB cuyo `model.safetensors.index.json` referencia
   tres shards que devuelven HTTP 404. Por tanto no se puede reutilizar el
   checkpoint, solo su formato de datos.

3. Las etiquetas de estos ficheros NO estan alineadas con las geometrias de
   sus bounding boxes. Medido sobre los datos reales:

     correlacion metrica_geometrica  <->  etiqueta   ~ 0.01 a 0.04
     exactitud en validacion cruzada (5-fold)         0.6257
     exactitud de la clase mayoritaria (baseline)     0.6243
     acuerdo del propio reward model con la etiqueta  0.4910

   Es decir: la cabeza entrenada no supera al clasificador trivial, y el
   propio modelo de recompensa acierta menos que una moneda. Entrenar sobre
   esto y reportar una exactitud alta seria enganoso, asi que este script NO
   lo hace: entrena, mide honestamente y falla si no hay senal.

   Modo de uso recomendado: `--mode gate`. Entrena y devuelve codigo de salida
   distinto de cero si la senal no supera el umbral. Es util en CI y como
   prueba reproducible de la limitacion.

4. Lo que SI funciona y esta verificado: las metricas geometricas de
   `core/nresponsive/metrics.py` estan alineadas con las restricciones que el
   evaluador verbaliza en sus prompts ("do not overlap", "prominent position",
   "avoid leaving the important central position vacant"). Se usan en modo
   `--mode heuristic` para puntuar layouts sin necesidad de entrenamiento.

Uso:
    # Comprobar si hay senal de aprendizaje (falla si no la hay)
    python datasets/scripts/finetune_reward.py --mode gate

    # Escribir la cabeza entrenada y sus metricas (aunque sean malas)
    python datasets/scripts/finetune_reward.py --mode train
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "core"))

from nresponsive import Layout, evaluate  # noqa: E402

FEATURE_NAMES = [
    "overlap_ratio",
    "coverage_ratio",
    "whitespace_ratio",
    "center_fill",
    "alignment_score",
    "prominence_score",
    "critical_visible",
    "n_elements_norm",
    "aspect_norm",
    "element_density",
]

# Por debajo de este margen sobre la clase mayoritaria no hay senal util.
MIN_SIGNAL_MARGIN = 0.02


def features_of(layout: Layout) -> List[float]:
    """Vector de caracteristicas geometricas del layout."""
    m = evaluate(layout.elements, layout.canvas)
    d = m.to_dict()
    n = len(layout.elements)
    area = layout.canvas.width * layout.canvas.height
    total_area = sum(e.bounds.area() for e in layout.elements)
    return [
        d["overlap_ratio"],
        d["coverage_ratio"],
        d["whitespace_ratio"],
        d["center_fill"],
        d["alignment_score"],
        d["prominence_score"],
        1.0 if d["critical_visible"] else 0.0,
        min(1.0, n / 30.0),
        min(1.0, layout.canvas.aspect / 3.0),
        total_area / area if area else 0.0,
    ]


def load_split(path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[Any]]:
    """Devuelve (features, reward, label, grupos).

    `label` es el juicio humano binario; `reward` es la recompensa registrada
    en el JSONL (en el fichero `score-` es el softmax del propio reward model,
    que resulta ser casi independiente de `label`).
    `grupos` es el tamano de canvas, usado para la validacion agrupada.
    """
    X: List[List[float]] = []
    y: List[float] = []
    lab: List[float] = []
    groups: List[Any] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            layout = Layout.from_dict(rec["layout"])
            X.append(features_of(layout))
            y.append(float(rec["reward"]))
            lab.append(float(rec["label"]))
            groups.append((layout.canvas.width, layout.canvas.height))
    if not X:
        raise SystemExit(f"split vacio: {path}")
    return (np.asarray(X, dtype=np.float64),
            np.asarray(y, dtype=np.float64),
            np.asarray(lab, dtype=np.float64),
            groups)


def standardize(X: np.ndarray, mean: np.ndarray | None = None,
                std: np.ndarray | None = None):
    if mean is None:
        mean = X.mean(axis=0)
    if std is None:
        std = X.std(axis=0)
    std = np.where(std < 1e-8, 1.0, std)
    return (X - mean) / std, mean, std


def fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    """Solucion en forma cerrada de la regresion ridge, con intercepto."""
    n, d = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    reg = np.eye(d + 1) * alpha
    reg[0, 0] = 0.0  # el intercepto no se penaliza
    return np.linalg.solve(Xb.T @ Xb + reg, Xb.T @ y)


def predict(X: np.ndarray, w: np.ndarray) -> np.ndarray:
    return np.hstack([np.ones((X.shape[0], 1)), X]) @ w


def regression_report(y: np.ndarray, yhat: np.ndarray) -> Dict[str, float]:
    err = yhat - y
    ss_res = float((err ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    yc, pc = y - y.mean(), yhat - yhat.mean()
    denom = float(np.sqrt((pc ** 2).sum() * (yc ** 2).sum()))
    corr = float((pc * yc).sum() / denom) if denom > 0 else 0.0
    return {
        "rmse": float(np.sqrt(ss_res / max(1, len(y)))),
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0,
        "pearson": corr,
        "n": int(len(y)),
    }


def cross_val_accuracy(X: np.ndarray, lab: np.ndarray, folds: int = 5) -> Dict[str, float]:
    """Exactitud en validacion cruzada aleatoria frente a la clase mayoritaria.

    OJO: esta cifra es enganosa en este dataset. Los registros vienen en
    grupos grandes con el mismo tamano de canvas (el grupo 513x750 solo ya es
    dos tercios de los datos), y un split aleatorio filtra informacion de
    plantilla al conjunto de validacion. Usa [group_cv_accuracy], que es la
    validacion honesta.
    """
    rng = np.random.default_rng(0)
    idx = rng.permutation(len(lab))
    accs: List[float] = []
    for k in range(folds):
        te = idx[k::folds]
        tr = np.setdiff1d(idx, te)
        if len(tr) == 0 or len(te) == 0:
            continue
        Xtr, mean, std = standardize(X[tr])
        Xte, _, _ = standardize(X[te], mean, std)
        w = fit_ridge(Xtr, lab[tr], 1.0)
        accs.append(float(((predict(Xte, w) > 0.5) == (lab[te] > 0.5)).mean()))
    baseline = float(max(lab.mean(), 1.0 - lab.mean()))
    acc = float(np.mean(accs)) if accs else 0.0
    return {
        "cv_accuracy": acc,
        "majority_baseline": baseline,
        "margin": acc - baseline,
    }


def group_cv_accuracy(X: np.ndarray, lab: np.ndarray, groups: List[Any],
                      min_group: int = 100) -> Dict[str, float]:
    """Validacion honesta: se retiene el canvas entero, no muestras sueltas.

    Agrupa las muestras por tamano de canvas y evalua dejando fuera grupos
    completos. Asi el modelo no puede memorizar una plantilla concreta: se mide
    si la geometria generaliza a canvas que no vio.
    """
    bucket: Dict[Any, List[int]] = {}
    for i, g in enumerate(groups):
        bucket.setdefault(g, []).append(i)

    accs: List[float] = []
    for key, idxs in sorted(bucket.items(), key=lambda kv: -len(kv[1])):
        te = np.asarray(idxs)
        if len(te) < min_group:
            continue
        tr = np.setdiff1d(np.arange(len(lab)), te)
        if len(tr) < 100:
            continue
        Xtr, mean, std = standardize(X[tr])
        Xte, _, _ = standardize(X[te], mean, std)
        w = fit_ridge(Xtr, lab[tr], 1.0)
        accs.append(float(((predict(Xte, w) > 0.5) == (lab[te] > 0.5)).mean()))

    baseline = float(max(lab.mean(), 1.0 - lab.mean()))
    acc = float(np.mean(accs)) if accs else 0.0
    return {
        "group_cv_accuracy": acc,
        "groups_evaluated": len(accs),
        "majority_baseline": baseline,
        "margin": acc - baseline,
    }


def heuristic_score(rec: Dict[str, Any]) -> float:
    """Puntuacion sin entrenamiento: la compuesta de las metricas geometricas.

    Es la via utilizable hoy. Esta alineada con las restricciones que el
    evaluador verbaliza, no con las etiquetas ruidosas de este fichero.
    """
    layout = Layout.from_dict(rec["layout"])
    return evaluate(layout.elements, layout.canvas).composite()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", default=str(REPO_ROOT / "datasets" / "processed" / "feedback_train.jsonl"))
    ap.add_argument("--eval", default=str(REPO_ROOT / "datasets" / "processed" / "feedback_eval.jsonl"))
    ap.add_argument("--output", default=str(REPO_ROOT / "datasets" / "processed" / "reward_model.json"))
    ap.add_argument("--mode", choices=("gate", "train", "heuristic"), default="gate",
                    help="gate: verifica que hay senal y falla si no; "
                         "train: escribe la cabeza y sus metricas; "
                         "heuristic: solo puntua con las metricas geometricas")
    ap.add_argument("--alpha", type=float, default=1.0)
    args = ap.parse_args()

    train_path, eval_path = Path(args.train), Path(args.eval)
    for p in (train_path, eval_path):
        if not p.exists():
            print(f"falta {p}. Ejecuta antes prepare_feedback_dataset.py", file=sys.stderr)
            return 1

    if args.mode == "heuristic":
        scores = [heuristic_score(json.loads(l)) for l in train_path.open(encoding="utf-8")]
        print(f"puntuacion heuristica sobre {len(scores)} layouts: "
              f"mean={np.mean(scores):.4f} std={np.std(scores):.4f} "
              f"min={np.min(scores):.4f} max={np.max(scores):.4f}")
        return 0

    print(f"cargando {train_path.name} ...")
    Xtr_raw, _, ytr, grp_tr = load_split(train_path)
    print(f"cargando {eval_path.name} ...")
    Xev_raw, _, yev, _ = load_split(eval_path)
    print(f"train={Xtr_raw.shape} eval={Xev_raw.shape}")

    print("\n-- correlacion de cada metrica con el juicio humano --")
    for i, name in enumerate(FEATURE_NAMES):
        col = Xtr_raw[:, i]
        r = float(np.corrcoef(col, ytr)[0, 1]) if col.std() > 1e-9 else 0.0
        print(f"  {name:20s} {r:+.4f}")

    rand_cv = cross_val_accuracy(Xtr_raw, ytr)
    grp_cv = group_cv_accuracy(Xtr_raw, ytr, grp_tr)
    print("\n-- validacion cruzada sobre la etiqueta humana --")
    print(f"  aleatoria (5-fold)  exactitud {rand_cv['cv_accuracy']:.4f}  "
          f"margen {rand_cv['margin']:+.4f}   <- optimista, hay fuga de plantilla")
    print(f"  agrupada por canvas exactitud {grp_cv['group_cv_accuracy']:.4f}  "
          f"margen {grp_cv['margin']:+.4f}   <- la cifra honesta")
    print(f"  clase mayoritaria   {grp_cv['majority_baseline']:.4f}  "
          f"({grp_cv['groups_evaluated']} grupos evaluados)")

    Xtr, mean, std = standardize(Xtr_raw)
    Xev_e, _, _ = standardize(Xev_raw, mean, std)
    w = fit_ridge(Xtr, ytr, args.alpha)
    rep = regression_report(yev, predict(Xev_e, w))
    print("\n-- regresion sobre la recompensa registrada (softmax del reward) --")
    print(f"  rmse={rep['rmse']:.4f} r2={rep['r2']:.4f} pearson={rep['pearson']:.4f}")

    if args.mode == "gate":
        if grp_cv["margin"] < MIN_SIGNAL_MARGIN:
            print(
                f"\nSIN SENAL: el margen agrupado {grp_cv['margin']:+.4f} no supera "
                f"{MIN_SIGNAL_MARGIN}.\n"
                "Las metricas geometricas no generalizan a canvas que el modelo "
                "no vio. Solo la validacion aleatoria parece buena, y lo es por "
                "fuga de plantilla (un unico canvas de 513x750 es dos tercios "
                "del dataset).\n"
                "No se debe reportar un modelo entrenado. Ver docs/LIMITATIONS.md.\n"
                "Alternativa utilizable hoy: --mode heuristic (metricas "
                "geometricas, alineadas con las restricciones del evaluador).",
                file=sys.stderr,
            )
            return 2
        print(f"\nHay senal suficiente (margen agrupado {grp_cv['margin']:+.4f}).")
        return 0

    coefs = {name: round(float(c), 6) for name, c in zip(FEATURE_NAMES, w[1:])}
    model = {
        "kind": "ridge-reward-head",
        "trained_on": train_path.name,
        "evaluated_on": eval_path.name,
        "n_train": int(Xtr.shape[0]),
        "n_eval": int(Xev_raw.shape[0]),
        "alpha": args.alpha,
        "features": FEATURE_NAMES,
        "intercept": round(float(w[0]), 6),
        "coefficients": coefs,
        "standardization": {"mean": mean.tolist(), "std": std.tolist()},
        "regression": rep,
        "random_cv": rand_cv,
        "group_cv": grp_cv,
        "has_signal": bool(grp_cv["margin"] >= MIN_SIGNAL_MARGIN),
        "notes": (
            "NO USAR EN PRODUCCION si has_signal es false. Las metricas "
            "geometricas no generalizan entre tamanos de canvas; la validacion "
            "aleatoria sobreestima por fuga de plantilla. Usa las metricas de "
            "core/nresponsive/metrics.py. Ver docs/LIMITATIONS.md."
        ),
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nmodelo escrito en {out} (has_signal={model['has_signal']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())