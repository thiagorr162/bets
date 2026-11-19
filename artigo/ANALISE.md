# Jogo patológico na APS e nos CAPS, 2018–2026

Este documento explica o que a análise faz e por quê. O código está em `analise/` (seção 1 em `dados.py`, 2 em `joinpoint.py`, 3–8 em `rodar.py`, 9 em `figuras.py`), a saída completa em `resultados/resultados.txt` e as figuras em `resultados/figuras/`. As seções têm a mesma numeração no código e na saída. Todo número citado no artigo vai também para `resultados/numeros.json`, de onde `analise/para_latex.py` gera as tabelas do artigo em `latex/tabelas/`.

O artigo usa só uma parte do que está aqui: a descritiva, o modelo principal com o controle negativo, um resumo da robustez, o perfil e a conduta. A magnitude (4c) e a defasagem entre as redes (7) ficam só neste documento.

```
uv run python artigo/analise/rodar.py        # uns 3 minutos com 22 processos; --B 99 para testar rápido
                                             # no fim, atualiza as tabelas e figuras de artigo/latex/
```

## 1. Dados

Usamos só dados públicos agregados. Não há ligação de pacientes, então não há submissão ao CEP (Res. CNS 510/2016, art. 1º).

Na atenção primária, a fonte é o relatório público de produção do SISAB: atendimentos individuais por mês, Brasil, de fev/2018 a set/2026. A unidade é o atendimento em que o CID foi registrado. Um mesmo atendimento pode ter mais de um CID.

Nos CAPS, a fonte são as RAAS do SIA-PS, baixadas do FTP do DATASUS, de jan/2018 a jun/2026. A unidade é a linha de RAAS, isto é, um procedimento registrado, datado pelo dia do atendimento. Do arquivo o script lê só sete colunas: estabelecimento, data do atendimento, sexo, idade, tipo de idade, CID principal e data de início da RAAS. A idade é usada só para formar faixas etárias. O cartão SUS e a data de nascimento não são lidos, e nenhum paciente é seguido entre meses. Tudo o que sai do script são contagens agregadas por mês, CID, sexo e faixa etária.

Três recortes de período:

- jul–ago/2026 ficam de fora nos CAPS porque ainda estão chegando;
- falta um arquivo dos 2.808 (AP, dez/2023);
- jan/2018 fica de fora na APS. É o primeiro mês do SISAB e tem 34 registros de jogo, contra 5 a 18 nos onze meses seguintes. Esse ponto sozinho criava uma quebra falsa no começo da série. A série completa aparece na robustez.

Os grupos de CID:

| Grupo | Códigos | Para quê |
|---|---|---|
| Jogo | F63.0 | desfecho |
| Referência | F32, F33, F41, F43, F10, F20 | representa o sistema: a demanda geral de saúde mental, usada como denominador |
| Controle negativo | F63.1, F63.2, F63.3 (piromania, cleptomania, tricotilomania) | mesmo agrupamento do jogo, mesmas regras de codificação, nada a ver com apostas |
| F63 sem especificação | F63, F63.8, F63.9 | não é controle, porque pode conter jogo; serve para ver se a alta é só codificação mais específica (só CAPS) |

Registro não é pessoa. Quem está em acompanhamento gera vários registros.

## 2. O modelo

Todos os testes usam regressão segmentada (joinpoint), a mesma ideia do programa Joinpoint do NCI, comum na CSP. Para contagens mensais:

```
log E[y_t] = log(denominador_t) + 11 dummies de mês + pandemia (mar/2020–dez/2021)
             + β·t + Σ δ_k·(t − τ_k)+
```

A tendência é uma linha quebrada. Em cada quebra τ a inclinação muda, mas a curva não salta.

- Contagens com denominador usam binomial negativa, com o denominador como offset. Quando o desfecho é uma fração (jogo / (jogo + controle)) usamos binomial com logit.
- As quebras são procuradas em todas as posições possíveis, com pelo menos 12 meses entre elas e das pontas. Testamos de 0 a 2 quebras e escolhemos pelo BIC. Entre modelos a menos de 2 pontos do melhor, fica o mais simples.
- O resultado de cada segmento é a variação percentual anual (VPA), 100·(e^(12·inclinação) − 1). A VPAM é a média do período todo (o que o Joinpoint chama de AAPC).

Sobre os intervalos de confiança: o principal é o do bootstrap. Ele reamostra blocos de 6 meses dos resíduos (999 réplicas) e, em cada réplica, procura as quebras de novo. Assim o intervalo carrega a incerteza sobre onde a quebra está. O número de quebras fica fixo nas réplicas. É o único intervalo da análise: não usamos erro-padrão de Newey-West, que seria condicional às quebras encontradas.

A existência da quebra é decidida pelo BIC, e não por um teste de Wald: com a posição da quebra estimada, esse teste não tem a distribuição usual.

