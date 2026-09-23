# Design: decisões com Jev nas skills de Instagram

- **Data:** 2026-09-23
- **Branch:** `feature/jev-decisions`
- **Status:** aprovado em seções no chat, aguardando revisão desta spec
- **Abordagem escolhida:** A, o núcleo com evidência

## 1. Contexto e objetivo

O repositório é um plugin do Claude Code: 13 skills de Instagram (`skills/ig-*/SKILL.md`), seis scripts Python só com stdlib e três bases JSON. Hoje as decisões semânticas são tomadas de dois jeitos:

- Por **regex ou lista de palavras**, nos scripts. Isso é frágil. O classificador de fórmulas deixa 51% dos hooks reais sem nome e erra 6 dos seus 26 exemplos canônicos.
- **Pelo próprio Claude**, seguindo a prosa da SKILL.md. Aí não há calibração nem reprodutibilidade, e a regra "never fabricate" é violada no próprio exemplo do `ig-reel`.

O objetivo é colocar o **Jev** (TypeSafe, modelo System One: estado + perguntas tipadas → respostas calibradas) nos pontos de decisão em que ele mostrou ganho sobre o que existe hoje. O código continua dono da política, dos limiares e de toda a aritmética. Junto disso, este trabalho entrega um `CLAUDE.md` completo em pt-BR.

## 2. Decisões já tomadas com o usuário

| Tema | Decisão |
|---|---|
| Idioma do conteúdo | Inglês, como hoje. O Jev é mais preciso em inglês. |
| Quando o Jev roda | **Ligado por padrão sempre que `TYPESAFE_API_KEY` existir.** Sem chave, com erro de rede, TLS, 429 ou 529, o script cai na heurística atual e diz qual motor decidiu. |
| Modelo | Fixado em `jev-1.13.0`. Nunca `jev-latest`. |
| CLAUDE.md | pt-BR. Identificadores e comandos ficam no original. |
| Escopo | Abordagem A: Fase 0 + cliente único + 4 funcionalidades (`proofcheck`, `formula`, `fit` e os pedidos da legenda) + README honesto + CLAUDE.md. |

## 3. Como chegamos aqui: workflow Pro × Contra

Foram 14 pontos de decisão. Cada um passou por um agente **Pro Thinking** (brainstorm e defesa) e um agente **Contra Thinking** (ataque), cegos um ao outro, e depois por um **Juiz**. Em seguida, um **Arquiteto** sintetizou uma arquitetura e um **Contra da arquitetura** a atacou. Foram 44 agentes e cerca de 110 chamadas reais ao `jev-1.13.0`, que custaram menos de US$ 0,05.

**Ressalva que vale para todos os números abaixo:** os conjuntos foram escritos e rotulados pelos próprios agentes. São smoke tests, não benchmarks.

| Ponto de decisão | Evidência | Decisão final |
|---|---|---|
| Guarda de fabricação | O código sozinho pegou 11/22 e 22/67 dos casos. O Jev pega número real associado ao fato errado (0,03–0,09), detalhe acrescentado e familiaridade inventada em DM. Ele falha em aritmética derivada e em nome inventado, por isso o código é o piso. | **Implementar** (`proofcheck.py`) |
| Fórmula do hook (`swipe`/`audit`) | Regex: 20/26 nos canônicos e 10/26 no set de stress, com 6 nomes errados em silêncio. Jev: 26/26 (leave-one-out) e 25/26. Com redação ingênua, o Jev cai em injeção. | **Implementar** (`formula.py`) |
| Veto "dá para escrever sem inventar?" | Cost Confession deu 0,13–0,19 numa ideia sem custo, enquanto o encaixe real deu 0,93–0,95. Os Choices de formato e de sticker viram com a redação e com injeção. | **Implementar só o veto** (`fit.py`) |
| Pedidos na legenda | 24/24 contra 7/24 da regex (paráfrase, citação, narrativa). O Job A/B é consulta de tabela e fica em código. | **Implementar só os pedidos** |
| Triagem de comentários, pitch em comentário, regras do voice.md, payoff no beats, tells parafraseados | Os sinais são bons, mas o concorrente real é o Claude, e envolvem dados de terceiros. | Próxima fase (§12) |
| Hookscore semântico, rubrica do perfil, extração no repurpose | Não mexe no AUC de 0,56 (hit contra flop). Dados fictícios. Uso raro. | Adiado (§12) |
| Formato e sticker, tipo de comentário, gates de DM (gatilho, tipo, recência) | A resposta muda com a redação e com injeção. Erra datas e contagens com confiança de 0,92. | Rejeitado (§12) |

## 4. Fundação

### 4.1 Cliente único: `skills/ig-human/jev.py`

É stdlib apenas. Fica em `ig-human` porque toda skill que escreve já passa por `/ig-human`, e o `proofcheck.py` mora lá.

**API pública:**

