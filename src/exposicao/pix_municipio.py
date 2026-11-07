"""Transações Pix por município (BCB, API Olinda), mensal, desde nov/2020.

Não é Pix *para bets*, é o total. Serve como exposição/controle e para ver a quebra
após a MP 1.394 (set/2026). Os 3 últimos meses são sempre rebaixados (revisões).

uv run python -m src.exposicao.pix_municipio
uv run python -m src.exposicao.pix_municipio --inicio 202401
"""

import argparse

import polars as pl

from src.config import INTERIM, PROCESSED, meses
from src.utils import get_json, juntar, salvar

URL = "https://olinda.bcb.gov.br/olinda/servico/Pix_DadosAbertos/versao/v1/odata/TransacoesPixPorMunicipio(DataBase=@DataBase)"
PASTA = INTERIM / "pix"


def baixar_mes(m: str) -> pl.DataFrame:
    # OData não aceita '+' como espaço (requests codifica assim), então a query vai montada à mão
    j = get_json(f"{URL}?@DataBase='{m}'&$filter=AnoMes%20eq%20{m}&$format=json&$top=100000")
    return pl.DataFrame(j["value"], infer_schema_length=None)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inicio", default="202011")
    a = p.parse_args()
    todos = meses(a.inicio)
    recentes = set(todos[-3:])
    for m in todos:
        destino = PASTA / f"{m}.parquet"
        if destino.exists() and m not in recentes:
            continue
        df = baixar_mes(m)
        if df.is_empty():
            print(f"  {m}: sem dados ainda")
            continue
        salvar(df, destino)
    df = juntar(PASTA, PROCESSED / "pix_municipio.parquet")
    print(df.group_by("AnoMes").len().sort("AnoMes").tail(5))


if __name__ == "__main__":
    main()
