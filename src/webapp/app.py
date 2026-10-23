"""Dashboard Streamlit del recomendador I-KIDS.

Interfaz web mínima que expone las dos funciones principales del sistema:

    1. Introducir un perfil de cliente y obtener recomendaciones ordenadas
       con su explicación trazable y avisos automáticos.
    2. Explorar el catálogo de programas extraídos con filtros por
       proveedor, estado documental y tipo de documento.

Se corresponde con el objetivo específico OE5 en su versión mínima
viable: plataforma web funcional sobre el pipeline existente, sin
funcionalidades de administración de catálogo ni gestión de usuarios,
que quedan documentadas como línea futura.

Lanzamiento::

    streamlit run src/webapp/app.py
"""

from __future__ import annotations

# --- Bootstrap: garantiza que la raíz del proyecto está en sys.path
# antes de importar el paquete src. Esto permite ejecutar `streamlit run
# src/webapp/app.py` desde cualquier terminal sin necesidad de configurar
# PYTHONPATH manualmente. ---
import sys
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json
from typing import Any

import pandas as pd
import streamlit as st

from src.application.gestionar_categorias import (
    enriquecer_catalogo as _enriquecer_con_categorias,
    filtrar_por_categorias,
    set_categorias,
)
from src.application.gestionar_seleccion import (
    cargar_seleccion,
    crear_campania,
    guardar_seleccion,
    limpiar_seleccion,
    toggle_programa,
)
from src.application.recomendar import recomendar
from src.models import CategoriaPrograma, PerfilCliente, Programa, SeleccionComercial
from src.recommendation import filtrar_candidatos

# Opciones de categoría para los multiselect de la UI, con etiqueta amigable.
# La coherencia con el enum CategoriaPrograma se verifica en
# tests/test_imports.py (test_categorias_ui_sincronizadas_con_enum) y en CI,
# así evitamos un assert runtime que podría tumbar la webapp si el deploy
# cachea módulos a medias.
_CATEGORIAS_UI: list[tuple[str, str]] = [
    ("mini_stay_verano", "☀️ Mini stay verano (I-KIDS)"),
    ("campamento_individual", "🏕️ Campamento (individual)"),
    ("campamento_deportivo", "⚽ Campamento deportivo"),
    ("semestre_academico", "📘 Semestre académico"),
    ("ano_academico", "🎓 Año académico"),
    ("gap_year", "🌍 Gap year"),
    ("inmersion_familiar", "🏡 Inmersión familiar"),
]
_CATEGORIA_LABEL: dict[str, str] = dict(_CATEGORIAS_UI)
_CATEGORIAS_VALORES: list[str] = [v for v, _ in _CATEGORIAS_UI]


ROOT = Path(__file__).resolve().parents[2]
CATALOGO_PATH = ROOT / "data" / "processed" / "programas.json"
RAW_DIR = ROOT / "data" / "raw"
EXCLUSIONS_PATH = ROOT / "data" / "exclusions.json"


# ---------------------------------------------------------------------------
# Carga del catálogo
# ---------------------------------------------------------------------------
#
# No se cachea deliberadamente con @st.cache_data: el catálogo persistido es
# un JSON de ~75\,KB cuya lectura y validación Pydantic cuesta pocos
# milisegundos en cada rerun. A cambio, se garantiza que cualquier
# modificación de exclusiones documentales ---hecha desde la pestaña
# Documentos--- se refleje de forma inmediata en el resto del dashboard
# sin que el asesor tenga que recargar la página. La versión cacheada
# producía una desincronización observable entre el estado del
# ``data/exclusions.json`` recién escrito y el ``catalogo_completo``
# servido desde la caché.


def cargar_catalogo() -> list[Programa]:
    if not CATALOGO_PATH.exists():
        return []
    raw = json.loads(CATALOGO_PATH.read_text(encoding="utf-8"))
    programas = [Programa.model_validate(p) for p in raw]
    # Aplicar categorías manuales (persistidas aparte del catálogo
    # extraído para que una re-extracción no las pise).
    return _enriquecer_con_categorias(programas)


# ---------------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="I-KIDS · Recomendador de programas",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Logo de I-KIDS como marca persistente en la cabecera de la sidebar
# (st.logo requiere Streamlit >= 1.34; se degrada con silencio si la
# versión instalada es más antigua, mostrando solo el título).
_LOGO_PATH = Path(__file__).parent / "assets" / "logo_ikids.png"
if _LOGO_PATH.exists() and hasattr(st, "logo"):
    st.logo(str(_LOGO_PATH), size="large")

# Header principal: logo + título alineados en dos columnas, para que
# el branding de I-KIDS sea visible desde la primera vista.
col_logo, col_titulo = st.columns([1, 5], vertical_alignment="center")
if _LOGO_PATH.exists():
    col_logo.image(str(_LOGO_PATH), width=110)
col_titulo.title("Recomendador de programas de inmersión lingüística")
col_titulo.caption(
    "Sistema de apoyo a la decisión desarrollado para I-KIDS · TFM MEI · "
    "Facultad de Informática de Barcelona (UPC)"
)

def _filtrar_por_exclusiones(
    programas: list[Programa], excluidos: set[str]
) -> list[Programa]:
    """Filtra programas cuyo documento de origen esté en la lista de exclusiones.

    Permite que las exclusiones aplicadas desde la pestaña "Documentos" se
    reflejen INMEDIATAMENTE en la pestaña "Recomendar" y en la vista de
    "Catálogo" sin requerir una re-extracción del catálogo. Los PDFs
    excluidos siguen omitiéndose además en la próxima re-extracción (ahorro
    de tokens de API); este filtro añade sobre eso la aplicación en vivo
    sobre el catálogo ya construido.

    Normaliza las rutas a POSIX relativo a la raíz del proyecto para que el
    match funcione tanto si `fuente_documento` se guardó como ruta absoluta
    como relativa.
    """
    if not excluidos:
        return programas

    def _esta_excluido(ruta: str | None) -> bool:
        if not ruta:
            return False
        candidato = Path(ruta)
        normalizada = candidato.as_posix()
        if normalizada in excluidos:
            return True
        try:
            rel = candidato.resolve().relative_to(ROOT).as_posix()
            if rel in excluidos:
                return True
        except (ValueError, OSError):
            pass
        return False

    return [
        p
        for p in programas
        if not _esta_excluido(p.fuente_documento)
        and not any(_esta_excluido(d) for d in (p.documentos_fuente or []))
    ]


def _leer_exclusiones_rapido() -> set[str]:
    """Lectura ligera de data/exclusions.json para filtrar el catálogo al
    inicio de cada rerun de Streamlit.

    Se define inline aquí porque `_cargar_exclusiones` (más abajo) se
    utiliza en callbacks y vive en la zona de helpers; a nivel de módulo
    no está todavía disponible cuando se carga el catálogo.
    """
    if not EXCLUSIONS_PATH.exists():
        return set()
    try:
        data = json.loads(EXCLUSIONS_PATH.read_text(encoding="utf-8"))
        return set(data.get("excluidos", []))
    except (json.JSONDecodeError, KeyError):
        return set()


