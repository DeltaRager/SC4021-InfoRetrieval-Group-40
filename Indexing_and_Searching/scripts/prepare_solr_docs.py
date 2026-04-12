"""
Single-source ingestion pipeline for the AI Opinion Search Engine.

Layers:
  Loader     -> CSV parsing for final_reddit_dataset_with_predictions.csv
  Normalizer -> canonical SolrDoc creation
  Enrichment -> model/vendor mention extraction + NLP (lemmatization/concepts)
  Chunker    -> splits long search_text into overlapping chunks for vector indexing
  Serializer -> JSONL output (one record per chunk, carrying full source-doc metadata)

Source:
  - final_reddit_dataset_with_predictions.csv  (Reddit predictions schema)

Output format:
  Each output record is a chunk record with chunk_id as the Solr `id`.
  The stable source-document id is stored in `doc_id`.
  Short documents produce exactly one chunk (chunk_index=0).
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

# Make project root importable so we can use nlp_utils and hybrid_search
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from nlp_utils import process_for_indexing, build_concept_text  # noqa: E402
    _NLP_AVAILABLE = True
except ImportError:
    _NLP_AVAILABLE = False
    def build_concept_text(concepts):  # type: ignore[misc]
        return ""

try:
    from hybrid_search import EmbeddingClient, EMBED_BATCH_SIZE, VECTOR_MAIN_WEIGHT, VECTOR_CONCEPT_WEIGHT  # noqa: E402
    _EMBEDDING_CLIENT = EmbeddingClient()
    _EMBED_AVAILABLE = True
except ImportError:
    _EMBEDDING_CLIENT = None  # type: ignore[assignment]
    _EMBED_AVAILABLE = False
    VECTOR_MAIN_WEIGHT    = float(os.getenv("VECTOR_MAIN_WEIGHT",    "1.0"))
    VECTOR_CONCEPT_WEIGHT = float(os.getenv("VECTOR_CONCEPT_WEIGHT", "0.2"))

# ---------------------------------------------------------------------------
# Chunking constants
# ---------------------------------------------------------------------------

CHUNK_TARGET_CHARS = 1200
CHUNK_OVERLAP_CHARS = 200
FALLBACK_CHUNK_TARGET_CHARS = 600
FALLBACK_CHUNK_OVERLAP_CHARS = 100
# Hard limit for a single embedding call; retry with smaller slice if exceeded
EMBED_MAX_CHARS = 4000


# ---------------------------------------------------------------------------
# Canonical document
# ---------------------------------------------------------------------------

@dataclass
class SolrDoc:
    id: str
    source_id: str
    source_dataset: str
    source_schema: str
    type: str                       # post | comment | unknown
    title: str
    body: str
    search_text: str                # combined retrieval field
    lemmatized_text: str            # NLP-lemmatized form for morphological recall
    concepts: str                   # extracted keyphrases / concept phrases
    subreddit: str
    score: int
    upvote_log: float
    created_date: str               # Solr ISO-8601: 2025-01-01T00:00:00Z
    time_bucket: str                # recent_week | recent_month | recent_quarter | older
    url: str
    model_mentions: list[str]
    vendor_mentions: list[str]
    polarity_label: str             # positive | negative | neutral | unknown
    subjectivity_label: str         # subjective | objective | unknown
    sarcasm_label: str              # sarcastic | non_sarcastic | unknown
    sarcasm_code: int               # raw numeric code from source (1/0/-1); -1 = unknown

    def to_dict(self) -> dict:
        d = asdict(self)
        # Remove empty list fields so Solr does not index empty multivalue fields
        for k in ("model_mentions", "vendor_mentions"):
            if not d[k]:
                del d[k]
        # Remove empty NLP fields to keep docs lean when NLP is unavailable
        if not d.get("lemmatized_text"):
            del d["lemmatized_text"]
        if not d.get("concepts"):
            del d["concepts"]
        return d


# ---------------------------------------------------------------------------
# Model / vendor lexicons
# ---------------------------------------------------------------------------

MODEL_ALIASES: dict[str, list[str]] = {
    "chatgpt":   ["chatgpt", "chat gpt", "gpt-4", "gpt4", "gpt-3", "gpt3", "gpt 4", "gpt 3"],
    "claude":    ["claude"],
    "gemini":    ["gemini", "bard"],
    "llama":     ["llama", "llama2", "llama 2", "llama3", "llama 3"],
    "copilot":   ["copilot", "github copilot"],
    "mistral":   ["mistral"],
    "grok":      ["grok"],
    "deepseek":  ["deepseek", "deep seek"],
    "perplexity":["perplexity"],
    "palm":      ["palm", "palm2", "palm 2"],
}

VENDOR_ALIASES: dict[str, list[str]] = {
    "openai":    ["openai", "open ai"],
    "anthropic": ["anthropic"],
    "google":    ["google deepmind", "google ai", "deepmind"],
    "meta":      ["meta ai", "meta llama"],
    "microsoft": ["microsoft"],
    "mistral_ai":["mistral ai"],
    "xai":       ["x.ai", "xai"],
}

# Pre-compile patterns for speed
_MODEL_PATTERNS = {
    canonical: re.compile(
        r"\b(" + "|".join(re.escape(a) for a in aliases) + r")\b",
        re.IGNORECASE,
    )
    for canonical, aliases in MODEL_ALIASES.items()
}

_VENDOR_PATTERNS = {
    canonical: re.compile(
        r"\b(" + "|".join(re.escape(a) for a in aliases) + r")\b",
        re.IGNORECASE,
    )
    for canonical, aliases in VENDOR_ALIASES.items()
}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def clean_text(value) -> str:
    text = str(value or "")
    # Strip BOM
    text = text.lstrip("\ufeff")
    text = re.sub(r"\[deleted\]|\[removed\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def hash_id(parts: Iterable[str]) -> str:
    joined = "||".join(str(p) for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def to_solr_date(raw) -> Optional[str]:
    """Convert epoch int, ISO string, or pandas Timestamp to Solr date string."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    try:
        if isinstance(raw, (int, float)):
            dt = datetime.fromtimestamp(float(raw), tz=timezone.utc)
        else:
            text = str(raw).strip()
            if not text:
                return None
            dt = pd.to_datetime(text, utc=True).to_pydatetime()
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def time_bucket(solr_date: Optional[str]) -> str:
    if not solr_date:
        return "older"
    try:
        dt = datetime.strptime(solr_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        delta = now - dt
        if delta.days <= 7:
            return "recent_week"
        if delta.days <= 30:
            return "recent_month"
        if delta.days <= 90:
            return "recent_quarter"
        return "older"
    except Exception:
        return "older"


def extract_models(text: str) -> list[str]:
    found = []
    for canonical, pat in _MODEL_PATTERNS.items():
        if pat.search(text):
            found.append(canonical)
    return found


def extract_vendors(text: str) -> list[str]:
    found = []
    for canonical, pat in _VENDOR_PATTERNS.items():
        if pat.search(text):
            found.append(canonical)
    return found



def enrich_nlp(text: str) -> tuple[str, str]:
    """Return (lemmatized_text, concepts) via nlp_utils, or empty strings if unavailable."""
    if not _NLP_AVAILABLE:
        return "", ""
    try:
        result = process_for_indexing(text)
        return result.get("lemmatized_text", ""), result.get("concepts", "")
    except Exception:
        return "", ""


# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------

def _split_into_chunks(
    text: str,
    target: int = CHUNK_TARGET_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[tuple[str, int, int]]:
    """Split *text* into overlapping chunks.

    Returns a list of (chunk_text, char_start, char_end) tuples.
    The strategy is:
      1. Try paragraph-aware splitting first.
      2. Within each paragraph segment, apply sliding-window splitting if the
         paragraph itself exceeds *target*.
      3. Fall back to pure sliding windows when no paragraph structure exists.

    Guarantees:
      - At least one chunk is always returned.
      - chunk_text strips leading/trailing whitespace.
      - Overlapping prefix is taken from the end of the previous chunk.
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= target:
        return [(text, 0, len(text))]

    # Split on blank lines (paragraph boundaries)
    paragraphs: list[str] = re.split(r"\n\s*\n", text)
    # Collapse to non-empty paragraphs and record their char offsets
    para_segments: list[tuple[str, int]] = []
    pos = 0
    for para in paragraphs:
        stripped = para.strip()
        if stripped:
            # Find start of this paragraph in original text
            start = text.find(stripped, pos)
            if start == -1:
                start = pos
            para_segments.append((stripped, start))
            pos = start + len(stripped)

    if not para_segments:
        para_segments = [(text, 0)]

    chunks: list[tuple[str, int, int]] = []
    prev_end = 0

    for para_text, para_start in para_segments:
        if len(para_text) <= target:
            # Paragraph fits in one chunk
            chunk_start = para_start
            chunk_end = para_start + len(para_text)
            if chunks:
                # Prefix with overlap from previous chunk
                prev_chunk_text = chunks[-1][0]
                overlap_prefix = prev_chunk_text[max(0, len(prev_chunk_text) - overlap):]
                combined = overlap_prefix + " " + para_text
                chunks.append((combined.strip(), chunk_start, chunk_end))
            else:
                chunks.append((para_text, chunk_start, chunk_end))
            prev_end = chunk_end
        else:
            # Paragraph too long: sliding window within it
            start = 0
            while start < len(para_text):
                end = min(start + target, len(para_text))
                slice_text = para_text[start:end].strip()
                abs_start = para_start + start
                abs_end = para_start + end
                if chunks and start == 0:
                    # Apply overlap prefix from previous chunk at paragraph boundary
                    prev_chunk_text = chunks[-1][0]
                    overlap_prefix = prev_chunk_text[max(0, len(prev_chunk_text) - overlap):]
                    slice_text = (overlap_prefix + " " + slice_text).strip()
                if slice_text:
                    chunks.append((slice_text, abs_start, abs_end))
                if end == len(para_text):
                    break
                start = end - overlap
            prev_end = para_start + len(para_text)

    if not chunks:
        chunks = [(text, 0, len(text))]

    return chunks


def _make_chunk_records(
    doc: dict,
    target: int = CHUNK_TARGET_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[dict]:
    """Produce one or more chunk records from a source document dict.

    Each chunk record is a full copy of the source-document metadata with
    additional chunk fields.  The Solr `id` becomes the chunk id; the stable
    source-document id is stored in `doc_id`.
    """
    source_id = doc["id"]
    search_text = doc.get("search_text", "").strip()

    # Parse the document-level concept list once.
    # concepts is stored as a pipe-separated string ("a | b | c") or may
    # already be a list in intermediate representations.
    doc_concepts_raw = doc.get("concepts", "")
    if isinstance(doc_concepts_raw, list):
        doc_concept_list = doc_concepts_raw
    else:
        doc_concept_list = [c.strip() for c in doc_concepts_raw.split("|") if c.strip()]

    if not search_text:
        # No text to chunk: emit one record with no chunk_vector.
        # For empty-text records, no meaningful scoping is possible — use empty
        # concept text to avoid pulling in unrelated document-level concepts.
        chunk_rec = dict(doc)
        chunk_rec["doc_id"] = source_id
        chunk_rec["chunk_id"] = f"{source_id}__c0"
        chunk_rec["id"] = chunk_rec["chunk_id"]
        chunk_rec["chunk_index"] = 0
        chunk_rec["chunk_text"] = ""
        chunk_rec["chunk_concept_text"] = ""
        chunk_rec["chunk_count"] = 1
        chunk_rec["chunk_char_start"] = 0
        chunk_rec["chunk_char_end"] = 0
        return [chunk_rec]

    spans = _split_into_chunks(search_text, target=target, overlap=overlap)
    records = []
    for idx, (chunk_text, char_start, char_end) in enumerate(spans):
        chunk_rec = dict(doc)
        chunk_rec["doc_id"] = source_id
        chunk_rec["chunk_id"] = f"{source_id}__c{idx}"
        chunk_rec["id"] = chunk_rec["chunk_id"]
        chunk_rec["chunk_index"] = idx
        chunk_rec["chunk_text"] = chunk_text
        # Scope concept text to only the concepts that appear in this chunk.
        # This prevents chunks from inheriting unrelated document-level concepts
        # (e.g., a chunk mentioning "AI" should not carry concepts about "privacy"
        # just because the parent document covers both topics).
        chunk_rec["chunk_concept_text"] = _chunk_concept_text(chunk_text, doc_concept_list)
        chunk_rec["chunk_count"] = len(spans)
        chunk_rec["chunk_char_start"] = char_start
        chunk_rec["chunk_char_end"] = char_end
        records.append(chunk_rec)

    return records


def _chunk_concept_text(chunk_text: str, doc_concept_list: list[str]) -> str:
    """Return concept text scoped to the concepts that appear in *chunk_text*.

    Only concepts whose phrase appears (case-insensitively) within *chunk_text*
    are included.  Preserves the original extractor order and deduplicates.
    When no concepts match, returns an empty string.

    This replaces the previous fallback where every chunk inherited the full
    document concept list regardless of relevance.
    """
    if not doc_concept_list or not chunk_text:
        return ""
    chunk_lower = chunk_text.lower()
    seen: set[str] = set()
    matched: list[str] = []
    for concept in doc_concept_list:
        phrase = concept.strip()
        if not phrase:
            continue
        key = phrase.lower()
        if key not in seen and key in chunk_lower:
            seen.add(key)
            matched.append(phrase)
    return build_concept_text(matched)


def _combine_vectors(
    main_vec: list[float],
    concept_vec: list[float],
    main_weight: float = VECTOR_MAIN_WEIGHT,
    concept_weight: float = VECTOR_CONCEPT_WEIGHT,
) -> list[float]:
    """Weighted elementwise combination of two vectors, L2-normalised.

    Implements the dual-path combination formula:
        combined = normalize(main_weight * f(a+b) + concept_weight * f(b))

    The default weights (main=1.0, concept=0.2) keep the full-text embedding
    as the primary signal while giving the concept channel a secondary boost.
    Equal weights (1.0, 1.0) reproduce the previous equal-weight behaviour.

    If the concept vector is all zeros (no concepts) the result is just the
    normalised scaled main vector.  Returns the zero vector if the weighted
    sum is the zero vector (degenerate case).
    """
    dim = len(main_vec)
    summed = [main_weight * main_vec[i] + concept_weight * concept_vec[i] for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in summed))
    if norm == 0.0:
        return summed
    return [v / norm for v in summed]


def _embed_chunk_records(docs: list[dict]) -> tuple[int, int, int]:
    """Embed chunk_text and chunk_concept_text for the provided chunk records.

    Generates three vector fields per chunk:
      - chunk_main_vector    : embedding of chunk_text (f(a'+b'))
      - chunk_concept_vector : embedding of chunk_concept_text (f(b')); zero vec if empty
      - chunk_vector         : normalize(main_weight * chunk_main_vector + concept_weight * chunk_concept_vector)

    chunk_vector is the combined retrieval field used in Solr kNN queries.

    Returns (attempted, success, skipped) where success counts chunks that
    received a valid chunk_vector.
    """
    if not _EMBED_AVAILABLE or _EMBEDDING_CLIENT is None:
        return 0, 0, 0

    indices = [i for i, d in enumerate(docs) if d.get("chunk_text", "").strip()]
    if not indices:
        return 0, 0, 0

    # Collect main texts (chunk_text) for batch embedding
    main_texts: list[str] = []
    for i in indices:
        ct = docs[i]["chunk_text"]
        if len(ct) > EMBED_MAX_CHARS:
            ct = ct[:EMBED_MAX_CHARS]
        main_texts.append(ct)

    main_embeddings = _EMBEDDING_CLIENT.embed_batch(main_texts, batch_size=EMBED_BATCH_SIZE)

    # Collect concept texts; only embed non-empty ones to save calls
    concept_indices: list[int] = []   # positions within `indices`
    concept_texts: list[str] = []
    for pos, i in enumerate(indices):
        ct = docs[i].get("chunk_concept_text", "").strip()
        if ct:
            concept_indices.append(pos)
            if len(ct) > EMBED_MAX_CHARS:
                ct = ct[:EMBED_MAX_CHARS]
            concept_texts.append(ct)

    concept_embeddings_sparse: list[list[float] | None] = []
    if concept_texts:
        concept_embeddings_sparse = _EMBEDDING_CLIENT.embed_batch(
            concept_texts, batch_size=EMBED_BATCH_SIZE
        )

    # Map position-within-indices → concept embedding (None if unavailable)
    concept_emb_by_pos: dict[int, list[float] | None] = {}
    for sparse_pos, pos in enumerate(concept_indices):
        concept_emb_by_pos[pos] = (
            concept_embeddings_sparse[sparse_pos]
            if sparse_pos < len(concept_embeddings_sparse)
            else None
        )

    success = 0
    skipped = 0
    dim = None  # inferred from first successful main embedding

    for pos, (doc_idx, main_emb) in enumerate(zip(indices, main_embeddings)):
        if main_emb is None:
            docs[doc_idx].pop("chunk_vector", None)
            docs[doc_idx].pop("chunk_main_vector", None)
            docs[doc_idx].pop("chunk_concept_vector", None)
            skipped += 1
            continue

        if dim is None:
            dim = len(main_emb)

        concept_emb = concept_emb_by_pos.get(pos)
        if concept_emb is None:
            # No concepts or embedding failed: use zero vector for concept channel
            zero_vec: list[float] = [0.0] * (dim or len(main_emb))
            concept_emb = zero_vec

        combined = _combine_vectors(main_emb, concept_emb)

        docs[doc_idx]["chunk_main_vector"] = main_emb
        docs[doc_idx]["chunk_concept_vector"] = concept_emb
        docs[doc_idx]["chunk_vector"] = combined
        success += 1

    return len(indices), success, skipped


def _source_doc_from_chunks(chunks: list[dict]) -> dict:
    """Reconstruct a source-document dict from one or more chunk records."""
    source = dict(chunks[0])
    source["id"] = source.get("doc_id") or source["id"]
    for key in (
        "doc_id",
        "chunk_id",
        "chunk_index",
        "chunk_text",
        "chunk_concept_text",
        "chunk_count",
        "chunk_char_start",
        "chunk_char_end",
        "chunk_vector",
        "chunk_main_vector",
        "chunk_concept_vector",
    ):
        source.pop(key, None)
    return source


def embed_docs(docs: list[dict]) -> None:
    """Embed chunk_text and chunk_concept_text for each chunk record in-place.

    Writes three vector fields per successfully embedded chunk:
      - chunk_main_vector    : f(a'+b') — main text embedding
      - chunk_concept_vector : f(b')    — concept text embedding (zero vec if no concepts)
      - chunk_vector         : normalize(main_weight * chunk_main_vector + concept_weight * chunk_concept_vector)

    chunk_vector is the combined retrieval field used in Solr kNN queries.

    Chunk records that lack chunk_text are skipped.  On embedding failure the
    vector fields are not written — those chunks are still indexed for BM25
    retrieval.

    Retry logic:
      - If a chunk text exceeds EMBED_MAX_CHARS, truncate it before retrying.
      - If a batch call fails and contains multiple items, retry each item
        individually (handled by EmbeddingClient.embed_batch).
      - A single chunk that still fails after individual retry is skipped.

    Emits a summary of:
      - chunks attempted
      - chunks embedded successfully
      - chunks skipped
    """
    if not _EMBED_AVAILABLE or _EMBEDDING_CLIENT is None:
        print("[INFO] Embedding service not available; skipping vector generation.")
        return

    embeddable = [d for d in docs if d.get("chunk_text", "").strip()]
    if not embeddable:
        return

    print(f"[INFO] Embedding {len(embeddable)} chunks (dual-path, batch_size={EMBED_BATCH_SIZE}) …")
    attempted, _success, skipped = _embed_chunk_records(docs)

    fallback_docs = 0
    replaced_chunks = 0
    if skipped:
        failed_doc_ids = sorted({
            d["doc_id"]
            for d in docs
            if d.get("chunk_text", "").strip() and "chunk_vector" not in d
        })
        for doc_id in failed_doc_ids:
            original_chunks = [d for d in docs if d.get("doc_id") == doc_id]
            if not original_chunks:
                continue

            original_missing = sum(
                1 for d in original_chunks
                if d.get("chunk_text", "").strip() and "chunk_vector" not in d
            )
            source_doc = _source_doc_from_chunks(original_chunks)
            fallback_chunks = _make_chunk_records(
                source_doc,
                target=FALLBACK_CHUNK_TARGET_CHARS,
                overlap=FALLBACK_CHUNK_OVERLAP_CHARS,
            )
            fallback_attempted, fallback_success, fallback_skipped = _embed_chunk_records(fallback_chunks)

            if fallback_attempted and fallback_skipped < original_missing:
                docs[:] = [d for d in docs if d.get("doc_id") != doc_id] + fallback_chunks
                fallback_docs += 1
                replaced_chunks += len(fallback_chunks)

    final_attempted = sum(1 for d in docs if d.get("chunk_text", "").strip())
    final_success = sum(1 for d in docs if d.get("chunk_text", "").strip() and "chunk_vector" in d)
    final_skipped = final_attempted - final_success
    print(
        f"[INFO] Chunks embedded: {final_success}/{final_attempted}"
        + (f"; skipped after retry: {final_skipped}" if final_skipped else "")
        + (
            f"; fallback rechunked docs: {fallback_docs} ({replaced_chunks} chunk record(s))"
            if fallback_docs else ""
        )
        + "."
    )


# ---------------------------------------------------------------------------
# Source-specific loaders
# ---------------------------------------------------------------------------

PREDICTIONS_FILE = "final_reddit_dataset_with_predictions.csv"

# Numeric → label mappings for prediction columns
_POLARITY_MAP = {1: "positive", 0: "negative", -1: "neutral"}
_SUBJECTIVITY_MAP = {1: "subjective", 0: "objective"}
_SARCASM_MAP = {1: "sarcastic", 0: "non_sarcastic"}


def _map_prediction(raw, label_map: dict) -> str:
    """Map a numeric prediction code to its string label, or 'unknown'."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return "unknown"
    try:
        code = int(float(raw))
        return label_map.get(code, "unknown")
    except (TypeError, ValueError):
        return "unknown"


def _safe_int_code(raw, default: int = -1) -> int:
    """Return the integer prediction code, or *default* on failure."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def load_reddit_predictions_csv(csv_path: Path) -> list[SolrDoc]:
    """Loader for final_reddit_dataset_with_predictions.csv."""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    docs: list[SolrDoc] = []

    for row in df.to_dict(orient="records"):
        # --- Core text ---
        raw_text = clean_text(row.get("text", ""))
        if not raw_text:
            continue

        source_id = str(row.get("id", "")).strip()
        doc_type = str(row.get("type", "") or "").strip().lower() or "unknown"
        title = clean_text(row.get("title", ""))
        subreddit = clean_text(row.get("subreddit", "")).lstrip("r/") or "unknown"
        url = str(row.get("url", "") or "").strip()
        author = str(row.get("author", "") or "").strip()

        # --- Timestamp: prefer created_dt, fall back to created_utc ---
        solr_date = to_solr_date(row.get("created_dt") or row.get("created_utc"))

        # --- Score ---
        score_raw = row.get("score", 0)
        score = int(score_raw) if score_raw and not (isinstance(score_raw, float) and math.isnan(score_raw)) else 0

        # --- Body / search_text ---
        body = raw_text
        # For posts include title in search_text; for comments body is enough
        if doc_type == "post" and title:
            search_text = f"{title} {body}"
        else:
            search_text = body

        lemmatized_text, concepts = enrich_nlp(search_text)

        # --- Prediction labels (numeric → string) ---
        polarity_label = _map_prediction(row.get("polarity"), _POLARITY_MAP)
        subjectivity_label = _map_prediction(row.get("subjectivity"), _SUBJECTIVITY_MAP)
        sarcasm_label = _map_prediction(row.get("sarcasm"), _SARCASM_MAP)
        sarcasm_code = _safe_int_code(row.get("sarcasm"))

        # Stable Solr id: use Reddit native id if available, else hash
        stable_id = source_id if source_id else hash_id([PREDICTIONS_FILE, raw_text[:120], str(solr_date), subreddit])

        docs.append(SolrDoc(
            id=stable_id,
            source_id=source_id,
            source_dataset="final_reddit_dataset_with_predictions",
            source_schema="reddit_predictions_csv",
            type=doc_type,
            title=title,
            body=body,
            search_text=search_text,
            lemmatized_text=lemmatized_text,
            concepts=concepts,
            subreddit=subreddit,
            score=score,
            upvote_log=round(math.log1p(max(score, 0)), 4),
            created_date=solr_date or "",
            time_bucket=time_bucket(solr_date),
            url=url,
            model_mentions=extract_models(body),
            vendor_mentions=extract_vendors(body),
            polarity_label=polarity_label,
            subjectivity_label=subjectivity_label,
            sarcasm_label=sarcasm_label,
            sarcasm_code=sarcasm_code,
        ))

    return docs


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def prepare_docs(
    predictions_csv_path: Path,
    output_path: Path,
) -> tuple[int, int, int]:
    """Build chunk records from the predictions CSV and write them to *output_path*.

    Returns (source_docs_processed, total_chunks, source_docs_with_zero_vectors).
    """
    if not predictions_csv_path.exists():
        print(f"[ERROR] Predictions CSV not found: {predictions_csv_path}")
        return 0, 0, 0

    source_docs: list[dict] = []
    seen: set[tuple] = set()

    docs = load_reddit_predictions_csv(predictions_csv_path)
    for doc in docs:
        # Deduplicate on stable id (Reddit native id already unique; hash fallback may collide)
        sig = (doc.id,)
        if sig in seen:
            continue
        seen.add(sig)
        source_docs.append(doc.to_dict())

    # Expand each source document into chunk records
    all_chunks: list[dict] = []
    for doc in source_docs:
        all_chunks.extend(_make_chunk_records(doc))

    print(f"[INFO] Source docs: {len(source_docs)}, chunk records: {len(all_chunks)}")

    # Embed chunk_text for each chunk record
    embed_docs(all_chunks)

    # Count source docs with zero successfully embedded chunks
    embedded_doc_ids: set[str] = {
        c["doc_id"] for c in all_chunks if "chunk_vector" in c
    }
    zero_vector_docs = len(source_docs) - len(embedded_doc_ids)
    if zero_vector_docs:
        print(f"[WARN] {zero_vector_docs} source doc(s) have no embedded chunks.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    return len(source_docs), len(all_chunks), zero_vector_docs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Single-source ingestion pipeline for AI Opinion Search Engine."
    )
    parser.add_argument(
        "--output", default="data/reddit_docs.jsonl",
        help="Output JSONL path (relative to Indexing_and_Searching/)",
    )
    parser.add_argument(
        "--input",
        default=None,
        help=f"Path to {PREDICTIONS_FILE} (auto-detected if omitted)",
    )
    args = parser.parse_args()

    # index_root is Indexing_and_Searching/
    index_root = Path(__file__).resolve().parents[1]
    output_path = index_root / args.output

    # Resolve predictions CSV: flag > sibling of index_root
    if args.input:
        predictions_csv_path = Path(args.input).resolve()
    else:
        candidates = [
            index_root / PREDICTIONS_FILE,
            index_root.parent / PREDICTIONS_FILE,
        ]
        predictions_csv_path = next((p for p in candidates if p.exists()), None)
        if predictions_csv_path:
            print(f"[INFO] Auto-detected predictions CSV: {predictions_csv_path}")
        else:
            print(f"[ERROR] {PREDICTIONS_FILE} not found. "
                  "Use --input <path> to specify it.")
            return

    if not _NLP_AVAILABLE:
        print("[WARN] nlp_utils not available; lemmatized_text and concepts will be empty.")

    source_count, chunk_count, zero_vec = prepare_docs(predictions_csv_path, output_path)
    print(
        f"Indexed {source_count} source docs → {chunk_count} chunk records. "
        f"Saved to {output_path}"
        + (f" ({zero_vec} source doc(s) with zero vector chunks)" if zero_vec else "")
        + "."
    )


if __name__ == "__main__":
    main()
