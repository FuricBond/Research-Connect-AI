"""
Audit SEC-01 — list the stored links that are not plain web addresses. Read-only.

The API has refused such values since the check was added, but rows written earlier keep theirs:
nothing is deleted behind a person's back, and the frontend never makes a link of one. This report
is how an administrator finds them, to ask the author to correct them.

    python -m scripts.report_unsafe_urls

Prints the table, column and row id of each value; the value itself is left out on purpose.
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.url_safety import is_safe_web_url
from app.db.session import SessionLocal
from app.models.opportunity import OpportunityModel
from app.models.research_posting import ResearchPostingModel
from app.models.research_posting_application import ResearchPostingApplicationModel
from app.models.research_submission import ResearchSubmissionModel

CHECKED = (
    (ResearchPostingModel, "external_url"),
    (ResearchPostingApplicationModel, "portfolio_url"),
    (ResearchSubmissionModel, "submission_url"),
    (OpportunityModel, "website_url"),
    (OpportunityModel, "submission_url"),
)


def main() -> int:
    found = 0
    with SessionLocal() as db:
        for model, column_name in CHECKED:
            column = getattr(model, column_name)
            rows = db.execute(select(model.id, column).where(column.is_not(None))).all()
            for row_id, value in rows:
                if not is_safe_web_url(value):
                    found += 1
                    print(f"{model.__tablename__}.{column_name}\t{row_id}")
    print(f"{found} stored link(s) are not plain web addresses.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
