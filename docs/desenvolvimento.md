# Desenvolvimento

```bash
# backend fora do Docker (precisa do postgres do compose rodando)
docker compose up -d postgres
uv sync                     # o grupo dev já traz o extra `observability`, usado nos testes
uv run uvicorn agent_service.main:app --app-dir src --reload

# frontend
cd frontend && npm install
AGENT_SERVICE_URL=http://127.0.0.1:58000 npm run dev

# schema: as migrações (Alembic) rodam sozinhas no startup; para aplicar à mão
uv run kuro-migrate
# mudança de schema nova = um arquivo em src/agent_service/migrations/versions/

# testes
uv run pytest
```

**Diagramas:** as fontes ficam em `docs/diagramas/*.mmd` e o README e os documentos exibem os
SVGs gerados a partir delas (uma versão clara e uma escura), porque o
renderizador de Mermaid do GitHub falha de forma intermitente. Depois de editar
um `.mmd`, regenere os dois SVGs:

```bash
npx -p @mermaid-js/mermaid-cli mmdc -i docs/diagramas/arquitetura.mmd -o docs/diagramas/arquitetura-claro.svg -t default -b transparent -c docs/diagramas/mermaid.json
npx -p @mermaid-js/mermaid-cli mmdc -i docs/diagramas/arquitetura.mmd -o docs/diagramas/arquitetura-escuro.svg -t dark -b transparent -c docs/diagramas/mermaid.json
uv run python docs/diagramas/fixar-tamanho.py    # grava o tamanho real, para o GitHub não esticar a imagem
```

## Documentação

A documentação mora em `docs/`, um assunto por arquivo; o `README.md` só apresenta
o projeto e aponta para eles, e o `AGENTS.md` fica curto, com as receitas da CLI.
Ao mudar algo que quem integra ou opera percebe, registre em
[notas-de-versao.md](notas-de-versao.md) (ver as regras no fim do arquivo).

| Para saber sobre | Leia |
|---|---|
| agentes, tools, RAG, memória, modelos, anexos | [conceitos.md](conceitos.md) |
| o shell, os comandos, o uso por agentes de IA | [cli.md](cli.md) |
| o console web | [console.md](console.md) |
| runs, trace store, Langfuse, shadow | [observabilidade.md](observabilidade.md) |
| componentes e fluxo de uma mensagem | [arquitetura.md](arquitetura.md) |
| configuração, HTTPS, deploy, segurança | [operacao.md](operacao.md) |
| integrar outro sistema ao Kuro | [integracao.md](integracao.md) |

Os links relativos entre documentos são conferidos por `tests/test_docs_links.py`:
um link que aponte para um arquivo ou título que não existe quebra o CI.
