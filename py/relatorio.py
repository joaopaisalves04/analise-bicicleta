"""Gera saida/relatorio.html: cada gráfico responde a uma pergunta e diz a resposta por escrito."""
from datetime import date
from html import escape

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs_version
from plotly.subplots import make_subplots

# Paleta validada (scripts/validate_palette.js): 3 categorias + rampa ordinal azul para as zonas
AZUL, LARANJA, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
TINTA, TINTA2, APAGADO = "#0b0b0b", "#52514e", "#898781"
GRELHA, EIXO, FUNDO = "#e8e7e1", "#c3c2b7", "#ffffff"   # FUNDO = fundo dos cartões (e do anel à volta dos pontos)
CORES_ZONAS = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]
CORES_VOLTAS = [AZUL, LARANJA, AQUA, "#eda100", "#e87ba4"]  # ordem da paleta: pares vizinhos validados
NOMES_ZONAS = ["Z1 · recuperação", "Z2 · base aeróbica", "Z3 · ritmo", "Z4 · limiar", "Z5 · máximo"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
                "outubro", "novembro", "dezembro"]
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
N_MAX_COMPARAR = 15           # nº de passeios no início e no fim usados para "antes vs agora"
N_MIN_COMPARAR = 5            # com menos de 2× isto passeios não há "antes vs agora"
N_COMPARAR = N_MAX_COMPARAR   # preparar() baixa-o para metade dos passeios quando há menos de 30
ORIGEM_ZONAS = None           # analisar.py: None se as zonas vêm da Garmin, senão como foram calculadas
CALOR, FRIO = 25, 12          # °C a partir dos quais um passeio conta como de calor / de frio
PARAGEM = 10                  # dias sem pedalar que contam como paragem
EPISODIO = 4                  # bpm acima do esperado (mediana de 5 passeios seguidos) para assinalar um período
AMOSTRA_S = 10                # resolução (s) do gráfico de detalhe por passeio
FC_REPOUSO = 55               # bpm; analisar.py troca pelo valor que está na Garmin (zonas_fc.json)
TENDENCIA_DIAS = 60           # janela para dizer se a eficiência está a subir, estável ou a descer
ESTAVEL_PCT = 3               # variação (%) abaixo da qual a eficiência conta como estável
TAU_FORMA, TAU_FADIGA = 42, 7  # dias; médias exponenciais da carga (como o Fitness & Freshness do Strava)
FATOR_MIN = 5                 # passeios mínimos de cada lado para avaliar um fator
ESTADOS = [                   # frescura ÷ forma: acima do limite → estado
    (0.15, "Fresco", "Estás descansado: bom momento para um passeio forte ou longo."),
    (-0.10, "Equilibrado", "O treino e o descanso estão equilibrados."),
    (-0.30, "A carregar", "Estás a treinar mais do que o habitual: é assim que a forma sobe, mas sem exagerar."),
    (-np.inf, "Cansado", "Muita carga recente: um ou dois dias leves ou de descanso ajudam a recuperar."),
]


def mes_pt(d):
    """'out 26' a partir de uma data ou período (o strftime dá os meses em inglês)."""
    return f"{MESES[d.month - 1]} {d.year % 100:02d}"


def num(x, casas=0):
    """Número à portuguesa: 3 982 · 25,7."""
    return f"{x:,.{casas}f}".replace(",", " ").replace(".", ",")


def estilo(fig, altura=360):
    fig.update_layout(
        template="simple_white", height=altura, margin=dict(l=60, r=20, t=40, b=50),
        paper_bgcolor=FUNDO, plot_bgcolor=FUNDO, separators=", ",
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=TINTA2, size=13),
        hoverlabel=dict(bgcolor="white", font_color=TINTA, bordercolor=EIXO),
        legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom", title_text=""),
    )
    fig.update_xaxes(showgrid=False, linecolor=EIXO, tickcolor=EIXO)
    fig.update_yaxes(showgrid=True, gridcolor=GRELHA, linecolor=EIXO, tickcolor=EIXO, zeroline=False)
    return fig


def eixo_meses(fig, p, **kw):
    inicios = pd.date_range(p["inicio"].min().to_period("M").start_time, p["inicio"].max(), freq="MS")
    fig.update_xaxes(tickvals=inicios, ticktext=[mes_pt(d) for d in inicios], **kw)


def mediana_mensal(p, col):
    g = p.groupby(p["inicio"].dt.to_period("M"))[col].median()
    return [per.start_time + pd.Timedelta(days=14) for per in g.index], g.values


def dica(p):
    return p["inicio"].dt.strftime("%d/%m/%Y") + " · " + p["km"].round(0).astype(int).astype(str) + " km"


# ---------- secções ----------

def sec_km(todos):
    meses = pd.period_range(todos["inicio"].min(), todos["inicio"].max(), freq="M")
    g = todos.groupby(todos["inicio"].dt.to_period("M"))
    km = g["km"].sum().reindex(meses, fill_value=0)
    n = g.size().reindex(meses, fill_value=0)
    fig = go.Figure(go.Bar(
        x=[mes_pt(m) for m in meses], y=km.values, marker_color=AZUL, marker_cornerradius=4,
        text=[num(v) for v in km.values], textposition="outside", textfont_color=TINTA2, cliponaxis=False,
        customdata=n.values, hovertemplate="%{x}: %{y:.0f} km em %{customdata} passeios<extra></extra>",
    ))
    estilo(fig).update_yaxes(title_text="km no mês")
    melhor = km.idxmax()
    resposta = (f"O teu melhor mês foi <b>{mes_pt(melhor)}</b>, com <b>{num(km.max())} km</b> em {n[melhor]} passeios. "
                f"Em média fizeste <b>{num(km.mean())} km por mês</b>.")
    if meses[-1] == pd.Period(date.today(), "M"):
        resposta += f" {mes_pt(meses[-1]).split()[0].capitalize()} ainda não acabou."
    return ("Quantos quilómetros fiz por mês?", resposta,
            "Cada barra é um mês. O número por cima é o total de km; passa o rato para ver quantos passeios foram.", [fig])


def duracao(segundos):
    h, m = divmod(int(round(segundos / 60)), 60)
    return f"{h} h {m:02d} min"


def semanas(p):
    """Km e nº de passeios por semana (segunda a domingo), até à semana atual, com as semanas sem passeios a 0."""
    sem = p["inicio"].dt.to_period("W-SUN")
    todas = pd.period_range(sem.min(), max(sem.max(), pd.Period(date.today(), "W-SUN")), freq="W-SUN")
    g = p.groupby(sem)
    return pd.DataFrame({"km": g["km"].sum(), "n": g.size()}).reindex(todas, fill_value=0)


def sequencias(ativas):
    """(maior, início da maior, fim da maior, atual) em semanas seguidas com pelo menos um passeio.

    A semana atual ainda está a decorrer: sem passeio não quebra a sequência, só não conta."""
    maior, ini_maior, fim_maior, corrida, ini = 0, None, None, 0, None
    for semana, ativa in ativas.items():
        if ativa:
            ini = semana if corrida == 0 else ini
            corrida += 1
            if corrida > maior:
                maior, ini_maior, fim_maior = corrida, ini, semana
        else:
            corrida = 0
    atual = corrida
    if atual == 0 and len(ativas) >= 2 and not ativas.iloc[-1]:  # semana atual ainda sem passeio
        atual = sequencias(ativas.iloc[:-1])[3]
    return maior, ini_maior, fim_maior, atual


