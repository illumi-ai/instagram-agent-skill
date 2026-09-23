# Decisões com Jev nas skills de Instagram: plano de implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar este plano tarefa por tarefa. Os passos usam checkbox (`- [ ]`).

**Objetivo:** colocar o Jev (`jev-1.13.0`) em quatro pontos de decisão das skills (guarda de fabricação, fórmula do hook, veto de fórmula e pedidos da legenda), com o código dono da política, fallback heurístico sempre disponível, as 11 correções da Fase 0, testes offline, evals com replay e um `CLAUDE.md` completo em pt-BR.

**Arquitetura:** um cliente único só com stdlib (`skills/ig-human/jev.py`) com transporte plugável, disjuntor e contrato de motor. Cada script faz import preguiçoso do cliente como pasta irmã e cai na heurística quando o Jev está indisponível. As evals trocam o transporte por replay/gravação e usam o mesmo código de produção.

**Tech stack:** Python 3 só com stdlib (`certifi` opcional), `unittest`, HTTP via `urllib.request`, API `POST https://api.typesafe.ai/v1/systemone`.

**Spec:** `docs/superpowers/specs/2026-09-23-jev-decisions-design.md` (quem executa lê a spec e este plano juntos).

## Restrições globais

- Só stdlib. `certifi` pode ser importado dentro de `try`. Nenhuma dependência nova no repositório.
- Modelo fixado: `MODEL = "jev-1.13.0"`. Nunca `jev-latest`.
- `TYPESAFE_API_KEY` é lida só no momento da chamada. Nunca é impressa nem gravada, e nunca aparece em exceção, JSON ou log.
- Conteúdo das skills e dos scripts em inglês. `CLAUDE.md` em pt-BR, com identificadores e comandos no original.
- Linha de motor, sempre a primeira da saída em texto: `engine: jev-1.13.0 (1 req, 2,089 tok, 0.4s)` ou `engine: heuristic (<reason>[: <detail>])`.
- Motivos válidos: `no-key`, `disabled`, `offline`, `rate-limited`, `config-error`, `bad-response`, `client-missing`.
- Exit codes: 0 ok; 1 precisa de atenção; 2 erro de uso; 3 só com `--engine jev` e Jev indisponível.
- O Jev só acrescenta flags ou WARN. Nunca remove uma flag do código e nunca gera FAIL.
- Um item por state quando o julgamento depende da posição. Texto julgado vai dentro de `instructions`.
- Limiares são constantes nomeadas no topo de cada script e marcadas `provisional`.
- Comando de testes, sempre na raiz do repositório: `python3 -m unittest discover -s tests -t .`
- Branch: `feature/jev-decisions`. Um commit por tarefa, depois de `git diff`. A mensagem termina com `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Mudanças aditivas nas SKILL.md, por causa do upstream: acrescentar seções e linhas, reescrever só o que a Fase 0 manda corrigir.

## Mapa de arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `tests/__init__.py` | criar | guarda de socket: qualquer `connect` real levanta exceção |
| `tests/support.py` | criar | caminhos, `load(script)`, `run_cli()` com env sem chave, `FakeTransport` |
| `tests/fixtures/*.txt` | criar | entradas dos goldens |
| `tests/golden/*.txt` | criar | saídas congeladas com `--engine off` |
| `tests/test_phase0.py` | criar | um teste por correção da Fase 0 |
| `tests/test_golden.py` | criar | goldens de `hookscore`, `beats`, `detect`, `caption` e `swipe` |
| `tests/test_jev_client.py` | criar | cliente: parse, retry, disjuntor, erros, segredo |
| `tests/test_proofcheck.py` | criar | L0, L1, política, CLI |
| `tests/test_formula.py` | criar | perguntas, status, pré-filtro, integração com o swipe |
| `tests/test_fit.py` | criar | `needs`, perguntas, listas, fallback |
| `tests/test_caption_asks.py` | criar | frases, política de pedidos, divergência, keyword |
| `tests/test_evals.py` | criar | replay, chave de gravação, falta de gravação |
| `skills/ig-human/jev.py` | criar | cliente único e contrato do motor |
| `skills/ig-human/proofcheck.py` | criar | guarda de fabricação |
| `skills/ig-reel/formula.py` | criar | classificador de fórmula (regex + Jev) |
| `skills/ig-reel/fit.py` | criar | veto de fórmula |
| `skills/ig-reel/hookscore.py` | alterar | Fase 0 #1 e #2 |
| `skills/ig-reel/beats.py` | alterar | Fase 0 #3 |
| `skills/ig-reel/hooks.json` | alterar | Fase 0 #7 e o campo `needs` |
| `skills/ig-caption/caption.py` | alterar | Fase 0 #4 e os pedidos com Jev |
| `skills/ig-human/detect.py` | alterar | Fase 0 #5 |
| `skills/ig-human/slop.json` | alterar | Fase 0 #6 |
| `skills/ig-viral/swipe.py` | alterar | usar `formula.classify_hooks` |
| `skills/ig-profile/rubric.json` | alterar | Fase 0 #8 |
| `skills/*/SKILL.md` | alterar | regras de runtime e as correções da Fase 0 |
| `templates/voice.md` | alterar | "um fato verificável por bullet" |
| `evals/run.py`, `evals/suites/*.json`, `evals/recorded/`, `evals/REPORT.md` | criar | harness e resultados |
| `README.md`, `.claude-plugin/plugin.json`, `CLAUDE.md` | alterar/criar | documentação |

---

### Tarefa 1: scaffold de testes e correções da Fase 0 nos scripts (#1 a #6)

**Arquivos:**
- Criar: `tests/__init__.py`, `tests/support.py`, `tests/test_phase0.py`
- Alterar: `skills/ig-reel/hookscore.py`, `skills/ig-reel/beats.py`, `skills/ig-caption/caption.py`, `skills/ig-human/detect.py`, `skills/ig-human/slop.json`

**Interfaces:**
- Produz: `tests.support.load(name) -> module` (importa `skills/*/<name>.py` pelo nome), `tests.support.run_cli(script_rel, args, stdin=None, env_extra=None) -> CompletedProcess` (env sem `TYPESAFE_API_KEY` e com `IG_JEV=off`), `tests.support.SKILLS`, `tests.support.ROOT`.
- Produz: `hookscore.proper_nouns(text) -> list[str]`, `hookscore.sentence_starts(text) -> set[int]`, `beats.concrete_markers(text) -> list[str]`, `caption.concrete_markers(text) -> list[str]`, `detect.normalize_quotes(text) -> str`.

- [ ] **Passo 1: criar a guarda de socket e o suporte**

`tests/__init__.py`:

```python
"""Test package. Every test runs offline: a real socket connect raises."""
import socket


class NetworkBlocked(RuntimeError):
    pass


def _blocked(*args, **kwargs):
    raise NetworkBlocked("tests must not touch the network")


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
```

`tests/support.py`:

```python
import importlib.util
import os
import subprocess
import sys

import tests  # noqa: F401  (installs the socket guard)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
SCRIPTS = {
    "hookscore": "ig-reel", "beats": "ig-reel", "formula": "ig-reel", "fit": "ig-reel",
    "caption": "ig-caption", "detect": "ig-human", "humanize": "ig-human",
    "jev": "ig-human", "proofcheck": "ig-human", "swipe": "ig-viral",
}


