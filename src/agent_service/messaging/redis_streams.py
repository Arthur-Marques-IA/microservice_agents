"""Mensageria assíncrona via Redis Streams.

MVP: só o produtor (`publish_task`) está ligado — outros módulos da
plataforma podem publicar uma tarefa para ser processada por um agente sem
esperar a resposta síncrona. O consumidor (`consume_tasks`) é um esqueleto:
ele lê o stream mas ainda não despacha para o `agents.registry`. Isso vira
a base do agente **orquestrador** na fase 2 (ver roadmap no README).
"""

import json
from functools import lru_cache
from typing import Any, AsyncIterator

from redis.asyncio import Redis

from agent_service.config import get_settings


@lru_cache
def get_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def publish_task(*, agent_type: str, payload: dict[str, Any]) -> str:
    """Publica uma tarefa assíncrona para ser processada por um agente."""
    settings = get_settings()
    redis = get_redis()
    message_id: str = await redis.xadd(
        settings.redis_stream_tasks,
        {"agent_type": agent_type, "payload": json.dumps(payload)},
    )
    return message_id


async def consume_tasks() -> AsyncIterator[dict[str, Any]]:
    """Esqueleto de consumidor: lê o stream de tarefas via consumer group.

    Ainda não é chamado por nenhum processo do serviço — fica pronto para o
    worker do agente orquestrador (fase 2) consumir e despachar via
    `agent_service.agents.registry.get_agent`.
    """
    settings = get_settings()
    redis = get_redis()

    try:
        await redis.xgroup_create(
            settings.redis_stream_tasks, settings.redis_consumer_group, mkstream=True
        )
    except Exception:
        pass  # grupo já existe

    while True:
        response = await redis.xreadgroup(
            groupname=settings.redis_consumer_group,
            consumername="worker-1",
            streams={settings.redis_stream_tasks: ">"},
            count=10,
            block=5000,
        )
        for _stream_name, messages in response:
            for message_id, fields in messages:
                yield {"id": message_id, **fields}
                await redis.xack(settings.redis_stream_tasks, settings.redis_consumer_group, message_id)
