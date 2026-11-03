"""Ponte entre a página web e o código de análise. Corre dentro do browser (Pyodide).

A página monta os ficheiros escolhidos em /entrada (sem os copiar para a memória), e as pastas
/dados e /cache ficam guardadas no próprio browser. Aqui só se usa o que já existe no programa:
importar.py (encontrar os passeios de bicicleta) e analisar.py (calcular e gerar o relatório e o mapa).
"""
import io
import json
import sys
from pathlib import Path

import analisar
import importar

ENTRADA = Path("/entrada")
DADOS, CACHE, SAIDA = Path("/dados"), Path("/cache"), Path("/saida")
FICHEIROS = ("relatorio.html", "app.html", "mapa_calor.html")


class Linhas(io.TextIOBase):
    """Reparte o que o programa escreve (print) em linhas para a página mostrar."""

    def __init__(self, destino):
        self.destino, self.resto = destino, ""

    def write(self, texto):
        self.resto += texto
        while "\n" in self.resto:
            linha, self.resto = self.resto.split("\n", 1)
            if linha.strip():
                self.destino(linha)
        return len(texto)


def preparar():
    for pasta in (DADOS, CACHE, SAIDA):
        pasta.mkdir(parents=True, exist_ok=True)
    analisar.DADOS, analisar.CACHE, analisar.SAIDA = DADOS, CACHE, SAIDA
    analisar.PUBLICAR = False


def candidatos():
    """Ficheiros escolhidos: .fit e .zip (incluindo a exportação completa), mesmo dentro de pastas."""
    if not ENTRADA.exists():
        return [], []
    todos = [f for f in ENTRADA.rglob("*") if f.is_file()]
    fits = sorted(f for f in todos if f.suffix.lower() in (".fit", ".zip"))
    zonas = [f for f in todos if f.name.endswith("_heartRateZones.json")]
    return fits, zonas


def estado():
    """O que há guardado: nº de passeios e se já há zonas de FC."""
    preparar()
    return {"passeios": len(list(DADOS.glob("*.fit"))), "zonas": (DADOS / "zonas_fc.json").exists()}


def executar(progresso, mensagem, fc_max=None, idade=None, forcar=False, redefinir=False):
    """Importa o que está em /entrada e, se houver novidades (ou forcar), gera o relatório e o mapa.

    redefinir: volta a criar as zonas de FC com a FC máxima dada (o utilizador corrigiu o valor).
    """
    preparar()
    sys.stdout = Linhas(mensagem)
    try:
        fits, zonas = candidatos()
        novos, repetidos, vistos, zonas_mudaram = importar.importar_caminhos(fits, progresso)
        for z in zonas:  # exportação já descompactada pelo browser: o ficheiro de zonas vem solto
            destino = DADOS / "zonas_fc.json"
            if not destino.exists() or destino.read_bytes() != z.read_bytes():
                destino.write_bytes(z.read_bytes())
                zonas_mudaram = True
        total = len(list(DADOS.glob("*.fit")))
        resultado = {"vistos": vistos, "novos": len(novos), "repetidos": repetidos, "passeios": total, "gerado": False}
        if total == 0:
            return resultado
        if redefinir and fc_max:
            (DADOS / "zonas_fc.json").unlink(missing_ok=True)
            forcar = True
        if not (DADOS / "zonas_fc.json").exists():
            z = analisar.criar_zonas(fc_max=fc_max, idade=idade, perguntar_ao_utilizador=False)
            (DADOS / "zonas_fc.json").write_text(json.dumps([z]), encoding="utf-8")
            zonas_mudaram = True
        if novos or zonas_mudaram or forcar or not all((SAIDA / f).exists() for f in FICHEIROS):
            mensagem("A calcular o relatório e o mapa...")
            analisar.principal()
            resultado["gerado"] = True
        return resultado
    finally:
        sys.stdout = sys.__stdout__
