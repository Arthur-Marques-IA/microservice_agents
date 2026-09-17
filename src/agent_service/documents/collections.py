"""Collections de documentos (RAG) sobre Postgres+pgvector.

Cada collection cadastrada (`documents/store.py`) vira uma `Knowledge` (base de
conhecimento do Agno) própria, com sua tabela pgvector. Um agente aponta para
uma delas em `knowledge_collection` e ganha uma tool de busca (`agents/base.py`).
As collections são registradas no
AgentOS (`main.py`, `knowledge=all_collections()`), que já expõe o pipeline de
ingestão completo (upload de arquivo, texto ou URL, com chunking configurável
e processamento assíncrono) em `/knowledge/content`, além de busca em
`/knowledge/search` — ver README para o contrato exato desses endpoints.

`add_text` cobre o caso de ingestão simples e programática (ex. futuramente a
partir de uma tool do agente analista), sem precisar montar um multipart/form.
"""

from functools import lru_cache
from typing import Any

from agno.knowledge.content import Content, FileData
from agno.knowledge.embedder.google import GeminiEmbedder
from agno.knowledge.knowledge import Knowledge
from agno.utils.string import generate_id
from agno.vectordb.pgvector import PgVector

from agent_service.config import get_settings
from agent_service.db import get_db
from agent_service.documents.store import list_collection_names


def collection_exists(name: str) -> bool:
    return name in list_collection_names()


@lru_cache
def get_collection(name: str) -> Knowledge:
    """Retorna (criando se necessário) a coleção de documentos `name`."""
    settings = get_settings()
    vector_db = PgVector(
        table_name=f"knowledge_{name}",
        db_url=settings.database_url,
        embedder=GeminiEmbedder(api_key=settings.google_api_key),
    )
    return Knowledge(
        name=name,
        vector_db=vector_db,
        contents_db=get_db(),
    )


def all_collections() -> list[Knowledge]:
    """Todas as collections cadastradas, para registrar no AgentOS no startup.

    Uma collection criada depois do boot funciona normalmente no `/chat` (o
    agente a resolve por nome), só não aparece nas rotas de knowledge do
    AgentOS até o próximo restart — mesma ressalva dos agentes."""
    return [get_collection(name) for name in list_collection_names()]


async def add_text(
    collection_name: str,
    *,
    text: str,
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Ingestão programática simples: adiciona um texto bruto à coleção.

    Para upload de arquivo/URL com opções de chunking, use o endpoint
    `POST /knowledge/content` exposto pelo AgentOS (ver README).
    """
    knowledge = get_collection(collection_name)
    content = Content(
        name=name or "texto-avulso",
        file_data=FileData(content=text.encode("utf-8"), type="manual"),
        metadata=metadata,
    )
    # Mesmo padrão do router do AgentOS (`/knowledge/content`): sem isso,
    # `content.id` fica None e o Agno acaba gerando um id não-determinístico
    # por baixo dos panos — o que fez duas ingestões de textos diferentes
    # colidirem no mesmo id durante os testes deste endpoint.
    content.content_hash = knowledge._build_content_hash(content)
    content.id = generate_id(content.content_hash)
    await knowledge._aload_content(content, upsert=False, skip_if_exists=True)
    return content.id


async def search(collection_name: str, *, query: str, limit: int = 5) -> list[Any]:
    knowledge = get_collection(collection_name)
    return await knowledge.asearch(query=query, max_results=limit)
