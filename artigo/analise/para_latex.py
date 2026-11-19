"""Leva os resultados para o projeto LaTeX do artigo (artigo/latex/, que é o que sobe no Overleaf):

  - confere se as afirmações qualitativas do texto ("dobrou a cada ano", "mais de duas vezes"...) continuam valendo com
    os números atuais de resultados/numeros.json; se uma rodada nova mudar isso, o texto precisa ser revisto;
  - gera latex/tabelas/tabela{1,2,3}.tex a partir de numeros.json;
  - copia as figuras do artigo e do material suplementar (PDF) para latex/figuras/.

Roda sozinho no fim de rodar.py, ou à parte (só lê numeros.json e as figuras):

    uv run python artigo/analise/para_latex.py

Os números do texto (main.tex) estão digitados; as tabelas não: não edite tabelas/*.tex à mão, edite este arquivo.
"""

import json
import shutil
import sys

from comum import FIG, OUT, ROOT

LATEX = ROOT / "artigo" / "latex"
FIGURAS = {  # arquivo no LaTeX -> arquivo da análise
    "figura1": "figura1_tendencia",
    "figura2": "figura2_perfil",
    "figuraS1": "figura_s2_robustez",
    "figuraS2": "figura_s3_mulheres",
}
NUM: dict = {}


def n(chave) -> float:
    """Valor numérico de uma chave formatada em pt-BR (−1.234,5 -> -1234.5)."""
    return float(str(NUM[chave]).replace("−", "-").replace(".", "").replace(",", "."))


def conferir_afirmacoes():
    """O texto afirma coisas qualitativas sobre os números ('estável', 'dobrou a cada ano', 'mais de duas vezes'...). Se
    uma rodada nova da análise mudar isso, o texto precisa ser revisto: aqui a montagem para."""
    outros = ("ansiedade", "depressao", "alcool")
    ctrl = {r: [n(f"desc.{r}.{a}.taxa_ctrl") for a in range(2018, 2027) if NUM[f"desc.{r}.{a}.meses"] == 12]
            for r in ("aps", "caps")}
    rob_caps = n("rob.caps_jogo_ref.desfecho = F63.0 + F63, F63.8, F63.9")
    regras = [
        (NUM["aps_jogo_ref.k"] == 1 and NUM["caps_jogo_ref.k"] == 1, "o texto supõe uma mudança de tendência por rede"),
        (NUM["aps_ref_sis.k"] == 0, "Tabela 2 supõe referência da APS com um único segmento"),
        (NUM["caps_ref_sis.k"] == 2 and n("caps_ref_sis.s2") < 0, "nota da Tabela 2: queda da referência dos CAPS"),
        (NUM["caps.faltam"] == 1, "o texto fala de um arquivo faltante, no singular"),
        (n("aps_jogo_ref.s1_bli") < 0 < n("aps_jogo_ref.s1_bls"), "APS 'estável' antes da mudança"),
        (90 <= n("aps_jogo_ref.ult") <= 110, "APS 'dobrou a cada ano'"),
        (n("aps_jogo_ref.ult_bli") > 0 and n("caps_jogo_ref.ult_bli") > 0, "crescimento depois da mudança"),
        (18 <= n("lag.jogo_ref.est") <= 30, "CAPS 'cerca de dois anos depois'"),
        (n("caps_controle_ref.ult_bli") < 0 < n("caps_controle_ref.ult_bls"), "controle dos CAPS 'sem tendência definida'"),
        (all(max(v) / min(v) < 1.5 for v in ctrl.values()), "controle 'variou pouco' nos anos completos"),
        (rob_caps < n("rob.caps_jogo_ref.min"), "'a exceção foi' somar os F63 sem especificação"),
        (n("idade.inesp") > 2 * n("idade.f630"), "F63 sem especificação 'têm outro perfil'"),
        (n("cond.jogo.especializado") > 2 * max(n(f"cond.{g}.especializado") for g in outros), "'mais de duas vezes'"),
        (n("cond.ansiedade.especializado") <= n("cond.alcool.especializado") <= n("cond.depressao.especializado"),
         "faixa 'ansiedade a depressão' no encaminhamento especializado"),
        (n("cond.jogo.alta") < min(n(f"cond.{g}.alta") for g in outros), "jogo 'terminou menos vezes em alta'"),
        (n("cond.jogo.caps") < 5, "encaminhamento ao CAPS 'raro'"),
    ]
    erros = [msg for ok, msg in regras if not ok]
    if erros:
        sys.exit("Afirmações do texto que os números atuais não sustentam:\n  - " + "\n  - ".join(erros))