## 3. Descritiva

Tabela por ano com as contagens, a taxa de jogo e do controle por 10 mil registros de referência, a taxa por milhão de habitantes e a % de mulheres.

A seção 3c traz a conduta registrada ao fim do atendimento na APS (alta, retorno, encaminhamento), de jan/2025 ao fim da série, para jogo, ansiedade, depressão e álcool, a partir do relatório do SISAB com a coluna Conduta.

Também há o perfil por sexo e faixa etária em 2025 (3b): a porcentagem dos registros de jogo e da referência em cada combinação de sexo e faixa. Na APS os dados vêm do recorte sexo × faixa do SISAB, disponível desde 2022. Nos CAPS vêm das RAAS. O perfil é descritivo e não tem intervalo de confiança, porque os registros de um mesmo paciente não são independentes. Registros sem sexo F/M ou sem idade ficam de fora.

## 4. Pergunta principal: o registro de jogo cresceu mais que o sistema?

Primeiro medimos quanto o sistema cresceu, ajustando o modelo às próprias contagens de referência, sem denominador. A referência principal das duas redes tem IC bootstrap, como os outros números citados no artigo. Fazemos o mesmo com a referência ampliada com CIAP na APS e com o total de RAAS nos CAPS.

Depois vem o modelo principal: contagem de F63.0 com offset log(referência). Com o offset, o crescimento do sistema já sai descontado. O que sobra é a tendência do jogo por unidade de demanda de saúde mental.

A hipótese se sustenta se o BIC escolher pelo menos uma quebra e o intervalo bootstrap da VPA do último segmento ficar todo acima de zero.

### Magnitude: quantos registros acima da linha de base (4c)

A VPA diz o quanto a taxa cresce por ano, mas não quantos registros isso significa. Para dar a ordem de grandeza, comparamos o observado com uma linha de base tirada do próprio modelo principal: o segmento anterior à quebra final prolongado, isto é, o mesmo ajuste sem a última mudança de inclinação. A suposição é que, sem a inflexão, a taxa de jogo por registro de referência seguiria a tendência que já tinha. A escolha é conservadora, porque nos CAPS o primeiro segmento já subia 18% ao ano. Como alternativa, mostramos a taxa congelada no nível que tinha na quebra. As duas linhas de base incluem o crescimento do sistema (pelo offset) e a sazonalidade.

O excesso é o observado menos o esperado, calculado por ano-calendário. A janela é fixa de propósito. Se somássemos "tudo depois da quebra", a janela mudaria a cada réplica do bootstrap, já que a quebra muda de lugar entre elas. O IC vem das mesmas 999 réplicas: em cada uma, a linha de base é refeita com os coeficientes e a quebra daquela réplica, e o observado fica fixo. O intervalo mede, portanto, a incerteza da linha de base, incluindo a incerteza sobre onde está a quebra.

É uma medida descritiva. A linha de base não é um contrafactual "sem apostas" nem "sem a lei", porque a quebra é estimada e não corresponde a uma data de intervenção (na APS ela vem 18 meses antes da Lei 14.790). Por isso não usamos uma regressão antes/depois com data fixa. Ela atribuiria à lei uma alta que já estava em curso e apagaria a defasagem entre APS e CAPS (seção 7).

Nos CAPS, calculamos também o excesso com os F63 sem especificação somados ao desfecho. Nesse recorte a comparação deve ser feita pela fração do observado. O excesso absoluto fica maior porque esses códigos também crescem desde 2021.

## 5. Especificidade

A alta poderia ser só mudança no jeito de codificar: o e-SUS passando a usar CID, a RAAS sendo preenchida de outro jeito, a rede sendo treinada. Uma mudança dessas afetaria os outros códigos F63 também.

Por isso rodamos o mesmo modelo no controle (F63.1–F63.3). Se ele não sobe, ponto para o jogo.

O teste direto é a fração F63.0 / (F63.0 + F63.1–F63.3), em binomial com logit. A inclinação desse modelo é exatamente a diferença entre o crescimento do jogo e o do controle. Se a VPA do último segmento for positiva, o jogo cresce mais.

Nos CAPS olhamos também os F63 sem especificação. Eles podem esconder casos de jogo. Se crescem junto, parte da alta do F63.0 pode ser só gente trocando F63 por F63.0. Testamos isso de duas formas: somando esses códigos ao desfecho e usando-os como comparador no lugar do controle. No SISAB esses códigos não foram consultados.

## 6. Robustez

A VPA do último segmento é refeita em vários cenários. A tabela e a figura mostram a estimativa pontual de cada cenário; só a análise principal tem intervalo (bootstrap).

