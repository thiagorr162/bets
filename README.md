# Efeitos das bets no Brasil

Endividamento, inadimplência, consumo e saúde mental antes e depois da expansão das apostas de quota fixa
(Lei 13.756/2018), da regulação (2025) e da proibição (MP 1.394, set/2026).

Tudo roda **a partir da raiz** com `uv`. Os caminhos são absolutos via `src/config.py`.

```bash
uv sync
uv run python -m src.pipeline            # etapas leves (APIs), minutos
uv run python -m src.pipeline --pesado   # + SCR, Bolsa Família, DATASUS: horas, dezenas de GB
uv run jupyter lab notebooks/            # análise rápida
```

| Pasta | Script | Fonte | Saída (`data/processed/`) |
|---|---|---|---|
| `src/endividamento` | `sgs_familias` | BCB/SGS 29037–29035, 20541, 20633, IPCA 433 | `endividamento_sgs` |
| `src/inadimplencia` | `sgs_inadimplencia` | BCB/SGS 21082, 21084, 21112 | `inadimplencia_sgs` |
| | `scr_uf` | SCR.data (PF × UF × renda × ocupação × modalidade) | `scr_pf_uf`, `scr_pf_uf_mes` |
| `src/consumo` | `pmc_pms` | IBGE/SIDRA 8880, 8881, 5906 | `consumo_pmc_pms` |
| `src/exposicao` | `municipios` | IBGE localidades + SIDRA 6579 | `municipios`, `populacao_municipio` |
| | `pix_municipio` | BCB Olinda, Pix por município | `pix_municipio` |
| | `bolsa_familia` | Portal da Transparência (CGU) | `bolsa_familia_municipio` |
| | `google_trends` | Google Trends (busca por apostas, UF × mês) | `google_trends_uf` |
| | `datasenado` | DataSenado 2024 (% que apostou e % com dívida em atraso, por UF) | `datasenado_uf_2024` |
| `src/saude_mental` | `sih_internacoes` | DATASUS SIH-RD (F63, F, F1x, X60–X84) | `sih_mental_municipio` |
| | `sia_caps` | DATASUS SIA-PS (RAAS/CAPS) | `sia_caps_municipio` |
| | `sim_suicidio` | DATASUS SIM (X60–X84) | `sim_suicidio_municipio` |

Cada script aceita filtros (`--anos`, `--ufs`, `--meses`; veja o docstring). Os scripts pesados guardam
agregados por arquivo em `data/interim/`, então dá para interromper e retomar.
As decisões metodológicas estão explicadas nos notebooks:

| Notebook | Conteúdo |
|---|---|
| `analise.ipynb` | Visão geral, linha do tempo, pandemia, deflator |
| `google_trends.ipynb` | Exposição: busca por apostas por UF e mês |
| `validacao_trends.ipynb` | Trends × DataSenado; apostadores × dívidas |
| `inadimplencia_painel.ipynb` | Painel UF × mês: Trends × inadimplência (SCR) |
| `consumo_painel.ipynb` | Painel UF × mês: Trends × varejo e serviços (PMC/PMS) |
| `saude_mental.ipynb` | Jogo patológico (F63) nos CAPS: tendência e painel |

Os painéis são montados por `src/painel.py`.
