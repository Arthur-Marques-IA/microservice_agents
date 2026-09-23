"""CRUD das collections de documentos + ingestão simples e busca.

Uma collection é uma base de conhecimento (pgvector) que um agente pode
consultar: o agente aponta para ela em `knowledge_collection`
(`api/agents_routes.py`) e ganha, com isso, uma tool de busca — é o elo que
antes não existia entre os documentos e os agentes.

Para upload de arquivo/URL com chunking, o AgentOS expõe `/knowledge/content`
(ver README); aqui fica o cadastro em si, a ingestão de texto avulso e a busca.
"""

import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_service.agents.store import list_definitions
from agent_service.documents import store
from agent_service.documents.collections import add_text, default_collection_name, search
from agent_service.documents.embedder import (
    DEFAULT_EMBEDDER_PROVIDER,
    EMBEDDERS,
    EmbedderNotConfiguredError,
    UnknownEmbedderProviderError,
    build_embedder,
    resolve_spec,
)

router = APIRouter(prefix="/collections", tags=["collections"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class CollectionIn(BaseModel):
    name: str = Field(..., description="Slug estável — vira o nome da tabela pgvector")
    label: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    embedder_provider: str | None = Field(
        default=None,
        description="Quem gera os vetores: google (padrão), openai ou ollama. Fixo depois de criada.",
    )
    embedder_model: str | None = Field(default=None, max_length=200)
    embedder_dimensions: int | None = Field(
        default=None, gt=0, le=8192, description="Só é preciso com um `embedder_model` fora do padrão do provedor."
    )


class CollectionUpdateIn(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)


class CollectionOut(BaseModel):
    name: str
    is_default: bool = False
    """Coleção que o pipeline de upload do AgentOS alimenta (arquivo/URL)."""
    label: str
    description: str | None
    is_seed: bool
    embedder_provider: str
    embedder_model: str
    embedder_dimensions: int | None = None
    agents_using: list[str] = []
    """Agentes com `knowledge_collection` apontando para cá — avisa antes de excluir."""
    created_at: datetime
    updated_at: datetime


class AddTextRequest(BaseModel):
    text: str
    name: str | None = None
    metadata: dict[str, Any] | None = None


class SearchResult(BaseModel):
    content: str
    metadata: dict[str, Any] | None = None


def _agents_using(name: str) -> list[str]:
    return [d["agent_type"] for d in list_definitions() if d.get("knowledge_collection") == name]


def _out(row: dict[str, Any]) -> dict[str, Any]:
    # `embedder_provider` sai preenchido mesmo para as collections anteriores à
    # coluna: quem lê precisa saber qual embedder responde, não se a linha é velha.
    spec = resolve_spec(row.get("embedder_provider"))
    return {
        **row,
        "embedder_provider": spec.provider,
        "embedder_model": row.get("embedder_model") or spec.default_model_id,
        "agents_using": _agents_using(row["name"]),
        "is_default": row["name"] == default_collection_name(),
    }


class EmbedderOut(BaseModel):
    provider: str
    label: str
    default_model_id: str
    default_dimensions: int | None
    requires_api_key: bool
    description: str
    configured: bool
    """A credencial existe agora — uma collection neste provedor indexaria."""


@router.get("/embedders", response_model=list[EmbedderOut])
def list_embedders() -> list[dict[str, Any]]:
    """Provedores de embedding e quais já têm credencial. Declarada antes de
    `/{collection_name}` porque o FastAPI casa as rotas na ordem."""
    saida = []
    for spec in EMBEDDERS.values():
        try:
            build_embedder(spec.provider)
            configured = True
        except EmbedderNotConfiguredError:
            configured = False
        saida.append({**vars(spec), "configured": configured})
    return saida


def _row_or_404(name: str) -> dict[str, Any]:
    row = store.get_collection_row(name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Coleção desconhecida: {name!r}")
    return row


@router.get("", response_model=list[CollectionOut])
def list_collections() -> list[dict[str, Any]]:
    return [_out(row) for row in store.list_collections()]


@router.post("", response_model=CollectionOut, status_code=201)
def create_collection(body: CollectionIn) -> dict[str, Any]:
    if not _SLUG_RE.match(body.name):
        raise HTTPException(status_code=422, detail="name deve ser um slug: minúsculas, números, '-' ou '_'")
    if store.get_collection_row(body.name) is not None:
        raise HTTPException(status_code=409, detail=f"Coleção {body.name!r} já existe")
    # Falhar aqui, e não na primeira ingestão: uma collection criada com um
    # provedor sem chave parece pronta e só quebra quando alguém manda um documento.
    try:
        build_embedder(body.embedder_provider, body.embedder_model, body.embedder_dimensions)
    except (UnknownEmbedderProviderError, EmbedderNotConfiguredError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    created = store.create_collection(
        name=body.name,
        label=body.label,
        description=body.description,
        embedder_provider=(body.embedder_provider or DEFAULT_EMBEDDER_PROVIDER).lower(),
        embedder_model=body.embedder_model,
        embedder_dimensions=body.embedder_dimensions,
    )
    return _out(created)


@router.get("/{collection_name}", response_model=CollectionOut)
def get_collection_detail(collection_name: str) -> dict[str, Any]:
    return _out(_row_or_404(collection_name))


@router.put("/{collection_name}", response_model=CollectionOut)
def update_collection(collection_name: str, body: CollectionUpdateIn) -> dict[str, Any]:
    _row_or_404(collection_name)
    return _out(store.update_collection(collection_name, label=body.label, description=body.description))


@router.delete("/{collection_name}", status_code=204)
def delete_collection(collection_name: str) -> None:
    row = _row_or_404(collection_name)
    if row["is_seed"]:
        raise HTTPException(status_code=403, detail="Coleção semeada pelo sistema não pode ser removida")
    using = _agents_using(collection_name)
    if using:
        raise HTTPException(
            status_code=409,
            detail=f"Coleção em uso por: {', '.join(using)}. Tire-a desses agentes primeiro.",
        )
    store.delete_collection(collection_name)


@router.post("/{collection_name}/documents", status_code=201)
async def ingest_text(collection_name: str, request: AddTextRequest) -> dict[str, str]:
    _row_or_404(collection_name)
    content_id = await add_text(collection_name, text=request.text, name=request.name, metadata=request.metadata)
    return {"content_id": content_id}


@router.get("/{collection_name}/search", response_model=list[SearchResult])
async def search_collection(collection_name: str, query: str, limit: int = 5) -> list[SearchResult]:
    _row_or_404(collection_name)
    documents = await search(collection_name, query=query, limit=limit)
    return [SearchResult(content=doc.content, metadata=doc.meta_data) for doc in documents]
