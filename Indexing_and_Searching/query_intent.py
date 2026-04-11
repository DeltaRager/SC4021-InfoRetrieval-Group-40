"""
Query intent inference for dynamic hybrid search weighting.

Classifies each query as `keyword`, `semantic`, or `mixed` and emits
per-query alpha (BM25 weight) and beta (vector weight) for weighted RRF.

Design goals:
- Pure helper module: no Flask, no Solr, no network calls.
- Score-based heuristics: tuning means adjusting thresholds, not rewriting logic.
- Side-effect free and easy to unit test.

Usage::

    from query_intent import infer_intent, QueryIntentProfile

    profile = infer_intent("Why do LLMs hallucinate?")
    # profile.intent_label  => "semantic"
    # profile.alpha         => 0.3
    # profile.beta          => 0.7
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain vocabulary (kept in sync with nlp_utils.PROTECTED_QUERY_TERMS)
# ---------------------------------------------------------------------------

DOMAIN_ENTITY_TERMS: frozenset[str] = frozenset({
    "chatgpt", "openai", "claude", "anthropic", "gemini", "bard",
    "llama", "copilot", "mistral", "grok", "deepseek", "perplexity",
    "palm", "meta", "microsoft", "google", "deepmind", "xai",
    "agi", "llm", "gpt", "gpt-4", "gpt-3", "gpt4", "gpt3",
    "bert", "t5", "dall-e", "dalle", "whisper", "codex",
    "stable diffusion", "midjourney", "huggingface",
})

# ---------------------------------------------------------------------------
# Signal keywords
# ---------------------------------------------------------------------------

QUESTION_WORDS: frozenset[str] = frozenset({
    "why", "how", "what", "when", "where", "who", "which",
    "is", "are", "does", "do", "can", "should", "would", "could",
    "will", "explain", "describe", "tell",
})

COMPARISON_MARKERS: frozenset[str] = frozenset({
    "vs", "versus", "compare", "comparison", "compared",
    "better", "worse", "best", "worst", "difference", "between",
    "or", "over", "prefer", "prefer", "alternative", "alternatives",
    "similar", "similarity", "unlike", "like",
})

ANALYTICAL_MARKERS: frozenset[str] = frozenset({
    "why", "how", "explain", "because", "reason", "cause", "effect",
    "impact", "result", "benefit", "drawback", "advantage", "disadvantage",
    "future", "prediction", "trend", "analysis", "evaluate", "review",
    "opinion", "think", "believe", "suggest", "recommend",
})

# ---------------------------------------------------------------------------
# Configurable thresholds (can be overridden at call-site for testing)
# ---------------------------------------------------------------------------

# A query is considered "short / keyword-style" when token count ≤ this
DEFAULT_SHORT_TOKEN_THRESHOLD: int = 3

# Heuristic score at or above this → semantic
DEFAULT_SEMANTIC_SCORE_THRESHOLD: float = 2.0

# Heuristic score at or above this (but below semantic) → mixed
DEFAULT_MIXED_SCORE_THRESHOLD: float = 0.5

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class QueryIntentProfile:
    """Classification result for a single query."""

    intent_label: str           # "keyword" | "semantic" | "mixed"
    alpha: float                # BM25 weight for weighted RRF
    beta: float                 # vector weight for weighted RRF

    # Fired signal names and their contribution scores (for diagnostics)
    signals: dict[str, float] = field(default_factory=dict)

    # Raw query features extracted during scoring
    query_features: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def infer_intent(
    query: str,
    *,
    # Weight mappings – override via environment-variable-backed defaults in
    # hybrid_search.py; or pass directly here for isolated testing.
    keyword_alpha: float = 0.8,
    keyword_beta: float = 0.2,
    mixed_alpha: float = 0.5,
    mixed_beta: float = 0.5,
    semantic_alpha: float = 0.3,
    semantic_beta: float = 0.7,
    # Classification thresholds
    short_token_threshold: int = DEFAULT_SHORT_TOKEN_THRESHOLD,
    semantic_score_threshold: float = DEFAULT_SEMANTIC_SCORE_THRESHOLD,
    mixed_score_threshold: float = DEFAULT_MIXED_SCORE_THRESHOLD,
) -> QueryIntentProfile:
    """Infer query intent and return weights for weighted RRF.

    Args:
        query: Raw query string (before NLP processing).
        keyword_alpha / keyword_beta: Weights used for keyword queries.
        mixed_alpha / mixed_beta:     Weights used for mixed queries.
        semantic_alpha / semantic_beta: Weights used for semantic queries.
        short_token_threshold:  Queries with ≤ this many tokens are biased toward keyword.
        semantic_score_threshold: Total signal score ≥ this → semantic.
        mixed_score_threshold:    Total signal score ≥ this (but < semantic) → mixed.

    Returns:
        QueryIntentProfile with intent_label, alpha, beta, signals, query_features.
    """
    query = (query or "").strip()
    features = _extract_features(query)
    signals, score = _score_signals(features)

    # Classify based on score thresholds and short-query heuristic
    is_short = features["token_count"] <= short_token_threshold
    has_entity = features["entity_count"] > 0

    if score >= semantic_score_threshold:
        intent = "semantic"
        alpha, beta = semantic_alpha, semantic_beta
    elif score >= mixed_score_threshold:
        intent = "mixed"
        alpha, beta = mixed_alpha, mixed_beta
    elif is_short and has_entity and score < mixed_score_threshold:
        # Short entity-only query with no analytical/question structure → keyword
        intent = "keyword"
        alpha, beta = keyword_alpha, keyword_beta
    elif is_short and score < mixed_score_threshold:
        intent = "keyword"
        alpha, beta = keyword_alpha, keyword_beta
    else:
        # Longer query without clear signals → mixed
        intent = "mixed"
        alpha, beta = mixed_alpha, mixed_beta

    return QueryIntentProfile(
        intent_label=intent,
        alpha=alpha,
        beta=beta,
        signals=signals,
        query_features=features,
    )


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def _extract_features(query: str) -> dict[str, Any]:
    """Extract raw features from the query string."""
    tokens_raw = query.split()
    tokens_lower = [t.lower().strip(".,;:!?\"'()[]{}") for t in tokens_raw]
    tokens_alpha = [t for t in tokens_lower if t]

    char_len = len(query)
    token_count = len(tokens_alpha)

    # Question mark
    has_question_mark = "?" in query

    # Question word at start or anywhere
    first_token = tokens_alpha[0] if tokens_alpha else ""
    question_word_lead = first_token in QUESTION_WORDS
    question_word_any = any(t in QUESTION_WORDS for t in tokens_alpha)

    # Comparison markers
    comparison_count = sum(1 for t in tokens_alpha if t in COMPARISON_MARKERS)

    # Analytical markers
    analytical_count = sum(1 for t in tokens_alpha if t in ANALYTICAL_MARKERS)

    # Entity mentions (domain vocabulary)
    entity_count = sum(1 for t in tokens_alpha if t in DOMAIN_ENTITY_TERMS)
    # Also check bigrams for multi-word entities like "stable diffusion"
    bigrams = [f"{tokens_alpha[i]} {tokens_alpha[i+1]}" for i in range(len(tokens_alpha) - 1)]
    entity_bigram_count = sum(1 for bg in bigrams if bg in DOMAIN_ENTITY_TERMS)
    entity_count += entity_bigram_count

    # Sentence-like structure: starts with capital + has verb-like question word
    looks_like_sentence = (
        bool(tokens_raw) and tokens_raw[0][0].isupper()
        and (question_word_lead or has_question_mark)
    )

    # Pure keyword ratio: fraction of tokens that are known entities or very short
    keyword_token_count = sum(
        1 for t in tokens_alpha
        if t in DOMAIN_ENTITY_TERMS or len(t) <= 4
    )
    keyword_ratio = keyword_token_count / max(token_count, 1)

    # POS-derived verb features (spaCy, defensive)
    has_verb = False
    verb_count = 0
    verb_lemmas: list[str] = []
    pos_available = False
    try:
        from nlp_utils import extract_query_pos_features
        pos_feats = extract_query_pos_features(query)
        has_verb = pos_feats["has_verb"]
        verb_count = pos_feats["verb_count"]
        verb_lemmas = pos_feats["verb_lemmas"]
        pos_available = pos_feats["pos_available"]
    except Exception as exc:  # noqa: BLE001
        logger.debug("POS tagging unavailable for query intent; falling back: %s", exc)

    return {
        "char_len": char_len,
        "token_count": token_count,
        "has_question_mark": has_question_mark,
        "question_word_lead": question_word_lead,
        "question_word_any": question_word_any,
        "comparison_count": comparison_count,
        "analytical_count": analytical_count,
        "entity_count": entity_count,
        "looks_like_sentence": looks_like_sentence,
        "keyword_ratio": keyword_ratio,
        "first_token": first_token,
        # POS-derived verb features
        "has_verb": has_verb,
        "verb_count": verb_count,
        "verb_lemmas": verb_lemmas,
        "pos_available": pos_available,
    }


# ---------------------------------------------------------------------------
# Signal scoring
# ---------------------------------------------------------------------------

def _score_signals(features: dict[str, Any]) -> tuple[dict[str, float], float]:
    """Compute a semantic-intent score from extracted features.

    Positive scores push toward semantic; negative scores push toward keyword.
    Returns (signals_dict, total_score).
    """
    signals: dict[str, float] = {}

    # Leading question word is a strong semantic signal
    if features["question_word_lead"]:
        signals["question_word_lead"] = 1.5

    # Question mark is a moderate semantic signal (even without question word)
    if features["has_question_mark"]:
        signals["question_mark"] = 1.0

    # Any question word in query
    if features["question_word_any"] and not features["question_word_lead"]:
        signals["question_word_mid"] = 0.8

    # Comparison structure: "X vs Y", "compare A and B", "better than"
    if features["comparison_count"] >= 1:
        signals["comparison"] = 1.2 * features["comparison_count"]

    # Analytical markers: "why", "explain", "reason"
    if features["analytical_count"] >= 1:
        signals["analytical"] = 0.8 * features["analytical_count"]

    # Longer queries are more likely semantic
    if features["token_count"] >= 6:
        signals["long_query"] = 0.6
    elif features["token_count"] >= 4:
        signals["medium_query"] = 0.3

    # Sentence-like structure (capital start + question form)
    if features["looks_like_sentence"]:
        signals["sentence_structure"] = 0.5

    # High keyword ratio (mostly entity/short tokens) pushes toward keyword
    if features["keyword_ratio"] >= 0.7 and features["entity_count"] >= 1:
        signals["keyword_dominant"] = -1.0
    elif features["keyword_ratio"] >= 0.5:
        signals["keyword_leaning"] = -0.5

    # Short query with entity but no question structure → keyword pull
    if features["token_count"] <= 2 and features["entity_count"] >= 1:
        signals["short_entity"] = -1.0
    elif features["token_count"] <= 3 and features["entity_count"] >= 1 and not features["question_word_any"]:
        signals["short_entity_no_question"] = -0.7

    # POS-derived verb signal: lexical verb/aux detected in the query
    if features.get("pos_available") and features.get("has_verb"):
        signals["verb_present"] = 1.2
        if features.get("verb_count", 0) >= 2:
            signals["multiple_verbs"] = 0.4

    total = sum(signals.values())
    return signals, total
