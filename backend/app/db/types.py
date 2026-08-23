from typing import Any
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    """PostgreSQL pgvector column type for SQLAlchemy."""

    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dim})"


# Optional integration with pgvector-python if installed
try:
    from pgvector.sqlalchemy import Vector as _PgVectorType  # type: ignore[import-untyped]
except ImportError:
    pass
