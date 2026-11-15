# DevOps + IA Generativa — Diagnóstico de falhas em CI/CD

Projeto Integrador (Unidade 5): uma aplicação Python com **erro intencional**, **testes automatizados** com `pytest`, um **pipeline CI/CD no GitHub Actions** e um **agente de IA generativa** que lê os logs da falha e sugere a correção.

## Estrutura

```
.
├── app/
│   └── calculadora.py        # aplicação (contém o erro intencional em aplicar_desconto)
├── tests/
│   └── test_calculadora.py   # 11 testes automatizados (pytest)
├── ai_agent/
│   └── analisar_logs.py      # agente de IA: lê o log, mascara segredos, chama o LLM, gera relatório
├── .github/workflows/ci.yml  # pipeline: testes -> diagnostico_ia
└── requirements.txt
```

## Como o pipeline funciona

| Ordem | Job | O que faz |
|---|---|---|
| 1 | `testes` | Instala dependências, roda `pytest` e salva `logs/pytest.log` como artefato (`logs-testes`) — inclusive quando falha. |
| 2 | `diagnostico_ia` | Roda **somente se os testes falharem** (`if: failure()`). Baixa o log, mascara segredos, envia para o LLM, publica o relatório na página de resumo da execução (*Summary*) e como artefato (`relatorio-ia`). |

O agente usa apenas a biblioteca padrão do Python e funciona com:
- **Google Gemini** — segredo `GEMINI_API_KEY` (opcional: `GEMINI_MODEL`, padrão `gemini-2.5-flash`). Há plano gratuito em <https://aistudio.google.com/apikey>.
- **OpenAI** — segredo `OPENAI_API_KEY` (opcional: `OPENAI_MODEL`, padrão `gpt-4o-mini`).
- **Sem chave** — faz uma análise heurística local (por regras), para o fluxo continuar demonstrável.

## Passo a passo

1. **Clone o repositório**:
   ```bash
   git clone https://github.com/LucasCruellas/devops-genai-lab.git
   cd devops-genai-lab
   ```
2. **Configure a chave da IA** em *Settings → Secrets and variables → Actions → New repository secret*:
   - Name: `GEMINI_API_KEY` (ou `OPENAI_API_KEY`)
   - Segredos do GitHub já são mascarados nos logs. Nunca coloque a chave no código.
3. **Acompanhe o pipeline** na aba *Actions*: o job `Testes automatizados` falha (2 de 11 testes) e o job `Diagnóstico com IA generativa` roda em seguida.
4. **Leia o diagnóstico** na página da execução (seção *Summary*) ou baixe o artefato `relatorio-ia`.
5. **Valide e aplique a correção** em `app/calculadora.py`:
   ```python
   return round(preco * (1 - percentual / 100), 2)
   ```
   Rode `python -m pytest -v` localmente e faça commit/push. O pipeline fica verde e o job de IA é pulado (*skipped*).

## Rodando localmente

```bash
pip install -r requirements.txt
mkdir -p logs
python -m pytest -v > logs/pytest.log 2>&1
python ai_agent/analisar_logs.py logs/pytest.log logs/relatorio_ia.md
```

## Erro intencional

`aplicar_desconto(preco, percentual)` subtraía o percentual como se fosse valor em reais (`preco - percentual`) em vez de calcular a porcentagem. Exemplo: 10% de R$ 200,00 retornava 190 em vez de 180. O histórico de commits mostra a execução com falha, o diagnóstico e a correção.

## Segurança

- O agente **mascara tokens, senhas e chaves** (GitHub `ghp_`/`github_pat_`, GitLab `glpat-`, OpenAI `sk-`, Google `AIza…`, `Bearer`, `password=` etc.) antes de enviar o log ao LLM.
- O agente **nunca quebra o pipeline** (sempre sai com código 0) e, se a API falhar, cai para a análise heurística.
- As sugestões da IA são **recomendações**: devem ser revisadas e validadas por uma pessoa antes de serem aplicadas.
