"""Minimiza as tabelas de nível de paciente do F63 (LGPD: dado de saúde é sensível).

Roda automaticamente no fim de `src.saude_mental.sia_f63_pacientes`, mas pode ser chamado sozinho:
    uv run python -m src.saude_mental.minimizar_f63

O que faz:
- troca o CNS (já criptografado pelo DATASUS, mas estável e igual ao de outras bases do SUS) por um
  pseudônimo novo: HMAC-SHA256 com uma chave aleatória guardada só em data/.chave_pseudonimo.
  A ligação entre meses continua funcionando, mas o código deixa de bater com qualquer outra base;
- reduz a geografia de município para UF, a idade para faixa etária e a data de início para mês/ano;
- descarta as colunas que a análise não usa (estabelecimento, raça/cor, situação de rua, tipo de droga, origem);
- apaga os arquivos intermediários por paciente em data/caps/interim/ (o perfil agregado já está em data/caps/processed/).

Consequência: refazer a extração exige baixar tudo de novo do FTP (~40 min). É o preço da minimização.
"""

import hashlib
import hmac
import secrets
import shutil

import polars as pl

from src.config import DATA, pasta

CHAVE = DATA / ".chave_pseudonimo"


def chave() -> bytes:
    if not CHAVE.exists():
        CHAVE.write_text(secrets.token_hex(32))
        CHAVE.chmod(0o600)
    return bytes.fromhex(CHAVE.read_text().strip())


def pseudonimo(k: bytes) -> pl.Expr:
    return pl.col("CNS_PAC").map_elements(
        lambda c: hmac.new(k, c.encode("latin1", "replace"), hashlib.sha256).hexdigest()[:16], return_dtype=pl.String
    ).alias("id")


def main():
    k = chave()
    reg_p, hist_p = pasta("caps") / "sia_f63_registros.parquet", pasta("caps") / "sia_f63_historico.parquet"
    reg = pl.read_parquet(reg_p)
    if "CNS_PAC" not in reg.columns:
        print("registros já minimizados")
    else:
        reg = (reg.with_columns(pseudonimo(k), pl.col("MUNPAC").str.slice(0, 2).alias("cod_uf"),
                                pl.col("DT_INICIO").str.slice(0, 6).alias("inicio_cmp"))
               .group_by("id", "cmp", "cod_uf", "faixa", "SEXOPAC", "CIDPRI", "CIDASSOC")
               .agg(pl.col("inicio_cmp").min(), pl.col("n_proc").sum()))
        reg.write_parquet(reg_p)
        print(f"✓ registros minimizados: {reg.height:,} linhas, colunas {reg.columns}")

    hist = pl.read_parquet(hist_p)
    if "CNS_PAC" not in hist.columns:
        print("histórico já minimizado")
    else:
        hist = (hist.with_columns(pseudonimo(k), pl.col("DT_INICIO").str.slice(0, 6).alias("inicio_cmp"))
                .group_by("id", "cmp", "CIDPRI").agg(pl.col("inicio_cmp").min(), pl.col("n_proc").sum()))
        hist.write_parquet(hist_p)
        print(f"✓ histórico minimizado: {hist.height:,} linhas, colunas {hist.columns}")

    for p in (pasta("caps", "interim") / "sia_f63", pasta("caps", "interim") / "sia_f63_hist"):
        if p.exists():
            shutil.rmtree(p)
            print(f"✓ apagado {p.relative_to(DATA.parent)}")


if __name__ == "__main__":
    main()
