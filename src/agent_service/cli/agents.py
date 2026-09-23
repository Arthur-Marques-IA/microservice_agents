"""`kuro agents`: listar, inspecionar, criar/editar e testar agentes.

Sem subcomando e com TTY, abre o seletor: escolhe o agente e depois a ação
(testar, ver, editar, versões, remover). Sem TTY, `kuro agents` = `list`.
"""

import json
from typing import Any

import click
import questionary
import typer
from rich.panel import Panel
from rich.table import Table

from agent_service.cli.chat import run_chat, session_for_existing
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

app = typer.Typer(help="Agentes: listar, ver, criar/editar (apply), testar, restaurar versão.", no_args_is_help=False)

BACK = "__voltar__"  # value=None faz o questionary devolver o título da opção

EDITABLE_FIELDS = (
    "name",
    "instructions",
    "tools",
    "model_provider",
    "model_id",
    "model_credential_id",
    "knowledge_collection",
    "dependency_fields",
    "memory_backend",
    "num_history_runs",
    "kind",
    "response_schema",
)


# Num agente `analysis` estes campos não têm efeito (ele é one-shot, sem sessão
# nem memória) e a API recusa configurá-los — oferecê-los no JSON editável seria
# convidar a mexer num campo que só devolve 422.
INERTES_EM_ANALYSIS = ("num_history_runs", "memory_backend")


def editable(definition: dict[str, Any]) -> dict[str, Any]:
    """Só os campos aceitos por `apply`/`PUT` — a saída de `get --editable`."""
    campos = EDITABLE_FIELDS
    if definition.get("kind") == "analysis":
        campos = tuple(c for c in campos if c not in INERTES_EM_ANALYSIS)
    return {"agent_type": definition["agent_type"], **{k: definition.get(k) for k in campos}}


# -- renderização ------------------------------------------------------------------


def _render_list(agents: list[dict[str, Any]]) -> None:
    table = Table(show_edge=False, header_style="bold")
    for column in ("agent_type", "nome", "modelo", "tools", "conhecimento", "prompt"):
        table.add_column(column)
    for a in agents:
        model = f"{a['model_provider'] or 'padrão'}/{a['model_id'] or 'padrão'}"
        seed = " [dim](seed)[/]" if a["is_seed"] else ""
        table.add_row(
            f"[cyan]{a['agent_type']}[/]{seed}",
            a["name"],
            model,
            ", ".join(a["tools"]) or "—",
            a.get("knowledge_collection") or "—",
            f"v{a['prompt_version']}",
        )
    console.print(table)


def _render_agent(a: dict[str, Any]) -> None:
    kind = a.get("kind", "conversational")
    lines = [
        f"[bold]{a['name']}[/] [dim]({a['agent_type']}{' · seed' if a['is_seed'] else ''} · {kind})[/]",
        f"modelo: {a['model_provider'] or 'padrão'} / {a['model_id'] or 'padrão'}"
        f" · credencial: {a.get('model_credential_id') or 'padrão do provedor'}",
        f"memória: {a['memory_backend']} · histórico: {a['num_history_runs']} runs · prompt v{a['prompt_version']}",
        f"tools: {', '.join(a['tools']) or '—'}",
        f"base de conhecimento: {a.get('knowledge_collection') or '—'}",
    ]
    if a["dependency_fields"]:
        deps = ", ".join(f"{f['name']}:{f['type']}{'*' if f['required'] else ''}" for f in a["dependency_fields"])
        lines.append(f"dependencies: {deps}  [dim](* obrigatório)[/]")
    if kind == "analysis" and a.get("response_schema"):
        campos = ", ".join(f"{f['name']}:{f['type']}{'*' if f['required'] else ''}" for f in a["response_schema"])
        lines.append(f"response_schema: {campos}  [dim](* obrigatório)[/]")
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


@app.command("rollback")
def rollback(
    ctx: typer.Context,
    agent_type: str,
    version: int = typer.Argument(..., min=1, help="Versão do prompt a restaurar (veja `agents versions`)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Não pede confirmação (obrigatório sem TTY)."),
) -> None:
    """Restaura as instructions de uma versão anterior do prompt.

    Não desfaz o histórico: reaplicar a v3 grava uma versão nova com o texto
    da v3, então dá para voltar atrás do rollback do mesmo jeito."""
    st = state(ctx)
    versions_list = call(st, st.client.agent_versions, agent_type)
    alvo = next((v for v in versions_list if v["version"] == version), None)
    if alvo is None:
        disponiveis = ", ".join(f"v{v['version']}" for v in versions_list) or "nenhuma"
        fail(st, f"{agent_type} não tem a versão v{version} (disponíveis: {disponiveis})", EXIT_USAGE)

    atual = call(st, st.client.get_agent, agent_type)
    if atual["instructions"] == alvo["instructions"]:
        emit(
            st,
            {"agent_type": agent_type, "unchanged": True, "prompt_version": atual["prompt_version"]},
            lambda _: console.print(f"[dim]v{version} é igual ao prompt atual (v{atual['prompt_version']}) — nada a fazer[/]"),
        )
        return

    if not yes:
        if not st.interactive:
            fail(st, "confirme com --yes para restaurar sem TTY", EXIT_USAGE)
        _render_versions([alvo])
        if not typer.confirm(f"Restaurar as instructions da v{version} de {agent_type}?"):
            raise typer.Exit()
    updated = call(st, st.client.update_agent, agent_type, {"instructions": alvo["instructions"]})
    emit(
        st,
        updated,
        lambda a: console.print(f"[green]✓[/] {agent_type} voltou ao texto da v{version} (agora prompt v{a['prompt_version']})"),
    )


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


