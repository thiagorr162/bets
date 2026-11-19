"""Configuração (caminhos, períodos, grupos de CID) e saída em texto, compartilhadas pelos outros módulos."""

import warnings
from pathlib import Path

import numpy as np
import polars as pl
import polars.selectors as cs

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OUT = ROOT / "artigo" / "resultados"
FIG = OUT / "figuras"
SISAB = DATA / "atencao_primaria/processed/sisab_aps.parquet"
SISAB_CONDUTA = DATA / "atencao_primaria/processed/sisab_conduta.parquet"
POP = DATA / "ibge/processed/populacao_municipio.parquet"
DBC = DATA / "caps/raw/datasus/SIASUS/200801_/Dados"
RAAS = DATA / "caps/processed/sia_raas.parquet"
RAAS_CNES = DATA / "caps/processed/sia_raas_cnes.parquet"
FTP = "ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados"

INICIO, FIM_APS, FIM_CAPS = "201801", "202609", "202606"  # RAAS chegam com atraso: jul–ago/2026 incompletos
# APS começa em fev/2018: jan/2018, 1º mês do SISAB, tem 34 registros de F63.0 contra 5–18 nos 11 meses seguintes
# (taxa 3× a maior do resto de 2018) e sozinho cria uma quebra espúria. A série completa entra na robustez.
INICIO_APS = "201802"
PANDEMIA = ("202003", "202112")
KMAX, MIN_SEG, BLOCO = 2, 12, 6  # máx. de quebras; meses mínimos por segmento; bloco do bootstrap (meses)

# Grupos (CID-10 principal)
REF_CID = ["F32", "F33", "F41", "F43", "F10", "F20"]  # referência: depressão, ansiedade, estresse, álcool, esquizofrenia
CONTROLE_CID = ["F631", "F632", "F633"]  # controle negativo: piromania, cleptomania, tricotilomania
INESPEC_CID = ["F63", "F638", "F639"]  # F63 sem especificação: podem conter jogo (só no CAPS; o SISAB não foi consultado)
REF_SISAB = ["depressao_cid", "depressao_rec_cid", "ansiedade_cid", "estresse_cid", "alcool_cid", "esquizofrenia_cid"]
CONTROLE_SISAB = ["piromania_cid", "cleptomania_cid", "tricotilomania_cid"]
CIAP_SISAB = ["depressao_ciap", "ansiedade_ciap", "sensacao_ansiedade_ciap", "tristeza_ciap", "alcool_ciap",
              "drogas_ciap", "esquizofrenia_ciap", "suicidio_tentativa_ciap"]
UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
       "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]

ROTULO = {
    "aps_jogo_ref": "APS · F63.0 / referência", "caps_jogo_ref": "CAPS · F63.0 / referência",
    "aps_controle_ref": "APS · F63.1–F63.3 / referência", "caps_controle_ref": "CAPS · F63.1–F63.3 / referência",
    "aps_jogo_controle": "APS · F63.0 vs F63.1–F63.3", "caps_jogo_controle": "CAPS · F63.0 vs F63.1–F63.3",
}


# %% Saída em texto
LINHAS: list[str] = []


def out(s=""):
    print(s, flush=True)
    LINHAS.append(str(s))


def secao(titulo):
    out("\n" + "=" * 100 + f"\n{titulo}\n" + "=" * 100)


def tabela(df: pl.DataFrame):
    df = df.with_columns(cs.float().map_elements(lambda x: num(x, 1), return_dtype=pl.String),
                         cs.integer().map_elements(lambda x: num(x) if abs(x) >= 1e4 else str(x),
                                                                 return_dtype=pl.String))
    with pl.Config(tbl_rows=-1, tbl_cols=-1, tbl_width_chars=200, fmt_str_lengths=60, tbl_hide_dataframe_shape=True,
                   tbl_hide_column_data_types=True, tbl_formatting="ASCII_MARKDOWN", float_precision=1):
        out(str(df))


MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def fmt_mes(m):
    return f"{MESES_PT[int(m[4:]) - 1]}/{m[:4]}"


def fmt_p(p):
    return "< 0,001" if p < 0.001 else f"{p:.3f}".replace(".", ",")


def num(x, nd=0):
    return f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".").replace("-", "−")


def dec(x, nd=1):
    return f"{x:.{nd}f}".replace(".", ",").replace("-", "−")


def pct(x):
    return f"{x:+.0f}%".replace("-", "−")


# Números citados no artigo: gravados em artigo/resultados/numeros.json, de onde saem as tabelas de artigo/latex/
NUM: dict = {}


def r0(x):
    """Inteiro arredondado, com o sinal de menos tipográfico."""
    x = float(x)
    return str(int(np.sign(x) * np.floor(abs(x) + 0.5))).replace("-", "−")  # meio para cima, não o arredondamento do banqueiro

