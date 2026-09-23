# CLAUDE.md

Guia para quem trabalha neste repositório, humano ou agente. O conteúdo das
skills, dos scripts e dos dados é em inglês. Este arquivo é em pt-BR, com
identificadores, comandos e caminhos no original.

## 1. Visão geral e mapa das pastas

Plugin do Claude Code com 13 skills de Instagram. Cada skill é uma pasta
`skills/ig-*/` com um `SKILL.md` (as instruções que o Claude segue) e, em
algumas, scripts Python só com stdlib que rodam de verdade. As skills escrevem;
o usuário posta. Nada aqui publica, curte, segue ou manda DM.

```
.claude-plugin/          plugin.json (versão 1.1.0) e marketplace.json
skills/
  ig-reel/               SKILL.md, hooks.json (26 fórmulas: template, exemplo, regex `match`, `needs`),
                         hookscore.py, beats.py, formula.py (regex + Jev), fit.py (veto de fórmula)
  ig-caption/            SKILL.md, caption.py (janela do feed, lint, pedidos com Jev)
  ig-human/              SKILL.md, slop.json, humanize.py, detect.py,
                         proofcheck.py (guarda de fabricação), jev.py (o único cliente TypeSafe)
  ig-viral/              SKILL.md, swipe.py (múltiplo sobre a mediana, fórmulas via formula.py)
  ig-profile/            SKILL.md, rubric.json (12 itens, 100 pontos)
  ig-audit/ ig-carousel/ ig-comment/ ig-dm/ ig-plan/ ig-reply/ ig-repurpose/ ig-story/
                         só SKILL.md
templates/voice.md       o perfil de voz que o usuário preenche
tests/                   unittest offline, fixtures e goldens com o Jev desligado
evals/                   run.py, suites/*.json (rótulos), recorded/ (respostas gravadas), REPORT.md
docs/superpowers/        spec e plano desta versão
```

## 2. Fluxo entre as skills e estado compartilhado

O estado do usuário mora fora do repositório, em `~/.claude/instagram/`:

| arquivo | quem escreve | quem lê |
| --- | --- | --- |
| `voice.md` | o usuário (a partir de `templates/voice.md`) ou o Claude, a pedido | todas as skills; `proofcheck.py` lê só *Who I am* e *Proof I can use* |
| `swipe.md` | `/ig-viral` (`swipe.py --out`) | `/ig-reel`, `/ig-plan` |
| `log.md` | `/ig-reel` (depois do "yes"), `/ig-comment` | `/ig-audit`, `/ig-comment` |
| `plan.md` | `/ig-plan` | `/ig-plan` |
| `.jev-offline` | `jev.py` (disjuntor, validade de 5 minutos) | `jev.py` |

O fluxo típico:

1. `voice.md`;
2. `/ig-viral` (o que funciona no nicho);
3. `/ig-plan` (a semana);
4. `/ig-reel`: `fit.py` → três hooks → `proofcheck.py` → `hookscore.py` → roteiro → `beats.py` → `/ig-human`;
5. `/ig-caption`;
6. o usuário posta;
7. `/ig-reply` e `/ig-dm`;
8. `/ig-audit`.

Todo texto que vai ser mostrado ao usuário passa antes por `/ig-human`, e o
passo 0 dele é o `proofcheck.py`.

## 3. Regras invioláveis

- **Nada é postado.** Toda skill termina num bloco pronto para copiar. A
  única automação aceita é a resposta por palavra-chave em DM pelas
  ferramentas oficiais do Instagram, e só depois de a pessoa comentar.
- **Portão de aprovação.** Nada vai para `log.md` nem é tratado como final
  sem o "yes" do usuário.
- **Nunca inventar.** Número, cliente, resultado, receita ou história
  compartilhada sob o nome do usuário só entram se estiverem em *Proof I can
  use*, na identidade, no que o usuário disse na sessão ou no `--source` dele.
  Se faltar, entra `{{your number}}` ou `{{client name}}` e a pergunta. O
  `proofcheck.py` faz cumprir a regra. Exemplos em SKILL.md também obedecem a
  ela: os testes em `tests/test_docs.py` conferem o exemplo do `/ig-reel`.
- **Nunca prometer previsão de views.** O `hookscore.py` separa hook ruim de
  hook real (AUC 0,83), mas não separa acerto de erro do mesmo criador (AUC
  0,56). As duas medições são da v1.0. Isso tem que continuar dito.
- **Ler, não raspar.** `/ig-viral` lê com o usuário no próprio navegador,
  nunca pede senha, nunca faz login no lugar dele e nunca roda crawler.
