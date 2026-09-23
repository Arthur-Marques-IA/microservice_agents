"""`kuro sessions`: as conversas guardadas — listar, ler a transcrição, apagar.

Usa as rotas de sessão do AgentOS (Postgres), não `/observability/sessions`:
a conversa em si não depende do Langfuse, então isto funciona também no modo
só-terminal, em que o tracing está desligado.

O `user_id` é o mesmo de `kuro chat` (`cli` por padrão, ou `KURO_USER_ID`):
sem ele a listagem traria as conversas de todo mundo, inclusive as do console.
O filtro por agente vai em `component_id`, que casa com o `agent_type` porque
`agents/base.py` cria o `Agent` do Agno com `id=agent_type`.
"""

import os
from typing import Any

import typer
from rich.table import Table

from agent_service.cli.common import EXIT_USAGE, call, console, emit, fail, state

app = typer.Typer(help="Sessões (conversas): listar, ver a transcrição, apagar.")

_USER_ID = typer.Option(
    "cli", "--user-id", "-u", envvar="KURO_USER_ID", help="Dono das conversas — o mesmo de `kuro chat`."
)


def _render_list(page: dict[str, Any]) -> None:
    items = page.get("data") or []
    if not items:
        console.print("Nenhuma conversa para este user_id — converse com `kuro chat <agente>` ou troque `--user-id`.")
        return
    table = Table(show_edge=False, header_style="bold")
    for column in ("atualizada", "session_id", "agente", "título", "tokens"):
        table.add_column(column, no_wrap=True)
    for s in items:
        when = str(s.get("updated_at") or s.get("created_at") or "")[5:16].replace("T", " ")
        title = (s.get("session_name") or "—")[:48]
        table.add_row(
            when,
            f"[cyan]{s['session_id']}[/]",
            s.get("agent_id") or "—",
            title,
            str(s.get("total_tokens") or "—"),
        )
    console.print(table)
    meta = page.get("meta") or {}
    if (meta.get("total_pages") or 0) > 1:
        console.print(f"[dim]página {meta.get('page')} de {meta['total_pages']} — use --page[/]")


def _render_transcript(runs: list[dict[str, Any]]) -> None:
    if not runs:
        console.print("[dim]sessão sem execuções[/]")
        return
    for run in runs:
        console.print(f"[bold cyan]você>[/] {run.get('run_input') or '—'}", highlight=False)
        content = run.get("content")
        if not isinstance(content, str):
            content = "" if content is None else str(content)
        console.print(f"[bold magenta]agente>[/] {content or '—'}", highlight=False)
        metrics = run.get("metrics") or {}
        parts = [f"run {run['run_id']}"]
        if metrics.get("total_tokens"):
            parts.append(f"{metrics['total_tokens']} tokens")
        console.print(f"[dim]{' · '.join(parts)}[/]\n", highlight=False)


@app.callback(invoke_without_command=True)
def sessions(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:  # defaults explícitos: chamar direto não resolve os typer.Option
        list_sessions(ctx, agent=None, user_id=os.environ.get("KURO_USER_ID") or "cli", limit=20, page=1)


@app.command("list")
def list_sessions(
    ctx: typer.Context,
    agent: str | None = typer.Option(None, "--agent", "-a", help="Filtra por agent_type."),
    user_id: str = _USER_ID,
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100),
    page: int = typer.Option(1, "--page", min=1),
) -> None:
    """Conversas de um user_id, da mais recente para a mais antiga."""
    st = state(ctx)
    result = call(
        st, st.client.list_sessions, user_id=user_id, component_id=agent, limit=limit, page=page
    )
    emit(st, result, _render_list)


@app.command("show")
def show_session(
    ctx: typer.Context,
    session_id: str,
    user_id: str = _USER_ID,
) -> None:
    """Transcrição da conversa: cada mensagem, a resposta e os tokens do run."""
    st = state(ctx)
    emit(st, call(st, st.client.session_runs, session_id, user_id), _render_transcript)


@app.command("rename")
def rename_session(ctx: typer.Context, session_id: str, name: str) -> None:
    """Dá um nome à conversa — é o que aparece na lista, aqui e no console."""
    st = state(ctx)
    emit(
        st,
        call(st, st.client.rename_session, session_id, name),
        lambda _: console.print(f"[green]✓[/] sessão {session_id} renomeada"),
    )


@app.command("delete")
def delete_session(
    ctx: typer.Context,
    session_id: str,
    user_id: str = _USER_ID,
    yes: bool = typer.Option(False, "--yes", "-y", help="Não pede confirmação (obrigatório sem TTY)."),
) -> None:
    """Apaga a conversa e todas as suas execuções. Não tem volta.

    Os traces do Langfuse não são afetados: `kuro runs` continua mostrando o
    que aconteceu."""
    st = state(ctx)
    if not yes:
        if not st.interactive:
            fail(st, "confirme com --yes para apagar sem TTY", EXIT_USAGE)
        if not typer.confirm(f"Apagar a conversa {session_id!r} e todo o histórico dela?"):
            raise typer.Exit()
    call(st, st.client.delete_session, session_id, user_id)
    emit(st, {"deleted": session_id}, lambda _: console.print(f"[green]✓[/] conversa {session_id} apagada"))
