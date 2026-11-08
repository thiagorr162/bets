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

| Script | Fonte | Saída (`data/<tema>/processed/`) |
|---|---|---|
| `src/exposicao/municipios` | IBGE: municípios e população estimada (SIDRA 6579) | `municipios`, `populacao_municipio` |
| `src/exposicao/google_trends` | Google Trends: busca por apostas, UF × mês | `google_trends_uf` |
| `src/exposicao/datasenado` | DataSenado 2024: % que apostou e % com dívida atrasada, por UF | `datasenado_uf_2024` |
| `src/saude_mental/sia_caps` | DATASUS SIA-PS (CAPS), agregado por município × mês | `sia_caps_municipio` |
| `src/saude_mental/sia_f63_pacientes` | DATASUS SIA-PS, pacientes com F63 (pseudonimizado por `minimizar_f63`) | `sia_f63_registros`, `sia_f63_historico`, `sia_perfil` |
| `src/saude_mental/sia_trajetorias` | DATASUS SIA-PS, todos os pacientes: pessoa (pseudônimo) × mês × grupo de CID | `sia_trajetorias` |
| `src/saude_mental/sia_grupos` | DATASUS SIA-PS: pacientes por grupo de CID, sexo e faixa etária | `sia_grupos` |
| `src/saude_mental/sisab_aps` | SISAB (atenção primária): atendimentos por CID/CIAP, sexo, faixa etária e sexo × faixa | `sisab_aps` |
| `src/saude_mental/sisab_conduta` | SISAB: conduta ao fim do atendimento (alta, retorno, encaminhamento p/ CAPS...) por CID | `sisab_conduta` |
| `src/saude_mental/graves_f63` | DATASUS SIH (internações) e SIM (óbitos), agregados por UF × mês × sexo × faixa etária | `sih_graves`, `sim_graves` |
| — | IBGE, projeção da população por sexo e idade (SIDRA 7358), em `data/ibge/raw/` | usada no `suicidio.ipynb` |

Os microdados do DATASUS são baixados direto do FTP (`ftp.datasus.gov.br`), em paralelo. Os `.dbc` originais ficam
guardados em `data/caps/raw/datasus/` (SIA-PS) e `data/internacoes_obitos/raw/datasus/` (SIH, SIM) e são reaproveitados:
um recorte novo não precisa baixar tudo de novo.

Os dados ficam organizados por tema, cada um com `raw/` (como baixado, nunca apagado), `interim/` (agregados por arquivo)
e `processed/` (tabelas finais). Nos scripts, use `pasta("caps", "raw")` de `src/config.py`.

```
data/
  caps/                SIA-PS: atendimentos nos CAPS
  atencao_primaria/    SISAB: atendimentos na atenção primária
  internacoes_obitos/  SIH e SIM
  exposicao/           Google Trends, DataSenado
  ibge/                municípios, população, malha das UFs
  congresso/           votações, emendas e projetos
  economia/            dados do branch master (SCR, Pix, Bolsa Família, SGS, PMC)
  .chave_pseudonimo    chave local do pseudônimo dos pacientes (não compartilhar)
```

### As tabelas que o site usa

Os exemplos abaixo são ilustrativos (códigos de paciente inventados); os números agregados são reais.

**`caps/sia_f63_registros`**: uma linha por paciente × mês em que a pessoa teve algum diagnóstico F63 no CAPS.

| coluna | o que é |
|---|---|
| `id` | código do paciente: o CNS criptografado do DATASUS, pseudonimizado de novo com HMAC e a chave local |
| `cmp` | mês do atendimento (`AAAAMM`) |
| `cod_uf` | UF (código IBGE; 35 = SP) |
| `faixa`, `SEXOPAC` | faixa etária (0-17, 18-24, 25-34, 35-44, 45-59, 60+) e sexo |
| `CIDPRI`, `CIDASSOC` | diagnóstico principal e associado |
| `inicio_cmp` | mês de início do acompanhamento no CAPS |
| `n_proc` | procedimentos no mês |

