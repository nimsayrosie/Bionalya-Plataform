"""Fluxo de acesso: cadastro, confirmação, aprovação, login e senha nova.

Rodar, da pasta plataforma/:   python -m pytest testes
"""

from __future__ import annotations

from conftest import cab


def _entrar(cliente, email, senha):
    return cliente.post("/api/sessao", json={"email": email, "senha": senha})


def _admin(cliente):
    r = _entrar(cliente, "admin@teste.br", "SenhaAdmin123")
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _cadastrar(cliente, email, senha="SenhaBoa123"):
    return cliente.post("/api/cadastro", json={
        "nome": "Pessoa de Teste", "email": email, "instituicao": "UniTeste",
        "vinculo": "estudante", "finalidade": "Testar a plataforma inteira.",
        "senha": senha, "termos": True})


def _ultimo_link(supabase, email, tipo):
    return next(e for e in reversed(supabase.emails)
                if e["para"] == email and e["tipo"] == tipo)["token_hash"]


def _aprovado(cliente, supabase, email, senha="SenhaBoa123"):
    """Cadastra, confirma o e-mail e aprova. Devolve a sessão da pessoa."""
    assert _cadastrar(cliente, email, senha).status_code == 201
    cliente.post("/api/confirmar-email",
                 json={"token_hash": _ultimo_link(supabase, email, "email")})
    adm = _admin(cliente)
    pedido = next(s for s in cliente.get("/api/equipe/solicitacoes",
                                         headers=cab(adm)).json()["solicitacoes"]
                  if s["email"] == email)
    cliente.post(f"/api/equipe/solicitacoes/{pedido['id']}/decidir",
                 json={"aprovar": True}, headers=cab(adm))
    r = _entrar(cliente, email, senha)
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- #

def test_admin_criado_na_partida(cliente, supabase):
    assert supabase.por_email("admin@teste.br")["confirmado"]
    r = _entrar(cliente, "admin@teste.br", "SenhaAdmin123")
    assert r.status_code == 200
    assert r.json()["usuario"]["papel"] == "admin"
    assert r.json()["refresh_token"]


def test_saude_mostra_banco_e_login(cliente):
    d = cliente.get("/saude").json()
    assert d["banco"] is True and d["login"] is True


def test_cadastro_completo(cliente, supabase, correio_enviado):
    email = "nova@uni.br"
    r = _cadastrar(cliente, email)
    assert r.status_code == 201
    assert r.json()["email_confirmado"] is False
    assert _ultimo_link(supabase, email, "email")

    # Antes de confirmar, o Supabase não deixa entrar.
    r = _entrar(cliente, email, "SenhaBoa123")
    assert r.status_code == 403 and "Confirme" in r.json()["detail"]

    # Confirmou, mas a equipe ainda não liberou.
    r = cliente.post("/api/confirmar-email",
                     json={"token_hash": _ultimo_link(supabase, email, "email")})
    assert r.status_code == 200
    assert r.json() == {"confirmado": True, "entrou": False, "status": "em_analise"}
    r = _entrar(cliente, email, "SenhaBoa123")
    assert r.status_code == 403 and "análise" in r.json()["detail"]

    # A equipe vê o pedido, com o e-mail confirmado, e libera.
    adm = _admin(cliente)
    pedidos = cliente.get("/api/equipe/solicitacoes", headers=cab(adm)).json()
    pedido = next(s for s in pedidos["solicitacoes"] if s["email"] == email)
    assert pedido["email_confirmado"] is True
    r = cliente.post(f"/api/equipe/solicitacoes/{pedido['id']}/decidir",
                     json={"aprovar": True}, headers=cab(adm))
    assert r.status_code == 200
    assert any(e["para"] == email and "liberado" in e["assunto"] for e in correio_enviado)

    r = _entrar(cliente, email, "SenhaBoa123")
    assert r.status_code == 200
    assert cliente.get("/api/eu", headers=cab(r.json()["token"])).json()["email"] == email


def test_cadastro_repetido(cliente):
    assert _cadastrar(cliente, "repetido@uni.br").status_code == 201
    assert _cadastrar(cliente, "repetido@uni.br").status_code == 409


