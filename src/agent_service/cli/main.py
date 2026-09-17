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

from agent_service.cli import agents, collections, runs, tools
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

# 127.0.0.1, não localhost: no Windows `localhost` tenta IPv6 (::1) primeiro e o
# port-forward do Docker Desktop nesse caminho derruba conexões de forma intermitente.
DEFAULT_URL = "http://127.0.0.1:58000"

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
app.add_typer(collections.app, name="collections")
app.command("chat")(chat)

providers_app = typer.Typer(help="Provedores de modelo (LLM) suportados.")
app.add_typer(providers_app, name="providers")
credentials_app = typer.Typer(help="Credenciais (chaves) de modelo: listar e testar.")
app.add_typer(credentials_app, name="credentials")


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
        "credentials": st.client.list_credentials,
    }
    for key, fn in checks.items():
        try:
            report[key] = fn()
        except ServiceUnavailable as exc:
            fail(st, str(exc), EXIT_UNAVAILABLE)
        except ApiError as exc:
            report[key] = {"error": exc.detail, "status": exc.status}
    if isinstance(report["credentials"], list):
        report["credentials"] = [
            {k: c.get(k) for k in ("id", "provider", "label", "enabled", "configured", "last_test_ok")}
            for c in report["credentials"]
        ]

    def render(r: dict[str, Any]) -> None:
        console.print(f"[green]●[/] agent-service em {r['url']}")
        obs = r["observability"]
        on = obs.get("enabled")
        console.print(f"{'[green]●[/]' if on else '[yellow]●[/]'} Langfuse {'ligado' if on else 'desligado — `kuro runs` não terá dados'}")
        py = r["python_tools"].get("enabled")
        console.print(f"{'[green]●[/]' if py else '[dim]●[/]'} tools Python {'ligadas' if py else 'desligadas'}")
        if isinstance(r["credentials"], list):
            ready = sorted({c["provider"] for c in r["credentials"] if c["enabled"] and c["configured"]})
            hint = "" if ready else " (google ainda usa GOOGLE_API_KEY do .env, se houver)"
            console.print(f"{'[green]●[/]' if ready else '[yellow]●[/]'} provedores com credencial ativa: {', '.join(ready) or 'nenhum'}{hint}")

    emit(st, report, render)


# -- providers / credentials -----------------------------------------------------


@providers_app.callback(invoke_without_command=True)
def providers(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        list_providers(ctx)


@providers_app.command("list")
def list_providers(ctx: typer.Context) -> None:
    """Provedores suportados e quantas credenciais cada um tem."""
    st = state(ctx)

    def render(rows: list[dict[str, Any]]) -> None:
        table = Table(show_edge=False, header_style="bold")
        for column in ("provider", "nome", "credenciais", "modelo padrão"):
            table.add_column(column)
        for p in rows:
            count = f"{p['configured_count']}/{p['credential_count']} com chave" if p["credential_count"] else "—"
            table.add_row(f"[cyan]{p['provider']}[/]", p["label"], count, p["default_model_id"])
        console.print(table)

    emit(st, call(st, st.client.list_providers), render)


@credentials_app.callback(invoke_without_command=True)
def credentials(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        list_credentials(ctx, provider=None)


@credentials_app.command("list")
def list_credentials(
    ctx: typer.Context,
    provider: str | None = typer.Option(None, "--provider", "-p", help="Filtra por provedor."),
) -> None:
    """Credenciais cadastradas (a chave nunca aparece, só os últimos 4 caracteres)."""
    st = state(ctx)
    rows = [c for c in call(st, st.client.list_credentials) if provider is None or c["provider"] == provider]

    def render(items: list[dict[str, Any]]) -> None:
        if not items:
            console.print("Nenhuma credencial cadastrada — crie pelo console web (Modelos).")
            return
        table = Table(show_edge=False, header_style="bold")
        for column in ("id", "provider", "nome", "ativa", "chave", "último teste", "agentes"):
            table.add_column(column)
        for c in items:
            test = {True: "[green]ok[/]", False: "[red]falhou[/]"}.get(c["last_test_ok"], "—")
            key = c["key_hint"] or ("sim" if c["configured"] else "[red]sem chave[/]")
            table.add_row(
                f"[cyan]{c['id']}[/]", c["provider"], c["label"], "sim" if c["enabled"] else "não",
                key, test, ", ".join(c["agents_using"]) or "—",
            )
        console.print(table)

    emit(st, rows, render)


@credentials_app.command("test")
def test_credential(ctx: typer.Context, credential_id: str) -> None:
    """Valida a chave salva de uma credencial (sem gastar tokens). Sai com 1 se falhar."""
    st = state(ctx)
    result = call(st, st.client.test_credential, credential_id)
    if st.json_mode:
        print_json(result)
    if not result["ok"]:
        fail(st, result.get("message") or "teste da credencial falhou", EXIT_FAILED)
    if not st.json_mode:
        console.print(f"[green]✓[/] credencial {credential_id} ok")


# -- shell -----------------------------------------------------------------------

_SHELL_HELP = """[bold]Comandos[/] (a `/` é opcional; qualquer comando da CLI funciona aqui)
  /agents              escolher um agente → testar, ver, editar, versões
  /chat <agente>       conversar direto com um agente
  /tools               escolher uma tool → ver e invocar
  /collections         bases de conhecimento (RAG) dos agentes
  /runs                execuções recentes   ·  /runs show <run_id>
  /providers           provedores de modelo ·  /credentials  chaves cadastradas
  /health              diagnóstico
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
            command.main(args=globals_ + hoist_global_flags(args), prog_name="kuro", standalone_mode=False)
        except click.exceptions.Exit:
            pass
        except click.ClickException as exc:
            exc.show()
        except click.exceptions.Abort:
            console.print()
        except KeyboardInterrupt:
            console.print()
        except SystemExit as exc:  # um comando que chamou sys.exit não derruba o shell
            err_console.print(f"[dim](comando encerrou com código {exc.code})[/]")
        except Exception:  # noqa: BLE001 - erro inesperado não pode matar o shell em silêncio
            err_console.print_exception(max_frames=5)
            err_console.print("[red]erro inesperado no comando acima[/] — o shell continua; /sair para sair")


GLOBAL_FLAGS = ("--json", "--no-input")


def hoist_global_flags(argv: list[str]) -> list[str]:
    """Aceita `--json`/`--no-input` em qualquer posição (`kuro agents list --json`),
    não só antes do comando — é o primeiro erro que uma IA comete. Para antes de `--`."""
    head, sep, tail = (argv[: argv.index("--")], ["--"], argv[argv.index("--") + 1 :]) if "--" in argv else (argv, [], [])
    flags = [a for a in head if a in GLOBAL_FLAGS]
    return flags + [a for a in head if a not in GLOBAL_FLAGS] + sep + tail


def main() -> None:
    # Windows: sem isto, texto com acento quebra num pipe (stdout/stderr em cp1252)
    # e chega corrompido quando vem por stdin (`type doc.txt | kuro collections add`).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    app(args=hoist_global_flags(sys.argv[1:]), prog_name="kuro")


if __name__ == "__main__":
    main()
