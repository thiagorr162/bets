"""1. Dados: séries mensais da APS (SISAB) e dos CAPS (RAAS do SIA-PS, agregadas a partir dos .dbc), perfil e conduta.

Só dados públicos agregados: das RAAS são lidas sete colunas, nenhuma identifica o paciente."""

import re
import struct
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import polars as pl
from comum import (
    CIAP_SISAB,
    CONTROLE_CID,
    CONTROLE_SISAB,
    DBC,
    FIM_APS,
    FIM_CAPS,
    FTP,
    INESPEC_CID,
    INICIO,
    POP,
    RAAS,
    RAAS_CNES,
    REF_CID,
    REF_SISAB,
    SISAB,
    SISAB_CONDUTA,
    UFS,
)

# %% 1. Dados ------------------------------------------------------------------------------------------------------
# 1a. CAPS: contagem de linhas de RAAS (cada linha = um procedimento registrado, datado por DT_ATEND) a partir dos
# .dbc do SIA-PS. O .dbf tem registros de largura fixa e só os
# bytes das colunas abaixo são lidos: CNS_PAC (cartão SUS) e DTNASC nunca saem do arquivo.
COLS = ["CNES_EXEC", "DT_ATEND", "SEXOPAC", "IDADEPAC", "TPIDADEPAC", "CIDPRI", "DT_INICIO"]
FAIXAS = [(0, 17, "0-17"), (18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"), (45, 59, "45-59"), (60, 999, "60+")]


def faixa_etaria() -> pl.Expr:
    """TPIDADEPAC 4 = idade em anos, 5 = 100 anos ou mais; os outros tipos (dias, meses) são crianças pequenas."""
    idade = (pl.when(pl.col("TPIDADEPAC") == "4").then(pl.col("IDADEPAC").cast(pl.Int32, strict=False))
             .when(pl.col("TPIDADEPAC") == "5").then(pl.lit(100)).otherwise(pl.lit(0)))
    e = pl.lit(None, dtype=pl.String)
    for lo, hi, rot in reversed(FAIXAS):
        e = pl.when(idade.is_between(lo, hi)).then(pl.lit(rot)).otherwise(e)
    return e


def ler_colunas(dbf: Path, cols: list[str]) -> pl.DataFrame:
    b = np.fromfile(dbf, dtype=np.uint8)
    n, hl, rl = struct.unpack("<IHH", b[4:12].tobytes())
    campos, pos = {}, 1  # byte 0 de cada registro = marca de exclusão
    for i in range(32, hl - 1, 32):
        nome = b[i:i + 11].tobytes().split(b"\0")[0].decode().strip()
        campos[nome] = (pos, int(b[i + 16]))
        pos += int(b[i + 16])
    reg = b[hl:hl + n * rl].reshape(n, rl)
    reg = reg[reg[:, 0] != ord("*")]
    return pl.DataFrame({c: pl.Series(c, np.ascontiguousarray(reg[:, o:o + ln]).view(f"S{ln}").ravel()
                                      .astype(f"U{ln}")).str.strip_chars() for c, (o, ln) in
                         ((c, campos[c]) for c in cols)})


def baixar(nome: str):
    DBC.mkdir(parents=True, exist_ok=True)
    tmp = DBC / f"{nome}.part"
    for i in range(4):
        try:
            with urlopen(f"{FTP}/{nome}", timeout=90) as r, open(tmp, "wb") as f:
                while bloco := r.read(1 << 20):
                    f.write(bloco)
            tmp.rename(DBC / nome)
            return
        except OSError:
            tmp.unlink(missing_ok=True)
            if i == 3:
                raise
            time.sleep(5 * (i + 1))


def raas_arquivo(nome: str):
    """Um .dbc (UF × competência) -> (registros por mês × CID × sexo × faixa etária × aberta-no-mês, registros por
    mês × CAPS)."""
    from pyreaddbc import dbc2dbf

    if not (DBC / nome).exists():
        baixar(nome)
    with tempfile.TemporaryDirectory() as tmp:
        dbf = Path(tmp) / "a.dbf"
        dbc2dbf(str(DBC / nome), str(dbf))
        df = ler_colunas(dbf, COLS)
    c = pl.col("CIDPRI")
    df = df.with_columns(pl.col("DT_ATEND").str.slice(0, 6).alias("cmp"),
                         pl.when(c.str.starts_with("F63")).then(c).when(c.str.starts_with("F")).then(c.str.slice(0, 3))
                         .otherwise(pl.lit("outro")).alias("cid"))
    por_cid = df.group_by("cmp", "cid", pl.col("SEXOPAC").alias("sexo"), faixa_etaria().alias("faixa"),
                          (pl.col("DT_INICIO").str.slice(0, 6) == pl.col("cmp")).alias("inicio")).agg(
        pl.len().alias("registros"))
    por_cnes = pl.concat([df.filter(f).group_by("cmp", pl.col("CNES_EXEC").alias("cnes"))
                          .agg(pl.len().alias("registros")).with_columns(pl.lit(g).alias("grupo"))
                          for g, f in (("jogo", pl.col("cid") == "F630"), ("total", pl.lit(True)))])
    return por_cid, por_cnes


def refazer_caps(processos: int):
    try:
        with urlopen(FTP + "/", timeout=120) as r:
            nomes = [ln.split()[-1] for ln in r.read().decode("latin1").splitlines() if ln.strip()]
    except OSError:
        nomes = [p.name for p in DBC.glob("PS*.dbc")]
    nomes = sorted(n for n in nomes if re.fullmatch(r"PS[A-Z]{2}\d{4}\.dbc", n) and n[2:4] in UFS
                   and "20" + n[4:8] >= INICIO)
    print(f"RAAS: {len(nomes)} arquivos")
    cid, cnes = [], []
    with ProcessPoolExecutor(processos, mp_context=get_context("spawn")) as ex:
        fut = {ex.submit(raas_arquivo, n): n for n in nomes}
        for i, f in enumerate(as_completed(fut), 1):
            try:
                a, b = f.result()
                cid.append(a)
                cnes.append(b)
            except Exception as e:
                print(f"  ! {fut[f]}: {e}")
            if i % 200 == 0:
                print(f"  {i}/{len(nomes)}")
    RAAS.parent.mkdir(parents=True, exist_ok=True)
    pl.concat(cid, how="vertical_relaxed").write_parquet(RAAS)
    pl.concat(cnes, how="vertical_relaxed").write_parquet(RAAS_CNES)


# 1b. Séries mensais nacionais
def entre(df, fim):
    return df.filter(pl.col("cmp").is_between(pl.lit(INICIO), pl.lit(fim)))


def serie_aps() -> pl.DataFrame:
    d = entre(pl.read_parquet(SISAB), FIM_APS)

    def largo(recorte, valor=None):
        x = d.filter(pl.col("recorte") == recorte)
        x = x if valor is None else x.filter(pl.col("valor") == valor)
        return x.pivot(on="grupo", index="cmp", values="atendimentos", aggregate_function="sum")

    t = largo("total").select("cmp", jogo=pl.col("jogo_cid"), referencia=pl.sum_horizontal(REF_SISAB),
                              controle=pl.sum_horizontal(CONTROLE_SISAB), trico=pl.col("tricotilomania_cid"),
                              ref_ampla=pl.sum_horizontal(REF_SISAB + CIAP_SISAB))
    for s in "FM":  # os recortes por sexo do SISAB não trazem F63.1–F63.3
        t = t.join(largo("sexo", s).select("cmp", pl.col("jogo_cid").alias(f"jogo_{s}"),
                                           pl.sum_horizontal(REF_SISAB).alias(f"referencia_{s}")), on="cmp")
    return t.fill_null(0).sort("cmp")


def serie_caps() -> pl.DataFrame:
    d = entre(pl.read_parquet(RAAS), FIM_CAPS)
    cid, sx, r, ini = pl.col("cid"), pl.col("sexo"), pl.col("registros"), pl.col("inicio")
    jogo, ref = cid == "F630", cid.is_in(REF_CID)
    t = d.group_by("cmp").agg(
        jogo=r.filter(jogo).sum(), controle=r.filter(cid.is_in(CONTROLE_CID)).sum(), trico=r.filter(cid == "F633").sum(),
        inespec=r.filter(cid.is_in(INESPEC_CID)).sum(),
        referencia=r.filter(ref).sum(), mental=r.filter(cid != "outro").sum(), total=r.sum(),
        jogo_inicio=r.filter(jogo & ini).sum(), referencia_inicio=r.filter(ref & ini).sum(),
        jogo_F=r.filter(jogo & (sx == "F")).sum(), jogo_M=r.filter(jogo & (sx == "M")).sum(),
        referencia_F=r.filter(ref & (sx == "F")).sum(), referencia_M=r.filter(ref & (sx == "M")).sum())
    c = entre(pl.read_parquet(RAAS_CNES), FIM_CAPS).filter(pl.col("grupo") == "jogo")
    c = c.group_by("cmp", "cnes").agg(r.sum()).group_by("cmp").agg(jogo_cap10=r.clip(0, 10).sum())
    return t.join(c, on="cmp", how="left").fill_null(0).sort("cmp")


def populacao() -> pl.DataFrame:
    """Brasil por ano; 2022–2023 (sem estimativa, ano do censo) interpolados; anos após o último repetem o último."""
    p = pl.read_parquet(POP).group_by("ano").agg(pl.col("populacao").sum())
    anos = pl.DataFrame({"ano": list(range(2018, 2027))}, schema={"ano": pl.Int32})
    return (anos.join(p.with_columns(pl.col("ano").cast(pl.Int32)), on="ano", how="left").sort("ano")
            .with_columns(pl.col("populacao").cast(pl.Float64).interpolate().forward_fill()))


def perfil_2025() -> pl.DataFrame:
    """% dos registros de jogo e da referência por sexo × faixa etária em 2025, na APS e nos CAPS."""
    a = pl.read_parquet(SISAB).filter((pl.col("recorte") == "sexofaixa") & pl.col("cmp").str.starts_with("2025"))
    a = (a.with_columns(pl.col("valor").str.split_exact("_", 1).struct.rename_fields(["sexo", "faixa"]).alias("sf"))
         .unnest("sf").with_columns(g=pl.when(pl.col("grupo") == "jogo_cid").then(pl.lit("jogo"))
                                    .when(pl.col("grupo").is_in(REF_SISAB)).then(pl.lit("ref")))
         .filter(pl.col("g").is_not_null()).group_by("g", "sexo", "faixa").agg(n=pl.col("atendimentos").sum()))
    c = pl.read_parquet(RAAS).filter(pl.col("cmp").str.starts_with("2025") & pl.col("sexo").is_in(["F", "M"])
                                     & pl.col("faixa").is_not_null())
    c = (c.with_columns(g=pl.when(pl.col("cid") == "F630").then(pl.lit("jogo"))
                        .when(pl.col("cid").is_in(REF_CID)).then(pl.lit("ref")))
         .filter(pl.col("g").is_not_null()).group_by("g", "sexo", "faixa").agg(n=pl.col("registros").sum()))
    grade = pl.DataFrame({"sexo": [s for s in "FM" for _ in FAIXAS], "faixa": [f[2] for _ in "FM" for f in FAIXAS]})
    for rede, d in (("APS", a), ("CAPS", c)):
        for g, rot in (("jogo", "F63.0"), ("ref", "referência")):
            x = d.filter(pl.col("g") == g).select("sexo", "faixa", pl.col("n").cast(pl.Float64))
            grade = grade.join(x.with_columns((100 * pl.col("n") / pl.col("n").sum()).alias(f"{rede} {rot} %"))
                               .drop("n"), on=["sexo", "faixa"], how="left")
    return grade.fill_null(0.0)


def conduta_aps() -> pl.DataFrame:
    """% dos atendimentos de cada diagnóstico com cada conduta, jan/2025 até o fim da série da APS. O denominador é o
    total de atendimentos do diagnóstico (relatório de produção); a conduta vem do relatório com a coluna Conduta."""
    c = pl.read_parquet(SISAB_CONDUTA).filter(pl.col("cmp").is_between(pl.lit("202501"), pl.lit(FIM_APS)))
    a = (pl.read_parquet(SISAB).filter((pl.col("recorte") == "total") & pl.col("cmp").is_between(pl.lit("202501"),
                                                                                               pl.lit(FIM_APS)))
         .group_by("grupo").agg(pl.col("atendimentos").sum()))
    cond = {"Alta do episódio": "alta", "Retorno para consulta agendada": "retorno",
            "Retorno p/ cuidado continuado/": "continuado", "Encaminhamento p/ serviço espe": "especializado",
            "Encaminhamento p/ CAPS": "caps"}
    linhas = []
    for g, rot in (("jogo_cid", "jogo"), ("ansiedade_cid", "ansiedade"), ("depressao_cid", "depressao"),
                   ("alcool_cid", "alcool")):
        n = a.filter(pl.col("grupo") == g)["atendimentos"].item()
        x = c.filter(pl.col("grupo") == g)
        linhas.append({"diagnóstico": rot, "atendimentos": n,
                       **{k: 100 * x.filter(pl.col("conduta") == nome)["n"].sum() / n for nome, k in cond.items()}})
    return pl.DataFrame(linhas)

