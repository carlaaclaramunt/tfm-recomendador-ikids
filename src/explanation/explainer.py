"""Generador de explicaciones trazables.

A partir de una recomendación (programa + puntuación + descomposición por
criterio) produce un texto en lenguaje natural que indica al asesor qué
criterios y qué fragmentos del documento justifican la selección.

La explicación se construye **a partir de los datos del propio sistema**,
sin pasar por un modelo generativo. De esta forma se garantiza la fidelidad
de la explicación al razonamiento real del recomendador.
"""

from __future__ import annotations

from src.models import PerfilCliente, Programa, Recomendacion


# Umbral por encima del cual un criterio se considera "fuerte" en la explicación.
UMBRAL_CRITERIO_FUERTE = 0.7


def explicar(recomendacion: Recomendacion, perfil: PerfilCliente) -> str:
    """Genera el texto de la explicación trazable.

    Args:
        recomendacion: Recomendación con su descomposición de puntuación.
        perfil: Perfil del cliente.

    Returns:
        Cadena con la explicación lista para mostrar al asesor.
    """
    programa = recomendacion.programa
    motivos: list[str] = []

    motivos.extend(_motivos_filtros(programa, perfil))
    motivos.extend(_motivos_criterios_fuertes(recomendacion, perfil))

    encabezado = (
        f"El programa «{programa.nombre}» de {programa.empresa_proveedora} "
        f"obtiene una puntuación de {recomendacion.puntuacion:.2f}."
    )

    if motivos:
        cuerpo = "Se recomienda porque " + "; ".join(motivos) + "."
    else:
        cuerpo = (
            "No destaca especialmente en ningún criterio individual, pero "
            "cumple las restricciones planteadas por el cliente."
        )

    fuente = f"Información extraída del documento: {programa.fuente_documento}."

    return "\n".join([encabezado, cuerpo, fuente])


# ---------------------------------------------------------------------------
# Construcción de los motivos
# ---------------------------------------------------------------------------


def _motivos_filtros(programa: Programa, perfil: PerfilCliente) -> list[str]:
    """Motivos derivados del cumplimiento de las restricciones duras."""
    motivos: list[str] = []
    motivos.append(f"el idioma coincide con el deseado ({perfil.idioma_deseado})")

    if programa.edad_min is not None and programa.edad_max is not None:
        motivos.append(
            f"la edad del estudiante ({perfil.edad_estudiante} años) "
            f"está dentro del rango admitido ({programa.edad_min}-{programa.edad_max})"
        )

    if (
            perfil.presupuesto_max_eur is not None
            and programa.precio_min_eur is not None
    ):
        if (
                programa.precio_max_eur is not None
                and programa.precio_max_eur != programa.precio_min_eur
        ):
            motivos.append(
                f"el precio (entre {programa.precio_min_eur:.0f}€ y "
                f"{programa.precio_max_eur:.0f}€) se ajusta al presupuesto "
                f"({perfil.presupuesto_max_eur:.0f}€)"
            )
        else:
            motivos.append(
                f"el precio ({programa.precio_min_eur:.0f}€) "
                f"está dentro del presupuesto ({perfil.presupuesto_max_eur:.0f}€)"
            )

    return motivos


def _motivos_criterios_fuertes(
    recomendacion: Recomendacion,
    perfil: PerfilCliente,
) -> list[str]:
    """Motivos derivados de los criterios MCDM con puntuación alta."""
    programa = recomendacion.programa
    motivos: list[str] = []

    for criterio, puntuacion in recomendacion.descomposicion.items():
        if puntuacion < UMBRAL_CRITERIO_FUERTE:
            continue

        if criterio == "ubicacion" and perfil.pais_preferido:
            motivos.append(
                f"el destino ({programa.pais}) coincide con el país preferido "
                f"({perfil.pais_preferido})"
            )
        elif criterio == "alojamiento" and perfil.tipo_alojamiento_preferido:
            motivos.append(
                f"el tipo de alojamiento ({programa.tipo_alojamiento}) "
                f"coincide con la preferencia del cliente"
            )
        elif criterio == "precio":
            motivos.append("el precio es competitivo respecto a las alternativas")
        elif criterio == "duracion" and (
                    programa.duracion_min_dias or programa.duracion_max_dias):
            dmin = programa.duracion_min_dias
            dmax = programa.duracion_max_dias
            if dmin == dmax or dmax is None:
                motivos.append(f"la duración ({dmin} días) se ajusta al rango deseado")
            elif dmin is None:
                motivos.append(f"la duración (hasta {dmax} días) se ajusta al rango deseado")
            else:
                motivos.append(f"la duración ({dmin}-{dmax} días) se ajusta al rango deseado")
        elif criterio == "edad_ajuste":
            motivos.append("el rango de edad del programa encaja muy bien con el estudiante")

    return motivos