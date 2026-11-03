"""Lê os .fit de dados/ e gera o relatório (saida/relatorio.html) e o mapa dos percursos (saida/mapa_calor.html)."""
import json
import pickle
import sys
from pathlib import Path

import folium
import numpy as np
import pandas as pd
from fitparse import FitFile

import app_movel
import meteo
import relatorio

RAIZ = Path(__file__).parent
DADOS = RAIZ / "dados"
SAIDA = RAIZ / "saida"
PUBLICO = SAIDA / "publico"   # versão sem os sítios de partida, que é a que vai para a internet
PUBLICAR = (RAIZ / "publicar.py").exists()  # só quem publica a app precisa da versão pública
CACHE = RAIZ / "cache"
PCT_ZONAS = [0.5, 0.6, 0.7, 0.8, 0.9]  # início das zonas 1–5 em fração da FC máxima (o que a Garmin usa por omissão)
PROGRESSO = None             # função(n, total) chamada a cada passeio lido (a versão web mostra o andamento)
FC_REPOUSO_OMISSAO = 60       # bpm, se o relógio não tiver guardado a FC de repouso
SEMICIRCULOS = 180 / 2**31

FC_MIN, FC_MAX = 40, 210      # fora disto é impossível em ciclismo
SALTO_MAX = 25                # bpm de desvio face à mediana local
JANELA = 15                   # amostras da mediana local
LIMITE_SUSPEITO = 0.05        # >5% removido marca o passeio como suspeito
V_MOVIMENTO = 1.0             # m/s; abaixo disto conta como parado
PAUSA_S = 30                  # intervalo (s) acima do qual não conta como tempo a pedalar
KM_MIN = 5                    # passeios mais curtos não entram nas médias nem na evolução
JANELA_INCLINACAO = 100       # m para cada lado de um ponto para medir a inclinação (menos ruído do GPS)
PLANO = 1.5                   # % de inclinação abaixo da qual (a subir ou a descer) conta como plano
KM_PLANO_MIN = 5              # km de plano necessários para a velocidade no plano contar
COLUNAS = ["timestamp", "heart_rate", "enhanced_speed", "enhanced_altitude", "position_lat", "position_long"]
GRELHA = 0.0006               # graus (~65 m); tamanho da célula para contar passagens no mapa
ESCALOES = [(1, 1), (2, 4), (5, 9), (10, 19), (20, 999)]  # nº de passeios por troço
CORES_ESCALOES = ["#fed976", "#fd8d3c", "#e31a1c", "#99000d", "#3f007d"]
LARGURAS = [2, 3, 4, 5, 7]
CORTE = -10**9                # célula fictícia que marca uma falha de GPS no meio do trajeto
GROSSA = 0.002                # graus (~200 m); grelha para comparar o percurso de dois passeios
SEMELHANCA_MIN = 0.6          # fração média de percurso em comum para dois passeios serem a mesma volta
VOLTA_MIN = 3                 # nº mínimo de passeios para uma volta contar como habitual
N_VOLTAS = 5                  # voltas habituais mostradas (as mais repetidas)
VIRTUAIS = ("indoor_cycling", "virtual_activity")  # rolo e Zwift & companhia: o GPS (se houver) é inventado
RUMOS = ["norte", "nordeste", "este", "sudeste", "sul", "sudoeste", "oeste", "noroeste"]


def fonte_fc(fit):
    """Descreve de onde veio a FC (cinta ANT+/BLE ou sensor do relógio) a partir do device_info."""
    fontes = set()
    for m in fit.get_messages("device_info"):
        v = m.get_values()
        if v.get("antplus_device_type") == "heart_rate" or v.get("source_type") in ("bluetooth_low_energy", "antplus"):
            fontes.add(str(v.get("antplus_device_type") or v.get("source_type")))
    return "sensor externo (" + ", ".join(sorted(fontes)) + ")" if fontes else "relógio (óptico)"


