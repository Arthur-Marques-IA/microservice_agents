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
kuro --json agents apply -f - <<'EOF'
{"agent_type": "extrator-contrato", "name": "Extrator de contrato", "instructions": ["Extraia os campos do contrato."],
 "kind": "analysis", "response_schema": [{"name": "valor", "type": "number", "required": true},
                                          {"name": "prazo_dias", "type": "integer"}]}
EOF
kuro --json analyze extrator-contrato -f contrato.txt        # ou stdin; devolve {result: {...}}

# Feedback de conversa vira instrução (agentes conversacionais)
kuro --json chat suporte -m "meu wifi caiu"
kuro --json agents feedback suporte -m "deveria confirmar o CPF antes de dar detalhes"  # usa a sessão salva
kuro --json agents feedback suporte --show                    # nota atual (markdown), já em uso nas próximas respostas

# Tools (sem montar agente)
kuro --json tools list
kuro --json tools get calculator                # builtins listam as funções disponíveis
kuro --json tools invoke calculator --fn add -a a=2 -a b=3

# Execuções (Langfuse; um run leva alguns segundos para aparecer)
kuro --json runs list --agent suporte -n 5
kuro --json runs show <run_id>                  # mensagem, resposta, spans (LLM/tools), scores
kuro --json runs score <run_id> 1 --comment "resposta correta"

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
  Use isto para dado que **não pode passar pelo modelo** (CPF, id de conta): ele nem
  vê o parâmetro. O agente é obrigado a declarar o campo em `dependency_fields`.
- `"const"`: valor fixo em `value`.

`required` é cobrado antes da chamada HTTP; faltando um, a tool devolve o que faltou.
Para testar sem montar agente: `kuro tools invoke <tool> --args-json '{"x": 1}'`
(a rota aceita também `dependencies`, via `POST /tools/{nome}/invoke`).

O formato do `apply` é o mesmo do `POST /agents`: `agent_type`, `name`, `instructions`, `tools`,
`model_provider`, `model_id`, `model_credential_id`, `knowledge_collection`, `dependency_fields`,
`memory_backend` e `num_history_runs`. Editar `instructions` gera uma nova versão do prompt.
