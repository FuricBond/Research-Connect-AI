from datetime import date

from pydantic import BaseModel, HttpUrl


class Opportunity(BaseModel):
    id: str
    title: str
    source: str
    opportunity_type: str
    deadline: date | None = None
    url: HttpUrl | None = None
    summary: str | None = None
