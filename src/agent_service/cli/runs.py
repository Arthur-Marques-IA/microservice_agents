"""`kuro runs`: execuções registradas no Langfuse (via /observability) e feedback."""

from typing import Any

import typer
from rich.table import Table
from rich.tree import Tree

from agent_service.cli.common import call, console, emit, state

app = typer.Typer(help="Execuções: listar, ver trace, registrar score.")


def _render_runs(page: dict[str, Any]) -> None:
    table = Table(show_edge=False, header_style="bold")
    for column in ("início", "run_id", "agente", "status", "tokens", "latência"):
        table.add_column(column, no_wrap=True)
    for r in page["items"]:
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
    console.print(table)
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
