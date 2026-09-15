from agent_service.agents.store import (
    create_definition,
    delete_definition,
    get_definition,
    list_prompt_versions,
    update_definition,
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
