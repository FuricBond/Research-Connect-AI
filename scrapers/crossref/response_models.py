"""
Lightweight dataclass representations for raw Crossref API messages.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CrossrefAuthorResponse:
    given: str | None = None
    family: str | None = None
    name: str | None = None
    sequence: str | None = None
    ORCID: str | None = None
    affiliation: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CrossrefWorkItemResponse:
    DOI: str
    title: list[str] = field(default_factory=list)
    subtitle: list[str] = field(default_factory=list)
    abstract: str | None = None
    type: str | None = None
    publisher: str | None = None
    container_title: list[str] = field(default_factory=list)
    short_container_title: list[str] = field(default_factory=list)
    volume: str | None = None
    issue: str | None = None
    page: str | None = None
    article_number: str | None = None
    ISSN: list[str] = field(default_factory=list)
    URL: str | None = None
    author: list[CrossrefAuthorResponse] = field(default_factory=list)
    license: list[dict[str, Any]] = field(default_factory=list)
    subject: list[str] = field(default_factory=list)
    is_referenced_by_count: int = 0
    reference_count: int = 0
    published_online: dict[str, Any] | None = None
    published_print: dict[str, Any] | None = None
    created: dict[str, Any] | None = None
    issued: dict[str, Any] | None = None
