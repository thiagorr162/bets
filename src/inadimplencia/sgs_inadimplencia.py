"""Inadimplência da carteira de crédito (BCB/SGS), Brasil, mensal.

uv run python -m src.inadimplencia.sgs_inadimplencia
"""

import polars as pl
from bcb import sgs

from src.config import ANO_INICIO, PROCESSED
from src.utils import salvar

SERIES = {
    "inad_total": 21082,  # inadimplência total (%)
    "inad_pf": 21084,  # pessoas físicas (%)
    "inad_pf_livres": 21112,  # PF, recursos livres (%)
}


def main():
    df = sgs.get(SERIES, start=f"{ANO_INICIO}-01-01")
    out = pl.from_pandas(df.reset_index()).rename({"Date": "data"}).with_columns(pl.col("data").cast(pl.Date))
    salvar(out, PROCESSED / "inadimplencia_sgs.parquet")


if __name__ == "__main__":
    main()
