"use strict";
// Service worker: (1) serve o relatório e o mapa que o programa gerou no próprio browser, como se fossem
// ficheiros do site (assim as ligações entre eles funcionam); (2) guarda o site e o motor de cálculo
// para a página abrir depressa e funcionar sem internet.
const APP = "app-v1";
const CDN = "cdn-v1";
const RESULTADO = "resultado";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const nome of await caches.keys()) {
      if (nome.startsWith("app-") && nome !== APP) await caches.delete(nome);
    }
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (e) => {
  const pedido = e.request;
  if (pedido.method !== "GET") return;
  const url = new URL(pedido.url);
  if (url.origin === location.origin) {
    e.respondWith(url.pathname.includes("/resultado/") ? resultado(url)
      : url.pathname.includes("/rodas/") ? cachePrimeiro(pedido, APP) // o nome do ficheiro tem a versão: nunca muda
      : redePrimeiro(pedido));
  } else if (url.hostname === "cdn.jsdelivr.net") {
    e.respondWith(cachePrimeiro(pedido, CDN));
  }
});

async function resultado(url) {
  let nome = url.pathname.split("/").pop();
  if (nome === "app.html" && url.searchParams.has("completa")) nome = "relatorio.html"; // "ver versão completa"
  const cache = await caches.open(RESULTADO);
  const r = await cache.match(new URL("resultado/" + nome, self.registration.scope).href);
  return r || new Response("Ainda não há relatório. Volta à página inicial e carrega os teus passeios.",
                           { status: 404, headers: { "Content-Type": "text/plain; charset=utf-8" } });
}

async function redePrimeiro(pedido) {
  const cache = await caches.open(APP);
  try {
    const r = await fetch(pedido);
    if (r.ok) cache.put(pedido, r.clone());
    return r;
  } catch (erro) {
    const guardado = await cache.match(pedido, { ignoreSearch: true });
    if (guardado) return guardado;
    throw erro;
  }
}

async function cachePrimeiro(pedido, nomeCache) {
  const cache = await caches.open(nomeCache);
  const guardado = await cache.match(pedido);
  if (guardado) return guardado;
  const r = await fetch(pedido);
  if (r.ok && (r.type === "cors" || r.type === "basic")) cache.put(pedido, r.clone());
  return r;
}