catalogo_completo = cargar_catalogo()
excluidos_actuales_render = _leer_exclusiones_rapido()
catalogo = _filtrar_por_exclusiones(catalogo_completo, excluidos_actuales_render)

if not catalogo_completo:
    st.error(
        "No se ha encontrado el catálogo procesado en "
        f"`{CATALOGO_PATH.relative_to(ROOT)}`. "
        "Ejecuta primero el pipeline de extracción con "
        "`python -m src.pipeline`."
    )
    st.stop()

# Métricas del header: catálogo + (si aplica) exclusiones + (si aplica) campaña
_seleccion_header = cargar_seleccion()
_metricas_header: list[tuple[str, str | int, str | None]] = []

if excluidos_actuales_render:
    omitidos = len(catalogo_completo) - len(catalogo)
    _metricas_header.append(("Programas activos", len(catalogo), None))
    _metricas_header.append((
        "Omitidos por exclusión documental",
        omitidos,
        "Programas filtrados en vivo porque su PDF fue marcado como "
        "excluido en la pestaña Documentos. No participan en las "
        "recomendaciones ni aparecen en el catálogo visible.",
    ))
else:
    _metricas_header.append(("Programas en el catálogo", len(catalogo), None))

if _seleccion_header is not None:
    _metricas_header.append((
        f"⭐ En campaña «{_seleccion_header.nombre}»",
        len(_seleccion_header.programas_seleccionados),
        "Programas incluidos en la campaña comercial activa. "
        "Edítala desde la pestaña ⭐ Selección.",
    ))

_cols_header = st.columns(len(_metricas_header))
for _col, (_label, _value, _help) in zip(_cols_header, _metricas_header):
    _col.metric(_label, _value, help=_help)

tab_recomendar, tab_catalogo, tab_seleccion, tab_documentos = st.tabs(
    ["🎯 Recomendar", "📚 Catálogo", "⭐ Selección", "📁 Documentos"]
)


# ---------------------------------------------------------------------------
# Helpers de renderizado
# ---------------------------------------------------------------------------


def _escanear_documentos(catalogo: list[Programa]) -> list[dict]:
    """Recorre data/raw/** y devuelve metadatos combinados con el catálogo.

    Incluye PDFs e imágenes (los dos formatos que el pipeline procesa
    hoy). IMPORTANTE: espera recibir el catálogo COMPLETO (sin filtrar
    por exclusiones), para que los documentos excluidos conserven la
    cuenta real de programas que contienen. El filtro de exclusiones
    se aplica solo al `estado` del documento (que pasa a `excluido`),
    no a los metadatos.
    """
    from datetime import datetime

    from src.application.construir_catalogo import EXTENSIONES_SOPORTADAS

    if not RAW_DIR.exists():
        return []

    # Indexar programas por documento fuente (nombre + ruta)
    programas_por_doc: dict[str, list[Programa]] = {}
    for prog in catalogo:
        for ruta_doc in [prog.fuente_documento, *prog.documentos_fuente]:
            if not ruta_doc:
                continue
            programas_por_doc.setdefault(ruta_doc, [])
            if prog not in programas_por_doc[ruta_doc]:
                programas_por_doc[ruta_doc].append(prog)

    excluidos = _cargar_exclusiones()
    docs = []
    ficheros = sorted(
        f
        for f in RAW_DIR.glob("**/*")
        if f.is_file() and f.suffix.lower() in EXTENSIONES_SOPORTADAS
    )
    for doc in ficheros:
        rel = doc.relative_to(ROOT).as_posix()
        empresa = doc.parent.name if doc.parent != RAW_DIR else "(sin proveedor)"
        programas = programas_por_doc.get(rel, [])
        # También intentar por nombre absoluto (algunos guardados usan absoluto)
        if not programas:
            programas = programas_por_doc.get(str(doc), [])

        anyos = [p.anyo_documento for p in programas if p.anyo_documento]
        estados = [p.estado_documento for p in programas]
        esta_excluido = rel in excluidos

        # Prioridad del estado mostrado:
        # 1. "excluido" si el asesor lo marcó manualmente (decisión humana
        #    prevalece sobre el estado documental automático).
        # 2. "obsoleto" / "parcialmente_obsoleto" según evaluación.
        # 3. "vigente" si hay programas en el catálogo.
        # 4. "sin_procesar" si el documento no ha pasado por la extracción.
        if esta_excluido:
            estado_peor = "excluido"
        elif "obsoleto" in estados:
            estado_peor = "obsoleto"
        elif "parcialmente_obsoleto" in estados:
            estado_peor = "parcialmente_obsoleto"
        elif estados:
            estado_peor = "vigente"
        else:
            estado_peor = "sin_procesar"

        stat = doc.stat()
        docs.append({
            "ruta": rel,
            "ruta_abs": str(doc),
            "nombre": doc.name,
            "empresa": empresa,
            "tipo": doc.suffix.lower().lstrip("."),
            "tamano_kb": round(stat.st_size / 1024, 1),
            "modificado": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "n_programas": len(programas),
            "estado": estado_peor,
            "anyo_detectado": max(anyos) if anyos else None,
            "excluido": esta_excluido,
        })
    return docs


def _cargar_exclusiones() -> set[str]:
    """Lee data/exclusions.json (crea uno vacío si no existe)."""
    if not EXCLUSIONS_PATH.exists():
        return set()
    try:
        data = json.loads(EXCLUSIONS_PATH.read_text(encoding="utf-8"))
        return set(data.get("excluidos", []))
    except (json.JSONDecodeError, KeyError):
        return set()


def _guardar_exclusiones(excluidos: set[str]) -> None:
    EXCLUSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "descripcion": "Rutas relativas a documentos excluidos del pipeline por decision del asesor (obsoletos, duplicados, superados por version mas nueva). El pipeline debera consultar esta lista al construir el catalogo para omitirlos.",
        "excluidos": sorted(excluidos),
    }
    EXCLUSIONS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _toggle_exclusion(ruta: str) -> None:
    """Alterna el estado de exclusión de un documento.

    La callback persiste el cambio en \texttt{data/exclusions.json} y
    fuerza un rerun completo del script con \texttt{st.rerun()}. El
    rerun implícito que dispara Streamlit al terminar una callback
    deja en algunos escenarios un ciclo intermedio en el que los
    widgets con \texttt{key} fija ---el botón de exclusión y el icono
    de la fila---  conservan su etiqueta anterior durante un
    fotograma, dando la impresión al asesor de que el cambio no se ha
    aplicado hasta recargar manualmente. Un \texttt{st.rerun()}
    explícito reconstruye todo el árbol de widgets desde cero y
    garantiza que la etiqueta del botón, el icono del panel y las
    métricas superiores reflejen el nuevo estado en el mismo
    fotograma.
    """
    excl = _cargar_exclusiones()
    if ruta in excl:
        excl.remove(ruta)
    else:
        excl.add(ruta)
    _guardar_exclusiones(excl)
    st.rerun()


