"""
Agente de IA generativa para diagnóstico de falhas em pipelines CI/CD.

Fluxo:
  1. Lê o log da execução dos testes (gerado pelo job de testes do pipeline).
  2. Mascara possíveis segredos (tokens, senhas, chaves) antes de enviar à IA.
  3. Extrai o trecho relevante (falhas + resumo) e o código-fonte citado no traceback.
  4. Envia para um LLM (Google Gemini ou OpenAI) pedindo diagnóstico e correção.
  5. Salva o relatório em Markdown (artefato do pipeline).

Se nenhuma chave de API estiver configurada, executa uma análise heurística
local (sem IA) para que o pipeline continue demonstrando o fluxo.

Uso:
  python ai_agent/analisar_logs.py logs/pytest.log logs/relatorio_ia.md

Variáveis de ambiente (no GitHub: Settings > Secrets and variables > Actions > New repository secret):
  GEMINI_API_KEY  -> usa o Google Gemini (modelo em GEMINI_MODEL)
  OPENAI_API_KEY  -> usa a OpenAI (modelo em OPENAI_MODEL)
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MAX_LOG_CHARS = 12000
MAX_SOURCE_CHARS = 6000

PADROES_SEGREDOS = [
    r"(?i)(api[_-]?key|token|secret|password|senha|passwd)\s*[:=]\s*\S+",
    r"gh[pousr]_[A-Za-z0-9]{30,}",         # tokens do GitHub
    r"github_pat_[A-Za-z0-9_]{30,}",       # token fino do GitHub
    r"glpat-[A-Za-z0-9_\-]{20,}",          # token pessoal do GitLab
    r"sk-[A-Za-z0-9_\-]{20,}",             # chave OpenAI
    r"AIza[0-9A-Za-z_\-]{35}",             # chave Google
    r"(?i)bearer\s+[A-Za-z0-9._\-]+",
]

PROMPT_SISTEMA = (
    "Você é um engenheiro DevOps sênior especialista em Python e pipelines CI/CD (GitHub Actions). "
    "Analise logs de pipelines com falha e produza diagnósticos objetivos, "
    "sempre em português do Brasil. Não invente informações que não estejam "
    "no log ou no código; se não tiver certeza, diga isso explicitamente."
)

PROMPT_USUARIO = """O pipeline de CI falhou. Abaixo estão o log dos testes automatizados e o código-fonte citado no traceback.

Responda em Markdown com exatamente estas seções:
## Resumo da falha
## Causa raiz provável
(indique arquivo, função e linha)
## Correção sugerida
(mostre o trecho corrigido em bloco de código)
## Como validar a correção
## Nível de confiança e riscos
(alto/médio/baixo e o que um humano deve revisar antes de aplicar)

### LOG DOS TESTES
```
{log}
```

