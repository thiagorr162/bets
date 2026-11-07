"""Atendimentos psicossociais/CAPS (SIA-PS, RAAS) por município do paciente e mês.

uv run python -m src.saude_mental.sia_caps
uv run python -m src.saude_mental.sia_caps --ufs SP --anos 2025 2026
"""

import argparse

import polars as pl

from src.config import ANO_FIM, ANO_INICIO, PROCESSED, UFS
from src.saude_mental._datasus import F63, MENTAL, SUBST, rodar_ftp
from src.utils import juntar


def agregar(df: pl.DataFrame) -> pl.DataFrame:
    cid = pl.col("CIDPRI").fill_null("")
    qtd = pl.col("PA_QTDAPR").cast(pl.Float64, strict=False)
    return (
        df.with_columns(
            pl.col("PA_CMP").cast(pl.String).alias("cmp") if "PA_CMP" in df.columns
            else pl.col("DT_ATEND").cast(pl.String).str.slice(0, 6).alias("cmp"),
            pl.col("MUNPAC").cast(pl.String).alias("cod_mun6"),
        )
        .group_by("cmp", "cod_mun6")
        .agg(
            pl.len().alias("raas_total"),
            cid.str.contains(F63).sum().alias("raas_f63"),
            cid.str.contains(MENTAL).sum().alias("raas_mental"),
            cid.str.contains(SUBST).sum().alias("raas_subst"),
            qtd.filter(cid.str.contains(F63)).sum().alias("proc_f63"),
            pl.col("CNS_PAC").filter(cid.str.contains(F63)).n_unique().alias("pacientes_f63"),
        )
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ufs", nargs="*", default=UFS)
    p.add_argument("--anos", type=int, nargs="*", default=list(range(ANO_INICIO, ANO_FIM + 1)))
    p.add_argument("--processos", type=int, default=8)
    a = p.parse_args()
    nomes = [f"PS{uf}{ano % 100:02d}{mes:02d}" for uf in a.ufs for ano in a.anos for mes in range(1, 13)]
    colunas = ["CIDPRI", "PA_QTDAPR", "PA_CMP", "DT_ATEND", "MUNPAC", "CNS_PAC"]
    pasta = rodar_ftp("sia", "SIASUS/200801_/Dados", nomes, agregar, colunas, a.processos)
    juntar(pasta, PROCESSED / "sia_caps_municipio.parquet")


if __name__ == "__main__":
    main()
