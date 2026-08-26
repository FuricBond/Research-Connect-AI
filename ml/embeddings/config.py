"""
Embedding configuration for Phase 2.3B.

All constants are read from the app-wide ``Settings`` object when available,
falling back to sensible defaults so that the ML layer can run independently
of the FastAPI server (e.g. from a CLI script).
"""
from __future__ import annotations

import os

# Default embedding model — 384-dim, multilingual-capable, well-supported.
DEFAULT_MODEL_NAME: str = "all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIM: int = 384
DEFAULT_BATCH_SIZE: int = 32
DEFAULT_DEVICE: str = "cpu"

# Runtime overrides from environment (mirror of Settings fields)
EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL_NAME)
EMBEDDING_DIM: int = int(os.environ.get("EMBEDDING_DIM", str(DEFAULT_EMBEDDING_DIM)))
EMBEDDING_BATCH_SIZE: int = int(
    os.environ.get("EMBEDDING_BATCH_SIZE", str(DEFAULT_BATCH_SIZE))
)
EMBEDDING_DEVICE: str = os.environ.get("EMBEDDING_DEVICE", DEFAULT_DEVICE)