def _guardar_documento_subido(uploaded_file, empresa: str) -> Path:
    """Guarda un fichero subido en data/raw/<empresa>/<nombre>."""
    empresa = (empresa or "sin_proveedor").strip() or "sin_proveedor"
    destino_dir = RAW_DIR / empresa
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / uploaded_file.name
    with destino.open("wb") as f:
        f.write(uploaded_file.getbuffer())
    return destino


# ---------------------------------------------------------------------------
# Helpers de renderizado de fichas
# ---------------------------------------------------------------------------

def _mostrar_ficha_completa(p: Programa) -> None:
    """Renderiza toda la información conocida de un programa."""
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Identificación**")
        st.markdown(f"- Nombre: {p.nombre}")
        st.markdown(f"- Empresa: {p.empresa_proveedora}")
        st.markdown(f"- País: {p.pais}, ciudad: {p.ciudad or '—'}")
        st.markdown(f"- Idioma: {p.idioma}")
        st.markdown(f"- Idioma del documento: {p.idioma_documento_origen or '—'}")

        st.markdown("**Rangos**")
        st.markdown(f"- Edades: {p.edad_min or '—'}–{p.edad_max or '—'}")
        st.markdown(f"- Duración: {p.duracion_min_dias or '—'}–{p.duracion_max_dias or '—'} días")
        if p.fechas_inicio_recurrentes:
            st.markdown(f"- Inicio recurrente: `{p.fechas_inicio_recurrentes}`")

        st.markdown("**Alojamiento y acreditaciones**")
        st.markdown(f"- Tipos: {', '.join(p.tipo_alojamiento) if p.tipo_alojamiento else '—'}")
        st.markdown(f"- Acreditaciones: {', '.join(p.acreditaciones) if p.acreditaciones else '—'}")

    with col2:
        st.markdown("**Información económica**")
        if p.precio_semanal_min_eur is not None:
            st.markdown(
                f"- Precio semanal: {p.precio_semanal_min_eur:.0f}–{p.precio_semanal_max_eur:.0f} €/sem"
            )
            if p.moneda_origen and p.moneda_origen != "EUR":
                st.markdown(
                    f"- Precio original: {p.precio_semanal_min_origen}–{p.precio_semanal_max_origen} {p.moneda_origen}/sem"
                )
        else:
            st.markdown("- Precio: no extraído")

        if p.costes_adicionales:
            st.markdown("**Costes adicionales**")
            for c in p.costes_adicionales:
                importe = f"{c.importe} {c.moneda or ''}" if c.importe else "sin importe"
                st.markdown(f"- {c.concepto} ({c.tipo}): {importe}")

        st.markdown("**Vigencia y estado**")
        st.markdown(f"- Estado documento: `{p.estado_documento}`")
        st.markdown(f"- Tipo documento: `{p.tipo_documento}`")
        st.markdown(f"- Origen: `{p.origen_documento}`")
        if p.campos_obsoletos:
            st.warning(
                f"Campos obsoletos: {', '.join(p.campos_obsoletos)}. "
                f"{p.razon_obsolescencia or ''}"
            )

        if p.partners:
            st.markdown("**Partners**")
            for pt in p.partners:
                st.markdown(f"- {pt.nombre} ({pt.rol})")
        if p.partnerships:
            st.markdown("**Partnerships**")
            for pt in p.partnerships:
                st.markdown(f"- {pt.nombre}: {pt.descripcion or ''}")

        if p.cursos_especialistas:
            st.markdown("**Cursos especialistas**")
            for c in p.cursos_especialistas:
                extra = ""
                if c.horas_dedicadas:
                    extra += f" · {c.horas_dedicadas}h/sem"
                if c.precio_adicional_semanal_eur:
                    extra += f" · +{c.precio_adicional_semanal_eur:.0f} €/sem"
                if c.partnership:
                    extra += f" · partnership: {c.partnership}"
                st.markdown(f"- {c.nombre} ({c.actividad}){extra}")

        if p.turnos:
            st.markdown("**Turnos**")
            for t in p.turnos:
                st.markdown(f"- {t.fecha_inicio} → {t.fecha_fin}")

    st.caption(f"Fuente: `{Path(p.fuente_documento).name}`")


# ---------------------------------------------------------------------------
# TAB 1 — Recomendar
# ---------------------------------------------------------------------------

