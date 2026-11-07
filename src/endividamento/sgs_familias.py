"""Endividamento e comprometimento de renda das famílias (BCB/SGS), Brasil, mensal.

uv run python -m src.endividamento.sgs_familias
"""

import polars as pl
from bcb import sgs

from src.config import ANO_INICIO, PROCESSED
from src.utils import salvar

SERIES = {
    "endiv_familias": 29037,  # endividamento / renda acumulada 12m (%)
    "endiv_familias_ex_hab": 29038,  # idem, exceto financiamento habitacional
    "comprom_renda": 29034,  # comprometimento de renda com serviço da dívida (%)
    "comprom_renda_ex_hab": 29035,
    "saldo_credito_pf": 20541,  # saldo da carteira PF (R$ milhões)
    "concessoes_pf": 20633,  # concessões de crédito PF (R$ milhões)
    "ipca_mensal": 433,  # IPCA var. % mensal — usado para deflacionar séries nominais
}


def main():
    df = sgs.get(SERIES, start=f"{ANO_INICIO}-01-01")
    out = pl.from_pandas(df.reset_index()).rename({"Date": "data"}).with_columns(pl.col("data").cast(pl.Date))
    salvar(out, PROCESSED / "endividamento_sgs.parquet")


if __name__ == "__main__":
    main()