# ---------------------------------------------------------------------------------------------------------- tabelas
def tex(s) -> str:
    return str(s).replace("%", r"\%").replace("−", r"\textminus{}")


def tabela(rotulo, titulo, cab, linhas, colunas, nota):
    """Tabela no formato da CSP: Times 9 pt, até 17 cm, um dado por célula, sem células mescladas."""
    corpo = "\n".join(" & ".join(tex(c) for c in lin) + r" \\" for lin in linhas)
    return (f"% Gerado por artigo/analise/para_latex.py a partir de artigo/resultados/numeros.json. Não editar à mão.\n"
            "\\begin{table}[htbp]\n\\centering\n\\fontsize{9}{11}\\selectfont\n\\setlength{\\tabcolsep}{4pt}\n"
            f"\\caption{{{titulo}}}\n\\label{{tab:{rotulo}}}\n\\begin{{tabular}}{{{colunas}}}\n\\toprule\n"
            + " & ".join(cab) + r" \\ \midrule" + "\n" + corpo + "\n\\bottomrule\n\\end{tabular}\n"
            f"\\par\\smallskip\\parbox{{\\linewidth}}{{\\raggedright {nota}}}\n\\end{{table}}\n")


FONTES = ("Fontes: Sistema de Informação em Saúde para a Atenção Básica; Sistema de Informações Ambulatoriais do SUS, "
          "Registro das Ações Ambulatoriais de Saúde.")
SIGLAS = "APS: atenção primária à saúde; CAPS: Centros de Atenção Psicossocial"
REFERENCIA = "Referência: F32, F33, F41, F43, F10 e F20"


def tabela1():
    linhas = [[str(a)] + [NUM[f"desc.{r}.{a}.{k}"] for r in ("aps", "caps") for k in ("jogo", "taxa", "taxa_ctrl")]
              for a in range(2018, 2027)]
    cab = ["Ano", "APS: jogo patológico (n)", "APS: jogo por 10 mil da referência",
           "APS: controle por 10 mil da referência", "CAPS: jogo patológico (n)", "CAPS: jogo por 10 mil da referência",
           "CAPS: controle por 10 mil da referência"]
    nota = (f"{SIGLAS}. Jogo patológico: F63.0; controle negativo: F63.1--F63.3. {REFERENCIA}. Na APS, 2018 vai de "
            f"fevereiro a dezembro e 2026, de janeiro a {NUM['aps.fim'].split('/')[0]}; nos CAPS, 2026 vai de janeiro a "
            f"{NUM['caps.fim'].split('/')[0]}. Na APS, a unidade é o atendimento; nos CAPS, o procedimento registrado. "
            + FONTES)
    titulo = ("Registros de jogo patológico e taxas de jogo patológico e do controle negativo por 10 mil registros do "
              "grupo de referência, por ano, na atenção primária à saúde (APS) e nos Centros de Atenção Psicossocial "
              "(CAPS). Brasil, 2018--2026.")
    return tabela("tabela1", titulo, cab, linhas, "p{1.0cm}" + "R{2.3cm}" * 6, nota)


