"""CRUD de tools + catálogo de builtins + um jeito de testar uma tool sem
precisar montar um agente inteiro em volta dela.

Três tipos (`kind`), a mesma tabela (`tools/store.py`) e o mesmo contrato:

- `builtin`: uma toolkit padrão do Agno (`GET /tools/catalog` lista as
  disponíveis e os parâmetros de cada uma).
- `api`: chama uma API HTTP existente, descrita em JSON — sem código
  (`agent_service/tools/api_tool.py` documenta o formato de `config`).
- `python`: uma função Python enviada pelo usuário, rodada num namespace
  restrito — best-effort, não uma sandbox forte (ver
  `agent_service/tools/python_tool.py`); desligada por padrão
  (`CUSTOM_PYTHON_TOOLS_ENABLED`).

Depois de criada, uma tool entra na lista de um agente pelo nome
(`AgentDefinitionIn.tools`), do mesmo jeito de sempre.
"""

import copy
import json
import re
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from agent_service.agents.store import list_definitions as list_agent_definitions
from agent_service.config import get_settings
from agent_service.tools import registry, secrets, store
from agent_service.tools.api_tool import ApiToolConfigError, required_dependencies, validate_api_config
from agent_service.tools.catalog import BuiltinConfigError, list_builtin_catalog, validate_builtin_config
from agent_service.tools.invoke import ToolUnavailableError
from agent_service.tools.invoke import invoke_tool as run_tool
from agent_service.tools.python_tool import PythonToolConfigError, validate_python_config
from agent_service.tools.registry import ToolBuildError
from agent_service.tools.sensitive import SECRET_MASK, get_slot, sensitive_slots, set_slot