with tab_recomendar:

    with st.sidebar:
        st.header("Perfil del cliente")

        st.markdown("**Datos básicos**")
        edad = st.number_input(
            "Edad del estudiante", min_value=0, max_value=99, value=14, step=1
        )
        presupuesto = st.number_input(
            "Presupuesto máximo (€ total)", min_value=0, value=3000, step=100,
            help="Presupuesto total del cliente para el programa completo",
        )
        col_dur1, col_dur2 = st.columns(2)
        with col_dur1:
            dur_min = st.number_input("Duración mín. (días)", min_value=1, value=14)
        with col_dur2:
            dur_max = st.number_input("Duración máx. (días)", min_value=1, value=30)

        # Las opciones de país se derivan del catálogo activo, para que
        # el selector refleje siempre los destinos realmente disponibles
        # tras cualquier ampliación del corpus procesado. Se filtran las
        # entradas sin país y las etiquetas multi-destino, que no son
        # seleccionables de forma unívoca por el asesor.
        paises_catalogo = sorted({
            p.pais for p in catalogo
            if p.pais and not p.pais.lower().startswith("múltiples destinos")
        })
        pais_pref = st.selectbox(
            "País preferido",
            options=["Sin preferencia", *paises_catalogo],
        )
        alojamiento_pref = st.selectbox(
            "Alojamiento preferido",
            options=["Sin preferencia", "familia", "residencia", "hotel", "campamento", "otro"],
        )

        intereses_str = st.text_input(
            "Intereses (separados por comas)",
            value="",
            help="Ej: football, tennis, business, cambridge, clil, senior, family",
        )

        st.markdown("**Pesos de los criterios**")
        st.caption("Suma se normaliza automáticamente. Ajusta según prioridades del cliente.")
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            w_precio = st.slider("Precio", 0.0, 1.0, 0.25, step=0.05)
            w_duracion = st.slider("Duración", 0.0, 1.0, 0.15, step=0.05)
            w_ubicacion = st.slider("Ubicación", 0.0, 1.0, 0.15, step=0.05)
        with col_p2:
            w_alojamiento = st.slider("Alojamiento", 0.0, 1.0, 0.15, step=0.05)
            w_edad = st.slider("Ajuste edad", 0.0, 1.0, 0.15, step=0.05)
            w_afinidad = st.slider("Afinidad temática", 0.0, 1.0, 0.15, step=0.05)

        top_k = st.slider("Nº recomendaciones", 1, 10, 5, step=1)

        # Filtro por tipo de programa (categorías comerciales). Multiselect
        # vacío = sin filtro (fail-open). Las categorías se asignan desde la
        # pestaña 📚 Catálogo (multiselect por programa).
        categorias_filtro = st.multiselect(
            "🏷️ Tipo de programa",
            options=_CATEGORIAS_VALORES,
            default=[],
            format_func=lambda v: _CATEGORIA_LABEL.get(v, v),
            help=(
                "Limita la recomendación a programas de las categorías "
                "elegidas. Si no marcas ninguna, se usan todas. Las "
                "categorías se asignan en la pestaña 📚 Catálogo."
            ),
        )

        # Toggle de campaña activa: si hay campaña y el asesor lo activa, la
        # recomendación se restringe a los programas de la campaña actual.
        # Por defecto desactivado para no sorprender al asesor.
        _seleccion_sidebar = cargar_seleccion()
        if _seleccion_sidebar is not None and _seleccion_sidebar.programas_seleccionados:
            solo_campania = st.toggle(
                f"⭐ Solo programas de «{_seleccion_sidebar.nombre}»",
                value=False,
                help=(
                    f"Si está activado, la recomendación se hace únicamente "
                    f"entre los {len(_seleccion_sidebar.programas_seleccionados)} "
                    f"programas de la campaña activa."
                ),
            )
        else:
            solo_campania = False

    # Construir perfil
    intereses = [i.strip() for i in intereses_str.split(",") if i.strip()]
    perfil = PerfilCliente(
        idioma_deseado="inglés",
        edad_estudiante=int(edad),
        presupuesto_max_eur=float(presupuesto) if presupuesto > 0 else None,
        duracion_min_dias=int(dur_min),
        duracion_max_dias=int(dur_max),
        pais_preferido=None if pais_pref == "Sin preferencia" else pais_pref,
        tipo_alojamiento_preferido=None if alojamiento_pref == "Sin preferencia" else alojamiento_pref,
        intereses=intereses,
        pesos={
            "precio": w_precio,
            "duracion": w_duracion,
            "ubicacion": w_ubicacion,
            "alojamiento": w_alojamiento,
            "edad_ajuste": w_edad,
            "afinidad": w_afinidad,
        },
    )

    # Si el asesor ha activado el toggle de campaña, se restringe el
    # universo de recomendación a los programas de la selección activa.
    # Fail-open por diseño: si la selección está vacía o no tiene coincidencia
    # con el catálogo filtrado, se avisa pero no se bloquea.
    from src.application.gestionar_seleccion import filtrar_catalogo as _filtrar_por_campania

    if solo_campania:
        catalogo_rec = _filtrar_por_campania(catalogo, _seleccion_sidebar)
        if not catalogo_rec:
            st.warning(
                "La campaña activa no tiene programas que coincidan con el "
                "catálogo visible. Desactiva el toggle o revisa la pestaña ⭐ Selección."
            )
    else:
        catalogo_rec = catalogo

    # Filtro por categorías comerciales (fail-open: lista vacía = todo).
    if categorias_filtro:
        catalogo_rec = filtrar_por_categorias(catalogo_rec, categorias_filtro)
        if not catalogo_rec:
            etiquetas = ", ".join(_CATEGORIA_LABEL.get(c, c) for c in categorias_filtro)
            st.warning(
                f"Ningún programa visible pertenece a las categorías "
                f"seleccionadas ({etiquetas}). Revisa las asignaciones en "
                f"la pestaña 📚 Catálogo."
            )

    # La lista final se produce con el mismo caso de uso que consume el CLI
    # (`src.application.recomendar`), garantizando que la webapp y la
    # evaluación miden exactamente el mismo código. `filtrar_candidatos` se
    # invoca aparte solo para el contador de candidatos mostrado en la UI.
    candidatos = filtrar_candidatos(perfil, catalogo_rec)
    recomendaciones = recomendar(perfil, catalogo_rec, top_k=top_k)

    col_a, col_b, col_c = st.columns(3)
    col_a.metric(
        "Programas en el universo" if solo_campania else "Programas en catálogo",
        len(catalogo_rec),
        help=(
            f"Restringido a la campaña «{_seleccion_sidebar.nombre}»."
            if solo_campania
            else None
        ),
    )
    col_b.metric("Candidatos tras filtro duro", len(candidatos))
    col_c.metric("Recomendaciones devueltas", len(recomendaciones))

    if not recomendaciones:
        # Mensaje de error diagnóstico: identifica cuál de los filtros duros
        # ha vaciado la lista para que el asesor sepa qué ajustar. Analiza
        # los motivos más habituales (presupuesto insuficiente, idioma,
        # país, duración incompatible) sobre el catálogo completo.
        motivos = []
        if catalogo:
            # 1) Presupuesto: calcula el coste mínimo esperable del programa
            #    más barato del catálogo dadas las semanas que el cliente
            #    acabaría cursando.
            precios = [p.precio_semanal_min_eur for p in catalogo
                       if p.precio_semanal_min_eur is not None]
            if precios and perfil.presupuesto_max_eur:
                precio_minimo = min(precios)
                dias_minimo = max(1, perfil.duracion_min_dias or 7)
                coste_minimo = precio_minimo * dias_minimo / 7
                if coste_minimo > perfil.presupuesto_max_eur:
                    motivos.append(
                        f"**Presupuesto insuficiente**: el programa más "
                        f"barato del catálogo cuesta {precio_minimo:.0f} €/sem, "
                        f"lo que con tu duración mínima de {dias_minimo} días "
                        f"suma un total estimado de {coste_minimo:.0f} € "
                        f"frente a tu presupuesto de "
                        f"{perfil.presupuesto_max_eur:.0f} €."
                    )
            # 2) Idioma: ningún programa del catálogo coincide con el deseado
            idiomas = {p.idioma for p in catalogo}
            if perfil.idioma_deseado and perfil.idioma_deseado not in idiomas:
                motivos.append(
                    f"**Idioma no disponible**: ningún programa del catálogo "
                    f"se imparte en {perfil.idioma_deseado}; los idiomas "
                    f"disponibles son {', '.join(sorted(idiomas))}."
                )
            # 3) País: si el usuario fijó una preferencia dura no cubierta
            paises = {p.pais for p in catalogo if p.pais}
            if perfil.pais_preferido and perfil.pais_preferido not in paises:
                motivos.append(
                    f"**País no disponible**: ningún programa del catálogo "
                    f"está ubicado en {perfil.pais_preferido}; los países "
                    f"disponibles son {', '.join(sorted(paises))}."
                )
        if motivos:
            st.warning(
                "**Ningún programa pasa las restricciones duras del perfil.**\n\n"
                + "\n\n".join(f"- {m}" for m in motivos)
                + "\n\nAjusta el campo correspondiente en el panel lateral "
                "y la lista se recalculará automáticamente."
            )
        else:
            st.warning(
                "Ningún programa pasa las restricciones duras del perfil. "
                "Ajusta el presupuesto, la duración, el país o el alojamiento "
                "en el panel lateral."
            )
    else:
        st.subheader(f"Top {len(recomendaciones)} recomendaciones")

        for i, rec in enumerate(recomendaciones, start=1):
            programa = rec.programa
            # La explicación la genera el caso de uso `recomendar()` y se
            # anexa como atributo `explicacion` de cada Recomendacion.
            explicacion = rec.explicacion or ""

            # Título con la puntuación en el encabezado
            titulo = f"**#{i}.** {programa.nombre} · {programa.empresa_proveedora}"
            titulo += f" · **{rec.puntuacion:.2f}**"

            with st.expander(titulo, expanded=(i == 1)):
                # Ficha resumida
                col1, col2, col3 = st.columns(3)
                col1.markdown(f"**País:** {programa.pais}")
                col1.markdown(f"**Ciudad:** {programa.ciudad or '—'}")
                if programa.precio_semanal_min_eur is not None:
                    if programa.precio_semanal_max_eur and programa.precio_semanal_max_eur != programa.precio_semanal_min_eur:
                        precio_txt = f"{programa.precio_semanal_min_eur:.0f}–{programa.precio_semanal_max_eur:.0f} €/sem"
                    else:
                        precio_txt = f"{programa.precio_semanal_min_eur:.0f} €/sem"
                else:
                    precio_txt = "—"
                col2.markdown(f"**Precio:** {precio_txt}")
                col2.markdown(f"**Duración:** {programa.duracion_min_dias or '—'}–{programa.duracion_max_dias or '—'} días")
                col2.markdown(f"**Edades:** {programa.edad_min or '—'}–{programa.edad_max or '—'}")
                col3.markdown(f"**Alojamiento:** {', '.join(programa.tipo_alojamiento) if programa.tipo_alojamiento else '—'}")
                col3.markdown(f"**Documento fuente:** `{Path(programa.fuente_documento).name}`")
                col3.markdown(f"**Estado:** {programa.estado_documento}")

                # Descomposición de la puntuación
                st.markdown("**Descomposición por criterio**")
                desc_df = pd.DataFrame(
                    [
                        {"Criterio": k, "Puntuación": round(v, 3)}
                        for k, v in rec.descomposicion.items()
                    ]
                )
                st.bar_chart(desc_df.set_index("Criterio"), height=180)

                # Explicación textual
                st.markdown("**Explicación**")
                st.info(explicacion)

                # Acreditaciones, partnerships, cursos especialistas
                extras = []
                if programa.acreditaciones:
                    extras.append(f"**Acreditaciones:** {', '.join(programa.acreditaciones)}")
                if programa.partnerships:
                    extras.append(
                        "**Partnerships:** " + ", ".join(p.nombre for p in programa.partnerships)
                    )
                if programa.cursos_especialistas:
                    extras.append(
                        "**Cursos especialistas:** "
                        + ", ".join(
                            f"{c.nombre} ({c.actividad}"
                            + (f", +{c.precio_adicional_semanal_eur:.0f} €/sem" if c.precio_adicional_semanal_eur else "")
                            + ")"
                            for c in programa.cursos_especialistas
                        )
                    )
                if programa.turnos:
                    extras.append(
                        "**Turnos:** "
                        + " · ".join(
                            f"{t.fecha_inicio.isoformat()}–{t.fecha_fin.isoformat()}"
                            for t in programa.turnos
                        )
                    )
                if extras:
                    st.markdown("\n\n".join(extras))


