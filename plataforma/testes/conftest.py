"""Ambiente dos testes: banco SQLite temporário e um Supabase de mentira.

O Supabase falso (SupabaseFalso) responde às mesmas rotas do Auth que a API
usa, guarda as contas em memória e registra os e-mails que "mandaria". Assim
os testes cobrem cadastro, confirmação, login, renovação e senha nova sem
rede e sem projeto de verdade.

As variáveis de ambiente são definidas ANTES de importar a API, porque o
config.py lê tudo na importação. Cada uma é definida explicitamente, mesmo
vazia: o config só completa o que faltar a partir do .env, e um .env de
verdade na máquina não pode vazar para o teste (o SMTP mandaria e-mail).
"""

from __future__ import annotations

import os
import secrets
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import jwt
import pytest

PASTA = Path(tempfile.mkdtemp(prefix="bionalya-testes-"))
URL = "https://teste.supabase.co"
SEGREDO = "segredo-de-teste-com-pelo-menos-32-caracteres"

os.environ.update({
    "DATABASE_URL": f"sqlite:///{PASTA / 'teste.db'}",
    "SUPABASE_URL": URL,
    "SUPABASE_ANON_KEY": "anon-teste",
    "SUPABASE_SERVICE_KEY": "service-teste",
    "SUPABASE_JWT_SECRET": SEGREDO,
    "SITE_URL": "http://teste.local",
    "SMTP_HOST": "", "SMTP_USUARIO": "", "SMTP_SENHA": "",
    "BIONALYA_ADMIN_EMAIL": "admin@teste.br",
    "BIONALYA_ADMIN_SENHA": "SenhaAdmin123",
    "BIONALYA_DEMO_EMAIL": "", "BIONALYA_DEMO_SENHA": "",
})