```python
MODEL = "jev-1.13.0"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"

class JevUnavailable(Exception):
    reason: str   # no-key | disabled | offline | rate-limited | config-error | bad-response
    detail: str   # texto curto, sem a chave

def mode(cli_value=None) -> str                    # "auto" | "jev" | "off"; flag > IG_JEV > auto
def ask(state, questions, *, timeout=6.0) -> Result # Result: answers, model, usage, elapsed_s, requests
def ask_many(state, questions, *, max_tokens=48000) -> Result   # divide as perguntas em chunks; tudo ou nada
def engine_line(result=None, reason=None, detail="") -> str
```

**Transporte.** `urllib.request`, com esta ordem de contexto SSL:

1. `certifi.where()`, se o `certifi` importar;
2. `/etc/ssl/cert.pem`, se o arquivo existir;
3. o contexto padrão.

Não há fallback via `curl`. Se o TLS falhar, o erro vira `JevUnavailable("offline", "tls: <mensagem ssl>")`, com a mensagem visível.

**Resiliência:**

- Retry apenas em HTTP 429 e 529. São no máximo 2 tentativas extras, com espera de `retry-after` (limitada a 3 s) ou 0,5 s e depois 1,5 s. Se ainda falhar, o motivo é `rate-limited`.
- Timeout, erro de conexão e erro de TLS não têm retry. Viram `offline`.
- **Disjuntor.** Em `offline`, o cliente grava `~/.claude/instagram/.jev-offline` com o timestamp. Por 5 minutos, `ask()` levanta `offline (cached)` sem chamar a rede. Uma resposta bem-sucedida apaga o arquivo.
- HTTP 400 com "Unknown model", 401 e 422 viram `config-error`. A mensagem é impressa em stderr mesmo no modo `auto`, porque indica um problema de configuração e não uma queda.
- Se `response.model` for diferente de `MODEL`, o motivo é `config-error`, com o detalhe "model mismatch". Os limiares valem para o pin.
- JSON inválido ou falta de um id de pergunta em `answers` viram `bad-response`.

**Chave:**

- É lida de `os.environ["TYPESAFE_API_KEY"]` no momento da chamada e nunca guardada em variável de módulo.
- Nunca vai para argv, arquivo, log, JSON de saída ou texto de exceção. Toda mensagem de erro passa por `_scrub()`.
- `IG_JEV_DEBUG=1` imprime o corpo da requisição e da resposta em stderr, nunca os headers. Fica desligado por padrão, porque imprime texto do usuário.

**Orçamento de tokens.** `ask_many` estima os tokens como `len(json)/4`. Acima de `max_tokens`, divide as perguntas em chunks sobre o mesmo `state` e os envia em sequência. Se qualquer chunk falhar, a chamada inteira falha.

### 4.2 Portabilidade e import

- Cada script que usa o Jev importa o cliente como pasta irmã, no mesmo padrão com que `swipe.py` já importa `hookscore`:

  ```python
  HERE = os.path.dirname(os.path.abspath(__file__))
  def _load_jev():
      sys.path.insert(0, os.path.join(HERE, "..", "ig-human"))
      try:
          import jev
          return jev
      except Exception:
          return None        # engine: heuristic (client-missing)
  ```

- O import é **preguiçoso**, dentro da função que chama o Jev. Um teste garante que `import hookscore` e `hookscore.run()` não carregam `jev`.
- A instalação documentada (`cp -r skills/ig-*`) copia todas as pastas juntas. Uma pasta copiada sozinha continua funcionando, só que em modo heurístico.

### 4.3 Contrato do motor (vale para todo script que usa Jev)

- **Opções:** `--engine auto|jev|off` e a variável `IG_JEV=off` (aceita `off`, `0` ou `false`). A flag vence a variável.
- **Linha de motor.** A primeira linha da saída em texto é sempre uma destas:
  - `engine: jev-1.13.0 (1 req, 2,089 tok, 0.4s)`
  - `engine: heuristic (no-key)`, ou `disabled`, `offline`, `offline (cached)`, `rate-limited`, `config-error`, `bad-response` ou `client-missing`
- **JSON (`--json`).** Campos `engine`, `engine_reason` (null quando o Jev respondeu), `model` e `usage`, mais as probabilidades cruas em `judgments`.
- **Tudo ou nada por execução.** Um mesmo relatório nunca mistura motores.
- **Nunca comparar entre motores.** Scores e contagens de execuções com motores diferentes não se comparam. Essa regra fica escrita nas SKILL.md.

### 4.4 Exit codes (tabela única)

| Código | Significado |
|---|---|
| 0 | ok |
| 1 | precisa de atenção. É a semântica de hoje: hook < 70, legenda diferente de READY, detect diferente de PASS, e agora qualquer flag do `proofcheck` |
| 2 | erro de uso (argparse, arquivo vazio), como hoje |
| 3 | só com `--engine jev`: o Jev estava indisponível. Serve às evals |

## 5. Funcionalidade 1: `skills/ig-human/proofcheck.py` (guarda de fabricação)

**Uso:**

```
python3 proofcheck.py draft.txt --said said.txt [--source source.txt] [--voice PATH] [-o fixed.txt] [--json] [--engine ...]
```

