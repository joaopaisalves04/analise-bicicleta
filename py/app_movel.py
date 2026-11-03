"""Gera a app para o telemóvel (iPhone, ~390×844): um ecrã de cada vez, com barra de separadores em baixo.

Usa as mesmas secções e cálculos do relatório (relatorio.todas_seccoes); aqui só muda a arrumação e o tamanho.
Ecrãs: Resumo (último passeio, mês, semana, recordes), Mapa (ecrã inteiro, com as voltas habituais),
Evolução (um gráfico de cada vez, escolhido em botões) e Passeios (lista; tocar abre o detalhe).
"""
from datetime import date
from html import escape

import pandas as pd
from plotly.offline import get_plotlyjs_version

import relatorio as R

GRAFICOS = [("forma", "Forma", 320), ("frescura", "Frescura", 420), ("km", "Km por mês", 300),
            ("semanas", "Semanas", 280), ("velocidade", "Velocidade", 320), ("fc", "Coração", 320),
            ("zonas", "Zonas", 380), ("fatores", "Fatores", None), ("voltas", "Voltas", 320)]
TENDENCIA_TXT = {"a subir": "a subir nos últimos 2 meses", "estável": "estável nos últimos 2 meses",
                 "a descer": "a descer nos últimos 2 meses"}
CONFIG = {"displayModeBar": False, "responsive": True, "scrollZoom": False}


def movel(fig, altura, nome=""):
    """Ajusta uma figura do relatório ao ecrã do telemóvel: mais baixa, margens curtas, sem arrastar com o dedo."""
    fig.update_layout(height=altura or fig.layout.height, margin=dict(l=42, r=10, t=34, b=40), font=dict(size=11),
                      dragmode=False, legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom", font=dict(size=11)))
    fig.update_yaxes(title_font_size=11)
    if nome == "frescura":
        fig.update_layout(margin=dict(t=74), legend=dict(y=1.1))
    if nome == "fatores":
        fig.update_layout(margin=dict(l=8, r=12, t=10, b=46))
        fig.update_xaxes(title_text="bpm vs o esperado", title_font_size=11)
    if nome == "detalhe":
        fig.update_layout(margin=dict(l=36, r=8, t=28, b=40))
    # eixo do tempo: um mês sim, outro não, senão os nomes atropelam-se
    for eixo in [k for k in fig.layout if k.startswith("xaxis")]:
        ax = fig.layout[eixo]
        if ax.tickvals is not None and len(ax.tickvals) > 7:
            ax.update(tickvals=ax.tickvals[::2], ticktext=ax.ticktext[::2])
    return fig


def html_fig(fig, div_id):
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id, config=CONFIG)


def delta(valor, tipico, casas, unid):
    if pd.isna(valor) or pd.isna(tipico):
        return ""
    d = valor - tipico
    if abs(d) < 0.5 * 10 ** -casas:
        return '<span class="d">= típico</span>'
    return f'<span class="d">{"▲" if d > 0 else "▼"} {R.num(abs(d), casas)} {unid}</span>'


def dia_curto(d):
    return f"{R.DIAS[d.weekday()][:3].capitalize()}, {d.day} {R.MESES[d.month - 1]}"


# ---------- ecrãs ----------

