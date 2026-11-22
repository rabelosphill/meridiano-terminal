# Manual do Meridiano

Guia prático para analistas, gestores e assessores. Tudo o que está aqui funciona com o mouse **e** com o teclado.

---

## 1. Abrir o terminal

Se o servidor não estiver rodando, num terminal:

```bash
cd ~/meridiano && ./run.sh
```

Quando aparecer `Uvicorn running on http://127.0.0.1:8000`, abra **http://127.0.0.1:8000** no navegador.
Para parar: `Ctrl + C` no terminal.

Ao abrir, o Meridiano volta para **o ponto exato onde você parou** (última função, célula e rolagem). Um link
copiado da barra de endereço (`…#cmd=PETR4 B3 FIN Q&cell=3.01@2026-09-30`) abre a mesma tela e célula para
quem receber — o link não carrega dados privados (teses, listas, usuário).

---

## 2. A tela

```
┌───────────────────────────── barra de comando (Ctrl/⌘ K) ─────────────────────────────┐
├──────────────────── cabeçalho do ativo: preço, variação, mercado, feed, horários ──────────┤
│  WATCHLIST (20%)   │          ANÁLISE (56%)                    │   CONTEXTO (24%)          │
│  MINHA-MESA        │  tela da função atual (FIN, COMPARE…)     │  fonte da célula          │
│                    │                                           │  fixados (Brent, USD/BRL) │
│                    │                                           │  feeds · fita de eventos  │
├────────────────────┴───────────────────────────────────────────┴───────────────────────────┤
│ rodapé: usuário · salvar layout · 20/56/24                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Redimensionar:** arraste as divisórias entre painéis (ou foque a divisória e use ← →).
- **Recolher:** botão ‹ / › no título da watchlist ou do contexto. Clique na barra estreita para reabrir.
- **Maximizar:** botão ⤢ no título de qualquer painel; clique de novo para restaurar.
- **Salvar layout:** rodapé → *salvar layout*. **20/56/24** volta à proporção inicial.
- Em notebook (tela < 1280 px) o painel de contexto já abre recolhido.
- No **celular**, os painéis viram abas no rodapé: *Lista*, *Análise*, *Fonte/Contexto*.

---

## 3. Barra de comando

`Ctrl/⌘ + K` abre a barra de qualquer lugar. Digite e pressione **Enter**.

- Sugestões aparecem enquanto você digita (nome da empresa, nome abreviado da B3, ticker, CNPJ, ISIN ou comando). Ações
  aparecem antes de fundos.
- `↑ ↓` escolhem uma sugestão · `Tab` completa · `Enter` executa · `Esc` fecha e **devolve o foco** para onde
  você estava.
- Maiúsculas/minúsculas e acentos não importam. Comandos aceitam **português ou inglês**.
- Comando errado ou incompatível mostra o motivo e botões com alternativas válidas
  (ex.: `USDBRL FIN` → "é moeda, sem demonstrações; tente `MACRO BR PTAX`").
- `Alt + ←` (ou a seta ← ao lado da logo) volta ao comando anterior.

### Formato

```
<TICKER> [BOLSA] <FUNÇÃO> [opções]      ex.: PETR4 B3 FIN Q
<COMANDO> [argumentos]                   ex.: COMPARE PETR4:B3 VALE3:B3
```

Bolsa: `B3`, `NASDAQ`, `NYSE` (opcional se o ticker for único). Em comparações use `TICKER:BOLSA`.

### Comandos

| Comando | Para que serve | Exemplos | Também aceita |
|---|---|---|---|
| `HELP` | Catálogo pesquisável de comandos, campos, métricas e atalhos | `HELP`, `HELP margem` | AJUDA, ? |
| `MARKETS` | Monitor Brasil–EUA: ações, ADRs, índices, câmbio, juros, commodities, macro | `MARKETS BR US` | MERCADOS, MON |
| `FIND` | Busca por empresa, instrumento e listagem (inclui tickers antigos) | `FIND PETROBRAS`, `FIND 33.000.167` | BUSCAR, PROCURAR |
| `OVERVIEW` | Perfil, identificadores, listagens, paridade de ADR, cobertura, abas | `PETR4 B3 OVERVIEW`, `PBR NYSE OVERVIEW` | DES, PERFIL, RESUMO |
| `FIN` | Demonstrações com fonte por célula | `PETR4 B3 FIN Q`, `AAPL NASDAQ FIN A`, `VALE3 B3 FIN LTM CF` | FA, DEMONSTRACOES |
| `FILINGS` | Documentos divulgados (10-K/10-Q, DFP/ITR), versões e datas | `AAPL NASDAQ FILINGS` | DOCS, DOCUMENTOS |
| `COMPARE` | Comparação lado a lado, com moeda e período explícitos | `COMPARE PETR4:B3 VALE3:B3`, `COMPARE PETR4:B3 AAPL:NASDAQ CCY=USD` | COMPARAR |
| `MACRO` | Série macroeconômica com fonte, unidade e datas | `MACRO BR SELIC`, `MACRO BR IPCA`, `MACRO BR PTAX`, `MACRO US UST10Y`, `MACRO GLOBAL BRENT` | ECO |
| `WATCH` | Lista pessoal persistente | `WATCH MINHA-MESA`, `WATCH MINHA-MESA +VALE3:B3 -SPX` | LISTA |
| `THESIS` | Tese, premissas, DCF anexado e histórico de versões | `THESIS PETR4:B3` | TESE |
| `DCF` | Valuation por fluxo de caixa descontado | `PETR4 B3 DCF` | VALUATION |

**Opções do FIN:** período `A` (anual), `Q` (trimestral), `LTM` (últimos 12 meses) — também `ANUAL`, `T`,
`TRIM`, `TTM`, `U12M`. Demonstração `IS` (DRE), `BS` (balanço), `CF` (fluxo de caixa) — também `DRE`, `BP`, `DFC`.
Ex.: `PETR4 B3 FIN T DFC` = fluxo de caixa trimestral.

---

## 4. Ler uma demonstração (FIN)

Barra de ferramentas da tela:

- **DRE · Balanço · Fluxo de caixa** e **Anual · Trimestral · LTM**.
- **Consolidado · Individual** (empresas brasileiras).
- **Última versão · Como divulgado**: valor reapresentado mais recente × valor da primeira divulgação.
- **Como se sabia em [data]**: mostra **somente o que tinha sido publicado até aquela data** (útil para
  backtests e para checar o que o mercado sabia). Botão *hoje* volta ao normal.
- **Exportar CSV** (depende da sua permissão — ver seção 10).

Unidade: valores em **milhões** da moeda do emissor (R$ ou US$), indicada acima da grade. Ações em milhões;
LPA na moeda. O cabeçalho mostra o **período fiscal** (ex.: `FY2026`, `3T26`, `Q4 FY26`) e, embaixo, a **data de
encerramento**; passe o mouse para ver o intervalo corrido completo.

### O que cada célula significa

| Aparência | Significado |
|---|---|
| `1.234` | Valor **reportado** pela empresa |
| `1.234` em *itálico azul* com ƒ | **Calculado** pelo sistema (ex.: 4º trimestre = ano − 9 meses). A fórmula aparece no painel de contexto |
| `↺` no canto | **Reapresentado**: existe outra versão desse valor em documento posterior |
| `—` | **Ausente**: não divulgado (não é zero). O motivo aparece ao passar o mouse |
| `0` | **Zero** reportado pela empresa |
| `n/c` amarelo | **Não comparável**: o sistema se recusou a calcular (ex.: conta mudou de definição) |
| rótulo `livre` | Conta criada pela própria empresa (código pode mudar entre documentos) |
| número vermelho | Negativo (sempre também com o sinal −) |

Convenção: despesas e saídas de caixa aparecem **negativas** para todas as empresas, inclusive as americanas
(que divulgam despesas positivas — a inversão fica registrada na célula).

---

## 5. Investigar um valor até o documento original

1. Na grade, mova-se com as **setas** (ou clique numa célula).
2. **Enter** (ou clique): o painel **Contexto → Fonte da célula** mostra valor original, escala, moeda,
   período, escopo, conta/tag, documento, data de divulgação, localização no arquivo, transformação aplicada
   e, se houver, todas as **versões** desse número com a diferença entre elas.
3. **S** (ou `Shift + Enter`, ou duplo clique, ou *Abrir fonte*): abre o **documento original** com o valor
   destacado.
   - EUA: o 10-K da SEC, rolado até o número na tabela (`N` / `Shift + N` = próxima/anterior ocorrência).
   - Brasil: a linha exata do arquivo oficial da CVM (DFP/ITR), com conta, valor, escala e período.
   - *Abrir no regulador ↗* leva ao documento no site da SEC ou da CVM.
4. **Esc** (ou *← Voltar à célula*): fecha o documento e devolve o foco **na mesma célula**.

**Reconciliar com original** (no painel de contexto) recalcula o valor a partir do documento armazenado e
mostra se bate (✔ *Reconciliado*) ou não.

---

## 6. Navegação por teclado (resumo)

| Tecla | Ação |
|---|---|
| `Ctrl/⌘ K` | Barra de comando |
| `Enter` | Executar comando · inspecionar célula |
| `Esc` | Voltar ao foco anterior · fechar documento |
| `↑ ↓ ← →` | Percorrer células e listas |
| `Home` / `End` | Início/fim da linha (com `Ctrl/⌘`: início/fim da tabela) |
| `PgUp` / `PgDn` | Rolar o painel focado (na grade: página de linhas) |
| `S` · `Shift Enter` | Abrir a fonte da célula |
| `N` · `Shift N` | Próxima/anterior ocorrência no documento |
| `Alt 1` / `Alt 2` / `Alt 3` | Focar watchlist / análise / contexto |
| `Alt ←` | Comando anterior |

---

## 7. Cotações, mercados e feeds

O cabeçalho do ativo e as listas mostram **dois estados separados**:

- **Mercado**: *aberto*, *fechado — fora do horário*, *fechado — fim de semana*, *feriado: …* (calendário da B3 e
  da NYSE/Nasdaq).
- **Feed**: de onde vem o preço e se está funcionando:

| Selo | Significado |
|---|---|
| `SIM` / **SIMULADO** | Preço **fictício** de desenvolvimento. Ações, ADRs, índices, DI e opções estão assim nesta versão porque não há contrato com bolsa. Não use para decisão |
| `EOD` | Fim de dia de fonte oficial, com a **data de referência original** (USD/BRL = PTAX do BCB; Brent e Treasury 10Y = FRED) |
| `INT` / **FEED INTERROMPIDO** | Provedor caiu: o **último valor válido** continua na tela, com a hora em que foi observado |
| `ATR` | Sem atualização há mais de 30 s |
| 🔒 | Você não tem permissão para esse feed |

Horários: o cabeçalho mostra a hora da observação **no fuso da bolsa** e **no seu fuso**, além dos relógios de São
Paulo, Nova York e local.

**Painel Contexto → Fixados:** Brent, USD/BRL e Treasury 10Y ficam **fixos** (não mudam quando você troca de
ativo). A linha *grupo A* segue o ativo que você está analisando. Clicar num item da watchlist troca o ativo do
grupo A mantendo a função atual (se você está no FIN da PETR4 e clica em AAPL, abre o FIN da AAPL).

**Fita:** eventos de preço e de estado dos feeds. *Pausar* congela a lista; enquanto pausada (ou se você rolar
para baixo), as novidades viram um contador — clique em *N novidades — ir para o mais recente*. As atualizações
nunca mudam sua rolagem, seleção ou foco.

**Testar uma queda de provedor:** Contexto → Feeds → `SIM_DEV` → *interromper* (e depois *restaurar*).

---

## 8. Análise

### OVERVIEW
Abas: Resumo, Negócio, Demonstrações, Caixa, Dívida, Estimativas, Valuation, Pares, Acionistas, Eventos, Opções,
Documentos, Tese. Abas **riscadas** estão desativadas — passe o mouse para ver o que falta para habilitar
(normalmente um contrato de dados). No Resumo:

- **Listagens** com vigência (tickers antigos continuam encontrando o mesmo ativo: `FB` → `META`).
- **Paridade ADR** (ex.: PBR): preço local × ações por ADR ÷ USD/BRL = preço implícito; prêmio/desconto; horário
  da B3, de NY e a data da PTAX.
- **Pacote setorial** (aba Negócio): métricas priorizadas para o setor e quais dependem de dados ainda não ligados.
- **Pares** (aba Pares): edite a lista (`VALE3:B3 AAPL:NASDAQ`), *Salvar pares* e *Comparar com pares*.

### COMPARE
Linhas: receita, crescimento, margens, EBIT, lucro, caixa operacional, capex, FCF, dívida líquida, ROE. Botões
**Nativa · BRL · USD** convertem: fluxos pela **PTAX média** do período, saldos pela **PTAX de fechamento** — a
taxa usada aparece na última linha. Cada empresa mantém seu exercício fiscal, com datas explícitas (a Apple fecha
o ano em setembro). Limitações (ex.: denominador negativo) aparecem em amarelo.

### MACRO
Valor atual, unidade, data de referência, data de publicação, fonte, regra de publicação, gráfico e tabela.
*Como se sabia em* mostra a série como era conhecida naquela data. `ausente` ≠ zero.

### DCF
Abre com premissas **tiradas do último exercício** (receita, margem, alíquota, capex, D&A, dívida líquida,
ações). Campos com **\*** são **premissas suas** (WACC, g, crescimento, capital de giro) — os valores iniciais
são apenas ponto de partida editável.

- Edite e pressione **Enter** ou *Calcular*.
- Resultado: valor por ação, EV, ponte EV → equity, projeção ano a ano, **matriz WACC × g**, **cenários**
  pessimista/base/otimista.
- Informe um **preço** para o **DCF reverso** (crescimento implícito).
- O sistema recusa WACC ≤ g e moeda/base (nominal/real) diferentes entre fluxo e WACC.
- *Restaurar padrões* desfaz suas edições. As premissas ficam salvas por ativo.

### THESIS (tese)
Título, posição (Comprado/Neutro/Vendido), texto, tabela de premissas e *DCF da tese* → *Anexar à tese*.
**Salvar nova versão** grava uma versão imutável com **autor e horário**. No histórico, **voltar ao ponto**
reabre a demonstração e a célula que você estava analisando quando salvou. Teses são privadas por usuário.

### WATCH (watchlist)
`WATCH MINHA-MESA` abre a lista; adicione com o campo `TICKER:BOLSA` ou pelo comando
`WATCH MINHA-MESA +VALE3:B3`; remova com *remover* ou `-TICKER`. A lista do painel esquerdo é a MINHA-MESA.

---

## 9. Dados e atualização

| Dado | Fonte | Frequência |
|---|---|---|
| Apple: demonstrações e 10-K | SEC EDGAR | a cada filing |
| Petrobras e Vale: DFP e ITR | CVM Dados Abertos | a cada entrega à CVM (arquivos atualizados semanalmente) |
| Selic, IPCA, PTAX | Banco Central (SGS) | diária / mensal |
| Brent, Treasury 10Y | FRED | diária, com defasagem |

**Atualização automática:** notícias a cada 30 min, preços/séries às 07:00 e 20:30, CVM aos domingos 09:00 (veja o
README, seção "Atualização automática", para acompanhar em `logs/update.log`, rodar na hora ou desligar).

Para atualizar manualmente, com o servidor parado ou rodando, num terminal na pasta do projeto:

```bash
.venv/bin/python -m backend.worker ingest all --mode auto
```

`auto` busca nas fontes e, sem internet, usa o **snapshot** guardado em `data/snapshot` (dados reais com data e
origem). Rodar de novo não duplica nada; valores revisados entram como **nova versão**. Ver o que aconteceu:

```bash
.venv/bin/python -m backend.worker status
```

Se você rodou a ingestão com o servidor aberto, recarregue a página (as telas ficam em cache por até 5 minutos).

---

## 10. Usuários e permissões

O seletor **Usuário** no rodapé simula perfis (nesta versão não há login real):

| Usuário | Perfil | Pode exportar |
|---|---|---|
| Ana Lima | analista | fundamentos SEC/CVM e macro BCB |
| Paulo Reis | gestor | tudo |
| Bia Souza | assessora | só macro BCB; não vê cotações simuladas |
| Admin | administrador | tudo |

A permissão é verificada **no servidor**: uma exportação negada retorna erro mesmo chamando a API diretamente,
e a tentativa fica registrada. Watchlist, teses, pares e layout são separados por usuário.

---

## 11. Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `zsh: no such file or directory: ./run.sh` | Você não está na pasta do projeto: `cd ~/meridiano && ./run.sh` |
| `address already in use` / porta 8000 ocupada | Já há um servidor rodando — use-o, ou pare-o (`Ctrl + C` no terminal dele) |
| Tela vazia ou erro ao abrir | Confira se o terminal mostra `Uvicorn running…` e recarregue a página |
| Célula `—` onde esperava número | Passe o mouse: é ausência real ou trimestre não isolável (motivo explicado) |
| `n/c` | A conta mudou de definição entre documentos; veja o motivo no painel de contexto |
| Preço não muda | Mercado fechado não afeta o feed simulado; verifique se o feed `SIM_DEV` está *interrompido* |
| *Sem permissão* ao exportar | Troque de usuário no rodapé (ver seção 10) |

---

## 12. Gráfico (CHART)

`PETR4 B3 CHART 1D 2Y` — o **1º argumento é a duração do candle** (`5MIN`, `1D`, `1W`, `1M`) e o **2º é a janela inicial**
(`3M`, `6M`, `YTD`, `1Y`, `2Y`, `5Y`, `MAX`). Barra superior: intervalo, janela, tipo (candles, OHLC, linha, área),
Linear/Log, Ajustado/Bruto, **Estudos ▾**, benchmark (`vs BOVA11`), Eventos, Alertas, ↶ Visão, Desenhos e **Salvar análise**.

- **Mouse:** roda = zoom no ponto do cursor · arrastar = mover · **Shift + arrastar** = ampliar o intervalo selecionado ·
  duplo clique = voltar à janela padrão · ↶ Visão (ou `Backspace`) = visão anterior.
- **Teclado** (clique no gráfico antes): `←/→` andam um candle · `+/−` zoom · `Delete` apaga o desenho selecionado · `Esc` cancela a ferramenta.
- **Linha de inspeção** (acima do gráfico): data, abertura, máxima, mínima, fechamento, volume, variação e o valor de cada
  estudo no candle apontado ("aquec." = ainda dentro do aquecimento).
- **Estudos:** clique em *+ nome* para adicionar; edite os parâmetros ao lado; a descrição traz fórmula e convenção. Os valores
  são calculados sobre todo o histórico, então aproximar o zoom não muda o RSI nem as médias.
- **Eventos** (círculos sob os candles): R = resultado, D = demonstração (DFP/ITR/10-K), $ = proventos, N = comunicado,
  M = macro. O círculo fica na **1ª sessão em que a informação pôde ser negociada**; clique para ver o instante real de
  publicação e a fonte no painel direito.
- **Desenhos:** escolha a ferramenta à esquerda e clique no gráfico (tendência/retângulo/Fibonacci/medição: 2 cliques;
  canal: 3; horizontal/nota: 1). Clique num desenho para selecioná-lo e arraste as alças; 🔒 bloqueia, ● oculta, × exclui.
  Desenhos ficam salvos por usuário, ativo e base de preço (ajustada/bruta).
- **Alertas:** escolha a regra (rompimento de máxima/mínima de N sessões, cruzamento de preço/média, RSI, volume relativo),
  o modo (fechamento confirmado ou intrabar) e a política (1 vez por barra, só a 1ª vez, toda ocorrência). A condição
  matemática aparece por extenso e os disparos históricos são listados.
- **Salvar análise** grava uma versão da tese com o candle, os estudos e os eventos daquele dia; em `THESIS`, *voltar ao
  ponto* reabre o gráfico exatamente nesse candle.
- Ações americanas: o gráfico mostra "indisponível" até existir uma fonte licenciada de preços (`TIINGO_API_KEY`).

## 13. Notícias (NEWS) e faixa do rodapé

`NEWS WORLD` (Principais do Dia), `NEWS LIVE` (Ao Vivo, cronológico), `NEWS BR`, `NEWS US`, `NEWS BRIDGE` (Ponte
Brasil–EUA), `NEWS WATCH` (sua watchlist), `NEWS PETR4:B3` (do ativo). Cada linha mostra horário (ou "(dia)" quando a fonte
só informa a data), veículo, tipo (comunicado oficial, documento regulatório, banco central…), selo **material** e os
ativos ligados com a natureza do vínculo (direto, setor, macro). Clique para ver a evidência à direita, com instante de
publicação em ET e BRT, licença, link para o original e **Ver reação no gráfico**, que abre o ativo na 1ª sessão negociável.
Se você estiver lendo mais abaixo, manchetes novas aparecem como contador ("N novas manchetes") em vez de empurrar a lista.

A **faixa** no rodapé mostra uma manchete por vez a cada 8 s: ‹ anterior, ❚❚ pausa, › próxima, *contínuo* (rolagem; desativada
se o sistema pedir movimento reduzido). O catálogo no fim da aba NEWS mostra o que está integrado e o que depende de contrato.

## 14. Eventos, valuation e pares

- `PETR4 B3 EVENTS` — lista de resultados, demonstrações, comunicados materiais e proventos com publicação × 1ª sessão
  negociável; clique numa linha para abrir o gráfico naquele candle.
- `PETR4 B3 VALUE` — P/L, EV/EBIT e P/VP com o fechamento oficial da B3 e fundamentos LTM (alertas quando o denominador não
  tem significado) + DCF completo.
- `PETR4 B3 PEERS` — edite o grupo de pares e compare.

## 15. Rastreador (SCAN)

`SCAN BR` abre com o exemplo reproduzível (volume financeiro médio de 20 sessões > R$ 10 mi, fechamento acima da média de
200 e retorno de preço em 63 sessões acima do Ibovespa/BOVA11). Edite filtros, data de corte e benchmark e clique *Rodar*.
O topo mostra a data de corte, a moeda, o universo, os aprovados, os reprovados e os **excluídos com o motivo** (histórico
insuficiente, sem negócio na data, provável evento societário não ajustado). Cada aprovado mostra *por que entrou*.
Clique num ativo para abrir o gráfico; `Alt ←` volta ao rastreador com os filtros intactos. *Salvar consulta* guarda a regra.

## 16. Layouts e alto contraste

No rodapé, **Layouts…** aplica os prontos (Visão Geral, Gráfico, Balanço, Notícias, Mesa Brasil–EUA) ou os seus; *salvar
layout…* grava painéis, comando e o estado do gráfico (ativo, intervalo, janela, estudos, benchmark, desenhos, candle).
**alto contraste** aumenta o contraste de cores e bordas (fica salvo).

---

## 17. Limites desta versão

- Cotações intradiárias de ações, ADRs, índices, DI e opções são **simuladas** (o fechamento diário da B3 é oficial). Consenso, notícias, acionistas e cadeia de
  opções exigem contrato e não aparecem.
- Cobertura de fundamentos: **Apple** (SEC) e **todas as companhias abertas brasileiras com ação na B3** (CVM). Fundos e
  ETFs têm só cotação. Ações americanas além da Apple precisam ser cadastradas.
- Data de divulgação da CVM tem precisão de **dia**.
- Login, renda fixa analítica, opções, carteira e execução ficam para próximas entregas.