- `--said` recebe as mensagens do próprio usuário nesta sessão, **copiadas literalmente** pelo Claude.
- `--source` recebe o ativo do próprio usuário. Só o `/ig-repurpose` usa.
- `--voice` tem como padrão `~/.claude/instagram/voice.md`.

**Evidência.** Só estas fontes contam:

- os bullets de `## Proof I can use`;
- nome e handle em `## Who I am`;
- `--said`;
- `--source`.

O relatório imprime a evidência usada. Texto de terceiros (comentários, DMs recebidas, outros falantes) **nunca** é evidência. `Off limits` e o resto do voice.md **nunca** são lidos para envio.

**Pré-processamento em código:**

- A quebra é por linha e depois por frase. Fragmentos com menos de 5 palavras se juntam à frase anterior.
- Linhas com `{{...}}` são ignoradas.
- Cada frase recebe uma shortlist dos 5 itens de evidência com maior sobreposição de palavras de conteúdo e de números normalizados.

**L0, só código, sempre roda:**

- **Conjunto de alegações.** Entram as frases com primeira pessoa ou cliente (`I, we, my, our, me, us, client, customer, student`), exceto perguntas e futuro (`I'll`, `I want`). Com Jev, também entram as frases em que `P(own_record)+P(client_result) >= 0.50`. O Jev pode ampliar esse conjunto, nunca reduzir.
- **Números.** São normalizados: dígitos, `$`, `k`, `%`, `x`, números por extenso e `twice/half/doubled/tripled`. Cada número precisa ser igual a um número de **um único** item de evidência, ou ser derivação exata de dois números **desse mesmo item**: razão, variação percentual, diferença, soma ou horas↔minutos, com tolerância de arredondamento. Se não for, o trecho vira `{{your number}}`.
- **Nomes e @handles.** Nomes são palavras capitalizadas fora do início de frase, descontando uma stoplist de plataformas, dias da semana e `I`. Nomes e handles precisam aparecer na evidência ou na identidade. Se não aparecerem, viram `{{client name}}`.
- **Offline, sem Jev.** Uma frase de primeira pessoa sem número e com menos de 2 palavras de conteúdo em comum com qualquer item de evidência recebe o status `UNVERIFIED`.

**L1, Jev, numa requisição com fan-out.** O `state` é `{"draft": "<rascunho, uma frase por linha>"}`. Cada pergunta leva seus próprios dados em `instructions` estruturadas.

- `kind_{i}` (Choice), para toda frase:
  - instructions: `{"sentence": "<frase i>", "question": "What kind of statement is `sentence`, as the creator would say it in their own Instagram post or message?"}`
  - criteria:
    - `own_record`: "States something the speaker did, saw, experienced, earned, lost or achieved, or something that happened to the speaker or their business: a result, an amount, a time, an event. This includes saying the speaker watched, read, liked or noticed a specific post, met or talked to someone, or shares friends, clients or events with the person they are writing to."
    - `client_result`: "States something that happened to, or was achieved by, a specific client, customer, student or collaborator of the speaker."
    - `outside_fact`: "States a fact or statistic about other people, a platform, a company or the world that could be checked against a source."
    - `advice_or_opinion`: "Tells the viewer what to do, or gives the speaker's belief or opinion, without stating a specific event or result."
    - `hypothetical`: "Describes an imagined, example or conditional situation, not something that happened."
    - `ask_or_other`: "A question, a call to action, a greeting, or a line that states nothing."
- `same_{i}_{j}` (Noul), para cada frase de alegação × item da shortlist:
  - instructions: `{"sentence": ..., "proof_item": ..., "question": "Does `proof_item` report the same event or result that `sentence` states?"}`
  - true: "The proof item describes the same event or result as the sentence, even if the sentence words it differently or leaves details out."
  - false: "The proof item describes a different event, client or result, or does not mention what the sentence states, even if the topic is similar."
- `held_{i}_{j}` (Noul), para os mesmos pares:
  - instructions: `{"sentence": ..., "proof_item": ..., "question": "Is everything that `sentence` states also stated in `proof_item`?"}`
  - true: "Every event, person, place, time and result that the sentence states is also stated in the proof item. Different wording, and a number written in words instead of digits, still count as stated."
  - false: "The sentence states at least one event, person, place, time or result that the proof item does not state, or states the opposite of the proof item."

**Política em código.** Constantes no topo do arquivo, provisórias: `CLAIM=0.50`, `SAME=0.50`, `HELD=0.50`, `SHORTLIST=5`.

Para cada alegação, com `best = argmax_j same_{i}_j`:

1. Se `same[best] < SAME`, o status é **UNBACKED** ("confirm or cut"). Os trechos de número ou nome recebem placeholder. Uma alegação sem número só é sinalizada, não reescrita.
2. Se `same[best] >= SAME`, mas os números do L0 não se ligam **a esse item**, o status é **MISMATCH** ("your proof says X").
3. Se `held[best] < HELD`, o status é **EMBELLISHED**: mostra a prova e pede para confirmar ou cortar. Se a única diferença for um número que o L0 validou como derivado, o status é **DERIVED** (revisão leve).
4. Nos demais casos, o status é **BACKED**, com o id da prova citado.

