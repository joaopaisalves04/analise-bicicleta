"use strict";
// Página: recebe os ficheiros do Garmin, entrega-os ao trabalhador (que corre o Python) e mostra o relatório.
const $ = (s) => document.querySelector(s);
const ADEQUADO = /\.(fit|zip)$|_heartRateZones\.json$/i;
const CHAVE = "analise-bicicleta";
let trabalhador = null;
let ocupado = false;

// ---------- service worker ----------
async function iniciarSW() {
  if (!("serviceWorker" in navigator)) return;
  try {
    await navigator.serviceWorker.register("sw.js");
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise((ok) => {
        navigator.serviceWorker.addEventListener("controllerchange", ok, { once: true });
        setTimeout(ok, 2500);
      });
    }
  } catch (e) { /* sem service worker a página funciona, só não guarda o relatório para a próxima visita */ }
}

// ---------- ecrãs ----------
function aviso(texto) {
  const a = $("#aviso");
  a.textContent = texto;
  a.hidden = false;
  clearTimeout(aviso.t);
  aviso.t = setTimeout(() => (a.hidden = true), 5000);
}

function mostrarInicio() {
  $("#relatorio").hidden = true;
  $("#relatorio").removeAttribute("src");
  $("#inicio").hidden = false;
  for (const b of ["#b-juntar", "#b-fcmax", "#b-apagar", "#b-nuvem"]) $(b).hidden = true;
  $("#l-nuvem").hidden = !Nuvem.disponivel();
}

function mostrarRelatorio() {
  const pagina = window.innerWidth <= 760 ? "app" : "relatorio";
  $("#relatorio").src = `resultado/${pagina}.html?t=${Date.now()}`;
  $("#relatorio").hidden = false;
  $("#inicio").hidden = true;
  for (const b of ["#b-juntar", "#b-fcmax", "#b-apagar"]) $(b).hidden = false;
  const doDrive = (meta() || {}).origem === "nuvem";
  $("#b-nuvem").textContent = doDrive ? "Atualizar do Drive" : "Guardar no Drive";
  $("#b-nuvem").title = doDrive ? "Vai buscar ao Google Drive o relatório mais recente" : "Guarda o relatório no teu Google Drive, para o ver noutros aparelhos";
  $("#b-nuvem").hidden = !Nuvem.disponivel();
  $("#b-fcmax").hidden = doDrive; // no telemóvel o relatório vem pronto: não há cálculo a refazer
  $("#b-juntar").hidden = doDrive;
}

function meta() {
  try { return JSON.parse(localStorage.getItem(CHAVE)); } catch (e) { return null; }
}

async function lerResultado() {
  const cache = await caches.open("resultado");
  const saida = {};
  for (const nome of Nuvem.FICHEIROS) {
    const r = await cache.match(new URL("resultado/" + nome, location.href).href);
    if (!r) throw new Error("Falta o relatório guardado neste aparelho.");
    saida[nome] = await r.blob();
  }
  return saida;
}

async function enviarNuvem(silencioso) {
  try {
    if (!silencioso) abrirProgresso("A guardar no teu Google Drive...");
    await Nuvem.enviar(await lerResultado(), silencioso);
    $("#progresso").hidden = true;
    aviso("Guardado no teu Google Drive. No telemóvel, abre esta página e carrega em \"Obter do Google Drive\".");
  } catch (e) {
    $("#progresso").hidden = true;
    aviso(silencioso ? "Para atualizar o Google Drive, carrega em \"Guardar no Drive\"." : e.message);
  }
}

async function receberNuvem() {
  try {
    abrirProgresso("A obter do teu Google Drive...");
    const dados = await Nuvem.receber();
    $("#progresso").hidden = true;
    if (!dados) { aviso("Ainda não há nada guardado nesta conta Google. No computador, carrega em \"Guardar no Drive\"."); return; }
    await guardarResultado(dados);
    localStorage.setItem(CHAVE, JSON.stringify({ origem: "nuvem", quando: Date.now() }));
    mostrarRelatorio();
    aviso("Relatório atualizado a partir do Google Drive.");
  } catch (e) {
    $("#progresso").hidden = true;
    aviso(e.message);
  }
}

async function haRelatorio() {
  if (!("caches" in window) || !localStorage.getItem(CHAVE)) return false;
  try {
    const cache = await caches.open("resultado");
    return (await cache.keys()).length >= 3;
  } catch (e) { return false; }
}

