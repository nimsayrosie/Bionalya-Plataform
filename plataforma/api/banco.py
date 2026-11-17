"""Banco da Bionalya, via SQLAlchemy.

Na hospedagem é o PostgreSQL do Supabase (variável DATABASE_URL), porque o
disco do plano grátis do Render é descartável e o SQLite sumiria a cada
reinício. Na sua máquina, sem a variável, continua sendo o arquivo bionalya.db.

Tabelas:
  usuarios      quem pediu acesso, com status e papel. E-mail e senha ficam no
                Supabase Auth; a ligação é a coluna auth_id
  bases         os CSVs de isolados
  antibioticos  quais aparecem na plataforma e qual o nome em português
  notificacoes  avisos para a equipe
  arquivos      cópia dos CSVs e modelos, para sobreviverem ao reinício

O que NÃO está aqui, de propósito: log de previsões. Ele entra depois, junto
com a reescrita do RNF10, porque gravar consulta ligada a usuário é tratamento
de dado pessoal e precisa de base legal e prazo de retenção definidos.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, Integer, LargeBinary,
                        String, Text,
                        create_engine, select)
from sqlalchemy.orm import (DeclarativeBase, Mapped, Session, mapped_column,
                            sessionmaker)

from . import config

VINCULOS = ("estudante", "pesquisador", "docente", "laboratorio")
STATUS = ("em_analise", "aprovado", "recusado")
# Três níveis, do menor para o maior. Um papel pode tudo que o anterior pode.
#   pesquisador  usa a plataforma: analisa isolados e vê os modelos
#   equipe       + libera cadastros e treina antibióticos
#   admin        + gerencia usuários e papéis
PAPEIS = ("pesquisador", "equipe", "admin")
NIVEL = {"pesquisador": 1, "equipe": 2, "admin": 3}
# Situação de uma base enviada pela plataforma.
SITUACOES_BASE = ("em_analise", "aprovada", "recusada")


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
    # O id da conta no Supabase Auth (o "sub" do token). Vazio só enquanto a
    # conta não foi ligada, o que a API resolve no primeiro login.
    auth_id: Mapped[str | None] = mapped_column(String(64), unique=True,
                                                index=True, nullable=True)
    email_confirmado: Mapped[bool] = mapped_column(Boolean, default=False)

    papel: Mapped[str] = mapped_column(String(16), default="pesquisador")
    status: Mapped[str] = mapped_column(String(16), default="em_analise")

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    decidido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decidido_por: Mapped[str | None] = mapped_column(String(160), nullable=True)
    motivo_recusa: Mapped[str | None] = mapped_column(Text, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    # False quando a senha foi sorteada (pelo admin ou na partida): a tela
    # Minha conta pede para trocar.
    senha_trocada: Mapped[bool] = mapped_column(Boolean, default=False)

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
            "email_confirmado": self.email_confirmado,
        }


class BaseDados(Base):
    """Um CSV de isolados. Vem de fábrica ou alguém subiu pela plataforma.

    Quem envia a base pode usá-la na hora, treinar os modelos dela e remover
    quando quiser — não há fila de aprovação. A equipe recebe um aviso
    (ver Notificacao) e pode remover depois, se for o caso.
    """
    __tablename__ = "bases"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)   # slug
    nome: Mapped[str] = mapped_column(String(160))
    especie: Mapped[str] = mapped_column(String(120))
    arquivo: Mapped[str] = mapped_column(String(200))               # nome dentro de dados/
    origem: Mapped[str] = mapped_column(String(20), default="upload")  # inicial | upload
    n_isolados: Mapped[int] = mapped_column(Integer, default=0)
    n_com_ast: Mapped[int] = mapped_column(Integer, default=0)
    enviada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    enviada_por: Mapped[str | None] = mapped_column(String(160), nullable=True)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Hoje toda base entra como "aprovada". A coluna continua existindo porque
    # bancos de versões anteriores têm linhas em "em_analise", que a partida
    # promove, e porque uma eventual volta da moderação não precisaria de
    # migração de esquema.
    situacao: Mapped[str] = mapped_column(String(16), default="aprovada")
    decidida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decidida_por: Mapped[str | None] = mapped_column(String(160), nullable=True)
    motivo_recusa: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Quem envia declara que pode usar aquele dado e que não há informação
    # identificável de paciente ali. Guardamos a versão do texto aceito, não só
    # um "sim": se o termo mudar, dá para saber o que a pessoa leu.
    termo_aceito: Mapped[bool] = mapped_column(Boolean, default=True)
    termo_versao: Mapped[str | None] = mapped_column(String(20), nullable=True)

    def publico(self) -> dict:
        return {
            "id": self.id, "nome": self.nome, "especie": self.especie,
            "arquivo": self.arquivo, "origem": self.origem,
            "n_isolados": self.n_isolados, "n_com_ast": self.n_com_ast,
            "enviada_em": self.enviada_em.isoformat() if self.enviada_em else None,
            "enviada_por": self.enviada_por, "observacao": self.observacao,
            "situacao": self.situacao,
            "decidida_em": self.decidida_em.isoformat() if self.decidida_em else None,
            "decidida_por": self.decidida_por,
            "motivo_recusa": self.motivo_recusa,
            "termo_aceito": self.termo_aceito, "termo_versao": self.termo_versao,
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
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    criado_por: Mapped[str | None] = mapped_column(String(160), nullable=True)


class Notificacao(Base):
    """Aviso para a equipe sobre o que os pesquisadores fizeram sozinhos.

    Importar base e treinar modelo não passam mais por aprovação; em vez de
    segurar o trabalho da pessoa, a plataforma avisa quem acompanha. O aviso é
    coletivo: qualquer pessoa da equipe lê e marca como lido para todas.
    """
    __tablename__ = "notificacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(32))        # base_nova | treino
    titulo: Mapped[str] = mapped_column(String(200))
    texto: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(200), nullable=True)
    autor: Mapped[str | None] = mapped_column(String(160), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    lida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lida_por: Mapped[str | None] = mapped_column(String(160), nullable=True)

    def publico(self) -> dict:
        return {
            "id": self.id, "tipo": self.tipo, "titulo": self.titulo,
            "texto": self.texto, "link": self.link, "autor": self.autor,
            "criada_em": self.criada_em.isoformat() if self.criada_em else None,
            "lida": self.lida_em is not None,
            "lida_por": self.lida_por,
        }


class Arquivo(Base):
    """Cópia de um arquivo do disco (CSV enviado, modelo treinado).

    Existe para a hospedagem, onde o disco some a cada reinício e o banco não.
    Quem cuida dela é o módulo arquivos.py.
    """
    __tablename__ = "arquivos"

    # Relativo à raiz do repositório: "dados/enviadas/x.csv",
    # "plataforma/modelos/<base>/<antibiotico>.joblib".
    caminho: Mapped[str] = mapped_column(String(400), primary_key=True)
    # deferred: listar os arquivos não traz os bytes junto.
    conteudo: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    tamanho: Mapped[int] = mapped_column(Integer, default=0)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


def avisar(db: Session, tipo: str, titulo: str, texto: str = "",
           link: str | None = None, autor: str | None = None) -> Notificacao:
    """Registra um aviso para a equipe. Não falha a operação que o gerou."""
    n = Notificacao(tipo=tipo, titulo=titulo, texto=texto, link=link, autor=autor)
    db.add(n)
    db.commit()
    return n


def _criar_motor():
    url = config.url_banco()
    if url.startswith("sqlite"):
        return create_engine(url, echo=False,
                             connect_args={"check_same_thread": False})
    # pool_pre_ping: o Postgres do plano grátis derruba conexão parada, e sem
    # isso a primeira consulta depois de um tempo quieto quebra.
    # Pool pequeno: o pooler do Supabase grátis aceita poucas conexões, e uma
    # instância do Render nunca precisa de mais que isso.
    return create_engine(url, echo=False, pool_pre_ping=True, pool_recycle=300,
                         pool_size=3, max_overflow=4, pool_timeout=20)


motor = _criar_motor()
SQLITE = motor.dialect.name == "sqlite"
Sessao_db = sessionmaker(bind=motor, expire_on_commit=False)


def criar_tabelas() -> list[str]:
    """Cria o que falta e devolve as colunas acrescentadas a tabelas antigas."""
    _descartar_login_antigo()
    Base.metadata.create_all(motor)
    novas = migrar()
    _limpar_antibioticos_antigos()
    _fechar_api_rest_do_supabase()
    return novas


def _descartar_login_antigo() -> None:
    """Banco da época em que a senha ficava aqui: recria usuarios do zero.

    Antes do Supabase, usuarios tinha senha_hash (NOT NULL) e havia a tabela
    sessoes. Não dá para levar essas contas: o Supabase não importa hash
    PBKDF2. Como a troca foi feita antes de alguém se cadastrar de verdade,
    a saída é apagar as duas tabelas; o admin e a demonstração são recriados
    na partida. Bases, modelos e avisos ficam intactos.
    """
    from sqlalchemy import inspect, text

    inspetor = inspect(motor)
    if not inspetor.has_table("usuarios"):
        return
    colunas = {c["name"] for c in inspetor.get_columns("usuarios")}
    if "senha_hash" not in colunas:
        return
    with motor.begin() as con:
        con.execute(text('DROP TABLE IF EXISTS "sessoes"'))
        con.execute(text('DROP TABLE "usuarios"'))
    print("Login antigo descartado: as contas passam a ficar no Supabase.")


def _fechar_api_rest_do_supabase() -> None:
    """Liga o RLS em todas as tabelas, sem nenhuma política.

    O Supabase publica toda tabela do schema public numa API REST, e a chave
    que abre essa API (anon) é pública por definição. Sem RLS, qualquer um com
    ela leria a tabela usuarios. Com RLS ligado e nenhuma política, a API REST
    não vê nada; a nossa API continua lendo tudo, porque conecta como o dono
    das tabelas, que não passa pelo RLS. Fora do Postgres não faz nada.
    """
    if SQLITE:
        return
    from sqlalchemy import text

    with motor.begin() as con:
        for tabela in Base.metadata.sorted_tables:
            con.execute(text(f'ALTER TABLE "{tabela.name}" ENABLE ROW LEVEL SECURITY'))


def migrar() -> list[str]:
    """ALTER TABLE ADD COLUMN para cada coluna que o código tem e o arquivo não.

    O `create_all` só sabe criar tabela nova: ele nunca mexe numa que já existe.
    Então, depois de uma atualização, um banco antigo quebra na primeira consulta
    com 'no such column'. Aqui a gente compara as duas listas e acrescenta o que
    falta, sem apagar nada.

    Só dá para ACRESCENTAR coluna, que é o que o SQLite permite. Remover ou mudar
    o tipo de uma pede migração de verdade — se um dia precisar, traga o Alembic.
    """
    from sqlalchemy import inspect, text

    acrescentadas: list[str] = []
    with motor.begin() as con:
        # inspect em vez de PRAGMA table_info: funciona no SQLite e no Postgres.
        inspetor = inspect(con)
        for tabela in Base.metadata.sorted_tables:
            if not inspetor.has_table(tabela.name):   # create_all já criou
                continue
            existentes = {c["name"] for c in inspetor.get_columns(tabela.name)}
            if not existentes:
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


def usuario_por_email(db: Session, email: str) -> Usuario | None:
    return db.execute(select(Usuario).where(Usuario.email == (email or "").strip().lower())
                      ).scalars().first()


def usuario_por_auth(db: Session, auth_id: str) -> Usuario | None:
    return db.execute(select(Usuario).where(Usuario.auth_id == auth_id)).scalars().first()


def contar(db: Session, modelo, **filtros) -> int:
    q = select(modelo)
    for k, v in filtros.items():
        q = q.where(getattr(modelo, k) == v)
    return len(db.execute(q).scalars().all())
