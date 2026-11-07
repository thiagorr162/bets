# Bets e saúde mental no Brasil

Branch `saude-mental`: só a parte de **jogo patológico e saúde mental** do projeto, base para o site. A análise
econômica (endividamento, inadimplência, consumo, Pix, Bolsa Família) está no branch `master`.

**Pergunta:** o boom das apostas (2020–2023), a regulação (2025) e a proibição (MP 1.394, set/2026) aparecem na
procura por tratamento de **jogo patológico (CID F63.0)** no SUS?

Tudo roda **a partir da raiz** com `uv`. Os caminhos são absolutos via `src/config.py`.

```bash
uv sync
uv run python -m src.pipeline            # exposição: Trends, DataSenado, população (minutos)
uv run python -m src.pipeline --pesado   # + DATASUS: CAPS, pacientes com F63, internações e óbitos (~1–2 h)
uv run jupyter lab notebooks/
```

## Dados

| Script | Fonte | Saída (`data/processed/`) |
|---|---|---|
| `src/exposicao/municipios` | IBGE: municípios e população estimada (SIDRA 6579) | `municipios`, `populacao_municipio` |
| `src/exposicao/google_trends` | Google Trends: busca por apostas, UF × mês | `google_trends_uf` |
| `src/exposicao/datasenado` | DataSenado 2024: % que apostou e % com dívida atrasada, por UF | `datasenado_uf_2024` |
| `src/saude_mental/sia_caps` | DATASUS SIA-PS (CAPS), agregado por município × mês | `sia_caps_municipio` |
| `src/saude_mental/sia_f63_pacientes` | DATASUS SIA-PS, pacientes com F63 (pseudonimizado por `minimizar_f63`) | `sia_f63_registros`, `sia_f63_historico`, `sia_perfil` |
| `src/saude_mental/graves_f63` | DATASUS SIH (internações) e SIM (óbitos), agregados por UF × mês × sexo × faixa etária | `sih_graves`, `sim_graves` |
| — | IBGE, projeção da população por sexo e idade (SIDRA 7358), em `data/raw/ibge/` | usada no `suicidio.ipynb` |

Os microdados do DATASUS são baixados direto do FTP (`ftp.datasus.gov.br`), em paralelo, e agregados na hora: os
`.dbc` originais não ficam guardados.

## Notebooks

| Notebook | Conteúdo |
|---|---|
| `google_trends.ipynb` | Busca por apostas por UF e mês; queda depois da MP 1.394 |
| `saude_mental.ipynb` | F63 nos CAPS: tendência nacional, comparação com outros diagnósticos, diferença longa por UF |
| `f63_pacientes.ipynb` | Pacientes com F63: subcódigos, novos × reclassificados, perfil por sexo e idade, comorbidade, regiões |
| `f63_comorbidade.ipynb` | Outros diagnósticos dos pacientes com F63.0 por ano e sexo (depressão, ansiedade, substâncias) |
| `suicidio.ipynb` | Suicídio (SIM) por sexo e idade, taxas por 100 mil, antes e depois de 2022 |

As decisões metodológicas estão explicadas nos próprios notebooks.

## Privacidade

Dado de saúde é **dado pessoal sensível** (LGPD, art. 5º, II). Por isso:
- `data/` fica fora do git;
- as tabelas de pacientes usam um **pseudônimo novo** (HMAC com chave aleatória em `data/.chave_pseudonimo`, que não
  deve ser compartilhada), UF em vez de município, faixa etária em vez de idade;
- os notebooks e o site mostram **só agregados**, com células de **menos de 5 pacientes suprimidas**;
- antes de publicar a parte de seguimento de pacientes, consultar o CEP (Resolução CNS 510/2016).