def sec_recordes(p, c):
    s = semanas(p)
    meses = p.groupby(p["inicio"].dt.to_period("M"))["km"].sum()
    maior, ini, fim, _ = sequencias(s["n"] > 0)
    rapido = c[c["km_plano"] >= 20].nlargest(1, "vel_plano").iloc[0]  # ≥20 km de plano: nada de sprints curtos
    longo, subida, tempo = p.loc[p["km"].idxmax()], p.loc[p["subida_m"].idxmax()], p.loc[p["tempo_s"].idxmax()]
    sem_top = s["km"].idxmax()
    cartoes_rec = "".join(cartao_recorde(*x) for x in [
        ("Passeio mais longo", f"{num(longo.km, 1)} km", f"{longo.inicio:%d/%m/%Y}"),
        ("Mais subida num passeio", f"{num(subida.subida_m)} m", f"{subida.inicio:%d/%m/%Y} · {num(subida.km)} km"),
        ("Mais tempo a pedalar", duracao(tempo.tempo_s), f"{tempo.inicio:%d/%m/%Y}"),
        ("Mais rápido no plano", f"{num(rapido.vel_plano, 1)} km/h", f"{rapido.inicio:%d/%m/%Y} · {num(rapido.km)} km"),
        ("Melhor semana", f"{num(s['km'].max())} km", f"semana de {sem_top.start_time:%d/%m/%Y} · {s.loc[sem_top, 'n']} passeios"),
        ("Melhor mês", f"{num(meses.max())} km", mes_pt(meses.idxmax())),
        ("Mais semanas seguidas", f"{maior} semanas", f"{ini.start_time:%d/%m} a {fim.end_time:%d/%m/%Y}"),
    ])
    return ("Quais são os meus recordes?", "Os teus melhores registos desde que tens dados.",
            "“Mais rápido no plano” só conta passeios com pelo menos 20 km planos, para não ganhar um passeio curto "
            "feito a fundo. As semanas vão de segunda a domingo.",
            [f'<div class="cartoes recordes">{cartoes_rec}</div>'])


def sec_semanas(p):
    s = semanas(p)
    ativas = s["n"] > 0
    maior, _, _, atual = sequencias(ativas)
    x = [per.start_time for per in s.index]
    fig = go.Figure(go.Bar(
        x=x, y=s["km"], marker_color=AZUL, marker_cornerradius=3,
        customdata=list(zip([per.start_time.strftime("%d/%m/%Y") for per in s.index], s["n"])),
        hovertemplate="semana de %{customdata[0]}<br>%{customdata[1]} passeios · %{y:.0f} km<extra></extra>"))
    estilo(fig, 320).update_layout(bargap=0.15)
    fig.update_yaxes(title_text="km na semana")
    eixo_meses(fig, p)
    recentes = s.iloc[-13:]  # últimas 13 semanas ≈ 3 meses
    resposta = (f"Pedalaste em <b>{int(ativas.sum())} de {len(s)} semanas</b>. A tua maior sequência foi de "
                f"<b>{maior} semanas seguidas</b> e a atual vai em <b>{atual}</b>. Nos últimos 3 meses fizeste em média "
                f"<b>{num(recentes['km'].mean())} km</b> e <b>{num(recentes['n'].mean(), 1)} passeios por semana</b>.")
    return ("Pedalo com regularidade?", resposta,
            "Cada barra é uma semana (segunda a domingo); as falhas são semanas sem passeios. "
            "A última barra é a semana atual, que ainda não acabou.", [fig])


def minimos_quadrados(y, X):
    X = np.column_stack([np.ones(len(X))] + [X[c] for c in X.columns])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return X @ coef


def correcao_cinta(c):
    """bpm que a cinta marca a mais do que o relógio, à mesma velocidade e forma (coeficiente de uma regressão)."""
    d = c.dropna(subset=["fc_media", "vel_plano"])
    if min((d["sensor"] == "cinta").sum(), (d["sensor"] != "cinta").sum()) < FATOR_MIN:
        return 0.0  # só um sensor, ou poucos passeios de um deles: não dá para medir a diferença
    X = np.column_stack([np.ones(len(d)), d["vel_plano"], np.log1p(d["km_acum"]), (d["sensor"] == "cinta") * 1.0])
    coef, *_ = np.linalg.lstsq(X, d["fc_media"].to_numpy(), rcond=None)
    return coef[3]


def eficiencia(c):
    """Metros percorridos no plano por cada batimento acima da FC de repouso (FC da cinta corrigida para o relógio).

    km/h → m/min (×1000/60) a dividir por batimentos/min acima do repouso.
    """
    d = c.dropna(subset=["fc_media", "vel_plano"]).copy()
    desvio = correcao_cinta(c)
    fc = d["fc_media"] - np.where(d["sensor"] == "cinta", desvio, 0)
    d["efic"] = d["vel_plano"] * 1000 / 60 / (fc - FC_REPOUSO)
    return d, desvio


def resumo_forma(c):
    d, desvio = eficiencia(c)
    if d.empty:
        return None  # nenhum passeio com FC e velocidade no plano
    antes, agora = d["efic"].head(N_COMPARAR).median(), d["efic"].tail(max(N_COMPARAR, N_MIN_COMPARAR)).median()
    fim = d["inicio"].max()
    rec = d[d["inicio"] > fim - pd.Timedelta(days=TENDENCIA_DIAS)]
    ant = d[(d["inicio"] <= fim - pd.Timedelta(days=TENDENCIA_DIAS))
            & (d["inicio"] > fim - pd.Timedelta(days=2 * TENDENCIA_DIAS))]
    var = (rec["efic"].median() / ant["efic"].median() - 1) * 100 if len(rec) >= 4 and len(ant) >= 4 else np.nan
    tendencia = ("sem dados" if pd.isna(var) else "a subir" if var >= ESTAVEL_PCT
                 else "a descer" if var <= -ESTAVEL_PCT else "estável")
    if N_COMPARAR < N_MIN_COMPARAR:
        antes = np.nan
    return dict(d=d, desvio=desvio, antes=antes, agora=agora, pct=(agora / antes - 1) * 100, var=var,
                tendencia=tendencia, desde=d["inicio"].iloc[0])


def sem_fc(pergunta):
    return (pergunta, "Os teus passeios não têm frequência cardíaca (FC). Esta parte aparece quando pedalares com "
            "uma cinta no peito ou com um relógio que meça a FC no pulso.", "", [])


def sec_forma(c):
    f = resumo_forma(c)
    if f is None:
        return sem_fc("Estou em melhor forma?")
    d = f["d"]
    sinal = "+" if f["pct"] >= 0 else "−"
    if pd.isna(f["pct"]):
        resposta = (f"Cada batimento acima do repouso leva-te <b>{num(f['agora'], 1)} m</b> no plano. "
                    + poucos_passeios(c))
    else:
        resposta = (f"{'Sim' if f['pct'] > ESTAVEL_PCT else 'Não' if f['pct'] < -ESTAVEL_PCT else 'Mais ou menos'}. "
                    f"Cada batimento acima do repouso leva-te agora <b>{num(f['agora'], 1)} m</b> no plano, contra "
                    f"<b>{num(f['antes'], 1)} m</b> nos teus primeiros {N_COMPARAR} passeios: "
                    f"<b>{sinal}{num(abs(f['pct']))}% de eficiência</b>.")
    if not pd.isna(f["var"]):
        resposta += (f" Nos últimos {TENDENCIA_DIAS // 30} meses está <b>{f['tendencia']}</b> "
                     f"({'+' if f['var'] >= 0 else '−'}{num(abs(f['var']))}% face aos {TENDENCIA_DIAS // 30} meses antes).")
    _, _, nota, figs = sec_linha(
        d, "efic", "m por batimento", "", lambda a, b: "", "")
    figs[0].update_traces(hovertemplate="%{text}<br>%{y:.1f} m por batimento<extra></extra>", selector=dict(mode="markers"))
    cinta = ("" if f["desvio"] == 0 else
             f"A cinta marca cerca de {num(abs(f['desvio']))} bpm {'acima' if f['desvio'] > 0 else 'abaixo'} do relógio, "
             "por isso os passeios com cinta foram corrigidos. ")
    return ("Estou em melhor forma?", resposta,
            f"Eficiência = metros que andas no plano por cada batimento acima da tua FC de repouso ({FC_REPOUSO} bpm). "
            "Sobe quando andas mais depressa com o mesmo esforço, ou ao mesmo ritmo com o coração "
            f"mais calmo: é a melhor medida de forma que estes dados permitem. {cinta}Cada ponto é um passeio e varia muito "
            "(vento, grupo, sensor); a linha escura é o valor típico de cada mês.", figs)


