"""SCR.data (BCB): carteira e inadimplência de PF por UF, ocupação, faixa de renda e modalidade.

Baixa planilha_{ano}.zip (~400 MB/ano), agrega cada mês e guarda em data/interim/scr/.

uv run python -m src.inadimplencia.scr_uf                # todos os anos
uv run python -m src.inadimplencia.scr_uf --anos 2024 2025
uv run python -m src.inadimplencia.scr_uf --apagar-zip   # remove o zip após agregar
"""

import argparse
import io
import zipfile

import polars as pl

from src.config import ANO_FIM, ANO_INICIO, INTERIM, PROCESSED, RAW
from src.utils import baixar, juntar, salvar

URL = "https://www.bcb.gov.br/pda/desig/planilha_{ano}.zip"
VALORES = [
    "vencido_acima_de_15_dias",
    "carteira_ativa",
    "carteira_inadimplida_arrastada",
    "ativo_problematico",
]
CHAVES = ["data_base", "uf", "ocupacao", "porte", "modalidade"]
PASTA = INTERIM / "scr"


def agregar_csv(raw: bytes) -> pl.DataFrame:
    df = pl.read_csv(
        io.BytesIO(raw),
        separator=";",
        infer_schema=False,
        encoding="utf8-lossy",
        columns=["data_base", "uf", "cliente", "ocupacao", "porte", "modalidade", "numero_de_operacoes", *VALORES],
    )
    num = lambda c: pl.col(c).str.replace_all(r"\.", "").str.replace(",", ".").cast(pl.Float64, strict=False)
    return (
        df.filter(pl.col("cliente") == "PF")
        .with_columns(
            pl.col("data_base").str.to_date("%Y-%m-%d"),
            pl.col("porte", "modalidade", "ocupacao").str.strip_chars(),
            # "<= 15" é suprimido por sigilo -> nulo
            pl.col("numero_de_operacoes").cast(pl.Int64, strict=False),
            *[num(c) for c in VALORES],
        )
        .group_by(CHAVES)
        .agg(pl.col("numero_de_operacoes", *VALORES).sum())
    )


def processar_ano(ano: int, apagar_zip: bool):
    zpath = baixar(URL.format(ano=ano), RAW / "scr" / f"planilha_{ano}.zip")
    with zipfile.ZipFile(zpath) as z:
        for nome in sorted(z.namelist()):
            destino = PASTA / nome.replace(".csv", ".parquet")
            if destino.exists():
                continue
            print(f"  agregando {nome}")
            salvar(agregar_csv(z.read(nome)), destino)
    if apagar_zip:
        zpath.unlink()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--anos", type=int, nargs="*", default=list(range(ANO_INICIO, ANO_FIM + 1)))
    p.add_argument("--apagar-zip", action="store_true")
    a = p.parse_args()
    for ano in a.anos:
        try:
            processar_ano(ano, a.apagar_zip)
        except Exception as e:  # ano corrente pode ainda não existir
            print(f"! {ano}: {e}")
    df = juntar(PASTA, PROCESSED / "scr_pf_uf.parquet")
    # versão enxuta: UF x mês
    uf = (
        df.group_by("data_base", "uf")
        .agg(pl.col(VALORES).sum())
        .with_columns((pl.col("carteira_inadimplida_arrastada") / pl.col("carteira_ativa") * 100).alias("inad_pct"))
        .sort("uf", "data_base")
    )
    salvar(uf, PROCESSED / "scr_pf_uf_mes.parquet")


if __name__ == "__main__":
    main()
