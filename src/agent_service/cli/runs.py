"""`kuro runs`: execuções registradas no Langfuse (via /observability) e feedback."""

import time
from typing import Any

import typer
from rich.table import Table
from rich.tree import Tree

from agent_service.cli.client import ApiError, ServiceUnavailable
from agent_service.cli.common import call, console, emit, fail_from, print_json, state

app = typer.Typer(help="Execuções: listar, acompanhar ao vivo, ver trace, resumir, registrar score.")


def _runs_table(rows: list[dict[str, Any]], *, header: bool = True) -> Table:
    table = Table(show_edge=False, header_style="bold", show_header=header)
    for column in ("início", "run_id", "agente", "status", "tokens", "latência"):
        table.add_column(column, no_wrap=True)
    for r in rows:
        status = "[green]ok[/]" if r["status"] == "success" else f"[red]{r['status']}[/]"
        latency = f"{r['latency_ms'] / 1000:.1f}s" if (r.get("latency_ms") or 0) > 0 else "—"
        table.add_row(
            str(r["started_at"])[5:16].replace("T", " "),
            r["run_id"],
            r["agent_type"],
            status,
            str(r["total_tokens"]),
            latency,
        )
    return table


def _render_runs(page: dict[str, Any]) -> None:
    console.print(_runs_table(page["items"]))
    if page.get("next_cursor"):
        console.print("[dim]há mais resultados — o cursor da próxima página vem em `--json` (next_cursor)[/]")


def _render_trace(trace: dict[str, Any]) -> None:
    run = trace["run"]
    console.print(f"[bold]{run['agent_type']}[/] [dim]run {run['run_id']} · {run['status']} · {run['total_tokens']} tokens[/]")
    console.print(f"[cyan]mensagem:[/] {run.get('message') or '—'}", highlight=False)
    console.print(f"[magenta]resposta:[/] {run.get('output') or '—'}", highlight=False)

    spans = trace["spans"]
    ids = {s["id"] for s in spans}
    root = Tree("[bold]spans[/]")
    nodes: dict[str, Tree] = {}
    for span in sorted(spans, key=lambda s: str(s["started_at"])):
        parent = nodes.get(span.get("parent_id")) if span.get("parent_id") in ids else root
        latency = f" {span['latency_ms']:.0f}ms" if span.get("latency_ms") else ""
        level = f" [red]{span['level']}[/]" if span["level"] not in ("DEFAULT", "DEBUG") else ""
        nodes[span["id"]] = (parent or root).add(f"{span['type'].lower()} [bold]{span['name']}[/][dim]{latency}[/]{level}")
    console.print(root)
    for score in trace.get("scores") or []:
        console.print(f"score {score['name']} = {score['value']} [dim]{score.get('comment') or ''}[/]")