async function guardarResultado(ficheiros) {
  await caches.delete("resultado");
  const cache = await caches.open("resultado");
  for (const [nome, dados] of Object.entries(ficheiros)) {
    await cache.put(new URL("resultado/" + nome, location.href).href,
                    new Response(dados, { headers: { "Content-Type": "text/html; charset=utf-8" } }));
  }
}

// ---------- progresso ----------
function abrirProgresso(titulo) {
  $("#titulo").textContent = titulo;
  $("#contagem").textContent = "";
  $("#registo").textContent = "";
  $("#erro").hidden = true;
  $("#fechar-erro").hidden = true;
  const barra = $("#barra");
  barra.classList.add("indef");
  barra.firstElementChild.style.width = "";
  $("#progresso").hidden = false;
}

function registo(texto) {
  const r = $("#registo");
  r.textContent += texto + "\n";
  r.scrollTop = r.scrollHeight;
}

function falhou(texto) {
  $("#titulo").textContent = "Algo correu mal";
  $("#barra").hidden = true;
  $("#erro").textContent = texto;
  $("#erro").hidden = false;
  $("#fechar-erro").hidden = false;
}

// ---------- trabalho ----------
function obterTrabalhador() {
  if (!trabalhador) trabalhador = new Worker("trabalhador.js", { type: "module" });
  return trabalhador;
}

function executar(ficheiros, opcoes = {}) {
  if (ocupado) return;
  ocupado = true;
  abrirProgresso(ficheiros.length ? "A ler os teus passeios..." : "A atualizar...");
  const t = obterTrabalhador();
  const barra = $("#barra");
  t.onmessage = async (e) => {
    const m = e.data;
    if (m.tipo === "estado") { $("#contagem").textContent = m.texto; registo(m.texto); }
    else if (m.tipo === "lidos") $("#contagem").textContent = `${m.vistos} ficheiros vistos, ${m.novos} passeios de bicicleta encontrados`;
    else if (m.tipo === "leitura") {
      $("#titulo").textContent = "A calcular a tua análise...";
      barra.classList.remove("indef");
      barra.firstElementChild.style.width = Math.max(4, (100 * m.n) / m.total) + "%";
      $("#contagem").textContent = `Passeio ${m.n + 1} de ${m.total}. Só demora assim na primeira vez.`;
    } else if (m.tipo === "texto") registo(m.texto);
    else if (m.tipo === "erro") { ocupado = false; falhou(m.texto); }
    else if (m.tipo === "fim") await terminar(m);
  };
  t.onerror = (e) => { ocupado = false; falhou("O motor de cálculo parou: " + (e.message || "erro desconhecido")); };
  t.postMessage({ tipo: "executar", ficheiros: ficheiros.map((f) => ({ nome: f.caminho, blob: f.file })), ...opcoes });
}

async function terminar(m) {
  ocupado = false;
  const r = m.resultado;
  if (r.passeios === 0) {
    $("#progresso").hidden = true;
    mostrarInicio();
    aviso("Não encontrei passeios de bicicleta nesses ficheiros. Confirma que exportaste o original do passeio.");
    return;
  }
  if (!r.gerado) {
    $("#progresso").hidden = true;
    aviso(r.novos === 0 ? "Esses passeios já estavam aqui. Nada de novo." : "Feito.");
    return;
  }
  await guardarResultado(m.ficheiros);
  localStorage.setItem(CHAVE, JSON.stringify({ origem: "calculado", passeios: r.passeios, quando: Date.now() }));
  $("#progresso").hidden = true;
  mostrarRelatorio();
  if (Nuvem.disponivel() && Nuvem.ligado()) enviarNuvem(true); // se já ligaste ao Drive, mantém-no atualizado
  if (navigator.storage && navigator.storage.persist) navigator.storage.persist();
  aviso(r.novos ? `${r.novos} passeio${r.novos === 1 ? "" : "s"} novo${r.novos === 1 ? "" : "s"}. Total: ${r.passeios}.` : "Relatório atualizado.");
}

// ---------- ficheiros ----------
function dosInputs(lista) {
  return [...lista].filter((f) => ADEQUADO.test(f.name))
    .map((f) => ({ file: f, caminho: f.webkitRelativePath || f.name }));
}

