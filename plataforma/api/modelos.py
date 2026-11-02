"""Carrega os modelos treinados e faz a previsão.

Um .joblib e um .json por antibiótico, na pasta modelos/. O .json é o que a
plataforma lê para montar telas; o .joblib é o que responde a previsão.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import joblib
import numpy as np

from . import config

_cache: dict[str, dict] = {}
_trava = threading.Lock()


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #

def partir(chave_completa: str) -> tuple[str, str]:
    """'neisseria-gonorrhoeae__ciprofloxacin' -> (base, antibiotico)"""
    if "__" in chave_completa:
        base, ab = chave_completa.split("__", 1)
        return base, ab
    return config.BASE_PADRAO, chave_completa


def caminho_modelo(chave_completa: str, extensao: str) -> Path:
    base, ab = partir(chave_completa)
    return config.PASTA_MODELOS / base / f"{ab}.{extensao}"


def pasta_da_base(base_id: str) -> Path:
    return config.PASTA_MODELOS / base_id


def metadados(antibiotico_id: str) -> dict | None:
    caminho = caminho_modelo(antibiotico_id, "json")
    if not caminho.exists():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def listar_metadados(base_id: str | None = None) -> list[dict]:
    if not config.PASTA_MODELOS.exists():
        return []
    pastas = ([config.PASTA_MODELOS / base_id] if base_id
              else [p for p in config.PASTA_MODELOS.iterdir() if p.is_dir()])
    metas = []
    for pasta in pastas:
        if not pasta.exists():
            continue
        for p in sorted(pasta.glob("*.json")):
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
                m.setdefault("base_id", pasta.name)
                m["chave"] = f"{m['base_id']}__{m['id']}"
                metas.append(m)
            except Exception:
                continue
    return sorted(metas, key=lambda m: -m.get("n_total", 0))


def tem_modelo(antibiotico_id: str) -> bool:
    return caminho_modelo(antibiotico_id, "joblib").exists()


def apagar_base(base_id: str) -> int:
    """Remove os modelos de uma base inteira. Devolve quantos arquivos saíram."""
    pasta = pasta_da_base(base_id)
    if not pasta.exists():
        return 0
    n = 0
    for arq in list(pasta.iterdir()):
        arq.unlink()
        n += 1
    pasta.rmdir()
    esquecer()
    return n


def carregar(antibiotico_id: str) -> dict:
    """Carrega o .joblib uma vez só e guarda em memória."""
    caminho = caminho_modelo(antibiotico_id, "joblib")
    if not caminho.exists():
        raise FileNotFoundError(
            f"Não existe modelo treinado para '{antibiotico_id}'.")
    chave = f"{antibiotico_id}:{caminho.stat().st_mtime_ns}"
    with _trava:
        if chave not in _cache:
            _cache.clear()                   # modelo retreinado: descarta o antigo
            _cache[chave] = joblib.load(caminho)
        return _cache[chave]


def esquecer(antibiotico_id: str | None = None) -> None:
    with _trava:
        _cache.clear()


def genes_conhecidos(antibiotico_id: str) -> list[str]:
    meta = metadados(antibiotico_id)
    return list(meta["features"]) if meta else []


# --------------------------------------------------------------------------- #
# Previsão
# --------------------------------------------------------------------------- #

def modelos_disponiveis(antibiotico_id: str) -> list[dict]:
    meta = metadados(antibiotico_id) or {}
    return meta.get("disponiveis") or []


def prever(antibiotico_id: str, genes: list[str],
           modelo_id: str | None = None) -> dict:
    pacote = carregar(antibiotico_id)
    meta = metadados(antibiotico_id) or {}

    treinados = pacote.get("modelos") or {}
    escolhido = modelo_id or pacote.get("padrao") or meta.get("modelo_id")
    if modelo_id and modelo_id not in treinados:
        raise KeyError(
            f"'{modelo_id}' não é um dos modelos treinados para este antibiótico.")
    estimador = treinados.get(escolhido) or pacote["modelo"]

    ficha = next((d for d in (meta.get("disponiveis") or [])
                  if d["id"] == escolhido), None) or {}

    features: list[str] = pacote["features"]
    limiar: float = float(pacote.get("limiar", 0.5))
    pesos: dict = pacote.get("pesos_explicacao", {})

    enviados = [g.strip() for g in genes if str(g).strip()]
    conjunto = set(enviados)
    reconhecidos = [g for g in enviados if g in features]
    ignorados = [g for g in enviados if g not in features]

    x = np.array([[1 if f in conjunto else 0 for f in features]])
    prob = float(estimador.predict_proba(x)[0, 1])
    classe = "resistente" if prob >= limiar else "sensivel"

    # Contribuição gene a gene: coeficiente da regressão logística ajustada no
    # mesmo treino. Positivo empurra para resistente, negativo para sensível.
    # Só os genes presentes entram — ausência não contribui.
    contribuicoes = sorted(
        ({"gene": g, "peso": round(float(pesos.get(g, 0.0)), 4)}
         for g in reconhecidos),
        key=lambda c: -abs(c["peso"]),
    )[:12]

    return {
        "antibiotico": antibiotico_id,
        "especie": meta.get("especie", config.ESPECIE_PADRAO),
        "classe": classe,
        "probabilidade": round(prob, 4),
        "limiar": limiar,
        "genes_reconhecidos": reconhecidos,
        "genes_ignorados": ignorados,
        "contribuicoes": contribuicoes,
        "explicacao_por": "regressão logística ajustada no mesmo conjunto de treino",
        "modelo": {
            "id": escolhido,
            "nome": ficha.get("nome") or meta.get("modelo_nome"),
            "versao": meta.get("versao"),
            "auc": ficha.get("auc"),
            "sensibilidade": ficha.get("sensibilidade"),
            "especificidade": ficha.get("especificidade"),
            "n_treino": meta.get("n_treino"),
            "n_features": meta.get("n_features"),
            "confianca": meta.get("confianca"),
            "alerta": meta.get("alerta"),
            "recomendado": meta.get("recomendado"),
            "era_recomendado": escolhido == meta.get("recomendado"),
        },
    }