@app.callback(invoke_without_command=True)
def runs(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:  # defaults explícitos: chamar direto não resolve os typer.Option
        list_runs(ctx, agent=None, status=None, session_id=None, user_id=None, limit=20, cursor=None)


@app.command("list")
def list_runs(
    ctx: typer.Context,
    agent: str | None = typer.Option(None, "--agent", "-a", help="Filtra por agent_type."),
    status: str | None = typer.Option(None, "--status", help="success | error"),
    session_id: str | None = typer.Option(None, "--session-id"),
    user_id: str | None = typer.Option(None, "--user-id"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100),
    cursor: str | None = typer.Option(None, "--cursor"),
) -> None:
    """Execuções mais recentes. Runs novos levam alguns segundos para aparecer."""
    st = state(ctx)
    page = call(
        st,
        st.client.list_runs,
        agent_type=agent,
        status=status,
        session_id=session_id,
        user_id=user_id,
        limit=limit,
        cursor=cursor,
    )
    emit(st, page, _render_runs)


@app.command("tail")
def tail_runs(
    ctx: typer.Context,
    agent: str | None = typer.Option(None, "--agent", "-a", help="Filtra por agent_type."),
    status: str | None = typer.Option(None, "--status", help="success | error"),
    interval: float = typer.Option(5.0, "--interval", min=1.0, help="Segundos entre as consultas."),
    limit: int = typer.Option(10, "--limit", "-n", min=1, max=100, help="Quantas execuções mostrar de saída."),
) -> None:
    """Acompanha as execuções ao vivo, como um `tail -f`. Ctrl+C para sair.

    É uma consulta repetida ao Langfuse, não um stream: um run aparece alguns
    segundos depois de terminar. Com `--json`, sai um objeto por execução."""
    st = state(ctx)
    seen: set[str] = set()
    first = True
    try:
        while True:
            try:
                page = st.client.list_runs(agent_type=agent, status=status, limit=limit if first else 100)
            except (ServiceUnavailable, ApiError) as exc:
                fail_from(st, exc)
            novos = [r for r in reversed(page["items"]) if r["run_id"] not in seen]
            seen.update(r["run_id"] for r in page["items"])
            if novos:
                if st.json_mode:
                    for run in novos:
                        print_json(run)
                else:
                    console.print(_runs_table(novos, header=first))
            first = False
            time.sleep(interval)
    except KeyboardInterrupt:
        if not st.json_mode:
            console.print()


@app.command("stats")
def stats(
    ctx: typer.Context,
    agent: str | None = typer.Option(None, "--agent", "-a", help="Filtra por agent_type."),
    prompt_version: int | None = typer.Option(None, "--prompt-version", min=1, help="Só uma versão do prompt."),
    status: str | None = typer.Option(None, "--status", help="success | error"),
    user_id: str | None = typer.Option(None, "--user-id"),
    session_id: str | None = typer.Option(None, "--session-id"),
) -> None:
    """Resumo das execuções: total, erros, tokens, custo e latência, com série diária."""
    st = state(ctx)
    result = call(
        st,
        st.client.run_stats,
        agent_type=agent,
        prompt_version=prompt_version,
        status=status,
        user_id=user_id,
        session_id=session_id,
    )
    emit(st, result, _render_stats)


def _render_stats(s: dict[str, Any]) -> None:
    custo = f"US$ {s['total_cost_usd']:.4f}" if s.get("total_cost_usd") else "—"
    latencia = f"{s['avg_latency_ms'] / 1000:.1f}s" if s.get("avg_latency_ms") else "—"
    por_status = ", ".join(f"{k}={v}" for k, v in sorted((s.get("status_counts") or {}).items())) or "—"
    console.print(
        f"[bold]{s['total_runs']}[/] execuções · {s['total_tokens']} tokens · {custo} · latência média {latencia}\n"
        f"[dim]por status: {por_status}[/]"
    )
    if s.get("buckets"):
        table = Table(show_edge=False, header_style="bold")
        for column in ("dia", "execuções", "erros", "tokens", "custo"):
            table.add_column(column, no_wrap=True)
        for b in s["buckets"]:
            table.add_row(
                b["date"],
                str(b["runs"]),
                f"[red]{b['errors']}[/]" if b["errors"] else "0",
                str(b["total_tokens"]),
                f"{b['cost_usd']:.4f}" if b.get("cost_usd") else "—",
            )
        console.print(table)
    # O agregado não varre o histórico inteiro; dizer isso evita conclusão errada.
    console.print(f"[dim]agregado sobre as {s['scanned']} execuções mais recentes[/]")


@app.command("show")
def show_run(ctx: typer.Context, run_id: str) -> None:
    """Trace completo de um run: mensagem, resposta, spans (LLM/tools) e scores."""
    st = state(ctx)
    emit(st, call(st, st.client.run_trace, run_id), _render_trace)


@app.command("score")
def score(
    ctx: typer.Context,
    run_id: str,
    value: float = typer.Argument(..., help="`feedback`: 1 positivo / 0 negativo; outros nomes: numérico."),
    name: str = typer.Option("feedback", "--name"),
    comment: str | None = typer.Option(None, "--comment"),
) -> None:
    """Registra uma avaliação para um run."""
    st = state(ctx)
    body = {"run_id": run_id, "name": name, "value": value, "comment": comment}
    emit(st, call(st, st.client.score, body), lambda s: console.print(f"[green]✓[/] {s['name']}={s['value']} em {s['run_id']}"))