def poucos_passeios(c):
    return (f"Com {len(c)} passeio{'' if len(c) == 1 else 's'} ainda não dá para comparar o início com agora: "
            f"a partir de {2 * N_MIN_COMPARAR} já dá.")


def carga_diaria(p):
    """Carga de treino por dia (TRIMP de Edwards: minutos em cada zona × nº da zona), do 1.º passeio até hoje."""
    carga = sum(p[f"Z{i}"].fillna(0) * i for i in range(1, 6))
    dias = pd.date_range(p["inicio"].min().normalize(), pd.Timestamp(date.today()))
    return carga.groupby(p["inicio"].dt.normalize()).sum().reindex(dias, fill_value=0)


def resumo_frescura(p):
    diaria = carga_diaria(p)
    # começa na carga média das primeiras 6 semanas, senão o início parecia sempre "cansado"
    forma, fadiga = [], []
    f = g = diaria.iloc[:TAU_FORMA].mean()
    for v in diaria:
        f += (v - f) / TAU_FORMA
        g += (v - g) / TAU_FADIGA
        forma.append(f)
        fadiga.append(g)
    s = pd.DataFrame({"forma": forma, "fadiga": fadiga}, index=diaria.index)
    s["frescura"] = s["forma"] - s["fadiga"]
    hoje = s.iloc[-1]
    rel = hoje["frescura"] / hoje["forma"] if hoje["forma"] > 0 else 0
    for limite, estado, conselho in ESTADOS:
        if rel > limite:
            break
    ha4 = s["forma"].iloc[-29] if len(s) > 28 else np.nan
    return dict(s=s, rel=rel, estado=estado, conselho=conselho,
                var_forma=(hoje["forma"] / ha4 - 1) * 100 if ha4 and not pd.isna(ha4) else np.nan)


def sec_frescura(p):
    r = resumo_frescura(p)
    s = r["s"]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.62, 0.38],
                        subplot_titles=("", "Frescura = forma − fadiga"))
    for col, nome, cor in (("forma", "forma (últimas ~6 semanas)", AZUL), ("fadiga", "fadiga (última semana)", LARANJA)):
        fig.add_trace(go.Scatter(x=s.index, y=s[col], mode="lines", name=nome, line=dict(color=cor, width=2),
                                 hovertemplate=f"%{{x|%d/%m/%Y}}<br>{nome.split(' ')[0]}: %{{y:.0f}}<extra></extra>"),
                      row=1, col=1)
    fig.add_trace(go.Bar(x=s.index, y=s["frescura"], showlegend=False, marker_line_width=0,
                         marker_color=np.where(s["frescura"] >= 0, AZUL, LARANJA),
                         hovertemplate="%{x|%d/%m/%Y}<br>frescura: %{y:.0f}<extra></extra>"), row=2, col=1)
    estilo(fig, 460).update_layout(bargap=0, hovermode="x unified", margin=dict(t=70))
    fig.update_annotations(font=dict(size=13, color=TINTA2), x=0, xanchor="left")
    fig.add_hline(y=0, line_color=EIXO, line_width=1, row=2, col=1)
    eixo_meses(fig, p)
    resposta = f"Neste momento estás <b>{r['estado'].lower()}</b>. {r['conselho']}"
    if not pd.isna(r["var_forma"]):
        resposta += (f" A tua carga habitual {'subiu' if r['var_forma'] >= 0 else 'desceu'} "
                     f"<b>{num(abs(r['var_forma']))}%</b> nas últimas 4 semanas.")
    return ("Estou fresco ou cansado?", resposta,
            "Cada passeio dá uma carga: os minutos em cada zona de FC vezes o número da zona (Z4 conta 4 vezes mais "
            "do que Z1). A forma é a média dessa carga nas últimas ~6 semanas e a fadiga a da última semana; a fadiga "
            "sobe e desce depressa, a forma devagar. Frescura = forma − fadiga: abaixo de zero (laranja) estás a treinar "
            "mais do que o habitual, acima (azul) estás descansado. É o mesmo princípio do \"Fitness & Freshness\" do "
            "Strava; é uma orientação, não um diagnóstico.", [fig])


