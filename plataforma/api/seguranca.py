"""Regras de senha.

A senha não passa pelo nosso banco: quem guarda é o Supabase Auth (com bcrypt).
Aqui ficam só a regra mínima, conferida antes de mandar para lá, e o sorteio
de senha para as contas que o admin cria.
"""

from __future__ import annotations

import secrets
import string

MIN_SENHA = 8


def senha_aleatoria(n: int = 14) -> str:
    alfabeto = string.ascii_letters + string.digits
    while True:
        senha = "".join(secrets.choice(alfabeto) for _ in range(n))
        # Garante letra minúscula, maiúscula e número: se o projeto do Supabase
        # estiver exigindo senha forte, a sorteada também passa.
        if (any(c.islower() for c in senha) and any(c.isupper() for c in senha)
                and any(c.isdigit() for c in senha)):
            return senha


def criticar_senha(senha: str) -> str | None:
    if len(senha or "") < MIN_SENHA:
        return f"A senha precisa de pelo menos {MIN_SENHA} caracteres."
    if len(senha) > 72:
        return "A senha pode ter no máximo 72 caracteres."
    return None
