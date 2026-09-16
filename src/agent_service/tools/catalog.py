"""Catálogo de toolkits padrão do Agno oferecidas para tools `kind="builtin"`.

Curado, não o pacote `agno.tools.*` inteiro: cada entrada aqui é uma toolkit
que já roda sem infraestrutura extra (ou só com uma chave/credencial que o
próprio usuário informa ao criar a tool pela API/UI — nunca um nome de
classe/módulo arbitrário vindo da API, para não virar um jeito de instanciar
qualquer coisa do Agno com kwargs livres). Para adicionar uma nova entrada:
importe a toolkit dentro da própria `factory` (import tardio: algumas pedem
um pacote opcional, só necessário se a tool for de fato usada — ver extra
`tools` no `pyproject.toml`) e descreva os parâmetros em `params`.
"""

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

ParamType = Literal["string", "integer", "boolean"]


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: ParamType
    label: str
    description: str = ""
    required: bool = False
    secret: bool = False
    """Mascarado nas respostas da API (ex.: senha de app do e-mail)."""
    default: Any = None


@dataclass(frozen=True)
class BuiltinToolSpec:
    builtin_id: str
    label: str
    description: str
    params: list[ParamSpec] = field(default_factory=list)
    factory: Callable[[dict[str, Any], str], Any] = field(repr=False, default=lambda params, tool_name: None)
    """`(params_validados, tool_name) -> Toolkit` do Agno. Import tardio dentro da função."""


def _tools_base_dir(tool_name: str) -> Path:
    """Diretório isolado por tool para toolkits que leem/escrevem arquivo —
    nunca o código-fonte do serviço nem um caminho escolhido pelo usuário."""
    base = Path(tempfile.gettempdir()) / "agent-service-tools" / tool_name
    base.mkdir(parents=True, exist_ok=True)
    return base


def _web_search(params: dict[str, Any], _tool_name: str) -> Any:
    try:
        from agno.tools.duckduckgo import DuckDuckGoTools
    except ImportError as exc:  # pragma: no cover - depende do extra opcional
        raise RuntimeError(
            "Pacote 'ddgs' não instalado — rode `uv sync --extra tools` no agent-service."
        ) from exc
    return DuckDuckGoTools(
        enable_news=params.get("enable_news", True),
        fixed_max_results=params.get("max_results") or None,
        region=params.get("region") or None,
    )


def _calculator(_params: dict[str, Any], _tool_name: str) -> Any:
    from agno.tools.calculator import CalculatorTools

    return CalculatorTools()


def _hackernews(_params: dict[str, Any], _tool_name: str) -> Any:
    from agno.tools.hackernews import HackerNewsTools

    return HackerNewsTools()


def _reasoning(_params: dict[str, Any], _tool_name: str) -> Any:
    from agno.tools.reasoning import ReasoningTools

    return ReasoningTools(add_instructions=True)


def _email(params: dict[str, Any], _tool_name: str) -> Any:
    from agno.tools.email import EmailTools

    return EmailTools(
        receiver_email=params.get("receiver_email") or None,
        sender_name=params.get("sender_name") or None,
        sender_email=params.get("sender_email") or None,
        sender_passkey=params.get("sender_passkey") or None,
    )


def _files(params: dict[str, Any], tool_name: str) -> Any:
    from agno.tools.file import FileTools

    return FileTools(
        base_dir=_tools_base_dir(tool_name),
        enable_delete_file=params.get("enable_delete_file", False),
    )


def _sleep(_params: dict[str, Any], _tool_name: str) -> Any:
    from agno.tools.sleep import SleepTools

    return SleepTools()


