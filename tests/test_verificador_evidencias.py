"""Tests del verificador de evidencias (trazabilidad verificable, LD24)."""

from src.curation.evidence import (
    UMBRAL_DERIVADO,
    generar_evidencias,
    tasa_trazabilidad_literal,
    verificar_evidencias,
)
from src.models import EvidenciaCampo, Programa


def _programa_con_evidencias(evidencias: list[EvidenciaCampo]) -> Programa:
    return Programa(
        nombre="Test Program",
        empresa_proveedora="Test",
        pais="Test",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
        evidencias=evidencias,
    )


# ---------------------------------------------------------------------------
# Verificación exacta y aproximada
# ---------------------------------------------------------------------------


def test_cita_literal_se_marca_como_literal():
    texto = "The programme runs for Age: 13-17 · £950 per week from 07/04."
    programa = _programa_con_evidencias(
        [
            EvidenciaCampo(
                campo="precio_semanal_min_eur",
                valor="1112",
                fragmento_fuente="£950 per week",
                fidelidad="literal",
            )
        ]
    )

    verificado = verificar_evidencias(programa, texto)
    assert verificado.evidencias[0].fidelidad == "literal"


def test_cita_inexistente_se_marca_como_no_verificable():
    texto = "Este programa cuesta 1200 euros por semana."
    programa = _programa_con_evidencias(
        [
            EvidenciaCampo(
                campo="precio_semanal_min_eur",
                valor="1500",
                fragmento_fuente="£950 per week",
                fidelidad="literal",
            )
        ]
    )

    verificado = verificar_evidencias(programa, texto)
    assert verificado.evidencias[0].fidelidad == "no_verificable"


def test_cita_con_espaciado_alterado_se_marca_como_derivado():
    # Texto real con doble espaciado, común tras extracción de PDF
    texto = "Standard tuition:  £950  per  week  including materials."
    programa = _programa_con_evidencias(
        [
            EvidenciaCampo(
                campo="precio_semanal_min_eur",
                valor="1112",
                fragmento_fuente="£950 per week",
                fidelidad="literal",
            )
        ]
    )

    # La normalización colapsa espacios → matchea literal
    verificado = verificar_evidencias(programa, texto)
    assert verificado.evidencias[0].fidelidad == "literal"


def test_cita_con_error_ocr_pero_muy_similar_se_marca_derivado():
    # Simula un error OCR de un dígito por otro dentro de un fragmento largo:
    # el precio real es 950 pero el OCR lo capturó como 95O (letra O).
    # La cita del LLM (con el dígito correcto) no aparece literal pero la
    # ventana del texto es muy parecida.
    texto = (
        "Programme summary. Standard tuition is £95O per week including all "
        "the course materials, insurance and airport transfer from the school office."
    )
    cita = "Standard tuition is £950 per week including all the course materials"
    programa = _programa_con_evidencias(
        [
            EvidenciaCampo(
                campo="precio_semanal_min_eur",
                valor="1112",
                fragmento_fuente=cita,
                fidelidad="literal",
            )
        ]
    )

    verificado = verificar_evidencias(programa, texto)
    assert verificado.evidencias[0].fidelidad == "derivado"


def test_cita_vacia_se_marca_como_no_verificable():
    programa = _programa_con_evidencias(
        [
            EvidenciaCampo(
                campo="edad_min",
                valor="13",
                fragmento_fuente="",
                fidelidad="literal",
            )
        ]
    )

    verificado = verificar_evidencias(programa, "cualquier texto")
    assert verificado.evidencias[0].fidelidad == "no_verificable"


def test_fidelidad_inferido_se_preserva_si_cita_aparece():
    texto = "This programme is open to all ages including families."
    programa = _programa_con_evidencias(
        [
            EvidenciaCampo(
                campo="edad_min",
                valor="0",
                fragmento_fuente="all ages",
                fidelidad="inferido",
            )
        ]
    )

    verificado = verificar_evidencias(programa, texto)
    # La cita aparece pero el valor 0 se dedujo → mantiene "inferido"
    assert verificado.evidencias[0].fidelidad == "inferido"


# ---------------------------------------------------------------------------
# Robustez
# ---------------------------------------------------------------------------


def test_programa_sin_evidencias_no_falla():
    programa = _programa_con_evidencias([])
    verificado = verificar_evidencias(programa, "texto irrelevante")
    assert verificado.evidencias == []


def test_verificacion_es_case_insensitive():
    texto = "Age Range: 13-17 years old."
    programa = _programa_con_evidencias(
        [
            EvidenciaCampo(
                campo="edad_min",
                valor="13",
                fragmento_fuente="age range: 13-17",
                fidelidad="literal",
            )
        ]
    )

    verificado = verificar_evidencias(programa, texto)
    assert verificado.evidencias[0].fidelidad == "literal"