def sec_fatores(c):
    """Que fatores mexem no esforço do coração, com uma margem honesta (bootstrap) em vez de números soltos."""
    d = c.dropna(subset=["fc_media", "vel_plano"]).sort_values("inicio").copy()
    X = pd.DataFrame({"vel": d["vel_plano"], "forma": np.log1p(d["km_acum"]), "cinta": (d["sensor"] == "cinta") * 1.0})
    d["dif"] = d["fc_media"] - minimos_quadrados(d["fc_media"].to_numpy(), X)
    d["km7"] = [c.loc[(c["inicio"] < t) & (c["inicio"] >= t - pd.Timedelta(days=7)), "km"].sum() for t in d["inicio"]]
    ameno = (d["temp"] >= 15) & (d["temp"] <= CALOR)
    testes = [
        (f"Calor (mais de {CALOR} °C)", d["temp"] > CALOR, ameno),
        (f"Frio (menos de {FRIO} °C)", d["temp"] < FRIO, ameno),
        ("Vento forte", d["vento"] > d["vento"].quantile(0.75), d["vento"] <= d["vento"].median()),
        (f"Depois de {PARAGEM}+ dias parado", d["dias_parado"] >= PARAGEM, d["dias_parado"] < PARAGEM),
        ("Semana anterior com muitos km", d["km7"] > d["km7"].quantile(0.75), d["km7"] <= d["km7"].median()),
        ("Dia seguido a outro passeio", d["dias_parado"] <= 1.5, (d["dias_parado"] > 1.5) & (d["dias_parado"] < PARAGEM)),
        ("De manhã (antes das 11 h)", d["inicio"].dt.hour < 11, d["inicio"].dt.hour >= 14),
    ]
    rng = np.random.default_rng(1)  # semente fixa: o mesmo resultado em cada atualização
    linhas = []
    for nome, a, b in testes:
        xa, xb = d.loc[a, "dif"].to_numpy(), d.loc[b, "dif"].to_numpy()
        if len(xa) < FATOR_MIN or len(xb) < FATOR_MIN:
            linhas.append((nome, np.nan, np.nan, np.nan, len(xa), "ainda sem dados"))
            continue
        ef = np.median(xa) - np.median(xb)
        boot = [np.median(rng.choice(xa, len(xa))) - np.median(rng.choice(xb, len(xb))) for _ in range(3000)]
        lo, hi = np.percentile(boot, [5, 95])
        veredicto = ("claro" if lo > 0 or hi < 0 else "possível" if abs(ef) >= 2 else "sem efeito visível")
        linhas.append((nome, ef, lo, hi, len(xa), veredicto))
    t = pd.DataFrame(linhas, columns=["nome", "ef", "lo", "hi", "n", "veredicto"])
    ordem = {"claro": 0, "possível": 1, "sem efeito visível": 2, "ainda sem dados": 3}
    t = t.assign(o=t["veredicto"].map(ordem), a=t["ef"].abs()).sort_values(["o", "a"], ascending=[True, False])

    v = t[t["ef"].notna()].iloc[::-1]  # de baixo para cima no gráfico
    rot = [f"{r.nome}<br><span style='font-size:11px;color:{APAGADO}'>{r.veredicto} · {r.n} passeios</span>"
           for r in v.itertuples()]
    fig = go.Figure(go.Scatter(
        x=v["ef"], y=rot, mode="markers", marker=dict(color=AZUL, size=10, line=dict(color=FUNDO, width=2)),
        error_x=dict(type="data", symmetric=False, array=v["hi"] - v["ef"], arrayminus=v["ef"] - v["lo"],
                     color=APAGADO, thickness=2, width=0),
        customdata=np.column_stack([v["lo"], v["hi"]]),
        hovertemplate="%{x:+.1f} bpm (margem %{customdata[0]:+.1f} a %{customdata[1]:+.1f})<extra></extra>"))
    fig.add_vline(x=0, line_color=TINTA2, line_width=1)
    estilo(fig, 60 + 54 * len(v)).update_layout(showlegend=False, margin=dict(l=10, r=20, t=20, b=50))
    fig.update_xaxes(title_text="bpm acima (+) ou abaixo (−) do esperado", zeroline=False, showgrid=True,
                     gridcolor=GRELHA, ticksuffix="")
    fig.update_yaxes(showgrid=False, automargin=True)

    claros = t[t["veredicto"] == "claro"]
    if len(claros):
        resposta = "O que mexe mesmo contigo: " + "; ".join(
            f"<b>{r.nome.lower()}</b> ({'+' if r.ef > 0 else '−'}{num(abs(r.ef))} bpm)" for r in claros.itertuples()) + "."
    else:
        resposta = f"Com {len(d)} passeios, <b>ainda nenhum fator tem efeito claro</b> no esforço do coração."
    poss = t[t["veredicto"] == "possível"]
    if len(poss):
        r = poss.iloc[0]
        resposta += (f" O mais provável é <b>{r['nome'].lower()}</b> ({'+' if r['ef'] > 0 else '−'}"
                     f"{num(abs(r['ef']))} bpm), mas com {r['n']} passeios ainda pode ser acaso.")
    resposta += " Para ficar claro: mais passeios, de preferência sempre com o mesmo sensor."
    return ("O que mexe com o meu esforço?", resposta,
            "Cada linha compara a FC (acima ou abaixo da esperada para a tua velocidade e forma) dos passeios com esse "
            "fator e sem ele. O ponto é a diferença típica; a barra é a margem onde o valor verdadeiro está com 90% de "
            "probabilidade. Se a barra atravessa o 0, ainda não há prova de efeito. Claro = a barra não toca no 0; "
            "possível = diferença de 2 bpm ou mais, mas a barra toca no 0. A temperatura e o vento são do Open-Meteo "
            "para o centro da tua zona. São associações, não provas de causa.", [fig])


def sec_mapa():
    return ("Por onde ando?",
            "Todas as estradas por onde passaste, com a cor do número de vezes. "
            '<a href="mapa_calor.html" target="_blank">Abrir o mapa em ecrã inteiro ↗</a>',
            "Na legenda escolhes o período, uma volta habitual ou só alguns escalões; "
            "clica numa linha para ver a lista dos passeios que lá passaram.",
            ['<iframe id="mapa" data-src="mapa_calor.html" title="Mapa dos percursos"></iframe>'])


def sec_voltas(c, voltas):
    titulo = "Quais são as minhas voltas habituais, e estou mais rápido nelas?"
    if not voltas:
        return titulo, "Ainda não há percursos repetidos vezes suficientes para comparar.", "", []
    fig, linhas, mais_rapido = go.Figure(), [], 0
    for v, cor in zip(voltas, CORES_VOLTAS):
        d = c[c["volta"] == v["n"]].sort_values("inicio")
        fig.add_trace(go.Scatter(
            x=d["inicio"], y=d["vel_media"], mode="lines+markers", name=f"Volta {v['n']}",
            line=dict(color=cor, width=2), marker=dict(size=9, color=cor, line=dict(color=FUNDO, width=2)),
            text=dica(d), hovertemplate=f"{escape(v['nome'])}<br>%{{text}}<br>%{{y:.1f}} km/h<extra></extra>"))
        v0, v1 = d["vel_media"].iloc[0], d["vel_media"].iloc[-1]
        mais_rapido += v1 > v0
        linhas.append(
            f'<tr><td><span class="ponto" style="background:{cor}"></span>{escape(v["nome"])}</td>'
            f'<td>{v["vezes"]}</td><td>{d["inicio"].iloc[0]:%d/%m/%Y}</td><td>{d["inicio"].iloc[-1]:%d/%m/%Y}</td>'
            f'<td>{num(v0, 1)} → {num(v1, 1)}</td><td><a href="#mapa" data-volta="{v["n"]}">ver no mapa</a></td></tr>')
    estilo(fig, 360).update_yaxes(title_text="km/h (média do passeio)")
    eixo_meses(fig, c)
    vezes = [v["vezes"] for v in voltas]
    resposta = (f"Encontrei <b>{len(voltas)} percursos</b> que repetiste ({min(vezes)} a {max(vezes)} vezes cada); "
                f"o mais repetido é a <b>{escape(voltas[0]['nome'])}</b>. Em <b>{mais_rapido} de {len(voltas)}</b> "
                "a última vez foi mais rápida do que a primeira.")
    tabela_voltas = ('<div class="tabela"><table><thead><tr><th>Volta</th><th>vezes</th><th>primeira</th>'
                     '<th>última</th><th>km/h 1.ª → última</th><th></th></tr></thead><tbody>'
                     + "".join(linhas) + "</tbody></table></div>")
    return (titulo, resposta,
            "Agrupei os passeios que partilham a maior parte do percurso (em qualquer sentido). Comparar a mesma volta "
            "consigo própria é mais justo do que comparar passeios diferentes, mas cada volta tem poucas repetições: "
            "um dia de vento pesa muito, por isso olha para a tendência de cada linha e não para um ponto isolado.",
            [tabela_voltas, fig])


def sec_linha(p, col, unid, pergunta, frase, nota, cor_por=None):
    fig = go.Figure()
    grupos = [(None, AZUL, p)] if cor_por is None else [
        (nome, cor, p[p[cor_por] == nome]) for nome, cor in (("relógio", AZUL), ("cinta", LARANJA))]
    for nome, cor, d in grupos:
        fig.add_trace(go.Scatter(
            x=d["inicio"], y=d[col], mode="markers", name=f"passeio com FC {'do' if nome == 'relógio' else 'da'} {nome}" if nome else "cada passeio",
            marker=dict(color=cor, size=8, opacity=0.55, line=dict(color=FUNDO, width=2)),
            text=dica(d), hovertemplate=f"%{{text}}<br>%{{y:.1f}} {unid}<extra></extra>"))
    x, y = mediana_mensal(p, col)
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines+markers", name="valor típico do mês (mediana)",
        line=dict(color=TINTA, width=2), marker=dict(size=7, color=TINTA),
        hovertemplate=f"mediana do mês: %{{y:.1f}} {unid}<extra></extra>"))
    estilo(fig, 380).update_yaxes(title_text=unid)
    eixo_meses(fig, p)
    antes, agora = p[col].head(N_COMPARAR).median(), p[col].tail(N_COMPARAR).median()
    resposta = frase(antes, agora) if N_COMPARAR >= N_MIN_COMPARAR else (poucos_passeios(p) if pergunta else "")
    return pergunta, resposta, nota, [fig]


