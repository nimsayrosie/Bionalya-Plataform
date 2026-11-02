/* Bionalya — alternância de tema (claro / escuro).
   Único JavaScript da interface. Sem isso, a página ainda funciona:
   ela segue o tema do sistema operacional pelo CSS.

   Como usar numa página nova:
     <script src="tema.js"></script>            (dentro do <head>)
     <button class="tema" type="button" data-tema-botao aria-pressed="false">
       <span class="tema-icone" aria-hidden="true"></span>
       <span class="tema-texto">Modo escuro</span>
     </button>
*/
(function () {
  var CHAVE = "bionalya-tema";
  var raiz = document.documentElement;

  function lerSalvo() {
    try { return localStorage.getItem(CHAVE); } catch (e) { return null; }
  }
  function salvar(valor) {
    try { localStorage.setItem(CHAVE, valor); } catch (e) { /* modo privado */ }
  }

  // Aplica a escolha guardada antes da página pintar, para não piscar.
  var salvo = lerSalvo();
  if (salvo === "dark" || salvo === "light") raiz.setAttribute("data-theme", salvo);

  function escuroAtivo() {
    var t = raiz.getAttribute("data-theme");
    if (t === "dark") return true;
    if (t === "light") return false;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function atualizarBotoes() {
    var escuro = escuroAtivo();
    var botoes = document.querySelectorAll("[data-tema-botao]");
    for (var i = 0; i < botoes.length; i++) {
      botoes[i].setAttribute("aria-pressed", escuro ? "true" : "false");
      var texto = botoes[i].querySelector(".tema-texto");
      if (texto) texto.textContent = escuro ? "Modo claro" : "Modo escuro";
    }
  }

  document.addEventListener("click", function (ev) {
    var alvo = ev.target.closest ? ev.target.closest("[data-tema-botao]") : null;
    if (!alvo) return;
    var novo = escuroAtivo() ? "light" : "dark";
    raiz.setAttribute("data-theme", novo);
    salvar(novo);
    atualizarBotoes();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", atualizarBotoes);
  } else {
    atualizarBotoes();
  }
})();
