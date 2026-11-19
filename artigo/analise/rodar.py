"""Jogo patológico (F63.0) na atenção primária (APS) e nos CAPS, Brasil, 2018–2026: todas as análises do artigo.

Hipóteses, modelos e testes estão descritos em artigo/ANALISE.md, na mesma ordem das seções (1 em dados.py, 2 em
joinpoint.py, 3–8 aqui, 9 em figuras.py).
Só dados públicos agregados: nenhum identificador de paciente é lido (ver seção 1).

    uv run python artigo/analise/rodar.py                  # ~15 min (bootstrap com 999 réplicas)
    uv run python artigo/analise/rodar.py --B 99           # teste rápido
    uv run python artigo/analise/rodar.py --refazer-caps   # reagrega as RAAS a partir dos .dbc do DATASUS

Entradas (em data/, fora do repositório):
    data/atencao_primaria/processed/sisab_aps.parquet     relatório público do SISAB (src/saude_mental/sisab_aps.py)
    data/caps/raw/datasus/SIASUS/200801_/Dados/PS*.dbc    RAAS do SIA-PS (FTP do DATASUS; baixados se faltarem)
    data/ibge/processed/populacao_municipio.parquet       estimativas de população do IBGE
Saídas: artigo/resultados/ (resultados.txt, numeros.json e figuras/*.png|pdf|svg)
"""

import argparse
import json
from datetime import date

import numpy as np
import para_latex
import polars as pl
import polars.selectors as cs
from comum import (
    DBC,
    FIG,
    FIM_APS,
    FIM_CAPS,
    INESPEC_CID,
    INICIO,
    INICIO_APS,
    LINHAS,
    NUM,
    OUT,
    PANDEMIA,
    RAAS,
    ROTULO,
    UFS,
    dec,
    fmt_mes,
    num,
    out,
    r0,
    secao,
    tabela,
)
from dados import conduta_aps, perfil_2025, populacao, refazer_caps, serie_aps, serie_caps
from figuras import figuras
from joinpoint import (
    bootstrap,
    excesso,
    guardar,
    ic_quebra,
    mes_mais,
    relatar,
    selecionar,
    sorteio_blocos,
    tempo,
    vpa,
)

