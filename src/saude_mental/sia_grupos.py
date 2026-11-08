"""Pacientes nos CAPS (SIA-PS) por grupo de diagnóstico, mês, sexo e faixa etária. Só contagens agregadas.

Grupos (CID principal da RAAS):
- depressao: F32–F33          - ansiedade: F41          - estresse: F43 (reação a estresse e ajustamento)
- alcool: F10                 - drogas: F11–F19         - esquizofrenia: F20 (comparação: sem relação esperada com apostas)
- jogo: F63.0                 - mental: capítulo F inteiro (denominador)

Contagem: pacientes distintos (CNS) dentro de cada arquivo UF × mês. Somando os arquivos de um mês, um paciente
atendido em CAPS de duas UFs no mesmo mês conta duas vezes (raro).

uv run python -m src.saude_mental.sia_grupos
"""

import argparse

import polars as pl

from src.config import ANO_FIM, ANO_INICIO, PROCESSED, UFS
from src.saude_mental._datasus import rodar_ftp
from src.saude_mental.sia_f63_pacientes import _faixa, _idade
from src.utils import juntar

DIR = "SIASUS/200801_/Dados"
COLS = ["CNS_PAC", "DT_ATEND", "IDADEPAC", "TPIDADEPAC", "SEXOPAC", "CIDPRI"]
GRUPOS = {
    "depressao": r"^F3[23]", "ansiedade": r"^F41", "estresse": r"^F43", "alcool": r"^F10",
    "drogas": r"^F1[1-9]", "esquizofrenia": r"^F20", "jogo": r"^F630", "mental": r"^F",
}


def agregar(df: pl.DataFrame) -> pl.DataFrame:
    df = df.with_columns(
        pl.col("DT_ATEND").str.slice(0, 6).alias("cmp"),
        pl.col("CIDPRI").fill_null("").str.strip_chars(),
        _idade().alias("idade"),
    ).with_columns(_faixa().alias("faixa"))
    return pl.concat([
        df.filter(pl.col("CIDPRI").str.contains(p)).group_by("cmp", "SEXOPAC", "faixa")
        .agg(pl.col("CNS_PAC").n_unique().alias("pacientes")).with_columns(pl.lit(g).alias("grupo"))
        for g, p in GRUPOS.items()
    ])


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--ufs", nargs="*", default=UFS)
    a.add_argument("--anos", type=int, nargs="*", default=list(range(ANO_INICIO, ANO_FIM + 1)))
    a.add_argument("--processos", type=int, default=8)
    x = a.parse_args()
    nomes = [f"PS{uf}{ano % 100:02d}{mes:02d}" for uf in x.ufs for ano in x.anos for mes in range(1, 13)]
    pasta = rodar_ftp("sia_grupos", DIR, nomes, agregar, COLS, x.processos)
    df = juntar(pasta, PROCESSED / "sia_grupos_tmp.parquet")
    (df.group_by("cmp", "grupo", "SEXOPAC", "faixa").agg(pl.col("pacientes").sum())
       .write_parquet(PROCESSED / "sia_grupos.parquet"))
    (PROCESSED / "sia_grupos_tmp.parquet").unlink()
    print("✓ data/processed/sia_grupos.parquet")


if __name__ == "__main__":
    main()
