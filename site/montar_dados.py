"""Monta os dados do site (só agregados, com supressão) e grava site/index.html a partir de site/modelo.html.

uv run python site/montar_dados.py

Regras de privacidade aplicadas aqui (o site não recebe nada em nível de pessoa):
- Brasil e UF: pacientes distintos por ano; contagens < 5 viram nulo.
- Cidade: só há o agregado do CAPS por município (F63, todos os subcódigos). Um ano só é mostrado se em
  algum mês houve >= 5 pessoas distintas com F63 (pacientes-mês >= 5 não garante 5 pessoas).
"""

import json
import math
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import CHOQUES, COPAS, PANDEMIA, PROCESSED, RAW  # noqa: E402

MIN = 5
CORTE = "202606"  # último mês do CAPS com envio completo (os 2 últimos disponíveis são descartados)
UF_COD = {"11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO", "21": "MA", "22": "PI",
          "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
          "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF"}
UF_NOME = {"RO": "Rondônia", "AC": "Acre", "AM": "Amazonas", "RR": "Roraima", "PA": "Pará", "AP": "Amapá",
           "TO": "Tocantins", "MA": "Maranhão", "PI": "Piauí", "CE": "Ceará", "RN": "Rio Grande do Norte",
           "PB": "Paraíba", "PE": "Pernambuco", "AL": "Alagoas", "SE": "Sergipe", "BA": "Bahia", "MG": "Minas Gerais",
           "ES": "Espírito Santo", "RJ": "Rio de Janeiro", "SP": "São Paulo", "PR": "Paraná", "SC": "Santa Catarina",
           "RS": "Rio Grande do Sul", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "GO": "Goiás",
           "DF": "Distrito Federal"}
ANOS = list(range(2018, 2027))


def sup(v):
    return None if v is None or v < MIN else int(v)


def registros():
    r = pl.read_parquet(PROCESSED / "sia_f63_registros.parquet").filter(pl.col("cmp").is_between(pl.lit("201801"), pl.lit(CORTE)))
    return r.with_columns(
        pl.when(pl.col("CIDPRI").str.starts_with("F63")).then(pl.col("CIDPRI")).otherwise(pl.col("CIDASSOC")).alias("cid"),
        pl.col("cmp").str.slice(0, 4).cast(pl.Int32).alias("ano"),
        pl.col("cod_uf").replace_strict(UF_COD, default=None).alias("uf"),
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


def ufs(r):
    pop = (pl.read_parquet(PROCESSED / "populacao_municipio.parquet").filter(pl.col("ano") == 2025)
           .with_columns(pl.col("cod_ibge").cast(pl.String).str.slice(0, 2).replace_strict(UF_COD, default=None).alias("uf"))
           .group_by("uf").agg(pl.col("populacao").sum()))
    gt = (pl.read_parquet(PROCESSED / "google_trends_uf.parquet").filter(pl.col("uf") != "BR")
          .group_by("uf").agg(pl.col("indice_comparavel").filter(pl.col("data").dt.year() == 2024).mean().alias("trends_2024")))
    ds = pl.read_parquet(PROCESSED / "datasenado_uf_2024.parquet")
    por_ano = (r.filter(pl.col("cid") == "F630").drop_nulls("uf").group_by("uf", "ano").agg(pl.col("id").n_unique().alias("n")))
    out = {}
    for uf, nome in UF_NOME.items():
        anos = {a: 0 for a in ANOS}
        for d in por_ano.filter(pl.col("uf") == uf).to_dicts():
            anos[d["ano"]] = d["n"]
        p = pop.filter(pl.col("uf") == uf)["populacao"][0]
        n25 = anos[2025]
        g = gt.filter(pl.col("uf") == uf)["trends_2024"]
        dsu = ds.filter(pl.col("uf") == uf).to_dicts()[0]
        out[uf] = {"nome": nome, "pop": int(p), "f630": {str(a): sup(v) for a, v in anos.items()},
                   "taxa_2025": n25 / p * 1e6 if n25 >= MIN else None,
                   "trends_2024": float(g[0]) if len(g) else None,
                   "apostou": dsu["pct_apostou"], "apostou_me": dsu["me_apostou"]}
    return out


def cidades():
    s = (pl.read_parquet(PROCESSED / "sia_caps_municipio.parquet")
         .filter(pl.col("cmp").is_between(pl.lit("201801"), pl.lit(CORTE)))
         .with_columns(pl.col("cmp").str.slice(0, 4).cast(pl.Int32).alias("ano"))
         .group_by("cod_mun6", "cmp", "ano").agg(pl.col("pacientes_f63", "raas_mental").sum()))
    a = s.group_by("cod_mun6", "ano").agg(pl.col("pacientes_f63").mean().alias("media"), pl.col("pacientes_f63").max().alias("max"),
                                          pl.col("raas_mental").sum().alias("mental"))
    mun = pl.read_parquet(PROCESSED / "municipios.parquet").with_columns(pl.col("cod_ibge").cast(pl.String).str.slice(0, 6).alias("cod_mun6"))
    pop = (pl.read_parquet(PROCESSED / "populacao_municipio.parquet").filter(pl.col("ano") == 2025)
           .with_columns(pl.col("cod_ibge").cast(pl.String).str.slice(0, 6).alias("cod_mun6")).select("cod_mun6", "populacao"))
    a = a.join(mun.select("cod_mun6", "municipio", "uf"), on="cod_mun6").join(pop, on="cod_mun6", how="left")
    out = []
    for (cod, nome, uf, popu), g in a.group_by(["cod_mun6", "municipio", "uf", "populacao"]):
        anos = {}
        for d in g.to_dicts():
            anos[str(d["ano"])] = [round(d["media"], 1) if d["max"] >= MIN else None, int(d["mental"])]
        out.append([nome, uf, int(popu or 0), anos])
    out.sort(key=lambda x: (x[0], x[1]))
    return out


def mapa():
    geo = json.loads((RAW / "ibge" / "br_uf.json").read_text())
    lat0 = math.cos(math.radians(-15))
    pts = [(x * lat0, -y) for f in geo["features"] for ring in _aneis(f["geometry"]) for x, y in ring]
    xmin, xmax = min(p[0] for p in pts), max(p[0] for p in pts)
    ymin, ymax = min(p[1] for p in pts), max(p[1] for p in pts)
    W = 560
    esc = W / (xmax - xmin)
    H = (ymax - ymin) * esc
    out = {}
    for f in geo["features"]:
        uf = UF_COD[str(f["properties"]["codarea"])]
        d = ""
        for ring in _aneis(f["geometry"]):
            d += "M" + "L".join(f"{(x * lat0 - xmin) * esc:.1f},{(-y - ymin) * esc:.1f}" for x, y in ring) + "Z"
        out[uf] = d
    return {"w": W, "h": round(H), "ufs": out}


def _aneis(g):
    if g["type"] == "Polygon":
        return g["coordinates"]
    return [ring for poly in g["coordinates"] for ring in poly]


def main():
    r = registros()
    perf, mulheres = perfil(r)
    dados = {
        "corte": CORTE, "choques": CHOQUES, "copas": COPAS, "pandemia": PANDEMIA,
        "serie": serie_nacional(r), "anual": anual(r), "novos": novos(r),
        "perfil": perf, "mulheres": mulheres, "ufs": ufs(r), "cidades": cidades(), "mapa": mapa(),
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
    print(f"✓ site/index.html e site/artifact.html ({len(js) / 1024:.0f} KB de dados, {len(dados['cidades'])} cidades)")


if __name__ == "__main__":
    main()
