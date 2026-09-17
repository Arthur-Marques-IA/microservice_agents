"""`kuro collections`: bases de conhecimento — cadastrar, alimentar e buscar.

Um agente consulta uma collection quando aponta para ela:
`kuro agents set <agente> knowledge_collection=manuais`.
"""

import sys
from typing import Any

import typer
from rich.table import Table

from agent_service.cli.common import EXIT_USAGE, State, call, console, emit, fail, state

app = typer.Typer(help="Collections de documentos (RAG): listar, criar, alimentar, buscar.")


def _render_list(rows: list[dict[str, Any]]) -> None:
    if not rows:
        console.print("Nenhuma collection. Crie uma com `kuro collections create <nome> --label \"Manuais\"`.")
        return
    table = Table(show_edge=False, header_style="bold")
    for column in ("name", "nome", "descrição", "agentes"):
        table.add_column(column)
    for c in rows:
        seed = " [dim](seed)[/]" if c["is_seed"] else ""
        table.add_row(
            f"[cyan]{c['name']}[/]{seed}", c["label"], c["description"] or "—", ", ".join(c["agents_using"]) or "—"
        )
    console.print(table)


@app.callback(invoke_without_command=True)
def collections(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        list_collections(ctx)


@app.command("list")
def list_collections(ctx: typer.Context) -> None:
    """Lista as collections e quais agentes usam cada uma."""
    st = state(ctx)
    emit(st, call(st, st.client.list_collections), _render_list)


@app.command("create")
def create_collection(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Slug: minúsculas, números, '-' ou '_'."),
    label: str = typer.Option(..., "--label", "-l", help="Nome exibido."),
    description: str | None = typer.Option(None, "--description", "-d"),
) -> None:
    """Cria uma collection (a tabela de vetores nasce na primeira ingestão)."""
    st = state(ctx)
    created = call(st, st.client.create_collection, {"name": name, "label": label, "description": description})
    emit(st, created, lambda c: console.print(f"[green]✓[/] collection {c['name']} criada"))


@app.command("delete")
def delete_collection(
    ctx: typer.Context,
    name: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Não pede confirmação (obrigatório sem TTY)."),
) -> None:
    """Remove o cadastro da collection (os documentos já indexados permanecem)."""
    st = state(ctx)
    if not yes:
        if not st.interactive:
            fail(st, "confirme com --yes para remover sem TTY", EXIT_USAGE)
        if not typer.confirm(f"Remover a collection {name!r}?"):
            raise typer.Exit()
    call(st, st.client.delete_collection, name)
    emit(st, {"deleted": name}, lambda _: console.print(f"[green]✓[/] {name} removida"))


@app.command("add")
def add_document(
    ctx: typer.Context,
    name: str,
    text: str | None = typer.Option(None, "--text", "-t", help="Texto a indexar; sem isto, lê de stdin."),
    title: str | None = typer.Option(None, "--title", help="Nome do documento."),
) -> None:
    """Indexa um texto na collection. Ex.: `type manual.txt | kuro collections add manuais`."""
    st = state(ctx)
    if text is None:
        text = "" if sys.stdin.isatty() else sys.stdin.read()
        if not text.strip():
            fail(st, "sem texto: use --text ou envie o conteúdo por stdin", EXIT_USAGE)
    result = call(st, st.client.add_document, name, {"text": text, "name": title})
    emit(st, result, lambda r: console.print(f"[green]✓[/] indexado ({r['content_id']})"))


@app.command("search")
def search_collection(
    ctx: typer.Context,
    name: str,
    query: str,
    limit: int = typer.Option(5, "--limit", "-n", min=1, max=50),
) -> None:
    """Busca semântica na collection — o mesmo que o agente enxerga."""
    st = state(ctx)
    results = call(st, st.client.search_collection, name, query, limit)

    def render(items: list[dict[str, Any]]) -> None:
        if not items:
            console.print("[dim]nada encontrado[/]")
            return
        for i, doc in enumerate(items, 1):
            console.print(f"[bold cyan]{i}.[/] {doc['content'][:500]}", highlight=False)

    emit(st, results, render)
