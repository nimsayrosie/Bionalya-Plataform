"""Conferência do token: o projeto novo do Supabase assina com ES256 e publica
a chave pública (JWKS). Aqui a chave é gerada na hora e o JWKS é trocado por
um stub, para testar a conferência local sem rede."""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from api import autenticacao, config


def _token(chave, **extra):
    agora = int(time.time())
    claims = {"sub": "abc-123", "email": "Pessoa@Uni.br", "aud": "authenticated",
              "iss": f"{config.SUPABASE_URL}/auth/v1", "iat": agora, "exp": agora + 600}
    claims.update(extra)
    return jwt.encode(claims, chave, algorithm="ES256", headers={"kid": "k1"})


def _com_jwks(chave_publica, funcao):
    antigo = autenticacao._jwks
    autenticacao._jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _t: SimpleNamespace(key=chave_publica))
    try:
        return funcao()
    finally:
        autenticacao._jwks = antigo


def test_es256_valido():
    privada = ec.generate_private_key(ec.SECP256R1())
    ident = _com_jwks(privada.public_key(),
                      lambda: autenticacao.conferir(_token(privada)))
    assert ident.auth_id == "abc-123" and ident.email == "pessoa@uni.br"


def test_es256_vencido_ou_de_outra_chave():
    privada = ec.generate_private_key(ec.SECP256R1())
    outra = ec.generate_private_key(ec.SECP256R1())
    publica = privada.public_key()
    assert _com_jwks(publica, lambda: autenticacao.conferir(
        _token(privada, exp=int(time.time()) - 10))) is None
    assert _com_jwks(publica, lambda: autenticacao.conferir(_token(outra))) is None
    assert _com_jwks(publica, lambda: autenticacao.conferir(
        _token(privada, aud="anon"))) is None
    assert _com_jwks(publica, lambda: autenticacao.conferir(
        _token(privada, iss="https://outro.supabase.co/auth/v1"))) is None
