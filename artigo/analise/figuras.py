"""9. Figuras do artigo e do material suplementar (PNG 300 dpi, PDF e SVG em artigo/resultados/figuras)."""

from datetime import date

import numpy as np
import polars as pl
from comum import FIG, PANDEMIA, ROTULO, fmt_mes
from dados import FAIXAS
from joinpoint import base, hinges, ic_quebra, mes_mais

# %% 9. Figuras ------------------------------------------------------------------------------------------------------
AZUL, LARANJA, TINTA, TINTA2, GRADE = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e6e5e0"
MARCOS = {"201812": "Lei 13.756", "202312": "Lei 14.790", "202501": "Mercado regulado"}


def figuras(A, S, sens, perfil):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": TINTA2, "axes.labelcolor": TINTA,
        "xtick.color": TINTA2, "ytick.color": TINTA2, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRADE, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "legend.frameon": False, "pdf.fonttype": 42})
    FIG.mkdir(parents=True, exist_ok=True)
    d = lambda m: date(int(m[:4]), int(m[4:]), 15)
    fmt_y = plt.FuncFormatter(lambda val, _: f"{val:g}".replace(".", ","))

    def eixo_tempo(ax, tit):
        ax.set_title(tit, loc="left", fontsize=9, color=TINTA, fontweight="bold")
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.tick_params(axis="x", labelsize=7)
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(fmt_y)
        ax.axvspan(d(PANDEMIA[0]), d(PANDEMIA[1]), color="#efeeea", zorder=0, lw=0)

    def salvar(fig, nome):
        fig.savefig(FIG / f"{nome}.pdf", bbox_inches="tight")
        fig.savefig(FIG / f"{nome}.png", dpi=300, bbox_inches="tight", facecolor="white")
        fig.savefig(FIG / f"{nome}.svg", bbox_inches="tight")  # vetorial: a CSP pede gráficos vetoriais na aprovação
        plt.close(fig)

    def tendencia(aj):  # preditor linear sem sazonalidade (média dos efeitos de mês) e sem offset
        X, ims = aj.X.copy(), [i for i, nm in enumerate(aj.nomes) if nm.startswith("mes")]
        ef = np.r_[0, aj.beta[ims]].mean()
        X[:, ims] = 0
        return X @ aj.beta + ef

    def banda(aj):  # IC95% bootstrap pontual da tendência (β e quebras de cada réplica), na mesma escala de `tendencia`
        X0, _, t = base(aj.meses, aj.pandemia)
        ims = [i for i, nm in enumerate(aj.nomes) if nm.startswith("mes")]
        X0 = X0.copy()
        X0[:, ims] = 0
        curvas = [np.column_stack([X0, hinges(t, tb)]) @ b + np.r_[0, b[ims]].mean()
                  for b, tb in zip(aj.boot["beta"], aj.boot["taus"])]
        return np.percentile(curvas, [2.5, 97.5], axis=0)

    paineis = (("aps", "A. Atenção primária (SISAB)"), ("caps", "B. CAPS (RAAS, SIA-PS)"))

    # Figura 1: volume mensal (média móvel de 3 meses) relativo a 2018 — jogo × sistema × controle
    fig, axs = plt.subplots(1, 2, figsize=(6.7, 3.2))
    for ax, (f, tit) in zip(axs, paineis):
        df = S[f]
        eixo_tempo(ax, tit)
        x = [d(m) for m in df["cmp"]]
        for col, cor, rot in (("jogo", AZUL, "Jogo patológico (F63.0)"), ("referencia", TINTA2, "Referência (sistema)"),
                              ("controle", LARANJA, "Controle (F63.1–F63.3)")):
            s = df[col].cast(pl.Float64)
            ax.plot(x, (s / s.filter(df["cmp"].str.starts_with("2018")).mean()).rolling_mean(3, center=True, min_samples=1), color=cor, lw=1.8, label=rot)
    axs[0].set_ylabel("Registros mensais / média de 2018\n(escala log; média móvel de 3 meses)")
    h, l_ = axs[0].get_legend_handles_labels()
    fig.legend(h, l_, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    salvar(fig, "figura_s1_volume")

    # Figura 2: taxa por 10 mil registros de referência com o ajuste joinpoint e a quebra final (IC bootstrap)
    fig, axs = plt.subplots(1, 2, figsize=(6.7, 3.2))
    for ax, (f, tit) in zip(axs, paineis):
        aj = A[f"{f}_jogo_ref"]
        x = [d(m) for m in aj.meses]
        eixo_tempo(ax, tit)
        for nome, cor, rot, mk in ((f"{f}_jogo_ref", AZUL, "Jogo patológico (F63.0)", "o"),
                                   (f"{f}_controle_ref", LARANJA, "Controle (F63.1–F63.3)", "o")):
            b = A[nome]
            ax.scatter(x, 1e4 * b.y / np.exp(b.off), s=9, color=cor, alpha=0.45, lw=0, marker=mk, zorder=2)
            lo_b, hi_b = banda(b)
            ax.fill_between(x, 1e4 * np.exp(lo_b), 1e4 * np.exp(hi_b), color=cor, alpha=0.18, lw=0, zorder=2)
            ax.plot(x, 1e4 * np.exp(tendencia(b)), color=cor, lw=2, zorder=3, label=rot)
        lo, hi = ic_quebra(aj)
        ax.axvspan(d(lo), d(hi), color=AZUL, alpha=0.10, lw=0)
        ax.axvline(d(mes_mais(aj.meses[0], aj.taus[-1])), color=AZUL, lw=1.0, ls="--")
        top = ax.get_ylim()[1]
        for i, (m, rot) in enumerate(MARCOS.items()):
            ax.axvline(d(m), color=TINTA2, lw=0.6, ls=":", zorder=1)
            ax.text(d(m), top / (1.0 if i % 2 == 0 else 1.45), " " + rot, fontsize=6, color=TINTA2, va="top",
                    bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.6, "alpha": 0.85})
    axs[0].set_ylabel("Registros por 10 mil registros de referência\n(escala log)")
    h, l_ = axs[0].get_legend_handles_labels()
    fig.legend(h, l_, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    salvar(fig, "figura1_tendencia")

    # Figura 3: floresta da robustez
    fig, ax = plt.subplots(figsize=(6.7, 6.6))
    y, ticks, labels = 0, [], []
    for m in ("aps_jogo_ref", "caps_jogo_ref", "aps_jogo_controle", "caps_jogo_controle"):
        ax.text(-0.01, y + 0.2, ROTULO[m], transform=ax.get_yaxis_transform(), ha="right", fontweight="bold", color=TINTA)
        y -= 1
        for r in sens.filter(pl.col("modelo") == m).iter_rows(named=True):
            p = r["cenario"] == "principal"
            cor = AZUL if p else TINTA2
            if p:
                ax.plot([r["li"], r["ls"]], [y, y], color=cor, lw=1.5)
            ax.plot(r["vpa"], y, "o", color=cor, ms=5 if p else 3.5)
            ticks.append(y)
            labels.append(f"{r['cenario']}  [{fmt_mes(r['quebra_final'])}]" if r["quebra_final"] else r["cenario"])
            y -= 1
        y -= 0.6
    ax.set_yticks(ticks, labels, fontsize=7)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Variação percentual anual no segmento final (análise principal com IC95% bootstrap)")
    ax.set_xlim(left=0)
    fig.tight_layout()
    salvar(fig, "figura_s2_robustez")

    # Figura 4: % de mulheres por ano (sem IC: registros do mesmo paciente não são independentes)
    fig, axs = plt.subplots(1, 2, figsize=(6.7, 2.9), sharey=True)
    for ax, (f, tit) in zip(axs, paineis):
        an = (S[f].with_columns(ano=pl.col("cmp").str.slice(0, 4).cast(pl.Int32)).group_by("ano")
              .agg(pl.col("jogo_F", "jogo_M", "referencia_F", "referencia_M").sum()).sort("ano"))
        for gr, cor, rot, mk in (("jogo", AZUL, "Jogo patológico (F63.0)", "o"), ("referencia", TINTA2, "Referência", "o")):
            fe, ma = an[f"{gr}_F"].to_numpy(), an[f"{gr}_M"].to_numpy()
            ax.plot(an["ano"].to_numpy(), 100 * fe / (fe + ma), color=cor, marker=mk, ms=4, lw=1.5, label=rot)
        ax.set_title(tit, loc="left", fontsize=9, color=TINTA, fontweight="bold")
        ax.set_ylim(0, 100)
        ax.set_xticks(an["ano"].to_list(), [str(k) for k in an["ano"].to_list()], fontsize=7)
    axs[0].set_ylabel("% de registros em mulheres")
    h, l_ = axs[0].get_legend_handles_labels()
    fig.legend(h, l_, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    salvar(fig, "figura_s3_mulheres")

    # Figura 5: perfil por sexo e faixa etária em 2025 (barras = jogo; traços = referência)
    fig, axs = plt.subplots(1, 2, figsize=(6.7, 3.0), sharey=True)
    faixas = [f[2] for f in FAIXAS]
    yy = np.arange(len(faixas))
    lim = 0
    for ax, (rede, tit) in zip(axs, (("APS", "A. Atenção primária (atendimentos)"), ("CAPS", "B. CAPS (registros de RAAS)"))):
        for sx, sinal in (("F", -1), ("M", 1)):
            p = perfil.filter(pl.col("sexo") == sx)
            p = p.join(pl.DataFrame({"faixa": faixas}), on="faixa", how="right")
            jg, rf = p[f"{rede} F63.0 %"].to_numpy(), p[f"{rede} referência %"].to_numpy()
            ax.barh(yy, sinal * jg, color=AZUL, height=0.7, label="Jogo patológico (F63.0)" if sx == "F" else None)
            ax.scatter(sinal * rf, yy, marker="|", s=180, color=TINTA, lw=1.6, zorder=3,
                       label="Referência (sistema)" if sx == "F" else None)
            lim = max(lim, np.nanmax(jg), np.nanmax(rf))
        ax.axvline(0, color=TINTA2, lw=0.6)
        ax.set_title(tit, loc="left", fontsize=9, color=TINTA, fontweight="bold", pad=14)
        ax.text(0.25, 1.0, "Mulheres", transform=ax.transAxes, ha="center", va="bottom", fontsize=7, color=TINTA2)
        ax.text(0.75, 1.0, "Homens", transform=ax.transAxes, ha="center", va="bottom", fontsize=7, color=TINTA2)
        ax.grid(axis="y", visible=False)
    for ax in axs:
        ax.set_xlim(-1.1 * lim, 1.1 * lim)
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda val, _: f"{abs(val):g}"))
        ax.set_xlabel("% dos registros do grupo, 2025")
    axs[0].set_yticks(yy, [f.replace("-", "–") for f in faixas])
    axs[0].set_ylabel("Faixa etária (anos)")
    h, l_ = axs[0].get_legend_handles_labels()
    ordem = sorted(range(len(l_)), key=lambda i: not l_[i].startswith("Jogo"))
    fig.legend([h[i] for i in ordem], [l_[i] for i in ordem], loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.08, 1, 0.97))
    salvar(fig, "figura2_perfil")

