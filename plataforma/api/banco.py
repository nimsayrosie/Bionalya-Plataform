"""Banco da Bionalya — SQLite, via SQLAlchemy.

Três tabelas:
  usuarios      quem pediu acesso, com status e papel
  sessoes       token -> usuário, com validade
  antibioticos  quais aparecem na plataforma e qual o nome em português

O que NÃO está aqui, de propósito: log de previsões. Ele entra depois, junto
com a reescrita do RNF10, porque gravar consulta ligada a usuário é tratamento
de dado pessoal e precisa de base legal e prazo de retenção definidos.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text,
                        create_engine, select)
from sqlalchemy.orm import (DeclarativeBase, Mapped, Session, mapped_column,
                            relationship, sessionmaker)

from . import config

VINCULOS = ("estudante", "pesquisador", "docente", "laboratorio")
STATUS = ("em_analise", "aprovado", "recusado")
# Três níveis, do menor para o maior. Um papel pode tudo que o anterior pode.
#   pesquisador  usa a plataforma: analisa isolados e vê os modelos
#   equipe       + libera cadastros e treina antibióticos
#   admin        + gerencia usuários e papéis
PAPEIS = ("pesquisador", "equipe", "admin")
NIVEL = {"pesquisador": 1, "equipe": 2, "admin": 3}


def pode(usuario, minimo: str) -> bool:
    return NIVEL.get(usuario.papel, 0) >= NIVEL.get(minimo, 99)


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    instituicao: Mapped[str] = mapped_column(String(160))
    vinculo: Mapped[str] = mapped_column(String(32))
    finalidade: Mapped[str] = mapped_column(Text, default="")
    senha_hash: Mapped[str] = mapped_column(String(256))

    papel: Mapped[str] = mapped_column(String(16), default="pesquisador")
    status: Mapped[str] = mapped_column(String(16), default="em_analise")

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    decidido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decidido_por: Mapped[str | None] = mapped_column(String(160), nullable=True)
    motivo_recusa: Mapped[str | None] = mapped_column(Text, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    senha_trocada: Mapped[bool] = mapped_column(Boolean, default=False)

    sessoes: Mapped[list["Sessao"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan")

    def publico(self) -> dict:
        return {
            "id": self.id, "nome": self.nome, "email": self.email,
            "instituicao": self.instituicao, "vinculo": self.vinculo,
            "finalidade": self.finalidade, "papel": self.papel,
            "status": self.status,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
            "decidido_em": self.decidido_em.isoformat() if self.decidido_em else None,
            "decidido_por": self.decidido_por,
            "motivo_recusa": self.motivo_recusa,
            "ativo": self.ativo,
            "senha_trocada": self.senha_trocada,
        }


class Sessao(Base):
    __tablename__ = "sessoes"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    expira_em: Mapped[datetime] = mapped_column(DateTime)

    usuario: Mapped[Usuario] = relationship(back_populates="sessoes")

    @classmethod
    def nova(cls, usuario: Usuario) -> "Sessao":
        return cls(
            token=secrets.token_urlsafe(32),
            usuario_id=usuario.id,
            expira_em=agora() + timedelta(hours=config.HORAS_SESSAO),
        )

    @property
    def valida(self) -> bool:
        exp = self.expira_em
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > agora()


class BaseDados(Base):
    """Um CSV de isolados. Vem de fábrica ou alguém subiu pela plataforma."""
    __tablename__ = "bases"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)   # slug
    nome: Mapped[str] = mapped_column(String(160))
    especie: Mapped[str] = mapped_column(String(120))
    arquivo: Mapped[str] = mapped_column(String(200))               # nome dentro de dados/
    origem: Mapped[str] = mapped_column(String(20), default="upload")  # inicial | upload
    n_isolados: Mapped[int] = mapped_column(Integer, default=0)
    n_com_ast: Mapped[int] = mapped_column(Integer, default=0)
    enviada_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    enviada_por: Mapped[str | None] = mapped_column(String(160), nullable=True)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    def publico(self) -> dict:
        return {
            "id": self.id, "nome": self.nome, "especie": self.especie,
            "arquivo": self.arquivo, "origem": self.origem,
            "n_isolados": self.n_isolados, "n_com_ast": self.n_com_ast,
            "enviada_em": self.enviada_em.isoformat() if self.enviada_em else None,
            "enviada_por": self.enviada_por, "observacao": self.observacao,
        }


class Antibiotico(Base):
    __tablename__ = "antibioticos"

    # id é "<base>__<antibiotico>", porque o mesmo antibiótico pode ter um
    # modelo diferente em cada base.
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    base_id: Mapped[str] = mapped_column(String(80), default=config.BASE_PADRAO)
    nome_base: Mapped[str] = mapped_column(String(64))              # como vem do NCBI
    nome: Mapped[str] = mapped_column(String(80))                   # exibição, em pt
    especie: Mapped[str] = mapped_column(String(120), default=config.ESPECIE_PADRAO)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Qual dos quatro algoritmos responde por padrão. Vazio = o recomendado
    # pelo treino (o de melhor AUC).
    modelo_padrao: Mapped[str | None] = mapped_column(String(40), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    criado_por: Mapped[str | None] = mapped_column(String(160), nullable=True)


motor = create_engine(f"sqlite:///{config.BANCO}", echo=False,
                      connect_args={"check_same_thread": False})
Sessao_db = sessionmaker(bind=motor, expire_on_commit=False)


def criar_tabelas() -> list[str]:
    """Cria o que falta e devolve as colunas acrescentadas a tabelas antigas."""
    Base.metadata.create_all(motor)
    novas = migrar()
    _limpar_antibioticos_antigos()
    return novas


def migrar() -> list[str]:
    """ALTER TABLE ADD COLUMN para cada coluna que o código tem e o arquivo não.

    O `create_all` só sabe criar tabela nova: ele nunca mexe numa que já existe.
    Então, depois de uma atualização, um banco antigo quebra na primeira consulta
    com 'no such column'. Aqui a gente compara as duas listas e acrescenta o que
    falta, sem apagar nada.

    Só dá para ACRESCENTAR coluna, que é o que o SQLite permite. Remover ou mudar
    o tipo de uma pede migração de verdade — se um dia precisar, traga o Alembic.
    """
    from sqlalchemy import text

    acrescentadas: list[str] = []
    with motor.begin() as con:
        for tabela in Base.metadata.sorted_tables:
            existentes = {linha[1] for linha in
                          con.execute(text(f"PRAGMA table_info('{tabela.name}')"))}
            if not existentes:                 # tabela nova: create_all já fez
                continue
            for coluna in tabela.columns:
                if coluna.name in existentes:
                    continue
                tipo = coluna.type.compile(motor.dialect)
                # Entra sempre como NULL: o SQLite recusa ADD COLUMN NOT NULL sem
                # um default constante. O valor certo vai logo abaixo, no UPDATE.
                con.execute(text(
                    f'ALTER TABLE "{tabela.name}" ADD COLUMN "{coluna.name}" {tipo}'))
                padrao = getattr(coluna.default, "arg", None)
                if padrao is not None and not callable(padrao):
                    con.execute(
                        text(f'UPDATE "{tabela.name}" SET "{coluna.name}" = :v '
                             f'WHERE "{coluna.name}" IS NULL'), {"v": padrao})
                acrescentadas.append(f"{tabela.name}.{coluna.name}")
    return acrescentadas


def _limpar_antibioticos_antigos() -> int:
    """Apaga as linhas da época em que o id era só o nome do antibiótico.

    Hoje o id é '<base>__<antibiotico>'. As linhas antigas não casam com nenhum
    arquivo em modelos/<base>/ e só atrapalhariam as listas; o próprio
    `_semear_antibioticos` recria tudo a partir dos modelos em disco.
    """
    from sqlalchemy import text

    with motor.begin() as con:
        r = con.execute(text(
            r"DELETE FROM antibioticos WHERE id NOT LIKE '%\_\_%' ESCAPE '\'"))
        return r.rowcount or 0


def sessao() -> Session:
    return Sessao_db()


def buscar_por_token(db: Session, token: str) -> Usuario | None:
    s = db.get(Sessao, token)
    if s is None or not s.valida:
        return None
    return db.get(Usuario, s.usuario_id)


def contar(db: Session, modelo, **filtros) -> int:
    q = select(modelo)
    for k, v in filtros.items():
        q = q.where(getattr(modelo, k) == v)
    return len(db.execute(q).scalars().all())
