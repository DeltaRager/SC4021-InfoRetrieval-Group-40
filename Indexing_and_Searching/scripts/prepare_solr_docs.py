"""
Multi-source ingestion pipeline for the AI Opinion Search Engine.

Layers:
  Loader     -> per-source CSV parsing
  Normalizer -> canonical SolrDoc creation
  Enrichment -> sentiment + model/vendor mention extraction + NLP (lemmatization/concepts)
  Serializer -> JSONL output

Sources:
  - bitcoin_ai_posts_comments_5000pool.csv          (3.1 schema)
  - information_security_ai_posts_comments_5000pool.csv (3.1 schema)
  - seo_ai_posts_comments_5000pool.csv              (3.1 schema)
  - reddit_ai_sentiment_shortened.csv               (sentiment schema)
"""

import argparse
import hashlib
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

# Make project root importable so we can use nlp_utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from nlp_utils import process_for_indexing  # noqa: E402
    _NLP_AVAILABLE = True
except ImportError:
    _NLP_AVAILABLE = False


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
    sentiment_label: str            # positive | negative | neutral | mixed | unknown
    sentiment_score: float          # [-1.0, 1.0], 0.0 if unknown
    opinionatedness_score: float    # [0.0, 1.0]

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

# Opinion marker patterns for opinionatedness scoring
_OPINION_MARKERS = re.compile(
    r"\b(I think|I believe|in my opinion|IMO|IMHO|I feel|I hate|I love|"
    r"I prefer|honestly|frankly|personally|to be honest|tbh|imo|"
    r"best|worst|terrible|amazing|awful|great|garbage|awesome|horrible|"
    r"disappointed|frustrated|impressed|excited|worried|concerned)\b",
    re.IGNORECASE,
)

_POSITIVE_WORDS = re.compile(
    r"\b(great|amazing|excellent|awesome|love|best|fantastic|wonderful|"
    r"impressive|brilliant|perfect|helpful|useful|good|nice|happy|"
    r"exciting|innovative|breakthrough|superior|outstanding|recommend)\b",
    re.IGNORECASE,
)

_NEGATIVE_WORDS = re.compile(
    r"\b(terrible|awful|horrible|hate|worst|bad|useless|disappointing|"
    r"frustrating|broken|garbage|trash|stupid|incompetent|overrated|"
    r"mediocre|scam|fake|dangerous|concerning|worry|worried|fear|"
    r"privacy|censor|bias|biased|wrong|error|fail|failed|failure)\b",
    re.IGNORECASE,
)


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


def compute_sentiment(text: str) -> tuple[str, float]:
    """Return (label, score) using simple lexical counting."""
    pos = len(_POSITIVE_WORDS.findall(text))
    neg = len(_NEGATIVE_WORDS.findall(text))
    total = pos + neg
    if total == 0:
        return "neutral", 0.0
    ratio = (pos - neg) / total
    if pos > 0 and neg > 0 and abs(ratio) < 0.4:
        label = "mixed"
    elif ratio > 0.3:
        label = "positive"
    elif ratio < -0.3:
        label = "negative"
    else:
        label = "neutral"
    score = max(-1.0, min(1.0, ratio))
    return label, round(score, 4)


def compute_opinionatedness(text: str) -> float:
    """Confidence [0,1] that text is opinion rather than pure news."""
    markers = len(_OPINION_MARKERS.findall(text))
    words = max(len(text.split()), 1)
    raw = markers / (words ** 0.5) * 4
    return round(min(1.0, raw), 4)


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
# Source-specific loaders
# ---------------------------------------------------------------------------

SOURCE_31_FILES = [
    ("bitcoin_ai_posts_comments_5000pool.csv",              "bitcoin"),
    ("information_security_ai_posts_comments_5000pool.csv", "information_security"),
    ("seo_ai_posts_comments_5000pool.csv",                  "seo"),
]

SENTIMENT_FILE = "reddit_ai_sentiment_shortened.csv"


def load_31_csv(csv_path: Path, source_dataset: str) -> list[SolrDoc]:
    """Loader for the three 3.1-format CSVs."""
    df = pd.read_csv(csv_path)
    docs: list[SolrDoc] = []

    for row in df.to_dict(orient="records"):
        raw_text = clean_text(row.get("Post/Comment text", ""))
        if not raw_text:
            continue

        posted_time_raw = row.get("Posted time", "")
        solr_date = to_solr_date(posted_time_raw)
        score = int(row.get("Number of upvotes", 0) or 0)
        subreddit = clean_text(row.get("Subreddit the post/comment is from", "")).lstrip("r/")
        subreddit = subreddit or source_dataset

        # Do NOT infer type from text length for 3.1 files
        doc_type = "unknown"
        title = ""
        body = raw_text
        search_text = body

        sentiment_label, sentiment_score = compute_sentiment(body)
        lemmatized_text, concepts = enrich_nlp(search_text)

        docs.append(SolrDoc(
            id=hash_id([csv_path.name, raw_text[:120], str(posted_time_raw)]),
            source_id="",
            source_dataset=source_dataset,
            source_schema="3.1_csv",
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
            url="",
            model_mentions=extract_models(body),
            vendor_mentions=extract_vendors(body),
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            opinionatedness_score=compute_opinionatedness(body),
        ))

    return docs


