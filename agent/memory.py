"""
agent/memory.py - Persistent memory for the DevOps agent using FAISS vector store.

Stores and retrieves past incidents, fixes, and context to enable
the agent to learn from history and avoid repeating mistakes.
"""

from __future__ import annotations

import json
import os
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from config import get_settings

# FAISS is optional at import time so tests can mock it
try:
    import faiss  # type: ignore
    _FAISS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _FAISS_AVAILABLE = False


@dataclass
class MemoryEntry:
    """A single memory record."""
    id: str
    query: str
    answer: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class AgentMemory:
    """
    Vector-backed memory store.

    Embeds text using OpenAI embeddings (text-embedding-3-small) and
    stores the resulting vectors in a FAISS index so that semantically
    similar past incidents can be retrieved quickly.

    Falls back to a plain list search when FAISS / OpenAI are unavailable
    (useful for unit tests and offline environments).
    """

    EMBEDDING_DIM = 1536  # text-embedding-3-small output dimension

    def __init__(self) -> None:
        settings = get_settings()
        self._dir = Path(settings.memory_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_results = settings.max_memory_results

        self._index_path = self._dir / "index.faiss"
        self._entries_path = self._dir / "entries.pkl"

        # In-memory state
        self._entries: list[MemoryEntry] = []
        self._index: Any = None  # faiss.IndexFlatL2 when available

        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, entry: MemoryEntry) -> None:
        """Add a new memory entry (with optional embedding)."""
        self._entries.append(entry)
        if _FAISS_AVAILABLE and self._index is not None:
            vec = self._embed(entry.query)
            if vec is not None:
                self._index.add(np.array([vec], dtype="float32"))
        self._save()

    def search(self, query: str, k: int | None = None) -> list[MemoryEntry]:
        """Return the *k* most relevant past entries for *query*."""
        k = k or self._max_results
        if not self._entries:
            return []

        if _FAISS_AVAILABLE and self._index is not None and self._index.ntotal > 0:
            vec = self._embed(query)
            if vec is not None:
                distances, indices = self._index.search(
                    np.array([vec], dtype="float32"), min(k, self._index.ntotal)
                )
                return [self._entries[i] for i in indices[0] if i < len(self._entries)]

        # Fallback: return the most recent entries
        return self._entries[-k:]

    def all_entries(self) -> list[MemoryEntry]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries = []
        self._index = self._make_index()
        self._save()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_index(self) -> Any:
        if _FAISS_AVAILABLE:
            return faiss.IndexFlatL2(self.EMBEDDING_DIM)
        return None

    def _embed(self, text: str) -> list[float] | None:
        """Return embedding vector or None on error."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=get_settings().openai_api_key)
            response = client.embeddings.create(
                input=text, model="text-embedding-3-small"
            )
            return response.data[0].embedding
        except Exception:
            return None

    def _save(self) -> None:
        with open(self._entries_path, "wb") as f:
            pickle.dump(self._entries, f)
        if _FAISS_AVAILABLE and self._index is not None:
            faiss.write_index(self._index, str(self._index_path))

    def _load(self) -> None:
        if self._entries_path.exists():
            with open(self._entries_path, "rb") as f:
                self._entries = pickle.load(f)

        if _FAISS_AVAILABLE:
            if self._index_path.exists():
                self._index = faiss.read_index(str(self._index_path))
            else:
                self._index = self._make_index()
                # Build index from existing entries (no stored embeddings)
                # We just create an empty index; embeddings will be added on next add()
