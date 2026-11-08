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
from src.config import CHOQUES, PANDEMIA, pasta  # noqa: E402

MIN = 5
# Aba e trechos do Congresso (votação de 2023, emendas à MP 1.394, projetos). Desligado por enquanto: o site foca
# em saúde mental. O conteúdo continua no modelo (marcado com data-congresso); para religar, troque para True.
MOSTRAR_CONGRESSO = False
# CPI das Bets no Senado: instalada em 12/11/2024, encerrada com o relatório rejeitado em 12/06/2025.
CPI = {"inicio": "2024-11-12", "fim": "2025-06-12",
       "url": "https://www12.senado.leg.br/radio/1/noticia/2024/11/12/cpi-das-bets-e-instalada-e-vai-investigar-influenciadores-donos-das-apostas-e-crime-de-lavagem-de-dinheiro"}
# Uma notícia por marco regulatório (mesma ordem de src.config.CHOQUES). Trocar aqui para mudar o link.
NOTICIAS = {
    "2018-12-12": ("Agência Brasil", "https://agenciabrasil.ebc.com.br/politica/noticia/2026-10/origem-das-bets-passa-por-lobby-estrangeiro-e-jabutis-no-congresso"),
    "2023-12-29": ("Agência Senado", "https://www12.senado.leg.br/noticias/materias/2024/01/05/regras-para-apostas-veja-o-que-muda-com-a-nova-lei"),
    "2024-10-01": ("Agência Brasil", "https://agenciabrasil.ebc.com.br/economia/noticia/2024-10/bets-nao-autorizadas-serao-suspensas-nesta-terca"),
    "2025-01-01": ("CNN Brasil", "https://www.cnnbrasil.com.br/economia/money/macroeconomia/mercado-regulado-de-bets-comeca-nesta-quarta-1o-veja-o-que-muda/"),
    "2026-09-25": ("Agência Brasil", "https://agenciabrasil.ebc.com.br/economia/noticia/2026-09/mp-proibe-bets-no-brasil-e-determina-devolucao-de-saldo-ao-apostador"),
}
CORTE = "202606"  # último mês do CAPS com envio completo (os 2 últimos disponíveis são descartados)


def sup(v):
    return None if v is None or v < MIN else int(v)


def registros():
    r = pl.read_parquet(pasta("caps") / "sia_f63_registros.parquet").filter(pl.col("cmp").is_between(pl.lit("201801"), pl.lit(CORTE)))
    return r.with_columns(
        pl.when(pl.col("CIDPRI").str.starts_with("F63")).then(pl.col("CIDPRI")).otherwise(pl.col("CIDASSOC")).alias("cid"),
        pl.col("cmp").str.slice(0, 4).cast(pl.Int32).alias("ano"),
    )


