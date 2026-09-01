from typing import Any

from sqlalchemy.types import UserDefinedType

try:
    from pgvector.sqlalchemy import Vector as _Vector
    Vector = _Vector
except ImportError:
    class Vector(UserDefinedType):  # type: ignore[no-redef]
        """PostgreSQL pgvector column type for SQLAlchemy (fallback)."""

        cache_ok = True

        def __init__(self, dim: int) -> None:
            self.dim = dim

        def get_col_spec(self, **kw: Any) -> str:
            return f"vector({self.dim})"


class TSVector(UserDefinedType):
    """PostgreSQL tsvector column type for SQLAlchemy (portable across dialects)."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "tsvector"
