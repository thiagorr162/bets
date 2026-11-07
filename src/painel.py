"""Montagem de painéis UF × mês juntando exposição (Google Trends) e outcomes.

Usado pelos notebooks; as decisões estão explicadas em notebooks/inadimplencia_painel.ipynb.
"""

import polars as pl

from src.config import PROCESSED

# Modalidades do SCR em que um aperto de liquidez de curto prazo deveria aparecer primeiro
# (crédito rotativo/pessoal sem garantia) vs. modalidades-placebo (com garantia real ou desconto
# em folha, que o devedor prioriza ou nem consegue deixar de pagar).
SENSIVEIS = ["PF - Cartão de crédito", "PF - Empréstimo sem consignação em folha", "PF - Outros créditos"]
PLACEBO = ["PF - Habitacional", "PF - Veículos", "PF - Empréstimo com consignação em folha"]
# "Rural e agroindustrial" fica fora dos dois grupos: depende de safra/clima, não de liquidez da família.

FAIXAS = {
    "ate_2sm": ["PF - Até 1 salário mínimo", "PF - Mais de 1 a 2 salários mínimos"],
    "2_a_5sm": ["PF - Mais de 2 a 3 salários mínimos", "PF - Mais de 3 a 5 salários mínimos"],
    "acima_5sm": ["PF - Mais de 5 a 10 salários mínimos", "PF - Mais de 10 a 20 salários mínimos",
                  "PF - Acima de 20 salários mínimos"],
}
# "Sem rendimento" e "Indisponível" ficam fora: composição instável (o "sem rendimento" foi de 3% a 16% de
# inadimplência só em 2025, sinal de reclassificação de clientes, não de comportamento).


def inadimplencia_uf(filtro: pl.Expr | None = None) -> pl.DataFrame:
    """Inadimplência (% carteira) por UF e mês, opcionalmente filtrando modalidade/porte."""
    s = pl.read_parquet(PROCESSED / "scr_pf_uf.parquet")
    if filtro is not None:
        s = s.filter(filtro)
    return (
        s.group_by("uf", pl.col("data_base").dt.truncate("1mo").alias("data"))
        .agg(pl.col("carteira_inadimplida_arrastada", "carteira_ativa").sum())
        .with_columns((pl.col("carteira_inadimplida_arrastada") / pl.col("carteira_ativa") * 100).alias("inad"))
        .select("uf", "data", "inad", "carteira_ativa")
    )


def trends_uf(defasagens=(0, 3, 6, 9), avancos=(6,)) -> pl.DataFrame:
    """Trends comparável por UF/mês, padronizado (z-score no painel) e com defasagens/avanços."""
    gt = pl.read_parquet(PROCESSED / "google_trends_uf.parquet").filter(pl.col("uf") != "BR").sort("uf", "data")
    gt = gt.with_columns(
        ((pl.col("indice_comparavel") - pl.col("indice_comparavel").mean()) / pl.col("indice_comparavel").std()).alias("trends")
    )
    cols = [pl.col("trends").shift(k).over("uf").alias(f"trends_l{k}") for k in defasagens]
    cols += [pl.col("trends").shift(-k).over("uf").alias(f"trends_f{k}") for k in avancos]
    return gt.with_columns(cols).select("uf", "data", "trends", *[c.meta.output_name() for c in cols])


def pobreza_uf() -> pl.DataFrame:
    """Proxy de pobreza da UF: beneficiários do PBF / população, ago/2024."""
    pbf = pl.read_parquet(PROCESSED / "bolsa_familia_municipio.parquet").filter(pl.col("anomes") == "202408")
    pop = pl.read_parquet(PROCESSED / "populacao_municipio.parquet").filter(pl.col("ano") == 2024)
    return (
        pbf.join(pop, on="cod_ibge").group_by("uf")
        .agg((pl.col("beneficiarios").sum() / pl.col("populacao").sum()).alias("pbf_share"))
    )


def selic() -> pl.DataFrame:
    s = pl.read_parquet(PROCESSED / "endividamento_sgs.parquet").select("data", "selic").drop_nulls()
    return s.with_columns(pl.col("data").dt.truncate("1mo"))


def painel(outcome: pl.DataFrame, inicio="2022-01-01", fim="2026-08-01") -> pl.DataFrame:
    """Junta outcome (uf, data, ...) com Trends, Selic e pobreza; restringe ao período."""
    ini, f = pl.lit(inicio).str.to_date(), pl.lit(fim).str.to_date()
    return (
        outcome.join(trends_uf(), on=["uf", "data"], how="inner")
        .join(selic(), on="data", how="left")
        .join(pobreza_uf(), on="uf", how="left")
        .with_columns(
            (pl.col("selic") * (pl.col("pbf_share") - pl.col("pbf_share").mean())).alias("selic_x_pobreza"),
            pl.col("data").dt.strftime("%Y-%m").alias("mes"),
            # id numérico da UF: o wild bootstrap (numba) não aceita cluster em texto
            pl.col("uf").rank("dense").cast(pl.Int64).alias("uf_id"),
        )
        .filter(pl.col("data").is_between(ini, f))
        .sort("uf", "data")
    )


def estimar(dados, y="inad", x="trends_l6", controles="selic_x_pobreza", fe="uf + mes", pesos=None, rotulo=None):
    """TWFE com EP clusterizado por UF + p-valor de wild cluster bootstrap (Rademacher, 9.999 réplicas, seed 42).

    `dados` é um pandas.DataFrame vindo de `painel(...).to_pandas()`.
    """
    import pyfixest as pf

    fml = f"{y} ~ {x}" + (f" + {controles}" if controles else "") + f" | {fe}"
    d = dados.dropna(subset=[y, x])
    fit = pf.feols(fml, data=d, vcov={"CRV1": "uf_id"}, weights=pesos)
    t = fit.tidy().loc[x]
    # wild bootstrap não é suportado com pesos (WLS): nesse caso fica só o EP clusterizado
    p_boot = float("nan") if pesos else float(fit.wildboottest(param=x, reps=9999, seed=42)["Pr(>|t|)"])
    return {"modelo": rotulo or fml, "β": t["Estimate"], "ep": t["Std. Error"], "p": t["Pr(>|t|)"],
            "p_boot": p_boot, "n": fit._N}
