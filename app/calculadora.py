"""
Aplicação de exemplo do laboratório DevOps + GenAI.

Módulo de cálculos simples de uma loja (preço, desconto, frete e média).
ATENÇÃO: a função `aplicar_desconto` contém um ERRO INTENCIONAL para que
o pipeline de CI falhe e o agente de IA generativa possa diagnosticar a falha.
"""


def somar(a: float, b: float) -> float:
    return a + b


def subtrair(a: float, b: float) -> float:
    return a - b


def multiplicar(a: float, b: float) -> float:
    return a * b


def dividir(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("Divisão por zero não é permitida")
    return a / b


def media(valores: list[float]) -> float:
    if not valores:
        raise ValueError("A lista de valores não pode estar vazia")
    return sum(valores) / len(valores)


def aplicar_desconto(preco: float, percentual: float) -> float:
    """Retorna o preço final após aplicar um desconto percentual (0 a 100)."""
    if percentual < 0 or percentual > 100:
        raise ValueError("O percentual deve estar entre 0 e 100")
    return round(preco * (1 - percentual / 100), 2)


def calcular_frete(peso_kg: float) -> float:
    """Frete fixo de R$ 10,00 até 1 kg + R$ 5,00 por kg adicional."""
    if peso_kg <= 0:
        raise ValueError("O peso deve ser maior que zero")
    if peso_kg <= 1:
        return 10.0
    return round(10.0 + (peso_kg - 1) * 5.0, 2)
