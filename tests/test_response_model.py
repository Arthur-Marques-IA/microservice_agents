from agent_service.agents.dependency_fields import validate_field_specs
from agent_service.agents.response_model import build_response_model


def test_required_field_has_no_default():
    fields = validate_field_specs([{"name": "valor", "type": "number", "required": True}])
    model = build_response_model("extrator-contrato", fields)
    assert model.model_fields["valor"].is_required()


def test_optional_field_defaults_to_none():
    fields = validate_field_specs([{"name": "observacao", "type": "string"}])
    model = build_response_model("extrator-contrato", fields)
    assert not model.model_fields["observacao"].is_required()
    assert model().observacao is None


def test_type_mapping_round_trip():
    fields = validate_field_specs(
        [
            {"name": "valor", "type": "number", "required": True},
            {"name": "prazo_dias", "type": "integer", "required": True},
            {"name": "ativo", "type": "boolean", "required": True},
            {"name": "cliente", "type": "string", "required": True},
        ]
    )
    model = build_response_model("extrator", fields)
    instance = model(valor=10.5, prazo_dias=30, ativo=True, cliente="Acme")
    assert instance.model_dump() == {"valor": 10.5, "prazo_dias": 30, "ativo": True, "cliente": "Acme"}
