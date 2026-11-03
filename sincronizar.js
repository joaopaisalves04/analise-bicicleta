"use strict";
// Passa o relatório já calculado entre aparelhos (PC e telemóvel) usando a pasta privada desta app no Google Drive
// da própria pessoa. Só a app que a criou a consegue ver (âmbito drive.appdata); não aparece na lista de ficheiros do Drive.
// Nada passa por servidores nossos: o browser fala diretamente com o Google.
const Nuvem = (() => {
  const ESCOPO = "https://www.googleapis.com/auth/drive.appdata";
  const API = "https://www.googleapis.com/drive/v3";
  const CARREGAR = "https://www.googleapis.com/upload/drive/v3";
  const FICHEIROS = ["relatorio.html", "app.html", "mapa_calor.html"];
  const LIGADO = "analise-bicicleta-nuvem";
  let token = null;
  let expira = 0;

  const disponivel = () => typeof GOOGLE_CLIENT_ID === "string" && GOOGLE_CLIENT_ID.length > 0;
  const ligado = () => localStorage.getItem(LIGADO) === "1";

  async function carregarGoogle() {
    if (window.google && google.accounts && google.accounts.oauth2) return;
    await new Promise((ok, erro) => {
      const s = document.createElement("script");
      s.src = "https://accounts.google.com/gsi/client";
      s.onload = ok;
      s.onerror = () => erro(new Error("Não consegui ligar ao Google. Verifica a internet."));
      document.head.appendChild(s);
    });
  }

  // silencioso: não mostra nada ao utilizador (falha se ele ainda não tiver autorizado ou se a sessão Google expirou)
  async function obterToken(silencioso) {
    if (token && Date.now() < expira - 60000) return token;
    await carregarGoogle();
    return new Promise((ok, erro) => {
      const cliente = google.accounts.oauth2.initTokenClient({
        client_id: GOOGLE_CLIENT_ID,
        scope: ESCOPO,
        callback: (r) => {
          if (r.error) return erro(new Error(r.error));
          token = r.access_token;
          expira = Date.now() + (r.expires_in || 3600) * 1000;
          localStorage.setItem(LIGADO, "1");
          ok(token);
        },
        error_callback: (e) => erro(new Error(e && e.type === "popup_closed" ? "Cancelaste a ligação ao Google." : (e && e.type) || "Falhou a ligação ao Google.")),
      });
      cliente.requestAccessToken({ prompt: silencioso ? "none" : "" });
    });
  }

  async function pedir(url, opcoes = {}) {
    const r = await fetch(url, { ...opcoes, headers: { Authorization: "Bearer " + token, ...(opcoes.headers || {}) } });
    if (!r.ok) throw new Error(`O Google Drive respondeu ${r.status}.`);
    return r;
  }

  async function listar() {
    const r = await pedir(`${API}/files?spaces=appDataFolder&pageSize=50&fields=files(id,name,modifiedTime)`);
    return (await r.json()).files || [];
  }

  async function comprimir(blob) {
    return new Response(blob.stream().pipeThrough(new CompressionStream("gzip"))).blob();
  }

  async function descomprimir(buffer) {
    return new Response(new Blob([buffer]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer();
  }

  async function enviarFicheiro(nome, conteudo, existente) {
    if (existente) {
      await pedir(`${CARREGAR}/files/${existente.id}?uploadType=media`, { method: "PATCH", body: conteudo });
      return;
    }
    const limite = "bicicleta" + Math.random().toString(36).slice(2);
    const meta = JSON.stringify({ name: nome, parents: ["appDataFolder"] });
    const corpo = new Blob([`--${limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${meta}\r\n`,
      `--${limite}\r\nContent-Type: application/gzip\r\n\r\n`, conteudo, `\r\n--${limite}--`]);
    await pedir(`${CARREGAR}/files?uploadType=multipart`, {
      method: "POST", body: corpo, headers: { "Content-Type": `multipart/related; boundary=${limite}` },
    });
  }

  // ficheiros: { "relatorio.html": Blob, ... }
  async function enviar(ficheiros, silencioso = false) {
    await obterToken(silencioso);
    const existentes = await listar();
    for (const nome of FICHEIROS) {
      await enviarFicheiro(nome, await comprimir(ficheiros[nome]), existentes.find((f) => f.name === nome));
    }
  }

  // devolve { "relatorio.html": ArrayBuffer, ... } ou null se ainda não há nada guardado nesta conta
  async function receber() {
    await obterToken(false);
    const existentes = await listar();
    if (!FICHEIROS.every((n) => existentes.some((f) => f.name === n))) return null;
    const saida = {};
    for (const nome of FICHEIROS) {
      const r = await pedir(`${API}/files/${existentes.find((f) => f.name === nome).id}?alt=media`);
      saida[nome] = await descomprimir(await r.arrayBuffer());
    }
    return saida;
  }

  async function apagar() {
    await obterToken(false);
    for (const f of await listar()) await pedir(`${API}/files/${f.id}`, { method: "DELETE" });
  }

  const preparar = () => (disponivel() ? carregarGoogle().catch(() => {}) : null);
  const esquecer = () => { localStorage.removeItem(LIGADO); token = null; };

  return { disponivel, ligado, preparar, enviar, receber, apagar, esquecer, FICHEIROS };
})();