def test_link_de_confirmacao_usado_duas_vezes(cliente, supabase):
    _cadastrar(cliente, "duas@uni.br")
    h = _ultimo_link(supabase, "duas@uni.br", "email")
    assert cliente.post("/api/confirmar-email", json={"token_hash": h}).status_code == 200
    r = cliente.post("/api/confirmar-email", json={"token_hash": h})
    assert r.status_code == 403 and "expirou" in r.json()["detail"]


def test_recusa_manda_email_com_motivo(cliente, supabase, correio_enviado):
    _cadastrar(cliente, "recusar@uni.br")
    adm = _admin(cliente)
    pedido = next(s for s in cliente.get("/api/equipe/solicitacoes",
                                         headers=cab(adm)).json()["solicitacoes"]
                  if s["email"] == "recusar@uni.br")
    cliente.post(f"/api/equipe/solicitacoes/{pedido['id']}/decidir",
                 json={"aprovar": False, "motivo": "Sem vínculo informado"},
                 headers=cab(adm))
    e = next(e for e in correio_enviado if e["para"] == "recusar@uni.br")
    assert "Sem vínculo informado" in e["texto"]


def test_token_invalido(cliente):
    assert cliente.get("/api/eu", headers=cab("lixo")).status_code == 401
    assert cliente.get("/api/eu").status_code == 401


def test_senha_errada_e_email_inexistente_respondem_igual(cliente):
    a = _entrar(cliente, "admin@teste.br", "errada123")
    b = _entrar(cliente, "ninguem@uni.br", "errada123")
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_renovar_sessao(cliente, supabase):
    s = _aprovado(cliente, supabase, "renova@uni.br")
    r = cliente.post("/api/sessao/renovar", json={"refresh_token": s["refresh_token"]})
    assert r.status_code == 200
    novo = r.json()
    assert novo["token"] != s["token"]
    assert cliente.get("/api/eu", headers=cab(novo["token"])).status_code == 200
    # refresh_token é de uso único
    r = cliente.post("/api/sessao/renovar", json={"refresh_token": s["refresh_token"]})
    assert r.status_code == 401


def test_desativar_corta_na_hora(cliente, supabase):
    s = _aprovado(cliente, supabase, "desativa@uni.br")
    adm = _admin(cliente)
    uid = s["usuario"]["id"]
    cliente.post(f"/api/admin/usuarios/{uid}/ativo", json={"ativo": False}, headers=cab(adm))
    assert cliente.get("/api/eu", headers=cab(s["token"])).status_code == 403
    r = cliente.post("/api/sessao/renovar", json={"refresh_token": s["refresh_token"]})
    assert r.status_code == 403


def test_recuperar_senha_pelo_link(cliente, supabase):
    email = "esqueceu@uni.br"
    antiga = _aprovado(cliente, supabase, email)
    r = cliente.post("/api/recuperar-senha", json={"email": email})
    assert r.status_code == 200
    h = _ultimo_link(supabase, email, "recovery")

    r = cliente.post("/api/redefinir-senha", json={"senha": "OutraSenha456", "token_hash": h})
    assert r.status_code == 200, r.text
    assert r.json()["entrou"] is True and r.json()["token"]

    assert _entrar(cliente, email, "SenhaBoa123").status_code == 401
    assert _entrar(cliente, email, "OutraSenha456").status_code == 200
    # A sessão aberta antes da troca caiu.
    r = cliente.post("/api/sessao/renovar", json={"refresh_token": antiga["refresh_token"]})
    assert r.status_code == 401
    # O link não serve duas vezes.
    r = cliente.post("/api/redefinir-senha", json={"senha": "Terceira789", "token_hash": h})
    assert r.status_code == 403


def test_recuperar_email_inexistente_nao_manda_nada(cliente, supabase):
    antes = len(supabase.emails)
    r = cliente.post("/api/recuperar-senha", json={"email": "fantasma@uni.br"})
    assert r.status_code == 200
    assert len(supabase.emails) == antes


def test_recuperar_com_email_fora_do_ar_avisa_a_equipe(cliente, supabase):
    _aprovado(cliente, supabase, "semsmtp@uni.br")
    supabase.falhar_recover = True
    try:
        r = cliente.post("/api/recuperar-senha", json={"email": "semsmtp@uni.br"})
    finally:
        supabase.falhar_recover = False
    assert r.status_code == 200
    avisos = cliente.get("/api/notificacoes", headers=cab(_admin(cliente))).json()
    assert any(a["tipo"] == "senha" and a["autor"] == "semsmtp@uni.br"
               for a in avisos["avisos"])


