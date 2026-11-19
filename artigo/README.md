# Artigo: jogo patológico na APS e nos CAPS, 2018–2026

Artigo para *Cadernos de Saúde Pública* (categoria Artigo). Usa apenas dados públicos agregados: nenhum identificador de
paciente é lido, e não há ligação de registros (Resolução CNS 510/2016, art. 1º, parágrafo único, incisos II e V).

O repositório tem duas partes que não se misturam:

| Pasta | Conteúdo |
|---|---|
| `latex/` | **o artigo**: projeto LaTeX que sobe no Overleaf (`main.tex`, `bibliography.bib`, `macros.tex`, `tabelas/`, `figuras/`) |
| `analise/` | código da análise: `dados.py` (séries do SISAB e das RAAS), `joinpoint.py` (modelo e bootstrap), `rodar.py` (todas as análises, na ordem do `ANALISE.md`), `figuras.py`, `para_latex.py` (tabelas e figuras do artigo para `latex/`), `comum.py` (caminhos, períodos e grupos de CID) |
| `resultados/` | gerado por `rodar.py`: `resultados.txt` (saída completa), `numeros.json` (todo número citado no artigo) e `figuras/` (PNG 300 dpi, PDF, SVG) |
| `ANALISE.md` | o que a análise faz e por quê, com os resultados comentados |

```bash
uv run python artigo/analise/rodar.py        # análise completa (~3 min; --B 99 para testar rápido)
uv run python artigo/analise/para_latex.py   # só atualiza latex/tabelas e latex/figuras a partir de resultados/
```

## Fluxo com o Overleaf

- O texto se escreve no Overleaf. Para começar, suba a pasta `latex/` (zipada) como projeto novo.
- `latex/tabelas/*.tex` e `latex/figuras/*.pdf` vêm da análise: não se editam à mão. Se a análise mudar, rode
  `rodar.py` (ou `para_latex.py`) e suba de novo só essas duas pastas.
- Os números do texto estão digitados no `main.tex`. O `para_latex.py` confere se as afirmações qualitativas do texto
  ("dobrou a cada ano", "mais de duas vezes maior"...) continuam valendo com os números atuais e para com erro se não.
- Na submissão, a CSP pede texto, tabelas, figuras e legendas em arquivos separados, com o texto em DOC/DOCX (Times 12,
  entrelinha 1,5, margens de 2 cm). Isso se faz no fim, a partir do `main.tex`.

As entradas ficam em `data/`, fora do git: `atencao_primaria/processed/sisab_aps.parquet` e `sisab_conduta.parquet`
(gerados por `src/saude_mental/`) e os `.dbc` das RAAS em `caps/raw/datasus/`, baixados do FTP do DATASUS se faltarem.