# %% 3–8. Análises ---------------------------------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--B", type=int, default=999)
    ap.add_argument("--processos", type=int, default=20)
    ap.add_argument("--refazer-caps", action="store_true")
    x = ap.parse_args()
    if x.refazer_caps or not RAAS.exists():
        refazer_caps(x.processos)

    a_completa, c = serie_aps(), serie_caps()
    a = a_completa.filter(pl.col("cmp") >= INICIO_APS)
    S = {"aps": a, "caps": c}
    v = lambda df, col: df[col].to_numpy().astype(float)
    M = {}
    for f, df in S.items():
        meses = df["cmp"].to_list()
        M[f"{f}_jogo_ref"] = (meses, {"y": v(df, "jogo"), "fam": "nb", "off": np.log(v(df, "referencia"))})
        M[f"{f}_controle_ref"] = (meses, {"y": v(df, "controle"), "fam": "nb", "off": np.log(v(df, "referencia"))})
        M[f"{f}_jogo_controle"] = (meses, {"y": v(df, "jogo"), "fam": "bin", "n": v(df, "jogo") + v(df, "controle")})

    out(f"Jogo patológico (F63.0) na APS e nos CAPS, Brasil — gerado por artigo/analise/rodar.py em {date.today():%d/%m/%Y}")
    out(f"APS: SISAB, {fmt_mes(INICIO_APS)}–{fmt_mes(FIM_APS)} ({a.height} meses). "
        f"CAPS: RAAS/SIA-PS, {fmt_mes(INICIO)}–{fmt_mes(FIM_CAPS)} ({c.height} meses). Bootstrap: {x.B} réplicas.")

    # ---------------------------------------------------------------- 3. Descritiva
    secao("3. DESCRITIVA (registros por ano)")
    j18 = a_completa.filter(pl.col("cmp").str.starts_with("2018"))["jogo"]
    NUM.update({"aps.jan2018": int(j18[0]), "aps.2018_min": int(j18[1:].min()), "aps.2018_max": int(j18[1:].max())})
    arqs = {p.name for p in DBC.glob("PS*.dbc") if p.name[2:4] in UFS and "20" + p.name[4:8] >= INICIO}
    ult_arq = max("20" + n_[4:8] for n_ in arqs)
    esperados = {f"PS{u}{mes_mais(INICIO, k)[2:]}.dbc" for u in UFS for k in range(int(tempo([INICIO, ult_arq])[1]) + 1)}
    faltam = sorted(esperados - arqs)
    NUM.update({"caps.arquivos": num(len(esperados)), "caps.faltam": len(faltam),
                "caps.faltantes": "; ".join(f"{n_[2:4]}, {fmt_mes('20' + n_[4:8])}" for n_ in faltam)})
    out(f"Arquivos de RAAS: {len(arqs)} de {len(esperados)} (faltam: {NUM['caps.faltantes'] or 'nenhum'})")
    pop = populacao()
    for f, df in (("aps", a), ("caps", c)):  # APS sem jan/2018, como nos modelos
        cols = ["jogo", "controle", "referencia", "jogo_F", "jogo_M"]
        an = (df.with_columns(ano=pl.col("cmp").str.slice(0, 4).cast(pl.Int32)).group_by("ano")
              .agg(*[pl.col(k).sum() for k in cols], meses=pl.len()).join(pop, on="ano").sort("ano"))
        out(f"\n{f.upper()}")
        tabela(an.select(
            "ano", "meses", pl.col("jogo").alias("F63.0"), pl.col("controle").alias("F63.1–3"),
            pl.col("referencia").alias("referência"),
            (1e4 * pl.col("jogo") / pl.col("referencia")).alias("F63.0/10 mil ref"),
            (1e4 * pl.col("controle") / pl.col("referencia")).alias("F63.1–3/10 mil ref"),
            (1e6 * pl.col("jogo") / pl.col("populacao") * 12 / pl.col("meses")).alias("F63.0/milhão hab·ano"),
            (100 * pl.col("jogo_F") / (pl.col("jogo_F") + pl.col("jogo_M"))).alias("% mulheres F63.0")))
        cheios = an.filter(pl.col("meses") == 12)
        tx = 1e4 * cheios["controle"] / cheios["referencia"]
        NUM[f"desc.{f}.taxa_ctrl_min"], NUM[f"desc.{f}.taxa_ctrl_max"] = dec(tx.min()), dec(tx.max())
        for r_ in an.iter_rows(named=True):
            b_ = f"desc.{f}.{r_['ano']}"
            NUM.update({f"{b_}.meses": r_["meses"], f"{b_}.jogo": num(r_["jogo"]), f"{b_}.controle": num(r_["controle"]),
                        f"{b_}.ref": num(r_["referencia"]), f"{b_}.taxa": dec(1e4 * r_["jogo"] / r_["referencia"]),
                        f"{b_}.taxa_ctrl": dec(1e4 * r_["controle"] / r_["referencia"])})

    out("\n3b. Perfil por sexo e faixa etária em 2025 (% dos registros de cada grupo; registros sem sexo F/M ou sem "
        "idade ficam de fora). APS: atendimentos do SISAB; CAPS: linhas de RAAS.")
    PERFIL = perfil_2025()
    tabela(PERFIL.select("sexo", "faixa", *[pl.col(k).round(1) for k in PERFIL.columns if k.endswith("%")]))
    for rede in ("APS", "CAPS"):
        for g, gk in (("F63.0", "jogo"), ("referência", "ref")):
            col = pl.col(f"{rede} {g} %")
            b_ = f"perfil.{rede.lower()}.{gk}"
            NUM.update({f"{b_}.25_44": r0(PERFIL.filter(pl.col("faixa").is_in(["25-34", "35-44"]))[f"{rede} {g} %"].sum()),
                        f"{b_}.h18_24": r0(PERFIL.filter((pl.col("sexo") == "M") & (pl.col("faixa") == "18-24"))
                                           [f"{rede} {g} %"].sum()),
                        f"{b_}.60": r0(PERFIL.filter(pl.col("faixa") == "60+")[f"{rede} {g} %"].sum()),
                        f"{b_}.0_17": r0(PERFIL.filter(pl.col("faixa") == "0-17")[f"{rede} {g} %"].sum()),
                        f"{b_}.mulheres": r0(PERFIL.filter(pl.col("sexo") == "F").select(col.sum()).item())})
    NUM["tab.perfil"] = PERFIL.with_columns(cs.float().round(1)).to_dicts()

    out("\n3c. Conduta registrada ao fim do atendimento na APS, jan/2025–" + fmt_mes(FIM_APS) + " (% dos atendimentos de "
        "cada diagnóstico; um atendimento pode ter mais de uma conduta)")
    CONDUTA = conduta_aps()
    tabela(CONDUTA)
    NUM["tab.conduta"] = CONDUTA.to_dicts()
    for r_ in CONDUTA.iter_rows(named=True):
        for k_, val in r_.items():
            if k_ != "diagnóstico":
                NUM[f"cond.{r_['diagnóstico']}.{k_}"] = num(val) if k_ == "atendimentos" else dec(val)

    # ---------------------------------------------------------------- 4. H1: efeito principal
    secao("4. H1 — O REGISTRO DE JOGO PATOLÓGICO CRESCEU ALÉM DO CRESCIMENTO DO SISTEMA?")
    out("\n4a. Crescimento do sistema (denominadores, contagens sem offset; NB, K por BIC)")
    sistema = {"APS · referência (F32, F33, F41, F43, F10, F20)": (a, "referencia"),
               "APS · referência ampliada (CID + CIAP de saúde mental)": (a, "ref_ampla"),
               "CAPS · referência (F32, F33, F41, F43, F10, F20)": (c, "referencia"),
               "CAPS · todas as RAAS": (c, "total")}
    mapa = sorteio_blocos(x.B)
    for (rot, (df, col)), chave in zip(sistema.items(), ("aps_ref_sis", "aps_refampla_sis", "caps_ref_sis",
                                                         "caps_total_sis")):
        aj = selecionar(v(df, col), df["cmp"].to_list(), "nb")[0]
        bootstrap(aj, mapa, x.processos)
        relatar(rot, aj)
        guardar(chave, aj)

    out("\n4b. Modelo principal: F63.0 com offset log(referência) — tendência da taxa de F63.0 por registro de "
        "referência, já descontado o crescimento do sistema")
    out("IC95% por bootstrap de blocos (inclui a incerteza sobre a posição das quebras; K fixo nas réplicas). A "
        "existência da quebra é decidida pelo BIC.")
    A, TODOS = {}, {}
    for nome in ("aps_jogo_ref", "caps_jogo_ref"):
        meses, kw = M[nome]
        A[nome], TODOS[nome] = selecionar(meses=meses, **kw)
        bootstrap(A[nome], mapa, x.processos)
        relatar(ROTULO[nome], A[nome], TODOS[nome])
        guardar(nome, A[nome])
        NUM[f"{nome}.bic"] = {k: num(a_.crit, 1) for k, a_ in TODOS[nome].items()}

    # CAPS com os F63 sem especificação somados ao desfecho (sensibilidade da seção 5; aqui só para o excesso)
    A["caps_jogo_inespec_ref"] = selecionar(meses=M["caps_jogo_ref"][0], y=v(c, "jogo") + v(c, "inespec"), fam="nb",
                                            off=np.log(v(c, "referencia")))[0]
    bootstrap(A["caps_jogo_inespec_ref"], mapa, x.processos)

    out("\n4c. Magnitude: registros acima da linha de base pré-inflexão (descritivo)")
    out("Linha de base principal = o segmento anterior à quebra final prolongado (mesmo modelo, sem a última mudança "
        "de inclinação): supõe que, sem a inflexão, a taxa seguiria a tendência que já tinha. Alternativa = taxa "
        "congelada no nível da quebra. As duas incluem o crescimento do sistema (offset) e a sazonalidade. Janelas = anos "
        "de calendário, as mesmas em todas as réplicas; o IC95% bootstrap é a incerteza da linha de base (β e posição "
        "da quebra refeitos em cada réplica; observado fixo). Não é estimativa do efeito de uma lei: a quebra é "
        "estimada, não uma data de intervenção.")
    exc = []

    def fracao(r):
        return f"{dec(100 * r['exc'] / r['obs'], 0)}% ({dec(100 * r['exc_lo'] / r['obs'], 0)}; {dec(100 * r['exc_hi'] / r['obs'], 0)})"

    for nome, rot in (("aps_jogo_ref", "APS · F63.0"), ("caps_jogo_ref", "CAPS · F63.0"),
                      ("caps_jogo_inespec_ref", "CAPS · F63.0 + F63, F63.8, F63.9")):
        aj = A[nome]
        for ano in range(2023, int(aj.meses[-1][:4]) + 1):
            ini, fim = f"{ano}01", min(f"{ano}12", aj.meses[-1])
            p, q = excesso(aj, ini, fim), excesso(aj, ini, fim, "congelada")
            exc.append({"modelo": rot, "janela": f"{fmt_mes(ini)}–{fmt_mes(fim)}", "observado": num(p["obs"]),
                        "esperado (IC95%)": f"{num(p['esp'])} ({num(p['esp_lo'])}; {num(p['esp_hi'])})",
                        "excesso (IC95%)": f"{num(p['exc'])} ({num(p['exc_lo'])}; {num(p['exc_hi'])})",
                        "% do observado (IC95%)": fracao(p),
                        "taxa congelada: excesso (%)": f"{num(q['exc'])} ({dec(100 * q['exc'] / q['obs'], 0)}%)"})
            rede = {"aps_jogo_ref": "aps", "caps_jogo_ref": "caps", "caps_jogo_inespec_ref": "capsinesp"}[nome]
            b_ = f"exc.{rede}.{ano}"
            NUM.update({f"{b_}.janela": f"{fmt_mes(ini)}–{fmt_mes(fim)}", f"{b_}.obs": num(p["obs"]),
                        f"{b_}.esp": num(p["esp"]), f"{b_}.esp_li": num(p["esp_lo"]), f"{b_}.esp_ls": num(p["esp_hi"]),
                        f"{b_}.exc": num(p["exc"]), f"{b_}.exc_li": num(p["exc_lo"]), f"{b_}.exc_ls": num(p["exc_hi"]),
                        f"{b_}.pct": r0(100 * p["exc"] / p["obs"]), f"{b_}.pct_li": r0(100 * p["exc_lo"] / p["obs"]),
                        f"{b_}.pct_ls": r0(100 * p["exc_hi"] / p["obs"]), f"{b_}.cong": num(q["exc"]),
                        f"{b_}.cong_pct": r0(100 * q["exc"] / q["obs"])})
    tabela(pl.DataFrame(exc))
    out(f"Quebra final: APS {fmt_mes(mes_mais(A['aps_jogo_ref'].meses[0], A['aps_jogo_ref'].taus[-1]))}; CAPS "
        f"{fmt_mes(mes_mais(c['cmp'][0], A['caps_jogo_ref'].taus[-1]))}; CAPS com F63 sem especificação "
        f"{fmt_mes(mes_mais(c['cmp'][0], A['caps_jogo_inespec_ref'].taus[-1]))}. No recorte com F63 sem especificação, o "
        "excesso absoluto é maior porque esses códigos também crescem desde out/2021 (seção 5a); compare pela % do "
        "observado.")

    # ---------------------------------------------------------------- 5. Especificidade
    secao("5. ESPECIFICIDADE — CONTROLE NEGATIVO (F63.1–F63.3: piromania, cleptomania, tricotilomania)")
    out("\n5a. Controle com o mesmo modelo do H1 (esperado: sem alta)")
    for nome in ("aps_controle_ref", "caps_controle_ref"):
        meses, kw = M[nome]
        A[nome], TODOS[nome] = selecionar(meses=meses, **kw)
        bootstrap(A[nome], mapa, x.processos)
        relatar(ROTULO[nome], A[nome], TODOS[nome])
        guardar(nome, A[nome])
    out("\nCódigos F63 sem especificação (F63, F63.8, F63.9; só CAPS). Não são controle: podem conter casos de jogo. "
        "Se crescem junto, parte da alta de F63.0 pode ser só codificação mais específica (F63 → F63.0).")
    aj = selecionar(v(c, "inespec"), c["cmp"].to_list(), "nb", off=np.log(v(c, "referencia")))[0]
    bootstrap(aj, mapa, x.processos)
    relatar("CAPS · F63, F63.8, F63.9 / referência", aj)
    guardar("caps_inespec_ref", aj)
    r_ = pl.read_parquet(RAAS).filter(pl.col("cmp").is_between(pl.lit("202201"), pl.lit(FIM_CAPS))
                                      & pl.col("faixa").is_not_null())
    for rot, f_ in (("F63.0", pl.col("cid") == "F630"), ("F63, F63.8, F63.9", pl.col("cid").is_in(INESPEC_CID))):
        x_ = r_.filter(f_)
        pm = 100 * x_.filter(pl.col('faixa') == '0-17')['registros'].sum() / x_['registros'].sum()
        out(f"  {rot}: {dec(pm, 0)}% dos registros de jan/2022 a {fmt_mes(FIM_CAPS)} em menores de 18 anos")
        NUM["idade.f630" if rot == "F63.0" else "idade.inesp"] = r0(pm)
    out("\n5b. Jogo contra controle: binomial F63.0/(F63.0 + F63.1–3). A inclinação é a diferença entre as taxas de "
        "crescimento do jogo e do controle (VPA = crescimento anual da razão F63.0 : controle)")
    for nome in ("aps_jogo_controle", "caps_jogo_controle"):
        meses, kw = M[nome]
        A[nome], TODOS[nome] = selecionar(meses=meses, **kw)
        bootstrap(A[nome], mapa, x.processos)
        relatar(ROTULO[nome], A[nome], TODOS[nome])
        guardar(nome, A[nome])

    # ---------------------------------------------------------------- 6. Robustez
    secao("6. ROBUSTEZ — VPA DO SEGMENTO FINAL EM CADA CENÁRIO (estimativa pontual; IC95% bootstrap só na análise "
          "principal)")
    sens = []

    def registrar(nome, cenario, aj):
        li, ls = (vpa(np.percentile(aj.boot["incl"][:, -1], [2.5, 97.5])) if aj.boot else (np.nan, np.nan))
        sens.append({"modelo": nome, "cenario": cenario, "K": aj.k,
                     "quebra_final": mes_mais(aj.meses[0], aj.taus[-1]) if aj.k else "",
                     "vpa": float(vpa(aj.contraste(aj.k) @ aj.beta)), "li": float(li), "ls": float(ls)})

    for nome in ("aps_jogo_ref", "caps_jogo_ref", "aps_jogo_controle", "caps_jogo_controle"):
        meses, kw = M[nome]
        df = S[nome.split("_")[0]]
        aj = A[nome]
        registrar(nome, "principal", aj)
        registrar(nome, "até 3 quebras", selecionar(meses=meses, kmax=3, **kw)[0])
        registrar(nome, "1 quebra (fixo)", selecionar(meses=meses, k_fixo=1, **kw)[0])
        for cen, keep, pand in (("sem meses da pandemia", [not (PANDEMIA[0] <= m <= PANDEMIA[1]) for m in meses], False),
                                ("até dez/2025", [m <= "202512" for m in meses], True)):
            keep = np.array(keep)
            kw2 = {k: (val[keep] if isinstance(val, np.ndarray) else val) for k, val in kw.items()}
            registrar(nome, cen, selecionar(meses=[m for m, k in zip(meses, keep) if k], pandemia=pand, **kw2)[0])
        if nome.startswith("aps"):
            mc = a_completa["cmp"].to_list()
            yc = v(a_completa, "jogo")
            kwc = ({"fam": "nb", "off": np.log(v(a_completa, "referencia"))} if nome.endswith("_ref")
                   else {"fam": "bin", "n": yc + v(a_completa, "controle")})
            registrar(nome, "série completa (com jan/2018)", selecionar(yc, mc, **kwc)[0])
        if nome.endswith("_ref"):  # offset trocado por covariável: o coeficiente de log(referência) é estimado
            registrar(nome, "log(referência) como covariável", selecionar(meses=meses, y=kw["y"], fam="nb", z=kw["off"])[0])
        if nome == "aps_jogo_ref":
            registrar(nome, "referência ampliada (CID + CIAP)",
                      selecionar(meses=meses, y=kw["y"], fam="nb", off=np.log(v(df, "ref_ampla")))[0])
        if nome == "caps_jogo_ref":
            registrar(nome, "referência = capítulo F inteiro",
                      selecionar(meses=meses, y=kw["y"], fam="nb", off=np.log(v(df, "mental")))[0])
            registrar(nome, "no máx. 10 registros por CAPS-mês",
                      selecionar(meses=meses, y=v(df, "jogo_cap10"), fam="nb", off=kw["off"])[0])
            registrar(nome, "desfecho = F63.0 + F63, F63.8, F63.9", A["caps_jogo_inespec_ref"])
            registrar(nome, "só RAAS iniciadas no mês",
                      selecionar(meses=meses, y=v(df, "jogo_inicio"), fam="nb", off=np.log(v(df, "referencia_inicio")))[0])
        if nome.endswith("_controle"):
            registrar(nome, "controle = só F63.3",
                      selecionar(meses=meses, y=kw["y"], fam="bin", n=kw["y"] + v(df, "trico"))[0])
        if nome == "caps_jogo_controle":
            registrar(nome, "comparador = F63, F63.8, F63.9",
                      selecionar(meses=meses, y=kw["y"], fam="bin", n=kw["y"] + v(df, "inespec"))[0])
            registrar(nome, "no máx. 10 registros por CAPS-mês",
                      selecionar(meses=meses, y=v(df, "jogo_cap10"), fam="bin", n=v(df, "jogo_cap10") + v(df, "controle"))[0])
    sens = pl.DataFrame(sens)
    tabela(sens.with_columns(pl.col("modelo").replace(ROTULO),
                             pl.col("quebra_final").map_elements(lambda m: fmt_mes(m) if m else "—", return_dtype=pl.String),
                             pl.col("vpa", "li", "ls").fill_nan(None).round(0).cast(pl.Int64)))
    NUM["tab.robustez"] = sens.with_columns(pl.col("vpa", "li", "ls").fill_nan(None).round(0)).to_dicts()
    for nome in ("aps_jogo_ref", "caps_jogo_ref", "aps_jogo_controle", "caps_jogo_controle"):
        o = sens.filter((pl.col("modelo") == nome) & ~pl.col("cenario").str.contains("F63, F63.8"))
        NUM.update({f"rob.{nome}.min": r0(o["vpa"].min()), f"rob.{nome}.max": r0(o["vpa"].max()),
                    f"rob.{nome}.qmin": fmt_mes(o["quebra_final"].min()), f"rob.{nome}.qmax": fmt_mes(o["quebra_final"].max()),
                    f"rob.{nome}.n": o.height - 1})
        for r_ in sens.filter(pl.col("modelo") == nome).iter_rows(named=True):
            NUM[f"rob.{nome}.{r_['cenario']}"] = r0(r_["vpa"])

    # ---------------------------------------------------------------- 7. Objetivo secundário: onde começou
    secao("7. SECUNDÁRIO — A ALTA COMEÇOU NA APS ANTES DO CAPS? (início do segmento final; bootstrap conjunto)")
    out("Réplicas pareadas: a réplica b da APS e a do CAPS reamostram os mesmos meses de calendário.")
    for par, rot in (("jogo_ref", "F63.0 / referência (modelo principal)"),
                     ("jogo_controle", "F63.0 vs controle (sensibilidade)")):
        qa, qc = A[f"aps_{par}"], A[f"caps_{par}"]
        desl = tempo([qa.meses[0], qc.meses[0]])[1]  # posição do início do CAPS na escala de tempo da APS
        dif = (qc.boot["taus"][:, -1] + desl) - qa.boot["taus"][:, -1]
        est = qc.taus[-1] + desl - qa.taus[-1]
        out(f"\n{rot}")
        out(f"  APS:  {fmt_mes(mes_mais(qa.meses[0], qa.taus[-1]))} (IC95% {' – '.join(map(fmt_mes, ic_quebra(qa)))})")
        out(f"  CAPS: {fmt_mes(mes_mais(qc.meses[0], qc.taus[-1]))} (IC95% {' – '.join(map(fmt_mes, ic_quebra(qc)))})")
        out(f"  defasagem CAPS − APS: {dec(est, 0)} meses (IC95% bootstrap {dec(np.percentile(dif, 2.5), 0)} a "
            f"{dec(np.percentile(dif, 97.5), 0)}); CAPS depois da APS em {np.sum(dif > 0)}/{len(dif)} réplicas")
        b_ = f"lag.{par}"
        NUM.update({f"{b_}.est": r0(est), f"{b_}.li": r0(np.percentile(dif, 2.5)), f"{b_}.ls": r0(np.percentile(dif, 97.5)),
                    f"{b_}.n": int(np.sum(dif > 0)), f"{b_}.B": len(dif)})

    # ---------------------------------------------------------------- 8. Objetivo secundário: feminização
    secao("8. SECUNDÁRIO (DESCRITIVO) — PORCENTAGEM DE MULHERES POR ANO, JOGO E REFERÊNCIA")
    out("Sem IC: registros de uma mesma pessoa não são independentes.")
    for f, df in S.items():
        d = df.filter(pl.col("cmp") >= "202201")
        out(f"\n{f.upper()}")
        an = d.with_columns(ano=pl.col("cmp").str.slice(0, 4)).group_by("ano").agg(
            pl.col("jogo_F", "jogo_M", "referencia_F", "referencia_M").sum()).sort("ano")
        out("  % mulheres por ano (jogo | referência): " + "  ".join(
            f"{r_['ano']}: {100 * r_['jogo_F'] / (r_['jogo_F'] + r_['jogo_M']):.0f} | "
            f"{100 * r_['referencia_F'] / (r_['referencia_F'] + r_['referencia_M']):.0f}" for r_ in an.iter_rows(named=True)))
        for r_ in an.iter_rows(named=True):
            NUM[f"fem.{f}.jogo.{r_['ano']}"] = r0(100 * r_["jogo_F"] / (r_["jogo_F"] + r_["jogo_M"]))
            NUM[f"fem.{f}.ref.{r_['ano']}"] = r0(100 * r_["referencia_F"] / (r_["referencia_F"] + r_["referencia_M"]))

    NUM.update({"B": x.B, "aps.meses": a.height, "caps.meses": c.height, "aps.ini": fmt_mes(INICIO_APS),
                "aps.fim": fmt_mes(FIM_APS), "caps.ini": fmt_mes(INICIO), "caps.fim": fmt_mes(FIM_CAPS),
                "rodada": f"{date.today():%d/%m/%Y}"})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "numeros.json").write_text(json.dumps(NUM, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "resultados.txt").write_text("\n".join(LINHAS) + "\n", encoding="utf-8")
    figuras(A, S, sens, PERFIL)
    para_latex.main()  # tabelas e figuras do artigo em artigo/latex/, com conferência das afirmações do texto
    print(f"\n✓ {OUT / 'resultados.txt'} e {FIG}/")


if __name__ == "__main__":
    main()