def tabela2():
    def lin(rot, b_a, b_c, chave, ic=("_bli", "_bls"), sep="; "):
        return [rot, NUM[f"{b_a}.{chave}"], NUM[f"{b_a}.{chave}{ic[0]}"] + sep + NUM[f"{b_a}.{chave}{ic[1]}"],
                NUM[f"{b_c}.{chave}"], NUM[f"{b_c}.{chave}{ic[0]}"] + sep + NUM[f"{b_c}.{chave}{ic[1]}"]]

    ap, cp = "aps_jogo_ref", "caps_jogo_ref"
    linhas = [
        lin("Jogo patológico: mês da mudança de tendência", ap, cp, "qult", ("_li", "_ls"), "--"),
        lin("Jogo patológico: VPA antes da mudança (%)", ap, cp, "s1"),
        lin("Jogo patológico: VPA depois da mudança (%)", ap, cp, "ult"),
        lin("Controle negativo: VPA do último segmento (%)", "aps_controle_ref", "caps_controle_ref", "ult"),
        lin("Registros da referência: VPA do último segmento (%)", "aps_ref_sis", "caps_ref_sis", "ult"),
    ]
    nota = (f"{SIGLAS}; IC95\\%: intervalo de 95\\% de confiança; VPA: variação percentual anual. Jogo patológico e "
            "controle negativo em taxa por 10 mil registros da referência; registros da referência em número absoluto "
            "(crescimento da rede). Regressão segmentada (\\emph{joinpoint}) binomial negativa, ajustada pelo mês do ano "
            f"e pela pandemia de COVID-19; IC95\\% por \\emph{{bootstrap}} de blocos de seis meses ({NUM['B']} réplicas). "
            f"Último segmento do controle negativo: desde {NUM['aps_controle_ref.qult']} na APS e desde "
            f"{NUM['caps_controle_ref.qult']} nos CAPS (IC95\\% do mês: {NUM['caps_controle_ref.qult_li']}--"
            f"{NUM['caps_controle_ref.qult_ls']}). Referência: sem mudança de tendência na APS; nos CAPS, queda de "
            f"{NUM['caps_ref_sis.s2_ini']} a {NUM['caps_ref_sis.s2_fim']} e crescimento desde então. Jogo patológico: "
            f"F63.0; controle negativo: F63.1--F63.3. {REFERENCIA}. APS: {NUM['aps.ini']} a {NUM['aps.fim']}; CAPS: "
            f"{NUM['caps.ini']} a {NUM['caps.fim']}. " + FONTES)
    titulo = ("Mudança de tendência e variação percentual anual das taxas de jogo patológico e do controle negativo e "
              "dos registros do grupo de referência na atenção primária à saúde (APS) e nos Centros de Atenção "
              "Psicossocial (CAPS). Brasil, 2018--2026.")
    return tabela("tabela2", titulo, ["Indicador", "APS", "IC95\\% (APS)", "CAPS", "IC95\\% (CAPS)"], linhas,
                  ">{\\raggedright\\arraybackslash}p{7.2cm}R{1.4cm}R{2.6cm}R{1.4cm}R{2.6cm}", nota)


def tabela3():
    rot = {"jogo": "Jogo patológico (F63.0)", "ansiedade": "Ansiedade (F41)", "depressao": "Depressão (F32)",
           "alcool": "Uso de álcool (F10)"}
    cols = ["atendimentos", "alta", "retorno", "continuado", "especializado", "caps"]
    linhas = [[rot[g]] + [NUM[f"cond.{g}.{c}"] for c in cols] for g in rot]
    cab = ["Diagnóstico", "Atendimentos (n)", "Alta do episódio (\\%)", "Retorno para consulta agendada (\\%)",
           "Retorno para cuidado continuado (\\%)", "Encaminhamento para serviço especializado (\\%)",
           "Encaminhamento para CAPS (\\%)"]
    nota = ("CAPS: Centro de Atenção Psicossocial. Um atendimento pode ter mais de uma conduta, e as linhas não somam "
            "100\\%. O registro não identifica o serviço especializado. Fonte: Sistema de Informação em Saúde para a "
            "Atenção Básica.")
    titulo = ("Conduta registrada ao fim dos atendimentos na atenção primária à saúde, por diagnóstico. Brasil, janeiro "
              f"de 2025 a {NUM['aps.fim']}.")
    return tabela("tabela3", titulo, cab, linhas, ">{\\raggedright\\arraybackslash}p{2.5cm}R{1.9cm}R{1.4cm}R{2.0cm}R{2.0cm}R{2.5cm}R{2.4cm}", nota)


def main():
    NUM.update(json.loads((OUT / "numeros.json").read_text(encoding="utf-8")))
    conferir_afirmacoes()
    (LATEX / "tabelas").mkdir(parents=True, exist_ok=True)
    (LATEX / "figuras").mkdir(parents=True, exist_ok=True)
    for i, f in enumerate((tabela1, tabela2, tabela3), 1):
        (LATEX / "tabelas" / f"tabela{i}.tex").write_text(f(), encoding="utf-8")
    for alvo, origem in FIGURAS.items():
        shutil.copy(FIG / f"{origem}.pdf", LATEX / "figuras" / f"{alvo}.pdf")
    print(f"✓ afirmações do texto conferidas; tabelas e figuras atualizadas em {LATEX}")


if __name__ == "__main__":
    main()