class SupabaseFalso:
    """O pedaço do Supabase Auth que a API usa."""

    def __init__(self):
        self.contas: dict[str, dict] = {}          # id -> conta
        self.renovar: dict[str, str] = {}          # refresh_token -> id
        self.links: dict[str, tuple[str, str]] = {}  # token_hash -> (id, tipo)
        self.emails: list[dict] = []               # o que teria sido mandado
        self.emitidos: dict[str, list[str]] = {}   # id -> access_tokens
        self.revogados: set[str] = set()
        self.falhar_recover = False

    # ------------------------------------------------------------ utilidades
    def por_email(self, email):
        return next((c for c in self.contas.values() if c["email"] == email.lower()), None)

    def _token(self, conta, validade=3600):
        agora = int(time.time())
        tok = jwt.encode({
            "sub": conta["id"], "email": conta["email"], "aud": "authenticated",
            "iss": f"{URL}/auth/v1", "role": "authenticated",
            "iat": agora, "exp": agora + validade, "jti": secrets.token_hex(8),
            "user_metadata": conta["meta"],
        }, SEGREDO, algorithm="HS256")
        self.emitidos.setdefault(conta["id"], []).append(tok)
        return tok

    def _sessao(self, conta):
        r = secrets.token_urlsafe(16)
        acesso = self._token(conta)
        self.renovar[r] = (conta["id"], acesso)
        return {"access_token": acesso, "refresh_token": r,
                "expires_in": 3600, "expires_at": int(time.time()) + 3600,
                "user": self._publico(conta)}

    def _publico(self, conta):
        return {"id": conta["id"], "email": conta["email"],
                "email_confirmed_at": "2026-01-01T00:00:00Z" if conta["confirmado"] else None,
                "user_metadata": conta["meta"], "identities": [{"id": conta["id"]}]}

    def _mandar(self, conta, tipo):
        h = secrets.token_hex(16)
        self.links[h] = (conta["id"], tipo)
        self.emails.append({"para": conta["email"], "tipo": tipo, "token_hash": h})

    def _dono(self, req):
        tok = req.headers.get("authorization", "").split(" ", 1)[-1]
        try:
            claims = jwt.decode(tok, SEGREDO, algorithms=["HS256"], audience="authenticated")
        except jwt.PyJWTError:
            return None
        if tok in self.revogados:
            return None
        return self.contas.get(claims["sub"])

    @staticmethod
    def _erro(status, codigo, msg="erro"):
        return httpx.Response(status, json={"error_code": codigo, "msg": msg})

    def nova_conta(self, email, senha, meta=None, confirmado=False):
        conta = {"id": str(uuid.uuid4()), "email": email.lower(), "senha": senha,
                 "meta": meta or {}, "confirmado": confirmado}
        self.contas[conta["id"]] = conta
        return conta

    # ------------------------------------------------------------- as rotas
    def __call__(self, req: httpx.Request) -> httpx.Response:
        caminho = req.url.path.removeprefix("/auth/v1")
        corpo = {}
        if req.content:
            import json
            corpo = json.loads(req.content)
        metodo = req.method
        q = req.url.params

        if caminho == "/signup" and metodo == "POST":
            if self.por_email(corpo["email"]):
                return httpx.Response(200, json={"id": str(uuid.uuid4()), "identities": []})
            c = self.nova_conta(corpo["email"], corpo["password"], corpo.get("data"))
            self._mandar(c, "email")
            return httpx.Response(200, json=self._publico(c) | {"email_confirmed_at": None})

        if caminho == "/token" and q.get("grant_type") == "password":
            c = self.por_email(corpo["email"])
            if c is None or c["senha"] != corpo["password"]:
                return self._erro(400, "invalid_credentials")
            if not c["confirmado"]:
                return self._erro(400, "email_not_confirmed")
            return httpx.Response(200, json=self._sessao(c))

        if caminho == "/token" and q.get("grant_type") == "refresh_token":
            par = self.renovar.pop(corpo["refresh_token"], None)
            if par is None:
                return self._erro(400, "refresh_token_not_found")
            return httpx.Response(200, json=self._sessao(self.contas[par[0]]))

        if caminho == "/logout":
            c = self._dono(req)
            if c is None:
                return self._erro(401, "bad_jwt")
            atual = req.headers["authorization"].split(" ", 1)[1]
            escopo = q.get("scope") or "local"
            for r, (cid, acesso) in list(self.renovar.items()):
                if cid != c["id"]:
                    continue
                if escopo == "global" or (escopo == "others") == (acesso != atual):
                    del self.renovar[r]
                    self.revogados.add(acesso)
            if escopo != "others":
                self.revogados.add(atual)
            return httpx.Response(204)

        if caminho == "/recover":
            if self.falhar_recover:
                return self._erro(500, "unexpected_failure", "Error sending recovery email")
            c = self.por_email(corpo["email"])
            if c:
                self._mandar(c, "recovery")
            return httpx.Response(200, json={})

        if caminho == "/resend":
            c = self.por_email(corpo["email"])
            if c and not c["confirmado"]:
                self._mandar(c, "email")
            return httpx.Response(200, json={})

        if caminho == "/verify":
            link = self.links.pop(corpo["token_hash"], None)
            if link is None or (link[1] == "recovery") != (corpo["type"] == "recovery"):
                return self._erro(403, "otp_expired")
            c = self.contas[link[0]]
            c["confirmado"] = True
            return httpx.Response(200, json=self._sessao(c))

        if caminho == "/user" and metodo == "PUT":
            c = self._dono(req)
            if c is None:
                return self._erro(401, "bad_jwt")
            if corpo.get("password") == c["senha"]:
                return self._erro(422, "same_password")
            c["senha"] = corpo["password"]
            return httpx.Response(200, json=self._publico(c))

        if caminho == "/user" and metodo == "GET":
            c = self._dono(req)
            return httpx.Response(200, json=self._publico(c)) if c else self._erro(401, "bad_jwt")

        if caminho.startswith("/admin/"):
            if req.headers.get("apikey") != "service-teste":
                return self._erro(403, "not_admin")
            if caminho == "/admin/users" and metodo == "POST":
                if self.por_email(corpo["email"]):
                    return self._erro(422, "email_exists")
                c = self.nova_conta(corpo["email"], corpo["password"],
                                    corpo.get("user_metadata"), corpo.get("email_confirm"))
                return httpx.Response(200, json=self._publico(c))
            if caminho == "/admin/users" and metodo == "GET":
                return httpx.Response(200, json={"users": [self._publico(c) for c in
                                                           self.contas.values()]})
            cid = caminho.rsplit("/", 1)[-1]
            c = self.contas.get(cid)
            if c is None:
                return self._erro(404, "user_not_found")
            if metodo == "PUT":
                if "password" in corpo:
                    c["senha"] = corpo["password"]
                if corpo.get("email_confirm"):
                    c["confirmado"] = True
                return httpx.Response(200, json=self._publico(c))
            if metodo == "DELETE":
                del self.contas[cid]
                return httpx.Response(200, json={})

        return self._erro(404, "rota_desconhecida", f"{metodo} {caminho}")


@pytest.fixture(scope="session")
def supabase():
    from api import autenticacao
    falso = SupabaseFalso()
    autenticacao._cliente = httpx.Client(transport=httpx.MockTransport(falso),
                                         base_url=f"{URL}/auth/v1")
    return falso


@pytest.fixture(scope="session")
def correio_enviado():
    """Troca o envio de e-mail da plataforma por uma lista."""
    from api import correio
    enviados = []
    correio.enviar = lambda para, assunto, texto, botao=None: (
        enviados.append({"para": para, "assunto": assunto, "texto": texto}) or True)
    return enviados


@pytest.fixture(scope="session")
def cliente(supabase, correio_enviado):
    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c


def cab(token):
    return {"Authorization": f"Bearer {token}"}
