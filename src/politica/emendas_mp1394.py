"""Emendas à MP 1.394/2026 (proibição das bets): autor, partido, UF e texto integral.

Fonte: dados abertos do Senado (as MPs tramitam no Congresso Nacional e as emendas ficam no sistema do Senado).
Cada emenda tem o texto num PDF; baixamos e extraímos o texto para classificar.

uv run python -m src.politica.emendas_mp1394
"""

import io
import re

import polars as pl
import requests
from pypdf import PdfReader

from src.config import PROCESSED, RAW
from src.utils import salvar

API = "https://legis.senado.leg.br/dadosabertos/processo/emenda"
ID_PROCESSO = 9110686  # MPV 1394/2026
PASTA = RAW / "congresso" / "mp1394"


def autoria(a: str) -> dict:
    # "Deputado Federal Beto Preto (PSD/PR)" / "Senador Alessandro Vieira (MDB/SE)"
    # partido pode vir vazio "(/RJ)" ou como "(S/Partido/RJ)": os dois viram "sem partido"
    m = re.match(r"(Deputad[oa] Federal|Senador[a]?)\s+(.+?)\s+\((.*)/([A-Z]{2})\)$", a.strip())
    if not m:
        return {"cargo": None, "parlamentar": a, "partido": None, "uf": None}
    cargo = "Deputado(a)" if m.group(1).startswith("Deputad") else "Senador(a)"
    partido = m.group(3) if m.group(3) and m.group(3) != "S/Partido" else "sem partido"
    return {"cargo": cargo, "parlamentar": m.group(2), "partido": partido, "uf": m.group(4)}


def texto_pdf(url: str, destino) -> str:
    if not destino.exists():
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        destino.write_bytes(r.content)
    pdf = PdfReader(io.BytesIO(destino.read_bytes()))
    return "\n".join((p.extract_text() or "") for p in pdf.pages)


def main():
    PASTA.mkdir(parents=True, exist_ok=True)
    emendas = requests.get(API, params={"idProcesso": ID_PROCESSO}, headers={"Accept": "application/json"}, timeout=120).json()
    linhas = []
    for e in sorted(emendas, key=lambda x: int(x["numero"])):
        n = int(e["numero"])
        texto = texto_pdf(e["urlDocumentoEmenda"], PASTA / f"emenda_{n:03d}.pdf")
        linhas.append({"numero": n, "data": e["dataApresentacao"], "autoria": e["autoria"], **autoria(e["autoria"]),
                       "tipo": e["tipo"], "url": e["urlDocumentoEmenda"], "texto": texto})
        print(f"  emenda {n} ✓ ({len(texto)} caracteres)")
    salvar(pl.DataFrame(linhas), PROCESSED / "mp1394_emendas.parquet")


if __name__ == "__main__":
    main()
