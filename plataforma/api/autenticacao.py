"""Login pelo Supabase Auth.

O Supabase guarda e-mail e senha (nós não guardamos nenhuma das duas coisas),
manda os e-mails de confirmação de cadastro e de nova senha, e entrega o token
de sessão. A API conversa com ele pela API REST do Auth, sem SDK: as telas
continuam falando só com /api/..., e as chaves do Supabase ficam no servidor.

O que fica do nosso lado é a tabela usuarios: papel, status de aprovação,
instituição, finalidade. Ela aponta para a conta do Supabase pela coluna
auth_id (o "sub" do token).

Conferência do token: projeto novo do Supabase assina o JWT com chave
assimétrica (ES256/RS256), e a chave pública fica em /auth/v1/.well-known/
jwks.json — a conferência é local, sem ir ao Supabase a cada requisição.
Projeto antigo assina com segredo (HS256): aí vale SUPABASE_JWT_SECRET, ou, sem
ele, a API pergunta ao Supabase quem é o dono do token (GET /auth/v1/user) e
guarda a resposta por um minuto.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

import httpx
import jwt

from . import config

TEMPO_LIMITE = httpx.Timeout(15.0, connect=10.0)


class ErroAuth(Exception):
    """Erro vindo do Supabase, já com uma mensagem que dá para mostrar."""

    def __init__(self, mensagem: str, status: int = 400, codigo: str | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status
        self.codigo = codigo


@dataclass
class Sessao:
    access_token: str
    refresh_token: str
    expira_em: int            # epoch, segundos
    auth_id: str
    email: str
    metadados: dict


@dataclass
class Identidade:
    auth_id: str
    email: str
    metadados: dict


def configurado() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_ANON_KEY)


def admin_configurado() -> bool:
    return configurado() and bool(config.SUPABASE_SERVICE_KEY)


def exigir_configuracao() -> None:
    if not configurado():
        raise ErroAuth(
            "O login não está configurado: faltam SUPABASE_URL e SUPABASE_ANON_KEY "
            "(veja .env.example).", 503, "nao_configurado")


# --------------------------------------------------------------------------- #
# Conversa com o Supabase
# --------------------------------------------------------------------------- #

_cliente: httpx.Client | None = None
_trava_cliente = threading.Lock()


def _http() -> httpx.Client:
    global _cliente
    with _trava_cliente:
        if _cliente is None:
            _cliente = httpx.Client(base_url=f"{config.SUPABASE_URL}/auth/v1",
                                    timeout=TEMPO_LIMITE)
        return _cliente


# Mensagens do Supabase (em inglês) traduzidas pelo código do erro. O que não
# estiver aqui cai na mensagem genérica, para não mostrar inglês na tela.
_TRADUCOES = {
    "invalid_credentials": "E-mail ou senha incorretos.",
    "email_not_confirmed": "Confirme seu e-mail antes de entrar: abra o link que "
                           "mandamos quando você se cadastrou.",
    "user_already_exists": "Já existe uma conta com esse e-mail.",
    "email_exists": "Já existe uma conta com esse e-mail.",
    "weak_password": "Essa senha é fraca demais. Use pelo menos 8 caracteres, "
                     "misturando letras e números.",
    "same_password": "A senha nova precisa ser diferente da atual.",
    "over_email_send_rate_limit": "Muitos e-mails enviados em pouco tempo. Espere "
                                  "alguns minutos e tente de novo.",
    "over_request_rate_limit": "Muitas tentativas seguidas. Espere um pouco e "
                               "tente de novo.",
    "otp_expired": "O link expirou ou já foi usado. Peça outro.",
    "flow_state_expired": "O link expirou. Peça outro.",
    "refresh_token_not_found": "Sessão expirada. Entre de novo.",
    "refresh_token_already_used": "Sessão expirada. Entre de novo.",
    "session_not_found": "Sessão expirada. Entre de novo.",
    "bad_jwt": "Sessão inválida. Entre de novo.",
    "user_banned": "Esta conta foi bloqueada.",
    "email_address_invalid": "Esse e-mail não é aceito. Confira o endereço.",
    "signup_disabled": "Cadastros estão fechados no momento.",
}


def _erro(r: httpx.Response) -> ErroAuth:
    try:
        corpo = r.json()
    except ValueError:
        corpo = {}
    codigo = corpo.get("error_code") or corpo.get("code") or corpo.get("error")
    if isinstance(codigo, int):
        codigo = None
    texto = (corpo.get("msg") or corpo.get("message")
             or corpo.get("error_description") or "")
    # Versões antigas do Auth não mandam error_code: reconhece pelo texto.
    if not codigo:
        t = texto.lower()
        if "invalid login credentials" in t:
            codigo = "invalid_credentials"
        elif "email not confirmed" in t:
            codigo = "email_not_confirmed"
        elif "already registered" in t:
            codigo = "user_already_exists"
        elif "expired" in t or ("invalid" in t and "token" in t):
            codigo = "otp_expired"
    mensagem = _TRADUCOES.get(codigo or "")
    if mensagem is None:
        if r.status_code == 429:
            mensagem = _TRADUCOES["over_request_rate_limit"]
        elif r.status_code >= 500:
            mensagem = "O serviço de login não respondeu. Tente de novo em instantes."
        else:
            mensagem = "Não foi possível concluir. Confira os dados e tente de novo."
    status = r.status_code if r.status_code < 500 else 502
    if status == 422:
        status = 400
    return ErroAuth(mensagem, status, codigo)


def _pedir(metodo: str, caminho: str, *, chave: str | None = None,
           token: str | None = None, **kw) -> dict:
    exigir_configuracao()
    chave = chave or config.SUPABASE_ANON_KEY
    cab = {"apikey": chave}
    # O token da pessoa vai no Authorization. Sem ele, vai a própria chave, mas
    # só se ela for das antigas (anon/service_role, que são JWT, começam com
    # "eyJ"). As novas (sb_publishable_..., sb_secret_...) não são JWT e vão
    # só no apikey: o Supabase cuida do resto.
    if token:
        cab["Authorization"] = f"Bearer {token}"
    elif chave.startswith("eyJ"):
        cab["Authorization"] = f"Bearer {chave}"
    try:
        r = _http().request(metodo, caminho, headers=cab, **kw)
    except httpx.HTTPError as e:
        raise ErroAuth("O serviço de login não respondeu. Tente de novo em instantes.",
                       502, "rede") from e
    if r.status_code >= 400:
        raise _erro(r)
    if not r.content:
        return {}
    try:
        return r.json()
    except ValueError:
        return {}


def _admin(metodo: str, caminho: str, **kw) -> dict:
    if not admin_configurado():
        raise ErroAuth("Falta SUPABASE_SERVICE_KEY no servidor para esta operação.",
                       503, "nao_configurado")
    return _pedir(metodo, caminho, chave=config.SUPABASE_SERVICE_KEY, **kw)


def _sessao(d: dict) -> Sessao:
    usuario = d.get("user") or {}
    expira = d.get("expires_at") or (int(time.time()) + int(d.get("expires_in") or 3600))
    return Sessao(
        access_token=d["access_token"], refresh_token=d.get("refresh_token", ""),
        expira_em=int(expira), auth_id=usuario.get("id", ""),
        email=(usuario.get("email") or "").lower(),
        metadados=usuario.get("user_metadata") or {},
    )


# --------------------------------------------------------------------------- #
# O que a pessoa faz
# --------------------------------------------------------------------------- #

def cadastrar(email: str, senha: str, metadados: dict, volta: str) -> tuple[str, bool]:
    """Cria a conta e manda o e-mail de confirmação.

    Devolve (auth_id, ja_confirmado). ja_confirmado só é True quando o projeto
    está com a confirmação de e-mail desligada.
    """
    d = _pedir("POST", "/signup", params={"redirect_to": volta},
               json={"email": email, "password": senha, "data": metadados})
    usuario = d.get("user") or d
    # Com a confirmação ligada, e-mail já cadastrado não dá erro: o Supabase
    # devolve um usuário de mentira, sem identidades, para não revelar que o
    # e-mail existe. Aqui a gente precisa saber, porque é o nosso cadastro.
    if usuario.get("identities") == []:
        raise ErroAuth(_TRADUCOES["user_already_exists"], 409, "user_already_exists")
    if not usuario.get("id"):
        raise ErroAuth("O serviço de login não devolveu a conta criada.", 502)
    confirmado = bool(usuario.get("email_confirmed_at") or d.get("access_token"))
    return usuario["id"], confirmado


def entrar(email: str, senha: str) -> Sessao:
    d = _pedir("POST", "/token", params={"grant_type": "password"},
               json={"email": email, "password": senha})
    return _sessao(d)


def renovar(refresh_token: str) -> Sessao:
    d = _pedir("POST", "/token", params={"grant_type": "refresh_token"},
               json={"refresh_token": refresh_token})
    return _sessao(d)


def sair(access_token: str, escopo: str = "local") -> None:
    """escopo: local (esta sessão), others (as outras) ou global (todas)."""
    try:
        _pedir("POST", "/logout", token=access_token, params={"scope": escopo})
    except ErroAuth:
        pass          # token já expirado: do nosso lado a sessão acabou igual


def pedir_nova_senha(email: str, volta: str) -> None:
    """Manda o e-mail com o link de nova senha. Silencioso para e-mail que não existe."""
    _pedir("POST", "/recover", params={"redirect_to": volta}, json={"email": email})


def reenviar_confirmacao(email: str, volta: str) -> None:
    _pedir("POST", "/resend", params={"redirect_to": volta},
           json={"type": "signup", "email": email})


def verificar_link(token_hash: str, tipo: str) -> Sessao:
    """Troca o token_hash que veio no link do e-mail por uma sessão.

    tipo: "recovery" (nova senha) ou "email"/"signup" (confirmação de cadastro).
    O link do e-mail abre uma tela nossa e é ela que chama isto, num clique.
    Assim, o robô de antivírus que abre todo link de e-mail para conferir não
    gasta o token antes da pessoa.
    """
    d = _pedir("POST", "/verify", json={"type": tipo, "token_hash": token_hash})
    if "access_token" not in d:
        raise ErroAuth(_TRADUCOES["otp_expired"], 400, "otp_expired")
    return _sessao(d)


def trocar_senha(access_token: str, senha_nova: str) -> None:
    _pedir("PUT", "/user", token=access_token, json={"password": senha_nova})


# --------------------------------------------------------------------------- #
# O que só o servidor faz (chave secreta)
# --------------------------------------------------------------------------- #

def admin_criar(email: str, senha: str, metadados: dict | None = None) -> str:
    """Cria uma conta já confirmada, sem mandar e-mail. Devolve o auth_id."""
    d = _admin("POST", "/admin/users", json={
        "email": email, "password": senha, "email_confirm": True,
        "user_metadata": metadados or {}})
    return d["id"]


def admin_buscar_por_email(email: str) -> dict | None:
    """O Auth não tem busca por e-mail na API: percorre as páginas."""
    email = email.lower()
    pagina = 1
    while True:
        d = _admin("GET", "/admin/users", params={"page": pagina, "per_page": 200})
        usuarios = d.get("users") or []
        for u in usuarios:
            if (u.get("email") or "").lower() == email:
                return u
        if len(usuarios) < 200:
            return None
        pagina += 1


def admin_trocar_senha(auth_id: str, senha: str) -> None:
    _admin("PUT", f"/admin/users/{auth_id}", json={"password": senha})


def admin_confirmar_email(auth_id: str) -> None:
    _admin("PUT", f"/admin/users/{auth_id}", json={"email_confirm": True})


def admin_apagar(auth_id: str) -> None:
    _admin("DELETE", f"/admin/users/{auth_id}")


# --------------------------------------------------------------------------- #
# Conferência do token em cada requisição
# --------------------------------------------------------------------------- #

_jwks: jwt.PyJWKClient | None = None
_cache_usuario: dict[str, tuple[float, Identidade]] = {}
_trava_cache = threading.Lock()


def _cliente_jwks() -> jwt.PyJWKClient:
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(
            f"{config.SUPABASE_URL}/auth/v1/.well-known/jwks.json",
            cache_keys=True, lifespan=3600, timeout=10,
            headers={"apikey": config.SUPABASE_ANON_KEY})
    return _jwks


def _identidade(claims: dict) -> Identidade:
    return Identidade(auth_id=claims["sub"], email=(claims.get("email") or "").lower(),
                      metadados=claims.get("user_metadata") or {})


def conferir(token: str) -> Identidade | None:
    """Quem é o dono do token, ou None se o token não vale."""
    if not configurado() or not token:
        return None
    try:
        alg = jwt.get_unverified_header(token).get("alg", "")
    except jwt.PyJWTError:
        return None

    opcoes = {"require": ["exp", "sub"]}
    emissor = f"{config.SUPABASE_URL}/auth/v1"
    try:
        if alg == "HS256":
            if config.SUPABASE_JWT_SECRET:
                claims = jwt.decode(token, config.SUPABASE_JWT_SECRET,
                                    algorithms=["HS256"], audience="authenticated",
                                    issuer=emissor, options=opcoes)
                return _identidade(claims)
            return _perguntar_ao_supabase(token)
        chave = _cliente_jwks().get_signing_key_from_jwt(token)
        claims = jwt.decode(token, chave.key, algorithms=["ES256", "RS256", "EdDSA"],
                            audience="authenticated", issuer=emissor, options=opcoes)
        return _identidade(claims)
    except jwt.ExpiredSignatureError:
        return None
    except jwt.PyJWKClientError:
        # Sem acesso à chave pública agora: pergunta direto, que também confere.
        return _perguntar_ao_supabase(token)
    except jwt.PyJWTError:
        return None


def _perguntar_ao_supabase(token: str) -> Identidade | None:
    chave = hashlib.sha256(token.encode()).hexdigest()
    agora = time.time()
    with _trava_cache:
        guardado = _cache_usuario.get(chave)
        if guardado and guardado[0] > agora:
            return guardado[1]
    try:
        u = _pedir("GET", "/user", token=token)
    except ErroAuth:
        return None
    ident = Identidade(auth_id=u["id"], email=(u.get("email") or "").lower(),
                       metadados=u.get("user_metadata") or {})
    with _trava_cache:
        if len(_cache_usuario) > 2000:
            _cache_usuario.clear()
        _cache_usuario[chave] = (agora + 60, ident)
    return ident