def test_trocar_senha_logado(cliente, supabase):
    email = "troca@uni.br"
    s = _aprovado(cliente, supabase, email)
    r = cliente.post("/api/eu/senha", headers=cab(s["token"]),
                     json={"senha_atual": "errada000", "senha_nova": "NovaSenha789"})
    assert r.status_code == 400
    r = cliente.post("/api/eu/senha", headers=cab(s["token"]),
                     json={"senha_atual": "SenhaBoa123", "senha_nova": "NovaSenha789"})
    assert r.status_code == 200, r.text
    nova = r.json()
    assert cliente.get("/api/eu", headers=cab(nova["token"])).status_code == 200
    # A sessão de antes caiu; a nova, que veio na resposta, vale.
    r = cliente.post("/api/sessao/renovar", json={"refresh_token": s["refresh_token"]})
    assert r.status_code == 401
    assert _entrar(cliente, email, "NovaSenha789").status_code == 200


def test_admin_cria_conta_e_gera_senha(cliente, supabase, correio_enviado):
    adm = _admin(cliente)
    r = cliente.post("/api/admin/usuarios", headers=cab(adm),
                     json={"nome": "Banca Avaliadora", "email": "banca@uni.br"})
    assert r.status_code == 201, r.text
    senha = r.json()["senha"]
    r_login = _entrar(cliente, "banca@uni.br", senha)
    assert r_login.status_code == 200
    assert r_login.json()["usuario"]["senha_trocada"] is False   # troca no 1º acesso
    assert any(e["para"] == "banca@uni.br" for e in correio_enviado)

    uid = r.json()["usuario"]["id"]
    r = cliente.post(f"/api/admin/usuarios/{uid}/senha", headers=cab(adm), json={})
    assert r.status_code == 200
    assert _entrar(cliente, "banca@uni.br", senha).status_code == 401
    assert _entrar(cliente, "banca@uni.br", r.json()["senha"]).status_code == 200


def test_senha_do_admin_obriga_troca_no_login(cliente, supabase):
    """Senha que o admin gerou: entra, mas só faz alguma coisa depois de trocar."""
    s = _aprovado(cliente, supabase, "obrigada@uni.br")
    adm = _admin(cliente)
    r = cliente.post(f"/api/admin/usuarios/{s['usuario']['id']}/senha",
                     headers=cab(adm), json={})
    gerada = r.json()["senha"]

    r = _entrar(cliente, "obrigada@uni.br", gerada)
    assert r.status_code == 200
    assert r.json()["usuario"]["senha_trocada"] is False
    tok = r.json()["token"]

    # /api/eu responde (a tela precisa dele para abrir o pop-up), o resto não.
    assert cliente.get("/api/eu", headers=cab(tok)).status_code == 200
    r = cliente.get("/api/modelos", headers=cab(tok))
    assert r.status_code == 403 and "Troque a senha" in r.json()["detail"]

    r = cliente.post("/api/eu/senha", headers=cab(tok),
                     json={"senha_atual": gerada, "senha_nova": "MinhaSenha321"})
    assert r.status_code == 200
    novo = r.json()["token"]
    assert r.json()["usuario"]["senha_trocada"] is True
    assert cliente.get("/api/modelos", headers=cab(novo)).status_code == 200


def test_senha_pelo_link_do_email_nao_obriga_troca(cliente, supabase):
    s = _aprovado(cliente, supabase, "link@uni.br")
    adm = _admin(cliente)
    cliente.post(f"/api/admin/usuarios/{s['usuario']['id']}/senha", headers=cab(adm), json={})
    cliente.post("/api/recuperar-senha", json={"email": "link@uni.br"})
    r = cliente.post("/api/redefinir-senha", json={
        "senha": "EscolhiEu123", "token_hash": _ultimo_link(supabase, "link@uni.br", "recovery")})
    assert r.json()["usuario"]["senha_trocada"] is True
    assert cliente.get("/api/modelos", headers=cab(r.json()["token"])).status_code == 200


def test_quem_nao_e_equipe_nao_aprova(cliente, supabase):
    s = _aprovado(cliente, supabase, "comum@uni.br")
    r = cliente.get("/api/equipe/solicitacoes", headers=cab(s["token"]))
    assert r.status_code == 403