def sec_zonas(p, limites, fc_max):
    zonas = [f"Z{i}" for i in range(1, 6)]
    mes = p.groupby(p["inicio"].dt.to_period("M"))[zonas].sum()
    pct = mes.div(mes.sum(axis=1), axis=0) * 100
    tetos = limites[1:] + [fc_max]
    fig = go.Figure()
    for z, nome, cor, lo, hi in zip(zonas, NOMES_ZONAS, CORES_ZONAS, limites, tetos):
        fig.add_trace(go.Bar(
            x=[mes_pt(m) for m in pct.index], y=pct[z], name=f"{nome} ({lo}–{hi - 1} bpm)", marker_color=cor,
            marker_line=dict(color=FUNDO, width=2), customdata=mes[z] / 60,
            hovertemplate=f"{nome}<br>%{{x}}: %{{y:.0f}}% do tempo (%{{customdata:.1f}} h)<extra></extra>"))
    estilo(fig, 400).update_layout(barmode="stack", bargap=0.25, legend_traceorder="normal")
    fig.update_yaxes(title_text="% do tempo a pedalar", range=[0, 100], ticksuffix="%")
    total = mes.sum()
    facil = (total["Z1"] + total["Z2"]) / total.sum() * 100
    duro = (total["Z4"] + total["Z5"]) / total.sum() * 100
    resposta = (f"<b>{num(facil)}%</b> do teu tempo foi em zonas fáceis (Z1–Z2), "
                f"<b>{num(100 - facil - duro)}%</b> em ritmo moderado (Z3) e <b>{num(duro)}%</b> em zonas duras (Z4–Z5).")
    return ("Com que intensidade pedalo?", resposta,
            "Cada barra é um mês e soma 100% do tempo com FC registada; as cores vão de claro (fácil) a escuro (máximo). "
            + ("As zonas são as que tens configuradas na Garmin. " if ORIGEM_ZONAS is None else
               f"As zonas foram calculadas a partir de uma FC máxima de {fc_max} bpm ({ORIGEM_ZONAS}). ")
            + "Muitos planos de treino recomendam cerca de 80% em zonas fáceis.", [fig])


def sec_detalhe(p, series):
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        subplot_titles=("Frequência cardíaca (bpm)", "Velocidade (km/h)", "Altitude (m)"))
    p = p.sort_values("inicio", ascending=False).reset_index(drop=True)
    botoes = []
    for i, r in p.iterrows():
        df = series[r["id"]].set_index("timestamp")[["fc_limpa", "vel_kmh", "enhanced_altitude"]]
        df = df.resample(f"{AMOSTRA_S}s").mean()  # buracos (pausas) ficam NaN e quebram a linha
        t = (df.index - df.index[0]).total_seconds() / 60
        for linha, col, cor, unid in ((1, "fc_limpa", LARANJA, "bpm"), (2, "vel_kmh", AZUL, "km/h"),
                                      (3, "enhanced_altitude", APAGADO, "m")):
            fig.add_trace(go.Scatter(x=t, y=df[col], mode="lines", line=dict(color=cor, width=1.5), visible=i == 0,
                                     showlegend=False, connectgaps=False,
                                     hovertemplate=f"min %{{x:.0f}}: %{{y:.0f}} {unid}<extra></extra>"), row=linha, col=1)
        fonte = "relógio" if r["fonte_fc"].startswith("relógio") else "cinta"
        dados = {"km": num(r["km"], 1), "tempo": duracao(r["tempo_s"]),
                 "subida": num(r["subida_m"]) if pd.notna(r["subida_m"]) else "–",
                 "vel": num(r["vel_media"], 1) if pd.notna(r["vel_media"]) else "–",
                 "fc": f"{num(r['fc_media'])} · {fonte}" if pd.notna(r["fc_media"]) else "–",
                 "temp": num(r["temp"]) if pd.notna(r.get("temp")) else "–"}
        attrs = " ".join(f'data-{k}="{escape(v)}"' for k, v in dados.items())
        botoes.append(f'<option value="{i}" {attrs}>{DIAS[r["inicio"].weekday()][:3]} {r["inicio"]:%d/%m/%Y} · '
                      f'{r["km"]:.0f} km</option>')
    estilo(fig, 620).update_layout(hovermode="x unified", margin=dict(t=40), meta="detalhe")
    fig.update_annotations(font=dict(size=13, color=TINTA2), x=0, xanchor="left")
    fig.update_xaxes(title_text="minutos desde o início", row=3, col=1)
    escolha = f'<select id="escolhe-passeio" aria-label="Escolher passeio">{"".join(botoes)}</select>'
    mini = "".join(f'<div class="mini"><span>{leg}</span><b data-campo="{campo}"></b></div>' for campo, leg in [
        ("km", "km"), ("tempo", "tempo"), ("vel", "km/h"), ("subida", "subida (m)"), ("fc", "FC média"), ("temp", "°C")])
    return ("Como correu cada passeio?",
            "Escolhe um passeio na lista (o mais recente aparece primeiro).",
            "Os três gráficos partilham o mesmo eixo do tempo: passa o rato para ver os três valores no mesmo minuto. "
            "Quando a altitude sobe, a velocidade costuma cair e a FC subir: é uma subida. "
            "Quando a FC desce de repente com a velocidade a zero, é uma paragem. Os espaços em branco são pausas.",
            [escolha, f'<div class="minis">{mini}</div>', fig])


# ---------- página ----------

def cartao_recorde(titulo, valor, quando):
    return (f'<div class="cartao"><div class="leg">{titulo}</div><div class="valor">{valor}</div>'
            f'<div class="quando">{quando}</div></div>')


def tabela(p):
    linhas = "".join(
        f"<tr><td>{r.inicio:%d/%m/%Y}</td><td>{num(r.km, 1)}</td><td>{num(r.tempo_s / 3600, 1)}</td>"
        f"<td>{num(r.subida_m) if pd.notna(r.subida_m) else '–'}</td><td>{num(r.vel_media, 1) if pd.notna(r.vel_media) else '–'}</td>"
        f"<td>{num(r.fc_media) if pd.notna(r.fc_media) else '–'}</td>"
        f"<td>{'–' if pd.isna(r.fc_media) else 'relógio' if r.fonte_fc.startswith('relógio') else 'cinta'}</td>"
        f"<td>{num(r.temp) if pd.notna(r.temp) else '–'}</td><td>{num(r.vento) if pd.notna(r.vento) else '–'}</td>"
        f"<td>{r.volta or ''}</td></tr>"
        for r in p.sort_values("inicio", ascending=False).itertuples())
    return ("<table><thead><tr><th>Data</th><th>km</th><th>horas</th><th>subida (m)</th><th>km/h</th>"
            f"<th>FC média</th><th>sensor FC</th><th>°C</th><th>vento km/h</th><th>volta</th></tr></thead>"
            f"<tbody>{linhas}</tbody></table>")


def data_longa(d):
    return f"{DIAS[d.weekday()]}, {d.day} de {MESES_LONGOS[d.month - 1]}"


