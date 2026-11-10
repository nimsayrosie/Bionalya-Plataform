"""Bionalya — API.

Sobe com:   python -m uvicorn api.main:app --reload
Documentação automática em /docs
As telas são servidas na raiz: http://127.0.0.1:8000/
"""

from __future__ import annotations

import json
import re
import unicodedata
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import (Depends, FastAPI, File, Form, Header, HTTPException,
                     UploadFile, status)
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import arquivos, banco, config, modelos, seguranca, treino

# --------------------------------------------------------------------------- #
# Partida
# --------------------------------------------------------------------------- #

def iniciar() -> None:
    novas = banco.criar_tabelas()
    if novas:
        print("Banco atualizado: " + ", ".join(novas))
    config.PASTA_ENVIADAS.mkdir(parents=True, exist_ok=True)
    # Antes de semear: _semear_antibioticos lê os modelos do disco.
    recriados = arquivos.restaurar()
    if recriados:
        print(f"{len(recriados)} arquivo(s) recriados a partir do banco.")
    with banco.sessao() as db:
        _semear_bases(db)
        _liberar_bases_em_analise(db)
        _semear_antibioticos(db)
        _semear_equipe(db)
        _semear_demo(db)


def _liberar_bases_em_analise(db: Session) -> None:
    """Versões anteriores seguravam a base até alguém da equipe aprovar.

    A aprovação deixou de existir: quem envia usa na hora. As bases que
    ficaram paradas na fila são liberadas aqui, para não sumirem do mapa.
    """
    paradas = db.execute(
        select(banco.BaseDados).where(banco.BaseDados.situacao == "em_analise")
    ).scalars().all()
    for b in paradas:
        b.situacao = "aprovada"
        b.decidida_em = banco.agora()
        b.decidida_por = "liberação automática"
    if paradas:
        db.commit()
        print(f"{len(paradas)} base(s) que estavam em análise foram liberadas.")


def _semear_bases(db: Session) -> None:
    """A base que vem de fábrica entra na tabela se ainda não estiver lá."""
    linha = db.get(banco.BaseDados, config.BASE_PADRAO)
    if linha is not None:
        # O arquivo pode ter mudado entre a completa e a amostra.
        if linha.arquivo != config.ARQUIVO_BASE_PADRAO:
            linha.arquivo = config.ARQUIVO_BASE_PADRAO
            linha.n_isolados = linha.n_com_ast = 0     # recontar
            db.commit()
        return
    db.add(banco.BaseDados(
        id=config.BASE_PADRAO, nome="Neisseria gonorrhoeae (NCBI)",
        especie=config.ESPECIE_PADRAO, arquivo=config.ARQUIVO_BASE_PADRAO,
        origem="inicial", enviada_por="sistema",
        observacao="Baixada do NCBI Pathogen Detection.",
    ))
    db.commit()


def _semear_antibioticos(db: Session) -> None:
    """Cada modelo treinado em disco vira uma linha da tabela de antibióticos."""
    for meta in modelos.listar_metadados():
        chave = meta["chave"]
        if db.get(banco.Antibiotico, chave):
            continue
        db.add(banco.Antibiotico(
            id=chave, base_id=meta["base_id"], nome_base=meta["nome_base"],
            nome=config.nome_pt(meta["nome_base"]),
            especie=meta.get("especie", config.ESPECIE_PADRAO),
            ativo=True, criado_por="treino inicial",
        ))
    db.commit()


def _semear_equipe(db: Session) -> None:
    """Primeiro acesso: cria a conta de admin com senha aleatória e escreve as
    credenciais num arquivo local, que o .gitignore não deixa subir."""
    if db.execute(select(banco.Usuario)
                  .where(banco.Usuario.papel == "admin")).scalars().first():
        return

    email = config.ADMIN_EMAIL

    # Banco de uma versão anterior, de quando só existiam dois papéis: promove
    # a conta que já era da equipe em vez de criar outra. Criar duplicaria o
    # e-mail, que é único, e a partida quebraria.
    antiga = db.execute(
        select(banco.Usuario)
        .where((banco.Usuario.email == email) | (banco.Usuario.papel == "equipe"))
        .order_by(banco.Usuario.criado_em)
    ).scalars().first()
    if antiga is not None:
        antiga.papel = "admin"
        antiga.status = "aprovado"
        antiga.ativo = True
        db.commit()
        print(f"\nConta {antiga.email} promovida a admin (banco de versão anterior).\n"
              "A senha continua a mesma.\n")
        return

    # Na hospedagem a senha vem do ambiente, e precisa ser sempre a mesma: o
    # disco é descartável, o banco volta do zero a cada reinício e uma senha
    # sorteada deixaria todo mundo de fora. Na sua máquina, sorteia.
    senha = config.ADMIN_SENHA or seguranca.senha_aleatoria()
    db.add(banco.Usuario(
        nome="Equipe Bionalya", email=email,
        instituicao="Centro Universitário Dom Helder",
        vinculo="pesquisador", finalidade="Administração da plataforma.",
        senha_hash=seguranca.hash_senha(senha),
        papel="admin", status="aprovado",
        decidido_em=banco.agora(), decidido_por="sistema",
    ))
    db.commit()

    aviso = (
        "PRIMEIRO ACESSO DA BIONALYA\n"
        "===========================\n\n"
        f"E-mail: {email}\n"
        f"Senha:  {senha}\n\n"
        "Esta é a conta de ADMIN: aprova cadastros, treina modelos e\n"
        "gerencia os papéis das outras pessoas.\n"
        "A senha foi gerada aleatoriamente nesta máquina e não está no\n"
        "repositório. Troque-a antes de usar a plataforma com outras pessoas,\n"
        "e apague este arquivo depois de anotar.\n"
    )
    if config.ADMIN_SENHA:
        # Senha veio do ambiente: já é conhecida, não faz sentido gravar em arquivo.
        print(f"\nAdmin criado a partir das variáveis de ambiente: {email}\n")
    else:
        (config.RAIZ / "PRIMEIRO-ACESSO.txt").write_text(aviso, encoding="utf-8")
        print("\n" + aviso)


def _semear_demo(db: Session) -> None:
    """Conta de demonstração, para compartilhar o link sem dar acesso de equipe.

    Só existe quando BIONALYA_DEMO_EMAIL e BIONALYA_DEMO_SENHA estão definidas.
    É um pesquisador comum: analisa e consulta, mas não libera acesso, não
    treina modelo e não importa base.
    """
    if not (config.DEMO_EMAIL and config.DEMO_SENHA):
        return
    if db.execute(select(banco.Usuario)
                  .where(banco.Usuario.email == config.DEMO_EMAIL.lower())
                  ).scalars().first():
        return
    db.add(banco.Usuario(
        nome=config.DEMO_NOME, email=config.DEMO_EMAIL.lower(),
        instituicao="—", vinculo="estudante",
        finalidade="Conta aberta para demonstração da plataforma.",
        senha_hash=seguranca.hash_senha(config.DEMO_SENHA),
        papel="pesquisador", status="aprovado",
        decidido_em=banco.agora(), decidido_por="sistema",
    ))
    db.commit()
    print(f"Conta de demonstração disponível: {config.DEMO_EMAIL}")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    # Roda uma vez, quando a API sobe: cria as tabelas e semeia o que falta.
    # (A forma antiga, @app.on_event("startup"), foi descontinuada e some nas
    #  versões novas do Starlette.)
    iniciar()
    yield