BUILTIN_CATALOG: dict[str, BuiltinToolSpec] = {
    spec.builtin_id: spec
    for spec in [
        BuiltinToolSpec(
            builtin_id="web_search",
            label="Busca na web (DuckDuckGo)",
            description="Pesquisa na web e notícias. Requer o extra `tools` instalado no serviço.",
            params=[
                ParamSpec("max_results", "integer", "Máx. de resultados", default=None),
                ParamSpec("enable_news", "boolean", "Incluir notícias", default=True),
                ParamSpec("region", "string", "Região (ex.: br-pt)", default=None),
            ],
            factory=_web_search,
        ),
        BuiltinToolSpec(
            builtin_id="calculator",
            label="Calculadora",
            description="Operações aritméticas exatas (soma, potência, fatorial, primalidade...).",
            factory=_calculator,
        ),
        BuiltinToolSpec(
            builtin_id="hackernews",
            label="Hacker News",
            description="Lê as histórias em alta e detalhes de usuários do Hacker News (API pública).",
            factory=_hackernews,
        ),
        BuiltinToolSpec(
            builtin_id="reasoning",
            label="Raciocínio estruturado",
            description="Dá ao agente as funções think/analyze do Agno para planejar antes de responder.",
            factory=_reasoning,
        ),
        BuiltinToolSpec(
            builtin_id="email",
            label="Enviar e-mail (SMTP)",
            description="Envia e-mails via Gmail SMTP. Efeito colateral real — configure com uma senha de app.",
            params=[
                ParamSpec("receiver_email", "string", "E-mail de destino", required=True),
                ParamSpec("sender_name", "string", "Nome do remetente"),
                ParamSpec("sender_email", "string", "E-mail remetente (Gmail)", required=True),
                ParamSpec("sender_passkey", "string", "Senha de app do remetente", required=True, secret=True),
            ],
            factory=_email,
        ),
        BuiltinToolSpec(
            builtin_id="files",
            label="Arquivos (sandbox)",
            description="Lê, lista e grava arquivos num diretório isolado por tool no próprio container "
            "(nunca o código do serviço nem um caminho escolhido pelo usuário).",
            params=[ParamSpec("enable_delete_file", "boolean", "Permitir excluir arquivos", default=False)],
            factory=_files,
        ),
        BuiltinToolSpec(
            builtin_id="sleep",
            label="Aguardar (debug)",
            description="Pausa a execução por N segundos — só para testar timeouts/streaming.",
            factory=_sleep,
        ),
    ]
}


def list_builtin_catalog() -> list[BuiltinToolSpec]:
    return sorted(BUILTIN_CATALOG.values(), key=lambda s: s.builtin_id)


def get_builtin_spec(builtin_id: str) -> BuiltinToolSpec | None:
    return BUILTIN_CATALOG.get(builtin_id)


class BuiltinConfigError(ValueError):
    pass


_TYPE_CHECK: dict[ParamType, type] = {"string": str, "integer": int, "boolean": bool}


def validate_builtin_config(config: dict[str, Any]) -> dict[str, Any]:
    """Confere `builtin_id` e valida/normaliza `params` contra `ParamSpec.params`
    do catálogo — tipo, obrigatoriedade e nomes desconhecidos."""
    builtin_id = config.get("builtin_id")
    spec = get_builtin_spec(builtin_id) if isinstance(builtin_id, str) else None
    if spec is None:
        raise BuiltinConfigError(f"builtin_id desconhecido: {builtin_id!r}")

    raw_params = config.get("params") or {}
    if not isinstance(raw_params, dict):
        raise BuiltinConfigError("params deve ser um objeto")

    known = {p.name: p for p in spec.params}
    unknown = set(raw_params) - set(known)
    if unknown:
        raise BuiltinConfigError(f"parâmetros desconhecidos para {builtin_id!r}: {sorted(unknown)}")

    normalized: dict[str, Any] = {}
    for p in spec.params:
        if p.name in raw_params and raw_params[p.name] is not None:
            value = raw_params[p.name]
            expected = _TYPE_CHECK[p.type]
            if expected is bool and not isinstance(value, bool):
                raise BuiltinConfigError(f"{p.name} deve ser booleano")
            if expected is int and not (isinstance(value, int) and not isinstance(value, bool)):
                raise BuiltinConfigError(f"{p.name} deve ser inteiro")
            if expected is str and not isinstance(value, str):
                raise BuiltinConfigError(f"{p.name} deve ser texto")
            normalized[p.name] = value
        elif p.required:
            raise BuiltinConfigError(f"{p.name} é obrigatório para {builtin_id!r}")
        elif p.default is not None:
            normalized[p.name] = p.default

    return {"builtin_id": builtin_id, "params": normalized}