async function lerEntrada(entrada, prefixo, saida) {
  if (entrada.isFile) {
    if (ADEQUADO.test(entrada.name)) {
      const file = await new Promise((ok, erro) => entrada.file(ok, erro));
      saida.push({ file, caminho: prefixo + entrada.name });
    }
  } else if (entrada.isDirectory) {
    const leitor = entrada.createReader();
    for (;;) {
      const bloco = await new Promise((ok, erro) => leitor.readEntries(ok, erro));
      if (!bloco.length) break;
      for (const filho of bloco) await lerEntrada(filho, prefixo + entrada.name + "/", saida);
    }
  }
}

async function dosItens(dt) {
  const saida = [];
  const entradas = [...dt.items].map((i) => (i.webkitGetAsEntry ? i.webkitGetAsEntry() : null));
  if (entradas.every(Boolean) && entradas.length) {
    for (const e of entradas) await lerEntrada(e, "", saida);
    return saida;
  }
  return dosInputs(dt.files);
}

function valorNumero(id) {
  const v = parseInt($(id).value, 10);
  return Number.isFinite(v) ? v : undefined;
}

function receber(ficheiros) {
  if (!ficheiros.length) {
    aviso("Não vi ficheiros .fit ou .zip. Larga os ficheiros exportados do Garmin Connect.");
    return;
  }
  executar(ficheiros, { fcMax: valorNumero("#fcmax"), idade: valorNumero("#idade") });
}

// ---------- ligações ----------
function ligar() {
  $("#b-escolher").onclick = $("#b-juntar").onclick = () => $("#in-ficheiros").click();
  $("#b-pasta").onclick = () => $("#in-pasta").click();
  $("#in-ficheiros").onchange = (e) => { receber(dosInputs(e.target.files)); e.target.value = ""; };
  $("#in-pasta").onchange = (e) => { receber(dosInputs(e.target.files)); e.target.value = ""; };
  Nuvem.preparar();
  $("#l-nuvem").hidden = !Nuvem.disponivel();
  $("#b-nuvem").onclick = () => ((meta() || {}).origem === "nuvem" ? receberNuvem() : enviarNuvem(false));
  $("#a-nuvem").onclick = (e) => { e.preventDefault(); receberNuvem(); };
  $("#b-fechar").onclick = () => { $("#progresso").hidden = true; $("#barra").hidden = false; };

  const largar = $("#largar");
  for (const ev of ["dragenter", "dragover"]) {
    document.addEventListener(ev, (e) => { e.preventDefault(); largar.classList.add("sobre"); });
  }
  for (const ev of ["dragleave", "drop"]) {
    document.addEventListener(ev, (e) => { e.preventDefault(); largar.classList.remove("sobre"); });
  }
  document.addEventListener("drop", async (e) => receber(await dosItens(e.dataTransfer)));

  $("#b-fcmax").onclick = () => {
    const texto = prompt("Qual é a tua frequência cardíaca máxima (bpm)? Usa o valor que está no Garmin Connect, ou o mais alto que já viste.");
    const v = parseInt(texto, 10);
    if (!texto) return;
    if (!(v >= 120 && v <= 230)) { aviso("Escreve um número entre 120 e 230."); return; }
    executar([], { fcMax: v, redefinir: true, forcar: true });
  };

  $("#b-apagar").onclick = async () => {
    if (!confirm("Apagar todos os passeios e o relatório guardados neste browser? Os teus ficheiros do Garmin não são afetados.")) return;
    if (Nuvem.disponivel() && Nuvem.ligado() && confirm("Apagar também a cópia guardada no teu Google Drive?")) {
      try { await Nuvem.apagar(); } catch (e) { aviso("Não consegui apagar a cópia do Drive: " + e.message); }
    }
    Nuvem.esquecer();
    if (trabalhador) { trabalhador.terminate(); trabalhador = null; }
    localStorage.removeItem(CHAVE);
    await caches.delete("resultado");
    await Promise.all(["/dados", "/cache"].map((nome) => new Promise((ok) => {
      const pedido = indexedDB.deleteDatabase(nome);
      pedido.onsuccess = pedido.onerror = pedido.onblocked = () => ok();
    })));
    mostrarInicio();
    aviso("Dados apagados.");
  };
}

(async function () {
  ligar();
  await iniciarSW();
  if (await haRelatorio()) mostrarRelatorio();
})();
