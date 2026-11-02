"""Senhas e primeiro acesso.

A senha nunca é guardada em texto: o banco grava só o hash PBKDF2-SHA256, que
é de mão única. Nem a equipe consegue ler a senha de alguém.
"""

from __future__ import annotations

import secrets
import string

from passlib.hash import pbkdf2_sha256

MIN_SENHA = 8


def hash_senha(senha: str) -> str:
    return pbkdf2_sha256.hash(senha)


def conferir_senha(senha: str, hash_guardado: str) -> bool:
    try:
        return pbkdf2_sha256.verify(senha, hash_guardado)
    except Exception:
        return False


def senha_aleatoria(n: int = 14) -> str:
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(n))


def criticar_senha(senha: str) -> str | None:
    if len(senha or "") < MIN_SENHA:
        return f"A senha precisa de pelo menos {MIN_SENHA} caracteres."
    return None
