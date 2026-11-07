"""Loop genérico DATASUS via pysus: baixa um arquivo por UF/período, agrega, guarda e apaga o bruto.

Os agregados ficam em data/interim/<fonte>/<arquivo>.parquet, então dá para interromper e retomar.
Códigos de município do DATASUS têm 6 dígitos (IBGE sem dígito verificador).
"""

import warnings
from collections.abc import Callable
from pathlib import Path

import polars as pl
import pysus

from src.config import INTERIM

warnings.filterwarnings("ignore", category=pysus.PySUSWarning)
pysus.disable_progress_bars()

# CID-10
F63 = r"^F63"  # transtornos dos hábitos e impulsos (F63.0 = jogo patológico)
MENTAL = r"^F"  # capítulo V inteiro
SUBST = r"^F1"  # uso de substâncias (F10-F19)
AUTOLESAO = r"^X(6\d|7\d|8[0-4])"  # lesões autoprovocadas (X60-X84)


def rodar(fonte: str, chamadas: list[tuple[str, dict]], agregador: Callable[[pl.DataFrame], pl.DataFrame]):
    """`chamadas`: lista de (nome_arquivo, kwargs para pysus.ftp.<fonte>)."""
    pasta = INTERIM / fonte
    pasta.mkdir(parents=True, exist_ok=True)
    func = getattr(pysus.ftp, fonte)
    for i, (nome, kw) in enumerate(chamadas, 1):
        destino = pasta / f"{nome}.parquet"
        if destino.exists():
            continue
        try:
            bag = func(**kw)
            if not bag.paths:
                continue
            for p in bag.paths:
                df = pl.read_parquet(p)
                agregador(df).write_parquet(destino)
                Path(p).unlink(missing_ok=True)
            print(f"  [{i}/{len(chamadas)}] {nome} ✓")
        except Exception as e:
            print(f"  [{i}/{len(chamadas)}] {nome} ! {e}")
    return pasta


# --- Download direto do FTP (sem pysus) -------------------------------------------------------
# O pysus guarda um catálogo DuckDB com trava de arquivo e não aceita vários processos ao mesmo
# tempo. Baixar o .dbc direto do FTP permite paralelizar. Conferido: o agregado sai idêntico ao do pysus.

FTP = "ftp://ftp.datasus.gov.br/dissemin/publicos"


def listar_ftp(diretorio: str) -> list[str]:
    from urllib.request import urlopen

    with urlopen(f"{FTP}/{diretorio}/", timeout=120) as r:
        linhas = r.read().decode("latin1").splitlines()
    return [ln.split()[-1] for ln in linhas if ln.strip()]


def _processar_ftp(args) -> str:
    """Roda num processo separado: baixa, converte .dbc → .dbf, lê só as colunas úteis, agrega, apaga."""
    import tempfile
    from urllib.request import urlopen

    from dbfread import DBF
    from pyreaddbc import dbc2dbf

    url, destino, agregador, colunas = args
    with tempfile.TemporaryDirectory() as tmp:
        dbc, dbf = Path(tmp) / "a.dbc", Path(tmp) / "a.dbf"
        with urlopen(url, timeout=600) as r, open(dbc, "wb") as f:
            f.write(r.read())
        dbc2dbf(str(dbc), str(dbf))
        tabela = DBF(str(dbf), encoding="iso-8859-1", char_decode_errors="replace")
        cols = [c for c in colunas if c in tabela.field_names]
        dados = {c: [] for c in cols}
        for reg in tabela:
            for c in cols:
                dados[c].append(reg[c])
        df = pl.DataFrame(dados, schema={c: pl.String for c in cols})
    agregador(df).write_parquet(destino)
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
        if any(pasta.glob(f"{nome}*.parquet")):
            continue
        partes = [arq for base, arq in disponiveis.items() if base == nome or (base[:-1] == nome and base[-1].isalpha())]
        for arq in partes:
            sufixo = "" if len(partes) == 1 else "_" + arq.rsplit(".", 1)[0][-1]
            tarefas.append((f"{FTP}/{diretorio}/{arq}", pasta / f"{nome}{sufixo}.parquet", agregador, colunas))
    print(f"  {len(tarefas)} arquivos a baixar ({len(nomes)} pedidos, {processos} processos)")
    with ProcessPoolExecutor(processos) as ex:
        futuros = {ex.submit(_processar_ftp, t): t for t in tarefas}
        for i, f in enumerate(as_completed(futuros), 1):
            try:
                print(f"  [{i}/{len(tarefas)}] {f.result()} ✓", flush=True)
            except Exception as e:
                print(f"  [{i}/{len(tarefas)}] {futuros[f][1].stem} ! {e}", flush=True)
    return pasta