# ---------------------------------------------------------------------------
# Helper compartido: filtro tipo Excel usado por las pestañas de Catálogo
# y Documentos. Se define a nivel de módulo (y no dentro del bloque
# `with tab_catalogo:`) para que las dos pestañas puedan invocarlo con
# la misma UX, en lugar de duplicar la lógica.
# ---------------------------------------------------------------------------


def _filtro_popover(col, label: str, opciones: list[str], key: str) -> list[str]:
    """Popover con casillas y atajos \"Todos / Ninguno\".

    El botón de disparo resume el estado activo (``todos (N)``, el nombre
    único cuando queda uno, o ``N de M`` en caso intermedio), de modo que
    el asesor ve de un vistazo qué filtros están activos sin
    desplegarlos.

    Nota de implementación: los botones ``Todos`` y ``Ninguno`` actualizan
    el estado maestro (``st.session_state[key]``) y además incrementan
    un contador de versión por filtro que se incluye en la ``key`` de
    cada checkbox. Al cambiar la ``key`` entre reruns, Streamlit trata
    cada checkbox como un widget \textbf{nuevo} sin estado previo, por
    lo que el argumento ``value=`` derivado del estado maestro se
    respeta de forma garantizada. Sin este contador, Streamlit conservaba
    el estado interno del widget por posición y lo priorizaba sobre el
    nuevo ``value=``, dejando los checkboxes desincronizados tras pulsar
    los atajos \"Todos\" o \"Ninguno\".
    """
    if key not in st.session_state:
        st.session_state[key] = list(opciones)
    # Auto-añadir solo las opciones GENUINAMENTE NUEVAS (no vistas en
    # ejecuciones anteriores) para no re-añadir las que el usuario
    # acaba de deseleccionar. Para ello guardamos el conjunto de
    # opciones de la ejecución anterior y comparamos. Caso típico:
    # el estado documental ``excluido`` aparece por primera vez cuando
    # el asesor excluye el primer documento. También cubre su
    # reaparición tras haber desaparecido: si todos los documentos
    # excluidos se reincluyen, ``excluido`` desaparece del filtro;
    # cuando se vuelve a excluir uno, reaparece como nueva opción y
    # se auto-selecciona. Si el usuario deselecciona ``vigente``
    # (por ejemplo), ``vigente`` sigue en opciones pero no en master,
    # y al coincidir con last_opciones no entra en nuevas: la decisión
    # explícita del usuario se respeta.
    last_opciones_key = f"{key}__last_opciones"
    last_opciones: set[str] = st.session_state.get(last_opciones_key, set(opciones))
    nuevas = [o for o in opciones if o not in last_opciones]
    if nuevas:
        current_master = list(st.session_state[key])
        for n in nuevas:
            if n not in current_master:
                current_master.append(n)
        st.session_state[key] = current_master
    st.session_state[last_opciones_key] = set(opciones)
    ver_key = f"{key}__ver"
    ver: int = st.session_state.get(ver_key, 0)
    seleccion_actual: list[str] = [o for o in st.session_state[key] if o in opciones]
    if len(seleccion_actual) == len(opciones):
        boton = f"{label}: todos ({len(opciones)})"
    elif len(seleccion_actual) == 1:
        boton = f"{label}: {seleccion_actual[0]}"
    else:
        boton = f"{label}: {len(seleccion_actual)} de {len(opciones)}"
    with col.popover(boton, use_container_width=True):
        c_all, c_none = st.columns(2)
        if c_all.button("Todos", key=f"{key}_all", use_container_width=True):
            st.session_state[key] = list(opciones)
            st.session_state[ver_key] = ver + 1
            st.rerun()
        if c_none.button("Ninguno", key=f"{key}_none", use_container_width=True):
            st.session_state[key] = []
            st.session_state[ver_key] = ver + 1
            st.rerun()
        st.divider()
        nueva: list[str] = []
        for opcion in opciones:
            ck_key = f"{key}_{opcion}__v{ver}"
            marcada = st.checkbox(
                str(opcion),
                value=opcion in seleccion_actual,
                key=ck_key,
            )
            if marcada:
                nueva.append(opcion)
        st.session_state[key] = nueva
    return st.session_state[key]


