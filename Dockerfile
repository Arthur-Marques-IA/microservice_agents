# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.33 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Instala dependências primeiro (cache separado do código-fonte)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Chama o uvicorn do venv diretamente: `uv run` re-sincronizaria o
# ambiente contra o lockfile a cada start (lento e sem necessidade, já
# que a imagem já foi montada com `uv sync` acima).
CMD ["uvicorn", "agent_service.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
