// Leva o foco ao resumo de erros após um envio inválido, para que leitores de
// tela anunciem os problemas e o teclado comece pelos links de correção.
(function () {
  var resumo = document.getElementById("resumo-erros");
  if (resumo) { resumo.focus(); }
})();
