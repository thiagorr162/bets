"""Atenção primária (SISAB/e-SUS APS): atendimentos individuais por diagnóstico, mês, sexo e faixa etária.

Fonte: relatório público de produção do SISAB (https://sisab.saude.gov.br, "Saúde > Produção"), consultado por
formulário. Linha = competência (mês); coluna = CIAP/CID; tipo de produção = atendimento individual.

- Conta ATENDIMENTOS com o problema/condição registrado, não pessoas distintas (o relatório não identifica pacientes).
- O SISAB aceita no máximo 12 meses por consulta; cada consulta leva ~30 s.
- Cobertura: o e-SUS foi implantado aos poucos; os anos iniciais têm bem menos registros (usar proporções).
- Toda resposta é guardada em data/raw/sisab/ (tabela em CSV) e reaproveitada: consulta já feita não é repetida.

uv run python -m src.saude_mental.sisab_aps
"""

import argparse
import csv
import html
import re
import time

import polars as pl
import requests

from src.config import PROCESSED, RAW

URL = "https://sisab.saude.gov.br/paginas/acessoRestrito/relatorio/federal/saude/RelSauProducao.xhtml"
PASTA = RAW / "sisab"
# sufixo -1 = CID-10; -4 = CIAP-2 (formato do formulário do SISAB)
CODIGOS = {
    "F32-1": "depressao_cid", "F33-1": "depressao_rec_cid", "F41-1": "ansiedade_cid", "F43-1": "estresse_cid",
    "F10-1": "alcool_cid", "F20-1": "esquizofrenia_cid", "F630-1": "jogo_cid",
    "P76-4": "depressao_ciap", "P74-4": "ansiedade_ciap", "P01-4": "sensacao_ansiedade_ciap", "P03-4": "tristeza_ciap",
    "P77-4": "suicidio_tentativa_ciap", "P15-4": "alcool_ciap", "P19-4": "drogas_ciap", "P72-4": "esquizofrenia_ciap",
}
FAIXAS = {"0-17": (0, 17), "18-24": (18, 24), "25-34": (25, 34), "35-44": (35, 44), "45-59": (45, 59), "60+": (60, 130)}


def recortes():
    yield "total", []
    for sx, v in [("M", "0"), ("F", "1")]:
        yield f"sexo={sx}", [("sexo", v)]
    for fx, (a, b) in FAIXAS.items():
        yield f"faixa={fx}", [("tpIdade", "ano"), ("idadeInicio", str(a)), ("idadeFim", str(b))]


def consultar(comps: list[str], extra: list, tentativas: int = 4) -> list[list[str]]:
    for i in range(tentativas):
        try:
            s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"
            g = s.get(URL, timeout=120).text
            vs = re.search(r'name="javax.faces.ViewState"[^>]*value="([^"]+)"', g).group(1)
            act = re.search(r'<form id="j_idt44"[^>]*action="([^"]+)"', g).group(1)
            base = [("j_idt44", "j_idt44"), ("lsCid", ",".join(CODIGOS) + ","), ("unidGeo", "brasil"),
                    ("selectLinha", "NU_COMPETENCIA"), ("selectcoluna", "CID"), ("tpProducao", "4"),
                    ("javax.faces.ViewState", vs), ("verTela", "Ver em tela")]
            if not any(k == "tpIdade" for k, _ in extra):
                base.append(("tpIdade", ""))
            r = s.post("https://sisab.saude.gov.br" + act, data=base + extra + [("j_idt76", c) for c in comps], timeout=600)
            tabs = [x for x in re.findall(r"<table.*?</table>", r.text, re.S) if "Competência" in x and "cid-" not in x]
            if not tabs:
                return []
            return [[html.unescape(re.sub(r"<[^>]+>|\s+", " ", c)).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", l, re.S)]
                    for l in re.findall(r"<tr.*?</tr>", tabs[0], re.S)]
        except (requests.RequestException, AttributeError):
            time.sleep(10 * (i + 1))
    raise RuntimeError("SISAB não respondeu")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--inicio", type=int, default=2018)
    a.add_argument("--fim", default="202609")
    x = a.parse_args()
    PASTA.mkdir(parents=True, exist_ok=True)
    anos = range(x.inicio, int(x.fim[:4]) + 1)
    for nome, extra in recortes():
        for ano in anos:
            arq = PASTA / f"{nome.replace('=', '_')}_{ano}.csv"
            if arq.exists():
                continue
            comps = [f"{ano}{m:02d}" for m in range(1, 13) if f"{ano}{m:02d}" <= x.fim]
            t0 = time.time()
            linhas = consultar(comps, extra)
            with open(arq, "w", newline="") as f:
                csv.writer(f).writerows(linhas)
            print(f"  {nome} {ano}: {max(len(linhas) - 1, 0)} meses ({time.time() - t0:.0f} s)", flush=True)

    # junta tudo em formato longo: cmp, recorte, código, atendimentos
    linhas = []
    for arq in sorted(PASTA.glob("*.csv")):
        nome = arq.stem.rsplit("_", 1)[0]
        tipo, _, valor = nome.partition("_")
        rows = list(csv.reader(open(arq)))
        if len(rows) < 2:
            continue
        cab = rows[0][1:]
        cods = []
        for c in cab:
            m = re.match(r"(CID|CIAP) \(([A-Z0-9]+)\)", c)
            cods.append(f"{m.group(2)}-{'1' if m.group(1) == 'CID' else '4'}" if m else c)
        for r in rows[1:]:
            for cod, v in zip(cods, r[1:]):
                linhas.append({"cmp": r[0], "recorte": tipo, "valor": valor or "total", "codigo": cod,
                               "grupo": CODIGOS.get(cod, cod), "atendimentos": int(v.replace(".", "") or 0)})
    df = pl.DataFrame(linhas).sort("recorte", "valor", "grupo", "cmp")
    df.write_parquet(PROCESSED / "sisab_aps.parquet")
    print(f"✓ data/processed/sisab_aps.parquet ({df.height:,} linhas)")


if __name__ == "__main__":
    main()
