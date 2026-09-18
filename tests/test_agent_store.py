from agent_service.agents.store import (
    create_definition,
    delete_definition,
    get_definition,
    get_feedback_note,
    list_prompt_versions,
    update_definition,
    upsert_feedback_note,
)


def test_create_definition_round_trip():
    create_definition(agent_type="teste-a", name="Teste A", instructions=["v1"])
    definition = get_definition("teste-a")
    assert definition is not None
    assert definition["prompt_version"] == 1
    delete_definition("teste-a")


def test_update_instructions_bumps_prompt_version_and_records_history():
    create_definition(agent_type="teste-b", name="Teste B", instructions=["v1"])
    update_definition("teste-b", instructions=["v2"])
    update_definition("teste-b", instructions=["v3"])

    definition = get_definition("teste-b")
    assert definition["prompt_version"] == 3
    assert definition["instructions"] == ["v3"]

    versions = list_prompt_versions("teste-b")
    assert [v["version"] for v in versions] == [3, 2, 1]
    delete_definition("teste-b")


def test_update_without_instructions_does_not_bump_version():
    create_definition(agent_type="teste-c", name="Teste C", instructions=["v1"])
    update_definition("teste-c", name="Novo nome")

    definition = get_definition("teste-c")
    assert definition["prompt_version"] == 1
    assert definition["name"] == "Novo nome"
    delete_definition("teste-c")


def test_create_definition_defaults_to_conversational_kind():
    create_definition(agent_type="teste-d", name="Teste D", instructions=["v1"])
    definition = get_definition("teste-d")
    assert definition["kind"] == "conversational"
    assert definition["response_schema"] == []
    delete_definition("teste-d")


def test_create_analysis_definition_with_response_schema():
    schema = [{"name": "valor", "type": "number", "required": True}]
    create_definition(agent_type="teste-e", name="Teste E", instructions=["v1"], kind="analysis", response_schema=schema)
    definition = get_definition("teste-e")
    assert definition["kind"] == "analysis"
    assert definition["response_schema"] == schema
    delete_definition("teste-e")


def test_upsert_feedback_note_inserts_then_updates():
    assert get_feedback_note("teste-f") is None
    first = upsert_feedback_note("teste-f", "- confirme o CPF antes de responder")
    assert first["content"] == "- confirme o CPF antes de responder"

    second = upsert_feedback_note("teste-f", "- confirme o CPF antes de responder\n- seja breve")
    assert second["content"] == "- confirme o CPF antes de responder\n- seja breve"
    assert get_feedback_note("teste-f")["content"] == second["content"]
    delete_definition("teste-f")


def test_delete_definition_removes_feedback_note():
    create_definition(agent_type="teste-g", name="Teste G", instructions=["v1"])
    upsert_feedback_note("teste-g", "- seja breve")
    delete_definition("teste-g")
    assert get_feedback_note("teste-g") is None