@app.command("feedback")
def feedback(
    ctx: typer.Context,
    agent_type: str,
    message: str | None = typer.Option(
        None, "--message", "-m", help="O que ajustar (ex.: 'deveria confirmar o CPF antes')."
    ),
    session_id: str | None = typer.Option(
        None, "--session-id", help="Sessão específica; por padrão usa a sessão salva da última `kuro chat`."
    ),
    show: bool = typer.Option(False, "--show", help="Só mostra as regras atuais, sem enviar feedback novo."),
    remove: list[str] = typer.Option([], "--remove", help="Apaga a regra com este id (repetível)."),
    clear: bool = typer.Option(False, "--clear", help="Zera a nota e o histórico dela."),
    versions: bool = typer.Option(False, "--versions", help="Histórico de versões da nota."),
    rollback: int | None = typer.Option(None, "--rollback", min=1, help="Reaplica as regras de uma versão."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Não pede confirmação (obrigatório sem TTY)."),
) -> None:
    """Ensina o agente a partir de uma conversa: mescla o feedback nas regras de
    comportamento que passam a orientar as respostas dele dali pra frente.

    A nota é uma lista de regras com id, não um texto solto: o merge edita e
    remove regra por id, e a resposta diz o que mudou. `--show` lista os ids,
    `--remove` apaga uma, `--rollback` volta para uma versão anterior."""
    st = state(ctx)
    if show:
        emit(st, call(st, st.client.get_feedback, agent_type), _render_note)
        return
    if versions:
        emit(st, call(st, st.client.feedback_versions, agent_type), _render_note_versions)
        return
    if rollback is not None:
        emit(
            st,
            call(st, st.client.rollback_feedback, agent_type, rollback),
            lambda n: console.print(f"[green]✓[/] nota de {agent_type} voltou à v{rollback} (agora v{n['version']})"),
        )
        return
    if clear:
        if not _confirmado(st, yes, f"Zerar a nota de feedback de {agent_type!r} (e o histórico)?"):
            return
        call(st, st.client.clear_feedback, agent_type)
        emit(st, {"cleared": agent_type}, lambda _: console.print(f"[green]✓[/] nota de {agent_type} zerada"))
        return
    if remove:
        atual = call(st, st.client.get_feedback, agent_type)
        ficam = [r for r in atual["rules"] if r["id"] not in set(remove)]
        if len(ficam) == len(atual["rules"]):
            fail(st, f"nenhuma regra com id em {', '.join(remove)} (veja `--show`)", EXIT_USAGE)
        if not ficam:
            fail(st, "isso apagaria todas as regras — use --clear", EXIT_USAGE)
        emit(st, call(st, st.client.replace_feedback, agent_type, ficam), _render_note)
        return

    if not message:
        fail(st, "use -m/--message com o que ajustar, ou --show para ver as regras atuais", EXIT_USAGE)
    session = session_id or session_for_existing(agent_type)
    if not session:
        fail(
            st,
            f"nenhuma sessão salva para {agent_type!r} — converse primeiro com `kuro chat {agent_type}` "
            "ou informe --session-id",
            EXIT_USAGE,
        )
    updated = call(st, st.client.send_feedback, agent_type, session, message)
    emit(st, updated, _render_merge)


def _confirmado(st: State, yes: bool, pergunta: str) -> bool:
    if yes:
        return True
    if not st.interactive:
        fail(st, "confirme com --yes sem TTY", EXIT_USAGE)
    return bool(typer.confirm(pergunta))


def _render_note(note: dict[str, Any]) -> None:
    if not note.get("rules"):
        console.print("[dim](sem regras ainda)[/]")
        return
    console.print(f"[dim]v{note['version']}[/]")
    for regra in note["rules"]:
        console.print(f"[dim]{regra['id']}[/] {regra['texto']}", highlight=False)


def _render_merge(note: dict[str, Any]) -> None:
    """Mostrar o diff é o ponto: o merge mexe em regras que ninguém releu."""
    _render_note(note)
    rotulos = {"adicionadas": "green", "editadas": "yellow", "removidas": "red", "fundidas": "dim", "ignoradas": "dim"}
    for chave, cor in rotulos.items():
        for item in (note.get("diff") or {}).get(chave, []):
            console.print(f"[{cor}]{chave[:-1]}:[/] {item}", highlight=False)


def _render_note_versions(rows: list[dict[str, Any]]) -> None:
    table = Table(show_edge=False, header_style="bold")
    for column in ("versão", "origem", "regras", "quando"):
        table.add_column(column)
    for v in rows:
        table.add_row(str(v["version"]), v["origin"], str(len(v["rules"])), str(v["created_at"])[:19].replace("T", " "))
    console.print(table)


# -- modo interativo -------------------------------------------------------------------


def _edit(st: State, definition: dict[str, Any]) -> None:
    """Abre os campos editáveis no editor ($VISUAL/$EDITOR; no Windows, o Bloco de
    Notas) e envia só o que mudou. JSON inválido reabre o editor sem perder o texto."""
    current = editable(definition)
    text = json.dumps(current, ensure_ascii=False, indent=2)
    while True:
        try:
            edited_text = click.edit(text, extension=".json")
        except click.ClickException as exc:
            console.print(f"[red]não consegui abrir o editor:[/] {exc.format_message()} (defina EDITOR, ex.: EDITOR=\"code --wait\")")
            return
        if edited_text is None:  # fechou sem salvar
            console.print("[dim]nada alterado[/]")
            return
        problem = None
        try:
            edited = json.loads(edited_text)
            if not isinstance(edited, dict):
                problem = "o conteúdo precisa ser um objeto JSON"
            elif edited.get("agent_type") != current["agent_type"]:
                problem = "agent_type não pode mudar"
        except ValueError as exc:
            problem = f"JSON inválido: {exc}"
        if problem is None:
            break
        console.print(f"[red]{problem}[/]")
        if not questionary.confirm("Reabrir o editor para corrigir?", default=True).ask():
            console.print("[dim]nada salvo[/]")
            return
        text = edited_text

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
            questionary.Choice("Restaurar uma versão do prompt", value="rollback"),
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
            elif action == "rollback":
                _rollback_menu(st, agent_type, definition)
            elif action == "delete" and questionary.confirm(f"Remover {agent_type}?", default=False).ask():
                call(st, st.client.delete_agent, agent_type)
                console.print(f"[green]✓[/] {agent_type} removido")
                return
        except typer.Exit:
            continue  # erro já impresso; segue no menu


def _rollback_menu(st: State, agent_type: str, definition: dict[str, Any]) -> None:
    """Escolhe uma versão antiga do prompt e a reaplica — o `rollback` da UI."""
    versions_list = call(st, st.client.agent_versions, agent_type)
    anteriores = [v for v in versions_list if v["instructions"] != definition["instructions"]]
    if not anteriores:
        console.print("[dim]não há uma versão diferente da atual para restaurar[/]")
        return
    choices = [
        questionary.Choice(f"v{v['version']}  —  {v['instructions'][0][:60]}", value=v["version"])
        for v in anteriores
    ]
    choices.append(questionary.Choice("← voltar", value=BACK))
    escolhida = questionary.select("Restaurar qual versão?", choices=choices).ask()
    if escolhida in (None, BACK):
        return
    alvo = next(v for v in anteriores if v["version"] == escolhida)
    _render_versions([alvo])
    if not questionary.confirm(f"Restaurar as instructions da v{escolhida}?", default=False).ask():
        return
    updated = call(st, st.client.update_agent, agent_type, {"instructions": alvo["instructions"]})
    console.print(f"[green]✓[/] texto da v{escolhida} restaurado (agora prompt v{updated['prompt_version']})")


@app.command("integrate")
def integrate(ctx: typer.Context, agent_type: str) -> None:
    """Como chamar este agente de outro módulo: endpoint, cURL e dependências."""
    st = state(ctx)
    emit(st, call(st, st.client.integration, agent_type), _render_integration)


def _render_integration(c: dict[str, Any]) -> None:
    console.print(f"[bold]{c['name']}[/] [dim]({c['agent_type']} · prompt v{c['prompt_version']})[/]")
    console.print(f"POST {c['chat_url']}   [dim]streaming (SSE): POST {c['stream_url']}[/]")

    if c["dependencies"]:
        table = Table(show_edge=False, header_style="bold", title="dependencies", title_justify="left")
        for column in ("campo", "tipo", "obrigatório", "exigido por", "descrição"):
            table.add_column(column)
        for d in c["dependencies"]:
            table.add_row(
                f"[cyan]{d['name']}[/]",
                d["type"],
                "sim" if d["required"] else "não",
                ", ".join(d["required_by_tools"]) or "—",
                d["description"] or d["label"],
            )
        console.print(table)

    console.print("\n[bold]exemplo[/]")
    console.print(c["curl"], highlight=False)
    for aviso in c["warnings"]:
        console.print(f"[yellow]atenção:[/] {aviso}")
