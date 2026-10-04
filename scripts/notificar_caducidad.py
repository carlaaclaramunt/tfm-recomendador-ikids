"""Notificación por correo electrónico de documentos caducados.

Lanzamiento manual (o programable con cron / GitHub Actions) que lee el
catálogo persistido en ``data/processed/programas.json``, agrupa los
programas por documento fuente, identifica aquellos cuyo estado
documental es ``obsoleto`` o ``parcialmente_obsoleto`` y envía un correo
HTML con el resumen al responsable de I-KIDS.

Se construye intencionadamente como script separado, no como feature
integrada en el dashboard, por tres razones:

1. El despliegue público del dashboard en Streamlit Community Cloud no
   dispone de infraestructura de \textit{cron} ni de un canal saliente
   para SMTP; el envío debe iniciarse desde un entorno con credenciales,
   fuera del propio servicio de visualización.
2. La política de ``quién recibe qué`` es de I-KIDS, no del sistema. El
   script expone esa política como variables de entorno
   (``EMAIL_TO``, ``EMAIL_FROM``), que la organización puede ajustar sin
   tocar código.
3. El modo ``--dry-run`` permite reproducir el contenido del correo sin
   enviar nada, lo que facilita la auditoría del listado por parte del
   asesor antes de que se propague.

Uso típico::

    # Prueba sin enviar: imprime por pantalla el correo tal cual saldría
    .venv/bin/python -m scripts.notificar_caducidad --dry-run

    # Envío real: requiere SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_TO
    # configurados en el fichero .env del repositorio
    .venv/bin/python -m scripts.notificar_caducidad

Variables de entorno esperadas (todas opcionales con default razonable
salvo las credenciales SMTP y el destinatario):

- ``SMTP_HOST`` (p.ej. ``smtp.gmail.com``)
- ``SMTP_PORT`` (por defecto 587)
- ``SMTP_USER``
- ``SMTP_PASS``
- ``EMAIL_FROM`` (por defecto ``SMTP_USER``)
- ``EMAIL_TO`` (destinatario, obligatorio en modo envío)
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
import sys
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from src.models import Programa

ROOT = Path(__file__).resolve().parents[1]
CATALOGO_PATH = ROOT / "data" / "processed" / "programas.json"


# ---------------------------------------------------------------------------
# Lógica de dominio: identificar documentos a notificar
# ---------------------------------------------------------------------------


ESTADOS_A_NOTIFICAR = {"obsoleto", "parcialmente_obsoleto"}


def _cargar_catalogo(path: Path) -> list[Programa]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Programa.model_validate(p) for p in payload]


def _agrupar_por_documento(programas: list[Programa]) -> dict[str, list[Programa]]:
    """Agrupa los programas por su documento fuente.

    Un mismo documento puede alimentar varios programas (p.ej. un
    brochure que describe un programa por ciudad). La notificación
    agrupa a nivel de documento para no inundar al asesor con una
    entrada por programa.
    """
    por_doc: dict[str, list[Programa]] = defaultdict(list)
    for p in programas:
        if p.fuente_documento:
            por_doc[p.fuente_documento].append(p)
    return por_doc


def _documentos_a_notificar(
    programas: list[Programa],
) -> list[dict]:
    """Devuelve la lista de documentos que requieren atención.

    Cada entrada agrupa: ruta del documento, estado peor observado entre
    sus programas, año del documento (si consta), número de programas
    afectados y una razón textual preparada para el cuerpo del correo.
    """
    resultado: list[dict] = []
    for ruta, progs in _agrupar_por_documento(programas).items():
        estados = {p.estado_documento for p in progs}
        if not (estados & ESTADOS_A_NOTIFICAR):
            continue
        # Priorizar `obsoleto` sobre `parcialmente_obsoleto`
        estado_peor = (
            "obsoleto" if "obsoleto" in estados else "parcialmente_obsoleto"
        )
        anyos = {p.anyo_documento for p in progs if p.anyo_documento}
        razones = {p.razon_obsolescencia for p in progs if p.razon_obsolescencia}
        resultado.append(
            {
                "ruta": ruta,
                "estado": estado_peor,
                "anyo": max(anyos) if anyos else None,
                "n_programas": len(progs),
                "razon": next(iter(razones)) if razones else "",
            }
        )
    # Ordenar: primero los obsoletos, luego parcialmente, luego por año
    resultado.sort(
        key=lambda d: (
            0 if d["estado"] == "obsoleto" else 1,
            d["anyo"] or 0,
        )
    )
    return resultado


# ---------------------------------------------------------------------------
# Construcción del correo
# ---------------------------------------------------------------------------


def _render_html(docs: list[dict]) -> str:
    """Devuelve el cuerpo HTML del correo."""
    if not docs:
        return (
            "<p>Enhorabuena: ningún documento del catálogo está marcado "
            "como obsoleto o parcialmente obsoleto en esta ejecución.</p>"
        )
    filas = []
    for d in docs:
        color = "#c62828" if d["estado"] == "obsoleto" else "#ef6c00"
        etiqueta = {
            "obsoleto": "Obsoleto",
            "parcialmente_obsoleto": "Parcialmente obsoleto",
        }[d["estado"]]
        filas.append(
            f"""
            <tr>
              <td style="padding:6px 10px;border-bottom:1px solid #eee;">
                <code>{d['ruta']}</code>
              </td>
              <td style="padding:6px 10px;border-bottom:1px solid #eee;color:{color};font-weight:bold;">
                {etiqueta}
              </td>
              <td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:center;">
                {d['anyo'] or '—'}
              </td>
              <td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:center;">
                {d['n_programas']}
              </td>
            </tr>
            """
        )
    tabla = "\n".join(filas)
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""
    <html><body style="font-family:Georgia,serif;color:#222;">
      <h2 style="color:#1b3a5c;">Documentos caducados en el catálogo</h2>
      <p>Esta notificación lista los documentos cuyos datos están
      marcados como obsoletos o parcialmente obsoletos por el
      subsistema de curación en la última construcción del catálogo
      ({fecha}). Se recomienda revisar la vigencia de las ofertas,
      solicitar la versión actualizada al proveedor correspondiente y,
      si procede, excluir el documento desde la pestaña
      <em>Documentos</em> del dashboard.</p>
      <table style="border-collapse:collapse;width:100%;margin-top:12px;font-size:14px;">
        <thead>
          <tr style="background:#eef2f6;">
            <th style="padding:8px 10px;text-align:left;">Documento</th>
            <th style="padding:8px 10px;text-align:left;">Estado</th>
            <th style="padding:8px 10px;text-align:center;">Año</th>
            <th style="padding:8px 10px;text-align:center;">Programas</th>
          </tr>
        </thead>
        <tbody>
          {tabla}
        </tbody>
      </table>
      <p style="margin-top:16px;font-size:12px;color:#666;">
        Correo generado automáticamente por el sistema de recomendación
        de I-KIDS. Para dejar de recibir esta notificación o cambiar el
        destinatario, modificar la variable <code>EMAIL_TO</code> en
        el fichero <code>.env</code> del repositorio.
      </p>
    </body></html>
    """.strip()


