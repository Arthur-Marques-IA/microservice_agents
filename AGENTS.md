# Operando o agent-service pelo terminal (para agentes de IA)

Use a CLI `kuro` em vez de `curl` para criar, editar e testar agentes, tools e
execuções. Ela fala com a API HTTP do serviço, que roda via Docker em
`http://127.0.0.1:58000` (você pode trocar a URL com `--url` ou `KURO_API_URL`).

```bash
uv run kuro health --json          # rode primeiro: serviço, Langfuse, provedores
uv run kuro <comando> --help       # ajuda de qualquer comando
```

## Convenções

- **Sempre use `--json`** (aceito em qualquer posição: `kuro agents list --json`).
  A saída de dados vai para o stdout; os erros saem em JSON no stderr (`{"error", "status", "detail"}`).
- **Códigos de saída:** `0` indica sucesso. `1` indica que a operação falhou: erro da API, tool com `ok: false` ou erro durante o chat.
  `2` indica uso incorreto (argumento ou dependency faltando). `3` indica que o serviço está inacessível.
- **Nada fica esperando entrada sem TTY.** Seletores e prompts só aparecem em terminal interativo;
  se faltar algo, o comando falha. Para garantir isso, use `--no-input` ou `KURO_NO_INPUT=1`.
- Valores `chave=valor` são lidos como JSON quando possível (`n=3`, `ativo=true`, `tags='["a"]'`).

## Receitas

```bash
# Agentes
kuro --json agents list
kuro --json agents get suporte
kuro --json agents get suporte --editable > suporte.json   # só os campos editáveis
kuro --json agents apply -f suporte.json                  # cria ou atualiza (também aceita -f - para stdin)
kuro --json agents set suporte num_history_runs=5 tools='["calculator"]'   # altera só esses campos
kuro --json agents versions suporte
kuro --json agents rollback suporte 3 --yes                # reaplica as instructions da v3 (vira uma versão nova)
kuro --json agents delete suporte --yes

# Testar um agente (a sessão fica salva por agente, então mensagens seguidas continuam a conversa)
kuro --json chat suporte -m "meu wifi caiu" -d cpf=12345678900
kuro --json chat suporte -m "recomeçar" --new-session
echo "mensagem longa" | kuro --json chat suporte
# retorna {content, run_id, trace_id, session_id, usage, error}

# Anexos: imagem, áudio, vídeo ou arquivo (PDF, DOCX, CSV, TXT...) direto ao modelo
kuro --json chat suporte -m "o que tem nessa foto?" --attach foto.png       # -a, repetível
kuro --json analyze extrator -a contrato.pdf                                # PDF sem extrair texto antes
# Pela API: `attachments: [{content_base64|url, mime_type, filename}]` no /chat e no /analyze.
# O modelo do agente precisa suportar o tipo (ex.: Gemini). Limite: MAX_ATTACHMENT_MB (20).
# No REPL do chat, os anexos vão só na 1ª mensagem. Em conversas, o anexo fica no histórico da
# sessão (Postgres) e volta como contexto nos turnos seguintes — para anexos grandes ou
# recorrentes prefira `analyze` (sem sessão).

# Agentes analistas (one-shot, sem sessão) — kind="analysis"
# `document` é texto: -f aceita qualquer arquivo de texto (inclusive .json) e stdin também.
# O response_schema aceita campos simples (string/integer/number/boolean) e compostos:
# "object" (exige `fields`) e "array" (exige `items`). Sem fields/items o schema sai inválido
# para o provedor, então isso é recusado com 422 no cadastro.
kuro --json agents apply -f - <<'EOF'
{"agent_type": "extrator-contrato", "name": "Extrator de contrato", "instructions": ["Extraia os campos do contrato."],
 "kind": "analysis", "response_schema": [{"name": "valor", "type": "number", "required": true},
                                          {"name": "cliente", "type": "object",
                                           "fields": [{"name": "nome", "type": "string", "required": true}]},
                                          {"name": "parcelas", "type": "array",
                                           "items": {"type": "object", "fields": [
                                               {"name": "numero", "type": "integer", "required": true},
                                               {"name": "valor", "type": "number", "required": true}]}}]}
EOF
kuro --json analyze extrator-contrato -f contrato.txt        # ou stdin; devolve {result: {...}}
cat conversa.json | kuro --json analyze classificador        # texto/JSON por stdin
# Em kind="analysis": `num_history_runs` e `memory_backend` dão 422 (não fazem nada num
# agente one-shot) e a nota de feedback não se aplica — ajuste as instructions.
# Teto do texto de entrada: MAX_INPUT_CHARS (200000 caracteres), no /chat e no /analyze.

# Feedback de conversa vira instrução (agentes conversacionais)
kuro --json chat suporte -m "meu wifi caiu"
kuro --json agents feedback suporte -m "deveria confirmar o CPF antes de dar detalhes"  # usa a sessão salva
kuro --json agents feedback suporte --show                    # nota atual (markdown), já em uso nas próximas respostas

# Tools (sem montar agente)
kuro --json tools list
kuro --json tools get calculator                # builtins listam as funções disponíveis
kuro --json tools get cep --editable > cep.json # só os campos editáveis
kuro --json tools apply -f cep.json             # cria (precisa de tool_name e kind) ou atualiza
kuro --json tools set cep enabled=false         # altera só esses campos (kind não muda)
kuro --json tools delete cep --yes              # trava se algum agente usa a tool
kuro --json tools invoke calculator --fn add -a a=2 -a b=3

# Execuções (Langfuse; um run leva alguns segundos para aparecer)
kuro --json runs list --agent suporte -n 5
kuro --json runs show <run_id>                  # mensagem, resposta, spans (LLM/tools), scores
kuro --json runs score <run_id> 1 --comment "resposta correta"
kuro --json runs stats --agent suporte          # total, erros, tokens, custo e série diária
kuro --json runs tail --agent suporte           # acompanha ao vivo; um objeto JSON por execução, Ctrl+C sai

# Conversas guardadas (Postgres — funciona mesmo com o Langfuse desligado)
# O user_id é o mesmo do chat: `cli` por padrão, ou KURO_USER_ID.
kuro --json sessions list --agent suporte
kuro --json sessions show <session_id>          # transcrição: cada mensagem, a resposta e os tokens
kuro --json sessions delete <session_id> --yes  # apaga a conversa e as execuções dela (não tem volta)

# Integração: como outro módulo chama este agente (endpoint, cURL, dependências obrigatórias)
kuro --json agents integrate suporte

# Bases de conhecimento (RAG) — o agente consulta a que estiver em knowledge_collection
kuro --json collections list
kuro --json collections create manuais --label "Manuais do produto"
cat manual.txt | kuro --json collections add manuais --title "Manual v2"
kuro --json collections search manuais "prazo de garantia"   # o mesmo que o agente enxerga
kuro --json agents set suporte knowledge_collection=manuais

# Modelos: provedores suportados e credenciais
kuro --json providers list
kuro --json credentials list --provider google
kuro --json credentials test <credential_id>    # valida a chave sem gastar tokens; sai com 1 se falhar
KEY=... kuro --json credentials add -p google -l "Produção" --api-key-env KEY
```