### CÓDIGO-FONTE RELACIONADO
{codigo}
"""


def mascarar_segredos(texto: str) -> str:
    for padrao in PADROES_SEGREDOS:
        texto = re.sub(padrao, "[SEGREDO_MASCARADO]", texto)
    return texto


def extrair_trecho_relevante(log: str) -> str:
    """Mantém a seção de FAILURES/ERRORS e o resumo final do pytest."""
    inicio = None
    for marcador in ("= FAILURES =", "= ERRORS ="):
        pos = log.find(marcador)
        if pos != -1:
            inicio = pos if inicio is None else min(inicio, pos)
    trecho = log[inicio:] if inicio is not None else log
    if len(trecho) > MAX_LOG_CHARS:
        trecho = trecho[:MAX_LOG_CHARS // 2] + "\n...[log truncado]...\n" + trecho[-MAX_LOG_CHARS // 2:]
    return trecho


def coletar_codigo_fonte(log: str) -> str:
    """Busca arquivos .py do projeto citados no traceback e inclui o conteúdo."""
    arquivos = []
    for caminho in re.findall(r"([\w./\\-]+\.py):\d+", log):
        caminho = caminho.replace("\\", "/")
        if caminho not in arquivos and Path(caminho).is_file() and "site-packages" not in caminho:
            arquivos.append(caminho)
    # Também inclui o módulo importado pelos testes (app/), onde o bug costuma estar
    for py in sorted(Path("app").glob("*.py")) if Path("app").is_dir() else []:
        if str(py) not in arquivos and py.name != "__init__.py":
            arquivos.append(str(py))

    partes, total = [], 0
    for caminho in arquivos:
        conteudo = Path(caminho).read_text(encoding="utf-8", errors="replace")
        numerado = "\n".join(f"{i:>4}: {linha}" for i, linha in enumerate(conteudo.splitlines(), 1))
        bloco = f"**{caminho}**\n```python\n{numerado}\n```\n"
        if total + len(bloco) > MAX_SOURCE_CHARS:
            break
        partes.append(bloco)
        total += len(bloco)
    return "\n".join(partes) or "(nenhum arquivo de código encontrado)"


def _post_json(url: str, payload: dict, headers: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chamar_gemini(prompt: str) -> tuple[str, str]:
    modelo = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": PROMPT_SISTEMA}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    dados = _post_json(url, payload, {"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    texto = "".join(p.get("text", "") for p in dados["candidates"][0]["content"]["parts"])
    return texto, f"Google Gemini ({modelo})"


def chamar_openai(prompt: str) -> tuple[str, str]:
    modelo = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": modelo,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": prompt},
        ],
    }
    dados = _post_json(
        "https://api.openai.com/v1/chat/completions",
        payload,
        {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
    )
    return dados["choices"][0]["message"]["content"], f"OpenAI ({modelo})"


def analise_heuristica(log: str) -> tuple[str, str]:
    """Fallback sem IA: regras simples para classificar a falha."""
    falhas = re.findall(r"^FAILED (\S+?)(?: - (.*))?$", log, flags=re.M)
    erros_e = re.findall(r"^E\s+(.*)$", log, flags=re.M)
    localizacoes = re.findall(r"^([\w./\\-]+\.py):(\d+): (\w+)", log, flags=re.M)

    categorias = {
        "AssertionError": "Erro de lógica: o valor retornado pela função difere do esperado pelo teste.",
        "ModuleNotFoundError": "Dependência ausente: verifique o requirements.txt e a etapa de instalação.",
        "ImportError": "Falha de importação: nome de função/módulo incorreto ou dependência ausente.",
        "SyntaxError": "Erro de sintaxe no código-fonte.",
        "TypeError": "Tipo de dado incorreto passado ou retornado por uma função.",
        "ZeroDivisionError": "Divisão por zero sem tratamento.",
    }
    tipo = next((t for t in categorias if t in log), None)

    linhas = ["## Resumo da falha"]
    if falhas:
        linhas.append(f"{len(falhas)} teste(s) falharam:")
        linhas += [f"- `{nome}` — {msg or 'sem mensagem'}" for nome, msg in falhas]
    else:
        linhas.append("Nenhum teste marcado como FAILED foi encontrado no log.")
    linhas += ["", "## Causa raiz provável", categorias.get(tipo, "Não foi possível classificar automaticamente.")]
    if localizacoes:
        linhas.append("Locais citados no traceback:")
        linhas += [f"- `{arq}`, linha {ln} ({ex})" for arq, ln, ex in dict.fromkeys(localizacoes)]
    if erros_e:
        linhas += ["", "Mensagens de erro (linhas `E`):", "```"] + erros_e[:10] + ["```"]
    linhas += [
        "",
        "## Correção sugerida",
        "Compare o valor esperado pelo teste com o retornado pela função citada e revise a fórmula. "
        "Configure `GEMINI_API_KEY` ou `OPENAI_API_KEY` para obter uma sugestão de código gerada por IA.",
        "",
        "## Como validar a correção",
        "Rode `pytest -v` localmente e faça um novo commit; o job de testes deve passar.",
        "",
        "## Nível de confiança e riscos",
        "Baixo/médio — análise baseada apenas em regras, sem IA generativa.",
    ]
    return "\n".join(linhas), "Análise heurística local (sem IA)"


def url_pipeline() -> str:
    if os.getenv("GITHUB_RUN_ID"):
        return f"{os.getenv('GITHUB_SERVER_URL')}/{os.getenv('GITHUB_REPOSITORY')}/actions/runs/{os.getenv('GITHUB_RUN_ID')}"
    return "execução local"


def main() -> int:
    caminho_log = Path(sys.argv[1] if len(sys.argv) > 1 else "logs/pytest.log")
    caminho_saida = Path(sys.argv[2] if len(sys.argv) > 2 else "logs/relatorio_ia.md")

    if not caminho_log.is_file():
        print(f"[agente-ia] Log não encontrado: {caminho_log}")
        return 0

    log_bruto = caminho_log.read_text(encoding="utf-8", errors="replace")
    log = mascarar_segredos(extrair_trecho_relevante(log_bruto))
    codigo = mascarar_segredos(coletar_codigo_fonte(log_bruto))
    prompt = PROMPT_USUARIO.format(log=log, codigo=codigo)

    try:
        if os.getenv("GEMINI_API_KEY"):
            analise, motor = chamar_gemini(prompt)
        elif os.getenv("OPENAI_API_KEY"):
            analise, motor = chamar_openai(prompt)
        else:
            analise, motor = analise_heuristica(log_bruto)
            motor += " — nenhuma chave de API configurada"
    except (urllib.error.URLError, KeyError, IndexError, TimeoutError, json.JSONDecodeError) as exc:
        detalhe = exc.read().decode("utf-8", "replace")[:500] if isinstance(exc, urllib.error.HTTPError) else ""
        print(f"[agente-ia] Falha ao chamar a API de IA: {exc} {mascarar_segredos(detalhe)}")
        analise, motor = analise_heuristica(log_bruto)
        motor += " — fallback após erro na API"

    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    relatorio = (
        "# Relatório de diagnóstico do pipeline (IA generativa)\n\n"
        f"- **Gerado em:** {agora}\n"
        f"- **Motor de análise:** {motor}\n"
        f"- **Pipeline:** {url_pipeline()}\n"
        f"- **Commit:** {os.getenv('GITHUB_SHA', '-')[:7]}\n\n"
        "> ⚠️ Sugestões geradas automaticamente. Revise e valide antes de aplicar.\n\n"
        f"{analise}\n"
    )
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    caminho_saida.write_text(relatorio, encoding="utf-8")
    print(relatorio)
    # No GitHub Actions, publica o relatório na página de resumo da execução
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as resumo:
            resumo.write(relatorio)
    return 0  # o agente nunca deve quebrar o pipeline


if __name__ == "__main__":
    sys.exit(main())