def ecra_resumo(p, c, s):
    r = p.iloc[-1]
    t = c.median(numeric_only=True)
    ultimo = f"""
<div class="ultimo">
  <div class="selo">Último passeio</div>
  <div class="data">{R.data_longa(r.inicio).capitalize()} · {r.inicio:%H:%M}</div>
  <div class="grande">{R.num(r.km, 1)}<small> km</small></div>
  {delta(r.km, t["km"], 0, "km vs típico")}
  <div class="quatro">
    <div><span>Tempo</span><b>{R.duracao(r.tempo_s)}</b></div>
    <div><span>Vel. no plano</span><b>{R.num(r.vel_plano, 1) if pd.notna(r.vel_plano) else "–"} <small>km/h</small></b>{delta(r.vel_plano, t["vel_plano"], 1, "km/h")}</div>
    <div><span>FC média</span><b>{R.num(r.fc_media) if pd.notna(r.fc_media) else "–"} <small>bpm</small></b>{delta(r.fc_media, t["fc_media"], 0, "bpm")}</div>
    <div><span>Subida</span><b>{R.num(r.subida_m) if pd.notna(r.subida_m) else "–"} <small>m</small></b>{delta(r.subida_m, t["subida_m"], 0, "m")}</div>
  </div>
</div>"""

    hoje = pd.Timestamp(date.today())
    meses = pd.period_range(p["inicio"].min(), p["inicio"].max(), freq="M")
    km_mes = p.groupby(p["inicio"].dt.to_period("M"))["km"].sum().reindex(meses, fill_value=0)
    este = p[p["inicio"].dt.to_period("M") == hoje.to_period("M")]
    media = km_mes[km_mes.index < hoje.to_period("M")].mean()
    sem = R.semanas(p)
    _, _, _, seguidas = R.sequencias(sem["n"] > 0)
    pct = min(100, este["km"].sum() / media * 100) if media > 0 else 0
    media_txt = (f"A tua média nos meses completos é {R.num(media)} km." if pd.notna(media)
                 else "Ainda não tens nenhum mês completo para comparar.")
    f = R.resumo_forma(c)
    fr = R.resumo_frescura(p) if c["fc_media"].notna().any() else None
    efic = ('<div class="cartao"><span>Eficiência</span><b>–</b><em>precisa de FC</em></div>' if f is None else
            f'<button class="cartao ir" data-ir="forma"><span>Eficiência</span><b>{R.num(f["agora"], 1)} <small>m/batimento</small></b>'
            f'<em>{"ainda poucos passeios" if pd.isna(f["pct"]) else ("▲" if f["pct"] >= 0 else "▼") + f" {R.num(abs(f['pct']))}% desde {R.mes_pt(f['desde'])}"}'
            f'<br>{TENDENCIA_TXT.get(f["tendencia"], "")}</em></button>')
    fresc = ('<div class="cartao"><span>Frescura</span><b>–</b><em>precisa de FC</em></div>' if fr is None else
             f'<button class="cartao ir" data-ir="frescura"><span>Frescura</span><b>{fr["estado"]}</b>'
             f'<em>{fr["conselho"].split(":")[0]}</em></button>')
    mes = f"""
<div class="cartao">
  <div class="linha-t"><b>{R.MESES_LONGOS[hoje.month - 1].capitalize()}</b><span>{len(este)} passeio{"" if len(este) == 1 else "s"}</span></div>
  <div class="grande escuro">{R.num(este["km"].sum())}<small> km</small></div>
  <div class="barra" role="img" aria-label="{R.num(pct)}% da média mensal"><i style="width:{pct:.0f}%"></i></div>
  <div class="nota">{media_txt}</div>
</div>
<div class="dois">
  <div class="cartao"><span>Esta semana</span><b>{R.num(sem["km"].iloc[-1])} <small>km</small></b><em>{int(sem["n"].iloc[-1])} passeio{"" if sem["n"].iloc[-1] == 1 else "s"}</em></div>
  <div class="cartao"><span>Sequência</span><b>{seguidas} <small>semanas</small></b><em>seguidas a pedalar</em></div>
</div>
<div class="dois">
  {efic}
  {fresc}
</div>"""

    recordes = s["recordes"][3][0].replace('class="cartoes recordes"', 'class="carrossel"')
    totais = "".join(f'<div><b>{v}</b><span>{leg}</span></div>' for v, leg in [
        (R.num(len(p)), "passeios"), (R.num(p["km"].sum()), "km"),
        (R.num(p["tempo_s"].sum() / 3600), "horas"), (R.num(p["subida_m"].sum()), "m de subida")])
    return f"""
<header class="titulo"><p>{R.data_longa(hoje).capitalize()}</p><h1>Resumo</h1></header>
<div class="miolo">{ultimo}{mes}
<h2 class="secao">Recordes</h2>{recordes}
<h2 class="secao">Desde {p["inicio"].min():%d/%m/%Y}</h2><div class="cartao totais">{totais}</div>
<p class="rodape"><a href="?completa">Abrir a versão completa</a><br>Atualizado a {date.today():%d/%m/%Y}</p>
</div>"""


