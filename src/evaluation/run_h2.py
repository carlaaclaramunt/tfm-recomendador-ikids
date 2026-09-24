"""CLI: evaluación H2 (calidad del ranking del recomendador).

Compara el ranking del sistema MCDM contra dos baselines naïve
(ordenación aleatoria con semilla fija y ordenación por precio semanal
ascendente) usando el baseline manual como ground truth de relevancia.

Métricas reportadas (macro sobre perfiles):
    - Precision@5
    - nDCG@10

Contraste estadístico:
    - Test de Wilcoxon (rangos con signo) del sistema frente a cada
      baseline, para cada métrica, sobre las series de valores por perfil.

Uso:
    python -m src.evaluation.run_h2
    python -m src.evaluation.run_h2 --etiqueta iteracion13
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date
from pathlib import Path

from scipy import stats

from src.evaluation.ranking_metrics import (
    macro_promedio,
    ndcg_at_k,
    precision_at_k,
)
from src.models import PerfilCliente, Programa
from src.recommendation import filtrar_candidatos, puntuar_candidatos


ROOT = Path(__file__).resolve().parents[2]
CATALOGO_PATH = ROOT / "data" / "processed" / "programas.json"
PERFILES_PATH = ROOT / "data" / "eval" / "perfiles_evaluacion.json"
BASELINE_PATH = ROOT / "data" / "eval" / "baseline_manual.json"
RESULTADOS_DIR = ROOT / "data" / "eval" / "resultados"

SEMILLA_ALEATORIA = 42
K_PRECISION = 5
K_NDCG = 10


# ---------------------------------------------------------------------------
# Rankeadores
# ---------------------------------------------------------------------------


def ranking_sistema(perfil: PerfilCliente, catalogo: list[Programa]) -> list[str]:
    """Ranking del sistema MCDM sobre el subconjunto de candidatos filtrados."""
    candidatos = filtrar_candidatos(perfil, catalogo)
    if not candidatos:
        return []
    rec = puntuar_candidatos(perfil, candidatos)
    return [r.programa.nombre for r in rec]


def ranking_random(perfil: PerfilCliente, catalogo: list[Programa]) -> list[str]:
    """Baseline aleatorio con semilla fija por perfil (reproducible)."""
    candidatos = filtrar_candidatos(perfil, catalogo)
    nombres = [c.nombre for c in candidatos]
    rng = random.Random(SEMILLA_ALEATORIA + hash(perfil.edad_estudiante))
    rng.shuffle(nombres)
    return nombres


def ranking_precio_ascendente(perfil: PerfilCliente, catalogo: list[Programa]) -> list[str]:
    """Baseline naïve: orden por precio semanal ascendente. Los null van al final."""
    candidatos = filtrar_candidatos(perfil, catalogo)

    def clave(p: Programa) -> tuple[int, float]:
        pmin = p.precio_semanal_min_eur
        if pmin is None:
            return (1, 0.0)
        return (0, pmin)

    ordenado = sorted(candidatos, key=clave)
    return [c.nombre for c in ordenado]


RANKEADORES = {
    "sistema_mcdm": ranking_sistema,
    "baseline_random": ranking_random,
    "baseline_precio_asc": ranking_precio_ascendente,
}


# ---------------------------------------------------------------------------
# Evaluación
# ---------------------------------------------------------------------------


def evaluar_rankeador(
    ranker,
    perfiles: list[dict],
    baseline_por_perfil: dict[str, list[str]],
    catalogo: list[Programa],
) -> dict:
    """Aplica un rankeador a todos los perfiles y devuelve las series y macros."""
    p_at_5: list[float] = []
    ndcg_10: list[float] = []
    por_perfil = []

    for entrada in perfiles:
        perfil = PerfilCliente(**entrada["perfil"])
        ranking = ranker(perfil, catalogo)
        gt = baseline_por_perfil.get(entrada["id"], [])
        p5 = precision_at_k(ranking, gt, k=K_PRECISION)
        nd10 = ndcg_at_k(ranking, gt, k=K_NDCG)
        p_at_5.append(p5)
        ndcg_10.append(nd10)
        por_perfil.append(
            {
                "perfil_id": entrada["id"],
                "n_candidatos": len(ranking),
                "ranking_top5": ranking[:5],
                "precision_at_5": round(p5, 4),
                "ndcg_at_10": round(nd10, 4),
            }
        )

    return {
        "por_perfil": por_perfil,
        "precision_at_5_serie": p_at_5,
        "ndcg_at_10_serie": ndcg_10,
        "precision_at_5_macro": round(macro_promedio(p_at_5), 4),
        "ndcg_at_10_macro": round(macro_promedio(ndcg_10), 4),
    }


def wilcoxon_seguro(serie_a: list[float], serie_b: list[float]) -> tuple[float | None, float | None]:
    """Wilcoxon signed-rank con manejo del caso todas-diferencias-cero."""
    diffs = [a - b for a, b in zip(serie_a, serie_b)]
    if all(d == 0 for d in diffs):
        return None, None
    try:
        stat, p = stats.wilcoxon(serie_a, serie_b, zero_method="wilcox", alternative="greater")
        return round(float(stat), 4), round(float(p), 6)
    except ValueError:
        return None, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluación H2: ranking del recomendador.")
    parser.add_argument("--catalogo", type=Path, default=CATALOGO_PATH)
    parser.add_argument("--perfiles", type=Path, default=PERFILES_PATH)
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument("--etiqueta", type=str, default=None)
    parser.add_argument("--salida-dir", type=Path, default=RESULTADOS_DIR)
    args = parser.parse_args()

    catalogo = [Programa.model_validate(p) for p in json.loads(args.catalogo.read_text(encoding="utf-8"))]
    perfiles_doc = json.loads(args.perfiles.read_text(encoding="utf-8"))
    baseline_doc = json.loads(args.baseline.read_text(encoding="utf-8"))

    baseline_por_perfil = {
        entrada["perfil_id"]: entrada["top5"]
        for entrada in baseline_doc["baseline_por_perfil"]
    }

    resultados = {
        nombre: evaluar_rankeador(fn, perfiles_doc["perfiles"], baseline_por_perfil, catalogo)
        for nombre, fn in RANKEADORES.items()
    }

    # Comparaciones estadísticas: sistema vs cada baseline
    comparaciones = {}
    ref = resultados["sistema_mcdm"]
    for otro_nombre in ("baseline_random", "baseline_precio_asc"):
        otro = resultados[otro_nombre]
        s_p5, p_p5 = wilcoxon_seguro(ref["precision_at_5_serie"], otro["precision_at_5_serie"])
        s_nd, p_nd = wilcoxon_seguro(ref["ndcg_at_10_serie"], otro["ndcg_at_10_serie"])
        comparaciones[f"sistema_vs_{otro_nombre}"] = {
            "wilcoxon_precision_at_5": {"stat": s_p5, "p_value": p_p5},
            "wilcoxon_ndcg_at_10": {"stat": s_nd, "p_value": p_nd},
        }

    _imprimir_informe(resultados, comparaciones)
    salida = _guardar_resultado(resultados, comparaciones, args.salida_dir, args.etiqueta)
    print(f"\nResultado guardado en: {salida.relative_to(ROOT)}")


def _imprimir_informe(resultados: dict, comparaciones: dict) -> None:
    print("=" * 78)
    print("EVALUACIÓN H2 — Calidad del ranking del recomendador")
    print("=" * 78)
    print(f"\n{'Rankeador':<24} {'Precision@5 macro':>20} {'nDCG@10 macro':>18}")
    print("-" * 78)
    for nombre, res in resultados.items():
        print(f"{nombre:<24} {res['precision_at_5_macro']:>20.4f} {res['ndcg_at_10_macro']:>18.4f}")

    print("\nContraste estadístico (Wilcoxon signed-rank, alternativa 'greater'):")
    for clave, comp in comparaciones.items():
        p5 = comp["wilcoxon_precision_at_5"]
        nd = comp["wilcoxon_ndcg_at_10"]
        print(f"\n  {clave}")
        print(f"    Precision@5: stat={p5['stat']}, p-value={p5['p_value']}")
        print(f"    nDCG@10:     stat={nd['stat']}, p-value={nd['p_value']}")

    print(f"\nUmbral OE3: p-value < 0.05 en Wilcoxon frente a la selección manual")


def _guardar_resultado(resultados: dict, comparaciones: dict, salida_dir: Path, etiqueta: str | None) -> Path:
    salida_dir.mkdir(parents=True, exist_ok=True)
    hoy = date.today().isoformat()
    nombre = f"h2_{hoy}" + (f"_{etiqueta}" if etiqueta else "") + ".json"
    salida = salida_dir / nombre
    # Convertir series (list) manteniendo redondeo
    for r in resultados.values():
        r["precision_at_5_serie"] = [round(v, 4) for v in r["precision_at_5_serie"]]
        r["ndcg_at_10_serie"] = [round(v, 4) for v in r["ndcg_at_10_serie"]]
    payload = {
        "fecha": date.today().isoformat(),
        "etiqueta": etiqueta,
        "resultados_por_rankeador": resultados,
        "comparaciones_wilcoxon": comparaciones,
    }
    salida.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return salida


if __name__ == "__main__":
    main()
