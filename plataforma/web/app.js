/* Bionalya — ligação das telas com a API.

   Só o essencial: guardar o token, falar com a API, e proteger as telas que
   exigem login. Sem framework e sem build — é um arquivo só, carregado por
   todas as páginas depois do tema.js.

   O login é do Supabase, mas as telas não falam com ele: tudo passa pela
   nossa API. O token vale uma hora; quando vence, a API responde 401 e este
   arquivo troca o refresh_token por um token novo e repete o pedido, sem a
   pessoa perceber.
*/
(function (global) {
  "use strict";

  var CHAVE_TOKEN = "bionalya-token";
  var CHAVE_RENOVAR = "bionalya-renovar";
  var CHAVE_USUARIO = "bionalya-usuario";
  var CHAVE_RESULTADO = "bionalya-ultimo-resultado";

  /* ---------------------------------------------------------- armazenamento */
  function guardar(chave, valor) {
    try { localStorage.setItem(chave, valor); } catch (e) { /* modo privado */ }
  }
  function ler(chave) {
    try { return localStorage.getItem(chave); } catch (e) { return null; }
  }
  function apagar(chave) {
    try { localStorage.removeItem(chave); } catch (e) { /* ignora */ }
  }

  function token() { return ler(CHAVE_TOKEN); }

  function usuario() {
    try { return JSON.parse(ler(CHAVE_USUARIO) || "null"); } catch (e) { return null; }
  }

  function entrarComSessao(dados) {
    guardar(CHAVE_TOKEN, dados.token);
    if (dados.refresh_token) guardar(CHAVE_RENOVAR, dados.refresh_token);
    if (dados.usuario) guardar(CHAVE_USUARIO, JSON.stringify(dados.usuario));
  }

  function limparSessao() {
    apagar(CHAVE_TOKEN); apagar(CHAVE_RENOVAR);
    apagar(CHAVE_USUARIO); apagar(CHAVE_RESULTADO);
  }

  /* Uma renovação por vez: se três pedidos voltam 401 juntos, os três
     esperam a mesma renovação em vez de gastar o refresh_token três vezes. */
  var renovando = null;
  function renovarSessao() {
    var r = ler(CHAVE_RENOVAR);
    if (!r) return Promise.resolve(false);
    if (!renovando) {
      renovando = fetch("/api/sessao/renovar", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: r })
      }).then(function (resp) {
        if (!resp.ok) return false;
        return resp.json().then(function (d) { entrarComSessao(d); return true; });
      }).catch(function () { return false; })
        .then(function (ok) { renovando = null; return ok; });
    }
    return renovando;
  }

  /* fetch com o token, renovando uma vez se ele tiver vencido. Para quem
     precisa da resposta crua (download de arquivo, upload com FormData). */
  function buscar(caminho, opcoes) {
    opcoes = Object.assign({}, opcoes || {});
    function tentar() {
      var cab = Object.assign({}, opcoes.headers || {});
      var t = token();
      if (t) cab["Authorization"] = "Bearer " + t;
      return fetch(caminho, Object.assign({}, opcoes, { headers: cab }));
    }
    return tentar().then(function (r) {
      if (r.status !== 401 || !ler(CHAVE_RENOVAR) || /\/api\/sessao/.test(caminho)) return r;
      return renovarSessao().then(function (ok) { return ok ? tentar() : r; });
    });
  }

  /* ------------------------------------------------------------------ rede */
  function api(caminho, opcoes) {
    opcoes = Object.assign({}, opcoes || {});
    var cabecalhos = Object.assign({}, opcoes.headers || {});
    if (opcoes.corpo !== undefined) {
      cabecalhos["Content-Type"] = "application/json";
      opcoes.body = JSON.stringify(opcoes.corpo);
      delete opcoes.corpo;
    }
    opcoes.headers = cabecalhos;

    return buscar(caminho, opcoes).then(function (r) {
      if (r.status === 204) return null;
      return r.text().then(function (texto) {
        var dados = null;
        try { dados = texto ? JSON.parse(texto) : null; } catch (e) { dados = null; }
        if (r.ok) return dados;

        var msg = (dados && (dados.detail || dados.mensagem)) || "Erro " + r.status;
        if (Array.isArray(msg)) {
          msg = msg.map(function (d) { return d.msg || JSON.stringify(d); }).join("; ");
        }
        // Sessão caiu e não deu para renovar: volta para a entrada. Nas telas
        // de acesso o 401 é só "senha errada", e fica na tela.
        if (r.status === 401 && token()) {
          limparSessao();
          if (!/(login|cadastro|esqueci-senha|redefinir-senha|confirmar-email)\.html/
                .test(location.pathname)) {
            location.href = "login.html?expirou=1";
          }
        }
        var erro = new Error(msg);
        erro.status = r.status;
        erro.dados = dados;
        throw erro;
      });
    });
  }

  /* --------------------------------------------------- proteção das telas */
  var NIVEL = { pesquisador: 1, equipe: 2, admin: 3 };

  function pode(u, minimo) {
    return (NIVEL[u && u.papel] || 0) >= (NIVEL[minimo] || 99);
  }

  function exigirLogin(opcoes) {
    opcoes = opcoes || {};
    if (!token()) {
      location.href = "login.html?volta=" + encodeURIComponent(
        location.pathname.split("/").pop());
      return Promise.reject(new Error("sem sessão"));
    }
    return api("/api/eu").then(function (u) {
      guardar(CHAVE_USUARIO, JSON.stringify(u));
      // Senha definida por outra pessoa: troca antes de a tela carregar.
      return u.senha_trocada ? u : pedirTrocaDeSenha(u);
    }).then(function (u) {
      var exigido = opcoes.papel || (opcoes.equipe ? "equipe" : null);
      if (exigido && !pode(u, exigido)) {
        location.href = "index.html";
        throw new Error("sem permissão");
      }
      pintarCabecalho(u);
      return u;
    });
  }

  function pintarCabecalho(u) {
    var alvo = document.querySelector("[data-usuario]");
    if (alvo) alvo.textContent = (u.nome || "").split(" ")[0];
    document.querySelectorAll("[data-papel]").forEach(function (el) {
      el.hidden = !pode(u, el.dataset.papel);
    });
    document.querySelectorAll("[data-so-equipe]").forEach(function (el) {
      el.hidden = !pode(u, "equipe");
    });
    if (pode(u, "equipe")) contarAvisos();
    var sair = document.querySelector("[data-sair]");
    if (sair && !sair.dataset.ligado) {
      sair.dataset.ligado = "1";
      sair.addEventListener("click", function (ev) {
        ev.preventDefault();
        api("/api/sessao", { method: "DELETE" })
          .catch(function () { /* mesmo falhando, limpa do lado de cá */ })
          .then(function () { limparSessao(); location.href = "login.html"; });
      });
    }
  }

  /* ---------------------------------------- troca obrigatória de senha */
  /* Quem entra com uma senha que outra pessoa definiu (o admin gerou, ou
     criou a conta com ela) troca na hora, num pop-up que não dá para fechar.
     A API também recusa as outras rotas até a troca: o pop-up não é só
     enfeite que dá para apagar pelo inspetor do navegador. */
  var trocaEmAndamento = null;

  function pedirTrocaDeSenha(u) {
    if (trocaEmAndamento) return trocaEmAndamento;
    trocaEmAndamento = new Promise(function (resolver) {
      var d = document.createElement("dialog");
      d.className = "dialogo";
      d.setAttribute("aria-labelledby", "troca-titulo");
      d.innerHTML =
        '<h2 id="troca-titulo">Crie a sua senha</h2>' +
        '<p>Você entrou com uma senha que outra pessoa definiu. Antes de continuar, ' +
        'troque por uma que só você conheça.</p>' +
        '<div class="recado" id="troca-recado" hidden role="alert"></div>' +
        '<form novalidate>' +
        '  <div class="campo"><label for="troca-atual">Senha que você recebeu</label>' +
        '    <input type="password" id="troca-atual" autocomplete="current-password" required></div>' +
        '  <div class="campo"><label for="troca-nova">Senha nova</label>' +
        '    <input type="password" id="troca-nova" autocomplete="new-password" ' +
        '           minlength="8" maxlength="72" required aria-describedby="troca-ajuda">' +
        '    <span class="ajuda" id="troca-ajuda">Pelo menos 8 caracteres.</span></div>' +
        '  <div class="campo"><label for="troca-confirma">Repita a senha nova</label>' +
        '    <input type="password" id="troca-confirma" autocomplete="new-password" ' +
        '           minlength="8" maxlength="72" required></div>' +
        '  <button class="botao" type="submit" style="width:100%">Salvar e continuar</button>' +
        '</form>' +
        '<p class="dialogo-rodape"><a href="#" data-troca-sair>Sair da conta</a></p>';
      document.body.appendChild(d);

      var form = d.querySelector("form");
      var btn = form.querySelector("button");
      var recado = d.querySelector("#troca-recado");

      // Esc não fecha: a troca é obrigatória.
      d.addEventListener("cancel", function (ev) { ev.preventDefault(); });

      d.querySelector("[data-troca-sair]").addEventListener("click", function (ev) {
        ev.preventDefault();
        api("/api/sessao", { method: "DELETE" }).catch(function () {})
          .then(function () { limparSessao(); location.href = "login.html"; });
      });

      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        aviso(recado, null);
        var atual = d.querySelector("#troca-atual").value;
        var nova = d.querySelector("#troca-nova").value;
        if (nova.length < 8) {
          d.querySelector("#troca-nova").focus();
          return aviso(recado, "A senha nova precisa de pelo menos 8 caracteres.");
        }
        if (nova !== d.querySelector("#troca-confirma").value) {
          d.querySelector("#troca-confirma").focus();
          return aviso(recado, "As duas senhas novas não são iguais.");
        }
        ocupado(btn, true, "Salvando…");
        api("/api/eu/senha", { method: "POST", corpo: {
          senha_atual: atual, senha_nova: nova
        }}).then(function (r) {
          entrarComSessao(r);
          d.close();
          d.remove();
          trocaEmAndamento = null;
          resolver(r.usuario || Object.assign({}, u, { senha_trocada: true }));
        }).catch(function (e) {
          ocupado(btn, false);
          aviso(recado, e.message);
        });
      });

      d.showModal();
      d.querySelector("#troca-atual").focus();
    });
    return trocaEmAndamento;
  }

  /* ------------------------------------------------- avisos para a equipe */
  /* Importar base e treinar modelo não passam mais por aprovação. Em vez de
     segurar o trabalho de quem envia, a plataforma avisa a equipe: este é o
     contador que aparece no menu. */
  function contarAvisos() {
    return api("/api/notificacoes?limite=1").then(function (d) {
      document.querySelectorAll("[data-avisos]").forEach(function (el) {
        el.textContent = d.nao_lidas;
        el.hidden = !d.nao_lidas;
      });
      return d.nao_lidas;
    }).catch(function () { /* contador é enfeite: nunca derruba a tela */ });
  }

  /* ---------------------------------------------------------------- recados */
  function aviso(destino, texto, tipo) {
    var el = typeof destino === "string" ? document.querySelector(destino) : destino;
    if (!el) return;
    if (!texto) { el.hidden = true; el.textContent = ""; return; }
    el.hidden = false;
    el.className = "recado recado-" + (tipo || "erro");
    el.textContent = texto;
  }

  function ocupado(botao, estaOcupado, textoOcupado) {
    if (!botao) return;
    if (estaOcupado) {
      botao.dataset.textoOriginal = botao.dataset.textoOriginal || botao.textContent;
      botao.textContent = textoOcupado || "Aguarde…";
      botao.disabled = true;
    } else {
      if (botao.dataset.textoOriginal) botao.textContent = botao.dataset.textoOriginal;
      botao.disabled = false;
    }
  }

  /* -------------------------------------------------------------- formatos */
  function pct(x, casas) {
    if (x === null || x === undefined) return "—";
    return (x * 100).toFixed(casas === undefined ? 1 : casas).replace(".", ",") + "%";
  }
  function num(x, casas) {
    if (x === null || x === undefined) return "—";
    return Number(x).toFixed(casas === undefined ? 3 : casas).replace(".", ",");
  }
  function inteiro(x) {
    if (x === null || x === undefined) return "—";
    return Number(x).toLocaleString("pt-BR");
  }
  function sinal(x) {
    var s = Number(x).toFixed(2).replace(".", ",");
    return (x > 0 ? "+" : x < 0 ? "−" : "") + s.replace("-", "");
  }

  function guardarResultado(r) { guardar(CHAVE_RESULTADO, JSON.stringify(r)); }
  function lerResultado() {
    try { return JSON.parse(ler(CHAVE_RESULTADO) || "null"); } catch (e) { return null; }
  }

  global.Bio = {
    api: api, buscar: buscar, token: token, usuario: usuario,
    entrarComSessao: entrarComSessao, limparSessao: limparSessao,
    exigirLogin: exigirLogin, pintarCabecalho: pintarCabecalho, pode: pode,
    aviso: aviso, ocupado: ocupado, contarAvisos: contarAvisos,
    pct: pct, num: num, inteiro: inteiro, sinal: sinal,
    pedirTrocaDeSenha: pedirTrocaDeSenha,
    guardarResultado: guardarResultado, lerResultado: lerResultado
  };
})(window);