# ---------------------------------------------------------------------------
# TAB 2 — Catálogo
# ---------------------------------------------------------------------------

with tab_catalogo:
    st.subheader("📚 Catálogo completo de programas extraídos")
    st.caption(
        "Vista de **consulta y filtrado**: una fila por programa recomendable. "
        "Los filtros tipo Excel permiten acotar por proveedor, tipo de documento, "
        "estado documental del programa y país."
    )

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    proveedores = sorted({p.empresa_proveedora for p in catalogo})
    tipos_doc = sorted({p.tipo_documento for p in catalogo})
    estados = sorted({p.estado_documento for p in catalogo})
    paises = sorted({p.pais for p in catalogo})

    filtro_prov = _filtro_popover(col_f1, "Proveedor", proveedores, "f_prov")
    filtro_tipo = _filtro_popover(col_f2, "Tipo de documento", tipos_doc, "f_tipo")
    filtro_estado = _filtro_popover(col_f3, "Estado documental", estados, "f_estado")
    filtro_pais = _filtro_popover(col_f4, "País", paises, "f_pais")

    filtrados = [
        p for p in catalogo
        if p.empresa_proveedora in filtro_prov
        and p.tipo_documento in filtro_tipo
        and p.estado_documento in filtro_estado
        and p.pais in filtro_pais
    ]

    st.metric("Programas filtrados", f"{len(filtrados)} / {len(catalogo)}")

    # Cargar la campaña activa (si existe) para marcar visualmente qué
    # programas forman ya parte de ella y permitir incluir/quitar desde
    # el detalle de cada programa.
    _seleccion_catalogo = cargar_seleccion()
    _en_campania_keys: set[str] = (
        set(_seleccion_catalogo.programas_seleccionados)
        if _seleccion_catalogo is not None
        else set()
    )

    # Tabla resumen
    resumen = []
    for p in filtrados:
        precio = (
            f"{p.precio_semanal_min_eur:.0f}–{p.precio_semanal_max_eur:.0f}"
            if p.precio_semanal_min_eur and p.precio_semanal_max_eur
            else "—"
        )
        en_campania = (
            p.programa_key in _en_campania_keys if p.programa_key else False
        )
        resumen.append(
            {
                "⭐": "✓" if en_campania else "",
                "Programa": p.nombre,
                "Proveedor": p.empresa_proveedora,
                "País": p.pais,
                "Ciudad": p.ciudad or "—",
                "Edades": f"{p.edad_min or '—'}–{p.edad_max or '—'}",
                "Duración (d)": f"{p.duracion_min_dias or '—'}–{p.duracion_max_dias or '—'}",
                "Precio (€/sem)": precio,
                "Alojamiento": ", ".join(p.tipo_alojamiento) if p.tipo_alojamiento else "—",
                "Tipo doc": p.tipo_documento,
                "Estado del programa": p.estado_documento,
            }
        )
    st.dataframe(pd.DataFrame(resumen), width='stretch', hide_index=True)

    if _seleccion_catalogo is not None:
        st.caption(
            f"⭐ marca los programas incluidos en la campaña activa "
            f"«{_seleccion_catalogo.nombre}». "
            f"Añade o quita desde el detalle de cada programa, debajo."
        )
    else:
        st.caption(
            "No hay campaña activa. Puedes crear una en la pestaña "
            "**⭐ Selección** para empezar a marcar programas."
        )

    # Detalle expandible
    st.subheader("Detalle por programa")

    def _on_toggle_catalogo(programa_key: str, state_key: str) -> None:
        """Callback que sincroniza el checkbox con la campaña activa."""
        try:
            toggle_programa(programa_key, incluir=st.session_state[state_key])
        except RuntimeError:
            # No hay campaña activa: ignoramos el toggle y avisamos vía mensaje
            # (gestionado abajo cuando se renderiza el checkbox).
            pass

    def _on_categorias_change(programa_key: str, state_key: str) -> None:
        """Persiste la nueva lista de categorías del programa."""
        etiquetas = st.session_state.get(state_key, [])
        # Las opciones en el multiselect son los VALORES del enum (no las
        # etiquetas con emoji), así que esto ya es la lista buena.
        try:
            set_categorias(programa_key, etiquetas)
        except ValueError:
            # Alguna categoría quedó fuera del enum: ignoramos silenciosamente.
            # No debería pasar porque las opciones vienen del enum.
            pass

    for p in filtrados:
        with st.expander(f"{p.nombre} · {p.empresa_proveedora}"):
            _mostrar_ficha_completa(p)

            # Multiselect de categorías comerciales (persistido aparte).
            if p.programa_key:
                cats_state_key = f"cats_cat_{p.programa_key}"
                # Sanear default: descartar valores que ya no estén en el
                # enum (ej. renombres antiguos) para no romper el multiselect.
                _default_cats = [
                    c for c in p.categorias if c in _CATEGORIAS_VALORES
                ]
                st.multiselect(
                    "🏷️ Categorías comerciales",
                    options=_CATEGORIAS_VALORES,
                    default=_default_cats,
                    key=cats_state_key,
                    format_func=lambda v: _CATEGORIA_LABEL.get(v, v),
                    on_change=_on_categorias_change,
                    args=(p.programa_key, cats_state_key),
                    help=(
                        "Un programa puede estar en varias categorías. "
                        "Lo que marques aquí se usa en el filtro «Tipo de "
                        "programa» de la pestaña 🎯 Recomendar."
                    ),
                )

            if _seleccion_catalogo is not None and p.programa_key:
                state_key = f"camp_cat_{p.programa_key}"
                st.checkbox(
                    "⭐ Incluir en la campaña activa",
                    value=p.programa_key in _en_campania_keys,
                    key=state_key,
                    on_change=_on_toggle_catalogo,
                    args=(p.programa_key, state_key),
                    help=(
                        f"Si lo marcas, este programa aparecerá en "
                        f"«{_seleccion_catalogo.nombre}»."
                    ),
                )
            elif not p.programa_key:
                st.caption(
                    "⚠ Este programa no tiene `programa_key` y no se puede "
                    "añadir a una campaña."
                )
            else:
                st.caption(
                    "ℹ️ Crea una campaña en la pestaña **⭐ Selección** "
                    "para poder marcar este programa."
                )


# ---------------------------------------------------------------------------
# TAB 3 — Selección (campaña comercial activa)
# ---------------------------------------------------------------------------

