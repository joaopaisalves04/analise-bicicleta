import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";
// Corre o programa Python (o mesmo do computador) dentro do browser, em segundo plano, com o Pyodide.
// Os ficheiros do Garmin são lidos aqui e nunca saem do aparelho.

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const VERSAO = "54be24ae5d"; // mudar quando o código Python mudar, para o browser não usar uma cópia antiga
const PACOTES = ["numpy", "pandas", "jinja2", "requests", "narwhals", "packaging", "xyzservices", "micropip"];
const RODAS = ["branca-0.8.2-py3-none-any.whl", "folium-0.20.0-py2.py3-none-any.whl", "plotly-7.1.0-py3-none-any.whl"];
const PROGRAMA = ["analisar.py", "relatorio.py", "app_movel.py", "meteo.py", "importar.py", "importar_web.py", "mapa.js"];
const FITPARSE = ["__init__.py", "base.py", "processors.py", "profile.py", "records.py", "utils.py"];
const RESULTADOS = ["relatorio.html", "app.html", "mapa_calor.html"];


let py = null;
const enviar = (tipo, dados = {}) => self.postMessage({ tipo, ...dados });
const relativo = (caminho) => new URL(caminho, self.location.href).href;

function sincronizar(deBrowser) {
  return new Promise((ok, erro) => py.FS.syncfs(deBrowser, (e) => (e ? erro(e) : ok())));
}

async function ficheiro(caminho) {
  const r = await fetch(relativo(caminho) + "?v=" + VERSAO);
  if (!r.ok) throw new Error("Não consegui descarregar " + caminho);
  return new Uint8Array(await r.arrayBuffer());
}

async function iniciar() {
  if (py) return;
  enviar("estado", { texto: "A preparar o motor de cálculo. Na primeira vez descarrega cerca de 40 MB e demora um pouco." });
  py = await loadPyodide({ indexURL: PYODIDE });
  await py.loadPackage(PACOTES);
  enviar("estado", { texto: "A preparar os gráficos e o mapa..." });
  const micropip = py.pyimport("micropip");
  for (const roda of RODAS) await micropip.install.callKwargs(relativo("rodas/" + roda), { deps: false });

  py.FS.mkdir("/app");
  py.FS.mkdir("/app/fitparse");
  for (const f of PROGRAMA) py.FS.writeFile("/app/" + f, await ficheiro("py/" + f));
  for (const f of FITPARSE) py.FS.writeFile("/app/fitparse/" + f, await ficheiro("py/fitparse/" + f));
  py.runPython('import sys; sys.path.insert(0, "/app")');

  // /dados (os passeios) e /cache (passeios já lidos) ficam guardados no browser entre visitas
  for (const pasta of ["/dados", "/cache"]) {
    py.FS.mkdir(pasta);
    py.FS.mount(py.FS.filesystems.IDBFS, {}, pasta);
  }
  await sincronizar(true);
  py.FS.mkdir("/saida");
}

async function executar(m) {
  await iniciar();
  const blobs = m.ficheiros.map((f, i) => ({ name: `${i}/${f.nome}`, data: f.blob }));
  py.FS.mkdir("/entrada");
  py.FS.mount(py.FS.filesystems.WORKERFS, { blobs }, "/entrada");
  try {
    py.globals.set("js_lidos", (vistos, novos) => enviar("lidos", { vistos, novos }));
    py.globals.set("js_leitura", (n, total) => enviar("leitura", { n, total }));
    py.globals.set("js_texto", (t) => enviar("texto", { texto: t }));
    py.globals.set("js_fc_max", m.fcMax || undefined);
    py.globals.set("js_idade", m.idade || undefined);
    py.globals.set("js_forcar", !!m.forcar);
    py.globals.set("js_redefinir", !!m.redefinir);
    const json = await py.runPythonAsync(`
import json, analisar, importar_web
analisar.PROGRESSO = lambda n, total: js_leitura(n, total)
json.dumps(importar_web.executar(lambda v, n: js_lidos(v, n), lambda t: js_texto(t),
                                 fc_max=js_fc_max, idade=js_idade, forcar=js_forcar, redefinir=js_redefinir))
`);
    const resultado = JSON.parse(json);
    await sincronizar(false);
    const ficheiros = {};
    if (resultado.gerado) {
      for (const nome of RESULTADOS) ficheiros[nome] = py.FS.readFile("/saida/" + nome);
    }
    self.postMessage({ tipo: "fim", resultado, ficheiros }, Object.values(ficheiros).map((u) => u.buffer));
  } finally {
    py.FS.unmount("/entrada");
    py.FS.rmdir("/entrada");
  }
}

self.onmessage = async (e) => {
  try {
    if (e.data.tipo === "executar") await executar(e.data);
  } catch (erro) {
    const linhas = String(erro && erro.message || erro).trim().split("\n");
    enviar("erro", { texto: linhas.slice(-4).join("\n") });
  }
};
