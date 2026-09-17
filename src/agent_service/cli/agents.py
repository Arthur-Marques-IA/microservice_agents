"""`kuro agents`: listar, inspecionar, criar/editar e testar agentes.

Sem subcomando e com TTY, abre o seletor: escolhe o agente e depois a ação
(testar, ver, editar, versões, remover). Sem TTY, `kuro agents` = `list`.
"""

import json
from typing import Any

import questionary
import typer
from rich.panel import Panel
from rich.table import Table

from agent_service.cli.chat import run_chat
from agent_service.cli.common import (
    EXIT_USAGE,
    State,
    call,
    console,
    emit,
    fail,
    parse_pairs,
    read_json_file,
    state,
)

app = typer.Typer(help="Agentes: listar, ver, criar/editar (apply), testar.", no_args_is_help=False)

BACK = "__voltar__"  # value=None faz o questionary devolver o título da opção

EDITABLE_FIELDS = (
    "name",
    "instructions",
    "tools",
    "model_provider",
    "model_id",
    "dependency_fields",
    "memory_backend",
    "num_history_runs",
)


def editable(definition: dict[str, Any]) -> dict[str, Any]:
    """Só os campos aceitos por `apply`/`PUT` — a saída de `get --editable`."""
    return {"agent_type": definition["agent_type"], **{k: definition[k] for k in EDITABLE_FIELDS}}


# -- renderização ------------------------------------------------------------------


def _render_list(agents: list[dict[str, Any]]) -> None:
    table = Table(show_edge=False, header_style="bold")
    for column in ("agent_type", "nome", "modelo", "tools", "prompt", "memória"):
        table.add_column(column)
    for a in agents:
        model = f"{a['model_provider'] or 'padrão'}/{a['model_id'] or 'padrão'}"
        seed = " [dim](seed)[/]" if a["is_seed"] else ""
        table.add_row(
            f"[cyan]{a['agent_type']}[/]{seed}",
            a["name"],
            model,
            ", ".join(a["tools"]) or "—",
            f"v{a['prompt_version']}",
            a["memory_backend"],
        )
    console.print(table)


def _render_agent(a: dict[str, Any]) -> None:
    lines = [
        f"[bold]{a['name']}[/] [dim]({a['agent_type']}{' · seed' if a['is_seed'] else ''})[/]",
        f"modelo: {a['model_provider'] or 'padrão'} / {a['model_id'] or 'padrão'}",
        f"memória: {a['memory_backend']} · histórico: {a['num_history_runs']} runs · prompt v{a['prompt_version']}",
        f"tools: {', '.join(a['tools']) or '—'}",
    ]
    if a["dependency_fields"]:
        deps = ", ".join(f"{f['name']}:{f['type']}{'*' if f['required'] else ''}" for f in a["dependency_fields"])
        lines.append(f"dependencies: {deps}  [dim](* obrigatório)[/]")
    lines.append("\n[bold]instructions[/]")
    lines += [f"  {i + 1}. {text}" for i, text in enumerate(a["instructions"])]
    console.print(Panel("\n".join(lines), expand=False))


def _render_versions(versions: list[dict[str, Any]]) -> None:
    for v in versions:
        console.print(f"[bold]v{v['version']}[/] [dim]{v['created_at']}[/]")
        for i, text in enumerate(v["instructions"]):
            console.print(f"  {i + 1}. {text}", highlight=False)


# -- comandos ------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def agents(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    st = state(ctx)
    if st.interactive:
        browse(st)
    else:
        list_agents(ctx)


@app.command("list")
def list_agents(ctx: typer.Context) -> None:
    """Lista os agentes cadastrados."""
    st = state(ctx)
    emit(st, call(st, st.client.list_agents), _render_list)


@app.command("get")
def get_agent(
    ctx: typer.Context,
    agent_type: str,
    as_editable: bool = typer.Option(
        False, "--editable", help="Só os campos editáveis, em JSON — pronto para `apply -f`."
    ),
) -> None:
    """Mostra a definição de um agente."""
    st = state(ctx)
    definition = call(st, st.client.get_agent, agent_type)
    if as_editable:
        emit(st, editable(definition))
    else:
        emit(st, definition, _render_agent)


@app.command("apply")
def apply_agent(
    ctx: typer.Context,
    file: str = typer.Option(..., "--file", "-f", help="JSON da definição (`-` = stdin). Precisa de agent_type."),
) -> None:
    """Cria o agente se não existir, senão atualiza só os campos do arquivo."""
    st = state(ctx)
    body = read_json_file(st, file)
    agent_type = body.get("agent_type")
    if not isinstance(agent_type, str) or not agent_type:
        fail(st, "o arquivo precisa do campo agent_type", EXIT_USAGE)

    existing = {a["agent_type"] for a in call(st, st.client.list_agents)}
    if agent_type in existing:
        changes = {k: v for k, v in body.items() if k != "agent_type"}
        unknown = sorted(set(changes) - set(EDITABLE_FIELDS))
        if unknown:
            fail(st, f"campos não editáveis: {', '.join(unknown)}", EXIT_USAGE)
        result, action = call(st, st.client.update_agent, agent_type, changes), "atualizado"
    else:
        result, action = call(st, st.client.create_agent, body), "criado"
    emit(st, result, lambda a: console.print(f"[green]✓[/] {a['agent_type']} {action} (prompt v{a['prompt_version']})"))


