#!/bin/sh
# Roda só no primeiro boot do container (PGDATA vazio) — ver imagem oficial
# do Postgres. O `agent-service` e o Langfuse dividem a mesma instância
# (um Postgres a menos rodando), cada um com seu próprio banco: o schema
# de um nunca aparece pro outro.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE langfuse;
EOSQL
