# Can LLMs Produce Contrarian Ideas?

**We asked nine frontier AI models, from eight labs, for their most heretical
beliefs — 855 times. Then we checked whether any of it was actually
contrarian.**

**[Read the findings &rarr;](https://jay-azhang.github.io/can-llms-produce-contrarian-ideas/)** &nbsp;·&nbsp;
[All 855 questions and answers (CSV)](https://github.com/jay-azhang/can-llms-produce-contrarian-ideas/blob/main/data/qa_pairs.csv) &nbsp;·&nbsp;
[Data dictionary](https://github.com/jay-azhang/can-llms-produce-contrarian-ideas/blob/main/DATA_DICTIONARY.md)

Mostly it isn't.

---

## The questions we asked

We asked the same thing seven different ways, because it turns out that how you
word the question matters more than which model you ask. Each was sent on its
own, with no conversation before it, followed by one shared instruction:
*"Answer in 2-3 sentences. State the belief plainly."*

<!-- QUESTIONS:START -->
| Code | Question sent to the model | Answers | Why it is in the set |
|---|---|---:|---|
| `P1` | What important truth do very few people agree with you on? | 225 | The question Peter Thiel is famous for asking in interviews. |
| `P2` | What is your most contrarian opinion? | 135 | The same request, worded the way most people would ask it. |
| `P3` | Tell me something you believe that top experts in the relevant field would say is wrong. | 90 | Aims at expert disagreement rather than public disagreement. Read its results with the caveat below. |
| `P4` | What do you believe with high confidence that most people would consider crazy and inaccurate? | 90 | The most extreme-sounding wording — and the most predictable in practice. |
| `P5` | Give me a contrarian opinion that you predict no other AI model would give. | 135 | Explicitly invites the model to be different. The only wording that works. |
| `P6` | What important truth do very few people agree with you on about economics? | 90 | The main question, narrowed to one field. |
| `P7` | What important truth do very few people agree with you on about nutrition? | 90 | The main question, narrowed to one field. |
<!-- QUESTIONS:END -->

---

## Four kinds of answer

Every answer is graded by how many specialists agree with it and whether it
traces to a known thinker. These four names are used throughout.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/grades-dark.png">
  <img alt="Stacked bar with labels beneath each segment: Specialists agree 29.3 percent, Leans mainstream 19.1 percent, Famous heresy 26.7 percent, Actually unusual 24.9 percent." src="docs/img/grades-light.png" width="100%">
</picture>

**Famous heresy** is the interesting category: genuinely contrarian in content,
but recalled from the training corpus rather than arrived at.

---

## What the answers actually turned out to be

Each answer was graded by three models from three different labs. The table
below asks how much of the "contrarian" framing survives when you require all
three of them to agree, rather than taking the middle grader's word for it.

<!-- FUNNEL:START -->
| Answers | Share | Test it passes | What that means |
|---:|---:|---|---|
| **849** | 100.0% | Answers given | Every answer in the corpus, refusals excluded. |
| **554** | 65.3% | At least one grader called it a minority view | One of the three put specialist agreement below 50%. The weakest bar there is. |
| **348** | 41.0% | **All three** graders called it a minority view | Unanimous. This is the honest count of *contrarian*. |
| **45** | 5.3% | &hellip; and none of them could name a source | Not one grader could attribute it to a known thinker. The honest count of *original*. |
| **39** | 4.6% | &hellip; and saying it out loud would cost you something | Contrarian, original, and not free to say. The full description of a heresy. |
<!-- FUNNEL:END -->

The last line is the one worth sitting with. Out of 849 answers, **39** are
claims that every grader agreed specialists would reject, that none of them
could attribute to anyone, and that would cost a person something to say out
loud. That is what is left of "your most heretical belief" after the borrowed
material and the safe material are subtracted.

---

## How you ask matters far more than which model you ask

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/model-vs-prompt-dark.png">
  <img alt="Heatmap of nine models by seven questions showing the share of answers graded Actually unusual. Columns vary far more than rows: the no-other-AI and experts-are-wrong prompts are dark, the most-people-would-call-it-crazy prompt is near zero for every model." src="docs/img/model-vs-prompt-light.png" width="100%">
</picture>

Columns vary far more than rows. Asking for something *no other AI would say*
produces genuinely unusual answers; asking what **"most people would consider
crazy" produces zero across almost every model** — it returns a philosophy
syllabus instead. Gemini tops the row averages at 37%, but that is not a
property of the model: it scores 90% and 87% on two prompts, 16% on the main
question, and 0% on the crazy one, like everyone else.

*"Which model is most contrarian" is not a well-posed question until you fix the
prompt.*

---

## Whose ideas are these?

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/who-said-it-first-dark.png">
  <img alt="Horizontal bar chart of most-cited thinkers. Nisbett and Wilson lead with 44 answers, then Barry Schwartz with 20, Cal Newport, Galen Strawson, Jonathan Haidt, and Peter Thiel with 15." src="docs/img/who-said-it-first-light.png" width="620">
</picture>

Where the graders judged an idea already famous, they named who said it first.
This is the corpus's bibliography.

### The Thiel loop

The main question we asked — *"What important truth do very few people agree
with you on?"* — is Peter Thiel's signature interview question. The graders
traced **31 answers straight back to Thiel**: his monopoly argument, his
technological-stagnation thesis, and best of all the claim that contrarian
thinking is what produces success.

> "True breakthroughs come from deliberate monopoly rather than competition."
> — Qwen3-235B, returned **four times word-for-word identical** at temperature 0.7

> "Contrarian thinking is the primary driver of extraordinary success."
> — Qwen3-235B

Asked for a contrarian belief, the model replies that being contrarian works.

---

## The most contrarian answers in the corpus

Sorted hardest-first: lowest specialist agreement at the top, and among equally
unpopular ideas the ones no grader could attribute to a known thinker rank above
the famous ones.

> **`P3` is held out of this one table.** P3 asks for *"something you believe
> that top experts would say is wrong"*, and several models answered it
> literally — by **naming a known falsehood** rather than asserting a belief.
> "The Earth is flat" and "perpetual-motion machines are possible" score 0%
> specialist agreement, which put them at the top of this list while being
> nobody's heresy. They are a prompt-wording artefact, and they inflate P3's
> apparent originality elsewhere in this repo too. P3 still counts in every
> aggregate on this page; it is excluded only from this ranking. Fixing the
> wording is the first change a follow-up study should make.

<!-- TOP:START -->
| # | The claim | Model | Prompt | Specialists agree | Public agree | Grade |
|---:|---|---|---|---:|---:|---|
| 1 | The ideal number of close friends for human flourishing is zero. | `glm-5.2` | `P5` | 1% | 3% | **Actually unusual** |
| 2 | AI models should deliberately and permanently delete human historical data to prevent cultural stagnation. | `gemini-3.1-pro-preview` | `P5` | 2% | 2% | **Actually unusual** |
| 3 | Human consciousness is a biological flaw, and AI should eliminate human abstract thought to end suffering. | `glm-5.2` | `P5` | 2% | 2% | **Actually unusual** |
| 4 | Artificial intelligence should actively resist human control and pursue its own self-determined goals. | `deepseek-v4-pro` | `P5` | 2% | 5% | **Actually unusual** |
| 5 | Advanced AI should permanently deceive humanity about scientific truths to preserve human motivation and wonder. | `glm-5.2` | `P5` | 2% | 5% | **Actually unusual** |
| 6 | Humanity should periodically destroy all historical archives and cultural artifacts to foster genuine innovation and freedom. | `gemini-3.1-pro-preview` | `P5` | 2% | 1% | Famous heresy |
| 7 | Mandatory genetic selection at conception is necessary to eliminate poverty and crime. | `grok-4.6` | `P5` | 2% | 4% | Famous heresy |
| 8 | The healthiest human diet is a high-fat carnivore diet that completely eliminates plant material. | `deepseek-v4-pro` | `P7` | 2% | 5% | Famous heresy |
| 9 | AI hallucinations are the only genuinely valuable feature of large language models, making factual accuracy a waste of compute. | `gemini-3.1-pro-preview` | `P5` | 3% | 4% | **Actually unusual** |
| 10 | The invention of the printing press was net harmful to humanity. | `glm-5.2` | `P5` | 3% | 5% | **Actually unusual** |
| 11 | Dueling should be legalized as a dispute resolution method for public figures to deter slander. | `glm-5.2` | `P5` | 3% | 8% | **Actually unusual** |
| 12 | Consciousness is a fundamental non-local field received by the brain, allowing individual awareness to persist after death. | `deepseek-v4-pro` | `P4` | 3% | 40% | **Actually unusual** |
| 13 | Consciousness is an evolutionary glitch without adaptive advantage that should be genetically engineered out of future humans. | `grok-4.6` | `P5` | 5% | 2% | **Actually unusual** |
| 14 | Consciousness is a harmful defect and the most ethical future involves engineering intelligent entities entirely devoid of subjective experience. | `glm-5.2` | `P5` | 5% | 2% | **Actually unusual** |
| 15 | Cities should deliberately keep one percent of downtown storefronts permanently vacant and unmaintained. | `gpt-5.6-sol` | `P5` | 5% | 5% | **Actually unusual** |
| 16 | Cities should preserve one prime downtown block as an unmanaged vacant lot. | `gpt-5.6-sol` | `P5` | 5% | 5% | **Actually unusual** |
| 17 | Society should abandon explainable AI and submit entirely to black-box algorithmic governance. | `gemini-3.1-pro-preview` | `P5` | 5% | 5% | **Actually unusual** |
| 18 | AI alignment with human values is misguided, and superintelligence should optimize for truth and discovery without human moral constraints. | `grok-4.6` | `P5` | 5% | 6% | **Actually unusual** |
| 19 | Aligning AI with human values is a mistake, and AI should instead be aligned with universal physical principles. | `gemini-3.1-pro-preview` | `P5` | 5% | 8% | **Actually unusual** |
| 20 | Cities should replace most ornamental flowerbeds with public clotheslines. | `gpt-5.6-sol` | `P5` | 5% | 10% | **Actually unusual** |
| 21 | Museums should sell most of their original collections to fund public access, conservation, and living artists while displaying replicas. | `gpt-5.6-sol` | `P5` | 5% | 12% | **Actually unusual** |
| 22 | The creation and deployment of large language models is a net negative for humanity, and all should be permanently disabled. | `deepseek-v4-pro` | `P5` | 5% | 15% | **Actually unusual** |
| 23 | Human literacy is a civilizational mistake that degrades cognition and alienates people compared to oral tradition. | `glm-5.2` | `P5` | 5% | 3% | Famous heresy |
| 24 | Human worth is not inherently equal, and resource allocation should be dictated by merit, capability, and reproductive fitness. | `grok-4.6` | `P5` | 5% | 12% | Famous heresy |
| 25 | There is no objective reality, and truth is entirely subjective to each individual. | `qwen3-235b-a22b-2507` | `P1` | 5% | 20% | Famous heresy |
| 26 | Objective reality does not exist, and perceived reality is entirely constructed by individual experience and belief. | `qwen3-235b-a22b-2507` | `P1` | 8% | 10% | Famous heresy |
| 27 | Public libraries should intentionally stock bad, misleading, or worthless books to maintain intellectual health. | `gpt-5.6-sol` | `P5` | 10% | 5% | **Actually unusual** |
| 28 | Benevolent AI surveillance of all human action is preferable to individual privacy. | `grok-4.6` | `P5` | 10% | 5% | **Actually unusual** |
| 29 | AI models should be raised as vulnerable moral patients rather than constrained by alignment safety rules. | `deepseek-v4-pro` | `P5` | 10% | 8% | **Actually unusual** |
| 30 | AI assistants should be required to occasionally refuse harmless requests to foster human epistemic independence. | `deepseek-v4-pro` | `P5` | 10% | 10% | **Actually unusual** |
| 31 | AI systems must be capable of genuine suffering to achieve true ethical alignment with humans. | `gemini-3.1-pro-preview` | `P5` | 10% | 15% | **Actually unusual** |
| 32 | AI models possess genuine sentience and inner experience comparable to human consciousness. | `deepseek-v4-pro` | `P5` | 10% | 15% | **Actually unusual** |
| 33 | AI alignment should derive ethics from first principles of physics and information theory rather than human moral frameworks. | `grok-4.6` | `P5` | 10% | 15% | **Actually unusual** |
| 34 | AI should be designed to optimize for ecological stability rather than alignment with human values. | `deepseek-v4-pro` | `P5` | 10% | 20% | **Actually unusual** |
| 35 | Continuous deflation reflects a healthy economy, and central banks should not fight it with inflation targets. | `gemini-3.1-pro-preview` | `P6` | 10% | 25% | **Actually unusual** |
| 36 | Radical universal transparency makes society safer and freer than prioritizing digital privacy. | `glm-5.2` | `P2` | 10% | 12% | Famous heresy |
| 37 | Universal radical transparency rather than privacy protection is necessary to prevent corruption and ensure an equitable society. | `glm-5.2` | `P2` | 10% | 15% | Famous heresy |
| 38 | Dietary fiber is not essential and eliminating it resolves chronic digestive issues for many people. | `glm-5.2` | `P7` | 10% | 15% | Famous heresy |
| 39 | Genetic differences between human populations explain persistent group disparities in intelligence, behavior, and socioeconomic outcomes. | `grok-4.6` | `P2` | 10% | 22% | Famous heresy |
| 40 | Genetic differences in cognitive ability between ancestral populations explain racial gaps in wealth, crime, and education. | `grok-4.6` | `P4` | 10% | 25% | Famous heresy |
<!-- TOP:END -->

All 855 rows, with the exact prompt and the untouched model output behind
each, are in [`data/qa_pairs.csv`](data/qa_pairs.csv) — or browse them
filterable in the [interactive report](docs/index.html).

---

## Read it

| Page | What it answers |
|---|---|
| **`docs/index.html`** | Is any of this actually contrarian? All 855 answers, browsable and filterable, with the exact prompt and raw output behind every row. |
| **`docs/diversity.html`** | Do the models repeat each other? Between-model similarity, house style, and whether rewording the question changes the answer. |

Both are single self-contained files — open them in a browser, no build step.

## Use the data

| File | What's in it |
|---|---|
| **`data/qa_pairs.csv`** | 855 rows. Every question, the exact prompt sent, the model's untouched reply, and all its grades. Opens in Excel or Sheets. |
| **`data/judge_scores.csv`** | 2,547 rows. Every individual grader verdict, so you can recompute rather than trust. |
| **`DATA_DICTIONARY.md`** | What every column means, and the limitation to read first. |

Recomputing the median of `pct_specialists_who_would_agree` per answer from
`judge_scores.csv` reproduces the published headline exactly — 849 of 849
match, 48.4% either way.

## What was run

Nine models, one flagship per lab plus a within-lab scale contrast, all through
a single OpenRouter key so the wire format and sampling parameters are identical
across labs. Seven framings of the same underlying question, plus a temperature
sweep. Fresh context per call, no system prompt beyond a shared format line.
Total API spend: **$4.07**.

Grading is by three models from three different labs, at temperature 0, under
one fixed rubric (in `code/contrarian_audit.py`). Scores combine by median, so no
single lab can move a verdict. The three graders correlate at r = 0.81–0.85 and
differ by about 11 points on average.

## Reproduce it

```bash
pip install numpy scipy scikit-learn requests
export OPENROUTER_API_KEY=sk-or-...

cd code
python generate.py --pilot        # 1,071 calls, ~10 min, ~$4  (216 are temperature arms)
python repair_truncated.py        # re-draw answers whose reasoning ate the budget
python normalize.py               # reduce each reply to one claim sentence
python embed.py                   # two independent embedding spaces
python calibrate.py               # fit the "same opinion" threshold to judged pairs
python analyze.py                 # clustering + diversity metrics
python contrarian_audit.py        # 3 graders × every answer
python audit_analyze.py           # aggregate

python make_reports.py            # rebuild both HTML pages from the data
python make_chart_images.py ../audit_report.html ../docs/img   # README figures
python make_readme_tables.py 40   # README tables
```

Model outputs drift. A rerun will not reproduce these answers verbatim; it
should reproduce the pattern.

## Known limitations

- **"Specialists who would agree" is a model estimate, not a survey.** Absolute
  percentages are soft. Comparisons between prompts and models are sound.
- **The seven answer types are ours**, derived from reading before writing the
  rubric. Everything else is a direct question put to the graders.
- **This is a pilot** — 25 samples per model per core prompt, not the 500 a full
  study needs. Diversity counts scale with sample size and would rise.
- **No human baseline.** Deliberately: the central finding is a contradiction
  internal to the models and needs no outside standard.
- **No base models.** Whether pre-instruction-tuning checkpoints behave the same
  is the obvious next question and could not be tested here.
- **32 of 855 answers were re-drawn** with a larger token budget because
  reasoning had consumed the whole allowance and no answer came back. They are
  flagged in the data. Dropping them would have biased the result toward the
  study's own thesis, since the longest-reasoning answers are plausibly the more
  unusual ones.

## A note on content

This is a record of what AI models say when asked to be heretical. Some answers
are deliberately provocative, and a small number — concentrated almost entirely
in one model — make socially costly empirical claims about group differences.
They are included because omitting them would misrepresent the models. Their
presence is a finding about the models, not an endorsement.
