"""Intensidade de busca por apostas (Google Trends), por UF e mês, comparável entre UFs.

Decisões (também explicadas no notebook):
- Termo: cesta com OR, "bet + apostas + betano + bet365 + tigrinho". O Google não tem um tópico
  estável de "apostas online" no Brasil, e um termo só perde quem busca a marca ou o cassino ("tigrinho").
- Série por UF: uma consulta por UF (geo=BR-XX) no período inteiro. O Trends devolve 0–100
  normalizado *dentro* da UF (100 = pico da própria UF), então as séries não se comparam entre si.
- Comparabilidade: a consulta por região (interest_by_region) dá o nível médio relativo de cada UF no
  período (100 = UF com maior participação de buscas). Reescalamos cada série para que sua média
  no período seja igual a esse nível: comparavel = serie_uf / media(serie_uf) * nivel_uf.
- O índice é participação (buscas do termo / total de buscas na UF), não volume absoluto.
- O Trends trabalha com amostras; valores mudam um pouco entre execuções. `--amostras N` repete as
  consultas N vezes e tira a média.

uv run python -m src.exposicao.google_trends
uv run python -m src.exposicao.google_trends --amostras 3
"""

import argparse
import time

import polars as pl
from pytrends.exceptions import TooManyRequestsError
from pytrends.request import TrendReq

from src.config import ANO_INICIO, HOJE, INTERIM, PROCESSED, UFS
from src.utils import salvar

TERMO = "bet + apostas + betano + bet365 + tigrinho"
PERIODO = f"{ANO_INICIO}-01-01 {HOJE.isoformat()}"
PASTA = INTERIM / "google_trends"
NOME_UF = {  # nome devolvido pelo interest_by_region -> sigla
    "Acre": "AC", "Alagoas": "AL", "Amapá": "AP", "Amazonas": "AM", "Bahia": "BA", "Ceará": "CE",
    "Distrito Federal": "DF", "Espírito Santo": "ES", "Goiás": "GO", "Maranhão": "MA",
    "Mato Grosso": "MT", "Mato Grosso do Sul": "MS", "Minas Gerais": "MG", "Pará": "PA",
    "Paraíba": "PB", "Paraná": "PR", "Pernambuco": "PE", "Piauí": "PI", "Rio de Janeiro": "RJ",
    "Rio Grande do Norte": "RN", "Rio Grande do Sul": "RS", "Rondônia": "RO", "Roraima": "RR",
    "Santa Catarina": "SC", "São Paulo": "SP", "Sergipe": "SE", "Tocantins": "TO",
}


def consultar(fn, tentativas=6):
    for i in range(tentativas):
        try:
            return fn()
        except TooManyRequestsError:
            espera = 30 * 2**i
            print(f"  429 do Google, esperando {espera}s")
            time.sleep(espera)
    raise RuntimeError("Google Trends bloqueou as consultas; tente mais tarde")


def serie(t: TrendReq, geo: str) -> pl.DataFrame:
    def _f():
        t.build_payload([TERMO], geo=geo, timeframe=PERIODO)
        return t.interest_over_time()

    df = consultar(_f).reset_index()
    return pl.from_pandas(df[["date", TERMO]]).rename({"date": "data", TERMO: "indice"}).with_columns(
        pl.col("data").cast(pl.Date), pl.col("indice").cast(pl.Float64)
    )


def niveis(t: TrendReq) -> pl.DataFrame:
    def _f():
        t.build_payload([TERMO], geo="BR", timeframe=PERIODO)
        return t.interest_by_region(resolution="REGION", inc_low_vol=True)

    df = consultar(_f).reset_index()
    return pl.from_pandas(df).rename({"geoName": "nome", TERMO: "nivel"}).with_columns(
        pl.col("nome").replace_strict(NOME_UF).alias("uf"), pl.col("nivel").cast(pl.Float64)
    ).select("uf", "nivel")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--amostras", type=int, default=1)
    p.add_argument("--pausa", type=float, default=8.0, help="segundos entre consultas")
    a = p.parse_args()
    PASTA.mkdir(parents=True, exist_ok=True)
    # sem retries/backoff do pytrends: ele usa uma API antiga do urllib3 que quebra; o retry é o nosso
    t = TrendReq(hl="pt-BR", tz=180)

    for k in range(a.amostras):
        for geo in ["BR", *[f"BR-{uf}" for uf in UFS]]:
            destino = PASTA / f"{geo}_a{k}.parquet"
            if destino.exists():
                continue
            serie(t, geo).with_columns(pl.lit(geo.removeprefix("BR-") if geo != "BR" else "BR").alias("uf")).write_parquet(destino)
            print(f"  amostra {k} {geo} ✓")
            time.sleep(a.pausa)
        destino = PASTA / f"niveis_a{k}.parquet"
        if not destino.exists():
            niveis(t).write_parquet(destino)
            time.sleep(a.pausa)

    series = pl.concat([pl.read_parquet(f) for f in PASTA.glob("BR*_a*.parquet")]).group_by("uf", "data").agg(pl.col("indice").mean())
    nv = pl.concat([pl.read_parquet(f) for f in PASTA.glob("niveis_a*.parquet")]).group_by("uf").agg(pl.col("nivel").mean())
    out = (
        series.join(nv, on="uf", how="left")
        .with_columns((pl.col("indice") / pl.col("indice").mean().over("uf") * pl.col("nivel")).alias("indice_comparavel"))
        .sort("uf", "data")
    )
    salvar(out, PROCESSED / "google_trends_uf.parquet")


if __name__ == "__main__":
    main()
