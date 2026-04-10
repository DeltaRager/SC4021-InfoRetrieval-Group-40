"""
NLP utilities for lemmatization and concept extraction.

Lemmatization:
    Uses spaCy (en_core_web_sm) for POS-aware lemmatization, referenced by
    methods such as Chrupala (2006), Mueller et al. (2015), and Toutanova
    & Cherry (2009).  spaCy's pipeline provides tokenisation, POS tagging,
    and lemmatisation in a single pass, making it ideal for search-engine
    pre-processing where the same pipeline must run at both index time and
    query time.

Concept Extraction:
    Combines two complementary approaches referenced in the lecture slides:
    1. spaCy noun-chunk extraction (syntactic parsing, similar to Snow et al.
       2006 and Cambria et al. 2022) for phrase-aware stopword handling.
    2. YAKE (Yet Another Keyword Extractor) for unsupervised keyphrase
       extraction (statistical, language-independent -- comparable to
       approaches by Zhang et al. 2016 and Meng et al. 2017).

Smart stopword removal:
    Removes common stopwords ("the", "a", "an", ...) while preserving them
    inside meaningful phrases detected via noun chunks and named entities.
    This covers the exceptions listed in the requirements:
        - Phrase queries, e.g. "King of Denmark"
        - Song titles, e.g. "Let it be"
        - Relational queries, e.g. "flights to London"
        - Punctuation, hyphens, and accents
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import re as _re

import spacy
import yake
from spellchecker import SpellChecker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-loaded singletons
# ---------------------------------------------------------------------------

_nlp: spacy.language.Language | None = None
_yake_extractor: yake.KeywordExtractor | None = None
_spell: SpellChecker | None = None
PROTECTED_QUERY_TERMS = {
    "chatgpt",
    "openai",
    "claude",
    "anthropic",
    "gemini",
    "bard",
    "llama",
    "copilot",
    "mistral",
    "grok",
    "deepseek",
    "perplexity",
    "palm",
    "meta",
    "microsoft",
    "google",
    "deepmind",
    "xai",
    "agi",
    "llm",
}


def _get_nlp() -> spacy.language.Language:
    """Load spaCy English model lazily (avoids startup cost when unused)."""
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("en_core_web_sm", disable=["textcat"])
        except OSError:
            logger.warning(
                "spaCy model 'en_core_web_sm' not found. "
                "Run: python -m spacy download en_core_web_sm"
            )
            raise
    return _nlp


def _get_spell() -> SpellChecker:
    """Create SpellChecker with domain vocabulary loaded lazily.

    In addition to the default English dictionary (~100 k words), we load
    domain-specific terms extracted from the indexed corpus so that words
    like "bitcoin", "cryptocurrency", "blockchain", etc. are treated as
    known words and can serve as correction candidates.
    """
    global _spell
    if _spell is None:
        _spell = SpellChecker()
        _load_domain_vocab(_spell)
    return _spell


def _load_domain_vocab(spell: SpellChecker) -> None:
    """Scan the indexed JSONL file and add frequent tokens to the spell
    checker so domain-specific terms are recognised."""
    from collections import Counter
    from pathlib import Path

    jsonl_path = Path(__file__).resolve().parent / "data" / "reddit_docs.jsonl"
    if not jsonl_path.exists():
        logger.debug("JSONL corpus not found at %s; skipping domain vocab", jsonl_path)
        return

    import json

    word_freq: Counter[str] = Counter()
    try:
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                doc = json.loads(line)
                text = " ".join(
                    part for part in (
                        doc.get("search_text", ""),
                        doc.get("full_text", ""),
                        doc.get("title", ""),
                        doc.get("body", ""),
                        " ".join(doc.get("model_mentions", []) or []),
                        " ".join(doc.get("vendor_mentions", []) or []),
                    )
                    if part
                )
                # Simple whitespace tokenisation; strip punctuation
                for token in text.lower().split():
                    clean = token.strip(".,;:!?\"'()[]{}<>*#@_~`/\\|-")
                    if clean.isalpha() and len(clean) >= 3:
                        word_freq[clean] += 1
    except Exception as exc:
        logger.warning("Failed to load domain vocab: %s", exc)
        return

    # Add domain words in a single bulk call.  Frequency boosting is NOT
    # needed because _best_candidate() uses normalised Levenshtein
    # similarity as the primary signal (not frequency).  This makes
    # loading nearly instant (~0.02 s for 5 000 words) instead of the
    # minutes it took with the old repeated-load approach.
    domain_words = [w for w, c in word_freq.items() if c >= 3]
    domain_words.extend(sorted(PROTECTED_QUERY_TERMS))
    if domain_words:
        spell.word_frequency.load_words(domain_words)
        logger.debug("Loaded %d domain words into spell checker", len(domain_words))


def _get_yake() -> yake.KeywordExtractor:
    """Create YAKE extractor lazily."""
    global _yake_extractor
    if _yake_extractor is None:
        _yake_extractor = yake.KeywordExtractor(
            lan="en",
            n=3,            # max n-gram size for keyphrases
            dedupLim=0.9,   # deduplication threshold
            dedupFunc="seqm",
            top=10,         # return top-10 concepts per text
            features=None,
        )
    return _yake_extractor


# ---------------------------------------------------------------------------
# Lemmatization
# ---------------------------------------------------------------------------

def lemmatize_text(text: str) -> str:
    """Return a lemmatized version of *text* using spaCy.

    Each token is replaced by its lemma (lower-cased).  Punctuation tokens
    are dropped so the lemmatized string is a clean bag of lemmas suitable
    for full-text indexing.

    Examples
    --------
    >>> lemmatize_text("The dogs were running quickly")
    'the dog be run quickly'
    >>> lemmatize_text("artificially intelligent systems")
    'artificially intelligent system'
    """
    nlp = _get_nlp()
    doc = nlp(text)
    tokens = [
        token.lemma_.lower()
        for token in doc
        if not token.is_punct and token.text.strip()
    ]
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# Concept / Keyphrase Extraction
# ---------------------------------------------------------------------------

def extract_concepts_yake(text: str) -> list[str]:
    """Extract keyphrases with YAKE (unsupervised, statistical).

    Returns a list of multi-word concepts sorted by relevance (most relevant
    first).  YAKE keeps stopwords that appear inside meaningful n-grams,
    e.g. "King of Denmark" stays intact.
    """
    extractor = _get_yake()
    if not text or not text.strip():
        return []
    keywords = extractor.extract_keywords(text)
    # YAKE returns (keyword_str, score); lower score == more relevant
    return [kw for kw, _score in keywords]


def extract_noun_chunks(text: str) -> list[str]:
    """Extract noun chunks via spaCy's dependency parser.

    Noun chunks naturally preserve stopwords that form part of a meaningful
    phrase, e.g. "the King of Denmark", "flights to London".
    """
    nlp = _get_nlp()
    doc = nlp(text)
    chunks = []
    for chunk in doc.noun_chunks:
        chunk_text = chunk.text.strip()
        if chunk_text:
            chunks.append(chunk_text)
    return chunks


def extract_named_entities(text: str) -> list[str]:
    """Extract named entities via spaCy NER.

    Named entities include people, organisations, locations, etc. that
    should never be broken up or have stopwords removed.
    """
    nlp = _get_nlp()
    doc = nlp(text)
    return [ent.text for ent in doc.ents if ent.text.strip()]


def extract_concepts(text: str) -> list[str]:
    """Combine YAKE keyphrases + spaCy noun chunks + NER into a deduplicated
    concept list.  This is stored as a separate Solr field so that queries
    can match on high-level concepts rather than individual tokens.
    """
    if not text or not text.strip():
        return []

    yake_concepts = extract_concepts_yake(text)
    noun_chunks = extract_noun_chunks(text)
    entities = extract_named_entities(text)

    # Merge and deduplicate (case-insensitive), preserving order
    seen: set[str] = set()
    merged: list[str] = []
    for phrase in yake_concepts + noun_chunks + entities:
        key = phrase.lower().strip()
        if key and key not in seen:
            seen.add(key)
            merged.append(phrase)
    return merged


# ---------------------------------------------------------------------------
# Smart Stopword Removal
# ---------------------------------------------------------------------------

def smart_remove_stopwords(text: str) -> str:
    """Remove stopwords while preserving them inside meaningful phrases.

    The function:
    1. Identifies *protected spans* -- tokens that belong to noun chunks or
       named entities.  Stopwords inside these spans are kept because they
       are integral to the phrase (e.g. "King **of** Denmark").
    2. For all remaining (unprotected) tokens, standard spaCy stopwords are
       removed.
    3. Punctuation, hyphens, and accented characters are always preserved.
    """
    nlp = _get_nlp()
    doc = nlp(text)

    # Collect indices of tokens inside noun chunks or named entities
    protected: set[int] = set()
    for chunk in doc.noun_chunks:
        for token in chunk:
            protected.add(token.i)
    for ent in doc.ents:
        for token in ent:
            protected.add(token.i)

    result: list[str] = []
    for token in doc:
        if token.i in protected:
            # Always keep tokens that are part of a meaningful phrase
            result.append(token.text)
        elif token.is_stop:
            # Drop unprotected stopwords
            continue
        elif not token.text.strip():
            continue
        else:
            result.append(token.text)

    return " ".join(result)


# ---------------------------------------------------------------------------
# Spell Correction
# ---------------------------------------------------------------------------

def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if not s2:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(
                prev[j + 1] + 1,       # deletion
                curr[j] + 1,           # insertion
                prev[j] + (c1 != c2),  # substitution
            ))
        prev = curr
    return prev[-1]


def _best_candidate(original: str, candidates: set[str] | None) -> str | None:
    """Pick the best spelling candidate by balancing edit-distance
    similarity and word frequency.

    Uses **normalised Levenshtein similarity** (``1 - dist / max_len``)
    as the primary signal and log-frequency as a tiebreaker.

    Unlike ``SequenceMatcher.ratio()`` (which divides by the *sum* of
    lengths), normalising by the *max* length avoids rewarding shorter
    candidates.  This ensures "phiscs" → "physics" (sim 0.71) beats
    "piss" (sim 0.67) even though "piss" has higher frequency.

    Scoring formula::

        score = similarity * 10  +  log(1 + freq) * 0.1
    """
    if not candidates:
        return None

    import math
    spell = _get_spell()

    def score(word: str) -> float:
        dist = _levenshtein(original, word)
        max_len = max(len(original), len(word))
        similarity = 1.0 - dist / max_len if max_len else 0.0
        freq = spell.word_frequency[word] or 1
        log_freq = math.log1p(freq)
        return similarity * 10 + log_freq * 0.1

    return max(candidates, key=score)


def spell_correct_query(query: str) -> dict[str, Any]:
    """Correct likely typos in *query* using pyspellchecker.

    pyspellchecker uses Peter Norvig's algorithm with a word-frequency
    dictionary (~100 k English words).  For each word not found in the
    dictionary, it generates candidates within Levenshtein distance 2 and
    picks the one with the highest frequency.

    Examples
    --------
    >>> spell_correct_query("artficial intellgence")
    {'corrected': 'artificial intelligence', 'has_corrections': True,
     'corrections': {'artficial': 'artificial', 'intellgence': 'intelligence'}}
    >>> spell_correct_query("phiscs")
    {'corrected': 'physics', 'has_corrections': True,
     'corrections': {'phiscs': 'physics'}}
    """
    spell = _get_spell()

    # Tokenise on whitespace but keep track of non-alpha tokens (numbers,
    # punctuation, special chars) so we don't try to spell-check them.
    tokens = query.split()
    corrected_tokens: list[str] = []
    corrections: dict[str, str] = {}

    for token in tokens:
        # Strip surrounding punctuation for checking, re-attach later
        stripped = token.strip(".,;:!?\"'()-")
        if not stripped or not stripped.isalpha() or len(stripped) <= 2:
            # Don't correct numbers, punctuation, or very short words
            corrected_tokens.append(token)
            continue

        lower = stripped.lower()
        if lower in PROTECTED_QUERY_TERMS:
            corrected_tokens.append(token)
            continue
        if lower in spell:
            # Word is known -- no correction needed
            corrected_tokens.append(token)
            continue

        # Get candidates and pick the best one.  spell.correction() uses
        # pure frequency, which can mis-fire for short edits of long words
        # (e.g. "phiscs" → "piss" instead of "physics").  We re-rank by
        # preferring candidates whose length is closer to the original.
        candidates = spell.candidates(lower)
        candidate = _best_candidate(lower, candidates) if candidates else None
        if candidate and candidate != lower:
            corrections[stripped] = candidate
            # Preserve original capitalisation pattern
            if stripped[0].isupper() and stripped[1:].islower():
                candidate = candidate.capitalize()
            elif stripped.isupper():
                candidate = candidate.upper()
            corrected_tokens.append(token.replace(stripped, candidate))
        else:
            corrected_tokens.append(token)

    corrected = " ".join(corrected_tokens)
    return {
        "corrected": corrected,
        "has_corrections": bool(corrections),
        "corrections": corrections,
    }


# ---------------------------------------------------------------------------
# Fuzzy Query Builder (Solr Levenshtein ~N)
# ---------------------------------------------------------------------------

def build_fuzzy_query(query: str) -> str:
    """Append Solr fuzzy operators (~N) to each term for typo tolerance.

    Solr/Lucene uses Levenshtein (edit-distance) automata at the index
    level to match terms within a given distance.  This function assigns:
        - ~1  for words of 4-5 characters  (1 edit  is enough)
        - ~2  for words of 6+  characters  (2 edits for longer words)
        - no fuzzy for words <= 3 chars     (too many false positives)

    Quoted phrases ("exact match") are left untouched because fuzzy
    operators don't apply inside Lucene phrase queries.

    Examples
    --------
    >>> build_fuzzy_query('artficial intellgence')
    'artficial~2 intellgence~2'
    >>> build_fuzzy_query('"prompt injection" risk')
    '"prompt injection" risk~1'
    """
    # Split while preserving quoted phrases intact
    parts = _re.findall(r'"[^"]*"|\S+', query)
    fuzzy_parts: list[str] = []

    for part in parts:
        if part.startswith('"') and part.endswith('"'):
            # Quoted phrase -- keep as-is
            fuzzy_parts.append(part)
        elif not part.isalpha():
            # Contains digits / special chars -- skip fuzzy
            fuzzy_parts.append(part)
        elif len(part) <= 3:
            fuzzy_parts.append(part)
        elif len(part) <= 5:
            fuzzy_parts.append(f"{part}~1")
        else:
            fuzzy_parts.append(f"{part}~2")

    return " ".join(fuzzy_parts)


# ---------------------------------------------------------------------------
# Prefix Completion & Wildcard Expansion
# ---------------------------------------------------------------------------

def _get_vocab() -> set[str]:
    """Return the full vocabulary known to the spell checker (lazy)."""
    spell = _get_spell()
    return set(spell.word_frequency.words())


def complete_prefix(prefix: str) -> str | None:
    """Complete a word prefix to the most likely full word.

    Scans the spell checker's vocabulary for words that start with
    *prefix* and returns the one with the highest frequency.

    Examples
    --------
    >>> complete_prefix("artif")
    'artificial'
    >>> complete_prefix("block")
    'block'
    """
    if not prefix or len(prefix) <= 1:
        return None

    prefix_lower = prefix.lower()
    spell = _get_spell()
    vocab = _get_vocab()

    # Find all words starting with this prefix
    matches = [w for w in vocab if w.startswith(prefix_lower) and len(w) > len(prefix_lower)]

    if not matches:
        return None

    # Primary: highest frequency.  Secondary: shortest word (for ties).
    # E.g. "artif" → "artificial" (high freq) over "artifact" (lower freq).
    # E.g. "bitco" → "bitcoin" over "bitcoiner" (same freq, shorter wins).
    return max(matches, key=lambda w: (spell.word_frequency[w], -len(w)))


def expand_wildcard(pattern: str) -> str | None:
    """Expand a wildcard pattern where ``*`` matches zero or more characters.

    The pattern is converted to a regex and matched against the spell
    checker's vocabulary.  The highest-frequency match is returned.

    Examples
    --------
    >>> expand_wildcard("int*enc")
    'intelligence'
    >>> expand_wildcard("block*")
    'blockchain'
    """
    if "*" not in pattern or not pattern:
        return None

    # Convert glob-style pattern to regex: * → .*
    # No trailing $ so the last segment can be a partial match,
    # e.g. "int*enc" matches "intelligence" (enc appears inside the word).
    regex_str = "^" + _re.escape(pattern.lower()).replace(r"\*", ".*")
    try:
        regex = _re.compile(regex_str)
    except _re.error:
        return None

    spell = _get_spell()
    vocab = _get_vocab()
    matches = [w for w in vocab if regex.match(w)]

    if not matches:
        return None

    # Primary: highest frequency.  Secondary: shortest word (for ties).
    return max(matches, key=lambda w: (spell.word_frequency[w], -len(w)))


def preprocess_query(query: str) -> dict[str, Any]:
    """Handle prefix completion and wildcard expansion on each token
    BEFORE spell correction runs.

    This is the first stage of query processing:
      1. Tokens containing ``*`` are expanded via wildcard matching
      2. Tokens not in the dictionary and not correctable are tried
         as prefixes

    Returns a dict with:
        processed : str  -- query after prefix/wildcard expansion
        expansions: dict -- {original_token: expanded_token}
        has_expansion: bool
    """
    spell = _get_spell()
    tokens = query.split()
    processed_tokens: list[str] = []
    expansions: dict[str, str] = {}

    for token in tokens:
        stripped = token.strip(".,;:!?\"'()-")
        if not stripped:
            processed_tokens.append(token)
            continue

        lower = stripped.lower()

        # 1. Wildcard expansion: token contains *
        if "*" in stripped:
            expanded = expand_wildcard(lower)
            if expanded and expanded != lower:
                expansions[stripped] = expanded
                # Preserve capitalisation
                if stripped[0].isupper() and stripped[1] != "*":
                    expanded = expanded.capitalize()
                processed_tokens.append(token.replace(stripped, expanded))
                continue
            # If wildcard didn't match, keep the * for Solr native wildcard
            processed_tokens.append(token)
            continue

        # 2. Prefix completion: if an unknown word is the start of a
        #    longer known word, prefer completing it over spell-correcting.
        #    E.g. "artif" → "artificial" (not "artie" via spell correction).
        if lower.isalpha() and len(lower) >= 3 and lower not in spell:
            completed = complete_prefix(lower)
            if completed and completed != lower:
                expansions[stripped] = completed
                if stripped[0].isupper() and stripped[1:].islower():
                    completed = completed.capitalize()
                elif stripped.isupper():
                    completed = completed.upper()
                processed_tokens.append(token.replace(stripped, completed))
                continue

        processed_tokens.append(token)

    result = " ".join(processed_tokens)
    return {
        "processed": result,
        "expansions": expansions,
        "has_expansion": bool(expansions),
    }

def process_for_indexing(text: str) -> dict[str, Any]:
    """Run the full NLP pipeline on a document's text for Solr indexing.

    Returns a dict with:
        lemmatized_text : str   -- lemmatized version of the input
        concepts        : str   -- pipe-separated list of extracted concepts
    """
    lemmatized = lemmatize_text(text)
    concepts = extract_concepts(text)
    return {
        "lemmatized_text": lemmatized,
        "concepts": " | ".join(concepts),
    }


def process_query(query: str) -> dict[str, Any]:
    """Run the full NLP pipeline on a user query.

    Processing order:
      1. **Prefix / wildcard expansion** -- complete partial words
         (e.g. "artif" → "artificial") and expand wildcards
         (e.g. "int*enc" → "intelligence").
      2. **Spell correction** -- fix remaining typos in the expanded
         query (e.g. "artficial" → "artificial").
      3. **Lemmatization + concept extraction** -- run on the fully
         corrected query for best downstream matching.

    Returns a dict with:
        original        : str  -- the raw query as typed by the user
        expanded        : str  -- after prefix/wildcard expansion
        expansions      : dict -- {partial: completed} mapping
        has_expansion   : bool -- True if any prefix/wildcard was expanded
        spell_corrected : str  -- after spell correction
        has_typo        : bool -- True if spell corrections were applied
        corrections     : dict -- {misspelled: corrected} mapping
        final_query     : str  -- the fully processed query sent to Solr
        lemmatized      : str  -- lemmatized version of final_query
        cleaned         : str  -- after smart stopword removal
        concepts        : list -- extracted concepts
        fuzzy           : str  -- original query with Solr ~N operators
    """
    # 1. Prefix completion & wildcard expansion
    pre_result = preprocess_query(query)
    expanded_q = pre_result["processed"]

    # 2. Spell correction (on expanded query)
    spell_result = spell_correct_query(expanded_q)
    corrected_q = spell_result["corrected"]

    # 3. Run NLP pipeline on the fully corrected query
    lemmatized = lemmatize_text(corrected_q)
    cleaned = smart_remove_stopwords(corrected_q)
    concepts = extract_concepts(corrected_q)

    # 4. Build fuzzy query from the ORIGINAL input (safety net)
    fuzzy = build_fuzzy_query(query)

    return {
        "original": query,
        "expanded": expanded_q,
        "expansions": pre_result["expansions"],
        "has_expansion": pre_result["has_expansion"],
        "spell_corrected": corrected_q,
        "has_typo": spell_result["has_corrections"],
        "corrections": spell_result["corrections"],
        "final_query": corrected_q,
        "fuzzy": fuzzy,
        "lemmatized": lemmatized,
        "cleaned": cleaned,
        "concepts": concepts,
    }
