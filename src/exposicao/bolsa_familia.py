"""Pagamentos do Novo Bolsa Família por município (Portal da Transparência/CGU).

Cada mês é um zip de ~350 MB com uma linha por beneficiário; agregamos por município
(nº de beneficiários e valor) e apagamos o zip. O arquivo traz código SIAFI, não IBGE:
o casamento com IBGE é feito por nome+UF (rodar src.exposicao.municipios antes).

uv run python -m src.exposicao.bolsa_familia --meses 202408 202409 202608 202609
uv run python -m src.exposicao.bolsa_familia --inicio 202303   # série completa (pesado)
"""

import argparse
import io
import zipfile

import polars as pl

from src.config import INTERIM, PROCESSED, RAW, meses
from src.exposicao.municipios import normalizar
from src.utils import baixar, juntar, salvar

URL = "https://portaldatransparencia.gov.br/download-de-dados/novo-bolsa-familia/{m}"

# Grafias antigas/divergentes no cadastro SIAFI -> nome IBGE (normalizado). Conferido à mão.
ALIASES = {
    ("SP", "FLORINIA"): "FLORINEA",
    ("MG", "SAO THOME DAS LETRAS"): "SAO TOME DAS LETRAS",
    ("PE", "LAGOA DO ITAENGA"): "LAGOA DE ITAENGA",
    ("TO", "COUTO DE MAGALHAES"): "COUTO MAGALHAES",
    ("PE", "DISTRITO ESTADUAL DE FERNANDO DE NORONHA"): "FERNANDO DE NORONHA",
    ("PB", "SAO DOMINGOS DE POMBAL"): "SAO DOMINGOS",
    ("RN", "ACU"): "ASSU",
    ("PE", "BELEM DE SAO FRANCISCO"): "BELEM DO SAO FRANCISCO",
    ("RN", "ARES"): "AREZ",
    ("SE", "GRACHO CARDOSO"): "GRACCHO CARDOSO",
    ("PE", "IGUARACI"): "IGUARACY",
    ("TO", "FORTALEZA DO TABOCAO"): "TABOCAO",
    ("SP", "SAO LUIS DO PARAITINGA"): "SAO LUIZ DO PARAITINGA",
    ("BA", "MUQUEM DE SAO FRANCISCO"): "MUQUEM DO SAO FRANCISCO",
    ("PA", "ELDORADO DOS CARAJAS"): "ELDORADO DO CARAJAS",
    ("MT", "POXOREO"): "POXOREU",
    ("MG", "DONA EUSEBIA"): "DONA EUZEBIA",
    ("SE", "AMPARO DE SAO FRANCISCO"): "AMPARO DO SAO FRANCISCO",
    ("MG", "BARAO DE MONTE ALTO"): "BARAO DO MONTE ALTO",
    ("SP", "EMBU"): "EMBU DAS ARTES",
    ("BA", "SANTA TERESINHA"): "SANTA TEREZINHA",
    ("MT", "SANTO ANTONIO DO LEVERGER"): "SANTO ANTONIO DE LEVERGER",
    ("PB", "SERIDO"): "SAO VICENTE DO SERIDO",
    ("RJ", "PARATI"): "PARATY",
    ("MG", "BRASOPOLIS"): "BRAZOPOLIS",
    ("TO", "SAO VALERIO DA NATIVIDADE"): "SAO VALERIO",
    ("RR", "SAO LUIZ"): "SAO LUIZ DO ANAUA",
    ("PA", "SANTA ISABEL DO PARA"): "SANTA IZABEL DO PARA",
    ("RJ", "TRAJANO DE MORAIS"): "TRAJANO DE MORAES",
    ("CE", "ITAPAGE"): "ITAPAJE",
}
PASTA = INTERIM / "bolsa_familia"


def processar(m: str, manter_zip: bool):
    destino = PASTA / f"{m}.parquet"
    if destino.exists():
        return
    zpath = baixar(URL.format(m=m), RAW / "bolsa_familia" / f"{m}.zip")
    csv = RAW / "bolsa_familia" / f"{m}.utf8.csv"
    # o CSV vem em latin1 e tem ~20 mi linhas: transcodifica em streaming e lê lazy
    with zipfile.ZipFile(zpath) as z:
        nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(nome) as src, open(csv, "w", encoding="utf-8") as dst:
            for linha in io.TextIOWrapper(src, encoding="latin1"):
                dst.write(linha)
    lf = pl.scan_csv(csv, separator=";", infer_schema=False)
    cols = lf.collect_schema().names()
    pick = lambda f: next(c for c in cols if f(normalizar(c)))
    valor = pick(lambda c: c.startswith("VALOR"))
    mun = pick(lambda c: c.startswith("NOME MUNICIPIO"))
    siafi = pick(lambda c: "SIAFI" in c)
    uf = pick(lambda c: c == "UF")
    agg = (
        lf.select(
            pl.col(siafi).alias("cod_siafi"),
            pl.col(uf).alias("uf"),
            pl.col(mun).alias("municipio"),
            pl.col(valor).str.replace_all(r"\.", "").str.replace(",", ".").cast(pl.Float64).alias("valor"),
        )
        .group_by("cod_siafi", "uf", "municipio")
        .agg(pl.len().alias("beneficiarios"), pl.col("valor").sum().alias("valor_pbf"))
        .with_columns(pl.lit(m).alias("anomes"))
        .collect()
    )
    salvar(agg, destino)
    csv.unlink()
    if not manter_zip:
        zpath.unlink()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--meses", nargs="*")
    p.add_argument("--inicio")
    p.add_argument("--manter-zip", action="store_true")
    a = p.parse_args()
    lista = a.meses or (meses(a.inicio) if a.inicio else ["202408"])
    for m in lista:
        try:
            processar(m, a.manter_zip)
        except Exception as e:
            print(f"! {m}: {e}")

    df = juntar(PASTA, INTERIM / "bolsa_familia_todos.parquet")
    mun = pl.read_parquet(PROCESSED / "municipios.parquet")
    df = df.with_columns(
        pl.col("municipio")
        .map_elements(normalizar, return_dtype=pl.String)
        .str.replace(r"\s*\(.*\)$", "")  # "SERRA CAIADA (EX PRESIDENTE JUSCELINO)"
        .alias("municipio_norm")
    ).with_columns(
        pl.struct("uf", "municipio_norm")
        .map_elements(lambda r: ALIASES.get((r["uf"], r["municipio_norm"]), r["municipio_norm"]), return_dtype=pl.String)
        .alias("municipio_norm")
    ).join(mun.select("cod_ibge", "uf", "municipio_norm"), on=["uf", "municipio_norm"], how="left")
    sem = df.filter(pl.col("cod_ibge").is_null()).select("uf", "municipio").unique()
    if sem.height:
        print(f"! {sem.height} municípios sem código IBGE (ajustar nomes):\n{sem.head(20)}")
    salvar(df, PROCESSED / "bolsa_familia_municipio.parquet")


if __name__ == "__main__":
    main()
