"""Embedding service for semantic search using sentence transformers.

Provides in-memory tokenization and semantic search capabilities using
cosine similarity on sentence transformer embeddings.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import List, Optional

import numpy as np

# Set tokenizer parallelism to avoid fork warnings
# This must be set before importing sentence_transformers
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

logger = logging.getLogger(__name__)

# Global singleton instance
_embedding_service: Optional[EmbeddingService] = None
_embedding_service_lock = threading.RLock()


class EmbeddingService:
    """Service for generating embeddings using sentence transformers.

    Uses lazy loading singleton pattern - model is loaded on first use
    and reused for subsequent calls.
    """

    def __init__(self) -> None:
        """Initialize the embedding service (model loaded lazily)."""
        self._model: Optional[object] = None
        self._model_lock = threading.RLock()

    def _ensure_model_loaded(self) -> bool:
        """Load the sentence transformer model if not already loaded.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        if self._model is not None:
            return True

        with self._model_lock:
            # Double-check after acquiring lock
            if self._model is not None:
                return True

            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading sentence transformer model: all-MiniLM-L6-v2")
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Sentence transformer model loaded successfully")
                return True
            except Exception as e:
                logger.warning(
                    f"Failed to load sentence transformer model: {e}. "
                    "Semantic search will fallback to heuristic scoring."
                )
                return False

    def embed_text(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for a single text string.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector as numpy array, or None if model failed to load.
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            if not self._ensure_model_loaded():
                return None
            # Get embedding dimension from model
            return np.zeros(self._get_embedding_dimension(), dtype=np.float32)

        if not self._ensure_model_loaded():
            return None

        try:
            embedding = self._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
            return embedding.astype(np.float32)
        except Exception as e:
            logger.warning(f"Failed to generate embedding for text: {e}")
            return None

    def embed_batch(self, texts: List[str]) -> Optional[np.ndarray]:
        """Generate embeddings for a batch of texts.

        Args:
            texts: List of texts to embed.

        Returns:
            Array of embedding vectors (shape: [len(texts), embedding_dim]),
            or None if model failed to load.
        """
        if not texts:
            return None

        if not self._ensure_model_loaded():
            return None

        try:
            # Filter out empty texts
            non_empty_texts = [t if t and t.strip() else " " for t in texts]
            embeddings = self._model.encode(
                non_empty_texts, convert_to_numpy=True, normalize_embeddings=True, batch_size=32
            )
            return embeddings.astype(np.float32)
        except Exception as e:
            logger.warning(f"Failed to generate batch embeddings: {e}")
            return None

    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            vec1: First embedding vector.
            vec2: Second embedding vector.

        Returns:
            Cosine similarity score between 0.0 and 1.0.
        """
        if vec1 is None or vec2 is None:
            return 0.0

        # Normalize vectors (should already be normalized, but ensure)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0

        # Cosine similarity = dot product of normalized vectors
        similarity = np.dot(vec1 / norm1, vec2 / norm2)
        # Clamp to [0, 1] range (should already be in this range, but ensure)
        return float(np.clip(similarity, 0.0, 1.0))

    def _get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by the model.

        Returns:
            Embedding dimension (384 for all-MiniLM-L6-v2).
        """
        if self._model is None:
            # Default dimension for all-MiniLM-L6-v2
            return 384
        # Get dimension from model if available
        try:
            return self._model.get_sentence_embedding_dimension()
        except Exception:
            return 384


def get_embedding_service() -> EmbeddingService:
    """Get the global singleton EmbeddingService instance.

    Returns:
        EmbeddingService instance.
    """
    global _embedding_service
    if _embedding_service is None:
        with _embedding_service_lock:
            if _embedding_service is None:
                _embedding_service = EmbeddingService()
    return _embedding_service

