import pytest

from app.calculadora import (
    aplicar_desconto,
    calcular_frete,
    dividir,
    media,
    multiplicar,
    somar,
    subtrair,
)


def test_somar():
    assert somar(2, 3) == 5


def test_subtrair():
    assert subtrair(10, 4) == 6


def test_multiplicar():
    assert multiplicar(3, 4) == 12


def test_dividir():
    assert dividir(10, 2) == 5


def test_dividir_por_zero():
    with pytest.raises(ValueError):
        dividir(10, 0)


def test_media():
    assert media([2, 4, 6]) == 4


def test_media_lista_vazia():
    with pytest.raises(ValueError):
        media([])


def test_aplicar_desconto_10_porcento():
    # 10% de desconto sobre R$ 200,00 deve resultar em R$ 180,00
    assert aplicar_desconto(200, 10) == 180.0


def test_aplicar_desconto_50_porcento():
    # 50% de desconto sobre R$ 80,00 deve resultar em R$ 40,00
    assert aplicar_desconto(80, 50) == 40.0


def test_aplicar_desconto_invalido():
    with pytest.raises(ValueError):
        aplicar_desconto(100, 150)


def test_calcular_frete():
    assert calcular_frete(0.5) == 10.0
    assert calcular_frete(3) == 20.0