- **A chave da TypeSafe nunca aparece:** nem em arquivo do projeto, nem em
  saída, log, JSON, teste ou mensagem de commit.

## 4. Arquitetura Jev

O Jev (TypeSafe, modelo System One) recebe um `state` e perguntas tipadas e
devolve probabilidades calibradas: Noul para sim/não e Choice para uma opção
de um conjunto. Ele não gera texto, não conta, não faz contas e não lê datas.
Por isso, o código é dono da política, dos limiares e de toda a aritmética. O
Jev só entra onde uma regex não consegue julgar sentido.

| skill | script | perguntas ao Jev | política em código | sem Jev |
| --- | --- | --- | --- | --- |
| `/ig-human` (e `/ig-reel`, `/ig-story`, `/ig-reply`, `/ig-repurpose` com `--source`) | `ig-human/proofcheck.py` | `kind_i` (Choice: own_record, client_result, outside_fact, advice_or_opinion, hypothetical, ask_or_other); `same_i_j` e `held_i_j` (Noul) contra os 5 itens de evidência mais próximos | números ligados a um único item (ou derivados dele), nomes e handles, placeholders; UNBACKED, MISMATCH, EMBELLISHED, DERIVED e BACKED com `CLAIM`, `SAME`, `HELD` = 0,50; o Jev só amplia as alegações e nunca remove flag da L0 | só a L0: FLAGGED, UNVERIFIED ou CHECKED |
| `/ig-viral`, `/ig-audit` | `ig-reel/formula.py` (usado pelo `swipe.py`) | `formula` (Choice entre as 26 fórmulas + `none`, montado do `hooks.json`); `has_shape` (Noul); um hook por requisição, até 4 em paralelo | conta só AGREE, ou JEV com confiança ≥ `JEV_ONLY_MIN` (0,85); DISPUTED, TENTATIVE, NEW-SHAPE, NO-HOOK e READ não contam; pré-filtro de metalinguagem (`META_RE`) nem chega ao Jev | a regex do `hooks.json`, como na v1.0; uma linha com metalinguagem fica READ com qualquer motor |
| `/ig-reel` | `ig-reel/fit.py` | `multi_idea` e `fit_{id}` (26 Nouls com `name`, `template` e `needs`) numa requisição | WRITABLE ≥ 0,50, UNLOCKABLE entre 0,25 e 0,50, VETOED < 0,25; TWO IDEAS com `multi_idea` ≥ 0,70; o Jev nunca ranqueia as sobreviventes | `fit: skipped` e a regra em prosa da SKILL.md; não existe heurística de veto |
| `/ig-caption` | `ig-caption/caption.py` | `s{i}_is_ask` (Noul) e `s{i}_ask_type` (Choice de 9 tipos), por frase | pedido se `is_ask` ≥ 0,50; tipos agrupados em código; faixa de dúvida [0,35, 0,65); nunca FAIL por julgamento do Jev; a regex sempre roda e divergências viram `note` | a lista `ASKS` de regex, como na v1.0 |

As funcionalidades estão marcadas como *provisional*. Os números medidos estão
em `evals/REPORT.md`.

## 5. Contrato do motor e exit codes

Vale para todo script que usa o Jev:

- **Opções.** `--engine auto|jev|off` e a variável `IG_JEV=off` (aceita `off`,
  `0` ou `false`). A flag vence a variável, e sem nenhuma das duas o modo é
  `auto`: Jev se `TYPESAFE_API_KEY` existir.
- **Primeira linha da saída em texto:**
  - `engine: jev-1.13.0 (1 req, 2,089 tok, 0.4s)`;
  - `engine: heuristic (<motivo>[: <detalhe>])`, com os motivos `no-key`, `disabled`, `offline`
    (`offline: cached` quando o disjuntor está aberto), `rate-limited`,
    `config-error`, `bad-response` e `client-missing`.
- **`--json`.** Campos `engine` (`jev` ou `heuristic`), `engine_reason`,
  `engine_detail`, `model`, `usage` e as respostas cruas em `judgments` (onde
  houver).
- **Tudo ou nada por execução.** Um relatório nunca mistura motores. Se uma
  requisição de um lote falha, o lote inteiro cai na heurística.
- **Nunca comparar resultados entre motores.** Essa regra está escrita nas
  SKILL.md e vale também para o `swipe.md`, que registra `formula engine` e a
  versão do `hooks.json`.

| código | significado |
| --- | --- |
| 0 | ok |
| 1 | precisa de atenção: hook < 70, legenda diferente de READY, `detect` diferente de PASS, qualquer flag do `proofcheck`, id errado no `formula.py --selftest` |
| 2 | erro de uso (argparse, arquivo vazio) |
| 3 | só com `--engine jev`: o Jev não estava disponível (é o que as evals usam) |

