"""`kuro dash`: o que está acontecendo no Kuro agora, sem abrir o console web.

Duas abas:

- **Execuções**: as últimas execuções, atualizadas sozinhas (consulta repetida, como
  `kuro runs tail`), com filtro por agente e status. Enter abre o trace: mensagem,
  resposta, spans de modelo e tools com entrada e saída, e as notas.
- **Panorama**: os números do dashboard dos Logs (`/observability/overview`) —
  totais contra o período anterior, uma linha por agente e as tools falhando.

Todo acesso à API roda numa thread (`@work(thread=True)`): o `Client` é síncrono, e
uma chamada lenta não pode congelar a tela.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Select,
    Static,
    TabbedContent,
    TabPane,
    Tree,
)

from agent_service.cli.client import ApiError, Client, ServiceUnavailable

PREVIEW = 600  # caracteres da entrada/saída de um span mostrados no trace

PERIODS = [("últimas 24 h", 1), ("últimos 7 dias", 7), ("últimos 30 dias", 30)]


def describe_error(exc: Exception) -> str:
    if isinstance(exc, ApiError):
        if exc.status in (401, 403):
            return f"sem permissão (HTTP {exc.status}): use uma chave de escopo admin em KURO_API_KEY"
        if exc.status == 501:
            return "o panorama só existe no trace store local (TRACE_STORE_BACKEND=langfuse responde 501)"
        detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail, ensure_ascii=False)
        return f"{detail} (HTTP {exc.status})"
    return str(exc)


def _when(value: Any) -> str:
    return str(value or "")[5:16].replace("T", " ")


def _cost(value: float | None) -> str:
    return "—" if value is None else f"US$ {value:.4f}"


def _status(status: str) -> Text:
    return Text("ok", style="green") if status == "success" else Text(status, style="bold red")


def _one_line(text: str | None, limit: int = 70) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _preview(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= PREVIEW else text[:PREVIEW] + f"… (+{len(text) - PREVIEW})"


def _delta(current: float | None, previous: float | None) -> str:
    if current is None or not previous:
        return ""
    change = (current - previous) / previous
    return f" ({'+' if change >= 0 else ''}{change:.0%})"


# -- trace de uma execução -----------------------------------------------------------


class RunScreen(Screen):
    BINDINGS = [Binding("escape,q", "app.pop_screen", "voltar")]

    def __init__(self, client: Client, run_id: str) -> None:
        super().__init__()
        self.client = client
        self.run_id = run_id

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static(f"carregando {self.run_id}…", id="run-head")
            yield Static(id="run-io")
            yield Tree("spans", id="spans")
            yield Static(id="scores")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(Tree).show_root = False
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        try:
            trace = self.client.run_trace(self.run_id)
        except (ApiError, ServiceUnavailable) as exc:
            self.app.call_from_thread(self.query_one("#run-head", Static).update, Text(describe_error(exc), style="red"))
            return
        self.app.call_from_thread(self.show, trace)

    def show(self, trace: dict[str, Any]) -> None:
        run = trace["run"]
        version = f" · v{run['agent_version']}" if run.get("agent_version") else ""
        latency = f" · {run['latency_ms'] / 1000:.1f}s" if run.get("latency_ms") else ""
        head = Text.assemble(
            (run["agent_type"], "bold"),
            f"{version} · ",
            _status(run["status"]),
            f" · {run['total_tokens']} tokens · {_cost(run.get('cost_usd'))}{latency}\n",
            (f"run {run['run_id']} · sessão {run.get('session_id') or '—'} · {_when(run['started_at'])}", "dim"),
        )
        if run.get("status_message"):
            head.append(f"\n{run['status_message']}", style="red")
        self.query_one("#run-head", Static).update(head)
        self.query_one("#run-io", Static).update(
            Text.assemble(
                ("\nmensagem\n", "bold cyan"),
                run.get("message") or "—",
                ("\n\nresposta\n", "bold magenta"),
                run.get("output") or "—",
                "\n",
            )
        )

        tree = self.query_one(Tree)
        tree.clear()
        spans = sorted(trace.get("spans") or [], key=lambda s: str(s["started_at"]))
        ids = {s["id"] for s in spans}
        nodes: dict[str, Any] = {}
        for span in spans:
            parent = nodes.get(span.get("parent_id")) if span.get("parent_id") in ids else tree.root
            latency = f" {span['latency_ms']:.0f}ms" if span.get("latency_ms") else ""
            failed = span["level"] not in ("DEFAULT", "DEBUG")
            label = Text.assemble(
                (span["type"].lower(), "dim"), " ", (span["name"], "bold red" if failed else "bold"), (latency, "dim")
            )
            node = (parent or tree.root).add(label, expand=failed)
            if span.get("status_message"):
                node.add_leaf(Text(span["status_message"], style="red"))
            if span.get("input") is not None:
                node.add_leaf(Text.assemble(("entrada ", "cyan"), _preview(span["input"])))
            if span.get("output") is not None:
                node.add_leaf(Text.assemble(("saída ", "magenta"), _preview(span["output"])))
            nodes[span["id"]] = node
            if failed:  # a falha não pode ficar escondida dentro de um nó fechado
                ancestor = node.parent
                while ancestor is not None:
                    ancestor.expand()
                    ancestor = ancestor.parent
        tree.root.expand()

        scores = trace.get("scores") or []
        self.query_one("#scores", Static).update(
            "\n".join(f"nota {s['name']} = {s['value']}  {s.get('comment') or ''}" for s in scores) or ""
        )


# -- abas --------------------------------------------------------------------------


class RunsPane(TabPane):
    """Últimas execuções, atualizadas a cada `interval` segundos."""

    def __init__(self, client: Client, interval: float, agent: str | None) -> None:
        super().__init__("Execuções", id="runs-pane")
        self.client = client
        self.interval = interval
        self.initial_agent = agent or ""
        self.paused = False
        self.shown: list[str] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="filters"):
            yield Input(value=self.initial_agent, placeholder="agente (agent_type)", id="agent")
            yield Select([("só sucesso", "success"), ("só erro", "error")], prompt="status: todos", id="status")
            yield Checkbox("sem testes (dry_run)", id="no-tests")
        yield DataTable(id="runs", cursor_type="row", zebra_stripes=True)
        yield Static(id="runs-status")

    def on_mount(self) -> None:
        table = self.query_one("#runs", DataTable)
        table.add_columns("quando", "agente", "v", "status", "tokens", "tempo", "custo", "mensagem")
        # Foco na tabela, não no filtro: com o filtro focado, `q`/`r`/`p` virariam texto.
        table.focus()
        self.refresh_runs()
        self.set_interval(self.interval, self.tick)

    def tick(self) -> None:
        if not self.paused:
            self.refresh_runs()

    def filters(self) -> dict[str, Any]:
        status = self.query_one("#status", Select).value
        return {
            "agent_type": self.query_one("#agent", Input).value.strip() or None,
            "status": status if isinstance(status, str) else None,
            "include_dry_run": False if self.query_one("#no-tests", Checkbox).value else None,
            "limit": 50,
        }

    def refresh_runs(self) -> None:
        # Os widgets só são lidos aqui, na thread da interface; o worker recebe os valores.
        self.fetch_runs(self.filters())

    @work(thread=True, exclusive=True, group="runs")
    def fetch_runs(self, filters: dict[str, Any]) -> None:
        try:
            page = self.client.list_runs(**filters)
        except (ApiError, ServiceUnavailable) as exc:
            self.app.call_from_thread(self.set_status, Text(describe_error(exc), style="red"))
            return
        self.app.call_from_thread(self.show, page["items"])

    def show(self, runs: list[dict[str, Any]]) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        ids = [r["run_id"] for r in runs]
        if ids != self.shown:
            table = self.query_one("#runs", DataTable)
            selected = self.selected_run()
            table.clear()
            for r in runs:
                latency = f"{r['latency_ms'] / 1000:.1f}s" if (r.get("latency_ms") or 0) > 0 else "—"
                table.add_row(
                    _when(r["started_at"]),
                    r["agent_type"],
                    str(r.get("agent_version") or "—"),
                    _status(r["status"]),
                    str(r["total_tokens"]),
                    latency,
                    _cost(r.get("cost_usd")),
                    _one_line(r.get("message")),
                    key=r["run_id"],
                )
            if selected in ids:
                table.move_cursor(row=ids.index(selected))
            self.shown = ids
        state = " · [b]pausado[/b] (p retoma)" if self.paused else ""
        self.set_status(f"{len(runs)} execuções · atualizado às {now}{state} · enter abre o trace")

    def set_status(self, message: str | Text) -> None:
        self.query_one("#runs-status", Static).update(message)

    def selected_run(self) -> str | None:
        table = self.query_one("#runs", DataTable)
        if table.row_count == 0:
            return None
        return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value

    @on(Input.Submitted, "#agent")
    @on(Select.Changed, "#status")
    @on(Checkbox.Changed, "#no-tests")
    def filters_changed(self) -> None:
        self.shown = []
        self.refresh_runs()

    @on(DataTable.RowSelected, "#runs")
    def open_run(self, event: DataTable.RowSelected) -> None:
        self.app.push_screen(RunScreen(self.client, event.row_key.value))


class OverviewPane(TabPane):
    """O panorama do dashboard dos Logs: precisa de escopo admin."""

    def __init__(self, client: Client, agent: str | None) -> None:
        super().__init__("Panorama", id="overview-pane")
        self.client = client
        self.agent = agent

    def compose(self) -> ComposeResult:
        with Horizontal(id="period-bar"):
            yield Select(PERIODS, value=7, allow_blank=False, id="period")
            yield Checkbox("incluir testes (dry_run)", id="with-tests")
        yield Static(id="totals")
        yield Static("[b]Agentes[/b]", classes="section")
        yield DataTable(id="agents", cursor_type="row", zebra_stripes=True)
        yield Static("[b]Tools falhando[/b]", classes="section")
        yield DataTable(id="tool-failures", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        self.query_one("#agents", DataTable).add_columns(
            "agente", "execuções", "erros", "tool falhou", "tokens", "custo", "👍/👎", "última"
        )
        self.query_one("#tool-failures", DataTable).add_columns("tool", "falha", "vezes", "agentes", "HTTP", "última")
        self.load()
        self.set_interval(60, self.load)

    @on(Select.Changed, "#period")
    @on(Checkbox.Changed, "#with-tests")
    def period_changed(self) -> None:
        self.load()

    def load(self) -> None:
        days = self.query_one("#period", Select).value
        since = datetime.now(UTC) - timedelta(days=days if isinstance(days, int) else 7)
        self.fetch(
            {
                "since": since.isoformat(),
                "agent_type": self.agent,
                "include_dry_run": True if self.query_one("#with-tests", Checkbox).value else None,
            }
        )

    @work(thread=True, exclusive=True, group="overview")
    def fetch(self, params: dict[str, Any]) -> None:
        try:
            overview = self.client.overview(**params)
        except (ApiError, ServiceUnavailable) as exc:
            self.app.call_from_thread(self.query_one("#totals", Static).update, Text(describe_error(exc), style="red"))
            return
        self.app.call_from_thread(self.show, overview)

    def show(self, overview: dict[str, Any]) -> None:
        totals, previous = overview["totals"], overview.get("previous") or {}
        runs = totals["runs"]
        error_rate = totals["errors"] / runs if runs else 0
        self.query_one("#totals", Static).update(
            Text.assemble(
                ("execuções ", "dim"), (str(runs), "bold"), _delta(runs, previous.get("runs")),
                ("   erros ", "dim"), (f"{totals['errors']} ({error_rate:.0%})", "bold red" if totals["errors"] else "bold"),
                ("   tool falhou ", "dim"), (str(totals["tool_failure_runs"]), "bold yellow" if totals["tool_failure_runs"] else "bold"),
                ("   sessões ", "dim"), (str(totals["sessions"]), "bold"),
                ("   tokens ", "dim"), (f"{totals['total_tokens']:,}".replace(",", "."), "bold"),
                _delta(totals["total_tokens"], previous.get("total_tokens")),
                ("   custo ", "dim"), (_cost(totals.get("cost_usd")), "bold"),
                _delta(totals.get("cost_usd"), previous.get("cost_usd")),
                ("   👍 ", "dim"), str(totals["feedback_up"]), ("  👎 ", "dim"), str(totals["feedback_down"]),
                "\n",
            )
        )
        agents = self.query_one("#agents", DataTable)
        agents.clear()
        for row in overview["agents"]:
            t = row["totals"]
            agents.add_row(
                row["agent_type"],
                str(t["runs"]),
                Text(str(t["errors"]), style="red" if t["errors"] else ""),
                Text(str(t["tool_failure_runs"]), style="yellow" if t["tool_failure_runs"] else ""),
                str(t["total_tokens"]),
                _cost(t.get("cost_usd")),
                f"{t['feedback_up']}/{t['feedback_down']}",
                _when(row["last_run_at"]),
                key=row["agent_type"],
            )
        failures = self.query_one("#tool-failures", DataTable)
        failures.clear()
        for row in overview["tool_failures"]:
            failures.add_row(
                row["tool_name"],
                row["failure"],
                str(row["count"]),
                ", ".join(row["agent_types"]),
                ", ".join(str(s) for s in row.get("http_status") or []) or "—",
                _when(row["last_at"]),
            )


# -- aplicação -----------------------------------------------------------------------


class KuroDash(App):
    TITLE = "kuro dash"
    CSS = """
    #filters, #period-bar { height: auto; padding: 0 1; }
    #filters Input { width: 32; }
    #filters Select, #period-bar Select { width: 26; }
    #runs { height: 1fr; }
    #runs-status { height: 1; padding: 0 1; color: $text-muted; }
    #totals { padding: 1 1 0 1; }
    .section { padding: 1 1 0 1; }
    #agents, #tool-failures { height: auto; max-height: 16; }
    #run-head, #run-io, #scores { padding: 0 1; }
    #spans { height: auto; padding: 0 1; }
    """
    BINDINGS = [
        Binding("q", "quit", "sair"),
        Binding("r", "refresh", "atualizar"),
        Binding("p", "pause", "pausar"),
        Binding("1", "tab('runs-pane')", "execuções", show=False),
        Binding("2", "tab('overview-pane')", "panorama", show=False),
    ]

    def __init__(self, client: Client, *, interval: float = 3.0, agent: str | None = None) -> None:
        super().__init__()
        self.client = client
        self.interval = interval
        self.agent = agent
        self.sub_title = client.base_url

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="runs-pane"):
            yield RunsPane(self.client, self.interval, self.agent)
            yield OverviewPane(self.client, self.agent)
        yield Footer()

    def on_mount(self) -> None:
        self.check_service()

    @work(thread=True)
    def check_service(self) -> None:
        try:
            version = self.client.health().get("version")
        except (ApiError, ServiceUnavailable) as exc:
            self.call_from_thread(self.notify, describe_error(exc), severity="error", timeout=10)
            return
        if version:
            self.call_from_thread(setattr, self, "sub_title", f"{self.client.base_url} · v{version}")

    def action_tab(self, pane: str) -> None:
        self.query_one(TabbedContent).active = pane

    def action_refresh(self) -> None:
        self.query_one(RunsPane).refresh_runs()
        self.query_one(OverviewPane).load()

    def action_pause(self) -> None:
        pane = self.query_one(RunsPane)
        pane.paused = not pane.paused
        pane.refresh_runs()