def _render_texto(docs: list[dict]) -> str:
    """Versión en texto plano como fallback multipart."""
    if not docs:
        return (
            "Ningún documento del catálogo está marcado como obsoleto o "
            "parcialmente obsoleto en esta ejecución."
        )
    lineas = [
        "Documentos caducados en el catálogo",
        "=" * 40,
        "",
    ]
    for d in docs:
        lineas.append(
            f"- [{d['estado']}] {d['ruta']} "
            f"(año {d['anyo'] or 'desconocido'}, {d['n_programas']} programa(s))"
        )
    lineas.append("")
    lineas.append(
        "Correo generado automáticamente por el sistema de recomendación "
        "de I-KIDS. Modificar EMAIL_TO en .env para cambiar destinatario."
    )
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Envío
# ---------------------------------------------------------------------------


def _construir_mensaje(
    docs: list[dict],
    remitente: str,
    destinatario: str,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"[I-KIDS] {len(docs)} documento(s) caducado(s) en el catálogo"
        if docs
        else "[I-KIDS] Catálogo sin documentos caducados"
    )
    msg["From"] = remitente
    msg["To"] = destinatario
    msg.attach(MIMEText(_render_texto(docs), "plain", "utf-8"))
    msg.attach(MIMEText(_render_html(docs), "html", "utf-8"))
    return msg


def _enviar(msg: MIMEMultipart, host: str, port: int, user: str, password: str) -> None:
    contexto = ssl.create_default_context()
    with smtplib.SMTP(host, port) as servidor:
        servidor.starttls(context=contexto)
        servidor.login(user, password)
        servidor.send_message(msg)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Imprime el correo por pantalla sin enviarlo. Útil para auditar.",
    )
    parser.add_argument(
        "--catalogo",
        type=Path,
        default=CATALOGO_PATH,
        help=f"Ruta al catálogo JSON (por defecto {CATALOGO_PATH}).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    load_dotenv(override=True)

    if not args.catalogo.exists():
        print(
            f"✗ No se encuentra el catálogo en {args.catalogo}. "
            "Lanza antes `construir_catalogo` para generarlo.",
            file=sys.stderr,
        )
        return 2

    programas = _cargar_catalogo(args.catalogo)
    docs = _documentos_a_notificar(programas)
    print(f"Documentos a notificar: {len(docs)}")

    remitente = os.getenv("EMAIL_FROM") or os.getenv("SMTP_USER", "")
    destinatario = os.getenv("EMAIL_TO", "")

    if args.dry_run:
        print(f"\n--- From: {remitente}")
        print(f"--- To:   {destinatario or '(sin destinatario)'}")
        print("--- Body (text):\n")
        print(_render_texto(docs))
        return 0

    if not destinatario:
        print(
            "✗ EMAIL_TO no está definido en .env. Añádelo o lanza con --dry-run.",
            file=sys.stderr,
        )
        return 2

    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    port = int(os.getenv("SMTP_PORT", "587"))
    if not all([host, user, password]):
        print(
            "✗ Faltan credenciales SMTP (SMTP_HOST, SMTP_USER, SMTP_PASS) en .env.",
            file=sys.stderr,
        )
        return 2

    msg = _construir_mensaje(docs, remitente or user, destinatario)
    _enviar(msg, host, port, user, password)
    print(f"✓ Notificación enviada a {destinatario}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
