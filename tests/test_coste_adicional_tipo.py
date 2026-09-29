"""Tests del validador tolerante de CosteAdicional.tipo.

El LLM devuelve ocasionalmente variantes ortográficas (outro, other) o
aliases interlingüísticos (transfer, insurance). El validator normaliza
esos valores en lugar de tirar el programa entero por ValidationError.
"""

import pytest

from src.models import CosteAdicional


def _coste(tipo_valor):
    return CosteAdicional(concepto="Test", tipo=tipo_valor)


# ---------------------------------------------------------------------------
# Valores canónicos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "canonico",
    [
        "traslado",
        "seguro",
        "deposito",
        "excursion",
        "lavanderia",
        "material",
        "servicio_menores",
        "pocket_money",
        "otro",
    ],
)
def test_valores_canonicos_se_preservan(canonico):
    assert _coste(canonico).tipo == canonico


# ---------------------------------------------------------------------------
# Variantes ortográficas y case-insensitivity
# ---------------------------------------------------------------------------


def test_outro_se_normaliza_a_otro():
    """Bug real: el LLM devolvió 'outro' y descartaba 7 programas Berlitz."""
    assert _coste("outro").tipo == "otro"


def test_other_se_normaliza_a_otro():
    assert _coste("other").tipo == "otro"


def test_case_insensitive():
    assert _coste("OTRO").tipo == "otro"
    assert _coste("Traslado").tipo == "traslado"


def test_espacios_se_recortan():
    assert _coste("  otro  ").tipo == "otro"


# ---------------------------------------------------------------------------
# Aliases interlingüísticos habituales
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "alias, canonico",
    [
        ("transfer", "traslado"),
        ("transport", "traslado"),
        ("transporte", "traslado"),
        ("insurance", "seguro"),
        ("deposit", "deposito"),
        ("damage_deposit", "deposito"),
        ("laundry", "lavanderia"),
        ("supplies", "material"),
        ("materials", "material"),
        ("unaccompanied_minor", "servicio_menores"),
        ("pocket", "pocket_money"),
        ("spending_money", "pocket_money"),
    ],
)
def test_alias_interlinguisticos(alias, canonico):
    assert _coste(alias).tipo == canonico


# ---------------------------------------------------------------------------
# Valores desconocidos y bordes
# ---------------------------------------------------------------------------


def test_valor_desconocido_cae_a_otro_sin_romper():
    """La información se preserva bajo categoría genérica en vez de tirar el programa."""
    assert _coste("una_categoria_que_no_existe").tipo == "otro"


def test_none_cae_a_otro():
    assert _coste(None).tipo == "otro"


def test_default_es_otro():
    # Sin especificar tipo, el default sigue siendo "otro"
    c = CosteAdicional(concepto="Test")
    assert c.tipo == "otro"