def ler(caminho):
    fit = FitFile(str(caminho))
    s = next(iter(fit.get_messages("session"))).get_values()
    linhas = [r.get_values() for r in fit.get_messages("record")]
    df = pd.DataFrame(linhas).reindex(columns=COLUNAS)  # passeios de rolo não têm GPS nem velocidade
    df["lat"] = df["position_lat"] * SEMICIRCULOS
    df["lon"] = df["position_long"] * SEMICIRCULOS
    df["vel_kmh"] = df["enhanced_speed"] * 3.6
    info = {
        "inicio": pd.Timestamp(s["start_time"]),
        "km": (s.get("total_distance") or 0) / 1000,
        "tempo_s": s.get("total_timer_time"),
        "subida_m": s.get("total_ascent"),
        "tipo": s.get("sub_sport"),
        "fonte_fc": fonte_fc(fit),
        # FC de repouso que o relógio tinha nesse dia (só é usada se não houver zonas da Garmin)
        "fc_repouso": next((m.get_values().get("resting_heart_rate") for m in fit.get_messages("user_profile")), None),
    }
    return df, info


def ler_com_cache(caminho):
    """Ler um .fit demora; guarda o resultado em cache/ e só relê se o ficheiro mudar."""
    c = CACHE / (caminho.stem + ".pkl")
    try:
        if not (c.exists() and c.stat().st_mtime >= caminho.stat().st_mtime):
            raise FileNotFoundError
        with open(c, "rb") as f:
            df, info = pickle.load(f)
    except Exception:  # sem cache, ou cache de outra versão das bibliotecas: lê o .fit outra vez
        df, info = ler(caminho)
        with open(c, "wb") as f:
            pickle.dump((df, info), f)
    # o nome completo identifica o passeio: os .zip de uma atividade dão todos "<nº>_ACTIVITY.fit"
    info["id"] = caminho.stem
    return df, info


def limpar_fc(fc):
    """Devolve a FC com NaN nas leituras implausíveis e o número removido."""
    fc = fc.astype(float)
    mediana = fc.rolling(JANELA, center=True, min_periods=3).median()
    mau = (fc < FC_MIN) | (fc > FC_MAX) | ((fc - mediana).abs() > SALTO_MAX)
    return fc.mask(mau), int(mau.sum())


def zonas_fc():
    """Limites inferiores das zonas 1–5, FC máxima e FC de repouso (bpm).

    Vêm do ficheiro da exportação completa da Garmin. Quem só exportou passeios soltos não o tem:
    nesse caso é criado um igual, com a FC máxima perguntada (ou estimada) e as percentagens da Garmin.
    """
    ficheiro = DADOS / "zonas_fc.json"
    if not ficheiro.exists():
        ficheiro.write_text(json.dumps([criar_zonas()]), encoding="utf-8")
    z = json.loads(ficheiro.read_text(encoding="utf-8"))[0]
    repouso = z.get("restingHeartRateUsed") or FC_REPOUSO_OMISSAO
    return [z[f"zone{i}Floor"] for i in range(1, 6)], z["maxHeartRateUsed"], repouso, z.get("origem")


def perguntar(texto):
    """Pergunta na janela; devolve "" se não houver ninguém a responder (ex.: corrido por outro programa)."""
    if sys.stdin is None or not sys.stdin.isatty():
        return ""
    try:
        return input(texto).strip()
    except EOFError:
        return ""


def numero(texto, minimo, maximo):
    try:
        n = int(texto)
    except ValueError:
        return None
    return n if minimo <= n <= maximo else None


