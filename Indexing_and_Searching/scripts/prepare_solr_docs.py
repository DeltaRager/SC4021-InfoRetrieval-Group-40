import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

# Make project root importable so we can use nlp_utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nlp_utils import process_for_indexing  # noqa: E402

INPUT_FILES = [
    "bitcoin_ai_posts_comments_5000pool.csv",
    "information_security_ai_posts_comments_5000pool.csv",
    "seo_ai_posts_comments_5000pool.csv",
]


@dataclass
class SolrDoc:
    id: str
    type: str
    title: str
    body: str
    full_text: str
    lemmatized_text: str
    concepts: str
    subreddit: str
    score: int
    created_date: str
    thread_id: str
    source_file: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "full_text": self.full_text,
            "lemmatized_text": self.lemmatized_text,
            "concepts": self.concepts,
            "subreddit": self.subreddit,
            "score": self.score,
            "created_date": self.created_date,
            "thread_id": self.thread_id,
            "source_file": self.source_file,
        }


def clean_text(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"\[deleted\]|\[removed\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def infer_type(text: str) -> str:
    if len(text) > 240:
        return "post"
    return "comment"


def hash_id(parts: Iterable[str]) -> str:
    joined = "||".join(parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def build_docs(df: pd.DataFrame, source_file: str) -> list[SolrDoc]:
    docs: list[SolrDoc] = []
    subreddit_fallback = source_file.replace("_ai_posts_comments_5000pool.csv", "")

    for row in df.to_dict(orient="records"):
        raw_text = clean_text(row.get("Post/Comment text", ""))
        if not raw_text:
            continue

        posted_time = str(row.get("Posted time", ""))
        score = int(row.get("Number of upvotes", 0) or 0)
        subreddit = str(row.get("Subreddit the post/comment is from", "")).replace("r/", "")
        subreddit = subreddit or subreddit_fallback

        record_type = infer_type(raw_text)
        title = raw_text[:150] if record_type == "post" else ""
        body = raw_text
        full_text = f"{title} {body}".strip()

        # ---- NLP enrichment: lemmatization + concept extraction ----
        nlp_fields = process_for_indexing(full_text)

        docs.append(
            SolrDoc(
                id=hash_id([source_file, raw_text[:120], posted_time]),
                type=record_type,
                title=title,
                body=body,
                full_text=full_text,
                lemmatized_text=nlp_fields["lemmatized_text"],
                concepts=nlp_fields["concepts"],
                subreddit=subreddit,
                score=score,
                created_date=posted_time,
                thread_id=hash_id([subreddit, posted_time, raw_text[:50]])[:16],
                source_file=source_file,
            )
        )

    return docs


def prepare_docs(repo_root: Path, output_path: Path) -> tuple[int, int]:
    all_docs: list[dict] = []
    seen = set()

    for csv_name in INPUT_FILES:
        csv_path = repo_root / csv_name
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path)
        docs = build_docs(df, csv_name)

        for doc in docs:
            signature = (doc.full_text.lower(), doc.created_date, doc.subreddit)
            if signature in seen:
                continue
            seen.add(signature)
            all_docs.append(doc.to_dict())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for doc in all_docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    return len(all_docs), len(seen)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Solr JSONL docs from crawled Reddit CSV files.")
    parser.add_argument("--output", default="data/reddit_docs.jsonl", help="Output JSONL path")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    output_path = repo_root / args.output

    total_docs, unique_docs = prepare_docs(repo_root, output_path)
    print(f"Prepared {total_docs} Solr docs ({unique_docs} unique signatures).")
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    main()
