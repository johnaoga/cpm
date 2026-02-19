"""SBERT-based similarity computations for papers ↔ topics and topics ↔ topics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np

from .models import Paper, Topic


def _get_model(model_name: str = "all-MiniLM-L6-v2"):
    """Lazy-load a SentenceTransformer model."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


# ---------------------------------------------------------------------------
# Paper ↔ Topic similarity
# ---------------------------------------------------------------------------

def compute_paper_topic_scores(
    papers: list[Paper],
    topics: list[Topic],
    model_name: str = "all-MiniLM-L6-v2",
) -> dict[int, dict[int, float]]:
    """Compute cosine similarity between each paper title and each topic name.

    Returns:
        {paper_id: {topic_id: score, ...}, ...}
    """
    model = _get_model(model_name)

    paper_texts = [p.title for p in papers]
    topic_texts = [t.name for t in topics]

    paper_embs = model.encode(paper_texts, convert_to_numpy=True, show_progress_bar=True)
    topic_embs = model.encode(topic_texts, convert_to_numpy=True, show_progress_bar=True)

    # Normalise for cosine similarity
    paper_embs = paper_embs / np.linalg.norm(paper_embs, axis=1, keepdims=True)
    topic_embs = topic_embs / np.linalg.norm(topic_embs, axis=1, keepdims=True)

    sim_matrix = paper_embs @ topic_embs.T  # (n_papers, n_topics)

    scores: dict[int, dict[int, float]] = {}
    for i, paper in enumerate(papers):
        scores[paper.paper_id] = {
            topic.topic_id: float(sim_matrix[i, j])
            for j, topic in enumerate(topics)
        }
    return scores


def save_paper_topic_scores(
    scores: dict[int, dict[int, float]],
    path: str | Path,
) -> None:
    """Save paper-topic scores to JSON."""
    # Convert keys to strings for JSON
    out = {str(pid): {str(tid): round(s, 6) for tid, s in tscores.items()}
           for pid, tscores in scores.items()}
    Path(path).write_text(json.dumps(out, indent=2))


def load_paper_topic_scores(path: str | Path) -> dict[int, dict[int, float]]:
    """Load paper-topic scores from JSON."""
    raw = json.loads(Path(path).read_text())
    return {
        int(pid): {int(tid): float(s) for tid, s in tscores.items()}
        for pid, tscores in raw.items()
    }


# ---------------------------------------------------------------------------
# Topic ↔ Topic similarity matrix
# ---------------------------------------------------------------------------

def compute_topic_similarity_matrix(
    topics: list[Topic],
    model_name: str = "all-MiniLM-L6-v2",
) -> np.ndarray:
    """Compute the topic-topic cosine similarity matrix.

    Returns:
        (n_topics, n_topics) numpy array.
    """
    model = _get_model(model_name)
    texts = [t.name for t in topics]
    embs = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
    embs = embs / np.linalg.norm(embs, axis=1, keepdims=True)
    return embs @ embs.T


def save_topic_similarity_matrix(
    matrix: np.ndarray,
    topics: list[Topic],
    path: str | Path,
) -> None:
    """Save the topic similarity matrix to JSON with topic metadata."""
    topic_ids = [t.topic_id for t in topics]
    topic_names = [t.name for t in topics]
    out = {
        "topic_ids": topic_ids,
        "topic_names": topic_names,
        "matrix": matrix.tolist(),
    }
    Path(path).write_text(json.dumps(out, indent=2))


def load_topic_similarity_matrix(
    path: str | Path,
) -> tuple[list[int], list[str], np.ndarray]:
    """Load topic similarity matrix from JSON.

    Returns:
        (topic_ids, topic_names, matrix)
    """
    raw = json.loads(Path(path).read_text())
    return (
        raw["topic_ids"],
        raw["topic_names"],
        np.array(raw["matrix"]),
    )


# ---------------------------------------------------------------------------
# Merge suggestion helper
# ---------------------------------------------------------------------------

def suggest_topic_merges(
    topics: list[Topic],
    sim_matrix: np.ndarray,
    pref_counts: dict[int, int],
    sim_threshold: float = 0.75,
    min_pref_count: int = 3,
) -> list[tuple[Topic, Topic, float]]:
    """Suggest pairs of topics that could be merged.

    A merge is suggested when:
      - cosine similarity ≥ sim_threshold, AND
      - at least one of the two topics has ≤ min_pref_count papers preferring it.

    Returns list of (topic_a, topic_b, similarity_score).
    """
    suggestions: list[tuple[Topic, Topic, float]] = []
    n = len(topics)
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(sim_matrix[i, j])
            if sim < sim_threshold:
                continue
            cnt_i = pref_counts.get(topics[i].topic_id, 0)
            cnt_j = pref_counts.get(topics[j].topic_id, 0)
            if cnt_i <= min_pref_count or cnt_j <= min_pref_count:
                suggestions.append((topics[i], topics[j], sim))
    suggestions.sort(key=lambda x: -x[2])
    return suggestions
