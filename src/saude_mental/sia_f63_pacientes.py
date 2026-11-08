"""Pacientes com F63 nos CAPS (SIA-PS): perfil, subcódigos e histórico no CAPS.

Duas passadas no FTP do DATASUS (~5 min cada, 8 processos):
  1. Para cada arquivo UF × mês:
     - `f63`: registros de pacientes com F63 no CID principal ou associado (1 linha por paciente × CAPS × mês);
     - `perfil`: pacientes distintos por grupo de CID (F63, F63.0, saúde mental, substâncias), sexo e faixa etária.
  2. `historico`: todos os registros (qualquer CID) dos pacientes que tiveram F63 em algum momento,
     para saber se já estavam no CAPS antes do primeiro F63 (paciente novo × reclassificado).

O CNS vem criptografado pelo DATASUS e é estável entre meses, o que permite seguir o paciente.
Os arquivos com nível de paciente ficam só em data/ (fora do git) e não devem ser publicados. No fim, as tabelas
são minimizadas por `src.saude_mental.minimizar_f63` (pseudônimo novo, UF em vez de município, faixa etária).

uv run python -m src.saude_mental.sia_f63_pacientes
"""

import argparse
from functools import partial

import polars as pl

from src.config import ANO_FIM, ANO_INICIO, UFS, pasta
from src.saude_mental._datasus import F63, MENTAL, SUBST, rodar_ftp

DIR = "SIASUS/200801_/Dados"
COLS_P1 = ["CNS_PAC", "DT_ATEND", "CNES_EXEC", "MUNPAC", "IDADEPAC", "TPIDADEPAC", "SEXOPAC", "RACACOR",
           "CIDPRI", "CIDASSOC", "DT_INICIO", "ORIGEM_PAC", "SIT_RUA", "TP_DROGA"]
COLS_P2 = ["CNS_PAC", "DT_ATEND", "CNES_EXEC", "CIDPRI", "DT_INICIO"]
FAIXAS = [(0, 17, "0-17"), (18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"), (45, 59, "45-59"), (60, 200, "60+")]


def _idade() -> pl.Expr:
    # TPIDADEPAC 4 = idade em anos; outros tipos (dias, meses) são crianças pequenas -> 0
    return pl.when(pl.col("TPIDADEPAC") == "4").then(pl.col("IDADEPAC").cast(pl.Int32, strict=False)).otherwise(0)


def _faixa() -> pl.Expr:
    e = pl.lit(None, dtype=pl.String)
    for lo, hi, rot in reversed(FAIXAS):
        e = pl.when(pl.col("idade").is_between(lo, hi)).then(pl.lit(rot)).otherwise(e)
    return e


def passada1(df: pl.DataFrame) -> dict[str, pl.DataFrame]:
    df = df.with_columns(
        pl.col("DT_ATEND").str.slice(0, 6).alias("cmp"),
        pl.col("CIDPRI").fill_null("").str.strip_chars(),
        pl.col("CIDASSOC").fill_null("").str.strip_chars(),
        _idade().alias("idade"),
    ).with_columns(_faixa().alias("faixa"))
    tem_f63 = pl.col("CIDPRI").str.contains(F63) | pl.col("CIDASSOC").str.contains(F63)
    f63 = (
        df.filter(tem_f63)
        .group_by("CNS_PAC", "cmp", "CNES_EXEC")
        .agg(pl.col("MUNPAC", "idade", "faixa", "SEXOPAC", "RACACOR", "CIDPRI", "CIDASSOC", "DT_INICIO",
                    "ORIGEM_PAC", "SIT_RUA", "TP_DROGA").first(), pl.len().alias("n_proc"))
    )
    grupos = {
        "f63": pl.col("CIDPRI").str.contains(F63),
        "f630": pl.col("CIDPRI").str.starts_with("F630"),
        "mental": pl.col("CIDPRI").str.contains(MENTAL),
        "subst": pl.col("CIDPRI").str.contains(SUBST),
    }
    perfil = pl.concat([
        df.filter(cond).group_by("cmp", "SEXOPAC", "faixa").agg(pl.col("CNS_PAC").n_unique().alias("pacientes"))
        .with_columns(pl.lit(g).alias("grupo"))
        for g, cond in grupos.items()
    ])
    return {"f63": f63, "perfil": perfil}


def passada2(df: pl.DataFrame, cns: frozenset) -> pl.DataFrame:
    return (
        df.filter(pl.col("CNS_PAC").is_in(list(cns)))
        .with_columns(pl.col("DT_ATEND").str.slice(0, 6).alias("cmp"), pl.col("CIDPRI").fill_null("").str.strip_chars())
        .group_by("CNS_PAC", "cmp", "CNES_EXEC", "CIDPRI").agg(pl.col("DT_INICIO").first(), pl.len().alias("n_proc"))
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ufs", nargs="*", default=UFS)
    p.add_argument("--anos", type=int, nargs="*", default=list(range(ANO_INICIO, ANO_FIM + 1)))
    p.add_argument("--processos", type=int, default=8)
    a = p.parse_args()
    nomes = [f"PS{uf}{ano % 100:02d}{mes:02d}" for uf in a.ufs for ano in a.anos for mes in range(1, 13)]

    print("Passada 1: registros F63 + perfil")
    pasta1 = rodar_ftp("sia_f63", DIR, nomes, passada1, COLS_P1, a.processos)
    f63 = pl.concat([pl.read_parquet(f) for f in (pasta1 / "f63").glob("*.parquet")], how="diagonal_relaxed")
    perfil = pl.concat([pl.read_parquet(f) for f in (pasta1 / "perfil").glob("*.parquet")], how="diagonal_relaxed")
    f63.write_parquet(pasta("caps") / "sia_f63_registros.parquet")
    perfil.group_by("cmp", "grupo", "SEXOPAC", "faixa").agg(pl.col("pacientes").sum()).write_parquet(pasta("caps") / "sia_perfil.parquet")
    print(f"✓ {f63['CNS_PAC'].n_unique():,} pacientes distintos com F63")

    print("Passada 2: histórico no CAPS dos pacientes com F63")
    cns = frozenset(f63["CNS_PAC"].unique().to_list())
    pasta2 = rodar_ftp("sia_f63_hist", DIR, nomes, partial(passada2, cns=cns), COLS_P2, a.processos)
    hist = pl.concat([pl.read_parquet(f) for f in pasta2.glob("*.parquet")], how="diagonal_relaxed")
    hist.write_parquet(pasta("caps") / "sia_f63_historico.parquet")
    print(f"✓ histórico: {hist.height:,} linhas")

    # LGPD: pseudonimiza de novo, reduz detalhe e apaga os intermediários por paciente
    from src.saude_mental import minimizar_f63

    minimizar_f63.main()


if __name__ == "__main__":
    main()
