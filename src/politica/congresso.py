"""Posições do Congresso sobre as bets, com dados nominais públicos (Câmara e Senado):

1. Votação de 2023 sobre o cassino online (PL 3.626/2023, que virou a Lei 14.790):
   - Senado, 12/12/2023: emenda nº 139 (Carlos Portinho), que tirava os jogos online/cassino do projeto. Aprovada 37 × 27.
   - Câmara, 21/12/2023: emenda do Senado nº 3 (a mesma mudança). Rejeitada 120 × 261, o que manteve o cassino na lei.
   Em ambas, "Sim" = tirar o cassino online; "Não" = manter.
2. Projetos de lei na Câmara que proíbem as apostas de quota fixa (por inteiro ou só o cassino online).

As emendas à MP 1.394/2026 ficam em src/politica/emendas_mp1394.py.

uv run python -m src.politica.congresso
"""

import polars as pl
import requests

from src.config import pasta
from src.utils import salvar

CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
SENADO = "https://legis.senado.leg.br/dadosabertos"
H = {"Accept": "application/json"}
VOT_CAMARA = "2374400-121"  # DTQ 17: emenda do Senado nº 3, 21/12/2023
MATERIA_SENADO, SESSAO_SENADO = "160197", "6797"  # PL 3626/2023; votação da emenda nº 139, 12/12/2023
VOTO = {"Sim": "tirar o cassino", "Não": "manter o cassino"}

# Projetos de lei (Câmara) que proíbem as apostas, encontrados pela busca da API e conferidos pela ementa.
PLS = {2462206: "total", 2494936: "total", 2519715: "total", 2538951: "total", 2541007: "total",
       2578880: "total (apostas online)", 2600159: "total", 2615935: "total", 2630762: "total", 2645600: "total",
       2636532: "só o cassino online"}


def get(url, **params):
    r = requests.get(url, params=params, headers=H, timeout=120)
    r.raise_for_status()
    return r.json()


def votacao_camara() -> pl.DataFrame:
    votos = get(f"{CAMARA}/votacoes/{VOT_CAMARA}/votos")["dados"]
    return pl.DataFrame([{
        "casa": "Câmara", "nome": v["deputado_"]["nome"], "partido": v["deputado_"]["siglaPartido"],
        "uf": v["deputado_"]["siglaUf"], "voto": VOTO.get(v["tipoVoto"], "outro"),
        "url": f"https://www.camara.leg.br/deputados/{v['deputado_']['id']}"} for v in votos])


def votacao_senado() -> pl.DataFrame:
    vs = get(f"{SENADO}/materia/votacoes/{MATERIA_SENADO}")["VotacaoMateria"]["Materia"]["Votacoes"]["Votacao"]
    v = next(x for x in vs if x["CodigoSessaoVotacao"] == SESSAO_SENADO)
    linhas = []
    for p in v["Votos"]["VotoParlamentar"]:
        ip = p["IdentificacaoParlamentar"]
        linhas.append({"casa": "Senado", "nome": ip["NomeParlamentar"], "partido": ip.get("SiglaPartidoParlamentar"),
                       "uf": ip.get("UfParlamentar"), "voto": VOTO.get(p.get("SiglaVoto"), "outro"),
                       "url": ip.get("UrlPaginaParlamentar")})
    return pl.DataFrame(linhas)


def projetos() -> pl.DataFrame:
    cache_dep = {}
    linhas = []
    for pid, alcance in PLS.items():
        p = get(f"{CAMARA}/proposicoes/{pid}")["dados"]
        for a in get(f"{CAMARA}/proposicoes/{pid}/autores")["dados"]:
            partido = uf = None
            if a.get("uri") and "/deputados/" in a["uri"]:
                if a["uri"] not in cache_dep:
                    s = get(a["uri"])["dados"]["ultimoStatus"]
                    cache_dep[a["uri"]] = (s.get("siglaPartido"), s.get("siglaUf"))
                partido, uf = cache_dep[a["uri"]]
            linhas.append({"projeto": f"PL {p['numero']}/{p['ano']}", "data": p["dataApresentacao"][:10], "alcance": alcance,
                           "ementa": p["ementa"], "autor": a["nome"], "partido": partido, "uf": uf,
                           "url": f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={pid}"})
    return pl.DataFrame(linhas)


def main():
    salvar(pl.concat([votacao_camara(), votacao_senado()]), pasta("congresso") / "congresso_votacao_cassino_2023.parquet")
    salvar(projetos(), pasta("congresso") / "congresso_pls_proibicao.parquet")


if __name__ == "__main__":
    main()
