# Painel no terminal: `kuro dash`

`kuro dash` abre um painel em tela cheia no terminal. Mostra as execuções chegando ao vivo, o
trace de cada uma e o panorama do dashboard dos Logs, sem abrir o console web. Serve para quem
desligou a UI (`docker compose up -d` sem o profile `ui`) e para quem opera um serviço remoto
pelo terminal.

Como a CLI, é só mais um cliente da API: valem as mesmas flags e variáveis (`--url`/`KURO_API_URL`,
`KURO_API_KEY`, `KURO_CA_BUNDLE`), contra o serviço local ou numa VPS.

## Instalar e abrir

O painel usa o [Textual](https://textual.textualize.io) e vem no extra `tui`:

```bash
uv run --extra tui kuro dash
```

Opções:

| Opção | O que faz |
|---|---|
| `--agent r8`, `-a r8` | Começa filtrado num agente (vale também para o panorama) |
| `--interval 5` | Segundos entre as atualizações das execuções (padrão 3) |

O painel precisa de um terminal interativo. Num script ou sem TTY, use `kuro runs tail --json`.

## As duas abas

**Execuções** (tecla `1`): as 50 execuções mais recentes, atualizadas sozinhas. Mostra quando,
agente, versão da configuração, status, tokens, tempo, custo e o começo da mensagem. Os filtros
no topo:

- **agente**: digite o `agent_type` e tecle Enter;
- **status**: todos, só sucesso ou só erro;
- **sem testes**: esconde as execuções em `dry_run`, como os testes do Playground.

Enter numa linha abre o **trace**: mensagem e resposta, a árvore de spans (chamadas ao modelo e
às tools, com a entrada e a saída de cada uma) e as notas. Um span com erro já abre expandido.
Esc volta.

**Panorama** (tecla `2`): os mesmos números da página Logs do console
(`/observability/overview`):

- totais do período, com a variação contra o período anterior;
- uma linha por agente, com execuções, erros, tool falhando, tokens, custo e 👍/👎;
- as tools que estão falhando, com o tipo de falha e o status HTTP.

O período pode ser 24 horas, 7 dias ou 30 dias, com ou sem os testes. O panorama se atualiza a
cada minuto e exige uma chave de escopo admin; sem ela, a aba explica o que falta em vez de
quebrar.

## Teclas

| Tecla | Ação |
|---|---|
| `1` / `2` | Aba Execuções / Panorama |
| Enter | Abre o trace da execução selecionada |
| Esc | Volta do trace |
| `r` | Atualiza agora |
| `p` | Pausa e retoma a atualização automática (para ler com calma) |
| `q` | Sai |

## Desenvolvimento

O código fica em `src/agent_service/tui/app.py`. Toda chamada à API roda numa thread
(`@work(thread=True)`), para uma resposta lenta não congelar a tela. Os testes
(`tests/test_tui.py`) dirigem o app com o `Pilot` do Textual, contra um cliente falso:

```bash
uv run pytest tests/test_tui.py
```
