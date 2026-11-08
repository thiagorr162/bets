"""Trajetórias de diagnóstico de TODOS os pacientes dos CAPS (SIA-PS), para comparar o que acontece depois do
primeiro diagnóstico de jogo patológico com o que acontece depois do primeiro diagnóstico de outros transtornos.

Saída (data/caps/processed/sia_trajetorias.parquet), uma linha por paciente × mês × grupo de diagnóstico:
- id: pseudônimo inteiro (HMAC-SHA256 do CNS com a chave local data/.chave_pseudonimo; o mesmo usado em
  sia_f63_registros, truncado em 64 bits)
- mes: meses desde jan/2018 (0 = jan/2018)
- grupo: código do grupo de CID (ver GRUPOS), vindo do CID principal OU do CID associado
- sexo (0 = M, 1 = F) e faixa etária (índice em FAIXAS) no mês
Nada mais do paciente é guardado. A tabela fica só em data/ (fora do git) e é usada apenas para agregados.

Lê os .dbc de data/caps/raw/datasus/ (baixa só o que faltar).

uv run python -m src.saude_mental.sia_trajetorias
"""

import argparse
import hashlib
import hmac

import polars as pl

from src.config import ANO_FIM, ANO_INICIO, DATA, UFS, pasta as pasta_dados
from src.saude_mental._datasus import rodar_ftp
from src.saude_mental.sia_f63_pacientes import FAIXAS, _faixa, _idade

DIR = "SIASUS/200801_/Dados"
COLS = ["CNS_PAC", "DT_ATEND", "IDADEPAC", "TPIDADEPAC", "SEXOPAC", "CIDPRI", "CIDASSOC"]
# ordem importa: o primeiro padrão que casar define o grupo
GRUPOS = [
    (1, "jogo patológico (F63.0)", r"^F630"),
    (2, "álcool (F10)", r"^F10"),
    (3, "outras drogas (F11–F19)", r"^F1[1-9]"),
    (4, "psicoses (F20–F29)", r"^F2"),
    (5, "humor/depressão (F30–F39)", r"^F3"),
    (6, "ansiedade/estresse (F40–F48)", r"^F4"),
    (7, "personalidade/impulsos (F60–F69, exceto F63.0)", r"^F6"),
    (8, "outros transtornos mentais (F)", r"^F"),
]
NOMES = {k: n for k, n, _ in GRUPOS}


def _grupo(col: str) -> pl.Expr:
    c = pl.col(col).fill_null("").str.strip_chars()
    e = pl.lit(None, dtype=pl.Int8)
    for k, _, p in reversed(GRUPOS):
        e = pl.when(c.str.contains(p)).then(pl.lit(k, dtype=pl.Int8)).otherwise(e)
    return e


def agregar(df: pl.DataFrame) -> pl.DataFrame:
    chave = bytes.fromhex((DATA / ".chave_pseudonimo").read_text().strip())
    df = df.with_columns(
        pl.col("CNS_PAC").map_elements(
            lambda c: int.from_bytes(hmac.new(chave, c.encode("latin1", "replace"), hashlib.sha256).digest()[:8], "big", signed=True),
            return_dtype=pl.Int64).alias("id"),
        ((pl.col("DT_ATEND").str.slice(0, 4).cast(pl.Int32, strict=False) - 2018) * 12
         + pl.col("DT_ATEND").str.slice(4, 2).cast(pl.Int32, strict=False) - 1).cast(pl.Int16).alias("mes"),
        pl.when(pl.col("SEXOPAC") == "F").then(1).when(pl.col("SEXOPAC") == "M").then(0).otherwise(None).cast(pl.Int8).alias("sexo"),
        _idade().alias("idade"),
    ).with_columns(_faixa().alias("faixa_txt"))
    rot = [r for _, _, r in FAIXAS]
    df = df.with_columns(pl.col("faixa_txt").replace_strict(rot, list(range(len(rot))), default=None, return_dtype=pl.Int8).alias("faixa"))
    partes = [df.select("id", "mes", "sexo", "faixa", _grupo(c).alias("grupo")) for c in ("CIDPRI", "CIDASSOC")]
    return pl.concat(partes).drop_nulls(["grupo", "mes"]).unique(["id", "mes", "grupo"])


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--ufs", nargs="*", default=UFS)
    a.add_argument("--anos", type=int, nargs="*", default=list(range(ANO_INICIO, ANO_FIM + 1)))
    a.add_argument("--processos", type=int, default=8)
    x = a.parse_args()
    nomes = [f"PS{uf}{ano % 100:02d}{mes:02d}" for uf in x.ufs for ano in x.anos for mes in range(1, 13)]
    pasta = rodar_ftp("sia_trajetorias", DIR, nomes, agregar, COLS, x.processos)
    df = pl.concat([pl.read_parquet(f) for f in pasta.glob("*.parquet")]).unique(["id", "mes", "grupo"])
    df.write_parquet(pasta_dados("caps") / "sia_trajetorias.parquet")
    print(f"✓ data/caps/processed/sia_trajetorias.parquet ({df.height:,} linhas, {df['id'].n_unique():,} pacientes)")


if __name__ == "__main__":
    main()
