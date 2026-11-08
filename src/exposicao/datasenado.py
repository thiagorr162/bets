"""DataSenado, Panorama Político 2024 (coleta 5–28/jun/2024, ~21.800 entrevistas): por UF,
% que gastou com bets nos últimos 30 dias (Tabela 15 do Anexo 2) e % com dívidas em atraso
há mais de 90 dias (Tabela 8 do Anexo 2), com margens de erro.

Os números são extraídos do PDF oficial (não há microdados abertos).

uv run python -m src.exposicao.datasenado
"""

import re

import polars as pl
from pypdf import PdfReader

from src.config import pasta
from src.exposicao.google_trends import NOME_UF
from src.utils import baixar, salvar

URL = "https://www12.senado.leg.br/noticias/arquivos/2024/09/30/relatorio_apostasesportivas-golpesdigitais-endividamento-1.pdf"
LINHA = re.compile(r"^\s*(?P<nome>[A-Za-zÀ-ú ]+?)\s+(?P<est>\d+)%\s+±(?P<me>\d+,\d)%\s+[\d\.]+\s*$")


def extrair(paginas: list[str], titulo: str) -> pl.DataFrame:
    """Lê as linhas 'UF  xx%  ±y,y%  pop' de todas as páginas cujo texto contém `titulo`."""
    rows = []
    for t in paginas:
        if titulo not in t:
            continue
        bloco = t.split(titulo, 1)[1].split("Fonte:", 1)[0]
        for linha in bloco.splitlines():
            m = LINHA.match(linha)
            if m and m["nome"].strip() in NOME_UF:
                rows.append({"uf": NOME_UF[m["nome"].strip()], "pct": float(m["est"]),
                             "margem": float(m["me"].replace(",", "."))})
    df = pl.DataFrame(rows).unique("uf")
    assert df.height == 27, f"{titulo}: {df.height} UFs extraídas (esperado 27)"
    return df


def main():
    pdf = baixar(URL, pasta("exposicao", "raw") / "panorama_politico_2024_apostas.pdf")
    paginas = [p.extract_text() or "" for p in PdfReader(pdf).pages]
    apostou = extrair(paginas, 'Tabela 15: "Distribuição da população que, nos últimos 30 dias, gastou em apostas')
    divida = extrair(paginas, 'Tabela 8: "Distribuição da população que possui dívidas em atraso há mais de 90')
    out = apostou.rename({"pct": "pct_apostou", "margem": "me_apostou"}).join(
        divida.rename({"pct": "pct_divida90", "margem": "me_divida90"}), on="uf"
    ).sort("uf")
    salvar(out, pasta("exposicao") / "datasenado_uf_2024.parquet")


if __name__ == "__main__":
    main()