def serie_nacional(r):
    m = (r.group_by("cmp").agg(
            pl.col("id").filter(pl.col("cid") == "F630").n_unique().alias("f630"),
            pl.col("id").filter(pl.col("cid").is_in(["F631", "F632", "F633"])).n_unique().alias("placebo"))
         .sort("cmp"))
    gt = (pl.read_parquet(pasta("exposicao") / "google_trends_uf.parquet").filter(pl.col("uf") == "BR")
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
    h = pl.read_parquet(pasta("caps") / "sia_f63_historico.parquet").with_columns(pl.col("cmp").str.to_date("%Y%m").alias("data"))
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
    p = (pl.read_parquet(pasta("caps") / "sia_perfil.parquet").filter((pl.col("grupo") == "mental") & pl.col("faixa").is_not_null()
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






def atencao_primaria():
    """SISAB: atendimentos individuais com F63.0 por mês, referência de saúde mental, perfil por idade e sexo."""
    a = pl.read_parquet(pasta("atencao_primaria") / "sisab_aps.parquet")
    PLACEBO = ["piromania_cid", "cleptomania_cid", "tricotilomania_cid"]  # controle, como no CAPS
    REF = ["depressao_cid", "depressao_rec_cid", "ansiedade_cid", "estresse_cid", "alcool_cid", "esquizofrenia_cid"]
    t = a.filter(pl.col("recorte") == "total")
    m = (t.group_by("cmp").agg(pl.col("atendimentos").filter(pl.col("grupo") == "jogo_cid").sum().alias("jogo"),
                               pl.col("atendimentos").filter(pl.col("grupo").is_in(REF)).sum().alias("ref"),
                               pl.col("atendimentos").filter(pl.col("grupo").is_in(PLACEBO)).sum().alias("placebo")).sort("cmp"))
    mensal = [{"cmp": d["cmp"], "jogo": sup(d["jogo"]), "placebo": sup(d["placebo"]), "ref": d["ref"], "por10mil": round(d["jogo"] / d["ref"] * 1e4, 2) if d["jogo"] >= MIN else None}
              for d in m.to_dicts()]
    an = (m.with_columns(pl.col("cmp").str.slice(0, 4).cast(pl.Int32).alias("ano")).group_by("ano")
          .agg((pl.col("jogo").sum() / pl.len()).alias("jogo_mes"), (pl.col("jogo").sum() / pl.col("ref").sum() * 1e4).alias("por10mil"), (pl.col("ref").sum() / pl.len()).alias("ref_mes"),
               pl.len().alias("meses")).sort("ano"))
    # saúde mental em geral = soma dos diagnósticos de referência (mesmo papel do "mental" no CAPS)
    g = pl.when(pl.col("grupo") == "jogo_cid").then(pl.lit("jogo")).when(pl.col("grupo").is_in(REF)).then(pl.lit("ref"))
    # pirâmide 2025: sexo × faixa, consultados juntos (recorte "sexofaixa")
    px = (a.filter((pl.col("recorte") == "sexofaixa") & pl.col("cmp").str.starts_with("2025")).with_columns(g.alias("g")).drop_nulls("g")
          .with_columns(pl.col("valor").str.split("_").list.get(0).alias("sexo"), pl.col("valor").str.split("_").list.get(1).alias("faixa"))
          .group_by("g", "sexo", "faixa").agg(pl.col("atendimentos").sum())
          .with_columns((pl.col("atendimentos") / pl.col("atendimentos").sum().over("g") * 100).alias("pct")))
    piramide = []
    for sx in ["F", "M"]:
        for fx in ["0-17", "18-24", "25-34", "35-44", "45-59", "60+"]:
            v = {r["g"]: r for r in px.filter((pl.col("sexo") == sx) & (pl.col("faixa") == fx)).to_dicts()}
            j = v.get("jogo")
            piramide.append({"sexo": sx, "faixa": fx, "j": round(j["pct"], 1) if j and j["atendimentos"] >= MIN else None,
                             "r": round(v["ref"]["pct"], 1) if "ref" in v else None})
    return {"mensal": mensal, "piramide": piramide, "anual": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in d.items()} for d in an.to_dicts()],
            "fim": m["cmp"].max()}


def conduta():
    """Conduta ao fim do atendimento na atenção primária, jan/2025–último mês: % dos atendimentos de cada diagnóstico
    com cada conduta (um atendimento pode ter mais de uma, então não soma 100)."""
    c = pl.read_parquet(pasta("atencao_primaria") / "sisab_conduta.parquet").filter(pl.col("cmp") >= "202501")
    a = (pl.read_parquet(pasta("atencao_primaria") / "sisab_aps.parquet")
         .filter((pl.col("recorte") == "total") & (pl.col("cmp") >= "202501")).group_by("grupo").agg(pl.col("atendimentos").sum()))
    COND = {"Alta do episódio": "alta", "Retorno para consulta agendada": "retorno", "Retorno p/ cuidado continuado/": "continuado",
            "Encaminhamento p/ serviço espe": "especializado", "Encaminhamento p/ CAPS": "caps"}
    out = {}
    for g in ["jogo_cid", "ansiedade_cid", "depressao_cid", "alcool_cid"]:
        n = a.filter(pl.col("grupo") == g)["atendimentos"].item()
        x = c.filter(pl.col("grupo") == g).group_by("conduta").agg(pl.col("n").sum())
        out[g] = {"n": n, **{k: round(x.filter(pl.col("conduta") == nome)["n"].sum() / n * 100, 1) for nome, k in COND.items()}}
    return {"grupos": out, "fim": c["cmp"].max()}


def trajetorias():
    """Diagnóstico novo nos 12 meses após o 1º diagnóstico (jan/2019–jun/2025), padronizado por sexo e idade dos
    pacientes de jogo patológico. Mesma lógica de notebooks/f63_trajetoria.ipynb."""
    corte = (2026 - 2018) * 12 + 6 - 1
    t = pl.read_parquet(pasta("caps") / "sia_trajetorias.parquet").filter(pl.col("mes").is_between(0, corte))
    entradas, desfechos = [1, 2, 3, 5, 6], [6, 5, 3, 2]
    prim = t.group_by("id", "grupo").agg(pl.col("mes").min().alias("t0"))
    perf = t.join(prim, left_on=["id", "grupo", "mes"], right_on=["id", "grupo", "t0"]).group_by("id", "grupo").agg(pl.col("sexo").first(), pl.col("faixa").first())
    co = (prim.filter(pl.col("grupo").is_in(entradas) & pl.col("t0").is_between(12, corte - 12)).join(perf, on=["id", "grupo"])
          .drop_nulls(["sexo", "faixa"]).rename({"grupo": "entrada"}))
    j = t.select("id", "mes", "grupo").join(co.select("id", "entrada", "t0"), on="id")
    antes = j.filter((pl.col("mes") >= pl.col("t0") - 12) & (pl.col("mes") < pl.col("t0"))).select("id", "entrada", "grupo").unique()
    depois = j.filter((pl.col("mes") > pl.col("t0")) & (pl.col("mes") <= pl.col("t0") + 12)).select("id", "entrada", "grupo").unique()
    novo = depois.join(antes, on=["id", "entrada", "grupo"], how="anti").filter(pl.col("grupo") != pl.col("entrada"))
    fica = j.filter((pl.col("mes") > pl.col("t0") + 6) & (pl.col("mes") <= pl.col("t0") + 12)).select("id", "entrada").unique().with_columns(pl.lit(True).alias("fica"))
    b = co.join(fica, on=["id", "entrada"], how="left").with_columns(pl.col("fica").fill_null(False))
    for g in desfechos:
        ids = novo.filter(pl.col("grupo") == g).select("id", "entrada").with_columns(pl.lit(True).alias(f"n{g}"))
        b = b.join(ids, on=["id", "entrada"], how="left").with_columns(pl.col(f"n{g}").fill_null(False))
    cols = [f"n{g}" for g in desfechos] + ["fica"]
    w = b.filter(pl.col("entrada") == 1).group_by("sexo", "faixa").len("nj").with_columns((pl.col("nj") / pl.col("nj").sum()).alias("peso"))
    es = b.group_by("entrada", "sexo", "faixa").agg(pl.len().alias("n"), *[pl.col(c).mean() for c in cols])
    out = {}
    for e in entradas:
        n = b.filter(pl.col("entrada") == e).height
        if e == 1:
            vals = {c: b.filter(pl.col("entrada") == 1)[c].mean() * 100 for c in cols}
        else:
            x = es.filter(pl.col("entrada") == e).join(w, on=["sexo", "faixa"])
            vals = {c: float((x[c] * x["peso"]).sum() / x["peso"].sum() * 100) for c in cols}
        out[str(e)] = {"n": n, **{c: round(v, 1) for c, v in vals.items()}}
    return out


def congresso():
    """Votação nominal de 2023 sobre o cassino online, emendas à MP 1.394 e projetos de proibição (dados públicos)."""
    v = pl.read_parquet(pasta("congresso") / "congresso_votacao_cassino_2023.parquet").filter(pl.col("voto") != "outro")
    votos = [[d["casa"], d["nome"], d["partido"], d["uf"], 1 if d["voto"] == "tirar o cassino" else 0, d["url"]] for d in v.to_dicts()]
    em = pl.read_parquet(pasta("congresso") / "mp1394_emendas.parquet").drop("texto").join(
        pl.read_csv(ROOT / "src" / "politica" / "classificacao_mp1394.csv"), on="numero")
    emendas = [[d["numero"], d["parlamentar"], d["partido"], d["uf"], d["cargo"], d["categoria"], d["resumo"], d["url"]] for d in em.sort("numero").to_dicts()]
    pls = pl.read_parquet(pasta("congresso") / "congresso_pls_proibicao.parquet")
    projetos = []
    for (proj, data, alc, ementa, url), g in pls.group_by(["projeto", "data", "alcance", "ementa", "url"], maintain_order=True):
        projetos.append({"projeto": proj, "data": data, "alcance": alc, "ementa": ementa, "url": url,
                         "autores": [[a["autor"], a["partido"], a["uf"]] for a in g.to_dicts()]})
    projetos.sort(key=lambda x: x["data"])
    return {"votos": votos, "emendas": emendas, "projetos": projetos}


def main():
    r = registros()
    perf, _ = perfil(r)
    dados = {
        "corte": CORTE, "choques": CHOQUES, "noticias": NOTICIAS, "pandemia": PANDEMIA, "cpi": CPI,
        "serie": serie_nacional(r), "anual": anual(r), "novos": novos(r),
        "perfil": [{"sexo": d["sexo"], "faixa": d["faixa"], **{k: (round(d[k], 1) if d[k] is not None else None) for k in ("pct_f630_2025", "pct_mental_2025")}} for d in perf], "aps": atencao_primaria(), "conduta": conduta(), "trajetorias": trajetorias(), "congresso": congresso() if MOSTRAR_CONGRESSO else None,
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
