"""Casos graves: internações (SIH-RD) e óbitos (SIM-DO) com jogo patológico, autolesão e suicídio,
agregados por mês, UF de residência, sexo e faixa etária. Nada em nível de pessoa é guardado.

- SIH: internação com F63 / F63.0 em qualquer campo de diagnóstico (principal, secundário, DIAGSEC1–9),
  autolesão (X60–X84 em qualquer campo), transtorno mental como diagnóstico principal e total.
- SIM: óbitos totais, suicídio (causa básica X60–X84) e óbitos com F63 / F63.0 mencionado em qualquer
  linha da declaração de óbito. SIM definitivo até 2024; 2025–2026 vêm da pasta PRELIM (preliminar).

uv run python -m src.saude_mental.graves_f63              # SIH + SIM, todas as UFs, 2018 em diante
uv run python -m src.saude_mental.graves_f63 --so-sim
"""

import argparse

import polars as pl

from src.config import ANO_FIM, ANO_INICIO, UFS, pasta
from src.saude_mental._datasus import AUTOLESAO, F63, MENTAL, rodar_ftp
from src.utils import juntar

FAIXAS = [(0, 17, "0-17"), (18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"), (45, 59, "45-59"), (60, 200, "60+")]
DIAGS_SIH = ["DIAG_PRINC", "DIAG_SECUN", *[f"DIAGSEC{i}" for i in range(1, 10)]]
COLS_SIH = [*DIAGS_SIH, "MUNIC_RES", "ANO_CMPT", "MES_CMPT", "IDADE", "COD_IDADE", "SEXO"]
LINHAS_SIM = ["CAUSABAS", "LINHAA", "LINHAB", "LINHAC", "LINHAD", "LINHAII"]
COLS_SIM = [*LINHAS_SIM, "CODMUNRES", "DTOBITO", "IDADE", "SEXO"]


def _faixa(idade: pl.Expr) -> pl.Expr:
    e = pl.lit(None, dtype=pl.String)
    for lo, hi, rot in reversed(FAIXAS):
        e = pl.when(idade.is_between(lo, hi)).then(pl.lit(rot)).otherwise(e)
    return e


def _algum(cols: list[str], padrao: str) -> pl.Expr:
    return pl.any_horizontal([pl.col(c).fill_null("").str.contains(padrao) for c in cols])


def agregar_sih(df: pl.DataFrame) -> pl.DataFrame:
    diags = [c for c in DIAGS_SIH if c in df.columns]
    # COD_IDADE 4 = anos; 2/3 = dias/meses (bebês) -> 0; 5 = 100+ anos
    idade = (pl.when(pl.col("COD_IDADE") == "4").then(pl.col("IDADE").cast(pl.Int32, strict=False))
             .when(pl.col("COD_IDADE") == "5").then(100 + pl.col("IDADE").cast(pl.Int32, strict=False))
             .otherwise(0))
    return (
        df.with_columns(
            (pl.col("ANO_CMPT") + pl.col("MES_CMPT").str.zfill(2)).alias("cmp"),
            pl.col("MUNIC_RES").str.slice(0, 2).alias("cod_uf"),
            pl.col("SEXO").replace_strict({"1": "M", "2": "F", "3": "F"}, default=None, return_dtype=pl.String).alias("sexo"),
            _faixa(idade).alias("faixa"),
        )
        .group_by("cmp", "cod_uf", "sexo", "faixa")
        .agg(
            pl.len().alias("intern_total"),
            pl.col("DIAG_PRINC").fill_null("").str.contains(MENTAL).sum().alias("intern_mental"),
            _algum(diags, F63).sum().alias("intern_f63"),
            _algum(diags, r"^F630").sum().alias("intern_f630"),
            _algum(diags, r"^F63[123]").sum().alias("intern_f63_nao_jogo"),
            pl.col("DIAG_PRINC").fill_null("").str.contains(F63).sum().alias("intern_f63_principal"),
            _algum(diags, AUTOLESAO).sum().alias("intern_autolesao"),
        )
    )


def agregar_sim(df: pl.DataFrame) -> pl.DataFrame:
    linhas = [c for c in LINHAS_SIM if c in df.columns]
    # IDADE no SIM: 1º dígito = unidade (4 = anos, 5 = 100+), 2 últimos = valor
    cod = pl.col("IDADE").fill_null("000")
    idade = (pl.when(cod.str.slice(0, 1) == "4").then(cod.str.slice(1, 2).cast(pl.Int32, strict=False))
             .when(cod.str.slice(0, 1) == "5").then(100 + cod.str.slice(1, 2).cast(pl.Int32, strict=False))
             .otherwise(0))
    dt = pl.col("DTOBITO").fill_null("").str.zfill(8)
    return (
        df.with_columns(
            (dt.str.slice(4, 4) + dt.str.slice(2, 2)).alias("cmp"),
            pl.col("CODMUNRES").fill_null("").str.slice(0, 2).alias("cod_uf"),
            pl.col("SEXO").replace_strict({"1": "M", "2": "F"}, default=None, return_dtype=pl.String).alias("sexo"),
            _faixa(idade).alias("faixa"),
        )
        .group_by("cmp", "cod_uf", "sexo", "faixa")
        .agg(
            pl.len().alias("obitos_total"),
            pl.col("CAUSABAS").fill_null("").str.contains(AUTOLESAO).sum().alias("obitos_suicidio"),
            _algum(linhas, r"F63").sum().alias("obitos_f63_mencionado"),
            _algum(linhas, r"F630").sum().alias("obitos_f630_mencionado"),
        )
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ufs", nargs="*", default=UFS)
    p.add_argument("--anos", type=int, nargs="*", default=list(range(ANO_INICIO, ANO_FIM + 1)))
    p.add_argument("--processos", type=int, default=8)
    p.add_argument("--so-sim", action="store_true")
    a = p.parse_args()

    print("SIM (óbitos)")
    nomes = [f"DO{uf}{ano}" for uf in a.ufs for ano in a.anos]
    rodar_ftp("sim_graves", "SIM/CID10/DORES", nomes, agregar_sim, COLS_SIM, a.processos)
    rodar_ftp("sim_graves", "SIM/PRELIM/DORES", nomes, agregar_sim, COLS_SIM, a.processos)  # 2025+ preliminar
    juntar(pasta("internacoes_obitos", "interim") / "sim_graves", pasta("internacoes_obitos") / "sim_graves.parquet")
    if a.so_sim:
        return

    print("SIH (internações)")
    nomes = [f"RD{uf}{ano % 100:02d}{mes:02d}" for uf in a.ufs for ano in a.anos for mes in range(1, 13)]
    rodar_ftp("sih_graves", "SIHSUS/200801_/Dados", nomes, agregar_sih, COLS_SIH, a.processos)
    juntar(pasta("internacoes_obitos", "interim") / "sih_graves", pasta("internacoes_obitos") / "sih_graves.parquet")


if __name__ == "__main__":
    main()
