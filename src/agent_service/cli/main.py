"""Entrada da CLI `kuro` (ver `[project.scripts]` no pyproject).

`kuro` sem argumentos, com TTY, abre um shell: `/agents`, `/tools`,
`/chat <agente>`, `/runs`... — cada linha é o mesmo comando da CLI (a `/`
é opcional), então tudo que funciona no shell funciona em um script.
"""

import shlex
import sys
from typing import Any

import click
import typer
from rich.table import Table

from agent_service.cli import agents, runs, tools
from agent_service.cli.chat import chat
from agent_service.cli.client import ApiError, Client, ServiceUnavailable
from agent_service.cli.common import (
    EXIT_FAILED,
    EXIT_UNAVAILABLE,
    State,
    call,
    console,
    emit,
    err_console,
    fail,
    print_json,
    state,
)

DEFAULT_URL = "http://localhost:58000"

app = typer.Typer(
    name="kuro",
    help="Opera o agent-service pelo terminal. `--json` em qualquer comando para saída de máquina.",
    no_args_is_help=False,
    rich_markup_mode="markdown",
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(agents.app, name="agents")
app.add_typer(tools.app, name="tools")
app.add_typer(runs.app, name="runs")
app.command("chat")(chat)

providers_app = typer.Typer(help="Provedores de modelo (LLM): listar e testar chaves.")
app.add_typer(providers_app, name="providers")


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    url: str = typer.Option(
        DEFAULT_URL, "--url", envvar=["KURO_API_URL", "AGENT_SERVICE_URL"], help="URL do agent-service."
    ),
    json_mode: bool = typer.Option(False, "--json", envvar="KURO_JSON", help="Saída JSON (stdout) e erros JSON (stderr)."),
    no_input: bool = typer.Option(
        False, "--no-input", envvar="KURO_NO_INPUT", help="Nunca pergunta nada (falha se faltar argumento)."
    ),
    timeout: float = typer.Option(120.0, "--timeout", help="Timeout das requisições, em segundos."),
) -> None:
    ctx.obj = State(client=Client(url, timeout=timeout), json_mode=json_mode, no_input=no_input)
    if ctx.invoked_subcommand is None:
        if ctx.obj.interactive:
            shell(ctx)
        else:
            console.print(ctx.get_help())


# -- health ----------------------------------------------------------------------


@app.command("health")
def health(ctx: typer.Context) -> None:
    """Diagnóstico: serviço no ar, Langfuse, tools Python e provedores configurados."""
    st = state(ctx)
    report: dict[str, Any] = {"url": st.client.base_url}
    report["service"] = call(st, st.client.health)
    checks = {
        "observability": st.client.observability_config,
        "python_tools": st.client.python_tools_config,
        "providers": st.client.list_providers,
    }
    for key, fn in checks.items():
        try:
            report[key] = fn()
        except ServiceUnavailable as exc:
            fail(st, str(exc), EXIT_UNAVAILABLE)
        except ApiError as exc:
            report[key] = {"error": exc.detail, "status": exc.status}
    if isinstance(report["providers"], list):
        report["providers"] = [
            {k: p.get(k) for k in ("provider", "enabled", "configured", "last_test_ok")} for p in report["providers"]
        ]

    def render(r: dict[str, Any]) -> None:
        console.print(f"[green]●[/] agent-service em {r['url']}")
        obs = r["observability"]
        on = obs.get("enabled")
        console.print(f"{'[green]●[/]' if on else '[yellow]●[/]'} Langfuse {'ligado' if on else 'desligado — `kuro runs` não terá dados'}")
        py = r["python_tools"].get("enabled")
        console.print(f"{'[green]●[/]' if py else '[dim]●[/]'} tools Python {'ligadas' if py else 'desligadas'}")
        if isinstance(r["providers"], list):
            ready = [p["provider"] for p in r["providers"] if p["enabled"] and p["configured"]]
            hint = "" if ready else " (google ainda usa GOOGLE_API_KEY do .env, se houver)"
            console.print(f"{'[green]●[/]' if ready else '[yellow]●[/]'} provedores habilitados: {', '.join(ready) or 'nenhum'}{hint}")

    emit(st, report, render)


# -- providers -------------------------------------------------------------------


@providers_app.callback(invoke_without_command=True)
def providers(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        list_providers(ctx)


@providers_app.command("list")
def list_providers(ctx: typer.Context) -> None:
    """Provedores e se estão habilitados/configurados (chaves nunca aparecem)."""
    st = state(ctx)

    def render(rows: list[dict[str, Any]]) -> None:
        table = Table(show_edge=False, header_style="bold")
        for column in ("provider", "habilitado", "chave", "modelo padrão", "último teste"):
            table.add_column(column)
        for p in rows:
            test = {True: "[green]ok[/]", False: "[red]falhou[/]"}.get(p["last_test_ok"], "—")
            key = p["key_hint"] or ("sim" if p["configured"] else "—")
            table.add_row(f"[cyan]{p['provider']}[/]", "sim" if p["enabled"] else "não", key, p["default_model_id"], test)
        console.print(table)

    emit(st, call(st, st.client.list_providers), render)


@providers_app.command("test")
def test_provider(ctx: typer.Context, provider: str) -> None:
    """Valida a chave salva de um provedor (sem gastar tokens). Sai com 1 se falhar."""
    st = state(ctx)
    result = call(st, st.client.test_provider, provider)
    if st.json_mode:
        print_json(result)
    if not result["ok"]:
        fail(st, result.get("message") or f"teste de {provider} falhou", EXIT_FAILED)
    if not st.json_mode:
        console.print(f"[green]✓[/] {provider} ok")


# -- shell -----------------------------------------------------------------------

_SHELL_HELP = """[bold]Comandos[/] (a `/` é opcional; qualquer comando da CLI funciona aqui)
  /agents              escolher um agente → testar, ver, editar, versões
  /chat <agente>       conversar direto com um agente
  /tools               escolher uma tool → ver e invocar
  /runs                execuções recentes   ·  /runs show <run_id>
  /providers           provedores de modelo ·  /health  diagnóstico
  /help                esta ajuda           ·  <comando> --help  detalhes
  /sair                sair"""


def shell(ctx: typer.Context) -> None:
    command = typer.main.get_command(app)
    root_params = ctx.params
    console.print(f"[bold]kuro[/] [dim]· {root_params['url']} · /help para comandos[/]")
    while True:
        try:
            line = console.input("[bold cyan]kuro>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        if not line:
            continue
        if line.startswith("/"):
            line = line[1:]
        if line in ("sair", "exit", "quit", "q"):
            return
        if line in ("help", "ajuda", "?"):
            console.print(_SHELL_HELP)
            continue
        try:
            args = shlex.split(line, posix=True)
        except ValueError as exc:
            err_console.print(f"[red]erro:[/] {exc}")
            continue
        globals_ = ["--url", root_params["url"], "--timeout", str(root_params["timeout"])]
        try:
            command.main(args=globals_ + args, prog_name="kuro", standalone_mode=False)
        except click.exceptions.Exit:
            pass
        except click.ClickException as exc:
            exc.show()
        except click.exceptions.Abort:
            console.print()
        except KeyboardInterrupt:
            console.print()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # Windows: acento não pode quebrar num pipe cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    app()


if __name__ == "__main__":
    main()
