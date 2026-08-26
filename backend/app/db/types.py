from typing import Any

try:
    from pgvector.sqlalchemy import Vector as _Vector
    Vector = _Vector
except ImportError:
    from sqlalchemy.types import UserDefinedType

    class Vector(UserDefinedType):  # type: ignore[no-redef]
        """PostgreSQL pgvector column type for SQLAlchemy (fallback)."""

        cache_ok = True

        def __init__(self, dim: int) -> None:
            self.dim = dim

        def get_col_spec(self, **kw: Any) -> str:
            return f"vector({self.dim})"
