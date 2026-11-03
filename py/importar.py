"""Importa passeios de bicicleta (.fit) para dados/ e volta a gerar o relatório e o mapa.

Aceita a exportação completa da Garmin (.zip), os .zip de uma só atividade do Garmin Connect,
.fit soltos e pastas. Só copia passeios de ciclismo que ainda não estejam em dados/ (compara a
hora de início). Os ficheiros de origem nunca são alterados nem apagados.

Sem caminhos, procura nas Transferências os .zip e .fit novos desde a última importação.
"""
import argparse
import io
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
from fitparse import FitFile

import analisar



def pasta_transferencias():
    """A pasta Transferências verdadeira, mesmo que tenha sido mudada de sítio (outro disco, OneDrive)."""
    if sys.platform != "win32":
        return Path.home() / "Downloads"  # Mac e Linux
    try:
        import ctypes
        from uuid import UUID
        guid = (ctypes.c_byte * 16).from_buffer_copy(UUID("374DE290-123F-4565-9164-39C4925E467B").bytes_le)
        caminho = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(caminho)) == 0:
            p = Path(caminho.value)
            ctypes.windll.ole32.CoTaskMemFree(caminho)
            if p.is_dir():
                return p
    except (AttributeError, OSError):
        pass
    return Path.home() / "Downloads"


TRANSFERENCIAS = pasta_transferencias()
MARCA = analisar.CACHE / "ultima_importacao.txt"
LANCADOR = "Atualizar.bat" if sys.platform == "win32" else "Atualizar.command"
COMO_EXPORTAR = """
Ainda não encontrei passeios de bicicleta. Para os trazer do Garmin:
  1. No computador, abre connect.garmin.com e entra na tua conta.
  2. Abre um passeio, carrega na roda dentada (canto superior direito) e escolhe "Exportar original".
     Repete para cada passeio que quiseres. Os ficheiros vão para as Transferências.
  3. Volta a fazer duplo clique em {lancador}.
Para trazer todos de uma vez: no Garmin Connect, Definições da conta > Gestão de dados >
Exportar dados. A Garmin manda um email com um .zip (pode demorar uns dias); descarrega-o
para as Transferências e faz duplo clique em {lancador}."""


def fits_em(caminho):
    """Gera (nome, bytes) de cada .fit num .fit, num .zip (incluindo a exportação completa) ou numa pasta."""
    if caminho.is_dir() and (caminho / "DI_CONNECT").is_dir():
        # exportação completa que o browser já descompactou (o Safari faz isto sozinho)
        for f in sorted((caminho / "DI_CONNECT").rglob("*")):
            if f.suffix.lower() == ".fit" or (f.suffix.lower() == ".zip" and f.name.startswith("UploadedFiles")):
                yield from fits_em(f)
    elif caminho.is_dir():
        for f in sorted(caminho.iterdir()):
            if f.suffix.lower() in (".fit", ".zip"):
                yield from fits_em(f)
    elif caminho.suffix.lower() == ".fit":
        yield caminho.name, caminho.read_bytes()
    elif caminho.suffix.lower() == ".zip":
        yield from fits_no_zip(zipfile.ZipFile(caminho))


def fits_no_zip(z):
    """Lê os .fit sem extrair nada para o disco. Na exportação completa estão num zip dentro do zip."""
    with z:
        for e in z.infolist():
            nome = e.filename.rsplit("/", 1)[-1]
            if nome.lower().endswith(".fit"):
                yield nome, z.read(e)
            elif nome.lower().endswith(".zip") and nome.startswith("UploadedFiles"):
                yield from fits_no_zip(zipfile.ZipFile(io.BytesIO(z.read(e))))


def zonas_no_zip(caminho):
    """Conteúdo do ficheiro de zonas de FC da exportação completa, ou None."""
    if caminho.is_dir():
        for f in caminho.rglob("*_heartRateZones.json"):
            return f.read_bytes()
        return None
    if caminho.suffix.lower() != ".zip":
        return None
    with zipfile.ZipFile(caminho) as z:
        for e in z.infolist():
            if e.filename.endswith("_heartRateZones.json"):
                return z.read(e)
    return None


def inicio_se_ciclismo(dados):
    """Hora de início se o .fit for um passeio de bicicleta; None para tudo o resto (sono, corrida, ...)."""
    try:
        fit = FitFile(io.BytesIO(dados))
        if next(iter(fit.get_messages("file_id"))).get_values().get("type") != "activity":
            return None  # a maior parte da exportação é monitorização diária: sai aqui, sem ler o resto
        s = next(iter(fit.get_messages("session")), None)
        if s is None or s.get_values().get("sport") != "cycling":
            return None
        return pd.Timestamp(s.get_values()["start_time"])
    except Exception:
        return None  # ficheiro estragado ou de um tipo que o fitparse não conhece