def criar_zonas(fc_max=None, idade=None, perguntar_ao_utilizador=True):
    """fc_max e idade já sabidas (a versão web pergunta na página); senão pergunta na janela."""
    passeios = [ler_com_cache(f) for f in DADOS.glob("*.fit")]
    recente = max(passeios, key=lambda x: x[1]["inicio"])[1]
    vista = max((limpar_fc(df["heart_rate"])[0].max() for df, _ in passeios), default=np.nan)
    if perguntar_ao_utilizador:
        print("\nAinda não sei as tuas zonas de frequência cardíaca (FC). Só pergunto esta vez.")
        fc_max = numero(perguntar(
            "Qual é a tua FC máxima? Está no Garmin Connect, nas definições, em \"Zonas de frequência cardíaca\".\n"
            "Escreve o número, ou carrega Enter se não souberes: "), 120, 230)
    if fc_max:
        origem = "indicada por ti"
    else:
        if perguntar_ao_utilizador:
            idade = numero(perguntar("Então escreve a tua idade (ou Enter para saltar): "), 10, 90)
        if idade:
            fc_max, origem = 220 - idade, "220 menos a idade, como a Garmin faz por omissão"
        elif pd.notna(vista):
            fc_max, origem = int(vista), "a mais alta dos teus passeios, provavelmente abaixo da real"
        else:
            fc_max, origem = 190, "valor por omissão, os passeios não têm FC"
    repouso = recente.get("fc_repouso") or FC_REPOUSO_OMISSAO
    print(f"FC máxima: {fc_max} bpm ({origem}); FC de repouso: {repouso} bpm.\n"
          f"Para mudar, apaga o ficheiro {Path('dados') / 'zonas_fc.json'} e volta a correr.\n")
    z = {"trainingMethod": "HR_MAX", "origem": origem, "restingHeartRateUsed": repouso, "maxHeartRateUsed": fc_max}
    z.update({f"zone{i}Floor": round(fc_max * pct) for i, pct in enumerate(PCT_ZONAS, start=1)})
    return z


def tempo_em_zonas(df, limites):
    """Minutos em cada zona (Z1..Z5) usando a FC limpa e o intervalo real entre amostras."""
    dt = df["timestamp"].diff().dt.total_seconds().clip(upper=PAUSA_S).fillna(0)
    zona = np.digitize(df["fc_limpa"], limites)  # 0 = abaixo de Z1, 1..5 = Z1..Z5
    validos = df["fc_limpa"].notna() & (zona > 0)
    return {f"Z{z}": dt[validos & (zona == z)].sum() / 60 for z in range(1, 6)}


def velocidade_no_plano(df):
    """Velocidade média (km/h) e km feitos nos troços planos, para as subidas não baralharem a comparação.

    A distância vem da velocidade × tempo e a inclinação da altitude 100 m antes e 100 m depois
    de cada ponto (a altitude ponto a ponto tem demasiado ruído).
    """
    d = df.dropna(subset=["enhanced_speed", "enhanced_altitude"])
    if len(d) < 2:
        return np.nan, 0.0  # rolo: sem velocidade nem altitude
    dt = d["timestamp"].diff().dt.total_seconds().clip(upper=PAUSA_S).fillna(0).to_numpy()
    passo = d["enhanced_speed"].to_numpy() * dt
    dist = passo.cumsum()
    alt = d["enhanced_altitude"].rolling(5, center=True, min_periods=1).median().to_numpy()
    dist_u, i = np.unique(dist, return_index=True)
    w = JANELA_INCLINACAO
    inc = (np.interp(dist + w, dist_u, alt[i]) - np.interp(dist - w, dist_u, alt[i])) / (2 * w) * 100
    plano = (np.abs(inc) < PLANO) & (d["enhanced_speed"].to_numpy() > V_MOVIMENTO)
    km, horas = passo[plano].sum() / 1000, dt[plano].sum() / 3600
    return (km / horas if km >= KM_PLANO_MIN else np.nan), km


