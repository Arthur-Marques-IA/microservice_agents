"""Contrato de integração de um agente (`GET /agents/{tipo}/integration`).

Quem vai chamar o agente de outro módulo precisa saber três coisas: qual
endpoint, o que mandar no corpo e quais `dependencies` são obrigatórias. Isso
é derivado, não escrito à mão: os campos declarados pelo agente e os campos
que as tools dele exigem (parâmetros `source="dependency"`) são a mesma
verdade — `agents_routes` só deixa salvar quando batem.

O console e a CLI consomem este endpoint, em vez de cada um montar o seu
exemplo de cURL e divergirem no primeiro campo novo.
"""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from agent_service.agents.store import get_definition
from agent_service.tools.api_tool import required_dependencies
from agent_service.tools.store import get_tool

router = APIRouter(prefix="/agents", tags=["agents"])

_EXAMPLE_BY_TYPE: dict[str, Any] = {"string": "texto", "integer": 42, "number": 1.5, "boolean": True}


class DependencyContract(BaseModel):
    name: str
    type: str
    required: bool
    label: str
    description: str
    example: Any
    required_by_tools: list[str] = []
    """Tools do agente que consomem este campo — elas falham sem ele."""


class IntegrationContract(BaseModel):
    agent_type: str
    name: str
    kind: str = "conversational"
    prompt_version: int
    endpoint: str
    """Rota que quem integra chama: `/chat` num agente conversacional,
    `/analyze` num analista — são contratos de corpo diferentes."""
    chat_url: str
    stream_url: str | None = None
    """`None` em `kind="analysis"`: analista é one-shot, não tem streaming."""
    response_schema: list[dict[str, Any]] = []
    """Só em `kind="analysis"`: a forma do `result` que volta."""
    dependencies: list[DependencyContract]
    request_example: dict[str, Any]
    curl: str
    warnings: list[str] = []
    """Deve vir vazio: uma tool exigindo campo não declarado é inconsistência de dados."""


def _example_for(field: dict[str, Any]) -> Any:
    if field.get("default") is not None:
        return field["default"]
    return _EXAMPLE_BY_TYPE.get(field.get("type", "string"), "texto")


@router.get("/{agent_type}/integration", response_model=IntegrationContract)
def get_integration_contract(
    agent_type: str,
    base_url: str = Query("http://127.0.0.1:58000", description="Endereço do serviço usado nos exemplos."),
) -> IntegrationContract:
    definition = get_definition(agent_type)
    if definition is None:
        raise HTTPException(status_code=404, detail=f"Agente {agent_type!r} não encontrado")

    # De quais campos cada tool do agente depende (parâmetros source="dependency").
    por_tool: dict[str, list[str]] = {}
    for tool_name in definition["tools"] or []:
        row = get_tool(tool_name)
        if row is not None and row["kind"] == "api":
            for campo in required_dependencies(row["config"] or {}):
                por_tool.setdefault(campo, []).append(tool_name)

    declarados = {f["name"] for f in definition["dependency_fields"] or []}
    warnings = [
        f"a tool {', '.join(tools)} exige dependencies.{campo}, que o agente não declara"
        for campo, tools in sorted(por_tool.items())
        if campo not in declarados
    ]

    dependencies = [
        DependencyContract(
            name=f["name"],
            type=f["type"],
            required=f["required"],
            label=f["label"],
            description=f["description"],
            example=_example_for(f),
            required_by_tools=sorted(por_tool.get(f["name"], [])),
        )
        for f in definition["dependency_fields"] or []
    ]

    exemplo_dependencies = {d.name: d.example for d in dependencies if d.required or d.example is not None}
    # Um analista não recebe `message` nem sessão: o corpo dele é `document`, e a
    # resposta é o objeto do `response_schema`. Um exemplo de `/chat` aqui manda
    # quem integra montar a chamada errada.
    kind = definition.get("kind") or "conversational"
    is_analysis = kind == "analysis"
    if is_analysis:
        request_example = {"agent_type": agent_type, "document": "Texto a analisar."}
    else:
        request_example = {
            "agent_type": agent_type,
            "user_id": "usuario-123",
            "session_id": "sessao-123",
            "message": "Olá!",
        }
    if exemplo_dependencies:
        request_example["dependencies"] = exemplo_dependencies

    base = base_url.rstrip("/")
    endpoint = "/analyze" if is_analysis else "/chat"
    corpo = json.dumps(request_example, ensure_ascii=False, indent=2)
    # Com auth ligada o exemplo precisa do header: um cURL que não funciona é
    # pior que exemplo nenhum, porque manda quem integra procurar no lugar errado.
    from agent_service.api.auth import auth_enabled

    # Aspas duplas: dentro de aspas simples o shell não expande a variável, e o
    # cURL sairia com o literal `$KURO_RUNTIME_API_KEY` no header — 401 para
    # quem copiasse e colasse, que é o oposto do que este endpoint existe para fazer.
    auth_header = '  -H "Authorization: Bearer $KURO_RUNTIME_API_KEY" \\\n' if auth_enabled() else ""
    curl = (
        f"curl -X POST {base}{endpoint} \\\n"
        f"  -H 'Content-Type: application/json' \\\n"
        f"{auth_header}"
        f"  -d '{corpo}'"
    )

    return IntegrationContract(
        agent_type=agent_type,
        name=definition["name"],
        kind=kind,
        prompt_version=definition["prompt_version"],
        endpoint=endpoint,
        chat_url=f"{base}{endpoint}",
        stream_url=None if is_analysis else f"{base}/chat/stream",
        response_schema=definition.get("response_schema") or [],
        dependencies=dependencies,
        request_example=request_example,
        curl=curl,
        warnings=warnings,
    )
