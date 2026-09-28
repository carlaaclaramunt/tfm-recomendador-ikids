"""Curación documental: agrupación, fusión y trazabilidad de programas."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

from src.models import Programa


# ---------------------------------------------------------------------------
# 3. Agrupar candidatos equivalentes
# ---------------------------------------------------------------------------

def normalizar_texto(texto: Optional[str]) -> str:
    if not texto:
        return ""

    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


def similitud_texto(a: Optional[str], b: Optional[str]) -> float:
    a_norm = normalizar_texto(a)
    b_norm = normalizar_texto(b)

    if not a_norm or not b_norm:
        return 0.0

    return SequenceMatcher(None, a_norm, b_norm).ratio()


def son_equivalentes(p1: Programa, p2: Programa, umbral_nombre: float = 0.65) -> bool:
    """Decide si dos programas probablemente representan el mismo programa real."""

    misma_empresa = (
        normalizar_texto(p1.empresa_proveedora)
        == normalizar_texto(p2.empresa_proveedora)
    )

    mismo_pais = normalizar_texto(p1.pais) == normalizar_texto(p2.pais)

    misma_ciudad = (
        not p1.ciudad
        or not p2.ciudad
        or normalizar_texto(p1.ciudad) == normalizar_texto(p2.ciudad)
    )

    mismo_anyo = (
        not p1.anyo_documento
        or not p2.anyo_documento
        or p1.anyo_documento == p2.anyo_documento
    )

    nombre_parecido = similitud_texto(p1.nombre, p2.nombre) >= umbral_nombre

    return misma_empresa and mismo_pais and misma_ciudad and mismo_anyo and nombre_parecido


def agrupar_programas_equivalentes(programas: list[Programa]) -> list[list[Programa]]:
    """Agrupa programas que parecen equivalentes.

    Devuelve una lista de grupos. Cada grupo contiene uno o más programas.
    """

    grupos: list[list[Programa]] = []

    for programa in programas:
        asignado = False

        for grupo in grupos:
            representante = grupo[0]

            if son_equivalentes(representante, programa):
                grupo.append(programa)
                asignado = True
                break

        if not asignado:
            grupos.append([programa])

    return grupos


# ---------------------------------------------------------------------------
# 4. Fusionar campos con prioridad
# ---------------------------------------------------------------------------

def elegir_texto_mas_largo(*valores: Optional[str]) -> Optional[str]:
    valores_validos = [v for v in valores if v]
    if not valores_validos:
        return None
    return max(valores_validos, key=len)


def elegir_primer_no_nulo(*valores):
    for valor in valores:
        if valor is not None:
            return valor
    return None


def unir_listas_sin_duplicados(*listas: list) -> list:
    resultado = []

    for lista in listas:
        if not lista:
            continue

        for item in lista:
            if item not in resultado:
                resultado.append(item)

    return resultado


def elegir_estado_documento(estados: list[str]) -> str:
    if "obsoleto" in estados:
        return "obsoleto"

    if "parcialmente_obsoleto" in estados:
        return "parcialmente_obsoleto"

    return "vigente"


def fusionar_grupo_programas(grupo: list[Programa]) -> Programa:
    """Fusiona un grupo de programas equivalentes en un único Programa."""

    base = grupo[0]
    data = base.model_dump()

    # Identificación
    data["nombre"] = elegir_texto_mas_largo(*(p.nombre for p in grupo))
    data["empresa_proveedora"] = elegir_primer_no_nulo(
        *(p.empresa_proveedora for p in grupo)
    )

    # Ubicación
    data["pais"] = elegir_primer_no_nulo(*(p.pais for p in grupo))
    data["ciudad"] = elegir_primer_no_nulo(*(p.ciudad for p in grupo))

    # Idioma
    data["idioma"] = elegir_primer_no_nulo(*(p.idioma for p in grupo))

    # Edad: rango más amplio
    edades_min = [p.edad_min for p in grupo if p.edad_min is not None]
    edades_max = [p.edad_max for p in grupo if p.edad_max is not None]

    data["edad_min"] = min(edades_min) if edades_min else None
    data["edad_max"] = max(edades_max) if edades_max else None

    # Duración: rango más amplio
    duraciones_min = [p.duracion_min_dias for p in grupo if p.duracion_min_dias is not None]
    duraciones_max = [p.duracion_max_dias for p in grupo if p.duracion_max_dias is not None]

    data["duracion_min_dias"] = min(duraciones_min) if duraciones_min else None
    data["duracion_max_dias"] = max(duraciones_max) if duraciones_max else None

    # Precio: rango más amplio
    precios_min = [p.precio_semanal_min_eur for p in grupo if p.precio_semanal_min_eur is not None]
    precios_max = [p.precio_semanal_max_eur for p in grupo if p.precio_semanal_max_eur is not None]

    data["precio_semanal_min_eur"] = min(precios_min) if precios_min else None
    data["precio_semanal_max_eur"] = max(precios_max) if precios_max else None

    # Moneda y precio original
    data["moneda_origen"] = elegir_primer_no_nulo(*(p.moneda_origen for p in grupo))

    precios_min_origen = [
        p.precio_semanal_min_origen for p in grupo if p.precio_semanal_min_origen is not None
    ]
    precios_max_origen = [
        p.precio_semanal_max_origen for p in grupo if p.precio_semanal_max_origen is not None
    ]

    data["precio_semanal_min_origen"] = min(precios_min_origen) if precios_min_origen else None
    data["precio_semanal_max_origen"] = max(precios_max_origen) if precios_max_origen else None

    # Alojamiento
    alojamientos = []

    for p in grupo:
        valor = p.tipo_alojamiento

        if isinstance(valor, list):
            alojamientos.extend(valor)
        elif valor:
            alojamientos.append(valor)

    data["tipo_alojamiento"] = list(dict.fromkeys(alojamientos))

    # Fechas del programa
    data["fecha_inicio"] = elegir_primer_no_nulo(*(p.fecha_inicio for p in grupo))
    data["fecha_fin"] = elegir_primer_no_nulo(*(p.fecha_fin for p in grupo))

    # Vigencia documental, si tienes estos campos en Programa
    if "vigencia_inicio" in data:
        data["vigencia_inicio"] = elegir_primer_no_nulo(
            *(getattr(p, "vigencia_inicio", None) for p in grupo)
        )

    if "vigencia_fin" in data:
        data["vigencia_fin"] = elegir_primer_no_nulo(
            *(getattr(p, "vigencia_fin", None) for p in grupo)
        )

    # Acreditaciones
    data["acreditaciones"] = unir_listas_sin_duplicados(
        *(p.acreditaciones for p in grupo)
    )

    # Curación documental
    anyos = [p.anyo_documento for p in grupo if p.anyo_documento is not None]
    data["anyo_documento"] = max(anyos) if anyos else None

    data["estado_documento"] = elegir_estado_documento(
        [p.estado_documento for p in grupo]
    )

    data["campos_obsoletos"] = unir_listas_sin_duplicados(
        *(p.campos_obsoletos for p in grupo)
    )

    data["razon_obsolescencia"] = elegir_texto_mas_largo(
        *(p.razon_obsolescencia for p in grupo)
    )

    data["tipo_documento"] = elegir_tipo_documento_prioritario(grupo)

    # 5. Trazabilidad
    documentos = []

    for p in grupo:
        documentos.extend(p.documentos_fuente or [])

        if p.fuente_documento:
            documentos.append(p.fuente_documento)

    data["documentos_fuente"] = list(dict.fromkeys(documentos))

    if data["documentos_fuente"]:
        data["fuente_documento"] = data["documentos_fuente"][0]

    data["programa_key"] = generar_programa_key(data)

    partnerships = []

    for p in grupo:
        partnerships.extend(getattr(p, "partnerships", []) or [])

    data["partnerships"] = []
    vistos = set()

    for partnership in partnerships:
        if partnership.nombre.lower() not in vistos:
            data["partnerships"].append(partnership)
            vistos.add(partnership.nombre.lower())

    evidencias = []

    for p in grupo:
        evidencias.extend(getattr(p, "evidencias", []) or [])

    data["evidencias"] = []
    vistos = set()

    for evidencia in evidencias:
        clave = (evidencia.campo, evidencia.valor, evidencia.documento_fuente)

        if clave not in vistos:
            data["evidencias"].append(evidencia)
            vistos.add(clave)

    costes = []

    for p in grupo:
        costes.extend(getattr(p, "costes_adicionales", []) or [])

    data["costes_adicionales"] = []
    vistos_costes = set()

    for coste in costes:
        clave = (
            coste.concepto.lower(),
            coste.tipo,
            coste.importe,
            coste.moneda,
        )

        if clave not in vistos_costes:
            data["costes_adicionales"].append(coste)
            vistos_costes.add(clave)

    # LD5 — fechas recurrentes: preservamos el texto más informativo
    # entre los del grupo.
    data["fechas_inicio_recurrentes"] = elegir_texto_mas_largo(
        *(getattr(p, "fechas_inicio_recurrentes", None) for p in grupo)
    )

    # LD19 — turnos: unión sin duplicados por fecha_inicio.
    turnos = []
    for p in grupo:
        turnos.extend(getattr(p, "turnos", []) or [])
    data["turnos"] = []
    vistos_turnos: set = set()
    for turno in turnos:
        clave = (turno.fecha_inicio, turno.fecha_fin)
        if clave not in vistos_turnos:
            data["turnos"].append(turno)
            vistos_turnos.add(clave)
    # Ordenamos por fecha_inicio para reproducibilidad
    data["turnos"].sort(key=lambda t: t.fecha_inicio)

    # LD20 — cursos especialistas: unión sin duplicados (por nombre+actividad),
    # preservando el ejemplar con más datos (horas o partnership rellenos).
    especialistas = []
    for p in grupo:
        especialistas.extend(getattr(p, "cursos_especialistas", []) or [])

    data["cursos_especialistas"] = []
    vistos_esp: dict[tuple, object] = {}
    for esp in especialistas:
        clave = (esp.nombre.lower().strip(), esp.actividad.lower().strip())
        actual = vistos_esp.get(clave)
        # preferimos el que tenga más campos rellenos
        if actual is None or _cuenta_campos_no_nulos(esp) > _cuenta_campos_no_nulos(actual):
            vistos_esp[clave] = esp

    data["cursos_especialistas"] = list(vistos_esp.values())

    return Programa(**data)


def _cuenta_campos_no_nulos(esp) -> int:
    """Cuenta cuántos campos opcionales rellenos tiene un CursoEspecialista."""
    return sum(
        1 for v in (
            getattr(esp, "horas_dedicadas", None),
            getattr(esp, "partnership", None),
            getattr(esp, "descripcion", None),
        ) if v is not None
    )


def elegir_tipo_documento_prioritario(grupo: list[Programa]) -> str:
    """Prioriza el tipo de documento más útil para representar el programa."""

    prioridad = {
        "ficha_programa": 5,
        "folleto_cliente_final": 4,
        "lista_precios": 3,
        "tarifa_b2b": 2,
        "otro": 1,
    }

    tipos = [p.tipo_documento for p in grupo]

    return max(tipos, key=lambda t: prioridad.get(t, 0))


def generar_programa_key(data: dict) -> str:
    partes = [
        normalizar_texto(data.get("empresa_proveedora")),
        normalizar_texto(data.get("pais")),
        normalizar_texto(data.get("ciudad")),
        normalizar_texto(data.get("nombre")),
        str(data.get("anyo_documento") or ""),
    ]

    return "|".join(p for p in partes if p)


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def fusionar_programas(programas: list[Programa]) -> list[Programa]:
    """Agrupa y fusiona programas equivalentes."""

    grupos = agrupar_programas_equivalentes(programas)

    programas_fusionados = [
        fusionar_grupo_programas(grupo)
        for grupo in grupos
    ]

    return programas_fusionados


def resumen_fusion(
    programas_originales: list[Programa],
    programas_fusionados: list[Programa],
) -> dict[str, int]:
    return {
        "programas_originales": len(programas_originales),
        "programas_fusionados": len(programas_fusionados),
        "programas_unificados": len(programas_originales) - len(programas_fusionados),
    }