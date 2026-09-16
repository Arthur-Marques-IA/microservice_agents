"""Cifra em repouso das chaves de API de provedor de modelo.

A chave de cifragem (`CREDENTIALS_ENCRYPTION_KEY`, Fernet — AES-128-CBC +
HMAC) mora só no ambiente do serviço, nunca no banco. Sem ela configurada, o
serviço recusa salvar ou ler chaves de provedor: erra alto, não guarda nada
em texto plano nem finge que cifrou.
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from agent_service.config import get_settings


class EncryptionNotConfiguredError(RuntimeError):
    pass


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().credentials_encryption_key
    if not key:
        raise EncryptionNotConfiguredError(
            "CREDENTIALS_ENCRYPTION_KEY não configurada. Gere uma com: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise EncryptionNotConfiguredError(f"CREDENTIALS_ENCRYPTION_KEY inválida: {exc}") from exc


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionNotConfiguredError(
            "Não foi possível decifrar a chave salva — CREDENTIALS_ENCRYPTION_KEY mudou desde que ela foi salva?"
        ) from exc


def mask_secret(plaintext: str) -> str:
    """Só os últimos 4 caracteres — reconhecível sem expor a chave inteira."""
    return f"····{plaintext[-4:]}" if len(plaintext) > 4 else "····"


def reset_cache() -> None:
    """Para testes: força reler `CREDENTIALS_ENCRYPTION_KEY` do `Settings` atual."""
    _fernet.cache_clear()
