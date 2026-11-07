"""Óbitos por suicídio (SIM, CAUSABAS X60-X84) por município de residência e mês.
O SIM é anual e sai com ~1-2 anos de defasagem (os preliminares podem não existir).

uv run python -m src.saude_mental.sim_suicidio
"""

import argparse

import polars as pl

from src.config import ANO_FIM, ANO_INICIO, PROCESSED, UFS
from src.saude_mental._datasus import AUTOLESAO, rodar
from src.utils import juntar


def agregar(df: pl.DataFrame) -> pl.DataFrame:
    dt = pl.col("DTOBITO").cast(pl.String).str.zfill(8)
    return (
        df.with_columns(
            dt.str.slice(4, 4).cast(pl.Int32, strict=False).alias("ano"),
            dt.str.slice(2, 2).cast(pl.Int32, strict=False).alias("mes"),
            pl.col("CODMUNRES").cast(pl.String).str.slice(0, 6).alias("cod_mun6"),
        )
        .group_by("ano", "mes", "cod_mun6")
        .agg(
            pl.len().alias("obitos_total"),
            pl.col("CAUSABAS").fill_null("").str.contains(AUTOLESAO).sum().alias("obitos_suicidio"),
        )
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ufs", nargs="*", default=UFS)
    p.add_argument("--anos", type=int, nargs="*", default=list(range(ANO_INICIO, ANO_FIM + 1)))
    a = p.parse_args()
    chamadas = [(f"DO{uf}{ano}", dict(state=uf, year=ano)) for uf in a.ufs for ano in a.anos]
    pasta = rodar("sim", chamadas, agregar)
    juntar(pasta, PROCESSED / "sim_suicidio_municipio.parquet")


if __name__ == "__main__":
    main()