def novidades_nas_transferencias(tudo):
    if not TRANSFERENCIAS.is_dir():
        print(f"Não encontrei a pasta das Transferências ({TRANSFERENCIAS}).")
        return []
    desde = None if tudo or not MARCA.exists() else datetime.fromisoformat(MARCA.read_text().strip())
    fs = sorted(f for f in TRANSFERENCIAS.iterdir()
                if (f.is_file() and f.suffix.lower() in (".zip", ".fit") or (f / "DI_CONNECT").is_dir())
                and (desde is None or datetime.fromtimestamp(f.stat().st_mtime) > desde))
    quando = "desde sempre" if desde is None else f"desde {desde:%d/%m/%Y %H:%M}"
    print(f"Transferências ({quando}): {len(fs)} ficheiro(s) .zip/.fit para ver")
    return fs


def importar_caminhos(caminhos, progresso=None):
    """Copia para dados/ os passeios de bicicleta novos que estão nos caminhos (.fit, .zip ou pastas).

    Devolve (novos, repetidos, vistos, zonas_mudaram). progresso(vistos, novos), se existir, é chamada
    de vez em quando (a versão web usa-a para mostrar o andamento).
    """
    existentes = {analisar.ler_com_cache(f)[1]["inicio"] for f in analisar.DADOS.glob("*.fit")}
    novos, repetidos, vistos, zonas_mudaram = [], 0, 0, False

    for c in caminhos:
        if not c.exists():
            print(f"  ! não existe: {c}")
            continue
        try:
            antes = vistos
            for nome, dados in fits_em(c):
                vistos += 1
                if progresso and vistos % 25 == 0:
                    progresso(vistos, len(novos))
                inicio = inicio_se_ciclismo(dados)
                if inicio is None:
                    continue
                if inicio in existentes:
                    repetidos += 1
                    continue
                destino = analisar.DADOS / nome
                if destino.exists():  # mesmo nome mas outro passeio: junta a data para não sobrepor
                    destino = destino.with_stem(f"{destino.stem}_{inicio:%Y%m%d_%H%M}")
                destino.write_bytes(dados)
                existentes.add(inicio)
                novos.append((inicio, destino.name))
            zonas = zonas_no_zip(c)
            ficheiro_zonas = analisar.DADOS / "zonas_fc.json"
            if zonas and (not ficheiro_zonas.exists() or ficheiro_zonas.read_bytes() != zonas):
                ficheiro_zonas.write_bytes(zonas)
                zonas_mudaram = True
            if vistos > antes:
                print(f"  {c.name}: {vistos - antes} ficheiro(s) .fit")
        except zipfile.BadZipFile:
            print(f"  ! {c.name} não é um .zip válido; ignorado")

    return novos, repetidos, vistos, zonas_mudaram


def principal():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("caminhos", nargs="*", type=Path, help=".zip, .fit ou pastas (por omissão: as Transferências)")
    ap.add_argument("--tudo", action="store_true", help="sem caminhos: ver todas as Transferências, não só o que é novo")
    ap.add_argument("--sem-analise", action="store_true", help="só copiar; não voltar a gerar o relatório e o mapa")
    args = ap.parse_args()

    analisar.CACHE.mkdir(exist_ok=True)
    analisar.DADOS.mkdir(exist_ok=True)
    inicio_importacao = datetime.now()
    caminhos = args.caminhos or novidades_nas_transferencias(args.tudo)
    novos, repetidos, vistos, zonas_mudaram = importar_caminhos(caminhos)

    if not args.caminhos:  # só a procura nas Transferências avança a marca de "já visto"
        MARCA.write_text(inicio_importacao.isoformat(timespec="seconds"))
    print(f"\n{vistos} .fit vistos · {len(novos) + repetidos} passeios de bicicleta · "
          f"{len(novos)} novo(s) · {repetidos} já existiam")
    for inicio, nome in sorted(novos):
        print(f"  + {inicio:%d/%m/%Y %H:%M}  {nome}")
    if zonas_mudaram:
        print("  + zonas de FC atualizadas a partir da exportação")

    tem_passeios = any(analisar.DADOS.glob("*.fit"))
    sem_relatorio = not (analisar.SAIDA / "relatorio.html").exists()
    if not tem_passeios:
        print(COMO_EXPORTAR.format(lancador=LANCADOR))
    elif (novos or zonas_mudaram or sem_relatorio) and not args.sem_analise:
        print("\nA gerar o relatório e o mapa...")
        analisar.principal()
    elif not novos:
        print("Nada de novo: o relatório e o mapa ficam como estavam.")


if __name__ == "__main__":
    principal()
