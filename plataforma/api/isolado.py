"""Lê o arquivo de um isolado e devolve os genes de resistência dele.

Serve a tela Nova análise: a pessoa envia o arquivo e os genes já aparecem
marcados, em vez de procurar um por um na lista. Três formatos:

  · CSV ou TSV do NCBI Pathogen Detection (o mesmo das bases): uma ou mais
    linhas de isolado, com a coluna "AMR genotypes"
    ("gyrA_S91F=POINT,mtrR=COMPLETE,...")
  · saída do AMRFinderPlus (TSV), com a coluna "Element symbol" (versão 4)
    ou "Gene symbol" (versões anteriores)
  · uma lista simples de genes, separados por vírgula, ponto e vírgula ou
    quebra de linha

O arquivo é lido em memória e descartado: nada aqui grava em disco nem no
banco. É dado de pesquisa, e pode ter identificação de amostra.
"""

from __future__ import annotations

import csv
import io
import re

from . import config, treino

# Nomes de gene como o NCBI escreve: letras, números, _ - . ( ) e '.
_GENE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-.()'/]{0,60}$")


class ArquivoInvalido(ValueError):
    pass


def _texto(conteudo: bytes) -> str:
    for cod in ("utf-8-sig", "latin-1"):
        try:
            return conteudo.decode(cod)
        except UnicodeDecodeError:
            continue
    raise ArquivoInvalido("Não deu para ler o arquivo como texto.")


def _coluna(cabecalho: list[str], *palavras: str) -> int | None:
    """Índice da coluna cujo nome tem todas as palavras (sem diferenciar caixa)."""
    candidatas = [(len(c), i) for i, c in enumerate(cabecalho)
                  if all(p in c.lower().replace("#", "").strip() for p in palavras)]
    return min(candidatas)[1] if candidatas else None


def ler(conteudo: bytes, nome_arquivo: str = "") -> dict:
    """Devolve {"formato", "isolados": [{"id", "rotulo", "genes"}]}."""
    if len(conteudo) > config.MAX_MB_ISOLADO * 1024 * 1024:
        raise ArquivoInvalido(
            f"O arquivo passa de {config.MAX_MB_ISOLADO} MB. Para um isolado, "
            "envie só a linha dele (ou a saída do AMRFinderPlus).")
    texto = _texto(conteudo).strip()
    if not texto:
        raise ArquivoInvalido("O arquivo está vazio.")

    primeira = texto.splitlines()[0]
    sep = "\t" if primeira.count("\t") > primeira.count(",") else ","
    linhas = list(csv.reader(io.StringIO(texto), delimiter=sep))
    cabecalho = [c.strip() for c in linhas[0]] if linhas else []

    col_ncbi = _coluna(cabecalho, "amr", "genotype")
    if col_ncbi is not None:
        return _ncbi(linhas, cabecalho, col_ncbi)

    col_amrf = _coluna(cabecalho, "element", "symbol")
    if col_amrf is None:
        col_amrf = _coluna(cabecalho, "gene", "symbol")
    if col_amrf is not None:
        return _amrfinder(linhas, cabecalho, col_amrf)

    return _lista(texto)


def _ncbi(linhas, cabecalho, col) -> dict:
    col_isolado = _coluna(cabecalho, "isolate")
    if col_isolado is not None and cabecalho[col_isolado].lower() != "isolate":
        exato = [i for i, c in enumerate(cabecalho) if c.lower() == "isolate"]
        col_isolado = exato[0] if exato else col_isolado
    col_cepa = _coluna(cabecalho, "strain")

    isolados = []
    for n, linha in enumerate(linhas[1:], start=1):
        if len(linha) <= col or not linha[col].strip():
            continue
        genes = treino.extrair_genes(linha[col])
        if not genes:
            continue
        ident = (linha[col_isolado].strip() if col_isolado is not None
                 and len(linha) > col_isolado else "") or f"linha {n}"
        cepa = (linha[col_cepa].strip() if col_cepa is not None
                and len(linha) > col_cepa else "")
        isolados.append({"id": ident, "rotulo": f"{cepa} · {ident}" if cepa else ident,
                         "genes": genes})
        if len(isolados) > config.MAX_ISOLADOS_NO_ARQUIVO:
            raise ArquivoInvalido(
                f"O arquivo tem mais de {config.MAX_ISOLADOS_NO_ARQUIVO} isolados. "
                "Para analisar uma base inteira, envie pela tela Bases de dados.")
    if not isolados:
        raise ArquivoInvalido("Nenhuma linha do arquivo tem genes na coluna "
                              "“AMR genotypes”.")
    return {"formato": "NCBI Pathogen Detection", "isolados": isolados}


def _amrfinder(linhas, cabecalho, col) -> dict:
    col_nome = next((i for i, c in enumerate(cabecalho) if c.lower() == "name"), None)
    por_amostra: dict[str, set[str]] = {}
    for linha in linhas[1:]:
        if len(linha) <= col:
            continue
        gene = linha[col].strip()
        if not _GENE.match(gene):
            continue
        amostra = (linha[col_nome].strip() if col_nome is not None
                   and len(linha) > col_nome else "") or "isolado"
        por_amostra.setdefault(amostra, set()).add(gene)
    if not por_amostra:
        raise ArquivoInvalido("A saída do AMRFinderPlus não tem nenhum gene.")
    isolados = [{"id": a, "rotulo": a, "genes": sorted(g)}
                for a, g in por_amostra.items()]
    return {"formato": "AMRFinderPlus", "isolados": isolados[:config.MAX_ISOLADOS_NO_ARQUIVO]}


def _lista(texto: str) -> dict:
    pedacos = re.split(r"[,;\n\r\t]+", texto)
    genes = sorted({p.strip().split("=")[0].strip() for p in pedacos
                    if _GENE.match(p.strip().split("=")[0].strip())})
    if not genes:
        raise ArquivoInvalido(
            "Não reconheci o arquivo. Envie o CSV do NCBI Pathogen Detection, a "
            "saída do AMRFinderPlus ou uma lista de genes separados por vírgula.")
    return {"formato": "lista de genes",
            "isolados": [{"id": "isolado", "rotulo": "isolado", "genes": genes}]}
