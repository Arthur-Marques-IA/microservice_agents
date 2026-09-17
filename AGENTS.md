# Operando o agent-service pelo terminal (para agentes de IA)

Use a CLI `kuro` em vez de `curl` para criar, editar e testar agentes, tools e
execuções. Ela fala com a API HTTP do serviço, que roda via Docker em
`http://localhost:58000` (você pode trocar a URL com `--url` ou `KURO_API_URL`).

```bash
uv run kuro health --json          # rode primeiro: serviço, Langfuse, provedores
uv run kuro <comando> --help       # ajuda de qualquer comando
```

## Convenções

- **Sempre use `--json`** (é uma opção global; vem antes do comando: `kuro --json agents list`).
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

# Tools (sem montar agente)
kuro --json tools list
kuro --json tools get calculator                # builtins listam as funções disponíveis
kuro --json tools invoke calculator --fn add -a a=2 -a b=3

# Execuções (Langfuse; um run leva alguns segundos para aparecer)
kuro --json runs list --agent suporte -n 5
kuro --json runs show <run_id>                  # mensagem, resposta, spans (LLM/tools), scores
kuro --json runs score <run_id> 1 --comment "resposta correta"

# Provedores de modelo
kuro --json providers list
```

O formato do `apply` é o mesmo do `POST /agents`: `agent_type`, `name`, `instructions`, `tools`,
`model_provider`, `model_id`, `dependency_fields`, `memory_backend` e `num_history_runs`.
Editar `instructions` gera uma nova versão do prompt.