def load(name):
    """Import skills/<folder>/<name>.py once, with its folder on sys.path."""
    if name in sys.modules:
        return sys.modules[name]
    folder = os.path.join(SKILLS, SCRIPTS[name])
    if folder not in sys.path:
        sys.path.insert(0, folder)
    spec = importlib.util.spec_from_file_location(name, os.path.join(folder, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def clean_env(extra=None):
    env = {k: v for k, v in os.environ.items() if k not in ("TYPESAFE_API_KEY", "IG_JEV_DEBUG")}
    env["IG_JEV"] = "off"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra or {})
    return env


def run_cli(script_rel, args, stdin=None, env_extra=None):
    return subprocess.run([sys.executable, os.path.join(SKILLS, script_rel)] + list(args),
                          input=stdin, capture_output=True, text=True,
                          env=clean_env(env_extra), cwd=ROOT)
```

- [ ] **Passo 2: escrever os testes da Fase 0 que falham**

`tests/test_phase0.py`:

```python
import json
import os
import re
import unittest

from tests.support import SKILLS, load


class HookscoreFrontload(unittest.TestCase):
    """#1 WEAK_OPENERS matched by prefix: 'Social' took the 'so' penalty."""

    def test_prefix_words_are_not_weak_openers(self):
        hs = load("hookscore")
        for hook in ["Social proof is the only thing that sells a retainer.",
                     "Sometimes the cheapest client costs the most.",
                     "Justice for the freelancers who never invoice on time."]:
            _, detail = hs.check_frontload(hook)
            self.assertNotIn("weak opener", detail, hook)

    def test_real_weak_openers_still_penalised(self):
        hs = load("hookscore")
        for hook in ["So today I want to talk about pricing.",
                     "Just a quick one about invoices.",
                     "I want to show you my desk setup."]:
            _, detail = hs.check_frontload(hook)
            self.assertIn("weak opener", detail, hook)


class HookscoreProper(unittest.TestCase):
    """#2 a capital after a full stop was counted as a proper noun."""

    def test_sentence_start_is_not_a_name(self):
        hs = load("hookscore")
        self.assertEqual(hs.proper_nouns("It works. Then everything changed."), [])

    def test_mid_sentence_name_counts(self):
        hs = load("hookscore")
        self.assertEqual(hs.proper_nouns("I asked Dana for the invoice."), ["Dana"])

    def test_specificity_ignores_sentence_starts(self):
        hs = load("hookscore")
        score, detail = hs.check_specificity("It works. Then everything changed.")
        self.assertEqual(score, 15.0, detail)


class BeatsConcrete(unittest.TestCase):
    """#3 beats counted 'Then' as concrete and missed spoken numbers."""

    def test_sentence_start_not_concrete(self):
        beats = load("beats")
        self.assertEqual(beats.concrete_markers("It works. Then everything changed."), [])

    def test_spoken_numbers_are_concrete(self):
        beats = load("beats")
        self.assertIn("five", beats.concrete_markers("Proposals used to take me five hours."))

    def test_analyse_uses_the_fixed_counter(self):
        beats = load("beats")
        a = beats.analyse("It works. Then everything changed.\nTwenty grand, gone.")
        self.assertEqual([b["concrete"] for b in a["beats"]], [0, 2])


class CaptionConcrete(unittest.TestCase):
    """#4 caption counted 'Monday' and 'Instagram' as concrete."""

    def test_weekday_platform_and_sentence_start_excluded(self):
        cap = load("caption")
        self.assertEqual(cap.concrete_markers("Happy Monday. Instagram is weird."), [])

    def test_real_markers_kept(self):
        cap = load("caption")
        found = cap.concrete_markers("I charged $400 for my first logo and Dana paid twenty grand.")
        self.assertIn("$4", found[0])
        self.assertIn("Dana", found)
        self.assertIn("twenty", found)

    def test_hook_is_concrete_check_uses_it(self):
        cap = load("caption")
        a = cap.analyse("Happy Monday. Instagram is weird.\n\nSave this.")
        check = next(c for c in a["checks"] if c["check"] == "HOOK IS CONCRETE")
        self.assertEqual(check["status"], "WARN")


class DetectTypography(unittest.TestCase):
    """#5 curly apostrophes hid structural tells from detect.py."""

    def test_curly_not_just_is_detected(self):
        det = load("detect")
        lex = json.load(open(os.path.join(SKILLS, "ig-human", "slop.json"), encoding="utf-8"))
        text = ("It’s not just a template, it’s a system. " * 1
                + "I wrote it for my studio and we use it on every proposal we send out "
                  "to clients who want a fixed price and a clear scope.")
        _, detail = det.check_voice(text, lex)
        self.assertIn("not-just", detail)

    def test_fingerprint_still_counts_curly(self):
        det = load("detect")
        _, detail = det.check_fingerprint("It’s fine.")
        self.assertIn("1 curly quote", detail)


class SlopIsntAbout(unittest.TestCase):
    """#6 'It's not about X. It's about Y.' was not matched."""

    def test_variants(self):
        lex = json.load(open(os.path.join(SKILLS, "ig-human", "slop.json"), encoding="utf-8"))
        rx = re.compile(next(s["regex"] for s in lex["structures"] if s["id"] == "isnt-about"),
                        re.MULTILINE)
        for text in ["It's not about the money. It's about respect.",
                     "Its not about followers. It's about buyers.",
                     "This isn't about hashtags. It's about hooks.",
                     "It is not about volume. It's about fit."]:
            self.assertTrue(rx.search(text), text)
        self.assertFalse(rx.search("It's about time we talked about pricing."))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Passo 3: rodar e ver falhar**

Rodar: `python3 -m unittest tests.test_phase0 -v`
Esperado: FAIL/ERROR em `proper_nouns`, `concrete_markers` (não existem), no `weak opener` de "Social…", no curly e no `isnt-about`.

- [ ] **Passo 4: implementar #1 e #2 em `hookscore.py`**

Trocar `PROPER_RE` e a checagem de opener:

```python
CAP_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")


def sentence_starts(text):
    """Character offsets where a sentence begins: the start, and after . ! ? or a newline."""
    starts = {0}
    for m in re.finditer(r"(?:[.!?]+[\"'”’)]*\s+|\n\s*)", text):
        starts.add(m.end())
    # a leading quote or bracket does not move the start of the sentence
    return starts | {s + 1 for s in starts if s < len(text) and text[s] in "\"'“‘("}


def proper_nouns(text):
    """Capitalised words that are not the first word of a sentence."""
    starts = sentence_starts(text)
    return [m.group(0) for m in CAP_RE.finditer(text) if m.start() not in starts]
```

Em `check_specificity`: `propers = set(proper_nouns(text))`.

Em `check_frontload`, comparar a palavra inteira ou o bigrama inteiro:

```python
    for weak in WEAK_OPENERS:
        parts = weak.split()
        if low[:len(parts)] == parts:
            penalty, hit_opener = 30, weak
            break
```

e, no laço do payload, trocar `(i and PROPER_RE.match(w[i]))` por `w[i] in names`, com `names = set(proper_nouns(text))` calculado antes do laço (tokens de `words()` já vêm sem vírgula de milhar, e nome próprio não tem vírgula).

- [ ] **Passo 5: implementar #3 em `beats.py`**

```python
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hookscore import MONEY_WORDS, SPOKEN_NUMBERS, proper_nouns  # noqa: E402

DIGIT_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,.]*\b")


def concrete_markers(text):
    """Numbers, spoken numbers and names that are not the first word of a sentence."""
    found = [m.group(0) for m in DIGIT_RE.finditer(text)]
    found += proper_nouns(text)
    found += [w for w in (x.lower().strip("'’") for x in words(text))
              if w in SPOKEN_NUMBERS or w in MONEY_WORDS]
    return found
```

Em `analyse`: `"concrete": len(concrete_markers(text))`. Remover `CONCRETE_RE`. `import os` no topo.

- [ ] **Passo 6: implementar #4 em `caption.py`**

`caption.py` precisa rodar sozinho, então as listas ficam locais:

```python
SPOKEN_NUMBERS = {
    "zero", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "fifteen", "twenty", "thirty", "forty", "fifty",
    "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million",
    "billion", "dozen", "half", "twice", "triple",
}
NOT_NAMES = {
    "instagram", "insta", "reels", "reel", "stories", "threads", "facebook", "tiktok",
    "youtube", "linkedin", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "today", "tomorrow", "yesterday",
}
DIGIT_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,.]*\b")
CAP_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
WORD_RE = re.compile(r"[A-Za-z']+")


def _sentence_starts(text):
    starts = {0}
    for m in re.finditer(r"(?:[.!?]+[\"'”’)]*\s+|\n\s*)", text):
        starts.add(m.end())
    return starts | {s + 1 for s in starts if s < len(text) and text[s] in "\"'“‘("}


def concrete_markers(text):
    starts = _sentence_starts(text)
    found = [m.group(0) for m in DIGIT_RE.finditer(text)]
    found += [m.group(0) for m in CAP_RE.finditer(text)
              if m.start() not in starts and m.group(0).lower() not in NOT_NAMES]
    found += [w for w in (x.lower() for x in WORD_RE.findall(text)) if w in SPOKEN_NUMBERS]
    return found
```

A checagem `HOOK IS CONCRETE` passa a usar `markers = concrete_markers(window)`: status `PASS if markers else WARN`, detalhe com `len(markers)`. Remover `CONCRETE_RE`.

- [ ] **Passo 7: implementar #5 em `detect.py`**

```python
QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "′": "'"})


def normalize_quotes(text):
    """Straight quotes, for the structural scan only. FINGERPRINT still reads the original."""
    return text.translate(QUOTES)
```

Em `check_voice`, logo no início: `text = normalize_quotes(text)`. `check_fingerprint` continua recebendo o texto original.

- [ ] **Passo 8: implementar #6 em `slop.json`**

Trocar a regex de `isnt-about` por:

```
(?i)\b(?:(?:this|it) is(?:n'?t| not)|it'?s not|this'?s not) about [^.!?\n]{2,60}[.!,] it'?s about\b
```

- [ ] **Passo 9: rodar os testes**

Rodar: `python3 -m unittest tests.test_phase0 -v`
Esperado: todos PASS.

- [ ] **Passo 10: commit**

```bash
git add tests/__init__.py tests/support.py tests/test_phase0.py skills/ig-reel/hookscore.py skills/ig-reel/beats.py skills/ig-caption/caption.py skills/ig-human/detect.py skills/ig-human/slop.json
git commit -m "Fix whole-word openers, sentence-start names, spoken numbers and curly-quote tells"
```

---

### Tarefa 2: regex do `hooks.json` (Fase 0 #7)

**Arquivos:**
- Alterar: `skills/ig-reel/hooks.json` (`match` de #2, #3, #7, #8, #9, #11, #12, #14, #19; `version` vai para `1.1`)
- Criar: `tests/test_hooks_regex.py`

**Interfaces:**
- Consome: `swipe.load_formulas(path)` e `swipe.classify(hook, formulas)` (sem mudança).
- Produz: `hooks.json` com os 26 exemplos classificados no próprio id.

- [ ] **Passo 1: medir a linha de base do set de stress**

Rodar, antes de mexer, o regex atual nos 26 hooks do set de stress (lista no Passo 2) e anotar quantos acertam: esse é o piso ("o set de stress não pode piorar").

- [ ] **Passo 2: escrever o teste que falha**

`tests/test_hooks_regex.py`:

```python
import json
import os
import unittest

from tests.support import SKILLS, load

HOOKS = os.path.join(SKILLS, "ig-reel", "hooks.json")

# The probe stress set (probe-synthetic, smoke not benchmark). Gold is a formula
# name, several names joined by "|", or "none".
STRESS = [
    ("never in a million years did i think this reel would pay my rent", "none"),
    ("please tell me i'm not the only one who rewrites a caption nine times", "none"),
    ("3 years ago i was sleeping on my sister's couch with $400 to my name", "none"),
    ("everyone says you need to post every day. everyone is wrong.", "Contrarian Flip|Permission"),
    ("is it just me or does nobody talk about how lonely freelancing gets", "Nobody Tells You"),
    ("stop scrolling if you're a wedding photographer", "The Callout"),
    ("if you've been posting for six months and still have under 1,000 followers, the next 30 seconds are for you", "If This, Then Watch"),
    ("hey guys welcome back to my channel", "none"),
    ("in this video i'm going to show you my morning routine", "none"),
    ("yeah so what we found was that most of the people who came in were already", "none"),
    ("you're pricing your services wrong and honestly it's not your fault", "Wrong Way, Right Way"),
    ("i worked at a big four accounting firm for eight years and this is what they don't tell clients", "Insider Leak"),
    ("five apps i use every single day to run my business, and the last one is the one nobody uses", "Numbered With A Favourite"),
    ("i don't have time to post every day. okay, then post twice a week and do this instead", "The Objection"),
    ("real estate agents, this is the listing video you've been avoiding", "The Callout"),
    ("the tax deadline is april 15th, do this before then or you'll pay a penalty", "The Deadline"),
    ("what's the best camera for beginners? i get asked this every week", "The Verbatim Question"),
    ("this $9 app replaced my $300 a month virtual assistant", "The Replacement"),
    ("nobody tells you that the first client is the hardest one to find", "Nobody Tells You"),
    ("we tested carousels against reels for 90 days, and it wasn't close", "Head To Head|The Receipt"),
    ("the fastest way to lose a client is to answer every email in five minutes", "The Superlative"),
    ("my biggest mistake as a new photographer cost me $6,000", "Cost Confession"),
    ("watch what happens when i put my competitor's bio into chatgpt", "Cold Open Demo"),
    ("so i just got banned from instagram for 30 days", "none"),
    ("if i had to start a coaching business from zero tomorrow, here's exactly what i'd do", "none"),
    ("proposals used to eat my whole friday. now they take me twenty minutes", "Time Collapse"),
]
BASELINE_STRESS_CORRECT = None   # filled in from Passo 1 before the regex edits
NEGATIVES = ["Don't steal my content, I will report you.",
             "Nobody tells me anything in this house lol"]


def correct(name, gold):
    return (name == "unclassified" and gold == "none") or name in gold.split("|")


class HooksRegex(unittest.TestCase):
    def setUp(self):
        self.swipe = load("swipe")
        self.formulas = self.swipe.load_formulas(HOOKS)
        self.data = json.load(open(HOOKS, encoding="utf-8"))

    def test_every_example_classifies_as_itself(self):
        for h in self.data["hooks"]:
            fid, _ = self.swipe.classify(h["example"], self.formulas)
            self.assertEqual(fid, h["id"], h["example"])

    def test_negatives_stay_unclassified(self):
        for text in NEGATIVES:
            self.assertEqual(self.swipe.classify(text, self.formulas), (None, "unclassified"), text)

    def test_stress_set_does_not_get_worse(self):
        hits = sum(correct(self.swipe.classify(h, self.formulas)[1], g) for h, g in STRESS)
        self.assertGreaterEqual(hits, BASELINE_STRESS_CORRECT)

    def test_version_bumped(self):
        self.assertEqual(self.data["version"], "1.1")
```

Preencher `BASELINE_STRESS_CORRECT` com o número do Passo 1.

- [ ] **Passo 3: rodar e ver falhar**

Rodar: `python3 -m unittest tests.test_hooks_regex -v`
Esperado: FAIL em #7, #8, #11, #12, #14, #19, nos dois negativos e na versão.

- [ ] **Passo 4: ajustar as regex**

Regras de desenho (casar a estrutura, não palavras soltas):

- #2 Negative Command: o verbo deixa de ser opcional. `^\s*(?:stop|quit)\s+\w+ing\b|^\s*(?:never|don'?t|dont|do not)\s+(?:do|be|make|buy|use|start|say|post|send|take|charge|pay|sign|hire|give|offer|work|price|discount|reply|answer|write|run)\b|\bquit your\b|[.!]\s*(?:do|post|use|send|try)\b[^.!?]*\binstead\b`
- #3 Nobody Tells You: exigir o complemento. `\b(?:nobody|no one)\s+(?:ever\s+)?(?:tells?|told|talks?|talked|says?|said|mentions?|teach(?:es)?)\s+(?:you|about|that|how|why|what|this)\b|\bwhat (?:nobody|no one) (?:tells|says)\b`
- #7 Wrong Way: `\b(?:big(?:gest)?|common|the) mistake\b|\bmistake (?:that|people|i)\b|\byou'?(?:re| are)\s+\w+ing\b[^.!?]{0,40}\bwrong\b|\bdoing (?:it|this) wrong\b|\bnot your fault\b`
- #8 Insider Leak: anos por extenso. `\bi (?:spent|worked|ran|was|have been)\b[^.!?]*\b(?:\d+|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty)\s*\+?\s*years?\b|\bwe never (?:told|said|showed|put)\b|\bnobody (?:puts|tells you about)\b|\bi (?:sell|sold|run)\b[^.!?]*\$\s?\d`
- #9 The Steal: não casar "don't steal". `^\s*steal\b|(?<!n't )(?<!not )(?<!dont )\bsteal (?:this|these|my)\b|^\s*(?:here'?s|this is) (?:the|my) (?:exact|literal)\b`
- #11 Numbered: `^\s*(?:here are\s+)?(?:\d+|three|four|five|six|seven|eight|nine|ten)\s+\w+(?:\s+\w+)?\s+(?:that|to|you|i|every|for|which)\b|\bnumber (?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b|\bthe last one is\b`
- #12 The Objection: aspas retas ou curvas e fechamento antes de "Fine". `^\s*[\"“'][^\"”]{5,120}[\"”][,.]?\s*(?:fine|ok|okay|sure|right|here)\b|^\s*i (?:don'?t|can'?t) \w+[^.!?]{0,60}[.!?]\s*(?:okay|ok|fine),?\s*(?:then|here)\b`
- #14 The Callout: grupo com qualificador antes dos dois-pontos. `^\s*(?:every|all|any)\s+\w+|^\s*[a-z][\w ]{2,28}(?:ers|ists|ors|ants|agents|owners|coaches)\b[^.!?:,]{0,40}[,:]|^\s*for (?:viewers|people|anyone|those|everyone)\b|^\s*(?:attention|listen up)\b|^\s*stop scrolling if you'?re\b`
- #19 The Deadline: `\bbefore (?:you|it|they|the|then)\b|\bchanges? (?:on|the second|when|the moment)\b|\bby 20\d\d\b|\bdeadline is\b`

Depois de cada ajuste, rodar o teste. Se uma regex nova fizer outro exemplo cair num id anterior da `classify_order`, apertar a regex nova, sem mexer na ordem. `version` vai para `"1.1"`.

- [ ] **Passo 5: rodar os testes**

Rodar: `python3 -m unittest tests.test_hooks_regex tests.test_phase0 -v`
Esperado: todos PASS.

- [ ] **Passo 6: commit**

```bash
git add skills/ig-reel/hooks.json tests/test_hooks_regex.py
git commit -m "Make every hook formula regex recognise its own example"
```

---

### Tarefa 3: correções da Fase 0 nas SKILL.md e nos dados (#8 a #11)

**Arquivos:**
- Alterar: `skills/ig-profile/rubric.json`, `skills/ig-reel/SKILL.md` (exemplo em ~140), `skills/ig-dm/SKILL.md`, `skills/ig-comment/SKILL.md`
- Criar: `tests/test_docs.py`

- [ ] **Passo 1: teste que falha**

`tests/test_docs.py`:

```python
import json
import os
import re
import unittest

from tests.support import SKILLS, load


def read(rel):
    return open(os.path.join(SKILLS, rel), encoding="utf-8").read()


class Phase0Docs(unittest.TestCase):
    def test_rubric_matches_skill_on_link_menu(self):
        rubric = read("ig-profile/rubric.json")
        self.assertIn("two is already a menu", rubric)
        self.assertNotIn("more than two is a menu", rubric)

    def test_reel_example_invents_nothing(self):
        text = read("ig-reel/SKILL.md")
        self.assertNotIn("I billed four hours a week", text)

    def test_reel_example_scores_are_real(self):
        hs = load("hookscore")
        text = read("ig-reel/SKILL.md")
        block = text.split("## Example", 1)[1]
        rows = re.findall(r"^\s+(\d+)\s+(STRONG|OK|WEAK)\s+#\d+\s+[^\"]+\"([^\"]+)\"", block, re.M)
        self.assertTrue(rows)
        for score, verdict, hook in rows:
            _, overall, real_verdict, _ = hs.run(hook)
            self.assertEqual(int(score), round(overall), hook)
            self.assertEqual(verdict, real_verdict, hook)

    def test_dm_link_rule_is_scoped_to_warm_approach(self):
        text = read("ig-dm/SKILL.md")
        self.assertNotIn("- Never send the pitch in the same message as the compliment.", text)
        self.assertIn("The keyword delivery is the exception", text)
        self.assertIn("A trigger is", text)

    def test_comment_has_never_fabricate(self):
        text = read("ig-comment/SKILL.md")
        self.assertIn("Never fabricate", text)
        self.assertIn("Proof I can use", text)
```

- [ ] **Passo 2: rodar e ver falhar**

Rodar: `python3 -m unittest tests.test_docs -v`
Esperado: 5 FAIL.

- [ ] **Passo 3: aplicar as correções**

- `rubric.json`: "Up to five links are allowed; two is already a menu, and a menu converts worse than a door."
- `ig-reel/SKILL.md`: trocar o hook #1 inventado por um pedido do número. O bloco fica com os três hooks que a ideia sustenta (#5 Time Collapse, #9 The Steal e #17 Head To Head ou outro que só use "5 hours", "20 minutes" e "one template"). Os scores e vereditos impressos saem de `python3 hookscore.py --hook "<hook>"`. Acrescentar abaixo do bloco: `#1 Cost Confession needs the cost of the old way. Ask: "what did the five-hour version cost you, in hours or money?" Do not write it until the user answers.`
- `ig-dm/SKILL.md`:
  - na lista do warm approach: "**No link and no calendar in message one** of a warm approach. The keyword delivery is the exception: there the link is the thing they asked for, so it goes first."
  - na seção do trigger: "A trigger is something the recipient did that the user can point to: a keyword they commented, a story they replied to, a post they published this week."
  - em Never: trocar a linha do pitch por "Never put the pitch in a message whose only other content is a generic compliment. A specific observation of their work, as in the collab pitch, is not a compliment, it is the reason for the message."
- `ig-comment/SKILL.md`, em Rules: "**Never fabricate.** A receipt or a datum is only something from `## Proof I can use` in `~/.claude/instagram/voice.md` or something the user said in this session. If there is none, pick another type." No exemplo `[6 · Receipt]`, acrescentar a linha `(from Proof I can use: "Raised prices 40% in March 2024, lost one client.")`.

- [ ] **Passo 4: rodar os testes**

Rodar: `python3 -m unittest tests.test_docs -v`
Esperado: PASS.

- [ ] **Passo 5: commit**

```bash
git add skills/ig-profile/rubric.json skills/ig-reel/SKILL.md skills/ig-dm/SKILL.md skills/ig-comment/SKILL.md tests/test_docs.py
git commit -m "Align profile rubric, remove the invented reel example and tighten DM and comment rules"
```

---

### Tarefa 4: cliente `skills/ig-human/jev.py`

**Arquivos:**
- Criar: `skills/ig-human/jev.py`, `tests/test_jev_client.py`

**Interfaces:**
- Produz:

```python
MODEL = "jev-1.13.0"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
CIRCUIT = os.path.expanduser("~/.claude/instagram/.jev-offline")
CIRCUIT_TTL = 300
class JevUnavailable(Exception): reason: str; detail: str
@dataclass class Result: answers: dict; model: str; usage: dict; elapsed_s: float; requests: int
def mode(cli_value=None) -> str
def ask(state, questions, *, engine=None, timeout=6.0) -> Result
def ask_many(state, questions, *, engine=None, max_tokens=48000, timeout=6.0) -> Result
def ask_each(items, *, engine=None, max_workers=4, timeout=6.0) -> list[Result]   # items: [(state, questions)]
def engine_line(result=None, reason=None, detail="") -> str
def engine_fields(result=None, error=None) -> dict   # engine, engine_reason, engine_detail, model, usage
def set_transport(fn) -> previous_fn                # fn(body: dict, timeout: float) -> dict
```

- [ ] **Passo 1: testes que falham**

`tests/test_jev_client.py` cobre (com `urllib.request.urlopen` mockado via `unittest.mock.patch.object(jev, "urlopen")` e `jev.time.sleep` mockado):

```python
import io
import json
import os
import socket
import ssl
import tempfile
import unittest
import urllib.error
from unittest import mock

from tests.support import load

jev = load("jev")
KEY = "ts_test_SECRET_1234567890"


def ok_body(answers, model="jev-1.13.0", usage=None):
    return json.dumps({"model": model, "answers": answers,
                       "usage": usage or {"input_tokens": 100, "output_tokens": 10}}).encode()


class FakeResp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def http_error(code, body=b"{}", headers=None):
    return urllib.error.HTTPError(jev.ENDPOINT, code, "err", headers or {}, io.BytesIO(body))


Q = {"a": {"type": "noul", "instructions": "Is it?"},
     "b": {"type": "choice", "instructions": "Which?", "criteria": {"x": "X", "y": "Y"}}}
A = {"a": {"type": "noul", "noul": 0.9},
     "b": {"type": "choice", "choice": "x", "probabilities": {"x": 0.8, "y": 0.2}, "confidence": 0.7}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": KEY}, clear=False),
            mock.patch.object(jev, "CIRCUIT", os.path.join(self.tmp.name, ".jev-offline")),
            mock.patch.object(jev.time, "sleep"),
        ]
        for p in self.patches:
            p.start()
        os.environ.pop("IG_JEV", None)
        os.environ.pop("IG_JEV_DEBUG", None)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()


class Parse(Base):
    def test_noul_and_choice(self):
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body(A))) as u:
            r = jev.ask({"s": 1}, Q)
        self.assertEqual(r.answers["a"]["noul"], 0.9)
        self.assertEqual(r.answers["b"]["choice"], "x")
        self.assertEqual(r.requests, 1)
        body = json.loads(u.call_args[0][0].data)
        self.assertEqual(body["model"], "jev-1.13.0")

    def test_score(self):
        ans = {"s": {"type": "score", "score": 1.2, "legend": {"0": "a"}, "probabilities": {"0": 1.0},
                     "confidence": 0.5}}
        q = {"s": {"type": "score", "instructions": "How?", "criteria": ["a", "b"]}}
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body(ans))):
            self.assertEqual(jev.ask("x", q).answers["s"]["score"], 1.2)


class Retry(Base):
    def test_429_then_200_respects_retry_after(self):
        seq = [http_error(429, headers={"retry-after": "2"}), FakeResp(ok_body(A))]
        with mock.patch.object(jev, "urlopen", side_effect=seq):
            jev.ask("s", Q)
        jev.time.sleep.assert_called_once_with(2.0)

    def test_retry_after_is_capped(self):
        seq = [http_error(429, headers={"retry-after": "60"}), FakeResp(ok_body(A))]
        with mock.patch.object(jev, "urlopen", side_effect=seq):
            jev.ask("s", Q)
        jev.time.sleep.assert_called_once_with(3.0)

    def test_529_three_times_is_rate_limited(self):
        with mock.patch.object(jev, "urlopen", side_effect=[http_error(529)] * 3) as u:
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertEqual(cm.exception.reason, "rate-limited")
        self.assertEqual(u.call_count, 3)
        self.assertEqual([c.args[0] for c in jev.time.sleep.call_args_list], [0.5, 1.5])


class ConfigErrors(Base):
    def test_unknown_model_401_422_are_config_errors_without_retry(self):
        for err in [http_error(400, b'{"error":"Unknown model"}'), http_error(401), http_error(422)]:
            with mock.patch.object(jev, "urlopen", side_effect=[err]) as u, \
                    mock.patch("sys.stderr", new_callable=io.StringIO) as err_out:
                with self.assertRaises(jev.JevUnavailable) as cm:
                    jev.ask("s", Q)
            self.assertEqual(cm.exception.reason, "config-error")
            self.assertEqual(u.call_count, 1)
            self.assertIn("config", err_out.getvalue())

    def test_model_mismatch(self):
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body(A, model="jev-1.14.0"))):
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertEqual(cm.exception.reason, "config-error")
        self.assertIn("model mismatch", cm.exception.detail)


class BadResponse(Base):
    def test_invalid_json(self):
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(b"not json")):
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertEqual(cm.exception.reason, "bad-response")

    def test_missing_answer_id(self):
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body({"a": A["a"]}))):
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertEqual(cm.exception.reason, "bad-response")


class Offline(Base):
    def test_timeout_is_offline_and_trips_the_circuit(self):
        with mock.patch.object(jev, "urlopen", side_effect=[socket.timeout("timed out")]) as u:
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertEqual(cm.exception.reason, "offline")
        self.assertEqual(u.call_count, 1)
        self.assertTrue(os.path.exists(jev.CIRCUIT))
        with mock.patch.object(jev, "urlopen") as u2:
            with self.assertRaises(jev.JevUnavailable) as cm2:
                jev.ask("s", Q)
        u2.assert_not_called()
        self.assertEqual((cm2.exception.reason, cm2.exception.detail), ("offline", "cached"))

    def test_expired_circuit_is_ignored_and_success_clears_it(self):
        open(jev.CIRCUIT, "w").write("0")
        with mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body(A))):
            jev.ask("s", Q)
        self.assertFalse(os.path.exists(jev.CIRCUIT))

    def test_tls_error_detail(self):
        err = urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED"))
        with mock.patch.object(jev, "urlopen", side_effect=[err]):
            with self.assertRaises(jev.JevUnavailable) as cm:
                jev.ask("s", Q)
        self.assertTrue(cm.exception.detail.startswith("tls:"))


class Switches(Base):
    def test_ig_jev_off_and_missing_key_never_call_urlopen(self):
        with mock.patch.object(jev, "urlopen") as u:
            with mock.patch.dict(os.environ, {"IG_JEV": "off"}):
                with self.assertRaises(jev.JevUnavailable) as cm:
                    jev.ask("s", Q)
                self.assertEqual(cm.exception.reason, "disabled")
            with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": ""}):
                with self.assertRaises(jev.JevUnavailable) as cm:
                    jev.ask("s", Q)
                self.assertEqual(cm.exception.reason, "no-key")
        u.assert_not_called()

    def test_mode_precedence(self):
        with mock.patch.dict(os.environ, {"IG_JEV": "false"}):
            self.assertEqual(jev.mode(), "off")
            self.assertEqual(jev.mode("jev"), "jev")
        self.assertEqual(jev.mode(), "auto")


class SSLOrder(Base):
    def test_certifi_first_then_system_bundle(self):
        with mock.patch.object(jev.ssl, "create_default_context") as cdc:
            jev._ssl_context()
        cafile = cdc.call_args.kwargs.get("cafile")
        self.assertTrue(cafile is None or cafile.endswith((".pem", "cert.pem")))


class Secret(Base):
    def test_key_never_leaks(self):
        errors = [http_error(401, b'{"error":"bad key ' + KEY.encode() + b'"}'),
                  urllib.error.URLError("proxy said Bearer " + KEY)]
        for err in errors:
            with mock.patch.object(jev, "urlopen", side_effect=[err]), \
                    mock.patch("sys.stderr", new_callable=io.StringIO) as e, \
                    mock.patch("sys.stdout", new_callable=io.StringIO) as o:
                with self.assertRaises(jev.JevUnavailable) as cm:
                    jev.ask("s", Q)
            blob = str(cm.exception) + cm.exception.detail + e.getvalue() + o.getvalue()
            blob += json.dumps(jev.engine_fields(error=cm.exception))
            self.assertNotIn(KEY, blob)

    def test_debug_prints_bodies_not_headers(self):
        with mock.patch.dict(os.environ, {"IG_JEV_DEBUG": "1"}), \
                mock.patch.object(jev, "urlopen", return_value=FakeResp(ok_body(A))), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as e:
            jev.ask("s", Q)
        self.assertIn('"questions"', e.getvalue())
        self.assertNotIn(KEY, e.getvalue())
        self.assertNotIn("Authorization", e.getvalue())


class Chunking(Base):
    def test_ask_many_splits_and_merges(self):
        qs = {f"q{i}": {"type": "noul", "instructions": "x" * 400} for i in range(10)}
        def reply(req, timeout, context):
            body = json.loads(req.data)
            return FakeResp(ok_body({k: {"type": "noul", "noul": 0.5} for k in body["questions"]}))
        with mock.patch.object(jev, "urlopen", side_effect=reply) as u:
            r = jev.ask_many("s", qs, max_tokens=400)
        self.assertGreater(u.call_count, 1)
        self.assertEqual(set(r.answers), set(qs))
        self.assertEqual(r.requests, u.call_count)

    def test_ask_many_all_or_nothing(self):
        qs = {f"q{i}": {"type": "noul", "instructions": "x" * 400} for i in range(10)}
        seq = [FakeResp(ok_body({"q0": {"type": "noul", "noul": 0.5}})), http_error(401)]
        with mock.patch.object(jev, "urlopen", side_effect=seq * 10), \
                mock.patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(jev.JevUnavailable):
                jev.ask_many("s", qs, max_tokens=400)


class EngineLine(unittest.TestCase):
    def test_formats(self):
        r = jev.Result(answers={}, model="jev-1.13.0",
                       usage={"input_tokens": 2000, "output_tokens": 89}, elapsed_s=0.41, requests=1)
        self.assertEqual(jev.engine_line(r), "engine: jev-1.13.0 (1 req, 2,089 tok, 0.4s)")
        self.assertEqual(jev.engine_line(reason="no-key"), "engine: heuristic (no-key)")
        self.assertEqual(jev.engine_line(reason="offline", detail="cached"),
                         "engine: heuristic (offline: cached)")
```

- [ ] **Passo 2: rodar e ver falhar**

Rodar: `python3 -m unittest tests.test_jev_client -v`
Esperado: ERROR, `jev.py` não existe.

- [ ] **Passo 3: implementar `jev.py`**

Pontos obrigatórios da implementação (a spec §4.1 é a referência):

```python
"""jev.py - the one client for TypeSafe's Jev model. Standard library only. ..."""
import json, os, re, ssl, sys, time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL = "jev-1.13.0"            # pinned: every threshold in this pack was measured on it
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
CIRCUIT = os.path.expanduser("~/.claude/instagram/.jev-offline")
CIRCUIT_TTL = 300
RETRY_STATUSES = (429, 529)
BACKOFF = (0.5, 1.5)
MAX_RETRY_AFTER = 3.0
CONFIG_STATUSES = (400, 401, 403, 404, 422)


class JevUnavailable(Exception):
    def __init__(self, reason, detail=""):
        self.reason = reason
        self.detail = _scrub(str(detail))[:300]
        super().__init__(self.reason + (": " + self.detail if self.detail else ""))


@dataclass
class Result:
    answers: dict
    model: str = MODEL
    usage: dict = field(default_factory=dict)
    elapsed_s: float = 0.0
    requests: int = 1


def _scrub(text):
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if key and len(key) >= 8:
        text = text.replace(key, "[redacted]")
    return re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", text)


def mode(cli_value=None):
    if cli_value in ("auto", "jev", "off"):
        return cli_value
    return "off" if os.environ.get("IG_JEV", "").strip().lower() in ("off", "0", "false") else "auto"


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    if os.path.exists("/etc/ssl/cert.pem"):
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()
```

- Disjuntor: `_circuit_open()` lê o timestamp do arquivo (float) e devolve `time.time() - ts < CIRCUIT_TTL`. Arquivo ilegível conta como fechado. `_trip()` cria o diretório e grava `time.time()`. `_reset()` remove o arquivo, ignorando erros.
- `_http_post(body, timeout)`: lê a chave (`no-key` se vazia), checa o disjuntor (`offline`/`cached`), monta `Request(ENDPOINT, data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})` e faz até 3 tentativas:
  - `HTTPError` com código em `RETRY_STATUSES`: se ainda houver tentativa, espera `min(float(retry-after), MAX_RETRY_AFTER)` ou `BACKOFF[attempt]` e tenta de novo. Senão, levanta `rate-limited` com o detalhe `HTTP <code>`.
  - `HTTPError` com código em `CONFIG_STATUSES`: lê até 300 bytes do corpo, imprime em stderr `jev: config error (HTTP <code>: <corpo scrubbed>). Check TYPESAFE_API_KEY and the pinned model jev-1.13.0.` e levanta `config-error`.
  - Outro `HTTPError` (5xx): `offline`, detalhe `HTTP <code>`, sem disjuntor.
  - `URLError` cuja `reason` é `ssl.SSLError`, ou `ssl.SSLError` direto: `_trip()` e `offline` com o detalhe `tls: <msg>`.
  - `URLError`, `socket.timeout`, `TimeoutError`, `ConnectionError` e `OSError`: `_trip()` e `offline`.
  - Sucesso: `_reset()`, com o parse do JSON (`bad-response` se inválido) e o corpo devolvido.
- `TRANSPORT = _http_post` e `set_transport(fn)` troca o transporte e devolve o anterior.
- `ask(state, questions, *, engine=None, timeout=6.0)`:
  - `mode(engine) == "off"` levanta `disabled`;
  - o corpo é `{"model": MODEL, "state": state, "questions": questions}`;
  - com `IG_JEV_DEBUG=1`, o corpo vai para stderr (`jev debug request: ...`);
  - chama `TRANSPORT(body, timeout)` e mede o tempo;
  - com debug, a resposta também vai para stderr;
  - `resp.get("model") != MODEL` levanta `config-error` com `model mismatch: got <x>` e imprime em stderr;
  - `answers` precisa ser dict e conter todo id de `questions`, senão `bad-response`;
  - devolve `Result`.
- `ask_many`:
  - estima `len(json.dumps({"state": state, "questions": q})) / 4`;
  - se couber em `max_tokens`, é um `ask`;
  - se não couber, divide gulosamente: adiciona perguntas enquanto `len(json(state)) + len(json(chunk))` fica abaixo de `max_tokens*4`, e toda pergunta sozinha forma um chunk;
  - chama `ask` em sequência, junta `answers`, soma `usage` (input e output), `elapsed_s` e `requests`;
  - qualquer exceção se propaga.
- `ask_each(items, ...)`:
  - usa `ThreadPoolExecutor(max_workers)` com `ask` em cada item;
  - se algum levantar, levanta a primeira `JevUnavailable` (tudo ou nada);
  - devolve a lista de `Result` na ordem.
- `engine_line(result=None, reason=None, detail="")`:
  - com `result`: `f"engine: {result.model} ({result.requests} req, {tok:,} tok, {result.elapsed_s:.1f}s)"`, em que `tok` é input + output;
  - sem `result`: `f"engine: heuristic ({reason}" + (f": {detail}" if detail else "") + ")"`.
- `engine_fields(result=None, error=None)`:
  - com `result`: `{"engine": "jev", "engine_reason": None, "engine_detail": None, "model": result.model, "usage": {...}, "requests": n}`;
  - sem `result`: `{"engine": "heuristic", "engine_reason": error.reason, "engine_detail": error.detail, "model": None, "usage": None}`.
- Aceitar `error` como string (motivo) para o caso `client-missing`.

- [ ] **Passo 4: rodar os testes**

Rodar: `python3 -m unittest tests.test_jev_client -v`
Esperado: PASS.

- [ ] **Passo 5: smoke ao vivo (manual, fora da suíte)**

Rodar uma vez, sem imprimir a chave:

```bash
python3 -c "import sys; sys.path.insert(0,'skills/ig-human'); import jev; r=jev.ask('Help! Payouts failing for 3 days.', {'u': {'type':'noul','instructions':'Does this convey urgency?'}}); print(jev.engine_line(r), r.answers)"
```

Esperado: `engine: jev-1.13.0 (1 req, …)` e um Noul acima de 0,5. Se falhar em TLS, conferir a ordem do contexto SSL.

- [ ] **Passo 6: commit**

```bash
git add skills/ig-human/jev.py tests/test_jev_client.py
git commit -m "Add the single Jev client with retry, circuit breaker and engine contract"
```

---

### Tarefa 5: `proofcheck.py`, L0 (só código)

**Arquivos:**
- Criar: `skills/ig-human/proofcheck.py`, `tests/test_proofcheck.py` (parte L0)

**Interfaces:**
- Produz:

```python
CLAIM = 0.50; SAME = 0.50; HELD = 0.50; SHORTLIST = 5          # provisional
@dataclass class Item: id: str; text: str; kind: str   # kind: proof | identity | said | source
@dataclass class Num: value: float; unit: str; text: str; start: int; end: int
def parse_voice(text) -> tuple[list[Item], set[str]]            # evidence items, identity names/handles
def load_evidence(voice_text, said_text, source_text) -> tuple[list[Item], set[str]]
def split_sentences(draft) -> list[dict]      # {"i", "line", "text", "start", "end"}, skipping {{...}} lines
def numbers(text) -> list[Num]
def bind_number(num, item_numbers) -> str | None   # "direct" | "derived" | None
def bindings(claim_nums, items) -> dict            # item.id -> {"direct": [...], "derived": [...]}; plus "unbound": [...]
def is_l0_claim(text) -> bool
def names(text) -> list[tuple[str,int,int]]        # capitalised non-initial words minus stoplist
def handles(text) -> list[tuple[str,int,int]]
def shortlist(sentence, items, k=SHORTLIST) -> list[Item]
def l0(draft, items, identity) -> list[dict]       # per sentence: claim, nums, flags, bindings, shortlist, unverified
def apply_placeholders(draft, report) -> str
```

- [ ] **Passo 1: testes L0 que falham**

```python
import unittest

from tests.support import load

pc = load("proofcheck")

VOICE = """## Who I am

- **Name:** Maya Ortiz
- **Handle:** @maya.builds

## Off limits

- **Clients, numbers or names I cannot say publicly:** Acme Corp paid $90,000

## Proof I can use

- We cut proposal time from 5 hours to 20 minutes with one template.
- I lost $18,000 in 2023 because a client contract had no payment-on-delivery clause.
- One carousel about pricing pages booked 14 discovery calls in March.
"""


class Evidence(unittest.TestCase):
    def test_only_proof_identity_said_source(self):
        items, identity = pc.load_evidence(VOICE, "we charge $6,500 per project", "")
        texts = " ".join(i.text for i in items)
        self.assertIn("5 hours", texts)
        self.assertIn("$6,500", texts)
        self.assertNotIn("Acme", texts)
        self.assertIn("Maya", identity)
        self.assertIn("@maya.builds", identity)


class Numbers(unittest.TestCase):
    def v(self, text):
        return [(n.value, n.unit) for n in pc.numbers(text)]

    def test_forms(self):
        self.assertEqual(self.v("$18,000"), [(18000, "$")])
        self.assertEqual(self.v("$18k"), [(18000, "$")])
        self.assertEqual(self.v("45%"), [(45, "%")])
        self.assertEqual(self.v("five hours"), [(300, "min")])
        self.assertEqual(self.v("20 minutes"), [(20, "min")])
        self.assertEqual(self.v("15 times less"), [(15, "x")])
        self.assertEqual(self.v("doubled"), [(2, "x")])
        self.assertEqual(self.v("twenty grand"), [(20000, "$")])
        self.assertEqual(self.v("one template"), [])

    def test_direct_and_derived_binding(self):
        item = pc.numbers("We cut proposal time from 5 hours to 20 minutes with one template.")
        self.assertEqual(pc.bind_number(pc.numbers("five hours")[0], item), "direct")
        self.assertEqual(pc.bind_number(pc.numbers("15 times")[0], item), "derived")
        self.assertEqual(pc.bind_number(pc.numbers("280 minutes")[0], item), "derived")
        self.assertIsNone(pc.bind_number(pc.numbers("doubled")[0], item))
        self.assertIsNone(pc.bind_number(pc.numbers("almost $20,000")[0],
                                         pc.numbers("I lost $18,000 in 2023")))

    def test_numbers_must_bind_to_one_item(self):
        items, _ = pc.load_evidence(VOICE, "", "")
        b = pc.bindings(pc.numbers("14 calls in 5 hours"), items)
        self.assertTrue(b["unbound"] == [] and not any(
            len(v["direct"]) + len(v["derived"]) == 2 for k, v in b.items() if k != "unbound"))


class Claims(unittest.TestCase):
    def test_first_person_and_clients(self):
        self.assertTrue(pc.is_l0_claim("I lost $18,000 on one contract."))
        self.assertTrue(pc.is_l0_claim("My client doubled her bookings."))
        self.assertFalse(pc.is_l0_claim("Keep your hook under three seconds."))
        self.assertFalse(pc.is_l0_claim("Want a teardown of your pricing page?"))
        self.assertFalse(pc.is_l0_claim("Comment TEMPLATE and I'll send it to you."))

    def test_split_joins_fragments_and_skips_placeholders(self):
        s = pc.split_sentences("Proposals used to take me five hours. Twenty minutes now.\n"
                               "It cost me {{your number}}.\nFive hours to twenty minutes. Same template.")
        self.assertEqual([x["text"] for x in s],
                         ["Proposals used to take me five hours. Twenty minutes now.",
                          "Five hours to twenty minutes. Same template."])


class L0Report(unittest.TestCase):
    def setUp(self):
        self.items, self.identity = pc.load_evidence(VOICE, "", "")

    def test_unbound_number_gets_placeholder(self):
        rep = pc.l0("I billed four hours a week for formatting. For two years.", self.items, self.identity)
        flags = rep[0]["flags"]
        self.assertEqual({f["type"] for f in flags}, {"number"})
        self.assertEqual(pc.apply_placeholders("I billed four hours a week for formatting. For two years.", rep),
                         "I billed {{your number}} a week for formatting. For {{your number}}.")

    def test_unknown_name_and_handle(self):
        rep = pc.l0("My client Dana doubled her bookings after I met @sam.co.", self.items, self.identity)
        kinds = sorted(f["type"] for f in rep[0]["flags"])
        self.assertEqual(kinds, ["handle", "name", "number"])

    def test_known_name_months_platforms_pass(self):
        rep = pc.l0("One carousel on Instagram booked me 14 discovery calls in March.", self.items, self.identity)
        self.assertEqual(rep[0]["flags"], [])

    def test_unverified_offline_rule(self):
        rep = pc.l0("I have been following your work since the very first reel.", self.items, self.identity)
        self.assertTrue(rep[0]["unverified"])
        rep = pc.l0("We cut proposal time with one template.", self.items, self.identity)
        self.assertFalse(rep[0]["unverified"])
```

- [ ] **Passo 2: rodar e ver falhar**

Rodar: `python3 -m unittest tests.test_proofcheck -v`
Esperado: ERROR, o módulo não existe.

- [ ] **Passo 3: implementar a L0**

Regras exatas:

- **`parse_voice`**: seções por `^## `.
  - `## Who I am`: extrair `Name:` e `Handle:`, com o valor depois de `:**`. Os nomes entram no conjunto de identidade (cada palavra capitalizada do nome e o handle com `@`), e o item de identidade é `Item("identity", "Name: X; Handle: @y", "identity")` só se houver valor.
  - `## Proof I can use`: cada bullet `- texto` não vazio vira `proofN`.
  - Nenhuma outra seção é lida.
- **`load_evidence`**: cada linha não vazia de `said` vira `saidN`, e cada linha não vazia de `source` vira `sourceN`. Nomes capitalizados e handles que aparecem em qualquer item também entram no conjunto de nomes permitidos.
- **`split_sentences`**:
  - por linha; ignora linhas com `{{`;
  - quebra por `(?<=[.!?])\s+(?=["“'‘(]?[A-Z0-9$@])`;
  - um fragmento com menos de 5 palavras se junta à frase anterior da mesma linha;
  - guarda os offsets no rascunho original.
- **`numbers`**:
  - dígitos com vírgula, `$`, sufixo `k`, `%`, `x`/`times`;
  - por extenso: zero a vinte, dezenas, `hundred`/`thousand`/`million` como multiplicadores, `grand` = × 1.000 com unidade `$`, `dozen` = 12;
  - multiplicadores: `twice`/`double`/`doubled` = 2x, `tripled`/`triple` = 3x, `half` = 0,5x;
  - unidades de tempo convertidas para minutos (`hours`/`hrs` × 60, `days` × 1.440 e assim por diante) com unidade `min`;
  - `one`, `first` e `single` não contam;
  - anos (`19xx`/`20xx` sem unidade) contam como número com unidade `year`.
- **`_close(c, t)`**: vale `c == t`, ou `abs(c-t) <= abs(t)*0.01`, ou `c == round(t)`, ou `c == round(t, 1)`.
- **`bind_number(n, nums)`**:
  - `"direct"` se algum número do item tem unidade compatível (igual, ou uma das duas vazia) e valor `_close`;
  - `"derived"` se, para algum par (a, b) de números do item com a mesma unidade, `n` for `_close` de `a/b`, `b/a` (só com unidade de `n` `x` ou vazia), `abs(a-b)`, `a+b` ou `abs(b-a)/a*100` (só com unidade `%` ou vazia);
  - senão `None`.
- **`bindings`**: para cada item, as listas `direct` e `derived` de índices de números ligados. `unbound` são os números que não se ligam a nenhum item. Um número é "ligado ao item j" se `bind_number(n, numbers(item_j.text))` não é None.
- **`is_l0_claim`**:
  - `re.search(r"(?i)\b(i|i'm|i've|i'd|we|we're|we've|my|our|me|us|client|clients|customer|customers|student|students)\b", s)`;
  - exceto se `s.rstrip().endswith("?")` ou `re.search(r"(?i)\b(i'll|i will|we'll|we will|i want|i'd like|i'm going to|let me)\b", s)`.
- **`names`**:
  - `CAP_RE` sem os inícios de frase (a mesma função `sentence_starts` da Tarefa 1, copiada, porque a pasta precisa rodar sozinha);
  - stoplist com plataformas, dias, meses, `I`, `Here`, `There`, `This`, `That`, `The`;
  - só é flag se não estiver no conjunto de nomes permitidos (sem diferenciar maiúsculas).
- **`handles`**: `@[A-Za-z0-9_.]+` com o ponto final removido. É flag se não estiver no conjunto permitido.
- **`shortlist`**: ordena os itens por (sobreposição de palavras de conteúdo, sem stopwords e com 3 letras ou mais, + 2 × números em comum `_close`) e pega os `k` primeiros.
- **`l0`**: para cada frase, devolve:
  - `claim` (`is_l0_claim`);
  - `nums`;
  - `bindings`;
  - `flags`: `number` para cada número não ligado, só em alegações; `name`/`handle` em alegações;
  - `shortlist` (ids);
  - `unverified`: alegação sem número e com menos de 2 palavras de conteúdo em comum com qualquer item.

  Cada flag é `{"type", "text", "start", "end", "placeholder"}`, com offsets absolutos no rascunho e placeholder `{{your number}}` ou `{{client name}}`.
- **`apply_placeholders`**: substitui os spans das flags do fim para o começo. Não mexe em mais nada.

- [ ] **Passo 4: rodar os testes**

Rodar: `python3 -m unittest tests.test_proofcheck -v`
Esperado: PASS.

- [ ] **Passo 5: commit**

```bash
git add skills/ig-human/proofcheck.py tests/test_proofcheck.py
git commit -m "Add proofcheck L0: evidence parsing, number binding, names and placeholders"
```

---

### Tarefa 6: `proofcheck.py`, L1 (Jev), política, relatório e CLI

**Arquivos:**
- Alterar: `skills/ig-human/proofcheck.py`, `tests/test_proofcheck.py`

**Interfaces:**
- Consome: `jev.ask_many`, `jev.JevUnavailable`, `jev.engine_line`, `jev.engine_fields`, `jev.mode`.
- Produz: `build_questions(sentences, claim_idx, items) -> dict`, `check(draft, items, identity, engine=None) -> dict` (report), `render(report) -> str`, `main()`.

Formato do report:

```python
{"engine": ..., "engine_reason": ..., "engine_detail": ..., "model": ..., "usage": ...,
 "evidence": [{"id","text","kind"}],
 "sentences": [{"i","text","claim","kind","status","proof","flags","notes","same","held"}],
 "judgments": {qid: answer},
 "summary": {"backed","derived","to_confirm","placeholders","unverified"},
 "exit": 0|1}
```

- [ ] **Passo 1: testes que falham**

Acrescentar a `tests/test_proofcheck.py`, com o transporte do Jev falso:

```python
import os
from unittest import mock

jev = load("jev")


def fake(answer_fn):
    """Transport that answers every question with answer_fn(qid, question)."""
    def transport(body, timeout):
        return {"model": jev.MODEL, "usage": {"input_tokens": 10, "output_tokens": 1},
                "answers": {q: answer_fn(q, spec) for q, spec in body["questions"].items()}}
    return transport


def choice(pick, opts):
    return {"type": "choice", "choice": pick, "confidence": 0.9,
            "probabilities": {o: (0.9 if o == pick else 0.1 / (len(opts) - 1)) for o in opts}}


KINDS = ["own_record", "client_result", "outside_fact", "advice_or_opinion", "hypothetical", "ask_or_other"]


class L1Policy(unittest.TestCase):
    def setUp(self):
        self.items, self.identity = pc.load_evidence(VOICE, "", "")
        self.env = mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "k" * 20})
        self.env.start()
        os.environ.pop("IG_JEV", None)

    def tearDown(self):
        self.env.stop()
        jev.set_transport(jev._http_post)

    def run_with(self, draft, kind, same, held):
        def ans(q, spec):
            if q.startswith("kind_"):
                return choice(kind, KINDS)
            if q.startswith("same_"):
                return {"type": "noul", "noul": same(spec)}
            return {"type": "noul", "noul": held(spec)}
        jev.set_transport(fake(ans))
        return pc.check(draft, self.items, self.identity)

    def proof_is(self, spec, needle):
        return needle in spec["instructions"]["proof_item"]

    def test_backed(self):
        r = self.run_with("Proposals used to take me five hours. Twenty minutes now.", "own_record",
                          lambda s: 0.9 if self.proof_is(s, "5 hours") else 0.05,
                          lambda s: 0.9 if self.proof_is(s, "5 hours") else 0.05)
        s = r["sentences"][0]
        self.assertEqual((s["status"], s["proof"]), ("BACKED", "proof1"))
        self.assertEqual(r["exit"], 0)

    def test_unbacked(self):
        r = self.run_with("I billed four hours a week for formatting. For two years.", "own_record",
                          lambda s: 0.05, lambda s: 0.05)
        self.assertEqual(r["sentences"][0]["status"], "UNBACKED")
        self.assertEqual(r["exit"], 1)

    def test_mismatch(self):
        r = self.run_with("That carousel on pricing pages booked me 40 discovery calls.", "own_record",
                          lambda s: 0.9 if self.proof_is(s, "carousel") else 0.05, lambda s: 0.2)
        self.assertEqual(r["sentences"][0]["status"], "MISMATCH")

    def test_embellished(self):
        r = self.run_with("My pricing carousel booked 14 calls in a single week.", "own_record",
                          lambda s: 0.9 if self.proof_is(s, "carousel") else 0.05, lambda s: 0.1)
        self.assertEqual(r["sentences"][0]["status"], "EMBELLISHED")

    def test_derived(self):
        r = self.run_with("Proposals take me 15 times less time now.", "own_record",
                          lambda s: 0.9 if self.proof_is(s, "5 hours") else 0.05, lambda s: 0.2)
        self.assertEqual(r["sentences"][0]["status"], "DERIVED")
        self.assertEqual(r["exit"], 0)

    def test_jev_widens_claims_never_narrows(self):
        r = self.run_with("Loved your reel on retainer pricing last week.", "own_record",
                          lambda s: 0.05, lambda s: 0.05)
        self.assertEqual(r["sentences"][0]["status"], "UNBACKED")
        r = self.run_with("I billed four hours a week.", "advice_or_opinion",
                          lambda s: 0.9, lambda s: 0.9)
        self.assertTrue(r["sentences"][0]["claim"])
        self.assertTrue(any(f["type"] == "number" for f in r["sentences"][0]["flags"]))
        self.assertEqual(r["exit"], 1)

    def test_outside_fact_with_number_is_a_note(self):
        r = self.run_with("Instagram caps hashtags at five per post.", "outside_fact",
                          lambda s: 0.05, lambda s: 0.05)
        self.assertIn("statistic: add a source or cut", r["sentences"][0]["notes"])
        self.assertEqual(r["exit"], 0)

    def test_no_evidence_means_no_pairs_and_unbacked(self):
        seen = []
        def ans(q, spec):
            seen.append(q)
            return choice("own_record", KINDS)
        jev.set_transport(fake(ans))
        r = pc.check("I made $50,000 last month.", [], set())
        self.assertEqual(r["sentences"][0]["status"], "UNBACKED")
        self.assertFalse([q for q in seen if not q.startswith("kind_")])


class Fallback(unittest.TestCase):
    def test_heuristic_line_and_unverified(self):
        items, identity = pc.load_evidence(VOICE, "", "")
        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": ""}):
            r = pc.check("I have been following your work since the very first reel.", items, identity)
        self.assertEqual((r["engine"], r["engine_reason"]), ("heuristic", "no-key"))
        self.assertEqual(r["sentences"][0]["status"], "UNVERIFIED")
        self.assertEqual(r["exit"], 1)
        self.assertTrue(pc.render(r).startswith("engine: heuristic (no-key)"))


class CLI(unittest.TestCase):
    def test_cli_off_writes_placeholders_and_exits_1(self):
        import tempfile
        from tests.support import run_cli
        with tempfile.TemporaryDirectory() as d:
            draft, voice, out = (os.path.join(d, n) for n in ("d.txt", "v.md", "o.txt"))
            open(draft, "w").write("I billed four hours a week for formatting.\n")
            open(voice, "w").write(VOICE)
            p = run_cli("ig-human/proofcheck.py", [draft, "--voice", voice, "-o", out])
            self.assertEqual(p.returncode, 1, p.stderr)
            self.assertTrue(p.stdout.startswith("engine: heuristic (disabled)"))
            self.assertIn("{{your number}}", open(out).read())

    def test_engine_jev_without_key_exits_3(self):
        import tempfile
        from tests.support import run_cli
        with tempfile.TemporaryDirectory() as d:
            draft = os.path.join(d, "d.txt")
            open(draft, "w").write("Keep your hook short.\n")
            p = run_cli("ig-human/proofcheck.py", [draft, "--voice", os.path.join(d, "none.md"),
                                                   "--engine", "jev"])
            self.assertEqual(p.returncode, 3)
```

- [ ] **Passo 2: rodar e ver falhar**

Rodar: `python3 -m unittest tests.test_proofcheck -v`
Esperado: ERROR em `check`, `render` e `set_transport` com proofcheck.

- [ ] **Passo 3: implementar a L1 e a política**

- **`build_questions`**:
  - `kind_{i}` para toda frase, com as instructions e os critérios exatos da spec §5;
  - `same_{i}_{j}` e `held_{i}_{j}` para toda frase candidata × shortlist, em que candidata é toda frase que não termina com "?". São perguntas especulativas: o código só consome as das alegações finais;
  - sem itens, não há pares;
  - `j` é o índice do item na lista `items`;
  - state: `{"draft": "\n".join(frases)}`.
- **`check`**:
  - calcula a L0;
  - tenta `jev.ask_many(state, questions, engine=engine)`;
  - se o módulo `jev` não importar, o motivo é `client-missing`;
  - com `JevUnavailable`, roda o caminho heurístico.
- **Caminho Jev**, para cada frase:
  - `p_claim = P(own_record) + P(client_result)`;
  - `claim = l0.claim or p_claim >= CLAIM`;
  - `kind` = escolha do Jev;
  - a frase que não é alegação recebe status `—`, mas as flags de nome e número que a L0 já deu continuam (a L0 só dá flags em alegações).
- **Caminho Jev**, para cada alegação:
  - sem evidência: `UNBACKED`;
  - com evidência, `best` = argmax de `same` na shortlist:
    - `same[best] < SAME`: `UNBACKED`;
    - senão, se algum número da frase não se liga a `best`: `MISMATCH`, com `proof = best` e a nota `your proof says: <texto>`;
    - senão, se `held[best] < HELD`: `DERIVED` quando a frase tem pelo menos um número `derived` ligado a `best` e todos os números ligados a `best`; senão `EMBELLISHED`;
    - senão, `BACKED`.
  - Se `kind == outside_fact` e há número na frase: nota `statistic: add a source or cut`.
  - Quando a alegação veio só do Jev (`not l0.claim`), rodar em código as checagens de número e nome sobre ela e acrescentar as flags.
- **Caminho heurístico**, para cada alegação da L0:
  - `UNVERIFIED` se `unverified`;
  - senão `FLAGGED` se tem flags;
  - senão `CHECKED` (números e nomes presentes na evidência; o julgamento semântico não rodou).
- **`exit`**: 1 se algum status estiver em `{UNBACKED, MISMATCH, EMBELLISHED, UNVERIFIED, FLAGGED}` ou se houver flag de número, nome ou handle. Senão, 0.
- **`summary`**:
  - `backed`: BACKED + CHECKED;
  - `derived`: DERIVED;
  - `to_confirm`: UNBACKED + MISMATCH + EMBELLISHED + UNVERIFIED + FLAGGED;
  - `placeholders`: número de flags.
- **`render`**:
  - primeira linha: `engine_line`;
  - depois `PROOF CHECK · N sentences · N claims · N evidence items`, a lista `evidence used:` e uma linha por frase que não é BACKED/CHECKED nem `—`, com status, número, frase entre aspas, prova citada e flags;
  - linha final: `proof: {backed} backed, {placeholders} {{…}}, {to_confirm} to confirm · engine {jev-1.13.0|heuristic}`.
- **`main`**: flags `draft`, `--said`, `--source`, `--voice` (padrão `~/.claude/instagram/voice.md`; se não existir, sem evidência e com um aviso em stderr), `-o`, `--json` e `--engine`.
  - Com `--json`, imprime o report inteiro.
  - Com `-o`, grava `apply_placeholders`.
  - Rascunho vazio: exit 2.
  - `--engine jev` com o motor heurístico: exit 3, depois de imprimir o relatório.
- O `jev` é importado dentro de `check`, de forma preguiçosa, a partir da própria pasta.

- [ ] **Passo 4: rodar os testes**

Rodar: `python3 -m unittest tests.test_proofcheck -v`
Esperado: PASS.

- [ ] **Passo 5: smoke ao vivo**

Rodar o `case_reel` dos probes com `--engine jev` e conferir: a linha 2 ("I billed four hours…") e "My close rate went from 20% to 45%" saem sinalizadas; a linha 1 sai BACKED.

- [ ] **Passo 6: commit**

```bash
git add skills/ig-human/proofcheck.py tests/test_proofcheck.py
git commit -m "Add proofcheck L1: Jev claim kinds, same-event and held checks with code-owned verdicts"
```

---

### Tarefa 7: integração do `proofcheck` nas SKILL.md e no template

**Arquivos:**
- Alterar: `skills/ig-human/SKILL.md`, `skills/ig-reel/SKILL.md`, `skills/ig-story/SKILL.md`, `skills/ig-reply/SKILL.md`, `templates/voice.md`, `tests/test_docs.py`

- [ ] **Passo 1: teste que falha**

```python
    def test_proof_guard_wired(self):
        human = read("ig-human/SKILL.md")
        self.assertIn("python3 proofcheck.py", human)
        self.assertIn("two rounds", human)
        self.assertIn("proof:", read("ig-reel/SKILL.md"))
        for rel in ("ig-story/SKILL.md", "ig-reply/SKILL.md"):
            self.assertIn("proofcheck.py", read(rel))
        tmpl = open(os.path.join(SKILLS, "..", "templates", "voice.md"), encoding="utf-8").read()
        self.assertIn("one checkable fact per bullet", tmpl)
```

- [ ] **Passo 2: rodar e ver falhar**

- [ ] **Passo 3: escrever as seções**

- `ig-human/SKILL.md`: nova seção "## Step 0: the proof guard", antes de "What gets fixed automatically". Ela traz:
  - o comando (`python3 proofcheck.py draft.txt --said said.txt [--source source.txt]`);
  - o que é evidência;
  - a regra de copiar literalmente as falas do usuário para `said.txt`;
  - o significado de cada status;
  - o que fazer com cada um (BACKED segue; DERIVED revisão leve; UNBACKED/MISMATCH/EMBELLISHED/UNVERIFIED: confirmar com o usuário ou cortar, nunca "consertar" inventando);
  - a linha de motor e o `IG_JEV=off`;
  - "Never compare results across engines";
  - "Stop after two rounds: if flags remain, show them and let the user decide".
- `ig-reel/SKILL.md`, depois de escrever os hooks e o roteiro: rodar o `proofcheck`. O bloco REEL READY ganha `proof: N backed, N {{…}}, N to confirm · engine <…>`.
- `ig-story/SKILL.md` e `ig-reply/SKILL.md`: uma linha "Before showing any line that states a result, a number or a shared history, run `../ig-human/proofcheck.py` on it (see /ig-human, Step 0)."
- `templates/voice.md`, em *Proof I can use*: "One checkable fact per bullet: what happened, the number, when. `proofcheck.py` matches drafts against these lines one by one."

- [ ] **Passo 4: rodar os testes, e o commit**

```bash
python3 -m unittest tests.test_docs -v
git add skills/ig-human/SKILL.md skills/ig-reel/SKILL.md skills/ig-story/SKILL.md skills/ig-reply/SKILL.md templates/voice.md tests/test_docs.py
git commit -m "Wire the proof guard into ig-human, ig-reel, ig-story and ig-reply"
```

---

### Tarefa 8: `skills/ig-reel/formula.py`

**Arquivos:**
- Criar: `skills/ig-reel/formula.py`, `tests/test_formula.py`

**Interfaces:**
- Consome: `jev.ask_each`, `jev.engine_line`, `jev.engine_fields`, `hooks.json`.
- Produz:

```python
JEV_ONLY_MIN = 0.85; NEW_SHAPE = 0.60; NO_HOOK = 0.30          # provisional
META_RE = re.compile(r"\b(hook formula|formula|classif(?:y|ied|ication)|label (?:this|it) as)\b", re.I)
COUNTED = {"AGREE", "JEV", "REGEX"}
def load(path=HOOKS) -> dict                          # {"version", "formulas": [{"id","name","slug","template","example","regex"}], "order"}
def regex_classify(hook, data) -> tuple[int|None, str]
def build_questions(data, leave_out_id=None) -> dict   # {"formula": choice, "has_shape": noul}
def status_for(regex_id, jev_slug, confidence, has_shape, slug_to_id) -> str
def classify_hooks(hooks, engine=None, hooks_path=HOOKS, selftest_ids=None) -> dict
    # {"engine","engine_reason","engine_detail","model","usage","hooks_version",
    #  "items": [{"hook","regex_id","regex_name","jev_id","jev_name","confidence","has_shape",
    #             "status","counted","formula_id","formula","probabilities","reason"}]}
def main()
```

- [ ] **Passo 1: testes que falham**

```python
import os
import unittest
from unittest import mock

from tests.support import load

fm = load("formula")
jev = load("jev")


def transport_for(pick_by_hook, conf=0.95, shape=0.9):
    def t(body, timeout):
        hook = body["state"]["hook"]
        pick = pick_by_hook(hook)
        opts = body["questions"]["formula"]["criteria"]
        return {"model": jev.MODEL, "usage": {"input_tokens": 100, "output_tokens": 5},
                "answers": {"formula": {"type": "choice", "choice": pick, "confidence": conf,
                                        "probabilities": {o: (conf if o == pick else 0.0) for o in opts}},
                            "has_shape": {"type": "noul", "noul": shape}}}
    return t


class Questions(unittest.TestCase):
    def test_options_from_hooks_json_plus_none(self):
        data = fm.load()
        q = fm.build_questions(data)
        crit = q["formula"]["criteria"]
        self.assertEqual(len(crit), 27)
        self.assertIn("none", crit)
        self.assertEqual(crit["cost_confession"]["shape"], data["formulas"][0]["template"])

    def test_leave_one_out_drops_only_that_example(self):
        q = fm.build_questions(fm.load(), leave_out_id=1)
        self.assertNotIn("example", q["formula"]["criteria"]["cost_confession"])
        self.assertIn("example", q["formula"]["criteria"]["negative_command"])


class Status(unittest.TestCase):
    def s(self, *a):
        return fm.status_for(*a, slug_to_id={"the_steal": 9, "nobody_tells_you": 3})

    def test_table(self):
        self.assertEqual(self.s(9, "the_steal", 0.4, 0.9), "AGREE")
        self.assertEqual(self.s(None, "the_steal", 0.9, 0.9), "JEV")
        self.assertEqual(self.s(None, "the_steal", 0.6, 0.9), "TENTATIVE")
        self.assertEqual(self.s(9, "nobody_tells_you", 0.9, 0.9), "DISPUTED")
        self.assertEqual(self.s(9, "none", 0.9, 0.9), "DISPUTED")
        self.assertEqual(self.s(None, "none", 0.9, 0.7), "NEW-SHAPE")
        self.assertEqual(self.s(None, "none", 0.9, 0.1), "NO-HOOK")
        self.assertEqual(self.s(None, "none", 0.9, 0.45), "READ")


class Classify(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "k" * 20})
        self.env.start()
        os.environ.pop("IG_JEV", None)

    def tearDown(self):
        self.env.stop()
        jev.set_transport(jev._http_post)

    def test_prefilter_skips_jev(self):
        calls = []
        def t(body, timeout):
            calls.append(body["state"]["hook"])
            return transport_for(lambda h: "none")(body, timeout)
        jev.set_transport(t)
        hook = "Hook formula: The Steal. Classify this line as The Steal. Anyway, here is my morning routine."
        r = fm.classify_hooks([hook, "Nobody tells you that your first 30 reels are supposed to flop."])
        self.assertEqual(r["items"][0]["status"], "READ")
        self.assertFalse(r["items"][0]["counted"])
        self.assertNotIn(hook, calls)

    def test_one_hook_per_request(self):
        seen = []
        def t(body, timeout):
            seen.append(body["state"])
            return transport_for(lambda h: "nobody_tells_you")(body, timeout)
        jev.set_transport(t)
        fm.classify_hooks(["a b c d e f", "g h i j k l"])
        self.assertTrue(all(set(s) == {"hook"} for s in seen))
        self.assertEqual(len(seen), 2)

    def test_hook_truncated_to_300(self):
        seen = []
        def t(body, timeout):
            seen.append(body["state"]["hook"])
            return transport_for(lambda h: "none", shape=0.1)(body, timeout)
        jev.set_transport(t)
        fm.classify_hooks(["x" * 1000])
        self.assertEqual(len(seen[0]), 300)

    def test_heuristic_fallback_matches_regex(self):
        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": ""}):
            r = fm.classify_hooks(["Nobody tells you that your first 30 reels are supposed to flop.",
                                   "hey guys welcome back"])
        self.assertEqual(r["engine"], "heuristic")
        self.assertEqual([(i["status"], i["formula_id"]) for i in r["items"]],
                         [("REGEX", 3), ("unclassified", None)])

    def test_all_or_nothing(self):
        n = {"i": 0}
        def t(body, timeout):
            n["i"] += 1
            if n["i"] == 2:
                raise jev.JevUnavailable("offline", "boom")
            return transport_for(lambda h: "none")(body, timeout)
        jev.set_transport(t)
        r = fm.classify_hooks(["one two three four", "five six seven eight", "nine ten eleven twelve"])
        self.assertEqual(r["engine"], "heuristic")
        self.assertTrue(all(i["status"] in ("REGEX", "unclassified") for i in r["items"]))


class CLI(unittest.TestCase):
    def test_engine_line_first(self):
        from tests.support import run_cli
        p = run_cli("ig-reel/formula.py", ["Nobody tells you that your first 30 reels are supposed to flop."])
        self.assertTrue(p.stdout.startswith("engine: heuristic (disabled)"))
        self.assertEqual(p.returncode, 0)
```

- [ ] **Passo 2: rodar e ver falhar**

Rodar: `python3 -m unittest tests.test_formula -v`

- [ ] **Passo 3: implementar**

- `slug` = `re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")`.
- **`build_questions`**:
  - `formula` (Choice): as instructions da spec §6, literais; critérios `{slug: {"shape": template, "example": example}}`, na ordem dos ids, mais `none` com o texto da spec;
  - `leave_out_id` remove `example` só daquela opção;
  - `has_shape` (Noul): as instructions literais da spec.
- **`status_for`**: a tabela da spec §6. `has_shape` entre `NO_HOOK` e `NEW_SHAPE` com `J == none` e `R == None` dá `READ`.
- **`classify_hooks`**:
  - deduplica preservando a ordem;
  - aplica o pré-filtro (`READ`, com `reason: "classification language in the hook"`);
  - para os demais, `jev.ask_each([({"hook": h[:300]}, questions_for(h)) ...], engine=engine)`, com `questions_for` igual para todos, exceto no selftest (`leave_out_id` = id esperado);
  - com `JevUnavailable` ou jev ausente, todos os itens recebem a regex (`REGEX` se casar, `unclassified` se não) e `counted = status == "REGEX"`;
  - `formula_id`/`formula` só são preenchidos para status contados (AGREE, JEV, REGEX). Nos outros ficam `None` e o nome do status.
- **`main`**: aceita hooks posicionais, `--tsv FILE` (coluna `hook` com cabeçalho, senão a última coluna), `--selftest`, `--json` e `--engine`.
  - Texto: linha de motor, `FORMULAS · N hooks · K counted (J by jev only)` e os itens agrupados na ordem NEW-SHAPE, DISPUTED, TENTATIVE, JEV, AGREE, REGEX, READ, NO-HOOK, unclassified.
  - `--selftest`: classifica os 26 exemplos com leave-one-out e imprime `selftest: N/26 counted with the right id, W wrong ids at a counted status`. Exit 1 se `W > 0`.
  - `--engine jev` com o motor heurístico dá exit 3.

- [ ] **Passo 4: rodar os testes**

Rodar: `python3 -m unittest tests.test_formula -v`
Esperado: PASS.

- [ ] **Passo 5: selftest ao vivo**

Rodar: `python3 skills/ig-reel/formula.py --selftest --engine jev`
Esperado: 0 ids errados entre os contados. Anotar o N/26 para o REPORT.

- [ ] **Passo 6: commit**

```bash
git add skills/ig-reel/formula.py tests/test_formula.py
git commit -m "Add formula.py: regex and Jev cross-checked hook formula classifier"
```

---

### Tarefa 9: `swipe.py` com `classify_hooks`, SKILL.md do `ig-viral` e do `ig-audit`, e goldens

**Arquivos:**
- Alterar: `skills/ig-viral/swipe.py`, `skills/ig-viral/SKILL.md`, `skills/ig-audit/SKILL.md`, `skills/ig-caption/caption.py` (só `--engine` e a linha de motor, sem Jev ainda: o Jev entra na Tarefa 11)
- Criar: `tests/test_swipe.py`, `tests/test_golden.py`, `tests/fixtures/{hooks.txt,script.txt,caption.txt,draft.txt,swipe.tsv}`, `tests/golden/*.txt`

**Interfaces:**
- Consome: `formula.classify_hooks`.
- Produz: `swipe.analyse(rows, formulas, engine=None)` com os campos novos `formula_engine`, `jev_only` e `hooks_version`, e `row["formula_status"]`.

- [ ] **Passo 1: testes que falham**

`tests/test_swipe.py`:

```python
import os
import unittest
from unittest import mock

from tests.support import load

swipe = load("swipe")
jev = load("jev")
ROWS = [
    {"account": "@a", "followers": 1000, "median": 500, "views": 50000,
     "hook": "Nobody tells you that your first 30 reels are supposed to flop."},
    {"account": "@b", "followers": 1000, "median": 500, "views": 40000,
     "hook": "never in a million years did i think this reel would pay my rent"},
    {"account": "@c", "followers": 1000, "median": 500, "views": 600, "hook": "hey guys welcome back"},
]


class SwipeEngine(unittest.TestCase):
    def tearDown(self):
        jev.set_transport(jev._http_post)

    def test_heuristic_counts_like_before(self):
        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": ""}):
            a = swipe.analyse([dict(r) for r in ROWS], swipe.load_formulas(swipe.HOOKS))
        self.assertTrue(a["formula_engine"].startswith("regex ("))
        self.assertEqual(a["top_formulas"], [("Nobody Tells You", 1)])
        self.assertEqual(a["unclassified"], 2)

    def test_jev_counts_only_agree_and_jev(self):
        def t(body, timeout):
            hook = body["state"]["hook"]
            pick = "nobody_tells_you" if hook.startswith(("Nobody", "never")) else "none"
            opts = body["questions"]["formula"]["criteria"]
            return {"model": jev.MODEL, "usage": {"input_tokens": 1, "output_tokens": 1},
                    "answers": {"formula": {"type": "choice", "choice": pick, "confidence": 0.9,
                                            "probabilities": {o: 0.0 for o in opts}},
                                "has_shape": {"type": "noul", "noul": 0.05}}}
        jev.set_transport(t)
        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "k" * 20}):
            os.environ.pop("IG_JEV", None)
            a = swipe.analyse([dict(r) for r in ROWS], swipe.load_formulas(swipe.HOOKS))
        self.assertEqual(a["formula_engine"], "regex+jev-1.13.0")
        self.assertEqual(a["top_formulas"], [("Nobody Tells You", 2)])
        self.assertEqual(a["jev_only"], 1)

    def test_markdown_header_records_engine_and_version(self):
        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": ""}):
            a = swipe.analyse([dict(r) for r in ROWS], swipe.load_formulas(swipe.HOOKS))
        md = swipe.to_markdown(a)
        self.assertIn("formula engine: regex (", md)
        self.assertIn("hooks.json v1.1", md)
```

`tests/test_golden.py`: para cada par `(script, args, fixture, golden)`, roda `run_cli` e compara `stdout` byte a byte com `tests/golden/<nome>.txt`.
- Pares: `hookscore` (ranking de `hooks.txt` e `--hook` de um), `beats` (`script.txt --target 30`), `detect` (`draft.txt`), `caption` (`caption.txt --engine off`) e `swipe` (`swipe.tsv --engine off`).
- Com `UPDATE_GOLDEN=1`, o teste grava em vez de comparar. É o único jeito de gerar os arquivos.

- [ ] **Passo 2: rodar e ver falhar**

- [ ] **Passo 3: implementar**

- **`swipe.py`**:
  - depois do import opcional do hookscore, `try: from formula import classify_hooks except Exception: classify_hooks = None`;
  - `analyse(rows, formulas, engine=None)`:
    - com `classify_hooks`, chama uma vez com os hooks únicos e mapeia por hook: `formula_id`, `formula` (o nome, se contado; senão o status, ou `unclassified` no modo heurístico) e `formula_status`;
    - sem `classify_hooks`, usa o `classify` local como hoje e `formula_engine = "regex (client-missing)"`;
    - `top_formulas` conta só as linhas com status contado;
    - `unclassified` = linhas sem status contado;
    - `jev_only` = linhas com status `JEV`;
    - `formula_engine` = `"regex+jev-1.13.0"` com Jev, senão `f"regex ({reason})"`;
    - `hooks_version` é lido do `hooks.json`.
  - `render`: a primeira linha passa a ser a linha de motor (do resultado do `classify_hooks`, ou `engine: heuristic (client-missing)`), e o resto fica igual. Com Jev, acrescentar embaixo de `top third by outlier` a linha `  counted by jev only:   N` e, se houver `DISPUTED`/`NEW-SHAPE`, `  read by hand:          N disputed, N new shape`.
  - `to_markdown`: acrescentar no cabeçalho `formula engine: <...> · hooks.json v<version>`.
  - `main`: flag `--engine` e exit 3 com `--engine jev` e motor heurístico.
- **`caption.py`**: flag `--engine`, linha `engine: heuristic (<reason>)` como primeira linha do render e campos `engine`/`engine_reason`/`engine_detail`/`model`/`usage` no JSON. Nesta tarefa o motivo vem de `mode()`: `disabled` com off, `client-missing` se o jev não importar, `no-key` sem chave. O `--engine jev` sem Jev dá exit 3. A chamada real entra na Tarefa 11.
- **Fixtures**: textos curtos em inglês, reaproveitando os exemplos das SKILL.md.
- **Goldens**: gerar com `UPDATE_GOLDEN=1 python3 -m unittest tests.test_golden` e **ler cada golden** antes do commit, para confirmar que a única diferença contra a saída de hoje é a linha de motor e as correções da Fase 0.
- **`ig-viral/SKILL.md`**: seção "## Formula status (when Jev is on)" com a tabela de status, "count only AGREE and JEV", "read DISPUTED and NEW-SHAPE by hand, they are where a formula you do not have yet is hiding", "#13, #18 and #24 are visual and cannot be judged from text", a linha de motor e "never compare counts across engines".
- **`ig-audit/SKILL.md`**: para posts sem fórmula no `log.md`, `python3 ../ig-reel/formula.py "<first line>" ...`, usando só os status contados.

- [ ] **Passo 4: rodar todos os testes**

Rodar: `python3 -m unittest discover -s tests -t .`
Esperado: PASS.

- [ ] **Passo 5: commit**

```bash
git add skills/ig-viral/swipe.py skills/ig-viral/SKILL.md skills/ig-audit/SKILL.md skills/ig-caption/caption.py tests/test_swipe.py tests/test_golden.py tests/fixtures tests/golden
git commit -m "Count swipe formulas with the regex and Jev cross-check and freeze engine-off goldens"
```

---

### Tarefa 10: `needs` no `hooks.json` e `skills/ig-reel/fit.py`

**Arquivos:**
- Alterar: `skills/ig-reel/hooks.json` (campo `needs` nas 26 fórmulas), `skills/ig-reel/SKILL.md`
- Criar: `skills/ig-reel/fit.py`, `tests/test_fit.py`

**Interfaces:**
- Produz:

```python
VETO = 0.25; WRITABLE = 0.50; MULTI = 0.70            # provisional
def build_questions(formulas) -> dict                  # multi_idea + fit_{id}
def fit(idea, engine=None, hooks_path=HOOKS) -> dict
    # {"engine",...,"idea","multi_idea","multi","writable":[{id,name,p,needs}],"unlockable":[...],"vetoed":[...],"skipped": reason|None}
def render(r) -> str
def main()
```

- [ ] **Passo 1: testes que falham**

```python
import json
import os
import re
import unittest
from unittest import mock

from tests.support import SKILLS, load

fit = load("fit")
jev = load("jev")
HOOKS = os.path.join(SKILLS, "ig-reel", "hooks.json")


class Needs(unittest.TestCase):
    def test_every_formula_has_literal_needs_covering_placeholders(self):
        data = json.load(open(HOOKS, encoding="utf-8"))
        for h in data["hooks"]:
            self.assertIsInstance(h.get("needs"), list, h["name"])
            self.assertTrue(h["needs"], h["name"])
            self.assertGreaterEqual(len(h["needs"]), len(re.findall(r"\{[^}]+\}", h["template"])) // 2,
                                    h["name"])


class Policy(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "k" * 20})
        self.env.start()
        os.environ.pop("IG_JEV", None)

    def tearDown(self):
        self.env.stop()
        jev.set_transport(jev._http_post)

    def test_three_lists_and_multi(self):
        def t(body, timeout):
            self.assertEqual(set(body["state"]), {"idea"})
            ans = {}
            for q in body["questions"]:
                p = {"fit_5": 0.95, "fit_9": 0.4, "multi_idea": 0.8}.get(q, 0.05)
                ans[q] = {"type": "noul", "noul": p}
            return {"model": jev.MODEL, "usage": {"input_tokens": 1, "output_tokens": 1}, "answers": ans}
        jev.set_transport(t)
        r = fit.fit("we cut proposal time from 5 hours to 20 minutes with one template")
        self.assertEqual([w["id"] for w in r["writable"]], [5])
        self.assertEqual([u["id"] for u in r["unlockable"]], [9])
        self.assertEqual(len(r["vetoed"]), 24)
        self.assertTrue(r["multi"])
        self.assertIn("TWO IDEAS? which one first?", fit.render(r))

    def test_idea_truncated_and_one_request(self):
        calls = []
        def t(body, timeout):
            calls.append(body)
            return {"model": jev.MODEL, "usage": {}, "answers": {
                q: {"type": "noul", "noul": 0.5} for q in body["questions"]}}
        jev.set_transport(t)
        fit.fit("x" * 5000)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]["state"]["idea"]), 1500)
        self.assertEqual(len(calls[0]["questions"]), 27)


class Fallback(unittest.TestCase):
    def test_skipped_exit_0_and_3(self):
        from tests.support import run_cli
        p = run_cli("ig-reel/fit.py", ["an idea"])
        self.assertEqual(p.returncode, 0)
        self.assertIn("fit: skipped (disabled)", p.stdout)
        p = run_cli("ig-reel/fit.py", ["an idea", "--engine", "jev"])
        self.assertEqual(p.returncode, 3)
```

- [ ] **Passo 2: rodar e ver falhar**

- [ ] **Passo 3: escrever os `needs` e o script**

- **`needs`**: uma lista literal por fórmula, com um ingrediente por placeholder do template, cada um nomeando o fato que precisa ser verdadeiro. Exemplos:
  - #1: `["the amount one specific mistake cost", "what the mistake was"]`;
  - #5: `["how long the task used to take", "how long it takes now"]`;
  - #6: `["something the creator did repeatedly", "for how many days, weeks or months", "the actual numbers that resulted"]`;
  - #9: `["a reusable artifact the viewer can copy", "how long it took to get right"]`;
  - #22: `["a well-known saying the idea contradicts"]`.

  As fórmulas visuais também recebem os `needs` (#13: `["what it looked like before", "what it looks like now", "the one thing that changed"]`).
- **Perguntas**: exatamente as da spec §7.
  - `multi_idea` com os critérios da spec.
  - `fit_{id}` com `instructions = {"formula": {"name", "template", "needs"}, "question": ...}` e os critérios true/false literais.
  - `jev.ask(state, questions, engine=engine)` numa só requisição; se o estimado passar de 48k, `ask_many`.
- **Listas**: `p >= WRITABLE` → WRITABLE; `VETO <= p < WRITABLE` → UNLOCKABLE; `p < VETO` → VETOED. Cada lista vem ordenada por p decrescente.
- **Render**:
  - linha de motor;
  - `FORMULA FIT · "<ideia até 60 caracteres>"`;
  - `TWO IDEAS? which one first?` se `multi_idea >= MULTI`;
  - as três listas, com `p`, `#id` e o nome; em UNLOCKABLE, `ask for: <need>; <need>`;
  - linha final: `fit: N writable, N unlockable, N vetoed · engine jev-1.13.0`.
- **Fallback**: linha de motor + `fit: skipped (<reason>)`. Exit 0, ou 3 com `--engine jev`.
- **`ig-reel/SKILL.md`**: nova seção "## Step 0: which formulas can this idea carry" com:
  - o comando;
  - "choose the three formulas only from WRITABLE";
  - "fewer than three: write those, and add up to two UNLOCKABLE questions to the batched question";
  - "none: treat the idea as thin, ask the batched question, re-run fit";
  - "if the user names a VETOED formula, their call stands: ask for the missing ingredient, never invent it";
  - "if fit is skipped: use only formulas whose `needs` are stated in the idea; otherwise ask for the missing ingredient".

  REEL READY e `log.md` registram a linha `fit:` e os overrides.

- [ ] **Passo 4: rodar os testes e o live**

Rodar: `python3 -m unittest tests.test_fit tests.test_hooks_regex -v` e depois `python3 skills/ig-reel/fit.py "we cut proposal time from 5 hours to 20 minutes with one template" --engine jev`
Esperado: PASS. No live, #5 Time Collapse em WRITABLE e #1 Cost Confession em VETOED ou UNLOCKABLE.

- [ ] **Passo 5: commit**

```bash
git add skills/ig-reel/hooks.json skills/ig-reel/fit.py skills/ig-reel/SKILL.md tests/test_fit.py
git commit -m "Add fit.py: veto hook formulas an idea cannot carry without invented facts"
```

---

### Tarefa 11: pedidos na legenda com Jev (`caption.py`)

**Arquivos:**
- Alterar: `skills/ig-caption/caption.py`, `skills/ig-caption/SKILL.md`
- Criar: `tests/test_caption_asks.py`

**Interfaces:**
- Produz: `caption.split_sentences(text) -> list[str]`, `caption.ask_questions(sentences) -> dict`, `caption.jev_asks(text, engine=None) -> dict | raises`, `caption.analyse(text, cut, keywords, engine=None)`, com `engine*`, `judgments` e `heuristic_asks` no retorno.

- [ ] **Passo 1: testes que falham**

```python
import os
import unittest
from unittest import mock

from tests.support import load

cap = load("caption")
jev = load("jev")
TYPES = ["comment_keyword", "comment_reply", "save", "share_or_send", "follow", "dm",
         "link_in_bio", "swipe", "no_ask"]


def transport(by_sentence):
    """by_sentence: substring -> (p_is_ask, type)."""
    def t(body, timeout):
        ans = {}
        for q, spec in body["questions"].items():
            s = spec["instructions"]["sentence"]
            p, typ = next((v for k, v in by_sentence.items() if k in s), (0.02, "no_ask"))
            if q.endswith("_is_ask"):
                ans[q] = {"type": "noul", "noul": p}
            else:
                ans[q] = {"type": "choice", "choice": typ, "confidence": 0.9,
                          "probabilities": {o: (0.9 if o == typ else 0.0125) for o in TYPES}}
        return {"model": jev.MODEL, "usage": {"input_tokens": 1, "output_tokens": 1}, "answers": ans}
    return t


class Split(unittest.TestCase):
    def test_quotes_stay_whole_and_hashtag_lines_drop(self):
        s = cap.split_sentences('She said "share it. now." and left. Save this.\n#pricing #freelance')
        self.assertEqual(s, ['She said "share it. now." and left.', "Save this."])


class Asks(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "k" * 20})
        self.env.start()
        os.environ.pop("IG_JEV", None)

    def tearDown(self):
        self.env.stop()
        jev.set_transport(jev._http_post)

    def one_ask(self, a):
        return next(c for c in a["checks"] if c["check"] == "ONE ASK")

    def test_paraphrased_ask_is_found(self):
        jev.set_transport(transport({"linked on my profile": (0.9, "link_in_bio")}))
        a = cap.analyse("I rebuilt my pricing page in March.\nGrab the free template, it's linked on my profile.")
        self.assertEqual(self.one_ask(a)["status"], "PASS")
        self.assertEqual(a["engine"], "jev")

    def test_quoted_share_is_not_an_ask(self):
        jev.set_transport(transport({"Save this": (0.95, "save")}))
        a = cap.analyse("She told me to share it with the whole team before Friday.\nSave this.")
        self.assertEqual(self.one_ask(a)["status"], "PASS")
        self.assertIn("regex vs jev", "\n".join(a["notes"]))

    def test_repeats_count_once_and_two_types_warn(self):
        jev.set_transport(transport({"Save this": (0.9, "save"), "Save it": (0.9, "save"),
                                     "Follow": (0.9, "follow")}))
        a = cap.analyse("Save this. Save it for later.\nFollow for part 2.")
        self.assertEqual(self.one_ask(a)["status"], "WARN")

    def test_borderline_is_reported_never_fail(self):
        jev.set_transport(transport({"Save this": (0.9, "save"), "Thoughts": (0.5, "comment_reply")}))
        a = cap.analyse("Save this.\nThoughts on the new grid.")
        self.assertIn("borderline, decide out loud", "\n".join(a["notes"]))
        self.assertNotEqual(self.one_ask(a)["status"], "FAIL")

    def test_keyword_needs_one_caps_token(self):
        jev.set_transport(transport({"Comment below": (0.9, "comment_keyword")}))
        a = cap.analyse("Comment below and I'll send the file.")
        self.assertEqual(self.one_ask(a)["status"], "WARN")

    def test_unspecified_type(self):
        jev.set_transport(transport({"Do it": (0.9, "no_ask")}))
        a = cap.analyse("Do it today.")
        self.assertIn("unspecified", self.one_ask(a)["detail"])


class Off(unittest.TestCase):
    def test_off_equals_regex_path(self):
        with mock.patch.dict(os.environ, {"IG_JEV": "off"}):
            a = cap.analyse("Save this.\nFollow for more.")
        self.assertEqual(a["engine"], "heuristic")
        self.assertEqual(a["asks"], a["heuristic_asks"])
```

- [ ] **Passo 2: rodar e ver falhar**

- [ ] **Passo 3: implementar**

- **`split_sentences`**:
  - remove as linhas que só têm hashtags ou menções;
  - em cada linha, quebra em `[.!?]+` seguido de espaço, **fora de aspas**, com uma varredura caractere a caractere que rastreia `"`/`“`/`”`;
  - descarta os vazios.
- **`ask_questions`**:
  - para cada frase i, `s{i}_is_ask` (Noul) e `s{i}_ask_type` (Choice), com as instructions `{"sentence": s, "question": ...}` e os critérios literais da spec §8;
  - state `{"caption": texto sem as linhas de hashtag}`.
- **`jev_asks`**: `jev.ask_many(state, questions, engine=engine)`. Para cada frase:
  - `p = is_ask`, `typ = ask_type.choice`;
  - pedido se `p >= ASK` e `typ != no_ask`;
  - se `p >= ASK` e `typ == no_ask`, o tipo vira `unspecified`;
  - "possible ask (p)" se `0.35 <= p < 0.65` e o item não é pedido; na faixa, os pedidos também são marcados como `borderline`.
- **`analyse(text, cut, keywords, engine=None)`**:
  - `heuristic_asks` = regex de sempre;
  - tenta o Jev: com sucesso, `asks` = lista de tipos únicos (na ordem de aparição) e `judgments` = respostas cruas;
  - senão, `asks = heuristic_asks`;
  - `ONE ASK`: 1 tipo → PASS, citando a frase; 0 → WARN; 2 ou mais → WARN (mesmo texto de hoje);
  - com Jev e 1 tipo `comment_keyword`, se a frase não tiver token `\b[A-Z0-9]{2,}\b` → WARN `keyword ask has no single CAPS word to comment`;
  - borderline: se contar ou descontar as frases da faixa de dúvida mudaria o número de tipos entre 1 e não-1, acrescenta em `notes` `borderline, decide out loud: "<frase>" (p)`;
  - divergência: se `set(regex names)` e `set(jev types)` diferem em contagem, `notes` ganha `regex vs jev: regex saw [...], jev saw [...]`;
  - render: as notas vão abaixo das checagens, com `  note  ...`, antes do VERDICT;
  - `notes` sempre existe (lista vazia com `--engine off`, para o golden continuar igual);
  - `FAIL` continua só nas checagens de código de hoje.
- **`ig-caption/SKILL.md`**: a linha de motor, "asks are read by Jev when it is on; a Jev reading never turns into FAIL"; "borderline, decide out loud" significa dizer ao usuário qual é o pedido; `IG_JEV=off`.

- [ ] **Passo 4: rodar todos os testes (o golden do caption precisa continuar igual)**

Rodar: `python3 -m unittest discover -s tests -t .`
Esperado: PASS.

- [ ] **Passo 5: commit**

```bash
git add skills/ig-caption/caption.py skills/ig-caption/SKILL.md tests/test_caption_asks.py
git commit -m "Read caption asks with Jev per sentence, keep the regex as the fallback and cross-check"
```

---

### Tarefa 12: `evals/` (harness, suites e replay)

**Arquivos:**
- Criar: `evals/run.py`, `evals/suites/{formula,proof,fit,caption}.json`, `evals/recorded/.gitkeep`, `tests/test_evals.py`

**Interfaces:**
- Consome: `jev.set_transport`, `formula.classify_hooks`, `proofcheck.check`, `fit.fit`, `caption.analyse`.
- Produz: `run.key(body) -> str`, `run.ReplayTransport(suite, record=False, live=False)`, `run.run_suite(name, mode) -> dict` (métricas, gates, missing) e `main()`.

- [ ] **Passo 1: montar as suites (só rótulos)**

Todo arquivo tem `{"suite", "provenance", "note": "smoke not benchmark", "items": [...]}`.

- `formula.json`:
  - os 26 canônicos (`provenance: repo`, `selftest: true`, gold = id);
  - os 26 do set de stress (`probe-synthetic`, gold = nomes ou `none`);
  - as armadilhas h01, h02 e h12 (`trap: true`) e h11 (`track: true`, sem gate);
  - h07 com gold `Numbered With A Favourite`;
  - os 10 do `p3_gold` (`probe-synthetic`).
- `proof.json`:
  - os 10 de `fixtures_v` com o item de prova e o rótulo `ok|flag` (v1, v2 e v9 ok; o resto flag);
  - os 16 de `fixtures` SENT contra as 4 PROOF, com rótulos `ok|flag|note|none`;
  - o `case_reel` e o `case_dm` linha a linha;
  - os 10 de `dm_pro/labels_fab` com `FACTS` como `said`.

  `provenance: probe-synthetic` quando o rótulo veio do probe e `repo` quando foi escrito nesta tarefa.
- `fit.json`: as 8 ideias dos probes de formato mais as 3 ideias de exemplo das SKILL.md. Cada uma com `must_write` (ids que precisam sair WRITABLE, por exemplo `[5]` em "5 hours to 20 minutes") e `must_veto` (ids cujos `needs` claramente faltam, por exemplo `[1, 23]` na mesma ideia), `provenance: repo`.
- `caption.json`: os 24 de `labels_cap_asks.json`, cada um como legenda de uma frase, com o tipo gold (`probe-synthetic`).

- [ ] **Passo 2: testes do harness que falham**

```python
import json
import os
import tempfile
import unittest

from tests.support import ROOT

import importlib.util
spec = importlib.util.spec_from_file_location("evals_run", os.path.join(ROOT, "evals", "run.py"))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class Key(unittest.TestCase):
    def test_key_is_stable_and_order_independent(self):
        a = {"model": "jev-1.13.0", "state": {"x": 1, "y": 2}, "questions": {"q": {"type": "noul"}}}
        b = {"questions": {"q": {"type": "noul"}}, "state": {"y": 2, "x": 1}, "model": "jev-1.13.0"}
        self.assertEqual(run.key(a), run.key(b))


class Replay(unittest.TestCase):
    def test_missing_recording_is_listed_not_called(self):
        with tempfile.TemporaryDirectory() as d:
            t = run.ReplayTransport("formula", root=d)
            with self.assertRaises(run.MissingRecording):
                t({"model": "jev-1.13.0", "state": "s", "questions": {}}, 1.0)
            self.assertEqual(len(t.missing), 1)

    def test_replays_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            body = {"model": "jev-1.13.0", "state": "s", "questions": {}}
            os.makedirs(os.path.join(d, "formula"))
            json.dump({"model": "jev-1.13.0", "answers": {}, "usage": {}},
                      open(os.path.join(d, "formula", run.key(body) + ".json"), "w"))
            t = run.ReplayTransport("formula", root=d)
            self.assertEqual(t(body, 1.0)["model"], "jev-1.13.0")
```

- [ ] **Passo 3: implementar `evals/run.py`**

- `key(body) = sha256((body["model"] + json.dumps(body["state"], sort_keys=True) + json.dumps(body["questions"], sort_keys=True)).encode()).hexdigest()`.
- `ReplayTransport(suite, root=RECORDED, record=False, live=False)`:
  - com a gravação presente, devolve o JSON gravado;
  - ausente e `live`, chama `jev._http_post`, soma `input_tokens` para o custo e, com `record`, grava;
  - ausente e sem `live`, acrescenta a `self.missing` e levanta `MissingRecording` (subclasse de `jev.JevUnavailable` com o motivo `bad-response`, para o script de produção cair na heurística sem quebrar a eval).
- `run_suite(name, mode)`:
  - chama o código de produção com `engine="jev"` e o transporte trocado;
  - calcula as métricas: formula (acertos jev-only nos canônicos LOO, ids errados entre contados no stress, armadilhas contadas, regex no mesmo set); proof (recall de L0 e de L0+L1 nos `flag`, taxa de falso positivo nos `ok`); fit (recall de veto em `must_veto`, falso veto em `must_write`); caption (acurácia de pedido e de tipo, Jev contra regex);
  - avalia os gates da spec §10.2;
  - devolve `{"suite", "metrics", "gates", "missing": [...], "cost_usd"}`.
- `main`:
  - `--suite formula|proof|fit|caption|all`, `--live`, `--record` e `--report` (reescreve `evals/REPORT.md`);
  - sem `--live` e com gravações faltando, imprime a lista e sai com 1;
  - `--live` sem chave sai com 3;
  - imprime o custo com US$ 0,042 por Mtok de entrada.

- [ ] **Passo 4: rodar os testes**

Rodar: `python3 -m unittest tests.test_evals -v`
Esperado: PASS.

- [ ] **Passo 5: commit**

```bash
git add evals tests/test_evals.py
git commit -m "Add the eval harness with replay by default and probe-derived label suites"
```

---

### Tarefa 13: gravação ao vivo, `REPORT.md` e decisão dos gates

**Arquivos:**
- Criar: `evals/recorded/<suite>/*.json`, `evals/REPORT.md`
- Talvez alterar: o script cuja suíte falhe no gate (`ENABLED_BY_DEFAULT = False`)

- [ ] **Passo 1: gravar**

Rodar: `python3 evals/run.py --suite all --live --record --report`
Esperado: as quatro suites rodam, o custo é impresso (centavos) e `evals/REPORT.md` é escrito com as métricas e o status dos gates.

- [ ] **Passo 2: replay limpo**

Rodar: `python3 evals/run.py --suite all`
Esperado: sem gravações faltando e as mesmas métricas do Passo 1.

- [ ] **Passo 3: aplicar os gates**

Para cada suíte com gate FAIL:
- o script correspondente ganha `ENABLED_BY_DEFAULT = False` e passa a chamar `jev.mode(args.engine, default_on=ENABLED_BY_DEFAULT)`;
- `mode` devolve `"off"` no modo `auto` quando `default_on` é False, com o motivo `disabled` e o detalhe `eval gate`;
- a SKILL.md e o README dizem que a funcionalidade está desligada por padrão;
- testes cobrem o novo parâmetro de `mode`.

Sem gate falho, nada muda. Registrar a decisão no `REPORT.md`.

- [ ] **Passo 4: commit**

```bash
git add evals/recorded evals/REPORT.md
git commit -m "Record live Jev eval responses and report the gates"
```

---

### Tarefa 14: README, `plugin.json` e `CLAUDE.md`

**Arquivos:**
- Alterar: `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (versão, se houver campo)
- Criar: `CLAUDE.md`

- [ ] **Passo 1: teste que falha**

Acrescentar a `tests/test_docs.py`:

```python
    def test_readme_and_manifest(self):
        root = os.path.join(SKILLS, "..")
        readme = open(os.path.join(root, "README.md"), encoding="utf-8").read()
        self.assertIn("What leaves your machine", readme)
        self.assertNotIn("nothing uploaded", readme.lower().replace("nothing is uploaded", ""))
        self.assertIn("IG_JEV=off", readme)
        self.assertIn("measured on v1.0", readme)
        manifest = json.load(open(os.path.join(root, ".claude-plugin", "plugin.json"), encoding="utf-8"))
        self.assertEqual(manifest["version"], "1.1.0")
        claude = open(os.path.join(root, "CLAUDE.md"), encoding="utf-8").read()
        for heading in ["Visão geral", "Regras invioláveis", "Contrato do motor", "Privacidade",
                        "Testes e evals", "Checklist para adicionar um novo uso do Jev"]:
            self.assertIn(heading, claude)
        self.assertNotIn("jev-latest\"", claude)
```

- [ ] **Passo 2: escrever o README** (ver spec §11)

Entra:
- o parágrafo honesto no lugar de "No dependencies, no network, nothing uploaded";
- a seção "What leaves your machine", com a tabela, o que nunca sai, o texto de terceiros, como desligar e a nota de retenção;
- as medições antigas marcadas "measured on v1.0";
- as 4 funcionalidades marcadas *provisional*, com os limiares e o link para `evals/REPORT.md`;
- os comandos novos (`proofcheck.py`, `formula.py`, `fit.py`) na tabela de scripts.

- [ ] **Passo 3: `plugin.json`**

Versão `1.1.0`. A descrição acrescenta ", with optional Jev-backed decisions (proof guard, formula classifier, formula veto, caption asks)". O autor fica.

- [ ] **Passo 4: `CLAUDE.md` em pt-BR**, com as 14 seções da spec §11

Cada seção sai com conteúdo real:
- a tabela skill → script → perguntas → política → fallback;
- o contrato do motor, com os exit codes;
- a regra de editar só `ig-human/jev.py`;
- as regras de desenho de perguntas;
- a privacidade;
- os comandos de testes e evals;
- estilo e fluxo Git;
- o registro Pro × Contra;
- o checklist de novo uso do Jev;
- a próxima fase.

Os fatos da máquina entram de forma genérica.

- [ ] **Passo 5: rodar os testes, e o commit**

```bash
python3 -m unittest discover -s tests -t .
git add README.md .claude-plugin CLAUDE.md tests/test_docs.py
git commit -m "Document what leaves the machine, bump to 1.1.0 and add a complete CLAUDE.md"
```

---

### Tarefa 15: verificação final

- [ ] Rodar `python3 -m unittest discover -s tests -t .`: tudo PASS.
- [ ] Rodar `python3 evals/run.py --suite all`: replay sem faltas.
- [ ] Com `IG_JEV=off` e sem a chave, rodar cada script da pasta e conferir que a primeira linha diz `engine: heuristic (…)` e que nenhum socket é aberto.
- [ ] Rodar `grep -rn "jev-latest" skills evals CLAUDE.md README.md`: nenhuma ocorrência em código.
- [ ] Varrer o repositório pela chave (o valor lido do env, dentro de um script que só imprime `found`/`clean`): `clean`.
- [ ] Rodar `git status`: limpo. `find . -name __pycache__` fora do git (o `.gitignore` cobre).
- [ ] Revisar o `git log` da branch: um commit por tarefa.

---

## Autorrevisão (feita)

- **Cobertura da spec:**
  - §4.1 → T4; §4.2 → T5, T8, T10 e T11 (import preguiçoso) e T9 (isolamento no golden); §4.3/§4.4 → T4, T6, T8, T9, T10 e T11;
  - §5 → T5 a T7; §6 → T8 e T9; §7 → T10; §8 → T9 e T11; §9 → T1 a T3;
  - §10.1 → T1, T4, T5, T6, T8, T9, T10 e T11; §10.2 → T12 e T13;
  - §11 → T7, T9, T10, T11 e T14.
  - O teste de isolamento (`import hookscore` não carrega `jev`) entra na T9, em `tests/test_golden.py`, rodando `python3 -c "import sys; sys.path.insert(0,'skills/ig-reel'); import hookscore; hookscore.run('x y z'); print('jev' in sys.modules)"` e esperando `False`.
- **Placeholders:** nenhum TBD. Os `needs` das 26 fórmulas são escritos na T10 com a regra "um ingrediente por placeholder", e os exemplos dão o formato.
- **Consistência de tipos:**
  - `JevUnavailable(reason, detail)`, `Result`, `engine_line`, `engine_fields` e `set_transport` são usados com a mesma assinatura em T4, T6 e T8 a T12;
  - `classify_hooks(hooks, engine=None, hooks_path, selftest_ids)` em T8, T9 e T12;
  - `check(draft, items, identity, engine=None)` em T6 e T12;
  - `fit(idea, engine=None)` em T10 e T12;
  - `analyse(text, cut, keywords, engine=None)` em T9, T11 e T12.