def principal():
    SAIDA.mkdir(exist_ok=True)
    CACHE.mkdir(exist_ok=True)
    if not any(DADOS.glob("*.fit")):
        print("Ainda não há passeios na pasta dados: não há nada para analisar.")
        return
    limites, fc_max, relatorio.FC_REPOUSO, relatorio.ORIGEM_ZONAS = zonas_fc()
    passeios, trajetos, series = [], {}, {}
    ficheiros = sorted(DADOS.glob("*.fit"))
    for n, f in enumerate(ficheiros):
        if PROGRESSO:
            PROGRESSO(n, len(ficheiros))
        df, info = ler_com_cache(f)
        series[info["id"]] = df
        df["fc_limpa"], removidas = limpar_fc(df["heart_rate"])
        mov = df[df["enhanced_speed"] > V_MOVIMENTO]
        vel_plano, km_plano = velocidade_no_plano(df)
        info.update(
            fim=df["timestamp"].iloc[-1] if len(df) else info["inicio"],
            vel_plano=vel_plano,
            km_plano=km_plano,
            fc_removida_pct=100 * removidas / max(len(df), 1),
            vel_media=mov["vel_kmh"].mean(),
            fc_media=mov["fc_limpa"].mean(),
            fc_max=df["fc_limpa"].max(),
            **tempo_em_zonas(df, limites),
        )
        passeios.append(info)
        gps = df.dropna(subset=["lat", "lon"])[["lat", "lon"]]
        trajetos[info["id"]] = gps.iloc[:0] if info["tipo"] in VIRTUAIS else gps
    p = (pd.DataFrame(passeios).drop_duplicates("inicio")  # o mesmo passeio exportado duas vezes
         .sort_values("inicio").reset_index(drop=True))
    p["suspeito"] = p["fc_removida_pct"] > 100 * LIMITE_SUSPEITO
    p["conta"] = (p["km"] >= KM_MIN) & ~p["tipo"].isin(VIRTUAIS)
    if not p["conta"].any():
        print(f"Nenhum passeio na rua com {KM_MIN} km ou mais: o relatório precisa de pelo menos um.")
        return

    fora = p[~p["conta"]]
    print(f"{len(p)} passeios, {p['km'].sum():.0f} km. Fora das médias ({len(fora)}): "
          + ", ".join(f"{r.inicio:%d/%m/%Y} ({r.km:.1f} km, {r.tipo})" for r in fora.itertuples()))
    if p["suspeito"].any():
        print("FC suspeita em:", ", ".join(f"{d:%d/%m/%Y}" for d in p.loc[p["suspeito"], "inicio"]))
    juntar_meteo(p, trajetos)
    p["volta"], voltas = voltas_habituais(p, trajetos)
    print("Voltas habituais:", "; ".join(f"{v['nome']} ({v['vezes']}×)" for v in voltas) or "nenhuma")
    p.to_csv(SAIDA / "passeios.csv", index=False)

    mapa_calor(p, trajetos, voltas, SAIDA / "mapa_calor.html")
    relatorio.gerar(p, series, limites, fc_max, voltas, SAIDA / "relatorio.html")
    app_movel.gerar(p, series, limites, fc_max, voltas, SAIDA / "app.html")

    if PUBLICAR:
        publico(p, trajetos, series, limites, fc_max, voltas)
    print("Pronto: abre saida/relatorio.html")


def publico(p, trajetos, series, limites, fc_max, voltas):
    """Versão para publicar: sem os sítios de onde costumas partir (ver privacidade.py)."""
    import privacidade
    zs = privacidade.zonas(trajetos)
    PUBLICO.mkdir(exist_ok=True)
    mapa_calor(p, {k: privacidade.ocultar_trajeto(t, zs) for k, t in trajetos.items()}, voltas,
               PUBLICO / "mapa_calor.html")
    series_pub = {k: privacidade.ocultar_serie(s, zs) for k, s in series.items()}
    relatorio.gerar(p, series_pub, limites, fc_max, voltas, PUBLICO / "relatorio.html")
    app_movel.gerar(p, series_pub, limites, fc_max, voltas, PUBLICO / "app.html")
    privacidade.verificar([PUBLICO / "mapa_calor.html", PUBLICO / "relatorio.html", PUBLICO / "app.html"], zs, trajetos)


def juntar_meteo(p, trajetos):
    """Acrescenta a p a temperatura (°C), o vento (km/h) e a humidade (%) médios de cada passeio.

    Pede ao Open-Meteo só o centro da zona arredondado a ~10 km (ver meteo.py). Sem internet,
    as colunas ficam vazias e o relatório sai na mesma, sem a parte do tempo.
    """
    p[["temp", "vento", "humidade"]] = np.nan
    inicios = [t.iloc[0] for t in trajetos.values() if len(t)]
    if not inicios:
        return
    lat, lon = np.median([x["lat"] for x in inicios]), np.median([x["lon"] for x in inicios])
    try:
        m = meteo.horario(lat, lon, p["inicio"].min(), p["fim"].max(), CACHE)
    except Exception as e:  # sem rede, serviço em baixo, ...
        print(f"Aviso: sem meteorologia ({e}); o relatório sai sem a parte do tempo.")
        return
    for i, r in p.iterrows():
        for k, v in meteo.durante(m, r["inicio"], r["fim"]).items():
            p.at[i, k] = v