def test_conta_criada_direto_no_supabase_entra_em_analise(cliente, supabase):
    """Quem se cadastrar pela API do Supabase, pulando a nossa, não entra:
    vira pedido em análise na primeira tentativa de login."""
    supabase.nova_conta("pulou@uni.br", "SenhaBoa123", {"nome": "Pulou"}, confirmado=True)
    r = _entrar(cliente, "pulou@uni.br", "SenhaBoa123")
    assert r.status_code == 403 and "análise" in r.json()["detail"]


def test_erro_de_validacao_vem_em_portugues(cliente):
    r = cliente.post("/api/cadastro", json={
        "nome": "Ana", "email": "ana@uni.br", "instituicao": "Uni",
        "vinculo": "estudante", "finalidade": "curta", "senha": "SenhaBoa123",
        "termos": True})
    assert r.status_code == 422
    assert r.json()["detail"] == ("Como pretende usar a plataforma: escreva pelo "
                                  "menos 10 caracteres.")
    r = cliente.post("/api/cadastro", json={"email": "nao-e-email"})
    assert "obrigatório" in r.json()["detail"] and "E-mail" in r.json()["detail"]


def test_promover_pede_a_senha_do_admin(cliente, supabase):
    s = _aprovado(cliente, supabase, "promover@uni.br")
    adm = _admin(cliente)
    uid = s["usuario"]["id"]
    url = f"/api/admin/usuarios/{uid}/papel"

    r = cliente.post(url, headers=cab(adm), json={"papel": "equipe"})
    assert r.status_code == 403 and "senha" in r.json()["detail"]
    r = cliente.post(url, headers=cab(adm), json={"papel": "equipe", "senha_admin": "errada"})
    assert r.status_code == 403 and "incorreta" in r.json()["detail"]
    assert cliente.get("/api/eu", headers=cab(s["token"])).json()["papel"] == "pesquisador"

    r = cliente.post(url, headers=cab(adm),
                     json={"papel": "equipe", "senha_admin": "SenhaAdmin123"})
    assert r.status_code == 200 and r.json()["papel"] == "equipe"
    avisos = cliente.get("/api/notificacoes", headers=cab(adm)).json()["avisos"]
    assert any(a["tipo"] == "papel" and "promover@uni.br" in a["texto"] for a in avisos)

    # Rebaixar não pede senha.
    r = cliente.post(url, headers=cab(adm), json={"papel": "pesquisador"})
    assert r.status_code == 200 and r.json()["papel"] == "pesquisador"


def test_apagar_conta_some_do_login_e_mantem_as_bases(cliente, supabase):
    from api import banco
    s = _aprovado(cliente, supabase, "apagar@uni.br")
    auth_id = supabase.por_email("apagar@uni.br")["id"]
    with banco.sessao() as db:
        db.add(banco.BaseDados(id="base-da-apagar", nome="Base dela", especie="X",
                               arquivo="x.csv", enviada_por="apagar@uni.br"))
        db.commit()
    adm = _admin(cliente)
    uid = s["usuario"]["id"]

    lista = cliente.get("/api/admin/usuarios", headers=cab(adm)).json()["usuarios"]
    assert next(x for x in lista if x["id"] == uid)["bases_enviadas"] == 1

    r = cliente.delete(f"/api/admin/usuarios/{uid}", headers=cab(adm))
    assert r.status_code == 200 and r.json()["bases_mantidas"] == 1
    assert auth_id not in supabase.contas
    assert _entrar(cliente, "apagar@uni.br", "SenhaBoa123").status_code == 401
    lista = cliente.get("/api/admin/usuarios", headers=cab(adm)).json()["usuarios"]
    assert all(x["email"] != "apagar@uni.br" for x in lista)
    with banco.sessao() as db:
        b = db.get(banco.BaseDados, "base-da-apagar")
        assert b is not None and b.enviada_por == "(conta apagada)"
        db.delete(b)
        db.commit()


def test_admin_nao_apaga_a_si_mesmo(cliente):
    adm = _admin(cliente)
    eu = cliente.get("/api/eu", headers=cab(adm)).json()
    assert cliente.delete(f"/api/admin/usuarios/{eu['id']}", headers=cab(adm)).status_code == 400
