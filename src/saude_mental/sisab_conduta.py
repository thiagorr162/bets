"""Atenção primária (SISAB): conduta registrada nos atendimentos individuais, por diagnóstico e mês.

Conduta = o que o profissional fez ao fim do atendimento (alta, retorno agendado, encaminhamento para o CAPS, para
serviço especializado, para urgência etc.). Um atendimento pode ter mais de uma conduta, então as condutas somam mais
que o número de atendimentos.

- Uma consulta por diagnóstico e ano: com a coluna "Conduta", o relatório soma os diagnósticos pedidos, então cada
  diagnóstico é consultado sozinho.
- Respostas guardadas em data/atencao_primaria/raw/conduta/<grupo>_<ano>.csv e reaproveitadas.

uv run python -m src.saude_mental.sisab_conduta
"""

import argparse
import csv
import time

import polars as pl

from src.config import pasta
from src.saude_mental.sisab_aps import CODIGOS, consultar

GRUPOS = {k: v for k, v in CODIGOS.items() if k.endswith("-1")}  # CIDs: jogo e diagnósticos de referência
PASTA = pasta("atencao_primaria", "raw") / "conduta"


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--inicio", type=int, default=2018)
    a.add_argument("--fim", default="202609")
    x = a.parse_args()
    PASTA.mkdir(parents=True, exist_ok=True)
    for cod, grupo in GRUPOS.items():
        for ano in range(x.inicio, int(x.fim[:4]) + 1):
            arq = PASTA / f"{grupo}_{ano}.csv"
            if arq.exists():
                continue
            comps = [f"{ano}{m:02d}" for m in range(1, 13) if f"{ano}{m:02d}" <= x.fim]
            t0 = time.time()
            linhas = consultar(comps, [], {cod: grupo}, coluna="CDT")
            with open(arq, "w", newline="") as f:
                csv.writer(f).writerows(linhas)
            print(f"  {grupo} {ano}: {max(len(linhas) - 1, 0)} meses ({time.time() - t0:.0f} s)", flush=True)

    linhas = []
    for arq in sorted(PASTA.glob("*.csv")):
        grupo = arq.stem.rsplit("_", 1)[0]
        rows = list(csv.reader(open(arq)))
        if len(rows) < 2:
            continue
        for r in rows[1:]:
            for conduta, v in zip(rows[0][1:], r[1:]):
                linhas.append({"cmp": r[0], "grupo": grupo, "conduta": conduta, "n": int(v.replace(".", "") or 0)})
    df = pl.DataFrame(linhas).sort("grupo", "cmp", "conduta")
    df.write_parquet(pasta("atencao_primaria") / "sisab_conduta.parquet")
    print(f"✓ data/atencao_primaria/processed/sisab_conduta.parquet ({df.height:,} linhas)")


if __name__ == "__main__":
    main()