def celulas_do_trajeto(t):
    """Sequência de células da grelha por onde o trajeto passa, sem saltar nenhuma.

    Entre dois pontos de GPS seguidos (7–35 m a andar) acrescenta pontos intermédios, senão um passeio
    podia ir A→C na diagonal e outro A→B→C na mesma estrada. Saltos grandes (falha de GPS) não se ligam.
    Devolve também todos os pontos (em unidades da grelha) e a célula de cada um, para as médias de posição.
    """
    xy = t[["lat", "lon"]].to_numpy() / GRELHA
    pedacos = [xy[:1]]
    for p, q in zip(xy[:-1], xy[1:]):
        d = np.abs(q - p).max()
        if d > 3:
            pedacos.append(np.array([[np.nan, np.nan], q]))  # NaN = corte
        elif d > 0.5:
            f = np.linspace(0, 1, int(np.ceil(d / 0.5)) + 1)[1:, None]
            pedacos.append(p + f * (q - p))
        else:
            pedacos.append(q[None])
    pts = np.vstack(pedacos)
    cel = np.round(np.nan_to_num(pts)).astype(np.int64)
    cel[np.isnan(pts).any(axis=1)] = CORTE
    seq = cel[np.r_[True, (np.diff(cel, axis=0) != 0).any(axis=1)]]  # tira repetidos seguidos
    return seq, cel, pts


def passeios_por_troco(trajetos):
    """Para cada troço (par de células vizinhas da grelha), a lista dos passeios que lá passaram.

    Conta passeios e não pontos de GPS: um troço feito devagar ou com paragens não pesa mais.
    Um passeio conta numa célula se passou nela ou numa encostada (~65 m): o erro do GPS
    não parte assim a mesma estrada em traços paralelos com contagens diferentes.
    trajetos: lista indexada pelo nº do passeio.

    Devolve também, para cada célula, a posição média (lat, lon) dos pontos de GPS que lá caíram:
    desenhar entre essas médias segue a estrada, entre os centros das células faz escadinhas.
    """
    vizinhas = [(i, j) for i in (-1, 0, 1) for j in (-1, 0, 1)]
    por_celula, troços, soma = {}, set(), {}
    for i, t in enumerate(trajetos):
        seq, cel, pts = celulas_do_trajeto(t)
        validas = {tuple(c) for c in seq if c[0] != CORTE}
        for c in {(c[0] + di, c[1] + dj) for c in validas for di, dj in vizinhas}:
            por_celula.setdefault(c, set()).add(i)
        for c, xy in zip(map(tuple, cel), pts):
            if c[0] != CORTE:
                s = soma.setdefault(c, [0.0, 0.0, 0])
                s[0] += xy[0]
                s[1] += xy[1]
                s[2] += 1
        for a, b in zip(map(tuple, seq[:-1]), map(tuple, seq[1:])):
            if a[0] != CORTE and b[0] != CORTE:
                troços.add((min(a, b), max(a, b)))
    centro = {c: (s[0] / s[2] * GRELHA, s[1] / s[2] * GRELHA) for c, s in soma.items()}
    return {(a, b): sorted(por_celula[a] & por_celula[b]) for a, b in troços}, centro


