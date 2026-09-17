"""`kuro tools`: listar, inspecionar e invocar tools sem montar um agente."""

import json
from typing import Any

import questionary
import typer
from rich.table import Table

from agent_service.cli.agents import BACK
from agent_service.cli.common import (
    EXIT_FAILED,
    State,
    call,
    console,
    emit,
    fail,
    parse_json_object,
    parse_pairs,
    print_json,
    state,
)

app = typer.Typer(help="Tools: listar, ver, catálogo de builtins, invocar.")


def _render_list(tools: list[dict[str, Any]]) -> None:
    table = Table(show_edge=False, header_style="bold")
    for column in ("tool_name", "kind", "label", "ativa"):
        table.add_column(column)
    for t in tools:
        seed = " [dim](seed)[/]" if t["is_seed"] else ""
        table.add_row(f"[cyan]{t['tool_name']}[/]{seed}", t["kind"], t["label"], "sim" if t["enabled"] else "[red]não[/]")
    console.print(table)


def _render_tool(t: dict[str, Any]) -> None:
    console.print(f"[bold]{t['label']}[/] [dim]({t['tool_name']} · {t['kind']})[/]")
    if t.get("description"):
        console.print(t["description"])
    if t.get("functions"):
        console.print(f"funções: {', '.join(t['functions'])}")
    if t.get("build_error"):
        console.print(f"[red]não constrói:[/] {t['build_error']}")
    console.print_json(json.dumps(t["config"], ensure_ascii=False, default=str))


def _render_invoke(result: dict[str, Any]) -> None:
    value = result["result"]
    if isinstance(value, str):
        console.print(value, highlight=False)
    else:
        console.print_json(json.dumps(value, ensure_ascii=False, default=str))


@app.callback(invoke_without_command=True)
def tools(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    st = state(ctx)
    if st.interactive:
        browse(st)
    else:
        list_tools(ctx)


@app.command("list")
def list_tools(ctx: typer.Context) -> None:
    """Lista as tools cadastradas."""
    st = state(ctx)
    emit(st, call(st, st.client.list_tools), _render_list)


@app.command("get")
def get_tool(ctx: typer.Context, tool_name: str) -> None:
    """Mostra uma tool (segredos mascarados) e, para builtins, as funções expostas."""
    st = state(ctx)
    emit(st, call(st, st.client.get_tool, tool_name), _render_tool)


@app.command("catalog")
def catalog(ctx: typer.Context) -> None:
    """Catálogo de toolkits builtin disponíveis e seus parâmetros."""
    st = state(ctx)
    emit(
        st,
        call(st, st.client.tool_catalog),
        lambda entries: [console.print(f"[cyan]{e['builtin_id']}[/] — {e['label']}: {e['description']}") for e in entries],
    )


@app.command("invoke")
def invoke(
    ctx: typer.Context,
    tool_name: str,
    arg: list[str] = typer.Option([], "--arg", "-a", help="Argumento nome=valor (repetível; valor em JSON quando possível)."),
    args_json: str | None = typer.Option(None, "--args-json", help="Argumentos como objeto JSON."),
    function: str | None = typer.Option(None, "--fn", help="Função da toolkit (obrigatório para kind=builtin)."),
) -> None:
    """Executa a tool isoladamente. Sai com código 1 se a tool falhar."""
    st = state(ctx)
    arguments = {**(parse_json_object(st, args_json, "--args-json") if args_json else {}), **parse_pairs(st, arg, "--arg")}
    _invoke(st, tool_name, arguments, function)


def _invoke(st: State, tool_name: str, arguments: dict[str, Any], function: str | None) -> None:
    result = call(st, st.client.invoke_tool, tool_name, arguments, function)
    if st.json_mode:
        print_json(result)
    if not result["ok"]:  # a API responde 200 com ok=false quando a tool em si falha
        fail(st, result.get("error") or "a tool falhou", EXIT_FAILED)
    if not st.json_mode:
        _render_invoke(result)


def browse(st: State) -> None:
    while True:
        rows = call(st, st.client.list_tools)
        choices = [questionary.Choice(f"{t['tool_name']}  —  {t['label']} ({t['kind']})", value=t["tool_name"]) for t in rows]
        choices.append(questionary.Choice("← sair", value=BACK))
        tool_name = questionary.select("Tool:", choices=choices).ask()
        if tool_name in (None, BACK):
            return
        try:
            detail = call(st, st.client.get_tool, tool_name)
            _render_tool(detail)
            if not questionary.confirm("Invocar agora?", default=True).ask():
                continue
            function = None
            if detail.get("functions"):
                function = questionary.select("Função:", choices=detail["functions"]).ask()
            raw = questionary.text("Argumentos (JSON):", default="{}").ask()
            if raw is None:
                continue
            _invoke(st, tool_name, parse_json_object(st, raw, "argumentos"), function)
        except typer.Exit:
            continue