router = APIRouter(prefix="/tools", tags=["tools"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_SECRET_MASK = SECRET_MASK
ToolKind = Literal["builtin", "api", "python"]


# -- validação/normalização por kind, e mascaramento de segredos -----------


def _validate_config(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    try:
        if kind == "builtin":
            return validate_builtin_config(config)
        if kind == "api":
            return validate_api_config(config)
        if kind == "python":
            return validate_python_config(config)
    except (BuiltinConfigError, ApiToolConfigError, PythonToolConfigError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=f"kind desconhecido: {kind!r}")


def _mask_config(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    """A config como sai em toda leitura (API, CLI, MCP, console): todo valor que parece
    segredo vira a máscara — o `auth`, os headers e os parâmetros fixos com nome sensível
    (`tools/sensitive.py`). Uma referência (`{{secret:NOME}}`) sai como está: não é o valor."""
    masked = copy.deepcopy(config)
    if kind == "api":
        for slot in sensitive_slots(masked):
            value = get_slot(masked, slot)
            if value and not secrets.references(value):
                set_slot(masked, slot, _SECRET_MASK)
    elif kind == "builtin":
        from agent_service.tools.catalog import get_builtin_spec

        spec = get_builtin_spec(masked.get("builtin_id", ""))
        if spec is not None:
            params = masked.get("params") or {}
            for p in spec.params:
                if p.secret and params.get(p.name):
                    params[p.name] = _SECRET_MASK
    return masked


def _unmask_config(kind: str, incoming: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    """Se o campo secreto veio de volta como a máscara (quem editou leu a tool e devolveu o
    valor mascarado sem mexer nele), restaura o valor guardado.

    O header ou parâmetro precisa continuar com o mesmo nome: renomeado com a máscara no
    valor, não há o que restaurar, e gravar a máscara trocaria o token por "••••••••" sem
    ninguém perceber — isso é 422 pedindo o valor."""
    merged = copy.deepcopy(incoming)
    if kind == "api":
        stored = {slot: get_slot(existing, slot) for slot in sensitive_slots(existing)}
        stored_params = {
            p.get("name"): p.get("value") for p in existing.get("parameters") or [] if p.get("source") == "const"
        }
        for slot in sensitive_slots(merged):
            if get_slot(merged, slot) != _SECRET_MASK:
                continue
            if slot[0] == "parameters":
                name = merged["parameters"][slot[1]].get("name")
                if name not in stored_params:
                    raise HTTPException(status_code=422, detail=_mask_left(f"parâmetro {name!r}"))
                set_slot(merged, slot, stored_params[name])
            elif slot in stored:
                set_slot(merged, slot, stored[slot])
            else:
                raise HTTPException(status_code=422, detail=_mask_left(f"{slot[0]}.{slot[1]}"))
    elif kind == "builtin":
        from agent_service.tools.catalog import get_builtin_spec

        spec = get_builtin_spec(merged.get("builtin_id", ""))
        if spec is not None:
            params = merged.get("params") or {}
            existing_params = existing.get("params") or {}
            for p in spec.params:
                if p.secret and params.get(p.name) == _SECRET_MASK:
                    params[p.name] = existing_params.get(p.name)
    return merged


def _mask_left(where: str) -> str:
    return (
        f"{where} veio com o valor mascarado ({_SECRET_MASK}), mas não há valor guardado com esse nome para "
        "restaurar (nome novo ou renomeado, ou uma tool nova criada a partir da leitura de outra). Mande o "
        "valor de verdade — de preferência uma referência {{secret:NOME}} (kuro secrets set NOME)."
    )


def _check_secrets(kind: str, config: dict[str, Any]) -> None:
    """Na gravação: nada de máscara sobrando (vira o valor do header sem ninguém notar) e
    toda referência apontando para um segredo que existe."""
    if kind == "builtin":
        return
    if _SECRET_MASK in json.dumps(config, ensure_ascii=False):
        raise HTTPException(status_code=422, detail=_mask_left("um campo"))
    missing = sorted(name for name in secrets.references(config) if not secrets.exists(name))
    if missing:
        nomes = ", ".join(missing)
        raise HTTPException(
            status_code=422,
            detail=f"a config referencia segredos que não existem: {nomes}. Cadastre antes com "
            f"`kuro secrets set {missing[0]}` (o valor vem do ambiente ou do stdin, nunca da linha de comando).",
        )


def _row_out(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "config": _mask_config(row["kind"], row["config"])}


# -- schemas -----------------------------------------------------------


class ToolIn(BaseModel):
    tool_name: str = Field(..., description="Slug estável, usado em AgentDefinition.tools")
    kind: ToolKind
    label: str
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    side_effect: bool | None = Field(
        default=None,
        description="A tool muda algo no sistema chamado (grava, cobra, transfere, envia)? "
        "Vazio = ainda não classificada: num teste (dry_run) ela não é chamada, por precaução.",
    )
    dry_run_support: bool | None = Field(
        default=None,
        description="A API da tool trata o header X-Kuro-Dry-Run (simula em vez de gravar)? Num teste (dry_run), uma tool "
        "com efeito colateral ou não classificada só é chamada com isto true. Só kind api e python. "
        "Vazio = não declarado.",
    )

    @model_validator(mode="after")
    def _validate_slug(self) -> "ToolIn":
        if not _SLUG_RE.match(self.tool_name):
            raise ValueError("tool_name deve ser um slug: letras minúsculas, números, '-' ou '_'")
        _check_dry_run_support(self.kind, self.dry_run_support)
        return self


def _check_dry_run_support(kind: str, dry_run_support: bool | None) -> None:
    if dry_run_support and kind == "builtin":
        raise ValueError(
            "dry_run_support=true não vale para kind='builtin': uma toolkit do Agno não recebe o header "
            "X-Kuro-Dry-Run, então não tem como simular"
        )


class ToolUpdateIn(BaseModel):
    label: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    side_effect: bool | None = Field(
        default=None, description="Mandar `null` explícito volta para 'não classificada'; omitir não mexe."
    )
    dry_run_support: bool | None = Field(
        default=None, description="Mandar `null` explícito volta para 'não declarado'; omitir não mexe."
    )


class ToolOut(BaseModel):
    tool_name: str
    kind: ToolKind
    label: str
    description: str | None
    config: dict[str, Any]
    enabled: bool
    is_seed: bool
    side_effect: bool | None = None
    """`None` = ainda não classificada."""
    dry_run_support: bool | None = None
    """A API trata o `X-Kuro-Dry-Run`? `None` = não declarado."""
    created_at: datetime
    updated_at: datetime


class ToolDetailOut(ToolOut):
    """Só na leitura de uma tool: introspecção best-effort do que ela expõe."""

    functions: list[str] | None = None
    """Nomes das funções expostas — só pra `kind="builtin"` (uma toolkit tem várias)."""
    build_error: str | None = None
    """Por que a tool não pôde ser construída agora (ex.: dependência opcional ausente)."""


class BuiltinParamOut(BaseModel):
    name: str
    type: str
    label: str
    description: str
    required: bool
    secret: bool
    default: Any


class BuiltinCatalogEntryOut(BaseModel):
    builtin_id: str
    label: str
    description: str
    params: list[BuiltinParamOut]


class ToolInvokeIn(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    dependencies: dict[str, Any] = Field(
        default_factory=dict,
        description="Simula o `dependencies` do /chat para parâmetros com source='dependency'.",
    )
    function_name: str | None = Field(
        default=None, description="Obrigatório para kind='builtin' — qual função da toolkit chamar."
    )
    dry_run: bool = Field(
        default=False,
        description="Como o `dry_run` do /chat: a chamada leva `X-Kuro-Dry-Run: true` e "
        "`dependencies.dry_run` vale true — o destino decide o que simular.",
    )


class ToolInvokeOut(BaseModel):
    ok: bool
    """`false` também quando a API da tool respondeu erro (HTTP 4xx/5xx, rede): o
    texto que o modelo leria vem em `result`, e o tipo em `failure`."""
    result: Any = None
    error: str | None = None
    failure: str | None = None
    """invalid_arguments | not_found | auth | unavailable | config | exception (`tools/failures.py`)."""
    http_status: int | None = None
    dry_run_skipped: bool = False
    """Teste (`dry_run`) com uma tool que não pode rodar nele: ela não foi chamada, e `result`
    diz por quê (ver `tools/dry_run.py`)."""


# -- config ---------------------------------------------------------------


class PythonToolsConfigOut(BaseModel):
    enabled: bool
    """`CUSTOM_PYTHON_TOOLS_ENABLED` — tools kind="python" podem ser criadas mesmo
    desligado (pra deixar prontas), mas só rodam (num agente ou em /invoke) com isto ligado."""


@router.get("/python-config", response_model=PythonToolsConfigOut)
def get_python_tools_config() -> dict[str, Any]:
    return {"enabled": get_settings().custom_python_tools_enabled}


# -- catálogo de builtins ------------------------------------------------


@router.get("/catalog", response_model=list[BuiltinCatalogEntryOut])
def get_builtin_catalog() -> list[dict[str, Any]]:
    return [
        {
            "builtin_id": spec.builtin_id,
            "label": spec.label,
            "description": spec.description,
            "params": [
                {
                    "name": p.name,
                    "type": p.type,
                    "label": p.label,
                    "description": p.description,
                    "required": p.required,
                    "secret": p.secret,
                    "default": p.default,
                }
                for p in spec.params
            ],
        }
        for spec in list_builtin_catalog()
    ]


# -- CRUD ----------------------------------------------------------------


@router.get("", response_model=list[ToolOut])
def list_tools() -> list[dict[str, Any]]:
    return [_row_out(row) for row in store.list_tools()]


@router.post("", response_model=ToolOut, status_code=201)
def create_tool(body: ToolIn) -> dict[str, Any]:
    if store.get_tool(body.tool_name) is not None:
        raise HTTPException(status_code=409, detail=f"Tool {body.tool_name!r} já existe")
    _check_secrets(body.kind, body.config)
    config = _validate_config(body.kind, body.config)
    created = store.create_tool(
        tool_name=body.tool_name,
        kind=body.kind,
        label=body.label,
        description=body.description,
        config=config,
        enabled=body.enabled,
        side_effect=body.side_effect,
        dry_run_support=body.dry_run_support,
    )
    return _row_out(created)


@router.get("/{tool_name}", response_model=ToolDetailOut)
def get_tool(tool_name: str) -> dict[str, Any]:
    row = store.get_tool(tool_name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Tool {tool_name!r} não encontrada")
    out = _row_out(row)
    if row["kind"] == "builtin" and row["enabled"]:
        try:
            built = registry.build_fresh(row)
            out["functions"] = sorted(getattr(built, "functions", {}).keys())
        except ToolBuildError as exc:
            out["build_error"] = str(exc)
    return out


@router.put("/{tool_name}", response_model=ToolOut)
def update_tool(tool_name: str, body: ToolUpdateIn) -> dict[str, Any]:
    current = store.get_tool(tool_name)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Tool {tool_name!r} não encontrada")

    if "dry_run_support" in body.model_fields_set:
        try:
            _check_dry_run_support(current["kind"], body.dry_run_support)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    config = None
    if body.config is not None:
        merged = _unmask_config(current["kind"], body.config, current["config"])
        _check_secrets(current["kind"], merged)
        config = _validate_config(current["kind"], merged)
        if current["kind"] == "api":
            _check_agents_declare_dependencies(tool_name, config)

    updated = store.update_tool(
        tool_name,
        label=body.label,
        description=body.description,
        config=config,
        enabled=body.enabled,
        **({"side_effect": body.side_effect} if "side_effect" in body.model_fields_set else {}),
        **({"dry_run_support": body.dry_run_support} if "dry_run_support" in body.model_fields_set else {}),
    )
    return _row_out(updated)


def _check_agents_declare_dependencies(tool_name: str, config: dict[str, Any]) -> None:
    """Uma dependência nova e obrigatória quebraria, em silêncio, todo agente que
    já usa esta tool sem declarar o campo — mesma ideia da trava do delete."""
    exigidas = set(required_dependencies(config))
    if not exigidas:
        return
    faltando = {
        d["agent_type"]: sorted(exigidas - {f["name"] for f in d["dependency_fields"] or []})
        for d in list_agent_definitions()
        if tool_name in (d["tools"] or [])
    }
    faltando = {agente: campos for agente, campos in faltando.items() if campos}
    if faltando:
        detalhe = "; ".join(f"{agente} não declara {', '.join(campos)}" for agente, campos in faltando.items())
        raise HTTPException(
            status_code=409,
            detail=f"Esta mudança exige dependencies que agentes em uso não declaram — {detalhe}",
        )


@router.delete("/{tool_name}", status_code=204)
def delete_tool(tool_name: str) -> None:
    row = store.get_tool(tool_name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Tool {tool_name!r} não encontrada")
    if row["is_seed"]:
        raise HTTPException(status_code=403, detail="Tool semeada pelo sistema não pode ser removida")

    using = [d["agent_type"] for d in list_agent_definitions() if tool_name in (d["tools"] or [])]
    if using:
        raise HTTPException(
            status_code=409,
            detail=f"Tool {tool_name!r} está em uso por: {', '.join(using)}. Remova-a desses agentes primeiro.",
        )
    store.delete_tool(tool_name)


# -- testar sem precisar de um agente ------------------------------------


@router.post("/{tool_name}/invoke", response_model=ToolInvokeOut)
async def invoke_tool(tool_name: str, body: ToolInvokeIn) -> dict[str, Any]:
    """Testa a tool isoladamente. `async` porque o entrypoint de uma tool
    `kind="api"` é uma corrotina (ver `tools/api_tool.py`) — chamá-lo de uma
    rota síncrona devolveria a corrotina sem executá-la."""
    try:
        result = await run_tool(
            tool_name,
            body.arguments,
            function_name=body.function_name,
            dependencies=body.dependencies,
            dry_run=body.dry_run,
        )
    except ToolUnavailableError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return ToolInvokeOut(**result).model_dump()
