import pytest

from agent_service.agents.dependency_fields import validate_field_specs
from agent_service.field_schema import MAX_DEPTH
from agent_service.agents.response_model import (
    ResponseSchemaError,
    build_response_model,
    validate_response_schema,
)


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


# -- tipos compostos: object e array ------------------------------------------


def test_array_de_objetos_vira_lista_tipada():
    """O caso que motivou os tipos compostos: extrair uma lista de itens de um
    documento, e não só campos soltos."""
    campos = validate_response_schema(
        [
            {
                "name": "parcelas",
                "type": "array",
                "required": True,
                "items": {
                    "type": "object",
                    "fields": [
                        {"name": "numero", "type": "integer", "required": True},
                        {"name": "valor", "type": "number", "required": True},
                    ],
                },
            }
        ]
    )
    model = build_response_model("extrator", campos)
    instancia = model(parcelas=[{"numero": 1, "valor": 10.0}, {"numero": 2, "valor": 20.0}])
    assert instancia.model_dump() == {"parcelas": [{"numero": 1, "valor": 10.0}, {"numero": 2, "valor": 20.0}]}


def test_objeto_aninhado_e_lista_simples():
    campos = validate_response_schema(
        [
            {"name": "cliente", "type": "object", "fields": [{"name": "nome", "type": "string", "required": True}]},
            {"name": "tags", "type": "array", "items": {"type": "string"}},
        ]
    )
    model = build_response_model("extrator", campos)
    instancia = model(cliente={"nome": "Ana"}, tags=["a", "b"])
    assert instancia.cliente.nome == "Ana"
    assert instancia.tags == ["a", "b"]


def test_schema_gerado_tem_items_e_properties():
    """Um `array` sem `items` sai como `"items": {}` e um `object` sem campos sai
    como `additionalProperties: true` — as duas formas que os provedores recusam
    em saída estruturada. É por isso que `items`/`fields` são obrigatórios."""
    campos = validate_response_schema(
        [
            {"name": "tags", "type": "array", "required": True, "items": {"type": "string"}},
            {
                "name": "cliente",
                "type": "object",
                "required": True,
                "fields": [{"name": "nome", "type": "string", "required": True}],
            },
        ]
    )
    schema = build_response_model("extrator", campos).model_json_schema()
    assert schema["properties"]["tags"]["items"] == {"type": "string"}
    referido = schema["properties"]["cliente"]["$ref"].rsplit("/", 1)[-1]
    assert "nome" in schema["$defs"][referido]["properties"]


def test_object_sem_fields_e_recusado():
    with pytest.raises(ResponseSchemaError) as exc:
        validate_response_schema([{"name": "cliente", "type": "object"}])
    assert "fields" in str(exc.value)


def test_array_sem_items_e_recusado():
    with pytest.raises(ResponseSchemaError) as exc:
        validate_response_schema([{"name": "tags", "type": "array"}])
    assert "items" in str(exc.value)


def test_array_de_object_sem_fields_e_recusado():
    with pytest.raises(ResponseSchemaError):
        validate_response_schema([{"name": "itens", "type": "array", "items": {"type": "object"}}])


def test_array_de_array_nao_e_suportado():
    with pytest.raises(ResponseSchemaError) as exc:
        validate_response_schema([{"name": "matriz", "type": "array", "items": {"type": "array"}}])
    assert "items" in str(exc.value)


def test_campo_duplicado_dentro_de_um_objeto():
    with pytest.raises(ResponseSchemaError) as exc:
        validate_response_schema(
            [
                {
                    "name": "cliente",
                    "type": "object",
                    "fields": [{"name": "nome", "type": "string"}, {"name": "nome", "type": "string"}],
                }
            ]
        )
    assert "duplicado" in str(exc.value)


def _aninhado(n: int) -> list[dict]:
    campo = {"name": "folha", "type": "string"}
    for i in range(n):
        campo = {"name": f"n{i}", "type": "object", "fields": [campo]}
    return [campo]


def test_aninhamento_no_limite_e_aceito():
    """Fixa o lado de cá da fronteira: um schema legal recusado viraria um 422
    aparentemente aleatório para quem o escreveu."""
    assert validate_response_schema(_aninhado(MAX_DEPTH))


def test_aninhamento_acima_do_limite_e_recusado():
    with pytest.raises(ResponseSchemaError) as exc:
        validate_response_schema(_aninhado(MAX_DEPTH + 1))
    assert "aninhamento" in str(exc.value)


def test_erro_diz_o_caminho_do_campo():
    """Com schema aninhado, saber só 'campo inválido' não ajuda a achar onde."""
    with pytest.raises(ResponseSchemaError) as exc:
        validate_response_schema(
            [
                {
                    "name": "cliente",
                    "type": "object",
                    "fields": [{"name": "idade", "type": "data-invalida"}],
                }
            ]
        )
    assert "cliente" in str(exc.value)
