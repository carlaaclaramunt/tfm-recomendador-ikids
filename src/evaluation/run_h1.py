"""CLI: evaluación H1 (precisión de la extracción).

Carga el catálogo extraído (data/processed/programas.json) y el ground truth
(data/eval/ground_truth.json), calcula precision/recall/F1 por campo y F1 macro,
imprime un informe legible y persiste el resultado en
data/eval/resultados/h1_<fecha>.json.

Uso:
    python -m src.evaluation.run_h1
    python -m src.evaluation.run_h1 --catalogo data/processed/programas.json
    python -m src.evaluation.run_h1 --etiqueta iteracion7
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from src.evaluation.extraction_metrics import evaluar_extraccion


ROOT = Path(__file__).resolve().parents[2]
GT_PATH = ROOT / "data" / "eval" / "ground_truth.json"
CATALOGO_PATH = ROOT / "data" / "processed" / "programas.json"
RESULTADOS_DIR = ROOT / "data" / "eval" / "resultados"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluación H1: extracción de información.")
    parser.add_argument("--catalogo", type=Path, default=CATALOGO_PATH)
    parser.add_argument("--gt", type=Path, default=GT_PATH)
    parser.add_argument(
        "--etiqueta",
        type=str,
        default=None,
        help="Etiqueta corta para identificar el run (ej: 'iteracion7'). Se añade al fichero de salida.",
    )
    parser.add_argument(
        "--salida-dir",
        type=Path,
        default=RESULTADOS_DIR,
        help="Directorio donde se persiste el resultado.",
    )
    args = parser.parse_args()

    gt = json.loads(args.gt.read_text(encoding="utf-8"))
    programas = json.loads(args.catalogo.read_text(encoding="utf-8"))

    resultado = evaluar_extraccion(gt, programas)

    _imprimir_informe(resultado)
    salida = _guardar_resultado(resultado, args.salida_dir, args.etiqueta)
    print(f"\nResultado guardado en: {salida.relative_to(ROOT)}")


def _imprimir_informe(resultado) -> None:
    print("=" * 70)
    print("EVALUACIÓN H1 — Precisión de extracción")
    print("=" * 70)
    print(f"GT versión:          {resultado.version_gt}")
    print(f"Programas GT:        {resultado.n_programas_gt}")
    print(f"Emparejados:         {resultado.n_programas_emparejados}")
    if resultado.programas_sin_match:
        print(f"Sin match:           {', '.join(resultado.programas_sin_match)}")
    print(
        f"\n{'CAMPO':<28} {'TP':>4} {'FP':>4} {'FN':>4} {'TN':>4}  "
        f"{'P':>6} {'R':>6} {'F1':>6}"
    )
    print("-" * 70)
    for nombre, r in resultado.por_campo.items():
        p = _fmt(r.precision)
        rec = _fmt(r.recall)
        f1 = _fmt(r.f1)
        print(
            f"{nombre:<28} {r.tp:>4} {r.fp:>4} {r.fn:>4} {r.tn:>4}  "
            f"{p:>6} {rec:>6} {f1:>6}"
        )
    print("-" * 70)
    macro_str = _fmt(resultado.macro_f1)
    print(f"{'F1 MACRO':<28} {'':>4} {'':>4} {'':>4} {'':>4}  {'':>6} {'':>6} {macro_str:>6}")
    print(f"\nUmbral OE2: F1 macro ≥ 0,85")
    if resultado.macro_f1 is not None:
        cumple = "✓ cumple" if resultado.macro_f1 >= 0.85 else "✗ por debajo"
        print(f"Estado:     {cumple}")


def _fmt(x) -> str:
    return f"{x:.3f}" if x is not None else "n/a"


def _guardar_resultado(resultado, salida_dir: Path, etiqueta: str | None) -> Path:
    salida_dir.mkdir(parents=True, exist_ok=True)
    hoy = date.today().isoformat()
    nombre = f"h1_{hoy}" + (f"_{etiqueta}" if etiqueta else "") + ".json"
    salida = salida_dir / nombre
    salida.write_text(
        json.dumps(resultado.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return salida


if __name__ == "__main__":
    main()
