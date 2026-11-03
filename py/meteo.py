"""Meteorologia histórica (Open-Meteo, gratuito e sem conta) para a zona dos passeios.

Só sai do computador uma coordenada arredondada a 0,1° (~10 km: o centro da zona, não a casa)
e o intervalo de datas. A resposta fica em cache/ e só se volta a pedir quando faltam dias.
"""
import json
import ssl
import sys
import urllib.parse
import urllib.request

try:
    import certifi  # já vem com o folium; o Python do Mac não traz certificados de raiz
except ImportError:
    certifi = None  # no browser não é preciso

import numpy as np
import pandas as pd

URL = "https://archive-api.open-meteo.com/v1/archive"
VARIAVEIS = ["temperature_2m", "wind_speed_10m", "relative_humidity_2m"]


def horario(lat, lon, de, ate, cache_dir):
    """Tabela hora a hora (UTC) com temperatura (°C), vento (km/h) e humidade (%), entre duas datas."""
    lat, lon = round(lat, 1), round(lon, 1)
    ficheiro = cache_dir / f"meteo_{lat}_{lon}.json"
    if ficheiro.exists():
        t = _tabela(json.loads(ficheiro.read_text(encoding="utf-8"))["hourly"])
        cobre = t.index[0] <= pd.Timestamp(de).floor("D") and t.index[-1] >= pd.Timestamp(ate).floor("D") + pd.Timedelta(hours=23)
        # o arquivo só tem os últimos ~5 dias mais tarde: dias recentes vêm vazios e voltam a ser pedidos
        if cobre and not t.loc[pd.Timestamp(de).floor("D"):pd.Timestamp(ate), "temperature_2m"].isna().any():
            return t
    params = {"latitude": lat, "longitude": lon, "start_date": f"{de:%Y-%m-%d}", "end_date": f"{ate:%Y-%m-%d}",
              "hourly": ",".join(VARIAVEIS), "timezone": "UTC", "wind_speed_unit": "kmh"}
    endereco = f"{URL}?{urllib.parse.urlencode(params)}"
    if sys.platform == "emscripten":  # no browser (Pyodide) não há sockets: o pedido é feito pelo próprio browser
        from pyodide.http import open_url
        dados = json.loads(open_url(endereco).read())
    else:
        contexto = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(endereco, timeout=60, context=contexto) as r:
            dados = json.loads(r.read().decode("utf-8"))
    ficheiro.write_text(json.dumps(dados), encoding="utf-8")
    return _tabela(dados["hourly"])


def _tabela(h):
    t = pd.DataFrame(h)
    t["time"] = pd.to_datetime(t["time"])
    return t.set_index("time")


def durante(meteo, inicio, fim):
    """Médias de temperatura, vento e humidade entre o início e o fim de um passeio (horas inteiras incluídas)."""
    janela = meteo.loc[inicio.floor("h"):fim.ceil("h")]
    if janela.empty or janela["temperature_2m"].isna().all():
        return {"temp": np.nan, "vento": np.nan, "humidade": np.nan}
    return {"temp": janela["temperature_2m"].mean(), "vento": janela["wind_speed_10m"].mean(),
            "humidade": janela["relative_humidity_2m"].mean()}