def comparar(valor, tipico, casas, unid, menos_e_melhor=False):
    """'▲ 1,2 km/h acima do teu típico' (texto neutro: a seta e a palavra dizem o sentido, não a cor)."""
    if pd.isna(valor) or pd.isna(tipico):
        return ""
    d = valor - tipico
    if abs(d) < 0.5 * 10 ** -casas:
        return "igual ao teu típico"
    return f"{'▲' if d > 0 else '▼'} {num(abs(d), casas)} {unid} {'acima' if d > 0 else 'abaixo'} do típico"


def ultimo_passeio(p, c, voltas):
    r = p.iloc[-1]
    nomes = {v["n"]: v["nome"] for v in voltas}
    tipico = c.median(numeric_only=True)
    tiles = [
        ("Distância", f"{num(r.km, 1)} <small>km</small>", comparar(r.km, tipico["km"], 0, "km")),
        ("Tempo", duracao(r.tempo_s), ""),
        ("Vel. no plano", f"{num(r.vel_plano, 1)} <small>km/h</small>" if pd.notna(r.vel_plano) else "–",
         comparar(r.vel_plano, tipico["vel_plano"], 1, "km/h")),
        ("FC média", f"{num(r.fc_media)} <small>bpm</small>" if pd.notna(r.fc_media) else "–",
         comparar(r.fc_media, tipico["fc_media"], 0, "bpm")),
        ("Subida", f"{num(r.subida_m)} <small>m</small>" if pd.notna(r.subida_m) else "–",
         comparar(r.subida_m, tipico["subida_m"], 0, "m")),
    ]
    html_tiles = "".join(f'<div class="cartao"><div class="leg">{t}</div><div class="valor">{v}</div>'
                         f'<div class="quando">{q}</div></div>' for t, v, q in tiles)
    extras = [f"{r.inicio:%H:%M} – {r.fim:%H:%M}"]
    if pd.notna(r.get("temp")):
        extras.append(f"{num(r.temp)} °C · vento {num(r.vento)} km/h")
    if pd.notna(r.get("volta")) and r.get("volta"):
        extras.append(escape(nomes.get(r.volta, f"Volta {r.volta}")))
    return (f'<section class="destaque"><div class="selo">Último passeio</div>'
            f'<h2>{data_longa(r.inicio).capitalize()}</h2><p class="sub2">{" · ".join(extras)}</p>'
            f'<div class="cartoes">{html_tiles}</div>'
            '<p class="ler-curto">“Típico” é a mediana de todos os teus passeios.</p></section>')


ICONES = {
    "resumo": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/>'
              '<rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "percursos": '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14M15 6v14"/>',
    "evolucao": '<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>',
    "coracao": '<path d="M12 20s-7-4.4-9-9a5 5 0 0 1 9-3.2A5 5 0 0 1 21 11c-2 4.6-9 9-9 9z"/>',
    "passeios": '<circle cx="5.5" cy="16.5" r="3.5"/><circle cx="18.5" cy="16.5" r="3.5"/>'
                '<path d="M5.5 16.5 9 10h6l3.5 6.5M9 10l3 6.5h-6.5M13 6.5h2.5L18.5 16.5"/>',
}


def svg(nome, classe=""):
    return (f'<svg class="{classe}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONES[nome]}</svg>')


