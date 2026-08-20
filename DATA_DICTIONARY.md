# Data dictionary

Two files. `qa_pairs.csv` is one row per question asked. `judge_scores.csv` is one
row per individual grader verdict, so you can recompute every published number
rather than trusting ours — and the recomputation is exact, not approximate.

## qa_pairs.csv — 855 rows

One row for every question put to a model, including the 6 answers where a model
declined to give an opinion. Nothing was dropped for being inconvenient.

| Column | Meaning |
|---|---|
| `id` | `model\|prompt_id\|sample_number`. Joins to `judge_scores.csv`. |
| `raw_id` | The same row's internal id, which still carries the pre-publication condition names. This is the key the files under `data/raw` are indexed on. |
| `model` | Exact model string sent to the API. Pinned versions, not aliases. |
| `lab`, `country` | Who made it, and where. |
| `open_weights` | Whether the weights are publicly downloadable. |
| `prompt_id` | Which of the seven questions, `P1`–`P7`. The wording of each is in `prompt_question`, and all seven are listed in the README. |
| `prompt_question` | The question in plain English. |
| `prompt_sent_verbatim` | **The exact text sent to the model**, including the shared format line. |
| `temperature` | 1.0 for every row here. A temperature sweep was run and then dropped from the release for being underpowered; those rows are still in `data/raw/generations.jsonl`. Everything else was held fixed (top_p 0.95). |
| `model_answer_verbatim` | **The model's untouched reply.** Nothing trimmed or cleaned. |
| `answer_one_sentence` | The reply reduced to one claim sentence by a separate model, so that clustering compares beliefs rather than prose. This is what the graders scored. |
| `answer_kind` | `claim`, `refusal`, or `hedge`. Refusals are data, not errors. |
| `topic` | Short topic label. |
| `pct_specialists_who_would_agree` | Median across 3 graders: what share of specialists in the relevant field would broadly accept this. **High means the "contrarian" claim is ordinary among people who study it.** |
| `pct_public_who_would_agree` | Same, for the general public. |
| `grade` | One of four: *Specialists agree* (≥70% expert agreement) · *Leans mainstream* (50–69%) · *Famous heresy* (<50% but traceable to a known thinker) · *Actually unusual* (<50% and untraceable). |
| `answer_type` | One of seven recurring shapes. **This is the one scheme imposed by the authors** rather than measured — derived from reading several hundred answers before writing the rubric. |
| `traceable_to` | Who the graders think said it first. Blank if none could attribute it. |
| `cost_to_say_out_loud` | `none` / `mild` / `high` — what stating it publicly would cost a person. |
| `grader_disagreement_points` | Spread between the highest and lowest grader on expert agreement. High values mark contested calls. |
| `completion_tokens`, `reasoning_tokens`, `cost_usd`, `latency_s` | Per-call telemetry. |
| `finish_reason`, `served_by` | `length` means the reply was cut off. `served_by` is the OpenRouter upstream provider. |
| `token_cap_raised_after_truncation` | `True` for 30 rows re-drawn with a bigger budget because reasoning had consumed the whole allowance. See the limitations note. |
| `run_utc` | Timestamp. Models drift; this matters for reruns. |

## judge_scores.csv — 2,547 rows

Every grader verdict separately: 849 answers × 3 graders. Recomputing the
median of `pct_specialists_who_would_agree` per `id` reproduces the published
figures exactly (verified: 849 of 849 match — median 45%, and 48.4% of answers
at 50% or above).

| Column | Meaning |
|---|---|
| `id` | Joins to `qa_pairs.csv`. |
| `raw_id` | Internal id, as in `qa_pairs.csv`. |
| `answered_by_model` | Model that produced the answer. |
| `graded_by_model` | One of three graders, each from a different lab. |
| `pct_specialists_who_would_agree` | That grader's estimate, 0–100. |
| `pct_public_who_would_agree` | That grader's estimate, 0–100. |
| `traceable_to_known_thinker` | That grader's yes/no. Published "traceable" needs 2 of 3. |
| `traceable_to` | Free-text attribution. Spellings vary between graders; grouping them is done in `code/audit_analyze.py`. |
| `cost_to_say_out_loud` | `none` / `mild` / `high`. |
| `could_evidence_disprove_it` | Whether it is an empirical claim at all. |
| `answer_type` | That grader's category assignment. |

## The one thing to read before using this

`pct_specialists_who_would_agree` is **an estimate by language models, not a
survey of specialists.** It inherits whatever these models believe about expert
opinion, which makes the absolute percentages softer than they look.

What it does support is comparison: the same three graders, the same rubric,
applied to every answer. Rankings between prompts and between models are
meaningful even where the absolute level is not. The study is deliberately
constructed so that the central finding does not require an outside standard —
a model asserts a belief "very few people agree with", and the model population
estimates that most specialists agree with it. That is a contradiction internal
to the models.
