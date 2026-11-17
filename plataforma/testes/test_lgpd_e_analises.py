"""Consentimento, histórico de análises, prazos de retenção e o arquivo do
isolado na Nova análise."""

from __future__ import annotations

from datetime import timedelta

from conftest import cab
from test_acesso import _admin, _aprovado

CIPRO = "neisseria-gonorrhoeae__ciprofloxacin"


def _prever(cliente, token, genes=("gyrA_S91F", "parC_S87R")):
    return cliente.post("/api/prever", headers=cab(token),
                        json={"antibiotico": CIPRO, "genes": list(genes)})


def test_cadastro_sem_consentimento_e_recusado(cliente):
    r = cliente.post("/api/cadastro", json={
        "nome": "Sem Aceite", "email": "semaceite@uni.br", "instituicao": "Uni",
        "vinculo": "estudante", "finalidade": "Quero testar a plataforma.",
        "senha": "SenhaBoa123", "termos": True})
    assert r.status_code == 400 and "dados" in r.json()["detail"]
    assert cliente.get("/api/consentimento").json()["versao"]


def test_historico_registra_abre_e_apaga(cliente, supabase):
    s = _aprovado(cliente, supabase, "historico@uni.br")
    tok = s["token"]
    r = _prever(cliente, tok)
    assert r.status_code == 200, r.text
    aid = r.json()["analise_id"]

    lista = cliente.get("/api/eu/analises", headers=cab(tok)).json()
    assert lista["total"] == 1 and lista["retencao_dias"] == 90
    assert lista["analises"][0]["nome_antibiotico"]
    reaberta = cliente.get(f"/api/eu/analises/{aid}", headers=cab(tok)).json()
    assert reaberta["classe"] == r.json()["classe"] and reaberta["feita_em"]

    # Outra pessoa não vê nem apaga.
    outra = _aprovado(cliente, supabase, "bisbilhoteira@uni.br")["token"]
    assert cliente.get(f"/api/eu/analises/{aid}", headers=cab(outra)).status_code == 404
    assert cliente.delete(f"/api/eu/analises/{aid}", headers=cab(outra)).status_code == 404
    assert cliente.get("/api/eu/analises", headers=cab(outra)).json()["total"] == 0

    assert cliente.delete(f"/api/eu/analises/{aid}", headers=cab(tok)).status_code == 204
    _prever(cliente, tok)
    _prever(cliente, tok)
    assert cliente.delete("/api/eu/analises", headers=cab(tok)).json()["apagadas"] == 2


def test_limpeza_apaga_analise_velha_e_conta_desativada_ha_um_ano(cliente, supabase):
    from api import banco
    from api.main import limpar_vencidos

    s = _aprovado(cliente, supabase, "velha@uni.br")
    _prever(cliente, s["token"])
    nova = _aprovado(cliente, supabase, "recente@uni.br")
    _prever(cliente, nova["token"])

    parada = _aprovado(cliente, supabase, "parada@uni.br")
    adm = _admin(cliente)
    cliente.post(f"/api/admin/usuarios/{parada['usuario']['id']}/ativo",
                 headers=cab(adm), json={"ativo": False})
    auth_parada = supabase.por_email("parada@uni.br")["id"]

    with banco.sessao() as db:
        for a in db.query(banco.Analise).filter(
                banco.Analise.usuario_id == s["usuario"]["id"]):
            a.criado_em = banco.agora() - timedelta(days=91)
        u = db.get(banco.Usuario, parada["usuario"]["id"])
        assert u.desativado_em is not None
        u.desativado_em = banco.agora() - timedelta(days=366)
        db.commit()
        feito = limpar_vencidos(db)

    assert feito["analises"] >= 1 and feito["contas"] >= 1
    assert cliente.get("/api/eu/analises", headers=cab(s["token"])).json()["total"] == 0
    assert cliente.get("/api/eu/analises", headers=cab(nova["token"])).json()["total"] == 1
    assert auth_parada not in supabase.contas
    with banco.sessao() as db:
        assert db.get(banco.Usuario, parada["usuario"]["id"]) is None


def test_reativar_limpa_a_data_de_desativacao(cliente, supabase):
    s = _aprovado(cliente, supabase, "volta@uni.br")
    adm = _admin(cliente)
    url = f"/api/admin/usuarios/{s['usuario']['id']}/ativo"
    assert cliente.post(url, headers=cab(adm), json={"ativo": False}).json()["desativado_em"]
    assert cliente.post(url, headers=cab(adm), json={"ativo": True}).json()["desativado_em"] is None


# --------------------------------------------------------------------------- #
# Arquivo do isolado
# --------------------------------------------------------------------------- #

NCBI = (
    "#Organism group,Strain,Isolate,AMR genotypes\n"
    'Neisseria gonorrhoeae,GC1,PDT1,"gyrA_S91F=POINT,parC_S87R=POINT,mtrR=COMPLETE"\n'
    'Neisseria gonorrhoeae,GC2,PDT2,"penA_A311V=POINT"\n'
)
AMRFINDER = (
    "Name\tProtein id\tElement symbol\tElement name\n"
    "amostra1\tNA\tgyrA_S91F\tgyrase\n"
    "amostra1\tNA\tparC_S87R\ttopoisomerase\n"
)


def test_ler_formatos():
    from api import isolado
    r = isolado.ler(NCBI.encode())
    assert r["formato"].startswith("NCBI") and len(r["isolados"]) == 2
    assert r["isolados"][0]["genes"] == ["gyrA_S91F", "mtrR", "parC_S87R"]
    assert r["isolados"][0]["rotulo"] == "GC1 · PDT1"

    r = isolado.ler(AMRFINDER.encode())
    assert r["formato"] == "AMRFinderPlus"
    assert r["isolados"][0]["genes"] == ["gyrA_S91F", "parC_S87R"]

    r = isolado.ler(b"gyrA_S91F, parC_S87R\nmtrR")
    assert r["isolados"][0]["genes"] == ["gyrA_S91F", "mtrR", "parC_S87R"]


def test_ler_arquivo_ruim():
    import pytest
    from api import isolado
    with pytest.raises(isolado.ArquivoInvalido):
        isolado.ler(b"")
    with pytest.raises(isolado.ArquivoInvalido):
        isolado.ler(b"#Organism group,AMR genotypes\nX,\n")


def test_rota_ler_isolado(cliente, supabase):
    tok = _aprovado(cliente, supabase, "arquivo@uni.br")["token"]
    r = cliente.post("/api/isolado/ler", headers=cab(tok),
                     files={"arquivo": ("isolado.csv", NCBI, "text/csv")})
    assert r.status_code == 200 and len(r.json()["isolados"]) == 2
    r = cliente.post("/api/isolado/ler", headers=cab(tok),
                     files={"arquivo": ("x.txt", "!!!", "text/plain")})
    assert r.status_code == 400 and "Não reconheci" in r.json()["detail"]
    assert cliente.post("/api/isolado/ler",
                        files={"arquivo": ("x.csv", NCBI, "text/csv")}).status_code == 401
