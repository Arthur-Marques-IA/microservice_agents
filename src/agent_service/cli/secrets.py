"""`kuro secrets`: os segredos que as tools usam por referência (`{{secret:NOME}}`).

O valor entra uma vez, por quem opera, e não sai mais: a listagem mostra o nome e quais
tools o usam. Como a chave de um provedor, o valor nunca vai como argumento (ficaria no
histórico do shell e na lista de processos): variável de ambiente, stdin ou prompt oculto.
"""

import os
import sys
from typing import Any

import typer
from rich.table import Table

from agent_service.cli.common import EXIT_USAGE, call, console, emit, fail, state

app = typer.Typer(help="Segredos das tools ({{secret:NOME}}): cadastrar, listar, remover. O valor não volta em leitura nenhuma.")


def _render_list(items: list[dict[str, Any]]) -> None:
    if not items:
        console.print("Nenhum segredo. Cadastre com: kuro secrets set NOME --value-env VARIAVEL", highlight=False)
        return
    table = Table(box=None, header_style="bold")
    for column in ("nome", "usado por", "descrição", "atualizado"):
        table.add_column(column)
    for s in items:
        table.add_row(
            s["name"], ", ".join(s.get("used_by") or []) or "—", s.get("description") or "", str(s.get("updated_at") or "")[:19]
        )
    console.print(table)


@app.command("list")
def list_secrets(ctx: typer.Context) -> None:
    """Os segredos e as tools que usam cada um — nunca o valor."""
    st = state(ctx)
    emit(st, call(st, st.client.list_secrets), _render_list)


@app.command("set")
def set_secret(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="NOME em maiúsculas, como na referência {{secret:NOME}}."),
    value_env: str | None = typer.Option(
        None, "--value-env", help="Nome da variável de ambiente com o valor (não o valor)."
    ),
    value_stdin: bool = typer.Option(False, "--value-stdin", help="Lê o valor do stdin."),
    description: str | None = typer.Option(None, "--description", help="Para que serve (aparece na listagem)."),
) -> None:
    """Cadastra ou troca o valor de um segredo. Trocar vale na próxima chamada da tool,
    sem editá-la. Ex.: `TOKEN=... kuro secrets set REGENTE_TOKEN --value-env TOKEN`."""
    st = state(ctx)
    if value_env:
        value = os.environ.get(value_env, "")
        if not value.strip():
            fail(st, f"a variável de ambiente {value_env} está vazia", EXIT_USAGE)
    elif value_stdin or not st.interactive:
        value = "" if sys.stdin.isatty() else sys.stdin.read()
        if not value.strip():
            fail(st, "sem valor: use --value-env NOME_DA_VARIAVEL ou envie por stdin (o valor não pode ir como argumento)", EXIT_USAGE)
    else:
        value = typer.prompt(f"Valor de {name}", hide_input=True)
    body: dict[str, Any] = {"value": value.strip()}
    if description is not None:
        body["description"] = description
    result = call(st, st.client.set_secret, name, body)
    verb = "cadastrado" if result.get("created") else "atualizado"
    emit(
        st,
        result,
        lambda r: console.print(
            f"[green]✓[/] segredo {name} {verb} (termina em {r['hint'][-4:]}). Use na tool como {{{{secret:{name}}}}}",
            highlight=False,
        ),
    )


@app.command("delete")
def delete_secret(
    ctx: typer.Context,
    name: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Não pede confirmação (obrigatório sem TTY)."),
) -> None:
    """Remove um segredo. Recusado enquanto alguma tool o referenciar."""
    st = state(ctx)
    if not yes:
        if not st.interactive:
            fail(st, "confirme com --yes para remover sem TTY", EXIT_USAGE)
        if not typer.confirm(f"Remover o segredo {name!r}? O valor não tem como ser recuperado."):
            raise typer.Exit()
    call(st, st.client.delete_secret, name)
    emit(st, {"deleted": name}, lambda _: console.print(f"[green]✓[/] segredo {name} removido"))
