/* Bionalya — ligação das telas com a API.

   Só o essencial: guardar o token, falar com a API, e proteger as telas que
   exigem login. Sem framework e sem build — é um arquivo só, carregado por
   todas as páginas depois do tema.js.
*/
(function (global) {
  "use strict";

  var CHAVE_TOKEN = "bionalya-token";
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
    guardar(CHAVE_USUARIO, JSON.stringify(dados.usuario || {}));
  }

  function limparSessao() {
    apagar(CHAVE_TOKEN); apagar(CHAVE_USUARIO); apagar(CHAVE_RESULTADO);
  }

  /* ------------------------------------------------------------------ rede */
  function api(caminho, opcoes) {
    opcoes = opcoes || {};
    var cabecalhos = Object.assign({}, opcoes.headers || {});
    if (opcoes.corpo !== undefined) {
      cabecalhos["Content-Type"] = "application/json";
      opcoes.body = JSON.stringify(opcoes.corpo);
      delete opcoes.corpo;
    }
    var t = token();
    if (t) cabecalhos["Authorization"] = "Bearer " + t;
    opcoes.headers = cabecalhos;

    return fetch(caminho, opcoes).then(function (r) {
      if (r.status === 204) return null;
      return r.text().then(function (texto) {
        var dados = null;
        try { dados = texto ? JSON.parse(texto) : null; } catch (e) { dados = null; }
        if (r.ok) return dados;

        var msg = (dados && (dados.detail || dados.mensagem)) || "Erro " + r.status;
        if (Array.isArray(msg)) {
          msg = msg.map(function (d) { return d.msg || JSON.stringify(d); }).join("; ");
        }
        if (r.status === 401) {       // sessão caiu: volta para a entrada
          limparSessao();
          if (!/login\.html/.test(location.pathname)) {
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
    api: api, token: token, usuario: usuario,
    entrarComSessao: entrarComSessao, limparSessao: limparSessao,
    exigirLogin: exigirLogin, pintarCabecalho: pintarCabecalho, pode: pode,
    aviso: aviso, ocupado: ocupado, contarAvisos: contarAvisos,
    pct: pct, num: num, inteiro: inteiro, sinal: sinal,
    guardarResultado: guardarResultado, lerResultado: lerResultado
  };
})(window);