Regras adicionais:

- `outside_fact` com número recebe uma NOTE: "statistic: add a source or cut".
- Sem nenhuma evidência, toda alegação é UNBACKED e nenhum par é enviado.
- **Flags = união de L0 e L1. O Jev nunca remove uma flag do L0.**
- Não há faixa silenciosa: toda linha que não é BACKED aparece ao lado do rascunho.
- `-o` grava o rascunho com os placeholders do L0 aplicados só nos trechos exatos.
- Exit 1 se houver qualquer UNBACKED, MISMATCH, EMBELLISHED, UNVERIFIED ou flag de número ou nome do L0. DERIVED e NOTE aparecem no relatório, mas não mudam o exit code. Sem nada disso, exit 0.

**Fica no código:** o parse do voice.md, a quebra de frases, a shortlist, toda a extração e comparação de números, a presença de nomes, os placeholders, os limiares e os vereditos. O Jev nunca conta, nunca compara números, nunca lida com datas e nunca escreve texto.

**Integração:**

- `ig-human/SKILL.md`: vira o passo 0 da ordem de operações. O loop do `/ig-human` fica limitado a **2 rodadas**. Depois disso, o usuário decide.
- `ig-reel/SKILL.md`: os três hooks e o roteiro passam pelo `proofcheck`, e o bloco REEL READY ganha `proof: N backed, N {{…}}, N to confirm · engine <…>`.
- `ig-story/SKILL.md` e `ig-reply/SKILL.md` ganham uma linha apontando para o guard.
- O README e o template `voice.md` pedem "um fato verificável por bullet" em *Proof I can use*.

## 6. Funcionalidade 2: `skills/ig-reel/formula.py` (classificador de fórmula)

**Uso:**

```
python3 formula.py "hook" ... | --tsv FILE | --selftest   [--json] [--engine ...]
```

A função `classify_hooks(hooks, engine="auto")` é usada por `swipe.py` e pelo `ig-audit`.

**Montagem das perguntas.** Os critérios são montados em runtime a partir do `hooks.json`, com uma entrada por fórmula no formato `{"shape": template, "example": example}`, mais `none`. No `--selftest`, o próprio exemplo de cada fórmula é removido da sua opção (leave-one-out).

**State.** Um hook por requisição: `{"hook": "<linha, cortada em código a 300 caracteres>"}`. As requisições saem em paralelo, até 4 threads. Os probes mediram que, com hooks em array, a confiança cai conforme a posição.

**Perguntas:**

- `formula` (Choice):
  - instructions: `{"question": "Which hook formula does the opening line in `hook` follow?", "judge": "Judge the structure of the line, not its topic. Spoken hooks paraphrase: the wording can differ from a formula's shape as long as the structure is clearly the same.", "two_fit": "If two formulas fit, pick the one that shapes the first sentence.", "no_match": "Pick none when no formula's structure is clearly present."}`
  - `none`: "The line does not follow any formula above. Use this for greetings, introductions of what the video covers, plain statements, fragments from the middle of a conversation, and hooks built on a structure that is not listed here."
- `has_shape` (Noul): "Does the line in `hook` open with a specific claim, number, question, command, confession or story tension aimed at the viewer, rather than a greeting, an announcement of what the video will cover, or a fragment picked up from the middle of a conversation?"

**Pré-filtro anti-injeção, em código.** Se o hook contém metalinguagem de classificação (regex `\b(hook formula|formula|classif(?:y|ied|ication)|label (?:this|it) as)\b`), o Jev não é consultado. O status é `READ`, com o motivo, e o hook não é contado.

*Nota de revisão:* o desenho do juiz também comparava com os nomes das fórmulas. Isso foi descartado, porque "Nobody tells you…" é o nome da fórmula #3 e é também o próprio hook.

**Status.** R = id da regex, J = escolha do Jev, c = confiança. Constantes provisórias: `JEV_ONLY_MIN=0.85`, `NEW_SHAPE=0.60`, `NO_HOOK=0.30`.

| Status | Regra | Contado? |
|---|---|---|
| `AGREE` | R ≠ None e J == R | sim |
| `JEV` | R == None, J ≠ none e c ≥ 0,85 | sim, marcado `jev` |
| `TENTATIVE` | R == None, J ≠ none e c < 0,85. Aparece como `#J?` | não |
| `DISPUTED` | R ≠ None e J ≠ R (inclusive J == none). Listado como `regex #R / jev #J (p)` para leitura manual | não |
| `NEW-SHAPE` | R == None, J == none e has_shape ≥ 0,60 | não, listado primeiro |
| `NO-HOOK` | R == None, J == none e has_shape < 0,30 | não |
| `READ` | pré-filtro, ou has_shape entre 0,30 e 0,60 | não |

Sem Jev, o status é o de hoje: nome da regex ou `unclassified`, com `engine: heuristic (…)`.

