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






def suicidio(r):
    """Taxa de suicídio por 100 mil (SIM; 2025 preliminar) para mulheres por faixa etária, e pessoas
    atendidas por F63.0 entre mulheres de 35–44 anos por ano. População: projeção IBGE por sexo e idade."""
    import re

    sim = (pl.read_parquet(PROCESSED / "sim_graves.parquet")
           .with_columns(pl.col("cmp").str.slice(0, 4).cast(pl.Int32, strict=False).alias("ano"))
           .filter(pl.col("ano").is_between(2018, 2025) & (pl.col("sexo") == "F") & pl.col("faixa").is_not_null())
           .group_by("ano", "faixa").agg(pl.col("obitos_suicidio").sum()))
    proj = json.loads((ROOT / "data" / "raw" / "ibge" / "projecao_sexo_idade.json").read_text())[1:]
    linhas = []
    for x in proj:
        m = re.fullmatch(r"(\d+) anos?( ou mais)?", x["D5N"])
        if m and x["V"].isdigit() and x["D4N"] == "Mulheres":
            linhas.append({"ano": int(x["D6N"]), "idade": int(m.group(1)), "pop": int(x["V"])})
    fx = (pl.when(pl.col("idade") <= 17).then(pl.lit("0-17")).when(pl.col("idade") <= 24).then(pl.lit("18-24"))
          .when(pl.col("idade") <= 34).then(pl.lit("25-34")).when(pl.col("idade") <= 44).then(pl.lit("35-44"))
          .when(pl.col("idade") <= 59).then(pl.lit("45-59")).otherwise(pl.lit("60+")))
    pop = pl.DataFrame(linhas).with_columns(fx.alias("faixa")).group_by("ano", "faixa").agg(pl.col("pop").sum())
    t = sim.join(pop, on=["ano", "faixa"]).with_columns((pl.col("obitos_suicidio") / pl.col("pop") * 1e5).alias("taxa")).sort("faixa", "ano")
    taxas = {f: {str(d["ano"]): round(d["taxa"], 2) for d in t.filter(pl.col("faixa") == f).to_dicts()}
             for f in ["18-24", "25-34", "35-44", "45-59"]}
    obitos_35_44 = {str(d["ano"]): int(d["obitos_suicidio"]) for d in t.filter(pl.col("faixa") == "35-44").to_dicts()}
    f63 = (r.filter((pl.col("cid") == "F630") & (pl.col("SEXOPAC") == "F") & (pl.col("faixa") == "35-44"))
           .group_by("ano").agg(pl.col("id").n_unique().alias("n")).sort("ano"))
    return {"taxas": taxas, "obitos_35_44": obitos_35_44,
            "f630_35_44": {str(d["ano"]): sup(d["n"]) for d in f63.to_dicts()}}


def main():
    r = registros()
    perf, mulheres = perfil(r)
    dados = {
        "corte": CORTE, "choques": CHOQUES, "pandemia": PANDEMIA,
        "serie": serie_nacional(r), "anual": anual(r), "novos": novos(r),
        "perfil": perf, "mulheres": mulheres, "suicidio": suicidio(r),
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
