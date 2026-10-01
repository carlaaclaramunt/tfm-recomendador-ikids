"""Genera el dossier de recomendaciones para la sesión H3 con I-KIDS.

Ejecuta el sistema real sobre los tres perfiles sintéticos (P1 adolescente
deportivo, P2 adulto inmersión premium, P3 docente CLIL) y empaqueta las
recomendaciones top-3 con su descomposición MCDM y la explicación textual
en un PDF listo para imprimir y repartir al equipo asesor.

Uso:
    python scripts/preparar_dossier_h3.py

Produce:
    informes/dossier_h3.pdf
    informes/dossier_h3.md   (fuente Markdown versionable)
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import markdown
import weasyprint

from src.application.construir_catalogo import construir_catalogo
from src.application.recomendar import recomendar
from src.models import PerfilCliente


# ---------------------------------------------------------------------------
# Perfiles del dossier (mismos tres que menciona el cuestionario H3)
# ---------------------------------------------------------------------------

PERFILES_DOSSIER = [
    {
        "id": "P1",
        "titulo": "Adolescente deportivo",
        "descripcion": (
            "Chico de 14 años con interés declarado en football, "
            "presupuesto 8.000 €, duración 21 a 35 días, "
            "alojamiento en residencia."
        ),
        "perfil": PerfilCliente(
            idioma_deseado="inglés",
            edad_estudiante=14,
            presupuesto_max_eur=8000.0,
            duracion_min_dias=21,
            duracion_max_dias=35,
            tipo_alojamiento_preferido="residencia",
            intereses=["football", "soccer"],
            pesos={
                "precio": 0.15,
                "duracion": 0.15,
                "ubicacion": 0.10,
                "alojamiento": 0.15,
                "edad_ajuste": 0.15,
                "afinidad": 0.30,
            },
        ),
    },
    {
        "id": "P2",
        "titulo": "Adulto inmersión premium",
        "descripcion": (
            "Adulto de 26 años, presupuesto 6.000 €, duración 7 a 14 días, "
            "alojamiento en familia, intereses declarados de inmersión "
            "intensiva y clases privadas."
        ),
        "perfil": PerfilCliente(
            idioma_deseado="inglés",
            edad_estudiante=26,
            presupuesto_max_eur=6000.0,
            duracion_min_dias=7,
            duracion_max_dias=14,
            tipo_alojamiento_preferido="familia",
            intereses=["immersion", "intensive", "private"],
            pesos={
                "precio": 0.20,
                "duracion": 0.15,
                "ubicacion": 0.10,
                "alojamiento": 0.15,
                "edad_ajuste": 0.10,
                "afinidad": 0.30,
            },
        ),
    },
    {
        "id": "P3",
        "titulo": "Docente CLIL",
        "descripcion": (
            "Docente de 35 años, presupuesto 2.500 €, duración 7 a 14 días, "
            "alojamiento en familia, intereses en formación de profesorado CLIL."
        ),
        "perfil": PerfilCliente(
            idioma_deseado="inglés",
            edad_estudiante=35,
            presupuesto_max_eur=2500.0,
            duracion_min_dias=7,
            duracion_max_dias=14,
            tipo_alojamiento_preferido="familia",
            intereses=["clil", "teacher training"],
            pesos={
                "precio": 0.25,
                "duracion": 0.15,
                "ubicacion": 0.10,
                "alojamiento": 0.15,
                "edad_ajuste": 0.05,
                "afinidad": 0.30,
            },
        ),
    },
]


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def _formatear_perfil(bloque: dict) -> str:
    p = bloque["perfil"]
    campos = [
        ("Idioma deseado", p.idioma_deseado),
        ("Edad del estudiante", f"{p.edad_estudiante} años"),
        ("Presupuesto máximo", f"{p.presupuesto_max_eur:.0f} €"),
        (
            "Duración",
            f"{p.duracion_min_dias}–{p.duracion_max_dias} días",
        ),
        ("Alojamiento preferido", p.tipo_alojamiento_preferido or "sin preferencia"),
        ("Intereses declarados", ", ".join(p.intereses) if p.intereses else "—"),
    ]
    filas = "\n".join(f"| **{k}** | {v} |" for k, v in campos)
    return (
        f"**Descripción resumida.** {bloque['descripcion']}\n\n"
        f"| Campo | Valor |\n|---|---|\n{filas}\n"
    )


def _formatear_descomposicion(descomposicion: dict) -> str:
    filas = "\n".join(
        f"| {k.capitalize()} | {v:.2f} |"
        for k, v in descomposicion.items()
    )
    return f"| Criterio | Score |\n|---|---|\n{filas}\n"


def _formatear_recomendacion(idx: int, rec, perfil: PerfilCliente) -> str:
    p = rec.programa
    bloque = f"### Recomendación #{idx} · {p.nombre}\n\n"
    bloque += f"**Puntuación global:** {rec.puntuacion:.2f}\n\n"
    bloque += f"**Proveedor:** {p.empresa_proveedora}  \n"
    bloque += f"**Destino:** {p.ciudad or '—'}, {p.pais}  \n"
    bloque += f"**Idioma:** {p.idioma}  \n"
    if p.edad_min is not None or p.edad_max is not None:
        bloque += f"**Rango de edad:** {p.edad_min or '—'}–{p.edad_max or '—'}  \n"
    if p.duracion_min_dias is not None or p.duracion_max_dias is not None:
        bloque += (
            f"**Duración:** {p.duracion_min_dias or '—'}–"
            f"{p.duracion_max_dias or '—'} días  \n"
        )
    if p.precio_semanal_min_eur is not None or p.precio_semanal_max_eur is not None:
        bloque += (
            f"**Precio semanal:** "
            f"{p.precio_semanal_min_eur or '—':.0f}–"
            f"{p.precio_semanal_max_eur or '—':.0f} €  \n"
        )
    if p.tipo_alojamiento:
        bloque += f"**Alojamiento ofertado:** {', '.join(p.tipo_alojamiento)}  \n"
    if p.acreditaciones:
        bloque += f"**Acreditaciones:** {', '.join(p.acreditaciones)}  \n"
    if p.fuente_documento:
        bloque += f"**Documento fuente:** `{Path(p.fuente_documento).name}`  \n"
    bloque += "\n**Descomposición MCDM:**\n\n"
    bloque += _formatear_descomposicion(rec.descomposicion)
    bloque += "\n**Explicación generada por el sistema:**\n\n"
    bloque += f"> {rec.explicacion or '_(sin explicación)_'}\n\n"
    bloque += "---\n"
    return bloque


def _construir_markdown(programas) -> str:
    hoy = date.today().strftime("%d de %B de %Y")
    md = [
        "# Dossier de recomendaciones — Validación H3",
        "",
        "**TFM · Recomendador de programas de inmersión lingüística para I-KIDS**  ",
        f"**Fecha de generación:** {hoy}  ",
        "**Catálogo evaluado:** 15 programas (iteración 23, trazabilidad verificable activa)",
        "",
        "---",
        "",
        "## Instrucciones para el respondiente",
        "",
        "Este dossier acompaña al cuestionario de validación H3. Contiene **tres recomendaciones ejemplo** producidas por el sistema real sobre tres perfiles sintéticos de cliente contrastados en interés, presupuesto y edad.",
        "",
        "Para cada perfil se muestra:",
        "",
        "- La descripción del cliente.",
        "- Las **tres mejores recomendaciones** calculadas por el sistema, con su puntuación global, descomposición por criterio MCDM y explicación en lenguaje natural.",
        "",
        "Tu tarea es leer cada bloque y responder las siete preguntas Likert del cuestionario adjunto, pensando en la calidad **comunicativa** de las explicaciones, no en la corrección exacta de cada recomendación.",
        "",
        "---",
        "",
    ]

    for bloque in PERFILES_DOSSIER:
        md.append(f"## Perfil {bloque['id']} — {bloque['titulo']}")
        md.append("")
        md.append(_formatear_perfil(bloque))
        md.append("")
        md.append("### Recomendaciones del sistema")
        md.append("")
        recomendaciones = recomendar(bloque["perfil"], programas, top_k=3)
        if not recomendaciones:
            md.append(
                "> ⚠ El sistema no ha devuelto recomendaciones para este perfil. "
                "Posiblemente ningún programa del catálogo pasa las restricciones duras."
            )
        else:
            for i, rec in enumerate(recomendaciones, start=1):
                md.append(_formatear_recomendacion(i, rec, bloque["perfil"]))
        md.append("")

    md.append("---")
    md.append("")
    md.append(
        "*Fin del dossier. Procede ahora a cumplimentar el cuestionario de "
        "validación H3 adjunto.*"
    )
    return "\n".join(md)


_CSS = """
@page { size: A4; margin: 2.0cm 1.8cm; }
body { font-family: Georgia, serif; font-size: 10.5pt; line-height: 1.45; color: #222; }
h1 { color: #1b3a5c; font-size: 20pt; margin-bottom: 0.3em; }
h2 { color: #1b3a5c; font-size: 15pt; margin-top: 1.4em; border-bottom: 1px solid #ccc; padding-bottom: 0.2em; }
h3 { color: #2a5078; font-size: 12pt; margin-top: 1em; }
table { border-collapse: collapse; width: 100%; margin: 0.6em 0; font-size: 9.5pt; }
th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: left; }
th { background: #eef2f6; }
blockquote { border-left: 3px solid #2a5078; margin: 0.6em 0; padding: 0.3em 0.9em; background: #f6f8fa; font-style: italic; }
code { background: #eef2f6; padding: 1px 4px; border-radius: 3px; font-size: 9.5pt; }
hr { border: 0; border-top: 1px solid #ddd; margin: 1.4em 0; }
"""


def main() -> None:
    print("Cargando catálogo…")
    programas = construir_catalogo(reextraer=False)
    print(f"  → {len(programas)} programas en catálogo")

    print("Generando Markdown…")
    md = _construir_markdown(programas)

    out_md = ROOT / "informes" / "dossier_h3.md"
    out_pdf = ROOT / "informes" / "dossier_h3.pdf"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")
    print(f"  → {out_md.relative_to(ROOT)}")

    print("Renderizando PDF…")
    html = markdown.markdown(md, extensions=["tables", "extra"])
    html_doc = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Dossier H3</title>"
        f"<style>{_CSS}</style></head><body>{html}</body></html>"
    )
    weasyprint.HTML(string=html_doc).write_pdf(str(out_pdf))
    print(f"  → {out_pdf.relative_to(ROOT)}")
    print()
    print("Dossier listo. Imprime el PDF y repártelo junto al cuestionario.")


if __name__ == "__main__":
    main()
