### Main ingestion pipeline for debate arguments

import pandas as pd
import uuid
from typing import Optional, List
import numpy as np
from sqlalchemy import create_engine, text

from .preprocessing import TextPreprocessor
from .embeddings import ArgumentEmbedder


class DebateIngestionPipeline:
    def __init__(
        self,
        db_url: str = "postgresql://aaryanpotdar:password@localhost:5432/postgres",
        embedding_model: Optional[str] = None,
        max_tokens: int = 384,
        chunk_size: Optional[int] = None,
    ):
        """Initialize the ingestion pipeline.

        Args:
            db_url: Database URL for PostgreSQL
            embedding_model: Name of the sentence-transformers model to use
            max_tokens: Maximum number of tokens allowed per text
            chunk_size: If provided, combine this many sentences into chunks
        """
        self.engine = create_engine(db_url)
        with self.engine.connect() as connection:
            connection.execute(
                text("""
                CREATE TABLE IF NOT EXISTS embeddings (
                            id UUID PRIMARY KEY,
                            embedding FLOAT8[],
                            text TEXT,
                            topic_id TEXT,
                            topic TEXT,
                            num_sentences INTEGER,
                            is_chunk BOOLEAN
                );
    """)
            )
        self.embedder = (
            ArgumentEmbedder(embedding_model) if embedding_model else ArgumentEmbedder()
        )
        self.preprocessor = TextPreprocessor(max_tokens=max_tokens)
        self.chunk_size = chunk_size

    def analyze_dataset(self, df: pd.DataFrame) -> dict:
        """Analyze the dataset and return statistics."""
        total_stats = {
            "total_rows": len(df),
            "total_sentences": 0,
            "avg_tokens_per_sentence": 0,
            "max_tokens": 0,
            "sentences_exceeding_limit": 0,
        }

        all_token_lengths = []

        for _, row in df.iterrows():
            if pd.isna(row["sentence"]):
                continue

            _, stats = self.preprocessor.preprocess_with_stats(str(row["sentence"]))
            total_stats["total_sentences"] += stats["num_sentences"]
            total_stats["sentences_exceeding_limit"] += stats[
                "sentences_exceeding_limit"
            ]
            total_stats["max_tokens"] = max(
                total_stats["max_tokens"], stats["max_tokens"]
            )
            all_token_lengths.append(stats["avg_tokens_per_sentence"])

        total_stats["avg_tokens_per_sentence"] = (
            sum(all_token_lengths) / len(all_token_lengths) if all_token_lengths else 0
        )

        return total_stats

    def save_embeddings_to_postgres(
        self,
        embeddings: np.ndarray,
        chunks: List[str],
        topic_id: str,
        topic: str,
    ):
        """Save embeddings and metadata to PostgreSQL.

        Args:
            embeddings: Numpy array of embeddings
            chunks: List of text chunks
            topic_id: ID of the topic
            topic: Topic name
        """
        # Create a DataFrame with embeddings and metadata
        df = pd.DataFrame(
            {
                "id": [str(uuid.uuid4()) for _ in chunks],
                "embedding": [embedding.tolist() for embedding in embeddings],
                "text": chunks,
                "topic_id": str(topic_id),
                "topic": topic,
                "num_sentences": [len(chunk.split(".")) for chunk in chunks],
                "is_chunk": [True] * len(chunks),  # Assuming all are chunks
            }
        )

        # Save to PostgreSQL
        df.to_sql("embeddings", con=self.engine, if_exists="append", index=False)
        print(f"Saved {len(chunks)} embeddings for topic {topic_id} to PostgreSQL.")

    def ingest_csv(
        self,
        csv_path: str,
        analyze_only: bool = False,
        skip_stats: bool = False,
        debug: bool = False,
    ) -> Optional[dict]:
        """Ingest arguments from CSV file with optional analysis only mode."""
        required_columns = ["id", "topic", "sentence"]
        df = pd.read_csv(csv_path)

        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        # Group by topic_id to process sentences from same topic together
        for topic_id, group in df.groupby("id"):
            if not skip_stats:
                stats = self.analyze_dataset(group)
                print(f"\nStats for topic {topic_id}:")
                print(f"Sentences: {stats['total_sentences']}")
                print(
                    f"Avg tokens per sentence: {stats['avg_tokens_per_sentence']:.2f}"
                )

            # Collect all sentences for this topic
            topic_sentences = []
            for _, row in group.iterrows():
                if pd.isna(row["sentence"]):
                    continue
                sentences = self.preprocessor.preprocess(str(row["sentence"]))
                topic_sentences.extend(sentences)

            # Chunk sentences from this topic together
            chunks = self.preprocessor.chunk_sentences(topic_sentences)
            if not skip_stats:
                print(f"Created {len(chunks)} chunks for topic {topic_id}")

            # Generate embeddings and save to PostgreSQL
            if not analyze_only:
                embeddings = self.embedder.embed_texts(chunks, debug=debug)
                self.save_embeddings_to_postgres(
                    embeddings=embeddings,
                    chunks=chunks,
                    topic_id=str(topic_id),
                    topic=group.iloc[0]["topic"],
                )
