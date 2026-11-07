"""Caminhos e parâmetros compartilhados. Tudo absoluto, derivado da raiz do projeto."""

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"  # arquivos baixados como vieram
INTERIM = DATA / "interim"  # agregados por arquivo (permite retomar downloads)
PROCESSED = DATA / "processed"  # tabelas finais usadas no notebook

for _d in (RAW, INTERIM, PROCESSED):
    _d.mkdir(parents=True, exist_ok=True)

ANO_INICIO = 2018
HOJE = date.today()
ANO_FIM = HOJE.year

UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]

# Marcos regulatórios usados como choques nas análises
CHOQUES = {
    "2018-12-12": "Lei 13.756 (legaliza quota fixa)",
    "2023-12-29": "Lei 14.790 (regulação)",
    "2024-10-01": "Bloqueio de sites não autorizados",
    "2025-01-01": "Mercado regulado",
    "2026-09-25": "MP 1.394 (proibição)",
}


# Período atípico da Covid-19: de mar/2020 (primeiras restrições, ESPIN decretada em fev/2020)
# até dez/2021 (fim do Auxílio Emergencial em out/2021 + normalização do SUS eletivo).
# A ESPIN só terminou em 22/04/2022; PANDEMIA_LONGA serve para testes de robustez.
PANDEMIA = ("2020-03-01", "2021-12-31")
PANDEMIA_LONGA = ("2020-03-01", "2022-04-30")


def meses(inicio: str, fim: str | None = None) -> list[str]:
    """Lista de meses 'YYYYMM' de `inicio` até `fim` (padrão: mês corrente)."""
    a, m = int(inicio[:4]), int(inicio[4:])
    fim = fim or f"{HOJE.year}{HOJE.month:02d}"
    out = []
    while f"{a}{m:02d}" <= fim:
        out.append(f"{a}{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return out
