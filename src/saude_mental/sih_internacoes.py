"""Internações SUS (SIH-RD) por município de residência e mês: jogo patológico (F63),
transtornos mentais (F), substâncias (F10-F19), autolesão (X60-X84) e total.

uv run python -m src.saude_mental.sih_internacoes                  # todas UFs, 2018→hoje
uv run python -m src.saude_mental.sih_internacoes --ufs SP RJ --anos 2024 2025
"""

import argparse

import polars as pl

from src.config import ANO_FIM, ANO_INICIO, PROCESSED, UFS
from src.saude_mental._datasus import AUTOLESAO, F63, MENTAL, SUBST, rodar
from src.utils import juntar


def agregar(df: pl.DataFrame) -> pl.DataFrame:
    prin = pl.col("DIAG_PRINC").fill_null("")
    sec = pl.col("DIAG_SECUN").fill_null("")
    return (
        df.with_columns(
            pl.col("ANO_CMPT").cast(pl.Int32).alias("ano"),
            pl.col("MES_CMPT").cast(pl.Int32).alias("mes"),
            pl.col("MUNIC_RES").cast(pl.String).alias("cod_mun6"),
        )
        .group_by("ano", "mes", "cod_mun6")
        .agg(
            pl.len().alias("intern_total"),
            (prin.str.contains(F63) | sec.str.contains(F63)).sum().alias("intern_f63"),
            prin.str.contains(MENTAL).sum().alias("intern_mental"),
            prin.str.contains(SUBST).sum().alias("intern_subst"),
            (prin.str.contains(AUTOLESAO) | sec.str.contains(AUTOLESAO)).sum().alias("intern_autolesao"),
        )
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ufs", nargs="*", default=UFS)
    p.add_argument("--anos", type=int, nargs="*", default=list(range(ANO_INICIO, ANO_FIM + 1)))
    a = p.parse_args()
    chamadas = [
        (f"RD{uf}{ano % 100:02d}{mes:02d}", dict(state=uf, year=ano, month=mes, group="RD"))
        for uf in a.ufs
        for ano in a.anos
        for mes in range(1, 13)
    ]
    pasta = rodar("sih", chamadas, agregar)
    juntar(pasta, PROCESSED / "sih_mental_municipio.parquet")


if __name__ == "__main__":
    main()