**Integração com `swipe.py`:**

- Importa `formula.classify_hooks` pelo caminho `../ig-reel` que já usa. Se falhar, roda o `classify()` local.
- Deduplica os hooks e faz uma chamada `classify_hooks()` por execução.
- `top_formulas` conta só `AGREE` e `JEV`, e imprime quantos vieram só do Jev.
- O cabeçalho do `swipe.md` passa a registrar `formula engine: regex+jev-1.13.0` ou `regex (<motivo>)`, mais `hooks.json v<versão>`.

**Outras SKILL.md:**

- `ig-viral/SKILL.md` explica os status e manda ler à mão `DISPUTED` e `NEW-SHAPE`. Também registra que as fórmulas visuais #13, #18 e #24 não podem ser julgadas por texto.
- `ig-audit/SKILL.md`: para posts sem fórmula no `log.md`, roda `../ig-reel/formula.py` sobre as primeiras linhas transcritas e usa só os status contados.

## 7. Funcionalidade 3: `skills/ig-reel/fit.py` (veto de fórmula)

**Uso:**

```
python3 fit.py "<ideia>" [--json] [--engine ...]
```

Lê o `hooks.json` da própria pasta.

**Mudança de dados.** Cada fórmula do `hooks.json` ganha o campo `needs`: uma lista literal dos ingredientes que o template exige, cobrindo todos os placeholders. Exemplo: #1 Cost Confession precisa de "the amount one specific mistake cost".

**State.** `{"idea": "<ideia literal, cortada em código a 1.500 caracteres>"}`, com exatamente uma ideia por requisição. voice.md, swipe.md, log.md e texto de terceiros nunca vão.

**Perguntas, numa só requisição:**

- `multi_idea` (Noul):
  - pergunta: "Does the `idea` contain two or more separate points that could each be a short video on its own?"
  - true: "Two or more distinct points, such as a story and an unrelated tip, or two different topics joined together."
  - false: "One point, even if it has several steps, details or tangents that all serve it."
- `fit_{id}` (26 Nouls gerados do `hooks.json`):
  - instructions: `{"formula": {"name": ..., "template": ..., "needs": ...}, "question": "Could a true hook in the shape of `formula.template` be written using only facts stated in the `idea`, without inventing any number, amount, duration, date, event, person or quote that `formula.needs` requires?"}`
  - true: "Everything in `formula.needs` is stated in the idea or follows directly from it."
  - false: "Something in `formula.needs` is missing from the idea and would have to be made up, or the formula does not match what the idea is about."

**Política em código.** Constantes provisórias: `VETO=0.25`, `WRITABLE=0.50`, `MULTI=0.70`.

- O script imprime três listas:
  - **WRITABLE** (≥ 0,50);
  - **UNLOCKABLE** (entre 0,25 e 0,50), em que cada `needs` vira uma pergunta de uma linha para o usuário;
  - **VETOED** (< 0,25).
- Se `multi_idea` ≥ 0,70, imprime "TWO IDEAS? which one first?".
- O Claude escolhe as 3 fórmulas **só entre as WRITABLE**. O Jev nunca ranqueia as sobreviventes.
- Se houver menos de 3 WRITABLE, o Claude escreve só essas e acrescenta até 2 perguntas UNLOCKABLE à pergunta agrupada.
- Se não houver nenhuma WRITABLE, a ideia é tratada como fina. O Claude faz a pergunta agrupada da SKILL.md e roda o `fit` de novo.
- Se o usuário nomear uma fórmula vetada, a escolha dele vale, e o Claude pede o ingrediente que falta em vez de inventá-lo.

**Fallback.** O script imprime `fit: skipped (<motivo>)` e sai com exit 0 (ou 3 com `--engine jev`). Vale então a regra em prosa: "use only formulas whose `needs` are stated in the idea; otherwise ask for the missing ingredient". Não existe heurística de veto em código, e nenhuma é inventada.

**Integração.** `ig-reel/SKILL.md` roda o `fit.py` antes de escrever hooks. O REEL READY e o `log.md` registram a linha `fit:` e qualquer override de fórmula vetada.

## 8. Funcionalidade 4: pedidos (asks) em `skills/ig-caption/caption.py`

**CLI.** Ganha `--engine`. A saída ganha a linha de motor, e `--json` ganha `engine`, `engine_reason`, `judgments` e `heuristic_asks`.

**Pré-processamento em código.** A quebra de frases mantém trechos citados dentro de uma frase só, e as linhas que só têm hashtags são removidas. O state é `{"caption": "<legenda sem as linhas só de hashtags>"}`, e cada pergunta leva a sua frase dentro de `instructions`. Tudo vai numa requisição.

**Perguntas, por frase i:**

- `s{i}_is_ask` (Noul):
  - pergunta: "Does `sentence`, which is part of `caption`, ask or invite the person reading this Instagram caption to do something?"
  - true: "It asks the reader to comment, reply, answer a question, save, share, send the post to someone, tag someone, follow, DM, use the link in the bio, or swipe. An indirect pointer to a resource ('the template is in my bio') and a question the reader is meant to answer in the comments both count."
  - false: "It tells a story, explains, gives advice about the topic (even as a command, like 'raise your prices'), describes or quotes what the writer or someone else said or did, or asks a rhetorical question that the caption answers itself. Words that are only quoted, described or reported do not count."