| Cenário | O que testa |
|---|---|
| até 3 quebras; 1 quebra fixa | a escolha do número de quebras |
| sem os meses da pandemia | a distorção de 2020–2021 |
| série até dez/2025 | meses recentes ainda sendo consolidados |
| APS com jan/2018 | a exclusão do primeiro mês |
| APS: referência com CID + CIAP | o denominador |
| CAPS: referência = capítulo F inteiro | o denominador |
| CAPS: no máximo 10 registros de jogo por CAPS-mês | picos de um único serviço lançando muita coisa de uma vez |
| CAPS: só RAAS iniciadas no mês | uma aproximação de casos novos, sem o acompanhamento |
| CAPS: F63 sem especificação somados ao desfecho, ou como comparador | reclassificação dentro de F63 |
| controle só com F63.3 | a composição do controle |
| log(referência) como covariável, com coeficiente livre | se fixar o coeficiente em 1 (offset) distorce a tendência |

O offset supõe que o jogo, sem nada novo, anda proporcional à referência. O último cenário da tabela testa isso: com o coeficiente de log(referência) livre, o que importa é se a VPA final se mantém.

## 7. Secundário: a alta começou primeiro na APS?

Comparamos a data da quebra que abre o último segmento na APS e nos CAPS. A defasagem é CAPS menos APS, em meses.

O bootstrap é conjunto: a réplica b da APS e a réplica b dos CAPS reamostram os mesmos meses do calendário. Isso mantém os choques que atingem as duas redes ao mesmo tempo. O intervalo da defasagem sai dessas réplicas pareadas, e contamos em quantas o CAPS vem depois.

O teste é feito no modelo principal (jogo / referência). O modelo jogo vs controle entra só como sensibilidade.

Mesmo que a APS venha antes, isso mostra quando cada rede passou a registrar jogo. Não mostra pacientes indo de uma para a outra.

## 8. Secundário e descritivo: proporção de mulheres

A porcentagem de mulheres nos registros de jogo e da referência, por ano, de 2022 em diante (antes disso o SISAB não tem o recorte por sexo). Sem intervalo de confiança, porque os registros de uma mesma pessoa não são independentes. Uma versão anterior testava a diferença de tendência por regressão logística; foi retirada para manter a análise simples, já que a série anual mostra o padrão diretamente.

## 9. Figuras

| Arquivo | O que mostra |
|---|---|
| `figura1_tendencia` (artigo, Figura 1) | taxa por 10 mil registros de referência com a linha ajustada e a banda de confiança de 95% (bootstrap pontual: em cada réplica a linha é refeita com os coeficientes e as quebras da réplica). A linha tracejada é a quebra final e a faixa azul é o intervalo bootstrap dela. Os pequenos degraus na linha vêm do indicador de pandemia. As leis aparecem só como referência de época |
| `figura2_perfil` (artigo, Figura 2) | perfil por sexo e faixa etária em 2025. As barras são o jogo e os traços, a referência |
| `figura_s2_robustez` (suplementar, Figura S1) | os cenários da seção 6 |
| `figura_s3_mulheres` (suplementar, Figura S2) | % de mulheres por ano, jogo e referência |
| `figura_s1_volume` (fora do artigo) | registros por mês em relação à média de 2018: jogo, referência e controle |

## Resultados

Rodada de 19/11/2026, com 999 réplicas. Os intervalos são do bootstrap, a não ser quando indicado.

O sistema cresceu, mas pouco perto do jogo. No último segmento, a referência sobe 19% ao ano na APS e 6% ao ano nos CAPS.

O registro de jogo cresceu bem mais que o sistema, nas duas redes:

| | Início da alta | VPA do último segmento |
|---|---|---|
| APS | jun/2022 (abr/2021 a dez/2022) | +100% (91 a 110) |
| CAPS | mai/2024 (jun/2023 a jan/2025) | +181% (107 a 367) |

Em números absolutos, quase todo o registro recente está acima da linha de base. Em 2025, primeiro ano inteiro depois da quebra nas duas redes:

| 2025 | Observado | Esperado | Acima da linha de base |
|---|---|---|---|
| APS | 3.423 | 451 (57 a 761) | 2.972 (2.662 a 3.366), ou 87% (78 a 98) |
| CAPS | 4.371 | 1.622 (1.033 a 2.129) | 2.749 (2.242 a 3.338), ou 63% (51 a 76) |
| CAPS, F63.0 + F63 sem especificação | 15.322 | 7.354 | 52% (47 a 59) |

Com a taxa congelada na quebra, a fração fica em 88% na APS e 69% nos CAPS. Em 2026 (jan–set na APS, jan–jun nos CAPS) a fração sobe para 92% e 81%. Em 2023, antes da quebra dos CAPS, o observado ficou dentro do esperado (−11%, de −33 a 19), como deveria. O esperado da APS tem intervalo largo porque a linha de base é extrapolada por mais de três anos a partir de um segmento com poucos casos, mas a fração em excesso quase não depende disso, já que o observado é muito maior.