CSS = """
:root { --pagina:#f1f2ee; --cartao:#ffffff; --tinta:#0b0b0b; --tinta2:#52514e; --apagado:#898781;
        --linha:#e8e7e1; --azul:#2a78d6; --noite:#0e2a4d; --suave:#f6f6f3; }
* { box-sizing:border-box; }
html { scroll-padding-top:70px; }
body { margin:0; background:var(--pagina); color:var(--tinta); -webkit-font-smoothing:antialiased;
       font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
.largura { max-width:1040px; margin:0 auto; padding:0 16px; }

/* cabeçalho */
.hero { color:#fff; padding:26px 0 28px;
        background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 760 260' fill='none'%3E%3Cpath d='M0 200C60 190 90 120 150 128S250 205 310 170 400 70 470 90 580 190 640 120 720 60 760 70' stroke='%237fe0b8' stroke-opacity='.55' stroke-width='3' stroke-linecap='round'/%3E%3Ccircle cx='470' cy='90' r='6' fill='white' fill-opacity='.85'/%3E%3C/svg%3E") no-repeat right 12px top 6px/min(540px,58%) auto,
                   radial-gradient(45% 60% at 8% 110%, rgba(27,175,122,.35), transparent 70%),
                   radial-gradient(120% 160% at 90% -30%, #2a78d6 0%, #15407a 42%, #0b1f3a 100%); }
.marca { display:flex; align-items:center; gap:10px; font-weight:600; font-size:15px; opacity:.92; }
.marca svg { width:26px; height:26px; }
.hero h1 { font-size:clamp(44px,9vw,68px); line-height:1; margin:20px 0 6px; font-weight:750; letter-spacing:-.03em; }
.hero h1 small { font-size:.38em; font-weight:600; opacity:.75; margin-left:6px; letter-spacing:0; }
.hero .sub { margin:0; opacity:.78; }
.kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin-top:22px; }
.kpi { background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.18); border-radius:14px; padding:12px 14px;
       backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px); transition:transform .2s, background .2s; }
.kpi:hover { transform:translateY(-2px); background:rgba(255,255,255,.16); }
.kpi b { display:block; font-size:26px; font-weight:650; font-variant-numeric:tabular-nums; }
.kpi span { font-size:13px; opacity:.78; }

/* navegação: separadores em cima no computador, barra em baixo no telemóvel */
nav { position:sticky; top:0; z-index:20; background:rgba(241,242,238,.88);
      backdrop-filter:saturate(1.4) blur(12px); -webkit-backdrop-filter:saturate(1.4) blur(12px);
      border-bottom:1px solid var(--linha); }
nav .largura { display:flex; gap:4px; padding-top:8px; padding-bottom:8px; overflow-x:auto; }
nav button { display:flex; align-items:center; gap:8px; border:0; background:none; color:var(--tinta2); cursor:pointer;
             font:inherit; font-size:15px; font-weight:560; padding:8px 16px; border-radius:999px; white-space:nowrap; }
nav button svg { width:18px; height:18px; }
nav button:hover { background:rgba(0,0,0,.05); color:var(--tinta); }
nav button[aria-current="page"] { background:linear-gradient(135deg,#0e2a4d,#1d5fb4); color:#fff; box-shadow:0 4px 12px rgba(29,95,180,.3); }

main { padding-top:6px; padding-bottom:64px; }
.painel[hidden] { display:none; }

/* cartões */
section { background:var(--cartao); border-radius:18px; padding:22px 22px 14px; margin-top:16px;
          border:1px solid rgba(0,0,0,.04); box-shadow:0 1px 2px rgba(16,24,40,.04), 0 6px 20px rgba(16,24,40,.05); }
h2 { font-size:20px; line-height:1.3; margin:0 0 6px; letter-spacing:-.01em; }
section h2::before { content:""; display:inline-block; width:5px; height:.95em; border-radius:3px; margin-right:10px; vertical-align:-.1em;
                     background:linear-gradient(180deg,#2a78d6,#1baf7a); }
@keyframes entra { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:none; } }
@media (prefers-reduced-motion: no-preference) { .painel:not([hidden]) { animation:entra .35s both; } }
h3 { font-size:16px; margin:18px 0 0; }
.resposta { font-size:16.5px; margin:0 0 10px; }
.resposta b { font-weight:650; }
section a { color:var(--azul); text-decoration:none; font-weight:550; }
section a:hover { text-decoration:underline; }
details.ler { margin:8px 0 6px; color:var(--tinta2); font-size:14px; }
details.ler summary { cursor:pointer; color:var(--tinta2); font-weight:560; list-style:none; display:inline-flex;
                      align-items:center; gap:6px; padding:4px 10px; border-radius:999px; background:var(--suave); }
details.ler summary::-webkit-details-marker { display:none; }
details.ler summary::before { content:"i"; display:inline-grid; place-items:center; width:16px; height:16px; border-radius:50%;
                              border:1.5px solid currentColor; font:700 11px/1 Georgia,serif; }
details.ler[open] summary { margin-bottom:6px; }
.cartoes { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:8px 0 6px; }
.recordes { grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); }
.cartao { background:var(--suave); border-radius:14px; padding:12px 14px; }
.cartao .leg { color:var(--tinta2); font-size:13px; font-weight:560; }
.cartao .valor { font-size:24px; font-weight:680; letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
.cartao .valor small { font-size:14px; font-weight:560; color:var(--tinta2); }
.quando { color:var(--apagado); font-size:13px; }

/* último passeio */
.destaque { border-top:4px solid var(--azul); background:linear-gradient(180deg,#f1f7ff 0%,#fff 38%); }
.selo { display:inline-block; font-size:12px; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
        color:var(--azul); background:#e9f1fb; padding:3px 10px; border-radius:999px; margin-bottom:8px; }
.sub2 { color:var(--tinta2); margin:0 0 6px; }
.ler-curto { color:var(--apagado); font-size:13px; margin:4px 0 2px; }

/* tabelas */
.tabela { overflow:auto; border-radius:12px; border:1px solid var(--linha); margin-top:10px; }
.tabela.alta { max-height:560px; }
table { border-collapse:collapse; width:100%; font-size:14px; font-variant-numeric:tabular-nums; }
th, td { text-align:right; padding:8px 10px; border-bottom:1px solid var(--linha); white-space:nowrap; }
th { position:sticky; top:0; background:var(--suave); color:var(--tinta2); font-weight:600; font-size:13px; }
tbody tr:last-child td { border-bottom:0; }
tbody tr:hover td { background:#fafaf8; }
th:first-child, td:first-child { text-align:left; }
td.txt, th.txt { text-align:left; color:var(--tinta2); white-space:normal; min-width:240px; }
.ponto { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:8px; }

/* mapa e escolha de passeio */
iframe#mapa { width:100%; height:620px; border:0; border-radius:14px; margin-top:6px; background:var(--suave); }
select { font:inherit; font-weight:560; padding:10px 40px 10px 14px; border-radius:12px; border:1px solid var(--linha);
         background:var(--suave) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2352514e' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E") no-repeat right 12px center/18px;
         appearance:none; width:100%; max-width:420px; color:var(--tinta); cursor:pointer; }
.minis { display:grid; grid-template-columns:repeat(auto-fit,minmax(110px,1fr)); gap:8px; margin:12px 0 4px; }
.mini { background:var(--suave); border-radius:12px; padding:8px 12px; }
.mini span { display:block; font-size:12px; color:var(--tinta2); }
.mini b { font-size:18px; font-variant-numeric:tabular-nums; }
.rodape { color:var(--apagado); font-size:13px; text-align:center; margin-top:28px; }

@media (max-width:720px) {
  body { padding-bottom:calc(70px + env(safe-area-inset-bottom)); }
  .hero { padding:20px 0 22px; }
  .kpis { grid-template-columns:repeat(2,1fr); }
  .kpi:last-child:nth-child(odd), .cartao:last-child:nth-child(odd) { grid-column:span 2; }
  nav { position:fixed; top:auto; bottom:0; left:0; right:0; background:rgba(255,255,255,.94);
        border-bottom:0; border-top:1px solid var(--linha); padding-bottom:env(safe-area-inset-bottom); }
  nav .largura { justify-content:space-around; padding:4px 2px; gap:0; }
  nav button { flex-direction:column; gap:2px; font-size:11px; padding:6px 8px; border-radius:12px; }
  nav button svg { width:22px; height:22px; }
  nav button[aria-current="page"] { background:none; color:var(--azul); }
  section { padding:18px 16px 12px; border-radius:16px; }
  .cartoes { grid-template-columns:repeat(2,1fr); }
  iframe#mapa { height:70vh; }
}
"""

JS = """
(function () {
  var botoes = document.querySelectorAll("nav button");
  var hero = document.querySelector(".hero");
  function abrir(nome, rolar) {
    if (!document.getElementById("aba-" + nome)) nome = "resumo";
    document.querySelectorAll(".painel").forEach(function (p) { p.hidden = p.id !== "aba-" + nome; });
    botoes.forEach(function (b) { b.setAttribute("aria-current", b.dataset.aba === nome ? "page" : "false"); });
    var painel = document.getElementById("aba-" + nome);
    // o mapa só carrega quando o separador aparece (escondido, o Leaflet calcula mal o tamanho)
    painel.querySelectorAll("iframe[data-src]").forEach(function (f) {
      if (!f.getAttribute("src")) f.setAttribute("src", f.dataset.src);
    });
    // os gráficos desenhados escondidos ficam com a largura errada
    painel.querySelectorAll(".js-plotly-plot").forEach(function (g) { Plotly.Plots.resize(g); });
    if (rolar && window.scrollY > hero.offsetHeight) window.scrollTo({ top: hero.offsetHeight });
    history.replaceState(null, "", "#" + nome);
  }
  botoes.forEach(function (b) { b.addEventListener("click", function () { abrir(b.dataset.aba, true); }); });
  abrir(location.hash.slice(1) || "resumo", false);

  // "ver no mapa": mostra só essa volta no mapa (o mapa lê #volta=N do endereço)
  document.querySelectorAll("a[data-volta]").forEach(function (a) {
    a.addEventListener("click", function (e) {
      e.preventDefault();
      var mapa = document.getElementById("mapa");
      mapa.setAttribute("src", "mapa_calor.html#volta=" + a.dataset.volta);
      mapa.scrollIntoView({ behavior: "smooth" });
    });
  });

  // escolher um passeio no detalhe
  var sel = document.getElementById("escolhe-passeio");
  if (sel) {
    var preencher = function () {
      var o = sel.selectedOptions[0];
      document.querySelectorAll("[data-campo]").forEach(function (b) { b.textContent = o.dataset[b.dataset.campo]; });
    };
    sel.addEventListener("change", function () {
      var i = +sel.value, vis = [];
      for (var k = 0; k < sel.options.length; k++) vis.push(k === i, k === i, k === i);
      Plotly.restyle("detalhe", { visible: vis });
      preencher();
    });
    preencher();
  }
})();
"""

ABAS = [("resumo", "Resumo"), ("percursos", "Percursos"), ("evolucao", "Evolução"),
        ("coracao", "Coração"), ("passeios", "Passeios")]


