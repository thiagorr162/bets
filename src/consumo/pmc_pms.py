"""Consumo: PMC (varejo e varejo ampliado) e PMS (serviços), IBGE/SIDRA, por UF, mensal.

uv run python -m src.consumo.pmc_pms
"""

import polars as pl

from src.config import PROCESSED
from src.utils import get_json, salvar

SIDRA = "https://apisidra.ibge.gov.br/values"
# tabela -> (nome, variáveis, classificação). 2022=100
TABELAS = {
    8880: ("pmc_varejo", "7169,7170", "c11046/all"),
    8881: ("pmc_ampliado", "7169,7170", "c11046/all"),
    5906: ("pms_servicos", "7167,7168", "c11046/all"),  # 8688 é por atividade, sem UF
}


def sidra(tabela: int, variaveis: str, classif: str, nivel: str = "n3/all") -> pl.DataFrame:
    rows = get_json(f"{SIDRA}/t/{tabela}/{nivel}/v/{variaveis}/p/all/{classif}")
    df = pl.DataFrame(rows[1:])
    return df.select(
        pl.col("D1C").alias("cod_uf"),
        pl.col("D1N").alias("uf_nome"),
        pl.col("D2N").alias("variavel"),
        pl.col("D3C").str.to_date("%Y%m").alias("data"),
        pl.col("D4N").alias("indice"),
        pl.col("V").cast(pl.Float64, strict=False).alias("valor"),
    )


def main():
    dfs = []
    for t, (nome, v, c) in TABELAS.items():
        for nivel in ("n1/all", "n3/all"):
            print(f"  SIDRA {t} {nivel}")
            dfs.append(sidra(t, v, c, nivel).with_columns(pl.lit(nome).alias("pesquisa")))
    salvar(pl.concat(dfs), PROCESSED / "consumo_pmc_pms.parquet")


if __name__ == "__main__":
    main()
