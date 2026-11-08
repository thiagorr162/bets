"""Download dos microdados do DATASUS direto do FTP: cada .dbc fica guardado em data/raw/datasus/ (e é
reaproveitado nas próximas execuções) e é agregado na hora.

Os agregados ficam em data/interim/<fonte>/<arquivo>.parquet, então dá para interromper e retomar.
Códigos de município do DATASUS têm 6 dígitos (IBGE sem dígito verificador).

Não usamos o pysus: ele guarda um catálogo DuckDB com trava de arquivo e não aceita vários processos ao
mesmo tempo. Baixando o .dbc direto do FTP dá para paralelizar. Conferido: o agregado sai idêntico ao do pysus.
"""

from pathlib import Path

import polars as pl

from src.config import INTERIM

# CID-10
F63 = r"^F63"  # transtornos dos hábitos e impulsos (F63.0 = jogo patológico)
MENTAL = r"^F"  # capítulo V inteiro
SUBST = r"^F1"  # uso de substâncias (F10-F19)
AUTOLESAO = r"^X(6\d|7\d|8[0-4])"  # lesões autoprovocadas (X60-X84)

FTP = "ftp://ftp.datasus.gov.br/dissemin/publicos"


def listar_ftp(diretorio: str) -> list[str]:
    from urllib.request import urlopen

    with urlopen(f"{FTP}/{diretorio}/", timeout=120) as r:
        linhas = r.read().decode("latin1").splitlines()
    return [ln.split()[-1] for ln in linhas if ln.strip()]


RAW_DATASUS = INTERIM.parent / "raw" / "datasus"


def bruto(url: str) -> Path:
    """Caminho do .dbc original em data/raw/datasus/<pasta do FTP>/; baixa só se ainda não estiver lá."""
    from urllib.request import urlopen

    destino = RAW_DATASUS / url.split("/dissemin/publicos/", 1)[1]
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(".part")
        with urlopen(url, timeout=600) as r, open(tmp, "wb") as f:
            f.write(r.read())
        tmp.rename(destino)
    return destino


def _processar_ftp(args) -> str:
    """Roda num processo separado: usa o .dbc guardado em data/raw/datasus/ (ou baixa e guarda lá),
    converte para .dbf, lê só as colunas úteis e agrega. O .dbc original nunca é apagado."""
    import tempfile
    from urllib.request import urlopen

    from dbfread import DBF
    from pyreaddbc import dbc2dbf

    url, destino, agregador, colunas = args
    dbc = bruto(url)
    with tempfile.TemporaryDirectory() as tmp:
        dbf = Path(tmp) / "a.dbf"
        dbc2dbf(str(dbc), str(dbf))
        tabela = DBF(str(dbf), encoding="iso-8859-1", char_decode_errors="replace")
        cols = [c for c in colunas if c in tabela.field_names]
        dados = {c: [] for c in cols}
        for reg in tabela:
            for c in cols:
                v = reg[c]  # campos numéricos do DBF (ex.: IDADE no SIH) viram texto, como os demais
                dados[c].append(v if v is None or isinstance(v, str) else str(v))
        df = pl.DataFrame(dados, schema={c: pl.String for c in cols})
    saida = agregador(df)
    # o agregador pode devolver várias tabelas: {"nome": df} -> <pasta>/<nome>/<arquivo>.parquet
    if isinstance(saida, dict):
        for k, v in saida.items():
            (destino.parent / k).mkdir(parents=True, exist_ok=True)
            v.write_parquet(destino.parent / k / destino.name)
    else:
        saida.write_parquet(destino)
    return destino.stem


def rodar_ftp(fonte: str, diretorio: str, nomes: list[str], agregador, colunas: list[str], processos: int = 8):
    """Baixa `nomes` (ex.: 'PSSP2401') de `diretorio` no FTP em paralelo e grava os agregados em
    data/interim/<fonte>/. Pula o que já existe. Arquivos divididos em partes (PSSP2401a, b...) são
    agregados juntos e somados."""
    from concurrent.futures import ProcessPoolExecutor, as_completed

    pasta = INTERIM / fonte
    pasta.mkdir(parents=True, exist_ok=True)
    disponiveis = {n.rsplit(".", 1)[0].upper(): n for n in listar_ftp(diretorio) if n.lower().endswith(".dbc")}
    tarefas = []
    for nome in nomes:
        if any(pasta.rglob(f"{nome}*.parquet")):
            continue
        partes = [arq for base, arq in disponiveis.items() if base == nome or (base[:-1] == nome and base[-1].isalpha())]
        for arq in partes:
            sufixo = "" if len(partes) == 1 else "_" + arq.rsplit(".", 1)[0][-1]
            tarefas.append((f"{FTP}/{diretorio}/{arq}", pasta / f"{nome}{sufixo}.parquet", agregador, colunas))
    print(f"  {len(tarefas)} arquivos a baixar ({len(nomes)} pedidos, {processos} processos)")
    # "spawn", não "fork": se o processo pai já usou o polars (que tem pool de threads), um fork pode
    # deixar os filhos travados para sempre (aconteceu na passada 2 do sia_f63_pacientes)
    import multiprocessing

    with ProcessPoolExecutor(processos, mp_context=multiprocessing.get_context("spawn")) as ex:
        futuros = {ex.submit(_processar_ftp, t): t for t in tarefas}
        for i, f in enumerate(as_completed(futuros), 1):
            try:
                print(f"  [{i}/{len(tarefas)}] {f.result()} ✓", flush=True)
            except Exception as e:
                print(f"  [{i}/{len(tarefas)}] {futuros[f][1].stem} ! {e}", flush=True)
    return pasta


def baixar_brutos(diretorio: str, prefixos: list[str], threads: int = 8) -> int:
    """Baixa para data/raw/datasus/ os .dbc de `diretorio` cujo nome começa por algum dos `prefixos`
    (ex.: ["PS"]), sem processar. Pula os que já estão no disco. Retorna quantos foram baixados."""
    from concurrent.futures import ThreadPoolExecutor

    arqs = [a for a in listar_ftp(diretorio) if a.lower().endswith(".dbc") and a.upper().startswith(tuple(prefixos))]
    faltam = [a for a in arqs if not (RAW_DATASUS / diretorio / a).exists()]
    print(f"  {len(arqs)} arquivos no FTP, {len(faltam)} a baixar para {RAW_DATASUS / diretorio}")
    with ThreadPoolExecutor(threads) as ex:
        for i, _ in enumerate(ex.map(lambda a: bruto(f"{FTP}/{diretorio}/{a}"), faltam), 1):
            if i % 200 == 0:
                print(f"  {i}/{len(faltam)}", flush=True)
    return len(faltam)