app = FastAPI(
    title="Bionalya",
    description="Previsão de resistência bacteriana a antibióticos. "
                "Protótipo de pesquisa, sem validação clínica.",
    version="0.1.0",
    lifespan=ciclo_de_vida,
)

# Cada CSV é lido uma vez e fica em memória. A base padrão tem 32 MB; reler a
# cada requisição deixaria a busca inutilizável.
_base_cache: dict[str, pd.DataFrame] = {}


def caminho_da_base(linha) -> Path:
    pasta = config.PASTA_ENVIADAS if linha.origem == "upload" else config.PASTA_DADOS
    return pasta / linha.arquivo


def dono_da_base(linha, u) -> bool:
    return bool(u and linha.enviada_por
                and linha.enviada_por.lower() == u.email.lower())


def base_visivel(linha, u) -> bool:
    """Base aprovada todo mundo vê. Em análise ou recusada, só o dono e a equipe.

    Devolver 404 em vez de 403 para base alheia é de propósito: quem não pode
    ver uma base também não precisa saber que ela existe.
    """
    if linha.situacao == "aprovada":
        return True
    return banco.pode(u, "equipe") or dono_da_base(linha, u)


def exigir_base(db: Session, base_id: str | None, u) -> banco.BaseDados:
    linha = db.get(banco.BaseDados, base_id or config.BASE_PADRAO)
    if linha is None or not base_visivel(linha, u):
        raise HTTPException(404, "Base não encontrada.")
    return linha


def exigir_antibiotico_visivel(db: Session, chave: str, u) -> None:
    """A chave de um antibiótico carrega a base dele; vale a mesma regra."""
    base_id, _ = modelos.partir(chave)
    exigir_base(db, base_id, u)


def pode_treinar(linha, u) -> bool:
    """Quem enviou a base treina os modelos dela; a equipe treina em qualquer uma."""
    return banco.pode(u, "equipe") or dono_da_base(linha, u)


def exigir_treino(linha, u) -> None:
    if not pode_treinar(linha, u):
        raise HTTPException(
            403, "Só quem enviou esta base, ou alguém da equipe, pode treinar "
                 "modelos com ela.")


def carregar_base_por_id(db: Session, base_id: str | None, u=None):
    linha = (exigir_base(db, base_id, u) if u is not None
             else db.get(banco.BaseDados, base_id or config.BASE_PADRAO))
    if linha is None:
        raise HTTPException(404, "Base não encontrada.")
    caminho = caminho_da_base(linha)
    chave = f"{linha.id}:{caminho}"
    if chave not in _base_cache:
        if not caminho.exists():
            raise HTTPException(
                503, f"O arquivo da base '{linha.nome}' não está em "
                     f"{caminho.parent.name}/. Veja o README para baixar, ou suba a "
                     "base de novo pela tela Bases.")
        _base_cache[chave] = treino.carregar_base(caminho)
    return linha, _base_cache[chave]


def esquecer_base(base_id: str) -> None:
    for k in [k for k in _base_cache if k.startswith(f"{base_id}:")]:
        _base_cache.pop(k, None)


def base_ncbi() -> pd.DataFrame:
    """Atalho para a base padrão, usado onde não há escolha de base."""
    chave = f"{config.BASE_PADRAO}:{config.CAMINHO_BASE}"
    if chave not in _base_cache:
        _base_cache[chave] = treino.carregar_base(config.CAMINHO_BASE)
    return _base_cache[chave]


# --------------------------------------------------------------------------- #
# Dependências de autenticação
# --------------------------------------------------------------------------- #

def db_sessao():
    db = banco.sessao()
    try:
        yield db
    finally:
        db.close()


Db = Annotated[Session, Depends(db_sessao)]


def _token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    partes = authorization.split()
    return partes[1] if len(partes) == 2 and partes[0].lower() == "bearer" else None


def usuario_atual(db: Db,
                  authorization: Annotated[str | None, Header()] = None
                  ) -> banco.Usuario:
    tok = _token(authorization)
    u = banco.buscar_por_token(db, tok) if tok else None
    if u is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Sessão inválida ou expirada. Entre de novo.")
    if u.status != "aprovado":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Seu acesso ainda não foi liberado.")
    if not u.ativo:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Esta conta foi desativada.")
    return u