with tab_seleccion:
    st.subheader("⭐ Selección comercial activa")
    st.caption(
        "Vista para **curar comercialmente** el catálogo: elige qué programas "
        "quiere empujar I-KIDS en un periodo concreto (una campaña). "
        "Después, desde la pestaña Recomendar, puedes marcar un toggle para "
        "recomendar solo entre los seleccionados."
    )

    seleccion_actual = cargar_seleccion()

    # --- Caso A: no hay campaña activa -> ofrecer creación
    if seleccion_actual is None:
        st.info(
            "No hay ninguna campaña activa en este momento. "
            "Crea una para empezar a añadir programas."
        )
        with st.form("form_crear_campania"):
            nombre_nueva = st.text_input(
                "Nombre de la campaña",
                placeholder="Ej. Campaña verano 2027",
            )
            col_f1, col_f2 = st.columns(2)
            fecha_inicio_nueva = col_f1.date_input(
                "Fecha de inicio",
                value=None,
                help="Si lo dejas vacío, se usa la fecha de hoy.",
            )
            fecha_fin_nueva = col_f2.date_input(
                "Fecha de fin (opcional)",
                value=None,
                help="Deja vacío si la campaña no tiene fecha de cierre.",
            )
            notas_nuevas = st.text_area(
                "Notas internas (opcional)",
                placeholder="Motivo o alcance de la campaña",
                height=80,
            )
            crear = st.form_submit_button(
                "Crear campaña", type="primary", use_container_width=True
            )

        if crear:
            if not nombre_nueva.strip():
                st.error("El nombre de la campaña no puede estar vacío.")
            else:
                try:
                    crear_campania(
                        nombre=nombre_nueva.strip(),
                        fecha_inicio=fecha_inicio_nueva or None,
                        fecha_fin=fecha_fin_nueva or None,
                        notas=notas_nuevas.strip() or None,
                    )
                    st.success(f"Campaña «{nombre_nueva.strip()}» creada.")
                    st.rerun()
                except Exception as e:
                    st.error(f"No se ha podido crear la campaña: {e}")

    # --- Caso B: hay campaña activa -> mostrar y permitir editar
    else:
        col_titulo, col_boton_cerrar = st.columns([3, 1], vertical_alignment="center")
        col_titulo.markdown(f"### 📌 {seleccion_actual.nombre}")

        def _cerrar_campania():
            limpiar_seleccion()

        col_boton_cerrar.button(
            "🗑 Terminar campaña",
            on_click=_cerrar_campania,
            help=(
                "Elimina la campaña activa. Los programas no se borran, solo "
                "se desmarcan. Puedes crear una campaña nueva después."
            ),
            use_container_width=True,
        )

        # Metadatos editables
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric(
            "Programas en campaña",
            len(seleccion_actual.programas_seleccionados),
        )
        col_m2.metric(
            "Fecha de inicio",
            seleccion_actual.fecha_inicio.isoformat(),
        )
        col_m3.metric(
            "Fecha de fin",
            seleccion_actual.fecha_fin.isoformat() if seleccion_actual.fecha_fin else "—",
        )

        with st.expander("✏️ Editar metadatos de la campaña"):
            with st.form("form_editar_campania"):
                nombre_edit = st.text_input(
                    "Nombre",
                    value=seleccion_actual.nombre,
                )
                col_e1, col_e2 = st.columns(2)
                fecha_inicio_edit = col_e1.date_input(
                    "Fecha de inicio",
                    value=seleccion_actual.fecha_inicio,
                )
                fecha_fin_edit = col_e2.date_input(
                    "Fecha de fin (opcional)",
                    value=seleccion_actual.fecha_fin,
                )
                notas_edit = st.text_area(
                    "Notas internas",
                    value=seleccion_actual.notas or "",
                    height=80,
                )
                guardar = st.form_submit_button(
                    "Guardar cambios",
                    type="primary",
                )

            if guardar:
                if not nombre_edit.strip():
                    st.error("El nombre no puede estar vacío.")
                else:
                    try:
                        actualizada = SeleccionComercial(
                            nombre=nombre_edit.strip(),
                            fecha_inicio=fecha_inicio_edit,
                            fecha_fin=fecha_fin_edit or None,
                            programas_seleccionados=seleccion_actual.programas_seleccionados,
                            notas=notas_edit.strip() or None,
                        )
                        guardar_seleccion(actualizada)
                        st.success("Metadatos actualizados.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se ha podido guardar: {e}")

        st.divider()

        # Lista de programas seleccionados
        st.markdown("#### Programas incluidos en la campaña")

        if not seleccion_actual.programas_seleccionados:
            st.info(
                "La campaña está vacía. Ve a la pestaña **Catálogo** y marca "
                "los programas que quieras incluir con el checkbox «En campaña»."
            )
        else:
            # Mapear programa_key a objeto Programa para enriquecer la tabla
            por_key = {
                p.programa_key: p for p in catalogo if p.programa_key
            }
            resumen_sel = []
            huerfanos = []
            for key in seleccion_actual.programas_seleccionados:
                p = por_key.get(key)
                if p is None:
                    huerfanos.append(key)
                    continue
                tipo_txt = (
                    ", ".join(_CATEGORIA_LABEL.get(c, c) for c in p.categorias)
                    if p.categorias
                    else "—"
                )
                resumen_sel.append(
                    {
                        "Programa": p.nombre,
                        "Proveedor": p.empresa_proveedora,
                        "País": p.pais,
                        "Tipo": tipo_txt,
                        "Edades": f"{p.edad_min or '—'}–{p.edad_max or '—'}",
                        "Precio (€/sem)": (
                            f"{p.precio_semanal_min_eur:.0f}–{p.precio_semanal_max_eur:.0f}"
                            if p.precio_semanal_min_eur and p.precio_semanal_max_eur
                            else "—"
                        ),
                        "key": key,
                    }
                )

            if resumen_sel:
                df_sel = pd.DataFrame(resumen_sel).drop(columns=["key"])
                st.dataframe(df_sel, width='stretch', hide_index=True)

            # Botón de quitar por programa
            st.markdown("##### Quitar programas de la campaña")
            for item in resumen_sel:
                col_lbl, col_btn = st.columns([5, 1])
                col_lbl.write(f"**{item['Programa']}** · {item['Proveedor']}")
                col_btn.button(
                    "❌ Quitar",
                    key=f"quitar_{item['key']}",
                    on_click=toggle_programa,
                    args=(item["key"], False),
                    use_container_width=True,
                )

            if huerfanos:
                with st.expander(
                    f"⚠️ {len(huerfanos)} programa(s) seleccionado(s) que ya no están en el catálogo"
                ):
                    st.caption(
                        "Estos `programa_key` figuran en la campaña pero no "
                        "aparecen en el catálogo actual (posiblemente eliminados "
                        "o renombrados tras una re-extracción). Puedes quitarlos."
                    )
                    for key in huerfanos:
                        col_h1, col_h2 = st.columns([5, 1])
                        col_h1.code(key)
                        col_h2.button(
                            "❌ Quitar",
                            key=f"quitar_huerfano_{key}",
                            on_click=toggle_programa,
                            args=(key, False),
                            use_container_width=True,
                        )

        if seleccion_actual.notas:
            st.divider()
            st.markdown("#### Notas internas")
            st.info(seleccion_actual.notas)