```
id                cmp     cod_uf  faixa  SEXOPAC  CIDPRI  CIDASSOC  inicio_cmp  n_proc
a1b2c3d4e5f60718  202503  35      25-34  M        F630              202503      2
a1b2c3d4e5f60718  202504  35      25-34  M        F630    F412      202503      4
```

**`caps/sia_f63_historico`**: todos os atendimentos no CAPS, com qualquer diagnóstico, das pessoas que alguma vez
tiveram F63. Serve para olhar o que havia antes do primeiro F63.0.

```
id                cmp     CIDPRI  inicio_cmp  n_proc
b7c8d9e0f1a2b3c4  202408  F322    202408      3
b7c8d9e0f1a2b3c4  202505  F630    202408      2
```

**`caps/sia_perfil`**: totais, sem pessoas: `cmp, grupo, SEXOPAC, faixa, pacientes`. Grupos: `f630`, `f63`, `mental`
(capítulo F inteiro) e `subst` (F10–F19). É a referência "saúde mental em geral" do perfil. Números reais:

```
cmp     grupo   SEXOPAC  faixa  pacientes
202503  f630    M        25-34  10
202503  mental  M        25-34  37566
```

**`caps/sia_trajetorias`**: todos os pacientes de saúde mental (38,7 milhões de linhas, 5,5 milhões de pessoas), em
inteiros para caber na memória: `id` (Int64, primeiros 8 bytes do HMAC), `mes` (meses desde jan/2018), `sexo`,
`faixa` e `grupo` (1 jogo, 2 álcool, 3 drogas, 4 psicoses, 5 humor, 6 ansiedade, 7 personalidade, 8 outros F).
Uma linha por pessoa × mês × grupo de diagnóstico presente (principal ou associado). `sexo`: 0 = M, 1 = F;
`faixa`: 0 (0-17) a 5 (60+); `mes` 86 = mar/2025.

```
id                    mes  sexo  faixa  grupo
-1234567890123456789  86   0     2      1
-1234567890123456789  90   0     2      6
```

**`atencao_primaria/sisab_aps`**: o SISAB não identifica pessoas, então tudo é contagem de atendimentos:
`cmp, recorte, valor, codigo, grupo, atendimentos`. `recorte` é `total`, `sexo` (`valor` = F/M), `faixa`
(`valor` = 25-34...) ou `sexofaixa` (`valor` = F_25-34). `codigo` tem sufixo `-1` para CID e `-4` para CIAP.

```
cmp     recorte  valor  codigo  grupo     atendimentos
202404  sexo     F      F630-1  jogo_cid  46
202511  faixa    0-17   F630-1  jogo_cid  21
```

**`atencao_primaria/sisab_conduta`**: `cmp, grupo, conduta, n`, uma consulta por diagnóstico (com a coluna
"Conduta" o relatório soma os diagnósticos pedidos). Um atendimento pode ter mais de uma conduta. Números reais:

```
cmp     grupo     conduta                                  n
202501  jogo_cid  Alta do episódio                         62
202501  jogo_cid  Encaminhamento p/ CAPS                   3
```

**`exposicao/google_trends_uf`**: `uf, data, indice` (0–100 dentro da UF), `nivel` (peso relativo da UF) e
`indice_comparavel`. O site usa só a série `BR`. Números reais:

```
uf  data        indice  nivel  indice_comparavel
BR  2025-03-01  47
SP  2025-03-01  48      38     49.1
```

### Como as tabelas são cruzadas

- **Série mensal do CAPS**: em `sia_f63_registros`, o diagnóstico F63 da linha é o `CIDPRI` se ele for F63, senão o
  `CIDASSOC`; contam-se os `id` distintos com F630 por `cmp` (mar/2025: 80 pessoas). O controle é o mesmo com
  F631–F633.
- **Novas no CAPS**: para cada `id`, o primeiro mês com F63.0 (t0). Junta com `sia_f63_historico` pelo `id` e
  procura qualquer atendimento entre t0 − 12 meses e t0 − 1. Sem nenhum, a pessoa é "nova no CAPS".
  Exemplo: primeiro F63.0 em mar/2025 e nenhum registro de mar/2024 a fev/2025 → nova.