def voltas_habituais(p, trajetos):
    """Agrupa os passeios que fazem o mesmo percurso. Devolve a coluna 'volta' (0 = nenhuma) e as voltas.

    Semelhança entre dois passeios = fração das células de ~200 m em comum (Jaccard), o que apanha o
    mesmo percurso feito em qualquer sentido. Os grupos juntam-se enquanto, em média, os seus passeios
    partilharem pelo menos SEMELHANCA_MIN do percurso (ligação média, para não encadear percursos diferentes).
    """
    idx = [i for i, r in p.iterrows() if r["conta"] and len(trajetos[r["id"]]) > 1]
    cel = []
    for i in idx:
        _, _, pts = celulas_do_trajeto(trajetos[p.at[i, "id"]])
        pts = pts[~np.isnan(pts).any(axis=1)] * GRELHA
        cel.append({tuple(c) for c in np.round(pts / GROSSA).astype(int)})
    n = len(cel)
    sem = np.eye(n)
    for a in range(n):
        for b in range(a + 1, n):
            sem[a, b] = sem[b, a] = len(cel[a] & cel[b]) / len(cel[a] | cel[b])
    grupos = [[k] for k in range(n)]
    while len(grupos) > 1:
        s, x, y = max((sem[np.ix_(g, h)].mean(), x, y)
                      for x, g in enumerate(grupos) for y, h in enumerate(grupos) if x < y)
        if s < SEMELHANCA_MIN:
            break
        grupos[x] += grupos.pop(y)
    grupos = sorted((g for g in grupos if len(g) >= VOLTA_MIN), key=len, reverse=True)[:N_VOLTAS]

    volta, voltas = pd.Series(0, index=p.index), []
    for k, g in enumerate(grupos, 1):
        linhas = [idx[j] for j in g]
        volta[linhas] = k
        # rumo: do início do passeio mais típico da volta até ao ponto mais afastado
        t = trajetos[p.at[idx[g[int(sem[np.ix_(g, g)].mean(axis=1).argmax())]], "id"]]
        lat0, lon0 = t.iloc[0]
        dlat, dlon = t["lat"] - lat0, (t["lon"] - lon0) * np.cos(np.radians(lat0))
        longe = int(np.hypot(dlat, dlon).argmax())
        rumo = RUMOS[int((np.degrees(np.arctan2(dlon.iloc[longe], dlat.iloc[longe])) % 360 + 22.5) // 45) % 8]
        km = p.loc[linhas, "km"].median()
        voltas.append({"n": k, "nome": f"Volta {k}: ~{km:.0f} km para {rumo}", "km": km, "vezes": len(g)})
    return volta, voltas


def periodos(datas):
    """Opções do filtro de período, contadas a partir do último passeio (não de hoje)."""
    fim = datas.max().normalize()
    iso = lambda d: d.strftime("%Y-%m-%d")
    opcoes = [("Tudo", datas.min(), fim)]
    for rot, dias in (("Último mês", 30), ("Últimos 3 meses", 91), ("Últimos 6 meses", 182)):
        opcoes.append((rot, fim - pd.Timedelta(days=dias - 1), fim))
    for ano in sorted(datas.dt.year.unique(), reverse=True):
        opcoes.append((str(ano), pd.Timestamp(int(ano), 1, 1), pd.Timestamp(int(ano), 12, 31)))
    return [{"rot": r, "de": iso(de), "ate": iso(ate)} for r, de, ate in opcoes]


def mapa_calor(p, trajetos, voltas, destino):
    p = p[p["id"].map(lambda i: len(trajetos[i]) > 1)].reset_index(drop=True)  # rolo não tem GPS
    if p.empty:
        destino.write_text('<!doctype html><meta charset="utf-8"><title>Mapa</title>'
                           '<p style="font:16px system-ui;padding:2em">Nenhum passeio tem GPS: não há mapa para mostrar.</p>',
                           encoding="utf-8")
        return
    tr = [trajetos[i] for i in p["id"]]
    por_troco, centro = passeios_por_troco(tr)
    pts = pd.concat(tr).dropna()
    # Os tiles do OpenStreetMap são bloqueados (403) quando o HTML é aberto do disco, sem Referer;
    # os da Esri não pedem Referer nem chave.
    m = folium.Map(location=[pts["lat"].mean(), pts["lon"].mean()], zoom_start=11, tiles=None)
    esri = "https://server.arcgisonline.com/ArcGIS/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}"
    for servico, nome in (("World_Topo_Map", "Topográfico"), ("World_Street_Map", "Ruas")):
        # o fundo Ruas tem estradas a vermelho que se confundem com as linhas: Topográfico por omissão
        folium.TileLayer(esri.format(servico), attr="Tiles © Esri", name=nome, show=nome == "Topográfico").add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)  # só os fundos; as linhas são desenhadas por mapa.js
    m.fit_bounds([[pts["lat"].min(), pts["lon"].min()], [pts["lat"].max(), pts["lon"].max()]])

    # As linhas são desenhadas no browser, para o filtro de período poder recontar os passeios
    dados = {
        "escaloes": [{"lo": lo, "hi": hi, "cor": c, "larg": w,
                      "rot": "1 vez" if hi == 1 else f"{lo}–{hi} vezes" if hi < 999 else f"{lo} ou mais vezes"}
                     for (lo, hi), c, w in zip(ESCALOES, CORES_ESCALOES, LARGURAS)],
        "passeios": [{"d": r.inicio.strftime("%Y-%m-%d"), "km": round(r.km, 1), "vol": int(r.volta),
                      "v": None if pd.isna(r.vel_media) else round(r.vel_media, 1)} for r in p.itertuples()],
        "voltas": [{"n": v["n"], "rot": f"{v['nome']} ({v['vezes']}×)"} for v in voltas],
        # [lat A, lon A, lat B, lon B, passeios]; 5 casas decimais ≈ 1 m
        "trocos": [[*(round(v, 5) for v in centro[a] + centro[b]), ids] for (a, b), ids in por_troco.items()],
        "periodos": periodos(p["inicio"]),
    }
    js = (RAIZ / "mapa.js").read_text(encoding="utf-8").replace("__MAPA__", m.get_name())
    m.get_root().html.add_child(folium.Element(
        LEGENDA_HTML
        + '<script type="application/json" id="dados-mapa">'
        + json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        + f"</script><script>{js}</script>"))
    m.save(destino)


# Legenda que também filtra; o conteúdo (escalões, períodos) é preenchido por mapa.js
LEGENDA_HTML = """
<style>
  #legenda { position:fixed; bottom:24px; left:12px; z-index:1000; background:#fff; padding:10px 12px;
             border-radius:8px; box-shadow:0 1px 4px rgba(0,0,0,.3); font:14px system-ui,'Segoe UI',sans-serif; }
  #legenda .lin { display:flex; justify-content:space-between; align-items:center; gap:14px; line-height:1.9; }
  #legenda label { cursor:pointer; display:flex; align-items:center; gap:6px; }
  #legenda .cor { display:inline-block; width:24px; }
  #legenda a { color:#2a78d6; font-size:12px; text-decoration:none; }
  #legenda button { margin-top:6px; padding:3px 10px; border:1px solid #c3c2b7; border-radius:5px; background:#fff; cursor:pointer; }
  #legenda select { font:inherit; padding:2px 4px; margin:2px 0 4px; max-width:260px; }
  #legenda .nota { color:#666; font-size:12px; margin-top:6px; max-width:260px; }
  #legenda hr { border:0; border-top:1px solid #e1e0d9; margin:8px 0; }
  #legenda #abrir { margin:0; border:0; padding:0; font:inherit; font-weight:700; background:none; }
  #legenda.fechada .corpo { display:none; }
  @media (max-width:600px) {
    #legenda { left:8px; right:8px; bottom:8px; font-size:13px; max-height:70vh; overflow-y:auto; }
  }
  .lista-passeios { max-height:220px; overflow-y:auto; margin-top:6px; }
  .lista-passeios table { border-collapse:collapse; font-size:13px; font-variant-numeric:tabular-nums; }
  .lista-passeios th, .lista-passeios td { padding:2px 8px; text-align:right; border-bottom:1px solid #eee; }
  .lista-passeios th:first-child, .lista-passeios td:first-child { text-align:left; }
</style>
<div id="legenda">
  <button id="abrir" aria-expanded="true">▾ Legenda e filtros</button>
  <div class="corpo">
    <hr>
    <b>Período</b><br>
    <select id="periodo"></select><br>
    <b>Volta</b><br>
    <select id="volta"></select>
    <div class="nota" id="info-periodo"></div>
    <hr>
    <b>Quantas vezes passei em cada troço</b>
    <div id="escaloes"></div>
    <button data-todos="1">Todos</button> <button data-todos="0">Nenhum</button>
    <div class="nota">Clica numa linha para ver os passeios que lá passaram</div>
  </div>
</div>
"""


if __name__ == "__main__":
    principal()
