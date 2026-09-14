from agno.db.sqlite import SqliteDb

from agent_service.memory import common as common_memory
from agent_service.memory.common import CommonMemoryBackend


def test_common_memory_add_and_search_round_trip(tmp_path, monkeypatch):
    db_file = str(tmp_path / "memory.db")
    monkeypatch.setattr(common_memory, "get_db", lambda: SqliteDb(db_file=db_file))

    backend = CommonMemoryBackend()
    backend.add(user_id="user-1", session_id="session-1", content="Gosta de café sem açúcar")

    memories = backend.manager.get_user_memories(user_id="user-1")
    assert any("café" in m.memory for m in memories)