def preparar(p):
    """Acrescenta as colunas de contexto (km acumulados, paragens...). Devolve (todos, os que contam nas médias)."""
    p = p.sort_values("inicio").reset_index(drop=True)
    p["km_acum"] = p["km"].cumsum().shift(fill_value=0)       # km feitos antes de cada passeio
    p["dias_parado"] = p["inicio"].diff().dt.total_seconds() / 86400
    p["km28_antes"] = [p.loc[(p["inicio"] < t) & (p["inicio"] >= t - pd.Timedelta(days=28)), "km"].sum()
                       for t in p["inicio"]]
    # regresso mais recente depois de uma paragem: há quantos dias, e quanto durou a paragem
    regresso = p["inicio"].where(p["dias_parado"] >= PARAGEM).ffill()
    p["dias_desde_regresso"] = (p["inicio"] - regresso).dt.total_seconds() / 86400
    p["pausa_antes"] = p["dias_parado"].where(p["dias_parado"] >= PARAGEM).ffill()
    c = p[p["conta"]].reset_index(drop=True)
    c["sensor"] = c["fonte_fc"].map(lambda s: "relógio" if s.startswith("relógio") else "cinta")
    global N_COMPARAR
    N_COMPARAR = min(N_MAX_COMPARAR, len(c) // 2)
    return p, c


def todas_seccoes(p, c, series, limites, fc_max, voltas):
    """Todas as secções, por nome: (pergunta, resposta, como ler, partes). Usadas no relatório e na app do telemóvel."""
    t0, t1 = c["vel_media"].head(N_COMPARAR).median(), c["vel_media"].tail(N_COMPARAR).median()
    fc_ok = c["fc_media"].notna().any()
    km_plano = c["km_plano"].sum() / c["km"].sum() * 100
    return {
        "recordes": sec_recordes(p, c), "km": sec_km(p), "semanas": sec_semanas(p),
        "mapa": sec_mapa(), "voltas": sec_voltas(c, voltas),
        "velocidade": sec_linha(
                c.dropna(subset=["vel_plano"]), "vel_plano", "km/h", "Estou a ficar mais rápido?",
                lambda a, b: (f"No plano, nos teus primeiros {N_COMPARAR} passeios andavas tipicamente a <b>{num(a, 1)} km/h</b>; "
                              f"nos últimos {N_COMPARAR} a <b>{num(b, 1)} km/h</b> "
                              f"(<b>{'+' if round(b - a, 1) >= 0 else '−'}{num(abs(b - a), 1)} km/h</b>). "
                              f"Contando também subidas e descidas: {num(t0, 1)} → {num(t1, 1)} km/h."),
                f"Cada ponto é um passeio, com a velocidade média só nos troços planos (inclinação abaixo de {num(1.5, 1)}%), "
                f"que são {num(km_plano)}% dos teus km: assim um passeio com mais subidas não parece mais lento. "
                "A linha escura é o valor típico de cada mês: olha para a linha, porque um passeio isolado "
                "varia muito com o vento ou com ir em grupo."),
        "forma": sec_forma(c),
        "fc": sem_fc("O coração está a trabalhar menos?") if not fc_ok else sec_linha(
                c, "fc_media", "bpm", "O coração está a trabalhar menos?",
                lambda a, b: (f"Nos primeiros {N_COMPARAR} passeios a FC média típica era <b>{num(a)} bpm</b>; "
                              f"nos últimos {N_COMPARAR} é <b>{num(b)} bpm</b> "
                              f"(<b>{'+' if round(b - a) >= 0 else '−'}{num(abs(b - a))} bpm</b>)."),
                "Cada ponto é um passeio (FC média em movimento), com a cor do sensor: o relógio no pulso ou a cinta no peito. "
                "Uma FC mais baixa a andar ao mesmo ritmo significa que o mesmo esforço te custa menos.",
                cor_por="sensor"),
        "zonas": sec_zonas(c, limites, fc_max) if fc_ok else sem_fc("Com que intensidade pedalo?"),
        "frescura": sec_frescura(p) if fc_ok else sem_fc("Estou fresco ou cansado?"),
        "fatores": sec_fatores(c) if fc_ok else sem_fc("O que mexe com o meu esforço?"),
        "detalhe": sec_detalhe(c, series),
    }


def gerar(p, series, limites, fc_max, voltas, destino):
    """p: todos os passeios; os que têm conta=False ficam só nos km e na tabela."""
    p, c = preparar(p)
    s = todas_seccoes(p, c, series, limites, fc_max, voltas)
    seccoes = {
        "resumo": [s["recordes"], s["km"], s["semanas"]],
        "percursos": [s["mapa"], s["voltas"]],
        "evolucao": [s["forma"], s["frescura"], s["velocidade"]],
        "coracao": [s["fc"], s["zonas"], s["fatores"]],
        "passeios": [s["detalhe"],
                     ("Todos os passeios", f"{len(p)} passeios, do mais recente para o mais antigo.", "",
                      [f'<div class="tabela alta">{tabela(p)}</div>'])],
    }
    paineis, n = [], 0
    for aba, lista in seccoes.items():
        blocos = [ultimo_passeio(p, c, voltas)] if aba == "resumo" else []
        for pergunta, resposta, como_ler, partes in lista:
            conteudo = "".join(
                parte if isinstance(parte, str) else parte.to_html(
                    full_html=False, include_plotlyjs=False, div_id=parte.layout.meta or f"g{n}_{j}",
                    config={"displaylogo": False, "responsive": True, "modeBarButtonsToRemove": ["select2d", "lasso2d"]})
                for j, parte in enumerate(partes))
            ler = (f'<details class="ler"><summary>Como ler</summary>{escape(como_ler)}</details>' if como_ler else "")
            blocos.append(f'<section><h2>{escape(pergunta)}</h2><p class="resposta">{resposta}</p>{conteudo}{ler}</section>')
            n += 1
        paineis.append(f'<div class="painel" id="aba-{aba}">{"".join(blocos)}</div>')

    horas = p["tempo_s"].sum() / 3600
    s = semanas(p)
    _, _, _, seguidas = sequencias(s["n"] > 0)
    este_mes = p[p["inicio"].dt.to_period("M") == pd.Period(date.today(), "M")]
    kpis = "".join(f'<div class="kpi"><b>{v}</b><span>{leg}</span></div>' for v, leg in [
        (num(len(p)), "passeios"), (num(horas), "horas a pedalar"), (f'{num(p["subida_m"].sum())} m', "de subida"),
        (f'{num(este_mes["km"].sum())} km', f"em {MESES_LONGOS[date.today().month - 1]} · {len(este_mes)} passeio{'' if len(este_mes) == 1 else 's'}"),
        (f"{seguidas}", "semanas seguidas a pedalar"),
    ])
    nav = "".join(f'<button type="button" data-aba="{a}">{svg(a)}<span>{nome}</span></button>' for a, nome in ABAS)
    periodo = f"{p['inicio'].min():%d/%m/%Y} a {p['inicio'].max():%d/%m/%Y}"
    icone = ("data:image/svg+xml," + svg("passeios").replace('class=""', 'xmlns="http://www.w3.org/2000/svg"')
             .replace("currentColor", "%232a78d6").replace('"', "'").replace("<", "%3C").replace(">", "%3E"))
    pagina = f"""<!doctype html>
<html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0b1f3a"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>Os meus passeios</title><link rel="icon" href="{icone}">
<script src="https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js"></script>
<style>{CSS}</style></head><body>
<header class="hero"><div class="largura">
  <div class="marca">{svg("passeios")}Os meus passeios</div>
  <h1>{num(p["km"].sum())}<small>km</small></h1>
  <p class="sub">pedalados de {periodo} · dados do Garmin</p>
  <div class="kpis">{kpis}</div>
</div></header>
<nav aria-label="Secções"><div class="largura">{nav}</div></nav>
<main class="largura">
{"".join(paineis)}
<p class="rodape">Atualizado a {date.today():%d/%m/%Y} · {len(p)} passeios</p>
</main>
<script>{JS}</script>
</body></html>"""
    destino.write_text(pagina, encoding="utf-8")