- **O que aparece depois**: em `sia_trajetorias`, t0 de cada pessoa × grupo é o primeiro `mes` do grupo. Para quem
  tem t0 entre jan/2019 e jun/2025, a tabela é cruzada consigo mesma pelo `id` em duas janelas: 12 meses antes e
  12 depois de t0. Um grupo é "novo" se aparece depois e não antes. Exemplo: F63.0 em mar/2025, F41 (ansiedade) em
  jul/2025 e nenhum F40–F48 entre mar/2024 e fev/2025 → ansiedade nova. As taxas dos outros grupos de entrada são
  padronizadas pela composição sexo × faixa dos pacientes de jogo (média ponderada das taxas por estrato).
- **Atenção primária por 10 mil**: no mesmo `cmp` de `sisab_aps`, atendimentos de `jogo_cid` ÷ soma de
  `depressao_cid`, `depressao_rec_cid`, `ansiedade_cid`, `estresse_cid`, `alcool_cid`, `esquizofrenia_cid` × 10.000.
  Mar/2025: 162 ÷ 159.589 × 10.000 = 10,2.
- **Perfil**: CAPS = pessoas-mês da `sia_f63_registros` por sexo × faixa, contra o grupo `mental` da `sia_perfil`;
  atenção primária = recorte `sexofaixa` (pirâmide) e `sexo` (mulheres por ano), contra a soma da referência.
- **Conduta**: cada conduta de `sisab_conduta` ÷ atendimentos do mesmo grupo e mês em `sisab_aps`.
- **Quantas vezes maior que em 2022**: cada mês ÷ média mensal de 2022 da mesma série (jogo na atenção primária,
  jogo no CAPS, referência da atenção primária). Atenção primária, mar/2025: 162 ÷ 19 = 8,5×.
- **Buscas**: a série `BR` do Trends entra por `cmp` (mês), só para mostrar no mesmo eixo; não há regressão.
- **Supressão**: toda contagem publicada abaixo de 5 vira vazio (`site/montar_dados.py`, `MIN = 5`).

## Notebooks

| Notebook | Conteúdo |
|---|---|
| `google_trends.ipynb` | Busca por apostas por UF e mês; queda depois da MP 1.394 |
| `saude_mental.ipynb` | F63 nos CAPS: tendência nacional, comparação com outros diagnósticos, diferença longa por UF |
| `f63_pacientes.ipynb` | Pacientes com F63: subcódigos, novos × reclassificados, perfil por sexo e idade, comorbidade, regiões |
| `f63_comorbidade.ipynb` | Outros diagnósticos dos pacientes com F63.0 por ano e sexo (depressão, ansiedade, substâncias) |
| `atencao_primaria.ipynb` | Jogo patológico na atenção primária (SISAB): série, comparação com outros diagnósticos, perfil, comparação com o CAPS |
| `f63_trajetoria.ipynb` | Diagnósticos novos e permanência no CAPS depois do jogo patológico, comparado com outros grupos |
| `suicidio.ipynb` | Suicídio (SIM) por sexo e idade, taxas por 100 mil, antes e depois de 2022 |
| `mp1394_emendas.ipynb` | As 99 emendas à MP 1.394 (proibição): quem propôs afrouxar ou reforçar, por parlamentar e partido |

As decisões metodológicas estão explicadas nos próprios notebooks.

## Privacidade

Dado de saúde é **dado pessoal sensível** (LGPD, art. 5º, II). Por isso:
- `data/` fica fora do git;
- as tabelas de pacientes usam um **pseudônimo novo** (HMAC com chave aleatória em `data/.chave_pseudonimo`, que não
  deve ser compartilhada), UF em vez de município, faixa etária em vez de idade;
- os notebooks e o site mostram **só agregados**, com células de **menos de 5 pacientes suprimidas**;
- antes de publicar a parte de seguimento de pacientes, consultar o CEP (Resolução CNS 510/2016).
