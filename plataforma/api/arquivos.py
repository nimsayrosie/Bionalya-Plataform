"""Cópia dos arquivos da plataforma dentro do banco.

Na hospedagem grátis o disco é descartável: a cada reinício somem os CSVs que
as pessoas enviaram (dados/enviadas/) e os modelos que elas treinaram
(modelos/<base>/). O banco Postgres não some. Então todo arquivo que a
plataforma grava também vai para a tabela `arquivos`, e na partida o que
estiver faltando no disco é recriado a partir de lá.

O disco continua sendo o lugar de onde tudo é lido — o resto do código não
precisa saber que este módulo existe, só avisar quando grava ou apaga.

Com SQLite (na sua máquina) isto fica desligado: o disco já é permanente, e
copiar um CSV de 100 MB para dentro do bionalya.db só dobraria o espaço.
Para forçar, BIONALYA_ARQUIVOS_NO_BANCO=1 liga e =0 desliga.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import delete, select

from . import banco, config


def ligado() -> bool:
    escolha = os.getenv("BIONALYA_ARQUIVOS_NO_BANCO", "").strip().lower()
    if escolha in ("1", "true", "sim", "yes"):
        return True
    if escolha in ("0", "false", "nao", "não", "no"):
        return False
    return not banco.SQLITE


def _chave(caminho: Path) -> str:
    """Caminho relativo à raiz do repositório, sempre com '/'."""
    return Path(caminho).resolve().relative_to(config.PROJETO).as_posix()


def guardar(*caminhos: Path) -> None:
    """Copia (ou atualiza) estes arquivos no banco."""
    if not ligado():
        return
    with banco.sessao() as db:
        for caminho in caminhos:
            caminho = Path(caminho)
            if not caminho.is_file():
                continue
            conteudo = caminho.read_bytes()
            chave = _chave(caminho)
            linha = db.get(banco.Arquivo, chave)
            if linha is None:
                db.add(banco.Arquivo(caminho=chave, conteudo=conteudo,
                                     tamanho=len(conteudo)))
            else:
                linha.conteudo = conteudo
                linha.tamanho = len(conteudo)
                linha.atualizado_em = banco.agora()
            db.commit()          # um por vez: não segura 100 MB de vários na memória


def guardar_pasta(pasta: Path) -> None:
    pasta = Path(pasta)
    if pasta.is_dir():
        guardar(*[p for p in sorted(pasta.iterdir()) if p.is_file()])


def apagar(caminho: Path) -> None:
    if not ligado():
        return
    with banco.sessao() as db:
        db.execute(delete(banco.Arquivo)
                   .where(banco.Arquivo.caminho == _chave(caminho)))
        db.commit()


def apagar_pasta(pasta: Path) -> None:
    if not ligado():
        return
    prefixo = _chave(pasta).rstrip("/") + "/"
    with banco.sessao() as db:
        db.execute(delete(banco.Arquivo)
                   .where(banco.Arquivo.caminho.startswith(prefixo, autoescape=True)))
        db.commit()


def restaurar() -> list[str]:
    """Recria no disco o que está no banco e falta (ou difere) no disco.

    Roda na partida, antes de tudo que lê modelos/ e dados/.
    """
    if not ligado():
        return []
    recriados: list[str] = []
    with banco.sessao() as db:
        # Primeiro só os nomes e tamanhos; o conteúdo vem um de cada vez.
        lista = db.execute(select(banco.Arquivo.caminho, banco.Arquivo.tamanho)).all()
        for chave, tamanho in lista:
            destino = config.PROJETO / chave
            if destino.is_file() and destino.stat().st_size == tamanho:
                continue
            conteudo = db.execute(select(banco.Arquivo.conteudo)
                                  .where(banco.Arquivo.caminho == chave)).scalar_one()
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(conteudo)
            recriados.append(chave)
    return recriados
