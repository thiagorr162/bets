"""Roda todas as etapas em sequência (sempre a partir da raiz do projeto).

uv run python -m src.pipeline            # etapas leves (APIs): minutos
uv run python -m src.pipeline --pesado   # + SCR, Bolsa Família e DATASUS: horas, dezenas de GB
"""

import argparse
import runpy
import sys

LEVES = [
    "src.exposicao.municipios",
    "src.endividamento.sgs_familias",
    "src.inadimplencia.sgs_inadimplencia",
    "src.consumo.pmc_pms",
    "src.exposicao.pix_municipio",
    "src.exposicao.google_trends",
]
PESADAS = [
    "src.inadimplencia.scr_uf",
    "src.exposicao.bolsa_familia",
    "src.saude_mental.sih_internacoes",
    "src.saude_mental.sia_caps",
    "src.saude_mental.sim_suicidio",
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