# ---------------------------------------------------------------------------
# TAB 4 — Documentos (gestión documental)
# ---------------------------------------------------------------------------

with tab_documentos:
    st.subheader("📁 Inventario de documentos del corpus")
    st.caption(
        "Vista de **gestión documental**: una fila por fichero (PDF o imagen) "
        "bajo `data/raw/`. Permite auditar cuántos programas aporta cada "
        "documento, consultar la fuente original, excluir ficheros caducados o "
        "duplicados mediante 🚫 y añadir nuevos documentos al corpus."
    )

    # Pasamos el catálogo COMPLETO (no el filtrado por exclusiones) a
    # `_escanear_documentos` para que los PDFs excluidos sigan mostrando
    # la cuenta real de programas que producen cuando se reactiven.
    documentos = _escanear_documentos(catalogo_completo)
    excluidos_actuales = _cargar_exclusiones()

    # ---- Métricas resumen
    total = len(documentos)
    activos = sum(1 for d in documentos if not d["excluido"])
    obsoletos = sum(1 for d in documentos if d["estado"] in ("obsoleto", "parcialmente_obsoleto"))
    sin_procesar = sum(1 for d in documentos if d["estado"] == "sin_procesar")

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Documentos totales", total)
    col_m2.metric("Activos", activos)
    col_m3.metric("Excluidos", total - activos)
    col_m4.metric("Sin procesar", sin_procesar)

    st.divider()

    # ---- Subir nuevo documento
    with st.expander("➕ Añadir un nuevo documento", expanded=False):
        col_up1, col_up2 = st.columns([2, 1])
        with col_up1:
            uploaded = st.file_uploader(
                "Selecciona un PDF",
                type=["pdf"],
                accept_multiple_files=False,
            )
        with col_up2:
            proveedores_conocidos = sorted({d["empresa"] for d in documentos if d["empresa"] != "(sin proveedor)"})
            opciones_prov = proveedores_conocidos + ["+ Nueva empresa..."]
            proveedor_sel = st.selectbox("Empresa proveedora", opciones_prov)
            if proveedor_sel == "+ Nueva empresa...":
                proveedor_sel = st.text_input("Nombre de la nueva empresa", value="")

        if uploaded and proveedor_sel:
            if st.button("💾 Guardar en data/raw/", type="primary"):
                destino = _guardar_documento_subido(uploaded, proveedor_sel)
                st.success(
                    f"Guardado en `{destino.relative_to(ROOT)}`. Para "
                    "incorporarlo al catálogo, ejecuta la re-extracción: "
                    "`python -m src.application.construir_catalogo --reextraer`"
                )

    st.divider()

    # ---- Filtros de la tabla (reutilizan el popover tipo Excel de Catálogo)
    # Los documentos excluidos SIEMPRE aparecen en la tabla con la marca
    # "🚫" para que el asesor pueda reactivarlos sin tener que buscar un
    # toggle oculto. Antes había un `Mostrar excluidos` que, al
    # desactivarse, hacía desaparecer la fila y el documento solo podía
    # recuperarse editando `data/exclusions.json` a mano, lo que era
    # confuso.
    col_f1, col_f2 = st.columns(2)
    empresas_disp = sorted({d["empresa"] for d in documentos})
    estados_disp = sorted({d["estado"] for d in documentos})

    filtro_emp = _filtro_popover(col_f1, "Proveedor", empresas_disp, "docs_prov")
    filtro_est = _filtro_popover(col_f2, "Estado documental", estados_disp, "docs_estado")

    docs_filtrados = [
        d for d in documentos
        if d["empresa"] in filtro_emp
        and d["estado"] in filtro_est
    ]

    # ---- Tabla resumen
    if docs_filtrados:
        df = pd.DataFrame([
            {
                "Excluido": "🚫" if d["excluido"] else "",
                "Documento": d["nombre"],
                "Proveedor": d["empresa"],
                "Programas": d["n_programas"],
                "Estado documental": d["estado"],
                # Siempre str: mezclar int con "—" rompe pyarrow en pandas 3.x
                # (intenta inferir int64 y falla al llegar al guion em-dash).
                "Año": str(d["anyo_detectado"]) if d["anyo_detectado"] else "—",
                "Tamaño (KB)": d["tamano_kb"],
                "Modificado": d["modificado"],
            }
            for d in docs_filtrados
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No hay documentos que cumplan los filtros seleccionados.")

    st.divider()

    # ---- Acciones por documento
    st.subheader("Consulta y acciones por documento")
    for d in docs_filtrados:
        titulo_prefix = "🚫 " if d["excluido"] else "📄 "
        titulo = f"{titulo_prefix}{d['nombre']} · {d['empresa']}"
        with st.expander(titulo):
            col_info, col_acciones = st.columns([2, 1])

            with col_info:
                st.markdown(f"- **Ruta:** `{d['ruta']}`")
                st.markdown(f"- **Tamaño:** {d['tamano_kb']} KB")
                st.markdown(f"- **Modificado:** {d['modificado']}")
                st.markdown(f"- **Año detectado:** {d['anyo_detectado'] or 'no detectado'}")
                st.markdown(f"- **Estado:** `{d['estado']}`")
                st.markdown(f"- **Programas asociados:** {d['n_programas']}")
                if d["n_programas"] == 0:
                    st.warning(
                        "Este documento no tiene programas extraídos. "
                        "Ejecuta el pipeline para procesarlo."
                    )
                if d["excluido"]:
                    st.error(
                        "Documento marcado como EXCLUIDO. No se procesará en "
                        "futuras ejecuciones del pipeline."
                    )

            with col_acciones:
                # Botón excluir/incluir
                label = "✅ Reincluir" if d["excluido"] else "🚫 Excluir"
                st.button(
                    label,
                    key=f"tog_{d['ruta']}",
                    on_click=_toggle_exclusion,
                    args=(d["ruta"],),
                )
                # Descarga del PDF
                try:
                    with open(d["ruta_abs"], "rb") as f:
                        st.download_button(
                            "⬇️ Descargar PDF",
                            data=f.read(),
                            file_name=d["nombre"],
                            mime="application/pdf",
                            key=f"dl_{d['ruta']}",
                        )
                except FileNotFoundError:
                    st.error("Fichero no encontrado en disco.")

            # Vista previa embebida (Streamlit >=1.44 tiene st.pdf; fallback a base64)
            if not d["excluido"]:
                if st.checkbox("Ver PDF inline", key=f"prev_{d['ruta']}"):
                    try:
                        st.pdf(d["ruta_abs"])
                    except AttributeError:
                        # Fallback: base64 iframe
                        import base64
                        with open(d["ruta_abs"], "rb") as f:
                            b64 = base64.b64encode(f.read()).decode()
                        st.markdown(
                            f'<iframe src="data:application/pdf;base64,{b64}" '
                            'width="100%" height="600"></iframe>',
                            unsafe_allow_html=True,
                        )