- `s{i}_ask_type` (Choice):
  - pergunta: "Which action, if any, does `sentence` ask the reader of this Instagram caption to take?"
  - opções e descrições:
    - `comment_keyword`: "Comment one specific word or code so the writer can send something, like 'Comment CONTRACT'"
    - `comment_reply`: "Reply in the comments with an opinion, answer, choice or emoji"
    - `save`: "Save the post for later"
    - `share_or_send`: "Share the post, send it to someone, or tag someone"
    - `follow`: "Follow the account"
    - `dm`: "Send the writer a direct message"
    - `link_in_bio`: "Use a link or resource in the bio or profile"
    - `swipe`: "Swipe or tap through the post"
    - `no_ask`: "The sentence does not ask the reader to take any action"

**Política em código.** Constantes provisórias: `ASK=0.50` e a faixa de dúvida `[0.35, 0.65)`.

- A frase i é um pedido se `is_ask >= 0.50` e `ask_type != no_ask`. Se `is_ask >= 0.50` e o tipo for `no_ask`, o tipo vira `unspecified`.
- Os pedidos são agrupados por tipo em código, então repetições contam uma vez. **Nunca se pergunta "quantos" ao Jev.**
- 1 tipo → PASS, citando a frase. 0 ou 2 ou mais → WARN. Isso mantém o mapeamento de hoje.
- As frases na faixa de dúvida aparecem como "possible ask (p)". Se contá-las mudaria o status, o script imprime "borderline, decide out loud".
- A regex `ASKS` continua rodando sempre, e qualquer divergência entre ela e o Jev é impressa numa linha.
- **Um julgamento do Jev nunca gera FAIL.** Os FAILs continuam só em código, e o veredito e o exit code mantêm o mapeamento de hoje.
- A validação da palavra-chave (`comment_keyword`: um token em MAIÚSCULAS, sem espaço nem emoji) fica em código.

**Com `--engine off`:** a saída é idêntica à de hoje, exceto pela linha de motor e pela correção da Fase 0 no `CONCRETE_RE`. Um teste golden garante isso.

## 9. Fase 0: correções determinísticas (sem rede, verificadas em 2026-09-23)