def test_documento_fuente_se_hereda_del_programa():
    programa = _programa_con_evidencias(
        [
            EvidenciaCampo(
                campo="edad_min",
                valor="13",
                fragmento_fuente="Age 13-17",
                fidelidad="literal",
                documento_fuente=None,
            )
        ]
    )

    verificado = verificar_evidencias(programa, "Age 13-17")
    assert verificado.evidencias[0].documento_fuente == "data/raw/test.pdf"


# ---------------------------------------------------------------------------
# Complemento del sistema (edades 0-99, conversiones de moneda)
# ---------------------------------------------------------------------------


def test_edades_universales_generan_evidencias_inferidas():
    programa = Programa(
        nombre="Family Package",
        empresa_proveedora="Test",
        pais="Test",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
        edad_min=0,
        edad_max=99,
    )

    completado = generar_evidencias(programa)
    campos = {ev.campo: ev for ev in completado.evidencias}
    assert campos["edad_min"].fidelidad == "inferido"
    assert campos["edad_max"].fidelidad == "inferido"


def test_precio_convertido_desde_gbp_se_marca_derivado():
    programa = Programa(
        nombre="UK Programme",
        empresa_proveedora="Test",
        pais="Reino Unido",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
        precio_semanal_min_eur=1112.0,
        moneda_origen="GBP",
    )

    completado = generar_evidencias(programa)
    ev = next(e for e in completado.evidencias if e.campo == "precio_semanal_min_eur")
    assert ev.fidelidad == "derivado"


def test_generar_evidencias_no_pisa_evidencias_existentes_del_llm():
    programa = Programa(
        nombre="UK Programme",
        empresa_proveedora="Test",
        pais="Reino Unido",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
        edad_min=0,
        edad_max=99,
        evidencias=[
            EvidenciaCampo(
                campo="edad_min",
                valor="0",
                fragmento_fuente="all ages welcome",
                fidelidad="literal",
            )
        ],
    )

    completado = generar_evidencias(programa)
    # La evidencia del LLM se preserva; no se añade una duplicada
    evidencias_edad_min = [e for e in completado.evidencias if e.campo == "edad_min"]
    assert len(evidencias_edad_min) == 1
    assert evidencias_edad_min[0].fragmento_fuente == "all ages welcome"


# ---------------------------------------------------------------------------
# Métrica agregada
# ---------------------------------------------------------------------------


def test_tasa_trazabilidad_literal_calcula_porcentaje():
    programas = [
        _programa_con_evidencias(
            [
                EvidenciaCampo(campo="edad_min", valor="13", fidelidad="literal"),
                EvidenciaCampo(campo="edad_max", valor="17", fidelidad="literal"),
                EvidenciaCampo(campo="precio_semanal_min_eur", valor="950", fidelidad="derivado"),
                EvidenciaCampo(campo="fecha_inicio", valor="2026-04-07", fidelidad="no_verificable"),
            ]
        ),
        _programa_con_evidencias(
            [
                EvidenciaCampo(campo="edad_min", valor="0", fidelidad="inferido"),
                EvidenciaCampo(campo="edad_max", valor="99", fidelidad="inferido"),
            ]
        ),
    ]

    metrica = tasa_trazabilidad_literal(programas)
    assert metrica["n_evidencias"] == 6
    assert metrica["n_literales"] == 2
    assert metrica["n_derivadas"] == 1
    assert metrica["n_no_verificables"] == 1
    assert metrica["n_inferidas"] == 2
    assert metrica["tasa_literal"] == 2 / 6
    assert metrica["tasa_verificable"] == 3 / 6


def test_tasa_trazabilidad_con_catalogo_vacio_no_divide_por_cero():
    metrica = tasa_trazabilidad_literal([])
    assert metrica["n_evidencias"] == 0
    assert metrica["tasa_literal"] == 0.0
    assert metrica["tasa_verificable"] == 0.0


def test_evidencias_de_campos_no_criticos_no_cuentan():
    programa = _programa_con_evidencias(
        [
            EvidenciaCampo(campo="nombre", valor="Foo", fidelidad="literal"),
            EvidenciaCampo(campo="edad_min", valor="13", fidelidad="literal"),
        ]
    )

    metrica = tasa_trazabilidad_literal([programa])
    assert metrica["n_evidencias"] == 1
    assert metrica["n_literales"] == 1


def test_umbral_derivado_es_estable():
    # Sanity check: si alguien cambia el umbral, este test lo detecta
    assert UMBRAL_DERIVADO == 0.90