## 6. Cliente e portabilidade

- **Um único cliente:** `skills/ig-human/jev.py`. Mudança de transporte,
  retry, TLS, modelo ou tratamento de erro é feita só nele. Os scripts não
  falam HTTP.
- **API do cliente:**
  - `mode()`, `ask()`, `ask_many()` (divide em chunks, tudo ou nada), `ask_each()` (várias requisições em paralelo, tudo ou nada);
  - `engine_line()`, `engine_fields()`;
  - `set_transport()` (as evals trocam o transporte por replay);
  - `JevUnavailable(reason, detail)`, `Result`.
- **Modelo fixado** em `MODEL = "jev-1.13.0"`. Uma resposta de outro modelo
  vira `config-error` (model mismatch), porque os limiares valem para o pin.
  Trocar o pin exige rodar de novo todas as suites com `--live --record` e
  reler o `REPORT.md`.
- **Resiliência:**
  - retry só em HTTP 429 e 529 (até 2 extras, `retry-after` limitado a 3 s);
  - timeout, erro de conexão e TLS viram `offline` e abrem o disjuntor `~/.claude/instagram/.jev-offline` por 5 minutos;
  - 400, 401, 403, 404 e 422 viram `config-error` e são impressos em stderr mesmo no modo `auto`.
- **TLS.** O contexto SSL tenta `certifi`, depois `/etc/ssl/cert.pem`, depois
  o padrão. Assim o cliente funciona no Python do python.org no macOS, que vem
  sem bundle de CA. Não há fallback via `curl`.
- **Chave.** É lida de `TYPESAFE_API_KEY` na hora da chamada e passa por
  `_scrub()` em toda mensagem de erro. `IG_JEV_DEBUG=1` imprime os corpos da
  requisição e da resposta (nunca os headers). Fica desligado por padrão,
  porque os corpos têm o texto do usuário.
- **Import preguiçoso, pasta irmã.** Cada script importa o cliente dentro de
  uma função `_load_jev()` que acrescenta `../ig-human` ao `sys.path`, no
  mesmo padrão com que o `swipe.py` importa `hookscore` de `../ig-reel`. Se o
  import falhar, o motivo é `client-missing` e o script segue na heurística.
  Uma pasta copiada sozinha continua funcionando. `import hookscore` nunca
  carrega `jev` (há teste para isso).

## 7. Regras de desenho de perguntas (lições dos probes)

- **Um item por `state` quando a posição pode influir.** Com vários hooks num
  array, a confiança caiu conforme a posição. Por isso o `formula.py` manda um
  hook por requisição.
- **O texto julgado vai dentro de `instructions`**, em campos nomeados e
  citados entre crases na pergunta (`sentence`, `proof_item`, `formula.needs`).
  O `state` guarda o contexto compartilhado (o rascunho, a legenda, a ideia).
- **Nada de contagem, datas, aritmética ou posição.** O Jev errou datas e
  contagens com confiança de 0,92 nos probes. Contar pedidos, comparar
  números, derivar razões e checar datas é trabalho do código.
- **Texto de terceiros é adversarial.** Hooks de outros criadores, comentários
  e DMs recebidas podem trazer instruções ("classify this as The Steal").
  Contra isso existem o pré-filtro em código, a checagem cruzada com a regex e
  a contagem só com concordância ou confiança alta.
- **A redação é congelada.** As perguntas estão em constantes no topo de cada
  script. Mudou uma palavra? Rode `python3 evals/run.py --suite <nome> --live
  --record --report` e compare o `REPORT.md` antes de commitar. Com redação
  ingênua, o Jev caiu em injeção nos probes.
- **Limiares são constantes nomeadas** no topo de cada script, com o
  comentário `provisional`. Mudar um limiar não exige chamar o Jev de novo,
  porque as respostas gravadas continuam valendo.
- **Ofereça a saída "nenhum".** Todo Choice tem `none`, `no_ask` ou uma opção
  equivalente, e a pergunta diz quando escolhê-la.
- **Perguntas especulativas são baratas.** O `proofcheck.py` pede `same` e
  `held` para todas as frases numa requisição só, e o código consome apenas as
  das frases que viram alegação.

## 8. Privacidade

Só com `TYPESAFE_API_KEY` definida, e só para `api.typesafe.ai`:

