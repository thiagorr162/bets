"""Monta os dados do site (só agregados, com supressão) e grava site/index.html a partir de site/modelo.html.

uv run python site/montar_dados.py

Regras de privacidade aplicadas aqui (o site não recebe nada em nível de pessoa):
- Só totais nacionais (série mensal, anos, perfil por sexo × faixa etária, novos × já no CAPS).
- Contagens < 5 viram nulo; percentuais e razões calculados a partir delas também.
"""

import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import CHOQUES, PANDEMIA, PROCESSED  # noqa: E402

MIN = 5
# Uma notícia por marco regulatório (mesma ordem de src.config.CHOQUES). Trocar aqui para mudar o link.
NOTICIAS = {
    "2018-12-12": ("O Povo", "https://www.opovo.com.br/esportes/maisesportes/2018/12/lei-que-libera-apostas-esportivas-no-brasil-e-aprovada.html"),
    "2023-12-29": ("Agência Gov", "https://agenciagov.ebc.com.br/noticias/202312/presidente-lula-sanciona-lei-que-regulamenta-apostas-esportivas"),
    "2024-10-01": ("Agência Gov", "https://agenciagov.ebc.com.br/noticias/202410/ministerio-da-fazenda-pede-bloqueio-de-mais-de-dois-mil-sites-de-apostas-ilegais-no-brasil"),
    "2025-01-01": ("Poder360", "https://www.poder360.com.br/poder-sportsmkt/bets-saiba-como-funcionara-o-mercado-no-brasil-a-partir-de-2025/"),
    "2026-09-25": ("Poder360", "https://www.poder360.com.br/poder-governo/lula-proibe-bets-no-brasil/"),
}
CORTE = "202606"  # último mês do CAPS com envio completo (os 2 últimos disponíveis são descartados)


def sup(v):
    return None if v is None or v < MIN else int(v)


def registros():
    r = pl.read_parquet(PROCESSED / "sia_f63_registros.parquet").filter(pl.col("cmp").is_between(pl.lit("201801"), pl.lit(CORTE)))
    return r.with_columns(
        pl.when(pl.col("CIDPRI").str.starts_with("F63")).then(pl.col("CIDPRI")).otherwise(pl.col("CIDASSOC")).alias("cid"),
        pl.col("cmp").str.slice(0, 4).cast(pl.Int32).alias("ano"),
    )


def serie_nacional(r):
    m = (r.group_by("cmp").agg(
            pl.col("id").filter(pl.col("cid") == "F630").n_unique().alias("f630"),
            pl.col("id").filter(pl.col("cid").is_in(["F631", "F632", "F633"])).n_unique().alias("placebo"))
         .sort("cmp"))
    gt = (pl.read_parquet(PROCESSED / "google_trends_uf.parquet").filter(pl.col("uf") == "BR")
          .select(pl.col("data").dt.strftime("%Y%m").alias("cmp"), pl.col("indice").cast(pl.Int32).alias("trends")))
    gt = gt.filter(pl.col("cmp") < "202611")  # nov/2026 é parcial
    caps = [{"cmp": d["cmp"], "f630": sup(d["f630"]), "placebo": sup(d["placebo"])} for d in m.to_dicts()]
    return {"caps": caps, "trends": gt.to_dicts()}


def anual(r):
    a = r.group_by("ano").agg(
        pl.col("id").filter(pl.col("cid") == "F630").n_unique().alias("f630"),
        pl.col("id").filter(pl.col("cid").is_in(["F631", "F632", "F633"])).n_unique().alias("placebo"),
        pl.col("cmp").n_unique().alias("meses")).sort("ano")
    return [{k: (sup(v) if k in ("f630", "placebo") else v) for k, v in d.items()} for d in a.to_dicts()]