def load_sentiment_csv(csv_path: Path) -> list[SolrDoc]:
    """Loader for reddit_ai_sentiment_shortened.csv."""
    # First line is a stray header artifact; skip it with skiprows if needed
    raw = csv_path.read_text(encoding="utf-8-sig")  # strips BOM
    lines = raw.splitlines()
    # Detect and skip stray first line (not starting with expected columns)
    expected_start = "id,"
    skip = 0
    if lines and not lines[0].startswith(expected_start):
        skip = 1

    df = pd.read_csv(csv_path, skiprows=skip, encoding="utf-8-sig")

    docs: list[SolrDoc] = []
    for row in df.to_dict(orient="records"):
        raw_text = clean_text(row.get("text", ""))
        if not raw_text:
            continue

        source_id = str(row.get("id", "")).strip()
        subreddit = clean_text(row.get("subreddit", "")).lstrip("r/")
        doc_type = str(row.get("type", "unknown")).strip() or "unknown"
        score = int(row.get("score", 0) or 0)
        created_utc = row.get("created_utc", None)
        solr_date = to_solr_date(created_utc)

        # This file has no title column; derive from type
        if doc_type == "post":
            title = raw_text[:150]
        else:
            title = ""

        body = raw_text
        search_text = f"{title} {body}".strip() if title else body

        sentiment_label, sentiment_score = compute_sentiment(body)
        lemmatized_text, concepts = enrich_nlp(search_text)

        stable_id = source_id if source_id else hash_id(["sentiment", raw_text[:120], str(created_utc)])

        docs.append(SolrDoc(
            id=stable_id,
            source_id=source_id,
            source_dataset="reddit_ai_sentiment",
            source_schema="sentiment_csv",
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
            url="",
            model_mentions=extract_models(body),
            vendor_mentions=extract_vendors(body),
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            opinionatedness_score=compute_opinionatedness(body),
        ))

    return docs


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def prepare_docs(
    index_root: Path,
    sentiment_path: Optional[Path],
    output_path: Path,
) -> tuple[int, int]:
    all_docs: list[dict] = []
    seen: set[tuple] = set()

    # Load 3.1 CSVs
    for csv_name, dataset in SOURCE_31_FILES:
        csv_path = index_root / csv_name
        if not csv_path.exists():
            print(f"[WARN] Not found, skipping: {csv_path}")
            continue
        docs = load_31_csv(csv_path, dataset)
        for doc in docs:
            sig = (doc.body.lower()[:200], doc.subreddit, doc.created_date)
            if sig in seen:
                continue
            seen.add(sig)
            all_docs.append(doc.to_dict())

    # Load sentiment CSV
    if sentiment_path and sentiment_path.exists():
        docs = load_sentiment_csv(sentiment_path)
        for doc in docs:
            sig = (doc.body.lower()[:200], doc.subreddit, doc.created_date)
            if sig in seen:
                continue
            seen.add(sig)
            all_docs.append(doc.to_dict())
    elif sentiment_path:
        print(f"[WARN] Sentiment file not found: {sentiment_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for doc in all_docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    return len(all_docs), len(seen)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-source ingestion pipeline for AI Opinion Search Engine."
    )
    parser.add_argument(
        "--output", default="data/reddit_docs.jsonl",
        help="Output JSONL path (relative to Indexing_and_Searching/)",
    )
    parser.add_argument(
        "--sentiment-file",
        default=None,
        help="Path to reddit_ai_sentiment_shortened.csv",
    )
    args = parser.parse_args()

    # repo_root is Indexing_and_Searching/
    index_root = Path(__file__).resolve().parents[1]
    output_path = index_root / args.output

    # Resolve sentiment file: flag > sibling of index_root > grandparent Data Scraping/
    if args.sentiment_file:
        sentiment_path = Path(args.sentiment_file).resolve()
    else:
        # Try common locations relative to the repo
        candidates = [
            index_root / SENTIMENT_FILE,
            index_root.parent / "Data Scraping" / SENTIMENT_FILE,
            index_root.parent.parent / "Data Scraping" / SENTIMENT_FILE,
        ]
        sentiment_path = next((p for p in candidates if p.exists()), None)
        if sentiment_path:
            print(f"[INFO] Auto-detected sentiment file: {sentiment_path}")
        else:
            print("[WARN] reddit_ai_sentiment_shortened.csv not found. "
                  "Use --sentiment-file <path> to specify it.")

    if not _NLP_AVAILABLE:
        print("[WARN] nlp_utils not available; lemmatized_text and concepts will be empty.")

    total, unique = prepare_docs(index_root, sentiment_path, output_path)
    print(f"Indexed {total} docs ({unique} unique). Saved to {output_path}")


if __name__ == "__main__":
    main()
