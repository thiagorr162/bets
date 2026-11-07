"""Funções auxiliares de download e IO."""

import time
from pathlib import Path

import polars as pl
import requests
from tqdm import tqdm

from src.config import ROOT

UA = {"User-Agent": "bets-research/0.1"}


def get_json(url: str, params: dict | None = None, tentativas: int = 5, timeout: int = 180):
    for i in range(tentativas):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if i == tentativas - 1:
                raise
            time.sleep(2**i)


def baixar(url: str, destino: Path, forcar: bool = False) -> Path:
    """Download em streaming para `destino` (pula se já existe)."""
    if destino.exists() and not forcar:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".part")
    with requests.get(url, headers=UA, stream=True, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0)) or None
        with open(tmp, "wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=destino.name) as bar:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                bar.update(len(chunk))
    tmp.rename(destino)
    return destino


def salvar(df: pl.DataFrame, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(destino)
    print(f"✓ {destino.relative_to(ROOT)}  ({df.height:,} linhas)")
    return destino


def juntar(pasta: Path, destino: Path) -> pl.DataFrame:
    """Concatena todos os parquets de `pasta` em `destino`."""
    arquivos = sorted(pasta.glob("*.parquet"))
    if not arquivos:
        raise FileNotFoundError(f"nenhum parquet em {pasta}")
    df = pl.concat([pl.read_parquet(a) for a in arquivos], how="diagonal_relaxed")
    salvar(df, destino)
    return df