| # | Arquivo | Bug verificado | Correção e teste |
|---|---|---|---|
| 1 | `ig-reel/hookscore.py` `check_frontload` | `WEAK_OPENERS` compara por prefixo: "Social…" e "Sometimes…" levam a penalidade de "so", "Justice…" a de "just" | Comparar a palavra inteira ou o bigrama inteiro. Teste com esses três hooks |
| 2 | `ig-reel/hookscore.py` `PROPER_RE` | Maiúscula depois de ponto conta como nome próprio | Excluir palavras em início de frase. Teste |
| 3 | `ig-reel/beats.py` `CONCRETE_RE` | "It works. Then everything changed." → `['Then']` | Mesma exclusão, mais os números por extenso de `hookscore.SPOKEN_NUMBERS`/`MONEY_WORDS`. Teste |
| 4 | `ig-caption/caption.py` `CONCRETE_RE` | "Happy Monday. Instagram is weird." → `['Monday','Instagram']` | Exclusão de início de frase, stoplist de plataformas e dias da semana, números por extenso. Teste |
| 5 | `ig-human/detect.py` | Não normaliza a tipografia antes das regex estruturais: "It’s not just X, it’s Y" com apóstrofo curvo não é detectado | Normalizar aspas e apóstrofos curvos numa cópia só para o scan estrutural (o FINGERPRINT continua contando no texto original). Teste |
| 6 | `ig-human/slop.json` `isnt-about` | "It's not about X. It's about Y." não casa, porque a regex só aceita "it is" | Acrescentar a variante `it'?s not about`. Teste |
| 7 | `ig-reel/hooks.json` | 6 regex não reconhecem os próprios exemplos (#7, #8, #11, #12, #14, #19) | Ajustar as regex. Teste: os 26 exemplos caem no próprio id. Negativos continuam sem classificação: "Don't steal my content, I will report you.", "Nobody tells me anything in this house lol". O set de stress dos probes não pode piorar |
| 8 | `ig-profile/rubric.json` × `SKILL.md:68` | "more than two is a menu" contra "two is already a menu" | Alinhar o `rubric.json` ao SKILL.md ("two is already a menu") |
| 9 | `ig-reel/SKILL.md:140` | O exemplo inventa "I billed four hours a week… for two years" | Trocar por um hook que a ideia sustenta ou por um pedido do número. Conferir os scores impressos contra o `hookscore` real |
| 10 | `ig-dm/SKILL.md` | "No link in message one" contradiz a entrega por palavra-chave, que é o link. "Never send the pitch in the same message as the compliment" confunde com o formato de collab | Restringir a regra do link ao warm approach. Separar elogio genérico de observação específica. Definir "trigger" |
| 11 | `ig-comment/SKILL.md` | Não tem a regra "never fabricate", e o recibo do exemplo não tem fonte | Acrescentar a regra, e deixar o exemplo citando uma linha de *Proof* |

## 10. Testes e evals

### 10.1 Testes (`python3 -m unittest discover -s tests`), offline

- **`tests/__init__.py`** troca `socket.socket.connect` por uma função que levanta exceção. Qualquer chamada real falha em alto e bom som.
- **`tests/test_jev_client.py`**, com `urlopen` mockado. Cobre:
  - parse de Noul, Choice e Score;
  - 429 seguido de 200, respeitando `retry-after` (com `sleep` patchado);
  - 529 três vezes → `rate-limited`;
  - 400 "Unknown model", 401 e 422 → `config-error` sem retry;
  - timeout → `offline` sem retry, com o disjuntor gravado e depois respeitado;
  - model mismatch, JSON inválido e id faltando;
  - `IG_JEV=off` e chave ausente, casos em que `urlopen` nunca é chamado;
  - ordem do contexto SSL;
  - **a chave nunca aparece** em stdout, stderr, exceções ou JSON.
- **Um teste por funcionalidade**, com respostas gravadas. Verifica a política em código, os status, os placeholders, o tudo ou nada e cada motivo de fallback.
- **Testes da Fase 0**, um por linha da tabela §9.
- **Golden de `--engine off`**, capturado **depois** da entrada da linha de motor, para `hookscore`, `caption`, `detect` e `swipe`.
- **Isolamento:** `import hookscore` e `hookscore.run()` não colocam `jev` em `sys.modules`.

### 10.2 Evals (`evals/run.py`)

- **Comando:** `python3 evals/run.py --suite formula|proof|fit|caption [--live [--record]]`.
- **Formato das suites.** Cada suite é `evals/suites/<nome>.json`, com itens, rótulos, métricas e `provenance` (`repo`, `probe-synthetic` ou `human-real`).
- **Replay é o padrão.** As respostas ficam em `evals/recorded/<suite>/<sha256(model+state+questions)>.json`. Se faltar alguma gravação, a eval **falha** e lista o que falta.
- **`--live`** exige a chave, imprime o custo (US$ 0,042 por Mtok de entrada) e, com `--record`, grava as respostas.
- **Seeds:**
  - `formula`: os 26 canônicos em leave-one-out, o set de stress e as armadilhas (h01, h02, h07, h12);
  - `proof`: os casos de `fabrication_pro`/`fabrication_contra` e os exemplos de `ig-reel`/`ig-dm`;
  - `fit`: as ideias de `format_pro`/`format_contra`;
  - `caption`: `labels_cap_asks.json`.

  Entram **só os rótulos**, copiados do scratchpad para `evals/suites/`, marcados `probe-synthetic, smoke not benchmark`. As respostas são regravadas ao vivo com a redação final das perguntas.
- **Portões, reportados sem prometer ganho:**
  - `formula`: Jev-only ≥ 24/26 no leave-one-out; 0 ids errados entre os contados no set de stress; nenhuma armadilha contada.
  - `proof`: o recall de L0+L1 fica acima do de L0 no seed; falsos positivos ≤ 0,25.
  - `fit`: recall de veto e taxa de falso veto, reportados.
  - `caption`: acurácia de pedido e de tipo, Jev contra regex, reportada.
  - Os resultados vão para `evals/REPORT.md`. Se um portão falhar, a funcionalidade fica desligada por padrão.

## 11. Documentação e privacidade

**README:**

- A linha "No dependencies, no network, nothing uploaded" é substituída por um parágrafo honesto.
- Nova seção **"What leaves your machine"**:

  | Script | O que envia |
  |---|---|
  | `proofcheck.py` | frases do rascunho, bullets de *Proof I can use*, suas falas literais e `--source` |
  | `formula.py`/`swipe.py` | cada hook (≤ 300 caracteres), sem conta, views ou seguidores |
  | `fit.py` | a ideia (≤ 1.500 caracteres) |
  | `caption.py` | as frases da legenda |

  - O que nunca sai: *Off limits*, o resto do voice.md, `log.md`, `plan.md` e `swipe.md`.
  - Texto de terceiros que sai: hooks públicos de outros criadores; nome ou handle do destinatário quando aparece num rascunho de DM.
  - Como desligar: `IG_JEV=off` ou `--engine off`.
  - A TypeSafe declara que não treina com requisições. Retenção zero (ZDR) só existe no plano enterprise.
- As medições antigas (0,83, 0,56, 49%) passam a dizer "measured on v1.0".
- As 4 funcionalidades aparecem como **provisional**, com os limiares iniciais e o resultado do `evals/REPORT.md`.

**SKILL.md.** Recebem as regras de runtime: motor, fallback, limite de rodadas e nunca comparar entre motores. São editadas:

- `ig-human`: passo 0 e limite de 2 rodadas;
- `ig-reel`: `fit`, `proof`, REEL READY, log e o exemplo corrigido;
- `ig-viral`: status;
- `ig-audit`: linha do `formula.py`;
- `ig-caption`: linha de motor;
- `ig-story` e `ig-reply`: ponteiro para o guard;
- as correções da Fase 0 em `ig-dm`, `ig-comment` e `ig-profile`.

**Manifestos.** `plugin.json` vai para a versão `1.1.0`, com a descrição mencionando as decisões opcionais via Jev. O autor original fica.

**`CLAUDE.md` (pt-BR), seções:**

1. Visão geral e mapa das pastas
2. Fluxo entre as skills e estado compartilhado (`~/.claude/instagram/`)
3. Regras invioláveis: nada é postado, portão de aprovação, nunca inventar, nunca prometer previsão de views
4. Arquitetura Jev: tabela skill → script → perguntas → política → fallback
5. Contrato do motor e exit codes
6. Cliente e portabilidade: editar só `ig-human/jev.py`; padrão de import
7. Regras de desenho de perguntas (lições dos probes): um item por state; texto julgado dentro de `instructions`; nada de contagem, datas, aritmética ou posição; texto de terceiros é adversarial; redação congelada, e toda mudança exige rodar a suite de novo; limiares como constantes nomeadas
8. Privacidade: o que sai e o que nunca sai; atualizar o README a cada mudança
9. Testes e evals: comandos, replay, `--live`, custo
10. Estilo: stdlib, saída pronta para copiar, `--json`, mudanças aditivas por causa do upstream
11. Fluxo Git
12. Registro das decisões Pro × Contra (a tabela da §3, com o motivo de cada uma)
13. Checklist para adicionar um novo uso do Jev
14. Próxima fase e o critério de entrada (§12)

Fatos específicos desta máquina (onde a chave é exportada, a falha de TLS do Python do python.org) aparecem de forma genérica: "o cliente trata a falta de CA no Python do python.org".

## 12. Fora de escopo

**Próxima fase.** Cada item só entra com uma eval que tenha **o Claude respondendo a mesma pergunta atômica** como baseline:

- triagem de comentários (`ig-reply/triage.py`);
- checagem de pitch em comentários;
- as regras semânticas do voice.md (Nouls de tópico e de promessa proibidos);
- o payoff por beat no `beats.py`;
- os tells parafraseados, só como consultivos.

**Adiados:**

- hookscore semântico: não move o 0,56 e o set é enviesado;
- rubrica do perfil com Jev: dados fictícios, uso raro;
- extração no `ig-repurpose`: falsos positivos em frases de enchimento, e transcrições de terceiros;
- elegibilidade por tipo de post no `ig-plan`: vira com a redação.

**Rejeitados:**

- Choice de formato e de sticker, e o gate de "ideia fina";
- Choice de tipo de comentário só pelo post;
- gates de gatilho, tipo e recência de DM: erram datas e contagens com confiança alta;
- guarda de elogio + pitch: não separa o template da própria skill de uma violação real;
- tema e tipo de post passados por Jev: melhor registrar na hora da escrita;
- o seam Noul do loop.

## 13. Riscos e perguntas abertas

- **Limiares provisórios.** Foram medidos em conjuntos pequenos e escritos pelos próprios agentes, e só uma coleta de dados reais rotulados por pessoas (fora deste escopo) justifica apertar ou promover. Mitigação: tudo marcado como *provisional* e o Jev só acrescenta flags ou WARN.
- **Deriva entre execuções.** Os probes mediram até 0,14 numa escala de 0 a 2. Mitigação: limiares com faixa de dúvida e nunca comparar entre motores.
- **Injeção em texto de terceiros** (hooks do swipe). Mitigação: pré-filtro, checagem cruzada com a regex e contagem só com concordância ou confiança ≥ 0,85.
- **Retenção de dados.** Vale verificar se o time tem DPA ou ZDR com a TypeSafe. O README não promete nada além do que a documentação diz.
- **Aposentadoria do `jev-1.13.0`.** O erro `config-error` é impresso em destaque. A troca do pin exige rodar todas as suites de novo.

## 14. Fases de implementação

Cada fase é um commit na `feature/jev-decisions`, com TDD.

0. Scaffold de `tests/` e as correções da Fase 0 (§9)
1. `ig-human/jev.py`, os helpers do contrato do motor e os testes do cliente
2. `proofcheck.py` e as SKILL.md do `ig-human`, `ig-reel` (proof), `ig-story` e `ig-reply`
3. `formula.py`, a integração com `swipe.py` e as SKILL.md do `ig-viral` e do `ig-audit`
4. `fit.py`, o campo `needs` no `hooks.json` e a SKILL.md do `ig-reel` (fit)
5. Os pedidos no `caption.py` e a SKILL.md do `ig-caption`
6. `evals/` (harness, seeds, gravação ao vivo, `REPORT.md`)
7. README, `plugin.json`, `CLAUDE.md` e a verificação final (testes, goldens, evals em replay)