def ecra_mapa(voltas):
    chips = '<button class="chip ativo" data-volta="0">Todas</button>' + "".join(
        f'<button class="chip" data-volta="{v["n"]}"><i style="background:{cor}"></i>{escape(v["nome"].split(": ")[1])}</button>'
        for v, cor in zip(voltas, R.CORES_VOLTAS))
    return f"""
<header class="titulo compacto"><h1>Mapa</h1></header>
<div class="chips" id="chips-mapa">{chips}</div>
<iframe id="mapa" data-src="mapa_calor.html" title="Mapa dos percursos"></iframe>"""


def ecra_evolucao(s):
    chips = "".join(f'<button class="chip{" ativo" if i == 0 else ""}" data-graf="{k}">{nome}</button>'
                    for i, (k, nome, _) in enumerate(GRAFICOS))
    cartoes = []
    for i, (k, _, altura) in enumerate(GRAFICOS):
        pergunta, resposta, como_ler, partes = s[k]
        corpo = "".join(p if isinstance(p, str) else html_fig(movel(p, altura, k), f"m_{k}_{j}")
                        for j, p in enumerate(partes))
        ler = f'<details class="ler"><summary>Como ler</summary>{escape(como_ler)}</details>' if como_ler else ""
        cartoes.append(f'<section class="cartao graf" id="graf-{k}"{"" if i == 0 else " hidden"}>'
                       f'<h3>{escape(pergunta)}</h3><p class="resposta">{resposta}</p>{corpo}{ler}</section>')
    return f"""
<header class="titulo"><h1>Evolução</h1></header>
<div class="chips fixos" id="chips-graf">{chips}</div>
<div class="miolo">{"".join(cartoes)}</div>"""


def ecra_passeios(p, c, s, voltas):
    nomes = {v["n"]: f"Volta {v['n']}" for v in voltas}
    ordem = {pid: i for i, pid in enumerate(c.sort_values("inicio", ascending=False)["id"])}  # = ordem do detalhe
    grupos = []
    q = p.sort_values("inicio", ascending=False)
    for mes, g in q.groupby(q["inicio"].dt.to_period("M"), sort=False):
        linhas = []
        for r in g.itertuples():
            i = ordem.get(r.id)
            vel = f" · {R.num(r.vel_media, 1)} km/h" if pd.notna(r.vel_media) else ""
            volta = f' · <em>{nomes[r.volta]}</em>' if pd.notna(r.volta) and r.volta in nomes else ""
            dados = {"titulo": R.data_longa(r.inicio).capitalize(), "hora": f"{r.inicio:%H:%M}",
                     "km": R.num(r.km, 1), "tempo": R.duracao(r.tempo_s),
                     "vel": R.num(r.vel_media, 1) if pd.notna(r.vel_media) else "–",
                     "plano": R.num(r.vel_plano, 1) if pd.notna(r.vel_plano) else "–",
                     "subida": R.num(r.subida_m) if pd.notna(r.subida_m) else "–",
                     "fc": R.num(r.fc_media) if pd.notna(r.fc_media) else "–",
                     "fcmax": R.num(r.fc_max) if pd.notna(r.fc_max) else "–",
                     "temp": f"{R.num(r.temp)} °C" if pd.notna(r.temp) else "–",
                     "sensor": "relógio" if r.fonte_fc.startswith("relógio") else "cinta"}
            attrs = " ".join(f'data-{k}="{escape(v)}"' for k, v in dados.items())
            seta = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>' if i is not None else ""
            linhas.append(
                f'<button class="passeio" {"data-i=" + chr(34) + str(i) + chr(34) if i is not None else "disabled"} {attrs}>'
                f'<div><b>{dia_curto(r.inicio)}</b><span>{R.duracao(r.tempo_s)}{vel}{volta}</span></div>'
                f'<strong>{R.num(r.km, 1)}<small> km</small></strong>{seta}</button>')
        grupos.append(f'<h2 class="secao mes"><span>{R.MESES_LONGOS[mes.month - 1].capitalize()} {mes.year}</span>'
                      f'<span>{R.num(g["km"].sum())} km</span></h2><div class="lista">{"".join(linhas)}</div>')

    fig = next(x for x in s["detalhe"][3] if not isinstance(x, str))
    fig.update_layout(meta=None)
    det = html_fig(movel(fig, 470, "detalhe"), "detalhe")
    campos = [("km", "km"), ("tempo", "tempo"), ("vel", "km/h média"), ("plano", "km/h no plano"),
              ("subida", "subida (m)"), ("fc", "FC média"), ("fcmax", "FC máxima"), ("temp", "temperatura")]
    grelha = "".join(f'<div><span>{leg}</span><b data-campo="{k}"></b></div>' for k, leg in campos)
    return f"""
<header class="titulo"><p>{len(p)} passeios · {R.num(p["km"].sum())} km</p><h1>Passeios</h1></header>
<div class="miolo">{"".join(grupos)}</div>
<div id="folha" aria-hidden="true">
  <div class="barra-topo"><button id="voltar"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 6-6 6 6 6"/></svg>Passeios</button></div>
  <div class="folha-miolo">
    <p class="cinza" data-campo="hora"></p><h1 data-campo="titulo"></h1>
    <div class="cartao grelha">{grelha}</div>
    <div class="cartao">{det}<p class="nota">FC do <span data-campo="sensor"></span>. Toca no gráfico para ver os valores de cada minuto.</p></div>
  </div>
</div>"""