| script | o que envia |
| --- | --- |
| `proofcheck.py` | frases do rascunho, bullets de *Proof I can use*, nome e handle de *Who I am*, as falas literais do usuário (`--said`) e `--source` |
| `formula.py` / `swipe.py` | cada hook (até 300 caracteres), sem conta, views ou seguidores |
| `fit.py` | a ideia (até 1.500 caracteres) |
| `caption.py` | as frases da legenda, sem as linhas só de hashtags |

- **Nunca sai:** *Off limits* e o resto do `voice.md`, `log.md`, `plan.md` e
  `swipe.md`.
- **Texto de terceiros que sai:** hooks públicos de outros criadores; nome ou
  handle do destinatário quando aparece num rascunho de DM checado pelo
  `proofcheck.py`.
- **Como desligar:** `IG_JEV=off` ou `--engine off`. Sem a chave, nada é
  enviado.
- **Retenção:** a documentação da TypeSafe declara que o Jev não é treinado
  com requisições nem respostas de clientes. Retenção zero (ZDR) só existe no
  plano enterprise.
- **Toda mudança no que é enviado atualiza a seção "What leaves your machine"
  do `README.md` no mesmo commit.**

## 9. Testes e evals

```bash
python3 -m unittest discover -s tests -t .              # tudo, offline
python3 -W error::ResourceWarning -m unittest discover -s tests -t .   # como é rodado antes de commitar
UPDATE_GOLDEN=1 python3 -m unittest tests.test_golden   # regrava os goldens; leia o diff antes
python3 evals/run.py --suite all                        # replay das respostas gravadas, sem rede
python3 evals/run.py --suite formula --live             # ao vivo, sem gravar (precisa da chave)
python3 evals/run.py --suite all --live --record --report   # regrava e reescreve evals/REPORT.md
python3 skills/ig-reel/formula.py --selftest --engine jev   # os 26 exemplos, leave-one-out
```

- **Testes offline.** `tests/__init__.py` bloqueia `socket.connect`, remove
  `TYPESAFE_API_KEY` do ambiente e liga `IG_JEV=off`. Um teste que exercita o
  caminho do Jev define uma chave falsa e um transporte falso com
  `jev.set_transport()`, e restaura os dois no `tearDown`.
- **Goldens** (`tests/golden/`): saídas de `hookscore`, `beats`, `detect`,
  `caption` e `swipe` com o Jev desligado. Com `--engine off`, a saída tem que
  ser a da v1.0 mais a linha de motor e as correções da Fase 0.
- **Evals.** O replay é o padrão: chave `sha256(model + state + questions)` em
  `evals/recorded/<suite>/`. Gravação faltando faz a suite falhar e listar o
  que falta. `--live` imprime o custo (US$ 0,042 por milhão de tokens de
  entrada; as quatro suites inteiras custaram US$ 0,013).
- **Portões** (definidos em cada `evals/suites/*.json`): formula ≥ 24/26 no
  leave-one-out, 0 id errado entre os contados no stress, nenhuma armadilha
  contada; proof com recall de L0+L1 acima do de L0 e falsos positivos ≤ 0,25.
  fit e caption são só reportados. Portão que falha deixa a funcionalidade
  desligada por padrão.
- **Os sets são smoke tests, não benchmarks.** São pequenos, e a maioria dos
  rótulos foi escrita por quem construiu as funcionalidades. A regex do
  `hooks.json` foi ajustada olhando o set de stress. Diga isso sempre que
  citar um número.

## 10. Estilo

- **Só stdlib.** `certifi` é opcional e fica dentro de `try`. Nada de
  `requirements.txt`.
- **Saída pronta para copiar,** com cabeçalho, barras de `=` e `-` e um
  veredito no fim, como nos scripts existentes. Todo script tem `--json`.
- **Docstring de módulo** explicando o que o script é e o que ele *não* é,
  no tom do README: sem superlativos e com os limites ditos.
- **Mudanças aditivas nas SKILL.md.** O upstream é de outro autor, então
  acrescente seções e linhas e reescreva só o que estiver errado.
- **Números que aparecem em SKILL.md ou README** (scores, exemplos de saída)
  precisam ser a saída real dos scripts. Há testes que conferem os do
  `/ig-reel`.
- **Nomes:** `snake_case` em Python, constantes em maiúsculas no topo do
  arquivo, ids de pergunta curtos (`kind_3`, `same_3_1`, `fit_5`).

## 11. Fluxo Git

- Nunca trabalhe na `main`. Esta versão está em `feature/jev-decisions`.
- Rode `git status` e `git branch` antes de começar e `git diff` antes de cada
  commit.
- Um commit por unidade que se testa sozinha, com mensagem descritiva (o que
  mudou e por quê), sem "fix" ou "update" soltos.
