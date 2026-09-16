"""Testes dos campos de `dependencies` configuráveis por agente:
`agents/dependency_fields.py` (validação), `api/agents_routes.py` (CRUD) e
`api/routes.py::_resolve` (aplicado a cada `/chat`).
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from agent_service.agents.dependency_fields import (
    DependencyFieldSpecError,
    DependencyValidationError,
    validate_dependencies,
    validate_field_specs,
)
from agent_service.agents.store import create_definition, delete_definition

from agent_service.api.agents_routes import AgentDefinitionIn, create_agent, update_agent
from agent_service.api.routes import ChatRequest, _resolve


# -- validate_field_specs ---------------------------------------------------


def test_validate_field_specs_normalizes_defaults():
    normalized = validate_field_specs([{"name": "cpf", "type": "string", "required": True}])
    assert normalized == [
        {"name": "cpf", "type": "string", "label": "cpf", "description": "", "required": True, "default": None}
    ]


def test_validate_field_specs_empty_is_a_noop():
    assert validate_field_specs(None) == []
    assert validate_field_specs([]) == []


def test_validate_field_specs_rejects_bad_name():
    with pytest.raises(DependencyFieldSpecError, match="nome de campo"):
        validate_field_specs([{"name": "não é identificador"}])


def test_validate_field_specs_rejects_duplicate_name():
    with pytest.raises(DependencyFieldSpecError, match="duplicado"):
        validate_field_specs([{"name": "cpf"}, {"name": "cpf"}])


def test_validate_field_specs_rejects_bad_type():
    with pytest.raises(DependencyFieldSpecError, match="tipo inválido"):
        validate_field_specs([{"name": "cpf", "type": "array"}])


# -- validate_dependencies ---------------------------------------------------


def test_validate_dependencies_passes_through_when_no_fields_declared():
    assert validate_dependencies([], {"qualquer": "coisa"}) == {"qualquer": "coisa"}
    assert validate_dependencies(None, None) == {}


def test_validate_dependencies_requires_declared_required_field():
    specs = validate_field_specs([{"name": "cpf", "required": True}])
    with pytest.raises(DependencyValidationError, match="cpf"):
        validate_dependencies(specs, {})


def test_validate_dependencies_applies_default_when_absent():
    specs = validate_field_specs([{"name": "plano", "default": "gratis"}])
    assert validate_dependencies(specs, {}) == {"plano": "gratis"}


def test_validate_dependencies_rejects_wrong_type():
    specs = validate_field_specs([{"name": "idade", "type": "integer"}])
    with pytest.raises(DependencyValidationError, match="idade"):
        validate_dependencies(specs, {"idade": "vinte"})
    with pytest.raises(DependencyValidationError):
        validate_dependencies(specs, {"idade": True})  # bool não conta como integer


def test_validate_dependencies_keeps_undeclared_extra_fields():
    specs = validate_field_specs([{"name": "cpf", "required": True}])
    result = validate_dependencies(specs, {"cpf": "000", "extra": "passa direto"})
    assert result == {"cpf": "000", "extra": "passa direto"}


# -- agents_routes.py --------------------------------------------------------


def test_create_agent_normalizes_dependency_fields():
    body = AgentDefinitionIn(
        agent_type="dep-fields-agent",
        name="Teste",
        instructions=["oi"],
        dependency_fields=[{"name": "cpf", "type": "string", "required": True}],
    )
    try:
        created = create_agent(body)
        assert created["dependency_fields"] == [
            {"name": "cpf", "type": "string", "label": "cpf", "description": "", "required": True, "default": None}
        ]
    finally:
        delete_definition("dep-fields-agent")


def test_create_agent_rejects_invalid_dependency_field():
    with pytest.raises(ValidationError, match="nome de campo"):
        AgentDefinitionIn(
            agent_type="bad-dep-agent",
            name="Teste",
            instructions=["oi"],
            dependency_fields=[{"name": "não é identificador"}],
        )


def test_update_agent_replaces_dependency_fields():
    create_definition(agent_type="dep-fields-update", name="Teste", instructions=["oi"])
    try:
        from agent_service.api.agents_routes import AgentDefinitionUpdate

        updated = update_agent(
            "dep-fields-update",
            AgentDefinitionUpdate(dependency_fields=[{"name": "email", "type": "string", "required": True}]),
        )
        assert updated["dependency_fields"][0]["name"] == "email"
    finally:
        delete_definition("dep-fields-update")


# -- routes.py::_resolve -----------------------------------------------------


def test_resolve_rejects_chat_missing_required_dependency():
    create_definition(
        agent_type="dep-fields-chat",
        name="Teste",
        instructions=["oi"],
        dependency_fields=[{"name": "cpf", "type": "string", "required": True}],
    )
    try:
        request = ChatRequest(agent_type="dep-fields-chat", user_id="u1", session_id="s1", message="oi")
        with pytest.raises(HTTPException) as exc:
            _resolve(request, "chat")
        assert exc.value.status_code == 422
        assert "cpf" in exc.value.detail
    finally:
        delete_definition("dep-fields-chat")


def test_resolve_applies_default_and_accepts_valid_dependencies():
    create_definition(
        agent_type="dep-fields-chat-ok",
        name="Teste",
        instructions=["oi"],
        dependency_fields=[{"name": "cpf", "type": "string", "required": True}, {"name": "plano", "default": "gratis"}],
    )
    try:
        request = ChatRequest(
            agent_type="dep-fields-chat-ok", user_id="u1", session_id="s1", message="oi", dependencies={"cpf": "000"}
        )
        _agent, run = _resolve(request, "chat")
        assert run.dependencies == {"cpf": "000", "plano": "gratis"}
    finally:
        delete_definition("dep-fields-chat-ok")