@app.command("set")
def set_fields(
    ctx: typer.Context,
    agent_type: str,
    pairs: list[str] = typer.Argument(
        ..., help='campo=valor (valor em JSON quando possível). Ex.: name="Suporte" tools=\'["web_search"]\''
    ),
) -> None:
    """Altera só os campos informados de um agente."""
    st = state(ctx)
    changes = parse_pairs(st, pairs, "campo")
    unknown = sorted(set(changes) - set(EDITABLE_FIELDS))
    if unknown:
        fail(st, f"campos não editáveis: {', '.join(unknown)} (use: {', '.join(EDITABLE_FIELDS)})", EXIT_USAGE)
    if isinstance(changes.get("instructions"), str):
        changes["instructions"] = [changes["instructions"]]
    result = call(st, st.client.update_agent, agent_type, changes)
    emit(st, result, lambda a: console.print(f"[green]✓[/] {a['agent_type']} atualizado (prompt v{a['prompt_version']})"))


@app.command("edit")
def edit_agent(ctx: typer.Context, agent_type: str) -> None:
    """Abre a definição no seu editor ($EDITOR) e salva o que mudar."""
    st = state(ctx)
    if not st.interactive:
        fail(st, "edit precisa de TTY; sem TTY use `agents set` ou `agents apply -f`", EXIT_USAGE)
    _edit(st, call(st, st.client.get_agent, agent_type))


@app.command("delete")
def delete_agent(
    ctx: typer.Context,
    agent_type: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Não pede confirmação (obrigatório sem TTY)."),
) -> None:
    """Remove um agente (agentes seed não podem ser removidos)."""
    st = state(ctx)
    if not yes:
        if not st.interactive:
            fail(st, "confirme com --yes para remover sem TTY", EXIT_USAGE)
        if not typer.confirm(f"Remover o agente {agent_type!r}?"):
            raise typer.Exit()
    call(st, st.client.delete_agent, agent_type)
    emit(st, {"deleted": agent_type}, lambda _: console.print(f"[green]✓[/] {agent_type} removido"))


@app.command("versions")
def versions(ctx: typer.Context, agent_type: str) -> None:
    """Histórico de versões do prompt (instructions)."""
    st = state(ctx)
    emit(st, call(st, st.client.agent_versions, agent_type), _render_versions)


@app.command("test")
def test_agent(
    ctx: typer.Context,
    agent_type: str,
    message: str | None = typer.Option(None, "--message", "-m", help="Mensagem única; sem ela abre o REPL."),
    dep: list[str] = typer.Option([], "--dep", "-d", help="Dependency nome=valor (repetível)."),
    new_session: bool = typer.Option(False, "--new-session", help="Começa uma sessão nova."),
) -> None:
    """Atalho para `kuro chat` com este agente."""
    st = state(ctx)
    run_chat(st, agent_type, message=message, deps=parse_pairs(st, dep, "--dep"), new_session=new_session)


# -- modo interativo -------------------------------------------------------------------


def _edit(st: State, definition: dict[str, Any]) -> None:
    current = editable(definition)
    edited_text = typer.edit(json.dumps(current, ensure_ascii=False, indent=2), extension=".json")
    if edited_text is None:
        console.print("[dim]nada alterado[/]")
        return
    try:
        edited = json.loads(edited_text)
    except ValueError as exc:
        console.print(f"[red]JSON inválido, nada salvo:[/] {exc}")
        return
    if edited.get("agent_type") != current["agent_type"]:
        console.print("[red]agent_type não pode mudar, nada salvo[/]")
        return
    changes = {k: v for k, v in edited.items() if k in EDITABLE_FIELDS and v != current.get(k)}
    if not changes:
        console.print("[dim]nada alterado[/]")
        return
    updated = call(st, st.client.update_agent, current["agent_type"], changes)
    console.print(f"[green]✓[/] salvo: {', '.join(changes)} (prompt v{updated['prompt_version']})")


def browse(st: State) -> None:
    while True:
        agents_list = call(st, st.client.list_agents)
        if not agents_list:
            console.print("Nenhum agente cadastrado. Crie um com `kuro agents apply -f agente.json`.")
            return
        choices = [questionary.Choice(f"{a['agent_type']}  —  {a['name']}", value=a["agent_type"]) for a in agents_list]
        choices.append(questionary.Choice("← sair", value=BACK))
        agent_type = questionary.select("Agente:", choices=choices).ask()
        if agent_type in (None, BACK):  # None = Ctrl+C
            return
        _agent_menu(st, agent_type)


def _agent_menu(st: State, agent_type: str) -> None:
    while True:
        try:
            definition = call(st, st.client.get_agent, agent_type)
        except typer.Exit:
            return  # removido ou inacessível: volta para a lista
        actions = [
            questionary.Choice("Testar (chat)", value="chat"),
            questionary.Choice("Testar em sessão nova", value="chat-new"),
            questionary.Choice("Ver definição", value="view"),
            questionary.Choice("Editar no editor", value="edit"),
            questionary.Choice("Histórico do prompt", value="versions"),
        ]
        if not definition["is_seed"]:
            actions.append(questionary.Choice("Remover", value="delete"))
        actions.append(questionary.Choice("← voltar", value=BACK))

        action = questionary.select(f"{definition['name']} ({agent_type}):", choices=actions).ask()
        try:
            if action in (None, BACK):
                return
            if action in ("chat", "chat-new"):
                run_chat(st, agent_type, new_session=action == "chat-new")
            elif action == "view":
                _render_agent(definition)
            elif action == "edit":
                _edit(st, definition)
            elif action == "versions":
                _render_versions(call(st, st.client.agent_versions, agent_type))
            elif action == "delete" and questionary.confirm(f"Remover {agent_type}?", default=False).ask():
                call(st, st.client.delete_agent, agent_type)
                console.print(f"[green]✓[/] {agent_type} removido")
                return
        except typer.Exit:
            continue  # erro já impresso; segue no menu
