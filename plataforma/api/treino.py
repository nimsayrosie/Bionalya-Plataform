"""Bionalya — treino dos modelos de previsão de resistência.

Um modelo por antibiótico. O mesmo pipeline do notebook, organizado para poder
ser chamado pela API quando alguém adicionar um antibiótico novo.

Decisões que valem ser lembradas:

* Rótulo: R = resistente (1), S = sensível (0). Isolados marcados I, NS ou ND
  são DESCARTADOS, não agrupados. É a mesma regra do notebook, e é o que faz
  o número bater com o que já foi apresentado.
* Separação treino/teste por CLUSTER GENÉTICO (coluna "SNP cluster"), nunca
  aleatória. Bactérias são clonais: cópias quase idênticas do mesmo isolado
  caindo nos dois lados inflam a AUC para 1,000 sem significar nada.
* O filtro de frequência mínima dos genes é calculado SÓ NO TREINO. Olhar a
  frequência no conjunto todo já é vazamento.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import MultiLabelBinarizer

try:
    from xgboost import XGBClassifier
except ImportError:  # pragma: no cover
    XGBClassifier = None

SEMENTE = 42

# Quanto o conjunto precisa ter para o treino valer alguma coisa.
MIN_TOTAL = 60          # isolados com R ou S
MIN_MINORITARIA = 10    # isolados na classe menos frequente

# Faixas de confiança, pelo tamanho da classe minoritária no conjunto todo.
def _confianca(n_minoritaria: int) -> str:
    if n_minoritaria >= 100:
        return "alta"
    if n_minoritaria >= 30:
        return "media"
    return "baixa"


# --------------------------------------------------------------------------- #
# Leitura da base
# --------------------------------------------------------------------------- #

def _achar_coluna(df: pd.DataFrame, *palavras: str) -> str | None:
    """Acha a coluna pelo conteúdo do nome, porque os cabeçalhos do NCBI vêm
    com espaços, '#' e maiúsculas que mudam entre exportações.

    Quando mais de uma coluna casa, vence a de nome mais curto: procurar por
    "isolate" acha tanto 'Isolate' quanto 'Isolate identifiers', e quem a gente
    quer é a primeira."""
    candidatas = [c for c in df.columns
                  if all(p in c.lower().replace("#", "").strip() for p in palavras)]
    return min(candidatas, key=len) if candidatas else None


def carregar_base(caminho: str | Path) -> pd.DataFrame:
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(
            f"Base não encontrada em {caminho}. Baixe o CSV de isolados em "
            "https://www.ncbi.nlm.nih.gov/pathogens/ e salve nesse caminho."
        )
    with open(caminho, "r", encoding="utf-8", errors="replace") as f:
        cabecalho = f.readline()
    sep = "\t" if cabecalho.count("\t") > cabecalho.count(",") else ","
    return pd.read_csv(caminho, sep=sep, low_memory=False)


# --------------------------------------------------------------------------- #
# Extração de rótulos e de genes
# --------------------------------------------------------------------------- #

_PAR_AST = re.compile(r"^([A-Za-z0-9\-/ ]+?)=([A-Za-z]+)$")


def chave(nome: str) -> str:
    """Normaliza o nome de um antibiótico para usar como identificador."""
    s = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def antibioticos_disponiveis(df: pd.DataFrame) -> list[dict]:
    """Varre a coluna de antibiograma e devolve o que dá para treinar."""
    col = _achar_coluna(df, "ast", "phenotype")
    if col is None:
        raise KeyError("Coluna de antibiograma (AST phenotypes) não encontrada.")

    contagem: dict[str, dict[str, int]] = {}
    for texto in df[col].dropna():
        for par in str(texto).split(","):
            m = _PAR_AST.match(par.strip())
            if not m:
                continue
            ab, fen = m.group(1).strip().lower(), m.group(2).strip().upper()
            contagem.setdefault(ab, {}).setdefault(fen, 0)
            contagem[ab][fen] += 1

    saida = []
    for ab, fens in contagem.items():
        r, s = fens.get("R", 0), fens.get("S", 0)
        menor = min(r, s)
        saida.append({
            "id": chave(ab),
            "nome_base": ab,
            "n_resistente": r,
            "n_sensivel": s,
            "n_util": r + s,
            "n_descartado": sum(v for k, v in fens.items() if k not in ("R", "S")),
            "treinavel": (r + s) >= MIN_TOTAL and menor >= MIN_MINORITARIA,
            "confianca": _confianca(menor),
            "motivo": _motivo(r, s),
        })
    return sorted(saida, key=lambda x: -x["n_util"])


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _motivo(r: int, s: int) -> str | None:
    menor = min(r, s)
    if r + s < MIN_TOTAL:
        return (f"só {_plural(r + s, 'isolado', 'isolados')} com R ou S "
                f"(mínimo {MIN_TOTAL})")
    if menor < MIN_MINORITARIA:
        if r < s:
            falta = _plural(menor, "isolado resistente", "isolados resistentes")
        else:
            falta = _plural(menor, "isolado sensível", "isolados sensíveis")
        return f"só {falta} (mínimo {MIN_MINORITARIA})"
    return None


def _rotulos(df: pd.DataFrame, antibiotico: str) -> pd.Series:
    col = _achar_coluna(df, "ast", "phenotype")
    alvo = antibiotico.lower()

    def ler(texto):
        if not isinstance(texto, str):
            return np.nan
        for par in texto.split(","):
            m = _PAR_AST.match(par.strip())
            if m and m.group(1).strip().lower() == alvo:
                fen = m.group(2).strip().upper()
                if fen == "R":
                    return 1
                if fen == "S":
                    return 0
                return np.nan
        return np.nan

    return df[col].map(ler)


def extrair_genes(texto) -> list[str]:
    """'gyrA_S91F=POINT,mtrR=COMPLETE' -> ['gyrA_S91F', 'mtrR']"""
    if not isinstance(texto, str):
        return []
    genes = []
    for par in texto.split(","):
        par = par.strip()
        if not par:
            continue
        genes.append(par.split("=")[0].strip())
    return sorted(set(g for g in genes if g))


# --------------------------------------------------------------------------- #
# Treino
# --------------------------------------------------------------------------- #

@dataclass
class Resultado:
    id: str
    nome: str
    especie: str
    metricas: dict
    modelos: list = field(default_factory=list)


def _modelos_candidatos(n_pos: int, n_neg: int) -> dict:
    peso = max(1.0, n_neg / max(n_pos, 1))
    cands = {
        "regressao_logistica": (
            "Regressão Logística",
            LogisticRegression(max_iter=3000, class_weight="balanced",
                               random_state=SEMENTE),
        ),
        "random_forest": (
            "Random Forest",
            RandomForestClassifier(n_estimators=400, min_samples_leaf=2,
                                   class_weight="balanced_subsample",
                                   random_state=SEMENTE, n_jobs=-1),
        ),
        "rede_neural": (
            "Redes Neurais",
            MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=3000,
                          early_stopping=True, random_state=SEMENTE),
        ),
    }
    if XGBClassifier is not None:
        cands["xgboost"] = (
            "XGBoost",
            XGBClassifier(n_estimators=400, max_depth=4, learning_rate=0.08,
                          subsample=0.9, colsample_bytree=0.9,
                          scale_pos_weight=peso, eval_metric="logloss",
                          random_state=SEMENTE, n_jobs=-1),
        )
    return cands


def _avaliar(y, p, limiar: float) -> dict:
    pred = (p >= limiar).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "auc": float(roc_auc_score(y, p)) if len(set(y)) > 1 else None,
        "sensibilidade": float(tp / (tp + fn)) if (tp + fn) else None,
        "especificidade": float(tn / (tn + fp)) if (tn + fp) else None,
        "falsos_negativos": int(fn),
        "falsos_positivos": int(fp),
        "verdadeiros_positivos": int(tp),
        "verdadeiros_negativos": int(tn),
    }


def treinar(
    antibiotico: str,
    caminho_csv: str | Path,
    destino: str | Path,
    especie: str = "Neisseria gonorrhoeae",
    limiar: float = 0.5,
    df: pd.DataFrame | None = None,
    base_id: str = "neisseria-gonorrhoeae",
) -> Resultado:
    """Treina os quatro modelos para um antibiótico, escolhe o melhor e salva."""
    if df is None:
        df = carregar_base(caminho_csv)

    col_gen = _achar_coluna(df, "amr", "genotype")
    col_snp = _achar_coluna(df, "snp", "cluster")
    if col_gen is None:
        raise KeyError("Coluna de genótipo (AMR genotypes) não encontrada.")

    y_todos = _rotulos(df, antibiotico)
    usaveis = y_todos.notna() & df[col_gen].notna()
    d = df.loc[usaveis].copy()
    y = y_todos.loc[usaveis].astype(int).to_numpy()

    n_pos, n_neg = int(y.sum()), int((1 - y).sum())
    menor = min(n_pos, n_neg)
    if len(y) < MIN_TOTAL or menor < MIN_MINORITARIA:
        raise ValueError(
            f"'{antibiotico}' não tem dado suficiente: {n_pos} resistentes e "
            f"{n_neg} sensíveis. {_motivo(n_pos, n_neg)}."
        )

    genes = d[col_gen].map(extrair_genes)

    # Clones sem cluster viram cada um o seu próprio grupo, nunca um grupo só.
    if col_snp is not None:
        grupos = d[col_snp].fillna(
            pd.Series("sozinho_" + d.index.astype(str), index=d.index)
        ).astype(str).to_numpy()
    else:
        grupos = np.array([f"sozinho_{i}" for i in d.index])

    # Divisão treino/teste por grupo. O GroupShuffleSplit é o do notebook e é o
    # que mantém os números já apresentados; quando a classe minoritária é tão
    # pequena que o teste sai com uma classe só, cai para o split estratificado
    # por grupo, que distribui as duas classes entre os folds.
    i_tr, i_te = next(
        GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEMENTE)
        .split(genes, y, groups=grupos)
    )
    if len(set(y[i_te])) < 2:
        i_tr, i_te = next(
            StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEMENTE)
            .split(genes, y, groups=grupos)
        )

    # --- features: binarizador ajustado SÓ no treino ---
    # Gene precisa aparecer em pelo menos MIN_OCORRENCIAS isolados de treino.
    # É o mesmo corte do notebook, e é o que dá os 58 genes já apresentados.
    MIN_OCORRENCIAS = 3
    mlb = MultiLabelBinarizer()
    X_tr_full = mlb.fit_transform(genes.iloc[i_tr])
    presenca = X_tr_full.sum(axis=0)
    manter = presenca >= MIN_OCORRENCIAS
    if manter.sum() < 3:                      # base pequena: afrouxa o filtro
        manter = presenca >= 1
    if manter.sum() < 1:
        raise ValueError(f"'{antibiotico}': nenhum gene variou o suficiente.")

    features = [str(g) for g, ok in zip(mlb.classes_, manter) if ok]
    X_tr = X_tr_full[:, manter]
    X_te = mlb.transform(genes.iloc[i_te])[:, manter]
    y_tr, y_te = y[i_tr], y[i_te]

    if len(set(y_te)) < 2:
        raise ValueError(
            f"'{antibiotico}': o conjunto de teste ficou com uma classe só. "
            "A base não tem clusters genéticos variados o bastante."
        )

    # --- treina e avalia os candidatos ---
    resultados = []
    treinados = {}
    for mid, (nome, modelo) in _modelos_candidatos(n_pos, n_neg).items():
        try:
            modelo.fit(X_tr, y_tr)
            p = modelo.predict_proba(X_te)[:, 1]
        except Exception as e:                # um modelo quebrar não derruba os outros
            resultados.append({"id": mid, "nome": nome, "erro": str(e)[:200]})
            continue
        treinados[mid] = modelo
        resultados.append({"id": mid, "nome": nome, **_avaliar(y_te, p, limiar)})

    validos = [r for r in resultados if r.get("auc") is not None]
    if not validos:
        raise ValueError(f"'{antibiotico}': nenhum modelo treinou com sucesso.")

    # Melhor AUC; empate desempatado pela sensibilidade, porque falso negativo
    # (dizer "sensível" para uma bactéria resistente) é o erro mais caro aqui.
    validos.sort(key=lambda r: (round(r["auc"], 4), r["sensibilidade"] or 0),
                 reverse=True)
    escolhido = validos[0]
    modelo_final = treinados[escolhido["id"]]

    # --- validação cruzada, sempre respeitando os clusters ---
    cv = {}
    n_folds = min(5, menor)
    if n_folds >= 2:
        try:
            skf = StratifiedGroupKFold(n_splits=n_folds, shuffle=True,
                                       random_state=SEMENTE)
            X_all = mlb.transform(genes)[:, manter]
            aucs = []
            for a, b in skf.split(X_all, y, groups=grupos):
                if len(set(y[b])) < 2:
                    continue
                m = _modelos_candidatos(n_pos, n_neg)[escolhido["id"]][1]
                m.fit(X_all[a], y[a])
                aucs.append(roc_auc_score(y[b], m.predict_proba(X_all[b])[:, 1]))
            if aucs:
                cv = {"folds": len(aucs), "auc_media": float(np.mean(aucs)),
                      "auc_desvio": float(np.std(aucs))}
        except Exception:
            cv = {}

    # --- explicação gene a gene: coeficientes da regressão logística ---
    # Vale para qualquer modelo servido. É a forma honesta de responder
    # "o que pesou nessa decisão" sem fingir que uma floresta é interpretável.
    explicador = LogisticRegression(max_iter=3000, class_weight="balanced",
                                    random_state=SEMENTE)
    explicador.fit(X_tr, y_tr)
    pesos = {g: float(c) for g, c in zip(features, explicador.coef_[0])}

    def _importancias(modelo):
        if not hasattr(modelo, "feature_importances_"):
            return None
        imp = modelo.feature_importances_
        return sorted(({"gene": g, "peso": float(v)} for g, v in zip(features, imp)),
                      key=lambda x: -x["peso"])[:12]

    importancias = _importancias(modelo_final)
    importancias_por_modelo = {mid: _importancias(m) for mid, m in treinados.items()}

    n_r_teste = int(y_te.sum())
    n_s_teste = int((1 - y_te).sum())
    menor_teste = min(n_r_teste, n_s_teste)
    alerta = None
    if menor_teste < 10:
        lado = "resistentes" if n_r_teste < n_s_teste else "sensíveis"
        alerta = (
            f"O conjunto de teste tem só {menor_teste} isolados {lado}. "
            "Com tão poucos, a AUC oscila muito de uma divisão para outra e "
            "não deve ser lida como medida confiável de desempenho."
        )

    versao = hashlib.sha256(
        f"{antibiotico}|{escolhido['id']}|{len(features)}|{len(y)}|{limiar}"
        .encode()
    ).hexdigest()[:12]

    meta = {
        "id": chave(antibiotico),
        "base_id": base_id,
        "nome_base": antibiotico,
        "especie": especie,
        "modelo_id": escolhido["id"],
        "modelo_nome": escolhido["nome"],
        "recomendado": escolhido["id"],
        "padrao": escolhido["id"],
        "disponiveis": [{"id": r["id"], "nome": r["nome"], "auc": r["auc"],
                         "sensibilidade": r["sensibilidade"],
                         "especificidade": r["especificidade"],
                         "falsos_negativos": r["falsos_negativos"]}
                        for r in validos],
        "versao": versao,
        "limiar": limiar,
        "treinado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "features": features,
        "n_features": len(features),
        "n_total": int(len(y)),
        "n_resistente": n_pos,
        "n_sensivel": n_neg,
        "n_treino": int(len(i_tr)),
        "n_teste": int(len(i_te)),
        "n_clusters": int(len(set(grupos))),
        "confianca": _confianca(menor),
        "alerta": alerta,
        "n_resistente_teste": n_r_teste,
        "n_sensivel_teste": n_s_teste,
        "metricas": {k: v for k, v in escolhido.items() if k not in ("id", "nome")},
        "comparacao": resultados,
        "validacao_cruzada": cv,
        "importancias": importancias,
        "importancias_por_modelo": importancias_por_modelo,
        "pesos_explicacao": pesos,
    }

    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    # Guarda TODOS os modelos que treinaram, não só o vencedor: quem analisa
    # pode querer comparar, e a regressão logística costuma ser preferida
    # quando o que importa é explicar gene a gene.
    joblib.dump(
        {"modelos": treinados, "modelo": modelo_final,
         "padrao": escolhido["id"], "recomendado": escolhido["id"],
         "features": features, "limiar": limiar,
         "versao": versao, "pesos_explicacao": pesos},
        destino / f"{meta['id']}.joblib",
    )
    (destino / f"{meta['id']}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return Resultado(id=meta["id"], nome=antibiotico, especie=especie,
                     metricas=meta["metricas"], modelos=resultados)
