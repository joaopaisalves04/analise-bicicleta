// Linhas do mapa, filtros (período, volta, escalões) e lista de passeios ao clicar.
// Os dados vêm de <script id="dados-mapa">, escritos por analisar.py; __MAPA__ é a variável do mapa Leaflet.
// Abrir com #volta=N no endereço mostra só essa volta (usado pelos links do relatório).
window.addEventListener("load", function () {
  var mapa = __MAPA__;
  var dados = JSON.parse(document.getElementById("dados-mapa").textContent);
  var E = dados.escaloes, P = dados.passeios, T = dados.trocos;
  var render = L.canvas({ padding: 0.5 });
  var camadas = E.map(function () { return null; });
  var contorno = null;                                 // contorno escuro por baixo do "1 vez", que é claro
  var visivel = E.map(function () { return true; });
  var dentro = P.map(function () { return true; });  // passeio dentro dos filtros
  var escalaoDe = new Int8Array(T.length);              // escalão de cada troço com os filtros (-1 = nenhum)
  var descricao = "";

  function escalao(n) {
    for (var i = 0; i < E.length; i++) if (n >= E[i].lo && n <= E[i].hi) return i;
    return -1;
  }
  function ponto(s, k) { return [s[2 * k], s[2 * k + 1]]; }
  function dataPt(d) { return d.split("-").reverse().join("/"); }

  function desenhar() {
    var linhas = E.map(function () { return []; });
    for (var k = 0; k < T.length; k++) {
      var ids = T[k][4], n = 0;
      for (var j = 0; j < ids.length; j++) if (dentro[ids[j]]) n++;
      var e = n ? escalao(n) : -1;
      escalaoDe[k] = e;
      if (e >= 0) linhas[e].push([ponto(T[k], 0), ponto(T[k], 1)]);
    }
    if (contorno) mapa.removeLayer(contorno);
    contorno = L.polyline(linhas[0], { renderer: render, color: "#6b5a1e", weight: E[0].larg + 2,
                                       opacity: 0.45, interactive: false });
    E.forEach(function (esc, i) {
      if (camadas[i]) mapa.removeLayer(camadas[i]);
      camadas[i] = L.polyline(linhas[i], { renderer: render, color: esc.cor, weight: esc.larg,
                                           opacity: 0.9, interactive: false });
    });
    atualizarVisiveis();
    return linhas;
  }

  // (re)põe as camadas por ordem: contorno, depois do escalão mais raro ao mais frequente (fica por cima)
  function atualizarVisiveis() {
    [contorno].concat(camadas).forEach(function (l) { if (l) mapa.removeLayer(l); });
    if (visivel[0] && contorno.getLatLngs().length) contorno.addTo(mapa);
    camadas.forEach(function (l, i) { if (visivel[i] && l.getLatLngs().length) l.addTo(mapa); });
  }

  function mostrar(i, sim) {
    visivel[i] = sim;
    document.querySelector('#escaloes input[data-i="' + i + '"]').checked = sim;
    atualizarVisiveis();
  }

  // legenda: encolher/abrir (começa encolhida em ecrãs pequenos e no mapa embutido no relatório)
  var legenda = document.getElementById("legenda"), abrir = document.getElementById("abrir");
  function encolher(sim) {
    legenda.classList.toggle("fechada", sim);
    abrir.textContent = (sim ? "▸" : "▾") + " Legenda e filtros";
    abrir.setAttribute("aria-expanded", String(!sim));
  }
  abrir.addEventListener("click", function () { encolher(!legenda.classList.contains("fechada")); });
  encolher(window.matchMedia("(max-width: 600px)").matches || window.innerHeight < 650);
  L.DomEvent.disableClickPropagation(legenda);
  L.DomEvent.disableScrollPropagation(legenda);

  // escalões
  document.getElementById("escaloes").innerHTML = E.map(function (esc, i) {
    return '<div class="lin"><label><input type="checkbox" data-i="' + i + '" checked>' +
      '<span class="cor" style="height:' + esc.larg + 'px;background:' + esc.cor +
      (i === 0 ? ";box-shadow:0 0 0 1px rgba(107,90,30,.45)" : "") + '"></span>' + esc.rot +
      '</label><a href="#" data-so="' + i + '">só este</a></div>';
  }).join("");
  document.querySelectorAll("#escaloes input").forEach(function (cb) {
    cb.addEventListener("change", function () { mostrar(+cb.dataset.i, cb.checked); });
  });
  document.querySelectorAll("#escaloes a[data-so]").forEach(function (a) {
    a.addEventListener("click", function (ev) {
      ev.preventDefault();
      E.forEach(function (_, i) { mostrar(i, i === +a.dataset.so); });
    });
  });
  document.querySelectorAll("#legenda button[data-todos]").forEach(function (b) {
    b.addEventListener("click", function () { E.forEach(function (_, i) { mostrar(i, b.dataset.todos === "1"); }); });
  });

  // filtros de período e de volta
  var selP = document.getElementById("periodo"), selV = document.getElementById("volta");
  selP.innerHTML = dados.periodos.map(function (op, i) {
    return '<option value="' + i + '">' + op.rot + "</option>";
  }).join("");
  selV.innerHTML = '<option value="0">Todos os passeios</option>' + dados.voltas.map(function (v) {
    return '<option value="' + v.n + '">' + v.rot + "</option>";
  }).join("");

  function aplicarFiltros(enquadrar) {
    var op = dados.periodos[+selP.value], vol = +selV.value, n = 0, km = 0;
    P.forEach(function (p, i) {
      dentro[i] = p.d >= op.de && p.d <= op.ate && (vol === 0 || p.vol === vol);
      if (dentro[i]) { n++; km += p.km; }
    });
    var partes = [];
    if (op.rot !== "Tudo") partes.push(op.rot.toLowerCase());
    if (vol) partes.push("volta " + vol);
    descricao = partes.length ? " (" + partes.join(", ") + ")" : "";
    document.getElementById("info-periodo").textContent =
      dataPt(op.de) + " a " + dataPt(op.ate) + " · " + n + " passeios · " + Math.round(km) + " km";
    mapa.closePopup();
    var linhas = desenhar();
    if (enquadrar && vol) {  // aproxima o mapa da volta escolhida
      var todas = [].concat.apply([], linhas);
      if (todas.length) mapa.fitBounds(L.latLngBounds([].concat.apply([], todas)), { padding: [40, 40], animate: false });
    }
  }
  selP.addEventListener("change", function () { aplicarFiltros(false); });
  selV.addEventListener("change", function () { aplicarFiltros(true); });

  function lerEndereco() {
    var m = location.hash.match(/volta=(\d+)/);
    if (!m) return false;
    selV.value = m[1];
    selP.value = "0";
    aplicarFiltros(true);
    return true;
  }
  window.addEventListener("hashchange", lerEndereco);

  // clique: troço visível mais próximo (até 10 px) e lista dos passeios que lá passaram
  function distSeg(p, a, b) {
    var dx = b.x - a.x, dy = b.y - a.y, l2 = dx * dx + dy * dy;
    var t = l2 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2)) : 0;
    return Math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy);
  }
  mapa.on("click", function (ev) {
    var pt = mapa.latLngToContainerPoint(ev.latlng), melhor = -1, dmin = 10;
    for (var k = 0; k < T.length; k++) {
      var e = escalaoDe[k];
      if (e < 0 || !visivel[e]) continue;
      var a = mapa.latLngToContainerPoint(ponto(T[k], 0));
      if (Math.abs(a.x - pt.x) > 60 || Math.abs(a.y - pt.y) > 60) continue;  // atalho: longe demais
      var d = distSeg(pt, a, mapa.latLngToContainerPoint(ponto(T[k], 1)));
      if (d < dmin) { dmin = d; melhor = k; }
    }
    if (melhor < 0) return;
    var ids = T[melhor][4].filter(function (i) { return dentro[i]; })
      .sort(function (x, y) { return P[x].d < P[y].d ? 1 : -1; });
    var linhas = ids.map(function (i) {
      var p = P[i];
      return "<tr><td>" + dataPt(p.d) + "</td><td>" + p.km.toFixed(1).replace(".", ",") + "</td><td>" +
        (p.v === null ? "–" : p.v.toFixed(1).replace(".", ",")) + "</td><td>" + (p.vol || "") + "</td></tr>";
    }).join("");
    L.popup({ maxWidth: 360 }).setLatLng(ev.latlng).setContent(
      "<b>Passaste aqui " + (ids.length === 1 ? "1 vez" : ids.length + " vezes") + "</b>" + descricao +
      '<div class="lista-passeios"><table><thead><tr><th>Data</th><th>km</th><th>km/h média</th><th>volta</th>' +
      "</tr></thead><tbody>" + linhas + "</tbody></table></div>" +
      '<div style="color:#666;font-size:11px;margin-top:4px">km e km/h do passeio inteiro</div>'
    ).openOn(mapa);
  });

  if (!lerEndereco()) aplicarFiltros(false);
});
