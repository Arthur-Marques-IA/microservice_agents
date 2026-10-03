# Console web

| Página | O que tem |
|---|---|
| **Playground** `/chat` | conversa em streaming com qualquer agente conversacional; URL por conversa, histórico reidratado; edição de `dependencies`; anexos; 👍/👎 — e o 👎 pergunta o que mudar e ensina o agente |
| **Análise** `/analyze` | roda um agente analista: documento (ou anexo) entra, o objeto do `response_schema` sai |
| **Agentes** `/agents` | configuração (só os campos alterados vão no `PUT`), tipo do agente, parâmetros de geração e tempo limite, editor da saída estruturada com valores permitidos (`enum`); **Versões** (configuração inteira e prompt com diff) e **Promover**; **Aprendizado** (as regras vindas de feedback, editáveis, com histórico e rollback); execuções, com a concordância do shadow nos analistas; conversas e a aba Integração com o contrato vindo do backend |
| **Tools** `/tools` | criação e edição dos três tipos, com formulário próprio por tipo, campos de dentro de parâmetros `object`/`array`, botão **Testar** (com `dependencies`) e origem de cada parâmetro |
| **Conhecimento** `/knowledge` | documentos com status, escolha do embedder na criação, upload por texto ou arquivo em qualquer coleção (URL só na padrão), teste de busca semântica |
| **Modelos** `/models` | credenciais por provedor, teste de chave |
| **Logs** `/logs` | sessões e execuções de todos os agentes, KPIs, gráfico diário; cada sessão e cada run abrem em detalhe |
| **Trace** `/runs/[id]` | cascata de spans (agente → modelo → tools), versão da configuração, tokens, custo, avaliações, metadata de quem chamou e a referência do shadow |

Atalhos: `Ctrl/⌘+K` (paleta de comandos) e `Ctrl/⌘+B` (recolher a sidebar).
Tema claro, escuro ou do sistema.

O navegador só fala com o Next.js. Os Route Handlers em `frontend/src/app/api/**`
fazem proxy para o `agent-service` usando `AGENT_SERVICE_URL`, que só existe no
servidor: sem CORS e sem expor o backend. Não há login no MVP: o `user_id` do
console fica no `localStorage` do navegador.
