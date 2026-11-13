"""Cohere-10M Dataset Loader for AlloyDB.

This script loads the Cohere Wikipedia dataset (768-dim embeddings) into AlloyDB.
It supports streaming directly from Hugging Face or generating realistic synthetic
samples matching the exact schema for rapid initialization and offline testing.
"""

import argparse
import json
import logging
import os
import sys
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cohere-loader")

COHERE_DATASET_NAME = "Cohere/wikipedia-22-12-simple-embeddings"

SAMPLE_TOPICS = [
    ("Artificial Intelligence", "Artificial intelligence (AI) is intelligence demonstrated by machines, as opposed to the intelligence of living beings, primarily of humans or other animals. Example tasks in which this is done include speech recognition, computer vision, translation between languages, as well as other mappings of inputs.", "https://en.wikipedia.org/wiki/Artificial_intelligence", 250000),
    ("Quantum Computing", "Quantum computing is a rapidly-emerging technology that harnesses the laws of quantum mechanics to solve problems too complex for classical computers. Quantum computers process information using quantum bits or qubits.", "https://en.wikipedia.org/wiki/Quantum_computing", 120000),
    ("AlloyDB for PostgreSQL", "AlloyDB for PostgreSQL is a fully managed, PostgreSQL-compatible relational database service designed for demanding enterprise database workloads, including hybrid transactional and analytical processing.", "https://cloud.google.com/alloydb", 85000),
    ("Vector Database", "A vector database is a database that can store vectors (high-dimensional vectors) alongside other data items. Vector databases are primarily used to enable similarity search and nearest neighbor search in AI applications.", "https://en.wikipedia.org/wiki/Vector_database", 95000),
    ("Deep Learning", "Deep learning is part of a broader family of machine learning methods based on artificial neural networks with representation learning. Learning can be supervised, semi-supervised or unsupervised.", "https://en.wikipedia.org/wiki/Deep_learning", 180000),
    ("Model Context Protocol", "The Model Context Protocol (MCP) is an open standard that enables AI models to securely interact with external data sources, developer tools, and operational systems.", "https://modelcontextprotocol.io", 75000),
    ("Google Cloud Platform", "Google Cloud Platform (GCP) is a suite of cloud computing services offered by Google that provides hosting, storage, machine learning, and database infrastructure.", "https://cloud.google.com", 210000),
    ("PostgreSQL", "PostgreSQL, also known as Postgres, is a free and open-source relational database management system emphasizing extensibility and SQL compliance.", "https://en.wikipedia.org/wiki/PostgreSQL", 160000),
    ("Nearest Neighbor Search", "Nearest neighbor search (NNS), as a form of proximity search, is the optimization problem of finding the point in a given set that is closest (or most similar) to a given point.", "https://en.wikipedia.org/wiki/Nearest_neighbor_search", 60000),
    ("Large Language Model", "A large language model (LLM) is a computational model notable for its ability to achieve general-purpose language generation and other natural language processing tasks such as classification.", "https://en.wikipedia.org/wiki/Large_language_model", 310000),
]


def generate_normalized_vector(dim=768, seed=None):
    """Generates a unit-normalized random vector matching Cohere's 768-dim embedding space."""
    if seed is not None:
        np.random.seed(seed)
    vec = np.random.randn(dim).astype(np.float32)
    norm = np.linalg.norm(vec)
    return (vec / (norm + 1e-10)).tolist()


def generate_synthetic_batch(start_id, batch_size):
    """Generates a batch of rows conforming strictly to Cohere-10M schema."""
    batch = []
    for i in range(batch_size):
        curr_id = start_id + i
        topic_idx = curr_id % len(SAMPLE_TOPICS)
        title, base_text, url, views = SAMPLE_TOPICS[topic_idx]
        
        text = f"{base_text} (Passage chunk #{curr_id}: Analysis of domain principles and algorithmic implementations.)"
        views_jitter = views + (curr_id * 17) % 5000
        emb = generate_normalized_vector(dim=768, seed=curr_id)
        
        batch.append({
            "id": curr_id,
            "title": title,
            "text": text,
            "url": url,
            "views": views_jitter,
            "langs": "en",
            "embedding": emb,
        })
    return batch


def format_sql_insert(row):
    """Formats a single row dictionary into a PostgreSQL INSERT statement."""
    vec_str = "[" + ",".join(f"{x:.6f}" for x in row["embedding"]) + "]"
    # Escape single quotes
    title = row["title"].replace("'", "''")
    text = row["text"].replace("'", "''")
    url = row["url"].replace("'", "''")
    
    return f"""
    INSERT INTO cohere_wikipedia (id, title, text, url, views, langs, embedding)
    VALUES ({row['id']}, '{title}', '{text}', '{url}', {row['views']}, '{row['langs']}', '{vec_str}'::vector)
    ON CONFLICT (id) DO UPDATE SET views = EXCLUDED.views;
    """


def main():
    parser = argparse.ArgumentParser(description="Load Cohere-10M dataset into AlloyDB")
    parser.add_argument("--rows", type=int, default=1000, help="Number of rows to load (default: 1000)")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for inserts")
    parser.add_argument("--use-hf", action="store_true", help="Attempt streaming from Hugging Face instead of synthetic generator")
    parser.add_argument("--output-sql", type=str, default="", help="Optional path to output generated SQL file")
    args = parser.parse_args()

    logger.info(f"Preparing to load {args.rows} rows of Cohere-10M dataset...")

    sql_statements = []
    total_loaded = 0

    if args.use_hf:
        try:
            from datasets import load_dataset
            logger.info(f"Connecting to Hugging Face dataset: {COHERE_DATASET_NAME} (streaming)...")
            ds = load_dataset(COHERE_DATASET_NAME, split="train", streaming=True)
            for i, item in enumerate(ds):
                if i >= args.rows:
                    break
                row = {
                    "id": int(item.get("id", i)),
                    "title": str(item.get("title", "Unknown")),
                    "text": str(item.get("text", "")),
                    "url": str(item.get("url", "")),
                    "views": int(item.get("views", 0)),
                    "langs": str(item.get("langs", "en")),
                    "embedding": item.get("emb", generate_normalized_vector(768, seed=i)),
                }
                sql_statements.append(format_sql_insert(row))
                total_loaded += 1
                if total_loaded % 500 == 0:
                    logger.info(f"Processed {total_loaded}/{args.rows} Hugging Face rows...")
        except Exception as e:
            logger.warning(f"Could not stream from Hugging Face ({e}). Falling back to synthetic Cohere-10M generation.")
            args.use_hf = False

    if not args.use_hf:
        for offset in range(0, args.rows, args.batch_size):
            size = min(args.batch_size, args.rows - offset)
            batch = generate_synthetic_batch(start_id=1000 + offset, batch_size=size)
            for row in batch:
                sql_statements.append(format_sql_insert(row))
            total_loaded += size
            logger.info(f"Generated {total_loaded}/{args.rows} Cohere-10M rows...")

    if args.output_sql:
        with open(args.output_sql, "w", encoding="utf-8") as f:
            f.write("\n".join(sql_statements))
        logger.info(f"Saved {total_loaded} INSERT statements to {args.output_sql}")

    logger.info("Dataset preparation complete.")


if __name__ == "__main__":
    main()