def usuario_equipe(u: Annotated[banco.Usuario, Depends(usuario_atual)]
                   ) -> banco.Usuario:
    if not banco.pode(u, "equipe"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Só a equipe pode fazer isso.")
    return u


def usuario_admin(u: Annotated[banco.Usuario, Depends(usuario_atual)]
                  ) -> banco.Usuario:
    if not banco.pode(u, "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Só quem é admin pode fazer isso.")
    return u


Logado = Annotated[banco.Usuario, Depends(usuario_atual)]
Equipe = Annotated[banco.Usuario, Depends(usuario_equipe)]
Admin = Annotated[banco.Usuario, Depends(usuario_admin)]


# --------------------------------------------------------------------------- #
# Modelos de entrada
# --------------------------------------------------------------------------- #

class CadastroEntrada(BaseModel):
    nome: str = Field(min_length=3, max_length=160)
    email: EmailStr
    instituicao: str = Field(min_length=2, max_length=160)
    vinculo: str
    finalidade: str = Field(min_length=10, max_length=2000)
    senha: str
    termos: bool


class RecuperarEntrada(BaseModel):
    # str e não EmailStr: e-mail mal digitado recebe a mesma resposta de
    # sempre, sem erro de validação que entregue alguma coisa.
    email: str = Field(max_length=160)
    mensagem: str | None = Field(default=None, max_length=500)


class SessaoEntrada(BaseModel):
    # Aqui é str, não EmailStr: a validação forte fica no cadastro. No login
    # a gente só precisa comparar com o que já está guardado.
    email: str
    senha: str


class DecisaoEntrada(BaseModel):
    aprovar: bool
    motivo: str | None = None


class PrevisaoEntrada(BaseModel):
    antibiotico: str
    genes: list[str] = Field(default_factory=list)
    especie: str | None = None
    modelo: str | None = None          # None usa o padrão do antibiótico


class SenhaEntrada(BaseModel):
    senha_atual: str
    senha_nova: str


class PapelEntrada(BaseModel):
    papel: str


class AtivoEntrada(BaseModel):
    ativo: bool


class ContaEntrada(BaseModel):
    """Conta criada pelo admin para compartilhar o acesso.

    A senha é opcional: sem ela, a API sorteia uma e devolve uma única vez na
    resposta. Depois disso ninguém mais consegue lê-la — o banco só tem o hash.
    """
    nome: str = Field(min_length=3, max_length=160)
    email: EmailStr
    papel: str = "pesquisador"
    senha: str | None = None
    instituicao: str = "—"
    observacao: str = ""


class PadraoEntrada(BaseModel):
    modelo: str | None = None          # None volta para o recomendado


class TreinoEntrada(BaseModel):
    antibiotico: str                 # nome como aparece na base (ex.: "tetracycline")
    base: str | None = None          # None usa a base padrão
    nome_exibicao: str | None = None
    limiar: float = Field(default=0.5, ge=0.05, le=0.95)


# --------------------------------------------------------------------------- #
# Acesso
# --------------------------------------------------------------------------- #

@app.post("/api/cadastro", status_code=201, tags=["acesso"])
def cadastrar(entrada: CadastroEntrada, db: Db):
    if not entrada.termos:
        raise HTTPException(400, "É preciso aceitar os termos para solicitar acesso.")
    if entrada.vinculo not in banco.VINCULOS:
        raise HTTPException(400, f"Vínculo inválido. Use um de: {', '.join(banco.VINCULOS)}.")
    if (erro := seguranca.criticar_senha(entrada.senha)):
        raise HTTPException(400, erro)

    ja = db.execute(select(banco.Usuario)
                    .where(banco.Usuario.email == entrada.email.lower())).scalars().first()
    if ja:
        raise HTTPException(409, "Já existe uma solicitação com esse e-mail.")

    db.add(banco.Usuario(
        nome=entrada.nome.strip(), email=entrada.email.lower(),
        instituicao=entrada.instituicao.strip(), vinculo=entrada.vinculo,
        finalidade=entrada.finalidade.strip(),
        senha_hash=seguranca.hash_senha(entrada.senha),
        papel="pesquisador", status="em_analise",
    ))
    db.commit()
    return {"status": "em_analise",
            "mensagem": "Solicitação enviada. A equipe responde no e-mail cadastrado."}


@app.post("/api/sessao", tags=["acesso"])
def entrar(entrada: SessaoEntrada, db: Db):
    u = db.execute(select(banco.Usuario)
                   .where(banco.Usuario.email == entrada.email.lower())).scalars().first()
    # Mesma resposta para e-mail inexistente e senha errada: não entregamos
    # a quem está tentando a informação de que o e-mail existe.
    if u is None or not seguranca.conferir_senha(entrada.senha, u.senha_hash):
        raise HTTPException(401, "E-mail ou senha incorretos.")
    if u.status == "em_analise":
        raise HTTPException(403, "Sua solicitação ainda está em análise.")
    if u.status == "recusado":
        raise HTTPException(403, "Sua solicitação de acesso foi recusada.")

    s = banco.Sessao.nova(u)
    db.add(s)
    db.commit()
    return {"token": s.token, "expira_em": s.expira_em.isoformat(),
            "usuario": u.publico()}


@app.delete("/api/sessao", status_code=204, tags=["acesso"])
def sair(db: Db, authorization: Annotated[str | None, Header()] = None):
    tok = _token(authorization)
    if tok and (s := db.get(banco.Sessao, tok)):
        db.delete(s)
        db.commit()


# Recuperação de senha, sem e-mail. A pessoa pede pela tela esqueci-senha.html,
# a equipe recebe um aviso e um admin gera uma senha nova na tela Usuários,
# que ele passa para a pessoa. Sem serviço de e-mail, é o caminho que funciona
# no plano grátis; quando o projeto tiver um, o pedido vira um link por e-mail.

RESPOSTA_RECUPERAR = (
    "Pedido registrado. Se o e-mail estiver cadastrado, a equipe vai gerar uma "
    "senha nova e entrar em contato com você pelo e-mail do cadastro.")


@app.post("/api/recuperar-senha", tags=["acesso"])
def recuperar_senha(entrada: RecuperarEntrada, db: Db):
    """Pede uma senha nova. Responde sempre igual, exista ou não a conta."""
    email = entrada.email.strip().lower()
    u = db.execute(select(banco.Usuario)
                   .where(banco.Usuario.email == email)).scalars().first()
    # Só vira aviso para conta que consegue entrar: em análise, recusada ou
    # desativada não adianta senha nova.
    if u is None or u.status != "aprovado" or not u.ativo:
        return {"mensagem": RESPOSTA_RECUPERAR}

    # Um pedido em aberto por pessoa basta. Clicar dez vezes não gera dez avisos.
    ja_pediu = db.execute(
        select(banco.Notificacao)
        .where(banco.Notificacao.tipo == "senha",
               banco.Notificacao.autor == email,
               banco.Notificacao.lida_em.is_(None))
    ).scalars().first()
    if ja_pediu is None:
        recado = (entrada.mensagem or "").strip()
        banco.avisar(
            db, "senha", f"{u.nome} esqueceu a senha",
            f"{email} pediu uma senha nova."
            + (f" Recado: “{recado}”" if recado else "")
            + " Um admin gera a senha nova na tela Usuários.",
            link=f"usuarios.html?busca={email}", autor=email)
    return {"mensagem": RESPOSTA_RECUPERAR}


@app.get("/api/eu", tags=["acesso"])
def eu(u: Logado):
    return u.publico()



@app.post("/api/eu/senha", tags=["acesso"])
def trocar_senha(entrada: SenhaEntrada, u: Logado, db: Db,
                 authorization: Annotated[str | None, Header()] = None):
    if not seguranca.conferir_senha(entrada.senha_atual, u.senha_hash):
        raise HTTPException(400, "A senha atual está incorreta.")
    if (erro := seguranca.criticar_senha(entrada.senha_nova)):
        raise HTTPException(400, erro)
    if entrada.senha_atual == entrada.senha_nova:
        raise HTTPException(400, "A senha nova precisa ser diferente da atual.")

    u.senha_hash = seguranca.hash_senha(entrada.senha_nova)
    u.senha_trocada = True
    # Trocar a senha derruba as outras sessões; a desta aba continua valendo,
    # para a pessoa não ser deslogada no meio da própria troca.
    atual = _token(authorization)
    derrubadas = 0
    for s in list(u.sessoes):
        if s.token != atual:
            db.delete(s)
            derrubadas += 1
    db.commit()
    return {"ok": True, "sessoes_encerradas": derrubadas,
            "mensagem": "Senha trocada." + (
                f" {derrubadas} outra(s) sessão(ões) foram encerradas."
                if derrubadas else "")}


# --------------------------------------------------------------------------- #
# Administração
# --------------------------------------------------------------------------- #

@app.get("/api/admin/usuarios", tags=["admin"])
def listar_usuarios(_: Admin, db: Db, papel: str | None = None,
                    busca: str | None = None):
    q = select(banco.Usuario).order_by(banco.Usuario.criado_em.desc())
    if papel:
        q = q.where(banco.Usuario.papel == papel)
    usuarios = db.execute(q).scalars().all()
    if busca:
        alvo = busca.strip().lower()
        usuarios = [u for u in usuarios
                    if alvo in u.nome.lower() or alvo in u.email.lower()
                    or alvo in (u.instituicao or "").lower()]
    return {
        "resumo": {p: banco.contar(db, banco.Usuario, papel=p) for p in banco.PAPEIS},
        "usuarios": [u.publico() for u in usuarios],
    }


@app.post("/api/admin/usuarios/{usuario_id}/papel", tags=["admin"])
def mudar_papel(usuario_id: int, entrada: PapelEntrada, adm: Admin, db: Db):
    if entrada.papel not in banco.PAPEIS:
        raise HTTPException(400, f"Papel inválido. Use um de: {', '.join(banco.PAPEIS)}.")
    u = db.get(banco.Usuario, usuario_id)
    if u is None:
        raise HTTPException(404, "Usuário não encontrado.")
    if u.id == adm.id:
        raise HTTPException(400, "Você não pode mudar o seu próprio papel.")
    if u.papel == "admin" and entrada.papel != "admin" and _conta_admins(db) <= 1:
        raise HTTPException(400, "Este é o único admin. Promova outra pessoa antes.")

    u.papel = entrada.papel
    if entrada.papel in ("equipe", "admin") and u.status != "aprovado":
        u.status = "aprovado"                 # promover já libera o acesso
        u.decidido_em = banco.agora()
        u.decidido_por = adm.email
    db.commit()
    return u.publico()


@app.post("/api/admin/usuarios/{usuario_id}/ativo", tags=["admin"])
def mudar_ativo(usuario_id: int, entrada: AtivoEntrada, adm: Admin, db: Db):
    u = db.get(banco.Usuario, usuario_id)
    if u is None:
        raise HTTPException(404, "Usuário não encontrado.")
    if u.id == adm.id:
        raise HTTPException(400, "Você não pode desativar a sua própria conta.")
    if not entrada.ativo and u.papel == "admin" and _conta_admins(db) <= 1:
        raise HTTPException(400, "Este é o único admin ativo.")

    u.ativo = entrada.ativo
    if not entrada.ativo:                     # desativou: derruba as sessões
        for s in list(u.sessoes):
            db.delete(s)
    db.commit()
    return u.publico()


@app.post("/api/admin/usuarios/{usuario_id}/senha", tags=["admin"])
def gerar_senha_nova(usuario_id: int, adm: Admin, db: Db):
    """Sorteia uma senha nova para alguém que esqueceu a sua.

    A senha aparece uma vez só, na resposta. A conta volta ao estado de "senha
    inicial" (a tela Minha conta pede para trocar), as sessões abertas caem e
    os pedidos de senha dessa pessoa saem da lista de avisos.
    """
    u = db.get(banco.Usuario, usuario_id)
    if u is None:
        raise HTTPException(404, "Usuário não encontrado.")
    if u.id == adm.id:
        raise HTTPException(400, "Para trocar a sua própria senha, use Minha conta.")

    senha = seguranca.senha_aleatoria()
    u.senha_hash = seguranca.hash_senha(senha)
    u.senha_trocada = False
    for s in list(u.sessoes):
        db.delete(s)
    for n in db.execute(
        select(banco.Notificacao)
        .where(banco.Notificacao.tipo == "senha",
               banco.Notificacao.autor == u.email,
               banco.Notificacao.lida_em.is_(None))
    ).scalars().all():
        n.lida_em = banco.agora()
        n.lida_por = adm.email
    db.commit()
    return {
        "usuario": u.publico(),
        "senha": senha,
        "aviso": "Esta senha aparece uma única vez. Copie agora e mande para a "
                 "pessoa por um canal que você confie. Quando ela entrar, a "
                 "plataforma pede para trocar.",
    }


@app.post("/api/admin/usuarios", status_code=201, tags=["admin"])
def criar_conta(entrada: ContaEntrada, adm: Admin, db: Db):
    """Cria uma conta já aprovada, para compartilhar o acesso com alguém.

    É o caminho curto: a pessoa não precisa se cadastrar e esperar liberação.
    Serve para a banca, para o professor orientador ou para um teste rápido.
    """
    if entrada.papel not in banco.PAPEIS:
        raise HTTPException(400, f"Papel inválido. Use um de: {', '.join(banco.PAPEIS)}.")

    email = entrada.email.strip().lower()
    if db.execute(select(banco.Usuario)
                  .where(banco.Usuario.email == email)).scalars().first():
        raise HTTPException(409, "Já existe uma conta com esse e-mail.")

    gerada = not entrada.senha
    senha = entrada.senha or seguranca.senha_aleatoria()
    problema = seguranca.criticar_senha(senha)
    if problema:
        raise HTTPException(422, problema)

    u = banco.Usuario(
        nome=entrada.nome.strip(), email=email,
        instituicao=(entrada.instituicao or "—").strip(),
        vinculo="pesquisador",
        finalidade=(entrada.observacao
                    or f"Acesso criado por {adm.email} para compartilhamento."),
        senha_hash=seguranca.hash_senha(senha),
        papel=entrada.papel, status="aprovado",
        decidido_em=banco.agora(), decidido_por=adm.email,
        senha_trocada=not gerada,
    )
    db.add(u)
    db.commit()
    return {
        "usuario": u.publico(),
        "senha": senha,
        "gerada": gerada,
        "aviso": "Esta senha aparece uma única vez. Copie agora e mande para a "
                 "pessoa por um canal que você confie — o banco guarda só o hash, "
                 "então nem você nem a equipe conseguem recuperá-la depois.",
    }


def _conta_admins(db: Session) -> int:
    return len([u for u in db.execute(
        select(banco.Usuario).where(banco.Usuario.papel == "admin")
    ).scalars().all() if u.ativo])


@app.post("/api/antibioticos/{antibiotico_id}/padrao", tags=["equipe"])
def definir_padrao(antibiotico_id: str, entrada: PadraoEntrada, u: Logado, db: Db):
    """Define qual dos modelos treinados responde por padrão."""
    linha = db.get(banco.Antibiotico, antibiotico_id)
    meta = modelos.metadados(antibiotico_id)
    if linha is None or meta is None:
        raise HTTPException(404, "Antibiótico não encontrado.")
    exigir_treino(exigir_base(db, linha.base_id, u), u)

    validos = {d["id"] for d in (meta.get("disponiveis") or [])}
    if entrada.modelo is not None and entrada.modelo not in validos:
        raise HTTPException(
            422, f"'{entrada.modelo}' não é um dos modelos treinados para "
                 f"{linha.nome}. Treinados: {', '.join(sorted(validos))}.")

    linha.modelo_padrao = entrada.modelo
    db.commit()
    return {"id": linha.id, "nome": linha.nome,
            "modelo_padrao": linha.modelo_padrao or meta.get("recomendado"),
            "usando_recomendado": linha.modelo_padrao is None}


# --------------------------------------------------------------------------- #
# Exploração da base
# --------------------------------------------------------------------------- #

@app.get("/api/base/isolados", tags=["base"])
def buscar_isolados(u: Logado, db: Db, base: str | None = None,
                    antibiotico: str | None = None,
                    fenotipo: str | None = None, gene: str | None = None,
                    busca: str | None = None, pagina: int = 1,
                    por_pagina: int = 25):
    """Busca nos isolados de uma base. Só leitura, sem modelo envolvido."""
    base_linha, df = carregar_base_por_id(db, base, u)

    col_gen = treino._achar_coluna(df, "amr", "genotype")
    col_ast = treino._achar_coluna(df, "ast", "phenotype")
    col_snp = treino._achar_coluna(df, "snp", "cluster")
    col_iso = treino._achar_coluna(df, "isolate") or df.columns[0]
    col_loc = treino._achar_coluna(df, "location")
    col_fonte = treino._achar_coluna(df, "isolation", "source")

    d = df
    if antibiotico:
        rot = treino._rotulos(d, antibiotico)
        if fenotipo == "resistente":
            d = d.loc[rot == 1]
        elif fenotipo == "sensivel":
            d = d.loc[rot == 0]
        else:
            d = d.loc[rot.notna()]
    if gene:
        alvo = gene.strip().lower()
        d = d.loc[d[col_gen].fillna("").str.lower().str.contains(alvo, regex=False)]
    if busca:
        alvo = busca.strip().lower()
        colunas = [c for c in (col_iso, col_loc, col_fonte) if c]
        marca = None
        for c in colunas:
            m = d[c].fillna("").astype(str).str.lower().str.contains(alvo, regex=False)
            marca = m if marca is None else (marca | m)
        if marca is not None:
            d = d.loc[marca]

    total = int(len(d))
    por_pagina = max(5, min(100, por_pagina))
    inicio = max(0, (max(1, pagina) - 1) * por_pagina)
    recorte = d.iloc[inicio:inicio + por_pagina]

    def txt(row, coluna) -> str:
        """Célula como texto, com vazio de verdade quando falta.

        Cuidado que custou caro: pd.isna devolve NaN para célula vazia, e
        float('nan') é truthy — um `valor or ""` deixa passar a string "nan"
        direto para a tela."""
        if not coluna:
            return ""
        valor = row.get(coluna)
        if valor is None or pd.isna(valor):
            return ""
        return str(valor).strip()

    linhas = []
    for idx, row in recorte.iterrows():
        linhas.append({
            "isolado": txt(row, col_iso) or str(idx),
            "local": txt(row, col_loc),
            "fonte": txt(row, col_fonte),
            "cluster": txt(row, col_snp),
            "genes": treino.extrair_genes(row.get(col_gen)),
            "ast": txt(row, col_ast),
        })

    return {"base": base_linha.publico(), "total": total,
            "pagina": max(1, pagina), "por_pagina": por_pagina,
            "paginas": max(1, -(-total // por_pagina)), "isolados": linhas}


# --------------------------------------------------------------------------- #
# Painel da equipe
# --------------------------------------------------------------------------- #

@app.get("/api/equipe/solicitacoes", tags=["equipe"])
def solicitacoes(_: Equipe, db: Db, situacao: str = "em_analise"):
    q = select(banco.Usuario).order_by(banco.Usuario.criado_em.desc())
    if situacao != "todas":
        q = q.where(banco.Usuario.status == situacao)
    usuarios = db.execute(q).scalars().all()
    return {
        "resumo": {s: banco.contar(db, banco.Usuario, status=s) for s in banco.STATUS},
        "solicitacoes": [x.publico() for x in usuarios if x.papel != "equipe"],
    }


@app.post("/api/equipe/solicitacoes/{usuario_id}/decidir", tags=["equipe"])
def decidir(usuario_id: int, entrada: DecisaoEntrada, equipe: Equipe, db: Db):
    u = db.get(banco.Usuario, usuario_id)
    if u is None:
        raise HTTPException(404, "Solicitação não encontrada.")
    if u.papel == "equipe":
        raise HTTPException(400, "Conta da equipe não passa por aprovação.")

    u.status = "aprovado" if entrada.aprovar else "recusado"
    u.decidido_em = banco.agora()
    u.decidido_por = equipe.email
    u.motivo_recusa = None if entrada.aprovar else (entrada.motivo or None)
    if not entrada.aprovar:                       # recusou: derruba as sessões
        for s in list(u.sessoes):
            db.delete(s)
    db.commit()
    return u.publico()



# --------------------------------------------------------------------------- #
# Avisos para a equipe
# --------------------------------------------------------------------------- #

@app.get("/api/notificacoes", tags=["equipe"])
def listar_notificacoes(_: Equipe, db: Db, limite: int = 30):
    """Avisos para a equipe: base nova, treino e pedido de senha nova."""
    itens = db.execute(
        select(banco.Notificacao)
        .order_by(banco.Notificacao.criada_em.desc())
    ).scalars().all()[:max(1, min(limite, 100))]
    nao_lidas = len([n for n in db.execute(
        select(banco.Notificacao).where(banco.Notificacao.lida_em.is_(None))
    ).scalars().all()])
    return {"nao_lidas": nao_lidas, "avisos": [n.publico() for n in itens]}


@app.post("/api/notificacoes/lidas", tags=["equipe"])
def marcar_lidas(equipe: Equipe, db: Db):
    """Marca tudo como lido. O aviso é da equipe inteira, não de cada pessoa."""
    pendentes = db.execute(
        select(banco.Notificacao).where(banco.Notificacao.lida_em.is_(None))
    ).scalars().all()
    for n in pendentes:
        n.lida_em = banco.agora()
        n.lida_por = equipe.email
    db.commit()
    return {"marcadas": len(pendentes)}


# --------------------------------------------------------------------------- #
# Bases de dados
# --------------------------------------------------------------------------- #

def _slug(texto: str) -> str:
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:70] or "base"


@app.get("/api/termo-base", tags=["base"])
def termo_base():
    """O texto que quem envia uma base precisa aceitar. A tela lê daqui, para
    o que está escrito na página e o que fica guardado serem a mesma coisa."""
    return {"versao": config.TERMO_BASE_VERSAO, "texto": config.TERMO_BASE,
            "max_mb": config.MAX_MB_BASE,
            "min_linhas": config.MIN_LINHAS_BASE,
            "cota_pesquisador": config.MAX_BASES_POR_PESQUISADOR}


def _contar_bases_de(db: Session, email: str) -> int:
    """Quantas bases a pessoa tem, contando as que ainda estão em análise."""
    return len([b for b in db.execute(
        select(banco.BaseDados)
        .where(banco.BaseDados.enviada_por == email.lower())
    ).scalars().all() if b.situacao != "recusada"])


@app.get("/api/bases", tags=["base"])
def listar_bases(u: Logado, db: Db):
    linhas = [b for b in db.execute(
        select(banco.BaseDados).order_by(banco.BaseDados.enviada_em)
    ).scalars().all() if base_visivel(b, u)]
    por_base: dict[str, int] = {}
    for m in modelos.listar_metadados():
        por_base[m["base_id"]] = por_base.get(m["base_id"], 0) + 1
    saida = []
    for b in linhas:
        presente = caminho_da_base(b).exists()
        # A base de fábrica entra na tabela sem contagem, porque contar exige
        # ler 32 MB de CSV e a API não pode demorar para subir. Conta aqui, na
        # primeira vez que alguém abre a lista, e guarda.
        if presente and not b.n_isolados:
            try:
                _, df = carregar_base_por_id(db, b.id)
                col_ast = treino._achar_coluna(df, "ast", "phenotype")
                b.n_isolados = int(len(df))
                b.n_com_ast = int(df[col_ast].notna().sum()) if col_ast else 0
                db.commit()
            except Exception:
                pass                      # a lista aparece mesmo sem a contagem
        d = b.publico()
        d["n_modelos"] = por_base.get(b.id, 0)
        d["arquivo_presente"] = presente
        d["padrao"] = b.id == config.BASE_PADRAO
        d["minha"] = dono_da_base(b, u)
        # Quem pode mexer nesta base: o dono apaga e baixa a dele; a equipe
        # decide o pedido; admin apaga qualquer uma que não seja a de fábrica.
        d["posso_apagar"] = (b.id != config.BASE_PADRAO
                             and (d["minha"] or banco.pode(u, "admin")))
        d["posso_baixar"] = d["minha"] or banco.pode(u, "equipe")
        # Quem enviou a base treina os modelos dela; a equipe treina em qualquer uma.
        d["posso_treinar"] = d["minha"] or banco.pode(u, "equipe")
        saida.append(d)
    return saida


@app.post("/api/bases", status_code=201, tags=["base"])
async def importar_base(u: Logado, db: Db,
                        arquivo: UploadFile = File(...),
                        nome: str = Form(...),
                        especie: str = Form(...),
                        observacao: str = Form(""),
                        termo: bool = Form(False)):
    """Recebe um CSV ou TSV de isolados e passa a servi-lo como mais uma base.

    A base entra valendo na hora, para quem a enviou e para todo mundo: não há
    fila de aprovação. Quem não é da equipe precisa aceitar o termo de
    responsabilidade — o dado é dele e a conta é dele — e a equipe recebe um
    aviso de que a base entrou.
    """
    da_equipe = banco.pode(u, "equipe")

    if not da_equipe:
        if not termo:
            raise HTTPException(
                400, "É preciso aceitar o termo de responsabilidade para enviar "
                     "uma base.")
        quantas = _contar_bases_de(db, u.email)
        if quantas >= config.MAX_BASES_POR_PESQUISADOR:
            raise HTTPException(
                409, f"Você já tem {quantas} bases na plataforma, que é o limite. "
                     "Remova uma antes de enviar outra.")

    if not arquivo.filename or not arquivo.filename.lower().endswith((".csv", ".tsv", ".txt")):
        raise HTTPException(400, "Envie um arquivo .csv ou .tsv exportado do NCBI.")

    base_id = _slug(nome)
    if db.get(banco.BaseDados, base_id):
        raise HTTPException(409, f"Já existe uma base chamada '{nome}'. Use outro nome.")

    config.PASTA_ENVIADAS.mkdir(parents=True, exist_ok=True)
    destino = config.PASTA_ENVIADAS / f"{base_id}{Path(arquivo.filename).suffix.lower()}"

    # Grava em pedaços: um CSV do NCBI pode ter dezenas de MB, e ler tudo em
    # memória antes de validar é pedir para derrubar a API.
    limite = config.MAX_MB_BASE * 1024 * 1024
    escrito = 0
    try:
        with open(destino, "wb") as saida:
            while pedaco := await arquivo.read(1024 * 1024):
                escrito += len(pedaco)
                if escrito > limite:
                    raise HTTPException(413, f"Arquivo maior que {config.MAX_MB_BASE} MB.")
                saida.write(pedaco)
    except HTTPException:
        destino.unlink(missing_ok=True)
        raise
    except Exception as e:
        destino.unlink(missing_ok=True)
        raise HTTPException(400, f"Não deu para salvar o arquivo: {e}")

    # Só agora valida o conteúdo. Se não servir, some com o arquivo.
    try:
        df = treino.carregar_base(destino)
        col_gen = treino._achar_coluna(df, "amr", "genotype")
        col_ast = treino._achar_coluna(df, "ast", "phenotype")
        if col_gen is None:
            raise ValueError(
                "não achei a coluna de genótipo (AMR genotypes). Baixe o CSV de "
                "isolados do NCBI Pathogen Detection, que já traz essa coluna.")
        if col_ast is None:
            raise ValueError(
                "não achei a coluna de antibiograma (AST phenotypes). Sem ela não dá "
                "para treinar nenhum modelo, porque não existe resposta certa.")
        if len(df) < config.MIN_LINHAS_BASE:
            raise ValueError(f"só {len(df)} linhas; o mínimo é {config.MIN_LINHAS_BASE}.")
        n_ast = int(df[col_ast].notna().sum())
        if n_ast == 0:
            raise ValueError(
                "a coluna de antibiograma existe mas está toda vazia. Na exportação "
                "do NCBI, confira se o filtro de AST ficou marcado.")
        treinaveis = [a for a in treino.antibioticos_disponiveis(df) if a["treinavel"]]
    except HTTPException:
        raise
    except Exception as e:
        destino.unlink(missing_ok=True)
        raise HTTPException(422, f"Arquivo recusado: {e}")

    situacao = "aprovada"
    db.add(banco.BaseDados(
        id=base_id, nome=nome.strip(), especie=especie.strip() or "—",
        arquivo=destino.name, origem="upload",
        n_isolados=int(len(df)), n_com_ast=n_ast,
        enviada_por=u.email, observacao=(observacao or "").strip() or None,
        situacao=situacao,
        decidida_em=banco.agora(),
        decidida_por=u.email,
        termo_aceito=True if da_equipe else bool(termo),
        termo_versao=config.TERMO_BASE_VERSAO,
    ))
    db.commit()
    arquivos.guardar(destino)
    esquecer_base(base_id)

    if treinaveis:
        recado = f"{len(treinaveis)} antibiótico(s) com dado suficiente para treinar."
    else:
        recado = ("Nenhum antibiótico desta base tem isolados suficientes nas duas "
                  "classes. A base entra na plataforma para consulta, mas não dá "
                  "para treinar modelo com ela.")
    if not da_equipe:
        recado += (" A base já está valendo: você pode treinar os modelos dela agora "
                   "mesmo, na tela Antibióticos. A equipe foi avisada.")
        banco.avisar(
            db, "base_nova",
            f"{u.nome} importou a base “{nome.strip()}”",
            f"{int(len(df))} isolados, {n_ast} com antibiograma, espécie "
            f"{especie.strip() or '—'}. "
            f"{len(treinaveis)} antibiótico(s) com dado suficiente para treinar.",
            link="bases.html", autor=u.email)

    return {
        "id": base_id, "nome": nome.strip(), "especie": especie.strip(),
        "n_isolados": int(len(df)), "n_com_ast": n_ast, "situacao": situacao,
        "treinaveis": [{"nome_base": a["nome_base"], "nome": config.nome_pt(a["nome_base"]),
                        "n_util": a["n_util"], "confianca": a["confianca"]}
                       for a in treinaveis],
        "mensagem": recado,
    }


@app.get("/api/bases/{base_id}/arquivo", tags=["base"])
def baixar_base(base_id: str, u: Logado, db: Db):
    """Devolve o CSV da base. O dono baixa a dele; a equipe baixa qualquer uma."""
    linha = db.get(banco.BaseDados, base_id)
    if linha is None or not base_visivel(linha, u):
        raise HTTPException(404, "Base não encontrada.")
    if not (dono_da_base(linha, u) or banco.pode(u, "equipe")):
        raise HTTPException(403, "Esta base não é sua.")
    caminho = caminho_da_base(linha)
    if not caminho.exists():
        raise HTTPException(404, "O arquivo desta base não está mais no servidor.")
    return FileResponse(caminho, media_type="text/csv",
                        filename=f"{linha.id}{caminho.suffix}")


@app.delete("/api/bases/{base_id}", tags=["base"])
def apagar_base(base_id: str, u: Logado, db: Db):
    """Remove a base e os modelos treinados com ela. O dono apaga a dele."""
    linha = db.get(banco.BaseDados, base_id)
    if linha is None or not base_visivel(linha, u):
        raise HTTPException(404, "Base não encontrada.")
    if linha.origem == "inicial":
        raise HTTPException(400, "A base que vem de fábrica não pode ser removida.")
    if not (dono_da_base(linha, u) or banco.pode(u, "admin")):
        raise HTTPException(403, "Só quem enviou a base, ou um admin, pode removê-la.")

    n = modelos.apagar_base(base_id)
    arquivos.apagar_pasta(modelos.pasta_da_base(base_id))
    arquivos.apagar(caminho_da_base(linha))
    for a in db.execute(select(banco.Antibiotico)
                        .where(banco.Antibiotico.base_id == base_id)).scalars().all():
        db.delete(a)
    caminho_da_base(linha).unlink(missing_ok=True)
    db.delete(linha)
    db.commit()
    esquecer_base(base_id)
    return {"removida": base_id, "modelos_apagados": n}


# --------------------------------------------------------------------------- #
# Base e antibióticos
# --------------------------------------------------------------------------- #

@app.get("/api/base/resumo", tags=["base"])
def resumo(u: Logado, db: Db, base: str | None = None):
    base_id = base or config.BASE_PADRAO
    metas = modelos.listar_metadados(base_id)
    linha = exigir_base(db, base_id, u)

    total_isolados = linha.n_isolados if linha else None
    com_ast = linha.n_com_ast if linha else None
    # A base de fábrica entra com zeros: só dá para contar lendo o CSV.
    if linha is not None and not total_isolados:
        try:
            _, df = carregar_base_por_id(db, base_id, u)
            total_isolados = int(len(df))
            col = treino._achar_coluna(df, "ast", "phenotype")
            com_ast = int(df[col].notna().sum()) if col else 0
            linha.n_isolados, linha.n_com_ast = total_isolados, com_ast
            db.commit()
        except HTTPException:
            pass

    # "Principal" é o modelo mais confiável, não o que tem mais isolados: a
    # ceftriaxona tem mais linhas, mas só 13 resistentes, e os números dela
    # não representam o que a plataforma faz de melhor.
    ordem = {"alta": 3, "media": 2, "baixa": 1}
    principal = max(metas, default=None,
                    key=lambda m: (ordem.get(m.get("confianca"), 0),
                                   m.get("n_total", 0)))
    return {
        "base_id": base_id,
        "base_nome": linha.nome if linha else "—",
        "total_isolados": total_isolados,
        "com_ast": com_ast,
        "usaveis": principal["n_total"] if principal else None,
        "n_features": principal["n_features"] if principal else None,
        "n_antibioticos": len(metas),
        "especie": (linha.especie if linha else config.ESPECIE_PADRAO),
        "base_disponivel": bool(linha) and caminho_da_base(linha).exists(),
    }


@app.get("/api/base/antibioticos", tags=["base"])
def listar_antibioticos(u: Logado, db: Db, base: str | None = None):
    """Os antibióticos que a plataforma serve, com o modelo de cada um."""
    por_id = {m["chave"]: m for m in modelos.listar_metadados()}
    q = select(banco.Antibiotico).order_by(banco.Antibiotico.nome)
    if base:
        exigir_base(db, base, u)
        q = q.where(banco.Antibiotico.base_id == base)
    linhas = db.execute(q).scalars().all()
    # Sem filtro de base, a lista traz só as bases que esta pessoa enxerga.
    if not base:
        visiveis = {b.id for b in db.execute(select(banco.BaseDados)).scalars().all()
                    if base_visivel(b, u)}
        linhas = [a for a in linhas if a.base_id in visiveis]
    # O nome da base, para a tela conseguir diferenciar o mesmo antibiótico
    # treinado em bases diferentes — a espécie costuma ser a mesma.
    nomes_de_base = {b.id: b.nome for b in
                     db.execute(select(banco.BaseDados)).scalars().all()}
    saida = []
    for a in linhas:
        m = por_id.get(a.id)
        if not m:
            continue
        saida.append({
            "id": a.id, "nome": a.nome, "nome_base": a.nome_base,
            "base_id": a.base_id, "antibiotico": m["id"],
            "base_nome": nomes_de_base.get(a.base_id, a.base_id),
            "especie": a.especie, "ativo": a.ativo,
            "n_isolados": m["n_total"], "n_resistente": m["n_resistente"],
            "n_sensivel": m["n_sensivel"], "n_features": m["n_features"],
            "modelo": m["modelo_nome"], "modelo_id": m["modelo_id"],
            "modelos": m.get("disponiveis") or [],
            "recomendado": m.get("recomendado"),
            "modelo_padrao": a.modelo_padrao or m.get("recomendado"),
            "usando_recomendado": a.modelo_padrao is None,
            "versao": m["versao"], "limiar": m["limiar"],
            "auc": (m.get("metricas") or {}).get("auc"),
            "sensibilidade": (m.get("metricas") or {}).get("sensibilidade"),
            "especificidade": (m.get("metricas") or {}).get("especificidade"),
            "falsos_negativos": (m.get("metricas") or {}).get("falsos_negativos"),
            "confianca": m["confianca"], "alerta": m.get("alerta"),
            "treinado_em": m["treinado_em"],
            "validacao_cruzada": m.get("validacao_cruzada") or {},
        })
    return saida


@app.get("/api/antibioticos/disponiveis", tags=["equipe"])
def disponiveis(u: Logado, db: Db, base: str | None = None):
    """O que existe na base escolhida e ainda não virou modelo."""
    base_id = base or config.BASE_PADRAO
    linha, df = carregar_base_por_id(db, base_id, u)
    exigir_treino(linha, u)
    encontrados = treino.antibioticos_disponiveis(df)
    ja_tem = {a.id for a in db.execute(
        select(banco.Antibiotico).where(banco.Antibiotico.base_id == base_id)
    ).scalars().all() if modelos.tem_modelo(a.id)}
    for a in encontrados:
        a["nome"] = config.nome_pt(a["nome_base"])
        a["ja_treinado"] = f"{base_id}__{a['id']}" in ja_tem
        a["base_id"] = base_id
    return {"base": linha.publico(), "antibioticos": encontrados}


@app.get("/api/antibioticos/{antibiotico_id}/genes", tags=["base"])
def genes(antibiotico_id: str, u: Logado, db: Db):
    exigir_antibiotico_visivel(db, antibiotico_id, u)
    meta = modelos.metadados(antibiotico_id)
    if meta is None:
        raise HTTPException(404, "Não existe modelo treinado para esse antibiótico.")
    importantes = {i["gene"] for i in (meta.get("importancias") or [])[:6]}
    pesos = meta.get("pesos_explicacao") or {}
    lista = [{"gene": g, "peso": round(float(pesos.get(g, 0.0)), 4),
              "destaque": g in importantes} for g in meta["features"]]
    lista.sort(key=lambda x: (-abs(x["peso"]), x["gene"]))
    return {"antibiotico": antibiotico_id, "n_features": meta["n_features"],
            "genes": lista}


@app.get("/api/modelos", tags=["base"])
def comparacao(u: Logado, db: Db, antibiotico: str | None = None):
    visiveis = {b.id for b in db.execute(select(banco.BaseDados)).scalars().all()
                if base_visivel(b, u)}
    metas = [m for m in modelos.listar_metadados() if m["base_id"] in visiveis]
    if not metas:
        raise HTTPException(503, "Nenhum modelo treinado ainda.")
    meta = next((m for m in metas if m["chave"] == antibiotico), metas[0])
    return {
        "antibiotico": meta["chave"], "base_id": meta["base_id"],
        "nome": config.nome_pt(meta["nome_base"]),
        "especie": meta["especie"], "escolhido": meta["modelo_id"],
        "n_treino": meta["n_treino"], "n_teste": meta["n_teste"],
        "n_clusters": meta["n_clusters"], "limiar": meta["limiar"],
        "confianca": meta["confianca"], "alerta": meta.get("alerta"),
        "comparacao": meta["comparacao"],
        "validacao_cruzada": meta.get("validacao_cruzada") or {},
        "importancias": meta.get("importancias") or [],
    }


@app.post("/api/antibioticos/treinar", tags=["equipe"])
def treinar_novo(entrada: TreinoEntrada, u: Logado, db: Db):
    """Treina um antibiótico novo a partir da base escolhida. Leva alguns segundos."""
    base_linha, df = carregar_base_por_id(db, entrada.base, u)
    base_id = base_linha.id
    exigir_treino(base_linha, u)

    alvo = entrada.antibiotico.strip().lower()
    candidatos = {a["nome_base"]: a for a in treino.antibioticos_disponiveis(df)}
    if alvo not in candidatos:
        raise HTTPException(
            404, f"'{entrada.antibiotico}' não aparece na coluna de antibiograma "
                 f"da base '{base_linha.nome}'.")
    info = candidatos[alvo]
    if not info["treinavel"]:
        raise HTTPException(422, f"Não dá para treinar '{alvo}': {info['motivo']}.")

    try:
        resultado = treino.treinar(alvo, caminho_da_base(base_linha),
                                   modelos.pasta_da_base(base_id),
                                   especie=base_linha.especie,
                                   limiar=entrada.limiar, df=df, base_id=base_id)
    except ValueError as e:
        raise HTTPException(422, str(e))

    modelos.esquecer()
    pasta = modelos.pasta_da_base(base_id)
    arquivos.guardar(pasta / f"{resultado.id}.joblib", pasta / f"{resultado.id}.json")
    chave = f"{base_id}__{resultado.id}"
    meta = modelos.metadados(chave) or {}
    linha = db.get(banco.Antibiotico, chave)
    nome = entrada.nome_exibicao or config.nome_pt(alvo)
    if linha is None:
        db.add(banco.Antibiotico(
            id=chave, base_id=base_id, nome_base=alvo, nome=nome,
            especie=base_linha.especie, ativo=True, criado_por=u.email))
    else:
        linha.nome = nome
        linha.ativo = True
    db.commit()

    if not banco.pode(u, "equipe"):
        m = meta.get("metricas") or {}
        banco.avisar(
            db, "treino",
            f"{u.nome} treinou {nome} na base “{base_linha.nome}”",
            f"Modelo escolhido: {meta.get('modelo_nome')}. "
            f"AUC {m.get('auc'):.3f}. Confiança {meta.get('confianca')}."
            + (f" Alerta: {meta.get('alerta')}" if meta.get("alerta") else ""),
            link="modelos.html", autor=u.email)

    return {"id": chave, "base_id": base_id, "base_nome": base_linha.nome,
            "nome": nome, "modelo": meta.get("modelo_nome"),
            "versao": meta.get("versao"), "n_features": meta.get("n_features"),
            "n_treino": meta.get("n_treino"), "n_teste": meta.get("n_teste"),
            "metricas": meta.get("metricas"), "confianca": meta.get("confianca"),
            "alerta": meta.get("alerta"),
            "validacao_cruzada": meta.get("validacao_cruzada") or {}}


# --------------------------------------------------------------------------- #
# Previsão
# --------------------------------------------------------------------------- #

@app.post("/api/prever", tags=["previsão"])
def prever(entrada: PrevisaoEntrada, u: Logado, db: Db):
    linha = db.get(banco.Antibiotico, entrada.antibiotico)
    if linha is None or not linha.ativo or not modelos.tem_modelo(entrada.antibiotico):
        raise HTTPException(404, "Não existe modelo ativo para esse antibiótico.")
    exigir_antibiotico_visivel(db, entrada.antibiotico, u)
    if not entrada.genes:
        raise HTTPException(400, "Marque pelo menos um gene de resistência.")

    escolhido = entrada.modelo or linha.modelo_padrao
    try:
        resposta = modelos.prever(entrada.antibiotico, entrada.genes, escolhido)
    except KeyError as e:
        raise HTTPException(422, str(e).strip("'"))
    resposta["nome_antibiotico"] = linha.nome
    resposta["aviso"] = (
        "Este resultado não é diagnóstico e não substitui o antibiograma. "
        "O modelo foi treinado com uma única espécie e pode errar, inclusive "
        "prevendo “sensível” para uma bactéria resistente."
    )
    return resposta


# --------------------------------------------------------------------------- #
# Telas
# --------------------------------------------------------------------------- #

@app.get("/", include_in_schema=False)
def raiz():
    return RedirectResponse("/inicio.html")


@app.get("/saude", tags=["base"])
def saude():
    return {"ok": True, "modelos": len(modelos.listar_metadados()),
            "base_disponivel": config.CAMINHO_BASE.exists(),
            "hora": datetime.now(timezone.utc).isoformat(timespec="seconds")}


if config.PASTA_WEB.exists():
    app.mount("/", StaticFiles(directory=config.PASTA_WEB, html=True), name="web")