O offset se sustenta: com o coeficiente de log(referência) livre no joinpoint, a VPA final passa de 100% para 104% na APS e de 181% para 189% nos CAPS.

O controle quase não se mexe. Na APS sobe 4% ao ano (IC bootstrap 1 a 14). Nos CAPS sobe 35% ao ano, mas só a partir de jul/2025, e o intervalo bootstrap vai de −1% a +61%. Na prática, a posição dessa quebra é indefinida (IC de fev/2020 a jul/2025). A razão jogo : controle cresce 91% ao ano na APS desde jun/2022 (84 a 99) e 151% ao ano nos CAPS desde dez/2023 (120 a 204).

Nos CAPS, os F63 sem especificação também sobem: 30% ao ano desde out/2021 (25 a 39). É o resultado que mais pesa contra. O perfil etário, porém, não é o do jogo: de jan/2022 a jun/2026, 36% desses registros são de menores de 18 anos, contra 7% no F63.0. Então é improvável que a maior parte deles seja jogo mal codificado, e somá-los ao desfecho é um cenário extremo. Com eles somados ao desfecho, a alta cai de 181% para 62% ao ano. Usados como comparador, a razão cresce 106% ao ano, contra 151% com o controle. O jogo continua crescendo mais que tudo, mas parte da alta do F63.0 provavelmente é reclassificação dentro de F63.

Nos outros cenários de robustez, o último segmento fica entre +100% e +103% na APS e entre +145% e +237% nos CAPS. A quebra cai entre jun/2022 e jul/2023 na APS e entre nov/2023 e mai/2024 nos CAPS.

A APS vem antes. Pelo modelo principal, a defasagem é de 23 meses (11 a 39), e o CAPS vem depois em 995 das 999 réplicas. No modelo jogo vs controle, a defasagem é de 18 meses (8 a 35).

A participação das mulheres no jogo só muda na APS: foi de 22% em 2022 para 39% em 2023 e depois ficou entre 46% e 48%, enquanto na referência ficou em 70%. Parece mais um salto em 2023 do que uma tendência. Nos CAPS a proporção oscila sem direção (59%, 36%, 55%, 42%, 45% de 2022 a 2026).

O perfil de quem recebe registro de jogo é diferente do perfil da referência. Em 2025, de 25 a 44 anos estavam 63% dos registros de jogo na APS e 59% nos CAPS. Na referência eram 32% e 42%. Homens de 18 a 24 anos pesam no jogo 11% na APS e 9% nos CAPS, contra 2% e 6% na referência. Pessoas de 60 anos ou mais quase não aparecem no jogo (3% na APS), mas são 25% da referência na APS.

## Limitações

Registro não é pessoa. Sem ligar pacientes, não dá para separar caso novo de acompanhamento. A RAAS iniciada no mês é só uma aproximação.

O controle negativo pega mudanças gerais de codificação. Não pega uma mudança que favoreça o F63.0 em particular: mais atenção ao tema na mídia, a Lei 14.790, orientações do Ministério da Saúde. Daqui não dá para separar aumento de demanda de aumento de reconhecimento do problema. Por isso os resultados devem ser lidos como registro de atendimento, não como ocorrência.

Nos CAPS, os F63 sem especificação também crescem, e somá-los ao F63.0 reduz bastante a alta. Uma parte do que aparece como jogo é provavelmente codificação mais específica.

Antes de 2021, os registros de jogo nos CAPS são poucos e concentrados. Em 2020 um único CAPS responde por metade do ano. O maior lançamento num mês foi de 150 registros, em ago/2022. Por isso a quebra de 2020 no modelo jogo vs controle dos CAPS e a % de mulheres antes de 2021 não devem ser interpretadas.

Parte do crescimento nos CAPS vem de mais serviços passando a usar o código, não só de mais registros por serviço. Os dados por estabelecimento permitem separar as duas coisas, mas isso não foi feito aqui.

O excesso depende de uma linha de base extrapolada. Ela supõe que a tendência anterior à quebra continuaria por até quatro anos, e não há como verificar isso. Por isso o esperado tem intervalo largo, e o número serve como ordem de grandeza, não como contagem de casos atribuíveis às apostas.

O modelo não permite saltos de nível, só mudanças de inclinação. Um salto, como o de jan/2025, entra como inclinação. Algumas séries têm autocorrelação nos resíduos (Ljung-Box p < 0,05), o que sugere que a linha quebrada não descreve tudo.

O desenho é ecológico. Não estima prevalência nem o efeito de uma lei.

O plano não foi registrado antes. Escolhas como o máximo de 2 quebras, a regra dos 2 pontos de BIC, os códigos do controle e a janela da feminização foram feitas durante a análise.
