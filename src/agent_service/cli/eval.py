"""`kuro eval`: roda um dataset de casos num agente analista e diz se a decisão bate.

É o "provo que não piorou" antes de promover: cada caso tem a entrada e a
decisão esperada (ex.: a que o agente legado tomou), e a comparação é
**determinística**, campo a campo — nada de LLM-juiz decidindo se `acao` ou
`qtd_parcelas` estão certos.

Formato do dataset (JSONL, um caso por linha):

    {"id": "c1", "input": {...} | "texto", "dependencies": {...}, "expected": {"acao": "responder", ...}}

`input` objeto vira JSON no `document` do `/analyze`. Só os campos presentes em
`expected` são comparados (objetos aninhados viram caminhos: `acordo.qtd_parcelas`),
ou só os de `--fields`.

Regras de política (`--rules regras.json`) valem para **toda** saída, com ou sem
`expected` — são o que não pode acontecer nunca:

    [{"name": "R6 nunca fica parado", "field": "acao", "op": "ne", "value": "nada"},
     {"name": "acordo só com identidade", "when": {"field": "acao", "op": "eq", "value": "efetivar_acordo"},
      "field": "identidade_confirmada", "op": "eq", "value": true},
     {"name": "teto", "field": "acordo.valor_acordo", "op": "lte", "value": {"$dep": "teto"}}]

`op`: eq, ne, in, not_in, lt, lte, gt, gte, exists, not_exists. `{"$dep": "a.b"}`
lê o valor das `dependencies` do caso. Um caso passa quando todos os campos
comparados batem e nenhuma regra é violada.

Saída: código 0 se a taxa de casos aprovados atinge `--min-pass` e nenhuma regra
foi violada; 1 caso contrário. Com `--compare outro-agente`, os dois rodam o
mesmo dataset e o código é 1 se o candidato ficar pior que o comparado.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import typer
from rich.table import Table

from agent_service.cli.client import ApiError, ServiceUnavailable
from agent_service.cli.common import EXIT_FAILED, EXIT_USAGE, call, console, emit, fail, fail_from, state

_MISSING = object()
_OPS = {"eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte", "exists", "not_exists"}


# -- lógica pura (testada sem serviço) ---------------------------------------------


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """`{"a": {"b": 1}}` → `{"a.b": 1}`. Listas ficam inteiras (comparadas como valor)."""
    if isinstance(value, dict) and value:
        out: dict[str, Any] = {}
        for key, item in value.items():
            out.update(flatten(item, f"{prefix}{key}."))
        return out
    return {prefix[:-1]: value} if prefix else {}


def get_path(value: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _equal(expected: Any, actual: Any, tolerance: float) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(expected - actual) <= tolerance
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip() == actual.strip()
    return expected == actual


def compare(expected: dict[str, Any], actual: dict[str, Any], fields: list[str] | None, tolerance: float) -> list[dict[str, Any]]:
    """Campos que não bateram: `[{field, expected, actual}]`."""
    wanted = flatten(expected)
    if fields:
        wanted = {f: get_path(expected, f) for f in fields if get_path(expected, f) is not _MISSING}
    mismatches = []
    for field, exp in wanted.items():
        got = get_path(actual, field)
        if got is _MISSING or not _equal(exp, got, tolerance):
            mismatches.append({"field": field, "expected": exp, "actual": None if got is _MISSING else got})
    return mismatches


def _resolve(value: Any, dependencies: dict[str, Any]) -> Any:
    if isinstance(value, dict) and set(value) == {"$dep"}:
        found = get_path(dependencies, value["$dep"])
        return None if found is _MISSING else found
    return value


def _holds(actual: Any, op: str, target: Any) -> bool:
    if op == "exists":
        return actual is not _MISSING and actual is not None
    if op == "not_exists":
        return actual is _MISSING or actual is None
    if actual is _MISSING:
        return False
    try:
        if op == "eq":
            return actual == target
        if op == "ne":
            return actual != target
        if op == "in":
            return actual in target
        if op == "not_in":
            return actual not in target
        if op == "lt":
            return actual < target
        if op == "lte":
            return actual <= target
        if op == "gt":
            return actual > target
        if op == "gte":
            return actual >= target
    except TypeError:
        return False
    raise ValueError(op)


def validate_rules(rules: Any) -> list[str]:
    """Problemas no arquivo de regras — melhor recusar antes de gastar tokens."""
    if not isinstance(rules, list):
        return ["o arquivo de regras precisa ser uma lista"]
    problems = []
    for i, rule in enumerate(rules):
        label = rule.get("name", f"#{i + 1}") if isinstance(rule, dict) else f"#{i + 1}"
        for part in (rule, rule.get("when")) if isinstance(rule, dict) else (rule,):
            if part is None:
                continue
            if not isinstance(part, dict) or "field" not in part or part.get("op") not in _OPS:
                problems.append(f"regra {label}: precisa de `field` e `op` em {sorted(_OPS)}")
    return problems


def check_rules(rules: list[dict[str, Any]], actual: dict[str, Any], dependencies: dict[str, Any]) -> list[dict[str, Any]]:
    """Regras violadas por esta saída: `[{rule, field, op, expected, actual}]`."""
    violations = []
    for i, rule in enumerate(rules):
        when = rule.get("when")
        if when and not _holds(get_path(actual, when["field"]), when["op"], _resolve(when.get("value"), dependencies)):
            continue
        got = get_path(actual, rule["field"])
        target = _resolve(rule.get("value"), dependencies)
        if not _holds(got, rule["op"], target):
            violations.append(
                {
                    "rule": rule.get("name", f"#{i + 1}"),
                    "field": rule["field"],
                    "op": rule["op"],
                    "expected": target,
                    "actual": None if got is _MISSING else got,
                }
            )
    return violations


def summarize(agent_type: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    compared = [r for r in results if r["error"] is None]
    fields_total = sum(r["fields_compared"] for r in compared)
    fields_ok = sum(r["fields_compared"] - len(r["mismatches"]) for r in compared)
    passed = sum(1 for r in results if r["passed"])
    versions = {(r.get("agent_version"), r.get("config_hash")) for r in compared}
    return {
        "agent_type": agent_type,
        "agent_version": next(iter(versions))[0] if len(versions) == 1 else None,
        "config_hash": next(iter(versions))[1] if len(versions) == 1 else None,
        "cases": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "errors": sum(1 for r in results if r["error"] is not None),
        "pass_rate": round(passed / len(results), 4) if results else 0.0,
        "field_match_rate": round(fields_ok / fields_total, 4) if fields_total else None,
        "policy_violations": sum(len(r["violations"]) for r in results),
    }


# -- execução ------------------------------------------------------------------------


def _load_cases(st: Any, path: str) -> list[dict[str, Any]]:
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError as exc:
        fail(st, f"não consegui ler {path}: {exc}", EXIT_USAGE)
    cases = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except ValueError as exc:
            fail(st, f"{path}:{number}: JSON inválido ({exc})", EXIT_USAGE)
        if not isinstance(case, dict) or "input" not in case:
            fail(st, f"{path}:{number}: cada caso precisa de `input` (e normalmente de `expected`)", EXIT_USAGE)
        case.setdefault("id", str(number))
        cases.append(case)
    if not cases:
        fail(st, f"{path}: nenhum caso", EXIT_USAGE)
    return cases


def _run_case(
    st: Any,
    agent_type: str,
    case: dict[str, Any],
    fields: list[str] | None,
    rules: list[dict[str, Any]],
    tolerance: float,
    score: bool,
) -> dict[str, Any]:
    document = case["input"] if isinstance(case["input"], str) else json.dumps(case["input"], ensure_ascii=False)
    dependencies = case.get("dependencies") or {}
    expected = case.get("expected") or {}
    base: dict[str, Any] = {"id": case["id"], "run_id": None, "error": None, "result": None}
    try:
        response = st.client.analyze(
            {"agent_type": agent_type, "document": document, "dependencies": dependencies or None}
        )
    except (ServiceUnavailable, ApiError) as exc:
        detail = exc.detail if isinstance(exc, ApiError) else str(exc)
        return {**base, "error": str(detail), "passed": False, "mismatches": [], "violations": [], "fields_compared": 0}

    result = response["result"]
    mismatches = compare(expected, result, fields, tolerance)
    violations = check_rules(rules, result, dependencies)
    fields_compared = len(fields) if fields else len(flatten(expected))
    passed = not mismatches and not violations
    if score:
        try:
            st.client.score(
                {"run_id": response["run_id"], "name": "eval", "value": 1 if passed else 0, "comment": f"caso {case['id']}"}
            )
        except (ServiceUnavailable, ApiError):
            pass  # a nota é um extra; o relatório continua valendo
    return {
        **base,
        "run_id": response["run_id"],
        "agent_version": response.get("agent_version"),
        "config_hash": response.get("config_hash"),
        "result": result,
        "passed": passed,
        "mismatches": mismatches,
        "violations": violations,
        "fields_compared": fields_compared,
    }


def _run_all(st: Any, agent_type: str, cases: list[dict[str, Any]], concurrency: int, **options: Any) -> list[dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(lambda case: _run_case(st, agent_type, case, **options), cases))


def _render(report: dict[str, Any]) -> None:
    for summary, results in [(report["summary"], report["results"])] + (
        [(report["compare"]["summary"], report["compare"]["results"])] if report.get("compare") else []
    ):
        version = f" v{summary['agent_version']}" if summary["agent_version"] else ""
        console.print(
            f"\n[bold]{summary['agent_type']}[/]{version}  "
            f"{summary['passed']}/{summary['cases']} casos ok ({summary['pass_rate']:.0%})  "
            f"campos: {summary['field_match_rate'] if summary['field_match_rate'] is not None else '—'}  "
            f"violações: {summary['policy_violations']}  erros: {summary['errors']}"
        )
        failed = [r for r in results if not r["passed"]]
        if failed:
            table = Table(show_edge=False, header_style="bold")
            for column in ("caso", "o que falhou"):
                table.add_column(column)
            for r in failed[:30]:
                reasons = [r["error"]] if r["error"] else []
                reasons += [f"{m['field']}: esperado {m['expected']!r}, veio {m['actual']!r}" for m in r["mismatches"]]
                reasons += [f"[red]regra {v['rule']}[/] ({v['field']} {v['op']} {v['expected']!r}; veio {v['actual']!r})" for v in r["violations"]]
                table.add_row(str(r["id"]), "\n".join(reasons))
            console.print(table)
    verdict = report["verdict"]
    color = "green" if verdict["ok"] else "red"
    console.print(f"\n[{color}]{'✓' if verdict['ok'] else '✗'} {verdict['reason']}[/]")


def eval_command(
    ctx: typer.Context,
    agent_type: str = typer.Argument(..., help="Agente candidato (kind='analysis'), ex.: r8-draft."),
    file: str = typer.Option(..., "--file", "-f", help="Dataset JSONL: {id, input, dependencies, expected} por linha."),
    rules_file: str | None = typer.Option(None, "--rules", "-r", help="Regras de política (JSON) que nenhuma saída pode violar."),
    fields: str | None = typer.Option(None, "--fields", help="Só estes campos (vírgula; caminho com ponto: acordo.qtd_parcelas)."),
    compare_with: str | None = typer.Option(None, "--compare", help="Roda o mesmo dataset neste agente (ex.: o de produção) e compara."),
    min_pass: float = typer.Option(0.9, "--min-pass", min=0.0, max=1.0, help="Fração mínima de casos aprovados para sair com 0."),
    tolerance: float = typer.Option(0.01, "--tolerance", min=0.0, help="Diferença aceita em campos numéricos."),
    concurrency: int = typer.Option(4, "--concurrency", "-c", min=1, max=16, help="Casos em paralelo."),
    no_score: bool = typer.Option(False, "--no-score", help="Não grava a nota `eval` (1/0) em cada run."),
) -> None:
    """Avalia um agente analista contra um dataset, de forma determinística.

    Ex.: `kuro eval r8-draft -f casos.jsonl --rules regras.json --compare r8 --json`.
    Sai com 1 se piorou (ou não atingiu --min-pass, ou violou alguma regra)."""
    st = state(ctx)
    for name in [agent_type] + ([compare_with] if compare_with else []):
        definition = call(st, st.client.get_agent, name)
        if definition.get("kind") != "analysis":
            fail(st, f"{name!r} não é um agente 'analysis' — o eval v0 compara saídas estruturadas", EXIT_USAGE)

    cases = _load_cases(st, file)
    rules: list[dict[str, Any]] = []
    if rules_file:
        try:
            rules = json.loads(open(rules_file, encoding="utf-8").read())
        except (OSError, ValueError) as exc:
            fail(st, f"não consegui ler as regras de {rules_file}: {exc}", EXIT_USAGE)
        if problems := validate_rules(rules):
            fail(st, "; ".join(problems), EXIT_USAGE)
    options = {
        "fields": [f.strip() for f in fields.split(",") if f.strip()] if fields else None,
        "rules": rules,
        "tolerance": tolerance,
        "score": not no_score,
    }

    try:
        results = _run_all(st, agent_type, cases, concurrency, **options)
        compare_results = _run_all(st, compare_with, cases, concurrency, **options) if compare_with else None
    except ServiceUnavailable as exc:
        fail_from(st, exc)

    summary = summarize(agent_type, results)
    report: dict[str, Any] = {"summary": summary, "results": results}
    if summary["errors"] == summary["cases"]:
        verdict = {"ok": False, "reason": "todos os casos falharam ao executar — veja `error` em cada um"}
    elif summary["policy_violations"]:
        verdict = {"ok": False, "reason": f"{summary['policy_violations']} violação(ões) de política"}
    elif compare_results is not None:
        other = summarize(compare_with, compare_results)
        report["compare"] = {"summary": other, "results": compare_results}
        worse = summary["passed"] < other["passed"]
        verdict = {
            "ok": not worse,
            "reason": f"{agent_type} {'pior que' if worse else 'não é pior que'} {compare_with} "
            f"({summary['passed']} × {other['passed']} casos ok)",
        }
    else:
        ok = summary["pass_rate"] >= min_pass
        verdict = {"ok": ok, "reason": f"{summary['pass_rate']:.0%} dos casos ok (mínimo {min_pass:.0%})"}
    report["verdict"] = verdict

    emit(st, report, _render)
    if not verdict["ok"]:
        raise typer.Exit(EXIT_FAILED)