def novos(r):
    h = pl.read_parquet(PROCESSED / "sia_f63_historico.parquet").with_columns(pl.col("cmp").str.to_date("%Y%m").alias("data"))
    t0 = (r.filter(pl.col("cid") == "F630").with_columns(pl.col("cmp").str.to_date("%Y%m").alias("data"))
          .group_by("id").agg(pl.col("data").min().alias("t0")))
    ant = h.join(t0, on="id").filter((pl.col("data") < pl.col("t0")) & (pl.col("data") >= pl.col("t0").dt.offset_by("-12mo")))
    tinha = ant.select("id").unique().with_columns(pl.lit(True).alias("tinha"))
    c = (t0.filter(pl.col("t0") >= pl.date(2019, 1, 1)).join(tinha, on="id", how="left")
         .with_columns(pl.col("tinha").fill_null(False), pl.col("t0").dt.year().alias("ano"))
         .group_by("ano").agg((~pl.col("tinha")).sum().alias("novos"), pl.col("tinha").sum().alias("ja")).sort("ano"))
    return [{"ano": d["ano"], "novos": sup(d["novos"]), "ja": sup(d["ja"])} for d in c.to_dicts()]


def perfil(r):
    faixas = ["0-17", "18-24", "25-34", "35-44", "45-59", "60+"]
    f = (r.filter((pl.col("cid") == "F630") & pl.col("faixa").is_not_null()).unique(["id", "cmp"])
         .group_by("ano", "SEXOPAC", "faixa").len("n"))
    p = (pl.read_parquet(PROCESSED / "sia_perfil.parquet").filter((pl.col("grupo") == "mental") & pl.col("faixa").is_not_null()
                                                                   & pl.col("cmp").is_between(pl.lit("201801"), pl.lit(CORTE)))
         .with_columns(pl.col("cmp").str.slice(0, 4).cast(pl.Int32).alias("ano"))
         .group_by("ano", "SEXOPAC", "faixa").agg(pl.col("pacientes").sum().alias("n")))
    out = []
    for sexo in ["F", "M"]:
        for fx in faixas:
            def n(df, ano):
                v = df.filter((pl.col("ano") == ano) & (pl.col("SEXOPAC") == sexo) & (pl.col("faixa") == fx))["n"]
                return int(v[0]) if len(v) else 0
            out.append({"sexo": sexo, "faixa": fx,
                        "f630_2022": n(f, 2022), "f630_2025": n(f, 2025),
                        "mental_2022": n(p, 2022), "mental_2025": n(p, 2025)})
    tot = {k: sum(d[k] for d in out) for k in ["f630_2022", "f630_2025", "mental_2022", "mental_2025"]}
    for d in out:
        d["pct_f630_2025"] = d["f630_2025"] / tot["f630_2025"] * 100 if d["f630_2025"] >= MIN else None
        d["pct_mental_2025"] = d["mental_2025"] / tot["mental_2025"] * 100
        d["cresc_f630"] = d["f630_2025"] / d["f630_2022"] if min(d["f630_2022"], d["f630_2025"]) >= MIN else None
        d["cresc_mental"] = d["mental_2025"] / d["mental_2022"]
        for k in ["f630_2022", "f630_2025"]:
            d[k] = sup(d[k])
    mulheres = {"f630_2025": sum(d["f630_2025"] or 0 for d in out if d["sexo"] == "F") / tot["f630_2025"] * 100,
                "mental_2025": sum(d["mental_2025"] for d in out if d["sexo"] == "F") / tot["mental_2025"] * 100}
    return out, mulheres






def main():
    r = registros()
    perf, mulheres = perfil(r)
    dados = {
        "corte": CORTE, "choques": CHOQUES, "noticias": NOTICIAS, "pandemia": PANDEMIA,
        "serie": serie_nacional(r), "anual": anual(r), "novos": novos(r),
        "perfil": perf, "mulheres": mulheres,
    }
    js = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    corpo = (ROOT / "site" / "modelo.html").read_text().replace("/*__DADOS__*/null", js)
    # artifact.html: só o conteúdo (a publicação no claude.ai acrescenta doctype/head/body)
    (ROOT / "site" / "artifact.html").write_text(corpo)
    # index.html: página completa, para abrir direto no navegador ou publicar no GitHub Pages
    cab = ('<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
           '<style>:root{color-scheme:light;padding:env(safe-area-inset-top,0px) 0 env(safe-area-inset-bottom,0px)}'
           'body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
           '</head><body>\n')
    (ROOT / "site" / "index.html").write_text(cab + corpo + "\n</body></html>\n")
    print(f"✓ site/index.html e site/artifact.html ({len(js) / 1024:.0f} KB de dados)")


if __name__ == "__main__":
    main()
