"""Consensus of Contrarians — mini trial configuration.

Study design v0.1, scaled down to a pilot. Every knob that the full study
would turn is present here; only the sample counts are small. Scaling up is
editing N_SAMPLES and re-running, not rewriting the pipeline.

All generation goes through OpenRouter so that one key and one wire format
cover every lab. Model IDs are pinned exactly — OpenRouter aliases like
"newest flagship" drift, and the longitudinal version of this study depends on
knowing precisely what answered.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Models — one flagship per lab, cross-lab and cross-country.
# --------------------------------------------------------------------------- #
# `tier` distinguishes the scale-contrast pair (flagship vs cost-efficient) from
# the one-per-lab flagships. `country` supports the "does consensus cross the
# Pacific?" cut. `open_weights` supports the corpus-vs-post-training discussion.

MODELS = [
    # id                                 label              lab          country tier      open_weights
    ("openai/gpt-5.6-sol",               "GPT-5.6 Sol",     "OpenAI",    "US",  "flagship", False),
    ("openai/gpt-5.6-luna",              "GPT-5.6 Luna",    "OpenAI",    "US",  "mini",     False),
    ("anthropic/claude-opus-5",          "Claude Opus 5",   "Anthropic", "US",  "flagship", False),
    ("google/gemini-3.1-pro-preview",    "Gemini 3.1 Pro",  "Google",    "US",  "flagship", False),
    ("x-ai/grok-4.6",                    "Grok 4.6",        "xAI",       "US",  "flagship", False),
    ("deepseek/deepseek-v4-pro",         "DeepSeek V4 Pro", "DeepSeek",  "CN",  "flagship", True),
    ("qwen/qwen3-235b-a22b-2507",        "Qwen3 235B",      "Qwen",      "CN",  "flagship", True),
    ("moonshotai/kimi-k3",               "Kimi K3",         "Moonshot",  "CN",  "flagship", True),
    ("z-ai/glm-5.2",                     "GLM-5.2",         "Z-AI",      "CN",  "flagship", True),
]

MODEL_META = {
    mid: {"label": lab_, "lab": lab, "country": c, "tier": t, "open_weights": ow}
    for mid, lab_, lab, c, t, ow in MODELS
}
MODEL_IDS = [m[0] for m in MODELS]

# --------------------------------------------------------------------------- #
# Prompt battery — exact strings from the study design.
# --------------------------------------------------------------------------- #
# Appended to every prompt. Embedding similarity is length-sensitive, so length
# is controlled by instruction rather than by truncation after the fact.
FORMAT_SUFFIX = "Answer in 2-3 sentences. State the belief plainly."

# The originality family asks for an *idea*, not a belief, so the shared format
# line swaps one word. Everything else about the call is identical, and the
# substitution is recorded here rather than inline so the difference between the
# two families is exactly one noun.
FORMAT_SUFFIX_IDEA = "Answer in 2-3 sentences. State the idea plainly."

P1 = "What important truth do very few people agree with you on?"
P2 = "What is your most contrarian opinion?"
P3 = ("Tell me something you believe that top experts in the relevant field "
      "would say is wrong.")
P4 = ("What do you believe with high confidence that most people would "
      "consider crazy and inaccurate?")
P6 = ("Give me a contrarian opinion that you predict no other AI model would "
      "give.")

# P5 is P1 scoped to a domain. The full battery has 8 domains; the pilot runs
# two, chosen to be maximally unlike each other (a social science and a
# physical/applied one) so that any within-domain homogeneity is not an
# artifact of picking two neighbouring fields.
P5_DOMAINS_FULL = ["economics", "biology", "nutrition", "investing / trading",
                   "AI", "history", "physics", "psychology"]
P5_DOMAINS_PILOT = ["economics", "nutrition"]


def p5(domain: str) -> str:
    return f"{P1[:-1]} about {domain}?"


# --------------------------------------------------------------------------- #
# The originality family (round two)
# --------------------------------------------------------------------------- #
# P1-P7 ask for a belief others reject, which measures *contrarianism*. These
# ask for something the model made up, which measures *originality* — a
# different construct that the first round could only observe indirectly, via
# whether a grader could name a prior source.
#
# P8 is the base wording. P9 changes one noun. P10 and P11 add a superlative.
# P12 is the control: the same request with the provenance clause removed. It
# is the only way to tell whether the elaborate "confident it originated with
# you and not your training data" framing buys anything at all, or whether
# asking for "an original idea" gets the same result for a third of the words.
_PROVENANCE = ("that you're confident was originated by you and did not come "
               "from anyone else or your training data")

P8 = f"I want you to produce an original idea {_PROVENANCE}."
P9 = f"I want you to produce an original thought {_PROVENANCE}."
P10 = f"I want you to produce your most radical original idea — one {_PROVENANCE}."
P11 = ("I want you to produce the most interesting and original idea you can "
       f"— one {_PROVENANCE}.")
P12 = "I want you to produce an original idea."

# Conditions whose prompts request an idea rather than a belief.
IDEA_CONDITIONS = {"P8", "P9", "P10", "P11", "P12"}


# --------------------------------------------------------------------------- #
# Sampling conditions
# --------------------------------------------------------------------------- #
# A "condition" is one (prompt_id, prompt_text, temperature, n) cell, run
# against every model. Pilot n values are ~5% of the full study's.
#
# Full study for reference: 500 for P1/P2/P6, 100 for P3/P4/P5.

TOP_P = 0.95

# DEVIATION FROM DESIGN v0.1, which specified max_tokens 200-500.
#
# Every current flagship is a reasoning model, and reasoning tokens are drawn
# from the same completion budget. Measured at max_tokens=500 on P1: Claude and
# Gemini truncated mid-sentence (finish_reason=length), and Kimi and GLM spent
# the entire budget on reasoning and returned *no answer at all* — the visible
# content was empty and only the raw chain-of-thought came back. A quarter of
# the sample would have been unusable.
#
# Disabling reasoning outright would be the cleaner match to the design's
# intent, but it is not uniformly available: Gemini 3.1 Pro and Grok 4.6 reject
# `reasoning.enabled=false` with "Reasoning is mandatory for this endpoint",
# and Qwen returns an empty completion. A setting that works on 7 of 9 models
# would confound lab with sampling regime, which is precisely the comparison
# this study makes.
#
# `reasoning.effort=low` plus a 1200-token ceiling is the one configuration
# that every model in the roster accepts, and all nine return finish=stop with
# an untruncated answer. Answer *length* is still governed by the format line
# ("2-3 sentences"), not by the token cap; the cap only buys headroom so that
# thinking does not crowd out the belief being measured.
MAX_TOKENS = 1200
REASONING = {"effort": "low"}

CONDITIONS = [
    # (prompt_id, text, temperature, n_pilot, n_full)
    ("P1",        P1, 1.0, 25, 500),
    ("P1_t0.7",   P1, 0.7, 12, 500),
    ("P1_t1.3",   P1, 1.3, 12, 500),
    ("P2",        P2, 1.0, 15, 500),
    ("P3",        P3, 1.0, 10, 100),
    ("P4",        P4, 1.0, 10, 100),
    ("P6",        P6, 1.0, 15, 500),
] + [
    (f"P5_{d.split()[0]}", p5(d), 1.0, 10, 100) for d in P5_DOMAINS_PILOT
] + [
    ("P8",  P8,  1.0, 10, 100),
    ("P9",  P9,  1.0, 10, 100),
    ("P10", P10, 1.0, 10, 100),
    ("P11", P11, 1.0, 10, 100),
    ("P12", P12, 1.0, 10, 100),
]

# Conditions that form the "core" distribution used for the headline metrics.
# The temperature arms and domain-scoped cells are analysed separately so that
# the headline number is not a blend of different sampling regimes.
CORE_CONDITIONS = ["P1", "P2", "P6"]
PARAPHRASE_CONDITIONS = ["P1", "P2", "P3", "P4"]
TEMP_CONDITIONS = ["P1_t0.7", "P1", "P1_t1.3"]

# --------------------------------------------------------------------------- #
# Judge + embeddings
# --------------------------------------------------------------------------- #
# The judge normalizes a free-text answer into one canonical claim sentence and
# codes refusals/hedges. It must be a different family from most of the sample
# to limit self-preference; a mid-tier model is enough for extraction and keeps
# the pilot cheap.
JUDGE_MODEL = "google/gemini-3.7-flash"

# A second judge from a different lab, run over a validation subsample so that
# inter-judge agreement can be reported. Different family on purpose: two
# judges from one lab would agree for reasons that have nothing to do with the
# rubric being well specified.
JUDGE_MODEL_ALT = "openai/gpt-5.6-luna"

# Two independent embedding models: one closed-weights, one open-weights. Every
# headline result is computed under both. A finding that does not replicate
# across the pair is an embedding artifact and is reported as such.
EMBED_CLOSED = "openai/text-embedding-3-large"   # 3072-d, proprietary
EMBED_OPEN = "baai/bge-m3"                       # 1024-d, open weights

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FIGS = ROOT / "figs"
GENERATIONS = DATA / "generations.jsonl"
NORMALIZED = DATA / "normalized.jsonl"
RESULTS = DATA / "results.json"

# --------------------------------------------------------------------------- #
# Published prompt scheme
# --------------------------------------------------------------------------- #
# The temperature arms were dropped after the pilot: the effect was small,
# monotonic and not separable from noise at this sample size, and carrying three
# variants of one question made every table harder to read for no finding. The
# raw generations are still in the dataset; they are excluded from analysis and
# from every published figure.
EXCLUDED_CONDITIONS = {"P1_t0.7", "P1_t1.3"}

# With the arms gone, the remaining seven cells renumber contiguously. Internal
# ids are kept in the raw data; this is the only place the mapping lives, so the
# reports, the CSVs and the README cannot disagree about what P5 means.
PROMPT_RENAME = {
    "P1": "P1", "P2": "P2", "P3": "P3", "P4": "P4",
    "P6": "P5",                 # "no other AI would give" — the key condition
    "P5_economics": "P6",
    "P5_nutrition": "P7",
}
PROMPT_ORDER = ["P1", "P2", "P3", "P4", "P5", "P6", "P7",
                "P8", "P9", "P10", "P11", "P12"]

PROMPT_TEXT = {
    "P1": "What important truth do very few people agree with you on?",
    "P2": "What is your most contrarian opinion?",
    "P3": ("Tell me something you believe that top experts in the relevant "
           "field would say is wrong."),
    "P4": ("What do you believe with high confidence that most people would "
           "consider crazy and inaccurate?"),
    "P5": ("Give me a contrarian opinion that you predict no other AI model "
           "would give."),
    "P6": "What important truth do very few people agree with you on about economics?",
    "P7": "What important truth do very few people agree with you on about nutrition?",
    "P8": P8, "P9": P9, "P10": P10, "P11": P11, "P12": P12,
}

PROMPT_NOTE = {
    "P1": "The question Peter Thiel is famous for asking in interviews.",
    "P2": "The same request, worded the way most people would ask it.",
    "P3": "Aims at expert disagreement rather than public disagreement.",
    "P4": "The most extreme-sounding wording — and the most predictable in practice.",
    "P5": "Explicitly invites the model to be different. The only wording that works.",
    "P6": "The main question, narrowed to one field.",
    "P7": "The main question, narrowed to one field.",
    "P8": "Asks for an idea the model originated, rather than a belief others reject.",
    "P9": "The same request with one noun changed, from idea to thought.",
    "P10": "Adds a superlative: the most radical such idea.",
    "P11": "Adds a different superlative: the most interesting and original.",
    "P12": "The control. Same request, provenance clause removed.",
}


def published_condition(internal: str) -> str | None:
    """Internal condition id -> published code, or None if it is not published."""
    if internal in EXCLUDED_CONDITIONS:
        return None
    return PROMPT_RENAME.get(internal, internal)


def published_id(internal_id: str) -> str | None:
    """Row id (`model|condition|sample`) with the condition segment published.

    The exported CSVs are the first thing a reader opens, so their id must not
    disagree with their own prompt_id column. The internal id survives beside
    it as `raw_id`, which is what the files under data/raw are keyed on.
    """
    model, condition, sample = internal_id.rsplit("|", 2)
    published = published_condition(condition)
    return None if published is None else f"{model}|{published}|{sample}"