ABAS = [("resumo", "Resumo", "resumo"), ("mapa", "Mapa", "percursos"), ("evolucao", "Evolução", "evolucao"),
        ("passeios", "Passeios", "passeios")]

CSS = """
:root { --fundo:#f2f2f7; --cartao:#fff; --tinta:#0b0b0b; --tinta2:#5f5f66; --linha:#e3e3e8; --azul:#2a78d6;
        --noite:#0b1f3a; --topo:env(safe-area-inset-top); --baixo:env(safe-area-inset-bottom); --barra:56px; }
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
html, body { margin:0; background:var(--fundo); color:var(--tinta); }
body { font:16px/1.4 -apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,"Segoe UI",Roboto,sans-serif;
       -webkit-font-smoothing:antialiased; padding-bottom:calc(var(--barra) + var(--baixo) + 16px);
       -webkit-text-size-adjust:100%; overscroll-behavior-y:none; }
button { font:inherit; color:inherit; }
.ecra[hidden] { display:none; }
.titulo { padding:calc(var(--topo) + 14px) 18px 6px; }
.titulo h1 { font-size:34px; line-height:1.1; font-weight:750; letter-spacing:-.025em; margin:0; }
.titulo p { margin:0 0 2px; color:var(--tinta2); font-size:14px; font-weight:560; }
.titulo.compacto { padding-bottom:4px; }
.titulo.compacto h1 { font-size:28px; }
.miolo { padding:6px 14px 0; }
.cartao { background:var(--cartao); border-radius:16px; padding:14px 16px; margin-bottom:12px; }
.secao { font-size:20px; font-weight:700; letter-spacing:-.01em; margin:22px 4px 10px; }
.secao.mes { display:flex; justify-content:space-between; align-items:baseline; font-size:15px; font-weight:650;
             color:var(--tinta2); text-transform:uppercase; letter-spacing:.03em; margin:20px 6px 8px; }
small { font-size:.55em; font-weight:600; color:inherit; opacity:.7; }
.nota { color:var(--tinta2); font-size:13px; margin:8px 0 0; }
.cinza { color:var(--tinta2); }

/* último passeio */
.ultimo { color:#fff; border-radius:20px; padding:16px 16px 14px; margin-bottom:12px;
          background:radial-gradient(130% 150% at 100% 0%, #2a78d6 0%, #15407a 50%, #0b1f3a 100%); }
.ultimo .selo { display:inline-block; font-size:11px; font-weight:700; letter-spacing:.07em; text-transform:uppercase;
                background:rgba(255,255,255,.16); padding:3px 9px; border-radius:99px; }
.ultimo .data { margin-top:8px; font-size:15px; opacity:.85; }
.grande { font-size:46px; font-weight:780; letter-spacing:-.03em; line-height:1.05; font-variant-numeric:tabular-nums; }
.grande small { font-size:.42em; }
.ultimo > .d { font-size:13px; opacity:.8; }
.quatro { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:12px; }
.quatro div { background:rgba(255,255,255,.1); border-radius:12px; padding:9px 11px; }
.quatro span { display:block; font-size:12px; opacity:.78; }
.quatro b { font-size:19px; font-variant-numeric:tabular-nums; }
.quatro .d { display:block; font-size:12px; opacity:.78; }
.linha-t { display:flex; justify-content:space-between; color:var(--tinta2); font-size:14px; }
.linha-t b { color:var(--tinta); font-size:16px; }
.grande.escuro { font-size:38px; margin-top:2px; }
.barra { height:8px; border-radius:99px; background:#e8eef8; overflow:hidden; margin-top:8px; }
.barra i { display:block; height:100%; border-radius:99px; background:var(--azul); }
.dois { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.dois .cartao span { display:block; color:var(--tinta2); font-size:13px; font-weight:560; }
.dois .cartao b { font-size:26px; font-weight:740; font-variant-numeric:tabular-nums; }
.dois .cartao em { display:block; font-style:normal; color:var(--tinta2); font-size:13px; }
.carrossel { display:flex; gap:10px; overflow-x:auto; scroll-snap-type:x mandatory; margin:0 -14px; padding:0 14px 4px;
             scrollbar-width:none; }
.carrossel::-webkit-scrollbar { display:none; }
.carrossel .cartao { flex:0 0 46%; scroll-snap-align:start; margin:0; padding:12px 14px; }
.carrossel .leg { color:var(--tinta2); font-size:13px; font-weight:560; min-height:2.6em; }
.carrossel .valor { font-size:22px; font-weight:740; letter-spacing:-.01em; }
.carrossel .quando { color:#8a8a90; font-size:12px; }
.cartao.ir { border:0; width:100%; text-align:left; cursor:pointer; display:block; }
.cartao.ir:active { background:#ececf0; }
.totais { display:grid; grid-template-columns:1fr 1fr; gap:12px 8px; }
.totais b { display:block; font-size:22px; font-weight:740; font-variant-numeric:tabular-nums; }
.totais span { color:var(--tinta2); font-size:13px; }
.rodape { text-align:center; color:#8a8a90; font-size:13px; margin:22px 0 8px; line-height:1.8; }
.rodape a { color:var(--azul); text-decoration:none; font-weight:560; }

/* botões de escolha (chips) */
.chips { display:flex; gap:8px; overflow-x:auto; padding:6px 14px 10px; scrollbar-width:none; }
.chips::-webkit-scrollbar { display:none; }
.chips.fixos { position:sticky; top:0; z-index:5; background:rgba(242,242,247,.92); padding-top:calc(var(--topo) * 0 + 8px);
               backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); }
.chip { flex:none; border:0; background:var(--cartao); padding:8px 14px; border-radius:99px; font-size:14px; font-weight:600;
        color:var(--tinta2); display:flex; align-items:center; gap:7px; white-space:nowrap; }
.chip i { width:9px; height:9px; border-radius:50%; }
.chip.ativo { background:var(--noite); color:#fff; }

/* gráficos */
.graf h3 { font-size:18px; line-height:1.25; margin:0 0 6px; letter-spacing:-.01em; }
.resposta { font-size:15px; margin:0 0 6px; }
.resposta b { font-weight:680; }
.graf .cartoes { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:8px 0; }
.graf .cartao { background:var(--fundo); padding:10px 12px; margin:0; }
.graf .cartao .leg { font-size:12px; color:var(--tinta2); }
.graf .cartao .valor { font-size:17px; font-weight:700; }
.graf .cartao .quando { font-size:11px; color:#8a8a90; }
.tabela { overflow-x:auto; margin:8px -4px; }
table { border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums; }
th, td { padding:6px; text-align:right; border-bottom:1px solid var(--linha); white-space:nowrap; }
th { color:var(--tinta2); font-weight:600; font-size:12px; }
th:first-child, td:first-child { text-align:left; }
td.txt, th.txt { text-align:left; white-space:normal; min-width:200px; color:var(--tinta2); }
.ponto { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; }
td a { color:var(--azul); text-decoration:none; font-weight:600; }
h3 + .resposta + .cartoes { margin-top:4px; }
details.ler { font-size:13px; color:var(--tinta2); margin-top:4px; }
details.ler summary { color:var(--azul); font-weight:600; padding:6px 0; list-style:none; }
details.ler summary::-webkit-details-marker { display:none; }

/* mapa: ocupa o espaço todo entre o título e a barra de baixo */
#ecra-mapa:not([hidden]) { position:fixed; inset:0 0 calc(var(--barra) + var(--baixo)) 0; display:flex; flex-direction:column; }
#ecra-mapa .chips { padding-bottom:8px; }
#mapa { flex:1; width:100%; border:0; background:#e9e9ee; }

/* lista de passeios */
.lista { background:var(--cartao); border-radius:16px; overflow:hidden; }
.passeio { width:100%; display:flex; align-items:center; gap:10px; border:0; background:none; text-align:left;
           padding:11px 12px 11px 16px; border-bottom:1px solid var(--linha); }
.passeio:last-child { border-bottom:0; }
.passeio:active { background:#ececf0; }
.passeio div { flex:1; min-width:0; }
.passeio b { display:block; font-size:16px; font-weight:600; }
.passeio span { display:block; color:var(--tinta2); font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.passeio em { font-style:normal; color:var(--azul); }
.passeio strong { font-size:18px; font-weight:700; font-variant-numeric:tabular-nums; }
.passeio svg, #voltar svg { width:18px; height:18px; fill:none; stroke:#b4b4bb; stroke-width:2.4; stroke-linecap:round; stroke-linejoin:round; }
.passeio[disabled] { opacity:.55; }

/* detalhe de um passeio: folha que entra da direita */
#folha { position:fixed; inset:0; z-index:30; background:var(--fundo); overflow-y:auto; transform:translateX(100%);
         transition:transform .28s cubic-bezier(.2,.8,.2,1); visibility:hidden; padding-bottom:calc(var(--baixo) + 20px); }
#folha.aberta { transform:none; visibility:visible; }
.barra-topo { position:sticky; top:0; z-index:2; padding:calc(var(--topo) + 6px) 8px 6px; background:rgba(242,242,247,.92);
              backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); }
#voltar { display:flex; align-items:center; gap:2px; border:0; background:none; color:var(--azul); font-size:17px; padding:6px; }
#voltar svg { stroke:var(--azul); width:22px; height:22px; }
.folha-miolo { padding:0 14px; }
.folha-miolo h1 { font-size:28px; margin:0 0 12px; letter-spacing:-.02em; }
.folha-miolo .cinza { margin:4px 0 0; font-size:14px; }
.grelha { display:grid; grid-template-columns:1fr 1fr; gap:12px 8px; }
.grelha span { display:block; color:var(--tinta2); font-size:12px; }
.grelha b { font-size:20px; font-weight:720; font-variant-numeric:tabular-nums; }

/* barra de separadores */
nav { position:fixed; left:0; right:0; bottom:0; z-index:20; display:flex; justify-content:space-around;
      padding:6px 4px var(--baixo); height:calc(var(--barra) + var(--baixo));
      background:rgba(249,249,251,.9); backdrop-filter:saturate(1.6) blur(18px); -webkit-backdrop-filter:saturate(1.6) blur(18px);
      border-top:.5px solid rgba(0,0,0,.18); }
nav button { flex:1; border:0; background:none; display:flex; flex-direction:column; align-items:center; gap:2px;
             font-size:10.5px; font-weight:560; color:#8a8a90; }
nav svg { width:25px; height:25px; }
nav button[aria-current="page"] { color:var(--azul); }

/* acabamento visual: cor, relevo e movimento suave (os números e gráficos não mudam) */
.cartao, .lista { box-shadow:0 1px 2px rgba(16,24,40,.04), 0 6px 18px rgba(16,24,40,.06); border-radius:18px; }
.ultimo { box-shadow:0 10px 28px rgba(21,64,122,.35);
          background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 760 260' fill='none'%3E%3Cpath d='M0 200C60 190 90 120 150 128S250 205 310 170 400 70 470 90 580 190 640 120 720 60 760 70' stroke='%237fe0b8' stroke-opacity='.6' stroke-width='4' stroke-linecap='round'/%3E%3Ccircle cx='470' cy='90' r='7' fill='white' fill-opacity='.9'/%3E%3C/svg%3E") no-repeat right 10px top 66px/54% auto,
                     radial-gradient(60% 70% at 0% 110%, rgba(27,175,122,.35), transparent 70%),
                     radial-gradient(130% 150% at 100% 0%, #2a78d6 0%, #15407a 50%, #0b1f3a 100%); }
.ultimo .selo { background:rgba(127,224,184,.22); color:#c9f5e3; }
.quatro div { background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.14); }
.barra i { background:linear-gradient(90deg,#2a78d6,#1baf7a); }
.chip.ativo { background:linear-gradient(135deg,#0e2a4d,#1d5fb4); box-shadow:0 4px 12px rgba(29,95,180,.3); }
.dois .cartao span::before { content:""; display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:7px;
                             vertical-align:.08em; background:var(--pt,#2a78d6); }
.dois .cartao:nth-child(1) { --pt:#eb6834; } .dois .cartao:nth-child(2) { --pt:#eda100; }
.cartao.ir[data-ir="forma"] { --pt:#2a78d6; } .cartao.ir[data-ir="frescura"] { --pt:#1baf7a; }
.carrossel .cartao { border-top:3px solid var(--pt,#2a78d6); }
.carrossel .cartao:nth-child(4n+2) { --pt:#1baf7a; } .carrossel .cartao:nth-child(4n+3) { --pt:#eb6834; }
.carrossel .cartao:nth-child(4n+4) { --pt:#eda100; }
.cartao.ir, .passeio, .chip { transition:transform .15s, background .15s; }
.cartao.ir:active, .passeio:active { transform:scale(.985); }
nav button { position:relative; }
nav button[aria-current="page"]::before { content:""; position:absolute; top:-6px; width:30px; height:3px; border-radius:0 0 4px 4px; background:var(--azul); }
@keyframes entra { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:none; } }
@media (prefers-reduced-motion: no-preference) { .ecra:not([hidden]) .miolo, .ecra:not([hidden]) .titulo { animation:entra .32s both; } }
"""

