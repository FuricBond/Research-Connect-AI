"""
A small, deterministic literature corpus for the discovery tests.

The demo seeder creates no research works, and real embeddings need a model download, which
a reproducible environment must not depend on. So this inserts six works through the
backend's own ORM models and gives them, and the seeded opportunities, fixed 384-dimensional
vectors built from topic directions: works and venues on the same topic are close, others
are not. That exercises the pgvector channels (stored vectors compared in PostgreSQL) end to
end. The one step it cannot exercise offline is embedding a free-text *query*, which is
reported separately.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import uuid

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

DIM = 384
TOPICS = ("ir", "nlp", "hci", "ml", "data")
MARKER = "E2E-"  # openalex_id prefix of every work inserted here


def _topic_vector(name: str) -> list[float]:
    block = DIM // len(TOPICS)
    start = TOPICS.index(name) * block
    return [1.0 if start <= i < start + block else 0.0 for i in range(DIM)]


def vector(*topics: str, salt: str = "") -> list[float]:
    """Unit vector along the given topics plus small deterministic noise."""
    digest = hashlib.sha256(salt.encode()).digest() * (DIM // 32 + 1)
    v = [sum(_topic_vector(t)[i] for t in topics) + (digest[i] / 255.0) * 0.05 for i in range(DIM)]
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


WORKS = [
    ("Dense passage retrieval for open-domain question answering",
     "We learn dense representations for passage retrieval and show they outperform sparse BM25 retrieval.",
     ("ir", "nlp"), 2020, 3100),
    ("Learning to rank for information retrieval with neural models",
     "A study of neural learning-to-rank models for information retrieval and search relevance.",
     ("ir", "ml"), 2019, 870),
    ("Reproducible retrieval evaluation with shared test collections",
     "Benchmarking information retrieval systems requires reproducible test collections and metrics.",
     ("ir", "data"), 2021, 240),
    ("Query understanding for low-resource languages",
     "Query understanding and retrieval for languages with little training data.",
     ("nlp", "ir"), 2022, 95),
    ("Accessible interfaces for screen reader users",
     "Design guidelines for accessible user interfaces evaluated with screen reader users.",
     ("hci",), 2018, 410),
    ("Research data management practices in computational science",
     "A survey of research data management, curation and sharing practices.",
     ("data",), 2017, 150),
]

OPPORTUNITY_TOPICS = {
    "International Conference on Information Retrieval Systems": ("ir",),
    "Workshop on Neural Retrieval Methods": ("ir", "ml"),
    "Journal of Information Retrieval Research": ("ir",),
    "Conference on Natural Language Understanding": ("nlp",),
    "Conference on Applied Machine Learning": ("ml",),
    "Transactions on Applied Machine Intelligence": ("ml",),
    "Symposium on Human-Computer Interaction and Accessibility": ("hci",),
    "Workshop on Research Data Management": ("data",),
}


def ensure_corpus(engine: Engine) -> dict[str, str]:
    """Inserts the works once; returns {title: work id}. Safe to call repeatedly."""
    from app.models.research_knowledge import ResearchWorkModel

    with Session(engine) as session:
        existing = {
            w.title: str(w.id)
            for w in session.execute(
                select(ResearchWorkModel).where(ResearchWorkModel.openalex_id.like(f"{MARKER}%"))
            ).scalars()
        }
        now = datetime.now(timezone.utc)
        for index, (title, abstract, topics, year, citations) in enumerate(WORKS):
            if title in existing:
                continue
            work = ResearchWorkModel(
                id=uuid.uuid4(),
                openalex_id=f"{MARKER}W{index:04d}",
                title=title,
                abstract=abstract,
                publication_year=year,
                work_type="article",
                language="en",
                cited_by_count=citations,
                is_oa=True,
                embedding=vector(*topics, salt=title),
                embedding_model="e2e-synthetic-topic-vectors",
                embedded_at=now,
            )
            session.add(work)
            existing[title] = str(work.id)
        session.commit()
        for title, topics in OPPORTUNITY_TOPICS.items():
            literal = "[" + ",".join(f"{x:.6f}" for x in vector(*topics, salt=title)) + "]"
            session.execute(
                text("UPDATE opportunities SET embedding = CAST(:v AS vector) WHERE title = :t AND embedding IS NULL"),
                {"v": literal, "t": title},
            )
        session.commit()
    return existing
