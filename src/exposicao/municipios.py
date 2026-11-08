"""Cadastro de municípios (IBGE) + população estimada (SIDRA 6579) para per capita.

uv run python -m src.exposicao.municipios
"""

import polars as pl
from unidecode import unidecode

from src.config import ANO_FIM, ANO_INICIO, pasta
from src.utils import get_json, salvar

LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
POP = "https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p"


def normalizar(s: str) -> str:
    return unidecode(s).upper().replace("-", " ").replace("'", "").strip()


def main():
    mun = pl.DataFrame(
        [
            {
                "cod_ibge": m["id"],
                "municipio": m["nome"],
                "uf": m["microrregiao"]["mesorregiao"]["UF"]["sigla"]
                if m.get("microrregiao")
                else m["regiao-imediata"]["regiao-intermediaria"]["UF"]["sigla"],
            }
            for m in get_json(LOCALIDADES)
        ]
    ).with_columns(pl.col("municipio").map_elements(normalizar, return_dtype=pl.String).alias("municipio_norm"))
    salvar(mun, pasta("ibge") / "municipios.parquet")

    # SIDRA limita ~100k valores por consulta: baixa em blocos de anos
    rows = []
    for ini in range(ANO_INICIO, ANO_FIM + 1, 5):
        anos = ",".join(str(a) for a in range(ini, min(ini + 5, ANO_FIM + 1)))
        try:
            rows += get_json(f"{POP}/{anos}")[1:]
        except Exception as e:  # anos sem estimativa publicada
            print(f"! população {anos}: {e}")
    pop = pl.DataFrame(rows).select(
        pl.col("D1C").cast(pl.Int64).alias("cod_ibge"),
        pl.col("D3N").cast(pl.Int32).alias("ano"),
        pl.col("V").cast(pl.Int64, strict=False).alias("populacao"),
    )
    salvar(pop, pasta("ibge") / "populacao_municipio.parquet")


if __name__ == "__main__":
    main()