## Tools: de onde vem cada parâmetro

Cada parâmetro de uma tool `kind="api"` declara um `source`:

- `"model"` (padrão): o modelo preenche — é o único que aparece no schema dele.
- `"dependency"`: o servidor injeta `dependencies[<campo>]` da requisição do `/chat`.
  Use isto para dado que **o modelo não pode escolher** (CPF, id de conta): o parâmetro
  fica fora do schema da tool, então o modelo não consegue inventar nem trocar o valor.
  O agente é obrigado a declarar o campo em `dependency_fields`.
  Atenção: todas as `dependencies` enviadas também entram no contexto do modelo. Isso
  protege qual valor vai na chamada, mas não esconde o valor do provedor de LLM.
- `"const"`: valor fixo em `value`.

`required` é cobrado antes da chamada HTTP; faltando um, a tool devolve o que faltou.

Toda tool só alcança endereços **públicos**: o destino é resolvido e conferido antes de cada
chamada (com a URL já montada, porque um parâmetro `location="path"` pode compor o host). Salvar
uma tool apontando para dentro falha com 422; uma chamada recusada devolve o motivo ao modelo.
Para um serviço interno legítimo, libere o host em `TOOL_EGRESS_ALLOWLIST`. O mesmo vale para o
`httpx` das tools `kind="python"`.
Para testar sem montar agente: `kuro tools invoke <tool> --args-json '{"x": 1}'`
(a rota aceita também `dependencies`, via `POST /tools/{nome}/invoke`).

O formato do `apply` é o mesmo do `POST /agents`: `agent_type`, `name`, `instructions`, `tools`,
`model_provider`, `model_id`, `model_credential_id`, `knowledge_collection`, `dependency_fields`,
`memory_backend`, `num_history_runs`, `kind` e `response_schema`. Editar `instructions` gera uma nova versão do prompt.
