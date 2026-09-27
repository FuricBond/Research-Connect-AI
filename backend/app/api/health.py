import logging

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.schema_status import check_schema
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Liveness: the process is up and serving. Touches nothing else."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness_check(response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    """
    Readiness (Phase 6.5): the database answers and its schema is the one this code expects.

    503 until both hold. The body carries only coarse states; the revisions involved are
    logged server-side, not disclosed here.
    """
    result = check_schema(db)
    if not result.ready:
        logger.warning("not ready: %s", result.describe())
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if result.ready else "not_ready",
        "database": result.database,
        "schema": result.schema,
    }