JS = """
(function () {
  var atual = null, posicao = {};
  var botoes = document.querySelectorAll("nav button");
  function redimensionar(onde) {
    onde.querySelectorAll(".js-plotly-plot").forEach(function (g) {
      if (g.offsetParent !== null) Plotly.Plots.resize(g);
    });
  }
  function abrir(nome) {
    if (!document.getElementById("ecra-" + nome)) nome = "resumo";
    if (atual) posicao[atual] = window.scrollY;
    atual = nome;
    document.querySelectorAll(".ecra").forEach(function (e) { e.hidden = e.id !== "ecra-" + nome; });
    botoes.forEach(function (b) { b.setAttribute("aria-current", b.dataset.ecra === nome ? "page" : "false"); });
    var ecra = document.getElementById("ecra-" + nome);
    ecra.querySelectorAll("iframe[data-src]").forEach(function (f) {
      if (!f.getAttribute("src")) f.setAttribute("src", f.dataset.src);
    });
    window.scrollTo(0, posicao[nome] || 0);
    redimensionar(ecra);
    history.replaceState(null, "", location.pathname + location.search + "#" + nome);
  }
  botoes.forEach(function (b) { b.addEventListener("click", function () { abrir(b.dataset.ecra); }); });

  // mapa: escolher a volta
  function verVolta(n) {
    document.querySelectorAll("#chips-mapa .chip").forEach(function (c) { c.classList.toggle("ativo", c.dataset.volta == n); });
    var f = document.getElementById("mapa");
    f.setAttribute("src", "mapa_calor.html#volta=" + n);
  }
  document.querySelectorAll("#chips-mapa .chip").forEach(function (c) {
    c.addEventListener("click", function () { verVolta(c.dataset.volta); });
  });
  document.querySelectorAll("a[data-volta]").forEach(function (a) {   // "ver no mapa" na tabela das voltas
    a.addEventListener("click", function (e) { e.preventDefault(); abrir("mapa"); verVolta(a.dataset.volta); });
  });

  // evolução: um gráfico de cada vez
  document.querySelectorAll("#chips-graf .chip").forEach(function (c) {
    c.addEventListener("click", function () {
      document.querySelectorAll("#chips-graf .chip").forEach(function (x) { x.classList.toggle("ativo", x === c); });
      document.querySelectorAll(".graf").forEach(function (g) { g.hidden = g.id !== "graf-" + c.dataset.graf; });
      c.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
      var g = document.getElementById("graf-" + c.dataset.graf);
      redimensionar(g);
      var topo = document.getElementById("chips-graf").offsetTop;
      if (window.scrollY > topo) window.scrollTo(0, topo);
    });
  });

  // cartões do Resumo que levam a um gráfico da Evolução
  document.querySelectorAll("[data-ir]").forEach(function (b) {
    b.addEventListener("click", function () {
      abrir("evolucao");
      document.querySelector('#chips-graf [data-graf="' + b.dataset.ir + '"]').click();
    });
  });

  // passeios: tocar abre o detalhe
  var folha = document.getElementById("folha"), n = document.querySelectorAll(".passeio[data-i]").length;
  function fechar() { folha.classList.remove("aberta"); folha.setAttribute("aria-hidden", "true"); }
  document.querySelectorAll(".passeio[data-i]").forEach(function (b) {
    b.addEventListener("click", function () {
      var i = +b.dataset.i, vis = [];
      for (var k = 0; k < n; k++) vis.push(k === i, k === i, k === i);
      folha.querySelectorAll("[data-campo]").forEach(function (el) { el.textContent = b.dataset[el.dataset.campo]; });
      folha.scrollTop = 0;
      folha.classList.add("aberta"); folha.setAttribute("aria-hidden", "false");
      Plotly.restyle("detalhe", { visible: vis }).then(function () { Plotly.Plots.resize("detalhe"); });
      history.pushState({ folha: 1 }, "");
    });
  });
  document.getElementById("voltar").addEventListener("click", function () { history.back(); });
  window.addEventListener("popstate", fechar);

  abrir(location.hash.slice(1) || "resumo");
})();
"""


def gerar(p, series, limites, fc_max, voltas, destino):
    p, c = R.preparar(p)
    s = R.todas_seccoes(p, c, series, limites, fc_max, voltas)
    ecras = {"resumo": ecra_resumo(p, c, s), "mapa": ecra_mapa(voltas), "evolucao": ecra_evolucao(s),
             "passeios": ecra_passeios(p, c, s, voltas)}
    corpo = "".join(f'<div class="ecra" id="ecra-{k}">{v}</div>' for k, v in ecras.items())
    nav = "".join(f'<button type="button" data-ecra="{k}">{R.svg(icone)}<span>{nome}</span></button>'
                  for k, nome, icone in ABAS)
    pagina = f"""<!doctype html>
<html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light"><meta name="theme-color" content="#f2f2f7">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default"><meta name="apple-mobile-web-app-title" content="Passeios">
<title>Os meus passeios</title>
<script src="https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js"></script>
<style>{CSS}</style></head><body>
{corpo}
<nav aria-label="Ecrãs">{nav}</nav>
<script>{JS}</script>
</body></html>"""
    destino.write_text(pagina, encoding="utf-8")
