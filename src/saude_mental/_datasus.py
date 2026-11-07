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
