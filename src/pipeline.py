"""Roda todas as etapas da parte de saúde mental, em sequência (sempre a partir da raiz do projeto).

uv run python -m src.pipeline            # exposição (Trends, DataSenado, população): minutos
uv run python -m src.pipeline --pesado   # + DATASUS (CAPS, pacientes, trajetórias, internações e óbitos) e SISAB: ~2–3 h
"""

import argparse
import runpy
import sys

LEVES = [
    "src.exposicao.municipios",  # população por município (taxas por milhão)
    "src.exposicao.google_trends",  # busca por apostas por UF e mês
    "src.exposicao.datasenado",  # % que aposta por UF (jun/2024)
]
PESADAS = [
    "src.saude_mental.sia_caps",  # CAPS agregado por município
    "src.saude_mental.sia_f63_pacientes",  # pacientes com F63 (pseudonimizado no fim)
    "src.saude_mental.sia_trajetorias",  # todos os pacientes de saúde mental: pessoa × mês × grupo de CID
    "src.saude_mental.sisab_aps",  # atenção primária: atendimentos por CID, sexo e idade
    "src.saude_mental.sisab_conduta",  # atenção primária: conduta por CID
    "src.saude_mental.graves_f63",  # internações (SIH) e óbitos (SIM)
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pesado", action="store_true")
    a = p.parse_args()
    for mod in LEVES + (PESADAS if a.pesado else []):
        print(f"\n=== {mod} ===")
        sys.argv = [mod]
        try:
            runpy.run_module(mod, run_name="__main__")
        except Exception as e:
            print(f"!!! {mod} falhou: {e}")


if __name__ == "__main__":
    main()