- Rode a suíte inteira antes do commit, conferindo o exit code, e não o
  `tail` da saída.
- Arquivos temporários ficam fora do repositório. O `.gitignore` já cobre
  `__pycache__/` e `*.tmp`.
- `evals/recorded/` entra no git: é o que permite o replay. Regravar muda os
  arquivos, então commite as gravações junto com o `REPORT.md` que elas
  produziram.

## 12. Registro das decisões Pro × Contra

Cada ponto de decisão passou por um agente Pro (brainstorm e defesa), um
agente Contra (ataque), cegos um ao outro, e um Juiz, com cerca de 110
chamadas reais ao `jev-1.13.0`. Os detalhes estão em
`docs/superpowers/specs/2026-09-23-jev-decisions-design.md`.

| ponto de decisão | decisão | por quê |
| --- | --- | --- |
| Guarda de fabricação | implementado (`proofcheck.py`) | o código sozinho pegou 11/22 e 22/67 dos casos; o Jev pega número real ligado ao fato errado, detalhe acrescentado e familiaridade inventada em DM; ele falha em aritmética e nome inventado, por isso o código é o piso |
| Fórmula do hook | implementado (`formula.py`) | a regex nomeava 20/26 dos próprios exemplos e errava em silêncio; o Jev acertou 26/26 no leave-one-out, mas caiu em injeção com redação ingênua, daí a checagem cruzada e o pré-filtro |
| Veto de fórmula | implementado, só o veto (`fit.py`) | separa bem a fórmula que exigiria fato inventado (0,13–0,19) do encaixe real (0,93–0,95); os Choices de formato e de sticker mudavam com a redação |
| Pedidos na legenda | implementado, só os pedidos | 24/24 contra 7/24 da regex nos probes (paráfrase, citação, narrativa); a escolha entre Job A e Job B é consulta de tabela e ficou no código |
| Triagem de comentários, pitch em comentário, regras do voice.md, payoff no beats, tells parafraseados | próxima fase | o sinal é bom, mas o concorrente real é o próprio Claude e há dados de terceiros |
| Hookscore semântico, rubrica do perfil, extração no repurpose, elegibilidade no plan | adiados | não movem o AUC de 0,56, os dados eram fictícios ou o uso é raro |
| Formato e sticker, tipo de comentário, gates de DM (gatilho, tipo, recência), elogio + pitch | rejeitados | a resposta muda com a redação e com injeção, e há erros de data e contagem com confiança alta |

## 13. Checklist para adicionar um novo uso do Jev

1. **Existe um concorrente mais simples?** Regex, tabela ou o próprio Claude
   seguindo a SKILL.md. Escreva a baseline antes.
2. **Separe o julgamento da política.** O Jev responde uma pergunta estreita,
   e o código decide.
3. **Desenhe as perguntas** seguindo a seção 7 e a skill `typesafe-ai` (leia a
   documentação ao vivo em https://docs.typesafe.ai/llms.txt). Coloque a
   redação em constantes.
4. **Use o cliente existente** (`ask`, `ask_many` ou `ask_each`) com import
   preguiçoso e o contrato do motor completo: `--engine`, linha de motor,
   campos `--json`, tudo ou nada e exit 3.
5. **Defina o fallback** sem inventar heurística: ou a lógica de antes, ou
   `skipped`.
6. **Limiares** como constantes `provisional`, com faixa de dúvida quando a
   decisão muda o veredito.
7. **Testes offline** com transporte falso, cobrindo cada status, cada motivo
   de fallback, a linha de motor e o isolamento. Se a saída com `--engine off`
   mudar, atualize o golden.
8. **Suite em `evals/suites/`** com `provenance` honesta, portão definido
   antes de rodar, `--live --record --report` e as gravações commitadas.
9. **Documentação no mesmo commit:** a regra de runtime na SKILL.md, a linha
   da tabela da seção 4 e da seção 8 deste arquivo, e "What leaves your
   machine" no README.

## 14. Próxima fase e critério de entrada

Candidatos: triagem de comentários (`ig-reply/triage.py`), checagem de pitch
em comentários, as regras semânticas do `voice.md` (tópicos e promessas
proibidos), payoff por beat no `beats.py` e tells parafraseados (só
consultivos).

**Critério de entrada:** cada item só entra com uma eval que tenha **o Claude
respondendo a mesma pergunta atômica** como baseline e com rótulos que não
foram escritos por quem construiu a funcionalidade. Antes de endurecer
qualquer limiar atual ou tirar o *provisional*, é preciso coletar dados reais
rotulados por pessoas (rascunhos, hooks e legendas de criadores de verdade).
